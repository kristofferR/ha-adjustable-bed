"""Durable exact-ID closure and profile-order references for accepted row126."""

import json
from collections import Counter
from pathlib import Path

from custom_components.adjustable_bed.hush_catalog import PRODUCTS

ROOT = Path(__file__).parents[1]
LEDGER = ROOT / "docs/apk-analysis/dispositions/row126-hush-base.json"


def test_exact_registry_closure_and_distinct_roles():
    data = json.loads(LEDGER.read_text())
    groups = {x["id"]: x for x in data["groups"]}
    assert Counter(g["disposition"] for g in groups.values()) == {
        "IMPLEMENTED": 10,
        "ALREADY_IMPLEMENTED": 3,
        "EXCLUDED": 6,
    }
    for key, size in [("owned", 2381), ("candidates", 3207), ("commands", 3014)]:
        rows = data[key]
        assert len(rows) == size
        assert [r[0] for r in rows] == list(range(size))
        assert all(r[-1] in groups for r in rows)
    assert len({(x[1], x[2]) for x in data["owned"]}) == 2381
    assert len({x[1] for x in data["candidates"]}) == 3207
    assert len({x[1] for x in data["commands"]}) == 3014
    assert all(len(x[3]) == 64 for x in data["commands"])
    for group in groups.values():
        assert group["accepted_source"]
        if group["disposition"] == "EXCLUDED":
            assert group["reason"]
        else:
            assert group["code"] and group["tests"]
            for ref in group["code"].split("; "):
                path = ref.split(":")[0]
                assert (ROOT / "custom_components/adjustable_bed" / path).is_file(), path
    fixture = json.loads((ROOT / "tests/fixtures/hush_catalog.json").read_text())
    assert len(fixture["products"]) == 72
    assert fixture["products"][0]["groups"] == [[], [], [], [], []]
    assert len(PRODUCTS) == 71
    assert sum(sum(map(len, p["groups"])) for p in fixture["products"]) == 1527
