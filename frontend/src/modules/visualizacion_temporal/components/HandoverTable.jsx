/**
 * Tabla de eventos de handover — HU-C2-009 y estructura V1 §3.
 *
 * El comportamiento clave está pedido explícitamente en la maqueta: **al hacer clic en una fila el
 * timeline hace zoom automático al evento**. Se implementa escribiendo en el store la selección y
 * el rango de zoom; las gráficas reaccionan solas.
 *
 * Las columnas Δ son de RSRP y RSRQ, no de RSSI y SINR como decía la maqueta original: son los
 * parámetros que el dataset real entrega (decisiones D-1 y D-5). La columna de SINR se muestra
 * igualmente cuando hay medida.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { sessionName } from '../../../shared/sessionNames';

import { Cargando, ErrorConsulta, SinResultados } from './EstadoConsulta.jsx';
import { IconoFlechaDerecha, IconoFlechaIzquierda } from './Iconos.jsx';
import { useHandovers } from '../hooks/useDatosVT.js';
import { formatearFechaHora, rangoAlrededorDe } from '../hooks/useSeriesEcharts.js';
import { useVisStore } from '../store/visStore.js';
import { ETIQUETAS_TIPO_EVENTO, ETIQUETAS_TIPO_EVENTO_CORTAS } from '../types/index.js';
import { fechaCorta, horaCorta } from '../utils/fechas.js';

const POR_PAGINA = 15;

/**
 * Un delta con signo y color. Un número plano no dice si la señal mejoró o empeoró, que es
 * justo lo que interesa mirar en un handover.
 *
 * `null` significa «no se pudo medir», y se distingue de un 0 («no cambió»).
 */
function Delta({ valor, unidad = 'dB' }) {
  if (valor === null || valor === undefined) {
    return <span className="vt-delta vt-delta--nulo" title="Sin medida en alguno de los extremos">—</span>;
  }

  const clase = valor > 0 ? 'vt-delta--mejora' : valor < 0 ? 'vt-delta--empeora' : 'vt-delta--igual';
  const signo = valor > 0 ? '+' : '';
  const flecha = valor > 0 ? '▲' : valor < 0 ? '▼' : '';

  return (
    <span className={`vt-delta ${clase}`}>
      {/* La flecha repite el signo en forma visual: no depender solo del verde y el rojo. */}
      {flecha && <span className="vt-delta__flecha" aria-hidden="true">{flecha}</span>}
      {signo}
      {valor.toFixed(1)} {unidad}
    </span>
  );
}

const COLUMNAS = [
  { clave: 'timestamp_evento', etiqueta: 'Fecha / hora', ordenable: true },
  { clave: 'origen', etiqueta: 'Celda origen', ordenable: false },
  { clave: 'destino', etiqueta: 'Celda destino', ordenable: false },
  { clave: 'tipo_evento', etiqueta: 'Tipo', ordenable: false },
  { clave: 'delta_rsrp_db', etiqueta: 'Δ RSRP', ordenable: true },
  { clave: 'delta_rsrq_db', etiqueta: 'Δ RSRQ', ordenable: true },
  { clave: 'delta_rssnr_db', etiqueta: 'Δ SINR', ordenable: true },
  { clave: 'duracion_permanencia_s', etiqueta: 'Permanencia', ordenable: true },
];

