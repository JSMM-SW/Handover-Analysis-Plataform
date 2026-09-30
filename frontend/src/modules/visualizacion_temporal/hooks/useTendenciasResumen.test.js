/**
 * Pruebas de las tendencias de las tarjetas de resumen (rediseño «Warm & Calm»).
 *
 * Son funciones puras. Lo que se protege es que los sparklines no mientan: que un intervalo sin
 * eventos cuente cero, que las radiobases acumuladas nunca bajen y que un hueco de captura se vea
 * como hueco.
 */

import { describe, expect, it } from 'vitest';

import {
  construirBarrasSparkline,
  construirTrazoSparkline,
  handoversPorIntervalo,
  medicionesPorIntervalo,
  radiobasesAcumuladas,
  rangoTemporal,
  tasaAcumuladaPorIntervalo,
} from './useTendenciasResumen.js';

const T0 = Date.parse('2026-07-01T13:00:00Z');
const iso = (segundos) => new Date(T0 + segundos * 1000).toISOString();

/** Rango de 10 minutos. */
const RANGO = [T0, T0 + 600_000];

describe('rangoTemporal', () => {
  it('usa los límites del resumen cuando los hay', () => {
    expect(rangoTemporal({ inicio: iso(0), fin: iso(600) })).toEqual(RANGO);
  });

  it('recurre a los tramos si el resumen no trae límites', () => {
    const tramos = [
      { inicio: iso(0), fin: iso(100) },
      { inicio: iso(100), fin: iso(600) },
    ];
    expect(rangoTemporal({ tramos })).toEqual(RANGO);
  });

  it('devuelve null si el rango no tiene duración', () => {
    expect(rangoTemporal({ inicio: iso(10), fin: iso(10) })).toBeNull();
    expect(rangoTemporal({})).toBeNull();
  });
});

describe('handoversPorIntervalo', () => {
  const eventos = [0, 30, 290, 599].map((s) => ({ timestamp_evento: iso(s) }));

  it('reparte los eventos en intervalos iguales', () => {
    expect(handoversPorIntervalo(eventos, RANGO, 2)).toEqual([3, 1]);
  });

  it('el instante final cae en el último intervalo, no fuera', () => {
    const cuentas = handoversPorIntervalo([{ timestamp_evento: iso(600) }], RANGO, 4);
    expect(cuentas).toEqual([0, 0, 0, 1]);
  });

  it('sin rango no hay serie', () => {
    expect(handoversPorIntervalo(eventos, null)).toBeNull();
  });
});

describe('tasaAcumuladaPorIntervalo', () => {
  it('al final coincide con la tasa global del recorrido', () => {
    // 4 handovers en 10 min = 0,4 HO/min, la misma cifra que muestra la tarjeta.
    const eventos = [0, 30, 290, 599].map((s) => ({ timestamp_evento: iso(s) }));
    const tasa = tasaAcumuladaPorIntervalo(eventos, RANGO, 5);

    expect(tasa.at(-1)).toBeCloseTo(0.4);
  });
});

describe('radiobasesAcumuladas', () => {
  it('cuenta celdas distintas y nunca decrece aunque se vuelva a una celda', () => {
    const tramos = [
      { inicio: iso(0), fin: iso(100), celda_clave: 'A' },
      { inicio: iso(100), fin: iso(300), celda_clave: 'B' },
      { inicio: iso(300), fin: iso(600), celda_clave: 'A' },
    ];
    const serie = radiobasesAcumuladas(tramos, RANGO, 3);

    expect(serie).toEqual([2, 2, 2]);
    expect(serie.every((v, i) => i === 0 || v >= serie[i - 1])).toBe(true);
  });
});

describe('medicionesPorIntervalo', () => {
  it('reparte las mediciones de cada tramo según su solape', () => {
    const tramos = [{ inicio: iso(0), fin: iso(600), n_mediciones: 600 }];
    expect(medicionesPorIntervalo(tramos, RANGO, 2)).toEqual([300, 300]);
  });

  it('un hueco de captura deja el intervalo a cero', () => {
    const tramos = [{ inicio: iso(0), fin: iso(300), n_mediciones: 300 }];
    expect(medicionesPorIntervalo(tramos, RANGO, 2)).toEqual([300, 0]);
  });
});

describe('construirTrazoSparkline', () => {
  it('necesita al menos dos puntos', () => {
    expect(construirTrazoSparkline([5])).toBeNull();
    expect(construirTrazoSparkline(null)).toBeNull();
  });

  it('el máximo queda arriba y el mínimo abajo', () => {
    const { linea } = construirTrazoSparkline([0, 10], { ancho: 100, alto: 20, margen: 0 });
    expect(linea).toBe('M0 20 L100 0');
  });

  it('una serie plana se dibuja centrada, sin dividir por cero', () => {
    const { linea } = construirTrazoSparkline([3, 3, 3], { ancho: 100, alto: 20 });
    expect(linea).toBe('M0 10 L50 10 L100 10');
  });

  it('el área cierra contra la base', () => {
    const { area } = construirTrazoSparkline([1, 2], { ancho: 100, alto: 20 });
    expect(area.endsWith('L100 20 L0 20 Z')).toBe(true);
  });
});

describe('construirBarrasSparkline', () => {
  it('una barra por intervalo, proporcional al máximo', () => {
    const barras = construirBarrasSparkline([0, 5, 10], { ancho: 30, alto: 20, hueco: 0 });

    expect(barras).toHaveLength(3);
    expect(barras[2].alto).toBe(20);
    expect(barras[1].alto).toBe(10);
  });

  it('un intervalo vacío deja un trazo mínimo visible, no desaparece', () => {
    const [vacia] = construirBarrasSparkline([0, 4], { alto: 20 });
    expect(vacia.alto).toBe(1);
  });
});
