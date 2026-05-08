from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Subscription, Usage, User
from app.services.errors import AIServiceError
from app.services.image import generate_image_base64
from app.services.orchestrator import run_orchestrator, stream_orchestrator
from app.services.rate_limit import check_and_consume_user_request

router = APIRouter(prefix="/chat", tags=["chat"])

FREE_PLAN_MAX_OUTPUT_TOKENS = 400
PRO_PLAN_MAX_OUTPUT_TOKENS = 1600


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=12000)


class ChatAttachment(BaseModel):
    type: str = Field(pattern="^(image|file_text|file_binary)$")
    name: str | None = Field(default=None, max_length=255)
    mime_type: str | None = Field(default=None, max_length=120)
    data_base64: str | None = Field(default=None, max_length=20_000_000)
    text: str | None = Field(default=None, max_length=120_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=12)
    inference_mode: str = Field(default="local", pattern="^(local|cloud)$")


class ChatResponse(BaseModel):
    assistant_message: str
    plan: str
    remaining_daily: int
    intent: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    image_data_url: str | None = None
    upload_result: dict[str, Any] | None = None


class ChatHistoryResponse(BaseModel):
    messages: list[dict]


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class ImageResponse(BaseModel):
    assistant_message: str
    image_data_url: str
    plan: str
    remaining_daily: int


class PrivacyStatusResponse(BaseModel):
    local_history_storage: str
    server_content_storage: str
    encryption_key_location: str
    cloud_mode_enabled: bool
    cloud_mode_warning: str


def _plan_for_user(db: Session, user_id: int) -> str:
    subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if not subscription:
        return "free"
    if subscription.expiry and subscription.expiry.tzinfo is None:
        subscription.expiry = subscription.expiry.replace(tzinfo=timezone.utc)
    if subscription.expiry and subscription.expiry < datetime.now(timezone.utc):
        subscription.plan = "free"
        subscription.status = "expired"
        db.commit()
    return subscription.plan


def _max_tokens_for_plan(plan: str) -> int:
    return PRO_PLAN_MAX_OUTPUT_TOKENS if plan == "pro" else FREE_PLAN_MAX_OUTPUT_TOKENS


def _increment_usage_counter(db: Session, user_id: int) -> None:
    usage = db.query(Usage).filter(Usage.user_id == user_id).first()
    if usage:
        usage.requests_count += 1
        db.commit()


@router.get("/messages", response_model=ChatHistoryResponse)
def get_messages() -> ChatHistoryResponse:
    return ChatHistoryResponse(messages=[])


@router.get("/privacy-status", response_model=PrivacyStatusResponse)
def privacy_status() -> PrivacyStatusResponse:
    return PrivacyStatusResponse(
        local_history_storage="Encrypted IndexedDB on user device only.",
        server_content_storage="Server does not persist prompts, responses, files, embeddings, or summaries.",
        encryption_key_location="Generated and stored locally in browser key store.",
        cloud_mode_enabled=False,
        cloud_mode_warning="Cloud inference requires explicit user opt-in per request.",
    )


@router.post("/message", response_model=ChatResponse)
def send_message(payload: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ChatResponse:
    plan = _plan_for_user(db, current_user.id)
    allowed, remaining = check_and_consume_user_request(current_user.id, plan)
    if not allowed:
        raise HTTPException(status_code=429, detail="Daily request limit reached for your plan.")

    messages = [message.model_dump() for message in payload.messages]
    attachments = [attachment.model_dump() for attachment in payload.attachments]
    allow_cloud = payload.inference_mode == "cloud"
    try:
        result = run_orchestrator(
            messages=messages,
            attachments=attachments,
            max_tokens=_max_tokens_for_plan(plan),
            allow_cloud_fallback=allow_cloud,
        )
        _increment_usage_counter(db, current_user.id)
        return ChatResponse(
            assistant_message=result.assistant_message,
            image_data_url=result.image_data_url,
            plan=plan,
            remaining_daily=remaining,
            intent=result.decision.task.value,
            artifacts=result.artifacts,
            upload_result=result.upload_result,
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/stream")
def stream_message(payload: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plan = _plan_for_user(db, current_user.id)
    allowed, remaining = check_and_consume_user_request(current_user.id, plan)
    if not allowed:
        raise HTTPException(status_code=429, detail="Daily request limit reached for your plan.")

    messages = [message.model_dump() for message in payload.messages]
    attachments = [attachment.model_dump() for attachment in payload.attachments]
    allow_cloud = payload.inference_mode == "cloud"

    def event_stream():
        try:
            for event in stream_orchestrator(
                messages=messages,
                attachments=attachments,
                max_tokens=_max_tokens_for_plan(plan),
                allow_cloud_fallback=allow_cloud,
            ):
                yield f"data: {json.dumps(event)}\n\n"
            _increment_usage_counter(db, current_user.id)
            yield f"data: {json.dumps({'type': 'done', 'plan': plan, 'remaining_daily': remaining})}\n\n"
        except AIServiceError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Unexpected error: {exc}'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/image", response_model=ImageResponse)
def image_message(payload: ImageRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ImageResponse:
    plan = _plan_for_user(db, current_user.id)
    allowed, remaining = check_and_consume_user_request(current_user.id, plan)
    if not allowed:
        raise HTTPException(status_code=429, detail="Daily request limit reached for your plan.")
    try:
        result = generate_image_base64(payload.prompt)
        _increment_usage_counter(db, current_user.id)
        return ImageResponse(
            assistant_message=result["assistant_message"],
            image_data_url=f"data:{result['mime_type']};base64,{result['image_base64']}",
            plan=plan,
            remaining_daily=remaining,
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
