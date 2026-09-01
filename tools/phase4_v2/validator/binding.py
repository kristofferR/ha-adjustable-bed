"""Typed dependency and evidence binding checks for Phase 4 v2 reports."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, TypeGuard, cast

from jsonschema.validators import Draft202012Validator

from tools.phase4_v2.ir import (
    SCHEMA_REVISION,
    IRValidationError,
    schema_document,
    validate_universe,
)
from tools.phase4_v2.ir.model import (
    _parse_ir_structure,
    _resolve_semantic_pointer,
    _validate_exact_evidence_coverage,
)

from .lineage import (
    EvidenceLineageTrust,
    LineageValidationError,
    bind_evidence_lineage,
)

CONTRACT_REVISION = "phase4-v2-validation-input-v3"
PACKAGE_CONTRACT_REVISION = "phase4-v2-package-validation-input-v2"
PREFLIGHT_SCHEMA = "phase4-v2-preflight-v3"
_LEGACY_PREFLIGHT_SCHEMA = "phase4-v2-preflight-v2"
VALIDATION_INPUT = "validation-input.json"
_REQUIRED_FROZEN_REPORT_MEMBERS = frozenset({"ANALYSIS.md", "SEARCH_LOG.md", "analysis.json"})
_DEPENDENCY_NAMES = ("corpus", "ir", "preflight", "schema")
_PACKAGE_DEPENDENCY_NAMES = (
    "corpus",
    "execution_plan",
    "ir",
    "preflight",
    "report_schema",
    "schema",
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_MAX_ANCHOR_COUNT = 4_096
_MAX_EVIDENCE_MEMBER_COUNT = 4_096
_MAX_ANCHOR_BYTES = 64 * 1024**2
_MAX_ANCHOR_ID_LENGTH = 256
_MAX_JSON_POINTER_LENGTH = 8_192
PACKAGE_LOCAL_DOMAIN_RESULT_SCHEMA: dict[str, object] = {
    "additionalProperties": False,
    "properties": {
        "evidence": {
            "items": {"minLength": 1, "type": "string"},
            "minItems": 1,
            "type": "array",
            "uniqueItems": True,
        },
        "status": {"const": "COMPLETE"},
    },
    "required": ["evidence", "status"],
    "type": "object",
}
_STACK_ROUTES: dict[str, tuple[str, ...]] = {
    "air": ("ffdec",),
    "android": ("apktool",),
    "android_dex": ("jadx",),
    "embedded_archive": ("embedded-archive-inventory",),
    "flutter": ("blutter",),
    "hermes": ("hermes-bundle",),
    "native": ("native-library-inventory",),
    "react_native": ("react-native-bundle",),
    "shipped_bundle": ("shipped-bundle",),
}
_ANALYSIS_SCHEMA = json.loads(
    (Path(__file__).parents[3] / "docs/apk-analysis/analysis.schema.json").read_text(
        encoding="utf-8"
    )
)
_ANALYSIS_VALIDATOR = Draft202012Validator(_ANALYSIS_SCHEMA)


class MemberNode(Protocol):
    """The filesystem facts needed by the binding validator."""

    @property
    def kind(self) -> str: ...

    @property
    def size(self) -> int: ...

    @property
    def sha256(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class DependencyPins:
    """Trusted content identities supplied by the orchestration layer."""

    preflight_sha256: str
    ir_sha256: str
    schema_sha256: str
    corpus_sha256: str

    def as_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return stable dependency names and digests."""
        return (
            ("corpus", self.corpus_sha256),
            ("ir", self.ir_sha256),
            ("preflight", self.preflight_sha256),
            ("schema", self.schema_sha256),
        )


