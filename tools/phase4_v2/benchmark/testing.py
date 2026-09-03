"""Test-only authority deployment seam.

Production code never imports this module and cannot select this config source.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import model


@dataclass(slots=True)
class BenchmarkAuthorityTestDeployment:
    """Mutable deployment config used only to exercise load and rotation behavior."""

    protected_config: bytes

    def load(self, authority_bytes: bytes) -> model.TrustedBenchmarkAuthority:
        config = model._parse_protected_authority_config(self.protected_config)
        return model._load_trusted_benchmark_authority_with_config(authority_bytes, config)

    def finalize(
        self,
        authority: model.TrustedBenchmarkAuthority,
        plan: model.BenchmarkPlan,
        oracle: model.OracleSuite,
        run: model.BenchmarkRun,
        audits: model.IndependentAuditSuite,
        timings: model.TimingSuite,
    ) -> model.BenchmarkReport:
        config = model._parse_protected_authority_config(self.protected_config)
        return model._finalize_benchmark_with_config(
            authority,
            plan,
            oracle,
            run,
            audits,
            timings,
            config,
        )
