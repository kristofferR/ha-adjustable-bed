"""Simon Li, Heal Every Night and OKIN-Seating app profiles, row060.

Every frame literal comes from the accepted clean-room reports for
com.okin.simon 1.0.1 (2), com.okin.healeverynight 1.0 (1) and
com.okin.minghua.R 1.0.1 (2) (test vectors and variant inventory), not from
captured traffic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import KeesonController
from custom_components.adjustable_bed.beds.keeson_okin_apps import (
    OkinAppKeesonController,
    heal_movement_key,
    java_uuid_order,
    okin_app_frame,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_OKIN_APP_SETTINGS,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_SIMON_LI,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

Action = Callable[[OkinAppKeesonController], Awaitable[None]]
ZERO = "e5fe160000000006"
HOLD = 10  # The apps refresh every 100 ms; the default burst is 10 x 100 ms.

# Simon Li report V01-V12 (action, frame); every control is a held stream.
SIMON_VECTORS: list[tuple[Action, str]] = [
    (lambda c: c.move_feet_up(), "e5fe160000000105"),  # V01 foot_up
    (lambda c: c.move_feet_down(), "e5fe160000000204"),  # V02 foot_down
    (lambda c: c.move_back_up(), "e5fe160000000402"),  # V03 back_head_up
    (lambda c: c.move_back_down(), "e5fe1600000008fe"),  # V04 back_head_down
    (lambda c: c.move_lumbar_up(), "e5fe1600000010f6"),  # V05 lumbar_up
    (lambda c: c.move_lumbar_down(), "e5fe1600000020e6"),  # V06 lumbar_down
    (lambda c: c.preset_home(), "e5fe1600000016f0"),  # V07 home
    (lambda c: c.preset_memory(1), "e5fe1600000040c6"),  # V08 memory1
    (lambda c: c.preset_memory(2), "e5fe160000008086"),  # V09 memory2
]
# OKIN-Seating report VEC01-VEC06.
SEATING_VECTORS: list[tuple[Action, str]] = [
    (lambda c: c.move_back_up(), "e5fe160000000402"),  # VEC01 back_up tag
    (lambda c: c.move_feet_down(), "e5fe160000000204"),  # VEC02 foot_down tag
    (lambda c: c.move_back_down(), "e5fe1600000008fe"),  # VEC03 union_down tag
    (lambda c: c.move_feet_up(), "e5fe160000000105"),  # VEC04 foot_up tag
    (lambda c: c.preset_home(), "e5fe160000000afc"),  # VEC05 HOME
]
# Heal Every Night report TV-* constants (key, final frame).
HEAL_CONSTANTS: dict[int, str] = {
    0x00000000: "e5fe160000000006",
    0x00000010: "e5fe1600000010f6",
    0x00000020: "e5fe1600000020e6",
    0x00000040: "e5fe1600000040c6",
    0x00000080: "e5fe160000008086",
    0x00000004: "e5fe160000000402",
    0x00000008: "e5fe1600000008fe",
    0x00000001: "e5fe160000000105",
    0x00000002: "e5fe160000000204",
    0x01000000: "e5fe160100000005",
    0x01000001: "e5fe160100000104",
    0x01000002: "e5fe160100000203",
    0x20000008: "e5fe1620000008de",
    0x01000008: "e5fe1601000008fd",
    0x20000009: "e5fe1620000009dd",
    0x01000009: "e5fe1601000009fc",
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
    0x31000001: "e5fe1631000001d4",
    0x31000000: "e5fe1631000000d5",
}
# Heal Every Night variant inventory (MCn-Ii-Aa-Bb): head_up, head_down, foot_up, foot_down.
HEAL_MOVEMENT: dict[tuple[bool, bool, bool], tuple[str, str, str, str]] = {
    (False, False, False): (
        "e5fe160000000105",
        "e5fe160000000204",
        "e5fe160000000402",
        "e5fe1600000008fe",
    ),
    (False, False, True): (
        "e5fe160000000105",
        "e5fe160000000204",
        "e5fe1600000008fe",
        "e5fe160000000402",
    ),
    (False, True, False): (
        "e5fe160000000204",
        "e5fe160000000105",
        "e5fe160000000402",
        "e5fe1600000008fe",
    ),
    (False, True, True): (
        "e5fe160000000204",
        "e5fe160000000105",
        "e5fe1600000008fe",
        "e5fe160000000402",
    ),
    (True, False, False): (
        "e5fe160000000402",
        "e5fe1600000008fe",
        "e5fe160000000105",
        "e5fe160000000204",
    ),
    (True, False, True): (
        "e5fe1600000008fe",
        "e5fe160000000402",
        "e5fe160000000105",
        "e5fe160000000204",
    ),
    (True, True, False): (
        "e5fe160000000402",
        "e5fe1600000008fe",
        "e5fe160000000204",
        "e5fe160000000105",
    ),
    (True, True, True): (
        "e5fe1600000008fe",
        "e5fe160000000402",
        "e5fe160000000204",
        "e5fe160000000105",
    ),
}
# Heal timer sequence vectors: TV-timer10-initial and TV-timer10-changed-off-zone.
TIMER_INITIAL = ["e5fe1610000030c6", "e5fe1610000020d6", "e5fe1610000011e5", "e5fe1611000011e4"]
HEAL_STOP = ["e5fe1610000010e6", "e5fe1611000010e5"]


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin seat",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:60",
            CONF_NAME: "Okin seat",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:60",
        entry_id="okin_app_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, mock_coordinator_connected
) -> AdjustableBedCoordinator:
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    return coordinator


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", sleep)
    return sleep


def _ctrl(
    coordinator: AdjustableBedCoordinator, variant: str, motors: int = 2
) -> OkinAppKeesonController:
    coordinator._motor_count = motors
    return OkinAppKeesonController(coordinator, variant=variant)


def _written(client: MagicMock) -> list[str]:
    return [c.args[1].hex() for c in client.write_gatt_char.await_args_list]


_HANDLES = iter(range(0x10, 0x1000))


@dataclass(eq=False)
class _Char:
    """A discovered characteristic; identity-hashed like Bleak's."""

    uuid: str
    properties: list[str]
    handle: int = field(default_factory=lambda: next(_HANDLES))


