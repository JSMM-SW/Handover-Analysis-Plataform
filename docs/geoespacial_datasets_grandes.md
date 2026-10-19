# Análisis geoespacial de conjuntos grandes

La consulta ya no rechaza conjuntos de más de 50.000 mediciones. El análisis
usa todas las filas del intervalo seleccionado. La detección de handovers sigue
ejecutándose por sesión completa con el detector de Temporal; las radios base
se estiman antes de simplificar los datos destinados al mapa.

## Análisis y representación

`total`, `total_handovers`, los conteos con/sin GPS y `promedios` corresponden al
análisis completo, no a la ventana ni al número de elementos dibujados. Como
antes, `total` y los promedios de señal usan mediciones con GPS válido.

Para conjuntos grandes, `mediciones` contiene puntos de las trayectorias
simplificadas y `senales` contiene todas las mediciones individuales de la vista,
incluido un margen para el calor. No se seleccionan muestras representativas ni
se sustituyen las posiciones por centroides. Cada entrada compacta conserva
`[latitud, longitud, rssi, rsrp, rsrq, rssnr, id_registro, timestamp_medicion, cell_id]`.
Para conjuntos pequeños, se usan directamente las entradas de `mediciones`.

Un Web Worker dibuja el calor en Canvas con el aporte de cada valor válido,
sin crear un marcador por registro. Las muestras que coinciden en un mismo píxel
se acumulan con sus sumas y cantidades: conservan su peso en el raster. Los nulos
siguen siendo ausencia de señal, nunca cero. El suavizado mezcla valores cercanos
en la imagen; no representa cobertura confirmada ni modifica las observaciones.
Al mover/cambiar la vista o la capa, se cancela el trabajador anterior. La descarga
PNG espera a que termine el dibujo.

El cursor usa un índice de proximidad de pantalla (radio de 8 píxeles) para
mostrar la medición individual más cercana: celda, fecha, hora y parámetro activo.
El clic consulta el detalle de ese mismo identificador y lo lleva a la vista.
Si hay coordenadas idénticas, se elige de forma estable la primera medición en el
orden de respuesta; todas siguen aportando al calor. Los puntos negros de handover
tienen prioridad al pasar el cursor. Ya no se muestran «mediciones agrupadas».

Los presupuestos de dibujo son 6.000 puntos de trayectorias
y 1.000 marcadores/grupos de handovers por respuesta. No hay un tope de 2.000
grupos para el calor: se envían todas las muestras individuales visibles.
Las estimaciones de radios base también se agrupan hasta 1.000
marcadores por vista, conservando su conteo completo en `total_radios_base` y
mostrando explícitamente una estimación de ejemplo al abrir un grupo. No limitan las mediciones
analizadas. Se conservan las separaciones de sesiones, hojas, huecos y puntos
excluidos. Si hay más tramos disjuntos de los que caben en el dibujo se informa al
usuario. Los grupos de handovers indican cuántos eventos representan y permiten
acercarse o consultar un evento original.

`vista_bbox` y `zoom` ajustan únicamente la representación. No sustituyen al
filtro geográfico `bbox`. El navegador solicita una nueva vista tras detener el
zoom/desplazamiento, cancela respuestas antiguas y conserva el dibujo previo
mientras carga. «Ajustar vista» utiliza la extensión completa del análisis.

## Detalles y caché

En PostgreSQL, la lectura usa una sola consulta por sesión y un cursor que
entrega bloques de 5.000 filas hasta completarla; ese tamaño no limita el
análisis. El cursor evita repetir la ordenación y abrir una nueva consulta por
bloque. La paginación por clave se conserva para otros motores. Se solicitan únicamente los
campos necesarios y se reutilizan las mismas filas para el mapa y el detector
de handovers, evitando descargar la sesión dos veces. El cursor y la transacción
se cierran antes de ejecutar el detector y generar el mapa. Si se interrumpe la
conexión, se reintenta una vez; un cursor interrumpido se reinicia descartando las
filas parciales para no duplicar registros ni analizar sesiones incompletas.

Los endpoints `GET /geoespacial/mediciones/{id}` y
`GET /geoespacial/handovers/{id}` permiten consultar el registro original bajo
demanda. La burbuja de calor muestra una medición individual, y su clic consulta
el detalle de esa misma medición; no muestra el promedio del raster.

