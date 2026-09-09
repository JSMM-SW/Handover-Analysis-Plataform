import { useEffect, useRef, useState } from 'react';
import { getGeo } from './api';
import MapaGeoespacial from './components/MapaGeoespacial';
import './GeoespacialPage.css';

const formatTime = (value) => new Intl.DateTimeFormat('es-EC', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'America/Guayaquil' }).format(new Date(value));
const emptyFilters = { desde: '', hasta: '', tecnologia: '', cell_id: '', bbox: '' };

export default function GeoespacialPage() {
  const [executions, setExecutions] = useState(null);
  const [execution, setExecution] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getGeo('ejecuciones', {}, controller.signal).then((rows) => {
      setExecutions(rows);
      setExecution((old) => rows.some((r) => r.execution_id === old) ? old : rows[0]?.execution_id || '');
      setError('');
    }).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [reload]);
  const source = <div className="geo-source"><label>Archivo procesado<select value={execution} onChange={(e) => setExecution(e.target.value)}><option value="">Selecciona una ejecución</option>{executions?.map((r) => <option key={r.execution_id} value={r.execution_id}>{r.filename} · {formatTime(r.processing_date)} · {r.execution_id.slice(0, 8)}</option>)}</select></label><button type="button" onClick={() => setReload((n) => n + 1)}>Actualizar archivos</button></div>;
  return <section className="geo-page">
    <header className="geo-heading"><div><span className="geo-eyebrow">ANÁLISIS ESPACIAL</span><h1>Explora tus mediciones</h1><p>Ubicación, trayectoria y señal de los datos procesados.</p></div><span className="geo-badge">Datos de PostgreSQL</span></header>

    {error && <p className="geo-error" role="alert">{error}</p>}
    {!executions && !error && <p role="status">Consultando ejecuciones…</p>}
    {executions?.length === 0 && <p className="geo-empty">No hay ejecuciones completadas. Procesa un archivo desde Ingesta y actualiza esta lista.</p>}
    {execution ? <ExecutionView key={execution} execution={execution} source={source} /> : source}
  </section>;
}

function ExecutionView({ execution, source }) {
  const [sheets, setSheets] = useState(null);
  const [sheet, setSheet] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    getGeo(`ejecuciones/${execution}/hojas`, {}, controller.signal).then((rows) => { setSheets(rows); setSheet(rows[0] || ''); }).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [execution]);
  return <>
    {error && <p role="alert" className="geo-error">{error}</p>}
    {!sheets && !error && <p role="status">Cargando hojas…</p>}
    {sheets?.length === 0 && <p className="geo-empty">Esta ejecución no contiene mediciones válidas.</p>}

    {sheet ? <DatasetView key={sheet} execution={execution} sheet={sheet} source={source} sheetSelect={<label className="geo-sheet">Hoja de medición<select value={sheet} onChange={(e) => setSheet(e.target.value)}>{sheets.map((s) => <option key={s}>{s}</option>)}</select></label>} /> : source}
  </>;
}

