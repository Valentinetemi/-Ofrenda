"""Missing-branch questions, including Gemma's rewrite being checked before use."""

import json
from pathlib import Path

from ofrenda.schemas import FamilyTree
from ofrenda.suggest import apply_review, find_gaps, suggestions_from_tree

ROOT = Path(__file__).resolve().parents[1]


def sample_tree() -> FamilyTree:
    return FamilyTree.model_validate_json((ROOT / "sample" / "family.json").read_text(encoding="utf-8"))


def test_sample_altar_lights_the_thin_branches():
    tree = sample_tree()
    gaps = [(person.id, kind) for person, kind in find_gaps(tree)]
    assert ("tunde", "missing_branch") in gaps
    assert ("ireti", "missing_spouse") in gaps
    assert ("kola", "missing_parents") in gaps
    assert ("folake", "missing_parents") in gaps
    assert all(person_id != "seyi" for person_id, _kind in gaps)
    assert all(person_id != "bisi" for person_id, _kind in gaps)

    suggestions = suggestions_from_tree(tree)
    tunde = next(item for item in suggestions if item.person_id == "tunde")
    assert "no spouse or children" in tunde.question
    assert "Accra" in tunde.question
    assert "Funke" in tunde.question
    assert "no memory of him" in tunde.question
    ireti = next(item for item in suggestions if item.person_id == "ireti")
    assert "spouse" in ireti.question
    assert "Funke" in ireti.question
    kola = next(item for item in suggestions if item.person_id == "kola")
    assert "parents" in kola.question
    assert "Funke" in kola.question


def test_review_keeps_gaps_and_drops_invented_people():
    baseline = suggestions_from_tree(sample_tree())
    payload = json.loads(
        """
        {
          "suggestions": [
            {"person_id": "tunde", "kind": "missing_branch", "question": "Ask Funke who Tunde lived with in Accra."},
            {"person_id": "ghost", "kind": "missing_branch", "question": "This person was invented."},
            {"person_id": "kola", "kind": "missing_spouse", "question": "Wrong kind of gap."},
            {"person_id": "ireti", "kind": "missing_spouse", "question": "   "}
          ]
        }
        """
    )
    reviewed = apply_review(baseline, payload)
    assert [item.person_id for item in reviewed] == [item.person_id for item in baseline]
    tunde = next(item for item in reviewed if item.person_id == "tunde")
    assert tunde.question == "Ask Funke who Tunde lived with in Accra."
    assert tunde.source == "gemma"
    ireti = next(item for item in reviewed if item.person_id == "ireti")
    assert ireti.source == "rules"
    assert "invented" not in " ".join(item.question for item in reviewed)
    assert all(item.person_id != "ghost" for item in reviewed)
