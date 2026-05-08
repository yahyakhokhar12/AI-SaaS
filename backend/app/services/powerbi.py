from __future__ import annotations

import json
import os
import time
import base64
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd
from dotenv import load_dotenv

from app.services.errors import AIServiceError
from app.services.export import build_text_artifact

load_dotenv()

PBI_BASE_URL = os.getenv("PBI_BASE_URL", "https://api.powerbi.com/v1.0/myorg")
PBI_WORKSPACE_ID = os.getenv("PBI_WORKSPACE_ID", "")
PBI_ACCESS_TOKEN = os.getenv("PBI_ACCESS_TOKEN", "")
PBI_ENABLE_UPLOAD = os.getenv("PBI_ENABLE_UPLOAD", "false").lower() == "true"
PBI_TEMPLATE_REPORT_ID = os.getenv("PBI_TEMPLATE_REPORT_ID", "")
PBI_EXPORT_FORMAT = os.getenv("PBI_EXPORT_FORMAT", "PDF")
PBI_EXPORT_TIMEOUT_SECONDS = int(os.getenv("PBI_EXPORT_TIMEOUT_SECONDS", "120"))


def _dataset_table_name(name: str) -> str:
    sanitized = "".join(character if character.isalnum() else "_" for character in name.lower())
    return sanitized[:80] or "dataset_table"


def _clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [str(column).strip().replace(" ", "_") for column in cleaned.columns]
    cleaned = cleaned.drop_duplicates()
    cleaned = cleaned.fillna("")
    return cleaned


def _find_sales_column(df: pd.DataFrame) -> str | None:
    numeric_columns = [str(column) for column in df.select_dtypes(include=["number"]).columns]
    for column in numeric_columns:
        normalized = column.lower()
        if "sales" in normalized or "revenue" in normalized or "amount" in normalized:
            return column
    return numeric_columns[0] if numeric_columns else None


def _find_date_column(df: pd.DataFrame) -> str | None:
    for column in df.columns:
        label = str(column).lower()
        if "date" in label or "month" in label or "year" in label:
            return str(column)
    for column in df.columns:
        if "datetime" in str(df[column].dtype).lower():
            return str(column)
    return None


def _dax_measures(df: pd.DataFrame) -> str:
    sales_column = _find_sales_column(df)
    date_column = _find_date_column(df)
    lines = ["-- Auto-generated DAX measures"]

    if sales_column:
        lines.extend(
            [
                f"Total Sales = SUM('Dataset'[{sales_column}])",
                f"Average Sales = AVERAGE('Dataset'[{sales_column}])",
                "Target Sales = [Average Sales] * 1.10",
            ]
        )
        if date_column:
            lines.extend(
                [
                    f"Previous Period Sales = CALCULATE([Total Sales], DATEADD('Dataset'[{date_column}], -1, MONTH))",
                    "Growth % = DIVIDE([Total Sales] - [Previous Period Sales], [Previous Period Sales])",
                ]
            )
        else:
            lines.append("Growth % = BLANK()")
        lines.append('KPI Status = IF([Total Sales] >= [Target Sales], "On Track", "Below Target")')
    else:
        lines.extend(
            [
                "Record Count = COUNTROWS('Dataset')",
                "Growth % = BLANK()",
                'KPI Status = IF([Record Count] > 0, "On Track", "No Data")',
            ]
        )

    return "\n".join(lines)


def _dashboard_schema(df: pd.DataFrame) -> dict[str, Any]:
    columns = [str(column) for column in df.columns]
    numeric = [str(column) for column in df.select_dtypes(include=["number"]).columns]
    categoricals = [column for column in columns if column not in numeric]
    date_column = _find_date_column(df)
    x_axis = date_column or (categoricals[0] if categoricals else columns[0])
    y_axis = _find_sales_column(df) or (numeric[0] if numeric else columns[0])
    return {
        "title": "Auto-Generated Power BI Dashboard",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_table": "Dataset",
        "visuals": [
            {"type": "card", "measure": "Total Sales", "title": "Total Sales"},
            {"type": "card", "measure": "Growth %", "title": "Growth %"},
            {"type": "card", "measure": "KPI Status", "title": "KPI Status"},
            {"type": "line_chart", "x": x_axis, "y": y_axis, "title": f"{y_axis} trend by {x_axis}"},
            {"type": "bar_chart", "x": x_axis, "y": y_axis, "title": f"{y_axis} by {x_axis}"},
            {"type": "table", "columns": columns[:10], "title": "Detail table"},
        ],
        "filters": columns[:8],
    }


