"""Keep the accepted row107 coverage ledger tied to executable support."""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed import doublesleep_protocol as p
from custom_components.adjustable_bed.doublesleep_state import daily_report

ROOT = Path(__file__).resolve().parents[1]
LEDGER = json.loads((ROOT / "tests/fixtures/doublesleep_ledger.json").read_text())


def test_accepted_inventory_is_exhaustive_and_references_exist():
    for table, count in (
        ("candidates", 629),
        ("commands", 143),
        ("action_protocol_cells", 273),
        ("models", 10),
        ("report_members", 46),
        ("artifact_members", 511),
    ):
        rows = LEDGER[table]
        assert len(rows) == count
        assert len({row.get("id", row.get("name")) for row in rows}) == count
    for group in LEDGER["groups"].values():
        for reference in [*group["code"], *group["tests"]]:
            filename, _, symbol = reference.partition(":")
            path = ROOT / filename
            assert path.is_file(), reference
            if symbol:
                text = path.read_text()
                if path.suffix == ".py":
                    nodes = list(ast.walk(ast.parse(text)))
                    for part in symbol.split("."):
                        matching = [
                            node
                            for node in nodes
                            if getattr(node, "name", None) == part
                            or isinstance(node, ast.Name)
                            and node.id == part
                        ]
                        assert matching, reference
                        nodes = [child for node in matching for child in ast.walk(node)]
                else:
                    assert symbol in text, reference
    for table in (
        "candidates",
        "commands",
        "action_protocol_cells",
        "models",
        "notifications",
        "cache_fields",
        "report_consumers",
        "report_fields",
        "artifact_members",
    ):
        for row in LEDGER[table]:
            assert row["disposition"] in ("IMPLEMENTED", "ALREADY_IMPLEMENTED", "EXCLUDED")
            if row["disposition"] == "EXCLUDED":
                assert row.get("reason"), row
            else:
                assert row["groups"], row
                assert all(group in LEDGER["groups"] for group in row["groups"])
    assert LEDGER["native_callsite_coverage"]["total"] == 1317
    assert len(LEDGER["cache_fields"]) == 16


def test_every_reachable_command_is_supported_and_every_other_slot_refuses_write():
    supported = {"p1": p.P1_SUPPORTED, "p2": p.P2_SUPPORTED, "p3": p.P3_SUPPORTED}
    for driver, indices in supported.items():
        rows = [row for row in LEDGER["commands"] if row["driver"].lower() == driver]
        assert {row["index"] for row in rows if row["disposition"] == "IMPLEMENTED"} == indices
        for index in range(91):
            if index in indices:
                continue
            with pytest.raises(ValueError):
                if driver == "p3":
                    p.JsonWriter().command(index, (), datetime.now(UTC), 247)
                else:
                    p.binary_command(driver, index, (), p.Cache(), datetime.now(UTC))
    assert p.binary_command("p1", 32, (), p.Cache(), datetime.now(UTC)) == b""
    assert {int(row["id"]) for row in LEDGER["models"]} == set(p.MODELS)
    assert {int(row["id"]) for row in LEDGER["models"] if row["is_double"]} == p.DOUBLE_MODELS


def test_every_daily_consumer_key_has_an_exact_default_and_no_local_score_is_fabricated():
    expected = {
        row["id"].split(":")[1] for row in LEDGER["report_fields"] if row["id"].startswith("DAILY:")
    }
    assert set(daily_report({})) == expected
    for field in (
        "resilience_ability",
        "stress_level",
        "fatigue_level",
        "autonomic_nervous_system_activity",
        "recovery_level",
    ):
        row = next(row for row in LEDGER["report_fields"] if row["id"] == "LEGACY:" + field)
        assert row["disposition"] == "EXCLUDED"
