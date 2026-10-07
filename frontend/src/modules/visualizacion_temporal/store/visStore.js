/**
 * Estado del cliente del Módulo 2 (Zustand).
 *
 * Separación clave (`docs/02-arquitectura.md`):
 * - **Zustand** guarda lo que el usuario ha *elegido*: filtros, selección, capas, ventana.
 * - **TanStack Query** guarda lo que viene del *servidor*. Aquí no se copia ni un dato remoto.
 *
 * El objeto de filtros derivado de este store es la **query key** de TanStack Query. Cuando el
 * usuario toca un filtro, la key cambia y las consultas se relanzan solas: así se cumple el
 * criterio 1 de HU-C2-006 sin escribir código de refresco.
 */

import { useMemo } from 'react';
import { create } from 'zustand';

import { PARAMETROS_RF } from '../types/index.js';

/** Capas visibles del timeline. Arrancan solo con RSSI: es el parámetro mejor cubierto. */
const CAPAS_INICIALES = {
  rsrp_dbm: false,
  rsrq_db: false,
  rssnr_db: false,
  rssi_dbm: true,
  marcadoresHO: true,
};

const ESTADO_INICIAL = {
  // --- Filtros (HU-C2-006) ---
  // Se pueden analizar varias sesiones a la vez; la lista vacía significa «ninguna elegida».
  sesionIds: [],
  desde: null,
  hasta: null,
  horaInicio: null,
  horaFin: null,
  tecnologias: [],

  // --- Visualización ---
  capas: { ...CAPAS_INICIALES },

  // --- Selección y detalle ---
  handoverSeleccionadoId: null,
  // Mientras sea cierto, el primer handover que llegue se selecciona solo. Se activa al elegir
  // sesiones o cambiar un filtro, y se apaga en cuanto hay un evento elegido (por el usuario o
  // por defecto). Así un usuario que despliega la tabla o elige otro evento no se ve corregido.
  seleccionPendiente: true,
  ventanaSegundos: 5,
  parametroDetalle: 'todos',

  // --- Sesión que muestran las gráficas temporales ---
  // Con varias sesiones de fechas lejanas, un eje de tiempo común las deja como dos rayas en los
  // extremos. `null` muestra todas; un id muestra solo esa sesión en las gráficas.
  sesionEnfocada: null,

  // --- Detección automática ---
  // Sesiones cuya detección ya se lanzó desde que se abrió la página. Al elegir una sesión que no
  // está aquí, se detectan sus handovers sin que el usuario tenga que pulsar nada; volver a
  // elegirla no repite la detección.
  sesionesDetectadas: [],

  // --- Zoom compartido entre gráficas ---
  rangoZoom: null, // [isoInicio, isoFin]

  // --- Disposición ---
  // Plegada, la tabla se reduce a una lista compacta y a su lado se ve el detalle del handover
  // elegido. Desplegada, se ve la tabla completa y el detalle se oculta. Arranca plegada: lo
  // primero que se ve es el primer handover con su gráfica.
  tablaColapsada: true,

  // --- Paneles laterales ---
  // En pantallas estrechas la configuración del análisis vive en un panel deslizante; en
  // escritorio se ve siempre y este indicador no tiene efecto visual.
  panelConfiguracionAbierto: false,
  glosarioAbierto: false,
};

/**
 * Lo que se reinicia cuando cambia lo que se analiza: el evento elegido y el zoom pertenecen a
 * unos datos concretos, y arrastrarlos a otros dejaría la interfaz mostrando un detalle que no
 * corresponde. La selección queda pendiente para que el primer evento nuevo se elija solo.
 */
const SELECCION_REINICIADA = {
  handoverSeleccionadoId: null,
  seleccionPendiente: true,
  rangoZoom: null,
};

/** Filtros vacíos. */
const SIN_FILTROS = {
  desde: null,
  hasta: null,
  horaInicio: null,
  horaFin: null,
  tecnologias: [],
};

