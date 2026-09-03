"""Protocol-neutral fixture producers for the production-path acceptance harness."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import tools.phase4_v2.equivalence.core as equivalence_core
import tools.phase4_v2.equivalence.execution as execution_module
import tools.phase4_v2.equivalence.inventory as inventory_module
import tools.phase4_v2.equivalence.prerequisite as prerequisite_module
import tools.phase4_v2.ir.model as ir_core
import tools.phase4_v2.ir.v1 as final_ir_model
import tools.phase4_v2.preflight.core as preflight_core
import tools.phase4_v2.preflight.registry as registry_module
import tools.phase4_v2.raw_source as raw_source_module
from tools.phase4_v2.equivalence.core import (
    ActivatedValidatorAuthority,
    ApplicationRoot,
    AuthenticatedValidatorEnvelope,
    authenticated_validator_envelope_payload,
    load_activated_validator_authority,
    load_authenticated_validator_envelope,
    validator_authority_payload,
    validator_authority_pin_payload,
    validator_envelope_signing_bytes,
)
from tools.phase4_v2.equivalence.execution import (
    ActivatedExecutionAuthority,
    execution_authority_payload,
    execution_authority_pin_payload,
    load_activated_execution_authority,
)
from tools.phase4_v2.equivalence.inventory import (
    ActivatedInventoryAuthority,
    AuthenticatedTargetInventoryEnvelope,
    inventory_authority_payload,
    inventory_authority_pin_payload,
    load_activated_inventory_authority,
)
from tools.phase4_v2.equivalence.plan import (
    FINAL_IR_SCHEMA_CANONICAL_BYTES,
    FINAL_IR_SCHEMA_SHA256,
    LOCAL_ONLY_DOMAINS,
    PACKAGE_EXECUTION_PLAN_REVISION,
    PACKAGE_PIPELINE_CAPABILITY,
    PACKAGE_REPORT_REVISION,
    PACKAGE_REPORT_SCHEMA_CANONICAL_BYTES,
    PACKAGE_REPORT_SCHEMA_SHA256,
    AcceptedTargetRootInventory,
    CapabilityPin,
    FrozenPackageRef,
    FullAnalysisRootPlan,
    PackageExecutionPlan,
    PackageLocalPlan,
    PreparationPlanBinding,
    RootExecutionPlan,
    TargetRootInventory,
    TargetRootOccurrence,
    build_package_execution_plan,
    freeze_package_execution_plan,
)
from tools.phase4_v2.equivalence.prerequisite import (
    ActivatedExactReuseAuthority,
    exact_reuse_authority_payload,
    exact_reuse_authority_pin_payload,
    load_activated_exact_reuse_authority,
)
from tools.phase4_v2.equivalence.provenance import (
    AuthenticatedSourceReportRegistry,
    build_authenticated_raw_source_report_registry,
    source_report_root_completion,
)
from tools.phase4_v2.ir import (
    FINAL_DOMAIN_COLLECTIONS,
    FINAL_SCHEMA_REVISION,
    SCHEMA_REVISION,
    SUPPORTED_CONTRACT_REVISION,
    SUPPORTED_VALIDATOR_REVISION,
    bind_validator_receipt,
    build_artifact_identity,
    build_evidence_anchor,
    build_evidence_binding,
    build_evidence_file,
    build_source_package,
    build_source_set,
    loads_final_ir,
    render_final_ir_markdown,
    schema_document,
)
from tools.phase4_v2.preflight import (
    REQUIRED_PREPARATION_ROUTES,
    ActivatedPreparationAuthority,
    ApprovedRoute,
    ApprovedToolRegistry,
    ExecutionProfile,
    OutputSufficiencyContract,
    PreflightResult,
    PreparationExecutionSigner,
    PreparationReceipt,
    ToolQualification,
    ToolSpec,
    build_execution_profile,
    execute_registered_preparation,
    load_activated_preparation_authority,
    preflight_delivery,
    preparation_authority_payload,
    qualify_tool,
)
from tools.phase4_v2.raw_source import (
    ActivatedRawSourceAuthority,
    RawSourceAnchor,
    RawSourceMember,
    RawSourceReauthenticationInput,
    build_authenticated_raw_source_registry,
    canonical_scalar_sha256,
    load_protected_raw_source_authority,
    raw_source_authority_payload,
    raw_source_collection_payload,
    raw_source_envelope_payload,
    raw_source_signing_bytes,
)
from tools.phase4_v2.validator import (
    BOUND_VALIDATION_PROFILE,
    CONTRACT_REVISION,
    LINEAGE_SCHEMA_REVISION,
    PACKAGE_CONTRACT_REVISION,
    DependencyPins,
    EvidenceLineageTrust,
    PackageDependencyPins,
    TrustedProducer,
    derive_raw_source_validator_receipt,
    validate_report_bundle,
)


@dataclass(frozen=True, slots=True)
class SyntheticTrust:
    preparation_signer: PreparationExecutionSigner
    preparation_registry: ApprovedToolRegistry
    preparation_profile: ExecutionProfile
    preparation_authority: ActivatedPreparationAuthority
    validator_key: Ed25519PrivateKey
    validator_authority: ActivatedValidatorAuthority
    inventory_key: Ed25519PrivateKey
    inventory_authority: ActivatedInventoryAuthority
    execution_key: Ed25519PrivateKey
    execution_authority: ActivatedExecutionAuthority
    raw_source_key: Ed25519PrivateKey
    raw_source_authority: ActivatedRawSourceAuthority
    tool_sha256: str


@dataclass(frozen=True, slots=True)
class SyntheticExactReuseTrust:
    key: Ed25519PrivateKey
    authority: ActivatedExactReuseAuthority


@dataclass(frozen=True, slots=True)
class SyntheticPackageInputs:
    package_ref: FrozenPackageRef
    package_local: PackageLocalPlan
    preparation_receipt: PreparationReceipt
    preparation_authority: ActivatedPreparationAuthority
    source_envelope: AuthenticatedValidatorEnvelope
    target_inventory: AcceptedTargetRootInventory
    execution_plan: PackageExecutionPlan
    report_root: Path
    dependencies: PackageDependencyPins
    lineage: EvidenceLineageTrust


@contextmanager
def protected_fixture_trust(
    root: Path, *, emit_candidates: bool = True
) -> Iterator[SyntheticTrust]:
    """Create deterministic fixture credentials admitted by protected-pin readers."""

    root.mkdir(parents=True)
    tool = _build_static_tool(emit_candidates)
    profile = build_execution_profile()
    registry = _registry(tool, profile)
    # This classmethod is the explicit test-only bootstrap counterpart of the
    # production root-owned credential loader. The resulting signer still signs
    # every receipt, and consumers authenticate it against the protected pin.
    preparation_signer = PreparationExecutionSigner._from_private_bytes(b"p" * 32)
    authority_payload = preparation_authority_payload(
        registry, profile, preparation_signer.public_key
    )
    preparation_pin = hashlib.sha256(authority_payload).hexdigest()
    preparation_patch = patch.object(
        registry_module, "_read_protected_activation_digest", return_value=preparation_pin
    )
    validator_key = Ed25519PrivateKey.from_private_bytes(b"v" * 32)
    validator_payload = validator_authority_payload(
        authority_id="synthetic-validator",
        public_key=_public_key_hex(validator_key),
        validator_revision=SUPPORTED_VALIDATOR_REVISION,
        contract_revision=SUPPORTED_CONTRACT_REVISION,
    )
    validator_pin = json.loads(validator_authority_pin_payload(validator_payload))[
        "activation_sha256"
    ]
    validator_patch = patch.object(
        equivalence_core, "_read_protected_validator_pin", return_value=validator_pin
    )
    inventory_key = Ed25519PrivateKey.from_private_bytes(b"i" * 32)
    inventory_payload = inventory_authority_payload(
        authority_id="synthetic-inventory",
        public_key=_public_key_hex(inventory_key),
        generation=1,
    )
    inventory_pin = json.loads(inventory_authority_pin_payload(inventory_payload))[
        "activation_sha256"
    ]
    inventory_patch = patch.object(
        inventory_module, "_read_protected_inventory_pin", return_value=inventory_pin
    )
    execution_key = Ed25519PrivateKey.from_private_bytes(b"e" * 32)
    execution_payload = execution_authority_payload(
        authority_id="synthetic-execution",
        public_key=_public_key_hex(execution_key),
        generation=1,
    )
    execution_pin = json.loads(execution_authority_pin_payload(execution_payload))[
        "activation_sha256"
    ]
    execution_patch = patch.object(
        execution_module, "_read_protected_execution_pin", return_value=execution_pin
    )
    raw_source_key = Ed25519PrivateKey.from_private_bytes(b"r" * 32)
    raw_source_payload = raw_source_authority_payload(
        authority_id="raw-source-test",
        generation=1,
        public_key=_public_key_hex(raw_source_key),
    )
    raw_source_patch = patch.object(
        raw_source_module,
        "_read_protected_raw_source_authority",
        return_value=raw_source_payload,
    )
    with (
        preparation_patch,
        validator_patch,
        inventory_patch,
        execution_patch,
        raw_source_patch,
    ):
        yield SyntheticTrust(
            preparation_signer,
            registry,
            profile,
            load_activated_preparation_authority(authority_payload),
            validator_key,
            load_activated_validator_authority(validator_payload),
            inventory_key,
            load_activated_inventory_authority(inventory_payload),
            execution_key,
            load_activated_execution_authority(execution_payload),
            raw_source_key,
            load_protected_raw_source_authority(),
            hashlib.sha256(tool.read_bytes()).hexdigest(),
        )


@contextmanager
def protected_exact_reuse_trust() -> Iterator[SyntheticExactReuseTrust]:
    """Activate the deterministic test-only exact-reuse signing authority."""

    key = Ed25519PrivateKey.from_private_bytes(b"q" * 32)
    payload = exact_reuse_authority_payload(
        authority_id="exact-reuse-test",
        public_key=_public_key_hex(key),
        generation=1,
    )
    activation = json.loads(exact_reuse_authority_pin_payload(payload))["activation_sha256"]
    with patch.object(
        prerequisite_module,
        "_read_protected_exact_reuse_authority_pin",
        return_value=activation,
    ):
        yield SyntheticExactReuseTrust(key, load_activated_exact_reuse_authority(payload))


def _public_key_hex(key: Ed25519PrivateKey) -> str:
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        .hex()
    )


def _write_zip_member(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    member.compress_type = zipfile.ZIP_STORED
    member.external_attr = 0o100644 << 16
    archive.writestr(member, payload)


def build_synthetic_package_inputs(
    root: Path,
    *,
    cluster_id: str,
    package_index: int,
    trust: SyntheticTrust,
    root_count: int = 1,
) -> IncompleteSyntheticPackage:
    """Build one real signed preparation and two genuinely validated reports."""

    cluster_token = hashlib.sha256(cluster_id.encode()).hexdigest()[:12]
    package_name = f"org.example.synthetic.c{cluster_token}.p{package_index}"
    package_root = root / package_name
    package_root.mkdir(parents=True)
    artifact = package_root / "base.apk"
    with zipfile.ZipFile(artifact, "w") as archive:
        _write_zip_member(archive, "AndroidManifest.xml", b"synthetic-manifest")
        _write_zip_member(archive, "res/raw/synthetic.txt", b"synthetic-resource")
    (package_root / "sealed").mkdir()

    def identity(arguments: tuple[str, ...], **_kwargs: object) -> tuple[str, None]:
        if arguments[0] == "aapt2":
            return (
                f"package: name='{package_name}' versionCode='1' versionName='1.0'\n",
                None,
            )
        return f"Signer #1 certificate SHA-256 digest: {'9' * 64}\n", None

    with (
        patch.object(preflight_core, "_run_identity_tool", side_effect=identity),
        preflight_delivery([artifact], sealing_directory=package_root / "sealed") as preflight,
    ):
        receipt = execute_registered_preparation(
            preflight,
            registry=trust.preparation_registry,
            authority=trust.preparation_authority,
            execution_profile=trust.preparation_profile,
            execution_signer=trust.preparation_signer,
            cache_directory=package_root / "preparation-cache",
            output_directory=package_root / "preparation-result",
        )
        preflight_bytes = _canonical(preflight.manifest())
        occurrence = _digest(f"occurrence:{cluster_id}:{package_index}")
        extractor = inventory_module.ExtractorCapability(
            name="phase4-v2-synthetic-inventory-extractor",
            implementation_sha256=trust.tool_sha256,
            configuration_sha256=_digest("synthetic-inventory-configuration"),
            capability_revision="synthetic-inventory-v1",
        )
        source_report, source_pins, source_lineage = _source_report(
            package_root / "source-report",
            preflight=preflight,
            preflight_bytes=preflight_bytes,
            tool_sha256=trust.tool_sha256,
            target_root=_digest(f"provisional-root:{cluster_id}:{package_index}"),
            occurrence=occurrence,
        )
        source_receipt = validate_report_bundle(
            source_report,
            expected_dependencies=source_pins,
            expected_evidence_lineage=source_lineage,
        )
        if not source_receipt.accepted:
            raise RuntimeError(f"synthetic source report failed: {source_receipt.diagnostics}")
        if preflight.package_identity is None:
            raise RuntimeError("synthetic preflight lost its package identity")
        source_envelope = _sign_validator_receipt(source_receipt.to_json().encode(), trust)
        package_ref = equivalence_core.frozen_package_ref_from_validator_envelope(source_envelope)
        if type(root_count) is not int or not 1 <= root_count <= 2:
            raise ValueError("synthetic root count must be one or two")
        application_roots = tuple(
            ApplicationRoot(
                package_ref_id=package_ref.content_id,
                root_kind="android",
                extractor_capability_id=extractor.content_id,
                occurrence_identity_sha256=(
                    occurrence if index == 0 else _digest(f"occurrence:{cluster_id}:{package_index}:1")
                ),
                content_root_sha256=(
                    _digest("synthetic-content-root")
                    if index == 0
                    else _digest(f"synthetic-content-root:{package_name}:{index}")
                ),
                inventory_sha256=(
                    _digest("synthetic-root-inventory")
                    if index == 0
                    else _digest(f"synthetic-root-inventory:{package_name}:{index}")
                ),
                dependency_root_sha256=(
                    _digest("synthetic-dependency-root")
                    if index == 0
                    else _digest(f"synthetic-dependency-root:{package_name}:{index}")
                ),
                inventory_complete=True,
                dependency_closure_complete=True,
            )
            for index in range(root_count)
        )
        package_local = PackageLocalPlan(
            package_ref.content_id,
            package_name,
            "1",
            "1.0",
            preflight.artifact_digest,
            hashlib.sha256(preflight_bytes).hexdigest(),
            CapabilityPin(
                PACKAGE_PIPELINE_CAPABILITY,
                PACKAGE_EXECUTION_PLAN_REVISION,
                _digest("synthetic-package-pipeline"),
            ),
        )
        inventory = TargetRootInventory(
            package_ref.content_id,
            tuple(
                TargetRootOccurrence(root.content_id, root.occurrence_identity_sha256)
                for root in application_roots
            ),
        )
        # The accepted preparation binding is supplied later by the queue's
        # trusted finish adapter. The authenticated inventory adapter similarly
        # turns this raw inventory into an AcceptedTargetRootInventory.
        return IncompleteSyntheticPackage(
            package_ref,
            package_local,
            receipt,
            trust.preparation_authority,
            source_envelope,
            inventory,
            application_roots,
            extractor,
            occurrence,
            preflight_bytes,
            tuple((item.name, item.sha256) for item in preflight.artifact_members),
            package_root,
            trust.tool_sha256,
        )


@dataclass(frozen=True, slots=True)
class IncompleteSyntheticPackage:
    package_ref: FrozenPackageRef
    package_local: PackageLocalPlan
    preparation_receipt: PreparationReceipt
    preparation_authority: ActivatedPreparationAuthority
    source_envelope: AuthenticatedValidatorEnvelope
    target_inventory: TargetRootInventory
    application_roots: tuple[ApplicationRoot, ...]
    extractor: inventory_module.ExtractorCapability
    occurrence: str
    preflight_bytes: bytes
    artifact_members: tuple[tuple[str, str], ...]
    package_root: Path
    tool_sha256: str

    @property
    def target_root(self) -> str:
        return self.application_root.content_id

    @property
    def application_root(self) -> ApplicationRoot:
        return self.application_roots[0]


def finish_synthetic_package_inputs(
    partial: IncompleteSyntheticPackage,
    *,
    preparation: PreparationPlanBinding,
    target_inventory: AcceptedTargetRootInventory,
    source_registry: AuthenticatedSourceReportRegistry,
    root_plans: tuple[RootExecutionPlan, ...] | None = None,
) -> SyntheticPackageInputs:
    """Build a production package plan and matching immutable report bundle."""

    if root_plans is None:
        source = next(
            item
            for item in source_registry.entries
            if item.package_ref.content_id == partial.package_ref.content_id
        )
        source_roots = source.report.validated_root_evidence
        if len(source_roots) != 1:
            raise RuntimeError("synthetic FULL source report must authenticate exactly one root")
        root_plans = (
            FullAnalysisRootPlan(
                partial.target_root,
                partial.occurrence,
                "synthetic authoritative analysis",
                (
                    CapabilityPin(
                        "apktool",
                        "pipeline-v1",
                        partial.tool_sha256,
                    ),
                ),
                (source_report_root_completion(source, source_roots[0]),),
            ),
        )
    execution_plan = build_package_execution_plan(
        target_package_ref_id=partial.package_ref.content_id,
        target_package_ref=partial.package_ref,
        cluster_id=_cluster_from_package_root(partial.package_root),
        package_local=partial.package_local,
        preparation=preparation,
        accepted_target_inventory=target_inventory,
        root_plans=root_plans,
    )
    report, dependencies, lineage = _package_report(partial, execution_plan, source_registry)
    return SyntheticPackageInputs(
        partial.package_ref,
        partial.package_local,
        partial.preparation_receipt,
        partial.preparation_authority,
        partial.source_envelope,
        target_inventory,
        execution_plan,
        report,
        dependencies,
        lineage,
    )


def _cluster_from_package_root(root: Path) -> str:
    cluster = root.parent.name
    if not cluster:
        raise RuntimeError("synthetic package root lost its cluster identity")
    return cluster


def _sign_validator_receipt(
    payload: bytes, trust: SyntheticTrust
) -> AuthenticatedValidatorEnvelope:
    signature = trust.validator_key.sign(
        validator_envelope_signing_bytes(payload, trust.validator_authority)
    ).hex()
    envelope = authenticated_validator_envelope_payload(
        payload, trust.validator_authority, signature=signature
    )
    return load_authenticated_validator_envelope(envelope, authority=trust.validator_authority)


def build_raw_backed_source_registry(
    partial: IncompleteSyntheticPackage,
    target_inventory: AuthenticatedTargetInventoryEnvelope,
    trust: SyntheticTrust,
    root_indexes: tuple[int, ...] = (0,),
) -> AuthenticatedSourceReportRegistry:
    """Bind one synthetic package's signed source report to exact raw scalars."""

    invocation_index, output = next(
        (index, output)
        for index, invocation in enumerate(partial.preparation_receipt.invocations)
        for output in invocation.outputs
        if output.bytes >= 48
    )
    member = RawSourceMember(
        "semantic-source",
        invocation_index,
        output.path,
        output.sha256,
        output.bytes,
    )
    semantic = ir_core._semantic_data(
        final_ir_model._parse_final_ir_structure(_synthetic_terminal_semantics())
    )
    pointers = tuple(
        sorted(
            pointer
            for pointer in ir_core._semantic_leaf_pointers(semantic)
            if not pointer.startswith("/domain_closure/")
            and not pointer.endswith("/@key")
        )
    )
    offset = 0
    anchors: list[RawSourceAnchor] = []
    for index, pointer in enumerate(pointers):
        value = ir_core._resolve_semantic_pointer(semantic, pointer)
        if type(value) is str:
            encoded = value.encode()
            representation = "utf8"
        elif type(value) in {int, bool}:
            encoded = json.dumps(value, separators=(",", ":")).encode()
            representation = "json-scalar"
        else:
            raise RuntimeError(f"synthetic semantic leaf is not a raw scalar: {pointer}")
        anchors.append(
            RawSourceAnchor(
                f"semantic-{partial.package_ref.content_id[:12]}-{index:02d}",
                member.id,
                offset,
                offset + len(encoded),
                encoded,
                representation,
                value,
                canonical_scalar_sha256(value),
                pointer,
            )
        )
        offset += len(encoded) + 1
    entries = []
    inputs_list: list[RawSourceReauthenticationInput] = []
    for root_index in root_indexes:
        root = partial.application_roots[root_index]
        rooted_anchors = tuple(
            RawSourceAnchor(
                anchor.id.replace(
                    partial.package_ref.content_id[:12],
                    f"{partial.package_ref.content_id[:8]}{root_index:04d}",
                ),
                anchor.member_id,
                anchor.start_byte,
                anchor.end_byte,
                anchor.raw_bytes,
                anchor.representation,
                anchor.decoded_value,
                anchor.value_sha256,
                anchor.source_ir_pointer,
            )
            for anchor in anchors
        )
        payload = raw_source_collection_payload(
            package_ref=partial.package_ref,
            root=root,
            preparation_receipt=partial.preparation_receipt,
            preparation_authority=partial.preparation_authority,
            target_inventory=target_inventory,
            members=(member,),
            anchors=rooted_anchors,
        )
        envelope = raw_source_envelope_payload(
            payload,
            trust.raw_source_key.sign(raw_source_signing_bytes(payload)).hex(),
        )
        entries.append(
            (
                envelope,
                partial.package_ref,
                root,
                partial.preparation_receipt,
                partial.preparation_authority,
                target_inventory,
            )
        )
        inputs_list.append(
            (
                partial.package_ref,
                root,
                partial.preparation_receipt,
                partial.preparation_authority,
                target_inventory,
            )
        )
    raw_registry = build_authenticated_raw_source_registry(tuple(entries))
    inputs: tuple[RawSourceReauthenticationInput, ...] = tuple(inputs_list)
    enriched_receipt = derive_raw_source_validator_receipt(
        partial.source_envelope,
        raw_source_registry=raw_registry,
        raw_source_inputs=inputs,
    )
    enriched = _sign_validator_receipt(enriched_receipt, trust)
    return build_authenticated_raw_source_report_registry(
        ((partial.package_ref, enriched),),
        raw_source_registry=raw_registry,
        raw_source_inputs=inputs,
    )


