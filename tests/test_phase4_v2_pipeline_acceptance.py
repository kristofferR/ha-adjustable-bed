from __future__ import annotations

import sqlite3
from contextlib import closing

import pytest

from tools.phase4_v2.benchmark import (
    SyntheticPipelineConfig,
    SyntheticStage,
    run_synthetic_pipeline_acceptance,
)


@pytest.mark.parametrize("seed", (7, 42, 8675309))
def test_pipeline_converges_across_randomized_crashes_and_corruption(tmp_path, seed: int) -> None:
    config = SyntheticPipelineConfig(
        seed=seed,
        clusters=3,
        packages_per_cluster=3,
        workers=6,
        crash_probability=0.25,
        corruption_probability=0.2,
    )

    report = run_synthetic_pipeline_acceptance(tmp_path / f"run-{seed}", config)

    assert report.job_count == config.clusters * (config.packages_per_cluster * 3 + 1) + 1
    assert report.attempt_count >= report.job_count
    assert report.injected_crashes == report.stale_writers_fenced
    assert report.reopen_count > 1
    assert dict(report.completed_by_stage) == {
        SyntheticStage.PREPARATION: config.clusters * config.packages_per_cluster,
        SyntheticStage.FINAL_IR: config.clusters * config.packages_per_cluster,
        SyntheticStage.REPORT_VALIDATION: config.clusters * config.packages_per_cluster,
        SyntheticStage.RECONCILIATION: config.clusters,
        SyntheticStage.PUBLICATION: 1,
    }
    assert len(report.publication_generation) == 64
    assert len(report.publication_source_sha256) == 64


def test_pipeline_rejects_corruption_before_formal_completion(tmp_path) -> None:
    root = tmp_path / "corruption"
    report = run_synthetic_pipeline_acceptance(
        root,
        SyntheticPipelineConfig(
            seed=11,
            clusters=2,
            packages_per_cluster=4,
            workers=5,
            crash_probability=0,
            corruption_probability=0.5,
        ),
    )

    assert report.rejected_corruptions > 0
    with closing(sqlite3.connect(root / "pipeline.sqlite3")) as connection:
        duplicate_completions = connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT job_id
                FROM attempts
                WHERE terminal = 'COMPLETED'
                GROUP BY job_id
                HAVING COUNT(*) != 1
            )
            """
        ).fetchone()
        artifacts = connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()
    assert duplicate_completions == (0,)
    assert artifacts == (report.job_count,)


def test_pipeline_publication_is_one_exact_atomic_snapshot(tmp_path) -> None:
    root = tmp_path / "publication"
    report = run_synthetic_pipeline_acceptance(
        root,
        SyntheticPipelineConfig(
            seed=99,
            clusters=4,
            packages_per_cluster=2,
            crash_probability=0.35,
            corruption_probability=0.25,
        ),
    )

    with closing(sqlite3.connect(root / "pipeline.sqlite3")) as connection:
        trackers = connection.execute(
            "SELECT generation, source_sha256 FROM tracker_views"
        ).fetchall()
    assert len(trackers) == 3
    assert set(trackers) == {(report.publication_generation, report.publication_source_sha256)}


def test_pipeline_config_and_root_are_fail_closed(tmp_path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="must not already exist"):
        run_synthetic_pipeline_acceptance(existing, SyntheticPipelineConfig(seed=1))
    with pytest.raises(ValueError, match="below one"):
        SyntheticPipelineConfig(seed=1, crash_probability=1)
