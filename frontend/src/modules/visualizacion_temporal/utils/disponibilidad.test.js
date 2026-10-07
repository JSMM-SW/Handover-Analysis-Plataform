/**
 * Pruebas de lo que se puede elegir en los filtros según los datos que hay.
 *
 * Son funciones puras: se prueban sin renderizar. Lo que se protege es que el calendario y la
 * franja horaria **no ofrezcan nada sin datos** y que no se pierda ningún minuto con datos.
 */

import { describe, expect, it } from 'vitest';

import {
  aHora,
  aMinutos,
  construirMes,
  diasEnRango,
  mesesConDatos,
  opcionesDeHora,
  pasoDeMinutos,
  unirFranjas,
} from './disponibilidad.js';

const dia = (fecha, franjas, n_handovers = 0) => ({
  fecha,
  n_mediciones: 100,
  n_handovers,
  franjas: franjas.map(([inicio, fin]) => ({ inicio: `${inicio}:00`, fin: `${fin}:00` })),
});

const DIAS = [
  dia('2026-07-01', [['08:00', '08:09']], 8),
  dia('2026-07-03', [['17:30', '17:35']]),
  dia('2026-09-28', [['16:24', '16:45']], 39),
];

describe('conversión de horas', () => {
  it('va y vuelve entre "HH:MM" y minutos', () => {
    expect(aMinutos('16:24:00')).toBe(984);
    expect(aHora(984)).toBe('16:24');
    expect(aHora(5)).toBe('00:05');
  });
});

describe('días en rango', () => {
  it('incluye los extremos y admite extremos abiertos', () => {
    expect(diasEnRango(DIAS, '2026-07-03', null).map((d) => d.fecha)).toEqual([
      '2026-07-03',
      '2026-09-28',
    ]);
    expect(diasEnRango(DIAS, null, '2026-07-03')).toHaveLength(2);
    expect(diasEnRango(DIAS)).toHaveLength(3);
  });
});

describe('unir franjas de varios días', () => {
  it('junta las que se solapan o se tocan y separa las demás', () => {
    const tramos = unirFranjas([
      dia('2026-07-01', [['16:00', '17:00']]),
      dia('2026-07-02', [['16:30', '18:00'], ['20:00', '20:10']]),
    ]);

    expect(tramos).toEqual([
      [aMinutos('16:00'), aMinutos('18:00')],
      [aMinutos('20:00'), aMinutos('20:10')],
    ]);
  });
});

describe('opciones de la franja horaria', () => {
  it('con pocos minutos con datos ofrece las horas de minuto en minuto', () => {
    const { paso, inicios, fines } = opcionesDeHora(DIAS, '2026-07-03', '2026-07-03');

    expect(paso).toBe(1);
    expect(inicios.map((o) => o.valor)).toEqual(['17:30', '17:31', '17:32', '17:33', '17:34', '17:35']);
    // «Hasta» llega al final del último minuto con datos (la consulta compara hora ≤ hasta).
    expect(fines.map((o) => o.valor)).toEqual(['17:31', '17:32', '17:33', '17:34', '17:35', '17:36']);
  });

  it('no ofrece horas de las pausas entre franjas', () => {
    const { inicios } = opcionesDeHora(DIAS);
    const valores = inicios.map((o) => o.valor);

    expect(valores).toContain('08:09');
    expect(valores).not.toContain('08:10');
    expect(valores).not.toContain('12:00');
    expect(valores).toContain('16:24');
  });

  it('con muchos minutos con datos espacia las opciones para que la lista no sea eterna', () => {
    const largo = [dia('2026-07-01', [['08:03', '13:58']])];
    const { paso, inicios, fines } = opcionesDeHora(largo);

    expect(paso).toBe(5);
    // El primer «desde» se redondea hacia abajo y el último «hasta» hacia arriba: no se pierde
    // ningún minuto con datos.
    expect(inicios[0].valor).toBe('08:00');
    expect(fines[fines.length - 1].valor).toBe('14:00');
  });

  it('el final del día se ofrece como el último segundo, que es una hora válida', () => {
    const { fines } = opcionesDeHora([dia('2026-07-01', [['23:55', '23:59']])]);

    expect(fines[fines.length - 1]).toEqual({ valor: '23:59:59', etiqueta: '23:59' });
  });

  it('sin días no ofrece nada', () => {
    expect(opcionesDeHora([])).toEqual({ paso: 1, inicios: [], fines: [] });
  });

  it('el paso crece con los minutos disponibles', () => {
    expect(pasoDeMinutos(180)).toBe(1);
    expect(pasoDeMinutos(181)).toBe(5);
    expect(pasoDeMinutos(901)).toBe(15);
  });
});

describe('calendario', () => {
  const porFecha = new Map(DIAS.map((d) => [d.fecha, d]));

  it('lista los meses con datos para saltar de uno a otro', () => {
    expect(mesesConDatos(DIAS)).toEqual(['2026-07', '2026-09']);
  });

  it('la semana empieza en lunes y los huecos fuera del mes van vacíos', () => {
    // El 1 de julio de 2026 es miércoles: dos huecos (lunes y martes) antes.
    const semanas = construirMes('2026-07', porFecha);

    expect(semanas[0].slice(0, 2)).toEqual([null, null]);
    expect(semanas[0][2].dia).toBe(1);
    expect(semanas.every((semana) => semana.length === 7)).toBe(true);
  });

  it('solo los días con datos son elegibles, y los que tienen handovers se marcan', () => {
    const dias = construirMes('2026-07', porFecha).flat().filter(Boolean);
    const buscar = (n) => dias.find((d) => d.dia === n);

    expect(buscar(1)).toMatchObject({ disponible: true, conHandovers: true });
    expect(buscar(2)).toMatchObject({ disponible: false, conHandovers: false });
    expect(buscar(3)).toMatchObject({ disponible: true, conHandovers: false });
    expect(dias.filter((d) => d.disponible)).toHaveLength(2);
  });

  it('marca el día elegido y lo describe para el lector de pantalla', () => {
    const elegido = construirMes('2026-07', porFecha, '2026-07-01')
      .flat()
      .find((d) => d?.seleccionada);

    expect(elegido.fecha).toBe('2026-07-01');
    expect(elegido.descripcion).toMatch(/^1 de julio de 2026, 8 handovers/);
  });
});
