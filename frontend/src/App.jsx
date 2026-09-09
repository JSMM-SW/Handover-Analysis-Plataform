import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import IngestaPage from './modules/ingesta/IngestaPage';
import GeoespacialPage from './modules/visualizacion_geoespacial/GeoespacialPage';
import './App.css';

export default function App() {
  return <BrowserRouter><div className="app-layout">
    <aside className="app-sidebar"><div className="app-brand">H<span> / </span>ANALYSIS</div><p>Plataforma de handovers</p><nav aria-label="Menú principal"><NavLink to="/ingesta">Ingesta</NavLink><NavLink to="/geoespacial">Geoespacial</NavLink></nav><small>Mediciones de redes celulares</small></aside>
    <main className="app-content"><Routes><Route path="/" element={<Navigate to="/ingesta" replace />} /><Route path="/ingesta" element={<IngestaPage />} /><Route path="/geoespacial" element={<GeoespacialPage />} /><Route path="*" element={<p>Página no encontrada. Usa el menú para continuar.</p>} /></Routes></main>
  </div></BrowserRouter>;
}
