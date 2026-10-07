/**
 * Pruebas de la transformación a ECharts (Fase 5, tarea 5.6).
 *
 * Son funciones puras, así que se prueban sin renderizar nada. Lo que se protege aquí es que la
 * gráfica no mienta: que los huecos sigan siendo huecos, que un parámetro sin medidas no se
 * confunda con uno a cero, y que los ejes no mezclen dBm con dB.
 */

import { describe, expect, it } from 'vitest';

import {
  EJE_POR_PARAMETRO,
  altoHistograma,
  indiceDeRotulo,
  rotulosCeldas,
  construirMarcadoresHO,
  construirSeriesEcharts,
  instantesConHuecosDatables,
} from './useSeriesEcharts.js';

const RESPUESTA = {
  t: ['2026-07-01T13:00:00Z', '2026-07-01T13:00:01Z', null, '2026-07-01T13:00:30Z'],
  series: {
    rsrp_dbm: [-82, -83, null, -90],
    rsrq_db: [-9, null, null, -12],
    rssnr_db: [null, null, null, null],
  },
  cobertura: [
    { parametro: 'rsrp_dbm', disponible: true, n_validos: 3, n_mediciones: 4 },
    { parametro: 'rsrq_db', disponible: true, n_validos: 2, n_mediciones: 4 },
    { parametro: 'rssnr_db', disponible: false, n_validos: 0, n_mediciones: 4 },
  ],
};

