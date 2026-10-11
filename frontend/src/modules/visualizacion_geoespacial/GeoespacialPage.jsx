import { useEffect, useState } from 'react';
import { getGeo } from './api';
import DatasetView from './components/DatasetView';
import SessionSelector from './components/SessionSelector';
import './GeoespacialPage.css';

/**
 * Página del módulo de visualización geoespacial: permite elegir una o
 * varias sesiones procesadas y muestra sus mediciones sobre el mapa
 * (rutas, handovers, radios base y mapa de calor).
 */
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

  /**
   * Marca o desmarca una sesión en la selección actual.
   *
   * @param {number|string} id - execution_id de la sesión.
   * @param {boolean} checked - true para agregarla, false para quitarla.
   */
  function selectSession(id, checked) {
    setSelectedIds((old) => checked ? [...old, id] : old.filter((key) => key !== id));
  }

  /**
   * Confirma la selección de sesiones y dispara un nuevo análisis.
   * Incrementa `version` para que DatasetView se vuelva a montar desde cero.
   */
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
        <h2>Visualización geoespacial</h2>
        <p>Explora tus mediciones: ubicación, trayectoria y señal de los datos procesados.</p>
      </header>
      {error && <p className="geo-error" role="alert">{error}</p>}
      {!executions && !error && <p className="geo-empty" role="status">Consultando ejecuciones…</p>}
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
