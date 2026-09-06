"""Seeded synthetic acceptance for the complete content-addressed pipeline.

No application artifact is read. The harness uses small canonical fixtures to
exercise preparation, final IR/report validation, reconciliation, and atomic
tracker publication across randomized crashes and process-style reopenings.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SyntheticStage(StrEnum):
    PREPARATION = "PREPARATION"
    FINAL_IR = "FINAL_IR"
    REPORT_VALIDATION = "REPORT_VALIDATION"
    RECONCILIATION = "RECONCILIATION"
    PUBLICATION = "PUBLICATION"


@dataclass(frozen=True, slots=True)
class SyntheticPipelineConfig:
    seed: int
    clusters: int = 4
    packages_per_cluster: int = 4
    workers: int = 8
    crash_probability: float = 0.2
    corruption_probability: float = 0.15
    max_rounds: int = 10_000

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        for label, value, maximum in (
            ("clusters", self.clusters, 100),
            ("packages_per_cluster", self.packages_per_cluster, 100),
            ("workers", self.workers, 64),
            ("max_rounds", self.max_rounds, 1_000_000),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{label} must be between 1 and {maximum}")
        for label, value in (
            ("crash_probability", self.crash_probability),
            ("corruption_probability", self.corruption_probability),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value < 1:
                raise ValueError(f"{label} must be at least zero and below one")


@dataclass(frozen=True, slots=True)
class SyntheticPipelineReport:
    seed: int
    job_count: int
    attempt_count: int
    injected_crashes: int
    post_commit_crashes: int
    rejected_corruptions: int
    stale_writers_fenced: int
    reopen_count: int
    completed_by_stage: tuple[tuple[SyntheticStage, int], ...]
    publication_generation: str
    publication_source_sha256: str


@dataclass(frozen=True, slots=True)
class _Claim:
    job_id: str
    stage: SyntheticStage
    fencing_token: int


_STAGE_ORDER = {
    SyntheticStage.PREPARATION: 0,
    SyntheticStage.FINAL_IR: 1,
    SyntheticStage.REPORT_VALIDATION: 2,
    SyntheticStage.RECONCILIATION: 3,
    SyntheticStage.PUBLICATION: 4,
}
_TRACKER_PATHS = ("queue.html", "queue.md", "status.json")


def run_synthetic_pipeline_acceptance(
    root: Path,
    config: SyntheticPipelineConfig,
) -> SyntheticPipelineReport:
    """Run a deterministic fake pipeline under crashes, corruption, and retries."""

    if root.exists():
        raise ValueError("synthetic pipeline root must not already exist")
    root.mkdir(parents=True)
    database = root / "pipeline.sqlite3"
    _initialize(database, config)
    generator = random.Random(config.seed)
    attempts = 0
    injected_crashes = 0
    post_commit_crashes = 0
    rejected_corruptions = 0
    stale_writers_fenced = 0
    reopen_count = 0
    rounds = 0
    seen_claims: set[tuple[str, int]] = set()

    while not _all_complete(database):
        rounds += 1
        if rounds > config.max_rounds:
            raise RuntimeError("synthetic pipeline did not converge")
        reopen_count += 1
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            claims = tuple(
                claim
                for claim in executor.map(
                    lambda worker: _claim(database, f"worker-{worker:02d}"),
                    range(config.workers),
                )
                if claim is not None
            )
        if not claims:
            raise RuntimeError("synthetic pipeline stalled")
        if len({item.job_id for item in claims}) != len(claims):
            raise RuntimeError("a work unit was assigned twice concurrently")
        for claim in sorted(claims, key=lambda item: item.job_id):
            key = (claim.job_id, claim.fencing_token)
            if key in seen_claims:
                raise RuntimeError("a fencing capability was issued twice")
            seen_claims.add(key)
            attempts += 1
            if generator.random() < config.crash_probability:
                injected_crashes += 1
                if not _recover(database, claim):
                    raise RuntimeError("crashed lease could not be recovered")
                candidate = _expected_output(database, claim)
                if _commit_output(database, claim, candidate):
                    raise RuntimeError("a stale worker published after recovery")
                stale_writers_fenced += 1
                continue
            candidate = _expected_output(database, claim)
            if generator.random() < config.corruption_probability:
                candidate = candidate + b"\ncorrupt"
                if _commit_output(database, claim, candidate):
                    raise RuntimeError("a corrupt artifact was accepted")
                rejected_corruptions += 1
                continue
            if not _commit_output(database, claim, candidate):
                raise RuntimeError("a live valid worker was unexpectedly fenced")
            if generator.random() < config.crash_probability:
                # The durable transaction committed, but its acknowledgement was lost.
                post_commit_crashes += 1
                if _commit_output(database, claim, candidate):
                    raise RuntimeError("a committed attempt was accepted twice after restart")

    generation, source, stage_counts = _verify_complete(database, config)
    return SyntheticPipelineReport(
        seed=config.seed,
        job_count=_job_count(config),
        attempt_count=attempts,
        injected_crashes=injected_crashes,
        post_commit_crashes=post_commit_crashes,
        rejected_corruptions=rejected_corruptions,
        stale_writers_fenced=stale_writers_fenced,
        reopen_count=reopen_count,
        completed_by_stage=stage_counts,
        publication_generation=generation,
        publication_source_sha256=source,
    )


def _initialize(database: Path, config: SyntheticPipelineConfig) -> None:
    with _connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                stage_order INTEGER NOT NULL,
                cluster_id TEXT,
                package_id TEXT,
                source_sha256 TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'READY',
                fencing_token INTEGER NOT NULL DEFAULT 0,
                output_sha256 TEXT
            );
            CREATE TABLE dependencies (
                job_id TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                PRIMARY KEY (job_id, parent_id),
                FOREIGN KEY (job_id) REFERENCES jobs(job_id),
                FOREIGN KEY (parent_id) REFERENCES jobs(job_id)
            );
            CREATE TABLE attempts (
                job_id TEXT NOT NULL,
                fencing_token INTEGER NOT NULL,
                owner TEXT NOT NULL,
                terminal TEXT,
                PRIMARY KEY (job_id, fencing_token)
            );
            CREATE TABLE artifacts (
                job_id TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                body BLOB NOT NULL
            );
            CREATE TABLE tracker_views (
                path TEXT PRIMARY KEY,
                generation TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                body BLOB NOT NULL
            );
            """
        )
        reconciliations: list[str] = []
        for cluster_index in range(config.clusters):
            cluster_id = f"cluster-{cluster_index:04d}"
            cluster_validations: list[str] = []
            for package_index in range(config.packages_per_cluster):
                package_id = f"package-{cluster_index:04d}-{package_index:04d}"
                source = _digest(f"source:{package_id}".encode())
                prep = f"{cluster_id}:{package_id}:prepare"
                final_ir = f"{cluster_id}:{package_id}:final-ir"
                validation = f"{cluster_id}:{package_id}:validate"
                _insert_job(
                    connection, prep, SyntheticStage.PREPARATION, cluster_id, package_id, source
                )
                _insert_job(
                    connection, final_ir, SyntheticStage.FINAL_IR, cluster_id, package_id, source
                )
                _insert_job(
                    connection,
                    validation,
                    SyntheticStage.REPORT_VALIDATION,
                    cluster_id,
                    package_id,
                    source,
                )
                connection.execute("INSERT INTO dependencies VALUES (?, ?)", (final_ir, prep))
                connection.execute("INSERT INTO dependencies VALUES (?, ?)", (validation, final_ir))
                cluster_validations.append(validation)
            reconciliation = f"{cluster_id}:reconcile"
            _insert_job(
                connection,
                reconciliation,
                SyntheticStage.RECONCILIATION,
                cluster_id,
                None,
                _digest(cluster_id.encode()),
            )
            for validation in cluster_validations:
                connection.execute(
                    "INSERT INTO dependencies VALUES (?, ?)",
                    (reconciliation, validation),
                )
            reconciliations.append(reconciliation)
        publication = "global:publish"
        _insert_job(
            connection,
            publication,
            SyntheticStage.PUBLICATION,
            None,
            None,
            _digest(b"global-publication"),
        )
        for reconciliation in reconciliations:
            connection.execute(
                "INSERT INTO dependencies VALUES (?, ?)",
                (publication, reconciliation),
            )


