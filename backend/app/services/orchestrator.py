from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Generator

from app.agents.router import RoutingDecision, TaskType, decide_task
from app.services.errors import AIServiceError
from app.services.export import build_text_artifact
from app.services.file import analyze_datasets, parse_dataset_attachments
from app.services.image import generate_image_base64
from app.services.llm import stream_reasoning
from app.services.powerbi import generate_powerbi_artifacts


@dataclass(slots=True)
class OrchestratorResult:
    decision: RoutingDecision
    assistant_message: str
    artifacts: list[dict[str, Any]]
    image_data_url: str | None = None
    upload_result: dict[str, Any] | None = None


def _latest_user_prompt(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", "")).strip()
    return ""


def _attachment_context_text(attachments: list[dict]) -> str:
    if not attachments:
        return ""

    manifest_lines: list[str] = [
        "User has already attached file/media inputs in this request.",
        "Do not ask the user to provide attachment type/name unless attachment content is actually missing.",
        "Attachment manifest:",
    ]
    text_blocks: list[str] = []

    for index, attachment in enumerate(attachments, start=1):
        attachment_type = str(attachment.get("type") or "unknown")
        name = str(attachment.get("name") or f"attachment_{index}")
        mime_type = str(attachment.get("mime_type") or "unknown")
        size_hint = attachment.get("size")
        size_text = f", size={size_hint}" if size_hint is not None else ""
        manifest_lines.append(f"- {index}. name={name}, type={attachment_type}, mime={mime_type}{size_text}")

        if attachment_type != "file_text":
            continue
        text = str(attachment.get("text") or "").strip()
        if text:
            text_blocks.append(f"[{name}]\n{text[:30000]}")

    combined = "\n".join(manifest_lines)
    if text_blocks:
        combined = f"{combined}\n\nExtracted text context:\n\n" + "\n\n".join(text_blocks)
    return combined


def _image_attachments_base64(attachments: list[dict]) -> list[str]:
    images: list[str] = []
    for attachment in attachments:
        if attachment.get("type") != "image":
            continue
        encoded = str(attachment.get("data_base64") or "").strip()
        if encoded:
            images.append(encoded)
    return images


def _file_analysis_payload(datasets: list) -> tuple[str, list[dict[str, Any]]]:
    analysis = analyze_datasets(datasets)
    summary = analysis["summary"]
    insights = analysis["insights"]
    assistant_message = (
        f"Analyzed `{summary['file_name']}` ({summary['file_type']}) with "
        f"{summary['rows']} rows and {summary['columns']} columns.\n"
        + ("\n".join(f"- {item}" for item in insights) if insights else "No major anomalies detected.")
    )
    artifacts = [
        build_text_artifact("summary.json", "application/json", json.dumps(analysis["summary"], indent=2)),
        build_text_artifact("insights.txt", "text/plain", "\n".join(insights) if insights else "No major anomalies detected."),
        build_text_artifact("cleaned_dataset.csv", "text/csv", analysis["cleaned_dataset_csv"]),
    ]
    return assistant_message, artifacts


def run_orchestrator(
    *,
    messages: list[dict],
    attachments: list[dict],
    max_tokens: int,
    allow_cloud_fallback: bool,
) -> OrchestratorResult:
    prompt = _latest_user_prompt(messages)
    decision = decide_task(prompt, attachments)

    if decision.task == TaskType.IMAGE:
        result = generate_image_base64(prompt)
        return OrchestratorResult(
            decision=decision,
            assistant_message=result["assistant_message"],
            artifacts=[],
            image_data_url=f"data:{result['mime_type']};base64,{result['image_base64']}",
        )

    if decision.task == TaskType.FILE_ANALYSIS:
        datasets = parse_dataset_attachments(attachments)
        assistant_message, artifacts = _file_analysis_payload(datasets)
        return OrchestratorResult(
            decision=decision,
            assistant_message=assistant_message,
            artifacts=artifacts,
        )

    if decision.task == TaskType.POWERBI:
        datasets = parse_dataset_attachments(attachments)
        if not datasets:
            raise AIServiceError("Attach a CSV/Excel/PDF dataset first to generate dashboard artifacts.")
        package = generate_powerbi_artifacts(
            datasets[0].dataframe,
            source_name=datasets[0].name,
            user_request=prompt,
        )
        return OrchestratorResult(
            decision=decision,
            assistant_message=package["assistant_message"],
            artifacts=package["artifacts"],
            upload_result=package.get("upload_result"),
        )

    chunks: list[str] = []
    extra_context = _attachment_context_text(attachments)
    image_attachments = _image_attachments_base64(attachments)
    for chunk in stream_reasoning(
        messages,
        max_tokens=max_tokens,
        extra_context=extra_context,
        image_attachments=image_attachments,
        allow_cloud_fallback=allow_cloud_fallback,
    ):
        chunks.append(chunk)
    response_text = "".join(chunks).strip() or "I could not generate a response."
    return OrchestratorResult(
        decision=decision,
        assistant_message=response_text,
        artifacts=[],
    )


def stream_orchestrator(
    *,
    messages: list[dict],
    attachments: list[dict],
    max_tokens: int,
    allow_cloud_fallback: bool,
) -> Generator[dict[str, Any], None, None]:
    prompt = _latest_user_prompt(messages)
    decision = decide_task(prompt, attachments)
    yield {"type": "route", "task": decision.task.value, "reason": decision.reason, "confidence": decision.confidence}

    if decision.task == TaskType.IMAGE:
        result = generate_image_base64(prompt)
        yield {"type": "image", "mime_type": result["mime_type"], "image_base64": result["image_base64"]}
        yield {"type": "delta", "content": result["assistant_message"]}
        return

    if decision.task == TaskType.FILE_ANALYSIS:
        datasets = parse_dataset_attachments(attachments)
        analysis = analyze_datasets(datasets)
        summary = analysis["summary"]
        lines = [
            f"Analyzed `{summary['file_name']}` ({summary['file_type']}).",
            f"Rows: {summary['rows']} | Columns: {summary['columns']}",
        ]
        if analysis["insights"]:
            lines.extend(f"- {item}" for item in analysis["insights"])
        for line in lines:
            yield {"type": "delta", "content": line + "\n"}
        yield {"type": "artifact", "artifact": build_text_artifact("summary.json", "application/json", json.dumps(summary, indent=2))}
        yield {"type": "artifact", "artifact": build_text_artifact("insights.txt", "text/plain", "\n".join(analysis["insights"]) if analysis["insights"] else "No major anomalies detected.")}
        yield {"type": "artifact", "artifact": build_text_artifact("cleaned_dataset.csv", "text/csv", analysis["cleaned_dataset_csv"])}
        return

    if decision.task == TaskType.POWERBI:
        datasets = parse_dataset_attachments(attachments)
        if not datasets:
            raise AIServiceError("Attach CSV/Excel/PDF first for Power BI generation.")
        package = generate_powerbi_artifacts(
            datasets[0].dataframe,
            source_name=datasets[0].name,
            user_request=prompt,
        )
        yield {"type": "delta", "content": package["assistant_message"] + "\n"}
        for artifact in package["artifacts"]:
            yield {"type": "artifact", "artifact": artifact}
        yield {"type": "meta", "upload_result": package.get("upload_result", {})}
        return

    extra_context = _attachment_context_text(attachments)
    image_attachments = _image_attachments_base64(attachments)
    for chunk in stream_reasoning(
        messages,
        max_tokens=max_tokens,
        extra_context=extra_context,
        image_attachments=image_attachments,
        allow_cloud_fallback=allow_cloud_fallback,
    ):
        yield {"type": "delta", "content": chunk}
