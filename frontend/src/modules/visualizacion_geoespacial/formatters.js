const LOCALE = 'es-EC';
const TIME_ZONE = 'America/Guayaquil';

const dateTime = new Intl.DateTimeFormat(LOCALE, {
  dateStyle: 'short', timeStyle: 'medium', timeZone: TIME_ZONE,
});
const rangeTime = new Intl.DateTimeFormat(LOCALE, {
  dateStyle: 'short', timeStyle: 'short', timeZone: TIME_ZONE,
});
const date = new Intl.DateTimeFormat(LOCALE, {
  dateStyle: 'medium', timeZone: TIME_ZONE,
});
const hour = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: TIME_ZONE,
});

export const formatTime = (value) => dateTime.format(new Date(value));
export const formatRange = (value) => rangeTime.format(new Date(value));
export const formatDate = (value) => date.format(new Date(value));
export const formatHour = (value) => hour.format(new Date(value));
export const sessionName = (row) => `Sesión ${row.sesion_label ?? row.execution_id}`;

export function technologyName(value) {
  return { 0: 'Sin señal', 1: 'LTE / 4G', 2: '3G / UMTS' }[value] ?? 'Sin dato';
}
