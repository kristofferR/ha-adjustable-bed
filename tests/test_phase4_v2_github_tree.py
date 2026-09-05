from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import tools.phase4_v2.queue.github_tree as github_tree
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


def test_transport_ignores_host_config_and_path_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GH_HOST", "GH_CONFIG_DIR", "HOME", "XDG_CONFIG_HOME", "PATH", "HTTPS_PROXY"):
        monkeypatch.setenv(name, "untrusted-override")
    monkeypatch.setenv("GH_TOKEN", "synthetic-token")
    real_popen = subprocess.Popen
    calls = []

    def launch(arguments, **kwargs):
        calls.append((arguments, kwargs))
        # Exercise the real pipe collector without making a network request.
        return real_popen((sys.executable, "-c", "print('ok')"), **kwargs)

    with patch.object(github_tree.subprocess, "Popen", side_effect=launch):
        result = github_tree._run_gh(("gh", "api", "--method", "GET", "user"), None, 5)
    arguments, kwargs = calls[0]
    assert arguments[0].startswith("/proc/self/fd/")
    assert arguments[1:4] == ("api", "--hostname", "github.com")
    assert set(kwargs["env"]) == {"GH_TOKEN", "GH_PROMPT_DISABLED", "GH_CONFIG_DIR"}
    assert kwargs["env"]["GH_CONFIG_DIR"] != "untrusted-override"
    assert not Path(kwargs["env"]["GH_CONFIG_DIR"]).exists()
    assert result.stdout == b"ok\n"


def test_transport_stops_oversized_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_tree, "_MAX_RESPONSE_BYTES", 128)
    with subprocess.Popen(
        (sys.executable, "-c", "import os,time; os.write(1,b'x'*4096); time.sleep(30)"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as process:
        try:
            with pytest.raises(GitHubContentsError, match="exceeds"):
                github_tree._read_bounded_process(process, 5)
        finally:
            process.kill()
            process.wait()


def test_transport_requires_explicit_deployment_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(GitHubContentsError, match="deployment GH_TOKEN"):
        github_tree._run_gh(("gh", "api", "--method", "GET", "user"), None, 5)


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


def _gateway(
    monkeypatch: pytest.MonkeyPatch, runner: _GitDataRunner
) -> GitHubTreeGateway:
    monkeypatch.setattr(github_tree, "_run_gh", runner)
    return GitHubTreeGateway("owner/repo", "phase4/trackers")


def test_tree_gateway_has_no_caller_supplied_transport() -> None:
    with pytest.raises(TypeError, match="runner"):
        GitHubTreeGateway(
            "owner/repo",
            "phase4/trackers",
            runner=_GitDataRunner(),  # type: ignore[call-arg]
        )

    gateway = GitHubTreeGateway("owner/repo", "phase4/trackers")
    with pytest.raises(AttributeError):
        gateway._runner = _GitDataRunner()  # type: ignore[attr-defined]


def test_tree_gateway_publishes_all_documents_in_one_ref_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    gateway = _gateway(monkeypatch, runner)
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


def test_tree_gateway_detects_ref_race_without_partial_visibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    runner.conflict = True
    gateway = _gateway(monkeypatch, runner)
    before = gateway.read(("issues/436.md",))

    assert not gateway.compare_and_replace(
        expected_revision=before.revision,
        expected_documents_sha256=document_set_sha256(before.documents),
        documents=(TrackerDocument("issues/436.md", b"new\n"),),
    )
    assert runner.documents["issues/436.md"] == b"old\n"


def test_tree_gateway_rejects_stale_document_preimage_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    gateway = _gateway(monkeypatch, runner)

    assert not gateway.compare_and_replace(
        expected_revision=_REF,
        expected_documents_sha256=hashlib.sha256(b"wrong").hexdigest(),
        documents=(TrackerDocument("issues/436.md", b"new\n"),),
    )
    assert not any(arguments[3] == "POST" for arguments, _payload in runner.calls)


def test_tree_gateway_reads_missing_files_from_a_pinned_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    gateway = _gateway(monkeypatch, runner)

    result = gateway.read(("issues/443.md",))

    assert result.documents == (TrackerDocument("issues/443.md", None),)
    content_read = next(arguments for arguments, _ in runner.calls if "/contents/" in arguments[4])
    assert f"ref={_REF}" in content_read


def test_tree_gateway_rejects_invalid_or_ambiguous_api_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr(github_tree, "_run_gh", InvalidRunner())
    gateway = GitHubTreeGateway("owner/repo", "trackers")

    with pytest.raises(GitHubContentsError, match="invalid JSON"):
        gateway.read(("queue.md",))


def test_tree_gateway_reconciles_success_after_uncertain_ref_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    runner.uncertain_apply = True
    gateway = _gateway(monkeypatch, runner)
    before = gateway.read(("issues/436.md",))
    desired = (TrackerDocument("issues/436.md", b"new\n"),)

    assert gateway.compare_and_replace(
        expected_revision=before.revision,
        expected_documents_sha256=document_set_sha256(before.documents),
        documents=desired,
    )


def test_tree_gateway_refuses_unprotected_force_pushes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    runner.allow_force_pushes = True
    gateway = _gateway(monkeypatch, runner)
    before = gateway.read(("issues/436.md",))

    with pytest.raises(GitHubContentsError, match="forbid force pushes"):
        gateway.compare_and_replace(
            expected_revision=before.revision,
            expected_documents_sha256=document_set_sha256(before.documents),
            documents=(TrackerDocument("issues/436.md", b"new\n"),),
        )
    assert not runner.blobs


def test_tree_gateway_bounds_total_decoded_readback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _GitDataRunner()
    paths = tuple(f"issues/{index:03d}.md" for index in range(5))
    runner.documents = dict.fromkeys(paths, b"x" * (900 * 1024))

    with pytest.raises(GitHubContentsError, match="document set exceeds"):
        _gateway(monkeypatch, runner).read(paths)


def test_tree_gateway_reports_unresolved_uncertain_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    gateway = _gateway(monkeypatch, runner)
    before = gateway.read(("issues/436.md",))

    with pytest.raises(GitHubTreePostWriteUnknownError, match="unknown"):
        gateway.compare_and_replace(
            expected_revision=before.revision,
            expected_documents_sha256=document_set_sha256(before.documents),
            documents=(TrackerDocument("issues/436.md", b"new\n"),),
        )
