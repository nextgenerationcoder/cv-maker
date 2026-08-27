import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import cv_store
from cv_json import build_template_json, json_text_to_profile, profile_to_json
from cv_models import CVProfile

logger = logging.getLogger("cv_maker.cv")

router = APIRouter(prefix="/api/cv", tags=["cv"])

MAX_JSON_BYTES = 2 * 1024 * 1024  # 2MB


class SaveProfileRequest(BaseModel):
    profile: CVProfile
    filename: Optional[str] = None


class AddGapsRequest(BaseModel):
    items: List[str]
    source: Optional[str] = None


@router.get("/template.json")
def download_template():
    return PlainTextResponse(
        build_template_json(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=cv_template.json"},
    )


@router.post("/import-json")
async def import_json(file: UploadFile = File(...)):
    is_json = (file.content_type == "application/json") or (
        file.filename or ""
    ).lower().endswith(".json")
    if not is_json:
        raise HTTPException(status_code=400, detail="Only JSON files are supported.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > MAX_JSON_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large — max {MAX_JSON_BYTES // (1024 * 1024)}MB.",
        )

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Couldn't read this file as UTF-8 text.")

    try:
        profile = json_text_to_profile(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("JSON import failed for filename=%r", file.filename)
        raise HTTPException(status_code=422, detail="Couldn't parse this JSON file.")

    cv_id = str(uuid.uuid4())
    filename = file.filename or "Imported CV"
    uploaded_at = cv_store.save_cv(cv_id, filename, profile)

    return {
        "id": cv_id,
        "filename": filename,
        "uploaded_at": uploaded_at,
        "updated_at": uploaded_at,
        "profile": profile.model_dump(),
    }


@router.get("/{cv_id}/export.json")
def export_cv_json(cv_id: str):
    record = cv_store.fetch_cv(cv_id)
    if record is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    profile = CVProfile.model_validate(record["profile"])
    return PlainTextResponse(
        profile_to_json(profile),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={record['filename']}.json"},
    )


@router.post("/{cv_id}/gaps")
def add_gaps(cv_id: str, body: AddGapsRequest):
    if cv_store.fetch_cv(cv_id) is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    items = [t.strip() for t in body.items if t.strip()]
    if not items:
        raise HTTPException(status_code=400, detail="No gap items provided.")
    created = cv_store.add_gaps(cv_id, items, source=body.source)
    return {"gaps": created}


@router.get("/{cv_id}/gaps")
def list_gaps(cv_id: str):
    if cv_store.fetch_cv(cv_id) is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    return {"gaps": cv_store.list_gaps(cv_id)}


@router.delete("/{cv_id}/gaps/{gap_id}")
def delete_gap(cv_id: str, gap_id: str):
    if not cv_store.delete_gap(cv_id, gap_id):
        raise HTTPException(status_code=404, detail="Gap not found.")
    return {"status": "deleted"}


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
