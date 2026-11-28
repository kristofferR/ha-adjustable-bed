#!/usr/bin/env python3
"""Regenerate the published APK Protocol Audit pages from the #436 body.

    apk_queue_view.py queue  <436-body.md|->                        > queue.html
    apk_queue_view.py status <436-body.md|-> <current-status.html> > status.html

Both pages read #436, and the status page also reads the GitHub pull request
list, live in the browser whenever they open, so they stay current between
publishes. The baked copy is what /raw readers and scripts without JavaScript
see. The queue view is built from #436 alone; the status page carries over its
run note. Publish the output with the html-communication skill's publish script.
"""

from __future__ import annotations

import html
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apk_tracker_guard import STATUSES, queue_rows  # noqa: E402

REPO = "https://github.com/kristofferR/ha-adjustable-bed"
QUEUE_VIEW = "https://plans.kristofferr.com/d/ch8geif5zzyg"
LIVE_STATUS = "https://plans.kristofferr.com/d/1aydd9y2s65x"
# The page titles also select which published draft an upload replaces, so keep them.
QUEUE_TITLE = "APK Protocol Audit Queue"
STATUS_TITLE = "APK Protocol Audit Live Status"

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
_ISSUE_REF = re.compile(r"(?<![\w/#])#(\d+)\b")
_CODE = re.compile(r"`([^`]+)`")
_RUN_NOTE = re.compile(r'<section id="run"[^>]*>(.*?)</section>', re.S)


def status_class(status: str) -> str:
    return status.lower().replace(" ", "-")


def inline(text: str) -> str:
    """Render a #436 cell: markdown links, `code` and bare #N references."""
    parts: list[str] = []
    last = 0
    for match in _MD_LINK.finditer(text):
        parts.append(_plain(text[last : match.start()]))
        label, url = html.escape(match[1]), html.escape(match[2])
        parts.append(f'<a href="{url}" target="_blank">{label}</a>')
        last = match.end()
    parts.append(_plain(text[last:]))
    return "".join(parts)


def _plain(text: str) -> str:
    text = _ISSUE_REF.sub(rf'<a href="{REPO}/issues/\1" target="_blank">#\1</a>', html.escape(text))
    return _CODE.sub(r"<code>\1</code>", text)


def app_html(app: str) -> str:
    """An app cell: its name, if any, over its package IDs. Cluster IDs stay in #436."""
    name = _CODE.sub("", app).strip(" ·,")
    packages = [p for p in _CODE.findall(app) if not p.startswith("cluster-")]
    listed = "".join(f"<code>{html.escape(p)}</code>" for p in packages)
    return (f'<span class="name">{html.escape(name)}</span>' if name else "") + listed


def version_html(version: str) -> str:
    """One line per package, so a cluster's versions line up with its packages."""
    return "".join(f"<span>{html.escape(v)}</span>" for v in version.split(", ") if v)


def _row(cells: list[str], *, version: bool = True) -> str:
    order, status, app, release, details = cells
    columns = [
        f'<td class="order">{html.escape(order)}</td>',
        f'<td><span class="chip {status_class(status)}">{html.escape(status)}</span></td>',
        f'<td class="app">{app_html(app)}</td>',
        f'<td class="version">{version_html(release)}</td>' if version else "",
        f'<td class="details">{inline(details)}</td>',
    ]
    return f'<tr data-status="{status_class(status)}">{"".join(columns)}</tr>'


def _counts(rows: list[list[str]]) -> str:
    counts = Counter(cells[1] for cells in rows)
    tiles = [("all", "Total", len(rows))] + [
        (status_class(status), label, counts[status]) for status, label in STATUSES.items()
    ]
    return "".join(
        f'<button class="tile {key}" data-filter="{key}" aria-pressed="{str(key == "all").lower()}">'
        f"<b>{count}</b>{label}</button>"
        for key, label, count in tiles
    )


