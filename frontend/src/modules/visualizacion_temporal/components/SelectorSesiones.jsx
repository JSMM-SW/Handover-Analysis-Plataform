/**
 * Selector de sesiones con selección múltiple — HU-C2-006.
 *
 * Un `<select multiple>` nativo obliga a usar Ctrl+clic, algo que casi nadie descubre solo. Aquí
 * se abre una lista con casillas: un clic añade o quita una sesión, y el botón resume lo elegido.
 *
 * Muchas sesiones comparten nombre (el mismo archivo cargado varias veces), así que cada opción
 * muestra además el inicio del identificador para poder distinguirlas.
 */

import { IconoCerrar } from './Iconos.jsx';
import { useDesplegable } from '../hooks/useInterfaz.js';

/** Fecha legible del inicio de la sesión. */
function fechaSesion(sesion) {
  return sesion.inicio
    ? new Date(sesion.inicio).toLocaleDateString('es-EC', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      })
    : 'sin fecha';
}

/** Nombre legible de una sesión: los nombres se repiten, así que se acompaña de la fecha. */
function etiquetaSesion(sesion) {
  const nombre = sesion.sesion_nombre || sesion.sesion_id.slice(0, 8);
  return `${nombre} · ${fechaSesion(sesion)} · ${sesion.n_mediciones.toLocaleString('es-EC')} mediciones`;
}

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
        ? etiquetaSesion(elegidas[0])
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
                    <span className="vt-multiselect__texto">
                      <span className="vt-multiselect__nombre">
                        {sesion.sesion_nombre || sesion.sesion_id.slice(0, 8)}
                      </span>
                      <span className="vt-multiselect__meta">
                        {fechaSesion(sesion)} · {sesion.n_mediciones.toLocaleString('es-EC')}{' '}
                        mediciones · {sesion.n_handovers} HO · id {sesion.sesion_id.slice(0, 8)}
                      </span>
                    </span>
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
