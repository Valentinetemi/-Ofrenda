"""Missing branches.

The gaps themselves are computed from the tree, so a model having a bad day
cannot forget that someone has no children recorded. Gemma's job, when it is
running, is to turn each gap into a question you could ask out loud.
"""

from __future__ import annotations

from ofrenda.jsonutil import parse_json_object
from ofrenda.names import short_name
from ofrenda.schemas import FamilyTree, Person, Suggestion

# Shown first. The uncle who left is the question the altar is for.
_KIND_ORDER = {
    "missing_branch": 0,
    "missing_spouse": 1,
    "missing_parents": 2,
    "missing_children": 3,
}


def _children(tree: FamilyTree) -> dict[str, list[str]]:
    kids = {person.id: [] for person in tree.people}
    for person in tree.people:
        for parent_id in person.parent_ids:
            if parent_id in kids:
                kids[parent_id].append(person.id)
    return kids


def _sibling_ids(person: Person, tree: FamilyTree, kids: dict[str, list[str]]) -> set[str]:
    found = set(person.sibling_ids)
    for parent_id in person.parent_ids:
        for sibling_id in kids.get(parent_id, []):
            if sibling_id != person.id:
                found.add(sibling_id)
    known = {item.id for item in tree.people}
    return {item for item in found if item in known}


def _remembered(people: list[Person], *, skip: set[str]) -> list[Person]:
    # A one-line bio is not a memory. Ask someone who actually has a story to tell.
    kept = [
        person
        for person in people
        if person.id not in skip and not person.death_year and person.memories
    ]
    kept.sort(key=lambda person: (person.birth_year is None, person.birth_year or 0, person.name))
    return kept


def who_to_ask(tree: FamilyTree, person: Person, kind: str) -> str:
    """A living relative who might know, never the narrator if anyone else will do."""
    by_id = {item.id: item for item in tree.people}
    kids = _children(tree)
    skip = {person.id}
    if tree.narrator_id:
        skip.add(tree.narrator_id)

    def pick(ids: list[str]) -> str | None:
        chosen = _remembered([by_id[item] for item in ids if item in by_id], skip=skip)
        if not chosen:
            return None
        return short_name(chosen[0].name)

    if kind == "missing_parents":
        spouse = pick(person.spouse_ids)
        if spouse:
            return spouse

    child = pick(kids.get(person.id, []))
    if child:
        return child

    grandchildren: list[str] = []
    for child_id in kids.get(person.id, []):
        grandchildren.extend(kids.get(child_id, []))
    grandchild = pick(grandchildren)
    if grandchild:
        return grandchild

    nieces: list[str] = []
    for sibling_id in _sibling_ids(person, tree, kids):
        nieces.extend(kids.get(sibling_id, []))
    niece = pick(nieces)
    if niece:
        return niece

    anyone = pick([item.id for item in tree.people])
    if anyone:
        return anyone
    return "someone who knew them"


def _pronouns(person: Person) -> dict[str, str]:
    spoken = short_name(person.name)
    if person.gender == "female":
        return {"subj": "she", "obj": "her", "poss": "her"}
    if person.gender == "male":
        return {"subj": "he", "obj": "him", "poss": "his"}
    return {"subj": spoken, "obj": spoken, "poss": f"{spoken}'s"}


def question_for(person: Person, kind: str, ask: str) -> str:
    name = person.name
    words = _pronouns(person)
    place = f" in {person.origin}" if person.origin else ""
    if kind == "missing_branch":
        text = (
            f"{name} has no spouse or children recorded. "
            f"Ask {ask} about {words['obj']}: who {words['subj']} built a life with{place}, "
            "and whether there were children."
        )
        if not person.memories:
            text += f" There is no memory of {words['obj']} yet. One story will hold {words['obj']} here."
        return text
    if kind == "missing_spouse":
        return f"Nobody has recorded a spouse for {name}. Ask {ask} who shared {words['poss']} home."
    if kind == "missing_parents":
        return (
            f"{name}'s parents are not on the ofrenda. "
            f"Ask {ask} for their names, and where they were from."
        )
    return (
        f"{name} has no children recorded. "
        f"Ask {ask} whether there were children, and what they were called."
    )


