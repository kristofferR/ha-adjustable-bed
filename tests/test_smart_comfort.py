"""Artifact vectors and session, capability and cleanup behavior for both apps."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.smart_comfort.controller import SmartComfortController
from custom_components.adjustable_bed.codec import smart_comfort as codec
from custom_components.adjustable_bed.profiles.smart_comfort import PROFILES
from tests.smart_comfort_vectors import NOTIFICATIONS, WRITES
from tests.test_controller_contract import _FactoryCoordinator


@pytest.mark.parametrize("profile,action,address,value,rgb,name,frozen", WRITES)
def test_all_member_command_literals(profile, action, address, value, rgb, name, frozen):
    assert profile in PROFILES
    actual = (
        codec.rename(name)
        if action == "rename"
        else codec.command(action, address, value=value, rgb=rgb)
    )
    assert actual.hex() == frozen


@pytest.mark.parametrize("profile,identifier,frame,expected", NOTIFICATIONS)
def test_all_member_notification_literals(profile, identifier, frame, expected):
    parsed = codec.parse_notification(bytes.fromhex(frame))
    kind = expected["kind"]
    if kind == "checksum_rejected":
        assert parsed is None
    elif kind == "system":
        assert isinstance(parsed, codec.SystemState)
        if expected.get("seats"):
            layout, motors, stored, _ = codec.MODELS[parsed.code]
            assert motors == expected["motors"]
            assert list(stored) == [seat["addr"] for seat in expected["seats"]]
            for seat in expected["seats"]:
                flags = parsed.flags[seat["addr"]]
                assert (bool(flags & 1), bool(flags & 2), bool(flags & 4)) == (
                    seat["cup"],
                    seat["base"],
                    seat["read"],
                )
        else:
            assert parsed.code not in codec.MODELS
    elif kind == "device":
        assert isinstance(parsed, codec.DeviceState)
        for field in ("read_brightness", "read_on", "cup_on", "base_brightness", "base_on"):
            assert getattr(parsed, field) == expected[field]
        assert parsed.rgb == tuple(expected["rgb"])
    elif kind == "ripple":
        assert isinstance(parsed, codec.RippleState)
        assert parsed.counters == tuple(
            expected.get("raw_frame_order", expected.get("display_order"))
        )
        assert (parsed.counters[0], parsed.counters[2], parsed.counters[1]) == tuple(
            expected["callback_order"]
        )


def controller(profile="synargy"):
    coordinator = _FactoryCoordinator()
    coordinator.handle_controller_state_updates = MagicMock()
    coordinator.clear_position_feedback = MagicMock()
    ctrl = SmartComfortController(coordinator, replace(PROFILES[profile], notify_delay_ms=0))
    return ctrl


def session(ctrl):
    """The coordinator's part of startup: it subscribes through the controller."""

    async def subscribe():
        await ctrl.start_notify()

    return MagicMock(async_start_notify=subscribe)


def system(ctrl, code=0x89, flags=(7, 7, 7)):
    ctrl._notification(
        MagicMock(), bytearray(codec.checked(bytes((0xA0, 0xB1, 0x56, code, *flags))))
    )
    ctrl._ready = True


@pytest.mark.parametrize("profile", PROFILES)
async def test_subscribe_query_then_admit_controls(profile):
    ctrl = controller(profile)
    events = []
    ctrl._coordinator.client = MagicMock(is_connected=True)

    async def subscribe(uuid, callback):
        events.append("subscribe")
        assert uuid == codec.NOTIFY_UUID

    ctrl.client.start_notify = subscribe

    async def write(data, *args, **kwargs):
        events.append(data)
        if data == codec.command("query_system"):
            system(ctrl, 0x84)

    ctrl.write_command = AsyncMock(side_effect=write)
    await ctrl.async_on_connect(session(ctrl))
    assert events == ["subscribe", codec.command("query_system"), codec.command("query_device", 0)]
    assert ctrl.requires_notification_channel
    assert ctrl.selectable_seats == (2, 0)
    assert not ctrl.supports_single_address_pairing
    assert [s.key for s in ctrl.motor_control_specs] == ["head", "back", "lumbar"]
    # Same controller reconnects must subscribe on the new link too.
    await ctrl.async_on_connect(session(ctrl))
    assert events.count("subscribe") == 2


