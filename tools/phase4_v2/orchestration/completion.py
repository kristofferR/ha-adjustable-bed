"""Authenticated, content-bound completion adapters for semantic cluster stages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from tools.phase4_v2.equivalence.plan import VALIDATED_PACKAGE_OUTPUT_REVISION
from tools.phase4_v2.queue import (
    ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
    ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
    ORCHESTRATION_PACKAGE_AUDIT_KIND,
    ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    CapabilityPin,
    CompletionDependencyPin,
    FanoutPublishReceipt,
    InputCheckedFinishResult,
    Lease,
    Queue,
    QueueConflictError,
)

from .graph import (
    CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
    CLUSTER_RECONCILIATION_COMPLETION_REVISION,
    PACKAGE_AUDIT_COMPLETION_REVISION,
    TRACKER_PUBLICATION_COMPLETION_REVISION,
    ClusterGraphPlan,
    cluster_implementation_unit_id,
    cluster_reconciliation_unit_id,
    completion_pin,
    completion_pins,
    package_audit_unit_id,
    stage_input_sha256,
    tracker_publication_unit_id,
    validate_cluster_graph,
)

STAGE_AUTHORITY_REVISION = "phase4-v2-stage-authority-v1"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_STAGES = frozenset({"audit", "reconciliation", "implementation", "publication"})
_MAX_DOCUMENT_BYTES = 1024 * 1024
_MAX_DIAGNOSTICS = 4_096
_MAX_PACKAGES = 250


@dataclass(frozen=True, slots=True, init=False)
class ActivatedStageAuthority:
    """One stage verifier admitted only through an externally pinned activation."""

    stage: str
    authority_id: str
    public_key: str
    canonical_bytes: bytes
    authority_sha256: str
    generation: int

    def __init__(self) -> None:
        raise ValueError("stage authorities must be loaded from a pinned activation")


def load_stage_authority(canonical_bytes: bytes) -> ActivatedStageAuthority:
    """Activate canonical authority bytes against deployment-owned protected pins."""

    return _load_stage_authority_with_config(canonical_bytes, _load_stage_authority_config())


def _load_stage_authority_with_config(
    canonical_bytes: bytes, config: Mapping[str, tuple[str, int]]
) -> ActivatedStageAuthority:

    raw = _canonical_document(canonical_bytes, "stage authority")
    _keys(raw, {"authority_id", "generation", "public_key", "revision", "stage"}, "stage authority")
    stage = _stage(raw["stage"])
    expected = config.get(stage)
    if expected is None:
        raise QueueConflictError("stage authority has no protected activation")
    expected_sha256, expected_generation = expected
    if _authority_sha256(canonical_bytes) != expected_sha256:
        raise QueueConflictError("stage authority does not match protected activation")
    if raw["revision"] != STAGE_AUTHORITY_REVISION:
        raise QueueConflictError("stage authority revision is unsupported")
    authority_id = _token(raw["authority_id"], "authority id")
    public_key = _digest(raw["public_key"], "authority public key")
    generation = raw["generation"]
    if type(generation) is not int or generation < 1 or generation != expected_generation:
        raise QueueConflictError("stage authority generation does not match protected activation")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
    result = object.__new__(ActivatedStageAuthority)
    object.__setattr__(result, "stage", stage)
    object.__setattr__(result, "authority_id", authority_id)
    object.__setattr__(result, "public_key", public_key)
    object.__setattr__(result, "canonical_bytes", canonical_bytes)
    object.__setattr__(result, "authority_sha256", expected_sha256)
    object.__setattr__(result, "generation", generation)
    return result


def stage_authority_capability(authority: ActivatedStageAuthority) -> CapabilityPin:
    """Derive the sole canonical queue capability from a protected authority."""

    restored = _revalidate_authority(authority)
    return CapabilityPin(
        f"phase4-v2-stage-authority:{restored.stage}",
        f"{STAGE_AUTHORITY_REVISION}:generation:{restored.generation}",
        restored.authority_sha256,
    )


@dataclass(frozen=True, slots=True, init=False)
class TrustedPackageAuditReceipt:
    revision: str
    authority_sha256: str
    graph_sha256: str
    cluster_id: str
    package_ref_id: str
    stage_input_sha256: str
    analysis_completion_revision: str
    analysis_completion_sha256: str
    package_surface_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        raise ValueError("audit receipts must be loaded from signed canonical bytes")


@dataclass(frozen=True, slots=True, init=False)
class TrustedReconciliationReceipt:
    revision: str
    authority_sha256: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    package_audit_receipts: tuple[tuple[str, str], ...]
    reconciliation_result_sha256: str
    completeness_receipt_sha256: str
    disposition_ledger_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        raise ValueError("reconciliation receipts must be loaded from signed canonical bytes")


@dataclass(frozen=True, slots=True, init=False)
class TrustedImplementationReceipt:
    revision: str
    authority_sha256: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    reconciliation_receipt_sha256: str
    disposition_ledger_sha256: str
    implementation_output_sha256: str
    accepted: bool
    diagnostics: tuple[str, ...]
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        raise ValueError("implementation receipts must be loaded from signed canonical bytes")


@dataclass(frozen=True, slots=True, init=False)
class TrustedPublicationReceipt:
    revision: str
    authority_sha256: str
    graph_sha256: str
    cluster_id: str
    stage_input_sha256: str
    implementation_receipt_sha256: str
    queue_generation_sha256: str
    document_set_sha256: str
    publication_config_sha256: str
    before_revision: str
    after_revision: str
    paths: tuple[str, ...]
    changed: bool
    accepted: bool
    diagnostics: tuple[str, ...]
    canonical_bytes: bytes
    receipt_sha256: str

    def __init__(self) -> None:
        raise ValueError("publication receipts must be loaded from signed canonical bytes")


@dataclass(frozen=True, slots=True)
class StageCompletion:
    receipt_sha256: str
    queue_result: InputCheckedFinishResult


def load_package_audit_receipt(
    canonical_bytes: bytes, authority: ActivatedStageAuthority
) -> TrustedPackageAuditReceipt:
    payload, receipt_sha256 = _load_signed(canonical_bytes, authority, "audit")
    _keys(payload, _AUDIT_FIELDS, "audit receipt")
    return _new_receipt(
        TrustedPackageAuditReceipt,
        canonical_bytes,
        receipt_sha256,
        revision=_exact_revision(payload["revision"], PACKAGE_AUDIT_COMPLETION_REVISION, "audit"),
        authority_sha256=_digest(payload["authority_sha256"], "audit authority"),
        graph_sha256=_digest(payload["graph_sha256"], "audit graph"),
        cluster_id=_token(payload["cluster_id"], "audit cluster"),
        package_ref_id=_digest(payload["package_ref_id"], "audit package"),
        stage_input_sha256=_digest(payload["stage_input_sha256"], "audit input"),
        analysis_completion_revision=_revision(
            payload["analysis_completion_revision"], "analysis completion revision"
        ),
        analysis_completion_sha256=_digest(
            payload["analysis_completion_sha256"], "analysis completion"
        ),
        package_surface_sha256=_digest(payload["package_surface_sha256"], "package surface"),
        accepted=_accepted(payload["accepted"], payload["diagnostics"], "audit"),
        diagnostics=_diagnostics(payload["diagnostics"], "audit diagnostics"),
    )


def load_reconciliation_receipt(
    canonical_bytes: bytes, authority: ActivatedStageAuthority
) -> TrustedReconciliationReceipt:
    payload, receipt_sha256 = _load_signed(canonical_bytes, authority, "reconciliation")
    _keys(payload, _RECONCILIATION_FIELDS, "reconciliation receipt")
    return _new_receipt(
        TrustedReconciliationReceipt,
        canonical_bytes,
        receipt_sha256,
        revision=_exact_revision(
            payload["revision"], CLUSTER_RECONCILIATION_COMPLETION_REVISION, "reconciliation"
        ),
        authority_sha256=_digest(payload["authority_sha256"], "reconciliation authority"),
        graph_sha256=_digest(payload["graph_sha256"], "reconciliation graph"),
        cluster_id=_token(payload["cluster_id"], "reconciliation cluster"),
        stage_input_sha256=_digest(payload["stage_input_sha256"], "reconciliation input"),
        package_audit_receipts=_pairs(
            payload["package_audit_receipts"], "reconciliation package audit receipts"
        ),
        reconciliation_result_sha256=_digest(
            payload["reconciliation_result_sha256"], "reconciliation result"
        ),
        completeness_receipt_sha256=_digest(
            payload["completeness_receipt_sha256"], "completeness receipt"
        ),
        disposition_ledger_sha256=_digest(
            payload["disposition_ledger_sha256"], "disposition ledger"
        ),
        accepted=_accepted(payload["accepted"], payload["diagnostics"], "reconciliation"),
        diagnostics=_diagnostics(payload["diagnostics"], "reconciliation diagnostics"),
    )


def load_implementation_receipt(
    canonical_bytes: bytes, authority: ActivatedStageAuthority
) -> TrustedImplementationReceipt:
    payload, receipt_sha256 = _load_signed(canonical_bytes, authority, "implementation")
    _keys(payload, _IMPLEMENTATION_FIELDS, "implementation receipt")
    return _new_receipt(
        TrustedImplementationReceipt,
        canonical_bytes,
        receipt_sha256,
        revision=_exact_revision(
            payload["revision"], CLUSTER_IMPLEMENTATION_COMPLETION_REVISION, "implementation"
        ),
        authority_sha256=_digest(payload["authority_sha256"], "implementation authority"),
        graph_sha256=_digest(payload["graph_sha256"], "implementation graph"),
        cluster_id=_token(payload["cluster_id"], "implementation cluster"),
        stage_input_sha256=_digest(payload["stage_input_sha256"], "implementation input"),
        reconciliation_receipt_sha256=_digest(
            payload["reconciliation_receipt_sha256"], "implementation reconciliation receipt"
        ),
        disposition_ledger_sha256=_digest(
            payload["disposition_ledger_sha256"], "implementation ledger"
        ),
        implementation_output_sha256=_digest(
            payload["implementation_output_sha256"], "implementation output"
        ),
        accepted=_accepted(payload["accepted"], payload["diagnostics"], "implementation"),
        diagnostics=_diagnostics(payload["diagnostics"], "implementation diagnostics"),
    )


def load_publication_receipt(
    canonical_bytes: bytes, authority: ActivatedStageAuthority
) -> TrustedPublicationReceipt:
    payload, receipt_sha256 = _load_signed(canonical_bytes, authority, "publication")
    _keys(payload, _PUBLICATION_FIELDS, "publication receipt")
    changed = payload["changed"]
    if type(changed) is not bool:
        raise ValueError("publication changed must be a boolean")
    return _new_receipt(
        TrustedPublicationReceipt,
        canonical_bytes,
        receipt_sha256,
        revision=_exact_revision(
            payload["revision"], TRACKER_PUBLICATION_COMPLETION_REVISION, "publication"
        ),
        authority_sha256=_digest(payload["authority_sha256"], "publication authority"),
        graph_sha256=_digest(payload["graph_sha256"], "publication graph"),
        cluster_id=_token(payload["cluster_id"], "publication cluster"),
        stage_input_sha256=_digest(payload["stage_input_sha256"], "publication input"),
        implementation_receipt_sha256=_digest(
            payload["implementation_receipt_sha256"], "publication implementation receipt"
        ),
        queue_generation_sha256=_digest(
            payload["queue_generation_sha256"], "published queue generation"
        ),
        document_set_sha256=_digest(payload["document_set_sha256"], "document set"),
        publication_config_sha256=_digest(
            payload["publication_config_sha256"], "publication config"
        ),
        before_revision=_revision(payload["before_revision"], "before revision"),
        after_revision=_revision(payload["after_revision"], "after revision"),
        paths=_paths(payload["paths"]),
        changed=changed,
        accepted=_accepted(payload["accepted"], payload["diagnostics"], "publication"),
        diagnostics=_diagnostics(payload["diagnostics"], "publication diagnostics"),
    )


def finish_package_audit(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    authority: ActivatedStageAuthority,
    receipt: TrustedPackageAuditReceipt,
) -> StageCompletion:
    graph = validate_cluster_graph(graph)
    receipt = _reauthenticate(
        receipt, TrustedPackageAuditReceipt, authority, load_package_audit_receipt
    )
    _require_graph_authority(graph.audit_capability_pins, authority)
    package = {item.package_ref_id: item for item in graph.packages}.get(receipt.package_ref_id)
    if package is None:
        raise QueueConflictError("package audit receipt belongs to another cluster")
    analysis = completion_pin(queue.snapshot(), package.unit_id)
    if analysis is None or analysis.revision != VALIDATED_PACKAGE_OUTPUT_REVISION:
        raise QueueConflictError("package audit requires accepted package analysis")
    expected_input = stage_input_sha256(
        graph,
        stage="audit",
        subject=receipt.package_ref_id,
        capability_pins=graph.audit_capability_pins,
        dependency_pins=(analysis,),
    )
    if (
        receipt.graph_sha256 != graph.content_id
        or receipt.cluster_id != graph.cluster_id
        or receipt.stage_input_sha256 != expected_input
        or receipt.analysis_completion_revision != analysis.revision
        or receipt.analysis_completion_sha256 != analysis.digest
        or lease.unit_id != package_audit_unit_id(graph, receipt.package_ref_id)
    ):
        raise QueueConflictError("package audit receipt does not bind its stage input")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_PACKAGE_AUDIT_KIND,
        expected_input,
        PACKAGE_AUDIT_COMPLETION_REVISION,
        authority,
        receipt.canonical_bytes,
    )


def finish_cluster_reconciliation(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    authority: ActivatedStageAuthority,
    receipt: TrustedReconciliationReceipt,
) -> StageCompletion:
    graph = validate_cluster_graph(graph)
    receipt = _reauthenticate(
        receipt, TrustedReconciliationReceipt, authority, load_reconciliation_receipt
    )
    _require_graph_authority(graph.reconciliation_capability_pins, authority)
    expected_input = _validate_reconciliation(queue, graph, receipt)
    if lease.unit_id != cluster_reconciliation_unit_id(graph):
        raise QueueConflictError("reconciliation receipt belongs to another stage")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
        expected_input,
        CLUSTER_RECONCILIATION_COMPLETION_REVISION,
        authority,
        receipt.canonical_bytes,
    )


def finish_cluster_implementation(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    reconciliation_authority: ActivatedStageAuthority,
    reconciliation_receipt: TrustedReconciliationReceipt,
    authority: ActivatedStageAuthority,
    receipt: TrustedImplementationReceipt,
) -> StageCompletion:
    graph = validate_cluster_graph(graph)
    reconciliation_receipt = _reauthenticate(
        reconciliation_receipt,
        TrustedReconciliationReceipt,
        reconciliation_authority,
        load_reconciliation_receipt,
    )
    receipt = _reauthenticate(
        receipt, TrustedImplementationReceipt, authority, load_implementation_receipt
    )
    _require_graph_authority(graph.implementation_capability_pins, authority)
    expected_input = _validate_implementation(queue, graph, reconciliation_receipt, receipt)
    if lease.unit_id != cluster_implementation_unit_id(graph):
        raise QueueConflictError("implementation receipt belongs to another stage")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
        expected_input,
        CLUSTER_IMPLEMENTATION_COMPLETION_REVISION,
        authority,
        receipt.canonical_bytes,
    )


def finish_tracker_publication(
    queue: Queue,
    lease: Lease,
    *,
    graph: ClusterGraphPlan,
    reconciliation_authority: ActivatedStageAuthority,
    reconciliation_receipt: TrustedReconciliationReceipt,
    implementation_authority: ActivatedStageAuthority,
    implementation_receipt: TrustedImplementationReceipt,
    authority: ActivatedStageAuthority,
    fanout_receipt: FanoutPublishReceipt,
    receipt: TrustedPublicationReceipt,
) -> StageCompletion:
    """Finish only after the real atomic fanout result is signed and bound."""

    graph = validate_cluster_graph(graph)
    reconciliation_receipt = _reauthenticate(
        reconciliation_receipt,
        TrustedReconciliationReceipt,
        reconciliation_authority,
        load_reconciliation_receipt,
    )
    implementation_receipt = _reauthenticate(
        implementation_receipt,
        TrustedImplementationReceipt,
        implementation_authority,
        load_implementation_receipt,
    )
    receipt = _reauthenticate(
        receipt, TrustedPublicationReceipt, authority, load_publication_receipt
    )
    _require_graph_authority(graph.publication_capability_pins, authority)
    if type(fanout_receipt) is not FanoutPublishReceipt:
        raise QueueConflictError("publication requires the exact production fanout receipt")
    _validate_fanout_event(queue, lease, fanout_receipt)
    _validate_implementation(queue, graph, reconciliation_receipt, implementation_receipt)
    implementation = _required_completion(
        completion_pins(queue.snapshot()),
        cluster_implementation_unit_id(graph),
        "tracker publication",
    )
    expected_input = stage_input_sha256(
        graph,
        stage="publication",
        subject=graph.cluster_id,
        capability_pins=graph.publication_capability_pins,
        dependency_pins=(implementation,),
    )
    fanout_values = (
        fanout_receipt.queue_generation,
        fanout_receipt.document_set_sha256,
        fanout_receipt.publication_config_sha256,
        fanout_receipt.before_revision,
        fanout_receipt.after_revision,
        fanout_receipt.paths,
        fanout_receipt.changed,
    )
    receipt_values = (
        receipt.queue_generation_sha256,
        receipt.document_set_sha256,
        receipt.publication_config_sha256,
        receipt.before_revision,
        receipt.after_revision,
        receipt.paths,
        receipt.changed,
    )
    if (
        implementation.digest != implementation_receipt.receipt_sha256
        or receipt.graph_sha256 != graph.content_id
        or receipt.cluster_id != graph.cluster_id
        or receipt.stage_input_sha256 != expected_input
        or receipt.implementation_receipt_sha256 != implementation_receipt.receipt_sha256
        or receipt_values != fanout_values
        or lease.unit_id != tracker_publication_unit_id(graph)
    ):
        raise QueueConflictError("publication receipt does not bind the production fanout result")
    return _finish(
        queue,
        lease,
        graph,
        ORCHESTRATION_TRACKER_PUBLICATION_KIND,
        expected_input,
        TRACKER_PUBLICATION_COMPLETION_REVISION,
        authority,
        receipt.canonical_bytes,
    )


def _validate_reconciliation(
    queue: Queue, graph: ClusterGraphPlan, receipt: TrustedReconciliationReceipt
) -> str:
    audits = _all_audit_completions(completion_pins(queue.snapshot()), graph)
    dependencies = tuple(sorted(audits, key=lambda item: item.parent_unit_id))
    expected_input = stage_input_sha256(
        graph,
        stage="reconciliation",
        subject=graph.cluster_id,
        capability_pins=graph.reconciliation_capability_pins,
        dependency_pins=dependencies,
    )
    expected_pairs = tuple(
        sorted(
            (package.package_ref_id, audits[index].digest)
            for index, package in enumerate(graph.packages)
        )
    )
    if (
        receipt.graph_sha256 != graph.content_id
        or receipt.cluster_id != graph.cluster_id
        or receipt.stage_input_sha256 != expected_input
        or receipt.package_audit_receipts != expected_pairs
    ):
        raise QueueConflictError("reconciliation receipt does not bind all package audits")
    return expected_input


def _validate_implementation(
    queue: Queue,
    graph: ClusterGraphPlan,
    reconciliation_receipt: TrustedReconciliationReceipt,
    receipt: TrustedImplementationReceipt,
) -> str:
    reconciliation = _required_completion(
        completion_pins(queue.snapshot()),
        cluster_reconciliation_unit_id(graph),
        "implementation receipt",
    )
    if reconciliation.digest != reconciliation_receipt.receipt_sha256:
        raise QueueConflictError("implementation receipt has a different reconciliation")
    _validate_reconciliation(queue, graph, reconciliation_receipt)
    expected_input = stage_input_sha256(
        graph,
        stage="implementation",
        subject=graph.cluster_id,
        capability_pins=graph.implementation_capability_pins,
        dependency_pins=(reconciliation,),
    )
    if (
        receipt.graph_sha256 != graph.content_id
        or receipt.cluster_id != graph.cluster_id
        or receipt.stage_input_sha256 != expected_input
        or receipt.reconciliation_receipt_sha256 != reconciliation_receipt.receipt_sha256
        or receipt.disposition_ledger_sha256 != reconciliation_receipt.disposition_ledger_sha256
    ):
        raise QueueConflictError("implementation receipt does not bind the accepted ledger")
    return expected_input


def _all_audit_completions(
    completions: Mapping[str, CompletionDependencyPin], graph: ClusterGraphPlan
) -> tuple[CompletionDependencyPin, ...]:
    result: list[CompletionDependencyPin] = []
    for package in graph.packages:
        completion = completions.get(package_audit_unit_id(graph, package.package_ref_id))
        if completion is None or completion.revision != PACKAGE_AUDIT_COMPLETION_REVISION:
            raise QueueConflictError("reconciliation requires every accepted package audit")
        result.append(completion)
    return tuple(result)


def _required_completion(
    completions: Mapping[str, CompletionDependencyPin], unit_id: str, stage: str
) -> CompletionDependencyPin:
    completion = completions.get(unit_id)
    if completion is None:
        raise QueueConflictError(f"{stage} requires its accepted parent")
    return completion


def _validate_fanout_event(queue: Queue, lease: Lease, receipt: FanoutPublishReceipt) -> None:
    """Prove the receipt came from the publisher's immutable internal checkpoint."""

    with sqlite3.connect(queue.database) as connection:
        row = connection.execute(
            """
            SELECT event_type, payload_json FROM events
            WHERE attempt_id = ? AND event_type IN (
                'TRACKER_PUBLISHED', 'TRACKER_ALREADY_CURRENT'
            ) ORDER BY event_id DESC LIMIT 1
            """,
            (lease.attempt_id,),
        ).fetchone()
    if row is None:
        raise QueueConflictError("publication has no production fanout checkpoint")
    event_type, encoded = row
    payload = json.loads(encoded, object_pairs_hook=_unique_object)
    expected = {
        "generation": receipt.queue_generation,
        "publication_config_sha256": receipt.publication_config_sha256,
        "targets": list(receipt.paths),
    }
    if receipt.changed:
        expected.update(
            {
                "document_set_sha256": receipt.document_set_sha256,
                "revision": receipt.after_revision,
            }
        )
        expected_type = "TRACKER_PUBLISHED"
    else:
        expected_type = "TRACKER_ALREADY_CURRENT"
    if event_type != expected_type or payload != expected:
        raise QueueConflictError("publication fanout receipt does not match its queue checkpoint")


