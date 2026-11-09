"""Historical hourly baseline adjusted by recent, explicitly tagged camera data."""
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from collections import defaultdict

from django.utils import timezone

from .models import CrowdLog


def hourly_averages(location, now):
    zone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    start = timezone.make_aware(datetime.combine(today, time.min), zone)
    rows = (CrowdLog.objects.filter(location=location, recorded_at__lt=start, user_count__gte=0)
            .order_by().values_list('recorded_at', 'user_count', 'source'))
    # Convert in Python: MySQL's CONVERT_TZ returns NULL without timezone tables.
    buckets = defaultdict(lambda: [0, 0, 0, 0])
    for recorded_at, user_count, source in rows.iterator():
        local = timezone.localtime(recorded_at, zone)
        if local.isoweekday() == today.isoweekday():
            buckets[local.hour][0] += user_count
            buckets[local.hour][1] += 1
            buckets[local.hour][2] += int(source == 'dummy')
            buckets[local.hour][3] += int(source == 'unknown')

    recent = (CrowdLog.objects.filter(location=location, source='camera', user_count__gte=0,
              recorded_at__gte=max(start, now - timedelta(minutes=30)), recorded_at__lte=now)
              .order_by('recorded_at', 'log_id').values_list('recorded_at', 'user_count'))
    actual_total = expected_total = 0
    camera_samples = 0
    last_camera_at = None
    for recorded_at, user_count in recent:
        hour = timezone.localtime(recorded_at, zone).hour
        if hour not in buckets:
            continue
        total, samples, _, _ = buckets[hour]
        actual_total += user_count
        expected_total += total / samples
        camera_samples += 1
        last_camera_at = recorded_at
    factor, offset = 1, 0
    if camera_samples:
        # Half the historical pattern, half the relative occupancy seen today.
        # A zero baseline uses an additive adjustment to avoid division by zero.
        if expected_total > 0:
            factor = (1 + actual_total / expected_total) / 2
        else:
            offset = actual_total / camera_samples / 2
    forecasts = []
    for hour, (total, samples, dummy_samples, unknown_samples) in sorted(buckets.items()):
        target = timezone.make_aware(datetime.combine(today, time(hour)), zone)
        if target > now:
            forecasts.append(SimpleNamespace(predicted_at=target,
                expected_count=round(max(0, total / samples * factor + offset), 1),
                sample_count=samples, baseline_count=round(total / samples, 1),
                camera_sample_count=camera_samples, last_camera_at=last_camera_at,
                camera_mean=round(actual_total / camera_samples, 1) if camera_samples else None,
                contains_dummy=bool(dummy_samples), contains_unknown=bool(unknown_samples)))
    return forecasts
