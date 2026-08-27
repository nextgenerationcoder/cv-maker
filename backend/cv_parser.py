"""Rule-based CV text extraction — no LLM/API involved.

Extracts text with pdfplumber's layout-preserving mode (needed so a
multi-column resume doesn't scramble dates away from the entries they
belong to — plain stream-order extraction does exactly that on common
resume templates), splits it into sections using a list of known
section-header phrases (English + German), then applies per-section
heuristics (regex for dates/emails/phones, indentation/bullet splitting,
keyword matching for "is this a tech term") to fill out a CVProfile.

This is inherently rougher than an LLM-based extraction: it will do
noticeably worse on CVs with unusual layouts, non-listed section headers,
or free-flowing prose instead of clear bullet points/date-prefixed entries.
"""

import re
from typing import Optional

import pdfplumber

from cv_models import (
    CVProfile,
    ContactInfo,
    EducationEntry,
    LanguageEntry,
    WorkExperienceEntry,
)

SECTION_HEADERS: dict[str, list[str]] = {
    "summary": [
        "summary", "profile", "objective", "about me", "career objective",
        "personal profile", "über mich", "profil", "zusammenfassung",
    ],
    "technical_knowledge": [
        "technical skills", "technical knowledge", "technologies", "tech stack",
        "it kenntnisse", "software kenntnisse", "it-kenntnisse",
    ],
    "skills": [
        "skills", "key skills", "core skills", "competencies",
        "kenntnisse", "fähigkeiten", "kompetenzen",
    ],
    "education": [
        "education", "academic background", "academic history",
        "ausbildung", "bildung", "schulbildung", "studium",
    ],
    "work_experience": [
        "work experience", "professional experience", "experience",
        "employment history", "work history",
        "berufserfahrung", "berufliche erfahrung", "praxiserfahrung", "werdegang",
    ],
    "languages": ["languages", "sprachen", "sprachkenntnisse"],
    "certifications": [
        "certifications", "certificates", "licenses",
        "zertifikate", "zertifizierungen",
    ],
    "preferred_roles": ["target role", "desired position", "zielposition"],
}
# Longest phrase first so e.g. "professional experience" wins over a
# shorter substring that might also match.
_HEADER_ENTRIES = sorted(
    ((phrase, section) for section, phrases in SECTION_HEADERS.items() for phrase in phrases),
    key=lambda pair: -len(pair[0]),
)

# Inline "Label: comma, separated, items" lines (common inside a single
# generic "Skills" block instead of separate headed sections).
_INLINE_LABEL_ROUTES: list[tuple[str, str]] = [
    ("language", "languages"),
    ("sprach", "languages"),
    ("tool", "technical_knowledge"),
    ("technical", "technical_knowledge"),
    ("technolog", "technical_knowledge"),
    ("software", "technical_knowledge"),
    ("it ", "technical_knowledge"),
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,5}\d{2,4}")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/\S+", re.IGNORECASE)
WEBSITE_RE = re.compile(r"(?:https?://)?(?:www\.)?[\w-]+\.\w{2,}(?:/\S*)?", re.IGNORECASE)
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|M(?:ä|ae)?r(?:ch|z)?|Apr(?:il)?|Ma[iy]|Jun[ei]?|"
    r"Jul[iy]?|Aug(?:ust)?|Sep(?:t|tember)?|Okt|Oct(?:ober)?|Nov(?:ember)?|De[cz](?:ember)?)"
)
# Matches a date range anywhere in a line — different CVs (and different
# sections of the same CV) put the date before or after the entry title,
# so this is searched, not anchored to line-start. The month name is an
# explicit list, not "any short word" — a loose `[A-Za-z]{3,9}` alternative
# here previously matched arbitrary word-endings ("...ship" in
# "Entrepreneurship") sitting in front of an unrelated year elsewhere on
# the line, silently corrupting titles.
DATE_RANGE_RE = re.compile(
    rf"(\d{{1,2}}/\d{{4}}|{_MONTH}\.?\s+\d{{4}}|\d{{4}})\s*[-–—]\s*"
    rf"(\d{{1,2}}/\d{{4}}|{_MONTH}\.?\s+\d{{4}}|\d{{4}}|present|current|today|heute|now|ongoing)",
    re.IGNORECASE,
)
# A date range that wrapped across two physical lines in a narrow column
# (e.g. "July 2018 – September" / "2020 ...") — merged before block
# splitting so DATE_RANGE_RE can see the whole span on one line.
_ORPHAN_MONTH_END_RE = re.compile(rf"{_MONTH}\w*\s*$", re.IGNORECASE)
_LEADING_YEAR_RE = re.compile(r"^\s*\d{4}\b")
INLINE_LABEL_RE = re.compile(r"^\s*([A-Za-zÀ-ÖØ-öø-ÿ&\s]{2,30}):\s*(.+)$")
LOCATION_LINE_RE = re.compile(r"^[A-ZÀ-Ö][\w.\- ]+,\s*[A-ZÀ-Ö][\w.\- ]+$")
# "City, 12345" or "City, Country" — searched within a line, not a whole-line match,
# since the preamble often packs location + phone + email onto one line.
LOCATION_HINT_RE = re.compile(
    r"\b([A-ZÀ-Ö][\wÀ-ÿ.\-]+(?:\s[A-ZÀ-Ö][\wÀ-ÿ.\-]+)?),\s*(\d{4,6}|[A-ZÀ-Ö][\wÀ-ÿ.\- ]{2,20})\b"
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "st", "vs", "etc", "approx", "no", "inc", "ltd", "co",
}

