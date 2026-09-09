# Visualización geoespacial

Primera versión conectada a PostgreSQL mediante la sesión compartida `get_db`.
Solo consulta información: no modifica tablas ni vuelve a procesar archivos.

## Ejecutar en Windows

Desde la raíz, con el entorno virtual de este equipo:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend
```

En otra terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Abrir http://localhost:5173/geoespacial o usar el menú lateral. Ingesta sigue
disponible en `/ingesta`. En un despliegue, configurar el servidor del frontend
para devolver `index.html` para las rutas de la aplicación.

La conexión real se configura exclusivamente en `.env` de la raíz, mediante
`DATABASE_URL`. El frontend usa `http://localhost:8000/api/v1` por defecto; se
puede cambiar con `VITE_API_URL` en `frontend/.env.local` y reiniciar Vite.
No colocar credenciales de PostgreSQL en variables VITE.

## Uso y límites

1. Seleccionar una ejecución completada y una hoja.
2. Ver puntos GPS y trayectoria aproximada. Un clic en un punto abre sus detalles.
3. Aplicar filtros por fecha/hora de Ecuador (UTC-5), tecnología o celda.
4. Para filtrar por zona, desplazar/acercar el mapa y pulsar **Filtrar por zona visible**.
5. Cambiar entre **Mapa de rutas y handovers** y **Mapa de calor**. Los filtros
   del panel izquierdo se conservan al cambiar de pestaña. La primera vista
   muestra puntos y trayectoria; los handovers siguen pendientes de identificación.
   La segunda muestra únicamente calor de mediciones. La elección de las capas
   de puntos y trayectoria se conserva en sessionStorage. Las selecciones de
   archivo y filtros se reinician al salir del módulo. En pantallas pequeñas,
   el panel de filtros aparece encima del mapa.

El calor representa concentración relativa de **mediciones**, no handovers,
y cambia con el zoom. Los colores de puntos representan intervalos de RSRP
indicados en la leyenda; no son un diagnóstico de calidad de servicio.

La hoja se usa como agrupación provisional. Confirmar que representa un solo
recorrido antes de interpretar su trayectoria. Se cortan las líneas en huecos
mayores de 60 segundos, horas repetidas, cambios de hoja y puntos excluidos por
los filtros. El umbral de 60 segundos es una regla inicial de visualización.
No se estiman rutas por calles ni posiciones entre mediciones.

La API admite hasta 20.000 registros por ejecución/hoja/intervalo temporal;
si se supera, pide reducir el intervalo, sin truncar silenciosamente. Los
filtros de celda, tecnología y zona se aplican después de leer esa secuencia
para conservar los cortes entre puntos excluidos.

Velocidad, detección de handovers y estaciones base no están implementadas:
requieren reglas o fuentes adicionales. Tampoco se implementa importación CSV,
exportación de mapas ni cambio de proveedor del mapa base en esta entrega.

## API

- `GET /api/v1/geoespacial/ejecuciones`: ejecuciones completadas.
- `GET /api/v1/geoespacial/ejecuciones/{execution_id}/hojas`: hojas disponibles.
- `GET /api/v1/geoespacial/mediciones`: parámetros `execution_id`, `hoja`,
  `desde`, `hasta`, `tecnologia`, `cell_id`, `bbox` (oeste,sur,este,norte).

Las fechas de la API requieren zona horaria; los extremos temporales son inclusivos.
La respuesta contiene `mediciones`, `tramos` (listas de IDs de puntos), `total`
y `advertencias`. Consultas vacías devuelven 200, parámetros inválidos 422,
ejecución/hoja inexistente 404 y fallos de base de datos 503 sin credenciales.

## Verificación

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit tests/integration/test_upload_endpoint.py tests/integration/test_geoespacial_endpoints.py -q
.\venv\Scripts\python.exe tests/check_geoespacial_readonly.py
cd frontend
npm.cmd run build
npm.cmd run lint
npm.cmd run test:e2e
```

Las pruebas automáticas usan datos de prueba. El script `check_geoespacial_readonly.py`
consulta la base configurada, comprueba la ejecución más reciente y no escribe datos.
Las pruebas de navegador usan Edge en Windows. En otros sistemas instalar Chromium
con `npx playwright install chromium`. El servidor de pruebas usa el puerto 5174.

El mapa usa [Leaflet](https://leafletjs.com/reference) y teselas de OpenStreetMap,
que requieren Internet. La navegación usa [React Router](https://reactrouter.com/start/declarative/routing).
