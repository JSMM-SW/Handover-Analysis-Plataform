/**
 * Pruebas del selector de la sesión que muestran las gráficas temporales.
 *
 * Con varias sesiones de fechas lejanas, un eje de tiempo común las deja como dos rayas en los
 * extremos. Se protege que el selector aparezca solo cuando hace falta, que enfoque y que avise
 * cuando «Todas» no se va a poder leer.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import EnfoqueSesion from './EnfoqueSesion.jsx';
import { sesionesAlejadas } from '../hooks/useEnfoqueSesion.js';
import { useVisStore } from '../store/visStore.js';

const SESIONES = [
  {
    sesion_id: 'a',
    sesion_nombre: 'Sesión 12 · Session_12_20260506.csv',
    inicio: '2026-05-06T23:49:15Z',
    fin: '2026-05-07T00:03:32Z',
  },
  {
    sesion_id: 'b',
    sesion_nombre: 'Sesión 134 · Session_134_20260928.csv',
    inicio: '2026-09-28T21:24:53Z',
    fin: '2026-09-28T21:45:43Z',
  },
];

beforeEach(() => {
  useVisStore.getState().reiniciar();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => SESIONES })),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderizar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <EnfoqueSesion />
    </QueryClientProvider>,
  );
}

describe('EnfoqueSesion', () => {
  it('con una sola sesión no aparece', () => {
    useVisStore.getState().setSesion('a');
    const { container } = renderizar();

    expect(container).toBeEmptyDOMElement();
  });

  it('con varias, ofrece «Todas» y cada sesión por su nombre, con la primera enfocada', async () => {
    useVisStore.getState().setSesiones(['a', 'b']);
    renderizar();

    expect(await screen.findByRole('button', { name: 'Sesión 134' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Todas' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Sesión 12' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('pulsar una sesión la enfoca en las gráficas', async () => {
    const usuario = userEvent.setup();
    useVisStore.getState().setSesiones(['a', 'b']);
    renderizar();

    await usuario.click(await screen.findByRole('button', { name: 'Sesión 134' }));

    expect(useVisStore.getState().sesionEnfocada).toBe('b');
  });

  it('con «Todas» y sesiones de fechas lejanas avisa de por qué se ven en los extremos', async () => {
    const usuario = userEvent.setup();
    useVisStore.getState().setSesiones(['a', 'b']);
    renderizar();

    await usuario.click(await screen.findByRole('button', { name: 'Todas' }));

    expect(await screen.findByRole('status')).toHaveTextContent(/Elige una para verla a escala/);
  });
});

describe('sesionesAlejadas', () => {
  it('detecta un hueco de más de una hora entre sesiones', () => {
    expect(sesionesAlejadas(SESIONES)).toBe(true);
  });

  it('dos sesiones seguidas no están alejadas', () => {
    const seguidas = [
      { inicio: '2026-07-01T13:00:00Z', fin: '2026-07-01T13:10:00Z' },
      { inicio: '2026-07-01T13:20:00Z', fin: '2026-07-01T13:30:00Z' },
    ];
    expect(sesionesAlejadas(seguidas)).toBe(false);
  });
});
