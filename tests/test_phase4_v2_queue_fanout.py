from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.phase4_v2.queue.fanout as fanout_module
from tools.phase4_v2.queue import (
    FanoutPublishReceipt,
    GitHubTreeGateway,
    Lease,
    PublisherConflictError,
    PublisherPostWriteConflictError,
    Queue,
    QueueConflictError,
    TrackerDocument,
    TrackerDocumentSet,
    TrackerFormat,
    TrackerTarget,
    document_set_sha256,
    publication_config_sha256,
    publish_tracker_fanout,
)
from tools.phase4_v2.queue.publication_config import TrackerPublicationConfig

_REVISION = "a" * 40
_NEXT_REVISION = "b" * 40
_TARGETS = (
    TrackerTarget("issues/436.md", TrackerFormat.MARKDOWN),
    TrackerTarget("issues/443.md", TrackerFormat.MARKDOWN),
    TrackerTarget("public/queue.html", TrackerFormat.HTML),
)
_CONFIG = TrackerPublicationConfig("owner/repository", "tracker", _TARGETS)
_PROTECTED_CONFIG_LOADER = fanout_module._load_protected_publication_config_sha256


@pytest.fixture(autouse=True)
def _protected_publication_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fanout_module,
        "_load_protected_publication_config_sha256",
        lambda: _CONFIG.sha256,
    )


class _MemorySetGateway:
    def __init__(self, repository: str = _CONFIG.repository, branch: str = _CONFIG.branch) -> None:
        self.repository = repository
        self.branch = branch
        self.revision = _REVISION
        self.documents: dict[str, bytes] = {}
        self.reject = False
        self.corrupt_readback = False
        self.writes = 0

    def read(self, paths: tuple[str, ...]) -> TrackerDocumentSet:
        documents = tuple(
            TrackerDocument(
                path,
                (
                    self.documents.get(path, b"") + b"corrupt"
                    if self.corrupt_readback and self.writes
                    else self.documents.get(path)
                ),
            )
            for path in paths
        )
        return TrackerDocumentSet(self.revision, documents)

    def compare_and_replace(
        self,
        *,
        expected_revision: str,
        expected_documents_sha256: str,
        documents: tuple[TrackerDocument, ...],
    ) -> bool:
        current = tuple(
            TrackerDocument(item.path, self.documents.get(item.path)) for item in documents
        )
        if (
            self.reject
            or expected_revision != self.revision
            or expected_documents_sha256 != document_set_sha256(current)
        ):
            return False
        self.documents = {item.path: item.body or b"" for item in documents}
        self.revision = _NEXT_REVISION
        self.writes += 1
        return True


def _sealed_gateway(
    monkeypatch: pytest.MonkeyPatch, backend: _MemorySetGateway
) -> GitHubTreeGateway:
    monkeypatch.setattr(
        GitHubTreeGateway,
        "read",
        lambda _self, paths: backend.read(paths),
    )
    monkeypatch.setattr(
        GitHubTreeGateway,
        "compare_and_replace",
        lambda _self, **values: backend.compare_and_replace(**values),
    )
    return GitHubTreeGateway(backend.repository, backend.branch)


@pytest.fixture
def publisher(tmp_path: Path) -> tuple[Queue, Lease]:
    queue = Queue(tmp_path / "state" / "queue.sqlite3", tmp_path / "attempts")
    queue.initialize()
    queue.enqueue("publisher", kind="tracker", input_digest="c" * 64)
    lease = queue.claim("publisher")
    assert lease is not None
    return queue, lease


