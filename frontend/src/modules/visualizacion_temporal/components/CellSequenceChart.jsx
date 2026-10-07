/**
 * Secuencia temporal de radiobases — HU-C2-003.
 *
 * Gráfica escalonada alineada con el timeline maestro: comparte el mismo `rangoZoom` del store, de
 * modo que al hacer zoom en una la otra sigue. Esa alineación es lo que permite comprobar de un
 * vistazo el CA2 de la historia: **cada escalón coincide con un marcador de handover**.
 */

import { useEffect, useMemo, useRef } from 'react';
import ReactECharts from 'echarts-for-react';

import AyudaContextual from './AyudaContextual.jsx';
import { Cargando, ErrorConsulta, SinResultados } from './EstadoConsulta.jsx';
import LeyendaMarcadoresHO from './LeyendaMarcadoresHO.jsx';
import { useHandovers, useSeriesCeldas } from '../hooks/useDatosVT.js';
import { useOpcionSecuenciaCeldas } from '../hooks/useSeriesEcharts.js';
import { useVisStore } from '../store/visStore.js';

const ALTO = 200;

export default function CellSequenceChart() {
  const mostrarMarcadores = useVisStore((e) => e.capas.marcadoresHO);
  const idDestacado = useVisStore((e) => e.handoverSeleccionadoId);
  const rangoZoom = useVisStore((e) => e.rangoZoom);

  const celdas = useSeriesCeldas();
  const handovers = useHandovers({ pageSize: 500, alcance: 'graficas' });
  const referencia = useRef(null);

  const tramos = useMemo(() => celdas.data?.tramos ?? [], [celdas.data]);
  const eventos = useMemo(() => handovers.data?.items ?? [], [handovers.data]);

  const opcion = useOpcionSecuenciaCeldas({
    tramos,
    handovers: eventos,
    mostrarMarcadores,
    idDestacado,
  });

  // Sincronización del eje X con el timeline maestro.
  useEffect(() => {
    const instancia = referencia.current?.getEchartsInstance?.();
    if (!instancia || !rangoZoom) return;

    instancia.dispatchAction({
      type: 'dataZoom',
      startValue: new Date(rangoZoom[0]).getTime(),
      endValue: new Date(rangoZoom[1]).getTime(),
    });
  }, [rangoZoom]);

  return (
    <div className="vt-grafica">
      <div className="vt-barra-herramientas">
        <span className="vt-barra-herramientas__etiqueta">
          PCI/PSC
          <AyudaContextual termino="pci_psc" alineacion="izquierda" />
        </span>

        {celdas.data && (
          <span className="vt-grafica__meta">
            {celdas.data.celdas_distintas} radiobases · {tramos.length} tramos
            <AyudaContextual termino="tramo" alineacion="derecha" />
          </span>
        )}
      </div>

      {celdas.isError ? (
        <ErrorConsulta error={celdas.error} onReintentar={celdas.refetch} alto={ALTO} />
      ) : celdas.isLoading ? (
        <Cargando mensaje="Cargando secuencia de celdas…" alto={ALTO} />
      ) : !tramos.length ? (
        <SinResultados
          titulo="Sin tramos"
          mensaje="No hay mediciones con celda identificable para estos filtros."
          alto={ALTO}
        />
      ) : (
        <>
          <LeyendaMarcadoresHO />
          <div
            className={`vt-grafica__lienzo${
              celdas.isFetching && celdas.isPlaceholderData ? ' vt-grafica__lienzo--actualizando' : ''
            }`}
          >
            <ReactECharts
              ref={referencia}
              option={opcion}
              style={{ height: ALTO, width: '100%' }}
              opts={{ renderer: 'canvas' }}
              notMerge
              lazyUpdate
            />
          </div>
        </>
      )}
    </div>
  );
}
