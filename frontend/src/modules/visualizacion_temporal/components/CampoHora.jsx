/**
 * Campo de hora con marcador de ejemplo.
 *
 * Un `<input type="time">` vacío muestra `--:--`, que no le dice al usuario qué escribir, y el
 * atributo `placeholder` no funciona en ese tipo de campo. Por eso, **mientras está vacío y sin
 * foco**, el campo es de texto con una hora de ejemplo como marcador. Al pulsarlo pasa a ser un
 * campo de hora normal y se abre el reloj del navegador.
 */

import { useCampoHora } from '../hooks/useInterfaz.js';

/**
 * @param {Object} props
 * @param {string|null} props.valor           'HH:MM' o null
 * @param {(valor: string|null) => void} props.onCambio
 * @param {string} props.ejemplo              hora que se muestra como marcador, p. ej. '08:00'
 * @param {string} props.etiqueta             nombre accesible del campo
 */
export default function CampoHora({ valor, onCambio, ejemplo, etiqueta }) {
  const { tipo, referencia, alEnfocar, alSalir } = useCampoHora(valor);

  return (
    <input
      ref={referencia}
      className={`vt-input vt-input--hora${valor ? '' : ' vt-input--vacio'}`}
      type={tipo}
      value={valor ?? ''}
      placeholder={`ej. ${ejemplo}`}
      onFocus={alEnfocar}
      onBlur={alSalir}
      onChange={(e) => onCambio(e.target.value || null)}
      aria-label={etiqueta}
    />
  );
}
