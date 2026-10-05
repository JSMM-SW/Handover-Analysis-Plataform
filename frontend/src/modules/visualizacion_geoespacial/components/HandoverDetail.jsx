import { formatTime, technologyName } from '../formatters';

export default function HandoverDetail({ event, onClose }) {
  const fields = {
    'Fecha y hora · Ecuador': formatTime(event.timestamp_medicion),
    'Celda origen': event.celda_origen,
    'Celda destino': event.cell_id,
    'Nodo origen': event.nodo_origen,
    'Nodo destino': event.node_id,
    Tecnología: technologyName(event.tecnologia),
    RSRP: event.rsrp == null ? 'Sin dato' : `${event.rsrp} dBm`,
    RSSI: event.rssi == null ? 'Sin dato' : `${event.rssi} dBm`,
    Velocidad: event.velocidad_kmh == null
      ? 'Sin dato'
      : `${event.velocidad_kmh.toLocaleString('es-EC', { maximumFractionDigits: 2 })} km/h`,
    Coordenadas: `${event.latitud}, ${event.longitud}`,
  };

  return (
    <aside className="geo-detail">
      <h2>Detalle de handover</h2>
      <button onClick={onClose} aria-label="Cerrar detalle">Cerrar</button>
      <dl>
        {Object.entries(fields).map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>
    </aside>
  );
}
