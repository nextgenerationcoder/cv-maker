import logging
import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

import cv_store
from cv_parser import extract_cv_profile

logger = logging.getLogger("cv_maker.cv")

router = APIRouter(prefix="/api/cv", tags=["cv"])

MAX_CV_BYTES = 15 * 1024 * 1024  # 15MB


@router.post("/upload")
async def upload_cv(file: UploadFile = File(...)):
    is_pdf = (file.content_type == "application/pdf") or (
        file.filename or ""
    ).lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(pdf_bytes) > MAX_CV_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large — max {MAX_CV_BYTES // (1024 * 1024)}MB.",
        )

    try:
        profile = extract_cv_profile(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        logger.exception("CV extraction failed for filename=%r", file.filename)
        raise HTTPException(
            status_code=500,
            detail="Couldn't parse this CV. It may use a layout this parser doesn't handle.",
        )

    cv_id = str(uuid.uuid4())
    uploaded_at = cv_store.save_cv(cv_id, file.filename or "cv.pdf", profile)

    return {
        "id": cv_id,
        "filename": file.filename,
        "uploaded_at": uploaded_at,
        "profile": profile.model_dump(),
    }


@router.get("")
def list_cvs(limit: int = Query(20, ge=1, le=100)):
    return {"cvs": cv_store.list_cvs(limit=limit)}


@router.get("/{cv_id}")
def get_cv(cv_id: str):
    record = cv_store.fetch_cv(cv_id)
    if record is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    return record
