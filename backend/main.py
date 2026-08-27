from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from jobspy import scrape_jobs

app = FastAPI(title="CV Maker Job Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_SITES = ["indeed", "linkedin", "zip_recruiter", "glassdoor", "google"]


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
    country_indeed: str = Query("USA", description="Country to search on Indeed/Glassdoor"),
):
    invalid_sites = [site for site in site_name if site not in SUPPORTED_SITES]
    if invalid_sites:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported site(s): {invalid_sites}. Supported: {SUPPORTED_SITES}",
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

    try:
        jobs: pd.DataFrame = scrape_jobs(**scrape_kwargs)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Job scrape failed: {exc}") from exc

    if jobs is None or jobs.empty:
        return {"count": 0, "jobs": []}

    jobs = jobs.where(pd.notnull(jobs), None)
    return {"count": len(jobs), "jobs": jobs.to_dict(orient="records")}
