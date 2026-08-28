# ADR-001 — Arquitectura inicial del módulo ETL de ingesta

**Estado:** Aceptada (Iteración 1)

## Problema

Se necesita una arquitectura para un módulo ETL que reciba archivos Excel de mediciones de handover, los valide, procese y deje disponibles como dataset para otros módulos de la plataforma (visualización temporal, geoespacial y KPIs). El plan de tesis exige que el diseño sea justificable académicamente y que el desarrollo siga XP (iterativo, incremental).

## Decisión

Arquitectura en capas, con el flujo:

```
Frontend (Jinja2 + HTML/CSS/JS) → API REST (FastAPI, /api/v1) → Service Layer → ETL Pipeline (Extract/Validate/Clean/Normalize/Structure/Load) → Repository (futuro) → Base de datos (futuro)
```

Para la Iteración 1 se implementan únicamente las etapas **Validate** (a nivel de archivo: extensión, tamaño, contenido no vacío) y **Extract** (lectura de metadatos de hojas con `openpyxl`). Las etapas Clean, Normalize, Structure y Load, así como la capa Repository, se difieren a iteraciones posteriores.

## Justificación

- **Separación de responsabilidades:** cada etapa del ETL es una función pura y testeable de forma aislada, sin depender de FastAPI ni del sistema de archivos más de lo necesario.
- **No acoplar el dominio a la persistencia:** el Service Layer y el ETL no conocen SQLAlchemy ni ningún motor de base de datos; la futura capa Repository absorberá ese acoplamiento cuando se implemente la etapa Load.
- **No invención de reglas de negocio:** las etapas Clean/Normalize no se implementan aún porque sus reglas dependen del análisis de un archivo real de handover (Objetivo 2 del plan de tesis). Crear stubs vacíos ahora sería código muerto y contradice el principio YAGNI de XP.

## Alternativas consideradas

1. **Monolito en `main.py`** — descartada: dificulta pruebas unitarias, viola separación de responsabilidades exigida en el plan de tesis.
2. **Crear todos los módulos del pipeline (incluyendo Clean/Normalize/Load) como stubs desde el inicio** — descartada: introduce código sin comportamiento real, no aporta valor verificable en la Iteración 1 y contradice XP (implementar solo lo que una historia de usuario requiere).
3. **Frontend en React/Vue consumiendo la API** — descartada por requisito explícito del plan: frontend dentro del ecosistema Python para esta primera versión.

## Ventajas

- Cada etapa puede probarse de forma unitaria sin levantar el servidor HTTP.
- El Service Layer permite cambiar la implementación de persistencia (Iteración 8) sin tocar las reglas de negocio del ETL.
- La estructura de carpetas mapea directamente a los objetivos específicos del plan de tesis, facilitando la redacción de la memoria.

## Desventajas / riesgos

- Al no existir aún la capa Repository, el resultado de la Iteración 1 no persiste en base de datos (se devuelve solo al frontend). Esto es aceptado como alcance explícito del MVP.
- Las validaciones de negocio (columnas obligatorias, tipos de dato) no existen todavía; hasta que se analice un archivo real, el sistema solo garantiza que el archivo es un Excel legible, no que su contenido sea válido para el dominio de handover.
