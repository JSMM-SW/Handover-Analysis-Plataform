import { useState, useEffect, useRef } from 'react';
import { sessionName } from '../../shared/sessionNames';
import {
    fetchKpiSummary,
    fetchHourlyDistribution,
    fetchFranjaHoraria,
    fetchDistribucionDiaSemana,
    fetchTrend,
    fetchSesiones,
    guardarReporteHistorial,
} from '../../services/kpisService';

import MultiSelectDropdown from './MultiSelectDropdown';
import VentanaTemporalSelector from './VentanaTemporalSelector';
import HistorialReportesModal from './HistorialReportesModal';
import ReporteImprimible from './ReporteImprimible';
import { construirResumenDesdePeriodo } from '../../shared/resumenPeriodo';
import { ETIQUETAS_FRANJA, ETIQUETAS_TECNOLOGIA, ETIQUETAS_PERIODO } from './etiquetas';

import './KpisDashboard.css';
import { generarPdfDesdeElemento } from './pdfHelpers';

const OPCIONES_TECNOLOGIA = [
    { value: '1', label: 'LTE / 4G' },
    { value: '2', label: '3G / UMTS' },
    { value: '3', label: '2G' },
];

const OPCIONES_FRANJA = [
    { value: 'manana', label: 'Mañana (06-12)' },
    { value: 'tarde', label: 'Tarde (12-19)' },
    { value: 'noche', label: 'Noche (19-06)' },
];

