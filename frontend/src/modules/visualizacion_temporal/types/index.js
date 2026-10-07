/**
 * Tipos y constantes compartidas del Módulo 2 (visualización temporal).
 *
 * El proyecto **no usa TypeScript** (verificado en la Fase 0), así que los contratos se declaran
 * como `typedef` de JSDoc. El editor los autocompleta igual y no obliga a introducir una cadena
 * de compilación nueva a mitad del proyecto.
 *
 * Estos tipos son el espejo de los schemas Pydantic de `backend/app/modules/
 * visualizacion_temporal/schemas.py`. Si cambia el backend, se cambian aquí.
 */

import { COLORES_RF } from '../utils/temaVisual.js';

// ================================================================================================
// Parámetros de radiofrecuencia
// ================================================================================================

/**
 * Parámetros de radiofrecuencia que analiza la interfaz.
 *
 * RSCP no está: no se tiene en cuenta en ningún análisis. El backend lo sigue devolviendo
 * (`rscp_dbm`, `delta_rscp_db`) y simplemente se ignora.
 *
 * @typedef {'rsrp_dbm'|'rsrq_db'|'rssnr_db'|'rssi_dbm'} ParametroRF
 */

/**
 * Único diccionario de etiquetas de la interfaz. **Ningún componente escribe estos nombres a
 * mano**: así el texto de la UI no se desincroniza entre pantallas.
 *
 * `rssnr_db` conserva el nombre RSSNR del CSV.
 *
 * Los colores salen de `utils/temaVisual.js`.
 *
 * @type {Record<ParametroRF, {etiqueta: string, corta: string, unidad: string, color: string}>}
 */
export const ETIQUETAS_RF = {
  rsrp_dbm: { etiqueta: 'RSRP (dBm)', corta: 'RSRP', unidad: 'dBm', color: COLORES_RF.rsrp_dbm },
  rsrq_db: { etiqueta: 'RSRQ (dB)', corta: 'RSRQ', unidad: 'dB', color: COLORES_RF.rsrq_db },
  rssnr_db: { etiqueta: 'RSSNR (dB)', corta: 'RSSNR', unidad: 'dB', color: COLORES_RF.rssnr_db },
  rssi_dbm: { etiqueta: 'RSSI (dBm)', corta: 'RSSI', unidad: 'dBm', color: COLORES_RF.rssi_dbm },
};

/** Orden en que se muestran los parámetros en toda la interfaz. @type {ParametroRF[]} */
export const PARAMETROS_RF = ['rsrp_dbm', 'rsrq_db', 'rssnr_db', 'rssi_dbm'];

/**
 * Tecnología de acceso radio tal como aparece en los datos ('LTE', 'WCDMA', 'GSM'…). No hay una
 * lista fija: la interfaz ofrece las que devuelve `GET /disponibilidad`.
 *
 * @typedef {string} Tecnologia
 */

/** @typedef {'intra_frecuencia'|'inter_frecuencia'|'inter_rat'|'desconocido'} TipoEvento */

export const ETIQUETAS_TIPO_EVENTO = {
  intra_frecuencia: 'Intra-frecuencia',
  inter_frecuencia: 'Inter-frecuencia',
  inter_rat: 'Inter-RAT',
  desconocido: 'Sin clasificar',
};

/** Versión corta para la lista visual de eventos, donde el ancho es escaso. */
export const ETIQUETAS_TIPO_EVENTO_CORTAS = {
  intra_frecuencia: 'Intra',
  inter_frecuencia: 'Inter-frec.',
  inter_rat: 'Inter-RAT',
  desconocido: 'Sin clasif.',
};

// ================================================================================================
// Contratos de la API
// ================================================================================================

/**
 * @typedef {Object} Sesion
 * @property {string}   sesion_id
 * @property {string?}  sesion_nombre
 * @property {string?}  inicio          ISO-8601 con zona
 * @property {string?}  fin
 * @property {number}   n_mediciones
 * @property {number}   n_celdas
 * @property {string[]} tecnologias
 * @property {number}   n_handovers
 */

