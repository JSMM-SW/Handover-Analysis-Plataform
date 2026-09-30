/**
 * Raíz de la aplicación: conmutador entre los módulos de la plataforma.
 *
 * Hasta ahora `App` renderizaba `<IngestaPage />` directamente, así que no había forma de que
 * convivieran dos módulos. Se introduce una navegación **mínima por pestañas** en lugar de React
 * Router: el proyecto no tiene router instalado y con dos módulos no compensa añadir la
 * dependencia y su configuración. Cuando entren los módulos 3 y 4 será el momento de valorarlo.
 *
 * La pestaña activa se guarda en el hash de la URL (`#/visualizacion-temporal`) para que se pueda
 * compartir un enlace y sobreviva a un refresco.
 */

import { useEffect, useState } from 'react';

import IngestaPage from './modules/ingesta/IngestaPage.jsx';
import VisualizacionTemporalPage from './modules/visualizacion_temporal/index.jsx';
import './App.css';

const MODULOS = [
  {
    id: 'ingesta',
    etiqueta: 'Ingesta de datos',
    descripcion: 'Carga y procesamiento de archivos de medición',
    Componente: IngestaPage,
  },
  {
    id: 'visualizacion-temporal',
    etiqueta: 'Visualización temporal',
    descripcion: 'Handovers y parámetros de radiofrecuencia en el tiempo',
    Componente: VisualizacionTemporalPage,
  },
];

const POR_DEFECTO = 'visualizacion-temporal';

function moduloDelHash() {
  const id = window.location.hash.replace(/^#\/?/, '');
  return MODULOS.some((m) => m.id === id) ? id : POR_DEFECTO;
}

export default function App() {
  const [moduloActivo, setModuloActivo] = useState(moduloDelHash);

  // Mantiene sincronizada la pestaña con el botón atrás del navegador.
  useEffect(() => {
    const alCambiarHash = () => setModuloActivo(moduloDelHash());
    window.addEventListener('hashchange', alCambiarHash);
    return () => window.removeEventListener('hashchange', alCambiarHash);
  }, []);

  const seleccionar = (id) => {
    window.location.hash = `#/${id}`;
    setModuloActivo(id);
  };

  const { Componente } = MODULOS.find((m) => m.id === moduloActivo) ?? MODULOS[0];

  return (
    <div className="app">
      <nav className="app-nav" aria-label="Módulos de la plataforma">
        <span className="app-nav__marca">Plataforma de Análisis de Handovers</span>
        <ul className="app-nav__lista">
          {MODULOS.map((m) => (
            <li key={m.id}>
              <button
                type="button"
                className={`app-nav__boton${moduloActivo === m.id ? ' app-nav__boton--activo' : ''}`}
                onClick={() => seleccionar(m.id)}
                aria-current={moduloActivo === m.id ? 'page' : undefined}
                title={m.descripcion}
              >
                {m.etiqueta}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <Componente />
    </div>
  );
}
