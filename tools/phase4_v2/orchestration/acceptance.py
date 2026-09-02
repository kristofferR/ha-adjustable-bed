"""Seeded, synthetic crash acceptance for the host-local orchestrator."""

from __future__ import annotations

import hashlib
import random
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from tools.phase4_v2.queue import Lease, Queue, StaleLeaseError, TerminalOutcome, WorkUnitStatus

from .model import WorkStage


@dataclass(frozen=True, slots=True)
class SyntheticAcceptanceConfig:
    """Bounded inputs for one reproducible acceptance run."""

    seed: int
    clusters: int = 8
    units_per_cluster: int = 8
    workers: int = 8
    crash_probability: float = 0.2
    forced_initial_crashes: int = 1
    max_rounds: int = 10_000

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        if type(self.clusters) is not int or not 1 <= self.clusters <= 1_000:
            raise ValueError("clusters must be between 1 and 1000")
        if type(self.units_per_cluster) is not int or not 1 <= self.units_per_cluster <= 1_000:
            raise ValueError("units_per_cluster must be between 1 and 1000")
        if type(self.workers) is not int or not 1 <= self.workers <= 64:
            raise ValueError("workers must be between 1 and 64")
        if (
            isinstance(self.crash_probability, bool)
            or not isinstance(self.crash_probability, (int, float))
            or not 0 <= self.crash_probability < 1
        ):
            raise ValueError("crash_probability must be at least zero and below one")
        if type(self.forced_initial_crashes) is not int or not (
            0 <= self.forced_initial_crashes <= self.clusters * (self.units_per_cluster + 2)
        ):
            raise ValueError("forced_initial_crashes must fit the synthetic unit count")
        if type(self.max_rounds) is not int or not 1 <= self.max_rounds <= 1_000_000:
            raise ValueError("max_rounds must be bounded and positive")


@dataclass(frozen=True, slots=True)
class SyntheticAcceptanceReport:
    """Evidence that a seeded run converged without overlap or output loss."""

    seed: int
    unit_count: int
    attempt_count: int
    injected_crashes: int
    recovered_attempts: int
    stale_writers_fenced: int
    max_implementation_debt_clusters: int
    rounds: int
    final_generation: str


