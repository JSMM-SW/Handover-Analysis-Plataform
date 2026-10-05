import { describe, expect, it } from 'vitest';
import { sessionExportLabel, sessionName } from './sessionNames';

describe('session names from uploaded filenames', () => {
  it.each([
    ['Session_55_312312_23132.csv', 'Sesión 55'],
    ['sesion _55_312312_23132.csv', 'Sesión 55'],
    ['SESIÓN_0055_312312_23132.CSV', 'Sesión 55'],
    ['Session_0_312312_23132.csv', 'Sesión 0'],
    ['mediciones_55.csv', 'Sesión 12'],
    ['Session_55abc.csv', 'Sesión 12'],
  ])('formats %s', (filename, expected) => {
    expect(sessionName({ filename, sesion_label: 12 })).toBe(expected);
  });

  it('uses the original filename instead of the old temporal label', () => {
    expect(sessionName({ sesion_nombre: 'Sesión 12 · Session_55_312312_23132.csv · Datos 1' })).toBe('Sesión 55');
    expect(sessionName({ sesion_nombre: 'Datos 1' })).toBe('Datos 1');
  });

  it('keeps duplicate uploads distinct internally and uses the source number for map exports', () => {
    const first = { filename: 'Session_55_312312_23132.csv', sesion_label: 12, execution_id: 'first' };
    const second = { ...first, sesion_label: 13, execution_id: 'second' };
    expect(sessionName(first)).toBe(sessionName(second));
    expect(first.execution_id).not.toBe(second.execution_id);
    expect(first.sesion_label).toBe(12);
    expect(sessionExportLabel(first)).toBe('55');
  });
});
