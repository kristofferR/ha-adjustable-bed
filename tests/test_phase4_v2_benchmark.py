from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import replace
from typing import cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.phase4_v2.benchmark import (
    BENCHMARK_REVISION,
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
    CorpusManifest,
    CorpusMember,
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
    TrialSchedule,
    TrustedBenchmarkAuthority,
    benchmark_json,
)
from tools.phase4_v2.benchmark import (
    finalize_benchmark as production_finalize_benchmark,
)
from tools.phase4_v2.benchmark import (
    load_trusted_benchmark_authority as production_load_trusted_benchmark_authority,
)
from tools.phase4_v2.benchmark import model as benchmark_model
from tools.phase4_v2.benchmark.testing import BenchmarkAuthorityTestDeployment

_DIGEST = "a" * 64
_AUTHORITY_KEY = Ed25519PrivateKey.from_private_bytes(b"r" * 32)
_ANALYST_KEY = Ed25519PrivateKey.from_private_bytes(b"l" * 32)
_MUTATION_KEY = Ed25519PrivateKey.from_private_bytes(b"m" * 32)
_AUDIT_KEY = Ed25519PrivateKey.from_private_bytes(b"a" * 32)
_TELEMETRY_KEY = Ed25519PrivateKey.from_private_bytes(b"t" * 32)
_TEST_DEPLOYMENT: BenchmarkAuthorityTestDeployment | None = None


@pytest.fixture(autouse=True)
def _protected_config_test_seam() -> None:
    global _TEST_DEPLOYMENT
    _TEST_DEPLOYMENT = BenchmarkAuthorityTestDeployment(b"")


def load_trusted_benchmark_authority(raw: bytes) -> TrustedBenchmarkAuthority:
    if _TEST_DEPLOYMENT is None:
        raise AssertionError("protected config test seam was not installed")
    return _TEST_DEPLOYMENT.load(raw)


