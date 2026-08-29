"""CVGenerationOrchestrator: wires the LLM steps together, enforces the
grounding safeguards, and is the only place that assembles the final
public CV. Structural facts (company/role/period/location/degree/
institution/name/contact info) are copied verbatim from the resume DB
here — the LLM is never asked to reproduce them, so they cannot drift.
"""
import logging
import os
import re
import time
from typing import Optional

from llm_provider import LLMProvider
from tailoring_evidence import EvidenceItem, build_evidence_pool
from tailoring_llm_steps import (
    analyze_job,
    evaluate_cv,
    generate_draft,
    polish_draft,
    revise_draft,
    select_evidence_and_match,
)
from tailoring_models import (
    CVDraftLLMOutput,
    CVEducationEntry,
    CVJobEntry,
    CVSkills,
    EvaluationResult,
    GenerationMeta,
    InternalGenerationResult,
    JobAnalysis,
    ProvenanceEntry,
    ResumeMatchResult,
    TailoredCV,
)

logger = logging.getLogger("cv_maker.tailoring")

PASS_SCORE = int(os.environ.get("TAILOR_PASS_SCORE", "75"))
MAX_REVISION_ATTEMPTS = int(os.environ.get("TAILOR_MAX_REVISIONS", "2"))

_NUMBER_RE = re.compile(r"\d[\d.,]*%?")


def run_job_analysis(provider: LLMProvider, job: dict) -> tuple[JobAnalysis, dict]:
    ja, usage = analyze_job(provider, job)
    return ja, {"inputTokens": usage.input_tokens, "cachedInputTokens": usage.cached_input_tokens, "outputTokens": usage.output_tokens}


def run_resume_match(
    provider: LLMProvider, cv_id: str, profile: dict, job_analysis: JobAnalysis
) -> tuple[ResumeMatchResult, list[EvidenceItem], dict]:
    evidence_pool = build_evidence_pool(cv_id, profile)
    if not evidence_pool:
        empty = ResumeMatchResult(
            matchScore=0,
            strongMatches=[],
            partialMatches=[],
            missingRequirements=list(job_analysis.requiredSkills),
            atsKeywordsCovered=[],
            selection=[],
        )
        return empty, evidence_pool, {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0}
    match, usage = select_evidence_and_match(provider, evidence_pool, job_analysis)
    return match, evidence_pool, {
        "inputTokens": usage.input_tokens,
        "cachedInputTokens": usage.cached_input_tokens,
        "outputTokens": usage.output_tokens,
    }


def _group_key(evidence_type: str, entry_index: int) -> str:
    return f"{evidence_type}:{entry_index}"


def _evidence_lookup(evidence: list[EvidenceItem]) -> dict[str, EvidenceItem]:
    return {e.id: e for e in evidence}


def _summarize_draft_for_eval(draft: CVDraftLLMOutput, profile: dict) -> str:
    lines = [f"Profile summary: {draft.profileSummary}"]
    for group in draft.jobGroups:
        _type, idx = group.groupKey.split(":")
        entries = profile.get("work_experience") if _type == "work" else profile.get("training_and_projects")
        entry = (entries or [{}])[int(idx)] if entries and int(idx) < len(entries) else {}
        header = entry.get("company") or entry.get("title") or group.groupKey
        role = entry.get("role") or ""
        lines.append(f"\n{role} at {header}:" if role else f"\n{header}:")
        for b in group.bullets:
            lines.append(f"  - {b.text}")
    for group in draft.educationGroups:
        _type, idx = group.groupKey.split(":")
        entries = profile.get("education") or []
        entry = entries[int(idx)] if int(idx) < len(entries) else {}
        header = entry.get("institution") or group.groupKey
        lines.append(f"\nEducation — {header}:")
        for b in group.bullets:
            lines.append(f"  - {b.text}")
    for g in draft.skillGroups:
        if g.items:
            lines.append(f"\n{g.category}: {', '.join(g.items)}")
    return "\n".join(lines)


def _grounded_text_pool(sources: list[EvidenceItem]) -> str:
    return " ".join(f"{s.bullet} {' '.join(s.metrics)}" for s in sources).lower()


def _bullet_is_grounded(text: str, source_ids: list[str], evidence_by_id: dict[str, EvidenceItem]) -> bool:
    if not source_ids:
        return False
    sources = [evidence_by_id[sid] for sid in source_ids if sid in evidence_by_id]
    if len(sources) != len(source_ids):
        return False  # cited an id outside the pool it was given — reject
    pool_text = _grounded_text_pool(sources)
    for match in _NUMBER_RE.findall(text):
        if match not in pool_text:
            return False  # a number appears that isn't backed by any cited source
    return True


