"""Fail-closed benchmark model and scorer for Phase 4 v2.

The blind plan contains only opaque case identities and an oracle commitment. The
accepted findings are supplied separately after every case result is frozen.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from enum import StrEnum

BENCHMARK_REVISION = "phase4-v2-benchmark-v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MIN_CASES = 8
_MAX_CASES = 12
_MAX_FINDINGS_PER_CASE = 100_000
_MAX_CANDIDATES_PER_CASE = 250_000


class MutationKind(StrEnum):
    """Required adversarial benchmark mutation classes."""

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
    """Terminal disposition for one deterministic BLE candidate."""

    MATERIAL_FINDING = "MATERIAL_FINDING"
    EXPLAINED_NON_BLE = "EXPLAINED_NON_BLE"
    DUPLICATE = "DUPLICATE"
    UNEXPLAINED = "UNEXPLAINED"


class AuditDecision(StrEnum):
    """Independent semantic audit result."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class RolloutDecision(StrEnum):
    """Final benchmark decision."""

    AUTHORIZE = "AUTHORIZE"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True, order=True)
class FindingIdentity:
    """Stable semantic identity of one material accepted finding."""

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
    """Minimum or observed evidence strength for one finding."""

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
    """Opaque case metadata safe to hand to a blind analyst."""

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


@dataclass(frozen=True, slots=True)
class BenchmarkPlan:
    """Frozen blind plan with no accepted finding content."""

    cases: tuple[BenchmarkCase, ...]
    oracle_sha256: str
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
        _digest(self.oracle_sha256, "oracle digest")
        if type(self.minimum_throughput_ratio) is not int or self.minimum_throughput_ratio < 1:
            raise ValueError("minimum throughput ratio must be a positive integer")
        if (
            type(self.minimum_token_reduction_ratio) is not int
            or self.minimum_token_reduction_ratio < 1
        ):
            raise ValueError("minimum token reduction ratio must be a positive integer")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "cases": [item.to_data() for item in self.cases],
            "minimum_throughput_ratio": self.minimum_throughput_ratio,
            "minimum_token_reduction_ratio": self.minimum_token_reduction_ratio,
            "oracle_sha256": self.oracle_sha256,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class CaseOracle:
    """Accepted comparison facts kept outside the blind plan."""

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
    """Frozen oracle revealed only to the final scorer."""

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
    audit: AuditDecision
    audit_receipt_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.case_id, "result case id")
        _digest(self.input_sha256, "result input digest")
        if type(self.audit) is not AuditDecision:
            raise ValueError("case audit must be an AuditDecision")
        _digest(self.audit_receipt_sha256, "case audit receipt digest")
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

    def to_data(self) -> dict[str, object]:
        return {
            "audit": self.audit.value,
            "audit_receipt_sha256": self.audit_receipt_sha256,
            "candidates": [item.to_data() for item in self.candidates],
            "case_id": self.case_id,
            "completed_stack_routes": list(self.completed_stack_routes),
            "findings": [item.to_data() for item in self.findings],
            "input_sha256": self.input_sha256,
        }


