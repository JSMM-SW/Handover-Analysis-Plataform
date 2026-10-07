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
function usarColorDeTema(nombreVariable) {
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
 * Al cambiar `data-tema`, el MutationObserver de `usarColorDeTema` agenda
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

const ETIQUETAS_FRANJA = { manana: 'Mañana', tarde: 'Tarde', noche: 'Noche' };
const ETIQUETAS_TECNOLOGIA = { '0': 'Sin señal', '1': 'LTE / 4G', '2': '3G / UMTS', '3': '2G' };
const ETIQUETAS_PERIODO = { diario: 'Diario', semanal: 'Semanal', mensual: 'Mensual', anual: 'Anual' };

const OPCIONES_TECNOLOGIA = [
    { value: '1', label: 'LTE / 4G' },
    { value: '2', label: '3G / UMTS' },
    { value: '3', label: '2G' },
    { value: '0', label: 'Sin señal' },
];

const OPCIONES_FRANJA = [
    { value: 'manana', label: 'Mañana (06-12)' },
    { value: 'tarde', label: 'Tarde (12-19)' },
    { value: 'noche', label: 'Noche (19-06)' },
];

export default function KpisDashboard() {
    const [startDate, setStartDate] = useState('2026-05-01');
    const [endDate, setEndDate] = useState('2026-05-24');
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
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const dashboardRef = useRef(null);

    const colorExitoso = usarColorDeTema('--color-exito');
    const colorFallido = usarColorDeTema('--color-error');
    const colorIndeterminado = usarColorDeTema('--color-texto-tenue');
    const colorPingPong = usarColorDeTema('--color-advertencia');
    const colorBorde = usarColorDeTema('--color-borde');
    const colorTextoTenue = usarColorDeTema('--color-texto-tenue');
    const colorSuperficie = usarColorDeTema('--color-superficie');
    const colorTexto = usarColorDeTema('--color-texto');

    const loadData = async () => {
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

    useEffect(() => {
        // loadData() llama a setLoading/setError de forma sincrona antes del
        // primer await, que es el patron estandar de fetching de datos (ver
        // "You Might Not Need an Effect" / "Fetching data" en la doc de React).
        // Una solucion mas "correcta" seria migrar a @tanstack/react-query (ya
        // disponible en el proyecto gracias al merge con develop), pero es un
        // cambio mas grande que no corresponde hacer solo para pasar el lint.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        loadData();
    }, [startDate, endDate, tecnologias, periodo, franjas, sesionLabels]);

    useEffect(() => {
        fetchSesiones().then(setSesiones).catch(() => setSesiones([]));
    }, []);

    /**
     * Genera el PDF del dashboard, siempre con la apariencia del modo oscuro.
     *
     * Fuerza temporalmente `data-tema="oscuro"` en <html> para que tanto el
     * CSS como los colores de Recharts (vía `usarColorDeTema`) se rendericen
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

    const pieData = summaryData ? [
        { name: 'Exitoso', value: summaryData.exitosos, color: colorExitoso },
        { name: 'Fallido', value: summaryData.fallidos, color: colorFallido },
        { name: 'Indeterminado', value: summaryData.indeterminados, color: colorIndeterminado },
    ] : [];

    const opcionesSesion = sesiones.map((sesion) => ({
        value: String(sesion.sesion_label),
        label: `${sessionName(sesion)} (${sesion.records_valid} registros)`,
    }));

    const resumenSeleccion = (seleccion, etiquetas, allLabel = 'Todas') => {
        if (seleccion.length === 0) return allLabel;
        return seleccion.map((valor) => etiquetas[valor] ?? valor).join(', ');
    };

    return (
        <div className="kpis-shell" ref={dashboardRef}>
            <header className="kpis-header">
                <div className="kpis-title-group">
                    <h2 className="kpis-title">KPIs y Reportes de Handover</h2>
                    <p className="kpis-subtitle">Monitoreo y análisis del desempeño del proceso de handover en redes móviles</p>
                </div>
                <div className="kpis-controls">
                    <div className="kpis-date-filter">
                        <span className="kpis-date-label">Ventana Temporal</span>
                        <VentanaTemporalSelector
                            periodo={periodo}
                            startDate={startDate}
                            endDate={endDate}
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
                    <MultiSelectDropdown
                        label="Sesión"
                        options={opcionesSesion}
                        selected={sesionLabels}
                        onChange={setSesionLabels}
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
                    <span>Sesión: {sesionLabels.length === 0 ? 'Todas' : sesionLabels.map((s) => `#${s}`).join(', ')}</span>
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
                    <div className="kpis-grid">
                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Total Handovers</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large">{summaryData.total_handovers}</span>
                            </div>
                            <p className="kpis-stat-sub">de {summaryData.total_mediciones} mediciones</p>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Tasa de Handover</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large highlight-green">{summaryData.tasa_handover}%</span>
                            </div>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Riesgos de Movilidad</h3>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Ping-Pong (HOPP)</span>
                                <span className="kpis-stat-value highlight-orange">{summaryData.tasa_hopp}%</span>
                            </div>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Handover Innecesarios</span>
                                <span className="kpis-stat-value highlight-red">{summaryData.tasa_innecesarios}%</span>
                            </div>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Handover Exitosos</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large" style={{ color: colorExitoso }}>{summaryData.tasa_exito}%</span>
                            </div>
                            <p className="kpis-stat-sub">{summaryData.exitosos} handovers exitosos</p>
                        </div>
                    </div>

                    <div className="kpis-row-layout">
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Evolución de KPIs ({periodo})</h3>
                            <div style={{ height: '280px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={trendData}>
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
                                    <span style={{ fontSize: '20px', fontWeight: 'bold', color: colorTexto, display: 'block' }}>{summaryData.total_handovers}</span>
                                    <span style={{ fontSize: '11px', color: colorTextoTenue, textTransform: 'uppercase' }}>Total</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="kpis-row-layout" style={{ marginTop: '24px' }}>
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Distribución de Handovers por Hora del Día</h3>
                            <div style={{ height: '300px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={hourlyData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="hora_etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
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
                            <div style={{ height: '300px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={franjaData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                        <XAxis dataKey="franja_etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
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
                                        <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
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
