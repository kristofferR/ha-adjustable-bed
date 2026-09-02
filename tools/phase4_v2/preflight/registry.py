"""Content-addressed, externally pinned preparation tool registries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Never, cast

from .core import PREFLIGHT_SCHEMA, PREPARATION_ROUTES, PreflightResult
from .execution import (
    CANDIDATE_CONTRACT_REVISION,
    CANDIDATE_CONTRACT_SHA256,
    CANDIDATE_INDEX_SCHEMA,
    CANDIDATE_SIGNAL_IDS,
    EXECUTION_SCHEMA,
    CandidateRecord,
    ExecutionLimits,
    InvocationRecord,
    OutputMember,
    PreparationError,
    StreamDigest,
    ToolRecord,
    ToolSpec,
    WarningRecord,
    execute_preparation,
)

TOOL_REGISTRY_SCHEMA = "phase4-v2-approved-tool-registry-v1"
PREPARATION_RECEIPT_REVISION = "phase4-v2-preparation-receipt-v1"
REQUIRED_PREPARATION_ROUTES = PREPARATION_ROUTES

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_MAX_JSON_BYTES = 256 * 1024**2
_MAX_ITEMS = 1_000_000


def _fail(message: str) -> Never:
    raise PreparationError(message)


def _sha(value: object, field: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256")
    return value


def _token(value: object, field: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        _fail(f"{field} must be a canonical token")
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise PreparationError("registry value is not canonical JSON") from error


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bounded_regular_file(path: Path, maximum: int = _MAX_JSON_BYTES) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        _fail(f"preparation member is not a bounded regular file: {path.name}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        payload = bytearray()
        while chunk := os.read(descriptor, min(1024 * 1024, maximum + 1 - len(payload))):
            payload.extend(chunk)
            if len(payload) > maximum:
                _fail(f"preparation member exceeds its byte limit: {path.name}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        _fail(f"preparation member changed while reading: {path.name}")
    return bytes(payload)


@dataclass(frozen=True, slots=True, order=True)
class ToolQualification:
    """One explicitly approved executable build and version response."""

    binary_sha256: str
    version: str

    def __post_init__(self) -> None:
        _sha(self.binary_sha256, "qualification.binary_sha256")
        if type(self.version) is not str or not self.version or len(self.version) > 16_384:
            _fail("qualification.version must be a bounded non-empty string")
        if any(character in self.version for character in ("\x00", "\r", "\n")):
            _fail("qualification.version must be one line")

    def to_data(self) -> dict[str, str]:
        return {"binary_sha256": self.binary_sha256, "version": self.version}


@dataclass(frozen=True, slots=True)
class OutputSufficiencyContract:
    """Protocol-neutral evidence that a route produced its expected output class."""

    minimum_files: int = 1
    minimum_bytes: int = 1
    required_paths: tuple[str, ...] = ()
    required_suffixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.minimum_files) is not int or not 1 <= self.minimum_files <= _MAX_ITEMS:
            _fail("output contract minimum_files is invalid")
        if type(self.minimum_bytes) is not int or not 1 <= self.minimum_bytes <= 2**63 - 1:
            _fail("output contract minimum_bytes is invalid")
        if type(self.required_paths) is not tuple or type(self.required_suffixes) is not tuple:
            _fail("output contract paths and suffixes must be tuples")
        if len(self.required_paths) > 4_096 or len(self.required_suffixes) > 256:
            _fail("output contract exceeds its item limit")
        if any(type(path) is not str for path in self.required_paths):
            _fail("output contract paths must be strings")
        if self.required_paths != tuple(sorted(set(self.required_paths))):
            _fail("output contract paths must be sorted and unique")
        if self.required_suffixes != tuple(sorted(set(self.required_suffixes))):
            _fail("output contract suffixes must be sorted and unique")
        for path in self.required_paths:
            candidate = PurePosixPath(path)
            if (
                candidate.is_absolute()
                or candidate.as_posix() != path
                or any(part in {"", ".", ".."} for part in candidate.parts)
            ):
                _fail("output contract contains an unsafe path")
        if any(
            type(suffix) is not str
            or not suffix.startswith(".")
            or len(suffix) > 64
            or suffix != suffix.lower()
            for suffix in self.required_suffixes
        ):
            _fail("output contract contains an invalid lowercase suffix")

    def validate_outputs(self, outputs: tuple[OutputMember, ...], route: str) -> None:
        if (
            len(outputs) < self.minimum_files
            or sum(item.bytes for item in outputs) < self.minimum_bytes
        ):
            _fail(f"route {route!r} does not meet its minimum output contract")
        paths = {item.path for item in outputs}
        missing_paths = set(self.required_paths) - paths
        if missing_paths:
            _fail(f"route {route!r} is missing required output paths")
        suffixes = {PurePosixPath(item.path).suffix.lower() for item in outputs}
        if set(self.required_suffixes) - suffixes:
            _fail(f"route {route!r} is missing required output suffixes")

    def to_data(self) -> dict[str, object]:
        return {
            "minimum_bytes": self.minimum_bytes,
            "minimum_files": self.minimum_files,
            "required_paths": list(self.required_paths),
            "required_suffixes": list(self.required_suffixes),
        }


@dataclass(frozen=True, slots=True)
class ApprovedRoute:
    """An exact route invocation, tool qualification, and output contract."""

    route: str
    tool: ToolSpec
    qualifications: tuple[ToolQualification, ...]
    output: OutputSufficiencyContract

    def __post_init__(self) -> None:
        _token(self.route, "route.route")
        if type(self.tool) is not ToolSpec:
            _fail("route.tool must be an exact ToolSpec")
        self.tool.validate()
        if type(self.qualifications) is not tuple or not self.qualifications:
            _fail("route.qualifications must be a non-empty tuple")
        if any(type(item) is not ToolQualification for item in self.qualifications):
            _fail("route contains an invalid tool qualification")
        if self.qualifications != tuple(sorted(set(self.qualifications))):
            _fail("route.qualifications must be sorted and unique")
        for qualification in self.qualifications:
            if type(qualification) is not ToolQualification:
                _fail("route contains an invalid tool qualification")
            qualification.__post_init__()
        if type(self.output) is not OutputSufficiencyContract:
            _fail("route.output must be an exact OutputSufficiencyContract")
        self.output.__post_init__()

    def to_data(self) -> dict[str, object]:
        return {
            "output": self.output.to_data(),
            "qualifications": [item.to_data() for item in self.qualifications],
            "route": self.route,
            "tool": {
                "arguments": list(self.tool.arguments),
                "executable": self.tool.executable,
                "flags": list(self.tool.flags),
                "version_arguments": list(self.tool.version_arguments),
            },
        }


@dataclass(frozen=True, slots=True)
class ApprovedToolRegistry:
    """The complete content-addressed preparation configuration."""

    revision: str
    pipeline_revision: str
    routes: tuple[ApprovedRoute, ...]
    schema: str = TOOL_REGISTRY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != TOOL_REGISTRY_SCHEMA:
            _fail("tool registry schema is unsupported")
        _token(self.revision, "registry.revision")
        _token(self.pipeline_revision, "registry.pipeline_revision")
        if type(self.routes) is not tuple:
            _fail("registry.routes must be a tuple")
        if any(type(item) is not ApprovedRoute for item in self.routes):
            _fail("registry contains an invalid route")
        if self.routes != tuple(sorted(self.routes, key=lambda item: item.route)):
            _fail("registry routes must be canonically ordered")
        if tuple(item.route for item in self.routes) != REQUIRED_PREPARATION_ROUTES:
            _fail("registry must define every preparation route exactly once")
        for route in self.routes:
            route.__post_init__()

    def to_data(self) -> dict[str, object]:
        return {
            "pipeline_revision": self.pipeline_revision,
            "revision": self.revision,
            "routes": [route.to_data() for route in self.routes],
            "schema": self.schema,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_data())).hexdigest()

    @property
    def tool_specs(self) -> dict[str, ToolSpec]:
        return {route.route: route.tool for route in self.routes}


@dataclass(frozen=True, slots=True, init=False)
class PreparationReceipt:
    """A validated, immutable bridge from preparation into completion gates."""

    artifact_digest: str
    package_name: str
    version_code: str
    preflight_manifest_sha256: str
    manifest_sha256: str
    candidate_index_sha256: str
    tool_registry_sha256: str
    pipeline_revision: str
    invocations: tuple[InvocationRecord, ...]
    candidates: tuple[CandidateRecord, ...]
    revision: str

    def __init__(self) -> None:
        _fail("PreparationReceipt must be created by the trusted registry validator")

    def to_data(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "candidate_index_sha256": self.candidate_index_sha256,
            "candidates": [item.to_data() for item in self.candidates],
            "invocations": [item.to_data() for item in self.invocations],
            "manifest_sha256": self.manifest_sha256,
            "package_name": self.package_name,
            "pipeline_revision": self.pipeline_revision,
            "preflight_manifest_sha256": self.preflight_manifest_sha256,
            "revision": self.revision,
            "tool_registry_sha256": self.tool_registry_sha256,
            "version_code": self.version_code,
        }

    @property
    def content_id(self) -> str:
        return hashlib.sha256(
            b"phase4-v2:preparation-receipt\0" + _canonical_json(self.to_data())
        ).hexdigest()


def _expect_object(value: object, keys: set[str], field: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        _fail(f"{field} must contain the exact expected keys")
    return value


def _expect_list(value: object, field: str, maximum: int = _MAX_ITEMS) -> list[object]:
    if type(value) is not list or len(value) > maximum:
        _fail(f"{field} must be a bounded list")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        _fail(f"{field} must be a bounded integer")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 1024 * 1024:
        _fail(f"{field} must be null or a bounded string")
    return value


def _stream(value: object, field: str) -> StreamDigest:
    item = _expect_object(value, {"bytes", "sha256"}, field)
    return StreamDigest(
        _integer(item["bytes"], f"{field}.bytes"), _sha(item["sha256"], f"{field}.sha256")
    )


def _output(value: object, field: str) -> OutputMember:
    item = _expect_object(value, {"bytes", "path", "sha256"}, field)
    path = item["path"]
    if type(path) is not str or not path or len(path.encode()) > 4_096:
        _fail(f"{field}.path is invalid")
    candidate = PurePosixPath(path)
    if (
        candidate.is_absolute()
        or candidate.as_posix() != path
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        _fail(f"{field}.path is unsafe")
    return OutputMember(
        path, _integer(item["bytes"], f"{field}.bytes"), _sha(item["sha256"], f"{field}.sha256")
    )


def _warning(value: object, field: str) -> WarningRecord:
    item = _expect_object(value, {"line", "sha256", "stream", "text"}, field)
    stream = item["stream"]
    text = item["text"]
    if stream not in {"stdout", "stderr"} or type(stream) is not str:
        _fail(f"{field}.stream is invalid")
    if type(text) is not str or len(text.encode()) > 16 * 1024:
        _fail(f"{field}.text is invalid")
    return WarningRecord(
        stream,
        _integer(item["line"], f"{field}.line", minimum=1),
        text,
        _sha(item["sha256"], f"{field}.sha256"),
    )


def _tool(value: object, field: str) -> ToolRecord:
    keys = {
        "binary_bytes",
        "binary_sha256",
        "executable",
        "failure",
        "version",
        "version_arguments",
        "version_stderr",
        "version_stdout",
    }
    item = _expect_object(value, keys, field)
    executable = item["executable"]
    if type(executable) is not str or not executable or len(executable) > 4_096:
        _fail(f"{field}.executable is invalid")
    binary_bytes = item["binary_bytes"]
    if binary_bytes is not None:
        binary_bytes = _integer(binary_bytes, f"{field}.binary_bytes", minimum=1)
    binary_sha256 = item["binary_sha256"]
    if binary_sha256 is not None:
        binary_sha256 = _sha(binary_sha256, f"{field}.binary_sha256")
    version_arguments_raw = _expect_list(
        item["version_arguments"], f"{field}.version_arguments", 128
    )
    if any(type(argument) is not str for argument in version_arguments_raw):
        _fail(f"{field}.version_arguments contains a non-string")
    return ToolRecord(
        executable,
        binary_bytes,
        binary_sha256,
        tuple(cast(list[str], version_arguments_raw)),
        _optional_string(item["version"], f"{field}.version"),
        _stream(item["version_stdout"], f"{field}.version_stdout"),
        _stream(item["version_stderr"], f"{field}.version_stderr"),
        _optional_string(item["failure"], f"{field}.failure"),
    )


def _invocation(value: object, field: str) -> InvocationRecord:
    keys = {
        "arguments",
        "cache_key",
        "exit_code",
        "failures",
        "fallback_reason",
        "fallback_route",
        "flags",
        "input_sha256",
        "member",
        "outputs",
        "route",
        "status",
        "stderr",
        "stdout",
        "tool",
        "warnings",
    }
    item = _expect_object(value, keys, field)
    strings: dict[str, tuple[str, ...]] = {}
    for name, maximum in (("arguments", 4_096), ("failures", 4_096), ("flags", 4_096)):
        raw = _expect_list(item[name], f"{field}.{name}", maximum)
        if any(type(entry) is not str for entry in raw):
            _fail(f"{field}.{name} contains a non-string")
        strings[name] = tuple(cast(list[str], raw))
    status = item["status"]
    if status not in {"COMPLETE", "FALLBACK", "BLOCKED"} or type(status) is not str:
        _fail(f"{field}.status is invalid")
    exit_code = item["exit_code"]
    if exit_code is not None and (type(exit_code) is not int or not -(2**31) <= exit_code < 2**31):
        _fail(f"{field}.exit_code is invalid")
    cache_key = item["cache_key"]
    if cache_key is not None:
        cache_key = _sha(cache_key, f"{field}.cache_key")
    member, route = item["member"], item["route"]
    if type(member) is not str or not member or len(member.encode()) > 4_096:
        _fail(f"{field}.member is invalid")
    route = _token(route, f"{field}.route")
    outputs = tuple(
        _output(entry, f"{field}.outputs")
        for entry in _expect_list(item["outputs"], f"{field}.outputs")
    )
    warnings = tuple(
        _warning(entry, f"{field}.warnings")
        for entry in _expect_list(item["warnings"], f"{field}.warnings")
    )
    return InvocationRecord(
        member,
        _sha(item["input_sha256"], f"{field}.input_sha256"),
        route,
        cache_key,
        _tool(item["tool"], f"{field}.tool"),
        strings["arguments"],
        strings["flags"],
        status,
        exit_code,
        _stream(item["stdout"], f"{field}.stdout"),
        _stream(item["stderr"], f"{field}.stderr"),
        warnings,
        strings["failures"],
        outputs,
        _optional_string(item["fallback_route"], f"{field}.fallback_route"),
        _optional_string(item["fallback_reason"], f"{field}.fallback_reason"),
    )


def _candidate(value: object, field: str) -> CandidateRecord:
    keys = {
        "end_byte",
        "invocation_cache_key",
        "member",
        "output_path",
        "output_sha256",
        "route",
        "signal",
        "start_byte",
    }
    item = _expect_object(value, keys, field)
    member, path, signal = item["member"], item["output_path"], item["signal"]
    if any(type(value) is not str or not value for value in (member, path, signal)):
        _fail(f"{field} contains an invalid string")
    return CandidateRecord(
        _sha(item["invocation_cache_key"], f"{field}.invocation_cache_key"),
        cast(str, member),
        _token(item["route"], f"{field}.route"),
        cast(str, path),
        _sha(item["output_sha256"], f"{field}.output_sha256"),
        _integer(item["start_byte"], f"{field}.start_byte"),
        _integer(item["end_byte"], f"{field}.end_byte", minimum=1),
        _token(signal, f"{field}.signal"),
    )


def load_preparation_receipt(
    directory: Path | str,
    *,
    preflight: PreflightResult,
    registry: ApprovedToolRegistry,
    expected_registry_sha256: str,
    expected_manifest_sha256: str,
    expected_candidate_index_sha256: str,
) -> PreparationReceipt:
    """Validate frozen preparation output against externally trusted inputs."""

    registry.__post_init__()
    expected_registry_sha256 = _sha(expected_registry_sha256, "expected registry digest")
    expected_manifest_sha256 = _sha(expected_manifest_sha256, "expected manifest digest")
    expected_candidate_index_sha256 = _sha(
        expected_candidate_index_sha256, "expected candidate-index digest"
    )
    if registry.sha256 != expected_registry_sha256:
        _fail("tool registry does not match the externally trusted digest")
    if preflight.decision.status != "READY" or preflight.package_identity is None:
        _fail("receipt validation requires a READY preflight result")
    root = Path(os.path.abspath(os.fspath(directory)))
    if not root.is_dir() or root.is_symlink():
        _fail("preparation output must be a regular directory")
    names = {entry.name for entry in os.scandir(root)}
    if names not in (
        {"PREPARATION.COMPLETE", "candidate-index.json", "manifest.json"},
        {"PREPARATION.BLOCKED", "candidate-index.json", "manifest.json"},
    ):
        _fail("preparation output contains an unexpected member set")
    manifest_bytes = _bounded_regular_file(root / "manifest.json")
    candidate_bytes = _bounded_regular_file(root / "candidate-index.json")
    try:
        manifest = json.loads(manifest_bytes, object_pairs_hook=_unique_object)
        candidate_index = json.loads(candidate_bytes, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PreparationError("preparation output contains invalid JSON") from error
    if (
        manifest_bytes != _canonical_json(manifest) + b"\n"
        or candidate_bytes != _canonical_json(candidate_index) + b"\n"
    ):
        _fail("preparation output JSON is not canonical")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    if manifest_sha256 != expected_manifest_sha256:
        _fail("preparation manifest does not match its externally trusted digest")
    if candidate_sha256 != expected_candidate_index_sha256:
        _fail("candidate index does not match its externally trusted digest")
    marker_name = (
        "PREPARATION.COMPLETE" if manifest.get("status") == "COMPLETE" else "PREPARATION.BLOCKED"
    )
    if marker_name not in names:
        _fail("preparation marker does not match manifest status")
    expected_marker = (
        f"{manifest_sha256} manifest.json\n{candidate_sha256} candidate-index.json\n".encode(
            "ascii"
        )
    )
    if _bounded_regular_file(root / marker_name, 1024) != expected_marker:
        _fail("preparation marker does not bind the published payloads")

    manifest_keys = {
        "artifact_digest",
        "candidate_contract",
        "candidate_index",
        "failures",
        "invocations",
        "package_identity",
        "pipeline_revision",
        "preflight",
        "schema",
        "status",
        "tool_registry_sha256",
    }
    manifest = _expect_object(manifest, manifest_keys, "manifest")
    if manifest["schema"] != EXECUTION_SCHEMA or manifest["status"] != "COMPLETE":
        _fail("only COMPLETE current-schema preparation output is acceptable")
    if manifest["artifact_digest"] != preflight.artifact_digest:
        _fail("preparation artifact digest does not match preflight")
    if _canonical_json(manifest["package_identity"]) != _canonical_json(
        preflight.package_identity.public_dict()
    ):
        _fail("preparation package identity does not match preflight")
    if manifest["pipeline_revision"] != registry.pipeline_revision:
        _fail("preparation pipeline revision does not match the registry")
    if manifest["tool_registry_sha256"] != expected_registry_sha256:
        _fail("preparation manifest does not bind the approved registry")
    candidate_contract = _expect_object(
        manifest["candidate_contract"], {"revision", "sha256"}, "manifest.candidate_contract"
    )
    if candidate_contract != {
        "revision": CANDIDATE_CONTRACT_REVISION,
        "sha256": CANDIDATE_CONTRACT_SHA256,
    }:
        _fail("preparation candidate contract is not the current trusted contract")
    preflight_manifest_sha256 = hashlib.sha256(_canonical_json(preflight.manifest())).hexdigest()
    preflight_pin = _expect_object(
        manifest["preflight"], {"manifest_sha256", "schema"}, "manifest.preflight"
    )
    if preflight_pin != {"manifest_sha256": preflight_manifest_sha256, "schema": PREFLIGHT_SCHEMA}:
        _fail("preparation preflight binding does not match the trusted result")
    candidate_pin = _expect_object(
        manifest["candidate_index"], {"candidates", "member", "sha256"}, "manifest.candidate_index"
    )
    if (
        candidate_pin["member"] != "candidate-index.json"
        or candidate_pin["sha256"] != candidate_sha256
    ):
        _fail("preparation candidate-index binding is invalid")
    if _expect_list(manifest["failures"], "manifest.failures"):
        _fail("COMPLETE preparation must not contain aggregate failures")

    invocations = tuple(
        _invocation(value, "manifest.invocations")
        for value in _expect_list(manifest["invocations"], "manifest.invocations")
    )
    artifact_sha256 = {member.name: member.sha256 for member in preflight.artifact_members}
    expected_invocations = tuple(
        (member.name, route, artifact_sha256[member.name])
        for member in preflight.decision.members
        for route in member.routes
    )
    if (
        tuple((item.member, item.route, item.input_sha256) for item in invocations)
        != expected_invocations
    ):
        _fail("preparation invocation set does not exactly match preflight routing")
    registry_by_route = {route.route: route for route in registry.routes}
    output_lookup: dict[tuple[str, str, str], OutputMember] = {}
    invocation_by_cache_key: dict[str, InvocationRecord] = {}
    for invocation in invocations:
        route = registry_by_route[invocation.route]
        expected_arguments = tuple(
            "input.apk" if value == "{input}" else "output" if value == "{output}" else value
            for value in route.tool.arguments
        )
        if invocation.arguments != expected_arguments or invocation.flags != route.tool.flags:
            _fail(f"route {invocation.route!r} invocation differs from the approved registry")
        if (
            invocation.tool.executable != Path(route.tool.executable).name
            or invocation.tool.version_arguments != route.tool.version_arguments
        ):
            _fail(f"route {invocation.route!r} tool identity differs from the approved registry")
        qualification = (invocation.tool.binary_sha256, invocation.tool.version)
        if qualification not in {
            (item.binary_sha256, item.version) for item in route.qualifications
        }:
            _fail(f"route {invocation.route!r} tool build is not approved")
        if invocation.tool.failure is not None or invocation.failures or invocation.exit_code != 0:
            _fail(f"route {invocation.route!r} contains an execution failure")
        if invocation.status not in {"COMPLETE", "FALLBACK"} or invocation.cache_key is None:
            _fail(f"route {invocation.route!r} is not complete")
        if invocation.cache_key in invocation_by_cache_key:
            _fail("preparation invocations contain a duplicate cache identity")
        invocation_by_cache_key[invocation.cache_key] = invocation
        if invocation.status == "COMPLETE":
            if invocation.fallback_route is not None or invocation.fallback_reason is not None:
                _fail(f"route {invocation.route!r} has spurious fallback metadata")
            route.output.validate_outputs(invocation.outputs, invocation.route)
        elif (
            invocation.route != "jadx"
            or invocation.fallback_route != "apktool"
            or invocation.fallback_reason != "JADX_OUTPUT_SUSPICIOUS"
        ):
            _fail("only the exact authoritative jadx-to-apktool fallback is acceptable")
        for output in invocation.outputs:
            key = (invocation.cache_key, output.path, output.sha256)
            if key in output_lookup:
                _fail("preparation outputs contain a duplicate identity")
            output_lookup[key] = output

    candidate_index = _expect_object(
        candidate_index,
        {"artifact_digest", "candidate_contract_sha256", "candidates", "schema"},
        "candidate-index",
    )
    if (
        candidate_index["schema"] != CANDIDATE_INDEX_SCHEMA
        or candidate_index["artifact_digest"] != preflight.artifact_digest
    ):
        _fail("candidate index identity does not match preparation")
    if candidate_index["candidate_contract_sha256"] != CANDIDATE_CONTRACT_SHA256:
        _fail("candidate index does not bind the current trusted contract")
    candidates = tuple(
        _candidate(value, "candidate-index.candidates")
        for value in _expect_list(candidate_index["candidates"], "candidate-index.candidates")
    )
    if _integer(candidate_pin["candidates"], "manifest.candidate_index.candidates") != len(
        candidates
    ):
        _fail("candidate count does not match the manifest")
    if candidates != tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.member,
                item.route,
                item.output_path,
                item.start_byte,
                item.end_byte,
                item.signal,
            ),
        )
    ):
        _fail("candidate index is not canonically ordered")
    if len(set(candidates)) != len(candidates):
        _fail("candidate index contains duplicate occurrences")
    jadx_fallbacks = [item for item in invocations if item.status == "FALLBACK"]
    for fallback in jadx_fallbacks:
        authoritative = next(
            (
                item
                for item in invocations
                if item.member == fallback.member
                and item.route == "apktool"
                and item.status == "COMPLETE"
            ),
            None,
        )
        if authoritative is None:
            _fail("jadx fallback is missing its complete apktool invocation")
        registry_by_route["apktool"].output.validate_outputs(authoritative.outputs, "apktool")
    for candidate in candidates:
        if candidate.signal not in CANDIDATE_SIGNAL_IDS:
            _fail("candidate uses a signal outside the trusted candidate contract")
        candidate_output = output_lookup.get(
            (candidate.invocation_cache_key, candidate.output_path, candidate.output_sha256)
        )
        if (
            candidate_output is None
            or candidate.end_byte > candidate_output.bytes
            or candidate.start_byte >= candidate.end_byte
        ):
            _fail("candidate does not reference an exact bounded invocation output")
        invocation = invocation_by_cache_key[candidate.invocation_cache_key]
        if (candidate.member, candidate.route) != (invocation.member, invocation.route):
            _fail("candidate member or route does not match its invocation")

    receipt = object.__new__(PreparationReceipt)
    for name, value in (
        ("artifact_digest", preflight.artifact_digest),
        ("package_name", preflight.package_identity.package_name),
        ("version_code", preflight.package_identity.version_code),
        ("preflight_manifest_sha256", preflight_manifest_sha256),
        ("manifest_sha256", manifest_sha256),
        ("candidate_index_sha256", candidate_sha256),
        ("tool_registry_sha256", expected_registry_sha256),
        ("pipeline_revision", registry.pipeline_revision),
        ("invocations", invocations),
        ("candidates", candidates),
        ("revision", PREPARATION_RECEIPT_REVISION),
    ):
        object.__setattr__(receipt, name, value)
    return receipt


def execute_registered_preparation(
    preflight: PreflightResult,
    *,
    registry: ApprovedToolRegistry,
    expected_registry_sha256: str,
    cache_directory: Path | str,
    output_directory: Path | str,
    limits: ExecutionLimits | None = None,
) -> PreparationReceipt:
    """Execute only an externally pinned registry, then validate its frozen output."""

    registry.__post_init__()
    if registry.sha256 != _sha(expected_registry_sha256, "expected registry digest"):
        _fail("tool registry does not match the externally trusted digest")
    result = execute_preparation(
        preflight,
        tool_specs=registry.tool_specs,
        cache_directory=cache_directory,
        output_directory=output_directory,
        pipeline_revision=registry.pipeline_revision,
        tool_registry_sha256=expected_registry_sha256,
        approved_tool_builds={
            route.route: frozenset(
                (item.binary_sha256, item.version) for item in route.qualifications
            )
            for route in registry.routes
        },
        limits=limits,
    )
    if any(item.tool.failure == "TOOL_BUILD_UNAPPROVED" for item in result.invocations):
        _fail("preparation tool build is not approved by the trusted registry")
    return load_preparation_receipt(
        output_directory,
        preflight=preflight,
        registry=registry,
        expected_registry_sha256=expected_registry_sha256,
        expected_manifest_sha256=result.manifest_sha256,
        expected_candidate_index_sha256=result.candidate_index_sha256,
    )
