# Módulo de ingesta y procesamiento de datos de handover

Componente ETL de la plataforma "Análisis y visualización de handovers en redes celulares" (Trabajo de Integración Curricular). Recibe archivos Excel con mediciones de handover, los valida, procesa y estructura como dataset para los módulos de visualización temporal, geoespacial y KPIs.

Desarrollo iterativo bajo Extreme Programming (XP). Ver [docs/historias-usuario.md](docs/historias-usuario.md) y [docs/decisiones/](docs/decisiones/) para las decisiones de arquitectura documentadas para la tesis.

## Estado actual (Iteración 1)

MVP: carga de un archivo `.xlsx` desde el navegador, validación a nivel de archivo (extensión/tamaño/integridad) y extracción de información básica (hojas, filas, columnas, encabezados). Las reglas de limpieza y normalización aún no están implementadas: se definirán tras analizar un archivo real de handover.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # opcional, valores por defecto ya funcionan
```

## Ejecución

```bash
uvicorn app.main:app --reload --app-dir backend
```

Abrir [http://127.0.0.1:8000](http://127.0.0.1:8000) para la interfaz web, o [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) para la documentación Swagger/OpenAPI.

## Pruebas

```bash
pytest
```
