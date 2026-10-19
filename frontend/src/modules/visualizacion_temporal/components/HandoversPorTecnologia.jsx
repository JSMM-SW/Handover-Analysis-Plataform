/**
 * Botón «Por tecnología» de la tarjeta «Handovers» y su popover — HU-C2-007.
 *
 * El popover dice, para cada transición, **de qué tecnología a qué tecnología** pasó el teléfono y
 * cuántas veces: «LTE → LTE 579», «LTE → GSM 1». Va escondido tras un botón para que la tarjeta
 * siga mostrando solo la cifra, como las demás (decisión D-7).
 *
 * Se cierra con su botón «×», con `Escape` o al hacer clic fuera (`useDesplegable`).
 */

import { useId } from 'react';

import { IconoCerrar } from './Iconos.jsx';
import { useDesplegable } from '../hooks/useInterfaz.js';

/**
 * @param {Object} props
 * @param {{clave: string, origen: string, destino: string|null, total: number}[]} props.filas
 *   salida de `desgloseTecnologia`
 */
export default function HandoversPorTecnologia({ filas }) {
  const { abierto, alternar, cerrar, referencia, disparador } = useDesplegable();
  const idPanel = useId();

  if (!filas.length) return null;

  return (
    <div className="vt-popover" ref={referencia}>
      <button
        ref={disparador}
        type="button"
        className="vt-boton vt-boton--texto vt-boton--pequeno vt-popover__disparador"
        onClick={alternar}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        aria-controls={abierto ? idPanel : undefined}
      >
        Por tecnología
      </button>

      {abierto && (
        <div
          className="vt-popover__panel"
          id={idPanel}
          role="dialog"
          aria-label="Handovers por tecnología"
        >
          <div className="vt-popover__cabecera">
            <span className="vt-popover__titulo">Handovers por tecnología</span>
            <button
              type="button"
              className="vt-popover__cerrar"
              onClick={cerrar}
              aria-label="Cerrar"
            >
              <IconoCerrar tamano={14} />
            </button>
          </div>
          <span className="vt-popover__subtitulo">De la tecnología de origen a la de destino</span>

          <ul className="vt-popover__lista">
            {filas.map((fila) => (
              <li className="vt-popover__fila" key={fila.clave}>
                <span className="vt-popover__transicion">
                  {fila.origen}
                  {fila.destino && (
                    <>
                      <span className="vt-popover__flecha" aria-hidden="true">→</span>
                      <span className="vt-visualmente-oculto"> a </span>
                      {fila.destino}
                    </>
                  )}
                </span>
                <span className="vt-popover__total">{fila.total.toLocaleString('es-EC')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
