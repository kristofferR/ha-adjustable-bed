"""Deployment checks for a separately owned queue service, not snapshot authentication.

Passing this check does not authenticate caller-created QueueSnapshot objects.
Formal consumers still need a service adapter that supplies authenticated state.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from .core import Queue, QueueConflictError

_PIN_PATH = Path("/etc/ha-adjustable-bed/phase4-v2-queue.json")
_REVISION = "phase4-v2-queue-deployment-v1"


def assert_queue_service_deployment(queue: Queue) -> None:
    """Check the external path/inode pin and exclude analyst filesystem writes."""
    pin = _load_pin()
    if pin["revision"] != _REVISION:
        raise QueueConflictError("unsupported queue deployment revision")
    for field in ("writer_uid", "analyst_uid", "device", "inode"):
        value = pin[field]
        if type(value) is not int or not 0 <= value < 2**64:
            raise QueueConflictError("invalid queue deployment identity")
    writer = pin["writer_uid"]
    if writer == pin["analyst_uid"]:
        raise QueueConflictError("queue service must have a different UID from analysts")
    database = queue.database.absolute()
    if str(database) != pin["database"] or database.resolve() != database:
        raise QueueConflictError("queue database differs from protected deployment path")
    before = database.lstat()
    if (before.st_dev, before.st_ino) != (pin["device"], pin["inode"]):
        raise QueueConflictError("queue database differs from protected deployment inode")
    for parent in database.parents:
        metadata = parent.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid not in {0, writer}
            or metadata.st_mode & 0o022
        ):
            raise QueueConflictError("queue service directory is writable outside its owner")
    for path in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if path == database:
                raise QueueConflictError("queue service database disappeared") from None
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != writer
            or metadata.st_mode & 0o022
            or metadata.st_nlink != 1
        ):
            raise QueueConflictError("queue service storage is not exclusively writer-owned")
    after = database.lstat()
    if _identity(before) != _identity(after):
        raise QueueConflictError("queue deployment changed during validation")


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_ctime_ns,
    )


def _load_pin() -> dict[str, object]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        directory = os.open(_PIN_PATH.parent, flags | os.O_DIRECTORY)
        try:
            parent = os.fstat(directory)
            if parent.st_uid != 0 or parent.st_mode & 0o022:
                raise QueueConflictError("queue deployment pin parent is unsafe")
            descriptor = os.open(_PIN_PATH.name, flags, dir_fd=directory)
            try:
                before = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != 0
                    or before.st_mode & 0o022
                    or before.st_nlink != 1
                    or not 0 < before.st_size <= 16 * 1024
                ):
                    raise QueueConflictError("queue deployment pin is unsafe or unbounded")
                with os.fdopen(os.dup(descriptor), "rb") as stream:
                    raw = stream.read(16 * 1024 + 1)
                if (
                    _identity(before) != _identity(os.fstat(descriptor))
                    or _identity(parent) != _identity(os.fstat(directory))
                    or len(raw) != before.st_size
                ):
                    raise QueueConflictError("queue deployment pin changed during read")
            finally:
                os.close(descriptor)
        finally:
            os.close(directory)
        value = json.loads(raw)
        if (
            type(value) is not dict
            or set(value)
            != {"revision", "database", "writer_uid", "analyst_uid", "device", "inode"}
            or json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n" != raw
        ):
            raise QueueConflictError("queue deployment pin is not exact canonical JSON")
        return value
    except (OSError, ValueError, RecursionError) as error:
        raise QueueConflictError(
            "protected queue deployment pin is unavailable or invalid"
        ) from error
