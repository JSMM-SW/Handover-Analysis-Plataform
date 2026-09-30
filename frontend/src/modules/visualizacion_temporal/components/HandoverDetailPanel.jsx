/**
 * Panel de detalle PRE / DURANTE / POST — HU-C2-005 y estructura V1 §4.
 *
 * Se abre al seleccionar un handover en la lista. De arriba abajo responde a tres preguntas, en
 * el orden en que un docente se las haría:
 *
 * 1. **¿Qué pasó?** Cabecera: de qué celda a qué celda, cuándo y de qué tipo.
 * 2. **¿Cómo se vio la señal?** Gráfica con las zonas ANTES y DESPUÉS sombreadas en azul y verde pastel.
 * 3. **¿Mejoró?** Tabla de medias pre/post con su Δ y el número de muestras que la respaldan.
 */

import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';

import AyudaContextual from './AyudaContextual.jsx';
import CampoNumero from './CampoNumero.jsx';
import { Cargando, ErrorConsulta, SinResultados } from './EstadoConsulta.jsx';
import { IconoFlechaDerecha, IconoFlechaIzquierda } from './Iconos.jsx';
import { useHandovers, useVentanaHandover } from '../hooks/useDatosVT.js';
import {
  SOMBREADO_VENTANA,
  formatearFechaHora,
  useOpcionVentana,
} from '../hooks/useSeriesEcharts.js';
import { useVisStore } from '../store/visStore.js';
import { ETIQUETAS_RF, ETIQUETAS_TIPO_EVENTO, PARAMETROS_RF } from '../types/index.js';

const ALTO = 280;

/** Presets de ventana temporal. El valor por defecto es 5 s, como pide la maqueta V1. */
const VENTANAS = [2, 5, 10, 30];

function Delta({ valor }) {
  if (valor === null || valor === undefined) {
    return <span className="vt-delta vt-delta--nulo">—</span>;
  }
  const clase = valor > 0 ? 'vt-delta--mejora' : valor < 0 ? 'vt-delta--empeora' : 'vt-delta--igual';
  const flecha = valor > 0 ? '▲' : valor < 0 ? '▼' : '';
  return (
    <span className={`vt-delta ${clase}`}>
      {flecha && <span className="vt-delta__flecha" aria-hidden="true">{flecha}</span>}
      {valor > 0 ? '+' : ''}
      {valor.toFixed(2)}
    </span>
  );
}

