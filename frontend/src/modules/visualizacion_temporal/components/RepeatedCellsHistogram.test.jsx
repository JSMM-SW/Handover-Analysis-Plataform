/**
 * Pruebas del histograma de radiobases repetidas (Fase 6, tarea 6.5) — HU-C2-008.
 *
 * El intervalo se elige con un deslizador: va de 1 minuto a lo que dura la sesión más larga
 * (`minutos_max`), y en el extremo derecho se analiza el recorrido completo.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RepeatedCellsHistogram from './RepeatedCellsHistogram.jsx';
import { useVisStore } from '../store/visStore.js';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="histograma" />,
}));

const CELDAS = [
  { celda_clave: 'LTE:7279051', psc_pci: 283, tech: 'LTE', n_visitas: 2, n_mediciones: 154, tiempo_total_s: 154 },
  { celda_clave: 'LTE:7213766', psc_pci: 461, tech: 'LTE', n_visitas: 1, n_mediciones: 90, tiempo_total_s: 89 },
];

const TOTAL = {
  intervalo: 'total',
  minutos: null,
  minutos_max: 21,
  top: 20,
  bins: [{ inicio: null, fin: null, sesion_id: null, celdas: CELDAS }],
  total_celdas: 8,
};

let respuesta = TOTAL;
let urlsPedidas = [];

beforeEach(() => {
  urlsPedidas = [];
  useVisStore.getState().reiniciar();
  useVisStore.getState().setSesion('s1');
  respuesta = TOTAL;

  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      urlsPedidas.push(String(url));
      return { ok: true, status: 200, json: async () => respuesta };
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RepeatedCellsHistogram />
    </QueryClientProvider>,
  );
}

describe('renderizado (CA1)', () => {
  it('dibuja el histograma con las celdas recibidas', async () => {
    renderizar();

    expect(await screen.findByTestId('histograma')).toBeInTheDocument();
  });

  it('muestra cuántos PCI/PSC hay en total', async () => {
    renderizar();

    expect(await screen.findByText('8 PCI/PSC en total')).toBeInTheDocument();
  });

  it('pide el histograma agrupado por PCI/PSC, como la secuencia de radiobases', async () => {
    renderizar();

    await waitFor(() => expect(urlsPedidas.some((u) => u.includes('eje=psc_pci'))).toBe(true));
  });
});

describe('deslizador de intervalo (CA2)', () => {
  it('arranca en el extremo derecho: el recorrido completo', async () => {
    renderizar();

    const deslizador = await screen.findByRole('slider', { name: 'Intervalo de análisis en minutos' });
    await waitFor(() => expect(deslizador).toHaveAttribute('max', '21'));
    expect(deslizador).toHaveValue('21');
    expect(screen.getByText('Todo el recorrido')).toBeInTheDocument();
    expect(urlsPedidas.every((u) => !u.includes('minutos='))).toBe(true);
  });

  it('arrastrar la bolita cambia los minutos y relanza la consulta', async () => {
    renderizar();

    const deslizador = await screen.findByRole('slider', { name: 'Intervalo de análisis en minutos' });
    await waitFor(() => expect(deslizador).toHaveAttribute('max', '21'));

    fireEvent.change(deslizador, { target: { value: '7' } });

    // El rótulo cambia al instante; la consulta sale en cuanto la bolita se detiene.
    expect(screen.getByText('7 minutos')).toBeInTheDocument();
    await waitFor(() => expect(urlsPedidas.some((u) => u.includes('minutos=7'))).toBe(true));
  });

  it('volver al extremo derecho vuelve al total', async () => {
    renderizar();

    const deslizador = await screen.findByRole('slider', { name: 'Intervalo de análisis en minutos' });
    await waitFor(() => expect(deslizador).toHaveAttribute('max', '21'));

    fireEvent.change(deslizador, { target: { value: '3' } });
    fireEvent.change(deslizador, { target: { value: '21' } });

    expect(screen.getByText('Todo el recorrido')).toBeInTheDocument();
  });

  it('con una sesión de un minuto no hay nada que deslizar', async () => {
    respuesta = { ...TOTAL, minutos_max: 1 };
    renderizar();

    const deslizador = await screen.findByRole('slider', { name: 'Intervalo de análisis en minutos' });
    await waitFor(() => expect(deslizador).toBeDisabled());
  });
});

describe('parámetro top', () => {
  it('se envía al backend', async () => {
    renderizar();

    await waitFor(() => expect(urlsPedidas.some((u) => u.includes('top=20'))).toBe(true));
  });

  it('cambiarlo relanza la consulta', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const entrada = await screen.findByLabelText('Número de celdas a mostrar');
    await usuario.tripleClick(entrada);
    await usuario.paste('5');

    await waitFor(() => expect(urlsPedidas.some((u) => u.includes('top=5'))).toBe(true));
  });
});

describe('varios intervalos', () => {
  it('permite navegar entre los bins cuando hay más de uno', async () => {
    respuesta = {
      ...TOTAL,
      minutos: 5,
      bins: [
        { inicio: '2026-07-01T13:00:00Z', fin: '2026-07-01T13:05:00Z', sesion_id: 's1', celdas: CELDAS },
        { inicio: '2026-07-01T13:05:00Z', fin: '2026-07-01T13:10:00Z', sesion_id: 's1', celdas: [CELDAS[0]] },
      ],
    };
    const usuario = userEvent.setup();
    renderizar();

    expect(await screen.findByText(/Intervalo 1 de 2/)).toBeInTheDocument();

    await usuario.click(screen.getByRole('button', { name: 'Intervalo siguiente' }));
    expect(await screen.findByText(/Intervalo 2 de 2/)).toBeInTheDocument();
  });

  it('con varias sesiones, cada intervalo dice de cuál es', async () => {
    respuesta = {
      ...TOTAL,
      minutos: 5,
      bins: [
        { inicio: '2026-07-01T13:00:00Z', fin: '2026-07-01T13:05:00Z', sesion_id: 'a', sesion_nombre: 'Session_12_x.csv', celdas: CELDAS },
        { inicio: '2026-09-28T21:24:53Z', fin: '2026-09-28T21:29:53Z', sesion_id: 'b', sesion_nombre: 'Session_134_y.csv', celdas: CELDAS },
      ],
    };
    renderizar();

    expect(await screen.findByText(/Intervalo 1 de 2 · Sesión 12/)).toBeInTheDocument();
  });

  it('con un solo intervalo no aparece la navegación', async () => {
    renderizar();

    await screen.findByTestId('histograma');
    expect(screen.queryByText(/Intervalo 1 de/)).not.toBeInTheDocument();
  });
});

describe('estado vacío', () => {
  it('avisa cuando no hay celdas para los filtros', async () => {
    respuesta = { ...TOTAL, minutos_max: 0, bins: [], total_celdas: 0 };
    renderizar();

    expect(await screen.findByText(/Sin radiobases/)).toBeInTheDocument();
  });
});
