"""Background collector for the German product-management word-frequency
corpus - loops JobSpy's LinkedIn scraper over several German cities and
search-term variants (a single call caps out well below the word target),
dedupes by job URL, and writes results as JSONL. Runs in a background
thread from jobs_corpus.py, reporting progress via corpus_store.

Only LinkedIn: Indeed/Glassdoor block search requests from this VPS's IP
(see job_parse.py's docstring).
"""
import json
import logging
import time
from pathlib import Path

import jobspy.linkedin
from jobspy import scrape_jobs

import corpus_store

log = logging.getLogger("cv_maker.corpus_collector")

# Works around a real bug in python-jobspy (present through at least
# 1.1.82, the latest release as of writing - checked against upstream
# source, not fixed by upgrading): LinkedIn's _process_job does
# `job_details.get("job_level", "").lower()`, but that default only
# applies when the key is *missing*, not when it's present and None - and
# parse_job_level(soup) returns None for any posting with no "Seniority
# level" field, which is common. That crashes the entire scrape_jobs()
# call, not just the one posting.
_original_parse_job_level = jobspy.linkedin.parse_job_level
jobspy.linkedin.parse_job_level = lambda soup: _original_parse_job_level(soup) or ""

SEARCH_TERMS = ["Produktmanager", "Product Manager", "Produktmanagement"]
LOCATIONS = [
    "Berlin, Germany", "München, Germany", "Hamburg, Germany",
    "Frankfurt, Germany", "Köln, Germany", "Stuttgart, Germany",
    "Düsseldorf, Germany", "Leipzig, Germany", "Germany",
]
RESULTS_PER_CALL = 50
SLEEP_BETWEEN_CALLS = 8  # seconds - polite pacing, not just speed for its own sake


def word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _load_existing(output_path: str) -> tuple[set[str], int, int]:
    """Seeds dedup/progress state from a previous run's output, so a
    second /start on the same account tops up toward the target instead
    of re-fetching and duplicating postings already on disk."""
    seen_urls: set[str] = set()
    total_words = 0
    path = Path(output_path)
    if not path.exists():
        return seen_urls, total_words, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        # A prior run killed mid-write (container restart, crash) can
        # leave a truncated last line - skip it rather than crash the
        # whole run on startup.
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = row.get("job_url")
        if url:
            seen_urls.add(url)
        total_words += word_count(row.get("description", ""))
    return seen_urls, total_words, len(seen_urls)


def run_collection(run_id: str, target_words: int, output_path: str) -> None:
    seen_urls, total_words, posting_count = _load_existing(output_path)

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "a", encoding="utf-8") as out:
            for term in SEARCH_TERMS:
                for location in LOCATIONS:
                    if total_words >= target_words:
                        break
                    step = f"Searching LinkedIn: {term!r} in {location!r} ({total_words}/{target_words} words)"
                    log.info(step)
                    corpus_store.update_progress(
                        run_id, collected_words=total_words, posting_count=posting_count, current_step=step,
                    )
                    try:
                        jobs = scrape_jobs(
                            site_name=["linkedin"],
                            search_term=term,
                            location=location,
                            results_wanted=RESULTS_PER_CALL,
                            linkedin_fetch_description=True,
                        )
                    except Exception:
                        log.exception("Search failed for term=%r location=%r - skipping.", term, location)
                        time.sleep(SLEEP_BETWEEN_CALLS)
                        continue

                    if jobs is not None and not jobs.empty:
                        for _, row in jobs.iterrows():
                            url = row.get("job_url")
                            description = row.get("description")
                            if not url or url in seen_urls or not description:
                                continue
                            seen_urls.add(url)
                            out.write(json.dumps({
                                "job_url": url,
                                "title": row.get("title"),
                                "location": str(row.get("location") or ""),
                                "description": description,
                            }, ensure_ascii=False) + "\n")
                            total_words += word_count(description)
                            posting_count += 1
                        out.flush()

                    time.sleep(SLEEP_BETWEEN_CALLS)
                if total_words >= target_words:
                    break

        corpus_store.update_progress(
            run_id, collected_words=total_words, posting_count=posting_count,
            current_step="done" if total_words >= target_words else "exhausted search combinations",
        )
        corpus_store.mark_done(run_id)
    except Exception as exc:
        log.exception("Corpus collection run %s failed", run_id)
        corpus_store.mark_failed(run_id, str(exc))
