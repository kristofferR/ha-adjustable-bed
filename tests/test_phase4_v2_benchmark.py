from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.phase4_v2.benchmark import (
    REQUIRED_CONTRACT_ISSUES,
    REQUIRED_COVERAGE_TAGS,
    REQUIRED_MUTATIONS,
    AuditDecision,
    AuditReceipt,
    AuditSubjectKind,
    BenchmarkAuthority,
    BenchmarkCase,
    BenchmarkPlan,
    BenchmarkReport,
    BenchmarkRun,
    CandidateDisposition,
    CandidateResult,
    CaseOracle,
    CaseResult,
    ContractPin,
    EvidenceQuality,
    FindingIdentity,
    FindingResult,
    IndependentAuditSuite,
    MutationDeclaration,
    MutationKind,
    MutationResult,
    OracleSuite,
    RolloutDecision,
    TimingPhase,
    TimingSample,
    TimingSuite,
    TokenSample,
    benchmark_json,
    finalize_benchmark,
)

_DIGEST = "a" * 64
_AUDIT_KEY = Ed25519PrivateKey.from_private_bytes(b"a" * 32)
_TELEMETRY_KEY = Ed25519PrivateKey.from_private_bytes(b"t" * 32)


def _public_key(private_key: Ed25519PrivateKey) -> str:
    return (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        .hex()
    )


def _digest(index: int) -> str:
    return f"{index:064x}"


def _artifacts() -> tuple[
    BenchmarkAuthority,
    BenchmarkPlan,
    OracleSuite,
    BenchmarkRun,
    IndependentAuditSuite,
    TimingSuite,
]:
    authority = BenchmarkAuthority(
        contracts=tuple(
            ContractPin(issue, f"issue-{issue}-v1", _digest(issue))
            for issue in REQUIRED_CONTRACT_ISSUES
        ),
        corpus_sha256=_digest(1_000),
        run_identity_sha256=_digest(1_001),
        toolchain_sha256=_digest(1_002),
        harness_sha256=_digest(1_003),
        analyst_identity_sha256=_digest(1_004),
        mutation_runner_identity_sha256=_digest(1_005),
        auditor_identity_sha256=_sha256_hex(_public_key(_AUDIT_KEY)),
        auditor_public_key=_public_key(_AUDIT_KEY),
        telemetry_collector_identity_sha256=_sha256_hex(_public_key(_TELEMETRY_KEY)),
        telemetry_collector_public_key=_public_key(_TELEMETRY_KEY),
    )
    case_tags = (*sorted(REQUIRED_COVERAGE_TAGS), "simple-managed")
    identities = tuple(
        FindingIdentity("transport", f"finding-{index}", _digest(index + 1))
        for index, _tag in enumerate(case_tags)
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
            for index, _tag in enumerate(case_tags)
        )
    )
    plan = BenchmarkPlan(
        cases=tuple(
            BenchmarkCase(
                case_id=f"case-{index}",
                input_sha256=_digest(index + 100),
                coverage_tags=(tag,),
            )
            for index, tag in enumerate(case_tags)
        ),
        mutations=tuple(
            MutationDeclaration(kind, _digest(index + 300))
            for index, kind in enumerate(sorted(REQUIRED_MUTATIONS, key=lambda item: item.value))
        ),
        oracle_sha256=oracle.content_id,
        authority_sha256=authority.content_id,
    )
    cases = tuple(
        CaseResult(
            case_id=f"case-{index}",
            input_sha256=_digest(index + 100),
            findings=(FindingResult(identities[index], quality),),
            candidates=(
                CandidateResult(
                    f"candidate-{index}",
                    CandidateDisposition.MATERIAL_FINDING,
                    identities[index],
                ),
            ),
            completed_stack_routes=("jadx", "smali"),
        )
        for index, _tag in enumerate(case_tags)
    )
    mutations = tuple(
        MutationResult(
            declaration.kind,
            declaration.input_sha256,
            _digest(index + 400),
            True,
            _digest(index + 500),
        )
        for index, declaration in enumerate(plan.mutations)
    )
    run = BenchmarkRun(
        plan_sha256=plan.content_id,
        authority_sha256=authority.content_id,
        corpus_sha256=authority.corpus_sha256,
        run_identity_sha256=authority.run_identity_sha256,
        toolchain_sha256=authority.toolchain_sha256,
        harness_sha256=authority.harness_sha256,
        analyst_identity_sha256=authority.analyst_identity_sha256,
        mutation_runner_identity_sha256=authority.mutation_runner_identity_sha256,
        cases=cases,
        mutations=mutations,
    )
    audit_subjects = (
        *((AuditSubjectKind.CASE, item.case_id, item.content_id) for item in run.cases),
        *((AuditSubjectKind.MUTATION, item.kind.value, item.content_id) for item in run.mutations),
    )
    audits = _signed_audit_suite(
        IndependentAuditSuite(
            authority_sha256=authority.content_id,
            auditor_identity_sha256=authority.auditor_identity_sha256,
            receipts=tuple(
                sorted(
                    AuditReceipt(
                        kind,
                        subject_id,
                        subject_sha,
                        AuditDecision.ACCEPTED,
                        _digest(index + 700),
                        authority.auditor_identity_sha256,
                    )
                    for index, (kind, subject_id, subject_sha) in enumerate(audit_subjects)
                )
            ),
            signature="0" * 128,
        )
    )
    host = _digest(1_008)
    timings = _signed_timing_suite(
        TimingSuite(
            authority.content_id,
            authority.corpus_sha256,
            authority.run_identity_sha256,
            authority.telemetry_collector_identity_sha256,
            host,
            tuple(
                sorted(
                    sample
                    for index, case in enumerate(plan.cases)
                    for sample in (
                        TimingSample(
                            "trial-0",
                            case.case_id,
                            TimingPhase.LEGACY,
                            index * 10_000,
                            index * 10_000 + 3_000,
                            authority.telemetry_collector_identity_sha256,
                            host,
                        ),
                        TimingSample(
                            "trial-0",
                            case.case_id,
                            TimingPhase.V2,
                            index * 10_000 + 4_000,
                            index * 10_000 + 5_000,
                            authority.telemetry_collector_identity_sha256,
                            host,
                        ),
                    )
                )
            ),
            tuple(
                sorted(
                    sample
                    for case in plan.cases
                    for sample in (
                        TokenSample(
                            "trial-0",
                            case.case_id,
                            TimingPhase.LEGACY,
                            5_000,
                            authority.telemetry_collector_identity_sha256,
                        ),
                        TokenSample(
                            "trial-0",
                            case.case_id,
                            TimingPhase.V2,
                            1_000,
                            authority.telemetry_collector_identity_sha256,
                        ),
                    )
                )
            ),
            "0" * 128,
        )
    )
    return authority, plan, oracle, run, audits, timings


