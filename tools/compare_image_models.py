"""Offline person detection comparison. No Django imports or database writes."""
import argparse
import csv
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.camera_preview import ImageInput
from tools.camera_masking import load_mask, apply_mask, comparison_image

CONDITIONS = [('yolo11n', 640), ('yolo11n', 1280), ('yolo11s', 1280)]
YOLO26_CONDITIONS = [('yolo11n', 1280), ('yolo11s', 1280), ('yolo26n', 1280), ('yolo26s', 1280)]


def save_image(path, frame):
    import cv2
    ok, data = cv2.imencode('.png', frame)
    if not ok:
        raise OSError('Could not encode comparison image')
    data.tofile(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(args):
    import cv2
    import numpy as np
    import ultralytics
    import torch
    from ultralytics import YOLO
    conditions = YOLO26_CONDITIONS if getattr(args, 'preset', 'legacy') == 'yolo11-yolo26' else CONDITIONS
    models_dir = ROOT / '.camera-runtime' / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: models_dir / (name + '.pt') for name, _ in conditions}
    if args.download_models:
        from ultralytics.utils.downloads import attempt_download_asset
        for path in paths.values():
            if not path.is_file():
                attempt_download_asset(path)
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f'Missing model: {path.name}; use --download-models')
    source = ImageInput(args.image)
    if not source.isOpened():
        raise ValueError('Image cannot be decoded')
    _, frame = source.read()
    mask = load_mask(args.mask_config, frame.shape)
    masked = apply_mask(frame, mask)
    output = args.output_dir / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    # Preserve original encoded source, settings, and hashes for reproducibility.
    (output / ('original' + args.image.suffix)).write_bytes(args.image.read_bytes())
    report = {'created_at': datetime.now().astimezone().isoformat(), 'image': str(args.image.resolve()),
              'image_sha256': digest(args.image), 'width': frame.shape[1], 'height': frame.shape[0],
              'mask': mask, 'mask_file': str(args.mask_config) if args.mask_config else None,
              'actual_count': None, 'actual_count_outside_mask': None, 'notes': '', 'db_saved': False,
              'device': args.device, 'conf': args.conf, 'iou_requested_for_nms': args.iou, 'classes': [0],
              'conditions': conditions, 'python': sys.version, 'executable': sys.executable,
              'repeats': args.repeats, 'warmup_calls_per_condition_and_stage': 1,
              'timing_definition': 'CPU predict wall time includes preprocessing/inference/postprocessing (NMS only when used); excludes model load, warmup, plotting and file saving',
              'ultralytics': ultralytics.__version__, 'torch': torch.__version__, 'opencv': cv2.__version__,
              'scope': 'Single demo image; not live stream or multi-camera validation', 'results': []}
    models = {}
    plotted = {}
    stages = [('unmasked', frame)]
    if args.mask_config:
        stages.append(('masked', masked))
    for stage, pixels in stages:
        logging.info('Stage: %s', stage)
        for name, size in conditions:
            model = models.get(name)
            if model is None:
                model = YOLO(str(paths[name]), task='detect')
                if model.names.get(0) != 'person':
                    raise ValueError('Model class 0 is not person')
                models[name] = model
            native_end2end = bool(getattr(model.model, 'end2end', False))
            settings = dict(classes=[0], conf=args.conf, imgsz=size, max_det=300,
                            device=args.device, verbose=False, save=False)
            if not native_end2end:
                settings['iou'] = args.iou
            model.predict(pixels.copy(), **settings)  # unmeasured warmup
            effective_end2end = bool(getattr(model.predictor.model, 'end2end', False))
            if effective_end2end != native_end2end:
                raise ValueError('Unexpected detection head change; refuse misleading inference settings')
            elapsed, counts, speeds = [], [], []
            result = None
            for _ in range(args.repeats):
                started = time.perf_counter()
                current = model.predict(pixels.copy(), **settings)[0]
                elapsed.append((time.perf_counter() - started) * 1000)
                counts.append(len(current.boxes))
                speeds.append(current.speed)
                if result is None:
                    result = current
            key = f'{name}_{size}'
            image = result.plot()
            annotated = cv2.copyMakeBorder(image, 55, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
            cv2.putText(annotated, f'{stage} {key}: {counts[0]} persons | {statistics.median(elapsed):.1f} ms',
                        (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            filename = f'{stage}_{key}.png'
            save_image(output / filename, annotated)
            plotted[(stage, key)] = (result, annotated)
            record = {'stage': stage, 'model': name, 'model_sha256': digest(paths[name]), 'imgsz': size,
                      'conf': args.conf, 'iou': None if effective_end2end else args.iou,
                      'nms_used': not effective_end2end, 'end2end': effective_end2end,
                      'inference_method': 'native end-to-end, NMS-free' if effective_end2end else 'traditional detection with NMS',
                      'predict_settings': settings, 'ultralytics': ultralytics.__version__, 'torch': torch.__version__,
                      'opencv': cv2.__version__, 'device': args.device,
                      'count': counts[0], 'counts_each_repeat': counts,
                      'predict_wall_ms_each_repeat': elapsed, 'predict_wall_ms_median': statistics.median(elapsed),
                      'ultralytics_speed_ms_each_repeat': speeds, 'actual_count': None, 'missed_people': None,
                      'false_detections': None, 'notes': '', 'image': filename,
                      'boxes': result.boxes.xyxy.cpu().tolist(), 'scores': result.boxes.conf.cpu().tolist()}
            report['results'].append(record)
            logging.info('%s %s people=%d median=%.1fms', stage, key, counts[0], statistics.median(elapsed))
            (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    for stage, _ in stages:
        panels = []
        for name, size in conditions:
            panel = plotted[(stage, f'{name}_{size}')][1]
            panels.append(cv2.resize(panel, (640, round(panel.shape[0] * 640 / panel.shape[1]))))
        rows.append(np.concatenate(panels, axis=1))
    save_image(output / 'overview.png', np.concatenate(rows, axis=0))
    if args.mask_config:
        for name, size in conditions:
            key = f'{name}_{size}'
            save_image(output / f'before-after_{key}.png', comparison_image(plotted[('unmasked', key)][0], plotted[('masked', key)][0]))
    fields = ['stage', 'model', 'imgsz', 'conf', 'iou', 'nms_used', 'end2end', 'ultralytics', 'count', 'predict_wall_ms_median',
              'actual_count', 'missed_people', 'false_detections', 'notes', 'image']
    with (output / 'review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(report['results'])
    logging.info('Results: %s (NO DB SAVE)', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--preset', choices=['legacy', 'yolo11-yolo26'], default='legacy', help='Keep existing comparison or compare YOLO11n/s and YOLO26n/s at 1280')
    parser.add_argument('--mask-config', type=Path)
    parser.add_argument('--conf', type=float, default=0.25)
    parser.add_argument('--iou', type=float, default=0.7)
    parser.add_argument('--device', choices=['cpu'], default='cpu', help='CPU ensures wall timing includes completed inference')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--download-models', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.camera-runtime' / 'model-comparisons')
    args = parser.parse_args()
    if not args.image.is_file() or not 0 < args.conf <= 1 or not 0 < args.iou <= 1 or args.repeats < 1:
        parser.error('Existing image, conf/iou in (0,1], and positive repeats required')
    compare(args)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    main()
