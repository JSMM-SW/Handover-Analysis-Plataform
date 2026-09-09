const API_BASE = "http://localhost:8000/api/v1/kpis";

export const fetchKpiSummary = async (startDate, endDate) => {
    const response = await fetch(`${API_BASE}/summary?start_date=${startDate}&end_date=${endDate}`);
    if (!response.ok) throw new Error("Error al cargar el resumen de KPIs");
    return response.json();
};

export const fetchHourlyDistribution = async (startDate, endDate) => {
    const response = await fetch(`${API_BASE}/hourly?start_date=${startDate}&end_date=${endDate}`);
    if (!response.ok) throw new Error("Error al cargar la distribución por horas");
    return response.json();
};

export const fetchDailyTrend = async (startDate, endDate) => {
    const response = await fetch(`${API_BASE}/trend?start_date=${startDate}&end_date=${endDate}`);
    if (!response.ok) throw new Error("Error al cargar tendencia diaria");
    return response.json();
};