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
    f"| 066 | ACCEPTED | `cluster-018` | Formal cluster | MERGED · [PR #825]({guard.PR_URL}825) |"
)


def clean_body(number: int, queue_row: str = QUEUE_ROW) -> str:
    """The smallest body that satisfies a tracker's rules."""
    parts = [guard.marker(number), "Links and purpose.", ""]
    for title, _budget in guard.TRACKERS[number].sections:
        parts += [f"## {title}", "", "Durable content in plain words.", ""]
        if title == "Canonical ordered phase 4 queue":
            parts += [guard.QUEUE_START, guard.QUEUE_HEADER, "|---:|---|---|---|---|"]
            parts += [queue_row, guard.QUEUE_END, ""]
    return "\n".join(parts)


@pytest.mark.parametrize("number", sorted(guard.TRACKERS))
def test_clean_body_passes(number: int) -> None:
    assert guard.lint(number, clean_body(number)) == []


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
        (436, lambda b: b.replace("| ACCEPTED |", "| MERGED / IMPLEMENTED |"), "analysis must"),
        (436, lambda b: b.replace(QUEUE_ROW, QUEUE_ROW + "\n" + QUEUE_ROW), "twice"),
        (
            436,
            lambda b: b.replace(QUEUE_ROW, QUEUE_ROW.split("[")[0] + "PR #825 |"),
            "write each PR",
        ),
        (436, lambda b: b.replace(f"[PR #825]({guard.PR_URL}825)", "merged"), "links its PR"),
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

MEMBERS = (
    '<ul class="apk-list"><li class="apk"><code>com.richmat.coastersleep</code>'
    '<span class="member-status done">Accepted</span></li></ul>'
)
OLD_VIEW = (
    '<p id="current-run">Run journal</p><details class="queue-item" data-rank="66" '
    f'data-family="richmat"><summary>stale</summary><p>stale reason</p>{MEMBERS}</details>'
)


def test_queue_view_mirrors_436_and_keeps_members() -> None:
    body = clean_body(436).replace(
        "## Status\n\nDurable content in plain words.",
        "## Status\n\n| Scope | Count |\n|---|---|\n| Implementation | 79 merged |",
    )
    page = view.render(body, OLD_VIEW)
    assert f'<a href="{guard.PR_URL}825" target="_blank">PR #825</a>' in page
    assert MEMBERS in page and "1/1 accepted" in page and "79 merged" in page
    assert "Run journal" not in page and "stale" not in page


def test_queue_view_refuses_units_it_cannot_expand() -> None:
    with pytest.raises(SystemExit, match="066"):
        view.render(clean_body(436), "<html></html>")
