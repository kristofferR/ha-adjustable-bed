"""Strict immutable input model for Phase 4 v2 cluster reconciliation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Never, cast

from jsonschema.validators import Draft202012Validator

from tools.phase4_v2.equivalence import FrozenPackageRef, Route, validate_frozen_package_ref

from .schema import COMPARISON_AREAS, INPUT_SCHEMA_REVISION, schema_document

_MAX_INPUT_BYTES = 16 * 1024**2
_MAX_JSON_DEPTH = 128
_MAX_JSON_NODES = 1_000_000
_MAX_JSON_STRING = 1_048_576
_MAX_VALUE_BYTES = 1_048_576
_MAX_PACKAGES = 32
_MAX_ROOTS_PER_PACKAGE = 4_096
_MAX_AREA_RECORDS = 100_000
_MAX_TOTAL_RECORDS = 250_000
_MAX_PROVENANCE_PER_RECORD = 4_096
_MAX_ANCHORS = 4_096
_MAX_TEXT = 4_096
_MAX_POINTER = 8_192
_MAX_INTEGER = 2**63 - 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SCHEMA_VALIDATOR = Draft202012Validator(schema_document())

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class ReconciliationError(ValueError):
    """The reconciliation input or result violated its pinned contract."""


class ComparisonArea(StrEnum):
    """The closed protocol-neutral 11-area reconciliation surface."""

    ACTIONS = "actions"
    AUTHENTICATION = "authentication"
    CAPABILITIES_CONFIGURATION = "capabilities_configuration"
    DISCOVERY = "discovery"
    GATT = "gatt"
    LIFECYCLE = "lifecycle"
    MODELS_VARIANTS = "models_variants"
    PACKET_CONSTRUCTION = "packet_construction"
    PARSING = "parsing"
    TIMING_STOP_RELEASE = "timing_stop_release"
    TRANSPORT = "transport"


class ClosureStatus(StrEnum):
    """Whether one package completely closed one comparison area."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class ClaimPolarity(StrEnum):
    """Explicit polarity prevents normalization from hiding semantic reversals."""

    AFFIRMED = "AFFIRMED"
    DENIED = "DENIED"


class DispositionKind(StrEnum):
    """Closed exact-set ledgers that every package report must reconcile."""

    ACTION = "ACTION"
    CANDIDATE = "CANDIDATE"
    VARIANT = "VARIANT"


class DispositionStatus(StrEnum):
    """The exhaustive disposition of a candidate, action, or variant."""

    ABSENT = "ABSENT"
    COVERED = "COVERED"
    EXCLUDED = "EXCLUDED"
    INCOMPLETE = "INCOMPLETE"


def _fail(message: str) -> Never:
    raise ReconciliationError(message)


