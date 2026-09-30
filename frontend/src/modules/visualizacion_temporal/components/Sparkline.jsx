/**
 * Micro-visualización de tendencia para las tarjetas de resumen.
 *
 * Solo pinta: la geometría la calculan `construirTrazoSparkline` y `construirBarrasSparkline`
 * (`hooks/useTendenciasResumen.js`). Se dibuja en SVG y no con ECharts porque son cinco gráficos
 * diminutos sin interacción y una instancia de ECharts por tarjeta sería un derroche.
 */

import { useMemo } from 'react';

import {
  construirBarrasSparkline,
  construirTrazoSparkline,
} from '../hooks/useTendenciasResumen.js';

const ANCHO = 100;
const ALTO = 28;

/**
 * @param {Object} props
 * @param {number[]|null} props.valores
 * @param {'linea'|'barras'} [props.variante]
 * @param {string} props.descripcion  lo que representa, para lectores de pantalla
 */
export default function Sparkline({ valores, variante = 'linea', descripcion }) {
  const geometria = useMemo(
    () =>
      variante === 'barras'
        ? construirBarrasSparkline(valores, { ancho: ANCHO, alto: ALTO })
        : construirTrazoSparkline(valores, { ancho: ANCHO, alto: ALTO }),
    [valores, variante],
  );

  // Sin datos suficientes se reserva el hueco igualmente: así las tarjetas no cambian de alto
  // cuando llegan los datos.
  if (!geometria) return <span className="vt-sparkline vt-sparkline--vacio" aria-hidden="true" />;

  return (
    <svg
      className={`vt-sparkline vt-sparkline--${variante}`}
      viewBox={`0 0 ${ANCHO} ${ALTO}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={descripcion}
    >
      {variante === 'barras' ? (
        geometria.map((barra, i) => (
          <rect
            key={i}
            className="vt-sparkline__barra"
            x={barra.x}
            y={barra.y}
            width={barra.ancho}
            height={barra.alto}
            rx="0.8"
          />
        ))
      ) : (
        <>
          <path className="vt-sparkline__area" d={geometria.area} />
          <path className="vt-sparkline__linea" d={geometria.linea} vectorEffect="non-scaling-stroke" />
        </>
      )}
    </svg>
  );
}
