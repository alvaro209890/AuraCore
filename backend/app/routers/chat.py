from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from app.dependencies import get_chat_assistant_service
from app.routers.memories import _to_persona_response, _to_project_response
from app.schemas import (
    ChatMessageResponse,
    ChatSessionResponse,
    ChatThreadResponse,
    ChatWorkspaceResponse,
    CreateChatThreadRequest,
    SendChatMessageRequest,
)
from app.services.chat_service import ChatAssistantService, ChatSessionState, ChatThreadSummary, ChatWorkspaceState
from app.services.supabase_store import ChatMessageRecord

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/session", response_model=ChatSessionResponse)
async def get_chat_session(
    thread_id: str | None = Query(default=None),
    chat_service: ChatAssistantService = Depends(get_chat_assistant_service),
) -> ChatSessionResponse:
    session = chat_service.get_session(thread_id=thread_id)
    return _to_chat_session_response(session)


@router.get("/workspace", response_model=ChatWorkspaceResponse)
async def get_chat_workspace(
    thread_id: str | None = Query(default=None),
    chat_service: ChatAssistantService = Depends(get_chat_assistant_service),
) -> ChatWorkspaceResponse:
    workspace = chat_service.get_workspace(thread_id=thread_id)
    return _to_chat_workspace_response(workspace)


@router.post("/threads", response_model=ChatWorkspaceResponse)
async def create_chat_thread(
    request: CreateChatThreadRequest | None = Body(default=None),
    chat_service: ChatAssistantService = Depends(get_chat_assistant_service),
) -> ChatWorkspaceResponse:
    workspace = chat_service.create_thread(title=request.title if request is not None else None)
    return _to_chat_workspace_response(workspace)


@router.post("/messages", response_model=ChatWorkspaceResponse)
async def send_chat_message(
    request: SendChatMessageRequest = Body(...),
    chat_service: ChatAssistantService = Depends(get_chat_assistant_service),
) -> ChatWorkspaceResponse:
    workspace = await chat_service.send_message(
        message_text=request.message_text,
        thread_id=request.thread_id,
    )
    return _to_chat_workspace_response(workspace)


def _to_chat_message_response(message: ChatMessageRecord) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


def _to_chat_thread_response(summary: ChatThreadSummary) -> ChatThreadResponse:
    return ChatThreadResponse(
        id=summary.thread.id,
        thread_key=summary.thread.thread_key,
        title=summary.thread.title,
        message_count=summary.message_count,
        last_message_preview=summary.last_message_preview,
        last_message_role=summary.last_message_role,
        last_message_at=summary.last_message_at,
        created_at=summary.thread.created_at,
        updated_at=summary.thread.updated_at,
    )


def _to_chat_session_response(session: ChatSessionState) -> ChatSessionResponse:
    return ChatSessionResponse(
        thread_id=session.thread.id,
        title=session.thread.title,
        current=_to_persona_response(session.persona),
        projects=[_to_project_response(project) for project in session.projects],
        messages=[_to_chat_message_response(message) for message in session.messages],
    )


def _to_chat_workspace_response(workspace: ChatWorkspaceState) -> ChatWorkspaceResponse:
    return ChatWorkspaceResponse(
        active_thread_id=workspace.session.thread.id,
        threads=[_to_chat_thread_response(thread) for thread in workspace.threads],
        session=_to_chat_session_response(workspace.session),
    )
