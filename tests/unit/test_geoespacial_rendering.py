from datetime import datetime, timezone
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Event

import pytest

from app.modules.visualizacion_geoespacial.constants import MAX_MAP_POINTS, MAX_EVENT_MARKERS
from app.modules.visualizacion_geoespacial.schemas import MapData, Measurement, HandoverEvent, RadioBaseEstimate
from app.modules.visualizacion_geoespacial.rendering import render_map
from app.modules.visualizacion_geoespacial.analysis_cache import AnalysisCache


def dataset(count):
    points = [Measurement(id_registro=UUID(int=index + 1), execution_id=UUID(int=1000000),
                          timestamp_medicion=datetime(2026, 5, 5, 13, tzinfo=timezone.utc),
                          latitud=-0.2 + index * 0.000001, longitud=-78.5 + index * 0.000001,
                          cell_id=10, tecnologia=1, hoja_origen=None, rssi=-90 if index % 3 == 0 else -60,
                          rsrq=None if index % 2 else -12) for index in range(count)]
    return MapData(mediciones=points, tramos=[[p.id_registro for p in points]], total=count,
                   handovers=[], total_handovers=0, advertencias=[])


def test_large_analysis_keeps_every_individual_signal_sample_and_bounded_routes():
    data = dataset(60001)
    original = data.mediciones
    result = render_map(data)
    assert result.total == 60001
    assert result.mapa_resumido
    assert len(result.mediciones) <= MAX_MAP_POINTS
    assert len(result.senales) == 60001
    assert len({sample[6] for sample in result.senales}) == 60001
    for point, sample in zip(original, result.senales):
        assert sample == (point.latitud, point.longitud, point.rssi, point.rsrp,
                          point.rsrq, point.rssnr, point.id_registro,
                          point.timestamp_medicion, point.cell_id)
    for metric in ('rssi', 'rsrq'):
        values = [getattr(p, metric) for p in original if getattr(p, metric) is not None]
        assert result.promedios[metric] == pytest.approx(sum(values) / len(values))
    assert result.tramos[0][0] == original[0].id_registro
    assert result.tramos[0][-1] == original[-1].id_registro


def test_zoom_and_viewport_change_representation_without_changing_statistics():
    source = dataset(7000)
    coarse = render_map(source.model_copy(), zoom=6)
    detailed = render_map(source.model_copy(), zoom=18, bounds=(-78.5, -0.2, -78.499, -0.199))
    assert coarse.total == detailed.total == 7000
    assert coarse.promedios == detailed.promedios
    assert coarse.limites == detailed.limites
    assert len(coarse.senales) == 7000
    assert 0 < len(detailed.senales) < 7000
    assert {sample[6] for sample in detailed.senales} <= {sample[6] for sample in coarse.senales}


def test_many_handovers_are_grouped_but_the_total_is_preserved():
    data = dataset(3500)
    data.handovers = [HandoverEvent(**point.model_dump(), registro_anterior_id=UUID(int=900000),
                                   celda_origen=5, nodo_origen=None) for point in data.mediciones[:2000]]
    data.total_handovers = data.handovers_con_ubicacion = 2000
    result = render_map(data, zoom=12)
    assert result.total_handovers == result.handovers_con_ubicacion == 2000
    assert len(result.grupos_handovers) <= MAX_EVENT_MARKERS
    assert sum(group['cantidad'] for group in result.grupos_handovers) == 2000
    assert result.handovers == []


def test_cache_retains_full_resolution_after_rendering_and_respects_budget():
    cache = AnalysisCache(point_budget=8000)
    calls = []
    def load():
        calls.append(1)
        return dataset(7000)
    render_map(cache.get_or_load('a', load))
    second = cache.get_or_load('a', load)
    assert len(second.mediciones) == 7000
    assert calls == [1]
    cache.get_or_load('b', load)
    assert len(cache.entries) == 1
    assert 'b' in cache.entries


def test_small_dataset_remains_exact_and_handles_empty_data():
    data = dataset(3)
    assert not render_map(data).mapa_resumido
    assert len(data.mediciones) == 3
    assert data.promedios['rssi'] == -70
    assert render_map(dataset(0)).total == 0


def test_cache_budget_does_not_reject_or_truncate_an_analysis():
    cache = AnalysisCache(point_budget=1)
    result = cache.get_or_load('large', lambda: dataset(7000))
    assert result.total == len(result.mediciones) == 7000
    assert not cache.entries


def test_many_radio_estimates_keep_total_when_grouped():
    data = dataset(5500)
    data.radios_base = [RadioBaseEstimate(
        id=str(i), execution_id=UUID(int=1000000), hoja_origen=None, node_id=1, cell_id=i + 1,
        tecnologia=1, earfcn=100, tac=1, psc_pci=[1], latitud=-0.2, longitud=-78.5,
        mediciones_validas=5, posiciones_disponibles=5, posiciones_utilizadas=5,
        rssi_max=-70, dispersion_m=10) for i in range(1001)]
    result = render_map(data)
    assert result.total_radios_base == 1001
    assert result.radios_base == []
    assert sum(group['cantidad'] for group in result.grupos_radios_base) == 1001


def test_concurrent_requests_share_one_analysis_even_without_storage_budget(monkeypatch):
    started, waiting, release = Event(), Event(), Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout)
    monkeypatch.setattr('app.modules.visualizacion_geoespacial.analysis_cache.Future', ObservedFuture)
    cache = AnalysisCache(point_budget=1)
    calls = []
    def load():
        calls.append(1)
        started.set()
        assert release.wait(10)
        return dataset(3)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(cache.get_or_load, 'a', load)
        assert started.wait(10)
        second = executor.submit(cache.get_or_load, 'a', load)
        try:
            assert waiting.wait(10)
        finally:
            release.set()
        assert first.result().total == second.result().total == 3
    assert calls == [1]
    assert not cache.pending


def test_failed_analysis_does_not_poison_cache_or_leave_waiters_pending():
    cache = AnalysisCache()
    def fail():
        raise ValueError('fallo temporal')
    with pytest.raises(ValueError):
        cache.get_or_load('a', fail)
    assert not cache.pending
    assert cache.get_or_load('a', lambda: dataset(3)).total == 3
