/**
 * Filtros de la configuración del análisis acotados a los datos que existen (Capa 2).
 *
 * Une la disponibilidad que devuelve el backend (`GET /disponibilidad`) con los filtros del
 * store, y devuelve al componente solo lo que puede pintar: qué días se pueden marcar, qué horas
 * ofrecer y qué tecnologías hay. El componente no calcula nada.
 */

import { useCallback, useMemo } from 'react';

import { useDisponibilidad } from './useDatosVT.js';
import { useVisStore } from '../store/visStore.js';
import { opcionesDeHora } from '../utils/disponibilidad.js';
import { aFechaLocal, aInstanteUTC } from '../utils/fechas.js';

/** Conserva el valor elegido entre las opciones aunque no esté (para que el `<select>` lo muestre). */
function conValorActual(opciones, valor) {
  if (!valor || opciones.some((o) => o.valor === valor)) return opciones;
  return [...opciones, { valor, etiqueta: valor.slice(0, 5) }].sort((a, b) =>
    a.valor.localeCompare(b.valor),
  );
}

/** El valor si sigue entre las opciones; si no, `null`. */
function siSigue(valor, opciones) {
  return valor && opciones.some((o) => o.valor === valor) ? valor : null;
}

export function useFiltrosDisponibles() {
  const desde = useVisStore((e) => e.desde);
  const hasta = useVisStore((e) => e.hasta);
  const horaInicio = useVisStore((e) => e.horaInicio);
  const horaFin = useVisStore((e) => e.horaFin);
  const setRangoFecha = useVisStore((e) => e.setRangoFecha);
  const setRangoHora = useVisStore((e) => e.setRangoHora);

  const disponibilidad = useDisponibilidad();
  const dias = useMemo(() => disponibilidad.data?.dias ?? [], [disponibilidad.data]);

  // El store guarda instantes; el calendario trabaja con días locales 'AAAA-MM-DD'.
  const fechaDesde = aFechaLocal(desde);
  const fechaHasta = aFechaLocal(hasta);

  const opciones = useMemo(
    () => opcionesDeHora(dias, fechaDesde || null, fechaHasta || null),
    [dias, fechaDesde, fechaHasta],
  );

  /**
   * Cambia los días elegidos. Si la franja horaria puesta no tiene datos en los días nuevos, se
   * suelta: de lo contrario quedaría un filtro imposible que el usuario no ha elegido.
   */
  const fijarFechas = useCallback(
    (nuevaDesde, nuevaHasta) => {
      const nuevas = opcionesDeHora(dias, nuevaDesde || null, nuevaHasta || null);
      setRangoFecha(
        aInstanteUTC(nuevaDesde, null, 'inicio'),
        aInstanteUTC(nuevaHasta, null, 'fin'),
      );

      const inicio = siSigue(horaInicio, nuevas.inicios);
      const fin = siSigue(horaFin, nuevas.fines);
      if (inicio !== horaInicio || fin !== horaFin) setRangoHora(inicio, fin);
    },
    [dias, horaInicio, horaFin, setRangoFecha, setRangoHora],
  );

  return {
    cargando: disponibilidad.isLoading,
    error: disponibilidad.isError ? disponibilidad.error : null,

    dias,
    tecnologias: disponibilidad.data?.tecnologias ?? [],

    fechaDesde,
    fechaHasta,
    elegirDesde: (fecha) => fijarFechas(fecha, fechaHasta),
    elegirHasta: (fecha) => fijarFechas(fechaDesde, fecha),

    // «Desde» no puede pasar de «hasta» ni al revés.
    horasInicio: conValorActual(
      opciones.inicios.filter((o) => !horaFin || o.valor < horaFin),
      horaInicio,
    ),
    horasFin: conValorActual(
      opciones.fines.filter((o) => !horaInicio || o.valor > horaInicio),
      horaFin,
    ),
    elegirHoraInicio: (hora) => setRangoHora(hora || null, horaFin),
    elegirHoraFin: (hora) => setRangoHora(horaInicio, hora || null),
  };
}