/**
 * @typedef {Object} Celda
 * @property {string}  clave    Identidad canónica: 'LTE:<ECI>' o '<tech>:<lac_tac>:<cid>'
 * @property {number?} cid
 * @property {number?} node_id
 * @property {number?} psc_pci
 * @property {number?} arfcn
 * @property {string?} tech
 */

/**
 * @typedef {Object} Handover
 * @property {string}     id_evento
 * @property {string}     sesion_id
 * @property {string}     timestamp_evento
 * @property {Celda}      celda_origen
 * @property {Celda}      celda_destino
 * @property {TipoEvento} tipo_evento
 * @property {boolean}    ping_pong   lo calcula el backend; la interfaz no lo muestra
 * @property {string?}    tipo_tecnologia
 * @property {'alta'|'baja'} confianza
 * @property {string?}    data_state_evento
 * @property {number?}    delta_rsrp_db
 * @property {number?}    delta_rsrq_db
 * @property {number?}    delta_rssnr_db
 * @property {number?}    delta_rscp_db
 * @property {number?}    delta_rssi_db
 * @property {number}     duracion_permanencia_s
 */

/**
 * @typedef {Object} PaginaHandovers
 * @property {number}     total
 * @property {number}     page
 * @property {number}     page_size
 * @property {Handover[]} items
 */

/**
 * Cobertura real de un parámetro. Es lo que permite escribir "sin datos válidos" en lugar de
 * pintar una gráfica vacía sin explicación.
 *
 * @typedef {Object} CoberturaParametro
 * @property {ParametroRF} parametro
 * @property {string}      etiqueta
 * @property {number}      n_validos
 * @property {number}      n_mediciones
 * @property {number}      pct_validos
 * @property {boolean}     disponible
 */

/**
 * Series en formato columnar. Un `null` en `t` marca un **corte** de la línea por hueco de
 * captura; un `null` dentro de una serie es "sin medida válida en ese instante".
 *
 * @typedef {Object} Series
 * @property {(string|null)[]}                    t
 * @property {Record<ParametroRF,(number|null)[]>} series
 * @property {boolean}                            downsampled
 * @property {number}                             puntos_originales
 * @property {number}                             puntos_devueltos
 * @property {CoberturaParametro[]}               cobertura
 */

/**
 * @typedef {Object} TramoCelda
 * @property {string}  inicio
 * @property {string}  fin
 * @property {string}  celda_clave
 * @property {string}  etiqueta
 * @property {string?} sesion_id
 * @property {string?} sesion_nombre
 * @property {number?} cid
 * @property {number?} node_id
 * @property {number?} psc_pci
 * @property {string?} tech
 * @property {number}  n_mediciones
 * @property {number}  duracion_s
 * @property {number}  valor_normalizado
 */

/**
 * @typedef {Object} TramosCelda
 * @property {'celda_clave'|'psc_pci'} eje
 * @property {TramoCelda[]}            tramos
 * @property {number}                  celdas_distintas
 */

/**
 * @typedef {Object} EstadisticasParametro
 * @property {number?} media_pre
 * @property {number?} media_post
 * @property {number?} delta
 * @property {number}  n_pre
 * @property {number}  n_post
 * @property {boolean} disponible
 */

/**
 * @typedef {Object} VentanaHandover
 * @property {Handover}                              evento
 * @property {string}                                t_evento
 * @property {number}                                segundos_antes
 * @property {number}                                segundos_despues
 * @property {string[]}                              t
 * @property {number[]}                              t_relativo_s
 * @property {('pre'|'evento'|'post')[]}             fase
 * @property {Record<ParametroRF,(number|null)[]>}   series
 * @property {Record<ParametroRF,EstadisticasParametro>} estadisticas
 */

