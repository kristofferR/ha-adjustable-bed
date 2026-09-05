"""Closed final-domain model for the Phase 4 v2 protocol IR."""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, cast

from . import model as core

FINAL_SCHEMA_REVISION = "phase4-protocol-ir-v1.2.0-2026-09-03"
_MAX_DEFINITIONS = 250_000
_MAX_REFERENCES = 4_096
_MAX_DOMAIN_EXPANSIONS = 1_000_000


class SelectorKind(StrEnum):
    MODEL = "MODEL"
    VARIANT = "VARIANT"
    REMOTE_CODE = "REMOTE_CODE"
    CAPABILITY = "CAPABILITY"
    CONFIGURATION = "CONFIGURATION"
    USER_STATE = "USER_STATE"


class MatchField(StrEnum):
    DEVICE_NAME = "DEVICE_NAME"
    SERVICE_UUID = "SERVICE_UUID"
    MANUFACTURER_DATA = "MANUFACTURER_DATA"
    SERVICE_DATA = "SERVICE_DATA"


class MatchOperation(StrEnum):
    EQUALS = "EQUALS"
    PREFIX = "PREFIX"
    REGEX = "REGEX"
    PRESENT = "PRESENT"


class GattServiceRole(StrEnum):
    CONTROL = "CONTROL"
    TELEMETRY = "TELEMETRY"
    AUTHENTICATION = "AUTHENTICATION"
    AUXILIARY = "AUXILIARY"


class GattCharacteristicRole(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    NOTIFY = "NOTIFY"
    INDICATE = "INDICATE"
    AUTHENTICATION = "AUTHENTICATION"


class WriteMode(StrEnum):
    WITH_RESPONSE = "WITH_RESPONSE"
    WITHOUT_RESPONSE = "WITHOUT_RESPONSE"


class TransformOperation(StrEnum):
    IDENTITY = "IDENTITY"
    ADD = "ADD"
    XOR = "XOR"
    REVERSE = "REVERSE"
    LITTLE_ENDIAN = "LITTLE_ENDIAN"
    BIG_ENDIAN = "BIG_ENDIAN"
    LOOKUP = "LOOKUP"


class PacketFieldSource(StrEnum):
    CONSTANT = "CONSTANT"
    ACTION_PARAMETER = "ACTION_PARAMETER"
    SELECTOR = "SELECTOR"
    COUNTER = "COUNTER"
    CHECKSUM = "CHECKSUM"
    AUTHENTICATION = "AUTHENTICATION"


class ChecksumAlgorithm(StrEnum):
    SUM8 = "SUM8"
    XOR8 = "XOR8"
    CRC8 = "CRC8"
    CRC16 = "CRC16"
    CUSTOM = "CUSTOM"


class AuthenticationMethod(StrEnum):
    NONE = "NONE"
    PIN = "PIN"
    CHALLENGE_RESPONSE = "CHALLENGE_RESPONSE"
    SESSION_TOKEN = "SESSION_TOKEN"
    CUSTOM = "CUSTOM"


class BufferingMode(StrEnum):
    DATAGRAM = "DATAGRAM"
    FIXED_LENGTH = "FIXED_LENGTH"
    DELIMITER = "DELIMITER"
    LENGTH_PREFIXED = "LENGTH_PREFIXED"


class CancellationMode(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    AFTER_FRAME = "AFTER_FRAME"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class ReleaseMode(StrEnum):
    NONE = "NONE"
    STOP_ACTION = "STOP_ACTION"
    RELEASE_ACTION = "RELEASE_ACTION"
    END_REFRESH = "END_REFRESH"


class LifecyclePhase(StrEnum):
    CONNECT = "CONNECT"
    AUTHENTICATE = "AUTHENTICATE"
    START_NOTIFY = "START_NOTIFY"
    WRITE = "WRITE"
    STOP_NOTIFY = "STOP_NOTIFY"
    DISCONNECT = "DISCONNECT"


@dataclass(frozen=True, slots=True)
class SelectorDefinition:
    variant_space: str
    dimension: str
    kind: SelectorKind
    values: tuple[core.JsonScalar, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "variant_space": self.variant_space,
            "dimension": self.dimension,
            "kind": self.kind.value,
            "values": list(self.values),
        }


@dataclass(frozen=True, slots=True)
class DiscoveryMatcher:
    field: MatchField
    operation: MatchOperation
    value: str | None

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"field": self.field.value, "operation": self.operation.value}
        if self.value is not None:
            data["value"] = self.value
        return data


@dataclass(frozen=True, slots=True)
class SelectionRule:
    protocol: str
    when: core.Predicate

    def to_data(self) -> dict[str, object]:
        return {"protocol": self.protocol, "when": self.when.to_data()}


@dataclass(frozen=True, slots=True)
class DiscoveryRule:
    selection_rule: str
    matchers: tuple[DiscoveryMatcher, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "selection_rule": self.selection_rule,
            "matchers": [matcher.to_data() for matcher in self.matchers],
        }


@dataclass(frozen=True, slots=True)
class GattService:
    uuid: str
    role: GattServiceRole

    def to_data(self) -> dict[str, object]:
        return {"uuid": self.uuid, "role": self.role.value}


@dataclass(frozen=True, slots=True)
class GattCharacteristic:
    service: str
    uuid: str
    roles: tuple[GattCharacteristicRole, ...]
    write_modes: tuple[WriteMode, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "service": self.service,
            "uuid": self.uuid,
            "roles": [role.value for role in self.roles],
            "write_modes": [mode.value for mode in self.write_modes],
        }


@dataclass(frozen=True, slots=True)
class Transform:
    operation: TransformOperation
    operand: core.JsonScalar | None = None
    lookup: tuple[tuple[core.JsonScalar, core.JsonScalar], ...] = ()

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"operation": self.operation.value}
        if self.operand is not None:
            data["operand"] = self.operand
        if self.lookup:
            data["lookup"] = [list(item) for item in self.lookup]
        return data


@dataclass(frozen=True, slots=True)
class Checksum:
    algorithm: ChecksumAlgorithm
    start_byte: int
    end_byte: int
    output_width: int

    def to_data(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm.value,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "output_width": self.output_width,
        }


