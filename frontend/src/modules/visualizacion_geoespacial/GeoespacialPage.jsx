import { useEffect, useRef, useState } from 'react';
import { getGeo } from './api';
import MapaGeoespacial from './components/MapaGeoespacial';
import RadioBaseSummary from './components/RadioBaseSummary';
import './GeoespacialPage.css';

const formatTime = (value) => new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'America/Guayaquil' }).format(new Date(value));
const formatRange = (value) => new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Guayaquil' }).format(new Date(value));
const sessionName = (row) => `handover_record_${row.execution_id}.csv`;
const emptyFilters = { desde: '', hasta: '', tecnologia: '', bbox: '' };

export default function GeoespacialPage() {
  const [executions, setExecutions] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [error, setError] = useState('');
  const [analysis, setAnalysis] = useState({ ids: [], version: 0 });
  useEffect(() => {
    const controller = new AbortController();
    getGeo('ejecuciones', {}, controller.signal).then((rows) => {
      setExecutions(rows);
      setSelectedIds((old) => old.filter((id) => rows.some((r) => r.execution_id === id)));
      setError('');
    }).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, []);
  const chosen = executions?.filter((row) => selectedIds.includes(row.execution_id)) || [];
  const starts = chosen.map((row) => row.fecha_inicio).filter(Boolean);
  const ends = chosen.map((row) => row.fecha_fin).filter(Boolean);
  const source = <div className="geo-source"><button type="button" className="geo-session-toggle" aria-expanded={sessionsOpen} aria-controls="geo-session-options" onClick={() => setSessionsOpen((open) => !open)}><span className="geo-session-selection">{chosen.length > 0 && <strong className="geo-session-caption">Sesiones seleccionadas</strong>}{chosen.length ? chosen.map(sessionName).join(', ') : 'Selecciona las sesiones para analizar'}</span><span aria-hidden="true">{sessionsOpen ? '▴' : '▾'}</span></button><fieldset id="geo-session-options" hidden={!sessionsOpen} className="geo-session-list"><legend>Sesiones para analizar</legend>{executions?.map((row) => <label key={row.execution_id} className="geo-session-option"><input type="checkbox" checked={selectedIds.includes(row.execution_id)} onChange={(event) => setSelectedIds((old) => event.target.checked ? [...old, row.execution_id] : old.filter((id) => id !== row.execution_id))} /><span>{sessionName(row)}<small>{row.records_valid ?? 0} registros válidos</small></span></label>)}{executions?.length === 0 && <span>No hay sesiones disponibles.</span>}</fieldset><button type="button" className="geo-primary" disabled={!selectedIds.length} onClick={() => { setAnalysis((old) => ({ ids: [...selectedIds], version: old.version + 1 })); setSessionsOpen(false); }}>Analizar sesiones</button>{chosen.length > 0 && <p className="geo-date-range" role="status"><strong>Rango de fechas de {chosen.length === 1 ? 'la sesión seleccionada' : 'las sesiones seleccionadas'}</strong>{starts.length && ends.length ? <>Del {formatRange(starts.sort()[0])} al {formatRange(ends.sort().at(-1))}</> : 'No hay fechas de mediciones disponibles.'}</p>}</div>;
  return <section className="geo-page">
    <header className="geo-heading"><div><span className="geo-eyebrow">ANÁLISIS GEOESPACIAL</span><h1>Explora tus mediciones</h1><p>Ubicación, trayectoria y señal de los datos procesados.</p></div></header>

    {error && <p className="geo-error" role="alert">{error}</p>}
    {!executions && !error && <p role="status">Consultando ejecuciones…</p>}
    {executions?.length === 0 && <p className="geo-empty">No hay ejecuciones completadas. Procesa un archivo desde Ingesta y vuelve a Geoespacial.</p>}
    {analysis.ids.length ? <DatasetView key={analysis.version} executionIds={analysis.ids} source={source} /> : <div className="geo-workspace"><aside className="geo-filter-panel" aria-label="Filtros geoespaciales"><h2>Filtros</h2>{source}<p className="geo-filter-hint">Selecciona una o varias sesiones para ver los mapas.</p></aside></div>}
  </section>;
}

function DatasetView({ executionIds, source }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [query, setQuery] = useState(emptyFilters);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState('rutas');
  const sequence = useRef(0);
  const [layers, setLayers] = useState(() => {
    try { return { handovers: true, rutas: true, ...JSON.parse(sessionStorage.getItem('geo-event-layers') || '{}') }; }
    catch { return { handovers: true, rutas: true }; }
  });
  useEffect(() => { try { sessionStorage.setItem('geo-event-layers', JSON.stringify(layers)); } catch { /* Optional storage. */ } }, [layers]);
  useEffect(() => {
    const controller = new AbortController();
    const request = ++sequence.current;
    const params = { execution_id: executionIds, ...query };
    // Inputs represent Ecuador time, independent of the browser timezone.
    if (params.desde) params.desde = params.desde.slice(0, 16) + ':00-05:00';
    if (params.hasta) params.hasta = params.hasta.slice(0, 16) + ':59.999999-05:00';
    getGeo('mediciones', params, controller.signal).then((data) => {
      if (sequence.current === request) { setResult({ query, data }); setError(''); }
    }).catch((e) => {
      if (e.name !== 'AbortError' && sequence.current === request) { setError(e.message); setResult({ query, data: null }); }
    });
    return () => controller.abort();
  }, [executionIds, query]);
  const loading = result?.query !== query;
  const data = loading ? null : result?.data;
  const signalPoints = data?.mediciones.filter((p) => p.rssi != null) || [];
  const shownSelected = selected && data?.handovers?.find((p) => p.id_registro === selected.id_registro);
  const change = (e) => setFilters((old) => ({ ...old, [e.target.name]: e.target.value }));
  const applyZone = (bbox) => { const next = { ...query, bbox }; setFilters(next); setQuery(next); setSelected(null); };
  const mapLayers = { ...layers, calor: tab === 'calor', radiosBase: tab === 'rutas' && Boolean(layers.radiosBase) };
  const changeTab = (value) => { setTab(value); setSelected(null); };
  return <div className="geo-workspace">
    <aside className="geo-filter-panel" aria-label="Filtros geoespaciales">
    <h2>Filtros</h2>
    {source}
    <form className="geo-filters" onSubmit={(e) => { e.preventDefault(); setSelected(null); setQuery({ ...filters }); }}>
      <label>Desde <input name="desde" type="datetime-local" step="60" value={filters.desde} onChange={change} /></label>
      <label>Hasta <input name="hasta" type="datetime-local" step="60" min={filters.desde || undefined} value={filters.hasta} onChange={change} /></label>
      <label>Tecnología<select name="tecnologia" value={filters.tecnologia} onChange={change}><option value="">Todas</option><option value="1">LTE / 4G</option><option value="2">3G / UMTS</option><option value="0">Sin señal</option></select></label>
      <button className="geo-primary" type="submit">Aplicar filtros</button><button type="button" onClick={() => { setFilters(emptyFilters); setQuery({ ...emptyFilters }); setSelected(null); }}>Limpiar</button>
    </form>
    {query.bbox && <p className="geo-zone">Zona geográfica aplicada <button onClick={() => applyZone('')}>Quitar zona</button></p>}
    </aside>
    <section className="geo-results">
    <div className="geo-tabs" role="tablist" aria-label="Vistas geoespaciales">
      {[['rutas', 'Mapa de rutas y handovers'], ['calor', 'Mapa de calor']].map(([key, label], index) => <button key={key} id={`geo-tab-${key}`} role="tab" aria-selected={tab === key} aria-controls="geo-map-panel" tabIndex={tab === key ? 0 : -1} onClick={() => changeTab(key)} onKeyDown={(event) => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
          event.preventDefault();
          const next = event.key === 'Home' ? 'rutas' : event.key === 'End' ? 'calor' : index === 0 ? 'calor' : 'rutas';
          changeTab(next);
          document.getElementById(`geo-tab-${next}`).focus();
        }
      }}>{label}</button>)}
    </div>
    <div id="geo-map-panel" role="tabpanel" aria-labelledby={`geo-tab-${tab}`}>
    <div className="geo-stats"><div><strong>{data ? data.total.toLocaleString('es-EC') : '—'}</strong><span>Datos analizados</span></div><div><strong>{data ? data.total_handovers : '—'}</strong><span>Handovers</span></div><div><strong>{signalPoints.length ? `${Math.round(signalPoints.reduce((sum, p) => sum + p.rssi, 0) / signalPoints.length)} dBm` : '—'}</strong><span>RSSI promedio</span></div></div>
    <div className="geo-toolbar"><span>Capas</span>{[['handovers', 'Handovers'], ['rutas', 'Trayectoria'], ...(tab === 'rutas' ? [['radiosBase', 'Radios Base']] : [])].map(([key, label]) => <label key={key}><input type="checkbox" checked={Boolean(layers[key])} onChange={(e) => setLayers((old) => ({ ...old, [key]: e.target.checked }))} />{label}</label>)}</div>
    {mapLayers.radiosBase && data && <RadioBaseSummary data={data} />}
    {loading && <p role="status" className="geo-empty">Consultando mediciones…</p>}
    {!loading && error && <p role="alert" className="geo-error">{error}</p>}
    {data?.total === 0 && <p role="status" className="geo-empty">No hay mediciones que coincidan con estos filtros.</p>}
    {data?.total > 0 && data.total_handovers === 0 && <p role="status" className="geo-empty">No se detectaron handovers con la regla de cambio de celda y nodo en estos datos.</p>}
    <MapaGeoespacial data={data} layers={mapLayers} onSelect={setSelected} onZone={applyZone} />
    {tab === 'rutas' ? <div className="geo-legend"><span><i style={{ background: '#128777' }} />RSSI ≥ −80 dBm</span><span><i style={{ background: '#cf9209' }} />−100 ≤ RSSI &lt; −80 dBm</span><span><i style={{ background: '#cf4960' }} />RSSI &lt; −100 dBm</span><span><i style={{ background: '#81909f' }} />RSSI sin dato</span></div> : <div className="geo-legend geo-heat-legend"><i />Azul → rojo: menor → mayor concentración relativa; varía con el zoom.</div>}
    {shownSelected && <aside className="geo-detail"><h2>Detalle de handover</h2><button onClick={() => setSelected(null)} aria-label="Cerrar detalle">Cerrar</button><dl>{Object.entries({ 'Fecha y hora · Ecuador': formatTime(shownSelected.timestamp_medicion), 'Celda origen': shownSelected.celda_origen, 'Celda destino': shownSelected.cell_id, 'Nodo origen': shownSelected.nodo_origen, 'Nodo destino': shownSelected.node_id, Tecnología: shownSelected.tecnologia === 1 ? 'LTE / 4G' : shownSelected.tecnologia === 2 ? '3G / UMTS' : 'Sin señal', RSSI: shownSelected.rssi == null ? 'Sin dato' : `${shownSelected.rssi} dBm`, Velocidad: shownSelected.velocidad_kmh == null ? 'Sin dato' : `${shownSelected.velocidad_kmh.toLocaleString('es-EC', { maximumFractionDigits: 2 })} km/h`, Coordenadas: `${shownSelected.latitud}, ${shownSelected.longitud}` }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></aside>}
    </div>
    </section>
  </div>;
}
