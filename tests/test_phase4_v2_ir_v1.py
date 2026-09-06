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
        "transforms": {
            "xor": {"operation": "XOR", "operand": 1},
            "state_lookup": {
                "operation": "LOOKUP",
                "lookup": [
                    [value, "idle"]
                    for value in sorted(
                        range(256), key=lambda value: core._canonical_json([value, "idle"])
                    )
                ],
            },
        },
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
                "transforms": ["state_lookup"],
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
        (
            "expected_action_rules",
            "expect_stop",
            {"protocol": protocol, "action": "stop", "when": {"op": "always"}},
        ),
        (
            "timings",
            "stop_timing",
            {
                "repeat_count": 1,
                "repeat_interval_ms": 0,
                "cancellation": "AFTER_FRAME",
                "release": "NONE",
            },
        ),
        (
            "packet_fields",
            "stop_field",
            {"offset": 0, "width": 1, "source": "CONSTANT", "constant_hex": "00", "transforms": []},
        ),
        ("packet_builders", "stop_builder", {"fields": ["stop_field"], "framing": "frame"}),
        (
            "transports",
            "stop_transport",
            {
                "characteristic": "write",
                "write_mode": "WITHOUT_RESPONSE",
                "packet_builder": "stop_builder",
                "timing": "stop_timing",
                "lifecycle": "command",
            },
        ),
        (
            "action_mappings",
            "stop_mapping",
            {
                "protocol": protocol,
                "action": "stop",
                "transport": "stop_transport",
                "when": {"op": "always"},
            },
        ),
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


def test_binary_discovery_matcher_requires_keyed_hex_bytes() -> None:
    with pytest.raises(IRValidationError, match="requires its numeric manufacturer ID key"):
        v1._parse_discovery_matcher(
            {"field": "MANUFACTURER_DATA", "operation": "EQUALS", "value_hex": "0102"},
            "$.matcher",
        )
    with pytest.raises(IRValidationError, match="invalid_hex"):
        v1._parse_discovery_matcher(
            {
                "field": "SERVICE_DATA",
                "operation": "EQUALS",
                "key": "1234",
                "value_hex": "raw bytes",
            },
            "$.matcher",
        )

    matcher = v1._parse_discovery_matcher(
        {
            "field": "SERVICE_DATA",
            "operation": "PREFIX",
            "key": "12345678-1234-ABCD-5678-123456789ABC",
            "value_hex": "0102",
        },
        "$.matcher",
    )
    assert matcher.to_data() == {
        "field": "SERVICE_DATA",
        "operation": "PREFIX",
        "key": "12345678-1234-abcd-5678-123456789abc",
        "value_hex": "0102",
    }

    short_key = v1._parse_discovery_matcher(
        {
            "field": "SERVICE_DATA",
            "operation": "EQUALS",
            "key": "1234",
            "value_hex": "01",
        },
        "$.matcher",
    )
    assert short_key.key == "00001234-0000-1000-8000-00805f9b34fb"
    full_key = v1._parse_discovery_matcher(
        {
            "field": "SERVICE_DATA",
            "operation": "EQUALS",
            "key": "00001234-0000-1000-8000-00805f9b34fb",
            "value_hex": "01",
        },
        "$.matcher",
    )
    assert v1._matchers_may_share_value(short_key, full_key)


def test_discovery_regex_rejects_backtracking_grammar() -> None:
    with pytest.raises(IRValidationError, match="unsafe_discovery_regex"):
        v1._parse_discovery_matcher(
            {"field": "DEVICE_NAME", "operation": "REGEX", "value": "(a+)+b"},
            "$.matcher",
        )

    matcher = v1._parse_discovery_matcher(
        {"field": "DEVICE_NAME", "operation": "REGEX", "value": "^Bed[0-9]$"},
        "$.matcher",
    )
    assert matcher.value == "^Bed[0-9]$"


@pytest.mark.parametrize("constant", ["ff", "ffffff"])
def test_packet_constant_must_match_declared_width(constant: str) -> None:
    with pytest.raises(IRValidationError, match="invalid_packet_field_width"):
        v1._parse_packet_field(
            {
                "offset": 0,
                "width": 2,
                "source": "CONSTANT",
                "constant_hex": constant,
                "transforms": [],
            },
            "$.field",
        )