/**
 * @typedef {Object} Resumen
 * @property {number}  total_handovers
 * @property {number}  radiobases_involucradas
 * @property {number}  sesiones_analizadas
 * @property {number}  n_mediciones
 * @property {string?} ventana_inicio
 * @property {string?} ventana_fin
 * @property {number?} duracion_s
 * @property {Record<string,number>} por_tipo
 * @property {Record<string,number>} por_tecnologia
 * @property {number}  total_ping_pong
 * @property {number}  total_confianza_baja
 * @property {number?} tasa_ho_por_minuto
 * @property {CoberturaParametro[]} cobertura_parametros
 */

/**
 * @typedef {Object} CeldaRepetida
 * @property {string}  celda_clave
 * @property {string}  etiqueta     «PCI n», «PSC n», «GSM CID n», «Sin PCI» o «Sin PSC»
 * @property {number?} arfcn        canal de la primera celda
 * @property {string[]} celdas_incluidas  celdas que suman en la barra (varias si comparten PCI)
 * @property {number[]} canales          canales de esas celdas
 * @property {number?} cid
 * @property {number?} node_id
 * @property {number?} psc_pci
 * @property {string?} tech
 * @property {number}  n_visitas
 * @property {number}  n_mediciones
 * @property {number}  tiempo_total_s
 */

/**
 * Un intervalo del histograma. Con varias sesiones, cada una tiene los suyos; el total no es de
 * ninguna (`sesion_id` nulo).
 *
 * @typedef {Object} BinIntervalo
 * @property {string?} inicio
 * @property {string?} fin
 * @property {string?} sesion_id
 * @property {string?} sesion_nombre
 * @property {CeldaRepetida[]} celdas
 */

/**
 * @typedef {Object} CeldasRepetidas
 * @property {'total'|'hora'|'10min'|'5min'} intervalo
 * @property {number?} minutos      duración de cada intervalo; null en el total
 * @property {number}  minutos_max  lo que dura la sesión más larga: el tope del deslizador
 * @property {number}  top
 * @property {BinIntervalo[]} bins
 * @property {number}  total_celdas
 */

/**
 * @typedef {Object} FranjaHoraria
 * @property {string} inicio  primer minuto con mediciones, 'HH:MM:SS' en hora local
 * @property {string} fin     último minuto con mediciones, incluido
 */

/**
 * Un día con datos de las sesiones elegidas, en la hora local del usuario.
 *
 * @typedef {Object} DiaDisponible
 * @property {string} fecha         'AAAA-MM-DD'
 * @property {number} n_mediciones
 * @property {number} n_handovers
 * @property {FranjaHoraria[]} franjas
 */

/**
 * Lo que se puede elegir en los filtros (`GET /disponibilidad`).
 *
 * @typedef {Object} Disponibilidad
 * @property {string} zona_horaria
 * @property {DiaDisponible[]} dias
 * @property {string[]} tecnologias
 */

/**
 * @typedef {Object} ResumenDeteccion
 * @property {string}  sesion_id
 * @property {string?} sesion_nombre
 * @property {number}  total_handovers
 * @property {Record<string,number>} por_tipo
 * @property {Record<string,number>} por_tecnologia
 * @property {number}  total_ping_pong
 * @property {number}  total_confianza_baja
 * @property {number}  radiobases_involucradas
 * @property {CoberturaParametro[]} cobertura_parametros
 * @property {number}  duracion_ms
 */

/**
 * Bloque de filtros común. Es, además, la **query key** de TanStack Query: cuando cambia, las
 * consultas se relanzan solas. Ahí se materializa el criterio 1 de HU-C2-006 sin código extra.
 *
 * @typedef {Object} FiltrosTemporales
 * @property {string[]}     sesionIds    una o varias sesiones analizadas juntas
 * @property {string?}      desde        ISO-8601
 * @property {string?}      hasta
 * @property {string?}      horaInicio   'HH:MM', en la hora local del usuario
 * @property {string?}      horaFin
 * @property {Tecnologia[]} tecnologias
 */