def _finish(
    queue: Queue,
    lease: Lease,
    graph: ClusterGraphPlan,
    kind: str,
    expected_input: str,
    completion_revision: str,
    authority: ActivatedStageAuthority,
    canonical_receipt: bytes,
) -> StageCompletion:
    del kind, expected_input, completion_revision
    result = queue.finish_authenticated_orchestration_stage(
        lease,
        graph=graph,
        authority=authority,
        canonical_receipt=canonical_receipt,
    )
    restored = _load_signed(canonical_receipt, authority, authority.stage)
    return StageCompletion(restored[1], result)


def _require_graph_authority(
    pins: tuple[CapabilityPin, ...], authority: ActivatedStageAuthority
) -> None:
    if pins != (stage_authority_capability(authority),):
        raise QueueConflictError("graph stage capability does not match protected authority")


def _reauthenticate[
    Receipt: (
        TrustedPackageAuditReceipt,
        TrustedReconciliationReceipt,
        TrustedImplementationReceipt,
        TrustedPublicationReceipt,
    )
](
    receipt: Receipt,
    expected_type: type[Receipt],
    authority: ActivatedStageAuthority,
    loader: Callable[[bytes, ActivatedStageAuthority], Receipt],
) -> Receipt:
    if type(receipt) is not expected_type or type(authority) is not ActivatedStageAuthority:
        raise QueueConflictError("stage completion requires exact authenticated types")
    restored = loader(receipt.canonical_bytes, authority)
    if restored != receipt:
        raise QueueConflictError(
            "stage receipt fields do not match their signed canonical preimage"
        )
    return restored