def _char(uuid: str, props: list[str]) -> _Char:
    return _Char(uuid, props)


def _service(uuid: str, *chars: _Char) -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid, characteristics=list(chars))


def test_builder_matches_the_report_vectors():
    # Simon V13-V16 and OKIN-Seating VEC07-VEC09: big-endian low 32 bits.
    assert okin_app_frame(0x01020304).hex() == "e5fe1601020304fc"
    assert okin_app_frame(-1).hex() == "e5fe16ffffffff0a"
    assert okin_app_frame(4294967297).hex() == "e5fe160000000105"
    assert okin_app_frame(2164227840).hex() == "e5fe1680ff7f0008"
    assert okin_app_frame(305419896).hex() == "e5fe1612345678f2"
    assert okin_app_frame(4600387192).hex() == "e5fe1612345678f2"
    for key, frame in HEAL_CONSTANTS.items():
        assert okin_app_frame(key).hex() == frame
        assert sum(okin_app_frame(key)) % 256 == 0xFF


@pytest.mark.parametrize(("action", "frame"), SIMON_VECTORS)
async def test_simon_controls_stream_then_release(
    coordinator, mock_bleak_client: MagicMock, no_sleep, action, frame
):
    await action(_ctrl(coordinator, KEESON_VARIANT_SIMON_LI))
    assert _written(mock_bleak_client) == [frame] * HOLD + [ZERO]
    # 100 ms between writes, then the 10 ms sendSingleMessage sleep.
    assert no_sleep.await_args_list == [call(0.1)] * (HOLD - 1) + [call(0.01)]


