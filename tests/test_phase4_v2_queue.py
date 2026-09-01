"""Concurrency and integrity tests for the Phase 4 v2 queue core."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path

import pytest

from tools.phase4_v2.queue import (
    CompletionConflictError,
    DependencyNotSatisfiedError,
    ExecutionMode,
    FinishDisposition,
    Lease,
    Queue,
    QueueConflictError,
    QueueError,
    StaleLeaseError,
    TerminalOutcome,
    WorkUnitStatus,
)


def _claim_in_process(database: str, attempts_root: str, owner: str) -> str | None:
    queue = Queue(Path(database), Path(attempts_root))
    lease = queue.claim(owner)
    return lease.unit_id if lease is not None else None


def _initialize_in_process(database: str, attempts_root: str) -> None:
    Queue(Path(database), Path(attempts_root)).initialize()


def _activate_in_process(
    database: str,
    attempts_root: str,
    capability: str,
    revision: str,
    digest: str,
    expected_revision: str,
    expected_digest: str,
) -> str:
    try:
        Queue(Path(database), Path(attempts_root)).activate_capability(
            capability,
            revision,
            digest,
            expected_revision=expected_revision,
            expected_digest=expected_digest,
        )
    except QueueConflictError:
        return f"conflict:{revision}"
    return f"success:{revision}"


def _activate_from_absent_in_process(
    database: str,
    attempts_root: str,
    capability: str,
    revision: str,
    digest: str,
) -> str:
    try:
        Queue(Path(database), Path(attempts_root)).activate_capability_from_absent(
            capability,
            revision,
            digest,
        )
    except QueueConflictError:
        return f"conflict:{revision}"
    return f"success:{revision}"


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    instance = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    instance.initialize()
    return instance


def _enqueue(queue: Queue, unit_id: str, *, priority: int = 0) -> None:
    queue.enqueue(
        unit_id,
        kind="package",
        input_digest=(unit_id.encode().hex() + "0" * 64)[:64],
        priority=priority,
    )


@pytest.mark.parametrize("priority", [True, -(2**31) - 1, 2**31])
def test_enqueue_rejects_invalid_priority_before_opening_database(
    tmp_path: Path, priority: int
) -> None:
    queue = Queue(tmp_path / "missing.sqlite3", tmp_path / "attempts")

    with pytest.raises(ValueError, match="priority must be a bounded integer"):
        _enqueue(queue, "package-a", priority=priority)

    assert not queue.database.exists()


@pytest.mark.parametrize("ttl", [True, 1.0, 2**31, 2**63])
def test_claim_and_renew_reject_unbounded_ttl(queue: Queue, ttl: object) -> None:
    _enqueue(queue, "package-a")

    with pytest.raises(ValueError, match="ttl_seconds must be a bounded positive integer"):
        queue.claim("worker-a", ttl_seconds=ttl)  # type: ignore[arg-type]

    lease = queue.claim("worker-a")
    assert lease is not None
    with pytest.raises(ValueError, match="ttl_seconds must be a bounded positive integer"):
        queue.renew(lease, ttl_seconds=ttl)  # type: ignore[arg-type]


def test_initialize_durably_publishes_attempt_root_before_database_pin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path.resolve()
    database_parent = root / "database" / "nested" / "state"
    attempts_parent = root / "workspaces" / "nested" / "attempts"
    instance = Queue(database_parent / "queue.sqlite3", attempts_parent)
    original_fsync = instance._fsync_directory_path
    original_connect = instance._connect
    fsynced: list[Path] = []

    def record_fsync(path: Path) -> None:
        original_fsync(path)
        fsynced.append(path)

    def assert_root_is_durable(
        *,
        require_schema: bool = True,
        allow_create: bool = False,
    ) -> sqlite3.Connection:
        assert {
            database_parent,
            database_parent.parent,
            database_parent.parent.parent,
            attempts_parent,
            attempts_parent.parent,
            attempts_parent.parent.parent,
            root,
        } <= set(fsynced)
        return original_connect(
            require_schema=require_schema,
            allow_create=allow_create,
        )

    monkeypatch.setattr(instance, "_fsync_directory_path", record_fsync)
    monkeypatch.setattr(instance, "_connect", assert_root_is_durable)

    instance.initialize()

    assert instance.database.is_file()


def test_multiprocess_claims_are_atomic_and_distinct(queue: Queue) -> None:
    for index in range(4):
        _enqueue(queue, f"package-{index}")

    context = get_context("spawn")
    with ProcessPoolExecutor(max_workers=8, mp_context=context) as executor:
        claims = list(
            executor.map(
                _claim_in_process,
                [str(queue.database)] * 8,
                [str(queue.attempts_root)] * 8,
                [f"worker-{index}" for index in range(8)],
            )
        )

    claimed = [unit_id for unit_id in claims if unit_id is not None]
    assert len(claimed) == 4
    assert len(set(claimed)) == 4
    for unit_id in claimed:
        assert queue.status(unit_id) is WorkUnitStatus.LEASED


def test_concurrent_initialization_pins_one_attempt_root(tmp_path: Path) -> None:
    database = tmp_path / "state" / "queue.sqlite3"
    attempts_root = tmp_path / "attempts"
    context = get_context("spawn")

    with ProcessPoolExecutor(max_workers=4, mp_context=context) as executor:
        list(
            executor.map(
                _initialize_in_process,
                [str(database)] * 4,
                [str(attempts_root)] * 4,
            )
        )

    Queue(database, attempts_root).initialize()


def test_schema_revision_three_is_pinned_and_v1_fails_before_schema_mutation(
    queue: Queue,
    tmp_path: Path,
) -> None:
    assert queue.snapshot().schema_revision == 3

    database = tmp_path / "legacy" / "queue.sqlite3"
    attempts_root = tmp_path / "legacy-attempts"
    database.parent.mkdir()
    attempts_root.mkdir()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE schema_meta (
                singleton INTEGER PRIMARY KEY,
                revision INTEGER NOT NULL,
                attempts_root TEXT NOT NULL,
                attempts_device INTEGER NOT NULL,
                attempts_inode INTEGER NOT NULL
            )
            """
        )
        root_stat = attempts_root.stat()
        connection.execute(
            "INSERT INTO schema_meta VALUES (1, 1, ?, ?, ?)",
            (str(attempts_root.resolve()), root_stat.st_dev, root_stat.st_ino),
        )

    with pytest.raises(QueueError, match="unsupported queue schema revision: 1"):
        Queue(database, attempts_root).initialize()

    with closing(sqlite3.connect(database)) as connection:
        activation_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'pipeline_capability_activations'
            """
        ).fetchone()
    assert activation_table is None


def test_schema_revision_two_requires_regeneration(tmp_path: Path) -> None:
    database = tmp_path / "legacy-v2" / "queue.sqlite3"
    attempts_root = tmp_path / "legacy-v2-attempts"
    database.parent.mkdir()
    attempts_root.mkdir()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE schema_meta (
                singleton INTEGER PRIMARY KEY,
                revision INTEGER NOT NULL,
                attempts_root TEXT NOT NULL,
                attempts_device INTEGER NOT NULL,
                attempts_inode INTEGER NOT NULL
            )
            """
        )
        root_stat = attempts_root.stat()
        connection.execute(
            "INSERT INTO schema_meta VALUES (1, 2, ?, ?, ?)",
            (str(attempts_root.resolve()), root_stat.st_dev, root_stat.st_ino),
        )

    with pytest.raises(QueueError, match="regenerate the queue from orchestration inputs"):
        Queue(database, attempts_root).initialize()


