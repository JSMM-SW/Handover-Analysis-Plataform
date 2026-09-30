import { formatRange, sessionName } from '../formatters';

export default function SessionSelector({ executions, selectedIds, open, onToggle, onSelect, onAnalyze }) {
  const chosen = executions?.filter((row) => selectedIds.includes(row.execution_id)) || [];
  const starts = chosen.map((row) => row.fecha_inicio).filter(Boolean).sort();
  const ends = chosen.map((row) => row.fecha_fin).filter(Boolean).sort();

  return (
    <div className="geo-source">
      <button
        type="button"
        className="geo-session-toggle"
        aria-expanded={open}
        aria-controls="geo-session-options"
        onClick={onToggle}
      >
        <span className="geo-session-selection">
          {chosen.length > 0 && <strong className="geo-session-caption">Sesiones seleccionadas</strong>}
          {chosen.length ? chosen.map(sessionName).join(', ') : 'Selecciona las sesiones para analizar'}
        </span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      <fieldset id="geo-session-options" hidden={!open} className="geo-session-list">
        <legend>Sesiones para analizar</legend>
        {executions?.map((row) => (
          <label key={row.execution_id} className="geo-session-option">
            <input
              type="checkbox"
              checked={selectedIds.includes(row.execution_id)}
              onChange={(event) => onSelect(row.execution_id, event.target.checked)}
            />
            <span>
              {sessionName(row)}
              <small>{row.records_valid ?? 0} registros válidos</small>
            </span>
          </label>
        ))}
        {executions?.length === 0 && <span>No hay sesiones disponibles.</span>}
      </fieldset>
      <button type="button" className="geo-primary" disabled={!selectedIds.length} onClick={onAnalyze}>
        Analizar sesiones
      </button>
      {chosen.length > 0 && (
        <p className="geo-date-range" role="status">
          <strong>Rango de fechas de {chosen.length === 1 ? 'la sesión seleccionada' : 'las sesiones seleccionadas'}</strong>
          {starts.length && ends.length
            ? <>Del {formatRange(starts[0])} al {formatRange(ends.at(-1))}</>
            : 'No hay fechas de mediciones disponibles.'}
        </p>
      )}
    </div>
  );
}
