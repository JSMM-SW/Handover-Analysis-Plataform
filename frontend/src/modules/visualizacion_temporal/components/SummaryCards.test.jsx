/**
 * Pruebas de las tarjetas de resumen (Fase 6, tarea 6.5) — HU-C2-007.
 *
 * Los tres indicadores obligatorios de la historia son total de handovers, radiobases involucradas
 * y sesiones analizadas: si alguno desaparece, la historia deja de cumplirse.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import SummaryCards from './SummaryCards.jsx';
import { desgloseTecnologia, formatearDuracion } from '../utils/formatoResumen.js';
import { useVisStore } from '../store/visStore.js';

const RESUMEN = {
  total_handovers: 8,
  radiobases_involucradas: 8,
  sesiones_analizadas: 1,
  n_mediciones: 600,
  duracion_s: 629,
  por_tipo: { intra_frecuencia: 4, inter_frecuencia: 2, inter_rat: 2 },
  por_tecnologia: { LTE: 6, 'LTE->WCDMA': 1, 'WCDMA->LTE': 1 },
  total_ping_pong: 1,
  total_confianza_baja: 1,
  tasa_ho_por_minuto: 0.763,
  cobertura_parametros: [],
};

let respuesta = RESUMEN;
let respuestaOk = true;

beforeEach(() => {
  useVisStore.getState().reiniciar();
  useVisStore.getState().setSesion('s1');
  respuesta = RESUMEN;
  respuestaOk = true;

  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: respuestaOk,
      status: respuestaOk ? 200 : 500,
      json: async () => (respuestaOk ? respuesta : { detail: 'Error interno del módulo.' }),
    })),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SummaryCards />
    </QueryClientProvider>,
  );
}

describe('los tres indicadores obligatorios de HU-C2-007', () => {
  it('muestra el total de handovers (CA1)', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('Handovers')).closest('article');
    await waitFor(() => expect(within(tarjeta).getByText('8')).toBeInTheDocument());
  });

  it('muestra las radiobases involucradas (CA2)', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('Celdas observadas')).closest('article');
    await waitFor(() => expect(within(tarjeta).getByText('8')).toBeInTheDocument());
    expect(tarjeta).toHaveTextContent('celdas distintas');
  });

  it('muestra las sesiones analizadas (CA3)', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('Sesiones')).closest('article');
    await waitFor(() => expect(within(tarjeta).getByText('1')).toBeInTheDocument());
  });

  it('los tres van destacados sobre los complementos', async () => {
    renderizar();

    await screen.findByText('Handovers');
    const principales = document.querySelectorAll('.vt-tarjeta--principal');

    expect(principales).toHaveLength(3);
  });
});

describe('complementos', () => {
  it('muestra las mediciones con la duración del periodo', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('Mediciones')).closest('article');
    await waitFor(() => expect(tarjeta).toHaveTextContent('600'));
    expect(tarjeta).toHaveTextContent('10 min');
  });

  it('la tarjeta HO / minuto muestra solo la tasa', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('HO / minuto')).closest('article');
    await waitFor(() => expect(tarjeta).toHaveTextContent('0.76'));
    expect(tarjeta).not.toHaveTextContent('LTE');
    expect(tarjeta.querySelector('.vt-tarjeta__detalle')).toBeNull();
  });

  it('el reparto por tecnología no se ve hasta pulsar «Por tecnología»', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('Handovers')).closest('article');
    const boton = await within(tarjeta).findByRole('button', { name: 'Por tecnología' });

    expect(boton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(tarjeta).not.toHaveTextContent('LTE');
  });
  it('la tarjeta de handovers solo muestra los handovers: el ping-pong no se tiene en cuenta', async () => {
    renderizar();

    const tarjeta = (await screen.findByText('Handovers')).closest('article');
    await waitFor(() => expect(within(tarjeta).getByText('8')).toBeInTheDocument());
    expect(tarjeta).toHaveTextContent('detectados');
    expect(document.body).not.toHaveTextContent(/ping-pong/i);
  });

  it('las tarjetas no llevan micro-gráficas: solo la cifra', async () => {
    renderizar();

    await screen.findByText('Handovers');
    expect(document.querySelector('.vt-tarjeta svg:not(.vt-icono)')).toBeNull();
  });

  it('los tres obligatorios siguen presentes aunque falten complementos', async () => {
    respuesta = { total_handovers: 3, radiobases_involucradas: 2, sesiones_analizadas: 1 };
    renderizar();

    for (const titulo of ['Handovers', 'Celdas observadas', 'Sesiones']) {
      expect(await screen.findByText(titulo)).toBeInTheDocument();
    }
  });
});

describe('casos límite', () => {
  it('una sesión sin handovers no rompe las tarjetas', async () => {
    respuesta = {
      ...RESUMEN,
      total_handovers: 0,
      total_ping_pong: 0,
      tasa_ho_por_minuto: null,
      por_tecnologia: {},
    };
    renderizar();

    const tarjeta = (await screen.findByText('Handovers')).closest('article');
    await waitFor(() => expect(within(tarjeta).getByText('0')).toBeInTheDocument());
    expect(within(tarjeta).queryByRole('button', { name: 'Por tecnología' })).not.toBeInTheDocument();

    const tasa = screen.getByText('HO / minuto').closest('article');
    expect(tasa).toHaveTextContent('—');
  });

  it('avisa si la consulta falla', async () => {
    respuestaOk = false;
    renderizar();

    const aviso = await screen.findByRole('alert', {}, { timeout: 5000 });
    expect(aviso).toHaveTextContent(/No se pudieron cargar los datos/);
  });
});

describe('popover «Por tecnología» de la tarjeta Handovers', () => {
  async function abrir(usuario) {
    renderizar();
    const boton = await screen.findByRole('button', { name: 'Por tecnología' });
    await usuario.click(boton);
    return { boton, popover: screen.getByRole('dialog', { name: 'Handovers por tecnología' }) };
  }

  it('muestra de qué tecnología a qué tecnología y cuántos, sin porcentajes', async () => {
    const { boton, popover } = await abrir(userEvent.setup());

    expect(boton).toHaveAttribute('aria-expanded', 'true');
    expect(within(popover).getAllByRole('listitem').map((f) => f.textContent)).toEqual([
      'LTE→ a LTE6',
      'LTE→ a WCDMA1',
      'WCDMA→ a LTE1',
    ]);
    expect(popover).not.toHaveTextContent('%');
  });

  it('se cierra con su botón «×» y el foco vuelve a «Por tecnología»', async () => {
    const usuario = userEvent.setup();
    const { boton, popover } = await abrir(usuario);

    await usuario.click(within(popover).getByRole('button', { name: 'Cerrar' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(boton).toHaveFocus();
  });

  it('se cierra con Escape', async () => {
    const usuario = userEvent.setup();
    await abrir(usuario);

    await usuario.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('se cierra al hacer clic fuera', async () => {
    const usuario = userEvent.setup();
    await abrir(usuario);

    await usuario.click(screen.getByText('Sesiones'));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('desglose por tecnología', () => {
  it('escribe cada transición de origen a destino, de más a menos', () => {
    expect(desgloseTecnologia({ 'LTE->WCDMA': 2, LTE: 37, WCDMA: 3, 'WCDMA->LTE': 2 })).toEqual([
      { clave: 'LTE', origen: 'LTE', destino: 'LTE', total: 37 },
      { clave: 'WCDMA', origen: 'WCDMA', destino: 'WCDMA', total: 3 },
      { clave: 'LTE->WCDMA', origen: 'LTE', destino: 'WCDMA', total: 2 },
      { clave: 'WCDMA->LTE', origen: 'WCDMA', destino: 'LTE', total: 2 },
    ]);
  });

  it('un evento sin tecnología sale como «Sin dato», sin destino', () => {
    expect(desgloseTecnologia({ LTE: 4, desconocida: 1 }).at(-1)).toEqual({
      clave: 'desconocida',
      origen: 'Sin dato',
      destino: null,
      total: 1,
    });
  });

  it('sin datos queda vacío', () => {
    expect(desgloseTecnologia()).toEqual([]);
    expect(desgloseTecnologia({ LTE: 0 })).toEqual([]);
  });

  it('la duración nunca muestra 60 minutos', () => {
    expect(formatearDuracion(86370)).toBe('24 h');
    expect(formatearDuracion(3 * 3600 + 5 * 60)).toBe('3 h 5 min');
    expect(formatearDuracion(629)).toBe('10 min');
    expect(formatearDuracion(20)).toBe('20 s');
  });
});

describe('tonos de las tarjetas', () => {
  it('cada tarjeta tiene un tono de color distinto', async () => {
    renderizar();

    await screen.findByText('Handovers');
    const tonos = [...document.querySelectorAll('.vt-tarjeta')].map((t) =>
      [...t.classList].find((c) => /^vt-tarjeta--(?!principal)/.test(c)),
    );

    expect(tonos).toHaveLength(5);
    expect(new Set(tonos).size).toBe(5);
  });
});
