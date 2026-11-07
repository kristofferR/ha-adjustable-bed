"""The one loader for gzipped JSON app catalogs.

A catalog reads its file with ``load`` and builds typed records from the returned
``Node``. Every accessor checks the declared type and raises ``CatalogError``
naming the path, so malformed data fails loudly instead of reaching a controller.
See "App catalogs" in ``docs/design/protocol-codecs.md``.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

type JsonValue = str | int | bool | None | list[JsonValue] | dict[str, JsonValue]


class CatalogError(ValueError):
    """A packaged catalog does not have its declared shape."""


@dataclass(frozen=True, slots=True)
class Node:
    """One JSON value and where it sits in its catalog."""

    value: object
    path: str

    def fail(self, expected: str) -> NoReturn:
        """Raise ``CatalogError`` for this value."""
        raise CatalogError(f"{self.path}: expected {expected}, got {self.value!r:.80}")

    def integer(self) -> int:
        if type(self.value) is int:
            return self.value
        self.fail("an integer")

    def text(self) -> str:
        if isinstance(self.value, str):
            return self.value
        self.fail("a string")

    def flag(self) -> bool:
        if isinstance(self.value, bool):
            return self.value
        self.fail("a boolean")

    def optional_text(self) -> str | None:
        return None if self.value is None else self.text()

    def items(self) -> tuple[Node, ...]:
        """A list's elements."""
        if isinstance(self.value, list):
            return tuple(Node(item, f"{self.path}[{i}]") for i, item in enumerate(self.value))
        self.fail("a list")

    def row(self, width: int) -> tuple[Node, ...]:
        """A fixed-width row's cells."""
        cells = self.items()
        if len(cells) != width:
            self.fail(f"a row of {width} cells")
        return cells

    def entries(self) -> dict[str, Node]:
        """An object's members."""
        if isinstance(self.value, dict):
            return {str(key): Node(item, f"{self.path}.{key}") for key, item in self.value.items()}
        self.fail("an object")

    def record(self, *keys: str) -> dict[str, Node]:
        """An object with exactly these members."""
        members = self.entries()
        if set(members) != set(keys):
            self.fail(f"an object with members {sorted(keys)}")
        return members

    def json(self) -> JsonValue:
        """A nested value of JSON's types except numbers with a fraction."""
        value = self.value
        if value is None or isinstance(value, str | bool) or type(value) is int:
            return value
        if isinstance(value, list):
            return [item.json() for item in self.items()]
        if isinstance(value, dict):
            return {key: item.json() for key, item in self.entries().items()}
        self.fail("a string, integer, boolean, null, list or object")


def load(directory: str, name: str) -> Node:
    """Read ``<directory>/<name>.json.gz`` next to this module.

    This reads a file, so call it from an executor, never the event loop.
    """
    path = Path(__file__).with_name(directory) / f"{name}.json.gz"
    return Node(json.loads(gzip.decompress(path.read_bytes())), f"{directory}/{name}.json.gz")
