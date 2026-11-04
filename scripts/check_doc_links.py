"""Check that relative links and anchors in the README and docs resolve.

Anchors follow GitHub's heading slugs, including the ``-1`` suffixes of repeated
headings, plus explicit ``<a id>``/``<a name>`` targets.

    uv run --no-sync python scripts/check_doc_links.py
"""

from __future__ import annotations

import html
import re
import sys
from functools import cache
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
# A fence closes on the same character, at least as long, with nothing after it.
_FENCE = re.compile(
    r"^ {0,3}(?:(?P<b>`{3,})|(?P<t>~{3,}))[^\n]*\n.*?"
    r"(?:^ {0,3}(?:(?P=b)`*|(?P=t)~*)[ \t]*$|\Z)",
    re.DOTALL | re.MULTILINE,
)
_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_REFERENCE = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*<?([^\s>]+)>?", re.MULTILINE)
_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_HTML_ANCHOR = re.compile(r"<a\s+(?:id|name)=[\"']([^\"']+)[\"']", re.IGNORECASE)


def documents() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def _strip_code(text: str) -> str:
    return _CODE.sub("", _FENCE.sub("", text))


def _rendered(heading: str) -> str:
    """The heading's rendered text: no links, tags, emphasis or entities; code kept literal."""
    spans: list[str] = []

    def keep(match: re.Match[str]) -> str:
        spans.append(match[1])
        return f"\0{len(spans) - 1}\0"

    text = re.sub(r"`([^`]*)`", keep, heading)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*{1,3})(\S(?:.*?\S)?)\1", r"\2", text)
    text = re.sub(r"(?<!\w)(_{1,3})(\S(?:.*?\S)?)\1(?!\w)", r"\2", text)
    text = html.unescape(text)
    return re.sub(r"\0(\d+)\0", lambda match: spans[int(match[1])], text)


def _slug(heading: str) -> str:
    text = _rendered(heading).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


@cache
def anchors(path: Path) -> frozenset[str]:
    text = _FENCE.sub("", path.read_text(encoding="utf-8"))
    # github-slugger: a repeated slug takes the next unused numeric suffix.
    taken: dict[str, int] = {}
    for heading in _HEADING.findall(text):
        base = slug = _slug(heading)
        while slug in taken:
            taken[base] += 1
            slug = f"{base}-{taken[base]}"
        taken[slug] = 0
    return frozenset({*taken, *_HTML_ANCHOR.findall(text)})


def broken_links(path: Path) -> list[str]:
    problems = []
    text = _strip_code(path.read_text(encoding="utf-8"))
    for target in (*_LINK.findall(text), *_REFERENCE.findall(text)):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        file_part, _, anchor = target.partition("#")
        resolved = (path.parent / unquote(file_part)).resolve() if file_part else path
        if not resolved.exists():
            problems.append(f"{target}: missing file")
        elif anchor and resolved.suffix == ".md" and unquote(anchor) not in anchors(resolved):
            problems.append(f"{target}: missing anchor")
    return problems


def main() -> int:
    failed = False
    for path in documents():
        for problem in broken_links(path):
            failed = True
            print(f"{path.relative_to(ROOT)}: {problem}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
