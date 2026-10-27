"""A small stand-in for Gemma.

Tests and `OFRENDA_MOCK_LLM=1` use this so the altar can be tried with no
Ollama install. It only understands a handful of family-sentence shapes.
Gemma is the storyteller when the app is run for real.
"""

from __future__ import annotations

import json
import re

from ofrenda.names import display_name, normalize_name

_WORD = r"[A-Za-z][\w'’-]*"
_NAME = rf"({_WORD}(?:\s+(?!from\b|who\b|moved\b|and\b|with\b){_WORD}){{0,3}})"
_PLACE = rf"({_WORD}(?:\s+{_WORD}){{0,2}})"

_FEMALE = {"mum", "mom", "mother", "mama", "sister", "daughter", "wife", "aunty", "aunt"}
_MALE = {"dad", "father", "papa", "baba", "brother", "son", "husband", "uncle"}
_PARENT = {"mum", "mom", "mother", "mama", "dad", "father", "papa", "baba"}
_SIBLING = {"brother", "sister"}
_SPOUSE = {"wife", "husband"}
_CHILD = {"son", "daughter"}

_REJECT = {
    "from",
    "who",
    "and",
    "the",
    "had",
    "has",
    "was",
    "is",
    "a",
    "an",
    "he",
    "she",
    "they",
    "her",
    "his",
    "their",
    "my",
    "with",
    "moved",
    "to",
    "called",
    "named",
    "brother",
    "sister",
    "wife",
    "husband",
    "son",
    "daughter",
}

_MY = re.compile(
    rf"\bmy\s+(mum|mom|mother|mama|dad|father|papa|brother|sister|wife|husband|son|daughter|uncle|aunty|aunt)\s+"
    rf"(?:is|was|named|called)\s+{_NAME}(?:\s+from\s+{_PLACE})?(?:\s+who\s+moved\s+to\s+{_PLACE})?",
    re.IGNORECASE,
)
_THEIR = re.compile(
    rf"\b(her|his|their)\s+(mum|mom|mother|mama|dad|father|papa|baba|brother|sister|wife|husband|son|daughter|uncle|aunty|aunt)\s+"
    rf"(?:is|was|named|called)\s+{_NAME}(?:\s+from\s+{_PLACE})?(?:\s+who\s+moved\s+to\s+{_PLACE})?",
    re.IGNORECASE,
)
_PRONOUN_HAD = re.compile(
    rf"\b(he|she|they)\s+had\s+(?:a|an)\s+(brother|sister|wife|husband|son|daughter)\s+"
    rf"(?:called\s+|named\s+)?{_NAME}(?:\s+from\s+{_PLACE})?(?:\s+who\s+moved\s+to\s+{_PLACE})?",
    re.IGNORECASE,
)
_NAMED_HAD = re.compile(
    rf"\b{_NAME}\s+had\s+(?:a|an)\s+(brother|sister|wife|husband|son|daughter)\s+"
    rf"(?:called\s+|named\s+)?{_NAME}(?:\s+from\s+{_PLACE})?(?:\s+who\s+moved\s+to\s+{_PLACE})?",
    re.IGNORECASE,
)


def _place(value: str | None) -> str | None:
    if not value:
        return None
    words: list[str] = []
    for word in value.split():
        if word.casefold() in {"who", "and", "he", "she", "they", "had", "with", "where"}:
            break
        words.append(display_name(word) if word.islower() else word)
        if len(words) == 3:
            break
    return " ".join(words) or None


def _good_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = display_name(name.strip(" .,"))
    if not cleaned or normalize_name(cleaned) in _REJECT:
        return None
    return cleaned


class _Draft:
    def __init__(self) -> None:
        self.people: dict[str, dict] = {}
        self.rels: list[dict] = []
        self.last: str | None = None
        self.female: str | None = None
        self.male: str | None = None

    def add_person(
        self,
        name: str | None,
        *,
        origin: str | None = None,
        notes: str | None = None,
        gender: str | None = None,
    ) -> str | None:
        pretty = _good_name(name)
        if not pretty:
            return None
        key = normalize_name(pretty)
        record = self.people.get(key)
        if record is None:
            record = {
                "name": pretty,
                "origin": None,
                "notes": None,
                "birth_year": None,
                "death_year": None,
                "gender": None,
                "memories": [],
            }
            self.people[key] = record
        if origin and not record["origin"]:
            record["origin"] = origin
        if notes and not record["notes"]:
            record["notes"] = notes
        if gender and not record["gender"]:
            record["gender"] = gender
        self.last = record["name"]
        if gender == "female":
            self.female = record["name"]
        elif gender == "male":
            self.male = record["name"]
        return record["name"]

    def add_rel(self, kind: str, source: str | None, target: str | None) -> None:
        if not source or not target or normalize_name(source) == normalize_name(target):
            return
        self.rels.append({"kind": kind, "source": source, "target": target})

    def payload(self) -> dict:
        return {"people": list(self.people.values()), "relationships": self.rels}


