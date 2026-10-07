/**
 * Pruebas de la tabla de eventos (Fase 5, tarea 5.6) — HU-C2-009.
 *
 * Lo que se protege aquí:
 * - **arranca plegada y con el primer evento elegido**, para que su detalle y su gráfica se vean
 *   sin hacer nada;
 * - «Desplegar» muestra la tabla completa, y elegir una fila la vuelve a plegar con ese evento;
 * - elegir un evento **no amplía las gráficas de abajo**: el zoom del store no se toca.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import HandoverTable from './HandoverTable.jsx';
import { useVisStore } from '../store/visStore.js';

const EVENTOS = [
  {
    id_evento: 'ev-1',
    sesion_id: 's1',
    timestamp_evento: '2026-07-01T13:01:30Z',
    celda_origen: { clave: 'LTE:7213766', psc_pci: 461 },
    celda_destino: { clave: 'LTE:7390405', psc_pci: 460 },
    tipo_evento: 'intra_frecuencia',
    ping_pong: false,
    confianza: 'alta',
    delta_rsrp_db: 14,
    delta_rsrq_db: -3,
    delta_rssnr_db: null,
    duracion_permanencia_s: 89,
  },
  {
    id_evento: 'ev-2',
    sesion_id: 's1',
    timestamp_evento: '2026-07-01T13:03:00Z',
    celda_origen: { clave: 'LTE:7390405', psc_pci: 460 },
    celda_destino: { clave: 'WCDMA:13163:30405', psc_pci: null },
    tipo_evento: 'inter_rat',
    ping_pong: true,
    confianza: 'baja',
    delta_rsrp_db: -6,
    delta_rsrq_db: null,
    delta_rssnr_db: null,
    duracion_permanencia_s: 12,
  },
];

let respuesta = { total: 2, page: 1, page_size: 15, items: EVENTOS };

beforeEach(() => {
  useVisStore.getState().reiniciar();
  useVisStore.getState().setSesion('s1');

  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => respuesta })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  respuesta = { total: 2, page: 1, page_size: 15, items: EVENTOS };
});

function renderizar(
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } }),
) {

  return render(
    <QueryClientProvider client={queryClient}>
      <HandoverTable />
    </QueryClientProvider>,
  );
}

/** Renderiza con la tabla ya desplegada, para mirar sus columnas. */
async function renderizarDesplegada() {
  const usuario = userEvent.setup();
  renderizar();
  await usuario.click(await screen.findByRole('button', { name: 'Desplegar' }));
  await screen.findByText('LTE:7213766');
  return usuario;
}

