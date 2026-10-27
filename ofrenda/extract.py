"""Turn a story into people and relationships.

The model is asked for JSON. We validate it, drop anything that does not fit,
and try again with the error in the next prompt. After the last try, the
caller gets a plain error instead of a half-built tree.
"""

from __future__ import annotations

from collections.abc import Callable

from ofrenda.jsonutil import JsonPayloadError, parse_json_object
from ofrenda.names import display_name, normalize_name
from ofrenda.schemas import ExtractedPerson, Extraction, Relation

Completer = Callable[[str], str]

INSTRUCTIONS = """You extract a family tree from one story. Reply with JSON only, no markdown.
The speaker is always a person named "Me".
Use exactly this shape:
{"people":[{"name":"","origin":null,"notes":null,"birth_year":null,"death_year":null,"gender":null,"memories":[]}],"relationships":[{"kind":"parent","source":"","target":""}]}
Rules:
- kind is "parent", "spouse", or "sibling".
- For parent, source is the parent and target is the child. "my mother is Funke" means source Funke, target Me.
- Resolve her, his, he, she, and they to the person just mentioned.
- Copy names as spoken. Do not invent people, years, places, or memories.
- origin is a place, or null. gender is "female", "male", or null, and only if the story says so.
- memories stays empty unless the story actually tells a small anecdote.
- Include Me in people when the story says my or I.
"""

_KIND_ALIASES = {
    "parent": "parent",
    "parent_of": "parent",
    "mother": "parent",
    "father": "parent",
    "mum": "parent",
    "dad": "parent",
    "spouse": "spouse",
    "married": "spouse",
    "partner": "spouse",
    "wife": "spouse",
    "husband": "spouse",
    "sibling": "sibling",
    "brother": "sibling",
    "sister": "sibling",
    "child": "child",
    "son": "child",
    "daughter": "child",
}

_GENDERS = {
    "female": "female",
    "male": "male",
    "f": "female",
    "m": "male",
    "woman": "female",
    "man": "male",
    "girl": "female",
    "boy": "male",
}


class ExtractionError(ValueError):
    """The story did not become a usable tree."""


def story_prompt(story: str) -> str:
    return (
        INSTRUCTIONS
        + "\nFamily story:\n\"\"\"\n"
        + story.strip()
        + "\n\"\"\"\nReply with JSON only.\n"
    )


def repair_prompt(story: str, previous: str, error: str) -> str:
    return (
        story_prompt(story)
        + "\nYour previous reply was not usable: "
        + error
        + "\nPrevious reply:\n"
        + previous[:2000]
        + "\nReply again with JSON only.\n"
    )


