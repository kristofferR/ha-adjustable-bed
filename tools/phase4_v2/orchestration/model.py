"""Typed orchestration stages and deterministic follow-up routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from tools.phase4_v2.queue import (
    ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
    ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
    ORCHESTRATION_PACKAGE_ANALYSIS_KIND,
    ORCHESTRATION_PACKAGE_AUDIT_KIND,
    ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    TerminalOutcome,
)


class WorkStage(StrEnum):
    """A queue kind with orchestration semantics."""

    PACKAGE_ANALYSIS = ORCHESTRATION_PACKAGE_ANALYSIS_KIND
    PACKAGE_AUDIT = ORCHESTRATION_PACKAGE_AUDIT_KIND
    CLUSTER_RECONCILIATION = ORCHESTRATION_CLUSTER_RECONCILIATION_KIND
    CLUSTER_IMPLEMENTATION = ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND
    TRACKER_PUBLICATION = ORCHESTRATION_TRACKER_PUBLICATION_KIND


class FollowUpAction(StrEnum):
    """The only scheduler actions produced by an attempt terminal."""

    ADVANCE = "ADVANCE"
    RETRY_REPAIR = "RETRY_REPAIR"
    WAIT_FOR_BLOCKER = "WAIT_FOR_BLOCKER"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class FollowUp:
    """One deterministic, machine-readable post-attempt decision."""

    action: FollowUpAction
    next_stage: WorkStage | None


_NEXT_STAGE = {
    WorkStage.PACKAGE_ANALYSIS: WorkStage.PACKAGE_AUDIT,
    WorkStage.PACKAGE_AUDIT: WorkStage.CLUSTER_RECONCILIATION,
    WorkStage.CLUSTER_RECONCILIATION: WorkStage.CLUSTER_IMPLEMENTATION,
    WorkStage.CLUSTER_IMPLEMENTATION: WorkStage.TRACKER_PUBLICATION,
}


def route_follow_up(stage: WorkStage, outcome: TerminalOutcome) -> FollowUp:
    """Map an immutable terminal to one typed scheduler action."""
    if not isinstance(stage, WorkStage):
        raise ValueError("stage must be a WorkStage")
    if not isinstance(outcome, TerminalOutcome):
        raise ValueError("outcome must be a TerminalOutcome")
    if outcome is TerminalOutcome.ACCEPTED:
        next_stage = _NEXT_STAGE.get(stage)
        return FollowUp(
            FollowUpAction.ADVANCE if next_stage is not None else FollowUpAction.COMPLETE,
            next_stage,
        )
    if outcome is TerminalOutcome.BLOCKED:
        return FollowUp(FollowUpAction.WAIT_FOR_BLOCKER, None)
    return FollowUp(FollowUpAction.RETRY_REPAIR, stage)
