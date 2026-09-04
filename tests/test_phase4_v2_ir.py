"""Focused tests for the compact Phase 4 v2 protocol IR core."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator

import pytest

import tools.phase4_v2.ir.model as ir_model
from tools.phase4_v2.ir import (
    BOUND_VALIDATION_PROFILE,
    SCHEMA_REVISION,
    SUPPORTED_CONTRACT_REVISION,
    SUPPORTED_VALIDATOR_REVISION,
    IRValidationError,
    ProtocolIRDocument,
    bind_validator_receipt,
    build_artifact_identity,
    build_evidence_anchor,
    build_evidence_binding,
    build_evidence_file,
    build_source_package,
    build_source_set,
    dumps_ir,
    loads_ir,
    parse_ir,
    schema_document,
    semantic_fingerprint,
    validate_universe,
)

_DEPENDENCY_DIGESTS = {
    "corpus": "1" * 64,
    "evidence_lineage": "2" * 64,
    "ir": "3" * 64,
    "preflight": "4" * 64,
    "schema": "5" * 64,
}
_EVIDENCE_MEMBER = "evidence/source.txt"
_EVIDENCE_SHA256 = hashlib.sha256(b"Raise").hexdigest()


def _document() -> dict[str, object]:
    return {
        "schema_revision": SCHEMA_REVISION,
        "source_packages": {},
        "evidence_files": {},
        "evidence_anchors": {},
        "source_sets": {},
        "evidence_bindings": {},
        "variant_spaces": {
            "variants": {
                "dimensions": {
                    "side": ["right", "left"],
                    "model": ["beta", "alpha"],
                },
                "constraints": [],
            }
        },
        "protocols": {"primary": {"variant_space": "variants"}},
        "actions": {
            "raise": {"summary": "Raise"},
            "lower": {"summary": "Lower"},
        },
        "expected_action_rules": {
            "expect_raise": {
                "protocol": "primary",
                "action": "raise",
                "when": {"op": "always"},
            },
            "expect_lower_beta": {
                "protocol": "primary",
                "action": "lower",
                "when": {
                    "op": "in",
                    "dimension": "model",
                    "values": ["beta"],
                },
            },
        },
        "command_bindings": {
            "bind_raise": {
                "protocol": "primary",
                "action": "raise",
                "when": {"op": "always"},
            },
            "bind_lower_beta": {
                "protocol": "primary",
                "action": "lower",
                "when": {
                    "op": "eq",
                    "dimension": "model",
                    "value": "beta",
                },
            },
        },
    }


def _load(data: dict[str, object]) -> ProtocolIRDocument:
    return ir_model._parse_ir_structure(json.loads(json.dumps(data)))


def _receipt_payload(**overrides: object) -> tuple[bytes, str]:
    receipt: dict[str, object] = {
        "accepted": True,
        "bundle_sha256": "b" * 64,
        "contract_revision": SUPPORTED_CONTRACT_REVISION,
        "declared_members": 8,
        "dependency_digests": dict(_DEPENDENCY_DIGESTS),
        "diagnostics": [],
        "discovered_members": 8,
        "evidence_anchors_checked": 2,
        "report_manifest_sha256": "c" * 64,
        "source_unchanged": True,
        "validated_artifact_identity": {
            "package_name": "example.package",
            "version_code": "123",
            "version_name": "1.2.3",
            "artifact_digest": "a" * 64,
        },
        "validated_evidence_anchors": [
            {
                "id": "raise-key",
                "owner": "a" * 64,
                "member": _EVIDENCE_MEMBER,
                "member_sha256": _EVIDENCE_SHA256,
                "start_byte": 0,
                "end_byte": 10,
                "ir_pointer": "/actions/raise/@key",
                "representation": "utf8",
                "value_sha256": hashlib.sha256(b'"raise"').hexdigest(),
            },
            {
                "id": "raise-summary",
                "owner": "a" * 64,
                "member": _EVIDENCE_MEMBER,
                "member_sha256": _EVIDENCE_SHA256,
                "start_byte": 0,
                "end_byte": 5,
                "ir_pointer": "/actions/raise/summary",
                "representation": "utf8",
                "value_sha256": hashlib.sha256(b'"Raise"').hexdigest(),
            },
        ],
        "validated_evidence_members": [
            {
                "member": _EVIDENCE_MEMBER,
                "owner": "a" * 64,
                "sha256": _EVIDENCE_SHA256,
            }
        ],
        "validation_profile": BOUND_VALIDATION_PROFILE,
        "validator_revision": SUPPORTED_VALIDATOR_REVISION,
    }
    receipt.update(overrides)
    identity = hashlib.sha256(
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    receipt["validation_receipt_sha256"] = identity
    return (
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode(),
        identity,
    )


def _bind_report(**overrides: object):
    payload, identity = _receipt_payload(**overrides)
    return bind_validator_receipt(
        payload,
        trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
        trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
        trusted_dependency_digests=_DEPENDENCY_DIGESTS,
        trusted_receipt_sha256=identity,
    )


def _provenance_document() -> tuple[dict[str, object], dict[str, str]]:
    artifact = build_artifact_identity(
        package_name="example.package",
        version_code="123",
        version_name="1.2.3",
        artifact_digest="a" * 64,
    )
    report = _bind_report()
    package_id, package = build_source_package(artifact, report)
    file_id, evidence_file = build_evidence_file(
        package=package_id,
        member=_EVIDENCE_MEMBER,
        sha256=_EVIDENCE_SHA256,
    )
    anchor_id, anchor = build_evidence_anchor(
        id="raise-summary",
        file=file_id,
        start_byte=0,
        end_byte=5,
        ir_pointer="/actions/raise/summary",
        representation="utf8",
        value_sha256=hashlib.sha256(b'"Raise"').hexdigest(),
    )
    source_set_id, source_set = build_source_set(
        package=package_id,
        anchors=(anchor_id,),
    )
    binding_id, binding = build_evidence_binding(
        target="/actions/raise/summary",
        source_sets=(source_set_id,),
    )
    key_anchor_id, key_anchor = build_evidence_anchor(
        id="raise-key",
        file=file_id,
        start_byte=0,
        end_byte=10,
        ir_pointer="/actions/raise/@key",
        representation="utf8",
        value_sha256=hashlib.sha256(b'"raise"').hexdigest(),
    )
    key_source_set_id, key_source_set = build_source_set(
        package=package_id,
        anchors=(key_anchor_id,),
    )
    key_binding_id, key_binding = build_evidence_binding(
        target="/actions/raise/@key",
        source_sets=(key_source_set_id,),
    )
    data = _document()
    data["source_packages"] = {package_id: package.to_data()}
    data["evidence_files"] = {file_id: evidence_file.to_data()}
    data["evidence_anchors"] = {
        anchor_id: anchor.to_data(),
        key_anchor_id: key_anchor.to_data(),
    }
    data["source_sets"] = {
        source_set_id: source_set.to_data(),
        key_source_set_id: key_source_set.to_data(),
    }
    data["evidence_bindings"] = {
        binding_id: binding.to_data(),
        key_binding_id: key_binding.to_data(),
    }
    return data, {
        "package": package_id,
        "file": file_id,
        "anchor": anchor_id,
        "source_set": source_set_id,
        "binding": binding_id,
        "key_anchor": key_anchor_id,
        "key_source_set": key_source_set_id,
        "key_binding": key_binding_id,
    }


def _authorized_single_leaf_document() -> tuple[dict[str, object], dict[str, str]]:
    data, identifiers = _provenance_document()
    data["variant_spaces"] = {}
    data["protocols"] = {}
    data["actions"] = {"raise": {"summary": "Raise"}}
    data["expected_action_rules"] = {}
    data["command_bindings"] = {}
    return data, identifiers


def _trusted_receipts(data: dict[str, object], package_id: str) -> dict[str, str]:
    packages = data["source_packages"]
    assert isinstance(packages, dict)
    package = packages[package_id]
    assert isinstance(package, dict)
    report = package["report"]
    assert isinstance(report, dict)
    receipt_sha256 = report["validation_receipt_sha256"]
    bundle_sha256 = report["bundle_sha256"]
    assert isinstance(receipt_sha256, str)
    assert isinstance(bundle_sha256, str)
    return {receipt_sha256: bundle_sha256}


def test_canonical_round_trip_and_fingerprint_are_deterministic() -> None:
    first_data = _document()
    second_data = copy.deepcopy(first_data)
    second_data["variant_spaces"] = {
        "variants": {
            "constraints": [],
            "dimensions": {
                "model": ["alpha", "beta"],
                "side": ["left", "right"],
            },
        }
    }
    second_data["actions"] = {
        "lower": {"summary": "Lower"},
        "raise": {"summary": "Raise"},
    }

    first = _load(first_data)
    second = _load(second_data)
    canonical = dumps_ir(first)

    assert canonical == dumps_ir(second)
    assert dumps_ir(ir_model._parse_ir_structure(json.loads(canonical))) == canonical
    assert semantic_fingerprint(first) == semantic_fingerprint(second)
    assert validate_universe(first).is_valid


def test_universe_reports_every_missing_action_variant() -> None:
    data = _document()
    bindings = data["command_bindings"]
    assert isinstance(bindings, dict)
    del bindings["bind_lower_beta"]

    result = validate_universe(_load(data))

    missing = [issue for issue in result.issues if issue.code == "missing_binding"]
    assert len(missing) == 2
    assert {dict(issue.key.profile)["side"] for issue in missing if issue.key} == {
        "left",
        "right",
    }


def test_universe_reports_bindings_outside_expected_applicability() -> None:
    data = _document()
    bindings = data["command_bindings"]
    assert isinstance(bindings, dict)
    lower = bindings["bind_lower_beta"]
    assert isinstance(lower, dict)
    lower["when"] = {"op": "always"}

    result = validate_universe(_load(data))

    extra = [issue for issue in result.issues if issue.code == "extra_binding"]
    assert len(extra) == 2
    assert {dict(issue.key.profile)["model"] for issue in extra if issue.key} == {"alpha"}


def test_universe_preserves_boolean_and_integer_selector_identity() -> None:
    data = _document()
    data["variant_spaces"] = {
        "variants": {
            "dimensions": {"selector": [True, 1]},
            "constraints": [],
        }
    }
    data["actions"] = {"raise": {"summary": "Raise"}}
    data["expected_action_rules"] = {
        "expect_boolean": {
            "protocol": "primary",
            "action": "raise",
            "when": {"op": "eq", "dimension": "selector", "value": True},
        }
    }
    data["command_bindings"] = {
        "bind_integer": {
            "protocol": "primary",
            "action": "raise",
            "when": {"op": "eq", "dimension": "selector", "value": 1},
        }
    }

    result = validate_universe(_load(data))

    assert [issue.code for issue in result.issues] == ["extra_binding", "missing_binding"]
    assert {type(dict(issue.key.profile)["selector"]) for issue in result.issues if issue.key} == {
        bool,
        int,
    }


def test_universe_distinguishes_duplicate_binding_coverage() -> None:
    data = _document()
    bindings = data["command_bindings"]
    assert isinstance(bindings, dict)
    bindings["bind_raise_duplicate"] = copy.deepcopy(bindings["bind_raise"])

    result = validate_universe(_load(data))

    duplicates = [issue for issue in result.issues if issue.code == "duplicate_binding_coverage"]
    assert len(duplicates) == 1
    assert duplicates[0].binding_ids == ("bind_raise", "bind_raise_duplicate")


def test_universe_distinguishes_partially_overlapping_bindings() -> None:
    data = _document()
    bindings = data["command_bindings"]
    assert isinstance(bindings, dict)
    bindings["bind_raise_alpha"] = {
        "protocol": "primary",
        "action": "raise",
        "when": {"op": "eq", "dimension": "model", "value": "alpha"},
    }

    result = validate_universe(_load(data))

    overlaps = [issue for issue in result.issues if issue.code == "overlapping_binding_coverage"]
    assert len(overlaps) == 1
    assert overlaps[0].binding_ids == ("bind_raise", "bind_raise_alpha")


def test_universe_groups_duplicate_bindings_without_pairwise_expansion() -> None:
    data = _document()
    bindings = data["command_bindings"]
    assert isinstance(bindings, dict)
    original = bindings["bind_raise"]
    for index in range(100):
        bindings[f"bind_raise_duplicate_{index:03d}"] = copy.deepcopy(original)

    result = validate_universe(_load(data))

    duplicates = [issue for issue in result.issues if issue.code == "duplicate_binding_coverage"]
    assert len(duplicates) == 1
    assert len(duplicates[0].binding_ids) == 101


def test_universe_caches_shared_spaces_and_bounds_aggregate_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _document()
    protocols = data["protocols"]
    assert isinstance(protocols, dict)
    protocols["secondary"] = {"variant_space": "variants"}
    document = _load(data)
    profile_calls = 0
    original_iter_profiles = ir_model.VariantSpace.iter_profiles

    def counted_profiles(space: ir_model.VariantSpace) -> Iterator[ir_model.Profile]:
        nonlocal profile_calls
        profile_calls += 1
        return original_iter_profiles(space)

    monkeypatch.setattr(ir_model.VariantSpace, "iter_profiles", counted_profiles)
    monkeypatch.setattr(ir_model, "_MAX_UNIVERSE_PROFILE_REFERENCES", 7)

    with pytest.raises(IRValidationError) as caught:
        validate_universe(document)

    assert caught.value.diagnostics[0].code == "universe_too_large"
    assert profile_calls == 1


def test_universe_stops_materializing_distinct_spaces_at_aggregate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _document()
    spaces = data["variant_spaces"]
    protocols = data["protocols"]
    assert isinstance(spaces, dict)
    assert isinstance(protocols, dict)
    spaces["variants_b"] = copy.deepcopy(spaces["variants"])
    spaces["variants_c"] = copy.deepcopy(spaces["variants"])
    protocols["secondary"] = {"variant_space": "variants_b"}
    protocols["tertiary"] = {"variant_space": "variants_c"}
    document = _load(data)
    profile_calls = 0
    original_iter_profiles = ir_model.VariantSpace.iter_profiles

    def counted_profiles(space: ir_model.VariantSpace) -> Iterator[ir_model.Profile]:
        nonlocal profile_calls
        profile_calls += 1
        return original_iter_profiles(space)

    monkeypatch.setattr(ir_model.VariantSpace, "iter_profiles", counted_profiles)
    monkeypatch.setattr(ir_model, "_MAX_UNIVERSE_PROFILE_REFERENCES", 7)

    with pytest.raises(IRValidationError) as caught:
        validate_universe(document)

    assert caught.value.diagnostics[0].code == "universe_too_large"
    assert profile_calls == 2


def test_variant_space_iterator_rejects_100001_valid_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ir_model, "_MAX_VARIANT_PROFILE_CANDIDATES", 100_001)
    space = ir_model.VariantSpace(
        (("variant", tuple(range(100_001))),),
        (),
    )

    with pytest.raises(IRValidationError) as caught:
        tuple(space.iter_profiles())

    assert caught.value.diagnostics[0].code == "variant_space_too_large"
    assert "valid profiles" in caught.value.diagnostics[0].message


def test_variant_space_iterator_rejects_100001_candidates_before_filtering() -> None:
    space = ir_model.VariantSpace(
        (("variant", tuple(range(100_001))),),
        (ir_model.Predicate("never"),),
    )

    with pytest.raises(IRValidationError) as caught:
        tuple(space.iter_profiles())

    assert caught.value.diagnostics[0].code == "variant_space_too_large"
    assert "candidate profiles" in caught.value.diagnostics[0].message


def test_parse_ir_rejects_json_container_subclasses_without_iterating() -> None:
    class HostileDict(dict[str, object]):
        def __iter__(self):
            raise AssertionError("hostile iterator was consumed")

    with pytest.raises(IRValidationError, match="invalid_json_structure"):
        parse_ir(HostileDict())


def test_universe_bounds_rule_and_binding_profile_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _load(_document())
    monkeypatch.setattr(ir_model, "_MAX_UNIVERSE_PROFILE_REFERENCES", 19)

    with pytest.raises(IRValidationError) as caught:
        validate_universe(document)

    assert caught.value.diagnostics[0].code == "universe_too_large"


def test_loader_is_strict_and_rejects_duplicate_definition_ids() -> None:
    payload = json.dumps(_document())
    payload = payload.replace(
        '"raise": {"summary": "Raise"}',
        '"raise": {"summary": "Raise"}, "raise": {"summary": "Again"}',
    )

    with pytest.raises(IRValidationError) as caught:
        loads_ir(payload)

    assert caught.value.diagnostics[0].code == "duplicate_object_key"


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_loader_rejects_non_finite_json_numbers(number: str) -> None:
    payload = json.dumps(_document()).replace('"Raise"', number, 1)

    with pytest.raises(IRValidationError) as caught:
        loads_ir(payload)

    assert caught.value.diagnostics[0].code == "non_finite_number"


def test_invalid_selector_is_diagnostic_instead_of_crashing_profile_expansion() -> None:
    data = _document()
    spaces = data["variant_spaces"]
    assert isinstance(spaces, dict)
    variants = spaces["variants"]
    assert isinstance(variants, dict)
    variants["constraints"] = [{"op": "eq", "dimension": "missing", "value": "anything"}]

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "unknown_selector_dimension"


def test_oversized_variant_space_is_rejected_before_expansion() -> None:
    data = _document()
    spaces = data["variant_spaces"]
    assert isinstance(spaces, dict)
    variants = spaces["variants"]
    assert isinstance(variants, dict)
    variants["dimensions"] = {f"d{index}": [False, True] for index in range(17)}

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "variant_space_too_large"


def test_loader_rejects_unpaired_unicode_surrogates() -> None:
    data = _document()
    actions = data["actions"]
    assert isinstance(actions, dict)
    actions["raise"] = {"summary": "\ud800"}

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "invalid_unicode"


def test_schema_document_is_pinned_strict_and_defensively_copied() -> None:
    first = schema_document()
    second = schema_document()

    assert first["additionalProperties"] is False
    assert first["properties"] != {}
    first["title"] = "changed"
    assert second["title"] == "Phase 4 protocol intermediate representation"


def test_provenance_builders_bind_validator_receipt_and_round_trip() -> None:
    first_data, identifiers = _provenance_document()
    second_data = copy.deepcopy(first_data)
    for key in (
        "source_packages",
        "evidence_files",
        "evidence_anchors",
        "source_sets",
        "evidence_bindings",
    ):
        definitions = second_data[key]
        assert isinstance(definitions, dict)
        second_data[key] = dict(reversed(tuple(definitions.items())))

    first = _load(first_data)
    second = _load(second_data)

    assert dumps_ir(first) == dumps_ir(second)
    assert semantic_fingerprint(first) == semantic_fingerprint(second)
    assert identifiers["package"].startswith("pkg:")
    assert identifiers["binding"].startswith("evidence:")


def test_semantic_fingerprint_excludes_artifact_and_receipt_provenance() -> None:
    with_provenance, _ = _provenance_document()
    without_provenance = copy.deepcopy(with_provenance)
    for key in (
        "source_packages",
        "evidence_files",
        "evidence_anchors",
        "source_sets",
        "evidence_bindings",
    ):
        without_provenance[key] = {}

    assert semantic_fingerprint(_load(with_provenance)) == semantic_fingerprint(
        _load(without_provenance)
    )


@pytest.mark.parametrize(
    ("accepted", "source_unchanged", "code"),
    [
        (False, True, "validator_rejected"),
        (True, False, "validator_source_changed"),
    ],
)
def test_validator_binding_requires_accepted_unchanged_source(
    accepted: bool, source_unchanged: bool, code: str
) -> None:
    payload, identity = _receipt_payload(
        accepted=accepted,
        source_unchanged=source_unchanged,
    )

    with pytest.raises(IRValidationError) as caught:
        bind_validator_receipt(
            payload,
            trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256=identity,
        )

    assert caught.value.diagnostics[0].code == code


def test_validator_binding_retains_exact_receipt_attestations() -> None:
    payload, identity = _receipt_payload()

    report = bind_validator_receipt(
        payload,
        trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
        trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
        trusted_dependency_digests=_DEPENDENCY_DIGESTS,
        trusted_receipt_sha256=identity,
    )

    assert report.validation_receipt_sha256 == identity
    assert report.dependency_digests == tuple(_DEPENDENCY_DIGESTS.items())
    assert report.validated_evidence_members[0].member == _EVIDENCE_MEMBER
    assert {anchor.ir_pointer for anchor in report.validated_evidence_anchors} == {
        "/actions/raise/@key",
        "/actions/raise/summary",
    }


def test_provenance_definition_identity_is_content_addressed() -> None:
    data, identifiers = _provenance_document()
    files = data["evidence_files"]
    assert isinstance(files, dict)
    evidence_file = files[identifiers["file"]]
    assert isinstance(evidence_file, dict)
    evidence_file["sha256"] = "e" * 64

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "noncanonical_provenance_id"


def test_source_sets_cannot_cross_package_boundaries() -> None:
    data, identifiers = _provenance_document()
    artifact = build_artifact_identity(
        package_name="other.package",
        version_code="9",
        version_name="9",
        artifact_digest="1" * 64,
    )
    report = _bind_report(
        bundle_sha256="2" * 64,
        report_manifest_sha256="3" * 64,
        validated_artifact_identity=artifact.to_data(),
        validated_evidence_members=[
            {
                "member": _EVIDENCE_MEMBER,
                "owner": artifact.artifact_digest,
                "sha256": _EVIDENCE_SHA256,
            }
        ],
        evidence_anchors_checked=1,
        validated_evidence_anchors=[
            {
                "id": "raise-summary",
                "owner": artifact.artifact_digest,
                "member": _EVIDENCE_MEMBER,
                "member_sha256": _EVIDENCE_SHA256,
                "start_byte": 0,
                "end_byte": 5,
                "ir_pointer": "/actions/raise/summary",
                "representation": "utf8",
                "value_sha256": hashlib.sha256(b'"Raise"').hexdigest(),
            }
        ],
    )
    other_package_id, other_package = build_source_package(artifact, report)
    packages = data["source_packages"]
    assert isinstance(packages, dict)
    packages[other_package_id] = other_package.to_data()
    mismatched_id, mismatched = build_source_set(
        package=other_package_id,
        anchors=(identifiers["anchor"],),
    )
    source_sets = data["source_sets"]
    assert isinstance(source_sets, dict)
    source_sets[mismatched_id] = mismatched.to_data()

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert any(
        diagnostic.code == "cross_package_source_set" for diagnostic in caught.value.diagnostics
    )


def test_evidence_target_must_be_an_existing_semantic_leaf() -> None:
    data, identifiers = _provenance_document()
    bindings = data["evidence_bindings"]
    assert isinstance(bindings, dict)
    old_binding = bindings.pop(identifiers["binding"])
    assert isinstance(old_binding, dict)
    invalid_id, invalid = build_evidence_binding(
        target="/actions/raise",
        source_sets=tuple(old_binding["source_sets"]),
    )
    bindings[invalid_id] = invalid.to_data()

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "evidence_target_not_leaf"


def test_nonnumeric_list_pointer_is_a_closed_validation_diagnostic() -> None:
    data, identifiers = _provenance_document()
    bindings = data["evidence_bindings"]
    assert isinstance(bindings, dict)
    old_binding = bindings.pop(identifiers["binding"])
    assert isinstance(old_binding, dict)
    invalid_id, invalid = build_evidence_binding(
        target="/variant_spaces/variants/dimensions/side/not-an-index",
        source_sets=tuple(old_binding["source_sets"]),
    )
    bindings[invalid_id] = invalid.to_data()

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "unknown_evidence_target"


def test_provenance_reference_expansion_is_bounded() -> None:
    with pytest.raises(IRValidationError) as caught:
        build_source_set(package="pkg:" + "a" * 64, anchors=("a" for _ in range(4097)))

    assert caught.value.diagnostics[0].code == "reference_set_too_large"


def test_shared_source_set_transitive_expansion_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data, _ = _provenance_document()
    monkeypatch.setattr(ir_model, "_MAX_PROVENANCE_EXPANSIONS", 1)

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "provenance_expansion_too_large"


def test_validation_diagnostic_amplification_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ir_model, "_MAX_VALIDATION_DIAGNOSTICS", 1)

    with pytest.raises(IRValidationError) as caught:
        ir_model._parse_ir_structure({})

    assert caught.value.diagnostics[0].code == "validation_diagnostic_limit_exceeded"


def test_provenance_objects_remain_closed() -> None:
    data, identifiers = _provenance_document()
    files = data["evidence_files"]
    assert isinstance(files, dict)
    evidence_file = files[identifiers["file"]]
    assert isinstance(evidence_file, dict)
    evidence_file["comment"] = "not part of the schema"

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "unknown_property"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"validation_profile": "FILESYSTEM_ONLY"}, "unbound_validation_profile"),
        ({"validation_profile": "BOUND_V1"}, "unbound_validation_profile"),
        ({"validator_revision": "validator-unknown"}, "validator_revision_mismatch"),
        ({"contract_revision": "contract-unknown"}, "contract_revision_mismatch"),
    ],
)
def test_receipt_binding_rejects_downgraded_or_unknown_contracts(
    overrides: dict[str, object], code: str
) -> None:
    payload, identity = _receipt_payload(**overrides)

    with pytest.raises(IRValidationError) as caught:
        bind_validator_receipt(
            payload,
            trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256=identity,
        )

    assert caught.value.diagnostics[0].code == code


def test_caller_cannot_bless_an_unknown_validator_revision() -> None:
    payload, identity = _receipt_payload(validator_revision="validator-unknown")

    with pytest.raises(IRValidationError) as caught:
        bind_validator_receipt(
            payload,
            trusted_validator_revision="validator-unknown",
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256=identity,
        )

    assert caught.value.diagnostics[0].code == "unsupported_validator_revision"


def test_receipt_binding_requires_exact_caller_dependency_pins() -> None:
    changed_pins = dict(_DEPENDENCY_DIGESTS)
    changed_pins["corpus"] = "f" * 64
    payload, identity = _receipt_payload(dependency_digests=changed_pins)

    with pytest.raises(IRValidationError) as caught:
        bind_validator_receipt(
            payload,
            trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256=identity,
        )

    assert caught.value.diagnostics[0].code == "dependency_pin_mismatch"


def test_receipt_binding_requires_exact_receipt_identity_and_canonical_bytes() -> None:
    payload, identity = _receipt_payload()

    with pytest.raises(IRValidationError) as wrong_identity:
        bind_validator_receipt(
            payload,
            trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256="f" * 64,
        )
    assert wrong_identity.value.diagnostics[0].code == "receipt_trust_mismatch"

    with pytest.raises(IRValidationError) as noncanonical:
        bind_validator_receipt(
            payload + b"\n",
            trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256=identity,
        )
    assert noncanonical.value.diagnostics[0].code == "receipt_not_canonical"


def test_evidence_file_and_anchor_must_be_exact_receipt_attestations() -> None:
    data, identifiers = _provenance_document()
    invented_file_id, invented_file = build_evidence_file(
        package=identifiers["package"],
        member="work/invented.txt",
        sha256="e" * 64,
    )
    files = data["evidence_files"]
    assert isinstance(files, dict)
    files[invented_file_id] = invented_file.to_data()

    with pytest.raises(IRValidationError) as invented_member:
        _load(data)
    assert any(
        item.code == "evidence_member_not_attested" for item in invented_member.value.diagnostics
    )

    data, identifiers = _provenance_document()
    invented_anchor_id, invented_anchor = build_evidence_anchor(
        id="raise-summary",
        file=identifiers["file"],
        start_byte=1,
        end_byte=5,
        ir_pointer="/actions/raise/summary",
        representation="utf8",
        value_sha256=hashlib.sha256(b'"Raise"').hexdigest(),
    )
    anchors = data["evidence_anchors"]
    assert isinstance(anchors, dict)
    anchors[invented_anchor_id] = invented_anchor.to_data()

    with pytest.raises(IRValidationError) as invented_range:
        _load(data)
    assert any(
        item.code == "evidence_anchor_not_attested" for item in invented_range.value.diagnostics
    )


def test_retained_attestations_must_reproduce_the_trusted_receipt_identity() -> None:
    data, identifiers = _provenance_document()
    packages = data["source_packages"]
    assert isinstance(packages, dict)
    package = packages[identifiers["package"]]
    assert isinstance(package, dict)
    report = package["report"]
    assert isinstance(report, dict)
    anchors = report["validated_evidence_anchors"]
    assert isinstance(anchors, list)
    anchor = anchors[0]
    assert isinstance(anchor, dict)
    anchor["start_byte"] = 1

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "receipt_identity_mismatch"


def test_source_set_anchor_attestation_must_match_semantic_target() -> None:
    data, identifiers = _provenance_document()
    bindings = data["evidence_bindings"]
    assert isinstance(bindings, dict)
    bindings.clear()
    binding_id, binding = build_evidence_binding(
        target="/actions/lower/summary",
        source_sets=(identifiers["source_set"],),
    )
    bindings[binding_id] = binding.to_data()

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert any(
        item.code == "evidence_target_attestation_mismatch" for item in caught.value.diagnostics
    )


def test_authorized_loader_requires_external_receipt_trust_and_exact_coverage() -> None:
    data, identifiers = _authorized_single_leaf_document()
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    trust = _trusted_receipts(data, identifiers["package"])

    loaded = loads_ir(encoded, trusted_receipts=trust)
    assert dict(loaded.actions)["raise"].summary == "Raise"

    with pytest.raises(IRValidationError) as untrusted:
        loads_ir(encoded)
    assert untrusted.value.diagnostics[0].code == "untrusted_validator_receipt"

    missing = copy.deepcopy(data)
    missing["evidence_bindings"] = {}
    with pytest.raises(IRValidationError) as uncovered:
        loads_ir(
            json.dumps(missing, sort_keys=True, separators=(",", ":")).encode(),
            trusted_receipts=trust,
        )
    assert uncovered.value.diagnostics[0].code == "missing_evidence_binding"


def test_authorized_loader_rejects_semantic_value_changed_after_validation() -> None:
    data, identifiers = _authorized_single_leaf_document()
    trust = _trusted_receipts(data, identifiers["package"])
    actions = data["actions"]
    assert isinstance(actions, dict)
    actions["raise"] = {"summary": "Changed after validation"}

    with pytest.raises(IRValidationError) as caught:
        loads_ir(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode(),
            trusted_receipts=trust,
        )

    assert any(
        item.code == "evidence_value_attestation_mismatch" for item in caught.value.diagnostics
    )


def test_authorized_loader_rejects_invented_empty_definition_and_identifier() -> None:
    data, identifiers = _authorized_single_leaf_document()
    actions = data["actions"]
    assert isinstance(actions, dict)
    actions["invented"] = {}

    with pytest.raises(IRValidationError) as caught:
        loads_ir(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode(),
            trusted_receipts=_trusted_receipts(data, identifiers["package"]),
        )

    missing = {
        item.path for item in caught.value.diagnostics if item.code == "missing_evidence_binding"
    }
    assert missing == {"/actions/invented", "/actions/invented/@key"}


def test_source_package_rejects_artifact_substitution_at_construction() -> None:
    report = _bind_report()
    different = build_artifact_identity(
        package_name="different.package",
        version_code="999",
        version_name="9.9.9",
        artifact_digest="f" * 64,
    )

    with pytest.raises(IRValidationError) as caught:
        build_source_package(different, report)

    assert caught.value.diagnostics[0].code == "artifact_identity_attestation_mismatch"


def test_receipt_binding_rejects_unpaired_unicode_as_diagnostic() -> None:
    with pytest.raises(IRValidationError) as caught:
        bind_validator_receipt(
            b'{"value":"\\ud800"}',
            trusted_validator_revision=SUPPORTED_VALIDATOR_REVISION,
            trusted_contract_revision=SUPPORTED_CONTRACT_REVISION,
            trusted_dependency_digests=_DEPENDENCY_DIGESTS,
            trusted_receipt_sha256="f" * 64,
        )

    assert caught.value.diagnostics[0].code == "invalid_unicode"


def test_json_depth_cycles_and_huge_integers_fail_as_diagnostics() -> None:
    with pytest.raises(IRValidationError) as deeply_nested:
        loads_ir(b"[" * 2_000 + b"]" * 2_000)
    assert deeply_nested.value.diagnostics[0].code == "json_too_deep"

    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(IRValidationError) as cycle:
        parse_ir(cyclic)
    assert cycle.value.diagnostics[0].code == "invalid_json_structure"

    data = _document()
    spaces = data["variant_spaces"]
    assert isinstance(spaces, dict)
    variants = spaces["variants"]
    assert isinstance(variants, dict)
    variants["dimensions"] = {"huge": [2**63]}
    with pytest.raises(IRValidationError) as huge_integer:
        parse_ir(data)
    assert huge_integer.value.diagnostics[0].code == "integer_out_of_range"


def test_json_value_error_and_input_size_are_closed_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(IRValidationError) as huge_literal:
        loads_ir("9" * 10_000)
    assert huge_literal.value.diagnostics[0].code == "invalid_json"

    monkeypatch.setattr(ir_model, "_MAX_IR_BYTES", 8)
    with pytest.raises(IRValidationError) as oversized:
        loads_ir(b'{"nine":9}')
    assert oversized.value.diagnostics[0].code == "input_too_large"
