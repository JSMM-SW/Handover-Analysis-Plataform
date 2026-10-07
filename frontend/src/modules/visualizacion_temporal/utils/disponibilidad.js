/**
 * Qué se puede elegir en los filtros según los datos que hay (funciones puras).
 *
 * El backend (`GET /disponibilidad`) dice qué días tienen mediciones, en qué franjas horarias y
 * cuántos handovers hay en cada uno, todo en la hora local del usuario. A partir de ahí se calcula
 * qué días se pueden marcar en el calendario y qué horas se ofrecen en la franja horaria: el
 * usuario solo puede elegir lo que existe, en lugar de ir probando fecha por fecha.
 *
 * Las fechas viajan como texto 'AAAA-MM-DD' y las horas como 'HH:MM'. Se comparan como texto (el
 * formato lo permite) y nunca se pasan por `new Date('AAAA-MM-DD')`, que las leería en UTC y las
 * movería un día en Ecuador.
 */

const MINUTOS_DIA = 24 * 60;

const pad = (n) => String(n).padStart(2, '0');

/** 'HH:MM' o 'HH:MM:SS' → minutos desde la medianoche. */
export function aMinutos(hora) {
  const [h, m] = hora.split(':').map(Number);
  return h * 60 + m;
}

/** Minutos desde la medianoche → 'HH:MM'. */
export function aHora(minutos) {
  return `${pad(Math.floor(minutos / 60))}:${pad(minutos % 60)}`;
}

/**
 * Días dentro de [desde, hasta], extremos incluidos y opcionales.
 *
 * @param {import('../types/index.js').DiaDisponible[]} dias
 * @param {string|null} [desde]  'AAAA-MM-DD'
 * @param {string|null} [hasta]  'AAAA-MM-DD'
 */
export function diasEnRango(dias = [], desde = null, hasta = null) {
  return dias.filter((d) => (!desde || d.fecha >= desde) && (!hasta || d.fecha <= hasta));
}

/**
 * Une las franjas horarias de varios días en tramos de minutos sin solapes.
 *
 * Si el lunes hay datos de 16:00 a 17:00 y el martes de 16:30 a 18:00, la franja horaria (que se
 * aplica a cada día) tiene datos de 16:00 a 18:00.
 *
 * @returns {Array<[number, number]>} pares [primer minuto, último minuto], ambos incluidos
 */
export function unirFranjas(dias = []) {
  const tramos = dias
    .flatMap((dia) => dia.franjas.map((f) => [aMinutos(f.inicio), aMinutos(f.fin)]))
    .sort((a, b) => a[0] - b[0]);

  const unidos = [];
  for (const [inicio, fin] of tramos) {
    const ultimo = unidos[unidos.length - 1];
    if (ultimo && inicio <= ultimo[1] + 1) ultimo[1] = Math.max(ultimo[1], fin);
    else unidos.push([inicio, fin]);
  }
  return unidos;
}

/**
 * Cada cuántos minutos se ofrece una hora: de minuto en minuto si hay pocos con datos, y más
 * espaciado si hay muchos, para que la lista no se haga interminable.
 */
export function pasoDeMinutos(totalMinutos) {
  if (totalMinutos <= 180) return 1;
  if (totalMinutos <= 900) return 5;
  return 15;
}

/** Opción de «hasta». El final del día no existe como hora: se usa el último segundo. */
function opcionFin(minutos) {
  return minutos >= MINUTOS_DIA
    ? { valor: '23:59:59', etiqueta: '23:59' }
    : { valor: aHora(minutos), etiqueta: aHora(minutos) };
}

/**
 * Horas que se ofrecen en la franja horaria para los días elegidos.
 *
 * - **Desde:** el inicio de cada paso que tiene datos (el primero, redondeado hacia abajo).
 * - **Hasta:** el final de cada paso con datos. Así la última opción cubre el último minuto entero:
 *   la consulta compara `hora ≤ hasta`, y unas mediciones a las 16:45:43 solo entran con un
 *   «hasta» de 16:46 o posterior.
 *
 * Las horas de una pausa larga entre dos franjas no se ofrecen.
 *
 * @param {import('../types/index.js').DiaDisponible[]} dias
 * @param {string|null} [desde]  primer día elegido, 'AAAA-MM-DD'
 * @param {string|null} [hasta]  último día elegido, 'AAAA-MM-DD'
 * @returns {{paso: number, inicios: {valor: string, etiqueta: string}[],
 *   fines: {valor: string, etiqueta: string}[]}}
 */