def _finalize(
    artifacts: tuple[
        BenchmarkAuthority,
        BenchmarkPlan,
        OracleSuite,
        BenchmarkRun,
        IndependentAuditSuite,
        TimingSuite,
    ],
) -> BenchmarkReport:
    return finalize_benchmark(*artifacts)


def test_complete_benchmark_authorizes_rollout_deterministically() -> None:
    artifacts = _artifacts()

    report = _finalize(artifacts)

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
        ("expensive", "token_gate_failed"),
    ],
)
def test_benchmark_rejects_each_quality_regression(change: str, code: str) -> None:
    authority, plan, oracle, run, _audits, timings = _artifacts()
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
                    first.findings[0].identity,
                    EvidenceQuality(1, True, ("jadx", "smali")),
                ),
            ),
        )
    elif change == "missing_stack":
        first = replace(first, completed_stack_routes=("jadx",))
    else:
        original_sample = next(
            item for item in timings.token_samples if item.phase is TimingPhase.V2
        )
        changed_sample = replace(
            original_sample,
            orchestration_tokens=1_001,
        )
        timings = _signed_timing_suite(
            replace(
                timings,
                token_samples=tuple(
                    sorted(
                        changed_sample if item == original_sample else item
                        for item in timings.token_samples
                    )
                ),
            )
        )
    if change != "expensive":
        run = replace(run, cases=(first, *run.cases[1:]))
    report = finalize_benchmark(
        authority,
        plan,
        oracle,
        run,
        _audit_suite(authority, run),
        timings,
    )

    assert report.decision is RolloutDecision.REJECT
    assert code in {item.code for item in report.diagnostics}


