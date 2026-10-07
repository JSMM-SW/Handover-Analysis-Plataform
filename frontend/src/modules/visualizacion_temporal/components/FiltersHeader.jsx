/**
 * Configuración del análisis — HU-C2-006.
 *
 * Una sola tarjeta con dos bloques, siguiendo la ley de proximidad: primero **qué** se analiza
 * (una o varias sesiones y la detección) y después **qué parte** (los filtros).
 *
 * Cómo funcionan los filtros de tiempo:
 *
 * - **Solo se ofrece lo que existe.** El calendario deja elegir únicamente los días con
 *   mediciones de las sesiones elegidas (los que tienen handovers llevan un punto), la franja
 *   horaria solo ofrece horas con datos en esos días, y las tecnologías son las que aparecen en
 *   la base. Todo sale de `GET /disponibilidad` a través de `useFiltrosDisponibles`.
 * - **Fechas «Desde» y «Hasta»** marcan días completos: desde las 00:00 del primero hasta las
 *   23:59:59 del último.
 * - **Franja horaria** acota las horas dentro de esos días. Si no se indica, se analiza el día
 *   entero; si se indica, se aplica a cada día del rango.
 * - **Todo va en hora local.** Las fechas se envían como instantes con zona y la franja horaria
 *   con la zona del navegador, que el backend usa para comparar (`utils/fechas.js`).
 * - **Todo filtro aplicado se ve** como un chip que se quita con un clic.
 */

import { useMemo } from 'react';

import AyudaContextual from './AyudaContextual.jsx';
import { IconoAjustes, IconoCerrar } from './Iconos.jsx';
import SelectorFecha from './SelectorFecha.jsx';
import SelectorSesiones from './SelectorSesiones.jsx';
import { useDeteccionAutomatica, useResumen, useSesiones } from '../hooks/useDatosVT.js';
import { useFiltrosDisponibles } from '../hooks/useFiltrosDisponibles.js';
import { useVisStore } from '../store/visStore.js';
import { textoFecha } from '../utils/fechas.js';