def merge_raw_backed_source_registries(
    *registries: AuthenticatedSourceReportRegistry,
) -> AuthenticatedSourceReportRegistry:
    """Merge independently authenticated synthetic source registries exactly."""

    raw_entries = []
    raw_inputs: list[RawSourceReauthenticationInput] = []
    report_entries = []
    for registry in registries:
        if registry.raw_source_registry is None:
            raise ValueError("synthetic source registry is not raw-backed")
        inputs = {
            (package.content_id, root.content_id): item
            for item in registry.raw_source_inputs
            for package, root, *_rest in (item,)
        }
        for collection in registry.raw_source_registry.entries:
            trusted = inputs[(collection.package_ref_id, collection.target_root_id)]
            raw_entries.append((collection.canonical_bytes, *trusted))
            raw_inputs.append(trusted)
        report_entries.extend((item.package_ref, item.envelope) for item in registry.entries)
    raw_registry = build_authenticated_raw_source_registry(tuple(raw_entries))
    return build_authenticated_raw_source_report_registry(
        tuple(report_entries),
        raw_source_registry=raw_registry,
        raw_source_inputs=tuple(raw_inputs),
    )


def _source_report(
    root: Path,
    *,
    preflight: PreflightResult,
    preflight_bytes: bytes,
    tool_sha256: str,
    target_root: str,
    occurrence: str,
) -> tuple[Path, DependencyPins, EvidenceLineageTrust]:
    if preflight.package_identity is None:
        raise RuntimeError("synthetic source report requires a package identity")
    root.mkdir()
    evidence = (SCHEMA_REVISION + "\n" + SCHEMA_REVISION).encode()
    evidence_digest = hashlib.sha256(evidence).hexdigest()
    evidence_member = f"evidence/sha256/{evidence_digest}"
    inputs = {
        "inputs/corpus.json": _json_line({"kind": "synthetic-corpus"}),
        "inputs/ir.json": _json_line(_empty_current_ir()),
        "inputs/preflight.json": preflight_bytes,
        "inputs/schema.json": _json_line(schema_document()),
        evidence_member: evidence,
    }
    members = {
        "ANALYSIS.md": b"Synthetic validation fixture.\n",
        "SEARCH_LOG.md": b"Synthetic validation fixture.\n",
        "reproducers/vector.py": b"# Deterministic synthetic evidence reproducer.\n",
        "analysis.json": _json_line(
            _complete_analysis_report(
                artifact_digest=preflight.artifact_digest,
                package_name=preflight.package_identity.package_name,
            )
        ),
        **inputs,
    }
    for relative, payload in members.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    digests = {name: hashlib.sha256(payload).hexdigest() for name, payload in inputs.items()}
    pins = DependencyPins(
        digests["inputs/preflight.json"],
        digests["inputs/ir.json"],
        digests["inputs/schema.json"],
        digests["inputs/corpus.json"],
    )
    contract = {
        "contract_revision": CONTRACT_REVISION,
        "dependencies": {
            name: {"member": f"inputs/{name}.json", "sha256": digest}
            for name, digest in pins.as_pairs()
        },
        "evidence_members": [
            {
                "member": evidence_member,
                "owner": preflight.artifact_digest,
                "sha256": evidence_digest,
            }
        ],
        "anchors": [
            {
                "id": "schema",
                "owner": preflight.artifact_digest,
                "member": evidence_member,
                "start_byte": 0,
                "end_byte": len(SCHEMA_REVISION),
                "ir_pointer": "/schema_revision",
                "representation": "utf8",
            }
        ],
    }
    _write(root, "validation-input.json", _json_line(contract), members)
    _write_manifest(root, members)
    lineage = _lineage(
        preflight,
        pins.preflight_sha256,
        evidence_member,
        evidence,
        tool_sha256,
        package_scopes=(),
        target_root=target_root,
        occurrence=occurrence,
        evidence_anchor_ids=("schema",),
    )
    return root, pins, lineage


