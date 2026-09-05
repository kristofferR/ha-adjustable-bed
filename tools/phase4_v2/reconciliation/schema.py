"""Closed input schema for deterministic Phase 4 v2 reconciliation."""

from __future__ import annotations

import copy
import hashlib
import json

INPUT_SCHEMA_REVISION = "phase4-v2-reconciliation-input-v5"
COMPARISON_AREAS = (
    "actions",
    "authentication",
    "capabilities_configuration",
    "discovery",
    "gatt",
    "lifecycle",
    "models_variants",
    "packet_construction",
    "parsing",
    "timing_stop_release",
    "transport",
)

_SHA256 = {"pattern": "^[0-9a-f]{64}$", "type": "string"}
_TOKEN = {
    "maxLength": 200,
    "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    "type": "string",
}
_POINTER = {
    "maxLength": 8192,
    "minLength": 1,
    "pattern": "^(?:/(?:[^~/]|~[01])*)+$",
    "type": "string",
}
_STRING_SET = {
    "items": {"maxLength": 256, "minLength": 1, "type": "string"},
    "maxItems": 4096,
    "type": "array",
    "uniqueItems": True,
}
_LONG_STRING_SET = {
    "items": {"maxLength": 4096, "minLength": 1, "type": "string"},
    "maxItems": 4096,
    "type": "array",
    "uniqueItems": True,
}
_POINTER_SET = {
    "items": _POINTER,
    "maxItems": 4096,
    "type": "array",
    "uniqueItems": True,
}

