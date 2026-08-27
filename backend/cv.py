import base64
import logging
import uuid

import anthropic
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

import cv_store
from cv_models import CVProfile

logger = logging.getLogger("cv_maker.cv")

router = APIRouter(prefix="/api/cv", tags=["cv"])

MAX_CV_BYTES = 15 * 1024 * 1024  # 15MB

EXTRACTION_PROMPT = """\
Extract all professional information from this CV/resume into structured data.
Be thorough: include every skill, every job, every degree, every language, and
every piece of technical knowledge (tools, frameworks, programming languages,
platforms) mentioned anywhere in the document.

For preferred_roles, infer the candidate's likely target job titles/roles from
their summary or objective section, their most recent job titles, and their
overall career trajectory, even if not explicitly stated as "preferred roles".

Only include information actually present in or reasonably inferable from the
document. Use empty lists or null for anything not found — do not invent
facts."""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


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

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    try:
        response = _get_client().messages.parse(
            model="claude-opus-5",
            max_tokens=8000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ],
            output_format=CVProfile,
        )
    except anthropic.APIStatusError:
        logger.exception("CV extraction failed for filename=%r", file.filename)
        raise HTTPException(
            status_code=502,
            detail="CV extraction failed. Please try again shortly.",
        )

    profile = response.parsed_output
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