KNOWN_TECH_KEYWORDS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang", "rust",
    "sql", "nosql", "postgresql", "mysql", "mongodb", "redis", "sqlite",
    "docker", "kubernetes", "aws", "azure", "gcp", "terraform", "ansible",
    "react", "angular", "vue", "node.js", "nodejs", "django", "flask", "fastapi",
    "spring", "spring boot", ".net", "html", "css", "sass", "tailwind",
    "git", "github", "gitlab", "ci/cd", "jenkins", "linux", "bash", "powershell",
    "excel", "power bi", "tableau", "sap", "salesforce", "jira", "confluence",
    "figma", "photoshop", "autocad", "matlab", "r", "pandas", "numpy",
    "tensorflow", "pytorch", "scikit-learn", "machine learning", "rest api",
    "graphql", "microservices", "agile", "scrum", "kanban",
}


def extract_pdf_text(pdf_bytes: bytes) -> str:
    import io

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [page.extract_text(layout=True) or "" for page in pdf.pages]
    return "\n".join(pages)


def _match_header(line: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", line.strip().strip(":").strip()).lower()
    if not normalized or len(normalized) > 40:
        return None
    for phrase, section in _HEADER_ENTRIES:
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized):
            return section
    return None


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        header = _match_header(line)
        if header:
            current = header
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on `sep`, but not inside parentheses — so "German (B1, ongoing)"
    stays one item instead of splitting at the comma inside the parens."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _clean_items(lines: list[str], split_commas: bool = True) -> list[str]:
    items: list[str] = []
    for line in lines:
        line = line.strip().lstrip("•-*·▪●○ ").strip()
        if not line:
            continue
        parts = _split_top_level(line) if split_commas else [line]
        for part in parts:
            if part and part not in items:
                items.append(part)
    return items


