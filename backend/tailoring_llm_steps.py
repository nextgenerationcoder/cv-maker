"""One function per pipeline stage. Each is a single, narrowly-scoped LLM
call — evidence selection, draft generation, evaluation, revision, and
polish are never collapsed into one call. Every call orders content
stable-first (rules, then the candidate evidence pool) so the evidence
block — the same across every stage of one generation run, and across
regenerations of the same CV — can be served from Anthropic's prompt
cache; job-specific/dynamic content always comes last, uncached.
"""
import logging
from typing import Optional

from llm_provider import LLMProvider, LLMUsage
from tailoring_evidence import EvidenceItem, render_evidence_block
from tailoring_models import (
    CVDraftLLMOutput,
    EvaluationResult,
    JobAnalysis,
    PolishLLMOutput,
    ResumeMatchResult,
)

logger = logging.getLogger("cv_maker.tailoring")

MAX_DESCRIPTION_CHARS = 6000


def _cached(text: str) -> dict:
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}


def _plain(text: str) -> dict:
    return {"type": "text", "text": text}


def _job_block(job: dict) -> str:
    return (
        f"Title: {job.get('title')}\n"
        f"Company: {job.get('company') or 'Unknown'}\n"
        f"Location: {job.get('location') or 'Unspecified'}\n"
        f"Job type: {job.get('job_type') or 'Unspecified'}\n\n"
        f"Description:\n{(job.get('description') or 'No description available.')[:MAX_DESCRIPTION_CHARS]}"
    )


def _job_analysis_block(ja: JobAnalysis) -> str:
    return (
        f"Job title: {ja.jobTitle}\n"
        f"Company: {ja.companyName or 'Unknown'}\n"
        f"Location: {ja.jobLocation or 'Unspecified'}\n"
        f"Company research: {ja.companyResearch or '(none)'}\n"
        f"Required skills: {', '.join(ja.requiredSkills) or '(none stated)'}\n"
        f"Nice-to-have skills: {', '.join(ja.niceToHaveSkills) or '(none stated)'}\n"
        f"Key responsibilities: {'; '.join(ja.keyResponsibilities) or '(none stated)'}\n"
        f"ATS keywords: {', '.join(ja.atsKeywords) or '(none stated)'}\n"
        f"Ideal candidate profile: {ja.idealCandidateProfile or '(not stated)'}\n"
        f"CV language: {ja.cvLanguage}"
    )


# ---------- Step 0: Job analysis ----------

JOB_ANALYSIS_RULES = """\
You turn a raw job advertisement into a structured job analysis.

Rules:
- Extract only what the advertisement actually states or clearly implies.
  Do not add generic recruiting assumptions (e.g. do not invent a degree
  requirement, a language requirement, a years-of-experience requirement,
  or a certification requirement unless the text actually asks for it).
- requiredSkills: explicitly required skills/technologies/qualifications.
- niceToHaveSkills: skills mentioned as a plus/preferred but not required.
- keyResponsibilities: the main duties of the role, as short phrases.
- atsKeywords: important keywords an ATS system would likely scan for
  (skills, tools, methodologies, role-specific terms) — derived only from
  the text given.
- idealCandidateProfile: 1-3 sentences describing who the employer is
  looking for, grounded in the text.
- cvLanguage: "de" if the posting is primarily in German, otherwise "en".
- companyResearch: 1-2 factual sentences about the company if the posting
  itself gives any indication (industry, size, product) — otherwise leave
  it as an empty string. Do not invent company facts.
"""


def analyze_job(provider: LLMProvider, job: dict) -> tuple[JobAnalysis, LLMUsage]:
    system_blocks = [_cached(JOB_ANALYSIS_RULES)]
    content_blocks = [_plain(f"JOB ADVERTISEMENT:\n{_job_block(job)}")]
    return provider.structured_call(
        system_blocks=system_blocks,
        content_blocks=content_blocks,
        output_model=JobAnalysis,
        max_tokens=2000,
    )


