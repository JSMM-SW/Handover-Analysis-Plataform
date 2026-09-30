/**
 * Una función por endpoint del Módulo 2. Sin lógica: solo traducen argumentos a HTTP.
 *
 * Espejo exacto de `backend/app/modules/visualizacion_temporal/router.py`.
 */

import { construirQuery, peticion } from './client.js';

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
  };
}

/** `GET /sesiones` — sesiones disponibles. @returns {Promise<import('../types/index.js').Sesion[]>} */
export function obtenerSesiones({ signal } = {}) {
  return peticion('/sesiones', { signal });
}

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
 * @returns {Promise<import('../types/index.js').CeldasRepetidas>}
 */
export function obtenerCeldasRepetidas(filtros, { intervalo = 'total', top = 20, signal } = {}) {
  const query = construirQuery({ ...filtrosAQuery(filtros), intervalo, top });
  return peticion(`/celdas-repetidas${query}`, { signal });
}
