/**
 * Histograma de radiobases repetidas con su deslizador de intervalo (Capa 2) — HU-C2-008.
 *
 * El intervalo de análisis se elige con una bolita que se arrastra: va de 1 minuto a lo que dura
 * la sesión más larga, y en el extremo derecho se analiza el recorrido completo. Mientras se
 * arrastra, el rótulo cambia al instante; la consulta sale cuando el usuario se detiene un
 * momento, y entretanto se sigue viendo el histograma anterior atenuado.
 *
 * Los intervalos se cuentan desde el inicio de cada sesión, así que con varias sesiones cada una
 * tiene los suyos y las flechas los recorren en orden cronológico.
 */

import { useMemo, useState } from 'react';

import { sessionName } from '../../../shared/sessionNames';
import { useCeldasRepetidas } from './useDatosVT.js';
import { useValorDiferido } from './useInterfaz.js';
import { formatearHora, rotulosCeldas } from './useSeriesEcharts.js';
import { useFiltrosGraficas } from '../store/visStore.js';

/** Referencias estables para «sin datos»: un `[]` nuevo en cada render rehace la gráfica. */
const SIN_BINS = [];
const SIN_CELDAS = [];

/** Rótulo del deslizador: los minutos de cada intervalo, o el total en el extremo derecho. */
export function textoIntervalo(minutos) {
  if (minutos === null || minutos === undefined) return 'Todo el recorrido';
  return minutos === 1 ? '1 minuto' : `${minutos} minutos`;
}

/** Rótulo de un intervalo en la navegación: su sesión (si hay varias) y su hora. */
export function etiquetaIntervalo(intervalo, variasSesiones = false) {
  if (!intervalo?.inicio) return '';
  const horas = `${formatearHora(intervalo.inicio)} – ${formatearHora(intervalo.fin)}`;
  return variasSesiones && intervalo.sesion_nombre ? `${sessionName(intervalo)} · ${horas}` : horas;
}

/** Posición de la bolita en porcentaje, para pintar la parte recorrida de la pista. */
export function progresoDeslizador(valor, maximo) {
  if (!maximo || maximo <= 1) return 100;
  return Math.round(((valor - 1) / (maximo - 1)) * 100);
}

export function useHistogramaRepetidas({ top = 20 } = {}) {
  const filtros = useFiltrosGraficas();

  // La posición pertenece a unos filtros: al cambiarlos (o al enfocar otra sesión) se vuelve al
  // total, porque la duración máxima ya es otra. `null` = extremo derecho, el total.
  const [deslizador, setDeslizador] = useState({ filtros, minutos: null });
  const minutos = deslizador.filtros === filtros ? deslizador.minutos : null;
  const minutosConsulta = useValorDiferido(minutos);

  const consulta = useCeldasRepetidas({ minutos: minutosConsulta, top });
  const maximo = consulta.data?.minutos_max ?? 0;

  // El intervalo que se ve se reinicia al primero cada vez que llegan datos nuevos.
  const [navegacion, setNavegacion] = useState({ datos: null, indice: 0 });
  const bins = consulta.data?.bins ?? SIN_BINS;
  const indice =
    navegacion.datos === consulta.data
      ? Math.min(navegacion.indice, Math.max(bins.length - 1, 0))
      : 0;
  const binActual = bins[indice] ?? null;
  const celdas = binActual?.celdas ?? SIN_CELDAS;
  const rotulos = useMemo(() => rotulosCeldas(celdas), [celdas]);
  const variasSesiones = new Set(bins.map((b) => b.sesion_id).filter(Boolean)).size > 1;

  const valor = minutos === null || minutos >= maximo ? maximo : minutos;

  return {
    consulta,
    celdas,
    rotulos,

    deslizador: {
      valor: Math.max(valor, 1),
      maximo: Math.max(maximo, 1),
      deshabilitado: maximo <= 1,
      texto: textoIntervalo(minutos === null || minutos >= maximo ? null : minutos),
      progreso: progresoDeslizador(valor, maximo),
      /** Llevar la bolita al extremo derecho vuelve al total. */
      mover: (nuevo) => setDeslizador({ filtros, minutos: nuevo >= maximo ? null : nuevo }),
    },

    intervalos: {
      total: bins.length,
      indice,
      etiqueta: etiquetaIntervalo(binActual, variasSesiones),
      irAnterior: () => setNavegacion({ datos: consulta.data, indice: Math.max(0, indice - 1) }),
      irSiguiente: () =>
        setNavegacion({ datos: consulta.data, indice: Math.min(bins.length - 1, indice + 1) }),
    },
  };
}
