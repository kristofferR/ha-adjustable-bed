"""Strict trust boundary for pre-analysis evidence lineage manifests."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Never, cast

LINEAGE_SCHEMA_REVISION = "phase4-v2-evidence-lineage-v4"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_ROUTE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")
_MAX_MANIFEST_BYTES = 64 * 1024**2
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 100_000
_MAX_MEMBERS = 4_096
_MAX_SOURCES_PER_MEMBER = 128
_MAX_TOTAL_SOURCES = 65_536
_MAX_TRUSTED_PRODUCERS = 256
_MAX_ARTIFACT_MEMBERS = 4_096
_MAX_ARTIFACT_MEMBER_LENGTH = 4_096
_MAX_ROOT_ANALYSES_PER_MEMBER = 256


@dataclass(frozen=True, slots=True)
class LineageDiagnostic:
    """One deterministic lineage validation failure."""

    code: str
    path: str
    message: str


class LineageValidationError(ValueError):
    """A lineage manifest did not cross the external trust boundary."""

    def __init__(self, diagnostic: LineageDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(f"{diagnostic.code} at {diagnostic.path}: {diagnostic.message}")


@dataclass(frozen=True, slots=True, order=True)
class TrustedProducer:
    """A producer identity authorized by orchestration, not by the report."""

    pipeline_revision: str
    route: str
    tool_sha256: str


@dataclass(frozen=True, slots=True)
class EvidenceLineageTrust:
    """Externally supplied lineage bytes, digest pin, and producer allowlist."""

    payload: bytes
    expected_manifest_sha256: str
    trusted_producers: tuple[TrustedProducer, ...]


@dataclass(frozen=True, slots=True)
class EvidenceProducer:
    """The exact trusted producer and invocation for one evidence output."""

    pipeline_revision: str
    route: str
    tool_sha256: str
    invocation_sha256: str
    outcome: Literal["SUCCEEDED"]
    output_size: int

    @property
    def trust_identity(self) -> TrustedProducer:
        return TrustedProducer(self.pipeline_revision, self.route, self.tool_sha256)

    def to_data(self) -> dict[str, str | int]:
        return {
            "invocation_sha256": self.invocation_sha256,
            "outcome": self.outcome,
            "output_size": self.output_size,
            "pipeline_revision": self.pipeline_revision,
            "route": self.route,
            "tool_sha256": self.tool_sha256,
        }


@dataclass(frozen=True, slots=True, order=True)
class SourceArtifactMember:
    """One exact APK member consumed by an evidence producer."""

    name: str
    sha256: str

    def to_data(self) -> dict[str, str]:
        return {"name": self.name, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class AuthoritativeRootAnalysisAttestation:
    """One trusted root-analysis result produced with an evidence member."""

    target_root_id: str
    target_occurrence_identity_sha256: str
    semantic_root_sha256: str

    def to_data(self) -> dict[str, str]:
        return {
            "semantic_root_sha256": self.semantic_root_sha256,
            "target_occurrence_identity_sha256": self.target_occurrence_identity_sha256,
            "target_root_id": self.target_root_id,
        }


@dataclass(frozen=True, slots=True)
class EvidenceLineageMember:
    """One content-addressed report member with artifact and producer lineage."""

    report_member: str
    sha256: str
    package_local_domains: tuple[str, ...]
    authoritative_root_analyses: tuple[AuthoritativeRootAnalysisAttestation, ...]
    source_artifact_members: tuple[SourceArtifactMember, ...]
    producer: EvidenceProducer

    def to_data(self) -> dict[str, object]:
        return {
            "authoritative_root_analyses": [
                item.to_data() for item in self.authoritative_root_analyses
            ],
            "producer": self.producer.to_data(),
            "package_local_domains": list(self.package_local_domains),
            "report_member": self.report_member,
            "sha256": self.sha256,
            "source_artifact_members": [item.to_data() for item in self.source_artifact_members],
        }


@dataclass(frozen=True, slots=True)
class EvidenceLineageManifest:
    """An authorized, immutable evidence set suitable for bundle binding."""

    schema: str
    manifest_sha256: str
    artifact_digest: str
    preflight_sha256: str
    members: tuple[EvidenceLineageMember, ...]

    @property
    def member_digests(self) -> tuple[tuple[str, str], ...]:
        """Return the exact report member set expected by bundle validation."""
        return tuple((item.report_member, item.sha256) for item in self.members)

    def to_data(self) -> dict[str, object]:
        """Return the canonical manifest content, excluding its external digest."""
        return {
            "artifact_digest": self.artifact_digest,
            "members": [item.to_data() for item in self.members],
            "preflight_sha256": self.preflight_sha256,
            "schema": self.schema,
        }


def bind_evidence_lineage(
    payload: str | bytes,
    *,
    expected_manifest_sha256: str,
    expected_artifact_digest: str,
    expected_preflight_sha256: str,
    expected_source_artifacts: Mapping[str, str],
    trusted_producers: Iterable[TrustedProducer],
) -> EvidenceLineageManifest:
    """Authorize canonical lineage bytes against orchestration-owned trust roots."""

    expected_manifest = _expect_sha256(expected_manifest_sha256, "$.trust.manifest_sha256")
    expected_artifact = _expect_sha256(expected_artifact_digest, "$.trust.artifact_digest")
    expected_preflight = _expect_sha256(expected_preflight_sha256, "$.trust.preflight_sha256")
    source_artifacts = _parse_expected_source_artifacts(expected_source_artifacts)
    producers = _parse_trusted_producers(trusted_producers)

    raw, encoded = _decode_strict_json(payload)
    root = _expect_object(raw, "$")
    canonical = _canonical_json(root)
    if encoded != canonical:
        _fail(
            "manifest_not_canonical",
            "$",
            "lineage manifest must be canonical UTF-8 JSON without a trailing newline",
        )
    actual_manifest = hashlib.sha256(encoded).hexdigest()
    if actual_manifest != expected_manifest:
        _fail(
            "manifest_digest_mismatch",
            "$.trust.manifest_sha256",
            "lineage bytes do not match the externally supplied manifest digest",
        )

    _expect_keys(
        root,
        path="$",
        required={"schema", "artifact_digest", "preflight_sha256", "members"},
    )
    schema = _expect_string(root["schema"], "$.schema", maximum=200)
    if schema != LINEAGE_SCHEMA_REVISION:
        _fail(
            "unsupported_schema_revision",
            "$.schema",
            f"expected {LINEAGE_SCHEMA_REVISION!r}",
        )
    artifact_digest = _expect_sha256(root["artifact_digest"], "$.artifact_digest")
    preflight_sha256 = _expect_sha256(root["preflight_sha256"], "$.preflight_sha256")
    if artifact_digest != expected_artifact:
        _fail(
            "artifact_digest_mismatch",
            "$.artifact_digest",
            "lineage artifact does not match validated preflight identity",
        )
    if preflight_sha256 != expected_preflight:
        _fail(
            "preflight_digest_mismatch",
            "$.preflight_sha256",
            "lineage preflight does not match the trusted preflight dependency",
        )

    members = _parse_members(root["members"], source_artifacts, producers)
    return EvidenceLineageManifest(
        schema=schema,
        manifest_sha256=actual_manifest,
        artifact_digest=artifact_digest,
        preflight_sha256=preflight_sha256,
        members=members,
    )


def _parse_expected_source_artifacts(value: Mapping[str, str]) -> dict[str, str]:
    if not value:
        _fail(
            "trusted_source_artifacts_required",
            "$.trust.source_artifacts",
            "validated preflight must supply at least one APK member",
        )
    parsed: dict[str, str] = {}
    for index, (name, digest) in enumerate(value.items()):
        if index >= _MAX_ARTIFACT_MEMBERS:
            _fail(
                "trusted_source_artifact_limit_exceeded",
                "$.trust.source_artifacts",
                f"source artifact count exceeds {_MAX_ARTIFACT_MEMBERS}",
            )
        parsed_name = _expect_artifact_member_name(name, "$.trust.source_artifacts")
        parsed_digest = _expect_sha256(digest, f"$.trust.source_artifacts.{parsed_name}")
        parsed[parsed_name] = parsed_digest
    if len({name.casefold() for name in parsed}) != len(parsed):
        _fail(
            "duplicate_trusted_source_artifact",
            "$.trust.source_artifacts",
            "validated preflight APK member names must be case-insensitively unique",
        )
    return parsed


def _parse_trusted_producers(value: Iterable[TrustedProducer]) -> frozenset[TrustedProducer]:
    collected: list[TrustedProducer] = []
    for index, producer in enumerate(value):
        if index >= _MAX_TRUSTED_PRODUCERS:
            _fail(
                "trusted_producer_limit_exceeded",
                "$.trust.producers",
                f"trusted producer count exceeds {_MAX_TRUSTED_PRODUCERS}",
            )
        if not isinstance(producer, TrustedProducer):
            _fail(
                "trusted_producer_invalid",
                f"$.trust.producers[{index}]",
                "trusted producers must use the immutable TrustedProducer type",
            )
        _expect_revision(
            producer.pipeline_revision, f"$.trust.producers[{index}].pipeline_revision"
        )
        _expect_route(producer.route, f"$.trust.producers[{index}].route")
        _expect_sha256(producer.tool_sha256, f"$.trust.producers[{index}].tool_sha256")
        collected.append(producer)
    if not collected:
        _fail(
            "trusted_producers_required",
            "$.trust.producers",
            "orchestration must authorize at least one producer",
        )
    if len(set(collected)) != len(collected):
        _fail(
            "duplicate_trusted_producer",
            "$.trust.producers",
            "trusted producer identities must be unique",
        )
    return frozenset(collected)


def _parse_members(
    raw: object,
    expected_sources: Mapping[str, str],
    trusted_producers: frozenset[TrustedProducer],
) -> tuple[EvidenceLineageMember, ...]:
    values = _expect_array(raw, "$.members")
    if not values:
        _fail("empty_member_set", "$.members", "lineage must contain evidence")
    if len(values) > _MAX_MEMBERS:
        _fail("member_limit_exceeded", "$.members", f"member count exceeds {_MAX_MEMBERS}")
    members = tuple(
        _parse_member(item, f"$.members[{index}]", expected_sources, trusted_producers)
        for index, item in enumerate(values)
    )
    member_paths = [item.report_member for item in members]
    if len(set(member_paths)) != len(member_paths):
        _fail("duplicate_member", "$.members", "report members must be unique")
    if member_paths != sorted(member_paths, key=lambda item: item.encode("utf-8")):
        _fail("members_not_sorted", "$.members", "members must use canonical byte ordering")
    total_sources = sum(len(item.source_artifact_members) for item in members)
    if total_sources > _MAX_TOTAL_SOURCES:
        _fail(
            "source_reference_limit_exceeded",
            "$.members",
            f"total source references exceed {_MAX_TOTAL_SOURCES}",
        )
    root_analyses: dict[tuple[str, str], str] = {}
    for member in members:
        for attestation in member.authoritative_root_analyses:
            identity = (
                attestation.target_root_id,
                attestation.target_occurrence_identity_sha256,
            )
            if identity in root_analyses:
                code = (
                    "duplicate_authoritative_root_analysis"
                    if root_analyses[identity] == attestation.semantic_root_sha256
                    else "conflicting_authoritative_root_analysis"
                )
                _fail(code, "$.members", "each root identity must have one semantic result")
            root_analyses[identity] = attestation.semantic_root_sha256
    return members


def _parse_member(
    raw: object,
    path: str,
    expected_sources: Mapping[str, str],
    trusted_producers: frozenset[TrustedProducer],
) -> EvidenceLineageMember:
    value = _expect_object(raw, path)
    _expect_keys(
        value,
        path=path,
        required={
            "authoritative_root_analyses",
            "package_local_domains",
            "producer",
            "report_member",
            "sha256",
            "source_artifact_members",
        },
    )
    digest = _expect_sha256(value["sha256"], f"{path}.sha256")
    report_member = _expect_string(value["report_member"], f"{path}.report_member", maximum=96)
    expected_report_member = f"evidence/sha256/{digest}"
    if report_member != expected_report_member:
        _fail(
            "report_member_not_content_addressed",
            f"{path}.report_member",
            f"expected {expected_report_member!r}",
        )
    sources = _parse_sources(value["source_artifact_members"], f"{path}.source_artifact_members")
    package_local_domains = _parse_package_local_domains(
        value["package_local_domains"], f"{path}.package_local_domains"
    )
    root_analyses = _parse_authoritative_root_analyses(
        value["authoritative_root_analyses"], f"{path}.authoritative_root_analyses"
    )
    for source in sources:
        if expected_sources.get(source.name) != source.sha256:
            _fail(
                "source_artifact_mismatch",
                f"{path}.source_artifact_members",
                f"source {source.name!r} is not in the validated preflight artifact set",
            )
    producer = _parse_producer(value["producer"], f"{path}.producer")
    if producer.trust_identity not in trusted_producers:
        _fail(
            "untrusted_producer",
            f"{path}.producer",
            "producer pipeline, route, and tool digest are not authorized",
        )
    return EvidenceLineageMember(
        report_member=report_member,
        sha256=digest,
        package_local_domains=package_local_domains,
        authoritative_root_analyses=root_analyses,
        source_artifact_members=sources,
        producer=producer,
    )


def _parse_authoritative_root_analyses(
    raw: object, path: str
) -> tuple[AuthoritativeRootAnalysisAttestation, ...]:
    values = _expect_array(raw, path)
    if len(values) > _MAX_ROOT_ANALYSES_PER_MEMBER:
        _fail(
            "authoritative_root_analysis_limit_exceeded",
            path,
            f"root analysis count exceeds {_MAX_ROOT_ANALYSES_PER_MEMBER}",
        )
    attestations: list[AuthoritativeRootAnalysisAttestation] = []
    for index, item in enumerate(values):
        location = f"{path}[{index}]"
        value = _expect_object(item, location)
        _expect_keys(
            value,
            path=location,
            required={
                "semantic_root_sha256",
                "target_occurrence_identity_sha256",
                "target_root_id",
            },
        )
        attestations.append(
            AuthoritativeRootAnalysisAttestation(
                target_root_id=_expect_sha256(
                    value["target_root_id"], f"{location}.target_root_id"
                ),
                target_occurrence_identity_sha256=_expect_sha256(
                    value["target_occurrence_identity_sha256"],
                    f"{location}.target_occurrence_identity_sha256",
                ),
                semantic_root_sha256=_expect_sha256(
                    value["semantic_root_sha256"], f"{location}.semantic_root_sha256"
                ),
            )
        )
    keys = [
        (
            item.target_root_id,
            item.target_occurrence_identity_sha256,
            item.semantic_root_sha256,
        )
        for item in attestations
    ]
    if keys != sorted(keys):
        _fail(
            "authoritative_root_analyses_not_sorted",
            path,
            "root analyses must use canonical digest ordering",
        )
    return tuple(attestations)


def _parse_package_local_domains(raw: object, path: str) -> tuple[str, ...]:
    values = _expect_array(raw, path)
    if len(values) > 256:
        _fail("package_local_domain_limit_exceeded", path, "domain count exceeds 256")
    domains = tuple(
        _expect_revision(item, f"{path}[{index}]") for index, item in enumerate(values)
    )
    if len(set(domains)) != len(domains):
        _fail("duplicate_package_local_domain", path, "domains must be unique")
    if list(domains) != sorted(domains, key=lambda item: item.encode("utf-8")):
        _fail("package_local_domains_not_sorted", path, "domains must use canonical byte ordering")
    return domains


def _parse_sources(raw: object, path: str) -> tuple[SourceArtifactMember, ...]:
    values = _expect_array(raw, path)
    if not values:
        _fail("empty_source_set", path, "each evidence member requires APK sources")
    if len(values) > _MAX_SOURCES_PER_MEMBER:
        _fail(
            "source_set_limit_exceeded",
            path,
            f"source count exceeds {_MAX_SOURCES_PER_MEMBER}",
        )
    sources: list[SourceArtifactMember] = []
    for index, item in enumerate(values):
        location = f"{path}[{index}]"
        value = _expect_object(item, location)
        _expect_keys(value, path=location, required={"name", "sha256"})
        sources.append(
            SourceArtifactMember(
                _expect_artifact_member_name(value["name"], f"{location}.name"),
                _expect_sha256(value["sha256"], f"{location}.sha256"),
            )
        )
    source_keys = [(item.name.encode("utf-8"), item.sha256) for item in sources]
    if len(set(sources)) != len(sources):
        _fail("duplicate_source_artifact", path, "source artifact entries must be unique")
    if source_keys != sorted(source_keys):
        _fail("source_artifacts_not_sorted", path, "sources must use canonical byte ordering")
    return tuple(sources)


def _parse_producer(raw: object, path: str) -> EvidenceProducer:
    value = _expect_object(raw, path)
    _expect_keys(
        value,
        path=path,
        required={
            "pipeline_revision",
            "route",
            "tool_sha256",
            "invocation_sha256",
            "outcome",
            "output_size",
        },
    )
    return EvidenceProducer(
        pipeline_revision=_expect_revision(value["pipeline_revision"], f"{path}.pipeline_revision"),
        route=_expect_route(value["route"], f"{path}.route"),
        tool_sha256=_expect_sha256(value["tool_sha256"], f"{path}.tool_sha256"),
        invocation_sha256=_expect_sha256(value["invocation_sha256"], f"{path}.invocation_sha256"),
        outcome=_expect_success(value["outcome"], f"{path}.outcome"),
        output_size=_expect_positive_integer(value["output_size"], f"{path}.output_size"),
    )


def _decode_strict_json(payload: str | bytes) -> tuple[object, bytes]:
    if isinstance(payload, str):
        try:
            encoded = payload.encode("utf-8")
        except UnicodeEncodeError as error:
            raise LineageValidationError(
                LineageDiagnostic("invalid_unicode", "$", "input contains an unpaired surrogate")
            ) from error
    elif isinstance(payload, bytes):
        encoded = payload
    else:
        _fail("invalid_input_type", "$", "lineage input must be text or bytes")
    if len(encoded) > _MAX_MANIFEST_BYTES:
        _fail(
            "manifest_too_large",
            "$",
            f"manifest has {len(encoded)} bytes; limit is {_MAX_MANIFEST_BYTES}",
        )
    try:
        raw = json.loads(
            encoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_number,
            parse_float=_reject_number,
            parse_int=_parse_integer,
        )
    except _DuplicateKey as error:
        raise LineageValidationError(
            LineageDiagnostic(
                "duplicate_object_key", "$", f"JSON object key {error.key!r} is duplicated"
            )
        ) from error
    except _InvalidNumber as error:
        raise LineageValidationError(
            LineageDiagnostic("invalid_number", "$", f"unsupported JSON number {error.value!r}")
        ) from error
    except RecursionError as error:
        raise LineageValidationError(
            LineageDiagnostic("json_too_deep", "$", "JSON nesting exceeds the parser limit")
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise LineageValidationError(LineageDiagnostic("invalid_json", "$", str(error))) from error
    _validate_json_shape(raw)
    return raw, encoded


def _validate_json_shape(raw: object) -> None:
    pending: list[tuple[object, int]] = [(raw, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            _fail("json_too_large", "$", f"JSON node count exceeds {_MAX_JSON_NODES}")
        if depth > _MAX_JSON_DEPTH:
            _fail("json_too_deep", "$", f"JSON nesting exceeds {_MAX_JSON_DEPTH}")
        if isinstance(value, dict):
            pending.extend((key, depth + 1) for key in value)
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise LineageValidationError(
                    LineageDiagnostic("invalid_unicode", "$", "JSON contains an unpaired surrogate")
                ) from error
        elif value is not None and type(value) not in {bool, int}:
            _fail("invalid_json_value", "$", f"unsupported JSON value {type(value).__name__}")


def _expect_object(raw: object, path: str) -> dict[str, object]:
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        _fail("expected_object", path, "expected a JSON object")
    return cast(dict[str, object], raw)


def _expect_array(raw: object, path: str) -> list[object]:
    if not isinstance(raw, list):
        _fail("expected_array", path, "expected a JSON array")
    return cast(list[object], raw)


def _expect_keys(value: Mapping[str, object], *, path: str, required: set[str]) -> None:
    if set(value) != required:
        _fail("object_keys_mismatch", path, "object does not contain the exact required keys")


def _expect_string(raw: object, path: str, *, maximum: int) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > maximum:
        _fail("invalid_string", path, f"expected 1 to {maximum} characters")
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError:
        _fail("invalid_unicode", path, "string contains an unpaired surrogate")
    return raw


def _expect_sha256(raw: object, path: str) -> str:
    value = _expect_string(raw, path, maximum=64)
    if _SHA256.fullmatch(value) is None:
        _fail("invalid_sha256", path, "expected lowercase SHA-256")
    return value


def _expect_revision(raw: object, path: str) -> str:
    value = _expect_string(raw, path, maximum=200)
    if _REVISION.fullmatch(value) is None:
        _fail("invalid_pipeline_revision", path, "pipeline revision is not canonical")
    return value


def _expect_route(raw: object, path: str) -> str:
    value = _expect_string(raw, path, maximum=100)
    if _ROUTE.fullmatch(value) is None:
        _fail("invalid_producer_route", path, "producer route is not canonical")
    return value


def _expect_success(raw: object, path: str) -> Literal["SUCCEEDED"]:
    if raw != "SUCCEEDED":
        _fail("producer_not_successful", path, "producer outcome must be 'SUCCEEDED'")
    return raw


def _expect_positive_integer(raw: object, path: str) -> int:
    if type(raw) is not int or not 0 < raw <= 2**63 - 1:
        _fail("invalid_output_size", path, "output size must be a positive 64-bit integer")
    return raw


def _expect_artifact_member_name(raw: object, path: str) -> str:
    value = _expect_string(raw, path, maximum=_MAX_ARTIFACT_MEMBER_LENGTH)
    candidate = PurePosixPath(value)
    if (
        "\\" in value
        or "\x00" in value
        or "\r" in value
        or "\n" in value
        or candidate.is_absolute()
        or value != candidate.as_posix()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or not value.casefold().endswith(".apk")
    ):
        _fail("invalid_source_artifact_name", path, "source must be a canonical APK member")
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _parse_integer(value: str) -> int:
    digits = value.removeprefix("-")
    if len(digits) > 19:
        raise _InvalidNumber(value)
    parsed = int(value)
    if not -(2**63) <= parsed <= 2**63 - 1:
        raise _InvalidNumber(value)
    return parsed


def _reject_number(value: str) -> Never:
    raise _InvalidNumber(value)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _fail(code: str, path: str, message: str) -> Never:
    raise LineageValidationError(LineageDiagnostic(code, path, message))


class _DuplicateKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


class _InvalidNumber(ValueError):
    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__(value)