def _gender_for(role: str) -> str | None:
    if role in _FEMALE:
        return "female"
    if role in _MALE:
        return "male"
    return None


def _link_role(draft: _Draft, role: str, owner: str | None, name: str | None) -> None:
    if not owner or not name:
        return
    if role in _PARENT:
        draft.add_rel("parent", name, owner)
    elif role in _SIBLING:
        draft.add_rel("sibling", owner, name)
    elif role in _SPOUSE:
        draft.add_rel("spouse", owner, name)
    elif role in _CHILD:
        draft.add_rel("parent", owner, name)


def _origin_and_notes(from_place: str | None, moved_place: str | None) -> tuple[str | None, str | None]:
    origin = _place(from_place) or _place(moved_place)
    notes = f"moved to {origin}" if moved_place and origin else None
    return origin, notes


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(not (end <= left or start >= right) for left, right in taken)


def parse_story(story: str) -> dict:
    """Read a few plain family sentences. Unknown wording yields no people."""
    draft = _Draft()
    if re.search(r"\b(my|i)\b", story, re.IGNORECASE):
        draft.add_person("Me")

    taken: list[tuple[int, int]] = []
    matches: list[tuple] = []
    # Lower priority wins a tie, so "he had a brother" stays a pronoun
    # and is not read as a person named He.
    for priority, kind, pattern in (
        (0, "my", _MY),
        (0, "their", _THEIR),
        (0, "pronoun_had", _PRONOUN_HAD),
        (1, "named_had", _NAMED_HAD),
    ):
        for match in pattern.finditer(story):
            matches.append((match.start(), -(match.end() - match.start()), priority, kind, match))
    matches.sort()

    for _start, _length, _priority, kind, match in matches:
        span = (match.start(), match.end())
        if _overlaps(span, taken):
            continue
        if kind == "my":
            role, name, from_place, moved = match.group(1, 2, 3, 4)
            origin, notes = _origin_and_notes(from_place, moved)
            person = draft.add_person(name, origin=origin, notes=notes, gender=_gender_for(role.lower()))
            _link_role(draft, role.lower(), "Me", person)
        elif kind == "their":
            pronoun, role, name, from_place, moved = match.group(1, 2, 3, 4, 5)
            owner = {"her": draft.female, "his": draft.male, "their": draft.last}[pronoun.lower()]
            origin, notes = _origin_and_notes(from_place, moved)
            person = draft.add_person(name, origin=origin, notes=notes, gender=_gender_for(role.lower()))
            _link_role(draft, role.lower(), owner, person)
        elif kind == "pronoun_had":
            pronoun, role, name, from_place, moved = match.group(1, 2, 3, 4, 5)
            owner = {"he": draft.male, "she": draft.female, "they": draft.last}[pronoun.lower()]
            origin, notes = _origin_and_notes(from_place, moved)
            person = draft.add_person(name, origin=origin, notes=notes, gender=_gender_for(role.lower()))
            _link_role(draft, role.lower(), owner, person)
        else:
            owner_name, role, name, from_place, moved = match.group(1, 2, 3, 4, 5)
            owner = draft.add_person(owner_name)
            origin, notes = _origin_and_notes(from_place, moved)
            person = draft.add_person(name, origin=origin, notes=notes, gender=_gender_for(role.lower()))
            _link_role(draft, role.lower(), owner, person)
        if kind != "named_had" or _good_name(match.group(1)):
            taken.append(span)
    return draft.payload()


def story_from_prompt(prompt: str) -> str:
    match = re.search(r'"""\n(.*?)\n"""', prompt, re.DOTALL)
    if match:
        return match.group(1)
    return prompt


def mock_complete(prompt: str) -> str:
    """Completer shaped like the Ollama client: prompt in, JSON string out."""
    return json.dumps(parse_story(story_from_prompt(prompt)))
