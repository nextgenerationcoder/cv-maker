from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PersonalInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    email: str = ""
    phone: str = ""
    location: Optional[str] = None


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullet: str
    skills: List[str] = Field(default_factory=list)
    metrics: List[str] = Field(default_factory=list)


class WorkExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str
    role: str
    period: str
    location: Optional[str] = None
    experiences: List[ExperienceItem] = Field(default_factory=list)


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str
    program: str
    degree: Optional[str] = None
    period: str
    location: Optional[str] = None
    experiences: List[ExperienceItem] = Field(default_factory=list)


class TrainingProjectEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    period: str
    duration: Optional[str] = None
    experiences: List[ExperienceItem] = Field(default_factory=list)


class LanguageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str
    level: str


class ToolItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    level: Optional[str] = None


class CVProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal_information: PersonalInformation = Field(default_factory=PersonalInformation)
    work_experience: List[WorkExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    training_and_projects: List[TrainingProjectEntry] = Field(default_factory=list)
    languages: List[LanguageEntry] = Field(default_factory=list)
    tools: Dict[str, List[ToolItem]] = Field(default_factory=dict)