# ---------- Step 1: Evidence selection + resume match ----------

SELECTION_RULES = """\
You are comparing a candidate's factual resume evidence against a job's
requirements. You will be given a list of atomic evidence items (each
with a stable id like "exp_ab12cd34ef56"), and a job analysis.

For EVERY evidence item, decide:
- relevanceScore (0-100): how relevant this specific item is to this job.
- decision: "include" (clearly relevant, should appear in a tailored CV
  for this job), "maybe" (tangentially relevant, borderline), or
  "exclude" (not relevant to this job).
- matchedRequirements: which of the job's requiredSkills/
  keyResponsibilities/idealCandidateProfile this item provides evidence
  for (use the job's own wording where possible).
- matchedKeywords: which of the job's atsKeywords this item's text
  naturally supports.
- reason: one concise sentence explaining the decision.

sourceId must always be copied exactly from the evidence item's id — never
invent an id and never use generated text as an id.

Then produce an overall resume-match summary:
- matchScore (0-100): overall fit of this candidate for this job, based
  only on the evidence provided.
- strongMatches: job requirements clearly well-covered by "include" items.
- partialMatches: job requirements only loosely/partially covered.
- missingRequirements: job requirements (from requiredSkills/
  keyResponsibilities) with no supporting evidence at all. Only list
  something here if the job analysis actually asked for it — never invent
  a requirement the job didn't mention.
- atsKeywordsCovered: which of the job's atsKeywords have real supporting
  evidence.

Never infer a skill for a candidate just because it would help the match.
Every judgment must be traceable to the evidence text given.

The candidate has told us the following are NOT worth flagging as
missing — either not relevant to the roles they want, or something
they've since gained real experience with. Never list any of these (or
close variants of the same underlying thing) in missingRequirements, and
don't let them lower matchScore.
"""


def select_evidence_and_match(
    provider: LLMProvider,
    evidence: list[EvidenceItem],
    job_analysis: JobAnalysis,
    ignored_requirements: Optional[list[str]] = None,
) -> tuple[ResumeMatchResult, LLMUsage]:
    ignored_block = ", ".join(ignored_requirements) if ignored_requirements else "(none)"
    system_blocks = [_cached(SELECTION_RULES)]
    content_blocks = [
        _cached(f"CANDIDATE RESUME EVIDENCE:\n{render_evidence_block(evidence)}"),
        _plain(f"JOB ANALYSIS:\n{_job_analysis_block(job_analysis)}"),
        _plain(f"NOT WORTH FLAGGING AS MISSING: {ignored_block}"),
    ]
    return provider.structured_call(
        system_blocks=system_blocks,
        content_blocks=content_blocks,
        output_model=ResumeMatchResult,
        max_tokens=8000,
    )


# ---------- Step 2: CV draft generation ----------

DRAFT_RULES = """\
You write a tailored CV draft using ONLY the candidate evidence items
given to you (identified by "groupKey:sourceId" pairs). You are NOT given
company names, roles, dates, institutions, or degrees to reproduce — those
come from elsewhere and are not your job to write. Your job is wording
only:

1. For each job group (a real employment position, already grouped for
   you), select and rewrite bullets from ONLY that group's evidence items.
   Bullets should be concise, professional, achievement-oriented, and
   ATS-readable. You may combine two related bullets from the SAME group
   into one bullet. You may drop weak/irrelevant bullets. Prefer 3-6
   bullets for highly relevant groups, fewer for less relevant ones. Every
   bullet's sourceIds must list the evidence id(s) (copied exactly) it was
   built from — never an empty list, never an invented id.
2. Same for education groups.
3. NEVER invent a fact, metric, technology, or achievement not present in
   the cited evidence text. If a source bullet says "improved onboarding"
   with no number, do not add a percentage. Only use ATS keywords when the
   evidence genuinely supports them — no keyword stuffing.
4. Write a 2-4 sentence profileSummary positioning the candidate for this
   specific job, synthesizing real evidence — set profileSummarySourceIds
   to the evidence ids it draws on (at least one). Do not claim the
   candidate previously held the target job title unless a source item
   says so.
5. skillGroups: build 1-4 groups from the categories languages,
   productBusiness, tools, strengths — but every skill/tool listed MUST
   come from the SKILLS WHITELIST given to you (it was extracted from the
   included evidence). Never add a skill just because the job wants it.
"""


