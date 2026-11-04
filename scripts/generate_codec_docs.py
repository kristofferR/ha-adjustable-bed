"""Regenerate the tables in codec guides that codec and profile data already know.

A codec guide marks each generated region with ``<!-- generated:<name> -->`` and
``<!-- /generated -->``. Run this script to rewrite the regions, or with
``--check`` to fail when one is stale (``tests/test_codec_docs.py`` does).

Each codec family's renderers live in ``scripts/codec_docs/<family>.py``, which
exports its ``BLOCKS``; this driver discovers them. To generate a block for a
family, write a renderer over its codec and profile modules and add it to that
module's ``BLOCKS``. Build every frame through the codec, so a table row cannot
show a frame its encoder does not produce.

    uv run --no-sync python scripts/generate_codec_docs.py [--check]
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import codec_docs  # noqa: E402
from scripts.codec_docs import _configuration  # noqa: E402
from scripts.codec_docs._common import Block  # noqa: E402


def family_modules() -> dict[str, ModuleType]:
    """Every family's renderer module, by family name."""
    return {
        info.name: importlib.import_module(f"{codec_docs.__name__}.{info.name}")
        for info in pkgutil.iter_modules(codec_docs.__path__)
        if not info.name.startswith("_")
    }


# Family blocks, then the cross-family blocks of the configuration guide.
BLOCKS: list[Block] = [
    *(block for module in family_modules().values() for block in module.BLOCKS),
    *_configuration.BLOCKS,
]


def _pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- generated:{re.escape(name)} -->\n).*?(<!-- /generated -->)", re.DOTALL
    )


def render(text: str, name: str, body: str) -> str:
    pattern = _pattern(name)
    if not pattern.search(text):
        raise ValueError(f"missing generated block {name!r}")
    return pattern.sub(lambda match: f"{match[1]}{body}\n{match[2]}", text, count=1)


def _rendered(guide: str) -> str:
    text = (ROOT / guide).read_text(encoding="utf-8")
    for block_guide, name, renderer in BLOCKS:
        if block_guide == guide:
            text = render(text, name, renderer())
    return text


def stale_guides() -> list[str]:
    """Return the guides whose generated blocks differ from their codec and profile data."""
    guides = dict.fromkeys(guide for guide, _, _ in BLOCKS)
    return [
        guide for guide in guides if _rendered(guide) != (ROOT / guide).read_text(encoding="utf-8")
    ]


def main(argv: list[str]) -> int:
    if "--check" in argv:
        stale = stale_guides()
        for guide in stale:
            print(f"{guide} is stale; run scripts/generate_codec_docs.py", file=sys.stderr)
        return 1 if stale else 0
    for guide in dict.fromkeys(guide for guide, _, _ in BLOCKS):
        (ROOT / guide).write_text(_rendered(guide), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