export const useVisStore = create((set, get) => ({
  ...ESTADO_INICIAL,

  /**
   * Fija las sesiones a analizar.
   *
   * Además de la selección y el zoom, **vacía los filtros**: el calendario, las horas y las
   * tecnologías que se ofrecen dependen de las sesiones elegidas, y un filtro puesto para otras
   * podría quedar fuera de lo que ahora existe. La tabla vuelve a plegarse con el primer evento.
   *
   * Con varias sesiones, las gráficas enfocan una (la que ya lo estaba o la primera): verlas
   * todas en un mismo eje solo sirve si son de fechas cercanas.
   */
  setSesiones: (sesionIds) => {
    const ids = [...new Set(sesionIds.filter(Boolean))];
    const enfocada = get().sesionEnfocada;
    set({
      sesionIds: ids,
      ...SIN_FILTROS,
      ...SELECCION_REINICIADA,
      tablaColapsada: true,
      sesionEnfocada: ids.length > 1 ? (ids.includes(enfocada) ? enfocada : ids[0]) : null,
    });
  },

  /** Analiza una única sesión (o ninguna con `null`). Atajo sobre `setSesiones`. */
  setSesion: (sesionId) => get().setSesiones(sesionId ? [sesionId] : []),

  /** Añade o quita una sesión del análisis. */
  toggleSesion: (sesionId) => {
    const { sesionIds, setSesiones } = get();
    setSesiones(
      sesionIds.includes(sesionId)
        ? sesionIds.filter((s) => s !== sesionId)
        : [...sesionIds, sesionId],
    );
  },

  // Cada filtro cambia la lista de eventos: el elegido puede quedar fuera, así que la selección
  // se reinicia y se elige otra vez el primero de la lista nueva.
  setRangoFecha: (desde, hasta) =>
    set({ desde: desde || null, hasta: hasta || null, ...SELECCION_REINICIADA }),

  setRangoHora: (horaInicio, horaFin) =>
    set({ horaInicio: horaInicio || null, horaFin: horaFin || null, ...SELECCION_REINICIADA }),

  toggleTecnologia: (tecnologia) =>
    set((estado) => ({
      tecnologias: estado.tecnologias.includes(tecnologia)
        ? estado.tecnologias.filter((t) => t !== tecnologia)
        : [...estado.tecnologias, tecnologia],
      ...SELECCION_REINICIADA,
    })),

  setTecnologias: (tecnologias) => set({ tecnologias: [...tecnologias], ...SELECCION_REINICIADA }),

  /** Elige qué sesión muestran las gráficas temporales (`null` = todas). */
  setSesionEnfocada: (sesionEnfocada) => set({ sesionEnfocada, rangoZoom: null }),

  toggleCapa: (capa) =>
    set((estado) => ({ capas: { ...estado.capas, [capa]: !estado.capas[capa] } })),

  setCapas: (capas) => set((estado) => ({ capas: { ...estado.capas, ...capas } })),

  /** Activa todas las capas de parámetros RF (el botón "Todos" del selector de capas). */
  activarTodasLasCapas: () =>
    set((estado) => ({
      capas: {
        ...estado.capas,
        ...Object.fromEntries(PARAMETROS_RF.map((p) => [p, true])),
      },
    })),

  /**
   * Selecciona un handover para analizarlo en detalle.
   *
   * Seleccionar **siempre pliega** la tabla: el detalle solo se muestra con la tabla plegada, así
   * que elegir un evento (también el mismo otra vez, tras desplegar) es la forma de verlo.
   *
   * No toca el zoom: las gráficas de abajo siguen mostrando el recorrido completo.
   */
  seleccionarHandover: (handoverSeleccionadoId) =>
    set({
      handoverSeleccionadoId,
      seleccionPendiente: false,
      tablaColapsada: Boolean(handoverSeleccionadoId),
    }),

  /**
   * Elige el evento que se muestra por defecto (el primero de la lista). A diferencia de
   * `seleccionarHandover`, respeta cómo tenga el usuario la tabla.
   */
  seleccionarPorDefecto: (handoverSeleccionadoId) =>
    set({ handoverSeleccionadoId, seleccionPendiente: false }),

  /** Olvida el evento elegido para que se vuelva a elegir el primero (p. ej. tras redetectar). */
  reiniciarSeleccion: () => set(SELECCION_REINICIADA),

  /** Anota que la detección de estas sesiones ya se lanzó, para no repetirla. */
  marcarDetectadas: (sesionIds) =>
    set((estado) => ({
      sesionesDetectadas: [...new Set([...estado.sesionesDetectadas, ...sesionIds])],
    })),

  setVentana: (ventanaSegundos) => set({ ventanaSegundos }),

  setParametroDetalle: (parametroDetalle) => set({ parametroDetalle }),

  setRangoZoom: (rangoZoom) => set({ rangoZoom }),

  toggleTablaColapsada: () => set((estado) => ({ tablaColapsada: !estado.tablaColapsada })),

  /** Despliega la tabla completa. El detalle se oculta, pero el evento sigue seleccionado. */
  desplegarTabla: () => set({ tablaColapsada: false }),

  /**
   * Abre o cierra el panel de configuración. Abrirlo cierra el glosario: dos paneles laterales a
   * la vez taparían el contenido en un móvil.
   */
  setPanelConfiguracion: (abierto) =>
    set((estado) => ({
      panelConfiguracionAbierto: abierto,
      glosarioAbierto: abierto ? false : estado.glosarioAbierto,
    })),

  /** Abre o cierra el glosario; por la misma razón, cierra el panel de configuración. */
  setGlosario: (abierto) =>
    set((estado) => ({
      glosarioAbierto: abierto,
      panelConfiguracionAbierto: abierto ? false : estado.panelConfiguracionAbierto,
    })),

  /** Limpia los filtros pero **conserva la sesión**: cambiarla es otra acción distinta. */
  limpiarFiltros: () => set({ ...SIN_FILTROS, ...SELECCION_REINICIADA }),

  /** Devuelve el estado a como arrancó, incluida la sesión. Útil en pruebas. */
  reiniciar: () => set({ ...ESTADO_INICIAL, capas: { ...CAPAS_INICIALES } }),

  /** Indica si hay algún filtro activo además de la sesión. */
  hayFiltrosActivos: () => {
    const { desde, hasta, horaInicio, horaFin, tecnologias } = get();
    return Boolean(desde || hasta || horaInicio || horaFin || tecnologias.length);
  },
}));

