"""The APK tracker guard rejects journal-style edits and restores the last clean body."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "apk_tracker_guard.py"
_SPEC = importlib.util.spec_from_file_location("apk_tracker_guard", _PATH)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)

QUEUE_ROW = (
    "| 066 | MERGED | `cluster-018` · `com.richmat.fortywinks`, `com.richmat.milemont` | "
    f"1.0.1 (2), 1.0.4 (5) | [PR #825]({guard.PR_URL}825) |"
)


def clean_body(number: int, queue_row: str = QUEUE_ROW) -> str:
    """The smallest body that satisfies a tracker's rules."""
    parts = [guard.marker(number), "Links and purpose.", ""]
    for title, _budget in guard.TRACKERS[number].sections:
        parts += [f"## {title}", "", "Durable content in plain words.", ""]
        if guard.TRACKERS[number].has_queue and title == "Status":
            parts += [*guard.count_table([]), ""]
        if title == "Queue":
            parts += [guard.QUEUE_START, guard.QUEUE_HEADER, "|---:|---|---|---|---|"]
            parts += [queue_row, guard.QUEUE_END, ""]
    return "\n".join(parts)


@pytest.mark.parametrize("number", sorted(guard.TRACKERS))
def test_clean_body_passes(number: int) -> None:
    assert guard.lint(number, clean_body(number)) == []


def test_queue_can_grow_beyond_its_old_size_limits() -> None:
    rows = "\n".join(
        f"| A{index} | QUEUED | Example · `com.example.bed{index}` | 1.0 ({index}) | |"
        for index in range(650)
    )
    assert guard.lint(436, clean_body(436, rows)) == []


COMPACTED = "Reverie041 PR720 MERGED00:26:37Z;041+1completion.UserPR720-only closure:39bdnormal squash;R15Sol1APPROVE10cases"


@pytest.mark.parametrize(
    ("number", "edit", "rule"),
    [
        (447, lambda b: "## Current run, 3 November 2026\n\nStatus.\n\n" + b, "first line"),
        (
            443,
            lambda b: b.replace("## History", "## Current run\n\nStatus.\n\n## History"),
            "sections",
        ),
        (443, lambda b: b.replace("Links and purpose.", "x" * 1300), "intro"),
        (447, lambda b: b.replace("Durable content", COMPACTED, 1), "compacted"),
        (436, lambda b: b.replace("PR #825", "PR #825 at " + "ab" * 32), "hashes"),
        (436, lambda b: b.replace("PR #825", "PR #825 " + "note " * 40), "160 characters"),
        (436, lambda b: b.replace("| MERGED |", "| MERGED / IMPLEMENTED |"), "status must"),
        (436, lambda b: b.replace("1.0.1 (2), 1.0.4 (5)", "v1.0.1, 1.0.4"), "name (code)"),
        (
            436,
            lambda b: b.replace("| MERGED |", "| BLOCKED |").replace(
                QUEUE_ROW.split(" | ")[-1], "|"
            ),
            "says why",
        ),
        (436, lambda b: b.replace("| Status | Count |", "| Scope | Count |"), "count table"),
        (436, lambda b: b.replace(QUEUE_ROW, QUEUE_ROW + "\n" + QUEUE_ROW), "twice"),
        (
            436,
            lambda b: b.replace(QUEUE_ROW, QUEUE_ROW.split("[")[0] + "PR #825 |"),
            "write each PR",
        ),
        (436, lambda b: b.replace(f"[PR #825]({guard.PR_URL}825)", "merged"), "links its PR"),
        (436, lambda b: b.replace(" · `com.richmat.fortywinks`", " · Forty Winks,"), "`package`"),
        (
            436,
            lambda b: b.replace(" · `com.richmat.fortywinks`, `com.richmat.milemont`", ""),
            "`package`",
        ),
    ],
)
def test_journal_style_edits_fail(number: int, edit, rule: str) -> None:
    problems = guard.lint(number, edit(clean_body(number)))
    assert any(rule in problem for problem in problems), problems


def _event(number: int, edited: str, previous: str | None) -> dict:
    event: dict = {"issue": {"number": number, "body": edited}, "changes": {}}
    if previous is not None:
        event["changes"]["body"] = {"from": previous}
    return event


