from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal

from .models import CrowdLog, CrowdPrediction, LocationMaster
from unittest.mock import patch


class CrowdLogUserCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.location = LocationMaster.objects.create(name="検証用", capacity=1)
        cls.admin = get_user_model().objects.create_superuser(
            username="test_admin", password="test-only-password",
        )

    def create_log(self, count):
        return CrowdLog.objects.create(
            location=self.location, user_count=count,
            crowd_rate=0, recorded_at=timezone.now(),
        )

    def admin_data(self, count):
        return {
            "location": self.location.pk, "user_count": count, "crowd_rate": 0,
            "recorded_at_0": "2026-10-02", "recorded_at_1": "12:00:00",
            "_save": "保存",
        }

    def test_admin_rejects_negative_on_add_and_change(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:crowd_app_crowdlog_add"))
        self.assertContains(response, 'min="0"')
        self.assertContains(response, "0以上の人数を入力してください。")
        response = self.client.post(
            reverse("admin:crowd_app_crowdlog_add"), self.admin_data(-1),
        )
        self.assertContains(response, "利用者人数は0以上で入力してください。")
        self.assertFalse(CrowdLog.objects.exists())
        log = self.create_log(0)
        response = self.client.post(
            reverse("admin:crowd_app_crowdlog_change", args=[log.pk]),
            self.admin_data(-1),
        )
        self.assertContains(response, "利用者人数は0以上で入力してください。")
        log.refresh_from_db()
        self.assertEqual(log.user_count, 0)

    def test_admin_accepts_zero_and_positive_above_capacity(self):
        self.client.force_login(self.admin)
        for count in (0, 2):
            with self.subTest(count=count):
                response = self.client.post(
                    reverse("admin:crowd_app_crowdlog_add"), self.admin_data(count),
                )
                self.assertEqual(response.status_code, 302)
                self.assertTrue(CrowdLog.objects.filter(user_count=count).exists())

    def test_database_rejects_negative_create_and_update(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_log(-1)
        log = self.create_log(0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CrowdLog.objects.filter(pk=log.pk).update(user_count=-1)
        log.refresh_from_db()
        self.assertEqual(log.user_count, 0)

    def test_database_accepts_zero_and_positive_above_capacity(self):
        for count in (0, 2):
            with self.subTest(count=count):
                log = self.create_log(count)
                log.refresh_from_db()
                self.assertEqual(log.user_count, count)


class HomeTests(TestCase):
    def make_location(self, capacity=40, name="ラウンジ"):
        return LocationMaster.objects.create(name=name, capacity=capacity)

    def record(self, location, count, at=None):
        return CrowdLog.objects.create(
            location=location, user_count=count, crowd_rate=99,
            recorded_at=at or timezone.now(),
        )

    def test_no_locations(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, '場所が未登録です')
        self.assertContains(response, '未計測')
        self.assertContains(response, 'href="/management/"')

    def test_unmeasured_is_distinct_from_zero(self):
        location = self.make_location()
        self.assertContains(self.client.get('/'), '未計測')
        self.record(location, 0)
        response = self.client.get('/')
        self.assertEqual(response.context['occupancy'], Decimal('0.0'))
        self.assertNotContains(response, '未計測')
        self.assertContains(response, '0人')

    def test_latest_record_tie_break_calculation_and_japan_time(self):
        location = self.make_location()
        at = datetime(2026, 10, 2, 1, 2, 3, tzinfo=datetime_timezone.utc)
        self.record(location, 8, at)
        latest = self.record(location, 12, at)
        self.record(location, 1, at.replace(day=1))
        response = self.client.get('/')
        self.assertEqual(response.context['latest'], latest)
        self.assertEqual(response.context['occupancy'], Decimal('30.0'))
        self.assertEqual(response.context['latest'].recorded_at, at)
        self.assertContains(response, '最終集計日時')
        self.assertContains(response, '>2026/10/02 10:02:03</time>（日本時間）')
        latest.refresh_from_db()
        self.assertEqual(latest.crowd_rate, 30)

    def test_location_selection_and_invalid_parameters(self):
        first = self.make_location()
        second = self.make_location(name='別の場所')
        self.record(second, 2)
        response = self.client.get('/', {'location': second.pk})
        self.assertEqual(response.context['selected_location'], second)
        self.assertContains(response, 'name="location"')
        for value in ('invalid', '-1', '999999999999999999999999', ''):
            response = self.client.get('/', {'location': value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['selected_location'], first)
            self.assertTrue(response.context['invalid_location'])

    def test_nonpositive_capacity(self):
        for capacity in (0, -1):
            location = self.make_location(capacity=capacity)
            self.record(location, 2)
            response = self.client.get('/', {'location': location.pk})
            self.assertContains(response, '算出不可')
            self.assertIsNone(response.context['occupancy'])
            self.assertEqual(response.context['crowd_state'], 'unknown')
            self.assertNotContains(response, '空いています')

    def test_crowd_status_thresholds_zero_and_over_capacity(self):
        for capacity, count, state, label in (
            (41, 0, 'low', '空いています'),
            (41, 12, 'low', '空いています'),
            (41, 13, 'moderate', 'やや混雑しています'),
            (41, 20, 'moderate', 'やや混雑しています'),
            (41, 21, 'moderate', 'やや混雑しています'),
            (41, 28, 'moderate', 'やや混雑しています'),
            (41, 29, 'moderate', 'やや混雑しています'),
            (41, 30, 'moderate', 'やや混雑しています'),
            (41, 31, 'high', '混雑しています'),
            (100, 29, 'low', '空いています'),
            (100, 30, 'low', '空いています'),
            (100, 31, 'moderate', 'やや混雑しています'),
            (100, 49, 'moderate', 'やや混雑しています'),
            (100, 50, 'moderate', 'やや混雑しています'),
            (100, 69, 'moderate', 'やや混雑しています'),
            (100, 70, 'moderate', 'やや混雑しています'),
            (100, 75, 'moderate', 'やや混雑しています'),
            (100, 76, 'high', '混雑しています'),
            (1000, 309, 'low', '空いています'),
            (1000, 310, 'moderate', 'やや混雑しています'),
            (1000, 750, 'moderate', 'やや混雑しています'),
            (1000, 751, 'high', '混雑しています'),
            (100, 120, 'high', '混雑しています'),
        ):
            with self.subTest(capacity=capacity, count=count):
                location = self.make_location(capacity=capacity)
                record = self.record(location, count)
                before = list(CrowdLog.objects.order_by('pk').values())
                response = self.client.get('/', {'location': location.pk})
                self.assertEqual(response.context['crowd_state'], state)
                self.assertEqual(response.context['crowd_label'], label)
                self.assertContains(response, 'crowd-state-' + state)
                self.assertContains(response, label)
                self.assertEqual(response.context['latest'], record)
                self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)

    def test_previous_day_record_is_neutral_and_keeps_measured_time(self):
        location = self.make_location()
        now = datetime(2026, 11, 10, 3, tzinfo=datetime_timezone.utc)
        record = self.record(location, 0, now - timedelta(days=1))
        with patch('crowd_app.views.timezone.now', return_value=now):
            response = self.client.get('/', {'location': location.pk})
        self.assertEqual(response.context['latest'], record)
        self.assertEqual(response.context['crowd_state'], 'unknown')
        self.assertTrue(response.context['is_previous_day'])
        self.assertContains(response, '本日は未計測')
        self.assertEqual(response.context['latest'].recorded_at, record.recorded_at)
        self.assertNotContains(response, '空いています')

    def test_unmeasured_status_and_dummy_notice_are_distinct(self):
        location = self.make_location()
        empty = self.client.get('/', {'location': location.pk})
        self.assertEqual(empty.context['crowd_state'], 'unknown')
        self.assertContains(empty, '未計測')
        self.assertNotContains(empty, '空いています')
        CrowdLog.objects.create(location=location, user_count=25,
                                recorded_at=timezone.now(), source='dummy')
        response = self.client.get('/', {'location': location.pk})
        self.assertContains(response, '表示中の人数はテストデータです。')
        self.assertContains(response, '最終集計日時')
        self.assertNotContains(response, '最終計測日時')
        self.assertNotContains(response, '前に計測')
        self.assertContains(response, '場所：ラウンジ')

    def test_refresh_reads_new_record_and_allows_over_capacity(self):
        location = self.make_location(capacity=10)
        self.record(location, 3)
        self.assertEqual(self.client.get('/').context['occupancy'], Decimal('30.0'))
        latest = self.record(location, 12)
        response = self.client.get('/', {'location': location.pk})
        self.assertEqual(response.context['latest'], latest)
        self.assertEqual(response.context['occupancy'], Decimal('120.0'))
        self.assertIn('no-store', response['Cache-Control'])

    def test_existing_admin_route(self):
        self.assertRedirects(self.client.get('/admin/'), '/admin/login/?next=/admin/')

    @patch('crowd_app.views.timezone.now', return_value=datetime(2026, 11, 10, 3, tzinfo=datetime_timezone.utc))
    def test_graph_order_selection_and_single_record(self, clock):
        location = self.make_location()
        other = self.make_location(name='別の場所')
        self.record(other, 99)
        at = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time())) + timedelta(hours=10)
        newer = self.record(location, 10, at)
        response = self.client.get('/')
        self.assertContains(response, 'class="trend-bar"', count=1)
        older = self.record(location, 3, at - timedelta(hours=1))
        response = self.client.get('/')
        self.assertEqual(response.context['history'], [older, newer])
        self.assertContains(response, 'class="trend-bar"', count=2)
        self.assertNotContains(response, '<polyline')
        self.assertContains(response, 'type="submit"', count=1)
        self.assertEqual(response.context['chart_points'][-1]['record'], newer)

    def test_graph_missing_and_latest_five_today_records(self):
        location = self.make_location()
        self.assertContains(self.client.get('/'), '対象期間のデータが存在しません')
        for count in range(21):
            self.record(location, count)
        response = self.client.get('/')
        self.assertEqual([row.user_count for row in response.context['history']], [16, 17, 18, 19, 20])
        self.assertContains(response, 'class="trend-bar"', count=5)
        self.assertEqual(response.context['latest'].user_count, 20)
        self.assertEqual(CrowdLog.objects.count(), 21)

    def test_latest_five_uses_measurement_time_and_id_and_excludes_future(self):
        location = self.make_location()
        other = self.make_location(name='別の場所')
        now = datetime(2026, 11, 10, 4, tzinfo=datetime_timezone.utc)
        at = now - timedelta(minutes=5)
        tied = [self.record(location, count, at) for count in range(6)]
        self.record(location, 99, now - timedelta(hours=1))
        self.record(location, 88, now + timedelta(minutes=5))
        self.record(other, 77, now - timedelta(minutes=1))
        before = list(CrowdLog.objects.order_by('pk').values())
        with patch('crowd_app.views.timezone.now', return_value=now):
            response = self.client.get('/', {'location': location.pk})
        self.assertEqual(response.context['history'], tied[1:])
        self.assertEqual(response.context['latest'], tied[-1])
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)

    def test_graph_filters_by_japan_day_boundaries_without_changing_records(self):
        location = self.make_location()
        other = self.make_location(name='別の場所')
        now = datetime(2026, 11, 6, 4, tzinfo=datetime_timezone.utc)
        start = datetime(2026, 11, 5, 15, tzinfo=datetime_timezone.utc)
        end = start + timedelta(days=1)
        self.record(location, 1, start - timedelta(microseconds=1))
        first = self.record(location, 2, start)
        second = self.record(location, 3, start)
        last = self.record(location, 4, end - timedelta(microseconds=1))
        self.record(location, 5, end)
        self.record(other, 6, start)
        before = list(CrowdLog.objects.order_by('pk').values())
        with patch('crowd_app.views.timezone.now', return_value=now):
            response = self.client.get('/', {'location': location.pk})
        self.assertEqual(response.context['history'], [first, second])
        self.assertContains(response, 'class="trend-bar"', count=2)
        self.assertContains(response, '本日・直近2件')
        with patch('crowd_app.views.timezone.now', return_value=end - timedelta(microseconds=1)):
            midnight_response = self.client.get('/', {'location': location.pk})
        self.assertEqual(midnight_response.context['history'], [first, second, last])
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)

    def test_yesterday_records_do_not_fill_today_graph(self):
        location = self.make_location()
        now = datetime(2026, 11, 6, 4, tzinfo=datetime_timezone.utc)
        yesterday = self.record(location, 8, now - timedelta(days=1))
        with patch('crowd_app.views.timezone.now', return_value=now):
            response = self.client.get('/')
        self.assertEqual(response.context['history'], [])
        self.assertContains(response, '対象期間のデータが存在しません')
        self.assertNotContains(response, 'class="trend-bar"')
        self.assertEqual(response.context['latest'], yesterday)

    def test_future_review_dummy_is_not_current_occupancy(self):
        location = self.make_location()
        latest = self.record(location, 3)
        CrowdLog.objects.create(location=location, user_count=14, source='dummy',
                                recorded_at=timezone.now() + timedelta(days=1))
        response = self.client.get('/')
        self.assertEqual(response.context['latest'], latest)
        self.assertEqual(response.context['occupancy'], Decimal('7.5'))