def _package_report(
    partial: IncompleteSyntheticPackage,
    execution_plan: PackageExecutionPlan,
    source_registry: AuthenticatedSourceReportRegistry,
) -> tuple[Path, PackageDependencyPins, EvidenceLineageTrust]:
    root = partial.package_root / "package-report"
    root.mkdir()
    local_evidence = b"CLOSED"
    local_digest = hashlib.sha256(local_evidence).hexdigest()
    local_member = f"evidence/sha256/{local_digest}"
    final_ir, trusted = _authorized_final_ir(source_registry)
    final_ir_bytes = _json_line(final_ir)
    final_document = loads_final_ir(final_ir_bytes, trusted_receipts=trusted)
    markdown = render_final_ir_markdown(final_document).encode()
    frozen = freeze_package_execution_plan(execution_plan)
    corpus = _json_line({"kind": "synthetic-corpus"})
    inputs = {
        "inputs/corpus.json": corpus,
        "inputs/execution_plan.json": frozen.canonical_bytes,
        "inputs/ir.json": final_ir_bytes,
        "inputs/preflight.json": partial.preflight_bytes,
        "inputs/report_schema.json": PACKAGE_REPORT_SCHEMA_CANONICAL_BYTES,
        "inputs/schema.json": FINAL_IR_SCHEMA_CANONICAL_BYTES,
        local_member: local_evidence,
    }
    dependencies = PackageDependencyPins(
        hashlib.sha256(partial.preflight_bytes).hexdigest(),
        hashlib.sha256(final_ir_bytes).hexdigest(),
        FINAL_IR_SCHEMA_SHA256,
        hashlib.sha256(corpus).hexdigest(),
        frozen.canonical_sha256,
        PACKAGE_REPORT_SCHEMA_SHA256,
    )
    full_roots = [
        root_plan
        for root_plan in execution_plan.root_plans
        if isinstance(root_plan, FullAnalysisRootPlan)
    ]
    root_evidence = b"Raise"
    root_digest = hashlib.sha256(root_evidence).hexdigest()
    root_member = f"evidence/sha256/{root_digest}"
    if full_roots:
        inputs[root_member] = root_evidence
    authoritative_root_results = []
    for root_plan in execution_plan.root_plans:
        if isinstance(root_plan, FullAnalysisRootPlan):
            root_semantic = root_digest
            result = {
                "analysis": {"semantic_root_sha256": root_semantic},
                "status": "COMPLETE",
            }
        else:
            root_semantic = root_plan.reuse.inherited_semantic_root_sha256
            result = {
                "reuse": {
                    "inherited_semantic_root_sha256": root_semantic,
                    "source_root_id": root_plan.reuse.source_root_id,
                },
                "status": "COMPLETE",
            }
        authoritative_root_results.append(
            {
                "result": result,
                "route": root_plan.route.value,
                "target_occurrence_identity_sha256": (
                    root_plan.target_occurrence_identity_sha256
                ),
                "target_root_id": root_plan.target_root_id,
            }
        )
    report = {
        "authoritative_root_results": authoritative_root_results,
        "final_ir_json_sha256": dependencies.ir_sha256,
        "final_ir_markdown_sha256": hashlib.sha256(markdown).hexdigest(),
        "final_ir_schema_revision": FINAL_SCHEMA_REVISION,
        "package_local_domains": {
            domain: {"evidence": [local_member], "status": "COMPLETE"}
            for domain in LOCAL_ONLY_DOMAINS
        },
        "report_revision": PACKAGE_REPORT_REVISION,
        "target_package_identity": {
            "artifact_digest": partial.package_local.target_artifact_digest,
            "package_name": partial.package_local.package_name,
            "version_code": partial.package_local.version_code,
            "version_name": partial.package_local.version_name,
        },
    }
    members = {
        "ANALYSIS.md": markdown,
        "SEARCH_LOG.md": b"Synthetic production-path acceptance fixture.\n",
        "reproducers/vector.py": b"# Deterministic synthetic evidence reproducer.\n",
        "analysis.json": _json_line(report),
        **inputs,
    }
    for relative, payload in members.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    evidence_members = [
        {
            "member": local_member,
            "owner": partial.package_local.target_artifact_digest,
            "package_local_domains": list(LOCAL_ONLY_DOMAINS),
            "sha256": local_digest,
        }
    ]
    anchors = [
        {
            "id": "local-evidence",
            "owner": partial.package_local.target_artifact_digest,
            "member": local_member,
            "start_byte": 0,
            "end_byte": len(local_evidence),
            "ir_pointer": "/domain_closure/status",
            "representation": "utf8",
        }
    ]
    if full_roots:
        evidence_members.append(
            {
                "member": root_member,
                "owner": partial.package_local.target_artifact_digest,
                "package_local_domains": [],
                "sha256": root_digest,
            }
        )
        anchors.append(
            {
                "id": "root-evidence",
                "owner": partial.package_local.target_artifact_digest,
                "member": root_member,
                "start_byte": 0,
                "end_byte": len(root_evidence),
                "ir_pointer": "/actions/raise/summary",
                "representation": "utf8",
            }
        )
    contract = {
        "contract_revision": PACKAGE_CONTRACT_REVISION,
        "dependencies": {
            name: {"member": f"inputs/{name}.json", "sha256": digest}
            for name, digest in dependencies.as_pairs()
        },
        "evidence_members": evidence_members,
        "anchors": anchors,
    }
    _write(root, "validation-input.json", _json_line(contract), members)
    _write_manifest(root, members)
    lineage = _package_lineage(
        partial,
        dependencies.preflight_sha256,
        local_member,
        local_evidence,
        root_member if full_roots else None,
        root_evidence if full_roots else None,
        full_roots[0] if full_roots else None,
    )
    return root, dependencies, lineage


