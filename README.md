# Módulo de ingesta y procesamiento de datos de handover

Componente ETL de la plataforma "Análisis y visualización de handovers en redes celulares" (Trabajo de Integración Curricular). Recibe archivos CSV con mediciones de handover, los valida, procesa y estructura como dataset para los módulos de visualización temporal, geoespacial y KPIs.

Desarrollo iterativo bajo Extreme Programming (XP). Ver [docs/historias-usuario.md](docs/historias-usuario.md) y [docs/decisiones/](docs/decisiones/) para las decisiones de arquitectura documentadas para la tesis.

## Estado actual (Iteración 1)

La ingesta admite solo CSV, valida y limpia mediciones, calcula velocidad y conserva las señales originales. Consulta [la migración de señales](docs/migracion_csv_senales.md) antes de actualizar una base existente.

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
