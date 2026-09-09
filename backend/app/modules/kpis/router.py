from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.db.database import get_db
from app.modules.kpis.repository import KpisRepository
from app.modules.kpis.schemas import SignalMetricsResponse, KpiSummaryResponse
from app.modules.kpis.services import calculate_global_kpis, calculate_kpi_summary

router = APIRouter(prefix="/kpis", tags=["Análisis de Desempeño"])

@router.get("/daily", response_model=SignalMetricsResponse)
def get_daily_kpis(
    target_date: date,
    db: Session = Depends(get_db)
):
    repo = KpisRepository(db)
    return calculate_global_kpis(target_date, repo)

@router.get("/summary", response_model=KpiSummaryResponse)
def get_kpi_summary(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    repo = KpisRepository(db)
    return calculate_kpi_summary(start_date, end_date, repo)

from app.modules.kpis.schemas import HourlyDistributionResponse
from app.modules.kpis.services import calculate_hourly_distribution

@router.get("/hourly", response_model=list[HourlyDistributionResponse])
def get_hourly_distribution(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    repo = KpisRepository(db)
    return calculate_hourly_distribution(start_date, end_date, repo)


from app.modules.kpis.schemas import DailyTrendResponse
from app.modules.kpis.services import calculate_daily_trend

@router.get("/trend", response_model=list[DailyTrendResponse])
def get_daily_trend(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    repo = KpisRepository(db)
    return calculate_daily_trend(start_date, end_date, repo)