"""Accepted com.okin.enhancements 1.0.3 (4) vectors, not hardware captures."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.comfort_enhancements import (
    ComfortEnhancementsController,
    alarm_frame,
    clock_frame,
    control_frame,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_COMFORT_ENHANCEMENTS,
    COMFORT_ENHANCEMENTS_VARIANTS,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type
from tests.state_helpers import massage_levels

ADDRESS = "AA:BB:CC:DD:01:10"
STOP = "e5fe160000000006"
PRESET_STOP = "e5fe160100000005"

# Every reachable static control builder in the accepted revised report.
VECTORS = {
    0x0: STOP,
    0x1: "e5fe160000000105",
    0x2: "e5fe160000000204",
    0x4: "e5fe160000000402",
    0x8: "e5fe1600000008fe",
    0x10: "e5fe1600000010f6",
    0x20: "e5fe1600000020e6",
    0x01000000: PRESET_STOP,
    0x01000001: "e5fe160100000104",
    0x01000002: "e5fe160100000203",
    0x01000003: "e5fe160100000302",
    0x01000004: "e5fe160100000401",
    0x01000008: "e5fe1601000008fd",
    0x01000009: "e5fe1601000009fc",
    0x20000003: "e5fe1620000003e3",
    0x20000008: "e5fe1620000008de",
    0x20000009: "e5fe1620000009dd",
    0x10000010: "e5fe1610000010e6",
    0x10000011: "e5fe1610000011e5",
    0x10000012: "e5fe1610000012e4",
    0x10000013: "e5fe1610000013e3",
    0x11000010: "e5fe1611000010e5",
    0x11000011: "e5fe1611000011e4",
    0x11000012: "e5fe1611000012e3",
    0x11000013: "e5fe1611000013e2",
    0x10000020: "e5fe1610000020d6",
    0x10000021: "e5fe1610000021d5",
    0x10000022: "e5fe1610000022d4",
    0x10000023: "e5fe1610000023d3",
    0x10000030: "e5fe1610000030c6",
    0x10000031: "e5fe1610000031c5",
    0x10000032: "e5fe1610000032c4",
    0x31000001: "e5fe1631000001d4",
    0x31000000: "e5fe1631000000d5",
}


class Char:
    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid, self.properties = uuid, properties
        self.handle = id(self) & 0xFFFF
        self.descriptors: list[object] = []


def services(*chars: Char) -> list[SimpleNamespace]:
    # Deliberately not FFE5/FFE0: the artifact scans roles across all parents.
    return [SimpleNamespace(uuid="unrelated-parent", characteristics=list(chars))]


def entry(hass: HomeAssistant, layout: str) -> MockConfigEntry:
    e = MockConfigEntry(
        domain=DOMAIN,
        title="Comfort Enhancements",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Comfort Enhancements",
            CONF_BED_TYPE: BED_TYPE_COMFORT_ENHANCEMENTS,
            CONF_PROTOCOL_VARIANT: layout,
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    e.add_to_hass(hass)
    return e


async def controller(
    hass: HomeAssistant, client: MagicMock, layout: str = "mc2"
) -> ComfortEnhancementsController:
    client.services = services(
        Char(KEESON_BASE_WRITE_CHAR_UUID, ["write"]), Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    c = AdjustableBedCoordinator(hass, entry(hass, layout))
    await c.async_connect()
    assert isinstance(c.controller, ComfortEnhancementsController)
    client.write_gatt_char.reset_mock()
    return c.controller


def written(client: MagicMock) -> list[str]:
    return [bytes(c.args[1]).hex() for c in client.write_gatt_char.call_args_list]


@pytest.fixture(autouse=True)
def no_protocol_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.comfort_enhancements.RELEASE_DELAY_S", 0
    )
    monkeypatch.setattr(ComfortEnhancementsController, "_delay", AsyncMock())


def test_all_static_and_dynamic_builder_vectors() -> None:
    assert {word: control_frame(word).hex() for word in VECTORS} == VECTORS
    assert clock_frame(datetime(2026, 11, 1)).hex() == "e2fe160000000009"
    assert clock_frame(datetime(2026, 10, 31, 23, 58, 59)).hex() == "e2fe163b3a170677"
    cases = [
        (
            datetime(2026, 11, 3, 20, 15, 30),
            True,
            6,
            45,
            True,
            0xF8,
            "ebfe161e0f142d0602041133f84a",
        ),
        (datetime(2026, 11, 1), True, 0, 0, False, 0xF9, "ebfe16000000000000010000f906"),
        (
            datetime(2026, 10, 31, 23, 59, 59),
            True,
            23,
            59,
            True,
            0xF3,
            "ebfe163b3b173b1706401133f3a4",
        ),
        (datetime(2026, 11, 2, 3, 2, 1), True, 6, 9, False, 0xFF, "ebfe16010203090601020000ffe9"),
        (
            datetime(2026, 11, 3, 20, 15, 30),
            False,
            0,
            0,
            False,
            0xFF,
            "ebfe161e0f14ffff02ffffffffc3",
        ),
        (
            datetime(2026, 10, 31, 23, 59, 59),
            False,
            0,
            0,
            False,
            0xFF,
            "ebfe163b3b17ffff06ffffffff73",
        ),
    ]
    for now, enabled, hour, minute, massage, memory, expected in cases:
        assert (
            alarm_frame(
                now, enabled=enabled, hour=hour, minute=minute, massage=massage, memory=memory
            ).hex()
            == expected
        )


@pytest.mark.parametrize(
    "layout,third,slots,massage",
    [
        ("mc2", "both", 2, True),
        ("mc3", "both", 2, False),
        ("mc4", "lumbar", 1, True),
        ("mc5", "bed_height", 1, True),
    ],
)
async def test_layout_and_every_movement(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch, layout, third, slots, massage
) -> None:
    c = await controller(hass, mock_bleak_client, layout)
    assert [s.key for s in c.motor_control_specs] == ["back", "legs", third]
    assert c.memory_slot_count == slots
    assert c.supports_massage == c.supports_lights == massage
    assert not c.supports_single_address_pairing
    c._coordinator._motor_pulse_count = 1
    for spec, up, down in zip(c.motor_control_specs, [1, 4, 0x10], [2, 8, 0x20], strict=True):
        assert spec.scheduler_resource == "*"
        for fn, word in [(spec.open_fn, up), (spec.close_fn, down)]:
            mock_bleak_client.write_gatt_char.reset_mock()
            await fn(c)
            assert written(mock_bleak_client) == [VECTORS[word], STOP]
    for slot in range(1, slots + 1):
        word = slot + 7 if slots == 2 else 3
        mock_bleak_client.write_gatt_char.reset_mock()
        await c.preset_memory(slot)
        await c.preset_memory(slot)
        await c.program_memory(slot)
        assert written(mock_bleak_client) == [
            VECTORS[0x01000000 + word],
            PRESET_STOP,
            VECTORS[0x20000000 + word],
        ]
    with pytest.raises(ValueError):
        await c.preset_memory(slots + 1)


async def test_hold_cadence_cancel_and_stop_classes(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch
) -> None:
    c = await controller(hass, mock_bleak_client)
    c._coordinator._motor_pulse_count = 3
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", sleep)
    await c.move_back_up()
    assert written(mock_bleak_client) == [VECTORS[1]] * 3 + [STOP]
    assert all(0 < call.args[0] <= 0.2 for call in sleep.await_args_list)
    mock_bleak_client.write_gatt_char.reset_mock()

    async def cancel(*args, **kwargs):
        c._coordinator.cancel_command.set()

    mock_bleak_client.write_gatt_char.side_effect = cancel
    await c.move_back_up()
    assert written(mock_bleak_client) == [VECTORS[1], STOP]
    mock_bleak_client.write_gatt_char.reset_mock()
    await c.stop_all()
    assert written(mock_bleak_client) == [STOP, PRESET_STOP]


async def test_task_cancellation_still_releases(
    hass, mock_coordinator_connected, mock_bleak_client
) -> None:
    c = await controller(hass, mock_bleak_client)
    entered = asyncio.Event()

    async def block(_char, data, **kwargs):
        if data.hex() != STOP:
            entered.set()
            await asyncio.Event().wait()

    mock_bleak_client.write_gatt_char.side_effect = block
    task = asyncio.create_task(c.move_back_up())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(mock_bleak_client)[-1] == STOP


async def test_gatt_last_matching_properties_notify_and_no_parser(
    hass, mock_coordinator_connected, mock_bleak_client
) -> None:
    c = await controller(hass, mock_bleak_client)
    first = Char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    last = Char(KEESON_BASE_WRITE_CHAR_UUID, ["write", "write-without-response"])
    notify = Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    mock_bleak_client.services = services(
        first, last, Char(KEESON_BASE_WRITE_CHAR_UUID, ["read"]), notify
    )
    await c.lights_on()
    assert mock_bleak_client.write_gatt_char.call_args.args[0] is last
    assert mock_bleak_client.write_gatt_char.call_args.kwargs["response"] is False
    await c.start_notify()
    assert mock_bleak_client.start_notify.call_args.args[0] is notify
    raw = MagicMock()
    c.set_raw_notify_callback(raw)
    for payload in [b"", b"\xe2\xfe\x16", bytes(range(20))]:
        c._notification(notify, bytearray(payload))
    assert raw.call_count == 3
    # Notifications have no parser; only the session's starting timer is published.
    assert c._coordinator.controller_state == {MASSAGE_TIMER_MINUTES: 0}
    await c.stop_notify()
    assert mock_bleak_client.stop_notify.call_args.args[0] is notify
    mock_bleak_client.services = services(Char(KEESON_BASE_WRITE_CHAR_UUID, ["read"]))
    with pytest.raises(ConnectionError):
        await c.lights_on()


async def test_all_preset_light_and_massage_sequences(
    hass, mock_coordinator_connected, mock_bleak_client
) -> None:
    c = await controller(hass, mock_bleak_client)
    await c.preset_zero_g()
    await c.preset_flat()
    await c.preset_tv()
    await c.controller_button_specs[0].press_fn(c)
    await c.lights_on()
    await c.lights_off()
    assert written(mock_bleak_client) == [
        VECTORS[w] for w in [0x01000001, 0x01000002, 0x01000003, 0x01000004, 0x31000001, 0x31000000]
    ]
    for zone, base in [("head", 0x10000010), ("foot", 0x11000010)]:
        mock_bleak_client.write_gatt_char.reset_mock()
        for _ in range(4):
            await c._zone_click(zone, cycle=True)
        expected = [VECTORS[0x10000030]] + [VECTORS[base + i] for i in [3, 2, 1, 0]]
        assert written(mock_bleak_client) == expected
    mock_bleak_client.write_gatt_char.reset_mock()
    await c.massage_mode_step()  # both off: head3 at +200, foot3 at +300, no wave
    for _ in range(4):
        await c.massage_mode_step()
    assert written(mock_bleak_client) == [
        VECTORS[w]
        for w in [
            0x10000030,
            0x10000013,
            0x11000013,
            0x10000021,
            0x10000022,
            0x10000023,
            0x10000020,
            0x11000010,
            0x10000010,
        ]
    ]
    mock_bleak_client.write_gatt_char.reset_mock()
    await c._timer_click()
    await c._timer_click()
    await c._timer_click()
    await c.massage_head_toggle()
    await c._timer_click()
    assert written(mock_bleak_client) == [
        VECTORS[w] for w in [0x10000030, 0x10000031, 0x10000032, 0x10000013, 0x10000010, 0x11000010]
    ]
    assert c._coordinator.controller_state[MASSAGE_TIMER_MINUTES] == 0
    c._coordinator.cancel_command.set()
    mock_bleak_client.write_gatt_char.reset_mock()
    await c.massage_mode_step()
    assert not written(mock_bleak_client)  # delayed actions cannot restart after STOP


def test_profile_requires_explicit_variant_and_owns_settings() -> None:
    assert not is_valid_variant_for_bed_type(BED_TYPE_COMFORT_ENHANCEMENTS, "auto")
    assert all(
        is_valid_variant_for_bed_type(BED_TYPE_COMFORT_ENHANCEMENTS, layout)
        for layout in COMFORT_ENHANCEMENTS_VARIANTS
    )
    assert {CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS, CONF_HAS_MASSAGE} <= hidden_generic_fields(
        BED_TYPE_COMFORT_ENHANCEMENTS, None
    )
    assert per_side_profile(BED_TYPE_COMFORT_ENHANCEMENTS, "mc2").variant_owned


@pytest.mark.parametrize("layout", COMFORT_ENHANCEMENTS_VARIANTS)
async def test_ha_entities_and_alarm_service(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    monkeypatch,
    layout,
) -> None:
    mock_bleak_client.services = services(
        Char(KEESON_BASE_WRITE_CHAR_UUID, ["write"]), Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    e = entry(hass, layout)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def exists(platform, key):
        return registry.async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}") is not None

    assert exists("button", "comfort_enhancements_quiet_sleep")
    assert exists("button", "program_memory_1")
    assert exists("button", "program_memory_2") == (layout in ("mc2", "mc3"))
    assert exists("button", "comfort_enhancements_head_cycle") == (layout != "mc3")
    assert exists("switch", "under_bed_lights") == (layout != "mc3")
    assert exists("select", "massage_timer") == (layout != "mc3")
    dev = next(x.device_id for x in registry.entities.values() if x.config_entry_id == e.entry_id)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.comfort_enhancements.dt_util.now",
        lambda: datetime(2026, 11, 3, 20, 15, 30),
    )
    mock_bleak_client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        DOMAIN,
        "comfort_enhancements_set_alarm",
        {"device_id": dev, "enabled": True, "time": "06:45:00", "memory": 1, "massage": True},
        blocking=True,
    )
    expected = (
        "ebfe161e0f142d0602041133f84a"
        if layout in ("mc2", "mc3")
        else "ebfe161e0f142d0602041133f34f"
    )
    assert written(mock_bleak_client) == [expected]
    await hass.services.async_call(DOMAIN, "sync_clock", {"device_id": dev}, blocking=True)
    assert written(mock_bleak_client)[-1] == clock_frame(datetime(2026, 11, 3, 20, 15, 30)).hex()
    await hass.services.async_call(
        DOMAIN,
        "comfort_enhancements_set_alarm",
        {"device_id": dev, "enabled": False},
        blocking=True,
    )
    assert written(mock_bleak_client)[-1] == "ebfe161e0f14ffff02ffffffffc3"
    for bad in [{"enabled": True}, {"enabled": True, "time": "06:00:01"}] + (
        [{"enabled": True, "time": "06:00:00", "memory": 2}] if layout in ("mc4", "mc5") else []
    ):
        mock_bleak_client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "comfort_enhancements_set_alarm", {"device_id": dev, **bad}, blocking=True
            )
        assert not written(mock_bleak_client)
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_normal_release_uses_100ms_wait_and_cleanup_errors_surface(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch
) -> None:
    c = await controller(hass, mock_bleak_client)
    from custom_components.adjustable_bed.beds import comfort_enhancements as module

    original_timeout = asyncio.timeout
    waits: list[float] = []

    def no_wait(seconds):
        waits.append(seconds)
        return original_timeout(0)

    monkeypatch.setattr(module, "RELEASE_DELAY_S", 0.1)
    monkeypatch.setattr(module.asyncio, "timeout", no_wait)
    await c._release(delay=True)
    assert waits == [0.1]
    assert written(mock_bleak_client) == [STOP]
    mock_bleak_client.write_gatt_char.side_effect = ConnectionError("lost link")
    with pytest.raises(ConnectionError, match="lost link"):
        await c.move_back_up()


async def test_factory_rejects_absent_or_automatic_layout(hass) -> None:
    c = AdjustableBedCoordinator(hass, entry(hass, "mc2"))
    for layout in [None, "auto", "mc6"]:
        with pytest.raises(ValueError, match="Choose a Comfort Enhancements"):
            await create_controller(c, BED_TYPE_COMFORT_ENHANCEMENTS, layout, None)


@pytest.mark.parametrize("wave", [False, True])
async def test_massage_shutdown_finishes_before_preempting_preset(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch, wave
) -> None:
    c = await controller(hass, mock_bleak_client)
    await c.massage_mode_step()
    if wave:
        for _ in range(3):
            await c.massage_mode_step()
    mock_bleak_client.write_gatt_char.reset_mock()
    entered = asyncio.Event()

    async def block_until_preempted(seconds):
        entered.set()
        await c._coordinator.cancel_command.wait()

    monkeypatch.setattr(c, "_delay", block_until_preempted)
    off = asyncio.create_task(
        c._coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.massage_mode_step() if wave else ctrl.massage_off()
        )
    )
    await entered.wait()
    await c._coordinator.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
    await off
    words = [0x10000020, 0x11000010, 0x10000010] if wave else [0x10000010, 0x11000010]
    assert written(mock_bleak_client) == [VECTORS[w] for w in [*words, 0x01000002]]
    state = c._coordinator.controller_state
    assert state[MASSAGE_TIMER_MINUTES] == 0
    assert massage_levels(state, "head", "foot") == {"head": 0, "foot": 0}


async def test_last_zone_off_restarts_timer_on_next_zone(
    hass, mock_coordinator_connected, mock_bleak_client
) -> None:
    c = await controller(hass, mock_bleak_client)
    await c.massage_head_toggle()
    assert c._coordinator.controller_state[MASSAGE_TIMER_MINUTES] == 10
    await c.massage_head_toggle()
    assert c._coordinator.controller_state[MASSAGE_TIMER_MINUTES] == 0
    mock_bleak_client.write_gatt_char.reset_mock()
    await c.massage_foot_toggle()
    assert written(mock_bleak_client) == [VECTORS[0x10000030], VECTORS[0x11000013]]


async def test_new_entries_keep_connection_state_and_layout_change_retires_actions(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
) -> None:
    from custom_components.adjustable_bed.bed_traits import disconnect_after_command_default_enabled

    assert not disconnect_after_command_default_enabled(BED_TYPE_COMFORT_ENHANCEMENTS, "mc2")
    mock_bleak_client.services = services(
        Char(KEESON_BASE_WRITE_CHAR_UUID, ["write"]), Char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    e = entry(hass, "mc2")
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for layout in ["mc2", "mc3", "mc5"]:
        if layout != "mc2":
            hass.config_entries.async_update_entry(
                e, data={**e.data, CONF_PROTOCOL_VARIANT: layout}
            )
            assert await hass.config_entries.async_reload(e.entry_id)
            await hass.async_block_till_done()
        for key in ["head_cycle", "foot_cycle", "timer_cycle"]:
            assert bool(
                registry.async_get_entity_id(
                    "button", DOMAIN, f"{ADDRESS}_comfort_enhancements_{key}"
                )
            ) == (layout != "mc3")
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("layout", [*COMFORT_ENHANCEMENTS_VARIANTS, None, "auto"])
async def test_offline_capabilities_require_the_saved_layout(hass, layout) -> None:
    e = entry(hass, layout)
    c = AdjustableBedCoordinator(hass, e)
    await c.async_prime_offline_controller()
    if layout in COMFORT_ENHANCEMENTS_VARIANTS:
        assert isinstance(c.capability_controller, ComfortEnhancementsController)
        assert c.capability_controller.layout == layout
        assert len(c.capability_controller.motor_control_specs) == 3
    else:
        assert c.capability_controller is None
    assert c.client is None
    assert c.controller is None
