/**
 * Página del Módulo 2 — Visualización temporal de handovers.
 *
 * Estructura V1 (`docs/00-contexto.md`). Comparte el sistema visual del resto de la plataforma
 * (variables globales de tema en `src/index.css`). El recorrido de lectura va de lo general a lo
 * particular:
 *
 * 1. Configuración del análisis (qué sesiones y qué parte).
 * 2. Resumen en tarjetas.
 * 3. Eventos de handover: tabla y detalle en **una misma sección**.
 * 4. Con varias sesiones, cuál muestran las gráficas.
 * 5. Línea de tiempo y secuencia de radiobases, alineadas.
 * 6. Radiobases repetidas.
 *
 * **Tabla y detalle se alternan, no se apilan.** La sección arranca plegada con el primer evento
 * elegido y su gráfica a la vista; elegir otro evento muestra el suyo, y «Desplegar» vuelve a la
 * tabla completa y oculta el detalle. Así nunca aparece un detalle suelto más abajo que obligue a
 * desplazarse para encontrarlo.
 *
 * **Las gráficas de abajo no siguen a la tabla.** Elegir un evento lo resalta en la línea de
 * tiempo y en la secuencia de radiobases, pero no las amplía: siempre muestran el recorrido
 * completo, salvo que el usuario haga zoom.
 */

import AyudaContextual from './components/AyudaContextual.jsx';
import CellSequenceChart from './components/CellSequenceChart.jsx';
import EnfoqueSesion from './components/EnfoqueSesion.jsx';
import GlosarioPanel from './components/GlosarioPanel.jsx';
import HandoverDetailPanel from './components/HandoverDetailPanel.jsx';
import HandoverTable from './components/HandoverTable.jsx';
import { IconoAjustes, IconoLibro } from './components/Iconos.jsx';
import PanelConfiguracion from './components/PanelConfiguracion.jsx';
import RepeatedCellsHistogram from './components/RepeatedCellsHistogram.jsx';
import SummaryCards from './components/SummaryCards.jsx';
import TimelineChart from './components/TimelineChart.jsx';
import { useNumeroFiltrosActivos, useVisStore } from './store/visStore.js';
import './VisualizacionTemporalPage.css';

/** Tarjeta de sección con título, ayuda breve y, si procede, un término del glosario. */
function Seccion({ titulo, ayuda, termino, children, className = '' }) {
  return (
    <section className={`vt-seccion ${className}`.trim()}>
      <div className="vt-seccion__cabecera">
        <h2 className="vt-seccion__titulo">
          {titulo}
          {termino && <AyudaContextual termino={termino} />}
        </h2>
        {ayuda && <p className="vt-seccion__ayuda">{ayuda}</p>}
      </div>
      {children}
    </section>
  );
}

/** Estado inicial: sin sesión todavía. Explica en tres pasos cómo empezar. */
function Bienvenida() {
  const setPanel = useVisStore((e) => e.setPanelConfiguracion);

  return (
    <div className="vt-bienvenida">
      <h2 className="vt-bienvenida__titulo">Empecemos por elegir un recorrido</h2>
      <p className="vt-bienvenida__texto">
        Esta herramienta muestra cómo cambió la conexión de un teléfono mientras se desplazaba.
      </p>
      <ol className="vt-bienvenida__pasos">
        <li>
          <span className="vt-bienvenida__numero">1</span>
          <span>
            <strong>Elige una o varias sesiones</strong> en «Configuración del análisis».
          </span>
        </li>
        <li>
          <span className="vt-bienvenida__numero">2</span>
          <span>
            Los <strong>handovers se detectan solos</strong> al elegir la sesión.
          </span>
        </li>
        <li>
          <span className="vt-bienvenida__numero">3</span>
          <span>
            <strong>Explora</strong> la línea de tiempo y haz clic en un evento para ver el detalle.
          </span>
        </li>
      </ol>
      <button
        type="button"
        className="vt-boton vt-boton--primario vt-solo-movil"
        onClick={() => setPanel(true)}
      >
        <IconoAjustes tamano={16} />
        Elegir sesión
      </button>
    </div>
  );
}