def test_counter_source_is_rejected_until_its_lifecycle_is_modeled() -> None:
    data = _document()
    fields = data["packet_fields"]
    assert isinstance(fields, dict)
    fields["strength_field"] = {
        "offset": 0,
        "width": 1,
        "source": "COUNTER",
        "source_ref": "sequence",
        "transforms": [],
    }

    with pytest.raises(IRValidationError, match="unknown_domain_enum"):
        _load(data)


@pytest.mark.parametrize("algorithm", ["CRC8", "CRC16", "CUSTOM"])
def test_underspecified_checksum_algorithms_are_rejected(algorithm: str) -> None:
    data = _document()
    checksums = data["checksums"]
    assert isinstance(checksums, dict)
    checksums["checksum"]["algorithm"] = algorithm

    with pytest.raises(IRValidationError, match="unknown_domain_enum"):
        _load(data)


@pytest.mark.parametrize("operand", [True, "1", -1, 2**63])
def test_arithmetic_transform_requires_a_nonnegative_integer(operand: object) -> None:
    data = _document()
    transforms = data["transforms"]
    assert isinstance(transforms, dict)
    transforms["xor"]["operand"] = operand

    with pytest.raises(IRValidationError, match="expected_integer|integer_out_of_range"):
        _load(data)


def test_arithmetic_transform_operand_must_fit_each_target_field() -> None:
    data = _document()
    transforms = data["transforms"]
    assert isinstance(transforms, dict)
    transforms["xor"]["operand"] = 256

    with pytest.raises(IRValidationError, match="transform_operand_out_of_range"):
        _load(data)


def test_packet_lookup_must_cover_every_source_domain_value() -> None:
    data = _document()
    transforms = data["transforms"]
    fields = data["packet_fields"]
    assert isinstance(transforms, dict)
    assert isinstance(fields, dict)
    transforms["strength_lookup"] = {"operation": "LOOKUP", "lookup": [[1, 10]]}
    fields["strength_field"]["transforms"] = ["strength_lookup"]

    with pytest.raises(IRValidationError, match="lookup_domain_incomplete"):
        _load(data)

    transforms["strength_lookup"]["lookup"].append([2, 20])
    _load(data)


def test_packet_lookup_uses_domain_after_arithmetic_transforms() -> None:
    data = _document()
    parameters = data["action_parameters"]
    transforms = data["transforms"]
    fields = data["packet_fields"]
    assert isinstance(parameters, dict)
    assert isinstance(transforms, dict)
    assert isinstance(fields, dict)
    parameters["strength"]["values"] = [1]
    transforms["add"] = {"operation": "ADD", "operand": 1}
    transforms["strength_lookup"] = {"operation": "LOOKUP", "lookup": [[2, 10]]}
    fields["strength_field"]["transforms"] = ["add", "strength_lookup"]

    _load(data)


@pytest.mark.parametrize("value", [256, -1, "not-a-byte"])
def test_packet_field_values_must_fit_their_destination_width(value: object) -> None:
    data = _document()
    parameters = data["action_parameters"]
    assert isinstance(parameters, dict)
    strength = parameters["strength"]
    assert isinstance(strength, dict)
    strength["values"] = [value]

    with pytest.raises(IRValidationError, match="packet_field_value_out_of_range"):
        _load(data)


def test_packet_field_transforms_must_preserve_destination_width() -> None:
    data = _document()
    parameters = data["action_parameters"]
    transforms = data["transforms"]
    fields = data["packet_fields"]
    assert (
        isinstance(parameters, dict) and isinstance(transforms, dict) and isinstance(fields, dict)
    )
    strength = parameters["strength"]
    assert isinstance(strength, dict)
    strength["values"] = [255]
    transforms["add"] = {"operation": "ADD", "operand": 1}
    fields["strength_field"]["transforms"] = ["add"]

    with pytest.raises(IRValidationError, match="packet_field_value_out_of_range"):
        _load(data)


def test_constant_and_checksum_transforms_must_preserve_destination_width() -> None:
    data = _document()
    transforms = data["transforms"]
    fields = data["packet_fields"]
    assert isinstance(transforms, dict) and isinstance(fields, dict)
    transforms["add"] = {"operation": "ADD", "operand": 1}
    fields["stop_field"]["constant_hex"] = "ff"
    fields["stop_field"]["transforms"] = ["add"]

    with pytest.raises(IRValidationError, match="packet_field_value_out_of_range"):
        _load(data)

    data = _document()
    transforms = data["transforms"]
    fields = data["packet_fields"]
    assert isinstance(transforms, dict) and isinstance(fields, dict)
    transforms["checksum_lookup"] = {
        "operation": "LOOKUP",
        "lookup": [[value, "not-a-byte"] for value in range(256)],
    }
    fields["checksum_field"]["transforms"] = ["checksum_lookup"]

    with pytest.raises(IRValidationError, match="packet_field_value_out_of_range"):
        _load(data)


