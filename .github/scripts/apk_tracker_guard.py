#!/usr/bin/env python3
"""Keep the APK Protocol Audit tracker issues readable.

The rules are described in docs/apk-analysis/TRACKERS.md.

    apk_tracker_guard.py check <issue> <file|->   lint a draft body
    apk_tracker_guard.py guard <event.json>       workflow mode for issues.edited

Guard mode restores the previous body when an edit breaks the rules and the
previous body passed them. Standard library only, so the workflow needs no setup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Tracker:
    # Exact ordered "## " sections, each with its byte budget.
    sections: tuple[tuple[str, int], ...]
    max_bytes: int
    intro_max_bytes: int = 1200
    has_queue: bool = False
    allow_hashes: bool = True


TRACKERS: dict[int, Tracker] = {
    436: Tracker(
        sections=(
            ("Status", 2500),
            ("Goal", 2000),
            ("Hardware validation policy", 3000),
            ("Canonical ordered phase 4 queue", 36000),
            ("Definition of done", 1500),
            ("History", 800),
        ),
        max_bytes=45000,
        has_queue=True,
        allow_hashes=False,
    ),
    443: Tracker(
        sections=(
            ("Operational audit method", 34000),
            ("Mandatory implementation convergence", 4500),
            ("Early analyses and tracker updates", 2000),
            ("Accepted evidence records", 75000),
            ("Accepted batch ledger", 30000),
            ("History", 800),
        ),
        max_bytes=145000,
    ),
    447: Tracker(
        sections=(
            ("Purpose", 1000),
            ("Acceptance and exclusion rules", 4000),
            ("Early-analysis intake", 12000),
            ("Accepted exclusions", 16000),
            ("Accepted evidence records", 32000),
            ("Routing", 2000),
            ("Exit gate", 800),
            ("History", 800),
        ),
        max_bytes=70000,
    ),
}

QUEUE_START = "<!-- phase4-queue:start -->"
QUEUE_END = "<!-- phase4-queue:end -->"
QUEUE_HEADER = "| Order | Analysis | Work unit | Route | Implementation |"
ANALYSIS_STATES = frozenset({"ACCEPTED", "IN PROGRESS", "PARTIAL", "QUEUED", "BLOCKED"})
IMPLEMENTATION_STATES = ("MERGED", "IN REVIEW", "PENDING", "NOT STARTED")
MAX_QUEUE_CELL = 160

_HASH = re.compile(r"\b[0-9a-f]{40,}\b")
_NOISE = re.compile(r"https?://\S+|`[^`]*`|\b[0-9a-f]{12,}\b|\]\([^)]*\)")


def marker(number: int) -> str:
    return f"<!-- apk-tracker:{number} -->"


def _split(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Split a body into its intro and its "## " sections, ignoring code fences."""
    intro: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    fenced = False
    for line in lines:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            sections.append((line[3:].strip(), [line]))
        elif sections:
            sections[-1][1].append(line)
        else:
            intro.append(line)
    return intro, sections


def _size(lines: list[str]) -> int:
    return len("\n".join(lines).encode())


def _compacted(line: str) -> bool:
    """Prose with its spaces squeezed out, the signature of budget compaction."""
    text = _NOISE.sub("", line)
    return len(text) >= 100 and text.count(" ") / len(text) < 0.08


def _lint_queue(lines: list[str]) -> list[str]:
    try:
        start, end = lines.index(QUEUE_START), lines.index(QUEUE_END)
    except ValueError:
        return [f"queue table must sit between {QUEUE_START} and {QUEUE_END}"]
    rows = [line for line in lines[start + 1 : end] if line.strip()]
    if len(rows) < 2 or rows[0] != QUEUE_HEADER:
        return [f"queue table must start with the header {QUEUE_HEADER}"]
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows[2:]:
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(cells) != 5 or not cells[0]:
            problems.append(f"queue row needs five cells and an order ID: {row[:80]}")
            continue
        order, analysis, _unit, _route, implementation = cells
        if order in seen:
            problems.append(f"queue row {order} appears twice")
        seen.add(order)
        if analysis not in ANALYSIS_STATES:
            problems.append(f"queue row {order}: analysis must be one of {sorted(ANALYSIS_STATES)}")
        if not implementation.startswith(IMPLEMENTATION_STATES):
            problems.append(
                f"queue row {order}: implementation must start with one of {IMPLEMENTATION_STATES}"
            )
        for cell in cells:
            if len(cell) > MAX_QUEUE_CELL:
                problems.append(f"queue row {order}: cell over {MAX_QUEUE_CELL} characters")
    return problems