def finalize_benchmark(
    authority: TrustedBenchmarkAuthority,
    plan: BenchmarkPlan,
    oracle: OracleSuite,
    run: BenchmarkRun,
    audits: IndependentAuditSuite,
    timings: TimingSuite,
) -> BenchmarkReport:
    if _TEST_DEPLOYMENT is None:
        raise AssertionError("protected config test seam was not installed")
    return _TEST_DEPLOYMENT.finalize(authority, plan, oracle, run, audits, timings)


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
    TrustedBenchmarkAuthority,
    BenchmarkPlan,
    OracleSuite,
    BenchmarkRun,
    IndependentAuditSuite,
    TimingSuite,
]:
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
    mutations = tuple(
        MutationDeclaration(kind, f"mutation-{index}", _digest(index + 300))
        for index, kind in enumerate(sorted(REQUIRED_MUTATIONS, key=lambda item: item.value))
    )
    manifest = CorpusManifest(
        tuple(
            sorted(
                (
                    *(
                        CorpusMember(f"case-{index}", _digest(index + 100))
                        for index in range(len(case_tags))
                    ),
                    *(CorpusMember(item.corpus_member_id, item.input_sha256) for item in mutations),
                )
            )
        )
    )
    plan = BenchmarkPlan(
        cases=tuple(
            BenchmarkCase(
                case_id=f"case-{index}",
                corpus_member_id=f"case-{index}",
                input_sha256=_digest(index + 100),
                coverage_tags=(tag,),
            )
            for index, tag in enumerate(case_tags)
        ),
        mutations=mutations,
        trial_schedule=TrialSchedule(("trial-a", "trial-b")),
        oracle_sha256=oracle.content_id,
        authority_sha256=_DIGEST,
    )
    authority = _signed_authority(
        BenchmarkAuthority(
            contracts=tuple(
                ContractPin(issue, f"issue-{issue}-v1", _digest(issue))
                for issue in REQUIRED_CONTRACT_ISSUES
            ),
            plan_contract_sha256=plan.contract_id,
            oracle_sha256=oracle.content_id,
            trial_schedule_sha256=plan.trial_schedule.content_id,
            corpus_manifest=manifest,
            corpus_sha256=manifest.content_id,
            run_identity_sha256=_digest(1_001),
            toolchain_sha256=_digest(1_002),
            harness_sha256=_digest(1_003),
            execution_nonce_sha256=_digest(1_004),
            analyst_identity_sha256=_sha256_hex(_public_key(_ANALYST_KEY)),
            analyst_public_key=_public_key(_ANALYST_KEY),
            mutation_runner_identity_sha256=_sha256_hex(_public_key(_MUTATION_KEY)),
            mutation_runner_public_key=_public_key(_MUTATION_KEY),
            auditor_identity_sha256=_sha256_hex(_public_key(_AUDIT_KEY)),
            auditor_public_key=_public_key(_AUDIT_KEY),
            telemetry_collector_identity_sha256=_sha256_hex(_public_key(_TELEMETRY_KEY)),
            telemetry_collector_public_key=_public_key(_TELEMETRY_KEY),
            generation=1,
            signature="0" * 128,
        )
    )
    plan = replace(plan, authority_sha256=authority.content_id)
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
    mutation_results = tuple(
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
        oracle_sha256=oracle.content_id,
        authority_sha256=authority.content_id,
        corpus_sha256=authority.corpus_sha256,
        run_identity_sha256=authority.run_identity_sha256,
        toolchain_sha256=authority.toolchain_sha256,
        harness_sha256=authority.harness_sha256,
        execution_nonce_sha256=authority.execution_nonce_sha256,
        analyst_identity_sha256=authority.analyst_identity_sha256,
        mutation_runner_identity_sha256=authority.mutation_runner_identity_sha256,
        cases=cases,
        mutations=mutation_results,
        analyst_signature="0" * 128,
        mutation_runner_signature="0" * 128,
    )
    run = _signed_run(run)
    audit_subjects = (
        *((AuditSubjectKind.CASE, item.case_id, item.content_id) for item in run.cases),
        *((AuditSubjectKind.MUTATION, item.kind.value, item.content_id) for item in run.mutations),
    )
    audits = _signed_audit_suite(
        IndependentAuditSuite(
            authority_sha256=authority.content_id,
            plan_sha256=plan.content_id,
            oracle_sha256=oracle.content_id,
            run_sha256=run.content_id,
            execution_nonce_sha256=authority.execution_nonce_sha256,
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
            authority_sha256=authority.content_id,
            plan_sha256=plan.content_id,
            oracle_sha256=oracle.content_id,
            run_sha256=run.content_id,
            execution_nonce_sha256=authority.execution_nonce_sha256,
            corpus_sha256=authority.corpus_sha256,
            run_identity_sha256=authority.run_identity_sha256,
            collector_identity_sha256=authority.telemetry_collector_identity_sha256,
            host_identity_sha256=host,
            samples=tuple(
                sorted(
                    sample
                    for trial_index, trial_id in enumerate(plan.trial_schedule.trial_ids)
                    for index, case in enumerate(plan.cases)
                    for sample in (
                        TimingSample(
                            trial_id,
                            case.case_id,
                            TimingPhase.LEGACY,
                            trial_index * 1_000_000 + index * 10_000,
                            trial_index * 1_000_000 + index * 10_000 + 3_000,
                            authority.telemetry_collector_identity_sha256,
                            host,
                        ),
                        TimingSample(
                            trial_id,
                            case.case_id,
                            TimingPhase.V2,
                            trial_index * 1_000_000 + index * 10_000 + 4_000,
                            trial_index * 1_000_000 + index * 10_000 + 5_000,
                            authority.telemetry_collector_identity_sha256,
                            host,
                        ),
                    )
                )
            ),
            token_samples=tuple(
                sorted(
                    sample
                    for trial_id in plan.trial_schedule.trial_ids
                    for case in plan.cases
                    for sample in (
                        TokenSample(
                            trial_id,
                            case.case_id,
                            TimingPhase.LEGACY,
                            5_000,
                            authority.telemetry_collector_identity_sha256,
                        ),
                        TokenSample(
                            trial_id,
                            case.case_id,
                            TimingPhase.V2,
                            1_000,
                            authority.telemetry_collector_identity_sha256,
                        ),
                    )
                )
            ),
            signature="0" * 128,
        )
    )
    trusted = _trusted(authority)
    return trusted, plan, oracle, run, audits, timings


