# Visualización geoespacial

Consulta PostgreSQL mediante `get_db`, sin modificar las mediciones.

## Ejecutar

Desde la raíz:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend
```

En otra terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Abrir http://localhost:5173/geoespacial. La conexión se configura en `.env`
mediante `DATABASE_URL`; el frontend usa `http://localhost:8000/api/v1` o
`VITE_API_URL` en `frontend/.env.local`. No colocar credenciales en variables VITE.
En producción, configurar el servidor web para resolver las rutas a `index.html`.

## Uso

Abrir el desplegable, marcar una o varias sesiones y pulsar «Analizar sesiones»
para cargar los mapas. Cambiar los checks no actualiza el análisis hasta pulsar
el botón de nuevo. El selector muestra «Sesión N» mediante `sesion_label`
y la cantidad de registros válidos. Las consultas siguen usando `execution_id`.
Bajo la selección se muestra
el intervalo de mediciones disponible, en hora de Ecuador, para orientar los
filtros de fecha. Se consultan todas sus hojas, sin unir recorridos entre
sesiones ni entre hojas diferentes. Los CSV no requieren hoja. El panel izquierdo filtra
por fecha/hora de Ecuador (UTC-5), tecnología y zona visible del mapa.
Las horas se seleccionan por minuto; «Hasta» incluye todo el minuto elegido.

Las pestañas comparten filtros y preferencias de capas:

- Mapa de rutas y handovers: capas Handovers, Trayectoria y Radios Base.
- Mapa de calor: el calor de handovers se muestra al abrir la pestaña; las
  capas Handovers y Trayectoria se pueden activar aparte.

La tarjeta Handovers cuenta los eventos de la consulta, independientemente de
si su capa está visible. Datos analizados cuenta las mediciones. Un clic en
un handover muestra celdas y nodos de origen/destino, fecha y coordenadas.
Al pasar el cursor aparece una burbuja con fecha, hora de Ecuador, RSSI,
RSRQ y RSSNR. Los valores ausentes aparecen como «Sin dato».
En CSV, la hora proviene de `sys_time`: la ingesta la guarda en UTC y la
burbuja la muestra de nuevo en hora de Ecuador, incluyendo segundos.
RSSI ausente se representa en gris y se excluye del promedio. Los colores del mapa usan intervalos de RSSI en dBm (desde -80, de -100 a -80 y menor de -100); la intensidad del calor indica concentración de eventos, no calidad de señal.

## Regla de handover

Regla acordada con el usuario: `cell_id` cambia **y** `node_id` cambia respecto
a la observación anterior del mismo recorrido. Cambiar solo uno no cuenta.
Se calcula sobre registros ordenados por hoja y tiempo, antes de los filtros
visuales. Se ubica el evento en la primera medición del destino.

Se mantiene el criterio de continuidad de esta visualización: no comparar
hojas diferentes, intervalos mayores de 60 segundos, tiempos repetidos ni
identificadores ausentes/inválidos. La consulta lee hasta 60 segundos previos
al inicio para detectar cambios en el borde temporal, sin mostrarlos como
mediciones del intervalo. Los filtros se aplican sobre la medición de destino.

La regla usa únicamente los registros persistidos, no confirma señalización
ni éxito del procedimiento de red. Los Excel sin node_id no pueden producir
eventos bajo esta regla. El calor usa exclusivamente eventos detectados,
con igual peso, y su intensidad relativa varía con el zoom.

La API admite hasta 20.000 registros leídos (incluido contexto temporal).
Si se supera, pide reducir el intervalo, sin truncar silenciosamente.
Las rutas se cortan en puntos excluidos por filtros, horas repetidas y huecos
mayores de 60 segundos. La agrupación por hoja presupone un recorrido por hoja.

La capa Radios Base calcula ubicaciones candidatas por celda, sin guardarlas
en la base de datos. Ver [método, parámetros y limitaciones](radios_base_estimadas.md).
No se implementan exportación del mapa ni filtro por velocidad.

## API

- `GET /api/v1/geoespacial/ejecuciones`: ejecuciones completadas y sus fechas mínima y máxima de medición.
- `GET /api/v1/geoespacial/ejecuciones/{id}/hojas`: hojas; CSV devuelve `[null]`.
- `GET /api/v1/geoespacial/mediciones`: uno o varios `execution_id` repetidos, `hoja` opcional,
  `desde`, `hasta`, `tecnologia`, `cell_id` opcional y `bbox` (oeste,sur,este,norte).

Omitir hoja consulta toda la ejecución. Fechas con zona horaria y extremos
inclusivos. Tecnología 0=sin señal, 1=LTE, 2=3G/UMTS. Respuesta: `mediciones`,
`tramos`, `total`, `handovers`, `total_handovers` y `advertencias`.
Errores: filtros inválidos 422, ejecución/hoja inexistente 404, base no disponible
503. Una consulta vacía devuelve 200 y listas vacías.

## Verificar

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit/test_geoespacial_service.py tests/unit/test_radio_bases.py tests/integration/test_geoespacial_endpoints.py -q
.\venv\Scripts\python.exe tests/check_geoespacial_readonly.py
cd frontend
npm.cmd run build
npm.cmd run lint
npm.cmd run test:e2e
```

E2E usa datos simulados y Edge en Windows (Chromium en otros sistemas).
El script de solo lectura consulta la base real. Las preferencias de capas
se guardan durante la sesión del navegador; filtros se reinician al salir.
El mapa base usa Leaflet y OpenStreetMap y requiere Internet.

## Integración con develop

Revisar conjuntamente la navegación en `frontend/src/App.jsx`, los estilos globales,
`backend/app/main.py` y las dependencias del frontend. El esquema compartido debe
incluir `etl_execution.sesion_label` y las columnas de mediciones usadas por el
módulo; geoespacial no crea ni migra tablas.

Las radios base usan marcadores de 24 × 24 píxeles. Su burbuja muestra sesión,
nodo, celda, tecnología y coordenadas. Los parámetros técnicos se agrupan en
«Detalles de la estimación», cerrado inicialmente, y se conserva el aviso de
ubicación aproximada. Cada sesión mantiene su propia estimación.

Las pruebas E2E simulan la API: no sustituyen una comprobación conjunta de
Ingesta y Geoespacial con la base del entorno de integración.
