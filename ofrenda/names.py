"""Name matching. 'Funke' and 'funke' are one person. 'Baba Ayo' is not 'Ayo'."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s'-]", re.UNICODE)

# Titles that are part of how a family says the name, so they stay in the short form.
_TITLES = {"mama", "baba", "pa", "ma", "chief", "alhaji", "alhaja", "madam", "daddy", "mummy"}


def normalize_name(name: str) -> str:
    cleaned = _PUNCT.sub("", name.casefold())
    return _SPACE.sub(" ", cleaned).strip()


def display_name(name: str) -> str:
    parts = _SPACE.sub(" ", name).strip().split(" ")
    pretty: list[str] = []
    for word in parts:
        pretty.append(word.capitalize() if word.islower() else word)
    return " ".join(pretty)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_name(name)).strip("-")
    return slug or "person"


def short_name(name: str) -> str:
    """The way you would say them across a table. 'Mama Ireti Adeyemi' -> 'Mama Ireti'."""
    parts = name.split()
    if not parts:
        return name
    if parts[0].casefold() in _TITLES and len(parts) > 1:
        return " ".join(parts[:2])
    return parts[0]
