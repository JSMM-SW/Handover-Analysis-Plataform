export default function RadioBaseSummary({ data }) {
  const count = data.radios_base?.length || 0;
  return <aside className="geo-radio-summary" aria-label="Estimación de radios base">
    <strong>Número de estimaciones: {count}</strong>
    <p>Las posiciones son estimaciones basadas en las mediciones del recorrido; no son ubicaciones confirmadas de antenas.</p>
  </aside>;
}
