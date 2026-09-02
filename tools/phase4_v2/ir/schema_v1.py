"""Pinned JSON Schema for the closed final Phase 4 protocol IR."""

from __future__ import annotations

import copy
from enum import StrEnum

from .schema import schema_document
from .v1 import (
    FINAL_DOMAIN_COLLECTIONS,
    FINAL_SCHEMA_REVISION,
    AuthenticationMethod,
    BufferingMode,
    CancellationMode,
    ChecksumAlgorithm,
    GattCharacteristicRole,
    GattServiceRole,
    LifecyclePhase,
    MatchField,
    MatchOperation,
    PacketFieldSource,
    ReleaseMode,
    SelectorKind,
    TransformOperation,
    WriteMode,
)

_REF = {"$ref": "#/$defs/identifier"}
_HEX = {"type": "string", "maxLength": 8192, "pattern": "^(?:[0-9a-f]{2})*$"}
_REFS = {
    "type": "array",
    "maxItems": 4096,
    "uniqueItems": True,
    "items": _REF,
}


def final_schema_document() -> dict[str, object]:
    """Return an isolated copy of the strict final-v1 schema."""

    base = schema_document()
    definitions = base["$defs"]
    assert isinstance(definitions, dict)
    definitions.update(_FINAL_DEFINITIONS)
    base["$id"] = f"https://local.invalid/schemas/{FINAL_SCHEMA_REVISION}.json"
    base["title"] = "Final Phase 4 protocol intermediate representation"
    base["required"] = [
        "schema_revision",
        "source_packages",
        "evidence_files",
        "evidence_anchors",
        "source_sets",
        "evidence_bindings",
        *FINAL_DOMAIN_COLLECTIONS,
        "domain_closure",
    ]
    properties = base["properties"]
    assert isinstance(properties, dict)
    properties.pop("command_bindings", None)
    properties["schema_revision"] = {"const": FINAL_SCHEMA_REVISION}
    for collection in FINAL_DOMAIN_COLLECTIONS:
        if collection not in properties:
            properties[collection] = {"$ref": f"#/$defs/{collection}_map"}
    properties["domain_closure"] = {"$ref": "#/$defs/domain_closure"}
    return copy.deepcopy(base)


def _enum(enum_type: type[StrEnum]) -> dict[str, object]:
    return {"enum": [item.value for item in enum_type]}


def _record(
    required: tuple[str, ...],
    properties: dict[str, object],
) -> dict[str, object]:
    return {
        "type": "object",
        "required": list(required),
        "properties": properties,
        "additionalProperties": False,
    }


def _map(definition: str) -> dict[str, object]:
    return {
        "type": "object",
        "propertyNames": _REF,
        "additionalProperties": {"$ref": f"#/$defs/{definition}"},
    }


