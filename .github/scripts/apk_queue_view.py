#!/usr/bin/env python3
"""Regenerate the published APK Protocol Audit pages from the #436 body.

    apk_queue_view.py queue  <436-body.md|-> <current-queue.html>  > queue.html
    apk_queue_view.py status <436-body.md|-> <current-status.html> > status.html

Both pages read #436, and the status page also reads the GitHub pull request
list, live in the browser whenever they open, so they stay current between
publishes. The baked copy is what /raw readers and scripts without JavaScript
see. The queue view carries each unit's APK member list over from the current
page, which is the only place it lives. The status page carries over its run
note. Publish the output with the html-communication skill's publish script.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apk_tracker_guard import queue_rows  # noqa: E402

REPO = "https://github.com/kristofferR/ha-adjustable-bed"
QUEUE_VIEW = "https://plans.kristofferr.com/d/ch8geif5zzyg"
LIVE_STATUS = "https://plans.kristofferr.com/d/1aydd9y2s65x"
ANALYSIS_CLASS = {
    "ACCEPTED": "done",
    "IN PROGRESS": "active",
    "PARTIAL": "partial",
    "QUEUED": "queued",
    "BLOCKED": "blocked",
}
IMPLEMENTATION_CLASS = {"MERGED": "done", "IN REVIEW": "active", "PENDING": "partial"}

_ITEM = re.compile(
    r'<details class="(?:queue-item|unit)"(?P<attrs>[^>]*)>(?P<body>.*?)</details>', re.S
)
_MEMBERS = re.compile(r'<ul class="apk-list">.*?</ul>', re.S)
_MEMBER_STATUS = re.compile(r'<span class="member-status ([a-z]+)">')
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
_ISSUE_REF = re.compile(r"(?<![\w/#])#(\d+)\b")
_RUN_NOTE = re.compile(
    r'<section id="run"[^>]*>(.*?)</section>|<h2>Run</h2>\s*<div class="panel">(.*?)</div>', re.S
)


def _rank(value: str) -> str:
    return value.zfill(3) if value.isdigit() else value


def members(view: str) -> dict[str, tuple[str, str]]:
    """Map each unit's rank to its family and its APK member list markup."""
    found: dict[str, tuple[str, str]] = {}
    for item in _ITEM.finditer(view):
        attrs = dict(re.findall(r'data-([a-z]+)="([^"]*)"', item["attrs"]))
        listing = _MEMBERS.search(item["body"])
        rank = attrs.get("order") or attrs["rank"]
        found[_rank(rank)] = (attrs.get("family", ""), listing[0] if listing else "")
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


def work_html(work: str) -> str:
    """A unit's ID, plus its member packages when it is a formal cluster."""
    code, _, packages = work.partition(" · ")
    listed = ", ".join(f"<code>{html.escape(p)}</code>" for p in re.findall(r"`([^`]+)`", packages))
    apps = f'<span class="apps">{listed}</span>' if listed else ""
    return f"<code>{html.escape(code.strip('`'))}</code>{apps}"


