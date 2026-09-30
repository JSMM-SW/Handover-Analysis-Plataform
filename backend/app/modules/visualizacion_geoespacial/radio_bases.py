"""Experimental per-cell candidates, NOT surveyed tower locations.

Pure calculation: no database writes or external data. Each session stays
independent because the dataset has no operator identifier. Assume one operator
per session. A cell/sector candidate is not a unique physical tower/site.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from statistics import median

from .schemas import RadioBaseEstimate, RadioBaseSummary
from .constants import INVALID_NETWORK_ID

EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class EstimationParameters:
    # Experimental defaults, not telecom standards or a calibrated error model.
    max_accuracy_m: float = 50
    min_accuracy_m: float = 5
    spatial_bin_m: float = 10
    min_positions: int = 5
    min_extent_m: float = 50
    max_extent_m: float = 30000
    strongest_fraction: float = 0.20


DEFAULT_PARAMETERS = EstimationParameters()


def _identity(value):
    return value is not None and 0 < value < INVALID_NETWORK_ID


def estimate_radio_bases(points, parameters=DEFAULT_PARAMETERS):
    """Use already visually filtered measurements (never the handover-only list).

    Deduplicate repeated samples regardless of record id/time, aggregate 10 m
    spatial bins with medians, then use the strongest 20% (minimum 5 positions;
    include signal ties). Project locally to metres before weighting:
    w = 10**((RSSI - RSSI_max)/10) / max(accuracy, 5)**2.
    Dispersion is weighted RMS spread of selected bins, NOT location accuracy.
    """
    groups = defaultdict(list)
    excluded = Counter()
    for point in points:
        if point.execution_id is None or not _identity(point.node_id) or not _identity(point.cell_id):
            excluded['Sin identificadores válidos de sesión, nodo o celda'] += 1
        elif point.tecnologia not in (1, 2) or point.earfcn is None or not 0 <= point.earfcn < INVALID_NETWORK_ID:
            excluded['Sin tecnología o frecuencia válida'] += 1
        elif not (math.isfinite(point.latitud) and math.isfinite(point.longitud)
                  and -85 < point.latitud < 85 and -180 <= point.longitud <= 180
                  and (point.latitud, point.longitud) != (0, 0)):
            excluded['Sin coordenadas utilizables'] += 1
        elif point.rssi is None or not -150 <= point.rssi < 0:
            excluded['RSSI ausente o fuera del rango de cálculo'] += 1
        elif point.accuracy is None or not 0 < point.accuracy <= parameters.max_accuracy_m:
            excluded['Precisión GPS ausente o insuficiente'] += 1
        else:
            # PCI/PSC is optional metadata, not a globally unique grouping key.
            key = (str(point.execution_id), point.hoja_origen, point.tecnologia,
                   point.node_id, point.cell_id, point.earfcn, point.tac)
            groups[key].append(point)

    summary = RadioBaseSummary(grupos_evaluados=len(groups),
                              mediciones_descartadas=sum(excluded.values()),
                              motivos=dict(excluded), parametros=asdict(parameters))
    estimates = []
    for key, observations in sorted(groups.items(), key=lambda item: repr(item[0])):
        samples = sorted({(p.latitud, p.longitud, p.rssi, p.accuracy) for p in observations})
        summary.duplicados_descartados += len(observations) - len(samples)
        lat0 = sum(p[0] for p in samples) / len(samples)
        lon0 = sum(p[1] for p in samples) / len(samples)
        scale_x = EARTH_RADIUS_M * math.cos(math.radians(lat0))
        bins = defaultdict(list)
        for lat, lon, signal, accuracy in samples:
            x = math.radians(lon - lon0) * scale_x
            y = math.radians(lat - lat0) * EARTH_RADIUS_M
            bins[(math.floor(x / parameters.spatial_bin_m), math.floor(y / parameters.spatial_bin_m))].append((x, y, signal, accuracy))
        positions = [tuple(median(sample[i] for sample in bucket) for i in range(4))
                     for bucket in bins.values()]
        extent = math.hypot(max(p[0] for p in positions) - min(p[0] for p in positions),
                            max(p[1] for p in positions) - min(p[1] for p in positions))
        if len(positions) < parameters.min_positions or not parameters.min_extent_m <= extent <= parameters.max_extent_m:
            summary.grupos_insuficientes += 1
            continue
        positions.sort(key=lambda p: (-p[2], p[3], p[0], p[1]))
        keep = max(parameters.min_positions, math.ceil(len(positions) * parameters.strongest_fraction))
        cutoff = positions[min(keep, len(positions)) - 1][2]
        selected = [p for p in positions if p[2] >= cutoff]
        strongest = max(p[2] for p in selected)
        weights = [10 ** ((p[2] - strongest) / 10) / max(p[3], parameters.min_accuracy_m) ** 2
                   for p in selected]
        total_weight = sum(weights)
        x = sum(w * p[0] for w, p in zip(weights, selected)) / total_weight
        y = sum(w * p[1] for w, p in zip(weights, selected)) / total_weight
        dispersion = math.sqrt(sum(w * ((p[0] - x) ** 2 + (p[1] - y) ** 2)
                                   for w, p in zip(weights, selected)) / total_weight)
        psc_limit = 503 if key[2] == 1 else 511
        estimates.append(RadioBaseEstimate(
            id=sha256(json.dumps(key).encode()).hexdigest()[:24],
            execution_id=key[0], hoja_origen=key[1], tecnologia=key[2], node_id=key[3],
            cell_id=key[4], earfcn=key[5], tac=key[6],
            psc_pci=sorted({p.psc_pci for p in observations if p.psc_pci is not None and 0 <= p.psc_pci <= psc_limit}),
            latitud=round(lat0 + math.degrees(y / EARTH_RADIUS_M), 7),
            longitud=round(lon0 + math.degrees(x / scale_x), 7),
            mediciones_validas=len(samples), posiciones_disponibles=len(positions),
            posiciones_utilizadas=len(selected), rssi_max=strongest,
            dispersion_m=round(dispersion, 2),
        ))
    return estimates, summary
