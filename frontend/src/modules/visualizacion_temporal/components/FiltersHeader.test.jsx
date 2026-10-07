/**
 * Pruebas de la configuración del análisis (Fase 4, tarea 4.8) — HU-C2-006.
 *
 * Lo que se comprueba:
 * - el criterio 1 de la historia: **al aplicar un filtro, las consultas se relanzan solas** (se
 *   mockea `fetch` y se inspeccionan las URLs pedidas);
 * - que el selector de sesiones muestre solo el nombre;
 * - que **solo se pueda elegir lo que existe**: días con datos en el calendario, horas con datos
 *   en la franja horaria y tecnologías presentes en la base (`GET /disponibilidad`).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
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
    n_handovers: 29,
  },
];

/** Días con datos, ya en hora local, tal como los devuelve `GET /disponibilidad`. */
const DISPONIBILIDAD = {
  zona_horaria: 'America/Guayaquil',
  dias: [
    {
      fecha: '2026-07-01',
      n_mediciones: 600,
      n_handovers: 8,
      franjas: [{ inicio: '08:00:00', fin: '08:09:00' }],
    },
    {
      fecha: '2026-07-03',
      n_mediciones: 100,
      n_handovers: 0,
      franjas: [{ inicio: '17:30:00', fin: '17:35:00' }],
    },
    {
      fecha: '2026-09-28',
      n_mediciones: 1217,
      n_handovers: 39,
      franjas: [{ inicio: '16:24:00', fin: '16:45:00' }],
    },
  ],
  tecnologias: ['GSM', 'LTE', 'NR'],
};

/** URLs que ha pedido el componente durante la prueba. */
let urlsPedidas = [];

/** Si es cierto, la detección de handovers responde con error. */
let deteccionFalla = false;

function respuestaPara(url) {
  if (url.includes('detectar-handovers')) {
    return { sesion_id: 'x', total_handovers: 8, duracion_ms: 120, por_tipo: {} };
  }
  if (url.includes('/disponibilidad')) return DISPONIBILIDAD;
  if (url.includes('/sesiones')) return SESIONES;
  return {};
}

beforeEach(() => {
  urlsPedidas = [];
  deteccionFalla = false;
  useVisStore.getState().reiniciar();

  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      urlsPedidas.push(String(url));
      if (deteccionFalla && String(url).includes('detectar-handovers')) {
        return {
          ok: false,
          status: 422,
          json: async () => ({ detail: 'La sesión no tiene mediciones con celda identificable.' }),
        };
      }
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

/** Elige la primera sesión, cierra el selector y espera a que lleguen los días con datos. */
async function prepararConSesion(usuario) {
  renderizar();
  await elegirSesion(usuario, 'Session_S1');
  await usuario.keyboard('{Escape}');
  await waitFor(() => expect(screen.getByLabelText('Fecha de inicio')).toBeEnabled());
}

/** Abre el calendario del campo indicado. */
async function abrirCalendario(usuario, campo) {
  await usuario.click(screen.getByLabelText(campo));
  return screen.findByRole('dialog', { name: `Elegir ${campo.toLowerCase()}` });
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

    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
  });

  it('cada opción muestra solo el nombre de la sesión', async () => {
    const usuario = userEvent.setup();
    renderizar();

    const boton = await screen.findByRole('button', { name: 'Sesión a analizar' });
    await waitFor(() => expect(boton).toBeEnabled());
    await usuario.click(boton);

    const opcion = screen.getByRole('checkbox', { name: /Session_S1_20260701_080000/ });
    expect(opcion.closest('label')).toHaveTextContent(/^Session_S1_20260701_080000$/);
    expect(screen.queryByText(/mediciones/)).not.toBeInTheDocument();
  });
});

