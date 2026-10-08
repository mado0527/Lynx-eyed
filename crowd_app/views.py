from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from .calculations import calculate_crowd_rate

from .models import CrowdLog, CrowdPrediction, LocationMaster, DeviceInfo, CameraInfo, DayOfWeekSummaryLog
from .prediction_chart import chart_series
from datetime import datetime, time, timedelta
from django.utils import timezone
from django.db.models import Avg, Count
from django.db.models.functions import ExtractIsoWeekDay
import math


@never_cache
def prediction_graph(request):
    locations = list(LocationMaster.objects.order_by('location_id'))
    selected = next((row for row in locations if str(row.pk) == request.GET.get('location')), None)
    invalid_location = 'location' in request.GET and selected is None
    selected = selected or (locations[0] if locations else None)
    now = timezone.now()
    today = timezone.localdate(now)
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(today, time.min), zone)
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), zone)
    predictions, actuals = [], []
    invalid_predictions = 0
    if selected:
        queryset = CrowdPrediction.objects.filter(location=selected, predicted_at__gt=now, predicted_at__lt=end)
        invalid_predictions = queryset.filter(expected_count__lt=0).count()
        # IDs resolve duplicates deterministically, without claiming a creation date.
        by_target = {}
        for row in queryset.filter(expected_count__gte=0).order_by('predicted_at', 'prediction_id'):
            by_target[row.predicted_at] = row
        predictions = list(by_target.values())
        by_time = {}
        for row in CrowdLog.objects.filter(location=selected, recorded_at__gte=start, recorded_at__lte=now).order_by('recorded_at', 'log_id'):
            by_time[row.recorded_at] = row
        actuals = list(by_time.values())
    times = [timezone.localtime(row.predicted_at) for row in predictions] + [timezone.localtime(row.recorded_at) for row in actuals]
    start_hour = min([9] + [at.hour for at in times])
    end_hour = max([18] + [math.ceil(at.hour + at.minute / 60 + at.second / 3600 + at.microsecond / 3_600_000_000) for at in times])
    max_count = max([40] + [row.expected_count for row in predictions] + [row.user_count for row in actuals])
    step = max(10, math.ceil(max_count / 4 / 10) * 10)
    ceiling = step * 4
    forecast_points, forecast_path = chart_series(predictions, 'predicted_at', 'expected_count', start_hour, end_hour, ceiling)
    actual_points, actual_path = chart_series(actuals, 'recorded_at', 'user_count', start_hour, end_hour, ceiling)
    label_stride = math.ceil((end_hour - start_hour) / 4)
    ticks = [{'left': (hour - start_hour) / (end_hour - start_hour) * 100,
              'label': f'{hour}:00', 'compact': hour in (start_hour, end_hour) or
              (index % label_stride == 0 and end_hour - hour >= label_stride)}
             for index, hour in enumerate(range(start_hour, end_hour + 1))]
    peak = max(predictions, key=lambda row: row.expected_count) if predictions else None
    return render(request, 'crowd_app/prediction.html', {
        'selected_location': selected, 'invalid_location': invalid_location,
        'today': today, 'now': now, 'forecast_points': forecast_points, 'forecast_path': forecast_path,
        'actual_points': actual_points, 'actual_path': actual_path, 'ticks': ticks,
        'y_ticks': [step * index for index in range(4, -1, -1)], 'peak': peak,
        'predictions': predictions, 'actuals': actuals, 'invalid_predictions': invalid_predictions,
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
    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)
    zone = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_date, time.min), zone)
    end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), zone)
    aggregates = {}
    saved_summary = False
    if selected:
        month_start = timezone.make_aware(datetime.combine(today.replace(day=1), time.min), zone)
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = timezone.make_aware(datetime.combine(next_month, time.min), zone)
        summaries = DayOfWeekSummaryLog.objects.filter(
            location=selected, summary_month__gte=month_start, summary_month__lt=month_end,
            day_of_week__range=(0, 6), avg_count__gte=0,
        ).order_by('executed_at', 'dow_log_id')
        for row in summaries:
            aggregates[row.day_of_week or 7] = {'average': row.avg_count, 'samples': 1}
        saved_summary = bool(aggregates)
        if not saved_summary:
            rows = (CrowdLog.objects.filter(location=selected, recorded_at__gte=start, recorded_at__lt=end)
                    .annotate(weekday=ExtractIsoWeekDay('recorded_at', tzinfo=zone))
                    .values('weekday').annotate(average=Avg('user_count'), samples=Count('pk')))
            aggregates = {row['weekday']: row for row in rows}
    maximum = max((row['average'] for row in aggregates.values()), default=0)
    step = max(1, math.ceil(maximum / 4))
    ceiling = step * 4
    chart = []
    for index, day in enumerate('月火水木金土日', 1):
        row = aggregates.get(index)
        average = row['average'] if row else None
        height = average / ceiling * 100 if average is not None else 0
        chart.append({'day': day, 'average': average, 'samples': row['samples'] if row else 0,
                      'height': height, 'measured': row is not None})
    measured = [row for row in chart if row['measured']]
    busiest = [row['day'] for row in measured if row['average'] == maximum]
    return render(request, 'crowd_app/weekly.html', {
        'locations': locations, 'selected_location': selected, 'periods': periods,
        'period': days, 'start_date': start_date, 'end_date': today, 'chart': chart,
        'ticks': [step * index for index in range(4, -1, -1)],
        'samples': sum(row['samples'] for row in measured), 'busiest': busiest,
        'maximum': maximum, 'invalid_location': invalid_location, 'invalid_period': invalid_period,
        'saved_summary': saved_summary, 'summary_month': today.replace(day=1),
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
    if selected:
        history = list(CrowdLog.objects.filter(location=selected).order_by('-recorded_at', '-log_id')[:20])
        latest = history[0] if history else None
        history.reverse()
        if latest is not None:
            occupancy = calculate_crowd_rate(latest.user_count, selected.capacity)
        if history:
            max_count = max(1, max(row.user_count for row in history))
            slot_width = 560 / len(history)
            bar_width = min(112, slot_width * 0.8)
            for index, row in enumerate(history):
                x = 60 + slot_width * (index + 0.5)
                y = 240 - 190 * row.user_count / max_count
                points.append({
                    'x': round(x, 2), 'left': round(x - bar_width / 2, 2),
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
    return render(request, 'crowd_app/devices.html', {
        'devices': DeviceInfo.objects.order_by('device_id') if can_view_devices else DeviceInfo.objects.none(),
        'cameras': CameraInfo.objects.select_related('location', 'device').order_by('camera_id') if can_view_cameras else CameraInfo.objects.none(),
    })
