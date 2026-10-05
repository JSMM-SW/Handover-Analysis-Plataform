/**
 * Glosario contextual del Módulo 2.
 *
 * Definiciones en lenguaje llano para un docente que no es especialista en radiofrecuencia. Es la
 * **única fuente** de estos textos: las ayudas «?» junto a cada dato y el panel «Glosario» leen de
 * aquí, así que una explicación no puede decir una cosa en la tarjeta y otra en el panel.
 *
 * Cada entrada tiene:
 * - `titulo`: el nombre que ve el usuario.
 * - `breve`:  una o dos frases para el tooltip.
 * - `detalle`: ampliación opcional para el panel de glosario (cómo leer el valor).
 * - `grupo`:  sección del panel en la que aparece.
 *
 * El fundamento técnico de cada definición está en `docs/06-marco-teorico-ho.md` y
 * `docs/10-guia-de-interpretacion.md`.
 */

/** @typedef {'senal'|'eventos'|'celdas'|'lectura'} GrupoGlosario */

/**
 * @typedef {Object} EntradaGlosario
 * @property {string}        titulo
 * @property {string}        breve
 * @property {string}        [detalle]
 * @property {GrupoGlosario} grupo
 */

/** @type {Record<string, EntradaGlosario>} */
export const GLOSARIO = {
  handover: {
    titulo: 'Handover (traspaso)',
    breve:
      'Momento en que el teléfono deja de usar una antena y pasa a otra, sin cortar la conexión. Ocurre al desplazarse.',
    detalle:
      'Es como pasar el testigo en una carrera de relevos: la red decide que otra antena atenderá mejor al teléfono y le traspasa la conexión.',
    grupo: 'eventos',
  },
  rsrp_dbm: {
    titulo: 'RSRP — potencia de la señal',
    breve:
      'Cuánta señal llega de la antena. Se mide en dBm y siempre es negativa: cuanto más cerca de cero, mejor.',
    detalle:
      'Orientativo: por encima de −80 dBm es excelente, entre −80 y −100 es buena y por debajo de −110 la conexión empieza a sufrir.',
    grupo: 'senal',
  },
  rsrq_db: {
    titulo: 'RSRQ — calidad de la señal',
    breve:
      'Qué tan «limpia» llega la señal, teniendo en cuenta el ruido y otras antenas. En dB: cuanto más cerca de cero, mejor.',
    detalle:
      'Una señal puede ser fuerte (buen RSRP) pero de mala calidad (RSRQ bajo) si hay muchas antenas interfiriendo. Por encima de −10 dB es buena; por debajo de −15 dB, pobre.',
    grupo: 'senal',
  },
  rssnr_db: {
    titulo: 'RSSNR — señal frente a ruido',
    breve:
      'Cuántas veces más fuerte es la señal útil que el ruido. Valores altos son mejores.',
    detalle:
      'Se conserva RSSNR cuando la aplicación lo entrega; los valores no disponibles aparecen como «sin datos».',
    grupo: 'senal',
  },
  rscp_dbm: {
    titulo: 'RSCP — potencia en 3G',
    breve: 'El equivalente del RSRP para redes 3G (WCDMA). Cuanto más cerca de cero, mejor.',
    grupo: 'senal',
  },
  rssi_dbm: {
    titulo: 'RSSI — potencia total recibida',
    breve:
      'Toda la energía de radio que capta el teléfono, incluida la de otras antenas y el ruido. Se conserva el campo RSSI del CSV en todas las tecnologías.',
    grupo: 'senal',
  },
  tecnologia: {
    titulo: 'Tecnología (LTE, WCDMA, GSM)',
    breve: 'La generación de red móvil: LTE es 4G, WCDMA es 3G y GSM es 2G.',
    grupo: 'celdas',
  },
  radiobase: {
    titulo: 'Radiobase (celda)',
    breve:
      'Cada una de las antenas que dan servicio al teléfono. Un mismo mástil suele tener varias celdas orientadas en distintas direcciones.',
    grupo: 'celdas',
  },
  eci_pci: {
    titulo: 'ECI y PCI',
    breve:
      'Dos formas de nombrar una celda. El ECI es su «DNI»: único en toda la red. El PCI es un número corto que se repite entre zonas.',
    detalle:
      'Por eso el ECI es la vista por defecto: con el PCI, dos celdas distintas con el mismo número parecerían la misma.',
    grupo: 'celdas',
  },
  tramo: {
    titulo: 'Tramo',
    breve:
      'Periodo continuo en el que el teléfono estuvo conectado a la misma celda. Si hay más tramos que celdas, el teléfono volvió a alguna.',
    grupo: 'celdas',
  },
  tipo_evento: {
    titulo: 'Tipo de handover',
    breve:
      'Intra-frecuencia: cambia de antena en la misma frecuencia (lo más común). Inter-frecuencia: cambia también de frecuencia. Inter-RAT: cambia de tecnología, por ejemplo de 4G a 3G.',
    grupo: 'eventos',
  },
  ping_pong: {
    titulo: 'Ping-pong',
    breve:
      'El teléfono va a una antena y vuelve enseguida a la anterior (A → B → A). Suele indicar una zona donde la red está mal ajustada.',
    grupo: 'eventos',
  },
  confianza: {
    titulo: 'Confianza baja',
    breve:
      'Faltaba algún dato para identificar la celda con total seguridad. El traspaso existe, pero su identificación es menos fiable.',
    grupo: 'eventos',
  },
  tasa_ho: {
    titulo: 'Handovers por minuto',
    breve:
      'Traspasos divididos entre la duración del recorrido. Permite comparar recorridos de distinta duración.',
    grupo: 'lectura',
  },
  delta: {
    titulo: 'Δ (delta)',
    breve:
      'Cuánto cambió un valor al hacer el traspaso. Positivo (verde): la señal mejoró. Negativo (rojo): empeoró. Una raya «—» significa que no se pudo medir, que no es lo mismo que cero.',
    grupo: 'lectura',
  },
  pre_post: {
    titulo: 'PRE y POST',
    breve:
      'PRE son los segundos anteriores al traspaso y POST los posteriores. Compararlos muestra si el cambio de antena mejoró la conexión.',
    grupo: 'lectura',
  },
  muestras: {
    titulo: 'Muestras',
    breve:
      'Cuántas mediciones válidas entraron en cada media. Con pocas muestras, la comparación es menos fiable.',
    grupo: 'lectura',
  },
  visitas: {
    titulo: 'Visitas a una celda',
    breve:
      'Cuántas veces volvió el teléfono a esa celda. Muchas visitas señalan zonas donde varias antenas se solapan.',
    grupo: 'celdas',
  },
};

/** Orden y títulos de las secciones del panel de glosario. */
export const GRUPOS_GLOSARIO = [
  { id: 'eventos', titulo: 'Traspasos' },
  { id: 'senal', titulo: 'Parámetros de señal' },
  { id: 'celdas', titulo: 'Antenas y celdas' },
  { id: 'lectura', titulo: 'Cómo leer los números' },
];

/** Entradas de un grupo, en el orden en que están declaradas. */
export function entradasDeGrupo(grupo) {
  return Object.entries(GLOSARIO)
    .filter(([, entrada]) => entrada.grupo === grupo)
    .map(([clave, entrada]) => ({ clave, ...entrada }));
}
