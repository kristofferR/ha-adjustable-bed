"""Atomic tracker documents backed by GitHub's contents API."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote

from .publisher import IssueDocument
from .tracker import GITHUB_ISSUE_BODY_MAX_CHARS

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_MISSING_REVISION = "missing"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 10_000
_TIMEOUT_SECONDS = 60


class GitHubContentsError(RuntimeError):
    """GitHub could not safely read or update a tracker document."""


class GitHubContentsPostWriteUnknownError(GitHubContentsError):
    """A failed transport may have applied the requested write."""


@dataclass(frozen=True, slots=True)
class GitHubContentsTarget:
    """One issue-keyed file on a dedicated tracker branch."""

    repository: str
    branch: str
    path: str

    def __post_init__(self) -> None:
        if type(self.repository) is not str or _REPOSITORY.fullmatch(self.repository) is None:
            raise ValueError("repository must be an owner/name pair")
        if (
            type(self.branch) is not str
            or not self.branch
            or len(self.branch) > 255
            or self.branch.startswith("-")
            or self.branch.endswith((".", "/"))
            or ".." in self.branch
            or "//" in self.branch
            or "@{" in self.branch
            or any(character in " ~^:?*[\\" for character in self.branch)
            or any(part.endswith(".lock") for part in self.branch.split("/"))
            or any(ord(character) < 32 or ord(character) == 127 for character in self.branch)
        ):
            raise ValueError("tracker branch is invalid")
        if type(self.path) is not str:
            raise ValueError("tracker path must be canonical and relative")
        candidate = PurePosixPath(self.path)
        if (
            not self.path
            or len(self.path) > 4_096
            or candidate.is_absolute()
            or candidate.as_posix() != self.path
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise ValueError("tracker path must be canonical and relative")


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes

    def __post_init__(self) -> None:
        if type(self.returncode) is not int:
            raise ValueError("command return code must be an integer")
        if type(self.stdout) is not bytes or type(self.stderr) is not bytes:
            raise ValueError("command output must be exact bytes")
        if len(self.stdout) > _MAX_RESPONSE_BYTES or len(self.stderr) > _MAX_RESPONSE_BYTES:
            raise ValueError("command output exceeds the configured limit")


type CommandRunner = Callable[[tuple[str, ...], int], CommandResult]


class GitHubContentsGateway:
    """Implement publisher CAS using GitHub content blob revisions."""

    def __init__(
        self,
        targets: Mapping[int, GitHubContentsTarget],
        *,
        runner: CommandRunner | None = None,
    ) -> None:
        if type(targets) is not dict or not targets:
            raise ValueError("GitHub contents targets must be a non-empty exact dict")
        copied: dict[int, GitHubContentsTarget] = {}
        for issue_number, target in targets.items():
            if type(issue_number) is not int or issue_number < 1:
                raise ValueError("tracker target keys must be positive issue numbers")
            if type(target) is not GitHubContentsTarget:
                raise ValueError("tracker targets must be exact GitHubContentsTarget values")
            copied[issue_number] = target
        self._targets = copied
        self._runner = runner or _run_gh

    def read(self, issue_number: int) -> IssueDocument:
        """Read one exact UTF-8 tracker file and its blob SHA."""

        target = self._target(issue_number)
        result = self._call(
            (
                "gh",
                "api",
                "--method",
                "GET",
                f"repos/{target.repository}/contents/{quote(target.path, safe='/')}",
                "-f",
                f"ref={target.branch}",
            ),
            _TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            if _is_not_found(result.stderr):
                return IssueDocument("", _MISSING_REVISION)
            raise GitHubContentsError(_error_message("read", result.stderr))
        response = _response_object(result.stdout)
        content = response.get("content")
        encoding = response.get("encoding")
        revision = response.get("sha")
        if (
            type(content) is not str
            or encoding != "base64"
            or type(revision) is not str
            or _REVISION.fullmatch(revision) is None
        ):
            raise GitHubContentsError("GitHub returned an invalid tracker document")
        try:
            decoded = base64.b64decode("".join(content.split()), validate=True)
            body = decoded.decode()
        except (binascii.Error, UnicodeDecodeError) as error:
            raise GitHubContentsError("GitHub tracker content is not canonical UTF-8") from error
        if len(body) > GITHUB_ISSUE_BODY_MAX_CHARS:
            raise GitHubContentsError("GitHub tracker content exceeds the configured limit")
        return IssueDocument(body, revision)

    def compare_and_replace(
        self,
        issue_number: int,
        *,
        expected_revision: str,
        expected_body_sha256: str,
        body: str,
    ) -> bool:
        """Atomically replace a file only while its exact blob SHA is current."""

        if type(body) is not str or len(body) > GITHUB_ISSUE_BODY_MAX_CHARS:
            raise ValueError("tracker body must be a bounded string")
        if not _digest(expected_body_sha256):
            raise ValueError("expected body digest must be a lowercase SHA-256")
        if (
            expected_revision != _MISSING_REVISION
            and _REVISION.fullmatch(expected_revision) is None
        ):
            raise ValueError("expected tracker revision is invalid")
        current = self.read(issue_number)
        if (
            current.revision != expected_revision
            or hashlib.sha256(current.body.encode()).hexdigest() != expected_body_sha256
        ):
            return False
        target = self._target(issue_number)
        arguments = [
            "gh",
            "api",
            "--method",
            "PUT",
            f"repos/{target.repository}/contents/{quote(target.path, safe='/')}",
            "--raw-field",
            "message=chore(trackers): update Phase 4 queue",
            "--raw-field",
            f"content={base64.b64encode(body.encode()).decode()}",
            "--raw-field",
            f"branch={target.branch}",
        ]
        if expected_revision != _MISSING_REVISION:
            arguments.extend(("--raw-field", f"sha={expected_revision}"))
        try:
            result = self._call(tuple(arguments), _TIMEOUT_SECONDS)
        except GitHubContentsError as error:
            try:
                after_uncertain = self.read(issue_number)
            except GitHubContentsError as read_error:
                raise GitHubContentsPostWriteUnknownError(
                    "GitHub tracker update outcome and readback are unknown"
                ) from read_error
            if after_uncertain.body == body:
                return True
            raise GitHubContentsPostWriteUnknownError(
                "GitHub tracker update outcome is unknown"
            ) from error
        if result.returncode == 0:
            _validate_update_response(result.stdout)
            return True
        after_failure = self.read(issue_number)
        if after_failure.revision != expected_revision:
            return False
        raise GitHubContentsError(_error_message("update", result.stderr))

    def _target(self, issue_number: int) -> GitHubContentsTarget:
        if type(issue_number) is not int:
            raise ValueError("issue number must be an integer")
        try:
            return self._targets[issue_number]
        except KeyError as error:
            raise ValueError(f"no GitHub contents target for issue {issue_number}") from error

    def _call(self, arguments: tuple[str, ...], timeout_seconds: int) -> CommandResult:
        result = self._runner(arguments, timeout_seconds)
        if type(result) is not CommandResult:
            raise GitHubContentsError("GitHub command runner returned an invalid result")
        return result


def _run_gh(arguments: tuple[str, ...], timeout_seconds: int) -> CommandResult:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "GH_CONFIG_DIR",
            "GH_ENTERPRISE_TOKEN",
            "GH_HOST",
            "GH_TOKEN",
            "HOME",
            "NO_COLOR",
            "PATH",
            "XDG_CONFIG_HOME",
        }
    }
    try:
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            env=environment,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitHubContentsError("GitHub CLI could not complete the tracker operation") from error
    if len(completed.stdout) > _MAX_RESPONSE_BYTES or len(completed.stderr) > _MAX_RESPONSE_BYTES:
        raise GitHubContentsError("GitHub CLI response exceeds the configured limit")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _response_object(payload: bytes) -> dict[str, object]:
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise GitHubContentsError("GitHub response exceeds the configured limit")
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise GitHubContentsError("GitHub returned invalid JSON") from error
    if type(value) is not dict:
        raise GitHubContentsError("GitHub returned an invalid response object")
    _bounded_json(value)
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _bounded_json(value: object) -> None:
    nodes = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            raise GitHubContentsError("GitHub JSON response exceeds structural limits")
        if type(current) is dict:
            stack.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in current)


def _validate_update_response(payload: bytes) -> None:
    response = _response_object(payload)
    content = response.get("content")
    commit = response.get("commit")
    if (
        type(content) is not dict
        or type(content.get("sha")) is not str
        or _REVISION.fullmatch(content["sha"]) is None
        or type(commit) is not dict
        or type(commit.get("sha")) is not str
        or _REVISION.fullmatch(commit["sha"]) is None
    ):
        raise GitHubContentsError("GitHub returned an invalid update receipt")


def _is_not_found(stderr: bytes) -> bool:
    lowered = stderr.lower()
    return b"http 404" in lowered or b'"status":"404"' in lowered


def _error_message(operation: str, stderr: bytes) -> str:
    detail = stderr.decode(errors="replace").strip().splitlines()
    suffix = f": {detail[-1][:300]}" if detail else ""
    return f"GitHub tracker {operation} failed{suffix}"


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