@pytest.mark.parametrize("code", (*codec.MODELS, 0x99))
def test_every_model_and_unknown_retention(code):
    ctrl = controller()
    system(ctrl, code)
    assert ctrl.selectable_seats == (codec.MODELS[code][3] if code in codec.MODELS else ())
    if code == 0x99:
        with pytest.raises(ValueError):
            ctrl._address()
        system(ctrl, 0x84)
        system(ctrl, 0x99, (1, 2, 4))
        assert ctrl.selectable_seats == (2, 0)
        assert ctrl._flags == (1, 2, 4)


@pytest.mark.parametrize("flags", range(8))
@pytest.mark.parametrize("address", range(3))
async def test_every_seat_feature_mask(flags, address):
    ctrl = controller()
    system(ctrl, flags=tuple(flags if i == address else 0 for i in range(3)))
    ctrl.write_command = AsyncMock()
    await ctrl.select_seat(str(address))
    for action, bit in (("cup_on", 1), ("base_on", 2), ("read_on", 4)):
        if flags & bit:
            await ctrl.accessory(action)
            assert ctrl.write_command.call_args.args[0] == codec.command(action, address)
        else:
            with pytest.raises(ValueError):
                await ctrl.accessory(action)
    if flags & 3:
        await ctrl.set_light_color((0, 128, 255))
        await ctrl.set_light_level(100)
    else:
        with pytest.raises(ValueError):
            await ctrl.set_light_color((0, 128, 255))


@pytest.mark.parametrize("profile", PROFILES)
async def test_memory_prepare_and_exactly_one_requested_action(profile):
    ctrl = controller(profile)
    system(ctrl)
    ctrl.session.seat = 2
    ctrl.write_command = AsyncMock()
    for save in (False, True):
        for slot in (1, 2):
            ctrl.write_command.reset_mock()
            await (ctrl.program_memory(slot) if save else ctrl.preset_memory(slot))
            assert [c.args[0] for c in ctrl.write_command.call_args_list] == [
                codec.command("memory_prepare", 2),
                codec.command(f"{'save' if save else 'recall'}_{slot}", 2),
            ]
    with pytest.raises(ValueError):
        await ctrl.preset_memory(3)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(
    "action",
    ("head_up", "head_down", "reclining_up", "reclining_down", "lumbar_up", "lumbar_down", "home"),
)
async def test_cancel_release_captures_zero_and_intended_seat(profile, action):
    ctrl = controller(profile)
    system(ctrl)
    ctrl.session.seat = 2
    calls = []

    async def write(data, *args, **kwargs):
        calls.append((data, kwargs))
        if len(calls) == 1:
            ctrl.session.seat = 0
            ctrl._coordinator.cancel_command.set()
            raise asyncio.CancelledError

    ctrl.write_command = AsyncMock(side_effect=write)
    with patch(
        "custom_components.adjustable_bed.beds.smart_comfort.controller.asyncio.sleep",
        new=AsyncMock(),
    ) as sleep:
        with pytest.raises(asyncio.CancelledError):
            await ctrl.hold_control(action, 1000)
        sleep.assert_awaited_once_with(0.1)
    assert calls[0][0] == codec.command(action, 2)
    assert calls[1][0] == codec.command("stop", 2)
    assert not calls[1][1]["cancel_event"].is_set()


async def test_failed_write_still_releases_and_stop_ignores_cancel():
    ctrl = controller()
    system(ctrl)
    ctrl.write_command = AsyncMock(side_effect=[ConnectionError("link lost"), None])
    with (
        patch(
            "custom_components.adjustable_bed.beds.smart_comfort.controller.asyncio.sleep",
            new=AsyncMock(),
        ),
        pytest.raises(ConnectionError),
    ):
        await ctrl.move_head_up()
    assert ctrl.write_command.call_args.args[0] == codec.command("stop", 0)
    ctrl.write_command = AsyncMock()
    ctrl._coordinator.cancel_command.set()
    await ctrl.stop_all()
    assert not ctrl.write_command.call_args.kwargs["cancel_event"].is_set()


