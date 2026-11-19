"""APK audit tracker ids (``row061``, ``unit128``, ``cluster018``) name nothing in the repository.

Name the app and its version instead. The integration and its docs are scanned
in full, comments and docstrings included; tests, scripts and tools are scanned
in their source text and file names. Exempt are the APK audit process docs and
tracker guard, which handle the tracker's own id format, and the exact files in
``EXEMPT_IDS``: saved-state keys a migration reads.
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).parents[1]
INTEGRATION = REPO / "custom_components" / "adjustable_bed"
AUDIT_ID = re.compile(r"(?<![a-z])(?:row|unit|cluster|repair|review)-?\d{3}(?!\d)", re.IGNORECASE)

# Scanned in full: every text file. Scanned as source: file names and code.
FULL = (INTEGRATION, REPO / "docs")
SOURCE = (REPO / "tests", REPO / "scripts", REPO / "tools")
SOURCE_SUFFIXES = {".py", ".md", ".ts", ".sh", ".txt"}
SKIPPED_PARTS = {"node_modules", "dist", "__pycache__"}
EXEMPT = {REPO / "docs" / "apk-analysis", REPO / "tests" / "test_apk_tracker_guard.py", Path(__file__)}

# Saved state still holds this id: the Richmat classic app keys a migration
# reads, and the docs and tests that describe that migration.
SAVED_STATE = {
    "custom_components/adjustable_bed/beds/richmat_classic/profiles.py": {"cluster018"},
    "docs/V5_BREAKING_CHANGES.md": {"cluster018"},
    "tests/test_richmat_classic_migration.py": {"cluster018"},
}
EXEMPT_IDS = SAVED_STATE


def _files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if SKIPPED_PARTS.intersection(path.relative_to(root).parts):
            continue
        if not any(path == exempt or exempt in path.parents for exempt in EXEMPT):
            yield path


def _offenders() -> Iterator[str]:
    for root in (*FULL, *SOURCE):
        for path in _files(root):
            relative = str(path.relative_to(REPO))
            allowed = EXEMPT_IDS.get(relative, set())
            if any(match.lower() not in allowed for match in AUDIT_ID.findall(path.name)):
                yield f"file name {relative}"
            if path.is_dir() or (root in SOURCE and path.suffix not in SOURCE_SUFFIXES):
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if any(match.lower() not in allowed for match in AUDIT_ID.findall(line)):
                    yield f"{relative}:{number}: {line.strip()[:100]}"


def test_no_audit_ids() -> None:
    assert list(_offenders()) == []


def test_the_guard_finds_every_id_form() -> None:
    found = AUDIT_ID.findall(
        "Row054, unit128, cluster-015, richmat_cluster022, repair005, review020; not preview112233"
    )
    assert found == ["Row054", "unit128", "cluster-015", "cluster022", "repair005", "review020"]


# Decompiler provenance an APK report records ("jadx/sources/...:97-117"). No
# test reads it, and the reports stay machine-local.
PROVENANCE_KEYS = {
    "evidence", "source_note", "mapping_evidence", "wake_up_massage_evidence", "source_files",
    "source_addresses", "source_functions", "source_method_sha256", "source_events",
    "literal_source", "delta_source", "scope_disposition", "initial_state_origin",
    "report_sha256", "artifact_sha256", "artifact_set_sha256", "source_trace",
}


def _keys(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def test_fixtures_carry_no_decompiler_provenance() -> None:
    fixtures = REPO / "tests" / "fixtures"
    found = {}
    for path in sorted(fixtures.rglob("*.json*")):
        relative = str(path.relative_to(fixtures))
        if not path.name.endswith((".json", ".json.gz")):
            continue
        raw = path.read_bytes()
        data = json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)
        if keys := PROVENANCE_KEYS.intersection(_keys(data)):
            found[relative] = sorted(keys)
    assert found == {}
