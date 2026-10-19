"""Bound browser work without imposing a limit on analytical measurements.

Signal samples preserve individual measurements. Route breaks and session
boundaries survive simplification; original detail fields remain available
through the detail endpoint.
"""
import math
from collections import defaultdict

from .constants import MAX_MAP_POINTS, MAX_EVENT_MARKERS

METRICS = ('rssi', 'rsrp', 'rsrq', 'rssnr')


def project(point, zoom):
    latitude = max(-85.05112878, min(85.05112878, point.latitud))
    scale = 256 * 2 ** zoom
    sin_lat = math.sin(math.radians(latitude))
    return ((point.longitud + 180) / 360 * scale,
            (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale)


def simplify(points, zoom, tolerance=2):
    """Iterative Douglas–Peucker in Web Mercator screen pixels."""
    if len(points) < 3:
        return points
    # Bound the quadratic worst case of Douglas–Peucker on GPS noise.
    if len(points) > MAX_MAP_POINTS * 2:
        count = MAX_MAP_POINTS * 2
        points = [points[round(i * (len(points) - 1) / (count - 1))] for i in range(count)]
    coords = [project(point, zoom) for point in points]
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        ax, ay = coords[start]
        bx, by = coords[end]
        dx, dy = bx - ax, by - ay
        squared = dx * dx + dy * dy
        maximum, index = tolerance * tolerance, None
        for i in range(start + 1, end):
            x, y = coords[i]
            fraction = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / squared)) if squared else 0
            distance = (x - ax - fraction * dx) ** 2 + (y - ay - fraction * dy) ** 2
            if distance > maximum:
                maximum, index = distance, i
        if index is not None:
            keep.add(index)
            stack.extend(((start, index), (index, end)))
    return [points[index] for index in sorted(keep)]


def grid_groups(points, zoom, budget):
    cell_size = 16
    while True:
        groups = defaultdict(list)
        for point in points:
            x, y = project(point, zoom)
            groups[(math.floor(x / cell_size), math.floor(y / cell_size))].append(point)
        if len(groups) <= budget:
            return list(groups.values())
        cell_size *= 2


def in_view(point, bounds, zoom):
    if bounds is None:
        return True
    # Include a kernel margin around the viewport to avoid heat seams.
    margin = 360 * 96 / (256 * 2 ** zoom)
    west, south, east, north = bounds
    return west - margin <= point.longitud <= east + margin and south - margin <= point.latitud <= north + margin


def summarize(data):
    """Compute statistics once on the complete analysis, before caching."""
    points = data.mediciones
    data.total_radios_base = len(data.radios_base)
    averages = {}
    for metric in METRICS:
        values = [getattr(point, metric) for point in points if getattr(point, metric) is not None]
        averages[metric] = sum(values) / len(values) if values else None
    data.promedios = averages
    if not points:
        return
    south, north = min(p.latitud for p in points), max(p.latitud for p in points)
    west, east = min(p.longitud for p in points), max(p.longitud for p in points)
    data.limites = [[south, west], [north, east]]


def render_map(data, zoom=None, bounds=None):
    """Statistics use all filtered GPS measurements, irrespective of viewport."""
    points = data.mediciones
    if not data.promedios:
        summarize(data)
    if not points:
        return data
    (south, west), (north, east) = data.limites
    if (len(points) <= MAX_MAP_POINTS and len(data.handovers) <= MAX_EVENT_MARKERS
            and len(data.radios_base) <= MAX_EVENT_MARKERS):
        return data

    data.mapa_resumido = True
    if zoom is None:
        a, b = project(points[0].model_copy(update={'latitud': south, 'longitud': west}), 0), project(points[0].model_copy(update={'latitud': north, 'longitud': east}), 0)
        zoom = max(0, min(18, math.floor(math.log2(min(1000 / max(abs(b[0] - a[0]), 0.001), 500 / max(abs(b[1] - a[1]), 0.001))))))
    visible = [point for point in points if in_view(point, bounds, zoom)]
    data.senales = [(p.latitud, p.longitud, p.rssi, p.rsrp, p.rsrq, p.rssnr,
                     p.id_registro, p.timestamp_medicion, p.cell_id) for p in visible]

    by_id = {point.id_registro: point for point in points}
    routes = []
    for segment in data.tramos:
        # Keep neighboring outside points where a route enters/leaves the view.
        chunk = []
        for previous, current in zip(segment, segment[1:]):
            a, b = by_id[previous], by_id[current]
            intersects = bounds is None or not (
                max(a.longitud, b.longitud) < bounds[0] or min(a.longitud, b.longitud) > bounds[2]
                or max(a.latitud, b.latitud) < bounds[1] or min(a.latitud, b.latitud) > bounds[3])
            if intersects:
                if not chunk:
                    chunk.append(a)
                chunk.append(b)
            elif chunk:
                routes.append(simplify(chunk, zoom))
                chunk = []
        if chunk:
            routes.append(simplify(chunk, zoom))
    # A secondary budget also handles noisy GPS paths and many disjoint routes.
    total = sum(map(len, routes))
    retained, segments = {}, []
    remaining = MAX_MAP_POINTS
    for route in sorted(routes, key=len, reverse=True):
        if remaining < 2:
            break
        count = min(len(route), remaining, max(2, math.floor(MAX_MAP_POINTS * len(route) / max(total, 1))))
        sampled = [route[round(i * (len(route) - 1) / (count - 1))] for i in range(count)]
        segments.append([p.id_registro for p in sampled])
        retained.update((p.id_registro, p) for p in sampled)
        remaining -= count
    data.mediciones = list(retained.values())
    data.tramos = segments
    data.tramos_omitidos = len(routes) - len(segments)
    # Single observations have no trajectory: keep a bounded representative set.
    if not retained:
        data.mediciones = [by_id[p.id_registro] for p in visible[:MAX_MAP_POINTS]]
    events = [event for event in data.handovers if in_view(event, bounds, zoom)]
    if len(events) > MAX_EVENT_MARKERS:
        data.grupos_handovers = [{
            'latitud': sum(p.latitud for p in group) / len(group),
            'longitud': sum(p.longitud for p in group) / len(group),
            'cantidad': len(group), 'id_registro': str(group[0].id_registro),
            'limites': [[min(p.latitud for p in group), min(p.longitud for p in group)],
                        [max(p.latitud for p in group), max(p.longitud for p in group)]],
        } for group in grid_groups(events, zoom, MAX_EVENT_MARKERS)]
        data.handovers = []
    else:
        data.handovers = events
    stations = [station for station in data.radios_base if in_view(station, bounds, zoom)]
    if len(stations) > MAX_EVENT_MARKERS:
        data.grupos_radios_base = [{
            'latitud': sum(p.latitud for p in group) / len(group),
            'longitud': sum(p.longitud for p in group) / len(group),
            'cantidad': len(group), 'ejemplo': group[0].model_dump(mode='json'),
            'limites': [[min(p.latitud for p in group), min(p.longitud for p in group)],
                        [max(p.latitud for p in group), max(p.longitud for p in group)]],
        } for group in grid_groups(stations, zoom, MAX_EVENT_MARKERS)]
        data.radios_base = []
    else:
        data.radios_base = stations
    return data
