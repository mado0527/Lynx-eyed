from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from .models import CrowdLog, LocationMaster


class AsyncPageTests(TestCase):
    def setUp(self):
        self.location = LocationMaster.objects.create(name='232', capacity=41)
        self.zone = ZoneInfo('Asia/Tokyo')
        clock = patch('crowd_app.views.timezone.now',
                      return_value=datetime(2026, 11, 13, 17, tzinfo=self.zone))
        clock.start()
        self.addCleanup(clock.stop)

    def test_dynamic_pages_keep_server_values_without_full_page_refresh(self):
        for path, fragment in (('/', 'home-occupancy'),
                               ('/prediction-graph/', 'prediction-chart')):
            response = self.client.get(path, {'location': self.location.pk},
                                       HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertContains(response, f'data-live-fragment="{fragment}"')
            self.assertContains(response, 'data-live-interval="5"')
            self.assertContains(response, '/static/crowd_app/page-live.js')
            self.assertNotContains(response, 'http-equiv="refresh"')
            self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(CrowdLog.objects.count(), 0)

    def test_updated_measurement_includes_zero_and_reading_never_writes(self):
        missing = self.client.get('/', {'location': self.location.pk})
        self.assertIsNone(missing.context['latest'])
        row = CrowdLog.objects.create(location=self.location, source='camera', user_count=0,
            recorded_at=datetime(2026, 11, 13, 16, tzinfo=self.zone))
        before = list(CrowdLog.objects.values())
        home = self.client.get('/', {'location': self.location.pk},
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(home.context['latest'].pk, row.pk)
        self.assertEqual(home.context['occupancy'], 0)
        prediction = self.client.get('/prediction-graph/', {'location': self.location.pk},
                                     HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        actual = next(value for value in prediction.context['hourly_actuals']
                      if value.recorded_at.hour == 16)
        self.assertEqual(actual.source, 'camera')
        self.assertEqual(actual.user_count, 0)
        self.assertEqual(list(CrowdLog.objects.values()), before)

    def test_preview_is_static_and_legacy_home_interval_is_preserved(self):
        preview = self.client.get('/prediction-graph/',
            {'location': self.location.pk, 'preview_date': '2026-11-10'})
        self.assertContains(preview, 'data-live-interval="0"')
        realtime = self.client.get('/', {'location': self.location.pk, 'realtime': '1'})
        self.assertContains(realtime, 'data-live-interval="2"')
        self.assertNotContains(realtime, 'http-equiv="refresh"')