def _build_cv(
    draft: CVDraftLLMOutput,
    included_evidence: list[EvidenceItem],
    profile: dict,
    job_analysis: JobAnalysis,
) -> tuple[TailoredCV, list[ProvenanceEntry], int]:
    evidence_by_id = _evidence_lookup(included_evidence)
    provenance: list[ProvenanceEntry] = []
    dropped = 0

    jobs: list[CVJobEntry] = []
    job_group_idx = 0
    for group in draft.jobGroups:
        gtype, idx_str = group.groupKey.split(":")
        idx = int(idx_str)
        source_list = profile.get("work_experience") if gtype == "work" else profile.get("training_and_projects")
        if not source_list or idx >= len(source_list):
            continue
        entry = source_list[idx]

        kept_bullets: list[str] = []
        for bullet in group.bullets:
            if _bullet_is_grounded(bullet.text, bullet.sourceIds, evidence_by_id):
                kept_bullets.append(bullet.text)
                provenance.append(
                    ProvenanceEntry(path=f"jobs[{job_group_idx}].bullets[{len(kept_bullets) - 1}]", sourceIds=bullet.sourceIds)
                )
            else:
                dropped += 1
                logger.warning("Dropped ungrounded bullet (group=%s): %r", group.groupKey, bullet.text[:120])

        if not kept_bullets:
            continue  # nothing survived grounding for this position — omit it entirely

        if gtype == "work":
            jobs.append(
                CVJobEntry(
                    date=entry.get("period") or "",
                    title=entry.get("role") or "",
                    type="work",
                    company=entry.get("company") or "",
                    location=entry.get("location"),
                    bullets=kept_bullets,
                )
            )
        else:
            jobs.append(
                CVJobEntry(
                    date=entry.get("period") or "",
                    title=entry.get("title") or "",
                    type="training",
                    company="",
                    location=None,
                    bullets=kept_bullets,
                )
            )
        job_group_idx += 1

    education: list[CVEducationEntry] = []
    edu_group_idx = 0
    for group in draft.educationGroups:
        _gtype, idx_str = group.groupKey.split(":")
        idx = int(idx_str)
        source_list = profile.get("education") or []
        if idx >= len(source_list):
            continue
        entry = source_list[idx]

        kept_bullets = []
        for bullet in group.bullets:
            if _bullet_is_grounded(bullet.text, bullet.sourceIds, evidence_by_id):
                kept_bullets.append(bullet.text)
                provenance.append(
                    ProvenanceEntry(path=f"education[{edu_group_idx}].bullets[{len(kept_bullets) - 1}]", sourceIds=bullet.sourceIds)
                )
            else:
                dropped += 1
                logger.warning("Dropped ungrounded education bullet (group=%s): %r", group.groupKey, bullet.text[:120])

        education.append(
            CVEducationEntry(
                date=entry.get("period") or "",
                degree=entry.get("degree") or entry.get("program") or "",
                institution=entry.get("institution") or "",
                location=entry.get("location"),
                bullets=kept_bullets,
            )
        )
        edu_group_idx += 1

    # Profile summary: must cite real evidence ids, or it's dropped rather than trusted blind.
    summary = draft.profileSummary
    if not draft.profileSummarySourceIds or not all(sid in evidence_by_id for sid in draft.profileSummarySourceIds):
        logger.warning("Dropping ungrounded profile summary (sourceIds=%r)", draft.profileSummarySourceIds)
        summary = ""
    else:
        provenance.append(ProvenanceEntry(path="profileSummary", sourceIds=draft.profileSummarySourceIds))

    # Skills: every item must appear (case-insensitive) in some included evidence item's skills list.
    whitelist = {s.lower() for item in included_evidence for s in item.skills}
    skills = CVSkills()
    for group in draft.skillGroups:
        kept = [item for item in group.items if item.lower() in whitelist]
        removed = len(group.items) - len(kept)
        if removed:
            logger.warning("Dropped %d ungrounded skill(s) from group %s", removed, group.category)
        setattr(skills, group.category, ", ".join(kept))

    personal = profile.get("personal_information") or {}
    cv = TailoredCV(
        lang=job_analysis.cvLanguage,
        name=personal.get("name") or "",
        jobTitle=job_analysis.jobTitle,
        location=personal.get("location") or "",
        phone=personal.get("phone") or "",
        email=personal.get("email") or "",
        photo="",
        profileSummary=summary,
        jobs=jobs,
        education=education,
        skills=skills,
    )
    return cv, provenance, dropped


