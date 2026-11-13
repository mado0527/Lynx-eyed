from datetime import date, datetime, time, timezone as datetime_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.template.loader import render_to_string

from .models import CrowdLog, LocationMaster
from .weekly_tendencies import SCHOOL_PERIODS, weekday_time_grid, selected_tendency
from unittest.mock import patch


class WeekdayTimeGridTests(TestCase):
    def setUp(self):
        self.location = LocationMaster.objects.create(name='時間帯検証', capacity=100)
        self.zone = ZoneInfo('Asia/Tokyo')
        self.now = datetime(2026, 11, 10, 10, 30, tzinfo=self.zone)
        # Deliberately test-only slots, independent of the school's timetable.
        self.periods = [('前半', time(9), time(10)), ('後半', time(10), time(11))]

    def record(self, count, day=9, hour=9, minute=0, source='camera', location=None):
        return CrowdLog.objects.create(location=location or self.location, user_count=count,
            recorded_at=datetime(2026, 11, day, hour, minute, tzinfo=self.zone), source=source)

    def grid(self):
        return weekday_time_grid(self.location, date(2026, 11, 2), date(2026, 11, 10),
                                 self.now, self.periods)

    def test_each_day_has_equal_weight_despite_different_sampling_frequency(self):
        for minute in range(10):
            self.record(0, day=2, minute=minute)
        self.record(20, day=9)
        result = self.grid()
        monday = result['time_rows'][0]['cells'][0]
        self.assertEqual(monday['average'], Decimal('10.0'))
        self.assertEqual(monday['observed_days'], 2)
        self.assertEqual(monday['samples'], 11)
        self.assertEqual(result['observed_days'], 2)

    def test_zero_missing_provenance_and_no_writes(self):
        self.record(0, source='dummy')
        self.record(10, hour=10, source='unknown')
        before = list(CrowdLog.objects.order_by('pk').values())
        result = self.grid()
        zero = result['time_rows'][0]['cells'][0]
        missing = result['time_rows'][0]['cells'][1]
        self.assertTrue(zero['measured'])
        self.assertEqual(zero['average'], Decimal('0.0'))
        self.assertEqual(zero['state'], 'low')
        self.assertFalse(missing['measured'])
        self.assertIsNone(missing['average'])
        self.assertEqual(missing['state'], 'unknown')
        self.assertTrue(zero['contains_dummy'])
        self.assertTrue(result['time_rows'][1]['cells'][0]['contains_unknown'])
        self.assertTrue(result['contains_dummy'])
        self.assertTrue(result['contains_unknown'])
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)

    def test_boundaries_weekends_future_location_and_duplicate_timestamp(self):
        self.record(99, hour=8, minute=59)
        self.record(4, hour=9)
        self.record(8, hour=9)  # Same timestamp: the largest ID wins.
        self.record(10, hour=10)
        self.record(99, hour=11)
        self.record(99, day=1)  # Before the requested period.
        self.record(99, day=7)  # Saturday.
        self.record(99, day=8)  # Sunday.
        self.record(12, day=10, hour=10, minute=30)  # Exactly now is valid.
        self.record(99, day=10, hour=10, minute=31)
        self.record(99, day=11)
        other = LocationMaster.objects.create(name='別の場所', capacity=100)
        self.record(99, minute=1, location=other)
        result = self.grid()
        self.assertEqual(result['samples'], 3)
        self.assertEqual(result['time_rows'][0]['cells'][0]['average'], Decimal('8.0'))
        self.assertEqual(result['time_rows'][1]['cells'][0]['average'], Decimal('10.0'))
        self.assertEqual(result['time_rows'][1]['cells'][1]['average'], Decimal('12.0'))

    def test_status_thresholds_match_top_and_invalid_capacity_is_neutral(self):
        for count, expected in ((30, 'low'), (31, 'moderate'), (75, 'moderate'), (76, 'high')):
            with self.subTest(count=count):
                self.record(count)
                self.assertEqual(self.grid()['time_rows'][0]['cells'][0]['state'], expected)
        self.location.capacity = 0
        cell = self.grid()['time_rows'][0]['cells'][0]
        self.assertTrue(cell['measured'])
        self.assertEqual(cell['average'], Decimal('76.0'))
        self.assertEqual(cell['state'], 'unknown')
        self.assertIsNone(cell['occupancy'])

    def test_round_half_up_and_japan_date_when_timestamp_is_utc(self):
        self.record(0, day=2)
        self.record(1, day=9)
        self.record(0, day=9, minute=1)
        self.assertEqual(self.grid()['time_rows'][0]['cells'][0]['average'], Decimal('0.3'))
        # UTC Sunday 23:59 is Monday 08:59 in Japan: first minute of this test slot.
        at = datetime(2026, 11, 8, 23, 59, tzinfo=datetime_timezone.utc)
        CrowdLog.objects.create(location=self.location, user_count=7, source='camera', recorded_at=at)
        result = weekday_time_grid(self.location, date(2026, 11, 9), date(2026, 11, 9),
            self.now, [('早朝', time(8, 59), time(9))])
        self.assertEqual(result['time_rows'][0]['cells'][0]['average'], Decimal('7.0'))
        self.assertEqual(result['samples'], 1)

    def test_no_location_is_all_missing(self):
        result = weekday_time_grid(None, date(2026, 11, 2), date(2026, 11, 10), self.now, self.periods)
        self.assertEqual(result['samples'], 0)
        self.assertTrue(all(not cell['measured'] for row in result['time_rows'] for cell in row['cells']))

    def test_school_period_boundaries_include_breaks_and_exclude_after_school(self):
        self.record(99, hour=9, minute=9)
        for count, (_, begins, _) in enumerate(SCHOOL_PERIODS, 1):
            self.record(count, hour=begins.hour, minute=begins.minute)
        self.record(99, hour=16, minute=30)
        result = weekday_time_grid(self.location, date(2026, 11, 2), date(2026, 11, 10),
                                   self.now, SCHOOL_PERIODS)
        self.assertEqual(result['samples'], 7)
        self.assertEqual([row['cells'][0]['average'] for row in result['time_rows']],
                         [Decimal(count) for count in range(1, 8)])
        self.assertEqual([(begins.strftime('%H:%M'), ends.strftime('%H:%M'))
            for _, begins, ends in SCHOOL_PERIODS], [
                ('09:10', '10:40'), ('10:40', '10:50'), ('10:50', '12:20'),
                ('12:20', '13:20'), ('13:20', '14:50'), ('14:50', '15:00'), ('15:00', '16:30'),
            ])

    def test_template_shows_counts_provenance_and_accessible_time_and_day_headers(self):
        self.record(0, source='dummy')
        result = self.grid()
        html = render_to_string('crowd_app/weekly.html', {
            **result, 'selected_location': self.location,
            'start_date': date(2026, 11, 2), 'end_date': date(2026, 11, 10),
        })
        self.assertIn('時間帯別の混雑傾向', html)
        self.assertIn('name="weekday"', html)
        self.assertIn('name="slot"', html)
        self.assertNotIn('name="grade"', html)
        self.assertIn('id="average-count"', html)
        self.assertIn('混雑率', html)
        self.assertIn('未計測', html)
        self.assertIn('<details id="aggregation-details">', html)
        self.assertNotIn('id="trend-chart"', html)
        self.assertNotIn('<table', html)

    def test_selected_trend_preserves_zero_gaps_and_equal_day_weighting(self):
        self.record(0, day=2, minute=0, source='dummy')
        self.record(10, day=9, minute=0)
        self.record(20, day=9, minute=1)
        self.record(8, day=9, minute=10)
        before = list(CrowdLog.objects.values())
        data = selected_tendency(self.location, date(2026, 11, 2), date(2026, 11, 10),
                                 self.now, self.periods, 1, 0)
        self.assertEqual(data['points'][0]['average'], Decimal('7.5'))
        self.assertIsNone(data['points'][1]['average'])
        self.assertEqual(data['points'][2]['average'], Decimal('8.0'))
        self.assertEqual(data['observed_days'], 2)
        self.assertEqual(data['samples'], 4)
        self.assertTrue(data['contains_dummy'])
        self.assertEqual(list(CrowdLog.objects.values()), before)

    def test_async_response_and_invalid_selection(self):
        self.record(0, day=9, hour=9, minute=10)
        with patch('crowd_app.views.timezone.now', return_value=self.now):
            response = self.client.get('/weekly-graph/', {'format': 'json', 'weekday': '1',
                'slot': '0', 'location': self.location.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['capacity'], 100)
            result = response.json()['result']
            self.assertEqual(result['average'], '0.0')
            self.assertEqual(result['occupancy'], '0.0')
            self.assertEqual(result['start'], '09:10')
            for params in ({'weekday': '6'}, {'slot': '-1'}, {'slot': 'bad'}):
                self.assertEqual(self.client.get('/weekly-graph/', {'format': 'json', **params}).status_code, 400)
            missing = self.client.get('/weekly-graph/', {'format': 'json', 'weekday': '5'}).json()['result']
            self.assertIsNone(missing['average'])
            self.assertIsNone(missing['occupancy'])