_SCHEMA: dict[str, object] = {
    "$id": f"https://local.invalid/schemas/{INPUT_SCHEMA_REVISION}.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "additionalProperties": False,
    "properties": {
        "cluster_id": _TOKEN,
        "packages": {
            "items": {"$ref": "#/$defs/package_surface"},
            "maxItems": 32,
            "minItems": 1,
            "type": "array",
        },
        "revision": {"const": INPUT_SCHEMA_REVISION},
    },
    "required": ["cluster_id", "packages", "revision"],
    "title": "Phase 4 v2 typed cluster reconciliation input",
    "type": "object",
    "$defs": {
        "area_surface": {
            "additionalProperties": False,
            "properties": {
                "area": {"enum": list(COMPARISON_AREAS)},
                "claims": {
                    "items": {"$ref": "#/$defs/claim"},
                    "maxItems": 100000,
                    "type": "array",
                },
                "closure": {"enum": ["COMPLETE", "INCOMPLETE"]},
                "dispositions": {
                    "items": {"$ref": "#/$defs/disposition"},
                    "maxItems": 100000,
                    "type": "array",
                },
                "gaps": _LONG_STRING_SET,
            },
            "required": ["area", "claims", "closure", "dispositions", "gaps"],
            "type": "object",
        },
        "claim": {
            "additionalProperties": False,
            "properties": {
                "key": _POINTER,
                "polarity": {"enum": ["AFFIRMED", "DENIED"]},
                "provenance": {
                    "items": {"$ref": "#/$defs/leaf_provenance"},
                    "maxItems": 4096,
                    "minItems": 1,
                    "type": "array",
                },
                "value": {},
            },
            "required": ["key", "polarity", "provenance", "value"],
            "type": "object",
        },
        "disposition": {
            "additionalProperties": False,
            "properties": {
                "claim_keys": _POINTER_SET,
                "item_id": _TOKEN,
                "kind": {"enum": ["ACTION", "CANDIDATE", "VARIANT"]},
                "provenance": {
                    "items": {"$ref": "#/$defs/leaf_provenance"},
                    "maxItems": 4096,
                    "minItems": 1,
                    "type": "array",
                },
                "reason_code": _TOKEN,
                "status": {"enum": ["ABSENT", "COVERED", "EXCLUDED", "INCOMPLETE"]},
            },
            "required": [
                "claim_keys",
                "item_id",
                "kind",
                "provenance",
                "reason_code",
                "status",
            ],
            "type": "object",
        },
        "leaf_provenance": {
            "additionalProperties": False,
            "properties": {
                "evidence_anchor_ids": {
                    **_STRING_SET,
                    "minItems": 1,
                },
                "report_pointer": _POINTER,
                "root_ref_id": _SHA256,
            },
            "required": ["evidence_anchor_ids", "report_pointer", "root_ref_id"],
            "type": "object",
        },
        "package_surface": {
            "additionalProperties": False,
            "properties": {
                "areas": {
                    "items": {"$ref": "#/$defs/area_surface"},
                    "maxItems": 11,
                    "type": "array",
                },
                "package_ref_id": _SHA256,
                "package_local": {"$ref": "#/$defs/package_local_provenance"},
                "report_revision": _TOKEN,
                "report_sha256": _SHA256,
                "roots": {
                    "items": {"$ref": "#/$defs/root_provenance"},
                    "maxItems": 4096,
                    "minItems": 1,
                    "type": "array",
                },
            },
            "required": [
                "areas",
                "package_local",
                "package_ref_id",
                "report_revision",
                "report_sha256",
                "roots",
            ],
            "type": "object",
        },
        "package_local_provenance": {
            "additionalProperties": False,
            "properties": {
                "evidence_anchor_ids": {**_STRING_SET, "minItems": 1},
                "mandatory_domains": {**_STRING_SET, "minItems": 1},
                "package_ref_id": _SHA256,
                "report_pointer": _POINTER,
                "source_package_id": {
                    "maxLength": 256,
                    "pattern": "^pkg:[0-9a-f]{64}$",
                    "type": "string",
                },
                "source_raw_receipt_sha256": _SHA256,
                "source_validation_receipt_sha256": _SHA256,
                "targets": {
                    "items": {"$ref": "#/$defs/package_local_target"},
                    "maxItems": 4096,
                    "minItems": 1,
                    "type": "array",
                },
            },
            "required": [
                "evidence_anchor_ids",
                "mandatory_domains",
                "package_ref_id",
                "report_pointer",
                "source_package_id",
                "source_raw_receipt_sha256",
                "source_validation_receipt_sha256",
                "targets",
            ],
            "type": "object",
        },
        "package_local_target": {
            "additionalProperties": False,
            "properties": {
                "evidence_anchor_id": {
                    "maxLength": 256,
                    "minLength": 1,
                    "type": "string",
                },
                "local_domain": _TOKEN,
                "terminal_ir_pointer": _POINTER,
            },
            "required": [
                "evidence_anchor_id",
                "local_domain",
                "terminal_ir_pointer",
            ],
            "type": "object",
        },
        "root_provenance": {
            "additionalProperties": False,
            "properties": {
                "blockers": _LONG_STRING_SET,
                "evidence_anchor_ids": _STRING_SET,
                "occurrence_identity_sha256": _SHA256,
                "package_ref_id": _SHA256,
                "report_pointer": _POINTER,
                "route": {"enum": ["BLOCKED", "EXACT_REUSE", "FULL_ANALYSIS"]},
                "semantic_root_sha256": {"oneOf": [_SHA256, {"type": "null"}]},
                "source_root_id": {"oneOf": [_SHA256, {"type": "null"}]},
                "source_package_ref_id": {"oneOf": [_SHA256, {"type": "null"}]},
                "source_occurrence_identity_sha256": {"oneOf": [_SHA256, {"type": "null"}]},
                "source_validation_receipt_sha256": {"oneOf": [_SHA256, {"type": "null"}]},
                "source_raw_receipt_sha256": {"oneOf": [_SHA256, {"type": "null"}]},
                "target_root_id": _SHA256,
            },
            "required": [
                "blockers",
                "evidence_anchor_ids",
                "occurrence_identity_sha256",
                "package_ref_id",
                "report_pointer",
                "route",
                "semantic_root_sha256",
                "source_root_id",
                "source_package_ref_id",
                "source_occurrence_identity_sha256",
                "source_validation_receipt_sha256",
                "source_raw_receipt_sha256",
                "target_root_id",
            ],
            "type": "object",
        },
    },
}
INPUT_SCHEMA_CANONICAL_BYTES = json.dumps(
    _SCHEMA,
    allow_nan=False,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
).encode("utf-8")
INPUT_SCHEMA_SHA256 = hashlib.sha256(INPUT_SCHEMA_CANONICAL_BYTES).hexdigest()


def schema_document() -> dict[str, object]:
    """Return a defensive copy of the pinned closed schema."""
    return copy.deepcopy(_SCHEMA)
