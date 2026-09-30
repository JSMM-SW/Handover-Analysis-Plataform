/**
 * Timeline maestro — HU-C2-002 y HU-C2-004.
 *
 * Solo pinta: la construcción de la opción de ECharts vive en `useOpcionTimeline`
 * (regla 5 de CLAUDE.md). Aquí queda la parte que sí es de presentación: montar el gráfico,
 * enlazar el zoom con el store y mostrar los estados de carga, error y vacío.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';

import { Cargando, ErrorConsulta, SinDatosValidos, SinResultados } from './EstadoConsulta.jsx';
import LayerSelector from './LayerSelector.jsx';
import LeyendaMarcadoresHO from './LeyendaMarcadoresHO.jsx';
import { useHandovers, useSeries } from '../hooks/useDatosVT.js';
import { useOpcionTimeline } from '../hooks/useSeriesEcharts.js';
import { useParametrosActivos, useVisStore } from '../store/visStore.js';

const ALTO = 340;

export default function TimelineChart() {
  const parametros = useParametrosActivos();
  const mostrarMarcadores = useVisStore((e) => e.capas.marcadoresHO);
  const idDestacado = useVisStore((e) => e.handoverSeleccionadoId);
  const rangoZoom = useVisStore((e) => e.rangoZoom);
  const setRangoZoom = useVisStore((e) => e.setRangoZoom);

  const series = useSeries();
  const handovers = useHandovers({ pageSize: 500 });

  const referencia = useRef(null);
  const temporizador = useRef(null);

  /**
   * Marca que el zoom lo ha provocado el propio código y no el usuario.
   *
   * Sin esto hay un bucle infinito que congela la pestaña: `dispatchAction({type:'dataZoom'})`
   * emite el evento `dataZoom`, el manejador escribe `rangoZoom` en el store, el cambio del store
   * vuelve a ejecutar el efecto, que despacha otra vez… El retardo del manejador no lo rompe,
   * solo lo hace más lento.
   */
  const zoomProgramatico = useRef(false);

  const eventos = useMemo(() => handovers.data?.items ?? [], [handovers.data]);

  const opcion = useOpcionTimeline({
    datos: series.data,
    parametros,
    handovers: eventos,
    mostrarMarcadores,
    idDestacado,
  });

  /**
   * Al mover el zoom se escribe el rango en el store con un pequeño retardo: sin él, arrastrar el
   * slider dispararía un render por cada píxel.
   */
  const alCambiarZoom = useCallback(() => {
    if (zoomProgramatico.current) return;

    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => {
      const instancia = referencia.current?.getEchartsInstance?.();
      if (!instancia) return;

      const { startValue, endValue } = instancia.getOption()?.dataZoom?.[0] ?? {};
      if (startValue == null || endValue == null) return;

      const nuevo = [
        new Date(startValue).toISOString(),
        new Date(endValue).toISOString(),
      ];

      // Solo se escribe si el rango cambió de verdad. Es la salvaguarda que rompe el ciclo
      // render → setOption → evento dataZoom → store → render: al llegar el mismo rango una
      // segunda vez, aquí se corta.
      const actual = useVisStore.getState().rangoZoom;
      if (actual && actual[0] === nuevo[0] && actual[1] === nuevo[1]) return;

      setRangoZoom(nuevo);
    }, 200);
  }, [setRangoZoom]);

  useEffect(() => () => clearTimeout(temporizador.current), []);

  /**
   * Zoom automático cuando se selecciona un handover en la tabla (estructura V1 §3).
   *
   * Se aplica sobre la instancia en lugar de reconstruir la opción para no perder el estado
   * interno del gráfico ni provocar un remontaje.
   */
  useEffect(() => {
    const instancia = referencia.current?.getEchartsInstance?.();
    if (!instancia || !rangoZoom) return;

    zoomProgramatico.current = true;
    instancia.dispatchAction({
      type: 'dataZoom',
      startValue: new Date(rangoZoom[0]).getTime(),
      endValue: new Date(rangoZoom[1]).getTime(),
    });

    // Se libera en el siguiente ciclo, cuando ECharts ya ha emitido su evento.
    const id = setTimeout(() => {
      zoomProgramatico.current = false;
    }, 300);
    return () => clearTimeout(id);
  }, [rangoZoom]);

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
              onEvents={{ dataZoom: alCambiarZoom }}
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