Se reutiliza el análisis durante 30 segundos con una caché local al proceso,
acotada por cantidad de entradas y puntos. La clave incluye sesiones, versiones
de carga y filtros. Un análisis que excede el presupuesto de caché se procesa
normalmente sin almacenarse. Las solicitudes simultáneas con la misma clave
comparten el análisis en curso, incluso si no cabe en la caché. No se escriben
ni modifican registros en la BD.

Además, las sesiones completas y sus eventos detectados se conservan durante
120 segundos en una caché independiente (hasta 200.000 filas/eventos y cuatro
entradas). Cambiar fechas, tecnología o el conjunto de sesiones reutiliza las
sesiones que ya están cargadas. La clave incluye la conexión, el identificador,
la fecha de procesamiento y la cantidad de registros válidos; cada solicitud
comprueba primero que la ejecución siga existiendo. Las filas compartidas son
tuplas inmutables, sin el diccionario por registro. La expiración sigue siendo
necesaria para cambios externos que no actualicen esa metadata. Los conjuntos
mayores al presupuesto se procesan completos, pero no se conservan.

Para bases existentes, aplicar `schema_migration_012_geoespacial_lectura.sql`
fuera de una transacción. Crea de forma concurrente un índice que coincide con
el orden de lectura por sesión, fecha, índice de reporte e identificador. No
altera las filas ni sustituye los índices existentes. `schema.sql` ya lo incluye
para instalaciones nuevas. La caché ayuda a solicitudes repetidas; este índice
ayuda a la lectura inicial. Los tiempos dependen de la red y del servidor.

Si una creación concurrente se interrumpe, comprobar `indisvalid` en `pg_index`
antes de dar la migración por aplicada: `IF NOT EXISTS` también omite un índice
inválido. Si existe y es inválido, repararlo con
`REINDEX INDEX CONCURRENTLY public.idx_handover_record_execution_order;` fuera
de una transacción. SQLSTATE `55P03` indica que no se obtuvo el bloqueo a tiempo;
se debe reintentar cuando terminen las transacciones que lo impiden.

Los errores de consulta registran el tipo de excepción y SQLSTATE sin exponer
credenciales ni sentencias SQL. El agotamiento del tiempo de consulta devuelve
HTTP 504; los problemas de conexión o disponibilidad devuelven HTTP 503.

## Límites prácticos

No hay un máximo fijo de filas para el análisis. Esto no implica recursos
infinitos: actualmente el análisis, el detector de Temporal y el estimador de
radios base trabajan en memoria del backend. Con conjuntos mucho mayores pueden
necesitarse procesamiento por trabajos, almacenamiento de resultados y recursos
adicionales. La caché es por proceso, no distribuida, y una modificación externa
de los registros puede tardar hasta su expiración en verse reflejada.
La transferencia de `senales` y el índice del navegador también consumen memoria
y red en proporción al número de muestras visibles. El Worker evita bloquear la
interfaz durante el raster, pero no proporciona capacidad ilimitada.

Las pruebas incluyen 60.001 mediciones en el API y 100.000 muestras en el raster,
el índice y el navegador. Comprueban identidades y valores individuales completos,
presupuestos de trayectorias, aportes al calor, cambios de zoom y detalles bajo
demanda. No constituyen una prueba de carga de millones de registros en Supabase.

También se verificó una consulta real de solo lectura a dos sesiones de Supabase
con 102.923 registros de origen: conservó 20.711 mediciones con GPS y 304
handovers. En esa ejecución la primera respuesta tardó aproximadamente 53
segundos y un cambio de zoom con el análisis en caché tardó 1,5 segundos. Son
tiempos observados, no garantías de rendimiento.

Con la caché adicional de sesiones y filas compactas, otra ejecución de esas
dos sesiones tardó 52,92 segundos en frío y 4,27 segundos al cambiar la franja
horaria de 00:00 a 00:05 (una clave de análisis distinta). Conservó los mismos
totales. Esta medición no acredita todavía una mejora de la carga inicial por
el índice de la migración 012.

La verificación posterior de rendimiento del cursor no pudo completarse por
problemas de conexión a Supabase. Sus pruebas automatizadas sí verifican lectura
completa, orden, cierre de recursos y recuperación sin duplicados. No se atribuye
un tiempo de carga real al cursor. Los intentos de aplicar la migración 012
devolvieron `55P03`; su estado debe verificarse antes de considerarla aplicada.
