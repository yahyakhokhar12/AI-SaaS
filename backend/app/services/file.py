from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services.errors import AIServiceError


@dataclass(slots=True)
class ParsedDataset:
    name: str
    dataframe: pd.DataFrame
    source_type: str


def _decode_base64(data_base64: str) -> bytes:
    try:
        return base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AIServiceError("Invalid attachment encoding.") from exc


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(column).strip().replace(" ", "_") for column in normalized.columns]
    normalized = normalized.drop_duplicates()
    return normalized.fillna("")


def _load_csv(raw: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw))


def _load_excel(raw: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(raw), engine="openpyxl")


def _load_pdf(raw: bytes) -> pd.DataFrame:
    try:
        import pdfplumber
    except Exception as exc:
        raise AIServiceError("PDF support missing. Install `pdfplumber`.") from exc

    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages[:20]:
            text = (page.extract_text() or "").strip()
            if text:
                text_parts.append(text)
    text = "\n".join(text_parts)
    return pd.DataFrame([{"document_text": text}])


def parse_dataset_attachments(attachments: list[dict]) -> list[ParsedDataset]:
    parsed: list[ParsedDataset] = []
    for attachment in attachments:
        if attachment.get("type") != "file_binary":
            continue
        name = str(attachment.get("name") or "uploaded_file").strip()
        mime_type = str(attachment.get("mime_type") or "").lower()
        raw = _decode_base64(str(attachment.get("data_base64") or ""))
        lower_name = name.lower()

        if mime_type.startswith("text/csv") or lower_name.endswith(".csv"):
            dataframe = _normalize_dataframe(_load_csv(raw))
            parsed.append(ParsedDataset(name=name, dataframe=dataframe, source_type="csv"))
            continue

        if (
            "spreadsheetml" in mime_type
            or "ms-excel" in mime_type
            or lower_name.endswith(".xlsx")
            or lower_name.endswith(".xls")
        ):
            dataframe = _normalize_dataframe(_load_excel(raw))
            parsed.append(ParsedDataset(name=name, dataframe=dataframe, source_type="excel"))
            continue

        if mime_type == "application/pdf" or lower_name.endswith(".pdf"):
            dataframe = _normalize_dataframe(_load_pdf(raw))
            parsed.append(ParsedDataset(name=name, dataframe=dataframe, source_type="pdf"))
            continue
    return parsed


def _column_insights(df: pd.DataFrame) -> list[str]:
    insights: list[str] = []
    numeric_columns = list(df.select_dtypes(include=["number"]).columns)
    if numeric_columns:
        for column in numeric_columns[:6]:
            series = pd.to_numeric(df[column], errors="coerce").dropna()
            if len(series) == 0:
                continue
            insights.append(
                f"{column}: mean={series.mean():.2f}, median={series.median():.2f}, min={series.min():.2f}, max={series.max():.2f}"
            )

    top_missing = df.isna().sum()
    missing_parts = [f"{col}:{int(count)}" for col, count in top_missing.items() if int(count) > 0][:6]
    if missing_parts:
        insights.append("Missing values -> " + ", ".join(missing_parts))

    return insights


def analyze_datasets(datasets: list[ParsedDataset]) -> dict[str, Any]:
    if not datasets:
        raise AIServiceError("No supported CSV/Excel/PDF file found in attachments.")

    primary = datasets[0]
    df = primary.dataframe
    summary = {
        "file_name": primary.name,
        "file_type": primary.source_type,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": [str(column) for column in df.columns[:50]],
    }
    insights = _column_insights(df)
    cleaned_csv = df.to_csv(index=False)
    preview = df.head(20).to_dict(orient="records")
    return {
        "summary": summary,
        "insights": insights,
        "cleaned_dataset_csv": cleaned_csv,
        "preview_rows": preview,
        "primary_dataset_name": primary.name,
    }