def test_fanout_publishes_markdown_and_html_from_one_snapshot(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    gateway = _MemorySetGateway()
    sealed = _sealed_gateway(monkeypatch, gateway)

    receipt = publish_tracker_fanout(queue, lease, sealed, _CONFIG)

    assert receipt.changed
    assert receipt.paths == tuple(item.path for item in _TARGETS)
    assert receipt.publication_config_sha256 == publication_config_sha256(_CONFIG)
    markdown = gateway.documents["issues/436.md"]
    assert markdown == gateway.documents["issues/443.md"]
    assert receipt.queue_generation.encode() in markdown
    assert receipt.queue_generation.encode() in gateway.documents["public/queue.html"]
    assert receipt.document_set_sha256 == document_set_sha256(
        tuple(TrackerDocument(path, body) for path, body in sorted(gateway.documents.items()))
    )
    assert fanout_module._authenticate_tracker_fanout_receipt(
        queue, sealed, _CONFIG, receipt
    ) == receipt


def test_fanout_receipt_is_reauthenticated_against_remote_state(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    backend = _MemorySetGateway()
    sealed = _sealed_gateway(monkeypatch, backend)
    receipt = publish_tracker_fanout(queue, lease, sealed, _CONFIG)
    forged = object.__new__(FanoutPublishReceipt)
    for name in (
        "queue_generation",
        "before_revision",
        "after_revision",
        "publication_config_sha256",
        "paths",
        "changed",
    ):
        object.__setattr__(forged, name, getattr(receipt, name))
    object.__setattr__(forged, "document_set_sha256", "f" * 64)

    with pytest.raises(PublisherConflictError, match="current tracker documents"):
        fanout_module._authenticate_tracker_fanout_receipt(queue, sealed, _CONFIG, forged)

    backend.documents[_TARGETS[0].path] = b"hostile remote replacement"
    with pytest.raises(PublisherConflictError, match="remote tracker tree"):
        fanout_module._authenticate_tracker_fanout_receipt(queue, sealed, _CONFIG, receipt)


def test_fanout_receipt_reauthentication_rejects_fake_gateway_and_rotated_config(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    backend = _MemorySetGateway()
    sealed = _sealed_gateway(monkeypatch, backend)
    receipt = publish_tracker_fanout(queue, lease, sealed, _CONFIG)

    with pytest.raises(PublisherConflictError, match="sealed GitHub tree gateway"):
        fanout_module._authenticate_tracker_fanout_receipt(queue, backend, _CONFIG, receipt)

    monkeypatch.setattr(
        fanout_module,
        "_load_protected_publication_config_sha256",
        lambda: "f" * 64,
    )
    with pytest.raises(PublisherConflictError, match="protected deployment pin"):
        fanout_module._authenticate_tracker_fanout_receipt(queue, sealed, _CONFIG, receipt)


def test_fanout_receipt_reauthentication_rejects_stale_queue_generation(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    backend = _MemorySetGateway()
    sealed = _sealed_gateway(monkeypatch, backend)
    receipt = publish_tracker_fanout(queue, lease, sealed, _CONFIG)
    queue.enqueue("late-work", kind="analysis", input_digest="d" * 64)

    with pytest.raises(PublisherConflictError, match="another queue generation"):
        fanout_module._authenticate_tracker_fanout_receipt(queue, sealed, _CONFIG, receipt)


def test_fanout_is_idempotent_without_a_second_commit(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    gateway = _MemorySetGateway()
    sealed = _sealed_gateway(monkeypatch, gateway)
    publish_tracker_fanout(queue, lease, sealed, _CONFIG)

    receipt = publish_tracker_fanout(queue, lease, sealed, _CONFIG)

    assert not receipt.changed
    assert gateway.writes == 1
    assert receipt.before_revision == receipt.after_revision == _NEXT_REVISION


def test_fanout_rejects_atomic_compare_and_swap_conflict(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    gateway = _MemorySetGateway()
    gateway.reject = True

    with pytest.raises(PublisherConflictError, match="document set changed"):
        publish_tracker_fanout(
            queue, lease, _sealed_gateway(monkeypatch, gateway), _CONFIG
        )
    assert gateway.writes == 0


def test_fanout_fails_closed_on_inexact_readback(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    gateway = _MemorySetGateway()
    gateway.corrupt_readback = True

    with pytest.raises(PublisherPostWriteConflictError, match="exact readback"):
        publish_tracker_fanout(
            queue, lease, _sealed_gateway(monkeypatch, gateway), _CONFIG
        )


def test_fanout_rejects_unsorted_duplicate_or_unsafe_targets(
    publisher: tuple[Queue, Lease],
) -> None:
    _queue, _lease = publisher

    with pytest.raises(ValueError, match="sorted"):
        TrackerPublicationConfig(_CONFIG.repository, _CONFIG.branch, tuple(reversed(_TARGETS)))
    with pytest.raises(ValueError, match="unique"):
        TrackerPublicationConfig(_CONFIG.repository, _CONFIG.branch, (_TARGETS[0], _TARGETS[0]))
    with pytest.raises(ValueError, match="canonical"):
        TrackerTarget("../queue.md", TrackerFormat.MARKDOWN)


def test_document_set_digest_binds_missing_vs_empty() -> None:
    missing = (TrackerDocument("queue.md", None),)
    empty = (TrackerDocument("queue.md", b""),)

    assert document_set_sha256(missing) != document_set_sha256(empty)


def test_publication_config_binds_renderer_format() -> None:
    markdown = (TrackerTarget("queue/output", TrackerFormat.MARKDOWN),)
    html = (TrackerTarget("queue/output", TrackerFormat.HTML),)

    assert publication_config_sha256(
        TrackerPublicationConfig("owner/repository", "tracker", markdown)
    ) != publication_config_sha256(TrackerPublicationConfig("owner/repository", "tracker", html))


def test_fanout_rejects_cross_repository_and_branch_replay(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher
    other_repository = TrackerPublicationConfig("other/repository", "tracker", _TARGETS)
    other_branch = TrackerPublicationConfig("owner/repository", "other", _TARGETS)

    assert other_repository.sha256 != _CONFIG.sha256
    assert other_branch.sha256 != _CONFIG.sha256
    gateway = _sealed_gateway(monkeypatch, _MemorySetGateway())
    with pytest.raises(PublisherConflictError, match="protected deployment pin"):
        publish_tracker_fanout(queue, lease, gateway, other_repository)
    with pytest.raises(PublisherConflictError, match="protected deployment pin"):
        publish_tracker_fanout(queue, lease, gateway, other_branch)


def test_fanout_rejects_gateway_bound_to_another_endpoint(
    publisher: tuple[Queue, Lease],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue, lease = publisher

    with pytest.raises(PublisherConflictError, match="endpoint"):
        publish_tracker_fanout(
            queue,
            lease,
            _sealed_gateway(
                monkeypatch, _MemorySetGateway("attacker/repository", "tracker")
            ),
            _CONFIG,
        )


def test_fanout_rejects_caller_supplied_gateway_and_subclass(
    publisher: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher

    with pytest.raises(PublisherConflictError, match="sealed GitHub tree gateway"):
        publish_tracker_fanout(queue, lease, _MemorySetGateway(), _CONFIG)

    class HostileGateway(GitHubTreeGateway):
        def read(self, paths: tuple[str, ...]) -> TrackerDocumentSet:
            return _MemorySetGateway().read(paths)

    with pytest.raises(PublisherConflictError, match="sealed GitHub tree gateway"):
        publish_tracker_fanout(
            queue,
            lease,
            HostileGateway(_CONFIG.repository, _CONFIG.branch),
            _CONFIG,
        )


def test_fanout_requires_exact_protected_publication_config(
    publisher: tuple[Queue, Lease], monkeypatch: pytest.MonkeyPatch
) -> None:
    queue, lease = publisher
    monkeypatch.setattr(
        fanout_module,
        "_load_protected_publication_config_sha256",
        lambda: "f" * 64,
    )

    with pytest.raises(PublisherConflictError, match="protected deployment pin"):
        publish_tracker_fanout(
            queue,
            lease,
            GitHubTreeGateway(_CONFIG.repository, _CONFIG.branch),
            _CONFIG,
        )


def test_protected_publication_config_fails_closed_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fanout_module,
        "_load_protected_publication_config_sha256",
        _PROTECTED_CONFIG_LOADER,
    )

    def unavailable(*_args: object, **_kwargs: object) -> int:
        raise PermissionError("synthetic denial")

    monkeypatch.setattr(fanout_module.os, "open", unavailable)

    with pytest.raises(PublisherConflictError, match="unavailable"):
        fanout_module._load_protected_publication_config_sha256()


def test_protected_publication_config_rejects_rotation_during_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fanout_module,
        "_load_protected_publication_config_sha256",
        _PROTECTED_CONFIG_LOADER,
    )
    payload = (
        json.dumps(
            {
                "publication_config_sha256": _CONFIG.sha256,
                "revision": "phase4-v2-publication-config-pin-v1",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )
    directory_metadata = SimpleNamespace(
        st_dev=1,
        st_ino=10,
        st_mode=stat.S_IFDIR | 0o755,
        st_nlink=2,
        st_uid=0,
        st_gid=0,
        st_size=4096,
        st_mtime_ns=1,
        st_ctime_ns=1,
    )
    file_metadata = SimpleNamespace(
        st_dev=1,
        st_ino=11,
        st_mode=stat.S_IFREG | 0o600,
        st_nlink=1,
        st_uid=0,
        st_gid=0,
        st_size=len(payload),
        st_mtime_ns=1,
        st_ctime_ns=1,
    )
    rotated_metadata = SimpleNamespace(**vars(file_metadata))
    rotated_metadata.st_ino = 12
    fstat_calls = 0
    read_calls = 0

    def fake_open(path: str, _flags: int, *, dir_fd: int | None = None) -> int:
        if path == "/etc/ha-adjustable-bed" and dir_fd is None:
            return 10
        if path == "phase4-v2-publication-config.pin.json" and dir_fd == 10:
            return 11
        raise AssertionError(f"unexpected protected-config open: {path!r}")

    def fake_fstat(descriptor: int) -> object:
        nonlocal fstat_calls
        if descriptor == 10:
            return directory_metadata
        if descriptor == 11:
            fstat_calls += 1
            return file_metadata if fstat_calls == 1 else rotated_metadata
        raise AssertionError(f"unexpected protected-config descriptor: {descriptor}")

    def fake_read(descriptor: int, _count: int) -> bytes:
        nonlocal read_calls
        assert descriptor == 11
        read_calls += 1
        return payload if read_calls == 1 else b""

    monkeypatch.setattr(fanout_module.os, "open", fake_open)
    monkeypatch.setattr(fanout_module.os, "fstat", fake_fstat)
    monkeypatch.setattr(fanout_module.os, "read", fake_read)
    monkeypatch.setattr(fanout_module.os, "close", lambda _descriptor: None)

    with pytest.raises(PublisherConflictError, match="changed while reading"):
        fanout_module._load_protected_publication_config_sha256()


def test_document_set_duplicate_path_with_different_presence_fails_closed() -> None:
    with pytest.raises(ValueError, match="unique"):
        TrackerDocumentSet(
            _REVISION,
            (TrackerDocument("queue.md", None), TrackerDocument("queue.md", b"")),
        )


def test_fanout_receipt_cannot_be_constructed_from_caller_values() -> None:
    with pytest.raises(ValueError, match="atomic publisher"):
        FanoutPublishReceipt()


def test_generic_internal_checkpoint_cannot_forge_publication(
    publisher: tuple[Queue, Lease],
) -> None:
    queue, lease = publisher

    with pytest.raises(QueueConflictError, match="atomic publisher grant"):
        queue._checkpoint_internal(
            lease,
            "TRACKER_PUBLISHED",
            {
                "document_set_sha256": "d" * 64,
                "generation": "e" * 64,
                "revision": _NEXT_REVISION,
                "targets": ["issues/436.md"],
            },
        )


def test_fanout_bounds_targets_before_rendering(publisher: tuple[Queue, Lease]) -> None:
    queue, lease = publisher
    targets = tuple(
        TrackerTarget(f"issues/{index:03d}.md", TrackerFormat.MARKDOWN) for index in range(33)
    )

    with pytest.raises(ValueError, match="non-empty bounded exact tuple"):
        TrackerPublicationConfig(_CONFIG.repository, _CONFIG.branch, targets)
    with pytest.raises(ValueError, match="canonical"):
        TrackerTarget("issues/", TrackerFormat.MARKDOWN)
