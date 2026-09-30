import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import IngestaPage from './modules/ingesta/IngestaPage';
import GeoespacialPage from './modules/visualizacion_geoespacial/GeoespacialPage';
import VisualizacionTemporalPage from './modules/visualizacion_temporal';
import './App.css';

const MODULE_PATHS = ['/ingesta', '/geoespacial', '/visualizacion-temporal'];

function ModuleRoutes() {
  const { hash } = useLocation();
  // Preserve URLs shared by the temporal module before the common router existed.
  const legacyPath = '/' + hash.replace(/^#\/?/, '');
  if (MODULE_PATHS.includes(legacyPath)) return <Navigate to={legacyPath} replace />;

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/ingesta" replace />} />
      <Route path="/ingesta" element={<IngestaPage />} />
      <Route path="/geoespacial" element={<GeoespacialPage />} />
      <Route path="/visualizacion-temporal" element={<VisualizacionTemporalPage />} />
      <Route path="*" element={<p>Página no encontrada. Usa el menú para continuar.</p>} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <aside className="app-sidebar">
          <div className="app-brand">H<span> / </span>ANALYSIS</div>
          <p>Plataforma de handovers</p>
          <nav aria-label="Menú principal">
            <NavLink to="/ingesta">Ingesta</NavLink>
            <NavLink to="/geoespacial">Geoespacial</NavLink>
            <NavLink to="/visualizacion-temporal">Visualización temporal</NavLink>
          </nav>
          <small>Mediciones de redes celulares</small>
        </aside>
        <main className="app-content"><ModuleRoutes /></main>
      </div>
    </BrowserRouter>
  );
}
