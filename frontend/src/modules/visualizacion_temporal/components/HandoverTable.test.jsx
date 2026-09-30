/**
 * Pruebas de la tabla de eventos (Fase 5, tarea 5.6) — HU-C2-009.
 *
 * Lo importante que se protege aquí es el comportamiento pedido en la maqueta V1 §3: **al hacer
 * clic en una fila, el timeline hace zoom al evento**. Se comprueba mirando el store, que es lo
 * que las gráficas leen.
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

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <HandoverTable />
    </QueryClientProvider>,
  );
}

describe('renderizado', () => {
  it('muestra una fila por evento', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');
    expect(document.querySelectorAll('.vt-tabla__fila')).toHaveLength(2);
  });

  it('muestra celda origen, destino, tipo y permanencia (CA1)', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');

    // Aparece dos veces y debe ser así: es el destino del primer evento y el origen del segundo.
    expect(screen.getAllByText('LTE:7390405')).toHaveLength(2);

    expect(screen.getByText('Intra-frecuencia')).toBeInTheDocument();
    expect(screen.getByText('89 s')).toBeInTheDocument();
  });

  it('marca el ping-pong y la confianza baja', async () => {
    renderizar();

    expect(await screen.findByText('ping-pong')).toBeInTheDocument();
    expect(screen.getByText('confianza baja')).toBeInTheDocument();
  });

  it('muestra los deltas con signo', async () => {
    renderizar();

    expect(await screen.findByText(/\+14\.0 dB/)).toBeInTheDocument();
    expect(screen.getByText(/-6\.0 dB/)).toBeInTheDocument();
  });

  it('un delta ausente se muestra como raya, no como cero', async () => {
    // `null` es "no se pudo medir" y 0 es "no cambió": confundirlos falsearía la lectura.
    renderizar();

    await screen.findByText('LTE:7213766');
    const rayas = screen.getAllByTitle('Sin medida en alguno de los extremos');

    expect(rayas.length).toBeGreaterThanOrEqual(2);
    expect(rayas[0]).toHaveTextContent('—');
  });
});

describe('clic en una fila (maqueta V1 §3)', () => {
  it('selecciona el evento en el store', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const fila = (await screen.findByText('LTE:7213766')).closest('tr');
    await usuario.click(fila);

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1');
  });

  it('encuadra el timeline sobre el evento', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const fila = (await screen.findByText('LTE:7213766')).closest('tr');
    await usuario.click(fila);

    const rango = useVisStore.getState().rangoZoom;
    expect(rango).not.toBeNull();

    // El evento debe quedar en el centro de la ventana.
    const centro = (new Date(rango[0]).getTime() + new Date(rango[1]).getTime()) / 2;
    expect(centro).toBe(new Date('2026-07-01T13:01:30Z').getTime());
  });

  it('al seleccionar, la tabla se pliega para dejar sitio al detalle', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const fila = (await screen.findByText('LTE:7213766')).closest('tr');
    await usuario.click(fila);

    await waitFor(() => expect(useVisStore.getState().tablaColapsada).toBe(true));
    expect(document.querySelector('.vt-lista-compacta')).toBeInTheDocument();
  });

  it('el evento elegido queda resaltado en la lista plegada', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await usuario.click((await screen.findByText('LTE:7213766')).closest('tr'));

    const activo = await waitFor(() =>
      document.querySelector('.vt-lista-compacta__item--activo'),
    );
    expect(activo).not.toBeNull();
  });

  it('desplegar muestra la tabla completa y oculta el detalle', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await usuario.click((await screen.findByText('LTE:7213766')).closest('tr'));
    await usuario.click(await screen.findByRole('button', { name: 'Desplegar' }));

    expect(useVisStore.getState().tablaColapsada).toBe(false);
    expect(document.querySelector('.vt-lista-compacta')).toBeNull();
  });

  it('al desplegar, la fila del evento que se analizaba queda resaltada y a la vista', async () => {
    const usuario = userEvent.setup();
    const desplazar = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = desplazar;
    renderizar();

    await usuario.click((await screen.findByText('LTE:7213766')).closest('tr'));
    await usuario.click(await screen.findByRole('button', { name: 'Desplegar' }));

    const fila = (await screen.findByText('LTE:7213766')).closest('tr');
    expect(fila.className).toContain('vt-tabla__fila--seleccionada');
    expect(desplazar).toHaveBeenCalled();
  });

  it('volver a pulsar el mismo evento tras desplegar lo pliega otra vez', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await usuario.click((await screen.findByText('LTE:7213766')).closest('tr'));
    await usuario.click(await screen.findByRole('button', { name: 'Desplegar' }));
    await usuario.click((await screen.findByText('LTE:7213766')).closest('tr'));

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1');
    expect(useVisStore.getState().tablaColapsada).toBe(true);
    expect(document.querySelector('.vt-lista-compacta')).toBeInTheDocument();
  });

  it('pulsar otro evento con la tabla desplegada también la pliega', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await usuario.click((await screen.findByText('LTE:7213766')).closest('tr'));
    await usuario.click(await screen.findByRole('button', { name: 'Desplegar' }));
    await usuario.click((await screen.findByText('WCDMA:13163:30405')).closest('tr'));

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2');
    expect(useVisStore.getState().tablaColapsada).toBe(true);
  });

  it('se puede seleccionar con el teclado', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const fila = (await screen.findByText('LTE:7213766')).closest('tr');
    fila.focus();
    await usuario.keyboard('{Enter}');

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1');
  });
});

describe('ordenación', () => {
  it('invierte el orden al pulsar dos veces la misma columna', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const cabecera = await screen.findByText(/Δ RSRP/);

    const filas = () => [...document.querySelectorAll('.vt-tabla__fila')];

    await usuario.click(cabecera);
    expect(within(filas()[0]).getByText(/-6\.0 dB/)).toBeInTheDocument();

    await usuario.click(cabecera);
    expect(within(filas()[0]).getByText(/\+14\.0 dB/)).toBeInTheDocument();
  });

  it('los valores ausentes van al final ordene como ordene', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const cabecera = await screen.findByText(/Δ RSRQ/);
    await usuario.click(cabecera);

    const filas = [...document.querySelectorAll('.vt-tabla__fila')];
    // ev-2 tiene delta_rsrq_db null, así que debe quedar el último.
    expect(within(filas[1]).getByText('WCDMA:13163:30405')).toBeInTheDocument();
  });
});

describe('estado vacío', () => {
  it('sugiere ejecutar la detección cuando no hay eventos', async () => {
    respuesta = { total: 0, page: 1, page_size: 15, items: [] };
    renderizar();

    expect(await screen.findByText(/No hay handovers para estos filtros/)).toBeInTheDocument();
    expect(screen.getByText(/Detectar handovers/)).toBeInTheDocument();
  });
});


describe('plegado de la tabla', () => {
  it('sin evento elegido no se ofrece plegar: plegar solo tiene sentido para ver un detalle', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');
    expect(screen.queryByRole('button', { name: 'Plegar tabla' })).not.toBeInTheDocument();
    expect(document.querySelector('.vt-lista-compacta')).toBeNull();
  });

  it('la lista plegada conserva la navegación entre eventos', async () => {
    const usuario = userEvent.setup();
    useVisStore.getState().toggleTablaColapsada();
    renderizar();

    await screen.findByRole('button', { name: 'Desplegar' });
    const items = [...document.querySelectorAll('.vt-lista-compacta__item')];
    await usuario.click(items[0]);

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-1');
  });

  it('plegada solo muestra el número y la fecha/hora', async () => {
    useVisStore.getState().toggleTablaColapsada();
    renderizar();

    await screen.findByRole('button', { name: 'Desplegar' });
    const item = document.querySelector('.vt-lista-compacta__item');

    // Las claves de celda ocupan demasiado en una columna estrecha: quedan fuera.
    expect(item.textContent).not.toContain('LTE:7213766');
    expect(item.querySelector('.vt-lista-compacta__hora')).not.toBeNull();
  });
});
