import { useState, useEffect, useRef } from 'react';
import { sessionName } from '../../shared/sessionNames';
import {
    fetchKpiSummary,
    fetchHourlyDistribution,
    fetchFranjaHoraria,
    fetchDistribucionDiaSemana,
    fetchTrend,
    fetchSesiones,
} from '../../services/kpisService';
import MultiSelectDropdown from './MultiSelectDropdown';
import VentanaTemporalSelector from './VentanaTemporalSelector';
import ResumenPanel from './ResumenPanel';
import TablaPeriodos from './TablaPeriodos';
import { formatearTasa } from '../../shared/formatearTasa';
import { construirResumenDesdePeriodo } from '../../shared/resumenPeriodo';




import {
    ComposedChart, LineChart, PieChart, Bar, Line, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import './KpisDashboard.css';

/**
 * Lee el valor actual de una variable CSS del tema (ej. "--color-exito")
 * y lo mantiene sincronizado cuando el usuario alterna claro/oscuro.
 *
 * El nombre empieza con "use" (en inglés) a propósito: React exige ese
 * prefijo en toda función que llame a useState/useEffect para reconocerla
 * como hook (regla react-hooks/rules-of-hooks del lint).
 *
 * Los gráficos de Recharts se dibujan como SVG y reciben sus colores por
 * atributos (fill/stroke), no por CSS -- los navegadores no resuelven
 * `var(--token)` de forma confiable ahí (se ve todo en negro), y
 * html2canvas tampoco sabe interpretar `var(...)` al exportar el PDF.
 * Por eso se resuelve el valor real (ej. "#34d399") en JavaScript con
 * `getComputedStyle`, en vez de pasar el string `var(--token)` directo.
 *
 * El MutationObserver detecta cuando cambia `data-tema` en <html> (ya sea
 * por `alternarTema` en App.jsx o por `exportToPDF`, que fuerza el tema
 * oscuro durante la captura) para recalcular el color.
 *
 * @param {string} nombreVariable - nombre de la variable CSS, con "--".
 * @returns {string} el color ya resuelto (ej. "#34d399").
 */
function useColorDeTema(nombreVariable) {
    const [color, setColor] = useState('#000000');

    useEffect(() => {
        const raiz = document.documentElement;
        const leerColor = () => {
            const valor = getComputedStyle(raiz).getPropertyValue(nombreVariable).trim();
            if (valor) setColor(valor);
        };
        leerColor();

        const observador = new MutationObserver(leerColor);
        observador.observe(raiz, { attributes: true, attributeFilter: ['data-tema'] });
        return () => observador.disconnect();
    }, [nombreVariable]);

    return color;
}

/**
 * Espera a que el navegador pinte dos frames seguidos.
 *
 * Al cambiar `data-tema`, el MutationObserver de `useColorDeTema` agenda
 * un re-render de React; el primer frame deja que React aplique los nuevos
 * colores al DOM y el segundo garantiza que el navegador ya los pintó
 * antes de que html2canvas capture.
 *
 * @returns {Promise<void>} se resuelve después del segundo frame.
 */
function esperarRepintado() {
    return new Promise((resolver) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolver()));
    });
}

/**
 * Contenido de tooltip para los gráficos de distribución (hora/franja/día

 * de la semana): además de las series que ya dibuja Recharts (exitosos,
 * fallidos, indeterminados, ping-pongs), agrega la línea "Mediciones
 * registradas", que no es una serie graficada sino contexto de volumen de
 * datos (Paso 9 del plan de refactor).
 *
 * Recibe los colores de superficie/borde/texto por parámetro (en vez de
 * leerlos con el hook useColorDeTema) porque es una función común usada por
 * los 3 gráficos, no un componente propio.
 *
 * @param {object} props - props estándar de un `content` de Recharts (`active`, `payload`, `label`).
 * @param {string} colorSuperficie - color de fondo del tooltip, ya resuelto.
 * @param {string} colorBorde - color del borde del tooltip, ya resuelto.
 * @param {string} colorTexto - color del texto del tooltip, ya resuelto.
 * @returns {JSX.Element | null} el tooltip, o null si no hay nada que mostrar.
 */