export default function KpisDashboard() {
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');

    const [tecnologias, setTecnologias] = useState([]);
    const [periodo, setPeriodo] = useState('diario');
    const [franjas, setFranjas] = useState([]);
    const [sesionLabels, setSesionLabels] = useState([]);
    const [sesiones, setSesiones] = useState([]);

    const [summaryData, setSummaryData] = useState(null);
    const [hourlyData, setHourlyData] = useState([]);
    const [franjaData, setFranjaData] = useState([]);
    const [diaSemanaData, setDiaSemanaData] = useState([]);

    const [trendData, setTrendData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [periodoSeleccionado, setPeriodoSeleccionado] = useState(null);
    const [hourlyDataPeriodo, setHourlyDataPeriodo] = useState(null);
    const [franjaDataPeriodo, setFranjaDataPeriodo] = useState(null);
    const [loadingPeriodo, setLoadingPeriodo] = useState(false);
    const [mostrarHistorial, setMostrarHistorial] = useState(false);

    const dashboardRef = useRef(null);

    useEffect(() => {
        /**
         * Consulta en paralelo todos los KPIs del dashboard con los filtros
         * actuales y guarda los resultados en el estado.
         *
         * Vive dentro del efecto (y no en el cuerpo del componente) para que
         * no sea una dependencia más del useEffect: así el efecto solo se
         * vuelve a ejecutar cuando cambian los filtros.
         *
         * @returns {Promise<void>}
         */
        const cargarDatos = async () => {
            setLoading(true);
            setError(null);
            try {
                const [summary, hourly, franjaResultado, diaSemana, trend] = await Promise.all([
                    fetchKpiSummary(startDate, endDate, tecnologias, franjas, sesionLabels),
                    fetchHourlyDistribution(startDate, endDate, tecnologias, franjas, sesionLabels),
                    fetchFranjaHoraria(startDate, endDate, tecnologias, sesionLabels),
                    fetchDistribucionDiaSemana(startDate, endDate, tecnologias, franjas, sesionLabels),
                    fetchTrend(startDate, endDate, periodo, tecnologias, franjas, sesionLabels),
                ]);

                const horaConEtiqueta = hourly.map(item => ({
                    ...item,
                    hora_etiqueta: `${String(item.hora).padStart(2, '0')}:00`,
                }));
                const franjaConEtiqueta = franjaResultado.map(item => ({
                    ...item,
                    franja_etiqueta: ETIQUETAS_FRANJA[item.franja] ?? item.franja,
                }));

                setSummaryData(summary);
                setHourlyData(horaConEtiqueta);
                setFranjaData(franjaConEtiqueta);
                setDiaSemanaData(diaSemana);
                setTrendData(trend);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        if (startDate && endDate) {
            cargarDatos();
        }
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setPeriodoSeleccionado(null);
    }, [startDate, endDate, tecnologias, periodo, franjas, sesionLabels]);

    useEffect(() => {
        fetchSesiones().then(setSesiones).catch(() => setSesiones([]));
    }, []);

    useEffect(() => {
        /**
         * Vuelve a consultar la distribución por hora y por franja horaria,
         * pero acotada a las fechas del periodo seleccionado en "Evolución
         * de KPIs" (en vez de todo el rango de fechas global) -- así esos
         * dos gráficos también reflejan el periodo elegido, no solo las
         * tarjetas y el panel de resumen.
         *
         * Es un efecto aparte (no se suma al de cargarDatos()) porque se
         * dispara por una interacción distinta (clic en un punto del
         * gráfico, no un cambio de filtro) y no debe bloquear el resto del
         * dashboard con su propio estado de carga.
         */
        if (!periodoSeleccionado) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setHourlyDataPeriodo(null);
            setFranjaDataPeriodo(null);
            return;
        }

        const punto = trendData.find((item) => item.periodo === periodoSeleccionado);
        if (!punto) return;

        let cancelado = false;
        setLoadingPeriodo(true);

        Promise.all([
            fetchHourlyDistribution(punto.fecha_inicio, punto.fecha_fin, tecnologias, franjas, sesionLabels),
            fetchFranjaHoraria(punto.fecha_inicio, punto.fecha_fin, tecnologias, sesionLabels),
        ])
            .then(([hourly, franjaResultado]) => {
                if (cancelado) return;
                setHourlyDataPeriodo(hourly.map((item) => ({
                    ...item,
                    hora_etiqueta: `${String(item.hora).padStart(2, '0')}:00`,
                })));
                setFranjaDataPeriodo(franjaResultado.map((item) => ({
                    ...item,
                    franja_etiqueta: ETIQUETAS_FRANJA[item.franja] ?? item.franja,
                })));
            })
            .catch(() => {
                if (!cancelado) {
                    setHourlyDataPeriodo(null);
                    setFranjaDataPeriodo(null);
                }
            })
            .finally(() => {
                if (!cancelado) setLoadingPeriodo(false);
            });

        return () => {
            cancelado = true;
        };
    }, [periodoSeleccionado, trendData, tecnologias, franjas, sesionLabels]);

    useEffect(() => {
        /**
         * Ajusta la ventana temporal a la primera y última medición de las
         * sesiones elegidas (o de todas, si no hay ninguna seleccionada) --
         * Paso 7 del plan de refactor. No depende de startDate/endDate, así
         * que no pisa lo que el usuario edite manualmente después: solo se
         * recalcula cuando cambia la selección de sesión o llega la lista
         * de sesiones por primera vez.
         */
        if (sesiones.length === 0) return;

        const relevantes = sesionLabels.length > 0
            ? sesiones.filter((sesion) => sesionLabels.includes(String(sesion.sesion_label)))
            : sesiones;
        const conFechas = relevantes.filter((sesion) => sesion.primera_medicion && sesion.ultima_medicion);
        if (conFechas.length === 0) return;

        const inicio = conFechas.reduce(
            (minimo, sesion) => (sesion.primera_medicion < minimo ? sesion.primera_medicion : minimo),
            conFechas[0].primera_medicion,
        );
        const fin = conFechas.reduce(
            (maximo, sesion) => (sesion.ultima_medicion > maximo ? sesion.ultima_medicion : maximo),
            conFechas[0].ultima_medicion,
        );

        // Mismo patrón que cargarDatos() más arriba: es estado derivado de
        // una fuente externa (las sesiones ya cargadas), no un efecto
        // secundario evitable.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setStartDate(inicio.slice(0, 10));
        setEndDate(fin.slice(0, 10));
    }, [sesionLabels, sesiones]);

    /**
     * Genera el PDF del dashboard con la apariencia del tema que el usuario
     * tiene activo en ese momento (claro u oscuro) -- a diferencia de antes
     * (Paso 11 del plan de refactor), ya no fuerza el tema oscuro durante la
     * captura.
     *
     * Si el dashboard no cabe en una sola página A4, se reparte en varias:
     * se captura una sola imagen larga con html2canvas y se va pegando esa
     * misma imagen en cada página con un corrimiento vertical negativo, para
     * que cada una muestre la porción que le corresponde (jsPDF recorta
     * automáticamente lo que sobra fuera de los límites de la página).
     *
     * @returns {Promise<void>}
     */
    const exportToPDF = async () => {
        const element = dashboardRef.current;
        if (!element) return;

        const controles = element.querySelector('.kpis-controls');
        const resumenFiltros = element.querySelector('.kpis-filtros-resumen-pdf');

        // html2canvas no puede capturar bien controles nativos del navegador
        // (select/input date, sobre todo con color-scheme: dark) -- los
        // reemplazamos por texto plano solo durante la captura.
        controles.style.display = 'none';
        resumenFiltros.style.display = 'flex';
        // La tabla de periodos tiene demasiadas columnas para caber en el
        // ancho de la tarjeta a su tamaño normal (queda cortada a la
        // derecha en el PDF) -- esta clase fuerza table-layout: fixed con
        // fuente/padding reducidos solo durante la captura, para que las
        // columnas se repartan dentro del ancho disponible en vez de
        // desbordarse.
        element.classList.add('kpis-pdf-compacto');

        try {
            const nombreArchivo = `Reporte_Handovers_${startDate}_al_${endDate}.pdf`;
            await generarPdfDesdeElemento(element, nombreArchivo);

            // Guarda una entrada en el historial.
            // No se espera ni bloquea la descarga del PDF por esto -- si falla
            // (ej. sin conexión al backend en ese instante), el usuario ya
            // tiene su PDF de todas formas.
            guardarReporteHistorial({
                nombre_archivo: nombreArchivo,
                fecha_inicio: startDate,
                fecha_fin: endDate,
                tecnologia: tecnologias.map(Number),
                franja: franjas,
                sesion_label: sesionLabels.map(Number),
                periodicidad: periodo,
                periodo_seleccionado: periodoSeleccionado,
                // hora_dia/franja_horaria/dia_semana se agregan para que el
                // historial pueda regenerar el PDF completo (con las 3
                // gráficas de distribución) más adelante -- antes de esto
                // solo se guardaba resumen+tendencia, insuficiente para
                // reconstruir esas 3 gráficas.
                resultados: {
                    resumen: resumenMostrado,
                    tendencia: trendData,
                    hora_dia: hourlyMostrado,
                    franja_horaria: franjaMostrado,
                    dia_semana: diaSemanaData,
                },
            }).catch(() => {});
        } finally {
            controles.style.display = 'flex';
            resumenFiltros.style.display = 'none';
            element.classList.remove('kpis-pdf-compacto');
        }
    };

    const hasData = summaryData && summaryData.total_handovers > 0;

    const opcionesSesion = sesiones.map((sesion) => ({
        value: String(sesion.sesion_label),
        label: `${sessionName(sesion)} (${sesion.records_valid} registros)`,
    }));

    const resumenSeleccion = (seleccion, etiquetas, allLabel = 'Todas') => {
        if (seleccion.length === 0) return allLabel;
        return seleccion.map((valor) => etiquetas[valor] ?? valor).join(', ');
    };

    /**
     * Años que cubren las mediciones de TODAS las sesiones (sin filtrar por
     * la selección actual, para que el selector siempre ofrezca el rango
     * completo disponible) -- reemplaza el "año actual y 9 anteriores" fijo
     * que usaba VentanaTemporalSelector antes (Paso 7 del plan de refactor).
     */
    const fechasConDatos = sesiones
        .flatMap((sesion) => [sesion.primera_medicion, sesion.ultima_medicion])
        .filter(Boolean);
    const anioActual = new Date().getFullYear();
    const aniosDisponibles = fechasConDatos.length > 0
        ? (() => {
            const anios = fechasConDatos.map((fecha) => Number(fecha.slice(0, 4)));
            const anioMin = Math.min(...anios);
            const anioMax = Math.max(...anios);
            return Array.from({ length: anioMax - anioMin + 1 }, (_, i) => anioMax - i);
        })()
        : [anioActual];

    /**
     * Textos del panel de resumen (ver ResumenPanel.jsx) -- "Sesión N" de
     * forma consistente con el selector y, más abajo, con el resumen del
     * PDF (Paso 8 del plan de refactor: antes el PDF mostraba "#label" en
     * vez del nombre).
     */
    const sesionesTexto = sesionLabels.length === 0
        ? `Todas (${sesiones.length} ${sesiones.length === 1 ? 'sesión' : 'sesiones'})`
        : sesiones
            .filter((sesion) => sesionLabels.includes(String(sesion.sesion_label)))
            .map((sesion) => sessionName(sesion))
            .join(', ');

    /**
     * Rango de fechas de la(s) sesión(es) elegidas en el selector de
     * Sesión, para mostrarlo junto al propio selector -- mismo patrón que
     * `SessionSelector.jsx` del módulo de geoespacial. Null si no hay
     * ninguna sesión seleccionada (equivalente a "todas") o si ninguna de
     * las elegidas tiene mediciones todavía.
     */
    const rangoFechasSesionTexto = (() => {
        if (sesionLabels.length === 0) return null;
        const relevantes = sesiones.filter((sesion) => sesionLabels.includes(String(sesion.sesion_label)));
        const conFechas = relevantes.filter((sesion) => sesion.primera_medicion && sesion.ultima_medicion);
        if (conFechas.length === 0) return null;
        const inicio = conFechas.reduce(
            (minimo, sesion) => (sesion.primera_medicion < minimo ? sesion.primera_medicion : minimo),
            conFechas[0].primera_medicion,
        );
        const fin = conFechas.reduce(
            (maximo, sesion) => (sesion.ultima_medicion > maximo ? sesion.ultima_medicion : maximo),
            conFechas[0].ultima_medicion,
        );
        return `Del ${inicio.slice(0, 10)} al ${fin.slice(0, 10)}`;
    })();

    /**
     * Punto de trendData que corresponde al periodo seleccionado con clic en
     * el gráfico "Evolución de KPIs" (Paso 10 del plan de refactor), o null
     * si no hay ninguno seleccionado.
     */
    const puntoSeleccionado = periodoSeleccionado
        ? trendData.find((punto) => punto.periodo === periodoSeleccionado)
        : null;

    /**
     * Resumen que alimenta las tarjetas, el donut y el panel: el del
     * periodo seleccionado si hay uno, o el del rango completo (summaryData)
     * si no. summaryData sigue siendo la fuente para `hasData` -- la
     * selección de un periodo nunca oculta ni muestra el dashboard, solo
     * cambia qué números se ven dentro de él.
     */
    const resumenMostrado = puntoSeleccionado
        ? construirResumenDesdePeriodo(puntoSeleccionado)
        : summaryData;

    // Datos para "Distribución de Handovers por Hora del Día" y
    // "Distribución por Franja Horaria": los del periodo seleccionado si ya
    // llegaron (hourlyDataPeriodo/franjaDataPeriodo), o los del rango
    // completo mientras tanto.
    const hourlyMostrado = (puntoSeleccionado && hourlyDataPeriodo) ? hourlyDataPeriodo : hourlyData;
    const franjaMostrado = (puntoSeleccionado && franjaDataPeriodo) ? franjaDataPeriodo : franjaData;

    const periodoTexto = puntoSeleccionado
        ? `${puntoSeleccionado.fecha_inicio} a ${puntoSeleccionado.fecha_fin} (periodo: ${puntoSeleccionado.etiqueta})`
        : `${startDate} a ${endDate}`;

    /**
     * Selecciona el periodo clickeado en el gráfico "Evolución de KPIs".
     * Siempre reemplaza la selección anterior (patrón de "filtro cruzado"
     * de los dashboards BI: Power BI, Tableau, Grafana) en vez de hacer
     * toggle comparando con el punto ya seleccionado -- así cada clic en
     * una fecha distinta cambia la selección de inmediato, sin casos
     * ambiguos. Para deseleccionar existe un botón explícito ("Ver todo el
     * periodo") en vez de depender de volver a clickear el mismo punto.
     *
     * @param {object} eventoRecharts - evento de clic de Recharts v3: trae
     * `activeTooltipIndex` (el índice del punto dentro de `trendData`),
     * entregado como STRING ("0", "1", ...), no como número.
     */
    const seleccionarPeriodo = (eventoRecharts) => {
        if (!eventoRecharts || eventoRecharts.activeTooltipIndex == null) return;
        const puntoClic = trendData[Number(eventoRecharts.activeTooltipIndex)];
        if (!puntoClic) return;
        setPeriodoSeleccionado(puntoClic.periodo);
    };

    /** Limpia la selección de periodo y vuelve a mostrar el rango completo. */
    const limpiarSeleccionPeriodo = () => setPeriodoSeleccionado(null);

    return (
        <div className="kpis-shell" ref={dashboardRef}>
            <header className="kpis-header">
                <div className="kpis-title-group">
                    <h2 className="kpis-title">KPIs y Reportes de Handover</h2>
                    <p className="kpis-subtitle">Monitoreo y análisis del desempeño del proceso de handover en redes móviles</p>
                </div>
                <div className="kpis-controls">
                    <div className="kpis-sesion-filter">
                        <MultiSelectDropdown
                            label="Sesión"
                            options={opcionesSesion}
                            selected={sesionLabels}
                            onChange={setSesionLabels}
                        />
                        {rangoFechasSesionTexto && (
                            <p className="kpis-sesion-rango-fechas">{rangoFechasSesionTexto}</p>
                        )}
                    </div>
                    <div className="kpis-date-filter">
                        <span className="kpis-date-label">Ventana Temporal</span>
                        <VentanaTemporalSelector
                            periodo={periodo}
                            startDate={startDate}
                            endDate={endDate}
                            aniosDisponibles={aniosDisponibles}
                            onChange={(nuevoInicio, nuevoFin) => {
                                setStartDate(nuevoInicio);
                                setEndDate(nuevoFin);
                            }}
                        />
                    </div>

                    <MultiSelectDropdown
                        label="Tecnología"
                        options={OPCIONES_TECNOLOGIA}
                        selected={tecnologias}
                        onChange={setTecnologias}
                    />
                    <MultiSelectDropdown
                        label="Franja Horaria"
                        options={OPCIONES_FRANJA}
                        selected={franjas}
                        onChange={setFranjas}
                    />
                    <div className="kpis-date-filter">
                        <span className="kpis-date-label">Periodicidad (tendencia)</span>
                        <select className="kpis-input" value={periodo} onChange={(e) => setPeriodo(e.target.value)}>
                            <option value="diario">Diario</option>
                            <option value="mensual">Mensual</option>
                            <option value="anual">Anual</option>
                        </select>
                    </div>
                    <div className="kpis-controls-action">
                        <button className="kpis-btn-historial" onClick={() => setMostrarHistorial(true)}>
                            Historial
                        </button>
                        <button className="kpis-btn-export" onClick={exportToPDF} disabled={!hasData || loading}>
                            Exportar PDF
                        </button>
                    </div>
                </div>

                {mostrarHistorial && (
                    <HistorialReportesModal onClose={() => setMostrarHistorial(false)} />
                )}

                {/* Solo visible durante la captura para el PDF (ver exportToPDF):
                    reemplaza a .kpis-controls, que html2canvas no captura bien
                    por tener <select>/<input type="date"> nativos. */}
                <div className="kpis-filtros-resumen-pdf" style={{ display: 'none' }}>
                    <span>Periodo: {startDate} a {endDate}</span>
                    <span>Tecnología: {resumenSeleccion(tecnologias, ETIQUETAS_TECNOLOGIA)}</span>
                    <span>Franja horaria: {resumenSeleccion(franjas, ETIQUETAS_FRANJA)}</span>
                    <span>Periodicidad: {ETIQUETAS_PERIODO[periodo]}</span>
                    <span>Sesión: {sesionesTexto}</span>
                    {puntoSeleccionado && (
                        <span>Periodo seleccionado: {puntoSeleccionado.etiqueta} ({puntoSeleccionado.fecha_inicio} a {puntoSeleccionado.fecha_fin})</span>
                    )}
                </div>
            </header>

            {loading && (
                <div className="kpis-loading-container">
                    <div className="kpis-spinner"></div>
                    <p>Consultando métricas en la base de datos...</p>
                </div>
            )}

            {error && <p className="highlight-red">Error de conexión: {error}</p>}

            {!loading && !error && !hasData && summaryData && (
                <div className="kpis-empty-state">
                    <h3>Sin registros de red</h3>
                    <p>No se detectaron eventos de Handover en el periodo seleccionado.</p>
                </div>
            )}

            {!loading && !error && hasData && (
                <ReporteImprimible
                    resumen={resumenMostrado}
                    tendencia={trendData}
                    horaDia={hourlyMostrado}
                    franjaHoraria={franjaMostrado}
                    diaSemana={diaSemanaData}
                    periodo={periodo}
                    sesionesTexto={sesionesTexto}
                    periodoTexto={periodoTexto}
                    tecnologiaTexto={resumenSeleccion(tecnologias, ETIQUETAS_TECNOLOGIA)}
                    puntoSeleccionado={puntoSeleccionado}
                    loadingPeriodo={loadingPeriodo}
                    onSeleccionarPeriodo={seleccionarPeriodo}
                    onLimpiarSeleccionPeriodo={limpiarSeleccionPeriodo}
                />
            )}
        </div>
    );
}
