from __future__ import annotations

import base64
from typing import Any


def build_artifact(name: str, mime_type: str, content: bytes) -> dict[str, Any]:
    return {
        "name": name,
        "mime_type": mime_type,
        "content_base64": base64.b64encode(content).decode("utf-8"),
    }


def build_text_artifact(name: str, mime_type: str, text: str) -> dict[str, Any]:
    return build_artifact(name=name, mime_type=mime_type, content=text.encode("utf-8"))

