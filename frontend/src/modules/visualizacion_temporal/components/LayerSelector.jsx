/**
 * Barra de herramientas del timeline: capas visibles — HU-C2-004 CA3.
 *
 * Hace a la vez de **selector** y de **leyenda**: cada parámetro lleva su punto de color, el mismo
 * que su línea en la gráfica (mapa único de `types/`). Por eso el gráfico no dibuja leyenda propia:
 * serían dos leyendas diciendo lo mismo.
 *
 * Un parámetro sin ninguna medida en la sesión se puede seleccionar igualmente, pero se marca
 * como «sin datos»: ocultarlo escondería la información de que no se midió (decisión D-5).
 */

import { IconoLibro } from './Iconos.jsx';
import { useVisStore } from '../store/visStore.js';
import { ETIQUETAS_RF, PARAMETROS_RF } from '../types/index.js';

export default function LayerSelector({ cobertura = [] }) {
  const capas = useVisStore((e) => e.capas);
  const toggleCapa = useVisStore((e) => e.toggleCapa);
  const setCapas = useVisStore((e) => e.setCapas);
  const activarTodas = useVisStore((e) => e.activarTodasLasCapas);
  const setGlosario = useVisStore((e) => e.setGlosario);

  const disponibilidad = new Map(cobertura.map((c) => [c.parametro, c]));
  const todasActivas = PARAMETROS_RF.every((p) => capas[p]);

  const alternarTodas = () => {
    if (todasActivas) {
      // Se apagan todos los parámetros pero se conservan los marcadores: son otra cosa.
      setCapas(Object.fromEntries(PARAMETROS_RF.map((p) => [p, false])));
    } else {
      activarTodas();
    }
  };

  return (
    <div className="vt-barra-herramientas" role="toolbar" aria-label="Capas visibles del timeline">
      <div className="vt-capas" role="group" aria-label="Parámetros de radiofrecuencia">
        <button
          type="button"
          className={`vt-capa vt-capa--todos${todasActivas ? ' vt-capa--activa' : ''}`}
          onClick={alternarTodas}
          aria-pressed={todasActivas}
        >
          Todos
        </button>

        {PARAMETROS_RF.map((parametro) => {
          const meta = ETIQUETAS_RF[parametro];
          const info = disponibilidad.get(parametro);
          const sinDatos = info ? !info.disponible : false;
          const activa = Boolean(capas[parametro]);

          return (
            <button
              key={parametro}
              type="button"
              className={`vt-capa${activa ? ' vt-capa--activa' : ''}${sinDatos ? ' vt-capa--sin-datos' : ''}`}
              onClick={() => toggleCapa(parametro)}
              title={
                sinDatos
                  ? `${meta.etiqueta}: el terminal no entregó este parámetro en esta sesión`
                  : meta.etiqueta
              }
              aria-pressed={activa}
            >
              <span
                className="vt-capa__color"
                style={{ '--vt-color-capa': meta.color }}
                aria-hidden="true"
              />
              {meta.corta}
              {sinDatos && <span className="vt-capa__aviso"> · sin datos</span>}
            </button>
          );
        })}
      </div>

      <button
        type="button"
        className="vt-boton vt-boton--texto vt-boton--pequeno"
        onClick={() => setGlosario(true)}
      >
        <IconoLibro tamano={15} />
        ¿Qué mide cada uno?
      </button>

      <span className="vt-barra-herramientas__separador" aria-hidden="true" />

      {/* Interruptor: es un encendido/apagado, no una capa de datos más. */}
      <button
        type="button"
        role="switch"
        className={`vt-interruptor${capas.marcadoresHO ? ' vt-interruptor--activo' : ''}`}
        onClick={() => toggleCapa('marcadoresHO')}
        aria-checked={Boolean(capas.marcadoresHO)}
        title="Líneas verticales en cada handover detectado"
      >
        <span className="vt-interruptor__pista" aria-hidden="true">
          <span className="vt-interruptor__bola" />
        </span>
        Marcadores HO
      </button>
    </div>
  );
}
