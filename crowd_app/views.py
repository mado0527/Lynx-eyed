from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from .calculations import calculate_crowd_rate

from .models import CrowdLog, LocationMaster, DeviceInfo, CameraInfo
from .prediction_chart import chart_series
from .average_forecast import hourly_averages
from .weekly_tendencies import SCHOOL_PERIODS, selected_tendency, weekday_time_grid
from django.http import JsonResponse
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from django.utils import timezone
import math


@never_cache
def prediction_graph(request):
    locations = list(LocationMaster.objects.order_by('location_id'))
    selected = next((row for row in locations if str(row.pk) == request.GET.get('location')), None)
    invalid_location = 'location' in request.GET and selected is None
    selected = selected or (locations[0] if locations else None)
    now = timezone.now()
    is_preview = False
    invalid_preview = False
    raw_preview_date = request.GET.get('preview_date')
    if raw_preview_date is not None:
        try:
            preview_date = date.fromisoformat(raw_preview_date)
            if preview_date >= timezone.localdate(now) or preview_date.isoformat() != raw_preview_date:
                raise ValueError
        except ValueError:
            invalid_preview = True
        else:
            is_preview = True
            now = timezone.make_aware(datetime.combine(preview_date, time.max), timezone.get_current_timezone())
    today = timezone.localdate(now)
    day_predictions = hourly_averages(selected, now, include_past=True) if selected else []
    predictions = [row for row in day_predictions if row.predicted_at > now]
    actuals = []
    hourly_actuals = []
    displayed_records = []
    if selected:
        zone = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(today, time.min), zone)
        end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), zone)
        allowed_sources = ('camera', 'dummy') if is_preview else ('camera',)
        records = CrowdLog.objects.filter(location=selected, source__in=allowed_sources, user_count__gte=0,
            recorded_at__gte=start, recorded_at__lt=end, recorded_at__lte=now).order_by('recorded_at', 'log_id')
        # Keep the largest ID at an identical timestamp; duplicate x values
        # must not create misleading vertical connections or interpolation errors.
        records = list({(row.source, row.recorded_at): row for row in records}.values())
        actuals = [row for row in records if row.source == 'camera']
        buckets = {}
        for row in records:
            hour = timezone.localtime(row.recorded_at, zone).replace(minute=0, second=0, microsecond=0)
            buckets.setdefault(hour, {'camera': [], 'dummy': []})[row.source].append(row)
        for hour, sources in sorted(buckets.items()):
            # A real measurement (including zero) takes precedence for the
            # whole hour. Never average synthetic values into observed values.
            source = 'camera' if sources['camera'] else 'dummy'
            adopted = sources[source]
            displayed_records.extend(adopted)
            hourly_actuals.append(SimpleNamespace(recorded_at=hour,
                user_count=round(sum(row.user_count for row in adopted) / len(adopted), 1),
                sample_count=len(adopted), source=source,
                period_end=hour + timedelta(hours=1), is_partial=hour + timedelta(hours=1) > now))
        if not is_preview:
            # Temporary display data only: never persist or use for forecast correction.
            occupied_hours = {row.recorded_at.hour for row in hourly_actuals}
            demo_ratios = (0.15, 0.25, 0.40, 0.75, 0.85, 0.55, 0.35, 0.45, 0.25, 0.10)
            capacity = max(0, selected.capacity or 0)
            for hour, ratio in enumerate(demo_ratios, start=9):
                at = timezone.make_aware(datetime.combine(today, time(hour)), zone)
                if at > now or hour in occupied_hours:
                    continue
                hourly_actuals.append(SimpleNamespace(recorded_at=at,
                    user_count=round(capacity * ratio), sample_count=1, source='dummy',
                    period_end=at + timedelta(hours=1), is_partial=at + timedelta(hours=1) > now))
            hourly_actuals.sort(key=lambda row: row.recorded_at)
    times = ([timezone.localtime(row.predicted_at) for row in day_predictions] +
             [timezone.localtime(row.recorded_at) for row in hourly_actuals])
    start_hour = min((at.hour for at in times), default=9)
    end_hour = max((math.ceil(at.hour + at.minute / 60 + at.second / 3600 + at.microsecond / 3_600_000_000)
                    for at in times), default=18)
    end_hour = max(end_hour, start_hour + 1)
    max_count = max([40] + [row.expected_count for row in day_predictions] + [row.user_count for row in hourly_actuals])
    step = max(10, math.ceil(max_count / 4 / 10) * 10)
    ceiling = step * 4
    forecast_points, forecast_path = chart_series(day_predictions, 'predicted_at', 'expected_count', start_hour, end_hour,
                                                  ceiling, max_gap_seconds=3600)
    actual_points, actual_path = chart_series(hourly_actuals, 'recorded_at', 'user_count', start_hour, end_hour, ceiling,
                                             max_gap_seconds=3600)
    label_stride = math.ceil((end_hour - start_hour) / 4)
    ticks = [{'left': (hour - start_hour) / (end_hour - start_hour) * 100,
              'label': f'{hour}:00', 'compact': hour in (start_hour, end_hour) or
              (index % label_stride == 0 and end_hour - hour >= label_stride)}
             for index, hour in enumerate(range(start_hour, end_hour + 1))]
    peak = max(day_predictions, key=lambda row: row.expected_count) if day_predictions else None
    return render(request, 'crowd_app/prediction.html', {
        'selected_location': selected, 'invalid_location': invalid_location,
        'today': today, 'now': now, 'forecast_points': forecast_points, 'forecast_path': forecast_path,
        'is_preview': is_preview, 'invalid_preview': invalid_preview,
        'period_label': '表示日' if is_preview else '本日',
        'day_predictions': day_predictions, 'actual_points': actual_points, 'actual_path': actual_path,
        'actuals': actuals, 'hourly_actuals': hourly_actuals,
        'has_dummy_actuals': any(row.source == 'dummy' for row in hourly_actuals),
        'display_record_count': sum(row.sample_count for row in hourly_actuals),
        'ticks': ticks,
        'y_ticks': [step * index for index in range(4, -1, -1)], 'peak': peak,
        'predictions': predictions,
        'refresh_seconds': None if is_preview else 5,
        'camera_sample_count': predictions[0].camera_sample_count if predictions else 0,
        'last_camera_at': predictions[0].last_camera_at if predictions else None,
        'baseline_unverified': any(p.contains_dummy or p.contains_unknown for p in day_predictions),
    })