@pytest.mark.parametrize(("action", "frame"), SEATING_VECTORS)
async def test_seating_controls_stream_then_release(
    coordinator, mock_bleak_client: MagicMock, no_sleep, action, frame
):
    await action(_ctrl(coordinator, KEESON_VARIANT_OKIN_SEATING))
    assert _written(mock_bleak_client) == [frame] * HOLD + [ZERO]


async def test_simon_memory_save_holds_the_memory_key_2100_ms(
    coordinator, mock_bleak_client: MagicMock, no_sleep, monkeypatch: pytest.MonkeyPatch
):
    """V10/V11: the same memory stream; the app shows "saved" after 2100 ms."""
    waits: list[float] = []

    async def fake_wait_for(awaitable: Any, timeout: float) -> None:
        awaitable.close()
        waits.append(timeout)
        raise TimeoutError

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.keeson_okin_apps.asyncio.wait_for", fake_wait_for
    )
    await _ctrl(coordinator, KEESON_VARIANT_SIMON_LI).program_memory(2)
    # Writes at 0..2000 ms, the hold lasts to 2100 ms, then the release.
    assert _written(mock_bleak_client) == ["e5fe160000008086"] * 21 + [ZERO]
    assert waits == [pytest.approx(0.1)]


async def test_hold_service_durations_and_validation(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _ctrl(coordinator, KEESON_VARIANT_OKIN_SEATING)
    assert controller.held_control_options == (
        "back_up",
        "back_down",
        "foot_up",
        "foot_down",
        "home",
    )
    await controller.hold_control("home", 250)
    assert _written(mock_bleak_client) == ["e5fe160000000afc"] * 3 + [ZERO]
    for bad in (99, 60001, True):
        with pytest.raises(ValueError):
            await controller.hold_control("home", bad)
    with pytest.raises(NotImplementedError):
        await controller.hold_control("lumbar_up", 500)
    with pytest.raises(NotImplementedError):
        await controller.preset_memory(1)


async def test_release_survives_a_stop_request(
    coordinator, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch
):
    """A stop ends the refresh, and the zero key still goes out on a fresh event."""
    controller = _ctrl(coordinator, KEESON_VARIANT_SIMON_LI)

    async def cancel(_delay: float) -> None:
        coordinator.cancel_command.set()

    monkeypatch.setattr("custom_components.adjustable_bed.beds.base.asyncio.sleep", cancel)
    await controller.move_lumbar_up()
    assert _written(mock_bleak_client) == ["e5fe1600000010f6", ZERO]


async def test_cancelled_release_skips_the_delay_but_still_writes_zero(
    coordinator, mock_bleak_client: MagicMock
):
    controller = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT)
    task = asyncio.create_task(controller._release_motion())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _written(mock_bleak_client) == [ZERO]


@pytest.mark.parametrize(("settings", "frames"), list(HEAL_MOVEMENT.items()))
async def test_heal_settings_remap_movement_like_the_app(
    coordinator, mock_bleak_client: MagicMock, no_sleep, settings, frames
):
    installation, actuator_1, actuator_2 = settings
    hass = coordinator.hass
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={
            **coordinator.entry.data,
            CONF_OKIN_APP_SETTINGS: {
                "installation": installation,
                "actuator_1": actuator_1,
                "actuator_2": actuator_2,
            },
        },
    )
    controller = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT, 3)
    for move, frame in zip(
        ("move_head_up", "move_head_down", "move_feet_up", "move_feet_down"), frames, strict=True
    ):
        mock_bleak_client.write_gatt_char.reset_mock()
        no_sleep.reset_mock()
        await getattr(controller, move)()
        assert _written(mock_bleak_client) == [frame] * HOLD + [ZERO]
        # The zero key follows 100 ms after the release.
        assert no_sleep.await_args_list[-1] == call(0.1)
    # Tilt and lumbar never change.
    assert (
        heal_movement_key(
            "tilt_up", installation=installation, actuator_1=actuator_1, actuator_2=actuator_2
        )
        == 0x10
    )
    assert (
        heal_movement_key(
            "lumbar_down", installation=installation, actuator_1=actuator_1, actuator_2=actuator_2
        )
        == 0x80
    )


