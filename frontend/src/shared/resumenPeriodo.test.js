import { describe, it, expect } from 'vitest';
import { construirResumenDesdePeriodo } from './resumenPeriodo';

describe('construirResumenDesdePeriodo', () => {
    it('calcula tasa_handover redondeada a 2 decimales a partir del punto', () => {
        const punto = {
            fecha_inicio: '2026-05-05',
            fecha_fin: '2026-05-05',
            total_mediciones: 7,
            total_handovers: 4,
            exitosos: 1,
            fallidos: 1,
            indeterminados: 2,
            tasa_exito: 50,
            tasa_phd: 50,
            tasa_innecesarios: 33.33,
            uho_evaluables: 3,
            ping_pongs: 1,
            tasa_hopp: 25,
        };

        const resumen = construirResumenDesdePeriodo(punto);

        // 4 / 7 * 100 = 57.142857... -> 57.14
        expect(resumen.tasa_handover).toBe(57.14);
        expect(resumen.total_mediciones).toBe(7);
        expect(resumen.total_handovers).toBe(4);
    });

    it('tasa_handover es null cuando el periodo no tiene mediciones', () => {
        const punto = {
            fecha_inicio: '2026-05-06',
            fecha_fin: '2026-05-06',
            total_mediciones: 0,
            total_handovers: 0,
            exitosos: 0,
            fallidos: 0,
            indeterminados: 0,
            tasa_exito: null,
            tasa_phd: null,
            tasa_innecesarios: null,
            uho_evaluables: 0,
            ping_pongs: 0,
            tasa_hopp: null,
        };

        const resumen = construirResumenDesdePeriodo(punto);

        expect(resumen.tasa_handover).toBeNull();
    });

    it('celdas_distintas y cambios_celda_no_observados no se pueden derivar de un punto de trend', () => {
        const punto = {
            fecha_inicio: '2026-05-05',
            fecha_fin: '2026-05-05',
            total_mediciones: 7,
            total_handovers: 4,
            exitosos: 1,
            fallidos: 1,
            indeterminados: 2,
            tasa_exito: 50,
            tasa_phd: 50,
            tasa_innecesarios: 33.33,
            uho_evaluables: 3,
            ping_pongs: 1,
            tasa_hopp: 25,
        };

        const resumen = construirResumenDesdePeriodo(punto);

        expect(resumen.celdas_distintas).toBeNull();
        expect(resumen.cambios_celda_no_observados).toBeNull();
    });
});
