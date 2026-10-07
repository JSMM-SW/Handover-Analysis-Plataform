/**
 * Hooks de datos del Módulo 2 (Capa 2).
 *
 * Adaptan lo que devuelve el servidor a lo que necesita cada gráfica. Los componentes no llaman
 * nunca a la API directamente: piden datos a estos hooks.
 *
 * Todas las consultas usan `['vt', <recurso>, filtros]` como clave, de modo que:
 * - cambiar un filtro relanza automáticamente las consultas afectadas (HU-C2-006 CA1);
 * - `queryClient.invalidateQueries({ queryKey: ['vt'] })` refresca el módulo entero tras
 *   ejecutar una detección.
 */

import { useCallback, useEffect } from 'react';
import {
  keepPreviousData,
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import {
  detectarHandovers,
  obtenerCeldasRepetidas,
  obtenerDisponibilidad,
  obtenerHandovers,
  obtenerResumen,
  obtenerSeries,
  obtenerSeriesCeldas,
  obtenerSesiones,
  obtenerVentanaHandover,
} from '../api/visualizacionTemporal.api.js';
import {
  useFiltros,
  useFiltrosGraficas,
  useParametrosActivos,
  useVisStore,
} from '../store/visStore.js';
import { PARAMETROS_RF } from '../types/index.js';
import { useAvisoTemporal } from './useInterfaz.js';

/** Las sesiones cambian poco; no hace falta revalidarlas a cada rato. */
const CINCO_MINUTOS = 5 * 60 * 1000;
const UN_MINUTO = 60 * 1000;

/**
 * Opciones comunes. `keepPreviousData` evita que la interfaz parpadee a "cargando" cada vez que
 * se mueve un filtro: se sigue viendo el resultado anterior, atenuado, hasta que llega el nuevo.
 */
const COMUNES = {
  placeholderData: keepPreviousData,
  staleTime: UN_MINUTO,
  retry: 1,
};

/** Sesiones disponibles para el selector del header. */
export function useSesiones() {
  return useQuery({
    queryKey: ['vt', 'sesiones'],
    queryFn: ({ signal }) => obtenerSesiones({ signal }),
    staleTime: CINCO_MINUTOS,
    retry: 1,
  });
}

/**
 * Días, franjas horarias y tecnologías con datos en las sesiones elegidas. Alimenta el
 * calendario y los filtros: solo se ofrece lo que existe en la base.
 */
export function useDisponibilidad() {
  const sesionIds = useVisStore((e) => e.sesionIds);

  return useQuery({
    queryKey: ['vt', 'disponibilidad', sesionIds],
    queryFn: ({ signal }) => obtenerDisponibilidad(sesionIds, { signal }),
    enabled: sesionIds.length > 0,
    staleTime: CINCO_MINUTOS,
    retry: 1,
  });
}

/**
 * Eventos de handover con los filtros activos (HU-C2-009).
 *
 * @param {Object} [opciones]
 * @param {'analisis'|'graficas'} [opciones.alcance]  `graficas` pide solo la sesión enfocada,
 *   para los marcadores de las gráficas temporales; `analisis` (por defecto), todas.
 */
export function useHandovers({ page = 1, pageSize = 50, orden = 'asc', alcance = 'analisis' } = {}) {
  const filtrosAnalisis = useFiltros();
  const filtrosGraficas = useFiltrosGraficas();
  const filtros = alcance === 'graficas' ? filtrosGraficas : filtrosAnalisis;

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'handovers', filtros, page, pageSize, orden],
    queryFn: ({ signal }) => obtenerHandovers(filtros, { page, pageSize, orden, signal }),
    enabled: filtros.sesionIds.length > 0,
  });
}

/**
 * Elige solo el primer handover de la lista en cuanto llega, para que la sección de eventos
 * arranque con la tabla plegada y la gráfica del detalle a la vista.
 *
 * Solo actúa con la selección pendiente (al elegir sesiones o cambiar un filtro) y con datos
 * vigentes: mientras se ven los datos anteriores atenuados, su primer evento ya no vale.
 *
 * @param {import('../types/index.js').Handover|undefined} primerEvento
 * @param {boolean} datosVigentes
 */
