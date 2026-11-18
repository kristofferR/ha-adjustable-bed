"""APK audit tracker ids (``row061``, ``unit128``, ``cluster018``) name nothing in the repository.

Name the app and its version instead. The integration and its docs are scanned
in full, comments and docstrings included; tests, scripts and tools are scanned
in their source text and file names. Exempt are an id that saved state still
holds, which a ``*LEGACY*`` constant in the integration states so a migration
can read it, the APK audit process docs and tracker guard, which handle the
tracker's own id format, and the ids in ``IN_FLIGHT``.
"""

from __future__ import annotations

import ast
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

# Ids left in beds whose tests other in-flight v5 work is rewriting (2026-11-18).
# Replace them with the app name and version, then drop them here, once it lands.
IN_FLIGHT = {
    "row116",  # Good Vibe
    "row159", "unit162", "row081", "cluster022", "cluster-022",  # MLILY, MLILY Supreme, Nisco
    "row101",  # Casper
    "row126",  # Hush
    "unit146",  # Luuna
    "row055", "cluster-020", "row061", "row173",  # Richmat MH and Richmat app
    "row132", "unit132", "row135",  # Jalon
    "row179",  # SonicSleep
}


def legacy_ids() -> set[str]:
    """Return the ids that ``*LEGACY*`` constants keep for migrations to read."""
    ids: set[str] = set()
    for path in INTEGRATION.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            targets = (
                node.targets if isinstance(node, ast.Assign)
                else [node.target] if isinstance(node, ast.AnnAssign)
                else []
            )
            if any(isinstance(t, ast.Name) and "LEGACY" in t.id for t in targets) and node.value:
                for child in ast.walk(node.value):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        ids.update(match.lower() for match in AUDIT_ID.findall(child.value))
    return ids


def _files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if SKIPPED_PARTS.intersection(path.relative_to(root).parts):
            continue
        if not any(path == exempt or exempt in path.parents for exempt in EXEMPT):
            yield path


def _offenders() -> Iterator[str]:
    allowed = legacy_ids() | IN_FLIGHT
    for root in (*FULL, *SOURCE):
        for path in _files(root):
            relative = path.relative_to(REPO)
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