@dataclass(frozen=True, slots=True)
class _MemberView:
    name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class _PreflightView:
    artifact_digest: str
    artifact_members: tuple[_MemberView, ...]
    decision: object

    def __init__(self, partial: IncompleteSyntheticPackage) -> None:
        object.__setattr__(self, "artifact_digest", partial.package_local.target_artifact_digest)
        object.__setattr__(
            self,
            "artifact_members",
            tuple(_MemberView(*item) for item in partial.artifact_members),
        )
        object.__setattr__(self, "decision", None)


def _package_lineage(
    partial: IncompleteSyntheticPackage,
    preflight_sha256: str,
    local_member: str,
    local_evidence: bytes,
    root_member: str | None,
    root_evidence: bytes | None,
    full_root: FullAnalysisRootPlan | None,
) -> EvidenceLineageTrust:
    source_members = [
        {"name": name, "sha256": digest} for name, digest in partial.artifact_members
    ]
    local_producer = TrustedProducer("pipeline-v1", "apktool", partial.tool_sha256)
    producers = [local_producer]
    members = [
        {
            "authoritative_root_analyses": [],
            "package_local_domains": list(LOCAL_ONLY_DOMAINS),
            "producer": {
                "invocation_sha256": _digest("synthetic-local-invocation"),
                "outcome": "SUCCEEDED",
                "output_size": len(local_evidence),
                "pipeline_revision": local_producer.pipeline_revision,
                "route": local_producer.route,
                "tool_sha256": local_producer.tool_sha256,
            },
            "report_member": local_member,
            "sha256": hashlib.sha256(local_evidence).hexdigest(),
            "source_artifact_members": source_members,
        }
    ]
    if root_member is not None and root_evidence is not None and full_root is not None:
        root_producer = TrustedProducer("pipeline-v1", "apktool", partial.tool_sha256)
        if root_producer not in producers:
            producers.append(root_producer)
        members.append(
            {
                "authoritative_root_analyses": [
                    {
                        "semantic_root_sha256": hashlib.sha256(root_evidence).hexdigest(),
                        "target_occurrence_identity_sha256": (
                            full_root.target_occurrence_identity_sha256
                        ),
                        "target_root_id": full_root.target_root_id,
                        "evidence_anchor_ids": ["root-evidence"],
                    }
                ],
                "package_local_domains": [],
                "producer": {
                    "invocation_sha256": _digest("synthetic-root-invocation"),
                    "outcome": "SUCCEEDED",
                    "output_size": len(root_evidence),
                    "pipeline_revision": root_producer.pipeline_revision,
                    "route": root_producer.route,
                    "tool_sha256": root_producer.tool_sha256,
                },
                "report_member": root_member,
                "sha256": hashlib.sha256(root_evidence).hexdigest(),
                "source_artifact_members": source_members,
            }
        )
    members.sort(key=lambda item: str(item["report_member"]).encode())
    document = {
        "artifact_digest": partial.package_local.target_artifact_digest,
        "members": members,
        "preflight_sha256": preflight_sha256,
        "schema": LINEAGE_SCHEMA_REVISION,
    }
    payload = _canonical(document)
    return EvidenceLineageTrust(
        payload,
        hashlib.sha256(payload).hexdigest(),
        tuple(sorted(producers, key=lambda item: (item.pipeline_revision, item.route))),
    )


