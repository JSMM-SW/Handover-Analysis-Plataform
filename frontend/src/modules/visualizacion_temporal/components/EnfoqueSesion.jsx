/**
 * Selector de la sesión que muestran las gráficas temporales.
 *
 * Solo aparece con varias sesiones elegidas. Por defecto las gráficas enfocan la primera: con
 * sesiones de fechas distintas, verlas todas en un mismo eje de tiempo las deja como dos rayas en
 * los extremos. «Todas» sigue disponible para comparar sesiones cercanas en el tiempo.
 */

import AyudaContextual from './AyudaContextual.jsx';
import { useEnfoqueSesion } from '../hooks/useEnfoqueSesion.js';

export default function EnfoqueSesion() {
  const { opciones, enfocada, enfocar, avisarAlejadas } = useEnfoqueSesion();

  if (opciones.length < 2) return null;

  return (
    <div className="vt-enfoque">
      <span id="vt-enfoque-titulo" className="vt-enfoque__titulo">
        Sesión en las gráficas
        <AyudaContextual
          titulo="Sesión en las gráficas"
          texto="La línea de tiempo, la secuencia de radiobases y las radiobases repetidas muestran solo la sesión elegida, a su escala. El resumen y la tabla de eventos siguen incluyendo todas."
        />
      </span>

      <div
        className="vt-segmentado vt-enfoque__opciones"
        role="group"
        aria-labelledby="vt-enfoque-titulo"
      >
        <button
          type="button"
          className={`vt-segmento${enfocada === null ? ' vt-segmento--activo' : ''}`}
          onClick={() => enfocar(null)}
          aria-pressed={enfocada === null}
        >
          Todas
        </button>
        {opciones.map((opcion) => (
          <button
            key={opcion.id}
            type="button"
            className={`vt-segmento${enfocada === opcion.id ? ' vt-segmento--activo' : ''}`}
            onClick={() => enfocar(opcion.id)}
            aria-pressed={enfocada === opcion.id}
            title={opcion.detalle || undefined}
          >
            {opcion.nombre}
          </button>
        ))}
      </div>

      {avisarAlejadas && (
        <p className="vt-enfoque__aviso" role="status">
          Las sesiones son de momentos muy distintos y en un mismo eje quedan en los extremos.
          Elige una para verla a escala.
        </p>
      )}
    </div>
  );
}