def _insert_job(
    connection: sqlite3.Connection,
    job_id: str,
    stage: SyntheticStage,
    cluster_id: str | None,
    package_id: str | None,
    source: str,
) -> None:
    connection.execute(
        "INSERT INTO jobs (job_id, stage, stage_order, cluster_id, package_id, source_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, stage.value, _STAGE_ORDER[stage], cluster_id, package_id, source),
    )


def _claim(database: Path, owner: str) -> _Claim | None:
    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT job_id, stage, fencing_token
            FROM jobs AS candidate
            WHERE status = 'READY'
              AND NOT EXISTS (
                SELECT 1
                FROM dependencies AS dependency
                JOIN jobs AS parent ON parent.job_id = dependency.parent_id
                WHERE dependency.job_id = candidate.job_id
                  AND parent.status != 'COMPLETED'
              )
            ORDER BY stage_order, job_id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        token = int(row[2]) + 1
        updated = connection.execute(
            "UPDATE jobs SET status = 'LEASED', fencing_token = ? "
            "WHERE job_id = ? AND status = 'READY' AND fencing_token = ?",
            (token, row[0], row[2]),
        )
        if updated.rowcount != 1:
            raise RuntimeError("synthetic claim compare-and-swap failed")
        connection.execute(
            "INSERT INTO attempts VALUES (?, ?, ?, NULL)",
            (row[0], token, owner),
        )
        connection.commit()
        return _Claim(row[0], SyntheticStage(row[1]), token)


