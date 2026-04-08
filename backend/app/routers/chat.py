from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.dependencies import get_chat_assistant_service
from app.routers.memories import _to_persona_response, _to_project_response
from app.schemas import ChatMessageResponse, ChatSessionResponse, SendChatMessageRequest
from app.services.chat_service import ChatAssistantService
from app.services.supabase_store import ChatMessageRecord

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/session", response_model=ChatSessionResponse)
async def get_chat_session(
    chat_service: ChatAssistantService = Depends(get_chat_assistant_service),
) -> ChatSessionResponse:
    session = chat_service.get_session()
    return ChatSessionResponse(
        thread_id=session.thread.id,
        title=session.thread.title,
        current=_to_persona_response(session.persona),
        projects=[_to_project_response(project) for project in session.projects],
        messages=[_to_chat_message_response(message) for message in session.messages],
    )


@router.post("/messages", response_model=ChatSessionResponse)
async def send_chat_message(
    request: SendChatMessageRequest = Body(...),
    chat_service: ChatAssistantService = Depends(get_chat_assistant_service),
) -> ChatSessionResponse:
    session = await chat_service.send_message(message_text=request.message_text)
    return ChatSessionResponse(
        thread_id=session.thread.id,
        title=session.thread.title,
        current=_to_persona_response(session.persona),
        projects=[_to_project_response(project) for project in session.projects],
        messages=[_to_chat_message_response(message) for message in session.messages],
    )


def _to_chat_message_response(message: ChatMessageRecord) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )
