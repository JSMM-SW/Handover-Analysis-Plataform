import { useEffect, useRef, useState } from 'react';
import { fetchHistorialReportes } from '../../services/kpisService';
import { ETIQUETAS_FRANJA, ETIQUETAS_TECNOLOGIA, ETIQUETAS_PERIODO } from './etiquetas';
import { formatearTasa } from '../../shared/formatearTasa';
import ReporteImprimible from './ReporteImprimible';
import { generarPdfDesdeElemento } from './pdfHelpers';

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
 * Texto de sesión(es) de un reporte del historial, mismo formato que
 * `sesionesTexto` en KpisDashboard.jsx pero a partir de los campos
 * guardados en la fila (`sesion_label`), no del estado en vivo del
 * dashboard -- lo usan tanto el resumen de filtros de la fila como
 * ReporteImprimible al regenerar el PDF.
 */
function sesionesTextoDeReporte(reporte) {
    return reporte.sesion_label.length === 0
        ? 'Todas'
        : reporte.sesion_label.map((label) => `Sesión ${label}`).join(', ');
}

/**
 * Texto de periodo de un reporte del historial, mismo formato que
 * `periodoTexto` en KpisDashboard.jsx.
 */
function periodoTextoDeReporte(reporte) {
    if (reporte.periodo_seleccionado) {
        return `${reporte.fecha_inicio} a ${reporte.fecha_fin} (periodo: ${reporte.periodo_seleccionado})`;
    }
    return `${reporte.fecha_inicio} a ${reporte.fecha_fin}`;
}

/**
 * Modal de solo lectura con el historial de reportes KPI exportados a PDF
 * (HU-010, Paso 13 del plan de refactor). Pide la lista recién al abrirse
 * (no en cada carga del dashboard), vía fetchHistorialReportes. Cada fila
 * se puede expandir con clic para ver el snapshot de resultados que se
 * guardó junto con los filtros -- no hace falta otra llamada al backend,
 * ya viene incluido en la respuesta.
 *
 * También permite regenerar el PDF de un reporte antiguo: renderiza
 * ReporteImprimible oculto con los datos guardados de ese reporte
 * (`reporte.resultados`) y lo captura con el mismo pipeline que usa el
 * dashboard en vivo (`generarPdfDesdeElemento`). No crea una nueva entrada
 * de historial -- solo vuelve a generar el archivo de uno ya existente.
 * Reportes guardados antes de que `resultados` incluyera
 * hora_dia/franja_horaria/dia_semana regeneran el PDF igual, pero esos 3
 * gráficos de distribución quedan vacíos (no hay forma de recuperar datos
 * que nunca se guardaron).
 *
 * @param {() => void} onClose - cierra el modal (clic en el fondo o la X).
 */
