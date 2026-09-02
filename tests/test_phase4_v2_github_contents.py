from __future__ import annotations

import base64
import hashlib
import json

import pytest

from tools.phase4_v2.queue import (
    CommandResult,
    GitHubContentsError,
    GitHubContentsGateway,
    GitHubContentsTarget,
)

_BLOB = "a" * 40
_NEXT_BLOB = "b" * 40
_COMMIT = "c" * 40


class _ContentsRunner:
    def __init__(self, body: str = "manual\n", revision: str = _BLOB) -> None:
        self.body = body
        self.revision = revision
        self.arguments: list[tuple[str, ...]] = []
        self.fail_update = False
        self.move_on_failure = False

    def __call__(self, arguments: tuple[str, ...], _timeout: int) -> CommandResult:
        self.arguments.append(arguments)
        if "GET" in arguments:
            if self.revision == "missing":
                return CommandResult(1, b"", b"gh: Not Found (HTTP 404)")
            return CommandResult(
                0,
                json.dumps(
                    {
                        "content": base64.b64encode(self.body.encode()).decode(),
                        "encoding": "base64",
                        "sha": self.revision,
                    }
                ).encode(),
                b"",
            )
        if self.fail_update:
            if self.move_on_failure:
                self.revision = _NEXT_BLOB
                self.body = "other writer\n"
            return CommandResult(1, b"", b"gh: conflict (HTTP 409)")
        content_argument = next(item for item in arguments if item.startswith("content="))
        self.body = base64.b64decode(content_argument.removeprefix("content=")).decode()
        self.revision = _NEXT_BLOB
        return CommandResult(
            0,
            json.dumps({"commit": {"sha": _COMMIT}, "content": {"sha": self.revision}}).encode(),
            b"",
        )


class _InvalidRunner:
    def __call__(self, _arguments: tuple[str, ...], _timeout: int) -> CommandResult:
        return "invalid"  # type: ignore[return-value]


def _gateway(runner: _ContentsRunner) -> GitHubContentsGateway:
    return GitHubContentsGateway(
        {542: GitHubContentsTarget("owner/repo", "phase4-trackers", "issues/542.md")},
        runner=runner,
    )


def test_contents_gateway_reads_and_cas_updates_exact_blob() -> None:
    runner = _ContentsRunner()
    gateway = _gateway(runner)
    before = gateway.read(542)

    changed = gateway.compare_and_replace(
        542,
        expected_revision=before.revision,
        expected_body_sha256=hashlib.sha256(before.body.encode()).hexdigest(),
        body="updated\n",
    )

    assert changed is True
    assert gateway.read(542).body == "updated\n"
    put = next(arguments for arguments in runner.arguments if "PUT" in arguments)
    assert f"sha={_BLOB}" in put
    assert "--raw-field" in put


def test_contents_gateway_creates_only_while_target_is_missing() -> None:
    runner = _ContentsRunner("", "missing")
    gateway = _gateway(runner)
    assert gateway.read(542).revision == "missing"

    assert gateway.compare_and_replace(
        542,
        expected_revision="missing",
        expected_body_sha256=hashlib.sha256(b"").hexdigest(),
        body="first\n",
    )
    put = next(arguments for arguments in runner.arguments if "PUT" in arguments)
    assert not any(item.startswith("sha=") for item in put)


def test_contents_gateway_rejects_stale_preimage_without_write() -> None:
    runner = _ContentsRunner()
    gateway = _gateway(runner)

    assert not gateway.compare_and_replace(
        542,
        expected_revision=_NEXT_BLOB,
        expected_body_sha256=hashlib.sha256(b"manual\n").hexdigest(),
        body="updated\n",
    )
    assert not any("PUT" in arguments for arguments in runner.arguments)


def test_contents_gateway_reports_server_side_cas_conflict() -> None:
    runner = _ContentsRunner()
    runner.fail_update = True
    runner.move_on_failure = True
    gateway = _gateway(runner)

    assert not gateway.compare_and_replace(
        542,
        expected_revision=_BLOB,
        expected_body_sha256=hashlib.sha256(b"manual\n").hexdigest(),
        body="updated\n",
    )


def test_contents_gateway_does_not_hide_non_conflict_api_failure() -> None:
    runner = _ContentsRunner()
    runner.fail_update = True
    gateway = _gateway(runner)

    with pytest.raises(GitHubContentsError, match="update failed"):
        gateway.compare_and_replace(
            542,
            expected_revision=_BLOB,
            expected_body_sha256=hashlib.sha256(b"manual\n").hexdigest(),
            body="updated\n",
        )


def test_contents_target_is_immutable_and_canonical() -> None:
    target = GitHubContentsTarget("owner/repo", "trackers", "issues/542.md")
    assert target.path == "issues/542.md"

    with pytest.raises(ValueError, match="canonical"):
        GitHubContentsTarget("owner/repo", "trackers", "../542.md")
    with pytest.raises(ValueError, match="branch"):
        GitHubContentsTarget("owner/repo", "bad..branch", "542.md")


def test_contents_gateway_accepts_github_wrapped_base64() -> None:
    runner = _ContentsRunner("x" * 100)

    original = runner.__call__

    def wrapped(arguments: tuple[str, ...], timeout: int) -> CommandResult:
        result = original(arguments, timeout)
        if "GET" not in arguments or result.returncode:
            return result
        payload = json.loads(result.stdout)
        payload["content"] = "\n".join(
            payload["content"][index : index + 20]
            for index in range(0, len(payload["content"]), 20)
        )
        return CommandResult(0, json.dumps(payload).encode(), b"")

    gateway = GitHubContentsGateway(
        {542: GitHubContentsTarget("owner/repo", "trackers", "issue plans/542.md")},
        runner=wrapped,
    )

    assert gateway.read(542).body == "x" * 100
    assert "%20" in runner.arguments[-1][4]


def test_contents_gateway_rejects_invalid_runner_result() -> None:
    gateway = GitHubContentsGateway(
        {542: GitHubContentsTarget("owner/repo", "trackers", "542.md")},
        runner=_InvalidRunner(),
    )

    with pytest.raises(GitHubContentsError, match="invalid result"):
        gateway.read(542)


def test_contents_gateway_rejects_ambiguous_json_response() -> None:
    class DuplicateKeyRunner:
        def __call__(self, _arguments: tuple[str, ...], _timeout: int) -> CommandResult:
            return CommandResult(
                0,
                b'{"content":"bWFudWFsXG4=","content":"b3RoZXJcbiIs'
                b'"encoding":"base64","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
                b"",
            )

    gateway = GitHubContentsGateway(
        {542: GitHubContentsTarget("owner/repo", "trackers", "542.md")},
        runner=DuplicateKeyRunner(),
    )

    with pytest.raises(GitHubContentsError, match="invalid JSON"):
        gateway.read(542)
