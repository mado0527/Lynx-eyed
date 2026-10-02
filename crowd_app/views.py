from django.shortcuts import render
from django.views.decorators.cache import never_cache
from .calculations import calculate_crowd_rate

from .models import CrowdLog, LocationMaster


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
    })
