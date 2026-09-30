/**
 * Iconos de trazo fino del Módulo 2.
 *
 * SVG en línea y dibujados a mano en lugar de una librería de iconos: son una docena, y añadir una
 * dependencia para ellos no compensa. Todos usan `currentColor`, así que toman el color del texto
 * que los rodea, y son decorativos (`aria-hidden`): el significado lo lleva siempre el texto.
 */

function Icono({ children, tamano = 18, className = '' }) {
  return (
    <svg
      className={`vt-icono ${className}`.trim()}
      width={tamano}
      height={tamano}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Dos flechas que se cruzan: el traspaso de una antena a otra. */
export function IconoHandover(props) {
  return (
    <Icono {...props}>
      <path d="M4 8h13l-3-3" />
      <path d="M20 16H7l3 3" />
    </Icono>
  );
}

/** Mástil con ondas: una radiobase. */
export function IconoAntena(props) {
  return (
    <Icono {...props}>
      <path d="M12 11v10" />
      <path d="M9 21h6" />
      <circle cx="12" cy="9" r="1.6" />
      <path d="M8.5 5.5a5 5 0 0 0 0 7" />
      <path d="M15.5 5.5a5 5 0 0 1 0 7" />
    </Icono>
  );
}

/** Recorrido con dos puntos: una sesión de medición. */
export function IconoRecorrido(props) {
  return (
    <Icono {...props}>
      <circle cx="6" cy="18" r="2" />
      <circle cx="18" cy="6" r="2" />
      <path d="M8 18h6a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h6" />
    </Icono>
  );
}

/** Pulso: mediciones tomadas a lo largo del tiempo. */
export function IconoPulso(props) {
  return (
    <Icono {...props}>
      <path d="M3 12h4l2-5 4 10 2-5h6" />
    </Icono>
  );
}

/** Cronómetro: ritmo por minuto. */
export function IconoRitmo(props) {
  return (
    <Icono {...props}>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.5 2" />
      <path d="M10 2h4" />
    </Icono>
  );
}

/** Deslizadores: configuración del análisis. */
export function IconoAjustes(props) {
  return (
    <Icono {...props}>
      <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12" />
      <circle cx="16" cy="6" r="2" />
      <circle cx="10" cy="12" r="2" />
      <circle cx="18" cy="18" r="2" />
    </Icono>
  );
}

/** Libro abierto: glosario. */
export function IconoLibro(props) {
  return (
    <Icono {...props}>
      <path d="M12 6c-2-1.5-5-2-8-1.5V19c3-.5 6 0 8 1.5 2-1.5 5-2 8-1.5V4.5c-3-.5-6 0-8 1.5z" />
      <path d="M12 6v14.5" />
    </Icono>
  );
}

export function IconoCerrar(props) {
  return (
    <Icono {...props}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Icono>
  );
}

/** Destello: acción de detectar. */
export function IconoDestello(props) {
  return (
    <Icono {...props}>
      <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
      <path d="M19 17l.7 1.8 1.8.7-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z" />
    </Icono>
  );
}

export function IconoFlechaIzquierda(props) {
  return (
    <Icono {...props}>
      <path d="M15 6l-6 6 6 6" />
    </Icono>
  );
}

export function IconoFlechaDerecha(props) {
  return (
    <Icono {...props}>
      <path d="M9 6l6 6-6 6" />
    </Icono>
  );
}