export default function FiltersHeader() {
  const sesionIds = useVisStore((e) => e.sesionIds);
  const desde = useVisStore((e) => e.desde);
  const hasta = useVisStore((e) => e.hasta);
  const horaInicio = useVisStore((e) => e.horaInicio);
  const horaFin = useVisStore((e) => e.horaFin);
  const tecnologias = useVisStore((e) => e.tecnologias);

  const setSesiones = useVisStore((e) => e.setSesiones);
  const toggleSesion = useVisStore((e) => e.toggleSesion);
  const setRangoFecha = useVisStore((e) => e.setRangoFecha);
  const setRangoHora = useVisStore((e) => e.setRangoHora);
  const toggleTecnologia = useVisStore((e) => e.toggleTecnologia);
  const limpiarFiltros = useVisStore((e) => e.limpiarFiltros);

  const { data: sesiones = [], isLoading, isError, error } = useSesiones();
  const resumen = useResumen();
  // Los handovers se detectan solos al elegir sesiones: ya no hay botón.
  const deteccion = useDeteccionAutomatica();
  const disponibles = useFiltrosDisponibles();

  const haySesion = sesionIds.length > 0;
  const cargandoDatos = haySesion && disponibles.cargando;

  const chips = useMemo(() => {
    const activos = [];
    if (desde)
      activos.push({ clave: 'desde', texto: `Desde ${textoFecha(desde)}`, quitar: () => setRangoFecha(null, hasta) });
    if (hasta)
      activos.push({ clave: 'hasta', texto: `Hasta ${textoFecha(hasta)}`, quitar: () => setRangoFecha(desde, null) });
    if (horaInicio)
      activos.push({ clave: 'hi', texto: `Desde las ${horaInicio.slice(0, 5)}`, quitar: () => setRangoHora(null, horaFin) });
    if (horaFin)
      activos.push({ clave: 'hf', texto: `Hasta las ${horaFin.slice(0, 5)}`, quitar: () => setRangoHora(horaInicio, null) });
    tecnologias.forEach((t) =>
      activos.push({ clave: `tec-${t}`, texto: t, quitar: () => toggleTecnologia(t) }),
    );
    return activos;
  }, [desde, hasta, horaInicio, horaFin, tecnologias, setRangoFecha, setRangoHora, toggleTecnologia]);

  const hayFiltros = chips.length > 0;
  // `?? null` en vez de leer la propiedad a pelo: una respuesta incompleta no debe tumbar la
  // configuración entera y dejar al usuario sin controles.
  const nMediciones = resumen.data?.n_mediciones ?? null;
  const nHandovers = resumen.data?.total_handovers ?? null;
  const sinResultados = hayFiltros && nMediciones === 0;

  return (
    <section className="vt-config" aria-labelledby="vt-config-titulo">
      <div className="vt-config__cabecera">
        <span className="vt-config__icono">
          <IconoAjustes />
        </span>
        <h2 id="vt-config-titulo" className="vt-config__titulo">
          Configuración del análisis
        </h2>
      </div>

      {/* Bloque 1: qué se analiza */}
      <div className="vt-config__bloque">
        <span className="vt-config__paso" aria-hidden="true">1</span>
        <div className="vt-config__cuerpo">
          <div className="vt-config__fila">
            <div className="vt-campo vt-campo--ancho">
              <span className="vt-campo__etiqueta">Sesiones a analizar</span>
              <SelectorSesiones
                sesiones={sesiones}
                seleccionadas={sesionIds}
                onAlternar={toggleSesion}
                onLimpiar={() => setSesiones([])}
                cargando={isLoading}
                deshabilitado={isError}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Bloque 2: qué parte del recorrido */}
      {/*
        El título del bloque no es un <legend>: una leyenda tiene que ser el primer hijo del
        fieldset y aquí va detrás del número de paso. Se enlaza con aria-labelledby, que da el
        mismo nombre accesible.
      */}
      <fieldset
        className="vt-config__bloque vt-filtros"
        disabled={!haySesion}
        aria-labelledby="vt-filtros-titulo"
      >
        <span className="vt-config__paso" aria-hidden="true">2</span>
        <div className="vt-config__cuerpo">
          <span id="vt-filtros-titulo" className="vt-filtros__leyenda">
            Filtros
          </span>

          <div className="vt-filtros__rejilla">
            <div className="vt-campo">
              <span className="vt-campo__etiqueta">Desde</span>
              <SelectorFecha
                etiqueta="Fecha de inicio"
                valor={disponibles.fechaDesde}
                dias={disponibles.dias}
                max={disponibles.fechaHasta}
                onCambio={disponibles.elegirDesde}
                cargando={cargandoDatos}
              />
            </div>

            <div className="vt-campo">
              <span className="vt-campo__etiqueta">Hasta</span>
              <SelectorFecha
                etiqueta="Fecha de fin"
                valor={disponibles.fechaHasta}
                dias={disponibles.dias}
                min={disponibles.fechaDesde}
                onCambio={disponibles.elegirHasta}
                cargando={cargandoDatos}
              />
            </div>

            <div className="vt-campo">
              <span className="vt-campo__etiqueta">
                Franja horaria
                <AyudaContextual
                  titulo="Franja horaria"
                  texto="Si no eliges horas, se analiza cada día completo. Si las eliges, solo se analizan esas horas dentro de las fechas seleccionadas. Solo se ofrecen horas con mediciones."
                />
              </span>
              <div className="vt-campo__par">
                <select
                  className={`vt-select vt-select--hora${horaInicio ? '' : ' vt-input--vacio'}`}
                  value={horaInicio ?? ''}
                  onChange={(e) => disponibles.elegirHoraInicio(e.target.value)}
                  aria-label="Franja horaria: desde"
                  disabled={!disponibles.horasInicio.length}
                >
                  <option value="">Desde…</option>
                  {disponibles.horasInicio.map((opcion) => (
                    <option key={opcion.valor} value={opcion.valor}>
                      {opcion.etiqueta}
                    </option>
                  ))}
                </select>
                <span className="vt-campo__separador" aria-hidden="true">–</span>
                <select
                  className={`vt-select vt-select--hora${horaFin ? '' : ' vt-input--vacio'}`}
                  value={horaFin ?? ''}
                  onChange={(e) => disponibles.elegirHoraFin(e.target.value)}
                  aria-label="Franja horaria: hasta"
                  disabled={!disponibles.horasFin.length}
                >
                  <option value="">Hasta…</option>
                  {disponibles.horasFin.map((opcion) => (
                    <option key={opcion.valor} value={opcion.valor}>
                      {opcion.etiqueta}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="vt-campo">
              <span className="vt-campo__etiqueta">
                <span id="vt-etiqueta-tecnologia">Tecnología</span>
                <AyudaContextual termino="tecnologia" alineacion="derecha" />
              </span>
              {disponibles.tecnologias.length ? (
                <div
                  className="vt-segmentado vt-segmentado--multiple"
                  role="group"
                  aria-labelledby="vt-etiqueta-tecnologia"
                >
                  {/* Las que aparecen en los datos de las sesiones elegidas, no una lista fija. */}
                  {disponibles.tecnologias.map((t) => (
                    <label
                      key={t}
                      className={`vt-segmento${tecnologias.includes(t) ? ' vt-segmento--activo' : ''}`}
                    >
                      <input
                        type="checkbox"
                        className="vt-visualmente-oculto"
                        checked={tecnologias.includes(t)}
                        onChange={() => toggleTecnologia(t)}
                      />
                      <span>{t}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <span className="vt-filtros__vacio">
                  {cargandoDatos ? 'Cargando…' : haySesion ? 'Sin tecnología registrada' : '—'}
                </span>
              )}
            </div>
          </div>

          <div className="vt-filtros__pie">
            {/* Retroalimentación: qué filtros están puestos y qué han dejado fuera */}
            {hayFiltros ? (
              <div className="vt-chips" aria-label="Filtros aplicados">
                {chips.map((chip) => (
                  <button
                    key={chip.clave}
                    type="button"
                    className="vt-chip"
                    onClick={chip.quitar}
                    title="Quitar este filtro"
                  >
                    {chip.texto}
                    <IconoCerrar tamano={12} />
                  </button>
                ))}
              </div>
            ) : (
              <span className="vt-filtros__vacio">Sin filtros: se analiza el recorrido completo.</span>
            )}

            <button
              type="button"
              className="vt-boton vt-boton--texto"
              onClick={limpiarFiltros}
              disabled={!hayFiltros}
            >
              Limpiar filtros
            </button>
          </div>

          {hayFiltros && (
            <div className="vt-filtros__estado" aria-live="polite">
              {resumen.isFetching ? (
                <span className="vt-filtros__resultado">Aplicando…</span>
              ) : sinResultados ? (
                <p className="vt-aviso vt-aviso--sin-datos" role="status">
                  <strong>No hay mediciones en ese rango.</strong> Prueba a ampliar las fechas o
                  la franja horaria, o pulsa «Limpiar filtros».
                </p>
              ) : (
                nMediciones !== null && (
                  <span className="vt-filtros__resultado" role="status">
                    <strong>{nMediciones.toLocaleString('es-EC')}</strong> mediciones y{' '}
                    <strong>{nHandovers ?? 0}</strong> handovers en el rango filtrado.
                  </span>
                )
              )}
            </div>
          )}
        </div>
      </fieldset>

      {isError && (
        <p className="vt-aviso vt-aviso--error" role="alert">
          No se pudieron cargar las sesiones: {error?.message}
        </p>
      )}

      {disponibles.error && (
        <p className="vt-aviso vt-aviso--error" role="alert">
          No se pudieron cargar las fechas con datos: {disponibles.error.message}
        </p>
      )}

      {deteccion.isPending && (
        <p className="vt-aviso vt-aviso--info" role="status">
          Detectando handovers…
        </p>
      )}

      {deteccion.fallidas.length > 0 && !deteccion.isPending && (
        <div className="vt-aviso vt-aviso--error" role="alert">
          No se pudieron detectar los handovers de{' '}
          {deteccion.fallidas.length === 1 ? 'una sesión' : `${deteccion.fallidas.length} sesiones`}:{' '}
          {deteccion.fallidas.map((f) => f.mensaje).join(' · ')}
          <button
            type="button"
            className="vt-boton vt-boton--texto vt-boton--pequeno"
            onClick={deteccion.reintentar}
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Total de las sesiones elegidas (lo mismo que la tarjeta «Handovers»); se oculta a los 3 s. */}
      {deteccion.avisoVisible && deteccion.resumenSeleccion.sesiones > 0 && (
        <p className="vt-aviso vt-aviso--ok" role="status">
          Handovers detectados: <strong>{deteccion.resumenSeleccion.total_handovers}</strong>
          {deteccion.resumenSeleccion.sesiones > 1
            ? ` en ${deteccion.resumenSeleccion.sesiones} sesiones`
            : ''}
          .
        </p>
      )}
    </section>
  );
}
