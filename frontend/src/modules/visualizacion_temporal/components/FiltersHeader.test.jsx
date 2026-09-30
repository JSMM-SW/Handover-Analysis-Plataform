/**
 * Pruebas de la configuración del análisis (Fase 4, tarea 4.8) — HU-C2-006.
 *
 * Lo que se comprueba es el criterio 1 de la historia: **al aplicar un filtro, las consultas se
 * relanzan solas**. Se mockea `fetch` y se inspeccionan las URLs pedidas. Además se cubre la
 * selección de varias sesiones y el filtro de fechas de día completo.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import FiltersHeader from './FiltersHeader.jsx';
import { useVisStore } from '../store/visStore.js';

const SESIONES = [
  {
    sesion_id: 'sesion-1',
    sesion_nombre: 'Session_S1_20260701_080000',
    inicio: '2026-07-01T13:00:00Z',
    fin: '2026-07-01T13:10:00Z',
    n_mediciones: 600,
    n_celdas: 8,
    tecnologias: ['LTE', 'WCDMA'],
    origen: 'sintetico',
    n_handovers: 8,
  },
  {
    sesion_id: 'sesion-2',
    sesion_nombre: 'Datos 1',
    inicio: '2026-05-06T23:49:15Z',
    fin: '2026-05-07T00:03:32Z',
    n_mediciones: 405,
    n_celdas: 25,
    tecnologias: ['LTE'],
    origen: 'real',
    n_handovers: 29,
  },
];

/** URLs que ha pedido el componente durante la prueba. */
let urlsPedidas = [];

function respuestaPara(url) {
  if (url.includes('detectar-handovers')) {
    return { sesion_id: 'x', total_handovers: 8, duracion_ms: 120, por_tipo: {} };
  }
  if (url.includes('/sesiones')) return SESIONES;
  return {};
}

beforeEach(() => {
  urlsPedidas = [];
  useVisStore.getState().reiniciar();

  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      urlsPedidas.push(String(url));
      return {
        ok: true,
        status: 200,
        json: async () => respuestaPara(String(url)),
      };
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <FiltersHeader />
    </QueryClientProvider>,
  );
}

/** Abre el selector y marca la sesión cuyo nombre coincide. */
async function elegirSesion(usuario, nombre) {
  const boton = await screen.findByRole('button', { name: 'Sesión a analizar' });
  await waitFor(() => expect(boton).toBeEnabled());
  if (boton.getAttribute('aria-expanded') !== 'true') await usuario.click(boton);
  await usuario.click(await screen.findByRole('checkbox', { name: new RegExp(nombre) }));
}

describe('carga de sesiones', () => {
  it('pide las sesiones al montarse y las ofrece en el selector', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await waitFor(() => {
      expect(urlsPedidas.some((u) => u.includes('/visualizacion-temporal/sesiones'))).toBe(true);
    });

    const boton = await screen.findByRole('button', { name: 'Sesión a analizar' });
    await waitFor(() => expect(boton).toBeEnabled());
    await usuario.click(boton);

    expect(screen.getAllByRole('checkbox', { name: /mediciones/ })).toHaveLength(2);
  });

  it('muestra fecha y mediciones junto al nombre, porque los nombres se repiten', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const boton = await screen.findByRole('button', { name: 'Sesión a analizar' });
    await waitFor(() => expect(boton).toBeEnabled());
    await usuario.click(boton);

    const opcion = screen.getByRole('checkbox', { name: /Session_S1_20260701_080000/ });
    expect(opcion.closest('label')).toHaveTextContent(/600 mediciones/);
  });
});

describe('selección de sesiones', () => {
  it('guarda la sesión en el store y la resume en el botón', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');

    expect(useVisStore.getState().sesionIds).toEqual(['sesion-1']);
    expect(screen.getByRole('button', { name: 'Sesión a analizar' })).toHaveTextContent(
      /Session_S1_20260701_080000/,
    );
  });

  it('permite elegir varias sesiones a la vez', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await elegirSesion(usuario, 'Datos 1');

    expect(useVisStore.getState().sesionIds).toEqual(['sesion-1', 'sesion-2']);
    expect(screen.getByRole('button', { name: 'Sesión a analizar' })).toHaveTextContent(
      '2 sesiones seleccionadas',
    );
  });

  it('las consultas piden todas las sesiones elegidas', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await elegirSesion(usuario, 'Datos 1');

    await waitFor(() => {
      expect(
        urlsPedidas.some(
          (u) => u.includes('/resumen') && u.includes('sesion_id=sesion-1') && u.includes('sesion_id=sesion-2'),
        ),
      ).toBe(true);
    });
  });

  it('se cierra con Escape', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');

    expect(screen.queryByRole('checkbox', { name: /Session_S1/ })).not.toBeInTheDocument();
  });
});