export function useSeleccionPorDefecto(primerEvento, datosVigentes) {
  const pendiente = useVisStore((e) => e.seleccionPendiente);
  const seleccionarPorDefecto = useVisStore((e) => e.seleccionarPorDefecto);
  const idPrimero = primerEvento?.id_evento ?? null;

  useEffect(() => {
    if (pendiente && datosVigentes && idPrimero) seleccionarPorDefecto(idPrimero);
  }, [pendiente, datosVigentes, idPrimero, seleccionarPorDefecto]);
}

/**
 * Series de los parámetros cuya capa está activa (HU-C2-004).
 *
 * Si el usuario apaga todas las capas no se consulta nada: pedir cero parámetros al backend
 * devolvería los cinco, que es justo lo contrario de lo que quiere.
 */
export function useSeries({ maxPuntos = 3000 } = {}) {
  const filtros = useFiltrosGraficas();
  const parametros = useParametrosActivos();

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'series', filtros, parametros, maxPuntos],
    queryFn: ({ signal }) => obtenerSeries(filtros, { parametros, maxPuntos, signal }),
    enabled: filtros.sesionIds.length > 0 && parametros.length > 0,
  });
}

/**
 * Identificador con el que se rotula la secuencia de radiobases: **solo PCI/PSC**. Los tramos
 * se siguen formando por celda (ECI), igual que la detección; lo que cambia es el rótulo.
 */
const EJE_CELDAS = 'psc_pci';

/** Secuencia temporal de radiobases (HU-C2-003). */
export function useSeriesCeldas() {
  const filtros = useFiltrosGraficas();
  const eje = EJE_CELDAS;

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'series-celdas', filtros, eje],
    queryFn: ({ signal }) => obtenerSeriesCeldas(filtros, { eje, signal }),
    enabled: filtros.sesionIds.length > 0,
  });
}

/** Resumen general (HU-C2-007). */
export function useResumen() {
  const filtros = useFiltros();

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'resumen', filtros],
    queryFn: ({ signal }) => obtenerResumen(filtros, { signal }),
    enabled: filtros.sesionIds.length > 0,
  });
}

/** Ventana PRE/POST del handover seleccionado (HU-C2-005). */
export function useVentanaHandover() {
  const idEvento = useVisStore((e) => e.handoverSeleccionadoId);
  const segundos = useVisStore((e) => e.ventanaSegundos);
  const parametroDetalle = useVisStore((e) => e.parametroDetalle);

  // «Todos» son los de la interfaz, no los que conoce el backend (que incluye RSCP).
  const parametros = parametroDetalle === 'todos' ? PARAMETROS_RF : [parametroDetalle];

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'ventana', idEvento, segundos, parametroDetalle],
    queryFn: ({ signal }) =>
      obtenerVentanaHandover(idEvento, {
        segundosAntes: segundos,
        segundosDespues: segundos,
        parametros,
        signal,
      }),
    enabled: Boolean(idEvento),
  });
}

/**
 * Histograma de radiobases repetidas (HU-C2-008).
 *
 * @param {Object} [opciones]
 * @param {number|null} [opciones.minutos]  duración de cada intervalo; `null` analiza el total
 * @param {number} [opciones.top]
 */
export function useCeldasRepetidas({ minutos = null, top = 20 } = {}) {
  const filtros = useFiltrosGraficas();
  // Una barra por PCI/PSC, como la secuencia de radiobases.
  const eje = EJE_CELDAS;

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'celdas-repetidas', filtros, minutos, top, eje],
    queryFn: ({ signal }) => obtenerCeldasRepetidas(filtros, { minutos, top, eje, signal }),
    enabled: filtros.sesionIds.length > 0,
  });
}

/**
 * Suma los resúmenes de detección de varias sesiones en uno solo, para el aviso de la interfaz.
 *
 * @param {import('../types/index.js').ResumenDeteccion[]} resumenes
 * @param {{sesionId: string, mensaje: string}[]} [fallidas]  sesiones cuya detección falló
 */
export function combinarDetecciones(resumenes, fallidas = []) {
  return {
    sesiones: resumenes.length,
    total_handovers: resumenes.reduce((suma, r) => suma + (r.total_handovers ?? 0), 0),
    duracion_ms: resumenes.reduce((suma, r) => suma + (r.duracion_ms ?? 0), 0),
    fallidas,
  };
}

/** Clave de la mutación de detección: permite saber desde cualquier componente si hay una en curso. */
const CLAVE_DETECCION = ['vt', 'deteccion'];

/** Referencia estable para «ninguna fallida». */
const SIN_FALLIDAS = [];