def _recover(database: Path, claim: _Claim) -> bool:
    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            "UPDATE jobs SET status = 'READY', fencing_token = fencing_token + 1 "
            "WHERE job_id = ? AND status = 'LEASED' AND fencing_token = ?",
            (claim.job_id, claim.fencing_token),
        )
        connection.execute(
            "UPDATE attempts SET terminal = 'CRASHED' WHERE job_id = ? AND fencing_token = ?",
            (claim.job_id, claim.fencing_token),
        )
        connection.commit()
        return updated.rowcount == 1


def _expected_output(database: Path, claim: _Claim) -> bytes:
    with _connect(database) as connection:
        job = connection.execute(
            "SELECT cluster_id, package_id, source_sha256 FROM jobs WHERE job_id = ?",
            (claim.job_id,),
        ).fetchone()
        parents = connection.execute(
            """
            SELECT dependency.parent_id, parent.output_sha256
            FROM dependencies AS dependency
            JOIN jobs AS parent ON parent.job_id = dependency.parent_id
            WHERE dependency.job_id = ?
            ORDER BY dependency.parent_id
            """,
            (claim.job_id,),
        ).fetchall()
    payload: dict[str, object] = {
        "cluster_id": job[0],
        "input_sha256": job[2],
        "job_id": claim.job_id,
        "package_id": job[1],
        "parents": [
            {"job_id": parent_id, "output_sha256": output_sha} for parent_id, output_sha in parents
        ],
        "stage": claim.stage.value,
    }
    if claim.stage is SyntheticStage.PREPARATION:
        payload["preparation_receipt"] = _digest(_canonical(payload))
    elif claim.stage is SyntheticStage.FINAL_IR:
        payload["final_ir_revision"] = "synthetic-final-ir-v1"
        payload["report_sha256"] = _digest(b"report:" + _canonical(payload))
    elif claim.stage is SyntheticStage.REPORT_VALIDATION:
        payload["decision"] = "ACCEPTED"
        payload["validation_revision"] = "synthetic-validation-v1"
    elif claim.stage is SyntheticStage.RECONCILIATION:
        payload["all_members_validated"] = True
        payload["reconciliation_revision"] = "synthetic-reconciliation-v1"
    else:
        payload["publication_revision"] = "synthetic-publication-v1"
    return _canonical(payload) + b"\n"


def _commit_output(database: Path, claim: _Claim, body: bytes) -> bool:
    expected = _expected_output(database, claim)
    with _connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        state = connection.execute(
            "SELECT status, fencing_token FROM jobs WHERE job_id = ?",
            (claim.job_id,),
        ).fetchone()
        if state != ("LEASED", claim.fencing_token):
            connection.rollback()
            return False
        if body != expected:
            connection.execute(
                "UPDATE jobs SET status = 'READY', fencing_token = fencing_token + 1 "
                "WHERE job_id = ? AND fencing_token = ?",
                (claim.job_id, claim.fencing_token),
            )
            connection.execute(
                "UPDATE attempts SET terminal = 'REJECTED' WHERE job_id = ? AND fencing_token = ?",
                (claim.job_id, claim.fencing_token),
            )
            connection.commit()
            return False
        output_sha = _digest(body)
        existing = connection.execute(
            "SELECT sha256, body FROM artifacts WHERE job_id = ?",
            (claim.job_id,),
        ).fetchone()
        if existing is not None and existing != (output_sha, body):
            raise RuntimeError("an immutable artifact would be overwritten")
        if existing is None:
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?)",
                (claim.job_id, output_sha, body),
            )
        if claim.stage is SyntheticStage.PUBLICATION:
            _publish_trackers(connection, output_sha)
        connection.execute(
            "UPDATE jobs SET status = 'COMPLETED', output_sha256 = ? "
            "WHERE job_id = ? AND fencing_token = ?",
            (output_sha, claim.job_id, claim.fencing_token),
        )
        connection.execute(
            "UPDATE attempts SET terminal = 'COMPLETED' WHERE job_id = ? AND fencing_token = ?",
            (claim.job_id, claim.fencing_token),
        )
        connection.commit()
        return True