def _apply_polish(draft: CVDraftLLMOutput, polish) -> CVDraftLLMOutput:
    new_job_groups = []
    for i, group in enumerate(draft.jobGroups):
        polished_texts = polish.jobBulletTexts[i] if i < len(polish.jobBulletTexts) else None
        if polished_texts and len(polished_texts) == len(group.bullets):
            bullets = [b.model_copy(update={"text": t}) for b, t in zip(group.bullets, polished_texts)]
        else:
            logger.warning("Polish output shape mismatch for job group %s — keeping unpolished text", group.groupKey)
            bullets = group.bullets
        new_job_groups.append(group.model_copy(update={"bullets": bullets}))

    new_edu_groups = []
    for i, group in enumerate(draft.educationGroups):
        polished_texts = polish.educationBulletTexts[i] if i < len(polish.educationBulletTexts) else None
        if polished_texts and len(polished_texts) == len(group.bullets):
            bullets = [b.model_copy(update={"text": t}) for b, t in zip(group.bullets, polished_texts)]
        else:
            logger.warning("Polish output shape mismatch for education group %s — keeping unpolished text", group.groupKey)
            bullets = group.bullets
        new_edu_groups.append(group.model_copy(update={"bullets": bullets}))

    summary = polish.profileSummary.strip() or draft.profileSummary
    return draft.model_copy(update={"jobGroups": new_job_groups, "educationGroups": new_edu_groups, "profileSummary": summary})


def run_generation(
    provider: LLMProvider,
    cv_id: str,
    profile: dict,
    cv_updated_at: str,
    job_analysis: JobAnalysis,
    match: ResumeMatchResult,
) -> InternalGenerationResult:
    start = time.monotonic()
    evidence_pool = build_evidence_pool(cv_id, profile)
    evidence_by_id = _evidence_lookup(evidence_pool)
    included_ids = {s.sourceId for s in match.selection if s.decision == "include"}
    included_evidence = [e for e in evidence_pool if e.id in included_ids]

    total = {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0}

    def _accumulate(usage):
        total["inputTokens"] += usage.input_tokens
        total["cachedInputTokens"] += usage.cached_input_tokens
        total["outputTokens"] += usage.output_tokens

    draft, usage = generate_draft(provider, included_evidence, job_analysis)
    _accumulate(usage)

    eval_result, usage = evaluate_cv(provider, _summarize_draft_for_eval(draft, profile), job_analysis)
    eval_result = eval_result.model_copy(update={"passed": eval_result.score >= PASS_SCORE})
    _accumulate(usage)

    revision_count = 0
    while not eval_result.passed and revision_count < MAX_REVISION_ATTEMPTS:
        feedback_text = "\n".join(
            f"- [{f.type}] {f.requirement or ''}: {f.message}" for f in eval_result.feedback
        ) or "No specific feedback items were given."
        draft, usage = revise_draft(provider, included_evidence, job_analysis, draft, feedback_text)
        _accumulate(usage)
        revision_count += 1
        eval_result, usage = evaluate_cv(provider, _summarize_draft_for_eval(draft, profile), job_analysis)
        eval_result = eval_result.model_copy(update={"passed": eval_result.score >= PASS_SCORE})
        _accumulate(usage)

    try:
        polish_out, usage = polish_draft(provider, draft)
        _accumulate(usage)
        final_draft = _apply_polish(draft, polish_out)
    except Exception:
        logger.exception("Polish step failed — using pre-polish draft")
        final_draft = draft

    cv, provenance, dropped = _build_cv(final_draft, included_evidence, profile, job_analysis)

    latency_ms = int((time.monotonic() - start) * 1000)
    generation = GenerationMeta(
        resumeVersion=cv_updated_at,
        revisionCount=revision_count,
        model=provider.model_name,
        provider=provider.provider_name,
        inputTokens=total["inputTokens"],
        cachedInputTokens=total["cachedInputTokens"],
        outputTokens=total["outputTokens"],
        latencyMs=latency_ms,
        droppedBullets=dropped,
    )
    logger.info(
        "Tailoring generation done cv_id=%s revisions=%d score=%d dropped=%d latency_ms=%d",
        cv_id, revision_count, eval_result.score, dropped, latency_ms,
    )
    return InternalGenerationResult(cv=cv, selection=match.selection, provenance=provenance, evaluation=eval_result, generation=generation)
