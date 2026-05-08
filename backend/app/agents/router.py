from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import sqrt

from app.services.embeddings import embed_sentences
from app.services.errors import AIServiceError


class TaskType(str, Enum):
    LLM = "llm_reasoning"
    IMAGE = "image_generation"
    FILE_ANALYSIS = "file_analysis"
    POWERBI = "powerbi_generation"


@dataclass(slots=True)
class RoutingDecision:
    task: TaskType
    confidence: float
    reason: str


IMAGE_HINTS = {
    "image",
    "photo",
    "picture",
    "draw",
    "illustration",
    "poster",
    "render",
    "generate image",
}

IMAGE_GENERATION_HINTS = {
    "generate",
    "draw",
    "create",
    "make",
    "render",
    "illustration",
    "poster",
}

POWERBI_HINTS = {
    "power bi",
    "dashboard",
    "dax",
    "kpi",
    "visualize",
    "report",
    "dataset",
}

FILE_HINTS = {
    "analyze file",
    "analyze this",
    "summarize file",
    "csv",
    "excel",
    "pdf",
    "rows",
    "columns",
    "sheet",
}

INTENT_EXAMPLES: dict[TaskType, list[str]] = {
    TaskType.IMAGE: [
        "generate an image of a futuristic city skyline",
        "draw a concept art illustration",
        "create a photo-realistic picture",
    ],
    TaskType.POWERBI: [
        "create a power bi dashboard with kpis",
        "build dax measures and report layout",
        "prepare dataset and dashboard config for power bi",
    ],
    TaskType.FILE_ANALYSIS: [
        "analyze this csv file and summarize trends",
        "read this excel sheet and give insights",
        "extract summary from this pdf document",
    ],
    TaskType.LLM: [
        "explain how transformers work",
        "help me reason about this architecture",
        "answer this technical question",
    ],
}


def _has_any_hint(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left)) or 1.0
    right_norm = sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


def _embedding_decision(normalized: str) -> RoutingDecision | None:
    if not normalized:
        return None
    prompts: list[str] = [normalized]
    all_examples: list[str] = []
    mapping: list[TaskType] = []
    for task, examples in INTENT_EXAMPLES.items():
        all_examples.extend(examples)
        mapping.extend([task] * len(examples))
    prompts.extend(all_examples)

    try:
        vectors = embed_sentences(prompts)
    except AIServiceError:
        return None

    query_vector = vectors[0]
    scores: dict[TaskType, float] = {}
    for vector, task in zip(vectors[1:], mapping):
        similarity = _cosine_similarity(query_vector, vector)
        best = scores.get(task, -1.0)
        if similarity > best:
            scores[task] = similarity

    if not scores:
        return None

    best_task = max(scores, key=scores.get)
    confidence = max(0.4, min(0.97, float(scores[best_task])))
    return RoutingDecision(
        task=best_task,
        confidence=confidence,
        reason="Embedding-based intent classification.",
    )


def decide_task(user_text: str, attachments: list[dict] | None) -> RoutingDecision:
    normalized = (user_text or "").strip().lower()
    attached_items = attachments or []
    attachment_count = len(attached_items)
    has_image_attachment = any(str(item.get("type")) == "image" for item in attached_items)
    has_binary_attachment = any(str(item.get("type")) == "file_binary" for item in attached_items)

    if has_image_attachment and not _has_any_hint(normalized, IMAGE_GENERATION_HINTS):
        return RoutingDecision(
            task=TaskType.LLM,
            confidence=0.84,
            reason="Image attachment present; routing to LLM/vision instead of image generation.",
        )

    if _has_any_hint(normalized, IMAGE_HINTS) and "dashboard" not in normalized:
        return RoutingDecision(task=TaskType.IMAGE, confidence=0.91, reason="Prompt asks for image generation.")

    if _has_any_hint(normalized, POWERBI_HINTS):
        return RoutingDecision(task=TaskType.POWERBI, confidence=0.93, reason="Prompt asks for BI/dashboard output.")

    if attachment_count > 0 and _has_any_hint(normalized, FILE_HINTS):
        return RoutingDecision(task=TaskType.FILE_ANALYSIS, confidence=0.88, reason="Prompt asks for file analysis.")

    if attachment_count > 0 and not normalized:
        if has_image_attachment and not has_binary_attachment:
            return RoutingDecision(
                task=TaskType.LLM,
                confidence=0.82,
                reason="Image attachment provided without text; routing to LLM/vision flow.",
            )
        return RoutingDecision(task=TaskType.FILE_ANALYSIS, confidence=0.74, reason="Files provided without clear intent.")

    semantic = _embedding_decision(normalized)
    if semantic is not None:
        if semantic.confidence < 0.78:
            return RoutingDecision(task=TaskType.LLM, confidence=0.66, reason="Low semantic confidence; using LLM default.")
        if semantic.task == TaskType.FILE_ANALYSIS and attachment_count == 0:
            return RoutingDecision(task=TaskType.LLM, confidence=0.66, reason="No attachments for file analysis; using LLM default.")
        if semantic.task == TaskType.POWERBI and attachment_count == 0 and not _has_any_hint(normalized, POWERBI_HINTS):
            return RoutingDecision(task=TaskType.LLM, confidence=0.66, reason="No dashboard context detected; using LLM default.")
        return semantic

    return RoutingDecision(task=TaskType.LLM, confidence=0.65, reason="Defaulting to general reasoning.")
