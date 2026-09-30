/**
 * Pruebas del panel de detalle PRE/POST (Fase 6, tarea 6.5) — HU-C2-005.
 *
 * ECharts no puede pintar en jsdom, así que se comprueba todo lo que rodea a la gráfica: la
 * cabecera del evento, el control de ventana, el filtro de parámetro, el aviso de ventana
 * recortada y la tabla de estadísticas.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import HandoverDetailPanel from './HandoverDetailPanel.jsx';
import { useVisStore } from '../store/visStore.js';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="grafica-ventana" />,
}));

const EVENTO = {
  id_evento: 'ev-1',
  sesion_id: 's1',
  timestamp_evento: '2026-07-01T13:01:30Z',
  celda_origen: { clave: 'LTE:7213766', psc_pci: 461 },
  celda_destino: { clave: 'LTE:7390405', psc_pci: 460 },
  tipo_evento: 'intra_frecuencia',
  ping_pong: false,
  tipo_tecnologia: 'LTE',
  confianza: 'alta',
  delta_rsrp_db: 14,
  duracion_permanencia_s: 89,
};

const EVENTO_2 = { ...EVENTO, id_evento: 'ev-2', timestamp_evento: '2026-07-01T13:03:00Z' };

/** Ventana completa: ±5 s reales. */
const VENTANA = {
  evento: EVENTO,
  t_evento: EVENTO.timestamp_evento,
  segundos_antes: 5,
  segundos_despues: 5,
  t: [],
  t_relativo_s: [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5],
  fase: ['pre', 'pre', 'pre', 'pre', 'pre', 'evento', 'post', 'post', 'post', 'post', 'post'],
  series: {
    rsrp_dbm: [-100, -101, -102, -103, -104, -86, -85, -85, -84, -84, -83],
    rssnr_db: [null, null, null, null, null, null, null, null, null, null, null],
  },
  estadisticas: {
    rsrp_dbm: { media_pre: -102, media_post: -84.5, delta: 17.5, n_pre: 5, n_post: 6, disponible: true },
    rssnr_db: { media_pre: null, media_post: null, delta: null, n_pre: 0, n_post: 0, disponible: false },
  },
};

let ventana = VENTANA;

let urlsPedidas = [];

beforeEach(() => {
  urlsPedidas = [];
  useVisStore.getState().reiniciar();
  useVisStore.getState().setSesion('s1');
  ventana = VENTANA;

  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      const texto = String(url);
      urlsPedidas.push(texto);

      const cuerpo = texto.includes('/ventana')
        ? ventana
        : { total: 2, page: 1, page_size: 500, items: [EVENTO, EVENTO_2] };

      return { ok: true, status: 200, json: async () => cuerpo };
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
      <HandoverDetailPanel />
    </QueryClientProvider>,
  );
}

describe('sin selección', () => {
  it('invita a elegir un handover en la tabla', async () => {
    renderizar();

    expect(await screen.findByText(/Ningún handover seleccionado/)).toBeInTheDocument();
  });
});

describe('cabecera del evento (CA1)', () => {
  beforeEach(() => useVisStore.getState().seleccionarHandover('ev-1'));

  it('muestra celda origen, destino, hora y tecnología', async () => {
    renderizar();

    expect(await screen.findByText('LTE:7213766')).toBeInTheDocument();
    expect(screen.getByText('LTE:7390405')).toBeInTheDocument();
    expect(screen.getByText(/Intra-frecuencia/)).toBeInTheDocument();
  });

  it('numera el handover dentro del listado', async () => {
    renderizar();

    expect(await screen.findByText(/Handover 1 de 2/)).toBeInTheDocument();
  });

  it('permite navegar al siguiente sin cerrar el panel', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const siguiente = await screen.findByTitle('Handover siguiente');
    await usuario.click(siguiente);

    expect(useVisStore.getState().handoverSeleccionadoId).toBe('ev-2');
  });

  it('el botón anterior está deshabilitado en el primer evento', async () => {
    renderizar();

    expect(await screen.findByTitle('Handover anterior')).toBeDisabled();
  });
});

describe('ventana temporal configurable (CA2)', () => {
  beforeEach(() => useVisStore.getState().seleccionarHandover('ev-1'));

  it('arranca en 5 segundos, como pide la maqueta', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');
    expect(useVisStore.getState().ventanaSegundos).toBe(5);
  });

  it('cambiar el preset actualiza el store y vuelve a consultar', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await usuario.click(await screen.findByRole('button', { name: '±30s' }));

    expect(useVisStore.getState().ventanaSegundos).toBe(30);
    await waitFor(() => {
      expect(urlsPedidas.some((u) => u.includes('segundos_antes=30'))).toBe(true);
    });
  });

  it('admite un valor libre además de los presets', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const entrada = await screen.findByLabelText('Ventana temporal en segundos');
    await usuario.tripleClick(entrada);
    await usuario.paste('12');

    await waitFor(() => expect(useVisStore.getState().ventanaSegundos).toBe(12));
  });

  it('avisa cuando la ventana llega recortada por el borde del recorrido', async () => {
    // Solo hay 2 s de datos previos: el evento está cerca del inicio de la sesión.
    ventana = {
      ...VENTANA,
      t_relativo_s: [-2, -1, 0, 1, 2, 3, 4, 5],
      fase: ['pre', 'pre', 'evento', 'post', 'post', 'post', 'post', 'post'],
    };
    useVisStore.getState().seleccionarHandover('ev-1');
    renderizar();

    expect(await screen.findByText(/Ventana recortada/)).toBeInTheDocument();
    expect(screen.getByText(/2\.0 s de datos/)).toBeInTheDocument();
  });

  it('no avisa cuando la ventana está completa', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');
    expect(screen.queryByText(/Ventana recortada/)).not.toBeInTheDocument();
  });
});

describe('filtro de parámetro (CA3)', () => {
  beforeEach(() => useVisStore.getState().seleccionarHandover('ev-1'));

  it('arranca en «todos»', async () => {
    renderizar();

    const selector = await screen.findByLabelText('Parámetro a analizar');
    expect(selector.value).toBe('todos');
  });

  it('permite elegir un parámetro concreto', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const selector = await screen.findByLabelText('Parámetro a analizar');
    await usuario.selectOptions(selector, 'rsrq_db');

    expect(useVisStore.getState().parametroDetalle).toBe('rsrq_db');
    await waitFor(() => {
      expect(urlsPedidas.some((u) => u.includes('parametros=rsrq_db'))).toBe(true);
    });
  });
});

describe('estadísticas pre/post', () => {
  beforeEach(() => useVisStore.getState().seleccionarHandover('ev-1'));

  it('muestra medias y delta por parámetro', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');
    // La etiqueta aparece tambien en el <option> del selector: se acota a la tabla.
    const tabla = screen.getByRole('table');
    const fila = within(tabla).getByText(/RSRP \(dBm\)/).closest('tr');

    expect(fila).toHaveTextContent('-102');
    expect(fila).toHaveTextContent('-84.5');
    expect(fila).toHaveTextContent('+17.50');
    expect(fila).toHaveTextContent('5 pre · 6 post');
  });

  it('un parámetro sin medidas se marca como tal, sin inventar un cero', async () => {
    renderizar();

    await screen.findByText('LTE:7213766');
    const tabla = screen.getByRole('table');
    const fila = within(tabla).getByText(/SINR\/RSSNR/).closest('tr');

    expect(fila.className).toContain('vt-tabla__fila--atenuada');
    expect(fila).toHaveTextContent('sin datos');
  });
});
