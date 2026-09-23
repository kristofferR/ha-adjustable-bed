"""Woosa Sleep 1.1.9 artifact vectors and command lifecycle.

Vector provenance: accepted report C01-C61 / N01-N07, documented in
docs/beds/woosa-disposition.md. No physical hardware confirmation is implied.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.solace import (
    SolaceController,
    build_solace_clock_command,
)
from custom_components.adjustable_bed.beds.woosa import WoosaController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SOLACE_CHAR_UUID,
    SOLACE_VARIANT_WOOSA,
    bed_type_has_position_feedback,
)
from custom_components.adjustable_bed.number import (
    MASSAGE_NUMBER_DESCRIPTIONS,
    AdjustableBedMassageNumber,
)
from custom_components.adjustable_bed.select import (
    MASSAGE_TIMER_DESCRIPTION,
    AdjustableBedMassageTimerSelect,
)
from custom_components.adjustable_bed.services import handle_solace_set_alarm


@pytest.fixture
def controller() -> Iterator[WoosaController]:
    coordinator = MagicMock()
    coordinator.controller_state = {}
    coordinator.cancel_command = asyncio.Event()
    coordinator.handle_controller_state_updates.side_effect = coordinator.controller_state.update
    coordinator.handle_controller_state_update.side_effect = (
        coordinator.controller_state.__setitem__
    )
    ctrl = WoosaController(coordinator)
    coordinator.controller = ctrl
    ctrl.write_command = AsyncMock()
    yield ctrl
    if ctrl._massage_expiry_handle is not None:
        ctrl._massage_expiry_handle.cancel()


def written(controller: WoosaController) -> list[str]:
    return [call.args[0].hex().upper() for call in controller.write_command.await_args_list]


def test_capability_surface(controller: WoosaController) -> None:
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]
    assert controller.memory_slot_count == 1
    assert controller.auto_enable_massage
    assert controller.massage_intensity_max == 3
    assert controller.massage_intensity_zones == ["head", "foot"]
    assert controller.supports_discrete_light_control
    assert controller.supports_light_level_control
    assert controller.supports_solace_alarm
    assert not controller.supports_solace_audio
    assert not controller.supports_preset_anti_snore
    assert not controller.supports_circulation_massage
    assert not controller.supports_massage_wave_frequency_control
    assert not controller.supports_light_state_feedback
    assert not bed_type_has_position_feedback(BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA)
    assert {spec.key for spec in controller.controller_button_specs} == {
        "woosa_love",
        "woosa_program_love",
        "woosa_program_tv",
        "woosa_program_zero_g",
        *(f"woosa_massage_mode_{mode}" for mode in range(1, 5)),
    }


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (0, "FFFFFFFF050000002396D9"),
        (1, "FFFFFFFF05000001239749"),
        (2, "FFFFFFFF050000022397B9"),
        (3, "FFFFFFFF05000003239629"),
        (4, "FFFFFFFF05000004239419"),
        (5, "FFFFFFFF05000005239589"),
        (6, "FFFFFFFF05000006239579"),
        (7, "FFFFFFFF050000072394E9"),
        (8, "FFFFFFFF05000008239119"),
        (9, "FFFFFFFF05000009239089"),
        (10, "FFFFFFFF0500000A239079"),
    ],
)
async def test_light_level_vectors(controller, level, expected) -> None:
    await controller.set_light_level(level)
    assert written(controller) == [expected]
    assert controller._coordinator.controller_state["light_level"] == level
    assert controller._coordinator.controller_state["under_bed_lights_on"] is (level > 0)
    if level == 0:
        assert controller._coordinator.controller_state["light_timer_option"] == "Off"


@pytest.mark.parametrize(
    ("option", "frame"),
    [
        ("10 min", "FFFFFFFF050000001916CA"),
        ("8 hours", "FFFFFFFF050000001A56CB"),
        ("10 hours", "FFFFFFFF050000001B970B"),
        ("Off", "FFFFFFFF050000004B9737"),
    ],
)
async def test_light_timer_and_explicit_off(controller, option, frame) -> None:
    await controller.set_light_timer(option)
    assert written(controller) == [frame]
    assert controller._coordinator.controller_state["light_timer_option"] == option
    assert controller.light_auto_off_seconds == {
        "10 min": 600,
        "8 hours": 28800,
        "10 hours": 36000,
        "Off": None,
    }[option]
    if option != "Off":
        await controller.lights_on()
        assert written(controller) == [frame, frame]


@pytest.mark.parametrize(
    ("zone", "frames"),
    [
        (
            "head",
            [
                "FFFFFFFF050000004F96F4",
                "FFFFFFFF0500000050D73C",
                "FFFFFFFF050000005116FC",
                "FFFFFFFF050000005256FD",
            ],
        ),
        (
            "foot",
            [
                "FFFFFFFF0500000053973D",
                "FFFFFFFF0500000054D6FF",
                "FFFFFFFF0500000055173F",
                "FFFFFFFF0500000056573E",
            ],
        ),
    ],
)
async def test_absolute_massage_vectors(controller, zone, frames) -> None:
    for level in range(4):
        await controller.set_massage_intensity(zone, level)
    assert written(controller) == frames
    assert controller.get_massage_state()[f"{zone}_intensity"] == 3


async def test_massage_modes_and_timer_vectors(controller) -> None:
    for mode in range(1, 5):
        await controller.set_massage_mode(mode)
    await controller.massage_mode_step()
    for minutes in (10, 20, 30, 0):
        await controller.set_massage_timer(minutes)
    assert written(controller) == [
        "FFFFFFFF050000005796FE",
        "FFFFFFFF0500000058D6FA",
        "FFFFFFFF0500000059173A",
        "FFFFFFFF050000005A573B",
        "FFFFFFFF0500050014C70E",
        "FFFFFFFF050000001656CE",
        "FFFFFFFF0500000017970E",
        "FFFFFFFF0500000018D70A",
        "FFFFFFFF050000001CD6C9",
    ]


def test_massage_entities_retain_state_without_live_controller(controller) -> None:
    coordinator = controller._coordinator
    coordinator.controller = None
    coordinator.capability_controller = controller
    coordinator.entity_side = None
    coordinator.device_info = {}
    coordinator.controller_state.update(
        {"woosa_head_level": 2, "woosa_foot_level": 3, "woosa_massage_timer": 20}
    )
    head = AdjustableBedMassageNumber(coordinator, MASSAGE_NUMBER_DESCRIPTIONS[1])
    foot = AdjustableBedMassageNumber(coordinator, MASSAGE_NUMBER_DESCRIPTIONS[2])
    timer = AdjustableBedMassageTimerSelect(
        coordinator, MASSAGE_TIMER_DESCRIPTION, controller.massage_timer_options
    )
    assert head.native_value == 2
    assert foot.native_value == 3
    assert timer.current_option == "20 min"


async def test_massage_timer_expiry_clears_activity_and_preserves_preferences(controller) -> None:
    await controller.set_massage_intensity("head", 2)
    await controller.set_massage_intensity("foot", 3)
    await controller.set_massage_timer(10)
    state = controller._coordinator.controller_state
    old_deadline = state["woosa_massage_deadline"]
    await controller.set_massage_timer(20)
    controller._expire_massage(old_deadline)
    assert state["woosa_massage_timer"] == 20

    state["woosa_massage_active"] = True
    assert controller._massage_expiry_handle is not None
    controller._massage_expiry_handle.cancel()
    controller._expire_massage(state["woosa_massage_deadline"])
    assert state["woosa_massage_active"] is False
    assert state["woosa_massage_timer"] == 0
    assert state["woosa_head_level"] == state["woosa_foot_level"] == 0
    assert state["woosa_head_preference"] == 2
    assert state["woosa_foot_preference"] == 3
    controller.write_command.reset_mock()
    with patch("custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock):
        await controller.massage_toggle()
    assert written(controller) == [
        "FFFFFFFF050000001CD6C9",
        "FFFFFFFF0500000017970E",
        "FFFFFFFF050000005116FC",
        "FFFFFFFF0500000056573E",
        "FFFFFFFF0500000058D6FA",
    ]
    await controller.massage_off()


async def test_massage_manual_steps_and_limits(controller) -> None:
    await controller.massage_head_up()
    await controller.massage_head_up()  # Already at maximum.
    await controller.massage_head_down()
    await controller.massage_foot_up()
    await controller.massage_foot_down()
    assert written(controller) == [
        "FFFFFFFF0500000010D6CC",
        "FFFFFFFF0500000011170C",
        "FFFFFFFF0500000012570D",
        "FFFFFFFF050000001396CD",
    ]


async def test_massage_start_sequence_preserves_independent_zones(controller) -> None:
    await controller.set_massage_intensity("head", 1)
    await controller.set_massage_intensity("foot", 3)
    controller.write_command.reset_mock()
    with patch(
        "custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await controller.massage_toggle()
    assert written(controller) == [
        "FFFFFFFF050000001CD6C9",
        "FFFFFFFF050000001656CE",
        "FFFFFFFF0500000050D73C",
        "FFFFFFFF0500000056573E",
        "FFFFFFFF0500000058D6FA",
    ]
    assert [call.args[0] for call in sleep.await_args_list] == [0.4] * 4
    await controller.massage_toggle()
    assert written(controller)[-1] == "FFFFFFFF050000001CD6C9"


async def test_massage_cancellation_stops_without_later_writes(controller) -> None:
    async def cancel(_delay):
        controller._coordinator.cancel_command.set()

    with (
        patch("custom_components.adjustable_bed.beds.woosa.asyncio.sleep", side_effect=cancel),
        pytest.raises(asyncio.CancelledError),
    ):
        await controller.massage_toggle()
    assert written(controller) == ["FFFFFFFF050000001CD6C9"] * 2
    cleanup_event = controller.write_command.await_args.kwargs["cancel_event"]
    assert not cleanup_event.is_set()
    assert not controller._coordinator.controller_state["woosa_massage_active"]


@pytest.mark.parametrize(
    ("method", "frame"),
    [
        ("move_back_up", "FFFFFFFF05000000039701"),
        ("move_back_down", "FFFFFFFF0500000004D6C3"),
        ("move_legs_up", "FFFFFFFF05000000065702"),
        ("move_legs_down", "FFFFFFFF0500000008D6C6"),
    ],
)
async def test_movement_vectors_and_stop_cleanup(controller, method, frame) -> None:
    controller._coordinator.cancel_command.set()
    await getattr(controller, method)()
    assert written(controller) == [frame, "FFFFFFFF0500000000D700"]
    assert not controller.write_command.await_args.kwargs["cancel_event"].is_set()


@pytest.mark.parametrize(
    ("method", "key", "base", "saved"),
    [
        ("preset_tv", "tv", "FFFFFFFF05000000051703", "FFFFFFFF05000051052A93"),
        ("preset_zero_g", "zero_g", "FFFFFFFF05000000091706", "FFFFFFFF05000091097A96"),
        ("preset_love", "love", "FFFFFFFF050000000F9704", "FFFFFFFF050000F10FD294"),
    ],
)
async def test_preset_presence_selects_dashboard_branch(
    controller, method, key, base, saved
) -> None:
    with patch(
        "custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await getattr(controller, method)()
        controller._coordinator.controller_state[f"solace_{key}_selected"] = True
        await getattr(controller, method)()
    assert written(controller) == ["FFFFFFFF0500000000D700", base, "FFFFFFFF0500000000D700", saved]
    assert [call.args[0] for call in sleep.await_args_list] == [0.2, 0.2]


async def test_favourite_requires_reported_memory_and_flat_is_direct(controller) -> None:
    with pytest.raises(ValueError, match="reported"):
        await controller.preset_memory(1)
    controller._parse_notification(bytes.fromhex("FFFFFFFF0306000A"))
    with patch("custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock):
        await controller.preset_memory(1)
    await controller.preset_flat()
    assert written(controller) == [
        "FFFFFFFF0500000000D700",
        "FFFFFFFF050000A10A2E97",
        "FFFFFFFF0500000008D6C6",
    ]
    with pytest.raises(ValueError):
        await controller.preset_memory(2)


@pytest.mark.parametrize(
    ("key", "frame"),
    [
        ("memory_1", "FFFFFFFF050000A00A2F07"),
        ("love", "FFFFFFFF050000F00FD304"),
        ("tv", "FFFFFFFF05000050052B03"),
        ("zero_g", "FFFFFFFF05000090097B06"),
    ],
)
async def test_save_presets_queries_four_slots(controller, key, frame) -> None:
    with patch(
        "custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await controller.save_preset(key)
    assert written(controller) == [
        frame,
        "FFFFFFFF03002800039F09",
        "FFFFFFFF03001800039F06",
        "FFFFFFFF03002000031ECB",
        "FFFFFFFF03003800039ECC",
    ]
    assert [call.args[0] for call in sleep.await_args_list] == [0.3] * 4
    assert not controller._preset_is_selected(key)


async def test_preset_cancellation_during_preamble(controller) -> None:
    async def cancel(_delay):
        controller._coordinator.cancel_command.set()

    with patch("custom_components.adjustable_bed.beds.woosa.asyncio.sleep", side_effect=cancel):
        await controller.preset_tv()
    assert written(controller) == ["FFFFFFFF0500000000D700"]


async def test_startup_schedule_and_controller_replacement(controller) -> None:
    async def execute(fn, **kwargs):
        await fn(controller._coordinator.controller)

    controller._coordinator.async_execute_controller_query = AsyncMock(side_effect=execute)
    now = datetime(2026, 9, 23, 12, 34, 56)
    with (
        patch(
            "custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock
        ) as sleep,
        patch("custom_components.adjustable_bed.beds.woosa.dt_util.now", return_value=now),
    ):
        await controller._async_query_preset_states("woosa")
    assert written(controller) == [
        "FFFFFFFF02000E0B001704",
        "FFFFFFFF03002800039F09",
        "FFFFFFFF03001800039F06",
        "FFFFFFFF01000111123456032609230005",
        "FFFFFFFF03002000031ECB",
        "FFFFFFFF01000A0B0F2104",
        "FFFFFFFF03003800039ECC",
        "FFFFFFFF050005FF23C728",
    ]
    assert sum(call.args[0] for call in sleep.await_args_list) == pytest.approx(1.5)
    controller.write_command.reset_mock()
    controller._coordinator.controller = MagicMock()
    await controller._async_query_preset_states("woosa")
    controller.write_command.assert_not_awaited()


async def test_alarm_packet_and_sound_gate(controller) -> None:
    args = {
        "enabled": True,
        "hour": 7,
        "minute": 30,
        "weekdays": (1, 3),
        "mode": "zero_g",
        "massage": True,
        "sound": "alarm",
    }
    await controller.program_solace_alarm(**args)
    assert written(controller) == [
        "FFFFFFFF01000213010730000A010101015804",
        "FFFFFFFF01000A0B0F2104",
    ]
    controller.write_command.reset_mock()
    with pytest.raises(ValueError, match="music"):
        await controller.program_solace_alarm(**{**args, "sound": "music_1"})
    controller.write_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("frame", "key", "value"),
    [
        ("FFFFFFFF0500000100D690", "woosa_head_level", 0),
        ("FFFFFFFF050000011E5698", "woosa_head_level", 1),
        ("FFFFFFFF050000011F9758", "woosa_head_level", 2),
        ("FFFFFFFF0500000120D748", "woosa_head_level", 3),
        ("FFFFFFFF0500000200D660", "woosa_foot_level", 0),
        ("FFFFFFFF05000002211678", "woosa_foot_level", 1),
        ("FFFFFFFF05000002225679", "woosa_foot_level", 2),
        ("FFFFFFFF050000022397B9", "woosa_foot_level", 3),
        ("FFFFFFFF0500000324D7EB", "woosa_massage_mode", 1),
        ("FFFFFFFF0500000325162B", "woosa_massage_mode", 2),
        ("FFFFFFFF0500000326562A", "woosa_massage_mode", 3),
        ("FFFFFFFF050000032797EA", "woosa_massage_mode", 4),
        ("FFFFFFFF0306000A", "solace_memory_1_selected", True),
        ("FFFFFFFF0306000F", "solace_love_selected", True),
        ("FFFFFFFF03060005", "solace_tv_selected", True),
        ("FFFFFFFF03060009", "solace_zero_g_selected", True),
    ],
)
def test_notification_vectors(controller, frame, key, value) -> None:
    controller._parse_notification(bytes.fromhex(frame))
    assert controller._coordinator.controller_state[key] == value


def test_ambiguous_light_value_is_diagnostic_only(controller) -> None:
    # The app's brightness-level2 frame is also its foot-massage level3 reply.
    controller._parse_notification(bytes.fromhex("FFFFFFFF050000022397B9"))
    state = controller._coordinator.controller_state
    assert state["woosa_foot_level"] == 3
    assert state["woosa_light_candidate"] == 2
    assert "light_level" not in state
    assert "under_bed_lights_on" not in state


def test_alarm_parser_raw_state_and_malformed_input(controller) -> None:
    frame = bytes.fromhex("FFFFFFFF010004130F0730000A01FF0101")
    for invalid in (frame[:12], b"\x00" + frame, b"\x00\x01"):
        controller._parse_notification(invalid)
    assert not controller._coordinator.controller_state
    controller._parse_notification(frame)
    state = controller._coordinator.controller_state
    assert state["solace_alarm_enabled"] is True
    assert state["solace_alarm_mode"] == "unknown_ff"
    assert state["solace_alarm_time"] == "07:30"
    assert state["solace_alarm_weekdays"] == "1,3"
    controller._parse_notification(bytes.fromhex("FFFFFFFF0100030B00"))
    assert state["solace_alarm_enabled"] is False
    assert state["solace_alarm_time"] == "00:00"
    assert state["solace_alarm_mode"] == "no_action"


def test_preset_reply_is_anchored_and_not_a_position(controller) -> None:
    controller._notify_callback = MagicMock()
    controller._parse_notification(bytes.fromhex("00FFFFFFFF0306000A"))
    assert not controller._preset_is_selected("memory_1")
    controller._parse_notification(bytes.fromhex("FFFFFFFF0306000A"))
    assert controller._preset_is_selected("memory_1")
    controller._notify_callback.assert_not_called()


async def test_custom_buttons_dispatch_to_live_controller(controller) -> None:
    offline = WoosaController(MagicMock())
    button = next(
        spec for spec in offline.controller_button_specs if spec.key == "woosa_massage_mode_4"
    )
    await button.press_fn(controller)
    assert written(controller) == ["FFFFFFFF050000005A573B"]
    with pytest.raises(ValueError, match="Woosa"):
        await button.press_fn(SolaceController(MagicMock()))


async def test_timer_off_and_late_cancellation_clear_active_state(controller) -> None:
    await controller.set_massage_timer(20)
    await controller.set_massage_timer(0)
    assert controller.get_massage_state()["timer_mode"] == "0"
    controller.write_command.reset_mock()
    waits = 0

    async def cancel_after_head(_delay):
        nonlocal waits
        waits += 1
        if waits == 3:
            controller._parse_notification(bytes.fromhex("FFFFFFFF050000011F9758"))
            controller._coordinator.cancel_command.set()

    with (
        patch(
            "custom_components.adjustable_bed.beds.woosa.asyncio.sleep",
            side_effect=cancel_after_head,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await controller.massage_toggle()
    assert written(controller) == [
        "FFFFFFFF050000001CD6C9",
        "FFFFFFFF0500000017970E",
        "FFFFFFFF050000005116FC",
        "FFFFFFFF050000001CD6C9",
    ]
    assert not controller._coordinator.controller_state["woosa_massage_active"]
    assert controller.get_massage_state()["timer_mode"] == "0"


@pytest.mark.parametrize(
    ("date", "frame"),
    [
        (datetime(2026, 9, 23, 12, 34, 56), "FFFFFFFF01000111123456032609230005"),
        # V-CLOCK2 uses independently supplied weekday 1; DateBean derives Saturday 6.
        (datetime(2000, 1, 1), "FFFFFFFF01000111000000060001011704"),
    ],
)
def test_clock_date_encoding(date, frame) -> None:
    assert build_solace_clock_command(date).hex().upper() == frame


@pytest.mark.parametrize(
    ("enabled", "hour", "minute", "days", "mode", "massage", "sound", "frame"),
    [
        (False, 0, 0, (), "no_action", False, "none", "FFFFFFFF01000213A10000000000030000B604"),
        (
            True,
            23,
            59,
            (1, 2, 3, 4, 5, 6, 7),
            "no_action",
            True,
            "alarm",
            "FFFFFFFF0100021301235900FE010301019305",
        ),
        (False, 23, 59, (), "memory_1", False, "alarm", "FFFFFFFF01000213A123590000000200013205"),
        (False, 23, 59, (1,), "memory_1", False, "alarm", "FFFFFFFF01000213A123590002010200013505"),
    ],
)
async def test_alarm_supported_selectors(
    controller, enabled, hour, minute, days, mode, massage, sound, frame
) -> None:
    await controller.program_solace_alarm(
        enabled=enabled,
        hour=hour,
        minute=minute,
        weekdays=days,
        mode=mode,
        massage=massage,
        sound=sound,
    )
    assert written(controller) == [frame, "FFFFFFFF01000A0B0F2104"]


async def test_alarm_sound_preflight_checks_all_targets(hass, controller) -> None:
    motionflex = MagicMock(capability_controller=SolaceController(MagicMock(ble_device_name="SealyMF")))
    woosa = MagicMock(capability_controller=controller)
    call = ServiceCall(
        hass,
        DOMAIN,
        "solace_set_alarm",
        {
            "device_id": ["motionflex", "woosa"],
            "enabled": True,
            "time": time(7, 30),
            "weekdays": [],
            "mode": "no_action",
            "massage": False,
            "sound": "music_1",
        },
    )
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(motionflex, "both"), (woosa, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._execute_sided", new_callable=AsyncMock
        ) as execute,
        pytest.raises(ServiceValidationError, match="sound"),
    ):
        await handle_solace_set_alarm(call)
    execute.assert_not_awaited()
    controller.write_command.assert_not_awaited()


async def test_woosa_setup_restores_light_and_exposes_profile_controls(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_async_ble_device_from_address,
    mock_bleak_client,
    enable_custom_integrations,
) -> None:
    mock_async_ble_device_from_address.return_value.name = "QMS-MQ-2228068"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Woosa",
            CONF_BED_TYPE: BED_TYPE_SOLACE,
            CONF_PROTOCOL_VARIANT: SOLACE_VARIANT_WOOSA,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_HAS_MASSAGE: False,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def entity_id(platform, key):
        found = registry.async_get_entity_id(platform, DOMAIN, f"AA:BB:CC:DD:EE:FF_{key}")
        assert found is not None
        return found

    light = entity_id("switch", "under_bed_lights")
    entity_id("number", "light_level")
    entity_id("button", "woosa_love")
    entity_id("button", "woosa_program_love")
    entity_id("button", "woosa_massage_mode_4")
    entity_id("button", "massage_mode_step")
    entity_id("binary_sensor", "solace_alarm_enabled")
    assert registry.async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:FF_back_position") is None
    await hass.services.async_call("switch", "turn_on", {"entity_id": light}, blocking=True)
    mock_bleak_client.write_gatt_char.assert_any_call(
        SOLACE_CHAR_UUID, bytes.fromhex("FFFFFFFF050000001916CA"), response=True
    )
    await hass.services.async_call("switch", "turn_off", {"entity_id": light}, blocking=True)
    assert hass.states.get(entity_id("select", "light_timer")).state == "Off"
    mock_bleak_client.write_gatt_char.assert_any_call(
        SOLACE_CHAR_UUID, bytes.fromhex("FFFFFFFF050000004B9737"), response=True
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id("select", "light_timer"), "option": "8 hours"},
        blocking=True,
    )
    assert hass.states.get(light).state == "on"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id("select", "light_timer"), "option": "Off"},
        blocking=True,
    )
    assert hass.states.get(light).state == "off"
    level = entity_id("number", "light_level")
    await hass.services.async_call(
        "number", "set_value", {"entity_id": level, "value": 5}, blocking=True
    )
    assert hass.states.get(light).state == "on"
    await hass.services.async_call(
        "number", "set_value", {"entity_id": level, "value": 0}, blocking=True
    )
    assert hass.states.get(light).state == "off"
    assert hass.states.get(entity_id("select", "light_timer")).state == "Off"
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    await hass.services.async_call(
        DOMAIN,
        "solace_set_alarm",
        {
            "device_id": [device.id],
            "enabled": True,
            "time": "07:30:00",
            "weekdays": ["monday", "wednesday"],
            "mode": "zero_g",
            "massage": True,
            "sound": "alarm",
        },
        blocking=True,
    )
    mock_bleak_client.write_gatt_char.assert_any_call(
        SOLACE_CHAR_UUID, bytes.fromhex("FFFFFFFF01000213010730000A010101015804"), response=True
    )
    await hass.config_entries.async_unload(entry.entry_id)


async def test_massage_restart_preserves_requested_levels(controller) -> None:
    await controller.set_massage_intensity("head", 1)
    await controller.set_massage_intensity("foot", 3)
    await controller.set_massage_timer(30)
    await controller.set_massage_mode(4)
    with patch("custom_components.adjustable_bed.beds.woosa.asyncio.sleep", new_callable=AsyncMock):
        await controller.massage_toggle()
        await controller.massage_toggle()
        controller._parse_notification(bytes.fromhex("FFFFFFFF0500000100D690"))
        controller._parse_notification(bytes.fromhex("FFFFFFFF0500000200D660"))
        controller.write_command.reset_mock()
        await controller.massage_toggle()
    assert written(controller) == [
        "FFFFFFFF050000001CD6C9",
        "FFFFFFFF0500000018D70A",
        "FFFFFFFF0500000050D73C",
        "FFFFFFFF0500000056573E",
        "FFFFFFFF050000005A573B",
    ]
    assert controller._coordinator.controller_state["woosa_massage_active"]
