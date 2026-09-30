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

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  detectarHandovers,
  obtenerCeldasRepetidas,
  obtenerHandovers,
  obtenerResumen,
  obtenerSeries,
  obtenerSeriesCeldas,
  obtenerSesiones,
  obtenerVentanaHandover,
} from '../api/visualizacionTemporal.api.js';
import { useFiltros, useParametrosActivos, useVisStore } from '../store/visStore.js';

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

/** Eventos de handover con los filtros activos (HU-C2-009). */
export function useHandovers({ page = 1, pageSize = 50, orden = 'asc' } = {}) {
  const filtros = useFiltros();

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'handovers', filtros, page, pageSize, orden],
    queryFn: ({ signal }) => obtenerHandovers(filtros, { page, pageSize, orden, signal }),
    enabled: filtros.sesionIds.length > 0,
  });
}

/**
 * Series de los parámetros cuya capa está activa (HU-C2-004).
 *
 * Si el usuario apaga todas las capas no se consulta nada: pedir cero parámetros al backend
 * devolvería los cinco, que es justo lo contrario de lo que quiere.
 */
export function useSeries({ maxPuntos = 3000 } = {}) {
  const filtros = useFiltros();
  const parametros = useParametrosActivos();

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'series', filtros, parametros, maxPuntos],
    queryFn: ({ signal }) => obtenerSeries(filtros, { parametros, maxPuntos, signal }),
    enabled: filtros.sesionIds.length > 0 && parametros.length > 0,
  });
}

/** Secuencia temporal de radiobases (HU-C2-003). */
export function useSeriesCeldas() {
  const filtros = useFiltros();
  const eje = useVisStore((e) => e.ejeCeldas);

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

  const parametros = parametroDetalle === 'todos' ? [] : [parametroDetalle];

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

/** Histograma de radiobases repetidas (HU-C2-008). */
export function useCeldasRepetidas({ intervalo = 'total', top = 20 } = {}) {
  const filtros = useFiltros();

  return useQuery({
    ...COMUNES,
    queryKey: ['vt', 'celdas-repetidas', filtros, intervalo, top],
    queryFn: ({ signal }) => obtenerCeldasRepetidas(filtros, { intervalo, top, signal }),
    enabled: filtros.sesionIds.length > 0,
  });
}

/**
 * Suma los resúmenes de detección de varias sesiones en uno solo, para el aviso de la interfaz.
 *
 * @param {import('../types/index.js').ResumenDeteccion[]} resumenes
 */
export function combinarDetecciones(resumenes) {
  return {
    sesiones: resumenes.length,
    total_handovers: resumenes.reduce((suma, r) => suma + (r.total_handovers ?? 0), 0),
    duracion_ms: resumenes.reduce((suma, r) => suma + (r.duracion_ms ?? 0), 0),
  };
}

/**
 * Ejecuta la detección de handovers (HU-C2-001) sobre una o varias sesiones.
 *
 * Las sesiones se procesan **una tras otra**, no en paralelo: cada detección borra y reescribe
 * los eventos de su sesión, y lanzarlas a la vez solo multiplicaría la carga sobre la base de
 * datos sin acabar antes.
 *
 * Al terminar invalida **todo** el módulo: los eventos nuevos afectan a la tabla, al resumen, al
 * histograma y a los marcadores del timeline, así que refrescar solo una parte dejaría la
 * interfaz mostrando cifras incoherentes entre sí.
 */
export function useDeteccion() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ sesionIds, parametros }) => {
      const resumenes = [];
      for (const sesionId of sesionIds) {
        resumenes.push(await detectarHandovers(sesionId, parametros));
      }
      return combinarDetecciones(resumenes);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['vt'] }),
  });
}
