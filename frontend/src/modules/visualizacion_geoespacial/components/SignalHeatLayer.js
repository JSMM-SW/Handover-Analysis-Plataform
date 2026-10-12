import L from 'leaflet';
import { signalRaster } from '../signalHeat';

// A half-resolution canvas is scaled smoothly to CSS pixels. Its finite kernel
// covers 36 screen pixels, recalculated on zoom/pan, never the whole study area.
export default L.Layer.extend({
  initialize(measurements, metric) { this.measurements = measurements; this.metric = metric; },
  onAdd(map) {
    this.canvas = L.DomUtil.create('canvas', 'geo-signal-heat-layer leaflet-layer leaflet-zoom-hide');
    this.canvas.style.pointerEvents = 'none';
    map.getPane('overlayPane').append(this.canvas);
    this.redraw();
  },
  onRemove() { this.canvas.remove(); },
  getEvents() { return { moveend: this.redraw, resize: this.redraw }; },
  redraw() {
    const size = this._map.getSize();
    const width = Math.max(1, Math.ceil(size.x / 2));
    const height = Math.max(1, Math.ceil(size.y / 2));
    this.canvas.width = width; this.canvas.height = height;
    this.canvas.style.width = `${size.x}px`; this.canvas.style.height = `${size.y}px`;
    L.DomUtil.setPosition(this.canvas, this._map.containerPointToLayerPoint([0, 0]));
    const points = this.measurements.map((measurement) => {
      const point = this._map.latLngToContainerPoint([measurement.latitud, measurement.longitud]);
      return { x: point.x / 2, y: point.y / 2, value: measurement[this.metric] };
    });
    this.canvas.getContext('2d').putImageData(new ImageData(signalRaster(points, this.metric, width, height), width, height), 0, 0);
  },
});