@dataclass(frozen=True, slots=True)
class MutationResult:
    kind: MutationKind
    detected: bool
    evidence_sha256: str

    def __post_init__(self) -> None:
        if type(self.kind) is not MutationKind:
            raise ValueError("mutation kind must be a MutationKind")
        if type(self.detected) is not bool:
            raise ValueError("mutation detected must be a boolean")
        _digest(self.evidence_sha256, "mutation evidence digest")

    def to_data(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "evidence_sha256": self.evidence_sha256,
            "kind": self.kind.value,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    plan_sha256: str
    cases: tuple[CaseResult, ...]
    mutations: tuple[MutationResult, ...]
    legacy_wall_time_ms: int
    v2_wall_time_ms: int
    legacy_orchestration_tokens: int
    v2_orchestration_tokens: int

    def __post_init__(self) -> None:
        _digest(self.plan_sha256, "run plan digest")
        _tuple_of(self.cases, CaseResult, "run cases")
        _unique((item.case_id for item in self.cases), label="run case ids")
        if tuple(sorted(self.cases, key=lambda item: item.case_id)) != self.cases:
            raise ValueError("run cases must be sorted by case id")
        _tuple_of(self.mutations, MutationResult, "mutation results")
        _unique((item.kind for item in self.mutations), label="mutation kinds")
        if tuple(sorted(self.mutations, key=lambda item: item.kind.value)) != self.mutations:
            raise ValueError("mutation results must be sorted by kind")
        for label, value in (
            ("legacy wall time", self.legacy_wall_time_ms),
            ("v2 wall time", self.v2_wall_time_ms),
            ("legacy orchestration tokens", self.legacy_orchestration_tokens),
            ("v2 orchestration tokens", self.v2_orchestration_tokens),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{label} must be a positive integer")

    @property
    def content_id(self) -> str:
        return _content_id(self.to_data())

    def to_data(self) -> dict[str, object]:
        return {
            "cases": [item.to_data() for item in self.cases],
            "legacy_orchestration_tokens": self.legacy_orchestration_tokens,
            "legacy_wall_time_ms": self.legacy_wall_time_ms,
            "mutations": [item.to_data() for item in self.mutations],
            "plan_sha256": self.plan_sha256,
            "v2_orchestration_tokens": self.v2_orchestration_tokens,
            "v2_wall_time_ms": self.v2_wall_time_ms,
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
    plan_sha256: str
    oracle_sha256: str
    run_sha256: str
    decision: RolloutDecision
    diagnostics: tuple[BenchmarkDiagnostic, ...]
    revision: str = BENCHMARK_REVISION

    def __post_init__(self) -> None:
        _digest(self.plan_sha256, "report plan digest")
        _digest(self.oracle_sha256, "report oracle digest")
        _digest(self.run_sha256, "report run digest")
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
            "decision": self.decision.value,
            "diagnostics": [item.to_data() for item in self.diagnostics],
            "oracle_sha256": self.oracle_sha256,
            "plan_sha256": self.plan_sha256,
            "revision": self.revision,
            "run_sha256": self.run_sha256,
        }


def finalize_benchmark(
    plan: BenchmarkPlan, oracle: OracleSuite, run: BenchmarkRun
) -> BenchmarkReport:
    """Reveal the committed oracle and deterministically decide rollout."""

    diagnostics: list[BenchmarkDiagnostic] = []
    if oracle.content_id != plan.oracle_sha256:
        diagnostics.append(_diag("oracle_commitment_mismatch", "$.oracle_sha256"))
    if run.plan_sha256 != plan.content_id:
        diagnostics.append(_diag("plan_commitment_mismatch", "$.run.plan_sha256"))

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
        if actual.audit is not AuditDecision.ACCEPTED:
            diagnostics.append(_diag("independent_audit_rejected", f"{base}.audit"))
        expected_findings = dict(expected.findings)
        actual_findings = {item.identity: item.evidence for item in actual.findings}
        for identity in sorted(set(actual_findings) - set(expected_findings)):
            diagnostics.append(
                _diag(
                    "unexpected_material_finding",
                    f"{base}.findings.{identity.finding_id}",
                )
            )
        for identity, minimum in expected_findings.items():
            observed = actual_findings.get(identity)
            finding_path = f"{base}.findings.{identity.finding_id}"
            if observed is None:
                diagnostics.append(_diag("material_finding_missing", finding_path))
                continue
            if observed.exact_anchor_count < minimum.exact_anchor_count:
                diagnostics.append(_diag("evidence_anchor_regression", finding_path))
            if minimum.package_bound and not observed.package_bound:
                diagnostics.append(_diag("package_binding_regression", finding_path))
            if not set(minimum.complete_stack_routes) <= set(observed.complete_stack_routes):
                diagnostics.append(_diag("finding_stack_coverage_regression", finding_path))
        if not set(expected.required_stack_routes) <= set(actual.completed_stack_routes):
            diagnostics.append(_diag("case_stack_coverage_regression", f"{base}.stack_routes"))
        candidate_results = {item.candidate_id: item for item in actual.candidates}
        if set(candidate_results) != set(expected.candidate_ids):
            diagnostics.append(_diag("candidate_set_mismatch", f"{base}.candidates"))
        for candidate in actual.candidates:
            if candidate.disposition is CandidateDisposition.UNEXPLAINED:
                diagnostics.append(
                    _diag(
                        "unexplained_ble_candidate", f"{base}.candidates.{candidate.candidate_id}"
                    )
                )
            if candidate.finding is not None and candidate.finding not in actual_findings:
                diagnostics.append(
                    _diag(
                        "candidate_finding_missing", f"{base}.candidates.{candidate.candidate_id}"
                    )
                )

    mutations = {item.kind: item for item in run.mutations}
    if set(mutations) != REQUIRED_MUTATIONS:
        diagnostics.append(_diag("mutation_set_mismatch", "$.run.mutations"))
    for kind in sorted(REQUIRED_MUTATIONS, key=lambda item: item.value):
        result = mutations.get(kind)
        if result is not None and not result.detected:
            diagnostics.append(_diag("mutation_not_detected", f"$.run.mutations.{kind.value}"))

    if run.legacy_wall_time_ms < plan.minimum_throughput_ratio * run.v2_wall_time_ms:
        diagnostics.append(_diag("throughput_gate_failed", "$.run.v2_wall_time_ms"))
    if (
        run.legacy_orchestration_tokens
        < plan.minimum_token_reduction_ratio * run.v2_orchestration_tokens
    ):
        diagnostics.append(_diag("token_gate_failed", "$.run.v2_orchestration_tokens"))

    diagnostics.sort()
    return BenchmarkReport(
        plan_sha256=plan.content_id,
        oracle_sha256=oracle.content_id,
        run_sha256=run.content_id,
        decision=RolloutDecision.AUTHORIZE if not diagnostics else RolloutDecision.REJECT,
        diagnostics=tuple(diagnostics),
    )


def benchmark_json(value: BenchmarkPlan | OracleSuite | BenchmarkRun | BenchmarkReport) -> bytes:
    """Serialize one benchmark artifact as canonical UTF-8 JSON."""

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