def _lineage(
    preflight: PreflightResult | _PreflightView,
    preflight_sha256: str,
    evidence_member: str,
    evidence: bytes,
    tool_sha256: str,
    *,
    package_scopes: tuple[str, ...],
    target_root: str | None,
    occurrence: str | None,
    evidence_anchor_ids: tuple[str, ...],
    producer: TrustedProducer | None = None,
) -> EvidenceLineageTrust:
    artifact_digest = preflight.artifact_digest
    artifact_members = preflight.artifact_members
    source_members = [{"name": item.name, "sha256": item.sha256} for item in artifact_members]
    producer = producer or TrustedProducer("pipeline-v1", "apktool", tool_sha256)
    root_analyses = (
        []
        if target_root is None or occurrence is None
        else [
            {
                "semantic_root_sha256": hashlib.sha256(evidence).hexdigest(),
                "target_occurrence_identity_sha256": occurrence,
                "target_root_id": target_root,
                "evidence_anchor_ids": list(evidence_anchor_ids),
            }
        ]
    )
    document = {
        "artifact_digest": artifact_digest,
        "members": [
            {
                "authoritative_root_analyses": root_analyses,
                "package_local_domains": list(package_scopes),
                "producer": {
                    "invocation_sha256": _digest("synthetic-invocation"),
                    "outcome": "SUCCEEDED",
                    "output_size": len(evidence),
                    "pipeline_revision": producer.pipeline_revision,
                    "route": producer.route,
                    "tool_sha256": producer.tool_sha256,
                },
                "report_member": evidence_member,
                "sha256": hashlib.sha256(evidence).hexdigest(),
                "source_artifact_members": source_members,
            }
        ],
        "preflight_sha256": preflight_sha256,
        "schema": LINEAGE_SCHEMA_REVISION,
    }
    payload = _canonical(document)
    return EvidenceLineageTrust(
        payload,
        hashlib.sha256(payload).hexdigest(),
        (producer,),
    )


