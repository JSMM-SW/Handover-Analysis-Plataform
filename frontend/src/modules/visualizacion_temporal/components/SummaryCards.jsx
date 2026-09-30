/**
 * Tarjetas de resumen — HU-C2-007.
 *
 * Los tres indicadores obligatorios de la historia (total de handovers, radiobases involucradas y
 * sesiones analizadas) van primero y destacados; el resto son complementos que ayudan a leer el
 * recorrido pero que la historia no exige.
 *
 * Cada tarjeta tiene **su propio tono pastel** (borde, icono y sparkline) para distinguirla de un
 * vistazo, además de un icono, una ayuda «?» en lenguaje llano y, cuando el indicador tiene una
 * evolución en el tiempo, un sparkline con su tendencia. «Sesiones» no lleva sparkline a propósito:
 * con un único recorrido no hay tendencia que mostrar, y dibujar una línea plana sería decoración.
 */

import AyudaContextual from './AyudaContextual.jsx';
import { ErrorConsulta } from './EstadoConsulta.jsx';
import { IconoAntena, IconoHandover, IconoPulso, IconoRecorrido, IconoRitmo } from './Iconos.jsx';
import Sparkline from './Sparkline.jsx';
import { useResumen } from '../hooks/useDatosVT.js';
import { useTendenciasResumen } from '../hooks/useTendenciasResumen.js';

function formatearDuracion(segundos) {
  if (segundos == null) return '—';

  const horas = Math.floor(segundos / 3600);
  const minutos = Math.round((segundos % 3600) / 60);

  if (horas) return `${horas} h ${minutos} min`;
  if (minutos) return `${minutos} min`;
  return `${Math.round(segundos)} s`;
}

function Tarjeta({
  titulo,
  valor,
  detalle,
  icono,
  termino,
  tendencia = null,
  variante = 'linea',
  descripcionTendencia,
  tono = 'azul',
  principal = false,
  cargando = false,
}) {
  return (
    <article className={`vt-tarjeta vt-tarjeta--${tono}${principal ? ' vt-tarjeta--principal' : ''}`}>
      <div className="vt-tarjeta__cabecera">
        <span className="vt-tarjeta__icono">{icono}</span>
        <span className="vt-tarjeta__titulo">{titulo}</span>
        {termino && <AyudaContextual termino={termino} alineacion="derecha" />}
      </div>

      <div className="vt-tarjeta__cuerpo">
        <div className="vt-tarjeta__cifras">
          {cargando ? (
            <span className="vt-tarjeta__valor vt-esqueleto" aria-label="Cargando" />
          ) : (
            <span className="vt-tarjeta__valor">{valor ?? '—'}</span>
          )}
          {detalle && <span className="vt-tarjeta__detalle">{detalle}</span>}
        </div>

        {descripcionTendencia && (
          <Sparkline
            valores={cargando ? null : tendencia}
            variante={variante}
            descripcion={descripcionTendencia}
          />
        )}
      </div>
    </article>
  );
}

export default function SummaryCards() {
  const { data, isLoading, isError, error, refetch } = useResumen();
  const tendencias = useTendenciasResumen();

  if (isError) return <ErrorConsulta error={error} onReintentar={refetch} alto={100} />;

  const numero = (v) => (v == null ? null : v.toLocaleString('es-EC'));

  const porTecnologia = Object.entries(data?.por_tecnologia ?? {})
    .sort((a, b) => b[1] - a[1])
    // «LTE->WCDMA» se muestra con flecha tipográfica: se lee mejor y no se parte en dos líneas.
    .map(([nombre, total]) => `${nombre.replace('->', '→')}: ${total}`)
    .join(' · ');

  return (
    <div className="vt-tarjetas">
      {/* Los tres obligatorios de HU-C2-007 */}
      <Tarjeta
        titulo="Handovers"
        valor={numero(data?.total_handovers)}
        detalle={data?.total_ping_pong ? `${data.total_ping_pong} ping-pong` : null}
        icono={<IconoHandover />}
        tono="azul"
        termino="handover"
        tendencia={tendencias.handovers}
        variante="barras"
        descripcionTendencia="Handovers a lo largo del recorrido"
        principal
        cargando={isLoading}
      />
      <Tarjeta
        titulo="Radiobases"
        valor={numero(data?.radiobases_involucradas)}
        detalle="celdas distintas"
        icono={<IconoAntena />}
        tono="verde"
        termino="radiobase"
        tendencia={tendencias.radiobases}
        descripcionTendencia="Radiobases distintas acumuladas a lo largo del recorrido"
        principal
        cargando={isLoading}
      />
      <Tarjeta
        titulo="Sesiones"
        valor={numero(data?.sesiones_analizadas)}
        detalle="analizadas"
        icono={<IconoRecorrido />}
        tono="lavanda"
        principal
        cargando={isLoading}
      />

      {/* Complementos */}
      <Tarjeta
        titulo="Mediciones"
        valor={numero(data?.n_mediciones)}
        detalle={formatearDuracion(data?.duracion_s)}
        icono={<IconoPulso />}
        tono="aqua"
        tendencia={tendencias.mediciones}
        variante="barras"
        descripcionTendencia="Mediciones a lo largo del recorrido; los huecos son periodos sin captura"
        cargando={isLoading}
      />
      <Tarjeta
        titulo="HO / minuto"
        valor={data?.tasa_ho_por_minuto != null ? data.tasa_ho_por_minuto.toFixed(2) : null}
        detalle={porTecnologia || null}
        icono={<IconoRitmo />}
        tono="ambar"
        termino="tasa_ho"
        tendencia={tendencias.tasa}
        descripcionTendencia="Ritmo acumulado de handovers por minuto"
        cargando={isLoading}
      />
    </div>
  );
}
