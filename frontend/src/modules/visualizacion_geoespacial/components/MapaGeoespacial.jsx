import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.heat';
import { signalColor } from '../signalHeat';
import SignalHeatLayer from './SignalHeatLayer';

const color = (rssi) => signalColor(rssi, 'rssi');
const formatDate = (value) => new Intl.DateTimeFormat('es-EC', {
  dateStyle: 'medium', timeZone: 'America/Guayaquil',
}).format(new Date(value));
const formatHour = (value) => new Intl.DateTimeFormat('es-EC', {
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  timeZone: 'America/Guayaquil',
}).format(new Date(value));

function appendFields(container, fields) {
  for (const [label, value] of fields) {
    const row = document.createElement('div');
    row.textContent = `${label}: ${value}`;
    container.append(row);
  }
}

function handoverTooltip(point, metric = null) {
  const content = document.createElement('div');
  content.className = 'geo-handover-tooltip';
  const title = document.createElement('strong');
  title.textContent = `Handover ${point.celda_origen} → ${point.cell_id}`;
  content.append(title);
  appendFields(content, [
    ['Fecha', formatDate(point.timestamp_medicion)],
    ['Hora', formatHour(point.timestamp_medicion)],
    ['RSSI', point.rssi == null ? 'Sin dato' : `${point.rssi} dBm`],
    ['RSRQ', point.rsrq == null ? 'Sin dato' : `${point.rsrq} dB`],
    ['RSSNR', point.rssnr == null ? 'Sin dato' : String(point.rssnr)],
  ].filter(([label]) => !metric || !['RSSI', 'RSRQ', 'RSSNR'].includes(label) || label === metric.toUpperCase()));
  return content;
}

function radioBasePopup(estimates, executions) {
  const content = document.createElement('div');
  content.className = 'geo-radio-popup';
  for (const station of estimates) {
    const section = document.createElement('section');
    const heading = document.createElement('strong');
    heading.textContent = 'Radio base estimada';
    section.append(heading);
    const session = executions?.find((row) => row.execution_id === station.execution_id);
    appendFields(section, [
      ['Sesión', session?.sesion_label ?? station.execution_id],
      ['Nodo', station.node_id], ['Celda', station.cell_id],
      ['Tecnología', station.tecnologia === 1 ? 'LTE / 4G' : '3G / UMTS'],
      ['Coordenadas estimadas', `${station.latitud}, ${station.longitud}`],
    ]);
    const note = document.createElement('p');
    note.textContent = 'Ubicación aproximada calculada a partir de las mediciones.';
    section.append(note);
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Detalles de la estimación';
    details.append(summary);
    appendFields(details, [
      [station.tecnologia === 1 ? 'PCI' : 'PSC', station.psc_pci?.length ? station.psc_pci.join(', ') : 'Sin dato'],
      ['Canal de frecuencia (ARFCN)', station.earfcn],
      ['Muestras válidas sin repetir', station.mediciones_validas],
      ['Posiciones utilizadas', `${station.posiciones_utilizadas} de ${station.posiciones_disponibles}`],
      ['RSSI máximo de posiciones', `${station.rssi_max} dBm`],
      ['Dispersión de posiciones', `${station.dispersion_m} m (no es el error de ubicación)`],
    ]);
    section.append(details);
    content.append(section);
  }
  return content;
}

export default function MapaGeoespacial({ data, layers, onSelect, onZone, executions }) {
  const host = useRef(null);
  const mapRef = useRef(null);
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    const map = L.map(host.current, { preferCanvas: true }).setView([-0.2, -78.5], 11);
    mapRef.current = map;
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, crossOrigin: 'anonymous', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
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
    if (layers.signalMetric) {
      new SignalHeatLayer(events, layers.signalMetric).addTo(group);
      for (const event of events) L.circleMarker([event.latitud, event.longitud], {
        radius: 8, stroke: false, fillOpacity: 0,
      }).bindTooltip(handoverTooltip(event, layers.signalMetric)).addTo(group);
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
          icon: L.divIcon({
            className: 'geo-radio-base-marker',
            html: `<svg aria-hidden="true" focusable="false" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="16" cy="9" r="2" fill="currentColor" stroke="none"/><path d="M16 11 10 27h12L16 11Zm-3 9h6m-7 4 7-4M9 5a6 6 0 0 0 0 8m14-8a6 6 0 0 1 0 8M5 2a10 10 0 0 0 0 14M27 2a10 10 0 0 1 0 14"/></svg>${stations.length > 1 ? `<span class="geo-radio-base-count" aria-hidden="true">${stations.length}</span>` : ''}`,
            iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -13],
          }),
          title: label, alt: label, zIndexOffset: 500,
        }).bindPopup(radioBasePopup(stations, executions), { maxWidth: 340 }).addTo(group);
      }
    }
    return () => group.remove();
  }, [data, layers, onSelect, executions]);
  return <div className="geo-map-wrap">
    <div className="geo-map" ref={host} aria-label="Mapa de mediciones GPS" />
    <button type="button" className="geo-zone-button" data-html2canvas-ignore onClick={() => {
      const b = mapRef.current.getBounds();
      onZone([Math.max(-180, b.getWest()), Math.max(-90, b.getSouth()), Math.min(180, b.getEast()), Math.min(90, b.getNorth())].join(','));
    }}>Filtrar por zona visible</button>
    {tileError && <p className="geo-tile-error" role="status">No se pudo cargar parte del mapa base. Comprueba tu conexión a Internet.</p>}
  </div>;
}
