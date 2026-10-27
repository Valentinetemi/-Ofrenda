"""The family file and the JSON we ask the model to return."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Gender = Literal["female", "male"]
RelationKind = Literal["parent", "spouse", "sibling"]


class Person(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    origin: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    gender: Gender | None = None
    bio: str = ""
    memories: list[str] = Field(default_factory=list)
    photo: str | None = None
    parent_ids: list[str] = Field(default_factory=list)
    spouse_ids: list[str] = Field(default_factory=list)
    sibling_ids: list[str] = Field(default_factory=list)


class FamilyTree(BaseModel):
    """One household's altar. Stored as JSON on the laptop, never uploaded."""

    model_config = ConfigDict(extra="ignore")

    people: list[Person] = Field(default_factory=list)
    narrator_id: str | None = None
    sample: bool = False


class ExtractedPerson(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    origin: str | None = None
    notes: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    gender: Gender | None = None
    memories: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: RelationKind
    source: str
    target: str


class Extraction(BaseModel):
    people: list[ExtractedPerson] = Field(default_factory=list)
    relationships: list[Relation] = Field(default_factory=list)


class Suggestion(BaseModel):
    id: str
    person_id: str
    person_name: str
    kind: str
    question: str
    source: Literal["rules", "gemma"] = "rules"
