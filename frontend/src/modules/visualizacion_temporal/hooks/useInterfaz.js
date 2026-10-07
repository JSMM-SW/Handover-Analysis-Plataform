/**
 * Comportamiento de interfaz del Módulo 2 (Capa 2): paneles laterales y ayudas contextuales.
 *
 * Nada de esto es lógica de negocio, pero sí es lógica: escuchar el teclado, bloquear el
 * desplazamiento del fondo, devolver el foco. Se saca de los componentes para que estos se
 * limiten a pintar (regla 5 de CLAUDE.md).
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react';

/** Punto de corte en el que la configuración pasa de tarjeta a panel deslizante. */
export const CONSULTA_MOVIL = '(max-width: 899px)';

function esPantallaEstrecha() {
  return typeof window !== 'undefined' && window.matchMedia?.(CONSULTA_MOVIL).matches;
}

/**
 * Panel lateral (drawer) accesible.
 *
 * - `Escape` lo cierra.
 * - Mientras está abierto en una pantalla estrecha, el fondo no se desplaza.
 * - Al abrirse, el foco entra en el panel; al cerrarse, vuelve a donde estaba.
 *
 * @param {boolean} abierto
 * @param {() => void} alCerrar
 * @param {{soloMovil?: boolean}} [opciones]  `soloMovil`: en escritorio el panel está siempre
 *   visible (la configuración), así que no se bloquea el fondo ni se mueve el foco.
 * @returns {import('react').RefObject<HTMLElement>} referencia para el contenedor del panel
 */
export function usePanelLateral(abierto, alCerrar, { soloMovil = false } = {}) {
  const referencia = useRef(null);

  useEffect(() => {
    if (!abierto) return undefined;
    if (soloMovil && !esPantallaEstrecha()) return undefined;

    const focoPrevio = document.activeElement;
    const overflowPrevio = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const alPulsar = (evento) => {
      if (evento.key === 'Escape') alCerrar();
    };
    document.addEventListener('keydown', alPulsar);

    // Se enfoca el propio panel (tabIndex=-1) y no su primer control: así el lector de pantalla
    // anuncia el título antes de caer en un campo concreto.
    referencia.current?.focus?.({ preventScroll: true });

    return () => {
      document.body.style.overflow = overflowPrevio;
      document.removeEventListener('keydown', alPulsar);
      focoPrevio?.focus?.({ preventScroll: true });
    };
  }, [abierto, alCerrar, soloMovil]);

  return referencia;
}

/**
 * Ayuda contextual («?»): se abre al pasar el ratón, al enfocar con teclado o al tocar, y se
 * cierra con `Escape` o al salir.
 *
 * El texto de la ayuda **solo se monta mientras está abierta**. Así no duplica en el DOM palabras
 * que ya aparecen en la interfaz (un «Intra-frecuencia» escondido confundiría a los lectores de
 * pantalla y a las pruebas que buscan ese texto).
 */
export function useAyudaContextual() {
  const [abierta, setAbierta] = useState(false);
  const id = useId();

  const abrir = useCallback(() => setAbierta(true), []);
  const cerrar = useCallback(() => setAbierta(false), []);

  useEffect(() => {
    if (!abierta) return undefined;
    const alPulsar = (evento) => {
      if (evento.key === 'Escape') setAbierta(false);
    };
    document.addEventListener('keydown', alPulsar);
    return () => document.removeEventListener('keydown', alPulsar);
  }, [abierta]);

  return {
    abierta,
    idTooltip: `ayuda-${id}`,
    disparador: {
      onMouseEnter: abrir,
      onMouseLeave: cerrar,
      onFocus: abrir,
      onBlur: cerrar,
      // En táctil no hay hover: el toque abre y tocar fuera (blur) cierra. No se alterna, porque
      // el clic llega justo después del foco y cerraría lo que el foco acaba de abrir.
      onClick: abrir,
    },
  };
}

/**
 * Desplegable propio (p. ej. el selector de varias sesiones): se cierra al hacer clic fuera o
 * con `Escape`, que es lo que el usuario espera de un `<select>` nativo.
 *
 * @returns {{abierto: boolean, alternar: () => void, cerrar: () => void,
 *   referencia: import('react').RefObject<HTMLElement>}}
 */
export function useDesplegable() {
  const [abierto, setAbierto] = useState(false);
  const referencia = useRef(null);

  const cerrar = useCallback(() => setAbierto(false), []);
  const alternar = useCallback(() => setAbierto((valor) => !valor), []);

  useEffect(() => {
    if (!abierto) return undefined;

    const alPulsarFuera = (evento) => {
      if (!referencia.current?.contains(evento.target)) setAbierto(false);
    };
    const alPulsarTecla = (evento) => {
      if (evento.key === 'Escape') setAbierto(false);
    };

    document.addEventListener('mousedown', alPulsarFuera);
    document.addEventListener('keydown', alPulsarTecla);
    return () => {
      document.removeEventListener('mousedown', alPulsarFuera);
      document.removeEventListener('keydown', alPulsarTecla);
    };
  }, [abierto]);

  return { abierto, alternar, cerrar, referencia };
}

/**
 * Devuelve `valor` con un pequeño retraso: solo cuando deja de cambiar durante `ms` milisegundos.
 *
 * Lo usa el deslizador del histograma: mientras se arrastra, el rótulo se actualiza al instante,
 * pero la consulta al backend solo sale cuando el usuario se detiene un momento. Sin esto se
 * lanzaría una petición por cada minuto que cruza la bolita.
 */
export function useValorDiferido(valor, ms = 250) {
  const [diferido, setDiferido] = useState(valor);

  useEffect(() => {
    const id = setTimeout(() => setDiferido(valor), ms);
    return () => clearTimeout(id);
  }, [valor, ms]);

  return diferido;
}

/**
 * Indica si un aviso pasajero debe verse: se muestra al aparecer `clave` y se oculta solo
 * pasados `ms` milisegundos. Una `clave` nueva (otro aviso) lo vuelve a mostrar.
 *
 * @param {unknown} clave  identifica el aviso actual; `null` si no hay ninguno
 * @param {number} [ms]
 */
export function useAvisoTemporal(clave, ms = 3000) {
  const [vencida, setVencida] = useState(null);

  useEffect(() => {
    if (clave === null || clave === undefined) return undefined;
    const id = setTimeout(() => setVencida(clave), ms);
    return () => clearTimeout(id);
  }, [clave, ms]);

  return clave !== null && clave !== undefined && vencida !== clave;
}
