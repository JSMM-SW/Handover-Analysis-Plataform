/**
 * Qué sesión muestran las gráficas temporales cuando se analizan varias (Capa 2).
 *
 * Varias sesiones de fechas lejanas en un mismo eje de tiempo quedan como dos rayas en los
 * extremos, con un vacío enorme en medio. Enfocar una sesión hace que la línea de tiempo, la
 * secuencia de radiobases y el histograma muestren solo esa, a escala. El resumen y la tabla de
 * eventos siguen abarcando todas.
 */

import { useMemo } from 'react';

import { sessionName } from '../../../shared/sessionNames';
import { useSesiones } from './useDatosVT.js';
import { useVisStore } from '../store/visStore.js';
import { textoFecha } from '../utils/fechas.js';

/** Hueco entre sesiones a partir del cual verlas juntas deja de ser legible. */
const HUECO_LEGIBLE_MS = 60 * 60 * 1000;

/**
 * Indica si entre alguna sesión y la siguiente hay más de una hora sin datos.
 *
 * @param {import('../types/index.js').Sesion[]} sesiones
 */
export function sesionesAlejadas(sesiones = []) {
  const ordenadas = sesiones
    .filter((s) => s.inicio && s.fin)
    .sort((a, b) => new Date(a.inicio) - new Date(b.inicio));

  return ordenadas.some(
    (sesion, i) => i > 0 && new Date(sesion.inicio) - new Date(ordenadas[i - 1].fin) > HUECO_LEGIBLE_MS,
  );
}

export function useEnfoqueSesion() {
  const sesionIds = useVisStore((e) => e.sesionIds);
  const enfocada = useVisStore((e) => e.sesionEnfocada);
  const enfocar = useVisStore((e) => e.setSesionEnfocada);
  const { data: sesiones = [] } = useSesiones();

  const elegidas = useMemo(
    () => sesionIds.map((id) => sesiones.find((s) => s.sesion_id === id) ?? { sesion_id: id }),
    [sesionIds, sesiones],
  );

  const opciones = useMemo(
    () =>
      elegidas.map((sesion) => ({
        id: sesion.sesion_id,
        nombre: sessionName(sesion),
        detalle: sesion.inicio ? `${sessionName(sesion)} · ${textoFecha(sesion.inicio)}` : '',
      })),
    [elegidas],
  );

  return {
    opciones,
    enfocada,
    enfocar,
    // Con «Todas» y sesiones lejanas se avisa de por qué la gráfica se ve partida.
    avisarAlejadas: enfocada === null && sesionesAlejadas(elegidas),
  };
}
