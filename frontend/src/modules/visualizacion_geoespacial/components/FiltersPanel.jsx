export default function FiltersPanel({ selector, children }) {
  return (
    <aside className="geo-filter-panel" aria-label="Filtros geoespaciales">
      <div className="geo-config-heading">
        <span className="geo-config-icon" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" focusable="false">
            <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" />
            <circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" />
          </svg>
        </span>
        <h2>Configuración del análisis</h2>
      </div>
      <div className="geo-config-block">
        <span className="geo-config-step" aria-hidden="true">1</span>
        <div className="geo-config-body">
          <span className="geo-config-label">Sesiones a analizar</span>
          {selector}
        </div>
      </div>
      {children ? (
        <div className="geo-config-block">
          <span className="geo-config-step" aria-hidden="true">2</span>
          <div className="geo-config-body">
            <span className="geo-config-label">Filtros</span>
            {children}
          </div>
        </div>
      ) : <p className="geo-filter-hint">Selecciona una o varias sesiones para ver los mapas.</p>}
    </aside>
  );
}