def test_multibyte_dynamic_packet_field_requires_explicit_byte_order() -> None:
    data = _document()
    parameters = data["action_parameters"]
    fields = data["packet_fields"]
    transforms = data["transforms"]
    assert isinstance(parameters, dict) and isinstance(fields, dict)
    assert isinstance(transforms, dict)
    parameters["strength"]["values"] = [258]
    fields["strength_field"]["width"] = 2

    with pytest.raises(IRValidationError, match="packet_field_byte_order_missing"):
        _load(data)

    transforms["little"] = {"operation": "LITTLE_ENDIAN"}
    fields["strength_field"]["transforms"] = ["little"]
    fields["checksum_field"]["offset"] = 2
    _load(data)


def test_duplicate_discovery_domain_cannot_select_different_protocols() -> None:
    data = _document()
    protocols = data["protocols"]
    selections = data["selection_rules"]
    discoveries = data["discovery_rules"]
    assert isinstance(protocols, dict)
    assert isinstance(selections, dict)
    assert isinstance(discoveries, dict)
    protocols["other"] = {"variant_space": "variants"}
    selections["select_other"] = {"protocol": "other", "when": {"op": "always"}}
    discoveries["discover_other"] = {
        "selection_rule": "select_other",
        "matchers": copy.deepcopy(discoveries["discover"]["matchers"]),
    }

    with pytest.raises(IRValidationError, match="ambiguous_discovery_rule"):
        _load(data)


def test_partially_overlapping_discovery_domains_cannot_select_different_protocols() -> None:
    data = _document()
    protocols = data["protocols"]
    selections = data["selection_rules"]
    discoveries = data["discovery_rules"]
    assert isinstance(protocols, dict)
    assert isinstance(selections, dict)
    assert isinstance(discoveries, dict)
    protocols["other"] = {"variant_space": "variants"}
    selections["select_other"] = {"protocol": "other", "when": {"op": "always"}}
    discoveries["discover_other"] = {
        "selection_rule": "select_other",
        "matchers": [
            *copy.deepcopy(discoveries["discover"]["matchers"]),
            {"field": "DEVICE_NAME", "operation": "PREFIX", "value": "Bed"},
        ],
    }

    with pytest.raises(IRValidationError, match="ambiguous_discovery_rule"):
        _load(data)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            {"field": "SERVICE_UUID", "operation": "EQUALS", "value": "1234"},
            {"field": "SERVICE_UUID", "operation": "EQUALS", "value": "5678"},
        ),
        (
            {
                "field": "MANUFACTURER_DATA",
                "operation": "EQUALS",
                "key": 1,
                "value_hex": "01",
            },
            {
                "field": "MANUFACTURER_DATA",
                "operation": "EQUALS",
                "key": 2,
                "value_hex": "02",
            },
        ),
        (
            {
                "field": "SERVICE_DATA",
                "operation": "EQUALS",
                "key": "1234",
                "value_hex": "01",
            },
            {
                "field": "SERVICE_DATA",
                "operation": "EQUALS",
                "key": "5678",
                "value_hex": "02",
            },
        ),
    ],
)
def test_coexistent_advertisement_entries_cannot_select_different_protocols(
    first: dict[str, object], second: dict[str, object]
) -> None:
    data = _document()
    protocols = data["protocols"]
    selections = data["selection_rules"]
    discoveries = data["discovery_rules"]
    assert isinstance(protocols, dict)
    assert isinstance(selections, dict)
    assert isinstance(discoveries, dict)
    protocols["other"] = {"variant_space": "variants"}
    selections["select_other"] = {"protocol": "other", "when": {"op": "always"}}
    discoveries["discover"]["matchers"] = [first]
    discoveries["discover_other"] = {
        "selection_rule": "select_other",
        "matchers": [second],
    }

    with pytest.raises(IRValidationError, match="ambiguous_discovery_rule"):
        _load(data)