export default function HandoverTable() {
  const [pagina, setPagina] = useState(1);
  const [orden, setOrden] = useState({ clave: 'timestamp_evento', ascendente: true });

  const seleccionado = useVisStore((e) => e.handoverSeleccionadoId);
  const seleccionarHandover = useVisStore((e) => e.seleccionarHandover);
  const setRangoZoom = useVisStore((e) => e.setRangoZoom);
  const ventanaSegundos = useVisStore((e) => e.ventanaSegundos);
  const colapsada = useVisStore((e) => e.tablaColapsada);
  const desplegarTabla = useVisStore((e) => e.desplegarTabla);
  const variasSesiones = useVisStore((e) => e.sesionIds.length > 1);

  const filaSeleccionada = useRef(null);

  const { data, isLoading, isError, error, refetch } = useHandovers({
    page: pagina,
    pageSize: POR_PAGINA,
  });

  const eventos = useMemo(() => {
    const items = [...(data?.items ?? [])];
    const { clave, ascendente } = orden;

    items.sort((a, b) => {
      const va = clave === 'timestamp_evento' ? new Date(a[clave]).getTime() : a[clave];
      const vb = clave === 'timestamp_evento' ? new Date(b[clave]).getTime() : b[clave];

      // Los valores ausentes van siempre al final, se ordene como se ordene.
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;

      return ascendente ? va - vb : vb - va;
    });

    return items;
  }, [data, orden]);

  /** Clic en una fila: selecciona el evento y encuadra el timeline sobre él (V1 §3). */
  const alSeleccionar = (evento) => {
    seleccionarHandover(evento.id_evento);
    setRangoZoom(rangoAlrededorDe(evento.timestamp_evento, ventanaSegundos));
  };

  /**
   * Al desplegar la tabla, la fila del evento que se estaba analizando se lleva a la vista: así
   * se ve de inmediato dónde estaba dentro de la tabla completa.
   */
  useEffect(() => {
    if (!colapsada && seleccionado) {
      filaSeleccionada.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    }
  }, [colapsada, seleccionado]);

  const alOrdenar = (clave) =>
    setOrden((actual) =>
      actual.clave === clave ? { clave, ascendente: !actual.ascendente } : { clave, ascendente: true },
    );

  if (isError) return <ErrorConsulta error={error} onReintentar={refetch} alto={180} />;
  if (isLoading) return <Cargando mensaje="Cargando eventos…" alto={180} />;

  if (!eventos.length) {
    return (
      <SinResultados
        titulo="No hay handovers para estos filtros"
        mensaje="Si es la primera vez que analizas esta sesión, pulsa «Detectar handovers» en la configuración del análisis."
        alto={180}
      />
    );
  }

  const totalPaginas = Math.max(1, Math.ceil((data?.total ?? 0) / POR_PAGINA));

  // Vista plegada: cede espacio al panel de detalle sin perder la navegación entre eventos.
  if (colapsada) {
    return (
      <div className="vt-tabla-envoltorio vt-tabla-envoltorio--plegada">
        <div className="vt-tabla__barra">
          <span>{data.total} handovers</span>
          <button
            type="button"
            className="vt-boton vt-boton--texto vt-boton--pequeno"
            onClick={desplegarTabla}
            title="Muestra la tabla completa y oculta el detalle"
          >
            Desplegar
          </button>
        </div>

        {/*
          Lista visual de eventos. Plegada no caben las claves de celda, así que cada evento se
          reconoce por su número, su hora y el color de su tipo; el ping-pong lleva su marca
          porque es lo primero que un análisis querrá localizar.
        */}
        <ol className="vt-lista-compacta">
          {eventos.map((evento, posicion) => {
            const activo = seleccionado === evento.id_evento;
            return (
              <li key={evento.id_evento}>
                <button
                  type="button"
                  className={`vt-lista-compacta__item${activo ? ' vt-lista-compacta__item--activo' : ''}`}
                  onClick={() => alSeleccionar(evento)}
                  aria-current={activo ? 'true' : undefined}
                  title={formatearFechaHora(evento.timestamp_evento)}
                >
                  <span className="vt-lista-compacta__n">
                    {(pagina - 1) * POR_PAGINA + posicion + 1}
                  </span>
                  <span className="vt-lista-compacta__cuando">
                    <span className="vt-lista-compacta__hora">
                      {horaCorta(evento.timestamp_evento)}
                    </span>
                    <span className="vt-lista-compacta__fecha">
                      {fechaCorta(evento.timestamp_evento)}
                    </span>
                  </span>
                  <span className="vt-lista-compacta__marcas">
                    <span
                      className={`vt-tipo-corto vt-tipo-corto--${evento.tipo_evento}`}
                      title={ETIQUETAS_TIPO_EVENTO[evento.tipo_evento] ?? evento.tipo_evento}
                    >
                      {ETIQUETAS_TIPO_EVENTO_CORTAS[evento.tipo_evento] ?? evento.tipo_evento}
                    </span>
                    {evento.ping_pong && (
                      <span className="vt-tipo-corto vt-tipo-corto--pingpong" title="Ping-pong">
                        PP
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>

        {totalPaginas > 1 && (
          <div className="vt-paginacion vt-paginacion--compacta">
            <button
              type="button"
              className="vt-boton vt-boton--secundario vt-boton--icono"
              onClick={() => setPagina((p) => Math.max(1, p - 1))}
              disabled={pagina === 1}
              aria-label="Página anterior"
            >
              <IconoFlechaIzquierda tamano={16} />
            </button>
            <span>
              {pagina} / {totalPaginas}
            </span>
            <button
              type="button"
              className="vt-boton vt-boton--secundario vt-boton--icono"
              onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
              disabled={pagina >= totalPaginas}
              aria-label="Página siguiente"
            >
              <IconoFlechaDerecha tamano={16} />
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="vt-tabla-envoltorio">
      <div className="vt-tabla__barra">
        <span>{data.total} handovers · clic en una fila para ver su detalle</span>
      </div>
      <table className="vt-tabla">
        <thead>
          <tr>
            {COLUMNAS.map((columna) => (
              <th
                key={columna.clave}
                scope="col"
                className={columna.ordenable ? 'vt-tabla__th--ordenable' : undefined}
                onClick={columna.ordenable ? () => alOrdenar(columna.clave) : undefined}
                aria-sort={
                  orden.clave === columna.clave
                    ? orden.ascendente
                      ? 'ascending'
                      : 'descending'
                    : undefined
                }
              >
                {columna.etiqueta}
                {orden.clave === columna.clave && (
                  <span aria-hidden="true">{orden.ascendente ? ' ▲' : ' ▼'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {eventos.map((evento) => (
            <tr
              key={evento.id_evento}
              ref={seleccionado === evento.id_evento ? filaSeleccionada : undefined}
              className={`vt-tabla__fila${
                seleccionado === evento.id_evento ? ' vt-tabla__fila--seleccionada' : ''
              }`}
              onClick={() => alSeleccionar(evento)}
              tabIndex={0}
              role="button"
              aria-pressed={seleccionado === evento.id_evento}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  alSeleccionar(evento);
                }
              }}
            >
              <td>
                {formatearFechaHora(evento.timestamp_evento)}
                {/* Con varias sesiones, cada evento dice de cuál viene. */}
                {variasSesiones && evento.sesion_nombre && (
                  <span className="vt-tabla__secundario">{sessionName(evento)}</span>
                )}
              </td>
              <td>
                <code>{evento.celda_origen.clave}</code>
                {evento.celda_origen.psc_pci != null && (
                  <span className="vt-tabla__secundario"> PCI {evento.celda_origen.psc_pci}</span>
                )}
              </td>
              <td>
                <code>{evento.celda_destino.clave}</code>
                {evento.celda_destino.psc_pci != null && (
                  <span className="vt-tabla__secundario"> PCI {evento.celda_destino.psc_pci}</span>
                )}
              </td>
              <td>
                <span className={`vt-etiqueta vt-etiqueta--${evento.tipo_evento}`}>
                  {ETIQUETAS_TIPO_EVENTO[evento.tipo_evento] ?? evento.tipo_evento}
                </span>
                {evento.ping_pong && <span className="vt-etiqueta vt-etiqueta--pingpong">ping-pong</span>}
                {evento.confianza === 'baja' && (
                  <span className="vt-etiqueta vt-etiqueta--baja" title="Identidad de celda incompleta">
                    confianza baja
                  </span>
                )}
              </td>
              <td><Delta valor={evento.delta_rsrp_db} /></td>
              <td><Delta valor={evento.delta_rsrq_db} /></td>
              <td><Delta valor={evento.delta_rssnr_db} /></td>
              <td>{Math.round(evento.duracion_permanencia_s)} s</td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPaginas > 1 && (
        <div className="vt-paginacion">
          <button
            type="button"
            className="vt-boton vt-boton--secundario"
            onClick={() => setPagina((p) => Math.max(1, p - 1))}
            disabled={pagina === 1}
          >
            Anterior
          </button>
          <span>
            Página {pagina} de {totalPaginas}
          </span>
          <button
            type="button"
            className="vt-boton vt-boton--secundario"
            onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
            disabled={pagina >= totalPaginas}
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
