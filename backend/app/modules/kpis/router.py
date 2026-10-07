"""
Endpoints del módulo de KPIs. Cada uno arma su `KpisRepository`, delega el
cálculo a `kpis/services.py` y devuelve el modelo de respuesta -- no hay
lógica de negocio aquí, solo el cableado HTTP (mismo patrón que
`ingesta/router.py`).
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.shared.db.database import get_db
from app.modules.kpis.repository import KpisRepository
from app.modules.kpis.schemas import (
    DiaSemanaResponse,
    FranjaHorariaResponse,
    HourlyDistributionResponse,
    KpiSummaryResponse,
    SesionResponse,
    SignalMetricsResponse,
    TrendResponse,
)
from app.modules.kpis.services import (
    calcular_distribucion_dia_semana,
    calcular_distribucion_franja_horaria,
    calcular_distribucion_horaria,
    calcular_metricas_globales_dia,
    calcular_resumen_kpis,
    calcular_tendencia,
    listar_sesiones,
)

router = APIRouter(prefix="/kpis", tags=["Análisis de Desempeño"])


@router.get("/daily", response_model=SignalMetricsResponse)
def obtener_kpis_diarios(target_date: date, db: Session = Depends(get_db)):
    """Calidad de señal general de un día puntual (no es específico de handovers)."""
    repositorio = KpisRepository(db)
    return calcular_metricas_globales_dia(target_date, repositorio)


@router.get("/sesiones", response_model=list[SesionResponse])
def obtener_sesiones(db: Session = Depends(get_db)):
    """Lista las sesiones (cargas de archivo) disponibles para filtrar los demás endpoints por sesión."""
    repositorio = KpisRepository(db)
    return listar_sesiones(repositorio)


@router.get("/summary", response_model=KpiSummaryResponse)
def obtener_resumen_kpis(
    start_date: date,
    end_date: date,
    tecnologia: list[int] | None = Query(default=None),
    franja: list[Literal["manana", "tarde", "noche"]] | None = Query(default=None),
    sesion_label: list[int] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Resumen agregado de KPIs de handover para un rango de fechas.

    `tecnologia`, `franja` y `sesion_label` son filtros multi-selección
    (repetir el parámetro, ej. `?tecnologia=1&tecnologia=2`). Sin
    especificarlos, o con una selección vacía, se incluyen todos los
    valores.
    """
    repositorio = KpisRepository(db)
    return calcular_resumen_kpis(start_date, end_date, repositorio, tecnologia, franja, sesion_label)


@router.get("/hourly", response_model=list[HourlyDistributionResponse])
def obtener_distribucion_horaria(
    start_date: date,
    end_date: date,
    tecnologia: list[int] | None = Query(default=None),
    franja: list[Literal["manana", "tarde", "noche"]] | None = Query(default=None),
    sesion_label: list[int] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Distribución de handovers por hora del día (0-23), desglosada por categoría."""
    repositorio = KpisRepository(db)
    return calcular_distribucion_horaria(start_date, end_date, repositorio, tecnologia, franja, sesion_label)


@router.get("/franja-horaria", response_model=list[FranjaHorariaResponse])
def obtener_distribucion_franja_horaria(
    start_date: date,
    end_date: date,
    tecnologia: list[int] | None = Query(default=None),
    sesion_label: list[int] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Igual que /hourly, pero agrupado en 3 franjas (mañana/tarde/noche) en vez de 24 horas."""
    repositorio = KpisRepository(db)
    return calcular_distribucion_franja_horaria(start_date, end_date, repositorio, tecnologia, sesion_label)


@router.get("/dia-semana", response_model=list[DiaSemanaResponse])
def obtener_distribucion_dia_semana(
    start_date: date,
    end_date: date,
    tecnologia: list[int] | None = Query(default=None),
    franja: list[Literal["manana", "tarde", "noche"]] | None = Query(default=None),
    sesion_label: list[int] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Distribución de handovers por día de la semana (Lunes a Domingo), desglosada por categoría."""
    repositorio = KpisRepository(db)
    return calcular_distribucion_dia_semana(start_date, end_date, repositorio, tecnologia, franja, sesion_label)


@router.get("/trend", response_model=list[TrendResponse])
def obtener_tendencia(
    start_date: date,
    end_date: date,
    periodo: Literal["diario", "semanal", "mensual", "anual"] = "diario",
    tecnologia: list[int] | None = Query(default=None),
    franja: list[Literal["manana", "tarde", "noche"]] | None = Query(default=None),
    sesion_label: list[int] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Evolución de los KPIs de handover a lo largo del tiempo, agrupada por `periodo`."""
    repositorio = KpisRepository(db)
    return calcular_tendencia(start_date, end_date, repositorio, periodo, tecnologia, franja, sesion_label)
