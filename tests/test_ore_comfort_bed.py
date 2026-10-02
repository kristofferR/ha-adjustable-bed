"""MaxCoil Una / Dynasty Bases app profile (com.ore.okincomfortbed code base).

Every frame literal is a test vector from the accepted clean-room reports
(row056, cluster-013); none comes from captured traffic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import KeesonController
from custom_components.adjustable_bed.beds.ore_comfort_bed import (
    STATE_LEVEL,
    STATE_TIMER,
    OreComfortBedController,
    build_frame,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_MAXCOIL_UNA,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

APPS = (KEESON_VARIANT_MAXCOIL_UNA, KEESON_VARIANT_DYNASTY_BASES)
ADDRESS = "AA:BB:CC:DD:05:60"
STOP_FRAME = "e5fe160000000006"
STORE_KEY = f"{DOMAIN}.app_state_{ADDRESS.replace(':', '_').lower()}"
SLOT = "keeson:maxcoil_una"

# The 34 unique payload vectors both reports publish (word -> final bytes).
REPORT_VECTORS = {
    0x00000000: "e5fe160000000006",
    0x00000001: "e5fe160000000105",
    0x00000002: "e5fe160000000204",
    0x00000004: "e5fe160000000402",
    0x00000008: "e5fe1600000008fe",
    0x00000010: "e5fe1600000010f6",
    0x00000020: "e5fe1600000020e6",
    0x00000040: "e5fe1600000040c6",
    0x00000080: "e5fe160000008086",
    0x01000001: "e5fe160100000104",
    0x01000002: "e5fe160100000203",
    0x01000008: "e5fe1601000008fd",
    0x01000009: "e5fe1601000009fc",
    0x20000001: "e5fe1620000001e5",
    0x20000002: "e5fe1620000002e4",
    0x20000008: "e5fe1620000008de",
    0x20000009: "e5fe1620000009dd",
    0x31000000: "e5fe1631000000d5",
    0x31000001: "e5fe1631000001d4",
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
}

# Command rows C01-C20: (motor count, cover key, up frame, down frame).
MOVEMENT_ROWS = [
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
]

Action = Callable[[OreComfortBedController], Awaitable[None]]

# Command rows C21-C31 and C37-C39, plus every slider level of C32-C34.
SINGLE_ROWS: list[tuple[str, Action, list[str]]] = [
    ("stop", lambda c: c.stop_all(), [STOP_FRAME]),
    ("zg_recall", lambda c: c.preset_zero_g(), ["e5fe160100000104"]),
    ("zg_save", lambda c: c.program_zero_g(), ["e5fe1620000001e5"]),
    ("flat_recall", lambda c: c.preset_flat(), ["e5fe160100000203"]),
    ("flat_save", lambda c: c.program_flat(), ["e5fe1620000002e4"]),
    ("a_recall", lambda c: c.preset_memory(1), ["e5fe1601000008fd"]),
    ("a_save", lambda c: c.program_memory(1), ["e5fe1620000008de"]),
    ("b_recall", lambda c: c.preset_memory(2), ["e5fe1601000009fc"]),
    ("b_save", lambda c: c.program_memory(2), ["e5fe1620000009dd"]),
    ("light_on", lambda c: c.lights_on(), ["e5fe1631000001d4"]),
    ("light_off", lambda c: c.lights_off(), ["e5fe1631000000d5"]),
    ("timer_10", lambda c: c.set_massage_timer_option("10"), ["e5fe1610000030c6"]),
    ("timer_20", lambda c: c.set_massage_timer_option("20"), ["e5fe1610000031c5"]),
    ("timer_30", lambda c: c.set_massage_timer_option("30"), ["e5fe1610000032c4"]),
    ("massage_stop", lambda c: c.massage_off(), ["e5fe1610000010e6", "e5fe1611000010e5"]),
    *(
        (f"{zone}_{level}", lambda c, z=zone, q=level: c.set_massage_level(z, q), [frame])
        for zone, frames in (
            ("wave", ("e5fe1610000020d6", "e5fe1610000021d5", "e5fe1610000022d4", "e5fe1610000023d3")),
            ("head", ("e5fe1610000010e6", "e5fe1610000011e5", "e5fe1610000012e4", "e5fe1610000013e3")),
            ("foot", ("e5fe1611000010e5", "e5fe1611000011e4", "e5fe1611000012e3", "e5fe1611000013e2")),
        )
        for level, frame in enumerate(frames)
    ),
]


class _Char:
    """A hashable stand-in for a discovered BleakGATTCharacteristic."""

    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid = uuid
        self.properties = properties
        self.handle = id(self) & 0xFFFF
        self.descriptors: list[object] = []


def _char(uuid: str, properties: list[str]) -> _Char:
    return _Char(uuid, properties)


def _services(*chars: _Char) -> list[SimpleNamespace]:
    return [SimpleNamespace(uuid="0000ffe5-0000-1000-8000-00805f9b34fb", characteristics=list(chars))]


def _entry(
    hass: HomeAssistant, variant: str, motor_count: int, address: str = ADDRESS
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ORE bed",
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "ORE bed",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: motor_count,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=address,
        entry_id=f"ore_{variant}_{motor_count}_{address}",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Record every wait (hold repeats and single-send delays) instead of sleeping."""
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.ore_comfort_bed.asyncio.sleep", sleep)
    return sleep


