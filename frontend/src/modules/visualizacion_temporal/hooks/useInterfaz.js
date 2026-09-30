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
 * Abre el calendario (o el reloj) nativo al pulsar **en cualquier parte** del campo, no solo en
 * el icono. `showPicker` puede lanzar si el navegador no lo permite en ese momento: entonces el
 * campo se comporta como siempre y el usuario puede escribir la fecha.
 */
export function abrirSelectorNativo(evento) {
  try {
    evento.currentTarget.showPicker?.();
  } catch {
    // Sin soporte o sin gesto de usuario válido: no hay nada que hacer.
  }
}

/**
 * Comportamiento de `CampoHora`: texto con marcador de ejemplo mientras está vacío y sin foco;
 * campo de hora nativo en cuanto el usuario lo pulsa o ya tiene un valor.
 *
 * El reloj se abre justo después del cambio de tipo (en el siguiente fotograma), porque
 * `showPicker` solo funciona sobre un campo que ya es `type="time"`.
 */
export function useCampoHora(valor) {
  const [enfocado, setEnfocado] = useState(false);
  const referencia = useRef(null);

  const tipo = valor || enfocado ? 'time' : 'text';

  useEffect(() => {
    if (!enfocado) return undefined;
    const id = requestAnimationFrame(() => {
      try {
        referencia.current?.showPicker?.();
      } catch {
        // Sin soporte o sin gesto válido: se puede escribir la hora igualmente.
      }
    });
    return () => cancelAnimationFrame(id);
  }, [enfocado]);

  return {
    tipo,
    referencia,
    alEnfocar: () => setEnfocado(true),
    alSalir: () => setEnfocado(false),
  };
}
