import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional

import cv_store
import tailoring_store
from auth import get_current_user
from tailoring_evidence import build_evidence_pool
from tailoring_models import JobAnalysis, ResumeMatchResult, TailoredCV
from tailoring_orchestrator import run_generation, run_job_analysis, run_resume_match

logger = logging.getLogger("cv_maker.tailoring_api")

router = APIRouter(prefix="/api/tailoring", tags=["tailoring"])


class CreateJobRequest(BaseModel):
    cv_id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    job_url: Optional[str] = None
    job_type: Optional[str] = None


class UpdateTailoredCvRequest(BaseModel):
    cv: TailoredCV


def _require_cv(cv_id: str, user_id: str) -> dict:
    record = cv_store.fetch_cv(cv_id, user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="CV not found.")
    return record


def _require_job(job_id: str, user_id: str) -> dict:
    job = tailoring_store.fetch_job(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.post("/jobs")
def create_job(body: CreateJobRequest, current_user: dict = Depends(get_current_user)):
    _require_cv(body.cv_id, current_user["id"])
    job = tailoring_store.create_job(current_user["id"], body.cv_id, body.model_dump())
    try:
        job_analysis, _usage = run_job_analysis(job)
    except Exception:
        logger.exception("Job analysis failed for job_id=%s", job["id"])
        raise HTTPException(status_code=502, detail="Couldn't analyze this job posting. Try again shortly.")
    tailoring_store.set_job_analysis(job["id"], current_user["id"], job_analysis.model_dump())
    return tailoring_store.fetch_job(job["id"], current_user["id"])


@router.get("/jobs")
def list_jobs(current_user: dict = Depends(get_current_user)):
    return {"jobs": tailoring_store.list_jobs(current_user["id"])}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    return _require_job(job_id, current_user["id"])


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    if not tailoring_store.delete_job(job_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"status": "deleted"}


@router.post("/jobs/{job_id}/match")
def run_match(job_id: str, current_user: dict = Depends(get_current_user)):
    job = _require_job(job_id, current_user["id"])
    if job["job_analysis"] is None:
        raise HTTPException(status_code=409, detail="Job hasn't been analyzed yet.")
    cv_record = _require_cv(job["cv_id"], current_user["id"])
    job_analysis = JobAnalysis.model_validate(job["job_analysis"])

    try:
        match, _evidence, _usage = run_resume_match(job["cv_id"], cv_record["profile"], job_analysis)
    except Exception:
        logger.exception("Resume match failed for job_id=%s", job_id)
        raise HTTPException(status_code=502, detail="Couldn't run resume matching. Try again shortly.")

    tailoring_store.upsert_match(job_id, current_user["id"], job["cv_id"], match.model_dump())
    return tailoring_store.fetch_match(job_id, current_user["id"], job["cv_id"])


@router.get("/jobs/{job_id}/match")
def get_match(job_id: str, current_user: dict = Depends(get_current_user)):
    job = _require_job(job_id, current_user["id"])
    match = tailoring_store.fetch_match(job_id, current_user["id"], job["cv_id"])
    if match is None:
        raise HTTPException(status_code=404, detail="No resume match yet — run one first.")
    return match


@router.get("/jobs/{job_id}/evidence")
def get_evidence(job_id: str, current_user: dict = Depends(get_current_user)):
    job = _require_job(job_id, current_user["id"])
    cv_record = _require_cv(job["cv_id"], current_user["id"])
    pool = build_evidence_pool(job["cv_id"], cv_record["profile"])
    return {"items": [item.model_dump() for item in pool]}


@router.post("/jobs/{job_id}/generate")
def generate_tailored_cv(job_id: str, current_user: dict = Depends(get_current_user)):
    job = _require_job(job_id, current_user["id"])
    if job["job_analysis"] is None:
        raise HTTPException(status_code=409, detail="Job hasn't been analyzed yet.")
    cv_record = _require_cv(job["cv_id"], current_user["id"])
    job_analysis = JobAnalysis.model_validate(job["job_analysis"])

    match_row = tailoring_store.fetch_match(job_id, current_user["id"], job["cv_id"])
    if match_row is None:
        try:
            match, _evidence, _usage = run_resume_match(job["cv_id"], cv_record["profile"], job_analysis)
        except Exception:
            logger.exception("Resume match failed during generate for job_id=%s", job_id)
            raise HTTPException(status_code=502, detail="Couldn't run resume matching. Try again shortly.")
        tailoring_store.upsert_match(job_id, current_user["id"], job["cv_id"], match.model_dump())
    else:
        match_row.pop("created_at", None)
        match = ResumeMatchResult.model_validate(match_row)

    try:
        result = run_generation(
            job["cv_id"], cv_record["profile"], cv_record["updated_at"], job_analysis, match
        )
    except Exception:
        logger.exception("CV generation failed for job_id=%s", job_id)
        raise HTTPException(status_code=502, detail="Couldn't generate the tailored CV. Try again shortly.")

    record = tailoring_store.create_tailored_cv(
        current_user["id"],
        job_id,
        job["cv_id"],
        result.cv.model_dump(),
        [s.model_dump() for s in result.selection],
        [p.model_dump() for p in result.provenance],
        result.evaluation.model_dump(),
        result.generation.model_dump(),
    )
    return record


@router.get("/jobs/{job_id}/tailored-cvs")
def list_tailored_cvs(job_id: str, current_user: dict = Depends(get_current_user)):
    _require_job(job_id, current_user["id"])
    return {"tailored_cvs": tailoring_store.list_tailored_cvs_for_job(job_id, current_user["id"])}


@router.get("/tailored-cvs/{tcv_id}")
def get_tailored_cv(tcv_id: str, current_user: dict = Depends(get_current_user)):
    record = tailoring_store.fetch_tailored_cv(tcv_id, current_user["id"])
    if record is None:
        raise HTTPException(status_code=404, detail="Tailored CV not found.")
    return record


@router.patch("/tailored-cvs/{tcv_id}")
def update_tailored_cv(tcv_id: str, body: UpdateTailoredCvRequest, current_user: dict = Depends(get_current_user)):
    record = tailoring_store.update_tailored_cv_content(tcv_id, current_user["id"], body.cv.model_dump())
    if record is None:
        raise HTTPException(status_code=404, detail="Tailored CV not found.")
    return record


@router.post("/tailored-cvs/{tcv_id}/regenerate")
def regenerate_tailored_cv(tcv_id: str, current_user: dict = Depends(get_current_user)):
    existing = tailoring_store.fetch_tailored_cv(tcv_id, current_user["id"])
    if existing is None:
        raise HTTPException(status_code=404, detail="Tailored CV not found.")
    return generate_tailored_cv(existing["job_id"], current_user)


@router.get("/tailored-cvs/{tcv_id}/export.json")
def export_tailored_cv(tcv_id: str, current_user: dict = Depends(get_current_user)):
    record = tailoring_store.fetch_tailored_cv(tcv_id, current_user["id"])
    if record is None:
        raise HTTPException(status_code=404, detail="Tailored CV not found.")
    import json

    return PlainTextResponse(
        json.dumps(record["cv"], indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=tailored_cv_{tcv_id[:8]}.json"},
    )