def _waits(sleep: AsyncMock) -> list[float]:
    # Zero-length yields come from unrelated event-loop plumbing.
    return [c.args[0] for c in sleep.await_args_list if c.args[0]]


async def _controller(
    hass: HomeAssistant, client: MagicMock, variant: str = KEESON_VARIANT_MAXCOIL_UNA, motor_count: int = 2
) -> OreComfortBedController:
    client.services = _services(
        _char(KEESON_BASE_WRITE_CHAR_UUID, ["write", "write-without-response"]),
        _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"]),
    )
    coordinator = AdjustableBedCoordinator(hass, _entry(hass, variant, motor_count))
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, OreComfortBedController)
    client.write_gatt_char.reset_mock()
    return controller


def _written(client: MagicMock) -> list[str]:
    return [bytes(c.args[1]).hex() for c in client.write_gatt_char.call_args_list]


def test_builder_reproduces_every_report_vector() -> None:
    for word, frame in REPORT_VECTORS.items():
        assert build_frame(word).hex() == frame
        assert sum(build_frame(word)) & 0xFF == 0xFF
    # Java long shifts then byte casts keep only the low 32 bits.
    assert build_frame(0x1_0000_0001).hex() == "e5fe160000000105"


@pytest.mark.parametrize("variant", APPS)
@pytest.mark.parametrize(("motor_count", "keys"), [
    (2, ["back", "feet", "both"]),
    (3, ["back", "feet", "head"]),
    (4, ["back", "feet", "waist", "lumbar"]),
])
async def test_motor_count_selects_the_app_screen(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    variant: str, motor_count: int, keys: list[str],
) -> None:
    controller = await _controller(hass, mock_bleak_client, variant, motor_count)
    specs = controller.motor_control_specs
    assert [s.key for s in specs] == keys
    assert [s.translation_key for s in specs] == keys
    # One global key and zero release: every STOP preempts every axis.
    assert {s.scheduler_resource for s in specs} == {"*"}
    assert controller.has_lumbar_support is (motor_count == 4)


@pytest.mark.parametrize(("motor_count", "key", "up", "down"), MOVEMENT_ROWS)
async def test_hold_repeats_every_100ms_then_releases_with_zero(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, motor_count: int, key: str, up: str, down: str,
) -> None:
    controller = await _controller(hass, mock_bleak_client, motor_count=motor_count)
    spec = next(s for s in controller.motor_control_specs if s.key == key)
    for action, frame in ((spec.open_fn, up), (spec.close_fn, down)):
        mock_bleak_client.write_gatt_char.reset_mock()
        sleeps.reset_mock()
        await action(controller)
        count = controller._coordinator.motor_pulse_count
        assert _written(mock_bleak_client) == [frame] * count + [STOP_FRAME]
        # 100 ms after each held write, then buttonUp's 100 ms before the zero word.
        assert _waits(sleeps) == [0.1] * count


