from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import health, ingestion
from app.core.logging import setup_logging

setup_logging()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title="Handover Ingestion ETL",
    description="Módulo de ingesta y procesamiento de datos de handover",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")

app.include_router(health.router, prefix="/api/v1")
app.include_router(ingestion.router, prefix="/api/v1")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
