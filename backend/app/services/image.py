from __future__ import annotations

import base64
import io
import os
from threading import Lock

from dotenv import load_dotenv

from app.services.errors import AIServiceError

load_dotenv()

SD_MODEL_ID = os.getenv("SD_MODEL_ID", "segmind/tiny-sd")
SD_FALLBACK_MODEL_ID = os.getenv("SD_FALLBACK_MODEL_ID", "runwayml/stable-diffusion-v1-5")
SD_NUM_INFERENCE_STEPS = int(os.getenv("SD_NUM_INFERENCE_STEPS", "20"))
SD_GUIDANCE_SCALE = float(os.getenv("SD_GUIDANCE_SCALE", "7.0"))
SD_WIDTH = int(os.getenv("SD_WIDTH", "512"))
SD_HEIGHT = int(os.getenv("SD_HEIGHT", "512"))
SD_PROMPT_PREFIX = os.getenv("SD_PROMPT_PREFIX", "")
SD_PROMPT_SUFFIX = os.getenv(
    "SD_PROMPT_SUFFIX",
    "ultra realistic, high detail, natural lighting, sharp focus, true-to-life textures",
)
SD_NEGATIVE_PROMPT = os.getenv(
    "SD_NEGATIVE_PROMPT",
    "blurry, low quality, noisy, distorted, artifacts, watermark, text, cartoon, painting, cgi, 3d render, malformed, duplicate objects, extra limbs",
)
SD_REALISM_BOOST = os.getenv("SD_REALISM_BOOST", "true").strip().lower() in {"1", "true", "yes", "on"}

_pipeline = None
_pipeline_lock = Lock()
_active_model_id = None


def _candidate_model_ids() -> list[str]:
    candidates = [SD_MODEL_ID, SD_FALLBACK_MODEL_ID]
    seen = set()
    unique = []
    for model_id in candidates:
        cleaned = str(model_id or "").strip()
        if cleaned and cleaned not in seen:
            unique.append(cleaned)
            seen.add(cleaned)
    return unique


def _build_pipeline(model_id: str, *, torch_module):
    from diffusers import DPMSolverMultistepScheduler, StableDiffusionPipeline

    dtype = torch_module.float16 if torch_module.cuda.is_available() else torch_module.float32
    pipeline = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=dtype)
    pipeline.scheduler = DPMSolverMultistepScheduler.from_config(pipeline.scheduler.config)
    if hasattr(pipeline, "enable_attention_slicing"):
        pipeline.enable_attention_slicing()
    pipeline = pipeline.to("cuda" if torch_module.cuda.is_available() else "cpu")
    return pipeline


def _load_pipeline():
    global _pipeline
    global _active_model_id
    if _pipeline is not None:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            import torch
        except Exception as exc:
            raise AIServiceError(
                "Stable Diffusion dependencies are missing. Install `diffusers torch accelerate`."
            ) from exc

        failures: list[str] = []
        for model_id in _candidate_model_ids():
            try:
                pipeline = _build_pipeline(model_id, torch_module=torch)
                _pipeline = pipeline
                _active_model_id = model_id
                return _pipeline
            except Exception as exc:
                failures.append(f"{model_id}: {exc}")

        raise AIServiceError("Unable to load image model. " + " | ".join(failures))


def _rounded_dimension(value: int) -> int:
    clamped = max(256, min(int(value), 1024))
    return clamped - (clamped % 8)


def _looks_like_realistic_request(prompt: str) -> bool:
    lowered = prompt.lower()
    hints = (
        "realistic",
        "photorealistic",
        "photo",
        "cinematic",
        "portrait",
        "dslr",
        "natural light",
        "8k",
        "ultra realistic",
    )
    return any(hint in lowered for hint in hints)


def _compose_prompt(cleaned_prompt: str) -> str:
    parts = [SD_PROMPT_PREFIX.strip(), cleaned_prompt]
    if SD_REALISM_BOOST or _looks_like_realistic_request(cleaned_prompt):
        parts.append(
            "photorealistic, professional photography, physically plausible lighting, detailed skin and material texture, sharp focus, realistic proportions"
        )
    parts.append(SD_PROMPT_SUFFIX.strip())
    return " ".join(part for part in parts if part)


def _is_retryable_image_error(message: str) -> bool:
    lowered = str(message or "").lower()
    hints = (
        "out of bounds",
        "unable to allocate",
        "out of memory",
        "cuda out of memory",
        "index",
    )
    return any(hint in lowered for hint in hints)


