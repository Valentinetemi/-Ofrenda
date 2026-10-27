"""Fold an extraction into the tree without cloning people who are already there."""

from __future__ import annotations

from dataclasses import dataclass, field

from ofrenda.names import normalize_name, slugify
from ofrenda.schemas import Extraction, FamilyTree, Person


@dataclass
class MergeResult:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)


def _by_id(tree: FamilyTree) -> dict[str, Person]:
    return {person.id: person for person in tree.people}


def _unique_id(tree: FamilyTree, name: str) -> str:
    base = slugify(name)
    taken = {person.id for person in tree.people}
    if base not in taken:
        return base
    number = 2
    while f"{base}-{number}" in taken:
        number += 1
    return f"{base}-{number}"


def _ancestors(tree: FamilyTree, person_id: str) -> set[str]:
    found: set[str] = set()
    stack = [person_id]
    by_id = _by_id(tree)
    while stack:
        current = stack.pop()
        person = by_id.get(current)
        if person is None:
            continue
        for parent_id in person.parent_ids:
            if parent_id in found or parent_id not in by_id:
                continue
            found.add(parent_id)
            stack.append(parent_id)
    return found


def link_parent(tree: FamilyTree, parent_id: str, child_id: str) -> bool:
    """Record parent -> child. Refuse a link that would cycle the tree."""
    if parent_id == child_id:
        return False
    by_id = _by_id(tree)
    child = by_id.get(child_id)
    parent = by_id.get(parent_id)
    if child is None or parent is None:
        return False
    if parent_id in child.parent_ids:
        return False
    # Adding the link would cycle if the child is already an ancestor of the parent.
    if child_id in _ancestors(tree, parent_id):
        return False
    child.parent_ids.append(parent_id)
    return True


def link_spouse(tree: FamilyTree, left_id: str, right_id: str) -> bool:
    if left_id == right_id:
        return False
    by_id = _by_id(tree)
    left = by_id.get(left_id)
    right = by_id.get(right_id)
    if left is None or right is None:
        return False
    changed = False
    if right_id not in left.spouse_ids:
        left.spouse_ids.append(right_id)
        changed = True
    if left_id not in right.spouse_ids:
        right.spouse_ids.append(left_id)
        changed = True
    return changed


def link_sibling(tree: FamilyTree, left_id: str, right_id: str) -> bool:
    if left_id == right_id:
        return False
    by_id = _by_id(tree)
    left = by_id.get(left_id)
    right = by_id.get(right_id)
    if left is None or right is None:
        return False
    changed = False
    if right_id not in left.sibling_ids:
        left.sibling_ids.append(right_id)
        changed = True
    if left_id not in right.sibling_ids:
        right.sibling_ids.append(left_id)
        changed = True
    return changed


def unlink(tree: FamilyTree, kind: str, left_id: str, right_id: str) -> bool:
    by_id = _by_id(tree)
    left = by_id.get(left_id)
    right = by_id.get(right_id)
    if left is None or right is None:
        return False
    changed = False
    if kind == "parent":
        if left_id in right.parent_ids:
            right.parent_ids.remove(left_id)
            changed = True
    elif kind == "child":
        if right_id in left.parent_ids:
            left.parent_ids.remove(right_id)
            changed = True
    elif kind == "spouse":
        if right_id in left.spouse_ids:
            left.spouse_ids.remove(right_id)
            changed = True
        if left_id in right.spouse_ids:
            right.spouse_ids.remove(left_id)
            changed = True
    elif kind == "sibling":
        if right_id in left.sibling_ids:
            left.sibling_ids.remove(right_id)
            changed = True
        if left_id in right.sibling_ids:
            right.sibling_ids.remove(left_id)
            changed = True
    return changed


def remove_person(tree: FamilyTree, person_id: str) -> Person | None:
    person = next((item for item in tree.people if item.id == person_id), None)
    if person is None:
        return None
    for other in tree.people:
        other.parent_ids = [item for item in other.parent_ids if item != person_id]
        other.spouse_ids = [item for item in other.spouse_ids if item != person_id]
        other.sibling_ids = [item for item in other.sibling_ids if item != person_id]
    tree.people = [item for item in tree.people if item.id != person_id]
    if tree.narrator_id == person_id:
        tree.narrator_id = None
    return person


def _index(tree: FamilyTree) -> dict[str, Person]:
    return {normalize_name(person.name): person for person in tree.people}


