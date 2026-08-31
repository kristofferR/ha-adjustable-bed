"""Strict, protocol-neutral core model for the Phase 4 v2 protocol IR."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Never, Protocol, cast

SCHEMA_REVISION = "phase4-protocol-ir-core-v0.5.0-2026-08-31"
PROVENANCE_IDENTITY_REVISION = "phase4-provenance-identity-v4"
SUPPORTED_VALIDATOR_REVISION = "phase4-v2-bundle-validator-v4"
SUPPORTED_CONTRACT_REVISION = "phase4-v2-validation-input-v3"
BOUND_VALIDATION_PROFILE = "BOUND_V4"
_DEPENDENCY_NAMES = ("corpus", "evidence_lineage", "ir", "preflight", "schema")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_MAX_VARIANT_PROFILES = 100_000
_MAX_VARIANT_DIMENSIONS = 128
_MAX_PROVENANCE_DEFINITIONS = 250_000
_MAX_PROVENANCE_REFERENCES = 4_096
_MAX_PROVENANCE_EDGES = 1_000_000
_MAX_PROVENANCE_EXPANSIONS = 1_000_000
_MAX_REPORT_PATH_LENGTH = 4_096
_MAX_JSON_POINTER_LENGTH = 8_192
_MAX_IR_BYTES = 64 * 1024**2
_MAX_RECEIPT_BYTES = 64 * 1024**2
_MAX_JSON_DEPTH = 128
_MAX_JSON_NODES = 2_000_000
_MAX_VALIDATION_DIAGNOSTICS = 4_096
_MIN_INTEGER = -(2**63)
_MAX_INTEGER = 2**63 - 1

type JsonScalar = str | int | bool
type Profile = tuple[tuple[str, JsonScalar], ...]


@dataclass(frozen=True, slots=True)
class IRDiagnostic:
    """A deterministic structural or semantic validation diagnostic."""

    code: str
    path: str
    message: str


class IRValidationError(ValueError):
    """Raised when an IR document is structurally or semantically invalid."""

    def __init__(self, diagnostics: Iterable[IRDiagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        detail = "; ".join(
            f"{item.code} at {item.path}: {item.message}" for item in self.diagnostics
        )
        super().__init__(detail)


class _BoundedDiagnostics(list[IRDiagnostic]):
    """Diagnostic collector that cannot amplify hostile input without bound."""

    def append(self, item: IRDiagnostic) -> None:
        if len(self) >= _MAX_VALIDATION_DIAGNOSTICS:
            _fail(
                "validation_diagnostic_limit_exceeded",
                "$",
                f"validation produced more than {_MAX_VALIDATION_DIAGNOSTICS} diagnostics",
            )
        super().append(item)

    def extend(self, values: Iterable[IRDiagnostic]) -> None:
        for item in values:
            self.append(item)


class _DataDefinition(Protocol):
    def to_data(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """Immutable identity of the package artifact represented by one report."""

    package_name: str
    version_code: str
    version_name: str
    artifact_digest: str

    def to_data(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "package_name": self.package_name,
            "version_code": self.version_code,
            "version_name": self.version_name,
        }


@dataclass(frozen=True, slots=True)
class AttestedEvidenceMember:
    """Exact evidence member reproduced by the bound validator run."""

    member: str
    owner: str
    sha256: str

    def to_data(self) -> dict[str, object]:
        return {"member": self.member, "owner": self.owner, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class AttestedEvidenceAnchor:
    """Exact byte anchor reproduced by the bound validator run."""

    id: str
    owner: str
    member: str
    member_sha256: str
    start_byte: int
    end_byte: int
    ir_pointer: str
    representation: str
    value_sha256: str

    def to_data(self) -> dict[str, object]:
        return {
            "end_byte": self.end_byte,
            "id": self.id,
            "ir_pointer": self.ir_pointer,
            "member": self.member,
            "member_sha256": self.member_sha256,
            "owner": self.owner,
            "representation": self.representation,
            "start_byte": self.start_byte,
            "value_sha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True)
class ValidatedReport:
    """Exact accepted BOUND_V4 receipt and all provenance attestations."""

    validator_revision: str
    contract_revision: str
    validation_profile: str
    validation_receipt_sha256: str
    bundle_sha256: str
    report_manifest_sha256: str
    discovered_members: int
    declared_members: int
    evidence_anchors_checked: int
    validated_artifact_identity: ArtifactIdentity
    dependency_digests: tuple[tuple[str, str], ...]
    validated_evidence_members: tuple[AttestedEvidenceMember, ...]
    validated_evidence_anchors: tuple[AttestedEvidenceAnchor, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "bundle_sha256": self.bundle_sha256,
            "contract_revision": self.contract_revision,
            "declared_members": self.declared_members,
            "dependency_digests": dict(self.dependency_digests),
            "discovered_members": self.discovered_members,
            "evidence_anchors_checked": self.evidence_anchors_checked,
            "report_manifest_sha256": self.report_manifest_sha256,
            "validated_artifact_identity": self.validated_artifact_identity.to_data(),
            "validated_evidence_anchors": [
                anchor.to_data() for anchor in self.validated_evidence_anchors
            ],
            "validated_evidence_members": [
                member.to_data() for member in self.validated_evidence_members
            ],
            "validation_profile": self.validation_profile,
            "validation_receipt_sha256": self.validation_receipt_sha256,
            "validator_revision": self.validator_revision,
        }


@dataclass(frozen=True, slots=True)
class SourcePackage:
    """One artifact and the validated report from which evidence may be cited."""

    artifact: ArtifactIdentity
    report: ValidatedReport

    def to_data(self) -> dict[str, object]:
        return {"artifact": self.artifact.to_data(), "report": self.report.to_data()}


@dataclass(frozen=True, slots=True)
class EvidenceFile:
    """One validator-manifest member pinned to a package and exact digest."""

    package: str
    member: str
    sha256: str

    def to_data(self) -> dict[str, object]:
        return {"member": self.member, "package": self.package, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    """One exact validator-attested anchor in a content-pinned file."""

    id: str
    file: str
    start_byte: int
    end_byte: int
    ir_pointer: str
    representation: str
    value_sha256: str

    def to_data(self) -> dict[str, object]:
        return {
            "end_byte": self.end_byte,
            "file": self.file,
            "id": self.id,
            "ir_pointer": self.ir_pointer,
            "representation": self.representation,
            "start_byte": self.start_byte,
            "value_sha256": self.value_sha256,
        }


@dataclass(frozen=True, slots=True)
class SourceSet:
    """A non-empty, package-local conjunction of evidence anchors."""

    package: str
    anchors: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {"package": self.package, "anchors": list(self.anchors)}


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    """Evidence source sets supporting one exact semantic JSON leaf."""

    target: str
    source_sets: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {"target": self.target, "source_sets": list(self.source_sets)}


@dataclass(frozen=True, slots=True)
class Predicate:
    """A closed predicate AST evaluated against one static variant profile."""

    op: str
    dimension: str | None = None
    value: JsonScalar | None = None
    values: tuple[JsonScalar, ...] = ()
    terms: tuple[Predicate, ...] = ()

    def matches(self, profile: Mapping[str, JsonScalar]) -> bool:
        """Return whether this predicate accepts a variant profile."""

        if self.op == "always":
            return True
        if self.op == "never":
            return False
        if self.op == "eq":
            assert self.dimension is not None
            return _scalars_equal(profile[self.dimension], self.value)
        if self.op == "in":
            assert self.dimension is not None
            actual = profile[self.dimension]
            return any(_scalars_equal(actual, value) for value in self.values)
        if self.op == "all":
            return all(term.matches(profile) for term in self.terms)
        if self.op == "any":
            return any(term.matches(profile) for term in self.terms)
        if self.op == "not":
            return not self.terms[0].matches(profile)
        raise AssertionError(f"unhandled predicate operation: {self.op}")

    def to_data(self) -> dict[str, object]:
        """Return the normalized JSON representation."""

        data: dict[str, object] = {"op": self.op}
        if self.op == "eq":
            data["dimension"] = self.dimension
            data["value"] = self.value
        elif self.op == "in":
            data["dimension"] = self.dimension
            data["values"] = list(self.values)
        elif self.op in {"all", "any"}:
            data["terms"] = [term.to_data() for term in self.terms]
        elif self.op == "not":
            data["term"] = self.terms[0].to_data()
        return data


@dataclass(frozen=True, slots=True)
class VariantSpace:
    """Finite static selector dimensions and constraints for one protocol."""

    dimensions: tuple[tuple[str, tuple[JsonScalar, ...]], ...]
    constraints: tuple[Predicate, ...]

    def profiles(self) -> tuple[Profile, ...]:
        """Enumerate valid profiles transiently without storing a Cartesian table."""

        names = tuple(name for name, _values in self.dimensions)
        domains = tuple(values for _name, values in self.dimensions)
        combinations = itertools.product(*domains) if domains else ((),)
        profiles: list[Profile] = []
        for combination in combinations:
            profile = tuple(zip(names, combination, strict=True))
            profile_map = dict(profile)
            if all(constraint.matches(profile_map) for constraint in self.constraints):
                profiles.append(profile)
        return tuple(profiles)

    def to_data(self) -> dict[str, object]:
        return {
            "dimensions": {name: list(values) for name, values in self.dimensions},
            "constraints": [constraint.to_data() for constraint in self.constraints],
        }


@dataclass(frozen=True, slots=True)
class ProtocolDefinition:
    variant_space: str

    def to_data(self) -> dict[str, object]:
        return {"variant_space": self.variant_space}


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    summary: str | None = None

    def to_data(self) -> dict[str, object]:
        return {} if self.summary is None else {"summary": self.summary}


@dataclass(frozen=True, slots=True)
class ExpectedActionRule:
    protocol: str
    action: str
    when: Predicate

    def to_data(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "action": self.action,
            "when": self.when.to_data(),
        }


@dataclass(frozen=True, slots=True)
class CommandBinding:
    protocol: str
    action: str
    when: Predicate

    def to_data(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "action": self.action,
            "when": self.when.to_data(),
        }


@dataclass(frozen=True, slots=True)
class ProtocolIRDocument:
    """Compact canonical IR with package-local, content-bound provenance."""

    schema_revision: str
    source_packages: tuple[tuple[str, SourcePackage], ...]
    evidence_files: tuple[tuple[str, EvidenceFile], ...]
    evidence_anchors: tuple[tuple[str, EvidenceAnchor], ...]
    source_sets: tuple[tuple[str, SourceSet], ...]
    evidence_bindings: tuple[tuple[str, EvidenceBinding], ...]
    variant_spaces: tuple[tuple[str, VariantSpace], ...]
    protocols: tuple[tuple[str, ProtocolDefinition], ...]
    actions: tuple[tuple[str, ActionDefinition], ...]
    expected_action_rules: tuple[tuple[str, ExpectedActionRule], ...]
    command_bindings: tuple[tuple[str, CommandBinding], ...]

    def to_data(self) -> dict[str, object]:
        """Return normalized JSON data with all definition maps ID-keyed."""

        return {
            "schema_revision": self.schema_revision,
            "source_packages": {
                identifier: definition.to_data() for identifier, definition in self.source_packages
            },
            "evidence_files": {
                identifier: definition.to_data() for identifier, definition in self.evidence_files
            },
            "evidence_anchors": {
                identifier: definition.to_data() for identifier, definition in self.evidence_anchors
            },
            "source_sets": {
                identifier: definition.to_data() for identifier, definition in self.source_sets
            },
            "evidence_bindings": {
                identifier: definition.to_data()
                for identifier, definition in self.evidence_bindings
            },
            "variant_spaces": {
                identifier: definition.to_data() for identifier, definition in self.variant_spaces
            },
            "protocols": {
                identifier: definition.to_data() for identifier, definition in self.protocols
            },
            "actions": {
                identifier: definition.to_data() for identifier, definition in self.actions
            },
            "expected_action_rules": {
                identifier: definition.to_data()
                for identifier, definition in self.expected_action_rules
            },
            "command_bindings": {
                identifier: definition.to_data() for identifier, definition in self.command_bindings
            },
        }


@dataclass(frozen=True, slots=True)
class UniverseKey:
    protocol: str
    action: str
    profile: Profile


@dataclass(frozen=True, slots=True)
class UniverseIssue:
    code: str
    key: UniverseKey | None
    binding_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UniverseValidation:
    expected: frozenset[UniverseKey]
    actual: frozenset[UniverseKey]
    issues: tuple[UniverseIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def build_artifact_identity(
    *,
    package_name: str,
    version_code: str,
    version_name: str,
    artifact_digest: str,
) -> ArtifactIdentity:
    """Build and validate one immutable package artifact identity."""

    return _parse_artifact_identity(
        {
            "package_name": package_name,
            "version_code": version_code,
            "version_name": version_name,
            "artifact_digest": artifact_digest,
        },
        "$.artifact",
    )


def bind_validator_receipt(
    receipt_payload: str | bytes,
    *,
    trusted_validator_revision: str,
    trusted_contract_revision: str,
    trusted_dependency_digests: Mapping[str, str],
    trusted_receipt_sha256: str,
) -> ValidatedReport:
    """Bind a canonical BOUND_V4 receipt to explicit caller trust roots."""

    if trusted_validator_revision != SUPPORTED_VALIDATOR_REVISION:
        _fail(
            "unsupported_validator_revision",
            "$.trust.validator_revision",
            f"supported validator revision is {SUPPORTED_VALIDATOR_REVISION!r}",
        )
    if trusted_contract_revision != SUPPORTED_CONTRACT_REVISION:
        _fail(
            "unsupported_contract_revision",
            "$.trust.contract_revision",
            f"supported contract revision is {SUPPORTED_CONTRACT_REVISION!r}",
        )
    trusted_pins = _parse_dependency_digests(
        trusted_dependency_digests,
        "$.trust.dependency_digests",
    )
    trusted_receipt_digest = _expect_sha256(trusted_receipt_sha256, "$.trust.receipt_sha256")
    raw, encoded = _decode_strict_json(receipt_payload, max_bytes=_MAX_RECEIPT_BYTES)
    receipt = _expect_object(raw, "$.receipt")
    if encoded != _canonical_json(receipt):
        _fail(
            "receipt_not_canonical",
            "$.receipt",
            "validator receipt must be canonical UTF-8 JSON without a trailing newline",
        )
    return _bind_receipt_data(
        receipt,
        trusted_validator_revision=trusted_validator_revision,
        trusted_contract_revision=trusted_contract_revision,
        trusted_dependency_digests=trusted_pins,
        trusted_receipt_sha256=trusted_receipt_digest,
    )


def build_source_package(
    artifact: ArtifactIdentity, report: ValidatedReport
) -> tuple[str, SourcePackage]:
    """Build a source-package definition and its canonical content ID."""

    package = _parse_source_package(
        {"artifact": artifact.to_data(), "report": report.to_data()},
        "$.source_package",
    )
    return _definition_with_id("pkg", package)


def build_evidence_file(*, package: str, member: str, sha256: str) -> tuple[str, EvidenceFile]:
    """Build a content-pinned validator-manifest member definition."""

    evidence_file = _parse_evidence_file(
        {"package": package, "member": member, "sha256": sha256},
        "$.evidence_file",
    )
    return _definition_with_id("file", evidence_file)


def build_evidence_anchor(
    *,
    id: str,
    file: str,
    start_byte: int,
    end_byte: int,
    ir_pointer: str,
    representation: str,
    value_sha256: str,
) -> tuple[str, EvidenceAnchor]:
    """Build an exact validator-attested anchor in an evidence file."""

    anchor = _parse_evidence_anchor(
        {
            "id": id,
            "file": file,
            "start_byte": start_byte,
            "end_byte": end_byte,
            "ir_pointer": ir_pointer,
            "representation": representation,
            "value_sha256": value_sha256,
        },
        "$.evidence_anchor",
    )
    return _definition_with_id("anchor", anchor)


def build_source_set(*, package: str, anchors: Iterable[str]) -> tuple[str, SourceSet]:
    """Build a canonical non-empty set of package-local evidence anchors."""

    source_set = _parse_source_set(
        {
            "package": package,
            "anchors": list(itertools.islice(anchors, _MAX_PROVENANCE_REFERENCES + 1)),
        },
        "$.source_set",
    )
    return _definition_with_id("sources", source_set)


def build_evidence_binding(
    *, target: str, source_sets: Iterable[str]
) -> tuple[str, EvidenceBinding]:
    """Build a canonical evidence binding for one semantic JSON leaf."""

    binding = _parse_evidence_binding(
        {
            "target": target,
            "source_sets": list(itertools.islice(source_sets, _MAX_PROVENANCE_REFERENCES + 1)),
        },
        "$.evidence_binding",
    )
    return _definition_with_id("evidence", binding)


def loads_ir(
    payload: str | bytes, *, trusted_receipts: Mapping[str, str] | None = None
) -> ProtocolIRDocument:
    """Load and strictly validate a canonical IR document."""

    raw, _encoded = _decode_strict_json(payload, max_bytes=_MAX_IR_BYTES)
    return parse_ir(raw, trusted_receipts=trusted_receipts)


def _decode_strict_json(payload: str | bytes, *, max_bytes: int) -> tuple[object, bytes]:
    if isinstance(payload, str):
        try:
            encoded_payload = payload.encode("utf-8")
        except UnicodeEncodeError as err:
            raise IRValidationError(
                (IRDiagnostic("invalid_unicode", "$", "input contains an unpaired surrogate"),)
            ) from err
    else:
        encoded_payload = payload
    if len(encoded_payload) > max_bytes:
        _fail(
            "input_too_large",
            "$",
            f"JSON input has {len(encoded_payload)} bytes; limit is {max_bytes}",
        )
    try:
        raw = json.loads(
            encoded_payload,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_number,
            parse_float=_parse_finite_float,
        )
    except _DuplicateKeyError as err:
        raise IRValidationError(
            (
                IRDiagnostic(
                    "duplicate_object_key",
                    "$",
                    f"JSON object key {err.key!r} appears more than once",
                ),
            )
        ) from err
    except _NonFiniteNumberError as err:
        raise IRValidationError(
            (
                IRDiagnostic(
                    "non_finite_number",
                    "$",
                    f"JSON number {err.value!r} is not finite",
                ),
            )
        ) from err
    except RecursionError as err:
        raise IRValidationError(
            (IRDiagnostic("json_too_deep", "$", f"JSON nesting exceeds {_MAX_JSON_DEPTH}"),)
        ) from err
    except (json.JSONDecodeError, UnicodeDecodeError, OverflowError, ValueError) as err:
        raise IRValidationError((IRDiagnostic("invalid_json", "$", str(err)),)) from err
    _validate_json_shape_bounds(raw)
    return raw, encoded_payload


def load_ir(path: Path, *, trusted_receipts: Mapping[str, str] | None = None) -> ProtocolIRDocument:
    """Load an IR document from disk without modifying it."""

    with path.open("rb") as source:
        payload = source.read(_MAX_IR_BYTES + 1)
    return loads_ir(payload, trusted_receipts=trusted_receipts)


def parse_ir(
    raw: object, *, trusted_receipts: Mapping[str, str] | None = None
) -> ProtocolIRDocument:
    """Parse and authorize an IR against caller-trusted validator receipts."""

    return _parse_ir(raw, trusted_receipts=trusted_receipts, authorize=True)


def _parse_ir_structure(raw: object) -> ProtocolIRDocument:
    """Parse structure for the validator without authorizing provenance."""

    return _parse_ir(raw, trusted_receipts=None, authorize=False)


def _parse_ir(
    raw: object, *, trusted_receipts: Mapping[str, str] | None, authorize: bool
) -> ProtocolIRDocument:

    _validate_json_shape_bounds(raw)
    root = _expect_object(raw, "$")
    _expect_keys(
        root,
        path="$",
        required={
            "schema_revision",
            "source_packages",
            "evidence_files",
            "evidence_anchors",
            "source_sets",
            "evidence_bindings",
            "variant_spaces",
            "protocols",
            "actions",
            "expected_action_rules",
            "command_bindings",
        },
    )
    revision = _expect_string(root["schema_revision"], "$.schema_revision")
    if revision != SCHEMA_REVISION:
        _fail(
            "unsupported_schema_revision",
            "$.schema_revision",
            f"expected {SCHEMA_REVISION!r}, got {revision!r}",
        )

    _validate_raw_provenance_bounds(root)
    source_packages = _parse_definition_map(
        root["source_packages"],
        "$.source_packages",
        _parse_source_package,
        limit=_MAX_PROVENANCE_DEFINITIONS,
    )
    evidence_files = _parse_definition_map(
        root["evidence_files"],
        "$.evidence_files",
        _parse_evidence_file,
        limit=_MAX_PROVENANCE_DEFINITIONS,
    )
    evidence_anchors = _parse_definition_map(
        root["evidence_anchors"],
        "$.evidence_anchors",
        _parse_evidence_anchor,
        limit=_MAX_PROVENANCE_DEFINITIONS,
    )
    source_sets = _parse_definition_map(
        root["source_sets"],
        "$.source_sets",
        _parse_source_set,
        limit=_MAX_PROVENANCE_DEFINITIONS,
    )
    evidence_bindings = _parse_definition_map(
        root["evidence_bindings"],
        "$.evidence_bindings",
        _parse_evidence_binding,
        limit=_MAX_PROVENANCE_DEFINITIONS,
    )
    variant_spaces = _parse_definition_map(
        root["variant_spaces"], "$.variant_spaces", _parse_variant_space
    )
    protocols = _parse_definition_map(root["protocols"], "$.protocols", _parse_protocol)
    actions = _parse_definition_map(root["actions"], "$.actions", _parse_action)
    expected_rules = _parse_definition_map(
        root["expected_action_rules"],
        "$.expected_action_rules",
        _parse_expected_rule,
    )
    bindings = _parse_definition_map(root["command_bindings"], "$.command_bindings", _parse_binding)

    document = ProtocolIRDocument(
        schema_revision=revision,
        source_packages=source_packages,
        evidence_files=evidence_files,
        evidence_anchors=evidence_anchors,
        source_sets=source_sets,
        evidence_bindings=evidence_bindings,
        variant_spaces=variant_spaces,
        protocols=protocols,
        actions=actions,
        expected_action_rules=expected_rules,
        command_bindings=bindings,
    )
    _validate_provenance(document)
    _validate_references_and_predicates(document)
    if authorize:
        _validate_trusted_receipts(document, trusted_receipts)
        _validate_exact_evidence_coverage(document)
    return document


def dumps_ir(document: ProtocolIRDocument) -> bytes:
    """Serialize an IR document to stable canonical UTF-8 JSON."""

    return _canonical_json(document.to_data()) + b"\n"


def semantic_fingerprint(document: ProtocolIRDocument) -> str:
    """Return a stable SHA-256 fingerprint of normalized semantic content."""

    return hashlib.sha256(
        _canonical_json(
            {
                "schema_revision": document.schema_revision,
                **_semantic_data(document),
            }
        )
    ).hexdigest()


def validate_universe(document: ProtocolIRDocument) -> UniverseValidation:
    """Compare expected action coverage with the command-binding multiset."""

    spaces = dict(document.variant_spaces)
    profiles_by_protocol = {
        protocol_id: spaces[protocol.variant_space].profiles()
        for protocol_id, protocol in document.protocols
    }

    expected: set[UniverseKey] = set()
    for _rule_id, rule in document.expected_action_rules:
        for profile in profiles_by_protocol[rule.protocol]:
            if rule.when.matches(dict(profile)):
                expected.add(UniverseKey(rule.protocol, rule.action, profile))

    binding_coverage: dict[str, frozenset[UniverseKey]] = {}
    actual_sources: defaultdict[UniverseKey, list[str]] = defaultdict(list)
    for binding_id, binding in document.command_bindings:
        covered = frozenset(
            UniverseKey(binding.protocol, binding.action, profile)
            for profile in profiles_by_protocol[binding.protocol]
            if binding.when.matches(dict(profile))
        )
        binding_coverage[binding_id] = covered
        for key in covered:
            actual_sources[key].append(binding_id)

    actual = set(actual_sources)
    issues: list[UniverseIssue] = []
    for key in sorted(expected - actual, key=_universe_sort_key):
        issues.append(UniverseIssue("missing_binding", key))
    for key in sorted(actual - expected, key=_universe_sort_key):
        issues.append(UniverseIssue("extra_binding", key, tuple(sorted(actual_sources[key]))))

    coverage_groups: defaultdict[frozenset[UniverseKey], list[str]] = defaultdict(list)
    for binding_id, coverage in binding_coverage.items():
        if not coverage:
            issues.append(UniverseIssue("empty_binding", None, (binding_id,)))
        else:
            coverage_groups[coverage].append(binding_id)

    for coverage, binding_ids in coverage_groups.items():
        if len(binding_ids) > 1:
            issues.append(
                UniverseIssue(
                    "duplicate_binding_coverage",
                    min(coverage, key=_universe_sort_key),
                    tuple(sorted(binding_ids)),
                )
            )

    overlap_keys: defaultdict[tuple[str, ...], list[UniverseKey]] = defaultdict(list)
    for key, binding_ids in actual_sources.items():
        coverage_sets = {binding_coverage[binding_id] for binding_id in binding_ids}
        overlap_group = tuple(sorted(binding_ids))
        if len(coverage_sets) > 1:
            overlap_keys[overlap_group].append(key)
    for overlap_group, keys in overlap_keys.items():
        issues.append(
            UniverseIssue(
                "overlapping_binding_coverage",
                min(keys, key=_universe_sort_key),
                overlap_group,
            )
        )

    issues.sort(
        key=lambda issue: (
            issue.code,
            _universe_sort_key(issue.key) if issue.key is not None else ("", "", b""),
            issue.binding_ids,
        )
    )
    return UniverseValidation(
        expected=frozenset(expected),
        actual=frozenset(actual),
        issues=tuple(issues),
    )


def _validate_raw_provenance_bounds(root: Mapping[str, object]) -> None:
    definition_count = 0
    for name in (
        "source_packages",
        "evidence_files",
        "evidence_anchors",
        "source_sets",
        "evidence_bindings",
    ):
        raw_collection = root[name]
        if isinstance(raw_collection, dict):
            definition_count += len(raw_collection)
    if definition_count > _MAX_PROVENANCE_DEFINITIONS:
        _fail(
            "provenance_graph_too_large",
            "$",
            f"provenance graph has {definition_count} definitions; "
            f"limit is {_MAX_PROVENANCE_DEFINITIONS}",
        )

    edge_count = 0
    for collection_name, property_name in (
        ("source_sets", "anchors"),
        ("evidence_bindings", "source_sets"),
    ):
        raw_collection = root[collection_name]
        if not isinstance(raw_collection, dict):
            continue
        for definition in raw_collection.values():
            if not isinstance(definition, dict):
                continue
            references = definition.get(property_name)
            if isinstance(references, list):
                edge_count += len(references)
                if edge_count > _MAX_PROVENANCE_EDGES:
                    _fail(
                        "provenance_graph_too_large",
                        f"$.{collection_name}",
                        f"provenance graph has more than {_MAX_PROVENANCE_EDGES} references",
                    )


def _validate_json_shape_bounds(raw: object) -> None:
    stack: list[tuple[object, int]] = [(raw, 0)]
    seen_containers: set[int] = set()
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            _fail(
                "json_structure_too_large",
                "$",
                f"JSON structure has more than {_MAX_JSON_NODES} values",
            )
        if depth > _MAX_JSON_DEPTH:
            _fail(
                "json_too_deep",
                "$",
                f"JSON nesting exceeds {_MAX_JSON_DEPTH}",
            )
        if isinstance(value, dict):
            identity = id(value)
            if identity in seen_containers:
                _fail("invalid_json_structure", "$", "JSON structure contains a cycle or alias")
            seen_containers.add(identity)
            stack.extend((key, depth + 1) for key in value)
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            identity = id(value)
            if identity in seen_containers:
                _fail("invalid_json_structure", "$", "JSON structure contains a cycle or alias")
            seen_containers.add(identity)
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is int:
            integer = cast(int, value)
            if not _MIN_INTEGER <= integer <= _MAX_INTEGER:
                _fail(
                    "integer_out_of_range",
                    "$",
                    f"JSON integers must be between {_MIN_INTEGER} and {_MAX_INTEGER}",
                )
        elif isinstance(value, float):
            if not math.isfinite(value):
                _fail("non_finite_number", "$", "JSON number is not finite")
        elif isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                _fail("invalid_unicode", "$", "JSON string contains an unpaired surrogate")
        elif value is not None and type(value) not in {str, bool}:
            _fail(
                "invalid_json_structure",
                "$",
                f"value of type {type(value).__name__!r} is not JSON-compatible",
            )


def _parse_artifact_identity(raw: object, path: str) -> ArtifactIdentity:
    value = _expect_object(raw, path)
    _expect_keys(
        value,
        path=path,
        required={
            "package_name",
            "version_code",
            "version_name",
            "artifact_digest",
        },
    )
    package_name = _expect_string(value["package_name"], f"{path}.package_name")
    if not _PACKAGE_ID_PATTERN.fullmatch(package_name):
        _fail(
            "invalid_package_id",
            f"{path}.package_name",
            f"package name {package_name!r} is not a dotted package identifier",
        )
    return ArtifactIdentity(
        package_name=package_name,
        version_code=_expect_nonempty_string(
            value["version_code"], f"{path}.version_code", max_length=256
        ),
        version_name=_expect_nonempty_string(
            value["version_name"], f"{path}.version_name", max_length=256
        ),
        artifact_digest=_expect_sha256(value["artifact_digest"], f"{path}.artifact_digest"),
    )


def _bind_receipt_data(
    receipt: dict[str, object],
    *,
    trusted_validator_revision: str,
    trusted_contract_revision: str,
    trusted_dependency_digests: tuple[tuple[str, str], ...],
    trusted_receipt_sha256: str,
) -> ValidatedReport:
    required = {
        "accepted",
        "bundle_sha256",
        "contract_revision",
        "declared_members",
        "dependency_digests",
        "diagnostics",
        "discovered_members",
        "evidence_anchors_checked",
        "report_manifest_sha256",
        "source_unchanged",
        "validated_artifact_identity",
        "validated_evidence_anchors",
        "validated_evidence_members",
        "validation_profile",
        "validation_receipt_sha256",
        "validator_revision",
    }
    _expect_keys(receipt, path="$.receipt", required=required)
    if not _expect_bool(receipt["accepted"], "$.receipt.accepted"):
        _fail("validator_rejected", "$.receipt.accepted", "validator receipt was not accepted")
    if not _expect_bool(receipt["source_unchanged"], "$.receipt.source_unchanged"):
        _fail(
            "validator_source_changed",
            "$.receipt.source_unchanged",
            "validator source was not unchanged",
        )
    diagnostics = _expect_array(receipt["diagnostics"], "$.receipt.diagnostics")
    if diagnostics:
        _fail(
            "accepted_receipt_has_diagnostics",
            "$.receipt.diagnostics",
            "an accepted validator receipt must have no diagnostics",
        )
    discovered = _expect_integer(
        receipt["discovered_members"], "$.receipt.discovered_members", minimum=0
    )
    declared = _expect_integer(receipt["declared_members"], "$.receipt.declared_members", minimum=0)
    if discovered != declared:
        _fail(
            "receipt_member_count_mismatch",
            "$.receipt",
            "accepted receipt discovered and declared member counts differ",
        )

    validator_revision = _expect_nonempty_string(
        receipt["validator_revision"], "$.receipt.validator_revision", max_length=256
    )
    contract_revision = _expect_nonempty_string(
        receipt["contract_revision"], "$.receipt.contract_revision", max_length=256
    )
    profile = _expect_nonempty_string(
        receipt["validation_profile"], "$.receipt.validation_profile", max_length=64
    )
    if profile != BOUND_VALIDATION_PROFILE:
        _fail(
            "unbound_validation_profile",
            "$.receipt.validation_profile",
            f"only {BOUND_VALIDATION_PROFILE!r} receipts may bind provenance",
        )
    if validator_revision != trusted_validator_revision:
        _fail(
            "validator_revision_mismatch",
            "$.receipt.validator_revision",
            "receipt validator revision does not match caller trust",
        )
    if contract_revision != trusted_contract_revision:
        _fail(
            "contract_revision_mismatch",
            "$.receipt.contract_revision",
            "receipt contract revision does not match caller trust",
        )
    dependencies = _parse_dependency_digests(
        receipt["dependency_digests"], "$.receipt.dependency_digests"
    )
    if dependencies != trusted_dependency_digests:
        _fail(
            "dependency_pin_mismatch",
            "$.receipt.dependency_digests",
            "receipt dependency pins do not match caller trust",
        )

    embedded_receipt_sha256 = _expect_sha256(
        receipt["validation_receipt_sha256"], "$.receipt.validation_receipt_sha256"
    )
    identity_input = dict(receipt)
    del identity_input["validation_receipt_sha256"]
    computed_receipt_sha256 = hashlib.sha256(_canonical_json(identity_input)).hexdigest()
    if embedded_receipt_sha256 != computed_receipt_sha256:
        _fail(
            "receipt_identity_mismatch",
            "$.receipt.validation_receipt_sha256",
            "embedded receipt identity does not reproduce from canonical receipt content",
        )
    if embedded_receipt_sha256 != trusted_receipt_sha256:
        _fail(
            "receipt_trust_mismatch",
            "$.receipt.validation_receipt_sha256",
            "receipt identity does not match caller trust",
        )

    report = _parse_validated_report(
        {
            "bundle_sha256": receipt["bundle_sha256"],
            "contract_revision": contract_revision,
            "declared_members": declared,
            "dependency_digests": dict(dependencies),
            "discovered_members": discovered,
            "evidence_anchors_checked": receipt["evidence_anchors_checked"],
            "report_manifest_sha256": receipt["report_manifest_sha256"],
            "validated_artifact_identity": receipt["validated_artifact_identity"],
            "validated_evidence_anchors": receipt["validated_evidence_anchors"],
            "validated_evidence_members": receipt["validated_evidence_members"],
            "validation_profile": profile,
            "validation_receipt_sha256": embedded_receipt_sha256,
            "validator_revision": validator_revision,
        },
        "$.receipt",
    )
    checked = _expect_integer(
        receipt["evidence_anchors_checked"],
        "$.receipt.evidence_anchors_checked",
        minimum=0,
    )
    if checked != len(report.validated_evidence_anchors):
        _fail(
            "receipt_anchor_count_mismatch",
            "$.receipt.evidence_anchors_checked",
            "checked anchor count does not equal retained anchor attestations",
        )
    return report


def _parse_dependency_digests(raw: object, path: str) -> tuple[tuple[str, str], ...]:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required=set(_DEPENDENCY_NAMES))
    return tuple(
        (name, _expect_sha256(value[name], f"{path}.{name}")) for name in _DEPENDENCY_NAMES
    )


def _parse_attested_member(raw: object, path: str) -> AttestedEvidenceMember:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"member", "owner", "sha256"})
    member = _expect_nonempty_string(
        value["member"], f"{path}.member", max_length=_MAX_REPORT_PATH_LENGTH
    )
    _validate_report_member_path(member, f"{path}.member")
    return AttestedEvidenceMember(
        member=member,
        owner=_expect_sha256(value["owner"], f"{path}.owner"),
        sha256=_expect_sha256(value["sha256"], f"{path}.sha256"),
    )


def _parse_attested_anchor(raw: object, path: str) -> AttestedEvidenceAnchor:
    value = _expect_object(raw, path)
    _expect_keys(
        value,
        path=path,
        required={
            "id",
            "owner",
            "member",
            "member_sha256",
            "start_byte",
            "end_byte",
            "ir_pointer",
            "representation",
            "value_sha256",
        },
    )
    member = _expect_nonempty_string(
        value["member"], f"{path}.member", max_length=_MAX_REPORT_PATH_LENGTH
    )
    _validate_report_member_path(member, f"{path}.member")
    start = _expect_integer(value["start_byte"], f"{path}.start_byte", minimum=0)
    end = _expect_integer(value["end_byte"], f"{path}.end_byte", minimum=start + 1)
    pointer = _expect_string(value["ir_pointer"], f"{path}.ir_pointer")
    _validate_json_pointer(pointer, f"{path}.ir_pointer", allow_root=False)
    representation = _expect_string(value["representation"], f"{path}.representation")
    if representation not in {"hex", "utf8"}:
        _fail(
            "unknown_evidence_representation",
            f"{path}.representation",
            "representation must be 'hex' or 'utf8'",
        )
    return AttestedEvidenceAnchor(
        id=_expect_nonempty_string(value["id"], f"{path}.id", max_length=256),
        owner=_expect_sha256(value["owner"], f"{path}.owner"),
        member=member,
        member_sha256=_expect_sha256(value["member_sha256"], f"{path}.member_sha256"),
        start_byte=start,
        end_byte=end,
        ir_pointer=pointer,
        representation=representation,
        value_sha256=_expect_sha256(value["value_sha256"], f"{path}.value_sha256"),
    )


def _parse_attested_members(raw: object, path: str) -> tuple[AttestedEvidenceMember, ...]:
    values = _expect_array(raw, path)
    _expect_bounded_nonempty_array(values, path)
    members = tuple(
        sorted(
            (_parse_attested_member(item, f"{path}[{index}]") for index, item in enumerate(values)),
            key=lambda member: _canonical_json(member.to_data()),
        )
    )
    member_paths = [member.member for member in members]
    if len(set(member_paths)) != len(member_paths):
        _fail("duplicate_attested_member", path, "attested member paths must be unique")
    return members


def _parse_attested_anchors(raw: object, path: str) -> tuple[AttestedEvidenceAnchor, ...]:
    values = _expect_array(raw, path)
    _expect_bounded_nonempty_array(values, path)
    anchors = tuple(
        sorted(
            (_parse_attested_anchor(item, f"{path}[{index}]") for index, item in enumerate(values)),
            key=lambda anchor: anchor.id.encode("utf-8"),
        )
    )
    anchor_ids = [anchor.id for anchor in anchors]
    if len(set(anchor_ids)) != len(anchor_ids):
        _fail("duplicate_attested_anchor", path, "attested anchor IDs must be unique")
    return anchors


def _parse_validated_report(raw: object, path: str) -> ValidatedReport:
    value = _expect_object(raw, path)
    _expect_keys(
        value,
        path=path,
        required={
            "validator_revision",
            "contract_revision",
            "validation_profile",
            "validation_receipt_sha256",
            "bundle_sha256",
            "report_manifest_sha256",
            "discovered_members",
            "declared_members",
            "evidence_anchors_checked",
            "validated_artifact_identity",
            "dependency_digests",
            "validated_evidence_members",
            "validated_evidence_anchors",
        },
    )
    report = ValidatedReport(
        validator_revision=_expect_nonempty_string(
            value["validator_revision"], f"{path}.validator_revision", max_length=256
        ),
        contract_revision=_expect_nonempty_string(
            value["contract_revision"], f"{path}.contract_revision", max_length=256
        ),
        validation_profile=_expect_nonempty_string(
            value["validation_profile"], f"{path}.validation_profile", max_length=64
        ),
        validation_receipt_sha256=_expect_sha256(
            value["validation_receipt_sha256"], f"{path}.validation_receipt_sha256"
        ),
        bundle_sha256=_expect_sha256(value["bundle_sha256"], f"{path}.bundle_sha256"),
        report_manifest_sha256=_expect_sha256(
            value["report_manifest_sha256"], f"{path}.report_manifest_sha256"
        ),
        discovered_members=_expect_integer(
            value["discovered_members"], f"{path}.discovered_members", minimum=0
        ),
        declared_members=_expect_integer(
            value["declared_members"], f"{path}.declared_members", minimum=0
        ),
        evidence_anchors_checked=_expect_integer(
            value["evidence_anchors_checked"], f"{path}.evidence_anchors_checked", minimum=0
        ),
        validated_artifact_identity=_parse_artifact_identity(
            value["validated_artifact_identity"], f"{path}.validated_artifact_identity"
        ),
        dependency_digests=_parse_dependency_digests(
            value["dependency_digests"], f"{path}.dependency_digests"
        ),
        validated_evidence_members=_parse_attested_members(
            value["validated_evidence_members"], f"{path}.validated_evidence_members"
        ),
        validated_evidence_anchors=_parse_attested_anchors(
            value["validated_evidence_anchors"], f"{path}.validated_evidence_anchors"
        ),
    )
    _validate_report_attestations(report, path)
    return report


def _validate_report_attestations(report: ValidatedReport, path: str) -> None:
    if report.validator_revision != SUPPORTED_VALIDATOR_REVISION:
        _fail(
            "unsupported_validator_revision",
            f"{path}.validator_revision",
            f"supported validator revision is {SUPPORTED_VALIDATOR_REVISION!r}",
        )
    if report.contract_revision != SUPPORTED_CONTRACT_REVISION:
        _fail(
            "unsupported_contract_revision",
            f"{path}.contract_revision",
            f"supported contract revision is {SUPPORTED_CONTRACT_REVISION!r}",
        )
    if report.validation_profile != BOUND_VALIDATION_PROFILE:
        _fail(
            "unbound_validation_profile",
            f"{path}.validation_profile",
            f"only {BOUND_VALIDATION_PROFILE!r} receipts may bind provenance",
        )
    if report.discovered_members != report.declared_members:
        _fail(
            "receipt_member_count_mismatch",
            path,
            "accepted receipt discovered and declared member counts differ",
        )
    if report.evidence_anchors_checked != len(report.validated_evidence_anchors):
        _fail(
            "receipt_anchor_count_mismatch",
            f"{path}.evidence_anchors_checked",
            "checked anchor count does not equal retained anchor attestations",
        )
    owner = report.validated_artifact_identity.artifact_digest
    members = {member.member: member for member in report.validated_evidence_members}
    for index, member in enumerate(report.validated_evidence_members):
        if member.owner != owner:
            _fail(
                "attested_member_owner_mismatch",
                f"{path}.validated_evidence_members[{index}].owner",
                "attested member owner does not match the artifact identity",
            )
    for index, anchor in enumerate(report.validated_evidence_anchors):
        member = members.get(anchor.member)
        if member is None:
            _fail(
                "attested_anchor_member_missing",
                f"{path}.validated_evidence_anchors[{index}].member",
                "attested anchor member is absent from the attested member set",
            )
        if anchor.owner != owner or anchor.owner != member.owner:
            _fail(
                "attested_anchor_owner_mismatch",
                f"{path}.validated_evidence_anchors[{index}].owner",
                "attested anchor owner does not match its member and artifact identity",
            )
        if anchor.member_sha256 != member.sha256:
            _fail(
                "attested_anchor_digest_mismatch",
                f"{path}.validated_evidence_anchors[{index}].member_sha256",
                "attested anchor member digest does not match its attested member",
            )
    reproduced_identity = hashlib.sha256(
        _canonical_json(_validated_report_identity_input(report))
    ).hexdigest()
    if reproduced_identity != report.validation_receipt_sha256:
        _fail(
            "receipt_identity_mismatch",
            f"{path}.validation_receipt_sha256",
            "receipt identity does not reproduce from retained exact receipt facts",
        )


def _validated_report_identity_input(report: ValidatedReport) -> dict[str, object]:
    return {
        "accepted": True,
        "bundle_sha256": report.bundle_sha256,
        "contract_revision": report.contract_revision,
        "declared_members": report.declared_members,
        "dependency_digests": dict(report.dependency_digests),
        "diagnostics": [],
        "discovered_members": report.discovered_members,
        "evidence_anchors_checked": report.evidence_anchors_checked,
        "report_manifest_sha256": report.report_manifest_sha256,
        "source_unchanged": True,
        "validated_artifact_identity": report.validated_artifact_identity.to_data(),
        "validated_evidence_anchors": [
            anchor.to_data() for anchor in report.validated_evidence_anchors
        ],
        "validated_evidence_members": [
            member.to_data() for member in report.validated_evidence_members
        ],
        "validation_profile": report.validation_profile,
        "validator_revision": report.validator_revision,
    }


def _parse_source_package(raw: object, path: str) -> SourcePackage:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"artifact", "report"})
    artifact = _parse_artifact_identity(value["artifact"], f"{path}.artifact")
    report = _parse_validated_report(value["report"], f"{path}.report")
    if artifact != report.validated_artifact_identity:
        _fail(
            "artifact_identity_attestation_mismatch",
            f"{path}.artifact",
            "source artifact identity does not match the validator attestation",
        )
    return SourcePackage(artifact=artifact, report=report)


def _parse_evidence_file(raw: object, path: str) -> EvidenceFile:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"package", "member", "sha256"})
    member = _expect_nonempty_string(
        value["member"], f"{path}.member", max_length=_MAX_REPORT_PATH_LENGTH
    )
    _validate_report_member_path(member, f"{path}.member")
    if member == "REPORT.SHA256":
        _fail(
            "manifest_is_not_evidence_member",
            f"{path}.member",
            "REPORT.SHA256 is bound by the package report identity, not as evidence",
        )
    return EvidenceFile(
        package=_expect_reference(value["package"], f"{path}.package"),
        member=member,
        sha256=_expect_sha256(value["sha256"], f"{path}.sha256"),
    )


def _parse_evidence_anchor(raw: object, path: str) -> EvidenceAnchor:
    value = _expect_object(raw, path)
    _expect_keys(
        value,
        path=path,
        required={
            "id",
            "file",
            "start_byte",
            "end_byte",
            "ir_pointer",
            "representation",
            "value_sha256",
        },
    )
    start = _expect_integer(value["start_byte"], f"{path}.start_byte", minimum=0)
    end = _expect_integer(value["end_byte"], f"{path}.end_byte", minimum=start + 1)
    pointer = _expect_string(value["ir_pointer"], f"{path}.ir_pointer")
    _validate_json_pointer(pointer, f"{path}.ir_pointer", allow_root=False)
    representation = _expect_string(value["representation"], f"{path}.representation")
    if representation not in {"hex", "utf8"}:
        _fail(
            "unknown_evidence_representation",
            f"{path}.representation",
            "representation must be 'hex' or 'utf8'",
        )
    return EvidenceAnchor(
        id=_expect_nonempty_string(value["id"], f"{path}.id", max_length=256),
        file=_expect_reference(value["file"], f"{path}.file"),
        start_byte=start,
        end_byte=end,
        ir_pointer=pointer,
        representation=representation,
        value_sha256=_expect_sha256(value["value_sha256"], f"{path}.value_sha256"),
    )


def _parse_source_set(raw: object, path: str) -> SourceSet:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"package", "anchors"})
    anchors = _parse_reference_set(value["anchors"], f"{path}.anchors")
    return SourceSet(
        package=_expect_reference(value["package"], f"{path}.package"),
        anchors=anchors,
    )


def _parse_evidence_binding(raw: object, path: str) -> EvidenceBinding:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"target", "source_sets"})
    target = _expect_string(value["target"], f"{path}.target")
    _validate_json_pointer(target, f"{path}.target", allow_root=False)
    return EvidenceBinding(
        target=target,
        source_sets=_parse_reference_set(value["source_sets"], f"{path}.source_sets"),
    )


def _parse_variant_space(raw: object, path: str) -> VariantSpace:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"dimensions", "constraints"})
    raw_dimensions = _expect_object(value["dimensions"], f"{path}.dimensions")
    if len(raw_dimensions) > _MAX_VARIANT_DIMENSIONS:
        _fail(
            "variant_space_too_large",
            f"{path}.dimensions",
            f"variant space has {len(raw_dimensions)} dimensions; "
            f"limit is {_MAX_VARIANT_DIMENSIONS}",
        )
    dimensions: list[tuple[str, tuple[JsonScalar, ...]]] = []
    for name in sorted(raw_dimensions):
        _validate_id(name, f"{path}.dimensions")
        raw_values = _expect_array(raw_dimensions[name], f"{path}.dimensions.{name}")
        if not raw_values:
            _fail(
                "empty_dimension",
                f"{path}.dimensions.{name}",
                "a selector dimension must declare at least one value",
            )
        if len(raw_values) > _MAX_VARIANT_PROFILES:
            _fail(
                "variant_space_too_large",
                f"{path}.dimensions.{name}",
                f"dimension has {len(raw_values)} values; limit is {_MAX_VARIANT_PROFILES}",
            )
        parsed_values = tuple(
            _expect_scalar(item, f"{path}.dimensions.{name}[{index}]")
            for index, item in enumerate(raw_values)
        )
        sorted_values = tuple(sorted(parsed_values, key=_scalar_sort_key))
        if len({_scalar_sort_key(item) for item in sorted_values}) != len(sorted_values):
            _fail(
                "duplicate_dimension_value",
                f"{path}.dimensions.{name}",
                "selector dimension values must be unique",
            )
        dimensions.append((name, sorted_values))

    raw_constraints = _expect_array(value["constraints"], f"{path}.constraints")
    constraints = tuple(
        sorted(
            (
                _parse_predicate(item, f"{path}.constraints[{index}]")
                for index, item in enumerate(raw_constraints)
            ),
            key=lambda predicate: _canonical_json(predicate.to_data()),
        )
    )
    return VariantSpace(tuple(dimensions), constraints)


def _parse_protocol(raw: object, path: str) -> ProtocolDefinition:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"variant_space"})
    return ProtocolDefinition(
        variant_space=_expect_reference(value["variant_space"], f"{path}.variant_space")
    )


def _parse_action(raw: object, path: str) -> ActionDefinition:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required=set(), optional={"summary"})
    summary = _expect_string(value["summary"], f"{path}.summary") if "summary" in value else None
    if summary == "":
        _fail("empty_string", f"{path}.summary", "summary must not be empty")
    return ActionDefinition(summary=summary)


def _parse_expected_rule(raw: object, path: str) -> ExpectedActionRule:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"protocol", "action", "when"})
    return ExpectedActionRule(
        protocol=_expect_reference(value["protocol"], f"{path}.protocol"),
        action=_expect_reference(value["action"], f"{path}.action"),
        when=_parse_predicate(value["when"], f"{path}.when"),
    )


def _parse_binding(raw: object, path: str) -> CommandBinding:
    value = _expect_object(raw, path)
    _expect_keys(value, path=path, required={"protocol", "action", "when"})
    return CommandBinding(
        protocol=_expect_reference(value["protocol"], f"{path}.protocol"),
        action=_expect_reference(value["action"], f"{path}.action"),
        when=_parse_predicate(value["when"], f"{path}.when"),
    )


def _parse_predicate(raw: object, path: str) -> Predicate:
    value = _expect_object(raw, path)
    op = _expect_string(value.get("op"), f"{path}.op")
    if op in {"always", "never"}:
        _expect_keys(value, path=path, required={"op"})
        return Predicate(op)
    if op == "eq":
        _expect_keys(value, path=path, required={"op", "dimension", "value"})
        return Predicate(
            op,
            dimension=_expect_reference(value["dimension"], f"{path}.dimension"),
            value=_expect_scalar(value["value"], f"{path}.value"),
        )
    if op == "in":
        _expect_keys(value, path=path, required={"op", "dimension", "values"})
        raw_values = _expect_array(value["values"], f"{path}.values")
        if not raw_values:
            _fail("empty_predicate_values", f"{path}.values", "values must not be empty")
        values = tuple(
            sorted(
                (
                    _expect_scalar(item, f"{path}.values[{index}]")
                    for index, item in enumerate(raw_values)
                ),
                key=_scalar_sort_key,
            )
        )
        if len({_scalar_sort_key(item) for item in values}) != len(values):
            _fail(
                "duplicate_predicate_value",
                f"{path}.values",
                "predicate values must be unique",
            )
        return Predicate(
            op,
            dimension=_expect_reference(value["dimension"], f"{path}.dimension"),
            values=values,
        )
    if op in {"all", "any"}:
        _expect_keys(value, path=path, required={"op", "terms"})
        raw_terms = _expect_array(value["terms"], f"{path}.terms")
        if not raw_terms:
            _fail("empty_predicate_terms", f"{path}.terms", "terms must not be empty")
        terms = tuple(
            sorted(
                (
                    _parse_predicate(item, f"{path}.terms[{index}]")
                    for index, item in enumerate(raw_terms)
                ),
                key=lambda predicate: _canonical_json(predicate.to_data()),
            )
        )
        return Predicate(op, terms=terms)
    if op == "not":
        _expect_keys(value, path=path, required={"op", "term"})
        return Predicate(op, terms=(_parse_predicate(value["term"], f"{path}.term"),))
    _fail(
        "unknown_predicate_operation",
        f"{path}.op",
        f"unsupported predicate operation {op!r}",
    )


def _validate_provenance(document: ProtocolIRDocument) -> None:
    packages = dict(document.source_packages)
    files = dict(document.evidence_files)
    anchors = dict(document.evidence_anchors)
    source_sets = dict(document.source_sets)
    attested_members_by_package = {
        package_id: {member.member: member for member in package.report.validated_evidence_members}
        for package_id, package in document.source_packages
    }
    attested_anchors_by_package = {
        package_id: {anchor.id: anchor for anchor in package.report.validated_evidence_anchors}
        for package_id, package in document.source_packages
    }
    diagnostics = _BoundedDiagnostics()

    _validate_provenance_expansion_bounds(document)

    for package_id, package in document.source_packages:
        if package.artifact != package.report.validated_artifact_identity:
            diagnostics.append(
                IRDiagnostic(
                    "artifact_identity_attestation_mismatch",
                    f"$.source_packages.{package_id}.artifact",
                    "source artifact identity does not match the validator attestation",
                )
            )

    for collection, prefix in (
        (document.source_packages, "pkg"),
        (document.evidence_files, "file"),
        (document.evidence_anchors, "anchor"),
        (document.source_sets, "sources"),
        (document.evidence_bindings, "evidence"),
    ):
        for identifier, definition in collection:
            expected_id = _content_id(prefix, definition.to_data())
            if identifier != expected_id:
                diagnostics.append(
                    IRDiagnostic(
                        "noncanonical_provenance_id",
                        f"$.{_provenance_collection_name(prefix)}.{identifier}",
                        f"expected content identity {expected_id!r}",
                    )
                )

    member_owners: dict[tuple[str, str], str] = {}
    for file_id, evidence_file in document.evidence_files:
        path = f"$.evidence_files.{file_id}"
        package = packages.get(evidence_file.package)
        if package is None:
            diagnostics.append(
                IRDiagnostic(
                    "unknown_reference",
                    f"{path}.package",
                    f"unknown source package {evidence_file.package!r}",
                )
            )
        else:
            attested = attested_members_by_package[evidence_file.package].get(evidence_file.member)
            if attested is None or attested.sha256 != evidence_file.sha256:
                diagnostics.append(
                    IRDiagnostic(
                        "evidence_member_not_attested",
                        path,
                        "evidence file path and digest do not match an exact receipt attestation",
                    )
                )
        member_key = (evidence_file.package, evidence_file.member)
        prior = member_owners.setdefault(member_key, file_id)
        if prior != file_id:
            diagnostics.append(
                IRDiagnostic(
                    "duplicate_evidence_member",
                    path,
                    f"same package member is also defined by {prior!r}",
                )
            )

    for anchor_id, anchor in document.evidence_anchors:
        evidence_file = files.get(anchor.file)
        if evidence_file is None:
            diagnostics.append(
                IRDiagnostic(
                    "unknown_reference",
                    f"$.evidence_anchors.{anchor_id}.file",
                    f"unknown evidence file {anchor.file!r}",
                )
            )
            continue
        package = packages.get(evidence_file.package)
        if package is None:
            continue
        receipt_anchor = attested_anchors_by_package[evidence_file.package].get(anchor.id)
        if receipt_anchor is None or (
            receipt_anchor.member != evidence_file.member
            or receipt_anchor.member_sha256 != evidence_file.sha256
            or receipt_anchor.start_byte != anchor.start_byte
            or receipt_anchor.end_byte != anchor.end_byte
            or receipt_anchor.ir_pointer != anchor.ir_pointer
            or receipt_anchor.representation != anchor.representation
            or receipt_anchor.value_sha256 != anchor.value_sha256
        ):
            diagnostics.append(
                IRDiagnostic(
                    "evidence_anchor_not_attested",
                    f"$.evidence_anchors.{anchor_id}",
                    "evidence anchor does not match an exact receipt attestation",
                )
            )

    edge_count = 0
    for source_set_id, source_set in document.source_sets:
        base_path = f"$.source_sets.{source_set_id}"
        if source_set.package not in packages:
            diagnostics.append(
                IRDiagnostic(
                    "unknown_reference",
                    f"{base_path}.package",
                    f"unknown source package {source_set.package!r}",
                )
            )
        edge_count += len(source_set.anchors)
        for index, anchor_id in enumerate(source_set.anchors):
            anchor = anchors.get(anchor_id)
            if anchor is None:
                diagnostics.append(
                    IRDiagnostic(
                        "unknown_reference",
                        f"{base_path}.anchors[{index}]",
                        f"unknown evidence anchor {anchor_id!r}",
                    )
                )
                continue
            evidence_file = files.get(anchor.file)
            if evidence_file is not None and evidence_file.package != source_set.package:
                diagnostics.append(
                    IRDiagnostic(
                        "cross_package_source_set",
                        f"{base_path}.anchors[{index}]",
                        f"anchor belongs to package {evidence_file.package!r}, "
                        f"not {source_set.package!r}",
                    )
                )

    semantic_data = _semantic_data(document)
    targets: dict[str, str] = {}
    for binding_id, binding in document.evidence_bindings:
        base_path = f"$.evidence_bindings.{binding_id}"
        edge_count += len(binding.source_sets)
        prior = targets.setdefault(binding.target, binding_id)
        if prior != binding_id:
            diagnostics.append(
                IRDiagnostic(
                    "duplicate_evidence_target",
                    f"{base_path}.target",
                    f"semantic leaf is already bound by {prior!r}",
                )
            )
        try:
            target_value = _resolve_semantic_pointer(semantic_data, binding.target)
        except KeyError, IndexError, TypeError, ValueError:
            diagnostics.append(
                IRDiagnostic(
                    "unknown_evidence_target",
                    f"{base_path}.target",
                    f"target {binding.target!r} does not identify semantic content",
                )
            )
        else:
            if isinstance(target_value, (dict, list)) and target_value:
                diagnostics.append(
                    IRDiagnostic(
                        "evidence_target_not_leaf",
                        f"{base_path}.target",
                        "evidence target must identify a scalar or empty-container semantic leaf",
                    )
                )
            else:
                value_sha256 = hashlib.sha256(_canonical_json(target_value)).hexdigest()
                for source_set_id in binding.source_sets:
                    source_set = source_sets.get(source_set_id)
                    if source_set is None:
                        continue
                    for anchor_id in source_set.anchors:
                        anchor = anchors.get(anchor_id)
                        if anchor is not None and anchor.value_sha256 != value_sha256:
                            diagnostics.append(
                                IRDiagnostic(
                                    "evidence_value_attestation_mismatch",
                                    f"{base_path}.target",
                                    f"anchor {anchor_id!r} does not attest the resolved value",
                                )
                            )
        for index, source_set_id in enumerate(binding.source_sets):
            source_set = source_sets.get(source_set_id)
            if source_set is None:
                diagnostics.append(
                    IRDiagnostic(
                        "unknown_reference",
                        f"{base_path}.source_sets[{index}]",
                        f"unknown source set {source_set_id!r}",
                    )
                )
                continue
            for anchor_id in source_set.anchors:
                anchor = anchors.get(anchor_id)
                if anchor is not None and anchor.ir_pointer != binding.target:
                    diagnostics.append(
                        IRDiagnostic(
                            "evidence_target_attestation_mismatch",
                            f"{base_path}.target",
                            f"anchor {anchor_id!r} attests {anchor.ir_pointer!r}",
                        )
                    )

    if edge_count > _MAX_PROVENANCE_EDGES:
        diagnostics.append(
            IRDiagnostic(
                "provenance_graph_too_large",
                "$.evidence_bindings",
                f"provenance graph has {edge_count} references; limit is {_MAX_PROVENANCE_EDGES}",
            )
        )
    if diagnostics:
        raise IRValidationError(diagnostics)


def _validate_provenance_expansion_bounds(document: ProtocolIRDocument) -> None:
    source_set_sizes = {
        source_set_id: len(source_set.anchors)
        for source_set_id, source_set in document.source_sets
    }
    direct_edges = sum(len(source_set.anchors) for _, source_set in document.source_sets)
    direct_edges += sum(
        len(binding.source_sets) for _, binding in document.evidence_bindings
    )
    if direct_edges > _MAX_PROVENANCE_EDGES:
        _fail(
            "provenance_graph_too_large",
            "$.evidence_bindings",
            f"provenance graph has {direct_edges} references; limit is {_MAX_PROVENANCE_EDGES}",
        )
    expansions = 0
    for _, binding in document.evidence_bindings:
        for source_set_id in binding.source_sets:
            expansions += source_set_sizes.get(source_set_id, 0)
            if expansions > _MAX_PROVENANCE_EXPANSIONS:
                _fail(
                    "provenance_expansion_too_large",
                    "$.evidence_bindings",
                    "binding-to-anchor expansion exceeds "
                    f"{_MAX_PROVENANCE_EXPANSIONS} references",
                )


def _validate_trusted_receipts(
    document: ProtocolIRDocument, trusted_receipts: Mapping[str, str] | None
) -> None:
    trusted = trusted_receipts or {}
    diagnostics = _BoundedDiagnostics()
    for package_id, package in document.source_packages:
        receipt = package.report
        if trusted.get(receipt.validation_receipt_sha256) != receipt.bundle_sha256:
            diagnostics.append(
                IRDiagnostic(
                    "untrusted_validator_receipt",
                    f"$.source_packages.{package_id}.report.validation_receipt_sha256",
                    "receipt identity and bundle digest are not present in the trusted registry",
                )
            )
    if diagnostics:
        raise IRValidationError(diagnostics)


def _validate_exact_evidence_coverage(document: ProtocolIRDocument) -> None:
    expected = set(_semantic_leaf_pointers(_semantic_data(document)))
    actual = {binding.target for _, binding in document.evidence_bindings}
    diagnostics = _BoundedDiagnostics()
    diagnostics.extend(
        IRDiagnostic("missing_evidence_binding", pointer, "semantic leaf has no evidence binding")
        for pointer in sorted(expected - actual)
    )
    diagnostics.extend(
        IRDiagnostic("extra_evidence_binding", pointer, "binding does not identify a semantic leaf")
        for pointer in sorted(actual - expected)
    )
    if diagnostics:
        raise IRValidationError(diagnostics)


def _semantic_leaf_pointers(value: object, pointer: str = "") -> Iterator[str]:
    if isinstance(value, dict):
        if not value and pointer not in _SEMANTIC_COLLECTION_POINTERS:
            yield pointer
            return
        for key in sorted(value):
            escaped = key.replace("~", "~0").replace("/", "~1")
            if _has_semantic_identifier_keys(pointer):
                yield f"{pointer}/{escaped}/@key"
            yield from _semantic_leaf_pointers(value[key], f"{pointer}/{escaped}")
    elif isinstance(value, list):
        if not value:
            yield pointer
            return
        for index, item in enumerate(value):
            yield from _semantic_leaf_pointers(item, f"{pointer}/{index}")
    else:
        yield pointer


_SEMANTIC_COLLECTION_POINTERS = frozenset(
    {
        "/variant_spaces",
        "/protocols",
        "/actions",
        "/expected_action_rules",
        "/command_bindings",
    }
)


def _has_semantic_identifier_keys(pointer: str) -> bool:
    if pointer in _SEMANTIC_COLLECTION_POINTERS:
        return True
    tokens = pointer.split("/")
    return len(tokens) == 4 and tokens[1] == "variant_spaces" and tokens[3] == "dimensions"


def _validate_references_and_predicates(document: ProtocolIRDocument) -> None:
    spaces = dict(document.variant_spaces)
    protocols = dict(document.protocols)
    actions = dict(document.actions)
    diagnostics = _BoundedDiagnostics()

    for space_id, space in document.variant_spaces:
        dimensions = dict(space.dimensions)
        space_diagnostics = _BoundedDiagnostics()
        for index, constraint in enumerate(space.constraints):
            space_diagnostics.extend(
                _predicate_diagnostics(
                    constraint,
                    dimensions,
                    f"$.variant_spaces.{space_id}.constraints[{index}]",
                )
            )
        diagnostics.extend(space_diagnostics)
        profile_count = math.prod(len(values) for values in dimensions.values())
        if profile_count > _MAX_VARIANT_PROFILES:
            diagnostics.append(
                IRDiagnostic(
                    "variant_space_too_large",
                    f"$.variant_spaces.{space_id}",
                    f"declared Cartesian space has {profile_count} profiles; "
                    f"limit is {_MAX_VARIANT_PROFILES}",
                )
            )
        elif not space_diagnostics and not space.profiles():
            diagnostics.append(
                IRDiagnostic(
                    "empty_variant_space",
                    f"$.variant_spaces.{space_id}",
                    "constraints eliminate every declared variant profile",
                )
            )

    for protocol_id, protocol in document.protocols:
        if protocol.variant_space not in spaces:
            diagnostics.append(
                IRDiagnostic(
                    "unknown_reference",
                    f"$.protocols.{protocol_id}.variant_space",
                    f"unknown variant space {protocol.variant_space!r}",
                )
            )

    for collection_name, definitions in (
        ("expected_action_rules", document.expected_action_rules),
        ("command_bindings", document.command_bindings),
    ):
        for identifier, definition in definitions:
            base_path = f"$.{collection_name}.{identifier}"
            if definition.protocol not in protocols:
                diagnostics.append(
                    IRDiagnostic(
                        "unknown_reference",
                        f"{base_path}.protocol",
                        f"unknown protocol {definition.protocol!r}",
                    )
                )
                continue
            if definition.action not in actions:
                diagnostics.append(
                    IRDiagnostic(
                        "unknown_reference",
                        f"{base_path}.action",
                        f"unknown action {definition.action!r}",
                    )
                )
            rule_space = spaces.get(protocols[definition.protocol].variant_space)
            if rule_space is not None:
                diagnostics.extend(
                    _predicate_diagnostics(
                        definition.when,
                        dict(rule_space.dimensions),
                        f"{base_path}.when",
                    )
                )

    if diagnostics:
        raise IRValidationError(diagnostics)


def _predicate_diagnostics(
    predicate: Predicate,
    dimensions: Mapping[str, tuple[JsonScalar, ...]],
    path: str,
) -> tuple[IRDiagnostic, ...]:
    diagnostics = _BoundedDiagnostics()
    if predicate.op in {"eq", "in"}:
        assert predicate.dimension is not None
        domain = dimensions.get(predicate.dimension)
        if domain is None:
            diagnostics.append(
                IRDiagnostic(
                    "unknown_selector_dimension",
                    f"{path}.dimension",
                    f"unknown selector dimension {predicate.dimension!r}",
                )
            )
        else:
            values = (predicate.value,) if predicate.op == "eq" else predicate.values
            domain_keys = {_scalar_sort_key(value) for value in domain}
            for value in values:
                if _scalar_sort_key(cast(JsonScalar, value)) not in domain_keys:
                    diagnostics.append(
                        IRDiagnostic(
                            "selector_value_outside_domain",
                            path,
                            f"value {value!r} is not in dimension {predicate.dimension!r}",
                        )
                    )
    child_label = "term" if predicate.op == "not" else "terms"
    for index, term in enumerate(predicate.terms):
        child_path = (
            f"{path}.{child_label}" if predicate.op == "not" else f"{path}.{child_label}[{index}]"
        )
        diagnostics.extend(_predicate_diagnostics(term, dimensions, child_path))
    return tuple(diagnostics)


def _parse_definition_map[Definition](
    raw: object,
    path: str,
    parser: Callable[[object, str], Definition],
    *,
    limit: int | None = None,
) -> tuple[tuple[str, Definition], ...]:
    value = _expect_object(raw, path)
    if limit is not None and len(value) > limit:
        _fail(
            "definition_map_too_large",
            path,
            f"definition map has {len(value)} entries; limit is {limit}",
        )
    parsed: list[tuple[str, Definition]] = []
    for identifier in sorted(value):
        _validate_id(identifier, path)
        parsed.append(
            (
                identifier,
                parser(value[identifier], f"{path}.{identifier}"),
            )
        )
    return tuple(parsed)


def _expect_object(raw: object, path: str) -> dict[str, object]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        _fail("expected_object", path, "expected a JSON object")
    return cast(dict[str, object], raw)


def _expect_array(raw: object, path: str) -> list[object]:
    if not isinstance(raw, list):
        _fail("expected_array", path, "expected a JSON array")
    return cast(list[object], raw)


def _expect_bounded_nonempty_array(value: list[object], path: str) -> None:
    if not value:
        _fail("empty_attestation_set", path, "at least one attestation is required")
    if len(value) > _MAX_PROVENANCE_REFERENCES:
        _fail(
            "attestation_set_too_large",
            path,
            f"attestation set has {len(value)} entries; limit is {_MAX_PROVENANCE_REFERENCES}",
        )


def _expect_string(raw: object, path: str) -> str:
    if not isinstance(raw, str):
        _fail("expected_string", path, "expected a string")
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError:
        _fail("invalid_unicode", path, "string contains an unpaired surrogate")
    return raw


def _expect_bool(raw: object, path: str) -> bool:
    if type(raw) is not bool:
        _fail("expected_boolean", path, "expected a boolean")
    return cast(bool, raw)


def _expect_nonempty_string(raw: object, path: str, *, max_length: int) -> str:
    value = _expect_string(raw, path)
    if not value:
        _fail("empty_string", path, "value must not be empty")
    if len(value) > max_length:
        _fail(
            "string_too_long",
            path,
            f"value has {len(value)} characters; limit is {max_length}",
        )
    return value


def _expect_sha256(raw: object, path: str) -> str:
    value = _expect_string(raw, path)
    if not _SHA256_PATTERN.fullmatch(value):
        _fail("invalid_sha256", path, "expected exactly 64 lowercase hexadecimal characters")
    return value


def _expect_integer(raw: object, path: str, *, minimum: int) -> int:
    if type(raw) is not int:
        _fail("expected_integer", path, "expected an integer")
    value = cast(int, raw)
    if value < minimum or value > _MAX_INTEGER:
        _fail(
            "integer_out_of_range",
            path,
            f"expected an integer between {minimum} and {_MAX_INTEGER}",
        )
    return value


def _expect_reference(raw: object, path: str) -> str:
    value = _expect_string(raw, path)
    _validate_id(value, path)
    return value


def _parse_reference_set(raw: object, path: str) -> tuple[str, ...]:
    values = _expect_array(raw, path)
    if not values:
        _fail("empty_reference_set", path, "at least one reference is required")
    if len(values) > _MAX_PROVENANCE_REFERENCES:
        _fail(
            "reference_set_too_large",
            path,
            f"reference set has {len(values)} entries; limit is {_MAX_PROVENANCE_REFERENCES}",
        )
    references = tuple(
        sorted(_expect_reference(value, f"{path}[{index}]") for index, value in enumerate(values))
    )
    if len(set(references)) != len(references):
        _fail("duplicate_reference", path, "references must be unique")
    return references


def _expect_scalar(raw: object, path: str) -> JsonScalar:
    if type(raw) not in {str, int, bool}:
        _fail(
            "expected_selector_scalar",
            path,
            "expected a string, integer, or boolean selector value",
        )
    value = cast(JsonScalar, raw)
    if isinstance(value, str):
        _expect_string(value, path)
    return value


def _expect_keys(
    value: Mapping[str, object],
    *,
    path: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - allowed)
    diagnostics = _BoundedDiagnostics()
    diagnostics.extend(
        IRDiagnostic("missing_property", path, f"missing required property {key!r}")
        for key in missing
    )
    diagnostics.extend(
        IRDiagnostic("unknown_property", path, f"unknown property {key!r}") for key in unknown
    )
    if diagnostics:
        raise IRValidationError(diagnostics)


def _validate_id(value: str, path: str) -> None:
    if not _ID_PATTERN.fullmatch(value):
        _fail(
            "invalid_identifier",
            path,
            f"identifier {value!r} does not match {_ID_PATTERN.pattern!r}",
        )


def _validate_report_member_path(value: str, path: str) -> None:
    if "\\" in value or "\x00" in value or "\r" in value or "\n" in value:
        _fail("invalid_report_path", path, "report member path is not canonical POSIX syntax")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or value != candidate.as_posix()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        _fail("invalid_report_path", path, "report member path is not canonical POSIX syntax")


def _validate_json_pointer(value: str, path: str, *, allow_root: bool) -> None:
    if len(value) > _MAX_JSON_POINTER_LENGTH:
        _fail(
            "json_pointer_too_long",
            path,
            f"JSON pointer has {len(value)} characters; limit is {_MAX_JSON_POINTER_LENGTH}",
        )
    if value == "":
        if allow_root:
            return
        _fail("invalid_json_pointer", path, "root JSON pointer is not allowed here")
    if not value.startswith("/"):
        _fail("invalid_json_pointer", path, "JSON pointer must be empty or start with '/'")
    for token in value[1:].split("/"):
        if re.search(r"~(?:[^01]|$)", token):
            _fail("invalid_json_pointer", path, "JSON pointer contains an invalid '~' escape")


def _decode_pointer_token(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _resolve_json_pointer(root: object, pointer: str) -> object:
    current = root
    if pointer == "":
        return current
    for raw_token in pointer[1:].split("/"):
        token = _decode_pointer_token(raw_token)
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            if (
                not token.isascii()
                or not token.isdecimal()
                or (token != "0" and token.startswith("0"))
            ):
                raise IndexError(token)
            current = current[int(token)]
        else:
            raise TypeError(token)
    return current


def _resolve_semantic_pointer(root: object, pointer: str) -> object:
    """Resolve a semantic pointer, including an attested mapping-key leaf."""
    encoded_tokens = pointer[1:].split("/") if pointer.startswith("/") else []
    if len(encoded_tokens) >= 2 and encoded_tokens[-1] == "@key":
        parent_pointer = "/" + "/".join(encoded_tokens[:-2]) if len(encoded_tokens) > 2 else ""
        parent = _resolve_json_pointer(root, parent_pointer)
        key = _decode_pointer_token(encoded_tokens[-2])
        if not isinstance(parent, dict) or key not in parent:
            raise KeyError(key)
        return key
    return _resolve_json_pointer(root, pointer)


def _semantic_data(document: ProtocolIRDocument) -> dict[str, object]:
    data = document.to_data()
    return {
        key: cast(object, data[key])
        for key in (
            "variant_spaces",
            "protocols",
            "actions",
            "expected_action_rules",
            "command_bindings",
        )
    }


def _content_id(prefix: str, data: Mapping[str, object]) -> str:
    digest = hashlib.sha256(
        _canonical_json(
            {
                "definition": dict(data),
                "identity_revision": PROVENANCE_IDENTITY_REVISION,
                "kind": prefix,
            }
        )
    ).hexdigest()
    return f"{prefix}:{digest}"


def _definition_with_id[Definition: _DataDefinition](
    prefix: str, definition: Definition
) -> tuple[str, Definition]:
    return _content_id(prefix, definition.to_data()), definition


def _provenance_collection_name(prefix: str) -> str:
    return {
        "pkg": "source_packages",
        "file": "evidence_files",
        "anchor": "evidence_anchors",
        "sources": "source_sets",
        "evidence": "evidence_bindings",
    }[prefix]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _scalar_sort_key(value: JsonScalar) -> bytes:
    return _canonical_json({"type": type(value).__name__, "value": value})


def _universe_sort_key(key: UniverseKey) -> tuple[str, str, bytes]:
    return key.protocol, key.action, _canonical_json(dict(key.profile))


def _scalars_equal(left: JsonScalar, right: JsonScalar | None) -> bool:
    return right is not None and _scalar_sort_key(left) == _scalar_sort_key(right)


def _fail(code: str, path: str, message: str) -> Never:
    raise IRValidationError((IRDiagnostic(code, path, message),))


class _DuplicateKeyError(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


class _NonFiniteNumberError(ValueError):
    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(value)


def _reject_non_finite_number(value: str) -> Never:
    raise _NonFiniteNumberError(value)


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _NonFiniteNumberError(value)
    return parsed


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result
