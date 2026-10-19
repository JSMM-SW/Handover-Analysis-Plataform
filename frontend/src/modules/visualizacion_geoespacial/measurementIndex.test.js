import { expect, it } from 'vitest';
import { measurementFromSample, measurementIndex } from './measurementIndex';

it('preserves original identity, timestamp, cell and missing signal values', () => {
  const sample = [-0.2, -78.5, -75, -100, null, 0, 'original-id', '2026-05-05T13:00:01Z', 42];
  expect(measurementFromSample(sample)).toEqual({
    latitud: -0.2, longitud: -78.5, rssi: -75, rsrp: -100, rsrq: null, rssnr: 0,
    id_registro: 'original-id', timestamp_medicion: '2026-05-05T13:00:01Z', cell_id: 42,
  });
});

it('finds the closest original across bucket edges and rejects distant positions', () => {
  const index = measurementIndex([{ x: 15, y: 16, sample: 'a' }, { x: 18, y: 16, sample: 'b' }]);
  expect(index.nearest(17, 16)).toBe('b');
  expect(index.nearest(16, 16)).toBe('a');
  expect(index.nearest(30, 30)).toBeNull();
});

it('keeps coincident observations individually identifiable without averaging them', () => {
  const first = { id_registro: 'first', rssi: -110 };
  const second = { id_registro: 'second', rssi: -70 };
  const index = measurementIndex([{ x: 10, y: 10, sample: first }, { x: 10, y: 10, sample: second }]);
  expect(index.nearest(10, 10)).toBe(first);
});

it('searches a hundred thousand samples without limiting the available identities', () => {
  const points = Array.from({ length: 100000 }, (_, i) => ({ x: i % 1000, y: Math.floor(i / 1000), sample: i }));
  const index = measurementIndex(points);
  expect(index.nearest(999, 99)).toBe(99999);
  expect(index.nearest(0, 0)).toBe(0);
});