async def test_missing_system_reply_or_unknown_model_fails_setup():
    ctrl = controller()
    ctrl.profile = replace(ctrl.profile, system_timeout_ms=1)
    ctrl.start_notify = AsyncMock()
    ctrl.write_command = AsyncMock()
    with pytest.raises(TimeoutError):
        await ctrl.async_on_connect(session(ctrl))
    assert not ctrl._ready

    async def write(data):
        system(ctrl, 0x99)

    ctrl.write_command = AsyncMock(side_effect=write)
    with pytest.raises(ValueError):
        await ctrl.async_on_connect(session(ctrl))
    # Notification subscription failure also propagates.
    ctrl.start_notify = AsyncMock(side_effect=ConnectionError("notify failed"))
    with pytest.raises(ConnectionError):
        await ctrl.async_on_connect(session(ctrl))


async def test_runtime_write_mode_and_raw_rename():
    ctrl = controller()
    client = MagicMock(is_connected=True)
    ctrl._coordinator.client = client
    characteristic = MagicMock(properties=["write-without-response"])
    client.services.get_characteristic.return_value = characteristic
    ctrl._write_gatt_with_retry = AsyncMock()
    await ctrl.write_command(codec.command("head_up"))
    assert ctrl._write_gatt_with_retry.call_args.kwargs["response"] is False
    characteristic.properties = ["write"]
    await ctrl.write_command(codec.command("head_up"))
    assert ctrl._write_gatt_with_retry.call_args.kwargs["response"] is True
    await ctrl.rename_device("Seat A")
    assert ctrl._write_gatt_with_retry.call_args.args == (codec.NAME_UUID, b"Seat A")


def test_parser_rejects_unsafe_lengths_and_keeps_unsigned_raw_counters():
    for data in (
        b"",
        b"\xff",
        b"\xa0\xb1",
        codec.checked(bytes((0xA0, 0xB1, 0x55)) + bytes(9)),
        codec.checked(b"\xb0\xb1\xb2" + bytes(11)),
    ):
        assert codec.parse_notification(data) is None
    ctrl = controller()
    system(ctrl)
    ctrl._notification(MagicMock(), bytearray.fromhex("b0b1b23c1f00805b2e00802c27008035"))
    # The raw counters stay in diagnostics; the covers show them as positions.
    counters = ctrl.protocol_diagnostics["feedback_counters"]
    assert isinstance(counters, tuple) and counters[0] == 2147491644
    assert [s.key for s in ctrl.controller_state_sensor_specs] == ["smart_comfort_model"]


@pytest.mark.parametrize("address", range(3))
@pytest.mark.parametrize("value", range(4, 101))
def test_every_brightness_value(address, value):
    for action in ("base_brightness", "read_brightness"):
        frame = codec.command(action, address, value=value)
        assert frame[3] == value and frame[5] == 1 << address and sum(frame) % 256 == 255


def test_rename_and_address_bounds():
    for name in ("", "A" * 17, "Sofa ø"):
        with pytest.raises(ValueError):
            codec.rename(name)
    assert codec.rename("A" * 16) == b"A" * 16
    for address in (-1, 3, True):
        with pytest.raises(ValueError):
            codec.command("head_up", address)


async def test_real_write_loop_stops_refresh_and_uses_fresh_neutral_event():
    ctrl = controller()
    system(ctrl)
    ctrl.session.seat = 2
    client = MagicMock(is_connected=True)
    client.services.get_characteristic.return_value = MagicMock(properties=["write"])
    ctrl._coordinator.client = client
    ctrl._coordinator.record_command_trace = MagicMock()
    frames = []

    async def write(uuid, data, **kwargs):
        frames.append(data)
        if len(frames) == 2:
            ctrl._coordinator.cancel_command.set()

    client.write_gatt_char = AsyncMock(side_effect=write)
    with patch(
        "custom_components.adjustable_bed.beds.smart_comfort.controller.asyncio.sleep",
        new=AsyncMock(),
    ):
        await ctrl.hold_control("home", 1000)
    assert frames == [codec.command("home", 2)] * 2 + [codec.command("stop", 2)]
    assert not ctrl.supports_preset_flat