async def test_release_is_sent_even_when_the_hold_was_cancelled(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    controller._coordinator.cancel_command.set()
    try:
        await controller.move_back_up()
    finally:
        controller._coordinator.cancel_command.clear()
    assert _written(mock_bleak_client) == [STOP_FRAME]


@pytest.mark.parametrize("motor_count", [2, 4])
async def test_head_exists_only_on_the_three_motor_screen(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock, motor_count: int,
) -> None:
    controller = await _controller(hass, mock_bleak_client, motor_count=motor_count)
    with pytest.raises(NotImplementedError):
        await controller.move_head_up()
    assert _written(mock_bleak_client) == []


@pytest.mark.parametrize(("name", "action", "frames"), SINGLE_ROWS, ids=[r[0] for r in SINGLE_ROWS])
async def test_single_actions_wait_100ms_then_write_the_app_frame_once(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, name: str, action: Action, frames: list[str],
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    await action(controller)
    assert _written(mock_bleak_client) == frames
    assert _waits(sleeps) == [0.1] * len(frames)
    # Last FFE9 instance, with Android's default write type for a dual-mode characteristic.
    for call in mock_bleak_client.write_gatt_char.call_args_list:
        assert call.args[0].uuid == KEESON_BASE_WRITE_CHAR_UUID
        assert call.kwargs["response"] is False


@pytest.mark.parametrize(("levels", "frames"), [
    # START-1..3: (wave, head, foot) slider progress (10,10,10), (39,0,25), (0,39,1).
    ((1, 1, 1), ["e5fe1610000021d5", "e5fe1610000011e5", "e5fe1611000011e4"]),
    ((3, 0, 2), ["e5fe1610000023d3", "e5fe1610000010e6", "e5fe1611000012e3"]),
    ((0, 3, 0), ["e5fe1610000020d6", "e5fe1610000013e3", "e5fe1611000010e5"]),
])
async def test_start_sends_current_wave_head_foot_levels(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, levels: tuple[int, int, int], frames: list[str],
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    controller.restore_persisted_app_state(dict(zip(("wave", "head", "foot"), levels, strict=True)))
    await controller.massage_start()
    assert _written(mock_bleak_client) == frames
    assert _waits(sleeps) == [0.1, 0.1, 0.1]


async def test_massage_levels_timer_and_stop_publish_app_state(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    state = controller._coordinator.controller_state
    # A fresh install restores slider progress 10, i.e. level 1, for every zone.
    assert {state[STATE_LEVEL[z]] for z in ("wave", "head", "foot")} == {1}
    await controller.set_massage_level("head", 3)
    await controller.set_massage_timer_option("20")
    assert state[STATE_LEVEL["head"]] == 3
    assert state[STATE_TIMER] == "20"
    # Stop zeroes head and foot on the bed only; the sliders keep their levels.
    await controller.massage_off()
    assert state[STATE_TIMER] is None
    assert state[STATE_LEVEL["head"]] == 3
    assert controller.persisted_app_state == {"wave": 1, "head": 3, "foot": 1}
    with pytest.raises(ValueError):
        await controller.set_massage_level("head", 4)
    with pytest.raises(ValueError):
        controller.restore_persisted_app_state({"head": 7})


async def test_write_roles_follow_the_app_scan(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock,
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    first = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write-without-response"])
    last = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    notify = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    mock_bleak_client.services = [
        SimpleNamespace(uuid="0000ffe0-0000-1000-8000-00805f9b34fb", characteristics=[first, notify]),
        SimpleNamespace(uuid="0000abcd-0000-1000-8000-00805f9b34fb", characteristics=[last]),
    ]
    controller._write_char = None
    await controller.preset_flat()
    call = mock_bleak_client.write_gatt_char.call_args
    # Any service, last match wins; write-only characteristics write with response.
    assert call.args[0] is last
    assert call.kwargs["response"] is True

    # Controls stay unavailable unless FFE4 exists too.
    mock_bleak_client.services = _services(last)
    controller._write_char = None
    with pytest.raises(HomeAssistantError):
        await controller.preset_flat()


async def test_notifications_are_never_subscribed(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    mock_bleak_client.start_notify.reset_mock()
    await controller.start_notify(lambda _key, _value: None)
    # The app enables FFE4 locally only: no CCCD write, and it discards replies.
    mock_bleak_client.start_notify.assert_not_called()


@pytest.mark.parametrize("variant", APPS)
async def test_profile_is_explicit_and_auto_keeps_keeson(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock, variant: str,
) -> None:
    controller = await _controller(hass, mock_bleak_client, variant)
    assert controller.protocol_diagnostics["layout"] == "bedding2 (2M)"
    # The app has no name or service rule, so Auto keeps the generic Keeson path.
    mock_bleak_client.services = None
    auto = await create_controller(
        coordinator=controller._coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant=VARIANT_AUTO,
        client=mock_bleak_client,
        device_name="ORE-ac2170000d",
    )
    assert isinstance(auto, KeesonController)


async def test_slider_levels_persist_across_restarts(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, hass_storage: dict,
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    await controller.set_massage_level("wave", 0)
    await controller.set_massage_level("foot", 2)
    coordinator = controller._coordinator
    await coordinator.async_shutdown()
    assert hass_storage[STORE_KEY]["data"] == {SLOT: {"wave": 0, "head": 1, "foot": 2}}

    restarted = AdjustableBedCoordinator(hass, coordinator.entry)
    await restarted.async_connect()
    assert restarted.controller.persisted_app_state == {"wave": 0, "head": 1, "foot": 2}
    assert restarted.controller_state[STATE_LEVEL["foot"]] == 2


async def test_slider_levels_survive_a_reconnect(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, hass_storage: dict,
) -> None:
    controller = await _controller(hass, mock_bleak_client)
    await controller.set_massage_level("head", 3)
    coordinator = controller._coordinator
    await coordinator.async_disconnect()
    await coordinator.async_connect()
    rebuilt = coordinator.controller
    assert rebuilt is not controller
    assert rebuilt.persisted_app_state == {"wave": 1, "head": 3, "foot": 1}
    await rebuilt.massage_start()
    assert _written(mock_bleak_client)[-2] == "e5fe1610000013e3"


async def test_invalid_stored_levels_fall_back_to_the_app_default(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    hass_storage: dict,
) -> None:
    hass_storage[STORE_KEY] = {"version": 1, "key": STORE_KEY, "data": {SLOT: {"head": 9, "foot": "x"}}}
    controller = await _controller(hass, mock_bleak_client)
    assert controller.persisted_app_state == {"wave": 1, "head": 1, "foot": 1}
    assert controller._coordinator.controller_state[STATE_LEVEL["head"]] == 1


async def test_removing_the_entry_deletes_its_stored_levels(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, hass_storage: dict, enable_custom_integrations,
) -> None:
    mock_bleak_client.services = _services(
        _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"]), _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    entry = _entry(hass, KEESON_VARIANT_MAXCOIL_UNA, 2)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_connect()
    await coordinator.controller.set_massage_level("wave", 3)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass_storage[STORE_KEY]["data"][SLOT]["wave"] == 3

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert STORE_KEY not in hass_storage

    # Re-adding the bed starts from the app's first-run levels.
    readded = AdjustableBedCoordinator(hass, _entry(hass, KEESON_VARIANT_MAXCOIL_UNA, 2))
    await readded.async_connect()
    assert readded.controller.persisted_app_state == {"wave": 1, "head": 1, "foot": 1}


async def test_removal_keeps_levels_another_entry_still_owns(
    hass: HomeAssistant, hass_storage: dict, enable_custom_integrations,
) -> None:
    hass_storage[STORE_KEY] = {"version": 1, "key": STORE_KEY, "data": {SLOT: {"wave": 3, "head": 1, "foot": 1}}}
    first = _entry(hass, KEESON_VARIANT_MAXCOIL_UNA, 2)
    duplicate = _entry(hass, KEESON_VARIANT_DYNASTY_BASES, 2, ADDRESS.lower())

    assert await hass.config_entries.async_remove(first.entry_id)
    await hass.async_block_till_done()
    assert hass_storage[STORE_KEY]["data"][SLOT]["wave"] == 3

    assert await hass.config_entries.async_remove(duplicate.entry_id)
    await hass.async_block_till_done()
    assert STORE_KEY not in hass_storage


async def test_profiles_sharing_an_address_keep_separate_slots(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    sleeps: AsyncMock, hass_storage: dict,
) -> None:
    maxcoil = await _controller(hass, mock_bleak_client, KEESON_VARIANT_MAXCOIL_UNA)
    dynasty_coordinator = AdjustableBedCoordinator(
        hass, _entry(hass, KEESON_VARIANT_DYNASTY_BASES, 2, ADDRESS.lower())
    )
    await dynasty_coordinator.async_connect()
    dynasty = dynasty_coordinator.controller
    assert isinstance(dynasty, OreComfortBedController)

    await maxcoil.set_massage_level("head", 3)
    await dynasty.set_massage_level("foot", 0)
    await maxcoil._coordinator.async_shutdown()
    await dynasty_coordinator.async_shutdown()

    assert hass_storage[STORE_KEY]["data"] == {
        "keeson:maxcoil_una": {"wave": 1, "head": 3, "foot": 1},
        "keeson:dynasty_bases": {"wave": 1, "head": 1, "foot": 0},
    }


async def test_a_removed_store_ignores_later_saves(hass: HomeAssistant, hass_storage: dict) -> None:
    from custom_components.adjustable_bed.app_state_store import (
        app_state_store,
        async_remove_app_states,
    )

    store = app_state_store(hass, ADDRESS)
    assert await store.async_slot(SLOT) == {}
    store.update(SLOT, {"wave": 2})
    await async_remove_app_states(hass, [ADDRESS])
    store.update(SLOT, {"wave": 3})
    await store.async_save()
    await hass.async_block_till_done()
    assert STORE_KEY not in hass_storage


async def test_failed_store_deletion_does_not_block_entry_removal(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, enable_custom_integrations,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from custom_components.adjustable_bed import app_state_store

    monkeypatch.setattr(app_state_store, "async_remove_app_states", AsyncMock(side_effect=OSError("busy")))
    entry = _entry(hass, KEESON_VARIANT_MAXCOIL_UNA, 2)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    assert "Could not delete stored app preferences" in caplog.text


async def test_setup_exposes_the_app_surface(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    enable_custom_integrations,
) -> None:
    from homeassistant.helpers import entity_registry as er

    mock_bleak_client.services = _services(
        _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"]), _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    )
    entry = _entry(hass, KEESON_VARIANT_DYNASTY_BASES, 4)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def exists(platform: str, key: str) -> bool:
        return registry.async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}") is not None

    for key in ("back", "feet", "waist", "lumbar"):
        assert exists("cover", key), key
    for key in ("head", "both", "tilt"):
        assert not exists("cover", key), key
    for key in (
        "preset_flat", "preset_zero_g", "preset_memory_1", "preset_memory_2",
        "program_memory_1", "program_memory_2", "massage_all_off", "stop",
        "ore_comfort_program_flat", "ore_comfort_program_zero_g", "ore_comfort_massage_start",
    ):
        assert exists("button", key), key
    for key in (
        "preset_anti_snore", "preset_tv", "preset_lounge", "preset_memory_3", "toggle_light",
        "massage_all_toggle", "massage_head_up", "massage_mode_step",
    ):
        assert not exists("button", key), key
    for zone in ("head", "foot", "wave"):
        assert exists("number", f"controller_number_ore_comfort_massage_{zone}"), zone
    assert exists("select", f"controller_select_{STATE_TIMER}")
    assert exists("switch", "under_bed_lights")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_switching_profiles_retires_the_other_profiles_entities(
    hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock,
    enable_custom_integrations,
) -> None:
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import KEESON_VARIANT_SINO

    mock_bleak_client.services = None
    entry = _entry(hass, KEESON_VARIANT_SINO, 4)
    registry = er.async_get(hass)

    def exists(platform: str, key: str) -> bool:
        return registry.async_get_entity_id(platform, DOMAIN, f"{ADDRESS}_{key}") is not None

    async def switch(variant: str) -> None:
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_PROTOCOL_VARIANT: variant})
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert exists("cover", "tilt")

    await switch(KEESON_VARIANT_DYNASTY_BASES)
    assert not exists("cover", "tilt")
    assert exists("cover", "waist")
    assert exists("button", "ore_comfort_massage_start")

    await switch(KEESON_VARIANT_SINO)
    for platform, key in (
        ("cover", "waist"),
        ("cover", "back"),
        ("button", "ore_comfort_massage_start"),
        ("button", "ore_comfort_program_flat"),
        ("number", "controller_number_ore_comfort_massage_head"),
        ("select", f"controller_select_{STATE_TIMER}"),
    ):
        assert not exists(platform, key), key
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def test_two_address_pairs_refuse_a_shared_profile_change() -> None:
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.config_flow import _PER_SIDE_APP_PROFILES

    assert {_PER_SIDE_APP_PROFILES[v] for v in APPS} == {"ore_comfort_unpair_first"}
    strings = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
    )
    assert "ore_comfort_unpair_first" in strings["options"]["error"]
