/**
 * Tarjetas de resumen — HU-C2-007.
 *
 * Los tres indicadores obligatorios de la historia (total de handovers, radiobases involucradas y
 * sesiones analizadas) van primero y destacados; el resto son complementos que ayudan a leer el
 * recorrido pero que la historia no exige.
 *
 * Cada tarjeta tiene **su propio tono pastel** (borde e icono) para distinguirla de un vistazo,
 * además de un icono y una ayuda «?» en lenguaje llano. Muestran **solo la cifra**: las
 * micro-gráficas de tendencia que llevaban antes confundían más de lo que explicaban.
 *
 * El ping-pong no se muestra en ninguna parte de la interfaz: el backend lo sigue calculando para
 * futuras implementaciones, pero el análisis no lo tiene en cuenta.
 *
 * Cómo se calcula cada cifra: `docs/12-calculos-del-modulo.md`.
 */

import AyudaContextual from './AyudaContextual.jsx';
import { ErrorConsulta } from './EstadoConsulta.jsx';
import { IconoAntena, IconoHandover, IconoPulso, IconoRecorrido, IconoRitmo } from './Iconos.jsx';
import { useDetectando, useResumen } from '../hooks/useDatosVT.js';
import { desgloseTecnologia, formatearDuracion } from '../utils/formatoResumen.js';

function Tarjeta({ titulo, valor, detalle, icono, termino, tono = 'azul', principal = false, cargando = false }) {
  return (
    <article className={`vt-tarjeta vt-tarjeta--${tono}${principal ? ' vt-tarjeta--principal' : ''}`}>
      <div className="vt-tarjeta__cabecera">
        <span className="vt-tarjeta__icono">{icono}</span>
        <span className="vt-tarjeta__titulo">{titulo}</span>
        {termino && <AyudaContextual termino={termino} alineacion="derecha" />}
      </div>

      <div className="vt-tarjeta__cifras">
        {cargando ? (
          <span className="vt-tarjeta__valor vt-esqueleto" aria-label="Cargando" />
        ) : (
          <span className="vt-tarjeta__valor">{valor ?? '—'}</span>
        )}
        {detalle && <span className="vt-tarjeta__detalle">{detalle}</span>}
      </div>
    </article>
  );
}

export default function SummaryCards() {
  const { data, isLoading: cargandoResumen, isError, error, refetch } = useResumen();
  // Mientras se detectan los handovers, las cifras de la base están a punto de cambiar.
  const detectando = useDetectando();
  const isLoading = cargandoResumen || detectando;

  if (isError) return <ErrorConsulta error={error} onReintentar={refetch} alto={100} />;

  const numero = (v) => (v == null ? null : v.toLocaleString('es-EC'));
  const porTecnologia = desgloseTecnologia(data?.por_tecnologia);

  return (
    <div className="vt-tarjetas">
      {/* Los tres obligatorios de HU-C2-007 */}
      <Tarjeta
        titulo="Handovers"
        valor={numero(data?.total_handovers)}
        detalle="detectados"
        icono={<IconoHandover />}
        tono="azul"
        termino="handover"
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
        cargando={isLoading}
      />
      <Tarjeta
        titulo="HO / minuto"
        valor={data?.tasa_ho_por_minuto != null ? data.tasa_ho_por_minuto.toFixed(2) : null}
        detalle={porTecnologia || null}
        icono={<IconoRitmo />}
        tono="ambar"
        termino="tasa_ho"
        cargando={isLoading}
      />
    </div>
  );
}
