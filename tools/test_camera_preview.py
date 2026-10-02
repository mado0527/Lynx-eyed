import argparse
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from tools.camera_preview import run, ChangeSnapshots
from tempfile import TemporaryDirectory


class CameraPreviewTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(source='test-input', timeout=1, capture_only=True,
                      headless=True, max_frames=1, model=Path(__file__),
                      conf=0.25, iou=0.7, imgsz=640, device='cpu', save_changes=False,
                      max_images=2, output_dir=Path('.camera-runtime/test'))
        return argparse.Namespace(**(values | changes))

    @patch('cv2.VideoCapture')
    def test_open_failure_is_error_and_releases_capture(self, factory):
        capture = factory.return_value
        capture.isOpened.return_value = False
        with self.assertLogs(level='ERROR') as logs:
            self.assertEqual(run(self.args()), 1)
        self.assertIn('nothing saved', logs.output[0])
        capture.read.assert_not_called()
        capture.release.assert_called_once()

    @patch('cv2.VideoCapture')
    def test_read_failure_is_not_counted_as_zero(self, factory):
        capture = factory.return_value
        capture.isOpened.return_value = True
        capture.read.return_value = (False, None)
        with patch('ultralytics.YOLO') as model, self.assertLogs(level='ERROR'):
            self.assertEqual(run(self.args(capture_only=False)), 1)
        model.assert_not_called()
        capture.release.assert_called_once()

    @patch('cv2.VideoCapture')
    def test_inference_only_requests_person_and_does_not_save(self, factory):
        frame = np.zeros((100, 160, 3), dtype=np.uint8)
        capture = factory.return_value
        capture.isOpened.return_value = True
        capture.read.return_value = (True, frame)
        model = MagicMock()
        model.names = {0: 'person', 1: 'bicycle'}
        result = MagicMock()
        result.boxes = [object(), object()]
        result.plot.return_value = frame.copy()
        model.predict.return_value = [result]
        with patch('ultralytics.YOLO', return_value=model), self.assertLogs(level='INFO') as logs:
            self.assertEqual(run(self.args(capture_only=False)), 0)
        self.assertEqual(model.predict.call_args.kwargs['classes'], [0])
        self.assertFalse(model.predict.call_args.kwargs['save'])
        self.assertEqual(model.predict.call_args.kwargs['iou'], 0.7)
        self.assertTrue(any('persons=2 (not saved)' in line for line in logs.output))
        capture.release.assert_called_once()

    def test_change_snapshots_initial_change_and_limit(self):
        test_root = Path('.camera-runtime/test')
        test_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=test_root.resolve()) as directory:
            saver = ChangeSnapshots(self.args(output_dir=Path(directory)))
            frame = np.zeros((80, 120, 3), dtype=np.uint8)
            result = MagicMock()
            result.plot.return_value = frame.copy()
            result.boxes.xyxy.cpu.return_value.tolist.return_value = []
            result.boxes.conf.cpu.return_value.tolist.return_value = []
            for count in (6, 6, 7, 6, 7):
                saver.consider(frame, result, count)
            self.assertEqual(saver.saved, 2)
            self.assertEqual(len(list(saver.directory.glob('*.jpg'))), 2)
            self.assertEqual(len(list(saver.directory.glob('*.npz'))), 2)
            self.assertTrue((saver.directory / '002_6-to-7.jpg').exists())


if __name__ == '__main__':
    unittest.main()
