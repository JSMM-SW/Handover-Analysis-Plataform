import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.heat';

const color = (rsrp) => rsrp >= -90 ? '#128777' : rsrp >= -105 ? '#cf9209' : '#cf4960';

export default function MapaGeoespacial({ data, layers, onSelect, onZone }) {
  const host = useRef(null);
  const mapRef = useRef(null);
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    const map = L.map(host.current, { preferCanvas: true }).setView([-0.2, -78.5], 11);
    mapRef.current = map;
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).on('tileerror', () => setTileError(true)).addTo(map);
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(host.current);
    return () => { resize.disconnect(); map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    const points = data?.mediciones || [];
    if (points.length) mapRef.current.fitBounds(points.map((p) => [p.latitud, p.longitud]), { padding: [30, 30], maxZoom: 16 });
  }, [data]);
  useEffect(() => {
    const group = L.layerGroup().addTo(mapRef.current);
    const points = data?.mediciones || [];
    const byId = new Map(points.map((p) => [p.id_registro, p]));
    if (layers.rutas) for (const segment of data?.tramos || []) {
      L.polyline(segment.map((id) => { const p = byId.get(id); return [p.latitud, p.longitud]; }), { color: '#3b69b1', weight: 3, opacity: 0.65 }).addTo(group);
    }
    if (layers.calor && points.length) L.heatLayer(points.map((p) => [p.latitud, p.longitud, 1]), {
      radius: 22, blur: 16, max: 1, maxZoom: 17,
      gradient: { 0.2: '#3066d6', 0.5: '#15bba5', 0.75: '#ffd45c', 1: '#e5504b' },
    }).addTo(group);
    if (layers.puntos) for (const p of points) {
      const marker = L.circleMarker([p.latitud, p.longitud], { radius: 5, color: '#fff', weight: 1, fillColor: color(p.rsrp_dbm), fillOpacity: 0.9 }).addTo(group);
      const label = document.createElement('span');
      label.textContent = `Celda ${p.cell_id} · ${p.rsrp_dbm} dBm`;
      marker.bindTooltip(label).on('click', () => onSelect(p));
    }
    return () => group.remove();
  }, [data, layers, onSelect]);
  return <div className="geo-map-wrap">
    <div className="geo-map" ref={host} aria-label="Mapa de mediciones GPS" />
    <button type="button" className="geo-zone-button" onClick={() => {
      const b = mapRef.current.getBounds();
      onZone([Math.max(-180, b.getWest()), Math.max(-90, b.getSouth()), Math.min(180, b.getEast()), Math.min(90, b.getNorth())].join(','));
    }}>Filtrar por zona visible</button>
    {tileError && <p className="geo-tile-error" role="status">No se pudo cargar parte del mapa base. Comprueba tu conexión a Internet.</p>}
  </div>;
}
