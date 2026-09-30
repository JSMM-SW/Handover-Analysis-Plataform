/**
 * Configuración del análisis — HU-C2-006.
 *
 * Una sola tarjeta con dos bloques, siguiendo la ley de proximidad: primero **qué** se analiza
 * (una o varias sesiones y la detección) y después **qué parte** (los filtros).
 *
 * Cómo funcionan los filtros de tiempo:
 *
 * - **Fechas «Desde» y «Hasta»** marcan días completos: desde las 00:00 del primero hasta las
 *   23:59:59 del último. Pulsar en cualquier parte del campo abre el calendario.
 * - **Franja horaria** acota las horas dentro de esos días. Si no se indica, se analiza el día
 *   entero (00:00 a 23:59); si se indica, se aplica a cada día del rango.
 * - **La fecha se envía con zona.** El usuario piensa en hora local y el backend compara en UTC;
 *   la conversión se hace en `utils/fechas.js`.
 * - **Todo filtro aplicado se ve** como un chip que se quita con un clic.
 */

import { useMemo } from 'react';

import AyudaContextual from './AyudaContextual.jsx';
import CampoHora from './CampoHora.jsx';
import { IconoAjustes, IconoCerrar, IconoDestello } from './Iconos.jsx';
import SelectorSesiones from './SelectorSesiones.jsx';
import { useDeteccion, useResumen, useSesiones } from '../hooks/useDatosVT.js';
import { abrirSelectorNativo } from '../hooks/useInterfaz.js';
import { useVisStore } from '../store/visStore.js';
import { TECNOLOGIAS } from '../types/index.js';
import { aFechaLocal, aInstanteUTC, textoFecha } from '../utils/fechas.js';

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
  const deteccion = useDeteccion();

  const haySesion = sesionIds.length > 0;

  // Los campos solo muestran la fecha; el store guarda el instante que abarca el día completo.
  const fechaDesde = aFechaLocal(desde);
  const fechaHasta = aFechaLocal(hasta);

  const chips = useMemo(() => {
    const activos = [];
    if (desde)
      activos.push({ clave: 'desde', texto: `Desde ${textoFecha(desde)}`, quitar: () => setRangoFecha(null, hasta) });
    if (hasta)
      activos.push({ clave: 'hasta', texto: `Hasta ${textoFecha(hasta)}`, quitar: () => setRangoFecha(desde, null) });
    if (horaInicio)
      activos.push({ clave: 'hi', texto: `Desde las ${horaInicio}`, quitar: () => setRangoHora(null, horaFin) });
    if (horaFin)
      activos.push({ clave: 'hf', texto: `Hasta las ${horaFin}`, quitar: () => setRangoHora(horaInicio, null) });
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

            <button
              type="button"
              className="vt-boton vt-boton--primario"
              onClick={() => deteccion.mutate({ sesionIds })}
              disabled={!haySesion || deteccion.isPending}
              title="Recorre las mediciones de las sesiones elegidas y detecta los cambios de celda servidora"
            >
              <IconoDestello tamano={16} />
              {deteccion.isPending ? 'Detectando…' : 'Detectar handovers'}
            </button>
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
            <label className="vt-campo">
              <span className="vt-campo__etiqueta">Desde</span>
              <input
                className={`vt-input vt-input--fecha${fechaDesde ? '' : ' vt-input--vacio'}`}
                type="date"
                value={fechaDesde}
                onChange={(e) => setRangoFecha(aInstanteUTC(e.target.value, null, 'inicio'), hasta)}
                onClick={abrirSelectorNativo}
                aria-label="Fecha de inicio"
                max={fechaHasta || undefined}
              />
            </label>

            <label className="vt-campo">
              <span className="vt-campo__etiqueta">Hasta</span>
              <input
                className={`vt-input vt-input--fecha${fechaHasta ? '' : ' vt-input--vacio'}`}
                type="date"
                value={fechaHasta}
                onChange={(e) => setRangoFecha(desde, aInstanteUTC(e.target.value, null, 'fin'))}
                onClick={abrirSelectorNativo}
                aria-label="Fecha de fin"
                min={fechaDesde || undefined}
              />
            </label>

            <div className="vt-campo">
              <span className="vt-campo__etiqueta">
                Franja horaria
                <AyudaContextual
                  titulo="Franja horaria"
                  texto="Si no eliges horas, se analiza cada día completo (de 00:00 a 23:59). Si las eliges, solo se analizan esas horas dentro de las fechas seleccionadas."
                />
              </span>
              <div className="vt-campo__par">
                <CampoHora
                  valor={horaInicio}
                  onCambio={(hora) => setRangoHora(hora, horaFin)}
                  ejemplo="08:00"
                  etiqueta="Franja horaria: desde"
                />
                <span className="vt-campo__separador" aria-hidden="true">–</span>
                <CampoHora
                  valor={horaFin}
                  onCambio={(hora) => setRangoHora(horaInicio, hora)}
                  ejemplo="18:00"
                  etiqueta="Franja horaria: hasta"
                />
              </div>
            </div>

            <div className="vt-campo">
              <span className="vt-campo__etiqueta">
                <span id="vt-etiqueta-tecnologia">Tecnología</span>
                <AyudaContextual termino="tecnologia" alineacion="derecha" />
              </span>
              <div
                className="vt-segmentado vt-segmentado--multiple"
                role="group"
                aria-labelledby="vt-etiqueta-tecnologia"
              >
                {TECNOLOGIAS.map((t) => (
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

      {deteccion.isError && (
        <p className="vt-aviso vt-aviso--error" role="alert">
          La detección falló: {deteccion.error?.message}
        </p>
      )}

      {deteccion.isSuccess && (
        <p className="vt-aviso vt-aviso--ok" role="status">
          Detección completada: <strong>{deteccion.data.total_handovers}</strong> handovers
          {deteccion.data.sesiones > 1 ? ` en ${deteccion.data.sesiones} sesiones` : ''} (
          {deteccion.data.duracion_ms} ms).
        </p>
      )}
    </section>
  );
}
