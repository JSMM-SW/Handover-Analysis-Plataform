/**
 * Campo numérico controlado que tolera estados intermedios.
 *
 * Un `<input type="number">` atado directamente a un valor externo es incómodo: al borrar el
 * contenido para teclear otro número, el valor vacío se convierte en el mínimo y el campo «salta»
 * mientras se escribe. Aquí se mantiene un estado local para lo que se está tecleando y solo se
 * propaga hacia arriba cuando el valor es válido.
 */

import { useEffect, useState } from 'react';

export default function CampoNumero({ valor, onCambio, min = 1, max = 1000, ...resto }) {
  const [texto, setTexto] = useState(String(valor));

  // Si el valor cambia desde fuera (p. ej. al pulsar un preset), el campo lo refleja.
  useEffect(() => setTexto(String(valor)), [valor]);

  const alEscribir = (evento) => {
    const nuevo = evento.target.value;
    setTexto(nuevo);

    const numero = Number(nuevo);
    if (nuevo !== '' && Number.isFinite(numero) && numero >= min && numero <= max) {
      onCambio(numero);
    }
  };

  // Al salir del campo se normaliza: si quedó vacío o fuera de rango, vuelve al valor vigente.
  const alSalir = () => {
    const numero = Number(texto);
    if (texto === '' || !Number.isFinite(numero) || numero < min || numero > max) {
      setTexto(String(valor));
    }
  };

  return (
    <input
      {...resto}
      className="vt-input vt-input--numero"
      type="number"
      min={min}
      max={max}
      value={texto}
      onChange={alEscribir}
      onBlur={alSalir}
    />
  );
}
