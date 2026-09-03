"""Adversarial tests for the pre-analysis evidence-lineage trust boundary."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError

import pytest

import tools.phase4_v2.validator.lineage as lineage_module
from tools.phase4_v2.validator.lineage import (
    LINEAGE_SCHEMA_REVISION,
    EvidenceLineageManifest,
    LineageValidationError,
    TrustedProducer,
    bind_evidence_lineage,
)

_ARTIFACT_DIGEST = "a" * 64
_PREFLIGHT_SHA256 = "b" * 64
_TOOL_SHA256 = "c" * 64
_INVOCATION_SHA256 = "d" * 64
_SOURCE_DIGESTS = {"base.apk": "e" * 64, "config.arm64.apk": "f" * 64}
_PRODUCER = TrustedProducer("extract-v1", "jadx", _TOOL_SHA256)


def _manifest(*, member_digest: str = "1" * 64) -> dict[str, object]:
    return {
        "artifact_digest": _ARTIFACT_DIGEST,
        "members": [
            {
                "authoritative_root_analyses": [],
                "package_local_domains": [],
                "producer": {
                    "invocation_sha256": _INVOCATION_SHA256,
                    "outcome": "SUCCEEDED",
                    "output_size": 128,
                    "pipeline_revision": _PRODUCER.pipeline_revision,
                    "route": _PRODUCER.route,
                    "tool_sha256": _PRODUCER.tool_sha256,
                },
                "report_member": f"evidence/sha256/{member_digest}",
                "sha256": member_digest,
                "source_artifact_members": [
                    {"name": name, "sha256": digest}
                    for name, digest in sorted(_SOURCE_DIGESTS.items())
                ],
            }
        ],
        "preflight_sha256": _PREFLIGHT_SHA256,
        "schema": LINEAGE_SCHEMA_REVISION,
    }


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _bind(
    value: dict[str, object],
    *,
    payload: bytes | None = None,
    expected_manifest_sha256: str | None = None,
    artifact_digest: str = _ARTIFACT_DIGEST,
    preflight_sha256: str = _PREFLIGHT_SHA256,
    source_artifacts: Mapping[str, str] | None = None,
    producers: tuple[TrustedProducer, ...] = (_PRODUCER,),
) -> EvidenceLineageManifest:
    encoded = _canonical(value) if payload is None else payload
    return bind_evidence_lineage(
        encoded,
        expected_manifest_sha256=(
            hashlib.sha256(encoded).hexdigest()
            if expected_manifest_sha256 is None
            else expected_manifest_sha256
        ),
        expected_artifact_digest=artifact_digest,
        expected_preflight_sha256=preflight_sha256,
        expected_source_artifacts=(
            dict(_SOURCE_DIGESTS) if source_artifacts is None else source_artifacts
        ),
        trusted_producers=producers,
    )


def _code(error: pytest.ExceptionInfo[LineageValidationError]) -> str:
    return error.value.diagnostic.code


def test_canonical_manifest_binds_to_external_trust_roots() -> None:
    value = _manifest()

    result = _bind(value)

    assert result.schema == LINEAGE_SCHEMA_REVISION
    assert result.artifact_digest == _ARTIFACT_DIGEST
    assert result.preflight_sha256 == _PREFLIGHT_SHA256
    assert result.manifest_sha256 == hashlib.sha256(_canonical(value)).hexdigest()
    assert result.member_digests == (("evidence/sha256/" + "1" * 64, "1" * 64),)
    assert result.to_data() == value
    with pytest.raises(FrozenInstanceError):
        result.artifact_digest = "0" * 64  # type: ignore[misc]


def test_manifest_binds_authoritative_root_analysis_to_its_exact_identity() -> None:
    value = _manifest()
    members = value["members"]
    assert isinstance(members, list)
    member = members[0]
    assert isinstance(member, dict)
    member["authoritative_root_analyses"] = [
        {
            "evidence_anchor_ids": ["anchor"],
            "semantic_root_sha256": "1" * 64,
            "target_occurrence_identity_sha256": "2" * 64,
            "target_root_id": "3" * 64,
        }
    ]

    [attestation] = _bind(value).members[0].authoritative_root_analyses

    assert attestation.semantic_root_sha256 == "1" * 64
    assert attestation.target_occurrence_identity_sha256 == "2" * 64
    assert attestation.target_root_id == "3" * 64
    assert attestation.evidence_anchor_ids == ("anchor",)


def test_manifest_rejects_duplicate_root_anchor_ids() -> None:
    value = _manifest()
    members = value["members"]
    assert isinstance(members, list)
    member = members[0]
    assert isinstance(member, dict)
    member["authoritative_root_analyses"] = [
        {
            "evidence_anchor_ids": ["anchor", "anchor"],
            "semantic_root_sha256": "1" * 64,
            "target_occurrence_identity_sha256": "2" * 64,
            "target_root_id": "3" * 64,
        }
    ]

    with pytest.raises(LineageValidationError) as caught:
        _bind(value)

    assert _code(caught) == "authoritative_root_anchor_set_not_canonical"


def test_manifest_rejects_conflicting_root_analyses_across_members() -> None:
    value = _manifest()
    members = value["members"]
    assert isinstance(members, list)
    first = members[0]
    assert isinstance(first, dict)
    second = copy.deepcopy(first)
    first["authoritative_root_analyses"] = [
        {
            "evidence_anchor_ids": ["anchor"],
            "semantic_root_sha256": "1" * 64,
            "target_occurrence_identity_sha256": "2" * 64,
            "target_root_id": "3" * 64,
        }
    ]
    second["authoritative_root_analyses"] = [
        {
            "evidence_anchor_ids": ["anchor"],
            "semantic_root_sha256": "4" * 64,
            "target_occurrence_identity_sha256": "2" * 64,
            "target_root_id": "3" * 64,
        }
    ]
    second["report_member"] = "evidence/sha256/" + "5" * 64
    second["sha256"] = "5" * 64
    members.append(second)

    with pytest.raises(LineageValidationError) as caught:
        _bind(value)

    assert _code(caught) == "conflicting_authoritative_root_analysis"


def test_manifest_requires_exact_external_digest() -> None:
    with pytest.raises(LineageValidationError) as caught:
        _bind(_manifest(), expected_manifest_sha256="0" * 64)

    assert _code(caught) == "manifest_digest_mismatch"


@pytest.mark.parametrize("suffix", [b"\n", b" "])
def test_manifest_bytes_must_be_canonical(suffix: bytes) -> None:
    value = _manifest()
    payload = _canonical(value) + suffix

    with pytest.raises(LineageValidationError) as caught:
        _bind(value, payload=payload)

    assert _code(caught) == "manifest_not_canonical"


def test_duplicate_json_keys_are_rejected() -> None:
    payload = b'{"artifact_digest":"' + _ARTIFACT_DIGEST.encode() + b'","members":[],"members":[]}'

    with pytest.raises(LineageValidationError) as caught:
        _bind(_manifest(), payload=payload)

    assert _code(caught) == "duplicate_object_key"


@pytest.mark.parametrize(
    ("field", "trusted", "code"),
    [
        ("artifact_digest", "0" * 64, "artifact_digest_mismatch"),
        ("preflight_sha256", "0" * 64, "preflight_digest_mismatch"),
    ],
)
def test_artifact_and_preflight_identity_are_exact(field: str, trusted: str, code: str) -> None:
    value = _manifest()
    value[field] = "9" * 64
    arguments = (
        {"artifact_digest": trusted}
        if field == "artifact_digest"
        else {"preflight_sha256": trusted}
    )

    with pytest.raises(LineageValidationError) as caught:
        _bind(value, **arguments)

    assert _code(caught) == code


def test_generated_file_cannot_be_blessed_by_renaming_only() -> None:
    value = _manifest()
    member = value["members"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    member["report_member"] = "evidence/copied-ir.json"

    with pytest.raises(LineageValidationError) as caught:
        _bind(value)

    assert _code(caught) == "report_member_not_content_addressed"


def test_source_must_match_validated_preflight_member() -> None:
    value = _manifest()
    member = value["members"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    sources = member["source_artifact_members"]
    assert isinstance(sources, list)
    source = sources[0]
    assert isinstance(source, dict)
    source["sha256"] = "0" * 64

    with pytest.raises(LineageValidationError) as caught:
        _bind(value)

    assert _code(caught) == "source_artifact_mismatch"


def test_untrusted_producer_is_rejected() -> None:
    value = _manifest()
    member = value["members"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    producer = member["producer"]
    assert isinstance(producer, dict)
    producer["route"] = "apktool"

    with pytest.raises(LineageValidationError) as caught:
        _bind(value)

    assert _code(caught) == "untrusted_producer"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("outcome", "FAILED", "producer_not_successful"),
        ("output_size", 0, "invalid_output_size"),
        ("output_size", True, "invalid_output_size"),
    ],
)
def test_producer_completion_must_attest_successful_substantive_output(
    field: str, value: object, code: str
) -> None:
    manifest = _manifest()
    member = manifest["members"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    producer = member["producer"]
    assert isinstance(producer, dict)
    producer[field] = value

    with pytest.raises(LineageValidationError) as caught:
        _bind(manifest)

    assert _code(caught) == code


def test_members_must_be_sorted_and_unique() -> None:
    value = _manifest(member_digest="2" * 64)
    members = value["members"]
    assert isinstance(members, list)
    second = copy.deepcopy(members[0])
    assert isinstance(second, dict)
    second["sha256"] = "1" * 64
    second["report_member"] = "evidence/sha256/" + "1" * 64
    members.append(second)

    with pytest.raises(LineageValidationError) as unsorted:
        _bind(value)
    assert _code(unsorted) == "members_not_sorted"

    members[:] = [members[0], copy.deepcopy(members[0])]
    with pytest.raises(LineageValidationError) as duplicate:
        _bind(value)
    assert _code(duplicate) == "duplicate_member"


def test_sources_must_be_sorted_and_unique() -> None:
    value = _manifest()
    member = value["members"][0]  # type: ignore[index]
    assert isinstance(member, dict)
    sources = member["source_artifact_members"]
    assert isinstance(sources, list)
    sources.reverse()

    with pytest.raises(LineageValidationError) as unsorted:
        _bind(value)
    assert _code(unsorted) == "source_artifacts_not_sorted"

    sources[:] = [sources[0], copy.deepcopy(sources[0])]
    with pytest.raises(LineageValidationError) as duplicate:
        _bind(value)
    assert _code(duplicate) == "duplicate_source_artifact"


@pytest.mark.parametrize(
    ("attribute", "code"),
    [
        ("_MAX_MEMBERS", "member_limit_exceeded"),
        ("_MAX_SOURCES_PER_MEMBER", "source_set_limit_exceeded"),
        ("_MAX_TOTAL_SOURCES", "source_reference_limit_exceeded"),
    ],
)
def test_manifest_collection_bounds_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch, attribute: str, code: str
) -> None:
    monkeypatch.setattr(lineage_module, attribute, 0)

    with pytest.raises(LineageValidationError) as caught:
        _bind(_manifest())

    assert _code(caught) == code


def test_trusted_producer_and_artifact_bounds_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lineage_module, "_MAX_TRUSTED_PRODUCERS", 0)
    with pytest.raises(LineageValidationError) as producers:
        _bind(_manifest())
    assert _code(producers) == "trusted_producer_limit_exceeded"

    monkeypatch.setattr(lineage_module, "_MAX_TRUSTED_PRODUCERS", 256)
    monkeypatch.setattr(lineage_module, "_MAX_ARTIFACT_MEMBERS", 0)
    with pytest.raises(LineageValidationError) as artifacts:
        _bind(_manifest())
    assert _code(artifacts) == "trusted_source_artifact_limit_exceeded"


class _LyingSourceMapping(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        return "e" * 64

    def __iter__(self) -> Iterator[str]:
        return iter(
            f"split-{index:04d}.apk" for index in range(lineage_module._MAX_ARTIFACT_MEMBERS + 1)
        )

    def __len__(self) -> int:
        return 1


def test_trusted_source_bound_does_not_rely_on_mapping_length() -> None:
    with pytest.raises(LineageValidationError) as caught:
        _bind(_manifest(), source_artifacts=_LyingSourceMapping())

    assert _code(caught) == "trusted_source_artifact_limit_exceeded"


def test_duplicate_trusted_producers_and_source_names_are_rejected() -> None:
    with pytest.raises(LineageValidationError) as producers:
        _bind(_manifest(), producers=(_PRODUCER, _PRODUCER))
    assert _code(producers) == "duplicate_trusted_producer"

    sources = {"BASE.apk": "1" * 64, "base.apk": "2" * 64}
    with pytest.raises(LineageValidationError) as artifacts:
        _bind(_manifest(), source_artifacts=sources)
    assert _code(artifacts) == "duplicate_trusted_source_artifact"


def test_manifest_byte_and_node_bounds_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lineage_module, "_MAX_MANIFEST_BYTES", 1)
    with pytest.raises(LineageValidationError) as byte_limit:
        _bind(_manifest())
    assert _code(byte_limit) == "manifest_too_large"

    monkeypatch.setattr(lineage_module, "_MAX_MANIFEST_BYTES", 64 * 1024**2)
    monkeypatch.setattr(lineage_module, "_MAX_JSON_NODES", 1)
    with pytest.raises(LineageValidationError) as node_limit:
        _bind(_manifest())
    assert _code(node_limit) == "json_too_large"


@pytest.mark.parametrize("name", ["../base.apk", "/base.apk", "base.dex", "base\\evil.apk"])
def test_source_artifact_names_are_canonical_apk_members(name: str) -> None:
    sources = {name: "1" * 64}

    with pytest.raises(LineageValidationError) as caught:
        _bind(_manifest(), source_artifacts=sources)

    assert _code(caught) == "invalid_source_artifact_name"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value.update(schema="obsolete"), "unsupported_schema_revision"),
        (lambda value: value.update(extra=True), "object_keys_mismatch"),
        (lambda value: value.update(members=[]), "empty_member_set"),
    ],
)
def test_schema_is_closed_and_revision_pinned(mutation: object, code: str) -> None:
    value = _manifest()
    assert callable(mutation)
    mutation(value)

    with pytest.raises(LineageValidationError) as caught:
        _bind(value)

    assert _code(caught) == code


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b'{"value":"\\ud800"}', "invalid_unicode"),
        (b'{"value":9223372036854775808}', "invalid_number"),
        (b"[" * 100 + b"]" * 100, "json_too_deep"),
    ],
)
def test_hostile_json_is_a_closed_diagnostic(payload: bytes, code: str) -> None:
    with pytest.raises(LineageValidationError) as caught:
        _bind(_manifest(), payload=payload)

    assert _code(caught) == code
