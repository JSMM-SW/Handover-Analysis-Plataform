import { useEffect, useRef } from 'react';
import { formatTime, technologyName } from '../formatters';

export default function MeasurementDetail({ point, onClose }) {
  const heading = useRef(null);
  useEffect(() => {
    heading.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    heading.current?.focus({ preventScroll: true });
  }, [point.id_registro]);
  const fields = {
    'Fecha y hora · Ecuador': formatTime(point.timestamp_medicion),
    Celda: point.cell_id,
    Tecnología: technologyName(point.tecnologia),
    RSSI: point.rssi == null ? 'Sin dato' : `${point.rssi} dBm`,
    RSRP: point.rsrp == null ? 'Sin dato' : `${point.rsrp} dBm`,
    RSRQ: point.rsrq == null ? 'Sin dato' : `${point.rsrq} dB`,
    RSSNR: point.rssnr == null ? 'Sin dato' : `${point.rssnr} dB`,
    Coordenadas: `${point.latitud}, ${point.longitud}`,
  };
  return <aside className="geo-detail">
    <h2 ref={heading} tabIndex={-1}>Detalle de medición original</h2>
    <button type="button" onClick={onClose}>Cerrar detalle de medición</button>
    <dl>{Object.entries(fields).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
  </aside>;
}
