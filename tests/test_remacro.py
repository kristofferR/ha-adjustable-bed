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
    assert protocol.add_remacro_model({"a": 1}, {99: b""}) == {"a": 1}


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
    app: protocol.RemacroApp, model_id: int, *, pulse: tuple[int, int] = (10, 25)
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
    controller = RemacroController(coordinator, app=app, model=protocol.MODELS[model_id])

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
    await controller.stop_all()
    assert writes == []


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
    with pytest.raises(ValueError):
        await controller.set_led_brightness(256)


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

    # A reconnect rebuilds the controller but keeps the app-local session.
    await live.set_control_side("right")
    live._serial.hold(0x0101)
    again = await create_controller(
        coordinator, BED_TYPE_REMACRO, "the_brick", None, manufacturer_data={51: b""}
    )
    assert isinstance(again, RemacroController)
    assert again.control_side == "right"
    assert again._serial.hold(0x0100)[0] == 3
    other_app = await create_controller(
        coordinator, BED_TYPE_REMACRO, "jeromes", None, manufacturer_data={51: b""}
    )
    assert isinstance(other_app, RemacroController)
    assert other_app.control_side == "left"


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
