/**
 * Panel de resumen del análisis (HU-006, Paso 8 del plan de refactor): a
 * diferencia de las tarjetas de arriba (que muestran tasas), este panel
 * muestra el CONTEXTO del análisis -- qué se analizó y con cuántos datos --
 * siempre visible en pantalla y capturado también en el PDF exportado (está
 * dentro de .kpis-shell, no se oculta como el resumen de filtros viejo).
 *
 * Los datos se agrupan en 3 bloques (alcance, volumen de datos,
 * clasificación) en vez de una lista plana de 10 filas, para que se note
 * qué tipo de información es cada una.
 *
 * Es un componente de presentación puro: KpisDashboard.jsx arma los textos
 * (sesiones, período, tecnología) y le pasa `resumen` (el summaryData de
 * /kpis/summary) tal cual.
 */
export default function ResumenPanel({ sesionesTexto, periodoTexto, tecnologiaTexto, resumen }) {
    if (!resumen) return null;

    const evaluablesPhd = resumen.exitosos + resumen.fallidos;

    // null en celdas_distintas/cambios_celda_no_observados significa que el
    // resumen viene de un periodo seleccionado en "Evolución de KPIs"
    // (Paso 10 del plan de refactor): /kpis/trend no calcula estos dos
    // campos por periodo, solo /kpis/summary sobre el rango completo.
    const celdasDistintasTexto = resumen.celdas_distintas ?? 'No disponible por periodo';
    const cambiosNoObservadosTexto = resumen.cambios_celda_no_observados ?? 'No disponible por periodo';

    const grupos = [
        {
            titulo: 'Alcance del análisis',
            filas: [
                { etiqueta: 'Sesiones analizadas', valor: sesionesTexto },
                { etiqueta: 'Período analizado', valor: periodoTexto },
                { etiqueta: 'Tecnologías', valor: tecnologiaTexto },
            ],
        },
        {
            titulo: 'Volumen de datos',
            filas: [
                { etiqueta: 'Celdas distintas', valor: celdasDistintasTexto },
                { etiqueta: 'Total de mediciones', valor: resumen.total_mediciones },
                { etiqueta: 'Total de handovers', valor: resumen.total_handovers },
            ],
        },
        {
            titulo: 'Clasificación',
            filas: [
                { etiqueta: 'Evaluables para PHD', valor: evaluablesPhd },
                { etiqueta: 'Evaluables para UHO', valor: resumen.uho_evaluables },
                { etiqueta: 'Indeterminados', valor: resumen.indeterminados },
                { etiqueta: 'Cambios de celda no observados', valor: cambiosNoObservadosTexto },
            ],
        },
    ];

    return (
        <section className="kpis-resumen-panel">
            <h3 className="kpis-resumen-titulo">Resumen del análisis</h3>
            {grupos.map((grupo) => (
                <div className="kpis-resumen-grupo" key={grupo.titulo}>
                    <h4 className="kpis-resumen-subtitulo">{grupo.titulo}</h4>
                    <div className="kpis-resumen-grid">
                        {grupo.filas.map((fila) => (
                            <div className="kpis-resumen-item" key={fila.etiqueta}>
                                <span className="kpis-resumen-label">{fila.etiqueta}</span>
                                <span className="kpis-resumen-value">{fila.valor}</span>
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </section>
    );
}
