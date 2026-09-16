import { useState, useEffect, useRef } from 'react';
import {
    fetchKpiSummary,
    fetchHourlyDistribution,
    fetchFranjaHoraria,
    fetchTrend,
} from '../../services/kpisService';
import {
    ComposedChart, LineChart, PieChart, Bar, Line, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import './KpisDashboard.css';

const ETIQUETAS_FRANJA = { manana: 'Mañana', tarde: 'Tarde', noche: 'Noche' };
const ETIQUETAS_TECNOLOGIA = { '0': 'Sin señal', '1': 'LTE / 4G', '2': '3G / UMTS' };
const ETIQUETAS_PERIODO = { diario: 'Diario', semanal: 'Semanal', mensual: 'Mensual', anual: 'Anual' };
const COLOR_EXITOSO = '#34d399';
const COLOR_FALLIDO = '#f87171';
const COLOR_INDETERMINADO = '#9aa2b1';
const COLOR_PING_PONG = '#fbbf24';

export default function KpisDashboard() {
    const [startDate, setStartDate] = useState('2026-05-01');
    const [endDate, setEndDate] = useState('2026-05-24');
    const [tecnologia, setTecnologia] = useState('');
    const [periodo, setPeriodo] = useState('diario');
    const [franja, setFranja] = useState('');

    const [summaryData, setSummaryData] = useState(null);
    const [hourlyData, setHourlyData] = useState([]);
    const [franjaData, setFranjaData] = useState([]);
    const [trendData, setTrendData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const dashboardRef = useRef(null);

    const loadData = async () => {
        setLoading(true);
        setError(null);
        try {
            const [summary, hourly, franjaResultado, trend] = await Promise.all([
                fetchKpiSummary(startDate, endDate, tecnologia, franja),
                fetchHourlyDistribution(startDate, endDate, tecnologia, franja),
                fetchFranjaHoraria(startDate, endDate, tecnologia),
                fetchTrend(startDate, endDate, periodo, tecnologia, franja),
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
            setTrendData(trend);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, [startDate, endDate, tecnologia, periodo, franja]);

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

        const canvas = await html2canvas(element, { backgroundColor: '#0b0d12', scale: 2 });
        const imgData = canvas.toDataURL('image/png');

        const pdf = new jsPDF('p', 'mm', 'a4');
        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = (canvas.height * pdfWidth) / canvas.width;

        pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
        pdf.save(`Reporte_Handovers_${startDate}_al_${endDate}.pdf`);

        controles.style.display = 'flex';
        resumenFiltros.style.display = 'none';
    };

    const hasData = summaryData && summaryData.total_handovers > 0;

    const pieData = summaryData ? [
        { name: 'Exitoso', value: summaryData.exitosos, color: COLOR_EXITOSO },
        { name: 'Fallido', value: summaryData.fallidos, color: COLOR_FALLIDO },
        { name: 'Indeterminado', value: summaryData.indeterminados, color: COLOR_INDETERMINADO },
    ] : [];

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
                        <div className="kpis-date-inputs">
                            <input type="date" className="kpis-input" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                            <span style={{ color: '#9aa2b1', fontSize: '13px' }}>a</span>
                            <input type="date" className="kpis-input" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                        </div>
                    </div>
                    <div className="kpis-date-filter">
                        <span className="kpis-date-label">Tecnología</span>
                        <select className="kpis-input" value={tecnologia} onChange={(e) => setTecnologia(e.target.value)}>
                            <option value="">Todas</option>
                            <option value="1">LTE / 4G</option>
                            <option value="2">3G / UMTS</option>
                            <option value="0">Sin señal</option>
                        </select>
                    </div>
                    <div className="kpis-date-filter">
                        <span className="kpis-date-label">Franja Horaria</span>
                        <select className="kpis-input" value={franja} onChange={(e) => setFranja(e.target.value)}>
                            <option value="">Todas</option>
                            <option value="manana">Mañana (06-12)</option>
                            <option value="tarde">Tarde (12-19)</option>
                            <option value="noche">Noche (19-06)</option>
                        </select>
                    </div>
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
                    <span>Tecnología: {ETIQUETAS_TECNOLOGIA[tecnologia] ?? 'Todas'}</span>
                    <span>Franja horaria: {ETIQUETAS_FRANJA[franja] ?? 'Todas'}</span>
                    <span>Periodicidad: {ETIQUETAS_PERIODO[periodo]}</span>
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
                                <span className="kpis-stat-value large" style={{ color: COLOR_EXITOSO }}>{summaryData.tasa_exito}%</span>
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
                                        <CartesianGrid strokeDasharray="3 3" stroke="#262b36" vertical={false} />
                                        <XAxis dataKey="etiqueta" stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: '#14171f', borderColor: '#262b36', color: '#fff' }} />
                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Line type="monotone" dataKey="exitosos" stroke={COLOR_EXITOSO} strokeWidth={3} name="Exitosos" dot={{ r: 4 }} />
                                        <Line type="monotone" dataKey="fallidos" stroke={COLOR_FALLIDO} strokeWidth={3} name="Fallidos" dot={{ r: 4 }} />
                                        <Line type="monotone" dataKey="indeterminados" stroke={COLOR_INDETERMINADO} strokeWidth={2} name="Indeterminados" dot={{ r: 3 }} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={COLOR_PING_PONG} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
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
                                        <Tooltip contentStyle={{ backgroundColor: '#14171f', borderColor: '#262b36', color: '#fff' }} />
                                        <Legend verticalAlign="bottom" height={36} iconType="circle" />
                                    </PieChart>
                                </ResponsiveContainer>
                                <div style={{ position: 'absolute', top: '42%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none' }}>
                                    <span style={{ fontSize: '20px', fontWeight: 'bold', color: '#fff', display: 'block' }}>{summaryData.total_handovers}</span>
                                    <span style={{ fontSize: '11px', color: '#9aa2b1', textTransform: 'uppercase' }}>Total</span>
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
                                        <CartesianGrid strokeDasharray="3 3" stroke="#262b36" vertical={false} />
                                        <XAxis dataKey="hora_etiqueta" stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: '#14171f', borderColor: '#262b36', color: '#fff' }} />
                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Bar dataKey="exitosos" stackId="eventos" fill={COLOR_EXITOSO} name="Exitosos" />
                                        <Bar dataKey="fallidos" stackId="eventos" fill={COLOR_FALLIDO} name="Fallidos" />
                                        <Bar dataKey="indeterminados" stackId="eventos" fill={COLOR_INDETERMINADO} name="Indeterminados" radius={[4, 4, 0, 0]} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={COLOR_PING_PONG} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Distribución por Franja Horaria</h3>
                            <div style={{ height: '300px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <ComposedChart data={franjaData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#262b36" vertical={false} />
                                        <XAxis dataKey="franja_etiqueta" stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: '#14171f', borderColor: '#262b36', color: '#fff' }} />
                                        <Legend verticalAlign="top" height={50} iconType="circle" />
                                        <Bar dataKey="exitosos" stackId="eventos" fill={COLOR_EXITOSO} name="Exitosos" />
                                        <Bar dataKey="fallidos" stackId="eventos" fill={COLOR_FALLIDO} name="Fallidos" />
                                        <Bar dataKey="indeterminados" stackId="eventos" fill={COLOR_INDETERMINADO} name="Indeterminados" radius={[4, 4, 0, 0]} />
                                        <Line type="monotone" dataKey="ping_pongs" stroke={COLOR_PING_PONG} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} />
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
