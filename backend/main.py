import logging
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from jobspy import scrape_jobs

import cv_store
from cv import router as cv_router

logger = logging.getLogger("cv_maker.jobs")

app = FastAPI(title="CV Maker Job Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cv_router)


@app.on_event("startup")
def _init_cv_db() -> None:
    cv_store.init_db()

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

    jobs = jobs.where(pd.notnull(jobs), None)
    return {"count": len(jobs), "jobs": jobs.to_dict(orient="records")}
