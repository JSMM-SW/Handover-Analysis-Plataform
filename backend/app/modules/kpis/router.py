from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.db.database import get_db
from app.modules.kpis.repository import KpisRepository
from app.modules.kpis.schemas import (
    FranjaHorariaResponse,
    HourlyDistributionResponse,
    KpiSummaryResponse,
    SignalMetricsResponse,
    TrendResponse,
)
from app.modules.kpis.services import (
    calcular_distribucion_franja_horaria,
    calcular_distribucion_horaria,
    calcular_metricas_globales_dia,
    calcular_resumen_kpis,
    calcular_tendencia,
)

router = APIRouter(prefix="/kpis", tags=["Análisis de Desempeño"])


@router.get("/daily", response_model=SignalMetricsResponse)
def obtener_kpis_diarios(target_date: date, db: Session = Depends(get_db)):
    """Calidad de señal general de un día puntual (no es específico de handovers)."""
    repositorio = KpisRepository(db)
    return calcular_metricas_globales_dia(target_date, repositorio)


@router.get("/summary", response_model=KpiSummaryResponse)
def obtener_resumen_kpis(
    start_date: date,
    end_date: date,
    tecnologia: int | None = None,
    franja: Literal["manana", "tarde", "noche"] | None = None,
    db: Session = Depends(get_db),
):
    """Resumen agregado de KPIs de handover para un rango de fechas.

    `tecnologia` es opcional: 0=sin señal, 1=LTE/4G, 2=3G/UMTS. `franja` es
    opcional: 'manana' (06-11:59), 'tarde' (12-18:59) o 'noche' (19-05:59).
    Sin especificarlas, se incluyen todas las tecnologías/horas.
    """
    repositorio = KpisRepository(db)
    return calcular_resumen_kpis(start_date, end_date, repositorio, tecnologia, franja)



@router.get("/hourly", response_model=list[HourlyDistributionResponse])
def obtener_distribucion_horaria(
    start_date: date,
    end_date: date,
    tecnologia: int | None = None,
    franja: Literal["manana", "tarde", "noche"] | None = None,
    db: Session = Depends(get_db),
):
    """Distribución de handovers por hora del día (0-23), desglosada por categoría."""
    repositorio = KpisRepository(db)
    return calcular_distribucion_horaria(start_date, end_date, repositorio, tecnologia, franja)



@router.get("/franja-horaria", response_model=list[FranjaHorariaResponse])
def obtener_distribucion_franja_horaria(
    start_date: date,
    end_date: date,
    tecnologia: int | None = None,
    db: Session = Depends(get_db),
):
    """Igual que /hourly, pero agrupado en 3 franjas (mañana/tarde/noche) en vez de 24 horas."""
    repositorio = KpisRepository(db)
    return calcular_distribucion_franja_horaria(start_date, end_date, repositorio, tecnologia)


@router.get("/trend", response_model=list[TrendResponse])
def obtener_tendencia(
    start_date: date,
    end_date: date,
    periodo: Literal["diario", "semanal", "mensual", "anual"] = "diario",
    tecnologia: int | None = None,
    franja: Literal["manana", "tarde", "noche"] | None = None,
    db: Session = Depends(get_db),
):
    """Evolución de los KPIs de handover a lo largo del tiempo, agrupada por `periodo`."""
    repositorio = KpisRepository(db)
    return calcular_tendencia(start_date, end_date, repositorio, periodo, tecnologia, franja)

