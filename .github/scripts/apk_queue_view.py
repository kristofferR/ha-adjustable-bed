#!/usr/bin/env python3
"""Regenerate the published APK Protocol Audit queue view from the #436 body.

    apk_queue_view.py <436-body.md|-> <current-view.html> > queue.html

Status, counts and PR links come from #436, so the view never disagrees with
it. Each unit's APK member list is carried over from the current view, which is
the only place it lives; edit a member's status there when that member changes.
Publish the output with the html-communication skill's publish script.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apk_tracker_guard import queue_rows  # noqa: E402

REPO = "https://github.com/kristofferR/ha-adjustable-bed"
ANALYSIS_CLASS = {
    "ACCEPTED": "done",
    "IN PROGRESS": "active",
    "PARTIAL": "partial",
    "QUEUED": "queued",
    "BLOCKED": "blocked",
}
IMPLEMENTATION_CLASS = {"MERGED": "done", "IN REVIEW": "active", "PENDING": "partial"}

_ITEM = re.compile(r'<details class="queue-item"(?P<attrs>[^>]*)>(?P<body>.*?)</details>', re.S)
_MEMBERS = re.compile(r'<ul class="apk-list">.*?</ul>', re.S)
_MEMBER_STATUS = re.compile(r'<span class="member-status ([a-z]+)">')
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
_ISSUE_REF = re.compile(r"(?<![\w/#])#(\d+)\b")


def _rank(value: str) -> str:
    return value.zfill(3) if value.isdigit() else value


def members(view: str) -> dict[str, tuple[str, str]]:
    """Map each unit's rank to its family and its APK member list markup."""
    found: dict[str, tuple[str, str]] = {}
    for item in _ITEM.finditer(view):
        attrs = dict(re.findall(r'data-([a-z]+)="([^"]*)"', item["attrs"]))
        listing = _MEMBERS.search(item["body"])
        found[_rank(attrs["rank"])] = (attrs.get("family", ""), listing[0] if listing else "")
    return found


