/**
 * Leyenda de los marcadores de handover.
 *
 * Las líneas verticales de las gráficas temporales no tienen leyenda propia en ECharts (son
 * `markLine`, no series), así que sin esto el usuario tendría que adivinar qué significa cada
 * color. Los colores salen de `TEMA`, los mismos que usa `construirMarcadoresHO`.
 *
 * «Handover seleccionado» solo aparece cuando hay un evento elegido: anunciar un color que no
 * está en la gráfica confundiría más que ayudaría.
 */

import { useVisStore } from '../store/visStore.js';
import { TEMA } from '../utils/temaVisual.js';

export default function LeyendaMarcadoresHO() {
  const visibles = useVisStore((e) => e.capas.marcadoresHO);
  const haySeleccion = useVisStore((e) => Boolean(e.handoverSeleccionadoId));

  if (!visibles) return null;

  return (
    <div className="vt-leyenda-ho" aria-label="Leyenda de marcadores de handover">
      <span className="vt-leyenda-ho__item">
        <span
          className="vt-leyenda-ho__linea"
          style={{ background: TEMA.marcadorHO }}
          aria-hidden="true"
        />
        Handover
      </span>
      {haySeleccion && (
        <span className="vt-leyenda-ho__item">
          <span
            className="vt-leyenda-ho__linea vt-leyenda-ho__linea--seleccionado"
            style={{ background: TEMA.marcadorHOSeleccionado }}
            aria-hidden="true"
          />
          Handover seleccionado
        </span>
      )}
    </div>
  );
}
