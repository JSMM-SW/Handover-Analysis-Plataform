/**
 * Pruebas del store del Módulo 2 (Fase 4, tarea 4.8).
 *
 * El store es donde se materializa HU-C2-006: su objeto de filtros es la query key de TanStack
 * Query, así que un fallo aquí se traduce en visualizaciones que no se refrescan o que se
 * refrescan de más.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { CAPAS_INICIALES, useVisStore } from './visStore.js';

const estado = () => useVisStore.getState();

beforeEach(() => {
  estado().reiniciar();
});

describe('selección de sesión', () => {
  it('guarda la sesión elegida', () => {
    estado().setSesion('sesion-1');

    expect(estado().sesionIds).toEqual(['sesion-1']);
  });

  it('permite analizar varias sesiones a la vez y quitarlas de una en una', () => {
    estado().toggleSesion('sesion-1');
    estado().toggleSesion('sesion-2');
    expect(estado().sesionIds).toEqual(['sesion-1', 'sesion-2']);

    estado().toggleSesion('sesion-1');
    expect(estado().sesionIds).toEqual(['sesion-2']);
  });

  it('no duplica sesiones', () => {
    estado().setSesiones(['a', 'b', 'a']);

    expect(estado().sesionIds).toEqual(['a', 'b']);
  });

  it('resetea la selección y el zoom al cambiar de sesión', () => {
    // Un handover y un zoom pertenecen a un recorrido concreto: arrastrarlos a otra sesión
    // dejaría la interfaz mostrando un detalle que no corresponde con lo que se ve.
    estado().setSesion('sesion-1');
    estado().seleccionarHandover('evento-9');
    estado().setRangoZoom(['2026-07-01T13:00:00Z', '2026-07-01T13:05:00Z']);

    estado().toggleSesion('sesion-2');

    expect(estado().sesionIds).toEqual(['sesion-1', 'sesion-2']);
    expect(estado().handoverSeleccionadoId).toBeNull();
    expect(estado().rangoZoom).toBeNull();
  });
});

describe('filtros', () => {
  it('guarda el rango de fechas y normaliza los vacíos a null', () => {
    estado().setRangoFecha('2026-07-01T13:00', '2026-07-01T14:00');
    expect(estado().desde).toBe('2026-07-01T13:00');

    estado().setRangoFecha('', '');
    expect(estado().desde).toBeNull();
    expect(estado().hasta).toBeNull();
  });

  it('guarda el rango horario', () => {
    estado().setRangoHora('08:00', '18:00');

    expect(estado().horaInicio).toBe('08:00');
    expect(estado().horaFin).toBe('18:00');
  });

  it('alterna tecnologías sin duplicarlas', () => {
    estado().toggleTecnologia('LTE');
    estado().toggleTecnologia('WCDMA');
    expect(estado().tecnologias).toEqual(['LTE', 'WCDMA']);

    estado().toggleTecnologia('LTE');
    expect(estado().tecnologias).toEqual(['WCDMA']);
  });

  it('detecta si hay filtros activos', () => {
    expect(estado().hayFiltrosActivos()).toBe(false);

    estado().toggleTecnologia('LTE');
    expect(estado().hayFiltrosActivos()).toBe(true);
  });

  it('limpiarFiltros conserva la sesión', () => {
    // Cambiar de sesión es una acción distinta de limpiar filtros: si "Limpiar" deseleccionara
    // la sesión, la página volvería al estado vacío y habría que empezar de cero.
    estado().setSesion('sesion-1');
    estado().setRangoFecha('2026-07-01T13:00', '2026-07-01T14:00');
    estado().setRangoHora('08:00', '18:00');
    estado().toggleTecnologia('LTE');
    estado().setRangoZoom(['a', 'b']);

    estado().limpiarFiltros();

    expect(estado().sesionIds).toEqual(['sesion-1']);
    expect(estado().desde).toBeNull();
    expect(estado().hasta).toBeNull();
    expect(estado().horaInicio).toBeNull();
    expect(estado().horaFin).toBeNull();
    expect(estado().tecnologias).toEqual([]);
    expect(estado().rangoZoom).toBeNull();
  });
});

describe('capas de visualización', () => {
  it('arranca solo con RSSI, que es el parámetro mejor cubierto', () => {
    expect(estado().capas.rssi_dbm).toBe(true);
    expect(estado().capas.rssnr_db).toBe(false);
  });

  it('alterna una capa concreta sin tocar las demás', () => {
    estado().toggleCapa('rsrq_db');

    expect(estado().capas.rsrq_db).toBe(true);
    expect(estado().capas.rssi_dbm).toBe(true);
  });

  it('activa todas las capas de parámetros y conserva los marcadores', () => {
    estado().setCapas({ marcadoresHO: false });

    estado().activarTodasLasCapas();

    expect(estado().capas.rsrp_dbm).toBe(true);
    expect(estado().capas.rsrq_db).toBe(true);
    expect(estado().capas.rssnr_db).toBe(true);
    expect(estado().capas.rscp_dbm).toBe(true);
    expect(estado().capas.rssi_dbm).toBe(true);
    expect(estado().capas.marcadoresHO).toBe(false);
  });
});

describe('detalle y eje de celdas', () => {
  it('permite elegir el identificador del eje de radiobases', () => {
    // Decisión D-2: se ofrecen ECI y PCI, con ECI por defecto.
    expect(estado().ejeCeldas).toBe('celda_clave');

    estado().setEjeCeldas('psc_pci');
    expect(estado().ejeCeldas).toBe('psc_pci');
  });

  it('la ventana por defecto es de 5 segundos', () => {
    expect(estado().ventanaSegundos).toBe(5);

    estado().setVentana(30);
    expect(estado().ventanaSegundos).toBe(30);
  });

  it('el parámetro de detalle arranca en "todos"', () => {
    expect(estado().parametroDetalle).toBe('todos');

    estado().setParametroDetalle('rsrq_db');
    expect(estado().parametroDetalle).toBe('rsrq_db');
  });
});

describe('reinicio', () => {
  it('devuelve el estado a como arrancó', () => {
    estado().setSesion('sesion-1');
    estado().toggleTecnologia('GSM');
    estado().toggleCapa('rssnr_db');

    estado().reiniciar();

    expect(estado().sesionIds).toEqual([]);
    expect(estado().tecnologias).toEqual([]);
    expect(estado().capas).toEqual(CAPAS_INICIALES);
  });

  it('no comparte la referencia de capas entre reinicios', () => {
    // Si `reiniciar` reutilizara el objeto literal, mutar las capas contaminaría el valor inicial
    // y el siguiente reinicio no restauraría nada.
    estado().toggleCapa('rssnr_db');
    estado().reiniciar();

    expect(estado().capas.rssnr_db).toBe(false);
    expect(CAPAS_INICIALES.rssnr_db).toBe(false);
  });
});

describe('paneles laterales', () => {
  it('arrancan cerrados', () => {
    expect(estado().panelConfiguracionAbierto).toBe(false);
    expect(estado().glosarioAbierto).toBe(false);
  });

  it('abrir la configuración cierra el glosario, y al revés', () => {
    // Dos paneles superpuestos taparían todo el contenido en un móvil.
    estado().setGlosario(true);
    estado().setPanelConfiguracion(true);

    expect(estado().panelConfiguracionAbierto).toBe(true);
    expect(estado().glosarioAbierto).toBe(false);

    estado().setGlosario(true);

    expect(estado().glosarioAbierto).toBe(true);
    expect(estado().panelConfiguracionAbierto).toBe(false);
  });

  it('cerrar un panel no abre el otro', () => {
    estado().setGlosario(true);
    estado().setPanelConfiguracion(false);

    expect(estado().glosarioAbierto).toBe(true);
    expect(estado().panelConfiguracionAbierto).toBe(false);
  });
});

describe('tabla de eventos y detalle', () => {
  it('seleccionar un handover pliega la tabla para mostrar el detalle', () => {
    estado().seleccionarHandover('ev-1');

    expect(estado().tablaColapsada).toBe(true);
  });

  it('desplegar oculta el detalle pero conserva el evento seleccionado', () => {
    estado().seleccionarHandover('ev-1');
    estado().desplegarTabla();

    expect(estado().tablaColapsada).toBe(false);
    expect(estado().handoverSeleccionadoId).toBe('ev-1');
  });

  it('volver a elegir el mismo evento tras desplegar lo pliega otra vez', () => {
    estado().seleccionarHandover('ev-1');
    estado().desplegarTabla();
    estado().seleccionarHandover('ev-1');

    expect(estado().tablaColapsada).toBe(true);
  });
});
