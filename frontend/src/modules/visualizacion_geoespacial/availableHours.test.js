import { describe, expect, it } from 'vitest';
import { availableHours } from './availableHours';

describe('available capture hours', () => {
  it('starts at the detected hour and advances in five-minute steps', () => {
    const result = availableHours([
      { fecha: '2026-05-05', franjas: [{ inicio: '06:11', fin: '06:22' }] },
      { fecha: '2026-05-06', franjas: [{ inicio: '00:00', fin: '00:02' }] },
    ], '2026-05-05', '2026-05-05');
    expect(result.inicios.map((hour) => hour.valor)).toEqual(['06:00', '06:05', '06:10', '06:15', '06:20', '06:25']);
    expect(result.fines).toEqual(result.inicios);
  });

  it('keeps the last recorded minute without overflowing past midnight', () => {
    const result = availableHours([{ fecha: '2026-05-05', franjas: [{ inicio: '23:59', fin: '23:59' }] }]);
    expect(result.fines[0]).toEqual({ valor: '23:00', etiqueta: '23:00' });
    expect(result.fines.at(-1)).toEqual({ valor: '23:59', etiqueta: '23:59' });
    expect(availableHours([], '', '').inicios).toEqual([]);
  });
});