def _match_existing(tree: FamilyTree, name: str) -> Person | None:
    """Exact name, or a unique leading-token prefix.

    'Tunde' is the Tunde Adeyemi already on the altar. 'Mama' is not guessed,
    because both Mama Ireti and Mama Folake would fit.
    """
    key = normalize_name(name)
    if not key:
        return None
    exact = [person for person in tree.people if normalize_name(person.name) == key]
    if exact:
        return exact[0]
    spoken = key.split()
    if key == "me" or not spoken:
        return None
    prefixes = []
    for person in tree.people:
        tokens = normalize_name(person.name).split()
        if len(spoken) < len(tokens) and tokens[: len(spoken)] == spoken:
            prefixes.append(person)
    if len(prefixes) == 1:
        return prefixes[0]
    return None


def _ensure(tree: FamilyTree, index: dict[str, Person], name: str, added: list[str]) -> Person:
    key = normalize_name(name)
    if key == "me" and tree.narrator_id:
        narrator = next((person for person in tree.people if person.id == tree.narrator_id), None)
        if narrator is not None:
            return narrator
    existing = _match_existing(tree, name)
    if existing is not None:
        index[key] = existing
        return existing
    person = Person(id=_unique_id(tree, name), name=name if name != "Me" else "Me")
    if key == "me":
        tree.narrator_id = person.id
    tree.people.append(person)
    index[key] = person
    added.append(person.name)
    return person


def _fill(person: Person, extracted_origin, extracted_notes, extracted_years, extracted_gender, memories) -> bool:
    changed = False
    if extracted_origin and not person.origin:
        person.origin = extracted_origin
        changed = True
    if extracted_gender and not person.gender:
        person.gender = extracted_gender
        changed = True
    birth, death = extracted_years
    if birth and not person.birth_year:
        person.birth_year = birth
        changed = True
    if death and not person.death_year:
        person.death_year = death
        changed = True
    already_written = f"{person.bio}\n" + "\n".join(person.memories)
    if (
        extracted_notes
        and extracted_notes.casefold() not in already_written.casefold()
    ):
        if not person.bio:
            person.bio = extracted_notes
        else:
            person.memories.append(extracted_notes)
        changed = True
    for memory in memories:
        if memory and memory not in person.memories:
            person.memories.append(memory)
            changed = True
    return changed


def merge_extraction(tree: FamilyTree, extraction: Extraction) -> MergeResult:
    """Mutates `tree`. Existing people keep their photos, memories, and edits."""
    index = _index(tree)
    added: list[str] = []
    updated_ids: list[str] = []

    def mark(person: Person, before: dict) -> None:
        if person.model_dump() != before and person.id not in updated_ids and person.name not in added:
            updated_ids.append(person.id)

    for extracted in extraction.people:
        person = _ensure(tree, index, extracted.name, added)
        before = person.model_dump()
        _fill(
            person,
            extracted.origin,
            extracted.notes,
            (extracted.birth_year, extracted.death_year),
            extracted.gender,
            extracted.memories,
        )
        mark(person, before)

    for relation in extraction.relationships:
        source = _ensure(tree, index, relation.source, added)
        target = _ensure(tree, index, relation.target, added)
        before_source = source.model_dump()
        before_target = target.model_dump()
        if relation.kind == "parent":
            link_parent(tree, source.id, target.id)
        elif relation.kind == "spouse":
            link_spouse(tree, source.id, target.id)
        elif relation.kind == "sibling":
            link_sibling(tree, source.id, target.id)
        mark(source, before_source)
        mark(target, before_target)

    names = {person.id: person.name for person in tree.people}
    return MergeResult(added=added, updated=[names[person_id] for person_id in updated_ids])


def describe_merge(result: MergeResult) -> str:
    if not result.added and not result.updated:
        return "Everyone in that story is already on the altar."
    parts: list[str] = []
    if result.added:
        parts.append("Set on the altar: " + _join(result.added) + ".")
    if result.updated:
        parts.append("Brought up to date: " + _join(result.updated) + ".")
    return " ".join(parts)


def _join(names: list[str]) -> str:
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    if len(unique) == 1:
        return unique[0]
    if len(unique) == 2:
        return f"{unique[0]} and {unique[1]}"
    return ", ".join(unique[:-1]) + f", and {unique[-1]}"
