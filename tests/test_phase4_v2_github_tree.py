from __future__ import annotations

import base64
import hashlib
import json

import pytest

from tools.phase4_v2.queue import (
    CommandResult,
    GitHubContentsError,
    GitHubTreeGateway,
    GitHubTreePostWriteUnknownError,
    TrackerDocument,
    document_set_sha256,
)

_REF = "a" * 40
_OTHER_REF = "b" * 40
_BASE_TREE = "c" * 40
_NEW_TREE = "d" * 40
_NEW_COMMIT = "e" * 40


class _GitDataRunner:
    def __init__(self) -> None:
        self.ref = _REF
        self.documents: dict[str, bytes] = {"issues/436.md": b"old\n"}
        self.blobs: dict[str, bytes] = {}
        self.pending_entries: list[dict[str, str]] = []
        self.calls: list[tuple[tuple[str, ...], bytes | None]] = []
        self.conflict = False
        self.uncertain_apply = False
        self.allow_force_pushes = False

    def __call__(
        self, arguments: tuple[str, ...], payload: bytes | None, _timeout: int
    ) -> CommandResult:
        self.calls.append((arguments, payload))
        method = arguments[3]
        endpoint = arguments[4]
        if method == "GET" and "/git/ref/" in endpoint:
            return self._ok({"object": {"sha": self.ref, "type": "commit"}})
        if method == "GET" and "/branches/" in endpoint and endpoint.endswith("/protection"):
            return self._ok(
                {
                    "allow_deletions": {"enabled": False},
                    "allow_force_pushes": {"enabled": self.allow_force_pushes},
                }
            )
        if method == "GET" and "/contents/" in endpoint:
            path = endpoint.split("/contents/", 1)[1].replace("%20", " ")
            body = self.documents.get(path)
            if body is None:
                return CommandResult(1, b"", b"gh: Not Found (HTTP 404)")
            return self._ok(
                {
                    "content": base64.b64encode(body).decode(),
                    "encoding": "base64",
                    "sha": "f" * 40,
                    "type": "file",
                }
            )
        if method == "GET" and "/git/commits/" in endpoint:
            return self._ok({"tree": {"sha": _BASE_TREE}})
        assert payload is not None
        body = json.loads(payload)
        if method == "POST" and endpoint.endswith("/git/blobs"):
            blob_id = f"{len(self.blobs) + 1:040x}"
            self.blobs[blob_id] = base64.b64decode(body["content"])
            return self._ok({"sha": blob_id})
        if method == "POST" and endpoint.endswith("/git/trees"):
            assert body["base_tree"] == _BASE_TREE
            self.pending_entries = body["tree"]
            return self._ok({"sha": _NEW_TREE})
        if method == "POST" and endpoint.endswith("/git/commits"):
            assert body["parents"] == [_REF]
            assert body["tree"] == _NEW_TREE
            return self._ok({"sha": _NEW_COMMIT})
        if method == "PATCH" and "/git/refs/heads/" in endpoint:
            assert body == {"force": False, "sha": _NEW_COMMIT}
            if self.conflict:
                self.ref = _OTHER_REF
                return CommandResult(1, b"", b"gh: conflict (HTTP 422)")
            self.ref = _NEW_COMMIT
            for entry in self.pending_entries:
                self.documents[entry["path"]] = self.blobs[entry["sha"]]
            if self.uncertain_apply:
                raise GitHubContentsError("synthetic timeout")
            return self._ok({"object": {"sha": _NEW_COMMIT, "type": "commit"}})
        raise AssertionError((method, endpoint))

    @staticmethod
    def _ok(value: object) -> CommandResult:
        return CommandResult(0, json.dumps(value).encode(), b"")


def _gateway(runner: _GitDataRunner) -> GitHubTreeGateway:
    return GitHubTreeGateway("owner/repo", "phase4/trackers", runner=runner)


def test_tree_gateway_publishes_all_documents_in_one_ref_update() -> None:
    runner = _GitDataRunner()
    gateway = _gateway(runner)
    paths = ("issues/436.md", "public/queue.html")
    before = gateway.read(paths)
    desired = (
        TrackerDocument("issues/436.md", b"new\n"),
        TrackerDocument("public/queue.html", b"<html></html>\n"),
    )

    assert gateway.compare_and_replace(
        expected_revision=before.revision,
        expected_documents_sha256=document_set_sha256(before.documents),
        documents=desired,
    )

    assert gateway.read(paths).documents == desired
    patches = [call for call in runner.calls if call[0][3] == "PATCH"]
    assert len(patches) == 1
    commit_payload = next(
        json.loads(payload)
        for arguments, payload in runner.calls
        if arguments[3] == "POST" and arguments[4].endswith("/git/commits")
    )
    assert commit_payload["parents"] == [_REF]