@dataclass(frozen=True, slots=True)
class Framing:
    prefix_hex: str
    suffix_hex: str
    length_field: str | None

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"prefix_hex": self.prefix_hex, "suffix_hex": self.suffix_hex}
        if self.length_field is not None:
            data["length_field"] = self.length_field
        return data


@dataclass(frozen=True, slots=True)
class PacketField:
    offset: int
    width: int
    source: PacketFieldSource
    source_ref: str | None
    constant_hex: str | None
    transforms: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {
            "offset": self.offset,
            "width": self.width,
            "source": self.source.value,
            "transforms": list(self.transforms),
        }
        if self.source_ref is not None:
            data["source_ref"] = self.source_ref
        if self.constant_hex is not None:
            data["constant_hex"] = self.constant_hex
        return data


@dataclass(frozen=True, slots=True)
class PacketBuilder:
    fields: tuple[str, ...]
    framing: str
    checksum: str | None

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"fields": list(self.fields), "framing": self.framing}
        if self.checksum is not None:
            data["checksum"] = self.checksum
        return data


@dataclass(frozen=True, slots=True)
class Authentication:
    method: AuthenticationMethod
    selectors: tuple[str, ...]
    request_builder: str | None
    response_parser: str | None

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {
            "method": self.method.value,
            "selectors": list(self.selectors),
        }
        if self.request_builder is not None:
            data["request_builder"] = self.request_builder
        if self.response_parser is not None:
            data["response_parser"] = self.response_parser
        return data


@dataclass(frozen=True, slots=True)
class Buffering:
    mode: BufferingMode
    size: int | None
    delimiter_hex: str | None

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"mode": self.mode.value}
        if self.size is not None:
            data["size"] = self.size
        if self.delimiter_hex is not None:
            data["delimiter_hex"] = self.delimiter_hex
        return data


@dataclass(frozen=True, slots=True)
class ParserField:
    offset: int
    width: int
    target_selector: str
    transforms: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "offset": self.offset,
            "width": self.width,
            "target_selector": self.target_selector,
            "transforms": list(self.transforms),
        }


@dataclass(frozen=True, slots=True)
class NotificationParser:
    buffering: str
    fields: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {"buffering": self.buffering, "fields": list(self.fields)}


@dataclass(frozen=True, slots=True)
class Timing:
    repeat_count: int
    repeat_interval_ms: int
    cancellation: CancellationMode
    release: ReleaseMode
    release_action: str | None

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {
            "repeat_count": self.repeat_count,
            "repeat_interval_ms": self.repeat_interval_ms,
            "cancellation": self.cancellation.value,
            "release": self.release.value,
        }
        if self.release_action is not None:
            data["release_action"] = self.release_action
        return data


@dataclass(frozen=True, slots=True)
class Lifecycle:
    phases: tuple[LifecyclePhase, ...]

    def to_data(self) -> dict[str, object]:
        return {"phases": [phase.value for phase in self.phases]}


@dataclass(frozen=True, slots=True)
class Transport:
    characteristic: str
    write_mode: WriteMode
    packet_builder: str
    notification_parser: str | None
    authentication: str | None
    timing: str
    lifecycle: str

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {
            "characteristic": self.characteristic,
            "write_mode": self.write_mode.value,
            "packet_builder": self.packet_builder,
            "timing": self.timing,
            "lifecycle": self.lifecycle,
        }
        if self.notification_parser is not None:
            data["notification_parser"] = self.notification_parser
        if self.authentication is not None:
            data["authentication"] = self.authentication
        return data


@dataclass(frozen=True, slots=True)
class ActionParameter:
    action: str
    values: tuple[core.JsonScalar, ...]

    def to_data(self) -> dict[str, object]:
        return {"action": self.action, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class ActionMapping:
    protocol: str
    action: str
    transport: str
    when: core.Predicate

    def to_data(self) -> dict[str, object]:
        return {
            "protocol": self.protocol,
            "action": self.action,
            "transport": self.transport,
            "when": self.when.to_data(),
        }


FINAL_DOMAIN_COLLECTIONS = (
    "variant_spaces",
    "protocols",
    "actions",
    "expected_action_rules",
    "selectors",
    "selection_rules",
    "discovery_rules",
    "gatt_services",
    "gatt_characteristics",
    "transforms",
    "checksums",
    "framings",
    "packet_fields",
    "packet_builders",
    "authentications",
    "bufferings",
    "parser_fields",
    "notification_parsers",
    "timings",
    "lifecycles",
    "transports",
    "action_parameters",
    "action_mappings",
)


@dataclass(frozen=True, slots=True)
class DomainClosure:
    domains: tuple[str, ...]
    unmodeled_paths: tuple[str, ...]

    def to_data(self) -> dict[str, object]:
        return {
            "status": "CLOSED" if not self.unmodeled_paths else "OPEN",
            "domains": list(self.domains),
            "unmodeled_paths": list(self.unmodeled_paths),
        }


type DefinitionMap[T] = tuple[tuple[str, T], ...]


@dataclass(frozen=True, slots=True)
class FinalProtocolIRDocument:
    """Final v1 IR. Every protocol domain is explicit and evidence-bound."""

    semantic_collection_names: ClassVar[tuple[str, ...]] = FINAL_DOMAIN_COLLECTIONS + (
        "domain_closure",
    )
    schema_revision: str
    source_packages: DefinitionMap[core.SourcePackage]
    evidence_files: DefinitionMap[core.EvidenceFile]
    evidence_anchors: DefinitionMap[core.EvidenceAnchor]
    source_sets: DefinitionMap[core.SourceSet]
    evidence_bindings: DefinitionMap[core.EvidenceBinding]
    variant_spaces: DefinitionMap[core.VariantSpace]
    protocols: DefinitionMap[core.ProtocolDefinition]
    actions: DefinitionMap[core.ActionDefinition]
    expected_action_rules: DefinitionMap[core.ExpectedActionRule]
    selectors: DefinitionMap[SelectorDefinition]
    selection_rules: DefinitionMap[SelectionRule]
    discovery_rules: DefinitionMap[DiscoveryRule]
    gatt_services: DefinitionMap[GattService]
    gatt_characteristics: DefinitionMap[GattCharacteristic]
    transforms: DefinitionMap[Transform]
    checksums: DefinitionMap[Checksum]
    framings: DefinitionMap[Framing]
    packet_fields: DefinitionMap[PacketField]
    packet_builders: DefinitionMap[PacketBuilder]
    authentications: DefinitionMap[Authentication]
    bufferings: DefinitionMap[Buffering]
    parser_fields: DefinitionMap[ParserField]
    notification_parsers: DefinitionMap[NotificationParser]
    timings: DefinitionMap[Timing]
    lifecycles: DefinitionMap[Lifecycle]
    transports: DefinitionMap[Transport]
    action_parameters: DefinitionMap[ActionParameter]
    action_mappings: DefinitionMap[ActionMapping]
    domain_closure: DomainClosure

    @property
    def command_bindings(self) -> DefinitionMap[core.CommandBinding]:
        """Keep legacy command rows absent; final mappings have richer predicates."""

        return ()

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"schema_revision": self.schema_revision}
        for name in (
            "source_packages",
            "evidence_files",
            "evidence_anchors",
            "source_sets",
            "evidence_bindings",
            *FINAL_DOMAIN_COLLECTIONS,
        ):
            definitions = cast(DefinitionMap[object], getattr(self, name))
            data[name] = {
                identifier: cast(core._DataDefinition, definition).to_data()
                for identifier, definition in definitions
            }
        data["domain_closure"] = self.domain_closure.to_data()
        return data


