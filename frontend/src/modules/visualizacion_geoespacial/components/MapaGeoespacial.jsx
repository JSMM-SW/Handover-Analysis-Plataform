import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { signalColor } from '../signalHeat';
import SignalHeatLayer from './SignalHeatLayer';

import { handoverTooltip, measurementTooltip, radioBasePopup } from '../mapPopups';

export default function MapaGeoespacial({ data, layers, onSelect, executions }) {
  const host = useRef(null);
  const mapRef = useRef(null);
  const [tileError, setTileError] = useState(false);
  // Reuse the route index when changing layers or opening a handover detail.
  const byId = useMemo(() => new Map((data?.mediciones || []).map((point) => [point.id_registro, point])), [data]);
  function centerData() {
    const points = [
      ...(data?.mediciones || []),
      ...(data?.handovers || []),
      ...(layers.radiosBase ? data?.radios_base || [] : []),
    ];
    if (!points.length) return;
    mapRef.current.fitBounds(points.map((point) => [point.latitud, point.longitud]), {
      padding: [40, 40], maxZoom: 16,
    });
  }
  useEffect(() => {
    const map = L.map(host.current, { preferCanvas: true }).setView([-0.2, -78.5], 11);
    mapRef.current = map;
    const handoverPane = map.createPane('geo-handover-points');
    handoverPane.style.zIndex = '450';
    handoverPane.style.pointerEvents = 'none';
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
    const events = data?.handovers || [];
    if (layers.rutas) for (const segment of data?.tramos || []) {
      L.polyline(segment.map((id) => { const p = byId.get(id); return [p.latitud, p.longitud]; }), { color: '#3b69b1', weight: 3, opacity: 0.65 }).addTo(group);
    }
    if (layers.handovers) for (const p of events) {
      const marker = L.circleMarker([p.latitud, p.longitud], { radius: 7, color: '#fff', weight: 2, fillColor: signalColor(p.rssi, 'rssi'), fillOpacity: 0.95 }).addTo(group);
      marker.bindTooltip(() => handoverTooltip(p), { direction: 'top', offset: [0, -8] }).on('click', () => onSelect(p));
    }
    if (layers.signalMetric) {
      const measurements = data?.mediciones || [];
      new SignalHeatLayer(measurements, layers.signalMetric).addTo(group);
      for (const point of measurements) L.circleMarker([point.latitud, point.longitud], {
        radius: 8, stroke: false, fillOpacity: 0,
      }).bindTooltip(() => measurementTooltip(point, layers.signalMetric)).addTo(group);
    }
    if (layers.blackHandovers) for (const event of events) {
      L.circleMarker([event.latitud, event.longitud], {
        radius: 3, stroke: false, fillColor: '#000', fillOpacity: 1,
        interactive: false, pane: 'geo-handover-points',
      }).addTo(group);
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
        const tooltip = document.createElement('div');
        tooltip.className = 'geo-handover-tooltip';
        const identifiers = new Map();
        for (const station of stations) {
          const type = station.tecnologia === 2 ? 'PSC' : 'PCI';
          if (!identifiers.has(type)) identifiers.set(type, new Set());
          for (const code of station.psc_pci ?? []) identifiers.get(type).add(code);
        }
        for (const [type, values] of identifiers) {
          const codes = [...values].sort((a, b) => a - b);
          const title = document.createElement('strong');
          title.textContent = `${type}: ${codes.length ? codes.join(', ') : 'Sin dato'}`;
          tooltip.append(title);
        }
        const label = stations.length === 1 ? `Radio base estimada · Celda ${first.cell_id}` : `${stations.length} estimaciones de radios base coincidentes`;
        L.marker([first.latitud, first.longitud], {
          icon: L.divIcon({
            className: 'geo-radio-base-marker',
            html: `<svg aria-hidden="true" focusable="false" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="16" cy="9" r="2" fill="currentColor" stroke="none"/><path d="M16 11 10 27h12L16 11Zm-3 9h6m-7 4 7-4M9 5a6 6 0 0 0 0 8m14-8a6 6 0 0 1 0 8M5 2a10 10 0 0 0 0 14M27 2a10 10 0 0 1 0 14"/></svg>${stations.length > 1 ? `<span class="geo-radio-base-count" aria-hidden="true">${stations.length}</span>` : ''}`,
            iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -13],
          }),
          alt: label, zIndexOffset: 500,
        }).bindTooltip(tooltip, { direction: 'top', offset: [0, -8] })
          .bindPopup(radioBasePopup(stations, executions), { maxWidth: 340 }).addTo(group);
      }
    }
    return () => group.remove();
  }, [data, layers, onSelect, executions, byId]);
  return <div className="geo-map-wrap">
    <div className="geo-map" ref={host} aria-label="Mapa de mediciones GPS" />
    <button type="button" className="geo-center-button" data-html2canvas-ignore
      disabled={!data?.mediciones?.length && !data?.handovers?.length}
      onClick={centerData}>Ajustar vista</button>
    {tileError && <p className="geo-tile-error" role="status">No se pudo cargar parte del mapa base. Comprueba tu conexión a Internet.</p>}
  </div>;
}
