"""Atomic work-definition materialization tests for the Phase 4 v2 queue."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import contextmanager
from multiprocessing import get_context
from pathlib import Path
from threading import Event
from typing import Any

import pytest

from tools.phase4_v2.queue import (
    CapabilityPin,
    CompletionDependencyPin,
    Queue,
    QueueConflictError,
)


def _materialize_in_process(
    database: str,
    attempts_root: str,
    kind: str,
    digest: str,
    capability: str,
) -> str:
    queue = Queue(Path(database), Path(attempts_root))
    try:
        queue.materialize_work_unit(
            "package-a",
            kind=kind,
            input_digest=digest,
            capability_pins=(CapabilityPin(capability, "revision-v1", digest),),
        )
    except QueueConflictError:
        return f"conflict:{kind}"
    return f"success:{kind}"


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    instance = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    instance.initialize()
    return instance


def test_materialization_derives_stable_digest_and_is_exactly_idempotent(queue: Queue) -> None:
    queue.enqueue("parent", kind="package", input_digest="f" * 64)
    capabilities = (
        CapabilityPin("validator", "validator-v1", "b" * 64),
        CapabilityPin("preflight", "preflight-v1", "a" * 64),
    )
    dependencies = (CompletionDependencyPin("parent", "report-v1", "c" * 64),)

    first = queue.materialize_work_unit(
        "package-a",
        kind="analysis",
        capability_pins=capabilities,
        dependency_pins=dependencies,
    )
    second = queue.materialize_work_unit(
        "package-a",
        kind="analysis",
        capability_pins=reversed(capabilities),
        dependency_pins=dependencies,
    )

    assert first == second
    assert len(first) == 64
    with pytest.raises(QueueConflictError, match="materialized work unit changed"):
        queue.materialize_work_unit(
            "package-a",
            kind="analysis",
            capability_pins=capabilities[:1],
            dependency_pins=dependencies,
        )


@pytest.mark.parametrize(
    ("capabilities", "dependencies", "message"),
    [
        (
            (
                CapabilityPin("validator", "v1", "a" * 64),
                CapabilityPin("validator", "v1", "a" * 64),
            ),
            (),
            "duplicate capability pin",
        ),
        (
            (),
            (
                CompletionDependencyPin("parent", "v1", "a" * 64),
                CompletionDependencyPin("parent", "v2", "b" * 64),
            ),
            "duplicate dependency pin",
        ),
        (
            (),
            (CompletionDependencyPin("package-a", "v1", "a" * 64),),
            "cannot depend on itself",
        ),
    ],
)
def test_invalid_pin_sets_fail_before_opening_database(
    tmp_path: Path,
    capabilities: tuple[CapabilityPin, ...],
    dependencies: tuple[CompletionDependencyPin, ...],
    message: str,
) -> None:
    queue = Queue(tmp_path / "missing.sqlite3", tmp_path / "attempts")

    with pytest.raises(ValueError, match=message):
        queue.materialize_work_unit(
            "package-a",
            kind="analysis",
            capability_pins=capabilities,
            dependency_pins=dependencies,
        )
    assert not queue.database.exists()


def test_materialization_bounds_identifiers_and_pin_counts(queue: Queue) -> None:
    with pytest.raises(ValueError, match="stable path-safe identifier"):
        queue.materialize_work_unit("x" * 201, kind="analysis")
    with pytest.raises(ValueError, match="256-pin limit"):
        queue.materialize_work_unit(
            "package-a",
            kind="analysis",
            capability_pins=(
                CapabilityPin(f"capability-{index}", "v1", "a" * 64)
                for index in range(257)
            ),
        )


def test_failed_dependency_insert_rolls_back_entire_materialization(queue: Queue) -> None:
    with pytest.raises(QueueConflictError, match="could not materialize"):
        queue.materialize_work_unit(
            "package-a",
            kind="analysis",
            capability_pins=(CapabilityPin("validator", "v1", "a" * 64),),
            dependency_pins=(
                CompletionDependencyPin("missing-parent", "report-v1", "b" * 64),
            ),
        )

    with sqlite3.connect(queue.database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM work_units WHERE unit_id = 'package-a'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM capability_requirements WHERE unit_id = 'package-a'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM dependencies WHERE unit_id = 'package-a'"
        ).fetchone()[0] == 0


def test_identical_concurrent_materialization_creates_one_exact_unit(queue: Queue) -> None:
    context = get_context("spawn")
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
        results = list(
            executor.map(
                _materialize_in_process,
                [str(queue.database)] * 2,
                [str(queue.attempts_root)] * 2,
                ["analysis"] * 2,
                ["a" * 64] * 2,
                ["validator"] * 2,
            )
        )

    assert results == ["success:analysis", "success:analysis"]
    with sqlite3.connect(queue.database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM work_units WHERE unit_id = 'package-a'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT capability, required_digest FROM capability_requirements"
        ).fetchall() == [("validator", "a" * 64)]


def test_conflicting_concurrent_materialization_never_mixes_pin_sets(queue: Queue) -> None:
    context = get_context("spawn")
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
        results = list(
            executor.map(
                _materialize_in_process,
                [str(queue.database)] * 2,
                [str(queue.attempts_root)] * 2,
                ["analysis-a", "analysis-b"],
                ["a" * 64, "b" * 64],
                ["validator-a", "validator-b"],
            )
        )

    assert sum(result.startswith("success:") for result in results) == 1
    assert sum(result.startswith("conflict:") for result in results) == 1
    with sqlite3.connect(queue.database) as connection:
        unit = connection.execute(
            "SELECT kind, input_digest FROM work_units WHERE unit_id = 'package-a'"
        ).fetchone()
        pin = connection.execute(
            "SELECT capability, required_digest FROM capability_requirements"
        ).fetchone()
    expected = {
        ("analysis-a", "a" * 64): ("validator-a", "a" * 64),
        ("analysis-b", "b" * 64): ("validator-b", "b" * 64),
    }
    assert pin == expected[unit]


def test_claim_cannot_observe_unit_before_all_pins_are_inserted(
    monkeypatch: pytest.MonkeyPatch,
    queue: Queue,
) -> None:
    transaction_paused = Event()
    release_transaction = Event()
    claim_connecting = Event()
    original_immediate = queue._immediate

    class _PausedConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
            return self._connection.execute(*args, **kwargs)

        def executemany(self, sql: str, parameters: Any) -> sqlite3.Cursor:
            if "INSERT INTO capability_requirements" in sql:
                transaction_paused.set()
                assert release_transaction.wait(5)
            return self._connection.executemany(sql, parameters)

    @contextmanager
    def paused_immediate(*, require_schema: bool = True):
        with original_immediate(require_schema=require_schema) as connection:
            yield _PausedConnection(connection)

    monkeypatch.setattr(queue, "_immediate", paused_immediate)
    claimant = Queue(queue.database, queue.attempts_root)
    original_connect = claimant._connect

    def observed_connect(*, require_schema: bool = True, allow_create: bool = False):
        claim_connecting.set()
        return original_connect(require_schema=require_schema, allow_create=allow_create)

    monkeypatch.setattr(claimant, "_connect", observed_connect)
    with ThreadPoolExecutor(max_workers=2) as executor:
        materialized = executor.submit(
            queue.materialize_work_unit,
            "package-a",
            kind="analysis",
            capability_pins=(CapabilityPin("inactive", "v1", "a" * 64),),
        )
        assert transaction_paused.wait(5)
        claimed = executor.submit(claimant.claim, "worker")
        assert claim_connecting.wait(5)
        release_transaction.set()

    assert len(materialized.result()) == 64
    assert claimed.result() is None