def _publish_trackers(connection: sqlite3.Connection, source_sha256: str) -> None:
    reconciliations = connection.execute(
        "SELECT job_id, output_sha256 FROM jobs WHERE stage = ? ORDER BY job_id",
        (SyntheticStage.RECONCILIATION.value,),
    ).fetchall()
    snapshot = _canonical(
        {
            "reconciliations": [
                {"job_id": job_id, "output_sha256": output_sha}
                for job_id, output_sha in reconciliations
            ],
            "source_sha256": source_sha256,
        }
    )
    generation = _digest(snapshot)
    for path in _TRACKER_PATHS:
        body = (
            _canonical(
                {
                    "generation": generation,
                    "path": path,
                    "snapshot_sha256": _digest(snapshot),
                    "source_sha256": source_sha256,
                }
            )
            + b"\n"
        )
        connection.execute(
            "INSERT INTO tracker_views VALUES (?, ?, ?, ?)",
            (path, generation, source_sha256, body),
        )


def _verify_complete(
    database: Path,
    config: SyntheticPipelineConfig,
) -> tuple[str, str, tuple[tuple[SyntheticStage, int], ...]]:
    with _connect(database) as connection:
        jobs = connection.execute(
            "SELECT job_id, stage, fencing_token, output_sha256 FROM jobs ORDER BY job_id"
        ).fetchall()
        artifacts = {
            job_id: (sha256, body)
            for job_id, sha256, body in connection.execute(
                "SELECT job_id, sha256, body FROM artifacts"
            )
        }
        trackers = connection.execute(
            "SELECT path, generation, source_sha256, body FROM tracker_views ORDER BY path"
        ).fetchall()
        completed_attempts = connection.execute(
            "SELECT job_id, COUNT(*) FROM attempts WHERE terminal = 'COMPLETED' GROUP BY job_id"
        ).fetchall()
    if len(jobs) != _job_count(config) or len(artifacts) != len(jobs):
        raise RuntimeError("the synthetic pipeline lost an output")
    if any(count != 1 for _job_id, count in completed_attempts) or len(completed_attempts) != len(
        jobs
    ):
        raise RuntimeError("a job acquired duplicate formal completions")
    for job_id, stage, token, output_sha in jobs:
        claim = _Claim(job_id, SyntheticStage(stage), token)
        expected = _expected_output(database, claim)
        if artifacts[job_id] != (_digest(expected), expected) or output_sha != _digest(expected):
            raise RuntimeError("a completed artifact is inconsistent with its exact inputs")
    if tuple(item[0] for item in trackers) != _TRACKER_PATHS:
        raise RuntimeError("the tracker fanout is incomplete")
    generations = {item[1] for item in trackers}
    sources = {item[2] for item in trackers}
    if len(generations) != 1 or len(sources) != 1:
        raise RuntimeError("tracker views came from inconsistent snapshots")
    for path, generation, source, body in trackers:
        decoded = json.loads(body)
        if (
            decoded["path"] != path
            or decoded["generation"] != generation
            or decoded["source_sha256"] != source
        ):
            raise RuntimeError("a tracker view failed exact readback")
    stage_counts = tuple(
        (stage, sum(1 for _job_id, value, _token, _digest_value in jobs if value == stage.value))
        for stage in SyntheticStage
    )
    return generations.pop(), sources.pop(), stage_counts


def _all_complete(database: Path) -> bool:
    with _connect(database) as connection:
        row = connection.execute("SELECT COUNT(*) FROM jobs WHERE status != 'COMPLETED'").fetchone()
    return row == (0,)


def _job_count(config: SyntheticPipelineConfig) -> int:
    return config.clusters * (config.packages_per_cluster * 3 + 1) + 1


@contextmanager
def _connect(database: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(database, timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        with connection:
            yield connection
    finally:
        connection.close()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
