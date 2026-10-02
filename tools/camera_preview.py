"""Standalone local preview; deliberately never imports Django or writes to DB."""
import argparse
import logging
import os
from pathlib import Path
import sys
import time
import json
from datetime import datetime
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / '.camera-runtime' / 'config'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('YOLO_CONFIG_DIR', str(CONFIG_DIR))


def parse_args():
    parser = argparse.ArgumentParser(description='OpenCV MJPEG / YOLO11n person preview. No masking or DB writes.')
    parser.add_argument('--source', default='http://192.168.0.134:8080/?action=stream')
    parser.add_argument('--capture-only', action='store_true', help='Verify frame acquisition without loading YOLO')
    parser.add_argument('--headless', action='store_true', help='Verify without opening a preview window')
    parser.add_argument('--max-frames', type=int, default=0, help='Stop after N successful frames; 0 means continuous')
    parser.add_argument('--timeout', type=float, default=8, help='Stream open/read timeout in seconds')
    parser.add_argument('--conf', type=float, default=0.25, help='Person confidence threshold')
    parser.add_argument('--iou', type=float, default=0.7, help='NMS IoU threshold')
    parser.add_argument('--save-changes', action='store_true', help='Save first frame and count changes locally')
    parser.add_argument('--max-images', type=int, default=20, help='Maximum annotated images per run')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.camera-runtime' / 'captures')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--model', type=Path, default=ROOT / '.camera-runtime' / 'models' / 'yolo11n.pt')
    args = parser.parse_args()
    if args.timeout <= 0 or args.max_frames < 0 or args.imgsz <= 0 or not 0 < args.conf <= 1 or not 0 < args.iou <= 1 or args.max_images < 1:
        parser.error('timeout/imgsz/max-images must be positive, max-frames nonnegative, conf/iou in (0, 1]')
    return args


class ChangeSnapshots:
    def __init__(self, args):
        self.args = args
        self.previous = None
        self.saved = 0
        self.directory = args.output_dir / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])

    def consider(self, frame, result, count):
        import cv2
        import numpy as np
        changed = count != self.previous
        previous = self.previous
        self.previous = count
        if not changed or self.saved >= self.args.max_images:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = f'{self.saved + 1:03d}_{previous if previous is not None else "start"}-to-{count}'
        # Keep boxes unobscured; count and settings are in an extra top border.
        image = cv2.copyMakeBorder(result.plot(), 45, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
        cv2.putText(image, f'Persons: {count} | conf={self.args.conf} iou={self.args.iou} | NO DB SAVE',
                    (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        if not cv2.imwrite(str(self.directory / (stem + '.jpg')), image):
            raise OSError('Snapshot write failed')
        self.saved += 1
        # Preserve original pixels for identical-frame comparison, not video recording.
        np.savez_compressed(self.directory / (stem + '.npz'), frame=frame)
        metadata = {
            'captured_at': datetime.now().astimezone().isoformat(),
            'previous_count': previous, 'count': count, 'conf': self.args.conf,
            'iou': self.args.iou, 'imgsz': self.args.imgsz, 'masking': False,
            'model': self.args.model.name,
            'boxes': result.boxes.xyxy.cpu().tolist(),
            'scores': result.boxes.conf.cpu().tolist(),
        }
        (self.directory / (stem + '.json')).write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        logging.info('Count change %s -> %d: snapshot %d/%d saved to %s',
                     previous, count, self.saved, self.args.max_images, self.directory)
        if self.saved == self.args.max_images:
            logging.info('Image limit reached; preview continues without further saves. Existing images retained.')


def run(args):
    import cv2
    timeout_ms = int(args.timeout * 1000)
    logging.info('Opening input (no masking; DB writes disabled)')
    capture = cv2.VideoCapture(args.source, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms,
    ])
    window = 'Lynx-eyed | Person preview | NO DB SAVE | Q / Esc to stop'
    try:
        if not capture.isOpened():
            logging.error('Input open failed. No count produced; nothing saved.')
            return 1
        ok, frame = capture.read()
        if not ok or frame is None or not frame.size:
            logging.error('First frame acquisition failed. Nothing saved.')
            return 1
        logging.info('Frame acquired: %dx%d', frame.shape[1], frame.shape[0])
        model = None
        if not args.capture_only:
            if not args.model.is_file():
                logging.error('Model is missing. Download the official yolo11n.pt to the documented local path.')
                return 1
            from ultralytics import YOLO
            model = YOLO(str(args.model), task='detect')
            if model.names.get(0) != 'person':
                logging.error('Model class 0 is not person; stopping.')
                return 1
        if not args.headless:
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 960, 540)
        frames = 0
        last_log = 0
        snapshots = ChangeSnapshots(args) if args.save_changes and model is not None else None
        logging.info('Detection settings: confidence=%s NMS IoU=%s', args.conf, args.iou)
        while True:
            if model is None:
                preview = frame.copy()
                text = 'Capture OK | No masking | NO DB SAVE'
            else:
                result = model.predict(frame, classes=[0], conf=args.conf, iou=args.iou, imgsz=args.imgsz,
                                       device=args.device, verbose=False, save=False)[0]
                count = len(result.boxes)
                preview = result.plot()
                if snapshots is not None:
                    snapshots.consider(frame, result, count)
                text = f'Persons: {count} | No masking | NO DB SAVE'
                if time.monotonic() - last_log >= 2 or frames == 0:
                    logging.info('Inference OK: persons=%d (not saved)', count)
                    last_log = time.monotonic()
            cv2.rectangle(preview, (0, 0), (preview.shape[1], 42), (25, 25, 25), -1)
            cv2.putText(preview, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
            frames += 1
            if not args.headless:
                cv2.imshow(window, preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q'), ord('Q')) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
            if args.max_frames and frames >= args.max_frames:
                break
            ok, frame = capture.read()
            if not ok or frame is None or not frame.size:
                logging.error('Frame read failed; not treated as zero persons. Stopping without saving.')
                return 1
        logging.info('Preview finished: %d frames. No DB writes. Snapshot images: %d', frames, snapshots.saved if snapshots else 0)
        return 0
    finally:
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        sys.exit(run(parse_args()))
    except KeyboardInterrupt:
        logging.info('Stopped by Ctrl+C. Nothing saved to DB.')
    except Exception as exc:
        logging.error('Preview failed (%s). No zero-count fallback or DB write.', type(exc).__name__)
        sys.exit(1)
