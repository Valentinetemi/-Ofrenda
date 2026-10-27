"""Merging an extraction into a tree that already has people."""

from ofrenda.extract import extract_story
from ofrenda.merge import merge_extraction
from ofrenda.mock_llm import mock_complete
from ofrenda.schemas import Extraction, ExtractedPerson, FamilyTree, Person, Relation

STORY = (
    "my mum is Funke, her dad was Baba Ayo from Ogbomoso, "
    "he had a brother Tunde who moved to Ghana"
)


def test_merge_builds_the_example_and_does_not_duplicate():
    tree = FamilyTree()
    first = merge_extraction(tree, extract_story(STORY, mock_complete))
    assert "Funke" in first.added
    assert "Baba Ayo" in first.added
    assert "Tunde" in first.added
    funke = next(person for person in tree.people if person.name == "Funke")
    ayo = next(person for person in tree.people if person.name == "Baba Ayo")
    tunde = next(person for person in tree.people if person.name == "Tunde")
    me = next(person for person in tree.people if person.name == "Me")
    assert funke.id in me.parent_ids
    assert ayo.id in funke.parent_ids
    assert tunde.id in ayo.sibling_ids
    assert ayo.origin == "Ogbomoso"
    assert tree.narrator_id == me.id

    again = merge_extraction(tree, extract_story(STORY, mock_complete))
    assert again.added == []
    assert len([person for person in tree.people if person.name == "Funke"]) == 1
    assert me.parent_ids.count(funke.id) == 1


def test_second_story_adds_a_spouse_without_cloning():
    tree = FamilyTree()
    merge_extraction(tree, extract_story(STORY, mock_complete))
    result = merge_extraction(tree, extract_story("Tunde had a wife called Ama from Accra", mock_complete))
    assert result.added == ["Ama"]
    tunde = next(person for person in tree.people if person.name == "Tunde")
    ama = next(person for person in tree.people if person.name == "Ama")
    assert ama.id in tunde.spouse_ids
    assert tunde.id in ama.spouse_ids
    assert ama.origin == "Accra"


def test_me_attaches_to_the_existing_narrator():
    tree = FamilyTree(
        narrator_id="seyi",
        people=[Person(id="seyi", name="Seyi Balogun", photo="seyi.png")],
    )
    merge_extraction(
        tree,
        Extraction(
            people=[ExtractedPerson(name="Me"), ExtractedPerson(name="Ada")],
            relationships=[Relation(kind="parent", source="Ada", target="Me")],
        ),
    )
    assert [person.name for person in tree.people] == ["Seyi Balogun", "Ada"]
    seyi = tree.people[0]
    ada = tree.people[1]
    assert ada.id in seyi.parent_ids
    assert seyi.photo == "seyi.png"


def test_parent_cycle_is_refused():
    tree = FamilyTree()
    merge_extraction(
        tree,
        Extraction(
            people=[ExtractedPerson(name="Ayo"), ExtractedPerson(name="Funke")],
            relationships=[Relation(kind="parent", source="Ayo", target="Funke")],
        ),
    )
    merge_extraction(
        tree,
        Extraction(
            people=[ExtractedPerson(name="Ayo"), ExtractedPerson(name="Funke")],
            relationships=[Relation(kind="parent", source="Funke", target="Ayo")],
        ),
    )
    ayo = next(person for person in tree.people if person.name == "Ayo")
    funke = next(person for person in tree.people if person.name == "Funke")
    assert ayo.id in funke.parent_ids
    assert funke.id not in ayo.parent_ids


def test_short_name_lands_on_the_person_already_on_the_altar():
    from pathlib import Path

    tree = FamilyTree.model_validate_json(
        (Path(__file__).resolve().parents[1] / "sample" / "family.json").read_text(encoding="utf-8")
    )
    before = len(tree.people)
    result = merge_extraction(tree, extract_story("Tunde had a wife called Ama from Accra", mock_complete))
    assert result.added == ["Ama"]
    assert len(tree.people) == before + 1
    tunde = next(person for person in tree.people if person.id == "tunde")
    ama = next(person for person in tree.people if person.name == "Ama")
    assert ama.id in tunde.spouse_ids


def test_existing_memory_is_kept_when_the_story_is_thin():
    tree = FamilyTree(people=[Person(id="funke", name="Funke", memories=["She ties her gele."], photo="funke.png")])
    merge_extraction(
        tree,
        Extraction(people=[ExtractedPerson(name="funke", origin="Lagos")], relationships=[]),
    )
    funke = tree.people[0]
    assert funke.memories == ["She ties her gele."]
    assert funke.photo == "funke.png"
    assert funke.origin == "Lagos"