def status_rows(body: str) -> list[tuple[str, str]]:
    section = body.split("\n## Status\n", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| ([^|]+?) \| ([^|]+?) \|$", section, re.M)
    return [row for row in rows if row[0] not in ("Scope", "---")]


def inline(text: str) -> str:
    """Render a #436 cell: markdown links and bare #N references become links."""
    parts: list[str] = []
    last = 0
    for match in _MD_LINK.finditer(text):
        parts.append(_refs(text[last : match.start()]))
        label, url = html.escape(match[1]), html.escape(match[2])
        parts.append(f'<a href="{url}" target="_blank">{label}</a>')
        last = match.end()
    parts.append(_refs(text[last:]))
    return "".join(parts)


def _refs(text: str) -> str:
    text = html.escape(text.replace("`", ""))
    return _ISSUE_REF.sub(rf'<a href="{REPO}/issues/\1" target="_blank">#\1</a>', text)


def unit(cells: list[str], family: str, listing: str) -> str:
    order, analysis, work, route, implementation = cells
    # A cluster's work cell reads "`cluster-NNN` · `package`, `package`".
    code, _, packages = work.partition(" · ")
    listed = ", ".join(f"<code>{html.escape(p)}</code>" for p in re.findall(r"`([^`]+)`", packages))
    apps_html = f'<span class="apps">{listed}</span>' if listed else ""
    state = implementation.split(" · ", 1)[0]
    statuses = _MEMBER_STATUS.findall(listing)
    accepted = sum(status in ("done", "accepted") for status in statuses)
    route_text = html.escape(route) + (f" · {html.escape(family)}" if family else "")
    return (
        f'<details class="unit" data-status="{ANALYSIS_CLASS[analysis]}">'
        f'<summary><span class="rank">{html.escape(order)}</span>'
        f'<span class="chip {ANALYSIS_CLASS[analysis]}">{html.escape(analysis)}</span>'
        f'<span class="work"><code>{html.escape(code.strip("`"))}</code>{apps_html}'
        f"<small>{route_text}</small></span>"
        f'<span class="members">{accepted}/{len(statuses)} accepted</span>'
        f'<span class="impl {IMPLEMENTATION_CLASS.get(state, "queued")}">{inline(implementation)}</span>'
        f"</summary>{listing}</details>"
    )


STYLE = """
:root{color-scheme:dark;--bg:#111214;--panel:#1b1c1f;--line:#2c2e33;--text:#ecebe6;--muted:#a3a29c;
--done:#7fc8a0;--active:#8fb8ef;--partial:#e3c07a;--queued:#9a9a95;--blocked:#e58f86}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 18px 60px}h1{font-size:24px;margin:0 0 6px}
h2{font-size:17px;margin:28px 0 10px}p{color:var(--muted);margin:6px 0}a{color:var(--active)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
table{border-collapse:collapse;width:100%}td{padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}
td:first-child{color:var(--muted);width:34%}tr:first-child td{border-top:0}
input{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);
color:var(--text);font:inherit;margin:4px 0 12px}
.unit{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:6px 0}
.unit summary{display:grid;grid-template-columns:44px 110px minmax(0,1.3fr) 92px minmax(0,1.7fr);
gap:10px;align-items:center;padding:9px 12px;cursor:pointer;list-style:none}
.unit summary::-webkit-details-marker{display:none}.rank{color:var(--muted);font-variant-numeric:tabular-nums}
.work>code{display:block;overflow-wrap:anywhere}.apps{display:block;font-size:13px;overflow-wrap:anywhere}.work small,.members{color:var(--muted);font-size:13px}
.chip{font-size:12px;font-weight:600;border:1px solid currentColor;border-radius:999px;padding:1px 8px;
justify-self:start}
.done{color:var(--done)}.active{color:var(--active)}.partial{color:var(--partial)}.queued{color:var(--queued)}
.blocked{color:var(--blocked)}.impl{font-size:14px}.impl.queued{color:var(--muted)}
.apk-list{list-style:none;margin:0;padding:4px 12px 12px 66px}
.apk{display:grid;grid-template-columns:minmax(0,1.4fr) 1fr 1fr 1fr;gap:10px;padding:6px 0;
border-top:1px solid var(--line);font-size:14px}.app-name,.meta,.role{color:var(--muted)}
.app-name{display:block}.member-status.accepted{color:var(--done)}
.hidden{display:none}
@media (max-width:760px){.unit summary{grid-template-columns:40px 1fr;row-gap:4px}
.unit summary>.work,.unit summary>.members,.unit summary>.impl{grid-column:1/-1}.apk-list{padding-left:12px}
.apk{grid-template-columns:1fr 1fr}}
"""

SCRIPT = """<script>(()=>{const s=document.querySelector('#search'),u=[...document.querySelectorAll('.unit')];
s.addEventListener('input',()=>{const q=s.value.trim().toLowerCase();u.forEach(e=>{const m=!q||e.textContent.toLowerCase().includes(q);
e.classList.toggle('hidden',!m);if(q&&m)e.open=true;});});})();</script>"""


def render(body: str, view: str) -> str:
    lines = body.replace("\r\n", "\n").split("\n")
    known = members(view)
    rows = queue_rows(lines)
    missing = [cells[0] for cells in rows if cells[0] not in known]
    if missing:
        raise SystemExit(f"units missing from the current view: {', '.join(missing)}")
    counts = "".join(
        f"<tr><td>{html.escape(scope)}</td><td>{html.escape(count)}</td></tr>"
        for scope, count in status_rows(body)
    )
    units = "\n".join(unit(cells, *known[cells[0]]) for cells in rows)
    links = " · ".join(
        f'<a href="{REPO}/issues/{number}" target="_blank">{label}</a>'
        for number, label in (
            (436, "Ordered queue #436"),
            (443, "Audit method and evidence #443"),
            (447, "Accepted early reports #447"),
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APK Protocol Audit Queue</title><style>{STYLE}</style></head>
<body><main>
<h1>APK Protocol Audit queue</h1>
<p>{links} · <a href="https://plans.kristofferr.com/d/1aydd9y2s65x" target="_blank">Live status</a></p>
<p>This page mirrors the #436 queue in its order and expands each unit into its APK members.
#436 is the authority; this view is regenerated from it after every queue change.</p>
<h2>Status</h2>
<div class="panel"><table>{counts}</table></div>
<h2>Ordered units and APK members</h2>
<input id="search" type="search" placeholder="Filter by row, package, app, status or PR" aria-label="Filter units">
{units}
</main>{SCRIPT}</body></html>
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    body = sys.stdin.read() if argv[0] == "-" else Path(argv[0]).read_text(encoding="utf-8")
    view = Path(argv[1]).read_text(encoding="utf-8")
    sys.stdout.write(render(body, view))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
