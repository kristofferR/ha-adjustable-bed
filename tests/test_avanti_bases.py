"""Row065 Avanti Bases 1.0.5 (7), vectors from its accepted FULL report.

These literals were checked against Avanti E07-E15 and audit round01, not
inferred from another ORE app. Hardware remains unverified.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import ATTR_ASSUMED_STATE, ATTR_ENTITY_ID, CONF_ADDRESS, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.beds.ore_comfort_bed import (
    STATE_LEVEL,
    STATE_TIMER,
    OreComfortBedController,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow, _per_side_refusal
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_AVANTI_BASES,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options

# Share transport/HA fixture helpers only; Avanti's command vectors stay below.
from .test_ore_comfort_bed import _char, _controller, _entry, _services, _waits, _written

APP = KEESON_VARIANT_AVANTI_BASES
STOP = "e5fe160000000006"

# E09-E11: all 20 directional UI controls, including the distinct same-key roles.
AXES = (
    (2, "back", "e5fe160000000105", "e5fe160000000204"),
    (2, "feet", "e5fe160000000402", "e5fe1600000008fe"),
    (2, "both", "e5fe1600000010f6", "e5fe1600000020e6"),
    (3, "back", "e5fe160000000105", "e5fe160000000204"),
    (3, "feet", "e5fe160000000402", "e5fe1600000008fe"),
    (3, "head", "e5fe1600000010f6", "e5fe1600000020e6"),
    (4, "back", "e5fe160000000105", "e5fe160000000204"),
    (4, "feet", "e5fe160000000402", "e5fe1600000008fe"),
    (4, "waist", "e5fe1600000010f6", "e5fe1600000020e6"),
    (4, "lumbar", "e5fe1600000040c6", "e5fe160000008086"),
)
# E13/E14, including the audit's corrected slider resource ranges and guard caveat.
LEVELS = {
    "head": ("e5fe1610000010e6", "e5fe1610000011e5", "e5fe1610000012e4", "e5fe1610000013e3"),
    "foot": ("e5fe1611000010e5", "e5fe1611000011e4", "e5fe1611000012e3", "e5fe1611000013e2"),
    "wave": ("e5fe1610000020d6", "e5fe1610000021d5", "e5fe1610000022d4", "e5fe1610000023d3"),
}


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.ore_comfort_bed.asyncio.sleep", sleep
    )
    return sleep


@pytest.mark.parametrize(("motors", "axis", "up", "down"), AXES)
async def test_avanti_movement_vectors_and_release(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
    motors: int,
    axis: str,
    up: str,
    down: str,
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP, motors)
    spec = next(s for s in ctrl.motor_control_specs if s.key == axis)
    assert spec.translation_key == axis
    assert spec.scheduler_resource == "*"
    for action, expected in ((spec.open_fn, up), (spec.close_fn, down)):
        mock_bleak_client.write_gatt_char.reset_mock()
        sleeps.reset_mock()
        await action(ctrl)
        count = ctrl._coordinator.motor_pulse_count
        assert _written(mock_bleak_client) == [expected] * count + [STOP]
        assert _waits(sleeps) == [0.1] * count


async def test_avanti_single_action_vectors(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP)
    # E08, E12, E15: one write after 100 ms, no trailing release.
    actions = (
        (ctrl.stop_all, STOP),
        (ctrl.preset_flat, "e5fe160100000203"),
        (ctrl.preset_zero_g, "e5fe160100000104"),
        (ctrl.program_flat, "e5fe1620000002e4"),
        (ctrl.program_zero_g, "e5fe1620000001e5"),
        (lambda: ctrl.preset_memory(1), "e5fe1601000008fd"),
        (lambda: ctrl.preset_memory(2), "e5fe1601000009fc"),
        (lambda: ctrl.program_memory(1), "e5fe1620000008de"),
        (lambda: ctrl.program_memory(2), "e5fe1620000009dd"),
        (ctrl.lights_on, "e5fe1631000001d4"),
        (ctrl.lights_off, "e5fe1631000000d5"),
        (lambda: ctrl.set_massage_timer_option("10"), "e5fe1610000030c6"),
        (lambda: ctrl.set_massage_timer_option("20"), "e5fe1610000031c5"),
        (lambda: ctrl.set_massage_timer_option("30"), "e5fe1610000032c4"),
    )
    for action, frame in actions:
        mock_bleak_client.write_gatt_char.reset_mock()
        sleeps.reset_mock()
        await action()
        assert _written(mock_bleak_client) == [frame]
        assert _waits(sleeps) == [0.1]


async def test_avanti_massage_vectors_and_preferences(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
    hass_storage: dict,
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP)
    assert ctrl.persisted_app_state == {"wave": 1, "head": 1, "foot": 1}
    await ctrl.massage_start()
    assert _written(mock_bleak_client) == [LEVELS[z][1] for z in ("wave", "head", "foot")]
    # The app's 40 raw slider ticks reduce to these four observable BLE levels.
    for zone, frames in LEVELS.items():
        for level, frame in enumerate(frames):
            mock_bleak_client.write_gatt_char.reset_mock()
            sleeps.reset_mock()
            await ctrl.set_massage_level(zone, level)
            assert _written(mock_bleak_client) == [frame]
            assert _waits(sleeps) == [0.1]
    mock_bleak_client.write_gatt_char.reset_mock()
    sleeps.reset_mock()
    await ctrl.massage_start()
    assert _written(mock_bleak_client) == [LEVELS[z][3] for z in ("wave", "head", "foot")]
    assert _waits(sleeps) == [0.1] * 3
    await ctrl.set_massage_timer_option("30")
    mock_bleak_client.write_gatt_char.reset_mock()
    sleeps.reset_mock()
    await ctrl.massage_off()
    assert _written(mock_bleak_client) == [LEVELS["head"][0], LEVELS["foot"][0]]
    assert _waits(sleeps) == [0.1] * 2
    assert ctrl._coordinator.controller_state[STATE_TIMER] is None
    assert all(ctrl._coordinator.controller_state[k] == 3 for k in STATE_LEVEL.values())
    coordinator = ctrl._coordinator
    await coordinator.async_shutdown()
    restarted = AdjustableBedCoordinator(hass, coordinator.entry)
    await restarted.async_connect()
    assert restarted.controller.persisted_app_state == {"wave": 3, "head": 3, "foot": 3}
    await restarted.async_shutdown()


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_avanti_cancelled_movement_releases(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
    task_cancel: bool,
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP)
    if task_cancel:
        # Cancellation while a held write is in flight must still send release.
        mock_bleak_client.write_gatt_char.side_effect = [asyncio.CancelledError(), None]
        with pytest.raises(asyncio.CancelledError):
            await ctrl.move_back_up()
        assert _written(mock_bleak_client)[-1] == STOP
    else:
        ctrl._coordinator.cancel_command.set()
        try:
            await ctrl.move_back_up()
        finally:
            ctrl._coordinator.cancel_command.clear()
        assert _written(mock_bleak_client) == [STOP]


@pytest.mark.parametrize("properties", [["write"], ["write", "write-without-response"]])
async def test_avanti_gatt_and_no_reported_state(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
    properties: list[str],
) -> None:
    ctrl = await _controller(hass, mock_bleak_client, APP)
    first = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    last = _char(KEESON_BASE_WRITE_CHAR_UUID, properties)
    notify = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    mock_bleak_client.services = [
        SimpleNamespace(uuid="arbitrary-service-1", characteristics=[first, notify]),
        SimpleNamespace(uuid="arbitrary-service-2", characteristics=[last]),
    ]
    await ctrl.preset_flat()
    call = mock_bleak_client.write_gatt_char.await_args
    assert call.args[0] is last
    assert call.kwargs["response"] is ("write-without-response" not in properties)
    assert not ctrl.supports_position_feedback
    await ctrl.start_notify()
    await ctrl.read_positions()
    mock_bleak_client.start_notify.assert_not_called()
    mock_bleak_client.read_gatt_char.assert_not_called()
    # Both roles are required, but neither an ACK nor a handshake is required.
    ctrl._write_char = None
    mock_bleak_client.services = _services(last)
    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(HomeAssistantError, match="FFE9 and FFE4"):
        await ctrl.preset_flat()
    assert not _written(mock_bleak_client)


async def test_avanti_app_choice_and_side_owned_layout(hass: HomeAssistant) -> None:
    choice = bed_type_choice(BED_TYPE_KEESON, APP)
    assert {o["value"]: o["label"] for o in get_bed_type_options()}[
        choice
    ] == "Avanti Bases app (Keeson)"
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._disconnect_choice_confirmed = True
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_manual_entry(
        {
            CONF_ADDRESS: "AA:BB:CC:DD:06:50",
            CONF_BED_TYPE: choice,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            CONF_MOTOR_COUNT: 4,
        }
    )
    # The app's screen sets the motor count; the entered one is its default.
    screen = await flow.async_step_profile_questions()
    assert screen["step_id"] == "profile_questions"
    await flow.async_step_profile_questions({CONF_MOTOR_COUNT: "4"})
    saved = flow._finish_with_verify.await_args.args[0]
    assert (saved[CONF_BED_TYPE], saved[CONF_PROTOCOL_VARIANT], saved[CONF_MOTOR_COUNT]) == (
        BED_TYPE_KEESON,
        APP,
        4,
    )
    # The screen question asks the motor count, so the generic form hides it too.
    assert hidden_generic_fields(BED_TYPE_KEESON, APP) == {
        CONF_MOTOR_COUNT,
        CONF_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_PULSE_DELAY_MS,
    }
    for changes, key in (
        ({CONF_MOTOR_COUNT: 3}, CONF_MOTOR_COUNT),
        ({CONF_PROTOCOL_VARIANT: "sino"}, CONF_PROTOCOL_VARIANT),
    ):
        assert _per_side_refusal((BED_TYPE_KEESON, APP), [(BED_TYPE_KEESON, APP)] * 2, changes) == (
            key,
            "Avanti Bases",
        )


@pytest.mark.parametrize("motors", [2, 3, 4])
async def test_avanti_entities_and_serialized_actions(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
    enable_custom_integrations,
    motors: int,
) -> None:
    address = "AA:BB:CC:DD:06:50"
    mock_bleak_client.services = _services(
        _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"]),
        _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"]),
    )
    entry = _entry(hass, APP, motors, address)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def entity(platform: str, key: str) -> str:
        found = registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}")
        assert found is not None, key
        return found

    ctrl = hass.data[DOMAIN][entry.entry_id].controller
    assert isinstance(ctrl, OreComfortBedController)
    assert ctrl.protocol_diagnostics["app_package"] == "com.ore.AvantiBases 1.0.5 (7)"
    assert {s.key for s in ctrl.motor_control_specs} == {r[1] for r in AXES if r[0] == motors}
    for spec in ctrl.motor_control_specs:
        entity("cover", spec.key)
    for key in (
        "stop",
        "preset_flat",
        "preset_zero_g",
        "preset_memory_1",
        "preset_memory_2",
        "program_memory_1",
        "program_memory_2",
        "ore_comfort_program_flat",
        "ore_comfort_program_zero_g",
        "ore_comfort_massage_start",
        "massage_all_off",
    ):
        entity("button", key)
    for zone in LEVELS:
        entity("number", f"controller_number_ore_comfort_massage_{zone}")
    entity("select", f"controller_select_{STATE_TIMER}")
    for key in ("back_position", "legs_position", "head_position", "lumbar_position"):
        assert registry.async_get_entity_id("number", DOMAIN, f"{address}_{key}") is None
    light = entity("switch", "under_bed_lights")
    assert hass.states.get(light).state == STATE_UNKNOWN
    assert hass.states.get(light).attributes[ATTR_ASSUMED_STATE] is True
    mock_bleak_client.write_gatt_char.reset_mock()
    # Exercise the user-facing button through the coordinator's command lock.
    await hass.services.async_call(
        "button",
        "press",
        {
            ATTR_ENTITY_ID: entity("button", "ore_comfort_program_flat"),
        },
        blocking=True,
    )
    assert _written(mock_bleak_client) == ["e5fe1620000002e4"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
