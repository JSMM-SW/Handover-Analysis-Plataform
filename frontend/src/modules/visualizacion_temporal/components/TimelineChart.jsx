/**
 * Timeline maestro — HU-C2-002 y HU-C2-004.
 *
 * Solo pinta: la construcción de la opción de ECharts vive en `useOpcionTimeline`
 * (regla 5 de CLAUDE.md). Aquí queda la parte que sí es de presentación: montar el gráfico,
 * enlazar el zoom con el store y mostrar los estados de carga, error y vacío.
 */

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';

import { Cargando, ErrorConsulta, SinDatosValidos, SinResultados } from './EstadoConsulta.jsx';
import LayerSelector from './LayerSelector.jsx';
import LeyendaMarcadoresHO from './LeyendaMarcadoresHO.jsx';
import { useSeries, useTodosLosHandovers } from '../hooks/useDatosVT.js';
import { useOpcionTimeline } from '../hooks/useSeriesEcharts.js';
import { useZoomSincronizado } from '../hooks/useZoomSincronizado.js';
import { useParametrosActivos, useVisStore } from '../store/visStore.js';

const ALTO = 340;

export default function TimelineChart() {
  const parametros = useParametrosActivos();
  const mostrarMarcadores = useVisStore((e) => e.capas.marcadoresHO);
  const idDestacado = useVisStore((e) => e.handoverSeleccionadoId);

  const series = useSeries();
  const handovers = useTodosLosHandovers({ alcance: 'graficas' });

  const eventos = useMemo(() => handovers.data?.items ?? [], [handovers.data]);

  const opcion = useOpcionTimeline({
    datos: series.data,
    parametros,
    handovers: eventos,
    mostrarMarcadores,
    idDestacado,
  });

  // Zoom compartido con la secuencia de radiobases: rueda del ratón y deslizador inferior.
  const { referencia, onEvents } = useZoomSincronizado(opcion);

  const cobertura = series.data?.cobertura ?? [];
  // Con `keepPreviousData` se sigue viendo la gráfica anterior mientras llega la nueva: se atenúa
  // para que el cambio de filtro se perciba como una transición y no como un salto.
  const actualizando = series.isFetching && series.isPlaceholderData;

  return (
    <div className="vt-grafica">
      <LayerSelector cobertura={cobertura} />

      {series.isError ? (
        <ErrorConsulta error={series.error} onReintentar={series.refetch} alto={ALTO} />
      ) : parametros.length === 0 ? (
        <SinResultados
          titulo="Ninguna capa activa"
          mensaje="Activa al menos un parámetro de radiofrecuencia para ver la gráfica."
          alto={ALTO}
        />
      ) : series.isLoading ? (
        <Cargando mensaje="Cargando series…" alto={ALTO} />
      ) : !series.data?.t?.length ? (
        <SinResultados
          titulo="Sin mediciones"
          mensaje="No hay datos para los filtros seleccionados."
          alto={ALTO}
        />
      ) : (
        <>
          <LeyendaMarcadoresHO />
          <div className={`vt-grafica__lienzo${actualizando ? ' vt-grafica__lienzo--actualizando' : ''}`}>
            <ReactECharts
              ref={referencia}
              option={opcion}
              style={{ height: ALTO, width: '100%' }}
              opts={{ renderer: 'canvas' }}
              notMerge
              lazyUpdate
              onEvents={onEvents}
            />
          </div>

          <SinDatosValidos
            cobertura={cobertura.filter((c) => parametros.includes(c.parametro))}
          />

          <p className="vt-grafica__pie">
            {series.data.puntos_devueltos.toLocaleString('es-EC')} puntos mostrados
            {series.data.downsampled && (
              <>
                {' '}de {series.data.puntos_originales.toLocaleString('es-EC')} — la serie se
                submuestreó con LTTB, que conserva picos y valles.
              </>
            )}
            {eventos.length > 0 && ` · ${eventos.length} handovers marcados.`}
          </p>
        </>
      )}
    </div>
  );
}
