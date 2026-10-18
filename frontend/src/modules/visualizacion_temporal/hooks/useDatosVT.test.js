/**
 * Pruebas de la coordinación entre la detección y las consultas de eventos.
 *
 * La detección reescribe los eventos de la sesión con identificadores nuevos. Una consulta que
 * salió antes de que terminara leía la lista vieja (o a medio reescribir) y, como aún no tenía
 * datos, la invalidación posterior no la relanzaba: el detalle buscaba un evento nuevo en una
 * lista vieja y mostraba «Handover — de 581».
 */

import { createElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDeteccion, useTodosLosHandovers } from './useDatosVT.js';
import { useVisStore } from '../store/visStore.js';

/** Peticiones de `GET /handovers` aún sin responder, en orden de llegada. */
let pendientes = [];

function responder(peticion, ids) {
  const items = ids.map((id) => ({ id_evento: id }));
  peticion.resolver({
    ok: true,
    status: 200,
    json: async () => ({ total: items.length, page: 1, page_size: 500, items }),
  });
}

beforeEach(() => {
  pendientes = [];
  useVisStore.getState().reiniciar();
  useVisStore.getState().setSesion('s1');

  vi.stubGlobal(
    'fetch',
    vi.fn((url, opciones) => {
      if (String(url).includes('/detectar-handovers')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ total_handovers: 2 }) });
      }
      return new Promise((resolver, rechazar) => {
        const peticion = { resolver };
        pendientes.push(peticion);
        opciones?.signal?.addEventListener('abort', () =>
          rechazar(new DOMException('Cancelada', 'AbortError')),
        );
      });
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const envoltorio = ({ children }) => createElement(QueryClientProvider, { client: queryClient }, children);
  return renderHook(
    () => ({ eventos: useTodosLosHandovers(), deteccion: useDeteccion() }),
    { wrapper: envoltorio },
  );
}

describe('eventos y detección', () => {
  it('una lista que estaba en vuelo al terminar la detección se vuelve a pedir', async () => {
    const { result } = montar();
    await waitFor(() => expect(pendientes).toHaveLength(1));
    const vieja = pendientes[0];

    // La detección termina mientras la primera lista sigue sin respuesta.
    act(() => {
      result.current.deteccion.mutate({ sesionIds: ['s1'] });
    });
    await waitFor(() => expect(pendientes).toHaveLength(2));

    // La respuesta vieja llega tarde y no debe contar; la nueva trae los identificadores nuevos.
    act(() => responder(vieja, ['viejo-1', 'viejo-2']));
    act(() => responder(pendientes[1], ['nuevo-1', 'nuevo-2']));

    await waitFor(() =>
      expect(result.current.eventos.data?.items.map((e) => e.id_evento)).toEqual(['nuevo-1', 'nuevo-2']),
    );
  });
});
