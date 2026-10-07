/**
 * Pruebas del toque educativo: ayudas contextuales «?» y panel de glosario.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import AyudaContextual from './AyudaContextual.jsx';
import GlosarioPanel from './GlosarioPanel.jsx';
import { useVisStore } from '../store/visStore.js';
import { GLOSARIO, GRUPOS_GLOSARIO, entradasDeGrupo } from '../types/glosario.js';
import { PARAMETROS_RF } from '../types/index.js';

beforeEach(() => useVisStore.getState().reiniciar());

describe('contenido del glosario', () => {
  it('no explica lo que la interfaz ya no muestra (ping-pong y RSCP)', () => {
    expect(GLOSARIO.ping_pong).toBeUndefined();
    expect(GLOSARIO.rscp_dbm).toBeUndefined();
  });

  it('explica todos los parámetros de radiofrecuencia del módulo', () => {
    // Si se añade un parámetro y no se explica, el docente se encuentra una sigla sin ayuda.
    PARAMETROS_RF.forEach((parametro) => {
      expect(GLOSARIO[parametro]?.breve).toBeTruthy();
    });
  });

  it('cada entrada pertenece a un grupo que el panel muestra', () => {
    const grupos = new Set(GRUPOS_GLOSARIO.map((g) => g.id));
    Object.values(GLOSARIO).forEach((entrada) => expect(grupos.has(entrada.grupo)).toBe(true));
  });

  it('ningún grupo queda vacío', () => {
    GRUPOS_GLOSARIO.forEach((g) => expect(entradasDeGrupo(g.id).length).toBeGreaterThan(0));
  });
});

describe('AyudaContextual', () => {
  it('la definición no está en el DOM hasta que se pide', () => {
    render(<AyudaContextual termino="rsrp_dbm" />);

    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('muestra la definición al pasar el ratón y la oculta al salir', async () => {
    const usuario = userEvent.setup();
    render(<AyudaContextual termino="rsrp_dbm" />);

    const boton = screen.getByRole('button', { name: /RSRP/ });
    await usuario.hover(boton);

    const burbuja = screen.getByRole('tooltip');
    expect(burbuja).toHaveTextContent(GLOSARIO.rsrp_dbm.breve);
    expect(boton).toHaveAttribute('aria-describedby', burbuja.id);

    await usuario.unhover(boton);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('se abre con el teclado y se cierra con Escape', async () => {
    const usuario = userEvent.setup();
    render(<AyudaContextual termino="tipo_evento" />);

    await usuario.tab();
    expect(screen.getByRole('tooltip')).toBeInTheDocument();

    await usuario.keyboard('{Escape}');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });

  it('admite un texto propio para ayudas que no son del glosario', async () => {
    const usuario = userEvent.setup();
    render(<AyudaContextual titulo="Franja horaria" texto="Se aplica a cada día." />);

    await usuario.hover(screen.getByRole('button'));
    expect(screen.getByRole('tooltip')).toHaveTextContent('Se aplica a cada día.');
  });

  it('un término desconocido no pinta nada', () => {
    const { container } = render(<AyudaContextual termino="no_existe" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('GlosarioPanel', () => {
  it('cerrado no monta el contenido', () => {
    render(<GlosarioPanel />);
    expect(screen.queryByText(GLOSARIO.handover.titulo)).not.toBeInTheDocument();
  });

  it('abierto muestra los grupos y sus definiciones', () => {
    useVisStore.getState().setGlosario(true);
    render(<GlosarioPanel />);

    const dialogo = screen.getByRole('dialog', { name: 'Glosario' });
    GRUPOS_GLOSARIO.forEach((g) => {
      expect(within(dialogo).getByRole('heading', { name: g.titulo })).toBeInTheDocument();
    });
    expect(within(dialogo).getByText(GLOSARIO.rsrq_db.titulo)).toBeInTheDocument();
  });

  it('se cierra con el botón y con Escape', async () => {
    const usuario = userEvent.setup();
    useVisStore.getState().setGlosario(true);
    const { rerender } = render(<GlosarioPanel />);

    await usuario.click(screen.getByRole('button', { name: 'Cerrar el glosario' }));
    expect(useVisStore.getState().glosarioAbierto).toBe(false);

    useVisStore.getState().setGlosario(true);
    rerender(<GlosarioPanel />);
    await usuario.keyboard('{Escape}');
    expect(useVisStore.getState().glosarioAbierto).toBe(false);
  });
});
