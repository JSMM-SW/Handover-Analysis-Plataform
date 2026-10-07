/**
 * Pruebas de los rótulos del deslizador del histograma de radiobases repetidas.
 */

import { describe, expect, it } from 'vitest';

import {
  etiquetaIntervalo,
  progresoDeslizador,
  textoIntervalo,
} from './useHistogramaRepetidas.js';

describe('textoIntervalo', () => {
  it('nombra los minutos o el recorrido completo', () => {
    expect(textoIntervalo(null)).toBe('Todo el recorrido');
    expect(textoIntervalo(1)).toBe('1 minuto');
    expect(textoIntervalo(7)).toBe('7 minutos');
  });
});

describe('progresoDeslizador', () => {
  it('va de 0 % en un minuto a 100 % en el máximo', () => {
    expect(progresoDeslizador(1, 21)).toBe(0);
    expect(progresoDeslizador(11, 21)).toBe(50);
    expect(progresoDeslizador(21, 21)).toBe(100);
  });

  it('sin recorrido posible la pista se ve llena', () => {
    expect(progresoDeslizador(1, 1)).toBe(100);
    expect(progresoDeslizador(0, 0)).toBe(100);
  });
});

describe('etiquetaIntervalo', () => {
  const intervalo = {
    inicio: '2026-09-28T21:24:53Z',
    fin: '2026-09-28T21:29:53Z',
    sesion_id: 'b',
    sesion_nombre: 'Sesión 134 · Session_134_20260928.csv',
  };

  it('con una sola sesión muestra solo las horas', () => {
    const texto = etiquetaIntervalo(intervalo, false);

    expect(texto).toMatch(/–/);
    expect(texto).not.toMatch(/Sesión/);
  });

  it('con varias sesiones antepone el nombre de la suya', () => {
    expect(etiquetaIntervalo(intervalo, true)).toMatch(/^Sesión 134 · /);
  });

  it('el total no tiene horas', () => {
    expect(etiquetaIntervalo({ inicio: null, fin: null })).toBe('');
  });
});
