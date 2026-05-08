from __future__ import annotations

import json
import os
import time
from typing import Callable
from typing import Iterable

import httpx
from dotenv import load_dotenv

from app.services.errors import AIServiceError

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
DEFAULT_LLM_SYSTEM_PROMPT = (
    "You are a reliable multi-agent AI assistant. "
    "Be concise, factual, and privacy-preserving. "
    "Never fabricate capabilities, analysis results, file metadata, image details, resolution, or technical specs. "
    "If required input is missing (for example an image/file is not actually attached), explicitly say what is missing and ask for it."
)
LLM_SYSTEM_PROMPT = os.getenv("LLM_SYSTEM_PROMPT", DEFAULT_LLM_SYSTEM_PROMPT)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "moondream")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
OLLAMA_NUM_CTX = max(512, int(os.getenv("OLLAMA_NUM_CTX", "2048")))
OLLAMA_NUM_BATCH = max(16, int(os.getenv("OLLAMA_NUM_BATCH", "128")))
OLLAMA_MIN_BATCH = max(8, int(os.getenv("OLLAMA_MIN_BATCH", "16")))
OLLAMA_TEXT_FALLBACK_MODEL = os.getenv("OLLAMA_TEXT_FALLBACK_MODEL", "llama3.2:1b").strip()
OLLAMA_VISION_FALLBACK_MODEL = os.getenv("OLLAMA_VISION_FALLBACK_MODEL", "").strip()

OPENAI_COMPAT_BASE_URL = os.getenv("OPENAI_COMPAT_BASE_URL", "https://api.openai.com/v1")
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "")
OPENAI_COMPAT_MODEL = os.getenv("OPENAI_COMPAT_MODEL", "gpt-4o-mini")
OPENAI_COMPAT_TIMEOUT_SECONDS = float(os.getenv("OPENAI_COMPAT_TIMEOUT_SECONDS", "120"))
STREAM_RETRY_ATTEMPTS = max(1, int(os.getenv("STREAM_RETRY_ATTEMPTS", "3")))
STREAM_RETRY_BACKOFF_SECONDS = float(os.getenv("STREAM_RETRY_BACKOFF_SECONDS", "0.8"))

VISION_MODEL_HINTS = ("vision", "llava", "bakllava", "moondream", "minicpm")
RESOURCE_ERROR_HINTS = (
    "failed to allocate",
    "unable to allocate",
    "not enough memory",
    "out of memory",
    "runner process has terminated",
    "failed to initialize the context",
)


def _compose_messages(messages: Iterable[dict], extra_context: str | None = None) -> list[dict]:
    merged = [{"role": "system", "content": LLM_SYSTEM_PROMPT}]
    if extra_context and extra_context.strip():
        merged.append(
            {
                "role": "system",
                "content": f"Relevant file context (ephemeral, never store):\n{extra_context.strip()}",
            }
        )
    for item in messages:
        role = item.get("role", "user")
        content = str(item.get("content", "")).strip()
        if content:
            merged.append({"role": role, "content": content})
    if len(merged) == 1:
        merged.append({"role": "user", "content": "Hello"})
    return merged


def _compose_messages_with_images(
    messages: Iterable[dict],
    *,
    extra_context: str | None = None,
    image_attachments: list[str] | None = None,
) -> list[dict]:
    merged = _compose_messages(messages, extra_context=extra_context)
    images = [item for item in (image_attachments or []) if str(item).strip()]
    if images:
        merged.append(
            {
                "role": "user",
                "content": "Use the attached image(s) while answering the user request.",
                "images": images,
            }
        )
    return merged


def _looks_like_vision_model(model_name: str) -> bool:
    normalized = str(model_name or "").lower()
    return any(hint in normalized for hint in VISION_MODEL_HINTS)


def _fetch_ollama_model_names() -> list[str]:
    endpoint = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        response = httpx.get(endpoint, timeout=15)
        if response.status_code >= 400:
            return []
        payload = response.json()
        models = payload.get("models", [])
        return [str(item.get("name", "")).strip() for item in models if str(item.get("name", "")).strip()]
    except Exception:
        return []


