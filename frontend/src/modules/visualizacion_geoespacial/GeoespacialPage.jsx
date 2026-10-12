import { useEffect, useState } from 'react';
import { getGeo } from './api';
import DatasetView from './components/DatasetView';
import SessionSelector from './components/SessionSelector';
import FiltersPanel from './components/FiltersPanel';
import './GeoespacialPage.css';

export default function GeoespacialPage() {
  const [executions, setExecutions] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [error, setError] = useState('');

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

  const selector = (
    <SessionSelector
      executions={executions}
      selectedIds={selectedIds}
      open={sessionsOpen}
      onToggle={() => setSessionsOpen((open) => !open)}
      onSelect={selectSession}
    />
  );

  return (
    <section className="geo-page">
      <header className="geo-heading">
        <div>
          <h1>Explora tus mediciones</h1>
        </div>
      </header>
      {error && <p className="geo-error" role="alert">{error}</p>}
      {!executions && !error && <p role="status">Consultando ejecuciones…</p>}
      {executions?.length === 0 && (
        <p className="geo-empty">No hay ejecuciones completadas. Procesa un archivo desde Ingesta y vuelve a Geoespacial.</p>
      )}
      {selectedIds.length ? (
        <DatasetView executionIds={selectedIds} executions={executions} selector={selector} />
      ) : (
        <div className="geo-workspace">
          <FiltersPanel selector={selector} />
        </div>
      )}
    </section>
  );
}