@dataclass(frozen=True, slots=True)
class PackageDependencyPins:
    """Trusted identities for a validated package-output work product."""

    preflight_sha256: str
    ir_sha256: str
    schema_sha256: str
    corpus_sha256: str
    execution_plan_sha256: str
    report_schema_sha256: str

    def as_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return the exact stable package dependency set."""
        return (
            ("corpus", self.corpus_sha256),
            ("execution_plan", self.execution_plan_sha256),
            ("ir", self.ir_sha256),
            ("preflight", self.preflight_sha256),
            ("report_schema", self.report_schema_sha256),
            ("schema", self.schema_sha256),
        )


type ExpectedDependencyPins = DependencyPins | PackageDependencyPins


@dataclass(frozen=True, slots=True)
class BindingDiagnostic:
    """One deterministic contract or provenance failure."""

    code: str
    path: str
    context: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class BindingResult:
    """Result of checking dependency pins and evidence anchors."""

    diagnostics: tuple[BindingDiagnostic, ...]
    dependency_digests: tuple[tuple[str, str], ...]
    anchors_checked: int
    contract_revision: str | None
    validated_artifact_identity: ArtifactIdentityAttestation | None
    validated_evidence_members: tuple[EvidenceMemberAttestation, ...]
    validated_evidence_anchors: tuple[EvidenceAnchorAttestation, ...]


@dataclass(frozen=True, slots=True)
class EvidenceMemberAttestation:
    """One exact report member whose ownership and digest were validated."""

    member: str
    owner: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"member": self.member, "owner": self.owner, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ArtifactIdentityAttestation:
    """Exact application identity parsed from the pinned preflight manifest."""

    package_name: str
    version_code: str
    version_name: str
    artifact_digest: str

    def to_dict(self) -> dict[str, str]:
        return {
            "artifact_digest": self.artifact_digest,
            "package_name": self.package_name,
            "version_code": self.version_code,
            "version_name": self.version_name,
        }


@dataclass(frozen=True, slots=True)
class EvidenceAnchorAttestation:
    """One exact evidence reproduction proven against the pinned IR."""

    id: str
    owner: str
    member: str
    member_sha256: str
    start_byte: int
    end_byte: int
    ir_pointer: str
    representation: str
    value_sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "end_byte": self.end_byte,
            "id": self.id,
            "ir_pointer": self.ir_pointer,
            "member": self.member,
            "member_sha256": self.member_sha256,
            "owner": self.owner,
            "representation": self.representation,
            "start_byte": self.start_byte,
            "value_sha256": self.value_sha256,
        }


type JsonObject = dict[str, object]
type RangeReader = Callable[[str, int, int], bytes]
type PathValidator = Callable[[str], bool]


def _dependency_contract(
    pins: ExpectedDependencyPins,
) -> tuple[str, tuple[str, ...]]:
    if isinstance(pins, PackageDependencyPins):
        return PACKAGE_CONTRACT_REVISION, _PACKAGE_DEPENDENCY_NAMES
    return CONTRACT_REVISION, _DEPENDENCY_NAMES


def validate_binding_contract(
    document: object,
    *,
    expected_dependencies: ExpectedDependencyPins,
    expected_evidence_lineage: EvidenceLineageTrust | None,
    nodes: Mapping[str, MemberNode],
    json_documents: Mapping[str, object],
    path_is_safe: PathValidator,
    read_range: RangeReader,
) -> BindingResult:
    """Validate one closed, protocol-neutral provenance contract."""
    expected_contract_revision, dependency_names = _dependency_contract(
        expected_dependencies
    )
    pins = expected_dependencies.as_pairs() + (
        (("evidence_lineage", expected_evidence_lineage.expected_manifest_sha256),)
        if expected_evidence_lineage is not None
        else ()
    )
    diagnostics: list[BindingDiagnostic] = []
    for name, digest in pins:
        if _DIGEST.fullmatch(digest) is None:
            diagnostics.append(
                BindingDiagnostic(
                    "EXPECTED_DEPENDENCY_DIGEST_INVALID",
                    VALIDATION_INPUT,
                    (("dependency", name),),
                )
            )
    if diagnostics:
        return _result(diagnostics, pins, 0, None, None, (), ())

    if not isinstance(document, dict):
        return _result(
            [
                BindingDiagnostic(
                    "VALIDATION_INPUT_INVALID", VALIDATION_INPUT, (("reason", "root"),)
                )
            ],
            pins,
            0,
            None,
            None,
            (),
            (),
        )
    expected_keys = {"contract_revision", "dependencies", "evidence_members", "anchors"}
    if set(document) != expected_keys:
        return _result(
            [
                BindingDiagnostic(
                    "VALIDATION_INPUT_INVALID",
                    VALIDATION_INPUT,
                    (("reason", "top_level_keys"),),
                )
            ],
            pins,
            0,
            None,
            None,
            (),
            (),
        )
    if document["contract_revision"] != expected_contract_revision:
        diagnostics.append(
            BindingDiagnostic(
                "VALIDATION_CONTRACT_REVISION_MISMATCH",
                VALIDATION_INPUT,
            )
        )
    contract_revision = (
        document["contract_revision"] if isinstance(document["contract_revision"], str) else None
    )

    dependencies = document["dependencies"]
    if not isinstance(dependencies, dict) or set(dependencies) != set(dependency_names):
        diagnostics.append(BindingDiagnostic("DEPENDENCY_SET_MISMATCH", VALIDATION_INPUT))
    else:
        _validate_dependencies(
            dependencies,
            dict(pins),
            nodes,
            path_is_safe,
            diagnostics,
            dependency_names,
        )
    ir_document = _dependency_document(dependencies, "ir", json_documents)
    schema = _dependency_document(dependencies, "schema", json_documents)
    _validate_current_ir_and_schema(ir_document, schema, dependencies, diagnostics)
    preflight_document = _dependency_document(dependencies, "preflight", json_documents)
    artifact_identity = _validate_preflight_identity(
        preflight_document,
        _dependency_member(dependencies, "preflight"),
        diagnostics,
    )
    trusted_evidence, trusted_evidence_scopes = _validate_evidence_lineage(
        expected_evidence_lineage,
        expected_dependencies,
        artifact_identity,
        preflight_document,
        nodes,
        path_is_safe,
        diagnostics,
    )
    _validate_frozen_report_members(nodes, diagnostics)
    package_contract = isinstance(expected_dependencies, PackageDependencyPins)
    if package_contract:
        _validate_package_dependency_documents(dependencies, json_documents, diagnostics)
    else:
        _validate_frozen_analysis_report(
            json_documents.get("analysis.json"), artifact_identity, diagnostics
        )

    package_domains = (
        _package_required_domains(dependencies, json_documents) if package_contract else None
    )
    owners, validated_members, evidence_scopes = _validate_evidence_members(
        document["evidence_members"],
        artifact_identity.artifact_digest if artifact_identity is not None else "",
        trusted_evidence,
        frozenset(_dependency_members(dependencies, dependency_names)),
        nodes,
        path_is_safe,
        diagnostics,
        package_domains=package_domains,
        trusted_scopes=trusted_evidence_scopes,
    )
    validated_anchors = _validate_anchors(
        document["anchors"],
        owners,
        {item.member: item for item in validated_members},
        nodes,
        ir_document,
        read_range,
        diagnostics,
    )
    if package_contract:
        _validate_package_report(
            dependencies,
            json_documents,
            artifact_identity,
            trusted_evidence,
            evidence_scopes,
            frozenset(
                [item.sha256 for item in validated_members]
                + [item.value_sha256 for item in validated_anchors]
            ),
            diagnostics,
        )
    return _result(
        diagnostics,
        pins,
        len(validated_anchors),
        contract_revision,
        artifact_identity,
        validated_members,
        validated_anchors,
    )


def _validate_frozen_report_members(
    nodes: Mapping[str, MemberNode], diagnostics: list[BindingDiagnostic]
) -> None:
    for member in sorted(_REQUIRED_FROZEN_REPORT_MEMBERS):
        node = nodes.get(member)
        if node is None or node.kind != "file" or node.size == 0 or node.sha256 is None:
            diagnostics.append(BindingDiagnostic("FROZEN_REPORT_MEMBER_MISSING", member))
    if not any(
        member.startswith("reproducers/")
        and node.kind == "file"
        and node.size > 0
        and node.sha256 is not None
        for member, node in nodes.items()
    ):
        diagnostics.append(BindingDiagnostic("FROZEN_REPORT_REPRODUCER_MISSING", "reproducers"))


def _validate_frozen_analysis_report(
    report: object,
    artifact_identity: ArtifactIdentityAttestation | None,
    diagnostics: list[BindingDiagnostic],
) -> None:
    report_path = "analysis.json"
    if not isinstance(report, dict) or report.get("status") != "COMPLETE":
        diagnostics.append(BindingDiagnostic("FROZEN_REPORT_ANALYSIS_INVALID", report_path))
        return
    if not _ANALYSIS_VALIDATOR.is_valid(report):
        diagnostics.append(BindingDiagnostic("FROZEN_REPORT_ANALYSIS_INVALID", report_path))
        return
    artifact = cast(dict[str, object], report["artifact"])
    if artifact_identity is None or (
        artifact.get("package_id"),
        artifact.get("version_code"),
        artifact.get("version_name"),
        artifact.get("artifact_set_sha256"),
    ) != (
        artifact_identity.package_name,
        artifact_identity.version_code,
        artifact_identity.version_name,
        artifact_identity.artifact_digest,
    ):
        diagnostics.append(BindingDiagnostic("FROZEN_REPORT_IDENTITY_MISMATCH", report_path))


def _validate_current_ir_and_schema(
    ir_document: object | None,
    pinned_schema: object | None,
    dependencies: object,
    diagnostics: list[BindingDiagnostic],
) -> None:
    ir_member = _dependency_member(dependencies, "ir")
    schema_member = _dependency_member(dependencies, "schema")
    if ir_document is None:
        diagnostics.append(BindingDiagnostic("PINNED_IR_INVALID", ir_member))
    else:
        try:
            parsed_ir = _parse_ir_structure(ir_document)
            universe = validate_universe(parsed_ir)
            if universe.issues:
                first = universe.issues[0]
                diagnostics.append(
                    BindingDiagnostic(
                        "PINNED_IR_INVALID",
                        ir_member,
                        (("ir_code", first.code),),
                    )
                )
            else:
                _validate_exact_evidence_coverage(parsed_ir)
        except IRValidationError as error:
            context: tuple[tuple[str, str], ...] = ()
            if error.diagnostics:
                first = error.diagnostics[0]
                context = (("ir_code", first.code), ("ir_path", first.path))
            diagnostics.append(BindingDiagnostic("PINNED_IR_INVALID", ir_member, context))

    current_schema = schema_document()
    pinned_revision = _schema_revision(pinned_schema)
    if pinned_revision != SCHEMA_REVISION:
        diagnostics.append(
            BindingDiagnostic(
                "PINNED_SCHEMA_REVISION_MISMATCH",
                schema_member,
                (("expected", SCHEMA_REVISION),),
            )
        )
    if pinned_schema != current_schema:
        diagnostics.append(BindingDiagnostic("PINNED_SCHEMA_STRUCTURE_MISMATCH", schema_member))


def _schema_revision(document: object | None) -> object | None:
    if not isinstance(document, dict):
        return None
    properties = document.get("properties")
    if not isinstance(properties, dict):
        return None
    revision = properties.get("schema_revision")
    return revision.get("const") if isinstance(revision, dict) else None


def _validate_preflight_identity(
    document: object | None,
    member: str,
    diagnostics: list[BindingDiagnostic],
) -> ArtifactIdentityAttestation | None:
    if not _is_exact_object(
        document,
        {
            "schema",
            "delivery_digest",
            "artifact_digest",
            "delivery_files",
            "artifact_members",
            "package_identity",
            "classification",
        },
    ):
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_INVALID", member))
        return None
    schema = document["schema"]
    if schema == _LEGACY_PREFLIGHT_SCHEMA:
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_NOT_READY", member))
        return None
    if schema != PREFLIGHT_SCHEMA:
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_INVALID", member))
        return None
    if (
        not _is_digest(document["delivery_digest"])
        or not _is_digest(document["artifact_digest"])
        or not _valid_preflight_files(document["delivery_files"])
        or not _valid_preflight_files(document["artifact_members"], require_apk=True)
        or document["delivery_digest"]
        != _preflight_manifest_digest("delivery", cast(list[object], document["delivery_files"]))
        or document["artifact_digest"]
        != _preflight_manifest_digest("artifact", cast(list[object], document["artifact_members"]))
    ):
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_INVALID", member))
        return None
    artifact_files = cast(list[dict[str, object]], document["artifact_members"])
    if not _valid_preflight_classification(document["classification"], artifact_files):
        diagnostics.append(
            BindingDiagnostic("PINNED_PREFLIGHT_CLASSIFICATION_INVALID", member)
        )
        return None
    classification = cast(dict[str, object], document["classification"])
    if classification["status"] != "READY" or classification["blockers"] != []:
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_NOT_READY", member))
        return None
    identity = document["package_identity"]
    if not _is_exact_object(
        identity,
        {
            "package_name",
            "version_code",
            "version_name",
            "signer_sha256",
            "base_member",
            "split_members",
        },
    ):
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_IDENTITY_INVALID", member))
        return None
    package_name = identity["package_name"]
    version_code = identity["version_code"]
    version_name = identity["version_name"]
    signers = identity["signer_sha256"]
    base_member = identity["base_member"]
    split_members = identity["split_members"]
    if (
        not isinstance(package_name, str)
        or _PACKAGE_NAME.fullmatch(package_name) is None
        or not isinstance(version_code, str)
        or not version_code
        or not isinstance(version_name, str)
        or not version_name
        or len(version_name) > 256
        or len(version_code) > 256
        or not isinstance(base_member, str)
        or not base_member
        or not isinstance(signers, list)
        or not signers
        or any(not _is_digest(item) for item in signers)
        or not isinstance(split_members, list)
        or any(
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) and part for part in item)
            for item in split_members
        )
    ):
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_IDENTITY_INVALID", member))
        return None
    typed_signers = cast(list[str], signers)
    typed_splits = cast(list[list[str]], split_members)
    artifact_names = {cast(str, item["name"]) for item in artifact_files}
    if (
        typed_signers != sorted(set(typed_signers))
        or base_member not in artifact_names
        or base_member in {item[1] for item in typed_splits}
        or typed_splits != sorted(typed_splits)
        or len({item[0] for item in typed_splits}) != len(typed_splits)
        or len({item[1] for item in typed_splits}) != len(typed_splits)
        or any(item[1] not in artifact_names for item in typed_splits)
        or {base_member, *(item[1] for item in typed_splits)} != artifact_names
    ):
        diagnostics.append(BindingDiagnostic("PINNED_PREFLIGHT_IDENTITY_INVALID", member))
        return None
    return ArtifactIdentityAttestation(
        package_name=package_name,
        version_code=version_code,
        version_name=version_name,
        artifact_digest=cast(str, document["artifact_digest"]),
    )


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _preflight_manifest_digest(domain: str, items: list[object]) -> str:
    encoded = (
        json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
    digest = hashlib.sha256()
    digest.update(domain.encode())
    digest.update(b"\0")
    digest.update(encoded)
    return digest.hexdigest()


def _valid_preflight_files(value: object, *, require_apk: bool = False) -> bool:
    if not isinstance(value, list) or not value:
        return False
    names: list[str] = []
    for item in value:
        if not _is_exact_object(item, {"name", "size", "sha256"}):
            return False
        if (
            not isinstance(item["name"], str)
            or not item["name"]
            or not _valid_preflight_member_name(item["name"], require_apk=require_apk)
            or not isinstance(item["size"], int)
            or isinstance(item["size"], bool)
            or item["size"] < 0
            or not _is_digest(item["sha256"])
        ):
            return False
        names.append(cast(str, item["name"]))
    return len({name.casefold() for name in names}) == len(names) and names == sorted(
        names, key=str.casefold
    )


def _valid_preflight_member_name(value: str, *, require_apk: bool) -> bool:
    candidate = PurePosixPath(value)
    return (
        "\\" not in value
        and "\x00" not in value
        and "\r" not in value
        and "\n" not in value
        and not candidate.is_absolute()
        and value == candidate.as_posix()
        and bool(candidate.parts)
        and all(part not in {"", ".", ".."} for part in candidate.parts)
        and (not require_apk or value.casefold().endswith(".apk"))
    )


def _valid_preflight_classification(
    value: object, artifact_files: list[dict[str, object]]
) -> bool:
    if not _is_exact_object(value, {"stacks", "routes", "status", "blockers", "members"}):
        return False
    stacks = _canonical_string_list(value["stacks"], require_nonempty=True)
    routes = _canonical_string_list(value["routes"], require_nonempty=True)
    blockers = _canonical_string_list(value["blockers"])
    members = value["members"]
    status = value["status"]
    if (
        stacks is None
        or routes is None
        or blockers is None
        or status not in {"READY", "BLOCKED"}
        or not isinstance(members, list)
        or not members
    ):
        return False
    parsed_members: list[tuple[str, tuple[str, ...], tuple[str, ...], str, tuple[str, ...]]] = []
    for item in members:
        parsed = _valid_preflight_member_classification(item)
        if parsed is None:
            return False
        parsed_members.append(parsed)
    names = [item[0] for item in parsed_members]
    artifact_names = [cast(str, item["name"]) for item in artifact_files]
    if names != artifact_names:
        return False
    aggregate_stacks = tuple(sorted({stack for _, item, _, _, _ in parsed_members for stack in item}))
    aggregate_routes = tuple(sorted({route for _, _, item, _, _ in parsed_members for route in item}))
    member_blockers = {blocker for _, _, _, _, item in parsed_members for blocker in item}
    coherent = (status == "READY") == (not blockers)
    return (
        tuple(stacks) == aggregate_stacks
        and tuple(routes) == aggregate_routes
        and set(blockers).issuperset(member_blockers)
        and coherent
        and all((member_status == "READY") == (not item_blockers) for *_, member_status, item_blockers in parsed_members)
    )


def _valid_preflight_member_classification(
    value: object,
) -> tuple[str, tuple[str, ...], tuple[str, ...], str, tuple[str, ...]] | None:
    if not _is_exact_object(value, {"name", "stacks", "routes", "status", "blockers"}):
        return None
    name = value["name"]
    stacks = _canonical_string_list(value["stacks"], require_nonempty=True)
    routes = _canonical_string_list(value["routes"], require_nonempty=True)
    blockers = _canonical_string_list(value["blockers"])
    status = value["status"]
    if (
        not isinstance(name, str)
        or not name
        or stacks is None
        or routes is None
        or blockers is None
        or status not in {"READY", "BLOCKED"}
        or any(stack not in _STACK_ROUTES for stack in stacks)
    ):
        return None
    expected_routes = tuple(
        sorted({route for stack in stacks for route in _STACK_ROUTES[stack]})
    )
    if tuple(routes) != expected_routes:
        return None
    return name, tuple(stacks), tuple(routes), cast(str, status), tuple(blockers)


def _canonical_string_list(
    value: object, *, require_nonempty: bool = False
) -> list[str] | None:
    if not _is_string_list(value):
        return None
    typed = cast(list[str], value)
    if require_nonempty and not typed:
        return None
    if any(not item for item in typed) or typed != sorted(set(typed)):
        return None
    return typed


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_dependencies(
    dependencies: JsonObject,
    expected: dict[str, str],
    nodes: Mapping[str, MemberNode],
    path_is_safe: PathValidator,
    diagnostics: list[BindingDiagnostic],
    dependency_names: tuple[str, ...],
) -> None:
    for name in dependency_names:
        value = dependencies[name]
        if not _is_exact_object(value, {"member", "sha256"}):
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_ENTRY_INVALID",
                    VALIDATION_INPUT,
                    (("dependency", name),),
                )
            )
            continue
        member = value["member"]
        digest = value["sha256"]
        if not isinstance(member, str) or not path_is_safe(member):
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_MEMBER_PATH_INVALID",
                    VALIDATION_INPUT,
                    (("dependency", name),),
                )
            )
            continue
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_DIGEST_INVALID",
                    member,
                    (("dependency", name),),
                )
            )
            continue
        if digest != expected[name]:
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_PIN_MISMATCH",
                    member,
                    (("dependency", name),),
                )
            )
        node = nodes.get(member)
        if node is None:
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_MEMBER_MISSING",
                    member,
                    (("dependency", name),),
                )
            )
        elif node.kind != "file":
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_MEMBER_NOT_REGULAR",
                    member,
                    (("dependency", name),),
                )
            )
        elif node.sha256 != digest:
            diagnostics.append(
                BindingDiagnostic(
                    "DEPENDENCY_MEMBER_DIGEST_MISMATCH",
                    member,
                    (("dependency", name),),
                )
            )


def _validate_evidence_lineage(
    trust: EvidenceLineageTrust | None,
    expected_dependencies: ExpectedDependencyPins,
    artifact_identity: ArtifactIdentityAttestation | None,
    preflight_document: object | None,
    nodes: Mapping[str, MemberNode],
    path_is_safe: PathValidator,
    diagnostics: list[BindingDiagnostic],
) -> tuple[dict[str, str], dict[str, frozenset[str]]]:
    if trust is None:
        diagnostics.append(
            BindingDiagnostic("TRUSTED_EVIDENCE_LINEAGE_REQUIRED", VALIDATION_INPUT)
        )
        return {}, {}
    if artifact_identity is None:
        return {}, {}
    artifact_sources = _preflight_artifact_sources(preflight_document)
    member_routes = _preflight_member_routes(preflight_document)
    if artifact_sources is None or member_routes is None:
        return {}, {}
    try:
        value = bind_evidence_lineage(
            trust.payload,
            expected_manifest_sha256=trust.expected_manifest_sha256,
            expected_artifact_digest=artifact_identity.artifact_digest,
            expected_preflight_sha256=expected_dependencies.preflight_sha256,
            expected_source_artifacts=artifact_sources,
            trusted_producers=trust.trusted_producers,
        )
    except LineageValidationError as error:
        diagnostics.append(
            BindingDiagnostic(
                "TRUSTED_EVIDENCE_LINEAGE_INVALID",
                VALIDATION_INPUT,
                (
                    ("lineage_code", error.diagnostic.code),
                    ("lineage_path", error.diagnostic.path),
                ),
            )
        )
        return {}, {}
    covered_routes: set[tuple[str, str]] = set()
    for item in value.members:
        node = nodes.get(item.report_member)
        if (
            node is None
            or node.kind != "file"
            or node.sha256 != item.sha256
            or node.size != item.producer.output_size
        ):
            diagnostics.append(
                BindingDiagnostic(
                    "TRUSTED_EVIDENCE_LINEAGE_COMPLETION_OUTPUT_INVALID",
                    item.report_member,
                )
            )
            return {}, {}
        if any(
            item.producer.route not in member_routes.get(source.name, frozenset())
            for source in item.source_artifact_members
        ):
            diagnostics.append(
                BindingDiagnostic(
                    "TRUSTED_EVIDENCE_LINEAGE_ROUTE_MISMATCH", item.report_member
                )
            )
            return {}, {}
        covered_routes.update(
            (source.name, item.producer.route) for source in item.source_artifact_members
        )
        if any(
            artifact_sources.get(source.name) != source.sha256
            for source in item.source_artifact_members
        ):
            diagnostics.append(
                BindingDiagnostic(
                    "TRUSTED_EVIDENCE_LINEAGE_SOURCE_MISMATCH", item.report_member
                )
            )
            return {}, {}
    required_routes = {
        (member, route) for member, routes in member_routes.items() for route in routes
    }
    missing_routes = sorted(required_routes - covered_routes)
    if missing_routes:
        missing_member, missing_route = missing_routes[0]
        diagnostics.append(
            BindingDiagnostic(
                "TRUSTED_EVIDENCE_LINEAGE_ROUTE_COVERAGE_INCOMPLETE",
                VALIDATION_INPUT,
                (("member", missing_member), ("route", missing_route)),
            )
        )
        return {}, {}
    if len(value.members) > _MAX_EVIDENCE_MEMBER_COUNT:
        diagnostics.append(
            BindingDiagnostic("TRUSTED_EVIDENCE_MEMBER_LIMIT_EXCEEDED", VALIDATION_INPUT)
        )
        return {}, {}
    trusted: dict[str, str] = {}
    scopes: dict[str, frozenset[str]] = {}
    for member, digest in value.member_digests:
        if not isinstance(member, str) or not path_is_safe(member) or not _is_digest(digest):
            diagnostics.append(
                BindingDiagnostic("TRUSTED_EVIDENCE_MEMBER_INVALID", VALIDATION_INPUT)
            )
            continue
        if not member.startswith("evidence/") or member == "evidence/":
            diagnostics.append(BindingDiagnostic("TRUSTED_EVIDENCE_NAMESPACE_INVALID", member))
            continue
        trusted[member] = digest
    scopes.update(
        (item.report_member, frozenset(item.package_local_domains))
        for item in value.members
        if item.report_member in trusted
    )
    return trusted, scopes


def _validate_package_dependency_documents(
    dependencies: object,
    json_documents: Mapping[str, object],
    diagnostics: list[BindingDiagnostic],
) -> None:
    for name, code in (
        ("execution_plan", "PINNED_EXECUTION_PLAN_INVALID"),
        ("report_schema", "PINNED_REPORT_SCHEMA_INVALID"),
    ):
        member = _dependency_member(dependencies, name)
        if member not in json_documents:
            diagnostics.append(BindingDiagnostic(code, member))


def _validate_package_report(
    dependencies: object,
    json_documents: Mapping[str, object],
    artifact_identity: ArtifactIdentityAttestation | None,
    trusted_evidence: Mapping[str, str],
    evidence_scopes: Mapping[str, frozenset[str]],
    trusted_semantic_roots: frozenset[str],
    diagnostics: list[BindingDiagnostic],
) -> None:
    schema_member = _dependency_member(dependencies, "report_schema")
    schema = _dependency_document(dependencies, "report_schema", json_documents)
    if not isinstance(schema, dict) or set(schema) != {
        "report_revision",
        "package_local_domain_result_schema",
        "required_package_local_domains",
        "requires_authoritative_root_result_set",
        "requires_target_package_identity",
        "schema_revision",
    }:
        diagnostics.append(BindingDiagnostic("PINNED_REPORT_SCHEMA_INVALID", schema_member))
        return
    report_revision = schema.get("report_revision")
    schema_revision = schema.get("schema_revision")
    required_domains = _canonical_string_list(
        schema.get("required_package_local_domains"), require_nonempty=True
    )
    if (
        not isinstance(report_revision, str)
        or not report_revision
        or not isinstance(schema_revision, str)
        or not schema_revision
        or schema.get("package_local_domain_result_schema")
        != PACKAGE_LOCAL_DOMAIN_RESULT_SCHEMA
        or required_domains is None
        or schema.get("requires_authoritative_root_result_set") is not True
        or schema.get("requires_target_package_identity") is not True
    ):
        diagnostics.append(BindingDiagnostic("PINNED_REPORT_SCHEMA_INVALID", schema_member))
        return

    report_path = "analysis.json"
    report = json_documents.get(report_path)
    execution_plan = _dependency_document(dependencies, "execution_plan", json_documents)
    execution_plan_member = _dependency_member(dependencies, "execution_plan")
    package_local = (
        execution_plan.get("package_local") if isinstance(execution_plan, dict) else None
    )
    root_count = (
        execution_plan.get("authoritative_root_count") if isinstance(execution_plan, dict) else None
    )
    root_plans = execution_plan.get("root_plans") if isinstance(execution_plan, dict) else None
    if (
        not isinstance(package_local, dict)
        or type(root_count) is not int
        or root_count < 0
        or package_local.get("mandatory_domains") != list(required_domains)
        or not isinstance(root_plans, list)
        or len(root_plans) != root_count
    ):
        diagnostics.append(
            BindingDiagnostic("PINNED_EXECUTION_PLAN_INVALID", execution_plan_member)
        )
        return
    planned_roots = tuple(_root_plan_identity(item) for item in root_plans)
    if any(item is None for item in planned_roots) or len(set(planned_roots)) != root_count:
        diagnostics.append(
            BindingDiagnostic("PINNED_EXECUTION_PLAN_INVALID", execution_plan_member)
        )
        return
    if not isinstance(report, dict):
        diagnostics.append(BindingDiagnostic("PACKAGE_REPORT_INVALID", report_path))
        return
    identity = report.get("target_package_identity")
    domains = report.get("package_local_domains")
    root_results = report.get("authoritative_root_results")
    if (
        report.get("report_revision") != report_revision
        or not isinstance(identity, dict)
        or set(identity) != {"artifact_digest", "package_name", "version_code", "version_name"}
        or not isinstance(domains, dict)
        or set(domains) != set(required_domains)
        or not isinstance(root_results, list)
        or any(
            not _valid_package_local_domain_result(
                name, domains[name], trusted_evidence, evidence_scopes
            )
            for name in required_domains
        )
        or len(root_results) != root_count
        or any(_root_result_identity(item) is None for item in root_results)
    ):
        diagnostics.append(BindingDiagnostic("PACKAGE_REPORT_INVALID", report_path))
        return
    reported_roots = tuple(_root_result_identity(item) for item in root_results)
    if set(reported_roots) != set(planned_roots):
        diagnostics.append(BindingDiagnostic("PACKAGE_REPORT_ROOT_SET_MISMATCH", report_path))
        return
    for index, root_result in enumerate(root_results):
        if not isinstance(root_result, dict) or root_result.get("route") != "FULL_ANALYSIS":
            continue
        result = cast(dict[str, object], root_result["result"])
        analysis = cast(dict[str, object], result["analysis"])
        semantic_root = cast(str, analysis["semantic_root_sha256"])
        if semantic_root not in trusted_semantic_roots:
            diagnostics.append(
                BindingDiagnostic(
                    "PACKAGE_REPORT_FULL_ANALYSIS_UNATTESTED",
                    f"{report_path}#/authoritative_root_results/{index}",
                )
            )
    plan_identity = {
        "artifact_digest": package_local.get("target_artifact_digest"),
        "package_name": package_local.get("package_name"),
        "version_code": package_local.get("version_code"),
        "version_name": package_local.get("version_name"),
    }
    if (
        artifact_identity is None
        or identity != artifact_identity.to_dict()
        or identity != plan_identity
    ):
        diagnostics.append(BindingDiagnostic("PACKAGE_REPORT_IDENTITY_MISMATCH", report_path))


def _valid_package_local_domain_result(
    domain: str,
    value: object,
    trusted_evidence: Mapping[str, str],
    evidence_scopes: Mapping[str, frozenset[str]],
) -> bool:
    if not _is_exact_object(value, {"evidence", "status"}) or value["status"] != "COMPLETE":
        return False
    evidence = _canonical_string_list(value["evidence"], require_nonempty=True)
    return evidence is not None and all(
        member in trusted_evidence and domain in evidence_scopes.get(member, frozenset())
        for member in evidence
    )


def _package_required_domains(
    dependencies: object, json_documents: Mapping[str, object]
) -> frozenset[str]:
    schema = _dependency_document(dependencies, "report_schema", json_documents)
    if not isinstance(schema, dict):
        return frozenset()
    domains = _canonical_string_list(
        schema.get("required_package_local_domains"), require_nonempty=True
    )
    return frozenset(domains or ())


def _root_plan_identity(
    value: object,
) -> tuple[str, str, str, str | None, str | None] | None:
    if not isinstance(value, dict):
        return None
    route = value.get("route")
    identity = value.get("reuse") if route == "EXACT_REUSE" else value
    if route not in {"BLOCKED", "EXACT_REUSE", "FULL_ANALYSIS"} or not isinstance(
        identity, dict
    ):
        return None
    root_id = identity.get("target_root_id")
    occurrence = identity.get("target_occurrence_identity_sha256")
    source_root_id = identity.get("source_root_id") if route == "EXACT_REUSE" else None
    semantic_root = (
        identity.get("inherited_semantic_root_sha256") if route == "EXACT_REUSE" else None
    )
    if (
        not _is_digest(root_id)
        or not _is_digest(occurrence)
        or (route == "EXACT_REUSE" and not _is_digest(source_root_id))
        or (route == "EXACT_REUSE" and not _is_digest(semantic_root))
    ):
        return None
    return (
        cast(str, root_id),
        cast(str, occurrence),
        cast(str, route),
        cast(str | None, source_root_id),
        cast(str | None, semantic_root),
    )


def _root_result_identity(
    value: object,
) -> tuple[str, str, str, str | None, str | None] | None:
    if not isinstance(value, dict) or set(value) != {
        "result",
        "route",
        "target_occurrence_identity_sha256",
        "target_root_id",
    }:
        return None
    result = value.get("result")
    route = value.get("route")
    root_id = value.get("target_root_id")
    occurrence = value.get("target_occurrence_identity_sha256")
    if (
        route not in {"BLOCKED", "EXACT_REUSE", "FULL_ANALYSIS"}
        or not _valid_root_result(route, result)
        or not _is_digest(root_id)
        or not _is_digest(occurrence)
    ):
        return None
    reuse = result.get("reuse") if route == "EXACT_REUSE" and isinstance(result, dict) else None
    return (
        cast(str, root_id),
        cast(str, occurrence),
        cast(str, route),
        cast(str, reuse["source_root_id"]) if isinstance(reuse, dict) else None,
        (
            cast(str, reuse["inherited_semantic_root_sha256"])
            if isinstance(reuse, dict)
            else None
        ),
    )


def _valid_root_result(route: object, result: object) -> bool:
    if route == "BLOCKED":
        return (
            _is_exact_object(result, {"blockers", "status"})
            and result["status"] == "BLOCKED"
            and _canonical_string_list(result["blockers"], require_nonempty=True) is not None
        )
    if route == "FULL_ANALYSIS":
        return (
            _is_exact_object(result, {"analysis", "status"})
            and result["status"] == "COMPLETE"
            and _is_exact_object(result["analysis"], {"semantic_root_sha256"})
            and _is_digest(result["analysis"]["semantic_root_sha256"])
        )
    if route == "EXACT_REUSE":
        return (
            _is_exact_object(result, {"reuse", "status"})
            and result["status"] == "COMPLETE"
            and _is_exact_object(
                result["reuse"],
                {"inherited_semantic_root_sha256", "source_root_id"},
            )
            and _is_digest(result["reuse"]["inherited_semantic_root_sha256"])
            and _is_digest(result["reuse"]["source_root_id"])
        )
    return False


def _preflight_artifact_sources(document: object | None) -> dict[str, str] | None:
    if not isinstance(document, dict):
        return None
    members = document.get("artifact_members")
    if not _valid_preflight_files(members, require_apk=True):
        return None
    return {
        cast(str, item["name"]): cast(str, item["sha256"])
        for item in cast(list[dict[str, object]], members)
    }


def _preflight_member_routes(
    document: object | None,
) -> dict[str, frozenset[str]] | None:
    if not isinstance(document, dict):
        return None
    classification = document.get("classification")
    if not isinstance(classification, dict):
        return None
    members = classification.get("members")
    if not isinstance(members, list):
        return None
    result: dict[str, frozenset[str]] = {}
    for member in members:
        if not isinstance(member, dict):
            return None
        name = member.get("name")
        routes = _canonical_string_list(member.get("routes"), require_nonempty=True)
        if not isinstance(name, str) or routes is None or name in result:
            return None
        result[name] = frozenset(routes)
    return result


def _dependency_members(
    dependencies: object,
    dependency_names: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(_dependency_member(dependencies, name) for name in dependency_names)


def _validate_evidence_members(
    value: object,
    expected_owner: str,
    expected_members: Mapping[str, str],
    dependency_members: frozenset[str],
    nodes: Mapping[str, MemberNode],
    path_is_safe: PathValidator,
    diagnostics: list[BindingDiagnostic],
    *,
    package_domains: frozenset[str] | None,
    trusted_scopes: Mapping[str, frozenset[str]],
) -> tuple[
    dict[str, str],
    tuple[EvidenceMemberAttestation, ...],
    dict[str, frozenset[str]],
]:
    owners: dict[str, str] = {}
    scopes: dict[str, frozenset[str]] = {}
    validated: list[EvidenceMemberAttestation] = []
    if not isinstance(value, list):
        diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBERS_INVALID", VALIDATION_INPUT))
        return owners, (), scopes
    if len(value) > _MAX_EVIDENCE_MEMBER_COUNT:
        diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_LIMIT_EXCEEDED", VALIDATION_INPUT))
        return owners, (), scopes
    declared_members = {
        entry.get("member")
        for entry in value
        if isinstance(entry, dict) and isinstance(entry.get("member"), str)
    }
    if declared_members != set(expected_members):
        diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_SET_MISMATCH", VALIDATION_INPUT))
    for index, entry in enumerate(value):
        location = f"{VALIDATION_INPUT}#/evidence_members/{index}"
        required_keys = {"member", "owner", "sha256"}
        if package_domains is not None:
            required_keys.add("package_local_domains")
        if not _is_exact_object(entry, required_keys):
            diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_INVALID", location))
            continue
        member = entry["member"]
        owner = entry["owner"]
        digest = entry["sha256"]
        if (
            not isinstance(member, str)
            or not path_is_safe(member)
            or not isinstance(owner, str)
            or _DIGEST.fullmatch(owner) is None
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
        ):
            diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_INVALID", location))
            continue
        if member in owners:
            diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_DUPLICATE", member))
            continue
        owners[member] = owner
        member_valid = True
        member_scopes: frozenset[str] = frozenset()
        if package_domains is not None:
            declared_scopes = _canonical_string_list(entry["package_local_domains"])
            if (
                declared_scopes is None
                or not set(declared_scopes).issubset(package_domains)
                or frozenset(declared_scopes) != trusted_scopes.get(member)
            ):
                diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_INVALID", location))
                member_valid = False
            else:
                member_scopes = frozenset(declared_scopes)
        if not member.startswith("evidence/") or member == "evidence/":
            diagnostics.append(BindingDiagnostic("EVIDENCE_NAMESPACE_INVALID", member))
            member_valid = False
        if member in dependency_members:
            diagnostics.append(BindingDiagnostic("EVIDENCE_DEPENDENCY_OVERLAP", member))
            member_valid = False
        if expected_members.get(member) != digest:
            diagnostics.append(BindingDiagnostic("EVIDENCE_TRUST_PIN_MISMATCH", member))
            member_valid = False
        if owner != expected_owner:
            diagnostics.append(BindingDiagnostic("EVIDENCE_OWNER_PIN_MISMATCH", member))
            member_valid = False
        node = nodes.get(member)
        if node is None:
            diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_MISSING", member))
            member_valid = False
        elif node.kind != "file":
            diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_NOT_REGULAR", member))
            member_valid = False
        elif node.sha256 != digest:
            diagnostics.append(BindingDiagnostic("EVIDENCE_MEMBER_DIGEST_MISMATCH", member))
            member_valid = False
        if member_valid:
            validated.append(EvidenceMemberAttestation(member, owner, digest))
            scopes[member] = member_scopes
    return owners, tuple(sorted(validated, key=lambda item: item.member.encode())), scopes


def _validate_anchors(
    value: object,
    owners: Mapping[str, str],
    validated_members: Mapping[str, EvidenceMemberAttestation],
    nodes: Mapping[str, MemberNode],
    ir_document: object | None,
    read_range: RangeReader,
    diagnostics: list[BindingDiagnostic],
) -> tuple[EvidenceAnchorAttestation, ...]:
    if not isinstance(value, list) or not value:
        diagnostics.append(BindingDiagnostic("EVIDENCE_ANCHORS_INVALID", VALIDATION_INPUT))
        return ()
    if len(value) > _MAX_ANCHOR_COUNT:
        diagnostics.append(
            BindingDiagnostic(
                "EVIDENCE_ANCHOR_LIMIT_EXCEEDED",
                VALIDATION_INPUT,
                (("limit", str(_MAX_ANCHOR_COUNT)),),
            )
        )
        return ()
    cumulative_bytes = _anchor_byte_total(value)
    if cumulative_bytes > _MAX_ANCHOR_BYTES:
        diagnostics.append(
            BindingDiagnostic(
                "EVIDENCE_BYTE_BUDGET_EXCEEDED",
                VALIDATION_INPUT,
                (("limit", str(_MAX_ANCHOR_BYTES)),),
            )
        )
        return ()
    seen_ids: set[str] = set()
    attestations: list[EvidenceAnchorAttestation] = []
    for index, anchor in enumerate(value):
        location = f"{VALIDATION_INPUT}#/anchors/{index}"
        required = {
            "id",
            "owner",
            "member",
            "start_byte",
            "end_byte",
            "ir_pointer",
            "representation",
        }
        if not _is_exact_object(anchor, required):
            diagnostics.append(BindingDiagnostic("EVIDENCE_ANCHOR_INVALID", location))
            continue
        anchor_id = anchor["id"]
        owner = anchor["owner"]
        member = anchor["member"]
        start = anchor["start_byte"]
        end = anchor["end_byte"]
        ir_pointer = anchor["ir_pointer"]
        representation = anchor["representation"]
        if (
            not isinstance(anchor_id, str)
            or not anchor_id
            or len(anchor_id) > _MAX_ANCHOR_ID_LENGTH
            or not isinstance(owner, str)
            or _DIGEST.fullmatch(owner) is None
            or not isinstance(member, str)
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(ir_pointer, str)
            or len(ir_pointer) > _MAX_JSON_POINTER_LENGTH
            or not isinstance(representation, str)
            or representation not in {"hex", "utf8"}
        ):
            diagnostics.append(BindingDiagnostic("EVIDENCE_ANCHOR_INVALID", location))
            continue
        if anchor_id in seen_ids:
            diagnostics.append(BindingDiagnostic("EVIDENCE_ANCHOR_DUPLICATE_ID", anchor_id))
            continue
        seen_ids.add(anchor_id)
        declared_owner = owners.get(member)
        if declared_owner is None:
            diagnostics.append(
                BindingDiagnostic(
                    "EVIDENCE_ANCHOR_MEMBER_UNDECLARED", member, (("anchor", anchor_id),)
                )
            )
            continue
        if declared_owner != owner:
            diagnostics.append(
                BindingDiagnostic(
                    "EVIDENCE_ANCHOR_OWNER_MISMATCH", member, (("anchor", anchor_id),)
                )
            )
            continue
        validated_member = validated_members.get(member)
        if validated_member is None:
            continue
        node = nodes.get(member)
        if node is None or node.kind != "file":
            continue
        if start < 0 or end <= start:
            diagnostics.append(
                BindingDiagnostic("EVIDENCE_RANGE_INVALID", member, (("anchor", anchor_id),))
            )
            continue
        if end > node.size:
            diagnostics.append(
                BindingDiagnostic(
                    "EVIDENCE_RANGE_OUT_OF_BOUNDS",
                    member,
                    (("anchor", anchor_id),),
                )
            )
            continue
        try:
            source = read_range(member, start, end)
        except OSError as error:
            context = (("anchor", anchor_id),)
            if error.errno is not None:
                context += (("errno", str(error.errno)),)
            diagnostics.append(
                BindingDiagnostic("EVIDENCE_MEMBER_UNREADABLE", member, tuple(sorted(context)))
            )
            continue
        if representation == "hex":
            reproduced = source.hex()
        else:
            try:
                reproduced = source.decode("utf-8")
            except UnicodeDecodeError:
                diagnostics.append(
                    BindingDiagnostic("EVIDENCE_UTF8_INVALID", member, (("anchor", anchor_id),))
                )
                continue
        try:
            expected_value = _resolve_semantic_pointer(ir_document, ir_pointer)
        except IndexError, KeyError, TypeError, ValueError:
            diagnostics.append(
                BindingDiagnostic(
                    "EVIDENCE_IR_POINTER_INVALID",
                    member,
                    (("anchor", anchor_id),),
                )
            )
            continue
        if not isinstance(expected_value, (str, int, bool, dict, list)) or (
            isinstance(expected_value, (dict, list)) and expected_value
        ):
            diagnostics.append(
                BindingDiagnostic(
                    "EVIDENCE_IR_VALUE_NOT_SCALAR",
                    member,
                    (("anchor", anchor_id),),
                )
            )
            continue
        expected_rendering = (
            expected_value
            if isinstance(expected_value, str)
            else json.dumps(expected_value, sort_keys=True, separators=(",", ":"))
        )
        if reproduced != expected_rendering:
            diagnostics.append(
                BindingDiagnostic("EVIDENCE_VALUE_MISMATCH", member, (("anchor", anchor_id),))
            )
            continue
        attestations.append(
            EvidenceAnchorAttestation(
                id=anchor_id,
                owner=owner,
                member=member,
                member_sha256=validated_member.sha256,
                start_byte=start,
                end_byte=end,
                ir_pointer=ir_pointer,
                representation=representation,
                value_sha256=hashlib.sha256(
                    json.dumps(
                        expected_value,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest(),
            )
        )
    return tuple(sorted(attestations, key=lambda item: item.id.encode()))


def _anchor_byte_total(value: list[object]) -> int:
    total = 0
    for anchor in value:
        if not isinstance(anchor, dict):
            continue
        start = anchor.get("start_byte")
        end = anchor.get("end_byte")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
        ):
            continue
        total += end - start
        if total > _MAX_ANCHOR_BYTES:
            return total
    return total


def _is_exact_object(value: object, keys: set[str]) -> TypeGuard[JsonObject]:
    return isinstance(value, dict) and set(value) == keys


def _dependency_document(
    dependencies: object,
    name: str,
    json_documents: Mapping[str, object],
) -> object | None:
    if not isinstance(dependencies, dict):
        return None
    entry = dependencies.get(name)
    if not isinstance(entry, dict):
        return None
    member = entry.get("member")
    return json_documents.get(member) if isinstance(member, str) else None


def _dependency_member(dependencies: object, name: str) -> str:
    if isinstance(dependencies, dict):
        entry = dependencies.get(name)
        if isinstance(entry, dict):
            member = entry.get("member")
            if isinstance(member, str):
                return member
    return VALIDATION_INPUT


def _result(
    diagnostics: list[BindingDiagnostic],
    pins: tuple[tuple[str, str], ...],
    anchors_checked: int,
    contract_revision: str | None,
    validated_artifact_identity: ArtifactIdentityAttestation | None,
    validated_members: tuple[EvidenceMemberAttestation, ...],
    validated_anchors: tuple[EvidenceAnchorAttestation, ...],
) -> BindingResult:
    ordered = tuple(
        sorted(
            set(diagnostics),
            key=lambda item: (
                item.code,
                item.path.encode("utf-8", "surrogateescape"),
                item.context,
            ),
        )
    )
    return BindingResult(
        diagnostics=ordered,
        dependency_digests=pins,
        anchors_checked=anchors_checked,
        contract_revision=contract_revision,
        validated_artifact_identity=validated_artifact_identity,
        validated_evidence_members=validated_members,
        validated_evidence_anchors=validated_anchors,
    )
