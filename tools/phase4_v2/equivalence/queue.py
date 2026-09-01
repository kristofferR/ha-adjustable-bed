"""Fail-closed adapter from frozen package plans to queue work units."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tools.phase4_v2.ir import bind_validator_receipt
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

from .core import FrozenPackageRef
from .plan import (
    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
    VALIDATED_PACKAGE_OUTPUT_REVISION,
    PackageExecutionPlan,
    PackagePlanStatus,
    ValidatedPackageOutput,
    build_validated_package_output,
    freeze_package_execution_plan,
    package_validation_receipt_completion,
)

PACKAGE_QUEUE_UNIT_KIND = "validated-package-output"
PACKAGE_QUEUE_UNIT_PREFIX = "package-output"
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


def package_queue_unit_id(target_package_ref_id: str) -> str:
    """Return the stable aggregate unit ID for one immutable package reference."""
    return f"{PACKAGE_QUEUE_UNIT_PREFIX}:{target_package_ref_id}"


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
    completion = package_validation_receipt_completion(package_ref)
    if lease.unit_id != completion.parent_unit_id:
        raise QueueConflictError("lease does not belong to the package validation receipt")
    report = bind_validator_receipt(
        receipt_payload,
        trusted_validator_revision=trusted_validator_revision,
        trusted_contract_revision=trusted_contract_revision,
        trusted_dependency_digests=trusted_dependency_digests,
        trusted_receipt_sha256=trusted_receipt_sha256,
    )
    identity = report.validated_artifact_identity
    dependencies = dict(report.dependency_digests)
    if (
        report.validation_receipt_sha256 != package_ref.validation_receipt_sha256
        or identity.package_name != package_ref.package_name
        or identity.version_code != package_ref.version_code
        or identity.artifact_digest != package_ref.artifact_digest
        or dependencies.get("preflight") != package_ref.preflight_sha256
    ):
        raise QueueConflictError("validated receipt does not bind the frozen package reference")
    return queue._finish_trusted_completion(
        lease,
        output_digest=completion.digest,
        completion_revision=PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
        expected_input_digest=completion.digest,
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