def _generation_profiles(*, cuda_available: bool, width: int, height: int, steps: int) -> list[dict]:
    profiles = [
        {"width": width, "height": height, "steps": steps, "guidance": SD_GUIDANCE_SCALE},
    ]
    if cuda_available:
        profiles.extend(
            [
                {"width": min(width, 768), "height": min(height, 768), "steps": min(steps, 30), "guidance": min(SD_GUIDANCE_SCALE, 7.0)},
                {"width": min(width, 640), "height": min(height, 640), "steps": 20, "guidance": 6.5},
                {"width": min(width, 512), "height": min(height, 512), "steps": 16, "guidance": 6.0},
            ]
        )
    else:
        profiles.extend(
            [
                {"width": min(width, 512), "height": min(height, 512), "steps": min(steps, 20), "guidance": min(SD_GUIDANCE_SCALE, 6.5)},
                {"width": min(width, 448), "height": min(height, 448), "steps": 14, "guidance": 6.0},
            ]
        )

    unique: list[dict] = []
    seen: set[tuple] = set()
    for profile in profiles:
        key = (profile["width"], profile["height"], profile["steps"], profile["guidance"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(profile)
    return unique


def _run_generation(pipeline, *, final_prompt: str, width: int, height: int, steps: int, guidance: float):
    return pipeline(
        prompt=final_prompt,
        negative_prompt=SD_NEGATIVE_PROMPT,
        num_inference_steps=steps,
        guidance_scale=guidance,
        width=width,
        height=height,
    )


def _try_switch_pipeline_model(*, torch_module) -> bool:
    global _pipeline
    global _active_model_id
    current = str(_active_model_id or "").strip()
    candidates = [model for model in _candidate_model_ids() if model != current]
    if not candidates:
        return False

    with _pipeline_lock:
        for model_id in candidates:
            try:
                pipeline = _build_pipeline(model_id, torch_module=torch_module)
                _pipeline = pipeline
                _active_model_id = model_id
                return True
            except Exception:
                continue
    return False


def generate_image_base64(prompt: str) -> dict:
    cleaned_prompt = (prompt or "").strip()
    if not cleaned_prompt:
        raise AIServiceError("Image prompt is empty.")
    final_prompt = _compose_prompt(cleaned_prompt)

    pipeline = _load_pipeline()
    try:
        import torch
    except Exception as exc:
        raise AIServiceError("Torch runtime is unavailable.") from exc

    width = _rounded_dimension(SD_WIDTH)
    height = _rounded_dimension(SD_HEIGHT)
    steps = SD_NUM_INFERENCE_STEPS
    if not torch.cuda.is_available():
        width = min(width, 512)
        height = min(height, 512)
        steps = min(max(steps, 18), 28)
    else:
        steps = min(max(steps, 24), 50)

    errors: list[str] = []
    profiles = _generation_profiles(
        cuda_available=torch.cuda.is_available(),
        width=width,
        height=height,
        steps=steps,
    )

    for profile in profiles:
        try:
            result = _run_generation(
                pipeline,
                final_prompt=final_prompt,
                width=profile["width"],
                height=profile["height"],
                steps=profile["steps"],
                guidance=profile["guidance"],
            )
            image = result.images[0]
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return {
                "mime_type": "image/png",
                "image_base64": encoded,
                "assistant_message": f"Image generated successfully with Stable Diffusion ({_active_model_id}).",
            }
        except Exception as exc:
            message = str(exc)
            errors.append(
                f"{_active_model_id or 'unknown'}@{profile['width']}x{profile['height']}/steps={profile['steps']}: {message}"
            )
            if not _is_retryable_image_error(message):
                raise AIServiceError(f"Image generation failed: {message}") from exc

    switched = _try_switch_pipeline_model(torch_module=torch)
    if switched:
        pipeline = _load_pipeline()
        for profile in profiles:
            try:
                result = _run_generation(
                    pipeline,
                    final_prompt=final_prompt,
                    width=profile["width"],
                    height=profile["height"],
                    steps=profile["steps"],
                    guidance=profile["guidance"],
                )
                image = result.images[0]
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                return {
                    "mime_type": "image/png",
                    "image_base64": encoded,
                    "assistant_message": f"Image generated successfully with Stable Diffusion ({_active_model_id}).",
                }
            except Exception as exc:
                errors.append(
                    f"{_active_model_id or 'unknown'}@{profile['width']}x{profile['height']}/steps={profile['steps']}: {exc}"
                )

    compact = " | ".join(errors[-3:]) if errors else "unknown runtime error"
    raise AIServiceError(
        "Image generation failed after fallback attempts. "
        f"Last errors: {compact}"
    )
