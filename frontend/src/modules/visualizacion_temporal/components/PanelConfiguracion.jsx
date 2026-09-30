/**
 * Contenedor responsivo de la configuración del análisis.
 *
 * - **Escritorio (≥ 900 px):** la tarjeta de configuración se ve siempre, encima del contenido.
 * - **Tablet y móvil (< 900 px):** la misma tarjeta pasa a un panel lateral que se abre con el
 *   botón «Configurar análisis». Así las gráficas ocupan la pantalla entera y los filtros siguen
 *   a un toque de distancia.
 *
 * Es un único `<FiltersHeader />` en los dos casos: lo que cambia es solo la presentación (CSS),
 * de modo que no hay dos copias de los controles que puedan desincronizarse.
 */

import FiltersHeader from './FiltersHeader.jsx';
import { IconoCerrar } from './Iconos.jsx';
import { usePanelLateral } from '../hooks/useInterfaz.js';
import { useVisStore } from '../store/visStore.js';

export default function PanelConfiguracion() {
  const abierto = useVisStore((e) => e.panelConfiguracionAbierto);
  const setPanel = useVisStore((e) => e.setPanelConfiguracion);
  const haySesion = useVisStore((e) => e.sesionIds.length > 0);

  const cerrar = () => setPanel(false);
  const referencia = usePanelLateral(abierto, cerrar, { soloMovil: true });

  return (
    <>
      {/* Velo: solo existe visualmente en pantallas estrechas con el panel abierto. */}
      <div
        className={`vt-velo vt-velo--config${abierto ? ' vt-velo--visible' : ''}`}
        onClick={cerrar}
        aria-hidden="true"
      />

      <aside
        ref={referencia}
        id="vt-panel-configuracion"
        className={`vt-panel-config${abierto ? ' vt-panel-config--abierto' : ''}`}
        aria-label="Configuración del análisis"
        tabIndex={-1}
      >
        <div className="vt-panel-config__barra">
          <span className="vt-panel-config__titulo">Configurar análisis</span>
          <button
            type="button"
            className="vt-boton vt-boton--icono vt-boton--fantasma"
            onClick={cerrar}
            aria-label="Cerrar la configuración"
          >
            <IconoCerrar />
          </button>
        </div>

        <FiltersHeader />

        <div className="vt-panel-config__pie">
          <button
            type="button"
            className="vt-boton vt-boton--primario vt-boton--bloque"
            onClick={cerrar}
            disabled={!haySesion}
          >
            Ver resultados
          </button>
        </div>
      </aside>
    </>
  );
}