describe('filtros combinados (HU-C2-006 CA2)', () => {
  it('acumula tecnologías a la vez', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');

    await usuario.click(screen.getByLabelText('LTE'));
    await usuario.click(screen.getByLabelText('GSM'));

    const estado = useVisStore.getState();
    expect(estado.sesionIds).toEqual(['sesion-1']);
    expect(estado.tecnologias).toEqual(['LTE', 'GSM']);
  });

  it('las fechas abarcan días completos: desde las 00:00 hasta las 23:59:59', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');

    fireEvent.change(screen.getByLabelText('Fecha de inicio'), { target: { value: '2026-07-01' } });
    fireEvent.change(screen.getByLabelText('Fecha de fin'), { target: { value: '2026-07-02' } });

    const { desde, hasta } = useVisStore.getState();
    expect(new Date(desde).getHours()).toBe(0);
    expect(new Date(desde).getMinutes()).toBe(0);
    expect(new Date(hasta).getHours()).toBe(23);
    expect(new Date(hasta).getMinutes()).toBe(59);
  });

  it('ya no hay campos de hora junto a las fechas; la hora va en la franja horaria', async () => {
    renderizar();

    await screen.findByLabelText('Fecha de inicio');
    expect(screen.queryByLabelText('Hora de inicio')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Hora de fin')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Franja horaria: desde')).toBeInTheDocument();
  });

  it('un campo de fecha vacío se muestra como marcador de posición', async () => {
    renderizar();

    expect(await screen.findByLabelText('Fecha de inicio')).toHaveClass('vt-input--vacio');
  });

  it('pulsar en el campo de fecha abre el calendario', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');

    const campo = screen.getByLabelText('Fecha de inicio');
    campo.showPicker = vi.fn();
    await usuario.click(campo);

    expect(campo.showPicker).toHaveBeenCalled();
  });

  it('muestra un chip por filtro activo y permite quitarlo', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');
    await usuario.click(screen.getByLabelText('LTE'));

    const chip = await screen.findByTitle('Quitar este filtro');
    expect(chip.textContent).toContain('LTE');

    await usuario.click(chip);

    expect(useVisStore.getState().tecnologias).toEqual([]);
  });

  it('el botón de limpiar está deshabilitado si no hay filtros', async () => {
    renderizar();

    const boton = await screen.findByRole('button', { name: 'Limpiar filtros' });
    expect(boton).toBeDisabled();
  });

  it('limpiar filtros vacía los chips pero conserva las sesiones', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');
    await usuario.click(screen.getByLabelText('LTE'));

    await usuario.click(screen.getByRole('button', { name: 'Limpiar filtros' }));

    expect(useVisStore.getState().tecnologias).toEqual([]);
    expect(useVisStore.getState().sesionIds).toEqual(['sesion-1']);
    expect(screen.queryByTitle('Quitar este filtro')).not.toBeInTheDocument();
  });
});

describe('textos retirados de la tarjeta', () => {
  it('no muestra la zona horaria ni la línea de contexto de la sesión', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');

    expect(screen.queryByText(/horas en/)).not.toBeInTheDocument();
    expect(screen.queryByText(/radiobases ·/)).not.toBeInTheDocument();
    expect(screen.queryByText(/acota el periodo/)).not.toBeInTheDocument();
  });
});

describe('detección de handovers', () => {
  it('está deshabilitada mientras no haya sesión', async () => {
    renderizar();

    const boton = await screen.findByRole('button', { name: 'Detectar handovers' });
    expect(boton).toBeDisabled();
  });

  it('lanza la detección de cada sesión elegida y suma el resultado', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await elegirSesion(usuario, 'Datos 1');
    await usuario.keyboard('{Escape}');

    await usuario.click(screen.getByRole('button', { name: 'Detectar handovers' }));

    await waitFor(() => {
      expect(urlsPedidas.some((u) => u.includes('/sesiones/sesion-1/detectar-handovers'))).toBe(true);
      expect(urlsPedidas.some((u) => u.includes('/sesiones/sesion-2/detectar-handovers'))).toBe(true);
    });

    const aviso = await screen.findByText(/Detección completada/);
    expect(aviso).toHaveTextContent('16');
    expect(aviso).toHaveTextContent('en 2 sesiones');
  });
});

describe('errores', () => {
  it('avisa si no se pueden cargar las sesiones', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Error interno del módulo.' }),
      })),
    );

    renderizar();

    // `useSesiones` reintenta una vez antes de darse por vencido, asi que el aviso tarda mas
    // que el segundo por defecto de findBy.
    const aviso = await screen.findByRole('alert', {}, { timeout: 5000 });
    expect(aviso).toHaveTextContent(/No se pudieron cargar las sesiones/);
  });
});