def _pull_inline_labels(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Pull out "Label: a, b, c" lines matching a known category, routing
    their content to that category and leaving the rest of the lines as-is.
    """
    leftover: list[str] = []
    routed: dict[str, list[str]] = {}
    for line in lines:
        m = INLINE_LABEL_RE.match(line)
        if not m:
            leftover.append(line)
            continue
        label, content = m.group(1).strip().lower(), m.group(2)
        target = next((cat for key, cat in _INLINE_LABEL_ROUTES if key in label), None)
        if target is None:
            # Recognized "Label: items" shape but not a category we route —
            # still strip the label so it doesn't fuse into the first item.
            leftover.append(content)
            continue
        routed.setdefault(target, []).extend(_clean_items([content]))
    return leftover, routed


def _extract_contact(full_text: str, preamble: list[str]) -> ContactInfo:
    email_match = EMAIL_RE.search(full_text)
    linkedin_match = LINKEDIN_RE.search(full_text)

    phone = None
    for line in preamble:
        m = PHONE_RE.search(line)
        if m and sum(c.isdigit() for c in m.group()) >= 6:
            phone = m.group().strip()
            break

    name = None
    for line in preamble[:5]:
        stripped = re.sub(r"\s+", " ", line.strip())
        words = stripped.split()
        if 1 < len(words) <= 4 and not EMAIL_RE.search(stripped) and not any(c.isdigit() for c in stripped):
            name = stripped
            break

    location = None
    for line in preamble:
        m = LOCATION_HINT_RE.search(re.sub(r"\s+", " ", line))
        if m:
            location = m.group(0).strip()
            break

    return ContactInfo(
        name=name,
        email=email_match.group() if email_match else None,
        phone=phone,
        location=location,
        linkedin=linkedin_match.group() if linkedin_match else None,
        website=None,
    )


def _premerge_wrapped_dates(lines: list[str]) -> list[str]:
    merged: list[str] = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        if (
            _ORPHAN_MONTH_END_RE.search(line)
            and i + 1 < len(lines)
            and _LEADING_YEAR_RE.match(lines[i + 1])
        ):
            merged.append(line.rstrip() + " " + lines[i + 1].strip())
            skip_next = True
        else:
            merged.append(line)
    return merged


def _split_into_entry_blocks(lines: list[str]) -> list[tuple[Optional[re.Match], list[str]]]:
    """Group lines into (date_match_or_None, block_lines) using a date range
    found anywhere in a line as an entry boundary — the date sits before the
    title in some CV sections and after it in others."""
    lines = _premerge_wrapped_dates(lines)
    blocks: list[tuple[Optional[re.Match], list[str]]] = []
    current_match: Optional[re.Match] = None
    current: list[str] = []
    for line in lines:
        m = DATE_RANGE_RE.search(line)
        if m:
            if current:
                blocks.append((current_match, current))
            header = re.sub(r"\s+", " ", (line[: m.start()] + line[m.end() :]).strip())
            current_match, current = m, [header] if header else []
        elif line.strip():
            current.append(line)
    if current:
        blocks.append((current_match, current))
    return blocks


def _merge_wrapped_lines(lines: list[str]) -> list[str]:
    """Reconstruct bullet points that got word-wrapped across two physical
    lines by joining everything and re-splitting on sentence boundaries."""
    blob = " ".join(l.strip() for l in lines if l.strip())
    blob = re.sub(r"\s+", " ", blob)
    if not blob:
        return []
    tokens = [s.strip() for s in SENTENCE_SPLIT_RE.split(blob) if s.strip()]
    merged: list[str] = []
    for tok in tokens:
        if merged:
            last_word = re.sub(r"[^\w]", "", merged[-1].split()[-1]).lower() if merged[-1].split() else ""
            if last_word in ABBREVIATIONS:
                merged[-1] = merged[-1] + " " + tok
                continue
        merged.append(tok)
    return merged


def _parse_work_experience(lines: list[str]) -> list[WorkExperienceEntry]:
    entries = []
    for date_match, block in _split_into_entry_blocks(lines):
        block = [l for l in block if l.strip()]
        if not block:
            continue
        title = block[0].strip()
        rest = block[1:]
        company, location = "Unknown", None
        if rest and not LOCATION_LINE_RE.match(rest[0].strip()):
            company = rest[0].strip()
            rest = rest[1:]
        if rest and LOCATION_LINE_RE.match(rest[0].strip()):
            location = rest[0].strip()
            rest = rest[1:]
        entries.append(
            WorkExperienceEntry(
                company=company,
                title=title,
                start_date=date_match.group(1) if date_match else None,
                end_date=date_match.group(2) if date_match else None,
                location=location,
                responsibilities=_merge_wrapped_lines(rest),
            )
        )
    return entries


def _parse_education(lines: list[str]) -> list[EducationEntry]:
    entries = []
    for date_match, block in _split_into_entry_blocks(lines):
        block = [l for l in block if l.strip()]
        if not block:
            continue
        header = block[0].strip()
        institution = block[1].strip() if len(block) > 1 else header
        degree, field = None, None
        for sep in [" – ", " - ", " in "]:
            if sep in header:
                degree, field = [p.strip() for p in header.split(sep, 1)]
                break
        details = _merge_wrapped_lines(block[2:])
        entries.append(
            EducationEntry(
                institution=institution,
                degree=degree or (header if not field else None),
                field_of_study=field,
                start_date=date_match.group(1) if date_match else None,
                end_date=date_match.group(2) if date_match else None,
                details=" ".join(details) or None,
            )
        )
    return entries


def _parse_languages(lines: list[str]) -> list[LanguageEntry]:
    languages = []
    for item in _clean_items(lines):
        proficiency = None
        name = item
        m = re.match(r"^(.*?)\s*[\(\-–:]\s*(.+?)\)?$", item)
        if m and m.group(2):
            name, proficiency = m.group(1).strip(), m.group(2).strip(" )")
        if name:
            languages.append(LanguageEntry(name=name, proficiency=proficiency))
    return languages


def extract_cv_profile(pdf_bytes: bytes) -> CVProfile:
    text = extract_pdf_text(pdf_bytes)
    if not text.strip():
        raise ValueError(
            "No text could be extracted from this PDF — it may be a scanned "
            "image without embedded text, which this parser can't read."
        )

    sections = _split_sections(text)

    skills_lines, routed_from_skills = _pull_inline_labels(sections.get("skills", []))
    tech_lines, routed_from_tech = _pull_inline_labels(sections.get("technical_knowledge", []))
    lang_section_lines = sections.get("languages", [])

    skills = _clean_items(skills_lines) + routed_from_tech.get("skills", [])
    technical_knowledge = (
        _clean_items(tech_lines)
        + routed_from_skills.get("technical_knowledge", [])
        + routed_from_tech.get("technical_knowledge", [])
    )
    if not technical_knowledge:
        technical_knowledge = [s for s in skills if s.lower() in KNOWN_TECH_KEYWORDS]

    languages = _parse_languages(lang_section_lines) or _parse_languages(
        routed_from_skills.get("languages", []) + routed_from_tech.get("languages", [])
    )

    work_experience = _parse_work_experience(sections.get("work_experience", []))

    preferred_roles = _clean_items(sections.get("preferred_roles", []))
    if not preferred_roles:
        seen: list[str] = []
        for job in work_experience[:2]:
            if job.title and job.title not in seen:
                seen.append(job.title)
        preferred_roles = seen

    summary_lines = sections.get("summary", [])
    summary = " ".join(l.strip() for l in summary_lines if l.strip()) or None

    return CVProfile(
        contact=_extract_contact(text, sections.get("preamble", [])),
        summary=summary,
        skills=skills,
        technical_knowledge=technical_knowledge,
        education=_parse_education(sections.get("education", [])),
        work_experience=work_experience,
        languages=languages,
        preferred_roles=preferred_roles,
        certifications=_clean_items(sections.get("certifications", [])),
    )