def test_discovery_selection_rule_must_match_a_valid_profile() -> None:
    data = _document()
    selections = data["selection_rules"]
    assert isinstance(selections, dict)
    selections["select"]["when"] = {"op": "never"}

    with pytest.raises(IRValidationError, match="unreachable_discovery_selection"):
        _load(data)


def test_packet_builder_checksum_must_match_its_checksum_field() -> None:
    data = _document()
    checksums = data["checksums"]
    fields = data["packet_fields"]
    assert isinstance(checksums, dict)
    assert isinstance(fields, dict)
    checksums["other"] = copy.deepcopy(checksums["checksum"])
    fields["checksum_field"]["source_ref"] = "other"

    with pytest.raises(IRValidationError, match="packet_builder_checksum_mismatch"):
        _load(data)


def test_packet_builder_checksum_requires_a_matching_output_field() -> None:
    data = _document()
    builders = data["packet_builders"]
    assert isinstance(builders, dict)
    builders["builder"]["fields"] = ["strength_field"]

    with pytest.raises(IRValidationError, match="packet_builder_checksum_mismatch"):
        _load(data)


def test_packet_builder_checksum_range_must_be_emitted_by_builder() -> None:
    data = _document()
    checksums = data["checksums"]
    assert isinstance(checksums, dict)
    checksums["checksum"]["end_byte"] = 100

    with pytest.raises(IRValidationError, match="checksum_range_out_of_bounds"):
        _load(data)


def test_packet_builder_checksum_range_must_exclude_output_field() -> None:
    data = _document()
    checksums = data["checksums"]
    assert isinstance(checksums, dict)
    checksums["checksum"]["end_byte"] = 2

    with pytest.raises(IRValidationError, match="checksum_range_includes_output"):
        _load(data)


def test_packet_builder_must_emit_its_framing_length_field() -> None:
    data = _document()
    framings = data["framings"]
    assert isinstance(framings, dict)
    framings["frame"]["length_field"] = "strength_field"
    builders = data["packet_builders"]
    assert isinstance(builders, dict)
    builders["stop_builder"]["framing"] = "frame"

    with pytest.raises(IRValidationError, match="packet_builder_length_field_missing"):
        _load(data)


def test_packet_builder_fields_must_not_leave_undefined_bytes() -> None:
    data = _document()
    fields = data["packet_fields"]
    assert isinstance(fields, dict)
    fields["checksum_field"]["offset"] = 2

    with pytest.raises(IRValidationError, match="packet_builder_field_gap"):
        _load(data)


@pytest.mark.parametrize(
    ("offset", "width"),
    [(v1.MAX_PACKET_BYTES, 1), (0, v1.MAX_PACKET_BYTES + 1)],
)
def test_packet_fields_must_fit_the_ble_value_limit(offset: int, width: int) -> None:
    with pytest.raises(IRValidationError, match="packet_field_too_large"):
        v1._parse_packet_field(
            {
                "offset": offset,
                "width": width,
                "source": "ACTION_PARAMETER",
                "source_ref": "strength",
                "transforms": [],
            },
            "$.field",
        )


def test_framed_packet_must_fit_the_ble_value_limit() -> None:
    data = _document()
    framings = data["framings"]
    assert isinstance(framings, dict)
    framings["frame"]["prefix_hex"] = "aa" * (v1.MAX_PACKET_BYTES - 1)

    with pytest.raises(IRValidationError, match="packet_builder_too_large"):
        _load(data)


@pytest.mark.parametrize(
    "exchange",
    [
        {},
        {"request_builder": "builder"},
        {"response_parser": "parser"},
    ],
)
def test_challenge_response_requires_executable_exchange(exchange: dict[str, str]) -> None:
    data = _document()
    authentications = data["authentications"]
    assert isinstance(authentications, dict)
    authentications["none"] = {
        "method": "CHALLENGE_RESPONSE",
        "selectors": ["remote_code"],
        **exchange,
    }

    with pytest.raises(IRValidationError, match="invalid_authentication_shape"):
        _load(data)


def test_custom_authentication_is_rejected_until_its_mechanics_are_modeled() -> None:
    data = _document()
    authentications = data["authentications"]
    assert isinstance(authentications, dict)
    authentications["none"] = {"method": "CUSTOM", "selectors": ["remote_code"]}

    with pytest.raises(IRValidationError, match="unsupported_authentication_method"):
        _load(data)


