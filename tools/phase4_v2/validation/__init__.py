"""Synthetic-safe Phase 4 v2 completion validation."""

from .gates import validate_completion
from .model import (
    ADAPTER_REVISION,
    VALIDATION_REVISION,
    CandidateLink,
    CompletenessReceipt,
    CompletionAdapter,
    Diagnostic,
    ValidationError,
    ValidationPins,
    WarningDisposition,
    WarningStatus,
    candidate_occurrence_id,
    warning_occurrence_id,
)

__all__ = [
    "ADAPTER_REVISION",
    "VALIDATION_REVISION",
    "CandidateLink",
    "CompletenessReceipt",
    "CompletionAdapter",
    "Diagnostic",
    "ValidationError",
    "ValidationPins",
    "WarningDisposition",
    "WarningStatus",
    "candidate_occurrence_id",
    "validate_completion",
    "warning_occurrence_id",
]
