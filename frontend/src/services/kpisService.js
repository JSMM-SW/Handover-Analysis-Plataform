const URL_BASE = "http://localhost:8000/api/v1/kpis";

/**
 * Arma el query string a partir de un objeto, omitiendo valores vacíos
 * (undefined, null, cadena vacía, o arrays vacíos) -- así los filtros
 * opcionales no se mandan cuando el usuario no seleccionó nada. Si un
 * valor es un array (tecnologia, franja, sesionLabel -- filtros
 * multi-selección), repite la clave una vez por elemento
 * (?tecnologia=1&tecnologia=2), que es como FastAPI espera listas en
 * query params.
 */
function construirQueryParams(parametros) {
    const query = new URLSearchParams();
    for (const [clave, valor] of Object.entries(parametros)) {
        if (valor === undefined || valor === null || valor === '') continue;
        if (Array.isArray(valor)) {
            valor.forEach((elemento) => query.append(clave, elemento));
        } else {
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

export const fetchKpiSummary = async (startDate, endDate, tecnologias, franjas, sesionLabels) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia: tecnologias, franja: franjas, sesion_label: sesionLabels });
    return obtenerJSON(`${URL_BASE}/summary?${query}`, "Error al cargar el resumen de KPIs");
};

export const fetchHourlyDistribution = async (startDate, endDate, tecnologias, franjas, sesionLabels) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia: tecnologias, franja: franjas, sesion_label: sesionLabels });
    return obtenerJSON(`${URL_BASE}/hourly?${query}`, "Error al cargar la distribución por horas");
};

export const fetchTrend = async (startDate, endDate, periodo = 'diario', tecnologias, franjas, sesionLabels) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, periodo, tecnologia: tecnologias, franja: franjas, sesion_label: sesionLabels });
    return obtenerJSON(`${URL_BASE}/trend?${query}`, "Error al cargar la tendencia");
};

export const fetchFranjaHoraria = async (startDate, endDate, tecnologias, sesionLabels) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia: tecnologias, sesion_label: sesionLabels });
    return obtenerJSON(`${URL_BASE}/franja-horaria?${query}`, "Error al cargar la distribución por franja horaria");
};

export const fetchDistribucionDiaSemana = async (startDate, endDate, tecnologias, franjas, sesionLabels) => {
    const query = construirQueryParams({ start_date: startDate, end_date: endDate, tecnologia: tecnologias, franja: franjas, sesion_label: sesionLabels });
    return obtenerJSON(`${URL_BASE}/dia-semana?${query}`, "Error al cargar la distribución por día de la semana");
};

export const fetchSesiones = async () => {
    return obtenerJSON(`${URL_BASE}/sesiones`, "Error al cargar la lista de sesiones");
};
