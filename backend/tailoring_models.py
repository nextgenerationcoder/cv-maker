from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------- Job analysis ----------


class JobAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobTitle: str
    companyName: Optional[str] = None
    jobLocation: Optional[str] = None
    companyResearch: str = ""
    requiredSkills: List[str] = Field(default_factory=list)
    niceToHaveSkills: List[str] = Field(default_factory=list)
    keyResponsibilities: List[str] = Field(default_factory=list)
    atsKeywords: List[str] = Field(default_factory=list)
    idealCandidateProfile: str = ""
    cvLanguage: Literal["de", "en"] = "en"


# ---------- Evidence selection / resume match ----------


class EvidenceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sourceId: str
    relevanceScore: int = Field(ge=0, le=100)
    decision: Literal["include", "maybe", "exclude"]
    matchedRequirements: List[str] = Field(default_factory=list)
    matchedKeywords: List[str] = Field(default_factory=list)
    reason: str


class ResumeMatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matchScore: int = Field(ge=0, le=100)
    strongMatches: List[str] = Field(default_factory=list)
    partialMatches: List[str] = Field(default_factory=list)
    missingRequirements: List[str] = Field(default_factory=list)
    atsKeywordsCovered: List[str] = Field(default_factory=list)
    selection: List[EvidenceSelection]


# ---------- CV draft (LLM-facing: wording only, no structural facts) ----------


class DraftBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    sourceIds: List[str] = Field(default_factory=list)


class DraftJobGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groupKey: str  # matches an evidence item's "work:<entry_index>" grouping key
    bullets: List[DraftBullet]


class DraftEducationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groupKey: str  # "education:<entry_index>"
    bullets: List[DraftBullet]


class DraftSkillGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["languages", "productBusiness", "tools", "strengths"]
    items: List[str] = Field(default_factory=list)


class CVDraftLLMOutput(BaseModel):
    """What the draft-generation LLM call actually returns. No company/
    role/dates/institution/degree here on purpose — those are filled in
    by the orchestrator from the canonical evidence, never by the model."""

    model_config = ConfigDict(extra="forbid")
    profileSummary: str
    profileSummarySourceIds: List[str] = Field(default_factory=list)
    jobGroups: List[DraftJobGroup]
    educationGroups: List[DraftEducationGroup]
    skillGroups: List[DraftSkillGroup]


class PolishLLMOutput(BaseModel):
    """Wording-only pass. Same shape as the draft's bullet/summary fields —
    deliberately excludes skillGroups and sourceIds, since polish must
    never change what a bullet claims, cites, or what skills are listed."""

    model_config = ConfigDict(extra="forbid")
    profileSummary: str
    jobBulletTexts: List[List[str]]  # same order/shape as the draft's job groups
    educationBulletTexts: List[List[str]]


# ---------- Evaluation / revision ----------


class EvaluationFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    requirement: Optional[str] = None
    message: str


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: int = Field(ge=0, le=100)
    passed: bool
    feedback: List[EvaluationFeedback] = Field(default_factory=list)


# ---------- Final public CV schema ----------


class CVBullet(BaseModel):
    text: str


class CVJobEntry(BaseModel):
    date: str
    title: str
    type: str = "work"
    company: str
    location: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


class CVEducationEntry(BaseModel):
    date: str
    degree: str
    institution: str
    location: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


class CVSkills(BaseModel):
    languages: str = ""
    productBusiness: str = ""
    tools: str = ""
    strengths: str = ""


class TailoredCV(BaseModel):
    lang: Literal["de", "en"] = "en"
    name: str = ""
    jobTitle: str = ""
    location: str = ""
    phone: str = ""
    email: str = ""
    photo: str = ""
    profileSummary: str = ""
    jobs: List[CVJobEntry] = Field(default_factory=list)
    education: List[CVEducationEntry] = Field(default_factory=list)
    skills: CVSkills = Field(default_factory=CVSkills)


# ---------- Internal generation result (richer than the public CV) ----------


class ProvenanceEntry(BaseModel):
    path: str
    sourceIds: List[str]


class GenerationMeta(BaseModel):
    resumeVersion: str
    revisionCount: int
    model: str
    provider: str = "anthropic"
    inputTokens: int = 0
    cachedInputTokens: int = 0
    outputTokens: int = 0
    latencyMs: int = 0
    droppedBullets: int = 0


class InternalGenerationResult(BaseModel):
    cv: TailoredCV
    selection: List[EvidenceSelection]
    provenance: List[ProvenanceEntry]
    evaluation: EvaluationResult
    generation: GenerationMeta
