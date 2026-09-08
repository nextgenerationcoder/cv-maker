"""POST /api/jobs/corpus/start kicks off a background collection run (see
corpus_collector.py) instead of blocking the request - reaching a large
word target can take many minutes (deliberately paced requests to
LinkedIn). Poll GET /api/jobs/corpus/{run_id} for progress, then
GET .../download once status is 'done'.
"""
import os
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import corpus_collector
import corpus_store
from auth import get_current_user

router = APIRouter(prefix="/api/jobs/corpus", tags=["jobs-corpus"])

CORPUS_DIR = os.environ.get("CORPUS_DIR", "./corpus_data")


class StartCorpusRequest(BaseModel):
    target_words: int = 700_000


@router.post("/start")
def start_corpus_run(body: StartCorpusRequest, current_user: dict = Depends(get_current_user)):
    if body.target_words < 1 or body.target_words > 5_000_000:
        raise HTTPException(status_code=400, detail="target_words must be between 1 and 5,000,000")

    # One file per account, appended to across runs - a second /start just
    # tops up toward a (possibly higher) target instead of re-fetching and
    # duplicating postings already collected by an earlier run.
    output_path = os.path.join(CORPUS_DIR, f"jobs_{current_user['id']}.jsonl")
    run = corpus_store.create_run(current_user["id"], body.target_words, output_path)

    thread = threading.Thread(
        target=corpus_collector.run_collection,
        args=(run["id"], body.target_words, output_path),
        daemon=True,
    )
    thread.start()

    return run


@router.get("")
def list_corpus_runs(current_user: dict = Depends(get_current_user)):
    return {"runs": corpus_store.list_runs(current_user["id"])}


@router.get("/{run_id}")
def get_corpus_run(run_id: str, current_user: dict = Depends(get_current_user)):
    run = corpus_store.get_run(run_id)
    if run is None or run["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("/{run_id}/download")
def download_corpus_run(run_id: str, current_user: dict = Depends(get_current_user)):
    run = corpus_store.get_run(run_id)
    if run is None or run["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Run not found.")
    if not run["output_path"] or not os.path.exists(run["output_path"]):
        raise HTTPException(status_code=404, detail="No output yet for this run.")
    return FileResponse(run["output_path"], media_type="application/x-ndjson", filename="jobs.jsonl")
