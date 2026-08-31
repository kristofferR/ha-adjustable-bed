"""Fail-closed adapter from frozen package plans to queue work units."""

from __future__ import annotations

from dataclasses import dataclass

from tools.phase4_v2.queue import (
    CapabilityPin as QueueCapabilityPin,
)
from tools.phase4_v2.queue import (
    CompletionDependencyPin,
    ExecutionMode,
    FinishResult,
    InputCheckedFinishDisposition,
    InputDigestMismatchError,
    Lease,
    Queue,
    QueueConflictError,
    TerminalOutcome,
)
from tools.phase4_v2.validator import ValidationReceipt

from .plan import (
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    PackageExecutionPlan,
    PackagePlanStatus,
    ValidatedPackageOutput,
    build_validated_package_output,
    freeze_package_execution_plan,
)

PACKAGE_QUEUE_UNIT_KIND = "validated-package-output"
PACKAGE_QUEUE_UNIT_PREFIX = "package-output"


@dataclass(frozen=True, slots=True)
class MaterializedPackageWork:
    """Identity of one exact package plan published to the queue."""

    unit_id: str
    input_digest: str


@dataclass(frozen=True, slots=True)
class FinishedPackageWork:
    """Trusted output and the queue completion that published it."""

    output: ValidatedPackageOutput
    queue_result: FinishResult


class PackagePlanInputMismatchError(InputDigestMismatchError):
    """A produced output was preserved but not accepted for changed input."""

    def __init__(
        self,
        message: str,
        *,
        output: ValidatedPackageOutput,
        queue_result: FinishResult,
    ) -> None:
        super().__init__(message)
        self.output = output
        self.queue_result = queue_result


def package_queue_unit_id(target_package_ref_id: str) -> str:
    """Return the stable aggregate unit ID for one immutable package reference."""
    return f"{PACKAGE_QUEUE_UNIT_PREFIX}:{target_package_ref_id}"


def materialize_package_execution_plan(
    queue: Queue,
    execution_plan: PackageExecutionPlan,
    *,
    priority: int = 0,
) -> MaterializedPackageWork | None:
    """Freeze and atomically materialize an executable package plan.

    A blocked plan deliberately has no queue representation. Exact-reuse roots
    remain dependencies of a distinct aggregate package-output unit.
    """
    frozen = freeze_package_execution_plan(execution_plan)
    if frozen.status is PackagePlanStatus.BLOCKED:
        return None

    unit_id = package_queue_unit_id(frozen.target_package_ref_id)
    input_digest = queue.materialize_work_unit(
        unit_id,
        kind=PACKAGE_QUEUE_UNIT_KIND,
        capability_pins=tuple(
            QueueCapabilityPin(pin.name, pin.revision, pin.digest)
            for pin in frozen.required_capabilities
        ),
        dependency_pins=tuple(
            CompletionDependencyPin(pin.parent_unit_id, pin.revision, pin.digest)
            for pin in frozen.required_completions
        ),
        input_digest=frozen.digest,
        priority=priority,
        execution_mode=ExecutionMode.NORMAL,
    )
    if input_digest != frozen.digest:
        raise QueueConflictError("queue did not preserve the frozen package plan digest")
    return MaterializedPackageWork(unit_id=unit_id, input_digest=input_digest)


def finish_package_execution_plan(
    queue: Queue,
    lease: Lease,
    *,
    execution_plan: PackageExecutionPlan,
    receipt: ValidationReceipt,
    trusted_validation_receipt_sha256: str,
) -> FinishedPackageWork:
    """Build and publish an accepted package output from live trusted inputs."""
    output = build_validated_package_output(
        execution_plan=execution_plan,
        receipt=receipt,
        trusted_validation_receipt_sha256=trusted_validation_receipt_sha256,
    )
    expected_unit_id = package_queue_unit_id(output.target_package_ref_id)
    if lease.unit_id != expected_unit_id:
        raise QueueConflictError("lease does not belong to the package execution plan")
    frozen = freeze_package_execution_plan(execution_plan)
    if output.execution_plan_id != frozen.digest:
        result = queue.finish(
            lease,
            TerminalOutcome.INPUT_MISMATCH,
            output_digest=output.content_id,
        )
        raise PackagePlanInputMismatchError(
            "package plan changed while its output was being built",
            output=output,
            queue_result=result,
        )

    checked = queue.finish_accepted_if_input_matches(
        lease,
        output_digest=output.content_id,
        completion_revision=VALIDATED_PACKAGE_OUTPUT_REVISION,
        expected_input_digest=frozen.digest,
    )
    result = checked.finish_result
    if checked.disposition is InputCheckedFinishDisposition.INPUT_MISMATCH:
        raise PackagePlanInputMismatchError(
            "package plan does not match the leased queue input",
            output=output,
            queue_result=result,
        )
    return FinishedPackageWork(output=output, queue_result=result)
