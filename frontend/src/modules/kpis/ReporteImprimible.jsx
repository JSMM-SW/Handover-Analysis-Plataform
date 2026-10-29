import { useState } from 'react';
import {
    ComposedChart, LineChart, PieChart, Bar, Line, Pie, Cell,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import ResumenPanel from './ResumenPanel';
import TablaPeriodos from './TablaPeriodos';
import { formatearTasa } from '../../shared/formatearTasa';
import { ETIQUETAS_PERIODO } from './etiquetas';
import { useColorDeTema, renderTooltipConMediciones } from './graficoHelpers';

/**
 * Contenido visual del reporte de KPIs: panel de resumen, tarjetas,
 * donut, "Evolución de KPIs" y las 3 gráficas de distribución, más la
 * tabla de periodos -- exactamente lo que captura `exportToPDF` en
 * KpisDashboard.jsx.
 *
 * Se extrajo a su propio componente (antes vivía inline en
 * KpisDashboard.jsx) para que el historial de reportes pueda reutilizarlo
 * y regenerar un PDF antiguo a partir del snapshot guardado, sin duplicar
 * todo este JSX ni depender del estado en vivo del dashboard -- recibe
 * todos los datos por props en vez de leerlos de hooks propios.
 *
 * `puntoSeleccionado`/`loadingPeriodo`/`onSeleccionarPeriodo`/
 * `onLimpiarSeleccionPeriodo` son opcionales: el dashboard en vivo los usa
 * para el filtro cruzado al hacer clic en un punto de "Evolución de
 * KPIs"; un reporte regenerado del historial es estático y simplemente
 * los omite (sin botón "Ver todo el periodo", sin clic habilitado).
 *
 * @param {object} props
 * @param {object} props.resumen - resumen a mostrar en panel/tarjetas/donut.
 * @param {Array} props.tendencia - datos de "Evolución de KPIs" y la tabla de periodos.
 * @param {Array} props.horaDia - datos de "Distribución de Handovers por Hora del Día".
 * @param {Array} props.franjaHoraria - datos de "Distribución por Franja Horaria".
 * @param {Array} props.diaSemana - datos de "Distribución por Día de la Semana".
 * @param {string} props.periodo - periodicidad activa ("diario"/"mensual"/"anual"), para los títulos.
 * @param {string} props.sesionesTexto - texto de sesión(es) para ResumenPanel.
 * @param {string} props.periodoTexto - texto de periodo para ResumenPanel.
 * @param {string} props.tecnologiaTexto - texto de tecnología(s) para ResumenPanel.
 * @param {object|null} [props.puntoSeleccionado] - punto de `tendencia` resaltado, si hay uno.
 * @param {boolean} [props.loadingPeriodo] - true mientras cargan hora/franja del periodo elegido.
 * @param {Function} [props.onSeleccionarPeriodo] - handler de clic en un punto de "Evolución de KPIs".
 * @param {Function} [props.onLimpiarSeleccionPeriodo] - handler del botón "Ver todo el periodo".
 */
export default function ReporteImprimible({
    resumen,
    tendencia,
    horaDia,
    franjaHoraria,
    diaSemana,
    periodo,
    sesionesTexto,
    periodoTexto,
    tecnologiaTexto,
    puntoSeleccionado = null,
    loadingPeriodo = false,
    onSeleccionarPeriodo = () => {},
    onLimpiarSeleccionPeriodo = () => {},
    animado = true,
}) {
    // Series de "Evolución de KPIs" que el usuario ocultó haciendo clic en su
    // leyenda -- el gráfico cruza 5 series en 2 ejes y es difícil de leer con
    // todas a la vez, así que se deja aislar unas pocas sin tocar los datos.
    const [seriesEvolucionOcultas, setSeriesEvolucionOcultas] = useState(() => new Set());

    const colorExitoso = useColorDeTema('--color-exito');
    const colorFallido = useColorDeTema('--color-error');
    const colorIndeterminado = useColorDeTema('--color-texto-tenue');
    const colorPingPong = useColorDeTema('--color-advertencia');
    const colorBorde = useColorDeTema('--color-borde');
    const colorTextoTenue = useColorDeTema('--color-texto-tenue');
    const colorSuperficie = useColorDeTema('--color-superficie');
    const colorTexto = useColorDeTema('--color-texto');
    const colorPrimario = useColorDeTema('--color-primario');

    const pieData = resumen ? [
        { name: 'Exitoso', value: resumen.exitosos, color: colorExitoso },
        { name: 'Fallido', value: resumen.fallidos, color: colorFallido },
        { name: 'Indeterminado', value: resumen.indeterminados, color: colorIndeterminado },
    ] : [];

    /**
     * Muestra u oculta una serie de "Evolución de KPIs" al hacer clic en su
     * entrada de la leyenda (patrón estándar de leyenda interactiva).
     *
     * @param {string} dataKey - el `dataKey` de la `<Line>` clickeada (ej. "ping_pongs").
     */
    const alternarSerieEvolucion = (dataKey) => {
        setSeriesEvolucionOcultas((anterior) => {
            const siguiente = new Set(anterior);
            if (siguiente.has(dataKey)) siguiente.delete(dataKey);
            else siguiente.add(dataKey);
            return siguiente;
        });
    };

    /**
     * Arma una función de renderizado de punto para una línea de
     * "Evolución de KPIs": el punto del periodo seleccionado se dibuja
     * más grande y con un anillo alrededor, para que se note cuál está
     * elegido además del texto "Mostrando el periodo...".
     *
     * @param {string} color - color de relleno del punto (el mismo de la línea).
     * @param {number} radio - radio normal del punto, sin selección.
     * @returns {Function} función `dot` que espera Recharts.
     */
    const crearPuntoEvolucion = (color, radio) => (props) => {
        const { cx, cy, payload } = props;
        const seleccionado = puntoSeleccionado && payload.periodo === puntoSeleccionado.periodo;
        return (
            <circle
                key={`punto-${payload.periodo}`}
                cx={cx}
                cy={cy}
                r={seleccionado ? radio + 4 : radio}
                fill={color}
                stroke={seleccionado ? colorTexto : 'none'}
                strokeWidth={seleccionado ? 2 : 0}
            />
        );
    };

    return (
        <>
            <ResumenPanel
                sesionesTexto={sesionesTexto}
                periodoTexto={periodoTexto}
                tecnologiaTexto={tecnologiaTexto}
                resumen={resumen}
            />

            <div className="kpis-grid">
                <div className="kpis-card">
                    <h3 className="kpis-card-title">Total Handovers</h3>
                    <div className="kpis-stat-main">
                        <span className="kpis-stat-value large">{resumen.total_handovers}</span>
                    </div>
                    <p className="kpis-stat-sub">de {resumen.total_mediciones} mediciones</p>
                </div>

                <div className="kpis-card">
                    <h3 className="kpis-card-title">Tasa de Handover</h3>
                    <div className="kpis-stat-main">
                        <span className="kpis-stat-value large highlight-green">{formatearTasa(resumen.tasa_handover)}</span>
                    </div>
                </div>

                <div className="kpis-card">
                    <h3 className="kpis-card-title">KPIs de Handover</h3>
                    <div className="kpis-stat">
                        <span className="kpis-stat-label">Ping-Pong (HOPP)</span>
                        <span className="kpis-stat-value highlight-orange">{formatearTasa(resumen.tasa_hopp)}</span>
                    </div>
                    <div className="kpis-stat">
                        <span className="kpis-stat-label">Handover Innecesarios</span>
                        <span className="kpis-stat-value highlight-red">{formatearTasa(resumen.tasa_innecesarios)}</span>
                    </div>
                    <div className="kpis-stat">
                        <span className="kpis-stat-label">Handover Post Degradados (PHD)</span>
                        <span className="kpis-stat-value highlight-red">{formatearTasa(resumen.tasa_phd)}</span>
                    </div>
                </div>

                <div className="kpis-card">
                    <h3 className="kpis-card-title">Handover Exitosos</h3>
                    <div className="kpis-stat-main">
                        <span className="kpis-stat-value large" style={{ color: colorExitoso }}>{formatearTasa(resumen.tasa_exito)}</span>
                    </div>
                    <p className="kpis-stat-sub">{resumen.exitosos} handovers exitosos</p>
                </div>
            </div>

            <div className="kpis-row-layout">
                <div className="kpis-card" style={{ margin: 0 }}>
                    <div className="kpis-card-header-row">
                        <h3 className="kpis-card-title">Evolución de KPIs ({ETIQUETAS_PERIODO[periodo]})</h3>
                        {puntoSeleccionado && (
                            <button type="button" className="kpis-btn-reset-periodo" onClick={onLimpiarSeleccionPeriodo}>
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
                            <LineChart data={tendencia} onClick={onSeleccionarPeriodo} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                <XAxis dataKey="etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Periodo', position: 'insideBottom', offset: -10, fill: colorTextoTenue, fontSize: 12 }} />
                                <YAxis yAxisId="handovers" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Handovers', angle: -90, position: 'insideLeft', fill: colorTextoTenue, fontSize: 12, style: { textAnchor: 'middle' } }} />
                                <YAxis yAxisId="mediciones" orientation="right" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Mediciones', angle: 90, position: 'insideRight', fill: colorTextoTenue, fontSize: 12, style: { textAnchor: 'middle' } }} />
                                <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
                                <Legend
                                    verticalAlign="top"
                                    height={50}
                                    iconType="circle"
                                    onClick={(entrada) => alternarSerieEvolucion(entrada.dataKey)}
                                    formatter={(valor, entrada) => (
                                        <span
                                            style={{
                                                cursor: 'pointer',
                                                color: seriesEvolucionOcultas.has(entrada.dataKey) ? colorTextoTenue : colorTexto,
                                                textDecoration: seriesEvolucionOcultas.has(entrada.dataKey) ? 'line-through' : 'none',
                                            }}
                                        >
                                            {valor}
                                        </span>
                                    )}
                                />
                                <Line yAxisId="handovers" type="monotone" dataKey="exitosos" stroke={colorExitoso} strokeWidth={3} name="Exitosos" dot={crearPuntoEvolucion(colorExitoso, 4)} hide={seriesEvolucionOcultas.has('exitosos')} isAnimationActive={animado} />
                                <Line yAxisId="handovers" type="monotone" dataKey="fallidos" stroke={colorFallido} strokeWidth={3} name="Fallidos" dot={crearPuntoEvolucion(colorFallido, 4)} hide={seriesEvolucionOcultas.has('fallidos')} isAnimationActive={animado} />
                                <Line yAxisId="handovers" type="monotone" dataKey="indeterminados" stroke={colorIndeterminado} strokeWidth={2} name="Indeterminados" dot={crearPuntoEvolucion(colorIndeterminado, 3)} hide={seriesEvolucionOcultas.has('indeterminados')} isAnimationActive={animado} />
                                <Line yAxisId="handovers" type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={crearPuntoEvolucion(colorPingPong, 3)} hide={seriesEvolucionOcultas.has('ping_pongs')} isAnimationActive={animado} />
                                <Line yAxisId="mediciones" type="monotone" dataKey="total_mediciones" stroke={colorPrimario} strokeWidth={2} strokeDasharray="5 3" name="Mediciones" dot={crearPuntoEvolucion(colorPrimario, 3)} hide={seriesEvolucionOcultas.has('total_mediciones')} isAnimationActive={animado} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="kpis-card" style={{ margin: 0 }}>
                    <h3 className="kpis-card-title">Distribución por Tipo de Evento</h3>
                    <div style={{ height: '280px', width: '100%', marginTop: '10px', position: 'relative' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={pieData} innerRadius={70} outerRadius={95} paddingAngle={4} dataKey="value" isAnimationActive={animado}>
                                    {pieData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ backgroundColor: colorSuperficie, borderColor: colorBorde, color: colorTexto }} />
                                <Legend verticalAlign="bottom" height={36} iconType="circle" />
                            </PieChart>
                        </ResponsiveContainer>
                        <div style={{ position: 'absolute', top: '42%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none' }}>
                            <span style={{ fontSize: '20px', fontWeight: 'bold', color: colorTexto, display: 'block' }}>{resumen.total_handovers}</span>
                            <span style={{ fontSize: '11px', color: colorTextoTenue, textTransform: 'uppercase' }}>Total Handovers</span>
                        </div>
                    </div>
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
                            <ComposedChart data={horaDia} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                <XAxis dataKey="hora_etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Hora del día', position: 'insideBottom', offset: -10, fill: colorTextoTenue, fontSize: 12 }} />
                                <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Cantidad de Handovers', angle: -90, position: 'insideLeft', fill: colorTextoTenue, fontSize: 12, style: { textAnchor: 'middle' } }} />
                                <Tooltip content={(props) => renderTooltipConMediciones(props, colorSuperficie, colorBorde, colorTexto)} />
                                <Legend verticalAlign="top" height={50} iconType="circle" />
                                <Bar dataKey="exitosos" stackId="eventos" fill={colorExitoso} name="Exitosos" isAnimationActive={animado} />
                                <Bar dataKey="fallidos" stackId="eventos" fill={colorFallido} name="Fallidos" isAnimationActive={animado} />
                                <Bar dataKey="indeterminados" stackId="eventos" fill={colorIndeterminado} name="Indeterminados" radius={[4, 4, 0, 0]} isAnimationActive={animado} />
                                <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} isAnimationActive={animado} />
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
                            <ComposedChart data={franjaHoraria} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                <XAxis dataKey="franja_etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Franja Horaria', position: 'insideBottom', offset: -10, fill: colorTextoTenue, fontSize: 12 }} />
                                <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Cantidad de Handovers', angle: -90, position: 'insideLeft', fill: colorTextoTenue, fontSize: 12, style: { textAnchor: 'middle' } }} />
                                <Tooltip content={(props) => renderTooltipConMediciones(props, colorSuperficie, colorBorde, colorTexto)} />
                                <Legend verticalAlign="top" height={50} iconType="circle" />
                                <Bar dataKey="exitosos" stackId="eventos" fill={colorExitoso} name="Exitosos" isAnimationActive={animado} />
                                <Bar dataKey="fallidos" stackId="eventos" fill={colorFallido} name="Fallidos" isAnimationActive={animado} />
                                <Bar dataKey="indeterminados" stackId="eventos" fill={colorIndeterminado} name="Indeterminados" radius={[4, 4, 0, 0]} isAnimationActive={animado} />
                                <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} isAnimationActive={animado} />
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
                            <ComposedChart data={diaSemana} margin={{ top: 5, right: 10, bottom: 20, left: 10 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke={colorBorde} vertical={false} />
                                <XAxis dataKey="etiqueta" stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Día de la Semana', position: 'insideBottom', offset: -10, fill: colorTextoTenue, fontSize: 12 }} />
                                <YAxis stroke={colorTextoTenue} fontSize={12} tickLine={false} axisLine={false} label={{ value: 'Cantidad de Handovers', angle: -90, position: 'insideLeft', fill: colorTextoTenue, fontSize: 12, style: { textAnchor: 'middle' } }} />
                                <Tooltip content={(props) => renderTooltipConMediciones(props, colorSuperficie, colorBorde, colorTexto)} />
                                <Legend verticalAlign="top" height={50} iconType="circle" />
                                <Bar dataKey="exitosos" stackId="eventos" fill={colorExitoso} name="Exitosos" isAnimationActive={animado} />
                                <Bar dataKey="fallidos" stackId="eventos" fill={colorFallido} name="Fallidos" isAnimationActive={animado} />
                                <Bar dataKey="indeterminados" stackId="eventos" fill={colorIndeterminado} name="Indeterminados" radius={[4, 4, 0, 0]} isAnimationActive={animado} />
                                <Line type="monotone" dataKey="ping_pongs" stroke={colorPingPong} strokeWidth={2} name="Ping-Pong" dot={{ r: 3 }} isAnimationActive={animado} />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            <div className="kpis-row-layout" style={{ marginTop: '24px', gridTemplateColumns: '1fr' }}>
                <div className="kpis-card" style={{ margin: 0 }}>
                    <h3 className="kpis-card-title">Tabla de Periodos ({ETIQUETAS_PERIODO[periodo]})</h3>
                    <TablaPeriodos datos={tendencia} />
                </div>
            </div>
        </>
    );
}