STYLE = """
:root{color-scheme:dark;--bg:#111214;--panel:#1b1c1f;--line:#2c2e33;--text:#ecebe6;--muted:#a3a29c;
--merged:#7fc8a0;--partial:#e3c07a;--review:#8fb8ef;--progress:#b9a3ef;--queued:#9a9a95;--blocked:#e58f86}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 18px 60px}h1{font-size:24px;margin:0 0 6px}
h2{font-size:17px;margin:28px 0 10px}p{color:var(--muted);margin:6px 0}a{color:var(--review)}
code{overflow-wrap:anywhere;font-size:13px}#freshness{font-size:13px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:6px 14px;overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:7px 8px;border-top:1px solid var(--line);
vertical-align:top}th{color:var(--muted);font-weight:600;border-top:0}tbody tr:first-child td{border-top:0}
.order{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
table.queue{table-layout:fixed}.queue col.order{width:52px}.queue col.status{width:128px}
.queue col.app{width:36%}.queue col.version{width:150px}
.app .name{display:block}.app code{display:block}.app .name~code{color:var(--muted)}
.version{color:var(--muted);font-variant-numeric:tabular-nums}.version span{display:block;white-space:nowrap}
.app code,.version span{line-height:20px}
.chip{font-size:12px;font-weight:600;border:1px solid currentColor;border-radius:999px;padding:1px 8px;
white-space:nowrap}
.merged{color:var(--merged)}.partial{color:var(--partial)}.in-review{color:var(--review)}
.in-progress{color:var(--progress)}.queued,.out-of-scope{color:var(--queued)}.blocked{color:var(--blocked)}
.tiles{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;font:inherit;
font-size:13px;cursor:pointer;text-align:left;color:var(--muted)}.tile b{display:block;font-size:22px;color:var(--text)}
.tile.merged b{color:var(--merged)}.tile.partial b{color:var(--partial)}.tile.in-review b{color:var(--review)}
.tile.in-progress b{color:var(--progress)}.tile.blocked b{color:var(--blocked)}
.tile[aria-pressed="true"]{border-color:var(--text);color:var(--text)}
input{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel);
color:var(--text);font:inherit;margin:0 0 12px}
.hidden{display:none}
@media (max-width:760px){.queue thead,.queue colgroup{display:none}table.queue{table-layout:auto}.queue tr{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;
padding:8px 0;border-top:1px solid var(--line)}.queue td{border:0;padding:0}.queue .app,.queue .version,.queue .details{grid-column:1/-1}}
"""

# Shared by both pages: read #436 live and render its cells like the Python side does.
LIVE_JS = """
const REPO='kristofferR/ha-adjustable-bed',GH='https://github.com/'+REPO,API='https://api.github.com/repos/'+REPO;
const LABELS=__LABELS__;
const cls=s=>s.toLowerCase().replace(/ /g,'-');
const esc=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#x27;'}[c]));
const plain=t=>esc(t).replace(/(^|[^\\w\\/#])#(\\d+)\\b/g,(x,p,n)=>`${p}<a href="${GH}/issues/${n}" target="_blank">#${n}</a>`)
.replace(/`([^`]+)`/g,'<code>$1</code>');
function inline(t){const re=/\\[([^\\]]+)\\]\\((https:\\/\\/[^)\\s]+)\\)/g;let out='',last=0,m;
while((m=re.exec(t))){out+=plain(t.slice(last,m.index))+`<a href="${esc(m[2])}" target="_blank">${esc(m[1])}</a>`;last=re.lastIndex;}
return out+plain(t.slice(last));}
function appHtml(a){const name=a.replace(/`[^`]+`/g,'').replace(/^[\\s·,]+|[\\s·,]+$/g,'');
const pk=[...a.matchAll(/`([^`]+)`/g)].map(m=>m[1]).filter(p=>!p.startsWith('cluster-')).map(p=>`<code>${esc(p)}</code>`);
return (name?`<span class="name">${esc(name)}</span>`:'')+pk.join('');}
const versionHtml=v=>v.split(', ').filter(Boolean).map(x=>`<span>${esc(x)}</span>`).join('');
function rowHtml([o,s,a,v,d],version=true){return `<tr data-status="${cls(s)}"><td class="order">${esc(o)}</td>`+
`<td><span class="chip ${cls(s)}">${esc(s)}</span></td><td class="app">${appHtml(a)}</td>`+
(version?`<td class="version">${versionHtml(v)}</td>`:'')+`<td class="details">${inline(d)}</td></tr>`;}
async function getJson(path){const url=path.startsWith('https:')?path:API+path;
const r=await fetch(url,{headers:{Accept:'application/vnd.github+json'},cache:'no-store'});
if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
async function read436(){const body=(await getJson('/issues/436')).body.replace(/\\r\\n/g,'\\n');
const a=body.indexOf('<!-- phase4-queue:start -->'),b=body.indexOf('<!-- phase4-queue:end -->');
return body.slice(a,b).split('\\n').filter(l=>l.startsWith('| ')&&!l.startsWith('| Order'))
.map(l=>l.trim().replace(/^\\|\\s*|\\s*\\|$/g,'').split(/\\s*\\|\\s*/));}
document.querySelector('#freshness').textContent='Reading live data…';
const stamp=()=>new Date().toISOString().slice(0,16).replace('T',' ')+' UTC';
"""

