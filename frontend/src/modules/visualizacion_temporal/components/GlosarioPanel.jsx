/**
 * Panel lateral de glosario.
 *
 * Reúne en un solo sitio todas las definiciones que aparecen sueltas en las ayudas «?». Está
 * pensado para un docente que quiere repasar los conceptos antes de explicarlos en clase, o
 * mientras mira una gráfica sin perderla de vista (el panel no tapa toda la pantalla en escritorio).
 *
 * El contenido solo se monta con el panel abierto: no tiene sentido que decenas de definiciones
 * vivan en el DOM mientras nadie las mira.
 */

import { IconoCerrar, IconoLibro } from './Iconos.jsx';
import { usePanelLateral } from '../hooks/useInterfaz.js';
import { useVisStore } from '../store/visStore.js';
import { GRUPOS_GLOSARIO, entradasDeGrupo } from '../types/glosario.js';

export default function GlosarioPanel() {
  const abierto = useVisStore((e) => e.glosarioAbierto);
  const setGlosario = useVisStore((e) => e.setGlosario);

  const cerrar = () => setGlosario(false);
  const referencia = usePanelLateral(abierto, cerrar);

  return (
    <>
      <div
        className={`vt-velo${abierto ? ' vt-velo--visible' : ''}`}
        onClick={cerrar}
        aria-hidden="true"
      />

      <aside
        ref={referencia}
        className={`vt-glosario${abierto ? ' vt-glosario--abierto' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="vt-glosario-titulo"
        aria-hidden={!abierto}
        tabIndex={-1}
      >
        {abierto && (
          <>
            <div className="vt-glosario__cabecera">
              <span className="vt-config__icono">
                <IconoLibro />
              </span>
              <div>
                <h2 id="vt-glosario-titulo" className="vt-glosario__titulo">
                  Glosario
                </h2>
                <p className="vt-glosario__subtitulo">
                  Los conceptos de esta pantalla, explicados sin tecnicismos.
                </p>
              </div>
              <button
                type="button"
                className="vt-boton vt-boton--icono vt-boton--fantasma"
                onClick={cerrar}
                aria-label="Cerrar el glosario"
              >
                <IconoCerrar />
              </button>
            </div>

            <div className="vt-glosario__contenido">
              {GRUPOS_GLOSARIO.map((grupo) => (
                <section key={grupo.id} className="vt-glosario__grupo">
                  <h3 className="vt-glosario__grupo-titulo">{grupo.titulo}</h3>
                  <dl className="vt-glosario__lista">
                    {entradasDeGrupo(grupo.id).map((entrada) => (
                      <div key={entrada.clave} className="vt-glosario__entrada">
                        <dt>{entrada.titulo}</dt>
                        <dd>
                          {entrada.breve}
                          {entrada.detalle && (
                            <span className="vt-glosario__detalle">{entrada.detalle}</span>
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </section>
              ))}
            </div>
          </>
        )}
      </aside>
    </>
  );
}
