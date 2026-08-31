"""Tests for the bounded Phase 4 v2 queue CLI and tracker renderers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from tools.phase4_v2.queue import (
    ExecutionMode,
    Queue,
    QueueError,
    TerminalOutcome,
    WorkUnitStatus,
    managed_block_sha256,
    render_html,
    render_markdown,
    replace_managed_block,
)
from tools.phase4_v2.queue.cli import main


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    instance = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    instance.initialize()
    return instance


def _args(queue: Queue, *command: str) -> list[str]:
    return [
        "--database",
        str(queue.database),
        "--attempts-root",
        str(queue.attempts_root),
        *command,
    ]


def _enqueue(queue: Queue, unit_id: str, *, mode: ExecutionMode = ExecutionMode.NORMAL) -> None:
    queue.enqueue(
        unit_id,
        kind="package",
        cluster_id="cluster-001",
        input_digest=(unit_id.encode().hex() + "0" * 64)[:64],
        execution_mode=mode,
    )


def test_snapshot_and_renderers_share_one_deterministic_generation(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    _enqueue(queue, "legacy-active", mode=ExecutionMode.LEGACY_EXTERNAL_ACTIVE)
    queue.require_capability(
        "package-a",
        "preflight",
        revision="preflight-v2",
        digest="c" * 64,
    )

    first = queue.snapshot()
    second = queue.snapshot()

    assert first == second
    assert first.generation_id == second.generation_id
    assert [unit.status for unit in first.units] == [
        WorkUnitStatus.READY,
        WorkUnitStatus.EXTERNAL_ACTIVE,
    ]
    markdown = render_markdown(first)
    html = render_html(first)
    assert first.generation_id in markdown
    assert first.generation_id in html
    assert "| EXTERNAL_ACTIVE | 1 |" in markdown
    assert "legacy-active" in html

    queue.register_capability("preflight", "preflight-v2", "c" * 64)
    capability_changed = queue.snapshot()
    assert capability_changed.event_watermark == first.event_watermark
    assert capability_changed.scheduler_state_digest != first.scheduler_state_digest
    assert capability_changed.generation_id != first.generation_id
    assert queue.claim("worker-a") is None

    queue.activate_capability_from_absent("preflight", "preflight-v2", "c" * 64)
    lease = queue.claim("worker-a")
    assert lease is not None
    changed = queue.snapshot()
    assert changed.generation_id != capability_changed.generation_id
    assert changed.event_watermark > first.event_watermark


def test_managed_block_replacement_requires_exact_preimage_generation(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    first = render_markdown(queue.snapshot())
    body = "Manual introduction.\n\n" + first + "\nManual footer.\n"
    old_generation = queue.snapshot().generation_id
    lease = queue.claim("worker-a")
    assert lease is not None
    updated = render_markdown(queue.snapshot())

    replaced = replace_managed_block(
        body,
        updated,
        expected_generation=old_generation,
        expected_block_sha256=managed_block_sha256(body),
    )

    assert replaced.startswith("Manual introduction.")
    assert replaced.endswith("Manual footer.\n")
    assert updated.strip() in replaced
    with pytest.raises(ValueError, match="generation changed"):
        replace_managed_block(
            body,
            updated,
            expected_generation="0" * 64,
            expected_block_sha256=managed_block_sha256(body),
        )
    changed_content = body.replace("| READY | 1 |", "| READY | 999 |")
    with pytest.raises(ValueError, match="block changed"):
        replace_managed_block(
            changed_content,
            updated,
            expected_generation=old_generation,
            expected_block_sha256=managed_block_sha256(body),
        )
    with pytest.raises(ValueError, match="disappeared"):
        replace_managed_block(
            "Manual only",
            updated,
            expected_generation=old_generation,
            expected_block_sha256=managed_block_sha256(body),
        )


def test_managed_block_rejects_reversed_or_multiple_markers(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    rendered = render_markdown(queue.snapshot())
    reversed_markers = (
        "<!-- phase4-v2-tracker:end -->\n"
        "<!-- phase4-v2-tracker:start generation=" + "0" * 64 + " -->\n"
    )

    with pytest.raises(ValueError, match="malformed"):
        managed_block_sha256(reversed_markers)
    with pytest.raises(ValueError, match="malformed"):
        replace_managed_block(
            rendered + rendered,
            rendered,
            expected_generation=queue.snapshot().generation_id,
            expected_block_sha256=managed_block_sha256(rendered),
        )


def test_cli_claim_checkpoint_finish_status_and_render(
    queue: Queue, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _enqueue(queue, "package-a")

    assert main(_args(queue, "claim", "--owner", "worker-a")) == 0
    claimed = json.loads(capsys.readouterr().out)
    assert claimed["claimed"] is True
    lease_file = tmp_path / "lease.json"
    lease_file.write_text(json.dumps(claimed["lease"]), encoding="utf-8")
    payload_file = tmp_path / "payload.json"
    payload_file.write_text('{"stage":"report_frozen"}', encoding="utf-8")

    assert (
        main(
            _args(
                queue,
                "checkpoint",
                "--lease-file",
                str(lease_file),
                "--event-type",
                "REPORT_FROZEN",
                "--payload-file",
                str(payload_file),
            )
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"checkpointed": True}
    assert (
        main(
            _args(
                queue,
                "finish",
                "--lease-file",
                str(lease_file),
                "--outcome",
                "ACCEPTED",
                "--output-digest",
                "a" * 64,
                "--completion-revision",
                "report-v1",
            )
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["disposition"] == "COMPLETED"

    assert main(_args(queue, "status", "--unit-id", "package-a")) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "COMPLETED",
        "unit_id": "package-a",
    }
    assert main(_args(queue, "render", "--format", "markdown")) == 0
    assert "<!-- phase4-v2-tracker:start" in capsys.readouterr().out


def test_cli_recover_and_unsafe_lease_file_fail_closed(
    queue: Queue, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("worker-a")
    assert lease is not None
    with closing(sqlite3.connect(queue.database)) as connection, connection:
        connection.execute("UPDATE leases SET expires_at = 1")

    assert main(_args(queue, "recover")) == 0
    assert json.loads(capsys.readouterr().out) == {"recovered": 1}
    assert queue.status("package-a") is WorkUnitStatus.READY

    actual = tmp_path / "lease.json"
    actual.write_text("{}", encoding="utf-8")
    alias = tmp_path / "lease-link.json"
    alias.symlink_to(actual)
    assert (
        main(
            _args(
                queue,
                "renew",
                "--lease-file",
                str(alias),
            )
        )
        == 2
    )
    assert "unsafe or inaccessible" in capsys.readouterr().err


def test_cli_requeues_an_explicitly_repaired_unit(
    queue: Queue, capsys: pytest.CaptureFixture[str]
) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("worker-a")
    assert lease is not None
    queue.finish(lease, TerminalOutcome.FAILED)

    assert main(_args(queue, "retry-repaired", "--unit-id", "package-a")) == 0

    assert json.loads(capsys.readouterr().out) == {
        "retried": True,
        "unit_id": "package-a",
    }
    assert queue.status("package-a") is WorkUnitStatus.READY


def test_cli_refuses_to_create_missing_queue(tmp_path: Path) -> None:
    missing = Queue(tmp_path / "missing.sqlite3", tmp_path / "missing-attempts")
    with pytest.raises(QueueError, match="database is missing or inaccessible"):
        missing.status("package-a")
    assert not missing.database.exists()

    with pytest.raises(SystemExit):
        main(
            [
                "--database",
                str(tmp_path / "missing.sqlite3"),
                "--attempts-root",
                str(tmp_path / "missing-attempts"),
                "status",
            ]
        )
    assert not (tmp_path / "missing.sqlite3").exists()


@pytest.mark.parametrize("revision", [1, 3])
def test_every_operation_rejects_incompatible_schema_without_mutation(
    revision: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / f"schema-{revision}" / "queue.sqlite3"
    attempts_root = tmp_path / f"attempts-{revision}"
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
            "INSERT INTO schema_meta VALUES (1, ?, ?, ?, ?)",
            (
                revision,
                str(attempts_root.resolve()),
                root_stat.st_dev,
                root_stat.st_ino,
            ),
        )
    incompatible = Queue(database, attempts_root)

    with pytest.raises(QueueError, match=f"unsupported queue schema revision: {revision}"):
        incompatible.status("package-a")
    with pytest.raises(QueueError, match=f"unsupported queue schema revision: {revision}"):
        incompatible.enqueue(
            "package-a",
            kind="package",
            input_digest="a" * 64,
        )

    assert main(_args(incompatible, "claim", "--owner", "worker")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"unsupported queue schema revision: {revision}" in captured.err
    assert not database.with_name(database.name + ".tracker-publisher.lock").exists()
    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert tables == {"schema_meta"}


def test_finish_snapshot_reports_latest_terminal(queue: Queue) -> None:
    _enqueue(queue, "package-a")
    lease = queue.claim("worker-a")
    assert lease is not None
    queue.finish(lease, TerminalOutcome.PARTIAL, output_digest="b" * 64)

    unit = queue.snapshot().units[0]
    assert unit.latest_outcome is TerminalOutcome.PARTIAL
    assert unit.attempt_count == 1
    assert unit.output_digest is None