QUEUE_JS = """
const search=document.querySelector('#search'),tiles=[...document.querySelectorAll('.tile')];
let only='all';
function filter(){const q=search.value.trim().toLowerCase();
document.querySelectorAll('#units tr').forEach(e=>e.classList.toggle('hidden',
(only!=='all'&&e.dataset.status!==only)||(q&&!e.textContent.toLowerCase().includes(q))));}
function bindTiles(){tiles.splice(0,tiles.length,...document.querySelectorAll('.tile'));
tiles.forEach(t=>t.addEventListener('click',()=>{only=only===t.dataset.filter?'all':t.dataset.filter;
tiles.forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.filter===only)));filter();}));}
search.addEventListener('input',filter);bindTiles();
(async()=>{const note=document.querySelector('#freshness');try{const rows=await read436();
document.querySelector('#units').innerHTML=rows.map(r=>rowHtml(r)).join('');
const n={};rows.forEach(r=>n[r[1]]=(n[r[1]]||0)+1);
const t=[['all','Total',rows.length],...Object.entries(LABELS).map(([s,l])=>[cls(s),l,n[s]||0])];
document.querySelector('#counts').innerHTML=t.map(([k,l,c])=>`<button class="tile ${k}" data-filter="${k}" aria-pressed="${k===only}"><b>${c}</b>${l}</button>`).join('');
bindTiles();filter();note.textContent='Live from #436, read '+stamp()+'.';}
catch(err){note.textContent='Showing the published snapshot; reading #436 live failed ('+err.message+').';}})();
"""

STATUS_JS = """
(async()=>{const note=document.querySelector('#freshness');try{const rows=await read436();
const active=rows.filter(([o,s])=>s==='IN PROGRESS'||s==='IN REVIEW');
const held=rows.filter(([o,s])=>s==='BLOCKED');
document.querySelector('#active').innerHTML=active.map(r=>rowHtml(r,false)).join('')||'<tr><td colspan="4">No unit is in progress.</td></tr>';
document.querySelector('#held').innerHTML=held.map(r=>rowHtml(r,false)).join('');
const byPr=new Map();rows.forEach(row=>[...row[4].matchAll(/\\[PR #(\\d+)\\]/g)].forEach(m=>byPr.set(+m[1],row)));
const day=new Date(Date.now()-7*864e5).toISOString().slice(0,10);
const q=encodeURIComponent(`repo:${REPO} is:pr is:merged base:main merged:>=${day}`);
const searchAll=async()=>{let items=[];for(let page=1;page<=5;page++){
const r=await getJson(`https://api.github.com/search/issues?per_page=100&page=${page}&q=${q}`);
items=items.concat(r.items);if(items.length>=r.total_count||!r.items.length)break;}return items;};
const [open,merged]=await Promise.all([getJson('/pulls?state=open&per_page=100'),searchAll()]);
const prs=[...open.filter(p=>byPr.has(p.number)).map(p=>[p,'Open']),
...merged.filter(p=>byPr.has(p.number)).map(p=>(p.merged_at=p.pull_request.merged_at,[p,'Merged '+p.merged_at.slice(0,10)]))]
.sort((x,y)=>(y[0].merged_at||'9').localeCompare(x[0].merged_at||'9'));
document.querySelector('#prs').innerHTML=prs.map(([p,state])=>{const r=byPr.get(p.number);
return `<tr><td class="order">${esc(r[0])}</td><td class="app">${appHtml(r[2])}</td><td><a href="${p.html_url}" target="_blank">PR #${p.number}</a> ${esc(p.title)}</td><td>${state}</td></tr>`;}).join('')
||'<tr><td colspan="4">No queue PR opened or merged in the last 7 days.</td></tr>';
note.textContent='Live from #436 and GitHub, read '+stamp()+'.';}catch(err){note.textContent='Showing the published snapshot; reading live data failed ('+err.message+').';}})();
"""


