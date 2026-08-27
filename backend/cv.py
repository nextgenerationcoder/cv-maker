import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import cv_store
from cv_csv import build_template_csv, csv_text_to_profile, profile_to_csv
from cv_models import CVProfile

logger = logging.getLogger("cv_maker.cv")

router = APIRouter(prefix="/api/cv", tags=["cv"])

MAX_CSV_BYTES = 2 * 1024 * 1024  # 2MB


class SaveProfileRequest(BaseModel):
    profile: CVProfile
    filename: Optional[str] = None


@router.get("/template.csv")
def download_template():
    return PlainTextResponse(
        build_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cv_template.csv"},
    )


@router.post("/import-csv")
async def import_csv(file: UploadFile = File(...)):
    is_csv = (file.content_type in ("text/csv", "application/vnd.ms-excel")) or (
        file.filename or ""
    ).lower().endswith(".csv")
    if not is_csv:
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large — max {MAX_CSV_BYTES // (1024 * 1024)}MB.",
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Couldn't read this file as UTF-8 text.")

    try:
        profile, warnings = csv_text_to_profile(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("CSV import failed for filename=%r", file.filename)
        raise HTTPException(status_code=422, detail="Couldn't parse this CSV file.")

    cv_id = str(uuid.uuid4())
    filename = file.filename or "Imported CV"
    uploaded_at = cv_store.save_cv(cv_id, filename, profile)

    return {
        "id": cv_id,
        "filename": filename,
        "uploaded_at": uploaded_at,
        "updated_at": uploaded_at,
        "profile": profile.model_dump(),
        "warnings": warnings,
    }


@router.get("/{cv_id}/export.csv")
def export_cv_csv(cv_id: str):
    record = cv_store.fetch_cv(cv_id)
    if record is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    profile = CVProfile.model_validate(record["profile"])
    return PlainTextResponse(
        profile_to_csv(profile),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={record['filename']}.csv"},
    )


@router.put("/{cv_id}")
def update_cv(cv_id: str, body: SaveProfileRequest):
    updated_at = cv_store.update_cv(cv_id, body.profile, filename=body.filename)
    if updated_at is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    record = cv_store.fetch_cv(cv_id)
    return record


@router.get("")
def list_cvs(limit: int = Query(20, ge=1, le=100)):
    return {"cvs": cv_store.list_cvs(limit=limit)}


@router.get("/{cv_id}")
def get_cv(cv_id: str):
    record = cv_store.fetch_cv(cv_id)
    if record is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    return record