async def test_heal_presets_retap_to_stop_and_save(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT)
    await controller.preset_flat()
    await controller.preset_flat()  # Re-tap of the selected preset: preset STOP.
    await controller.preset_zero_g()
    await controller.preset_memory(1)  # Selecting another preset deselects Zero G.
    await controller.program_memory(2)  # Save keeps the selection.
    await controller.preset_memory(1)
    await controller.preset_memory(2)
    assert _written(mock_bleak_client) == [
        "e5fe160100000203",
        "e5fe160100000005",
        "e5fe160100000104",
        "e5fe1601000008fd",
        "e5fe1620000009dd",
        "e5fe160100000005",
        "e5fe1601000009fc",
    ]
    # The selection survives a controller rebuild after a reconnect.
    mock_bleak_client.write_gatt_char.reset_mock()
    await _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT).stop_all()
    assert _written(mock_bleak_client) == [ZERO, "e5fe160100000005"]
    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.stop_all()
    assert _written(mock_bleak_client) == [ZERO]


async def test_heal_massage_page_follows_the_app_state_machine(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    controller = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT)
    # Sliders and +/- are disabled until a timer starts the page.
    with pytest.raises(ValueError):
        await controller.massage_head_up()
    with pytest.raises(ValueError):
        await controller.set_heal_massage_level("wave", 2)
    mock_bleak_client.write_gatt_char.assert_not_awaited()

    await controller.set_massage_timer(20)  # Every label sends timer1.
    assert _written(mock_bleak_client) == TIMER_INITIAL
    assert no_sleep.await_args_list == [call(0.1)] * 3
    assert controller.get_massage_state()["timer_mode"] == "20"

    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.massage_wave_next()
    await controller.massage_wave_next()
    await controller.massage_wave_next()
    await controller.massage_wave_next()  # Clamped at 4 but still sent.
    await controller.massage_head_down()
    await controller.massage_head_down()  # Clamped at 0 but still sent.
    await controller.set_heal_massage_level("foot", 2)
    assert _written(mock_bleak_client) == [
        "e5fe1610000021d5",
        "e5fe1610000022d4",
        "e5fe1610000023d3",
        "e5fe1610000023d3",
        "e5fe1610000010e6",
        "e5fe1610000010e6",
        "e5fe1611000012e3",
    ]
    assert coordinator.controller_state["okin_app_massage_wave"] == 4
    for zone, level in (("wave", 0), ("wave", 5), ("head", 4), ("lumbar", 1)):
        with pytest.raises(ValueError):
            await controller.set_heal_massage_level(zone, level)

    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.massage_off()
    assert _written(mock_bleak_client) == HEAL_STOP
    with pytest.raises(ValueError):
        await controller.massage_foot_up()

    # TV-timer10-changed-off-zone: a zero level becomes one, the rest are kept.
    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.set_massage_timer(10)
    assert _written(mock_bleak_client) == [
        "e5fe1610000030c6",
        "e5fe1610000023d3",
        "e5fe1610000011e5",
        "e5fe1611000012e3",
    ]
    mock_bleak_client.write_gatt_char.reset_mock()
    await controller.set_massage_timer(0)  # The timer select's Off is the STOP button.
    assert _written(mock_bleak_client) == HEAL_STOP
    with pytest.raises(ValueError):
        await controller.set_massage_timer(15)


async def test_heal_light_is_healing_7_and_8_only(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    healing_6 = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT, 2)
    assert not healing_6.supports_lights
    with pytest.raises(NotImplementedError):
        await healing_6.lights_on()
    healing_7 = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT, 3)
    assert healing_7.supports_discrete_light_control
    await healing_7.lights_toggle()
    await healing_7.lights_toggle()
    await healing_7.lights_off()
    assert _written(mock_bleak_client) == [
        "e5fe1631000001d4",
        "e5fe1631000000d5",
        "e5fe1631000000d5",
    ]


