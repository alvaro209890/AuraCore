from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.automation import router as automation_router
from app.routers.chat import router as chat_router
from app.dependencies import get_automation_service, get_settings
from app.routers.internal_agent import router as internal_agent_router
from app.routers.internal import router as internal_router
from app.routers.internal_storage import router as internal_storage_router
from app.routers.memories import router as memories_router
from app.routers.observer import router as observer_router
from app.routers.whatsapp_agent import router as whatsapp_agent_router
from app.services.chat_service import ChatServiceError
from app.services.deepseek_service import DeepSeekError
from app.services.groq_service import GroqChatError
from app.services.memory_service import MemoryAnalysisError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(observer_router)
app.include_router(memories_router)
app.include_router(chat_router)
app.include_router(automation_router)
app.include_router(internal_router)
app.include_router(internal_agent_router)
app.include_router(internal_storage_router)
app.include_router(whatsapp_agent_router)


@app.on_event("startup")
async def schedule_automation_warm_start() -> None:
    get_automation_service().warm_start()


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


@app.exception_handler(DeepSeekError)
async def deepseek_error_handler(_: Request, exc: DeepSeekError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(MemoryAnalysisError)
async def memory_analysis_error_handler(_: Request, exc: MemoryAnalysisError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ChatServiceError)
async def chat_service_error_handler(_: Request, exc: ChatServiceError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(GroqChatError)
async def groq_chat_error_handler(_: Request, exc: GroqChatError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})
