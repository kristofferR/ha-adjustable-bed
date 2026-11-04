"""Regenerate the manifest's Bluetooth matchers from the declared discovery hints.

Each family declares its hints in
``custom_components/adjustable_bed/discovery_hints/<family>.py``. Run this
script to rewrite the manifest's ``bluetooth`` list from them, or with
``--check`` to fail when the manifest is stale (CI runs it).

    uv run --no-sync python scripts/generate_bluetooth_matchers.py [--check]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.adjustable_bed.discovery_hints import manifest_matchers  # noqa: E402

MANIFEST = ROOT / "custom_components" / "adjustable_bed" / "manifest.json"


def rendered() -> str:
    """The manifest text with its ``bluetooth`` list generated from the hints."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["bluetooth"] = manifest_matchers()
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    text = rendered()
    if "--check" in argv:
        if text != MANIFEST.read_text(encoding="utf-8"):
            print(
                f"{MANIFEST.relative_to(ROOT)} is stale; run scripts/generate_bluetooth_matchers.py",
                file=sys.stderr,
            )
            return 1
        return 0
    MANIFEST.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