async def test_no_middle_seat_for_three_seat_no_mid_and_ignored_high_bits():
    ctrl = controller()
    system(ctrl, 0x84, (0x80, 0x80, 0x80))
    with pytest.raises(ValueError):
        await ctrl.select_seat("1")
    assert not ctrl.supports_light_color_control
    assert [s.key for s in ctrl.controller_button_specs] == ["smart_comfort_home"]


async def test_primary_rgb_power_uses_selected_seats_actual_accessory():
    ctrl = controller()
    system(ctrl, flags=(1, 2, 4))
    ctrl.write_command = AsyncMock()
    for address, action in ((0, "cup_on"), (1, "base_on")):
        await ctrl.select_seat(str(address))
        await ctrl.lights_on()
        assert ctrl.write_command.call_args.args[0] == codec.command(action, address)
    await ctrl.select_seat("2")
    with pytest.raises(ValueError):
        await ctrl.lights_on()


@pytest.mark.parametrize("profile", PROFILES)
async def test_recreated_controller_keeps_selected_seat_and_revalidates_model(profile):
    ctrl = controller(profile)
    system(ctrl)
    ctrl.write_command = AsyncMock()
    await ctrl.select_seat("2")
    rebuilt = SmartComfortController(ctrl._coordinator, ctrl.profile)
    system(rebuilt)
    rebuilt.write_command = AsyncMock()
    with patch(
        "custom_components.adjustable_bed.beds.smart_comfort.controller.asyncio.sleep",
        new=AsyncMock(),
    ):
        await rebuilt.move_head_up()
    await rebuilt.preset_memory(1)
    assert rebuilt.session.seat == 2
    assert [call.args[0] for call in rebuilt.write_command.call_args_list] == [
        codec.command("head_up", 2),
        codec.command("stop", 2),
        codec.command("memory_prepare", 2),
        codec.command("recall_1", 2),
    ]
    # A changed model must never reuse a now-unaddressable seat.
    changed = SmartComfortController(ctrl._coordinator, ctrl.profile)
    system(changed, 0x02)
    assert changed.session.seat == 0
    # Address and app profile keep independent session boundaries.
    ctrl._coordinator.address = "00:11:22:33:44:55"
    separate = SmartComfortController(ctrl._coordinator, ctrl.profile)
    system(separate)
    assert separate.session.seat == 0


@pytest.mark.parametrize("profile", PROFILES)
async def test_coordinator_cancellation_drains_delay_and_neutral_write(profile):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl = controller(profile)
    system(ctrl)
    ctrl.session.seat = 2
    client = MagicMock(is_connected=True)
    client.services.get_characteristic.return_value = MagicMock(properties=["write"])
    ctrl._coordinator.client = client
    ctrl._coordinator.record_command_trace = MagicMock()
    frames = []
    client.write_gatt_char = AsyncMock(side_effect=lambda uuid, data, **kwargs: frames.append(data))
    release_started = asyncio.Event()
    finish_delay = asyncio.Event()
    real_sleep = asyncio.sleep

    async def sleep(delay):
        assert delay == 0.1
        release_started.set()
        await finish_delay.wait()

    with patch(
        "custom_components.adjustable_bed.beds.smart_comfort.controller.asyncio.sleep", new=sleep
    ):
        operation = asyncio.create_task(ctrl.hold_control("home", 100))
        waiter = asyncio.create_task(
            AdjustableBedCoordinator._async_wait_for_controller_operation(
                ctrl._coordinator,
                operation,
                cancel_event=ctrl._coordinator.cancel_command,
                operation_name="test_home",
                raise_on_cancel=False,
            )
        )
        await release_started.wait()
        ctrl._coordinator.cancel_command.set()
        # Let the actual coordinator waiter cancel the operation in its release delay.
        for _ in range(3):
            await real_sleep(0)
        assert operation.cancelling()
        ctrl.session.seat = 0
        operation.cancel()  # A second cancellation must not abandon the cleanup task.
        await real_sleep(0)
        assert not waiter.done()
        assert frames == [codec.command("home", 2)]
        finish_delay.set()
        await waiter
    assert frames == [codec.command("home", 2), codec.command("stop", 2)]


