"""Eshine row106 artifact vectors, safe parsing and HA control surfaces.

Derived integration tests, not the raw APK Protocol Audit report. Evidence and
intentional safety differences: docs/apk-analysis/dispositions/row106-eshine.md.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.eshine import STATE_GROUPS, EshineController
from custom_components.adjustable_bed.beds.eshine_protocol import (
    GATT_MAPS,
    OPCODES,
    NotificationStream,
    control_frame,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_ESHINE,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
)
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor


def service(row=GATT_MAPS[1], *, response=True, notify_uuid=None):
    write = SimpleNamespace(
        uuid=row[1],
        properties=["write"] + ([] if response else ["write-without-response"]),
        handle=1,
    )
    notify = SimpleNamespace(uuid=notify_uuid or row[2], properties=["notify"], handle=2)
    return SimpleNamespace(uuid=row[0], characteristics=[write, notify])


def make(*services):
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_pulse_delay_ms = 999  # Ignored: fixed artifact interval.
    coordinator.controller_state = {}
    coordinator.handle_controller_state_updates.side_effect = coordinator.controller_state.update
    coordinator.client = MagicMock(is_connected=True, services=list(services) or [service()])
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return EshineController(coordinator)


def frames(controller):
    return [bytes(call.args[1]).hex() for call in controller.client.write_gatt_char.call_args_list]


@pytest.fixture
def sleeps(monkeypatch):
    delays = []
    real_sleep = asyncio.sleep

    async def sleep(delay):
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return delays


# Every reachable action in both formats. The literals are the artifact vectors.
COMMANDS = [
    ("head_up", "24", "6e01002493"),
    ("head_down", "25", "6e01002594"),
    ("feet_up", "26", "6e01002695"),
    ("feet_down", "27", "6e01002796"),
    ("lumbar_up", "3f", "6e01003fae"),
    ("lumbar_down", "40", "6e010040af"),
    ("pillow_up", "41", "6e010041b0"),
    ("pillow_down", "42", "6e010042b1"),
    ("flat", "31", "6e010031a0"),
    ("light", "3c", "6e01003cab"),
    ("massage_head_strength", "4c", "6e01004cbb"),
    ("massage_foot_strength", "4e", "6e01004ebd"),
    ("massage_mode", "48", "6e010048b7"),
    ("massage_off", "5e", "6e01005ecd"),
    ("massage_10_minutes", "5f", "6e01005fce"),
    ("massage_20_minutes", "63", "6e010063d2"),
    ("massage_30_minutes", "61", "6e010061d0"),
    ("anti_snore", "46", "6e010046b5"),
    ("zero_g", "45", "6e010045b4"),
    ("save_anti_snore", "69", "6e010069d8"),
    ("save_zero_g", "66", "6e010066d5"),
    ("stop", "6e", "6e01006edd"),
    ("exit_limit", "00", "6e02010071"),
]


@pytest.mark.parametrize(("action", "compact", "framed"), COMMANDS)
async def test_all_action_vectors(action, compact, framed, sleeps):
    assert control_frame(action, True).hex() == compact
    assert control_frame(action, False).hex() == framed
    for row, expected, stop in [
        (GATT_MAPS[0], compact, "6e"),
        (GATT_MAPS[1], framed, "6e01006edd"),
    ]:
        ctrl = make(service(row))
        await ctrl.async_discover_capabilities()
        await ctrl.start_notify()
        ctrl.client.write_gatt_char.reset_mock()
        if action == "exit_limit":
            with pytest.raises(ValueError):
                await ctrl.execute_action(action)
        else:
            await ctrl.execute_action(action)
            assert frames(ctrl) == (
                [expected] * 3 + [stop] if action in ctrl.held_control_options else [expected]
            )


@pytest.mark.parametrize("row", GATT_MAPS)
@pytest.mark.parametrize("response", [True, False])
async def test_endpoint_session_and_setup(row, response):
    # The artifact chooses the first NOTIFY property, not its declared UUID.
    ctrl = make(service(row, response=response, notify_uuid="00001234-0000-1000-8000-00805f9b34fb"))
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    await ctrl.start_notify()
    assert frames(ctrl) == ["00" if row == GATT_MAPS[0] else "6e02010071"]
    assert ctrl.client.write_gatt_char.call_args.kwargs["response"] is response
    assert ctrl.client.write_gatt_char.call_args.args[0] is ctrl._write_char
    ctrl.client.start_notify.assert_awaited_once()
    assert ctrl.client.start_notify.call_args.args[0] is ctrl._notify_char
    await ctrl.stop_notify()
    ctrl.client.stop_notify.assert_awaited_once()


async def test_refuse_ambiguous_or_incomplete_gatt_without_writes():
    for services in [(service(GATT_MAPS[0]), service()), (service(), service())]:
        ctrl = make(*services)
        with pytest.raises(ValueError):
            await ctrl.async_discover_capabilities()
        assert frames(ctrl) == []
    for props in (["write-without-response"], ["read"]):
        s = service()
        s.characteristics[0].properties = props
        ctrl = make(s)
        with pytest.raises(ValueError):
            await ctrl.async_discover_capabilities()
    s = service()
    s.characteristics[1].properties = ["indicate"]
    ctrl = make(s)
    with pytest.raises(ValueError):
        await ctrl.async_discover_capabilities()


@pytest.mark.parametrize("error", [BleakError("failed write"), asyncio.CancelledError()])
async def test_failed_or_cancelled_movement_releases_with_fresh_event(error):
    ctrl = make()
    await ctrl.async_discover_capabilities()

    async def write(*args, **kwargs):
        if args[1] != control_frame("stop", False):
            ctrl._coordinator.cancel_command.set()
            raise error

    ctrl.client.write_gatt_char.side_effect = write
    with pytest.raises(type(error)):
        await ctrl.move_head_up()
    assert frames(ctrl) == ["6e01002493", "6e01006edd"]


async def test_cancel_event_ends_refresh_and_stop_is_not_suppressed(sleeps):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    ctrl.client.write_gatt_char.side_effect = lambda *_a, **_kw: (
        ctrl._coordinator.cancel_command.set()
    )
    await ctrl.move_head_up()
    assert frames(ctrl) == ["6e01002493", "6e01006edd"]
    assert ctrl.motor_pulse_settings() == (3, 100)


async def test_hold_is_bounded_and_always_stops(sleeps):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    await ctrl.hold_control("pillow_down", 300)
    assert frames(ctrl) == ["6e010042b1"] * 4 + ["6e01006edd"]
    for control, duration in [("flat", 100), ("head_up", 0), ("head_up", 60001), ("head_up", True)]:
        with pytest.raises(ValueError):
            await ctrl.hold_control(control, duration)


async def test_profile_exposes_exact_controls_and_no_invented_queries():
    ctrl = make()
    assert {spec.key for spec in ctrl.motor_control_specs} == {"head", "feet", "lumbar", "pillow"}
    assert all(
        spec.scheduler_resource == "*" and spec.position_key is None
        for spec in ctrl.motor_control_specs
    )
    assert ctrl.supports_massage and ctrl.auto_enable_massage and ctrl.supports_lights
    assert not ctrl.supports_memory_presets and ctrl.memory_slot_count == 0
    assert not ctrl.supports_single_address_pairing and not ctrl.supports_direct_position_control
    assert not ctrl.supports_position_feedback
    assert BED_TYPE_ESHINE in BEDS_WITHOUT_ANGLE_FEEDBACK
    assert len(ctrl.controller_button_specs) == 7
    assert {row["value"]: row["label"] for row in get_bed_type_options()}[
        BED_TYPE_ESHINE
    ] == "Eshine app (E6000)"
    hidden = hidden_generic_fields(BED_TYPE_ESHINE, None)
    assert {CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS} <= hidden
    assert CONF_MOTOR_PULSE_COUNT not in hidden
    assert per_side_profile(BED_TYPE_ESHINE, None) is not None
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    await ctrl.read_positions()
    assert frames(ctrl) == ["6e02010071"]


async def test_buttons_and_generic_actions(sleeps):
    ctrl = make()
    await ctrl.async_discover_capabilities()
    for spec in ctrl.controller_button_specs:
        await spec.press_fn(ctrl)
    for method in (
        ctrl.preset_flat,
        ctrl.preset_zero_g,
        ctrl.preset_anti_snore,
        ctrl.lights_toggle,
        ctrl.massage_off,
        ctrl.massage_mode_step,
    ):
        await method()
    assert frames(ctrl) == [
        "6e010066d5",
        "6e010069d8",
        "6e01004cbb",
        "6e01004ebd",
        "6e01005fce",
        "6e010063d2",
        "6e010061d0",
        "6e010031a0",
        "6e010045b4",
        "6e010046b5",
        "6e01003cab",
        "6e01005ecd",
        "6e010048b7",
    ]
    assert set(OPCODES) == {action for action, _, _ in COMMANDS}


# Integration projections of every accepted stream vector, including excluded domains.
RECEIVE_VECTORS = [
    (
        "motor-basic",
        ["6e200b01020200012c02cd"],
        [("motor_height", {"height": 30.0, "type": 2, "angle": -1, "monitorHeight": 0})],
    ),
    (
        "motor-full",
        ["6e200e01020300007b012c01c813"],
        [("motor_height", {"height": 12.3, "type": 1, "angle": 44, "monitorHeight": 45.6})],
    ),
    (
        "massage-pairs",
        ["6e200b02010201040206ab"],
        [("massage_head_strength", 4), ("massage_foot_strength", 6)],
    ),
    ("massage-2", ["6e20090202030005a3"], [("massage_mode", 5)]),
    ("massage-4", ["6e20090204030003a3"], [("massage_frequency", 3)]),
    ("massage-5", ["6e20090205030004a5"], [("music_shake", 4)]),
    ("massage-6", ["6e20090206030001a3"], [("massage_on", True)]),
    ("white-led", ["6e200903010200019e"], [("white_led", True)]),
    (
        "rgb",
        ["6e200b04010200ff00ff9e"],
        [("rgb_color", {"r": 1.0, "g": 0.0, "b": 1.0, "alpha": 1})],
    ),
    ("rgb-timer", ["6e200a04020300020fb2"], [("rgb_timer", 135)]),
    ("rgb-motion", ["6e20090403020001a1"], [("rgb_motion", True)]),
    ("rgb-off", ["6e20090404020000a1"], [("rgb_on", False)]),
    ("alarm", ["6e200d050102010203040506b8"], [("alarm_list", [1, 2, 3, 4, 5, 6])]),
    ("alarm-report", ["6e200d0501030708090a0b0cdd"], [("alarm_report", [7, 8, 9, 10, 11, 12])]),
    ("snore-enable", ["6e20090601020001a1"], [("anti_snore", True)]),
    ("off-bed-disable", ["6e20090602020000a1"], [("off_bed", False)]),
    ("sleep-name", ["6e200a06030300414227"], [("sleep_adv_name", [65, 66])]),
    ("snore-stop-music", ["6e200a060402000101a6"], [("snore_stop_music", True)]),
    ("snore-count", ["6e200a060503000109b0"], [("anti_snore_count", 9)]),
    ("snore-time", ["6e200a060503000208b0"], [("anti_snore_time", 8)]),
    ("lock", ["6e20090702020001a3"], [("box_lock", True)]),
    ("unlock", ["6e20090702030002a5"], [("box_unlock", True)]),
    ("music-1", ["6e20090901020001a4"], [("music_play", True)]),
    ("music-3", ["6e20090903020001a6"], [("music_ble", True)]),
    ("music-4", ["6e20090904020001a7"], [("music_usb", True)]),
    ("check-1", ["6e20080a010009aa"], [("component_check_1", [110, 32, 8, 10, 1, 0, 9, 170])]),
    ("check-2", ["6e20080a020009ab"], [("component_check_2", [110, 32, 8, 10, 2, 0, 9, 171])]),
    ("check-3", ["6e20080a030009ac"], [("component_check_3", [110, 32, 8, 10, 3, 0, 9, 172])]),
    ("check-4", ["6e20080a040009ad"], [("component_check_4", [110, 32, 8, 10, 4, 0, 9, 173])]),
    ("check-5", ["6e20080a050009ae"], [("component_check_5", [110, 32, 8, 10, 5, 0, 9, 174])]),
    ("check-6", ["6e20080a060009af"], [("component_check_6", [110, 32, 8, 10, 6, 0, 9, 175])]),
    ("press-1", ["6e20090b01030003a9"], [("press_mode", 3)]),
    ("press-2", ["6e20090b02030002a9"], [("standard_split", True)]),
    ("press-4", ["6e20090b04030004ad"], [("same_split", 4)]),
    ("blanket-1", ["6e20090d01020000a7"], []),
    ("blanket-2", ["6e200b0d020200000000aa"], []),
    ("blanket-5", ["6e200b0d050200000000ad"], []),
    ("blanket-6", ["6e20090d06020000ac"], []),
    ("blanket-7", ["6e20160d0702000000000000000000000000000000ba"], []),
    ("blanket-8", ["6e20090d08020000ae"], []),
    ("blanket-9", ["6e200d0d0902000000000000b3"], []),
    ("desk-extended", ["6e201b0f0102180117043807590a0c0d0e0f10032d1401480153b8"], []),
    ("common-clock_capability", ["6e09010078"], [("clock_capability", True)]),
    ("common-light_capability", ["6e0e00037f"], [("light_capability", True)]),
    ("common-aromatherapy_capability", ["6e1a000189"], [("aromatherapy_capability", True)]),
    ("common-alarm_add_success", ["6e07010177"], [("alarm_add_success", True)]),
    ("common-alarm_cancel_success", ["6e07010278"], [("alarm_cancel_success", True)]),
    ("common-music_capability", ["6e16010186"], [("music_capability", True)]),
    ("common-detection_capability", ["6e90c101c0"], [("detection_capability", True)]),
    ("common-snore_capability", ["6e2100008f"], [("snore_capability", True)]),
    ("common-box_lock", ["6e23018416"], [("box_lock", True)]),
    ("common-box_unlock", ["6e23008415"], [("box_unlock", True)]),
    ("common-6e90000907", ["6e90000907"], [("protocol_version", 9)]),
    ("common-6e90170507", ["6e90170507"], [("bed_mode", 7)]),
    ("common-6e90362d07", ["6e90362d07"], [("motor_angle", {"no": 1, "status": 2, "angle": 45})]),
    (
        "common-6e90a29c07",
        ["6e90a29c07"],
        [("massage_state", {"mode": 1, "massage1": 4, "massage2": 3, "massage3": 2})],
    ),
    (
        "common-6e90b1e007",
        ["6e90b1e007"],
        [("music_usb", True), ("music_play", True), ("music_shake", True), ("music_ble", True)],
    ),
    ("common-6e90c23007", ["6e90c23007"], [("detection_status", "pause")]),
    ("common-6e90c31207", ["6e90c31207"], []),
    ("common-6e90d12a07", ["6e90d12a07"], [("music_volume", 42)]),
    ("common-6e90d20507", ["6e90d20507"], [("music_shake_gear", 5)]),
    ("common-internal-header", ["6e23a06e9f"], []),
    ("fragmented-extension", ["6e200903", "010200019e"], [("white_led", True)]),
    ("bad-extension-checksum", ["6e200903010200019f"], []),
    (
        "concatenated-common",
        ["6e090100786e0e00037f"],
        [("clock_capability", True), ("light_capability", True)],
    ),
    ("partial-common-lost", ["6e9000", "0907"], []),
    ("ota-1", ["6e40000b01010212341f63"], []),
    ("ota-2", ["6e40000a010202438efa"], []),
    ("ota-3", ["6e40000a01030201d14c"], []),
    ("ota-4", ["6e40000a0104020264bf"], []),
    ("ota-5", ["6e40000a0105020073cd"], []),
    ("desk-common-seven", ["6e900000043800"], []),
    ("desk-common-sixteen-any-type", ["6e01000117043807590a0c0d0e0f1000"], []),
    ("ignored-domain", ["6e20090801020001a3"], []),
    ("ignored-operation", ["6e200903010100019d"], []),
    ("ignored-subtype", ["6e200903020200019f"], []),
    ("massage-unknown-tag", ["6e20090201020309a8"], []),
    ("massage-odd-pairs", ["6e200a020102010900a7"], []),
    ("common-detection-default", ["6e90c2f007"], [("detection_status", "start")]),
    ("common-unknown", ["6e91000107"], []),
    ("ota-fragmented", ["6e40000a", "0103030782bb"], []),
    ("ota-bad-crc", ["6e40000a0103030782ba"], []),
    ("repair001-valid-3-2-00", ["6e200806030200a1"], [("sleep_adv_name", [])]),
    ("repair001-valid-3-2-0041", ["6e20090603020041e3"], [("sleep_adv_name", [65])]),
    ("repair001-valid-5-2-0000", ["6e20090605020000a4"], []),
    ("repair001-valid-5-2-00012a", ["6e200a06050200012ad0"], [("anti_snore_count", 42)]),
    ("repair001-valid-5-2-00022b", ["6e200a06050200022bd2"], [("anti_snore_time", 43)]),
    ("repair001-valid-4-2-000001", ["6e200a060402000001a5"], []),
    ("repair001-valid-4-2-000101", ["6e200a060402000101a6"], [("snore_stop_music", True)]),
    ("repair001-opgate-3-2", ["6e20070603019f"], []),
    ("repair001-opgate-5-2", ["6e2007060501a1"], []),
    ("repair001-valid-3-3-00", ["6e200806030300a2"], [("sleep_adv_name", [])]),
    ("repair001-valid-3-3-0041", ["6e20090603030041e4"], [("sleep_adv_name", [65])]),
    ("repair001-valid-5-3-0000", ["6e20090605030000a5"], []),
    ("repair001-valid-5-3-00012a", ["6e200a06050300012ad1"], [("anti_snore_count", 42)]),
    ("repair001-valid-5-3-00022b", ["6e200a06050300022bd3"], [("anti_snore_time", 43)]),
    ("repair001-valid-4-3-000001", ["6e200a060403000001a6"], []),
    ("repair001-valid-4-3-000101", ["6e200a060403000101a7"], [("snore_stop_music", True)]),
    ("repair001-opgate-3-3", ["6e20070603019f"], []),
    ("repair001-opgate-5-3", ["6e2007060501a1"], []),
]


@pytest.mark.parametrize(
    ("vector_id", "chunks", "expected"), RECEIVE_VECTORS, ids=[r[0] for r in RECEIVE_VECTORS]
)
def test_receive_vectors(vector_id, chunks, expected):
    stream = NotificationStream()
    result = []
    for chunk in chunks:
        result.extend(stream.feed(bytes.fromhex(chunk)))
    assert result == expected


@pytest.mark.parametrize(
    "data",
    [
        "6e2000",
        "6e400000",
        "6e200492",
        "6e20070501009b",
        "6e2007060302a0",
        "6e2007060303a1",
        "6e200806050200a3",
        "6e200806050300a4",
    ],
)
def test_malformed_frames_never_fabricate_state(data):
    stream = NotificationStream()
    assert stream.feed(bytes.fromhex(data)) == []
    assert stream.feed(bytes.fromhex("6e09010078")) == [("clock_capability", True)]


async def test_parsed_state_exposed_as_diagnostics_without_position_mapping():
    ctrl = make()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    raw = MagicMock()
    ctrl._raw_notify_callback = raw
    for _id, chunks, _expected in RECEIVE_VECTORS:
        ctrl._stream = NotificationStream()
        for chunk in chunks:
            ctrl._handle_notification(ctrl._notify_char, bytearray.fromhex(chunk))
    raw.assert_called()
    state = ctrl._coordinator.controller_state
    assert state["eshine_motors_data"]["motor_1"] == {"no": 1, "status": 2, "angle": 45}
    assert state["eshine_motors_data"]["motor_type_1"]["monitorHeight"] == 45.6
    assert state["eshine_alarm_data"]["alarm_report"] == [7, 8, 9, 10, 11, 12]
    assert set(STATE_GROUPS) == set(ctrl._observed)
    for spec in ctrl.controller_state_sensor_specs:
        sensor = AdjustableBedControllerStateSensor(ctrl._coordinator, spec)
        assert sensor.native_value == state[spec.state_key]
        assert sensor.extra_state_attributes == {key: state[key] for key in spec.attribute_keys}
    ctrl._coordinator.handle_position_update.assert_not_called()
    await ctrl.stop_notify()
    assert ctrl._stream.buffer == b""
    await ctrl.async_discover_capabilities()
    assert all(value is None for value in state.values())


async def test_cover_stop_bypasses_the_movement_cancel_event():
    ctrl = make()
    await ctrl.async_discover_capabilities()
    ctrl._coordinator.cancel_command.set()
    await ctrl.motor_control_specs[0].stop_fn(ctrl)
    assert frames(ctrl) == ["6e01006edd"]