export default function HistorialReportesModal({ onClose }) {
    const [historial, setHistorial] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState(null);
    const [expandidoId, setExpandidoId] = useState(null);
    const [reporteParaCapturar, setReporteParaCapturar] = useState(null);
    const [generandoId, setGenerandoId] = useState(null);
    const capturaRef = useRef(null);

    useEffect(() => {
        fetchHistorialReportes()
            .then(setHistorial)
            .catch((err) => setError(err.message))
            .finally(() => setCargando(false));
    }, []);

    useEffect(() => {
        /**
         * Regenera el PDF de `reporteParaCapturar` una vez que
         * ReporteImprimible terminó de montarse (oculto) con sus datos --
         * separado del clic que lo dispara porque el montaje y el
         * posterior repintado de los gráficos son asíncronos.
         */
        if (!reporteParaCapturar) return;
        let cancelado = false;

        (async () => {
            // Recharts mide el ancho real del contenedor con
            // ResizeObserver en su primer montaje -- este es un montaje
            // nuevo (oculto, recién creado), a diferencia del dashboard en
            // vivo donde los gráficos ya estaban montados antes de
            // exportar. Los 2 frames que ya espera
            // generarPdfDesdeElemento no bastan siempre para ese primer
            // layout; este margen adicional reduce el riesgo de capturar
            // los gráficos todavía vacíos.
            await new Promise((resolver) => setTimeout(resolver, 300));
            if (cancelado) return;

            try {
                await generarPdfDesdeElemento(capturaRef.current, reporteParaCapturar.nombre_archivo);
            } catch {
                // Si falla la captura, simplemente no se descarga nada --
                // no hay nada más que romper (a diferencia de exportToPDF,
                // esto no guarda otra entrada de historial).
            } finally {
                if (!cancelado) {
                    setGenerandoId(null);
                    setReporteParaCapturar(null);
                }
            }
        })();

        return () => {
            cancelado = true;
        };
    }, [reporteParaCapturar]);

    const alternarExpandido = (id) => {
        setExpandidoId((actual) => (actual === id ? null : id));
    };

    const generarPdfDeReporte = (reporte) => {
        setGenerandoId(reporte.id);
        setReporteParaCapturar(reporte);
    };

    return (
        <>
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
                                        <div className="kpis-historial-item-header-row">
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
                                            <button
                                                type="button"
                                                className="kpis-historial-btn-generar"
                                                onClick={() => generarPdfDeReporte(reporte)}
                                                disabled={generandoId === reporte.id}
                                            >
                                                {generandoId === reporte.id ? 'Generando...' : 'Generar PDF'}
                                            </button>
                                        </div>
                                        <div className="kpis-historial-item-filtros">
                                            <span>Periodo: {reporte.fecha_inicio} a {reporte.fecha_fin}</span>
                                            <span>Tecnología: {textoSeleccion(reporte.tecnologia.map(String), ETIQUETAS_TECNOLOGIA)}</span>
                                            <span>Franja horaria: {textoSeleccion(reporte.franja, ETIQUETAS_FRANJA)}</span>
                                            <span>Sesiones: {sesionesTextoDeReporte(reporte)}</span>
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

            {/* Oculto fuera de pantalla (no display:none -- html2canvas
                necesita que el elemento esté realmente dispuesto/pintado
                para capturarlo) -- se monta solo mientras se regenera un
                PDF del historial, con los datos de ese snapshot guardado. */}
            {reporteParaCapturar && (
                <div className="kpis-captura-oculta-contenedor">
                <div className="kpis-shell kpis-pdf-compacto kpis-captura-oculta-contenido" ref={capturaRef}>
                    <div className="kpis-filtros-resumen-pdf" style={{ display: 'flex' }}>
                        <span>Periodo: {reporteParaCapturar.fecha_inicio} a {reporteParaCapturar.fecha_fin}</span>
                        <span>Tecnología: {textoSeleccion(reporteParaCapturar.tecnologia.map(String), ETIQUETAS_TECNOLOGIA)}</span>
                        <span>Franja horaria: {textoSeleccion(reporteParaCapturar.franja, ETIQUETAS_FRANJA)}</span>
                        <span>Periodicidad: {ETIQUETAS_PERIODO[reporteParaCapturar.periodicidad] ?? reporteParaCapturar.periodicidad}</span>
                        <span>Sesión: {sesionesTextoDeReporte(reporteParaCapturar)}</span>
                        {reporteParaCapturar.periodo_seleccionado && (
                            <span>Periodo seleccionado: {reporteParaCapturar.periodo_seleccionado}</span>
                        )}
                    </div>
                    <ReporteImprimible
                        resumen={reporteParaCapturar.resultados?.resumen}
                        tendencia={reporteParaCapturar.resultados?.tendencia ?? []}
                        horaDia={reporteParaCapturar.resultados?.hora_dia ?? []}
                        franjaHoraria={reporteParaCapturar.resultados?.franja_horaria ?? []}
                        diaSemana={reporteParaCapturar.resultados?.dia_semana ?? []}
                        periodo={reporteParaCapturar.periodicidad}
                        sesionesTexto={sesionesTextoDeReporte(reporteParaCapturar)}
                        periodoTexto={periodoTextoDeReporte(reporteParaCapturar)}
                        tecnologiaTexto={textoSeleccion(reporteParaCapturar.tecnologia.map(String), ETIQUETAS_TECNOLOGIA)}
                        animado={false}
                    />
                </div>
                </div>
            )}
        </>
    );
}
