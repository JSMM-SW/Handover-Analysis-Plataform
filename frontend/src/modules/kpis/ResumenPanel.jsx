/**
 * Panel de resumen del análisis (HU-006, Paso 8 del plan de refactor): a
 * diferencia de las tarjetas de arriba (que muestran tasas), este panel
 * muestra el CONTEXTO del análisis -- qué se analizó y con cuántos datos --
 * siempre visible en pantalla y capturado también en el PDF exportado (está
 * dentro de .kpis-shell, no se oculta como el resumen de filtros viejo).
 *
 * Es un componente de presentación puro: KpisDashboard.jsx arma los textos
 * (sesiones, período, tecnología) y le pasa `resumen` (el summaryData de
 * /kpis/summary) tal cual.
 */
export default function ResumenPanel({ sesionesTexto, periodoTexto, tecnologiaTexto, resumen }) {
    if (!resumen) return null;

    const evaluablesPhd = resumen.exitosos + resumen.fallidos;

    const filas = [
        { etiqueta: 'Sesiones analizadas', valor: sesionesTexto },
        { etiqueta: 'Período analizado', valor: periodoTexto },
        { etiqueta: 'Tecnologías', valor: tecnologiaTexto },
        { etiqueta: 'Celdas distintas', valor: resumen.celdas_distintas },
        { etiqueta: 'Total de mediciones', valor: resumen.total_mediciones },
        { etiqueta: 'Total de handovers', valor: resumen.total_handovers },
        { etiqueta: 'Evaluables para PHD', valor: evaluablesPhd },
        { etiqueta: 'Evaluables para UHO', valor: resumen.uho_evaluables },
        { etiqueta: 'Indeterminados', valor: resumen.indeterminados },
        { etiqueta: 'Cambios de celda no observados', valor: resumen.cambios_celda_no_observados },
    ];

    return (
        <section className="kpis-resumen-panel">
            <h3 className="kpis-resumen-titulo">Resumen del análisis</h3>
            <div className="kpis-resumen-grid">
                {filas.map((fila) => (
                    <div className="kpis-resumen-item" key={fila.etiqueta}>
                        <span className="kpis-resumen-label">{fila.etiqueta}</span>
                        <span className="kpis-resumen-value">{fila.valor}</span>
                    </div>
                ))}
            </div>
        </section>
    );
}