def lint(number: int, body: str) -> list[str]:
    """Return every rule the body breaks; an empty list means it passes."""
    tracker = TRACKERS[number]
    body = body.replace("\r\n", "\n")
    lines = body.split("\n")
    problems: list[str] = []

    if lines[0].strip() != marker(number):
        problems.append(f"the first line must be {marker(number)}; nothing goes above it")
    if len(body.encode()) > tracker.max_bytes:
        problems.append(f"body is {len(body.encode())} bytes, over its {tracker.max_bytes} budget")
    if "<!-- run-" in body:
        problems.append("run journal blocks (<!-- run-...) do not belong in tracker bodies")
    if not tracker.allow_hashes and _HASH.search(body):
        problems.append(f"#{number} holds no hashes; seals belong in the evidence trackers")

    intro, sections = _split(lines)
    if _size(intro) > tracker.intro_max_bytes:
        problems.append(f"intro is over {tracker.intro_max_bytes} bytes; status goes in sections")
    titles = [title for title, _ in sections]
    expected = [title for title, _ in tracker.sections]
    if titles != expected:
        problems.append(f"sections must be exactly {expected}, found {titles}")
    budgets = dict(tracker.sections)
    for title, section in sections:
        if title in budgets and _size(section) > budgets[title]:
            problems.append(f"section {title!r} is over its {budgets[title]} byte budget")
        if tracker.has_queue and title == "Canonical ordered phase 4 queue":
            problems.extend(_lint_queue(section))

    for index, line in enumerate(lines, 1):
        if _compacted(line):
            problems.append(f"line {index} reads as compacted text: {line[:80]}")
    return problems


def _api(method: str, path: str, payload: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/{path}",
        method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def guard(event: dict) -> int:
    """Check one issues.edited event; restore the previous body if the edit broke the rules."""
    number = event["issue"]["number"]
    previous = event.get("changes", {}).get("body", {}).get("from")
    if number not in TRACKERS or previous is None:
        return 0
    edited = event["issue"]["body"] or ""
    problems = lint(number, edited)
    if not problems:
        print(f"#{number}: edit follows the tracker rules")
        return 0
    for problem in problems:
        print(f"::error title=#{number} tracker rule::{problem}")
    if lint(number, previous):
        print(f"#{number}: the previous body also breaks the rules, so it is not restored")
        return 1
    path = f"repos/{os.environ['GITHUB_REPOSITORY']}/issues/{number}"
    if (_api("GET", path)["body"] or "") != edited:
        print(f"#{number}: the issue changed again after this edit, so it is not restored")
        return 1
    _api("PATCH", path, {"body": previous})
    print(f"#{number}: restored the previous body; see docs/apk-analysis/TRACKERS.md")
    return 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="lint a draft body")
    check.add_argument("issue", type=int, choices=sorted(TRACKERS))
    check.add_argument("body", help="body file, or - for stdin")
    guard_parser = commands.add_parser("guard", help="workflow mode for issues.edited")
    guard_parser.add_argument("event", help="path to the GitHub event payload")
    args = parser.parse_args(argv)

    if args.command == "guard":
        with open(args.event, encoding="utf-8") as handle:
            return guard(json.load(handle))
    if args.body == "-":
        body = sys.stdin.read()
    else:
        with open(args.body, encoding="utf-8") as handle:
            body = handle.read()
    problems = lint(args.issue, body)
    for problem in problems:
        print(problem)
    if not problems:
        print(f"#{args.issue}: body follows the tracker rules")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