def test_benchmark_rejects_identity_contract_and_commitment_drift() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    changed = replace(authority, toolchain_sha256=_digest(9_999))

    report = finalize_benchmark(changed, plan, oracle, run, audits, timings)

    assert {
        "authority_commitment_mismatch",
        "run_authority_mismatch",
        "audit_authority_mismatch",
        "timing_authority_mismatch",
    } <= {item.code for item in report.diagnostics}


def test_authority_requires_exact_contract_set_and_independent_actors() -> None:
    authority, *_ = _artifacts()
    with pytest.raises(ValueError, match="exact ordered issues"):
        replace(authority, contracts=authority.contracts[:-1])
    with pytest.raises(ValueError, match="independent"):
        replace(
            authority,
            auditor_identity_sha256=authority.analyst_identity_sha256,
        )


def test_mutation_input_and_output_are_committed_and_independently_audited() -> None:
    authority, plan, oracle, run, _audits, timings = _artifacts()
    changed = replace(run.mutations[0], input_sha256=_digest(9_999))
    changed_run = replace(run, mutations=(changed, *run.mutations[1:]))
    audits = _audit_suite(authority, changed_run)

    report = finalize_benchmark(authority, plan, oracle, changed_run, audits, timings)

    assert "mutation_input_mismatch" in {item.code for item in report.diagnostics}
    with pytest.raises(ValueError, match="differ"):
        replace(changed, output_sha256=changed.input_sha256)


def test_case_cannot_self_attest_and_receipt_is_bound_to_exact_result() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    first = audits.receipts[0]
    wrong = replace(first, subject_sha256=_digest(9_999))
    bad_audits = replace(audits, receipts=(wrong, *audits.receipts[1:]))

    report = finalize_benchmark(authority, plan, oracle, run, bad_audits, timings)

    assert "audit_subject_mismatch" in {item.code for item in report.diagnostics}
    assert "audit_signature_invalid" in {item.code for item in report.diagnostics}
    assert "audit" not in CaseResult.__dataclass_fields__


def test_missing_or_rejected_independent_audit_rejects_rollout() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    missing = replace(audits, receipts=audits.receipts[1:])
    report = finalize_benchmark(authority, plan, oracle, run, missing, timings)
    assert "audit_subject_set_mismatch" in {item.code for item in report.diagnostics}

    rejected_receipt = replace(audits.receipts[0], decision=AuditDecision.REJECTED)
    rejected = replace(audits, receipts=(rejected_receipt, *audits.receipts[1:]))
    report = finalize_benchmark(authority, plan, oracle, run, rejected, timings)
    assert "independent_audit_rejected" in {item.code for item in report.diagnostics}


def test_raw_timing_pairs_and_provenance_are_required() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    missing_phase = replace(
        timings,
        samples=tuple(item for item in timings.samples if item.phase is TimingPhase.LEGACY),
    )
    report = finalize_benchmark(authority, plan, oracle, run, audits, missing_phase)
    assert {"throughput_gate_failed", "timing_phase_pair_mismatch"} <= {
        item.code for item in report.diagnostics
    }

    first = timings.samples[0]
    bad_sample = replace(first, collector_identity_sha256=_digest(9_999))
    bad_timings = replace(timings, samples=tuple(sorted((bad_sample, *timings.samples[1:]))))
    report = finalize_benchmark(authority, plan, oracle, run, audits, bad_timings)
    assert "timing_collector_mismatch" in {item.code for item in report.diagnostics}


def test_each_timing_and_token_pair_must_meet_the_ratio() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    legacy_timings = [item for item in timings.samples if item.phase is TimingPhase.LEGACY]
    timing_replacements = {
        legacy_timings[0]: replace(
            legacy_timings[0],
            finished_monotonic_ns=legacy_timings[0].started_monotonic_ns + 2_999,
        ),
        legacy_timings[1]: replace(
            legacy_timings[1],
            finished_monotonic_ns=legacy_timings[1].started_monotonic_ns + 3_001,
        ),
    }
    legacy_tokens = [item for item in timings.token_samples if item.phase is TimingPhase.LEGACY]
    token_replacements = {
        legacy_tokens[0]: replace(legacy_tokens[0], orchestration_tokens=4_999),
        legacy_tokens[1]: replace(legacy_tokens[1], orchestration_tokens=5_001),
    }
    changed = _signed_timing_suite(
        replace(
            timings,
            samples=tuple(sorted(timing_replacements.get(item, item) for item in timings.samples)),
            token_samples=tuple(
                sorted(token_replacements.get(item, item) for item in timings.token_samples)
            ),
        )
    )

    report = finalize_benchmark(authority, plan, oracle, run, audits, changed)

    assert {"throughput_gate_failed", "token_gate_failed"} <= {
        item.code for item in report.diagnostics
    }


