"""Svane Remote Version 1.8 literal vectors and target-local lifecycle."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.svane import (
    DIS,
    DOWN,
    FEET,
    HEAD,
    LIGHT,
    MOTIONS,
    OLD,
    OLD_CHAR,
    POSITION,
    SOFTWARE,
    UP,
    SvaneCommands,
    SvaneController,
    uuid,
)
from custom_components.adjustable_bed.svane_state import SvaneSession, get_svane_session


def make_controller(profile="multi", *, properties=("write", "read", "notify"), session=None):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_count = 2
    roles = (
        (HEAD, (UP, DOWN, POSITION, uuid("fb6e"))),
        (FEET, (UP, DOWN, POSITION)),
        (LIGHT, (uuid("a8e0"), uuid("b5e9"), uuid("3fb2"))),
        (OLD, (OLD_CHAR,)),
        (SOFTWARE, (uuid("a592"),)),
        (DIS, tuple(uuid(x) for x in ("2a26", "2a27", "2a29"))),
    )
    services = [
        SimpleNamespace(
            uuid=s,
            characteristics=[
                MagicMock(uuid=c, properties=list(properties), handle=i * 10 + j)
                for j, c in enumerate(chars)
            ],
        )
        for i, (s, chars) in enumerate(roles)
    ]
    client = MagicMock(is_connected=True, services=services)
    coordinator.client = client
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()

    async def read(role):
        return {
            uuid("2a26"): b"firmware",
            uuid("2a27"): b"hardware",
            uuid("2a29"): b"maker",
            OLD_CHAR: bytes.fromhex("109981388113"),
            POSITION: b"\x81\x38",
        }.get(role.uuid, b"")

    client.read_gatt_char = AsyncMock(side_effect=read)
    controller = SvaneController(coordinator, profile=profile, session=session)
    coordinator.controller = controller

    async def query(refresh, **kwargs):
        if kwargs["run_if"]():
            await refresh(controller)

    coordinator.async_execute_controller_query = AsyncMock(side_effect=query)
    return controller


def written(controller):
    return [
        (
            next(s.uuid for s in controller.client.services if call.args[0] in s.characteristics),
            call.args[0].uuid,
            bytes(call.args[1]).hex(),
        )
        for call in controller.client.write_gatt_char.call_args_list
    ]


@pytest.mark.parametrize(
    "level,expected",
    [
        (5, "130205010064"),
        (10, "13020a010064"),
        (90, "13025a010064"),
        (95, "13025f010064"),
        (100, "130264010064"),
        (256, "130200010064"),
        (-1, "1302ff010064"),
        (-2147483648, "130200010064"),
        (2147483647, "1302ff010064"),
    ],
)
def test_java_int32_light_vectors(level, expected):
    assert SvaneCommands.light_brightness(level).hex() == expected


@pytest.mark.parametrize(
    "head,feet,expected",
    [
        (None, None, "100000000000"),
        (True, None, "100100000000"),
        (False, None, "100200000000"),
        (None, True, "101000000000"),
        (None, False, "102000000000"),
        (True, True, "101100000000"),
        (True, False, "102100000000"),
        (False, True, "101200000000"),
        (False, False, "102200000000"),
    ],
)
def test_closed_jmc_motion_vectors(head, feet, expected):
    assert SvaneCommands.motion(head, feet).hex() == expected


@pytest.mark.parametrize("value", [True, 1.2, "90", None, 2**31, -(2**31) - 1])
def test_invalid_builder_value_before_transport(value):
    with pytest.raises(ValueError):
        SvaneCommands.light_brightness(value)


@pytest.mark.parametrize("profile", ["multi", "jmc"])
@pytest.mark.parametrize("control", list(MOTIONS))
async def test_literal_held_actions_and_release(profile, control):
    controller = make_controller(profile)
    await controller.hold_control(control, 130)
    calls = written(controller)
    head, feet = MOTIONS[control]
    if profile == "jmc":
        assert calls[0] == (OLD, OLD_CHAR, SvaneCommands.motion(head, feet).hex())
        assert calls[-1] == (OLD, OLD_CHAR, "100000000000")
        assert all(s == OLD and c == OLD_CHAR for s, c, _ in calls)
    else:
        expected = {
            (s, UP if direction else DOWN)
            for s, direction in ((HEAD, head), (FEET, feet))
            if direction is not None
        }
        assert {(s, c) for s, c, b in calls if b == "0100"} == expected
        assert {(s, c) for s, c, b in calls if b == "0000"} == expected
        assert {b for _, _, b in calls} == {"0100", "0000"}


@pytest.mark.parametrize(
    "profile,control,minfirst,minnext",
    [
        ("jmc", "head_up", 0, 0.095),
        ("jmc", "feet_up", 0.095, 0.19),
        ("multi", "feet_up", 0.095, 0.19),
    ],
)
async def test_source_schedule_after_work(profile, control, minfirst, minnext):
    controller = make_controller(profile)
    times = []
    start = asyncio.get_running_loop().time()

    async def write(role, data, **kwargs):
        if data not in (b"\x00\x00", SvaneCommands.motion(None, None)):
            times.append(asyncio.get_running_loop().time() - start)

    controller.client.write_gatt_char.side_effect = write
    await controller.hold_control(control, 350)
    assert len(times) >= 2
    assert times[0] >= minfirst
    assert times[1] - times[0] >= minnext


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_partial_release_preserves_remaining_axis(profile):
    controller = make_controller(profile)
    task = asyncio.create_task(controller.hold_control("head_up_feet_down", 600))
    while not controller.client.write_gatt_char.await_count:
        await asyncio.sleep(0.001)
    controller.request_svane_axis_release("head")
    await asyncio.sleep(0.25)
    intermediate = written(controller)
    controller.request_svane_axis_release("feet")
    await task
    calls = written(controller)
    if profile == "jmc":
        assert intermediate[0][2] == "102100000000"
        assert "102000000000" in [b for _, _, b in intermediate]
        assert "100000000000" not in [b for _, _, b in intermediate]
        assert calls[-1][2] == "100000000000"
        assert [b for _, _, b in calls].count("100000000000") == 1
    else:
        assert (HEAD, UP, "0000") in intermediate
        assert (FEET, DOWN, "0100") in intermediate
        assert calls[-1] == (FEET, DOWN, "0000")


@pytest.mark.parametrize("profile", ["multi", "jmc"])
@pytest.mark.parametrize("termination", ["event", "task", "write"])
async def test_started_roles_cleanup_after_cancellation_or_write_failure(profile, termination):
    controller = make_controller(profile)
    if termination == "write":

        async def write(role, data, **kwargs):
            if data in (b"\x01\x00", bytes.fromhex("101100000000")):
                raise BleakError("submission failed")

        controller.client.write_gatt_char.side_effect = write
        with pytest.raises(BleakError):
            await controller.hold_control("head_up_feet_up", 500)
    else:
        task = asyncio.create_task(controller.hold_control("head_up_feet_up", 500))
        await asyncio.sleep(0.13)
        if termination == "event":
            controller._coordinator.cancel_command.set()
        else:
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    calls = written(controller)
    assert calls[-1][2] == ("100000000000" if profile == "jmc" else "0000")
    assert not controller._started


async def test_cleanup_attempts_all_p1_directions_when_one_stop_fails():
    controller = make_controller()
    controller._started = {(HEAD, UP), (FEET, DOWN)}

    async def write(role, data, **kwargs):
        if role.uuid == UP:
            raise BleakError("head stop failed")

    controller.client.write_gatt_char.side_effect = write
    with pytest.raises(BleakError):
        await controller.stop_all()
    assert {(s, c, b) for s, c, b in written(controller)} == {
        (HEAD, UP, "0000"),
        (FEET, DOWN, "0000"),
    }


@pytest.mark.parametrize(
    "properties,response",
    [
        (("write",), True),
        (("write-without-response",), False),
        (("write", "write-without-response"), False),
    ],
)
async def test_exact_role_and_property_backed_write_mode(properties, response):
    controller = make_controller(properties=properties)
    await controller.execute_app_control("position")
    assert written(controller) == [(HEAD, uuid("fb6e"), "0300")]
    assert controller.client.write_gatt_char.await_args.kwargs["response"] is response


@pytest.mark.parametrize("failure", ["missing", "readonly", "duplicate", "disconnected"])
async def test_role_failure_precedes_any_movement(failure):
    controller = make_controller()
    head = controller.client.services[0]
    if failure == "missing":
        head.characteristics = []
    elif failure == "readonly":
        head.characteristics[0].properties = ["read"]
    elif failure == "duplicate":
        head.characteristics.append(head.characteristics[0])
    else:
        controller.client.is_connected = False
    with pytest.raises((ValueError, ConnectionError)):
        await controller.hold_control("head_up", 100)
    controller.client.write_gatt_char.assert_not_awaited()


async def test_initialization_order_keeps_device_information_off_the_connect_path():
    controller = make_controller()
    events = []
    original_read = controller.client.read_gatt_char.side_effect

    async def read(role):
        events.append(("read", role.uuid))
        return await original_read(role)

    async def subscribe(role, callback):
        events.append(("notify", role.uuid))

    async def write(role, data, **kwargs):
        events.append(("write", role.uuid, data.hex()))

    async def wait(seconds):
        events.append(("wait", seconds))
        return True

    controller.client.read_gatt_char.side_effect = read
    controller.client.start_notify.side_effect = subscribe
    controller.client.write_gatt_char.side_effect = write
    controller._wait = wait
    await controller.start_notify()
    assert events[0] == ("wait", 0.1)
    assert events[1:3] == [("notify", OLD_CHAR), ("write", uuid("a592"), "040000000000")]
    assert [r for kind, *tail in events[3:] if kind == "read" for r in tail] == [POSITION, OLD_CHAR]
    assert controller.session.feet == b"\x81\x38"
    assert controller.session.position == bytes.fromhex("81388113")
    connected = len(events)
    # The app's paced device-information reads follow in the background.
    assert controller._device_info_task is not None
    await controller._device_info_task
    assert events[connected:] == [
        ("read", uuid("2a26")),
        ("wait", 1),
        ("read", uuid("2a27")),
        ("wait", 1),
        ("read", uuid("2a29")),
        ("wait", 1),
    ]
    before = len(events)
    await controller.start_notify()
    assert len(events) == before
    await controller.stop_notify()
    assert not controller._subscriptions


async def test_failed_status_subscription_keeps_the_connection():
    """A proxy without a free notify slot loses observations, not motor control."""
    controller = make_controller()
    controller.client.start_notify.side_effect = BleakError("no free notify slot")

    async def wait(seconds):
        return True

    controller._wait = wait
    await controller.start_notify()
    assert controller._initialized
    await controller.stop_notify()


@pytest.mark.parametrize("state", [0, 1])
@pytest.mark.parametrize("present", [0, 1, 2, 3])
@pytest.mark.parametrize("fails", [False, True])
async def test_state_read_attempts_all_present_roles_in_order(state, present, fails):
    controller = make_controller()
    first = HEAD if state == 0 else FEET
    controller.client.services = [
        s
        for s in controller.client.services
        if (s.uuid == first and present & 1) or (s.uuid == OLD and present & 2)
    ]
    if fails:
        controller.client.read_gatt_char.side_effect = BleakError("read submission failed")
    await controller._read_state(state)
    assert [call.args[0].uuid for call in controller.client.read_gatt_char.call_args_list] == (
        [POSITION] if present & 1 else []
    ) + ([OLD_CHAR] if present & 2 else [])


async def test_partial_dis_observation_survives_later_failure_and_reconstruction():
    session = SvaneSession()
    controller = make_controller(session=session)
    controller.client.read_gatt_char.side_effect = [b"known fw", BleakError("hardware read failed")]
    controller._wait = AsyncMock(return_value=True)
    with pytest.raises(BleakError):
        await controller.refresh_device_information()
    assert session.observations["svane_firmware"] == "known fw"
    assert "svane_hardware" not in session.observations
    rebuilt = make_controller(session=session)
    updates = rebuilt._coordinator.handle_controller_state_updates.call_args_list
    assert any(call.args[0].get("svane_firmware") == "known fw" for call in updates)
    assert not session.position


@pytest.mark.parametrize(
    "service,char",
    [
        (DIS, uuid("2a26")),
        (DIS, uuid("2a27")),
        (DIS, uuid("2a29")),
        (HEAD, POSITION),
        (FEET, POSITION),
        (OLD, OLD_CHAR),
        (HEAD, uuid("2a27")),
        (DIS, POSITION),
    ],
)
@pytest.mark.parametrize("raw", ["100081388113", "", "10", "00"])
def test_dispatch_origin_precedence_and_short_buffers(service, char, raw):
    controller = make_controller()
    data = bytes.fromhex(raw)
    accepted = controller.accept_response(service, char, data)
    expected = bool(data) and (
        (service in (HEAD, FEET) and char == POSITION)
        or (service == OLD and char == OLD_CHAR and len(data) >= 6 and data[0] == 16)
    )
    assert accepted is expected
    assert (controller.session.position is not None) == (expected and service == OLD)
    if expected and service == HEAD:
        assert controller.session.head == data
    if expected and service == FEET:
        assert controller.session.feet == data


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_save_read_only_and_recall_exact_opaque_bytes(profile):
    controller = make_controller(profile)
    controller._wait = AsyncMock(return_value=True)
    await controller.program_memory(2)
    assert written(controller) == []
    await controller.preset_memory(2)
    if profile == "jmc":
        assert written(controller) == [(OLD, OLD_CHAR, "100481388113")]
    else:
        assert written(controller) == [(HEAD, POSITION, "8138"), (FEET, POSITION, "8138")]
    assert controller._wait.await_args.args == (1,)


async def test_unbounded_p1_raw_memory_and_cancelled_head_feet_gap():
    controller = make_controller()
    raw = b"\x01\x02\x03\x04\x05"
    controller.session.multi_slots[1] = (raw, b"\xff")
    controller._wait = AsyncMock(return_value=False)
    await controller.preset_memory(1)
    assert written(controller) == [(HEAD, POSITION, raw.hex())]


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_top_defaults_light_on_off_and_no_extra_stop(profile):
    controller = make_controller(profile)
    await controller.execute_app_control("position")
    await controller.lights_toggle()
    await controller.lights_toggle()
    assert [b for _, _, b in written(controller)] == (
        ["0300"] if profile == "multi" else ["108100000000"]
    ) + ["13025a010064", "130200000000"]
    assert not controller.session.light_on
    # The app's Svane position keeps the button ID existing entries use.
    assert controller.supports_preset_zero_g
    assert not controller.supports_preset_flat
    assert not controller.position_number_specs
    assert not controller.supports_massage


@pytest.mark.parametrize(
    "initial,step,expected,characteristic",
    [(90, 5, 95, "b5e9"), (100, 5, 95, "3fb2"), (5, -5, 10, "b5e9")],
)
async def test_lamp_triangle_updates_intent_before_failure_and_no_release_frame(
    initial, step, expected, characteristic
):
    session = SvaneSession(
        intensity=initial, light_on=True, light_step=step, light_intent_known=True
    )
    controller = make_controller(session=session)
    controller._wait = AsyncMock(return_value=True)
    controller.client.write_gatt_char.side_effect = BleakError("failed lamp write")
    with pytest.raises(BleakError):
        await controller.hold_control("light_adjust", 500)
    assert session.intensity == expected
    assert written(controller) == [
        (LIGHT, uuid(characteristic), SvaneCommands.light_brightness(expected).hex())
    ]
    controller._coordinator.remember_svane_preferences.assert_called_once()


async def test_lamp_hold_off_or_short_no_io():
    controller = make_controller()
    await controller.hold_control("light_adjust", 100)
    controller.session.light_on = True
    controller.session.light_intent_known = True
    await controller.hold_control("light_adjust", 200)
    controller.client.write_gatt_char.assert_not_awaited()


async def test_process_cache_rebuild_cold_restart_and_target_isolation(hass):
    session = get_svane_session(hass, "AA:BB:CC:DD:EE:FF", "multi")
    session.light_on = True
    session.light_step = -5
    session.multi_slots[1] = (b"head", b"feet")
    assert get_svane_session(hass, "aa:bb:cc:dd:ee:ff", "multi") is session
    other = get_svane_session(hass, "AA:BB:CC:DD:EE:00", "multi")
    assert not other.light_on and not other.multi_slots
    cold = SimpleNamespace(data={})
    reset = get_svane_session(
        cold, "AA:BB:CC:DD:EE:FF", "multi", {"intensity": 95, "slots": ["00112233", "44556677"]}
    )
    assert not reset.light_on and reset.light_step == 5 and not reset.multi_slots
    assert reset.intensity == 95 and reset.jmc_slots == (
        bytes.fromhex("00112233"),
        bytes.fromhex("44556677"),
    )
    changed = get_svane_session(hass, "AA:BB:CC:DD:EE:FF", "jmc")
    assert changed is not session and not changed.multi_slots


@pytest.mark.parametrize(
    "preferences",
    [
        False,
        {"intensity": True},
        {"intensity": 101},
        {"intensity": 7},
        {"slots": ["1234", "1234"]},
        {"slots": ["00112233"]},
    ],
)
def test_bad_stored_preferences_before_connection(hass, preferences):
    with pytest.raises(ValueError):
        get_svane_session(hass, "AA:BB:CC:DD:EE:FF", "multi", preferences)


async def test_notify_lifecycle_cleanup_unsubscribes_even_failed_motor_release():
    controller = make_controller()
    await controller._subscribe(OLD, OLD_CHAR)
    controller._started = {(HEAD, UP)}
    controller.client.write_gatt_char.side_effect = BleakError("release failed")
    with pytest.raises(BleakError):
        await controller.stop_notify()
    controller.client.stop_notify.assert_awaited_once()
    assert not controller._subscriptions
    assert controller._started == {(HEAD, UP)}
    controller.client.write_gatt_char.side_effect = None
    await controller.stop_all()
    assert not controller._started
    assert [packet for _, _, packet in written(controller)] == ["0000", "0000"]


@pytest.mark.parametrize("retired", ["stop", "replacement", "disconnected", "role", "sender"])
async def test_retired_notification_callback_cannot_forward_raw_or_state(retired):
    controller = make_controller("jmc")
    client = controller.client
    raw_callback = MagicMock()
    controller.set_raw_notify_callback(raw_callback)
    await controller._subscribe(OLD, OLD_CHAR)
    role, callback = client.start_notify.call_args.args
    callback(role, bytearray.fromhex("100081388113"))
    assert controller.session.position == bytes.fromhex("81388113")
    raw_callback.reset_mock()
    controller._coordinator.handle_controller_state_updates.reset_mock()
    sender = role
    if retired == "stop":
        await controller.stop_notify()
        # A new subscription must not make the retired callback usable again.
        await controller._subscribe(OLD, OLD_CHAR)
    elif retired == "replacement":
        controller._coordinator.client = make_controller("jmc").client
    elif retired == "disconnected":
        client.is_connected = False
    elif retired == "role":
        old_service = next(service for service in client.services if service.uuid == OLD)
        old_service.characteristics = []
    else:
        sender = client.services[0].characteristics[0]
    callback(sender, bytearray.fromhex("100011223344"))
    assert controller.session.position == bytes.fromhex("81388113")
    raw_callback.assert_not_called()
    controller._coordinator.handle_controller_state_updates.assert_not_called()


async def test_device_information_cancel_preserves_completed_metadata():
    controller = make_controller()

    async def wait(seconds):
        if seconds == 1:
            controller._coordinator.cancel_command.set()
            return False
        return True

    controller._wait = wait
    await controller.start_notify()
    assert controller._device_info_task is not None
    await controller._device_info_task
    assert controller.session.observations["svane_firmware"] == "firmware"
    assert "svane_hardware" not in controller.session.observations


@pytest.mark.parametrize(
    ("level", "written_level"), [(1, 5), (37, 35), (38, 40), (100, 100)]
)
async def test_light_slider_snaps_to_app_steps(level, written_level):
    """The established 0-100 slider keeps working; levels snap to the app's steps."""
    controller = make_controller()
    await controller.set_light_level(level)
    assert written(controller)[-1][2] == SvaneCommands.light_brightness(written_level).hex()
    assert controller.session.intensity == written_level


