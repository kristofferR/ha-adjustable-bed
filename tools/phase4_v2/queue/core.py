"""Atomic SQLite work leasing for independent Phase 4 v2 workers.

Every path is supplied by the caller. The module has no live-database default and
never removes an attempt workspace. SQLite serializes claims; fencing tokens stop
an expired worker from publishing after another worker recovers its unit.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
import uuid
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.phase4_v2.equivalence.core import FrozenPackageRef
    from tools.phase4_v2.equivalence.plan import (
        PackageExecutionPlan,
        ValidatedPackageOutput,
    )
    from tools.phase4_v2.validator import DependencyPins

SCHEMA_REVISION = 3
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_IDENTIFIER_LENGTH = 200
_MAX_MATERIALIZED_PINS = 256
_MAX_EVENT_PAYLOAD_BYTES = 1024 * 1024
_MAX_EVENT_PAYLOAD_DEPTH = 64
_MAX_EVENT_PAYLOAD_NODES = 100_000
_MIN_PRIORITY = -(2**31)
_MAX_PRIORITY = 2**31 - 1
_MAX_TTL_SECONDS = 2**31 - 1
MAX_ACTIVE_ORCHESTRATION_CLUSTERS = 4
MAX_ACTIVE_ORCHESTRATION_LEASES_PER_CLUSTER = 8
ORCHESTRATION_PACKAGE_ANALYSIS_KIND = "validated-package-output"
ORCHESTRATION_PACKAGE_AUDIT_KIND = "phase4-v2-package-audit"
ORCHESTRATION_CLUSTER_RECONCILIATION_KIND = "phase4-v2-cluster-reconciliation"
ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND = "phase4-v2-cluster-implementation"
ORCHESTRATION_TRACKER_PUBLICATION_KIND = "phase4-v2-tracker-publication"
ORCHESTRATION_KINDS = frozenset(
    {
        ORCHESTRATION_PACKAGE_ANALYSIS_KIND,
        ORCHESTRATION_PACKAGE_AUDIT_KIND,
        ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
        ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
        ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    }
)
_TRUSTED_ORCHESTRATION_STAGE_KINDS = ORCHESTRATION_KINDS - {
    ORCHESTRATION_PACKAGE_ANALYSIS_KIND
}
_INTERNAL_EVENT_TYPES = frozenset(
    {
        "CLAIMED",
        "FINISHED",
        "LEASE_EXPIRED",
        "RENEWED",
        "BLOCKER_REQUEUED",
        "REPAIR_REQUEUED",
        "TRACKER_ALREADY_CURRENT",
        "TRACKER_PUBLISHED",
        "WORKSPACE_ALLOCATION_FAILED",
    }
)


class QueueError(RuntimeError):
    """Base error for queue operations."""


class QueueConflictError(QueueError):
    """An immutable queue definition conflicts with an existing definition."""


class StaleLeaseError(QueueError):
    """A worker no longer owns the lease identified by its fencing token."""


class DependencyNotSatisfiedError(QueueError):
    """A pinned dependency or pipeline capability is absent or changed."""


class CompletionConflictError(QueueError):
    """A unit already has a different formal completion."""


class InputDigestMismatchError(QueueError):
    """The accepted output was built from different immutable input."""


def _unsupported_schema_revision(revision: object) -> QueueError:
    message = f"unsupported queue schema revision: {revision}"
    if revision == 2:
        message += "; regenerate the queue from orchestration inputs at a new path"
    return QueueError(message)


def _encode_event_payload(payload: Mapping[str, object]) -> str:
    nodes = 0
    scalar_bytes = 0
    stack: list[tuple[object, int]] = [(payload, 1)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_EVENT_PAYLOAD_NODES:
            raise ValueError("event payload exceeds the node limit")
        if isinstance(value, dict):
            if depth > _MAX_EVENT_PAYLOAD_DEPTH:
                raise ValueError("event payload exceeds the nesting limit")
            if nodes + len(value) > _MAX_EVENT_PAYLOAD_NODES:
                raise ValueError("event payload exceeds the node limit")
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError("event payload object keys must be strings")
                if len(key) > _MAX_EVENT_PAYLOAD_BYTES:
                    raise ValueError("event payload exceeds the byte limit")
                scalar_bytes += len(key.encode("utf-8"))
                stack.append((child, depth + 1))
        elif isinstance(value, (list, tuple)):
            if depth > _MAX_EVENT_PAYLOAD_DEPTH:
                raise ValueError("event payload exceeds the nesting limit")
            if nodes + len(value) > _MAX_EVENT_PAYLOAD_NODES:
                raise ValueError("event payload exceeds the node limit")
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            if len(value) > _MAX_EVENT_PAYLOAD_BYTES:
                raise ValueError("event payload exceeds the byte limit")
            scalar_bytes += len(value.encode("utf-8"))
        elif value is None or type(value) in {bool, int, float}:
            scalar_bytes += len(str(value))
        else:
            raise ValueError(f"event payload contains unsupported type: {type(value).__name__}")
        if scalar_bytes > _MAX_EVENT_PAYLOAD_BYTES:
            raise ValueError("event payload exceeds the byte limit")
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("event payload is not valid JSON") from error
    if len(encoded.encode("utf-8")) > _MAX_EVENT_PAYLOAD_BYTES:
        raise ValueError("event payload exceeds the byte limit")
    return encoded


class ExecutionMode(StrEnum):
    """Whether the v2 queue is allowed to execute a work unit."""

    NORMAL = "NORMAL"
    LEGACY_EXTERNAL_ACTIVE = "LEGACY_EXTERNAL_ACTIVE"


class WorkUnitStatus(StrEnum):
    """Materialized scheduling state for a work unit."""

    READY = "READY"
    LEASED = "LEASED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    EXTERNAL_ACTIVE = "EXTERNAL_ACTIVE"


class TerminalOutcome(StrEnum):
    """Immutable outcome of one attempt."""

    ACCEPTED = "ACCEPTED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    INPUT_MISMATCH = "INPUT_MISMATCH"
    ABANDONED = "ABANDONED"


class FinishDisposition(StrEnum):
    """Whether a finish created or repeated a formal completion."""

    COMPLETED = "COMPLETED"
    IDEMPOTENT = "IDEMPOTENT"
    TERMINAL_ONLY = "TERMINAL_ONLY"


class InputCheckedFinishDisposition(StrEnum):
    """Result of atomically comparing input while finishing accepted output."""

    ACCEPTED = "ACCEPTED"
    INPUT_MISMATCH = "INPUT_MISMATCH"


@dataclass(frozen=True, slots=True)
class Lease:
    """The complete capability needed to mutate one leased attempt."""

    unit_id: str
    attempt_id: str
    lease_id: str
    owner: str
    fencing_token: int
    expires_at: int
    input_digest: str
    workspace: Path


@dataclass(frozen=True, slots=True)
class FinishResult:
    """Result of recording an attempt terminal."""

    disposition: FinishDisposition
    unit_id: str
    attempt_id: str
    output_digest: str | None


@dataclass(frozen=True, slots=True)
class InputCheckedFinishResult:
    """Atomic accepted finish or preserved input-mismatch terminal."""

    disposition: InputCheckedFinishDisposition
    finish_result: FinishResult


@dataclass(frozen=True, slots=True)
class CapabilityPin:
    """One exact immutable pipeline-capability requirement."""

    capability: str
    revision: str
    digest: str


@dataclass(frozen=True, slots=True)
class CompletionDependencyPin:
    """One exact immutable formal-completion dependency."""

    parent_unit_id: str
    revision: str
    digest: str


@dataclass(frozen=True, slots=True)
class WorkUnitSnapshot:
    """Deterministic tracker state for one immutable work unit."""

    unit_id: str
    kind: str
    cluster_id: str | None
    priority: int
    ordinal: int
    execution_mode: ExecutionMode
    status: WorkUnitStatus
    input_digest: str
    attempt_count: int
    latest_outcome: TerminalOutcome | None
    completion_revision: str | None
    output_digest: str | None
    dependency_count: int
    capability_count: int

    def as_dict(self) -> dict[str, object]:
        """Return the canonical public representation."""
        return {
            "unit_id": self.unit_id,
            "kind": self.kind,
            "cluster_id": self.cluster_id,
            "priority": self.priority,
            "ordinal": self.ordinal,
            "execution_mode": self.execution_mode,
            "status": self.status,
            "input_digest": self.input_digest,
            "attempt_count": self.attempt_count,
            "latest_outcome": self.latest_outcome,
            "completion_revision": self.completion_revision,
            "output_digest": self.output_digest,
            "dependency_count": self.dependency_count,
            "capability_count": self.capability_count,
        }


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    """One consistent SQLite read watermark for tracker generation."""

    schema_revision: int
    event_watermark: int
    scheduler_state_digest: str
    generation_id: str
    units: tuple[WorkUnitSnapshot, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the canonical public representation."""
        return {
            "schema_revision": self.schema_revision,
            "event_watermark": self.event_watermark,
            "scheduler_state_digest": self.scheduler_state_digest,
            "generation_id": self.generation_id,
            "units": [unit.as_dict() for unit in self.units],
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    revision INTEGER NOT NULL,
    attempts_root TEXT NOT NULL,
    attempts_device INTEGER NOT NULL,
    attempts_inode INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    database_path TEXT NOT NULL,
    database_device INTEGER NOT NULL,
    database_inode INTEGER NOT NULL,
    parent_identities TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_units (
    unit_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    cluster_id TEXT,
    priority INTEGER NOT NULL,
    ordinal INTEGER NOT NULL UNIQUE,
    execution_mode TEXT NOT NULL CHECK (
        execution_mode IN ('NORMAL', 'LEGACY_EXTERNAL_ACTIVE')
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'READY', 'LEASED', 'REPAIR_REQUIRED', 'BLOCKED',
            'COMPLETED', 'EXTERNAL_ACTIVE'
        )
    ),
    input_digest TEXT NOT NULL CHECK (length(input_digest) = 64),
    fencing_generation INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS pipeline_capabilities (
    capability TEXT NOT NULL,
    revision TEXT NOT NULL,
    digest TEXT NOT NULL CHECK (length(digest) = 64),
    accepted_at INTEGER NOT NULL DEFAULT (unixepoch()),
    PRIMARY KEY (capability, revision)
);

CREATE UNIQUE INDEX IF NOT EXISTS pipeline_capabilities_exact_pin
    ON pipeline_capabilities(capability, revision, digest);

CREATE TABLE IF NOT EXISTS pipeline_capability_activations (
    activation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    revision TEXT NOT NULL,
    digest TEXT NOT NULL CHECK (length(digest) = 64),
    activated_at INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE (capability, revision),
    FOREIGN KEY (capability, revision, digest)
        REFERENCES pipeline_capabilities(capability, revision, digest)
);

CREATE TABLE IF NOT EXISTS capability_requirements (
    unit_id TEXT NOT NULL REFERENCES work_units(unit_id),
    capability TEXT NOT NULL,
    required_revision TEXT NOT NULL,
    required_digest TEXT NOT NULL CHECK (length(required_digest) = 64),
    PRIMARY KEY (unit_id, capability)
);

CREATE TABLE IF NOT EXISTS dependencies (
    unit_id TEXT NOT NULL REFERENCES work_units(unit_id),
    parent_unit_id TEXT NOT NULL REFERENCES work_units(unit_id),
    required_revision TEXT NOT NULL,
    required_digest TEXT NOT NULL CHECK (length(required_digest) = 64),
    PRIMARY KEY (unit_id, parent_unit_id),
    CHECK (unit_id <> parent_unit_id)
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL REFERENCES work_units(unit_id),
    lease_id TEXT NOT NULL UNIQUE,
    owner TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    workspace TEXT NOT NULL UNIQUE,
    input_digest TEXT NOT NULL CHECK (length(input_digest) = 64),
    started_at INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE (unit_id, fencing_token)
);

CREATE TABLE IF NOT EXISTS leases (
    unit_id TEXT PRIMARY KEY REFERENCES work_units(unit_id),
    lease_id TEXT NOT NULL UNIQUE,
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
    owner TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    CHECK (expires_at > 0)
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS attempt_terminals (
    attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),
    outcome TEXT NOT NULL CHECK (
        outcome IN (
            'ACCEPTED', 'PARTIAL', 'BLOCKED', 'FAILED',
            'INPUT_MISMATCH', 'ABANDONED'
        )
    ),
    output_digest TEXT,
    completion_revision TEXT,
    finished_at INTEGER NOT NULL DEFAULT (unixepoch()),
    CHECK (output_digest IS NULL OR length(output_digest) = 64),
    CHECK (
        outcome <> 'ACCEPTED'
        OR (output_digest IS NOT NULL AND completion_revision IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS formal_completions (
    unit_id TEXT PRIMARY KEY REFERENCES work_units(unit_id),
    attempt_id TEXT NOT NULL UNIQUE REFERENCES attempts(attempt_id),
    output_digest TEXT NOT NULL CHECK (length(output_digest) = 64),
    completion_revision TEXT NOT NULL,
    completed_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS work_units_schedule
    ON work_units(status, execution_mode, priority DESC, ordinal, unit_id);
CREATE INDEX IF NOT EXISTS dependencies_child ON dependencies(unit_id);
CREATE INDEX IF NOT EXISTS capability_requirements_unit
    ON capability_requirements(unit_id);
CREATE INDEX IF NOT EXISTS pipeline_capability_activations_head
    ON pipeline_capability_activations(capability, activation_id DESC);

CREATE TRIGGER IF NOT EXISTS attempts_no_update
BEFORE UPDATE ON attempts BEGIN SELECT RAISE(ABORT, 'attempts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS attempts_no_delete
BEFORE DELETE ON attempts BEGIN SELECT RAISE(ABORT, 'attempts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;
CREATE TRIGGER IF NOT EXISTS terminals_no_update
BEFORE UPDATE ON attempt_terminals
BEGIN SELECT RAISE(ABORT, 'attempt terminals are immutable'); END;
CREATE TRIGGER IF NOT EXISTS terminals_no_delete
BEFORE DELETE ON attempt_terminals
BEGIN SELECT RAISE(ABORT, 'attempt terminals are immutable'); END;
CREATE TRIGGER IF NOT EXISTS completions_no_update
BEFORE UPDATE ON formal_completions
BEGIN SELECT RAISE(ABORT, 'formal completions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS completions_no_delete
BEFORE DELETE ON formal_completions
BEGIN SELECT RAISE(ABORT, 'formal completions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS dependencies_no_update
BEFORE UPDATE ON dependencies
BEGIN SELECT RAISE(ABORT, 'dependencies are immutable'); END;
CREATE TRIGGER IF NOT EXISTS dependencies_no_delete
BEFORE DELETE ON dependencies
BEGIN SELECT RAISE(ABORT, 'dependencies are immutable'); END;
CREATE TRIGGER IF NOT EXISTS capability_requirements_no_update
BEFORE UPDATE ON capability_requirements
BEGIN SELECT RAISE(ABORT, 'capability requirements are immutable'); END;
CREATE TRIGGER IF NOT EXISTS capability_requirements_no_delete
BEFORE DELETE ON capability_requirements
BEGIN SELECT RAISE(ABORT, 'capability requirements are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pipeline_capabilities_no_update
BEFORE UPDATE ON pipeline_capabilities
BEGIN SELECT RAISE(ABORT, 'pipeline capabilities are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pipeline_capabilities_no_delete
BEFORE DELETE ON pipeline_capabilities
BEGIN SELECT RAISE(ABORT, 'pipeline capabilities are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pipeline_capability_activations_no_update
BEFORE UPDATE ON pipeline_capability_activations
BEGIN SELECT RAISE(ABORT, 'pipeline capability activations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pipeline_capability_activations_no_delete
BEFORE DELETE ON pipeline_capability_activations
BEGIN SELECT RAISE(ABORT, 'pipeline capability activations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS pipeline_capability_activations_exact_pin
BEFORE INSERT ON pipeline_capability_activations
WHEN NOT EXISTS (
    SELECT 1 FROM pipeline_capabilities
    WHERE capability = NEW.capability
      AND revision = NEW.revision
      AND digest = NEW.digest
)
BEGIN SELECT RAISE(ABORT, 'capability activation pin is not registered'); END;
CREATE TRIGGER IF NOT EXISTS work_unit_definition_no_update
BEFORE UPDATE OF
    unit_id, kind, cluster_id, priority, ordinal, execution_mode, input_digest
ON work_units
BEGIN SELECT RAISE(ABORT, 'work unit definitions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS work_units_no_delete
BEFORE DELETE ON work_units
BEGIN SELECT RAISE(ABORT, 'work units are immutable'); END;
CREATE TRIGGER IF NOT EXISTS schema_meta_no_update
BEFORE UPDATE ON schema_meta
BEGIN SELECT RAISE(ABORT, 'schema metadata is immutable'); END;
CREATE TRIGGER IF NOT EXISTS schema_meta_no_delete
BEFORE DELETE ON schema_meta
BEGIN SELECT RAISE(ABORT, 'schema metadata is immutable'); END;
CREATE TRIGGER IF NOT EXISTS queue_identity_no_update
BEFORE UPDATE ON queue_identity
BEGIN SELECT RAISE(ABORT, 'queue identity metadata is immutable'); END;
CREATE TRIGGER IF NOT EXISTS queue_identity_no_delete
BEFORE DELETE ON queue_identity
BEGIN SELECT RAISE(ABORT, 'queue identity metadata is immutable'); END;
"""


def _schema_objects(connection: sqlite3.Connection) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (str(item[0]), str(item[1]), str(item[2]))
        for item in connection.execute(
            """
            SELECT type, name, sql FROM sqlite_master
            WHERE type IN ('table', 'index', 'trigger')
              AND name NOT LIKE 'sqlite_%'
              AND sql IS NOT NULL
            """
        )
    )


def _required_schema_objects() -> frozenset[tuple[str, str, str]]:
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(_SCHEMA)
        return _schema_objects(connection)


_REQUIRED_SCHEMA_OBJECTS = _required_schema_objects()
_TRUSTED_COMPLETION_KIND_PREFIX = "trusted-"
_RESERVED_UNIT_KINDS = {
    "package-validation-receipt:": "trusted-package-validation-receipt",
    "phase4-v2-audit:": ORCHESTRATION_PACKAGE_AUDIT_KIND,
    "phase4-v2-implementation:": ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
    "phase4-v2-publication:": ORCHESTRATION_TRACKER_PUBLICATION_KIND,
    "phase4-v2-reconciliation:": ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
}


@dataclass(frozen=True, slots=True)
class _PackageReceiptPublication:
    package_ref: FrozenPackageRef
    receipt_payload: str | bytes
    trusted_validator_revision: str
    trusted_contract_revision: str
    trusted_dependency_digests: Mapping[str, str]
    trusted_receipt_sha256: str


@dataclass(frozen=True, slots=True)
class _ValidatedPackageOutputPublication:
    output: object


@dataclass(frozen=True, slots=True)
class _OrchestrationStagePublication:
    kind: str
    cluster_id: str


class Queue:
    """A host-local, process-safe queue backed by one explicit SQLite path."""

    def __init__(
        self,
        database: Path,
        attempts_root: Path,
        *,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        normalized_database = Path(os.path.realpath(database))
        normalized_attempts_root = Path(os.path.realpath(attempts_root))
        if (
            normalized_database == normalized_attempts_root
            or normalized_database in normalized_attempts_root.parents
            or normalized_attempts_root in normalized_database.parents
        ):
            raise ValueError("database and attempts root must be separate")
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        self.database = normalized_database
        self.attempts_root = normalized_attempts_root
        self.busy_timeout_ms = busy_timeout_ms

    def initialize(self) -> None:
        """Create the explicitly configured database and attempt root."""
        self._create_directory_tree_durably(self.database.parent)
        self._create_directory_tree_durably(self.attempts_root)
        root_fd = self._open_directory_path(self.attempts_root)
        try:
            root_stat = os.fstat(root_fd)
        finally:
            os.close(root_fd)
        connection = self._connect(require_schema=False, allow_create=True)
        try:
            metadata_exists = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'schema_meta'
                """
            ).fetchone()
            if metadata_exists is not None:
                pinned = connection.execute(
                    "SELECT revision FROM schema_meta WHERE singleton = 1"
                ).fetchone()
                if pinned is not None and int(pinned["revision"]) != SCHEMA_REVISION:
                    raise _unsupported_schema_revision(pinned["revision"])
            self._enable_wal(connection)
            connection.executescript(_SCHEMA)
            identity = self._database_identity()
            existing_identity = connection.execute(
                "SELECT database_path, database_device, database_inode, parent_identities "
                "FROM queue_identity WHERE singleton = 1"
            ).fetchone()
            if existing_identity is None:
                database_path, database_device, database_inode = identity[0]
                connection.execute(
                    """
                    INSERT INTO queue_identity(
                        singleton, database_path, database_device, database_inode,
                        parent_identities
                    ) VALUES (1, ?, ?, ?, ?)
                    """,
                    (
                        database_path,
                        database_device,
                        database_inode,
                        json.dumps(identity[1:], separators=(",", ":")),
                    ),
                )
            elif self._stored_database_identity(existing_identity) != identity:
                raise QueueError("queue database or parent identity differs from initialized queue")
        finally:
            connection.close()
        with self._immediate(require_schema=False) as connection:
            existing = connection.execute(
                """
                SELECT revision, attempts_root, attempts_device, attempts_inode
                FROM schema_meta WHERE singleton = 1
                """
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO schema_meta(
                        singleton, revision, attempts_root, attempts_device, attempts_inode
                    ) VALUES (1, ?, ?, ?, ?)
                    """,
                    (
                        SCHEMA_REVISION,
                        str(self.attempts_root),
                        root_stat.st_dev,
                        root_stat.st_ino,
                    ),
                )
            elif int(existing["revision"]) != SCHEMA_REVISION:
                raise _unsupported_schema_revision(existing["revision"])
            elif (
                existing["attempts_root"],
                existing["attempts_device"],
                existing["attempts_inode"],
            ) != (str(self.attempts_root), root_stat.st_dev, root_stat.st_ino):
                raise QueueError("attempt root identity differs from initialized queue")

    def enqueue(
        self,
        unit_id: str,
        *,
        kind: str,
        input_digest: str,
        cluster_id: str | None = None,
        priority: int = 0,
        execution_mode: ExecutionMode = ExecutionMode.NORMAL,
    ) -> None:
        """Add an immutable work definition, idempotently when identical."""
        _validate_identifier(unit_id, "unit_id")
        _validate_identifier(kind, "kind")
        _validate_reserved_unit_kind(unit_id, kind)
        if cluster_id is not None:
            _validate_identifier(cluster_id, "cluster_id")
        _validate_orchestration_definition(kind, cluster_id)
        _validate_digest(input_digest, "input_digest")
        if type(priority) is not int or not _MIN_PRIORITY <= priority <= _MAX_PRIORITY:
            raise ValueError("priority must be a bounded integer")
        status = (
            WorkUnitStatus.EXTERNAL_ACTIVE
            if execution_mode is ExecutionMode.LEGACY_EXTERNAL_ACTIVE
            else WorkUnitStatus.READY
        )
        with self._immediate() as connection:
            existing = connection.execute(
                """
                SELECT kind, cluster_id, priority, execution_mode, input_digest
                FROM work_units WHERE unit_id = ?
                """,
                (unit_id,),
            ).fetchone()
            definition = (
                kind,
                cluster_id,
                priority,
                execution_mode.value,
                input_digest,
            )
            if existing is not None:
                observed = tuple(existing)
                if observed != definition:
                    raise QueueConflictError(f"work unit definition changed: {unit_id}")
                return
            ordinal_row = connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 AS ordinal FROM work_units"
            ).fetchone()
            connection.execute(
                """
                INSERT INTO work_units(
                    unit_id, kind, cluster_id, priority, ordinal,
                    execution_mode, status, input_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit_id,
                    kind,
                    cluster_id,
                    priority,
                    int(ordinal_row["ordinal"]),
                    execution_mode.value,
                    status.value,
                    input_digest,
                ),
            )

    def materialize_work_unit(
        self,
        unit_id: str,
        *,
        kind: str,
        capability_pins: Iterable[CapabilityPin] = (),
        dependency_pins: Iterable[CompletionDependencyPin] = (),
        input_digest: str | None = None,
        cluster_id: str | None = None,
        priority: int = 0,
        execution_mode: ExecutionMode = ExecutionMode.NORMAL,
    ) -> str:
        """Atomically publish one immutable work unit and its complete pin sets."""
        _validate_identifier(unit_id, "unit_id")
        _validate_identifier(kind, "kind")
        _validate_reserved_unit_kind(unit_id, kind)
        if cluster_id is not None:
            _validate_identifier(cluster_id, "cluster_id")
        _validate_orchestration_definition(kind, cluster_id)
        if type(priority) is not int or not _MIN_PRIORITY <= priority <= _MAX_PRIORITY:
            raise ValueError("priority must be a bounded integer")
        if not isinstance(execution_mode, ExecutionMode):
            raise ValueError("execution_mode must be an ExecutionMode")

        capabilities = _bounded_materialization_values(
            capability_pins,
            CapabilityPin,
            "capability_pins",
        )
        dependencies = _bounded_materialization_values(
            dependency_pins,
            CompletionDependencyPin,
            "dependency_pins",
        )
        for pin in capabilities:
            _validate_identifier(pin.capability, "capability")
            _validate_revision(pin.revision)
            _validate_digest(pin.digest, "capability digest")
        for pin in dependencies:
            _validate_identifier(pin.parent_unit_id, "parent_unit_id")
            if pin.parent_unit_id == unit_id:
                raise ValueError("work unit cannot depend on itself")
            _validate_revision(pin.revision)
            _validate_digest(pin.digest, "dependency digest")

        capabilities = tuple(sorted(capabilities, key=lambda pin: pin.capability))
        dependencies = tuple(sorted(dependencies, key=lambda pin: pin.parent_unit_id))
        _reject_duplicate_pin_keys(
            (pin.capability for pin in capabilities),
            "capability",
        )
        _reject_duplicate_pin_keys(
            (pin.parent_unit_id for pin in dependencies),
            "dependency",
        )
        if input_digest is None:
            input_digest = _derive_materialized_input_digest(
                unit_id=unit_id,
                kind=kind,
                cluster_id=cluster_id,
                priority=priority,
                execution_mode=execution_mode,
                capabilities=capabilities,
                dependencies=dependencies,
            )
        else:
            _validate_digest(input_digest, "input_digest")

        status = (
            WorkUnitStatus.EXTERNAL_ACTIVE
            if execution_mode is ExecutionMode.LEGACY_EXTERNAL_ACTIVE
            else WorkUnitStatus.READY
        )
        definition = (
            kind,
            cluster_id,
            priority,
            execution_mode.value,
            input_digest,
        )
        expected_capabilities = tuple(
            (pin.capability, pin.revision, pin.digest) for pin in capabilities
        )
        expected_dependencies = tuple(
            (pin.parent_unit_id, pin.revision, pin.digest) for pin in dependencies
        )

        with self._immediate() as connection:
            existing = connection.execute(
                """
                SELECT kind, cluster_id, priority, execution_mode, input_digest
                FROM work_units WHERE unit_id = ?
                """,
                (unit_id,),
            ).fetchone()
            if existing is not None:
                observed_capabilities = tuple(
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT capability, required_revision, required_digest
                        FROM capability_requirements
                        WHERE unit_id = ? ORDER BY capability
                        """,
                        (unit_id,),
                    ).fetchall()
                )
                observed_dependencies = tuple(
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT parent_unit_id, required_revision, required_digest
                        FROM dependencies
                        WHERE unit_id = ? ORDER BY parent_unit_id
                        """,
                        (unit_id,),
                    ).fetchall()
                )
                if (
                    tuple(existing) != definition
                    or observed_capabilities != expected_capabilities
                    or observed_dependencies != expected_dependencies
                ):
                    raise QueueConflictError(f"materialized work unit changed: {unit_id}")
                return input_digest

            ordinal_row = connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 AS ordinal FROM work_units"
            ).fetchone()
            try:
                connection.execute(
                    """
                    INSERT INTO work_units(
                        unit_id, kind, cluster_id, priority, ordinal,
                        execution_mode, status, input_digest
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        unit_id,
                        kind,
                        cluster_id,
                        priority,
                        int(ordinal_row["ordinal"]),
                        execution_mode.value,
                        status.value,
                        input_digest,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO capability_requirements(
                        unit_id, capability, required_revision, required_digest
                    ) VALUES (?, ?, ?, ?)
                    """,
                    ((unit_id, *pin) for pin in expected_capabilities),
                )
                connection.executemany(
                    """
                    INSERT INTO dependencies(
                        unit_id, parent_unit_id, required_revision, required_digest
                    ) VALUES (?, ?, ?, ?)
                    """,
                    ((unit_id, *pin) for pin in expected_dependencies),
                )
            except sqlite3.IntegrityError as error:
                raise QueueConflictError(
                    f"could not materialize work unit: {unit_id}"
                ) from error
        return input_digest

    def register_capability(self, capability: str, revision: str, digest: str) -> None:
        """Register one immutable capability revision without activating it."""
        _validate_identifier(capability, "capability")
        _validate_revision(revision)
        _validate_digest(digest, "digest")
        with self._immediate() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO pipeline_capabilities(capability, revision, digest)
                    VALUES (?, ?, ?)
                    """,
                    (capability, revision, digest),
                )
            except sqlite3.IntegrityError as error:
                existing = connection.execute(
                    """
                    SELECT digest FROM pipeline_capabilities
                    WHERE capability = ? AND revision = ?
                    """,
                    (capability, revision),
                ).fetchone()
                if existing is None or existing["digest"] != digest:
                    raise QueueConflictError(
                        f"capability revision changed: {capability}/{revision}"
                    ) from error

    def activate_capability_from_absent(
        self,
        capability: str,
        revision: str,
        digest: str,
    ) -> None:
        """CAS an absent capability head to one exact registered pin."""
        self._activate_capability(
            capability,
            revision,
            digest,
            expected_head=None,
        )

    def activate_capability(
        self,
        capability: str,
        revision: str,
        digest: str,
        *,
        expected_revision: str,
        expected_digest: str,
    ) -> None:
        """CAS the active head from one exact pin to another registered pin."""
        _validate_revision(expected_revision)
        _validate_digest(expected_digest, "expected_digest")
        self._activate_capability(
            capability,
            revision,
            digest,
            expected_head=(expected_revision, expected_digest),
        )

    def _activate_capability(
        self,
        capability: str,
        revision: str,
        digest: str,
        *,
        expected_head: tuple[str, str] | None,
    ) -> None:
        _validate_identifier(capability, "capability")
        _validate_revision(revision)
        _validate_digest(digest, "digest")
        with self._immediate() as connection:
            registered = connection.execute(
                """
                SELECT digest FROM pipeline_capabilities
                WHERE capability = ? AND revision = ?
                """,
                (capability, revision),
            ).fetchone()
            if registered is None or registered["digest"] != digest:
                raise QueueConflictError(
                    f"capability activation is not registered: {capability}/{revision}"
                )
            head = connection.execute(
                """
                SELECT revision, digest
                FROM pipeline_capability_activations
                WHERE capability = ?
                ORDER BY activation_id DESC LIMIT 1
                """,
                (capability,),
            ).fetchone()
            observed_head = tuple(head) if head is not None else (None, None)
            target_head = (revision, digest)
            if observed_head == target_head:
                return
            expected_observed = expected_head if expected_head is not None else (None, None)
            if observed_head != expected_observed:
                raise QueueConflictError(
                    f"capability head changed before activation: {capability}"
                )
            previously_activated = connection.execute(
                """
                SELECT 1 FROM pipeline_capability_activations
                WHERE capability = ? AND revision = ?
                """,
                (capability, revision),
            ).fetchone()
            if previously_activated is not None:
                raise QueueConflictError(
                    f"stale capability revision cannot be reactivated: "
                    f"{capability}/{revision}"
                )
            self._insert_capability_activation(connection, capability, revision, digest)

    def require_capability(
        self,
        unit_id: str,
        capability: str,
        *,
        revision: str,
        digest: str,
    ) -> None:
        """Pin a work unit to one exact pipeline capability."""
        _validate_identifier(unit_id, "unit_id")
        _validate_identifier(capability, "capability")
        _validate_revision(revision)
        _validate_digest(digest, "digest")
        with self._immediate() as connection:
            self._require_unstarted(connection, unit_id)
            try:
                connection.execute(
                    """
                    INSERT INTO capability_requirements(
                        unit_id, capability, required_revision, required_digest
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (unit_id, capability, revision, digest),
                )
            except sqlite3.IntegrityError as error:
                existing = connection.execute(
                    """
                    SELECT required_revision, required_digest
                    FROM capability_requirements
                    WHERE unit_id = ? AND capability = ?
                    """,
                    (unit_id, capability),
                ).fetchone()
                if existing is None or tuple(existing) != (revision, digest):
                    raise QueueConflictError(
                        f"capability requirement changed: {unit_id}/{capability}"
                    ) from error

    def add_dependency(
        self,
        unit_id: str,
        parent_unit_id: str,
        *,
        revision: str,
        digest: str,
    ) -> None:
        """Require one exact formal completion before a unit may run."""
        _validate_identifier(unit_id, "unit_id")
        _validate_identifier(parent_unit_id, "parent_unit_id")
        _validate_revision(revision)
        _validate_digest(digest, "digest")
        with self._immediate() as connection:
            self._require_unstarted(connection, unit_id)
            cyclic = connection.execute(
                """
                WITH RECURSIVE reachable(unit_id) AS (
                    VALUES (?)
                    UNION
                    SELECT dependency.parent_unit_id
                    FROM dependencies AS dependency
                    JOIN reachable ON dependency.unit_id = reachable.unit_id
                )
                SELECT 1 FROM reachable WHERE unit_id = ? LIMIT 1
                """,
                (parent_unit_id, unit_id),
            ).fetchone()
            if cyclic is not None:
                raise QueueConflictError(
                    f"dependency would create a cycle: {unit_id}/{parent_unit_id}"
                )
            try:
                connection.execute(
                    """
                    INSERT INTO dependencies(
                        unit_id, parent_unit_id, required_revision, required_digest
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (unit_id, parent_unit_id, revision, digest),
                )
            except sqlite3.IntegrityError as error:
                existing = connection.execute(
                    """
                    SELECT required_revision, required_digest FROM dependencies
                    WHERE unit_id = ? AND parent_unit_id = ?
                    """,
                    (unit_id, parent_unit_id),
                ).fetchone()
                if existing is None or tuple(existing) != (revision, digest):
                    raise QueueConflictError(
                        f"dependency changed: {unit_id}/{parent_unit_id}"
                    ) from error

    def claim(
        self,
        owner: str,
        *,
        ttl_seconds: int = 1_800,
        allowed_kinds: Iterable[str] | None = None,
    ) -> Lease | None:
        """Atomically claim the first eligible work unit."""
        _validate_owner(owner)
        _validate_ttl(ttl_seconds)
        kinds = _validate_allowed_kinds(allowed_kinds)
        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            return None
        try:
            return self._claim_with_publication_guard(owner, ttl_seconds, kinds)
        finally:
            os.close(guard)

    def _claim_with_publication_guard(
        self,
        owner: str,
        ttl_seconds: int,
        allowed_kinds: tuple[str, ...] | None,
    ) -> Lease | None:
        with self._immediate() as connection:
            self._recover_expired(connection)
            kind_filter = ""
            parameters: dict[str, object] = {
                "implementation_kind": ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND,
                "max_active_clusters": MAX_ACTIVE_ORCHESTRATION_CLUSTERS,
                "max_leases_per_cluster": MAX_ACTIVE_ORCHESTRATION_LEASES_PER_CLUSTER,
                "publication_kind": ORCHESTRATION_TRACKER_PUBLICATION_KIND,
                "reconciliation_kind": ORCHESTRATION_CLUSTER_RECONCILIATION_KIND,
            }
            if allowed_kinds is not None:
                allowed_names = tuple(
                    f"allowed_kind_{index}" for index in range(len(allowed_kinds))
                )
                placeholders = ",".join(f":{name}" for name in allowed_names)
                kind_filter = f" AND unit.kind IN ({placeholders})"
                parameters.update(zip(allowed_names, allowed_kinds, strict=True))
            orchestration_kinds = tuple(sorted(ORCHESTRATION_KINDS))
            orchestration_names = tuple(
                f"orchestration_kind_{index}" for index in range(len(orchestration_kinds))
            )
            orchestration_values = ",".join(f"(:{name})" for name in orchestration_names)
            parameters.update(zip(orchestration_names, orchestration_kinds, strict=True))
            row = connection.execute(
                f"""
                WITH orchestration_kinds(kind) AS (VALUES {orchestration_values})
                SELECT unit_id, input_digest, fencing_generation
                FROM work_units AS unit
                WHERE unit.status = 'READY'
                  AND unit.execution_mode = 'NORMAL'
                  {kind_filter}
                  AND NOT EXISTS (
                      SELECT 1 FROM leases WHERE leases.unit_id = unit.unit_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM dependencies AS dependency
                      LEFT JOIN formal_completions AS completion
                        ON completion.unit_id = dependency.parent_unit_id
                      WHERE dependency.unit_id = unit.unit_id
                        AND (
                            completion.unit_id IS NULL
                            OR completion.completion_revision <> dependency.required_revision
                            OR completion.output_digest <> dependency.required_digest
                        )
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM capability_requirements AS requirement
                      LEFT JOIN pipeline_capability_activations AS activation
                        ON activation.capability = requirement.capability
                       AND activation.revision = requirement.required_revision
                       AND activation.digest = requirement.required_digest
                       AND activation.activation_id = (
                           SELECT MAX(candidate.activation_id)
                           FROM pipeline_capability_activations AS candidate
                           WHERE candidate.capability = requirement.capability
                       )
                      WHERE requirement.unit_id = unit.unit_id
                        AND activation.capability IS NULL
                  )
                  AND (
                      unit.cluster_id IS NULL
                      OR unit.kind NOT IN (SELECT kind FROM orchestration_kinds)
                      OR (
                          (
                              EXISTS (
                                  SELECT 1
                                  FROM leases AS active
                                  JOIN work_units AS active_unit
                                    ON active_unit.unit_id = active.unit_id
                                  WHERE active_unit.cluster_id = unit.cluster_id
                                    AND active_unit.kind IN (SELECT kind FROM orchestration_kinds)
                              )
                              OR (
                                  SELECT COUNT(DISTINCT active_unit.cluster_id)
                                  FROM leases AS active
                                  JOIN work_units AS active_unit
                                    ON active_unit.unit_id = active.unit_id
                                  WHERE active_unit.cluster_id IS NOT NULL
                                    AND active_unit.kind IN (SELECT kind FROM orchestration_kinds)
                              ) < :max_active_clusters
                          )
                          AND (
                              SELECT COUNT(*)
                              FROM leases AS active
                              JOIN work_units AS active_unit
                                ON active_unit.unit_id = active.unit_id
                              WHERE active_unit.cluster_id = unit.cluster_id
                                AND active_unit.kind IN (SELECT kind FROM orchestration_kinds)
                          ) < :max_leases_per_cluster
                      )
                  )
                  AND (
                      unit.kind <> :reconciliation_kind
                      OR (
                          NOT EXISTS (
                              SELECT 1
                              FROM leases AS active_reconciliation
                              JOIN work_units AS reconciliation
                                ON reconciliation.unit_id = active_reconciliation.unit_id
                              WHERE reconciliation.kind = :reconciliation_kind
                                AND reconciliation.cluster_id <> unit.cluster_id
                          )
                          AND NOT EXISTS (
                              SELECT 1
                              FROM formal_completions AS completed_reconciliation
                              JOIN work_units AS reconciliation
                                ON reconciliation.unit_id = completed_reconciliation.unit_id
                              WHERE reconciliation.kind = :reconciliation_kind
                                AND reconciliation.cluster_id <> unit.cluster_id
                                AND NOT EXISTS (
                                    SELECT 1
                                    FROM work_units AS implementation
                                    JOIN formal_completions AS completed_implementation
                                      ON completed_implementation.unit_id = implementation.unit_id
                                    WHERE implementation.kind = :implementation_kind
                                      AND implementation.cluster_id = reconciliation.cluster_id
                                )
                            )
                      )
                  )
                  AND (
                      unit.kind <> :implementation_kind
                      OR EXISTS (
                          SELECT 1
                          FROM work_units AS reconciliation
                          JOIN formal_completions AS completed_reconciliation
                            ON completed_reconciliation.unit_id = reconciliation.unit_id
                          WHERE reconciliation.kind = :reconciliation_kind
                            AND reconciliation.cluster_id = unit.cluster_id
                      )
                  )
                  AND (
                      unit.kind <> :publication_kind
                      OR EXISTS (
                          SELECT 1
                          FROM work_units AS implementation
                          JOIN formal_completions AS completed_implementation
                            ON completed_implementation.unit_id = implementation.unit_id
                          WHERE implementation.kind = :implementation_kind
                            AND implementation.cluster_id = unit.cluster_id
                      )
                  )
                ORDER BY unit.priority DESC, unit.ordinal, unit.unit_id
                LIMIT 1
                """,
                parameters,
            ).fetchone()
            if row is None:
                return None

            unit_id = str(row["unit_id"])
            fencing_token = int(row["fencing_generation"]) + 1
            attempt_id = uuid.uuid4().hex
            lease_id = uuid.uuid4().hex
            workspace = self.attempts_root / unit_id / attempt_id
            connection.execute(
                """
                UPDATE work_units
                SET fencing_generation = ?, status = 'LEASED'
                WHERE unit_id = ? AND status = 'READY'
                """,
                (fencing_token, unit_id),
            )
            connection.execute(
                """
                INSERT INTO attempts(
                    attempt_id, unit_id, lease_id, owner, fencing_token, workspace, input_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    unit_id,
                    lease_id,
                    owner,
                    fencing_token,
                    str(workspace),
                    str(row["input_digest"]),
                ),
            )
            expiry_row = connection.execute(
                """
                SELECT CAST(unixepoch('subsec') * 1000 AS INTEGER) + (? * 1000)
                    AS expires_at
                """,
                (ttl_seconds,),
            ).fetchone()
            expires_at = int(expiry_row["expires_at"])
            connection.execute(
                """
                INSERT INTO leases(
                    unit_id, lease_id, attempt_id, owner, fencing_token, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (unit_id, lease_id, attempt_id, owner, fencing_token, expires_at),
            )
            self._append_event(
                connection,
                attempt_id,
                "CLAIMED",
                {"fencing_token": fencing_token},
            )
            lease = Lease(
                unit_id=unit_id,
                attempt_id=attempt_id,
                lease_id=lease_id,
                owner=owner,
                fencing_token=fencing_token,
                expires_at=expires_at,
                input_digest=str(row["input_digest"]),
                workspace=workspace,
            )
        try:
            self._create_workspace(lease)
        except BaseException as error:
            try:
                self._record_workspace_failure(lease)
            except BaseException as record_error:
                raise record_error from error
            if not isinstance(error, Exception):
                raise
            raise QueueError(f"could not create attempt workspace: {workspace}") from error
        dependencies_changed = False
        with self._immediate() as connection:
            self._require_live_lease(connection, lease)
            if not self._dependencies_satisfied(connection, lease.unit_id):
                connection.execute(
                    """
                    INSERT INTO attempt_terminals(attempt_id, outcome)
                    VALUES (?, 'INPUT_MISMATCH')
                    """,
                    (lease.attempt_id,),
                )
                self._append_event(
                    connection,
                    lease.attempt_id,
                    "FINISHED",
                    {"outcome": TerminalOutcome.INPUT_MISMATCH},
                )
                connection.execute("DELETE FROM leases WHERE unit_id = ?", (lease.unit_id,))
                connection.execute(
                    "UPDATE work_units SET status = 'REPAIR_REQUIRED' WHERE unit_id = ?",
                    (lease.unit_id,),
                )
                dependencies_changed = True
        if dependencies_changed:
            raise DependencyNotSatisfiedError(
                f"dependencies changed during workspace publication: {lease.unit_id}"
            )
        return lease

    def renew(self, lease: Lease, *, ttl_seconds: int = 1_800) -> Lease:
        """Renew a live lease using SQLite's clock."""
        _validate_ttl(ttl_seconds)
        with self._immediate() as connection:
            self._require_live_lease(connection, lease)
            expiry_row = connection.execute(
                """
                SELECT CAST(unixepoch('subsec') * 1000 AS INTEGER) + (? * 1000)
                    AS expires_at
                """,
                (ttl_seconds,),
            ).fetchone()
            expires_at = int(expiry_row["expires_at"])
            updated = connection.execute(
                """
                UPDATE leases SET expires_at = MAX(expires_at, ?)
                WHERE unit_id = ? AND lease_id = ? AND attempt_id = ?
                  AND owner = ? AND fencing_token = ?
                  AND expires_at > CAST(unixepoch('subsec') * 1000 AS INTEGER)
                """,
                (
                    expires_at,
                    lease.unit_id,
                    lease.lease_id,
                    lease.attempt_id,
                    lease.owner,
                    lease.fencing_token,
                ),
            )
            if updated.rowcount != 1:
                raise StaleLeaseError(f"lease expired: {lease.unit_id}")
            renewed_row = connection.execute(
                """
                SELECT live.expires_at, attempt.input_digest, attempt.workspace
                FROM leases AS live
                JOIN attempts AS attempt ON attempt.attempt_id = live.attempt_id
                WHERE live.unit_id = ?
                """,
                (lease.unit_id,),
            ).fetchone()
            if renewed_row is None:
                raise StaleLeaseError(f"lease disappeared while renewing: {lease.unit_id}")
            expires_at = int(renewed_row["expires_at"])
            self._append_event(connection, lease.attempt_id, "RENEWED", {})
            return Lease(
                unit_id=lease.unit_id,
                attempt_id=lease.attempt_id,
                lease_id=lease.lease_id,
                owner=lease.owner,
                fencing_token=lease.fencing_token,
                expires_at=expires_at,
                input_digest=str(renewed_row["input_digest"]),
                workspace=Path(str(renewed_row["workspace"])),
            )

    def checkpoint(
        self,
        lease: Lease,
        event_type: str,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        """Append a milestone for a live fenced attempt."""
        _validate_identifier(event_type, "event_type")
        if event_type in _INTERNAL_EVENT_TYPES:
            raise ValueError(f"event type is reserved for queue internals: {event_type}")
        encoded = _encode_event_payload(payload or {})
        with self._immediate() as connection:
            self._require_live_lease(connection, lease)
            self._append_encoded_event(connection, lease.attempt_id, event_type, encoded)

    def _checkpoint_internal(
        self,
        lease: Lease,
        event_type: str,
        payload: Mapping[str, object],
    ) -> None:
        if event_type not in _INTERNAL_EVENT_TYPES:
            raise ValueError(f"event type is not reserved for queue internals: {event_type}")
        encoded = _encode_event_payload(payload)
        with self._immediate() as connection:
            self._require_live_lease(connection, lease)
            self._append_encoded_event(connection, lease.attempt_id, event_type, encoded)

    def finish(
        self,
        lease: Lease,
        outcome: TerminalOutcome,
        *,
        output_digest: str | None = None,
        completion_revision: str | None = None,
        expected_input_digest: str | None = None,
    ) -> FinishResult:
        """Record an immutable terminal and, for ACCEPTED, formal completion."""
        if outcome is TerminalOutcome.ACCEPTED:
            if output_digest is None or completion_revision is None:
                raise ValueError("accepted attempts require output digest and revision")
            _validate_digest(output_digest, "output_digest")
            _validate_revision(completion_revision)
            if expected_input_digest is not None:
                _validate_digest(expected_input_digest, "expected_input_digest")
        elif output_digest is not None:
            _validate_digest(output_digest, "output_digest")
        if outcome is not TerminalOutcome.ACCEPTED and expected_input_digest is not None:
            raise ValueError("expected input digest is only valid for accepted attempts")
        if completion_revision is not None:
            _validate_revision(completion_revision)

        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented attempt completion")
        try:
            return self._finish_with_publication_guard(
                lease,
                outcome,
                output_digest=output_digest,
                completion_revision=completion_revision,
                expected_input_digest=expected_input_digest,
                terminalize_input_mismatch=False,
                trusted_publication=None,
            )
        finally:
            os.close(guard)

    def finish_accepted_if_input_matches(
        self,
        lease: Lease,
        *,
        expected_input_digest: str,
        output_digest: str,
        completion_revision: str,
    ) -> InputCheckedFinishResult:
        """Atomically accept matching input or preserve an INPUT_MISMATCH output."""
        _validate_digest(expected_input_digest, "expected_input_digest")
        _validate_digest(output_digest, "output_digest")
        _validate_revision(completion_revision)

        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented attempt completion")
        try:
            result = self._finish_with_publication_guard(
                lease,
                TerminalOutcome.ACCEPTED,
                output_digest=output_digest,
                completion_revision=completion_revision,
                expected_input_digest=expected_input_digest,
                terminalize_input_mismatch=True,
                trusted_publication=None,
            )
        finally:
            os.close(guard)
        return InputCheckedFinishResult(
            disposition=(
                InputCheckedFinishDisposition.INPUT_MISMATCH
                if result.disposition is FinishDisposition.TERMINAL_ONLY
                else InputCheckedFinishDisposition.ACCEPTED
            ),
            finish_result=result,
        )

    def _finish_trusted_orchestration_stage(
        self,
        lease: Lease,
        *,
        kind: str,
        cluster_id: str,
        expected_input_digest: str,
        output_digest: str,
        completion_revision: str,
    ) -> InputCheckedFinishResult:
        """Publish one typed orchestration receipt through a stage adapter."""
        if kind not in _TRUSTED_ORCHESTRATION_STAGE_KINDS:
            raise QueueConflictError("kind has no trusted orchestration-stage adapter")
        _validate_identifier(cluster_id, "cluster_id")
        _validate_digest(expected_input_digest, "expected_input_digest")
        _validate_digest(output_digest, "output_digest")
        _validate_revision(completion_revision)
        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented attempt completion")
        try:
            result = self._finish_with_publication_guard(
                lease,
                TerminalOutcome.ACCEPTED,
                output_digest=output_digest,
                completion_revision=completion_revision,
                expected_input_digest=expected_input_digest,
                terminalize_input_mismatch=True,
                trusted_publication=_OrchestrationStagePublication(kind, cluster_id),
            )
        finally:
            os.close(guard)
        return InputCheckedFinishResult(
            disposition=(
                InputCheckedFinishDisposition.INPUT_MISMATCH
                if result.disposition is FinishDisposition.TERMINAL_ONLY
                else InputCheckedFinishDisposition.ACCEPTED
            ),
            finish_result=result,
        )

    def finish_input_mismatch_if_input_changed(
        self,
        lease: Lease,
        *,
        expected_input_digest: str,
    ) -> FinishResult:
        """Record an input mismatch only when the leased input has changed."""
        _validate_digest(expected_input_digest, "expected_input_digest")
        with self._connect() as connection:
            self._require_live_lease(connection, lease)
            if self._input_digests_match(connection, lease, expected_input_digest):
                raise QueueConflictError(
                    f"leased input already matches the expected digest: {lease.unit_id}"
                )
        return self.finish(lease, TerminalOutcome.INPUT_MISMATCH)

    def finish_package_validation_receipt(
        self,
        lease: Lease,
        *,
        package_ref: FrozenPackageRef,
        receipt_payload: str | bytes,
        trusted_validator_revision: str,
        trusted_contract_revision: str,
        trusted_dependency_digests: Mapping[str, str],
        trusted_receipt_sha256: str,
    ) -> FinishResult:
        """Validate and publish one reserved package receipt as a single operation."""
        from tools.phase4_v2.equivalence.plan import (
            PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
            package_validation_receipt_completion,
        )

        completion = package_validation_receipt_completion(package_ref)
        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented attempt completion")
        try:
            return self._finish_with_publication_guard(
                lease,
                TerminalOutcome.ACCEPTED,
                output_digest=completion.digest,
                completion_revision=PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
                expected_input_digest=completion.digest,
                terminalize_input_mismatch=False,
                trusted_publication=_PackageReceiptPublication(
                    package_ref=package_ref,
                    receipt_payload=receipt_payload,
                    trusted_validator_revision=trusted_validator_revision,
                    trusted_contract_revision=trusted_contract_revision,
                    trusted_dependency_digests=trusted_dependency_digests,
                    trusted_receipt_sha256=trusted_receipt_sha256,
                ),
            )
        finally:
            os.close(guard)

    def finish_validated_package_output(
        self,
        lease: Lease,
        *,
        execution_plan: PackageExecutionPlan,
        report_root: Path,
        trusted_dependencies: DependencyPins,
        evidence_lineage_payload: bytes,
    ) -> tuple[ValidatedPackageOutput, InputCheckedFinishResult]:
        """Validate report bytes, then publish one reserved package output."""
        from tools.phase4_v2.equivalence.plan import (
            PACKAGE_REPORT_SCHEMA_SHA256,
            VALIDATED_PACKAGE_OUTPUT_REVISION,
            build_validated_package_output,
            freeze_package_execution_plan,
        )
        from tools.phase4_v2.validator import (
            DependencyPins,
            EvidenceLineageTrust,
            PackageDependencyPins,
            TrustedProducer,
            validate_report_bundle,
        )

        if type(trusted_dependencies) is not DependencyPins:
            raise QueueConflictError("package validation requires exact trusted dependencies")
        frozen = freeze_package_execution_plan(execution_plan)
        plan_input_mismatch = frozen.digest != lease.input_digest
        if plan_input_mismatch:
            with self._connect() as connection:
                self._require_live_lease(connection, lease)
                if self._input_digests_match(connection, lease, frozen.digest):
                    raise QueueConflictError(
                        f"lease input digest is inconsistent: {lease.unit_id}"
                    )
        target_preflight_sha256 = execution_plan.target_package_ref.preflight_sha256
        if type(evidence_lineage_payload) is not bytes:
            raise QueueConflictError("evidence lineage payload must be exact immutable bytes")
        try:
            receipt_dependencies = {
                name: self._trusted_receipt_dependency(
                    lease,
                    lease.input_digest,
                    execution_plan.target_package_ref.validation_receipt_sha256,
                    name,
                )
                for name in ("corpus", "evidence_lineage", "ir", "preflight", "schema")
            }
        except (DependencyNotSatisfiedError, InputDigestMismatchError):
            if not plan_input_mismatch:
                raise
            self.finish_input_mismatch_if_input_changed(
                lease,
                expected_input_digest=frozen.digest,
            )
            raise InputDigestMismatchError(
                f"package plan does not match the leased queue input: {lease.unit_id}"
            ) from None
        if receipt_dependencies["preflight"] != target_preflight_sha256:
            raise QueueConflictError(
                "trusted receipt preflight does not match the package execution plan"
            )
        lineage_digest = receipt_dependencies["evidence_lineage"]
        producer_pins = {
            (capability.revision, capability.name, capability.digest)
            for capability in frozen.required_capabilities
        }
        trusted_evidence_lineage = EvidenceLineageTrust(
            payload=evidence_lineage_payload,
            expected_manifest_sha256=lineage_digest,
            trusted_producers=tuple(
                TrustedProducer(revision, route, digest)
                for revision, route, digest in sorted(producer_pins)
            ),
        )
        receipt = validate_report_bundle(
            report_root,
            expected_dependencies=PackageDependencyPins(
                preflight_sha256=target_preflight_sha256,
                ir_sha256=receipt_dependencies["ir"],
                schema_sha256=receipt_dependencies["schema"],
                corpus_sha256=receipt_dependencies["corpus"],
                execution_plan_sha256=frozen.digest,
                report_schema_sha256=PACKAGE_REPORT_SCHEMA_SHA256,
            ),
            expected_evidence_lineage=trusted_evidence_lineage,
        )
        receipt_sha256 = receipt.validation_receipt_sha256
        if receipt_sha256 is None:
            raise QueueConflictError("validator returned an unidentified package receipt")
        output = build_validated_package_output(
            execution_plan=execution_plan,
            receipt=receipt,
            trusted_validation_receipt_sha256=receipt_sha256,
        )
        if plan_input_mismatch or output.execution_plan_id != freeze_package_execution_plan(
            execution_plan
        ).digest:
            result = self.finish(
                lease,
                TerminalOutcome.INPUT_MISMATCH,
                output_digest=output.content_id,
            )
            return output, InputCheckedFinishResult(
                disposition=InputCheckedFinishDisposition.INPUT_MISMATCH,
                finish_result=result,
            )
        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented attempt completion")
        try:
            result = self._finish_with_publication_guard(
                lease,
                TerminalOutcome.ACCEPTED,
                output_digest=output.content_id,
                completion_revision=VALIDATED_PACKAGE_OUTPUT_REVISION,
                expected_input_digest=frozen.digest,
                terminalize_input_mismatch=True,
                trusted_publication=_ValidatedPackageOutputPublication(output),
            )
        finally:
            os.close(guard)
        return output, InputCheckedFinishResult(
            disposition=(
                InputCheckedFinishDisposition.INPUT_MISMATCH
                if result.disposition is FinishDisposition.TERMINAL_ONLY
                else InputCheckedFinishDisposition.ACCEPTED
            ),
            finish_result=result,
        )

    def _trusted_receipt_dependency(
        self,
        lease: Lease,
        expected_input_digest: str,
        expected_receipt_sha256: str,
        dependency_name: str,
    ) -> str:
        """Read one trust root from the exact receipt completion pinned to a lease."""
        from tools.phase4_v2.equivalence.plan import (
            PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
        )

        with self._connect() as connection:
            self._require_live_lease(connection, lease)
            if not self._input_digests_match(connection, lease, expected_input_digest):
                raise InputDigestMismatchError(
                    f"package plan does not match the leased queue input: {lease.unit_id}"
                )
            row = connection.execute(
                """
                SELECT event.payload_json
                FROM dependencies AS dependency
                JOIN work_units AS parent
                  ON parent.unit_id = dependency.parent_unit_id
                JOIN formal_completions AS completion
                  ON completion.unit_id = dependency.parent_unit_id
                 AND completion.completion_revision = dependency.required_revision
                 AND completion.output_digest = dependency.required_digest
                JOIN events AS event
                  ON event.attempt_id = completion.attempt_id
                 AND event.event_type = 'FINISHED'
                WHERE dependency.unit_id = ?
                  AND parent.kind = 'trusted-package-validation-receipt'
                  AND dependency.required_revision = ?
                  AND dependency.required_digest = ?
                """,
                (
                    lease.unit_id,
                    PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
                    expected_receipt_sha256,
                ),
            ).fetchone()
        if row is None:
            raise DependencyNotSatisfiedError(
                "package validation receipt trust roots are not pinned"
            )
        try:
            payload = json.loads(str(row["payload_json"]))
            dependencies = payload["trusted_dependency_digests"]
            digest = dependencies[dependency_name]
        except (KeyError, TypeError, ValueError) as error:
            raise QueueConflictError(
                "package validation receipt trust roots are unavailable"
            ) from error
        _validate_digest(digest, dependency_name)
        return str(digest)

    def _finish_with_publication_guard(
        self,
        lease: Lease,
        outcome: TerminalOutcome,
        *,
        output_digest: str | None,
        completion_revision: str | None,
        expected_input_digest: str | None,
        terminalize_input_mismatch: bool,
        trusted_publication: (
            _PackageReceiptPublication
            | _ValidatedPackageOutputPublication
            | _OrchestrationStagePublication
            | None
        ),
    ) -> FinishResult:
        trusted_receipt_dependencies: dict[str, str] | None = None
        if isinstance(trusted_publication, _PackageReceiptPublication):
            trusted_receipt_dependencies = self._validate_package_receipt_publication(
                lease,
                trusted_publication,
                output_digest=output_digest,
                completion_revision=completion_revision,
                expected_input_digest=expected_input_digest,
            )
        elif isinstance(trusted_publication, _ValidatedPackageOutputPublication):
            self._validate_package_output_publication(
                lease,
                trusted_publication,
                output_digest=output_digest,
                completion_revision=completion_revision,
                expected_input_digest=expected_input_digest,
            )
        elif isinstance(trusted_publication, _OrchestrationStagePublication):
            if (
                trusted_publication.kind not in _TRUSTED_ORCHESTRATION_STAGE_KINDS
                or expected_input_digest != lease.input_digest
            ):
                raise QueueConflictError("orchestration publication does not bind the lease")
        with self._immediate() as connection:
            unit = connection.execute(
                "SELECT kind, cluster_id FROM work_units WHERE unit_id = ?",
                (lease.unit_id,),
            ).fetchone()
            if unit is None:
                raise QueueError(f"unknown work unit: {lease.unit_id}")
            reserved = _requires_trusted_completion_adapter(
                lease.unit_id, str(unit["kind"])
            )
            if outcome is TerminalOutcome.ACCEPTED and reserved != (
                trusted_publication is not None
            ):
                raise QueueConflictError(
                    "reserved completion must use its trusted publication adapter"
                )
            if isinstance(trusted_publication, _OrchestrationStagePublication) and (
                str(unit["kind"]) != trusted_publication.kind
                or unit["cluster_id"] != trusted_publication.cluster_id
            ):
                raise QueueConflictError("orchestration receipt belongs to another stage")
            terminal = connection.execute(
                """
                SELECT outcome, output_digest, completion_revision
                FROM attempt_terminals WHERE attempt_id = ?
                """,
                (lease.attempt_id,),
            ).fetchone()
            if terminal is not None:
                if (
                    terminalize_input_mismatch
                    and terminal["outcome"] == TerminalOutcome.INPUT_MISMATCH.value
                ):
                    return self._repeat_finish(
                        connection,
                        lease,
                        terminal,
                        TerminalOutcome.INPUT_MISMATCH,
                        output_digest,
                        None,
                        None,
                    )
                return self._repeat_finish(
                    connection,
                    lease,
                    terminal,
                    outcome,
                    output_digest,
                    completion_revision,
                    expected_input_digest,
                )

            self._require_live_lease(connection, lease)
            if outcome is TerminalOutcome.ACCEPTED and expected_input_digest is not None:
                if not self._input_digests_match(
                    connection, lease, expected_input_digest
                ):
                    if not terminalize_input_mismatch:
                        raise InputDigestMismatchError(
                            f"accepted output input changed: {lease.unit_id}"
                        )
                    outcome = TerminalOutcome.INPUT_MISMATCH
                    completion_revision = None
            if outcome is TerminalOutcome.ACCEPTED and not self._dependencies_satisfied(
                connection, lease.unit_id
            ):
                raise DependencyNotSatisfiedError(
                    f"dependencies changed before completion: {lease.unit_id}"
                )
            if (
                outcome is TerminalOutcome.ACCEPTED
                and str(unit["kind"]) == ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND
                and not self._cluster_has_accepted_reconciliation(connection, lease.unit_id)
            ):
                raise QueueConflictError("cluster implementation requires accepted reconciliation")
            if (
                outcome is TerminalOutcome.ACCEPTED
                and str(unit["kind"]) == ORCHESTRATION_TRACKER_PUBLICATION_KIND
                and not self._cluster_has_accepted_implementation(connection, lease.unit_id)
            ):
                raise QueueConflictError("tracker publication requires accepted implementation")

            connection.execute(
                """
                INSERT INTO attempt_terminals(
                    attempt_id, outcome, output_digest, completion_revision
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    lease.attempt_id,
                    outcome.value,
                    output_digest,
                    completion_revision,
                ),
            )
            event_payload: dict[str, object] = {"outcome": outcome}
            if (
                outcome is TerminalOutcome.ACCEPTED
                and trusted_receipt_dependencies is not None
            ):
                event_payload["trusted_dependency_digests"] = dict(
                    sorted(trusted_receipt_dependencies.items())
                )
            self._append_event(connection, lease.attempt_id, "FINISHED", event_payload)

            disposition = FinishDisposition.TERMINAL_ONLY
            if outcome is TerminalOutcome.ACCEPTED:
                existing = connection.execute(
                    """
                    SELECT attempt_id, output_digest, completion_revision
                    FROM formal_completions WHERE unit_id = ?
                    """,
                    (lease.unit_id,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO formal_completions(
                            unit_id, attempt_id, output_digest, completion_revision
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            lease.unit_id,
                            lease.attempt_id,
                            output_digest,
                            completion_revision,
                        ),
                    )
                    disposition = FinishDisposition.COMPLETED
                elif (
                    existing["output_digest"],
                    existing["completion_revision"],
                ) == (output_digest, completion_revision):
                    disposition = FinishDisposition.IDEMPOTENT
                else:
                    raise CompletionConflictError(
                        f"different completion already exists: {lease.unit_id}"
                    )
                next_status = WorkUnitStatus.COMPLETED
            elif outcome is TerminalOutcome.BLOCKED:
                next_status = WorkUnitStatus.BLOCKED
            else:
                next_status = WorkUnitStatus.REPAIR_REQUIRED

            connection.execute("DELETE FROM leases WHERE unit_id = ?", (lease.unit_id,))
            connection.execute(
                "UPDATE work_units SET status = ? WHERE unit_id = ?",
                (next_status.value, lease.unit_id),
            )
            return FinishResult(
                disposition=disposition,
                unit_id=lease.unit_id,
                attempt_id=lease.attempt_id,
                output_digest=output_digest,
            )

    @staticmethod
    def _cluster_has_accepted_reconciliation(
        connection: sqlite3.Connection,
        unit_id: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM work_units AS implementation
            JOIN work_units AS reconciliation
              ON reconciliation.kind = ?
             AND reconciliation.cluster_id = implementation.cluster_id
            JOIN formal_completions AS completed_reconciliation
              ON completed_reconciliation.unit_id = reconciliation.unit_id
            WHERE implementation.unit_id = ?
              AND implementation.cluster_id IS NOT NULL
            LIMIT 1
            """,
            (ORCHESTRATION_CLUSTER_RECONCILIATION_KIND, unit_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _cluster_has_accepted_implementation(
        connection: sqlite3.Connection,
        unit_id: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM work_units AS publication
            JOIN work_units AS implementation
              ON implementation.kind = ?
             AND implementation.cluster_id = publication.cluster_id
            JOIN formal_completions AS completed_implementation
              ON completed_implementation.unit_id = implementation.unit_id
            WHERE publication.unit_id = ?
              AND publication.cluster_id IS NOT NULL
            LIMIT 1
            """,
            (ORCHESTRATION_CLUSTER_IMPLEMENTATION_KIND, unit_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _validate_package_receipt_publication(
        lease: Lease,
        publication: _PackageReceiptPublication,
        *,
        output_digest: str | None,
        completion_revision: str | None,
        expected_input_digest: str | None,
    ) -> dict[str, str]:
        from tools.phase4_v2.equivalence.plan import (
            PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION,
            package_validation_receipt_completion,
        )
        from tools.phase4_v2.ir import bind_validator_receipt

        package_ref = publication.package_ref
        completion = package_validation_receipt_completion(package_ref)
        if (
            lease.unit_id != completion.parent_unit_id
            or output_digest != completion.digest
            or completion_revision != PACKAGE_VALIDATION_RECEIPT_COMPLETION_REVISION
            or expected_input_digest != completion.digest
        ):
            raise QueueConflictError(
                "publication does not belong to the package validation receipt"
            )
        report = bind_validator_receipt(
            publication.receipt_payload,
            trusted_validator_revision=publication.trusted_validator_revision,
            trusted_contract_revision=publication.trusted_contract_revision,
            trusted_dependency_digests=publication.trusted_dependency_digests,
            trusted_receipt_sha256=publication.trusted_receipt_sha256,
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
        return dependencies

    @staticmethod
    def _validate_package_output_publication(
        lease: Lease,
        publication: _ValidatedPackageOutputPublication,
        *,
        output_digest: str | None,
        completion_revision: str | None,
        expected_input_digest: str | None,
    ) -> None:
        from tools.phase4_v2.equivalence.plan import (
            VALIDATED_PACKAGE_OUTPUT_REVISION,
            ValidatedPackageOutput,
            package_queue_unit_id,
        )

        output = publication.output
        if type(output) is not ValidatedPackageOutput or (
            lease.unit_id != package_queue_unit_id(output.target_package_ref_id)
            or output_digest != output.content_id
            or completion_revision != VALIDATED_PACKAGE_OUTPUT_REVISION
            or expected_input_digest != output.execution_plan_id
        ):
            raise QueueConflictError(
                "publication does not belong to the validated package output"
            )

    def status(self, unit_id: str) -> WorkUnitStatus:
        """Return the materialized status of one unit."""
        _validate_identifier(unit_id, "unit_id")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT status FROM work_units WHERE unit_id = ?", (unit_id,)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise QueueError(f"unknown work unit: {unit_id}")
        return WorkUnitStatus(row["status"])

    def attempt_outcome(self, attempt_id: str) -> TerminalOutcome | None:
        """Read the immutable terminal for one exact attempt, if it has one."""
        _validate_identifier(attempt_id, "attempt_id")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT outcome FROM attempt_terminals WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        finally:
            connection.close()
        return TerminalOutcome(row["outcome"]) if row is not None else None

    def retry_repaired(self, unit_id: str) -> None:
        """Return an explicitly repaired failed unit to the ready queue."""
        _validate_identifier(unit_id, "unit_id")
        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented repaired-unit retry")
        try:
            with self._immediate() as connection:
                row = connection.execute(
                    """
                    SELECT unit.status, latest.attempt_id
                    FROM work_units AS unit
                    LEFT JOIN attempts AS latest
                      ON latest.unit_id = unit.unit_id
                     AND latest.fencing_token = (
                        SELECT MAX(candidate.fencing_token)
                        FROM attempts AS candidate
                        WHERE candidate.unit_id = unit.unit_id
                     )
                    WHERE unit.unit_id = ?
                    """,
                    (unit_id,),
                ).fetchone()
                if row is None:
                    raise QueueError(f"unknown work unit: {unit_id}")
                if WorkUnitStatus(row["status"]) is not WorkUnitStatus.REPAIR_REQUIRED:
                    raise QueueConflictError(f"work unit is not repair-required: {unit_id}")
                attempt_id = row["attempt_id"]
                if attempt_id is None:
                    raise QueueError(f"repair-required unit has no recorded attempt: {unit_id}")
                self._append_event(connection, str(attempt_id), "REPAIR_REQUEUED", {})
                connection.execute(
                    "UPDATE work_units SET status = 'READY' WHERE unit_id = ?",
                    (unit_id,),
                )
        finally:
            os.close(guard)

    def retry_blocked(self, unit_id: str) -> None:
        """Return a unit whose external blocker was resolved to the ready queue."""
        _validate_identifier(unit_id, "unit_id")
        self.verify_schema()
        guard = self._try_acquire_publication_guard(wait=True)
        if guard is None:
            raise QueueConflictError("tracker publication prevented blocked-unit retry")
        try:
            with self._immediate() as connection:
                row = connection.execute(
                    """
                    SELECT unit.status, latest.attempt_id
                    FROM work_units AS unit
                    LEFT JOIN attempts AS latest
                      ON latest.unit_id = unit.unit_id
                     AND latest.fencing_token = (
                        SELECT MAX(candidate.fencing_token)
                        FROM attempts AS candidate
                        WHERE candidate.unit_id = unit.unit_id
                     )
                    WHERE unit.unit_id = ?
                    """,
                    (unit_id,),
                ).fetchone()
                if row is None:
                    raise QueueError(f"unknown work unit: {unit_id}")
                if WorkUnitStatus(row["status"]) is not WorkUnitStatus.BLOCKED:
                    raise QueueConflictError(f"work unit is not blocked: {unit_id}")
                attempt_id = row["attempt_id"]
                if attempt_id is None:
                    raise QueueError(f"blocked unit has no recorded attempt: {unit_id}")
                self._append_event(connection, str(attempt_id), "BLOCKER_REQUEUED", {})
                connection.execute(
                    "UPDATE work_units SET status = 'READY' WHERE unit_id = ?",
                    (unit_id,),
                )
        finally:
            os.close(guard)

    def recover(self) -> int:
        """Fence expired leases and return the number of recovered attempts."""
        self.verify_schema()
        guard = self._try_acquire_publication_guard()
        if guard is None:
            return 0
        try:
            with self._immediate() as connection:
                return self._recover_expired(connection)
        finally:
            os.close(guard)

    def snapshot(self) -> QueueSnapshot:
        """Read deterministic tracker state in one consistent transaction."""
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._require_schema_compatible(connection)
            metadata = connection.execute(
                "SELECT revision FROM schema_meta WHERE singleton = 1"
            ).fetchone()
            if metadata is None:
                raise QueueError("queue is not initialized")
            watermark_row = connection.execute(
                """
                SELECT COALESCE(MAX(event_id), 0) AS watermark
                FROM events
                WHERE event_type NOT IN (
                    'RENEWED', 'TRACKER_PUBLISHED', 'TRACKER_ALREADY_CURRENT'
                )
                """
            ).fetchone()
            scheduler_state = {
                "capabilities": [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT capability, revision, digest
                        FROM pipeline_capabilities
                        ORDER BY capability, revision
                        """
                    ).fetchall()
                ],
                "capability_activations": [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT capability, revision, digest
                        FROM pipeline_capability_activations
                        ORDER BY capability, activation_id
                        """
                    ).fetchall()
                ],
                "requirements": [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT unit_id, capability, required_revision, required_digest
                        FROM capability_requirements
                        ORDER BY unit_id, capability
                        """
                    ).fetchall()
                ],
                "dependencies": [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT unit_id, parent_unit_id, required_revision, required_digest
                        FROM dependencies
                        ORDER BY unit_id, parent_unit_id
                        """
                    ).fetchall()
                ],
            }
            scheduler_state_digest = hashlib.sha256(
                json.dumps(scheduler_state, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            rows = connection.execute(
                """
                SELECT
                    unit.unit_id,
                    unit.kind,
                    unit.cluster_id,
                    unit.priority,
                    unit.ordinal,
                    unit.execution_mode,
                    unit.status,
                    unit.input_digest,
                    (SELECT COUNT(*) FROM attempts AS attempt
                     WHERE attempt.unit_id = unit.unit_id) AS attempt_count,
                    terminal.outcome AS latest_outcome,
                    completion.completion_revision,
                    completion.output_digest,
                    (SELECT COUNT(*) FROM dependencies AS dependency
                     WHERE dependency.unit_id = unit.unit_id) AS dependency_count,
                    (SELECT COUNT(*) FROM capability_requirements AS requirement
                     WHERE requirement.unit_id = unit.unit_id) AS capability_count
                FROM work_units AS unit
                LEFT JOIN attempts AS latest
                  ON latest.unit_id = unit.unit_id
                 AND latest.fencing_token = (
                    SELECT MAX(candidate.fencing_token)
                    FROM attempts AS candidate
                    WHERE candidate.unit_id = unit.unit_id
                 )
                LEFT JOIN attempt_terminals AS terminal
                  ON terminal.attempt_id = latest.attempt_id
                LEFT JOIN formal_completions AS completion
                  ON completion.unit_id = unit.unit_id
                ORDER BY unit.ordinal, unit.unit_id
                """
            ).fetchall()
            units = tuple(
                WorkUnitSnapshot(
                    unit_id=str(row["unit_id"]),
                    kind=str(row["kind"]),
                    cluster_id=(str(row["cluster_id"]) if row["cluster_id"] is not None else None),
                    priority=int(row["priority"]),
                    ordinal=int(row["ordinal"]),
                    execution_mode=ExecutionMode(row["execution_mode"]),
                    status=WorkUnitStatus(row["status"]),
                    input_digest=str(row["input_digest"]),
                    attempt_count=int(row["attempt_count"]),
                    latest_outcome=(
                        TerminalOutcome(row["latest_outcome"])
                        if row["latest_outcome"] is not None
                        else None
                    ),
                    completion_revision=(
                        str(row["completion_revision"])
                        if row["completion_revision"] is not None
                        else None
                    ),
                    output_digest=(
                        str(row["output_digest"]) if row["output_digest"] is not None else None
                    ),
                    dependency_count=int(row["dependency_count"]),
                    capability_count=int(row["capability_count"]),
                )
                for row in rows
            )
            payload = {
                "schema_revision": int(metadata["revision"]),
                "event_watermark": int(watermark_row["watermark"]),
                "scheduler_state_digest": scheduler_state_digest,
                "units": [unit.as_dict() for unit in units],
            }
            generation_id = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return QueueSnapshot(
            schema_revision=int(metadata["revision"]),
            event_watermark=int(watermark_row["watermark"]),
            scheduler_state_digest=scheduler_state_digest,
            generation_id=generation_id,
            units=units,
        )

    def verify_schema(self) -> None:
        """Fail unless the database has the exact operational schema revision."""
        connection = self._connect()
        connection.close()

    def _repeat_finish(
        self,
        connection: sqlite3.Connection,
        lease: Lease,
        terminal: sqlite3.Row,
        outcome: TerminalOutcome,
        output_digest: str | None,
        completion_revision: str | None,
        expected_input_digest: str | None,
    ) -> FinishResult:
        attempt = connection.execute(
            """
            SELECT unit_id, lease_id, owner, fencing_token
            FROM attempts WHERE attempt_id = ?
            """,
            (lease.attempt_id,),
        ).fetchone()
        if attempt is None or (
            attempt["unit_id"],
            attempt["lease_id"],
            attempt["owner"],
            attempt["fencing_token"],
        ) != (lease.unit_id, lease.lease_id, lease.owner, lease.fencing_token):
            raise StaleLeaseError(f"attempt capability mismatch: {lease.unit_id}")
        if outcome is TerminalOutcome.ACCEPTED and expected_input_digest is not None:
            self._require_input_digest(connection, lease, expected_input_digest)
        observed = (
            terminal["outcome"],
            terminal["output_digest"],
            terminal["completion_revision"],
        )
        requested = (outcome.value, output_digest, completion_revision)
        if observed != requested:
            if terminal["outcome"] == TerminalOutcome.ABANDONED.value:
                raise StaleLeaseError(f"attempt lease expired: {lease.unit_id}")
            if terminal["outcome"] == TerminalOutcome.ACCEPTED.value:
                raise CompletionConflictError(
                    f"attempt already completed differently: {lease.unit_id}"
                )
            raise QueueConflictError(f"attempt already terminated differently: {lease.attempt_id}")
        return FinishResult(
            disposition=(
                FinishDisposition.IDEMPOTENT
                if outcome is TerminalOutcome.ACCEPTED
                else FinishDisposition.TERMINAL_ONLY
            ),
            unit_id=lease.unit_id,
            attempt_id=lease.attempt_id,
            output_digest=output_digest,
        )

    @staticmethod
    def _require_input_digest(
        connection: sqlite3.Connection,
        lease: Lease,
        expected_input_digest: str,
    ) -> None:
        if not Queue._input_digests_match(connection, lease, expected_input_digest):
            raise InputDigestMismatchError(
                f"accepted output input changed: {lease.unit_id}"
            )

    @staticmethod
    def _input_digests_match(
        connection: sqlite3.Connection,
        lease: Lease,
        expected_input_digest: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT attempt.input_digest AS attempt_input_digest,
                   unit.input_digest AS unit_input_digest
            FROM attempts AS attempt
            JOIN work_units AS unit ON unit.unit_id = attempt.unit_id
            WHERE attempt.attempt_id = ? AND attempt.unit_id = ?
            """,
            (lease.attempt_id, lease.unit_id),
        ).fetchone()
        if row is None:
            raise StaleLeaseError(f"attempt capability mismatch: {lease.unit_id}")
        return not (
            row["attempt_input_digest"] != expected_input_digest
            or row["unit_input_digest"] != expected_input_digest
        )

    def _recover_expired(self, connection: sqlite3.Connection) -> int:
        expired = connection.execute(
            """
            SELECT unit_id, attempt_id FROM leases
            WHERE expires_at <= CAST(unixepoch('subsec') * 1000 AS INTEGER)
            ORDER BY unit_id
            """
        ).fetchall()
        for row in expired:
            connection.execute(
                """
                INSERT OR IGNORE INTO attempt_terminals(attempt_id, outcome)
                VALUES (?, 'ABANDONED')
                """,
                (row["attempt_id"],),
            )
            self._append_event(connection, row["attempt_id"], "LEASE_EXPIRED", {})
            connection.execute("DELETE FROM leases WHERE unit_id = ?", (row["unit_id"],))
            connection.execute(
                """
                UPDATE work_units SET status = 'READY'
                WHERE unit_id = ? AND execution_mode = 'NORMAL'
                  AND status = 'LEASED'
                """,
                (row["unit_id"],),
            )
        return len(expired)

    def _record_workspace_failure(self, lease: Lease) -> None:
        with self._immediate() as connection:
            try:
                self._require_live_lease(connection, lease)
            except StaleLeaseError:
                return
            connection.execute(
                """
                INSERT INTO attempt_terminals(attempt_id, outcome)
                VALUES (?, 'FAILED')
                """,
                (lease.attempt_id,),
            )
            self._append_event(connection, lease.attempt_id, "WORKSPACE_ALLOCATION_FAILED", {})
            connection.execute("DELETE FROM leases WHERE unit_id = ?", (lease.unit_id,))
            connection.execute(
                "UPDATE work_units SET status = 'REPAIR_REQUIRED' WHERE unit_id = ?",
                (lease.unit_id,),
            )

    def _create_workspace(self, lease: Lease) -> None:
        root_fd = self._open_attempts_root()
        unit_fd = -1
        workspace_fd = -1
        marker_fd = -1
        try:
            try:
                os.mkdir(lease.unit_id, mode=0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            except FileExistsError:
                pass
            unit_fd = self._open_directory_at(root_fd, lease.unit_id)
            os.mkdir(lease.attempt_id, mode=0o700, dir_fd=unit_fd)
            workspace_fd = self._open_directory_at(unit_fd, lease.attempt_id)
            marker = (
                json.dumps(
                    {
                        "attempt_id": lease.attempt_id,
                        "fencing_token": lease.fencing_token,
                        "input_digest": lease.input_digest,
                        "lease_id": lease.lease_id,
                        "owner": lease.owner,
                        "unit_id": lease.unit_id,
                    },
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            marker_fd = os.open(
                "ATTEMPT.READY",
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o400,
                dir_fd=workspace_fd,
            )
            written = 0
            while written < len(marker):
                chunk_size = os.write(marker_fd, marker[written:])
                if chunk_size <= 0:
                    raise QueueError("short write while publishing attempt marker")
                written += chunk_size
            os.fsync(marker_fd)
            os.close(marker_fd)
            marker_fd = -1
            os.fsync(workspace_fd)
            os.fsync(unit_fd)
            os.fsync(root_fd)
        finally:
            if marker_fd >= 0:
                os.close(marker_fd)
            if workspace_fd >= 0:
                os.close(workspace_fd)
            if unit_fd >= 0:
                os.close(unit_fd)
            os.close(root_fd)

    def _open_attempts_root(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT attempts_root, attempts_device, attempts_inode
                FROM schema_meta WHERE singleton = 1
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None or row["attempts_root"] != str(self.attempts_root):
            raise QueueError("queue attempt root is not initialized")
        descriptor = self._open_directory_path(self.attempts_root)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (
            row["attempts_device"],
            row["attempts_inode"],
        ):
            os.close(descriptor)
            raise QueueError("queue attempt root identity changed")
        return descriptor

    def _try_acquire_publication_guard(self, *, wait: bool = False) -> int | None:
        """Acquire the process-scoped guard ordered before queue recovery."""
        path = self.database.with_name(self.database.name + ".tracker-publisher.lock")
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError as error:
            raise QueueError("publisher guard is unsafe or inaccessible") from error
        try:
            node = os.fstat(descriptor)
            if not stat.S_ISREG(node.st_mode) or node.st_nlink != 1:
                raise QueueError("publisher guard is not a private regular file")
            deadline = time.monotonic() + self.busy_timeout_ms / 1_000
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not wait:
                        os.close(descriptor)
                        return None
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        os.close(descriptor)
                        return None
                    time.sleep(min(0.01, remaining))
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    @staticmethod
    def _open_directory_path(path: Path) -> int:
        flags = (
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            return os.open(path, flags)
        except OSError as error:
            raise QueueError(f"unsafe or inaccessible directory: {path}") from error

    @classmethod
    def _fsync_directory_path(cls, path: Path) -> None:
        descriptor = cls._open_directory_path(path)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _create_directory_tree_durably(self, path: Path) -> None:
        """Create a directory tree and sync every link to its existing anchor."""
        anchor = path
        while not anchor.exists():
            parent = anchor.parent
            if parent == anchor:
                raise QueueError(f"directory tree has no existing anchor: {path}")
            anchor = parent
        if not anchor.is_dir():
            raise QueueError(f"directory tree anchor is not a directory: {anchor}")

        path.mkdir(parents=True, exist_ok=True)
        current = path
        while True:
            self._fsync_directory_path(current)
            if current == anchor:
                break
            current = current.parent

    @staticmethod
    def _open_directory_at(parent_fd: int, name: str) -> int:
        flags = (
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            return os.open(name, flags, dir_fd=parent_fd)
        except OSError as error:
            raise QueueError(f"unsafe attempt directory component: {name}") from error

    def _require_live_lease(self, connection: sqlite3.Connection, lease: Lease) -> None:
        row = connection.execute(
            """
            SELECT 1 FROM leases
            WHERE unit_id = ? AND lease_id = ? AND attempt_id = ?
              AND owner = ? AND fencing_token = ?
              AND expires_at > CAST(unixepoch('subsec') * 1000 AS INTEGER)
            """,
            (
                lease.unit_id,
                lease.lease_id,
                lease.attempt_id,
                lease.owner,
                lease.fencing_token,
            ),
        ).fetchone()
        if row is None:
            raise StaleLeaseError(f"stale or expired lease: {lease.unit_id}")

    @staticmethod
    def _require_unstarted(connection: sqlite3.Connection, unit_id: str) -> None:
        row = connection.execute(
            """
            SELECT status,
                   EXISTS(SELECT 1 FROM attempts WHERE attempts.unit_id = work_units.unit_id)
                       AS has_attempt
            FROM work_units WHERE unit_id = ?
            """,
            (unit_id,),
        ).fetchone()
        if row is None:
            raise QueueError(f"unknown work unit: {unit_id}")
        if row["status"] != WorkUnitStatus.READY.value or bool(row["has_attempt"]):
            raise QueueConflictError(f"dependencies are frozen after work starts: {unit_id}")

    def _dependencies_satisfied(self, connection: sqlite3.Connection, unit_id: str) -> bool:
        missing = connection.execute(
            """
            SELECT 1
            FROM dependencies AS dependency
            LEFT JOIN formal_completions AS completion
              ON completion.unit_id = dependency.parent_unit_id
            WHERE dependency.unit_id = ?
              AND (
                  completion.unit_id IS NULL
                  OR completion.completion_revision <> dependency.required_revision
                  OR completion.output_digest <> dependency.required_digest
              )
            UNION ALL
            SELECT 1
            FROM capability_requirements AS requirement
            LEFT JOIN pipeline_capability_activations AS activation
              ON activation.capability = requirement.capability
             AND activation.revision = requirement.required_revision
             AND activation.digest = requirement.required_digest
             AND activation.activation_id = (
                 SELECT MAX(candidate.activation_id)
                 FROM pipeline_capability_activations AS candidate
                 WHERE candidate.capability = requirement.capability
             )
            WHERE requirement.unit_id = ? AND activation.capability IS NULL
            LIMIT 1
            """,
            (unit_id, unit_id),
        ).fetchone()
        return missing is None

    @staticmethod
    def _insert_capability_activation(
        connection: sqlite3.Connection,
        capability: str,
        revision: str,
        digest: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO pipeline_capability_activations(capability, revision, digest)
            VALUES (?, ?, ?)
            """,
            (capability, revision, digest),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        attempt_id: str,
        event_type: str,
        payload: Mapping[str, object],
    ) -> None:
        encoded = _encode_event_payload(payload)
        Queue._append_encoded_event(connection, attempt_id, event_type, encoded)

    @staticmethod
    def _append_encoded_event(
        connection: sqlite3.Connection,
        attempt_id: str,
        event_type: str,
        encoded: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO events(attempt_id, event_type, payload_json)
            VALUES (?, ?, ?)
            """,
            (attempt_id, event_type, encoded),
        )

    @contextmanager
    def _immediate(
        self,
        *,
        require_schema: bool = True,
    ) -> Iterator[sqlite3.Connection]:
        connection = self._connect(require_schema=require_schema)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if require_schema:
                self._require_schema_compatible(connection)
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(
        self,
        *,
        require_schema: bool = True,
        allow_create: bool = False,
    ) -> sqlite3.Connection:
        target = str(self.database) if allow_create else f"{self.database.as_uri()}?mode=rw"
        try:
            connection = sqlite3.connect(
                target,
                timeout=self.busy_timeout_ms / 1_000,
                isolation_level=None,
                uri=not allow_create,
            )
        except sqlite3.Error as error:
            raise QueueError("queue database is missing or inaccessible") from error
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA synchronous = FULL")
        if require_schema:
            try:
                self._require_schema_compatible(connection)
            except BaseException:
                connection.close()
                raise
        self._verify_database_identity(connection, allow_create=allow_create)
        return connection

    def _database_identity(self) -> tuple[tuple[str, int, int], ...]:
        """Return the database and every directory identity in its path."""
        identities: list[tuple[str, int, int]] = []
        current = self.database
        while True:
            try:
                node = os.lstat(current)
            except OSError as error:
                raise QueueError("queue database path is missing or inaccessible") from error
            if current == self.database:
                valid = stat.S_ISREG(node.st_mode)
            else:
                valid = stat.S_ISDIR(node.st_mode)
            if not valid or stat.S_ISLNK(node.st_mode):
                raise QueueError("queue database path contains an unsafe node")
            identities.append((str(current), node.st_dev, node.st_ino))
            if current.parent == current:
                break
            current = current.parent
        return tuple(identities)

    @staticmethod
    def _stored_database_identity(
        row: sqlite3.Row,
    ) -> tuple[tuple[str, int, int], ...]:
        try:
            parents = json.loads(str(row["parent_identities"]))
            if type(parents) is not list:
                raise ValueError
            parsed = [
                (
                    item[0],
                    item[1],
                    item[2],
                )
                for item in parents
                if type(item) is list and len(item) == 3
            ]
            if len(parsed) != len(parents) or any(
                type(path) is not str
                or type(device) is not int
                or type(inode) is not int
                for path, device, inode in parsed
            ):
                raise ValueError
            return (
                (
                    row["database_path"],
                    row["database_device"],
                    row["database_inode"],
                ),
                *parsed,
            )
        except (TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError) as error:
            raise QueueError("queue database identity metadata is invalid") from error

    def _verify_database_identity(
        self,
        connection: sqlite3.Connection,
        *,
        allow_create: bool,
    ) -> None:
        try:
            row = connection.execute(
                """
                SELECT database_path, database_device, database_inode, parent_identities
                FROM queue_identity WHERE singleton = 1
                """
            ).fetchone()
        except sqlite3.OperationalError as error:
            if allow_create and "no such table" in str(error).casefold():
                return
            raise QueueError("queue database identity metadata is missing or unreadable") from error
        if row is None:
            if allow_create:
                return
            raise QueueError("queue database identity metadata is missing or unreadable")
        if self._stored_database_identity(row) != self._database_identity():
            raise QueueError("queue database or parent identity changed")

    @staticmethod
    def _require_schema_compatible(connection: sqlite3.Connection) -> None:
        try:
            row = connection.execute(
                "SELECT revision FROM schema_meta WHERE singleton = 1"
            ).fetchone()
            schema_objects = _schema_objects(connection)
        except sqlite3.DatabaseError as error:
            raise QueueError("queue schema metadata is missing or unreadable") from error
        if row is None:
            raise QueueError("queue schema metadata is missing or unreadable")
        if int(row["revision"]) != SCHEMA_REVISION:
            raise _unsupported_schema_revision(row["revision"])
        if schema_objects != _REQUIRED_SCHEMA_OBJECTS:
            raise QueueError("queue schema objects are incomplete, unexpected, or altered")

    def _enable_wal(self, connection: sqlite3.Connection) -> None:
        """Establish WAL mode despite concurrent first-time initializers."""
        deadline = time.monotonic() + self.busy_timeout_ms / 1_000
        while True:
            try:
                row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).casefold():
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise QueueError("timed out establishing SQLite WAL mode") from error
                time.sleep(min(0.05, remaining))
                continue
            if row is None or str(row[0]).casefold() != "wal":
                raise QueueError("SQLite refused WAL journal mode")
            return


def _validate_identifier(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > _MAX_IDENTIFIER_LENGTH
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise ValueError(f"{label} must be a stable path-safe identifier")


def _validate_reserved_unit_kind(unit_id: str, kind: str) -> None:
    reserved_kinds = _reserved_unit_kinds()
    for prefix, reserved_kind in reserved_kinds.items():
        if unit_id.startswith(prefix):
            if kind != reserved_kind:
                raise ValueError(f"reserved work unit requires kind {reserved_kind!r}")
            return
    if kind.startswith(_TRUSTED_COMPLETION_KIND_PREFIX):
        raise ValueError("trusted completion kinds require a reserved work unit ID")


def _reserved_unit_kinds() -> dict[str, str]:
    from tools.phase4_v2.equivalence.plan import (
        PACKAGE_QUEUE_UNIT_KIND,
        PACKAGE_QUEUE_UNIT_PREFIX,
    )

    return {
        **_RESERVED_UNIT_KINDS,
        f"{PACKAGE_QUEUE_UNIT_PREFIX}:": PACKAGE_QUEUE_UNIT_KIND,
    }


def _requires_trusted_completion_adapter(unit_id: str, kind: str) -> bool:
    return (
        kind in ORCHESTRATION_KINDS
        or kind.startswith(_TRUSTED_COMPLETION_KIND_PREFIX)
        or any(unit_id.startswith(prefix) for prefix in _reserved_unit_kinds())
    )


def _validate_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _validate_revision(value: str) -> None:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > 200:
        raise ValueError("revision must be a non-empty bounded string")


def _validate_owner(owner: str) -> None:
    if not owner or "\x00" in owner or len(owner) > 500:
        raise ValueError("owner must be a non-empty bounded string")


def _validate_ttl(ttl_seconds: int) -> None:
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= _MAX_TTL_SECONDS:
        raise ValueError("ttl_seconds must be a bounded positive integer")


def _validate_allowed_kinds(allowed_kinds: Iterable[str] | None) -> tuple[str, ...] | None:
    if allowed_kinds is None:
        return None
    if isinstance(allowed_kinds, (str, bytes)):
        raise ValueError("allowed_kinds must be a collection of identifiers")
    kinds = tuple(islice(allowed_kinds, _MAX_MATERIALIZED_PINS + 1))
    if not kinds or len(kinds) > _MAX_MATERIALIZED_PINS:
        raise ValueError("allowed_kinds must be a non-empty bounded collection")
    for kind in kinds:
        _validate_identifier(kind, "allowed kind")
    if len(set(kinds)) != len(kinds):
        raise ValueError("allowed_kinds contains duplicates")
    return tuple(sorted(kinds))


def _validate_orchestration_definition(kind: str, cluster_id: str | None) -> None:
    if (
        kind in ORCHESTRATION_KINDS - {ORCHESTRATION_PACKAGE_ANALYSIS_KIND}
        and cluster_id is None
    ):
        raise ValueError("orchestration stage requires a cluster_id")


def _bounded_materialization_values[PinT: (CapabilityPin, CompletionDependencyPin)](
    values: Iterable[PinT],
    expected_type: type[PinT],
    label: str,
) -> tuple[PinT, ...]:
    try:
        bounded = tuple(islice(iter(values), _MAX_MATERIALIZED_PINS + 1))
    except TypeError as error:
        raise ValueError(f"{label} must be an iterable of immutable pins") from error
    if len(bounded) > _MAX_MATERIALIZED_PINS:
        raise ValueError(f"{label} exceeds the {_MAX_MATERIALIZED_PINS}-pin limit")
    if any(type(value) is not expected_type for value in bounded):
        raise ValueError(f"{label} contains an invalid pin type")
    return bounded


def _reject_duplicate_pin_keys(keys: Iterator[str], label: str) -> None:
    previous: str | None = None
    for key in keys:
        if key == previous:
            raise ValueError(f"duplicate {label} pin: {key}")
        previous = key


def _derive_materialized_input_digest(
    *,
    unit_id: str,
    kind: str,
    cluster_id: str | None,
    priority: int,
    execution_mode: ExecutionMode,
    capabilities: tuple[CapabilityPin, ...],
    dependencies: tuple[CompletionDependencyPin, ...],
) -> str:
    payload = {
        "capability_pins": [
            [pin.capability, pin.revision, pin.digest] for pin in capabilities
        ],
        "cluster_id": cluster_id,
        "dependency_pins": [
            [pin.parent_unit_id, pin.revision, pin.digest] for pin in dependencies
        ],
        "execution_mode": execution_mode.value,
        "kind": kind,
        "priority": priority,
        "schema": "phase4-v2-work-materialization-v1",
        "unit_id": unit_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
