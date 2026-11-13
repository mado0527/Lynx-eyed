from datetime import datetime, timezone as datetime_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from .models import CrowdLog, CrowdPrediction, LocationMaster


class PredictionPreviewTests(TestCase):
    def setUp(self):
        self.location = LocationMaster.objects.create(name='試用検証', capacity=41)
        self.zone = ZoneInfo('Asia/Tokyo')
        now = datetime(2026, 11, 11, 3, tzinfo=datetime_timezone.utc)
        clock = patch('crowd_app.views.timezone.now', return_value=now)
        clock.start()
        self.addCleanup(clock.stop)

    def record(self, count, day=10, hour=9, minute=0, source='dummy', location=None):
        return CrowdLog.objects.create(location=location or self.location, user_count=count,
            source=source, recorded_at=datetime(2026, 11, day, hour, minute, tzinfo=self.zone))

    def preview(self, day='2026-11-10'):
        return self.client.get('/prediction-graph/', {'location': self.location.pk, 'preview_date': day})

    def test_preview_uses_saved_dummy_only_in_hours_without_camera_and_never_writes(self):
        for hour, count in ((9, 24), (10, 26), (11, 99), (12, 4)):
            self.record(count, hour=hour)
        self.record(0, hour=11, minute=30, source='camera')
        self.record(99, hour=11, minute=30)  # Larger dummy ID cannot override measured zero.
        self.record(20, hour=13, source='camera')
        self.record(24, hour=13, minute=30, source='camera')
        self.record(99, hour=14, source='unknown')
        self.record(99, day=11)
        other = LocationMaster.objects.create(name='対象外', capacity=41)
        self.record(99, hour=14, location=other)
        for hour in range(9, 14):
            self.record(20, day=3, hour=hour, source='camera')
        before = list(CrowdLog.objects.order_by('pk').values())
        predictions_before = list(CrowdPrediction.objects.order_by('pk').values())
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_preview'])
        self.assertTrue(response.context['has_dummy_actuals'])
        hourly = response.context['hourly_actuals']
        self.assertEqual([row.user_count for row in hourly], [24, 26, 0, 4, 22])
        self.assertEqual([row.source for row in hourly], ['dummy', 'dummy', 'camera', 'dummy', 'camera'])
        self.assertEqual(response.context['display_record_count'], 6)
        self.assertEqual(response.context['camera_sample_count'], 0)
        self.assertTrue(all(row.camera_sample_count == 0 for row in response.context['day_predictions']))
        self.assertContains(response, '試用表示：2026/11/10')
        self.assertContains(response, '計測値（テスト含む・時間帯平均）')
        self.assertContains(response, 'テスト平均：24.0人')
        self.assertContains(response, '実測平均：0.0人')
        self.assertNotContains(response, '本日の')
        self.assertNotContains(response, 'http-equiv="refresh"')
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)
        self.assertEqual(list(CrowdPrediction.objects.order_by('pk').values()), predictions_before)

    def test_normal_screen_uses_temporary_values_without_writing_saved_dummy(self):
        self.record(25, day=11)
        before = list(CrowdLog.objects.values())
        response = self.client.get('/prediction-graph/', {'location': self.location.pk})
        self.assertFalse(response.context['is_preview'])
        self.assertTrue(response.context['has_dummy_actuals'])
        self.assertEqual([row.user_count for row in response.context['hourly_actuals']], [6, 10, 16, 31])
        self.assertTrue(all(point['at'] <= response.context['now'] for point in response.context['actual_points']))
        self.assertContains(response, 'テストデータ')
        self.assertEqual(list(CrowdLog.objects.values()), before)

    def test_temporary_values_do_not_override_camera_zero(self):
        self.record(0, day=11, hour=10, source='camera')
        response = self.client.get('/prediction-graph/', {'location': self.location.pk})
        hourly = {row.recorded_at.hour: row for row in response.context['hourly_actuals']}
        self.assertEqual(hourly[10].source, 'camera')
        self.assertEqual(hourly[10].user_count, 0)
        self.assertEqual(hourly[9].source, 'dummy')

    def test_invalid_or_future_preview_falls_back_to_today_with_notice(self):
        for value in ('invalid', '2026-11-31', '20261110', '2026-11-11', '2026-11-12', ''):
            with self.subTest(value=value):
                response = self.preview(value)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['invalid_preview'])
                self.assertFalse(response.context['is_preview'])
                self.assertEqual(response.context['today'].isoformat(), '2026-11-11')
                self.assertContains(response, '試用表示の日付が無効です')

    def test_empty_preview_is_not_invented_or_replaced_with_another_date(self):
        self.record(25)
        response = self.preview('2026-11-02')
        self.assertTrue(response.context['is_preview'])
        self.assertEqual(response.context['actual_points'], [])
        self.assertEqual(response.context['forecast_points'], [])
        self.assertContains(response, '対象期間のデータが存在しません')
