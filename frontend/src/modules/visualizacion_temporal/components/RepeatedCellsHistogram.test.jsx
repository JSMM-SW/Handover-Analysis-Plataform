/**
 * Pruebas del histograma de radiobases repetidas (Fase 6, tarea 6.5) — HU-C2-008.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
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

let respuesta = { intervalo: 'total', top: 20, bins: [{ inicio: null, fin: null, celdas: CELDAS }], total_celdas: 8 };
let urlsPedidas = [];

beforeEach(() => {
  urlsPedidas = [];
  useVisStore.getState().reiniciar();
  useVisStore.getState().setSesion('s1');
  respuesta = { intervalo: 'total', top: 20, bins: [{ inicio: null, fin: null, celdas: CELDAS }], total_celdas: 8 };

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

  it('muestra cuántas celdas hay en total', async () => {
    renderizar();

    expect(await screen.findByText('8 celdas en total')).toBeInTheDocument();
  });
});

describe('intervalos de análisis (CA2)', () => {
  it('ofrece los cuatro intervalos', async () => {
    renderizar();

    await screen.findByRole('button', { name: 'Total' });
    for (const etiqueta of ['Total', 'Por hora', '10 min', '5 min']) {
      expect(screen.getByRole('button', { name: etiqueta })).toBeInTheDocument();
    }
  });

  it('cambiar el intervalo relanza la consulta con el nuevo parámetro', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await usuario.click(await screen.findByRole('button', { name: '5 min' }));

    await waitFor(() => {
      expect(urlsPedidas.some((u) => u.includes('intervalo=5min'))).toBe(true);
    });
  });

  it('el intervalo activo queda marcado', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const porHora = await screen.findByRole('button', { name: 'Por hora' });
    await usuario.click(porHora);

    await waitFor(() => expect(porHora.className).toContain('vt-segmento--activo'));
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
      intervalo: '5min',
      top: 20,
      bins: [
        { inicio: '2026-07-01T13:00:00Z', fin: '2026-07-01T13:05:00Z', celdas: CELDAS },
        { inicio: '2026-07-01T13:05:00Z', fin: '2026-07-01T13:10:00Z', celdas: [CELDAS[0]] },
      ],
      total_celdas: 8,
    };
    const usuario = userEvent.setup();
    renderizar();

    expect(await screen.findByText(/Intervalo 1 de 2/)).toBeInTheDocument();

    await usuario.click(screen.getByRole('button', { name: 'Intervalo siguiente' }));
    expect(await screen.findByText(/Intervalo 2 de 2/)).toBeInTheDocument();
  });

  it('con un solo intervalo no aparece la navegación', async () => {
    renderizar();

    await screen.findByTestId('histograma');
    expect(screen.queryByText(/Intervalo 1 de/)).not.toBeInTheDocument();
  });
});

describe('estado vacío', () => {
  it('avisa cuando no hay celdas para los filtros', async () => {
    respuesta = { intervalo: 'total', top: 20, bins: [], total_celdas: 0 };
    renderizar();

    expect(await screen.findByText(/Sin radiobases/)).toBeInTheDocument();
  });
});
