import { useState, useEffect, useRef } from 'react';
import { fetchKpiSummary, fetchHourlyDistribution, fetchDailyTrend } from '../../services/kpisService';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import './KpisDashboard.css';

export default function KpisDashboard() {
    const [startDate, setStartDate] = useState('2026-05-01');
    const [endDate, setEndDate] = useState('2026-05-24');
    const [summaryData, setSummaryData] = useState(null);
    const [hourlyData, setHourlyData] = useState([]);
    const [trendData, setTrendData] = useState([]);
    const [loading, setLoading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [error, setError] = useState(null);
    
    const dashboardRef = useRef(null);

    const loadData = async () => {
        setLoading(true);
        setError(null);
        try {
            const [summary, hourly, trend] = await Promise.all([
                fetchKpiSummary(startDate, endDate),
                fetchHourlyDistribution(startDate, endDate),
                fetchDailyTrend(startDate, endDate)
            ]);
            
            const formattedHourly = hourly.map(item => ({
                ...item,
                hora_etiqueta: `${String(item.hora).padStart(2, '0')}:00`
            }));

            setSummaryData(summary);
            setHourlyData(formattedHourly);
            setTrendData(trend);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, [startDate, endDate]);

    const triggerIngestion = async () => {
        setSyncing(true);
        try {
            const response = await fetch('http://localhost:8000/api/v1/ingesta/ejecutar', { method: 'POST' });
            if (!response.ok) throw new Error("El módulo de ingesta falló.");
            await loadData();
        } catch (err) {
            alert("Atención: " + err.message);
        } finally {
            setSyncing(false);
        }
    };

    const exportToPDF = async () => {
        const element = dashboardRef.current;
        if (!element) return;
        
        const controls = element.querySelector('.kpis-controls-action');
        controls.style.display = 'none';
        
        const canvas = await html2canvas(element, { backgroundColor: '#0b0d12', scale: 2 });
        const imgData = canvas.toDataURL('image/png');
        
        const pdf = new jsPDF('p', 'mm', 'a4');
        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = (canvas.height * pdfWidth) / canvas.width;
        
        pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
        pdf.save(`Reporte_Handovers_${startDate}_al_${endDate}.pdf`);
        
        controls.style.display = 'flex'; 
    };

    const hasData = summaryData && summaryData.total_handovers > 0;

    // Datos para el gráfico de dona por tipo
    const pieData = summaryData ? [
        { name: 'Exitoso', value: summaryData.exitosos, color: '#4f8cff' },
        { name: 'Ping-Pong', value: summaryData.ping_pongs, color: '#fbbf24' },
        { name: 'Innecesario', value: summaryData.uho_eventos, color: '#c084fc' },
        { name: 'Fallido', value: summaryData.fallidos, color: '#f87171' }
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
                    <div className="kpis-controls-action">
                        <button className="kpis-btn-sync" onClick={triggerIngestion} disabled={syncing || loading}>
                            {syncing ? 'Sincronizando...' : 'Extraer ETL'}
                        </button>
                        <button className="kpis-btn-export" onClick={exportToPDF} disabled={!hasData || loading}>
                            Exportar PDF
                        </button>
                    </div>
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
                    {/* Tarjetas Principales */}
                    <div className="kpis-grid">
                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Total Handovers</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large">{summaryData.total_handovers}</span>
                            </div>
                            <p className="kpis-stat-sub">Eventos en el periodo</p>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Handover Rate (HOR)</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large highlight-green">{summaryData.hor_porcentaje}%</span>
                            </div>
                            <p className="kpis-stat-sub">{summaryData.exitosos} saltos exitosos</p>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Riesgos de Movilidad</h3>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Ping-Pong (HOPP)</span>
                                <span className="kpis-stat-value highlight-orange">{summaryData.tasa_hopp}%</span>
                            </div>
                            <div className="kpis-stat">
                                <span className="kpis-stat-label">Tasa de Fallos</span>
                                <span className="kpis-stat-value highlight-red">{summaryData.tasa_fallos}%</span>
                            </div>
                        </div>

                        <div className="kpis-card">
                            <h3 className="kpis-card-title">Handovers Innecesarios</h3>
                            <div className="kpis-stat-main">
                                <span className="kpis-stat-value large" style={{ color: '#c084fc' }}>{summaryData.tasa_uho}%</span>
                            </div>
                            <p className="kpis-stat-sub">{summaryData.uho_eventos} eventos sin mejora de RSRP</p>
                        </div>
                    </div>

                    {/* Fila 1: Evolución Temporal + Resumen del Análisis */}
                    <div className="kpis-row-layout">
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Evolución Temporal de KPIs (Diaria)</h3>
                            <div style={{ height: '280px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={trendData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#262b36" vertical={false} />
                                        <XAxis dataKey="fecha_etiqueta" stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} domain={[0, 100]} />
                                        <Tooltip contentStyle={{ backgroundColor: '#14171f', borderColor: '#262b36', color: '#fff' }} />
                                        <Legend verticalAlign="top" height={36} iconType="circle" />
                                        <Line type="monotone" dataKey="hor_porcentaje" stroke="#34d399" strokeWidth={3} name="HOR (%)" dot={{ r: 4 }} />
                                        <Line type="monotone" dataKey="tasa_fallos" stroke="#f87171" strokeWidth={3} name="Tasa de Fallos (%)" dot={{ r: 4 }} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Resumen del Análisis</h3>
                            <div className="kpis-summary-box" style={{ marginTop: '20px' }}>
                                <div className="kpis-summary-item">
                                    <div>
                                        <span className="kpis-summary-label">Periodo analizado</span>
                                        <span className="kpis-summary-value">{startDate} al {endDate}</span>
                                    </div>
                                </div>
                                <div className="kpis-summary-item">
                                    <div>
                                        <span className="kpis-summary-label">Tecnología</span>
                                        <span className="kpis-summary-value">LTE / 4G</span>
                                    </div>
                                </div>
                                <div className="kpis-summary-item">
                                    <div>
                                        <span className="kpis-summary-label">Eventos procesados</span>
                                        <span className="kpis-summary-value">{summaryData.total_handovers} handovers</span>
                                    </div>
                                </div>
                                <div className="kpis-summary-item">
                                    <div>
                                        <span className="kpis-summary-label">Ventana temporal</span>
                                        <span className="kpis-summary-value">Diaria</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Fila 2: Distribución por Hora + Distribución por Tipo (Dona) */}
                    <div className="kpis-row-layout" style={{ marginTop: '24px' }}>
                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Distribución de Handovers por Hora del Día</h3>
                            <div style={{ height: '280px', width: '100%', marginTop: '20px' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={hourlyData}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#262b36" vertical={false} />
                                        <XAxis dataKey="hora_etiqueta" stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <YAxis stroke="#9aa2b1" fontSize={12} tickLine={false} axisLine={false} />
                                        <Tooltip contentStyle={{ backgroundColor: '#14171f', borderColor: '#262b36', color: '#fff' }} itemStyle={{ color: '#4f8cff' }} />
                                        <Bar dataKey="cantidad_handovers" fill="#4f8cff" radius={[4, 4, 0, 0]} name="Handovers" />
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </div>

                        <div className="kpis-card" style={{ margin: 0 }}>
                            <h3 className="kpis-card-title">Distribución por Tipo de Evento</h3>
                            <div style={{ height: '280px', width: '100%', marginTop: '10px', position: 'relative' }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <PieChart>
                                        <Pie
                                            data={pieData}
                                            innerRadius={70}
                                            outerRadius={95}
                                            paddingAngle={4}
                                            dataKey="value"
                                        >
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
                </>
            )}
        </div>
    );
}