def _load_signed(
    canonical_bytes: bytes, authority: ActivatedStageAuthority, stage: str
) -> tuple[dict[str, object], str]:
    if type(authority) is not ActivatedStageAuthority:
        raise QueueConflictError("stage receipt requires an exact activated authority")
    restored = _revalidate_authority(authority)
    if restored != authority:
        raise QueueConflictError("stage authority fields do not match their activation preimage")
    if restored.stage != stage:
        raise QueueConflictError("stage authority was activated for another stage")
    document = _canonical_document(canonical_bytes, f"{stage} receipt")
    _keys(document, {"payload", "signature"}, f"{stage} receipt envelope")
    payload = document["payload"]
    if type(payload) is not dict:
        raise ValueError(f"{stage} receipt payload must be an object")
    if payload.get("stage") != stage:
        raise QueueConflictError("signed receipt belongs to another stage")
    if payload.get("authority_sha256") != authority.authority_sha256:
        raise QueueConflictError("signed receipt belongs to another authority")
    signature = document["signature"]
    if type(signature) is not str or _SIGNATURE.fullmatch(signature) is None:
        raise ValueError("stage receipt signature must be a lowercase Ed25519 signature")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority.public_key)).verify(
            bytes.fromhex(signature), _signing_bytes(stage, payload)
        )
    except InvalidSignature as error:
        raise QueueConflictError("stage receipt signature is invalid") from error
    return payload, _receipt_sha256(stage, canonical_bytes)


