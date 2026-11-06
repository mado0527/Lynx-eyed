"""Read-only hourly forecasts from historical observations."""
from datetime import datetime, time
from types import SimpleNamespace

from django.db.models import Avg, Count
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.utils import timezone

from .models import CrowdLog


def hourly_averages(location, now):
    zone = timezone.get_current_timezone()
    today = timezone.localdate(now)
    start = timezone.make_aware(datetime.combine(today, time.min), zone)
    rows = (CrowdLog.objects.filter(location=location, recorded_at__lt=start, user_count__gte=0)
            .annotate(weekday=ExtractIsoWeekDay('recorded_at', tzinfo=zone),
                      hour=ExtractHour('recorded_at', tzinfo=zone))
            .filter(weekday=today.isoweekday()).order_by().values('hour')
            .annotate(mean=Avg('user_count'), samples=Count('pk')).order_by('hour'))
    forecasts = []
    for row in rows:
        target = timezone.make_aware(datetime.combine(today, time(row['hour'])), zone)
        if target > now:
            forecasts.append(SimpleNamespace(predicted_at=target,
                expected_count=round(row['mean'], 1), sample_count=row['samples']))
    return forecasts
