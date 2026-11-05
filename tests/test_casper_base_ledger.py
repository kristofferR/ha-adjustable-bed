"""The row101 delivery must retain every disposition and resolvable code/test reference."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_disposition_coverage_and_references():
    ledger = json.loads((ROOT / "tests/fixtures/casper_base/ledger.json").read_text())
    entries = ledger["entries"]
    assert len({e["id"] for e in entries}) == len(entries) == 568
    assert Counter(e["disposition"] for e in entries) == {"IMPLEMENTED": 535, "EXCLUDED": 33}
    assert Counter(e["domain"] for e in entries) == ledger["domains"]
    assert sum(e["domain"] == "command" for e in entries) == 181
    assert sum(e["domain"] == "decoder" for e in entries) == 56
    for e in entries:
        assert e["evidence"] and e["behavior"]
        assert e["implementation_group"] in ledger["implementation_groups"]
        assert e["validation_group"] in ledger["validation_groups"]
        if e["disposition"] == "EXCLUDED":
            assert e["reason"]
        for contract in e.get("contracts", []):
            assert any(x["id"] == contract for x in entries)
    for groups in ("implementation_groups", "validation_groups"):
        for refs in ledger[groups].values():
            assert refs
            for ref in refs:
                path, _, symbols = ref.partition(":")
                assert (ROOT / path).is_file(), ref
                if symbols:
                    source = (ROOT / path).read_text()
                    assert all(symbol in source for symbol in symbols.split("/")), ref
    assert (
        ledger["authority"]["report_manifest_sha256"]
        == "1cc13b9e51aa6e74e7f6a507c7418b1420f72a734d5eb7027b60db11ccf6daef"
    )
    assert (
        ledger["authority"]["audit_manifest_sha256"]
        == "bfc0cea59e3685b8970fbb6d5d5728973238dd8789235b09f6600396c98dbbc0"
    )