def _finalize(
    artifacts: tuple[
        TrustedBenchmarkAuthority,
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
    trusted, plan, oracle, run, audits, timings = _artifacts()
    changed = _signed_authority(
        replace(
            _authority_for_test(trusted),
            toolchain_sha256=_digest(9_999),
            signature="0" * 128,
        )
    )

    with pytest.raises(ValueError, match="protected benchmark authority"):
        finalize_benchmark(
            cast(TrustedBenchmarkAuthority, changed), plan, oracle, run, audits, timings
        )
    with pytest.raises(ValueError, match="bytes do not match"):
        load_trusted_benchmark_authority(
            benchmark_json(changed),
        )


def test_authority_requires_exact_contract_set_and_independent_actors() -> None:
    trusted, *_ = _artifacts()
    authority = _authority_for_test(trusted)
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


def test_protected_authority_loader_rejects_self_issuance_wrong_pins_and_noncanonical_json() -> (
    None
):
    trusted, plan, oracle, run, audits, timings = _artifacts()
    authority = _authority_for_test(trusted)

    assert _trusted(authority).content_id == authority.content_id
    protected_slot = "_canonical_bytes"
    with pytest.raises(AttributeError, match="immutable"):
        setattr(trusted, protected_slot, replace(authority, harness_sha256=_digest(9_999)))
    with pytest.raises(AttributeError, match="immutable"):
        delattr(trusted, protected_slot)
    with pytest.raises(ValueError, match="protected benchmark authority"):
        finalize_benchmark(
            cast(TrustedBenchmarkAuthority, authority),
            plan,
            oracle,
            run,
            audits,
            timings,
        )
    wrong_key = Ed25519PrivateKey.from_private_bytes(b"w" * 32)
    self_issued = replace(authority, signature="0" * 128)
    self_issued = replace(self_issued, signature=wrong_key.sign(self_issued.signing_bytes).hex())
    with pytest.raises(ValueError, match="bytes do not match"):
        load_trusted_benchmark_authority(
            benchmark_json(self_issued),
        )
    with pytest.raises(ValueError, match="canonical JSON"):
        load_trusted_benchmark_authority(
            benchmark_json(authority).replace(b'"contracts":', b'"contracts" :', 1),
        )


def test_protected_config_pins_generation_and_finalize_reverifies_retained_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, plan, oracle, run, audits, timings = _artifacts()
    authority = _authority_for_test(trusted)
    replay = _signed_authority(replace(authority, generation=2, signature="0" * 128))
    replay_bytes = benchmark_json(replay)
    _write_test_config(replay_bytes, generation=1)
    with pytest.raises(ValueError, match="generation does not match"):
        load_trusted_benchmark_authority(replay_bytes)

    _write_test_config(replay_bytes, generation=replay.generation)
    with pytest.raises(ValueError, match="rotated after authority load"):
        finalize_benchmark(trusted, plan, oracle, run, audits, timings)
    if _TEST_DEPLOYMENT is None:
        raise AssertionError("protected config test seam was not installed")
    rotated_config = benchmark_model._parse_protected_authority_config(
        _TEST_DEPLOYMENT.protected_config
    )
    reloads = 0

    def reload_rotated_config() -> object:
        nonlocal reloads
        reloads += 1
        return rotated_config

    monkeypatch.setattr(benchmark_model, "_load_protected_authority_config", reload_rotated_config)
    with pytest.raises(ValueError, match="rotated after authority load"):
        production_finalize_benchmark(trusted, plan, oracle, run, audits, timings)
    assert reloads == 1

    _write_test_config(benchmark_json(authority), generation=authority.generation)
    object.__setattr__(trusted, "_canonical_bytes", replay_bytes)
    with pytest.raises(ValueError, match="bytes do not match"):
        finalize_benchmark(trusted, plan, oracle, run, audits, timings)


def test_production_config_source_ignores_injected_global(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted, *_ = _artifacts()
    authority = _authority_for_test(trusted)
    opened: list[object] = []

    def unavailable(path: object, *_args: object, **_kwargs: object) -> int:
        opened.append(path)
        raise FileNotFoundError

    with monkeypatch.context() as patched:
        patched.setattr(
            benchmark_model, "_PROTECTED_AUTHORITY_CONFIG_PATH", "/attacker", raising=False
        )
        patched.setattr(benchmark_model.os, "open", unavailable)
        with pytest.raises(ValueError, match="config is unavailable"):
            production_load_trusted_benchmark_authority(benchmark_json(authority))

    assert opened == ["/etc/ha-adjustable-bed"]


def test_protected_config_rejects_non_root_owner_and_unsafe_parent() -> None:
    non_root_file = os.stat_result((stat.S_IFREG | 0o600, 0, 0, 1, 1_000, 0, 0, 0, 0, 0))
    unsafe_parent = os.stat_result((stat.S_IFDIR | 0o722, 0, 0, 1, 0, 0, 0, 0, 0, 0))
    symlink_file = os.stat_result((stat.S_IFLNK | 0o600, 0, 0, 1, 0, 0, 0, 0, 0, 0))
    writable_file = os.stat_result((stat.S_IFREG | 0o606, 0, 0, 1, 0, 0, 0, 0, 0, 0))
    plain_parent = os.stat_result((stat.S_IFREG | 0o700, 0, 0, 1, 0, 0, 0, 0, 0, 0))

    with pytest.raises(ValueError, match="ownership or mode is unsafe"):
        benchmark_model._validate_protected_file(non_root_file)
    with pytest.raises(ValueError, match="must be a regular file"):
        benchmark_model._validate_protected_file(symlink_file)
    with pytest.raises(ValueError, match="ownership or mode is unsafe"):
        benchmark_model._validate_protected_file(writable_file)
    with pytest.raises(ValueError, match="parent ownership or mode is unsafe"):
        benchmark_model._validate_protected_directory(unsafe_parent)
    with pytest.raises(ValueError, match="parent must be a directory"):
        benchmark_model._validate_protected_directory(plain_parent)


def test_protected_authority_loader_rejects_duplicate_keys_and_parser_bounds() -> None:
    trusted, *_ = _artifacts()
    authority = _authority_for_test(trusted)
    raw = benchmark_json(authority)
    duplicate = raw.replace(
        b"{",
        b'{"revision":"' + BENCHMARK_REVISION.encode() + b'",',
        1,
    )
    with pytest.raises(ValueError, match="strict JSON"):
        load_trusted_benchmark_authority(
            duplicate,
        )
    with pytest.raises(ValueError, match="size limit"):
        load_trusted_benchmark_authority(
            b" " * (64 * 1024 + 1),
        )
    with pytest.raises(ValueError, match="depth limit"):
        load_trusted_benchmark_authority(
            (b"[" * 13) + b"0" + (b"]" * 13),
        )
    with pytest.raises(ValueError, match="node limit"):
        load_trusted_benchmark_authority(
            b"[" + b",".join(b"0" for _ in range(513)) + b"]",
        )


def test_audit_and_telemetry_suites_cannot_replay_across_plan_or_run() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    changed_plan = replace(plan, minimum_throughput_ratio=2)
    changed_run = _signed_run(replace(run, plan_sha256=changed_plan.content_id))

    report = finalize_benchmark(
        authority,
        changed_plan,
        oracle,
        changed_run,
        audits,
        timings,
    )

    assert {"audit_context_mismatch", "timing_authority_mismatch"} <= {
        item.code for item in report.diagnostics
    }

    changed_case = replace(run.cases[0], completed_stack_routes=("jadx",))
    transplanted_run = _signed_run(replace(run, cases=(changed_case, *run.cases[1:])))
    report = finalize_benchmark(
        authority,
        plan,
        oracle,
        transplanted_run,
        audits,
        timings,
    )
    assert {"audit_context_mismatch", "timing_authority_mismatch"} <= {
        item.code for item in report.diagnostics
    }


def test_authority_rejects_substituted_oracle_and_trial_schedule() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    changed_oracle = replace(
        oracle,
        cases=(
            replace(oracle.cases[0], candidate_ids=("substituted-candidate",)),
            *oracle.cases[1:],
        ),
    )
    changed_plan = replace(plan, oracle_sha256=changed_oracle.content_id)
    report = finalize_benchmark(authority, changed_plan, changed_oracle, run, audits, timings)
    assert {"authority_oracle_mismatch", "plan_contract_mismatch"} <= {
        item.code for item in report.diagnostics
    }

    changed_schedule = TrialSchedule(tuple(reversed(plan.trial_schedule.trial_ids)))
    changed_plan = replace(plan, trial_schedule=changed_schedule)
    report = finalize_benchmark(authority, changed_plan, oracle, run, audits, timings)
    assert {"authority_trial_schedule_mismatch", "plan_contract_mismatch"} <= {
        item.code for item in report.diagnostics
    }


def test_signed_authority_rejects_substituted_corpus_manifest() -> None:
    trusted, *_ = _artifacts()
    authority = _authority_for_test(trusted)
    changed_member = replace(authority.corpus_manifest.members[0], input_sha256=_digest(9_999))
    changed_manifest = CorpusManifest(
        tuple(sorted((changed_member, *authority.corpus_manifest.members[1:])))
    )
    substituted = replace(
        authority,
        corpus_manifest=changed_manifest,
        corpus_sha256=changed_manifest.content_id,
    )

    with pytest.raises(ValueError, match="bytes do not match"):
        load_trusted_benchmark_authority(
            benchmark_json(substituted),
        )


def test_caller_config_cannot_mint_or_finalize_a_trusted_authority() -> None:
    assert not hasattr(benchmark_model, "_AUTHORITY_SEAL")
    assert not hasattr(benchmark_model, "_load_trusted_benchmark_authority_with_config")
    assert not hasattr(benchmark_model, "_finalize_benchmark_with_config")
    with pytest.raises(ValueError, match="protected configuration"):
        TrustedBenchmarkAuthority()


def test_every_case_and_mutation_must_prove_exact_corpus_membership() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    changed_case = replace(plan.cases[0], corpus_member_id=plan.mutations[0].corpus_member_id)
    changed_plan = replace(plan, cases=(changed_case, *plan.cases[1:]))
    report = finalize_benchmark(authority, changed_plan, oracle, run, audits, timings)
    assert {
        "case_corpus_membership_invalid",
        "corpus_member_reused",
        "corpus_member_set_mismatch",
    } <= {item.code for item in report.diagnostics}

    changed_mutation = replace(plan.mutations[0], corpus_member_id=plan.cases[0].corpus_member_id)
    changed_plan = replace(plan, mutations=(changed_mutation, *plan.mutations[1:]))
    report = finalize_benchmark(authority, changed_plan, oracle, run, audits, timings)
    assert "mutation_corpus_membership_invalid" in {item.code for item in report.diagnostics}

    duplicated_case = replace(plan.cases[1], corpus_member_id=plan.cases[0].corpus_member_id)
    changed_plan = replace(plan, cases=(plan.cases[0], duplicated_case, *plan.cases[2:]))
    report = finalize_benchmark(authority, changed_plan, oracle, run, audits, timings)
    assert {"corpus_member_reused", "corpus_member_set_mismatch"} <= {
        item.code for item in report.diagnostics
    }


def test_manifest_cannot_contain_unassigned_extra_member() -> None:
    trusted, plan, oracle, run, audits, timings = _artifacts()
    authority = _authority_for_test(trusted)
    manifest = CorpusManifest(
        tuple(
            sorted(
                (*authority.corpus_manifest.members, CorpusMember("unused-extra", _digest(9_999)))
            )
        )
    )
    expanded = _signed_authority(
        replace(
            authority,
            corpus_manifest=manifest,
            corpus_sha256=manifest.content_id,
            signature="0" * 128,
        )
    )
    expanded_trusted = _trusted(expanded)
    expanded_plan = replace(plan, authority_sha256=expanded.content_id)

    report = finalize_benchmark(expanded_trusted, expanded_plan, oracle, run, audits, timings)

    assert "corpus_member_set_mismatch" in {item.code for item in report.diagnostics}

    with pytest.raises(ValueError, match="member ids must be unique"):
        CorpusManifest(
            (
                CorpusMember("duplicate", _digest(1)),
                CorpusMember("duplicate", _digest(2)),
            )
        )


def test_signed_subset_of_frozen_trial_schedule_is_rejected() -> None:
    authority, plan, oracle, run, audits, timings = _artifacts()
    subset = _signed_timing_suite(
        replace(
            timings,
            samples=tuple(item for item in timings.samples if item.trial_id == "trial-a"),
            token_samples=tuple(
                item for item in timings.token_samples if item.trial_id == "trial-a"
            ),
        )
    )

    report = finalize_benchmark(authority, plan, oracle, run, audits, subset)

    assert {"timing_schedule_mismatch", "token_schedule_mismatch"} <= {
        item.code for item in report.diagnostics
    }


@pytest.mark.parametrize(
    ("actor", "code"),
    [
        ("analyst", "analyst_signature_invalid"),
        ("mutation", "mutation_runner_signature_invalid"),
    ],
)
def test_run_producers_must_use_their_distinct_pinned_keys(actor: str, code: str) -> None:
    authority, plan, oracle, run, _audits, timings = _artifacts()
    if actor == "analyst":
        changed_run = _signed_run(run, analyst_key=_MUTATION_KEY)
    else:
        changed_run = _signed_run(run, mutation_key=_ANALYST_KEY)
    audits = _audit_suite(authority, changed_run)
    timings = _signed_timing_suite(replace(timings, run_sha256=changed_run.content_id))

    report = finalize_benchmark(authority, plan, oracle, changed_run, audits, timings)

    assert code in {item.code for item in report.diagnostics}


def test_trial_schedule_rejects_duplicates_and_unbounded_counts() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        TrialSchedule(("trial-a", "trial-a"))
    with pytest.raises(ValueError, match="1 to 1000"):
        TrialSchedule(tuple(f"trial-{index}" for index in range(1_001)))


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
        MutationDeclaration(cast(MutationKind, "REMOVED_CALLSITE"), "member", _DIGEST)
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


def _audit_suite(
    authority: BenchmarkAuthority | TrustedBenchmarkAuthority,
    run: BenchmarkRun,
) -> IndependentAuditSuite:
    authority_data = (
        _authority_for_test(authority)
        if type(authority) is TrustedBenchmarkAuthority
        else authority
    )
    subjects = (
        *((AuditSubjectKind.CASE, item.case_id, item.content_id) for item in run.cases),
        *((AuditSubjectKind.MUTATION, item.kind.value, item.content_id) for item in run.mutations),
    )
    return _signed_audit_suite(
        IndependentAuditSuite(
            authority_sha256=authority.content_id,
            plan_sha256=run.plan_sha256,
            oracle_sha256=run.oracle_sha256,
            run_sha256=run.content_id,
            execution_nonce_sha256=run.execution_nonce_sha256,
            auditor_identity_sha256=authority_data.auditor_identity_sha256,
            receipts=tuple(
                sorted(
                    AuditReceipt(
                        kind,
                        subject_id,
                        digest,
                        AuditDecision.ACCEPTED,
                        _digest(index + 7_000),
                        authority_data.auditor_identity_sha256,
                    )
                    for index, (kind, subject_id, digest) in enumerate(subjects)
                )
            ),
            signature="0" * 128,
        )
    )


def _signed_audit_suite(suite: IndependentAuditSuite) -> IndependentAuditSuite:
    return replace(suite, signature=_AUDIT_KEY.sign(suite.signing_bytes).hex())


def _signed_timing_suite(suite: TimingSuite) -> TimingSuite:
    return replace(suite, signature=_TELEMETRY_KEY.sign(suite.signing_bytes).hex())


def _signed_run(
    run: BenchmarkRun,
    *,
    analyst_key: Ed25519PrivateKey = _ANALYST_KEY,
    mutation_key: Ed25519PrivateKey = _MUTATION_KEY,
) -> BenchmarkRun:
    analyst_signed = replace(
        run,
        analyst_signature=analyst_key.sign(run.analyst_signing_bytes).hex(),
    )
    return replace(
        analyst_signed,
        mutation_runner_signature=mutation_key.sign(
            analyst_signed.mutation_runner_signing_bytes
        ).hex(),
    )


def _signed_authority(authority: BenchmarkAuthority) -> BenchmarkAuthority:
    return replace(
        authority,
        signature=_AUTHORITY_KEY.sign(authority.signing_bytes).hex(),
    )


def _trusted(authority: BenchmarkAuthority) -> TrustedBenchmarkAuthority:
    raw = benchmark_json(authority)
    _write_test_config(raw, generation=authority.generation)
    return load_trusted_benchmark_authority(raw)


def _write_test_config(
    authority_bytes: bytes,
    *,
    generation: int,
    signing_key: Ed25519PrivateKey = _AUTHORITY_KEY,
) -> None:
    if _TEST_DEPLOYMENT is None:
        raise AssertionError("protected config test seam was not installed")
    config = {
        "authority_sha256": hashlib.sha256(authority_bytes).hexdigest(),
        "generation": generation,
        "signing_public_key": _public_key(signing_key),
    }
    _TEST_DEPLOYMENT.protected_config = (
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )


def _authority_for_test(trusted: TrustedBenchmarkAuthority) -> BenchmarkAuthority:
    if _TEST_DEPLOYMENT is None:
        raise AssertionError("protected config test seam was not installed")
    config = benchmark_model._parse_protected_authority_config(_TEST_DEPLOYMENT.protected_config)
    return benchmark_model._reverify_trusted_authority(trusted, config)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(bytes.fromhex(value)).hexdigest()
