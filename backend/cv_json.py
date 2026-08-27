"""JSON import/export for CVProfile.

The schema matches a "source of truth" template the user already had in
use elsewhere (personal_information / work_experience / education /
training_and_projects / languages / tools, with per-bullet skills and
metrics, and free-form tool categories) — CVProfile in cv_models.py is
kept in exact structural sync with it, including extra="forbid" so a
typo'd key from a hand-edited or LLM-produced file is caught as a clear
error rather than silently dropped.
"""

import json

from pydantic import ValidationError

from cv_models import CVProfile

TEMPLATE = {
    "personal_information": {
        "name": "",
        "email": "",
        "phone": "",
        "location": None,
    },
    "work_experience": [
        {
            "company": "",
            "role": "",
            "period": "",
            "location": "",
            "experiences": [
                {"bullet": "", "skills": [], "metrics": []},
            ],
        }
    ],
    "education": [
        {
            "institution": "",
            "program": "",
            "degree": None,
            "period": "",
            "location": "",
            "experiences": [
                {"bullet": "", "skills": [], "metrics": []},
            ],
        }
    ],
    "training_and_projects": [
        {
            "title": "",
            "period": "",
            "duration": "",
            "experiences": [
                {"bullet": "", "skills": [], "metrics": []},
            ],
        }
    ],
    "languages": [
        {"language": "", "level": ""},
    ],
    "tools": {
        "ai_automation": [{"name": "", "level": None}],
        "project_knowledge_data": [{"name": "", "level": None}],
        "design_web_engineering": [{"name": "", "level": None}],
    },
}


def build_template_json() -> str:
    return json.dumps(TEMPLATE, indent=2)


def json_text_to_profile(text: str) -> CVProfile:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Not valid JSON: {exc}") from exc

    try:
        return CVProfile.model_validate(data)
    except ValidationError as exc:
        messages = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(root)"
            messages.append(f"{loc}: {err['msg']}")
        raise ValueError("Doesn't match the expected schema:\n" + "\n".join(messages)) from exc


def profile_to_json(profile: CVProfile) -> str:
    return profile.model_dump_json(indent=2)