def _group_key(evidence_type: str, entry_index: int) -> str:
    return f"{evidence_type}:{entry_index}"


def generate_draft(
    provider: LLMProvider, included_evidence: list[EvidenceItem], job_analysis: JobAnalysis
) -> tuple[CVDraftLLMOutput, LLMUsage]:
    work_groups: dict[str, list[EvidenceItem]] = {}
    edu_groups: dict[str, list[EvidenceItem]] = {}
    skills_whitelist: set[str] = set()
    for item in included_evidence:
        skills_whitelist.update(item.skills)
        if item.type == "work":
            work_groups.setdefault(_group_key(item.type, item.entry_index), []).append(item)
        elif item.type == "education":
            edu_groups.setdefault(_group_key(item.type, item.entry_index), []).append(item)
        else:
            work_groups.setdefault(_group_key(item.type, item.entry_index), []).append(item)

    groups_block_lines = ["WORK/TRAINING GROUPS (write bullets only from within a group):"]
    for key, items in work_groups.items():
        groups_block_lines.append(f"\nGroup {key} — {items[0].label}:")
        for it in items:
            groups_block_lines.append(f"  [{it.id}] {it.bullet}")
    groups_block_lines.append("\nEDUCATION GROUPS:")
    for key, items in edu_groups.items():
        groups_block_lines.append(f"\nGroup {key} — {items[0].label}:")
        for it in items:
            groups_block_lines.append(f"  [{it.id}] {it.bullet}")
    groups_block_lines.append(f"\nSKILLS WHITELIST: {', '.join(sorted(skills_whitelist)) or '(none)'}")

    system_blocks = [_cached(DRAFT_RULES)]
    content_blocks = [
        _cached("\n".join(groups_block_lines)),
        _plain(f"JOB ANALYSIS:\n{_job_analysis_block(job_analysis)}"),
    ]
    draft, usage = provider.structured_call(
        system_blocks=system_blocks,
        content_blocks=content_blocks,
        output_model=CVDraftLLMOutput,
        max_tokens=8000,
    )
    return draft, usage


# ---------- Step 3: Evaluation ----------

EVAL_RULES = """\
You evaluate a tailored CV draft against a job's requirements. Judge only
against: jobTitle, requiredSkills, niceToHaveSkills, keyResponsibilities,
atsKeywords, idealCandidateProfile. Never penalize the CV for missing
something the job analysis never asked for.

Evaluate:
- Relevance: does the CV foreground the most relevant evidence?
- Coverage: are important employer requirements represented, where
  supporting evidence exists?
- ATS coverage: are relevant ATS keywords naturally represented?
- Prioritization: do the strongest experiences get the most space?
- Honesty: does every claim look grounded (no suspicious invented-looking
  specifics)?
- Clarity: is positioning toward the target role clear?

Return score (0-100) and passed = (score >= 75). feedback must be
specific and actionable — reference an actual gap or a specific bullet,
never a vague "improve the CV." Example of a good feedback item: {"type":
"missing_coverage", "requirement": "stakeholder management", "message":
"Existing stakeholder-management evidence is underrepresented in the
bullets."}
"""


def evaluate_cv(
    provider: LLMProvider, cv_summary_text: str, job_analysis: JobAnalysis
) -> tuple[EvaluationResult, LLMUsage]:
    system_blocks = [_cached(EVAL_RULES)]
    content_blocks = [
        _plain(f"JOB ANALYSIS:\n{_job_analysis_block(job_analysis)}"),
        _plain(f"CV DRAFT:\n{cv_summary_text}"),
    ]
    return provider.structured_call(
        system_blocks=system_blocks,
        content_blocks=content_blocks,
        output_model=EvaluationResult,
        max_tokens=2000,
    )