describe('construirSeriesEcharts', () => {
  it('devuelve una serie por parámetro pedido', () => {
    const series = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm', 'rsrq_db']);

    expect(series).toHaveLength(2);
    expect(series.map((s) => s.id)).toEqual(['rsrp_dbm', 'rsrq_db']);
  });

  it('empareja cada valor con su instante por índice', () => {
    const [rsrp] = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm']);

    expect(rsrp.data[0]).toEqual(['2026-07-01T13:00:00Z', -82]);
    expect(rsrp.data[1]).toEqual(['2026-07-01T13:00:01Z', -83]);
    expect(rsrp.data[3]).toEqual(['2026-07-01T13:00:30Z', -90]);
  });

  it('conserva los nulos y no los une', () => {
    // Sin esto, la gráfica dibujaría una recta sobre un intervalo en el que no se midió nada.
    const [rsrp] = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm']);

    expect(rsrp.connectNulls).toBe(false);
    expect(rsrp.data.filter(([, v]) => v === null)).toHaveLength(1);
  });

  it('el corte de línea lleva un instante válido, nunca un x nulo', () => {
    // Un eje `type: 'time'` con coordenada X nula produce NaN al calcular la extensión y
    // deja el gráfico colgado, bloqueando la pestaña.
    const [rsrp] = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm']);

    expect(rsrp.data.every(([x]) => x !== null && x !== undefined)).toBe(true);

    const corte = rsrp.data[2];
    expect(corte[1]).toBeNull();
    expect(new Date(corte[0]).getTime()).toBeGreaterThan(
      new Date('2026-07-01T13:00:01Z').getTime(),
    );
    expect(new Date(corte[0]).getTime()).toBeLessThan(
      new Date('2026-07-01T13:00:30Z').getTime(),
    );
  });

  it('separa las potencias en dBm de las relaciones en dB', () => {
    // Compartir eje aplastaría ambas curvas: −140…−40 dBm contra −20…+30 dB.
    const series = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm', 'rsrq_db', 'rssnr_db']);
    const porId = Object.fromEntries(series.map((s) => [s.id, s.yAxisIndex]));

    expect(porId.rsrp_dbm).toBe(0);
    expect(porId.rsrq_db).toBe(1);
    expect(porId.rssnr_db).toBe(1);
  });

  it('todos los parámetros tienen eje asignado', () => {
    expect(Object.keys(EJE_POR_PARAMETRO).sort()).toEqual(
      ['rsrp_dbm', 'rsrq_db', 'rssi_dbm', 'rssnr_db'].sort(),
    );
  });

  it('marca como sin datos el parámetro que no tiene ninguna medida', () => {
    const series = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm', 'rssnr_db']);
    const porId = Object.fromEntries(series.map((s) => [s.id, s.sinDatos]));

    expect(porId.rsrp_dbm).toBe(false);
    expect(porId.rssnr_db).toBe(true);
  });

  it('devuelve la serie del parámetro sin datos en lugar de omitirla', () => {
    // Omitirla escondería que el terminal no midió ese parámetro (decisión D-5).
    const series = construirSeriesEcharts(RESPUESTA, ['rssnr_db']);

    expect(series).toHaveLength(1);
    expect(series[0].data.every(([, v]) => v === null)).toBe(true);
  });

  it('usa el color fijo del parámetro', () => {
    const [rsrp] = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm']);

    expect(rsrp.lineStyle.color).toBe(rsrp.itemStyle.color);
    expect(rsrp.lineStyle.color).toMatch(/^#/);
  });

  it('respeta las capas activas y su orden', () => {
    const series = construirSeriesEcharts(RESPUESTA, ['rsrq_db', 'rsrp_dbm']);

    expect(series.map((s) => s.id)).toEqual(['rsrq_db', 'rsrp_dbm']);
  });

  it('ignora un parámetro que el backend no devolvió', () => {
    const series = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm', 'rssi_dbm']);

    expect(series.map((s) => s.id)).toEqual(['rsrp_dbm']);
  });

  it('con una respuesta vacía devuelve una lista vacía sin romper', () => {
    expect(construirSeriesEcharts(null, ['rsrp_dbm'])).toEqual([]);
    expect(construirSeriesEcharts({ t: [], series: {} }, ['rsrp_dbm'])).toEqual([]);
  });

  it('activa la ruta de dibujado optimizada para series largas', () => {
    const [rsrp] = construirSeriesEcharts(RESPUESTA, ['rsrp_dbm']);

    expect(rsrp.large).toBe(true);
    expect(rsrp.sampling).toBe('lttb');
  });
});

describe('construirMarcadoresHO', () => {
  const HANDOVERS = [
    {
      id_evento: 'ev-1',
      timestamp_evento: '2026-07-01T13:01:30Z',
      celda_origen: { clave: 'LTE:1' },
      celda_destino: { clave: 'LTE:2' },
      tipo_evento: 'intra_frecuencia',
      ping_pong: false,
    },
    {
      id_evento: 'ev-2',
      timestamp_evento: '2026-07-01T13:03:00Z',
      celda_origen: { clave: 'LTE:2' },
      celda_destino: { clave: 'LTE:1' },
      tipo_evento: 'intra_frecuencia',
      ping_pong: true,
    },
  ];

  it('coloca un marcador en cada instante de handover', () => {
    const marcadores = construirMarcadoresHO(HANDOVERS);

    expect(marcadores.data).toHaveLength(2);
    expect(marcadores.data.map((m) => m.xAxis)).toEqual([
      '2026-07-01T13:01:30Z',
      '2026-07-01T13:03:00Z',
    ]);
  });

  it('guarda origen y destino para el tooltip', () => {
    const [primero] = construirMarcadoresHO(HANDOVERS).data;

    expect(primero.origen).toBe('LTE:1');
    expect(primero.destino).toBe('LTE:2');
  });

  it('los marcadores son líneas continuas, no discontinuas', () => {
    const { data } = construirMarcadoresHO(HANDOVERS, 'ev-2');

    expect(data.every((m) => m.lineStyle.type === 'solid')).toBe(true);
  });

  it('destaca el marcador seleccionado con otro color, más grosor y sombra', () => {
    const { data } = construirMarcadoresHO(HANDOVERS, 'ev-2');

    expect(data[1].lineStyle.color).not.toBe(data[0].lineStyle.color);
    expect(data[1].lineStyle.width).toBeGreaterThan(data[0].lineStyle.width);
    expect(data[1].lineStyle.shadowBlur).toBeGreaterThan(0);
    expect(data[0].lineStyle.shadowBlur ?? 0).toBe(0);
  });

  it('todos los marcadores no seleccionados comparten un único color', () => {
    const { data } = construirMarcadoresHO(HANDOVERS, null);

    expect(new Set(data.map((m) => m.lineStyle.color)).size).toBe(1);
  });

  it('todos los marcadores se dibujan aunque no haya ninguno seleccionado', () => {
    // Los handovers son el mapa de donde ocurrieron los traspasos: deben verse siempre,
    // no solo cuando se pincha uno en la tabla.
    const { data } = construirMarcadoresHO(HANDOVERS, null);

    expect(data).toHaveLength(2);
    expect(data.every((m) => m.lineStyle.opacity >= 0.9)).toBe(true);
  });

  it('sin handovers no devuelve marcadores', () => {
    expect(construirMarcadoresHO([])).toBeNull();
  });
});

describe('instantesConHuecosDatables', () => {
  it('sitúa el corte en el punto medio del hueco', () => {
    const salida = instantesConHuecosDatables([
      '2026-07-01T13:00:00Z',
      null,
      '2026-07-01T13:00:10Z',
    ]);

    expect(salida[1]).toBe('2026-07-01T13:00:05.000Z');
  });

  it('nunca deja una coordenada X nula si hay algún instante válido', () => {
    const salida = instantesConHuecosDatables([null, '2026-07-01T13:00:00Z', null]);

    expect(salida.every((x) => x !== null)).toBe(true);
  });

  it('deja intactos los instantes sin huecos', () => {
    const entrada = ['2026-07-01T13:00:00Z', '2026-07-01T13:00:01Z'];

    expect(instantesConHuecosDatables(entrada)).toEqual(entrada);
  });
});


describe('histograma horizontal de radiobases', () => {
  const CELDAS = [
    { celda_clave: 'LTE:7279051', etiqueta: 'PCI 283', arfcn: 700 },
    { celda_clave: 'GSM:13163:30405', etiqueta: 'GSM CID 30405', arfcn: 62 },
  ];

  it('rotula cada barra con el PCI/PSC que envía el backend', () => {
    expect(rotulosCeldas(CELDAS)).toEqual(['PCI 283', 'GSM CID 30405']);
  });

  it('no añade el canal: las celdas que comparten PCI ya vienen sumadas en una barra', () => {
    const agrupada = [
      {
        celda_clave: 'LTE:7174347',
        etiqueta: 'PCI 407',
        arfcn: 700,
        celdas_incluidas: ['LTE:7174347', 'LTE:7174354'],
        canales: [700, 850],
      },
    ];

    expect(rotulosCeldas(agrupada)).toEqual(['PCI 407']);
  });

  it('el alto crece con el número de celdas y nunca queda aplastado', () => {
    expect(altoHistograma(1)).toBeGreaterThanOrEqual(180);
    expect(altoHistograma(20)).toBeGreaterThan(altoHistograma(8));
  });

  it('localiza la barra del rótulo sobre el que pasa el ratón', () => {
    // Es lo que permite ver el nombre completo de una celda truncada.
    const evento = { componentType: 'yAxis', value: 'GSM CID 30405' };
    expect(indiceDeRotulo(evento, rotulosCeldas(CELDAS))).toBe(1);
  });

  it('ignora eventos que no vienen de un rótulo', () => {
    expect(indiceDeRotulo({ componentType: 'series', value: 2 }, rotulosCeldas(CELDAS))).toBe(-1);
  });
});