class AutomaticCrowdRateTests(TestCase):
    def setUp(self):
        self.location = LocationMaster.objects.create(name='自動計算', capacity=25)

    def record(self, count):
        return CrowdLog.objects.create(
            location=self.location, user_count=count, recorded_at=timezone.now(),
        )

    def test_create_zero_over_capacity_and_invalid_capacity(self):
        for count, expected in ((10, 40), (0, 0), (30, 120)):
            record = self.record(count)
            record.refresh_from_db()
            self.assertEqual(record.crowd_rate, expected)
        for capacity in (0, -1):
            self.location.capacity = capacity
            self.location.save()
            self.assertIsNone(self.record(10).crowd_rate)

    def test_updates_recalculate_but_capacity_change_preserves_history(self):
        record = self.record(10)
        self.location.capacity = 50
        self.location.save()
        record.refresh_from_db()
        self.assertEqual(record.crowd_rate, 40)
        record.save()
        record.refresh_from_db()
        self.assertEqual(record.crowd_rate, 40)
        self.assertEqual(self.client.get('/').context['occupancy'], Decimal('20.0'))
        record.user_count = 20
        record.save(update_fields=['user_count'])
        record.refresh_from_db()
        self.assertEqual(record.crowd_rate, 40)
        other = LocationMaster.objects.create(name='移動先', capacity=25)
        record.location = other
        record.save(update_fields=['location'])
        record.refresh_from_db()
        self.assertEqual(record.crowd_rate, 80)

    def test_legacy_values_are_not_rewritten_and_admin_needs_no_rate(self):
        record = self.record(10)
        # Simulate an existing manually entered value without invoking save().
        CrowdLog.objects.filter(pk=record.pk).update(crowd_rate=7)
        record.refresh_from_db()
        record.recorded_at = timezone.now()
        record.save(update_fields=['recorded_at'])
        record.refresh_from_db()
        self.assertEqual(record.crowd_rate, 7)
        self.assertEqual(self.client.get('/').context['occupancy'], Decimal('40.0'))
        from .admin import CrowdLogAdminForm
        form = CrowdLogAdminForm(data={
            'location': self.location.pk, 'user_count': 10,
            'recorded_at': timezone.now(),
        })
        self.assertNotIn('crowd_rate', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.crowd_rate, 40)


