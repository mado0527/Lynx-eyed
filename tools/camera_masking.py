"""Pixel-coordinate exclusion masks and local comparison evidence; no DB access."""
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def load_mask(path, shape):
    height, width = shape[:2]
    if path is None:
        return {'width': width, 'height': height, 'rectangles': []}
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(config, dict):
        raise ValueError('Mask configuration must be a JSON object')
    if config.get('width') != width or config.get('height') != height:
        raise ValueError('Mask resolution differs from input; select regions again for this resolution')
    rectangles = config.get('rectangles')
    if not isinstance(rectangles, list):
        raise ValueError('rectangles must be a list of [x, y, width, height]')
    for rect in rectangles:
        if not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect):
            raise ValueError('Mask coordinates must be four integers')
        x, y, w, h = rect
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise ValueError('Mask rectangle is outside the input frame')
    return config


def apply_mask(frame, config):
    if frame.shape[1] != config['width'] or frame.shape[0] != config['height']:
        raise ValueError('Input resolution changed; stopping rather than applying incorrect coordinates')
    masked = frame.copy()
    for x, y, w, h in config['rectangles']:
        masked[y:y+h, x:x+w] = 0
    return masked


def select_mask(frame, path, confirm_in_terminal=False):
    import cv2
    path = Path(path)
    if path.exists():
        raise FileExistsError('Mask file already exists; choose a new filename to preserve it')
    title = 'Select exclusion rectangles: drag, Enter/Space next, Esc finish'
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    rectangles = cv2.selectROIs(title, frame, showCrosshair=True, fromCenter=False)
    logging.info('ROI selection finished: %d rectangles. Opening confirmation; click that window and press S to save.', len(rectangles))
    cv2.destroyWindow(title)
    config = {'width': frame.shape[1], 'height': frame.shape[0],
              'rectangles': [[int(v) for v in rect] for rect in rectangles]}
    preview = apply_mask(frame, config)
    title = 'Mask confirmation: S save / Esc cancel (NO DB SAVE)'
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.imshow(title, preview)
    if confirm_in_terminal:
        cv2.waitKey(100)  # Paint the confirmation image before waiting on stdin.
        answer = input('Return to PowerShell. Save these mask regions? Type SAVE then Enter (anything else cancels): ')
        if answer.strip().upper() != 'SAVE':
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as output:
            json.dump(config, output, indent=2)
        logging.info('Mask file created and verified: %s (%d bytes)', path.resolve(), path.stat().st_size)
        return True
    # HighGUI needs waitKey to process creation/paint events before visibility checks.
    # Checking visibility immediately after imshow can incorrectly cancel a new window.
    while True:
        key = cv2.waitKey(100) & 0xff
        if key in (ord('s'), ord('S')):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8') as output:
                json.dump(config, output, indent=2)
            return True
        if key in (27, ord('q'), ord('Q')):
            logging.info('Mask confirmation cancelled by key; configuration was not written.')
            break
        if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
            logging.info('Mask confirmation window closed; configuration was not written.')
            break
    return False


def comparison_image(before, after):
    import cv2
    import numpy as np
    panels = []
    for label, result in [('Before', before), ('Masked', after)]:
        panel = cv2.copyMakeBorder(result.plot(), 50, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25, 25, 25))
        cv2.putText(panel, f'{label}: {len(result.boxes)} persons | NO DB SAVE', (10, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        panels.append(panel)
    return np.concatenate(panels, axis=1)


class ComparisonEvidence:
    def __init__(self, args, config):
        self.args, self.config = args, config
        self.previous = None
        self.saved = 0
        self.directory = args.output_dir / ('mask-comparison-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])

    def consider(self, frame, before, after, image, measured_at):
        import cv2
        import numpy as np
        pair = (len(before.boxes), len(after.boxes))
        changed = pair != self.previous
        self.previous = pair
        if not changed or self.saved >= self.args.max_images:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = self.directory / f'{self.saved+1:03d}_before-{pair[0]}_masked-{pair[1]}'
        if not cv2.imwrite(str(stem.with_suffix('.jpg')), image):
            raise OSError('Comparison image write failed')
        np.savez_compressed(stem.with_suffix('.npz'), frame=frame)
        metadata = {'measured_at': measured_at.isoformat(), 'mask': self.config,
                    'conf': self.args.conf, 'iou': self.args.iou, 'imgsz': self.args.imgsz,
                    'model': str(self.args.model), 'db_saved': False, 'actual_count': None,
                    'notes': '', 'scope': '223 classroom, single camera; no multi-camera validation'}
        for label, result in [('before', before), ('masked', after)]:
            metadata[label] = {'count': len(result.boxes), 'boxes': result.boxes.xyxy.cpu().tolist(),
                               'scores': result.boxes.conf.cpu().tolist()}
        stem.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        self.saved += 1