async def test_light_slider_zero_turns_the_lamp_off():
    controller = make_controller()
    await controller.set_light_level(0)
    assert written(controller)[-1][2] == "130200000000"
    assert not controller.session.light_on


async def test_saved_p1_memory_is_persisted_and_survives_a_restart():
    """Saved P1 slots are stored with the entry, so recall works after a restart (#152)."""
    controller = make_controller()
    await controller.program_memory(1)
    preferences = controller._coordinator.remember_svane_preferences.call_args.args[0]
    assert preferences["multi_slots"] == {"1": ["8138", "8138"]}
    # A restart builds a fresh session from the persisted preferences.
    from custom_components.adjustable_bed.svane_state import svane_multi_slots

    restarted = make_controller(
        session=SvaneSession(multi_slots=svane_multi_slots(preferences))
    )
    restarted._wait = AsyncMock(return_value=True)
    await restarted.preset_memory(1)
    assert written(restarted) == [(HEAD, POSITION, "8138"), (FEET, POSITION, "8138")]


@pytest.mark.parametrize(
    "multi_slots",
    [{"3": ["81", "82"]}, {"1": ["81"]}, {"1": ["", "82"]}, {"1": ["8", "82"]}, ["81", "82"]],
)
def test_invalid_persisted_p1_memory_is_rejected(multi_slots):
    from custom_components.adjustable_bed.svane_state import svane_preferences

    with pytest.raises(ValueError):
        svane_preferences({"intensity": 90, "multi_slots": multi_slots})
