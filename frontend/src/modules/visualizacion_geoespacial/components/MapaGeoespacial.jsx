import { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { signalColor } from '../signalHeat';
import SignalHeatLayer from './SignalHeatLayer';

import { handoverTooltip, radioBasePopup } from '../mapPopups';

export default function MapaGeoespacial({ data, layers, onSelect, executions, viewKey, onViewportChange, onDetail }) {
  const host = useRef(null);
  const mapRef = useRef(null);
  const fittedKey = useRef(null);
  const summarized = Boolean(data?.mapa_resumido);
  const [tileError, setTileError] = useState(false);
  const [heatError, setHeatError] = useState(false);
  // Reuse the route index when changing layers or opening a handover detail.
  const byId = useMemo(() => new Map((data?.mediciones || []).map((point) => [point.id_registro, point])), [data]);
  function centerData() {
    const points = [
      ...(data?.mediciones || []),
      ...(data?.handovers || []),
      ...(layers.radiosBase ? data?.radios_base || [] : []),
    ];
    const bounds = data?.limites?.length ? L.latLngBounds(data.limites) : points.length ? L.latLngBounds(points.map((point) => [point.latitud, point.longitud])) : null;
    if (!bounds) return;
    if (layers.radiosBase) for (const station of data?.radios_base || []) bounds.extend([station.latitud, station.longitud]);
    mapRef.current.fitBounds(bounds, {
      padding: [40, 40], maxZoom: 16,
    });
  }
  useEffect(() => {
    const map = L.map(host.current, { preferCanvas: true }).setView([-0.2, -78.5], 11);
    mapRef.current = map;
    map.on('geo:heat-error', () => setHeatError(true));
    map.on('geo:heat-ready', () => setHeatError(false));
    const handoverPane = map.createPane('geo-handover-points');
    handoverPane.style.zIndex = '450';
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, crossOrigin: 'anonymous', attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).on('tileerror', () => setTileError(true)).addTo(map);
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(host.current);
    return () => { resize.disconnect(); map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    if (!data || fittedKey.current === viewKey) return;
    const points = data?.mediciones || [];
    const bounds = data.limites?.length ? data.limites : points.map((p) => [p.latitud, p.longitud]);
    if (bounds.length) mapRef.current.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
    fittedKey.current = viewKey;
  }, [data, viewKey]);
  useEffect(() => {
    if (!summarized || !onViewportChange) return;
    const map = mapRef.current;
    let timer;
    const update = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const b = map.getBounds();
        const bounds = [Math.max(-180, b.getWest()), Math.max(-90, b.getSouth()), Math.min(180, b.getEast()), Math.min(90, b.getNorth())];
        if (bounds[0] < bounds[2] && bounds[1] < bounds[3]) onViewportChange({
          zoom: Math.round(map.getZoom()), vista_bbox: bounds.map((value) => value.toFixed(6)).join(','),
        });
      }, 350);
    };
    map.on('moveend resize', update);
    update();
    return () => { clearTimeout(timer); map.off('moveend resize', update); };
  }, [summarized, onViewportChange]);
  useEffect(() => {
    const group = L.layerGroup().addTo(mapRef.current);
    // SVG paths receive events only on the dots; a canvas in the upper pane
    // would also intercept measurement hovers on the rest of the map.
    const blackRenderer = layers.blackHandovers ? L.svg({ pane: 'geo-handover-points' }) : null;
    const events = data?.handovers || [];
    if (layers.rutas) for (const segment of data?.tramos || []) {
      L.polyline(segment.map((id) => { const p = byId.get(id); return [p.latitud, p.longitud]; }), { color: '#3b69b1', weight: 3, opacity: 0.65 }).addTo(group);
    }
    if (layers.handovers) for (const p of events) {
      const marker = L.circleMarker([p.latitud, p.longitud], { radius: 7, color: '#fff', weight: 2, fillColor: signalColor(p.rssi, 'rssi'), fillOpacity: 0.95 }).addTo(group);
      marker.bindTooltip(() => handoverTooltip(p), { direction: 'top', offset: [0, -8] }).on('click', () => onSelect(p));
    }
    if (layers.signalMetric) {
      const measurements = summarized ? data?.senales || [] : data?.mediciones || [];
      new SignalHeatLayer(measurements, layers.signalMetric, onDetail).addTo(group);
    }
    if (layers.blackHandovers) for (const event of events) {
      L.circleMarker([event.latitud, event.longitud], {
        radius: 3, stroke: false, fillColor: '#000', fillOpacity: 1,
        renderer: blackRenderer, pane: 'geo-handover-points',
      }).bindTooltip(() => handoverTooltip(event, 'handovers'), { direction: 'top', offset: [0, -8] })
        .on('click', () => onSelect(event)).addTo(group);
    }
    if (layers.handovers || layers.blackHandovers) for (const cluster of data?.grupos_handovers || []) {
      const content = document.createElement('div');
      const title = document.createElement('p');
      title.textContent = `${cluster.cantidad} handovers agrupados`;
      const zoom = document.createElement('button');
      zoom.textContent = 'Acercar';
      zoom.onclick = () => mapRef.current.fitBounds(cluster.limites, { padding: [30, 30], maxZoom: Math.min(mapRef.current.getMaxZoom(), mapRef.current.getZoom() + 3) });
      const detail = document.createElement('button');
      detail.textContent = 'Ver un handover del grupo';
      detail.onclick = () => onDetail?.(cluster.id_registro, true);
      content.append(title, zoom, detail);
      L.circleMarker([cluster.latitud, cluster.longitud], {
        radius: Math.min(16, 5 + Math.log2(cluster.cantidad)), color: '#fff', weight: 1,
        fillColor: layers.blackHandovers ? '#000' : '#4068a0', fillOpacity: 0.95,
        ...(blackRenderer ? { renderer: blackRenderer, pane: 'geo-handover-points' } : {}),
      }).bindTooltip(`${cluster.cantidad} handovers agrupados`).bindPopup(content).addTo(group);
    }
    if (layers.radiosBase) {
      for (const cluster of data?.grupos_radios_base || []) {
        const content = document.createElement('div');
        const title = document.createElement('p');
        title.textContent = `${cluster.cantidad} estimaciones agrupadas. Se muestra una estimación del grupo.`;
        content.append(title, radioBasePopup([cluster.ejemplo], executions));
        const zoom = document.createElement('button');
        zoom.textContent = 'Acercar';
        zoom.onclick = () => mapRef.current.fitBounds(cluster.limites, { padding: [30, 30], maxZoom: Math.min(mapRef.current.getMaxZoom(), mapRef.current.getZoom() + 3) });
        content.append(zoom);
        L.circleMarker([cluster.latitud, cluster.longitud], {
          radius: Math.min(16, 5 + Math.log2(cluster.cantidad)), color: '#fff', weight: 1,
          fillColor: '#7953a8', fillOpacity: 0.95,
        }).bindTooltip(`${cluster.cantidad} estimaciones agrupadas`).bindPopup(content).addTo(group);
      }
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
    return () => { group.remove(); blackRenderer?.remove(); };
  }, [data, layers, onSelect, executions, byId, summarized, onDetail]);
  return <div className="geo-map-wrap">
    <div className="geo-map" ref={host} aria-label="Mapa de mediciones GPS" />
    <button type="button" className="geo-center-button" data-html2canvas-ignore
      disabled={!data?.total}
      onClick={centerData}>Ajustar vista</button>
    {tileError && <p className="geo-tile-error" role="status">No se pudo cargar parte del mapa base. Comprueba tu conexión a Internet.</p>}
    {heatError && layers.signalMetric && <p className="geo-error" role="alert">No se pudo dibujar el calor. Vuelve a seleccionar el parámetro.</p>}
  </div>;
}