def _powerbi_column_type(series: pd.Series) -> str:
    dtype = str(series.dtype).lower()
    if "int" in dtype:
        return "Int64"
    if "float" in dtype or "double" in dtype:
        return "Double"
    if "datetime" in dtype:
        return "DateTime"
    if "bool" in dtype:
        return "bool"
    return "string"


def _api_base_url() -> str:
    return f"{PBI_BASE_URL}/groups/{PBI_WORKSPACE_ID}" if PBI_WORKSPACE_ID else PBI_BASE_URL


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PBI_ACCESS_TOKEN}", "Content-Type": "application/json"}


def _create_push_dataset(client: httpx.Client, df: pd.DataFrame, table_name: str) -> dict[str, Any]:
    table_columns = [{"name": str(column), "dataType": _powerbi_column_type(df[column])} for column in df.columns]
    create_payload = {
        "name": f"AutoDataset_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "defaultMode": "Push",
        "tables": [{"name": table_name, "columns": table_columns}],
    }
    create_response = client.post(f"{_api_base_url()}/datasets", headers=_auth_headers(), json=create_payload)
    if create_response.status_code >= 400:
        raise AIServiceError(
            f"Dataset creation failed ({create_response.status_code}): {create_response.text}"
        )

    dataset_id = create_response.json().get("id")
    rows = df.fillna("").head(10000).to_dict(orient="records")
    rows_payload = {"rows": rows}
    rows_response = client.post(
        f"{_api_base_url()}/datasets/{dataset_id}/tables/{table_name}/rows",
        headers=_auth_headers(),
        json=rows_payload,
    )
    if rows_response.status_code >= 400:
        raise AIServiceError(f"Rows push failed ({rows_response.status_code}): {rows_response.text}")

    return {"dataset_id": dataset_id, "table_name": table_name}


def _create_report_from_template(client: httpx.Client, dataset_id: str, source_name: str) -> str | None:
    if not PBI_TEMPLATE_REPORT_ID:
        return None

    clone_payload = {
        "name": f"AutoReport_{_dataset_table_name(source_name)}_{int(time.time())}",
        "targetModelId": dataset_id,
    }
    clone_response = client.post(
        f"{_api_base_url()}/reports/{PBI_TEMPLATE_REPORT_ID}/Clone",
        headers=_auth_headers(),
        json=clone_payload,
    )
    if clone_response.status_code >= 400:
        return None
    return clone_response.json().get("id")


def _export_report_file(client: httpx.Client, report_id: str) -> dict[str, Any]:
    export_response = client.post(
        f"{_api_base_url()}/reports/{report_id}/ExportTo",
        headers=_auth_headers(),
        json={"format": PBI_EXPORT_FORMAT},
    )
    if export_response.status_code >= 400:
        return {
            "requested": False,
            "message": f"Report export request failed: {export_response.status_code}",
            "details": export_response.text,
        }

    export_id = export_response.json().get("id")
    deadline = time.time() + PBI_EXPORT_TIMEOUT_SECONDS
    while time.time() < deadline:
        status_response = client.get(
            f"{_api_base_url()}/reports/{report_id}/exports/{export_id}",
            headers=_auth_headers(),
        )
        if status_response.status_code >= 400:
            return {
                "requested": True,
                "message": f"Export status check failed: {status_response.status_code}",
                "details": status_response.text,
            }
        payload = status_response.json()
        status = str(payload.get("status", "")).lower()
        if status == "succeeded":
            resource_location = payload.get("resourceLocation")
            if not resource_location:
                return {"requested": True, "message": "Export succeeded but no resource location found."}
            file_response = client.get(resource_location, headers=_auth_headers())
            if file_response.status_code >= 400:
                return {
                    "requested": True,
                    "message": f"Export download failed: {file_response.status_code}",
                    "details": file_response.text,
                }
            return {
                "requested": True,
                "message": "Report export completed.",
                "filename": f"powerbi_report.{PBI_EXPORT_FORMAT.lower()}",
                "mime_type": "application/octet-stream",
                "content_bytes": file_response.content,
            }
        if status == "failed":
            return {"requested": True, "message": "Report export failed."}
        time.sleep(2)
    return {"requested": True, "message": "Report export timed out."}