/**
 * Ejecuta la detección de handovers (HU-C2-001) sobre una o varias sesiones.
 *
 * Las sesiones se procesan **una tras otra**, no en paralelo: cada detección borra y reescribe
 * los eventos de su sesión, y lanzarlas a la vez solo multiplicaría la carga sobre la base de
 * datos sin acabar antes. Si una falla, las demás siguen; las fallidas se devuelven aparte para
 * poder avisar y reintentarlas.
 *
 * Al terminar invalida **todo** el módulo: los eventos nuevos afectan a la tabla, al resumen, al
 * histograma y a los marcadores del timeline, así que refrescar solo una parte dejaría la
 * interfaz mostrando cifras incoherentes entre sí.
 *
 * También olvida el evento elegido: la detección reescribe los eventos con identificadores
 * nuevos, y el anterior ya no existe. Se elige otra vez el primero de la lista nueva.
 */
export function useDeteccion() {
  const queryClient = useQueryClient();
  const reiniciarSeleccion = useVisStore((e) => e.reiniciarSeleccion);

  return useMutation({
    mutationKey: CLAVE_DETECCION,
    mutationFn: async ({ sesionIds, parametros }) => {
      const resumenes = [];
      const fallidas = [];
      for (const sesionId of sesionIds) {
        try {
          resumenes.push(await detectarHandovers(sesionId, parametros));
        } catch (error) {
          fallidas.push({ sesionId, mensaje: error?.message ?? 'Error desconocido' });
        }
      }
      return combinarDetecciones(resumenes, fallidas);
    },
    onSuccess: () => {
      reiniciarSeleccion();
      return queryClient.invalidateQueries({ queryKey: ['vt'] });
    },
  });
}

/** `true` mientras se están detectando handovers de alguna sesión. */
export function useDetectando() {
  return useIsMutating({ mutationKey: CLAVE_DETECCION }) > 0;
}

/**
 * Detección automática: al elegir una sesión, sus handovers se detectan solos.
 *
 * Cada sesión se detecta **una vez por apertura de la página**: volver a elegirla no repite la
 * detección. Así los eventos siempre salen del algoritmo vigente, sin que el usuario tenga que
 * recordar pulsar un botón, y sin reescribirlos cada vez que marca o desmarca una casilla.
 *
 * Una sesión que falla no se reintenta sola (fallaría en bucle): `reintentar` lo hace a petición.
 */
export function useDeteccionAutomatica() {
  const sesionIds = useVisStore((e) => e.sesionIds);
  const marcarDetectadas = useVisStore((e) => e.marcarDetectadas);
  const deteccion = useDeteccion();
  const { mutate } = deteccion;
  const { data: sesiones = [] } = useSesiones();

  useEffect(() => {
    // Se lee el store en el momento, no el valor del render: en modo estricto React ejecuta el
    // efecto dos veces seguidas y la segunda no debe lanzar la misma detección otra vez.
    const yaDetectadas = useVisStore.getState().sesionesDetectadas;
    const pendientes = sesionIds.filter((id) => !yaDetectadas.includes(id));
    if (!pendientes.length) return;

    marcarDetectadas(pendientes);
    mutate({ sesionIds: pendientes });
  }, [sesionIds, marcarDetectadas, mutate]);

  const fallidas = deteccion.data?.fallidas ?? SIN_FALLIDAS;
  const reintentar = useCallback(
    () => mutate({ sesionIds: fallidas.map((f) => f.sesionId) }),
    [mutate, fallidas],
  );

  // El aviso habla de **todas las sesiones elegidas**, no solo de la última detectada: al añadir
  // una sesión solo se detecta esa, pero las tarjetas suman todas. El total sale de
  // `GET /sesiones`, que la detección refresca antes de darse por terminada, y es la misma
  // cuenta de `eventos_handover` que usa la tarjeta «Handovers».
  const elegidas = sesiones.filter((s) => sesionIds.includes(s.sesion_id));
  const resumenSeleccion = {
    total_handovers: elegidas.reduce((suma, s) => suma + (s.n_handovers ?? 0), 0),
    sesiones: elegidas.length,
  };

  // Se muestra 3 s tras cada detección terminada y luego se oculta solo.
  const avisoVisible = useAvisoTemporal(
    deteccion.isSuccess && !deteccion.isPending ? deteccion.submittedAt : null,
  );

  return { ...deteccion, fallidas, reintentar, resumenSeleccion, avisoVisible };
}
