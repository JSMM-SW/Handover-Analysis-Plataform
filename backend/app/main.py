# main.py corregido
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.shared.logging import setup_logging
from app.api.routes.health import router as health_router  # <-- RUTA CORREGIDA
from app.modules.ingesta.router import router as ingesta_router

setup_logging()

app = FastAPI(
    title="Plataforma de Análisis de Handovers",
    description="API para ingesta, análisis temporal, geoespacial y métricas QoE",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusión de Enrutadores Modulares
app.include_router(health_router, prefix="/api/v1") # <-- Endpoint del sistema
app.include_router(ingesta_router, prefix="/api/v1")