class MockupScreenTests(TestCase):
    def test_public_pages_and_navigation(self):
        for name in ('prediction', 'weekly', 'live', 'help'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            if name == 'prediction':
                self.assertContains(response, '予測データがありません')
            elif name != 'weekly':
                self.assertContains(response, '未実装')
            self.assertContains(response, 'name="viewport"')
        self.assertContains(self.client.get(reverse('prediction')), reverse('weekly'))
        self.assertNotContains(self.client.get(reverse('live')), '稼働中')
        self.assertContains(self.client.get('/'), reverse('prediction'))
        self.assertContains(self.client.get('/'), reverse('live'))
        self.assertContains(self.client.get('/'), 'type="submit"', count=1)

    def test_authentication_and_admin_templates(self):
        self.assertRedirects(self.client.get('/login/'), '/management/login/')
        response = self.client.get('/admin/login/')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'crowd_app/management.css')
        self.assertTemplateUsed(response, 'crowd_app/management_login.html')
        response = self.client.get(reverse('devices'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/admin/login/'))
        user = get_user_model().objects.create_superuser(username='design_admin', password='test-only-password')
        self.client.force_login(user)
        response = self.client.get('/admin/')
        self.assertContains(response, '管理者ダッシュボード')
        self.assertContains(response, reverse('admin:crowd_app_crowdlog_changelist'))
        self.assertEqual(self.client.get(reverse('devices')).status_code, 200)

    def test_staff_without_model_permissions_cannot_view_devices(self):
        user = get_user_model().objects.create_user(username='limited_staff', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('devices')).status_code, 403)


class WeeklyGraphTests(TestCase):
    def setUp(self):
        self.location = LocationMaster.objects.create(name='曜日検証', capacity=40)
        self.now = datetime(2026, 11, 10, 8, tzinfo=datetime_timezone.utc)  # Tuesday 17:00 JST
        self.today = timezone.localdate(self.now)
        clock = patch('crowd_app.views.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def record(self, count, day, location=None, minute=0):
        from datetime import time
        return CrowdLog.objects.create(location=location or self.location, user_count=count,
            recorded_at=timezone.make_aware(datetime.combine(day, time(12, minute))))

    def test_time_grid_uses_observations_and_preserves_saved_summaries(self):
        from .models import DayOfWeekSummaryLog
        month = timezone.make_aware(datetime.combine(self.today.replace(day=1), datetime.min.time()))
        DayOfWeekSummaryLog.objects.create(location=self.location, summary_month=month,
            day_of_week=1, avg_count=99, executed_at=self.now)
        self.record(12, self.today - timedelta(days=1))
        before = list(DayOfWeekSummaryLog.objects.values())
        response = self.client.get(reverse('weekly'))
        self.assertEqual(response.context['time_rows'][2]['cells'][0]['average'], Decimal('12.0'))
        self.assertContains(response, '時間帯別の混雑傾向')
        self.assertNotContains(response, '保存済み曜日別集計')
        self.assertEqual(list(DayOfWeekSummaryLog.objects.values()), before)

    def test_average_zero_missing_and_no_database_writes(self):
        self.record(0, self.today)
        self.record(10, self.today - timedelta(days=1))
        self.record(30, self.today - timedelta(days=1), minute=5)
        before = list(CrowdLog.objects.values())
        response = self.client.get(reverse('weekly'))
        cells = response.context['time_rows'][2]['cells']
        self.assertEqual(cells[1]['average'], Decimal('0.0'))
        self.assertEqual(cells[0]['average'], Decimal('20.0'))
        self.assertEqual(sum(cell['measured'] for cell in cells), 2)
        self.assertContains(response, '未計測')
        self.assertContains(response, 'id="average-count"')
        self.assertContains(response, '<details id="aggregation-details">')
        self.assertNotContains(response, '<table')
        data = self.client.get(reverse('weekly'), {'format': 'json'}).json()
        self.assertEqual(len(data['slots']), 7)
        self.assertIn('09:10〜10:40', data['slots'][0]['label'])
        self.assertContains(response, f'href="/prediction-graph/?location={self.location.pk}"')
        self.assertEqual(list(CrowdLog.objects.values()), before)

    def test_period_boundaries_and_location(self):
        self.record(10, self.today - timedelta(days=27))
        self.record(99, self.today - timedelta(days=28))
        self.record(99, self.today + timedelta(days=1))
        other = LocationMaster.objects.create(name='対象外', capacity=40)
        self.record(99, self.today, other)
        self.assertEqual(self.client.get(reverse('weekly')).context['samples'], 1)
        self.assertEqual(self.client.get(reverse('weekly'), {'period': 56}).context['samples'], 2)
        self.assertEqual(self.client.get(reverse('weekly'), {'location': other.pk}).context['samples'], 1)

    def test_japan_time_slot_and_invalid_parameters(self):
        # UTC 00:10 is 09:10 in Japan, the inclusive start of period 1.
        CrowdLog.objects.create(location=self.location, user_count=5,
            recorded_at=datetime(2026, 11, 9, 0, 10, tzinfo=datetime_timezone.utc))
        response = self.client.get(reverse('weekly'), {'location': 'bad', 'period': 'bad'})
        self.assertEqual(response.context['time_rows'][0]['cells'][0]['average'], Decimal('5.0'))
        self.assertTrue(response.context['invalid_period'])
        self.assertTrue(response.context['invalid_location'])

    def test_no_locations_and_no_measurements(self):
        response = self.client.get(reverse('weekly'))
        self.assertEqual(response.context['samples'], 0)
        self.assertContains(response, 'データなし')
        self.assertTrue(all(cell['average'] is None
            for row in response.context['time_rows'] for cell in row['cells']))
        self.location.delete()
        self.assertIsNone(self.client.get(reverse('weekly')).context['selected_location'])

    def test_days_are_equally_weighted_across_multiple_weeks(self):
        self.record(0, self.today - timedelta(days=8))
        self.record(20, self.today - timedelta(days=8), minute=5)
        self.record(20, self.today - timedelta(days=1))
        self.record(30, self.today)
        before = list(CrowdLog.objects.order_by('pk').values())
        response = self.client.get(reverse('weekly'), {'location': self.location.pk})
        cells = response.context['time_rows'][2]['cells']
        self.assertEqual((cells[0]['average'], cells[0]['observed_days']), (Decimal('15.0'), 2))
        self.assertEqual((cells[1]['average'], cells[1]['observed_days']), (Decimal('30.0'), 1))
        self.assertTrue(all(cell['average'] is None for cell in cells[2:]))
        self.assertEqual(response.context['samples'], 4)
        self.assertEqual(response.context['observed_days'], 3)
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)


class PredictionGraphTests(TestCase):
    def setUp(self):
        self.location = LocationMaster.objects.create(name='平均予測検証', capacity=40)
        self.other = LocationMaster.objects.create(name='対象外', capacity=40)
        self.now = datetime(2026, 11, 6, 3, tzinfo=datetime_timezone.utc)  # Friday 12:00 JST
        clock = patch('crowd_app.views.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def observe(self, count, days=7, hour=13, location=None):
        at = (self.now - timedelta(days=days)).replace(hour=hour - 9)
        return CrowdLog.objects.create(location=location or self.location,
                                       user_count=count, recorded_at=at)

    def camera(self, count, minutes=5, source='camera', location=None):
        return CrowdLog.objects.create(location=location or self.location, source=source,
            user_count=count, recorded_at=self.now - timedelta(minutes=minutes))

    def test_new_camera_readings_change_forecast_without_writes_on_view(self):
        self.observe(10, hour=11)
        self.observe(20, hour=13)
        baseline = self.client.get(reverse('prediction'))
        self.camera(5)
        first = self.client.get(reverse('prediction'))
        self.assertEqual(first.context['predictions'][0].expected_count, 15)
        self.assertEqual(first.context['camera_sample_count'], 1)
        self.assertNotEqual(first.context['forecast_path'], baseline.context['forecast_path'])
        self.camera(15, minutes=1)
        before = list(CrowdLog.objects.values())
        second = self.client.get(reverse('prediction'))
        self.assertEqual(second.context['predictions'][0].expected_count, 20)
        self.assertEqual(second.context['camera_sample_count'], 2)
        self.assertContains(second, 'カメラ実測2件で補正')
        self.assertNotContains(second, 'http-equiv="refresh"')
        self.assertContains(second, 'data-live-interval="5"')
        self.assertEqual(list(CrowdLog.objects.values()), before)

    def test_full_day_remains_visible_from_first_to_last_slot_after_close(self):
        for hour in range(9, 17):
            self.observe(20, hour=hour)
        response = self.client.get(reverse('prediction'))
        self.assertEqual([timezone.localtime(p.predicted_at).hour for p in response.context['day_predictions']],
                         list(range(9, 17)))
        self.assertEqual([timezone.localtime(p.predicted_at).hour for p in response.context['predictions']],
                         list(range(13, 17)))
        closed = self.now.replace(hour=9)  # 18:00 JST
        with patch('crowd_app.views.timezone.now', return_value=closed):
            evening = self.client.get(reverse('prediction'))
        self.assertEqual(len(evening.context['day_predictions']), 8)
        self.assertEqual(evening.context['predictions'], [])
        self.assertTrue(evening.context['forecast_path'])
        self.assertContains(evening, '比較用の過去平均')
        self.assertNotContains(evening, '対象期間のデータが存在しません')

    def test_past_comparison_is_not_adjusted_with_later_camera_data(self):
        self.observe(10, hour=11)
        self.observe(20, hour=13)
        self.camera(5)
        first = self.client.get(reverse('prediction'))
        self.assertEqual(first.context['day_predictions'][0].expected_count, 10)
        self.assertEqual(first.context['predictions'][0].expected_count, 15)
        self.camera(15, minutes=1)
        second = self.client.get(reverse('prediction'))
        self.assertEqual(second.context['day_predictions'][0].expected_count, 10)
        self.assertTrue(second.context['day_predictions'][0].is_past)
        self.assertEqual(second.context['day_predictions'][0].camera_sample_count, 0)
        self.assertEqual(second.context['predictions'][0].expected_count, 20)
        self.assertContains(second, '事前に保存した予測値ではありません')

    def test_actuals_use_only_today_camera_and_largest_id_at_same_time(self):
        zero = self.camera(0, minutes=120)
        self.camera(7, minutes=10)
        newest = self.camera(10, minutes=10)
        self.camera(99, source='dummy')
        self.camera(98, source='unknown')
        self.camera(97, minutes=24 * 60)
        self.camera(96, minutes=-1)
        self.camera(95, location=self.other)
        before = list(CrowdLog.objects.order_by('pk').values())
        response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['actuals'], [zero, newest])
        self.assertEqual([p['count'] for p in response.context['actual_points']], [0, 10])
        self.assertIn(' C ', response.context['actual_path'])
        self.assertContains(response, 'class="actual-line"')
        self.assertContains(response, 'カメラ実測のみ表示しています')
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)

    def test_actual_and_forecast_share_full_day_axis_and_count_scale(self):
        self.observe(10, hour=13)
        for hour, minute, count in ((0, 5, 0), (23, 59, 80)):
            CrowdLog.objects.create(location=self.location, source='camera', user_count=count,
                recorded_at=timezone.make_aware(datetime(2026, 11, 6, hour, minute)))
        late = self.now.replace(hour=14, minute=59, second=59)  # 23:59:59 JST
        with patch('crowd_app.views.timezone.now', return_value=late):
            response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['ticks'][0]['label'], '0:00')
        self.assertEqual(response.context['ticks'][-1]['label'], '23:00')
        self.assertGreaterEqual(max(response.context['y_ticks']), 80)
        points = response.context['forecast_points'] + response.context['actual_points']
        self.assertTrue(all(0 <= p['left'] <= 100 and 0 <= p['top'] <= 100 for p in points))

    def test_missing_forecast_hours_are_not_filled_or_connected(self):
        self.observe(0, hour=9)
        self.observe(20, hour=11)
        response = self.client.get(reverse('prediction'))
        self.assertEqual([timezone.localtime(p.predicted_at).hour for p in response.context['day_predictions']], [9, 11])
        self.assertEqual(response.context['forecast_path'].count('M '), 2)
        self.assertNotIn(' C ', response.context['forecast_path'])
        self.assertEqual(response.context['actual_points'], [])
        self.assertContains(response, '本日のカメラ実測データはまだありません')

    def test_hourly_actuals_average_valid_zero_and_mark_current_hour_partial(self):
        for count, minutes in ((0, 60), (6, 50), (12, 1), (10, 0)):
            self.camera(count, minutes=minutes)
        self.camera(99, source='dummy')
        before = list(CrowdLog.objects.order_by('pk').values())
        response = self.client.get(reverse('prediction'))
        self.assertEqual(len(response.context['actuals']), 4)
        hourly = response.context['hourly_actuals']
        self.assertEqual([timezone.localtime(row.recorded_at).hour for row in hourly], [11, 12])
        self.assertEqual([row.user_count for row in hourly], [6, 10])
        self.assertEqual([row.sample_count for row in hourly], [3, 1])
        self.assertEqual([row.is_partial for row in hourly], [False, True])
        self.assertEqual(len(response.context['actual_points']), 2)
        self.assertContains(response, 'カメラ実測（時間帯平均）')
        self.assertContains(response, '実測平均：6.0人')
        self.assertContains(response, '計測済み分の平均')
        self.assertEqual(list(CrowdLog.objects.order_by('pk').values()), before)

    def test_hourly_actuals_do_not_create_or_bridge_missing_hours(self):
        self.camera(0, minutes=120)  # 10:00 JST
        self.camera(20, minutes=0)  # 12:00 JST
        response = self.client.get(reverse('prediction'))
        self.assertEqual([timezone.localtime(row.recorded_at).hour for row in response.context['hourly_actuals']], [10, 12])
        self.assertEqual([point['count'] for point in response.context['actual_points']], [0, 20])
        self.assertEqual(response.context['actual_path'].count('M '), 2)
        self.assertNotIn(' C ', response.context['actual_path'])

    def test_adjustment_excludes_dummy_unknown_stale_future_and_other_location(self):
        self.observe(10, hour=11)
        self.observe(20, hour=13)
        self.camera(40, source='dummy')
        self.camera(39, source='unknown')
        self.camera(40, minutes=31)
        self.camera(40, minutes=-1)
        self.camera(40, location=self.other)
        valid = self.camera(6)
        response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['predictions'][0].expected_count, 16)
        self.assertEqual(response.context['camera_sample_count'], 1)
        self.assertEqual(response.context['last_camera_at'], valid.recorded_at)

    def test_zero_camera_count_is_used_and_zero_baseline_does_not_divide(self):
        self.observe(10, hour=11)
        self.observe(20, hour=13)
        reading = self.camera(0)
        self.assertEqual(self.client.get(reverse('prediction')).context['predictions'][0].expected_count, 10)
        # Metadata is explicit: a measured zero is not a communication failure.
        self.assertEqual(self.client.get(reverse('prediction')).context['camera_sample_count'], 1)
        CrowdLog.objects.filter(pk=reading.pk).update(user_count=4)
        CrowdLog.objects.filter(location=self.location, recorded_at__lt=self.now - timedelta(days=1),
                                user_count=10).update(user_count=0)
        self.assertEqual(self.client.get(reverse('prediction')).context['predictions'][0].expected_count, 22)

    def test_no_matching_baseline_does_not_invent_forecast_hours(self):
        self.camera(12)
        response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['predictions'], [])

    def test_live_adjustment_uses_japan_midnight_boundary(self):
        self.now = datetime(2026, 11, 5, 15, 30, tzinfo=datetime_timezone.utc)
        CrowdLog.objects.create(location=self.location, user_count=10,
            recorded_at=datetime(2026, 10, 29, 15, 10, tzinfo=datetime_timezone.utc))
        CrowdLog.objects.create(location=self.location, user_count=20,
            recorded_at=datetime(2026, 10, 29, 16, tzinfo=datetime_timezone.utc))
        self.camera(40, minutes=40)  # Previous day in Japan.
        self.camera(5, minutes=10)
        with patch('crowd_app.views.timezone.now', return_value=self.now):
            response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['predictions'][0].expected_count, 15)
        self.assertEqual(response.context['camera_sample_count'], 1)

    def test_review_morning_dummy_and_noon_camera_update_the_prediction(self):
        self.now = datetime(2026, 11, 10, 4, 20, tzinfo=datetime_timezone.utc)
        for hour, count in [(12, 10), (13, 20), (14, 30)]:
            row = self.observe(count, days=14, hour=hour)
            CrowdLog.objects.filter(pk=row.pk).update(source='dummy')
        for hour, count in [(8, 2), (9, 6), (10, 10), (11, 14)]:
            at = timezone.make_aware(datetime(2026, 11, 10, hour))
            CrowdLog.objects.create(location=self.location, user_count=count,
                                    recorded_at=at, source='dummy')
        with patch('crowd_app.views.timezone.now', return_value=self.now):
            initial = self.client.get(reverse('prediction'))
            self.camera(5, minutes=25)  # 12:55, compared with historical 12:00 bucket.
            first = self.client.get(reverse('prediction'))
            self.camera(15, minutes=5)  # 13:15, compared with historical 13:00 bucket.
            second = self.client.get(reverse('prediction'))
        self.assertEqual(initial.context['predictions'][0].expected_count, 30)
        self.assertEqual(first.context['predictions'][0].expected_count, 22.5)
        self.assertEqual(second.context['predictions'][0].expected_count, 25)
        self.assertEqual(second.context['camera_sample_count'], 2)
        self.assertContains(second, 'ダミーまたは記録元が未確認')

    def test_average_uses_matching_location_weekday_hour_and_past_days(self):
        self.observe(0)
        self.observe(11, days=14)
        self.observe(100, days=6)
        self.observe(100, location=self.other)
        self.observe(100, days=0)
        self.observe(100, days=-7)
        self.observe(100, hour=11)
        self.observe(100, hour=12)
        self.observe(9, hour=15)
        response = self.client.get(reverse('prediction'))
        forecasts = response.context['predictions']
        self.assertEqual([row.expected_count for row in forecasts], [5.5, 9])
        self.assertEqual([row.sample_count for row in forecasts], [2, 1])
        self.assertEqual([timezone.localtime(row.predicted_at).hour for row in forecasts], [13, 15])
        self.assertContains(response, '過去の観測 2件の平均')
        self.assertNotContains(response, 'chart-dot actual-dot')
        self.assertNotContains(response, 'class="actual-line"')

    def test_no_history_does_not_use_current_observations_or_saved_predictions(self):
        self.observe(12, days=0)
        CrowdPrediction.objects.create(location=self.location, expected_count=99,
                                       predicted_at=self.now + timedelta(hours=1))
        response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['predictions'], [])
        self.assertEqual(response.context['forecast_path'], '')
        self.assertContains(response, '対象期間のデータが存在しません')

    def test_zero_is_valid_and_request_does_not_write_records(self):
        self.observe(0)
        observations = list(CrowdLog.objects.values())
        predictions = list(CrowdPrediction.objects.values())
        response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['predictions'][0].expected_count, 0)
        self.assertEqual(list(CrowdLog.objects.values()), observations)
        self.assertEqual(list(CrowdPrediction.objects.values()), predictions)
        self.assertIn('no-store', response['Cache-Control'])

    def test_japan_weekday_and_hour_across_utc_date_boundary(self):
        self.now = datetime(2026, 11, 5, 15, 30, tzinfo=datetime_timezone.utc)  # Friday 00:30 JST
        with patch('crowd_app.views.timezone.now', return_value=self.now):
            CrowdLog.objects.create(location=self.location, user_count=6,
                recorded_at=datetime(2026, 10, 29, 16, tzinfo=datetime_timezone.utc))
            response = self.client.get(reverse('prediction'))
        self.assertEqual(response.context['predictions'][0].expected_count, 6)
        self.assertEqual(timezone.localtime(response.context['predictions'][0].predicted_at).hour, 1)

    def test_location_navigation_and_empty_locations(self):
        self.observe(8, location=self.other)
        response = self.client.get(reverse('prediction'), {'location': self.other.pk})
        self.assertEqual(response.context['predictions'][0].expected_count, 8)
        self.assertContains(response, f'href="/weekly-graph/?location={self.other.pk}"')
        self.assertTrue(self.client.get(reverse('prediction'), {'location': 'bad'}).context['invalid_location'])
        LocationMaster.objects.all().delete()
        self.assertEqual(self.client.get(reverse('prediction')).context['predictions'], [])

