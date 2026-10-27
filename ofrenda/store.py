"""The family file. One JSON document, written in full under a lock."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from ofrenda.schemas import FamilyTree

T = TypeVar("T")


class Store:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> FamilyTree:
        with self._lock:
            return self._read()

    def save(self, tree: FamilyTree) -> None:
        with self._lock:
            self._write(tree)

    def update(self, fn: Callable[[FamilyTree], T]) -> T:
        """Mutate the tree inside `fn`, then save. If `fn` raises, the file stays."""
        with self._lock:
            tree = self._read()
            result = fn(tree)
            self._write(tree)
            return result

    def _read(self) -> FamilyTree:
        if not self.path.is_file():
            return FamilyTree()
        return FamilyTree.model_validate_json(self.path.read_text(encoding="utf-8"))

    def _write(self, tree: FamilyTree) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(tree.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)
