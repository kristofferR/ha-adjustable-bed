"""Fail-closed adapter from frozen package plans to queue work units."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tools.phase4_v2.preflight.registry import (
    ActivatedPreparationAuthority,
    PreparationReceipt,
)
from tools.phase4_v2.queue import (
    CapabilityPin as QueueCapabilityPin,
)
from tools.phase4_v2.queue import (
    CompletionDependencyPin,
    ExecutionMode,
    FinishDisposition,
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
    PREPARATION_QUEUE_UNIT_KIND,
    PackageExecutionPlan,
    PackageLocalPlan,
    PackagePlanStatus,
    PreparationPlanBinding,
    ValidatedPackageOutput,
    freeze_package_execution_plan,
    package_queue_unit_id,
    package_validation_receipt_completion,
    preparation_capability_pins,
    preparation_queue_unit_id,
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


@dataclass(frozen=True, slots=True)
class MaterializedPreparationWork:
    """Identity of one externally authorized package-preparation unit."""

    unit_id: str
    input_digest: str


@dataclass(frozen=True, slots=True)
class FinishedPreparationWork:
    """Accepted preparation binding and its formal queue completion."""

    binding: PreparationPlanBinding
    queue_result: FinishResult


class PackagePlanInputMismatchError(InputDigestMismatchError):
    """A produced output was preserved but not accepted for changed input."""

    def __init__(
        self,
        message: str,
        *,
        output: ValidatedPackageOutput | None,
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


def materialize_package_preparation(
    queue: Queue,
    *,
    package_ref: FrozenPackageRef,
    package_local: PackageLocalPlan,
    authority: ActivatedPreparationAuthority,
    priority: int = 0,
) -> MaterializedPreparationWork:
    """Materialize one package preparation against independently active pins."""

    if type(package_ref) is not FrozenPackageRef:
        raise QueueConflictError("preparation requires an exact frozen package reference")
    if type(package_local) is not PackageLocalPlan:
        raise QueueConflictError("preparation requires an exact package-local plan")
    package_ref_id = package_ref.content_id
    if (
        package_local.target_package_ref_id,
        package_local.package_name,
        package_local.version_code,
        package_local.target_artifact_digest,
        package_local.requirements_sha256,
    ) != (
        package_ref_id,
        package_ref.package_name,
        package_ref.version_code,
        package_ref.artifact_digest,
        package_ref.preflight_sha256,
    ):
        raise QueueConflictError("preparation package identity does not match its frozen reference")
    capabilities = preparation_capability_pins(authority)
    unit_id = preparation_queue_unit_id(package_ref_id)
    input_digest = queue.materialize_work_unit(
        unit_id,
        kind=PREPARATION_QUEUE_UNIT_KIND,
        capability_pins=tuple(
            QueueCapabilityPin(pin.name, pin.revision, pin.digest) for pin in capabilities
        ),
        priority=priority,
    )
    return MaterializedPreparationWork(unit_id, input_digest)


def finish_package_preparation(
    queue: Queue,
    lease: Lease,
    *,
    package_ref: FrozenPackageRef,
    package_local: PackageLocalPlan,
    receipt: PreparationReceipt,
    authority: ActivatedPreparationAuthority,
) -> FinishedPreparationWork:
    """Publish one trusted preparation receipt and return its plan-only binding."""

    binding, result = queue.finish_preparation_receipt(
        lease,
        package_ref=package_ref,
        package_local=package_local,
        receipt=receipt,
        authority=authority,
    )
    return FinishedPreparationWork(binding, result)


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

    preparation = frozen.preparation.completion
    queue.require_formal_completion(
        preparation.parent_unit_id,
        revision=preparation.revision,
        digest=preparation.digest,
        capability_pins=tuple(
            QueueCapabilityPin(pin.name, pin.revision, pin.digest)
            for pin in frozen.preparation.capabilities
        ),
    )

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
        cluster_id=frozen.cluster_id,
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

    try:
        output, checked = queue.finish_validated_package_output(
            lease,
            execution_plan=execution_plan,
            report_root=report_root,
            trusted_dependencies=trusted_dependencies,
            evidence_lineage_payload=evidence_lineage_payload,
        )
    except InputDigestMismatchError as error:
        raise PackagePlanInputMismatchError(
            str(error),
            output=None,
            queue_result=FinishResult(
                disposition=FinishDisposition.TERMINAL_ONLY,
                unit_id=lease.unit_id,
                attempt_id=lease.attempt_id,
                output_digest=None,
            ),
        ) from error
    result = checked.finish_result
    if checked.disposition is InputCheckedFinishDisposition.INPUT_MISMATCH:
        raise PackagePlanInputMismatchError(
            "package plan does not match the leased queue input",
            output=output,
            queue_result=result,
        )
    return FinishedPackageWork(output=output, queue_result=result)
