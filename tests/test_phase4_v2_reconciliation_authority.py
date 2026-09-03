"""Authenticated authority-bound reconciliation surface regressions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.phase4_v2.ir import dumps_final_ir, loads_final_ir, render_final_ir_markdown
from tools.phase4_v2.orchestration.acceptance import (
    complete_authenticated_synthetic_package_inputs,
)
from tools.phase4_v2.orchestration.testing import (
    _authorized_final_ir,
    build_synthetic_package_inputs,
    protected_fixture_trust,
)
from tools.phase4_v2.queue import Queue
from tools.phase4_v2.reconciliation import (
    ReconciliationError,
    derive_authenticated_final_ir_package_surface,
)


def test_surface_rejects_report_plan_output_and_envelope_transplants(tmp_path: Path) -> None:
    queue = Queue(tmp_path / "queue.sqlite3", tmp_path / "attempts")
    queue.initialize()
    with protected_fixture_trust(tmp_path / "trust") as trust:
        active: set[tuple[str, str, str]] = set()
        packages = tuple(
            complete_authenticated_synthetic_package_inputs(
                queue,
                build_synthetic_package_inputs(
                    tmp_path / "cluster-auth",
                    cluster_id="cluster-auth",
                    package_index=index,
                    trust=trust,
                ),
                trust,
                active,
            )
            for index in range(2)
        )
        data, receipts = _authorized_final_ir(packages[0].source_registry)
        document = loads_final_ir(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n",
            trusted_receipts=receipts,
        )
        canonical = dumps_final_ir(document)
        markdown = render_final_ir_markdown(document)
        first, second = packages
        common = {
            "package_ref": first.package_ref,
            "execution_plan": first.frozen_plan,
            "queue": queue,
            "validated_output": first.output,
            "execution_envelope": first.execution_envelope,
            "report_bytes": first.report_bytes,
            "report_manifest_bytes": first.report_manifest_bytes,
            "document": document,
            "canonical_json": canonical,
            "markdown": markdown,
            "source_registry": first.source_registry,
            "exact_reuse_receipts": first.exact_reuse_receipts,
        }
        assert derive_authenticated_final_ir_package_surface(**common).package_surface.package_ref == first.package_ref
        for field, transplanted in (
            ("execution_plan", second.frozen_plan),
            ("validated_output", second.output),
            ("execution_envelope", second.execution_envelope),
            ("report_bytes", second.report_bytes),
        ):
            with pytest.raises((ReconciliationError, ValueError)):
                derive_authenticated_final_ir_package_surface(
                    **{**common, field: transplanted}
                )