export default function HandoverDetailPanel() {
  const idSeleccionado = useVisStore((e) => e.handoverSeleccionadoId);
  const seleccionarHandover = useVisStore((e) => e.seleccionarHandover);
  const ventanaSegundos = useVisStore((e) => e.ventanaSegundos);
  const setVentana = useVisStore((e) => e.setVentana);
  const parametroDetalle = useVisStore((e) => e.parametroDetalle);
  const setParametroDetalle = useVisStore((e) => e.setParametroDetalle);

  const { data, isLoading, isError, error, refetch, isFetching, isPlaceholderData } =
    useVentanaHandover();
  const listado = useHandovers({ pageSize: 500 });

  const eventos = useMemo(() => listado.data?.items ?? [], [listado.data]);
  const indice = eventos.findIndex((e) => e.id_evento === idSeleccionado);

  const parametrosGraficados = useMemo(
    () => (parametroDetalle === 'todos' ? PARAMETROS_RF : [parametroDetalle]),
    [parametroDetalle],
  );

  const opcion = useOpcionVentana({ datos: data, parametros: parametrosGraficados });

  if (!idSeleccionado) {
    return (
      <SinResultados
        titulo="Ningún handover seleccionado"
        mensaje="Elige un evento de la lista para analizar su ventana temporal."
        alto={ALTO}
      />
    );
  }

  if (isError) return <ErrorConsulta error={error} onReintentar={refetch} alto={ALTO} />;
  if (isLoading || !data) return <Cargando mensaje="Cargando ventana del evento…" alto={ALTO} />;

  const { evento } = data;

  // Cuando el evento está cerca del borde del recorrido, la ventana llega recortada.
  const antesReal = Math.abs(Math.min(...data.t_relativo_s));
  const despuesReal = Math.max(...data.t_relativo_s);
  const recortada = antesReal < ventanaSegundos || despuesReal < ventanaSegundos;

  return (
    // La clave hace que el panel se vuelva a montar al cambiar de evento: así la transición de
    // entrada marca visualmente que lo que se ve es otro traspaso.
    <div className="vt-detalle" key={evento.id_evento}>
      {/* 1. Qué pasó */}
      <div className="vt-detalle__cabecera">
        <div className="vt-detalle__identidad">
          <span className="vt-detalle__numero">
            Handover {indice >= 0 ? indice + 1 : '—'}
            {eventos.length ? ` de ${eventos.length}` : ''}
          </span>
          <h3 className="vt-detalle__ruta">
            <code>{evento.celda_origen.clave}</code>
            <span className="vt-detalle__flecha">
              <IconoFlechaDerecha tamano={16} />
              <span className="vt-visualmente-oculto">hacia</span>
            </span>
            <code>{evento.celda_destino.clave}</code>
          </h3>
          <div className="vt-detalle__meta">
            <span className="vt-detalle__hora">{formatearFechaHora(evento.timestamp_evento)}</span>
            <span className={`vt-etiqueta vt-etiqueta--${evento.tipo_evento}`}>
              {ETIQUETAS_TIPO_EVENTO[evento.tipo_evento] ?? evento.tipo_evento}
            </span>
            {evento.tipo_tecnologia && (
              <span className="vt-etiqueta">{evento.tipo_tecnologia}</span>
            )}
            {evento.ping_pong && <span className="vt-etiqueta vt-etiqueta--pingpong">ping-pong</span>}
            {evento.confianza === 'baja' && (
              <span className="vt-etiqueta vt-etiqueta--baja">confianza baja</span>
            )}
            <AyudaContextual termino="tipo_evento" alineacion="izquierda" />
          </div>
        </div>

        <div className="vt-detalle__navegacion">
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-boton--pequeno"
            onClick={() => seleccionarHandover(eventos[indice - 1].id_evento)}
            disabled={indice <= 0}
            title="Handover anterior"
          >
            <IconoFlechaIzquierda tamano={15} />
            Anterior
          </button>
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-boton--pequeno"
            onClick={() => seleccionarHandover(eventos[indice + 1].id_evento)}
            disabled={indice < 0 || indice >= eventos.length - 1}
            title="Handover siguiente"
          >
            Siguiente
            <IconoFlechaDerecha tamano={15} />
          </button>
        </div>
      </div>

      {/* 2. Cómo se vio la señal */}
      <div className="vt-barra-herramientas">
        <span className="vt-barra-herramientas__etiqueta">Ventana</span>
        <div className="vt-segmentado" role="group" aria-label="Ventana temporal">
          {VENTANAS.map((segundos) => (
            <button
              key={segundos}
              type="button"
              className={`vt-segmento${ventanaSegundos === segundos ? ' vt-segmento--activo' : ''}`}
              onClick={() => setVentana(segundos)}
              aria-pressed={ventanaSegundos === segundos}
            >
              ±{segundos}s
            </button>
          ))}
        </div>
        <CampoNumero
          valor={ventanaSegundos}
          onCambio={setVentana}
          min={1}
          max={600}
          aria-label="Ventana temporal en segundos"
        />

        <span className="vt-barra-herramientas__separador" aria-hidden="true" />

        <label className="vt-barra-herramientas__campo">
          <span className="vt-barra-herramientas__etiqueta">Parámetro</span>
          <select
            className="vt-select vt-select--compacto"
            value={parametroDetalle}
            onChange={(e) => setParametroDetalle(e.target.value)}
            aria-label="Parámetro a analizar"
          >
            <option value="todos">Todos</option>
            {PARAMETROS_RF.map((p) => (
              <option key={p} value={p}>
                {ETIQUETAS_RF[p].etiqueta}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Leyenda de las zonas sombreadas: la gráfica no se entiende sin ella. */}
      <div className="vt-leyenda-zonas" aria-hidden="true">
        <span className="vt-leyenda-zonas__item">
          <span className="vt-leyenda-zonas__muestra" style={{ background: SOMBREADO_VENTANA.pre }} />
          Antes del traspaso
        </span>
        <span className="vt-leyenda-zonas__item">
          <span className="vt-leyenda-zonas__linea" />
          Instante del handover
        </span>
        <span className="vt-leyenda-zonas__item">
          <span className="vt-leyenda-zonas__muestra" style={{ background: SOMBREADO_VENTANA.post }} />
          Después del traspaso
        </span>
        <AyudaContextual termino="pre_post" alineacion="derecha" />
      </div>

      {recortada && (
        <p className="vt-aviso vt-aviso--sin-datos">
          Ventana recortada por el borde del recorrido: solo hay {antesReal.toFixed(1)} s de datos
          previos y {despuesReal.toFixed(1)} s posteriores.
        </p>
      )}

      {opcion ? (
        <div
          className={`vt-grafica__lienzo vt-detalle__grafica${
            isFetching && isPlaceholderData ? ' vt-grafica__lienzo--actualizando' : ''
          }`}
        >
          <ReactECharts
            option={opcion}
            style={{ height: ALTO, width: '100%' }}
            opts={{ renderer: 'canvas' }}
            notMerge
            lazyUpdate
          />
        </div>
      ) : (
        <SinResultados
          titulo="Sin datos en la ventana"
          mensaje="No hay mediciones alrededor de este evento."
          alto={ALTO}
        />
      )}

      {/* 3. ¿Mejoró? */}
      <div className="vt-tabla-envoltorio">
        <table className="vt-tabla vt-tabla--compacta">
          <caption className="vt-tabla__pie">
            Comparación de las medias antes y después del handover
          </caption>
          <thead>
            <tr>
              <th scope="col">Parámetro</th>
              <th scope="col">Media pre</th>
              <th scope="col">Media post</th>
              <th scope="col">
                <span className="vt-th-ayuda">
                  Δ <AyudaContextual termino="delta" alineacion="izquierda" />
                </span>
              </th>
              <th scope="col">
                <span className="vt-th-ayuda">
                  Muestras <AyudaContextual termino="muestras" alineacion="derecha" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {PARAMETROS_RF.filter((p) => data.estadisticas?.[p]).map((parametro) => {
              const est = data.estadisticas[parametro];
              return (
                <tr key={parametro} className={est.disponible ? undefined : 'vt-tabla__fila--atenuada'}>
                  <td>
                    <span
                      className="vt-capa__color"
                      style={{ '--vt-color-capa': ETIQUETAS_RF[parametro].color }}
                      aria-hidden="true"
                    />{' '}
                    {ETIQUETAS_RF[parametro].etiqueta}
                  </td>
                  <td className="vt-tabla__numero">
                    {est.media_pre ?? <span className="vt-delta--nulo">sin datos</span>}
                  </td>
                  <td className="vt-tabla__numero">
                    {est.media_post ?? <span className="vt-delta--nulo">sin datos</span>}
                  </td>
                  <td className="vt-tabla__numero"><Delta valor={est.delta} /></td>
                  <td className="vt-tabla__secundario">
                    {est.n_pre} pre · {est.n_post} post
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