def test_tree_gateway_detects_ref_race_without_partial_visibility() -> None:
    runner = _GitDataRunner()
    runner.conflict = True
    gateway = _gateway(runner)
    before = gateway.read(("issues/436.md",))

    assert not gateway.compare_and_replace(
        expected_revision=before.revision,
        expected_documents_sha256=document_set_sha256(before.documents),
        documents=(TrackerDocument("issues/436.md", b"new\n"),),
    )
    assert runner.documents["issues/436.md"] == b"old\n"


def test_tree_gateway_rejects_stale_document_preimage_before_writes() -> None:
    runner = _GitDataRunner()
    gateway = _gateway(runner)

    assert not gateway.compare_and_replace(
        expected_revision=_REF,
        expected_documents_sha256=hashlib.sha256(b"wrong").hexdigest(),
        documents=(TrackerDocument("issues/436.md", b"new\n"),),
    )
    assert not any(arguments[3] == "POST" for arguments, _payload in runner.calls)


def test_tree_gateway_reads_missing_files_from_a_pinned_ref() -> None:
    runner = _GitDataRunner()
    gateway = _gateway(runner)

    result = gateway.read(("issues/443.md",))

    assert result.documents == (TrackerDocument("issues/443.md", None),)
    content_read = next(arguments for arguments, _ in runner.calls if "/contents/" in arguments[4])
    assert f"ref={_REF}" in content_read


def test_tree_gateway_rejects_invalid_or_ambiguous_api_receipts() -> None:
    class InvalidRunner:
        def __call__(
            self, _arguments: tuple[str, ...], _payload: bytes | None, _timeout: int
        ) -> CommandResult:
            return CommandResult(
                0,
                b'{"object":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
                b'"sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","type":"commit"}}',
                b"",
            )

    gateway = GitHubTreeGateway("owner/repo", "trackers", runner=InvalidRunner())

    with pytest.raises(GitHubContentsError, match="invalid JSON"):
        gateway.read(("queue.md",))


def test_tree_gateway_reconciles_success_after_uncertain_ref_transport() -> None:
    runner = _GitDataRunner()
    runner.uncertain_apply = True
    gateway = _gateway(runner)
    before = gateway.read(("issues/436.md",))
    desired = (TrackerDocument("issues/436.md", b"new\n"),)

    assert gateway.compare_and_replace(
        expected_revision=before.revision,
        expected_documents_sha256=document_set_sha256(before.documents),
        documents=desired,
    )


def test_tree_gateway_refuses_unprotected_force_pushes() -> None:
    runner = _GitDataRunner()
    runner.allow_force_pushes = True
    gateway = _gateway(runner)
    before = gateway.read(("issues/436.md",))

    with pytest.raises(GitHubContentsError, match="forbid force pushes"):
        gateway.compare_and_replace(
            expected_revision=before.revision,
            expected_documents_sha256=document_set_sha256(before.documents),
            documents=(TrackerDocument("issues/436.md", b"new\n"),),
        )
    assert not runner.blobs


def test_tree_gateway_bounds_total_decoded_readback() -> None:
    runner = _GitDataRunner()
    paths = tuple(f"issues/{index:03d}.md" for index in range(5))
    runner.documents = dict.fromkeys(paths, b"x" * (900 * 1024))

    with pytest.raises(GitHubContentsError, match="document set exceeds"):
        _gateway(runner).read(paths)


def test_tree_gateway_reports_unresolved_uncertain_write() -> None:
    class UnknownRunner(_GitDataRunner):
        patch_attempted = False

        def __call__(
            self, arguments: tuple[str, ...], payload: bytes | None, timeout: int
        ) -> CommandResult:
            if arguments[3] == "PATCH":
                self.patch_attempted = True
                raise GitHubContentsError("synthetic timeout")
            if self.patch_attempted and arguments[3] == "GET":
                raise GitHubContentsError("synthetic readback failure")
            return super().__call__(arguments, payload, timeout)

    runner = UnknownRunner()
    gateway = _gateway(runner)
    before = gateway.read(("issues/436.md",))

    with pytest.raises(GitHubTreePostWriteUnknownError, match="unknown"):
        gateway.compare_and_replace(
            expected_revision=before.revision,
            expected_documents_sha256=document_set_sha256(before.documents),
            documents=(TrackerDocument("issues/436.md", b"new\n"),),
        )
