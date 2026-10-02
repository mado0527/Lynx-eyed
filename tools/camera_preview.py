"""Camera preview; DB writes require --save-db and an explicit --location-id."""
import argparse
import logging
import os
from pathlib import Path
import sys
import time
import json
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / '.camera-runtime' / 'config'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('YOLO_CONFIG_DIR', str(CONFIG_DIR))


def parse_args():
    parser = argparse.ArgumentParser(description='OpenCV / YOLO11n preview. No masking; DB save is opt-in.')
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
    parser.add_argument('--save-db', action='store_true', help='Explicitly enable MySQL recording')
    parser.add_argument('--location-id', type=int, help='Required DB destination when save-db is enabled')
    parser.add_argument('--interval', type=float, default=300, help='Measurement/save interval in seconds (DB mode)')
    parser.add_argument('--max-records', type=int, default=0, help='Stop after N DB records, 0 means continuous')
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--model', type=Path, default=ROOT / '.camera-runtime' / 'models' / 'yolo11n.pt')
    args = parser.parse_args()
    if args.interval <= 0 or args.max_records < 0:
        parser.error('interval must be positive; max-records must be nonnegative')
    if args.save_db and (args.location_id is None or args.location_id <= 0 or args.capture_only):
        parser.error('--save-db requires a positive --location-id and detection mode')
    if not args.save_db and args.max_records:
        parser.error('--max-records requires --save-db')
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
        status = 'DB ENABLED' if self.args.save_db else 'NO DB SAVE'
        cv2.putText(image, f'Persons: {count} | conf={self.args.conf} iou={self.args.iou} | {status}',
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
    recorder = None
    records = 0
    if args.save_db:
        sys.path.insert(0, str(ROOT))
        from tools.db_recording import CrowdRecorder
        recorder = CrowdRecorder(args.location_id)
        logging.info('DB enabled: location_id=%d name=%s interval=%ss (no masking)',
                     recorder.location.pk, recorder.location.name, args.interval)
    timeout_ms = int(args.timeout * 1000)
    logging.info('Opening input (no masking; DB writes %s)', 'enabled' if recorder else 'disabled')
    capture = cv2.VideoCapture(args.source, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms,
    ])
    status = 'DB ENABLED' if recorder else 'NO DB SAVE'
    window = f'Lynx-eyed | Person preview | {status} | Q / Esc to stop'
    try:
        if not capture.isOpened():
            logging.error('Input open failed. No count produced; nothing saved.')
            return 1
        ok, frame = capture.read()
        if not ok or frame is None or not frame.size:
            logging.error('First frame acquisition failed. Nothing saved.')
            return 1
        logging.info('Frame acquired: %dx%d', frame.shape[1], frame.shape[0])
        measured_at = datetime.now(timezone.utc)
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
        next_measurement = 0
        count = None
        while True:
            if model is None:
                preview = frame.copy()
                text = 'Capture OK | No masking | NO DB SAVE'
            elif recorder is None or time.monotonic() >= next_measurement:
                result = model.predict(frame, classes=[0], conf=args.conf, iou=args.iou, imgsz=args.imgsz,
                                       device=args.device, verbose=False, save=False)[0]
                count = len(result.boxes)
                if recorder is not None:
                    saved = recorder.save(count, measured_at)
                    records += 1
                    logging.info('DB saved: log_id=%d location_id=%d people=%d rate=%s measured_at=%s',
                                 saved.pk, saved.location_id, count, saved.crowd_rate,
                                 saved.recorded_at.isoformat())
                    next_measurement = time.monotonic() + args.interval
                preview = result.plot()
                if snapshots is not None:
                    snapshots.consider(frame, result, count)
                text = f'Persons: {count} | No masking | {status}'
                if time.monotonic() - last_log >= 2 or frames == 0:
                    logging.info('Inference OK: persons=%d (%s)', count, 'DB saved' if recorder else 'not saved')
                    last_log = time.monotonic()
            else:
                preview = frame.copy()
                text = f'Last measured: {count} | Waiting for next measurement | {status}'
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
            if args.max_records and records >= args.max_records:
                break
            ok, frame = capture.read()
            if not ok or frame is None or not frame.size:
                logging.error('Frame read failed; not treated as zero persons. Stopping without saving.')
                return 1
            measured_at = datetime.now(timezone.utc)
        logging.info('Preview finished: %d frames; DB records=%d; snapshot images=%d', frames, records, snapshots.saved if snapshots else 0)
        return 0
    finally:
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        args = parse_args()
        if args.save_db:
            log_dir = ROOT / '.camera-runtime' / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / ('recording-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.log')
            handler = logging.FileHandler(log_path, encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logging.getLogger().addHandler(handler)
            logging.info('Local recording log: %s', log_path)
        sys.exit(run(args))
    except KeyboardInterrupt:
        logging.info('Stopped by Ctrl+C. Previously saved records are retained.')
    except Exception as exc:
        logging.error('Process failed (%s). No zero-count fallback; no further records saved.', type(exc).__name__)
        sys.exit(1)
