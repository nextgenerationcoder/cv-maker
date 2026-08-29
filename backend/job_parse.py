"""Best-effort single-job-URL parser — an alternative to search-scraping
for sites (Indeed, Glassdoor, etc.) that block search requests from
datacenter/VPS IPs but often still serve an individual job page fine.

Most job boards and ATSs (Indeed, Glassdoor, LinkedIn, Greenhouse, Lever,
Workday, Personio, ...) embed a JobPosting object in JSON-LD
(<script type="application/ld+json">) for SEO — that's a portal-agnostic
way to get structured title/company/location/description without writing
a per-site scraper. Falls back to Open Graph meta tags, then to raw page
text, if no JSON-LD is found. Any of it can come back empty; the frontend
always lets the user fill in gaps by hand.
"""
import json
import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("cv_maker.job_parse")

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_DESCRIPTION_CHARS = 8000
REQUEST_TIMEOUT = 15


def _find_job_posting_ld(soup: BeautifulSoup) -> Optional[dict]:
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                candidates.extend(g for g in graph if isinstance(g, dict))
            type_ = item.get("@type")
            types = type_ if isinstance(type_, list) else [type_]
            if "JobPosting" in types:
                return item
    return None


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return value.get("name") or value.get("value") or ""
    return str(value)


def _html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()


def _location_from_ld(job: dict) -> Optional[str]:
    loc = job.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return None
    address = loc.get("address")
    if not isinstance(address, dict):
        return None
    parts = [
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry") if isinstance(address.get("addressCountry"), str) else _text(address.get("addressCountry")),
    ]
    return ", ".join(p for p in parts if p) or None


def parse_job_url(url: str) -> dict:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to fetch job URL %r: %s", url, exc)
        raise ValueError(
            "Couldn't fetch that page — it may be blocking automated requests. "
            "Paste the job details in manually instead."
        )

    soup = BeautifulSoup(response.text, "html.parser")
    job = _find_job_posting_ld(soup)

    if job:
        description_html = job.get("description") or ""
        description = _html_to_text(description_html) if description_html else ""
        return {
            "title": _text(job.get("title")).strip() or None,
            "company": _text(job.get("hiringOrganization")).strip() or None,
            "location": _location_from_ld(job),
            "description": description[:MAX_DESCRIPTION_CHARS] or None,
            "job_url": url,
        }

    # Fallback: Open Graph tags + raw visible text.
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    title = (og_title["content"].strip() if og_title and og_title.get("content") else None) or (
        soup.title.string.strip() if soup.title and soup.title.string else None
    )
    description = None
    if og_desc and og_desc.get("content"):
        description = og_desc["content"].strip()
    else:
        body_text = soup.get_text(separator="\n")
        body_text = re.sub(r"\n{2,}", "\n", body_text).strip()
        description = body_text[:MAX_DESCRIPTION_CHARS] or None

    if not title and not description:
        raise ValueError(
            "Couldn't find any job details on that page — paste the title and "
            "description in manually instead."
        )

    return {"title": title, "company": None, "location": None, "description": description, "job_url": url}
