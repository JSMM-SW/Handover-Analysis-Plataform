import { useLayoutEffect, useState } from 'react';
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import IngestaPage from './modules/ingesta/IngestaPage';
import KpisDashboard from './modules/kpis/KpisDashboard';
import GeoespacialPage from './modules/visualizacion_geoespacial/GeoespacialPage';
import VisualizacionTemporalPage from './modules/visualizacion_temporal';
import './App.css';
import logo from './assets/logo.png';

const MODULE_PATHS = ['/ingesta', '/kpis', '/geoespacial', '/visualizacion-temporal'];
const CLAVE_TEMA = 'handover-analysis-tema';

function temaInicial() {
  try {
    const guardado = localStorage.getItem(CLAVE_TEMA);
    if (guardado === 'claro' || guardado === 'oscuro') return guardado;
  } catch {
    // localStorage puede fallar (modo privado, cookies bloqueadas) -- se
    // sigue de largo con la preferencia del sistema como respaldo.
  }
  const prefiereOscuro = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  return prefiereOscuro ? 'oscuro' : 'claro';
}

function ModuleRoutes() {
  const { hash } = useLocation();
  // Preserve URLs shared by the temporal module before the common router existed.
  const legacyPath = '/' + hash.replace(/^#\/?/, '');
  if (MODULE_PATHS.includes(legacyPath)) return <Navigate to={legacyPath} replace />;

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/ingesta" replace />} />
      <Route path="/ingesta" element={<IngestaPage />} />
      <Route path="/kpis" element={<KpisDashboard />} />
      <Route path="/geoespacial" element={<GeoespacialPage />} />
      <Route path="/visualizacion-temporal" element={<VisualizacionTemporalPage />} />
      <Route path="*" element={<p>Página no encontrada. Usa el menú para continuar.</p>} />
    </Routes>
  );
}

export default function App() {
  const [tema, setTema] = useState(temaInicial);

  // useLayoutEffect (no useEffect) a propósito: debe fijar data-tema en
  // <html> ANTES de que otros componentes (ej. los hooks usarColorDeTema
  // de KpisDashboard) lean getComputedStyle en su propio primer efecto.
  // Con useEffect normal hay una carrera: los efectos de los hijos corren
  // antes que el de App, así que leerían el tema por defecto del CSS en
  // vez del real guardado en localStorage/sistema.
  useLayoutEffect(() => {
    document.documentElement.dataset.tema = tema;
    try {
      localStorage.setItem(CLAVE_TEMA, tema);
    } catch {
      // Sin persistencia no pasa nada grave -- el tema solo dura la sesión.
    }
  }, [tema]);

  const alternarTema = () => {
    setTema((actual) => (actual === 'oscuro' ? 'claro' : 'oscuro'));
  };

  return (
    <BrowserRouter>
      <div className="app-layout">
        <aside className="app-sidebar">
                    <img src={logo} alt="H Analytics" className="app-brand-logo" />

          <p>Plataforma de handovers</p>
          <nav aria-label="Menú principal">
            <NavLink to="/ingesta">Ingesta</NavLink>
            <NavLink to="/kpis">KPIs</NavLink>
            <NavLink to="/geoespacial">Geoespacial</NavLink>
            <NavLink to="/visualizacion-temporal">Visualización temporal</NavLink>
          </nav>
          <button
            type="button"
            className="app-theme-toggle"
            onClick={alternarTema}
            aria-pressed={tema === 'oscuro'}
          >
            {tema === 'oscuro' ? 'Modo claro' : 'Modo oscuro'}
          </button>
          <small>Mediciones de redes celulares</small>
        </aside>
        <main className="app-content"><ModuleRoutes /></main>
      </div>
    </BrowserRouter>
  );
}
