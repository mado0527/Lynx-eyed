from datetime import datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from .models import CameraInfo, CrowdLog, DeviceInfo, LocationMaster


class ManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.location = LocationMaster.objects.create(name='対象ラウンジ', capacity=40)
        cls.other = LocationMaster.objects.create(name='別ラウンジ', capacity=20)
        cls.admin = get_user_model().objects.create_superuser('management_test_admin', password='test-only-password')
        cls.user = get_user_model().objects.create_user('ordinary_test_user', password='test-only-password')
        cls.staff = get_user_model().objects.create_user('limited_test_staff', password='test-only-password', is_staff=True)
        cls.now = datetime(2026, 10, 8, 3, tzinfo=utc.utc)
        cls.device = DeviceInfo.objects.create(name='検証用端末', cpu_usage=5, storage_usage=10,
            network_status=0, checked_at=cls.now)
        cls.camera = CameraInfo.objects.create(camera_id='test-camera', name='対象カメラ',
            location=cls.location, device=cls.device, camera_type=0, status=0, installed_at=cls.now)

    def setUp(self):
        self.clock = patch('crowd_app.management.timezone.now', return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def grant(self, *names):
        self.staff.user_permissions.add(*Permission.objects.filter(content_type__app_label='crowd_app', codename__in=names))

    def record(self, count, day, hour=0, location=None):
        return CrowdLog.objects.create(location=location or self.location, user_count=count,
            recorded_at=datetime(2026, 10, day, hour, tzinfo=utc.utc))

    def test_anonymous_redirect_preserves_place_and_month(self):
        response = self.client.get(reverse('management'), {'location': self.other.pk, 'month': '2026-09'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/management/login/?next='))
        self.assertIn('location%3D', response.url)
        self.assertIn('2026-09', response.url)

    def test_normal_staff_login_and_safe_redirect(self):
        self.grant('view_locationmaster', 'view_crowdlog')
        response = self.client.post(reverse('management_login'), {
            'username': self.staff.username, 'password': 'test-only-password',
            'next': f'/management/?location={self.other.pk}&month=2026-09',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/management/?location={self.other.pk}&month=2026-09')
        self.assertEqual(self.client.get(response.url).status_code, 200)
        self.client.logout()
        response = self.client.post(reverse('management_login'), {
            'username': self.admin.username, 'password': 'test-only-password',
            'next': 'https://untrusted.example/', 'location': self.other.pk,
        })
        self.assertEqual(response.url, f'/management/?location={self.other.pk}')

    def test_regular_user_and_inactive_user_cannot_login_or_access(self):
        response = self.client.post(reverse('management_login'), {
            'username': self.user.username, 'password': 'test-only-password',
        })
        self.assertContains(response, '管理者権限が必要')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('management')).status_code, 403)
        self.client.logout()
        self.admin.is_active = False
        self.admin.save(update_fields=['is_active'])
        response = self.client.post(reverse('management_login'), {
            'username': self.admin.username, 'password': 'test-only-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_dashboard_requires_both_view_permissions(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('management')).status_code, 403)
        self.grant('view_crowdlog')
        self.assertEqual(self.client.get(reverse('management')).status_code, 403)
        self.grant('view_locationmaster')
        response = self.client.get(reverse('management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'カメラ情報の閲覧権限がありません')
        self.assertNotContains(response, self.camera.name)
        self.assertContains(response, '端末情報管理（閲覧権限なし）')
        self.assertEqual(self.client.get(reverse('devices')).status_code, 403)

    def test_logout_and_login_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('management_login'), {
            'username': self.admin.username, 'password': 'test-only-password',
        }).status_code, 403)
        client.force_login(self.admin)
        self.assertEqual(client.get(reverse('management_logout')).status_code, 405)
        self.assertEqual(client.post(reverse('management_logout')).status_code, 403)
        client.get(reverse('management'))
        token = client.cookies['csrftoken'].value
        response = client.post(reverse('management_logout'), {'csrfmiddlewaretoken': token})
        self.assertRedirects(response, reverse('home'))
        self.assertNotIn('_auth_user_id', client.session)

    def test_admin_login_uses_shared_screen_and_preserves_destination(self):
        destination = '/admin/crowd_app/deviceinfo/'
        response = self.client.get(reverse('admin:login'), {'next': destination})
        self.assertTemplateUsed(response, 'crowd_app/management_login.html')
        self.assertNotContains(response, 'Lynx-eyed 管理者ページ')
        response = self.client.post(reverse('admin:login'), {
            'username': self.admin.username, 'password': 'test-only-password', 'next': destination,
        })
        self.assertRedirects(response, destination)
        self.client.logout()
        response = self.client.post(reverse('admin:login'), {
            'username': self.admin.username, 'password': 'test-only-password', 'next': 'https://untrusted.example/',
        })
        self.assertRedirects(response, reverse('admin:index'))
        self.client.logout()
        response = self.client.post(reverse('admin:login'), {
            'username': self.user.username, 'password': 'test-only-password',
        })
        self.assertContains(response, '管理者権限が必要')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertRedirects(self.client.get('/login/?next=/admin/'), '/management/login/?next=/admin/')

    def test_admin_logout_csrf_and_shared_relogin(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.get(reverse('admin:logout')).status_code, 405)
        self.assertEqual(client.post(reverse('admin:logout')).status_code, 403)
        client.get(reverse('admin:index'))
        response = client.post(reverse('admin:logout'), {
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        }, follow=True)
        self.assertEqual(response.redirect_chain, [('/management/login/?next=%2Fadmin%2F', 302)])
        self.assertTemplateUsed(response, 'crowd_app/management_login.html')
        self.assertNotIn('_auth_user_id', client.session)

    def test_month_averages_latest_zero_and_no_mutation(self):
        self.client.force_login(self.admin)
        first = self.record(10, 2)
        second = self.record(30, 2, 1)
        latest = self.record(0, 8)
        self.record(99, 9)  # Future records must not be included.
        self.record(99, 2, location=self.other)
        # Keep a historical saved rate independent of current capacity.
        CrowdLog.objects.filter(pk=first.pk).update(crowd_rate=20)
        CrowdLog.objects.filter(pk=second.pk).update(crowd_rate=60)
        self.location.capacity = 100
        self.location.save(update_fields=['capacity'])
        before = list(CrowdLog.objects.values())
        response = self.client.get(reverse('management'), {'location': self.location.pk})
        self.assertEqual(response.context['latest'], latest)
        self.assertEqual(response.context['sample_count'], 3)
        self.assertAlmostEqual(response.context['average_rate'], 80 / 3)
        self.assertEqual(response.context['max_count'], 30)
        self.assertEqual(response.context['daily_points'][1]['average'], 20)
        self.assertEqual(response.context['daily_points'][7]['average'], 0)
        self.assertIsNone(response.context['daily_points'][0]['average'])
        self.assertEqual(list(CrowdLog.objects.values()), before)
        self.assertContains(response, '未対応')
        self.assertContains(response, '登録上の状態：正常')
        self.assertContains(response, 'type="checkbox" disabled', count=3)
        self.assertNotContains(response, 'id="content-related"')
        self.assertNotContains(response, 'id="user-tools"')

    def test_month_boundaries_japan_and_navigation(self):
        self.client.force_login(self.admin)
        # UTC Sep 30 15:00 is Japan Oct 1 00:00.
        CrowdLog.objects.create(location=self.location, user_count=7,
            recorded_at=datetime(2026, 9, 30, 15, tzinfo=utc.utc))
        CrowdLog.objects.create(location=self.location, user_count=3,
            recorded_at=datetime(2026, 9, 30, 14, 59, tzinfo=utc.utc))
        response = self.client.get(reverse('management'), {'month': '2026-09', 'location': self.location.pk})
        self.assertEqual(response.context['sample_count'], 1)
        self.assertEqual(response.context['daily_points'][-1]['average'], 3)
        self.assertEqual(response.context['latest'].user_count, 7)
        self.assertIn('month=2026-10', response.context['next_url'])
        self.assertIn(f'location={self.location.pk}', response.context['next_url'])
        self.assertIsNone(self.client.get(response.context['next_url']).context['next_url'])

    def test_no_data_no_locations_invalid_month_and_null_rate(self):
        self.client.force_login(self.admin)
        for month in ('invalid', '2026-13', '2026-11', '0001-01', ''):
            response = self.client.get(reverse('management'), {'month': month})
            self.assertTrue(response.context['invalid_month'])
            self.assertContains(response, '未計測')
            self.assertContains(response, '対象月の計測記録がありません')
        self.location.capacity = 0
        self.location.save()
        self.record(0, 2)
        response = self.client.get(reverse('management'))
        self.assertContains(response, '算出不可')
        self.assertEqual(response.context['rate_count'], 0)
        self.assertEqual(response.context['latest'].user_count, 0)
        LocationMaster.objects.all().delete()
        self.assertContains(self.client.get(reverse('management')), '場所が未登録です')

    def test_camera_device_permissions_and_data_edit_admin_preserved(self):
        self.grant('view_locationmaster', 'view_crowdlog', 'view_camerainfo')
        self.client.force_login(self.staff)
        response = self.client.get(reverse('management'))
        self.assertContains(response, self.camera.name)
        self.assertContains(response, f'href="/device-management/?location={self.location.pk}"')
        response = self.client.get(reverse('devices'))
        self.assertContains(response, '端末情報の閲覧権限がありません')
        self.assertNotContains(response, 'href="/admin/crowd_app/deviceinfo/"')
        self.assertEqual(self.client.get('/admin/crowd_app/deviceinfo/').status_code, 403)
        response = self.client.get(reverse('devices'), {'location': self.location.pk})
        self.assertContains(response, f'href="/management/?location={self.location.pk}"')
        self.assertContains(response, self.camera.name)
        self.assertEqual(self.client.get(reverse('devices'), {'location': 'invalid'}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('management')), 'href="/admin/"')
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.assertContains(self.client.get('/'), f'href="/management/?location={self.location.pk}"')

    def test_error_and_independent_login_template(self):
        response = self.client.get(reverse('management_login'))
        self.assertContains(response, '管理者ログイン')
        self.assertNotContains(response, 'id="header"')
        self.assertContains(response, 'autocomplete="current-password"')
        response = self.client.post(reverse('management_login'), {
            'username': self.admin.username, 'password': 'wrong-test-password',
        })
        self.assertContains(response, 'role="alert"')
        self.assertNotIn('_auth_user_id', self.client.session)
