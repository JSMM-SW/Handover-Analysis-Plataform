import { useEffect, useMemo, useRef, useState } from 'react';
import { downloadMap } from '../exportMap';
import useMeasurements from '../hooks/useMeasurements';
import MapaGeoespacial from './MapaGeoespacial';
import RadioBaseSummary from './RadioBaseSummary';
import SignalLegend from './SignalLegend';
import HandoverDetail from './HandoverDetail';
import { MapTabs, MapToolbar } from './MapControls';
import { sessionExportLabel } from '../../../shared/sessionNames';

const EMPTY_FILTERS = Object.freeze({ desde: '', hasta: '', tecnologia: '', bbox: '' });
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
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState('rutas');
  const [heatMetric, setHeatMetric] = useState('handovers');
  const [layers, setLayers] = useState(loadLayers);
  const { data, loading, error } = useMeasurements(executionIds, query);

  useEffect(() => {
    try { sessionStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify(layers)); }
    catch { /* Layer preferences are optional when storage is unavailable. */ }
  }, [layers]);

  // Keep Leaflet layers stable when editing filters or opening a detail.
  const mapLayers = useMemo(() => tab === 'calor'
    ? { calor: heatMetric === 'handovers', signalMetric: heatMetric === 'handovers' ? null : heatMetric }
    : { ...layers, calor: false, signalMetric: null }, [tab, heatMetric, layers]);
  const signalPoints = data?.mediciones.filter((point) => point.rssi != null) || [];
  const averageSignal = signalPoints.length
    ? `${Math.round(signalPoints.reduce((sum, point) => sum + point.rssi, 0) / signalPoints.length)} dBm`
    : '—';
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

  return (
    <div className="geo-workspace" inert={exporting} aria-busy={exporting}>
      <aside className="geo-filter-panel" aria-label="Filtros geoespaciales">
        <h2>Filtros</h2>
        {selector}
        <form className="geo-filters" onSubmit={(event) => { event.preventDefault(); applyFilters(filters); }}>
          <label>Desde <input name="desde" type="datetime-local" step="60" value={filters.desde} onChange={changeFilter} /></label>
          <label>Hasta <input name="hasta" type="datetime-local" step="60" min={filters.desde || undefined} value={filters.hasta} onChange={changeFilter} /></label>
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
          <button className="geo-primary" type="submit">Aplicar filtros</button>
          <button type="button" onClick={() => applyFilters(EMPTY_FILTERS)}>Limpiar</button>
        </form>
      </aside>
      <section className="geo-results">
        <MapTabs tab={tab} onChange={changeTab} />
        <div id="geo-map-panel" role="tabpanel" aria-labelledby={`geo-tab-${tab}`}>
          <div className={`geo-stats${tab === 'calor' ? ' geo-stats-heat' : ''}`}>
            {tab === 'rutas' && <div><strong>{data ? data.total.toLocaleString('es-EC') : '—'}</strong><span>Datos analizados</span></div>}
            <div><strong>{data ? data.total_handovers : '—'}</strong><span>Handovers</span></div>
            {tab === 'calor' ? HEAT_STATS.map(({ key, label, unit }) => (
              <div key={key} title="Promedio de los valores disponibles en los handovers filtrados">
                <strong>{averageParameter(data?.handovers, key, unit)}</strong><span>{label}</span>
              </div>
            )) : <div><strong>{averageSignal}</strong><span>RSSI promedio</span></div>}
          </div>
          <MapToolbar
            tab={tab}
            layers={layers}
            onLayerChange={(key, checked) => setLayers((old) => ({ ...old, [key]: checked }))}
            heatMetric={heatMetric}
            onHeatChange={setHeatMetric}
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
            <p role="status" className="geo-empty">No se detectaron handovers con la regla de cambio de celda y nodo en estos datos.</p>
          )}
          <div className="geo-export" ref={exportArea}>
            <MapaGeoespacial
              data={data}
              layers={mapLayers}
              onSelect={setSelected}
              onZone={(bbox) => applyFilters({ ...query, bbox })}
              executions={executions}
            />
            {tab === 'rutas' || heatMetric !== 'handovers' ? (
              <SignalLegend metric={tab === 'rutas' ? 'rssi' : heatMetric} aggregated={tab === 'calor'} />
            ) : (
              <div className="geo-legend geo-heat-legend"><i />Azul → rojo: menor → mayor concentración relativa.</div>
            )}
          </div>
          {shownSelected && <HandoverDetail event={shownSelected} onClose={() => setSelected(null)} />}
        </div>
      </section>
    </div>
  );
}
