"""Non-destructive migration planning for accepted analysis v1.12 reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn

from .model import IRDiagnostic, IRValidationError

MIGRATION_REVISION = "phase4-analysis-v1.12-to-ir-v1"
SOURCE_SCHEMA_REVISION = "phase4-analysis-v1.12-2026-07-26"
_MAX_BYTES = 64 * 1024**2
_MAX_DEPTH = 128
_MAX_NODES = 2_000_000
_MAX_MAPPINGS = 500_000


class MigrationDomain(StrEnum):
    """Closed destination domains for one legacy semantic leaf."""

    ACTION = "ACTION"
    AUTHENTICATION = "AUTHENTICATION"
    CONFIGURATION = "CONFIGURATION"
    DISCOVERY = "DISCOVERY"
    GATT = "GATT"
    LIFECYCLE = "LIFECYCLE"
    LIMITATION = "LIMITATION"
    METADATA = "METADATA"
    PACKET = "PACKET"
    PARSER = "PARSER"
    PROVENANCE = "PROVENANCE"
    SELECTOR = "SELECTOR"
    STATE = "STATE"
    TEST_VECTOR = "TEST_VECTOR"
    TIMING_RELEASE = "TIMING_RELEASE"
    TOOL_COVERAGE = "TOOL_COVERAGE"
    TRANSPORT = "TRANSPORT"
    VARIANT = "VARIANT"


class MigrationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True, order=True)
class MigratedClaim:
    """One exact source leaf assigned to a normalized destination domain."""

    source_pointer: str
    target_domain: MigrationDomain
    value_sha256: str

    def __post_init__(self) -> None:
        _pointer(self.source_pointer)
        if type(self.target_domain) is not MigrationDomain:
            raise ValueError("migration target must be a MigrationDomain")
        if len(self.value_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.value_sha256
        ):
            raise ValueError("migration value digest must be a lowercase SHA-256")

    def to_data(self) -> dict[str, str]:
        return {
            "source_pointer": self.source_pointer,
            "target_domain": self.target_domain.value,
            "value_sha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True)
class V112MigrationPlan:
    """Content-bound migration inventory; it never rewrites the source report."""

    source_sha256: str
    mapped_claims: tuple[MigratedClaim, ...]
    unmodeled_paths: tuple[str, ...]
    revision: str = MIGRATION_REVISION
    source_schema_revision: str = SOURCE_SCHEMA_REVISION

    def __post_init__(self) -> None:
        if self.revision != MIGRATION_REVISION:
            raise ValueError("unsupported migration revision")
        if self.source_schema_revision != SOURCE_SCHEMA_REVISION:
            raise ValueError("unsupported source schema revision")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("migration source digest must be a lowercase SHA-256")
        if type(self.mapped_claims) is not tuple or any(
            type(item) is not MigratedClaim for item in self.mapped_claims
        ):
            raise ValueError("mapped claims must be an exact tuple of MigratedClaim")
        if tuple(sorted(self.mapped_claims)) != self.mapped_claims:
            raise ValueError("mapped claims must be sorted")
        if len({item.source_pointer for item in self.mapped_claims}) != len(self.mapped_claims):
            raise ValueError("mapped source pointers must be unique")
        if type(self.unmodeled_paths) is not tuple or any(
            type(item) is not str for item in self.unmodeled_paths
        ):
            raise ValueError("unmodeled paths must be an exact tuple of strings")
        for pointer in self.unmodeled_paths:
            _pointer(pointer)
        if tuple(sorted(set(self.unmodeled_paths))) != self.unmodeled_paths:
            raise ValueError("unmodeled paths must be sorted and unique")
        if {item.source_pointer for item in self.mapped_claims} & set(self.unmodeled_paths):
            raise ValueError("a source path cannot be both mapped and unmodeled")

    @property
    def status(self) -> MigrationStatus:
        return MigrationStatus.INCOMPLETE if self.unmodeled_paths else MigrationStatus.COMPLETE

    @property
    def content_id(self) -> str:
        return hashlib.sha256(_canonical(self.to_data())).hexdigest()

    def to_data(self) -> dict[str, object]:
        return {
            "mapped_claims": [item.to_data() for item in self.mapped_claims],
            "revision": self.revision,
            "source_schema_revision": self.source_schema_revision,
            "source_sha256": self.source_sha256,
            "status": self.status.value,
            "unmodeled_paths": list(self.unmodeled_paths),
        }


def plan_v112_migration(
    payload: str | bytes,
    mappings: dict[str, MigrationDomain],
) -> V112MigrationPlan:
    """Inventory every source leaf and map only caller-declared paths."""

    raw, encoded = _decode(payload)
    if type(raw) is not dict:
        _fail("migration_source_invalid", "$", "source report must be an object")
    if raw.get("schema_revision") != SOURCE_SCHEMA_REVISION:
        _fail(
            "migration_source_revision_mismatch",
            "$.schema_revision",
            f"expected {SOURCE_SCHEMA_REVISION!r}",
        )
    if type(mappings) is not dict:
        raise ValueError("migration mappings must be an exact dict")
    if len(mappings) > _MAX_MAPPINGS:
        raise ValueError("migration mapping limit exceeded")
    leaves = dict(_leaf_values(raw))
    mapped: list[MigratedClaim] = []
    for pointer, domain in mappings.items():
        _pointer(pointer)
        if type(domain) is not MigrationDomain:
            raise ValueError("migration mapping values must be MigrationDomain instances")
        if pointer not in leaves:
            _fail(
                "migration_mapping_not_leaf",
                pointer,
                "mapping does not identify a source semantic leaf",
            )
        mapped.append(
            MigratedClaim(
                source_pointer=pointer,
                target_domain=domain,
                value_sha256=hashlib.sha256(_canonical(leaves[pointer])).hexdigest(),
            )
        )
    mapped.sort()
    return V112MigrationPlan(
        source_sha256=hashlib.sha256(encoded).hexdigest(),
        mapped_claims=tuple(mapped),
        unmodeled_paths=tuple(sorted(set(leaves) - set(mappings))),
    )


def require_complete_migration(plan: V112MigrationPlan) -> None:
    """Fail closed until every source semantic leaf has a destination."""

    if type(plan) is not V112MigrationPlan:
        raise ValueError("migration plan must be an exact V112MigrationPlan")
    if plan.unmodeled_paths:
        _fail(
            "migration_incomplete",
            plan.unmodeled_paths[0],
            f"{len(plan.unmodeled_paths)} source paths remain unmodeled",
        )


def migration_json(plan: V112MigrationPlan) -> bytes:
    """Serialize a migration plan as canonical UTF-8 JSON."""

    if type(plan) is not V112MigrationPlan:
        raise ValueError("migration plan must be an exact V112MigrationPlan")
    return _canonical(plan.to_data()) + b"\n"


def _decode(payload: str | bytes) -> tuple[object, bytes]:
    if type(payload) is str:
        try:
            encoded = payload.encode()
        except UnicodeEncodeError as error:
            _fail("migration_source_invalid", "$", str(error), cause=error)
    elif type(payload) is bytes:
        encoded = payload
    else:
        raise ValueError("migration payload must be exact str or bytes")
    if len(encoded) > _MAX_BYTES:
        _fail("migration_source_too_large", "$", "source report exceeds the byte limit")
    try:
        raw = json.loads(
            encoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
            parse_int=_parse_integer,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as error:
        _fail("migration_source_invalid", "$", str(error), cause=error)
    _shape_bounds(raw)
    return raw, encoded


def _leaf_values(value: object, pointer: str = "") -> Iterator[tuple[str, object]]:
    if type(value) is dict:
        if not value:
            yield pointer or "/", value
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _leaf_values(value[key], f"{pointer}/{escaped}")
    elif type(value) is list:
        if not value:
            yield pointer or "/", value
        for index, item in enumerate(value):
            yield from _leaf_values(item, f"{pointer}/{index}")
    else:
        yield pointer or "/", value


def _shape_bounds(raw: object) -> None:
    stack = [(raw, 0)]
    seen: set[int] = set()
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_NODES:
            _fail("migration_source_too_large", "$", "source report exceeds the node limit")
        if depth > _MAX_DEPTH:
            _fail("migration_source_too_deep", "$", "source report exceeds the depth limit")
        if type(value) in {dict, list}:
            identity = id(value)
            if identity in seen:
                _fail("migration_source_invalid", "$", "source contains a cycle or alias")
            seen.add(identity)
        if type(value) is dict:
            stack.extend((key, depth + 1) for key in value)
            stack.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            stack.extend((item, depth + 1) for item in value)
        elif type(value) not in {str, int, bool, type(None)}:
            _fail("migration_source_invalid", "$", "source contains a non-JSON value")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number: {value}")


def _reject_float(value: str) -> NoReturn:
    raise ValueError(f"JSON decimal is unsupported: {value}")


def _parse_integer(value: str) -> int:
    if len(value.lstrip("-")) > 19:
        raise ValueError("JSON integer is outside the signed 64-bit range")
    integer = int(value)
    if not -(2**63) <= integer <= 2**63 - 1:
        raise ValueError("JSON integer is outside the signed 64-bit range")
    return integer


def _pointer(value: str) -> None:
    if type(value) is not str or not value.startswith("/") or len(value) > 8_192:
        raise ValueError("migration source pointer is invalid")
    for token in value[1:].split("/"):
        index = 0
        while index < len(token):
            if token[index] == "~":
                if index + 1 >= len(token) or token[index + 1] not in "01":
                    raise ValueError("migration source pointer has invalid escaping")
                index += 2
            else:
                index += 1


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _fail(
    code: str,
    path: str,
    message: str,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    error = IRValidationError((IRDiagnostic(code, path, message),))
    if cause is not None:
        raise error from cause
    raise error
