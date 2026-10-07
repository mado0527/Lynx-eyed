"""Display geometry for saved values only; this module does not forecast."""
from django.utils import timezone


def smooth_path(points):
    """Monotone cubic interpolation without overshooting saved counts."""
    if not points:
        return ''
    path = f"M {points[0]['x']:.6f} {points[0]['y']:.6f}"
    if len(points) == 1:
        return path
    widths = [b['x'] - a['x'] for a, b in zip(points, points[1:])]
    slopes = [(b['y'] - a['y']) / h for a, b, h in zip(points, points[1:], widths)]
    tangents = [slopes[0]]
    for i in range(1, len(points) - 1):
        before, after = slopes[i - 1], slopes[i]
        if before * after <= 0:
            tangents.append(0)
        else:
            w1, w2 = 2 * widths[i] + widths[i - 1], widths[i] + 2 * widths[i - 1]
            tangents.append((w1 + w2) / (w1 / before + w2 / after))
    tangents.append(slopes[-1])
    for i, (a, b, h) in enumerate(zip(points, points[1:], widths)):
        path += (f" C {a['x'] + h / 3:.6f} {a['y'] + tangents[i] * h / 3:.6f}"
                 f" {b['x'] - h / 3:.6f} {b['y'] - tangents[i + 1] * h / 3:.6f}"
                 f" {b['x']:.6f} {b['y']:.6f}")
    return path


def chart_series(records, time_field, count_field, start_hour, end_hour, ceiling):
    points = []
    for row in records:
        at = timezone.localtime(getattr(row, time_field))
        hour = at.hour + at.minute / 60 + at.second / 3600 + at.microsecond / 3_600_000_000
        left = (hour - start_hour) / (end_hour - start_hour) * 100
        top = (1 - getattr(row, count_field) / ceiling) * 100
        points.append({'record': row, 'at': at, 'count': getattr(row, count_field),
                       'left': left, 'top': top, 'x': left * 10, 'y': top * 10,
                       'edge': 'edge-left' if left < 20 else 'edge-right' if left > 80 else ''})
    return points, smooth_path(points)
