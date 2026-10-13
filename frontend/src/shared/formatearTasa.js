/**
 * Formatea una tasa (%) para mostrarla en una tarjeta o tabla. El backend
 * devuelve `null` cuando el denominador de la tasa es 0 (Paso 6 del plan de
 * refactor de KPIs) -- "sin datos", no un 0% real -- así que no se puede
 * mostrar directamente `{valor}%` o saldría literalmente "null%".
 *
 * @param {number | null | undefined} valor - la tasa ya calculada por el backend.
 * @returns {string} "Sin datos" si `valor` es null/undefined, o "N%" si no.
 */
export function formatearTasa(valor) {
    return valor == null ? 'Sin datos' : `${valor}%`;
}
