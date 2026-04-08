from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.dependencies import get_settings
from app.routers.observer import router as observer_router
from app.routers.webhooks import router as webhook_router
from app.services.evolution_api import EvolutionApiError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting AuraCore backend.")
    yield
    logger.info("Stopping AuraCore backend.")


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(observer_router)
app.include_router(webhook_router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.environment,
        "status": "ok",
    }


@app.get("/health", tags=["meta"])
async def healthcheck() -> dict[str, str]:
    return {"status": "healthy"}


@app.exception_handler(EvolutionApiError)
async def evolution_api_error_handler(_: Request, exc: EvolutionApiError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
