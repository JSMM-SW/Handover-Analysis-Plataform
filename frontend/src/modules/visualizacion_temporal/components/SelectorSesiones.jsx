/**
 * Selector de sesiones con selección múltiple — HU-C2-006.
 *
 * Un `<select multiple>` nativo obliga a usar Ctrl+clic, algo que casi nadie descubre solo. Aquí
 * se abre una lista con casillas: un clic añade o quita una sesión, y el botón resume lo elegido.
 *
 * Cada opción muestra **solo el nombre de la sesión**. La fecha, las mediciones y los handovers
 * de cada una se ven después en el resumen y en el calendario de los filtros.
 */

import { IconoCerrar } from './Iconos.jsx';
import { sessionName } from '../../../shared/sessionNames';
import { useDesplegable } from '../hooks/useInterfaz.js';

/**
 * @param {Object} props
 * @param {import('../types/index.js').Sesion[]} props.sesiones
 * @param {string[]} props.seleccionadas
 * @param {(id: string) => void} props.onAlternar
 * @param {() => void} props.onLimpiar
 * @param {boolean} [props.cargando]
 * @param {boolean} [props.deshabilitado]
 */
export default function SelectorSesiones({
  sesiones,
  seleccionadas,
  onAlternar,
  onLimpiar,
  cargando = false,
  deshabilitado = false,
}) {
  const { abierto, alternar, referencia } = useDesplegable();

  const elegidas = sesiones.filter((s) => seleccionadas.includes(s.sesion_id));

  const resumen = cargando
    ? 'Cargando sesiones…'
    : elegidas.length === 0
      ? 'Selecciona una o varias sesiones…'
      : elegidas.length === 1
        ? sessionName(elegidas[0])
        : `${elegidas.length} sesiones seleccionadas`;

  return (
    <div className="vt-multiselect" ref={referencia}>
      <button
        type="button"
        className={`vt-select vt-multiselect__boton${elegidas.length ? '' : ' vt-multiselect__boton--vacio'}`}
        onClick={alternar}
        disabled={cargando || deshabilitado}
        aria-label="Sesión a analizar"
        aria-haspopup="true"
        aria-expanded={abierto}
        aria-controls="vt-lista-sesiones"
      >
        <span className="vt-multiselect__resumen">{resumen}</span>
      </button>

      {abierto && (
        <div className="vt-multiselect__panel" id="vt-lista-sesiones">
          <div className="vt-multiselect__cabecera">
            <span>
              {elegidas.length
                ? `${elegidas.length} de ${sesiones.length} seleccionadas`
                : `${sesiones.length} sesiones disponibles`}
            </span>
            {elegidas.length > 0 && (
              <button
                type="button"
                className="vt-boton vt-boton--texto vt-boton--pequeno"
                onClick={onLimpiar}
              >
                <IconoCerrar tamano={12} />
                Quitar todas
              </button>
            )}
          </div>

          <ul className="vt-multiselect__lista" role="group" aria-label="Sesiones disponibles">
            {sesiones.map((sesion) => {
              const marcada = seleccionadas.includes(sesion.sesion_id);
              return (
                <li key={sesion.sesion_id}>
                  <label
                    className={`vt-multiselect__opcion${marcada ? ' vt-multiselect__opcion--marcada' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={marcada}
                      onChange={() => onAlternar(sesion.sesion_id)}
                    />
                    <span className="vt-multiselect__nombre">{sessionName(sesion)}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
