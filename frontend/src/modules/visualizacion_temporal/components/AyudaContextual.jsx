/**
 * Ayuda contextual «?» junto a un dato o un control.
 *
 * Muestra la definición breve de un término del glosario en lenguaje llano. El texto sale de
 * `types/glosario.js`, que es la única fuente de estas explicaciones.
 */

import { useAyudaContextual } from '../hooks/useInterfaz.js';
import { GLOSARIO } from '../types/glosario.js';

/**
 * @param {Object} props
 * @param {string} [props.termino]  clave de `GLOSARIO`
 * @param {string} [props.titulo]   alternativa a `termino` para una ayuda de interfaz que no es
 *   un concepto del glosario (p. ej. cómo funciona un filtro)
 * @param {string} [props.texto]
 * @param {'centro'|'izquierda'|'derecha'} [props.alineacion]  hacia dónde se abre la burbuja;
 *   junto a un borde de la tarjeta conviene abrirla hacia dentro para que no se corte.
 */
export default function AyudaContextual({ termino, titulo, texto, alineacion = 'centro' }) {
  const { abierta, idTooltip, disparador } = useAyudaContextual();
  const entrada = termino ? GLOSARIO[termino] : titulo && { titulo, breve: texto };

  if (!entrada) return null;

  return (
    <span className="vt-ayuda-ctx">
      <button
        type="button"
        className="vt-ayuda-ctx__boton"
        aria-label={`Qué significa: ${entrada.titulo}`}
        aria-describedby={abierta ? idTooltip : undefined}
        aria-expanded={abierta}
        {...disparador}
      >
        ?
      </button>
      {abierta && (
        <span
          role="tooltip"
          id={idTooltip}
          className={`vt-ayuda-ctx__burbuja vt-ayuda-ctx__burbuja--${alineacion}`}
        >
          <span className="vt-ayuda-ctx__titulo">{entrada.titulo}</span>
          <span className="vt-ayuda-ctx__texto">{entrada.breve}</span>
        </span>
      )}
    </span>
  );
}