@never_cache
def weekly_graph(request):
    locations = list(LocationMaster.objects.order_by('location_id'))
    selected = next((row for row in locations if str(row.pk) == request.GET.get('location')), None)
    invalid_location = 'location' in request.GET and selected is None
    selected = selected or (locations[0] if locations else None)
    periods = [(28, '直近4週間'), (56, '直近8週間'), (84, '直近12週間')]
    raw_period = request.GET.get('period', '28')
    invalid_period = raw_period not in ('28', '56', '84')
    days = int(raw_period) if not invalid_period else 28
    now = timezone.now()
    today = timezone.localdate(now)
    start_date = today - timedelta(days=days - 1)
    if request.GET.get('format') == 'json':
        try:
            weekday = int(request.GET.get('weekday', '1'))
            slot = int(request.GET.get('slot', '0'))
            if weekday not in range(1, 6):
                raise ValueError
        except ValueError:
            return JsonResponse({'error': '選択内容が無効です。'}, status=400)
        timetable = SCHOOL_PERIODS
        options = [{'value': index, 'label': f'{label}（{begins:%H:%M}〜{ends:%H:%M}）'}
                   for index, (label, begins, ends) in enumerate(timetable)]
        if slot not in range(len(timetable)):
            return JsonResponse({'error': '時間帯の指定が無効です。'}, status=400)
        result = selected_tendency(selected, start_date, today, now, timetable, weekday, slot)
        return JsonResponse({'result': result, 'slots': options,
            'capacity': selected.capacity if selected else None,
            'start_date': start_date.isoformat(), 'end_date': today.isoformat(),
            'location': selected.name if selected else '場所未登録',
            'notice': ('場所の指定が無効です。登録済みの場所を表示しています。' if invalid_location else '') +
                      ('期間の指定が無効です。直近4週間を表示しています。' if invalid_period else '')})
    return render(request, 'crowd_app/weekly.html', {
        **weekday_time_grid(selected, start_date, today, now, SCHOOL_PERIODS),
        'locations': locations, 'selected_location': selected, 'periods': periods,
        'period': days, 'start_date': start_date, 'end_date': today,
        'slot_options': [(index, label) for index, (label, _, _) in enumerate(SCHOOL_PERIODS)],
        'invalid_location': invalid_location, 'invalid_period': invalid_period,
    })