describe('selección de sesiones', () => {
  it('guarda la sesión en el store y la resume en el botón con su nombre', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');

    expect(useVisStore.getState().sesionIds).toEqual(['sesion-1']);
    expect(screen.getByRole('button', { name: 'Sesión a analizar' })).toHaveTextContent(
      /^Session_S1_20260701_080000$/,
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

describe('calendario: solo los días con datos', () => {
  it('pide la disponibilidad de las sesiones elegidas en la zona del navegador', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    const pedida = urlsPedidas.find((u) => u.includes('/disponibilidad'));
    expect(pedida).toContain('sesion_id=sesion-1');
    expect(pedida).toContain('zona_horaria=');
  });

  it('un campo de fecha vacío se muestra como marcador de posición', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    expect(screen.getByLabelText('Fecha de inicio')).toHaveClass('vt-input--vacio');
  });

  it('pulsar en el campo abre el calendario en el primer mes con datos', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    const calendario = await abrirCalendario(usuario, 'Fecha de inicio');

    expect(within(calendario).getByText(/julio de 2026/)).toBeInTheDocument();
  });

  it('los días sin datos no se pueden elegir', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    const calendario = await abrirCalendario(usuario, 'Fecha de inicio');

    expect(within(calendario).getByRole('button', { name: /^1 de julio de 2026/ })).toBeEnabled();
    expect(within(calendario).getByRole('button', { name: /^2 de julio de 2026/ })).toBeDisabled();
  });

  it('los días con handovers llevan un punto', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    const calendario = await abrirCalendario(usuario, 'Fecha de inicio');
    const conHandovers = within(calendario).getByRole('button', { name: /^1 de julio de 2026/ });
    const sinHandovers = within(calendario).getByRole('button', { name: /^3 de julio de 2026/ });

    expect(conHandovers.querySelector('.vt-calendario__punto')).not.toBeNull();
    expect(sinHandovers.querySelector('.vt-calendario__punto')).toBeNull();
    expect(conHandovers).toHaveAccessibleName(/8 handovers/);
  });

  it('las flechas saltan al mes siguiente con datos, sin pasar por los vacíos', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    const calendario = await abrirCalendario(usuario, 'Fecha de inicio');
    await usuario.click(within(calendario).getByRole('button', { name: 'Mes siguiente con datos' }));

    expect(within(calendario).getByText(/septiembre de 2026/)).toBeInTheDocument();
    expect(within(calendario).getByRole('button', { name: 'Mes siguiente con datos' })).toBeDisabled();
  });

  it('las fechas abarcan días completos: desde las 00:00 hasta las 23:59:59', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    let calendario = await abrirCalendario(usuario, 'Fecha de inicio');
    await usuario.click(within(calendario).getByRole('button', { name: /^1 de julio de 2026/ }));
    calendario = await abrirCalendario(usuario, 'Fecha de fin');
    await usuario.click(within(calendario).getByRole('button', { name: /^3 de julio de 2026/ }));

    const { desde, hasta } = useVisStore.getState();
    expect(new Date(desde).getHours()).toBe(0);
    expect(new Date(desde).getMinutes()).toBe(0);
    expect(new Date(hasta).getDate()).toBe(3);
    expect(new Date(hasta).getHours()).toBe(23);
    expect(new Date(hasta).getMinutes()).toBe(59);
    expect(screen.getByLabelText('Fecha de inicio')).toHaveTextContent('01/07/2026');
  });

  it('«hasta» no deja elegir días anteriores a «desde»', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    let calendario = await abrirCalendario(usuario, 'Fecha de inicio');
    await usuario.click(within(calendario).getByRole('button', { name: /^3 de julio de 2026/ }));
    calendario = await abrirCalendario(usuario, 'Fecha de fin');

    expect(within(calendario).getByRole('button', { name: /^1 de julio de 2026/ })).toBeDisabled();
  });
});

describe('franja horaria: solo las horas con datos', () => {
  const opciones = (nombre) =>
    [...screen.getByLabelText(nombre).querySelectorAll('option')]
      .map((o) => o.value)
      .filter(Boolean);

  it('ya no hay campos de hora junto a las fechas; la hora va en la franja horaria', async () => {
    renderizar();

    await screen.findByLabelText('Fecha de inicio');
    expect(screen.queryByLabelText('Hora de inicio')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Franja horaria: desde')).toBeInTheDocument();
  });

  it('solo ofrece horas en las que hay mediciones', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    const desde = opciones('Franja horaria: desde');
    expect(desde).toContain('08:00');
    expect(desde).toContain('16:24');
    expect(desde).not.toContain('12:00');
    // «Hasta» llega al final del último minuto con datos.
    expect(opciones('Franja horaria: hasta')).toContain('16:46');
  });

  it('con días elegidos, solo ofrece las horas de esos días', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    let calendario = await abrirCalendario(usuario, 'Fecha de inicio');
    await usuario.click(within(calendario).getByRole('button', { name: /^3 de julio de 2026/ }));
    calendario = await abrirCalendario(usuario, 'Fecha de fin');
    await usuario.click(within(calendario).getByRole('button', { name: /^3 de julio de 2026/ }));

    expect(opciones('Franja horaria: desde')).toEqual([
      '17:30', '17:31', '17:32', '17:33', '17:34', '17:35',
    ]);
  });

  it('elegir las horas las guarda en el store', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    await usuario.selectOptions(screen.getByLabelText('Franja horaria: desde'), '16:30');
    await usuario.selectOptions(screen.getByLabelText('Franja horaria: hasta'), '16:40');

    expect(useVisStore.getState().horaInicio).toBe('16:30');
    expect(useVisStore.getState().horaFin).toBe('16:40');
    // «Hasta» ya no ofrece horas anteriores a «desde».
    expect(opciones('Franja horaria: hasta')).not.toContain('16:25');
  });

  it('cambiar de día suelta una franja que en el día nuevo no tiene datos', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    await usuario.selectOptions(screen.getByLabelText('Franja horaria: desde'), '08:00');
    const calendario = await abrirCalendario(usuario, 'Fecha de inicio');
    await usuario.click(within(calendario).getByRole('button', { name: 'Mes siguiente con datos' }));
    await usuario.click(within(calendario).getByRole('button', { name: /^28 de septiembre/ }));

    expect(useVisStore.getState().horaInicio).toBeNull();
  });
});

