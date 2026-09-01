"""Fail-closed adapter from frozen package plans to queue work units."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
)
from tools.phase4_v2.validator import DependencyPins

from .core import FrozenPackageRef
from .plan import (
    PACKAGE_QUEUE_UNIT_KIND,
    PackageExecutionPlan,
    PackagePlanStatus,
    ValidatedPackageOutput,
    freeze_package_execution_plan,
    package_queue_unit_id,
    package_validation_receipt_completion,
)
from .plan import (
    PACKAGE_QUEUE_UNIT_PREFIX as PACKAGE_QUEUE_UNIT_PREFIX,
)

PACKAGE_VALIDATION_RECEIPT_QUEUE_UNIT_KIND = "trusted-package-validation-receipt"


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


@dataclass(frozen=True, slots=True)
class MaterializedPackageReceiptWork:
    """Identity of one receipt import that only the trusted adapter may complete."""

    unit_id: str
    input_digest: str


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


def materialize_package_validation_receipt(
    queue: Queue,
    package_ref: FrozenPackageRef,
    *,
    priority: int = 0,
) -> MaterializedPackageReceiptWork:
    """Materialize the reserved import unit for one frozen package receipt."""
    completion = package_validation_receipt_completion(package_ref)
    queue.materialize_work_unit(
        completion.parent_unit_id,
        kind=PACKAGE_VALIDATION_RECEIPT_QUEUE_UNIT_KIND,
        input_digest=completion.digest,
        priority=priority,
    )
    return MaterializedPackageReceiptWork(completion.parent_unit_id, completion.digest)


def finish_package_validation_receipt(
    queue: Queue,
    lease: Lease,
    *,
    package_ref: FrozenPackageRef,
    receipt_payload: str | bytes,
    trusted_validator_revision: str,
    trusted_contract_revision: str,
    trusted_dependency_digests: Mapping[str, str],
    trusted_receipt_sha256: str,
) -> FinishResult:
    """Verify and publish a canonical package-local validator receipt."""
    return queue.finish_package_validation_receipt(
        lease,
        package_ref=package_ref,
        receipt_payload=receipt_payload,
        trusted_validator_revision=trusted_validator_revision,
        trusted_contract_revision=trusted_contract_revision,
        trusted_dependency_digests=trusted_dependency_digests,
        trusted_receipt_sha256=trusted_receipt_sha256,
    )


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
    report_root: Path,
    trusted_dependencies: DependencyPins,
    evidence_lineage_payload: bytes,
) -> FinishedPackageWork:
    """Validate and publish a package report from live trusted inputs."""
    frozen = freeze_package_execution_plan(execution_plan)
    expected_unit_id = package_queue_unit_id(frozen.target_package_ref_id)
    if lease.unit_id != expected_unit_id:
        raise QueueConflictError("lease does not belong to the package execution plan")

    output, checked = queue.finish_validated_package_output(
        lease,
        execution_plan=execution_plan,
        report_root=report_root,
        trusted_dependencies=trusted_dependencies,
        evidence_lineage_payload=evidence_lineage_payload,
    )
    result = checked.finish_result
    if checked.disposition is InputCheckedFinishDisposition.INPUT_MISMATCH:
        raise PackagePlanInputMismatchError(
            "package plan does not match the leased queue input",
            output=output,
            queue_result=result,
        )
    return FinishedPackageWork(output=output, queue_result=result)