/**
 * Página principal del módulo: cabecera, panel de configuración y, cuando hay sesión elegida,
 * el resumen, los eventos y las gráficas temporales.
 */
export default function VisualizacionTemporalPage() {
  const haySesion = useVisStore((e) => e.sesionIds.length > 0);
  const seleccionado = useVisStore((e) => e.handoverSeleccionadoId);
  const tablaColapsada = useVisStore((e) => e.tablaColapsada);
  const panelAbierto = useVisStore((e) => e.panelConfiguracionAbierto);
  const setPanel = useVisStore((e) => e.setPanelConfiguracion);
  const setGlosario = useVisStore((e) => e.setGlosario);
  const nFiltros = useNumeroFiltrosActivos();

  // El detalle solo se ve con la tabla plegada. Desplegada, la tabla ocupa toda la sección y el
  // detalle se oculta (el evento sigue seleccionado y resaltado en su fila).
  const mostrarDetalle = Boolean(seleccionado) && tablaColapsada;

  return (
    <div className="vt-pagina">
      <header className="vt-pagina__cabecera">
        <div className="vt-pagina__titulo">
          <h2>Visualización temporal de handovers</h2>
          <p>Evolución de la señal y de la celda servidora a lo largo del recorrido.</p>
        </div>

        <div className="vt-pagina__acciones">
          <button
            type="button"
            className="vt-boton vt-boton--secundario vt-solo-movil"
            onClick={() => setPanel(true)}
            aria-expanded={panelAbierto}
            aria-controls="vt-panel-configuracion"
          >
            <IconoAjustes tamano={16} />
            Configurar análisis
            {nFiltros > 0 && (
              <>
                <span className="vt-insignia" aria-hidden="true">{nFiltros}</span>
                <span className="vt-visualmente-oculto">, {nFiltros} filtros activos</span>
              </>
            )}
          </button>
          <button
            type="button"
            className="vt-boton vt-boton--secundario"
            onClick={() => setGlosario(true)}
          >
            <IconoLibro tamano={16} />
            Glosario
          </button>
        </div>
      </header>

      <PanelConfiguracion />

      {!haySesion ? (
        <Bienvenida />
      ) : (
        <main className="vt-contenido">
          <SummaryCards />

          <Seccion
            titulo="Eventos de handover"
            ayuda={
              mostrarDetalle
                ? 'Elige otro evento de la lista o pulsa «Desplegar» para volver a la tabla completa.'
                : 'Cada fila es un traspaso detectado. Haz clic en una para ver su detalle y su gráfica antes y después del traspaso.'
            }
            termino="handover"
            className={mostrarDetalle ? 'vt-seccion--acento' : ''}
          >
            <div className={`vt-eventos${mostrarDetalle ? ' vt-eventos--con-detalle' : ''}`}>
              <div className="vt-eventos__tabla">
                <HandoverTable />
              </div>

              {mostrarDetalle && (
                <div className="vt-eventos__detalle">
                  <h3 className="vt-eventos__subtitulo">
                    Detalle del handover
                    <AyudaContextual termino="pre_post" />
                  </h3>
                  <HandoverDetailPanel />
                </div>
              )}
            </div>
          </Seccion>

          <EnfoqueSesion />

          {/* Las gráficas ocupan siempre el ancho completo: comprimirlas las vuelve ilegibles. */}
          <Seccion
            titulo="Línea de tiempo"
            ayuda="Evolución de la señal durante todo el recorrido. Cada línea vertical marca un handover; el elegido en la tabla se resalta en otro color."
            termino="handover"
          >
            <TimelineChart />
          </Seccion>

          <Seccion
            titulo="Secuencia de radiobases"
            ayuda="Qué antena daba servicio en cada momento. Cada escalón coincide con un handover."
            termino="radiobase"
          >
            <CellSequenceChart />
          </Seccion>

          <Seccion
            titulo="Radiobases repetidas"
            ayuda="Cuántas veces volvió el teléfono a cada antena. Los valores altos señalan zonas donde varias antenas se solapan."
            termino="visitas"
          >
            <RepeatedCellsHistogram />
          </Seccion>
        </main>
      )}

      <GlosarioPanel />
    </div>
  );
}
