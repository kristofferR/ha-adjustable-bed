"""Row 050 Remacro app profiles: artifact frames, timing and model routing.

Literal vectors come from the accepted com.cheers.slumber / com.cheers.brick /
com.cheers.jewmes reports (TV*/T* ids) and the cluster-002 reconciliation's
decisive sequences. Hardware is unverified.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds import remacro_protocol as protocol
from custom_components.adjustable_bed.beds.remacro import RemacroController
from custom_components.adjustable_bed.const import (
    BED_TYPE_REMACRO,
    BEDS_REQUIRING_PAIRING,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_REMACRO_LED_LEVEL,
    CONF_REMACRO_MODEL,
    DOMAIN,
    REMACRO_READ_CHAR_UUID,
    REMACRO_VARIANTS,
    REMACRO_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller

SLUMBER = protocol.APP_SLUMBERLAND
BRICK = protocol.APP_THE_BRICK
JEROMES = protocol.APP_JEROMES

# Jerome's T001-T092 (serial 0x81, PID 1, parameter 0): every control code.
ARTIFACT_CODE_VECTORS = {
    0x0001: "81 01 01 00 00 00 00 00",
    0x0100: "81 01 00 01 00 00 00 00",
    0x0101: "81 01 01 01 00 00 00 00",
    0x0102: "81 01 02 01 00 00 00 00",
    0x0104: "81 01 04 01 00 00 00 00",
    0x0105: "81 01 05 01 00 00 00 00",
    0x0106: "81 01 06 01 00 00 00 00",
    0x0108: "81 01 08 01 00 00 00 00",
    0x0109: "81 01 09 01 00 00 00 00",
    0x010A: "81 01 0a 01 00 00 00 00",
    0x0110: "81 01 10 01 00 00 00 00",
    0x0111: "81 01 11 01 00 00 00 00",
    0x0123: "81 01 23 01 00 00 00 00",
    0x0124: "81 01 24 01 00 00 00 00",
    0x0133: "81 01 33 01 00 00 00 00",
    0x0134: "81 01 34 01 00 00 00 00",
    0x0200: "81 01 00 02 00 00 00 00",
    0x0201: "81 01 01 02 00 00 00 00",
    0x0202: "81 01 02 02 00 00 00 00",
    0x0203: "81 01 03 02 00 00 00 00",
    0x0204: "81 01 04 02 00 00 00 00",
    0x0205: "81 01 05 02 00 00 00 00",
    0x0206: "81 01 06 02 00 00 00 00",
    0x0207: "81 01 07 02 00 00 00 00",
    0x0208: "81 01 08 02 00 00 00 00",
    0x0209: "81 01 09 02 00 00 00 00",
    0x020A: "81 01 0a 02 00 00 00 00",
    0x020B: "81 01 0b 02 00 00 00 00",
    0x020C: "81 01 0c 02 00 00 00 00",
    0x0220: "81 01 20 02 00 00 00 00",
    0x0221: "81 01 21 02 00 00 00 00",
    0x0222: "81 01 22 02 00 00 00 00",
    0x0228: "81 01 28 02 00 00 00 00",
    0x0229: "81 01 29 02 00 00 00 00",
    0x022A: "81 01 2a 02 00 00 00 00",
    0x0230: "81 01 30 02 00 00 00 00",
    0x0231: "81 01 31 02 00 00 00 00",
    0x0233: "81 01 33 02 00 00 00 00",
    0x0240: "81 01 40 02 00 00 00 00",
    0x0242: "81 01 42 02 00 00 00 00",
    0x0248: "81 01 48 02 00 00 00 00",
    0x0249: "81 01 49 02 00 00 00 00",
    0x024A: "81 01 4a 02 00 00 00 00",
    0x0250: "81 01 50 02 00 00 00 00",
    0x0251: "81 01 51 02 00 00 00 00",
    0x0253: "81 01 53 02 00 00 00 00",
    0x0301: "81 01 01 03 00 00 00 00",
    0x0302: "81 01 02 03 00 00 00 00",
    0x0303: "81 01 03 03 00 00 00 00",
    0x0310: "81 01 10 03 00 00 00 00",
    0x0311: "81 01 11 03 00 00 00 00",
    0x0312: "81 01 12 03 00 00 00 00",
    0x0313: "81 01 13 03 00 00 00 00",
    0x0500: "81 01 00 05 00 00 00 00",
    0x0501: "81 01 01 05 00 00 00 00",
    0x050F: "81 01 0f 05 00 00 00 00",
    0x2401: "81 01 01 24 00 00 00 00",
    0x6400: "81 01 00 64 00 00 00 00",
    0x6401: "81 01 01 64 00 00 00 00",
    0x6402: "81 01 02 64 00 00 00 00",
    0x6403: "81 01 03 64 00 00 00 00",
    0x6404: "81 01 04 64 00 00 00 00",
    0x6405: "81 01 05 64 00 00 00 00",
    0x6406: "81 01 06 64 00 00 00 00",
    0x6407: "81 01 07 64 00 00 00 00",
    0x6408: "81 01 08 64 00 00 00 00",
    0x6409: "81 01 09 64 00 00 00 00",
    0x640A: "81 01 0a 64 00 00 00 00",
    0x640B: "81 01 0b 64 00 00 00 00",
    0x640C: "81 01 0c 64 00 00 00 00",
    0x640D: "81 01 0d 64 00 00 00 00",
    0x640E: "81 01 0e 64 00 00 00 00",
    0x6443: "81 01 43 64 00 00 00 00",
    0x6444: "81 01 44 64 00 00 00 00",
    0x6445: "81 01 45 64 00 00 00 00",
    0x6455: "81 01 55 64 00 00 00 00",
    0x6456: "81 01 56 64 00 00 00 00",
    0x6457: "81 01 57 64 00 00 00 00",
    0x6511: "81 01 11 65 00 00 00 00",
    0x6512: "81 01 12 65 00 00 00 00",
    0x6513: "81 01 13 65 00 00 00 00",
    0x6521: "81 01 21 65 00 00 00 00",
    0x6522: "81 01 22 65 00 00 00 00",
    0x6523: "81 01 23 65 00 00 00 00",
    0x6530: "81 01 30 65 00 00 00 00",
    0x6531: "81 01 31 65 00 00 00 00",
    0x6538: "81 01 38 65 00 00 00 00",
    0x6539: "81 01 39 65 00 00 00 00",
    0x6540: "81 01 40 65 00 00 00 00",
    0x6541: "81 01 41 65 00 00 00 00",
    0x6548: "81 01 48 65 00 00 00 00",
    0x6549: "81 01 49 65 00 00 00 00",
}


def _hex(value: str) -> bytes:
    return bytes.fromhex(value)


def _protocol_codes() -> set[int]:
    codes = {protocol.FLAT, protocol.MOTOR_STOP, protocol.LIGHT_OFF, protocol.LIGHT_RGBV}
    codes.add(protocol.LIGHT_RGBV_SAVE)
    for screen in protocol.SCREENS.values():
        for side in (screen.left, screen.right):
            if side is None:
                continue
            for axis in (side.combined, side.head, side.lumbar, side.foot):
                if axis is not None:
                    codes.update((axis.up, axis.down, axis.stop))
            codes.update(side.memory_recall, side.memory_save, side.presets.values())
            if side.massage is not None:
                m = side.massage
                codes.update((*m.head, *m.head_wave, m.head_off, *m.foot, *m.foot_wave))
                codes.update((m.foot_off, *m.wave, m.wave_off))
    return codes


@pytest.mark.parametrize(("code", "expected"), sorted(ARTIFACT_CODE_VECTORS.items()))
def test_frame_matches_artifact_vectors(code: int, expected: str) -> None:
    assert protocol.build_frame(0x81, protocol.PID_CONTROL, code) == _hex(expected)


def test_every_emitted_code_has_an_artifact_vector() -> None:
    assert _protocol_codes() == set(ARTIFACT_CODE_VECTORS)


def test_parameter_and_wrap_vectors() -> None:
    # Slumberland TV097/TV096, Jerome's T103/T104.
    assert protocol.build_frame(1, 1, 0x0501, protocol.LED_WHITE | 128) == _hex(
        "01 01 01 05 80 ff ff ff"
    )
    assert protocol.build_frame(256, 1, 0x0101) == _hex("00 01 01 01 00 00 00 00")
    assert protocol.build_frame(0xFF, 1, 0x0501, protocol.LED_WHITE) == _hex(
        "ff 01 01 05 00 ff ff ff"
    )
    assert protocol.build_frame(0xFF, 1, 0x050F, protocol.LED_WHITE | 255) == _hex(
        "ff 01 0f 05 ff ff ff ff"
    )


def test_counter_semantics_per_app() -> None:
    shared = protocol.SynDataSerial(cache_hold_serial=False)
    # sendCodeLong pre-increments (02); sendCode then reuses it (02).
    assert shared.hold(0x0001)[0] == 2
    assert shared.tap(0x0001)[0] == 2
    assert shared.hold(0x0001)[0] == 4

    jeromes = protocol.SynDataSerial(cache_hold_serial=True)
    assert [jeromes.hold(0x0110)[0] for _ in range(3)] == [2, 2, 2]
    assert jeromes.hold(0x0001)[0] == 3
    assert jeromes.tap(0x0111)[0] == 3
    assert jeromes.hold(0x0001)[0] == 4  # tap advanced i without touching the cache


def test_counter_wraps_low_byte() -> None:
    serial = protocol.SynDataSerial(cache_hold_serial=False)
    for _ in range(254):
        serial.hold(0x0100)
    assert serial.hold(0x0101) == _hex("00 01 01 01 00 00 00 00")


def test_model_map_and_app_divergence() -> None:
    screens = {model_id: model.screen.name for model_id, model in protocol.MODELS.items()}
    assert screens == {
        14: "TenActivity",
        16: "TenActivity",
        45: "TwoActivity",
        46: "SixActivity",
        47: "ThreeActivity",
        48: "OneActivity",
        49: "FiveActivity",
        50: "FourActivity",
        51: "EightActivity",
        52: "NineActivity",
        53: "TwoActivity1",
        54: "TwelveActivity",
        55: "ElevenActivity",
    }
    assert protocol.APP_MODEL_IDS[JEROMES] == frozenset(range(45, 54))
    assert protocol.APP_MODEL_IDS[SLUMBER] == protocol.APP_MODEL_IDS[BRICK]
    assert protocol.APP_LED_SETTINGS_MODEL_IDS[SLUMBER] == {46, 49, 50, 51, 52, 53, 54, 55}
    assert protocol.APP_LED_SETTINGS_MODEL_IDS[JEROMES] == frozenset()
    assert {protocol.app_for_variant(v) for v in REMACRO_VARIANTS} == {SLUMBER, BRICK, JEROMES}
    assert protocol.app_for_variant(None) == SLUMBER


def test_model_selection_uses_lowest_company_id() -> None:
    assert protocol.resolve_model(SLUMBER, {55: b"", 14: b"\x01"}, None).model_id == 14
    assert protocol.resolve_model(JEROMES, None, 47).model_id == 47
    # The advertisement wins over the stored selector, as in the apps.
    assert protocol.resolve_model(SLUMBER, {50: b""}, 47).model_id == 50
    with pytest.raises(ValueError, match="Jerome's"):
        protocol.resolve_model(JEROMES, {54: b""}, None)
    with pytest.raises(ValueError, match="company ID 13"):
        protocol.resolve_model(SLUMBER, {13: b"", 50: b""}, None)
    with pytest.raises(ValueError, match="unknown"):
        protocol.resolve_model(SLUMBER, {}, True)
    assert protocol.add_remacro_model({"a": 1}, {52: b""}) == {"a": 1, CONF_REMACRO_MODEL: 52}
    # An unmapped ID is remembered too, so it stays refused without history.
    assert protocol.add_remacro_model({"a": 1}, {99: b""}) == {"a": 1, CONF_REMACRO_MODEL: 99}
    assert protocol.add_remacro_model({"a": 1}, {}) == {"a": 1}


def test_bed_needs_no_pairing() -> None:
    assert BED_TYPE_REMACRO not in BEDS_REQUIRING_PAIRING


# -----------------------------------------------------------------------------
# Controller behavior with a virtual clock
# -----------------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    @property
    def ms(self) -> int:
        return round(self.now * 1000)


def make_controller(
    app: protocol.RemacroApp,
    model_id: int,
    *,
    pulse: tuple[int, int] = (10, 25),
    led_level: int | None = None,
    session: protocol.RemacroSession | None = None,
) -> tuple[RemacroController, Clock, list[tuple[int, str]]]:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count, coordinator.motor_pulse_delay_ms = pulse
    coordinator.controller_state = {}
    coordinator.handle_controller_state_updates.side_effect = coordinator.controller_state.update
    coordinator.handle_controller_state_update.side_effect = lambda key, value: (
        coordinator.controller_state.update({key: value})
    )
    clock = Clock()
    writes: list[tuple[int, str]] = []

    async def write(char, data, response):
        assert char == REMACRO_WRITE_CHAR_UUID
        assert response is False  # WRITE_TYPE_NO_RESPONSE in every app
        writes.append((clock.ms, bytes(data).hex(" ")))

    coordinator.client = MagicMock(is_connected=True, services=[])
    coordinator.client.write_gatt_char = AsyncMock(side_effect=write)
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    controller = RemacroController(
        coordinator,
        app=app,
        model=protocol.MODELS[model_id],
        led_level=led_level,
        session=session,
    )

    async def sleep(seconds: float) -> None:
        clock.now += max(seconds, 0)

    async def pause(seconds: float, cancel_event: asyncio.Event) -> bool:
        if cancel_event.is_set():
            return True
        clock.now += max(seconds, 0)
        return False

    controller._sleep = sleep  # type: ignore[method-assign]
    controller._pause = pause  # type: ignore[method-assign]
    return controller, clock, writes


async def test_default_movement_sends_once_and_stops_120ms_after_release() -> None:
    controller, _, writes = make_controller(SLUMBER, 49)
    await controller.move_back_up()
    assert writes == [(0, "02 01 01 01 00 00 00 00"), (370, "03 01 00 01 00 00 00 00")]


@pytest.mark.parametrize("app", [SLUMBER, BRICK, JEROMES])
async def test_one_activity_individual_release_stops_three_times(app) -> None:
    controller, _, writes = make_controller(app, 48)
    await controller.move_lumbar_down()
    assert [(t, frame[6:11]) for t, frame in writes] == [
        (0, "0a 01"),
        (250, "08 01"),
        (370, "08 01"),
        (490, "08 01"),
    ]


async def test_one_activity_combined_streams_in_slumberland() -> None:
    controller, _, writes = make_controller(SLUMBER, 48)
    await controller.move_all_down()
    assert writes == [
        (0, "02 01 11 01 00 00 00 00"),
        (100, "03 01 11 01 00 00 00 00"),
        (200, "04 01 11 01 00 00 00 00"),
        (250, "05 01 01 00 00 00 00 00"),
        (270, "06 01 01 00 00 00 00 00"),
        (290, "07 01 01 00 00 00 00 00"),
    ]


async def test_one_activity_combined_repeats_cached_serial_in_jeromes() -> None:
    controller, _, writes = make_controller(JEROMES, 48)
    await controller.move_all_down()
    assert [(t, frame[:2]) for t, frame in writes] == [
        (0, "02"),
        (100, "02"),
        (200, "02"),
        (250, "03"),
        (270, "03"),
        (290, "03"),
    ]


async def test_one_activity_combined_is_single_shot_in_the_brick() -> None:
    controller, _, writes = make_controller(BRICK, 48)
    await controller.move_all_down()
    assert writes == [(0, "02 01 11 01 00 00 00 00"), (370, "03 01 01 00 00 00 00 00")]


async def test_cancelled_movement_still_sends_release_stop() -> None:
    controller, _, writes = make_controller(SLUMBER, 45)

    async def cancelled_pause(seconds: float, cancel_event: asyncio.Event) -> bool:
        cancel_event.set()
        return True

    controller._pause = cancelled_pause  # type: ignore[method-assign]
    await controller.move_legs_up()
    assert writes == [(0, "02 01 05 01 00 00 00 00"), (120, "03 01 04 01 00 00 00 00")]


async def test_split_screen_side_selector_routes_side_codes() -> None:
    controller, _, writes = make_controller(SLUMBER, 51)
    assert controller.control_side == "left"
    await controller.move_back_up()
    await controller.set_control_side("right")
    assert controller._coordinator.controller_state["remacro_control_side"] == "right"
    await controller.move_back_up()
    await controller.move_legs_down()
    await controller.move_all_up()
    codes = [frame[6:11] for _, frame in writes]
    assert codes == [
        "01 64",
        "00 64",  # left head
        "04 64",
        "03 64",  # right head
        "0e 64",
        "0c 64",  # shared foot
        "56 64",
        "55 64",  # right combined
    ]
    with pytest.raises(ValueError):
        await controller.set_control_side("both")


async def test_side_selector_only_on_split_screens() -> None:
    split, _, _ = make_controller(SLUMBER, 52)
    simple, _, _ = make_controller(SLUMBER, 50)
    assert [spec.options for spec in split.controller_select_specs] == [("left", "right")]
    assert simple.controller_select_specs == ()
    with pytest.raises(ValueError):
        await simple.set_control_side("right")


async def test_preset_second_tap_stops_and_flat_is_combined_down() -> None:
    controller, _, writes = make_controller(SLUMBER, 49)
    await controller.preset_zero_g()
    await controller.preset_zero_g()
    await controller.preset_tv()
    await controller.preset_anti_snore()
    await controller.preset_flat()
    assert [frame for _, frame in writes] == [
        "02 01 03 03 00 00 00 00",
        "03 01 01 00 00 00 00 00",
        "04 01 02 03 00 00 00 00",
        "05 01 01 03 00 00 00 00",
        "06 01 11 01 00 00 00 00",
    ]


async def test_jeromes_taps_use_capture_then_increment() -> None:
    controller, _, writes = make_controller(JEROMES, 46)
    await controller.preset_flat()
    await controller.preset_memory(2)
    await controller.lights_on()
    assert [frame for _, frame in writes] == [
        "01 01 11 01 00 00 00 00",
        "02 01 13 03 00 00 00 00",
        "03 01 01 05 00 00 00 00",
    ]


async def test_split_presets_memory_and_global_stop() -> None:
    controller, _, writes = make_controller(SLUMBER, 51)
    await controller.set_control_side("right")
    await controller.preset_tv()
    await controller.preset_memory(2)
    await controller.program_memory(1)
    await controller.stop_all()
    assert [frame[6:11] for _, frame in writes] == ["22 65", "39 65", "48 65", "01 00"]


async def test_nine_activity_defines_no_global_stop() -> None:
    controller, _, writes = make_controller(SLUMBER, 52)
    assert controller.supports_stop_all is False
    await controller.stop_all()
    assert writes == []
    assert make_controller(SLUMBER, 51)[0].supports_stop_all is True


async def test_memory_slots_follow_the_screen() -> None:
    controller, _, writes = make_controller(SLUMBER, 55)
    assert controller.memory_slot_count == 1
    await controller.preset_memory(1)
    await controller.program_memory(1)
    assert [frame[6:11] for _, frame in writes] == ["11 03", "10 03"]
    with pytest.raises(ValueError):
        await controller.preset_memory(2)
    plain, _, _ = make_controller(SLUMBER, 45)
    with pytest.raises(ValueError):
        await plain.program_memory(1)


@pytest.mark.parametrize(
    ("app", "head", "foot"),
    [
        # Reconciliation decisive sequence: wave, then three taps.
        (SLUMBER, "05 01 20 02 00 00 00 00", "05 01 28 02 00 00 00 00"),
        (BRICK, "05 01 20 02 00 00 00 00", "05 01 28 02 00 00 00 00"),
        (JEROMES, "04 01 23 01 00 00 00 00", "04 01 24 01 00 00 00 00"),
    ],
)
async def test_wave_mode_zone_wrap_matches_each_app(app, head, foot) -> None:
    for toggle, expected in (("massage_head_toggle", head), ("massage_foot_toggle", foot)):
        controller, _, writes = make_controller(app, 47)
        await controller.massage_mode_step()
        for _ in range(3):
            await getattr(controller, toggle)()
        assert writes[-1][1] == expected


async def test_massage_cycle_without_wave_and_wave_button_cycle() -> None:
    controller, _, writes = make_controller(SLUMBER, 50)
    for _ in range(4):
        await controller.massage_head_toggle()
    for _ in range(3):
        await controller.massage_mode_step()
    assert [frame[6:11] for _, frame in writes] == [
        "01 02",
        "02 02",
        "03 02",
        "23 01",
        "30 02",
        "31 02",
        "00 02",
    ]


async def test_nine_right_side_massage_keeps_literal_2401_and_shared_counters() -> None:
    controller, _, writes = make_controller(SLUMBER, 52)
    await controller.massage_mode_step()  # left wave 1
    await controller.set_control_side("right")
    await controller.massage_head_toggle()  # shared counter: 1 -> 2
    await controller.massage_mode_step()  # right wave 2
    await controller.massage_mode_step()  # right wave off
    await controller.set_control_side("left")
    await controller.massage_mode_step()  # left wave 1
    await controller.massage_mode_step()
    await controller.massage_mode_step()  # left wave off
    assert [frame[6:11] for _, frame in writes] == [
        "30 02",
        "01 24",
        "51 02",
        "53 02",
        "30 02",
        "31 02",
        "33 02",
    ]


async def test_slumberland_never_sends_zone_off_while_a_wave_runs() -> None:
    controller, _, writes = make_controller(SLUMBER, 54)
    await controller.massage_mode_step()
    for _ in range(9):
        await controller.massage_foot_toggle()
    assert "24 01" not in {frame[6:11] for _, frame in writes}


async def test_light_toggle_frames_and_capability() -> None:
    controller, _, writes = make_controller(SLUMBER, 47)
    await controller.lights_on()
    await controller.lights_off()
    assert [frame for _, frame in writes] == ["02 01 01 05 00 00 00 00", "03 01 00 05 00 00 00 00"]
    dark, _, _ = make_controller(SLUMBER, 48)
    assert dark.supports_lights is False
    with pytest.raises(NotImplementedError):
        await dark.lights_on()


async def test_led_brightness_preview_and_save_timing() -> None:
    controller, _, writes = make_controller(BRICK, 53)
    await controller.save_led_brightness()  # Preference default 255 before any change.
    await controller.set_led_brightness(0)
    await controller.save_led_brightness()
    assert writes == [
        (500, "01 01 0f 05 ff ff ff ff"),
        (650, "02 01 01 05 00 ff ff ff"),
        (1150, "03 01 0f 05 00 ff ff ff"),
    ]
    assert controller._coordinator.controller_state["remacro_led_brightness"] == 0
    # Each commit persists the slider value, like the app's "LV" preference.
    remember = controller._coordinator.remember_remacro_led_level
    assert [call.args for call in remember.call_args_list] == [(53, 255), (53, 0)]
    with pytest.raises(ValueError):
        await controller.set_led_brightness(256)


async def test_led_level_restores_the_committed_value() -> None:
    controller, _, writes = make_controller(SLUMBER, 50, led_level=64)
    assert controller._coordinator.controller_state["remacro_led_brightness"] == 64
    await controller.save_led_brightness()
    assert writes == [(500, "01 01 0f 05 40 ff ff ff")]


@pytest.mark.parametrize(("app", "model_id"), [(SLUMBER, 47), (JEROMES, 50), (SLUMBER, 14)])
async def test_led_setting_hidden_where_the_app_hides_it(app, model_id) -> None:
    controller, _, _ = make_controller(app, model_id)
    assert controller.controller_number_specs == ()
    assert controller.controller_button_specs == ()
    with pytest.raises(NotImplementedError):
        await controller.set_led_brightness(10)


@pytest.mark.parametrize(
    ("model_id", "motors", "memory", "presets", "massage", "light"),
    [
        (14, ["all_motors"], 0, False, False, False),
        (45, ["back", "legs", "all_motors"], 0, False, False, False),
        (46, ["back", "legs", "all_motors"], 2, True, False, True),
        (47, ["back", "legs", "all_motors"], 2, False, True, True),
        (48, ["back", "lumbar", "legs", "all_motors"], 0, False, False, False),
        (49, ["back", "lumbar", "legs", "all_motors"], 2, True, False, True),
        (50, ["back", "lumbar", "legs", "all_motors"], 2, False, True, True),
        (51, ["back", "lumbar", "legs", "all_motors"], 2, True, False, True),
        (52, ["back", "lumbar", "legs", "all_motors"], 2, False, True, True),
        (53, ["back", "legs", "all_motors"], 0, False, False, False),
        (54, ["back", "lumbar", "legs"], 1, True, True, True),
        (55, ["back", "legs", "all_motors"], 1, True, True, True),
    ],
)
def test_capabilities_match_each_screen(model_id, motors, memory, presets, massage, light) -> None:
    controller, _, _ = make_controller(SLUMBER, model_id)
    assert [spec.key for spec in controller.motor_control_specs] == motors
    assert controller.memory_slot_count == memory
    assert controller.supports_memory_programming is bool(memory)
    assert controller.supports_preset_flat is True
    assert controller.supports_preset_zero_g is presets
    assert controller.supports_preset_anti_snore is presets
    assert controller.supports_preset_tv is presets
    assert controller.supports_massage is massage
    assert controller.auto_enable_massage is massage
    assert controller.supports_head_massage_toggle_control is massage
    assert controller.supports_massage_mode_step_control is massage
    assert controller.supports_lights is light
    assert controller.supports_discrete_light_control is light
    assert controller.supports_light_color_control is False
    assert controller.has_tilt_support is False
    assert controller.supports_position_feedback is False


async def test_unsupported_controls_raise_without_writing() -> None:
    controller, _, writes = make_controller(SLUMBER, 14)
    with pytest.raises(NotImplementedError):
        await controller.move_back_up()
    with pytest.raises(NotImplementedError):
        await controller.preset_zero_g()
    with pytest.raises(NotImplementedError):
        await controller.massage_head_toggle()
    assert writes == []


async def test_notifications_subscribe_without_writes_or_state() -> None:
    controller, _, writes = make_controller(SLUMBER, 50)
    assert controller.requires_notification_channel is True
    await controller.start_notify()
    controller.client.start_notify.assert_awaited_once()
    assert controller.client.start_notify.await_args.args[0] == REMACRO_READ_CHAR_UUID
    handler = controller.client.start_notify.await_args.args[1]
    handler(None, bytearray.fromhex("0187040000000000"))
    assert writes == []
    assert set(controller._coordinator.controller_state) == {"remacro_led_brightness"}
    await controller.stop_notify()
    controller.client.stop_notify.assert_awaited_once_with(REMACRO_READ_CHAR_UUID)


def test_protocol_diagnostics_names_profile() -> None:
    controller, _, _ = make_controller(JEROMES, 52)
    assert controller.protocol_diagnostics == {
        "remacro_app": JEROMES,
        "remacro_model_id": 52,
        "remacro_model": "CS-B500YM",
        "remacro_screen": "NineActivity",
        "remacro_control_side": "left",
    }


async def test_factory_resolves_app_and_model() -> None:
    async def run_import(func, *args):
        return func(*args)

    coordinator = MagicMock()
    coordinator.hass = SimpleNamespace(async_add_import_executor_job=run_import, data={})
    coordinator.address = "aa:bb:cc:dd:ee:ff"
    coordinator.entry = SimpleNamespace(data={CONF_REMACRO_MODEL: 46})
    coordinator.cancel_command = asyncio.Event()
    live = await create_controller(
        coordinator, BED_TYPE_REMACRO, "the_brick", None, manufacturer_data={51: b"", 60: b""}
    )
    offline = await create_controller(coordinator, BED_TYPE_REMACRO, "auto", None)
    assert isinstance(live, RemacroController)
    assert isinstance(offline, RemacroController)
    assert (live.app, live.model.model_id) == (BRICK, 51)
    assert (offline.app, offline.model.model_id) == (SLUMBER, 46)

    # A rebuild (handoff or reconnect) keeps every app field in the session.
    await live.set_control_side("right")
    live._serial.hold(0x0101)
    live._session.active_preset = "tv"
    live._session.head_level = 2
    coordinator.entry.data[CONF_REMACRO_LED_LEVEL] = {"51": 9, "46": 7}
    again = await create_controller(
        coordinator, BED_TYPE_REMACRO, "the_brick", None, manufacturer_data={51: b""}
    )
    assert isinstance(again, RemacroController)
    assert again.control_side == "right"
    assert again._serial.hold(0x0100)[0] == 3
    session = again._session
    assert (session.active_preset, session.head_level, session.led_brightness) == ("tv", 2, 255)
    assert session in coordinator.hass.data[DOMAIN]["app_sessions"]["AA:BB:CC:DD:EE:FF"].values()
    other_app = await create_controller(
        coordinator, BED_TYPE_REMACRO, "jeromes", None, manufacturer_data={51: b""}
    )
    assert isinstance(other_app, RemacroController)
    assert other_app.control_side == "left"
    # "LV" is keyed by model: a model without a committed level starts at 255.
    coordinator.entry.data[CONF_REMACRO_LED_LEVEL] = {"46": 7, "50": 33}
    seeded = await create_controller(
        coordinator, BED_TYPE_REMACRO, "the_brick", None, manufacturer_data={50: b""}
    )
    changed = await create_controller(
        coordinator, BED_TYPE_REMACRO, "the_brick", None, manufacturer_data={52: b""}
    )
    assert isinstance(seeded, RemacroController) and isinstance(changed, RemacroController)
    assert (seeded._led_level, changed._led_level) == (33, 255)


# -----------------------------------------------------------------------------
# Home Assistant entity surface
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_id", "present", "absent"),
    [
        (51, [("button", "preset_zero_g")], [("button", "massage_head_toggle")]),
        (
            52,
            [("button", "massage_head_toggle"), ("button", "massage_mode_step")],
            [("button", "preset_zero_g")],
        ),
    ],
)
async def test_entities_follow_the_advertised_model(
    hass: HomeAssistant,
    mock_coordinator_connected,
    enable_custom_integrations,
    model_id,
    present,
    absent,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Remacro Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
            CONF_NAME: "Remacro Bed",
            CONF_BED_TYPE: BED_TYPE_REMACRO,
            CONF_PROTOCOL_VARIANT: "slumberland",
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:51",
    )
    entry.add_to_hass(hass)
    advert = MagicMock(manufacturer_data={model_id: b""})
    with patch(
        "custom_components.adjustable_bed.coordinator.bluetooth.async_last_service_info",
        return_value=advert,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.data[CONF_REMACRO_MODEL] == model_id
    registry = er.async_get(hass)
    unique_ids = {
        (row.domain, row.unique_id.removeprefix("AA:BB:CC:DD:EE:51_"))
        for row in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    for expected in (
        ("cover", "back"),
        ("cover", "lumbar"),
        ("cover", "legs"),
        ("cover", "all_motors"),
        ("select", "controller_select_remacro_control_side"),
        ("number", "controller_number_remacro_led_brightness"),
        ("button", "remacro_led_brightness_save"),
        ("switch", "under_bed_lights"),
        ("button", "program_memory_2"),
        *present,
    ):
        assert expected in unique_ids, expected
    for missing in absent:
        assert missing not in unique_ids, missing
    assert ("cover", "tilt") not in unique_ids
    assert ("button", "preset_memory_3") not in unique_ids
    assert ("light", "under_bed_lights") not in unique_ids
    await hass.config_entries.async_unload(entry.entry_id)


# -----------------------------------------------------------------------------
# Setup, config flow and options validation
# -----------------------------------------------------------------------------

_HISTORY = "homeassistant.components.bluetooth.async_last_service_info"


def _remacro_entry(hass: HomeAssistant, address: str, **data) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Remacro Bed",
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Remacro Bed",
            CONF_BED_TYPE: BED_TYPE_REMACRO,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            **data,
        },
        unique_id=address,
    )
    entry.add_to_hass(hass)
    return entry


async def test_existing_entry_without_model_waits_before_connecting(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_establish_connection,
    enable_custom_integrations,
) -> None:
    entry = _remacro_entry(hass, "AA:BB:CC:DD:EE:60")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.reason is not None and "model is unknown" in entry.reason
    mock_establish_connection.assert_not_awaited()


@pytest.mark.parametrize(
    ("variant", "company_id", "reason"),
    [("slumberland", 13, "none of the"), ("jeromes", 54, "Jerome's app does not list")],
)
async def test_unlisted_model_fails_setup_without_a_reconnect_loop(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_establish_connection,
    enable_custom_integrations,
    variant,
    company_id,
    reason,
) -> None:
    entry = _remacro_entry(hass, "AA:BB:CC:DD:EE:61", **{CONF_PROTOCOL_VARIANT: variant})
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={company_id: b""})):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.reason is not None and reason in entry.reason
    mock_establish_connection.assert_not_awaited()


async def test_model_cache_falls_back_to_non_connectable_history(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    entry = _remacro_entry(hass, "AA:BB:CC:DD:EE:62")
    adverts = {True: None, False: MagicMock(manufacturer_data={47: b""})}
    with patch(_HISTORY, side_effect=lambda _hass, _address, connectable: adverts[connectable]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.data[CONF_REMACRO_MODEL] == 47
    await hass.config_entries.async_unload(entry.entry_id)


async def test_legacy_entities_are_removed_or_kept_on_upgrade(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    address = "AA:BB:CC:DD:EE:63"
    entry = _remacro_entry(hass, address)
    registry = er.async_get(hass)
    # The previous generic controller's surface: back/legs/lumbar/tilt covers,
    # an RGB light, four memories, LED-white toggle and massage toggles.
    legacy = {
        ("cover", "back"),
        ("cover", "legs"),
        ("cover", "lumbar"),
        ("cover", "tilt"),
        ("cover", "head"),
        ("cover", "feet"),
        ("light", "under_bed_lights"),
        ("switch", "under_bed_lights"),
        ("button", "preset_memory_3"),
        ("button", "preset_memory_4"),
        ("button", "program_memory_3"),
        ("button", "preset_anti_snore"),
        ("button", "toggle_light"),
        ("button", "massage_all_toggle"),
        ("button", "massage_head_toggle"),
    }
    entity_ids = {
        key: registry.async_get_or_create(
            key[0], DOMAIN, f"{address}_{key[1]}", config_entry=entry
        ).entity_id
        for key in legacy
    }
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={45: b""})):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    remaining = {
        (row.domain, row.unique_id.removeprefix(f"{address}_"))
        for row in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    # CS-B200 (TwoActivity): head and foot keep their unique IDs and entity IDs.
    assert registry.async_get(entity_ids[("cover", "back")]) is not None
    assert registry.async_get(entity_ids[("cover", "legs")]) is not None
    assert ("cover", "all_motors") in remaining
    assert not (legacy - {("cover", "back"), ("cover", "legs")}) & remaining
    await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_refuses_models_the_app_does_not_list(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.flow_id = "remacro"
    flow.handler = DOMAIN
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:64", CONF_BED_TYPE: BED_TYPE_REMACRO}
    with patch(_HISTORY, return_value=None):
        unmapped = flow._remacro_unsupported_abort(data, manufacturer_data={13: b""})
        not_listed = flow._remacro_unsupported_abort(
            {**data, CONF_PROTOCOL_VARIANT: "jeromes"}, manufacturer_data={55: b""}
        )
        field_error = flow._remacro_variant_error(
            BED_TYPE_REMACRO, "jeromes", data[CONF_ADDRESS], {55: b""}
        )
        unknown = flow._remacro_unsupported_abort(data, manufacturer_data={})
        listed = flow._remacro_unsupported_abort(data, manufacturer_data={55: b""})
    assert unmapped is not None and unmapped["type"] is FlowResultType.ABORT
    assert unmapped["reason"] == "remacro_model_unmapped"
    # A model another app lists is a field error on the form choosing the app.
    assert not_listed is None
    assert field_error == "remacro_model_not_in_app"
    assert unmapped["description_placeholders"] == {"company_id": "13", "app": "Slumberland"}
    assert unknown is None and listed is None
    # An empty discovery map falls back to the non-connectable history.
    adverts = {True: None, False: MagicMock(manufacturer_data={52: b""})}
    with patch(_HISTORY, side_effect=lambda _hass, _address, connectable: adverts[connectable]):
        cached = flow._maybe_add_advertisement_metadata(data, manufacturer_data={})
    assert cached[CONF_REMACRO_MODEL] == 52


async def test_options_reject_an_app_that_does_not_list_the_model(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:65",
            CONF_BED_TYPE: BED_TYPE_REMACRO,
            CONF_MOTOR_COUNT: 2,
            CONF_PROTOCOL_VARIANT: "slumberland",
            CONF_REMACRO_MODEL: 54,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    with patch(_HISTORY, return_value=None):
        result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: "jeromes"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "remacro_model_not_in_app"}
    assert entry.data[CONF_PROTOCOL_VARIANT] == "slumberland"


async def test_paired_sides_cache_their_own_model(hass: HomeAssistant) -> None:
    from custom_components.adjustable_bed import _maybe_cache_paired_remacro_models
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN

    left, right = "AA:BB:CC:DD:EE:66", "AA:BB:CC:DD:EE:67"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_REMACRO,
            CONF_PAIR_CHILDREN: [
                {"side": "left", CONF_ADDRESS: left, CONF_BED_TYPE: BED_TYPE_REMACRO},
                {"side": "right", CONF_ADDRESS: right, CONF_BED_TYPE: BED_TYPE_REMACRO},
            ],
        },
    )
    entry.add_to_hass(hass)
    adverts = {left: MagicMock(manufacturer_data={50: b""}), right: None}
    with patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]):
        _maybe_cache_paired_remacro_models(hass, entry)
    children = entry.data[CONF_PAIR_CHILDREN]
    assert children[0][CONF_REMACRO_MODEL] == 50
    assert CONF_REMACRO_MODEL not in children[1]


async def test_discovery_form_reports_an_app_that_does_not_list_the_model(
    hass: HomeAssistant, mock_bluetooth_service_info_remacro, enable_custom_integrations
) -> None:
    from homeassistant.config_entries import SOURCE_BLUETOOTH
    from homeassistant.data_entry_flow import FlowResultType

    mock_bluetooth_service_info_remacro.manufacturer_data = {55: b""}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=mock_bluetooth_service_info_remacro
    )
    assert result["step_id"] == "bluetooth_confirm"
    with patch(_HISTORY, return_value=None):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BED_TYPE: BED_TYPE_REMACRO, CONF_PROTOCOL_VARIANT: "jeromes"},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["errors"][CONF_PROTOCOL_VARIANT] == "remacro_model_not_in_app"


async def test_options_fix_reloads_a_failed_entry(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

    entry = _remacro_entry(hass, "AA:BB:CC:DD:EE:68", **{CONF_PROTOCOL_VARIANT: "jeromes"})
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={54: b""})):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_ERROR
        flow = AdjustableBedOptionsFlow(entry)
        flow.handler = entry.entry_id
        flow.hass = hass
        result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: "slumberland"})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_REMACRO_MODEL] == 54
    await hass.config_entries.async_unload(entry.entry_id)


async def test_led_level_persists_through_the_coordinator_without_reload(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    entry = _remacro_entry(hass, "AA:BB:CC:DD:EE:69")
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={50: b""})):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = hass.data[DOMAIN][entry.entry_id]
        coordinator.remember_remacro_led_level(50, 64)
        await hass.async_block_till_done()
    assert entry.data[CONF_REMACRO_LED_LEVEL] == {"50": 64}
    assert hass.data[DOMAIN][entry.entry_id] is coordinator  # No reload replaced it.
    await hass.config_entries.async_unload(entry.entry_id)


def _remacro_pair(hass: HomeAssistant, left_model: int | None, right_model: int | None):
    from custom_components.adjustable_bed import _build_paired_children
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_CHILDREN,
        CONF_PAIR_ID,
        CONF_PAIR_MEMBER_ADDRESSES,
        CONF_PAIR_MODE,
        CONF_PAIR_SCHEMA_VERSION,
        CONF_SIDE,
        PAIR_MODE_SEPARATE_ADDRESS,
    )

    def child(side: str, address: str, model: int | None) -> dict:
        data = {
            CONF_SIDE: side,
            CONF_ADDRESS: address,
            CONF_NAME: side.capitalize(),
            CONF_BED_TYPE: BED_TYPE_REMACRO,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        }
        if model is not None:
            data[CONF_REMACRO_MODEL] = model
        return data

    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Remacro Pair",
        data={
            CONF_PAIR_ID: "pair_remacro",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_SCHEMA_VERSION: 1,
            CONF_BED_TYPE: BED_TYPE_REMACRO,
            CONF_NAME: "Remacro Pair",
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_PAIR_MEMBER_ADDRESSES: [left, right],
            CONF_PAIR_CHILDREN: [
                child("left", left, left_model),
                child("right", right, right_model),
            ],
        },
        unique_id="pair_remacro",
        version=4,
    )
    entry.add_to_hass(hass)
    return entry, _build_paired_children(hass, entry)


async def test_paired_side_with_unlisted_model_does_not_connect(
    hass: HomeAssistant, mock_coordinator_connected, mock_establish_connection
) -> None:
    from homeassistant.helpers import issue_registry as ir

    _entry, children = _remacro_pair(hass, None, None)
    adverts = {
        "AA:BB:CC:DD:EE:71": MagicMock(manufacturer_data={50: b""}),
        "AA:BB:CC:DD:EE:72": MagicMock(manufacturer_data={13: b""}),
    }
    with patch(
        "custom_components.adjustable_bed.remacro_discovery.bluetooth.async_last_service_info",
        side_effect=lambda _hass, address, connectable: adverts[address],
    ):
        assert await children["right"].async_connect() is False
        mock_establish_connection.assert_not_awaited()
        assert await children["left"].async_connect() is True
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:72")
    assert issue is not None and issue.translation_key == "remacro_model_unmapped"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:71") is None
    await children["left"].async_disconnect()


async def test_paired_side_led_level_persists_to_its_descriptor(hass: HomeAssistant) -> None:
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN

    entry, children = _remacro_pair(hass, 50, 52)
    children["right"].remember_remacro_led_level(52, 12)
    await hass.async_block_till_done()
    descriptors = {child["side"]: child for child in entry.data[CONF_PAIR_CHILDREN]}
    assert descriptors["right"][CONF_REMACRO_LED_LEVEL] == {"52": 12}
    assert CONF_REMACRO_LED_LEVEL not in descriptors["left"]


async def test_paired_offline_minting_needs_a_stored_model(hass: HomeAssistant) -> None:
    _entry, children = _remacro_pair(hass, 51, None)
    await children["left"].async_prime_offline_controller()
    await children["right"].async_prime_offline_controller()
    minted = children["left"].capability_controller
    assert isinstance(minted, RemacroController) and minted.model.model_id == 51
    assert children["right"].capability_controller is None


@pytest.mark.parametrize("app", [SLUMBER, JEROMES])
async def test_app_state_survives_controller_rebuilds(app) -> None:
    """Disconnect After Command rebuilds the controller after every action."""
    session = protocol.RemacroSession(protocol.SynDataSerial(cache_hold_serial=app == JEROMES))
    frames: list[str] = []
    for action in ("massage_head_toggle", "massage_head_toggle", "massage_mode_step"):
        controller, _, writes = make_controller(app, 50, session=session)
        await getattr(controller, action)()
        frames += [frame for _, frame in writes]
    assert [frame[6:11] for frame in frames] == ["01 02", "02 02", "30 02"]

    preset_session = protocol.RemacroSession(protocol.SynDataSerial(cache_hold_serial=False))
    codes = []
    for _ in range(2):
        controller, _, writes = make_controller(SLUMBER, 49, session=preset_session)
        await controller.preset_zero_g()
        codes += [frame[6:11] for _, frame in writes]
    assert codes == ["03 03", "01 00"]  # The re-press after a rebuild still stops.

    led_session = protocol.RemacroSession(protocol.SynDataSerial(cache_hold_serial=False))
    controller, _, _ = make_controller(SLUMBER, 50, session=led_session, led_level=200)
    await controller.set_led_brightness(10)
    controller, _, writes = make_controller(SLUMBER, 50, session=led_session, led_level=200)
    await controller.save_led_brightness()
    assert writes[-1][1][6:] == "0f 05 0a ff ff ff"  # The slider value, not the stored 200.
    controller._coordinator.remember_remacro_led_level.assert_called_once_with(50, 10)


async def test_session_outlives_unload_until_no_entry_owns_the_bed(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    address = "AA:BB:CC:DD:EE:70"
    entry = _remacro_entry(hass, address)
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={50: b""})):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    sessions = hass.data[DOMAIN]["app_sessions"]
    await hass.config_entries.async_unload(entry.entry_id)
    # Unpair unloads the pair before its restored entries exist; the state stays.
    assert sessions.get(address)
    restored = _remacro_entry(hass, address)
    await hass.config_entries.async_remove(entry.entry_id)
    assert sessions.get(address)
    await hass.config_entries.async_remove(restored.entry_id)
    assert not sessions.get(address)


async def test_unchanged_pair_app_validates_each_side_against_its_own_app(
    hass: HomeAssistant,
) -> None:
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN

    entry, _children = _remacro_pair(hass, 45, 55)
    children = [dict(child) for child in entry.data[CONF_PAIR_CHILDREN]]
    children[0][CONF_PROTOCOL_VARIANT], children[1][CONF_PROTOCOL_VARIANT] = (
        "jeromes",
        "slumberland",
    )
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_PROTOCOL_VARIANT: "jeromes", CONF_PAIR_CHILDREN: children},
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    adverts = {
        "AA:BB:CC:DD:EE:71": MagicMock(manufacturer_data={45: b""}),
        "AA:BB:CC:DD:EE:72": MagicMock(manufacturer_data={55: b""}),
    }
    with patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]):
        result = await flow.async_step_settings({})
    assert not (result["type"] is FlowResultType.FORM and result.get("errors"))


@pytest.mark.parametrize("variants", [("the_brick", "jeromes"), ("jeromes", "jeromes")])
async def test_combined_options_refuse_any_app_change(hass: HomeAssistant, variants) -> None:
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN

    entry, _children = _remacro_pair(hass, 50, 50)
    children = [dict(child) for child in entry.data[CONF_PAIR_CHILDREN]]
    children[0][CONF_PROTOCOL_VARIANT], children[1][CONF_PROTOCOL_VARIANT] = variants
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_PAIR_CHILDREN: children})
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    with patch(_HISTORY, return_value=None):
        result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: "slumberland"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "remacro_app_unpair_first"}
    stored = [child[CONF_PROTOCOL_VARIANT] for child in entry.data[CONF_PAIR_CHILDREN]]
    assert stored == list(variants)


async def test_removing_an_entry_clears_its_remacro_issues(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    from homeassistant.helpers import issue_registry as ir

    from custom_components.adjustable_bed.remacro_discovery import update_remacro_model_issue

    pair, _children = _remacro_pair(hass, 50, 50)
    standalone = _remacro_entry(hass, "AA:BB:CC:DD:EE:73")
    # A restored single for the left side owns that address after unpair.
    restored = _remacro_entry(hass, "AA:BB:CC:DD:EE:71")
    for address in ("AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72", "AA:BB:CC:DD:EE:73"):
        update_remacro_model_issue(
            hass, address, "Bed", "unmapped", {"company_id": "13", "app": "Slumberland"}
        )
    issues = ir.async_get(hass)
    await hass.config_entries.async_remove(pair.entry_id)
    await hass.config_entries.async_remove(standalone.entry_id)
    assert issues.async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:72") is None
    assert issues.async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:73") is None
    assert issues.async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:71") is not None
    await hass.config_entries.async_remove(restored.entry_id)
    assert issues.async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:71") is None


async def test_pair_loads_when_one_side_has_an_unmapped_model(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    from homeassistant.helpers import issue_registry as ir

    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry, _children = _remacro_pair(hass, 50, 50)
    registry = er.async_get(hass)
    for address in (left, right):
        registry.async_get_or_create("cover", DOMAIN, f"{address}_back", config_entry=entry)
    adverts = {
        left: MagicMock(manufacturer_data={50: b""}),
        right: MagicMock(manufacturer_data={13: b""}),
    }
    with patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        good = registry.async_get_entity_id("cover", DOMAIN, f"{left}_back")
        assert good is not None
        state = hass.states.get(good)
        assert state is not None and state.state != "unavailable"
        assert registry.async_get_entity_id("cover", DOMAIN, f"{right}_back") is None
        issues = ir.async_get(hass)
        assert issues.async_get_issue(DOMAIN, f"remacro_model_{right}") is not None
        assert issues.async_get_issue(DOMAIN, f"remacro_model_{left}") is None
        await hass.config_entries.async_unload(entry.entry_id)


def _absorbing_pair(hass: HomeAssistant):
    """A pair whose sides still have their original standalone entries."""
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN
    from custom_components.adjustable_bed.pairing import KEY_ABSORBED_ENTRY_ID

    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    registry = er.async_get(hass)
    originals = {}
    for address in (left, right):
        single = _remacro_entry(hass, address, **{CONF_REMACRO_MODEL: 50})
        for domain, key in (("cover", "back"), ("button", "preset_flat")):
            registry.async_get_or_create(domain, DOMAIN, f"{address}_{key}", config_entry=single)
        originals[address] = single
    entry, _children = _remacro_pair(hass, 50, 50)
    children = [dict(child) for child in entry.data[CONF_PAIR_CHILDREN]]
    for child in children:
        child[KEY_ABSORBED_ENTRY_ID] = originals[child[CONF_ADDRESS]].entry_id
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_PAIR_CHILDREN: children})
    adverts = {
        left: MagicMock(manufacturer_data={50: b""}),
        right: MagicMock(manufacturer_data={13: b""}),
    }
    history = patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address])
    return entry, originals, left, right, history


async def test_absorbing_a_refused_side_leaves_no_stale_controls(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    entry, originals, left, right, history = _absorbing_pair(hass)
    registry = er.async_get(hass)
    good_cover = registry.async_get_entity_id("cover", DOMAIN, f"{left}_back")
    with history:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert all(
            hass.config_entries.async_get_entry(o.entry_id) is None for o in originals.values()
        )
        # The good side keeps its entity ID, now owned by the pair.
        row = registry.async_get(good_cover)
        assert row is not None and row.config_entry_id == entry.entry_id
        # Only the side's connection diagnostics remain; its old controls are gone.
        right_keys = {
            r.unique_id.removeprefix(f"{right}_")
            for r in registry.entities.values()
            if r.unique_id.startswith(f"{right}_")
        }
        assert right_keys <= {"ble_connection", "connect", "disconnect"}
        await hass.config_entries.async_unload(entry.entry_id)


async def test_refused_side_rollback_keeps_its_original_controls(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    entry, originals, left, right, history = _absorbing_pair(hass)
    registry = er.async_get(hass)
    refused = originals[right]
    real_remove = hass.config_entries.async_remove

    async def remove(entry_id: str):
        if entry_id == refused.entry_id:
            raise RuntimeError("simulated removal failure")
        return await real_remove(entry_id)

    with history, patch.object(hass.config_entries, "async_remove", side_effect=remove):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(refused.entry_id) is not None
    rows = [r for r in registry.entities.values() if r.unique_id.startswith(f"{right}_")]
    assert {r.unique_id.removeprefix(f"{right}_") for r in rows} == {"back", "preset_flat"}
    assert {r.config_entry_id for r in rows} == {refused.entry_id}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_leaving_remacro_clears_its_model_issues(hass: HomeAssistant) -> None:
    from homeassistant.helpers import issue_registry as ir

    from custom_components.adjustable_bed import (
        _async_prepare_remacro_entry,
        _maybe_cache_paired_remacro_models,
    )
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN
    from custom_components.adjustable_bed.remacro_discovery import update_remacro_model_issue

    placeholders = {"company_id": "13", "app": "Slumberland"}
    for address in ("AA:BB:CC:DD:EE:80", "AA:BB:CC:DD:EE:81"):
        update_remacro_model_issue(hass, address, "Bed", "unmapped", placeholders)
    standalone = _remacro_entry(hass, "AA:BB:CC:DD:EE:80", **{CONF_BED_TYPE: "linak"})
    _async_prepare_remacro_entry(hass, standalone)
    pair = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: "linak",
            CONF_PAIR_CHILDREN: [{"side": "left", CONF_ADDRESS: "AA:BB:CC:DD:EE:81"}],
        },
    )
    pair.add_to_hass(hass)
    _maybe_cache_paired_remacro_models(hass, pair)
    issues = ir.async_get(hass)
    assert issues.async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:80") is None
    assert issues.async_get_issue(DOMAIN, "remacro_model_AA:BB:CC:DD:EE:81") is None


async def test_light_switch_starts_unknown_and_side_select_needs_no_link(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_establish_connection,
    enable_custom_integrations,
) -> None:
    address = "AA:BB:CC:DD:EE:82"
    entry = _remacro_entry(hass, address)
    registry = er.async_get(hass)
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={51: b""})):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        switch = registry.async_get_entity_id("switch", DOMAIN, f"{address}_under_bed_lights")
        assert switch is not None
        state = hass.states.get(switch)
        # The bed never reports its light, so there is no definitive off.
        assert state is not None and state.state == "unknown"
        assert state.attributes.get("assumed_state") is True

        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_disconnect()
        assert not coordinator.is_connected
        mock_establish_connection.reset_mock()
        side = registry.async_get_entity_id(
            "select", DOMAIN, f"{address}_controller_select_remacro_control_side"
        )
        assert side is not None
        await hass.services.async_call(
            "select", "select_option", {"entity_id": side, "option": "right"}, blocking=True
        )
        await hass.async_block_till_done()
        mock_establish_connection.assert_not_awaited()
        assert hass.states.get(side).state == "right"
        sessions = hass.data[DOMAIN]["app_sessions"]
        assert [s.side for s in sessions[address].values()] == ["right"]
        await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("left_company", "right_company", "expected_state"),
    [
        # Both sides refused: permanent error, no retry loop.
        (13, 13, ConfigEntryState.SETUP_ERROR),
        # One usable side: the pair loads half-available.
        (50, 13, ConfigEntryState.LOADED),
        # A merely unseen side keeps setup retrying.
        (None, 13, ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_pair_setup_outcome_follows_its_sides(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_establish_connection,
    enable_custom_integrations,
    left_company,
    right_company,
    expected_state,
) -> None:
    from homeassistant.helpers import issue_registry as ir

    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry, _children = _remacro_pair(hass, None, None)
    adverts = {
        address: MagicMock(manufacturer_data={company: b""}) if company is not None else None
        for address, company in ((left, left_company), (right, right_company))
    }
    with patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is expected_state
        issues = ir.async_get(hass)
        assert issues.async_get_issue(DOMAIN, f"remacro_model_{right}") is not None
        assert (issues.async_get_issue(DOMAIN, f"remacro_model_{left}") is not None) is (
            left_company == 13
        )
        if expected_state is ConfigEntryState.SETUP_ERROR:
            assert entry.reason is not None and "No side" in entry.reason
            mock_establish_connection.assert_not_awaited()
        if expected_state is ConfigEntryState.LOADED:
            await hass.config_entries.async_unload(entry.entry_id)


async def test_absorbed_split_side_keeps_its_session_across_reconnects(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
) -> None:
    """Absorbing loaded singles must not drop the session the pair now uses."""
    from custom_components.adjustable_bed.const import CONF_PAIR_CHILDREN
    from custom_components.adjustable_bed.pairing import KEY_ABSORBED_ENTRY_ID

    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    adverts = {
        left: MagicMock(manufacturer_data={51: b""}),
        right: MagicMock(manufacturer_data={51: b""}),
    }

    async def instant_pause(self, seconds: float, cancel_event: asyncio.Event) -> bool:
        return cancel_event.is_set()

    async def instant_sleep(self, seconds: float) -> None:
        return None

    with (
        patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]),
        patch.object(RemacroController, "_pause", instant_pause),
        patch.object(RemacroController, "_sleep", instant_sleep),
    ):
        originals = {}
        for address in (left, right):
            single = _remacro_entry(hass, address)
            assert await hass.config_entries.async_setup(single.entry_id)
            await hass.async_block_till_done()
            originals[address] = single
        entry, _children = _remacro_pair(hass, 51, 51)
        children = [dict(child) for child in entry.data[CONF_PAIR_CHILDREN]]
        for child in children:
            child[KEY_ABSORBED_ENTRY_ID] = originals[child[CONF_ADDRESS]].entry_id
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_PAIR_CHILDREN: children}
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert all(
            hass.config_entries.async_get_entry(o.entry_id) is None for o in originals.values()
        )

        registry = er.async_get(hass)
        side = registry.async_get_entity_id(
            "select", DOMAIN, f"{left}_controller_select_remacro_control_side"
        )
        cover = registry.async_get_entity_id("cover", DOMAIN, f"{left}_back")
        assert side is not None and cover is not None
        await hass.services.async_call(
            "select", "select_option", {"entity_id": side, "option": "right"}, blocking=True
        )
        child = hass.data[DOMAIN][entry.entry_id].children["left"]
        await child.async_disconnect()
        assert not child.is_connected
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call("cover", "open_cover", {"entity_id": cover}, blocking=True)
        await hass.async_block_till_done()
        codes = [
            bytes(call.args[1])[2:4].hex()
            for call in mock_bleak_client.write_gatt_char.call_args_list
            if call.args[0] == REMACRO_WRITE_CHAR_UUID
        ]
        # Right head up 0x6404 and its STOP 0x6403, not the left 0x6401/0x6400.
        assert codes == ["0464", "0364"]
        await hass.config_entries.async_unload(entry.entry_id)


async def test_unmapped_model_stays_refused_after_a_restart_without_history(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_establish_connection,
    enable_custom_integrations,
) -> None:
    from homeassistant.helpers import issue_registry as ir

    address = "AA:BB:CC:DD:EE:90"
    entry = _remacro_entry(hass, address)
    with patch(_HISTORY, return_value=MagicMock(manufacturer_data={13: b""})):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.data[CONF_REMACRO_MODEL] == 13
    # Restart with the bed out of range: no history, only the stored selector.
    with patch(_HISTORY, return_value=None):
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"remacro_model_{address}") is not None
    mock_establish_connection.assert_not_awaited()


@pytest.mark.parametrize(
    ("left_company", "right_company", "stop_button"),
    [
        (52, 52, False),
        (51, 52, True),
        # A refused (controller-less) side cannot take a global STOP either.
        (52, 13, False),
        (51, 13, True),
    ],
)
async def test_paired_stop_needs_a_side_with_global_stop(
    hass: HomeAssistant,
    mock_coordinator_connected,
    enable_custom_integrations,
    left_company,
    right_company,
    stop_button,
) -> None:
    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry, _children = _remacro_pair(hass, None, None)
    adverts = {
        left: MagicMock(manufacturer_data={left_company: b""}),
        right: MagicMock(manufacturer_data={right_company: b""}),
    }
    registry = er.async_get(hass)
    with patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        stop = next(
            (
                row.entity_id
                for row in er.async_entries_for_config_entry(registry, entry.entry_id)
                if row.domain == "button" and row.unique_id.endswith("stop_both")
            ),
            None,
        )
        assert (stop is not None) is stop_button
        if stop is not None:
            children = hass.data[DOMAIN][entry.entry_id].children
            with (
                patch.object(children["left"], "async_stop_command", AsyncMock()) as left_stop,
                patch.object(children["right"], "async_stop_command", AsyncMock()) as right_stop,
                patch.object(children["right"], "request_command_cancel") as right_cancel,
            ):
                await hass.services.async_call(
                    "button", "press", {"entity_id": stop}, blocking=True
                )
            left_stop.assert_awaited_once()
            # The other side only has its running movement cancelled, never a
            # reconnect for a frame it cannot take.
            right_stop.assert_not_awaited()
            right_cancel.assert_called_once()
        await hass.config_entries.async_unload(entry.entry_id)


async def test_unseen_paired_side_gets_controls_when_it_advertises(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry, _children = _remacro_pair(hass, None, None)
    adverts = {left: MagicMock(manufacturer_data={50: b""}), right: None}
    callbacks = {}

    def register(_hass, seen, matcher, _mode):
        callbacks[matcher["address"]] = seen

        def unsubscribe() -> None:
            callbacks.pop(matcher["address"], None)

        return unsubscribe

    registry = er.async_get(hass)
    with (
        patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]),
        patch("homeassistant.components.bluetooth.async_register_callback", side_effect=register),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert registry.async_get_entity_id("cover", DOMAIN, f"{left}_back") is not None
        assert registry.async_get_entity_id("cover", DOMAIN, f"{right}_back") is None
        assert set(callbacks) == {right}

        adverts[right] = MagicMock(manufacturer_data={47: b""})
        callbacks[right](MagicMock(address=right, manufacturer_data={47: b""}), None)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert registry.async_get_entity_id("cover", DOMAIN, f"{right}_back") is not None
        assert not callbacks  # The reload no longer watches a now-known side.
        await hass.config_entries.async_unload(entry.entry_id)


async def test_unseen_side_with_legacy_controls_loads_the_pair_half_available(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry, _children = _remacro_pair(hass, 50, None)
    registry = er.async_get(hass)
    # Left over from the generic controller this pair used before upgrading.
    registry.async_get_or_create("cover", DOMAIN, f"{right}_back", config_entry=entry)
    adverts = {left: MagicMock(manufacturer_data={50: b""}), right: None}
    callbacks = {}

    def register(_hass, seen, matcher, _mode):
        callbacks[matcher["address"]] = seen
        return lambda: callbacks.pop(matcher["address"], None)

    with (
        patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]),
        patch("homeassistant.components.bluetooth.async_register_callback", side_effect=register),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert set(callbacks) == {right}
        # Kept for the reload that adopts it once the side advertises.
        assert registry.async_get_entity_id("cover", DOMAIN, f"{right}_back") is not None
        await hass.config_entries.async_unload(entry.entry_id)


async def test_refused_side_retires_pair_level_combined_controls(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    entry, _children = _remacro_pair(hass, 50, 50)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "button", DOMAIN, "pair_remacro_preset_flat_both", config_entry=entry
    ).entity_id
    adverts = {
        left: MagicMock(manufacturer_data={50: b""}),
        right: MagicMock(manufacturer_data={13: b""}),
    }
    with patch(_HISTORY, side_effect=lambda _hass, address, connectable: adverts[address]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert registry.async_get(stale) is None
        await hass.config_entries.async_unload(entry.entry_id)


async def test_all_motors_yields_to_a_single_axis_stop(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
    enable_custom_integrations,
) -> None:
    """The combined control overlaps every motor, so a head stop preempts it."""
    address = "AA:BB:CC:DD:EE:91"
    entry = _remacro_entry(hass, address)
    registry = er.async_get(hass)
    holding = asyncio.Event()

    async def hold_until_cancelled(self, seconds: float, cancel_event: asyncio.Event) -> bool:
        holding.set()
        await cancel_event.wait()
        return True

    async def instant_sleep(self, seconds: float) -> None:
        return None

    with (
        patch(_HISTORY, return_value=MagicMock(manufacturer_data={50: b""})),
        patch.object(RemacroController, "_pause", hold_until_cancelled),
        patch.object(RemacroController, "_sleep", instant_sleep),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        all_motors = registry.async_get_entity_id("cover", DOMAIN, f"{address}_all_motors")
        head = registry.async_get_entity_id("cover", DOMAIN, f"{address}_back")
        assert all_motors is not None and head is not None
        mock_bleak_client.write_gatt_char.reset_mock()
        moving = hass.async_create_task(
            hass.services.async_call(
                "cover", "open_cover", {"entity_id": all_motors}, blocking=True
            )
        )
        async with asyncio.timeout(2):
            await holding.wait()
            await hass.services.async_call(
                "cover", "stop_cover", {"entity_id": head}, blocking=True
            )
            await moving
        codes = [
            bytes(call.args[1])[2:4].hex()
            for call in mock_bleak_client.write_gatt_char.call_args_list
            if call.args[0] == REMACRO_WRITE_CHAR_UUID
        ]
        # All motors up, its release STOP, then the head STOP.
        assert codes == ["1001", "0100", "0001"]
        await hass.config_entries.async_unload(entry.entry_id)