function DatasetView({ execution, sheet, source, sheetSelect }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [query, setQuery] = useState(emptyFilters);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState('rutas');
  const sequence = useRef(0);
  const [layers, setLayers] = useState(() => {
    try { return { puntos: true, rutas: true, calor: false, ...JSON.parse(sessionStorage.getItem('geo-layers') || '{}') }; }
    catch { return { puntos: true, rutas: true, calor: false }; }
  });
  useEffect(() => { try { sessionStorage.setItem('geo-layers', JSON.stringify(layers)); } catch { /* Optional storage. */ } }, [layers]);
  useEffect(() => {
    const controller = new AbortController();
    const request = ++sequence.current;
    const params = { execution_id: execution, hoja: sheet, ...query };
    // Inputs represent Ecuador time, independent of the browser timezone.
    if (params.desde) params.desde += '-05:00';
    if (params.hasta) params.hasta += '-05:00';
    getGeo('mediciones', params, controller.signal).then((data) => {
      if (sequence.current === request) { setResult({ query, data }); setError(''); }
    }).catch((e) => {
      if (e.name !== 'AbortError' && sequence.current === request) { setError(e.message); setResult({ query, data: null }); }
    });
    return () => controller.abort();
  }, [execution, sheet, query]);
  const loading = result?.query !== query;
  const data = loading ? null : result?.data;
  const shownSelected = selected && data?.mediciones.find((p) => p.id_registro === selected.id_registro);
  const change = (e) => setFilters((old) => ({ ...old, [e.target.name]: e.target.value }));
  const applyZone = (bbox) => { const next = { ...query, bbox }; setFilters(next); setQuery(next); setSelected(null); };
  const mapLayers = tab === 'calor' ? { puntos: false, rutas: false, calor: true } : { ...layers, calor: false };
  const changeTab = (value) => { setTab(value); setSelected(null); };
  return <div className="geo-workspace">
    <aside className="geo-filter-panel" aria-label="Filtros geoespaciales">
    <h2>Filtros</h2>
    <p className="geo-filter-hint">Se aplican a ambas vistas del mapa.</p>
    {source}
    {sheetSelect}
    <form className="geo-filters" onSubmit={(e) => { e.preventDefault(); setSelected(null); setQuery({ ...filters }); }}>
      <label>Desde · Ecuador<input name="desde" type="datetime-local" step="1" value={filters.desde} onChange={change} /></label>
      <label>Hasta · Ecuador<input name="hasta" type="datetime-local" step="1" min={filters.desde || undefined} value={filters.hasta} onChange={change} /></label>
      <label>Tecnología<select name="tecnologia" value={filters.tecnologia} onChange={change}><option value="">Todas</option><option value="1">LTE / 4G</option><option value="0">Sin señal</option></select></label>
      <label>Celda<input name="cell_id" type="number" min="1" step="1" placeholder="Todas" value={filters.cell_id} onChange={change} /></label>
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
    <p className="geo-view-description">{tab === 'rutas' ? 'Rutas y mediciones disponibles. La identificación de eventos de handover está pendiente.' : 'Densidad de mediciones GPS. Esta vista todavía no representa eventos de handover.'}</p>
    <div className="geo-stats"><div><strong>{data ? data.total.toLocaleString('es-EC') : '—'}</strong><span>Mediciones visibles</span></div><div><strong>{data ? new Set(data.mediciones.map((p) => p.cell_id)).size : '—'}</strong><span>Celdas observadas</span></div><div><strong>{data?.total ? `${Math.round(data.mediciones.reduce((sum, p) => sum + p.rsrp_dbm, 0) / data.total)} dBm` : '—'}</strong><span>RSRP promedio</span></div></div>
    {tab === 'rutas' && <div className="geo-toolbar"><span>Capas</span>{[['puntos', 'Mediciones'], ['rutas', 'Trayectoria aproximada']].map(([key, label]) => <label key={key}><input type="checkbox" checked={Boolean(layers[key])} onChange={(e) => setLayers((old) => ({ ...old, [key]: e.target.checked }))} />{label}</label>)}</div>}
    {loading && <p role="status" className="geo-empty">Consultando mediciones…</p>}
    {!loading && error && <p role="alert" className="geo-error">{error}</p>}
    {data?.total === 0 && <p role="status" className="geo-empty">No hay mediciones que coincidan con estos filtros.</p>}
    <MapaGeoespacial data={data} layers={mapLayers} onSelect={setSelected} onZone={applyZone} />
    {tab === 'rutas' ? <div className="geo-legend"><span><i style={{ background: '#128777' }} />RSRP ≥ −90</span><span><i style={{ background: '#cf9209' }} />−105 ≤ RSRP &lt; −90</span><span><i style={{ background: '#cf4960' }} />RSRP &lt; −105 dBm</span></div> : <div className="geo-legend geo-heat-legend"><i />Azul → rojo: menor → mayor concentración relativa; varía con el zoom.</div>}
    {shownSelected && <aside className="geo-detail"><h2>Detalle de medición</h2><button onClick={() => setSelected(null)} aria-label="Cerrar detalle">Cerrar</button><dl>{Object.entries({ 'Fecha y hora · Ecuador': formatTime(shownSelected.timestamp_medicion), Celda: shownSelected.cell_id, Tecnología: shownSelected.tecnologia === 1 ? 'LTE / 4G' : 'Sin señal', RSRP: `${shownSelected.rsrp_dbm} dBm`, Coordenadas: `${shownSelected.latitud}, ${shownSelected.longitud}`, Hoja: shownSelected.hoja_origen }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></aside>}
    <div className="geo-notes">{data?.advertencias.map((note) => <p key={note}>{note}</p>)}<p>Velocidad y estaciones base no están disponibles en el esquema actual.</p></div>
    </div>
    </section>
  </div>;
}