def test_verify_schema_rejects_revision_three_database_missing_operational_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "truncated" / "queue.sqlite3"
    attempts_root = tmp_path / "truncated-attempts"
    database.parent.mkdir()
    attempts_root.mkdir()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE schema_meta (
                singleton INTEGER PRIMARY KEY,
                revision INTEGER NOT NULL,
                attempts_root TEXT NOT NULL,
                attempts_device INTEGER NOT NULL,
                attempts_inode INTEGER NOT NULL
            )
            """
        )
        root_stat = attempts_root.stat()
        connection.execute(
            "INSERT INTO schema_meta VALUES (1, 3, ?, ?, ?)",
            (str(attempts_root.resolve()), root_stat.st_dev, root_stat.st_ino),
        )

    with pytest.raises(QueueError, match="schema objects are incomplete"):
        Queue(database, attempts_root).verify_schema()


def test_verify_schema_rejects_missing_immutability_trigger(queue: Queue) -> None:
    with closing(sqlite3.connect(queue.database)) as connection, connection:
        connection.execute("DROP TRIGGER events_no_update")

    with pytest.raises(QueueError, match="schema objects are incomplete"):
        queue.verify_schema()


def test_expired_worker_is_fenced_after_recovery(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    first = queue.claim("chat-a")
    assert first is not None
    with closing(sqlite3.connect(queue.database)) as connection, connection:
        connection.execute(
            """
            UPDATE leases
            SET expires_at = CAST(unixepoch('subsec') * 1000 AS INTEGER) - 1
            """
        )

    second = queue.claim("chat-b")

    assert second is not None
    assert second.unit_id == first.unit_id
    assert second.attempt_id != first.attempt_id
    assert second.fencing_token == first.fencing_token + 1
    assert first.workspace.is_dir()
    with pytest.raises(StaleLeaseError):
        queue.renew(first)
    with pytest.raises(StaleLeaseError):
        queue.checkpoint(first, "LATE_CHECKPOINT")
    with pytest.raises(StaleLeaseError):
        queue.finish(
            first,
            TerminalOutcome.ACCEPTED,
            output_digest="a" * 64,
            completion_revision="report-v1",
        )


def test_live_lease_renews_with_database_time(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("chat-a", ttl_seconds=2)
    assert lease is not None

    renewed = queue.renew(lease, ttl_seconds=60)

    assert renewed.expires_at > lease.expires_at
    queue.checkpoint(renewed, "REPORT_STARTED")


def test_renew_restores_immutable_attempt_metadata(queue: Queue, tmp_path: Path) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("chat-a")
    assert lease is not None
    tampered = replace(
        lease,
        input_digest="f" * 64,
        workspace=tmp_path / "escaped",
    )

    renewed = queue.renew(tampered)

    assert renewed.input_digest == lease.input_digest
    assert renewed.workspace == lease.workspace


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"value": "x" * (1024 * 1024)}, "byte limit"),
        ({"values": [None] * 100_000}, "node limit"),
        ({"value": [[[[[[[[[[None]]]]]]]]]]}, "nesting limit"),
    ],
)
def test_checkpoint_rejects_unbounded_payload_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
    queue: Queue,
    payload: dict[str, object],
    message: str,
) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("chat-a")
    assert lease is not None
    if message == "nesting limit":
        monkeypatch.setattr("tools.phase4_v2.queue.core._MAX_EVENT_PAYLOAD_DEPTH", 8)

    def unexpected_transaction(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("checkpoint entered a transaction")

    monkeypatch.setattr(queue, "_immediate", unexpected_transaction)

    with pytest.raises(ValueError, match=message):
        queue.checkpoint(lease, "REPORT_DATA", payload)


def test_attempt_history_and_completion_rows_are_immutable(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    queue.register_capability("validator", "validator-v1", "c" * 64)
    queue.activate_capability_from_absent("validator", "validator-v1", "c" * 64)
    queue.require_capability("package-a", "validator", revision="validator-v1", digest="c" * 64)
    lease = queue.claim("chat-a")
    assert lease is not None
    queue.checkpoint(lease, "REPORT_FROZEN", {"digest": "a" * 64})
    queue.finish(
        lease,
        TerminalOutcome.ACCEPTED,
        output_digest="a" * 64,
        completion_revision="report-v1",
    )

    statements = (
        "UPDATE attempts SET owner = 'other'",
        "DELETE FROM attempts",
        "UPDATE events SET event_type = 'other'",
        "DELETE FROM events",
        "UPDATE attempt_terminals SET outcome = 'FAILED'",
        "DELETE FROM attempt_terminals",
        "UPDATE formal_completions SET output_digest = '" + "b" * 64 + "'",
        "DELETE FROM formal_completions",
        "UPDATE work_units SET priority = 999",
        "DELETE FROM work_units",
        "UPDATE pipeline_capabilities SET digest = '" + "d" * 64 + "'",
        "DELETE FROM pipeline_capabilities",
        "UPDATE capability_requirements SET required_revision = 'other'",
        "DELETE FROM capability_requirements",
        "UPDATE schema_meta SET attempts_inode = 1",
        "DELETE FROM schema_meta",
    )
    for statement in statements:
        with (
            sqlite3.connect(queue.database) as connection,
            pytest.raises(sqlite3.IntegrityError, match="immutable"),
        ):
            connection.execute(statement)


def test_completion_is_idempotent_but_conflicting_digest_is_rejected(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("chat-a")
    assert lease is not None

    completed = queue.finish(
        lease,
        TerminalOutcome.ACCEPTED,
        output_digest="a" * 64,
        completion_revision="report-v1",
    )
    repeated = queue.finish(
        lease,
        TerminalOutcome.ACCEPTED,
        output_digest="a" * 64,
        completion_revision="report-v1",
    )

    assert completed.disposition is FinishDisposition.COMPLETED
    assert repeated.disposition is FinishDisposition.IDEMPOTENT
    with pytest.raises(StaleLeaseError):
        queue.finish(
            replace(lease, lease_id="forged-lease"),
            TerminalOutcome.ACCEPTED,
            output_digest="a" * 64,
            completion_revision="report-v1",
        )
    with pytest.raises(CompletionConflictError):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest="b" * 64,
            completion_revision="report-v1",
        )


def test_dependency_revision_and_digest_are_fail_closed(queue: Queue) -> None:
    _enqueue(queue, "parent", priority=0)
    _enqueue(queue, "child", priority=100)
    queue.add_dependency("child", "parent", revision="report-v1", digest="a" * 64)

    for statement in (
        "UPDATE dependencies SET required_revision = 'other'",
        "DELETE FROM dependencies",
    ):
        with (
            sqlite3.connect(queue.database) as connection,
            pytest.raises(sqlite3.IntegrityError, match="immutable"),
        ):
            connection.execute(statement)

    parent = queue.claim("parent-worker")
    assert parent is not None
    assert parent.unit_id == "parent"
    queue.finish(
        parent,
        TerminalOutcome.ACCEPTED,
        output_digest="b" * 64,
        completion_revision="report-v1",
    )

    assert queue.claim("child-worker") is None
    assert queue.status("child") is WorkUnitStatus.READY


def test_dependency_cycles_are_rejected_before_insertion(queue: Queue) -> None:
    for unit_id in ("first", "second", "third"):
        _enqueue(queue, unit_id)
    queue.add_dependency("second", "first", revision="report-v1", digest="a" * 64)
    queue.add_dependency("third", "second", revision="report-v1", digest="b" * 64)

    with pytest.raises(QueueConflictError, match="create a cycle"):
        queue.add_dependency("first", "third", revision="report-v1", digest="c" * 64)
    with pytest.raises(QueueConflictError, match="create a cycle"):
        queue.add_dependency("first", "first", revision="report-v1", digest="d" * 64)

    with sqlite3.connect(queue.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0] == 2


def test_exact_dependency_and_capability_unlock_unit(queue: Queue) -> None:
    _enqueue(queue, "parent")
    _enqueue(queue, "child", priority=100)
    queue.add_dependency("child", "parent", revision="report-v1", digest="a" * 64)
    queue.require_capability(
        "child",
        "validator",
        revision="validator-v1",
        digest="c" * 64,
    )
    parent = queue.claim("parent-worker")
    assert parent is not None and parent.unit_id == "parent"
    queue.finish(
        parent,
        TerminalOutcome.ACCEPTED,
        output_digest="a" * 64,
        completion_revision="report-v1",
    )
    assert queue.claim("child-worker") is None

    queue.register_capability("validator", "validator-v1", "c" * 64)
    assert queue.claim("child-worker") is None
    queue.activate_capability_from_absent("validator", "validator-v1", "c" * 64)
    child = queue.claim("child-worker")

    assert child is not None
    assert child.unit_id == "child"


def test_capability_revision_cannot_be_rebound_to_another_digest(queue: Queue) -> None:
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v1", "a" * 64)

    with pytest.raises(QueueConflictError, match="capability revision changed"):
        queue.register_capability("validator", "validator-v1", "b" * 64)


def test_only_the_active_capability_head_is_eligible_for_claim(queue: Queue) -> None:
    _enqueue(queue, "old-validator", priority=100)
    _enqueue(queue, "new-validator", priority=90)
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v2", "b" * 64)
    queue.activate_capability_from_absent("validator", "validator-v1", "a" * 64)
    queue.require_capability(
        "old-validator",
        "validator",
        revision="validator-v1",
        digest="a" * 64,
    )
    queue.require_capability(
        "new-validator",
        "validator",
        revision="validator-v2",
        digest="b" * 64,
    )

    queue.activate_capability(
        "validator",
        "validator-v2",
        "b" * 64,
        expected_revision="validator-v1",
        expected_digest="a" * 64,
    )
    lease = queue.claim("worker")

    assert lease is not None
    assert lease.unit_id == "new-validator"
    assert queue.status("old-validator") is WorkUnitStatus.READY


def test_accepted_finish_is_fenced_when_capability_head_changes(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v2", "b" * 64)
    queue.activate_capability_from_absent("validator", "validator-v1", "a" * 64)
    queue.require_capability(
        "package-a",
        "validator",
        revision="validator-v1",
        digest="a" * 64,
    )
    lease = queue.claim("worker")
    assert lease is not None

    queue.activate_capability(
        "validator",
        "validator-v2",
        "b" * 64,
        expected_revision="validator-v1",
        expected_digest="a" * 64,
    )

    with pytest.raises(
        DependencyNotSatisfiedError,
        match="dependencies changed before completion",
    ):
        queue.finish(
            lease,
            TerminalOutcome.ACCEPTED,
            output_digest="c" * 64,
            completion_revision="report-v1",
        )
    assert queue.status("package-a") is WorkUnitStatus.LEASED
    with closing(sqlite3.connect(queue.database)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM attempt_terminals").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM formal_completions").fetchone()[0] == 0
    result = queue.finish(
        lease,
        TerminalOutcome.INPUT_MISMATCH,
        output_digest="c" * 64,
    )
    assert result.disposition is FinishDisposition.TERMINAL_ONLY
    assert queue.status("package-a") is WorkUnitStatus.REPAIR_REQUIRED
    with closing(sqlite3.connect(queue.database)) as connection:
        terminal = connection.execute(
            """
            SELECT outcome, output_digest, completion_revision
            FROM attempt_terminals WHERE attempt_id = ?
            """,
            (lease.attempt_id,),
        ).fetchone()
    assert terminal == (TerminalOutcome.INPUT_MISMATCH.value, "c" * 64, None)


def test_capability_activation_history_is_append_only_and_never_rolls_back(
    queue: Queue,
) -> None:
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v2", "b" * 64)
    queue.activate_capability_from_absent("validator", "validator-v1", "a" * 64)
    queue.activate_capability(
        "validator",
        "validator-v2",
        "b" * 64,
        expected_revision="validator-v1",
        expected_digest="a" * 64,
    )
    queue.activate_capability(
        "validator",
        "validator-v2",
        "b" * 64,
        expected_revision="validator-v1",
        expected_digest="a" * 64,
    )

    with closing(sqlite3.connect(queue.database)) as connection:
        activations = connection.execute(
            """
            SELECT revision, digest FROM pipeline_capability_activations
            ORDER BY activation_id
            """
        ).fetchall()
    assert activations == [("validator-v1", "a" * 64), ("validator-v2", "b" * 64)]

    with pytest.raises(QueueConflictError, match="stale capability revision"):
        queue.activate_capability(
            "validator",
            "validator-v1",
            "a" * 64,
            expected_revision="validator-v2",
            expected_digest="b" * 64,
        )
    with pytest.raises(QueueConflictError, match="activation is not registered"):
        queue.activate_capability(
            "validator",
            "validator-v3",
            "c" * 64,
            expected_revision="validator-v2",
            expected_digest="b" * 64,
        )
    with pytest.raises(QueueConflictError, match="activation is not registered"):
        queue.activate_capability(
            "validator",
            "validator-v2",
            "c" * 64,
            expected_revision="validator-v2",
            expected_digest="b" * 64,
        )

    for statement in (
        "UPDATE pipeline_capability_activations SET revision = 'other'",
        "DELETE FROM pipeline_capability_activations",
    ):
        with (
            sqlite3.connect(queue.database) as connection,
            pytest.raises(sqlite3.IntegrityError, match="immutable"),
        ):
            connection.execute(statement)

    with (
        sqlite3.connect(queue.database) as connection,
        pytest.raises(sqlite3.IntegrityError, match="activation pin is not registered"),
    ):
        connection.execute(
            """
            INSERT INTO pipeline_capability_activations(capability, revision, digest)
            VALUES ('validator', 'validator-v2', ?)
            """,
            ("c" * 64,),
        )


def test_competing_capability_bootstraps_use_compare_and_swap(queue: Queue) -> None:
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v2", "b" * 64)
    context = get_context("spawn")

    with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
        outcomes = list(
            executor.map(
                _activate_from_absent_in_process,
                [str(queue.database)] * 2,
                [str(queue.attempts_root)] * 2,
                ["validator"] * 2,
                ["validator-v1", "validator-v2"],
                ["a" * 64, "b" * 64],
            )
        )

    successes = [outcome for outcome in outcomes if outcome.startswith("success:")]
    conflicts = [outcome for outcome in outcomes if outcome.startswith("conflict:")]
    assert len(successes) == 1
    assert len(conflicts) == 1
    winner = successes[0].removeprefix("success:")
    loser = conflicts[0].removeprefix("conflict:")
    digests = {"validator-v1": "a" * 64, "validator-v2": "b" * 64}

    queue.activate_capability_from_absent("validator", winner, digests[winner])
    with pytest.raises(QueueConflictError, match="head changed before activation"):
        queue.activate_capability_from_absent("validator", loser, digests[loser])

    with closing(sqlite3.connect(queue.database)) as connection:
        activations = connection.execute(
            """
            SELECT revision, digest FROM pipeline_capability_activations
            ORDER BY activation_id
            """
        ).fetchall()
    assert activations == [(winner, digests[winner])]


def test_competing_capability_activations_use_compare_and_swap(queue: Queue) -> None:
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v2", "b" * 64)
    queue.register_capability("validator", "validator-v3", "c" * 64)
    queue.activate_capability_from_absent("validator", "validator-v1", "a" * 64)
    context = get_context("spawn")

    with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
        outcomes = list(
            executor.map(
                _activate_in_process,
                [str(queue.database)] * 2,
                [str(queue.attempts_root)] * 2,
                ["validator"] * 2,
                ["validator-v2", "validator-v3"],
                ["b" * 64, "c" * 64],
                ["validator-v1"] * 2,
                ["a" * 64] * 2,
            )
        )

    successes = [
        outcome.removeprefix("success:")
        for outcome in outcomes
        if outcome.startswith("success:")
    ]
    conflicts = [
        outcome.removeprefix("conflict:")
        for outcome in outcomes
        if outcome.startswith("conflict:")
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    winner = successes[0]
    loser = conflicts[0]
    digests = {"validator-v2": "b" * 64, "validator-v3": "c" * 64}

    with closing(sqlite3.connect(queue.database)) as connection:
        activations = connection.execute(
            """
            SELECT revision, digest FROM pipeline_capability_activations
            ORDER BY activation_id
            """
        ).fetchall()
    assert activations == [("validator-v1", "a" * 64), (winner, digests[winner])]

    queue.activate_capability(
        "validator",
        winner,
        digests[winner],
        expected_revision="validator-v1",
        expected_digest="a" * 64,
    )
    with pytest.raises(QueueConflictError, match="head changed before activation"):
        queue.activate_capability(
            "validator",
            loser,
            digests[loser],
            expected_revision="validator-v1",
            expected_digest="a" * 64,
        )
    queue.activate_capability(
        "validator",
        loser,
        digests[loser],
        expected_revision=winner,
        expected_digest=digests[winner],
    )
    with closing(sqlite3.connect(queue.database)) as connection:
        final_history = connection.execute(
            """
            SELECT revision, digest FROM pipeline_capability_activations
            ORDER BY activation_id
            """
        ).fetchall()
    assert final_history == [
        ("validator-v1", "a" * 64),
        (winner, digests[winner]),
        (loser, digests[loser]),
    ]


def test_legacy_external_active_unit_is_visible_but_never_claimed(queue: Queue) -> None:
    queue.enqueue(
        "cluster-011",
        kind="cluster",
        cluster_id="cluster-011",
        input_digest="1" * 64,
        priority=1_000,
        execution_mode=ExecutionMode.LEGACY_EXTERNAL_ACTIVE,
    )
    _enqueue(queue, "package-next")

    lease = queue.claim("v2-worker")

    assert lease is not None
    assert lease.unit_id == "package-next"
    assert queue.status("cluster-011") is WorkUnitStatus.EXTERNAL_ACTIVE
    assert not (queue.attempts_root / "cluster-011").exists()


def test_attempt_workspaces_are_unique_and_never_removed(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("chat-a")
    assert lease is not None
    queue.finish(lease, TerminalOutcome.PARTIAL, output_digest="a" * 64)

    assert lease.workspace.is_dir()
    assert queue.status("package-a") is WorkUnitStatus.REPAIR_REQUIRED
    assert queue.claim("another-worker") is None


def test_repaired_unit_can_be_requeued_without_losing_attempt_history(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    first = queue.claim("chat-a")
    assert first is not None
    queue.finish(first, TerminalOutcome.PARTIAL, output_digest="a" * 64)

    queue.retry_repaired("package-a")
    second = queue.claim("chat-b")

    assert second is not None
    assert second.unit_id == "package-a"
    assert second.fencing_token == first.fencing_token + 1
    assert first.workspace.is_dir()
    assert second.workspace.is_dir()
    with closing(sqlite3.connect(queue.database)) as connection:
        outcomes = connection.execute(
            "SELECT outcome FROM attempt_terminals ORDER BY rowid"
        ).fetchall()
        events = connection.execute(
            "SELECT event_type FROM events WHERE attempt_id = ? ORDER BY event_id",
            (first.attempt_id,),
        ).fetchall()
    assert outcomes == [(TerminalOutcome.PARTIAL.value,)]
    assert ("REPAIR_REQUEUED",) in events


def test_only_repair_required_units_can_be_requeued(queue: Queue) -> None:
    _enqueue(queue, "package-a")

    with pytest.raises(QueueConflictError, match="not repair-required"):
        queue.retry_repaired("package-a")


def test_blocked_unit_can_be_requeued_after_its_blocker_is_resolved(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    first = queue.claim("chat-a")
    assert first is not None
    queue.finish(first, TerminalOutcome.BLOCKED)

    queue.retry_blocked("package-a")
    second = queue.claim("chat-b")

    assert second is not None
    assert second.unit_id == "package-a"
    assert second.fencing_token == first.fencing_token + 1
    with closing(sqlite3.connect(queue.database)) as connection:
        events = connection.execute(
            "SELECT event_type FROM events WHERE attempt_id = ? ORDER BY event_id",
            (first.attempt_id,),
        ).fetchall()
    assert ("BLOCKER_REQUEUED",) in events


def test_only_blocked_units_can_use_blocker_retry(queue: Queue) -> None:
    _enqueue(queue, "package-a")

    with pytest.raises(QueueConflictError, match="not blocked"):
        queue.retry_blocked("package-a")


def test_workspace_allocation_failure_is_recorded_without_untracked_attempt(
    monkeypatch: pytest.MonkeyPatch, queue: Queue
) -> None:
    _enqueue(queue, "package-a")

    def reject_attempt_directory(_lease: object) -> None:
        raise OSError("synthetic workspace failure")

    monkeypatch.setattr(queue, "_create_workspace", reject_attempt_directory)

    with pytest.raises(QueueError, match="could not create attempt workspace"):
        queue.claim("chat-a")

    assert queue.status("package-a") is WorkUnitStatus.REPAIR_REQUIRED
    with closing(sqlite3.connect(queue.database)) as connection, connection:
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 1
        assert connection.execute("SELECT outcome FROM attempt_terminals").fetchone()[0] == "FAILED"
        assert connection.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0


def test_workspace_interrupt_is_recorded_and_reraised_unchanged(
    monkeypatch: pytest.MonkeyPatch, queue: Queue
) -> None:
    _enqueue(queue, "package-a")
    interrupt = KeyboardInterrupt("synthetic interrupt")

    def interrupt_workspace(_lease: object) -> None:
        raise interrupt

    monkeypatch.setattr(queue, "_create_workspace", interrupt_workspace)

    with pytest.raises(KeyboardInterrupt) as raised:
        queue.claim("chat-a")

    assert raised.value is interrupt
    assert queue.status("package-a") is WorkUnitStatus.REPAIR_REQUIRED


def test_attempt_unit_symlink_cannot_escape_root(queue: Queue, tmp_path: Path) -> None:
    _enqueue(queue, "package-a")
    outside = tmp_path / "outside"
    outside.mkdir()
    (queue.attempts_root / "package-a").symlink_to(outside, target_is_directory=True)

    with pytest.raises(QueueError, match="could not create attempt workspace"):
        queue.claim("chat-a")

    assert not tuple(outside.iterdir())
    assert queue.status("package-a") is WorkUnitStatus.REPAIR_REQUIRED


def test_claim_never_returns_lease_recovered_during_workspace_publication(
    monkeypatch: pytest.MonkeyPatch, queue: Queue
) -> None:
    _enqueue(queue, "package-a")
    original_create = queue._create_workspace
    recovered: list[Lease | None] = []

    def recover_after_publication(lease: Lease) -> None:
        original_create(lease)
        with closing(sqlite3.connect(queue.database)) as connection, connection:
            connection.execute(
                """
                UPDATE leases
                SET expires_at = CAST(unixepoch('subsec') * 1000 AS INTEGER) - 1
                """
            )
        second_queue = Queue(queue.database, queue.attempts_root, busy_timeout_ms=1)
        recovered.append(second_queue.claim("chat-b"))

    monkeypatch.setattr(queue, "_create_workspace", recover_after_publication)

    with pytest.raises(StaleLeaseError):
        queue.claim("chat-a")

    assert recovered == [None]
    second_queue = Queue(queue.database, queue.attempts_root)
    second = second_queue.claim("chat-b")
    assert second is not None
    assert second.fencing_token == 2
    assert second.workspace.is_dir()
    with closing(sqlite3.connect(queue.database)) as connection, connection:
        attempts = connection.execute(
            "SELECT outcome FROM attempt_terminals ORDER BY finished_at"
        ).fetchall()
    assert attempts == [("ABANDONED",)]


def test_claim_rejects_capability_change_during_workspace_publication(
    monkeypatch: pytest.MonkeyPatch,
    queue: Queue,
) -> None:
    _enqueue(queue, "package-a")
    queue.register_capability("validator", "validator-v1", "a" * 64)
    queue.register_capability("validator", "validator-v2", "b" * 64)
    queue.activate_capability_from_absent("validator", "validator-v1", "a" * 64)
    queue.require_capability(
        "package-a",
        "validator",
        revision="validator-v1",
        digest="a" * 64,
    )
    original_create = queue._create_workspace
    published: list[Lease] = []

    def change_head_after_publication(lease: Lease) -> None:
        original_create(lease)
        published.append(lease)
        queue.activate_capability(
            "validator",
            "validator-v2",
            "b" * 64,
            expected_revision="validator-v1",
            expected_digest="a" * 64,
        )

    monkeypatch.setattr(queue, "_create_workspace", change_head_after_publication)

    with pytest.raises(
        DependencyNotSatisfiedError,
        match="dependencies changed during workspace publication",
    ):
        queue.claim("worker")

    assert len(published) == 1
    lease = published[0]
    assert lease.workspace.is_dir()
    assert queue.status("package-a") is WorkUnitStatus.REPAIR_REQUIRED
    with closing(sqlite3.connect(queue.database)) as connection:
        terminal = connection.execute(
            """
            SELECT outcome, output_digest, completion_revision
            FROM attempt_terminals WHERE attempt_id = ?
            """,
            (lease.attempt_id,),
        ).fetchone()
        lease_count = connection.execute(
            "SELECT COUNT(*) FROM leases WHERE unit_id = 'package-a'"
        ).fetchone()[0]
    assert terminal == (TerminalOutcome.INPUT_MISMATCH.value, None, None)
    assert lease_count == 0
