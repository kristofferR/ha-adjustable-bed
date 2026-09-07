"""Generate compact production mappings from the accepted row018 table pair.

Usage: uv run python tools/generate_richmat_profiles.py ACTIONS.tsv SELECTORS.tsv SCALARS.json

Prints an apply_patch patch by default; --check verifies the committed catalog.
Inputs are frozen report derivatives, not APKs or decompilation. Hash pinning
prevents accidental use of the superseded, defective runtime extraction.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
from pathlib import Path

ACTIONS_SHA256 = "5267a88431aa50dd8d6d5bd5d917e9db32d5a7a82edda4e1aa0647a3995db5cc"
SELECTORS_SHA256 = "7bc288c81b2438d2c97a5c9b11438021a0afcc68f59fd69223aa74761e025cbb"
REPORT_SHA256 = "3038c935d219550968b21a2a5c8f363d17aac4ef38f668fb5f58a3e4d9bc745d"
SCALARS_SHA256 = "6d5b25829da86dfbcbd9e2e8e504ed91b0e8591fc21f9af36b29ec1afd9a0517"
SCALAR_REPORT_SHA256 = "80522a5e45182f611985aa15d0a3fc22e430be6896b095de38b8b2c92d7552c4"
TARGET = (
    Path(__file__).resolve().parents[1] / "custom_components/adjustable_bed/richmat_profiles.py"
)
BEGIN = "# BEGIN GENERATED CATALOG"
END = "# END GENERATED CATALOG"
FIELDS = (
    "action",
    "index",
    "short_opcode",
    "long_opcode",
    "nordic_short_opcode",
    "operate",
    "button",
    "short_override",
    "long_override",
    "nordic_short_override",
)
INTEGER_FIELDS = frozenset(FIELDS) - {"action", "operate", "button"}
SCALAR_FIELDS = (
    "richmatSleepMonitoringType",
    "isRichmatForcedDisplayBleSleep",
    "isRichmatForcedDisplayLightTherapy",
    "isRichmatSupportRepeatAlarm",
    "isHaveSmartLock",
    "isRichmatHaveLightStrip",
    "isRichmatHaveGrooveLightStrip",
    "isRichmatSupportLightTherapy",
    "isRichmatSupportBlanket",
    "isRichmatHaveWarmColdStrip",
    "isAvocadoSupportRepeatAlarm",
    "isHaveLightStrip",
    "bedLightDisplayType",
    "isSupportRepeatAlarm",
    "rmcSleepMonitoringType",
    "isHaveBottomMassageCountDown",
)


def read_verified(path: Path, expected_hash: str) -> list[dict[str, str]]:
    """Read only the exact frozen input referenced by this implementation."""
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError(f"Frozen input hash mismatch: {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def generate(actions_path: Path, selectors_path: Path, scalars_path: Path) -> str:
    """Deduplicate definitions while retaining selector, getter, and row order."""
    rows = read_verified(actions_path, ACTIONS_SHA256)
    selectors = read_verified(selectors_path, SELECTORS_SHA256)
    products: dict[str, dict[str, list[int]]] = {
        row["product"]: {} for row in selectors if row["product"]
    }
    getters: list[str] = []
    specs: list[tuple[str | int | None, ...]] = []
    spec_ids: dict[tuple[str | int | None, ...], int] = {}
    for row in rows:
        getter = row["getter"]
        if getter not in getters:
            getters.append(getter)
        spec = tuple(
            (int(row[key], 16) if row[key] else None) if key in INTEGER_FIELDS else row[key]
            for key in FIELDS
        )
        if spec not in spec_ids:
            spec_ids[spec] = len(specs)
            specs.append(spec)
        table = products[row["product"]].setdefault(getter, [])
        if int(row["getter_occurrence"]) != len(table):
            raise ValueError(f"Noncontiguous getter occurrence: {row['product']} / {getter}")
        table.append(spec_ids[spec])

    lines = [
        BEGIN,
        "# fmt: off",
        f"# Accepted row018 report manifest: {REPORT_SHA256}",
        f"# {len(products)} concrete products; {len(rows)} ordered occurrences; {len(specs)} shared specs.",
        f"_GETTERS: tuple[str, ...] = {tuple(getters)!r}",
        "_ACTION_SPECS: tuple[_ActionSpec, ...] = (",
    ]
    lines.extend(f"    _ActionSpec{spec!r}," for spec in specs)
    lines.extend(
        [
            ")",
            "_PRODUCT_TABLES: dict[str, tuple[tuple[int, tuple[int, ...]], ...]] = {",
        ]
    )
    for product, tables in products.items():
        compact = tuple((getters.index(getter), tuple(ids)) for getter, ids in tables.items())
        lines.append(f"    {product!r}: {compact!r},")
    lines.append("}")
    scalar_bytes = scalars_path.read_bytes()
    if hashlib.sha256(scalar_bytes).hexdigest() != SCALARS_SHA256:
        raise ValueError(f"Frozen scalar input hash mismatch: {scalars_path}")
    scalar_rows = json.loads(scalar_bytes)["products"]
    settings: dict[tuple[bool | str, ...], list[str]] = {}
    found: set[str] = set()
    for row in scalar_rows:
        code = row["selector"]["selector_string"]
        if not code:
            continue
        if code in found or code not in products:
            raise ValueError(f"Unexpected/duplicate scalar selector: {code}")
        found.add(code)
        values: list[bool | str] = []
        for field in SCALAR_FIELDS:
            cell = row["values"][field]
            if cell["type"] == "bool" and isinstance(cell["value"], bool):
                values.append(cell["value"])
            elif cell["type"] == "enum" and isinstance(cell["name"], str):
                values.append(cell["name"])
            else:
                raise ValueError(f"Unexpected scalar type: {code}/{field}")
        settings.setdefault(tuple(values), []).append(code)
    if found != set(products):
        raise ValueError("Scalar selectors do not cover the complete action catalog")
    lines.extend(
        [
            f"# Scalar appendix manifest: {SCALAR_REPORT_SHA256}",
            "_SETTINGS_GROUPS: tuple[tuple[RichmatProductSettings, tuple[str, ...]], ...] = (",
        ]
    )
    for spec, codes in settings.items():
        lines.append(f"    (RichmatProductSettings{spec!r}, {tuple(codes)!r}),")
    lines.extend(
        [
            ")",
            "_PRODUCT_SETTINGS = {code: settings for settings, codes in _SETTINGS_GROUPS for code in codes}",
            "# fmt: on",
            END,
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """Emit the scoped catalog patch or check that it matches frozen evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actions", type=Path)
    parser.add_argument("selectors", type=Path)
    parser.add_argument("scalars", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = generate(args.actions, args.selectors, args.scalars)
    source = TARGET.read_text(encoding="utf-8")
    old = source[source.index(BEGIN) : source.index(END) + len(END)]
    if args.check:
        if old != generated:
            raise SystemExit("Committed catalog does not match the accepted inputs")
        print("Catalog exactly matches all three frozen inputs")
        return
    print("*** Begin Patch")
    print(f"*** Update File: {TARGET}")
    for line in list(difflib.unified_diff(old.splitlines(), generated.splitlines(), lineterm=""))[
        2:
    ]:
        print("@@" if line.startswith("@@") else line)
    print("*** End Patch")


if __name__ == "__main__":
    main()