export function opcionesDeHora(dias = [], desde = null, hasta = null) {
  const tramos = unirFranjas(diasEnRango(dias, desde, hasta));
  const total = tramos.reduce((suma, [a, b]) => suma + b - a + 1, 0);
  const paso = pasoDeMinutos(total);

  const inicios = new Set();
  const fines = new Set();
  for (const [a, b] of tramos) {
    for (let m = Math.floor(a / paso) * paso; m <= b; m += paso) inicios.add(m);
    const ultimoFin = Math.ceil((b + 1) / paso) * paso;
    for (let m = Math.ceil((a + 1) / paso) * paso; m <= ultimoFin; m += paso) {
      fines.add(Math.min(m, MINUTOS_DIA));
    }
  }

  const ordenar = (conjunto) => [...conjunto].sort((x, y) => x - y);
  return {
    paso,
    inicios: ordenar(inicios).map((m) => ({ valor: aHora(m), etiqueta: aHora(m) })),
    fines: ordenar(fines).map(opcionFin),
  };
}

// ================================================================================================
// Calendario
// ================================================================================================

/** Cabecera del calendario: la semana empieza en lunes, como en los calendarios de Ecuador. */
export const DIAS_SEMANA = ['lu', 'ma', 'mi', 'ju', 'vi', 'sá', 'do'];

/** 'AAAA-MM-DD' → 'AAAA-MM'. */
export function mesDe(fecha) {
  return fecha.slice(0, 7);
}

/** Meses con algún día disponible, en orden: el calendario salta de uno a otro. */
export function mesesConDatos(dias = []) {
  return [...new Set(dias.map((d) => mesDe(d.fecha)))].sort();
}

/** Nombre del mes para la cabecera del calendario: 'septiembre de 2026'. */
export function nombreMes(mes) {
  const [anio, numero] = mes.split('-').map(Number);
  return new Date(anio, numero - 1, 1).toLocaleDateString('es-EC', {
    month: 'long',
    year: 'numeric',
  });
}

/** Texto completo de un día para el lector de pantalla y el tooltip. */
function describirDia(fecha, dia) {
  const [anio, mes, numero] = fecha.split('-').map(Number);
  const texto = new Date(anio, mes - 1, numero).toLocaleDateString('es-EC', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  if (!dia) return `${texto}, sin datos`;

  const mediciones = `${dia.n_mediciones.toLocaleString('es-EC')} mediciones`;
  return dia.n_handovers > 0
    ? `${texto}, ${dia.n_handovers} handovers, ${mediciones}`
    : `${texto}, sin handovers detectados, ${mediciones}`;
}

/**
 * Semanas de un mes para pintar el calendario.
 *
 * Cada semana tiene siete celdas; las que caen fuera del mes son `null`. Una celda solo es
 * `disponible` si ese día tiene mediciones (y, si se pasan, está dentro de `min`/`max`).
 *
 * @param {string} mes  'AAAA-MM'
 * @param {Map<string, import('../types/index.js').DiaDisponible>} disponibles  días elegibles por fecha
 * @param {string|null} [seleccionada]  'AAAA-MM-DD'
 */
export function construirMes(mes, disponibles, seleccionada = null) {
  const [anio, numero] = mes.split('-').map(Number);
  const diasDelMes = new Date(anio, numero, 0).getDate();
  // getDay(): 0 = domingo. Con la semana en lunes, el domingo va al final.
  const huecoInicial = (new Date(anio, numero - 1, 1).getDay() + 6) % 7;

  const celdas = Array.from({ length: huecoInicial }, () => null);
  for (let dia = 1; dia <= diasDelMes; dia += 1) {
    const fecha = `${mes}-${pad(dia)}`;
    const datos = disponibles.get(fecha) ?? null;
    celdas.push({
      fecha,
      dia,
      disponible: Boolean(datos),
      conHandovers: (datos?.n_handovers ?? 0) > 0,
      seleccionada: fecha === seleccionada,
      descripcion: describirDia(fecha, datos),
    });
  }
  while (celdas.length % 7) celdas.push(null);

  const semanas = [];
  for (let i = 0; i < celdas.length; i += 7) semanas.push(celdas.slice(i, i + 7));
  return semanas;
}
