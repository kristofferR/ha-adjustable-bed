"""Atomic multi-file tracker publication through one GitHub commit."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
from collections.abc import Callable
from urllib.parse import quote

from .fanout import TrackerDocument, TrackerDocumentSet, document_set_sha256
from .github_contents import CommandResult, GitHubContentsError, GitHubContentsTarget

_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_REQUEST_BYTES = 12 * 1024 * 1024
_MAX_DOCUMENT_SET_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 10_000
_TIMEOUT_SECONDS = 60

type TreeCommandRunner = Callable[[tuple[str, ...], bytes | None, int], CommandResult]


class GitHubTreePostWriteUnknownError(GitHubContentsError):
    """A failed ref transport may have made the commit visible."""


class GitHubTreeGateway:
    """Compare-and-swap a complete tracker set at one Git branch ref."""

    def __init__(
        self,
        repository: str,
        branch: str,
        *,
        runner: TreeCommandRunner | None = None,
    ) -> None:
        validated = GitHubContentsTarget(repository, branch, "tracker")
        self._repository = validated.repository
        self._branch = validated.branch
        self._runner = runner or _run_gh

    def read(self, paths: tuple[str, ...]) -> TrackerDocumentSet:
        """Read all requested files from one immutable commit revision."""

        canonical_paths = _paths(paths)
        revision = self._read_ref()
        documents: list[TrackerDocument] = []
        total_bytes = 0
        for path in canonical_paths:
            result = self._call(
                (
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    f"repos/{self._repository}/contents/{quote(path, safe='/')}",
                    "-f",
                    f"ref={revision}",
                )
            )
            if result.returncode != 0:
                if _is_not_found(result.stderr):
                    documents.append(TrackerDocument(path, None))
                    continue
                raise GitHubContentsError(_error("read tracker file", result.stderr))
            response = _object(result.stdout)
            content = response.get("content")
            blob_id = response.get("sha")
            if (
                response.get("type") != "file"
                or response.get("encoding") != "base64"
                or type(content) is not str
                or type(blob_id) is not str
                or _OBJECT_ID.fullmatch(blob_id) is None
            ):
                raise GitHubContentsError("GitHub returned invalid tracker file content")
            try:
                body = base64.b64decode("".join(content.split()), validate=True)
            except binascii.Error as error:
                raise GitHubContentsError("GitHub returned invalid tracker file base64") from error
            total_bytes += len(body)
            if total_bytes > _MAX_DOCUMENT_SET_BYTES:
                raise GitHubContentsError("GitHub tracker document set exceeds its byte limit")
            documents.append(TrackerDocument(path, body))
        return TrackerDocumentSet(revision, tuple(documents))

    def compare_and_replace(
        self,
        *,
        expected_revision: str,
        expected_documents_sha256: str,
        documents: tuple[TrackerDocument, ...],
    ) -> bool:
        """Commit all files, then fast-forward the branch only from the expected tip."""

        if type(expected_revision) is not str or _OBJECT_ID.fullmatch(expected_revision) is None:
            raise ValueError("expected GitHub ref revision is invalid")
        if (
            type(expected_documents_sha256) is not str
            or _DIGEST.fullmatch(expected_documents_sha256) is None
        ):
            raise ValueError("expected document-set digest is invalid")
        TrackerDocumentSet(expected_revision, documents)
        paths = tuple(item.path for item in documents)
        canonical_paths = _paths(paths)
        if paths != canonical_paths or any(item.body is None for item in documents):
            raise ValueError("replacement documents must be sorted, unique, and present")
        current = self.read(paths)
        if (
            current.revision != expected_revision
            or document_set_sha256(current.documents) != expected_documents_sha256
        ):
            return False
        self._require_protected_branch()

        commit = self._get(
            f"repos/{self._repository}/git/commits/{expected_revision}",
            "read base commit",
        )
        tree = commit.get("tree")
        if type(tree) is not dict:
            raise GitHubContentsError("GitHub returned an invalid base commit")
        base_tree = _object_id(tree.get("sha"), "base tree")

        entries: list[dict[str, str]] = []
        for document in documents:
            body = document.body
            if body is None:
                raise ValueError("replacement documents must be present")
            blob = self._write(
                "POST",
                f"repos/{self._repository}/git/blobs",
                {"content": base64.b64encode(body).decode(), "encoding": "base64"},
                "create tracker blob",
            )
            entries.append(
                {
                    "mode": "100644",
                    "path": document.path,
                    "sha": _object_id(blob.get("sha"), "blob"),
                    "type": "blob",
                }
            )
        new_tree = self._write(
            "POST",
            f"repos/{self._repository}/git/trees",
            {"base_tree": base_tree, "tree": entries},
            "create tracker tree",
        )
        tree_id = _object_id(new_tree.get("sha"), "created tree")
        new_commit = self._write(
            "POST",
            f"repos/{self._repository}/git/commits",
            {
                "message": "chore(trackers): update Phase 4 queue",
                "parents": [expected_revision],
                "tree": tree_id,
            },
            "create tracker commit",
        )
        commit_id = _object_id(new_commit.get("sha"), "created commit")
        try:
            result = self._call_json(
                "PATCH",
                f"repos/{self._repository}/git/refs/heads/{quote(self._branch, safe='/')}",
                {"force": False, "sha": commit_id},
            )
        except GitHubContentsError as error:
            return self._resolve_uncertain_write(paths, documents, commit_id, error)
        if result.returncode != 0:
            current_revision = self._read_ref()
            if current_revision == commit_id:
                return True
            if current_revision != expected_revision:
                return self.read(paths).documents == documents
            raise GitHubContentsError(_error("update tracker ref", result.stderr))
        response = _object(result.stdout)
        target = response.get("object")
        if (
            type(target) is not dict
            or target.get("type") != "commit"
            or _object_id(target.get("sha"), "updated ref") != commit_id
        ):
            raise GitHubContentsError("GitHub returned an invalid tracker ref receipt")
        return True

    def _require_protected_branch(self) -> None:
        response = self._get(
            f"repos/{self._repository}/branches/{quote(self._branch, safe='')}/protection",
            "read tracker branch protection",
        )
        force_pushes = response.get("allow_force_pushes")
        deletions = response.get("allow_deletions")
        if (
            type(force_pushes) is not dict
            or force_pushes.get("enabled") is not False
            or type(deletions) is not dict
            or deletions.get("enabled") is not False
        ):
            raise GitHubContentsError("tracker branch must forbid force pushes and deletions")

    def _resolve_uncertain_write(
        self,
        paths: tuple[str, ...],
        documents: tuple[TrackerDocument, ...],
        commit_id: str,
        error: GitHubContentsError,
    ) -> bool:
        try:
            after = self.read(paths)
        except GitHubContentsError as read_error:
            raise GitHubTreePostWriteUnknownError(
                "GitHub tracker ref update and readback outcomes are unknown"
            ) from read_error
        if after.revision == commit_id or after.documents == documents:
            return True
        raise GitHubTreePostWriteUnknownError(
            "GitHub tracker ref update outcome is unknown"
        ) from error

    def _read_ref(self) -> str:
        response = self._get(
            f"repos/{self._repository}/git/ref/heads/{quote(self._branch, safe='/')}",
            "read tracker ref",
        )
        target = response.get("object")
        if type(target) is not dict or target.get("type") != "commit":
            raise GitHubContentsError("GitHub tracker ref is not a commit")
        return _object_id(target.get("sha"), "tracker ref")

    def _get(self, endpoint: str, operation: str) -> dict[str, object]:
        result = self._call(("gh", "api", "--method", "GET", endpoint))
        if result.returncode != 0:
            raise GitHubContentsError(_error(operation, result.stderr))
        return _object(result.stdout)

    def _write(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, object],
        operation: str,
    ) -> dict[str, object]:
        result = self._call_json(method, endpoint, payload)
        if result.returncode != 0:
            raise GitHubContentsError(_error(operation, result.stderr))
        return _object(result.stdout)

    def _call_json(self, method: str, endpoint: str, payload: dict[str, object]) -> CommandResult:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if len(body) > _MAX_REQUEST_BYTES:
            raise GitHubContentsError("GitHub tracker request exceeds its byte limit")
        return self._call(("gh", "api", "--method", method, endpoint, "--input", "-"), body)

    def _call(self, arguments: tuple[str, ...], payload: bytes | None = None) -> CommandResult:
        result = self._runner(arguments, payload, _TIMEOUT_SECONDS)
        if type(result) is not CommandResult:
            raise GitHubContentsError("GitHub tree command runner returned an invalid result")
        return result


def _run_gh(
    arguments: tuple[str, ...], payload: bytes | None, timeout_seconds: int
) -> CommandResult:
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
            input=payload,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitHubContentsError("GitHub CLI could not complete the tracker operation") from error
    if len(completed.stdout) > _MAX_RESPONSE_BYTES or len(completed.stderr) > _MAX_RESPONSE_BYTES:
        raise GitHubContentsError("GitHub CLI response exceeds the configured limit")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    if (
        type(paths) is not tuple
        or not paths
        or len(paths) > 32
        or any(type(path) is not str for path in paths)
    ):
        raise ValueError("tracker paths must be a non-empty bounded exact tuple")
    for path in paths:
        TrackerDocument(path, None)
    if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
        raise ValueError("tracker paths must be sorted and unique")
    return paths


def _object(payload: bytes) -> dict[str, object]:
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


def _object_id(value: object, label: str) -> str:
    if type(value) is not str or _OBJECT_ID.fullmatch(value) is None:
        raise GitHubContentsError(f"GitHub returned an invalid {label} object ID")
    return value


def _is_not_found(stderr: bytes) -> bool:
    lowered = stderr.lower()
    return b"http 404" in lowered or b'"status":"404"' in lowered


def _error(operation: str, stderr: bytes) -> str:
    details = stderr.decode(errors="replace").strip().splitlines()
    suffix = f": {details[-1][:300]}" if details else ""
    return f"GitHub tracker {operation} failed{suffix}"
