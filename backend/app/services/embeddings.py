from __future__ import annotations

import os
from threading import Lock

from dotenv import load_dotenv

from app.services.errors import AIServiceError

load_dotenv()

EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "sentence_transformers").lower()
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_model = None
_model_lock = Lock()


def _load_sentence_transformer():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise AIServiceError(
                "Embeddings dependencies missing. Install `sentence-transformers`."
            ) from exc
        _model = SentenceTransformer(EMBEDDINGS_MODEL)
        return _model


def embed_sentences(sentences: list[str]) -> list[list[float]]:
    if EMBEDDINGS_PROVIDER == "none":
        raise AIServiceError("Embeddings provider is disabled.")
    if not sentences:
        return []

    model = _load_sentence_transformer()
    try:
        vectors = model.encode(
            sentences,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
    except Exception as exc:
        raise AIServiceError(f"Embedding generation failed: {exc}") from exc
    return [vector.tolist() for vector in vectors]
