"""Read-only weekday/time-slot averages of the stored observation records."""
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.utils import timezone

from .calculations import calculate_crowd_rate
from .models import CrowdLog


SCHOOL_PERIODS = (
    ('1限', time(9, 10), time(10, 40)),
    ('休憩', time(10, 40), time(10, 50)),
    ('2限', time(10, 50), time(12, 20)),
    ('昼休み', time(12, 20), time(13, 20)),
    ('3限', time(13, 20), time(14, 50)),
    ('休憩', time(14, 50), time(15)),
    ('4限', time(15), time(16, 30)),
)

def selected_tendency(location, start_date, end_date, now, periods, weekday, slot):
    """Reuse daily-weighted aggregates for the summary and five-minute trend."""
    row = weekday_time_grid(location, start_date, end_date, now, periods)['time_rows'][slot]
    cell = row['cells'][weekday - 1]
    begins, finishes = row['start'], row['end']
    anchor = datetime.combine(start_date, begins)
    stop = datetime.combine(start_date, finishes)
    bins = []
    while anchor < stop:
        following = min(anchor + timedelta(minutes=5), stop)
        bins.append((anchor.strftime('%H:%M'), anchor.time(), following.time()))
        anchor = following
    grid = weekday_time_grid(location, start_date, end_date, now, bins)
    points = []
    for bucket in grid['time_rows']:
        value = bucket['cells'][weekday - 1]
        points.append({'time': bucket['label'], 'average': value['average'],
                       'days': value['observed_days'], 'samples': value['samples']})
    return {**cell, 'start': begins.strftime('%H:%M'), 'end': finishes.strftime('%H:%M'),
            'label': row['label'], 'points': points}


def weekday_time_grid(location, start_date, end_date, now, periods):
    """Average within each day/slot first, then give each observed day equal weight.

    ``periods`` contains (label, start_time, end_time) tuples. The beginning is
    included and the end excluded, so a boundary belongs to only the next slot.
    Missing days are not zeroes. Successful zero-person observations are valid.
    """
    zone = ZoneInfo('Asia/Tokyo')
    start = timezone.make_aware(datetime.combine(start_date, time.min), zone)
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), zone)
    daily = {}
    sources = defaultdict(lambda: defaultdict(int))
    observed_dates = set()
    if location:
        records = (CrowdLog.objects.filter(location=location, user_count__gte=0,
                   recorded_at__gte=start, recorded_at__lt=end, recorded_at__lte=now)
                   .order_by('recorded_at', '-log_id')
                   .values_list('recorded_at', 'user_count', 'source'))
        previous_at = None
        for recorded_at, count, source in records.iterator():
            # For an identical timestamp, the largest ID is the adopted record.
            if recorded_at == previous_at:
                continue
            previous_at = recorded_at
            local_at = timezone.localtime(recorded_at, zone)
            weekday = local_at.isoweekday()
            if weekday > 5:
                continue
            for index, (_, begins, finishes) in enumerate(periods):
                if begins <= local_at.time() < finishes:
                    key = (local_at.date(), index)
                    total, samples = daily.get(key, (0, 0))
                    daily[key] = (total + count, samples + 1)
                    sources[index, weekday][source] += 1
                    observed_dates.add(local_at.date())
                    break

    averages = defaultdict(list)
    for (day, index), (total, samples) in daily.items():
        averages[index, day.isoweekday()].append(Decimal(total) / samples)

    rows = []
    for index, (label, begins, finishes) in enumerate(periods):
        cells = []
        for weekday, day_label in enumerate('月火水木金', 1):
            values = averages[index, weekday]
            average = sum(values, Decimal(0)) / len(values) if values else None
            occupancy = calculate_crowd_rate(average, location.capacity) if average is not None else None
            state, status = 'unknown', '未計測'
            if average is not None:
                if occupancy is None:
                    status = '混雑率は算出不可'
                elif occupancy < 31:
                    state, status = 'low', '空いています'
                elif occupancy <= 75:
                    state, status = 'moderate', 'やや混雑しています'
                else:
                    state, status = 'high', '混雑しています'
            provenance = sources[index, weekday]
            cells.append({
                'day': day_label, 'measured': average is not None,
                'average': average.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP) if values else None,
                'occupancy': occupancy, 'state': state, 'status': status,
                'observed_days': len(values), 'samples': sum(provenance.values()),
                'contains_dummy': bool(provenance.get('dummy')),
                'contains_unknown': any(count for source, count in provenance.items()
                                        if source not in ('camera', 'dummy')),
            })
        rows.append({'label': label, 'start': begins, 'end': finishes, 'cells': cells})

    all_cells = [cell for row in rows for cell in row['cells']]
    return {
        'time_rows': rows, 'weekdays': list('月火水木金'),
        'samples': sum(cell['samples'] for cell in all_cells),
        'observed_days': len(observed_dates),
        'contains_dummy': any(cell['contains_dummy'] for cell in all_cells),
        'contains_unknown': any(cell['contains_unknown'] for cell in all_cells),
    }