@dataclass(frozen=True, slots=True)
class FinalUniverseKey:
    protocol: str
    action: str
    selectors: core.Profile
    parameters: core.Profile


@dataclass(frozen=True, slots=True)
class FinalUniverseIssue:
    code: str
    key: FinalUniverseKey
    mapping_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FinalUniverseValidation:
    expected: frozenset[FinalUniverseKey]
    actual: frozenset[FinalUniverseKey]
    issues: tuple[FinalUniverseIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def parse_final_ir(
    raw: object, *, trusted_receipts: Mapping[str, str] | None = None
) -> FinalProtocolIRDocument:
    """Parse, authorize, and close a final v1 document."""

    return _parse_final_ir(raw, trusted_receipts=trusted_receipts, authorize=True)


def loads_final_ir(
    payload: str | bytes, *, trusted_receipts: Mapping[str, str] | None = None
) -> FinalProtocolIRDocument:
    """Decode and authorize a bounded final-v1 JSON document."""

    raw, _encoded = core._decode_strict_json(payload, max_bytes=core._MAX_IR_BYTES)
    return parse_final_ir(raw, trusted_receipts=trusted_receipts)


def load_final_ir(
    path: Path, *, trusted_receipts: Mapping[str, str] | None = None
) -> FinalProtocolIRDocument:
    """Load a bounded final-v1 document without modifying it."""

    with path.open("rb") as source:
        payload = source.read(core._MAX_IR_BYTES + 1)
    return loads_final_ir(payload, trusted_receipts=trusted_receipts)


def _parse_final_ir_structure(raw: object) -> FinalProtocolIRDocument:
    """Parse final-v1 structure without trusting provenance, for validators."""

    return _parse_final_ir(raw, trusted_receipts=None, authorize=False)


def _parse_final_ir(
    raw: object,
    *,
    trusted_receipts: Mapping[str, str] | None,
    authorize: bool,
) -> FinalProtocolIRDocument:

    core._validate_json_shape_bounds(raw)
    root = core._expect_object(raw, "$")
    required = {
        "schema_revision",
        "source_packages",
        "evidence_files",
        "evidence_anchors",
        "source_sets",
        "evidence_bindings",
        *FINAL_DOMAIN_COLLECTIONS,
        "domain_closure",
    }
    core._expect_keys(root, path="$", required=required)
    revision = core._expect_string(root["schema_revision"], "$.schema_revision")
    if revision != FINAL_SCHEMA_REVISION:
        core._fail(
            "unsupported_schema_revision",
            "$.schema_revision",
            f"expected {FINAL_SCHEMA_REVISION!r}, got {revision!r}",
        )
    core._validate_raw_provenance_bounds(root)
    parse_map = core._parse_definition_map

    def final_map[T](name: str, parser: Callable[[object, str], T]):
        return parse_map(root[name], f"$.{name}", parser, limit=_MAX_DEFINITIONS)

    document = FinalProtocolIRDocument(
        schema_revision=revision,
        source_packages=parse_map(
            root["source_packages"],
            "$.source_packages",
            core._parse_source_package,
            limit=_MAX_DEFINITIONS,
        ),
        evidence_files=parse_map(
            root["evidence_files"],
            "$.evidence_files",
            core._parse_evidence_file,
            limit=_MAX_DEFINITIONS,
        ),
        evidence_anchors=parse_map(
            root["evidence_anchors"],
            "$.evidence_anchors",
            core._parse_evidence_anchor,
            limit=_MAX_DEFINITIONS,
        ),
        source_sets=parse_map(
            root["source_sets"], "$.source_sets", core._parse_source_set, limit=_MAX_DEFINITIONS
        ),
        evidence_bindings=parse_map(
            root["evidence_bindings"],
            "$.evidence_bindings",
            core._parse_evidence_binding,
            limit=_MAX_DEFINITIONS,
        ),
        variant_spaces=final_map("variant_spaces", core._parse_variant_space),
        protocols=final_map("protocols", core._parse_protocol),
        actions=final_map("actions", core._parse_action),
        expected_action_rules=final_map("expected_action_rules", core._parse_expected_rule),
        selectors=final_map("selectors", _parse_selector),
        selection_rules=final_map("selection_rules", _parse_selection_rule),
        discovery_rules=final_map("discovery_rules", _parse_discovery_rule),
        gatt_services=final_map("gatt_services", _parse_gatt_service),
        gatt_characteristics=final_map("gatt_characteristics", _parse_gatt_characteristic),
        transforms=final_map("transforms", _parse_transform),
        checksums=final_map("checksums", _parse_checksum),
        framings=final_map("framings", _parse_framing),
        packet_fields=final_map("packet_fields", _parse_packet_field),
        packet_builders=final_map("packet_builders", _parse_packet_builder),
        authentications=final_map("authentications", _parse_authentication),
        bufferings=final_map("bufferings", _parse_buffering),
        parser_fields=final_map("parser_fields", _parse_parser_field),
        notification_parsers=final_map("notification_parsers", _parse_notification_parser),
        timings=final_map("timings", _parse_timing),
        lifecycles=final_map("lifecycles", _parse_lifecycle),
        transports=final_map("transports", _parse_transport),
        action_parameters=final_map("action_parameters", _parse_action_parameter),
        action_mappings=final_map("action_mappings", _parse_action_mapping),
        domain_closure=_parse_domain_closure(root["domain_closure"], "$.domain_closure"),
    )
    core._validate_provenance(cast(core.ProtocolIRDocument, document))
    core._validate_references_and_predicates(cast(core.ProtocolIRDocument, document))
    _validate_final_references(document)
    if authorize:
        core._validate_trusted_receipts(cast(core.ProtocolIRDocument, document), trusted_receipts)
        core._validate_exact_evidence_coverage(cast(core.ProtocolIRDocument, document))
    universe = validate_final_universe(document)
    if universe.issues:
        first = universe.issues[0]
        core._fail(first.code, "$.action_mappings", f"mapping coverage differs at {first.key!r}")
    return document


def dumps_final_ir(document: FinalProtocolIRDocument) -> bytes:
    return core._canonical_json(document.to_data()) + b"\n"


def final_semantic_fingerprint(document: FinalProtocolIRDocument) -> str:
    return hashlib.sha256(
        core._canonical_json(
            {
                "schema_revision": document.schema_revision,
                **core._semantic_data(cast(core.ProtocolIRDocument, document)),
            }
        )
    ).hexdigest()


def validate_final_universe(document: FinalProtocolIRDocument) -> FinalUniverseValidation:
    spaces = dict(document.variant_spaces)
    protocols = dict(document.protocols)
    parameters_by_action: dict[str, list[tuple[str, tuple[core.JsonScalar, ...]]]] = {}
    for parameter_id, parameter in document.action_parameters:
        parameters_by_action.setdefault(parameter.action, []).append(
            (parameter_id, parameter.values)
        )
    expected: set[FinalUniverseKey] = set()
    actual_sources: dict[FinalUniverseKey, list[str]] = {}
    expansions = 0
    for _, rule in document.expected_action_rules:
        profiles = spaces[protocols[rule.protocol].variant_space].iter_profiles()
        for profile in profiles:
            if not rule.when.matches(dict(profile)):
                continue
            parameter_domains = parameters_by_action.get(rule.action, [])
            names = tuple(item[0] for item in parameter_domains)
            values = tuple(item[1] for item in parameter_domains)
            for combination in itertools.product(*values) if values else ((),):
                expansions += 1
                if expansions > _MAX_DOMAIN_EXPANSIONS:
                    core._fail(
                        "universe_too_large",
                        "$.action_parameters",
                        "final universe expansion exceeds its bound",
                    )
                expected.add(
                    FinalUniverseKey(
                        rule.protocol,
                        rule.action,
                        profile,
                        tuple(zip(names, combination, strict=True)),
                    )
                )
    for mapping_id, mapping in document.action_mappings:
        profiles = spaces[protocols[mapping.protocol].variant_space].iter_profiles()
        for profile in profiles:
            parameter_domains = parameters_by_action.get(mapping.action, [])
            names = tuple(item[0] for item in parameter_domains)
            values = tuple(item[1] for item in parameter_domains)
            for combination in itertools.product(*values) if values else ((),):
                expansions += 1
                if expansions > _MAX_DOMAIN_EXPANSIONS:
                    core._fail(
                        "universe_too_large",
                        "$.action_mappings",
                        "final universe expansion exceeds its bound",
                    )
                combined = dict(profile)
                combined.update(zip(names, combination, strict=True))
                if mapping.when.matches(combined):
                    key = FinalUniverseKey(
                        mapping.protocol,
                        mapping.action,
                        profile,
                        tuple(zip(names, combination, strict=True)),
                    )
                    actual_sources.setdefault(key, []).append(mapping_id)
    actual = set(actual_sources)
    issues = [FinalUniverseIssue("missing_action_mapping", key, ()) for key in expected - actual]
    issues.extend(
        FinalUniverseIssue("extra_action_mapping", key, tuple(sorted(actual_sources[key])))
        for key in actual - expected
    )
    issues.extend(
        FinalUniverseIssue("duplicate_action_mapping", key, tuple(sorted(ids)))
        for key, ids in actual_sources.items()
        if len(ids) != 1
    )
    issues.sort(
        key=lambda issue: (
            issue.code,
            core._canonical_json(
                {
                    "protocol": issue.key.protocol,
                    "action": issue.key.action,
                    "selectors": dict(issue.key.selectors),
                    "parameters": dict(issue.key.parameters),
                }
            ),
            issue.mapping_ids,
        )
    )
    return FinalUniverseValidation(frozenset(expected), frozenset(actual), tuple(issues))


def _object(
    raw: object, path: str, required: set[str], optional: set[str] | None = None
) -> dict[str, object]:
    value = core._expect_object(raw, path)
    core._expect_keys(value, path=path, required=required, optional=optional or set())
    return value


def _enum[T: StrEnum](enum_type: type[T], raw: object, path: str) -> T:
    value = core._expect_string(raw, path)
    try:
        return enum_type(value)
    except ValueError:
        core._fail("unknown_domain_enum", path, f"unsupported {enum_type.__name__} value {value!r}")


def _refs(raw: object, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    values = core._expect_array(raw, path)
    if len(values) > _MAX_REFERENCES or (not allow_empty and not values):
        core._fail("invalid_reference_set", path, "reference set is empty or exceeds its bound")
    parsed = tuple(
        core._expect_reference(value, f"{path}[{index}]") for index, value in enumerate(values)
    )
    if len(set(parsed)) != len(parsed):
        core._fail("duplicate_reference", path, "references must be unique")
    return parsed


def _scalars(raw: object, path: str) -> tuple[core.JsonScalar, ...]:
    values = core._expect_array(raw, path)
    if not values or len(values) > core._MAX_VARIANT_PROFILES:
        core._fail("invalid_scalar_domain", path, "scalar domain is empty or exceeds its bound")
    parsed = tuple(
        sorted(
            (core._expect_scalar(item, f"{path}[{index}]") for index, item in enumerate(values)),
            key=core._scalar_sort_key,
        )
    )
    if len({core._scalar_sort_key(item) for item in parsed}) != len(parsed):
        core._fail("duplicate_domain_value", path, "domain values must be unique")
    return parsed


def _hex(raw: object, path: str, *, allow_empty: bool = True) -> str:
    value = core._expect_string(raw, path)
    if (
        (not allow_empty and not value)
        or len(value) > 8192
        or len(value) % 2
        or any(character not in "0123456789abcdef" for character in value)
    ):
        core._fail("invalid_hex", path, "hex must be bounded, even-length, and lowercase")
    return value


def _parse_selector(raw: object, path: str) -> SelectorDefinition:
    value = _object(raw, path, {"variant_space", "dimension", "kind", "values"})
    return SelectorDefinition(
        core._expect_reference(value["variant_space"], f"{path}.variant_space"),
        core._expect_reference(value["dimension"], f"{path}.dimension"),
        _enum(SelectorKind, value["kind"], f"{path}.kind"),
        _scalars(value["values"], f"{path}.values"),
    )


def _parse_selection_rule(raw: object, path: str) -> SelectionRule:
    value = _object(raw, path, {"protocol", "when"})
    return SelectionRule(
        core._expect_reference(value["protocol"], f"{path}.protocol"),
        core._parse_predicate(value["when"], f"{path}.when"),
    )


def _parse_discovery_rule(raw: object, path: str) -> DiscoveryRule:
    value = _object(raw, path, {"selection_rule", "matchers"})
    raw_matchers = core._expect_array(value["matchers"], f"{path}.matchers")
    if not raw_matchers or len(raw_matchers) > _MAX_REFERENCES:
        core._fail(
            "invalid_matcher_set", f"{path}.matchers", "matcher set is empty or exceeds its bound"
        )
    matchers = tuple(
        _parse_discovery_matcher(item, f"{path}.matchers[{index}]")
        for index, item in enumerate(raw_matchers)
    )
    return DiscoveryRule(
        core._expect_reference(value["selection_rule"], f"{path}.selection_rule"), matchers
    )


def _parse_discovery_matcher(raw: object, path: str) -> DiscoveryMatcher:
    value = _object(raw, path, {"field", "operation"}, {"value"})
    operation = _enum(MatchOperation, value["operation"], f"{path}.operation")
    candidate = (
        core._expect_nonempty_string(value["value"], f"{path}.value", max_length=4096)
        if "value" in value
        else None
    )
    if (operation is MatchOperation.PRESENT) != (candidate is None):
        core._fail(
            "invalid_discovery_matcher",
            path,
            "PRESENT omits value; every other operation requires it",
        )
    if operation is MatchOperation.REGEX and candidate is not None:
        try:
            re.compile(candidate)
        except re.error as error:
            core._fail("invalid_discovery_regex", f"{path}.value", str(error))
    return DiscoveryMatcher(
        _enum(MatchField, value["field"], f"{path}.field"), operation, candidate
    )


def _gatt_uuid(raw: object, path: str) -> str:
    value = core._expect_nonempty_string(raw, path, max_length=36)
    if re.fullmatch(
        r"(?:[0-9a-fA-F]{4}|[0-9a-fA-F]{8}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
        value,
    ) is None:
        core._fail("invalid_gatt_uuid", path, "expected a 16, 32, or canonical 128-bit UUID")
    return value.lower()


def _parse_gatt_service(raw: object, path: str) -> GattService:
    value = _object(raw, path, {"uuid", "role"})
    return GattService(
        _gatt_uuid(value["uuid"], f"{path}.uuid"),
        _enum(GattServiceRole, value["role"], f"{path}.role"),
    )


def _parse_gatt_characteristic(raw: object, path: str) -> GattCharacteristic:
    value = _object(raw, path, {"service", "uuid", "roles", "write_modes"})
    raw_roles = core._expect_array(value["roles"], f"{path}.roles")
    raw_modes = core._expect_array(value["write_modes"], f"{path}.write_modes")
    if len(raw_roles) > len(GattCharacteristicRole) or len(raw_modes) > len(WriteMode):
        core._fail("invalid_gatt_roles", path, "role or write-mode set exceeds its bound")
    roles = tuple(
        _enum(GattCharacteristicRole, item, f"{path}.roles[{index}]")
        for index, item in enumerate(raw_roles)
    )
    modes = tuple(
        _enum(WriteMode, item, f"{path}.write_modes[{index}]")
        for index, item in enumerate(raw_modes)
    )
    if not roles or len(set(roles)) != len(roles) or len(set(modes)) != len(modes):
        core._fail(
            "invalid_gatt_roles", path, "roles must be non-empty and role/mode entries unique"
        )
    return GattCharacteristic(
        core._expect_reference(value["service"], f"{path}.service"),
        _gatt_uuid(value["uuid"], f"{path}.uuid"),
        tuple(sorted(roles)),
        tuple(sorted(modes)),
    )


def _parse_transform(raw: object, path: str) -> Transform:
    value = _object(raw, path, {"operation"}, {"operand", "lookup"})
    operation = _enum(TransformOperation, value["operation"], f"{path}.operation")
    operand = (
        core._expect_scalar(value["operand"], f"{path}.operand") if "operand" in value else None
    )
    lookup: tuple[tuple[core.JsonScalar, core.JsonScalar], ...] = ()
    if "lookup" in value:
        items = core._expect_array(value["lookup"], f"{path}.lookup")
        if not items or len(items) > _MAX_REFERENCES:
            core._fail("invalid_lookup", f"{path}.lookup", "lookup is empty or exceeds its bound")
        pairs = []
        for index, item in enumerate(items):
            pair = core._expect_array(item, f"{path}.lookup[{index}]")
            if len(pair) != 2:
                core._fail(
                    "invalid_lookup", f"{path}.lookup[{index}]", "lookup entries must be pairs"
                )
            pairs.append(
                (
                    core._expect_scalar(pair[0], f"{path}.lookup[{index}][0]"),
                    core._expect_scalar(pair[1], f"{path}.lookup[{index}][1]"),
                )
            )
        lookup = tuple(sorted(pairs, key=lambda pair: core._canonical_json(pair)))
        if len({core._scalar_sort_key(pair[0]) for pair in lookup}) != len(lookup):
            core._fail("invalid_lookup", f"{path}.lookup", "lookup keys must be unique")
    requires_operand = operation in {TransformOperation.ADD, TransformOperation.XOR}
    requires_lookup = operation is TransformOperation.LOOKUP
    if requires_operand != (operand is not None) or requires_lookup != bool(lookup):
        core._fail("invalid_transform_shape", path, "transform operands do not match the operation")
    return Transform(operation, operand, lookup)


def _parse_checksum(raw: object, path: str) -> Checksum:
    value = _object(raw, path, {"algorithm", "start_byte", "end_byte", "output_width"})
    start = core._expect_integer(value["start_byte"], f"{path}.start_byte", minimum=0)
    return Checksum(
        _enum(ChecksumAlgorithm, value["algorithm"], f"{path}.algorithm"),
        start,
        core._expect_integer(value["end_byte"], f"{path}.end_byte", minimum=start + 1),
        core._expect_integer(value["output_width"], f"{path}.output_width", minimum=1),
    )


def _parse_framing(raw: object, path: str) -> Framing:
    value = _object(raw, path, {"prefix_hex", "suffix_hex"}, {"length_field"})
    return Framing(
        _hex(value["prefix_hex"], f"{path}.prefix_hex"),
        _hex(value["suffix_hex"], f"{path}.suffix_hex"),
        core._expect_reference(value["length_field"], f"{path}.length_field")
        if "length_field" in value
        else None,
    )


def _parse_packet_field(raw: object, path: str) -> PacketField:
    value = _object(
        raw, path, {"offset", "width", "source", "transforms"}, {"source_ref", "constant_hex"}
    )
    source = _enum(PacketFieldSource, value["source"], f"{path}.source")
    source_ref = (
        core._expect_reference(value["source_ref"], f"{path}.source_ref")
        if "source_ref" in value
        else None
    )
    constant = (
        _hex(value["constant_hex"], f"{path}.constant_hex", allow_empty=False)
        if "constant_hex" in value
        else None
    )
    if (source is PacketFieldSource.CONSTANT) != (constant is not None) or (
        source is not PacketFieldSource.CONSTANT and source_ref is None
    ):
        core._fail(
            "invalid_packet_field_source",
            path,
            "field source requires exactly its matching payload",
        )
    width = core._expect_integer(value["width"], f"{path}.width", minimum=1)
    if constant is not None and len(bytes.fromhex(constant)) != width:
        core._fail("invalid_packet_field_width", path, "constant byte length must equal width")
    return PacketField(
        core._expect_integer(value["offset"], f"{path}.offset", minimum=0),
        width,
        source,
        source_ref,
        constant,
        _refs(value["transforms"], f"{path}.transforms", allow_empty=True),
    )


def _parse_packet_builder(raw: object, path: str) -> PacketBuilder:
    value = _object(raw, path, {"fields", "framing"}, {"checksum"})
    return PacketBuilder(
        _refs(value["fields"], f"{path}.fields"),
        core._expect_reference(value["framing"], f"{path}.framing"),
        core._expect_reference(value["checksum"], f"{path}.checksum")
        if "checksum" in value
        else None,
    )


def _parse_authentication(raw: object, path: str) -> Authentication:
    value = _object(raw, path, {"method", "selectors"}, {"request_builder", "response_parser"})
    method = _enum(AuthenticationMethod, value["method"], f"{path}.method")
    request = (
        core._expect_reference(value["request_builder"], f"{path}.request_builder")
        if "request_builder" in value
        else None
    )
    response = (
        core._expect_reference(value["response_parser"], f"{path}.response_parser")
        if "response_parser" in value
        else None
    )
    selectors = _refs(
        value["selectors"], f"{path}.selectors", allow_empty=method is AuthenticationMethod.NONE
    )
    if method is AuthenticationMethod.NONE and (selectors or request or response):
        core._fail(
            "invalid_authentication_shape", path, "NONE authentication cannot declare inputs"
        )
    return Authentication(method, selectors, request, response)


def _parse_buffering(raw: object, path: str) -> Buffering:
    value = _object(raw, path, {"mode"}, {"size", "delimiter_hex"})
    mode = _enum(BufferingMode, value["mode"], f"{path}.mode")
    size = (
        core._expect_integer(value["size"], f"{path}.size", minimum=1) if "size" in value else None
    )
    delimiter = (
        _hex(value["delimiter_hex"], f"{path}.delimiter_hex", allow_empty=False)
        if "delimiter_hex" in value
        else None
    )
    if (mode in {BufferingMode.FIXED_LENGTH, BufferingMode.LENGTH_PREFIXED}) != (
        size is not None
    ) or (mode is BufferingMode.DELIMITER) != (delimiter is not None):
        core._fail("invalid_buffering_shape", path, "buffering parameters do not match its mode")
    return Buffering(mode, size, delimiter)


def _parse_parser_field(raw: object, path: str) -> ParserField:
    value = _object(raw, path, {"offset", "width", "target_selector", "transforms"})
    return ParserField(
        core._expect_integer(value["offset"], f"{path}.offset", minimum=0),
        core._expect_integer(value["width"], f"{path}.width", minimum=1),
        core._expect_reference(value["target_selector"], f"{path}.target_selector"),
        _refs(value["transforms"], f"{path}.transforms", allow_empty=True),
    )


def _parse_notification_parser(raw: object, path: str) -> NotificationParser:
    value = _object(raw, path, {"buffering", "fields"})
    return NotificationParser(
        core._expect_reference(value["buffering"], f"{path}.buffering"),
        _refs(value["fields"], f"{path}.fields"),
    )


def _parse_timing(raw: object, path: str) -> Timing:
    value = _object(
        raw,
        path,
        {"repeat_count", "repeat_interval_ms", "cancellation", "release"},
        {"release_action"},
    )
    release = _enum(ReleaseMode, value["release"], f"{path}.release")
    action = (
        core._expect_reference(value["release_action"], f"{path}.release_action")
        if "release_action" in value
        else None
    )
    if (release in {ReleaseMode.STOP_ACTION, ReleaseMode.RELEASE_ACTION}) != (action is not None):
        core._fail(
            "invalid_release_shape",
            path,
            "action-based release requires exactly one release action",
        )
    return Timing(
        core._expect_integer(value["repeat_count"], f"{path}.repeat_count", minimum=1),
        core._expect_integer(value["repeat_interval_ms"], f"{path}.repeat_interval_ms", minimum=0),
        _enum(CancellationMode, value["cancellation"], f"{path}.cancellation"),
        release,
        action,
    )


def _parse_lifecycle(raw: object, path: str) -> Lifecycle:
    value = _object(raw, path, {"phases"})
    raw_phases = core._expect_array(value["phases"], f"{path}.phases")
    if len(raw_phases) > len(LifecyclePhase):
        core._fail("invalid_lifecycle", path, "lifecycle phase list exceeds its bound")
    phases = tuple(
        _enum(LifecyclePhase, item, f"{path}.phases[{index}]")
        for index, item in enumerate(raw_phases)
    )
    if not phases or len(set(phases)) != len(phases) or LifecyclePhase.WRITE not in phases:
        core._fail(
            "invalid_lifecycle",
            path,
            "lifecycle phases must be non-empty, unique, and include WRITE",
        )
    phase_order = {phase: index for index, phase in enumerate(LifecyclePhase)}
    if tuple(sorted(phases, key=phase_order.__getitem__)) != phases:
        core._fail("invalid_lifecycle", path, "lifecycle phases must follow protocol order")
    return Lifecycle(phases)


def _parse_transport(raw: object, path: str) -> Transport:
    value = _object(
        raw,
        path,
        {"characteristic", "write_mode", "packet_builder", "timing", "lifecycle"},
        {"notification_parser", "authentication"},
    )
    return Transport(
        core._expect_reference(value["characteristic"], f"{path}.characteristic"),
        _enum(WriteMode, value["write_mode"], f"{path}.write_mode"),
        core._expect_reference(value["packet_builder"], f"{path}.packet_builder"),
        core._expect_reference(value["notification_parser"], f"{path}.notification_parser")
        if "notification_parser" in value
        else None,
        core._expect_reference(value["authentication"], f"{path}.authentication")
        if "authentication" in value
        else None,
        core._expect_reference(value["timing"], f"{path}.timing"),
        core._expect_reference(value["lifecycle"], f"{path}.lifecycle"),
    )


def _parse_action_parameter(raw: object, path: str) -> ActionParameter:
    value = _object(raw, path, {"action", "values"})
    return ActionParameter(
        core._expect_reference(value["action"], f"{path}.action"),
        _scalars(value["values"], f"{path}.values"),
    )


def _parse_action_mapping(raw: object, path: str) -> ActionMapping:
    value = _object(raw, path, {"protocol", "action", "transport", "when"})
    return ActionMapping(
        core._expect_reference(value["protocol"], f"{path}.protocol"),
        core._expect_reference(value["action"], f"{path}.action"),
        core._expect_reference(value["transport"], f"{path}.transport"),
        core._parse_predicate(value["when"], f"{path}.when"),
    )


def _parse_domain_closure(raw: object, path: str) -> DomainClosure:
    value = _object(raw, path, {"status", "domains", "unmodeled_paths"})
    status = core._expect_string(value["status"], f"{path}.status")
    domains = tuple(
        core._expect_string(item, f"{path}.domains[{index}]")
        for index, item in enumerate(core._expect_array(value["domains"], f"{path}.domains"))
    )
    paths = tuple(
        core._expect_string(item, f"{path}.unmodeled_paths[{index}]")
        for index, item in enumerate(
            core._expect_array(value["unmodeled_paths"], f"{path}.unmodeled_paths")
        )
    )
    if status != "CLOSED" or domains != FINAL_DOMAIN_COLLECTIONS or paths:
        core._fail(
            "domain_not_closed",
            path,
            "final v1 requires the exact domain list, CLOSED status, and no unmodeled paths",
        )
    return DomainClosure(domains, paths)


def _validate_final_references(document: FinalProtocolIRDocument) -> None:
    collections = {
        name: dict(cast(Iterable[tuple[str, object]], getattr(document, name)))
        for name in FINAL_DOMAIN_COLLECTIONS
    }
    diagnostics = core._BoundedDiagnostics()

    def reference(collection: str, identifier: str | None, path: str) -> None:
        if identifier is not None and identifier not in collections[collection]:
            diagnostics.append(
                core.IRDiagnostic(
                    "unknown_reference", path, f"unknown {collection} definition {identifier!r}"
                )
            )

    for selector_id, selector in document.selectors:
        reference(
            "variant_spaces", selector.variant_space, f"$.selectors.{selector_id}.variant_space"
        )
        space = collections["variant_spaces"].get(selector.variant_space)
        if isinstance(space, core.VariantSpace):
            declared = dict(space.dimensions).get(selector.dimension)
            if declared is None or declared != selector.values:
                diagnostics.append(
                    core.IRDiagnostic(
                        "selector_domain_mismatch",
                        f"$.selectors.{selector_id}",
                        "selector must exactly reproduce its variant-space dimension",
                    )
                )
    declared_dimensions = {
        (selector.variant_space, selector.dimension) for _, selector in document.selectors
    }
    required_dimensions = {
        (space_id, name)
        for space_id, space in document.variant_spaces
        for name, _ in space.dimensions
    }
    if declared_dimensions != required_dimensions or len(declared_dimensions) != len(
        document.selectors
    ):
        diagnostics.append(
            core.IRDiagnostic(
                "selector_domain_not_exact",
                "$.selectors",
                "every variant dimension must have exactly one typed selector",
            )
        )
    dimension_names = {dimension for _space, dimension in required_dimensions}
    parameter_names = {identifier for identifier, _ in document.action_parameters}
    collisions = dimension_names & parameter_names
    if collisions:
        diagnostics.append(
            core.IRDiagnostic(
                "selector_parameter_collision",
                "$.action_parameters",
                f"action parameter IDs collide with selector dimensions: {sorted(collisions)!r}",
            )
        )
    protocols = cast(dict[str, core.ProtocolDefinition], collections["protocols"])
    for rule_id, rule in document.selection_rules:
        reference("protocols", rule.protocol, f"$.selection_rules.{rule_id}.protocol")
        protocol = protocols.get(rule.protocol)
        if protocol is not None:
            diagnostics.extend(
                core._predicate_diagnostics(
                    rule.when,
                    dict(
                        cast(
                            core.VariantSpace, collections["variant_spaces"][protocol.variant_space]
                        ).dimensions
                    ),
                    f"$.selection_rules.{rule_id}.when",
                )
            )
    for rule_id, rule in document.discovery_rules:
        reference(
            "selection_rules", rule.selection_rule, f"$.discovery_rules.{rule_id}.selection_rule"
        )
    for char_id, char in document.gatt_characteristics:
        reference("gatt_services", char.service, f"$.gatt_characteristics.{char_id}.service")
        if char.write_modes and GattCharacteristicRole.WRITE not in char.roles:
            diagnostics.append(
                core.IRDiagnostic(
                    "write_mode_without_role",
                    f"$.gatt_characteristics.{char_id}.write_modes",
                    "write modes require the WRITE role",
                )
            )
    for field_id, field in document.packet_fields:
        for index, transform in enumerate(field.transforms):
            reference("transforms", transform, f"$.packet_fields.{field_id}.transforms[{index}]")
        if field.source is PacketFieldSource.ACTION_PARAMETER:
            reference(
                "action_parameters", field.source_ref, f"$.packet_fields.{field_id}.source_ref"
            )
        if field.source is PacketFieldSource.SELECTOR:
            reference("selectors", field.source_ref, f"$.packet_fields.{field_id}.source_ref")
        if field.source is PacketFieldSource.CHECKSUM:
            reference("checksums", field.source_ref, f"$.packet_fields.{field_id}.source_ref")
        if field.source is PacketFieldSource.AUTHENTICATION:
            reference("authentications", field.source_ref, f"$.packet_fields.{field_id}.source_ref")
    for framing_id, framing in document.framings:
        reference("packet_fields", framing.length_field, f"$.framings.{framing_id}.length_field")
    for builder_id, builder in document.packet_builders:
        for index, field in enumerate(builder.fields):
            reference("packet_fields", field, f"$.packet_builders.{builder_id}.fields[{index}]")
        reference("framings", builder.framing, f"$.packet_builders.{builder_id}.framing")
        reference("checksums", builder.checksum, f"$.packet_builders.{builder_id}.checksum")
    for auth_id, auth in document.authentications:
        for index, selector in enumerate(auth.selectors):
            reference("selectors", selector, f"$.authentications.{auth_id}.selectors[{index}]")
        reference(
            "packet_builders", auth.request_builder, f"$.authentications.{auth_id}.request_builder"
        )
        reference(
            "notification_parsers",
            auth.response_parser,
            f"$.authentications.{auth_id}.response_parser",
        )
    for field_id, field in document.parser_fields:
        reference("selectors", field.target_selector, f"$.parser_fields.{field_id}.target_selector")
        for index, transform in enumerate(field.transforms):
            reference("transforms", transform, f"$.parser_fields.{field_id}.transforms[{index}]")
    for parser_id, parser in document.notification_parsers:
        reference("bufferings", parser.buffering, f"$.notification_parsers.{parser_id}.buffering")
        for index, field in enumerate(parser.fields):
            reference("parser_fields", field, f"$.notification_parsers.{parser_id}.fields[{index}]")
    for timing_id, timing in document.timings:
        reference("actions", timing.release_action, f"$.timings.{timing_id}.release_action")
    for transport_id, transport in document.transports:
        reference(
            "gatt_characteristics",
            transport.characteristic,
            f"$.transports.{transport_id}.characteristic",
        )
        reference(
            "packet_builders",
            transport.packet_builder,
            f"$.transports.{transport_id}.packet_builder",
        )
        reference(
            "notification_parsers",
            transport.notification_parser,
            f"$.transports.{transport_id}.notification_parser",
        )
        reference(
            "authentications",
            transport.authentication,
            f"$.transports.{transport_id}.authentication",
        )
        reference("timings", transport.timing, f"$.transports.{transport_id}.timing")
        reference("lifecycles", transport.lifecycle, f"$.transports.{transport_id}.lifecycle")
        char = collections["gatt_characteristics"].get(transport.characteristic)
        if isinstance(char, GattCharacteristic) and transport.write_mode not in char.write_modes:
            diagnostics.append(
                core.IRDiagnostic(
                    "unsupported_write_mode",
                    f"$.transports.{transport_id}.write_mode",
                    "transport write mode is not declared by the characteristic",
                )
            )
    for parameter_id, parameter in document.action_parameters:
        reference("actions", parameter.action, f"$.action_parameters.{parameter_id}.action")
    for mapping_id, mapping in document.action_mappings:
        reference("protocols", mapping.protocol, f"$.action_mappings.{mapping_id}.protocol")
        reference("actions", mapping.action, f"$.action_mappings.{mapping_id}.action")
        reference("transports", mapping.transport, f"$.action_mappings.{mapping_id}.transport")
        protocol = protocols.get(mapping.protocol)
        if protocol is not None:
            dimensions = dict(
                cast(
                    core.VariantSpace, collections["variant_spaces"][protocol.variant_space]
                ).dimensions
            )
            dimensions.update(
                {
                    parameter_id: parameter.values
                    for parameter_id, parameter in document.action_parameters
                    if parameter.action == mapping.action
                }
            )
            diagnostics.extend(
                core._predicate_diagnostics(
                    mapping.when, dimensions, f"$.action_mappings.{mapping_id}.when"
                )
            )
    if diagnostics:
        raise core.IRValidationError(diagnostics)