@pytest.mark.parametrize("profile", PROFILES)
def test_reading_brightness_appears_only_after_reading_capability(profile):
    ctrl = controller(profile)
    assert ctrl.controller_number_specs == ()
    system(ctrl, flags=(1, 2, 3))
    assert ctrl.controller_number_specs == ()
    system(ctrl, flags=(1, 4, 3))
    assert [spec.key for spec in ctrl.controller_number_specs] == ["smart_comfort_read_brightness"]


async def test_cup_and_reading_lights_are_switches_beside_the_base_light():
    ctrl = controller()
    system(ctrl, flags=(1 | 2, 4, 0))
    ctrl.write_command = AsyncMock()
    switches = {s.key: s for s in ctrl.controller_switch_specs}
    assert set(switches) == {"smart_comfort_cup", "smart_comfort_read"}
    await ctrl.select_seat("0")
    await switches["smart_comfort_cup"].set_fn(ctrl, True)
    assert ctrl.write_command.call_args.args[0] == codec.command("cup_on", 0)
    await ctrl.select_seat("1")
    await switches["smart_comfort_read"].set_fn(ctrl, False)
    assert ctrl.write_command.call_args.args[0] == codec.command("read_off", 1)
    # Without a base light the light entity already drives the cup holder light.
    bare = controller()
    system(bare, flags=(1, 0, 0))
    assert bare.controller_switch_specs == ()


# Position reports: head, reclining and lumbar counters in frame order (#628).
HOME = "b0b1b20000008000000080000000806c"
MID = "b0b1b29e0f00802d17008096130080d2"
FULL = "b0b1b23c1f00805b2e00802c27008035"  # frozen SYNERGY vector
PAST_FULL = "b0b1b20020008000300080ffffffffa0"
BELOW_HOME = "b0b1b2ffffff7f000000000000000070"
HOME_FULL_FULL = "b0b1b2000000805b2e00802c27008090"  # frozen SYNARGY vector: imgpos153
SYSTEM_03 = "a0b156030102044e"  # frozen: single seat, three motors


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (HOME, (0, 0, 0)),
        (MID, (50, 100 * 5933 / 11867, 50)),
        (FULL, (100, 100, 100)),
        (PAST_FULL, (100, 100, 100)),
        (BELOW_HOME, (0, 0, 0)),
        (HOME_FULL_FULL, (0, 100, 100)),
    ],
)
def test_counters_scale_to_the_apps_travel_percentages(frame, expected):
    state = codec.parse_notification(bytes.fromhex(frame))
    assert isinstance(state, codec.RippleState)
    assert state.percentages == pytest.approx(expected)


async def _connected_seat(hass, client, monkeypatch, profile, **data):
    """Connect a real coordinator; return it and a way to deliver a notification."""
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.smart_comfort import controller as module
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_MOTOR_COUNT, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    monkeypatch.setattr(module, "SYNARGY", replace(module.SYNARGY, notify_delay_ms=0))
    callbacks = {}

    def notify(frame):
        callbacks[codec.NOTIFY_UUID](MagicMock(), bytearray.fromhex(frame))

    async def subscribe(uuid, callback):
        callbacks[uuid] = callback

    async def write(_uuid, frame, **_kwargs):
        if frame == codec.command("query_system"):
            notify(SYSTEM_03)

    client.start_notify = AsyncMock(side_effect=subscribe)
    client.write_gatt_char = AsyncMock(side_effect=write)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:5C",
            CONF_NAME: "Seat",
            CONF_BED_TYPE: f"smart_comfort_{profile}",
            CONF_MOTOR_COUNT: 3,
            **data,
        },
        unique_id="AA:BB:CC:DD:EE:5C",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    assert isinstance(coordinator.controller, SmartComfortController)
    return coordinator, notify


