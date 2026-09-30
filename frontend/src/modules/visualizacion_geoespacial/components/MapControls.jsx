const TABS = [['rutas', 'Mapa de rutas y handovers'], ['calor', 'Mapa de calor']];
const ROUTE_LAYERS = [['handovers', 'Handovers'], ['rutas', 'Trayectoria'], ['radiosBase', 'Radios Base']];
const HEAT_LAYERS = [['handovers', 'Handovers'], ['rssi', 'RSSI'], ['rsrq', 'RSRQ']];

export function MapTabs({ tab, onChange }) {
  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : 1 - index;
    const next = TABS[nextIndex][0];
    onChange(next);
    document.getElementById(`geo-tab-${next}`).focus();
  }

  return (
    <div className="geo-tabs" role="tablist" aria-label="Vistas geoespaciales">
      {TABS.map(([key, label], index) => (
        <button
          key={key}
          id={`geo-tab-${key}`}
          role="tab"
          aria-selected={tab === key}
          aria-controls="geo-map-panel"
          tabIndex={tab === key ? 0 : -1}
          onClick={() => onChange(key)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function MapToolbar({ tab, layers, onLayerChange, heatMetric, onHeatChange, exporting, canExport, onExport }) {
  return (
    <div className="geo-toolbar">
      <span>Capas</span>
      {tab === 'calor' ? (
        <div className="geo-heat-options" role="radiogroup" aria-label="Capas del mapa de calor">
          {HEAT_LAYERS.map(([key, label]) => (
            <label key={key}>
              <input type="radio" name="heatMetric" checked={heatMetric === key} onChange={() => onHeatChange(key)} />
              {label}
            </label>
          ))}
        </div>
      ) : ROUTE_LAYERS.map(([key, label]) => (
        <label key={key}>
          <input type="checkbox" checked={layers[key]} onChange={(event) => onLayerChange(key, event.target.checked)} />
          {label}
        </label>
      ))}
      <button className="geo-download" type="button" disabled={exporting || !canExport} onClick={onExport}>
        <span aria-hidden="true">↓</span> {exporting ? 'Preparando imagen…' : 'Descargar mapa'}
      </button>
    </div>
  );
}
