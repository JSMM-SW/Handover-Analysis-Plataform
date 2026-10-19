/**
 * Una función por endpoint del Módulo 2. Sin lógica: solo traducen argumentos a HTTP.
 *
 * Espejo exacto de `backend/app/modules/visualizacion_temporal/router.py`.
 */

import { TIMEOUT_MS, construirQuery, peticion } from './client.js';
import { zonaHoraria } from '../utils/fechas.js';

/**
 * Traduce los filtros del store al bloque de query params del backend.
 *
 * El store usa camelCase (convención de JavaScript) y el backend snake_case: la traducción vive
 * **solo aquí**, para que ningún componente tenga que conocer los dos vocabularios.
 *
 * @param {import('../types/index.js').FiltrosTemporales} filtros
 */
export function filtrosAQuery(filtros = {}) {
  return {
    // Lista: el backend acepta el parámetro repetido (`?sesion_id=a&sesion_id=b`).
    sesion_id: filtros.sesionIds ?? [],
    desde: filtros.desde ?? null,
    hasta: filtros.hasta ?? null,
    hora_inicio: filtros.horaInicio ?? null,
    hora_fin: filtros.horaFin ?? null,
    tecnologia: filtros.tecnologias ?? [],
    // La franja horaria se escribe en hora local; el backend la compara en esta zona.
    zona_horaria: zonaHoraria(),
  };
}

/** `GET /sesiones` — sesiones disponibles. @returns {Promise<import('../types/index.js').Sesion[]>} */
export function obtenerSesiones({ signal } = {}) {
  return peticion('/sesiones', { signal });
}

/**
 * `GET /disponibilidad` — días, franjas horarias y tecnologías con datos en las sesiones elegidas.
 * @returns {Promise<import('../types/index.js').Disponibilidad>}
 */
export function obtenerDisponibilidad(sesionIds, { signal } = {}) {
  const query = construirQuery({ sesion_id: sesionIds, zona_horaria: zonaHoraria() });
  return peticion(`/disponibilidad${query}`, { signal });
}

/**
 * La detección recorre siempre la sesión entera (no admite rango temporal) y además reescribe sus
 * eventos, así que se le da más margen que a una consulta.
 */
const TIMEOUT_DETECCION_MS = 2 * TIMEOUT_MS;

/**
 * `POST /sesiones/{id}/detectar-handovers` — ejecuta la detección (HU-C2-001).
 * @returns {Promise<import('../types/index.js').ResumenDeteccion>}
 */
export function detectarHandovers(sesionId, parametros = {}, { signal } = {}) {
  return peticion(`/sesiones/${encodeURIComponent(sesionId)}/detectar-handovers`, {
    method: 'POST',
    body: {
      muestras_confirmacion: parametros.muestrasConfirmacion ?? 2,
      ventana_ping_pong_s: parametros.ventanaPingPongS ?? 10,
      max_gap_s: parametros.maxGapS ?? 30,
      recalcular: parametros.recalcular ?? true,
    },
    signal,
    timeoutMs: TIMEOUT_DETECCION_MS,
  });
}

/**
 * `GET /handovers` — tabla de eventos (HU-C2-009).
 * @returns {Promise<import('../types/index.js').PaginaHandovers>}
 */
export function obtenerHandovers(filtros, { page = 1, pageSize = 50, orden = 'asc', signal } = {}) {
  const query = construirQuery({
    ...filtrosAQuery(filtros),
    page,
    page_size: pageSize,
    orden,
  });
  return peticion(`/handovers${query}`, { signal });
}

/** Eventos por página al pedirlos todos: el máximo que admite `GET /handovers`. */
const PAGINA_MAXIMA = 500;

/**
 * `GET /handovers`, todas las páginas — los marcadores de las gráficas y la navegación del detalle
 * necesitan **todos** los eventos, no solo los primeros 500 (la Sesión 4 tiene 581).
 *
 * La primera página dice cuántos hay; las demás se piden a la vez. Devuelve la misma forma que
 * `obtenerHandovers`, con todos los eventos en `items`.
 * @returns {Promise<import('../types/index.js').PaginaHandovers>}
 */
export async function obtenerTodosLosHandovers(filtros, { signal } = {}) {
  const pedir = (page) => obtenerHandovers(filtros, { page, pageSize: PAGINA_MAXIMA, signal });

  const primera = await pedir(1);
  const paginas = Math.ceil(primera.total / PAGINA_MAXIMA);
  if (paginas <= 1) return primera;

  const resto = await Promise.all(
    Array.from({ length: paginas - 1 }, (_, indice) => pedir(indice + 2)),
  );
  const items = [primera, ...resto].flatMap((pagina) => pagina.items);
  return { ...primera, page_size: items.length, items };
}

/**
 * `GET /series` — series de parámetros RF (HU-C2-004).
 * @returns {Promise<import('../types/index.js').Series>}
 */
export function obtenerSeries(filtros, { parametros = [], maxPuntos = 3000, signal } = {}) {
  const query = construirQuery({
    ...filtrosAQuery(filtros),
    parametros,
    max_puntos: maxPuntos,
  });
  return peticion(`/series${query}`, { signal });
}

/**
 * `GET /series-celdas` — secuencia de radiobases (HU-C2-003).
 * @returns {Promise<import('../types/index.js').TramosCelda>}
 */
export function obtenerSeriesCeldas(filtros, { eje = 'celda_clave', signal } = {}) {
  const query = construirQuery({ ...filtrosAQuery(filtros), eje });
  return peticion(`/series-celdas${query}`, { signal });
}

/**
 * `GET /handovers/{id}/ventana` — ventana PRE/POST (HU-C2-005).
 * @returns {Promise<import('../types/index.js').VentanaHandover>}
 */
export function obtenerVentanaHandover(
  idEvento,
  { segundosAntes = 5, segundosDespues = 5, parametros = [], signal } = {},
) {
  const query = construirQuery({
    segundos_antes: segundosAntes,
    segundos_despues: segundosDespues,
    parametros,
  });
  return peticion(`/handovers/${encodeURIComponent(idEvento)}/ventana${query}`, { signal });
}

/** `GET /resumen` — totales del dataset (HU-C2-007). @returns {Promise<import('../types/index.js').Resumen>} */
export function obtenerResumen(filtros, { signal } = {}) {
  return peticion(`/resumen${construirQuery(filtrosAQuery(filtros))}`, { signal });
}

/**
 * `GET /celdas-repetidas` — histograma de radiobases (HU-C2-008).
 *
 * `minutos` es la duración de cada intervalo; `null` analiza el total. `eje` decide qué cuenta
 * cada barra: una celda (`celda_clave`) o un PCI/PSC (`psc_pci`).
 * @returns {Promise<import('../types/index.js').CeldasRepetidas>}
 */
export function obtenerCeldasRepetidas(
  filtros,
  { minutos = null, top = 20, eje = 'celda_clave', signal } = {},
) {
  const query = construirQuery({ ...filtrosAQuery(filtros), minutos, top, eje });
  return peticion(`/celdas-repetidas${query}`, { signal });
}
