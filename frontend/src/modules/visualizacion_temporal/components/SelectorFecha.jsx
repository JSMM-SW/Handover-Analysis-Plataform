/**
 * Campo de fecha con un calendario que **solo deja elegir los días con datos** — HU-C2-006.
 *
 * El `<input type="date">` nativo no permite deshabilitar días sueltos (solo un mínimo y un
 * máximo), así que el usuario acababa probando fecha por fecha hasta dar con una que tuviera
 * handovers. Aquí los días sin mediciones aparecen apagados y no se pueden pulsar, los que tienen
 * handovers llevan un punto, y las flechas saltan directamente al mes anterior o siguiente con
 * datos.
 *
 * Solo pinta: qué mes se ve y qué días se pueden elegir lo decide `useCalendario`.
 */

import { IconoCalendario, IconoFlechaDerecha, IconoFlechaIzquierda } from './Iconos.jsx';
import { useCalendario } from '../hooks/useCalendario.js';
import { DIAS_SEMANA } from '../utils/disponibilidad.js';
import { textoDia } from '../utils/fechas.js';

/**
 * @param {Object} props
 * @param {string} props.etiqueta  nombre accesible del campo, p. ej. «Fecha de inicio»
 * @param {string} props.valor     día elegido 'AAAA-MM-DD' o ''
 * @param {import('../types/index.js').DiaDisponible[]} props.dias  días con datos
 * @param {string} [props.min]     primer día elegible
 * @param {string} [props.max]     último día elegible
 * @param {(fecha: string) => void} props.onCambio
 * @param {boolean} [props.cargando]
 */
export default function SelectorFecha({
  etiqueta,
  valor,
  dias,
  min = '',
  max = '',
  onCambio,
  cargando = false,
}) {
  // Se desestructura: el resultado lleva la referencia del contenedor, y leer otras propiedades
  // del mismo objeto durante el render contaría como leer la referencia.
  const {
    abierto,
    referencia,
    cerrar,
    alternar,
    titulo,
    semanas,
    sinDias,
    irAnterior,
    irSiguiente,
  } = useCalendario({ dias, valor, min, max });

  const elegir = (fecha) => {
    onCambio(fecha);
    cerrar();
  };

  return (
    <div className="vt-fecha" ref={referencia}>
      <button
        type="button"
        className={`vt-input vt-fecha__boton${valor ? '' : ' vt-input--vacio'}`}
        onClick={alternar}
        aria-label={etiqueta}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        disabled={cargando}
      >
        <span>{cargando ? 'Cargando…' : valor ? textoDia(valor) : 'dd/mm/aaaa'}</span>
        <IconoCalendario tamano={16} />
      </button>

      {abierto && (
        <div className="vt-calendario" role="dialog" aria-label={`Elegir ${etiqueta.toLowerCase()}`}>
          {sinDias ? (
            <p className="vt-calendario__vacio">No hay días con datos en este rango.</p>
          ) : (
            <>
              <div className="vt-calendario__cabecera">
                <button
                  type="button"
                  className="vt-boton vt-boton--icono vt-boton--fantasma"
                  onClick={irAnterior ?? undefined}
                  disabled={!irAnterior}
                  aria-label="Mes anterior con datos"
                >
                  <IconoFlechaIzquierda tamano={16} />
                </button>
                <span className="vt-calendario__mes" aria-live="polite">
                  {titulo}
                </span>
                <button
                  type="button"
                  className="vt-boton vt-boton--icono vt-boton--fantasma"
                  onClick={irSiguiente ?? undefined}
                  disabled={!irSiguiente}
                  aria-label="Mes siguiente con datos"
                >
                  <IconoFlechaDerecha tamano={16} />
                </button>
              </div>

              <table className="vt-calendario__rejilla">
                <thead>
                  <tr>
                    {DIAS_SEMANA.map((dia) => (
                      <th key={dia} scope="col">
                        {dia}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {semanas.map((semana, indice) => (
                    <tr key={indice}>
                      {semana.map((celda, columna) => (
                        <td key={celda?.fecha ?? `hueco-${columna}`}>
                          {celda && (
                            <button
                              type="button"
                              className={[
                                'vt-calendario__dia',
                                celda.disponible && 'vt-calendario__dia--disponible',
                                celda.seleccionada && 'vt-calendario__dia--elegido',
                              ]
                                .filter(Boolean)
                                .join(' ')}
                              onClick={() => elegir(celda.fecha)}
                              disabled={!celda.disponible}
                              aria-pressed={celda.seleccionada}
                              aria-label={celda.descripcion}
                              title={celda.descripcion}
                            >
                              {celda.dia}
                              {celda.conHandovers && (
                                <span className="vt-calendario__punto" aria-hidden="true" />
                              )}
                            </button>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>

              <p className="vt-calendario__pie">
                <span className="vt-calendario__punto" aria-hidden="true" /> con handovers · solo se
                pueden elegir los días con datos
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