def _synthetic_terminal_semantics() -> dict[str, object]:
    """Return one closed, nontrivial protocol universe with scalar evidence leaves."""

    data: dict[str, object] = {
        "schema_revision": FINAL_SCHEMA_REVISION,
        "source_packages": {},
        "evidence_files": {},
        "evidence_anchors": {},
        "source_sets": {},
        "evidence_bindings": {},
        **{name: {} for name in FINAL_DOMAIN_COLLECTIONS},
        "variant_spaces": {
            "variants": {
                "dimensions": {"side": ["left"]},
                "constraints": [{"op": "always"}],
            }
        },
        "protocols": {"primary": {"variant_space": "variants"}},
        "actions": {
            "raise": {"summary": "Raise"},
            "stop": {"summary": "Stop"},
        },
        "expected_action_rules": {
            "expect_raise": {
                "protocol": "primary",
                "action": "raise",
                "when": {"op": "always"},
            }
        },
        "selectors": {
            "side": {
                "variant_space": "variants",
                "dimension": "side",
                "kind": "VARIANT",
                "values": ["left"],
            }
        },
        "selection_rules": {
            "select": {"protocol": "primary", "when": {"op": "always"}}
        },
        "discovery_rules": {
            "discover": {
                "selection_rule": "select",
                "matchers": [
                    {"field": "SERVICE_UUID", "operation": "EQUALS", "value": "service"}
                ],
            }
        },
        "gatt_services": {"service": {"uuid": "service", "role": "CONTROL"}},
        "gatt_characteristics": {
            "write": {
                "service": "service",
                "uuid": "write",
                "roles": ["WRITE"],
                "write_modes": ["WITHOUT_RESPONSE"],
            }
        },
        "transforms": {"identity": {"operation": "IDENTITY"}},
        "checksums": {
            "checksum": {
                "algorithm": "SUM8",
                "start_byte": 0,
                "end_byte": 1,
                "output_width": 1,
            }
        },
        "framings": {"frame": {"prefix_hex": "aa", "suffix_hex": "55"}},
        "packet_fields": {
            "command": {
                "offset": 0,
                "width": 1,
                "source": "CONSTANT",
                "constant_hex": "01",
                "transforms": ["identity"],
            }
        },
        "packet_builders": {
            "builder": {
                "fields": ["command"],
                "framing": "frame",
                "checksum": "checksum",
            }
        },
        "authentications": {"auth": {"method": "PIN", "selectors": ["side"]}},
        "bufferings": {"datagram": {"mode": "DATAGRAM"}},
        "parser_fields": {
            "state": {
                "offset": 0,
                "width": 1,
                "target_selector": "side",
                "transforms": ["identity"],
            }
        },
        "notification_parsers": {
            "parser": {"buffering": "datagram", "fields": ["state"]}
        },
        "timings": {
            "movement": {
                "repeat_count": 1,
                "repeat_interval_ms": 100,
                "cancellation": "AFTER_FRAME",
                "release": "STOP_ACTION",
                "release_action": "stop",
            }
        },
        "lifecycles": {"command": {"phases": ["CONNECT", "WRITE", "DISCONNECT"]}},
        "transports": {
            "transport": {
                "characteristic": "write",
                "write_mode": "WITHOUT_RESPONSE",
                "packet_builder": "builder",
                "notification_parser": "parser",
                "authentication": "auth",
                "timing": "movement",
                "lifecycle": "command",
            }
        },
        "action_mappings": {
            "raise_mapping": {
                "protocol": "primary",
                "action": "raise",
                "transport": "transport",
                "when": {"op": "always"},
            }
        },
        "domain_closure": {
            "status": "CLOSED",
            "domains": list(FINAL_DOMAIN_COLLECTIONS),
            "unmodeled_paths": [],
        },
    }
    return data