def _clip(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or text.lower() in {"null", "none", "unknown", "n/a"}:
        return None
    return text[:limit]


def _year(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    if 1800 <= year <= 2100:
        return year
    return None


def _gender(value: object) -> str | None:
    if value is None:
        return None
    return _GENDERS.get(str(value).strip().casefold())


def _memories(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    kept: list[str] = []
    for item in value:
        text = _clip(item, 400)
        if text and text not in kept:
            kept.append(text)
        if len(kept) == 6:
            break
    return kept


def validate_extraction(payload: dict) -> Extraction:
    """Turn loose model JSON into an Extraction, or raise ExtractionError."""
    people_raw = payload.get("people")
    rel_raw = payload.get("relationships")
    if people_raw is None:
        people_raw = payload.get("persons")
    if not isinstance(people_raw, list) or not people_raw:
        raise ExtractionError("the reply did not name any people")

    people: list[ExtractedPerson] = []
    for item in people_raw:
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("name"), 80)
        if not name:
            continue
        birth = _year(item.get("birth_year"))
        death = _year(item.get("death_year"))
        if birth and death and death < birth:
            death = None
        people.append(
            ExtractedPerson(
                name=display_name(name),
                origin=_clip(item.get("origin"), 80),
                notes=_clip(item.get("notes"), 400),
                birth_year=birth,
                death_year=death,
                gender=_gender(item.get("gender")),  # type: ignore[arg-type]
                memories=_memories(item.get("memories")),
            )
        )
    if not people:
        raise ExtractionError("every person in the reply had an empty name")

    known = {normalize_name(person.name) for person in people}
    relationships: list[Relation] = []
    if isinstance(rel_raw, list):
        for item in rel_raw:
            if not isinstance(item, dict):
                continue
            kind_raw = str(item.get("kind") or item.get("type") or "").strip().casefold()
            kind = _KIND_ALIASES.get(kind_raw.replace(" ", "_").replace("-", "_"))
            source = _clip(item.get("source") or item.get("from") or item.get("a"), 80)
            target = _clip(item.get("target") or item.get("to") or item.get("b"), 80)
            if kind is None or not source or not target:
                continue
            if kind == "child":
                # The model said source is the child of target. Flip it.
                source, target = target, source
                kind = "parent"
            if normalize_name(source) not in known or normalize_name(target) not in known:
                continue
            relationships.append(
                Relation(kind=kind, source=display_name(source), target=display_name(target))  # type: ignore[arg-type]
            )
    return dedupe_extraction(Extraction(people=people, relationships=relationships))


def dedupe_extraction(extraction: Extraction) -> Extraction:
    """One entry per spoken name. Spouse and sibling links are stored once."""
    merged: dict[str, ExtractedPerson] = {}
    order: list[str] = []
    for person in extraction.people:
        key = normalize_name(person.name)
        if not key:
            continue
        current = merged.get(key)
        if current is None:
            merged[key] = person.model_copy(deep=True)
            order.append(key)
            continue
        if person.origin and not current.origin:
            current.origin = person.origin
        if person.notes and person.notes not in (current.notes or ""):
            current.notes = person.notes if not current.notes else f"{current.notes} {person.notes}"
        if person.birth_year and not current.birth_year:
            current.birth_year = person.birth_year
        if person.death_year and not current.death_year:
            current.death_year = person.death_year
        if person.gender and not current.gender:
            current.gender = person.gender
        for memory in person.memories:
            if memory not in current.memories:
                current.memories.append(memory)

    people = [merged[key] for key in order]
    canon = {normalize_name(person.name): person.name for person in people}
    mentions_me = any(
        normalize_name(end) == "me"
        for rel in extraction.relationships
        for end in (rel.source, rel.target)
    )
    if mentions_me and "me" not in canon:
        people.append(ExtractedPerson(name="Me"))
        canon["me"] = "Me"

    relationships: list[Relation] = []
    seen: set[tuple] = set()
    for rel in extraction.relationships:
        source_key = normalize_name(rel.source)
        target_key = normalize_name(rel.target)
        if source_key not in canon or target_key not in canon or source_key == target_key:
            continue
        source = canon[source_key]
        target = canon[target_key]
        if rel.kind in {"spouse", "sibling"}:
            signature = (rel.kind, tuple(sorted((source_key, target_key))))
        else:
            signature = (rel.kind, source_key, target_key)
        if signature in seen:
            continue
        seen.add(signature)
        relationships.append(Relation(kind=rel.kind, source=source, target=target))
    return Extraction(people=people, relationships=relationships)


def extract_story(story: str, complete: Completer) -> Extraction:
    text = story.strip()
    if not text:
        raise ExtractionError("Tell a little of the story first.")
    try:
        raw = complete(story_prompt(text))
    except Exception as exc:
        raise ExtractionError(f"The storyteller could not be reached. {exc}") from exc
    try:
        return validate_extraction(parse_json_object(raw))
    except (ExtractionError, JsonPayloadError) as exc:
        raise ExtractionError(
            f"I couldn't read that story ({exc}). "
            "Try one relationship at a time: who was whose parent, spouse, or sibling."
        ) from exc