def unit(cells: list[str], family: str, listing: str) -> str:
    order, analysis, work, route, implementation = cells
    state = implementation.split(" · ", 1)[0]
    statuses = _MEMBER_STATUS.findall(listing)
    accepted = sum(status in ("done", "accepted") for status in statuses)
    route_text = html.escape(route) + (f" · {html.escape(family)}" if family else "")
    return (
        f'<details class="unit" data-order="{html.escape(order)}" data-family="{html.escape(family)}"'
        f' data-status="{ANALYSIS_CLASS[analysis]}">'
        f'<summary><span class="rank">{html.escape(order)}</span>'
        f'<span class="chip {ANALYSIS_CLASS[analysis]}">{html.escape(analysis)}</span>'
        f'<span class="work">{work_html(work)}<small>{route_text}</small></span>'
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
code{overflow-wrap:anywhere}#freshness{font-size:13px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px;overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 8px;border-top:1px solid var(--line);
vertical-align:top}th{color:var(--muted);font-weight:600;border-top:0}td:first-child{color:var(--muted)}
.counts td:first-child{width:34%}.counts tr:first-child td{border-top:0}
.rows td:first-child{white-space:nowrap}.rows td:last-child{width:40%}
input{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);
color:var(--text);font:inherit;margin:4px 0 12px}
.unit{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:6px 0}
.unit summary{display:grid;grid-template-columns:44px 110px minmax(0,1.3fr) 92px minmax(0,1.7fr);
gap:10px;align-items:center;padding:9px 12px;cursor:pointer;list-style:none}
.unit summary::-webkit-details-marker{display:none}.rank{color:var(--muted);font-variant-numeric:tabular-nums}
.work>code{display:block}.apps{display:block;font-size:13px;overflow-wrap:anywhere}
.work small,.members{color:var(--muted);font-size:13px}
.chip{font-size:12px;font-weight:600;border:1px solid currentColor;border-radius:999px;padding:1px 8px;
justify-self:start;white-space:nowrap}
.done{color:var(--done)}.active{color:var(--active)}.partial{color:var(--partial)}.queued{color:var(--queued)}
.blocked{color:var(--blocked)}.impl{font-size:14px}.impl.queued{color:var(--muted)}
.apk-list{list-style:none;margin:0;padding:4px 12px 12px 66px}
.apk{display:grid;grid-template-columns:minmax(0,1.4fr) 1fr 1fr 1fr;gap:10px;padding:6px 0;
border-top:1px solid var(--line);font-size:14px}.app-name,.meta,.role{color:var(--muted)}
.app-name{display:block}.member-status.accepted{color:var(--done)}
.hidden{display:none}
@media (max-width:760px){.unit summary{grid-template-columns:40px 1fr;row-gap:4px}
.unit summary>.work,.unit summary>.members,.unit summary>.impl{grid-column:1/-1}.apk-list{padding-left:12px}
.apk{grid-template-columns:1fr 1fr}.rows td:last-child{width:auto}}
"""

# Shared by both pages: read #436 live and render its cells like the Python side does.
LIVE_JS = """
const REPO='kristofferR/ha-adjustable-bed',GH='https://github.com/'+REPO,API='https://api.github.com/repos/'+REPO;
const CLS={'ACCEPTED':'done','IN PROGRESS':'active','PARTIAL':'partial','QUEUED':'queued','BLOCKED':'blocked'};
const IMPL={'MERGED':'done','IN REVIEW':'active','PENDING':'partial'};
const esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#x27;'}[c]));
const refs=t=>esc(t.replace(/`/g,'')).replace(/(^|[^\\w\\/#])#(\\d+)\\b/g,(x,p,n)=>`${p}<a href="${GH}/issues/${n}" target="_blank">#${n}</a>`);
function inline(t){const re=/\\[([^\\]]+)\\]\\((https:\\/\\/[^)\\s]+)\\)/g;let out='',last=0,m;
while((m=re.exec(t))){out+=refs(t.slice(last,m.index))+`<a href="${esc(m[2])}" target="_blank">${esc(m[1])}</a>`;last=re.lastIndex;}
return out+refs(t.slice(last));}
function workHtml(w){const i=w.indexOf(' · '),code=(i<0?w:w.slice(0,i)).replace(/`/g,'');
const pk=i<0?[]:[...w.slice(i+3).matchAll(/`([^`]+)`/g)].map(m=>`<code>${esc(m[1])}</code>`);
return `<code>${esc(code)}</code>`+(pk.length?`<span class="apps">${pk.join(', ')}</span>`:'');}
async function getJson(path){const url=path.startsWith('https:')?path:API+path;
const r=await fetch(url,{headers:{Accept:'application/vnd.github+json'},cache:'no-store'});
if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
async function read436(){const body=(await getJson('/issues/436')).body.replace(/\\r\\n/g,'\\n');
const a=body.indexOf('<!-- phase4-queue:start -->'),b=body.indexOf('<!-- phase4-queue:end -->');
const rows=body.slice(a,b).split('\\n').filter(l=>l.startsWith('| ')&&!l.startsWith('| Order'))
.map(l=>l.trim().replace(/^\\|\\s*|\\s*\\|$/g,'').split(/\\s*\\|\\s*/));
const st=(body.split('\\n## Status\\n')[1]||'').split('\\n## ')[0].split('\\n')
.filter(l=>/^\\| .+ \\| .+ \\|$/.test(l)&&!l.startsWith('| Scope')).map(l=>l.slice(2,-2).split(' | '));
return {rows,status:st};}
document.querySelector('#freshness').textContent='Reading live data…';
const stamp=()=>new Date().toISOString().slice(0,16).replace('T',' ')+' UTC';
"""

QUEUE_JS = """
(async()=>{const note=document.querySelector('#freshness');try{const {rows,status}=await read436();
const box=document.querySelector('#units');rows.forEach(([o,a,w,r,impl])=>{const e=box.querySelector(`.unit[data-order="${o}"]`);
if(!e)return;const c=CLS[a]||'queued';e.dataset.status=c;const chip=e.querySelector('.chip');chip.className='chip '+c;chip.textContent=a;
const fam=e.dataset.family;e.querySelector('.work').innerHTML=workHtml(w)+`<small>${esc(r)}${fam?' · '+esc(fam):''}</small>`;
const im=e.querySelector('.impl');im.className='impl '+(IMPL[impl.split(' · ')[0]]||'queued');im.innerHTML=inline(impl);box.append(e);});
document.querySelector('#counts').innerHTML=status.map(([s,c])=>`<tr><td>${esc(s)}</td><td>${esc(c)}</td></tr>`).join('');
note.textContent='Live from #436, read '+stamp()+'.';}catch(err){note.textContent='Showing the published snapshot; reading #436 live failed ('+err.message+').';}})();
const s=document.querySelector('#search');s.addEventListener('input',()=>{const q=s.value.trim().toLowerCase();
document.querySelectorAll('.unit').forEach(e=>{const m=!q||e.textContent.toLowerCase().includes(q);
e.classList.toggle('hidden',!m);if(q&&m)e.open=true;});});
"""

STATUS_JS = """
const rowHtml=([o,a,w,r,impl])=>`<tr><td>${esc(o)}</td><td><span class="chip ${CLS[a]||'queued'}">${esc(a)}</span></td><td>${workHtml(w)}</td><td>${inline(impl)}</td></tr>`;
(async()=>{const note=document.querySelector('#freshness');try{const {rows}=await read436();
const active=rows.filter(([o,a,w,r,i])=>a==='IN PROGRESS'||a==='PARTIAL'||/^(IN REVIEW|PENDING)/.test(i));
const held=rows.filter(([o,a])=>a==='BLOCKED');
document.querySelector('#active').innerHTML=active.map(rowHtml).join('')||'<tr><td colspan="4">No unit is in progress.</td></tr>';
document.querySelector('#held').innerHTML=held.map(rowHtml).join('');
const byPr=new Map();rows.forEach(row=>[...row[4].matchAll(/\\[PR #(\\d+)\\]/g)].forEach(m=>byPr.set(+m[1],row)));
const day=new Date(Date.now()-7*864e5).toISOString().slice(0,10);
const q=encodeURIComponent(`repo:${REPO} is:pr is:merged base:main merged:>=${day}`);
const searchAll=async()=>{let items=[];for(let page=1;page<=5;page++){
const r=await getJson(`https://api.github.com/search/issues?per_page=100&page=${page}&q=${q}`);
items=items.concat(r.items);if(items.length>=r.total_count||!r.items.length)break;}return items;};
const [open,mergedItems]=await Promise.all([getJson('/pulls?state=open&per_page=100'),searchAll()]);
const merged={items:mergedItems};
const prs=[...open.filter(p=>byPr.has(p.number)).map(p=>[p,'Open']),
...merged.items.filter(p=>byPr.has(p.number)).map(p=>(p.merged_at=p.pull_request.merged_at,[p,'Merged '+p.merged_at.slice(0,10)]))]
.sort((x,y)=>(y[0].merged_at||'9').localeCompare(x[0].merged_at||'9'));
document.querySelector('#prs').innerHTML=prs.map(([p,state])=>{const r=byPr.get(p.number);
return `<tr><td>${esc(r[0])}</td><td>${workHtml(r[2])}</td><td><a href="${p.html_url}" target="_blank">PR #${p.number}</a> ${esc(p.title)}</td><td>${state}</td></tr>`;}).join('')
||'<tr><td colspan="4">No queue PR opened or merged in the last 7 days.</td></tr>';
note.textContent='Live from #436 and GitHub, read '+stamp()+'.';}catch(err){note.textContent='Showing the published snapshot; reading live data failed ('+err.message+').';}})();
"""


def _links(*extra: tuple[str, str]) -> str:
    items = [
        (f"{REPO}/issues/436", "Ordered queue #436"),
        (f"{REPO}/issues/443", "Audit method and evidence #443"),
        (f"{REPO}/issues/447", "Accepted early reports #447"),
        *extra,
    ]
    return " · ".join(f'<a href="{url}" target="_blank">{label}</a>' for url, label in items)


def _page(title: str, heading: str, content: str, script: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{STYLE}</style></head>
<body><main>
<h1>{heading}</h1>
{content}
</main><script>{LIVE_JS}{script}</script></body></html>
"""


def _freshness() -> str:
    return '<p id="freshness">Published snapshot. Opening the page in a browser reads the live data.</p>'


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
    content = f"""<p>{_links((LIVE_STATUS, "Live status"))}</p>
<p>This page mirrors the #436 queue in its order and expands each unit into its APK members.</p>
{_freshness()}
<h2>Status</h2>
<div class="panel"><table class="counts"><tbody id="counts">{counts}</tbody></table></div>
<h2>Ordered units and APK members</h2>
<input id="search" type="search" placeholder="Filter by row, package, app, status or PR" aria-label="Filter units">
<div id="units">
{units}
</div>"""
    return _page("APK Protocol Audit Queue", "APK Protocol Audit queue", content, QUEUE_JS)


def _row(cells: list[str]) -> str:
    order, analysis, work, _route, implementation = cells
    return (
        f"<tr><td>{html.escape(order)}</td>"
        f'<td><span class="chip {ANALYSIS_CLASS[analysis]}">{html.escape(analysis)}</span></td>'
        f"<td>{work_html(work)}</td><td>{inline(implementation)}</td></tr>"
    )


def render_status(body: str, current: str) -> str:
    rows = queue_rows(body.replace("\r\n", "\n").split("\n"))
    note = _RUN_NOTE.search(current)
    if not note:
        raise SystemExit("the current status page has no run note to carry over")
    run = (note[1] or note[2]).strip()
    active = [
        r
        for r in rows
        if r[1] in ("IN PROGRESS", "PARTIAL") or r[4].startswith(("IN REVIEW", "PENDING"))
    ]
    held = [r for r in rows if r[1] == "BLOCKED"]
    head = "<tr><th>Row</th><th>Analysis</th><th>Unit</th><th>Implementation</th></tr>"
    content = f"""<p>{_links((QUEUE_VIEW, "Queue view"))}</p>
<p>Run status for the APK Protocol Audit. Active and held units come from #436, and pull requests from GitHub.</p>
{_freshness()}
<h2>Run</h2>
<section id="run" class="panel">{run}</section>
<h2>Active</h2>
<div class="panel"><table class="rows"><thead>{head}</thead><tbody id="active">{"".join(map(_row, active))}</tbody></table></div>
<h2>Pull requests in the last 7 days</h2>
<div class="panel"><table class="rows"><thead><tr><th>Row</th><th>Unit</th><th>PR</th><th>State</th></tr></thead>
<tbody id="prs"><tr><td colspan="4">Loads from GitHub when the page opens.</td></tr></tbody></table></div>
<h2>Held or blocked</h2>
<div class="panel"><table class="rows"><thead>{head}</thead><tbody id="held">{"".join(map(_row, held))}</tbody></table></div>"""
    return _page(
        "APK Protocol Audit Live Status", "APK Protocol Audit live status", content, STATUS_JS
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("queue", "status"):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    body = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text(encoding="utf-8")
    current = Path(argv[2]).read_text(encoding="utf-8")
    sys.stdout.write((render if argv[0] == "queue" else render_status)(body, current))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