def _authorized_final_ir(
    source_registry: AuthenticatedSourceReportRegistry | None = None,
) -> tuple[dict[str, object], dict[str, str]]:
    data: dict[str, object] = {
        "schema_revision": FINAL_SCHEMA_REVISION,
        "source_packages": {},
        "evidence_files": {},
        "evidence_anchors": {},
        "source_sets": {},
        "evidence_bindings": {},
        **{name: {} for name in FINAL_DOMAIN_COLLECTIONS},
        "domain_closure": {
            "status": "CLOSED",
            "domains": list(FINAL_DOMAIN_COLLECTIONS),
            "unmodeled_paths": [],
        },
    }
    if source_registry is not None:
        packages: dict[str, object] = {}
        files: dict[str, object] = {}
        final_anchors: dict[str, object] = {}
        source_sets: dict[str, object] = {}
        bindings: dict[str, object] = {}
        sets_by_pointer: dict[str, list[str]] = {}
        trusted: dict[str, str] = {}
        for source in source_registry.entries:
            if len(source.report.validated_root_evidence) != 1:
                raise RuntimeError("synthetic final IR requires one root per source report")
            root = source.report.validated_root_evidence[0]
            root_anchor_ids = {
                anchor_id
                for member in root.evidence_members
                for anchor_id in member.evidence_anchor_ids
            }
            package_id, package = build_source_package(
                source.source_package.artifact, source.source_package.report
            )
            packages[package_id] = package.to_data()
            file_ids: dict[str, str] = {}
            root_members = {item.member for item in root.evidence_members}
            for member in source.report.validated_evidence_members:
                if member.member not in root_members:
                    continue
                file_id, evidence_file = build_evidence_file(
                    package=package_id, member=member.member, sha256=member.sha256
                )
                file_ids[member.member] = file_id
                files[file_id] = evidence_file.to_data()
            for anchor in source.report.validated_evidence_anchors:
                if anchor.id not in root_anchor_ids:
                    continue
                anchor_id, evidence_anchor = build_evidence_anchor(
                    id=anchor.id,
                    file=file_ids[anchor.member],
                    start_byte=anchor.start_byte,
                    end_byte=anchor.end_byte,
                    ir_pointer=anchor.ir_pointer,
                    representation=anchor.representation,
                    value_sha256=anchor.value_sha256,
                )
                final_anchors[anchor_id] = evidence_anchor.to_data()
                source_set_id, source_set = build_source_set(
                    package=package_id, anchors=(anchor_id,)
                )
                source_sets[source_set_id] = source_set.to_data()
                sets_by_pointer.setdefault(anchor.ir_pointer, []).append(source_set_id)
            trusted[source.report.validation_receipt_sha256] = source.report.bundle_sha256
        for pointer, source_set_ids in sets_by_pointer.items():
            binding_id, binding = build_evidence_binding(
                target=pointer,
                source_sets=tuple(sorted(source_set_ids)),
            )
            bindings[binding_id] = binding.to_data()
        data["source_packages"] = packages
        data["evidence_files"] = files
        data["evidence_anchors"] = final_anchors
        data["source_sets"] = source_sets
        data["evidence_bindings"] = bindings
        semantics = _synthetic_terminal_semantics()
        for name in (*FINAL_DOMAIN_COLLECTIONS, "domain_closure"):
            data[name] = semantics[name]
        return data, trusted
    pointers = [
        "/domain_closure/status",
        *(f"/domain_closure/domains/{index}" for index in range(len(FINAL_DOMAIN_COLLECTIONS))),
        "/domain_closure/unmodeled_paths",
    ]
    artifact = build_artifact_identity(
        package_name="synthetic.protocol",
        version_code="1",
        version_name="1.0",
        artifact_digest="a" * 64,
    )
    member = "evidence/synthetic.txt"
    member_digest = hashlib.sha256(b"synthetic").hexdigest()
    values = ["CLOSED", *FINAL_DOMAIN_COLLECTIONS, []]
    attestations = [
        {
            "id": f"claim-{index}",
            "owner": artifact.artifact_digest,
            "member": member,
            "member_sha256": member_digest,
            "start_byte": index,
            "end_byte": index + 1,
            "ir_pointer": pointer,
            "representation": "utf8",
            "value_sha256": hashlib.sha256(_canonical(value)).hexdigest(),
        }
        for index, (pointer, value) in enumerate(zip(pointers, values, strict=True))
    ]
    attestations.sort(key=lambda item: str(item["id"]).encode())
    receipt_data = {
        "accepted": True,
        "bundle_sha256": "b" * 64,
        "contract_revision": CONTRACT_REVISION,
        "declared_members": 1,
        "dependency_digests": {
            name: str(index) * 64
            for index, name in enumerate(
                ("corpus", "evidence_lineage", "ir", "preflight", "schema"), start=1
            )
        },
        "diagnostics": [],
        "discovered_members": 1,
        "evidence_anchors_checked": len(attestations),
        "report_manifest_sha256": "c" * 64,
        "source_unchanged": True,
        "validated_artifact_identity": artifact.to_data(),
        "validated_evidence_anchors": attestations,
        "validated_evidence_members": [
            {"member": member, "owner": artifact.artifact_digest, "sha256": member_digest}
        ],
        "validated_root_evidence": [],
        "validation_profile": BOUND_VALIDATION_PROFILE,
        "validator_revision": SUPPORTED_VALIDATOR_REVISION,
    }
    receipt_id = hashlib.sha256(_canonical(receipt_data)).hexdigest()
    receipt_data["validation_receipt_sha256"] = receipt_id
    report = bind_validator_receipt(
        _canonical(receipt_data),
        trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
        trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
        trusted_dependency_digests=receipt_data["dependency_digests"],
        trusted_receipt_sha256=receipt_id,
    )
    package_id, package = build_source_package(artifact, report)
    file_id, evidence_file = build_evidence_file(
        package=package_id, member=member, sha256=member_digest
    )
    anchors: dict[str, object] = {}
    source_sets: dict[str, object] = {}
    bindings: dict[str, object] = {}
    for item in attestations:
        anchor_id, anchor = build_evidence_anchor(
            id=str(item["id"]),
            file=file_id,
            start_byte=int(item["start_byte"]),
            end_byte=int(item["end_byte"]),
            ir_pointer=str(item["ir_pointer"]),
            representation="utf8",
            value_sha256=str(item["value_sha256"]),
        )
        source_set_id, source_set = build_source_set(package=package_id, anchors=(anchor_id,))
        binding_id, binding = build_evidence_binding(
            target=str(item["ir_pointer"]), source_sets=(source_set_id,)
        )
        anchors[anchor_id] = anchor.to_data()
        source_sets[source_set_id] = source_set.to_data()
        bindings[binding_id] = binding.to_data()
    data["source_packages"] = {package_id: package.to_data()}
    data["evidence_files"] = {file_id: evidence_file.to_data()}
    data["evidence_anchors"] = anchors
    data["source_sets"] = source_sets
    data["evidence_bindings"] = bindings
    return data, {receipt_id: report.bundle_sha256}


