import { formatearTasa } from '../../shared/formatearTasa';

/**
 * Tabla con el desglose completo de cada periodo de la tendencia (Paso 9 del
 * plan de refactor): el gráfico de líneas "Evolución de KPIs" solo muestra
 * 4 series (exitosos/fallidos/indeterminados/ping-pongs); esta tabla expone
 * TODAS las columnas que calcula `calcular_tendencia` en services.py,
 * incluyendo las fechas reales de cada periodo y las métricas de UHO.
 *
 * Es un componente de presentación puro: recibe `datos` (el trendData de
 * GET /kpis/trend) tal cual y no hace ningún cálculo.
 *
 * @param {Array<object>} datos - lista de periodos devuelta por fetchTrend.
 */
export default function TablaPeriodos({ datos }) {
    if (!datos || datos.length === 0) return null;

    return (
        <div className="kpis-tabla-periodos-wrapper">
            <table className="kpis-tabla-periodos">
                <thead>
                    <tr>
                        <th>Periodo</th>
                        <th>Desde</th>
                        <th>Hasta</th>
                        <th>Mediciones</th>
                        <th>Handovers</th>
                        <th>Exitosos</th>
                        <th>Fallidos</th>
                        <th>Indeterminados</th>
                        <th>Tasa Éxito</th>
                        <th>Tasa PHD</th>
                        <th>Ping-Pong</th>
                        <th>Tasa HOPP</th>
                        <th>Evaluables UHO</th>
                        <th>UHO</th>
                        <th>Tasa Innecesarios</th>
                    </tr>
                </thead>
                <tbody>
                    {datos.map((fila) => (
                        <tr key={fila.periodo}>
                            <td>{fila.etiqueta}</td>
                            <td>{fila.fecha_inicio}</td>
                            <td>{fila.fecha_fin}</td>
                            <td>{fila.total_mediciones}</td>
                            <td>{fila.total_handovers}</td>
                            <td>{fila.exitosos}</td>
                            <td>{fila.fallidos}</td>
                            <td>{fila.indeterminados}</td>
                            <td>{formatearTasa(fila.tasa_exito)}</td>
                            <td>{formatearTasa(fila.tasa_phd)}</td>
                            <td>{fila.ping_pongs}</td>
                            <td>{formatearTasa(fila.tasa_hopp)}</td>
                            <td>{fila.uho_evaluables}</td>
                            <td>{fila.uho}</td>
                            <td>{formatearTasa(fila.tasa_innecesarios)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
