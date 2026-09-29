import { SIGNAL_METRICS, SIGNAL_COLORS } from '../signalHeat';

export default function SignalLegend({ metric, aggregated = false }) {
  const { label, unit, high, low } = SIGNAL_METRICS[metric];
  if (aggregated) return <div className="geo-signal-legend">
    <p>{label} en handovers: calor suavizado; los valores se combinan por distancia donde se superponen. No representa cobertura confirmada.</p>
    <div className="geo-legend">
      <span>{label} ≤ {low} {unit}</span><i className="geo-signal-gradient" /><span>{label} ≥ {high} {unit}</span>
      <span><i style={{ background: SIGNAL_COLORS.missing }} />{label} sin dato</span>
    </div>
  </div>;
  return <div className="geo-signal-legend">
    <div className="geo-legend">
      <span><i style={{ background: SIGNAL_COLORS.high }} />{label} ≥ {high} {unit}</span>
      <span><i style={{ background: SIGNAL_COLORS.middle }} />{low} ≤ {label} &lt; {high} {unit}</span>
      <span><i style={{ background: SIGNAL_COLORS.low }} />{label} &lt; {low} {unit}</span>
      <span><i style={{ background: SIGNAL_COLORS.missing }} />{label} sin dato</span>
    </div>
  </div>;
}
