/**
 * Calendario de días con datos (Capa 2): qué mes se ve, a qué meses se puede saltar y qué días
 * se pueden elegir. El componente `SelectorFecha` solo pinta lo que devuelve este hook.
 */

import { useMemo, useState } from 'react';

import { useDesplegable } from './useInterfaz.js';
import {
  construirMes,
  diasEnRango,
  mesDe,
  mesesConDatos,
  nombreMes,
} from '../utils/disponibilidad.js';

/**
 * @param {Object} args
 * @param {import('../types/index.js').DiaDisponible[]} args.dias  días con datos
 * @param {string} [args.valor]  día elegido, 'AAAA-MM-DD' o ''
 * @param {string} [args.min]    primer día elegible (p. ej. «desde» para el campo «hasta»)
 * @param {string} [args.max]    último día elegible
 */
export function useCalendario({ dias, valor = '', min = '', max = '' }) {
  const desplegable = useDesplegable();

  const elegibles = useMemo(() => diasEnRango(dias, min || null, max || null), [dias, min, max]);
  const porFecha = useMemo(() => new Map(elegibles.map((d) => [d.fecha, d])), [elegibles]);
  const meses = useMemo(() => mesesConDatos(elegibles), [elegibles]);

  // Mes que el usuario ha navegado; mientras no navegue, se abre en el del día elegido o en el
  // primero con datos.
  const [mesNavegado, setMesNavegado] = useState(null);
  const mes = mesNavegado ?? (valor ? mesDe(valor) : (meses[0] ?? null));

  // Las flechas saltan al mes anterior o siguiente **con datos**: con sesiones de mayo y de
  // septiembre no hay que pasar por junio, julio y agosto vacíos.
  const anterior = mes ? ([...meses].reverse().find((m) => m < mes) ?? null) : null;
  const siguiente = mes ? (meses.find((m) => m > mes) ?? null) : null;

  const semanas = useMemo(
    () => (mes ? construirMes(mes, porFecha, valor || null) : []),
    [mes, porFecha, valor],
  );

  return {
    abierto: desplegable.abierto,
    referencia: desplegable.referencia,
    cerrar: desplegable.cerrar,
    /** Abre o cierra; al abrir, vuelve al mes del día elegido. */
    alternar: () => {
      setMesNavegado(null);
      desplegable.alternar();
    },

    titulo: mes ? nombreMes(mes) : '',
    semanas,
    sinDias: meses.length === 0,
    irAnterior: anterior ? () => setMesNavegado(anterior) : null,
    irSiguiente: siguiente ? () => setMesNavegado(siguiente) : null,
  };
}
