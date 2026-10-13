/**
 * Construye el objeto "resumen" (misma forma que /kpis/summary) a partir de
 * un punto de /kpis/trend, para cuando el usuario selecciona un periodo
 * puntual en el gráfico "Evolución de KPIs" (Paso 10 del plan de refactor).
 *
 * Un punto de trend no trae todos los campos de summary:
 * - `tasa_handover` se puede recalcular aquí con la misma fórmula que usa
 *   el backend (total_handovers / total_mediciones * 100, 2 decimales,
 *   null si no hay mediciones).
 * - `celdas_distintas` y `cambios_celda_no_observados` NO se pueden derivar
 *   de un punto de trend (son cálculos sobre la secuencia completa, no por
 *   periodo) -- se devuelven como `null` a propósito, para que la UI
 *   muestre "No disponible por periodo" en vez de un número incorrecto.
 *
 * @param {object} punto - un elemento de trendData (TrendResponse del backend).
 * @returns {object} un resumen con la misma forma que KpiSummaryResponse.
 */
export function construirResumenDesdePeriodo(punto) {
    const tasaHandover = punto.total_mediciones > 0
        ? Math.round((punto.total_handovers / punto.total_mediciones) * 100 * 100) / 100
        : null;

    return {
        fecha_inicio: punto.fecha_inicio,
        fecha_fin: punto.fecha_fin,
        total_mediciones: punto.total_mediciones,
        total_handovers: punto.total_handovers,
        tasa_handover: tasaHandover,
        exitosos: punto.exitosos,
        fallidos: punto.fallidos,
        indeterminados: punto.indeterminados,
        tasa_exito: punto.tasa_exito,
        tasa_phd: punto.tasa_phd,
        tasa_innecesarios: punto.tasa_innecesarios,
        uho_evaluables: punto.uho_evaluables,
        ping_pongs: punto.ping_pongs,
        tasa_hopp: punto.tasa_hopp,
        celdas_distintas: null,
        cambios_celda_no_observados: null,
    };
}