@pytest.mark.parametrize(
    ("variant", "motors", "keys"),
    [
        (KEESON_VARIANT_SIMON_LI, 2, ["back", "feet", "lumbar"]),
        (KEESON_VARIANT_SIMON_LI, 4, ["back", "feet", "lumbar"]),
        (KEESON_VARIANT_OKIN_SEATING, 4, ["back", "feet"]),
        (KEESON_VARIANT_HEAL_EVERY_NIGHT, 2, ["head", "feet"]),
        (KEESON_VARIANT_HEAL_EVERY_NIGHT, 3, ["head", "feet", "tilt", "lumbar"]),
        (KEESON_VARIANT_HEAL_EVERY_NIGHT, 4, ["head", "feet", "tilt", "lumbar"]),
    ],
)
async def test_each_app_exposes_its_fixed_controls(coordinator, variant, motors, keys):
    controller = _ctrl(coordinator, variant, motors)
    assert [spec.key for spec in controller.motor_control_specs] == keys


async def test_capabilities_are_gated_per_app(coordinator):
    simon = _ctrl(coordinator, KEESON_VARIANT_SIMON_LI)
    seating = _ctrl(coordinator, KEESON_VARIANT_OKIN_SEATING)
    heal = _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT, 4)
    for controller in (simon, seating, heal):
        assert controller.supports_stop_all
        assert controller.requires_notification_channel
        assert not controller.supports_single_address_pairing
        assert not controller.supports_preset_lounge
        assert not controller.supports_preset_tv
        assert not controller.supports_preset_anti_snore
        assert not controller.supports_massage_toggle_control
        assert not controller.supports_massage_mode_step_control
        assert not controller.supports_light_toggle_control
    for controller in (simon, seating):
        assert not controller.supports_preset_flat
        assert not controller.supports_preset_zero_g
        assert not controller.supports_lights
        assert not controller.auto_enable_massage
        assert not controller.supports_massage_off_control
        assert not controller.supports_head_massage_intensity_step_control
        assert not controller.supports_massage_timer
        assert controller.controller_number_specs == ()
        assert controller.controller_select_specs == ()
        assert [spec.key for spec in controller.controller_button_specs] == ["okin_app_home"]
    assert simon.memory_slot_count == 2 and simon.supports_memory_programming
    assert seating.memory_slot_count == 0 and not seating.supports_memory_presets
    assert heal.memory_slot_count == 2 and heal.supports_memory_programming
    assert heal.supports_preset_flat and heal.supports_preset_zero_g
    assert heal.auto_enable_massage and heal.supports_massage_off_control
    assert heal.supports_massage_wave_direction_control
    assert heal.massage_timer_options == [10, 20, 30]
    assert heal.controller_button_specs == ()
    assert [
        (s.key, s.native_min_value, s.native_max_value) for s in heal.controller_number_specs
    ] == [
        ("okin_app_massage_head", 0, 3),
        ("okin_app_massage_foot", 0, 3),
        ("okin_app_massage_wave", 1, 4),
    ]
    assert [s.key for s in heal.controller_select_specs] == [
        "okin_app_installation",
        "okin_app_actuator_1",
        "okin_app_actuator_2",
    ]


def test_java_uuid_order_is_signed():
    low = "00000000-0000-1000-8000-00805f9b34fb"
    high_bit = "80000000-0000-1000-8000-00805f9b34fb"
    assert java_uuid_order(high_bit) < java_uuid_order(low)