def test_nontrivial_authentication_requires_lifecycle_phase() -> None:
    data = _document()
    authentications = data["authentications"]
    assert isinstance(authentications, dict)
    authentications["none"] = {
        "method": "PIN",
        "selectors": ["remote_code"],
        "request_builder": "builder",
    }

    with pytest.raises(IRValidationError, match="authentication_lifecycle_missing_phase"):
        _load(data)


def test_pin_requires_executable_exchange() -> None:
    data = _document()
    authentications = data["authentications"]
    assert isinstance(authentications, dict)
    authentications["none"] = {
        "method": "PIN",
        "selectors": ["remote_code"],
    }

    with pytest.raises(IRValidationError, match="invalid_authentication_shape"):
        _load(data)


def test_session_token_is_rejected_until_token_extraction_is_modeled() -> None:
    data = _document()
    authentications = data["authentications"]
    assert isinstance(authentications, dict)
    authentications["none"] = {
        "method": "SESSION_TOKEN",
        "selectors": ["remote_code"],
        "request_builder": "builder",
        "response_parser": "parser",
    }

    with pytest.raises(IRValidationError, match="unsupported_authentication_method"):
        _load(data)


def test_pin_request_builder_must_emit_authentication_value() -> None:
    data = _document()
    authentications = data["authentications"]
    lifecycles = data["lifecycles"]
    assert isinstance(authentications, dict) and isinstance(lifecycles, dict)
    authentications["none"] = {
        "method": "PIN",
        "selectors": ["remote_code"],
        "request_builder": "builder",
    }
    lifecycles["command"]["phases"] = [
        "CONNECT",
        "AUTHENTICATE",
        "START_NOTIFY",
        "WRITE",
        "DISCONNECT",
    ]

    with pytest.raises(IRValidationError, match="authentication_exchange_missing_credential"):
        _load(data)


@pytest.mark.parametrize("builder_target", ["command", "authentication"])
def test_transport_builders_require_the_attached_non_none_authentication(
    builder_target: str,
) -> None:
    data = _document()
    fields = data["packet_fields"]
    builders = data["packet_builders"]
    authentications = data["authentications"]
    lifecycles = data["lifecycles"]
    transports = data["transports"]
    assert isinstance(fields, dict) and isinstance(builders, dict)
    assert isinstance(authentications, dict) and isinstance(lifecycles, dict)
    assert isinstance(transports, dict)
    fields["command_auth"] = {
        "offset": 2,
        "width": 1,
        "source": "AUTHENTICATION",
        "source_ref": "auth",
        "transforms": [],
    }
    fields["request_auth"] = {
        "offset": 0,
        "width": 1,
        "source": "AUTHENTICATION",
        "source_ref": "auth",
        "transforms": [],
    }
    builders["builder"]["fields"].append("command_auth")
    builders["auth_builder"] = {"fields": ["request_auth"], "framing": "frame"}
    authentications["auth"] = {
        "method": "PIN",
        "selectors": ["remote_code"],
        "request_builder": "auth_builder",
    }
    lifecycles["command"]["phases"] = [
        "CONNECT",
        "AUTHENTICATE",
        "START_NOTIFY",
        "WRITE",
        "DISCONNECT",
    ]
    transports["transport"]["authentication"] = "auth"
    target_field = "command_auth" if builder_target == "command" else "request_auth"
    fields[target_field]["source_ref"] = "none"

    with pytest.raises(IRValidationError, match="transport_authentication_field_mismatch"):
        _load(data)


def test_action_mapping_rejects_packet_parameter_for_another_action() -> None:
    data = _document()
    parameters = data["action_parameters"]
    assert isinstance(parameters, dict)
    parameters["strength"]["action"] = "stop"

    with pytest.raises(IRValidationError, match="action_mapping_parameter_mismatch"):
        _load(data)


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


def test_parser_outputs_must_belong_to_its_target_selector_domain() -> None:
    data = _document()
    fields = data["parser_fields"]
    assert isinstance(fields, dict)
    fields["state"]["transforms"] = []

    with pytest.raises(IRValidationError, match="parser_output_outside_selector_domain"):
        _load(data)


def test_parser_lookup_must_cover_every_reachable_raw_value() -> None:
    data = _document()
    transforms = data["transforms"]
    assert isinstance(transforms, dict)
    transforms["state_lookup"]["lookup"] = [[0, "idle"]]

    with pytest.raises(IRValidationError, match="lookup_domain_incomplete"):
        _load(data)