/**
 * Objeto de filtros memoizado — **es la query key de TanStack Query**.
 *
 * Se seleccionan los campos uno a uno en lugar de devolver el estado entero para que el objeto
 * solo cambie de identidad cuando cambie un filtro de verdad. Si se devolviera el store completo,
 * cualquier cambio (abrir un panel, seleccionar un evento) invalidaría todas las consultas.
 *
 * @returns {import('../types/index.js').FiltrosTemporales}
 */
export function useFiltros() {
  const sesionIds = useVisStore((e) => e.sesionIds);
  const desde = useVisStore((e) => e.desde);
  const hasta = useVisStore((e) => e.hasta);
  const horaInicio = useVisStore((e) => e.horaInicio);
  const horaFin = useVisStore((e) => e.horaFin);
  const tecnologias = useVisStore((e) => e.tecnologias);

  return useMemo(
    () => ({ sesionIds, desde, hasta, horaInicio, horaFin, tecnologias }),
    [sesionIds, desde, hasta, horaInicio, horaFin, tecnologias],
  );
}

/**
 * Filtros de las gráficas temporales (línea de tiempo, secuencia y radiobases repetidas).
 *
 * Son los del análisis, salvo que con una sesión enfocada solo se pide esa. El resumen y la tabla
 * de eventos siguen usando `useFiltros`, con todas las sesiones.
 *
 * @returns {import('../types/index.js').FiltrosTemporales}
 */
export function useFiltrosGraficas() {
  const filtros = useFiltros();
  const enfocada = useVisStore((e) => e.sesionEnfocada);

  return useMemo(
    () =>
      enfocada && filtros.sesionIds.includes(enfocada)
        ? { ...filtros, sesionIds: [enfocada] }
        : filtros,
    [filtros, enfocada],
  );
}

/**
 * Cuántos filtros hay aplicados además de la sesión. Lo usa el botón que abre el panel de
 * configuración en móvil: con el panel cerrado, es la única pista de que hay filtros actuando.
 */
export function useNumeroFiltrosActivos() {
  const desde = useVisStore((e) => e.desde);
  const hasta = useVisStore((e) => e.hasta);
  const horaInicio = useVisStore((e) => e.horaInicio);
  const horaFin = useVisStore((e) => e.horaFin);
  const tecnologias = useVisStore((e) => e.tecnologias);

  return [desde, hasta, horaInicio, horaFin].filter(Boolean).length + tecnologias.length;
}

/** Lista de parámetros RF con la capa activa, en el orden de la interfaz. */
export function useParametrosActivos() {
  const capas = useVisStore((e) => e.capas);
  return useMemo(() => PARAMETROS_RF.filter((p) => capas[p]), [capas]);
}

export { ESTADO_INICIAL, CAPAS_INICIALES, SIN_FILTROS };
