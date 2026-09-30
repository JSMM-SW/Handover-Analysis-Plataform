# Historias de usuario

Se construyen de forma incremental, iteración a iteración, según la metodología XP definida en el plan de tesis.

---

## HU-01 — Carga de archivo Excel

**Descripción:**
Como usuario de la plataforma, quiero cargar un archivo Excel con datos de handover, para que el sistema lo reciba y verifique que es un archivo válido antes de procesarlo.

**Criterios de aceptación:**
- El usuario puede seleccionar un archivo `.xlsx` desde el navegador.
- Si el archivo no tiene extensión `.xlsx`, el sistema rechaza la carga con un mensaje de error claro.
- Si el archivo está vacío o supera el tamaño máximo configurado, el sistema lo rechaza.
- El archivo se envía al backend mediante una petición HTTP real a FastAPI (sin datos simulados).

**Prioridad:** Alta
**Iteración:** 1

---

## HU-02 — Información básica del archivo cargado

**Descripción:**
Como usuario de la plataforma, quiero ver información básica del archivo cargado (hojas, número de filas, número de columnas y encabezados), para confirmar que el sistema leyó correctamente mi archivo antes de que se le apliquen reglas de negocio.

**Criterios de aceptación:**
- Tras una carga exitosa, el sistema muestra el nombre de cada hoja del Excel.
- Se muestra el número de filas y columnas de cada hoja.
- Se muestra un identificador de ejecución (`execution_id`) único para esa carga.
- Se muestra el tiempo de procesamiento.
- Si el archivo está corrupto o no puede interpretarse como Excel, el sistema informa un error (HTTP 422) en lugar de fallar silenciosamente.

**Prioridad:** Alta
**Iteración:** 1
