import { useEffect, useState } from 'react';
import { fetchHistorialReportes } from '../../services/kpisService';
import { ETIQUETAS_FRANJA, ETIQUETAS_TECNOLOGIA, ETIQUETAS_PERIODO } from './etiquetas';
import { formatearTasa } from '../../shared/formatearTasa';

/**
 * Arma el texto de una selección multi-valor para mostrarlo en una fila del
 * historial (ej. "LTE / 4G, 3G / UMTS"), igual que `resumenSeleccion` en
 * KpisDashboard.jsx pero como función suelta -- este componente no comparte
 * estado con el dashboard, así que no vale la pena importar esa versión.
 */
function textoSeleccion(valores, etiquetas) {
    if (!valores || valores.length === 0) return 'Todas';
    return valores.map((valor) => etiquetas[valor] ?? valor).join(', ');
}

/**
 * Arma las filas del resumen guardado (reporte.resultados.resumen) para
 * mostrarlas al expandir un reporte -- mismo formato que ResumenPanel.jsx,
 * pero a partir del snapshot guardado en vez de summaryData en vivo.
 * `celdas_distintas`/`cambios_celda_no_observados` pueden venir null si el
 * reporte se exportó con un periodo puntual seleccionado (Paso 10): esos
 * dos campos no se recalculan por periodo.
 */
function filasResultado(resumen) {
    if (!resumen) return [];
    return [
        { etiqueta: 'Total de mediciones', valor: resumen.total_mediciones },
        { etiqueta: 'Total de handovers', valor: resumen.total_handovers },
        { etiqueta: 'Tasa de handover', valor: formatearTasa(resumen.tasa_handover) },
        { etiqueta: 'Exitosos', valor: resumen.exitosos },
        { etiqueta: 'Fallidos', valor: resumen.fallidos },
        { etiqueta: 'Indeterminados', valor: resumen.indeterminados },
        { etiqueta: 'Tasa de éxito', valor: formatearTasa(resumen.tasa_exito) },
        { etiqueta: 'Tasa PHD', valor: formatearTasa(resumen.tasa_phd) },
        { etiqueta: 'Ping-Pong', valor: resumen.ping_pongs },
        { etiqueta: 'Tasa HOPP', valor: formatearTasa(resumen.tasa_hopp) },
        { etiqueta: 'Evaluables UHO', valor: resumen.uho_evaluables },
        { etiqueta: 'Tasa innecesarios', valor: formatearTasa(resumen.tasa_innecesarios) },
        { etiqueta: 'Celdas distintas', valor: resumen.celdas_distintas ?? 'No disponible' },
        { etiqueta: 'Cambios no observados', valor: resumen.cambios_celda_no_observados ?? 'No disponible' },
    ];
}

/**
 * Modal de solo lectura con el historial de reportes KPI exportados a PDF
 * (HU-010, Paso 13 del plan de refactor). Pide la lista recién al abrirse
 * (no en cada carga del dashboard), vía fetchHistorialReportes. Cada fila
 * se puede expandir con clic para ver el snapshot de resultados que se
 * guardó junto con los filtros -- no hace falta otra llamada al backend,
 * ya viene incluido en la respuesta.
 *
 * @param {() => void} onClose - cierra el modal (clic en el fondo o la X).
 */
export default function HistorialReportesModal({ onClose }) {
    const [historial, setHistorial] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(null);
    const [expandidoId, setExpandidoId] = useState(null);

    useEffect(() => {
        fetchHistorialReportes()
            .then(setHistorial)
            .catch((err) => setError(err.message))
            .finally(() => setCargando(false));
    }, []);

    const alternarExpandido = (id) => {
        setExpandidoId((actual) => (actual === id ? null : id));
    };

    return (
        <div className="kpis-modal-overlay" onClick={onClose}>
            <div className="kpis-modal-panel" onClick={(e) => e.stopPropagation()}>
                <div className="kpis-modal-header">
                    <h3 className="kpis-modal-titulo">Historial de reportes</h3>
                    <button className="kpis-modal-cerrar" onClick={onClose} aria-label="Cerrar">×</button>
                </div>

                {cargando && <p className="kpis-modal-estado">Cargando historial...</p>}
                {error && <p className="kpis-modal-estado highlight-red">Error al cargar el historial: {error}</p>}
                {!cargando && !error && historial.length === 0 && (
                    <p className="kpis-modal-estado">Todavía no se ha exportado ningún reporte.</p>
                )}

                {!cargando && !error && historial.length > 0 && (
                    <ul className="kpis-historial-lista">
                        {historial.map((reporte) => {
                            const expandido = expandidoId === reporte.id;
                            return (
                                <li className="kpis-historial-item" key={reporte.id}>
                                    <button
                                        type="button"
                                        className="kpis-historial-item-cabecera"
                                        onClick={() => alternarExpandido(reporte.id)}
                                        aria-expanded={expandido}
                                    >
                                        <span className="kpis-historial-archivo">{reporte.nombre_archivo}</span>
                                        <span className="kpis-historial-fecha">
                                            {new Date(reporte.fecha_generacion).toLocaleString()}
                                        </span>
                                    </button>
                                    <div className="kpis-historial-item-filtros">
                                        <span>Periodo: {reporte.fecha_inicio} a {reporte.fecha_fin}</span>
                                        <span>Tecnología: {textoSeleccion(reporte.tecnologia.map(String), ETIQUETAS_TECNOLOGIA)}</span>
                                        <span>Franja horaria: {textoSeleccion(reporte.franja, ETIQUETAS_FRANJA)}</span>
                                        <span>
                                            Sesiones: {reporte.sesion_label.length === 0
                                                ? 'Todas'
                                                : reporte.sesion_label.map((label) => `Sesión ${label}`).join(', ')}
                                        </span>
                                        <span>Periodicidad: {ETIQUETAS_PERIODO[reporte.periodicidad] ?? reporte.periodicidad}</span>
                                        {reporte.periodo_seleccionado && (
                                            <span>Periodo seleccionado: {reporte.periodo_seleccionado}</span>
                                        )}
                                    </div>

                                    {expandido && (
                                        <div className="kpis-historial-resultados">
                                            {filasResultado(reporte.resultados?.resumen).map((fila) => (
                                                <div className="kpis-historial-resultado-item" key={fila.etiqueta}>
                                                    <span className="kpis-historial-resultado-label">{fila.etiqueta}</span>
                                                    <span className="kpis-historial-resultado-valor">{fila.valor}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
        </div>
    );
}
