"""Synthetic tests for the closed final-domain protocol IR."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

import tools.phase4_v2.ir.model as core
import tools.phase4_v2.ir.v1 as v1
from tools.phase4_v2.ir import (
    FINAL_DOMAIN_COLLECTIONS,
    FINAL_SCHEMA_REVISION,
    IRValidationError,
    dumps_final_ir,
    final_schema_document,
    final_semantic_fingerprint,
    loads_final_ir,
    parse_final_ir,
    render_final_ir_markdown,
    validate_final_ir_markdown,
    validate_final_universe,
)


def _document() -> dict[str, object]:
    selector_dimensions = {
        "model": ["alpha", "beta"],
        "variant": ["default"],
        "remote_code": [1],
        "capability": [True],
        "configuration": ["standard"],
        "user_state": ["idle"],
    }
    selector_kinds = {
        "model": "MODEL",
        "variant": "VARIANT",
        "remote_code": "REMOTE_CODE",
        "capability": "CAPABILITY",
        "configuration": "CONFIGURATION",
        "user_state": "USER_STATE",
    }
    data: dict[str, object] = {
        "schema_revision": FINAL_SCHEMA_REVISION,
        "source_packages": {},
        "evidence_files": {},
        "evidence_anchors": {},
        "source_sets": {},
        "evidence_bindings": {},
        "variant_spaces": {"variants": {"dimensions": selector_dimensions, "constraints": []}},
        "protocols": {"protocol": {"variant_space": "variants"}},
        "actions": {"raise": {"summary": "Raise"}, "stop": {}},
        "expected_action_rules": {
            "expect_raise": {
                "protocol": "protocol",
                "action": "raise",
                "when": {"op": "always"},
            }
        },
        "selectors": {
            name: {
                "variant_space": "variants",
                "dimension": name,
                "kind": selector_kinds[name],
                "values": values,
            }
            for name, values in selector_dimensions.items()
        },
        "selection_rules": {"select": {"protocol": "protocol", "when": {"op": "always"}}},
        "discovery_rules": {
            "discover": {
                "selection_rule": "select",
                "matchers": [
                    {
                        "field": "SERVICE_UUID",
                        "operation": "EQUALS",
                        "value": "1234",
                    }
                ],
            }
        },
        "gatt_services": {"service": {"uuid": "1234", "role": "CONTROL"}},
        "gatt_characteristics": {
            "write": {
                "service": "service",
                "uuid": "5678",
                "roles": ["NOTIFY", "WRITE"],
                "write_modes": ["WITHOUT_RESPONSE"],
            }
        },
        "transforms": {"xor": {"operation": "XOR", "operand": 1}},
        "checksums": {
            "checksum": {
                "algorithm": "SUM8",
                "start_byte": 0,
                "end_byte": 2,
                "output_width": 1,
            }
        },
        "framings": {"frame": {"prefix_hex": "aa", "suffix_hex": "55"}},
        "packet_fields": {
            "strength_field": {
                "offset": 0,
                "width": 1,
                "source": "ACTION_PARAMETER",
                "source_ref": "strength",
                "transforms": ["xor"],
            },
            "checksum_field": {
                "offset": 1,
                "width": 1,
                "source": "CHECKSUM",
                "source_ref": "checksum",
                "transforms": [],
            },
        },
        "packet_builders": {
            "builder": {
                "fields": ["strength_field", "checksum_field"],
                "framing": "frame",
                "checksum": "checksum",
            }
        },
        "authentications": {"none": {"method": "NONE", "selectors": []}},
        "bufferings": {"datagram": {"mode": "DATAGRAM"}},
        "parser_fields": {
            "state": {
                "offset": 0,
                "width": 1,
                "target_selector": "user_state",
                "transforms": [],
            }
        },
        "notification_parsers": {"parser": {"buffering": "datagram", "fields": ["state"]}},
        "timings": {
            "movement": {
                "repeat_count": 3,
                "repeat_interval_ms": 100,
                "cancellation": "AFTER_FRAME",
                "release": "STOP_ACTION",
                "release_action": "stop",
            }
        },
        "lifecycles": {"command": {"phases": ["CONNECT", "START_NOTIFY", "WRITE", "DISCONNECT"]}},
        "transports": {
            "transport": {
                "characteristic": "write",
                "write_mode": "WITHOUT_RESPONSE",
                "packet_builder": "builder",
                "notification_parser": "parser",
                "authentication": "none",
                "timing": "movement",
                "lifecycle": "command",
            }
        },
        "action_parameters": {"strength": {"action": "raise", "values": [1, 2]}},
        "action_mappings": {
            "raise_mapping": {
                "protocol": "protocol",
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
    _add_stop_mapping(data, "protocol")
    return data


def _add_stop_mapping(data: dict[str, object], protocol: str) -> None:
    for collection, key, value in (
        ("expected_action_rules", "expect_stop", {"protocol": protocol, "action": "stop", "when": {"op": "always"}}),
        ("timings", "stop_timing", {"repeat_count": 1, "repeat_interval_ms": 0, "cancellation": "AFTER_FRAME", "release": "NONE"}),
        ("packet_fields", "stop_field", {"offset": 0, "width": 1, "source": "CONSTANT", "constant_hex": "00", "transforms": []}),
        ("packet_builders", "stop_builder", {"fields": ["stop_field"], "framing": "frame"}),
        ("transports", "stop_transport", {"characteristic": "write", "write_mode": "WITHOUT_RESPONSE", "packet_builder": "stop_builder", "timing": "stop_timing", "lifecycle": "command"}),
        ("action_mappings", "stop_mapping", {"protocol": protocol, "action": "stop", "transport": "stop_transport", "when": {"op": "always"}}),
    ):
        target = data[collection]
        assert isinstance(target, dict)
        target[key] = value


def _load(data: dict[str, object] | None = None) -> v1.FinalProtocolIRDocument:
    return v1._parse_final_ir_structure(json.loads(json.dumps(data or _document())))


def _authorized_document(
    source: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, str]]:
    data = source or _document()
    semantic = core._semantic_data(_load(data))
    pointers = sorted(core._semantic_leaf_pointers(semantic))
    artifact = core.build_artifact_identity(
        package_name="synthetic.protocol",
        version_code="1",
        version_name="1.0",
        artifact_digest="a" * 64,
    )
    member = "evidence/synthetic.txt"
    member_digest = hashlib.sha256(b"synthetic").hexdigest()
    attestations = []
    for index, pointer in enumerate(pointers):
        value = core._resolve_semantic_pointer(semantic, pointer)
        attestations.append(
            {
                "id": f"claim-{index}",
                "owner": artifact.artifact_digest,
                "member": member,
                "member_sha256": member_digest,
                "start_byte": index,
                "end_byte": index + 1,
                "ir_pointer": pointer,
                "representation": "utf8",
                "value_sha256": hashlib.sha256(core._canonical_json(value)).hexdigest(),
            }
        )
    attestations.sort(key=lambda item: str(item["id"]).encode())
    receipt_data: dict[str, object] = {
        "accepted": True,
        "bundle_sha256": "b" * 64,
        "contract_revision": core.SUPPORTED_CONTRACT_REVISION,
        "declared_members": 1,
        "dependency_digests": {
            name: str(index) * 64 for index, name in enumerate(core._DEPENDENCY_NAMES, start=1)
        },
        "diagnostics": [],
        "discovered_members": 1,
        "evidence_anchors_checked": len(attestations),
        "report_manifest_sha256": "c" * 64,
        "source_unchanged": True,
        "validated_artifact_identity": artifact.to_data(),
        "validated_evidence_anchors": attestations,
        "validated_evidence_members": [
            {
                "member": member,
                "owner": artifact.artifact_digest,
                "sha256": member_digest,
            }
        ],
        "validated_root_evidence": [],
        "validation_profile": core.BOUND_VALIDATION_PROFILE,
        "validator_revision": core.SUPPORTED_VALIDATOR_REVISION,
    }
    receipt_id = hashlib.sha256(core._canonical_json(receipt_data)).hexdigest()
    receipt_data["validation_receipt_sha256"] = receipt_id
    dependency_digests = receipt_data["dependency_digests"]
    assert isinstance(dependency_digests, dict)
    report = core.bind_validator_receipt(
        core._canonical_json(receipt_data),
        trusted_validator_revision=core.SUPPORTED_VALIDATOR_REVISION,
        trusted_contract_revision=core.SUPPORTED_CONTRACT_REVISION,
        trusted_dependency_digests=dependency_digests,
        trusted_receipt_sha256=receipt_id,
    )
    package_id, package = core.build_source_package(artifact, report)
    file_id, evidence_file = core.build_evidence_file(
        package=package_id, member=member, sha256=member_digest
    )
    evidence_anchors = {}
    source_sets = {}
    evidence_bindings = {}
    for attestation in attestations:
        anchor_id, anchor = core.build_evidence_anchor(
            id=str(attestation["id"]),
            file=file_id,
            start_byte=int(attestation["start_byte"]),
            end_byte=int(attestation["end_byte"]),
            ir_pointer=str(attestation["ir_pointer"]),
            representation="utf8",
            value_sha256=str(attestation["value_sha256"]),
        )
        source_set_id, source_set = core.build_source_set(package=package_id, anchors=(anchor_id,))
        binding_id, binding = core.build_evidence_binding(
            target=str(attestation["ir_pointer"]), source_sets=(source_set_id,)
        )
        evidence_anchors[anchor_id] = anchor.to_data()
        source_sets[source_set_id] = source_set.to_data()
        evidence_bindings[binding_id] = binding.to_data()
    data["source_packages"] = {package_id: package.to_data()}
    data["evidence_files"] = {file_id: evidence_file.to_data()}
    data["evidence_anchors"] = evidence_anchors
    data["source_sets"] = source_sets
    data["evidence_bindings"] = evidence_bindings
    return data, {receipt_id: report.bundle_sha256}


def test_final_v1_covers_every_required_domain_and_schema_is_strict() -> None:
    data = _document()
    document = _load(data)

    Draft202012Validator(final_schema_document()).validate(data)
    assert document.domain_closure.domains == FINAL_DOMAIN_COLLECTIONS
    assert set(document.semantic_collection_names) == {
        *FINAL_DOMAIN_COLLECTIONS,
        "domain_closure",
    }
    assert dumps_final_ir(document).endswith(b"\n")


def test_final_loader_rejects_duplicate_keys_before_semantic_validation() -> None:
    payload = '{"schema_revision":"first","schema_revision":"second"}'

    with pytest.raises(IRValidationError) as caught:
        loads_final_ir(payload)

    assert caught.value.diagnostics[0].code == "duplicate_object_key"


def test_final_definition_maps_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _document()
    monkeypatch.setattr(v1, "_MAX_DEFINITIONS", 1)

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "definition_map_too_large"


def test_v05_loader_remains_strictly_backwards_compatible() -> None:
    old = {
        "schema_revision": core.SCHEMA_REVISION,
        "source_packages": {},
        "evidence_files": {},
        "evidence_anchors": {},
        "source_sets": {},
        "evidence_bindings": {},
        "variant_spaces": {},
        "protocols": {},
        "actions": {},
        "expected_action_rules": {},
        "command_bindings": {},
    }

    assert core._parse_ir_structure(old).schema_revision == core.SCHEMA_REVISION
    with pytest.raises(IRValidationError) as caught:
        v1._parse_final_ir_structure(old)
    assert caught.value.diagnostics[0].code == "missing_property"


def test_domain_closure_rejects_missing_or_unmodeled_domains() -> None:
    data = _document()
    closure = data["domain_closure"]
    assert isinstance(closure, dict)
    closure["unmodeled_paths"] = ["/commands/0"]

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "domain_not_closed"


def test_final_universe_expands_selectors_and_action_parameters_exactly_once() -> None:
    document = _load()

    result = validate_final_universe(document)

    assert result.is_valid
    assert len(result.expected) == 6
    assert result.expected == result.actual


def test_final_universe_rejects_duplicate_and_missing_mappings() -> None:
    data = _document()
    mappings = data["action_mappings"]
    assert isinstance(mappings, dict)
    mappings["duplicate"] = copy.deepcopy(mappings["raise_mapping"])

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "duplicate_action_mapping"


def test_action_mapping_expansion_is_bounded_when_expected_universe_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _document()
    data["expected_action_rules"] = {}
    monkeypatch.setattr(v1, "_MAX_DOMAIN_EXPANSIONS", 1)

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == "universe_too_large"


def test_every_final_semantic_leaf_requires_exact_evidence() -> None:
    document = _load()
    pointers = set(core._semantic_leaf_pointers(core._semantic_data(document)))

    assert "/gatt_services/service/uuid" in pointers
    assert "/packet_fields/strength_field/source" in pointers
    assert "/domain_closure/status" in pointers
    with pytest.raises(IRValidationError) as caught:
        parse_final_ir(json.loads(json.dumps(_document())), trusted_receipts={})
    assert caught.value.diagnostics[0].code == "missing_evidence_binding"
    assert {diagnostic.path for diagnostic in caught.value.diagnostics} == {
        pointer
        for pointer in pointers
        if not pointer.startswith("/domain_closure/") and not pointer.endswith("/@key")
    }


def test_final_document_authorizes_exact_once_evidence_for_every_domain() -> None:
    data, trusted = _authorized_document()
    Draft202012Validator(final_schema_document()).validate(data)

    document = parse_final_ir(json.loads(json.dumps(data)), trusted_receipts=trusted)

    assert document.schema_revision == FINAL_SCHEMA_REVISION
    assert validate_final_universe(document).is_valid


@pytest.mark.parametrize("value", ["ABCD", "1234ABCD", "12345678-1234-ABCD-5678-123456789ABC"])
def test_gatt_uuid_accepts_supported_representations(value: str) -> None:
    service = v1._parse_gatt_service({"uuid": value, "role": "CONTROL"}, "$.service")
    assert service.uuid == value.lower()
    characteristic = v1._parse_gatt_characteristic(
        {"service": "service", "uuid": value, "roles": ["WRITE"], "write_modes": []},
        "$.characteristic",
    )
    assert characteristic.uuid == value.lower()


@pytest.mark.parametrize("value", ["not-a-uuid", "abc", "0x1234", "123456789", "1234\n"])
def test_gatt_uuid_rejects_invalid_endpoint(value: str) -> None:
    with pytest.raises(IRValidationError, match="invalid_gatt_uuid"):
        v1._parse_gatt_service({"uuid": value, "role": "CONTROL"}, "$.service")
    with pytest.raises(IRValidationError, match="invalid_gatt_uuid"):
        v1._parse_gatt_characteristic(
            {"service": "service", "uuid": value, "roles": ["WRITE"], "write_modes": []},
            "$.characteristic",
        )


@pytest.mark.parametrize("constant", ["ff", "ffffff"])
def test_packet_constant_must_match_declared_width(constant: str) -> None:
    with pytest.raises(IRValidationError, match="invalid_packet_field_width"):
        v1._parse_packet_field(
            {"offset": 0, "width": 2, "source": "CONSTANT", "constant_hex": constant,
             "transforms": []},
            "$.field",
        )


def test_fixed_length_parser_rejects_field_beyond_buffer() -> None:
    data = _document()
    data["bufferings"] = {"datagram": {"mode": "FIXED_LENGTH", "size": 1}}
    fields = data["parser_fields"]
    assert isinstance(fields, dict)
    fields["state"]["offset"] = 1
    with pytest.raises(IRValidationError, match="parser_field_out_of_bounds"):
        _load(data)
    fields["state"]["offset"] = 0
    _load(data)


@pytest.mark.parametrize("mutation", ["missing", "other_protocol", "profile", "parameters"])
def test_release_requires_unique_mapping_for_same_protocol_and_profile(mutation: str) -> None:
    data = _document()
    mappings = data["action_mappings"]
    rules = data["expected_action_rules"]
    assert isinstance(mappings, dict) and isinstance(rules, dict)
    if mutation == "missing":
        del mappings["stop_mapping"]
        del rules["expect_stop"]
    elif mutation == "other_protocol":
        protocols = data["protocols"]
        assert isinstance(protocols, dict)
        protocols["other"] = {"variant_space": "variants"}
        mappings["stop_mapping"]["protocol"] = "other"
        rules["expect_stop"]["protocol"] = "other"
    elif mutation == "profile":
        predicate = {"op": "eq", "dimension": "model", "value": "alpha"}
        mappings["stop_mapping"]["when"] = predicate
        rules["expect_stop"]["when"] = predicate
    else:
        parameters = data["action_parameters"]
        assert isinstance(parameters, dict)
        parameters["stop_mode"] = {"action": "stop", "values": [1, 2]}
    with pytest.raises(IRValidationError, match="unresolved_release_action"):
        _load(data)


def test_notification_parser_accepts_indicate_role() -> None:
    data = _document()
    characteristics = data["gatt_characteristics"]
    assert isinstance(characteristics, dict)
    characteristics["write"]["roles"] = ["WRITE", "INDICATE"]
    _load(data)


def test_final_markdown_is_deterministic_and_rejects_drift() -> None:
    document = _load()
    rendered = render_final_ir_markdown(document)

    assert validate_final_ir_markdown(document, rendered) == final_semantic_fingerprint(document)
    assert "## Gatt services" in rendered
    assert "## Domain closure" in rendered
    with pytest.raises(IRValidationError) as caught:
        validate_final_ir_markdown(document, rendered.replace("## Timings", "## Timing notes"))
    assert caught.value.diagnostics[0].code == "markdown_render_mismatch"


@pytest.mark.parametrize(
    ("path", "mutation", "code"),
    [
        (("packet_fields", "checksum_field", "width"), 2, "checksum_field_width_mismatch"),
        (("packet_fields", "checksum_field", "offset"), 0, "overlapping_packet_fields"),
        (("gatt_characteristics", "write", "roles"), ["WRITE"], "notification_role_missing"),
        (
            ("packet_fields", "strength_field"),
            {"offset": 0, "width": 1, "source": "CONSTANT", "transforms": []},
            "invalid_packet_field_source",
        ),
        (
            ("bufferings", "datagram"),
            {"mode": "FIXED_LENGTH"},
            "invalid_buffering_shape",
        ),
        (
            ("transports", "transport", "write_mode"),
            "WITH_RESPONSE",
            "unsupported_write_mode",
        ),
    ],
)
def test_final_domains_fail_closed_on_incoherent_shapes(
    path: tuple[str, ...], mutation: object, code: str
) -> None:
    data = _document()
    target: object = data
    for token in path[:-1]:
        assert isinstance(target, dict)
        target = target[token]
    assert isinstance(target, dict)
    target[path[-1]] = mutation

    with pytest.raises(IRValidationError) as caught:
        _load(data)

    assert caught.value.diagnostics[0].code == code