describe('estado por defecto', () => {
  it('arranca plegada y con el primer evento elegido', async () => {
    renderizar();

    await waitFor(() => expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1'));
    expect(useVisStore.getState().tablaColapsada).toBe(true);
    expect(document.querySelector('.vt-lista-compacta')).toBeInTheDocument();
    expect(document.querySelector('.vt-lista-compacta__item--activo')).not.toBeNull();
  });

  it('la selección por defecto no toca el zoom de las gráficas', async () => {
    renderizar();

    await waitFor(() => expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1'));
    expect(useVisStore.getState().rangoZoom).toBeNull();
  });

  it('si el usuario ya eligió un evento, no se le cambia por el primero', async () => {
    useVisStore.getState().seleccionarHandover('ev-2');
    renderizar();

    await screen.findByRole('button', { name: 'Desplegar' });
    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2');
  });

  it('al cambiar un filtro se vuelve a elegir el primero de la lista nueva', async () => {
    renderizar();
    await waitFor(() => expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1'));

    // Con el filtro solo queda ev-2: debe elegirse ese, no el primero de la lista anterior.
    respuesta = { total: 1, page: 1, page_size: 15, items: [EVENTOS[1]] };
    useVisStore.getState().toggleTecnologia('WCDMA');

    await waitFor(() => expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2'));
    expect(useVisStore.getState().seleccionPendiente).toBe(false);
  });
});

describe('renderizado de la tabla completa', () => {
  it('muestra una fila por evento', async () => {
    await renderizarDesplegada();

    expect(document.querySelectorAll('.vt-tabla__fila')).toHaveLength(2);
  });

  it('muestra celda origen, destino, tipo y permanencia (CA1)', async () => {
    await renderizarDesplegada();

    // Aparece dos veces y debe ser así: es el destino del primer evento y el origen del segundo.
    expect(screen.getAllByText('LTE:7390405')).toHaveLength(2);

    expect(screen.getByText('Intra-frecuencia')).toBeInTheDocument();
    expect(screen.getByText('89 s')).toBeInTheDocument();
  });

  it('marca la confianza baja y no muestra el ping-pong, que no se tiene en cuenta', async () => {
    await renderizarDesplegada();

    expect(screen.getByText('confianza baja')).toBeInTheDocument();
    // ev-2 viene marcado como ping-pong desde el backend: la interfaz no lo enseña.
    expect(screen.queryByText(/ping-pong/i)).not.toBeInTheDocument();
  });

  it('muestra los deltas con signo', async () => {
    await renderizarDesplegada();

    expect(screen.getByText(/\+14\.0 dB/)).toBeInTheDocument();
    expect(screen.getByText(/-6\.0 dB/)).toBeInTheDocument();
  });

  it('un delta ausente se muestra como raya, no como cero', async () => {
    // `null` es "no se pudo medir" y 0 es "no cambió": confundirlos falsearía la lectura.
    await renderizarDesplegada();

    const rayas = screen.getAllByTitle('Sin medida en alguno de los extremos');
    expect(rayas.length).toBeGreaterThanOrEqual(2);
    expect(rayas[0]).toHaveTextContent('—');
  });
});

describe('elegir un evento', () => {
  it('desplegar muestra la tabla completa y oculta el detalle', async () => {
    await renderizarDesplegada();

    expect(useVisStore.getState().tablaColapsada).toBe(false);
    expect(document.querySelector('.vt-lista-compacta')).toBeNull();
  });

  it('al desplegar, la fila del evento que se analizaba queda resaltada y a la vista', async () => {
    const desplazar = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = desplazar;

    await renderizarDesplegada();

    const fila = screen.getByText('LTE:7213766').closest('tr');
    expect(fila.className).toContain('vt-tabla__fila--seleccionada');
    expect(desplazar).toHaveBeenCalled();
  });

  it('elegir una fila la selecciona y vuelve a plegar la tabla', async () => {
    const usuario = await renderizarDesplegada();

    await usuario.click(screen.getByText('WCDMA:13163:30405').closest('tr'));

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2');
    expect(useVisStore.getState().tablaColapsada).toBe(true);
    expect(document.querySelector('.vt-lista-compacta')).toBeInTheDocument();
  });

  it('elegir un evento no amplía las gráficas: siguen mostrando el recorrido completo', async () => {
    const usuario = await renderizarDesplegada();

    await usuario.click(screen.getByText('WCDMA:13163:30405').closest('tr'));

    expect(useVisStore.getState().rangoZoom).toBeNull();
  });

  it('volver a pulsar el mismo evento tras desplegar lo pliega otra vez', async () => {
    const usuario = await renderizarDesplegada();

    await usuario.click(screen.getByText('LTE:7213766').closest('tr'));

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1');
    expect(useVisStore.getState().tablaColapsada).toBe(true);
  });

  it('se puede seleccionar con el teclado', async () => {
    const usuario = await renderizarDesplegada();

    const fila = screen.getByText('WCDMA:13163:30405').closest('tr');
    fila.focus();
    await usuario.keyboard('{Enter}');

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2');
  });

  it('en la lista plegada se elige otro evento con un clic', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await screen.findByRole('button', { name: 'Desplegar' });
    const items = [...document.querySelectorAll('.vt-lista-compacta__item')];
    await usuario.click(items[1]);

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2');
  });

  it('plegada no marca el ping-pong', async () => {
    renderizar();

    await screen.findByRole('button', { name: 'Desplegar' });
    expect(document.querySelector('.vt-lista-compacta')).not.toHaveTextContent('PP');
  });

  it('plegada solo muestra el número y la fecha/hora', async () => {
    renderizar();

    await screen.findByRole('button', { name: 'Desplegar' });
    const item = document.querySelector('.vt-lista-compacta__item');

    // Las claves de celda ocupan demasiado en una columna estrecha: quedan fuera.
    expect(item.textContent).not.toContain('LTE:7213766');
    expect(item.querySelector('.vt-lista-compacta__hora')).not.toBeNull();
  });
});

describe('ordenación', () => {
  it('invierte el orden al pulsar dos veces la misma columna', async () => {
    const usuario = await renderizarDesplegada();

    const cabecera = screen.getByText(/Δ RSRP/);
    const filas = () => [...document.querySelectorAll('.vt-tabla__fila')];

    await usuario.click(cabecera);
    expect(within(filas()[0]).getByText(/-6\.0 dB/)).toBeInTheDocument();

    await usuario.click(cabecera);
    expect(within(filas()[0]).getByText(/\+14\.0 dB/)).toBeInTheDocument();
  });

  it('los valores ausentes van al final ordene como ordene', async () => {
    const usuario = await renderizarDesplegada();

    await usuario.click(screen.getByText(/Δ RSRQ/));

    const filas = [...document.querySelectorAll('.vt-tabla__fila')];
    // ev-2 tiene delta_rsrq_db null, así que debe quedar el último.
    expect(within(filas[1]).getByText('WCDMA:13163:30405')).toBeInTheDocument();
  });
});

describe('estado vacío', () => {
  it('sin eventos sugiere ampliar los filtros: ya no hay que pulsar «Detectar handovers»', async () => {
    respuesta = { total: 0, page: 1, page_size: 15, items: [] };
    renderizar();

    expect(await screen.findByText(/No hay handovers para estos filtros/)).toBeInTheDocument();
    expect(screen.getByText(/ampliar las fechas/)).toBeInTheDocument();
    expect(screen.queryByText(/Detectar handovers/)).not.toBeInTheDocument();
    expect(useVisStore.getState().handoverSeleccionadoId).toBeNull();
  });
});

describe('detección automática en curso', () => {
  it('muestra «Detectando handovers…» y no elige ningún evento de la lista que va a cambiar', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    // Una detección que no termina: basta con que exista para que la tabla espere.
    queryClient
      .getMutationCache()
      .build(queryClient, { mutationKey: ['vt', 'deteccion'], mutationFn: () => new Promise(() => {}) })
      .execute(undefined);

    renderizar(queryClient);

    expect(await screen.findByText('Detectando handovers…')).toBeInTheDocument();
    expect(useVisStore.getState().handoverSeleccionadoId).toBeNull();
  });
});