def find_gaps(tree: FamilyTree) -> list[tuple[Person, str]]:
    """Structural holes worth a candle. Leaves and the narrator are left in peace."""
    by_id = {person.id: person for person in tree.people}
    kids = _children(tree)
    gaps: list[tuple[Person, str]] = []
    for person in tree.people:
        if person.id == tree.narrator_id:
            continue
        children = [by_id[item] for item in kids.get(person.id, []) if item in by_id]
        has_spouse = bool(person.spouse_ids)
        has_children = bool(children)
        has_siblings = bool(_sibling_ids(person, tree, kids))
        if not has_spouse and not has_children and has_siblings and not person.memories:
            gaps.append((person, "missing_branch"))
        elif not has_spouse and has_children and person.death_year:
            gaps.append((person, "missing_spouse"))
        elif not person.parent_ids and has_spouse and has_children:
            gaps.append((person, "missing_parents"))
        elif not has_children and has_spouse and person.death_year:
            gaps.append((person, "missing_children"))
    gaps.sort(key=lambda item: (_KIND_ORDER.get(item[1], 9), item[0].birth_year or 9999, item[0].name))
    return gaps


def suggestions_from_tree(tree: FamilyTree) -> list[Suggestion]:
    made: list[Suggestion] = []
    for person, kind in find_gaps(tree):
        ask = who_to_ask(tree, person, kind)
        made.append(
            Suggestion(
                id=f"{person.id}:{kind}",
                person_id=person.id,
                person_name=person.name,
                kind=kind,
                question=question_for(person, kind, ask),
                source="rules",
            )
        )
    return made


def apply_review(baseline: list[Suggestion], payload: dict) -> list[Suggestion]:
    """Keep the gaps the rules found. Replace a question only when it names the same person."""
    by_key = {(item.person_id, item.kind): item for item in baseline}
    incoming = payload.get("suggestions")
    if not isinstance(incoming, list):
        return baseline
    for item in incoming:
        if not isinstance(item, dict):
            continue
        person_id = item.get("person_id")
        kind = item.get("kind")
        question = item.get("question")
        if not isinstance(question, str):
            continue
        question = " ".join(question.split())
        if not question or len(question) > 400:
            continue
        key = (person_id, kind)
        if key not in by_key:
            continue
        by_key[key] = by_key[key].model_copy(update={"question": question, "source": "gemma"})
    return [by_key[(item.person_id, item.kind)] for item in baseline]


def review_prompt(tree: FamilyTree, baseline: list[Suggestion]) -> str:
    lines = ["Family on the altar:"]
    by_id = {person.id: person for person in tree.people}
    for person in tree.people:
        parents = ", ".join(by_id[item].name for item in person.parent_ids if item in by_id) or "unknown"
        spouses = ", ".join(by_id[item].name for item in person.spouse_ids if item in by_id) or "none recorded"
        lines.append(
            f"- {person.name} (id {person.id}), origin {person.origin or 'unknown'}, "
            f"parents: {parents}, spouse: {spouses}, memories: {len(person.memories)}"
        )
    lines.append("")
    lines.append("Gaps already found. Rewrite each question so a younger relative could ask it.")
    lines.append("Do not invent people. Do not add gaps. Do not drop facts such as a place name.")
    lines.append('Reply with JSON only: {"suggestions":[{"person_id":"","kind":"","question":""}]}')
    for item in baseline:
        lines.append(f"- person_id {item.person_id}, kind {item.kind}: {item.question}")
    return "\n".join(lines)


def review_with_model(tree: FamilyTree, complete) -> list[Suggestion]:
    """Ask the model to rephrase. Any failure leaves the original questions in place."""
    baseline = suggestions_from_tree(tree)
    if not baseline:
        return baseline
    try:
        raw = complete(review_prompt(tree, baseline))
        payload = parse_json_object(raw)
    except Exception:
        return baseline
    return apply_review(baseline, payload)
