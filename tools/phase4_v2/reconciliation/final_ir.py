"""Deterministic reconciliation surfaces derived from the final protocol IR."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast

from tools.phase4_v2.equivalence import (
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    AuthenticatedPackageExecutionEnvelope,
    FrozenPackageExecutionPlan,
    FrozenPackageRef,
    Route,
    ValidatedPackageOutput,
    package_queue_unit_id,
    validate_authenticated_package_output,
    validate_frozen_package_ref,
)
from tools.phase4_v2.ir import (
    FINAL_DOMAIN_COLLECTIONS,
    FINAL_SCHEMA_REVISION,
    FinalProtocolIRDocument,
    SelectorKind,
    dumps_final_ir,
    validate_final_ir_markdown,
    validate_final_universe,
)
from tools.phase4_v2.ir import model as ir_core
from tools.phase4_v2.ir import v1 as final_ir_model
from tools.phase4_v2.queue import Queue, WorkUnitStatus

from .model import (
    AreaSurface,
    CanonicalValue,
    ClaimPolarity,
    ClosureStatus,
    ComparisonArea,
    DispositionKind,
    DispositionStatus,
    LeafProvenance,
    LedgerDisposition,
    NormalizedClaim,
    PackageSurface,
    ReconciliationError,
    RootProvenance,
)

_COLLECTION_AREAS = {
    "variant_spaces": ComparisonArea.MODELS_VARIANTS,
    "protocols": ComparisonArea.MODELS_VARIANTS,
    "actions": ComparisonArea.ACTIONS,
    "expected_action_rules": ComparisonArea.ACTIONS,
    "selectors": ComparisonArea.MODELS_VARIANTS,
    "selection_rules": ComparisonArea.DISCOVERY,
    "discovery_rules": ComparisonArea.DISCOVERY,
    "gatt_services": ComparisonArea.GATT,
    "gatt_characteristics": ComparisonArea.GATT,
    "transforms": ComparisonArea.PACKET_CONSTRUCTION,
    "checksums": ComparisonArea.PACKET_CONSTRUCTION,
    "framings": ComparisonArea.PACKET_CONSTRUCTION,
    "packet_fields": ComparisonArea.PACKET_CONSTRUCTION,
    "packet_builders": ComparisonArea.PACKET_CONSTRUCTION,
    "authentications": ComparisonArea.AUTHENTICATION,
    "bufferings": ComparisonArea.PARSING,
    "parser_fields": ComparisonArea.PARSING,
    "notification_parsers": ComparisonArea.PARSING,
    "timings": ComparisonArea.TIMING_STOP_RELEASE,
    "lifecycles": ComparisonArea.LIFECYCLE,
    "transports": ComparisonArea.TRANSPORT,
    "action_parameters": ComparisonArea.ACTIONS,
    "action_mappings": ComparisonArea.ACTIONS,
}
_SELECTOR_AREAS = {
    SelectorKind.CAPABILITY: ComparisonArea.CAPABILITIES_CONFIGURATION,
    SelectorKind.CONFIGURATION: ComparisonArea.CAPABILITIES_CONFIGURATION,
}


@dataclass(frozen=True, slots=True)
class FinalIRSurfaceDerivation:
    """One immutable surface and its independently reproduced exact-set universes."""

    package_surface: PackageSurface
    final_ir_json_sha256: str
    final_ir_markdown_sha256: str
    candidate_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    variant_ids: tuple[str, ...]


def derive_authenticated_final_ir_package_surface(
    *,
    package_ref: FrozenPackageRef,
    execution_plan: FrozenPackageExecutionPlan,
    queue: Queue,
    validated_output: ValidatedPackageOutput,
    execution_envelope: AuthenticatedPackageExecutionEnvelope,
    report_bytes: bytes,
    report_manifest_bytes: bytes,
    document: FinalProtocolIRDocument,
    canonical_json: bytes,
    markdown: str,
) -> FinalIRSurfaceDerivation:
    """Derive a surface only from an accepted, signed package publication."""

    package_ref = validate_frozen_package_ref(package_ref)
    authenticated = validate_authenticated_package_output(validated_output, execution_envelope)
    if type(authenticated) is not ValidatedPackageOutput:
        raise ReconciliationError("authenticated package output has an invalid type")
    completion = next(
        (
            item
            for item in queue.snapshot().units
            if item.unit_id == package_queue_unit_id(package_ref.content_id)
        ),
        None,
    )
    if (
        execution_plan.target_package_ref_id != package_ref.content_id
        or execution_plan.digest != authenticated.execution_plan_id
        or completion is None
        or completion.status is not WorkUnitStatus.COMPLETED
        or completion.completion_revision != VALIDATED_PACKAGE_OUTPUT_REVISION
        or completion.output_digest != authenticated.content_id
    ):
        raise ReconciliationError("package completion does not bind the authenticated output")
    if type(report_bytes) is not bytes:
        raise ReconciliationError("report must be exact immutable bytes")
    try:
        report = json.loads(report_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReconciliationError("package report is invalid JSON") from error
    canonical_report = json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if report_bytes not in {canonical_report, canonical_report + b"\n"}:
        raise ReconciliationError("package report is not canonical JSON")
    try:
        receipt = json.loads(execution_envelope.receipt_bytes)
        manifest_sha256 = receipt["report_manifest_sha256"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ReconciliationError("signed receipt has no report manifest authority") from error
    if hashlib.sha256(report_manifest_bytes).hexdigest() != manifest_sha256:
        raise ReconciliationError("report manifest differs from the signed receipt")
    analysis_entry = f"{hashlib.sha256(report_bytes).hexdigest()}  analysis.json"
    if analysis_entry not in report_manifest_bytes.decode("utf-8", errors="strict").splitlines():
        raise ReconciliationError("analysis report is absent from the signed report manifest")
    results = report.get("authoritative_root_results") if type(report) is dict else None
    if type(results) is not list:
        raise ReconciliationError("package report has no authoritative root results")
    result_locations = {
        (item.get("target_root_id"), item.get("target_occurrence_identity_sha256")): index
        for index, item in enumerate(results)
        if type(item) is dict and item.get("route") == Route.FULL_ANALYSIS.value
    }
    report_roots = {
        (
            item.get("target_root_id"),
            item.get("target_occurrence_identity_sha256"),
            item.get("result", {}).get("analysis", {}).get("semantic_root_sha256"),
        )
        for item in results
        if type(item) is dict and item.get("route") == Route.FULL_ANALYSIS.value
    }
    attested_roots = {
        (
            item.target_root_id,
            item.target_occurrence_identity_sha256,
            item.semantic_root_sha256,
        )
        for item in authenticated.validated_root_evidence
    }
    if report_roots != attested_roots:
        raise ReconciliationError("report roots differ from retained validator attestations")
    anchor_keys_by_id = {anchor.id: key for key, anchor in document.evidence_anchors}
    retained_anchor_ids = {
        anchor
        for attestation in authenticated.validated_root_evidence
        for member in attestation.evidence_members
        for anchor in member.evidence_anchor_ids
    }
    if not retained_anchor_ids <= set(anchor_keys_by_id):
        raise ReconciliationError("retained root evidence names anchors outside the final IR")
    roots = tuple(
        RootProvenance(
            package_ref.content_id,
            attestation.target_root_id,
            attestation.target_occurrence_identity_sha256,
            Route.FULL_ANALYSIS,
            attestation.semantic_root_sha256,
            None,
            f"/authoritative_root_results/{result_locations[(attestation.target_root_id, attestation.target_occurrence_identity_sha256)]}",
            tuple(
                sorted(
                    anchor_keys_by_id[anchor]
                    for member in attestation.evidence_members
                    for anchor in member.evidence_anchor_ids
                )
            ),
        )
        for attestation in authenticated.validated_root_evidence
    )
    if len(roots) != len(result_locations):
        raise ReconciliationError("retained root attestations do not match the exact report roots")
    return derive_final_ir_package_surface(
        package_ref=package_ref,
        report_sha256=authenticated.target_report_sha256,
        report_revision=authenticated.target_report_revision,
        roots=tuple(sorted(roots, key=lambda item: item.content_id)),
        document=document,
        canonical_json=canonical_json,
        markdown=markdown,
    )


def derive_final_ir_package_surface(
    *,
    package_ref: FrozenPackageRef,
    report_sha256: str,
    report_revision: str,
    roots: tuple[RootProvenance, ...],
    document: FinalProtocolIRDocument,
    canonical_json: bytes,
    markdown: str,
) -> FinalIRSurfaceDerivation:
    """Reproduce one complete package surface solely from canonical final-IR semantics."""

    if type(document) is not FinalProtocolIRDocument:
        raise ReconciliationError("final IR must use the exact FinalProtocolIRDocument type")
    if document.schema_revision != FINAL_SCHEMA_REVISION:
        raise ReconciliationError("final IR schema revision is not terminal")
    if type(canonical_json) is not bytes or dumps_final_ir(document) != canonical_json:
        raise ReconciliationError("final IR JSON is not the exact canonical document")
    try:
        raw = json.loads(canonical_json)
        reproduced = final_ir_model._parse_final_ir_structure(raw)
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise ReconciliationError("final IR JSON cannot be independently reproduced") from error
    if reproduced != document:
        raise ReconciliationError("final IR object differs from its canonical JSON")
    validate_final_ir_markdown(reproduced, markdown)
    universe = validate_final_universe(reproduced)
    if not universe.is_valid:
        raise ReconciliationError("final IR action universe is not closed")
    if type(roots) is not tuple or not roots:
        raise ReconciliationError("final IR surface requires a non-empty exact root set")
    for root in roots:
        if type(root) is not RootProvenance:
            raise ReconciliationError("final IR roots must use exact RootProvenance records")
        root.__post_init__()
        if root.package_ref_id != package_ref.content_id or root.blockers:
            raise ReconciliationError("final IR roots are not complete for the target package")

    semantic = ir_core._semantic_data(cast(ir_core.ProtocolIRDocument, reproduced))
    leaf_pointers = tuple(sorted(ir_core._semantic_leaf_pointers(semantic)))
    provenance_by_pointer = _leaf_provenance(reproduced, roots, leaf_pointers)
    claims_by_area: dict[ComparisonArea, list[NormalizedClaim]] = {
        area: [] for area in ComparisonArea
    }
    for pointer in leaf_pointers:
        area = _area_for_pointer(reproduced, pointer)
        claims_by_area[area].append(
            NormalizedClaim(
                pointer,
                ClaimPolarity.AFFIRMED,
                CanonicalValue.from_data(ir_core._resolve_semantic_pointer(semantic, pointer)),
                provenance_by_pointer[pointer],
            )
        )

    candidates = _candidate_universe(reproduced)
    actions = tuple(
        sorted((_universe_id("action", _action_key_data(key)), key) for key in universe.expected)
    )
    variants = _variant_universe(reproduced)
    dispositions_by_area: dict[ComparisonArea, list[LedgerDisposition]] = {
        area: [] for area in ComparisonArea
    }
    for candidate_id, area, pointer in candidates:
        dispositions_by_area[area].append(
            _covered_disposition(
                DispositionKind.CANDIDATE,
                candidate_id,
                _claims_under(claims_by_area[area], pointer),
            )
        )
    for action_id, action_key in actions:
        dispositions_by_area[ComparisonArea.ACTIONS].append(
            _covered_disposition(
                DispositionKind.ACTION,
                action_id,
                _claims_under(
                    claims_by_area[ComparisonArea.ACTIONS],
                    f"/actions/{action_key.action}",
                ),
            )
        )
    for variant_id, protocol_id in variants:
        dispositions_by_area[ComparisonArea.MODELS_VARIANTS].append(
            _covered_disposition(
                DispositionKind.VARIANT,
                variant_id,
                _claims_under(
                    claims_by_area[ComparisonArea.MODELS_VARIANTS],
                    f"/protocols/{protocol_id}",
                ),
            )
        )

    areas = tuple(
        AreaSurface(
            area,
            ClosureStatus.COMPLETE,
            tuple(sorted(claims_by_area[area], key=lambda item: item.sort_key)),
            tuple(sorted(dispositions_by_area[area], key=lambda item: item.sort_key)),
        )
        for area in sorted(ComparisonArea, key=lambda item: item.value)
    )
    surface = PackageSurface(
        package_ref,
        report_sha256,
        report_revision,
        roots,
        areas,
    )
    return FinalIRSurfaceDerivation(
        surface,
        hashlib.sha256(canonical_json).hexdigest(),
        hashlib.sha256(markdown.encode("utf-8", errors="strict")).hexdigest(),
        tuple(item[0] for item in candidates),
        tuple(item[0] for item in actions),
        tuple(item[0] for item in variants),
    )


def _leaf_provenance(
    document: FinalProtocolIRDocument,
    roots: tuple[RootProvenance, ...],
    pointers: tuple[str, ...],
) -> dict[str, tuple[LeafProvenance, ...]]:
    bindings: dict[str, ir_core.EvidenceBinding] = {}
    for _binding_id, binding in document.evidence_bindings:
        if binding.target in bindings:
            raise ReconciliationError("final IR contains duplicate semantic evidence bindings")
        bindings[binding.target] = binding
    source_sets = dict(document.source_sets)
    declared_anchors = set(dict(document.evidence_anchors))
    roots_by_anchor: dict[str, list[RootProvenance]] = {}
    for root in roots:
        for anchor in root.evidence_anchor_ids:
            roots_by_anchor.setdefault(anchor, []).append(root)
    if set(roots_by_anchor) != declared_anchors or any(
        len(owners) != 1 for owners in roots_by_anchor.values()
    ):
        raise ReconciliationError("root provenance does not exactly partition final IR anchors")

    result: dict[str, tuple[LeafProvenance, ...]] = {}
    used_anchors: set[str] = set()
    for pointer in pointers:
        binding = bindings.get(pointer)
        if binding is None:
            raise ReconciliationError(f"final IR leaf has no evidence binding: {pointer}")
        grouped: dict[str, set[str]] = {}
        for source_set_id in binding.source_sets:
            source_set = source_sets[source_set_id]
            for anchor in source_set.anchors:
                owners = roots_by_anchor.get(anchor, ())
                if len(owners) != 1:
                    raise ReconciliationError("final IR anchor has ambiguous root provenance")
                grouped.setdefault(owners[0].content_id, set()).add(anchor)
                used_anchors.add(anchor)
        result[pointer] = tuple(
            sorted(
                (
                    LeafProvenance(root_id, pointer, tuple(sorted(anchor_ids)))
                    for root_id, anchor_ids in grouped.items()
                ),
                key=lambda item: item.sort_key,
            )
        )
        if not result[pointer]:
            raise ReconciliationError("final IR leaf evidence has no root provenance")
    if used_anchors != declared_anchors:
        raise ReconciliationError("final IR contains anchors outside semantic leaf provenance")
    return result


def _area_for_pointer(document: FinalProtocolIRDocument, pointer: str) -> ComparisonArea:
    parts = pointer.split("/")
    collection = parts[1] if len(parts) > 1 else ""
    if collection == "selectors" and len(parts) > 2:
        selector = dict(document.selectors).get(parts[2])
        if selector is not None:
            return _SELECTOR_AREAS.get(selector.kind, ComparisonArea.MODELS_VARIANTS)
    if collection == "domain_closure" and len(parts) > 3 and parts[2] == "domains":
        try:
            domain = document.domain_closure.domains[int(parts[3])]
        except (IndexError, ValueError) as error:
            raise ReconciliationError("final IR domain-closure pointer is invalid") from error
        return _COLLECTION_AREAS[domain]
    if collection == "domain_closure":
        return ComparisonArea.MODELS_VARIANTS
    try:
        return _COLLECTION_AREAS[collection]
    except KeyError as error:
        raise ReconciliationError(
            f"final IR leaf is outside the closed surface: {pointer}"
        ) from error


def _candidate_universe(
    document: FinalProtocolIRDocument,
) -> tuple[tuple[str, ComparisonArea, str], ...]:
    values: list[tuple[str, ComparisonArea, str]] = []
    for collection in FINAL_DOMAIN_COLLECTIONS:
        definitions = cast(tuple[tuple[str, object], ...], getattr(document, collection))
        for identifier, definition in definitions:
            values.append(
                (
                    _universe_id(
                        "candidate",
                        {
                            "collection": collection,
                            "definition": cast(ir_core._DataDefinition, definition).to_data(),
                            "identifier": identifier,
                        },
                    ),
                    _area_for_pointer(document, f"/{collection}/{identifier}"),
                    f"/{collection}/{identifier}",
                )
            )
    values.sort()
    return tuple(values)


def _variant_universe(document: FinalProtocolIRDocument) -> tuple[tuple[str, str], ...]:
    spaces = dict(document.variant_spaces)
    values = (
        (
            _universe_id(
                "variant",
                {"profile": dict(profile), "protocol": protocol_id},
            ),
            protocol_id,
        )
        for protocol_id, protocol in document.protocols
        for profile in spaces[protocol.variant_space].iter_profiles()
    )
    return tuple(sorted(values))


def _claims_under(claims: list[NormalizedClaim], pointer: str) -> list[NormalizedClaim]:
    matching = [
        claim for claim in claims if claim.key == pointer or claim.key.startswith(f"{pointer}/")
    ]
    if not matching:
        raise ReconciliationError(f"final IR definition has no semantic claims: {pointer}")
    # The complete leaf set remains in the area. One definition-local claim is a
    # bounded, deterministic ledger witness for the independently derived ID.
    return matching[:1]


def _action_key_data(key: object) -> dict[str, object]:
    typed = cast(final_ir_model.FinalUniverseKey, key)
    return {
        "action": typed.action,
        "parameters": dict(typed.parameters),
        "protocol": typed.protocol,
        "selectors": dict(typed.selectors),
    }


def _universe_id(kind: str, value: object) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", errors="strict")
    return f"{kind}:{hashlib.sha256(kind.encode('ascii') + b'\0' + payload).hexdigest()}"


def _covered_disposition(
    kind: DispositionKind,
    item_id: str,
    claims: list[NormalizedClaim],
) -> LedgerDisposition:
    if not claims:
        raise ReconciliationError(f"final IR {kind.value} universe has no semantic claims")
    provenance = tuple(
        sorted(
            {item.sort_key: item for claim in claims for item in claim.provenance}.values(),
            key=lambda item: item.sort_key,
        )
    )
    return LedgerDisposition(
        kind,
        item_id,
        DispositionStatus.COVERED,
        "final-ir-derived",
        tuple(sorted({claim.key for claim in claims})),
        provenance,
    )
