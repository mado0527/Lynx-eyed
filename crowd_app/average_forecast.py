"""Read-only hourly forecasts from historical observations."""
from datetime import datetime, time
from types import SimpleNamespace
from collections import defaultdict

from django.utils import timezone

from .models import CrowdLog


def hourly_averages(location, now):
    zone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    start = timezone.make_aware(datetime.combine(today, time.min), zone)
    rows = (CrowdLog.objects.filter(location=location, recorded_at__lt=start, user_count__gte=0)
            .order_by().values_list('recorded_at', 'user_count'))
    # Convert in Python: MySQL's CONVERT_TZ returns NULL without timezone tables.
    buckets = defaultdict(lambda: [0, 0])
    for recorded_at, user_count in rows.iterator():
        local = timezone.localtime(recorded_at, zone)
        if local.isoweekday() == today.isoweekday():
            buckets[local.hour][0] += user_count
            buckets[local.hour][1] += 1
    forecasts = []
    for hour, (total, samples) in sorted(buckets.items()):
        target = timezone.make_aware(datetime.combine(today, time(hour)), zone)
        if target > now:
            forecasts.append(SimpleNamespace(predicted_at=target,
                expected_count=round(total / samples, 1), sample_count=samples))
    return forecasts