class FakeApi:
    """Records API calls and serves the issue's current body."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.body = ""

    def __call__(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.calls.append((method, path, payload))
        return {"body": self.body}


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeApi:
    fake = FakeApi()
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(guard, "_api", fake)
    return fake


def test_guard_restores_previous_body(api: FakeApi) -> None:
    clean = clean_body(436)
    api.body = junk = "Run journal\n" + clean
    assert guard.guard(_event(436, junk, clean)) == 1
    assert api.calls[-1] == ("PATCH", "repos/owner/repo/issues/436", {"body": clean})


def test_guard_keeps_a_newer_edit(api: FakeApi) -> None:
    clean = clean_body(436)
    api.body = "a later edit"
    assert guard.guard(_event(436, "Run journal\n" + clean, clean)) == 1
    assert [method for method, _path, _payload in api.calls] == ["GET"]


def test_guard_accepts_clean_edits_and_ignores_title_edits(api: FakeApi) -> None:
    clean = clean_body(447)
    assert guard.guard(_event(447, clean, "Run journal\n" + clean)) == 0
    assert guard.guard(_event(447, "Run journal\n" + clean, None)) == 0
    assert guard.guard(_event(123, "anything", "anything else")) == 0
    assert api.calls == []


_VIEW_PATH = _PATH.with_name("apk_queue_view.py")
_VIEW_SPEC = importlib.util.spec_from_file_location("apk_queue_view", _VIEW_PATH)
assert _VIEW_SPEC and _VIEW_SPEC.loader
view = importlib.util.module_from_spec(_VIEW_SPEC)
sys.modules[_VIEW_SPEC.name] = view
_VIEW_SPEC.loader.exec_module(view)


def test_queue_view_is_built_from_436_alone() -> None:
    body = clean_body(436).replace(
        QUEUE_ROW,
        QUEUE_ROW + "\n| A01 | QUEUED | Aeroflex · `com.aeroflex.aeroflex` | 1.1.0 (14) | |",
    )
    page = view.render(body)
    assert f'<a href="{guard.PR_URL}825" target="_blank">PR #825</a>' in page
    # A cluster lists its packages with one version line each; its cluster ID stays in #436.
    assert (
        "<code>com.richmat.fortywinks</code><code>com.richmat.milemont</code></td>"
        '<td class="version"><span>1.0.1 (2)</span><span>1.0.4 (5)</span></td>'
    ) in page
    assert "<code>cluster-018</code>" not in page
    assert '<span class="name">Aeroflex</span><code>com.aeroflex.aeroflex</code>' in page
    assert "<b>2</b>Total" in page and "<b>1</b>Merged" in page and "<b>1</b>Queued" in page


def test_guard_recomputes_436_counts_after_a_clean_edit(api: FakeApi) -> None:
    clean = clean_body(436)
    stale = clean.replace("| Total | 0 |", "| Total | 7 |")
    api.body = stale
    assert guard.guard(_event(436, stale, clean)) == 0
    assert api.calls[-1] == (
        "PATCH",
        "repos/owner/repo/issues/436",
        {"body": guard.with_counts(clean)},
    )
    assert "| Total | 1 |" in api.calls[-1][2]["body"]


def test_status_page_bakes_active_and_held_units_and_keeps_its_run_note() -> None:
    body = clean_body(436).replace(
        QUEUE_ROW,
        QUEUE_ROW + "\n| 061 | BLOCKED | `com.richmat.tx` | | Package unknown |"
        "\n| 113 | IN PROGRESS | `com.HHC.MotoMotion` | 1.0 (1) | Implementing |",
    )
    old = '<section id="run" class="panel"><p>Run window note.</p></section>'
    page = view.render_status(body, old)
    assert old in page
    active = page.split('id="active">')[1].split("</tbody>")[0]
    held = page.split('id="held">')[1].split("</tbody>")[0]
    assert "com.HHC.MotoMotion" in active and "fortywinks" not in active
    assert "com.richmat.tx" in held and "com.HHC.MotoMotion" not in held
    assert "Run window note." in view.render_status(body, page)
