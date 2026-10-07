/**
 * Histograma de radiobases repetidas — HU-C2-008.
 *
 * Una «visita» es un tramo de permanencia: si el terminal vuelve a la misma celda más tarde,
 * cuenta otra vez. Es lo que revela los patrones de movilidad y las zonas de solapamiento donde
 * proliferan los handovers problemáticos.
 *
 * El intervalo de análisis se elige **arrastrando una bolita**: a medida que avanza, crecen los
 * minutos de cada intervalo y el histograma se actualiza; en el extremo derecho se analiza el
 * recorrido completo. La lógica del deslizador vive en `useHistogramaRepetidas`.
 *
 * Se dibuja con **barras horizontales** para que los identificadores de celda se lean sin rotar;
 * los que no caben se truncan y el nombre completo aparece al pasar el ratón por el rótulo.
 */

import { useCallback, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';

import AyudaContextual from './AyudaContextual.jsx';
import CampoNumero from './CampoNumero.jsx';
import { Cargando, ErrorConsulta, SinResultados } from './EstadoConsulta.jsx';
import { IconoFlechaDerecha, IconoFlechaIzquierda } from './Iconos.jsx';
import { useHistogramaRepetidas } from '../hooks/useHistogramaRepetidas.js';
import {
  altoHistograma,
  indiceDeRotulo,
  useOpcionCeldasRepetidas,
} from '../hooks/useSeriesEcharts.js';

const ALTO_ESTADO = 220;

export default function RepeatedCellsHistogram() {
  const [top, setTop] = useState(20);

  const referencia = useRef(null);

  const { consulta, celdas, rotulos, deslizador, intervalos } = useHistogramaRepetidas({ top });
  const { data, isLoading, isError, error, refetch, isFetching, isPlaceholderData } = consulta;

  const opcion = useOpcionCeldasRepetidas({ celdas, rotulos });

  /** Al pasar por un rótulo truncado se abre el tooltip de su barra, con el nombre completo. */
  const alPasarRaton = useCallback(
    (evento) => {
      const indice = indiceDeRotulo(evento, rotulos);
      if (indice < 0) return;
      referencia.current
        ?.getEchartsInstance?.()
        ?.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: indice });
    },
    [rotulos],
  );

  return (
    <div className="vt-grafica">
      <div className="vt-barra-herramientas">
        <label className="vt-deslizador">
          <span className="vt-barra-herramientas__etiqueta">Intervalo</span>
          <input
            type="range"
            className="vt-deslizador__control"
            min={1}
            max={deslizador.maximo}
            step={1}
            value={deslizador.valor}
            onChange={(e) => deslizador.mover(Number(e.target.value))}
            disabled={deslizador.deshabilitado}
            aria-label="Intervalo de análisis en minutos"
            aria-valuetext={deslizador.texto}
            style={{ '--vt-progreso': `${deslizador.progreso}%` }}
          />
          <output className="vt-deslizador__valor" aria-live="polite">
            {deslizador.texto}
          </output>
        </label>

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
            {data.total_celdas} PCI/PSC en total
            <AyudaContextual termino="visitas" alineacion="derecha" />
          </span>
        )}
      </div>

      {/* Navegación entre intervalos cuando hay más de uno */}
      {intervalos.total > 1 && (
        <div className="vt-paginacion vt-paginacion--compacta">
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-boton--icono"
            onClick={intervalos.irAnterior}
            disabled={intervalos.indice === 0}
            aria-label="Intervalo anterior"
          >
            <IconoFlechaIzquierda tamano={16} />
          </button>
          <span>
            Intervalo {intervalos.indice + 1} de {intervalos.total}
            {intervalos.etiqueta && <> · {intervalos.etiqueta}</>}
          </span>
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-boton--icono"
            onClick={intervalos.irSiguiente}
            disabled={intervalos.indice >= intervalos.total - 1}
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
