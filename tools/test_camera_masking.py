import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import numpy as np

from tools.camera_masking import apply_mask, load_mask, select_mask, ComparisonEvidence, comparison_image
import tools.test_camera_preview as previous_tests
from tools.camera_preview import run, parse_args


class MaskTests(unittest.TestCase):
    def test_demo_image_reads_unicode_path_without_camera_or_db(self):
        import cv2
        with TemporaryDirectory() as directory:
            path = Path(directory) / '確認画像.png'
            frame = np.full((100, 160, 3), 123, dtype=np.uint8)
            ok, encoded = cv2.imencode('.png', frame)
            self.assertTrue(ok)
            encoded.tofile(path)
            args = previous_tests.CameraPreviewTests().args(image=path, max_frames=0)
            with patch('cv2.VideoCapture') as camera, patch('tools.db_recording.CrowdRecorder') as writer:
                self.assertEqual(run(args), 0)
                camera.assert_not_called()
                writer.assert_not_called()
                args.save_db = True
                with self.assertRaises(ValueError):
                    run(args)
                writer.assert_not_called()

    def test_user_selected_coordinates_saved_without_overwriting(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'mask.json'
            frame = np.full((100, 160, 3), 123, dtype=np.uint8)
            with patch('cv2.namedWindow'), patch('cv2.selectROIs', return_value=np.array([[5, 10, 20, 30]])), \
                 patch('cv2.destroyWindow'), patch('cv2.imshow'), \
                 patch('cv2.getWindowProperty', return_value=1), patch('cv2.waitKey', return_value=ord('s')):
                self.assertTrue(select_mask(frame, path))
                with self.assertRaises(FileExistsError):
                    select_mask(frame, path)
            self.assertEqual(load_mask(path, frame.shape)['rectangles'], [[5, 10, 20, 30]])

    def test_no_config_preserves_pixels_and_original(self):
        frame = np.full((10, 20, 3), 123, dtype=np.uint8)
        masked = apply_mask(frame, load_mask(None, frame.shape))
        np.testing.assert_array_equal(frame, masked)
        self.assertIsNot(frame, masked)

    def test_only_selected_rectangle_is_black(self):
        frame = np.full((10, 20, 3), 123, dtype=np.uint8)
        mask = {'width': 20, 'height': 10, 'rectangles': [[2, 3, 4, 5]]}
        actual = apply_mask(frame, mask)
        expected = frame.copy()
        expected[3:8, 2:6] = 0
        np.testing.assert_array_equal(actual, expected)
        self.assertTrue(np.all(frame == 123))
        with self.assertRaises(ValueError):
            apply_mask(np.zeros((11, 20, 3)), mask)

    def test_invalid_configs_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'mask.json'
            for config in [{'width': 21, 'height': 10, 'rectangles': []},
                           {'width': 20, 'height': 10, 'rectangles': [[19, 0, 2, 2]]},
                           {'width': 20, 'height': 10, 'rectangles': [[0, 0, 0, 2]]},
                           {'width': 20, 'height': 10, 'rectangles': [[True, 0, 2, 2]]}]:
                path.write_text(json.dumps(config), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_mask(path, (10, 20, 3))

    def test_compare_rejects_db_before_writer_or_camera(self):
        args = previous_tests.CameraPreviewTests().args(compare_mask=True, save_db=True, location_id=1)
        with patch('tools.db_recording.CrowdRecorder') as writer, patch('cv2.VideoCapture') as capture:
            with self.assertRaises(ValueError):
                run(args)
            writer.assert_not_called()
            capture.assert_not_called()
        with patch('sys.argv', ['preview', '--compare-mask', '--mask-config', 'mask.json', '--save-db', '--location-id', '1']):
            with self.assertRaises(SystemExit):
                parse_args()

    @patch('cv2.VideoCapture')
    def test_same_frame_comparison_and_evidence_limit(self, capture_factory):
        with TemporaryDirectory() as directory:
            frame = np.full((100, 160, 3), 123, dtype=np.uint8)
            config = {'width': 160, 'height': 100, 'rectangles': [[5, 10, 20, 30]]}
            path = Path(directory) / 'mask.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            args = previous_tests.CameraPreviewTests().args(capture_only=False, compare_mask=True,
                    mask_config=path, output_dir=Path(directory), max_frames=3, max_images=1)
            capture_factory.return_value.isOpened.return_value = True
            capture_factory.return_value.read.return_value = (True, frame)
            model = MagicMock()
            model.names = {0: 'person'}
            result = MagicMock()
            result.boxes.__len__.return_value = 1
            result.boxes.xyxy.cpu.return_value.tolist.return_value = [[1, 2, 3, 4]]
            result.boxes.conf.cpu.return_value.tolist.return_value = [0.8]
            result.plot.return_value = frame.copy()
            model.predict.return_value = [result]
            with patch('ultralytics.YOLO', return_value=model), patch('tools.db_recording.CrowdRecorder') as writer:
                self.assertEqual(run(args), 0)
                writer.assert_not_called()
            self.assertEqual(model.predict.call_count, 6)
            for before, after in zip(model.predict.call_args_list[::2], model.predict.call_args_list[1::2]):
                np.testing.assert_array_equal(before.args[0], frame)
                np.testing.assert_array_equal(after.args[0], apply_mask(frame, config))
                self.assertEqual(before.kwargs, after.kwargs)
            self.assertTrue(np.all(frame == 123))
            images = list(Path(directory).glob('mask-comparison-*/*.jpg'))
            self.assertEqual(len(images), 1)
            metadata = json.loads(images[0].with_suffix('.json').read_text(encoding='utf-8'))
            self.assertFalse(metadata['db_saved'])
            self.assertEqual(metadata['mask'], config)

    def test_evidence_stops_at_limit_when_counts_change(self):
        with TemporaryDirectory() as directory:
            args = previous_tests.CameraPreviewTests().args(output_dir=Path(directory), max_images=2)
            frame = np.zeros((100, 160, 3), dtype=np.uint8)
            result = MagicMock()
            result.plot.return_value = frame
            result.boxes.xyxy.cpu.return_value.tolist.return_value = []
            result.boxes.conf.cpu.return_value.tolist.return_value = []
            saver = ComparisonEvidence(args, load_mask(None, frame.shape))
            for count in (6, 7, 10, 3):
                result.boxes.__len__.return_value = count
                saver.consider(frame, result, result, comparison_image(result, result), datetime.now(timezone.utc))
            self.assertEqual(saver.saved, 2)
            self.assertEqual(len(list(saver.directory.glob('*.jpg'))), 2)


if __name__ == '__main__':
    unittest.main()