async def test_write_goes_to_the_last_ffe9_service_with_android_write_type(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    first = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    last = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write", "write-without-response"])
    mock_bleak_client.services = [
        _service("0000ffe5-0000-1000-8000-00805f9b34fb", last),
        # Java orders this negative high word first, so FFE5 is the last match.
        _service("f0000000-0000-1000-8000-00805f9b34fb", first),
    ]
    controller = _ctrl(coordinator, KEESON_VARIANT_OKIN_SEATING)
    await controller.hold_control("home", 100)
    await_args = mock_bleak_client.write_gatt_char.await_args
    assert await_args.args[0] is last
    assert await_args.kwargs["response"] is False

    mock_bleak_client.services = [_service("0000ffe5-0000-1000-8000-00805f9b34fb", first)]
    await controller.hold_control("home", 100)
    assert mock_bleak_client.write_gatt_char.await_args.kwargs["response"] is True


@pytest.mark.parametrize(
    "services",
    [
        [
            _service(
                "0000ffe0-0000-1000-8000-00805f9b34fb",
                _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"]),
            )
        ],
        [
            _service(
                "0000ffe5-0000-1000-8000-00805f9b34fb",
                _char(KEESON_BASE_WRITE_CHAR_UUID, ["write-without-response"]),
            )
        ],
    ],
)
async def test_missing_or_unwritable_ffe9_fails_without_a_write(
    coordinator, mock_bleak_client: MagicMock, no_sleep, services
):
    mock_bleak_client.services = services
    with pytest.raises(BleakError):
        await _ctrl(coordinator, KEESON_VARIANT_HEAL_EVERY_NIGHT).preset_flat()
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_every_ffe4_is_subscribed_and_failures_do_not_block(
    coordinator, mock_bleak_client: MagicMock, no_sleep
):
    a = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    b = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["notify"])
    no_notify = _char(KEESON_BASE_NOTIFY_CHAR_UUID, ["read"])
    write = _char(KEESON_BASE_WRITE_CHAR_UUID, ["write"])
    mock_bleak_client.services = [
        _service("0000ffe0-0000-1000-8000-00805f9b34fb", a, no_notify),
        _service("0000ffe5-0000-1000-8000-00805f9b34fb", b, write),
    ]
    mock_bleak_client.start_notify = AsyncMock(side_effect=[BleakError("no CCCD"), None])
    controller = _ctrl(coordinator, KEESON_VARIANT_SIMON_LI)
    await controller.start_notify(None)
    assert [c.args[0] for c in mock_bleak_client.start_notify.await_args_list] == [a, b]
    # The replies are discarded: only diagnostics see them.
    controller._on_notification(MagicMock(), bytearray(b"\xe2\xfe\x16\x00"))
    assert coordinator.controller_state == {}
    await controller.preset_memory(1)
    assert _written(mock_bleak_client)[0] == "e5fe1600000040c6"


async def test_profiles_are_selected_only_explicitly(coordinator):
    auto = await create_controller(
        coordinator=coordinator,
        bed_type=BED_TYPE_KEESON,
        protocol_variant="auto",
        client=coordinator.client,
        device_name="Simon Li",
    )
    assert type(auto) is KeesonController
    assert auto._variant == KEESON_VARIANT_BASE
    for variant in (
        KEESON_VARIANT_SIMON_LI,
        KEESON_VARIANT_HEAL_EVERY_NIGHT,
        KEESON_VARIANT_OKIN_SEATING,
    ):
        explicit = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_KEESON,
            protocol_variant=variant,
            client=coordinator.client,
            device_name="Simon Li",
        )
        assert isinstance(explicit, OkinAppKeesonController)
        assert explicit._variant == variant


def _entry(hass: HomeAssistant, address: str, variant: str, motors: int) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin seat",
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Okin seat",
            CONF_BED_TYPE: BED_TYPE_KEESON,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: motors,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id=address,
        entry_id=f"okin_{address.replace(':', '')}",
    )
    entry.add_to_hass(hass)
    return entry