def test_parser_rejects_numeric_transform_after_string_lookup() -> None:
    data = _document()
    fields = data["parser_fields"]
    assert isinstance(fields, dict)
    fields["state"]["transforms"] = ["state_lookup", "xor"]

    with pytest.raises(IRValidationError, match="invalid_transform_input_domain"):
        _load(data)


def test_notification_parser_rejects_conflicting_targets() -> None:
    data = _document()
    fields = data["parser_fields"]
    parsers = data["notification_parsers"]
    assert isinstance(fields, dict) and isinstance(parsers, dict)
    fields["other_state"] = {
        "offset": 1,
        "width": 1,
        "target_selector": "user_state",
        "transforms": ["state_lookup"],
    }
    parsers["parser"]["fields"] = ["state", "other_state"]

    with pytest.raises(IRValidationError, match="duplicate_parser_target"):
        _load(data)


def test_length_prefixed_buffering_is_rejected_until_semantics_are_modeled() -> None:
    data = _document()
    data["bufferings"] = {"datagram": {"mode": "LENGTH_PREFIXED", "size": 1}}

    with pytest.raises(IRValidationError, match="unsupported_buffering_mode"):
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


def test_release_actions_must_terminate() -> None:
    data = _document()
    timings = data["timings"]
    assert isinstance(timings, dict)
    timings["stop_timing"] = {
        "repeat_count": 1,
        "repeat_interval_ms": 0,
        "cancellation": "AFTER_FRAME",
        "release": "STOP_ACTION",
        "release_action": "stop",
    }

    with pytest.raises(IRValidationError, match="cyclic_release_action"):
        _load(data)


def test_action_mapping_must_consume_each_action_parameter() -> None:
    data = _document()
    fields = data["packet_fields"]
    assert isinstance(fields, dict)
    fields["strength_field"] = {
        "offset": 0,
        "width": 1,
        "source": "CONSTANT",
        "constant_hex": "01",
        "transforms": [],
    }

    with pytest.raises(IRValidationError, match="unconsumed_action_parameter"):
        _load(data)


def test_action_mapping_predicate_can_consume_an_action_parameter() -> None:
    data = _document()
    fields = data["packet_fields"]
    mappings = data["action_mappings"]
    assert isinstance(fields, dict) and isinstance(mappings, dict)
    fields["strength_field"] = {
        "offset": 0,
        "width": 1,
        "source": "CONSTANT",
        "constant_hex": "01",
        "transforms": [],
    }
    mappings["raise_mapping"]["when"] = {
        "op": "eq",
        "dimension": "strength",
        "value": 1,
    }
    mappings["raise_two"] = {
        "protocol": "protocol",
        "action": "raise",
        "transport": "transport",
        "when": {"op": "eq", "dimension": "strength", "value": 2},
    }

    _load(data)


def test_notification_parser_accepts_indicate_role() -> None:
    data = _document()
    characteristics = data["gatt_characteristics"]
    assert isinstance(characteristics, dict)
    characteristics["write"]["roles"] = ["WRITE", "INDICATE"]
    _load(data)


def test_notification_parser_requires_start_notify_lifecycle_phase() -> None:
    data = _document()
    lifecycles = data["lifecycles"]
    assert isinstance(lifecycles, dict)
    lifecycles["command"]["phases"] = ["CONNECT", "WRITE", "DISCONNECT"]

    with pytest.raises(IRValidationError, match="notification_lifecycle_missing_start"):
        _load(data)


@pytest.mark.parametrize(
    ("roles", "phases", "code"),
    [
        (
            ["WRITE"],
            ["CONNECT", "AUTHENTICATE", "START_NOTIFY", "WRITE", "DISCONNECT"],
            "notification_role_missing",
        ),
        (
            ["NOTIFY", "WRITE"],
            ["CONNECT", "AUTHENTICATE", "WRITE", "DISCONNECT"],
            "notification_lifecycle_missing_start",
        ),
    ],
)
def test_authentication_response_parser_requires_notification_channel(
    roles: list[str], phases: list[str], code: str
) -> None:
    data = _document()
    authentications = data["authentications"]
    transports = data["transports"]
    characteristics = data["gatt_characteristics"]
    lifecycles = data["lifecycles"]
    assert isinstance(authentications, dict) and isinstance(transports, dict)
    assert isinstance(characteristics, dict) and isinstance(lifecycles, dict)
    authentications["none"] = {
        "method": "CHALLENGE_RESPONSE",
        "selectors": ["remote_code"],
        "request_builder": "builder",
        "response_parser": "parser",
    }
    transports["transport"].pop("notification_parser")
    characteristics["write"]["roles"] = roles
    lifecycles["command"]["phases"] = phases

    with pytest.raises(IRValidationError, match=code):
        _load(data)


