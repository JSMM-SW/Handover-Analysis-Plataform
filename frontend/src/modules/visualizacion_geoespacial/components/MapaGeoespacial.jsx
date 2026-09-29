import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.heat';

const color = (rssi) => rssi == null ? '#81909f' : rssi >= -80 ? '#128777' : rssi >= -100 ? '#cf9209' : '#cf4960';
const formatDate = (value) => new Intl.DateTimeFormat('es-EC', {
  dateStyle: 'medium', timeZone: 'America/Guayaquil',
}).format(new Date(value));
const formatHour = (value) => new Intl.DateTimeFormat('es-EC', {
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  timeZone: 'America/Guayaquil',
}).format(new Date(value));

function handoverTooltip(point) {
  const content = document.createElement('div');
  content.className = 'geo-handover-tooltip';
  const title = document.createElement('strong');
  title.textContent = `Handover ${point.celda_origen} → ${point.cell_id}`;
  content.append(title);
  for (const [name, value] of [
    ['Fecha', formatDate(point.timestamp_medicion)],
    ['Hora', formatHour(point.timestamp_medicion)],
    ['RSSI', point.rssi == null ? 'Sin dato' : `${point.rssi} dBm`],
    ['RSRQ', point.rsrq == null ? 'Sin dato' : `${point.rsrq} dB`],
    ['RSSNR', point.rssnr == null ? 'Sin dato' : String(point.rssnr)],
  ]) {
    const line = document.createElement('div');
    line.textContent = `${name}: ${value}`;
    content.append(line);
  }
  return content;
}

function radioBasePopup(estimates) {
  const content = document.createElement('div');
  content.className = 'geo-radio-popup';
  for (const station of estimates) {
    const section = document.createElement('section');
    const heading = document.createElement('strong');
    heading.textContent = 'Radio base estimada · ubicación candidata por celda';
    section.append(heading);
    for (const [label, value] of [
      ['Sesión', `handover_record_${station.execution_id}.csv`],
      ['Nodo', station.node_id], ['Celda', station.cell_id],
      ['Tecnología', station.tecnologia === 1 ? 'LTE / 4G' : '3G / UMTS'],
      [station.tecnologia === 1 ? 'PCI' : 'PSC', station.psc_pci?.length ? station.psc_pci.join(', ') : 'Sin dato'],
      ['Canal de frecuencia (ARFCN)', station.earfcn],
      ['Coordenadas estimadas', `${station.latitud}, ${station.longitud}`],
      ['Muestras válidas sin repetir', station.mediciones_validas],
      ['Posiciones utilizadas', `${station.posiciones_utilizadas} de ${station.posiciones_disponibles}`],
      ['RSSI máximo de posiciones', `${station.rssi_max} dBm`],
      ['Dispersión de posiciones', `${station.dispersion_m} m (no es el error de ubicación)`],
    ]) {
      const row = document.createElement('div');
      row.textContent = `${label}: ${value}`;
      section.append(row);
    }
    content.append(section);
  }
  return content;
}

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
    const events = data?.handovers || [];
    if (layers.rutas) for (const segment of data?.tramos || []) {
      L.polyline(segment.map((id) => { const p = byId.get(id); return [p.latitud, p.longitud]; }), { color: '#3b69b1', weight: 3, opacity: 0.65 }).addTo(group);
    }
    if (layers.calor && events.length) L.heatLayer(events.map((p) => [p.latitud, p.longitud, 1]), {
      radius: 22, blur: 16, max: 1, maxZoom: 17,
      gradient: { 0.2: '#3066d6', 0.5: '#15bba5', 0.75: '#ffd45c', 1: '#e5504b' },
    }).addTo(group);
    if (layers.handovers) for (const p of events) {
      const marker = L.circleMarker([p.latitud, p.longitud], { radius: 7, color: '#fff', weight: 2, fillColor: color(p.rssi), fillOpacity: 0.95 }).addTo(group);
      marker.bindTooltip(handoverTooltip(p), { direction: 'top', offset: [0, -8] }).on('click', () => onSelect(p));
    }
    if (layers.radiosBase) {
      // Identical uploads may yield coincident candidates. Share a marker but
      // keep every session's result in the popup; never average across sessions.
      const coincident = new Map();
      for (const station of data?.radios_base || []) {
        const key = `${station.latitud},${station.longitud}`;
        if (!coincident.has(key)) coincident.set(key, []);
        coincident.get(key).push(station);
      }
      for (const stations of coincident.values()) {
        const first = stations[0];
        const label = stations.length === 1 ? `Radio base estimada · Celda ${first.cell_id}` : `${stations.length} estimaciones de radios base coincidentes`;
        L.marker([first.latitud, first.longitud], {
          icon: L.divIcon({ className: 'geo-radio-base-marker', html: `<span aria-hidden="true">◆${stations.length > 1 ? stations.length : ''}</span>`, iconSize: [32, 32], iconAnchor: [16, 16] }),
          title: label, alt: label, zIndexOffset: 500,
        }).bindPopup(radioBasePopup(stations), { maxWidth: 340 }).addTo(group);
      }
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
