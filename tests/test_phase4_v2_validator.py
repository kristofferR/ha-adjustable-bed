"""Mutation tests for the Phase 4 v2 filesystem-integrity validator."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import tools.phase4_v2.validator.__main__ as validator_main
import tools.phase4_v2.validator.binding as validator_binding
import tools.phase4_v2.validator.bundle as validator_bundle
from tools.phase4_v2.ir import SCHEMA_REVISION, bind_validator_receipt, schema_document
from tools.phase4_v2.validator import (
    BOUND_VALIDATION_PROFILE,
    CONTRACT_REVISION,
    PACKAGE_BOUND_VALIDATION_PROFILE,
    PACKAGE_CONTRACT_REVISION,
    DependencyPins,
    EvidenceLineageTrust,
    PackageDependencyPins,
    TrustedProducer,
    load_json_strict,
    validate_report_bundle,
)

_EVIDENCE = f"{SCHEMA_REVISION}\n{SCHEMA_REVISION}\n".encode()
_EVIDENCE_DIGEST = hashlib.sha256(_EVIDENCE).hexdigest()
_EVIDENCE_MEMBER = f"evidence/sha256/{_EVIDENCE_DIGEST}"
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


def _valid_bundle(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    report = tmp_path / "report"
    scripts = report / "reproducers"
    scripts.mkdir(parents=True)
    members = {
        "ANALYSIS.md": b"Synthetic validation fixture.\n",
        "SEARCH_LOG.md": b"Synthetic validation fixture.\n",
        "analysis.json": b'{"schema_revision":"synthetic-v1","status":"COMPLETE"}\n',
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
    package_inputs = {
        "inputs/execution_plan.json": _json_bytes(
            {"schema": "phase4-v2-execution-plan-v1", "steps": []}
        ),
        "inputs/report_schema.json": _json_bytes(
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}
        ),
    }
    for relative, data in package_inputs.items():
        destination = report / relative
        destination.write_bytes(data)
        members[relative] = data
    package_pins = PackageDependencyPins(
        preflight_sha256=pins.preflight_sha256,
        ir_sha256=pins.ir_sha256,
        schema_sha256=pins.schema_sha256,
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
                "producer": {
                    "invocation_sha256": "8" * 64,
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
        "schema": "phase4-v2-evidence-lineage-v1",
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return EvidenceLineageTrust(
        payload=payload,
        expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
        trusted_producers=(_LINEAGE_PRODUCER,),
    )


def _replace_dependency(
    report: Path,
    members: dict[str, bytes],
    pins: DependencyPins,
    contract: dict[str, object],
    name: str,
    document: object,
) -> DependencyPins:
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
    assert first.dependency_digests == pins.as_pairs() + (
        ("evidence_lineage", _trusted_lineage(pins).expected_manifest_sha256),
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
    assert first.dependency_digests == pins.as_pairs() + (
        ("evidence_lineage", _trusted_lineage(pins).expected_manifest_sha256),
    )
    assert dict(first.dependency_digests)["execution_plan"] == pins.execution_plan_sha256
    assert dict(first.dependency_digests)["report_schema"] == pins.report_schema_sha256
    assert first.validated_artifact_identity is not None
    assert first.validated_artifact_identity.package_name == "example.package"
    assert first.evidence_anchors_checked == 2
    assert first.to_json() == second.to_json()


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
        item
        for item in receipt.diagnostics
        if item.code == "TRUSTED_EVIDENCE_LINEAGE_INVALID"
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
        trusted_producers=(
            TrustedProducer("phase4-extract-v1", "jadx", _LINEAGE_TOOL_SHA256),
        ),
    )

    receipt = validate_report_bundle(
        report,
        expected_dependencies=pins,
        expected_evidence_lineage=forged,
    )

    assert "TRUSTED_EVIDENCE_LINEAGE_ROUTE_MISMATCH" in {
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
    changed_pins = _replace_dependency(
        report, members, pins, contract, "preflight", preflight
    )
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
                "producer": {
                    "invocation_sha256": "8" * 64,
                    "pipeline_revision": producer.pipeline_revision,
                    "route": producer.route,
                    "tool_sha256": producer.tool_sha256,
                },
                "report_member": _EVIDENCE_MEMBER,
                "sha256": _EVIDENCE_DIGEST,
                "source_artifact_members": [
                    {"name": "split.apk", "sha256": "6" * 64}
                ],
            }
        ],
        "preflight_sha256": changed_pins.preflight_sha256,
        "schema": "phase4-v2-evidence-lineage-v1",
    }
    lineage_payload = json.dumps(
        lineage_document, sort_keys=True, separators=(",", ":")
    ).encode()
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

    assert "TRUSTED_EVIDENCE_LINEAGE_ROUTE_MISMATCH" in {
        item.code for item in receipt.diagnostics
    }


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
    changed_pins = _replace_dependency(
        report, members, pins, contract, "preflight", preflight
    )

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
    changed_pins = _replace_dependency(
        report, members, pins, contract, "preflight", preflight
    )

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
    changed_pins = _replace_dependency(
        report, members, pins, contract, "preflight", preflight
    )

    receipt = _validate_bound(report, changed_pins)

    assert "PINNED_PREFLIGHT_CLASSIFICATION_INVALID" in {
        item.code for item in receipt.diagnostics
    }


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
    changed_pins = _replace_dependency(
        report, members, pins, contract, "preflight", preflight
    )

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
            max_bytes=1024,
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