def _links(*extra: tuple[str, str]) -> str:
    items = [(f"{REPO}/issues/436", "Queue issue #436"), *extra]
    return " · ".join(f'<a href="{url}" target="_blank">{label}</a>' for url, label in items)


def _page(title: str, heading: str, content: str, script: str) -> str:
    labels = "{" + ",".join(f"'{s}':'{label}'" for s, label in STATUSES.items()) + "}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{STYLE}</style></head>
<body><main>
<h1>{heading}</h1>
{content}
</main><script>{LIVE_JS.replace("__LABELS__", labels)}{script}</script></body></html>
"""


def _freshness() -> str:
    return '<p id="freshness">Published snapshot. Opening the page in a browser reads the live data.</p>'


def _rows(body: str) -> list[list[str]]:
    return queue_rows(body.replace("\r\n", "\n").split("\n"))


def render(body: str) -> str:
    rows = _rows(body)
    units = "\n".join(_row(cells) for cells in rows)
    content = f"""<p>{_links((LIVE_STATUS, "Live status"))}</p>
{_freshness()}
<div class="tiles" id="counts">{_counts(rows)}</div>
<input id="search" type="search" placeholder="Filter by row, app, package, version or PR" aria-label="Filter the queue">
<div class="panel"><table class="queue"><colgroup><col class="order"><col class="status"><col class="app"><col class="version"><col></colgroup><thead><tr><th>#</th><th>Status</th><th>App</th><th>Version</th><th>Details</th></tr></thead>
<tbody id="units">
{units}
</tbody></table></div>"""
    return _page(QUEUE_TITLE, "APK queue", content, QUEUE_JS)


def render_status(body: str, current: str) -> str:
    rows = _rows(body)
    note = _RUN_NOTE.search(current)
    if not note:
        raise SystemExit("the current status page has no run note to carry over")
    active = [r for r in rows if r[1] in ("IN PROGRESS", "IN REVIEW")]
    held = [r for r in rows if r[1] == "BLOCKED"]
    head = "<tr><th>#</th><th>Status</th><th>App</th><th>Details</th></tr>"

    def table(body_id: str, units: list[list[str]]) -> str:
        cells = "".join(_row(r, version=False) for r in units)
        return f'<div class="panel"><table><thead>{head}</thead><tbody id="{body_id}">{cells}</tbody></table></div>'

    content = f"""<p>{_links((QUEUE_VIEW, "Queue view"))}</p>
{_freshness()}
<h2>Run</h2>
<section id="run" class="panel">{note[1].strip()}</section>
<h2>Active</h2>
{table("active", active)}
<h2>Pull requests in the last 7 days</h2>
<div class="panel"><table><thead><tr><th>#</th><th>App</th><th>PR</th><th>State</th></tr></thead>
<tbody id="prs"><tr><td colspan="4">Loads from GitHub when the page opens.</td></tr></tbody></table></div>
<h2>Blocked</h2>
{table("held", held)}"""
    return _page(STATUS_TITLE, "APK queue live status", content, STATUS_JS)


def main(argv: list[str]) -> int:
    if not (argv[:1] == ["queue"] and len(argv) == 2 or argv[:1] == ["status"] and len(argv) == 3):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    body = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text(encoding="utf-8")
    if argv[0] == "queue":
        sys.stdout.write(render(body))
    else:
        sys.stdout.write(render_status(body, Path(argv[2]).read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
