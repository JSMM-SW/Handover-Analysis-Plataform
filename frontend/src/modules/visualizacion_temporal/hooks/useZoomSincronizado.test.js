/**
 * Pruebas del zoom compartido entre la línea de tiempo y la secuencia de radiobases.
 *
 * ECharts no pinta en jsdom, así que se sustituye la instancia por un doble que registra lo que se
 * le despacha. Lo que se protege: que el zoom del usuario llegue al store, que el del store se
 * aplique a la gráfica y que un zoom aplicado por el propio código no vuelva al store (el bucle
 * que congelaba la pestaña).
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useOpcionSecuenciaCeldas } from './useSeriesEcharts.js';
import { useZoomSincronizado } from './useZoomSincronizado.js';
import { useVisStore } from '../store/visStore.js';

const INICIO = Date.parse('2026-07-07T17:00:00Z');
const FIN = Date.parse('2026-07-07T17:30:00Z');

/** Doble de la instancia de ECharts con un zoom fijo. */
function instanciaFalsa() {
  return {
    dispatchAction: vi.fn(),
    getOption: () => ({ dataZoom: [{ startValue: INICIO, endValue: FIN }] }),
  };
}

function montar(opcion = {}) {
  const instancia = instanciaFalsa();
  const hook = renderHook(({ opcion: o }) => useZoomSincronizado(o), {
    initialProps: { opcion },
  });
  hook.result.current.referencia.current = { getEchartsInstance: () => instancia };
  return { ...hook, instancia };
}

beforeEach(() => {
  vi.useFakeTimers();
  useVisStore.getState().reiniciar();
});

afterEach(() => vi.useRealTimers());

describe('useZoomSincronizado', () => {
  it('el zoom del usuario se escribe en el store, con un pequeño retardo', () => {
    const { result } = montar();

    act(() => result.current.onEvents.dataZoom());
    expect(useVisStore.getState().rangoZoom).toBeNull();

    act(() => vi.advanceTimersByTime(250));
    expect(useVisStore.getState().rangoZoom).toEqual([
      new Date(INICIO).toISOString(),
      new Date(FIN).toISOString(),
    ]);
  });

  it('el rango del store se aplica a la gráfica', () => {
    const { instancia, rerender } = montar();

    act(() => useVisStore.getState().setRangoZoom(['2026-07-07T17:05:00.000Z', '2026-07-07T17:10:00.000Z']));
    rerender({ opcion: {} });

    expect(instancia.dispatchAction).toHaveBeenCalledWith({
      type: 'dataZoom',
      startValue: Date.parse('2026-07-07T17:05:00Z'),
      endValue: Date.parse('2026-07-07T17:10:00Z'),
    });
  });

  it('un zoom aplicado por el código no vuelve al store', () => {
    const { result, rerender } = montar();
    const rango = ['2026-07-07T17:05:00.000Z', '2026-07-07T17:10:00.000Z'];

    act(() => useVisStore.getState().setRangoZoom(rango));
    rerender({ opcion: {} });
    // ECharts emite su evento justo después del dispatchAction.
    act(() => result.current.onEvents.dataZoom());
    act(() => vi.advanceTimersByTime(250));

    expect(useVisStore.getState().rangoZoom).toEqual(rango);
  });

  it('al reconstruirse la gráfica (otra opción) se vuelve a aplicar el rango', () => {
    const { instancia, rerender } = montar();
    act(() => useVisStore.getState().setRangoZoom(['2026-07-07T17:05:00.000Z', '2026-07-07T17:10:00.000Z']));
    rerender({ opcion: {} });
    instancia.dispatchAction.mockClear();

    // Por ejemplo, al elegir otro handover cambia el marcador destacado y la opción es otra.
    rerender({ opcion: { otra: true } });

    expect(instancia.dispatchAction).toHaveBeenCalledTimes(1);
  });
});

describe('secuencia de radiobases', () => {
  const TRAMOS = [
    {
      inicio: '2026-07-07T17:00:00Z',
      fin: '2026-07-07T17:20:00Z',
      valor_normalizado: 0,
      etiqueta: 'PCI 37',
      celda_clave: 'LTE:1',
      n_mediciones: 1200,
      duracion_s: 1200,
    },
  ];

  it('tiene el mismo zoom que la línea de tiempo: rueda del ratón y deslizador', () => {
    const { result } = renderHook(() => useOpcionSecuenciaCeldas({ tramos: TRAMOS }));

    expect(result.current.dataZoom.map((z) => z.type)).toEqual(['inside', 'slider']);
  });

  it('el zoom no quita puntos: un tramo más largo que la ventana sigue viéndose', () => {
    const { result } = renderHook(() => useOpcionSecuenciaCeldas({ tramos: TRAMOS }));

    expect(result.current.dataZoom.every((z) => z.filterMode === 'none')).toBe(true);
  });
});
