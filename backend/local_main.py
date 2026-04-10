from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.dependencies import get_settings
from app.routers.chat import router as chat_router
from app.routers.internal import router as internal_router
from app.routers.internal_agent import router as internal_agent_router
from app.routers.memories import router as memories_router
from app.routers.observer import router as observer_router
from app.routers.whatsapp_agent import router as whatsapp_agent_router

settings = get_settings()

app = FastAPI(title=f"{settings.app_name} (Local)")
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
app.include_router(whatsapp_agent_router)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": "local",
        "status": "ok",
    }


@app.get("/health", tags=["meta"])
async def healthcheck() -> dict[str, str]:
    return {"status": "healthy"}
