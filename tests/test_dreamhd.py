"""Row105 Dream Motion HD 1.0.4 vectors, accepted report 2bc0c2799d86.

Expected literals come from this package's frozen census, not another app.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed import jiecang_app_protocol as protocol
from tests.test_jiecang_app_controller import make_controller as make_controller
from tests.test_jiecang_app_controller import packets

PROFILE = "dreamhd"


def receive(controller, value):
    controller._handle_notification(SimpleNamespace(uuid="notify"), bytearray.fromhex(value))


def test_complete_reachable_fixed_frame_census():
    actual = {command.hex() for _, command in protocol.DREAMHD_BOOTSTRAP}
    for layout in protocol.DREAMHD_LAYOUTS:
        for axis in protocol.layout_axes(layout):
            for up in (False, True):
                actual.add(protocol.motion_command(layout, axis, up).hex())
        for preset in ("flat", "zero_g", "anti_snore", "yoga"):
            actual.add(protocol.preset_command(layout, preset).hex())
        for zone in protocol.massage_zones(layout):
            for level in range(4):
                actual.add(protocol.massage_command(layout, zone, level).hex())
        actual.add(protocol.massage_close_command(layout).hex())
        actual.add(protocol.massage_mode_command(layout).hex())
    for slot in (1, 2):
        for save in (False, True):
            actual.add(protocol.memory_command(slot, save, PROFILE).hex())
    actual.update(
        (protocol.SHORT_RELEASE.hex(), protocol.AUTOMATIC_LIGHT_TOGGLE.hex(), "f1f10f000f7e")
    )
    assert actual == FROZEN_FIXED_FRAMES
    assert len(actual) == 45


def test_hd_startup_and_dynamic_vectors():
    assert [t for t, _ in protocol.DREAMHD_BOOTSTRAP] == [
        0,
        100,
        1000,
        1100,
        1200,
        1300,
        1400,
        1500,
        1600,
        1700,
        1800,
        1900,
    ]
    assert protocol.rgb_command(255, 0, 0, 100, 1800, True).hex() == "f1f152070000ff64070801cc7e"
    assert (
        protocol.clock_command(datetime(2026, 11, 3, 4, 5, 6)).hex() == "f1f15007380b0302040506ae7e"
    )
    assert (
        protocol.alarm_command(True, (True,) * 7, 23, 59, "yoga", 3, 2).hex()
        == "f1f151080101fe173b060302b67e"
    )
    for seconds in (0, 60, 120, 180, 240, 300, 600, 900, 1200, 1500, 1800):
        assert (
            int.from_bytes(protocol.rgb_command(1, 2, 3, 100, seconds, True)[8:10], "big")
            == seconds
        )
    assert protocol.rename_command("Bed room", True, False, PROFILE) == b"Bed room"
    # Use an actual byte length rather than reproducing Android's odd-nibble failure.
    assert (
        protocol.rename_command("A" * 10, False, True, PROFILE) == b"\x01\xfc\x07\x0a" + b"A" * 10
    )
    assert (
        protocol.rename_command("A" * 16, False, True, PROFILE) == b"\x01\xfc\x07\x10" + b"A" * 16
    )


def test_all_feature_bytes_and_sticky_consumer_orders():
    for value in range(256):
        update = protocol.parse_notification(bytes((242, 242, 14, 0, value, 0, 0)), PROFILE)
        assert update is not None and update.capabilities is not None
        # Accepted Java helper: third significant bit from MSB when width >= 3.
        width = value.bit_length()
        expected = width >= 3 and bool(value & (1 << (width - 3)))
        assert update.capabilities.light_config == expected
        assert update.capabilities.yoga == bool(value & 2)
        for has_light in (False, True):
            for suppressed in (False, True):
                for visibility in (0, 4, 8):
                    state = protocol.DreamHDLightControls(
                        visibility, visibility, visibility, suppressed
                    )
                    state.receive(update, has_light=has_light, split_series=False)
                    if has_light:
                        assert state.picker == (0 if expected else 8)
                        assert state.human == state.container == (0 if expected else 4)
                        assert state.suppressed == (suppressed or not expected)
                    else:
                        assert state == protocol.DreamHDLightControls(
                            visibility, visibility, visibility, suppressed
                        )
    positive = protocol.parse_notification(bytes.fromhex("f2f20e00a00000"), PROFILE)
    negative = protocol.parse_notification(bytes.fromhex("f2f20e00060000"), PROFILE)
    rgb = protocol.parse_notification(bytes.fromhex("f2f2520733221164012c01517e"), PROFILE)
    state = protocol.DreamHDLightControls()
    state.receive(negative, has_light=True, split_series=False)
    state.receive(rgb, has_light=True, split_series=False)
    assert state.picker == 8 and state.suppressed
    state.receive(positive, has_light=True, split_series=False)
    assert state.picker == state.human == 0 and state.suppressed
    state.receive(rgb, has_light=True, split_series=False)
    assert state.picker == 0  # suppression does not hide an already visible picker
    state.connected()
    state.receive(rgb, has_light=False, split_series=False)
    assert state.picker == 0 and state.human == 4 and not state.suppressed
    state.receive(protocol.Notification(reapply_layout=True), has_light=False, split_series=False)
    assert state.picker == 4


async def test_hd_controller_commands_and_cancellation(make_controller):
    controller, coordinator, client = make_controller(profile=PROFILE)
    await controller.move_back_up()
    assert packets(client) == [bytes.fromhex("f1f1010101037e")] * 4 + [protocol.SHORT_RELEASE]
    client.write_gatt_char.reset_mock()
    await controller.preset_memory(2)
    await controller.program_memory(1)
    await controller.massage_mode_step()
    assert [p.hex() for p in packets(client)] == [
        "f1f10d01010f7e",
        "f1f14e004e7e",
        *(["f1f10a01010c7e"] * 3),
        "f1f116010a217e",
    ]
    client.write_gatt_char.reset_mock()
    coordinator.cancel_command.set()
    await controller.move_back_up()
    await controller.preset_flat()
    assert packets(client) == [protocol.SHORT_RELEASE] * 2


async def test_hd_split_feedback_alias_and_no_optimistic_intensity(make_controller):
    controller, _, client = make_controller(profile=PROFILE, layout="standard_3_split_upper")
    await controller.set_massage_intensity("right", 3)
    assert packets(client)[0].hex() == "f1f122020804307e"
    assert controller.get_massage_state()["right_intensity"] == 0
    receive(controller, "f2f206050200030040507e")
    assert controller.get_massage_state() == {
        "head_intensity": 1,
        "foot_intensity": 2,
        "right_intensity": 2,
    }


async def test_hd_light_consumer_and_released_toggles(make_controller):
    controller, _, client = make_controller(profile=PROFILE)
    receive(controller, "f2f2520733221164012c01517e")
    assert controller.supports_light_color_control
    assert not controller.supports_automatic_light
    receive(controller, "f2f20e00060000")
    assert controller.supports_preset_yoga and not controller.supports_light_color_control
    receive(controller, "f2f2520733221164012c01517e")
    assert not controller.supports_light_color_control
    receive(controller, "f2f20e00a00000")
    assert controller.supports_light_color_control and controller.supports_automatic_light
    assert controller.protocol_diagnostics["dreamhd_light_controls"]["suppressed"]
    receive(controller, "f2f25300000000")
    assert controller._automatic_light is False
    await controller.set_automatic_light(True)
    await controller.lights_toggle()
    assert packets(client) == [
        protocol.AUTOMATIC_LIGHT_TOGGLE,
        protocol.SHORT_RELEASE,
        protocol.rgb_command(17, 34, 51, 100, 300, False),
        protocol.SHORT_RELEASE,
        bytes.fromhex("f1f10f000f7e"),
        protocol.SHORT_RELEASE,
    ]


async def test_hd_manual_light_gate_and_legacy_consumer(make_controller):
    controller, _, _ = make_controller(profile=PROFILE, has_light=False)
    receive(controller, "f2f20e00a00000")
    receive(controller, "f2f2520733221164012c01517e")
    assert controller._hd_light.picker == 0
    assert not controller.supports_light_color_control and not controller.supports_automatic_light
    receive(controller, "000005000000000040")
    receive(controller, "000005000000000000")
    assert controller._light_on is True  # clear bit only consumed with main light visible
    with pytest.raises(ValueError, match="not configured"):
        await controller.lights_toggle()


@pytest.mark.parametrize("transport", ("g1", "g2", "g3"))
async def test_hd_transports_bootstrap_and_reconnect(make_controller, transport):
    controller, _, client = make_controller(profile=PROFILE, transports=(transport,))
    controller._capabilities_received.set()
    await controller.start_notify()
    assert packets(client) == (
        [] if transport == "g2" else [b for _, b in protocol.DREAMHD_BOOTSTRAP]
    )
    assert client.start_notify.await_count == (2 if transport == "g3" else 1)
    receive(controller, "f2f20e00060000")
    receive(controller, "f2f2520733221164012c01517e")
    await controller.stop_notify()
    await controller.start_notify()
    assert controller._hd_light == protocol.DreamHDLightControls()
    assert controller._rgb is None
    assert controller.supports_preset_yoga


@pytest.mark.parametrize("layout", ("standard_4_bilateral", "split_after_bilateral"))
def test_hd_never_exposes_unproven_layouts(make_controller, layout):
    with pytest.raises(ValueError, match="unavailable"):
        make_controller(profile=PROFILE, layout=layout)


def test_hd_wake_offsets_and_parser_edges():
    for layout in protocol.DREAMHD_LAYOUTS:
        schedule = protocol.wake_schedule(layout, "memory_2", 2, 3, profile=PROFILE)
        assert [t for t, b in schedule if b[2] == 0x14] == [500, 530, 560]
        assert [t for t, b in schedule if b[2] == 0x0D] == [800, 830, 860, 890, 920]
        assert all(b != protocol.LONG_RELEASE for _, b in schedule)
        assert [t for t, b in schedule if b[2] == 0x22] == (
            [180, 210, 240] if layout in ("standard_3_split_upper", "split_series") else []
        )
    for value in range(256):
        update = protocol.parse_notification(bytes((242, 242, 83, 0, value, 0, 0)), PROFILE)
        assert update.automatic_light == (value != 0)
    for size in range(7, 14):
        assert (
            protocol.parse_notification(
                bytes.fromhex("f2f251080101fe173b060302b67e")[:size], PROFILE
            ).alarm
            is None
        )
    assert (
        protocol.parse_notification(bytes.fromhex("000006050200030040507e"), PROFILE).massage_legs
        == 3
    )
    assert (
        protocol.parse_notification(bytes.fromhex("f2f251080101feff3b060302b67e"), PROFILE).alarm
        is None
    )


async def test_hd_unknown_alarm_preset_retains_previous_selection(make_controller):
    controller, _, _ = make_controller(profile=PROFILE)
    receive(controller, "f2f251080101fe173b060302b67e")
    receive(controller, "f2f251080101fe173bff0302b67e")
    assert controller._alarm.wake == "yoga"


async def test_hd_wake_cleanup_on_success_cancel_and_failure(make_controller):
    for outcome in ("success", "cancel", "failure"):
        controller, coordinator, client = make_controller(profile=PROFILE)
        if outcome == "cancel":
            coordinator.cancel_command.set()
        if outcome == "failure":
            client.write_gatt_char.side_effect = [RuntimeError("failed"), None, None]
            with pytest.raises(RuntimeError, match="failed"):
                await controller.execute_wake_routine(preset="flat", head_level=1)
        else:
            await controller.execute_wake_routine(preset="flat", head_level=1)
        if outcome == "success":
            assert packets(client)[-1] == protocol.SHORT_RELEASE
        else:
            assert packets(client)[-2:] == [protocol.SHORT_RELEASE, bytes.fromhex("f1f11101081a7e")]


def test_hd_discovery_has_no_app_or_name_inference():
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.beds.jiecang_app import _TRANSPORTS
    from custom_components.adjustable_bed.const import BED_TYPE_JIECANG_APP, JIECANG_APP_PROFILES
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES

    manifest = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/manifest.json").read_text()
    )
    service_filters = {row.get("service_uuid") for row in manifest["bluetooth"]}
    assert _TRANSPORTS["g1"][0] in service_filters
    assert _TRANSPORTS["g3"][0] in service_filters
    assert _TRANSPORTS["g2"][0] not in service_filters
    assert JIECANG_APP_PROFILES["dreamhd"] == "Dream Motion HD"
    assert "Dream Motion HD" in BED_TYPE_DISPLAY_NAMES[BED_TYPE_JIECANG_APP]


FROZEN_FIXED_FRAMES = {
    "f1f10000007e",
    "f1f1000101027e",
    "f1f1000108097e",
    "f1f1000110117e",
    "f1f1000140417e",
    "f1f100024000427e",
    "f1f1010101037e",
    "f1f1020101047e",
    "f1f1030101057e",
    "f1f1040101067e",
    "f1f1050101077e",
    "f1f1060101087e",
    "f1f1070101097e",
    "f1f10801010a7e",
    "f1f10901010b7e",
    "f1f10a01010c7e",
    "f1f10b01010d7e",
    "f1f10c01010e7e",
    "f1f10d01010f7e",
    "f1f10f000f7e",
    "f1f11101081a7e",
    "f1f1120208001c7e",
    "f1f1120208021e7e",
    "f1f1120208031f7e",
    "f1f112020804207e",
    "f1f1140208001e7e",
    "f1f114020802207e",
    "f1f114020803217e",
    "f1f114020804227e",
    "f1f116010a217e",
    "f1f11901011b7e",
    "f1f11a01011c7e",
    "f1f11b01011d7e",
    "f1f11c01011e7e",
    "f1f1200101227e",
    "f1f1210101237e",
    "f1f1220208002c7e",
    "f1f1220208022e7e",
    "f1f1220208032f7e",
    "f1f122020804307e",
    "f1f1230101257e",
    "f1f1240101267e",
    "f1f1280200002a7e",
    "f1f1290200002b7e",
    "f1f14e004e7e",
}


async def test_hd_cancelled_wake_attempts_massage_stop_even_when_release_fails(make_controller):
    controller, coordinator, client = make_controller(profile=PROFILE)

    async def write(_uuid, command, **_kwargs):
        if command[2] == 0x12:
            coordinator.cancel_command.set()
        elif command == protocol.SHORT_RELEASE:
            raise RuntimeError("release failed")

    client.write_gatt_char.side_effect = write
    with pytest.raises(RuntimeError, match="release failed"):
        await controller.execute_wake_routine(preset="flat", head_level=1)
    assert packets(client) == [
        bytes.fromhex("f1f1120208021e7e"),
        protocol.SHORT_RELEASE,
        bytes.fromhex("f1f11101081a7e"),
    ]
