"""Check that relative links and anchors in the README and docs resolve.

Anchors follow GitHub's heading slugs, including the ``-1`` suffixes of repeated
headings, plus explicit ``<a id>``/``<a name>`` targets.

    uv run --no-sync python scripts/check_doc_links.py
"""

from __future__ import annotations

import re
import sys
from functools import cache
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
_FENCE = re.compile(r"^(```|~~~).*?^\1", re.DOTALL | re.MULTILINE)
_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_HTML_ANCHOR = re.compile(r"<a\s+(?:id|name)=[\"']([^\"']+)[\"']", re.IGNORECASE)


def documents() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def _strip_code(text: str) -> str:
    return _CODE.sub("", _FENCE.sub("", text))


def _slug(heading: str) -> str:
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


@cache
def anchors(path: Path) -> frozenset[str]:
    text = _FENCE.sub("", path.read_text(encoding="utf-8"))
    seen: dict[str, int] = {}
    found = set(_HTML_ANCHOR.findall(text))
    for heading in _HEADING.findall(text):
        slug = _slug(heading)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")
    return frozenset(found)


def broken_links(path: Path) -> list[str]:
    problems = []
    for target in _LINK.findall(_strip_code(path.read_text(encoding="utf-8"))):
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
