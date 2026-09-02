from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tools.phase4_v2.benchmark import (
    REQUIRED_COVERAGE_TAGS,
    REQUIRED_MUTATIONS,
    AuditDecision,
    BenchmarkCase,
    BenchmarkPlan,
    BenchmarkReport,
    BenchmarkRun,
    CandidateDisposition,
    CandidateResult,
    CaseOracle,
    CaseResult,
    EvidenceQuality,
    FindingIdentity,
    FindingResult,
    MutationKind,
    MutationResult,
    OracleSuite,
    RolloutDecision,
    benchmark_json,
    finalize_benchmark,
)

_DIGEST = "a" * 64


def _artifacts() -> tuple[BenchmarkPlan, OracleSuite, BenchmarkRun]:
    identities = tuple(
        FindingIdentity("transport", f"finding-{index}", f"{index + 1:064x}") for index in range(8)
    )
    quality = EvidenceQuality(2, True, ("jadx", "smali"))
    oracle = OracleSuite(
        tuple(
            CaseOracle(
                case_id=f"case-{index}",
                findings=((identities[index], quality),),
                candidate_ids=(f"candidate-{index}",),
                required_stack_routes=("jadx", "smali"),
            )
            for index in range(8)
        )
    )
    plan = BenchmarkPlan(
        cases=tuple(
            BenchmarkCase(
                case_id=f"case-{index}",
                input_sha256=f"{index + 100:064x}",
                coverage_tags=(tag,),
            )
            for index, tag in enumerate((*sorted(REQUIRED_COVERAGE_TAGS), "simple-managed"))
        ),
        oracle_sha256=oracle.content_id,
    )
    run = BenchmarkRun(
        plan_sha256=plan.content_id,
        cases=tuple(
            CaseResult(
                case_id=f"case-{index}",
                input_sha256=f"{index + 100:064x}",
                findings=(FindingResult(identities[index], quality),),
                candidates=(
                    CandidateResult(
                        f"candidate-{index}",
                        CandidateDisposition.MATERIAL_FINDING,
                        identities[index],
                    ),
                ),
                completed_stack_routes=("jadx", "smali"),
                audit=AuditDecision.ACCEPTED,
                audit_receipt_sha256=f"{index + 700:064x}",
            )
            for index in range(8)
        ),
        mutations=tuple(
            MutationResult(kind, True, f"{index + 500:064x}")
            for index, kind in enumerate(sorted(REQUIRED_MUTATIONS, key=lambda item: item.value))
        ),
        legacy_wall_time_ms=3_000,
        v2_wall_time_ms=1_000,
        legacy_orchestration_tokens=5_000,
        v2_orchestration_tokens=1_000,
    )
    return plan, oracle, run


def test_complete_benchmark_authorizes_rollout_deterministically() -> None:
    plan, oracle, run = _artifacts()

    report = finalize_benchmark(plan, oracle, run)

    assert report.decision is RolloutDecision.AUTHORIZE
    assert not report.diagnostics
    assert benchmark_json(report) == benchmark_json(report)
    assert len(report.content_id) == 64


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("missing_finding", "material_finding_missing"),
        ("unexplained_candidate", "unexplained_ble_candidate"),
        ("weak_evidence", "evidence_anchor_regression"),
        ("missing_stack", "case_stack_coverage_regression"),
        ("audit_rejected", "independent_audit_rejected"),
        ("slow", "throughput_gate_failed"),
        ("expensive", "token_gate_failed"),
    ],
)
def test_benchmark_rejects_each_quality_regression(change: str, code: str) -> None:
    plan, oracle, run = _artifacts()
    first = run.cases[0]
    if change == "missing_finding":
        first = replace(first, findings=())
    elif change == "unexplained_candidate":
        first = replace(
            first,
            candidates=(CandidateResult("candidate-0", CandidateDisposition.UNEXPLAINED),),
        )
    elif change == "weak_evidence":
        first = replace(
            first,
            findings=(
                FindingResult(
                    first.findings[0].identity, EvidenceQuality(1, True, ("jadx", "smali"))
                ),
            ),
        )
    elif change == "missing_stack":
        first = replace(first, completed_stack_routes=("jadx",))
    elif change == "audit_rejected":
        first = replace(first, audit=AuditDecision.REJECTED)
    elif change == "slow":
        run = replace(run, v2_wall_time_ms=1_001)
    else:
        run = replace(run, v2_orchestration_tokens=1_001)
    if change not in {"slow", "expensive"}:
        run = replace(run, cases=(first, *run.cases[1:]))

    report = finalize_benchmark(plan, oracle, run)

    assert report.decision is RolloutDecision.REJECT
    assert code in {item.code for item in report.diagnostics}


