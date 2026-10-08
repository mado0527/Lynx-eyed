"""Independent staff screens backed by Django authentication and existing models."""
import calendar
import math
import re
from collections import defaultdict
from datetime import date, datetime, time
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView, redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .models import CameraInfo, CrowdLog, LocationMaster

DASHBOARD_PERMISSIONS = ('crowd_app.view_locationmaster', 'crowd_app.view_crowdlog')


class ManagementAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError('この画面には管理者権限が必要です。', code='not_staff')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'placeholder': 'ユーザー名', 'autocomplete': 'username'})
        self.fields['password'].widget.attrs.update({'placeholder': '••••••••', 'autocomplete': 'current-password'})


class ManagementLoginView(LoginView):
    template_name = 'crowd_app/management_login.html'
    authentication_form = ManagementAuthenticationForm

    def get_default_redirect_url(self):
        query = {}
        location = self.request.POST.get('location') or self.request.GET.get('location')
        if location and location.isdigit():
            query['location'] = location
        return reverse('management') + ('?' + urlencode(query) if query else '')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['location_id'] = self.request.POST.get('location') or self.request.GET.get('location', '')
        return context


class ManagementLogoutView(LogoutView):
    next_page = 'home'
    http_method_names = ['post', 'options']

    def get_success_url(self):
        # Ignore user-provided redirect targets on logout.
        return reverse('home')


class DataManagementLoginView(ManagementLoginView):
    def get_default_redirect_url(self):
        return reverse('admin:index')


class DataManagementLogoutView(ManagementLogoutView):
    def get_success_url(self):
        return reverse('management_login') + '?' + urlencode({'next': reverse('admin:index')})


def management_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse('management_login'))
        if not request.user.is_active or not request.user.is_staff or not request.user.has_perms(DASHBOARD_PERMISSIONS):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def month_link(month, location):
    query = {'month': month.strftime('%Y-%m')}
    if location:
        query['location'] = location.pk
    return reverse('management') + '?' + urlencode(query)


@never_cache
@management_required
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate(now)
    locations = list(LocationMaster.objects.order_by('location_id'))
    selected = next((row for row in locations if str(row.pk) == request.GET.get('location')), None)
    invalid_location = 'location' in request.GET and selected is None
    selected = selected or (locations[0] if locations else None)
    month = today.replace(day=1)
    raw_month = request.GET.get('month')
    invalid_month = False
    if raw_month is not None:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}', raw_month):
                raise ValueError
            parsed = date.fromisoformat(raw_month + '-01')
            if parsed.year < 1900 or parsed > month:
                raise ValueError
            month = parsed
        except ValueError:
            invalid_month = True
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    previous_month = date(month.year - (month.month == 1), (month.month - 2) % 12 + 1, 1)
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(month, time.min), zone)
    end = timezone.make_aware(datetime.combine(next_month, time.min), zone)
    latest = None
    per_day = defaultdict(lambda: {'sum': 0, 'samples': 0})
    sample_count, max_count, rate_sum, rate_count = 0, None, 0, 0
    if selected:
        latest = CrowdLog.objects.filter(location=selected, recorded_at__lte=now).order_by('-recorded_at', '-log_id').first()
        records = CrowdLog.objects.filter(location=selected, recorded_at__gte=start, recorded_at__lt=end, recorded_at__lte=now)
        for at, count, rate in records.values_list('recorded_at', 'user_count', 'crowd_rate').iterator():
            bucket = per_day[timezone.localtime(at).day]
            bucket['sum'] += count
            bucket['samples'] += 1
            sample_count += 1
            max_count = count if max_count is None else max(max_count, count)
            if rate is not None and math.isfinite(rate):
                rate_sum += rate
                rate_count += 1
    average_rate = rate_sum / rate_count if rate_count else None
    maximum_daily = max((row['sum'] / row['samples'] for row in per_day.values()), default=0)
    ceiling = max(40, math.ceil(maximum_daily / 20) * 20)
    days = []
    last_day = calendar.monthrange(month.year, month.month)[1]
    for day in range(1, last_day + 1):
        row = per_day.get(day)
        average = row['sum'] / row['samples'] if row else None
        days.append({'day': day, 'average': average, 'measured': row is not None,
                     'height': average / ceiling * 100 if average is not None else 0,
                     'samples': row['samples'] if row else 0,
                     'label': day in (1, last_day) or (day % 5 == 0 and last_day - day >= 3),
                     'compact_label': day in (1, 10, 20, last_day)})
    can_view_cameras = request.user.has_perm('crowd_app.view_camerainfo')
    cameras = CameraInfo.objects.filter(location=selected).order_by('camera_id') if selected and can_view_cameras else []
    can_view_devices = request.user.has_perm('crowd_app.view_deviceinfo')
    return render(request, 'crowd_app/management_dashboard.html', {
        'locations': locations, 'selected_location': selected, 'invalid_location': invalid_location,
        'month': month, 'month_end': date(month.year, month.month, len(days)),
        'invalid_month': invalid_month, 'latest': latest, 'average_rate': average_rate,
        'sample_count': sample_count, 'rate_count': rate_count, 'max_count': max_count,
        'daily_points': days, 'y_ticks': [ceiling, ceiling / 2, 0],
        'previous_url': month_link(previous_month, selected) if previous_month.year >= 1900 else None,
        'next_url': month_link(next_month, selected) if next_month <= today.replace(day=1) else None,
        'can_view_cameras': can_view_cameras, 'cameras': cameras,
        'can_view_devices': can_view_devices, 'can_access_devices': can_view_devices or can_view_cameras,
        'can_manage_data': request.user.has_module_perms('crowd_app'),
    })
