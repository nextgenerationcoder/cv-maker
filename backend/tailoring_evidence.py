"""Flattens a CVProfile into atomic, individually-addressable evidence
items with stable IDs, and reassembles selected items back into CV
positions. Structural facts (company/role/period/location/degree/
institution) always come from here verbatim — the LLM never regenerates
them, which is the main hallucination guard for those fields.

IDs are derived deterministically from content (section + entry index +
bullet text), not stored in the DB. That means the resume DB needs no
schema migration and no rewrite when new experiences are appended — an
existing item's ID only changes if its own text is edited, which is an
acceptable trade-off (an edited claim is, for provenance purposes,
effectively a new claim).
"""
import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, computed_field


class EvidenceItem(BaseModel):
    id: str
    type: Literal["work", "education", "training"]
    entry_index: int
    company: Optional[str] = None
    role: Optional[str] = None
    institution: Optional[str] = None
    degree: Optional[str] = None
    program: Optional[str] = None
    title: Optional[str] = None
    period: Optional[str] = None
    location: Optional[str] = None
    bullet: str
    skills: list[str] = []
    metrics: list[str] = []

    @computed_field  # type: ignore[misc]
    @property
    def label(self) -> str:
        if self.type == "work":
            return f"{self.role} at {self.company}"
        if self.type == "education":
            head = self.degree or self.program or "Education"
            return f"{head} — {self.institution}"
        return self.title or "Training/project"


def _make_id(cv_id: str, type_: str, entry_index: int, bullet_index: int, bullet: str) -> str:
    digest = hashlib.sha1(f"{cv_id}|{type_}|{entry_index}|{bullet}".encode("utf-8")).hexdigest()
    return f"exp_{digest[:12]}"


def build_evidence_pool(cv_id: str, profile: dict) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []

    for i, entry in enumerate(profile.get("work_experience") or []):
        for j, exp in enumerate(entry.get("experiences") or []):
            bullet = (exp.get("bullet") or "").strip()
            if not bullet:
                continue
            items.append(
                EvidenceItem(
                    id=_make_id(cv_id, "work", i, j, bullet),
                    type="work",
                    entry_index=i,
                    company=entry.get("company"),
                    role=entry.get("role"),
                    period=entry.get("period"),
                    location=entry.get("location"),
                    bullet=bullet,
                    skills=exp.get("skills") or [],
                    metrics=exp.get("metrics") or [],
                )
            )

    for i, entry in enumerate(profile.get("education") or []):
        for j, exp in enumerate(entry.get("experiences") or []):
            bullet = (exp.get("bullet") or "").strip()
            if not bullet:
                continue
            items.append(
                EvidenceItem(
                    id=_make_id(cv_id, "education", i, j, bullet),
                    type="education",
                    entry_index=i,
                    institution=entry.get("institution"),
                    degree=entry.get("degree"),
                    program=entry.get("program"),
                    period=entry.get("period"),
                    location=entry.get("location"),
                    bullet=bullet,
                    skills=exp.get("skills") or [],
                    metrics=exp.get("metrics") or [],
                )
            )

    for i, entry in enumerate(profile.get("training_and_projects") or []):
        for j, exp in enumerate(entry.get("experiences") or []):
            bullet = (exp.get("bullet") or "").strip()
            if not bullet:
                continue
            items.append(
                EvidenceItem(
                    id=_make_id(cv_id, "training", i, j, bullet),
                    type="training",
                    entry_index=i,
                    title=entry.get("title"),
                    period=entry.get("period"),
                    bullet=bullet,
                    skills=exp.get("skills") or [],
                    metrics=exp.get("metrics") or [],
                )
            )

    return items


def render_evidence_block(items: list[EvidenceItem]) -> str:
    """Stable, deterministic text rendering of the evidence pool — this is
    the block we put behind a cache_control breakpoint, so it must be
    byte-identical across calls for the same CV to actually hit cache."""
    lines: list[str] = []
    for item in items:
        tail = ""
        if item.skills:
            tail += f" [skills: {', '.join(item.skills)}]"
        if item.metrics:
            tail += f" [metrics: {', '.join(item.metrics)}]"
        lines.append(f"[{item.id}] ({item.type} — {item.label}, {item.period or 'no dates given'}) {item.bullet}{tail}")
    return "\n".join(lines) if lines else "(no resume evidence on file)"