describe('tecnologías: las que hay en la base', () => {
  it('ofrece las tecnologías de los datos, no una lista fija', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    expect(await screen.findByLabelText('NR')).toBeInTheDocument();
    expect(screen.queryByLabelText('WCDMA')).not.toBeInTheDocument();
  });

  it('acumula tecnologías a la vez', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    await usuario.click(await screen.findByLabelText('LTE'));
    await usuario.click(screen.getByLabelText('GSM'));

    const estado = useVisStore.getState();
    expect(estado.sesionIds).toEqual(['sesion-1']);
    expect(estado.tecnologias).toEqual(['LTE', 'GSM']);
  });
});

describe('chips y limpieza', () => {
  it('muestra un chip por filtro activo y permite quitarlo', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);
    await usuario.click(await screen.findByLabelText('LTE'));

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
    await prepararConSesion(usuario);
    await usuario.click(await screen.findByLabelText('LTE'));

    await usuario.click(screen.getByRole('button', { name: 'Limpiar filtros' }));

    expect(useVisStore.getState().tecnologias).toEqual([]);
    expect(useVisStore.getState().sesionIds).toEqual(['sesion-1']);
    expect(screen.queryByTitle('Quitar este filtro')).not.toBeInTheDocument();
  });
});

describe('textos retirados de la tarjeta', () => {
  it('no muestra la zona horaria ni la línea de contexto de la sesión', async () => {
    const usuario = userEvent.setup();
    await prepararConSesion(usuario);

    expect(screen.queryByText(/horas en/)).not.toBeInTheDocument();
    expect(screen.queryByText(/radiobases ·/)).not.toBeInTheDocument();
    expect(screen.queryByText(/acota el periodo/)).not.toBeInTheDocument();
  });
});

describe('detección automática de handovers', () => {
  const detecciones = (sesion) =>
    urlsPedidas.filter((u) => u.includes(`/sesiones/${sesion}/detectar-handovers`)).length;

  it('ya no hay botón para detectar', async () => {
    renderizar();

    await screen.findByRole('button', { name: 'Sesión a analizar' });
    expect(screen.queryByRole('button', { name: /Detectar handovers/ })).not.toBeInTheDocument();
  });

  it('elegir sesiones lanza la detección de cada una, sin pulsar nada', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await elegirSesion(usuario, 'Datos 1');

    await waitFor(() => {
      expect(detecciones('sesion-1')).toBe(1);
      expect(detecciones('sesion-2')).toBe(1);
    });
    // El aviso suma todas las sesiones elegidas (8 + 29), igual que la tarjeta «Handovers», y no
    // solo la última que se detectó.
    await waitFor(() =>
      expect(screen.getByText(/Handovers detectados/)).toHaveTextContent(
        'Handovers detectados: 37 en 2 sesiones',
      ),
    );
  });

  it('volver a elegir una sesión ya detectada no repite la detección', async () => {
    const usuario = userEvent.setup();
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await waitFor(() => expect(detecciones('sesion-1')).toBe(1));

    await elegirSesion(usuario, 'Session_S1'); // la quita
    await elegirSesion(usuario, 'Session_S1'); // y la vuelve a poner

    expect(useVisStore.getState().sesionIds).toEqual(['sesion-1']);
    expect(detecciones('sesion-1')).toBe(1);
  });

  it('si la detección falla, avisa y permite reintentarla', async () => {
    const usuario = userEvent.setup();
    deteccionFalla = true;
    renderizar();

    await elegirSesion(usuario, 'Session_S1');
    await usuario.keyboard('{Escape}');

    const aviso = await screen.findByRole('alert');
    expect(aviso).toHaveTextContent(/No se pudieron detectar los handovers/);
    expect(aviso).toHaveTextContent(/celda identificable/);

    deteccionFalla = false;
    await usuario.click(within(aviso).getByRole('button', { name: 'Reintentar' }));

    await waitFor(() => expect(detecciones('sesion-1')).toBe(2));
    expect(await screen.findByText(/Handovers detectados/)).toBeInTheDocument();
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
