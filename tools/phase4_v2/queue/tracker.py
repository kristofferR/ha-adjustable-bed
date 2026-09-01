"""Deterministic tracker renderers for one queue snapshot."""

from __future__ import annotations

import hashlib
import html
import re
from collections import Counter

from .core import QueueSnapshot, WorkUnitStatus

_START = "<!-- phase4-v2-tracker:start"
_END = "<!-- phase4-v2-tracker:end -->"
_HEADER = re.compile(r"<!-- phase4-v2-tracker:start generation=([0-9a-f]{64}) -->")
GITHUB_ISSUE_BODY_MAX_CHARS = 65_536


def render_markdown(
    snapshot: QueueSnapshot, *, max_characters: int = GITHUB_ISSUE_BODY_MAX_CHARS
) -> str:
    """Render a replaceable GitHub issue-body block."""
    if max_characters < 1:
        raise ValueError("tracker output budget must be positive")
    counts = Counter(unit.status for unit in snapshot.units)
    lines = [
        f"{_START} generation={snapshot.generation_id} -->",
        "## Phase 4 v2 queue",
        "",
        f"Generation: `{snapshot.generation_id}`  ",
        f"Event watermark: `{snapshot.event_watermark}`",
        f"Scheduler state: `{snapshot.scheduler_state_digest}`",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {status.value} | {counts[status]} |" for status in WorkUnitStatus)
    lines.extend(
        [
            "",
            "| # | Unit | Cluster | Kind | Status | Attempts | Latest outcome |",
            "| ---: | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    unit_lines = []
    for unit in snapshot.units:
        unit_lines.append(
            "| "
            + " | ".join(
                (
                    str(unit.ordinal),
                    unit.unit_id,
                    unit.cluster_id or "",
                    unit.kind,
                    unit.status.value,
                    str(unit.attempt_count),
                    unit.latest_outcome.value if unit.latest_outcome is not None else "",
                )
            )
            + " |"
    )
    suffix = ["", _END]
    included = 0
    for index, line in enumerate(unit_lines):
        remaining = len(unit_lines) - index - 1
        omitted = [f"| … | | | | | | {remaining} additional units omitted |"] if remaining else []
        rendered = "\n".join([*lines, line, *omitted, *suffix]) + "\n"
        if len(rendered) > max_characters:
            break
        lines.append(line)
        included += 1
    else:
        rendered = "\n".join([*lines, *suffix]) + "\n"
        if len(rendered) <= max_characters:
            return rendered

    omitted = len(unit_lines) - included
    if omitted:
        lines.append(f"| … | | | | | | {omitted} additional units omitted |")
    rendered = "\n".join([*lines, *suffix]) + "\n"
    if len(rendered) > max_characters:
        raise ValueError("tracker output budget cannot fit its summary")
    return rendered


def render_html(snapshot: QueueSnapshot) -> str:
    """Render a self-contained, static HTML tracker from the same snapshot."""
    counts = Counter(unit.status for unit in snapshot.units)
    summary = "".join(
        f'<tr><th scope="row">{html.escape(status.value)}</th><td>{counts[status]}</td></tr>'
        for status in WorkUnitStatus
    )
    units = "".join(
        "<tr>"
        f"<td>{unit.ordinal}</td>"
        f"<td><code>{html.escape(unit.unit_id)}</code></td>"
        f"<td>{html.escape(unit.cluster_id or '')}</td>"
        f"<td>{html.escape(unit.kind)}</td>"
        f"<td>{html.escape(unit.status.value)}</td>"
        f"<td>{unit.attempt_count}</td>"
        f"<td>{html.escape(unit.latest_outcome.value if unit.latest_outcome else '')}</td>"
        "</tr>"
        for unit in snapshot.units
    )
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Phase 4 v2 queue</title>
<style>
:root {{ color-scheme: dark; font-family: ui-monospace, SFMono-Regular, monospace; }}
body {{ margin: 24px; background: #000; color: #fff; }}
h1 {{ font: 600 24px system-ui, sans-serif; }}
p {{ color: #aaa; }}
table {{ border-collapse: collapse; width: 100%; margin: 20px 0 36px; }}
th, td {{ border-bottom: 1px solid #333; padding: 8px 10px; text-align: left; }}
td:first-child, td:nth-last-child(2) {{ text-align: right; }}
</style>
<h1>Phase 4 v2 queue</h1>
<p>Generation <code>{snapshot.generation_id}</code>, event watermark {snapshot.event_watermark}, scheduler state <code>{snapshot.scheduler_state_digest}</code></p>
<table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>{summary}</tbody></table>
<table><thead><tr><th>#</th><th>Unit</th><th>Cluster</th><th>Kind</th><th>Status</th><th>Attempts</th><th>Latest outcome</th></tr></thead><tbody>{units}</tbody></table>
</html>
"""


def _managed_block(body: str) -> tuple[int, int, str, str] | None:
    starts = [match.start() for match in re.finditer(re.escape(_START), body)]
    ends = [match.start() for match in re.finditer(re.escape(_END), body)]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise ValueError("issue body contains malformed managed tracker markers")
    start = starts[0]
    end = ends[0] + len(_END)
    header_end = body.find("\n", start, end)
    if header_end < 0:
        raise ValueError("managed tracker header is malformed")
    match = _HEADER.fullmatch(body[start:header_end])
    if match is None:
        raise ValueError("managed tracker header is malformed")
    return start, end, match.group(1), body[start:end]


def managed_block_sha256(body: str) -> str | None:
    """Return the exact managed-block preimage digest, if one exists."""
    block = _managed_block(body)
    return hashlib.sha256(block[3].encode()).hexdigest() if block is not None else None


def managed_block_generation(body: str) -> str | None:
    """Return the managed block generation, if one exists."""
    block = _managed_block(body)
    return block[2] if block is not None else None


def managed_block_length(body: str) -> int:
    """Return the current managed-block length, if one exists."""
    block = _managed_block(body)
    return len(block[3]) if block is not None else 0


def replace_managed_block(
    body: str,
    rendered: str,
    *,
    expected_generation: str | None,
    expected_block_sha256: str | None,
) -> str:
    """Replace exactly one managed block after a caller-owned preimage check."""
    replacement = _managed_block(rendered)
    if (
        replacement is None
        or rendered[: replacement[0]].strip()
        or rendered[replacement[1] :].strip()
    ):
        raise ValueError("replacement must contain exactly one complete managed tracker block")
    existing = _managed_block(body)
    if existing is not None:
        start, end, observed, block = existing
        if observed != expected_generation:
            raise ValueError("managed tracker generation changed since read")
        observed_digest = hashlib.sha256(block.encode()).hexdigest()
        if observed_digest != expected_block_sha256:
            raise ValueError("managed tracker block changed since read")
        return body[:start] + replacement[3] + body[end:]
    if expected_generation is not None or expected_block_sha256 is not None:
        raise ValueError("managed tracker block disappeared since read")
    separator = "" if not body or body.endswith("\n\n") else "\n\n"
    return body + separator + rendered
