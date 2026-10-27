"""Extraction: validation, retries, dedupe, and the mock storyteller."""

import json

import pytest

from ofrenda.extract import ExtractionError, extract_story, validate_extraction
from ofrenda.jsonutil import parse_json_object
from ofrenda.mock_llm import mock_complete, parse_story
from ofrenda.names import normalize_name

STORY = (
    "my mum is Funke, her dad was Baba Ayo from Ogbomoso, "
    "he had a brother Tunde who moved to Ghana"
)


def _funke_payload():
    return {
        "people": [
            {"name": "Funke", "origin": None, "notes": None, "birth_year": None, "death_year": None, "memories": []},
            {"name": "Me", "origin": None, "notes": None, "birth_year": None, "death_year": None, "memories": []},
        ],
        "relationships": [{"kind": "parent", "source": "Funke", "target": "Me"}],
    }


def test_fenced_json_and_trailing_comma():
    raw = '```json\n{"people": [{"name": "Funke",}], "relationships": []}\n```'
    data = parse_json_object(raw)
    extraction = validate_extraction(data)
    assert [person.name for person in extraction.people] == ["Funke"]


def test_child_kind_is_flipped_into_parent():
    extraction = validate_extraction(
        {
            "people": [{"name": "Funke"}, {"name": "Seyi"}],
            "relationships": [{"kind": "daughter", "source": "Seyi", "target": "Funke"}],
        }
    )
    assert extraction.relationships[0].kind == "parent"
    assert extraction.relationships[0].source == "Seyi" or extraction.relationships[0].source == "Funke"
    rel = extraction.relationships[0]
    assert (rel.source, rel.target) == ("Funke", "Seyi")


def test_unknown_relation_endpoint_is_dropped():
    extraction = validate_extraction(
        {
            "people": [{"name": "Funke"}],
            "relationships": [{"kind": "parent", "source": "Funke", "target": "Nobody"}],
        }
    )
    assert extraction.people[0].name == "Funke"
    assert extraction.relationships == []


def test_impossible_year_is_dropped_not_fatal():
    extraction = validate_extraction(
        {"people": [{"name": "Ayo", "birth_year": "nineteen", "death_year": 1400}], "relationships": []}
    )
    assert extraction.people[0].birth_year is None
    assert extraction.people[0].death_year is None


def test_dedupe_same_name_keeps_origin():
    extraction = validate_extraction(
        {
            "people": [
                {"name": "Funke", "origin": None, "memories": ["She hums."]},
                {"name": "funke", "origin": "Lagos", "memories": ["She hums.", "She calls on Sundays."]},
            ],
            "relationships": [],
        }
    )
    assert len(extraction.people) == 1
    person = extraction.people[0]
    assert normalize_name(person.name) == "funke"
    assert person.origin == "Lagos"
    assert person.memories == ["She hums.", "She calls on Sundays."]


def test_retries_then_accepts():
    prompts = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return "I think your mum is Funke, honestly."
        return json.dumps(_funke_payload())

    extraction = extract_story("my mum is Funke", complete)
    assert len(prompts) == 2
    assert "not usable" in prompts[1]
    assert any(person.name == "Funke" for person in extraction.people)


def test_gives_up_after_three_bad_replies():
    def complete(prompt: str) -> str:
        return "still not json"

    with pytest.raises(ExtractionError):
        extract_story("my mum is Funke", complete, attempts=3)


def test_mock_parses_the_ogbomoso_story():
    payload = parse_story(STORY)
    names = {person["name"] for person in payload["people"]}
    assert {"Funke", "Baba Ayo", "Tunde", "Me"} <= names
    rels = {(item["kind"], item["source"], item["target"]) for item in payload["relationships"]}
    assert ("parent", "Funke", "Me") in rels
    assert ("parent", "Baba Ayo", "Funke") in rels
    assert ("sibling", "Baba Ayo", "Tunde") in rels or ("sibling", "Tunde", "Baba Ayo") in rels
    ayo = next(person for person in payload["people"] if person["name"] == "Baba Ayo")
    tunde = next(person for person in payload["people"] if person["name"] == "Tunde")
    assert ayo["origin"] == "Ogbomoso"
    assert ayo["gender"] == "male"
    assert tunde["origin"] == "Ghana"
    assert "Ghana" in (tunde["notes"] or "")


def test_mock_wife_sentence_and_full_extract():
    extraction = extract_story("Tunde had a wife called Ama from Accra", mock_complete)
    names = {person.name for person in extraction.people}
    assert "Tunde" in names and "Ama" in names
    ama = next(person for person in extraction.people if person.name == "Ama")
    assert ama.origin == "Accra"
    assert ama.gender == "female"
    assert any(rel.kind == "spouse" and {rel.source, rel.target} == {"Tunde", "Ama"} for rel in extraction.relationships)
