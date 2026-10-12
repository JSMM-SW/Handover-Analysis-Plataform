import { useEffect, useMemo, useRef, useState } from 'react';
import { downloadMap } from '../exportMap';
import useMeasurements from '../hooks/useMeasurements';
import MapaGeoespacial from './MapaGeoespacial';
import RadioBaseSummary from './RadioBaseSummary';
import SignalLegend from './SignalLegend';
import HandoverDetail from './HandoverDetail';
import { MapTabs, MapToolbar } from './MapControls';
import { sessionExportLabel } from '../../../shared/sessionNames';
import FiltersPanel from './FiltersPanel';
import { getGeo } from '../api';
import SelectorFecha from '../../visualizacion_temporal/components/SelectorFecha';
import { availableHours } from '../availableHours';
import '../../visualizacion_temporal/VisualizacionTemporalPage.css';

const EMPTY_FILTERS = Object.freeze({ desde: '', hasta: '', hora_inicio: '', hora_fin: '', tecnologia: '' });

function sessionFilters(days) {
  const next = { ...EMPTY_FILTERS, desde: days[0]?.fecha ?? '', hasta: days.at(-1)?.fecha ?? '' };
  const hours = availableHours(days, next.desde, next.hasta);
  return { ...next, hora_inicio: hours.inicios[0]?.valor ?? '', hora_fin: hours.fines.at(-1)?.valor ?? '' };
}
const LAYER_STORAGE_KEY = 'geo-event-layers';
const DEFAULT_LAYERS = Object.freeze({ handovers: true, rutas: true, radiosBase: false });
const HEAT_STATS = [
  { key: 'rsrp', label: 'RSRP promedio', unit: 'dBm' },
  { key: 'rsrq', label: 'RSRQ promedio', unit: 'dB' },
  { key: 'rssnr', label: 'RSSNR promedio', unit: 'dB' },
  { key: 'rssi', label: 'RSSI promedio', unit: 'dBm' },
];

function averageParameter(points, key, unit) {
  const values = (points ?? []).map((point) => point[key]).filter(Number.isFinite);
  if (!values.length) return '—';
  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  return `${average.toLocaleString('es-EC', { maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`;
}

function loadLayers() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(LAYER_STORAGE_KEY) || '{}');
    return Object.fromEntries(Object.entries(DEFAULT_LAYERS).map(([key, value]) => [
      key, typeof saved?.[key] === 'boolean' ? saved[key] : value,
    ]));
  } catch {
    return { ...DEFAULT_LAYERS };
  }
}

