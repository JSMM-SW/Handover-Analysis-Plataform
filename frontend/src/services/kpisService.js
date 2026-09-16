const URL_BASE = "http://localhost:8000/api/v1/kpis";

/**
 * Arma el query string a partir de un objeto, omitiendo valores vacíos
 * (undefined, null o cadena vacía) -- así los filtros opcionales
 * (tecnologia, periodo) no se mandan cuando el usuario elige "Todas".
 */
function construirQueryParams(parametros) {
    const query = new URLSearchParams();
    for (const [clave, valor] of Object.entries(parametros)) {
        if (valor !== undefined && valor !== null && valor !== '') {
            query.append(clave, valor);
        }
    }
    return query.toString();
}

async function obtenerJSON(url, mensajeError) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(mensajeError);
    return response.json();
}

export const fetchKpiSummary = async (startDate, endDate, tecnologia, franja) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia, franja });
    return obtenerJSON(`${URL_BASE}/summary?${query}`, "Error al cargar el resumen de KPIs");
};

export const fetchHourlyDistribution = async (startDate, endDate, tecnologia, franja) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia, franja });
    return obtenerJSON(`${URL_BASE}/hourly?${query}`, "Error al cargar la distribución por horas");
};

export const fetchTrend = async (startDate, endDate, periodo = 'diario', tecnologia, franja) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, periodo, tecnologia, franja });
    return obtenerJSON(`${URL_BASE}/trend?${query}`, "Error al cargar la tendencia");
};

export const fetchFranjaHoraria = async (startDate, endDate, tecnologia) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia });
    return obtenerJSON(`${URL_BASE}/franja-horaria?${query}`, "Error al cargar la distribución por franja horaria");
};


