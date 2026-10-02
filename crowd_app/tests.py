from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal

from .models import CrowdLog, LocationMaster


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
        self.assertContains(response, 'href="/admin/"')

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
        self.assertContains(response, '10:02:03')
        self.assertContains(response, '2026/10/02')
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

    def test_graph_order_selection_and_single_record(self):
        location = self.make_location()
        other = self.make_location(name='別の場所')
        self.record(other, 99)
        at = datetime(2026, 10, 2, 1, 2, 3, tzinfo=datetime_timezone.utc)
        newer = self.record(location, 10, at)
        response = self.client.get('/')
        self.assertContains(response, 'class="trend-bar"', count=1)
        older = self.record(location, 3, at.replace(day=1))
        response = self.client.get('/')
        self.assertEqual(response.context['history'], [older, newer])
        self.assertContains(response, 'class="trend-bar"', count=2)
        self.assertNotContains(response, '<polyline')
        self.assertContains(response, 'type="submit"', count=1)
        self.assertEqual(response.context['chart_points'][-1]['record'], newer)

    def test_graph_missing_and_recent_limit(self):
        location = self.make_location()
        self.assertContains(self.client.get('/'), '対象期間のデータが存在しません')
        for count in range(21):
            self.record(location, count)
        response = self.client.get('/')
        self.assertEqual(len(response.context['history']), 20)
        self.assertEqual(response.context['history'][0].user_count, 1)
        self.assertEqual(response.context['latest'].user_count, 20)


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
            self.assertContains(response, '未実装')
            self.assertContains(response, 'name="viewport"')
        self.assertContains(self.client.get(reverse('prediction')), reverse('weekly'))
        self.assertNotContains(self.client.get(reverse('live')), '稼働中')
        self.assertContains(self.client.get('/'), reverse('prediction'))
        self.assertContains(self.client.get('/'), reverse('live'))
        self.assertContains(self.client.get('/'), 'type="submit"', count=1)

    def test_authentication_and_admin_templates(self):
        self.assertRedirects(self.client.get('/login/'), '/admin/login/')
        response = self.client.get('/admin/login/')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'admin-design.css')
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
