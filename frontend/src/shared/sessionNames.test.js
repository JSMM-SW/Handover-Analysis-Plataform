import { describe, expect, it } from 'vitest';
import { SESSION_PENDING, sessionExportLabel, sessionName, sessionNumber } from './sessionNames';

describe('session names come from sesion_label, never from the filename', () => {
  it.each([
    ['Session_31_20240308_171157.csv', 7, 'Sesión 7'],
    ['Session_55_312312_23132.csv', 12, 'Sesión 12'],
    ['SESIÓN_0055_312312_23132.CSV', 3, 'Sesión 3'],
    ['mediciones.csv', 168, 'Sesión 168'],
  ])('%s with sesion_label %i is "%s"', (filename, sesion_label, expected) => {
    expect(sessionName({ filename, sesion_label })).toBe(expected);
  });

  it('never takes the number from the filename when there is no sesion_label', () => {
    const pending = { filename: 'Session_31_20240308_171157.csv', sesion_label: null };
    expect(sessionNumber(pending)).toBeNull();
    expect(sessionName(pending)).toBe('Session_31_20240308_171157.csv');
    expect(sessionName(pending)).not.toBe('Sesión 31');
    expect(sessionName({})).toBe(SESSION_PENDING);
    expect(sessionName({ execution_id: 'abc' })).toBe(SESSION_PENDING);
  });

  it('reads the label the backend wrote in the temporal sesion_nombre, not the file number', () => {
    expect(sessionName({ sesion_nombre: 'Sesión 12 · Session_55_312312_23132.csv · Datos 1' })).toBe('Sesión 12');
    expect(sessionName({ sesion_nombre: 'Sesión 12 · Session_55_312312_23132.csv' })).toBe('Sesión 12');
    // Sin etiqueta del backend se muestra tal cual, sin extraer el 55.
    expect(sessionName({ sesion_nombre: 'Session_55_312312_23132.csv · Datos 1' })).toBe('Session_55_312312_23132.csv · Datos 1');
  });

  it('gives consecutive names to files loaded in order, whatever number their names carry', () => {
    const first = { filename: 'Session_90_20240308_171157.csv', sesion_label: 168, execution_id: 'first' };
    const second = { filename: 'Session_12_20240309_081500.csv', sesion_label: 169, execution_id: 'second' };
    expect([first, second].map(sessionName)).toEqual(['Sesión 168', 'Sesión 169']);
    expect(sessionExportLabel(first)).toBe('168');
    expect(sessionExportLabel({ execution_id: 'x' })).toBe('pendiente');
  });
});
