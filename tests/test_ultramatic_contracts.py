"""App-only generation boundaries and newly added native capability bridge."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.adjustable_bed.profiles import ultramatic as app
from scripts.codec_docs import okin_nframe as docs
from scripts.codec_docs._ultramatic import render
from scripts.generate_codec_docs import _rendered, family_modules
from tests.card_placements import FIXTURE, controller_entities, placements
from tests.entity_translation_reachability import entity_strings, missing_translations
from tests.hold_lease_wire import virtual_clock
from tests.test_ultramatic_runtime import ALARM_REPORT, runtime, writes  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
BED = "ultramatic_smart_bed"


async def test_native_massage_bridge_uses_admitted_proven_action(runtime):  # noqa: F811 - pytest fixture
    _, coord, client = runtime
    with virtual_clock():
        await coord.async_execute_controller_command(lambda c: c.massage_toggle(), resource="*")
    assert coord.controller.supports_massage_toggle_control
    assert writes(client) == [app.control("massageOnOff"), *([app.QUERY_MASSAGE] * 3)]


def test_private_renderer_is_registered_under_existing_family():
    assert "ultramatic" not in family_modules()
    assert ("docs/beds/okin-nframe.md", "ultramatic-controls", render) in docs.BLOCKS
    text = render()
    assert "without response" in text and "indicate accepted" in text
    assert "05 02 00 00 00 00 00" in text


async def test_app_translation_slugs_and_stable_ids(
    runtime,  # noqa: F811 - pytest fixture
):
    _, coordinator, _ = runtime
    specs = coordinator.controller.controller_button_specs
    assert {
        "ultramatic_timerSwitch",
        "ultramatic_headStrengthAdd",
        "ultramatic_headStrengthReduce",
        "ultramatic_footStrengthAdd",
        "ultramatic_footStrengthReduce",
        "ultramatic_waveAdd",
        "ultramatic_waveReduce",
    } <= {spec.key for spec in specs}
    for path in ("strings.json", "translations/en.json"):
        labels = json.loads((ROOT / "custom_components/adjustable_bed" / path).read_text())
        for spec in specs:
            assert spec.translation_key is not None
            assert re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", spec.translation_key)
            assert labels["entity"]["button"][spec.translation_key]["name"]


async def test_card_app_fixture_matches_actual_factory(runtime):  # noqa: F811 - pytest fixture
    _, coord, _ = runtime
    current = json.loads(FIXTURE.read_text())
    expected = placements(controller_entities([coord.controller]))
    assert expected and all(current[key] == value for key, value in expected.items())
    app_keys = {key for key in current if key.split(":", 1)[1].startswith("ultramatic_")}
    assert app_keys == {key for key in expected if key.split(":", 1)[1].startswith("ultramatic_")}


def test_wire_app_scenarios_schema_aliases_and_exact_gatt():
    data = json.loads((ROOT / "tests/fixtures/wire_snapshot.json").read_text())
    app_scenarios = {key for key in data["scenarios"] if key == BED or key.startswith(BED + ":")}
    assert app_scenarios == {BED} | {
        f"{BED}:{side}:{notify}:{header}"
        for side in ("A", "AB", "B")
        for notify in ("notify", "indicate")
        for header in ("ed", "a5")
    }
    assert data["schema"] == 3
    assert data["chars"]["6e400002"] == app.WRITE_UUID
    assert data["chars"]["6e400003"] == app.NOTIFY_UUID
    for key in app_scenarios:
        assert not data["scenarios"][key]["info"].get("gaps"), key
        assert data["scenarios"][key]["commands"]["connect"]["status"] == "ok"
        assert data["scenarios"][key]["info"]["bed_type"] == BED
        toggle = data["scenarios"][key]["commands"]["ultramatic_alarm_toggle"]
        if key == BED or key.startswith(BED + ":AB:"):
            assert toggle == {"status": "no_writes"}
        else:
            assert toggle["status"] == "ok"
    layouts = json.loads((ROOT / "tests/fixtures/wire_snapshot_layouts.json").read_text())
    for key, notify in ((BED, "notify"), (BED + ":indicate", "indicate")):
        assert layouts[key] == {
            "services": {app.SERVICE_UUID: [app.WRITE_UUID, app.NOTIFY_UUID]},
            "properties": {app.WRITE_UUID: ["write-without-response"], app.NOTIFY_UUID: [notify]},
        }


async def test_app_wire_plan_records_unequal_combined_toggle_as_safe_no_writes(
    runtime,  # noqa: F811 - pytest fixture
):
    from scripts.wire_snapshot import plan_commands

    _, coordinator, client = runtime
    client.start_notify.await_args.args[1](None, bytearray(ALARM_REPORT))
    command = next(
        c for c in plan_commands(coordinator.controller) if c.name == "ultramatic_alarm_toggle"
    )
    await command.call(coordinator.controller)
    assert command.declared and not command.is_gap("no_writes")
    assert writes(client) == []


async def test_app_wire_plan_does_not_mask_an_unsafe_combined_toggle_regression(
    runtime,  # noqa: F811 - pytest fixture
):
    from scripts.wire_snapshot import plan_commands

    _, coordinator, client = runtime
    command = next(
        c for c in plan_commands(coordinator.controller) if c.name == "ultramatic_alarm_toggle"
    )
    with (
        patch.object(coordinator.controller, "prepare_alarm", return_value=object()),
        pytest.raises(AssertionError, match="Unequal Ultramatic records"),
    ):
        await command.call(coordinator.controller)
    assert writes(client) == []


def test_only_changed_guide_outputs_are_current():
    for name in ("docs/beds/okin-nframe.md", "docs/CONFIGURATION.md"):
        assert _rendered(name) == (ROOT / name).read_text()


async def test_app_factory_entities_have_translations(runtime):  # noqa: F811 - pytest fixture
    _, coord, _ = runtime
    assert missing_translations(entity_strings(), [coord.controller]) == {}