@never_cache
def home(request):
    locations = list(LocationMaster.objects.order_by('location_id'))
    selected = locations[0] if locations else None
    requested = request.GET.get('location')
    invalid_location = False
    if requested is not None:
        selected_match = next((item for item in locations if str(item.pk) == requested), None)
        if selected_match is None:
            invalid_location = True
        else:
            selected = selected_match
    latest = None
    occupancy = None
    history = []
    points = []
    ticks = []
    max_count = 1
    now = timezone.now()
    crowd_state = 'unknown'
    crowd_label = '未計測'
    is_previous_day = False
    if selected:
        logs = CrowdLog.objects.filter(location=selected)
        latest = logs.filter(recorded_at__lte=now).order_by('-recorded_at', '-log_id').first()
        today = timezone.localdate(now)
        zone = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(today, time.min), zone)
        end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), zone)
        history = list(logs.filter(recorded_at__gte=start, recorded_at__lt=end, recorded_at__lte=now)
                       .order_by('-recorded_at', '-log_id')[:5])
        history.reverse()
        if latest is not None:
            occupancy = calculate_crowd_rate(latest.user_count, selected.capacity)
            is_previous_day = timezone.localdate(latest.recorded_at) != today
            if is_previous_day:
                crowd_label = '本日は未計測'
            elif occupancy is None:
                crowd_label = '混雑率は算出不可'
            elif occupancy < 31:
                crowd_state, crowd_label = 'low', '空いています'
            elif occupancy <= 75:
                crowd_state, crowd_label = 'moderate', 'やや混雑しています'
            else:
                crowd_state, crowd_label = 'high', '混雑しています'
        if history:
            max_count = max(1, max(row.user_count for row in history))
            slot_width = 560 / len(history)
            bar_width = min(112, slot_width * 0.8)
            for index, row in enumerate(history):
                x = 60 + slot_width * (index + 0.5)
                y = 240 - 190 * row.user_count / max_count
                points.append({
                    'x': round(x, 2), 'left': round(x - bar_width / 2, 2),
                    'slot_left': round(60 + slot_width * index, 2), 'slot_width': round(slot_width, 2),
                    'width': round(bar_width, 2), 'y': round(y, 2),
                    'height': round(240 - y, 2), 'record': row,
                    'show_label': len(history) <= 5 or index in (0, len(history) - 1),
                })
            ticks = [{'y': 240, 'value': 0}, {'y': 50, 'value': max_count}]
    return render(request, 'crowd_app/home.html', {
        'locations': locations, 'selected_location': selected,
        'latest': latest, 'occupancy': occupancy,
        'invalid_location': invalid_location,
        'history': history, 'chart_points': points, 'chart_ticks': ticks,
        'crowd_state': crowd_state, 'crowd_label': crowd_label,
        'is_previous_day': is_previous_day,
        'refresh_seconds': 2 if request.GET.get('realtime') == '1' else None,
    })


def information_page(request, page):
    pages = {
        'live': ('ライブ映像', 'カメラ映像', '映像表示', 'カメラ映像の配信・閲覧は未実装です。'),
        'help': ('ヘルプ', '使い方ガイド', '混雑状況の確認', ''),
    }
    title, subtitle, panel_title, message = pages[page]
    return render(request, 'crowd_app/information.html', {
        'page': page, 'title': title, 'subtitle': subtitle,
        'panel_title': panel_title, 'message': message,
    })


@staff_member_required
def device_management(request):
    can_view_devices = request.user.has_perm('crowd_app.view_deviceinfo')
    can_view_cameras = request.user.has_perm('crowd_app.view_camerainfo')
    if not (can_view_devices or can_view_cameras):
        raise PermissionDenied
    selected = None
    if 'location' in request.GET:
        if not request.user.has_perm('crowd_app.view_locationmaster'):
            raise PermissionDenied
        selected = next((row for row in LocationMaster.objects.order_by('location_id')
                         if str(row.pk) == request.GET['location']), None)
        if selected is None:
            raise PermissionDenied
    cameras = CameraInfo.objects.select_related('location', 'device').order_by('camera_id') if can_view_cameras else CameraInfo.objects.none()
    if selected:
        cameras = cameras.filter(location=selected)
    return render(request, 'crowd_app/devices.html', {
        'can_view_devices': can_view_devices, 'can_view_cameras': can_view_cameras,
        'selected_location': selected,
        'can_access_dashboard': request.user.has_perms(('crowd_app.view_locationmaster', 'crowd_app.view_crowdlog')),
        'devices': DeviceInfo.objects.order_by('device_id') if can_view_devices else DeviceInfo.objects.none(),
        'cameras': cameras,
    })
