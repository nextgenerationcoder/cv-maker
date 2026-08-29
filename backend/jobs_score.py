import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import cv_store
from auth import get_current_user
from job_scoring import MAX_JOBS_PER_REQUEST, JobInput, score_jobs
from llm_provider import get_provider_for_user

logger = logging.getLogger("cv_maker.jobs_score")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class ScoreJobsRequest(BaseModel):
    cv_id: str
    jobs: List[JobInput]


@router.post("/score")
def score_jobs_endpoint(
    body: ScoreJobsRequest, current_user: dict = Depends(get_current_user)
):
    if not body.jobs:
        raise HTTPException(status_code=400, detail="No jobs provided.")
    if len(body.jobs) > MAX_JOBS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many jobs in one request — max {MAX_JOBS_PER_REQUEST}.",
        )

    cv_record = cv_store.fetch_cv(body.cv_id, current_user["id"])
    if cv_record is None:
        raise HTTPException(status_code=404, detail="CV not found.")

    try:
        provider = get_provider_for_user(current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        scores = score_jobs(provider, cv_record["profile"], body.jobs)
    except Exception:
        logger.exception("Job scoring failed for cv_id=%r", body.cv_id)
        raise HTTPException(
            status_code=502,
            detail="Job scoring failed. Try again shortly.",
        )

    return {"scores": [s.model_dump() for s in scores]}