_FINAL_DEFINITIONS: dict[str, object] = {
    "selectors_map": _map("selector"),
    "selector": _record(
        ("variant_space", "dimension", "kind", "values"),
        {
            "variant_space": _REF,
            "dimension": _REF,
            "kind": _enum(SelectorKind),
            "values": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100000,
                "uniqueItems": True,
                "items": {"$ref": "#/$defs/selector_scalar"},
            },
        },
    ),
    "selection_rules_map": _map("selection_rule"),
    "selection_rule": _record(
        ("protocol", "when"),
        {"protocol": _REF, "when": {"$ref": "#/$defs/predicate"}},
    ),
    "discovery_rules_map": _map("discovery_rule"),
    "discovery_rule": _record(
        ("selection_rule", "matchers"),
        {
            "selection_rule": _REF,
            "matchers": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4096,
                "items": {"$ref": "#/$defs/discovery_matcher"},
            },
        },
    ),
    "discovery_matcher": _record(
        ("field", "operation"),
        {
            "field": _enum(MatchField),
            "operation": _enum(MatchOperation),
            "value": {"type": "string", "minLength": 1, "maxLength": 4096},
        },
    ),
    "gatt_services_map": _map("gatt_service"),
    "gatt_service": _record(
        ("uuid", "role"),
        {
            "uuid": {"type": "string", "minLength": 1, "maxLength": 256},
            "role": _enum(GattServiceRole),
        },
    ),
    "gatt_characteristics_map": _map("gatt_characteristic"),
    "gatt_characteristic": _record(
        ("service", "uuid", "roles", "write_modes"),
        {
            "service": _REF,
            "uuid": {"type": "string", "minLength": 1, "maxLength": 256},
            "roles": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": _enum(GattCharacteristicRole),
            },
            "write_modes": {
                "type": "array",
                "uniqueItems": True,
                "items": _enum(WriteMode),
            },
        },
    ),
    "transforms_map": _map("transform"),
    "transform": _record(
        ("operation",),
        {
            "operation": _enum(TransformOperation),
            "operand": {"$ref": "#/$defs/selector_scalar"},
            "lookup": {
                "type": "array",
                "maxItems": 4096,
                "items": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"$ref": "#/$defs/selector_scalar"},
                },
            },
        },
    ),
    "checksums_map": _map("checksum"),
    "checksum": _record(
        ("algorithm", "start_byte", "end_byte", "output_width"),
        {
            "algorithm": _enum(ChecksumAlgorithm),
            "start_byte": {"type": "integer", "minimum": 0},
            "end_byte": {"type": "integer", "minimum": 1},
            "output_width": {"type": "integer", "minimum": 1},
        },
    ),
    "framings_map": _map("framing"),
    "framing": _record(
        ("prefix_hex", "suffix_hex"),
        {"prefix_hex": _HEX, "suffix_hex": _HEX, "length_field": _REF},
    ),
    "packet_fields_map": _map("packet_field"),
    "packet_field": _record(
        ("offset", "width", "source", "transforms"),
        {
            "offset": {"type": "integer", "minimum": 0},
            "width": {"type": "integer", "minimum": 1},
            "source": _enum(PacketFieldSource),
            "source_ref": _REF,
            "constant_hex": _HEX,
            "transforms": _REFS,
        },
    ),
    "packet_builders_map": _map("packet_builder"),
    "packet_builder": _record(
        ("fields", "framing"),
        {"fields": {**_REFS, "minItems": 1}, "framing": _REF, "checksum": _REF},
    ),
    "authentications_map": _map("authentication"),
    "authentication": _record(
        ("method", "selectors"),
        {
            "method": _enum(AuthenticationMethod),
            "selectors": _REFS,
            "request_builder": _REF,
            "response_parser": _REF,
        },
    ),
    "bufferings_map": _map("buffering"),
    "buffering": _record(
        ("mode",),
        {
            "mode": _enum(BufferingMode),
            "size": {"type": "integer", "minimum": 1},
            "delimiter_hex": _HEX,
        },
    ),
    "parser_fields_map": _map("parser_field"),
    "parser_field": _record(
        ("offset", "width", "target_selector", "transforms"),
        {
            "offset": {"type": "integer", "minimum": 0},
            "width": {"type": "integer", "minimum": 1},
            "target_selector": _REF,
            "transforms": _REFS,
        },
    ),
    "notification_parsers_map": _map("notification_parser"),
    "notification_parser": _record(
        ("buffering", "fields"),
        {"buffering": _REF, "fields": {**_REFS, "minItems": 1}},
    ),
    "timings_map": _map("timing"),
    "timing": _record(
        ("repeat_count", "repeat_interval_ms", "cancellation", "release"),
        {
            "repeat_count": {"type": "integer", "minimum": 1},
            "repeat_interval_ms": {"type": "integer", "minimum": 0},
            "cancellation": _enum(CancellationMode),
            "release": _enum(ReleaseMode),
            "release_action": _REF,
        },
    ),
    "lifecycles_map": _map("lifecycle"),
    "lifecycle": _record(
        ("phases",),
        {
            "phases": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": _enum(LifecyclePhase),
            }
        },
    ),
    "transports_map": _map("transport"),
    "transport": _record(
        ("characteristic", "write_mode", "packet_builder", "timing", "lifecycle"),
        {
            "characteristic": _REF,
            "write_mode": _enum(WriteMode),
            "packet_builder": _REF,
            "notification_parser": _REF,
            "authentication": _REF,
            "timing": _REF,
            "lifecycle": _REF,
        },
    ),
    "action_parameters_map": _map("action_parameter"),
    "action_parameter": _record(
        ("action", "values"),
        {
            "action": _REF,
            "values": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100000,
                "uniqueItems": True,
                "items": {"$ref": "#/$defs/selector_scalar"},
            },
        },
    ),
    "action_mappings_map": _map("action_mapping"),
    "action_mapping": _record(
        ("protocol", "action", "transport", "when"),
        {
            "protocol": _REF,
            "action": _REF,
            "transport": _REF,
            "when": {"$ref": "#/$defs/predicate"},
        },
    ),
    "domain_closure": _record(
        ("status", "domains", "unmodeled_paths"),
        {
            "status": {"const": "CLOSED"},
            "domains": {
                "type": "array",
                "prefixItems": [{"const": item} for item in FINAL_DOMAIN_COLLECTIONS],
                "minItems": len(FINAL_DOMAIN_COLLECTIONS),
                "maxItems": len(FINAL_DOMAIN_COLLECTIONS),
            },
            "unmodeled_paths": {"type": "array", "maxItems": 0},
        },
    ),
}
