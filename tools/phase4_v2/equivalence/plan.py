"""Immutable, queue-shaped execution contracts for Phase 4 v2 packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, NamedTuple, Never, overload

from tools.phase4_v2.validator import (
    PACKAGE_BOUND_VALIDATION_PROFILE,
    PACKAGE_CONTRACT_REVISION,
    VALIDATOR_REVISION,
    Diagnostic,
    ValidationReceipt,
)
from tools.phase4_v2.validator.binding import (
    ArtifactIdentityAttestation,
    EvidenceAnchorAttestation,
    EvidenceMemberAttestation,
)

from .core import (
    EQUIVALENCE_SCHEMA_REVISION,
    EXTRACTOR_CAPABILITY_REVISION,
    LEDGER_DECISION_REVISION,
    LOCAL_ONLY_DOMAINS,
    ApplicationRoot,
    EquivalenceError,
    ExtractorCapability,
    FrozenPackageRef,
    LedgerDecision,
    Route,
)

PACKAGE_LOCAL_PLAN_REVISION = "phase4-v2-package-local-plan-v2"
TARGET_ROOT_INVENTORY_REVISION = "phase4-v2-target-root-inventory-v1"
EXACT_REUSE_PINS_REVISION = "phase4-v2-exact-reuse-pins-v2"
ROOT_EXECUTION_PLAN_REVISION = "phase4-v2-root-execution-plan-v2"
PACKAGE_EXECUTION_PLAN_REVISION = "phase4-v2-package-execution-plan-v2"
VALIDATED_PACKAGE_OUTPUT_REVISION = "phase4-v2-validated-package-output-v2"
SEMANTIC_ROOT_COMPLETION_REVISION = "phase4-v2-semantic-root-completion-v1"
EXACT_REUSE_PIPELINE_CAPABILITY = "phase4-v2-exact-reuse"
PACKAGE_PIPELINE_CAPABILITY = "phase4-v2-package-analysis"
SEMANTIC_ROOT_AUDIT_REVISION = "phase4-v2-semantic-root-audit-v1"
PACKAGE_REPORT_REVISION = "phase4-v2-package-report-v1"
PACKAGE_REPORT_SCHEMA_REVISION = "phase4-v2-package-report-schema-v1"
PACKAGE_REPORT_SCHEMA_CANONICAL_BYTES = json.dumps(
    {
        "report_revision": PACKAGE_REPORT_REVISION,
        "required_package_local_domains": list(LOCAL_ONLY_DOMAINS),
        "requires_authoritative_root_result_set": True,
        "requires_target_package_identity": True,
        "schema_revision": PACKAGE_REPORT_SCHEMA_REVISION,
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
PACKAGE_REPORT_SCHEMA_SHA256 = hashlib.sha256(PACKAGE_REPORT_SCHEMA_CANONICAL_BYTES).hexdigest()

_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_PACKAGE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_MAX_ROOTS = 250_000
_MAX_ROOT_CAPABILITIES = 32
_MAX_ROOT_DEPENDENCIES = 64
_MAX_GLOBAL_REQUIREMENTS = 256
_MAX_GLOBAL_REQUIREMENT_BYTES = 8 * 1024 * 1024
_MAX_BLOCKERS = 4_096
_MAX_TEXT = 4_096
_MAX_RECEIPT_ITEMS = 4_096
_MAX_RECEIPT_PATH = 8_192
_MAX_RECEIPT_COUNTER = 2_000_000
_PACKAGE_RECEIPT_DEPENDENCIES = (
    "corpus",
    "evidence_lineage",
    "execution_plan",
    "ir",
    "preflight",
    "report_schema",
    "schema",
)


def _fail(message: str) -> Never:
    raise EquivalenceError(message)


def _sha(value: str, field: str) -> None:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256 digest")


def _token(value: str, field: str) -> None:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        _fail(f"{field} must be a queue identifier or revision token")


def _text(value: str, field: str, maximum: int = _MAX_TEXT) -> None:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(f"{field} must be a non-empty bounded string")
    if any(ord(character) < 0x20 for character in value):
        _fail(f"{field} contains a control character")


def _revision(value: str, expected: str, field: str) -> None:
    _token(value, field)
    if value != expected:
        _fail(f"unsupported {field} {value!r}; expected {expected!r}")


def _content_id(domain: str, data: Mapping[str, object]) -> str:
    encoded = _canonical_bytes(data)
    return hashlib.sha256(domain.encode() + b"\0" + encoded).hexdigest()


def _canonical_bytes(data: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError, UnicodeError) as error:
        raise EquivalenceError("canonical content contains an unsupported value") from error


@dataclass(frozen=True, slots=True)
class CapabilityPin:
    """Exact shape consumed by ``Queue.require_capability``."""

    name: str
    revision: str
    digest: str

    def __post_init__(self) -> None:
        _token(self.name, "capability.name")
        _token(self.revision, "capability.revision")
        _sha(self.digest, "capability.digest")

    def to_data(self) -> dict[str, str]:
        return {"digest": self.digest, "name": self.name, "revision": self.revision}


@dataclass(frozen=True, slots=True)
class CompletionPin:
    """Exact shape consumed by ``Queue.add_dependency``."""

    parent_unit_id: str
    revision: str
    digest: str

    def __post_init__(self) -> None:
        _token(self.parent_unit_id, "completion.parent_unit_id")
        _token(self.revision, "completion.revision")
        _sha(self.digest, "completion.digest")

    def to_data(self) -> dict[str, str]:
        return {
            "digest": self.digest,
            "parent_unit_id": self.parent_unit_id,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True, init=False)
class SemanticRootCompletion:
    """Queue completion binding inherited semantics to their audited source root."""

    source_root_id: str
    inherited_semantic_root_sha256: str
    completion: CompletionPin

    def __init__(self) -> None:
        _fail("SemanticRootCompletion must be created by its typed evidence factory")


def _semantic_root_completion_digest(
    source_root_id: str,
    inherited_semantic_root_sha256: str,
    parent_unit_id: str,
) -> str:
    _sha(source_root_id, "semantic completion source root")
    _sha(inherited_semantic_root_sha256, "semantic completion inherited root")
    _token(parent_unit_id, "semantic completion parent unit")
    return _content_id(
        "phase4-v2:semantic-root-completion",
        {
            "inherited_semantic_root_sha256": inherited_semantic_root_sha256,
            "parent_unit_id": parent_unit_id,
            "revision": SEMANTIC_ROOT_COMPLETION_REVISION,
            "source_root_id": source_root_id,
        },
    )


def build_semantic_root_completion(
    *,
    source_root: ApplicationRoot,
    inherited_semantic_root_sha256: str,
    parent_unit_id: str,
) -> SemanticRootCompletion:
    if type(source_root) is not ApplicationRoot:
        _fail("semantic root completion requires an exact ApplicationRoot")
    source_root.__post_init__()
    digest = _semantic_root_completion_digest(
        source_root.content_id,
        inherited_semantic_root_sha256,
        parent_unit_id,
    )
    result = object.__new__(SemanticRootCompletion)
    object.__setattr__(result, "source_root_id", source_root.content_id)
    object.__setattr__(
        result, "inherited_semantic_root_sha256", inherited_semantic_root_sha256
    )
    object.__setattr__(
        result,
        "completion",
        CompletionPin(parent_unit_id, SEMANTIC_ROOT_COMPLETION_REVISION, digest),
    )
    return result


def _semantic_root_completion(value: SemanticRootCompletion) -> SemanticRootCompletion:
    if type(value) is not SemanticRootCompletion:
        _fail("semantic audit inherited root requires a typed SemanticRootCompletion")
    completion = _completion(value.completion, "semantic root completion")
    _sha(value.source_root_id, "semantic completion source root")
    _sha(value.inherited_semantic_root_sha256, "semantic completion inherited root")
    _revision(
        completion.revision,
        SEMANTIC_ROOT_COMPLETION_REVISION,
        "semantic root completion",
    )
    if completion.digest != _semantic_root_completion_digest(
        value.source_root_id,
        value.inherited_semantic_root_sha256,
        completion.parent_unit_id,
    ):
        _fail("semantic root completion does not reproduce its typed source binding")
    result = object.__new__(SemanticRootCompletion)
    object.__setattr__(result, "source_root_id", value.source_root_id)
    object.__setattr__(
        result,
        "inherited_semantic_root_sha256",
        value.inherited_semantic_root_sha256,
    )
    object.__setattr__(result, "completion", completion)
    return result


def _capability(value: CapabilityPin, field: str) -> CapabilityPin:
    if type(value) is not CapabilityPin:
        _fail(f"{field} must be an exact CapabilityPin")
    return CapabilityPin(value.name, value.revision, value.digest)


def _completion(value: CompletionPin, field: str) -> CompletionPin:
    if type(value) is not CompletionPin:
        _fail(f"{field} must be an exact CompletionPin")
    return CompletionPin(value.parent_unit_id, value.revision, value.digest)


def _capability_tuple(
    values: tuple[CapabilityPin, ...], field: str, *, nonempty: bool = False
) -> tuple[CapabilityPin, ...]:
    if (
        type(values) is not tuple
        or (nonempty and not values)
        or len(values) > _MAX_ROOT_CAPABILITIES
    ):
        _fail(f"{field} must be a bounded{' non-empty' if nonempty else ''} tuple")
    copied = tuple(_capability(item, field) for item in values)
    if tuple(sorted(copied, key=lambda item: (item.name, item.revision, item.digest))) != copied:
        _fail(f"{field} must be canonically ordered")
    if len({item.name for item in copied}) != len(copied):
        _fail(f"{field} contains duplicate capability names")
    return copied


def _completion_tuple(values: tuple[CompletionPin, ...], field: str) -> tuple[CompletionPin, ...]:
    if type(values) is not tuple or len(values) > _MAX_ROOT_DEPENDENCIES:
        _fail(f"{field} must be a bounded tuple")
    copied = tuple(_completion(item, field) for item in values)
    if (
        tuple(sorted(copied, key=lambda item: (item.parent_unit_id, item.revision, item.digest)))
        != copied
    ):
        _fail(f"{field} must be canonically ordered")
    if len({item.parent_unit_id for item in copied}) != len(copied):
        _fail(f"{field} contains duplicate dependency unit IDs")
    return copied


@dataclass(frozen=True, slots=True)
class PackageLocalPlan:
    target_package_ref_id: str
    package_name: str
    version_code: str
    version_name: str
    target_artifact_digest: str
    requirements_sha256: str
    pipeline_capability: CapabilityPin
    mandatory_domains: tuple[str, ...] = LOCAL_ONLY_DOMAINS
    revision: str = PACKAGE_LOCAL_PLAN_REVISION

    def __post_init__(self) -> None:
        _sha(self.target_package_ref_id, "package_local.target_package_ref_id")
        if type(self.package_name) is not str or _PACKAGE.fullmatch(self.package_name) is None:
            _fail("package_local.package_name is invalid")
        _text(self.version_code, "package_local.version_code", 256)
        _text(self.version_name, "package_local.version_name", 256)
        _sha(self.target_artifact_digest, "package_local.target_artifact_digest")
        _sha(self.requirements_sha256, "package_local.requirements_sha256")
        if (
            type(self.mandatory_domains) is not tuple
            or self.mandatory_domains != LOCAL_ONLY_DOMAINS
            or any(type(item) is not str for item in self.mandatory_domains)
        ):
            _fail("every package-local closure domain must be an exact mandatory tuple")
        pipeline = _capability(self.pipeline_capability, "package pipeline")
        if pipeline.name != PACKAGE_PIPELINE_CAPABILITY:
            _fail("package pipeline capability has the wrong name")
        _revision(pipeline.revision, PACKAGE_EXECUTION_PLAN_REVISION, "package pipeline")
        object.__setattr__(self, "pipeline_capability", pipeline)
        _revision(self.revision, PACKAGE_LOCAL_PLAN_REVISION, "package-local plan revision")

    def to_data(self) -> dict[str, object]:
        return {
            "mandatory_domains": list(self.mandatory_domains),
            "package_name": self.package_name,
            "pipeline_capability": self.pipeline_capability.to_data(),
            "requirements_sha256": self.requirements_sha256,
            "revision": self.revision,
            "target_artifact_digest": self.target_artifact_digest,
            "target_package_ref_id": self.target_package_ref_id,
            "version_code": self.version_code,
            "version_name": self.version_name,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:package-local-plan", self.to_data())


def _local(value: PackageLocalPlan) -> PackageLocalPlan:
    if type(value) is not PackageLocalPlan:
        _fail("plan requires an exact PackageLocalPlan")
    return PackageLocalPlan(
        value.target_package_ref_id,
        value.package_name,
        value.version_code,
        value.version_name,
        value.target_artifact_digest,
        value.requirements_sha256,
        value.pipeline_capability,
        value.mandatory_domains,
        value.revision,
    )


@dataclass(frozen=True, slots=True)
class TargetRootOccurrence:
    target_root_id: str
    occurrence_identity_sha256: str

    def __post_init__(self) -> None:
        _sha(self.target_root_id, "occurrence.target_root_id")
        _sha(self.occurrence_identity_sha256, "occurrence.identity")

    def to_data(self) -> dict[str, str]:
        return {
            "occurrence_identity_sha256": self.occurrence_identity_sha256,
            "target_root_id": self.target_root_id,
        }


def _occurrence(value: TargetRootOccurrence) -> TargetRootOccurrence:
    if type(value) is not TargetRootOccurrence:
        _fail("inventory requires exact TargetRootOccurrence records")
    return TargetRootOccurrence(value.target_root_id, value.occurrence_identity_sha256)


def _occurrence_key(value: TargetRootOccurrence) -> tuple[str, str]:
    return (value.occurrence_identity_sha256, value.target_root_id)


@dataclass(frozen=True, slots=True)
class TargetRootInventory:
    target_package_ref_id: str
    occurrences: tuple[TargetRootOccurrence, ...]
    revision: str = TARGET_ROOT_INVENTORY_REVISION

    def __post_init__(self) -> None:
        _sha(self.target_package_ref_id, "inventory.target_package_ref_id")
        if type(self.occurrences) is not tuple or not self.occurrences:
            _fail("target-root inventory must contain at least one occurrence")
        if len(self.occurrences) > _MAX_ROOTS:
            _fail(f"target-root inventory exceeds {_MAX_ROOTS} occurrences")
        copied = tuple(_occurrence(item) for item in self.occurrences)
        if tuple(sorted(copied, key=_occurrence_key)) != copied:
            _fail("target-root inventory occurrences must be canonically ordered")
        if len({item.occurrence_identity_sha256 for item in copied}) != len(copied):
            _fail("target-root inventory contains a duplicate occurrence")
        if len({item.target_root_id for item in copied}) != len(copied):
            _fail("target-root inventory contains a duplicate target root")
        object.__setattr__(self, "occurrences", copied)
        _revision(self.revision, TARGET_ROOT_INVENTORY_REVISION, "target inventory revision")

    @property
    def root_count(self) -> int:
        return len(self.occurrences)

    @property
    def occurrence_root_set_sha256(self) -> str:
        return _content_id(
            "phase4-v2:occurrence-root-set",
            {"occurrences": [item.to_data() for item in self.occurrences]},
        )

    def to_data(self) -> dict[str, object]:
        return {
            "occurrence_root_set_sha256": self.occurrence_root_set_sha256,
            "occurrences": [item.to_data() for item in self.occurrences],
            "revision": self.revision,
            "root_count": self.root_count,
            "target_package_ref_id": self.target_package_ref_id,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:target-root-inventory", self.to_data())


def _inventory(value: TargetRootInventory) -> TargetRootInventory:
    if type(value) is not TargetRootInventory:
        _fail("plan requires an exact TargetRootInventory")
    return TargetRootInventory(
        value.target_package_ref_id,
        value.occurrences,
        value.revision,
    )


@dataclass(frozen=True, slots=True)
class AcceptedTargetRootInventory:
    inventory: TargetRootInventory
    completion: CompletionPin

    def __post_init__(self) -> None:
        inventory = _inventory(self.inventory)
        completion = _completion(self.completion, "target inventory completion")
        _revision(completion.revision, TARGET_ROOT_INVENTORY_REVISION, "inventory completion")
        if completion.digest != inventory.content_id:
            _fail("target inventory completion does not accept this exact inventory")
        object.__setattr__(self, "inventory", inventory)
        object.__setattr__(self, "completion", completion)

    def to_data(self) -> dict[str, object]:
        return {"completion": self.completion.to_data(), "inventory": self.inventory.to_data()}


def _accepted_inventory(value: AcceptedTargetRootInventory) -> AcceptedTargetRootInventory:
    if type(value) is not AcceptedTargetRootInventory:
        _fail("plan requires an exact AcceptedTargetRootInventory")
    return AcceptedTargetRootInventory(value.inventory, value.completion)


@dataclass(frozen=True, slots=True, init=False)
class SemanticRootAudit:
    source_root_id: str
    target_root_id: str
    target_occurrence_identity_sha256: str
    extractor_capability_id: str
    inherited_semantic_root_sha256: str
    inherited_semantic_root_completion: CompletionPin
    target_inventory_completion: CompletionPin
    ledger_decision_completion: CompletionPin
    direct_semantic_audit_completion: CompletionPin
    extractor_capability: CapabilityPin
    equivalence_pipeline: CapabilityPin
    binding_sha256: str
    revision: str

    def __init__(self) -> None:
        _fail("SemanticRootAudit must be created by its typed evidence factory")

    def to_data(self) -> dict[str, object]:
        return {
            "direct_semantic_audit_completion": self.direct_semantic_audit_completion.to_data(),
            "equivalence_pipeline": self.equivalence_pipeline.to_data(),
            "extractor_capability": self.extractor_capability.to_data(),
            "extractor_capability_id": self.extractor_capability_id,
            "inherited_semantic_root_sha256": self.inherited_semantic_root_sha256,
            "inherited_semantic_root_completion": (
                self.inherited_semantic_root_completion.to_data()
            ),
            "ledger_decision_completion": self.ledger_decision_completion.to_data(),
            "revision": self.revision,
            "source_root_id": self.source_root_id,
            "target_inventory_completion": self.target_inventory_completion.to_data(),
            "target_occurrence_identity_sha256": self.target_occurrence_identity_sha256,
            "target_root_id": self.target_root_id,
            "binding_sha256": self.binding_sha256,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:semantic-root-audit", self.to_data())


def build_semantic_root_audit(
    *,
    source_root: ApplicationRoot,
    ledger_decision: LedgerDecision,
    extractor: ExtractorCapability,
    accepted_target_inventory: AcceptedTargetRootInventory,
    inherited_semantic_root_sha256: str,
    inherited_semantic_root_completion: SemanticRootCompletion,
    target_inventory_completion: CompletionPin,
    ledger_decision_completion: CompletionPin,
    direct_semantic_audit_completion: CompletionPin,
    extractor_capability: CapabilityPin,
    equivalence_pipeline: CapabilityPin,
) -> SemanticRootAudit:
    if type(source_root) is not ApplicationRoot:
        _fail("semantic audit requires an exact ApplicationRoot")
    if type(ledger_decision) is not LedgerDecision:
        _fail("semantic audit requires an exact LedgerDecision")
    if type(extractor) is not ExtractorCapability:
        _fail("semantic audit requires an exact ExtractorCapability")
    source_root.__post_init__()
    ledger_decision.__post_init__()
    extractor.__post_init__()
    accepted = _accepted_inventory(accepted_target_inventory)
    inventory_pin = _completion(target_inventory_completion, "semantic audit inventory")
    ledger_pin = _completion(ledger_decision_completion, "semantic audit ledger")
    audit_pin = _completion(direct_semantic_audit_completion, "semantic audit completion")
    semantic_root_completion = _semantic_root_completion(
        inherited_semantic_root_completion
    )
    semantic_root_pin = semantic_root_completion.completion
    extractor_pin = _capability(extractor_capability, "semantic audit extractor")
    pipeline_pin = _capability(equivalence_pipeline, "semantic audit pipeline")
    _sha(inherited_semantic_root_sha256, "semantic audit inherited root")
    _revision(
        semantic_root_pin.revision,
        SEMANTIC_ROOT_COMPLETION_REVISION,
        "semantic root completion",
    )
    if (
        semantic_root_completion.source_root_id != source_root.content_id
        or semantic_root_completion.inherited_semantic_root_sha256
        != inherited_semantic_root_sha256
    ):
        _fail("semantic root completion does not bind the audited source and inherited root")
    if ledger_decision.route is not Route.EXACT_REUSE:
        _fail("semantic audit requires an EXACT_REUSE ledger decision")
    if (
        ledger_decision.source_root_id != source_root.content_id
        or ledger_decision.inherited_root_id != source_root.content_id
    ):
        _fail("ledger decision does not bind the audited source root")
    if source_root.extractor_capability_id != extractor.content_id:
        _fail("source root does not bind the audited extractor")
    target = tuple(
        item
        for item in accepted.inventory.occurrences
        if item.target_root_id == ledger_decision.target_root_id
    )
    if len(target) != 1:
        _fail("ledger target is absent from the accepted target-root inventory")
    if inventory_pin != accepted.completion:
        _fail("semantic audit uses a transplanted target inventory completion")
    _revision(ledger_pin.revision, LEDGER_DECISION_REVISION, "semantic audit ledger")
    if ledger_pin.digest != ledger_decision.content_id:
        _fail("semantic audit ledger completion does not bind the decision")
    _revision(audit_pin.revision, SEMANTIC_ROOT_COMPLETION_REVISION, "semantic audit completion")
    if audit_pin.digest != ledger_decision.source_audit_receipt_sha256:
        _fail("semantic audit completion does not bind the direct source audit")
    if extractor_pin.digest != extractor.content_id:
        _fail("semantic audit extractor capability does not bind the extractor record")
    if pipeline_pin.name != EXACT_REUSE_PIPELINE_CAPABILITY:
        _fail("semantic audit pipeline capability has the wrong name")
    _revision(pipeline_pin.revision, EQUIVALENCE_SCHEMA_REVISION, "semantic audit pipeline")
    values: dict[str, object] = {
        "source_root_id": source_root.content_id,
        "target_root_id": ledger_decision.target_root_id,
        "target_occurrence_identity_sha256": target[0].occurrence_identity_sha256,
        "extractor_capability_id": extractor.content_id,
        "inherited_semantic_root_sha256": inherited_semantic_root_sha256,
        "inherited_semantic_root_completion": semantic_root_pin,
        "target_inventory_completion": inventory_pin,
        "ledger_decision_completion": ledger_pin,
        "direct_semantic_audit_completion": audit_pin,
        "extractor_capability": extractor_pin,
        "equivalence_pipeline": pipeline_pin,
        "revision": SEMANTIC_ROOT_AUDIT_REVISION,
    }
    values["binding_sha256"] = _semantic_audit_binding_sha256(values)
    result = object.__new__(SemanticRootAudit)
    for field, value in values.items():
        object.__setattr__(result, field, value)
    return result


def _semantic_audit_binding_sha256(values: Mapping[str, object]) -> str:
    def pin_data(name: str) -> dict[str, str]:
        value = values[name]
        if type(value) is CompletionPin or type(value) is CapabilityPin:
            return value.to_data()
        _fail(f"semantic audit {name} is not an exact pin")

    return _content_id(
        "phase4-v2:semantic-root-audit-binding",
        {
            "direct_semantic_audit_completion": pin_data(
                "direct_semantic_audit_completion"
            ),
            "equivalence_pipeline": pin_data("equivalence_pipeline"),
            "extractor_capability": pin_data("extractor_capability"),
            "extractor_capability_id": values["extractor_capability_id"],
            "inherited_semantic_root_completion": pin_data(
                "inherited_semantic_root_completion"
            ),
            "inherited_semantic_root_sha256": values[
                "inherited_semantic_root_sha256"
            ],
            "ledger_decision_completion": pin_data("ledger_decision_completion"),
            "revision": values["revision"],
            "source_root_id": values["source_root_id"],
            "target_inventory_completion": pin_data("target_inventory_completion"),
            "target_occurrence_identity_sha256": values[
                "target_occurrence_identity_sha256"
            ],
            "target_root_id": values["target_root_id"],
        },
    )


def _semantic_audit(value: SemanticRootAudit) -> SemanticRootAudit:
    if type(value) is not SemanticRootAudit:
        _fail("exact reuse requires an exact typed SemanticRootAudit")
    values: dict[str, object] = {
        "source_root_id": value.source_root_id,
        "target_root_id": value.target_root_id,
        "target_occurrence_identity_sha256": value.target_occurrence_identity_sha256,
        "extractor_capability_id": value.extractor_capability_id,
        "inherited_semantic_root_sha256": value.inherited_semantic_root_sha256,
        "inherited_semantic_root_completion": _completion(
            value.inherited_semantic_root_completion,
            "semantic audit inherited root completion",
        ),
        "target_inventory_completion": _completion(
            value.target_inventory_completion, "semantic audit inventory"
        ),
        "ledger_decision_completion": _completion(
            value.ledger_decision_completion, "semantic audit ledger"
        ),
        "direct_semantic_audit_completion": _completion(
            value.direct_semantic_audit_completion, "semantic audit direct completion"
        ),
        "extractor_capability": _capability(
            value.extractor_capability, "semantic audit extractor"
        ),
        "equivalence_pipeline": _capability(
            value.equivalence_pipeline, "semantic audit pipeline"
        ),
        "revision": value.revision,
    }
    for field in (
        "source_root_id",
        "target_root_id",
        "target_occurrence_identity_sha256",
        "extractor_capability_id",
        "inherited_semantic_root_sha256",
    ):
        raw = values[field]
        if type(raw) is not str:
            _fail(f"semantic audit {field} must be an exact digest")
        _sha(raw, f"semantic audit {field}")
    _revision(value.revision, SEMANTIC_ROOT_AUDIT_REVISION, "semantic root audit revision")
    semantic_pin = values["inherited_semantic_root_completion"]
    assert type(semantic_pin) is CompletionPin
    _revision(
        semantic_pin.revision,
        SEMANTIC_ROOT_COMPLETION_REVISION,
        "semantic root completion",
    )
    if semantic_pin.digest != _semantic_root_completion_digest(
        value.source_root_id,
        value.inherited_semantic_root_sha256,
        semantic_pin.parent_unit_id,
    ):
        _fail("semantic root completion relation no longer reproduces")
    extractor_pin = values["extractor_capability"]
    assert type(extractor_pin) is CapabilityPin
    if extractor_pin.digest != value.extractor_capability_id:
        _fail("semantic audit extractor relation no longer reproduces")
    pipeline = values["equivalence_pipeline"]
    assert type(pipeline) is CapabilityPin
    if pipeline.name != EXACT_REUSE_PIPELINE_CAPABILITY:
        _fail("semantic audit pipeline relation no longer reproduces")
    _revision(pipeline.revision, EQUIVALENCE_SCHEMA_REVISION, "semantic audit pipeline")
    for name, expected in (
        ("target_inventory_completion", TARGET_ROOT_INVENTORY_REVISION),
        ("ledger_decision_completion", LEDGER_DECISION_REVISION),
        ("direct_semantic_audit_completion", SEMANTIC_ROOT_COMPLETION_REVISION),
    ):
        pin = values[name]
        assert type(pin) is CompletionPin
        _revision(pin.revision, expected, f"semantic audit {name}")
    _sha(value.binding_sha256, "semantic audit binding")
    if value.binding_sha256 != _semantic_audit_binding_sha256(values):
        _fail("semantic audit binding no longer reproduces its typed relationships")
    values["binding_sha256"] = value.binding_sha256
    result = object.__new__(SemanticRootAudit)
    for field, copied in values.items():
        object.__setattr__(result, field, copied)
    return result


@dataclass(frozen=True, slots=True, init=False)
class ExactReusePins:
    source_root_id: str
    target_root_id: str
    target_occurrence_identity_sha256: str
    inherited_semantic_root_sha256: str
    inherited_semantic_root_completion: CompletionPin
    target_inventory_completion: CompletionPin
    ledger_decision_completion: CompletionPin
    direct_semantic_audit_completion: CompletionPin
    extractor_capability: CapabilityPin
    equivalence_pipeline: CapabilityPin
    extractor_record_revision: str = EXTRACTOR_CAPABILITY_REVISION
    revision: str = EXACT_REUSE_PINS_REVISION

    def __init__(self) -> None:
        _fail("ExactReusePins must be created from a typed SemanticRootAudit")

    def __post_init__(self) -> None:
        _sha(self.source_root_id, "reuse.source_root_id")
        _sha(self.target_root_id, "reuse.target_root_id")
        _sha(self.target_occurrence_identity_sha256, "reuse.occurrence")
        _sha(self.inherited_semantic_root_sha256, "reuse.semantic_root")
        semantic_root = _completion(
            self.inherited_semantic_root_completion, "reuse semantic root completion"
        )
        inventory = _completion(self.target_inventory_completion, "reuse inventory")
        ledger = _completion(self.ledger_decision_completion, "reuse ledger")
        audit = _completion(self.direct_semantic_audit_completion, "reuse semantic audit")
        extractor = _capability(self.extractor_capability, "reuse extractor")
        pipeline = _capability(self.equivalence_pipeline, "reuse pipeline")
        _revision(inventory.revision, TARGET_ROOT_INVENTORY_REVISION, "inventory completion")
        _revision(ledger.revision, LEDGER_DECISION_REVISION, "ledger completion")
        _revision(audit.revision, SEMANTIC_ROOT_COMPLETION_REVISION, "semantic audit")
        _revision(
            semantic_root.revision,
            SEMANTIC_ROOT_COMPLETION_REVISION,
            "semantic root completion",
        )
        if semantic_root.digest != _semantic_root_completion_digest(
            self.source_root_id,
            self.inherited_semantic_root_sha256,
            semantic_root.parent_unit_id,
        ):
            _fail("reuse semantic root completion does not bind the source and inherited root")
        _revision(
            self.extractor_record_revision,
            EXTRACTOR_CAPABILITY_REVISION,
            "extractor record revision",
        )
        if pipeline.name != EXACT_REUSE_PIPELINE_CAPABILITY:
            _fail("exact reuse pipeline capability has the wrong name")
        _revision(pipeline.revision, EQUIVALENCE_SCHEMA_REVISION, "equivalence pipeline")
        object.__setattr__(self, "target_inventory_completion", inventory)
        object.__setattr__(self, "ledger_decision_completion", ledger)
        object.__setattr__(self, "direct_semantic_audit_completion", audit)
        object.__setattr__(self, "inherited_semantic_root_completion", semantic_root)
        object.__setattr__(self, "extractor_capability", extractor)
        object.__setattr__(self, "equivalence_pipeline", pipeline)
        _revision(self.revision, EXACT_REUSE_PINS_REVISION, "reuse pins revision")

    def to_data(self) -> dict[str, object]:
        return {
            "direct_semantic_audit_completion": self.direct_semantic_audit_completion.to_data(),
            "equivalence_pipeline": self.equivalence_pipeline.to_data(),
            "extractor_capability": self.extractor_capability.to_data(),
            "extractor_record_revision": self.extractor_record_revision,
            "inherited_semantic_root_sha256": self.inherited_semantic_root_sha256,
            "inherited_semantic_root_completion": (
                self.inherited_semantic_root_completion.to_data()
            ),
            "ledger_decision_completion": self.ledger_decision_completion.to_data(),
            "revision": self.revision,
            "source_root_id": self.source_root_id,
            "target_inventory_completion": self.target_inventory_completion.to_data(),
            "target_occurrence_identity_sha256": self.target_occurrence_identity_sha256,
            "target_root_id": self.target_root_id,
        }


def _reuse(value: ExactReusePins) -> ExactReusePins:
    if type(value) is not ExactReusePins:
        _fail("exact route requires exact concrete ExactReusePins")
    return _new_reuse_pins(
        source_root_id=value.source_root_id,
        target_root_id=value.target_root_id,
        target_occurrence_identity_sha256=value.target_occurrence_identity_sha256,
        inherited_semantic_root_sha256=value.inherited_semantic_root_sha256,
        inherited_semantic_root_completion=value.inherited_semantic_root_completion,
        target_inventory_completion=value.target_inventory_completion,
        ledger_decision_completion=value.ledger_decision_completion,
        direct_semantic_audit_completion=value.direct_semantic_audit_completion,
        extractor_capability=value.extractor_capability,
        equivalence_pipeline=value.equivalence_pipeline,
        extractor_record_revision=value.extractor_record_revision,
        revision=value.revision,
    )


def _new_reuse_pins(
    *,
    source_root_id: str,
    target_root_id: str,
    target_occurrence_identity_sha256: str,
    inherited_semantic_root_sha256: str,
    inherited_semantic_root_completion: CompletionPin,
    target_inventory_completion: CompletionPin,
    ledger_decision_completion: CompletionPin,
    direct_semantic_audit_completion: CompletionPin,
    extractor_capability: CapabilityPin,
    equivalence_pipeline: CapabilityPin,
    extractor_record_revision: str = EXTRACTOR_CAPABILITY_REVISION,
    revision: str = EXACT_REUSE_PINS_REVISION,
) -> ExactReusePins:
    result = object.__new__(ExactReusePins)
    for field, value in (
        ("source_root_id", source_root_id),
        ("target_root_id", target_root_id),
        ("target_occurrence_identity_sha256", target_occurrence_identity_sha256),
        ("inherited_semantic_root_sha256", inherited_semantic_root_sha256),
        ("inherited_semantic_root_completion", inherited_semantic_root_completion),
        ("target_inventory_completion", target_inventory_completion),
        ("ledger_decision_completion", ledger_decision_completion),
        ("direct_semantic_audit_completion", direct_semantic_audit_completion),
        ("extractor_capability", extractor_capability),
        ("equivalence_pipeline", equivalence_pipeline),
        ("extractor_record_revision", extractor_record_revision),
        ("revision", revision),
    ):
        object.__setattr__(result, field, value)
    result.__post_init__()
    return result


def build_exact_reuse_root_plan(audit: SemanticRootAudit) -> ExactReuseRootPlan:
    audit = _semantic_audit(audit)
    _revision(audit.revision, SEMANTIC_ROOT_AUDIT_REVISION, "semantic root audit revision")
    _sha(audit.source_root_id, "semantic audit source root")
    _sha(audit.target_root_id, "semantic audit target root")
    _sha(audit.target_occurrence_identity_sha256, "semantic audit occurrence")
    _sha(audit.extractor_capability_id, "semantic audit extractor ID")
    _sha(audit.inherited_semantic_root_sha256, "semantic audit inherited root")
    inventory = _completion(audit.target_inventory_completion, "semantic audit inventory")
    ledger = _completion(audit.ledger_decision_completion, "semantic audit ledger")
    direct = _completion(audit.direct_semantic_audit_completion, "semantic audit direct completion")
    semantic_root = _completion(
        audit.inherited_semantic_root_completion,
        "semantic audit inherited root completion",
    )
    extractor = _capability(audit.extractor_capability, "semantic audit extractor")
    pipeline = _capability(audit.equivalence_pipeline, "semantic audit pipeline")
    _revision(inventory.revision, TARGET_ROOT_INVENTORY_REVISION, "semantic audit inventory")
    _revision(ledger.revision, LEDGER_DECISION_REVISION, "semantic audit ledger")
    _revision(direct.revision, SEMANTIC_ROOT_COMPLETION_REVISION, "semantic audit direct")
    if extractor.digest != audit.extractor_capability_id:
        _fail("semantic audit extractor relation no longer reproduces")
    if pipeline.name != EXACT_REUSE_PIPELINE_CAPABILITY:
        _fail("semantic audit pipeline relation no longer reproduces")
    _revision(pipeline.revision, EQUIVALENCE_SCHEMA_REVISION, "semantic audit pipeline")
    pins = _new_reuse_pins(
        source_root_id=audit.source_root_id,
        target_root_id=audit.target_root_id,
        target_occurrence_identity_sha256=audit.target_occurrence_identity_sha256,
        inherited_semantic_root_sha256=audit.inherited_semantic_root_sha256,
        inherited_semantic_root_completion=semantic_root,
        target_inventory_completion=inventory,
        ledger_decision_completion=ledger,
        direct_semantic_audit_completion=direct,
        extractor_capability=extractor,
        equivalence_pipeline=pipeline,
    )
    return ExactReuseRootPlan(pins)


@dataclass(frozen=True, slots=True)
class ExactReuseRootPlan:
    reuse: ExactReusePins
    revision: str = ROOT_EXECUTION_PLAN_REVISION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reuse", _reuse(self.reuse))
        _revision(self.revision, ROOT_EXECUTION_PLAN_REVISION, "root plan revision")

    route = Route.EXACT_REUSE

    @property
    def target_root_id(self) -> str:
        return self.reuse.target_root_id

    @property
    def target_occurrence_identity_sha256(self) -> str:
        return self.reuse.target_occurrence_identity_sha256

    def to_data(self) -> dict[str, object]:
        return {"reuse": self.reuse.to_data(), "revision": self.revision, "route": self.route.value}


@dataclass(frozen=True, slots=True)
class FullAnalysisRootPlan:
    target_root_id: str
    target_occurrence_identity_sha256: str
    reason: str
    analysis_capabilities: tuple[CapabilityPin, ...]
    analysis_dependencies: tuple[CompletionPin, ...] = ()
    revision: str = ROOT_EXECUTION_PLAN_REVISION

    def __post_init__(self) -> None:
        _sha(self.target_root_id, "full.target_root_id")
        _sha(self.target_occurrence_identity_sha256, "full.occurrence")
        _text(self.reason, "full.reason")
        object.__setattr__(
            self,
            "analysis_capabilities",
            _capability_tuple(
                self.analysis_capabilities, "full analysis capabilities", nonempty=True
            ),
        )
        object.__setattr__(
            self,
            "analysis_dependencies",
            _completion_tuple(self.analysis_dependencies, "full analysis dependencies"),
        )
        _revision(self.revision, ROOT_EXECUTION_PLAN_REVISION, "root plan revision")

    route = Route.FULL_ANALYSIS

    def to_data(self) -> dict[str, object]:
        return {
            "analysis_capabilities": [item.to_data() for item in self.analysis_capabilities],
            "analysis_dependencies": [item.to_data() for item in self.analysis_dependencies],
            "reason": self.reason,
            "revision": self.revision,
            "route": self.route.value,
            "target_occurrence_identity_sha256": self.target_occurrence_identity_sha256,
            "target_root_id": self.target_root_id,
        }


@dataclass(frozen=True, slots=True)
class BlockedRootPlan:
    target_root_id: str
    target_occurrence_identity_sha256: str
    blockers: tuple[str, ...]
    revision: str = ROOT_EXECUTION_PLAN_REVISION

    def __post_init__(self) -> None:
        _sha(self.target_root_id, "blocked.target_root_id")
        _sha(self.target_occurrence_identity_sha256, "blocked.occurrence")
        if type(self.blockers) is not tuple or not self.blockers:
            _fail("blocked root plan requires at least one blocker")
        if len(self.blockers) > _MAX_BLOCKERS:
            _fail(f"blocked root plan exceeds {_MAX_BLOCKERS} blockers")
        for index, blocker in enumerate(self.blockers):
            _text(blocker, f"blocked.blockers[{index}]")
        if tuple(sorted(set(self.blockers))) != self.blockers:
            _fail("blocked root plan blockers must be sorted and unique")
        _revision(self.revision, ROOT_EXECUTION_PLAN_REVISION, "root plan revision")

    route = Route.BLOCKED

    def to_data(self) -> dict[str, object]:
        return {
            "blockers": list(self.blockers),
            "revision": self.revision,
            "route": self.route.value,
            "target_occurrence_identity_sha256": self.target_occurrence_identity_sha256,
            "target_root_id": self.target_root_id,
        }


type RootExecutionPlan = ExactReuseRootPlan | FullAnalysisRootPlan | BlockedRootPlan


def _root(value: RootExecutionPlan) -> RootExecutionPlan:
    if type(value) is ExactReuseRootPlan:
        return ExactReuseRootPlan(value.reuse, value.revision)
    if type(value) is FullAnalysisRootPlan:
        return FullAnalysisRootPlan(
            value.target_root_id,
            value.target_occurrence_identity_sha256,
            value.reason,
            value.analysis_capabilities,
            value.analysis_dependencies,
            value.revision,
        )
    if type(value) is BlockedRootPlan:
        return BlockedRootPlan(
            value.target_root_id,
            value.target_occurrence_identity_sha256,
            value.blockers,
            value.revision,
        )
    _fail("root plan must be an exact supported concrete type")


def _root_key(value: RootExecutionPlan) -> tuple[str, str, str]:
    return (value.target_occurrence_identity_sha256, value.target_root_id, value.route.value)


def _merge_capabilities(values: Iterable[CapabilityPin]) -> tuple[CapabilityPin, ...]:
    indexed: dict[str, CapabilityPin] = {}
    for value in values:
        copied = _capability(value, "aggregate capability")
        previous = indexed.get(copied.name)
        if previous is not None and previous != copied:
            _fail(f"conflicting capability pins for {copied.name!r}")
        indexed[copied.name] = copied
    if len(indexed) > _MAX_GLOBAL_REQUIREMENTS:
        _fail("global capability requirement count exceeds its limit")
    if (
        sum(len(item.name) + len(item.revision) + len(item.digest) for item in indexed.values())
        > _MAX_GLOBAL_REQUIREMENT_BYTES
    ):
        _fail("global capability requirement byte budget exceeded")
    return tuple(sorted(indexed.values(), key=lambda item: item.name))


def _merge_completions(values: Iterable[CompletionPin]) -> tuple[CompletionPin, ...]:
    indexed: dict[str, CompletionPin] = {}
    for value in values:
        copied = _completion(value, "aggregate completion")
        previous = indexed.get(copied.parent_unit_id)
        if previous is not None and previous != copied:
            _fail(f"conflicting completion pins for {copied.parent_unit_id!r}")
        indexed[copied.parent_unit_id] = copied
    if len(indexed) > _MAX_GLOBAL_REQUIREMENTS:
        _fail("global completion requirement count exceeds its limit")
    if (
        sum(
            len(item.parent_unit_id) + len(item.revision) + len(item.digest)
            for item in indexed.values()
        )
        > _MAX_GLOBAL_REQUIREMENT_BYTES
    ):
        _fail("global completion requirement byte budget exceeded")
    return tuple(sorted(indexed.values(), key=lambda item: item.parent_unit_id))


class PackagePlanStatus(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PackageExecutionPlan:
    """Mutable-boundary input; freeze it before treating it as a trust proof."""

    target_package_ref_id: str
    target_package_ref: FrozenPackageRef
    package_local: PackageLocalPlan
    accepted_target_inventory: AcceptedTargetRootInventory
    root_plans: tuple[RootExecutionPlan, ...]
    revision: str = PACKAGE_EXECUTION_PLAN_REVISION

    def __post_init__(self) -> None:
        _sha(self.target_package_ref_id, "plan.target_package_ref_id")
        if type(self.target_package_ref) is not FrozenPackageRef:
            _fail("plan requires an exact FrozenPackageRef")
        target_package_ref = FrozenPackageRef(
            self.target_package_ref.package_name,
            self.target_package_ref.version_code,
            self.target_package_ref.artifact_digest,
            self.target_package_ref.preflight_sha256,
            self.target_package_ref.validation_receipt_sha256,
            self.target_package_ref.revision,
        )
        local = _local(self.package_local)
        accepted = _accepted_inventory(self.accepted_target_inventory)
        if target_package_ref.content_id != self.target_package_ref_id:
            _fail("frozen package reference does not reproduce the target package ID")
        if (
            target_package_ref.package_name,
            target_package_ref.version_code,
            target_package_ref.artifact_digest,
        ) != (
            local.package_name,
            local.version_code,
            local.target_artifact_digest,
        ):
            _fail("package-local plan does not match the frozen package artifact identity")
        if local.target_package_ref_id != self.target_package_ref_id:
            _fail("package-local plan targets a different package")
        if accepted.inventory.target_package_ref_id != self.target_package_ref_id:
            _fail("target-root inventory targets a different package")
        if type(self.root_plans) is not tuple or not self.root_plans:
            _fail("package execution plan requires at least one root plan")
        if len(self.root_plans) > _MAX_ROOTS:
            _fail(f"package execution plan exceeds {_MAX_ROOTS} roots")
        roots = tuple(_root(item) for item in self.root_plans)
        if tuple(sorted(roots, key=_root_key)) != roots:
            _fail("root plans must use canonical deterministic ordering")
        planned = tuple(
            TargetRootOccurrence(item.target_root_id, item.target_occurrence_identity_sha256)
            for item in roots
        )
        if planned != accepted.inventory.occurrences:
            _fail("root plans do not exactly reproduce the authoritative occurrence/root set")
        for item in roots:
            if type(item) is ExactReuseRootPlan and (
                item.reuse.target_inventory_completion != accepted.completion
            ):
                _fail("exact reuse pins a transplanted target inventory completion")
        object.__setattr__(self, "target_package_ref", target_package_ref)
        object.__setattr__(self, "package_local", local)
        object.__setattr__(self, "accepted_target_inventory", accepted)
        object.__setattr__(self, "root_plans", roots)
        _ = self.required_capabilities
        _ = self.required_completions
        _revision(self.revision, PACKAGE_EXECUTION_PLAN_REVISION, "package plan revision")

    @property
    def status(self) -> PackagePlanStatus:
        if any(item.route is Route.BLOCKED for item in self.root_plans):
            return PackagePlanStatus.BLOCKED
        return PackagePlanStatus.EXECUTABLE

    @property
    def executable(self) -> bool:
        return self.status is PackagePlanStatus.EXECUTABLE

    @property
    def inherited_semantic_roots(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.reuse.inherited_semantic_root_sha256
                    for item in self.root_plans
                    if type(item) is ExactReuseRootPlan
                }
            )
        )

    @property
    def required_capabilities(self) -> tuple[CapabilityPin, ...]:
        def values() -> Iterable[CapabilityPin]:
            yield self.package_local.pipeline_capability
            for item in self.root_plans:
                if type(item) is ExactReuseRootPlan:
                    yield item.reuse.extractor_capability
                    yield item.reuse.equivalence_pipeline
                elif type(item) is FullAnalysisRootPlan:
                    yield from item.analysis_capabilities

        return _merge_capabilities(values())

    @property
    def required_completions(self) -> tuple[CompletionPin, ...]:
        def values() -> Iterable[CompletionPin]:
            yield self.accepted_target_inventory.completion
            for item in self.root_plans:
                if type(item) is ExactReuseRootPlan:
                    yield item.reuse.target_inventory_completion
                    yield item.reuse.ledger_decision_completion
                    yield item.reuse.direct_semantic_audit_completion
                    yield item.reuse.inherited_semantic_root_completion
                elif type(item) is FullAnalysisRootPlan:
                    yield from item.analysis_dependencies

        return _merge_completions(values())

    def to_data(self) -> dict[str, object]:
        inventory = self.accepted_target_inventory.inventory
        return {
            "accepted_target_inventory": self.accepted_target_inventory.to_data(),
            "authoritative_occurrence_root_set_sha256": inventory.occurrence_root_set_sha256,
            "authoritative_root_count": inventory.root_count,
            "package_local": self.package_local.to_data(),
            "required_capabilities": [item.to_data() for item in self.required_capabilities],
            "required_completions": [item.to_data() for item in self.required_completions],
            "revision": self.revision,
            "root_plans": [item.to_data() for item in self.root_plans],
            "status": self.status.value,
            "target_package_ref_id": self.target_package_ref_id,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:package-execution-plan", self.to_data())


class FrozenCapabilityPin(NamedTuple):
    """Tuple-backed capability pin that cannot be mutated through object setattr."""

    name: str
    revision: str
    digest: str


class FrozenCompletionPin(NamedTuple):
    """Tuple-backed completion pin that cannot be mutated through object setattr."""

    parent_unit_id: str
    revision: str
    digest: str


def _frozen_capability(value: CapabilityPin) -> FrozenCapabilityPin:
    copied = _capability(value, "frozen capability")
    return FrozenCapabilityPin(copied.name, copied.revision, copied.digest)


def _frozen_completion(value: CompletionPin) -> FrozenCompletionPin:
    copied = _completion(value, "frozen completion")
    return FrozenCompletionPin(copied.parent_unit_id, copied.revision, copied.digest)


@dataclass(frozen=True, slots=True, init=False)
class FrozenPackageExecutionPlan:
    """Canonical immutable snapshot consumed by trust-sensitive adapters."""

    target_package_ref_id: str
    canonical_bytes: bytes
    digest: str
    status: PackagePlanStatus
    root_count: int
    package_name: str
    version_code: str
    version_name: str
    target_artifact_digest: str
    inherited_semantic_roots: tuple[str, ...]
    semantic_audit_completion_digests: tuple[str, ...]
    required_capabilities: tuple[FrozenCapabilityPin, ...]
    required_completions: tuple[FrozenCompletionPin, ...]

    def __init__(self) -> None:
        _fail("FrozenPackageExecutionPlan must be created by its canonical factory")


def _new_frozen_package_execution_plan(
    *,
    target_package_ref_id: str,
    canonical_bytes: bytes,
    digest: str,
    status: PackagePlanStatus,
    root_count: int,
    package_name: str,
    version_code: str,
    version_name: str,
    target_artifact_digest: str,
    inherited_semantic_roots: tuple[str, ...],
    semantic_audit_completion_digests: tuple[str, ...],
    required_capabilities: tuple[FrozenCapabilityPin, ...],
    required_completions: tuple[FrozenCompletionPin, ...],
) -> FrozenPackageExecutionPlan:
    values: dict[str, object] = {
        "target_package_ref_id": target_package_ref_id,
        "canonical_bytes": canonical_bytes,
        "digest": digest,
        "status": status,
        "root_count": root_count,
        "package_name": package_name,
        "version_code": version_code,
        "version_name": version_name,
        "target_artifact_digest": target_artifact_digest,
        "inherited_semantic_roots": inherited_semantic_roots,
        "semantic_audit_completion_digests": semantic_audit_completion_digests,
        "required_capabilities": required_capabilities,
        "required_completions": required_completions,
    }
    _sha(target_package_ref_id, "snapshot.target_package_ref_id")
    if type(canonical_bytes) is not bytes:
        _fail("snapshot canonical bytes must be exact immutable bytes")
    _sha(digest, "snapshot.digest")
    try:
        decoded = json.loads(canonical_bytes)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise EquivalenceError("snapshot canonical bytes are not valid JSON") from error
    if not isinstance(decoded, dict) or _canonical_bytes(decoded) != canonical_bytes:
        _fail("snapshot canonical bytes are not an exact canonical preimage")
    expected_digest = hashlib.sha256(
        b"phase4-v2:package-execution-plan\0" + canonical_bytes
    ).hexdigest()
    if digest != expected_digest:
        _fail("snapshot digest does not bind its canonical preimage")
    if type(status) is not PackagePlanStatus:
        _fail("snapshot status must be a PackagePlanStatus")
    if type(root_count) is not int or not 0 < root_count <= _MAX_ROOTS:
        _fail("snapshot root count is invalid")
    if decoded.get("target_package_ref_id") != target_package_ref_id:
        _fail("snapshot target does not match its canonical preimage")
    if decoded.get("status") != status.value:
        _fail("snapshot status does not match its canonical preimage")
    if decoded.get("authoritative_root_count") != root_count:
        _fail("snapshot root count does not match its canonical preimage")
    local = decoded.get("package_local")
    if not isinstance(local, dict) or (
        local.get("package_name"),
        local.get("version_code"),
        local.get("version_name"),
        local.get("target_artifact_digest"),
    ) != (package_name, version_code, version_name, target_artifact_digest):
        _fail("snapshot package identity does not match its canonical preimage")
    if type(required_capabilities) is not tuple or not required_capabilities:
        _fail("snapshot capabilities must be a non-empty tuple")
    if any(type(item) is not FrozenCapabilityPin for item in required_capabilities):
        _fail("snapshot capabilities must use exact immutable pins")
    if type(required_completions) is not tuple or any(
        type(item) is not FrozenCompletionPin for item in required_completions
    ):
        _fail("snapshot completions must use exact immutable pins")
    expected_capability_data = [
        {"name": item.name, "revision": item.revision, "digest": item.digest}
        for item in required_capabilities
    ]
    expected_completion_data = [
        {
            "parent_unit_id": item.parent_unit_id,
            "revision": item.revision,
            "digest": item.digest,
        }
        for item in required_completions
    ]
    if decoded.get("required_capabilities") != expected_capability_data:
        _fail("snapshot capabilities do not match its canonical preimage")
    if decoded.get("required_completions") != expected_completion_data:
        _fail("snapshot completions do not match its canonical preimage")
    if type(package_name) is not str or _PACKAGE.fullmatch(package_name) is None:
        _fail("snapshot package name is invalid")
    _text(version_code, "snapshot.version_code", 256)
    _text(version_name, "snapshot.version_name", 256)
    _sha(target_artifact_digest, "snapshot.target_artifact_digest")
    for field, items in (
        ("inherited_semantic_roots", inherited_semantic_roots),
        ("semantic_audit_completion_digests", semantic_audit_completion_digests),
    ):
        if type(items) is not tuple or tuple(sorted(set(items))) != items:
            _fail(f"snapshot {field} must be a canonical tuple")
        for item in items:
            _sha(item, f"snapshot.{field}")
    if tuple(sorted(required_capabilities, key=lambda item: item.name)) != required_capabilities:
        _fail("snapshot capabilities are not canonical")
    if len({item.name for item in required_capabilities}) != len(required_capabilities):
        _fail("snapshot capabilities contain duplicate names")
    if (
        tuple(sorted(required_completions, key=lambda item: item.parent_unit_id))
        != required_completions
    ):
        _fail("snapshot completions are not canonical")
    if len({item.parent_unit_id for item in required_completions}) != len(
        required_completions
    ):
        _fail("snapshot completions contain duplicate unit IDs")
    if len(required_capabilities) > _MAX_GLOBAL_REQUIREMENTS or len(
        required_completions
    ) > _MAX_GLOBAL_REQUIREMENTS:
        _fail("snapshot requirement set exceeds the queue limit")
    result = object.__new__(FrozenPackageExecutionPlan)
    for field, value in values.items():
        object.__setattr__(result, field, value)
    return result


def _validate_frozen_package_execution_plan(
    value: FrozenPackageExecutionPlan,
) -> FrozenPackageExecutionPlan:
    if type(value) is not FrozenPackageExecutionPlan:
        _fail("expected an exact frozen package execution plan")
    return _new_frozen_package_execution_plan(
        target_package_ref_id=value.target_package_ref_id,
        canonical_bytes=value.canonical_bytes,
        digest=value.digest,
        status=value.status,
        root_count=value.root_count,
        package_name=value.package_name,
        version_code=value.version_code,
        version_name=value.version_name,
        target_artifact_digest=value.target_artifact_digest,
        inherited_semantic_roots=value.inherited_semantic_roots,
        semantic_audit_completion_digests=value.semantic_audit_completion_digests,
        required_capabilities=value.required_capabilities,
        required_completions=value.required_completions,
    )


def freeze_package_execution_plan(value: PackageExecutionPlan) -> FrozenPackageExecutionPlan:
    if type(value) is not PackageExecutionPlan:
        _fail("plan snapshot requires an exact PackageExecutionPlan")
    frozen = PackageExecutionPlan(
        value.target_package_ref_id,
        value.target_package_ref,
        value.package_local,
        value.accepted_target_inventory,
        value.root_plans,
        value.revision,
    )
    canonical = _canonical_bytes(frozen.to_data())
    digest = hashlib.sha256(b"phase4-v2:package-execution-plan\0" + canonical).hexdigest()
    return _new_frozen_package_execution_plan(
        target_package_ref_id=frozen.target_package_ref_id,
        canonical_bytes=canonical,
        digest=digest,
        status=frozen.status,
        root_count=len(frozen.root_plans),
        package_name=frozen.package_local.package_name,
        version_code=frozen.package_local.version_code,
        version_name=frozen.package_local.version_name,
        target_artifact_digest=frozen.package_local.target_artifact_digest,
        inherited_semantic_roots=frozen.inherited_semantic_roots,
        semantic_audit_completion_digests=tuple(
            sorted(
                {
                    item.reuse.direct_semantic_audit_completion.digest
                    for item in frozen.root_plans
                    if type(item) is ExactReuseRootPlan
                }
            )
        ),
        required_capabilities=tuple(
            _frozen_capability(item) for item in frozen.required_capabilities
        ),
        required_completions=tuple(
            _frozen_completion(item) for item in frozen.required_completions
        ),
    )


def build_package_execution_plan(
    *,
    target_package_ref_id: str,
    target_package_ref: FrozenPackageRef,
    package_local: PackageLocalPlan,
    accepted_target_inventory: AcceptedTargetRootInventory,
    root_plans: Iterable[RootExecutionPlan],
) -> PackageExecutionPlan:
    roots: list[RootExecutionPlan] = []
    for index, item in enumerate(root_plans):
        if index >= _MAX_ROOTS:
            _fail(f"package execution plan exceeds {_MAX_ROOTS} roots")
        roots.append(_root(item))
    return PackageExecutionPlan(
        target_package_ref_id,
        target_package_ref,
        package_local,
        accepted_target_inventory,
        tuple(sorted(roots, key=_root_key)),
    )


@dataclass(frozen=True, slots=True, init=False)
class ValidatedPackageOutput:
    target_package_ref_id: str
    execution_plan_id: str
    validation_receipt_sha256: str
    target_report_revision: str
    target_report_schema_revision: str
    target_report_schema_sha256: str
    target_report_sha256: str
    revision: str

    def __init__(self) -> None:
        _fail("ValidatedPackageOutput must be created by the trusted receipt factory")

    def to_data(self) -> dict[str, str]:
        return {
            "execution_plan_id": self.execution_plan_id,
            "revision": self.revision,
            "target_package_ref_id": self.target_package_ref_id,
            "target_report_revision": self.target_report_revision,
            "target_report_schema_revision": self.target_report_schema_revision,
            "target_report_schema_sha256": self.target_report_schema_sha256,
            "target_report_sha256": self.target_report_sha256,
            "validation_receipt_sha256": self.validation_receipt_sha256,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:validated-package-output", self.to_data())


def _exact_pair_tuple(
    value: tuple[tuple[str, str], ...], field: str
) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple:
        _fail(f"{field} must be an exact tuple")
    copied: list[tuple[str, str]] = []
    if len(value) > _MAX_RECEIPT_ITEMS:
        _fail(f"{field} exceeds its item limit")
    for item in value:
        if type(item) is not tuple or len(item) != 2 or any(type(part) is not str for part in item):
            _fail(f"{field} contains a non-exact pair")
        if any(len(part) > _MAX_RECEIPT_PATH for part in item):
            _fail(f"{field} contains an unbounded pair")
        copied.append((item[0], item[1]))
    if len({item[0] for item in copied}) != len(copied):
        _fail(f"{field} contains duplicate keys")
    return tuple(copied)


def _receipt_string(
    value: object,
    field: str,
    *,
    maximum: int = _MAX_RECEIPT_PATH,
    nonempty: bool = True,
) -> str:
    if (
        type(value) is not str
        or (nonempty and not value)
        or len(value) > maximum
        or any(ord(character) < 0x20 for character in value)
    ):
        _fail(f"{field} must be an exact bounded string")
    return value


@overload
def _receipt_sha(
    value: object, field: str, *, optional: Literal[False] = False
) -> str: ...


@overload
def _receipt_sha(
    value: object, field: str, *, optional: Literal[True]
) -> str | None: ...


def _receipt_sha(value: object, field: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if type(value) is not str:
        _fail(f"{field} must be an exact digest")
    _sha(value, field)
    return value


def _receipt_counter(value: object, field: str, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _fail(f"{field} must be an exact bounded non-negative integer")
    return value


def _snapshot_receipt(receipt: ValidationReceipt) -> ValidationReceipt:
    if type(receipt) is not ValidationReceipt:
        _fail("validated output requires an exact ValidationReceipt")
    if type(receipt.diagnostics) is not tuple:
        _fail("validator diagnostics must be an exact tuple")
    if len(receipt.diagnostics) > _MAX_RECEIPT_ITEMS:
        _fail("validator diagnostics exceed their item limit")
    diagnostics: list[Diagnostic] = []
    for item in receipt.diagnostics:
        if type(item) is not Diagnostic:
            _fail("validator diagnostics contain a non-exact Diagnostic")
        context = _exact_pair_tuple(item.context, "diagnostic context")
        diagnostics.append(
            Diagnostic(
                _receipt_string(item.code, "diagnostic.code", maximum=256),
                _receipt_string(item.path, "diagnostic.path"),
                context,
            )
        )
    identity = receipt.validated_artifact_identity
    if type(identity) is not ArtifactIdentityAttestation:
        _fail("validator receipt has no exact validated artifact identity")
    package_name = _receipt_string(identity.package_name, "artifact.package_name", maximum=256)
    if _PACKAGE.fullmatch(package_name) is None:
        _fail("validator artifact package name is invalid")
    copied_identity = ArtifactIdentityAttestation(
        package_name,
        _receipt_string(identity.version_code, "artifact.version_code", maximum=256),
        _receipt_string(identity.version_name, "artifact.version_name", maximum=256),
        _receipt_sha(identity.artifact_digest, "artifact.artifact_digest"),
    )
    if type(receipt.validated_evidence_members) is not tuple:
        _fail("validated evidence members must be an exact tuple")
    if len(receipt.validated_evidence_members) > _MAX_RECEIPT_ITEMS:
        _fail("validated evidence members exceed their item limit")
    members: list[EvidenceMemberAttestation] = []
    for item in receipt.validated_evidence_members:
        if type(item) is not EvidenceMemberAttestation:
            _fail("validated evidence members contain a non-exact attestation")
        members.append(
            EvidenceMemberAttestation(
                _receipt_string(item.member, "evidence member.member"),
                _receipt_sha(item.owner, "evidence member.owner"),
                _receipt_sha(item.sha256, "evidence member.sha256"),
            )
        )
    if type(receipt.validated_evidence_anchors) is not tuple:
        _fail("validated evidence anchors must be an exact tuple")
    if len(receipt.validated_evidence_anchors) > _MAX_RECEIPT_ITEMS:
        _fail("validated evidence anchors exceed their item limit")
    anchors: list[EvidenceAnchorAttestation] = []
    for item in receipt.validated_evidence_anchors:
        if type(item) is not EvidenceAnchorAttestation:
            _fail("validated evidence anchors contain a non-exact attestation")
        anchors.append(
            EvidenceAnchorAttestation(
                _receipt_string(item.id, "evidence anchor.id", maximum=256),
                _receipt_sha(item.owner, "evidence anchor.owner"),
                _receipt_string(item.member, "evidence anchor.member"),
                _receipt_sha(item.member_sha256, "evidence anchor.member_sha256"),
                _receipt_counter(item.start_byte, "evidence anchor.start_byte", 2**31 - 1),
                _receipt_counter(item.end_byte, "evidence anchor.end_byte", 2**31 - 1),
                _receipt_string(item.ir_pointer, "evidence anchor.ir_pointer"),
                _receipt_string(item.representation, "evidence anchor.representation", maximum=16),
                _receipt_sha(item.value_sha256, "evidence anchor.value_sha256"),
            )
        )
        if item.end_byte <= item.start_byte:
            _fail("evidence anchor range is invalid")
    dependencies = _exact_pair_tuple(
        receipt.dependency_digests, "validator dependency digests"
    )
    if tuple(name for name, _ in dependencies) != _PACKAGE_RECEIPT_DEPENDENCIES:
        _fail("validator dependency digests are not the exact BOUND_V5 set")
    for name, digest in dependencies:
        _sha(digest, f"validator dependency {name}")
    accepted = receipt.accepted
    source_unchanged = receipt.source_unchanged
    if type(accepted) is not bool or type(source_unchanged) is not bool:
        _fail("validator receipt flags must be exact booleans")
    anchors_checked = _receipt_counter(
        receipt.evidence_anchors_checked,
        "receipt.evidence_anchors_checked",
        _MAX_RECEIPT_ITEMS,
    )
    if anchors_checked != len(anchors):
        _fail("validator anchor count does not match its attestations")
    return ValidationReceipt(
        validator_revision=_receipt_string(
            receipt.validator_revision, "receipt.validator_revision", maximum=256
        ),
        accepted=accepted,
        source_unchanged=source_unchanged,
        bundle_sha256=_receipt_sha(receipt.bundle_sha256, "receipt.bundle_sha256", optional=True),
        report_manifest_sha256=_receipt_sha(
            receipt.report_manifest_sha256,
            "receipt.report_manifest_sha256",
            optional=True,
        ),
        discovered_members=_receipt_counter(
            receipt.discovered_members, "receipt.discovered_members", _MAX_RECEIPT_COUNTER
        ),
        declared_members=_receipt_counter(
            receipt.declared_members, "receipt.declared_members", _MAX_RECEIPT_COUNTER
        ),
        diagnostics=tuple(diagnostics),
        dependency_digests=dependencies,
        evidence_anchors_checked=anchors_checked,
        validation_profile=_receipt_string(
            receipt.validation_profile, "receipt.validation_profile", maximum=64
        ),
        contract_revision=_receipt_string(
            receipt.contract_revision, "receipt.contract_revision", maximum=256
        ),
        validated_artifact_identity=copied_identity,
        validated_evidence_members=tuple(members),
        validated_evidence_anchors=tuple(anchors),
        validation_receipt_sha256=_receipt_sha(
            receipt.validation_receipt_sha256,
            "receipt.validation_receipt_sha256",
            optional=True,
        ),
    )


def _receipt_identity(receipt: ValidationReceipt) -> str:
    try:
        payload = json.dumps(
            receipt.identity_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, UnicodeError) as error:
        raise EquivalenceError("validator receipt identity is not canonical JSON") from error
    return hashlib.sha256(payload).hexdigest()


def build_validated_package_output(
    *,
    execution_plan: PackageExecutionPlan,
    receipt: ValidationReceipt,
    trusted_validation_receipt_sha256: str,
) -> ValidatedPackageOutput:
    if type(execution_plan) is not PackageExecutionPlan:
        _fail("validated output requires an exact PackageExecutionPlan")
    plan = freeze_package_execution_plan(execution_plan)
    if plan.status is not PackagePlanStatus.EXECUTABLE:
        _fail("a blocked package execution plan cannot produce a validated output")
    frozen_receipt = _snapshot_receipt(receipt)
    _sha(trusted_validation_receipt_sha256, "trusted_validation_receipt_sha256")
    identity_sha = _receipt_identity(frozen_receipt)
    if (
        frozen_receipt.validation_receipt_sha256 != identity_sha
        or trusted_validation_receipt_sha256 != identity_sha
    ):
        _fail("validator receipt identity does not match the external trust pin")
    if frozen_receipt.validator_revision != VALIDATOR_REVISION:
        _fail("validator receipt uses an unsupported validator revision")
    if frozen_receipt.contract_revision != PACKAGE_CONTRACT_REVISION:
        _fail("validator receipt uses an unsupported contract revision")
    if frozen_receipt.validation_profile != PACKAGE_BOUND_VALIDATION_PROFILE:
        _fail("validator receipt is not package-bound")
    if (
        frozen_receipt.accepted is not True
        or frozen_receipt.source_unchanged is not True
        or frozen_receipt.diagnostics
    ):
        _fail("validator receipt is not an accepted unchanged zero-diagnostic result")
    dependencies = dict(frozen_receipt.dependency_digests)
    if dependencies.get("execution_plan") != plan.digest:
        _fail("validator receipt does not bind the frozen execution plan")
    if dependencies.get("report_schema") != PACKAGE_REPORT_SCHEMA_SHA256:
        _fail("validator receipt does not bind the current package-report schema")
    if frozen_receipt.bundle_sha256 is None:
        _fail("validator receipt has no target bundle digest")
    _sha(frozen_receipt.bundle_sha256, "receipt.bundle_sha256")
    identity = frozen_receipt.validated_artifact_identity
    assert identity is not None
    if (
        identity.package_name,
        identity.version_code,
        identity.version_name,
        identity.artifact_digest,
    ) != (
        plan.package_name,
        plan.version_code,
        plan.version_name,
        plan.target_artifact_digest,
    ):
        _fail("validator receipt targets a different artifact identity")
    forbidden = {*plan.inherited_semantic_roots, *plan.semantic_audit_completion_digests}
    if frozen_receipt.bundle_sha256 in forbidden:
        _fail("source semantic-root evidence cannot serve as the target package report")
    output = object.__new__(ValidatedPackageOutput)
    object.__setattr__(output, "target_package_ref_id", plan.target_package_ref_id)
    object.__setattr__(output, "execution_plan_id", plan.digest)
    object.__setattr__(output, "validation_receipt_sha256", identity_sha)
    object.__setattr__(output, "target_report_revision", PACKAGE_REPORT_REVISION)
    object.__setattr__(output, "target_report_schema_revision", PACKAGE_REPORT_SCHEMA_REVISION)
    object.__setattr__(output, "target_report_schema_sha256", PACKAGE_REPORT_SCHEMA_SHA256)
    object.__setattr__(output, "target_report_sha256", frozen_receipt.bundle_sha256)
    object.__setattr__(output, "revision", VALIDATED_PACKAGE_OUTPUT_REVISION)
    return output