function renderTooltipConMediciones({ active, payload, label }, colorSuperficie, colorBorde, colorTexto) {
    if (!active || !payload || payload.length === 0) return null;

    const totalMediciones = payload[0].payload.total_mediciones;

    return (
        <div style={{
            backgroundColor: colorSuperficie,
            border: `1px solid ${colorBorde}`,
            borderRadius: '6px',
            padding: '8px 12px',
            color: colorTexto,
            fontSize: '13px',
        }}>
            <p style={{ margin: '0 0 4px', fontWeight: 600 }}>{label}</p>
            {payload.map((entry) => (
                <p key={entry.dataKey} style={{ margin: 0, color: entry.color }}>
                    {entry.name}: {entry.value}
                </p>
            ))}
            <p style={{ margin: '4px 0 0', paddingTop: '4px', borderTop: `1px solid ${colorBorde}` }}>
                Mediciones registradas: {totalMediciones}
            </p>
        </div>
    );
}

const ETIQUETAS_FRANJA = { manana: 'Mañana', tarde: 'Tarde', noche: 'Noche' };


const ETIQUETAS_TECNOLOGIA = { '0': 'Sin señal', '1': 'LTE / 4G', '2': '3G / UMTS', '3': '2G' };
const ETIQUETAS_PERIODO = { diario: 'Diario', semanal: 'Semanal', mensual: 'Mensual', anual: 'Anual' };

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



    const dashboardRef = useRef(null);

    const colorExitoso = useColorDeTema('--color-exito');
    const colorFallido = useColorDeTema('--color-error');
    const colorIndeterminado = useColorDeTema('--color-texto-tenue');
    const colorPingPong = useColorDeTema('--color-advertencia');
    const colorBorde = useColorDeTema('--color-borde');
    const colorTextoTenue = useColorDeTema('--color-texto-tenue');
        const colorSuperficie = useColorDeTema('--color-superficie');
    const colorTexto = useColorDeTema('--color-texto');
    const colorPrimario = useColorDeTema('--color-primario');


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
     * Genera el PDF del dashboard, siempre con la apariencia del modo oscuro.

     *
     * Fuerza temporalmente `data-tema="oscuro"` en <html> para que tanto el
     * CSS como los colores de Recharts (vía `useColorDeTema`) se rendericen
     * en oscuro, captura con html2canvas y luego restaura el tema que tenía
     * el usuario. Se modifica el atributo directamente (no el estado de
     * App.jsx) para no persistir el cambio en localStorage.
     *
     * @returns {Promise<void>}
     */
    const exportToPDF = async () => {
        const element = dashboardRef.current;
        if (!element) return;

        const raiz = document.documentElement;
        const temaAnterior = raiz.dataset.tema;
        const controles = element.querySelector('.kpis-controls');
        const resumenFiltros = element.querySelector('.kpis-filtros-resumen-pdf');

        // html2canvas no puede capturar bien controles nativos del navegador
        // (select/input date, sobre todo con color-scheme: dark) -- los
        // reemplazamos por texto plano solo durante la captura.
        controles.style.display = 'none';
        resumenFiltros.style.display = 'flex';
        raiz.dataset.tema = 'oscuro';

        try {
            await esperarRepintado();

            // Se lee aquí (y no del hook) porque el valor del hook es el del
            // render anterior al cambio de tema.
            const fondoOscuro = getComputedStyle(raiz).getPropertyValue('--color-fondo').trim();

            const canvas = await html2canvas(element, {
                backgroundColor: fondoOscuro,
                scale: 2,
            });

            const imgData = canvas.toDataURL('image/png');

            const pdf = new jsPDF('p', 'mm', 'a4');
            const pdfWidth = pdf.internal.pageSize.getWidth();
            const pdfHeight = (canvas.height * pdfWidth) / canvas.width;

            pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
            pdf.save(`Reporte_Handovers_${startDate}_al_${endDate}.pdf`);
        } finally {
            raiz.dataset.tema = temaAnterior;
            controles.style.display = 'flex';
            resumenFiltros.style.display = 'none';
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
        ? `Todas (${sesiones.length} sesiones)`
        : sesiones
            .filter((sesion) => sesionLabels.includes(String(sesion.sesion_label)))
            .map((sesion) => sessionName(sesion))
            .join(', ');
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

        const pieData = resumenMostrado ? [
        { name: 'Exitoso', value: resumenMostrado.exitosos, color: colorExitoso },
        { name: 'Fallido', value: resumenMostrado.fallidos, color: colorFallido },
        { name: 'Indeterminado', value: resumenMostrado.indeterminados, color: colorIndeterminado },
    ] : [];

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
     * Alterna la selección de un periodo al hacer clic sobre un punto del
     * gráfico "Evolución de KPIs": un clic en un punto nuevo lo selecciona,
     * un clic sobre el mismo punto ya seleccionado lo deselecciona.
     *
     * @param {object} eventoRecharts - evento de clic que entrega Recharts,
     * con `activePayload` (el/los punto(s) bajo el cursor).
     */
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
                    <MultiSelectDropdown
                        label="Sesión"
                        options={opcionesSesion}
                        selected={sesionLabels}
                        onChange={setSesionLabels}
                    />
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
                            <option value="semanal">Semanal</option>
                            <option value="mensual">Mensual</option>
                            <option value="anual">Anual</option>
                        </select>
                    </div>
                    <div className="kpis-controls-action">
                        <button className="kpis-btn-export" onClick={exportToPDF} disabled={!hasData || loading}>
                            Exportar PDF
                        </button>
                    </div>
                </div>

                {/* Solo visible durante la captura para el PDF (ver exportToPDF):
                    reemplaza a .kpis-controls, que html2canvas no captura bien
                    por tener <select>/<input type="date"> nativos. */}
                <div className="kpis-filtros-resumen-pdf" style={{ display: 'none' }}>
                    <span>Periodo: {startDate} a {endDate}</span>
                    <span>Tecnología: {resumenSeleccion(tecnologias, ETIQUETAS_TECNOLOGIA)}</span>
                    <span>Franja horaria: {resumenSeleccion(franjas, ETIQUETAS_FRANJA)}</span>
                    <span>Periodicidad: {ETIQUETAS_PERIODO[periodo]}</span>
                    <span>Sesión: {sesionesTexto}</span>

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
                <>
                                        <ResumenPanel
                        sesionesTexto={sesionesTexto}
                        periodoTexto={periodoTexto}
                        tecnologiaTexto={resumenSeleccion(tecnologias, ETIQUETAS_TECNOLOGIA)}
                        resumen={resumenMostrado}
                    />

                    <div className="kpis-grid">
                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Total Handovers</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large">{resumenMostrado.total_handovers}</span>
                            </div>
                            <p className="kpis-stat-sub">de {resumenMostrado.total_mediciones} mediciones</p>
                        </div>

                                                <div className="kpis-card">
                            <h3 className="kpis-card-title">Tasa de Handover</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large highlight-green">{formatearTasa(resumenMostrado.tasa_handover)}</span>
                            </div>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Riesgos de Movilidad</h3>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Ping-Pong (HOPP)</span>
                                <span className="kpis-stat-value highlight-orange">{formatearTasa(resumenMostrado.tasa_hopp)}</span>
                            </div>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Handover Innecesarios</span>
                                <span className="kpis-stat-value highlight-red">{formatearTasa(resumenMostrado.tasa_innecesarios)}</span>
                            </div>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Handover Post Degradados (PHD)</span>
                                <span className="kpis-stat-value highlight-red">{formatearTasa(resumenMostrado.tasa_phd)}</span>
                            </div>
                        </div>


                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Handover Exitosos</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large" style={{ color: colorExitoso }}>{formatearTasa(resumenMostrado.tasa_exito)}</span>
                            </div>
                            <p className="kpis-stat-sub">{resumenMostrado.exitosos} handovers exitosos</p>
                        </div>

                    </div>


                                                            <div className="kpis-row-layout">
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <div className="kpis-card-header-row">
                                <h3 className="kpis-card-title">Evolución de KPIs ({periodo})</h3>
                                {puntoSeleccionado && (
                                    <button type="button" className="kpis-btn-reset-periodo" onClick={limpiarSeleccionPeriodo}>
                                        Ver todo el periodo
                                    </button>
                                )}
                            </div>
                            {puntoSeleccionado && (
                                <p className="kpis-periodo-seleccionado-hint">
                                    Mostrando el periodo <strong>{puntoSeleccionado.etiqueta}</strong>
                                </p>
                            )}
                            <div className="kpis-chart-clickeable" style={{ height: '280px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={trendData} onClick={seleccionarPeriodo}>

                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Line type="monotone" dataKey="exitosos" stroke={colorExitoso} strokeWidth={3} name="Exitosos" dot={{ r: 4 }} />
                                        <Line type="monotone" dataKey="fallidos" stroke={colorFallido} strokeWidth={3} name="Fallidos" dot={{ r: 4 }} />
                                        <Line type="monotone" dataKey="indeterminados" stroke={colorIndeterminado} strokeWidth={2} name="Indeterminados" dot={{ r: 3 }} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>


                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Distribución por Tipo de Evento</h3>
                            <div style={{ height: '280px', width: '100%', marginTop: '10px', position: 'relative' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie data={pieData} innerRadius={70} outerRadius={95} paddingAngle={4} dataKey="value">
                                            {pieData.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={entry.color} />
                                            ))}
                                        </Pie>
                                        <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
                                        <Legend verticalAlign="bottom" height={36} iconType="circle" />
                                    </PieChart>
                                </ResponsiveContainer>
                                <div style={{ position: 'absolute', top: '42%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none' }}>
                                    <span style={{ fontSize: '20px', fontWeight: 'bold', color: colorTexto, display: 'block' }}>{resumenMostrado.total_handovers}</span>
                                    <span style={{ fontSize: '11px', color: colorTextoTenue, textTransform: 'uppercase' }}>Total</span>
                                </div>

                            </div>
                        </div>
                    </div>

                    <div className="kpis-row-layout" style={{ marginTop: '24px', gridTemplateColumns: '1fr' }}>
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Mediciones Registradas ({periodo})</h3>
                            <div style={{ height: '220px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={trendData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
                                        <Bar dataKey="total_mediciones" fill={colorPrimario} name="Mediciones" radius={[4, 4, 0, 0]} />

                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>

                    <div className="kpis-row-layout" style={{ marginTop: '24px', gridTemplateColumns: '1fr' }}>
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Tabla de Periodos ({periodo})</h3>
                            <TablaPeriodos datos={trendData} />
                        </div>
                    </div>

                    <div className="kpis-row-layout" style={{ marginTop: '24px' }}>
                        <div className="kpis-card" style={{ margin: 0 }}>
                                                        <h3 className="kpis-card-title">Distribución de Handovers por Hora del Día</h3>
                            {puntoSeleccionado && (
                                <p className="kpis-periodo-seleccionado-hint">
                                    {loadingPeriodo ? 'Cargando datos del periodo...' : (
                                        <>Mostrando solo <strong>{puntoSeleccionado.etiqueta}</strong></>
                                    )}
                                </p>
                            )}
                            <div style={{ height: '300px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                                                        <ComposedChart data={hourlyMostrado}>

                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="hora_etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip content={(props) => renderTooltipConMediciones(props, colorSuperficie, colorBorde, colorTexto)} />

                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Bar dataKey="exitosos" stackId="eventos" fill={colorExitoso} name="Exitosos" />
                                        <Bar dataKey="fallidos" stackId="eventos" fill={colorFallido} name="Fallidos" />
                                        <Bar dataKey="indeterminados" stackId="eventos" fill={colorIndeterminado} name="Indeterminados" radius={[4, 4, 0, 0]} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="kpis-card" style={{ margin: 0 }}>
                                                        <h3 className="kpis-card-title">Distribución por Franja Horaria</h3>
                            {puntoSeleccionado && (
                                <p className="kpis-periodo-seleccionado-hint">
                                    {loadingPeriodo ? 'Cargando datos del periodo...' : (
                                        <>Mostrando solo <strong>{puntoSeleccionado.etiqueta}</strong></>
                                    )}
                                </p>
                            )}
                            <div style={{ height: '300px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                                                        <ComposedChart data={franjaMostrado}>

                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="franja_etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip content={(props) => renderTooltipConMediciones(props, colorSuperficie, colorBorde, colorTexto)} />

                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Bar dataKey="exitosos" stackId="eventos" fill={colorExitoso} name="Exitosos" />
                                        <Bar dataKey="fallidos" stackId="eventos" fill={colorFallido} name="Fallidos" />
                                        <Bar dataKey="indeterminados" stackId="eventos" fill={colorIndeterminado} name="Indeterminados" radius={[4, 4, 0, 0]} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>
                    <div className="kpis-row-layout" style={{ marginTop: '24px', gridTemplateColumns: '1fr' }}>
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Distribución por Día de la Semana</h3>
                            <div style={{ height: '300px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                                                        <ComposedChart data={diaSemanaData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip content={(props) => renderTooltipConMediciones(props, colorSuperficie, colorBorde, colorTexto)} />

                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Bar dataKey="exitosos" stackId="eventos" fill={colorExitoso} name="Exitosos" />
                                        <Bar dataKey="fallidos" stackId="eventos" fill={colorFallido} name="Fallidos" />
                                        <Bar dataKey="indeterminados" stackId="eventos" fill={colorIndeterminado} name="Indeterminados" radius={[4, 4, 0, 0]} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
