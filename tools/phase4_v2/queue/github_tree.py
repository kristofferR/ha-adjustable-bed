"""Atomic multi-file tracker publication through one GitHub commit."""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import selectors
import stat
import subprocess
import tempfile
import time
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

class GitHubTreePostWriteUnknownError(GitHubContentsError):
    """A failed ref transport may have made the commit visible."""


class GitHubTreeGateway:
    """Compare-and-swap a complete tracker set at one Git branch ref."""

    __slots__ = ("_branch", "_repository")

    def __init__(self, repository: str, branch: str) -> None:
        validated = GitHubContentsTarget(repository, branch, "tracker")
        self._repository = validated.repository
        self._branch = validated.branch

    @property
    def repository(self) -> str:
        return self._repository

    @property
    def branch(self) -> str:
        return self._branch

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
        result = _run_gh(arguments, payload, _TIMEOUT_SECONDS)
        if type(result) is not CommandResult:
            raise GitHubContentsError("GitHub tree command runner returned an invalid result")
        return result


def _run_gh(
    arguments: tuple[str, ...], payload: bytes | None, timeout_seconds: int
) -> CommandResult:
    if arguments[:2] != ("gh", "api"):
        raise GitHubContentsError("tracker transport permits only GitHub API operations")
    # Pin the deployment-installed executable, never resolve an analyst's PATH.
    executable_fd = -1
    try:
        executable_fd = os.open("/usr/bin/gh", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        metadata = os.fstat(executable_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
            or not metadata.st_mode & 0o111
            or metadata.st_nlink != 1
        ):
            raise GitHubContentsError("GitHub CLI must be a root-owned protected executable")
        for directory in ("/", "/usr", "/usr/bin"):
            entry = os.stat(directory, follow_symlinks=False)
            if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != 0 or entry.st_mode & 0o022:
                raise GitHubContentsError("GitHub CLI directory is not protected")
        # Config discovery, proxies, alternate hosts, and executable lookup are not inherited.
        # A deployment token is used only for the fixed github.com endpoint.
        environment = {"GH_TOKEN": os.environ.get("GH_TOKEN", ""), "GH_PROMPT_DISABLED": "1"}
        if not environment["GH_TOKEN"]:
            raise GitHubContentsError("tracker publication requires a deployment GH_TOKEN")
        with tempfile.TemporaryDirectory(prefix="phase4-gh-") as config_directory:
            environment["GH_CONFIG_DIR"] = config_directory
            command = (
                f"/proc/self/fd/{executable_fd}", "api", "--hostname", "github.com",
                *arguments[2:],
            )
            with tempfile.TemporaryFile() as input_file:
                input_file.write(payload or b"")
                input_file.seek(0)
                with subprocess.Popen(
                    command, stdin=input_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env=environment, cwd=config_directory, pass_fds=(executable_fd,),
                ) as process:
                    try:
                        result = _read_bounded_process(process, timeout_seconds)
                    except BaseException:
                        process.kill()
                        process.wait()
                        raise
        after = os.fstat(executable_fd)
        if (
            metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mode,
            metadata.st_uid, metadata.st_gid, metadata.st_nlink, metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mode,
            after.st_uid, after.st_gid, after.st_nlink, after.st_mtime_ns, after.st_ctime_ns,
        ):
            raise GitHubContentsError("GitHub CLI changed during publication")
        return result
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitHubContentsError("GitHub CLI could not complete the tracker operation") from error
    finally:
        if executable_fd >= 0:
            os.close(executable_fd)


def _read_bounded_process(process: subprocess.Popen[bytes], timeout_seconds: int) -> CommandResult:
    """Drain both pipes concurrently and stop before retaining an oversized response."""
    assert process.stdout is not None and process.stderr is not None
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    deadline = time.monotonic() + timeout_seconds
    total = 0
    with selectors.DefaultSelector() as selector:
        for stream in streams:
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout_seconds)
            for key, _events in selector.select(remaining):
                chunk = os.read(key.fd, min(65536, _MAX_RESPONSE_BYTES - total + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > _MAX_RESPONSE_BYTES:
                    raise GitHubContentsError("GitHub CLI response exceeds the configured limit")
                stream = process.stdout if key.fd == process.stdout.fileno() else process.stderr
                streams[stream].extend(chunk)
    code = process.wait(timeout=max(0, deadline - time.monotonic()))
    return CommandResult(code, bytes(streams[process.stdout]), bytes(streams[process.stderr]))


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