def run_synthetic_acceptance(
    root: Path,
    config: SyntheticAcceptanceConfig,
) -> SyntheticAcceptanceReport:
    """Exercise concurrent claims, crashes, recovery, fencing, and convergence."""
    if root.exists():
        raise ValueError("synthetic acceptance root must not already exist")
    database = root / "state" / "queue.sqlite3"
    attempts_root = root / "attempts"
    queue = Queue(database, attempts_root)
    queue.initialize()
    unit_count = config.clusters * (config.units_per_cluster + 2)
    unit_stages: dict[str, WorkStage] = {}
    unit_clusters: dict[str, str] = {}
    for cluster in range(config.clusters):
        cluster_id = f"synthetic-cluster:{cluster:04d}"
        audit_units = []
        for index in range(config.units_per_cluster):
            unit_id = f"synthetic-audit:{cluster:04d}:{index:04d}"
            audit_units.append(unit_id)
            unit_stages[unit_id] = WorkStage.PACKAGE_AUDIT
            unit_clusters[unit_id] = cluster_id
            queue.enqueue(
                unit_id,
                kind=WorkStage.PACKAGE_AUDIT.value,
                cluster_id=cluster_id,
                input_digest=_digest(f"input:{unit_id}"),
            )
        reconciliation_id = f"synthetic-reconciliation:{cluster:04d}"
        unit_stages[reconciliation_id] = WorkStage.CLUSTER_RECONCILIATION
        unit_clusters[reconciliation_id] = cluster_id
        queue.enqueue(
            reconciliation_id,
            kind=WorkStage.CLUSTER_RECONCILIATION.value,
            cluster_id=cluster_id,
            input_digest=_digest(f"input:{reconciliation_id}"),
        )
        for audit_id in audit_units:
            queue.add_dependency(
                reconciliation_id,
                audit_id,
                revision="synthetic-acceptance-v1",
                digest=_digest(f"output:{audit_id}"),
            )
        implementation_id = f"synthetic-implementation:{cluster:04d}"
        unit_stages[implementation_id] = WorkStage.CLUSTER_IMPLEMENTATION
        unit_clusters[implementation_id] = cluster_id
        queue.enqueue(
            implementation_id,
            kind=WorkStage.CLUSTER_IMPLEMENTATION.value,
            cluster_id=cluster_id,
            input_digest=_digest(f"input:{implementation_id}"),
        )
        queue.add_dependency(
            implementation_id,
            reconciliation_id,
            revision="synthetic-acceptance-v1",
            digest=_digest(f"output:{reconciliation_id}"),
        )

    generator = random.Random(config.seed)
    attempt_count = 0
    injected_crashes = 0
    recovered_attempts = 0
    stale_writers_fenced = 0
    max_implementation_debt_clusters = 0
    reconciled_clusters: set[str] = set()
    implemented_clusters: set[str] = set()
    rounds = 0
    while any(unit.status is not WorkUnitStatus.COMPLETED for unit in queue.snapshot().units):
        rounds += 1
        if rounds > config.max_rounds:
            raise RuntimeError("synthetic acceptance did not converge within max_rounds")
        owners = [f"synthetic-worker:{index:02d}" for index in range(config.workers)]
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            leases = tuple(
                lease
                for lease in executor.map(
                    lambda owner: Queue(database, attempts_root).claim(
                        owner,
                        allowed_kinds=tuple(
                            stage.value
                            for stage in WorkStage
                            if stage is not WorkStage.PACKAGE_ANALYSIS
                        ),
                    ),
                    owners,
                )
                if lease is not None
            )
        if not leases:
            raise RuntimeError("synthetic queue stalled before completion")
        if len({lease.unit_id for lease in leases}) != len(leases):
            raise RuntimeError("overlapping leases were issued")
        attempt_count += len(leases)
        crashed = []
        for lease in sorted(leases, key=lambda item: item.unit_id):
            if (
                injected_crashes < config.forced_initial_crashes
                or generator.random() < config.crash_probability
            ):
                crashed.append(lease)
                injected_crashes += 1
            else:
                stage = unit_stages[lease.unit_id]
                cluster_id = unit_clusters[lease.unit_id]
                _finish_synthetic_stage(queue, lease, stage, cluster_id)
                if stage is WorkStage.CLUSTER_RECONCILIATION:
                    reconciled_clusters.add(cluster_id)
                elif stage is WorkStage.CLUSTER_IMPLEMENTATION:
                    implemented_clusters.add(cluster_id)
                debt_clusters = reconciled_clusters - implemented_clusters
                max_implementation_debt_clusters = max(
                    max_implementation_debt_clusters,
                    len(debt_clusters),
                )
                if len(debt_clusters) > 1:
                    raise RuntimeError("multiple clusters accumulated implementation debt")
        if crashed:
            with closing(sqlite3.connect(database)) as connection, connection:
                updated = connection.executemany(
                    "UPDATE leases SET expires_at = 1 WHERE lease_id = ?",
                    ((lease.lease_id,) for lease in crashed),
                )
                if updated.rowcount != len(crashed):
                    raise RuntimeError("crash injection lost a live lease")
            recovered_attempts += queue.recover()
            for lease in crashed:
                try:
                    queue.finish(lease, TerminalOutcome.FAILED)
                except StaleLeaseError:
                    stale_writers_fenced += 1
                else:  # pragma: no cover - a failed fence is the harness failure
                    raise RuntimeError("recovered worker was not fenced")

    snapshot = queue.snapshot()
    if len(snapshot.units) != unit_count or any(
        unit.status is not WorkUnitStatus.COMPLETED for unit in snapshot.units
    ):
        raise RuntimeError("synthetic queue did not converge exactly")
    workspace_count = sum(1 for unit in attempts_root.iterdir() for child in unit.iterdir())
    if workspace_count != attempt_count:
        raise RuntimeError("an attempt workspace was lost or overwritten")
    return SyntheticAcceptanceReport(
        seed=config.seed,
        unit_count=unit_count,
        attempt_count=attempt_count,
        injected_crashes=injected_crashes,
        recovered_attempts=recovered_attempts,
        stale_writers_fenced=stale_writers_fenced,
        max_implementation_debt_clusters=max_implementation_debt_clusters,
        rounds=rounds,
        final_generation=snapshot.generation_id,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _finish_synthetic_stage(
    queue: Queue,
    lease: object,
    stage: WorkStage,
    cluster_id: str,
) -> None:
    """Exercise the trusted boundary without exposing it for production work."""
    if not isinstance(lease, Lease):
        raise RuntimeError("synthetic harness received an invalid lease")
    if stage.value not in {
        WorkStage.PACKAGE_AUDIT.value,
        WorkStage.CLUSTER_RECONCILIATION.value,
        WorkStage.CLUSTER_IMPLEMENTATION.value,
    }:
        raise RuntimeError("synthetic harness claimed an unexpected stage")
    queue._finish_trusted_orchestration_stage(
        lease,
        kind=stage.value,
        cluster_id=cluster_id,
        expected_input_digest=lease.input_digest,
        output_digest=_digest(f"output:{lease.unit_id}"),
        completion_revision="synthetic-acceptance-v1",
    )