@pytest.mark.usefixtures("mock_coordinator_connected")
@pytest.mark.parametrize("profile", PROFILES)
async def test_covers_show_reported_positions_without_a_saved_choice(
    hass, mock_bleak_client, monkeypatch, profile
):
    """An entry from before positions were read stores no choice, so it reads them."""
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.services import _position_config
    from tests.error_helpers import raises_key

    coordinator, notify = await _connected_seat(hass, mock_bleak_client, monkeypatch, profile)
    notify(MID)
    assert coordinator.position_data == pytest.approx(
        {"head": 50, "back": 100 * 5933 / 11867, "lumbar": 50}
    )
    notify(PAST_FULL)
    covers = {
        spec.translation_key: AdjustableBedCover(coordinator, _build_cover_description(spec))
        for spec in coordinator.controller.motor_control_specs
    }
    assert {key: cover.current_cover_position for key, cover in covers.items()} == {
        "head": 100,
        "smart_comfort_reclining": 100,
        "lumbar": 100,
    }
    notify(HOME)
    assert all(cover.is_closed for cover in covers.values())
    # The apps show positions only; nothing can be told to seek one.
    assert coordinator.controller.position_number_specs == ()
    for motor in ("head", "back", "legs", "lumbar"):
        with raises_key("invalid_motor_for_bed_type", ServiceValidationError):
            _position_config(coordinator, coordinator.controller, motor, 50)


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_positions_stay_unread_when_turned_off(hass, mock_bleak_client, monkeypatch):
    from custom_components.adjustable_bed.const import CONF_DISABLE_ANGLE_SENSING

    coordinator, notify = await _connected_seat(
        hass, mock_bleak_client, monkeypatch, "synergy", **{CONF_DISABLE_ANGLE_SENSING: True}
    )
    notify(MID)
    assert coordinator.position_data == {}
    counters = coordinator.controller.protocol_diagnostics["feedback_counters"]
    assert counters == (0x80000F9E, 0x8000172D, 0x80001396)


@pytest.mark.parametrize("profile", PROFILES)
async def test_configure_offers_reading_positions_and_saves_it_off(hass, profile):
    """Reading is on without a saved choice; the app's own settings stay hidden."""
    from custom_components.adjustable_bed.bed_traits import reads_positions
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_COUNT,
        CONF_READ_POSITIONS,
    )
    from custom_components.adjustable_bed.profile_id import with_profile_ids
    from tests.test_setup_questions import entry_for

    entry = entry_for(
        hass,
        with_profile_ids(
            {
                CONF_BED_TYPE: f"smart_comfort_{profile}",
                "address": "AA:BB:CC:DD:EE:5C",
                CONF_MOTOR_COUNT: 3,
                "has_massage": False,
            }
        ),
    )
    assert reads_positions(entry.data)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    shown = {marker.schema for marker in form["data_schema"].schema}
    assert CONF_READ_POSITIONS in shown and CONF_MOTOR_COUNT not in shown
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await flow._async_options_form({CONF_READ_POSITIONS: False}, step_id="settings")
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True
    assert not reads_positions(entry.data)


async def test_another_seat_starts_without_the_previous_seats_positions():
    ctrl = controller()
    system(ctrl)
    ctrl.write_command = AsyncMock()
    clear = ctrl._coordinator.clear_position_feedback
    await ctrl.select_seat("0")  # already selected: a requery, not another seat
    clear.assert_not_called()
    await ctrl.select_seat("2")
    clear.assert_called_once_with(("head", "back", "lumbar"))


@pytest.mark.parametrize("profile", PROFILES)
async def test_only_memory_recall_is_followed(profile):
    ctrl = controller(profile)
    system(ctrl)
    ctrl.write_command = AsyncMock()
    ctrl.follow_autonomous_move = AsyncMock()
    await ctrl.program_memory(1)
    with patch(
        "custom_components.adjustable_bed.beds.smart_comfort.controller.asyncio.sleep",
        new=AsyncMock(),
    ):
        await ctrl.hold_control("home", 100)
        await ctrl.move_back_up()
    ctrl.follow_autonomous_move.assert_not_awaited()
    await ctrl.preset_memory(2)
    ctrl.follow_autonomous_move.assert_awaited_once()
    assert ctrl.write_command.call_args.args[0] == codec.command("recall_2", 0)
