import L from 'leaflet';
import { measurementTooltip } from '../mapPopups';
import { measurementFromSample, measurementIndex } from '../measurementIndex';

// One canvas and one proximity index, regardless of sample count. Raster work
// runs outside the UI thread and is cancelled when the view/layer changes.
export default L.Layer.extend({
  initialize(samples, metric, onDetail) {
    this.samples = samples; this.metric = metric; this.onDetail = onDetail;
  },
  onAdd(map) {
    this.canvas = L.DomUtil.create('canvas', 'geo-signal-heat-layer leaflet-layer leaflet-zoom-hide');
    this.canvas.style.pointerEvents = 'none';
    map.getPane('overlayPane').append(this.canvas);
    this.tooltip = L.tooltip({ direction: 'top', offset: [0, -8] });
    this.redraw();
  },
  onRemove() {
    this.worker?.terminate();
    cancelAnimationFrame(this.hoverFrame);
    this.hideTooltip();
    this.canvas.remove();
  },
  getEvents() {
    return { moveend: this.redraw, resize: this.redraw, movestart: this.hideTooltip,
      mousemove: this.queueHover, mouseout: this.hideTooltip, click: this.selectMeasurement };
  },
  hideTooltip() {
    this.tooltip?.remove();
    this.hovered = null;
  },
  nearest(event) {
    // Handovers and radio-base SVG paths have priority over signal samples.
    if (event.originalEvent?.target?.closest('path.leaflet-interactive, .leaflet-marker-icon, .leaflet-popup')) return null;
    const position = event.containerPoint ?? this._map.latLngToContainerPoint(event.latlng);
    return this.index?.nearest(position.x, position.y);
  },
  queueHover(event) {
    this.hoverEvent = event;
    if (this.hoverFrame) return;
    this.hoverFrame = requestAnimationFrame(() => {
      this.hoverFrame = null;
      if (!this._map) return;
      const sample = this.nearest(this.hoverEvent);
      if (!sample) { this.hideTooltip(); return; }
      if (sample === this.hovered) return;
      const point = measurementFromSample(sample);
      this.tooltip.setLatLng([point.latitud, point.longitud])
        .setContent(measurementTooltip(point, this.metric)).addTo(this._map);
      this.hovered = sample;
    });
  },
  selectMeasurement(event) {
    const sample = this.nearest(event);
    if (sample) this.onDetail?.(measurementFromSample(sample).id_registro);
  },
  redraw() {
    this.worker?.terminate();
    this.hideTooltip();
    const size = this._map.getSize();
    const width = Math.max(1, Math.ceil(size.x / 2));
    const height = Math.max(1, Math.ceil(size.y / 2));
    this.canvas.width = width; this.canvas.height = height;
    this.canvas.style.width = `${size.x}px`; this.canvas.style.height = `${size.y}px`;
    this.canvas.dataset.rendering = 'true';
    delete this.canvas.dataset.error;
    L.DomUtil.setPosition(this.canvas, this._map.containerPointToLayerPoint([0, 0]));
    const projected = [];
    const coordinates = [];
    for (const sample of this.samples) {
      const point = measurementFromSample(sample);
      const pixel = this._map.latLngToContainerPoint([point.latitud, point.longitud]);
      if (pixel.x < -36 || pixel.y < -36 || pixel.x > size.x + 36 || pixel.y > size.y + 36) continue;
      projected.push({ x: pixel.x, y: pixel.y, sample });
      coordinates.push(pixel.x / 2, pixel.y / 2, point[this.metric] ?? NaN);
    }
    this.index = measurementIndex(projected);
    const values = new Float64Array(coordinates);
    const worker = new Worker(new URL('../signalHeat.worker.js', import.meta.url), { type: 'module' });
    this.worker = worker;
    worker.onmessage = ({ data: { pixels } }) => {
      if (this.worker !== worker || !this._map) return;
      this.canvas.getContext('2d').putImageData(new ImageData(pixels, width, height), 0, 0);
      this.canvas.dataset.rendering = 'false';
      this._map.fire('geo:heat-ready');
      worker.terminate();
      this.worker = null;
    };
    worker.onerror = () => {
      if (this.worker !== worker) return;
      this.canvas.dataset.rendering = 'false';
      this.canvas.dataset.error = 'true';
      worker.terminate();
      this.worker = null;
      this._map?.fire('geo:heat-error');
    };
    worker.postMessage({ coordinates: values, metric: this.metric, width, height }, [values.buffer]);
  },
});
