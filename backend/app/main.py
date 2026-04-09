from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from contextlib import suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.chat import router as chat_router
from app.dependencies import get_automation_service, get_settings
from app.routers.automation import router as automation_router
from app.routers.internal_agent import router as internal_agent_router
from app.routers.internal import router as internal_router
from app.routers.memories import router as memories_router
from app.routers.observer import router as observer_router
from app.routers.whatsapp_agent import router as whatsapp_agent_router
from app.services.chat_service import ChatServiceError
from app.services.deepseek_service import DeepSeekError
from app.services.groq_service import GroqChatError
from app.services.memory_service import MemoryAnalysisError
from app.services.observer_gateway import ObserverGatewayError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting AuraCore backend.")
    task = asyncio.create_task(_automation_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
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
app.include_router(memories_router)
app.include_router(chat_router)
app.include_router(internal_router)
app.include_router(internal_agent_router)
app.include_router(automation_router)
app.include_router(whatsapp_agent_router)


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


@app.exception_handler(ObserverGatewayError)
async def observer_gateway_error_handler(_: Request, exc: ObserverGatewayError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


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


async def _automation_loop() -> None:
    # Let the HTTP server finish binding before background automation starts.
    await asyncio.sleep(2)
    while True:
        try:
            automation_service = get_automation_service()
            await automation_service.tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automation tick failed.")
        await asyncio.sleep(60)
