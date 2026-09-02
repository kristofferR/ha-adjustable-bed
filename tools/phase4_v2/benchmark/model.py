"""Externally attested blind benchmark contract for Phase 4 v2 rollout."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

BENCHMARK_REVISION = "phase4-v2-benchmark-v2"
REQUIRED_CONTRACT_ISSUES = (544, 545, 546, 547, 548, 549)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ED25519_PUBLIC_KEY = re.compile(r"^[0-9a-f]{64}$")
_ED25519_SIGNATURE = re.compile(r"^[0-9a-f]{128}$")
_MIN_CASES = 8
_MAX_CASES = 12
_MAX_FINDINGS_PER_CASE = 100_000
_MAX_CANDIDATES_PER_CASE = 250_000
_MAX_TIMING_SAMPLES = 100_000


class MutationKind(StrEnum):
    REMOVED_CALLSITE = "REMOVED_CALLSITE"
    RESOURCE_SELECTOR_CHANGE = "RESOURCE_SELECTOR_CHANGE"
    DECOMPILER_FAILURE = "DECOMPILER_FAILURE"
    STOP_TIMING_CHANGE = "STOP_TIMING_CHANGE"
    COORDINATED_REBASE = "COORDINATED_REBASE"
    REPORT_INTEGRITY_ATTACK = "REPORT_INTEGRITY_ATTACK"


REQUIRED_MUTATIONS = frozenset(MutationKind)
REQUIRED_COVERAGE_TAGS = frozenset(
    {
        "lifecycle-timing",
        "multi-protocol-catalog",
        "non-jvm",
        "obfuscated",
        "parser",
        "promoted-sibling",
        "simple-managed",
    }
)


class CandidateDisposition(StrEnum):
    MATERIAL_FINDING = "MATERIAL_FINDING"
    EXPLAINED_NON_BLE = "EXPLAINED_NON_BLE"
    DUPLICATE = "DUPLICATE"
    UNEXPLAINED = "UNEXPLAINED"


class AuditDecision(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class AuditSubjectKind(StrEnum):
    CASE = "CASE"
    MUTATION = "MUTATION"


class TimingPhase(StrEnum):
    LEGACY = "LEGACY"
    V2 = "V2"


class RolloutDecision(StrEnum):
    AUTHORIZE = "AUTHORIZE"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True, order=True)
class ContractPin:
    """One externally frozen issue contract."""

    issue: int
    revision: str
    sha256: str

    def __post_init__(self) -> None:
        if type(self.issue) is not int or self.issue not in REQUIRED_CONTRACT_ISSUES:
            raise ValueError("contract issue must be one of #544 through #549")
        _identifier(self.revision, "contract revision")
        _digest(self.sha256, "contract digest")

    def to_data(self) -> dict[str, object]:
        return {"issue": self.issue, "revision": self.revision, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class BenchmarkAuthority:
    """Immutable identities approved outside benchmark execution."""

    contracts: tuple[ContractPin, ...]
    corpus_sha256: str
    run_identity_sha256: str
    toolchain_sha256: str
    harness_sha256: str
    analyst_identity_sha256: str
    mutation_runner_identity_sha256: str
    auditor_identity_sha256: str
    auditor_public_key: str
    telemetry_collector_identity_sha256: str
    telemetry_collector_public_key: str
    revision: str = BENCHMARK_REVISION

    def __post_init__(self) -> None:
        if self.revision != BENCHMARK_REVISION:
            raise ValueError(f"unsupported benchmark revision: {self.revision!r}")
        _tuple_of(self.contracts, ContractPin, "contract pins")
        if tuple(item.issue for item in self.contracts) != REQUIRED_CONTRACT_ISSUES:
            raise ValueError("contract pins must contain exact ordered issues #544 through #549")
        values = (
            ("corpus", self.corpus_sha256),
            ("run identity", self.run_identity_sha256),
            ("toolchain", self.toolchain_sha256),
            ("harness", self.harness_sha256),
            ("analyst identity", self.analyst_identity_sha256),
            ("mutation runner identity", self.mutation_runner_identity_sha256),
            ("auditor identity", self.auditor_identity_sha256),
            ("telemetry collector identity", self.telemetry_collector_identity_sha256),
        )
        for label, value in values:
            _digest(value, label)
        actors = (
            self.analyst_identity_sha256,
            self.mutation_runner_identity_sha256,
            self.auditor_identity_sha256,
            self.telemetry_collector_identity_sha256,
        )
        if len(set(actors)) != len(actors):
            raise ValueError("benchmark actor identities must be independent")
        for label, public_key, identity in (
            ("auditor", self.auditor_public_key, self.auditor_identity_sha256),
            (
                "telemetry collector",
                self.telemetry_collector_public_key,
                self.telemetry_collector_identity_sha256,
            ),
        ):
            if type(public_key) is not str or _ED25519_PUBLIC_KEY.fullmatch(public_key) is None:
                raise ValueError(f"{label} public key must be a lowercase Ed25519 key")
            if _content_digest(bytes.fromhex(public_key)) != identity:
                raise ValueError(f"{label} identity must bind its Ed25519 public key")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "analyst_identity_sha256": self.analyst_identity_sha256,
            "auditor_identity_sha256": self.auditor_identity_sha256,
            "auditor_public_key": self.auditor_public_key,
            "contracts": [item.to_data() for item in self.contracts],
            "corpus_sha256": self.corpus_sha256,
            "harness_sha256": self.harness_sha256,
            "mutation_runner_identity_sha256": self.mutation_runner_identity_sha256,
            "revision": self.revision,
            "run_identity_sha256": self.run_identity_sha256,
            "telemetry_collector_identity_sha256": self.telemetry_collector_identity_sha256,
            "telemetry_collector_public_key": self.telemetry_collector_public_key,
            "toolchain_sha256": self.toolchain_sha256,
        }


@dataclass(frozen=True, slots=True, order=True)
class FindingIdentity:
    domain: str
    finding_id: str
    semantic_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.domain, "finding domain")
        _identifier(self.finding_id, "finding id")
        _digest(self.semantic_sha256, "finding semantic digest")

    def to_data(self) -> dict[str, str]:
        return {
            "domain": self.domain,
            "finding_id": self.finding_id,
            "semantic_sha256": self.semantic_sha256,
        }


@dataclass(frozen=True, slots=True)
class EvidenceQuality:
    exact_anchor_count: int
    package_bound: bool
    complete_stack_routes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.exact_anchor_count) is not int or self.exact_anchor_count < 0:
            raise ValueError("exact anchor count must be a non-negative integer")
        if type(self.package_bound) is not bool:
            raise ValueError("package bound must be a boolean")
        _tuple_of(self.complete_stack_routes, str, "stack routes")
        _unique_ids(self.complete_stack_routes, "stack routes", allow_empty=True)

    def to_data(self) -> dict[str, object]:
        return {
            "complete_stack_routes": list(self.complete_stack_routes),
            "exact_anchor_count": self.exact_anchor_count,
            "package_bound": self.package_bound,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    input_sha256: str
    coverage_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case id")
        _digest(self.input_sha256, "case input digest")
        _tuple_of(self.coverage_tags, str, "coverage tags")
        _unique_ids(self.coverage_tags, "coverage tags")

    def to_data(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "coverage_tags": list(self.coverage_tags),
            "input_sha256": self.input_sha256,
        }


@dataclass(frozen=True, slots=True, order=True)
class MutationDeclaration:
    kind: MutationKind
    input_sha256: str

    def __post_init__(self) -> None:
        if type(self.kind) is not MutationKind:
            raise ValueError("mutation kind must be a MutationKind")
        _digest(self.input_sha256, "mutation input digest")

    def to_data(self) -> dict[str, str]:
        return {"input_sha256": self.input_sha256, "kind": self.kind.value}


@dataclass(frozen=True, slots=True)
class BenchmarkPlan:
    cases: tuple[BenchmarkCase, ...]
    mutations: tuple[MutationDeclaration, ...]
    oracle_sha256: str
    authority_sha256: str
    minimum_throughput_ratio: int = 3
    minimum_token_reduction_ratio: int = 5
    revision: str = BENCHMARK_REVISION

    def __post_init__(self) -> None:
        if self.revision != BENCHMARK_REVISION:
            raise ValueError(f"unsupported benchmark revision: {self.revision!r}")
        if not _MIN_CASES <= len(self.cases) <= _MAX_CASES:
            raise ValueError(f"benchmark must contain {_MIN_CASES} to {_MAX_CASES} cases")
        _tuple_of(self.cases, BenchmarkCase, "benchmark cases")
        _unique((item.case_id for item in self.cases), label="case ids")
        if tuple(sorted(self.cases, key=lambda item: item.case_id)) != self.cases:
            raise ValueError("benchmark cases must be sorted by case id")
        missing_tags = REQUIRED_COVERAGE_TAGS - {
            tag for item in self.cases for tag in item.coverage_tags
        }
        if missing_tags:
            raise ValueError(
                "benchmark cases are missing required coverage tags: "
                + ", ".join(sorted(missing_tags))
            )
        _tuple_of(self.mutations, MutationDeclaration, "mutation declarations")
        required = tuple(sorted(REQUIRED_MUTATIONS, key=lambda item: item.value))
        if tuple(item.kind for item in self.mutations) != required:
            raise ValueError("mutation declarations must contain the exact required set")
        _digest(self.oracle_sha256, "oracle digest")
        _digest(self.authority_sha256, "authority digest")
        for label, value in (
            ("minimum throughput ratio", self.minimum_throughput_ratio),
            ("minimum token reduction ratio", self.minimum_token_reduction_ratio),
        ):
            if type(value) is not int or value < 1:
                raise ValueError(f"{label} must be a positive integer")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "authority_sha256": self.authority_sha256,
            "cases": [item.to_data() for item in self.cases],
            "minimum_throughput_ratio": self.minimum_throughput_ratio,
            "minimum_token_reduction_ratio": self.minimum_token_reduction_ratio,
            "mutations": [item.to_data() for item in self.mutations],
            "oracle_sha256": self.oracle_sha256,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class CaseOracle:
    case_id: str
    findings: tuple[tuple[FindingIdentity, EvidenceQuality], ...]
    candidate_ids: tuple[str, ...]
    required_stack_routes: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.case_id, "oracle case id")
        if type(self.findings) is not tuple or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not FindingIdentity
            or type(item[1]) is not EvidenceQuality
            for item in self.findings
        ):
            raise ValueError("oracle findings must be exact identity/evidence pairs")
        if len(self.findings) > _MAX_FINDINGS_PER_CASE:
            raise ValueError("oracle finding limit exceeded")
        _unique((item[0] for item in self.findings), label="oracle findings")
        if tuple(sorted(self.findings, key=lambda item: item[0])) != self.findings:
            raise ValueError("oracle findings must be sorted")
        _tuple_of(self.candidate_ids, str, "oracle candidate ids")
        _unique_ids(self.candidate_ids, "oracle candidate ids", allow_empty=True)
        if len(self.candidate_ids) > _MAX_CANDIDATES_PER_CASE:
            raise ValueError("oracle candidate limit exceeded")
        _tuple_of(self.required_stack_routes, str, "required stack routes")
        _unique_ids(self.required_stack_routes, "required stack routes")

    def to_data(self) -> dict[str, object]:
        return {
            "candidate_ids": list(self.candidate_ids),
            "case_id": self.case_id,
            "findings": [
                {"evidence": evidence.to_data(), "identity": identity.to_data()}
                for identity, evidence in self.findings
            ],
            "required_stack_routes": list(self.required_stack_routes),
        }


@dataclass(frozen=True, slots=True)
class OracleSuite:
    cases: tuple[CaseOracle, ...]

    def __post_init__(self) -> None:
        _tuple_of(self.cases, CaseOracle, "oracle cases")
        _unique((item.case_id for item in self.cases), label="oracle case ids")
        if tuple(sorted(self.cases, key=lambda item: item.case_id)) != self.cases:
            raise ValueError("oracle cases must be sorted by case id")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {"cases": [item.to_data() for item in self.cases]}


@dataclass(frozen=True, slots=True)
class FindingResult:
    identity: FindingIdentity
    evidence: EvidenceQuality

    def __post_init__(self) -> None:
        if type(self.identity) is not FindingIdentity:
            raise ValueError("finding result identity must be a FindingIdentity")
        if type(self.evidence) is not EvidenceQuality:
            raise ValueError("finding result evidence must be EvidenceQuality")

    def to_data(self) -> dict[str, object]:
        return {"evidence": self.evidence.to_data(), "identity": self.identity.to_data()}


@dataclass(frozen=True, slots=True)
class CandidateResult:
    candidate_id: str
    disposition: CandidateDisposition
    finding: FindingIdentity | None = None

    def __post_init__(self) -> None:
        _identifier(self.candidate_id, "candidate id")
        if type(self.disposition) is not CandidateDisposition:
            raise ValueError("candidate disposition must be a CandidateDisposition")
        if self.finding is not None and type(self.finding) is not FindingIdentity:
            raise ValueError("candidate finding must be a FindingIdentity")
        if self.disposition is CandidateDisposition.MATERIAL_FINDING and self.finding is None:
            raise ValueError("material candidate disposition requires a finding")
        if (
            self.disposition is not CandidateDisposition.MATERIAL_FINDING
            and self.finding is not None
        ):
            raise ValueError("only material candidates may reference a finding")

    def to_data(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "disposition": self.disposition.value,
            "finding": None if self.finding is None else self.finding.to_data(),
        }


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    input_sha256: str
    findings: tuple[FindingResult, ...]
    candidates: tuple[CandidateResult, ...]
    completed_stack_routes: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.case_id, "result case id")
        _digest(self.input_sha256, "result input digest")
        _tuple_of(self.findings, FindingResult, "result findings")
        if len(self.findings) > _MAX_FINDINGS_PER_CASE:
            raise ValueError("result finding limit exceeded")
        _unique((item.identity for item in self.findings), label="result findings")
        if tuple(sorted(self.findings, key=lambda item: item.identity)) != self.findings:
            raise ValueError("result findings must be sorted")
        _tuple_of(self.candidates, CandidateResult, "result candidates")
        if len(self.candidates) > _MAX_CANDIDATES_PER_CASE:
            raise ValueError("result candidate limit exceeded")
        _unique((item.candidate_id for item in self.candidates), label="result candidates")
        if tuple(sorted(self.candidates, key=lambda item: item.candidate_id)) != self.candidates:
            raise ValueError("result candidates must be sorted")
        _tuple_of(self.completed_stack_routes, str, "completed stack routes")
        _unique_ids(self.completed_stack_routes, "completed stack routes")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "candidates": [item.to_data() for item in self.candidates],
            "case_id": self.case_id,
            "completed_stack_routes": list(self.completed_stack_routes),
            "findings": [item.to_data() for item in self.findings],
            "input_sha256": self.input_sha256,
        }


@dataclass(frozen=True, slots=True)
class MutationResult:
    kind: MutationKind
    input_sha256: str
    output_sha256: str
    detected: bool
    evidence_sha256: str

    def __post_init__(self) -> None:
        if type(self.kind) is not MutationKind:
            raise ValueError("mutation kind must be a MutationKind")
        if type(self.detected) is not bool:
            raise ValueError("mutation detected must be a boolean")
        _digest(self.input_sha256, "mutation input digest")
        _digest(self.output_sha256, "mutation output digest")
        _digest(self.evidence_sha256, "mutation evidence digest")
        if self.input_sha256 == self.output_sha256:
            raise ValueError("mutation output must differ from its input")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "evidence_sha256": self.evidence_sha256,
            "input_sha256": self.input_sha256,
            "kind": self.kind.value,
            "output_sha256": self.output_sha256,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    plan_sha256: str
    authority_sha256: str
    corpus_sha256: str
    run_identity_sha256: str
    toolchain_sha256: str
    harness_sha256: str
    analyst_identity_sha256: str
    mutation_runner_identity_sha256: str
    cases: tuple[CaseResult, ...]
    mutations: tuple[MutationResult, ...]

    def __post_init__(self) -> None:
        values = (
            ("plan", self.plan_sha256),
            ("authority", self.authority_sha256),
            ("corpus", self.corpus_sha256),
            ("run identity", self.run_identity_sha256),
            ("toolchain", self.toolchain_sha256),
            ("harness", self.harness_sha256),
            ("analyst identity", self.analyst_identity_sha256),
            ("mutation runner identity", self.mutation_runner_identity_sha256),
        )
        for label, value in values:
            _digest(value, label)
        _tuple_of(self.cases, CaseResult, "run cases")
        _unique((item.case_id for item in self.cases), label="run case ids")
        if tuple(sorted(self.cases, key=lambda item: item.case_id)) != self.cases:
            raise ValueError("run cases must be sorted by case id")
        _tuple_of(self.mutations, MutationResult, "mutation results")
        _unique((item.kind for item in self.mutations), label="mutation kinds")
        if tuple(sorted(self.mutations, key=lambda item: item.kind.value)) != self.mutations:
            raise ValueError("mutation results must be sorted by kind")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "analyst_identity_sha256": self.analyst_identity_sha256,
            "authority_sha256": self.authority_sha256,
            "cases": [item.to_data() for item in self.cases],
            "corpus_sha256": self.corpus_sha256,
            "harness_sha256": self.harness_sha256,
            "mutation_runner_identity_sha256": self.mutation_runner_identity_sha256,
            "mutations": [item.to_data() for item in self.mutations],
            "plan_sha256": self.plan_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "toolchain_sha256": self.toolchain_sha256,
        }


@dataclass(frozen=True, slots=True, order=True)
class AuditReceipt:
    subject_kind: AuditSubjectKind
    subject_id: str
    subject_sha256: str
    decision: AuditDecision
    evidence_sha256: str
    auditor_identity_sha256: str

    def __post_init__(self) -> None:
        if type(self.subject_kind) is not AuditSubjectKind:
            raise ValueError("audit subject kind must be an AuditSubjectKind")
        _identifier(self.subject_id, "audit subject id")
        _digest(self.subject_sha256, "audit subject digest")
        if type(self.decision) is not AuditDecision:
            raise ValueError("audit decision must be an AuditDecision")
        _digest(self.evidence_sha256, "audit evidence digest")
        _digest(self.auditor_identity_sha256, "auditor identity")

    def to_data(self) -> dict[str, str]:
        return {
            "auditor_identity_sha256": self.auditor_identity_sha256,
            "decision": self.decision.value,
            "evidence_sha256": self.evidence_sha256,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind.value,
            "subject_sha256": self.subject_sha256,
        }


@dataclass(frozen=True, slots=True)
class IndependentAuditSuite:
    authority_sha256: str
    auditor_identity_sha256: str
    receipts: tuple[AuditReceipt, ...]
    signature: str

    def __post_init__(self) -> None:
        _digest(self.authority_sha256, "audit authority digest")
        _digest(self.auditor_identity_sha256, "auditor identity")
        _tuple_of(self.receipts, AuditReceipt, "audit receipts")
        if tuple(sorted(self.receipts)) != self.receipts:
            raise ValueError("audit receipts must be sorted")
        _unique(
            ((item.subject_kind, item.subject_id) for item in self.receipts),
            label="audit subjects",
        )
        if type(self.signature) is not str or _ED25519_SIGNATURE.fullmatch(self.signature) is None:
            raise ValueError("audit suite signature must be a lowercase Ed25519 signature")

    @property
    def signing_bytes(self) -> bytes:
        return _canonical(self.unsigned_data())

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {**self.unsigned_data(), "signature": self.signature}

    def unsigned_data(self) -> dict[str, object]:
        return {
            "auditor_identity_sha256": self.auditor_identity_sha256,
            "authority_sha256": self.authority_sha256,
            "receipts": [item.to_data() for item in self.receipts],
        }


@dataclass(frozen=True, slots=True, order=True)
class TimingSample:
    """One raw duration from a monotonic clock with immutable provenance."""

    trial_id: str
    case_id: str
    phase: TimingPhase
    started_monotonic_ns: int
    finished_monotonic_ns: int
    collector_identity_sha256: str
    host_identity_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.trial_id, "timing trial id")
        _identifier(self.case_id, "timing case id")
        if type(self.phase) is not TimingPhase:
            raise ValueError("timing phase must be a TimingPhase")
        if type(self.started_monotonic_ns) is not int or self.started_monotonic_ns < 0:
            raise ValueError("timing start must be a non-negative monotonic nanosecond value")
        if (
            type(self.finished_monotonic_ns) is not int
            or self.finished_monotonic_ns <= self.started_monotonic_ns
        ):
            raise ValueError("timing finish must be after timing start")
        _digest(self.collector_identity_sha256, "timing collector identity")
        _digest(self.host_identity_sha256, "timing host identity")

    @property
    def duration_ns(self) -> int:
        return self.finished_monotonic_ns - self.started_monotonic_ns

    def to_data(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "clock": "monotonic_ns",
            "collector_identity_sha256": self.collector_identity_sha256,
            "finished_monotonic_ns": self.finished_monotonic_ns,
            "host_identity_sha256": self.host_identity_sha256,
            "phase": self.phase.value,
            "started_monotonic_ns": self.started_monotonic_ns,
            "trial_id": self.trial_id,
        }


@dataclass(frozen=True, slots=True, order=True)
class TokenSample:
    """One raw orchestration-token observation from the trusted collector."""

    trial_id: str
    case_id: str
    phase: TimingPhase
    orchestration_tokens: int
    collector_identity_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.trial_id, "token trial id")
        _identifier(self.case_id, "token case id")
        if type(self.phase) is not TimingPhase:
            raise ValueError("token phase must be a TimingPhase")
        if type(self.orchestration_tokens) is not int or self.orchestration_tokens <= 0:
            raise ValueError("orchestration tokens must be a positive integer")
        _digest(self.collector_identity_sha256, "token collector identity")

    def to_data(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "collector_identity_sha256": self.collector_identity_sha256,
            "orchestration_tokens": self.orchestration_tokens,
            "phase": self.phase.value,
            "trial_id": self.trial_id,
        }


@dataclass(frozen=True, slots=True)
class TimingSuite:
    authority_sha256: str
    corpus_sha256: str
    run_identity_sha256: str
    collector_identity_sha256: str
    host_identity_sha256: str
    samples: tuple[TimingSample, ...]
    token_samples: tuple[TokenSample, ...]
    signature: str

    def __post_init__(self) -> None:
        for label, value in (
            ("timing authority", self.authority_sha256),
            ("timing corpus", self.corpus_sha256),
            ("timing run identity", self.run_identity_sha256),
            ("timing collector identity", self.collector_identity_sha256),
            ("timing host identity", self.host_identity_sha256),
        ):
            _digest(value, label)
        _tuple_of(self.samples, TimingSample, "timing samples")
        if not self.samples or len(self.samples) > _MAX_TIMING_SAMPLES:
            raise ValueError("timing samples must be non-empty and bounded")
        if tuple(sorted(self.samples)) != self.samples:
            raise ValueError("timing samples must be sorted")
        _unique(
            ((item.trial_id, item.case_id, item.phase) for item in self.samples),
            label="timing samples",
        )
        _tuple_of(self.token_samples, TokenSample, "token samples")
        if not self.token_samples or len(self.token_samples) > _MAX_TIMING_SAMPLES:
            raise ValueError("token samples must be non-empty and bounded")
        if tuple(sorted(self.token_samples)) != self.token_samples:
            raise ValueError("token samples must be sorted")
        _unique(
            ((item.trial_id, item.case_id, item.phase) for item in self.token_samples),
            label="token samples",
        )
        if type(self.signature) is not str or _ED25519_SIGNATURE.fullmatch(self.signature) is None:
            raise ValueError("timing suite signature must be a lowercase Ed25519 signature")

    @property
    def signing_bytes(self) -> bytes:
        return _canonical(self.unsigned_data())

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {**self.unsigned_data(), "signature": self.signature}

    def unsigned_data(self) -> dict[str, object]:
        return {
            "authority_sha256": self.authority_sha256,
            "collector_identity_sha256": self.collector_identity_sha256,
            "corpus_sha256": self.corpus_sha256,
            "host_identity_sha256": self.host_identity_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "samples": [item.to_data() for item in self.samples],
            "token_samples": [item.to_data() for item in self.token_samples],
        }


@dataclass(frozen=True, slots=True, order=True)
class BenchmarkDiagnostic:
    code: str
    path: str
    message: str

    def __post_init__(self) -> None:
        _identifier(self.code, "diagnostic code")
        if type(self.path) is not str or not self.path.startswith("$."):
            raise ValueError("diagnostic path must be a canonical root path")
        if type(self.message) is not str or not self.message:
            raise ValueError("diagnostic message must not be empty")

    def to_data(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    authority_sha256: str
    plan_sha256: str
    oracle_sha256: str
    run_sha256: str
    audit_suite_sha256: str
    timing_suite_sha256: str
    decision: RolloutDecision
    diagnostics: tuple[BenchmarkDiagnostic, ...]
    revision: str = BENCHMARK_REVISION

    def __post_init__(self) -> None:
        for label, value in (
            ("report authority", self.authority_sha256),
            ("report plan", self.plan_sha256),
            ("report oracle", self.oracle_sha256),
            ("report run", self.run_sha256),
            ("report audit suite", self.audit_suite_sha256),
            ("report timing suite", self.timing_suite_sha256),
        ):
            _digest(value, label)
        if type(self.decision) is not RolloutDecision:
            raise ValueError("report decision must be a RolloutDecision")
        _tuple_of(self.diagnostics, BenchmarkDiagnostic, "report diagnostics")
        if tuple(sorted(self.diagnostics)) != self.diagnostics:
            raise ValueError("report diagnostics must be sorted")
        if self.revision != BENCHMARK_REVISION:
            raise ValueError(f"unsupported benchmark revision: {self.revision!r}")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "audit_suite_sha256": self.audit_suite_sha256,
            "authority_sha256": self.authority_sha256,
            "decision": self.decision.value,
            "diagnostics": [item.to_data() for item in self.diagnostics],
            "oracle_sha256": self.oracle_sha256,
            "plan_sha256": self.plan_sha256,
            "revision": self.revision,
            "run_sha256": self.run_sha256,
            "timing_suite_sha256": self.timing_suite_sha256,
        }


def finalize_benchmark(
    authority: BenchmarkAuthority,
    plan: BenchmarkPlan,
    oracle: OracleSuite,
    run: BenchmarkRun,
    audits: IndependentAuditSuite,
    timings: TimingSuite,
) -> BenchmarkReport:
    """Reveal committed inputs and deterministically decide rollout."""

    diagnostics: list[BenchmarkDiagnostic] = []
    if plan.authority_sha256 != authority.content_id:
        diagnostics.append(_diag("authority_commitment_mismatch", "$.plan.authority_sha256"))
    if oracle.content_id != plan.oracle_sha256:
        diagnostics.append(_diag("oracle_commitment_mismatch", "$.plan.oracle_sha256"))
    if run.plan_sha256 != plan.content_id:
        diagnostics.append(_diag("plan_commitment_mismatch", "$.run.plan_sha256"))
    _check_run_authority(authority, run, diagnostics)
    _check_cases(plan, oracle, run, diagnostics)
    _check_mutations(plan, run, diagnostics)
    _check_audits(authority, run, audits, diagnostics)
    _check_timings(authority, plan, timings, diagnostics)
    diagnostics.sort()
    return BenchmarkReport(
        authority.content_id,
        plan.content_id,
        oracle.content_id,
        run.content_id,
        audits.content_id,
        timings.content_id,
        RolloutDecision.AUTHORIZE if not diagnostics else RolloutDecision.REJECT,
        tuple(diagnostics),
    )


def _check_run_authority(
    authority: BenchmarkAuthority,
    run: BenchmarkRun,
    diagnostics: list[BenchmarkDiagnostic],
) -> None:
    expected = {
        "authority_sha256": authority.content_id,
        "corpus_sha256": authority.corpus_sha256,
        "run_identity_sha256": authority.run_identity_sha256,
        "toolchain_sha256": authority.toolchain_sha256,
        "harness_sha256": authority.harness_sha256,
        "analyst_identity_sha256": authority.analyst_identity_sha256,
        "mutation_runner_identity_sha256": authority.mutation_runner_identity_sha256,
    }
    for field, value in expected.items():
        if getattr(run, field) != value:
            diagnostics.append(_diag("run_authority_mismatch", f"$.run.{field}"))


def _check_cases(
    plan: BenchmarkPlan,
    oracle: OracleSuite,
    run: BenchmarkRun,
    diagnostics: list[BenchmarkDiagnostic],
) -> None:
    plan_cases = {item.case_id: item for item in plan.cases}
    oracle_cases = {item.case_id: item for item in oracle.cases}
    run_cases = {item.case_id: item for item in run.cases}
    expected_ids = set(plan_cases)
    for code, actual, path in (
        ("oracle_case_set_mismatch", set(oracle_cases), "$.oracle.cases"),
        ("run_case_set_mismatch", set(run_cases), "$.run.cases"),
    ):
        if actual != expected_ids:
            diagnostics.append(_diag(code, path))
    for case_id in sorted(expected_ids & set(oracle_cases) & set(run_cases)):
        planned = plan_cases[case_id]
        expected = oracle_cases[case_id]
        actual = run_cases[case_id]
        base = f"$.cases.{case_id}"
        if actual.input_sha256 != planned.input_sha256:
            diagnostics.append(_diag("case_input_mismatch", f"{base}.input_sha256"))
        expected_findings = dict(expected.findings)
        actual_findings = {item.identity: item.evidence for item in actual.findings}
        for identity in sorted(set(actual_findings) - set(expected_findings)):
            diagnostics.append(
                _diag("unexpected_material_finding", f"{base}.findings.{identity.finding_id}")
            )
        for identity, minimum in expected_findings.items():
            observed = actual_findings.get(identity)
            path = f"{base}.findings.{identity.finding_id}"
            if observed is None:
                diagnostics.append(_diag("material_finding_missing", path))
                continue
            if observed.exact_anchor_count < minimum.exact_anchor_count:
                diagnostics.append(_diag("evidence_anchor_regression", path))
            if minimum.package_bound and not observed.package_bound:
                diagnostics.append(_diag("package_binding_regression", path))
            if not set(minimum.complete_stack_routes) <= set(observed.complete_stack_routes):
                diagnostics.append(_diag("finding_stack_coverage_regression", path))
        if not set(expected.required_stack_routes) <= set(actual.completed_stack_routes):
            diagnostics.append(_diag("case_stack_coverage_regression", f"{base}.stack_routes"))
        candidate_results = {item.candidate_id: item for item in actual.candidates}
        if set(candidate_results) != set(expected.candidate_ids):
            diagnostics.append(_diag("candidate_set_mismatch", f"{base}.candidates"))
        for candidate in actual.candidates:
            path = f"{base}.candidates.{candidate.candidate_id}"
            if candidate.disposition is CandidateDisposition.UNEXPLAINED:
                diagnostics.append(_diag("unexplained_ble_candidate", path))
            if candidate.finding is not None and candidate.finding not in actual_findings:
                diagnostics.append(_diag("candidate_finding_missing", path))


def _check_mutations(
    plan: BenchmarkPlan,
    run: BenchmarkRun,
    diagnostics: list[BenchmarkDiagnostic],
) -> None:
    declarations = {item.kind: item for item in plan.mutations}
    results = {item.kind: item for item in run.mutations}
    if set(results) != REQUIRED_MUTATIONS:
        diagnostics.append(_diag("mutation_set_mismatch", "$.run.mutations"))
    for kind in sorted(REQUIRED_MUTATIONS, key=lambda item: item.value):
        result = results.get(kind)
        if result is None:
            continue
        if result.input_sha256 != declarations[kind].input_sha256:
            diagnostics.append(
                _diag("mutation_input_mismatch", f"$.run.mutations.{kind.value}.input_sha256")
            )
        if not result.detected:
            diagnostics.append(_diag("mutation_not_detected", f"$.run.mutations.{kind.value}"))


def _check_audits(
    authority: BenchmarkAuthority,
    run: BenchmarkRun,
    audits: IndependentAuditSuite,
    diagnostics: list[BenchmarkDiagnostic],
) -> None:
    if audits.authority_sha256 != authority.content_id:
        diagnostics.append(_diag("audit_authority_mismatch", "$.audits.authority_sha256"))
    if audits.auditor_identity_sha256 != authority.auditor_identity_sha256:
        diagnostics.append(_diag("audit_identity_mismatch", "$.audits.auditor_identity_sha256"))
    if not _verify_signature(
        authority.auditor_public_key,
        audits.signature,
        audits.signing_bytes,
    ):
        diagnostics.append(_diag("audit_signature_invalid", "$.audits.signature"))
    expected = {
        **{(AuditSubjectKind.CASE, item.case_id): item.content_id for item in run.cases},
        **{(AuditSubjectKind.MUTATION, item.kind.value): item.content_id for item in run.mutations},
    }
    actual = {(item.subject_kind, item.subject_id): item for item in audits.receipts}
    if set(actual) != set(expected):
        diagnostics.append(_diag("audit_subject_set_mismatch", "$.audits.receipts"))
    for subject, expected_digest in expected.items():
        receipt = actual.get(subject)
        if receipt is None:
            continue
        path = f"$.audits.{subject[0].value}.{subject[1]}"
        if receipt.auditor_identity_sha256 != authority.auditor_identity_sha256:
            diagnostics.append(_diag("audit_identity_mismatch", f"{path}.auditor_identity_sha256"))
        if receipt.subject_sha256 != expected_digest:
            diagnostics.append(_diag("audit_subject_mismatch", f"{path}.subject_sha256"))
        if receipt.decision is not AuditDecision.ACCEPTED:
            diagnostics.append(_diag("independent_audit_rejected", f"{path}.decision"))


def _check_timings(
    authority: BenchmarkAuthority,
    plan: BenchmarkPlan,
    timings: TimingSuite,
    diagnostics: list[BenchmarkDiagnostic],
) -> None:
    expected_headers = {
        "authority_sha256": authority.content_id,
        "corpus_sha256": authority.corpus_sha256,
        "run_identity_sha256": authority.run_identity_sha256,
        "collector_identity_sha256": authority.telemetry_collector_identity_sha256,
    }
    for field, value in expected_headers.items():
        if getattr(timings, field) != value:
            diagnostics.append(_diag("timing_authority_mismatch", f"$.timings.{field}"))
    if not _verify_signature(
        authority.telemetry_collector_public_key,
        timings.signature,
        timings.signing_bytes,
    ):
        diagnostics.append(_diag("timing_signature_invalid", "$.timings.signature"))
    cases = {item.case_id for item in plan.cases}
    pairs: dict[tuple[str, str], dict[TimingPhase, TimingSample]] = {}
    for sample in timings.samples:
        path = f"$.timings.{sample.trial_id}.{sample.case_id}.{sample.phase.value}"
        if sample.case_id not in cases:
            diagnostics.append(_diag("timing_case_mismatch", path))
        if sample.collector_identity_sha256 != timings.collector_identity_sha256:
            diagnostics.append(_diag("timing_collector_mismatch", path))
        if sample.host_identity_sha256 != timings.host_identity_sha256:
            diagnostics.append(_diag("timing_host_mismatch", path))
        pairs.setdefault((sample.trial_id, sample.case_id), {})[sample.phase] = sample
    if {case_id for _trial, case_id in pairs} != cases:
        diagnostics.append(_diag("timing_case_set_mismatch", "$.timings.samples"))
    complete = [pair for pair in pairs.values() if set(pair) == set(TimingPhase)]
    if len(complete) != len(pairs):
        diagnostics.append(_diag("timing_phase_pair_mismatch", "$.timings.samples"))
    legacy_ns = sum(pair[TimingPhase.LEGACY].duration_ns for pair in complete)
    v2_ns = sum(pair[TimingPhase.V2].duration_ns for pair in complete)
    if (
        not v2_ns
        or legacy_ns < plan.minimum_throughput_ratio * v2_ns
        or any(
            pair[TimingPhase.LEGACY].duration_ns
            < plan.minimum_throughput_ratio * pair[TimingPhase.V2].duration_ns
            for pair in complete
        )
    ):
        diagnostics.append(_diag("throughput_gate_failed", "$.timings.samples"))
    token_pairs: dict[tuple[str, str], dict[TimingPhase, TokenSample]] = {}
    for sample in timings.token_samples:
        path = f"$.timings.tokens.{sample.trial_id}.{sample.case_id}.{sample.phase.value}"
        if sample.collector_identity_sha256 != timings.collector_identity_sha256:
            diagnostics.append(_diag("token_collector_mismatch", path))
        token_pairs.setdefault((sample.trial_id, sample.case_id), {})[sample.phase] = sample
    if set(token_pairs) != set(pairs) or any(
        set(pair) != set(TimingPhase) for pair in token_pairs.values()
    ):
        diagnostics.append(_diag("token_sample_pair_mismatch", "$.timings.token_samples"))
    complete_tokens = [pair for pair in token_pairs.values() if set(pair) == set(TimingPhase)]
    legacy_tokens = sum(pair[TimingPhase.LEGACY].orchestration_tokens for pair in complete_tokens)
    v2_tokens = sum(pair[TimingPhase.V2].orchestration_tokens for pair in complete_tokens)
    if (
        not v2_tokens
        or legacy_tokens < plan.minimum_token_reduction_ratio * v2_tokens
        or any(
            pair[TimingPhase.LEGACY].orchestration_tokens
            < plan.minimum_token_reduction_ratio * pair[TimingPhase.V2].orchestration_tokens
            for pair in complete_tokens
        )
    ):
        diagnostics.append(_diag("token_gate_failed", "$.timings.token_samples"))


def benchmark_json(
    value: BenchmarkAuthority
    | BenchmarkPlan
    | OracleSuite
    | BenchmarkRun
    | IndependentAuditSuite
    | TimingSuite
    | BenchmarkReport,
) -> bytes:
    return _canonical(value.to_data()) + b"\n"


def _diag(code: str, path: str) -> BenchmarkDiagnostic:
    return BenchmarkDiagnostic(code=code, path=path, message=code.replace("_", " "))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _content_id(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _content_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _verify_signature(public_key: str, signature: str, payload: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            bytes.fromhex(signature), payload
        )
    except InvalidSignature, ValueError:
        return False
    return True


def _identifier(value: str, label: str) -> None:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError(f"{label} is not a canonical identifier")


def _digest(value: str, label: str) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")


def _unique(values: Iterable[Hashable], *, label: str) -> None:
    materialized = tuple(values)
    if len(set(materialized)) != len(materialized):
        raise ValueError(f"{label} must be unique")


def _unique_ids(values: tuple[str, ...], label: str, *, allow_empty: bool = False) -> None:
    if not values and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    for value in values:
        _identifier(value, label)
    if tuple(sorted(values)) != values:
        raise ValueError(f"{label} must be sorted")
    _unique(values, label=label)


def _tuple_of(values: object, item_type: type[object], label: str) -> None:
    if type(values) is not tuple or any(type(item) is not item_type for item in values):
        raise ValueError(f"{label} must be an exact tuple of {item_type.__name__}")