def _resolve_ollama_model_for_messages(messages: list[dict]) -> str:
    has_images = any(isinstance(message.get("images"), list) and message.get("images") for message in messages)
    if not has_images:
        return OLLAMA_MODEL

    available_models = _fetch_ollama_model_names()
    configured = OLLAMA_VISION_MODEL.strip()
    if configured and configured in available_models:
        return configured

    discovered = next((item for item in available_models if _looks_like_vision_model(item)), None)
    if discovered:
        return discovered

    raise AIServiceError(
        "Image analysis requires a vision model in Ollama. Install one with "
        "`ollama pull moondream` (or `ollama pull llava`) and set OLLAMA_VISION_MODEL."
    )


def _is_ollama_resource_error(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(hint in lowered for hint in RESOURCE_ERROR_HINTS)


def _unique_non_empty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


def _candidate_ctx_sizes() -> list[int]:
    values = [OLLAMA_NUM_CTX]
    if OLLAMA_NUM_CTX > 1024:
        values.append(1024)
    if OLLAMA_NUM_CTX > 768:
        values.append(768)
    if OLLAMA_NUM_CTX > 512:
        values.append(512)
    return [max(512, size) for size in values]


def _candidate_batch_sizes() -> list[int]:
    values = [OLLAMA_NUM_BATCH]
    if OLLAMA_NUM_BATCH > 64:
        values.append(64)
    if OLLAMA_NUM_BATCH > 32:
        values.append(32)
    if OLLAMA_NUM_BATCH > OLLAMA_MIN_BATCH:
        values.append(OLLAMA_MIN_BATCH)
    unique: list[int] = []
    seen: set[int] = set()
    for item in values:
        fixed = max(8, int(item))
        if fixed in seen:
            continue
        seen.add(fixed)
        unique.append(fixed)
    return unique


def _stream_ollama_once(messages: list[dict], *, model_name: str, num_ctx: int, num_batch: int) -> Iterable[str]:
    endpoint = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "options": {"num_ctx": num_ctx, "num_batch": num_batch},
    }
    try:
        with httpx.stream("POST", endpoint, json=payload, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            if response.status_code >= 400:
                error_body = response.read().decode("utf-8", errors="replace")
                raise AIServiceError(f"Ollama error {response.status_code}: {error_body}")
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield delta
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError(f"Ollama streaming failed: {exc}") from exc


def _stream_ollama(messages: list[dict]) -> Iterable[str]:
    has_images = any(isinstance(message.get("images"), list) and message.get("images") for message in messages)
    primary_model = _resolve_ollama_model_for_messages(messages)
    fallback_model = OLLAMA_VISION_FALLBACK_MODEL if has_images else OLLAMA_TEXT_FALLBACK_MODEL
    model_candidates = _unique_non_empty([primary_model, fallback_model])
    ctx_candidates = _candidate_ctx_sizes()
    batch_candidates = _candidate_batch_sizes()
    failures: list[str] = []

    for model_name in model_candidates:
        for ctx_size in ctx_candidates:
            for batch_size in batch_candidates:
                try:
                    yield from _stream_ollama_once(
                        messages,
                        model_name=model_name,
                        num_ctx=ctx_size,
                        num_batch=batch_size,
                    )
                    return
                except AIServiceError as exc:
                    failure = f"{model_name} (num_ctx={ctx_size}, num_batch={batch_size}) -> {exc}"
                    failures.append(failure)
                    if not _is_ollama_resource_error(str(exc)):
                        raise

    if failures:
        compact = " | ".join(failures[-4:])
        raise AIServiceError(
            "Ollama could not load a model with available memory. "
            "Try a smaller model, lower context, lower batch size, or close other apps using RAM. "
            f"Attempts: {compact}"
        )
    raise AIServiceError("Ollama could not generate a response.")


def _stream_openai_compatible(messages: list[dict], max_tokens: int) -> Iterable[str]:
    if not OPENAI_COMPAT_API_KEY:
        raise AIServiceError("OPENAI_COMPAT_API_KEY is not configured.")
    endpoint = f"{OPENAI_COMPAT_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_COMPAT_API_KEY}",
        "Content-Type": "application/json",
    }
    normalized_messages = [{"role": msg.get("role", "user"), "content": str(msg.get("content", ""))} for msg in messages]
    has_image_inputs = any(isinstance(message.get("images"), list) and message.get("images") for message in messages)
    if has_image_inputs:
        normalized_messages.append(
            {
                "role": "system",
                "content": (
                    "Images were attached by the user, but this cloud fallback path does not include image bytes. "
                    "Do not claim to see images; ask user to switch to local vision mode."
                ),
            }
        )

    payload = {
        "model": OPENAI_COMPAT_MODEL,
        "messages": normalized_messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }
    try:
        with httpx.stream(
            "POST",
            endpoint,
            headers=headers,
            json=payload,
            timeout=OPENAI_COMPAT_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code >= 400:
                error_body = response.read().decode("utf-8", errors="replace")
                raise AIServiceError(f"OpenAI-compatible error {response.status_code}: {error_body}")
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                value = line[6:].strip()
                if value == "[DONE]":
                    break
                try:
                    chunk = json.loads(value)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    yield delta
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError(f"OpenAI-compatible streaming failed: {exc}") from exc


def _is_retryable_error(message: str) -> bool:
    lowered = message.lower()
    retry_indicators = (
        " error 429",
        " error 500",
        " error 502",
        " error 503",
        " error 504",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection refused",
        "remoteprotocolerror",
        "network",
    )
    return any(indicator in lowered for indicator in retry_indicators)


def _stream_with_retries(streamer: Callable[[], Iterable[str]]) -> Iterable[str]:
    for attempt in range(1, STREAM_RETRY_ATTEMPTS + 1):
        emitted_any = False
        try:
            for chunk in streamer():
                emitted_any = True
                yield chunk
            return
        except AIServiceError as exc:
            should_retry = (
                not emitted_any
                and attempt < STREAM_RETRY_ATTEMPTS
                and _is_retryable_error(str(exc))
            )
            if not should_retry:
                raise
            backoff = STREAM_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
            time.sleep(backoff)


def stream_reasoning(
    messages: Iterable[dict],
    *,
    max_tokens: int = 1200,
    extra_context: str | None = None,
    image_attachments: list[str] | None = None,
    allow_cloud_fallback: bool = False,
) -> Iterable[str]:
    prepared = _compose_messages_with_images(
        messages,
        extra_context=extra_context,
        image_attachments=image_attachments,
    )
    provider = LLM_PROVIDER
    if provider == "ollama":
        try:
            yield from _stream_with_retries(lambda: _stream_ollama(prepared))
            return
        except AIServiceError as ollama_error:
            if allow_cloud_fallback and OPENAI_COMPAT_API_KEY:
                try:
                    yield from _stream_with_retries(
                        lambda: _stream_openai_compatible(prepared, max_tokens=max_tokens)
                    )
                    return
                except AIServiceError as fallback_error:
                    raise AIServiceError(
                        f"{ollama_error} | OpenAI-compatible fallback failed: {fallback_error}"
                    ) from fallback_error
            raise AIServiceError(
                f"{ollama_error}. Start Ollama at {OLLAMA_BASE_URL}. "
                "Cloud fallback is disabled unless explicitly enabled by the user."
            ) from ollama_error
    if provider in {"openai", "openai_compatible"}:
        if not allow_cloud_fallback:
            raise AIServiceError(
                "Cloud inference is disabled in Local-Only mode. Switch to Cloud Mode to use external APIs."
            )
        yield from _stream_with_retries(
            lambda: _stream_openai_compatible(prepared, max_tokens=max_tokens)
        )
        return
    raise AIServiceError(f"Unsupported LLM_PROVIDER: {provider}")

