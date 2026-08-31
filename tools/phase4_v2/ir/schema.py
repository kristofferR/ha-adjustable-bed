"""Pinned JSON Schema for the first strict Phase 4 v2 IR slice."""

from __future__ import annotations

import copy

from .model import (
    BOUND_VALIDATION_PROFILE,
    SCHEMA_REVISION,
    SUPPORTED_CONTRACT_REVISION,
    SUPPORTED_VALIDATOR_REVISION,
)

_ID_PATTERN = "^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_SHA256_PATTERN = "^[0-9a-f]{64}$"
_PACKAGE_ID_PATTERN = "^[A-Za-z0-9_]+(?:\\.[A-Za-z0-9_]+)+$"
_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": f"https://local.invalid/schemas/{SCHEMA_REVISION}.json",
    "title": "Phase 4 protocol intermediate representation",
    "type": "object",
    "required": [
        "schema_revision",
        "source_packages",
        "evidence_files",
        "evidence_anchors",
        "source_sets",
        "evidence_bindings",
        "variant_spaces",
        "protocols",
        "actions",
        "expected_action_rules",
        "command_bindings",
    ],
    "properties": {
        "schema_revision": {"const": SCHEMA_REVISION},
        "source_packages": {"$ref": "#/$defs/source_package_map"},
        "evidence_files": {"$ref": "#/$defs/evidence_file_map"},
        "evidence_anchors": {"$ref": "#/$defs/evidence_anchor_map"},
        "source_sets": {"$ref": "#/$defs/source_set_map"},
        "evidence_bindings": {"$ref": "#/$defs/evidence_binding_map"},
        "variant_spaces": {"$ref": "#/$defs/variant_space_map"},
        "protocols": {"$ref": "#/$defs/protocol_map"},
        "actions": {"$ref": "#/$defs/action_map"},
        "expected_action_rules": {"$ref": "#/$defs/rule_map"},
        "command_bindings": {"$ref": "#/$defs/rule_map"},
    },
    "additionalProperties": False,
    "$defs": {
        "identifier": {"type": "string", "pattern": _ID_PATTERN},
        "sha256": {"type": "string", "pattern": _SHA256_PATTERN},
        "reference_set": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4096,
            "uniqueItems": True,
            "items": {"$ref": "#/$defs/identifier"},
        },
        "artifact_identity": {
            "type": "object",
            "required": ["package_name", "version_code", "version_name", "artifact_digest"],
            "properties": {
                "package_name": {"type": "string", "pattern": _PACKAGE_ID_PATTERN},
                "version_code": {"type": "string", "minLength": 1, "maxLength": 256},
                "version_name": {"type": "string", "minLength": 1, "maxLength": 256},
                "artifact_digest": {"$ref": "#/$defs/sha256"},
            },
            "additionalProperties": False,
        },
        "validated_report": {
            "type": "object",
            "required": [
                "validator_revision",
                "contract_revision",
                "validation_profile",
                "validation_receipt_sha256",
                "bundle_sha256",
                "report_manifest_sha256",
                "discovered_members",
                "declared_members",
                "evidence_anchors_checked",
                "dependency_digests",
                "validated_artifact_identity",
                "validated_evidence_members",
                "validated_evidence_anchors",
            ],
            "properties": {
                "validator_revision": {"const": SUPPORTED_VALIDATOR_REVISION},
                "contract_revision": {"const": SUPPORTED_CONTRACT_REVISION},
                "validation_profile": {"const": BOUND_VALIDATION_PROFILE},
                "validation_receipt_sha256": {"$ref": "#/$defs/sha256"},
                "bundle_sha256": {"$ref": "#/$defs/sha256"},
                "report_manifest_sha256": {"$ref": "#/$defs/sha256"},
                "discovered_members": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 9223372036854775807,
                },
                "declared_members": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 9223372036854775807,
                },
                "evidence_anchors_checked": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 9223372036854775807,
                },
                "dependency_digests": {"$ref": "#/$defs/dependency_digests"},
                "validated_artifact_identity": {"$ref": "#/$defs/artifact_identity"},
                "validated_evidence_members": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4096,
                    "items": {"$ref": "#/$defs/attested_evidence_member"},
                },
                "validated_evidence_anchors": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4096,
                    "items": {"$ref": "#/$defs/attested_evidence_anchor"},
                },
            },
            "additionalProperties": False,
        },
        "dependency_digests": {
            "type": "object",
            "required": ["corpus", "evidence_lineage", "ir", "preflight", "schema"],
            "properties": {
                "corpus": {"$ref": "#/$defs/sha256"},
                "evidence_lineage": {"$ref": "#/$defs/sha256"},
                "ir": {"$ref": "#/$defs/sha256"},
                "preflight": {"$ref": "#/$defs/sha256"},
                "schema": {"$ref": "#/$defs/sha256"},
            },
            "additionalProperties": False,
        },
        "attested_evidence_member": {
            "type": "object",
            "required": ["member", "owner", "sha256"],
            "properties": {
                "member": {"type": "string", "minLength": 1, "maxLength": 4096},
                "owner": {"$ref": "#/$defs/sha256"},
                "sha256": {"$ref": "#/$defs/sha256"},
            },
            "additionalProperties": False,
        },
        "attested_evidence_anchor": {
            "type": "object",
            "required": [
                "id",
                "owner",
                "member",
                "member_sha256",
                "start_byte",
                "end_byte",
                "ir_pointer",
                "representation",
                "value_sha256",
            ],
            "properties": {
                "id": {"type": "string", "minLength": 1, "maxLength": 256},
                "owner": {"$ref": "#/$defs/sha256"},
                "member": {"type": "string", "minLength": 1, "maxLength": 4096},
                "member_sha256": {"$ref": "#/$defs/sha256"},
                "start_byte": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 9223372036854775807,
                },
                "end_byte": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 9223372036854775807,
                },
                "ir_pointer": {"type": "string", "minLength": 1, "maxLength": 8192},
                "representation": {"enum": ["hex", "utf8"]},
                "value_sha256": {"$ref": "#/$defs/sha256"},
            },
            "additionalProperties": False,
        },
        "source_package": {
            "type": "object",
            "required": ["artifact", "report"],
            "properties": {
                "artifact": {"$ref": "#/$defs/artifact_identity"},
                "report": {"$ref": "#/$defs/validated_report"},
            },
            "additionalProperties": False,
        },
        "evidence_file": {
            "type": "object",
            "required": ["package", "member", "sha256"],
            "properties": {
                "package": {"$ref": "#/$defs/identifier"},
                "member": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4096,
                    "$comment": "parse_ir additionally requires a canonical relative report path",
                },
                "sha256": {"$ref": "#/$defs/sha256"},
            },
            "additionalProperties": False,
        },
        "evidence_anchor": {
            "type": "object",
            "required": [
                "id",
                "file",
                "start_byte",
                "end_byte",
                "ir_pointer",
                "representation",
                "value_sha256",
            ],
            "properties": {
                "id": {"type": "string", "minLength": 1, "maxLength": 256},
                "file": {"$ref": "#/$defs/identifier"},
                "start_byte": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 9223372036854775807,
                },
                "end_byte": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 9223372036854775807,
                },
                "ir_pointer": {"type": "string", "minLength": 1, "maxLength": 8192},
                "representation": {"enum": ["hex", "utf8"]},
                "value_sha256": {"$ref": "#/$defs/sha256"},
            },
            "additionalProperties": False,
        },
        "source_set": {
            "type": "object",
            "required": ["package", "anchors"],
            "properties": {
                "package": {"$ref": "#/$defs/identifier"},
                "anchors": {"$ref": "#/$defs/reference_set"},
            },
            "additionalProperties": False,
        },
        "evidence_binding": {
            "type": "object",
            "required": ["target", "source_sets"],
            "properties": {
                "target": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 8192,
                    "$comment": "parse_ir additionally requires a valid RFC 6901 JSON Pointer to a semantic scalar leaf",
                },
                "source_sets": {"$ref": "#/$defs/reference_set"},
            },
            "additionalProperties": False,
        },
        "selector_scalar": {
            "oneOf": [
                {"type": "string"},
                {
                    "type": "integer",
                    "minimum": -9223372036854775808,
                    "maximum": 9223372036854775807,
                },
                {"type": "boolean"},
            ]
        },
        "predicate": {
            "oneOf": [
                {
                    "type": "object",
                    "required": ["op"],
                    "properties": {"op": {"enum": ["always", "never"]}},
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["op", "dimension", "value"],
                    "properties": {
                        "op": {"const": "eq"},
                        "dimension": {"$ref": "#/$defs/identifier"},
                        "value": {"$ref": "#/$defs/selector_scalar"},
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["op", "dimension", "values"],
                    "properties": {
                        "op": {"const": "in"},
                        "dimension": {"$ref": "#/$defs/identifier"},
                        "values": {
                            "type": "array",
                            "minItems": 1,
                            "uniqueItems": True,
                            "items": {"$ref": "#/$defs/selector_scalar"},
                        },
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["op", "terms"],
                    "properties": {
                        "op": {"enum": ["all", "any"]},
                        "terms": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"$ref": "#/$defs/predicate"},
                        },
                    },
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "required": ["op", "term"],
                    "properties": {
                        "op": {"const": "not"},
                        "term": {"$ref": "#/$defs/predicate"},
                    },
                    "additionalProperties": False,
                },
            ]
        },
        "variant_space": {
            "type": "object",
            "required": ["dimensions", "constraints"],
            "properties": {
                "dimensions": {
                    "type": "object",
                    "propertyNames": {"pattern": _ID_PATTERN},
                    "additionalProperties": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"$ref": "#/$defs/selector_scalar"},
                    },
                },
                "constraints": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/predicate"},
                },
            },
            "additionalProperties": False,
        },
        "protocol": {
            "type": "object",
            "required": ["variant_space"],
            "properties": {"variant_space": {"$ref": "#/$defs/identifier"}},
            "additionalProperties": False,
        },
        "action": {
            "type": "object",
            "properties": {"summary": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        "rule": {
            "type": "object",
            "required": ["protocol", "action", "when"],
            "properties": {
                "protocol": {"$ref": "#/$defs/identifier"},
                "action": {"$ref": "#/$defs/identifier"},
                "when": {"$ref": "#/$defs/predicate"},
            },
            "additionalProperties": False,
        },
        "variant_space_map": {
            "type": "object",
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/variant_space"},
        },
        "protocol_map": {
            "type": "object",
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/protocol"},
        },
        "action_map": {
            "type": "object",
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/action"},
        },
        "rule_map": {
            "type": "object",
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/rule"},
        },
        "source_package_map": {
            "type": "object",
            "maxProperties": 250000,
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/source_package"},
        },
        "evidence_file_map": {
            "type": "object",
            "maxProperties": 250000,
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/evidence_file"},
        },
        "evidence_anchor_map": {
            "type": "object",
            "maxProperties": 250000,
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/evidence_anchor"},
        },
        "source_set_map": {
            "type": "object",
            "maxProperties": 250000,
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/source_set"},
        },
        "evidence_binding_map": {
            "type": "object",
            "maxProperties": 250000,
            "propertyNames": {"pattern": _ID_PATTERN},
            "additionalProperties": {"$ref": "#/$defs/evidence_binding"},
        },
    },
}


def schema_document() -> dict[str, object]:
    """Return a defensive copy of the pinned schema document."""

    return copy.deepcopy(_SCHEMA)
