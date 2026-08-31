"""Deterministic integrity validation for frozen Phase 4 report bundles."""

from .binding import CONTRACT_REVISION, VALIDATION_INPUT, DependencyPins
from .bundle import (
    VALIDATOR_REVISION,
    Diagnostic,
    StrictJsonError,
    ValidationReceipt,
    load_json_strict,
    validate_report_bundle,
)
from .lineage import (
    LINEAGE_SCHEMA_REVISION,
    EvidenceLineageManifest,
    EvidenceLineageTrust,
    LineageValidationError,
    TrustedProducer,
    bind_evidence_lineage,
)

__all__ = [
    "VALIDATOR_REVISION",
    "Diagnostic",
    "DependencyPins",
    "CONTRACT_REVISION",
    "StrictJsonError",
    "ValidationReceipt",
    "VALIDATION_INPUT",
    "load_json_strict",
    "validate_report_bundle",
    "LINEAGE_SCHEMA_REVISION",
    "EvidenceLineageManifest",
    "EvidenceLineageTrust",
    "LineageValidationError",
    "TrustedProducer",
    "bind_evidence_lineage",
]
