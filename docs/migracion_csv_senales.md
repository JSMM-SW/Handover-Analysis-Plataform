# Ingesta CSV y señales originales

La migración 007 elimina `rsrp_dbm`, `rscp_dbm` y `rssi_dbm` de
`handover_record`. La ingesta admite únicamente `.csv`; ya no interpreta
el valor `rssi` en función de `tech`.

| Campo del CSV | Campo limpio |
| --- | --- |
| rssi | rssi |
| rsrq | rsrq |
| rssnr | rssnr |
| rssi_strongest (RSRP de NetMonitor) | rsrp |

Los centinelas `2147483647` se guardan como `NULL`. `rssi_strongest` es
opcional para conservar compatibilidad con exportaciones que no lo incluyan.
Tras la verificacion del usuario para esta app, `rssi_strongest` se interpreta
como RSRP. La columna de la base se llama `rsrp` y no se aplica ninguna
formula ni se copia RSSI. Esta interpretacion es especifica del export de NetMonitor.
Aplicar la migracion 008 despues de la 007 para actualizar metadatos y deltas historicos.
`tecnologia` sigue derivándose de `net_type`; `tech` y `net_type` originales
se conservan.

## Despliegue sobre una base existente

Actualizar juntos backend y frontend. Las versiones anteriores del backend
consultan columnas eliminadas y no son compatibles con el nuevo esquema.
Detener los procesos de ingesta durante la migración y reiniciar el backend
después. Configurar `ALLOWED_EXTENSIONS=.csv` en `.env`.

Desde la raíz del proyecto, con el entorno virtual:

```powershell
python migrations/migrate_csv_signals.py --raw-dir C:\ruta\a\CSV
python migrations/migrate_csv_signals.py --apply --raw-dir C:\ruta\a\CSV
```

La primera ejecución es una previsualización de los originales disponibles.
La segunda bloquea las tablas afectadas durante una transacción, respalda
`handover_record`, `etl_execution` y `eventos_handover` en JSONL comprimido
dentro de `backups/csv_signals_<fechaUTC>/` y verifica su lectura y recuento.
`manifest.json` conserva las columnas previas, recuentos y hashes SHA-256.
Es un respaldo de las tablas afectadas, no de toda la instancia Supabase.
Los respaldos no deben subirse al repositorio.

La migración recupera RSSI desde el campo al que lo copió el ETL anterior,
solo en registros CSV. Cuando existe el original, verifica fecha, celda,
nodo, frecuencia e índice de registro antes de recuperar las cuatro señales.
Una coincidencia ambigua no se actualiza. Sin original, `rsrp`
permanece `NULL`. No se eliminan ni vuelven a insertar sesiones o mediciones.
La restricción CSV aborta la transacción si todavía existen registros Excel:
no se borran implícitamente.

El script SQL no utiliza `CASCADE`: una dependencia externa bloquea el cambio
en lugar de eliminar vistas u objetos ajenos. La migración se aplica una sola
vez. Ante un error dentro de la transacción, PostgreSQL revierte los cambios;
el respaldo local permanece disponible.

## Compatibilidad de módulos

- Geoespacial usa `rssi` para su promedio, mapa de calor y estimación de radios
  base. No dibuja observaciones sin GPS. Admite el filtro de tecnología 2G.
- Temporal conserva sus contratos API anteriores para evitar romper clientes:
  `rssi_dbm` es ahora un alias de lectura de `rssi` para todas las tecnologías.
  `rsrp_dbm` es un alias de `rsrp`; RSCP sigue sin dato. La capa inicial es RSSI y RSSNR se muestra con su nombre.
  Los datos sintéticos de prueba mantienen su propio esquema.
- KPIs obtiene RSRP de `rsrp`. El porcentaje critico usa solo
  observaciones con RSRP disponible; sin medidas devuelve `null`.
  Los cálculos PHD/UHO siguen usando RSSI y RSRQ. Los deltas históricos
  RSRP se recuperan de las mediciones que delimitan cada evento mediante la
  migracion 008; RSCP permanece sin dato. No se borran eventos.
- El dataset limpio exportado incluye las cuatro columnas originales de señal.

Las columnas de contratos y fixtures de Temporal con nombres anteriores no
son columnas de `handover_record` y no deben confundirse con las eliminadas.

## Nombre de columna RSRP

La migracion 009 renombra `handover_record.rssi_strongest` a `rsrp`,
sin cambiar sus valores ni el tipo SMALLINT nullable. El CSV mantiene el
encabezado original `rssi_strongest`; el ETL lo convierte a `rsrp`.
La API geoespacial y el CSV limpio exportado usan `rsrp`. Temporal conserva
el alias `rsrp_dbm` de su contrato. El ejecutor aplica 007, 008 y 009 en orden
para bases anteriores a 007. En bases ya actualizadas aplicar solo las pendientes.