def test_benchmark_rejects_oracle_plan_and_mutation_drift() -> None:
    plan, oracle, run = _artifacts()
    run = replace(run, plan_sha256=_DIGEST, mutations=run.mutations[:-1])
    plan = replace(plan, oracle_sha256=_DIGEST)

    report = finalize_benchmark(plan, oracle, run)

    assert report.decision is RolloutDecision.REJECT
    assert {
        "mutation_set_mismatch",
        "oracle_commitment_mismatch",
        "plan_commitment_mismatch",
    } <= {item.code for item in report.diagnostics}


def test_blind_plan_contains_no_oracle_findings() -> None:
    plan, _oracle, _run = _artifacts()

    payload = benchmark_json(plan)

    assert b"finding-" not in payload
    assert b"semantic_sha256" not in payload


def test_plan_requires_eight_to_twelve_sorted_cases() -> None:
    with pytest.raises(ValueError, match="8 to 12"):
        BenchmarkPlan(
            cases=(BenchmarkCase("case-0", _DIGEST, ("managed",)),),
            oracle_sha256=_DIGEST,
        )


def test_plan_requires_every_holdout_coverage_class() -> None:
    plan, _oracle, _run = _artifacts()
    cases = tuple(replace(item, coverage_tags=("simple-managed",)) for item in plan.cases)

    with pytest.raises(ValueError, match="missing required coverage tags"):
        replace(plan, cases=cases)


def test_candidate_finding_must_exist_in_case_results() -> None:
    plan, oracle, run = _artifacts()
    first = run.cases[0]
    unknown = FindingIdentity("transport", "unknown", "f" * 64)
    first = replace(
        first,
        candidates=(
            CandidateResult("candidate-0", CandidateDisposition.MATERIAL_FINDING, unknown),
        ),
    )

    report = finalize_benchmark(plan, oracle, replace(run, cases=(first, *run.cases[1:])))

    assert "candidate_finding_missing" in {item.code for item in report.diagnostics}


def test_unexpected_material_finding_requires_new_frozen_oracle() -> None:
    plan, oracle, run = _artifacts()
    first = run.cases[0]
    novel = FindingIdentity("transport", "novel", "f" * 64)
    first = replace(
        first,
        findings=tuple(
            sorted(
                (*first.findings, FindingResult(novel, EvidenceQuality(1, True, ("jadx",)))),
                key=lambda item: item.identity,
            )
        ),
    )

    report = finalize_benchmark(plan, oracle, replace(run, cases=(first, *run.cases[1:])))

    assert report.decision is RolloutDecision.REJECT
    assert "unexpected_material_finding" in {item.code for item in report.diagnostics}


def test_runtime_enum_types_are_strict() -> None:
    plan, _oracle, run = _artifacts()
    first = run.cases[0]

    with pytest.raises(ValueError, match="CandidateDisposition"):
        CandidateResult("candidate", cast(CandidateDisposition, "UNEXPLAINED"))
    with pytest.raises(ValueError, match="AuditDecision"):
        replace(first, audit=cast(AuditDecision, "ACCEPTED"))
    with pytest.raises(ValueError, match="MutationKind"):
        MutationResult(cast(MutationKind, "REMOVED_CALLSITE"), True, plan.oracle_sha256)


def test_runtime_boolean_types_are_strict() -> None:
    with pytest.raises(ValueError, match="package bound"):
        EvidenceQuality(1, cast(bool, 1), ("jadx",))
    with pytest.raises(ValueError, match="mutation detected"):
        MutationResult(next(iter(REQUIRED_MUTATIONS)), cast(bool, 1), _DIGEST)


def test_candidate_finding_runtime_type_is_strict() -> None:
    with pytest.raises(ValueError, match="FindingIdentity"):
        CandidateResult(
            "candidate",
            CandidateDisposition.MATERIAL_FINDING,
            cast(FindingIdentity, "finding"),
        )


def test_report_runtime_types_are_strict() -> None:
    with pytest.raises(ValueError, match="RolloutDecision"):
        BenchmarkReport(
            _DIGEST,
            _DIGEST,
            _DIGEST,
            cast(RolloutDecision, "AUTHORIZE"),
            (),
        )
    with pytest.raises(ValueError, match="unsupported benchmark revision"):
        BenchmarkReport(
            _DIGEST,
            _DIGEST,
            _DIGEST,
            RolloutDecision.REJECT,
            (),
            revision="future",
        )
