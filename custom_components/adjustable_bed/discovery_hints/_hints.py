"""Discovery hint records shared by every family module."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from itertools import product
from typing import NamedTuple

# One entry of the manifest's ``bluetooth`` list.
type Matcher = dict[str, str | int | bool | list[int]]

# Home Assistant indexes local names by their first three characters, which
# therefore must be literal (homeassistant.components.bluetooth.match).
_LITERAL_PREFIX_LENGTH = 3


class Advertisement(NamedTuple):
    """The advertisement fields hints match, normalized once."""

    name: str
    service_uuids: frozenset[str]
    manufacturer_data: Mapping[int, bytes]


def _bed_types(bed_types: Iterable[str]) -> frozenset[str]:
    if isinstance(bed_types, str) or not bed_types:
        raise TypeError("bed_types is a non-empty collection of bed types")
    return frozenset(bed_types)


def _connectable(matcher: Matcher, connectable: bool | None) -> Matcher:
    if connectable is not None:
        matcher["connectable"] = connectable
    return matcher


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceHint:
    """An advertised service UUID."""

    uuid: str
    bed_types: frozenset[str]
    connectable: bool | None = None

    def __post_init__(self) -> None:
        if self.uuid != self.uuid.lower():
            raise ValueError(f"service UUID hints are lowercase: {self.uuid}")

    def matchers(self) -> tuple[Matcher, ...]:
        return (_connectable({"service_uuid": self.uuid}, self.connectable),)

    def matches(self, advertisement: Advertisement) -> bool:
        return self.uuid in advertisement.service_uuids


@dataclass(frozen=True, slots=True, kw_only=True)
class ManufacturerHint:
    """A manufacturer data record, optionally with a payload prefix."""

    company_id: int
    bed_types: frozenset[str]
    data_start: bytes = b""

    def matchers(self) -> tuple[Matcher, ...]:
        matcher: Matcher = {"manufacturer_id": self.company_id}
        if self.data_start:
            matcher["manufacturer_data_start"] = list(self.data_start)
        return (matcher,)

    def matches(self, advertisement: Advertisement) -> bool:
        payload = advertisement.manufacturer_data.get(self.company_id)
        return payload is not None and payload.startswith(self.data_start)


class Case(Enum):
    """How Home Assistant's case-sensitive name matcher must spell a pattern."""

    EXACT = "exact"  # only as declared
    FOLD = "fold"  # as declared and in lowercase
    ANY = "any"  # every upper/lower combination of its letters


def _spellings(pattern: str, case: Case) -> tuple[str, ...]:
    if case is Case.EXACT:
        return (pattern,)
    if case is Case.FOLD:
        return tuple(dict.fromkeys((pattern, pattern.lower())))
    options = [(c.lower(), c.upper()) if c.isalpha() else (c,) for c in pattern]
    return tuple("".join(chars) for chars in product(*options))


@dataclass(frozen=True, slots=True, kw_only=True)
class NameHint:
    """Advertised local names, matched as Home Assistant's gate matches them.

    Each pattern is a glob without its trailing ``*``. ``case`` lists the
    spellings the case-sensitive gate needs. ``anywhere`` records that
    detection also accepts a pattern after the start of the name, which the
    prefix-indexed gate cannot express.
    """

    patterns: tuple[str, ...]
    bed_types: frozenset[str]
    case: Case = Case.EXACT
    anywhere: bool = False
    connectable: bool | None = None
    _regex: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if any(char in pattern for pattern in self.patterns for char in "?["):
            raise ValueError(f"name hints use only the * wildcard: {self.patterns}")
        for glob in self.globs:
            literal = glob[:_LITERAL_PREFIX_LENGTH]
            if len(glob) <= _LITERAL_PREFIX_LENGTH or "*" in literal or "[" in literal:
                raise ValueError(
                    f"name hints need a {_LITERAL_PREFIX_LENGTH}-character literal prefix: {glob}"
                )
        # A glob ends in "*", so it matches any name that starts with a match.
        regex = "|".join(".*".join(map(re.escape, glob[:-1].split("*"))) for glob in self.globs)
        object.__setattr__(self, "_regex", re.compile(regex, re.DOTALL))

    @property
    def globs(self) -> tuple[str, ...]:
        """The manifest ``local_name`` globs, every spelling of every pattern."""
        return tuple(
            dict.fromkeys(
                spelling + "*"
                for pattern in self.patterns
                for spelling in _spellings(pattern, self.case)
            )
        )

    def matchers(self) -> tuple[Matcher, ...]:
        return tuple(_connectable({"local_name": glob}, self.connectable) for glob in self.globs)

    def matches(self, advertisement: Advertisement) -> bool:
        return self.matches_name(advertisement.name)

    def matches_name(self, name: str) -> bool:
        found = self._regex.search(name) if self.anywhere else self._regex.match(name)
        return found is not None


type Hint = ServiceHint | ManufacturerHint | NameHint


def services(
    *uuids: str, bed_types: Iterable[str], connectable: bool | None = None
) -> tuple[ServiceHint, ...]:
    """One hint per service UUID, all leading to the same bed types."""
    return tuple(
        ServiceHint(uuid=uuid.lower(), bed_types=_bed_types(bed_types), connectable=connectable)
        for uuid in uuids
    )


def names(
    *patterns: str,
    bed_types: Iterable[str],
    case: Case = Case.EXACT,
    anywhere: bool = False,
    connectable: bool | None = None,
) -> NameHint:
    """A name hint over one or more patterns that share their bed types and case."""
    return NameHint(
        patterns=patterns,
        bed_types=_bed_types(bed_types),
        case=case,
        anywhere=anywhere,
        connectable=connectable,
    )


def manufacturer(
    company_id: int, *, bed_types: Iterable[str], data_start: bytes = b""
) -> ManufacturerHint:
    """A manufacturer data hint."""
    return ManufacturerHint(
        company_id=company_id, bed_types=_bed_types(bed_types), data_start=data_start
    )