def _push_dataset_upload(df: pd.DataFrame, table_name: str, source_name: str) -> dict[str, Any]:
    if not PBI_ENABLE_UPLOAD:
        return {"enabled": False, "message": "Power BI upload disabled by configuration."}
    if not PBI_ACCESS_TOKEN:
        return {"enabled": False, "message": "PBI_ACCESS_TOKEN is missing."}

    try:
        with httpx.Client(timeout=60) as client:
            created = _create_push_dataset(client, df, table_name)
            dataset_id = created["dataset_id"]
            report_id = _create_report_from_template(client, dataset_id, source_name)
            export_result = _export_report_file(client, report_id) if report_id else {"requested": False}
            return {
                "enabled": True,
                "uploaded": True,
                "dataset_id": dataset_id,
                "table_name": table_name,
                "report_id": report_id,
                "report_export": {key: value for key, value in export_result.items() if key != "content_bytes"},
                "report_file_bytes": export_result.get("content_bytes"),
                "report_file_name": export_result.get("filename"),
                "report_file_mime_type": export_result.get("mime_type", "application/octet-stream"),
                "message": "Push dataset created and rows uploaded.",
            }
    except AIServiceError as exc:
        return {"enabled": True, "uploaded": False, "message": str(exc)}
    except Exception as exc:
        return {"enabled": True, "uploaded": False, "message": f"Upload exception: {exc}"}


def generate_powerbi_artifacts(df: pd.DataFrame, source_name: str, user_request: str) -> dict[str, Any]:
    if df.empty:
        raise AIServiceError("Dataset is empty. Cannot generate Power BI artifacts.")

    prepared = _clean_dataset(df)
    dax = _dax_measures(prepared)
    schema = _dashboard_schema(prepared)
    dataset_csv = prepared.to_csv(index=False)
    table_name = _dataset_table_name(source_name)

    instructions = "\n".join(
        [
            "Power BI Export Workflow",
            "1) Import dataset.csv into Power BI Desktop.",
            "2) Rename the table to 'Dataset'.",
            "3) Create measures from dax.txt.",
            "4) Configure visuals using dashboard_config.json.",
            "5) Optional: enable REST upload by setting PBI_ENABLE_UPLOAD=true and auth env vars.",
            "6) Optional: set PBI_TEMPLATE_REPORT_ID to clone a template report and trigger report export.",
            f"Request context: {user_request}",
        ]
    )

    upload_result = _push_dataset_upload(prepared, table_name=table_name, source_name=source_name)
    artifacts = [
        build_text_artifact("dataset.csv", "text/csv", dataset_csv),
        build_text_artifact("dax.txt", "text/plain", dax),
        build_text_artifact("dashboard_config.json", "application/json", json.dumps(schema, indent=2)),
        build_text_artifact("instructions.txt", "text/plain", instructions),
    ]

    if upload_result.get("report_file_bytes"):
        artifacts.append(
            {
                "name": upload_result.get("report_file_name", "powerbi_report.bin"),
                "mime_type": upload_result.get("report_file_mime_type", "application/octet-stream"),
                "content_base64": base64.b64encode(upload_result["report_file_bytes"]).decode("utf-8"),
            }
        )

    return {
        "assistant_message": "Power BI artifacts generated: dataset, DAX, dashboard config, and workflow instructions.",
        "artifacts": artifacts,
        "upload_result": {key: value for key, value in upload_result.items() if key != "report_file_bytes"},
    }