def test_audit_and_timing_attestations_cannot_be_forged_by_copying_identity() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    forged_audits = replace(audits, signature="0" * 128)
    forged_timings = replace(timings, signature="0" * 128)

    report = finalize_benchmark(
        authority,
        plan,
        oracle,
        run,
        forged_audits,
        forged_timings,
    )

    assert {"audit_signature_invalid", "timing_signature_invalid"} <= {
        item.code for item in report.diagnostics
    }


def test_blind_plan_contains_no_oracle_findings_or_aggregate_timings() -> None:
    _authority, plan, _oracle, _run, _audits, _timings = _artifacts()

    payload = benchmark_json(plan)

    assert b"finding-" not in payload
    assert b"semantic_sha256" not in payload
    assert b"wall_time" not in payload


def test_plan_case_count_tracks_coverage_contract_without_hardcoded_fixture_count() -> None:
    _authority, plan, *_rest = _artifacts()
    assert len(plan.cases) == len(REQUIRED_COVERAGE_TAGS) + 1


def test_candidate_finding_must_exist_in_case_results() -> None:
    authority, plan, oracle, run, _audits, timings = _artifacts()
    first = run.cases[0]
    unknown = FindingIdentity("transport", "unknown", "f" * 64)
    first = replace(
        first,
        candidates=(
            CandidateResult("candidate-0", CandidateDisposition.MATERIAL_FINDING, unknown),
        ),
    )
    changed_run = replace(run, cases=(first, *run.cases[1:]))

    report = finalize_benchmark(
        authority,
        plan,
        oracle,
        changed_run,
        _audit_suite(authority, changed_run),
        timings,
    )

    assert "candidate_finding_missing" in {item.code for item in report.diagnostics}


def test_runtime_types_are_strict() -> None:
    authority, _plan, _oracle, run, _audits, _timings = _artifacts()
    with pytest.raises(ValueError, match="CandidateDisposition"):
        CandidateResult("candidate", cast(CandidateDisposition, "UNEXPLAINED"))
    with pytest.raises(ValueError, match="MutationKind"):
        MutationDeclaration(cast(MutationKind, "REMOVED_CALLSITE"), _DIGEST)
    with pytest.raises(ValueError, match="package bound"):
        EvidenceQuality(1, cast(bool, 1), ("jadx",))
    with pytest.raises(ValueError, match="mutation detected"):
        replace(run.mutations[0], detected=cast(bool, 1))
    with pytest.raises(ValueError, match="RolloutDecision"):
        BenchmarkReport(
            authority.content_id,
            _DIGEST,
            _DIGEST,
            _DIGEST,
            _DIGEST,
            _DIGEST,
            cast(RolloutDecision, "AUTHORIZE"),
            (),
        )


def _audit_suite(authority: BenchmarkAuthority, run: BenchmarkRun) -> IndependentAuditSuite:
    subjects = (
        *((AuditSubjectKind.CASE, item.case_id, item.content_id) for item in run.cases),
        *((AuditSubjectKind.MUTATION, item.kind.value, item.content_id) for item in run.mutations),
    )
    return _signed_audit_suite(
        IndependentAuditSuite(
            authority.content_id,
            authority.auditor_identity_sha256,
            tuple(
                sorted(
                    AuditReceipt(
                        kind,
                        subject_id,
                        digest,
                        AuditDecision.ACCEPTED,
                        _digest(index + 7_000),
                        authority.auditor_identity_sha256,
                    )
                    for index, (kind, subject_id, digest) in enumerate(subjects)
                )
            ),
            "0" * 128,
        )
    )


def _signed_audit_suite(suite: IndependentAuditSuite) -> IndependentAuditSuite:
    return replace(suite, signature=_AUDIT_KEY.sign(suite.signing_bytes).hex())


def _signed_timing_suite(suite: TimingSuite) -> TimingSuite:
    return replace(suite, signature=_TELEMETRY_KEY.sign(suite.signing_bytes).hex())


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(bytes.fromhex(value)).hexdigest()
