/**
 * Zoom temporal compartido entre la línea de tiempo y la secuencia de radiobases (Capa 2).
 *
 * Las dos gráficas tienen eje X de tiempo y el mismo control de zoom (rueda del ratón y
 * deslizador inferior). El rango vive en el store (`rangoZoom`): al hacer zoom en una, la otra
 * muestra el mismo tramo del recorrido, que es lo que permite comparar la señal con la celda
 * servidora de un vistazo.
 */

import { useCallback, useEffect, useMemo, useRef } from 'react';

import { useVisStore } from '../store/visStore.js';

/** Espera, en ms, antes de escribir el rango en el store mientras se arrastra el deslizador. */
const RETARDO_ESCRITURA_MS = 200;

/** Tiempo, en ms, durante el que un evento de zoom se atribuye al propio código y se ignora. */
const VENTANA_PROGRAMATICA_MS = 300;

/**
 * @param {Object} opcion  la opción de ECharts que pinta la gráfica. Al cambiar (otros datos,
 *   otro handover destacado) ECharts vuelve al recorrido completo, así que el rango del store se
 *   aplica otra vez.
 * @returns {{referencia: import('react').RefObject, onEvents: Record<string, Function>}}
 *   `referencia` va al `ref` de `<ReactECharts>` y `onEvents` a su prop del mismo nombre.
 */
export function useZoomSincronizado(opcion) {
  const rangoZoom = useVisStore((e) => e.rangoZoom);
  const setRangoZoom = useVisStore((e) => e.setRangoZoom);

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

  /**
   * Al mover el zoom se escribe el rango en el store con un pequeño retardo: sin él, arrastrar el
   * deslizador dispararía un render por cada píxel.
   */
  const alCambiarZoom = useCallback(() => {
    if (zoomProgramatico.current) return;

    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => {
      const instancia = referencia.current?.getEchartsInstance?.();
      if (!instancia) return;

      const { startValue, endValue } = instancia.getOption()?.dataZoom?.[0] ?? {};
      if (startValue == null || endValue == null) return;

      const nuevo = [new Date(startValue).toISOString(), new Date(endValue).toISOString()];

      // Solo se escribe si el rango cambió de verdad. Es la salvaguarda que rompe el ciclo
      // render → setOption → evento dataZoom → store → render: al llegar el mismo rango una
      // segunda vez, aquí se corta.
      const actual = useVisStore.getState().rangoZoom;
      if (actual && actual[0] === nuevo[0] && actual[1] === nuevo[1]) return;

      setRangoZoom(nuevo);
    }, RETARDO_ESCRITURA_MS);
  }, [setRangoZoom]);

  useEffect(() => () => clearTimeout(temporizador.current), []);

  /**
   * Aplica el rango del store, lo haya fijado esta gráfica o la otra. Se aplica sobre la
   * instancia en lugar de reconstruir la opción para no perder el estado interno del gráfico ni
   * provocar un remontaje.
   */
  useEffect(() => {
    const instancia = referencia.current?.getEchartsInstance?.();
    if (!instancia || !rangoZoom) return undefined;

    zoomProgramatico.current = true;
    instancia.dispatchAction({
      type: 'dataZoom',
      startValue: new Date(rangoZoom[0]).getTime(),
      endValue: new Date(rangoZoom[1]).getTime(),
    });

    // Se libera en el siguiente ciclo, cuando ECharts ya ha emitido su evento.
    const id = setTimeout(() => {
      zoomProgramatico.current = false;
    }, VENTANA_PROGRAMATICA_MS);
    return () => clearTimeout(id);
  }, [rangoZoom, opcion]);

  const onEvents = useMemo(() => ({ dataZoom: alCambiarZoom }), [alCambiarZoom]);

  return { referencia, onEvents };
}