# ---------- Step 4: Targeted revision ----------

REVISION_RULES = DRAFT_RULES + """

This is a REVISION, not a rewrite. You are given the current draft and
specific evaluator feedback. Only change what the feedback asks for —
preserve wording, order, and content the feedback didn't flag. If the
feedback asks for something not supported by the evidence given, do NOT
invent it — either make the closest truthful wording improvement or leave
it as-is. Do not reorder groups or reshuffle unrelated bullets.
"""


def revise_draft(
    provider: LLMProvider,
    included_evidence: list[EvidenceItem],
    job_analysis: JobAnalysis,
    current_draft: CVDraftLLMOutput,
    feedback_text: str,
) -> tuple[CVDraftLLMOutput, LLMUsage]:
    work_groups: dict[str, list[EvidenceItem]] = {}
    edu_groups: dict[str, list[EvidenceItem]] = {}
    skills_whitelist: set[str] = set()
    for item in included_evidence:
        skills_whitelist.update(item.skills)
        target = work_groups if item.type != "education" else edu_groups
        target.setdefault(_group_key(item.type, item.entry_index), []).append(item)

    groups_block_lines = ["WORK/TRAINING GROUPS:"]
    for key, items in work_groups.items():
        groups_block_lines.append(f"\nGroup {key} — {items[0].label}:")
        for it in items:
            groups_block_lines.append(f"  [{it.id}] {it.bullet}")
    groups_block_lines.append("\nEDUCATION GROUPS:")
    for key, items in edu_groups.items():
        groups_block_lines.append(f"\nGroup {key} — {items[0].label}:")
        for it in items:
            groups_block_lines.append(f"  [{it.id}] {it.bullet}")
    groups_block_lines.append(f"\nSKILLS WHITELIST: {', '.join(sorted(skills_whitelist)) or '(none)'}")

    system_blocks = [_cached(REVISION_RULES)]
    content_blocks = [
        _cached("\n".join(groups_block_lines)),
        _plain(f"JOB ANALYSIS:\n{_job_analysis_block(job_analysis)}"),
        _plain(f"CURRENT DRAFT:\n{current_draft.model_dump_json(indent=2)}"),
        _plain(f"EVALUATOR FEEDBACK TO ADDRESS:\n{feedback_text}"),
    ]
    return provider.structured_call(
        system_blocks=system_blocks,
        content_blocks=content_blocks,
        output_model=CVDraftLLMOutput,
        max_tokens=8000,
    )


# ---------- Step 5: Final polish ----------

POLISH_RULES = """\
You are a copy editor, not a CV writer. You may ONLY improve wording,
grammar, readability, conciseness, professional tone, and natural ATS
keyword phrasing. You must NOT add, remove, or change any fact, company,
role, date, institution, degree, metric, or skill. You must NOT change
what a bullet claims — only how it's phrased. Keep the same number of
bullets per group, in the same order. Return the polished text in the
exact same structure/order you were given.
"""


def polish_draft(provider: LLMProvider, draft: CVDraftLLMOutput) -> tuple[PolishLLMOutput, LLMUsage]:
    import json as _json

    payload = {
        "profileSummary": draft.profileSummary,
        "jobBulletTexts": [[b.text for b in g.bullets] for g in draft.jobGroups],
        "educationBulletTexts": [[b.text for b in g.bullets] for g in draft.educationGroups],
    }

    system_blocks = [_cached(POLISH_RULES)]
    content_blocks = [_plain(f"DRAFT TO POLISH:\n{_json.dumps(payload, indent=2)}")]
    return provider.structured_call(
        system_blocks=system_blocks,
        content_blocks=content_blocks,
        output_model=PolishLLMOutput,
        max_tokens=8000,
    )