def _empty_current_ir() -> dict[str, object]:
    return {
        "actions": {},
        "command_bindings": {},
        "evidence_anchors": {},
        "evidence_bindings": {},
        "evidence_files": {},
        "expected_action_rules": {},
        "protocols": {},
        "schema_revision": SCHEMA_REVISION,
        "source_packages": {},
        "source_sets": {},
        "variant_spaces": {},
    }


def _complete_analysis_report(*, artifact_digest: str, package_name: str) -> dict[str, object]:
    gates = (
        "identity_verified",
        "stack_coverage",
        "artifact_inventory",
        "decompiler_warnings_resolved",
        "search_passes_recorded",
        "transport_callsites_dispositioned",
        "protocol_candidates_dispositioned",
        "control_actions_traced",
        "command_rows_complete",
        "test_vectors_reproducible",
        "feature_domains_searched",
        "second_pass_clean",
        "variant_reconciliation",
        "schema_validation",
        "report_agreement",
        "cleanroom_isolation",
        "uncertainties_actionable",
    )
    return {
        "schema_revision": "phase4-analysis-v1.12-2026-07-26",
        "status": "COMPLETE",
        "artifact": {
            "app_name": "Synthetic fixture",
            "package_id": package_name,
            "version_name": "1.0",
            "version_code": "1",
            "artifact_set_sha256": artifact_digest,
            "files": [{"file": "base.apk", "size": 1, "sha256": "f" * 64}],
            "signer_certificate_sha256": ["9" * 64],
            "source": "synthetic fixture",
        },
        "analyst": {
            "identity": "synthetic",
            "prompt_revision": "synthetic",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T00:00:01Z",
        },
        "tool_coverage": [
            {
                "tool": "synthetic",
                "version": "1",
                "purpose": "validation fixture",
                "status": "COMPLETE",
            }
        ],
        "application_stacks": [
            {"stack": "android", "present": True, "coverage": "COMPLETE", "evidence": ["synthetic"]}
        ],
        "variant_inventory": [],
        "candidate_ledger": [
            {
                "id": "candidate-1",
                "category": "transport",
                "source": "synthetic",
                "disposition": "DEAD/UNUSED",
                "evidence": ["synthetic"],
            }
        ],
        "protocols": [],
        "test_vectors": [],
        "evidence": [
            {
                "id": "evidence-1",
                "claim": "Synthetic fixture",
                "paths": ["ANALYSIS.md"],
                "confidence": "VERIFIED",
            }
        ],
        "completion_gates": [
            {"gate": gate, "result": "PASS", "evidence": ["synthetic"]} for gate in gates
        ],
        "limitations": ["No reachable protocol exists in this synthetic fixture."],
        "blockers": [],
        "deferred_external_validation": [],
    }


def _registry(tool: Path, profile: ExecutionProfile) -> ApprovedToolRegistry:
    spec = ToolSpec(
        str(tool),
        ("--version",),
        ("--deterministic", "apktool", "{input}", "{output}"),
        ("--deterministic",),
        str(tool.parent),
    )
    record = qualify_tool(spec, profile)
    if any(
        value is None
        for value in (
            record.binary_sha256,
            record.version,
            record.runtime_sha256,
            record.runtime_files,
        )
    ):
        raise RuntimeError("synthetic tool qualification failed")
    assert record.binary_sha256 is not None
    assert record.version is not None
    assert record.runtime_sha256 is not None
    assert record.runtime_files is not None
    qualification = ToolQualification(
        record.binary_sha256,
        record.version,
        record.runtime_sha256,
        record.runtime_files,
    )
    return ApprovedToolRegistry(
        "synthetic-registry-v1",
        "pipeline-v1",
        tuple(
            ApprovedRoute(
                route,
                ToolSpec(
                    str(tool),
                    ("--version",),
                    ("--deterministic", route, "{input}", "{output}"),
                    ("--deterministic",),
                    str(tool.parent),
                ),
                (qualification,),
                OutputSufficiencyContract(
                    required_suffixes=((".smali",) if route == "apktool" else (".java",))
                ),
            )
            for route in REQUIRED_PREPARATION_ROUTES
        ),
    )


@cache
def _build_static_tool(emit_candidates: bool = True) -> Path:
    tool_root = Path(tempfile.mkdtemp(prefix="phase4-v2-synthetic-tool-"))
    source = tool_root / "fixture.c"
    binary = tool_root / "fixture-tool"
    semantic_body = "BluetoothGatt" + "x" * 16_384
    output_statements = (
        f'if(strcmp(route,"apktool")==0)write_file(out,"smali","App.smali","{semantic_body}");\n'
        f' if(strcmp(route,"jadx")==0)write_file(out,"sources","App.java","{semantic_body}");'
        if emit_candidates
        else 'write_file(out,"smali","App.smali","synthetic fixture");'
    )
    source.write_text(
        r"""#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static void write_file(const char *root, const char *dir, const char *name, const char *body) {
 char d[4096], p[4096]; snprintf(d,sizeof(d),"%s/%s",root,dir); mkdir(d,0700);
 snprintf(p,sizeof(p),"%s/%s",d,name); int fd=open(p,O_WRONLY|O_CREAT|O_TRUNC,0600);
 if(fd<0||write(fd,body,strlen(body))!=(ssize_t)strlen(body)) exit(92); close(fd);
}
int main(int argc,char **argv) {
 if(argc==2&&strcmp(argv[1],"--version")==0){puts("synthetic-tool 1.0");return 0;}
 if(argc<5)return 90; const char *route=argv[argc-3],*out=argv[argc-1];
 """
        + output_statements
        + r"""
 return 0;
}""",
        encoding="utf-8",
    )
    subprocess.run(
        ["gcc", "-static", "-O2", "-s", str(source), "-o", str(binary)],
        check=True,
        capture_output=True,
    )
    source.unlink()
    return binary


def _write(root: Path, relative: str, payload: bytes, members: dict[str, bytes]) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    members[relative] = payload


def _write_manifest(root: Path, members: dict[str, bytes]) -> None:
    (root / "REPORT.SHA256").write_text(
        "".join(
            f"{hashlib.sha256(payload).hexdigest()}  {path}\n"
            for path, payload in sorted(members.items())
        ),
        encoding="utf-8",
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _json_line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
