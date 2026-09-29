export default function RadioBaseSummary({ data }) {
  const count = data.radios_base?.length || 0;
  const summary = data.resumen_radios_base;
  return <aside className="geo-radio-summary" aria-label="Estimación de radios base">
    <strong>{count ? `${count} estimaciones por celda` : 'No hay datos suficientes para estimar ubicaciones con estos filtros.'}</strong>
    <p>Las posiciones son estimaciones basadas en las mediciones del recorrido; no son ubicaciones confirmadas de antenas.</p>
    <p>Se calcula por sesión y celda. Una misma antena puede tener varias celdas. Las sesiones se mantienen separadas porque no se dispone del operador; cada sesión debe corresponder a una sola red.</p>
    {summary && <details><summary>Datos utilizados y descartados</summary>
      <p>{summary.grupos_evaluados} grupos evaluados · {summary.grupos_insuficientes} grupos con posiciones insuficientes o extensión no adecuada.</p>
      <p>{summary.mediciones_descartadas} mediciones excluidas · {summary.duplicados_descartados} muestras repetidas descartadas.</p>
      {Object.entries(summary.motivos || {}).map(([reason, total]) => <p key={reason}>{reason}: {total}</p>)}
      <p>Los filtros de fecha, tecnología y zona cambian las mediciones usadas y pueden desplazar las estimaciones. Un recorrido por un solo lado de la antena puede sesgar su posición.</p>
    </details>}
  </aside>;
}
