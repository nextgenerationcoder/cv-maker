import logging
from typing import Optional

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from jobspy import scrape_jobs

import cv_store
import settings_store
import tailoring_store
import user_store
from auth import get_current_user
from auth import router as auth_router
from cv import router as cv_router
from jobs_score import router as jobs_score_router
from settings import router as settings_router
from tailoring import router as tailoring_router

logger = logging.getLogger("cv_maker.jobs")

app = FastAPI(title="CV Maker Job Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(cv_router)
app.include_router(jobs_score_router)
app.include_router(tailoring_router)
app.include_router(settings_router)


@app.on_event("startup")
def _init_db() -> None:
    cv_store.init_db()
    user_store.init_db()
    tailoring_store.init_db()
    settings_store.init_db()

SUPPORTED_SITES = ["indeed", "linkedin", "zip_recruiter", "glassdoor", "google"]
SUPPORTED_JOB_TYPES = [
    "fulltime",
    "parttime",
    "contract",
    "temporary",
    "internship",
    "perdiem",
    "nights",
    "other",
    "summer",
    "volunteer",
]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/jobs")
def search_jobs(
    search_term: str = Query(..., description="Job title or keywords to search for"),
    location: Optional[str] = Query(None, description="City, state, or remote"),
    site_name: list[str] = Query(
        default=["indeed"], description="Job boards to search, e.g. indeed, linkedin"
    ),
    results_wanted: int = Query(20, ge=1, le=100),
    hours_old: Optional[int] = Query(
        None, description="Only return jobs posted within this many hours"
    ),
    is_remote: Optional[bool] = Query(None),
    job_type: Optional[str] = Query(
        None, description=f"One of: {SUPPORTED_JOB_TYPES}"
    ),
    distance: Optional[int] = Query(
        None, ge=0, description="Search radius in miles from location"
    ),
    easy_apply: Optional[bool] = Query(
        None, description="Only jobs with an easy-apply option (LinkedIn/Indeed)"
    ),
    country_indeed: str = Query("USA", description="Country to search on Indeed/Glassdoor"),
    include_keywords: Optional[str] = Query(
        None,
        description="Comma-separated; keep only jobs whose title/description/company "
        "contains at least one of these (applied after scraping, not sent to the job board)",
    ),
    exclude_keywords: Optional[str] = Query(
        None,
        description="Comma-separated; drop jobs whose title/description/company "
        "contains any of these (applied after scraping, not sent to the job board)",
    ),
    current_user: dict = Depends(get_current_user),
):
    invalid_sites = [site for site in site_name if site not in SUPPORTED_SITES]
    if invalid_sites:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported site(s): {invalid_sites}. Supported: {SUPPORTED_SITES}",
        )
    if job_type is not None and job_type not in SUPPORTED_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported job_type: {job_type}. Supported: {SUPPORTED_JOB_TYPES}",
        )

    scrape_kwargs = {
        "site_name": site_name,
        "search_term": search_term,
        "location": location,
        "results_wanted": results_wanted,
        "country_indeed": country_indeed,
    }
    if hours_old is not None:
        scrape_kwargs["hours_old"] = hours_old
    if is_remote is not None:
        scrape_kwargs["is_remote"] = is_remote
    if job_type is not None:
        scrape_kwargs["job_type"] = job_type
    if distance is not None:
        scrape_kwargs["distance"] = distance
    if easy_apply is not None:
        scrape_kwargs["easy_apply"] = easy_apply

    try:
        jobs: pd.DataFrame = scrape_jobs(**scrape_kwargs)
    except Exception as exc:
        logger.exception("Job scrape failed for search_term=%r site_name=%r", search_term, site_name)
        raise HTTPException(
            status_code=502,
            detail="Job scrape failed. The job board may be temporarily unavailable or blocking requests — try again shortly.",
        ) from exc

    if jobs is None or jobs.empty:
        return {"count": 0, "jobs": []}

    include_terms = _split_keywords(include_keywords)
    exclude_terms = _split_keywords(exclude_keywords)
    if include_terms or exclude_terms:
        jobs = jobs[jobs.apply(lambda row: _keyword_filter(row, include_terms, exclude_terms), axis=1)]

    jobs = jobs.where(pd.notnull(jobs), None)
    return {"count": len(jobs), "jobs": jobs.to_dict(orient="records")}


def _split_keywords(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [term.strip().lower() for term in raw.split(",") if term.strip()]


def _keyword_filter(row: "pd.Series", include_terms: list[str], exclude_terms: list[str]) -> bool:
    haystack = " ".join(
        str(row.get(col) or "") for col in ("title", "description", "company")
    ).lower()
    if include_terms and not any(term in haystack for term in include_terms):
        return False
    if exclude_terms and any(term in haystack for term in exclude_terms):
        return False
    return True
