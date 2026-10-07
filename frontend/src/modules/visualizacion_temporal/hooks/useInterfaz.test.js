/**
 * Pruebas de los ayudantes de interfaz con tiempo: el aviso pasajero y el valor diferido.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAvisoTemporal, useValorDiferido } from './useInterfaz.js';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('useAvisoTemporal', () => {
  it('muestra el aviso y lo oculta solo a los 3 segundos', () => {
    const { result } = renderHook(({ clave }) => useAvisoTemporal(clave), {
      initialProps: { clave: 1 },
    });

    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(2999));
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(false);
  });

  it('un aviso nuevo se vuelve a mostrar', () => {
    const { result, rerender } = renderHook(({ clave }) => useAvisoTemporal(clave), {
      initialProps: { clave: 1 },
    });
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current).toBe(false);

    rerender({ clave: 2 });

    expect(result.current).toBe(true);
  });

  it('sin aviso no muestra nada', () => {
    const { result } = renderHook(() => useAvisoTemporal(null));

    expect(result.current).toBe(false);
  });
});

describe('useValorDiferido', () => {
  it('entrega el valor cuando deja de cambiar', () => {
    const { result, rerender } = renderHook(({ valor }) => useValorDiferido(valor, 250), {
      initialProps: { valor: 1 },
    });

    rerender({ valor: 2 });
    rerender({ valor: 3 });
    expect(result.current).toBe(1);

    act(() => vi.advanceTimersByTime(250));
    expect(result.current).toBe(3);
  });
});
