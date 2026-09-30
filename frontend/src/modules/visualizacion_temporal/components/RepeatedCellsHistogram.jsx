/**
 * Histograma de radiobases repetidas — HU-C2-008.
 *
 * Una «visita» es un tramo de permanencia: si el terminal vuelve a la misma celda más tarde,
 * cuenta otra vez. Es lo que revela los patrones de movilidad y las zonas de solapamiento donde
 * proliferan los handovers problemáticos.
 *
 * Se dibuja con **barras horizontales** para que los identificadores de celda se lean sin rotar;
 * los que no caben se truncan y el nombre completo aparece al pasar el ratón por el rótulo.
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';

import AyudaContextual from './AyudaContextual.jsx';
import CampoNumero from './CampoNumero.jsx';
import { Cargando, ErrorConsulta, SinResultados } from './EstadoConsulta.jsx';
import { IconoFlechaDerecha, IconoFlechaIzquierda } from './Iconos.jsx';
import { useCeldasRepetidas } from '../hooks/useDatosVT.js';
import {
  altoHistograma,
  formatearHora,
  indiceDeRotulo,
  useOpcionCeldasRepetidas,
} from '../hooks/useSeriesEcharts.js';
import { useVisStore } from '../store/visStore.js';

const ALTO_ESTADO = 220;

/** Intervalos de análisis del CA2 de la historia. */
const INTERVALOS = [
  { valor: 'total', etiqueta: 'Total' },
  { valor: 'hora', etiqueta: 'Por hora' },
  { valor: '10min', etiqueta: '10 min' },
  { valor: '5min', etiqueta: '5 min' },
];

export default function RepeatedCellsHistogram() {
  const [intervalo, setIntervalo] = useState('total');
  const [top, setTop] = useState(20);
  const [indiceBin, setIndiceBin] = useState(0);

  const eje = useVisStore((e) => e.ejeCeldas);
  const referencia = useRef(null);

  const { data, isLoading, isError, error, refetch, isFetching, isPlaceholderData } =
    useCeldasRepetidas({ intervalo, top });

  const bins = useMemo(() => data?.bins ?? [], [data]);
  const binActual = bins[Math.min(indiceBin, Math.max(bins.length - 1, 0))] ?? null;
  const celdas = useMemo(() => binActual?.celdas ?? [], [binActual]);

  const opcion = useOpcionCeldasRepetidas({ celdas, eje });

  /** Al pasar por un rótulo truncado se abre el tooltip de su barra, con el nombre completo. */
  const alPasarRaton = useCallback(
    (evento) => {
      const indice = indiceDeRotulo(evento, celdas, eje);
      if (indice < 0) return;
      referencia.current
        ?.getEchartsInstance?.()
        ?.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: indice });
    },
    [celdas, eje],
  );

  const cambiarIntervalo = (nuevo) => {
    setIntervalo(nuevo);
    setIndiceBin(0); // los bins del intervalo anterior ya no aplican
  };

  return (
    <div className="vt-grafica">
      <div className="vt-barra-herramientas">
        <span className="vt-barra-herramientas__etiqueta">Intervalo</span>
        <div className="vt-segmentado" role="group" aria-label="Intervalo de análisis">
          {INTERVALOS.map((opcionIntervalo) => (
            <button
              key={opcionIntervalo.valor}
              type="button"
              className={`vt-segmento${intervalo === opcionIntervalo.valor ? ' vt-segmento--activo' : ''}`}
              onClick={() => cambiarIntervalo(opcionIntervalo.valor)}
              aria-pressed={intervalo === opcionIntervalo.valor}
            >
              {opcionIntervalo.etiqueta}
            </button>
          ))}
        </div>

        <span className="vt-barra-herramientas__separador" aria-hidden="true" />

        <label className="vt-barra-herramientas__campo">
          <span className="vt-barra-herramientas__etiqueta">Mostrar</span>
          <CampoNumero
            valor={top}
            onCambio={setTop}
            min={1}
            max={200}
            aria-label="Número de celdas a mostrar"
          />
        </label>

        {data && (
          <span className="vt-grafica__meta">
            {data.total_celdas} celdas en total
            <AyudaContextual termino="visitas" alineacion="derecha" />
          </span>
        )}
      </div>

      {/* Navegación entre intervalos cuando hay más de uno */}
      {bins.length > 1 && (
        <div className="vt-paginacion vt-paginacion--compacta">
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-boton--icono"
            onClick={() => setIndiceBin((i) => Math.max(0, i - 1))}
            disabled={indiceBin === 0}
            aria-label="Intervalo anterior"
          >
            <IconoFlechaIzquierda tamano={16} />
          </button>
          <span>
            Intervalo {indiceBin + 1} de {bins.length}
            {binActual?.inicio && (
              <> · {formatearHora(binActual.inicio)} – {formatearHora(binActual.fin)}</>
            )}
          </span>
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-boton--icono"
            onClick={() => setIndiceBin((i) => Math.min(bins.length - 1, i + 1))}
            disabled={indiceBin >= bins.length - 1}
            aria-label="Intervalo siguiente"
          >
            <IconoFlechaDerecha tamano={16} />
          </button>
        </div>
      )}

      {isError ? (
        <ErrorConsulta error={error} onReintentar={refetch} alto={ALTO_ESTADO} />
      ) : isLoading ? (
        <Cargando mensaje="Cargando radiobases…" alto={ALTO_ESTADO} />
      ) : !opcion ? (
        <SinResultados
          titulo="Sin radiobases"
          mensaje="No hay celdas para los filtros seleccionados."
          alto={ALTO_ESTADO}
        />
      ) : (
        <div
          className={`vt-grafica__lienzo${
            isFetching && isPlaceholderData ? ' vt-grafica__lienzo--actualizando' : ''
          }`}
        >
          <ReactECharts
            ref={referencia}
            option={opcion}
            style={{ height: altoHistograma(celdas.length), width: '100%' }}
            opts={{ renderer: 'canvas' }}
            notMerge
            lazyUpdate
            onEvents={{ mouseover: alPasarRaton }}
          />
        </div>
      )}
    </div>
  );
}
