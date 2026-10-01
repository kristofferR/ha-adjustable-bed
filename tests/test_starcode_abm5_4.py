"""Frozen standalone004 packet/parser vectors and actual owner-bound runtime."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import (
    FIELDS,
    FIRMWARE_UUID,
    MANUFACTURER_UUID,
    SELECTORS,
    TRANSPORTS,
    build_frame,
    constructor_selector,
    initial_fields,
    manufacturer_selector,
    parse_fields,
    scan_matches,
)
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS, PARSER_VECTORS


def make_controller(command="BOX25", ui=None, device="BOX25"):
    co = MagicMock()
    co.name = "Star test"
    co.ble_device_name = "Star test"
    co.address = "AA:BB:CC:DD:EE:FF"
    co.cancel_command = asyncio.Event()
    co.motor_pulse_count = 2
    co.entry.data = {}
    t = TRANSPORTS[device]
    roles = [
        MagicMock(
            uuid=u, handle=i, properties=["read", "write", "write-without-response", "notify"]
        )
        for i, u in enumerate((t.write, t.notify, MANUFACTURER_UUID, FIRMWARE_UUID))
    ]
    co.client = MagicMock(
        is_connected=True,
        services=[
            MagicMock(uuid=t.service, characteristics=roles[:2]),
            MagicMock(uuid="0000180a-0000-1000-8000-00805f9b34fb", characteristics=roles[2:]),
        ],
    )
    for name in ("write_gatt_char", "read_gatt_char", "start_notify", "stop_notify"):
        setattr(co.client, name, AsyncMock())
    co.client.read_gatt_char.return_value = b"star"
    co.async_execute_controller_command = AsyncMock()
    return StarcodeAbm5_4Controller(
        co, command_selector=command, ui_selector=ui, transport_selector=device
    )


@pytest.mark.parametrize(("selector", "action", "value", "frame"), BUILDER_VECTORS)
def test_reachable_command_vectors(selector, action, value, frame):
    assert build_frame(selector, action, value).hex() == frame


@pytest.mark.parametrize(("selector", "frame", "expected"), PARSER_VECTORS)
def test_parser_vectors_and_short_input_safety(selector, frame, expected):
    updates = parse_fields(selector, bytes.fromhex(frame))
    if expected is None:
        assert updates == {}
    else:
        initial: dict[str, object] = dict.fromkeys(FIELDS, 0)
        initial.update({"43": False, "47": False, "5f": False})
        initial.update(updates)
        assert initial == expected


@pytest.mark.parametrize("selector", SELECTORS)
def test_all_parsers_are_selected_by_C_not_device_transport(selector):
    data = bytes.fromhex("a50b0e0001640006030000000000251000000000")
    c = make_controller(selector, device="BOX3633")
    updates = parse_fields(c.command_selector, data)
    assert c.control_characteristic_uuid == TRANSPORTS["BOX3633"].write
    assert c.memory_slot_count == 1
    assert not c.supports_position_feedback
    if selector in ("BOX25", "BOX25_STAR"):
        assert updates["b"] == 1
        assert updates["13"] == 6
    elif selector != "BOX15":
        assert updates["b"] == 10
        assert updates["23"] == -1


@pytest.mark.parametrize(
    ("name", "constructor", "scannable"),
    [
        ("Star1", "BOX25", True),
        ("star1", "BOX3633", True),
        ("STAR1", "BOX3633", True),
        ("BLE1", "BOX1220", False),
        ("ble1", "BOX3633", False),
        ("XStar", "BOX3633", False),
    ],
)
def test_exact_discovery_and_independent_constructor_casing(name, constructor, scannable):
    assert constructor_selector(name) == constructor
    assert scan_matches(name) is scannable


@pytest.mark.parametrize(
    ("text", "selector"),
    [("star", "BOX25_STAR"), ("Star", "BOX25"), ("star\x00", "BOX25"), ("", "BOX25")],
)
def test_manufacturer_is_exact_untrimmed_match(text, selector):
    assert manufacturer_selector(text) == selector


@pytest.mark.parametrize("action", ["changeMassageTime", "changeLightBrightness"])
@pytest.mark.parametrize("value", [-1, 256, True])
def test_unreachable_dynamic_values_have_no_frame(action, value):
    with pytest.raises(ValueError):
        build_frame("BOX25", action, value)


async def test_actual_GATT_roles_and_response_follow_D_independently_of_C():
    for d, t in TRANSPORTS.items():
        c = make_controller("BOX15", device=d)
        await c.write_command(build_frame("BOX15", "headUp"))
        call = c.client.write_gatt_char.call_args
        assert call.args[0] is c.client.services[0].characteristics[0]
        assert call.args[1].hex() == "e6fe16010000000004"
        assert call.kwargs["response"] is t.response


async def test_actual_stream_release_and_delayed_massage_sequence():
    c = make_controller()
    writes = []
    now = 0.0

    async def record(role, data, *, response):
        writes.append((round(now, 3), data.hex()))

    async def wait(seconds, _event):
        nonlocal now
        now += seconds
        return True

    async def sleep(seconds):
        nonlocal now
        now += seconds

    c.client.write_gatt_char.side_effect = record
    loop = asyncio.get_running_loop()
    with (
        patch.object(loop, "time", lambda: now),
        patch.object(c, "_wait", wait),
        patch("custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", sleep),
    ):
        await c.hold_control("head_up", 250)
    assert writes == [
        (0.0, "05020000000100"),
        (0.1, "05020000000100"),
        (0.2, "05020000000100"),
        (0.25, "05020000000000"),
    ]
    writes.clear()
    c._massage_on = True
    now = 0.0
    with (
        patch.object(loop, "time", lambda: now),
        patch.object(c, "_wait", wait),
        patch("custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", sleep),
    ):
        await c.massage_head_up()
    assert writes == [(0.0, "05020000080000"), (0.1, "05020000000000"), (0.3, "00b0")]


@pytest.mark.parametrize("ui", SELECTORS)
async def test_presets_release_depends_on_U_not_C(ui):
    c = make_controller("BOX25", ui=ui)
    await c._stream("tv", 0, release="preset")
    packets = [x.args[1].hex() for x in c.client.write_gatt_char.call_args_list]
    assert packets == ["05020000400000"] + (
        ["05020000000000"] if ui in ("BOX25", "BOX25_STAR") else []
    )


async def test_cancelled_movement_still_releases_with_fresh_event():
    c = make_controller()

    async def write(role, data, *, response):
        if data == build_frame("BOX25", "headUp"):
            c._coordinator.cancel_command.set()

    c.client.write_gatt_char.side_effect = write
    await c.hold_control("head_up", 200)
    assert [x.args[1] for x in c.client.write_gatt_char.call_args_list] == [
        build_frame("BOX25", "headUp"),
        build_frame("BOX25", "stop"),
    ]


async def test_cooperative_cancel_waiting_for_ble_lock_returns_without_packet():
    c = make_controller()
    event = asyncio.Event()
    async with c.ble_lock:
        task = asyncio.create_task(
            c.write_command(build_frame("BOX25", "headUp"), cancel_event=event)
        )
        await asyncio.sleep(0)
        event.set()
    await task
    c.client.write_gatt_char.assert_not_called()


async def test_cooperative_cancel_waiting_for_ble_lock_keeps_fresh_movement_release():
    c = make_controller()
    async with c.ble_lock:
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await asyncio.sleep(0)
        c._coordinator.cancel_command.set()
    await task
    assert [call.args[1] for call in c.client.write_gatt_char.call_args_list] == [
        build_frame("BOX25", "stop")
    ]


async def test_actual_task_cancel_waiting_for_ble_lock_still_propagates():
    c = make_controller()
    async with c.ble_lock:
        task = asyncio.create_task(c.write_command(build_frame("BOX25", "headUp")))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    c.client.write_gatt_char.assert_not_called()


async def test_callback_cannot_retarget_after_owner_or_connection_change():
    c = make_controller()
    old = c.client
    c._coordinator.address = "11:22:33:44:55:66"
    with pytest.raises(ConnectionError):
        await c.lights_on()
    assert old.write_gatt_char.call_count == 0
    c._notification(
        old,
        c._session_generation,
        old.services[0].characteristics[1],
        bytearray.fromhex("a50b0000000100010000000000001110"),
    )
    assert not c._massage_on
    assert c._coordinator.handle_controller_state_updates.call_count == 0


async def test_own_address_modern_flags_survive_exact_AddDevice_transition():
    c = make_controller("BOX25", device="BOX1220")
    c._raw_fields.update({"b": 1, "43": True, "53": 4})
    c._massage_on = True
    c._light_on = True
    c._timer_index = 1
    c._level = 4
    await c.adopt_transport_profile()
    assert (c.command_selector, c.ui_selector, c.transport_selector) == ("BOX1220",) * 3
    assert c._massage_on and c._light_on and c._level == 4
    await c.set_app_brightness(6)
    assert c.client.write_gatt_char.call_args.args[1] == bytes.fromhex("04e000060000")
    c._coordinator._async_persist_config.assert_called_once()


@pytest.mark.parametrize("selector", SELECTORS)
async def test_positive_massage_and_brightness_gates_are_writer_backed(selector):
    c = make_controller(selector)
    with pytest.raises(ValueError):
        await c.set_app_timer("10")
    with pytest.raises(ValueError):
        await c.set_app_brightness(2)
    c._massage_on = c._light_on = True
    if selector not in ("BOX1220", "BOX3633", "BOX25", "BOX25_STAR"):
        with pytest.raises(ValueError):
            await c.set_app_timer("10")
        with pytest.raises(ValueError):
            await c.set_app_brightness(2)
    assert c.client.write_gatt_char.call_count == 0


def test_default_raw_state_and_no_unknown_position_semantics():
    fields = initial_fields()
    assert fields["47"] is True and fields["5f"] is True
    c = make_controller()
    assert c.position_number_specs == ()
    assert len(c.controller_state_sensor_specs) == 29
    assert c.controller_select_specs[0].options == ("10", "20", "30")
    assert not c.supports_massage_off_control
    assert not c.supports_light_color_control


@pytest.mark.parametrize("value", [0, 7, 15, 30, 255, True, 2.5])
async def test_public_brightness_rejects_private_builder_domain(value):
    c = make_controller()
    c._light_on = True
    with pytest.raises(ValueError):
        await c.set_app_brightness(value)
    c.client.write_gatt_char.assert_not_called()
    if type(value) is int and 0 <= value <= 255:
        assert build_frame("BOX25", "changeLightBrightness", value)[1] == 0xE0


async def test_stream_captures_refresh_but_release_uses_current_own_address_C():
    c = make_controller()

    async def wait(_duration, _event):
        c.command_selector = "BOX25_STAR"
        return False

    with patch.object(c, "_wait", wait):
        await c.hold_control("head_up", 200)
    assert [x.args[1] for x in c.client.write_gatt_char.call_args_list] == [
        build_frame("BOX25", "headUp"),
        build_frame("BOX25_STAR", "stop"),
    ]


@pytest.mark.parametrize(
    "release,ui,stops",
    [
        ("stop", "none", True),
        ("preset", "BOX25", True),
        ("preset", "none", False),
        ("none", "BOX25", False),
    ],
)
async def test_teardown_releases_original_owner_before_invalidation(release, ui, stops):
    c = make_controller(ui=ui)
    client = c.client
    c._notify_client = client
    c._active_release = (client, c._session_generation, c._operation_generation, release)
    await c.stop_notify()
    assert client.write_gatt_char.call_count == int(stops)
    if stops:
        assert client.write_gatt_char.call_args.args[1] == build_frame("BOX25", "stop")
    assert c._active_release is None and not c._ready


async def test_optional_read_retry_and_stale_result_cannot_update_new_session():
    c = make_controller()
    c.client.read_gatt_char.side_effect = [OSError("read"), b"Star"]
    sleep = AsyncMock()
    with patch("custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", sleep):
        await c._classify()
    sleep.assert_awaited_once_with(0.2)
    assert c.command_selector == c.transport_selector == "BOX25"
    assert c.ui_selector == "BOX25"
    assert c.client.read_gatt_char.call_args.args[0] is c.client.services[1].characteristics[0]

    async def stale(_role):
        c._session_generation += 1
        return b"stale firmware"

    c.client.read_gatt_char.side_effect = stale
    await c._read_firmware()
    assert c._firmware is None


@pytest.mark.parametrize(
    "device,subscribe,wake",
    [
        ("BOX1220", True, False),
        ("BOX3633", False, False),
        ("BOX25", True, True),
        ("BOX25_STAR", True, True),
    ],
)
async def test_connection_actual_roles_subscription_wake_retry_and_delays(device, subscribe, wake):
    c = make_controller(device=device)
    pending = []
    c._spawn = pending.append
    if wake:
        c.client.write_gatt_char.side_effect = [OSError("wake"), None]
    if subscribe:
        c.client.start_notify.side_effect = [OSError("notify"), None]
    sleep = AsyncMock()
    with patch("custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", sleep):
        await c.start_notify()
        assert c._ready
        assert [operation.__name__ for operation in pending] == (
            ["connected_reads"] if wake else ["classify", "connected_reads"]
        )
        if wake:
            assert c._classification_complete
            assert (
                c.client.read_gatt_char.call_args.args[0] is c.client.services[1].characteristics[0]
            )
        if subscribe:
            sleep.assert_awaited_once_with(2)
        assert c.client.start_notify.call_count == (2 if subscribe else 0)
        assert c.client.write_gatt_char.call_count == (2 if wake else 0)
        for call in c.client.write_gatt_char.call_args_list:
            assert call.args[0] is c.client.services[0].characteristics[0]
            assert call.args[1] == bytes.fromhex("5a0b00a5") and call.kwargs["response"] is True
        connected_reads = next(
            operation for operation in pending if operation.__name__ == "connected_reads"
        )
        await connected_reads()
        assert [x.args[0] for x in sleep.call_args_list][-2:] == [0.5, 1]
        assert c.client.read_gatt_char.call_args.args[0] is c.client.services[1].characteristics[1]
    await c.stop_notify()
    assert c.client.stop_notify.call_count == int(subscribe)


async def test_changed_U_callback_consumes_exact_fields_and_suppresses_duplicate():
    c = make_controller()
    pending = []
    c._spawn = pending.append
    frame = bytearray.fromhex("a50b0000000100010000000000002110")
    role = c.client.services[0].characteristics[1]
    c._notification(c.client, 0, role, frame)
    assert c._massage_on and c._light_on and c._level == 2
    assert c.get_light_state()["is_on"] is True
    assert len(pending) == 1
    values = c._coordinator.handle_controller_state_updates.call_args.args[0]
    assert values["starcode_abm5_4_massage_timer"] == "10"
    assert values["starcode_abm5_4_head_intensity"] == 0
    c._notification(c.client, 0, role, frame)
    assert len(pending) == 1 and c._coordinator.handle_controller_state_updates.call_count == 1
    c._operation_generation += 1
    await pending[0]()
    c._coordinator.async_execute_controller_command.assert_not_called()


async def test_strict_shared_light_debounce_and_unreachable_profile_plus_minus():
    c = make_controller("BOX15")
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", return_value=1):
        await c._light_step(1)
    with patch.object(loop, "time", return_value=1.5):
        await c._light_step(-1)
    assert c.client.write_gatt_char.call_count == 1
    with patch.object(loop, "time", return_value=1.501):
        await c._light_step(-1)
    assert [x.args[1] for x in c.client.write_gatt_char.call_args_list] == [
        build_frame("BOX15", "changeLightBrightness", 2),
        build_frame("BOX15", "turnoffUnderbedLighting"),
    ]


@pytest.mark.parametrize("first", ["step", "brightness", "on", "off", "toggle"])
@pytest.mark.parametrize("second", ["step", "brightness", "on", "off", "toggle"])
async def test_every_light_path_shares_strict_elapsed_gate(first, second):
    c = make_controller()
    c._light_on = True
    actions = {
        "step": lambda: c._light_step(1),
        "brightness": lambda: c.set_app_brightness(4),
        "on": c.underbed_lights_on,
        "off": c.underbed_lights_off,
        "toggle": c.underbed_lights_toggle,
    }
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", return_value=1.0):
        await actions[first]()
    level = c._level
    for timestamp in (1.499, 1.5, 1.5009):
        with patch.object(loop, "time", return_value=timestamp):
            await actions[second]()
        assert c.client.write_gatt_char.call_count == 1
        assert c._level == level
        assert c._last_light_time_ms == 1000
    with patch.object(loop, "time", return_value=1.501):
        await actions[second]()
    assert c.client.write_gatt_char.call_count == 2
    assert c._last_light_time_ms == 1501


@pytest.mark.parametrize("value", [0, 7, 15, 30, 255, True, 2.5])
async def test_invalid_brightness_does_not_consume_shared_light_gate(value):
    c = make_controller()
    c._light_on = True
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", return_value=1.0):
        await c.lights_on()
    with patch.object(loop, "time", return_value=1.501):
        with pytest.raises(ValueError):
            await c.set_app_brightness(value)
        assert c._last_light_time_ms == 1000
        await c.set_app_brightness(4)
    assert c.client.write_gatt_char.call_count == 2
    assert c.client.write_gatt_char.call_args.args[1] == build_frame(
        "BOX25", "changeLightBrightness", 4
    )


def test_retained_state_cannot_authorize_another_address_or_a_cold_controller():
    c = make_controller()
    c._ui_state_observed = c._massage_on = c._light_on = True
    c._level, c._timer_index = 4, 2
    c._publish()
    retained = c._coordinator.starcode_app_retained_state
    c._coordinator.address = "11:22:33:44:55:66"
    other = StarcodeAbm5_4Controller(c._coordinator, command_selector="BOX1220")
    assert not other._ui_state_observed and not other._massage_on and not other._light_on
    assert (other._level, other._timer_index) == (1, 0)
    for target in (other, make_controller("BOX1220")):
        with pytest.raises(ValueError):
            target._require_positive()
        with pytest.raises(ValueError):
            target._require_positive(light=True)
    c._publish()  # An obsolete owner cannot replace the newly selected address's cache.
    assert c._coordinator.starcode_app_retained_state is retained


async def test_same_owner_reconstruction_preserves_gate_time_but_not_parser_baseline():
    c = make_controller()
    role = c.client.services[0].characteristics[1]
    c._notification(c.client, 0, role, bytearray.fromhex("a50b0000000100010000000000002100"))
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", return_value=1.0):
        await c.lights_on()
    replacement = StarcodeAbm5_4Controller(
        c._coordinator, command_selector="BOX25", transport_selector="BOX25"
    )
    assert replacement._raw_fields == initial_fields()
    assert not replacement._parser_state_observed
    replacement._publish()
    state = c._coordinator.handle_controller_state_updates.call_args.args[0]
    assert state["starcode_abm5_4_light_on"] is True
    assert state["starcode_abm5_4_raw_53"] is None
    for key, value in {
        "wave": 0,
        "head_intensity": 0,
        "low_4b": 1,
        "automatic_white_flag": False,
    }.items():
        assert state["starcode_abm5_4_" + key] == value
    with patch.object(loop, "time", return_value=1.5):
        await replacement.lights_off()
    assert c.client.write_gatt_char.call_count == 1
    with patch.object(loop, "time", return_value=1.501):
        await replacement.lights_off()
    assert c.client.write_gatt_char.call_count == 2
    replacement._notification(
        replacement.client, 0, role, bytearray.fromhex("a50b0000000100010000000000002100")
    )
    assert replacement._parser_state_observed
    assert replacement._raw_fields["53"] == 2


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize(
    "control",
    [
        "head_up",
        "head_down",
        "foot_up",
        "foot_down",
        "union_up",
        "union_down",
        "memory_1",
        "flat",
        "tv",
        "lounge",
        "zero_g",
        "anti_snore",
        "save_memory_1",
        "save_tv",
        "save_lounge",
        "save_zero_g",
        "save_reset",
    ],
)
async def test_action_timing_and_release(selector, control):
    from custom_components.adjustable_bed.beds.starcode_abm5_4 import _MOVEMENT, _PRESETS, _SAVES

    c = make_controller(selector)
    now = 0.0
    writes = []

    async def wait(seconds, _event):
        nonlocal now
        now = round(now + seconds, 6)
        return True

    async def record(_role, data, *, response):
        writes.append((round(now, 3), data))

    c.client.write_gatt_char.side_effect = record
    action = _MOVEMENT.get(control) or _PRESETS.get(control) or _SAVES[control[5:]]
    duration = 6000 if control.startswith("save_") else 600 if control == "flat" else 250
    stop = (
        control in _MOVEMENT
        or control in ("memory_1", "save_memory_1")
        or selector in ("BOX25", "BOX25_STAR")
    )
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", lambda: now), patch.object(c, "_wait", wait):
        await c.hold_control(control, 250)
    refresh = writes[:-1] if stop else writes
    assert refresh[0] == (0.0, build_frame(selector, action))
    assert all(packet == build_frame(selector, action) for _, packet in refresh)
    assert [timestamp for timestamp, _ in refresh] == [
        round(i / 10, 3) for i in range((duration + 99) // 100)
    ]
    if stop:
        assert writes[-1] == (duration / 1000, build_frame(selector, "stop"))
    assert c._active_release is None


async def test_automatic_white_captures_C_refreshes_five_seconds_and_never_stops():
    c = make_controller()
    now = 0.0
    writes = []

    async def wait(seconds, _event):
        nonlocal now
        now = round(now + seconds, 6)
        c.command_selector = "BOX25_STAR"
        return True

    async def record(_role, data, *, response):
        writes.append((round(now, 3), data))

    c.client.write_gatt_char.side_effect = record
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", lambda: now), patch.object(c, "_wait", wait):
        await c._stream("change2White", 5000, release="none")
    assert len(writes) == 50
    assert [time for time, _ in writes] == [i / 10 for i in range(50)]
    assert all(packet == build_frame("BOX25", "change2White") for _, packet in writes)


@pytest.mark.parametrize("selector", SELECTORS)
@pytest.mark.parametrize("ui", SELECTORS)
async def test_memory_A_recall_releases_immediately_independent_of_U(selector, ui):
    c = make_controller(selector, ui=ui)
    await c.hold_control("memory_1", 1)
    assert [call.args[1] for call in c.client.write_gatt_char.await_args_list] == [
        build_frame(selector, "m1"),
        build_frame(selector, "stop"),
    ]


@pytest.mark.parametrize("failed_tick", [0, 1, 3])
async def test_platform_write_failure_keeps_exact_ticks_and_release_without_retry(
    failed_tick, caplog
):
    c = make_controller()
    now = 0.0
    attempts = []

    async def wait(seconds, _event):
        nonlocal now
        now = round(now + seconds, 6)
        return True

    async def write(_role, packet, *, response):
        attempts.append((round(now, 3), packet))
        if len(attempts) - 1 == failed_tick:
            raise BleakError("platform write failed")

    c.client.write_gatt_char.side_effect = write
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", lambda: now), patch.object(c, "_wait", wait):
        await c._stream("headUp", 250)
    assert attempts == [
        (0.0, build_frame("BOX25", "headUp")),
        (0.1, build_frame("BOX25", "headUp")),
        (0.2, build_frame("BOX25", "headUp")),
        (0.25, build_frame("BOX25", "stop")),
    ]
    assert "without acknowledgement" in caplog.text
    assert c._active_release is None


async def test_failed_massage_release_still_issues_delayed_query_without_retry():
    c = make_controller()
    now = 0.0
    attempts = []

    async def wait(seconds, _event):
        nonlocal now
        now = round(now + seconds, 6)
        return True

    async def sleep(seconds):
        nonlocal now
        now = round(now + seconds, 6)

    async def write(_role, packet, *, response):
        attempts.append((round(now, 3), packet))
        if packet == build_frame("BOX25", "stop"):
            raise BleakError("release transport failure")

    c.client.write_gatt_char.side_effect = write
    loop = asyncio.get_running_loop()
    with (
        patch.object(loop, "time", lambda: now),
        patch.object(c, "_wait", wait),
        patch("custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", sleep),
    ):
        await c._stream("headStrengthAdd", 0, release="massage")
    assert attempts == [
        (0.0, build_frame("BOX25", "headStrengthAdd")),
        (0.1, build_frame("BOX25", "stop")),
        (0.3, build_frame("BOX25", "queryMassage")),
    ]


async def test_metadata_exact_manufacturer_changes_C_D_but_never_U_or_roles():
    c = make_controller("BOX15", ui="BOX15")
    original_transport = c._transport
    await c._classify()
    assert (c.command_selector, c.transport_selector, c.ui_selector) == (
        "BOX25_STAR",
        "BOX25_STAR",
        "BOX15",
    )
    assert c._transport is original_transport
    c._coordinator._begin_internal_entry_update.assert_called_once_with(False)
    assert c._coordinator._async_persist_config.call_args.kwargs["keys"] == {
        "starcode_abm5_4_command_selector",
        "starcode_abm5_4_ui_selector",
    }
    other = make_controller("BOX15", device="BOX3633")
    await other._classify()
    assert (other.command_selector, other.transport_selector, other.ui_selector) == (
        "BOX15",
        "BOX3633",
        "BOX15",
    )
    other._coordinator._async_persist_config.assert_not_called()


async def test_optional_absence_and_pending_notification_do_not_block_control():
    c = make_controller("BOX15")
    c.client.services = c.client.services[:1]
    pending = []
    c._spawn = pending.append
    await c.start_notify()
    assert c._ready
    await c._classify()
    assert c.command_selector == "BOX15"
    await c._stream("headUp", 0)
    assert [call.args[1] for call in c.client.write_gatt_char.call_args_list] == [
        build_frame("BOX15", "keepConnect"),
        build_frame("BOX15", "headUp"),
        build_frame("BOX15", "stop"),
    ]
    c.client.start_notify.assert_awaited_once()


async def test_exact_required_service_cannot_reuse_a_foreign_role_uuid():
    c = make_controller()
    c.client.services[0].uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    with pytest.raises(ConnectionError):
        await c.start_notify()
    assert not c._ready
    c.client.write_gatt_char.assert_not_called()


async def test_write_latency_is_absorbed_in_the_exact_refresh_interval():
    c = make_controller()
    now = 0.0
    writes = []

    async def record(_role, data, *, response):
        nonlocal now
        writes.append((round(now, 3), data))
        now += 0.03

    async def wait(seconds, _event):
        nonlocal now
        now += seconds
        return True

    c.client.write_gatt_char.side_effect = record
    loop = asyncio.get_running_loop()
    with patch.object(loop, "time", lambda: now), patch.object(c, "_wait", wait):
        await c.hold_control("head_up", 250)
    assert [time for time, _ in writes] == [0.0, 0.1, 0.2, 0.25]
    assert c._coordinator.record_command_trace.call_count == 4
    assert c._coordinator.record_command_trace.call_args.kwargs["characteristic_handle"] == 0


@pytest.mark.parametrize("selector", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
@pytest.mark.parametrize(
    "kind,value", [("timer", v) for v in (1, 2, 3)] + [("brightness", v) for v in range(1, 7)]
)
async def test_every_public_live_parameter_uses_own_address_observed_writer(selector, kind, value):
    c = make_controller("BOX25", device=selector)
    c._spawn = lambda _operation: None
    c._notification(
        c.client,
        c._session_generation,
        c.client.services[0].characteristics[1],
        bytearray.fromhex("a50b0000000100010000000000002110"),
    )
    assert c._massage_on and c._light_on
    await c.adopt_transport_profile()
    with patch(
        "custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", new=AsyncMock()
    ):
        if kind == "timer":
            await c.set_app_timer(str(value * 10))
            packets = [
                build_frame(selector, "changeMassageTime", value),
                build_frame(selector, "stop"),
                build_frame(selector, "queryMassage"),
            ]
        else:
            await c.set_app_brightness(value)
            packets = [build_frame(selector, "changeLightBrightness", value)]
    assert [call.args[1] for call in c.client.write_gatt_char.call_args_list] == packets


@pytest.mark.parametrize("selector", ["none", "BOX15", "BOX24", "BOX1221", "BOX2422", "BOX2442"])
async def test_legacy_fresh_plus_uses_only_raw_two_without_a_brightness_slider(selector):
    c = make_controller(selector)
    await c._light_step(1)
    assert c.client.write_gatt_char.call_args.args[1] == build_frame(
        selector, "changeLightBrightness", 2
    )
    assert c.controller_number_specs == ()


async def test_old_operation_finally_cannot_stop_a_newer_operation():
    c = make_controller()

    async def wait(_duration, _event):
        c._operation_generation += 1
        return False

    with patch.object(c, "_wait", wait):
        await c.hold_control("head_up", 200)
    assert [call.args[1] for call in c.client.write_gatt_char.call_args_list] == [
        build_frame("BOX25", "headUp")
    ]
    assert c._active_release is None
