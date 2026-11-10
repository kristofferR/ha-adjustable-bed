"""Unit152: replay the accepted OKIN Comfort Bed 1.1.6 (8) command rows.

Fixture literals come from the frozen report, manifest SHA-256
313a09f8e5f9aa06cc11ca465bb8d4bbee31eb30816586296e2061a3d1229675.
Hardware is unverified. Shared helpers provide HA/transport fixtures only.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypedDict
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow, _per_side_refusal
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    KEESON_VARIANT_OKIN_COMFORT_BED,
)
from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options
from custom_components.adjustable_bed.profiles.keeson import OKIN_COMFORT_BED, encode
from tests.form_helpers import finish_new_bed, start_new_bed
from tests.keeson_vectors import FROZEN_FRAMES
from tests.test_ore_comfort_bed import _controller, _waits, _written

APP = KEESON_VARIANT_OKIN_COMFORT_BED
FIXTURE = Path(__file__).parent / "fixtures/okin_comfort_bed/vectors.json"


class Inputs(TypedDict):
    words: list[str]


class Vector(TypedDict):
    id: str
    variant: str
    action: str
    inputs: Inputs
    expected_bytes: str


VECTORS: list[Vector] = json.loads(FIXTURE.read_text())


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.ore_comfort_bed.asyncio.sleep", sleep)
    return sleep


def test_frozen_rows_use_existing_codec_byte_for_byte() -> None:
    assert len(VECTORS) == 104
    frames = set()
    for row in VECTORS:
        expected = row["expected_bytes"].split(" ; ")
        assert [encode(OKIN_COMFORT_BED, int(word, 16)).hex() for word in row["inputs"]["words"]] == expected
        frames.update(expected)
    assert FROZEN_FRAMES[APP] == frames


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
async def test_every_reachable_command_row(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
    row: Vector,
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP, int(row["variant"][-1]))
    action = row["action"]
    expected = row["expected_bytes"].split(" ; ")
    held = action.endswith((" up", " down"))
    if held:
        axis, direction = action.split()
        key = {"foot": "feet", "union": "both"}.get(axis, axis)
        spec = next(spec for spec in ctrl.motor_control_specs if spec.key == key)
        assert spec.scheduler_resource == "*"
        assert ctrl.execution.hold == "stream"
        assert not ctrl.execution.concurrent
        await (spec.open_fn if direction == "up" else spec.close_fn)(ctrl)
        expected = expected * ctrl._coordinator.motor_pulse_count + ["e5fe160000000006"]
    elif action.startswith("movement release"):
        await ctrl.stop_all()
    elif action.startswith(("recall ", "save ")):
        verb, preset = action.split()
        if preset in ("MemoryA", "MemoryB"):
            slot = 1 if preset == "MemoryA" else 2
            await (ctrl.preset_memory if verb == "recall" else ctrl.program_memory)(slot)
        else:
            method = {
                ("recall", "Zg"): ctrl.preset_zero_g,
                ("save", "Zg"): ctrl.program_zero_g,
                ("recall", "Flat"): ctrl.preset_flat,
                ("save", "Flat"): ctrl.program_flat,
            }[verb, preset]
            await method()
    elif action.startswith("light "):
        await (ctrl.lights_on if action == "light on" else ctrl.lights_off)()
    elif action.startswith("massage timer "):
        await ctrl.set_massage_timer_option(action.split()[2])
    elif action == "massage start (defaults)":
        await ctrl.massage_start()
    elif action == "massage stop":
        await ctrl.massage_off()
    else:
        assert action.startswith(("massage wave ", "massage head intensity ", "massage foot intensity "))
        await ctrl.set_massage_level(action.split()[1], int(action.split()[-1]))
    assert _written(mock_bleak_client) == expected
    # Holds have N-1 inter-write waits and one delayed release; singletons
    # each wait once, with no implicit trailing zero frame.
    assert _waits(sleeps) == [0.1] * (len(expected) - int(held))
    assert ctrl.protocol_diagnostics["app_package"] == "com.ore.okincomfortbed 1.1.6 (8)"


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_cancelled_hold_still_releases(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, task_cancel: bool,
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP)
    if task_cancel:
        mock_bleak_client.write_gatt_char.side_effect = [asyncio.CancelledError(), None]
        with pytest.raises(asyncio.CancelledError):
            await ctrl.move_back_up()
    else:
        ctrl._coordinator.cancel_command.set()
        try:
            await ctrl.move_back_up()
        finally:
            ctrl._coordinator.cancel_command.clear()
    assert _written(mock_bleak_client)[-1] == "e5fe160000000006"


async def test_app_is_findable_and_owns_each_receivers_screen(hass: HomeAssistant) -> None:
    choice = bed_type_choice(BED_TYPE_KEESON, APP)
    assert {o["value"]: o["label"] for o in get_bed_type_options()}[choice] == "OKIN Comfort Bed app (Keeson)"
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    screen = await start_new_bed(flow, "typed", choice, "AA:BB:CC:DD:15:20")
    assert screen["step_id"] == "profile_questions"
    await finish_new_bed(flow, await flow.async_step_profile_questions({CONF_MOTOR_COUNT: "4"}))
    saved = flow._finish_with_verify.await_args.args[0]
    assert (saved[CONF_BED_TYPE], saved[CONF_PROTOCOL_VARIANT], saved[CONF_MOTOR_COUNT]) == (BED_TYPE_KEESON, APP, 4)
    assert hidden_generic_fields(BED_TYPE_KEESON, APP) == {
        CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_DISABLE_ANGLE_SENSING, CONF_MOTOR_PULSE_DELAY_MS,
    }
    for changes, key in (
        ({CONF_MOTOR_COUNT: 3}, CONF_MOTOR_COUNT),
        ({CONF_PROTOCOL_VARIANT: "sino"}, CONF_PROTOCOL_VARIANT),
    ):
        assert _per_side_refusal((BED_TYPE_KEESON, APP), [(BED_TYPE_KEESON, APP)] * 2, changes) == (key, "OKIN Comfort Bed")


async def test_connection_only_resolves_live_gatt_without_initial_commands(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
) -> None:
    from types import SimpleNamespace

    from custom_components.adjustable_bed.const import (
        KEESON_BASE_NOTIFY_CHAR_UUID,
        KEESON_BASE_WRITE_CHAR_UUID,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_ore_comfort_bed import _char, _entry

    first = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    last = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write-without-response"])
    notify = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    mock_bleak_client.services = [
        SimpleNamespace(uuid="0000abcd-0000-1000-8000-00805f9b34fb", characteristics=[first, notify]),
        SimpleNamespace(uuid="0000dcba-0000-1000-8000-00805f9b34fb", characteristics=[last]),
    ]
    coord = AdjustableBedCoordinator(hass, _entry(hass, APP, 4))
    await coord.async_connect()
    mock_bleak_client.write_gatt_char.assert_not_called()
    mock_bleak_client.start_notify.assert_not_called()
    mock_bleak_client.read_gatt_char.assert_not_called()
    await coord.controller.preset_flat()
    assert mock_bleak_client.write_gatt_char.call_args.args[0] is last
    assert mock_bleak_client.write_gatt_char.call_args.kwargs["response"] is False
    await coord.async_disconnect()
    # A new connection must choose a new handle and mode, with no stale cache.
    mock_bleak_client.services[1].characteristics = [first]
    await coord.async_connect()
    await coord.controller.preset_flat()
    assert mock_bleak_client.write_gatt_char.call_args.args[0] is first
    assert mock_bleak_client.write_gatt_char.call_args.kwargs["response"] is True
