"""Test-only authority deployment seam.

Production code never imports this module and cannot select this config source.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from . import model


@dataclass(slots=True)
class BenchmarkAuthorityTestDeployment:
    """Mutable deployment config used only to exercise load and rotation behavior."""

    protected_config: bytes

    def load(self, authority_bytes: bytes) -> model.TrustedBenchmarkAuthority:
        config = model._parse_protected_authority_config(self.protected_config)
        with patch.object(model, "_load_protected_authority_config", return_value=config):
            return model.load_trusted_benchmark_authority(authority_bytes)

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
        with patch.object(model, "_load_protected_authority_config", return_value=config):
            return model.finalize_benchmark(authority, plan, oracle, run, audits, timings)