async def _reload(hass: HomeAssistant, entry: MockConfigEntry, **changes: Any) -> None:
    hass.config_entries.async_update_entry(entry, data={**entry.data, **changes})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_exposes_each_app_surface_and_cleans_up(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
):
    address = "AA:BB:CC:DD:EE:61"
    entry = _entry(hass, address, KEESON_VARIANT_HEAL_EVERY_NIGHT, 4)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # No PIN, handshake or initialization frame: setup writes nothing.
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    registry = er.async_get(hass)

    def exists(platform: str, key: str) -> bool:
        return registry.async_get_entity_id(platform, DOMAIN, f"{address}_{key}") is not None

    for key in ("head", "feet", "tilt", "lumbar"):
        assert exists("cover", key), key
    for key in (
        "preset_flat",
        "preset_zero_g",
        "preset_memory_1",
        "preset_memory_2",
        "program_memory_1",
        "program_memory_2",
        "stop",
        "massage_all_off",
        "massage_head_up",
        "massage_foot_down",
        "massage_wave_next",
        "massage_wave_previous",
    ):
        assert exists("button", key), key
    for key in ("preset_memory_3", "preset_anti_snore", "massage_all_toggle", "toggle_light"):
        assert not exists("button", key), key
    for key in ("okin_app_massage_head", "okin_app_massage_foot", "okin_app_massage_wave"):
        assert exists("number", f"controller_number_{key}"), key
    for key in ("okin_app_installation", "okin_app_actuator_1", "okin_app_actuator_2"):
        assert exists("select", f"controller_select_{key}"), key
    assert exists("select", "massage_timer")
    assert exists("switch", "under_bed_lights")

    # Settings are local: no frame, persisted in the entry, and remap the keys.
    state_id = registry.async_get_entity_id(
        "select", DOMAIN, f"{address}_controller_select_okin_app_installation"
    )
    assert hass.states.get(state_id).state == "standard"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": state_id, "option": "swapped"}, blocking=True
    )
    await hass.async_block_till_done()
    mock_bleak_client.write_gatt_char.assert_not_awaited()  # A local setting sends nothing.
    assert entry.data[CONF_OKIN_APP_SETTINGS] == {
        "installation": True,
        "actuator_1": False,
        "actuator_2": False,
    }
    assert hass.states.get(state_id).state == "swapped"

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_SIMON_LI})
    for key in ("back", "feet", "lumbar"):
        assert exists("cover", key), key
    assert not exists("cover", "head")
    assert not exists("cover", "tilt")
    for key in ("okin_app_home", "preset_memory_2", "program_memory_2", "stop"):
        assert exists("button", key), key
    for key in ("preset_flat", "preset_zero_g", "massage_all_off", "massage_wave_next"):
        assert not exists("button", key), key
    assert not exists("select", "controller_select_okin_app_installation")
    assert not exists("number", "controller_number_okin_app_massage_wave")
    assert not exists("select", "massage_timer")
    assert not exists("switch", "under_bed_lights")

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_OKIN_SEATING})
    assert not exists("cover", "lumbar")
    assert exists("button", "okin_app_home")
    assert not exists("button", "preset_memory_1")

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_BASE})
    assert not exists("button", "okin_app_home")
    assert not exists("cover", "back")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_hold_service(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address: MagicMock,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
    no_sleep,
):
    address = "AA:BB:CC:DD:EE:62"
    entry = _entry(hass, address, KEESON_VARIANT_SIMON_LI, 2)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "okin_app_hold_control",
            {"device_id": [device.id], "control": "tilt_up", "duration": 1},
            blocking=True,
        )
    mock_bleak_client.write_gatt_char.assert_not_awaited()

    await hass.services.async_call(
        DOMAIN,
        "okin_app_hold_control",
        {"device_id": [device.id], "control": "home", "duration": 0.3},
        blocking=True,
    )
    assert _written(mock_bleak_client) == ["e5fe1600000016f0"] * 3 + [ZERO]

    await _reload(hass, entry, **{CONF_PROTOCOL_VARIANT: KEESON_VARIANT_BASE})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "okin_app_hold_control",
            {"device_id": [device.id], "control": "home", "duration": 1},
            blocking=True,
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
