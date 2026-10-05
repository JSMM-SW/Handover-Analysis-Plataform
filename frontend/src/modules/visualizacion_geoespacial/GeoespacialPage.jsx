import { useEffect, useState } from 'react';
import { getGeo } from './api';
import DatasetView from './components/DatasetView';
import SessionSelector from './components/SessionSelector';
import './GeoespacialPage.css';

export default function GeoespacialPage() {
  const [executions, setExecutions] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [error, setError] = useState('');
  const [analysis, setAnalysis] = useState({ ids: [], version: 0 });

  useEffect(() => {
    const controller = new AbortController();
    getGeo('ejecuciones', {}, controller.signal)
      .then((rows) => {
        if (controller.signal.aborted) return;
        setExecutions(rows);
        setError('');
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setError(error.message);
      });
    return () => controller.abort();
  }, []);

  function selectSession(id, checked) {
    setSelectedIds((old) => checked ? [...old, id] : old.filter((key) => key !== id));
  }

  function analyzeSessions() {
    setAnalysis((old) => ({ ids: [...selectedIds], version: old.version + 1 }));
    setSessionsOpen(false);
  }

  const selector = (
    <SessionSelector
      executions={executions}
      selectedIds={selectedIds}
      open={sessionsOpen}
      onToggle={() => setSessionsOpen((open) => !open)}
      onSelect={selectSession}
      onAnalyze={analyzeSessions}
    />
  );

  return (
    <section className="geo-page">
      <header className="geo-heading">
        <div>
          <span className="geo-eyebrow">VISUALIZACIÓN GEOESPACIAL</span>
          <h1>Explora tus mediciones</h1>
          <p>Ubicación, trayectoria y señal de los datos procesados.</p>
        </div>
      </header>
      {error && <p className="geo-error" role="alert">{error}</p>}
      {!executions && !error && <p role="status">Consultando ejecuciones…</p>}
      {executions?.length === 0 && (
        <p className="geo-empty">No hay ejecuciones completadas. Procesa un archivo desde Ingesta y vuelve a Geoespacial.</p>
      )}
      {analysis.ids.length ? (
        <DatasetView key={analysis.version} executionIds={analysis.ids} executions={executions} selector={selector} />
      ) : (
        <div className="geo-workspace">
          <aside className="geo-filter-panel" aria-label="Filtros geoespaciales">
            <h2>Filtros</h2>
            {selector}
            <p className="geo-filter-hint">Selecciona una o varias sesiones para ver los mapas.</p>
          </aside>
        </div>
      )}
    </section>
  );
}
