/**
 * Pruebas de la leyenda de marcadores de handover.
 */

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import LeyendaMarcadoresHO from './LeyendaMarcadoresHO.jsx';
import { useVisStore } from '../store/visStore.js';

beforeEach(() => useVisStore.getState().reiniciar());

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