def _sha256(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256 digest")
    return value


def _token(value: object, field: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        _fail(f"{field} must be a canonical token of at most 200 characters")
    return value


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{field} must be a non-empty string of at most {maximum} characters")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        _fail(f"{field} contains a control character")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail(f"{field} is not valid Unicode")
    return value


def _pointer(value: object, field: str) -> str:
    pointer = _text(value, field, maximum=_MAX_POINTER)
    if not pointer.startswith("/"):
        _fail(f"{field} must be a non-root JSON pointer")
    index = 0
    while index < len(pointer):
        if pointer[index] == "~":
            if index + 1 >= len(pointer) or pointer[index + 1] not in "01":
                _fail(f"{field} contains a non-canonical JSON pointer escape")
            index += 2
            continue
        index += 1
    return pointer


def _ordered_texts(
    values: object,
    field: str,
    *,
    maximum_count: int = _MAX_ANCHORS,
    maximum_length: int = 256,
    require_nonempty: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        _fail(f"{field} must be an immutable tuple")
    typed = cast(tuple[object, ...], values)
    if len(typed) > maximum_count or (require_nonempty and not typed):
        _fail(f"{field} has an invalid number of entries")
    result = tuple(
        _text(value, f"{field}[{index}]", maximum=maximum_length)
        for index, value in enumerate(typed)
    )
    if result != tuple(sorted(set(result))):
        _fail(f"{field} must be sorted and unique")
    return result


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ReconciliationError("value is not canonical JSON") from error


def _content_id(domain: str, value: Mapping[str, object]) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + _canonical_json(value)).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ReconciliationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_integer(value: str) -> int:
    parsed = int(value)
    if abs(parsed) > _MAX_INTEGER:
        raise ReconciliationError("JSON integer exceeds signed 64-bit range")
    return parsed


def _parse_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ReconciliationError("JSON number must be finite")
    return parsed


def _reject_constant(value: str) -> Never:
    raise ReconciliationError(f"JSON constant {value!r} is not permitted")


def _decode_json(payload: str | bytes, *, maximum_bytes: int | None = None) -> JsonValue:
    byte_limit = _MAX_INPUT_BYTES if maximum_bytes is None else maximum_bytes
    if type(payload) is str:
        try:
            raw = payload.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ReconciliationError("input is not valid Unicode") from error
    elif type(payload) is bytes:
        raw = payload
    else:
        _fail("input must be exact str or bytes")
    if len(raw) > byte_limit:
        _fail(f"input exceeds {byte_limit} bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
            parse_int=_parse_integer,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconciliationError("input is not strict UTF-8 JSON") from error
    _validate_json_shape(value)
    return cast(JsonValue, value)


def _validate_json_shape(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            _fail(f"JSON exceeds {_MAX_JSON_NODES} nodes")
        if depth > _MAX_JSON_DEPTH:
            _fail(f"JSON exceeds depth {_MAX_JSON_DEPTH}")
        if current is None or type(current) in {bool, int, float}:
            continue
        if type(current) is str:
            _text(current, "JSON string", maximum=_MAX_JSON_STRING)
            continue
        if type(current) is list:
            stack.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            for key, item in mapping.items():
                _text(key, "JSON object key", maximum=_MAX_JSON_STRING)
                stack.append((item, depth + 1))
            continue
        _fail("JSON contains an unsupported value type")


@dataclass(frozen=True, slots=True)
class CanonicalValue:
    """One normalized semantic value stored as canonical JSON bytes."""

    canonical_json: bytes

    def __post_init__(self) -> None:
        if type(self.canonical_json) is not bytes or len(self.canonical_json) > _MAX_VALUE_BYTES:
            _fail(f"canonical value must be bytes of at most {_MAX_VALUE_BYTES} bytes")
        value = _decode_json(self.canonical_json, maximum_bytes=_MAX_VALUE_BYTES)
        if _canonical_json(value) != self.canonical_json:
            _fail("semantic value is not in canonical JSON form")

    @classmethod
    def from_data(cls, value: object) -> CanonicalValue:
        """Validate and freeze one normalized JSON value."""
        _validate_json_shape(value)
        encoded = _canonical_json(value)
        if len(encoded) > _MAX_VALUE_BYTES:
            _fail(f"semantic value exceeds {_MAX_VALUE_BYTES} bytes")
        return cls(encoded)

    def to_data(self) -> JsonValue:
        return _decode_json(self.canonical_json, maximum_bytes=_MAX_VALUE_BYTES)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json).hexdigest()


@dataclass(frozen=True, slots=True)
class RootProvenance:
    """Exact package-local root and accepted report location for semantic leaves."""

    package_ref_id: str
    target_root_id: str
    occurrence_identity_sha256: str
    route: Route
    semantic_root_sha256: str | None
    source_root_id: str | None
    source_package_ref_id: str | None
    source_occurrence_identity_sha256: str | None
    source_validation_receipt_sha256: str | None
    source_raw_receipt_sha256: str | None
    report_pointer: str
    evidence_anchor_ids: tuple[str, ...]
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _sha256(self.package_ref_id, "root.package_ref_id")
        _sha256(self.target_root_id, "root.target_root_id")
        _sha256(self.occurrence_identity_sha256, "root.occurrence_identity_sha256")
        if type(self.route) is not Route:
            _fail("root.route must use the public Route type")
        _pointer(self.report_pointer, "root.report_pointer")
        anchors = _ordered_texts(self.evidence_anchor_ids, "root.evidence_anchor_ids")
        blockers = _ordered_texts(
            self.blockers,
            "root.blockers",
            maximum_length=_MAX_TEXT,
        )
        semantic = _sha256(
            self.semantic_root_sha256,
            "root.semantic_root_sha256",
            optional=True,
        )
        source = _sha256(self.source_root_id, "root.source_root_id", optional=True)
        source_package = _sha256(
            self.source_package_ref_id, "root.source_package_ref_id", optional=True
        )
        source_occurrence = _sha256(
            self.source_occurrence_identity_sha256,
            "root.source_occurrence_identity_sha256",
            optional=True,
        )
        source_receipt = _sha256(
            self.source_validation_receipt_sha256,
            "root.source_validation_receipt_sha256",
            optional=True,
        )
        source_raw_receipt = _sha256(
            self.source_raw_receipt_sha256,
            "root.source_raw_receipt_sha256",
            optional=True,
        )
        if self.route is Route.FULL_ANALYSIS:
            if (
                semantic is None
                or source is not None
                or source_occurrence is None
                or source_receipt is None
                or source_raw_receipt is None
                or source_package is None
                or blockers
                or not anchors
            ):
                _fail("FULL_ANALYSIS root requires authenticated semantic evidence")
        elif self.route is Route.EXACT_REUSE:
            if (
                semantic is None
                or source is None
                or source_occurrence is None
                or source_receipt is None
                or source_raw_receipt is None
                or source_package is None
                or blockers
                or not anchors
            ):
                _fail("EXACT_REUSE root requires inherited semantic evidence and source root")
        elif self.route is Route.BLOCKED:
            if (
                semantic is not None
                or source is not None
                or source_occurrence is not None
                or source_receipt is not None
                or source_raw_receipt is not None
                or source_package is not None
                or not blockers
            ):
                _fail("BLOCKED root requires blockers and no semantic or source root")
        else:
            _fail("root.route is unsupported")

    def to_data(self) -> dict[str, object]:
        return {
            "blockers": list(self.blockers),
            "evidence_anchor_ids": list(self.evidence_anchor_ids),
            "occurrence_identity_sha256": self.occurrence_identity_sha256,
            "package_ref_id": self.package_ref_id,
            "report_pointer": self.report_pointer,
            "route": self.route.value,
            "semantic_root_sha256": self.semantic_root_sha256,
            "source_root_id": self.source_root_id,
            "source_package_ref_id": self.source_package_ref_id,
            "source_occurrence_identity_sha256": self.source_occurrence_identity_sha256,
            "source_validation_receipt_sha256": self.source_validation_receipt_sha256,
            "source_raw_receipt_sha256": self.source_raw_receipt_sha256,
            "target_root_id": self.target_root_id,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:reconciliation-root-provenance", self.to_data())


@dataclass(frozen=True, slots=True)
class LeafProvenance:
    """Exact report node and artifact anchors supporting one normalized leaf."""

    root_ref_id: str
    report_pointer: str
    evidence_anchor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _sha256(self.root_ref_id, "provenance.root_ref_id")
        _pointer(self.report_pointer, "provenance.report_pointer")
        _ordered_texts(
            self.evidence_anchor_ids,
            "provenance.evidence_anchor_ids",
            require_nonempty=True,
        )

    def to_data(self) -> dict[str, object]:
        return {
            "evidence_anchor_ids": list(self.evidence_anchor_ids),
            "report_pointer": self.report_pointer,
            "root_ref_id": self.root_ref_id,
        }

    @property
    def sort_key(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.root_ref_id, self.report_pointer, self.evidence_anchor_ids)


def _provenance_tuple(value: object, field: str) -> tuple[LeafProvenance, ...]:
    if type(value) is not tuple:
        _fail(f"{field} must be an immutable tuple")
    items = cast(tuple[object, ...], value)
    if not items or len(items) > _MAX_PROVENANCE_PER_RECORD:
        _fail(f"{field} has an invalid number of entries")
    result: list[LeafProvenance] = []
    for index, item in enumerate(items):
        if type(item) is not LeafProvenance:
            _fail(f"{field}[{index}] must be LeafProvenance")
        item.__post_init__()
        result.append(item)
    typed = tuple(result)
    if typed != tuple(sorted(typed, key=lambda item: item.sort_key)):
        _fail(f"{field} must be sorted")
    if len({item.sort_key for item in typed}) != len(typed):
        _fail(f"{field} contains duplicate provenance")
    return typed


@dataclass(frozen=True, slots=True)
class NormalizedClaim:
    """One closed, normalized semantic leaf with exact provenance."""

    key: str
    polarity: ClaimPolarity
    value: CanonicalValue
    provenance: tuple[LeafProvenance, ...]

    def __post_init__(self) -> None:
        _pointer(self.key, "claim.key")
        if type(self.polarity) is not ClaimPolarity:
            _fail("claim.polarity is invalid")
        if type(self.value) is not CanonicalValue:
            _fail("claim.value must be CanonicalValue")
        self.value.__post_init__()
        _provenance_tuple(self.provenance, "claim.provenance")

    def to_data(self) -> dict[str, object]:
        return {
            "key": self.key,
            "polarity": self.polarity.value,
            "provenance": [item.to_data() for item in self.provenance],
            "value": self.value.to_data(),
        }

    @property
    def sort_key(self) -> tuple[str, str, str, tuple[tuple[str, str, tuple[str, ...]], ...]]:
        return (
            self.key,
            self.polarity.value,
            self.value.sha256,
            tuple(item.sort_key for item in self.provenance),
        )


@dataclass(frozen=True, slots=True)
class LedgerDisposition:
    """Exact candidate, action, or variant disposition."""

    kind: DispositionKind
    item_id: str
    status: DispositionStatus
    reason_code: str
    claim_keys: tuple[str, ...]
    provenance: tuple[LeafProvenance, ...]

    def __post_init__(self) -> None:
        if type(self.kind) is not DispositionKind or type(self.status) is not DispositionStatus:
            _fail("disposition kind and status must use the closed enums")
        _token(self.item_id, "disposition.item_id")
        _token(self.reason_code, "disposition.reason_code")
        keys = _ordered_texts(
            self.claim_keys,
            "disposition.claim_keys",
            maximum_length=_MAX_POINTER,
        )
        for index, key in enumerate(keys):
            _pointer(key, f"disposition.claim_keys[{index}]")
        if self.status is DispositionStatus.COVERED and not keys:
            _fail("COVERED disposition requires at least one claim key")
        _provenance_tuple(self.provenance, "disposition.provenance")

    def to_data(self) -> dict[str, object]:
        return {
            "claim_keys": list(self.claim_keys),
            "item_id": self.item_id,
            "kind": self.kind.value,
            "provenance": [item.to_data() for item in self.provenance],
            "reason_code": self.reason_code,
            "status": self.status.value,
        }

    @property
    def identity(self) -> str:
        return f"{self.kind.value}:{self.item_id}"

    @property
    def sort_key(self) -> tuple[object, ...]:
        return (
            self.kind.value,
            self.item_id,
            self.status.value,
            self.reason_code,
            self.claim_keys,
            tuple(item.sort_key for item in self.provenance),
        )


@dataclass(frozen=True, slots=True)
class AreaSurface:
    """One package's closed normalized surface for one comparison area."""

    area: ComparisonArea
    closure: ClosureStatus
    claims: tuple[NormalizedClaim, ...]
    dispositions: tuple[LedgerDisposition, ...]
    gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.area) is not ComparisonArea or type(self.closure) is not ClosureStatus:
            _fail("area and closure must use the closed enums")
        if type(self.claims) is not tuple or len(self.claims) > _MAX_AREA_RECORDS:
            _fail("area.claims must be a bounded immutable tuple")
        if type(self.dispositions) is not tuple or len(self.dispositions) > _MAX_AREA_RECORDS:
            _fail("area.dispositions must be a bounded immutable tuple")
        for item in self.claims:
            if type(item) is not NormalizedClaim:
                _fail("area.claims contains a non-claim")
            item.__post_init__()
        for item in self.dispositions:
            if type(item) is not LedgerDisposition:
                _fail("area.dispositions contains a non-disposition")
            item.__post_init__()
        if self.claims != tuple(sorted(self.claims, key=lambda item: item.sort_key)):
            _fail("area.claims must be sorted")
        if self.dispositions != tuple(sorted(self.dispositions, key=lambda item: item.sort_key)):
            _fail("area.dispositions must be sorted")
        gaps = _ordered_texts(self.gaps, "area.gaps", maximum_length=_MAX_TEXT)
        if self.closure is ClosureStatus.COMPLETE:
            if gaps or any(
                item.status is DispositionStatus.INCOMPLETE for item in self.dispositions
            ):
                _fail("COMPLETE area cannot contain gaps or incomplete dispositions")
        elif not gaps and not any(
            item.status is DispositionStatus.INCOMPLETE for item in self.dispositions
        ):
            _fail("INCOMPLETE area requires a gap or incomplete disposition")
        known_claims = {item.key for item in self.claims}
        unknown = sorted(
            key
            for disposition in self.dispositions
            for key in disposition.claim_keys
            if key not in known_claims
        )
        if unknown:
            _fail(f"disposition references unknown claim {unknown[0]!r}")

    def to_data(self) -> dict[str, object]:
        return {
            "area": self.area.value,
            "claims": [item.to_data() for item in self.claims],
            "closure": self.closure.value,
            "dispositions": [item.to_data() for item in self.dispositions],
            "gaps": list(self.gaps),
        }


@dataclass(frozen=True, slots=True)
class PackageSurface:
    """The complete normalized comparison input for one frozen package report."""

    package_ref: FrozenPackageRef
    report_sha256: str
    report_revision: str
    roots: tuple[RootProvenance, ...]
    areas: tuple[AreaSurface, ...]

    def __post_init__(self) -> None:
        validate_frozen_package_ref(self.package_ref)
        _sha256(self.report_sha256, "package.report_sha256")
        _token(self.report_revision, "package.report_revision")
        if (
            type(self.roots) is not tuple
            or not self.roots
            or len(self.roots) > _MAX_ROOTS_PER_PACKAGE
        ):
            _fail("package.roots must be a bounded non-empty immutable tuple")
        for root in self.roots:
            if type(root) is not RootProvenance:
                _fail("package.roots contains an invalid record")
            root.__post_init__()
            if root.package_ref_id != self.package_ref.content_id:
                _fail("root package reference does not match its containing package")
        if self.roots != tuple(sorted(self.roots, key=lambda item: item.content_id)):
            _fail("package.roots must be sorted by content ID")
        root_ids = {item.content_id for item in self.roots}
        roots_by_id = {item.content_id: item for item in self.roots}
        if len(root_ids) != len(self.roots):
            _fail("package.roots contains duplicate root provenance")
        if type(self.areas) is not tuple or len(self.areas) > len(ComparisonArea):
            _fail("package.areas must be a bounded immutable tuple")
        for area in self.areas:
            if type(area) is not AreaSurface:
                _fail("package.areas contains an invalid record")
            area.__post_init__()
        if self.areas != tuple(sorted(self.areas, key=lambda item: item.area.value)):
            _fail("package.areas must be sorted")
        if len({item.area for item in self.areas}) != len(self.areas):
            _fail("package.areas contains a duplicate area")
        for area in self.areas:
            for provenance in (item for claim in area.claims for item in claim.provenance):
                if provenance.root_ref_id not in root_ids:
                    _fail("claim provenance references a root outside its package")
                if roots_by_id[provenance.root_ref_id].route is Route.BLOCKED:
                    _fail("claim provenance cannot reference a blocked root")
                if not set(provenance.evidence_anchor_ids) <= set(
                    roots_by_id[provenance.root_ref_id].evidence_anchor_ids
                ):
                    _fail("claim provenance contains an anchor not attested by its root")
            for provenance in (
                item for disposition in area.dispositions for item in disposition.provenance
            ):
                if provenance.root_ref_id not in root_ids:
                    _fail("disposition provenance references a root outside its package")
                if roots_by_id[provenance.root_ref_id].route is Route.BLOCKED:
                    _fail("disposition provenance cannot reference a blocked root")
                if not set(provenance.evidence_anchor_ids) <= set(
                    roots_by_id[provenance.root_ref_id].evidence_anchor_ids
                ):
                    _fail("disposition provenance contains an anchor not attested by its root")

    def to_data(self) -> dict[str, object]:
        return {
            "areas": [item.to_data() for item in self.areas],
            "package_ref_id": self.package_ref.content_id,
            "report_revision": self.report_revision,
            "report_sha256": self.report_sha256,
            "roots": [item.to_data() for item in self.roots],
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:reconciliation-package-surface", self.to_data())


@dataclass(frozen=True, slots=True)
class ReconciliationInput:
    """A frozen set of package-local normalized reports for one formal cluster."""

    cluster_id: str
    packages: tuple[PackageSurface, ...]
    revision: str = INPUT_SCHEMA_REVISION

    def __post_init__(self) -> None:
        _token(self.cluster_id, "cluster_id")
        if self.revision != INPUT_SCHEMA_REVISION:
            _fail(f"unsupported reconciliation input revision {self.revision!r}")
        if type(self.packages) is not tuple or not 2 <= len(self.packages) <= _MAX_PACKAGES:
            _fail(f"packages must contain between 2 and {_MAX_PACKAGES} entries")
        for package in self.packages:
            if type(package) is not PackageSurface:
                _fail("packages contains an invalid package surface")
            package.__post_init__()
        if self.packages != tuple(
            sorted(self.packages, key=lambda item: item.package_ref.content_id)
        ):
            _fail("packages must be sorted by frozen package reference ID")
        package_ids = [item.package_ref.content_id for item in self.packages]
        if len(set(package_ids)) != len(package_ids):
            _fail("packages contains a duplicate frozen package reference")
        record_count = sum(
            len(area.claims) + len(area.dispositions)
            for package in self.packages
            for area in package.areas
        )
        if record_count > _MAX_TOTAL_RECORDS:
            _fail(f"reconciliation input exceeds {_MAX_TOTAL_RECORDS} semantic records")
        if tuple(item.value for item in ComparisonArea) != COMPARISON_AREAS:
            _fail("comparison-area enum differs from the pinned schema")

    def to_data(self) -> dict[str, object]:
        return {
            "cluster_id": self.cluster_id,
            "packages": [item.to_data() for item in self.packages],
            "revision": self.revision,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:reconciliation-input", self.to_data())


def dumps_input(value: ReconciliationInput) -> bytes:
    """Serialize a fully revalidated input into canonical JSON."""
    if type(value) is not ReconciliationInput:
        _fail("value must be ReconciliationInput")
    value.__post_init__()
    encoded = _canonical_json(value.to_data())
    if len(encoded) > _MAX_INPUT_BYTES:
        _fail(f"input exceeds {_MAX_INPUT_BYTES} bytes")
    return encoded


def loads_input(
    payload: str | bytes,
    *,
    trusted_input: ReconciliationInput,
) -> ReconciliationInput:
    """Verify serialized input against an already authority-derived snapshot."""
    if type(trusted_input) is not ReconciliationInput:
        _fail("trusted input must use the exact ReconciliationInput type")
    expected = dumps_input(trusted_input)
    supplied = payload.encode("utf-8", errors="strict") if type(payload) is str else payload
    if type(supplied) is not bytes or supplied != expected:
        _fail("serialized input differs from the authority-derived reconciliation input")
    return trusted_input


def _loads_untrusted_input(
    payload: str | bytes,
    *,
    package_refs: Mapping[str, FrozenPackageRef],
) -> ReconciliationInput:
    """Internal schema parser; never an authority boundary."""
    raw = _decode_json(payload)
    errors = sorted(
        _SCHEMA_VALIDATOR.iter_errors(raw),
        key=lambda item: tuple(str(part) for part in item.path),
    )
    if errors:
        first = errors[0]
        location = "/".join(str(item) for item in first.absolute_path) or "$"
        _fail(f"schema validation failed at {location}: {first.message}")
    trusted_refs = {
        package_ref_id: validate_frozen_package_ref(package_ref)
        for package_ref_id, package_ref in package_refs.items()
    }
    if any(key != value.content_id for key, value in trusted_refs.items()):
        _fail("trusted package reference mapping contains a transplanted key")
    return _parse_input(cast(dict[str, object], raw), trusted_refs)


def _parse_input(
    raw: dict[str, object], package_refs: Mapping[str, FrozenPackageRef]
) -> ReconciliationInput:
    packages = tuple(
        _parse_package(cast(dict[str, object], item), package_refs)
        for item in cast(list[object], raw["packages"])
    )
    return ReconciliationInput(
        cluster_id=cast(str, raw["cluster_id"]),
        packages=packages,
        revision=cast(str, raw["revision"]),
    )


def _parse_package(
    raw: dict[str, object], package_refs: Mapping[str, FrozenPackageRef]
) -> PackageSurface:
    package_ref_id = cast(str, raw["package_ref_id"])
    try:
        package_ref = package_refs[package_ref_id]
    except KeyError:
        _fail(f"missing trusted package reference {package_ref_id!r}")
    roots = tuple(
        _parse_root(cast(dict[str, object], item)) for item in cast(list[object], raw["roots"])
    )
    areas = tuple(
        _parse_area(cast(dict[str, object], item)) for item in cast(list[object], raw["areas"])
    )
    return PackageSurface(
        package_ref=package_ref,
        report_sha256=cast(str, raw["report_sha256"]),
        report_revision=cast(str, raw["report_revision"]),
        roots=roots,
        areas=areas,
    )


def _parse_root(raw: dict[str, object]) -> RootProvenance:
    return RootProvenance(
        package_ref_id=cast(str, raw["package_ref_id"]),
        target_root_id=cast(str, raw["target_root_id"]),
        occurrence_identity_sha256=cast(str, raw["occurrence_identity_sha256"]),
        route=Route(cast(str, raw["route"])),
        semantic_root_sha256=cast(str | None, raw["semantic_root_sha256"]),
        source_root_id=cast(str | None, raw["source_root_id"]),
        source_package_ref_id=cast(str | None, raw["source_package_ref_id"]),
        source_occurrence_identity_sha256=cast(
            str | None, raw["source_occurrence_identity_sha256"]
        ),
        source_validation_receipt_sha256=cast(
            str | None, raw["source_validation_receipt_sha256"]
        ),
        source_raw_receipt_sha256=cast(str | None, raw["source_raw_receipt_sha256"]),
        report_pointer=cast(str, raw["report_pointer"]),
        evidence_anchor_ids=tuple(cast(list[str], raw["evidence_anchor_ids"])),
        blockers=tuple(cast(list[str], raw["blockers"])),
    )


def _parse_provenance(raw: dict[str, object]) -> LeafProvenance:
    return LeafProvenance(
        root_ref_id=cast(str, raw["root_ref_id"]),
        report_pointer=cast(str, raw["report_pointer"]),
        evidence_anchor_ids=tuple(cast(list[str], raw["evidence_anchor_ids"])),
    )


def _parse_area(raw: dict[str, object]) -> AreaSurface:
    claims = tuple(
        _parse_claim(cast(dict[str, object], item)) for item in cast(list[object], raw["claims"])
    )
    dispositions = tuple(
        _parse_disposition(cast(dict[str, object], item))
        for item in cast(list[object], raw["dispositions"])
    )
    return AreaSurface(
        area=ComparisonArea(cast(str, raw["area"])),
        closure=ClosureStatus(cast(str, raw["closure"])),
        claims=claims,
        dispositions=dispositions,
        gaps=tuple(cast(list[str], raw["gaps"])),
    )


def _parse_claim(raw: dict[str, object]) -> NormalizedClaim:
    return NormalizedClaim(
        key=cast(str, raw["key"]),
        polarity=ClaimPolarity(cast(str, raw["polarity"])),
        value=CanonicalValue.from_data(raw["value"]),
        provenance=tuple(
            _parse_provenance(cast(dict[str, object], item))
            for item in cast(list[object], raw["provenance"])
        ),
    )


def _parse_disposition(raw: dict[str, object]) -> LedgerDisposition:
    return LedgerDisposition(
        kind=DispositionKind(cast(str, raw["kind"])),
        item_id=cast(str, raw["item_id"]),
        status=DispositionStatus(cast(str, raw["status"])),
        reason_code=cast(str, raw["reason_code"]),
        claim_keys=tuple(cast(list[str], raw["claim_keys"])),
        provenance=tuple(
            _parse_provenance(cast(dict[str, object], item))
            for item in cast(list[object], raw["provenance"])
        ),
    )


def canonical_content_id(domain: str, value: Mapping[str, object]) -> str:
    """Hash a closed record using the package's canonical encoding."""
    _token(domain, "content-id domain")
    return _content_id(domain, value)


def canonical_json_bytes(value: object) -> bytes:
    """Return canonical bytes after applying the shared JSON bounds."""
    _validate_json_shape(value)
    return _canonical_json(value)


def load_bounded_json(payload: str | bytes) -> JsonValue:
    """Load a bounded strict JSON document for renderer verification."""
    return _decode_json(payload)
