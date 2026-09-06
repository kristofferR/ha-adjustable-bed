"""Tests for non-model heartbeats and preimage-safe tracker publication."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import Event

import pytest

import tools.phase4_v2.queue.publisher as queue_publisher
from tools.phase4_v2.queue import (
    IssueDocument,
    Lease,
    PublisherConflictError,
    PublisherPostWriteConflictError,
    PublisherReadbackError,
    Queue,
    QueueConflictError,
    TerminalOutcome,
    WorkUnitStatus,
    publish_tracker,
    run_heartbeat,
)
from tools.phase4_v2.queue.tracker import GITHUB_ISSUE_BODY_MAX_CHARS, render_markdown


class _MemoryGateway:
    def __init__(self, body: str = "Manual introduction.\n") -> None:
        self.body = body
        self.revision = 1
        self.reject = False
        self.corrupt_readback = False

    def read(self, _issue_number: int) -> IssueDocument:
        body = self.body + "corrupt" if self.corrupt_readback and self.revision > 1 else self.body
        return IssueDocument(body, str(self.revision))

    def compare_and_replace(
        self,
        _issue_number: int,
        *,
        expected_revision: str,
        expected_body_sha256: str,
        body: str,
    ) -> bool:
        if self.reject:
            return False
        if expected_revision != str(self.revision):
            return False
        if hashlib.sha256(self.body.encode()).hexdigest() != expected_body_sha256:
            return False
        self.body = body
        self.revision += 1
        return True


@pytest.fixture
def publisher_queue(tmp_path: Path) -> tuple[Queue, Lease]:
    queue = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    queue.initialize()
    queue.enqueue(
        "tracker-publisher",
        kind="tracker",
        input_digest="a" * 64,
        priority=100,
    )
    lease = queue.claim("publisher-a")
    assert lease is not None
    return queue, lease


def test_publisher_preserves_manual_text_and_exactly_reads_back(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    gateway = _MemoryGateway()

    first = publish_tracker(queue, lease, gateway, 542)
    generation_after_publish = queue.snapshot().generation_id
    second = publish_tracker(queue, lease, gateway, 542)

    assert first.changed is True
    assert second.changed is False
    assert gateway.body.startswith("Manual introduction.\n\n")
    assert gateway.body.count("<!-- phase4-v2-tracker:start") == 1
    assert first.queue_generation == generation_after_publish
    assert second.queue_generation == generation_after_publish
    with closing(sqlite3.connect(queue.database)) as connection, connection:
        event_types = tuple(
            row[0]
            for row in connection.execute(
                "SELECT event_type FROM events WHERE event_type LIKE 'TRACKER_DOCUMENT_%' "
                "ORDER BY event_id"
            )
        )
    assert event_types == (
        "TRACKER_DOCUMENT_PUBLISHED",
        "TRACKER_DOCUMENT_ALREADY_CURRENT",
    )


def test_publisher_replaces_an_existing_block_without_reserving_a_separator(
    monkeypatch: pytest.MonkeyPatch,
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    rendered = render_markdown(queue.snapshot())
    gateway = _MemoryGateway(rendered)
    monkeypatch.setattr(queue_publisher, "GITHUB_ISSUE_BODY_MAX_CHARS", len(rendered))

    receipt = publish_tracker(queue, lease, gateway, 542)

    assert receipt.changed is False
    assert gateway.body == rendered


def test_publisher_rejects_issue_cas_conflict(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    gateway = _MemoryGateway()
    gateway.reject = True

    with pytest.raises(PublisherConflictError, match="issue body changed"):
        publish_tracker(queue, lease, gateway, 542)


def test_publisher_rejects_inexact_readback(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    gateway = _MemoryGateway()
    gateway.corrupt_readback = True

    with pytest.raises(PublisherReadbackError, match="exact"):
        publish_tracker(queue, lease, gateway, 542)


def test_tracker_publication_truncates_units_to_the_available_issue_body_budget(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    for index in range(255):
        queue.enqueue(
            f"unit-{index:03d}-" + "x" * 191,
            kind="kind-" + "y" * 195,
            cluster_id="cluster-" + "z" * 192,
            input_digest=f"{index:064x}",
        )

    rendered = render_markdown(queue.snapshot())
    assert len(rendered) <= GITHUB_ISSUE_BODY_MAX_CHARS
    assert "additional units omitted" in rendered

    gateway = _MemoryGateway("Manual introduction.\n" + "m" * 30_000)
    receipt = publish_tracker(queue, lease, gateway, 542)

    assert receipt.changed is True
    assert len(gateway.body) <= GITHUB_ISSUE_BODY_MAX_CHARS
    assert "additional units omitted" in gateway.body


def test_publisher_rejects_queue_drift_before_write(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue

    class DriftingGateway(_MemoryGateway):
        def read(self, issue_number: int) -> IssueDocument:
            queue.register_capability("validator", "validator-v2", "b" * 64)
            return super().read(issue_number)

    with pytest.raises(PublisherConflictError, match="queue changed"):
        publish_tracker(queue, lease, DriftingGateway(), 542)


def test_publisher_reports_post_write_queue_drift_for_retry(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue

    class PostWriteDriftingGateway(_MemoryGateway):
        def read(self, issue_number: int) -> IssueDocument:
            document = super().read(issue_number)
            if self.revision > 1:
                queue.register_capability("validator", "validator-v2", "b" * 64)
            return document

    gateway = PostWriteDriftingGateway()
    with pytest.raises(PublisherPostWriteConflictError, match="written but queue changed"):
        publish_tracker(queue, lease, gateway, 542)

    assert "<!-- phase4-v2-tracker:start" in gateway.body


def test_publisher_wraps_post_write_checkpoint_failure(
    monkeypatch: pytest.MonkeyPatch,
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    gateway = _MemoryGateway()

    def fail_checkpoint(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic checkpoint failure")

    monkeypatch.setattr(queue, "_checkpoint_internal", fail_checkpoint)

    with pytest.raises(
        PublisherPostWriteConflictError,
        match="publication event could not be recorded",
    ):
        publish_tracker(queue, lease, gateway, 542)
    assert "<!-- phase4-v2-tracker:start" in gateway.body


def test_public_checkpoint_cannot_hide_internal_event_names(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue

    for event_type in (
        "RENEWED",
        "TRACKER_PUBLISHED",
        "TRACKER_ALREADY_CURRENT",
        "TRACKER_DOCUMENT_PUBLISHED",
        "TRACKER_DOCUMENT_ALREADY_CURRENT",
    ):
        with pytest.raises(ValueError, match="reserved"):
            queue.checkpoint(lease, event_type)


def test_publication_guard_excludes_a_second_local_publisher(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, _ = publisher_queue

    with (
        queue_publisher._publication_guard(queue),
        pytest.raises(PublisherConflictError, match="another tracker publisher"),
        queue_publisher._publication_guard(queue),
    ):
        pytest.fail("second publisher unexpectedly acquired the guard")


def test_publication_guard_prevents_lease_recovery_and_reclaim(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, first = publisher_queue
    challenger = Queue(queue.database, queue.attempts_root, busy_timeout_ms=1)

    with queue_publisher._publication_guard(queue):
        with closing(sqlite3.connect(queue.database)) as connection, connection:
            connection.execute("UPDATE leases SET expires_at = 1")

        assert challenger.claim("publisher-b") is None
        assert challenger.recover() == 0
        assert queue.status(first.unit_id) is WorkUnitStatus.LEASED

    second = challenger.claim("publisher-b")
    assert second is not None
    assert second.unit_id == first.unit_id
    assert second.fencing_token == first.fencing_token + 1


def test_publication_guard_prevents_attempt_completion_during_write(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    competing_queue = Queue(queue.database, queue.attempts_root, busy_timeout_ms=1)
    blocked = []

    class CompletingGateway(_MemoryGateway):
        def compare_and_replace(
            self,
            issue_number: int,
            *,
            expected_revision: str,
            expected_body_sha256: str,
            body: str,
        ) -> bool:
            with pytest.raises(QueueConflictError, match="publication") as error:
                competing_queue.finish(lease, TerminalOutcome.PARTIAL)
            blocked.append(error.value)
            assert queue.status(lease.unit_id) is WorkUnitStatus.LEASED
            return super().compare_and_replace(
                issue_number,
                expected_revision=expected_revision,
                expected_body_sha256=expected_body_sha256,
                body=body,
            )

    publish_tracker(queue, lease, CompletingGateway(), 542)

    assert len(blocked) == 1
    competing_queue.finish(lease, TerminalOutcome.PARTIAL)
    assert queue.status(lease.unit_id) is WorkUnitStatus.REPAIR_REQUIRED


def test_publication_guard_prevents_repaired_unit_retry(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    queue.finish(lease, TerminalOutcome.PARTIAL)
    competing_queue = Queue(queue.database, queue.attempts_root, busy_timeout_ms=1)

    with queue_publisher._publication_guard(queue), pytest.raises(
        QueueConflictError, match="publication"
    ):
        competing_queue.retry_repaired(lease.unit_id)

    assert queue.status(lease.unit_id) is WorkUnitStatus.REPAIR_REQUIRED


class _StopOnFirstWait(Event):
    def wait(self, timeout: float | None = None) -> bool:
        del timeout
        return True


def test_heartbeat_renews_without_tracker_generation_churn(
    publisher_queue: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher_queue
    before = queue.snapshot()
    renewed = []

    current = run_heartbeat(
        queue,
        lease,
        _StopOnFirstWait(),
        ttl_seconds=60,
        interval_seconds=10,
        on_renewed=renewed.append,
    )

    after = queue.snapshot()
    assert renewed == [current]
    assert after.generation_id == before.generation_id
    assert after.event_watermark == before.event_watermark


@pytest.mark.parametrize(
    ("ttl", "interval"),
    [(0, 1.0), (10, 0), (10, 10), (10, float("nan")), (10, float("inf"))],
)
def test_heartbeat_rejects_unsafe_intervals(
    publisher_queue: tuple[Queue, Lease], ttl: int, interval: float
) -> None:
    queue, lease = publisher_queue

    with pytest.raises(ValueError):
        run_heartbeat(
            queue,
            lease,
            Event(),
            ttl_seconds=ttl,
            interval_seconds=interval,
        )