class CameraRecordingIntegrationTests(TestCase):
    def test_recorder_uses_existing_rate_calculation_and_top_page(self):
        from tools.db_recording import CrowdRecorder
        location = LocationMaster.objects.create(name='223検証', capacity=25)
        recorder = CrowdRecorder(location.pk)
        measured_at = timezone.now()
        record = recorder.save(10, measured_at)
        record.refresh_from_db()
        self.assertEqual(record.crowd_rate, 40)
        self.assertEqual(record.recorded_at, measured_at)
        self.assertEqual(record.source, 'camera')
        response = self.client.get('/', {'location': location.pk})
        self.assertEqual(response.context['latest'], record)
        self.assertEqual(response.context['occupancy'], Decimal('40.0'))
        measured_text = timezone.localtime(measured_at).strftime('%Y/%m/%d %H:%M:%S')
        self.assertContains(response, measured_text)
        self.assertContains(response, f'href="/prediction-graph/?location={location.pk}"')
        with patch('crowd_app.views.timezone.now', return_value=measured_at + timedelta(minutes=5)):
            refreshed = self.client.get('/', {'location': location.pk})
        self.assertContains(refreshed, measured_text)
        self.assertEqual(CrowdLog.objects.count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.recorded_at, measured_at)
        zero = recorder.save(0, timezone.now())
        self.assertEqual(zero.crowd_rate, 0)
        self.assertEqual(self.client.get('/', {'location': location.pk}).context['latest'], zero)
