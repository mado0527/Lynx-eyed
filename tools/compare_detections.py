"""Compare settings on the same saved frames; no Django or DB access."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.camera_preview import CONFIG_DIR  # Configure local Ultralytics storage first.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_dir', type=Path)
    parser.add_argument('--max-images', type=int, default=6)
    parser.add_argument('--conf', type=float, default=0.35)
    parser.add_argument('--iou', type=float, default=0.5)
    args = parser.parse_args()
    if args.max_images < 1 or not 0 < args.conf <= 1 or not 0 < args.iou <= 1:
        parser.error('max-images must be positive and conf/iou in (0, 1]')
    import cv2
    import numpy as np
    import json
    from datetime import datetime
    from uuid import uuid4
    from ultralytics import YOLO
    model = YOLO(str(ROOT / '.camera-runtime/models/yolo11n.pt'), task='detect')
    files = sorted(args.capture_dir.glob('*.npz'))[:args.max_images]
    if not files:
        parser.error('No original frames found in capture directory')
    output = args.capture_dir / ('comparison-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    output.mkdir(parents=True)
    for source in files:
        metadata = json.loads(source.with_suffix('.json').read_text(encoding='utf-8'))
        with np.load(source, allow_pickle=False) as data:
            frame = data['frame']
        settings = [('Baseline', metadata['conf'], metadata['iou']),
                    ('Confidence only', args.conf, metadata['iou']),
                    ('IoU only', metadata['conf'], args.iou)]
        panels = []
        summary = []
        for label, conf, iou in settings:
            result = model.predict(frame, classes=[0], conf=conf, iou=iou,
                                   imgsz=metadata['imgsz'], device='cpu', verbose=False, save=False)[0]
            image = cv2.copyMakeBorder(result.plot(), 42, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
            count = len(result.boxes)
            cv2.putText(image, f'{label}: {count} | conf={conf} iou={iou}', (8, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            panels.append(image)
            summary.append({'label': label, 'count': count, 'conf': conf, 'iou': iou,
                            'boxes': result.boxes.xyxy.cpu().tolist(), 'scores': result.boxes.conf.cpu().tolist()})
        # One image per source frame, stacked vertically for clear side-by-side review.
        if not cv2.imwrite(str(output / (source.stem + '.jpg')), np.vstack(panels)):
            raise OSError('Comparison image write failed')
        (output / (source.stem + '.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(source.stem + ': ' + ', '.join(f"{item['label']}={item['count']}" for item in summary))
    print('Comparison images:', output)
    print('Review each person box, not just the total. No production thresholds changed; no DB writes.')


if __name__ == '__main__':
    main()
