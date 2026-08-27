import logging
from typing import List, Optional

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger("cv_maker.job_scoring")

MAX_JOBS_PER_REQUEST = 25
MAX_DESCRIPTION_CHARS = 2000


class JobInput(BaseModel):
    id: int
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    job_type: Optional[str] = None


class JobScore(BaseModel):
    id: int
    score: int = Field(ge=0, le=100)
    reasoning: str
    missing_requirements: List[str] = Field(default_factory=list)


class JobScoreBatch(BaseModel):
    scores: List[JobScore]


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _experience_lines(experiences: list) -> str:
    parts = []
    for exp in experiences or []:
        bullet = exp.get("bullet", "")
        skills = exp.get("skills") or []
        metrics = exp.get("metrics") or []
        tail = ""
        if skills:
            tail += f" [skills: {', '.join(skills)}]"
        if metrics:
            tail += f" [metrics: {', '.join(metrics)}]"
        parts.append(f"    - {bullet}{tail}")
    return "\n".join(parts)


def _build_profile_summary(profile: dict) -> str:
    lines: list[str] = []

    personal = profile.get("personal_information") or {}
    if personal.get("location"):
        lines.append(f"Location: {personal['location']}")

    if profile.get("work_experience"):
        lines.append("Work experience:")
        for w in profile["work_experience"]:
            lines.append(f"  {w.get('role')} at {w.get('company')} ({w.get('period')})")
            exp_lines = _experience_lines(w.get("experiences"))
            if exp_lines:
                lines.append(exp_lines)

    if profile.get("education"):
        lines.append("Education:")
        for e in profile["education"]:
            degree_bit = f"{e.get('degree')} " if e.get("degree") else ""
            lines.append(f"  {degree_bit}{e.get('program')} — {e.get('institution')} ({e.get('period')})")
            exp_lines = _experience_lines(e.get("experiences"))
            if exp_lines:
                lines.append(exp_lines)

    if profile.get("training_and_projects"):
        lines.append("Training & projects:")
        for t in profile["training_and_projects"]:
            lines.append(f"  {t.get('title')} ({t.get('period')})")
            exp_lines = _experience_lines(t.get("experiences"))
            if exp_lines:
                lines.append(exp_lines)

    if profile.get("languages"):
        langs = ", ".join(f"{l['language']} ({l.get('level') or 'unspecified level'})" for l in profile["languages"])
        lines.append("Languages: " + langs)

    tools = profile.get("tools") or {}
    for category, items in tools.items():
        if items:
            names = ", ".join(
                f"{i['name']}" + (f" ({i['level']})" if i.get("level") else "") for i in items
            )
            lines.append(f"Tools ({category}): {names}")

    return "\n".join(lines)


SCORE_PROMPT_TEMPLATE = """\
You are assessing job fit for a candidate against a list of job postings.
For EACH job below, decide how strong a candidate for it this person is —
whether they are realistically qualified to apply, based only on the
candidate profile below. Do not assume anything about the candidate that
isn't stated in the profile.

Score 0-100:
- 0-24: Not aligned — missing core requirements (wrong field, far too
  junior/senior, missing a required language or degree)
- 25-49: Stretch — meets some requirements but has real gaps worth knowing
- 50-74: Worth applying — meets most requirements, reasonably competitive
- 75-100: Strong match — meets or exceeds the apparent requirements

For each job, give a 1-2 sentence reasoning grounded in specifics from the
candidate profile and the job posting, and list concrete missing
requirements (empty list if there aren't any). Some job postings below may
have no description text available — in that case, judge only from the
title/company/location and say so isn't enough to be confident.

CANDIDATE PROFILE:
{profile_summary}

JOBS:
{jobs_block}
"""


def score_jobs(profile: dict, jobs: List[JobInput]) -> List[JobScore]:
    profile_summary = _build_profile_summary(profile) or "(no profile information provided)"
    jobs_block = "\n\n".join(
        f"[id={job.id}] {job.title} at {job.company or 'Unknown company'}"
        + (f" ({job.location})" if job.location else "")
        + (f" — {job.job_type}" if job.job_type else "")
        + "\n"
        + (job.description or "No description available.")[:MAX_DESCRIPTION_CHARS]
        for job in jobs
    )
    prompt = SCORE_PROMPT_TEMPLATE.format(profile_summary=profile_summary, jobs_block=jobs_block)

    response = _get_client().messages.parse(
        model="claude-opus-5",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
        output_format=JobScoreBatch,
    )
    return response.parsed_output.scores
