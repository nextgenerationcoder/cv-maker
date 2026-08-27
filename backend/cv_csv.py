"""CSV import/export for CVProfile.

Deliberately a flat "long" table (one row per item, a `type` column
disambiguates what it is) rather than one row per profile — a nested
structure like education/work history with a variable number of entries
doesn't map cleanly onto flat columns, and this shape is easy for any LLM
to produce reliably and easy for us to parse with the stdlib csv module,
no guessing involved on either side.
"""

import csv
import io
from typing import List, Tuple

from cv_models import (
    CVProfile,
    ContactInfo,
    EducationEntry,
    LanguageEntry,
    WorkExperienceEntry,
)

FIELDNAMES = ["type", "field1", "field2", "field3", "field4", "field5", "field6"]

# type -> (field1 name, field2 name, ...) for building the template / docs.
ROW_SCHEMAS = {
    "contact": ["name", "email", "phone", "location", "linkedin", "website"],
    "summary": ["summary text"],
    "skill": ["skill"],
    "technical": ["technical knowledge item"],
    "education": ["institution", "degree", "field_of_study", "start_date", "end_date", "details"],
    "work": ["title", "company", "start_date", "end_date", "location", "responsibilities (separate with ;)"],
    "language": ["name", "proficiency"],
    "preferred_role": ["preferred role"],
    "certification": ["certification"],
}

TEMPLATE_EXAMPLE_ROWS = [
    ["contact", "Jane Doe", "jane@example.com", "+1 555 123 4567", "Berlin, Germany", "https://linkedin.com/in/janedoe", "https://janedoe.dev"],
    ["summary", "2-3 sentence professional summary.", "", "", "", "", ""],
    ["skill", "Project Management", "", "", "", "", ""],
    ["skill", "Excel", "", "", "", "", ""],
    ["technical", "Python", "", "", "", "", ""],
    ["technical", "Docker", "", "", "", "", ""],
    ["education", "MIT", "BSc", "Computer Science", "2016", "2020", "Relevant coursework or highlights"],
    ["work", "Software Engineer", "Acme Corp", "2020", "2022", "Berlin", "Built X; Led Y; Shipped Z"],
    ["language", "English", "Native", "", "", "", ""],
    ["preferred_role", "Backend Engineer", "", "", "", "", ""],
    ["certification", "AWS Certified Solutions Architect", "", "", "", "", ""],
]


def build_template_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(FIELDNAMES)
    for row in TEMPLATE_EXAMPLE_ROWS:
        writer.writerow(row)
    return buf.getvalue()


def profile_to_csv(profile: CVProfile) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(FIELDNAMES)

    c = profile.contact
    writer.writerow(["contact", c.name or "", c.email or "", c.phone or "", c.location or "", c.linkedin or "", c.website or ""])
    if profile.summary:
        writer.writerow(["summary", profile.summary, "", "", "", "", ""])
    for s in profile.skills:
        writer.writerow(["skill", s, "", "", "", "", ""])
    for t in profile.technical_knowledge:
        writer.writerow(["technical", t, "", "", "", "", ""])
    for e in profile.education:
        writer.writerow(["education", e.institution, e.degree or "", e.field_of_study or "", e.start_date or "", e.end_date or "", e.details or ""])
    for w in profile.work_experience:
        writer.writerow(["work", w.title, w.company, w.start_date or "", w.end_date or "", w.location or "", "; ".join(w.responsibilities)])
    for lang in profile.languages:
        writer.writerow(["language", lang.name, lang.proficiency or "", "", "", "", ""])
    for r in profile.preferred_roles:
        writer.writerow(["preferred_role", r, "", "", "", "", ""])
    for cert in profile.certifications:
        writer.writerow(["certification", cert, "", "", "", "", ""])

    return buf.getvalue()


def csv_text_to_profile(csv_text: str) -> Tuple[CVProfile, List[str]]:
    """Returns (profile, warnings) — warnings list malformed/unrecognized
    rows that were skipped, so a few LLM mistakes don't sink the whole
    import."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("Empty CSV file.")
    missing_cols = [f for f in FIELDNAMES if f not in reader.fieldnames]
    if missing_cols:
        raise ValueError(
            f"CSV is missing expected column(s): {', '.join(missing_cols)}. "
            f"Expected header: {','.join(FIELDNAMES)}"
        )

    contact = ContactInfo()
    summary = None
    skills: List[str] = []
    technical_knowledge: List[str] = []
    education: List[EducationEntry] = []
    work_experience: List[WorkExperienceEntry] = []
    languages: List[LanguageEntry] = []
    preferred_roles: List[str] = []
    certifications: List[str] = []
    warnings: List[str] = []

    def get(row: dict, key: str) -> str:
        return (row.get(key) or "").strip()

    for i, row in enumerate(reader, start=2):  # start=2: header is row 1
        row_type = get(row, "type").lower()
        f = [get(row, f"field{n}") for n in range(1, 7)]

        if row_type == "contact":
            contact = ContactInfo(
                name=f[0] or None, email=f[1] or None, phone=f[2] or None,
                location=f[3] or None, linkedin=f[4] or None, website=f[5] or None,
            )
        elif row_type == "summary":
            summary = f[0] or None
        elif row_type == "skill":
            if f[0]:
                skills.append(f[0])
        elif row_type == "technical":
            if f[0]:
                technical_knowledge.append(f[0])
        elif row_type == "education":
            if f[0]:
                education.append(EducationEntry(
                    institution=f[0], degree=f[1] or None, field_of_study=f[2] or None,
                    start_date=f[3] or None, end_date=f[4] or None, details=f[5] or None,
                ))
            else:
                warnings.append(f"Row {i}: education row missing institution, skipped.")
        elif row_type == "work":
            if f[0] or f[1]:
                responsibilities = [r.strip() for r in f[5].split(";") if r.strip()]
                work_experience.append(WorkExperienceEntry(
                    title=f[0] or "", company=f[1] or "", start_date=f[2] or None,
                    end_date=f[3] or None, location=f[4] or None, responsibilities=responsibilities,
                ))
            else:
                warnings.append(f"Row {i}: work row missing title and company, skipped.")
        elif row_type == "language":
            if f[0]:
                languages.append(LanguageEntry(name=f[0], proficiency=f[1] or None))
        elif row_type == "preferred_role":
            if f[0]:
                preferred_roles.append(f[0])
        elif row_type == "certification":
            if f[0]:
                certifications.append(f[0])
        elif row_type == "":
            continue  # blank row
        else:
            warnings.append(f"Row {i}: unrecognized type '{row_type}', skipped.")

    profile = CVProfile(
        contact=contact,
        summary=summary,
        skills=skills,
        technical_knowledge=technical_knowledge,
        education=education,
        work_experience=work_experience,
        languages=languages,
        preferred_roles=preferred_roles,
        certifications=certifications,
    )
    return profile, warnings
