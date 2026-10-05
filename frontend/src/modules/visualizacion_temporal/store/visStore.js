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
  rscp_dbm: false,
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
  ejeCeldas: 'celda_clave', // 'celda_clave' (ECI) | 'psc_pci'  — decisión D-2

  // --- Selección y detalle ---
  handoverSeleccionadoId: null,
  ventanaSegundos: 5,
  parametroDetalle: 'todos',

  // --- Zoom compartido entre gráficas ---
  rangoZoom: null, // [isoInicio, isoFin]

  // --- Disposición ---
  // Plegada, la tabla se reduce a una lista compacta y a su lado se ve el detalle del handover
  // elegido. Desplegada, se ve la tabla completa y el detalle se oculta.
  tablaColapsada: false,

  // --- Paneles laterales ---
  // En pantallas estrechas la configuración del análisis vive en un panel deslizante; en
  // escritorio se ve siempre y este indicador no tiene efecto visual.
  panelConfiguracionAbierto: false,
  glosarioAbierto: false,
};

export const useVisStore = create((set, get) => ({
  ...ESTADO_INICIAL,

  /**
   * Fija las sesiones a analizar.
   *
   * Resetea la selección y el zoom a propósito: un handover y un rango de zoom pertenecen a unos
   * recorridos concretos, y arrastrarlos a otros dejaría la interfaz mostrando un detalle que no
   * corresponde a lo que se está viendo.
   */
  setSesiones: (sesionIds) =>
    set({
      sesionIds: [...new Set(sesionIds.filter(Boolean))],
      handoverSeleccionadoId: null,
      tablaColapsada: false,
      rangoZoom: null,
    }),

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

  setRangoFecha: (desde, hasta) => set({ desde: desde || null, hasta: hasta || null }),

  setRangoHora: (horaInicio, horaFin) =>
    set({ horaInicio: horaInicio || null, horaFin: horaFin || null }),

  toggleTecnologia: (tecnologia) =>
    set((estado) => ({
      tecnologias: estado.tecnologias.includes(tecnologia)
        ? estado.tecnologias.filter((t) => t !== tecnologia)
        : [...estado.tecnologias, tecnologia],
    })),

  setTecnologias: (tecnologias) => set({ tecnologias: [...tecnologias] }),

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

  setEjeCeldas: (ejeCeldas) => set({ ejeCeldas }),

  /**
   * Selecciona un handover para analizarlo en detalle.
   *
   * Seleccionar **siempre pliega** la tabla: el detalle solo se muestra con la tabla plegada, así
   * que elegir un evento (también el mismo otra vez, tras desplegar) es la forma de verlo.
   */
  seleccionarHandover: (handoverSeleccionadoId) =>
    set({
      handoverSeleccionadoId,
      tablaColapsada: Boolean(handoverSeleccionadoId),
    }),

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
  limpiarFiltros: () =>
    set({
      desde: null,
      hasta: null,
      horaInicio: null,
      horaFin: null,
      tecnologias: [],
      rangoZoom: null,
    }),

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

export { ESTADO_INICIAL, CAPAS_INICIALES };
