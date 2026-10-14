/**
 * Pruebas de la carga de todos los handovers.
 *
 * Los marcadores de las gráficas y la navegación del detalle pedían una sola página de 500: con
 * la Sesión 4 (581 eventos) faltaban los últimos 81 y el detalle decía «Handover 1 de 500».
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { obtenerTodosLosHandovers } from './visualizacionTemporal.api.js';

/** Eventos de prueba numerados, en el orden en que los devuelve el backend. */
function eventos(desde, hasta) {
  return Array.from({ length: hasta - desde }, (_, i) => ({ id_evento: `ev-${desde + i}` }));
}

let total = 0;
let paginasPedidas = [];

beforeEach(() => {
  paginasPedidas = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      const parametros = new URL(url).searchParams;
      const page = Number(parametros.get('page'));
      const pageSize = Number(parametros.get('page_size'));
      paginasPedidas.push({ page, pageSize });

      const desde = (page - 1) * pageSize;
      const cuerpo = {
        total,
        page,
        page_size: pageSize,
        items: eventos(desde, Math.min(desde + pageSize, total)),
      };
      return { ok: true, status: 200, json: async () => cuerpo };
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

const FILTROS = { sesionIds: ['s4'] };

describe('obtenerTodosLosHandovers', () => {
  it('con más de 500 eventos pide todas las páginas y las junta en orden', async () => {
    total = 581;

    const respuesta = await obtenerTodosLosHandovers(FILTROS);

    expect(paginasPedidas).toEqual([
      { page: 1, pageSize: 500 },
      { page: 2, pageSize: 500 },
    ]);
    expect(respuesta.total).toBe(581);
    expect(respuesta.items).toHaveLength(581);
    expect(respuesta.items.at(0).id_evento).toBe('ev-0');
    expect(respuesta.items.at(-1).id_evento).toBe('ev-580');
  });

  it('si caben en una página no hace más peticiones', async () => {
    total = 39;

    const respuesta = await obtenerTodosLosHandovers(FILTROS);

    expect(paginasPedidas).toHaveLength(1);
    expect(respuesta.items).toHaveLength(39);
  });

  it('sin eventos devuelve la lista vacía', async () => {
    total = 0;

    const respuesta = await obtenerTodosLosHandovers(FILTROS);

    expect(paginasPedidas).toHaveLength(1);
    expect(respuesta.items).toEqual([]);
  });
});
