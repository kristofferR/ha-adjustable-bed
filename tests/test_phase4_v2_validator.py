"""Mutation tests for the Phase 4 v2 filesystem-integrity validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import tools.phase4_v2.validator.__main__ as validator_main
import tools.phase4_v2.validator.binding as validator_binding
import tools.phase4_v2.validator.bundle as validator_bundle
from tests.test_phase4_v2_ir_v1 import _authorized_document, _document
from tools.phase4_v2.equivalence import (
    FINAL_IR_SCHEMA_SHA256,
    PACKAGE_REPORT_REVISION,
    PACKAGE_REPORT_SCHEMA_REVISION,
)
from tools.phase4_v2.ir import (
    FINAL_SCHEMA_REVISION,
    SCHEMA_REVISION,
    bind_validator_receipt,
    final_schema_document,
    loads_final_ir,
    render_final_ir_markdown,
    schema_document,
)
from tools.phase4_v2.ir.model import _resolve_json_pointer
from tools.phase4_v2.validator import (
    BOUND_VALIDATION_PROFILE,
    CONTRACT_REVISION,
    LINEAGE_SCHEMA_REVISION,
    PACKAGE_BOUND_VALIDATION_PROFILE,
    PACKAGE_CONTRACT_REVISION,
    DependencyPins,
    EvidenceLineageTrust,
    PackageDependencyPins,
    TrustedProducer,
    load_json_strict,
    validate_report_bundle,
)
from tools.phase4_v2.validator.binding import PACKAGE_LOCAL_DOMAIN_RESULT_SCHEMA

_EVIDENCE = f"{SCHEMA_REVISION}\n{SCHEMA_REVISION}\n".encode()
_EVIDENCE_DIGEST = hashlib.sha256(_EVIDENCE).hexdigest()
_EVIDENCE_MEMBER = f"evidence/sha256/{_EVIDENCE_DIGEST}"
_PACKAGE_DOMAINS = (
    "configuration",
    "lifecycle",
    "negative_closure",
    "reachability",
    "resources",
    "selectors",
)
_LINEAGE_TOOL_SHA256 = "7" * 64
_LINEAGE_PRODUCER = TrustedProducer("phase4-extract-v1", "apktool", _LINEAGE_TOOL_SHA256)


def _write_manifest(report: Path, members: dict[str, bytes]) -> None:
    lines = [
        f"{hashlib.sha256(data).hexdigest()}  {path}\n" for path, data in sorted(members.items())
    ]
    (report / "REPORT.SHA256").write_text("".join(lines), encoding="utf-8")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _preflight_digest(domain: str, items: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode())
    digest.update(b"\0")
    digest.update(_json_bytes(items))
    return digest.hexdigest()


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


def _complete_analysis_report(
    *,
    artifact_digest: str = "0" * 64,
    package_id: str = "example.package",
    version_code: str = "123",
    version_name: str = "1.2.3",
) -> dict[str, object]:
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
            "package_id": package_id,
            "version_name": version_name,
            "version_code": version_code,
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
            {
                "stack": "android",
                "present": True,
                "coverage": "COMPLETE",
                "evidence": ["synthetic"],
            }
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


def _valid_bundle(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    report = tmp_path / "report"
    scripts = report / "reproducers"
    scripts.mkdir(parents=True)
    members = {
        "ANALYSIS.md": b"Synthetic validation fixture.\n",
        "SEARCH_LOG.md": b"Synthetic validation fixture.\n",
        "analysis.json": _json_bytes(_complete_analysis_report()),
        "reproducers/vector.py": b"# Stored evidence only. The validator never executes this.\n",
    }
    for relative, data in members.items():
        destination = report / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    _write_manifest(report, members)
    return report, members


def _write_contract(
    report: Path,
    members: dict[str, bytes],
    contract: dict[str, object],
) -> None:
    encoded = (json.dumps(contract, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (report / "validation-input.json").write_bytes(encoded)
    members["validation-input.json"] = encoded
    _write_manifest(report, members)


def _bound_bundle(
    tmp_path: Path,
) -> tuple[Path, dict[str, bytes], DependencyPins, dict[str, object]]:
    report, members = _valid_bundle(tmp_path)
    evidence = _EVIDENCE
    delivery_files: list[dict[str, object]] = [
        {"name": "delivery.apk", "size": 1, "sha256": "e" * 64}
    ]
    artifact_members: list[dict[str, object]] = [
        {"name": "base.apk", "size": 1, "sha256": "f" * 64}
    ]
    artifact_digest = _preflight_digest("artifact", artifact_members)
    inputs = {
        "inputs/corpus.json": b'{"kind":"synthetic-corpus"}\n',
        "inputs/ir.json": _json_bytes(_empty_current_ir()),
        "inputs/preflight.json": _json_bytes(
            {
                "schema": "phase4-v2-preflight-v3",
                "delivery_digest": _preflight_digest("delivery", delivery_files),
                "artifact_digest": artifact_digest,
                "delivery_files": delivery_files,
                "artifact_members": artifact_members,
                "package_identity": {
                    "package_name": "example.package",
                    "version_code": "123",
                    "version_name": "1.2.3",
                    "signer_sha256": ["9" * 64],
                    "base_member": "base.apk",
                    "split_members": [],
                },
                "classification": {
                    "stacks": ["android"],
                    "routes": ["apktool"],
                    "status": "READY",
                    "blockers": [],
                    "members": [
                        {
                            "name": "base.apk",
                            "stacks": ["android"],
                            "routes": ["apktool"],
                            "status": "READY",
                            "blockers": [],
                        }
                    ],
                },
            }
        ),
        "inputs/schema.json": _json_bytes(schema_document()),
        _EVIDENCE_MEMBER: evidence,
    }
    members["analysis.json"] = _json_bytes(
        _complete_analysis_report(
            artifact_digest=artifact_digest,
            package_id="example.package",
            version_code="123",
            version_name="1.2.3",
        )
    )
    (report / "analysis.json").write_bytes(members["analysis.json"])
    for relative, data in inputs.items():
        destination = report / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        members[relative] = data
    digests = {path: hashlib.sha256(data).hexdigest() for path, data in inputs.items()}
    pins = DependencyPins(
        preflight_sha256=digests["inputs/preflight.json"],
        ir_sha256=digests["inputs/ir.json"],
        schema_sha256=digests["inputs/schema.json"],
        corpus_sha256=digests["inputs/corpus.json"],
    )
    contract: dict[str, object] = {
        "contract_revision": CONTRACT_REVISION,
        "dependencies": {
            name: {
                "member": f"inputs/{name}.json",
                "sha256": digest,
            }
            for name, digest in pins.as_pairs()
        },
        "evidence_members": [
            {
                "member": _EVIDENCE_MEMBER,
                "owner": artifact_digest,
                "sha256": digests[_EVIDENCE_MEMBER],
            }
        ],
        "anchors": [
            {
                "id": "label",
                "owner": artifact_digest,
                "member": _EVIDENCE_MEMBER,
                "start_byte": 0,
                "end_byte": len(SCHEMA_REVISION),
                "ir_pointer": "/schema_revision",
                "representation": "utf8",
            },
            {
                "id": "value",
                "owner": artifact_digest,
                "member": _EVIDENCE_MEMBER,
                "start_byte": len(SCHEMA_REVISION) + 1,
                "end_byte": 2 * len(SCHEMA_REVISION) + 1,
                "ir_pointer": "/schema_revision",
                "representation": "utf8",
            },
        ],
    }
    _write_contract(report, members, contract)
    return report, members, pins, contract


def _package_bound_bundle(
    tmp_path: Path,
) -> tuple[Path, dict[str, bytes], PackageDependencyPins, dict[str, object]]:
    report, members, pins, contract = _bound_bundle(tmp_path)
    package_domains = _PACKAGE_DOMAINS
    preflight = json.loads(members["inputs/preflight.json"])
    evidence_members = contract["evidence_members"]
    assert isinstance(evidence_members, list)
    evidence_members[0]["package_local_domains"] = list(package_domains)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    for anchor in anchors:
        assert isinstance(anchor, dict)
        anchor["ir_pointer"] = "/actions/raise/summary"
    final_data = _document()
    actions = final_data["actions"]
    assert isinstance(actions, dict)
    raise_action = actions["raise"]
    assert isinstance(raise_action, dict)
    raise_action["summary"] = SCHEMA_REVISION
    final_data, trusted = _authorized_document(final_data)
    final_json = _json_bytes(final_data)
    final_document = loads_final_ir(final_json, trusted_receipts=trusted)
    final_markdown = render_final_ir_markdown(final_document).encode()
    members["inputs/ir.json"] = final_json
    members["inputs/schema.json"] = _json_bytes(final_schema_document())
    members["ANALYSIS.md"] = final_markdown
    for relative in ("inputs/ir.json", "inputs/schema.json", "ANALYSIS.md"):
        (report / relative).write_bytes(members[relative])
    members["analysis.json"] = _json_bytes(
        {
            "authoritative_root_results": [],
            "package_local_domains": {
                name: {
                    "evidence": [_EVIDENCE_MEMBER],
                    "status": "COMPLETE",
                }
                for name in package_domains
            },
            "final_ir_json_sha256": hashlib.sha256(final_json).hexdigest(),
            "final_ir_markdown_sha256": hashlib.sha256(final_markdown).hexdigest(),
            "final_ir_schema_revision": FINAL_SCHEMA_REVISION,
            "report_revision": PACKAGE_REPORT_REVISION,
            "target_package_identity": {
                "artifact_digest": preflight["artifact_digest"],
                "package_name": preflight["package_identity"]["package_name"],
                "version_code": preflight["package_identity"]["version_code"],
                "version_name": preflight["package_identity"]["version_name"],
            },
        }
    )
    (report / "analysis.json").write_bytes(members["analysis.json"])
    package_inputs = {
        "inputs/execution_plan.json": _json_bytes(
            {
                "authoritative_root_count": 0,
                "package_local": {
                    "mandatory_domains": list(package_domains),
                    "package_name": preflight["package_identity"]["package_name"],
                    "target_artifact_digest": preflight["artifact_digest"],
                    "version_code": preflight["package_identity"]["version_code"],
                    "version_name": preflight["package_identity"]["version_name"],
                },
                "revision": "phase4-v2-package-execution-plan-v2",
                "root_plans": [],
            }
        ),
        "inputs/report_schema.json": _json_bytes(
            {
                "final_ir_schema_revision": FINAL_SCHEMA_REVISION,
                "final_ir_schema_sha256": FINAL_IR_SCHEMA_SHA256,
                "report_revision": PACKAGE_REPORT_REVISION,
                "package_local_domain_result_schema": PACKAGE_LOCAL_DOMAIN_RESULT_SCHEMA,
                "required_package_local_domains": list(package_domains),
                "requires_authoritative_root_result_set": True,
                "requires_canonical_final_ir_json": True,
                "requires_final_ir_markdown_agreement": True,
                "requires_target_package_identity": True,
                "schema_revision": PACKAGE_REPORT_SCHEMA_REVISION,
            }
        ),
    }
    for relative, data in package_inputs.items():
        destination = report / relative
        destination.write_bytes(data)
        members[relative] = data
    package_pins = PackageDependencyPins(
        preflight_sha256=pins.preflight_sha256,
        ir_sha256=hashlib.sha256(final_json).hexdigest(),
        schema_sha256=hashlib.sha256(members["inputs/schema.json"]).hexdigest(),
        corpus_sha256=pins.corpus_sha256,
        execution_plan_sha256=hashlib.sha256(
            package_inputs["inputs/execution_plan.json"]
        ).hexdigest(),
        report_schema_sha256=hashlib.sha256(
            package_inputs["inputs/report_schema.json"]
        ).hexdigest(),
    )
    contract["contract_revision"] = PACKAGE_CONTRACT_REVISION
    contract["dependencies"] = {
        name: {"member": f"inputs/{name}.json", "sha256": digest}
        for name, digest in package_pins.as_pairs()
    }
    _write_contract(report, members, contract)
    return report, members, package_pins, contract


def _trusted_lineage(
    pins: DependencyPins | PackageDependencyPins,
) -> EvidenceLineageTrust:
    artifact_digest = _preflight_digest(
        "artifact", [{"name": "base.apk", "size": 1, "sha256": "f" * 64}]
    )
    document = {
        "artifact_digest": artifact_digest,
        "members": [
            {
                "authoritative_root_analyses": [
                    {
                        "evidence_anchor_ids": ["value"],
                        "semantic_root_sha256": _EVIDENCE_DIGEST,
                        "target_occurrence_identity_sha256": "b" * 64,
                        "target_root_id": "a" * 64,
                    }
                ],
                "package_local_domains": (
                    list(_PACKAGE_DOMAINS) if isinstance(pins, PackageDependencyPins) else []
                ),
                "producer": {
                    "invocation_sha256": "8" * 64,
                    "outcome": "SUCCEEDED",
                    "output_size": len(_EVIDENCE),
                    "pipeline_revision": _LINEAGE_PRODUCER.pipeline_revision,
                    "route": _LINEAGE_PRODUCER.route,
                    "tool_sha256": _LINEAGE_PRODUCER.tool_sha256,
                },
                "report_member": _EVIDENCE_MEMBER,
                "sha256": _EVIDENCE_DIGEST,
                "source_artifact_members": [{"name": "base.apk", "sha256": "f" * 64}],
            }
        ],
        "preflight_sha256": pins.preflight_sha256,
        "schema": LINEAGE_SCHEMA_REVISION,
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return EvidenceLineageTrust(
        payload=payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        trusted_producers=(_LINEAGE_PRODUCER,),
    )


def _replace_dependency[PinT: DependencyPins | PackageDependencyPins](
    report: Path,
    members: dict[str, bytes],
    pins: PinT,
    contract: dict[str, object],
    name: str,
    document: object,
) -> PinT:
    member = f"inputs/{name}.json"
    encoded = _json_bytes(document)
    (report / member).write_bytes(encoded)
    members[member] = encoded
    digest = hashlib.sha256(encoded).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    dependency = dependencies[name]
    assert isinstance(dependency, dict)
    dependency["sha256"] = digest
    _write_contract(report, members, contract)
    return replace(pins, **{f"{name}_sha256": digest})


def _set_package_roots(
    report: Path,
    members: dict[str, bytes],
    pins: PackageDependencyPins,
    contract: dict[str, object],
    *,
    root_plans: list[dict[str, object]],
    root_results: list[dict[str, object]],
) -> PackageDependencyPins:
    execution_plan = json.loads(members["inputs/execution_plan.json"])
    execution_plan["authoritative_root_count"] = len(root_plans)
    execution_plan["root_plans"] = root_plans
    plan_bytes = _json_bytes(execution_plan)
    (report / "inputs/execution_plan.json").write_bytes(plan_bytes)
    members["inputs/execution_plan.json"] = plan_bytes
    plan_digest = hashlib.sha256(plan_bytes).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    plan_dependency = dependencies["execution_plan"]
    assert isinstance(plan_dependency, dict)
    plan_dependency["sha256"] = plan_digest

    package_report = json.loads(members["analysis.json"])
    package_report["authoritative_root_results"] = root_results
    report_bytes = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(report_bytes)
    members["analysis.json"] = report_bytes
    _write_contract(report, members, contract)
    return replace(pins, execution_plan_sha256=plan_digest)


def _validate_bound(report: Path, pins: DependencyPins):
    return validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=_trusted_lineage(pins),
    )


def _validate_package_bound(report: Path, pins: PackageDependencyPins):
    return validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=_trusted_lineage(pins),
    )


def _codes(report: Path) -> tuple[str, ...]:
    return tuple(
        item.code for item in validate_report_bundle(report, allow_unbound=True).diagnostics
    )


def _validate_unbound(report: Path) -> validator_bundle.ValidationReceipt:
    return validate_report_bundle(report, allow_unbound=True)


def test_valid_bundle_has_stable_receipt_and_is_not_mutated(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    before = validator_bundle.capture_tree_snapshot(report)

    first = _validate_unbound(report)
    second = _validate_unbound(report)

    assert first.accepted is True
    assert first.source_unchanged is True
    assert first.to_json() == second.to_json()
    assert validator_bundle.capture_tree_snapshot(report) == before
    assert json.loads(first.to_json())["diagnostics"] == []


def test_pinned_dependencies_and_evidence_anchors_are_reproduced(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)

    first = _validate_bound(report, pins)
    second = _validate_bound(report, pins)

    assert first.accepted is True
    assert first.dependency_digests == tuple(
        sorted(
            pins.as_pairs()
            + (("evidence_lineage", _trusted_lineage(pins).expected_manifest_sha256),)
        )
    )
    assert first.evidence_anchors_checked == 2
    assert first.validation_profile == BOUND_VALIDATION_PROFILE
    assert first.contract_revision == CONTRACT_REVISION
    assert first.validated_artifact_identity is not None
    assert first.validated_artifact_identity.package_name == "example.package"
    assert first.validated_artifact_identity.version_code == "123"
    assert first.validated_artifact_identity.version_name == "1.2.3"
    assert [item.to_dict() for item in first.validated_evidence_members] == [
        {
            "member": _EVIDENCE_MEMBER,
            "owner": first.validated_artifact_identity.artifact_digest,
            "sha256": hashlib.sha256(
                f"{SCHEMA_REVISION}\n{SCHEMA_REVISION}\n".encode()
            ).hexdigest(),
        }
    ]
    assert [item.id for item in first.validated_evidence_anchors] == ["label", "value"]
    assert all(item.value_sha256 for item in first.validated_evidence_anchors)
    assert (
        first.validation_receipt_sha256
        == hashlib.sha256(
            json.dumps(first.identity_payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert first.to_json() == second.to_json()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda report: report.update(status="BLOCKED"), "FROZEN_REPORT_ANALYSIS_INVALID"),
        (lambda report: report.pop("completion_gates"), "FROZEN_REPORT_ANALYSIS_INVALID"),
        (
            lambda report: report["artifact"].update(package_id="other.package"),
            "FROZEN_REPORT_IDENTITY_MISMATCH",
        ),
    ],
)
def test_bound_profile_requires_complete_schema_valid_identity_bound_analysis(
    tmp_path: Path, mutation: object, expected_code: str
) -> None:
    report, members, pins, _ = _bound_bundle(tmp_path)
    analysis = json.loads(members["analysis.json"])
    assert callable(mutation)
    mutation(analysis)
    replacement = _json_bytes(analysis)
    (report / "analysis.json").write_bytes(replacement)
    members["analysis.json"] = replacement
    _write_manifest(report, members)

    receipt = _validate_bound(report, pins)

    assert expected_code in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize("member", ["ANALYSIS.md", "SEARCH_LOG.md", "reproducers/vector.py"])
def test_bound_profile_requires_every_frozen_report_artifact(tmp_path: Path, member: str) -> None:
    report, members, pins, _ = _bound_bundle(tmp_path)
    del members[member]
    (report / member).unlink()
    _write_manifest(report, members)

    receipt = _validate_bound(report, pins)

    expected = (
        "FROZEN_REPORT_REPRODUCER_MISSING"
        if member.startswith("reproducers/")
        else "FROZEN_REPORT_MEMBER_MISSING"
    )
    assert expected in {item.code for item in receipt.diagnostics}


def test_package_output_profile_attests_exact_six_pin_contract(tmp_path: Path) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)

    first = _validate_package_bound(report, pins)
    second = _validate_package_bound(report, pins)

    assert first.accepted is True
    assert first.source_unchanged is True
    assert first.diagnostics == ()
    assert first.validator_revision == validator_bundle.VALIDATOR_REVISION
    assert first.validation_profile == PACKAGE_BOUND_VALIDATION_PROFILE
    assert first.contract_revision == PACKAGE_CONTRACT_REVISION
    assert first.dependency_digests == tuple(
        sorted(
            pins.as_pairs()
            + (("evidence_lineage", _trusted_lineage(pins).expected_manifest_sha256),)
        )
    )
    assert dict(first.dependency_digests)["execution_plan"] == pins.execution_plan_sha256
    assert dict(first.dependency_digests)["report_schema"] == pins.report_schema_sha256
    assert first.validated_artifact_identity is not None
    assert first.validated_artifact_identity.package_name == "example.package"
    assert first.evidence_anchors_checked == 2
    assert first.to_json() == second.to_json()


@pytest.mark.parametrize("member", ["ANALYSIS.md", "SEARCH_LOG.md", "reproducers/vector.py"])
def test_package_profile_requires_every_frozen_report_artifact(tmp_path: Path, member: str) -> None:
    report, members, pins, _ = _package_bound_bundle(tmp_path)
    del members[member]
    (report / member).unlink()
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    expected = (
        "FROZEN_REPORT_REPRODUCER_MISSING"
        if member.startswith("reproducers/")
        else "FROZEN_REPORT_MEMBER_MISSING"
    )
    assert expected in {item.code for item in receipt.diagnostics}


def test_package_profile_rejects_empty_reproducer_artifact(tmp_path: Path) -> None:
    report, members, pins, _ = _package_bound_bundle(tmp_path)
    (report / "reproducers" / "vector.py").write_bytes(b"")
    members["reproducers/vector.py"] = b""
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    assert "FROZEN_REPORT_REPRODUCER_MISSING" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize("member", ["ANALYSIS.md", "SEARCH_LOG.md"])
def test_package_profile_rejects_empty_mandatory_document(tmp_path: Path, member: str) -> None:
    report, members, pins, _ = _package_bound_bundle(tmp_path)
    (report / member).write_bytes(b"")
    members[member] = b""
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    assert "FROZEN_REPORT_MEMBER_MISSING" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    "missing",
    [
        "target_package_identity",
        "package_local_domains",
        "authoritative_root_results",
        "final_ir_schema_revision",
        "final_ir_json_sha256",
        "final_ir_markdown_sha256",
    ],
)
def test_package_profile_requires_the_package_report_contract(tmp_path: Path, missing: str) -> None:
    report, members, pins, _ = _package_bound_bundle(tmp_path)
    package_report = json.loads(members["analysis.json"])
    del package_report[missing]
    replacement = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(replacement)
    members["analysis.json"] = replacement
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_rejects_unknown_package_report_field(tmp_path: Path) -> None:
    report, members, pins, _ = _package_bound_bundle(tmp_path)
    package_report = json.loads(members["analysis.json"])
    package_report["untrusted_extension"] = True
    replacement = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(replacement)
    members["analysis.json"] = replacement
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_requires_canonical_final_ir_json(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    ir_member = "inputs/ir.json"
    replacement = members[ir_member][:-1] + b" \n"
    (report / ir_member).write_bytes(replacement)
    members[ir_member] = replacement
    digest = hashlib.sha256(replacement).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    ir_dependency = dependencies["ir"]
    assert isinstance(ir_dependency, dict)
    ir_dependency["sha256"] = digest
    package_report = json.loads(members["analysis.json"])
    package_report["final_ir_json_sha256"] = digest
    report_bytes = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(report_bytes)
    members["analysis.json"] = report_bytes
    _write_contract(report, members, contract)

    receipt = _validate_package_bound(report, replace(pins, ir_sha256=digest))

    assert "PACKAGE_FINAL_IR_JSON_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_requires_exact_final_ir_markdown(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    replacement = members["ANALYSIS.md"] + b"\n"
    (report / "ANALYSIS.md").write_bytes(replacement)
    members["ANALYSIS.md"] = replacement
    package_report = json.loads(members["analysis.json"])
    package_report["final_ir_markdown_sha256"] = hashlib.sha256(replacement).hexdigest()
    report_bytes = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(report_bytes)
    members["analysis.json"] = report_bytes
    _write_contract(report, members, contract)

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_FINAL_IR_RENDER_INVALID" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("limit_name", "expected"),
    [
        ("_MAX_FINAL_IR_BYTES", "PACKAGE_FINAL_IR_JSON_INVALID"),
        ("_MAX_FINAL_MARKDOWN_BYTES", "PACKAGE_FINAL_IR_RENDER_INVALID"),
    ],
)
def test_package_profile_bounds_final_ir_render_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    limit_name: str,
    expected: str,
) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)
    monkeypatch.setattr(validator_binding, limit_name, 1)

    receipt = _validate_package_bound(report, pins)

    assert expected in {item.code for item in receipt.diagnostics}


def test_package_profile_reports_final_ir_read_failure_on_ir_member(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)
    original = validator_bundle._read_member_range

    def fail_final_ir_read(
        root: Path,
        member: validator_bundle.PurePosixPath,
        snapshot_nodes: dict[str, validator_bundle._Node],
        start: int,
        end: int,
    ) -> bytes:
        if member.as_posix() == "inputs/ir.json":
            raise OSError("synthetic final IR read failure")
        return original(root, member, snapshot_nodes, start, end)

    monkeypatch.setattr(validator_bundle, "_read_member_range", fail_final_ir_read)

    receipt = _validate_package_bound(report, pins)

    assert any(
        item.code == "PACKAGE_FINAL_IR_JSON_INVALID" and item.path == "inputs/ir.json"
        for item in receipt.diagnostics
    )


def test_package_profile_binds_each_authoritative_root_result_to_its_plan(
    tmp_path: Path,
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root_plan = {
        "analysis_capabilities": [],
        "analysis_dependencies": [],
        "reason": "fixture",
        "revision": "phase4-v2-root-execution-plan-v2",
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    root_result = {
        "result": {
            "analysis": {"semantic_root_sha256": _EVIDENCE_DIGEST},
            "status": "COMPLETE",
        },
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root_plan],
        root_results=[root_result],
    )
    assert _validate_package_bound(report, pins).accepted is True

    root_result["target_root_id"] = "c" * 64
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root_plan],
        root_results=[root_result],
    )

    receipt = _validate_package_bound(report, pins)
    assert "PACKAGE_REPORT_ROOT_SET_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_package_profile_rejects_root_attestation_with_unknown_anchor(tmp_path: Path) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)
    trust = _trusted_lineage(pins)
    document = json.loads(trust.payload)
    document["members"][0]["authoritative_root_analyses"][0]["evidence_anchor_ids"] = ["missing"]
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=replace(
            trust,
            payload=payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        ),
    )

    assert "ROOT_EVIDENCE_ANCHOR_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_retains_two_roots_sharing_one_evidence_member(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    roots = [("a" * 64, "b" * 64), ("c" * 64, "d" * 64)]
    root_plans = [
        {
            "analysis_capabilities": [],
            "analysis_dependencies": [],
            "reason": "fixture",
            "revision": "phase4-v2-root-execution-plan-v2",
            "route": "FULL_ANALYSIS",
            "target_occurrence_identity_sha256": occurrence,
            "target_root_id": root_id,
        }
        for root_id, occurrence in roots
    ]
    root_results = [
        {
            "result": {
                "analysis": {"semantic_root_sha256": _EVIDENCE_DIGEST},
                "status": "COMPLETE",
            },
            "route": "FULL_ANALYSIS",
            "target_occurrence_identity_sha256": occurrence,
            "target_root_id": root_id,
        }
        for root_id, occurrence in roots
    ]
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=root_plans,
        root_results=root_results,
    )
    trust = _trusted_lineage(pins)
    document = json.loads(trust.payload)
    analyses = document["members"][0]["authoritative_root_analyses"]
    analyses.append(
        {
            "evidence_anchor_ids": ["value"],
            "semantic_root_sha256": _EVIDENCE_DIGEST,
            "target_occurrence_identity_sha256": "d" * 64,
            "target_root_id": "c" * 64,
        }
    )
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=replace(
            trust,
            payload=payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        ),
    )

    assert receipt.accepted is True
    assert len(receipt.validated_root_evidence) == 2
    assert {item.evidence_members[0].member for item in receipt.validated_root_evidence} == {
        _EVIDENCE_MEMBER
    }


def test_package_profile_rejects_unattested_full_analysis_semantic_root(
    tmp_path: Path,
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root],
        root_results=[
            {
                **root,
                "result": {
                    "analysis": {"semantic_root_sha256": "c" * 64},
                    "status": "COMPLETE",
                },
            }
        ],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_FULL_ANALYSIS_UNATTESTED" in {item.code for item in receipt.diagnostics}
    assert receipt.accepted is False


def test_package_profile_rejects_extra_semantic_attestation_for_same_root(
    tmp_path: Path,
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root],
        root_results=[
            {
                **root,
                "result": {
                    "analysis": {"semantic_root_sha256": _EVIDENCE_DIGEST},
                    "status": "COMPLETE",
                },
            }
        ],
    )
    trust = _trusted_lineage(pins)
    document = json.loads(trust.payload)
    document["members"][0]["authoritative_root_analyses"].append(
        {
            "evidence_anchor_ids": ["value"],
            "semantic_root_sha256": "c" * 64,
            "target_occurrence_identity_sha256": "b" * 64,
            "target_root_id": "a" * 64,
        }
    )
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=replace(
            trust,
            payload=payload,
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        ),
    )

    assert "PACKAGE_REPORT_ROOT_EVIDENCE_SET_MISMATCH" in {
        item.code for item in receipt.diagnostics
    }


def test_package_profile_rejects_anchor_hash_as_full_analysis_semantic_root(
    tmp_path: Path,
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    anchor_digest = hashlib.sha256(SCHEMA_REVISION.encode()).hexdigest()
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root],
        root_results=[
            {
                **root,
                "result": {
                    "analysis": {"semantic_root_sha256": anchor_digest},
                    "status": "COMPLETE",
                },
            }
        ],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_FULL_ANALYSIS_UNATTESTED" in {item.code for item in receipt.diagnostics}
    assert receipt.accepted is False


def test_package_profile_rejects_semantic_root_attested_for_another_root(
    tmp_path: Path,
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "c" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root],
        root_results=[
            {
                **root,
                "result": {
                    "analysis": {"semantic_root_sha256": _EVIDENCE_DIGEST},
                    "status": "COMPLETE",
                },
            }
        ],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_FULL_ANALYSIS_UNATTESTED" in {item.code for item in receipt.diagnostics}
    assert receipt.accepted is False


def test_package_profile_rejects_unstructured_root_result(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[
            {
                "analysis_capabilities": [],
                "analysis_dependencies": [],
                "reason": "fixture",
                "revision": "phase4-v2-root-execution-plan-v2",
                "route": "FULL_ANALYSIS",
                "target_occurrence_identity_sha256": "b" * 64,
                "target_root_id": "a" * 64,
            }
        ],
        root_results=[{}],
    )

    receipt = _validate_package_bound(report, pins)
    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("route", "status"),
    [("BLOCKED", "COMPLETE"), ("EXACT_REUSE", "BLOCKED"), ("FULL_ANALYSIS", "BLOCKED")],
)
def test_package_profile_rejects_root_result_status_for_wrong_route(
    tmp_path: Path, route: str, status: str
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root_plan = {
        "route": route,
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    if route == "EXACT_REUSE":
        root_plan = {
            "reuse": {
                "inherited_semantic_root_sha256": "c" * 64,
                "source_root_id": "d" * 64,
                "target_occurrence_identity_sha256": "b" * 64,
                "target_root_id": "a" * 64,
            },
            "route": route,
        }
    root_result = {
        "result": {"status": status},
        "route": route,
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root_plan],
        root_results=[root_result],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_rejects_placeholder_root_result(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root],
        root_results=[{**root, "result": {"placeholder": True}}],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("FULL_ANALYSIS", {"placeholder": True}),
        ("FULL_ANALYSIS", {"semantic_root_sha256": "not-a-digest"}),
        ("EXACT_REUSE", {"placeholder": True}),
        (
            "EXACT_REUSE",
            {
                "inherited_semantic_root_sha256": "c" * 64,
                "source_root_id": "not-a-digest",
            },
        ),
    ],
)
def test_package_profile_rejects_invalid_route_payload(
    tmp_path: Path, route: str, payload: dict[str, object]
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": route,
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    plan = (
        {
            "route": route,
            "reuse": {
                **root,
                "inherited_semantic_root_sha256": "c" * 64,
                "source_root_id": "d" * 64,
            },
        }
        if route == "EXACT_REUSE"
        else root
    )
    result_name = "reuse" if route == "EXACT_REUSE" else "analysis"
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[plan],
        root_results=[{**root, "result": {result_name: payload, "status": "COMPLETE"}}],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_accepts_typed_exact_reuse_result(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "EXACT_REUSE",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[
            {
                "route": "EXACT_REUSE",
                "reuse": {
                    **root,
                    "inherited_semantic_root_sha256": "c" * 64,
                    "source_root_id": "d" * 64,
                },
            }
        ],
        root_results=[
            {
                **root,
                "result": {
                    "reuse": {
                        "inherited_semantic_root_sha256": "c" * 64,
                        "source_root_id": "d" * 64,
                    },
                    "status": "COMPLETE",
                },
            }
        ],
    )
    assert _validate_package_bound(report, pins).accepted is True


@pytest.mark.parametrize(
    "changed_field",
    ["inherited_semantic_root_sha256", "source_root_id"],
)
def test_package_profile_rejects_exact_reuse_result_from_unpinned_source(
    tmp_path: Path, changed_field: str
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "EXACT_REUSE",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    planned_reuse = {
        **root,
        "inherited_semantic_root_sha256": "c" * 64,
        "source_root_id": "d" * 64,
    }
    reported_reuse = {
        "inherited_semantic_root_sha256": "c" * 64,
        "source_root_id": "d" * 64,
        changed_field: "e" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[{"route": "EXACT_REUSE", "reuse": planned_reuse}],
        root_results=[
            {
                **root,
                "result": {"reuse": reported_reuse, "status": "COMPLETE"},
            }
        ],
    )
    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_ROOT_SET_MISMATCH" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("route", "result"),
    [
        ("EXACT_REUSE", {"status": "COMPLETE"}),
        ("FULL_ANALYSIS", {"status": "COMPLETE"}),
    ],
)
def test_package_profile_rejects_completed_root_without_substantive_result(
    tmp_path: Path, route: str, result: dict[str, object]
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": route,
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    plan = (
        {
            "route": route,
            "reuse": {
                **root,
                "inherited_semantic_root_sha256": "c" * 64,
                "source_root_id": "d" * 64,
            },
        }
        if route == "EXACT_REUSE"
        else root
    )
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[plan],
        root_results=[{**root, "result": result}],
    )

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    "domain_result",
    [
        {},
        {"placeholder": True},
        {"status": "COMPLETE"},
        {"evidence": ["evidence/untrusted"], "status": "COMPLETE"},
    ],
)
def test_package_profile_rejects_invalid_package_local_domain_result(
    tmp_path: Path, domain_result: dict[str, object]
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    root = {
        "route": "FULL_ANALYSIS",
        "target_occurrence_identity_sha256": "b" * 64,
        "target_root_id": "a" * 64,
    }
    pins = _set_package_roots(
        report,
        members,
        pins,
        contract,
        root_plans=[root],
        root_results=[
            {
                **root,
                "result": {
                    "analysis": {"semantic_root_sha256": "c" * 64},
                    "status": "COMPLETE",
                },
            }
        ],
    )
    package_report = json.loads(members["analysis.json"])
    package_report["package_local_domains"]["configuration"] = domain_result
    replacement = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(replacement)
    members["analysis.json"] = replacement
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_rejects_evidence_outside_domain_scope(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    evidence_members = contract["evidence_members"]
    assert isinstance(evidence_members, list)
    evidence_member = evidence_members[0]
    assert isinstance(evidence_member, dict)
    evidence_member["package_local_domains"] = [
        domain for domain in _PACKAGE_DOMAINS if domain != "configuration"
    ]
    _write_contract(report, members, contract)

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_requires_explicit_root_plan_set(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    execution_plan = json.loads(members["inputs/execution_plan.json"])
    del execution_plan["root_plans"]

    updated_pins = _replace_dependency(
        report,
        members,
        pins,
        contract,
        "execution_plan",
        execution_plan,
    )
    assert isinstance(updated_pins, PackageDependencyPins)
    receipt = _validate_package_bound(report, updated_pins)

    assert "PINNED_EXECUTION_PLAN_INVALID" in {item.code for item in receipt.diagnostics}


def test_package_profile_binds_report_to_preflight_identity(tmp_path: Path) -> None:
    report, members, pins, _ = _package_bound_bundle(tmp_path)
    package_report = json.loads(members["analysis.json"])
    package_report["target_package_identity"]["version_code"] = "different"
    replacement = _json_bytes(package_report)
    (report / "analysis.json").write_bytes(replacement)
    members["analysis.json"] = replacement
    _write_manifest(report, members)

    receipt = _validate_package_bound(report, pins)

    assert "PACKAGE_REPORT_IDENTITY_MISMATCH" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    "field",
    [
        "preflight_sha256",
        "ir_sha256",
        "schema_sha256",
        "corpus_sha256",
        "execution_plan_sha256",
        "report_schema_sha256",
    ],
)
def test_each_package_dependency_pin_is_fail_closed(tmp_path: Path, field: str) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)

    receipt = _validate_package_bound(report, replace(pins, **{field: "f" * 64}))

    assert receipt.accepted is False
    assert "DEPENDENCY_PIN_MISMATCH" in {item.code for item in receipt.diagnostics}
    assert receipt.validation_profile == PACKAGE_BOUND_VALIDATION_PROFILE


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_package_dependency_set_is_exact(tmp_path: Path, mutation: str) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    if mutation == "missing":
        del dependencies["execution_plan"]
    else:
        dependencies["unexpected"] = {
            "member": "inputs/execution_plan.json",
            "sha256": pins.execution_plan_sha256,
        }
    _write_contract(report, members, contract)

    receipt = _validate_package_bound(report, pins)

    assert "DEPENDENCY_SET_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_package_dependency_substitution_is_rejected(tmp_path: Path) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    dependencies["execution_plan"] = {
        "member": "inputs/report_schema.json",
        "sha256": pins.report_schema_sha256,
    }
    _write_contract(report, members, contract)

    receipt = _validate_package_bound(report, pins)

    assert "DEPENDENCY_PIN_MISMATCH" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("name", "field", "code"),
    [
        (
            "execution_plan",
            "execution_plan_sha256",
            "PINNED_EXECUTION_PLAN_INVALID",
        ),
        ("report_schema", "report_schema_sha256", "PINNED_REPORT_SCHEMA_INVALID"),
    ],
)
def test_package_profile_rejects_non_json_package_dependencies(
    tmp_path: Path,
    name: str,
    field: str,
    code: str,
) -> None:
    report, members, pins, contract = _package_bound_bundle(tmp_path)
    invalid = b"not-json\n"
    member = f"inputs/{name}.json"
    (report / member).write_bytes(invalid)
    members[member] = invalid
    digest = hashlib.sha256(invalid).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    dependency = dependencies[name]
    assert isinstance(dependency, dict)
    dependency["sha256"] = digest
    _write_contract(report, members, contract)

    receipt = _validate_package_bound(
        report,
        replace(pins, **{field: digest}),
    )

    assert {item.code for item in receipt.diagnostics} >= {
        "JSON_NOT_STRICT",
        code,
    }


@pytest.mark.parametrize("name", ["execution_plan", "report_schema"])
def test_package_dependency_member_must_exist(tmp_path: Path, name: str) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)
    (report / "inputs" / f"{name}.json").unlink()

    receipt = _validate_package_bound(report, pins)

    assert "DEPENDENCY_MEMBER_MISSING" in {item.code for item in receipt.diagnostics}


def test_bound_profiles_reject_contract_and_pin_type_confusion(tmp_path: Path) -> None:
    v4_report, _, v4_pins, _ = _bound_bundle(tmp_path / "v4")
    v5_report, _, v5_pins, _ = _package_bound_bundle(tmp_path / "v5")
    package_pins_for_v4 = PackageDependencyPins(
        preflight_sha256=v4_pins.preflight_sha256,
        ir_sha256=v4_pins.ir_sha256,
        schema_sha256=v4_pins.schema_sha256,
        corpus_sha256=v4_pins.corpus_sha256,
        execution_plan_sha256="a" * 64,
        report_schema_sha256="b" * 64,
    )

    v4_as_v5 = validate_report_bundle(
        v4_report,
        expected_dependencies=package_pins_for_v4,
        expected_evidence_lineage=_trusted_lineage(package_pins_for_v4),
    )
    v5_as_v4 = validate_report_bundle(
        v5_report,
        expected_dependencies=DependencyPins(
            preflight_sha256=v5_pins.preflight_sha256,
            ir_sha256=v5_pins.ir_sha256,
            schema_sha256=v5_pins.schema_sha256,
            corpus_sha256=v5_pins.corpus_sha256,
        ),
        expected_evidence_lineage=_trusted_lineage(v5_pins),
    )

    assert v4_as_v5.validation_profile == PACKAGE_BOUND_VALIDATION_PROFILE
    assert v5_as_v4.validation_profile == BOUND_VALIDATION_PROFILE
    assert {item.code for item in v4_as_v5.diagnostics} >= {
        "DEPENDENCY_SET_MISMATCH",
        "VALIDATION_CONTRACT_REVISION_MISMATCH",
    }
    assert {item.code for item in v5_as_v4.diagnostics} >= {
        "DEPENDENCY_SET_MISMATCH",
        "VALIDATION_CONTRACT_REVISION_MISMATCH",
    }


def test_canonical_receipt_binds_through_current_ir_boundary(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    receipt = _validate_bound(report, pins)
    assert receipt.validation_receipt_sha256 is not None

    bound = bind_validator_receipt(
        receipt.to_json(),
        trusted_validator_revision=receipt.validator_revision,
        trusted_contract_revision=CONTRACT_REVISION,
        trusted_dependency_digests=dict(receipt.dependency_digests),
        trusted_receipt_sha256=receipt.validation_receipt_sha256,
    )

    assert bound.validation_receipt_sha256 == receipt.validation_receipt_sha256
    assert [item.member for item in bound.validated_evidence_members] == [_EVIDENCE_MEMBER]
    assert [item.id for item in bound.validated_evidence_anchors] == ["label", "value"]


def test_unicode_receipt_uses_same_canonical_identity_as_ir(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    anchor = anchors[0]
    assert isinstance(anchor, dict)
    anchor["id"] = "læbel"
    _write_contract(report, members, contract)
    receipt = _validate_bound(report, pins)
    assert receipt.validation_receipt_sha256 is not None

    bound = bind_validator_receipt(
        receipt.to_json(),
        trusted_validator_revision=receipt.validator_revision,
        trusted_contract_revision=CONTRACT_REVISION,
        trusted_dependency_digests=dict(receipt.dependency_digests),
        trusted_receipt_sha256=receipt.validation_receipt_sha256,
    )

    assert [item.id for item in bound.validated_evidence_anchors] == ["læbel", "value"]


def test_cli_receipt_output_binds_without_newline_rewriting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    lineage = _trusted_lineage(pins)
    lineage_path = tmp_path / "trusted-lineage.json"
    lineage_path.write_bytes(lineage.payload)
    monkeypatch.setattr(
        "sys.argv",
        [
            "phase4-validator",
            str(report),
            "--preflight-sha256",
            pins.preflight_sha256,
            "--ir-sha256",
            pins.ir_sha256,
            "--schema-sha256",
            pins.schema_sha256,
            "--corpus-sha256",
            pins.corpus_sha256,
            "--evidence-lineage",
            str(lineage_path),
            "--evidence-lineage-sha256",
            lineage.expected_manifest_sha256,
            "--trusted-producer",
            f"{_LINEAGE_PRODUCER.pipeline_revision},{_LINEAGE_PRODUCER.route},"
            f"{_LINEAGE_PRODUCER.tool_sha256}",
        ],
    )

    assert validator_main.main() == 0
    output = capsys.readouterr().out
    assert not output.endswith("\n")
    receipt_data = json.loads(output)
    receipt_sha256 = receipt_data["validation_receipt_sha256"]
    assert isinstance(receipt_sha256, str)
    bound = bind_validator_receipt(
        output,
        trusted_validator_revision=validator_bundle.VALIDATOR_REVISION,
        trusted_contract_revision=CONTRACT_REVISION,
        trusted_dependency_digests={
            **dict(pins.as_pairs()),
            "evidence_lineage": lineage.expected_manifest_sha256,
        },
        trusted_receipt_sha256=receipt_sha256,
    )
    assert bound.validation_receipt_sha256 == receipt_sha256


def test_external_lineage_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    report = tmp_path / "report"
    report.mkdir()
    fifo = tmp_path / "lineage.fifo"
    os.mkfifo(fifo)

    with pytest.raises(SystemExit):
        validator_main._read_external_lineage(argparse.ArgumentParser(), report, fifo)


def test_cli_selects_package_profile_only_with_both_package_pins(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    report, _, pins, _ = _package_bound_bundle(tmp_path)
    lineage = _trusted_lineage(pins)
    lineage_path = tmp_path / "trusted-lineage.json"
    lineage_path.write_bytes(lineage.payload)
    monkeypatch.setattr(
        "sys.argv",
        [
            "phase4-validator",
            str(report),
            "--preflight-sha256",
            pins.preflight_sha256,
            "--ir-sha256",
            pins.ir_sha256,
            "--schema-sha256",
            pins.schema_sha256,
            "--corpus-sha256",
            pins.corpus_sha256,
            "--execution-plan-sha256",
            pins.execution_plan_sha256,
            "--report-schema-sha256",
            pins.report_schema_sha256,
            "--evidence-lineage",
            str(lineage_path),
            "--evidence-lineage-sha256",
            lineage.expected_manifest_sha256,
            "--trusted-producer",
            f"{_LINEAGE_PRODUCER.pipeline_revision},{_LINEAGE_PRODUCER.route},"
            f"{_LINEAGE_PRODUCER.tool_sha256}",
        ],
    )

    assert validator_main.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["validation_profile"] == PACKAGE_BOUND_VALIDATION_PROFILE
    assert receipt["contract_revision"] == PACKAGE_CONTRACT_REVISION
    assert receipt["dependency_digests"]["execution_plan"] == pins.execution_plan_sha256
    assert receipt["dependency_digests"]["report_schema"] == pins.report_schema_sha256


def test_lineage_descriptor_resolution_fails_closed_without_descriptor_fs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_path: Path, *, strict: bool = False) -> Path:
        del strict
        raise FileNotFoundError

    monkeypatch.setattr(Path, "resolve", unavailable)

    with pytest.raises(SystemExit):
        validator_main._opened_descriptor_path(argparse.ArgumentParser(), 7)


def test_pinned_ir_must_parse_with_current_ir_parser(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    invalid_ir = _empty_current_ir()
    invalid_ir["schema_revision"] = "obsolete"
    encoded = _json_bytes(invalid_ir)
    (report / "inputs" / "ir.json").write_bytes(encoded)
    members["inputs/ir.json"] = encoded
    digest = hashlib.sha256(encoded).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    ir_dependency = dependencies["ir"]
    assert isinstance(ir_dependency, dict)
    ir_dependency["sha256"] = digest
    _write_contract(report, members, contract)

    receipt = validate_report_bundle(report, expected_dependencies=replace(pins, ir_sha256=digest))

    assert "PINNED_IR_INVALID" in {item.code for item in receipt.diagnostics}


def test_pinned_ir_must_cover_its_expected_action_universe(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    incomplete_ir = _empty_current_ir()
    incomplete_ir.update(
        {
            "actions": {"raise": {"summary": "Raise"}},
            "expected_action_rules": {
                "expect_raise": {
                    "action": "raise",
                    "protocol": "primary",
                    "when": {"op": "always"},
                }
            },
            "protocols": {"primary": {"variant_space": "default"}},
            "variant_spaces": {"default": {"constraints": [], "dimensions": {}}},
        }
    )
    pins = _replace_dependency(report, members, pins, contract, "ir", incomplete_ir)

    receipt = _validate_bound(report, pins)

    diagnostic = next(item for item in receipt.diagnostics if item.code == "PINNED_IR_INVALID")
    assert dict(diagnostic.context) == {"ir_code": "missing_binding"}


def test_pinned_ir_requires_exact_semantic_evidence_coverage(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    uncovered_ir = _empty_current_ir()
    uncovered_ir["actions"] = {"raise": {"summary": "Raise"}}
    pins = _replace_dependency(report, members, pins, contract, "ir", uncovered_ir)

    receipt = _validate_bound(report, pins)

    diagnostic = next(item for item in receipt.diagnostics if item.code == "PINNED_IR_INVALID")
    assert dict(diagnostic.context) == {
        "ir_code": "missing_evidence_binding",
        "ir_path": "/actions/raise/@key",
    }


def test_pinned_schema_must_equal_current_structure(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    stale_schema = schema_document()
    stale_schema["title"] = "mutated"
    encoded = _json_bytes(stale_schema)
    (report / "inputs" / "schema.json").write_bytes(encoded)
    members["inputs/schema.json"] = encoded
    digest = hashlib.sha256(encoded).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    schema_dependency = dependencies["schema"]
    assert isinstance(schema_dependency, dict)
    schema_dependency["sha256"] = digest
    _write_contract(report, members, contract)

    receipt = validate_report_bundle(
        report, expected_dependencies=replace(pins, schema_sha256=digest)
    )

    assert "PINNED_SCHEMA_STRUCTURE_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_pinned_schema_revision_is_checked_independently(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    stale_schema = schema_document()
    properties = stale_schema["properties"]
    assert isinstance(properties, dict)
    properties["schema_revision"] = {"const": "obsolete"}
    encoded = _json_bytes(stale_schema)
    (report / "inputs" / "schema.json").write_bytes(encoded)
    members["inputs/schema.json"] = encoded
    digest = hashlib.sha256(encoded).hexdigest()
    dependencies = contract["dependencies"]
    assert isinstance(dependencies, dict)
    schema_dependency = dependencies["schema"]
    assert isinstance(schema_dependency, dict)
    schema_dependency["sha256"] = digest
    _write_contract(report, members, contract)

    receipt = validate_report_bundle(
        report, expected_dependencies=replace(pins, schema_sha256=digest)
    )

    assert "PINNED_SCHEMA_REVISION_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_anchor_count_limit_fails_before_range_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    monkeypatch.setattr(validator_binding, "_MAX_ANCHOR_COUNT", 1)

    def unexpected_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("range reader must not run after the count gate")

    monkeypatch.setattr(validator_bundle, "_read_member_range", unexpected_read)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_ANCHOR_LIMIT_EXCEEDED" in {item.code for item in receipt.diagnostics}


def test_anchor_byte_budget_fails_before_range_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    monkeypatch.setattr(validator_binding, "_MAX_ANCHOR_BYTES", 1)

    def unexpected_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("range reader must not run after the byte gate")

    monkeypatch.setattr(validator_bundle, "_read_member_range", unexpected_read)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_BYTE_BUDGET_EXCEEDED" in {item.code for item in receipt.diagnostics}


def test_malformed_anchor_cannot_bypass_cumulative_byte_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    anchors[0] = {}
    _write_contract(report, members, contract)
    monkeypatch.setattr(validator_binding, "_MAX_ANCHOR_BYTES", 1)

    def unexpected_read(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("malformed entries must not disable the byte gate")

    monkeypatch.setattr(validator_bundle, "_read_member_range", unexpected_read)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_BYTE_BUDGET_EXCEEDED" in {item.code for item in receipt.diagnostics}


def test_anchor_reader_reads_only_exact_descriptor_ranges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    original_pread = os.pread
    calls: list[tuple[int, int]] = []

    def observed_pread(fd: int, length: int, offset: int) -> bytes:
        calls.append((length, offset))
        return original_pread(fd, length, offset)

    monkeypatch.setattr(os, "pread", observed_pread)

    receipt = _validate_bound(report, pins)

    assert receipt.accepted is True
    assert calls == [
        (len(SCHEMA_REVISION), 0),
        (len(SCHEMA_REVISION), len(SCHEMA_REVISION) + 1),
    ]


@pytest.mark.parametrize(
    "field",
    ["preflight_sha256", "ir_sha256", "schema_sha256", "corpus_sha256"],
)
def test_each_dependency_pin_is_fail_closed(tmp_path: Path, field: str) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    wrong = replace(pins, **{field: "f" * 64})

    receipt = validate_report_bundle(report, expected_dependencies=wrong)

    assert receipt.accepted is False
    assert "DEPENDENCY_PIN_MISMATCH" in tuple(item.code for item in receipt.diagnostics)


def test_missing_evidence_member_fails_existence_gate(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    (report / _EVIDENCE_MEMBER).unlink()

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_MEMBER_MISSING" in tuple(item.code for item in receipt.diagnostics)


def test_anchor_owner_must_match_declared_member_owner(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    anchor = anchors[0]
    assert isinstance(anchor, dict)
    anchor["owner"] = "f" * 64
    _write_contract(report, members, contract)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_ANCHOR_OWNER_MISMATCH" in tuple(item.code for item in receipt.diagnostics)


def test_evidence_owner_is_pinned_to_package_preflight(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    evidence_members = contract["evidence_members"]
    anchors = contract["anchors"]
    assert isinstance(evidence_members, list)
    assert isinstance(anchors, list)
    evidence_member = evidence_members[0]
    assert isinstance(evidence_member, dict)
    evidence_member["owner"] = "f" * 64
    for anchor in anchors:
        assert isinstance(anchor, dict)
        anchor["owner"] = "f" * 64
    _write_contract(report, members, contract)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_OWNER_PIN_MISMATCH" in tuple(item.code for item in receipt.diagnostics)


def test_anchor_range_must_be_inside_owned_member(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    anchor = anchors[0]
    assert isinstance(anchor, dict)
    anchor["end_byte"] = 10_000
    _write_contract(report, members, contract)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_RANGE_OUT_OF_BOUNDS" in tuple(item.code for item in receipt.diagnostics)


def test_anchor_value_must_reproduce_from_exact_bytes(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    anchor = anchors[1]
    assert isinstance(anchor, dict)
    anchor["representation"] = "hex"
    _write_contract(report, members, contract)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_VALUE_MISMATCH" in tuple(item.code for item in receipt.diagnostics)


def test_anchor_attestation_fields_are_bounded_for_external_binding(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    anchors = contract["anchors"]
    assert isinstance(anchors, list)
    anchor = anchors[0]
    assert isinstance(anchor, dict)
    anchor["id"] = "a" * 257
    _write_contract(report, members, contract)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_ANCHOR_INVALID" in {item.code for item in receipt.diagnostics}


def test_bound_contract_without_trusted_pins_is_rejected(tmp_path: Path) -> None:
    report, _, _, _ = _bound_bundle(tmp_path)

    receipt = validate_report_bundle(report)

    assert "DEPENDENCY_PINS_REQUIRED" in tuple(item.code for item in receipt.diagnostics)


def test_malformed_bound_contract_cannot_bypass_binding_validation(tmp_path: Path) -> None:
    report, members, pins, _ = _bound_bundle(tmp_path)
    malformed = b'{"dependencies":{},"dependencies":{}}\n'
    (report / "validation-input.json").write_bytes(malformed)
    members["validation-input.json"] = malformed
    _write_manifest(report, members)

    receipt = _validate_bound(report, pins)

    assert {item.code for item in receipt.diagnostics} >= {
        "JSON_NOT_STRICT",
        "VALIDATION_INPUT_INVALID",
    }


def test_default_validation_is_fail_closed_without_binding_contract(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)

    receipt = validate_report_bundle(report)

    assert receipt.accepted is False
    assert receipt.validation_profile == "FILESYSTEM_ONLY"
    assert tuple(item.code for item in receipt.diagnostics) == ("DEPENDENCY_PINS_REQUIRED",)


def test_stale_member_hash_is_rejected(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    analysis = report / "analysis.json"
    analysis.write_bytes(b'{"schema_revision":"synthetic-v2","status":"COMPLETE"}\n')

    assert _codes(report) == ("MEMBER_DIGEST_MISMATCH",)


def test_extra_member_is_rejected(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    (report / "unhashed.txt").write_text("extra", encoding="utf-8")

    assert _codes(report) == ("MEMBER_UNDECLARED",)


def test_missing_member_is_rejected(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    (report / "ANALYSIS.md").unlink()

    assert _codes(report) == ("MEMBER_MISSING",)


def test_manifest_path_traversal_is_rejected_without_reading_target(tmp_path: Path) -> None:
    report = tmp_path / "report"
    report.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret":true}', encoding="utf-8")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (report / "REPORT.SHA256").write_text(f"{digest}  ../outside.json\n", encoding="utf-8")

    receipt = _validate_unbound(report)

    assert tuple(item.code for item in receipt.diagnostics) == ("PATH_ESCAPE",)
    assert outside.read_text(encoding="utf-8") == '{"secret":true}'


def test_symlink_escape_is_rejected_without_following_it(tmp_path: Path) -> None:
    report = tmp_path / "report"
    report.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret":true}', encoding="utf-8")
    os.symlink(outside, report / "analysis.json")
    digest = hashlib.sha256(outside.read_bytes()).hexdigest()
    (report / "REPORT.SHA256").write_text(f"{digest}  analysis.json\n", encoding="utf-8")

    assert _codes(report) == ("MEMBER_NOT_REGULAR", "SYMLINK_FORBIDDEN")
    assert outside.read_text(encoding="utf-8") == '{"secret":true}'


def test_duplicate_json_key_is_rejected(tmp_path: Path) -> None:
    report, members = _valid_bundle(tmp_path)
    duplicate = b'{"status":"COMPLETE","status":"PARTIAL"}\n'
    (report / "analysis.json").write_bytes(duplicate)
    members["analysis.json"] = duplicate
    _write_manifest(report, members)

    receipt = _validate_unbound(report)

    assert _codes(report) == ("JSON_NOT_STRICT",)
    assert receipt.diagnostics[0].to_dict()["context"] == {
        "key": "status",
        "reason": "duplicate_key",
    }


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity", b"1e9999"])
def test_non_finite_json_number_is_rejected(constant: bytes) -> None:
    with pytest.raises(validator_bundle.StrictJsonError, match="non_finite_number"):
        load_json_strict(b'{"value":' + constant + b"}")


def test_manifest_parser_bounds_invalid_line_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validator_bundle, "_MAX_MANIFEST_DIAGNOSTICS", 3)

    _entries, diagnostics = validator_bundle._parse_manifest(b"invalid\n" * 10)

    assert [item.code for item in diagnostics] == [
        "MANIFEST_INVALID_LINE",
        "MANIFEST_INVALID_LINE",
        "MANIFEST_DIAGNOSTIC_LIMIT_EXCEEDED",
    ]


def test_manifest_parser_bounds_valid_declarations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validator_bundle, "_MAX_MANIFEST_DECLARATIONS", 2)
    manifest = "".join(f"{'0' * 64}  member-{index}\n" for index in range(5)).encode()

    entries, diagnostics = validator_bundle._parse_manifest(manifest)

    assert [entry.path for entry in entries] == ["member-0", "member-1"]
    assert [item.code for item in diagnostics] == ["MANIFEST_DECLARATION_LIMIT_EXCEEDED"]


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (b'{"value":' + b"9" * 5_000 + b"}", "invalid_json"),
        (b'{"value":"\\ud800"}', "invalid_unicode"),
    ],
)
def test_hostile_json_values_are_deterministically_rejected(payload: bytes, reason: str) -> None:
    with pytest.raises(validator_bundle.StrictJsonError, match=reason):
        load_json_strict(payload)


def test_validator_json_depth_and_integer_bounds_are_fail_closed() -> None:
    nested: object = 0
    for _ in range(130):
        nested = [nested]

    with pytest.raises(validator_bundle.StrictJsonError, match="json_too_deep"):
        load_json_strict(_json_bytes(nested))
    with pytest.raises(validator_bundle.StrictJsonError, match="integer_out_of_range"):
        load_json_strict(_json_bytes({"value": 2**63}))


@pytest.mark.parametrize("token", ["+1", "-1", " 1", "1_0", "01", "١"])
def test_ir_pointer_rejects_noncanonical_array_indices(token: str) -> None:
    with pytest.raises(IndexError):
        _resolve_json_pointer(["zero", "one"], f"/{token}")


def test_evidence_pointer_index_error_becomes_a_diagnostic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)

    def reject_pointer(_document: object, _pointer: str) -> object:
        raise IndexError("out of range")

    monkeypatch.setattr(validator_binding, "_resolve_semantic_pointer", reject_pointer)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_IR_POINTER_INVALID" in {item.code for item in receipt.diagnostics}


def test_source_snapshot_comparison_ignores_only_access_time(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    before = validator_bundle.capture_tree_snapshot(report)
    after = replace(
        before,
        nodes=tuple(replace(node, atime_ns=node.atime_ns + 1) for node in before.nodes),
    )

    assert validator_bundle._source_snapshots_match(before, after) is True
    changed = replace(
        after,
        nodes=(replace(after.nodes[0], mtime_ns=after.nodes[0].mtime_ns + 1), *after.nodes[1:]),
    )
    assert validator_bundle._source_snapshots_match(before, changed) is False


@pytest.mark.parametrize("member", ["inputs/ir.json", "analysis.json"])
def test_bound_validator_rejects_generated_self_evidence(tmp_path: Path, member: str) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    owner = preflight["artifact_digest"]
    contract["evidence_members"] = [
        {
            "member": member,
            "owner": owner,
            "sha256": hashlib.sha256(members[member]).hexdigest(),
        }
    ]
    _write_contract(report, members, contract)

    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=_trusted_lineage(pins),
    )

    assert receipt.accepted is False
    assert {
        "TRUSTED_EVIDENCE_NAMESPACE_INVALID",
        "EVIDENCE_NAMESPACE_INVALID",
    }.intersection(item.code for item in receipt.diagnostics)


def test_content_addressed_copy_of_ir_cannot_replace_external_lineage(
    tmp_path: Path,
) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    copied = members["inputs/ir.json"]
    copied_digest = hashlib.sha256(copied).hexdigest()
    copied_member = f"evidence/sha256/{copied_digest}"
    destination = report / copied_member
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(copied)
    members[copied_member] = copied
    preflight = json.loads(members["inputs/preflight.json"])
    owner = preflight["artifact_digest"]
    contract["evidence_members"] = [
        {"member": copied_member, "owner": owner, "sha256": copied_digest}
    ]
    contract["anchors"] = [
        {
            "id": "self-schema",
            "owner": owner,
            "member": copied_member,
            "start_byte": 20,
            "end_byte": 20 + len(SCHEMA_REVISION),
            "ir_pointer": "/schema_revision",
            "representation": "utf8",
        }
    ]
    _write_contract(report, members, contract)

    receipt = _validate_bound(report, pins)

    assert "EVIDENCE_MEMBER_SET_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_lineage_identity_is_rechecked_at_bundle_boundary(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    trust = _trusted_lineage(pins)
    document = json.loads(trust.payload)
    document["artifact_digest"] = "0" * 64
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    forged = replace(
        trust,
        payload=payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
    )

    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=forged,
    )

    diagnostic = next(
        item for item in receipt.diagnostics if item.code == "TRUSTED_EVIDENCE_LINEAGE_INVALID"
    )
    assert dict(diagnostic.context)["lineage_code"] == "artifact_digest_mismatch"


def test_lineage_producer_route_must_be_required_by_preflight(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    trust = _trusted_lineage(pins)
    document = json.loads(trust.payload)
    producer_data = document["members"][0]["producer"]
    assert isinstance(producer_data, dict)
    producer_data["route"] = "jadx"
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    forged = EvidenceLineageTrust(
        payload=payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        trusted_producers=(TrustedProducer("phase4-extract-v1", "jadx", _LINEAGE_TOOL_SHA256),),
    )

    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=forged,
    )

    assert "TRUSTED_EVIDENCE_LINEAGE_ROUTE_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_lineage_completion_size_must_match_substantive_bundle_output(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    trust = _trusted_lineage(pins)
    document = json.loads(trust.payload)
    producer_data = document["members"][0]["producer"]
    assert isinstance(producer_data, dict)
    producer_data["output_size"] = len(_EVIDENCE) + 1
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    forged = replace(
        trust,
        payload=payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
    )

    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=forged,
    )

    assert "TRUSTED_EVIDENCE_LINEAGE_COMPLETION_OUTPUT_INVALID" in {
        item.code for item in receipt.diagnostics
    }


def test_lineage_cannot_borrow_route_from_another_artifact_member(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    artifact_members = [
        {"name": "base.apk", "size": 1, "sha256": "f" * 64},
        {"name": "split.apk", "size": 1, "sha256": "6" * 64},
    ]
    artifact_digest = _preflight_digest("artifact", artifact_members)
    preflight["artifact_members"] = artifact_members
    preflight["artifact_digest"] = artifact_digest
    preflight["package_identity"]["split_members"] = [["config", "split.apk"]]
    preflight["classification"] = {
        "stacks": ["android", "android_dex"],
        "routes": ["apktool", "jadx"],
        "status": "READY",
        "blockers": [],
        "members": [
            {
                "name": "base.apk",
                "stacks": ["android", "android_dex"],
                "routes": ["apktool", "jadx"],
                "status": "READY",
                "blockers": [],
            },
            {
                "name": "split.apk",
                "stacks": ["android"],
                "routes": ["apktool"],
                "status": "READY",
                "blockers": [],
            },
        ],
    }
    changed_pins = _replace_dependency(report, members, pins, contract, "preflight", preflight)
    evidence_members = contract["evidence_members"]
    anchors = contract["anchors"]
    assert isinstance(evidence_members, list)
    assert isinstance(anchors, list)
    for item in [*evidence_members, *anchors]:
        assert isinstance(item, dict)
        item["owner"] = artifact_digest
    _write_contract(report, members, contract)
    producer = TrustedProducer("phase4-extract-v1", "jadx", _LINEAGE_TOOL_SHA256)
    lineage_document = {
        "artifact_digest": artifact_digest,
        "members": [
            {
                "authoritative_root_analyses": [],
                "package_local_domains": [],
                "producer": {
                    "invocation_sha256": "8" * 64,
                    "outcome": "SUCCEEDED",
                    "output_size": len(_EVIDENCE),
                    "pipeline_revision": producer.pipeline_revision,
                    "route": producer.route,
                    "tool_sha256": producer.tool_sha256,
                },
                "report_member": _EVIDENCE_MEMBER,
                "sha256": _EVIDENCE_DIGEST,
                "source_artifact_members": [{"name": "split.apk", "sha256": "6" * 64}],
            }
        ],
        "preflight_sha256": changed_pins.preflight_sha256,
        "schema": LINEAGE_SCHEMA_REVISION,
    }
    lineage_payload = json.dumps(lineage_document, sort_keys=True, separators=(",", ":")).encode()
    lineage = EvidenceLineageTrust(
        payload=lineage_payload,
        expected_manifest_sha256=hashlib.sha256(lineage_payload).hexdigest(),
        trusted_producers=(producer,),
    )

    receipt = validate_report_bundle(
        report,
        expected_dependencies=changed_pins,
        expected_evidence_lineage=lineage,
    )

    assert "TRUSTED_EVIDENCE_LINEAGE_ROUTE_MISMATCH" in {item.code for item in receipt.diagnostics}


def test_lineage_must_cover_every_required_member_route(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    preflight["classification"] = {
        "stacks": ["android", "android_dex"],
        "routes": ["apktool", "jadx"],
        "status": "READY",
        "blockers": [],
        "members": [
            {
                "name": "base.apk",
                "stacks": ["android", "android_dex"],
                "routes": ["apktool", "jadx"],
                "status": "READY",
                "blockers": [],
            }
        ],
    }
    changed_pins = _replace_dependency(report, members, pins, contract, "preflight", preflight)

    receipt = validate_report_bundle(
        report,
        expected_dependencies=changed_pins,
        expected_evidence_lineage=_trusted_lineage(changed_pins),
    )

    assert "TRUSTED_EVIDENCE_LINEAGE_ROUTE_COVERAGE_INCOMPLETE" in {
        item.code for item in receipt.diagnostics
    }


def test_bound_validator_requires_external_evidence_lineage(tmp_path: Path) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)

    receipt = validate_report_bundle(report, expected_dependencies=pins)

    assert receipt.accepted is False
    assert "TRUSTED_EVIDENCE_LINEAGE_REQUIRED" in {item.code for item in receipt.diagnostics}


def test_pinned_preflight_artifact_digest_must_reproduce(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    preflight["artifact_digest"] = "0" * 64
    changed_pins = _replace_dependency(
        report,
        members,
        pins,
        contract,
        "preflight",
        preflight,
    )

    receipt = _validate_bound(report, changed_pins)

    assert "PINNED_PREFLIGHT_INVALID" in {item.code for item in receipt.diagnostics}


def test_legacy_blocked_preflight_cannot_issue_bound_receipt(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    preflight["schema"] = "phase4-v2-preflight-v2"
    preflight["classification"] = {
        "stacks": ["android"],
        "routes": ["apktool"],
        "status": "BLOCKED",
        "blockers": ["stack_detection_not_exhaustive"],
    }
    changed_pins = _replace_dependency(report, members, pins, contract, "preflight", preflight)

    receipt = _validate_bound(report, changed_pins)

    assert "PINNED_PREFLIGHT_NOT_READY" in {item.code for item in receipt.diagnostics}


@pytest.mark.parametrize(
    ("status", "blockers"),
    [
        ("UNKNOWN", []),
        ("READY", ["contradictory"]),
        ("BLOCKED", []),
    ],
)
def test_v3_preflight_status_and_blockers_must_be_coherent(
    tmp_path: Path, status: str, blockers: list[str]
) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    classification = preflight["classification"]
    assert isinstance(classification, dict)
    classification["status"] = status
    classification["blockers"] = blockers
    changed_pins = _replace_dependency(report, members, pins, contract, "preflight", preflight)

    receipt = _validate_bound(report, changed_pins)

    assert "PINNED_PREFLIGHT_CLASSIFICATION_INVALID" in {item.code for item in receipt.diagnostics}


def test_coherent_v3_blocked_preflight_is_not_ready(tmp_path: Path) -> None:
    report, members, pins, contract = _bound_bundle(tmp_path)
    preflight = json.loads(members["inputs/preflight.json"])
    classification = preflight["classification"]
    assert isinstance(classification, dict)
    classification["status"] = "BLOCKED"
    classification["blockers"] = ["unknown_application_stack:base.apk"]
    classified_members = classification["members"]
    assert isinstance(classified_members, list)
    member = classified_members[0]
    assert isinstance(member, dict)
    member["status"] = "BLOCKED"
    member["blockers"] = ["unknown_application_stack:base.apk"]
    changed_pins = _replace_dependency(report, members, pins, contract, "preflight", preflight)

    receipt = _validate_bound(report, changed_pins)

    assert "PINNED_PREFLIGHT_NOT_READY" in {item.code for item in receipt.diagnostics}


def test_accepted_receipt_must_fit_ir_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, _, pins, _ = _bound_bundle(tmp_path)
    monkeypatch.setattr(validator_bundle, "_MAX_RECEIPT_BYTES", 1)

    receipt = _validate_bound(report, pins)

    assert receipt.accepted is False
    assert "RECEIPT_SIZE_LIMIT_EXCEEDED" in {item.code for item in receipt.diagnostics}


def test_rejected_receipt_is_compacted_to_its_size_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(validator_bundle, "_MAX_RECEIPT_BYTES", 1_024)
    receipt = validator_bundle.ValidationReceipt(
        validator_revision="fixture-v1",
        accepted=False,
        source_unchanged=True,
        bundle_sha256=None,
        report_manifest_sha256=None,
        discovered_members=0,
        declared_members=0,
        diagnostics=tuple(
            validator_bundle.Diagnostic("FAILURE", f"path-{index}-{'x' * 100}")
            for index in range(10)
        ),
    )

    compact = validator_bundle._with_receipt_identity(receipt)

    assert compact.diagnostics == (validator_bundle.Diagnostic("RECEIPT_SIZE_LIMIT_EXCEEDED", "."),)
    assert len(compact.to_json().encode()) <= validator_bundle._MAX_RECEIPT_BYTES


def test_validator_detects_concurrent_source_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, _ = _valid_bundle(tmp_path)
    analysis = report / "analysis.json"
    original_capture = validator_bundle.capture_tree_snapshot
    captures = 0

    def mutate_before_second_capture(root: Path) -> validator_bundle._TreeSnapshot:
        nonlocal captures
        captures += 1
        if captures == 2:
            analysis.write_bytes(b'{"status":"changed-after-validation"}\n')
        return original_capture(root)

    monkeypatch.setattr(validator_bundle, "capture_tree_snapshot", mutate_before_second_capture)

    receipt = _validate_unbound(report)

    assert "SOURCE_TREE_MUTATED" in tuple(item.code for item in receipt.diagnostics)
    assert receipt.source_unchanged is False
    assert receipt.accepted is False


def test_validator_never_executes_report_scripts(tmp_path: Path) -> None:
    report, members = _valid_bundle(tmp_path)
    marker = tmp_path / "executed"
    script = f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n".encode()
    (report / "reproducers" / "vector.py").write_bytes(script)
    members["reproducers/vector.py"] = script
    _write_manifest(report, members)

    assert _validate_unbound(report).accepted is True
    assert marker.exists() is False


def test_validator_limits_aggregate_retained_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report, members = _valid_bundle(tmp_path)
    extra = b"{}\n"
    (report / "extra.json").write_bytes(extra)
    members["extra.json"] = extra
    _write_manifest(report, members)
    monkeypatch.setattr(
        validator_bundle,
        "_MAX_PARSED_JSON_BYTES",
        len(members["analysis.json"]),
    )

    receipt = _validate_unbound(report)

    assert "JSON_AGGREGATE_LIMIT_EXCEEDED" in {item.code for item in receipt.diagnostics}


def test_validator_checks_tree_limit_before_sorting_every_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = tmp_path / "report"
    report.mkdir()
    (report / "one").write_text("one", encoding="utf-8")
    (report / "two").write_text("two", encoding="utf-8")
    monkeypatch.setattr(validator_bundle, "_MAX_TREE_ENTRIES", 2)

    receipt = _validate_unbound(report)

    assert tuple(item.code for item in receipt.diagnostics) == ("SOURCE_SNAPSHOT_FAILED",)
    assert receipt.diagnostics[0].to_dict()["context"] == {"operation": "entry_limit_exceeded"}


def test_member_read_is_bound_to_initial_snapshot(tmp_path: Path) -> None:
    report, members = _valid_bundle(tmp_path)
    snapshot = validator_bundle.capture_tree_snapshot(report)
    snapshot_nodes = {node.path: node for node in snapshot.nodes}
    replacement = b'{"status":"different"}\n'
    (report / "analysis.json").write_bytes(replacement)
    members["analysis.json"] = replacement
    _write_manifest(report, members)

    with pytest.raises(OSError, match="changed since initial snapshot"):
        validator_bundle._read_member(
            report,
            validator_bundle.PurePosixPath("analysis.json"),
            snapshot_nodes,
            max_bytes=64 * 1024,
        )


def test_range_read_is_bound_to_initial_snapshot(tmp_path: Path) -> None:
    report, _, _, _ = _bound_bundle(tmp_path)
    snapshot = validator_bundle.capture_tree_snapshot(report)
    snapshot_nodes = {node.path: node for node in snapshot.nodes}
    source = report / _EVIDENCE_MEMBER
    source.write_bytes(b"x" * source.stat().st_size)

    with pytest.raises(OSError, match="changed since initial snapshot"):
        validator_bundle._read_member_range(
            report,
            validator_bundle.PurePosixPath(_EVIDENCE_MEMBER),
            snapshot_nodes,
            0,
            1,
        )


def test_non_utf8_member_name_is_rejected_without_receipt_crash(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    raw_path = os.fsencode(report) + b"/bad-\xff.txt"
    descriptor = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, b"opaque")
    finally:
        os.close(descriptor)

    receipt = _validate_unbound(report)

    assert receipt.accepted is False
    assert "MEMBER_UNDECLARED" in tuple(item.code for item in receipt.diagnostics)
    assert receipt.bundle_sha256 is not None


def test_validation_reads_do_not_change_access_time(tmp_path: Path) -> None:
    report, _ = _valid_bundle(tmp_path)
    analysis = report / "analysis.json"
    node = analysis.stat()
    old_atime = 1_600_000_000_000_000_000
    os.utime(analysis, ns=(old_atime, node.st_mtime_ns))

    receipt = _validate_unbound(report)

    assert receipt.accepted is True
    assert analysis.stat().st_atime_ns == old_atime


def test_hardlinked_report_member_is_rejected(tmp_path: Path) -> None:
    report, members = _valid_bundle(tmp_path)
    os.link(report / "analysis.json", report / "analysis-copy.json")
    members["analysis-copy.json"] = members["analysis.json"]
    _write_manifest(report, members)

    receipt = _validate_unbound(report)

    hardlinks = [item.path for item in receipt.diagnostics if item.code == "HARDLINK_FORBIDDEN"]
    assert hardlinks == ["analysis-copy.json", "analysis.json"]
