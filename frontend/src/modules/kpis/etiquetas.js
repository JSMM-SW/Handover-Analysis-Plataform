/**
 * Etiquetas legibles compartidas del módulo de KPIs. Viven en un archivo
 * propio (no en KpisDashboard.jsx) para poder reusarlas en otros
 * componentes como HistorialReportesModal.jsx sin romper la regla de
 * react-refresh, que no permite exportar nada que no sea un componente
 * desde un archivo que sí exporta un componente por default.
 */
export const ETIQUETAS_FRANJA = { manana: 'Mañana', tarde: 'Tarde', noche: 'Noche' };

export const ETIQUETAS_TECNOLOGIA = { '0': 'Sin señal', '1': 'LTE / 4G', '2': '3G / UMTS', '3': '2G' };

export const ETIQUETAS_PERIODO = { diario: 'Diario', semanal: 'Semanal', mensual: 'Mensual', anual: 'Anual' };