def _revalidate_authority(authority: ActivatedStageAuthority) -> ActivatedStageAuthority:
    if type(authority) is not ActivatedStageAuthority:
        raise QueueConflictError("stage receipt requires an exact activated authority")
    return load_stage_authority(authority.canonical_bytes)


def _load_stage_authority_config() -> dict[str, tuple[str, int]]:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        directory = os.open("/etc/ha-adjustable-bed", directory_flags)
    except OSError as error:
        raise QueueConflictError("protected stage authority config is unavailable") from error
    try:
        _validate_protected_directory(os.fstat(directory))
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open("phase4-v2-stage-authorities.json", flags, dir_fd=directory)
        except OSError as error:
            raise QueueConflictError("protected stage authority config is unavailable") from error
        try:
            _validate_protected_file(os.fstat(descriptor))
            chunks: list[bytes] = []
            remaining = 16 * 1024 + 1
            while remaining:
                chunk = os.read(descriptor, min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
    raw = b"".join(chunks)
    document = _canonical_document(raw, "protected stage authority config")
    _keys(document, set(_STAGES), "protected stage authority config")
    result: dict[str, tuple[str, int]] = {}
    for stage in sorted(_STAGES):
        entry = document[stage]
        if type(entry) is not dict:
            raise ValueError("protected stage authority entry must be an object")
        _keys(entry, {"authority_sha256", "generation"}, "protected stage authority entry")
        generation = entry["generation"]
        if type(generation) is not int or generation < 1:
            raise ValueError("protected stage authority generation must be positive")
        result[stage] = (_digest(entry["authority_sha256"], "protected authority"), generation)
    return result


def _validate_protected_directory(metadata: os.stat_result) -> None:
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
        raise QueueConflictError("protected stage authority parent is unsafe")


def _validate_protected_file(metadata: os.stat_result) -> None:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
        raise QueueConflictError("protected stage authority config is unsafe")


def _new_receipt[
    Receipt: (
        TrustedPackageAuditReceipt,
        TrustedReconciliationReceipt,
        TrustedImplementationReceipt,
        TrustedPublicationReceipt,
    )
](
    receipt_type: type[Receipt], canonical_bytes: bytes, receipt_sha256: str, **values: object
) -> Receipt:
    result = object.__new__(receipt_type)
    for field, value in (
        *values.items(),
        ("canonical_bytes", canonical_bytes),
        ("receipt_sha256", receipt_sha256),
    ):
        object.__setattr__(result, field, value)
    return result


def _canonical_document(value: object, label: str) -> dict[str, object]:
    if type(value) is not bytes or not value or len(value) > _MAX_DOCUMENT_BYTES:
        raise ValueError(f"{label} must be bounded exact bytes")
    try:
        decoded = json.loads(value, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError(f"{label} is not valid canonical JSON") from error
    if type(decoded) is not dict or _canonical_bytes(decoded) != value:
        raise ValueError(f"{label} is not an exact canonical preimage")
    return decoded


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _keys(value: dict[str, object], expected: frozenset[str] | set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are not exact")


def _signing_bytes(stage: str, payload: object) -> bytes:
    return f"phase4-v2:signed-stage-receipt:{stage}".encode() + b"\0" + _canonical_bytes(payload)


def _authority_sha256(canonical_bytes: bytes) -> str:
    return hashlib.sha256(b"phase4-v2:stage-authority\0" + canonical_bytes).hexdigest()


def _receipt_sha256(stage: str, canonical_bytes: bytes) -> str:
    return hashlib.sha256(
        f"phase4-v2:signed-stage-receipt:{stage}".encode() + b"\0" + canonical_bytes
    ).hexdigest()


def _accepted(value: object, diagnostics: object, label: str) -> bool:
    items = _diagnostics(diagnostics, f"{label} diagnostics")
    if value is not True or items:
        raise QueueConflictError(f"{label} receipt is not an accepted zero-diagnostic result")
    return True


def _diagnostics(value: object, label: str) -> tuple[str, ...]:
    if (
        type(value) is not list
        or len(value) > _MAX_DIAGNOSTICS
        or any(type(item) is not str for item in value)
    ):
        raise ValueError(f"{label} must be a JSON array")
    items = tuple(value)
    for item in items:
        _token(item, label)
    if items != tuple(sorted(set(items))):
        raise ValueError(f"{label} must be sorted and unique")
    return items


def _pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
    if (
        type(value) is not list
        or len(value) > _MAX_PACKAGES
        or any(
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            for item in value
        )
    ):
        raise ValueError(f"{label} must be an exact JSON pair array")
    pairs = tuple((item[0], item[1]) for item in value)
    for package_ref_id, digest in pairs:
        _digest(package_ref_id, label)
        _digest(digest, label)
    if pairs != tuple(sorted(set(pairs))) or len({item[0] for item in pairs}) != len(pairs):
        raise ValueError(f"{label} must be sorted and unique")
    return pairs


def _paths(value: object) -> tuple[str, ...]:
    if type(value) is not list or not value or any(type(item) is not str for item in value):
        raise ValueError("publication paths must be a non-empty JSON array")
    paths = tuple(value)
    if paths != tuple(sorted(set(paths))):
        raise ValueError("publication paths must be sorted and unique")
    return paths


def _exact_revision(value: object, expected: str, label: str) -> str:
    if value != expected:
        raise QueueConflictError(f"{label} receipt revision is unsupported")
    return expected


def _stage(value: object) -> str:
    if type(value) is not str or value not in _STAGES:
        raise ValueError("stage must name one supported semantic stage")
    return value


def _revision(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value) > 200 or "\0" in value:
        raise ValueError(f"{label} must be a bounded revision")
    return value


def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _token(value: object, label: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical token")
    return value


_AUDIT_FIELDS = frozenset(
    {
        "accepted",
        "analysis_completion_revision",
        "analysis_completion_sha256",
        "authority_sha256",
        "cluster_id",
        "diagnostics",
        "graph_sha256",
        "package_ref_id",
        "package_surface_sha256",
        "revision",
        "stage",
        "stage_input_sha256",
    }
)
_RECONCILIATION_FIELDS = frozenset(
    {
        "accepted",
        "authority_sha256",
        "cluster_id",
        "completeness_receipt_sha256",
        "diagnostics",
        "disposition_ledger_sha256",
        "graph_sha256",
        "package_audit_receipts",
        "reconciliation_result_sha256",
        "revision",
        "stage",
        "stage_input_sha256",
    }
)
_IMPLEMENTATION_FIELDS = frozenset(
    {
        "accepted",
        "authority_sha256",
        "cluster_id",
        "diagnostics",
        "disposition_ledger_sha256",
        "graph_sha256",
        "implementation_output_sha256",
        "reconciliation_receipt_sha256",
        "revision",
        "stage",
        "stage_input_sha256",
    }
)
_PUBLICATION_FIELDS = frozenset(
    {
        "accepted",
        "after_revision",
        "authority_sha256",
        "before_revision",
        "changed",
        "cluster_id",
        "diagnostics",
        "document_set_sha256",
        "graph_sha256",
        "implementation_receipt_sha256",
        "paths",
        "publication_config_sha256",
        "queue_generation_sha256",
        "revision",
        "stage",
        "stage_input_sha256",
    }
)