export default function DatasetView({ executionIds, executions, selector }) {
  const exportArea = useRef(null);
  const exportBusy = useRef(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [query, setQuery] = useState(EMPTY_FILTERS);
  const [availability, setAvailability] = useState(null);
  const [availabilityError, setAvailabilityError] = useState('');
  const days = availability?.executionIds === executionIds ? availability.days : [];
  const loadingDays = availability?.executionIds !== executionIds && !availabilityError;
  const hours = availableHours(days, filters.desde, filters.hasta);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState('rutas');
  const [heatMetric, setHeatMetric] = useState('rssi');
  const [showHeatHandovers, setShowHeatHandovers] = useState(false);
  const [layers, setLayers] = useState(loadLayers);
  const { data, loading, error } = useMeasurements(executionIds, query);

  useEffect(() => {
    const controller = new AbortController();
    getGeo('disponibilidad', { execution_id: executionIds }, controller.signal)
      .then((days) => {
        if (controller.signal.aborted) return;
        const next = sessionFilters(days);
        setAvailability({ executionIds, days });
        setAvailabilityError('');
        setFilters(next);
        setQuery(next);
        setSelected(null);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setAvailabilityError(error.message);
      });
    return () => controller.abort();
  }, [executionIds]);

  useEffect(() => {
    try { sessionStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify(layers)); }
    catch { /* Layer preferences are optional when storage is unavailable. */ }
  }, [layers]);

  // Keep Leaflet layers stable when editing filters or opening a detail.
  const mapLayers = useMemo(() => tab === 'calor'
    ? { rutas: true, blackHandovers: showHeatHandovers, signalMetric: heatMetric }
    : { ...layers, signalMetric: null }, [tab, heatMetric, layers, showHeatHandovers]);
  const averageSignal = averageParameter(data?.mediciones, 'rssi', 'dBm');
  const shownSelected = selected && data?.handovers?.find((point) => point.id_registro === selected.id_registro);

  function applyFilters(next) {
    setFilters(next);
    setQuery({ ...next });
    setSelected(null);
    setExportError('');
  }

  function changeTab(value) {
    setTab(value);
    setSelected(null);
    setExportError('');
  }

  async function exportCurrentMap() {
    if (exportBusy.current || !data?.total) return;
    exportBusy.current = true;
    setExporting(true);
    setExportError('');
    try {
      await downloadMap(exportArea.current, {
        tab,
        heatMetric,
        sessionLabels: executionIds.map((id) => sessionExportLabel(executions.find((row) => row.execution_id === id) ?? { execution_id: id })),
      });
    } catch (error) {
      setExportError(error.name === 'SecurityError'
        ? 'El mapa base no permite exportar sus imágenes. Recarga la página y vuelve a intentar.'
        : error.message || 'No se pudo descargar el mapa. Vuelve a intentar.');
    } finally {
      exportBusy.current = false;
      setExporting(false);
    }
  }

  function changeFilter(event) {
    setFilters((old) => ({ ...old, [event.target.name]: event.target.value }));
  }

  function changeDate(key, value) {
    setFilters((old) => {
      const next = { ...old, [key]: value };
      const available = availableHours(days, next.desde, next.hasta);
      return { ...next, hora_inicio: available.inicios[0]?.valor ?? '', hora_fin: available.fines.at(-1)?.valor ?? '' };
    });
  }

  return (
    <div className="geo-workspace" inert={exporting} aria-busy={exporting}>
      <FiltersPanel selector={selector}>
        <form className="geo-filters" onSubmit={(event) => { event.preventDefault(); applyFilters(filters); }}>
          <div className="geo-date-field"><span>Desde</span><SelectorFecha etiqueta="Fecha de inicio" valor={filters.desde} dias={days} max={filters.hasta} cargando={loadingDays} mostrarHandovers={false} onCambio={(desde) => changeDate('desde', desde)} /></div>
          <div className="geo-date-field"><span>Hasta</span><SelectorFecha etiqueta="Fecha de fin" valor={filters.hasta} dias={days} min={filters.desde} cargando={loadingDays} mostrarHandovers={false} onCambio={(hasta) => changeDate('hasta', hasta)} /></div>
          <div className="geo-hour-field"><span>Franja horaria</span><div className="geo-hour-range">
            <select aria-label="Franja horaria: desde" name="hora_inicio" value={filters.hora_inicio} onChange={changeFilter} disabled={!hours.inicios.length}>
              <option value="">Desde…</option>
              {hours.inicios.filter((hour) => !filters.hora_fin || hour.valor <= filters.hora_fin).map((hour) => <option key={hour.valor} value={hour.valor}>{hour.etiqueta}</option>)}
            </select><span aria-hidden="true">–</span>
            <select aria-label="Franja horaria: hasta" name="hora_fin" value={filters.hora_fin} onChange={changeFilter} disabled={!hours.fines.length}>
              <option value="">Hasta…</option>
              {hours.fines.filter((hour) => !filters.hora_inicio || hour.valor >= filters.hora_inicio).map((hour) => <option key={hour.valor} value={hour.valor}>{hour.etiqueta}</option>)}
            </select>
          </div></div>
          <label>
            Tecnología
            <select name="tecnologia" value={filters.tecnologia} onChange={changeFilter}>
              <option value="">Todas</option>
              <option value="1">LTE / 4G</option>
              <option value="2">3G / UMTS</option>
              <option value="3">2G / GSM</option>
              <option value="0">Sin señal</option>
            </select>
          </label>
          <div className="geo-filter-actions">
            <button className="geo-primary" type="submit">Aplicar filtros</button>
            <button type="button" onClick={() => applyFilters(sessionFilters(days))}>Limpiar</button>
          </div>
        </form>
        {availabilityError && <p role="alert" className="geo-error">{availabilityError}</p>}
      </FiltersPanel>
      <section className="geo-results">
        <MapTabs tab={tab} onChange={changeTab} />
        <div id="geo-map-panel" role="tabpanel" aria-labelledby={`geo-tab-${tab}`}>
          <div className={`geo-stats${tab === 'calor' ? ' geo-stats-heat' : ''}`}>
            {tab === 'rutas' && <div><strong>{data ? data.total.toLocaleString('es-EC') : '—'}</strong><span>Datos analizados</span></div>}
            <div><strong>{data ? data.total_handovers : '—'}</strong><span>Handovers</span></div>
            {tab === 'calor' ? HEAT_STATS.map(({ key, label, unit }) => (
              <div key={key} title="Promedio de los valores disponibles en las mediciones filtradas">
                <strong>{averageParameter(data?.mediciones, key, unit)}</strong><span>{label}</span>
              </div>
            )) : <div><strong>{averageSignal}</strong><span>RSSI promedio</span></div>}
          </div>
          {data && data.total_handovers > 0 && (
            <p className="geo-handover-coverage" role="status">
              {data.total_handovers} handovers detectados · {data.handovers_con_ubicacion ?? data.handovers.length} con ubicación · {data.handovers_sin_ubicacion ?? Math.max(0, data.total_handovers - data.handovers.length)} sin ubicación
            </p>
          )}
          <MapToolbar
            tab={tab}
            layers={layers}
            onLayerChange={(key, checked) => setLayers((old) => ({ ...old, [key]: checked }))}
            heatMetric={heatMetric}
            onHeatChange={setHeatMetric}
            showHeatHandovers={showHeatHandovers}
            onHeatHandoversChange={setShowHeatHandovers}
            exporting={exporting}
            canExport={!loading && Boolean(data?.total)}
            onExport={exportCurrentMap}
          />
          {exportError && <p className="geo-error" role="alert">{exportError}</p>}
          {mapLayers.radiosBase && data && <RadioBaseSummary data={data} />}
          {loading && <p role="status" className="geo-empty">Consultando mediciones…</p>}
          {!loading && error && <p role="alert" className="geo-error">{error}</p>}
          {data?.total === 0 && <p role="status" className="geo-empty">No hay mediciones que coincidan con estos filtros.</p>}
          {data?.total > 0 && data.total_handovers === 0 && (
            <p role="status" className="geo-empty">No se detectaron handovers con el detector de Temporal en estos datos.</p>
          )}
          <div className="geo-export" ref={exportArea}>
            <MapaGeoespacial
              data={data}
              layers={mapLayers}
              onSelect={setSelected}
              executions={executions}
            />
            <SignalLegend metric={tab === 'rutas' ? 'rssi' : heatMetric} aggregated={tab === 'calor'} />
          </div>
          {shownSelected && <HandoverDetail event={shownSelected} onClose={() => setSelected(null)} />}
        </div>
      </section>
    </div>
  );
}
