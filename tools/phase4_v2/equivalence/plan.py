"""Immutable, queue-shaped execution contracts for Phase 4 v2 packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal, NamedTuple, Never, cast, overload

from tools.phase4_v2.ir import (
    FINAL_SCHEMA_REVISION,
    build_source_package,
    final_schema_document,
)
from tools.phase4_v2.preflight.execution import (
    CANDIDATE_CONTRACT_REVISION,
    CANDIDATE_CONTRACT_SHA256,
    CandidateRecord,
    InvocationRecord,
    PreparationError,
)
from tools.phase4_v2.preflight.registry import (
    PREPARATION_AUTHORITY_SCHEMA,
    PREPARATION_RECEIPT_REVISION,
    ActivatedPreparationAuthority,
    PreparationReceipt,
    load_activated_preparation_authority,
    validate_preparation_receipt_authority,
)
from tools.phase4_v2.raw_source import (
    AuthenticatedPackageLocalEvidence,
    PackageLocalEvidenceReauthenticationInput,
    RawSourceAuthenticationError,
    reauthenticate_package_local_evidence,
)
from tools.phase4_v2.validator import (
    PACKAGE_BOUND_VALIDATION_PROFILE,
    PACKAGE_CONTRACT_REVISION,
    VALIDATOR_REVISION,
    Diagnostic,
    ValidationReceipt,
    validate_package_local_validator_envelope,
)
from tools.phase4_v2.validator.binding import (
    PACKAGE_LOCAL_DOMAIN_RESULT_SCHEMA,
    ArtifactIdentityAttestation,
    EvidenceAnchorAttestation,
    EvidenceMemberAttestation,
    ValidatedRootEvidenceAttestation,
    ValidatedRootEvidenceMember,
)

from .core import (
    EQUIVALENCE_SCHEMA_REVISION,
    EXTRACTOR_CAPABILITY_REVISION,
    LEDGER_DECISION_REVISION,
    LOCAL_ONLY_DOMAINS,
    ApplicationRoot,
    AuthenticatedValidatorEnvelope,
    EquivalenceError,
    ExtractorCapability,
    FrozenPackageRef,
    LedgerDecision,
    Route,
    validate_frozen_package_ref,
)

PACKAGE_LOCAL_EVIDENCE_BINDING_REVISION = (
    "phase4-v2-package-local-evidence-binding-v1"
)
PACKAGE_LOCAL_PLAN_REVISION = "phase4-v2-package-local-plan-v4"
TARGET_ROOT_INVENTORY_REVISION = "phase4-v2-target-root-inventory-v1"
EXACT_REUSE_PINS_REVISION = "phase4-v2-exact-reuse-pins-v4"
ROOT_EXECUTION_PLAN_REVISION = "phase4-v2-root-execution-plan-v3"
PACKAGE_EXECUTION_PLAN_REVISION = "phase4-v2-package-execution-plan-v6"
VALIDATED_PACKAGE_OUTPUT_REVISION = "phase4-v2-validated-package-output-v7"
PACKAGE_QUEUE_UNIT_KIND = "validated-package-output"
PACKAGE_QUEUE_UNIT_PREFIX = "package-output"
PREPARATION_QUEUE_UNIT_KIND = "prepared-package-input"
PREPARATION_QUEUE_UNIT_PREFIX = "package-preparation"
PREPARATION_AUTHORITY_CAPABILITY = "phase4-v2-preparation-authority"
PREPARATION_REGISTRY_CAPABILITY = "phase4-v2-preparation-registry"
PREPARATION_EXECUTION_CAPABILITY = "phase4-v2-preparation-execution"
PREPARATION_CANDIDATE_CAPABILITY = "phase4-v2-preparation-candidate-contract"
PREPARATION_PIPELINE_CAPABILITY = "phase4-v2-preparation-pipeline"
SEMANTIC_ROOT_COMPLETION_REVISION = "phase4-v2-semantic-root-completion-v1"
PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION = "phase4-v2-package-validation-receipt-v1"
EXACT_REUSE_PIPELINE_CAPABILITY = "phase4-v2-exact-reuse"
EXACT_REUSE_AUTHORITY_CAPABILITY = "phase4-v2-exact-reuse-authority"
EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX = "exact-reuse-semantic-root"
EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX = "exact-reuse-ledger-decision"
EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX = "exact-reuse-direct-audit"
PACKAGE_PIPELINE_CAPABILITY = "phase4-v2-package-analysis"
SEMANTIC_ROOT_AUDIT_REVISION = "phase4-v2-semantic-root-audit-v2"
PACKAGE_REPORT_REVISION = "phase4-v2-package-report-v2"
PACKAGE_REPORT_SCHEMA_REVISION = "phase4-v2-package-report-schema-v3"
FINAL_IR_SCHEMA_CANONICAL_BYTES = json.dumps(
    final_schema_document(), sort_keys=True, separators=(",", ":")
).encode("utf-8")
FINAL_IR_SCHEMA_SHA256 = hashlib.sha256(FINAL_IR_SCHEMA_CANONICAL_BYTES).hexdigest()
PACKAGE_REPORT_SCHEMA_CANONICAL_BYTES = json.dumps(
    {
        "final_ir_schema_revision": FINAL_SCHEMA_REVISION,
        "final_ir_schema_sha256": FINAL_IR_SCHEMA_SHA256,
        "report_revision": PACKAGE_REPORT_REVISION,
        "package_local_domain_result_schema": PACKAGE_LOCAL_DOMAIN_RESULT_SCHEMA,
        "required_package_local_domains": list(LOCAL_ONLY_DOMAINS),
        "requires_authoritative_root_result_set": True,
        "requires_canonical_final_ir_json": True,
        "requires_final_ir_markdown_agreement": True,
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


def package_queue_unit_id(target_package_ref_id: str) -> str:
    """Return the reserved queue unit ID for one immutable package reference."""
    _sha(target_package_ref_id, "target_package_ref_id")
    return f"{PACKAGE_QUEUE_UNIT_PREFIX}:{target_package_ref_id}"


def preparation_queue_unit_id(target_package_ref_id: str) -> str:
    """Return the reserved preparation unit for one frozen package identity."""
    _sha(target_package_ref_id, "target_package_ref_id")
    return f"{PREPARATION_QUEUE_UNIT_PREFIX}:{target_package_ref_id}"


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


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            _fail("canonical content contains a duplicate object key")
        value[key] = item
    return value


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
    object.__setattr__(result, "inherited_semantic_root_sha256", inherited_semantic_root_sha256)
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


def package_validation_receipt_completion(package_ref: FrozenPackageRef) -> CompletionPin:
    """Return the completion that externally attests a frozen package receipt."""
    frozen = validate_frozen_package_ref(package_ref)
    return CompletionPin(
        f"package-validation-receipt:{frozen.content_id}",
        PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
        frozen.validation_receipt_sha256,
    )


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
class PackageLocalEvidenceBinding:
    """Plan pin for target-owned, raw-authenticated package-local evidence."""

    package_ref_id: str
    raw_receipt_sha256: str
    raw_authority_sha256: str
    validation_receipt_sha256: str
    source_package_id: str
    validator_evidence_sha256: str
    preparation_receipt_sha256: str
    target_inventory_receipt_sha256: str
    mandatory_domains: tuple[str, ...]
    evidence_member_ids: tuple[str, ...]
    evidence_anchor_ids: tuple[str, ...]
    producer_capabilities: tuple[CapabilityPin, ...]
    revision: str = PACKAGE_LOCAL_EVIDENCE_BINDING_REVISION

    def __post_init__(self) -> None:
        _sha(self.package_ref_id, "package-local evidence package reference")
        _sha(self.raw_receipt_sha256, "package-local raw receipt")
        _sha(self.raw_authority_sha256, "package-local raw authority")
        _sha(self.validation_receipt_sha256, "package-local validation receipt")
        _text(self.source_package_id, "package-local source package ID", 256)
        if (
            not self.source_package_id.startswith("pkg:")
            or _SHA.fullmatch(self.source_package_id[4:]) is None
        ):
            _fail("package-local source package ID is invalid")
        _sha(self.validator_evidence_sha256, "package-local validator evidence")
        _sha(self.preparation_receipt_sha256, "package-local preparation receipt")
        _sha(self.target_inventory_receipt_sha256, "package-local target inventory receipt")
        if self.mandatory_domains != tuple(sorted(LOCAL_ONLY_DOMAINS)):
            _fail("package-local evidence must cover the exact local domain set")
        for field, values in (
            ("package-local member IDs", self.evidence_member_ids),
            ("package-local anchor IDs", self.evidence_anchor_ids),
        ):
            if (
                type(values) is not tuple
                or not values
                or len(values) > _MAX_RECEIPT_ITEMS
                or any(type(item) is not str or not item for item in values)
                or values != tuple(sorted(set(values)))
            ):
                _fail(f"{field} must be a bounded sorted unique tuple")
        producers = _capability_tuple(
            self.producer_capabilities,
            "package-local evidence producer capabilities",
            nonempty=True,
        )
        object.__setattr__(self, "producer_capabilities", producers)
        _revision(
            self.revision,
            PACKAGE_LOCAL_EVIDENCE_BINDING_REVISION,
            "package-local evidence binding",
        )

    def to_data(self) -> dict[str, object]:
        return {
            "evidence_anchor_ids": list(self.evidence_anchor_ids),
            "evidence_member_ids": list(self.evidence_member_ids),
            "mandatory_domains": list(self.mandatory_domains),
            "package_ref_id": self.package_ref_id,
            "preparation_receipt_sha256": self.preparation_receipt_sha256,
            "producer_capabilities": [item.to_data() for item in self.producer_capabilities],
            "raw_receipt_sha256": self.raw_receipt_sha256,
            "raw_authority_sha256": self.raw_authority_sha256,
            "revision": self.revision,
            "source_package_id": self.source_package_id,
            "target_inventory_receipt_sha256": self.target_inventory_receipt_sha256,
            "validator_evidence_sha256": self.validator_evidence_sha256,
            "validation_receipt_sha256": self.validation_receipt_sha256,
        }

    @property
    def content_id(self) -> str:
        return _content_id("phase4-v2:package-local-evidence-binding", self.to_data())


def bind_package_local_evidence(
    *,
    package_ref: FrozenPackageRef,
    evidence: AuthenticatedPackageLocalEvidence,
    evidence_inputs: PackageLocalEvidenceReauthenticationInput,
    enriched_validator_envelope: AuthenticatedValidatorEnvelope,
) -> PackageLocalEvidenceBinding:
    """Bind local raw evidence and its non-circular validator attestation to a plan."""

    from .core import load_authenticated_validator_envelope

    package_ref = validate_frozen_package_ref(package_ref)
    try:
        local = reauthenticate_package_local_evidence(evidence, inputs=evidence_inputs)
        base = load_authenticated_validator_envelope(
            package_ref.validator_envelope_bytes,
            authority=package_ref.validator_authority,
        )
        enriched = validate_package_local_validator_envelope(
            base,
            enriched_validator_envelope,
            evidence=local,
            evidence_inputs=evidence_inputs,
        )
    except (EquivalenceError, RawSourceAuthenticationError, ValueError) as error:
        raise EquivalenceError("package-local evidence authentication failed") from error
    source_package_id, _source_package = build_source_package(
        enriched.report.validated_artifact_identity,
        enriched.report,
    )
    validator_evidence_sha256 = hashlib.sha256(
        _canonical_bytes(
            {
                "anchors": [item.to_data() for item in enriched.report.validated_evidence_anchors],
                "members": [item.to_data() for item in enriched.report.validated_evidence_members],
            }
        )
    ).hexdigest()
    producers = tuple(
        sorted(
            {
                CapabilityPin(item.producer_name, item.producer_revision, item.producer_digest)
                for item in local.members
            },
            key=lambda item: item.name,
        )
    )
    return PackageLocalEvidenceBinding(
        package_ref_id=package_ref.content_id,
        raw_receipt_sha256=local.receipt_sha256,
        raw_authority_sha256=local.authority.activation_sha256,
        validation_receipt_sha256=enriched.report.validation_receipt_sha256,
        source_package_id=source_package_id,
        validator_evidence_sha256=validator_evidence_sha256,
        preparation_receipt_sha256=local.preparation_receipt_sha256,
        target_inventory_receipt_sha256=local.target_inventory_receipt_sha256,
        mandatory_domains=local.mandatory_domains,
        evidence_member_ids=tuple(sorted(item.id for item in local.members)),
        evidence_anchor_ids=tuple(sorted(item.id for item in local.anchors)),
        producer_capabilities=producers,
    )


def _local_evidence(value: PackageLocalEvidenceBinding) -> PackageLocalEvidenceBinding:
    if type(value) is not PackageLocalEvidenceBinding:
        _fail("package-local plan requires exact authenticated evidence binding")
    return PackageLocalEvidenceBinding(
        value.package_ref_id,
        value.raw_receipt_sha256,
        value.raw_authority_sha256,
        value.validation_receipt_sha256,
        value.source_package_id,
        value.validator_evidence_sha256,
        value.preparation_receipt_sha256,
        value.target_inventory_receipt_sha256,
        value.mandatory_domains,
        value.evidence_member_ids,
        value.evidence_anchor_ids,
        value.producer_capabilities,
        value.revision,
    )


@dataclass(frozen=True, slots=True)
class PackageLocalPlan:
    target_package_ref_id: str
    package_name: str
    version_code: str
    version_name: str
    target_artifact_digest: str
    requirements_sha256: str
    pipeline_capability: CapabilityPin
    evidence_producer_capabilities: tuple[CapabilityPin, ...]
    evidence: PackageLocalEvidenceBinding
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
        producers = _capability_tuple(
            self.evidence_producer_capabilities,
            "package-local evidence producers",
            nonempty=True,
        )
        object.__setattr__(self, "evidence_producer_capabilities", producers)
        evidence = _local_evidence(self.evidence)
        if (
            evidence.package_ref_id != self.target_package_ref_id
            or evidence.mandatory_domains != tuple(sorted(self.mandatory_domains))
            or not set(evidence.producer_capabilities) <= set(producers)
        ):
            _fail("package-local evidence differs from its plan identity or producers")
        object.__setattr__(self, "evidence", evidence)
        _revision(self.revision, PACKAGE_LOCAL_PLAN_REVISION, "package-local plan revision")

    def to_data(self) -> dict[str, object]:
        return {
            "mandatory_domains": list(self.mandatory_domains),
            "package_name": self.package_name,
            "pipeline_capability": self.pipeline_capability.to_data(),
            "evidence_producer_capabilities": [
                item.to_data() for item in self.evidence_producer_capabilities
            ],
            "evidence": self.evidence.to_data(),
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
        value.evidence_producer_capabilities,
        value.evidence,
        value.mandatory_domains,
        value.revision,
    )


@dataclass(frozen=True, slots=True, init=False)
class PreparationPlanBinding:
    """Exact accepted preparation and activated capabilities required by a plan."""

    package_ref_id: str
    package_name: str
    version_code: str
    version_name: str
    artifact_digest: str
    preflight_sha256: str
    receipt_sha256: str
    completion: CompletionPin
    capabilities: tuple[CapabilityPin, ...]
    evidence_producer_capabilities: tuple[CapabilityPin, ...]

    def __init__(self) -> None:
        _fail("PreparationPlanBinding must be created from a trusted preparation receipt")

    def to_data(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "capabilities": [item.to_data() for item in self.capabilities],
            "evidence_producer_capabilities": [
                item.to_data() for item in self.evidence_producer_capabilities
            ],
            "completion": self.completion.to_data(),
            "package_name": self.package_name,
            "package_ref_id": self.package_ref_id,
            "preflight_sha256": self.preflight_sha256,
            "receipt_sha256": self.receipt_sha256,
            "version_code": self.version_code,
            "version_name": self.version_name,
        }


def preparation_capability_pins(
    authority: ActivatedPreparationAuthority,
) -> tuple[CapabilityPin, ...]:
    """Reconstruct the exact externally activated preparation capability set."""

    if type(authority) is not ActivatedPreparationAuthority:
        _fail("preparation requires an activated preparation authority")
    try:
        authority_bytes = _canonical_bytes(authority.to_data()) + b"\n"
    except (AttributeError, TypeError, ValueError) as error:
        raise EquivalenceError("preparation authority is invalid") from error
    try:
        restored_authority = load_activated_preparation_authority(authority_bytes)
    except ValueError as error:
        raise EquivalenceError("preparation authority activation is invalid") from error
    if restored_authority != authority:
        _fail("preparation authority does not reproduce its external activation")
    if authority.candidate_contract_sha256 != CANDIDATE_CONTRACT_SHA256:
        _fail("preparation authority uses an unsupported candidate contract")
    for value, field in (
        (authority.registry_revision, "authority.registry_revision"),
        (authority.pipeline_revision, "authority.pipeline_revision"),
        (authority.execution_profile_revision, "authority.execution_profile_revision"),
    ):
        _token(value, field)
    for value, field in (
        (authority.activation_sha256, "authority.activation_sha256"),
        (authority.registry_sha256, "authority.registry_sha256"),
        (authority.execution_profile_sha256, "authority.execution_profile_sha256"),
        (authority.candidate_contract_sha256, "authority.candidate_contract_sha256"),
    ):
        _sha(value, field)
    return tuple(
        sorted(
            (
                CapabilityPin(
                    PREPARATION_AUTHORITY_CAPABILITY,
                    PREPARATION_AUTHORITY_SCHEMA,
                    authority.activation_sha256,
                ),
                CapabilityPin(
                    PREPARATION_CANDIDATE_CAPABILITY,
                    CANDIDATE_CONTRACT_REVISION,
                    authority.candidate_contract_sha256,
                ),
                CapabilityPin(
                    PREPARATION_EXECUTION_CAPABILITY,
                    authority.execution_profile_revision,
                    authority.execution_profile_sha256,
                ),
                CapabilityPin(
                    PREPARATION_PIPELINE_CAPABILITY,
                    authority.pipeline_revision,
                    authority.registry_sha256,
                ),
                CapabilityPin(
                    PREPARATION_REGISTRY_CAPABILITY,
                    authority.registry_revision,
                    authority.registry_sha256,
                ),
            ),
            key=lambda item: item.name,
        )
    )


def _validated_preparation_receipt(
    receipt: PreparationReceipt,
    authority: ActivatedPreparationAuthority,
) -> tuple[str, tuple[CapabilityPin, ...]]:
    if type(receipt) is not PreparationReceipt:
        _fail("preparation binding requires an exact PreparationReceipt")
    capabilities = preparation_capability_pins(authority)
    if receipt.revision != PREPARATION_RECEIPT_REVISION:
        _fail("preparation receipt revision is unsupported")
    if (
        receipt.authority_sha256,
        receipt.tool_registry_sha256,
        receipt.pipeline_revision,
        receipt.execution_profile_revision,
        receipt.execution_profile_sha256,
        receipt.candidate_contract_sha256,
    ) != (
        authority.activation_sha256,
        authority.registry_sha256,
        authority.pipeline_revision,
        authority.execution_profile_revision,
        authority.execution_profile_sha256,
        authority.candidate_contract_sha256,
    ):
        _fail("preparation receipt does not match its activated authority")
    if type(receipt.invocations) is not tuple or any(
        type(item) is not InvocationRecord for item in receipt.invocations
    ):
        _fail("preparation receipt contains invalid invocation records")
    if type(receipt.candidates) is not tuple or any(
        type(item) is not CandidateRecord for item in receipt.candidates
    ):
        _fail("preparation receipt contains invalid candidate records")
    for value, field in (
        (receipt.artifact_digest, "receipt.artifact_digest"),
        (receipt.preflight_manifest_sha256, "receipt.preflight_manifest_sha256"),
        (receipt.manifest_sha256, "receipt.manifest_sha256"),
        (receipt.candidate_index_sha256, "receipt.candidate_index_sha256"),
    ):
        _sha(value, field)
    if type(receipt.package_name) is not str or _PACKAGE.fullmatch(receipt.package_name) is None:
        _fail("preparation receipt package name is invalid")
    _text(receipt.version_code, "receipt.version_code", 256)
    _text(receipt.version_name, "receipt.version_name", 256)
    try:
        receipt_sha256 = receipt.content_id
        _ = _canonical_bytes(receipt.to_data())
    except (AttributeError, TypeError, ValueError) as error:
        raise EquivalenceError("preparation receipt is invalid") from error
    _sha(receipt_sha256, "receipt.content_id")
    return receipt_sha256, capabilities


def _preparation_evidence_producers(
    receipt: PreparationReceipt,
) -> tuple[CapabilityPin, ...]:
    producers: dict[str, CapabilityPin] = {}
    for invocation in receipt.invocations:
        if invocation.status != "COMPLETE":
            continue
        if not invocation.outputs or invocation.tool.binary_sha256 is None:
            _fail("complete preparation producer has no output or binary digest")
        producer = CapabilityPin(
            invocation.route,
            receipt.pipeline_revision,
            invocation.tool.binary_sha256,
        )
        previous = producers.setdefault(producer.name, producer)
        if previous != producer:
            _fail("preparation route has ambiguous evidence producers")
    return _capability_tuple(
        tuple(sorted(producers.values(), key=lambda item: item.name)),
        "preparation evidence producers",
        nonempty=True,
    )


def preparation_evidence_producer_capabilities(
    receipt: PreparationReceipt,
    authority: ActivatedPreparationAuthority,
) -> tuple[CapabilityPin, ...]:
    """Derive exact report-lineage producer pins from an authenticated preparation."""

    try:
        restored = validate_preparation_receipt_authority(receipt, authority)
    except PreparationError as error:
        raise EquivalenceError("preparation producer authentication failed") from error
    return _preparation_evidence_producers(restored)


def _new_accepted_preparation_plan_binding(
    *,
    package_ref: FrozenPackageRef,
    package_local: PackageLocalPlan,
    receipt: PreparationReceipt,
    authority: ActivatedPreparationAuthority,
) -> PreparationPlanBinding:
    """Bind one validated receipt to the package plan and external activation."""

    package_ref = validate_frozen_package_ref(package_ref)
    local = _local(package_local)
    receipt_sha256, capabilities = _validated_preparation_receipt(receipt, authority)
    evidence_producers = preparation_evidence_producer_capabilities(receipt, authority)
    package_ref_id = package_ref.content_id
    if local.target_package_ref_id != package_ref_id or (
        receipt.package_name,
        receipt.version_code,
        receipt.version_name,
        receipt.artifact_digest,
        receipt.preflight_manifest_sha256,
    ) != (
        local.package_name,
        local.version_code,
        local.version_name,
        local.target_artifact_digest,
        local.requirements_sha256,
    ):
        _fail("preparation receipt does not match the frozen package plan identity")
    completion = CompletionPin(
        preparation_queue_unit_id(package_ref_id),
        PREPARATION_RECEIPT_REVISION,
        receipt_sha256,
    )
    result = object.__new__(PreparationPlanBinding)
    values: dict[str, object] = {
        "package_ref_id": package_ref_id,
        "package_name": local.package_name,
        "version_code": local.version_code,
        "version_name": local.version_name,
        "artifact_digest": local.target_artifact_digest,
        "preflight_sha256": local.requirements_sha256,
        "receipt_sha256": receipt_sha256,
        "completion": completion,
        "capabilities": capabilities,
        "evidence_producer_capabilities": evidence_producers,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


def _preparation(value: PreparationPlanBinding) -> PreparationPlanBinding:
    if type(value) is not PreparationPlanBinding:
        _fail("plan requires an exact PreparationPlanBinding")
    completion = _completion(value.completion, "preparation completion")
    capabilities = _capability_tuple(
        value.capabilities,
        "preparation capabilities",
        nonempty=True,
    )
    evidence_producers = _capability_tuple(
        value.evidence_producer_capabilities,
        "preparation evidence producers",
        nonempty=True,
    )
    if completion.parent_unit_id != preparation_queue_unit_id(value.package_ref_id):
        _fail("preparation completion belongs to another package")
    _revision(completion.revision, PREPARATION_RECEIPT_REVISION, "preparation completion")
    if completion.digest != value.receipt_sha256:
        _fail("preparation completion does not bind its receipt")
    expected_names = {
        PREPARATION_AUTHORITY_CAPABILITY,
        PREPARATION_CANDIDATE_CAPABILITY,
        PREPARATION_EXECUTION_CAPABILITY,
        PREPARATION_PIPELINE_CAPABILITY,
        PREPARATION_REGISTRY_CAPABILITY,
    }
    if {item.name for item in capabilities} != expected_names:
        _fail("preparation capabilities are incomplete")
    for name, field in (
        (value.package_ref_id, "preparation.package_ref_id"),
        (value.artifact_digest, "preparation.artifact_digest"),
        (value.preflight_sha256, "preparation.preflight_sha256"),
        (value.receipt_sha256, "preparation.receipt_sha256"),
    ):
        _sha(name, field)
    if type(value.package_name) is not str or _PACKAGE.fullmatch(value.package_name) is None:
        _fail("preparation package name is invalid")
    _text(value.version_code, "preparation.version_code", 256)
    _text(value.version_name, "preparation.version_name", 256)
    result = object.__new__(PreparationPlanBinding)
    for name in value.__dataclass_fields__:
        object.__setattr__(result, name, getattr(value, name))
    object.__setattr__(result, "completion", completion)
    object.__setattr__(result, "capabilities", capabilities)
    object.__setattr__(result, "evidence_producer_capabilities", evidence_producers)
    return result


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


@dataclass(frozen=True, slots=True, init=False)
class AcceptedTargetRootInventory:
    inventory: TargetRootInventory
    completion: CompletionPin
    authority_sha256: str
    canonical_envelope: bytes
    authority: object
    package_ref: FrozenPackageRef
    extractor: ExtractorCapability

    def __init__(self) -> None:
        _fail("accepted inventories derive only from an authenticated inventory envelope")

    def __post_init__(self) -> None:
        inventory = _inventory(self.inventory)
        completion = _completion(self.completion, "target inventory completion")
        _revision(completion.revision, TARGET_ROOT_INVENTORY_REVISION, "inventory completion")
        if completion.digest != inventory.content_id:
            _fail("target inventory completion does not accept this exact inventory")
        _sha(self.authority_sha256, "target inventory authority")
        if type(self.canonical_envelope) is not bytes:
            _fail("accepted target inventory requires exact authenticated envelope bytes")
        object.__setattr__(self, "inventory", inventory)
        object.__setattr__(self, "completion", completion)

    def to_data(self) -> dict[str, object]:
        return {
            "authority_sha256": self.authority_sha256,
            "completion": self.completion.to_data(),
            "envelope_sha256": hashlib.sha256(self.canonical_envelope).hexdigest(),
            "inventory": self.inventory.to_data(),
        }


def _accepted_inventory(value: AcceptedTargetRootInventory) -> AcceptedTargetRootInventory:
    from .inventory import validate_accepted_target_inventory

    return validate_accepted_target_inventory(value)


@dataclass(frozen=True, slots=True, init=False)
class SemanticRootAudit:
    source_root: ApplicationRoot
    ledger_decision: LedgerDecision
    extractor: ExtractorCapability
    accepted_target_inventory: AcceptedTargetRootInventory
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
    exact_reuse_prerequisite_receipt_sha256: str
    exact_reuse_prerequisite_capabilities: tuple[CapabilityPin, ...]
    binding_sha256: str
    revision: str

    def __init__(self) -> None:
        _fail("SemanticRootAudit must be created by its typed evidence factory")

    def to_data(self) -> dict[str, object]:
        return {
            "accepted_target_inventory": self.accepted_target_inventory.to_data(),
            "direct_semantic_audit_completion": self.direct_semantic_audit_completion.to_data(),
            "equivalence_pipeline": self.equivalence_pipeline.to_data(),
            "exact_reuse_prerequisite_capabilities": [
                item.to_data() for item in self.exact_reuse_prerequisite_capabilities
            ],
            "exact_reuse_prerequisite_receipt_sha256": (
                self.exact_reuse_prerequisite_receipt_sha256
            ),
            "extractor_capability": self.extractor_capability.to_data(),
            "extractor": self.extractor.to_data(),
            "extractor_capability_id": self.extractor_capability_id,
            "inherited_semantic_root_sha256": self.inherited_semantic_root_sha256,
            "inherited_semantic_root_completion": (
                self.inherited_semantic_root_completion.to_data()
            ),
            "ledger_decision_completion": self.ledger_decision_completion.to_data(),
            "ledger_decision": self.ledger_decision.to_data(),
            "revision": self.revision,
            "source_root_id": self.source_root_id,
            "source_root": self.source_root.to_data(),
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
    exact_reuse_prerequisite_receipt_sha256: str,
    exact_reuse_prerequisite_capabilities: tuple[CapabilityPin, ...],
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
    semantic_root_completion = _semantic_root_completion(inherited_semantic_root_completion)
    semantic_root_pin = semantic_root_completion.completion
    extractor_pin = _capability(extractor_capability, "semantic audit extractor")
    pipeline_pin = _capability(equivalence_pipeline, "semantic audit pipeline")
    _sha(
        exact_reuse_prerequisite_receipt_sha256,
        "semantic audit exact-reuse prerequisite receipt",
    )
    prerequisite_receipt = exact_reuse_prerequisite_receipt_sha256
    prerequisite_capabilities = _capability_tuple(
        exact_reuse_prerequisite_capabilities,
        "semantic audit exact-reuse prerequisite capabilities",
        nonempty=True,
    )
    _sha(inherited_semantic_root_sha256, "semantic audit inherited root")
    _revision(
        semantic_root_pin.revision,
        SEMANTIC_ROOT_COMPLETION_REVISION,
        "semantic root completion",
    )
    if (
        semantic_root_completion.source_root_id != source_root.content_id
        or semantic_root_completion.inherited_semantic_root_sha256 != inherited_semantic_root_sha256
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
    prerequisite_by_name = {item.name: item for item in prerequisite_capabilities}
    if (
        EXACT_REUSE_AUTHORITY_CAPABILITY not in prerequisite_by_name
        or prerequisite_by_name.get(pipeline_pin.name) != pipeline_pin
        or prerequisite_by_name.get(extractor_pin.name) != extractor_pin
    ):
        _fail("semantic audit prerequisite capabilities omit its authenticated route")
    expected_units = (
        f"{EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX}:{prerequisite_receipt}",
        f"{EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX}:{prerequisite_receipt}",
        f"{EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX}:{prerequisite_receipt}",
    )
    if (
        semantic_root_pin.parent_unit_id,
        ledger_pin.parent_unit_id,
        audit_pin.parent_unit_id,
    ) != expected_units:
        _fail("semantic audit completions do not derive from one signed prerequisite")
    values: dict[str, object] = {
        "source_root": replace(source_root),
        "ledger_decision": replace(ledger_decision),
        "extractor": replace(extractor),
        "accepted_target_inventory": _accepted_inventory(accepted_target_inventory),
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
        "exact_reuse_prerequisite_receipt_sha256": prerequisite_receipt,
        "exact_reuse_prerequisite_capabilities": prerequisite_capabilities,
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
            "direct_semantic_audit_completion": pin_data("direct_semantic_audit_completion"),
            "equivalence_pipeline": pin_data("equivalence_pipeline"),
            "exact_reuse_prerequisite_capabilities": [
                item.to_data()
                for item in cast(
                    tuple[CapabilityPin, ...],
                    values["exact_reuse_prerequisite_capabilities"],
                )
            ],
            "exact_reuse_prerequisite_receipt_sha256": values[
                "exact_reuse_prerequisite_receipt_sha256"
            ],
            "extractor_capability": pin_data("extractor_capability"),
            "extractor_capability_id": values["extractor_capability_id"],
            "inherited_semantic_root_completion": pin_data("inherited_semantic_root_completion"),
            "inherited_semantic_root_sha256": values["inherited_semantic_root_sha256"],
            "ledger_decision_completion": pin_data("ledger_decision_completion"),
            "revision": values["revision"],
            "source_root_id": values["source_root_id"],
            "target_inventory_completion": pin_data("target_inventory_completion"),
            "target_occurrence_identity_sha256": values["target_occurrence_identity_sha256"],
            "target_root_id": values["target_root_id"],
        },
    )


def _semantic_audit(value: SemanticRootAudit) -> SemanticRootAudit:
    if type(value) is not SemanticRootAudit:
        _fail("exact reuse requires an exact typed SemanticRootAudit")
    try:
        source_root = replace(value.source_root)
        ledger_decision = replace(value.ledger_decision)
        extractor = replace(value.extractor)
        accepted_inventory = _accepted_inventory(value.accepted_target_inventory)
    except AttributeError as error:
        raise EquivalenceError("semantic audit is missing its typed source records") from error
    extractor_pin = _capability(value.extractor_capability, "semantic audit extractor")
    if extractor_pin.digest != extractor.content_id:
        _fail("semantic audit extractor relation no longer reproduces")
    semantic_root_pin = _completion(
        value.inherited_semantic_root_completion,
        "semantic audit inherited root completion",
    )
    semantic_root_completion = build_semantic_root_completion(
        source_root=source_root,
        inherited_semantic_root_sha256=value.inherited_semantic_root_sha256,
        parent_unit_id=semantic_root_pin.parent_unit_id,
    )
    if semantic_root_completion.completion != semantic_root_pin:
        _fail("semantic root completion relation no longer reproduces")
    binding_values = {
        "direct_semantic_audit_completion": value.direct_semantic_audit_completion,
        "equivalence_pipeline": value.equivalence_pipeline,
        "exact_reuse_prerequisite_capabilities": value.exact_reuse_prerequisite_capabilities,
        "exact_reuse_prerequisite_receipt_sha256": (
            value.exact_reuse_prerequisite_receipt_sha256
        ),
        "extractor_capability": extractor_pin,
        "extractor_capability_id": value.extractor_capability_id,
        "inherited_semantic_root_completion": value.inherited_semantic_root_completion,
        "inherited_semantic_root_sha256": value.inherited_semantic_root_sha256,
        "ledger_decision_completion": value.ledger_decision_completion,
        "revision": value.revision,
        "source_root_id": value.source_root_id,
        "target_inventory_completion": value.target_inventory_completion,
        "target_occurrence_identity_sha256": value.target_occurrence_identity_sha256,
        "target_root_id": value.target_root_id,
    }
    if value.binding_sha256 != _semantic_audit_binding_sha256(binding_values):
        _fail("semantic audit binding no longer reproduces its typed relationships")
    rebuilt = build_semantic_root_audit(
        source_root=source_root,
        ledger_decision=ledger_decision,
        extractor=extractor,
        accepted_target_inventory=accepted_inventory,
        inherited_semantic_root_sha256=value.inherited_semantic_root_sha256,
        inherited_semantic_root_completion=semantic_root_completion,
        target_inventory_completion=value.target_inventory_completion,
        ledger_decision_completion=value.ledger_decision_completion,
        direct_semantic_audit_completion=value.direct_semantic_audit_completion,
        extractor_capability=value.extractor_capability,
        equivalence_pipeline=value.equivalence_pipeline,
        exact_reuse_prerequisite_receipt_sha256=(
            value.exact_reuse_prerequisite_receipt_sha256
        ),
        exact_reuse_prerequisite_capabilities=(
            value.exact_reuse_prerequisite_capabilities
        ),
    )
    if rebuilt.to_data() != value.to_data():
        _fail("semantic audit source relationships no longer reproduce")
    return rebuilt


@dataclass(frozen=True, slots=True, init=False)
class ExactReusePins:
    source_root_id: str
    target_root_id: str
    target_occurrence_identity_sha256: str
    inherited_semantic_root_sha256: str
    byte_identity_proof_id: str
    inherited_semantic_root_completion: CompletionPin
    target_inventory_completion: CompletionPin
    ledger_decision_completion: CompletionPin
    direct_semantic_audit_completion: CompletionPin
    extractor_capability: CapabilityPin
    equivalence_pipeline: CapabilityPin
    exact_reuse_prerequisite_receipt_sha256: str
    exact_reuse_prerequisite_capabilities: tuple[CapabilityPin, ...]
    extractor_record_revision: str = EXTRACTOR_CAPABILITY_REVISION
    revision: str = EXACT_REUSE_PINS_REVISION

    def __init__(self) -> None:
        _fail("ExactReusePins must be created from a typed SemanticRootAudit")

    def __post_init__(self) -> None:
        _sha(self.source_root_id, "reuse.source_root_id")
        _sha(self.target_root_id, "reuse.target_root_id")
        _sha(self.target_occurrence_identity_sha256, "reuse.occurrence")
        _sha(self.inherited_semantic_root_sha256, "reuse.semantic_root")
        _sha(self.byte_identity_proof_id, "reuse.byte_identity_proof_id")
        _sha(
            self.exact_reuse_prerequisite_receipt_sha256,
            "reuse exact-reuse prerequisite receipt",
        )
        semantic_root = _completion(
            self.inherited_semantic_root_completion, "reuse semantic root completion"
        )
        inventory = _completion(self.target_inventory_completion, "reuse inventory")
        ledger = _completion(self.ledger_decision_completion, "reuse ledger")
        audit = _completion(self.direct_semantic_audit_completion, "reuse semantic audit")
        extractor = _capability(self.extractor_capability, "reuse extractor")
        pipeline = _capability(self.equivalence_pipeline, "reuse pipeline")
        prerequisite_capabilities = _capability_tuple(
            self.exact_reuse_prerequisite_capabilities,
            "reuse exact-reuse prerequisite capabilities",
            nonempty=True,
        )
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
        expected_units = (
            f"{EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX}:{self.exact_reuse_prerequisite_receipt_sha256}",
            f"{EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX}:{self.exact_reuse_prerequisite_receipt_sha256}",
            f"{EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX}:{self.exact_reuse_prerequisite_receipt_sha256}",
        )
        if (
            semantic_root.parent_unit_id,
            ledger.parent_unit_id,
            audit.parent_unit_id,
        ) != expected_units:
            _fail("reuse completions do not derive from one signed prerequisite")
        object.__setattr__(self, "target_inventory_completion", inventory)
        object.__setattr__(self, "ledger_decision_completion", ledger)
        object.__setattr__(self, "direct_semantic_audit_completion", audit)
        object.__setattr__(self, "inherited_semantic_root_completion", semantic_root)
        object.__setattr__(self, "extractor_capability", extractor)
        object.__setattr__(self, "equivalence_pipeline", pipeline)
        object.__setattr__(
            self,
            "exact_reuse_prerequisite_capabilities",
            prerequisite_capabilities,
        )
        _revision(self.revision, EXACT_REUSE_PINS_REVISION, "reuse pins revision")

    def to_data(self) -> dict[str, object]:
        return {
            "direct_semantic_audit_completion": self.direct_semantic_audit_completion.to_data(),
            "equivalence_pipeline": self.equivalence_pipeline.to_data(),
            "exact_reuse_prerequisite_capabilities": [
                item.to_data() for item in self.exact_reuse_prerequisite_capabilities
            ],
            "exact_reuse_prerequisite_receipt_sha256": (
                self.exact_reuse_prerequisite_receipt_sha256
            ),
            "extractor_capability": self.extractor_capability.to_data(),
            "extractor_record_revision": self.extractor_record_revision,
            "inherited_semantic_root_sha256": self.inherited_semantic_root_sha256,
            "byte_identity_proof_id": self.byte_identity_proof_id,
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
        byte_identity_proof_id=value.byte_identity_proof_id,
        inherited_semantic_root_completion=value.inherited_semantic_root_completion,
        target_inventory_completion=value.target_inventory_completion,
        ledger_decision_completion=value.ledger_decision_completion,
        direct_semantic_audit_completion=value.direct_semantic_audit_completion,
        extractor_capability=value.extractor_capability,
        equivalence_pipeline=value.equivalence_pipeline,
        exact_reuse_prerequisite_receipt_sha256=(
            value.exact_reuse_prerequisite_receipt_sha256
        ),
        exact_reuse_prerequisite_capabilities=(
            value.exact_reuse_prerequisite_capabilities
        ),
        extractor_record_revision=value.extractor_record_revision,
        revision=value.revision,
    )


def _new_reuse_pins(
    *,
    source_root_id: str,
    target_root_id: str,
    target_occurrence_identity_sha256: str,
    inherited_semantic_root_sha256: str,
    byte_identity_proof_id: str,
    inherited_semantic_root_completion: CompletionPin,
    target_inventory_completion: CompletionPin,
    ledger_decision_completion: CompletionPin,
    direct_semantic_audit_completion: CompletionPin,
    extractor_capability: CapabilityPin,
    equivalence_pipeline: CapabilityPin,
    exact_reuse_prerequisite_receipt_sha256: str,
    exact_reuse_prerequisite_capabilities: tuple[CapabilityPin, ...],
    extractor_record_revision: str = EXTRACTOR_CAPABILITY_REVISION,
    revision: str = EXACT_REUSE_PINS_REVISION,
) -> ExactReusePins:
    result = object.__new__(ExactReusePins)
    for field, value in (
        ("source_root_id", source_root_id),
        ("target_root_id", target_root_id),
        ("target_occurrence_identity_sha256", target_occurrence_identity_sha256),
        ("inherited_semantic_root_sha256", inherited_semantic_root_sha256),
        ("byte_identity_proof_id", byte_identity_proof_id),
        ("inherited_semantic_root_completion", inherited_semantic_root_completion),
        ("target_inventory_completion", target_inventory_completion),
        ("ledger_decision_completion", ledger_decision_completion),
        ("direct_semantic_audit_completion", direct_semantic_audit_completion),
        ("extractor_capability", extractor_capability),
        ("equivalence_pipeline", equivalence_pipeline),
        (
            "exact_reuse_prerequisite_receipt_sha256",
            exact_reuse_prerequisite_receipt_sha256,
        ),
        ("exact_reuse_prerequisite_capabilities", exact_reuse_prerequisite_capabilities),
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
        byte_identity_proof_id=cast(str, audit.ledger_decision.byte_identity_proof_id),
        inherited_semantic_root_completion=semantic_root,
        target_inventory_completion=inventory,
        ledger_decision_completion=ledger,
        direct_semantic_audit_completion=direct,
        extractor_capability=extractor,
        equivalence_pipeline=pipeline,
        exact_reuse_prerequisite_receipt_sha256=(
            audit.exact_reuse_prerequisite_receipt_sha256
        ),
        exact_reuse_prerequisite_capabilities=(
            audit.exact_reuse_prerequisite_capabilities
        ),
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
    byte_count = 0
    for value in values:
        copied = _capability(value, "aggregate capability")
        previous = indexed.get(copied.name)
        if previous is not None and previous != copied:
            _fail(f"conflicting capability pins for {copied.name!r}")
        if previous is not None:
            continue
        if len(indexed) >= _MAX_GLOBAL_REQUIREMENTS:
            _fail("global capability requirement count exceeds its limit")
        byte_count += len(copied.name) + len(copied.revision) + len(copied.digest)
        if byte_count > _MAX_GLOBAL_REQUIREMENT_BYTES:
            _fail("global capability requirement byte budget exceeded")
        indexed[copied.name] = copied
    return tuple(sorted(indexed.values(), key=lambda item: item.name))


def _merge_completions(values: Iterable[CompletionPin]) -> tuple[CompletionPin, ...]:
    indexed: dict[str, CompletionPin] = {}
    byte_count = 0
    for value in values:
        copied = _completion(value, "aggregate completion")
        previous = indexed.get(copied.parent_unit_id)
        if previous is not None and previous != copied:
            _fail(f"conflicting completion pins for {copied.parent_unit_id!r}")
        if previous is not None:
            continue
        if len(indexed) >= _MAX_GLOBAL_REQUIREMENTS:
            _fail("global completion requirement count exceeds its limit")
        byte_count += len(copied.parent_unit_id) + len(copied.revision) + len(copied.digest)
        if byte_count > _MAX_GLOBAL_REQUIREMENT_BYTES:
            _fail("global completion requirement byte budget exceeded")
        indexed[copied.parent_unit_id] = copied
    return tuple(sorted(indexed.values(), key=lambda item: item.parent_unit_id))


class PackagePlanStatus(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PackageExecutionPlan:
    """Mutable-boundary input; freeze it before treating it as a trust proof."""

    target_package_ref_id: str
    target_package_ref: FrozenPackageRef
    cluster_id: str
    package_local: PackageLocalPlan
    preparation: PreparationPlanBinding
    accepted_target_inventory: AcceptedTargetRootInventory
    root_plans: tuple[RootExecutionPlan, ...]
    revision: str = PACKAGE_EXECUTION_PLAN_REVISION

    def __post_init__(self) -> None:
        _sha(self.target_package_ref_id, "plan.target_package_ref_id")
        _token(self.cluster_id, "plan.cluster_id")
        target_package_ref = validate_frozen_package_ref(self.target_package_ref)
        local = _local(self.package_local)
        preparation = _preparation(self.preparation)
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
        if local.requirements_sha256 != target_package_ref.preflight_sha256:
            _fail("package-local requirements do not match the frozen package preflight")
        if local.target_package_ref_id != self.target_package_ref_id:
            _fail("package-local plan targets a different package")
        if (
            preparation.package_ref_id,
            preparation.package_name,
            preparation.version_code,
            preparation.version_name,
            preparation.artifact_digest,
            preparation.preflight_sha256,
        ) != (
            self.target_package_ref_id,
            local.package_name,
            local.version_code,
            local.version_name,
            local.target_artifact_digest,
            local.requirements_sha256,
        ):
            _fail("preparation binding targets a different package plan")
        if (
            local.evidence_producer_capabilities
            != preparation.evidence_producer_capabilities
        ):
            _fail("package-local evidence producers differ from accepted preparation routes")
        if accepted.inventory.target_package_ref_id != self.target_package_ref_id:
            _fail("target-root inventory targets a different package")
        if (
            local.evidence.preparation_receipt_sha256 != preparation.receipt_sha256
            or local.evidence.target_inventory_receipt_sha256
            != hashlib.sha256(accepted.canonical_envelope).hexdigest()
        ):
            _fail("package-local evidence pins transplanted preparation or inventory")
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
        object.__setattr__(self, "preparation", preparation)
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
            from .inventory import (
                inventory_authority_capability,
                inventory_extractor_capability,
            )

            yield self.package_local.pipeline_capability
            yield from self.package_local.evidence_producer_capabilities
            yield from self.preparation.capabilities
            yield inventory_authority_capability(self.accepted_target_inventory.authority)
            yield inventory_extractor_capability(self.accepted_target_inventory.extractor)
            for item in self.root_plans:
                if type(item) is ExactReuseRootPlan:
                    yield from item.reuse.exact_reuse_prerequisite_capabilities
                    yield item.reuse.extractor_capability
                    yield item.reuse.equivalence_pipeline
                elif type(item) is FullAnalysisRootPlan:
                    yield from item.analysis_capabilities

        return _merge_capabilities(values())

    @property
    def required_completions(self) -> tuple[CompletionPin, ...]:
        def values() -> Iterable[CompletionPin]:
            yield self.preparation.completion
            yield package_validation_receipt_completion(self.target_package_ref)
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
            "cluster_id": self.cluster_id,
            "package_local": self.package_local.to_data(),
            "preparation": self.preparation.to_data(),
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


class FrozenPreparationPlanBinding(NamedTuple):
    """Tuple-backed accepted preparation identity carried across trust boundaries."""

    package_ref_id: str
    package_name: str
    version_code: str
    version_name: str
    artifact_digest: str
    preflight_sha256: str
    receipt_sha256: str
    completion: FrozenCompletionPin
    capabilities: tuple[FrozenCapabilityPin, ...]
    evidence_producer_capabilities: tuple[FrozenCapabilityPin, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "capabilities": [
                {"digest": item.digest, "name": item.name, "revision": item.revision}
                for item in self.capabilities
            ],
            "evidence_producer_capabilities": [
                {"digest": item.digest, "name": item.name, "revision": item.revision}
                for item in self.evidence_producer_capabilities
            ],
            "completion": {
                "digest": self.completion.digest,
                "parent_unit_id": self.completion.parent_unit_id,
                "revision": self.completion.revision,
            },
            "package_name": self.package_name,
            "package_ref_id": self.package_ref_id,
            "preflight_sha256": self.preflight_sha256,
            "receipt_sha256": self.receipt_sha256,
            "version_code": self.version_code,
            "version_name": self.version_name,
        }


class FrozenPackageLocalEvidenceBinding(NamedTuple):
    """Tuple-backed target-local evidence identity carried to reconciliation."""

    package_ref_id: str
    raw_receipt_sha256: str
    raw_authority_sha256: str
    validation_receipt_sha256: str
    source_package_id: str
    validator_evidence_sha256: str
    preparation_receipt_sha256: str
    target_inventory_receipt_sha256: str
    mandatory_domains: tuple[str, ...]
    evidence_member_ids: tuple[str, ...]
    evidence_anchor_ids: tuple[str, ...]
    producer_capabilities: tuple[FrozenCapabilityPin, ...]
    revision: str

    def to_data(self) -> dict[str, object]:
        return {
            "evidence_anchor_ids": list(self.evidence_anchor_ids),
            "evidence_member_ids": list(self.evidence_member_ids),
            "mandatory_domains": list(self.mandatory_domains),
            "package_ref_id": self.package_ref_id,
            "preparation_receipt_sha256": self.preparation_receipt_sha256,
            "producer_capabilities": [
                {"digest": item.digest, "name": item.name, "revision": item.revision}
                for item in self.producer_capabilities
            ],
            "raw_receipt_sha256": self.raw_receipt_sha256,
            "raw_authority_sha256": self.raw_authority_sha256,
            "revision": self.revision,
            "source_package_id": self.source_package_id,
            "target_inventory_receipt_sha256": self.target_inventory_receipt_sha256,
            "validator_evidence_sha256": self.validator_evidence_sha256,
            "validation_receipt_sha256": self.validation_receipt_sha256,
        }


def _frozen_capability(value: CapabilityPin) -> FrozenCapabilityPin:
    copied = _capability(value, "frozen capability")
    return FrozenCapabilityPin(copied.name, copied.revision, copied.digest)


def _frozen_completion(value: CompletionPin) -> FrozenCompletionPin:
    copied = _completion(value, "frozen completion")
    return FrozenCompletionPin(copied.parent_unit_id, copied.revision, copied.digest)


def _frozen_preparation(value: PreparationPlanBinding) -> FrozenPreparationPlanBinding:
    copied = _preparation(value)
    return FrozenPreparationPlanBinding(
        package_ref_id=copied.package_ref_id,
        package_name=copied.package_name,
        version_code=copied.version_code,
        version_name=copied.version_name,
        artifact_digest=copied.artifact_digest,
        preflight_sha256=copied.preflight_sha256,
        receipt_sha256=copied.receipt_sha256,
        completion=_frozen_completion(copied.completion),
        capabilities=tuple(_frozen_capability(item) for item in copied.capabilities),
        evidence_producer_capabilities=tuple(
            _frozen_capability(item) for item in copied.evidence_producer_capabilities
        ),
    )


def _frozen_local_evidence(
    value: PackageLocalEvidenceBinding,
) -> FrozenPackageLocalEvidenceBinding:
    copied = _local_evidence(value)
    return FrozenPackageLocalEvidenceBinding(
        copied.package_ref_id,
        copied.raw_receipt_sha256,
        copied.raw_authority_sha256,
        copied.validation_receipt_sha256,
        copied.source_package_id,
        copied.validator_evidence_sha256,
        copied.preparation_receipt_sha256,
        copied.target_inventory_receipt_sha256,
        copied.mandatory_domains,
        copied.evidence_member_ids,
        copied.evidence_anchor_ids,
        tuple(_frozen_capability(item) for item in copied.producer_capabilities),
        copied.revision,
    )


@dataclass(frozen=True, slots=True, init=False)
class FrozenPackageExecutionPlan:
    """Canonical immutable snapshot consumed by trust-sensitive adapters."""

    target_package_ref_id: str
    cluster_id: str
    canonical_bytes: bytes
    digest: str
    status: PackagePlanStatus
    root_count: int
    package_name: str
    version_code: str
    version_name: str
    target_artifact_digest: str
    preflight_sha256: str
    preparation: FrozenPreparationPlanBinding
    package_local_evidence: FrozenPackageLocalEvidenceBinding
    inherited_semantic_roots: tuple[str, ...]
    semantic_audit_completion_digests: tuple[str, ...]
    required_capabilities: tuple[FrozenCapabilityPin, ...]
    required_completions: tuple[FrozenCompletionPin, ...]

    def __init__(self) -> None:
        _fail("FrozenPackageExecutionPlan must be created by its canonical factory")

    @property
    def canonical_sha256(self) -> str:
        """Plain file digest of the canonical execution-plan JSON bytes."""
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def _new_frozen_package_execution_plan(
    *,
    target_package_ref_id: str,
    cluster_id: str,
    canonical_bytes: bytes,
    digest: str,
    status: PackagePlanStatus,
    root_count: int,
    package_name: str,
    version_code: str,
    version_name: str,
    target_artifact_digest: str,
    preflight_sha256: str,
    preparation: FrozenPreparationPlanBinding,
    package_local_evidence: FrozenPackageLocalEvidenceBinding,
    inherited_semantic_roots: tuple[str, ...],
    semantic_audit_completion_digests: tuple[str, ...],
    required_capabilities: tuple[FrozenCapabilityPin, ...],
    required_completions: tuple[FrozenCompletionPin, ...],
) -> FrozenPackageExecutionPlan:
    values: dict[str, object] = {
        "target_package_ref_id": target_package_ref_id,
        "cluster_id": cluster_id,
        "canonical_bytes": canonical_bytes,
        "digest": digest,
        "status": status,
        "root_count": root_count,
        "package_name": package_name,
        "version_code": version_code,
        "version_name": version_name,
        "target_artifact_digest": target_artifact_digest,
        "preflight_sha256": preflight_sha256,
        "preparation": preparation,
        "package_local_evidence": package_local_evidence,
        "inherited_semantic_roots": inherited_semantic_roots,
        "semantic_audit_completion_digests": semantic_audit_completion_digests,
        "required_capabilities": required_capabilities,
        "required_completions": required_completions,
    }
    _sha(target_package_ref_id, "snapshot.target_package_ref_id")
    _token(cluster_id, "snapshot.cluster_id")
    if type(canonical_bytes) is not bytes:
        _fail("snapshot canonical bytes must be exact immutable bytes")
    _sha(digest, "snapshot.digest")
    try:
        decoded = json.loads(canonical_bytes, object_pairs_hook=_unique_json_object)
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
    if decoded.get("cluster_id") != cluster_id:
        _fail("snapshot cluster does not match its canonical preimage")
    if decoded.get("revision") != PACKAGE_EXECUTION_PLAN_REVISION:
        _fail("snapshot revision does not match the supported plan contract")
    if decoded.get("status") != status.value:
        _fail("snapshot status does not match its canonical preimage")
    if decoded.get("authoritative_root_count") != root_count:
        _fail("snapshot root count does not match its canonical preimage")
    decoded_roots = decoded.get("root_plans")
    if not isinstance(decoded_roots, list):
        _fail("snapshot root plans are absent from its canonical preimage")
    derived_semantic_roots: set[str] = set()
    derived_audit_digests: set[str] = set()
    derived_prerequisite_capabilities: list[dict[str, object]] = []
    for root in decoded_roots:
        if not isinstance(root, dict) or root.get("route") != Route.EXACT_REUSE.value:
            continue
        if set(root) != {"reuse", "revision", "route"} or root.get(
            "revision"
        ) != ROOT_EXECUTION_PLAN_REVISION:
            _fail("snapshot exact-reuse root has an unsupported schema")
        reuse = root.get("reuse")
        if not isinstance(reuse, dict) or set(reuse) != {
            "byte_identity_proof_id",
            "direct_semantic_audit_completion",
            "equivalence_pipeline",
            "exact_reuse_prerequisite_capabilities",
            "exact_reuse_prerequisite_receipt_sha256",
            "extractor_capability",
            "extractor_record_revision",
            "inherited_semantic_root_completion",
            "inherited_semantic_root_sha256",
            "ledger_decision_completion",
            "revision",
            "source_root_id",
            "target_inventory_completion",
            "target_occurrence_identity_sha256",
            "target_root_id",
        }:
            _fail("snapshot exact-reuse root has no canonical reuse binding")
        if reuse.get("revision") != EXACT_REUSE_PINS_REVISION:
            _fail("snapshot exact-reuse pins use an unsupported revision")
        prerequisite_receipt = reuse.get("exact_reuse_prerequisite_receipt_sha256")
        _sha(cast(str, prerequisite_receipt), "snapshot exact-reuse prerequisite receipt")
        completions = (
            (
                reuse.get("inherited_semantic_root_completion"),
                EXACT_REUSE_SEMANTIC_ROOT_UNIT_PREFIX,
            ),
            (
                reuse.get("ledger_decision_completion"),
                EXACT_REUSE_LEDGER_DECISION_UNIT_PREFIX,
            ),
            (
                reuse.get("direct_semantic_audit_completion"),
                EXACT_REUSE_DIRECT_AUDIT_UNIT_PREFIX,
            ),
        )
        if any(
            not isinstance(completion, dict)
            or completion.get("parent_unit_id") != f"{prefix}:{prerequisite_receipt}"
            for completion, prefix in completions
        ):
            _fail("snapshot exact-reuse completions do not bind one prerequisite")
        prerequisite_capabilities = reuse.get("exact_reuse_prerequisite_capabilities")
        if (
            not isinstance(prerequisite_capabilities, list)
            or not prerequisite_capabilities
            or len(prerequisite_capabilities) > _MAX_ROOT_CAPABILITIES
            or any(
                not isinstance(item, dict)
                or set(item) != {"digest", "name", "revision"}
                or type(item.get("name")) is not str
                or type(item.get("revision")) is not str
                or type(item.get("digest")) is not str
                or _SHA.fullmatch(cast(str, item.get("digest"))) is None
                for item in prerequisite_capabilities
            )
            or prerequisite_capabilities
            != sorted(
                prerequisite_capabilities,
                key=lambda item: (
                    cast(str, item["name"]),
                    cast(str, item["revision"]),
                    cast(str, item["digest"]),
                ),
            )
            or len({cast(str, item["name"]) for item in prerequisite_capabilities})
            != len(prerequisite_capabilities)
        ):
            _fail("snapshot exact-reuse prerequisite capabilities are invalid")
        derived_prerequisite_capabilities.extend(prerequisite_capabilities)
        semantic_root = reuse.get("inherited_semantic_root_sha256")
        audit = reuse.get("direct_semantic_audit_completion")
        if not isinstance(semantic_root, str) or not isinstance(audit, dict):
            _fail("snapshot exact-reuse root has malformed semantic bindings")
        audit_digest = audit.get("digest")
        if not isinstance(audit_digest, str):
            _fail("snapshot exact-reuse root has malformed audit completion")
        derived_semantic_roots.add(semantic_root)
        derived_audit_digests.add(audit_digest)
    if inherited_semantic_roots != tuple(sorted(derived_semantic_roots)):
        _fail("snapshot inherited semantic roots do not derive from canonical root plans")
    if semantic_audit_completion_digests != tuple(sorted(derived_audit_digests)):
        _fail("snapshot audit completions do not derive from canonical root plans")
    local = decoded.get("package_local")
    if (
        not isinstance(local, dict)
        or set(local)
        != {
            "evidence_producer_capabilities",
            "evidence",
            "mandatory_domains",
            "package_name",
            "pipeline_capability",
            "requirements_sha256",
            "revision",
            "target_artifact_digest",
            "target_package_ref_id",
            "version_code",
            "version_name",
        }
        or (
        local.get("package_name"),
        local.get("version_code"),
        local.get("version_name"),
        local.get("target_artifact_digest"),
        local.get("requirements_sha256"),
    ) != (
        package_name,
        version_code,
        version_name,
        target_artifact_digest,
        preflight_sha256,
        )
    ):
        _fail("snapshot package identity does not match its canonical preimage")
    if type(required_capabilities) is not tuple or not required_capabilities:
        _fail("snapshot capabilities must be a non-empty tuple")
    if any(type(item) is not FrozenCapabilityPin for item in required_capabilities):
        _fail("snapshot capabilities must use exact immutable pins")
    if type(preparation) is not FrozenPreparationPlanBinding:
        _fail("snapshot preparation must use an exact immutable binding")
    if decoded.get("preparation") != preparation.to_data():
        _fail("snapshot preparation does not match its canonical preimage")
    if preparation.package_ref_id != target_package_ref_id or (
        preparation.package_name,
        preparation.version_code,
        preparation.version_name,
        preparation.artifact_digest,
        preparation.preflight_sha256,
    ) != (
        package_name,
        version_code,
        version_name,
        target_artifact_digest,
        preflight_sha256,
    ):
        _fail("snapshot preparation targets a different package identity")
    if type(package_local_evidence) is not FrozenPackageLocalEvidenceBinding:
        _fail("snapshot package-local evidence must use an exact immutable binding")
    if local.get("evidence") != package_local_evidence.to_data():
        _fail("snapshot package-local evidence differs from its canonical preimage")
    if (
        package_local_evidence.package_ref_id != target_package_ref_id
        or package_local_evidence.preparation_receipt_sha256
        != preparation.receipt_sha256
    ):
        _fail("snapshot package-local evidence targets another package or preparation")
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
    if any(item not in expected_capability_data for item in derived_prerequisite_capabilities):
        _fail("snapshot capabilities omit an exact-reuse prerequisite pin")
    if any(item not in required_capabilities for item in preparation.capabilities):
        _fail("snapshot capabilities omit an accepted preparation pin")
    evidence_producer_data = [
        {"digest": item.digest, "name": item.name, "revision": item.revision}
        for item in preparation.evidence_producer_capabilities
    ]
    if local.get("evidence_producer_capabilities") != evidence_producer_data:
        _fail("snapshot package-local evidence producers differ from preparation")
    if any(
        item not in required_capabilities
        for item in preparation.evidence_producer_capabilities
    ):
        _fail("snapshot capabilities omit a package-local evidence producer")
    pipeline_data = local.get("pipeline_capability")
    if (
        not isinstance(pipeline_data, dict)
        or set(pipeline_data) != {"digest", "name", "revision"}
        or pipeline_data.get("name") != PACKAGE_PIPELINE_CAPABILITY
        or pipeline_data.get("revision") != PACKAGE_EXECUTION_PLAN_REVISION
        or pipeline_data not in expected_capability_data
    ):
        _fail("snapshot capabilities omit the package analysis pipeline")
    if preparation.completion not in required_completions:
        _fail("snapshot completions omit the accepted preparation receipt")
    if type(package_name) is not str or _PACKAGE.fullmatch(package_name) is None:
        _fail("snapshot package name is invalid")
    _text(version_code, "snapshot.version_code", 256)
    _text(version_name, "snapshot.version_name", 256)
    _sha(target_artifact_digest, "snapshot.target_artifact_digest")
    _sha(preflight_sha256, "snapshot.preflight_sha256")
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
    if len({item.parent_unit_id for item in required_completions}) != len(required_completions):
        _fail("snapshot completions contain duplicate unit IDs")
    if (
        len(required_capabilities) > _MAX_GLOBAL_REQUIREMENTS
        or len(required_completions) > _MAX_GLOBAL_REQUIREMENTS
    ):
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
        cluster_id=value.cluster_id,
        canonical_bytes=value.canonical_bytes,
        digest=value.digest,
        status=value.status,
        root_count=value.root_count,
        package_name=value.package_name,
        version_code=value.version_code,
        version_name=value.version_name,
        target_artifact_digest=value.target_artifact_digest,
        preflight_sha256=value.preflight_sha256,
        preparation=value.preparation,
        package_local_evidence=value.package_local_evidence,
        inherited_semantic_roots=value.inherited_semantic_roots,
        semantic_audit_completion_digests=value.semantic_audit_completion_digests,
        required_capabilities=value.required_capabilities,
        required_completions=value.required_completions,
    )


def validate_frozen_package_execution_plan(
    value: FrozenPackageExecutionPlan,
) -> FrozenPackageExecutionPlan:
    """Reconstruct and verify an immutable package-plan trust boundary."""

    return _validate_frozen_package_execution_plan(value)


def validate_preparation_receipt_for_plan(
    plan: FrozenPackageExecutionPlan,
    receipt: PreparationReceipt,
    authority: ActivatedPreparationAuthority,
) -> FrozenPreparationPlanBinding:
    """Verify a receipt is the exact preparation completion frozen into a plan."""

    frozen = _validate_frozen_package_execution_plan(plan)
    evidence_producers = preparation_evidence_producer_capabilities(receipt, authority)
    receipt_sha256, capabilities = _validated_preparation_receipt(receipt, authority)
    binding = frozen.preparation
    if (
        receipt.package_name,
        receipt.version_code,
        receipt.version_name,
        receipt.artifact_digest,
        receipt.preflight_manifest_sha256,
        receipt_sha256,
    ) != (
        binding.package_name,
        binding.version_code,
        binding.version_name,
        binding.artifact_digest,
        binding.preflight_sha256,
        binding.receipt_sha256,
    ):
        _fail("preparation receipt is not the completion frozen into this plan")
    if tuple(_frozen_capability(item) for item in capabilities) != binding.capabilities:
        _fail("preparation authority is not the capability set frozen into this plan")
    if (
        tuple(_frozen_capability(item) for item in evidence_producers)
        != binding.evidence_producer_capabilities
    ):
        _fail("preparation evidence producers are not frozen into this plan")
    if binding.completion != FrozenCompletionPin(
        preparation_queue_unit_id(binding.package_ref_id),
        PREPARATION_RECEIPT_REVISION,
        receipt_sha256,
    ):
        _fail("preparation completion is not frozen into this plan")
    return binding


def freeze_package_execution_plan(value: PackageExecutionPlan) -> FrozenPackageExecutionPlan:
    if type(value) is not PackageExecutionPlan:
        _fail("plan snapshot requires an exact PackageExecutionPlan")
    frozen = PackageExecutionPlan(
        target_package_ref_id=value.target_package_ref_id,
        target_package_ref=value.target_package_ref,
        cluster_id=value.cluster_id,
        package_local=value.package_local,
        preparation=value.preparation,
        accepted_target_inventory=value.accepted_target_inventory,
        root_plans=value.root_plans,
        revision=value.revision,
    )
    canonical = _canonical_bytes(frozen.to_data())
    digest = hashlib.sha256(b"phase4-v2:package-execution-plan\0" + canonical).hexdigest()
    return _new_frozen_package_execution_plan(
        target_package_ref_id=frozen.target_package_ref_id,
        cluster_id=frozen.cluster_id,
        canonical_bytes=canonical,
        digest=digest,
        status=frozen.status,
        root_count=len(frozen.root_plans),
        package_name=frozen.package_local.package_name,
        version_code=frozen.package_local.version_code,
        version_name=frozen.package_local.version_name,
        target_artifact_digest=frozen.package_local.target_artifact_digest,
        preflight_sha256=frozen.package_local.requirements_sha256,
        preparation=_frozen_preparation(frozen.preparation),
        package_local_evidence=_frozen_local_evidence(frozen.package_local.evidence),
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
    cluster_id: str,
    package_local: PackageLocalPlan,
    preparation: PreparationPlanBinding,
    accepted_target_inventory: AcceptedTargetRootInventory,
    root_plans: Iterable[RootExecutionPlan],
) -> PackageExecutionPlan:
    roots: list[RootExecutionPlan] = []
    for index, item in enumerate(root_plans):
        if index >= _MAX_ROOTS:
            _fail(f"package execution plan exceeds {_MAX_ROOTS} roots")
        roots.append(_root(item))
    return PackageExecutionPlan(
        target_package_ref_id=target_package_ref_id,
        target_package_ref=target_package_ref,
        cluster_id=cluster_id,
        package_local=package_local,
        preparation=preparation,
        accepted_target_inventory=accepted_target_inventory,
        root_plans=tuple(sorted(roots, key=_root_key)),
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
    target_final_ir_schema_revision: str
    target_final_ir_schema_sha256: str
    target_final_ir_json_sha256: str
    package_local_raw_receipt_sha256: str
    package_local_raw_authority_sha256: str
    validated_root_evidence: tuple[ValidatedRootEvidenceAttestation, ...]
    revision: str

    def __init__(self) -> None:
        _fail("ValidatedPackageOutput must be created by the trusted receipt factory")

    def to_data(self) -> dict[str, object]:
        return {
            "execution_plan_id": self.execution_plan_id,
            "revision": self.revision,
            "target_package_ref_id": self.target_package_ref_id,
            "target_report_revision": self.target_report_revision,
            "target_report_schema_revision": self.target_report_schema_revision,
            "target_report_schema_sha256": self.target_report_schema_sha256,
            "target_report_sha256": self.target_report_sha256,
            "target_final_ir_schema_revision": self.target_final_ir_schema_revision,
            "target_final_ir_schema_sha256": self.target_final_ir_schema_sha256,
            "target_final_ir_json_sha256": self.target_final_ir_json_sha256,
            "package_local_raw_authority_sha256": self.package_local_raw_authority_sha256,
            "package_local_raw_receipt_sha256": self.package_local_raw_receipt_sha256,
            "validation_receipt_sha256": self.validation_receipt_sha256,
            "validated_root_evidence": [item.to_dict() for item in self.validated_root_evidence],
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
def _receipt_sha(value: object, field: str, *, optional: Literal[False] = False) -> str: ...


@overload
def _receipt_sha(value: object, field: str, *, optional: Literal[True]) -> str | None: ...


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
    if type(receipt.validated_root_evidence) is not tuple:
        _fail("validated root evidence must be an exact tuple")
    root_evidence: list[ValidatedRootEvidenceAttestation] = []
    for root in receipt.validated_root_evidence:
        if type(root) is not ValidatedRootEvidenceAttestation:
            _fail("validated root evidence contains a non-exact attestation")
        evidence_members: list[ValidatedRootEvidenceMember] = []
        for evidence in root.evidence_members:
            if type(evidence) is not ValidatedRootEvidenceMember:
                _fail("validated root evidence contains a non-exact member")
            anchor_ids = tuple(
                _receipt_string(item, "root evidence anchor ID", maximum=256)
                for item in evidence.evidence_anchor_ids
            )
            if not anchor_ids or anchor_ids != tuple(sorted(set(anchor_ids))):
                _fail("validated root evidence anchor IDs are not canonical")
            evidence_members.append(
                ValidatedRootEvidenceMember(
                    _receipt_string(evidence.member, "root evidence member"),
                    _receipt_sha(evidence.member_sha256, "root evidence member digest"),
                    anchor_ids,
                )
            )
        copied_root = ValidatedRootEvidenceAttestation(
            _receipt_sha(root.target_root_id, "root evidence target root"),
            _receipt_sha(
                root.target_occurrence_identity_sha256, "root evidence occurrence identity"
            ),
            _receipt_sha(root.semantic_root_sha256, "root evidence semantic root"),
            tuple(evidence_members),
        )
        root_evidence.append(copied_root)
    if tuple(root_evidence) != tuple(sorted(set(root_evidence))):
        _fail("validated root evidence is not canonical")
    member_index = {item.member: item for item in members}
    anchor_index = {item.id: item for item in anchors}
    for root in root_evidence:
        if not root.evidence_members:
            _fail("validated root evidence has no evidence members")
        for evidence in root.evidence_members:
            member = member_index.get(evidence.member)
            if member is None or member.sha256 != evidence.member_sha256:
                _fail("validated root evidence member is not retained by the receipt")
            for anchor_id in evidence.evidence_anchor_ids:
                anchor = anchor_index.get(anchor_id)
                if (
                    anchor is None
                    or anchor.member != evidence.member
                    or anchor.member_sha256 != evidence.member_sha256
                    or anchor.owner != member.owner
                ):
                    _fail("validated root evidence anchor is not retained for its member")
    dependencies = _exact_pair_tuple(receipt.dependency_digests, "validator dependency digests")
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
        validated_root_evidence=tuple(root_evidence),
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
    package_local_evidence: AuthenticatedPackageLocalEvidence,
    package_local_evidence_inputs: PackageLocalEvidenceReauthenticationInput,
    package_local_validator_envelope: AuthenticatedValidatorEnvelope,
) -> ValidatedPackageOutput:
    if type(execution_plan) is not PackageExecutionPlan:
        _fail("validated output requires an exact PackageExecutionPlan")
    expected_local = bind_package_local_evidence(
        package_ref=execution_plan.target_package_ref,
        evidence=package_local_evidence,
        evidence_inputs=package_local_evidence_inputs,
        enriched_validator_envelope=package_local_validator_envelope,
    )
    if expected_local != execution_plan.package_local.evidence:
        _fail("package output uses package-local evidence outside its execution plan")
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
    if dependencies.get("execution_plan") != plan.canonical_sha256:
        _fail("validator receipt does not bind the frozen execution plan")
    if dependencies.get("report_schema") != PACKAGE_REPORT_SCHEMA_SHA256:
        _fail("validator receipt does not bind the current package-report schema")
    if dependencies.get("schema") != FINAL_IR_SCHEMA_SHA256:
        _fail("validator receipt does not bind the current final-IR schema")
    final_ir_sha256 = dependencies.get("ir")
    if final_ir_sha256 is None:
        _fail("validator receipt does not bind canonical final-IR JSON")
    _sha(final_ir_sha256, "validator final-IR dependency")
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
    local_binding = plan.package_local_evidence
    local_anchor_ids = set(local_binding.evidence_anchor_ids)
    local_anchors = tuple(
        item
        for item in frozen_receipt.validated_evidence_anchors
        if item.id in local_anchor_ids
    )
    if tuple(sorted(item.id for item in local_anchors)) != local_binding.evidence_anchor_ids:
        _fail("validator receipt does not contain the exact target-local anchor set")
    local_member_paths = {item.member for item in local_anchors}
    local_members = tuple(
        item
        for item in frozen_receipt.validated_evidence_members
        if item.member in local_member_paths
    )
    local_evidence_sha256 = hashlib.sha256(
        _canonical_bytes(
            {
                "anchors": [item.to_dict() for item in local_anchors],
                "members": [item.to_dict() for item in local_members],
            }
        )
    ).hexdigest()
    if (
        not local_anchors
        or any(item.owner != plan.target_artifact_digest for item in local_anchors)
        or any(item.owner != plan.target_artifact_digest for item in local_members)
        or local_evidence_sha256 != local_binding.validator_evidence_sha256
    ):
        _fail("validator receipt target-local evidence differs from the frozen raw binding")
    forbidden = {*plan.inherited_semantic_roots, *plan.semantic_audit_completion_digests}
    if frozen_receipt.bundle_sha256 in forbidden:
        _fail("source semantic-root evidence cannot serve as the target package report")
    canonical_plan = json.loads(plan.canonical_bytes)
    expected_full_roots = {
        (item["target_root_id"], item["target_occurrence_identity_sha256"])
        for item in canonical_plan["root_plans"]
        if item["route"] == Route.FULL_ANALYSIS.value
    }
    retained_full_roots = {
        (item.target_root_id, item.target_occurrence_identity_sha256)
        for item in frozen_receipt.validated_root_evidence
    }
    if retained_full_roots != expected_full_roots or len(
        frozen_receipt.validated_root_evidence
    ) != len(expected_full_roots):
        _fail("validator receipt does not retain the exact FULL root evidence set")
    output = object.__new__(ValidatedPackageOutput)
    object.__setattr__(output, "target_package_ref_id", plan.target_package_ref_id)
    object.__setattr__(output, "execution_plan_id", plan.digest)
    object.__setattr__(output, "validation_receipt_sha256", identity_sha)
    object.__setattr__(output, "target_report_revision", PACKAGE_REPORT_REVISION)
    object.__setattr__(output, "target_report_schema_revision", PACKAGE_REPORT_SCHEMA_REVISION)
    object.__setattr__(output, "target_report_schema_sha256", PACKAGE_REPORT_SCHEMA_SHA256)
    object.__setattr__(output, "target_report_sha256", frozen_receipt.bundle_sha256)
    object.__setattr__(output, "target_final_ir_schema_revision", FINAL_SCHEMA_REVISION)
    object.__setattr__(output, "target_final_ir_schema_sha256", FINAL_IR_SCHEMA_SHA256)
    object.__setattr__(output, "target_final_ir_json_sha256", final_ir_sha256)
    object.__setattr__(
        output,
        "package_local_raw_receipt_sha256",
        plan.package_local_evidence.raw_receipt_sha256,
    )
    object.__setattr__(
        output,
        "package_local_raw_authority_sha256",
        plan.package_local_evidence.raw_authority_sha256,
    )
    object.__setattr__(output, "validated_root_evidence", frozen_receipt.validated_root_evidence)
    object.__setattr__(output, "revision", VALIDATED_PACKAGE_OUTPUT_REVISION)
    if (
        bind_package_local_evidence(
            package_ref=execution_plan.target_package_ref,
            evidence=package_local_evidence,
            evidence_inputs=package_local_evidence_inputs,
            enriched_validator_envelope=package_local_validator_envelope,
        )
        != expected_local
    ):
        _fail("package-local evidence changed during output validation")
    return output
