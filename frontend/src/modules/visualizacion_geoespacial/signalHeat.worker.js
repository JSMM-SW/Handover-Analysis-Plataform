import { signalRaster } from './signalHeat';

self.onmessage = ({ data: { coordinates, metric, width, height } }) => {
  function* points() {
    for (let i = 0; i < coordinates.length; i += 3) {
      yield { x: coordinates[i], y: coordinates[i + 1], value: coordinates[i + 2] };
    }
  }
  const pixels = signalRaster(points(), metric, width, height);
  self.postMessage({ pixels, width, height }, [pixels.buffer]);
};
