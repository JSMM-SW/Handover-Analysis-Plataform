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

Seleccionar una o varias sesiones carga el análisis automáticamente. Los filtros
horizontales separan fechas y franja horaria, con días disponibles y pasos de
cinco minutos desde la hora inicial detectada. Las horas se interpretan en
America/Guayaquil y el minuto final se incluye completo. Las consultas usan
`execution_id`; los nombres visibles proceden de `sesion_label`.

- Rutas: capas Trayectoria, Handovers y Radios Base.
- Calor: parámetros RSSI, RSRP, RSRQ y RSSNR, con una casilla independiente para
  mostrar handovers como puntos negros. La trayectoria permanece visible.

El calor representa todas las mediciones limpias con GPS que cumplen los filtros,
no solo las asociadas a handovers. Los colores son rangos de visualización, no
umbrales calibrados de cobertura. Los valores ausentes se excluyen de los
promedios y aparecen en gris cuando no hay valores disponibles.

Datos analizados y los promedios de señal corresponden a las mediciones con GPS
válido. Handovers incluye todos los eventos que cumplen los filtros, mostrando
aparte cuántos tienen ubicación. El mapa dibuja los que tienen GPS válido.
La hora proviene de `sys_time`, almacenada en UTC y presentada en hora de Ecuador.

Ajustar vista encuadra todo el conjunto analizado; no aplica un filtro geográfico.
El tema claro/oscuro adapta paneles y controles sin alterar los colores de señal.

## Detección de handovers

Se reutiliza el detector de Temporal, por sesión completa antes de aplicar los
filtros. Geoespacial lee las filas una sola vez y adapta sus campos al contrato
del detector. Sus valores predeterminados son dos
muestras de confirmación, un máximo de 30 segundos entre celdas y una ventana
ping-pong de 10 segundos. El evento se ubica en la primera observación del destino.
Son eventos inferidos; no confirman señalización ni éxito del procedimiento de red.

Las rutas conservan sus propios cortes: hojas/sesiones diferentes, mediciones
excluidas, horas repetidas e intervalos mayores de 60 segundos.

## Conjuntos grandes

No hay un límite fijo de 50.000 mediciones para el análisis. El backend conserva
los conteos y promedios completos y envia una representación adaptada al zoom:
trayectorias simplificadas, calor con todas las mediciones individuales de la
vista y grupos de eventos/estimaciones. El cursor consulta la medición más cercana,
sin crear un círculo interactivo por registro; el raster se calcula en un Worker.
Los detalles originales se consultan bajo demanda. Ver
[funcionamiento, presupuestos de dibujo y límites prácticos](geoespacial_datasets_grandes.md).

La capa Radios Base estima posiciones por celda sin escribirlas en la base de
datos. Ver [método, parámetros y limitaciones](radios_base_estimadas.md).
No se implementa filtro por velocidad.

## Descargar la visualización

El botón «Descargar mapa», a la derecha de las capas, guarda un PNG de la vista
actual en ambas pestañas. Incluye el área y zoom visibles, las capas activas,
la leyenda y la atribución de OpenStreetMap. Excluye filtros, navegación,
controles del mapa y burbujas abiertas. El archivo se genera en el navegador,
sin enviar la imagen al backend ni guardarla en la base de datos.

El nombre indica la vista, la sesión analizada (o `varias_sesiones`) y la fecha
de descarga en Ecuador, por ejemplo `mapa_handovers_sesion_14_2026-09-29.png`.
Para las capas de señal se añade el parámetro: `mapa_calor_rsrq_sesion_14_2026-09-29.png`.
Se captura a escala 2 para mejorar la legibilidad; no añade detalle cartográfico
que no esté en la vista. La carpeta final depende de la configuración del navegador.

Mientras se prepara la imagen se bloquean temporalmente los controles del
análisis. Sin mediciones o durante la consulta, el botón está deshabilitado.
Se espera a que carguen las imágenes del mapa base (hasta 12 segundos); si fallan
o no permiten lectura mediante CORS, se muestra un error en lugar de descargar
un mapa incompleto. Se utiliza `html2canvas`, cargado solo al exportar.

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

El workflow `.github/workflows/ci.yml` ejecuta pruebas unitarias y de API
geoespacial, lint, compilación y Playwright en los PR hacia `develop` y `master`.
No utiliza credenciales de producción ni ejecuta los scripts contra la base real.
En CI se usa Chromium; la validación local en Windows usa Edge.

Organización del código:

- `GeoespacialPage.jsx`: carga de sesiones y confirmación de la selección.
- `components/SessionSelector.jsx`: desplegable y rango de fechas.
- `components/DatasetView.jsx`: estado de filtros, capas y descarga del análisis.
- `hooks/useMeasurements.js`: consultas cancelables y protección ante respuestas antiguas.
- `components/MapControls.jsx` y `HandoverDetail.jsx`: controles y detalle del evento.
- `components/MapaGeoespacial.jsx`: ciclo de vida del mapa y sus capas Leaflet.
- `mapPopups.js` y `formatters.js`: burbujas seguras y formatos compartidos.
- `signalHeat.js`, `components/SignalHeatLayer.js` y `exportMap.js`: cálculo de calor,
  representación en canvas y descarga PNG.
- `backend/.../visualizacion_geoespacial/constants.py`: límites compartidos por consulta y análisis.

Las opciones de capas se memorizan para no recrear los objetos Leaflet al editar
filtros todavía no aplicados o abrir detalles. Las preferencias guardadas solo
aceptan las claves y valores booleanos de las capas existentes.

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
