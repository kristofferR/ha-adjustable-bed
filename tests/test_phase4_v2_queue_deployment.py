"""Deployment assertions reject analyst-owned queues and changing authority files."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.phase4_v2.orchestration.completion as completion
import tools.phase4_v2.queue.deployment as deployment
from tools.phase4_v2.queue import Queue, QueueConflictError


def test_queue_deployment_rejects_the_analyst_as_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = Queue(tmp_path / "queue.sqlite3", tmp_path / "attempts")
    monkeypatch.setattr(
        deployment,
        "_load_pin",
        lambda: {
            "revision": "phase4-v2-queue-deployment-v1",
            "database": str(queue.database),
            "writer_uid": os.getuid(),
            "analyst_uid": os.getuid(),
            "device": 1,
            "inode": 1,
        },
    )
    with pytest.raises(QueueConflictError, match="different UID"):
        deployment.assert_queue_service_deployment(queue)


@pytest.mark.parametrize("mutation", [None, "mode", "uid", "gid", "nlink", "ctime", "oversize"])
def test_stage_config_checks_complete_metadata_before_and_after_read(
    monkeypatch: pytest.MonkeyPatch, mutation: str | None
) -> None:
    payload = json.dumps(
        {
            stage: {"authority_sha256": "a" * 64, "generation": 1}
            for stage in ("audit", "reconciliation", "implementation", "publication")
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    directory = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o755,
        st_uid=0,
        st_gid=0,
        st_dev=1,
        st_ino=1,
        st_size=4096,
        st_nlink=2,
        st_mtime_ns=1,
        st_ctime_ns=1,
    )
    before = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_uid=0,
        st_gid=0,
        st_dev=1,
        st_ino=2,
        st_size=len(payload),
        st_nlink=1,
        st_mtime_ns=1,
        st_ctime_ns=1,
    )
    after = SimpleNamespace(**vars(before))
    if mutation == "oversize":
        before.st_size = 16 * 1024 + 1
    elif mutation is not None:
        field = {
            "mode": "st_mode",
            "uid": "st_uid",
            "gid": "st_gid",
            "nlink": "st_nlink",
            "ctime": "st_ctime_ns",
        }[mutation]
        setattr(after, field, getattr(after, field) + 1)
    reads = iter((payload, b""))
    file_stats = iter((before, after))
    fake_os = SimpleNamespace(
        **{
            name: getattr(os, name)
            for name in ("O_RDONLY", "O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
        }
    )
    fake_os.open = lambda path, _flags, **_kwargs: 1 if path == "/etc/ha-adjustable-bed" else 2
    fake_os.fstat = lambda fd: directory if fd == 1 else next(file_stats)
    fake_os.read = lambda _fd, _size: next(reads)
    fake_os.close = lambda _fd: None
    monkeypatch.setattr(completion, "os", fake_os)
    if mutation is None:
        assert len(completion._load_stage_authority_config()) == 4
    else:
        with pytest.raises(QueueConflictError):
            completion._load_stage_authority_config()
