/**
 * Pruebas del campo de hora con marcador de ejemplo y de la leyenda de marcadores de handover.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CampoHora from './CampoHora.jsx';
import LeyendaMarcadoresHO from './LeyendaMarcadoresHO.jsx';
import { useVisStore } from '../store/visStore.js';

beforeEach(() => useVisStore.getState().reiniciar());

describe('CampoHora', () => {
  it('vacío muestra una hora de ejemplo en vez de las rayas --:--', () => {
    render(<CampoHora valor={null} onCambio={() => {}} ejemplo="08:00" etiqueta="Desde" />);

    const campo = screen.getByLabelText('Desde');
    expect(campo).toHaveAttribute('type', 'text');
    expect(campo).toHaveAttribute('placeholder', 'ej. 08:00');
  });

  it('al enfocarlo pasa a campo de hora nativo', () => {
    render(<CampoHora valor={null} onCambio={() => {}} ejemplo="08:00" etiqueta="Desde" />);

    const campo = screen.getByLabelText('Desde');
    fireEvent.focus(campo);

    expect(campo).toHaveAttribute('type', 'time');
  });

  it('si pierde el foco sin valor vuelve a mostrar el ejemplo', () => {
    render(<CampoHora valor={null} onCambio={() => {}} ejemplo="08:00" etiqueta="Desde" />);

    const campo = screen.getByLabelText('Desde');
    fireEvent.focus(campo);
    fireEvent.blur(campo);

    expect(campo).toHaveAttribute('type', 'text');
  });

  it('con valor se muestra como campo de hora y propaga los cambios', () => {
    const onCambio = vi.fn();
    render(<CampoHora valor="09:30" onCambio={onCambio} ejemplo="08:00" etiqueta="Desde" />);

    const campo = screen.getByLabelText('Desde');
    expect(campo).toHaveAttribute('type', 'time');

    fireEvent.change(campo, { target: { value: '10:15' } });
    expect(onCambio).toHaveBeenCalledWith('10:15');
  });

  it('borrar el valor envía null, no una cadena vacía', () => {
    const onCambio = vi.fn();
    render(<CampoHora valor="09:30" onCambio={onCambio} ejemplo="08:00" etiqueta="Desde" />);

    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '' } });
    expect(onCambio).toHaveBeenCalledWith(null);
  });
});

describe('LeyendaMarcadoresHO', () => {
  it('explica el color de los marcadores de handover', () => {
    render(<LeyendaMarcadoresHO />);

    expect(screen.getByText('Handover')).toBeInTheDocument();
  });

  it('solo anuncia el color del seleccionado cuando hay uno', () => {
    const { rerender } = render(<LeyendaMarcadoresHO />);
    expect(screen.queryByText('Handover seleccionado')).not.toBeInTheDocument();

    useVisStore.getState().seleccionarHandover('ev-1');
    rerender(<LeyendaMarcadoresHO />);
    expect(screen.getByText('Handover seleccionado')).toBeInTheDocument();
  });

  it('desaparece si se apagan los marcadores', () => {
    useVisStore.getState().toggleCapa('marcadoresHO');
    const { container } = render(<LeyendaMarcadoresHO />);

    expect(container).toBeEmptyDOMElement();
  });
});
