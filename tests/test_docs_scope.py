"""docs/ holds documentation only: discovery ledgers and disposition files are audit records.

AGENTS.md keeps a ledger machine-local with its APK Protocol Audit report, and the
implementation PR states its totals and exclusions.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"

# Names the removed audit records used: rowNNN-*, 032-*, S01-*, issue558-*,
# *-disposition*.md, *-ledger.json, *-convergence.md and *-issue-audit.md.
_AUDIT_NAME = re.compile(
    r"disposition|ledger|convergence|issue-audit|^(?:row|issue|s)?\d{2,}[-_.]", re.IGNORECASE
)


def test_docs_hold_no_disposition_or_ledger_files() -> None:
    found = sorted(
        path.relative_to(DOCS.parent).as_posix()
        for path in DOCS.rglob("*")
        if path.is_file()
        and (
            _AUDIT_NAME.search(path.name)
            or path.suffix == ".csv"
            or "dispositions" in path.relative_to(DOCS).parts
        )
    )
    assert not found, (
        "Audit records do not belong in docs/. Keep the ledger machine-local with its "
        f"APK Protocol Audit report, and put its totals and exclusions in the PR body: {found}"
    )
