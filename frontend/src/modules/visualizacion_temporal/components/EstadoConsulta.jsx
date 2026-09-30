/**
 * Estados transversales de la interfaz: cargando, error y vacío.
 *
 * Centralizados para que las cinco visualizaciones del módulo no inventen cada una su forma de
 * decir lo mismo. Son componentes de presentación pura: no consultan nada.
 */

/** Bloque de carga con el alto reservado, para que el layout no dé saltos al llegar los datos. */
export function Cargando({ mensaje = 'Cargando…', alto = 120 }) {
  return (
    <div className="vt-estado vt-estado--cargando" style={{ minHeight: alto }} role="status">
      <span className="vt-spinner" aria-hidden="true" />
      <span>{mensaje}</span>
    </div>
  );
}

/**
 * Error con el mensaje del backend, que ya viene en español y explica la causa concreta.
 * Mostrarlo tal cual es más útil que un "ha ocurrido un error".
 */
export function ErrorConsulta({ error, onReintentar, alto = 120 }) {
  const mensaje = error?.message ?? 'No se pudo completar la consulta.';

  return (
    <div className="vt-estado vt-estado--error" style={{ minHeight: alto }} role="alert">
      <strong>No se pudieron cargar los datos</strong>
      <span className="vt-estado__detalle">{mensaje}</span>
      {onReintentar && (
        <button type="button" className="vt-boton vt-boton--secundario" onClick={onReintentar}>
          Reintentar
        </button>
      )}
    </div>
  );
}

/** Estado vacío: la consulta fue bien, simplemente no hay nada que mostrar. No es un fallo. */
export function SinResultados({
  titulo = 'Sin resultados',
  mensaje = 'No hay datos para los filtros seleccionados.',
  accion = null,
  alto = 120,
}) {
  return (
    <div className="vt-estado vt-estado--vacio" style={{ minHeight: alto }}>
      <strong>{titulo}</strong>
      <span className="vt-estado__detalle">{mensaje}</span>
      {accion}
    </div>
  );
}

/**
 * Aviso de que un parámetro no tiene ni una medida válida en la sesión.
 *
 * Es la materialización de la decisión D-5: en lugar de pintar una gráfica vacía sin explicación,
 * se dice por qué está vacía. Con el terminal del dataset de referencia, esto es exactamente lo
 * que ocurre con SINR/RSSNR.
 */
export function SinDatosValidos({ cobertura }) {
  if (!cobertura?.length) return null;

  const ausentes = cobertura.filter((c) => !c.disponible);
  if (!ausentes.length) return null;

  return (
    <p className="vt-aviso vt-aviso--sin-datos">
      <strong>Sin datos válidos:</strong>{' '}
      {ausentes.map((c) => c.etiqueta).join(', ')}. El terminal de medición no entregó estos
      parámetros en esta sesión.
    </p>
  );
}