def test_authentication_builder_parameter_must_belong_to_mapped_action() -> None:
    data = _document()
    parameters = data["action_parameters"]
    fields = data["packet_fields"]
    builders = data["packet_builders"]
    authentications = data["authentications"]
    lifecycles = data["lifecycles"]
    assert isinstance(parameters, dict) and isinstance(fields, dict)
    assert isinstance(builders, dict) and isinstance(authentications, dict)
    assert isinstance(lifecycles, dict)
    parameters["stop_parameter"] = {"action": "stop", "values": [1]}
    fields["auth_value"] = {
        "offset": 0,
        "width": 1,
        "source": "AUTHENTICATION",
        "source_ref": "none",
        "transforms": [],
    }
    fields["wrong_parameter"] = {
        "offset": 1,
        "width": 1,
        "source": "ACTION_PARAMETER",
        "source_ref": "stop_parameter",
        "transforms": [],
    }
    builders["auth_builder"] = {
        "fields": ["auth_value", "wrong_parameter"],
        "framing": "frame",
    }
    authentications["none"] = {
        "method": "PIN",
        "selectors": ["remote_code"],
        "request_builder": "auth_builder",
    }
    lifecycles["command"]["phases"] = [
        "CONNECT",
        "AUTHENTICATE",
        "START_NOTIFY",
        "WRITE",
        "DISCONNECT",
    ]

    with pytest.raises(IRValidationError, match="action_mapping_parameter_mismatch"):
        _load(data)


@pytest.mark.parametrize("authentication_target", ["request_builder", "response_parser"])
def test_action_mapping_rejects_transport_selector_from_another_variant_space(
    authentication_target: str,
) -> None:
    data = _document()
    spaces = data["variant_spaces"]
    selectors = data["selectors"]
    fields = data["packet_fields"]
    assert isinstance(spaces, dict) and isinstance(selectors, dict) and isinstance(fields, dict)
    spaces["other"] = {"dimensions": {"other": [1]}, "constraints": []}
    selectors["other"] = {
        "variant_space": "other",
        "dimension": "other",
        "kind": "VARIANT",
        "values": [1],
    }
    transports = data["transports"]
    authentications = data["authentications"]
    lifecycles = data["lifecycles"]
    assert isinstance(transports, dict) and isinstance(authentications, dict)
    assert isinstance(lifecycles, dict)
    transport = transports["transport"]
    lifecycle = lifecycles["command"]
    assert isinstance(transport, dict) and isinstance(lifecycle, dict)
    lifecycle["phases"] = ["CONNECT", "AUTHENTICATE", "START_NOTIFY", "WRITE", "DISCONNECT"]
    auth: dict[str, object] = {"method": "PIN", "selectors": ["remote_code"]}
    if authentication_target == "request_builder":
        fields["auth_selector"] = {
            "offset": 0,
            "width": 1,
            "source": "SELECTOR",
            "source_ref": "other",
            "transforms": [],
        }
        builders = data["packet_builders"]
        assert isinstance(builders, dict)
        builders["auth_builder"] = {"fields": ["auth_selector"], "framing": "frame"}
        auth["request_builder"] = "auth_builder"
    else:
        transforms = data["transforms"]
        parser_fields = data["parser_fields"]
        parsers = data["notification_parsers"]
        assert isinstance(transforms, dict)
        assert isinstance(parser_fields, dict) and isinstance(parsers, dict)
        transforms["other_lookup"] = {
            "operation": "LOOKUP",
            "lookup": [[value, 1] for value in range(256)],
        }
        parser_fields["auth_state"] = {
            "offset": 0,
            "width": 1,
            "target_selector": "other",
            "transforms": ["other_lookup"],
        }
        parsers["auth_parser"] = {"buffering": "datagram", "fields": ["auth_state"]}
        auth["request_builder"] = "builder"
        auth["response_parser"] = "auth_parser"
    authentications["none"] = auth

    with pytest.raises(IRValidationError, match="action_mapping_selector_variant_space_mismatch"):
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
