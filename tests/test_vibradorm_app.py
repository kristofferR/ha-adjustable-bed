"""Frozen row031 vectors and real controller delivery/lifecycle behavior."""

from __future__ import annotations

import asyncio
from itertools import product
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.vibradorm_app import (
    CBI,
    COMMAND,
    INFO_FIELDS,
    LIGHT,
    RESPONSE,
    VibradormAppController,
    async_prepare_vibradorm_app_pairing,
    decode_standard_info,
    parse_article,
    parse_sync,
    validate_vibradorm_app_profile,
)
from custom_components.adjustable_bed.light import (
    LIGHT_DESCRIPTION,
    AdjustableBedOnOffLight,
)
from custom_components.adjustable_bed.vibradorm_app_state import (
    VibradormAppFloorIntent,
    VibradormAppTimerIntent,
)


def make_controller(
    control: int | str = 2, *, app: str = "caresse", features: bool = False
) -> VibradormAppController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_count = 4
    coordinator.client = MagicMock(
        is_connected=True,
        services=[
            MagicMock(
                uuid="unrelated-service-membership-is-not-a-source-requirement",
                characteristics=[
                    MagicMock(uuid=uuid, handle=index + 1, properties=properties)
                    for index, (uuid, properties) in enumerate(
                        [
                            (COMMAND, ["write"]),
                            (CBI, ["write", "write-without-response"]),
                            (LIGHT, ["write"]),
                            (RESPONSE, ["notify"]),
                            *((uuid, ["read"]) for _, uuid in INFO_FIELDS),
                        ]
                    )
                ],
            )
        ],
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock(return_value=b" value ")
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return VibradormAppController(
        coordinator,
        app_profile=app,
        control_type=control,
        restored=app == "caresse" and (control != 2 or features),
        floor_light=True if features else None,
        rgb=features,
        massage=features,
    )


def written(controller: VibradormAppController) -> list[str]:
    return [call.args[1].hex() for call in controller.client.write_gatt_char.call_args_list]


PROFILE_VECTORS = (
    (-1, ("head", "back", "legs", "feet"), 6, False),
    (0, ("back", "legs"), 6, False),
    (1, ("head", "back", "legs", "feet"), 6, False),
    (2, ("back", "legs"), 0, True),
    (3, ("head", "back", "legs"), 3, True),
    (4, ("head", "back", "legs"), 6, False),
    (5, ("back", "legs"), 6, False),
    (6, ("head", "back", "legs"), 6, False),
    (7, ("head", "back", "legs", "feet"), 6, False),
    ("other", (), 6, False),
)


@pytest.mark.parametrize(("control", "groups", "slots", "basic"), PROFILE_VECTORS)
@pytest.mark.parametrize("features", [False, True])
def test_explicit_restored_profiles_and_no_generic_axis_fallback(
    control, groups, slots, basic, features
):
    c = make_controller(control, features=features)
    assert c.profile.groups == groups
    assert tuple(s.key for s in c.motor_control_specs) == groups
    assert all(s.scheduler_resource == "*" for s in c.motor_control_specs)
    assert c.memory_slot_count == slots
    assert c.supports_memory_programming is not basic
    assert c.requires_notification_channel is not basic
    assert c.supports_lights is features
    assert c.supports_light_toggle_control is features
    assert c.supports_massage is features
    assert c.supports_head_massage_toggle_control is features
    assert not c.supports_position_feedback
    assert not c.supports_preset_flat
    assert not c.supports_simultaneous_movement
    assert not c.supports_light_color_control
    assert not c.supports_light_state_feedback
    assert not c.supports_massage_intensity_control
    assert not c.supports_massage_timer
    assert len(c.controller_select_specs) == (3 if features else 0)
    assert len(c.controller_number_specs) == (3 if features else 0)


@pytest.mark.parametrize("control", [5, 7])
def test_werkmeister_own_selector_scope(control):
    c = make_controller(control, app="werkmeister")
    assert c.supports_lights and not c.supports_massage
    assert ("sync" in c.held_control_options) == (control == 7)
    assert c.light_level_max == 8
    assert c.light_level_min == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"app_profile": "unknown", "control_type": 2},
        {"app_profile": "caresse", "control_type": True},
        {"app_profile": "caresse", "control_type": 99, "restored": True},
        {"app_profile": "caresse", "control_type": 3},
        {"app_profile": "caresse", "control_type": 2, "rgb": True},
        {"app_profile": "werkmeister", "control_type": 3},
        {"app_profile": "werkmeister", "control_type": 5, "rgb": True},
        {"app_profile": "werkmeister", "control_type": 7, "floor_light": False},
    ],
)
def test_invalid_profile_before_ble(kwargs):
    with pytest.raises(ValueError):
        validate_vibradorm_app_profile(**kwargs)


MOTOR_VECTORS = (
    ("head_up", "03"),
    ("head_down", "02"),
    ("back_up", "0b"),
    ("back_down", "0a"),
    ("legs_up", "09"),
    ("legs_down", "08"),
    ("feet_up", "05"),
    ("feet_down", "04"),
    ("all_up", "10"),
    ("all_down", "00"),
)
MEMORY_VECTORS = ((1, "0e"), (2, "0f"), (3, "0c"), (4, "1a"), (5, "1b"), (6, "1c"))


@pytest.mark.parametrize(("control", "groups", "slots", "basic"), PROFILE_VECTORS)
@pytest.mark.parametrize("toggle", [0, 0x8000])
@pytest.mark.asyncio
async def test_all_motor_recall_routes_same_packet_refresh_fresh_stop(
    control, groups, slots, basic, toggle
):
    c = make_controller(control)
    vectors = [
        (action, code)
        for action, code in MOTOR_VECTORS
        if action.rsplit("_", 1)[0] in groups or action.startswith("all_") and groups
    ]
    vectors += [(f"memory_{slot}", code) for slot, code in MEMORY_VECTORS if slot <= slots]
    for action, code in vectors:
        c._toggle = toggle
        c._coordinator.cancel_command.clear()
        c.client.write_gatt_char.reset_mock()
        count = 0

        async def deliver(_char, _packet, **_kwargs):
            nonlocal count
            count += 1
            if count == 2:
                c._coordinator.cancel_command.set()

        c.client.write_gatt_char.side_effect = deliver
        with patch("asyncio.sleep", new=AsyncMock()), pytest.raises(asyncio.CancelledError):
            await c.hold_control(action, 100)
        expected = code if basic else f"{(int(code, 16) | toggle):04x}"
        assert written(c) == [expected, expected, "ff" if basic else "00ff"]
        assert c._toggle == toggle ^ 0x8000
        assert all(call.kwargs["response"] for call in c.client.write_gatt_char.call_args_list)


@pytest.mark.parametrize(("slot", "opcode"), MEMORY_VECTORS)
@pytest.mark.parametrize("toggle", [0, 0x8000])
@pytest.mark.asyncio
async def test_nine_frame_save_wrong_receiver_literal_slot_and_four_stops(slot, opcode, toggle):
    c = make_controller(7)
    c._toggle = toggle
    with patch("asyncio.sleep", new=AsyncMock()):
        await c.program_memory(slot)
    first, second = ("000d", "800d") if toggle == 0 else ("800d", "000d")
    assert written(c) == [first, second, first, second, "00" + opcode, *(["00ff"] * 4)]
    assert c._toggle == toggle ^ 0x8000


@pytest.mark.parametrize(
    "failure", [ConnectionError("delivery"), TimeoutError("transport timeout")]
)
@pytest.mark.asyncio
async def test_failed_save_stops_four_times_preserves_error_and_consumed_intent(failure):
    c = make_controller(7)
    c.client.write_gatt_char.side_effect = [failure, None, None, None, None]
    with patch("asyncio.sleep", new=AsyncMock()), pytest.raises(type(failure), match=str(failure)):
        await c.program_memory(1)
    assert written(c) == ["000d", *(["00ff"] * 4)]
    assert c._toggle == 0x8000


@pytest.mark.asyncio
async def test_real_hold_deadline_release_and_external_task_cancellation():
    c = make_controller(7)
    times = []

    async def deliver(_char, data, **_kwargs):
        if data != b"\x00\xff":
            times.append(asyncio.get_running_loop().time())

    c.client.write_gatt_char.side_effect = deliver
    start = asyncio.get_running_loop().time()
    await c.hold_control("back_up", 220)
    assert 2 <= len(times) <= 3
    assert all(t < start + 0.22 for t in times)
    assert written(c)[-1] == "00ff"
    c.client.write_gatt_char.reset_mock()
    task = asyncio.create_task(c.hold_control("back_up", 5000))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(c)[-1] == "00ff"


@pytest.mark.asyncio
async def test_transport_timeout_is_not_a_successful_host_deadline():
    c = make_controller(7)
    c.client.write_gatt_char.side_effect = [TimeoutError("transport"), None]
    with pytest.raises(TimeoutError, match="transport"):
        await c.hold_control("back_up", 100)
    assert written(c) == ["000b", "00ff"]


@pytest.mark.parametrize("control", [2, 7])
@pytest.mark.parametrize("extension", [False, True])
@pytest.mark.parametrize("toggle", [0, 0x8000])
@pytest.mark.asyncio
async def test_floor_exact_routes_execution_toggle_timer_pending(control, extension, toggle):
    c = make_controller(control, features=True)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        light_extension=extension,
    )
    c._toggle = toggle
    await c.set_light_timer("12 min")
    assert written(c) == []
    await c.set_light_level(6)
    raw = "06" if extension else "c0"
    if control == 2 and not extension:
        assert written(c) == [raw + "000c"]
        assert c._toggle == toggle
        assert c.client.write_gatt_char.call_args.args[0].uuid == LIGHT
    else:
        header = (0x1011 if control == 7 and extension else 0x11) | toggle
        assert written(c) == [f"{header:04x}" + raw + "0c"]
        assert c._toggle == toggle
    c.client.write_gatt_char.reset_mock()
    await c.lights_toggle()
    assert c._toggle == toggle ^ 0x8000
    assert written(c) == (
        ["00000c"]
        if control == 2 and not extension
        else [f"{((0x1011 if control == 7 and extension else 0x11) | (toggle ^ 0x8000)):04x}000c"]
    )
    await c.set_light_timer("Off")
    assert c._timer_minutes == 12 and not c._timer_enabled


@pytest.mark.asyncio
async def test_nonextended_level_eight_is_raw200_and_positive_slider_denies_off():
    c = make_controller(7, features=True)
    await c.set_light_level(8)
    assert written(c) == ["0011c800"]
    for value in (0, 9, 1.5, True):
        with pytest.raises(ValueError):
            await c.set_light_level(value)
    await c.lights_off()
    assert written(c)[-1] == "80110000"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\x00 Model \x00", "Model"),
        (b"A\x00B", "A\x00B"),
        (bytes(range(33)), ""),
        (b"\xc2\xa0X\xc2\xa0", "\xa0X\xa0"),
        (b"\xff", "\ufffd"),
        (b"", ""),
    ],
)
def test_java_edge_trim_utf8(raw, expected):
    assert decode_standard_info(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\x21\xa0\xc8 A\x00 ", " A\x00 "),
        (b"\x21\xa0\xc8X", None),
        (b"\x21\xa0\xc8XY", "XY"),
        (b"\x21\xa0\xc7XY", None),
    ],
)
def test_article_exact_prefix_minimum_and_no_trim(raw, expected):
    assert parse_article(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"\x20\x3f\x40", True),
        (b"\x20\x3f\x80", False),
        (b"\x3f\x40\x00", True),
        (b"\x3f\x00\xff", False),
        (b"\x3f\x40", None),
        (b"\x20\x40\x40", None),
    ],
)
def test_sync_parser_only_supported_prefixes(raw, expected):
    assert parse_sync(raw) is expected


@pytest.mark.parametrize(
    ("control", "app", "requests"),
    [
        (2, "caresse", 0),
        (3, "caresse", 0),
        (4, "caresse", 0),
        ("other", "caresse", 0),
        (5, "werkmeister", 3),
        (6, "caresse", 3),
        (7, "werkmeister", 3),
    ],
)
@pytest.mark.asyncio
async def test_before_pair_order_five_reads_three_reply_gated_requests_and_cleanup(
    control, app, requests
):
    c = make_controller(control, app=app)
    client = c.client
    events = []
    callback = None

    async def subscribe(_char, cb):
        nonlocal callback
        callback = cb
        events.append("subscribe")

    async def read(char):
        events.append(char.uuid)
        return b" value "

    async def write(char, data, **_kwargs):
        events.append(data.hex())
        assert callback is not None
        callback(char, bytearray(b"unrelated"))
        callback(char, bytearray(b"\x21\xa0\xc8 article "))

    client.start_notify.side_effect = subscribe
    client.read_gatt_char.side_effect = read
    client.write_gatt_char.side_effect = write
    metadata = await async_prepare_vibradorm_app_pairing(
        client, app, control, deadline=asyncio.get_running_loop().time() + 1
    )
    assert (
        events
        == ([] if control in (2, 3) else ["subscribe"])
        + [uuid for _, uuid in INFO_FIELDS]
        + ["01a0c8"] * requests
    )
    assert metadata.model == metadata.firmware == metadata.software == "value"
    assert metadata.main_firmware_article == (" article " if requests else None)
    assert client.stop_notify.await_count == (0 if control in (2, 3) else 1)
    assert not client.pair.called
    assert c._toggle == 0


@pytest.mark.asyncio
async def test_info_unrelated_reply_deadline_and_cancel_cleanup_no_extra_writes():
    c = make_controller(7)
    result = asyncio.create_task(
        async_prepare_vibradorm_app_pairing(
            c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() + 0.03
        )
    )
    with pytest.raises(TimeoutError):
        await result
    assert written(c) == ["01a0c8"]
    c.client.stop_notify.assert_awaited_once()
    c.client.write_gatt_char.reset_mock()
    cancellation = asyncio.Event()
    cancellation.set()
    with pytest.raises(asyncio.CancelledError):
        await async_prepare_vibradorm_app_pairing(
            c.client,
            "werkmeister",
            7,
            deadline=asyncio.get_running_loop().time() + 1,
            cancel_event=cancellation,
        )
    assert written(c) == []


@pytest.mark.asyncio
async def test_failed_info_read_aborts_remaining_reads_and_stops_subscription():
    c = make_controller(7)
    c.client.read_gatt_char.side_effect = [b"name", OSError("read failed")]
    with pytest.raises(OSError):
        await async_prepare_vibradorm_app_pairing(
            c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() + 1
        )
    assert c.client.read_gatt_char.await_count == 2
    assert written(c) == []
    c.client.stop_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_startup_no_first_bond_replay_and_explicit_info_publish():
    c = make_controller(4)
    await c.async_discover_capabilities()
    await c.start_notify()
    assert not c.client.read_gatt_char.called and written(c) == []
    await c.refresh_device_info()
    assert c.client.start_notify.await_count == 1
    c._coordinator.handle_controller_state_update.assert_any_call("vibradorm_app_model", "value")
    assert c._metadata.model == "value"
    assert c._article_reply is None
    await c.stop_notify()
    assert not c._subscribed


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.asyncio
async def test_werkmeister_sync_query_reply_hold_and_release_late_reply_no_restart(active):
    c = make_controller(7, app="werkmeister")
    await c.start_notify()
    char = c.client.services[0].characteristics[3]

    async def write(_char, data, **_kwargs):
        if data[-1:] == b"\x3f":
            c._notification(char, bytearray((0x20, 0x3F, 0x40 if active else 0)))
        elif data != b"\x00\xff":
            c._coordinator.cancel_command.set()

    c.client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await c.hold_control("sync", 100)
    assert written(c) == ["003d3f", "8019" if active else "8018", "00ff"]
    assert c._sync_reply is None
    c._notification(char, bytearray((0x20, 0x3F, 0x40)))
    assert len(written(c)) == 3
    assert c._sync_observed is True


@pytest.mark.parametrize("missing", [COMMAND, RESPONSE])
@pytest.mark.asyncio
async def test_exact_roles_missing_and_no_fallback(missing):
    c = make_controller(2 if missing == COMMAND else 7)
    chars = c.client.services[0].characteristics
    chars[:] = [char for char in chars if char.uuid != missing]
    with pytest.raises(ValueError):
        await c.async_discover_capabilities()


@pytest.mark.asyncio
async def test_write_mode_host_property_policy_and_no_basic_notification():
    c = make_controller(2)
    await c.start_notify()
    assert not c.client.start_notify.called
    c = make_controller(7)
    c.client.services[0].characteristics[1].properties = ["write-without-response"]
    await c.stop_all()
    assert c.client.write_gatt_char.call_args.kwargs["response"] is False
    c.client.services[0].characteristics[1].properties = ["read"]
    with pytest.raises(ValueError):
        await c.stop_all()


@pytest.mark.asyncio
async def test_immutable_specs_callbacks_dispatch_side_bound_live_controller():
    c = make_controller(2, features=True)
    for spec in c.controller_button_specs:
        assert spec.translation_key == spec.key
    select = next(s for s in c.controller_select_specs if s.key.endswith("mood_effect"))
    number = next(s for s in c.controller_number_specs if s.key.endswith("floor_timer_minutes"))
    observed = []

    async def delivery(_char, _packet, **_kwargs):
        observed.append(c.command_side)

    c.client.write_gatt_char.side_effect = delivery
    await select.select_fn(c.bind_side("right"), "sunrise")
    await number.set_fn(c.bind_side("right"), 17)
    assert observed == ["right"]
    assert c._timer_minutes == 17 and not c._timer_enabled
    assert c.command_side is None


# Literal fixtures exported by the accepted smali repair verifier, independent
# of integration builders; no machine-local corpus is needed to run these.
MASSAGE_ARTIFACT_VECTORS = [
    {
        "id": "MR001",
        "basic": True,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 0,
        "setup_tap": "none",
        "action": "fresh individual",
        "expected_bytes": ["00300001000000000000"],
    },
    {
        "id": "MR002",
        "basic": True,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 0,
        "setup_tap": "none",
        "action": "fresh automatic",
        "expected_bytes": ["00300101030300000000"],
    },
    {
        "id": "MR003",
        "basic": True,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "automatic",
        "action": "automatic to individual",
        "expected_bytes": ["803400", "00300001000000000000"],
    },
    {
        "id": "MR004",
        "basic": True,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "individual",
        "action": "individual to automatic",
        "expected_bytes": ["803400", "00300101030300000000"],
    },
    {
        "id": "MR005",
        "basic": True,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "automatic",
        "action": "automatic off",
        "expected_bytes": ["803400"],
    },
    {
        "id": "MR006",
        "basic": True,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "individual",
        "action": "individual off",
        "expected_bytes": ["803400"],
    },
    {
        "id": "MR007",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["00300001000000000000"],
    },
    {
        "id": "MR008",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["00300001000000000000"],
    },
    {
        "id": "MR009",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["00300001000500000000"],
    },
    {
        "id": "MR010",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["00300001000300000000"],
    },
    {
        "id": "MR011",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["00300001020000000000"],
    },
    {
        "id": "MR012",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["00300001030000000000"],
    },
    {
        "id": "MR013",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["00300001020500000000"],
    },
    {
        "id": "MR014",
        "basic": True,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["00300001030300000000"],
    },
    {
        "id": "MR015",
        "basic": True,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["803400", "00300101020500000000", "803400", "00300001000000000000"],
    },
    {
        "id": "MR016",
        "basic": True,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["803400", "00300101020500000000", "803400", "00300001020000000000"],
    },
    {
        "id": "MR017",
        "basic": True,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["803400", "00300101020500000000", "803400", "00300001000500000000"],
    },
    {
        "id": "MR018",
        "basic": True,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["803400", "00300101020500000000", "803400", "00300001020500000000"],
    },
    {
        "id": "MR019",
        "basic": True,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "none",
        "action": "fresh individual",
        "expected_bytes": ["80300001000000000000"],
    },
    {
        "id": "MR020",
        "basic": True,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "none",
        "action": "fresh automatic",
        "expected_bytes": ["80300101030300000000"],
    },
    {
        "id": "MR021",
        "basic": True,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "automatic",
        "action": "automatic to individual",
        "expected_bytes": ["003400", "80300001000000000000"],
    },
    {
        "id": "MR022",
        "basic": True,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "individual",
        "action": "individual to automatic",
        "expected_bytes": ["003400", "80300101030300000000"],
    },
    {
        "id": "MR023",
        "basic": True,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "automatic",
        "action": "automatic off",
        "expected_bytes": ["003400"],
    },
    {
        "id": "MR024",
        "basic": True,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "individual",
        "action": "individual off",
        "expected_bytes": ["003400"],
    },
    {
        "id": "MR025",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["80300001000000000000"],
    },
    {
        "id": "MR026",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["80300001000000000000"],
    },
    {
        "id": "MR027",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["80300001000500000000"],
    },
    {
        "id": "MR028",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["80300001000300000000"],
    },
    {
        "id": "MR029",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["80300001020000000000"],
    },
    {
        "id": "MR030",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["80300001030000000000"],
    },
    {
        "id": "MR031",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["80300001020500000000"],
    },
    {
        "id": "MR032",
        "basic": True,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["80300001030300000000"],
    },
    {
        "id": "MR033",
        "basic": True,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["003400", "80300101020500000000", "003400", "80300001000000000000"],
    },
    {
        "id": "MR034",
        "basic": True,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["003400", "80300101020500000000", "003400", "80300001020000000000"],
    },
    {
        "id": "MR035",
        "basic": True,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["003400", "80300101020500000000", "003400", "80300001000500000000"],
    },
    {
        "id": "MR036",
        "basic": True,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["003400", "80300101020500000000", "003400", "80300001020500000000"],
    },
    {
        "id": "MR037",
        "basic": False,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 0,
        "setup_tap": "none",
        "action": "fresh individual",
        "expected_bytes": ["10300001000000000000"],
    },
    {
        "id": "MR038",
        "basic": False,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 0,
        "setup_tap": "none",
        "action": "fresh automatic",
        "expected_bytes": ["10300101030300000000"],
    },
    {
        "id": "MR039",
        "basic": False,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "automatic",
        "action": "automatic to individual",
        "expected_bytes": ["903400", "10300001000000000000"],
    },
    {
        "id": "MR040",
        "basic": False,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "individual",
        "action": "individual to automatic",
        "expected_bytes": ["903400", "10300101030300000000"],
    },
    {
        "id": "MR041",
        "basic": False,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "automatic",
        "action": "automatic off",
        "expected_bytes": ["903400"],
    },
    {
        "id": "MR042",
        "basic": False,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 0,
        "setup_tap": "individual",
        "action": "individual off",
        "expected_bytes": ["903400"],
    },
    {
        "id": "MR043",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["10300001000000000000"],
    },
    {
        "id": "MR044",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["10300001000000000000"],
    },
    {
        "id": "MR045",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["10300001000500000000"],
    },
    {
        "id": "MR046",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["10300001000300000000"],
    },
    {
        "id": "MR047",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["10300001020000000000"],
    },
    {
        "id": "MR048",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["10300001030000000000"],
    },
    {
        "id": "MR049",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["10300001020500000000"],
    },
    {
        "id": "MR050",
        "basic": False,
        "initial_toggle": 0,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["10300001030300000000"],
    },
    {
        "id": "MR051",
        "basic": False,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["903400", "10300101020500000000", "903400", "10300001000000000000"],
    },
    {
        "id": "MR052",
        "basic": False,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["903400", "10300101020500000000", "903400", "10300001020000000000"],
    },
    {
        "id": "MR053",
        "basic": False,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["903400", "10300101020500000000", "903400", "10300001000500000000"],
    },
    {
        "id": "MR054",
        "basic": False,
        "initial_toggle": 32768,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["903400", "10300101020500000000", "903400", "10300001020500000000"],
    },
    {
        "id": "MR055",
        "basic": False,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "none",
        "action": "fresh individual",
        "expected_bytes": ["90300001000000000000"],
    },
    {
        "id": "MR056",
        "basic": False,
        "initial_toggle": 32768,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "none",
        "action": "fresh automatic",
        "expected_bytes": ["90300101030300000000"],
    },
    {
        "id": "MR057",
        "basic": False,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "automatic",
        "action": "automatic to individual",
        "expected_bytes": ["103400", "90300001000000000000"],
    },
    {
        "id": "MR058",
        "basic": False,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "individual",
        "action": "individual to automatic",
        "expected_bytes": ["103400", "90300101030300000000"],
    },
    {
        "id": "MR059",
        "basic": False,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "automatic",
        "action": "automatic off",
        "expected_bytes": ["103400"],
    },
    {
        "id": "MR060",
        "basic": False,
        "initial_toggle": 0,
        "initial_toggle_before_setup": 32768,
        "setup_tap": "individual",
        "action": "individual off",
        "expected_bytes": ["103400"],
    },
    {
        "id": "MR061",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["90300001000000000000"],
    },
    {
        "id": "MR062",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["90300001000000000000"],
    },
    {
        "id": "MR063",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["90300001000500000000"],
    },
    {
        "id": "MR064",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["90300001000300000000"],
    },
    {
        "id": "MR065",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["90300001020000000000"],
    },
    {
        "id": "MR066",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [0, 0],
        "expected_bytes": ["90300001030000000000"],
    },
    {
        "id": "MR067",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["90300001020500000000"],
    },
    {
        "id": "MR068",
        "basic": False,
        "initial_toggle": 32768,
        "action": "saved individual flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [0, 0],
        "expected_bytes": ["90300001030300000000"],
    },
    {
        "id": "MR069",
        "basic": False,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["103400", "90300101020500000000", "103400", "90300001000000000000"],
    },
    {
        "id": "MR070",
        "basic": False,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": False,
        "saved_zones": [2, 5],
        "expected_bytes": ["103400", "90300101020500000000", "103400", "90300001020000000000"],
    },
    {
        "id": "MR071",
        "basic": False,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": False,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["103400", "90300101020500000000", "103400", "90300001000500000000"],
    },
    {
        "id": "MR072",
        "basic": False,
        "initial_toggle": 0,
        "action": "individual to automatic to individual, saved flags",
        "head_saved": True,
        "foot_saved": True,
        "saved_zones": [2, 5],
        "expected_bytes": ["103400", "90300101020500000000", "103400", "90300001020500000000"],
    },
]

PALETTE_ARTIFACT_VECTORS = [
    ("#008a00", "008a00"),
    ("#00aba9", "00aba9"),
    ("#1ba1e2", "1aa1e2"),
    ("#0050ef", "0050ef"),
    ("#6a00ff", "6a00ff"),
    ("#aa00ff", "aa00ff"),
    ("#f472d0", "f472d0"),
    ("#d80073", "d80073"),
    ("#a20025", "a20024"),
    ("#e51400", "e51300"),
    ("#fa6800", "fa6800"),
    ("#f0a30a", "f0a309"),
    ("#e3c800", "e3c800"),
    ("#825a2c", "825a2c"),
    ("#6d8764", "6d8764"),
    ("#647687", "647687"),
    ("#76708a", "76708a"),
    ("#ffffff", "ffffff"),
]


@pytest.mark.parametrize("vector", MASSAGE_ARTIFACT_VECTORS, ids=lambda row: row["id"])
@pytest.mark.asyncio
async def test_all_72_artifact_massage_saved_state_and_nested_click_vectors(vector):
    c = make_controller(2 if vector["basic"] else 7, features=True)
    c._toggle = vector.get("initial_toggle_before_setup", vector["initial_toggle"])
    setup = vector.get("setup_tap", "none")
    if setup != "none":
        await c.execute_app_action("massage_" + setup)
    if "saved_zones" in vector:
        c._massage.saved_zones = tuple(vector["saved_zones"])
        c._massage.saved_flags = (vector["head_saved"], vector["foot_saved"])
    if vector["action"].startswith("individual to automatic to individual,"):
        # The source fixture begins after the saved-individual enable click.
        c._toggle = vector["initial_toggle"] ^ 0x8000
        await c.execute_app_action("massage_individual")
    c.client.write_gatt_char.reset_mock()
    if vector["action"] in ("fresh automatic", "individual to automatic", "automatic off"):
        await c.execute_app_action("massage_automatic")
    elif vector["action"].startswith("individual to automatic to individual,"):
        await c.execute_app_action("massage_automatic")
        await c.execute_app_action("massage_individual")
    else:
        await c.execute_app_action("massage_individual")
    assert written(c) == vector["expected_bytes"]
    assert all(call.args[0].uuid == CBI for call in c.client.write_gatt_char.call_args_list)


@pytest.mark.parametrize(("palette", "rgb"), PALETTE_ARTIFACT_VECTORS)
@pytest.mark.parametrize("control", [2, 7])
@pytest.mark.parametrize("toggle", [0, 0x8000])
@pytest.mark.asyncio
async def test_all_18_fixed100_palette_outputs_exact_group_and_intent(
    palette, rgb, control, toggle
):
    c = make_controller(control, features=True)
    c._toggle = toggle
    await c.set_mood_palette(palette)
    assert written(c) == [f"{((0x77 if control == 2 else 0x1077) | toggle):04x}0100{rgb}"]
    assert c._toggle == toggle ^ 0x8000
    assert len(c.controller_select_specs[0].options) == 18


@pytest.mark.parametrize("control", [2, 7])
@pytest.mark.parametrize(
    ("speed", "wire"),
    [
        (0, "12"),
        (1, "10"),
        (2, "0e"),
        (3, "0c"),
        (4, "0a"),
        (5, "08"),
        (6, "06"),
        (7, "04"),
        (8, "02"),
    ],
)
@pytest.mark.asyncio
async def test_all_mood_speed_outputs(control, speed, wire):
    c = make_controller(control, features=True)
    await c.set_mood_speed(speed)
    assert written(c) == [("0077" if control == 2 else "1077") + "09" + wire]


@pytest.mark.parametrize("control", [2, 7])
@pytest.mark.parametrize(
    ("effect", "wire"), [("sunrise", "01"), ("rainbow", "02"), ("disco", "03")]
)
@pytest.mark.asyncio
async def test_mood_effect_and_always_extended_toggle(control, effect, wire):
    c = make_controller(control, features=True)
    await c.set_mood_effect(effect)
    await c.execute_app_action("mood_toggle")
    assert written(c) == [("0077" if control == 2 else "1077") + "08" + wire, "9077"]


@pytest.mark.parametrize(
    ("automatic", "individual", "wave", "zone_state"), product((7, 8), (9, 10), (7, 8), (7, 8))
)
@pytest.mark.parametrize("zone", [0, 1])
@pytest.mark.asyncio
async def test_complete_shipped_zone_step_guard_matrix(
    automatic, individual, wave, zone_state, zone
):
    c = make_controller(7, features=True)
    c._massage.automatic, c._massage.individual, c._massage.wave = automatic, individual, wave
    c._massage.zone_states = (zone_state, zone_state)
    # This predicate is bound to the actual fragment's accepted Cartesian guard proof.
    enabled = automatic == 7 and wave == 7 or individual == 9 and zone_state == 7
    if enabled:
        await (c.massage_head_up() if zone == 0 else c.massage_foot_up())
        assert len(written(c)) == 1
        assert c._massage.zones[zone] == 1
    else:
        with pytest.raises(ValueError):
            await (c.massage_head_up() if zone == 0 else c.massage_foot_up())
        assert written(c) == []


@pytest.mark.asyncio
async def test_massage_zone_flags_steps_waves_and_speed_do_not_collapse_modes():
    c = make_controller(7, features=True)
    with pytest.raises(ValueError):
        await c.massage_head_toggle()
    await c.execute_app_action("massage_individual")
    assert c._massage.zones == (0, 0)
    await c.massage_head_toggle()
    await c.massage_head_up()
    assert c._massage.flags == (True, False) and c._massage.zones == (4, 0)
    await c.massage_head_toggle()
    assert c._massage.saved_flags == (True, False) and c._massage.saved_zones == (4, 3)
    with pytest.raises(ValueError):
        await c.set_massage_wave("2")
    await c.execute_app_action("massage_automatic")
    for wave in ("1", "2", "3", "4"):
        await c.set_massage_wave(wave)
    assert c._massage.effect == 4
    for _ in range(10):
        await c.massage_head_down()
    assert c._massage.zones[0] == 1
    for _ in range(10):
        await c.massage_head_up()
    assert c._massage.zones[0] == 5
    await c.set_massage_speed(5)
    assert c._massage.speed == 5
    assert all(packet[:4] != "00ff" for packet in written(c))


@pytest.mark.asyncio
async def test_validation_and_failed_one_shot_no_false_published_success():
    c = make_controller(7, features=True)
    for operation in (
        c.set_mood_speed(8.5),
        c.set_massage_speed(0),
        c.set_mood_palette("#000000"),
        c.set_mood_effect("unknown"),
        c.set_light_timer("61 min"),
        c.hold_control("back_up+legs_up", 100),
        c.hold_control("back_up", 99),
        c.program_memory(7),
    ):
        with pytest.raises(ValueError):
            await operation
    assert written(c) == [] and c._toggle == 0
    c.client.write_gatt_char.side_effect = ConnectionError("failed")
    with pytest.raises(ConnectionError):
        await c.set_mood_effect("sunrise")
    assert c._toggle == 0x8000
    assert not c._coordinator.handle_controller_state_update.called


@pytest.mark.asyncio
async def test_pre_cancelled_floor_level_does_not_construct_command():
    c = make_controller(7, features=True)
    c._coordinator.cancel_command.set()
    await c.set_light_level(1)
    assert c._toggle == 0 and c._floor_level == 0
    assert written(c) == []
    assert not c._coordinator.handle_controller_state_updates.called


@pytest.mark.parametrize(("control", "extension"), [(2, False), (2, True), (7, False), (7, True)])
@pytest.mark.parametrize("initial_level", [0, 3])
@pytest.mark.parametrize("action", ["on", "off", "level", "toggle"])
@pytest.mark.asyncio
async def test_pre_cancelled_floor_actions_preserve_session_intent_and_sequence(
    control, extension, initial_level, action
):
    existing = make_controller(control)
    floor = VibradormAppFloorIntent(level=initial_level, default_level=6)
    timer = VibradormAppTimerIntent(enabled=True, minutes=12)
    c = VibradormAppController(
        existing._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        light_extension=extension,
        floor_intent=floor,
        timer_intent=timer,
    )
    c._toggle = 0x8000
    before = c.get_light_state()
    c._coordinator.cancel_command.set()
    if action == "on":
        await c.lights_on()
    elif action == "off":
        await c.lights_off()
    elif action == "level":
        await c.set_light_level(2)
    else:
        await c.lights_toggle()
    assert written(c) == []
    assert floor.level == initial_level and floor.default_level == 6
    assert timer.enabled and timer.minutes == 12
    assert c._toggle == 0x8000 and c.get_light_state() == before
    c._coordinator.remember_vibradorm_app_floor_default.assert_not_called()
    c._coordinator.handle_controller_state_updates.assert_not_called()
    c._coordinator.record_command_trace.assert_not_called()


@pytest.mark.asyncio
async def test_light_execution_toggle_waits_for_lane_and_cancel_drops_only_execution():
    c = make_controller(7, features=True)
    await c._ble_lock.acquire()
    task = asyncio.create_task(c.set_light_level(2))
    await asyncio.sleep(0)
    assert c._toggle == 0x8000  # Construction consumes once; execution has not begun.
    c._coordinator.cancel_command.set()
    c._ble_lock.release()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert c._toggle == 0x8000 and written(c) == []


@pytest.mark.asyncio
async def test_failed_light_execution_consumes_both_stages_without_state_ack():
    c = make_controller(7, features=True)
    c.client.write_gatt_char.side_effect = OSError("light failed")
    with pytest.raises(OSError):
        await c.set_light_level(2)
    assert c._toggle == 0
    assert c._floor_level == 2  # Source local intent survives failed delivery.
    assert not c._coordinator.handle_controller_state_updates.called


@pytest.mark.asyncio
async def test_failed_nested_massage_keeps_constructed_mode_intent_and_toggle():
    c = make_controller(7, features=True)
    await c.execute_app_action("massage_individual")
    c.client.write_gatt_char.reset_mock()
    c._coordinator.handle_controller_state_updates.reset_mock()
    c.client.write_gatt_char.side_effect = OSError("off delivery failed")
    with pytest.raises(OSError):
        await c.execute_app_action("massage_automatic")
    assert written(c) == ["903400"]
    assert c._massage.automatic == 7 and c._massage.zones == (3, 3)
    assert c._toggle == 0x8000  # Both logical commands were constructed before delivery.
    assert not c._coordinator.handle_controller_state_updates.called


@pytest.mark.asyncio
async def test_cancel_during_release_repeatedly_cannot_suppress_cleanup():
    c = make_controller(7)
    entered = asyncio.Event()
    allow = asyncio.Event()

    async def write(_char, _data, **_kwargs):
        entered.set()
        await allow.wait()

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.stop_all())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    allow.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(c) == ["00ff"]


@pytest.mark.asyncio
async def test_pair_subscription_cleanup_survives_second_cancellation():
    c = make_controller(7)
    entered = asyncio.Event()
    allow = asyncio.Event()

    async def stop(_char):
        entered.set()
        await allow.wait()

    c.client.stop_notify.side_effect = stop
    task = asyncio.create_task(
        async_prepare_vibradorm_app_pairing(
            c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() + 1
        )
    )
    while not c.client.write_gatt_char.called:
        await asyncio.sleep(0)
    task.cancel()
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    allow.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    c.client.stop_notify.assert_awaited_once()
    assert written(c) == ["01a0c8"]


@pytest.mark.asyncio
async def test_outer_deadline_expired_before_helper_no_new_io():
    c = make_controller(7)
    with pytest.raises(TimeoutError):
        await async_prepare_vibradorm_app_pairing(
            c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() - 1
        )
    assert not c.client.start_notify.called
    assert not c.client.read_gatt_char.called
    assert written(c) == []


@pytest.mark.parametrize("uuid", [uuid for _, uuid in INFO_FIELDS])
@pytest.mark.asyncio
async def test_information_exact_read_property_required_and_no_fallback(uuid):
    c = make_controller(2)
    for char in c.client.services[0].characteristics:
        if char.uuid == uuid:
            char.properties = ["write"]
    with pytest.raises(ValueError):
        await async_prepare_vibradorm_app_pairing(
            c.client, "caresse", 2, deadline=asyncio.get_running_loop().time() + 1
        )
    assert not c.client.pair.called and written(c) == []


@pytest.mark.asyncio
async def test_late_article_reply_after_transaction_never_restarts_requests():
    c = make_controller(7)
    await c.start_notify()
    char = c.client.services[0].characteristics[3]

    async def write(_char, _data, **_kwargs):
        c._notification(char, bytearray(b"\x21\xa0\xc8AA"))

    c.client.write_gatt_char.side_effect = write
    await c.refresh_device_info()
    assert written(c) == ["01a0c8"] * 3
    c._notification(char, bytearray(b"\x21\xa0\xc8late"))
    assert written(c) == ["01a0c8"] * 3
    assert c._article_reply is None


def test_cached_metadata_is_only_validated_diagnostic_state_never_profile():
    c = make_controller(2)
    c._coordinator.entry.data = {
        "vibradorm_app_metadata": {
            "model": "Werkmeister",
            "firmware": " CBI ",
            "software": "\x00embedded\x00",
            "main_firmware_article": None,
        }
    }
    c = VibradormAppController(c._coordinator, app_profile="caresse", control_type=2)
    assert c.profile.basic and c.profile.groups == ("back", "legs") and not c.profile.floor_light
    c._coordinator.handle_controller_state_update.assert_any_call("vibradorm_app_firmware", " CBI ")
    c._coordinator.handle_controller_state_update.assert_any_call(
        "vibradorm_app_software", "\x00embedded\x00"
    )
    assert not c.client.read_gatt_char.called
    c._coordinator.entry.data["vibradorm_app_metadata"]["software"] = False
    c._coordinator.handle_controller_state_update.reset_mock()
    c = VibradormAppController(c._coordinator, app_profile="caresse", control_type=2)
    assert c._metadata is None
    assert not c._coordinator.handle_controller_state_update.called


@pytest.mark.parametrize("control", [-1, 0, 1, 2, 3, 4, 5, 6, 7, "other"])
@pytest.mark.parametrize(("floor", "rgb", "massage", "extension"), product((False, True), repeat=4))
def test_independent_persisted_feature_matrix_exact_immutable_specs(
    control, floor, rgb, massage, extension
):
    c = make_controller(control)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=floor,
        rgb=rgb,
        massage=massage,
        light_extension=extension,
    )
    assert c.profile.floor_light is floor
    assert c.profile.rgb is rgb
    assert c.profile.massage is massage
    assert c.profile.light_extension is extension
    assert c.supports_lights is floor
    assert c.supports_light_timer is floor
    assert c.supports_light_level_control is floor
    assert c.supports_head_massage_toggle_control is massage
    assert c.light_level_max == (6 if extension else 8)
    select_keys = {spec.key for spec in c.controller_select_specs}
    assert ("vibradorm_app_mood_palette" in select_keys) is rgb
    assert ("vibradorm_app_mood_effect" in select_keys) is rgb
    assert ("vibradorm_app_massage_wave" in select_keys) is massage
    number_keys = {spec.key for spec in c.controller_number_specs}
    assert ("vibradorm_app_floor_timer_minutes" in number_keys) is floor
    assert ("vibradorm_app_mood_speed" in number_keys) is rgb
    assert ("vibradorm_app_massage_speed" in number_keys) is massage


@pytest.mark.asyncio
async def test_info_nullable_data_empty_and_raw_diagnostics_are_not_angle_feedback():
    assert decode_standard_info(None) == ""
    c = make_controller(7)
    c.client.read_gatt_char.return_value = None
    await c.start_notify()
    char = c.client.services[0].characteristics[3]
    raw = MagicMock()
    c.set_raw_notify_callback(raw)
    c._notification(char, bytearray(b"position or arbitrary bytes"))
    raw.assert_called_once_with(RESPONSE, b"position or arbitrary bytes")
    assert c._sync_observed is None
    assert not c._coordinator.handle_controller_state_update.called


@pytest.mark.asyncio
async def test_cancel_before_pair_helper_has_no_subscription_or_information_io():
    c = make_controller(7)
    event = asyncio.Event()
    event.set()
    with pytest.raises(asyncio.CancelledError):
        await async_prepare_vibradorm_app_pairing(
            c.client,
            "werkmeister",
            7,
            deadline=asyncio.get_running_loop().time() + 1,
            cancel_event=event,
        )
    assert not c.client.start_notify.called
    assert not c.client.stop_notify.called
    assert not c.client.read_gatt_char.called and written(c) == []


@pytest.mark.asyncio
async def test_sync_release_before_reply_and_caresse_dead_sync_gate():
    c = make_controller(7, app="werkmeister")
    await c.start_notify()
    task = asyncio.create_task(c.hold_control("sync", 100))
    while not c.client.write_gatt_char.called:
        await asyncio.sleep(0)
    c._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    char = c.client.services[0].characteristics[3]
    c._notification(char, bytearray(b"\x20\x3f\x40"))
    assert written(c) == ["003d3f", "00ff"]
    for ctrl in (5, 7):
        c = make_controller(ctrl)
        with pytest.raises(ValueError):
            await c.hold_control("sync", 100)
        assert written(c) == []


@pytest.mark.asyncio
async def test_save_cancel_stops_four_with_fresh_event_no_late_slot():
    c = make_controller(7)

    async def deliver(_char, data, **_kwargs):
        if data == b"\x00\x0d":
            c._coordinator.cancel_command.set()

    c.client.write_gatt_char.side_effect = deliver
    with patch("asyncio.sleep", new=AsyncMock()), pytest.raises(asyncio.CancelledError):
        await c.program_memory(6)
    assert written(c) == ["000d", *(["00ff"] * 4)]
    assert c._toggle == 0x8000


@pytest.mark.asyncio
async def test_article_write_failure_cleanup_and_malformed_only_reply_times_out():
    c = make_controller(7)
    c.client.write_gatt_char.side_effect = OSError("article write failed")
    with pytest.raises(OSError):
        await async_prepare_vibradorm_app_pairing(
            c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() + 1
        )
    assert written(c) == ["01a0c8"]
    c.client.stop_notify.assert_awaited_once()
    c = make_controller(7)
    callback = None

    async def subscribe(_char, fn):
        nonlocal callback
        callback = fn

    async def write(char, _data, **_kwargs):
        assert callback is not None
        for data in (b"\x21\xa0\xc8X", b"\x21\xa0\xc7AB", b"anything"):
            callback(char, bytearray(data))

    c.client.start_notify.side_effect = subscribe
    c.client.write_gatt_char.side_effect = write
    with pytest.raises(TimeoutError):
        await async_prepare_vibradorm_app_pairing(
            c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() + 0.03
        )
    assert written(c) == ["01a0c8"]
    c.client.stop_notify.assert_awaited_once()


# CmdLight constructors receive converted raw brightness, not slider levels.
FLOOR_ARTIFACT_VECTORS = [
    ("V0044", False, 0, 0, False, 0, "00110000"),
    ("V0045", False, 0, 0, False, 1, "00110001"),
    ("V0046", False, 0, 0, False, 60, "0011003c"),
    ("V0047", False, 0, 0, True, 0, "10110000"),
    ("V0048", False, 0, 0, True, 1, "10110001"),
    ("V0049", False, 0, 0, True, 60, "1011003c"),
    ("V0053", False, 0, 1, True, 0, "10110100"),
    ("V0054", False, 0, 1, True, 1, "10110101"),
    ("V0055", False, 0, 1, True, 60, "1011013c"),
    ("V0059", False, 0, 6, True, 0, "10110600"),
    ("V0060", False, 0, 6, True, 1, "10110601"),
    ("V0061", False, 0, 6, True, 60, "1011063c"),
    ("V0068", False, 0, 1, False, 0, "00112000"),
    ("V0069", False, 0, 1, False, 1, "00112001"),
    ("V0070", False, 0, 1, False, 60, "0011203c"),
    ("V0074", False, 0, 8, False, 0, "0011c800"),
    ("V0075", False, 0, 8, False, 1, "0011c801"),
    ("V0076", False, 0, 8, False, 60, "0011c83c"),
    ("V0080", False, 0, 7, False, 0, "0011e000"),
    ("V0081", False, 0, 7, False, 1, "0011e001"),
    ("V0082", False, 0, 7, False, 60, "0011e03c"),
    ("V0186", False, 32768, 0, False, 0, "80110000"),
    ("V0187", False, 32768, 0, False, 1, "80110001"),
    ("V0188", False, 32768, 0, False, 60, "8011003c"),
    ("V0189", False, 32768, 0, True, 0, "90110000"),
    ("V0190", False, 32768, 0, True, 1, "90110001"),
    ("V0191", False, 32768, 0, True, 60, "9011003c"),
    ("V0195", False, 32768, 1, True, 0, "90110100"),
    ("V0196", False, 32768, 1, True, 1, "90110101"),
    ("V0197", False, 32768, 1, True, 60, "9011013c"),
    ("V0201", False, 32768, 6, True, 0, "90110600"),
    ("V0202", False, 32768, 6, True, 1, "90110601"),
    ("V0203", False, 32768, 6, True, 60, "9011063c"),
    ("V0210", False, 32768, 1, False, 0, "80112000"),
    ("V0211", False, 32768, 1, False, 1, "80112001"),
    ("V0212", False, 32768, 1, False, 60, "8011203c"),
    ("V0216", False, 32768, 8, False, 0, "8011c800"),
    ("V0217", False, 32768, 8, False, 1, "8011c801"),
    ("V0218", False, 32768, 8, False, 60, "8011c83c"),
    ("V0222", False, 32768, 7, False, 0, "8011e000"),
    ("V0223", False, 32768, 7, False, 1, "8011e001"),
    ("V0224", False, 32768, 7, False, 60, "8011e03c"),
    ("V0331", True, 0, 0, True, 0, "00110000"),
    ("V0332", True, 0, 0, True, 1, "00110001"),
    ("V0333", True, 0, 0, True, 60, "0011003c"),
    ("V0337", True, 0, 1, True, 0, "00110100"),
    ("V0338", True, 0, 1, True, 1, "00110101"),
    ("V0339", True, 0, 1, True, 60, "0011013c"),
    ("V0343", True, 0, 6, True, 0, "00110600"),
    ("V0344", True, 0, 6, True, 1, "00110601"),
    ("V0345", True, 0, 6, True, 60, "0011063c"),
    ("V0370", True, 0, 0, False, 0, "000000"),
    ("V0371", True, 0, 0, False, 60, "00003c"),
    ("V0372", True, 0, 1, False, 0, "200000"),
    ("V0373", True, 0, 1, False, 60, "20003c"),
    ("V0374", True, 0, 8, False, 0, "c80000"),
    ("V0375", True, 0, 8, False, 60, "c8003c"),
    ("V0376", True, 0, 7, False, 0, "e00000"),
    ("V0377", True, 0, 7, False, 60, "e0003c"),
    ("V0473", True, 32768, 0, True, 0, "80110000"),
    ("V0474", True, 32768, 0, True, 1, "80110001"),
    ("V0475", True, 32768, 0, True, 60, "8011003c"),
    ("V0479", True, 32768, 1, True, 0, "80110100"),
    ("V0480", True, 32768, 1, True, 1, "80110101"),
    ("V0481", True, 32768, 1, True, 60, "8011013c"),
    ("V0485", True, 32768, 6, True, 0, "80110600"),
    ("V0486", True, 32768, 6, True, 1, "80110601"),
    ("V0487", True, 32768, 6, True, 60, "8011063c"),
    ("V0512", True, 32768, 0, False, 0, "000000"),
    ("V0513", True, 32768, 0, False, 60, "00003c"),
    ("V0514", True, 32768, 1, False, 0, "200000"),
    ("V0515", True, 32768, 1, False, 60, "20003c"),
    ("V0516", True, 32768, 8, False, 0, "c80000"),
    ("V0517", True, 32768, 8, False, 60, "c8003c"),
    ("V0518", True, 32768, 7, False, 0, "e00000"),
    ("V0519", True, 32768, 7, False, 60, "e0003c"),
]

MASSAGE_PACKET_ARTIFACT_VECTORS = [
    ("V0111", False, 0, [0, 1, 0, 0], "10300001000000000000"),
    ("V0112", False, 0, [0, 1, 1, 5], "10300001010500000000"),
    ("V0113", False, 0, [0, 1, 3, 3], "10300001030300000000"),
    ("V0114", False, 0, [0, 5, 0, 0], "10300005000000000000"),
    ("V0115", False, 0, [0, 5, 1, 5], "10300005010500000000"),
    ("V0116", False, 0, [0, 5, 3, 3], "10300005030300000000"),
    ("V0117", False, 0, [1, 1, 0, 0], "10300101000000000000"),
    ("V0118", False, 0, [1, 1, 1, 5], "10300101010500000000"),
    ("V0119", False, 0, [1, 1, 3, 3], "10300101030300000000"),
    ("V0120", False, 0, [1, 5, 0, 0], "10300105000000000000"),
    ("V0121", False, 0, [1, 5, 1, 5], "10300105010500000000"),
    ("V0122", False, 0, [1, 5, 3, 3], "10300105030300000000"),
    ("V0123", False, 0, [2, 1, 0, 0], "10300201000000000000"),
    ("V0124", False, 0, [2, 1, 1, 5], "10300201010500000000"),
    ("V0125", False, 0, [2, 1, 3, 3], "10300201030300000000"),
    ("V0126", False, 0, [2, 5, 0, 0], "10300205000000000000"),
    ("V0127", False, 0, [2, 5, 1, 5], "10300205010500000000"),
    ("V0128", False, 0, [2, 5, 3, 3], "10300205030300000000"),
    ("V0129", False, 0, [3, 1, 0, 0], "10300301000000000000"),
    ("V0130", False, 0, [3, 1, 1, 5], "10300301010500000000"),
    ("V0131", False, 0, [3, 1, 3, 3], "10300301030300000000"),
    ("V0132", False, 0, [3, 5, 0, 0], "10300305000000000000"),
    ("V0133", False, 0, [3, 5, 1, 5], "10300305010500000000"),
    ("V0134", False, 0, [3, 5, 3, 3], "10300305030300000000"),
    ("V0135", False, 0, [4, 1, 0, 0], "10300401000000000000"),
    ("V0136", False, 0, [4, 1, 1, 5], "10300401010500000000"),
    ("V0137", False, 0, [4, 1, 3, 3], "10300401030300000000"),
    ("V0138", False, 0, [4, 5, 0, 0], "10300405000000000000"),
    ("V0139", False, 0, [4, 5, 1, 5], "10300405010500000000"),
    ("V0140", False, 0, [4, 5, 3, 3], "10300405030300000000"),
    ("V0253", False, 32768, [0, 1, 0, 0], "90300001000000000000"),
    ("V0254", False, 32768, [0, 1, 1, 5], "90300001010500000000"),
    ("V0255", False, 32768, [0, 1, 3, 3], "90300001030300000000"),
    ("V0256", False, 32768, [0, 5, 0, 0], "90300005000000000000"),
    ("V0257", False, 32768, [0, 5, 1, 5], "90300005010500000000"),
    ("V0258", False, 32768, [0, 5, 3, 3], "90300005030300000000"),
    ("V0259", False, 32768, [1, 1, 0, 0], "90300101000000000000"),
    ("V0260", False, 32768, [1, 1, 1, 5], "90300101010500000000"),
    ("V0261", False, 32768, [1, 1, 3, 3], "90300101030300000000"),
    ("V0262", False, 32768, [1, 5, 0, 0], "90300105000000000000"),
    ("V0263", False, 32768, [1, 5, 1, 5], "90300105010500000000"),
    ("V0264", False, 32768, [1, 5, 3, 3], "90300105030300000000"),
    ("V0265", False, 32768, [2, 1, 0, 0], "90300201000000000000"),
    ("V0266", False, 32768, [2, 1, 1, 5], "90300201010500000000"),
    ("V0267", False, 32768, [2, 1, 3, 3], "90300201030300000000"),
    ("V0268", False, 32768, [2, 5, 0, 0], "90300205000000000000"),
    ("V0269", False, 32768, [2, 5, 1, 5], "90300205010500000000"),
    ("V0270", False, 32768, [2, 5, 3, 3], "90300205030300000000"),
    ("V0271", False, 32768, [3, 1, 0, 0], "90300301000000000000"),
    ("V0272", False, 32768, [3, 1, 1, 5], "90300301010500000000"),
    ("V0273", False, 32768, [3, 1, 3, 3], "90300301030300000000"),
    ("V0274", False, 32768, [3, 5, 0, 0], "90300305000000000000"),
    ("V0275", False, 32768, [3, 5, 1, 5], "90300305010500000000"),
    ("V0276", False, 32768, [3, 5, 3, 3], "90300305030300000000"),
    ("V0277", False, 32768, [4, 1, 0, 0], "90300401000000000000"),
    ("V0278", False, 32768, [4, 1, 1, 5], "90300401010500000000"),
    ("V0279", False, 32768, [4, 1, 3, 3], "90300401030300000000"),
    ("V0280", False, 32768, [4, 5, 0, 0], "90300405000000000000"),
    ("V0281", False, 32768, [4, 5, 1, 5], "90300405010500000000"),
    ("V0282", False, 32768, [4, 5, 3, 3], "90300405030300000000"),
    ("V0395", True, 0, [0, 1, 0, 0], "00300001000000000000"),
    ("V0396", True, 0, [0, 1, 1, 5], "00300001010500000000"),
    ("V0397", True, 0, [0, 1, 3, 3], "00300001030300000000"),
    ("V0398", True, 0, [0, 5, 0, 0], "00300005000000000000"),
    ("V0399", True, 0, [0, 5, 1, 5], "00300005010500000000"),
    ("V0400", True, 0, [0, 5, 3, 3], "00300005030300000000"),
    ("V0401", True, 0, [1, 1, 0, 0], "00300101000000000000"),
    ("V0402", True, 0, [1, 1, 1, 5], "00300101010500000000"),
    ("V0403", True, 0, [1, 1, 3, 3], "00300101030300000000"),
    ("V0404", True, 0, [1, 5, 0, 0], "00300105000000000000"),
    ("V0405", True, 0, [1, 5, 1, 5], "00300105010500000000"),
    ("V0406", True, 0, [1, 5, 3, 3], "00300105030300000000"),
    ("V0407", True, 0, [2, 1, 0, 0], "00300201000000000000"),
    ("V0408", True, 0, [2, 1, 1, 5], "00300201010500000000"),
    ("V0409", True, 0, [2, 1, 3, 3], "00300201030300000000"),
    ("V0410", True, 0, [2, 5, 0, 0], "00300205000000000000"),
    ("V0411", True, 0, [2, 5, 1, 5], "00300205010500000000"),
    ("V0412", True, 0, [2, 5, 3, 3], "00300205030300000000"),
    ("V0413", True, 0, [3, 1, 0, 0], "00300301000000000000"),
    ("V0414", True, 0, [3, 1, 1, 5], "00300301010500000000"),
    ("V0415", True, 0, [3, 1, 3, 3], "00300301030300000000"),
    ("V0416", True, 0, [3, 5, 0, 0], "00300305000000000000"),
    ("V0417", True, 0, [3, 5, 1, 5], "00300305010500000000"),
    ("V0418", True, 0, [3, 5, 3, 3], "00300305030300000000"),
    ("V0419", True, 0, [4, 1, 0, 0], "00300401000000000000"),
    ("V0420", True, 0, [4, 1, 1, 5], "00300401010500000000"),
    ("V0421", True, 0, [4, 1, 3, 3], "00300401030300000000"),
    ("V0422", True, 0, [4, 5, 0, 0], "00300405000000000000"),
    ("V0423", True, 0, [4, 5, 1, 5], "00300405010500000000"),
    ("V0424", True, 0, [4, 5, 3, 3], "00300405030300000000"),
    ("V0537", True, 32768, [0, 1, 0, 0], "80300001000000000000"),
    ("V0538", True, 32768, [0, 1, 1, 5], "80300001010500000000"),
    ("V0539", True, 32768, [0, 1, 3, 3], "80300001030300000000"),
    ("V0540", True, 32768, [0, 5, 0, 0], "80300005000000000000"),
    ("V0541", True, 32768, [0, 5, 1, 5], "80300005010500000000"),
    ("V0542", True, 32768, [0, 5, 3, 3], "80300005030300000000"),
    ("V0543", True, 32768, [1, 1, 0, 0], "80300101000000000000"),
    ("V0544", True, 32768, [1, 1, 1, 5], "80300101010500000000"),
    ("V0545", True, 32768, [1, 1, 3, 3], "80300101030300000000"),
    ("V0546", True, 32768, [1, 5, 0, 0], "80300105000000000000"),
    ("V0547", True, 32768, [1, 5, 1, 5], "80300105010500000000"),
    ("V0548", True, 32768, [1, 5, 3, 3], "80300105030300000000"),
    ("V0549", True, 32768, [2, 1, 0, 0], "80300201000000000000"),
    ("V0550", True, 32768, [2, 1, 1, 5], "80300201010500000000"),
    ("V0551", True, 32768, [2, 1, 3, 3], "80300201030300000000"),
    ("V0552", True, 32768, [2, 5, 0, 0], "80300205000000000000"),
    ("V0553", True, 32768, [2, 5, 1, 5], "80300205010500000000"),
    ("V0554", True, 32768, [2, 5, 3, 3], "80300205030300000000"),
    ("V0555", True, 32768, [3, 1, 0, 0], "80300301000000000000"),
    ("V0556", True, 32768, [3, 1, 1, 5], "80300301010500000000"),
    ("V0557", True, 32768, [3, 1, 3, 3], "80300301030300000000"),
    ("V0558", True, 32768, [3, 5, 0, 0], "80300305000000000000"),
    ("V0559", True, 32768, [3, 5, 1, 5], "80300305010500000000"),
    ("V0560", True, 32768, [3, 5, 3, 3], "80300305030300000000"),
    ("V0561", True, 32768, [4, 1, 0, 0], "80300401000000000000"),
    ("V0562", True, 32768, [4, 1, 1, 5], "80300401010500000000"),
    ("V0563", True, 32768, [4, 1, 3, 3], "80300401030300000000"),
    ("V0564", True, 32768, [4, 5, 0, 0], "80300405000000000000"),
    ("V0565", True, 32768, [4, 5, 1, 5], "80300405010500000000"),
    ("V0566", True, 32768, [4, 5, 3, 3], "80300405030300000000"),
]


@pytest.mark.parametrize(
    ("vector_id", "basic", "toggle", "level", "extension", "timer", "expected"),
    FLOOR_ARTIFACT_VECTORS,
)
@pytest.mark.asyncio
async def test_reachable_frozen_floor_boundary_and_timer_packet_vectors(
    vector_id, basic, toggle, level, extension, timer, expected
):
    c = make_controller(2 if basic else 7, features=True)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=2 if basic else 7,
        restored=True,
        floor_light=True,
        light_extension=extension,
    )
    c._toggle = toggle
    if timer:
        await c.set_light_timer(f"{timer} min")
    if level:
        await c.set_light_level(level)
    else:
        # Frozen low-level builder vectors isolate header construction from
        # the native OFF caller's separate toggle preadvance.
        await c._floor(0)
    assert written(c) == [expected], vector_id
    assert c._toggle == toggle


@pytest.mark.parametrize(
    ("vector_id", "basic", "toggle", "settings", "expected"), MASSAGE_PACKET_ARTIFACT_VECTORS
)
@pytest.mark.asyncio
async def test_reachable_frozen_massage_builder_settings_vectors(
    vector_id, basic, toggle, settings, expected
):
    c = make_controller(2 if basic else 7, features=True)
    c._toggle = toggle
    c._massage.effect, c._massage.speed, z1, z2 = settings
    c._massage.zones = (z1, z2)
    await c._send_massage()
    assert written(c) == [expected], vector_id
    assert c._toggle == toggle ^ 0x8000


@pytest.mark.asyncio
async def test_host_ordinary_buttons_exact_one_second_policy_not_travel_claim():
    c = make_controller(7)
    c.hold_control = AsyncMock()
    await c.move_head_up()
    await c.move_back_down()
    await c.move_legs_up()
    await c.move_feet_down()
    await c.preset_memory(6)
    await c.execute_app_action("all_down")
    assert [call.args for call in c.hold_control.call_args_list] == [
        ("head_up", 1000),
        ("back_down", 1000),
        ("legs_up", 1000),
        ("feet_down", 1000),
        ("memory_6", 1000),
        ("all_down", 1000),
    ]
    with pytest.raises(NotImplementedError):
        await c.preset_flat()


@pytest.mark.asyncio
async def test_information_null_reads_become_empty_metadata_strings():
    c = make_controller(2)
    c.client.read_gatt_char.return_value = None
    metadata = await async_prepare_vibradorm_app_pairing(
        c.client, "caresse", 2, deadline=asyncio.get_running_loop().time() + 1
    )
    assert metadata.model == metadata.firmware == metadata.software == ""
    assert metadata.main_firmware_article is None
    assert c.client.read_gatt_char.await_count == 5


@pytest.mark.asyncio
async def test_held_refresh_waits_for_successful_completion_plus_nominal_pump_gap():
    c = make_controller(7)
    started = []
    completed = []

    async def write(_char, data, **_kwargs):
        if data == b"\x00\xff":
            return
        started.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.035)
        completed.append(asyncio.get_running_loop().time())

    c.client.write_gatt_char.side_effect = write
    await c.hold_control("back_up", 220)
    assert len(started) == 2
    assert started[1] - completed[0] >= 0.095
    assert written(c) == ["000b", "000b", "00ff"]


@pytest.mark.asyncio
async def test_mood_local_intent_survives_failed_write_without_success_publication():
    c = make_controller(7, features=True)
    c.client.write_gatt_char.side_effect = OSError("failed")
    with pytest.raises(OSError):
        await c.set_mood_effect("disco")
    assert c.protocol_diagnostics["mood_intent"] == {"effect": "disco"}
    assert not c._coordinator.handle_controller_state_update.called


# Both manifests select Globals; its actual onCreate smali writes NLB_LEVEL=0.
# Getter fallbacks6/8 cannot override that reachable application initializer.
@pytest.mark.parametrize(
    ("control", "app", "extension", "expected"),
    [
        (2, "caresse", False, "c00000"),
        (2, "caresse", True, "80110600"),
        (7, "caresse", False, "8011c000"),
        (7, "caresse", True, "90110600"),
        (5, "werkmeister", False, "8011c000"),
        (7, "werkmeister", False, "8011c000"),
    ],
)
@pytest.mark.asyncio
async def test_manifest_globals_startup_zero_first_floor_toggle_on_exact_routes(
    control, app, extension, expected
):
    existing = make_controller(control, app=app)
    c = VibradormAppController(
        existing._coordinator,
        app_profile=app,
        control_type=control,
        restored=app == "caresse",
        floor_light=True,
        light_extension=extension,
    )
    assert c._floor_level == 0
    assert c._floor_default == 6
    assert not c._coordinator.handle_controller_state_updates.called
    assert not c.supports_light_state_feedback
    await c.lights_toggle()
    assert written(c) == [expected]
    assert c._toggle == 0x8000
    assert c.get_light_state()["state_source"] == "local_intent"


# unconfigure writes both local level and remembered level6. The same positive
# state is reachable through the exposed slider, without a new Android reset API.
@pytest.mark.parametrize(
    ("control", "extension", "off", "on"),
    [
        (2, False, "000000", "c00000"),
        (2, True, "80110000", "00110600"),
        (7, False, "80110000", "0011c000"),
        (7, True, "90110000", "10110600"),
    ],
)
@pytest.mark.asyncio
async def test_retained_positive_reset6_floor_toggle_off_then_remembers_six(
    control, extension, off, on
):
    c = make_controller(control, features=True)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        light_extension=extension,
    )
    await c.set_light_level(6)
    assert c._toggle == 0
    c.client.write_gatt_char.reset_mock()
    await c.lights_toggle()
    assert written(c) == [off]
    assert c._floor_level == 0 and c._floor_default == 6
    await c.lights_toggle()
    assert written(c) == [off, on]
    assert c._floor_level == 6 and c._toggle == 0


@pytest.mark.parametrize(
    ("control", "extension", "expected", "local_level"),
    [
        (2, False, "c00000", 6),
        (2, True, "80110600", 6),
        (7, False, "8011c000", 6),
        (7, True, "90110600", 6),
    ],
)
@pytest.mark.asyncio
async def test_failed_first_floor_toggle_retains_constructed_local_intent_without_ack(
    control, extension, expected, local_level
):
    c = make_controller(control, features=True)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        light_extension=extension,
    )
    c.client.write_gatt_char.side_effect = OSError("first toggle failed")
    with pytest.raises(OSError):
        await c.lights_toggle()
    assert written(c) == [expected]
    assert c._floor_level == local_level and c._toggle == 0x8000
    assert not c._coordinator.handle_controller_state_updates.called
    assert not c.supports_light_state_feedback


@pytest.mark.parametrize(
    ("control", "app", "extension", "expected"),
    [
        (2, "caresse", False, "000000"),
        (2, "caresse", True, "80110000"),
        (7, "caresse", False, "80110000"),
        (7, "caresse", True, "90110000"),
        (5, "werkmeister", False, "80110000"),
        (7, "werkmeister", False, "80110000"),
    ],
)
@pytest.mark.asyncio
async def test_new_onboarding_local_six_first_toggle_off_without_measured_state(
    control, app, extension, expected
):
    c = make_controller(control, app=app)
    floor = VibradormAppFloorIntent(level=6, default_level=6)
    c = VibradormAppController(
        c._coordinator,
        app_profile=app,
        control_type=control,
        restored=app == "caresse",
        floor_light=True,
        light_extension=extension,
        floor_intent=floor,
    )
    assert c._floor_level == 6 and not c.supports_light_state_feedback
    assert not c._coordinator.handle_controller_state_updates.called
    await c.lights_toggle()
    assert written(c) == [expected]
    assert floor.level == 0 and floor.default_level == 6
    c._coordinator.remember_vibradorm_app_floor_default.assert_not_called()


@pytest.mark.parametrize(("control", "expected"), [(2, "c80000"), (7, "8011c800")])
@pytest.mark.asyncio
async def test_explicit_retained_missing_preference_eight_fallback(control, expected):
    c = make_controller(control, features=True)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        floor_intent=VibradormAppFloorIntent(level=0, default_level=8),
    )
    await c.lights_toggle()
    assert written(c) == [expected] and c._floor_level == 8


@pytest.mark.parametrize(
    ("control", "off", "on"), [(2, "80110000", "00110800"), (7, "90110000", "10110800")]
)
@pytest.mark.asyncio
async def test_remembered_eight_preserved_even_extension_slider_maximum_six(control, off, on):
    c = make_controller(control, features=True)
    floor = VibradormAppFloorIntent(level=8, default_level=6)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        light_extension=True,
        floor_intent=floor,
    )
    assert c.light_level_max == 6
    with pytest.raises(ValueError):
        await c.set_light_level(8)
    await c.lights_toggle()
    c._coordinator.remember_vibradorm_app_floor_default.assert_called_once_with(8)
    assert floor.default_level == 8
    await c.lights_toggle()
    assert written(c) == [off, on] and floor.level == 8
    await c.lights_toggle()
    c._coordinator.remember_vibradorm_app_floor_default.assert_called_once_with(8)


@pytest.mark.asyncio
async def test_shared_floor_and_pending_timer_survive_controller_reconstruction():
    c = make_controller(7)
    floor = VibradormAppFloorIntent(level=0, default_level=6)
    timer = VibradormAppTimerIntent(enabled=False, minutes=0)
    kwargs = {
        "app_profile": "caresse",
        "control_type": 7,
        "restored": True,
        "floor_light": True,
        "floor_intent": floor,
        "timer_intent": timer,
    }
    c = VibradormAppController(c._coordinator, **kwargs)
    await c.set_pending_floor_timer(17)
    await c.execute_app_action("floor_timer_toggle")
    await c.set_light_level(3)
    await c.lights_toggle()
    assert floor.level == 0 and floor.default_level == 3
    assert timer.enabled and timer.minutes == 17
    c._coordinator.remember_vibradorm_app_floor_default.assert_called_once_with(3)
    c.client.write_gatt_char.reset_mock()
    rebuilt = VibradormAppController(c._coordinator, **kwargs)
    assert rebuilt._floor_level == 0 and rebuilt._floor_default == 3
    assert rebuilt._timer_enabled and rebuilt._timer_minutes == 17
    await rebuilt.lights_toggle()
    assert written(rebuilt) == ["80116011"]
    assert floor.level == 3


@pytest.mark.asyncio
async def test_failed_toggle_preserves_shared_intent_and_persisted_default_before_delivery():
    c = make_controller(7)
    floor = VibradormAppFloorIntent(level=8, default_level=6)
    timer = VibradormAppTimerIntent(enabled=True, minutes=12)
    kwargs = {
        "app_profile": "caresse",
        "control_type": 7,
        "restored": True,
        "floor_light": True,
        "floor_intent": floor,
        "timer_intent": timer,
    }
    c = VibradormAppController(c._coordinator, **kwargs)
    c.client.write_gatt_char.side_effect = OSError("failed")
    with pytest.raises(OSError):
        await c.lights_toggle()
    assert floor.level == 0 and floor.default_level == 8
    assert timer.enabled and timer.minutes == 12
    c._coordinator.remember_vibradorm_app_floor_default.assert_called_once_with(8)
    assert not c._coordinator.handle_controller_state_updates.called
    rebuilt = VibradormAppController(c._coordinator, **kwargs)
    assert rebuilt._floor_level == 0 and rebuilt._floor_default == 8
    assert rebuilt._timer_enabled and rebuilt._timer_minutes == 12


@pytest.mark.parametrize(
    ("holder", "field", "value"),
    [
        ("floor", "level", 9),
        ("floor", "default_level", 0),
        ("timer", "minutes", 61),
        ("timer", "enabled", 1),
    ],
)
def test_invalid_mutated_session_holder_values_rejected_before_io(holder, field, value):
    c = make_controller(7)
    floor = VibradormAppFloorIntent()
    timer = VibradormAppTimerIntent()
    setattr(floor if holder == "floor" else timer, field, value)
    with pytest.raises(ValueError):
        VibradormAppController(
            c._coordinator,
            app_profile="caresse",
            control_type=7,
            restored=True,
            floor_intent=floor,
            timer_intent=timer,
        )
    assert written(c) == []


@pytest.mark.asyncio
async def test_recreated_controller_is_fresh_mc_and_screen_preserving_only_process_holders():
    c = make_controller(7, features=True)
    floor = VibradormAppFloorIntent(level=0, default_level=6)
    timer = VibradormAppTimerIntent(enabled=True, minutes=20)
    c = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=7,
        restored=True,
        floor_light=True,
        massage=True,
        floor_intent=floor,
        timer_intent=timer,
    )
    await c.execute_app_action("massage_automatic")
    assert c._toggle == 0x8000 and c._massage.zones == (3, 3)
    c._coordinator.handle_controller_state_updates.reset_mock()
    rebuilt = VibradormAppController(
        c._coordinator,
        app_profile="caresse",
        control_type=7,
        restored=True,
        floor_light=True,
        massage=True,
        floor_intent=floor,
        timer_intent=timer,
    )
    # HA reconstruction models a fresh MC+MainScreen, not an SDK reconnect
    # retaining those exact instances. MC resetsT; MassageSettings resets zones.
    assert rebuilt._toggle == 0 and rebuilt._massage.zones == (0, 0)
    assert rebuilt._massage.saved_zones == (3, 3)
    assert rebuilt._massage.saved_flags == (False, False)
    assert rebuilt._timer_enabled and rebuilt._timer_minutes == 20
    assert rebuilt._floor_level == 0 and rebuilt._floor_default == 6
    assert not rebuilt._coordinator.handle_controller_state_updates.called


NATIVE_FLOOR_ENTITY_VECTORS = (
    (2, "caresse", False, ("200000", "000000", "200000", "200000", "000000", "000000")),
    (2, "caresse", True, ("00110100", "80110000", "00110100", "80110100", "00110000", "80110000")),
    (7, "caresse", False, ("00112000", "80110000", "00112000", "80112000", "00110000", "80110000")),
    (7, "caresse", True, ("10110100", "90110000", "10110100", "90110100", "10110000", "90110000")),
    (
        5,
        "werkmeister",
        False,
        ("00112000", "80110000", "00112000", "80112000", "00110000", "80110000"),
    ),
    (
        7,
        "werkmeister",
        False,
        ("00112000", "80110000", "00112000", "80112000", "00110000", "80110000"),
    ),
)


@pytest.mark.parametrize(
    ("control", "extension", "off", "on"),
    [
        (2, False, "000000", "c00000"),
        (2, True, "80110000", "00110600"),
        (7, False, "80110000", "0011c000"),
        (7, True, "90110000", "10110600"),
    ],
)
@pytest.mark.asyncio
async def test_initial_native_off_sends_requested_frame_despite_local_zero(
    control, extension, off, on
):
    existing = make_controller(control)
    c = VibradormAppController(
        existing._coordinator,
        app_profile="caresse",
        control_type=control,
        restored=True,
        floor_light=True,
        light_extension=extension,
    )
    assert c._floor_level == 0
    assert not c._coordinator.handle_controller_state_updates.called
    await c.lights_off()
    await c.lights_on()
    assert written(c) == [off, on]
    assert c._floor_default == 6 and c._floor_level == 6
    c._coordinator.remember_vibradorm_app_floor_default.assert_not_called()


@pytest.mark.parametrize(("control", "app", "extension", "packets"), NATIVE_FLOOR_ENTITY_VECTORS)
@pytest.mark.asyncio
async def test_real_native_light_entity_remembers_slider_and_repeats_requested_branch(
    control, app, extension, packets
):
    existing = make_controller(control, app=app)
    c = VibradormAppController(
        existing._coordinator,
        app_profile=app,
        control_type=control,
        restored=app == "caresse",
        floor_light=True,
        light_extension=extension,
    )
    runtime = c._coordinator
    runtime.capability_controller = c
    runtime.entity_side = None

    async def dispatch(operation, **kwargs):
        assert kwargs == {"cancel_running": False}
        await operation(c)

    runtime.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    entity = AdjustableBedOnOffLight(runtime, LIGHT_DESCRIPTION)
    entity.async_write_ha_state = MagicMock()
    assert entity.is_on is None and not c.supports_light_state_feedback
    await c.set_light_level(1)
    await entity.async_turn_off()
    assert c._floor_default == 1 and c._floor_level == 0
    await entity.async_turn_on()
    assert c._floor_level == 1
    # HA repeat calls resend explicit requested branches, never the opposite
    # toggle; the local intent remains distinct from measured hardware state.
    await entity.async_turn_on()
    await entity.async_turn_off()
    await entity.async_turn_off()
    assert written(c) == list(packets)
    assert c._toggle == 0x8000
    runtime.remember_vibradorm_app_floor_default.assert_called_once_with(1)
    assert runtime.async_execute_controller_command.await_count == 5


@pytest.mark.parametrize(("control", "app", "extension", "packets"), NATIVE_FLOOR_ENTITY_VECTORS)
@pytest.mark.asyncio
async def test_failed_native_off_remembers_level_and_retry_keeps_off_branch(
    control, app, extension, packets
):
    existing = make_controller(control, app=app)
    c = VibradormAppController(
        existing._coordinator,
        app_profile=app,
        control_type=control,
        restored=app == "caresse",
        floor_light=True,
        light_extension=extension,
    )
    await c.set_light_level(1)
    c._coordinator.handle_controller_state_updates.reset_mock()
    c.client.write_gatt_char.side_effect = OSError("OFF transport failed")
    with pytest.raises(OSError):
        await c.lights_off()
    assert c._floor_level == 0 and c._floor_default == 1
    assert not c._coordinator.handle_controller_state_updates.called
    c.client.write_gatt_char.side_effect = None
    await c.lights_off()
    await c.lights_on()
    # Failure still consumes the source construction/execution toggle. Retry
    # is an explicit OFF, followed by restoration of remembered level1.
    assert written(c) == [packets[0], packets[1], packets[4], packets[3]]
    c._coordinator.remember_vibradorm_app_floor_default.assert_called_once_with(1)


# Independently executed JavaUtf8Probe outputs (Java StandardCharsets.UTF_8).
JAVA_UTF8_MALFORMED_VECTORS = (
    ("eda080", "\ufffd"),
    ("edbfbf", "\ufffd"),
    ("eda0", "\ufffd"),
    ("eda041", "\ufffdA"),
    ("eda0ff", "\ufffd\ufffd"),
    ("eda08080", "\ufffd\ufffd"),
    ("edbf41", "\ufffdA"),
    ("edbfff", "\ufffd\ufffd"),
    ("f08080", "\ufffd\ufffd\ufffd"),
    ("f49080", "\ufffd\ufffd\ufffd"),
    ("f4908080", "\ufffd\ufffd\ufffd\ufffd"),
    ("e282", "\ufffd"),
    ("e28041", "\ufffdA"),
    ("ed9fbf", "\ud7ff"),
    ("eda07f", "\ufffd\x7f"),
    ("eda0c0", "\ufffd\ufffd"),
    ("edbf00", "\ufffd\x00"),
    ("edbfc2a0", "\ufffd\xa0"),
)


@pytest.mark.parametrize(("raw", "decoded"), JAVA_UTF8_MALFORMED_VECTORS)
def test_java_utf8_malformed_replacement_lengths_and_distinct_trim(raw, decoded):
    payload = bytes.fromhex(raw)
    assert decode_standard_info(b" \x00" + payload + b"\x00 ") == decoded.strip(
        "".join(map(chr, range(33)))
    )
    assert parse_article(b"\x21\xa0\xc8 \x00" + payload + b"\x00 ") == " \x00" + decoded + "\x00 "


def duplicate_roles(c, across_services):
    first = list(c.client.services[0].characteristics)
    duplicates = [
        MagicMock(uuid=char.uuid, handle=100 + index, properties=char.properties[:])
        for index, char in enumerate(first)
    ]
    if across_services:
        c.client.services.append(MagicMock(characteristics=duplicates))
    else:
        c.client.services[0].characteristics.extend(duplicates)
    return {char.uuid: char for char in first}, duplicates


@pytest.mark.parametrize("across_services", [False, True])
@pytest.mark.asyncio
async def test_first_exact_native_roles_bound_read_notify_write_and_unsubscribe(across_services):
    c = make_controller(4, features=True)
    first, duplicates = duplicate_roles(c, across_services)
    await c.async_discover_capabilities()
    await c.start_notify()
    c.client.start_notify.assert_awaited_once_with(first[RESPONSE], c._notification)
    await c.refresh_device_info()
    assert [call.args[0] for call in c.client.read_gatt_char.call_args_list] == [
        first[uuid] for _, uuid in INFO_FIELDS
    ]
    await c.stop_all()
    assert c.client.write_gatt_char.call_args.args[0] is first[CBI]
    assert (
        c._coordinator.record_command_trace.call_args.kwargs["characteristic_handle"]
        == first[CBI].handle
    )
    # Subscription teardown keeps the exact target it started with, even if
    # native enumeration changes before teardown.
    c.client.services[0].characteristics[:] = list(reversed(duplicates))
    await c.stop_notify()
    c.client.stop_notify.assert_awaited_once_with(first[RESPONSE])


@pytest.mark.parametrize("across_services", [False, True])
@pytest.mark.parametrize("operation", ["read", "notify", "write"])
@pytest.mark.asyncio
async def test_invalid_first_exact_role_never_falls_through_later_duplicate(
    across_services, operation
):
    c = make_controller(2 if operation == "read" else 4)
    first, _ = duplicate_roles(c, across_services)
    uuid = INFO_FIELDS[0][1] if operation == "read" else RESPONSE if operation == "notify" else CBI
    first[uuid].properties = []
    with pytest.raises(ValueError):
        if operation == "read":
            await c.refresh_device_info()
        elif operation == "notify":
            await c.start_notify()
        else:
            await c.stop_all()
    assert not c.client.read_gatt_char.called
    assert not c.client.start_notify.called
    assert not c.client.write_gatt_char.called


@pytest.mark.parametrize("across_services", [False, True])
@pytest.mark.parametrize("uuid", [COMMAND, LIGHT, CBI])
@pytest.mark.asyncio
async def test_all_app_write_roles_use_selected_characteristic_object(across_services, uuid):
    c = make_controller(7 if uuid == CBI else 2, features=True)
    first, _ = duplicate_roles(c, across_services)
    if uuid == COMMAND:
        await c.write_command(b"\x03")
    elif uuid == LIGHT:
        await c.lights_off()
    else:
        await c.stop_all()
    assert c.client.write_gatt_char.call_args.args[0] is first[uuid]
    assert (
        c._coordinator.record_command_trace.call_args.kwargs["characteristic_handle"]
        == first[uuid].handle
    )


@pytest.mark.asyncio
async def test_metadata_progress_commits_each_article_reply_before_next_request():
    c = make_controller(7)
    callback = None
    progress = []
    articles = iter((b"one", b"two", b"three"))

    async def subscribe(_char, listener):
        nonlocal callback
        callback = listener

    async def write(char, _data, **_kwargs):
        article = next(articles)
        before = len(progress)
        assert callback is not None
        callback(char, bytearray(b"\x21\xa0\xc8" + article))
        assert progress[before:] == [{"main_firmware_article": article.decode()}]

    c.client.start_notify.side_effect = subscribe
    c.client.write_gatt_char.side_effect = write
    result = await async_prepare_vibradorm_app_pairing(
        c.client,
        "werkmeister",
        7,
        deadline=asyncio.get_running_loop().time() + 1,
        metadata_progress=progress.append,
    )
    assert progress == [
        {"model": "value"},
        {"firmware": "value"},
        {"software": "value"},
        {"main_firmware_article": "one"},
        {"main_firmware_article": "two"},
        {"main_firmware_article": "three"},
    ]
    assert result.main_firmware_article == "three"


@pytest.mark.parametrize("across_services", [False, True])
@pytest.mark.asyncio
async def test_pair_helper_first_exact_roles_and_bound_subscription_cleanup(across_services):
    c = make_controller(7)
    first, _ = duplicate_roles(c, across_services)
    callback = None

    async def subscribe(char, listener):
        nonlocal callback
        assert char is first[RESPONSE]
        callback = listener

    async def write(char, data, **kwargs):
        assert char is first[CBI] and data == b"\x01\xa0\xc8" and kwargs == {"response": True}
        assert callback is not None
        callback(first[RESPONSE], bytearray(b"\x21\xa0\xc8article"))

    c.client.start_notify.side_effect = subscribe
    c.client.write_gatt_char.side_effect = write
    await async_prepare_vibradorm_app_pairing(
        c.client, "werkmeister", 7, deadline=asyncio.get_running_loop().time() + 1
    )
    assert [call.args[0] for call in c.client.read_gatt_char.call_args_list] == [
        first[uuid] for _, uuid in INFO_FIELDS
    ]
    c.client.stop_notify.assert_awaited_once_with(first[RESPONSE])


@pytest.mark.asyncio
async def test_repeat_pump_and_release_reselect_current_connection_exact_handle():
    c = make_controller(7)
    old_client = c.client
    first, _ = duplicate_roles(c, True)
    replacement = make_controller(7)
    new_first, _ = duplicate_roles(replacement, False)
    new_first[CBI].handle = 888
    new_first[CBI].properties = ["write-without-response"]

    async def initial(char, data, **kwargs):
        assert char is first[CBI] and kwargs == {"response": True}
        c._coordinator.client = replacement.client

    async def renewed(char, data, **kwargs):
        assert char is new_first[CBI] and kwargs == {"response": False}
        if data != b"\x00\xff":
            c._coordinator.cancel_command.set()

    old_client.write_gatt_char.side_effect = initial
    replacement.client.write_gatt_char.side_effect = renewed
    with pytest.raises(asyncio.CancelledError):
        await c.hold_control("back_up", 500)
    assert [call.args[1] for call in old_client.write_gatt_char.call_args_list] == [b"\x00\x0b"]
    assert written(replacement) == ["000b", "00ff"]
    assert c._coordinator.record_command_trace.call_args.kwargs["characteristic_handle"] == 888


@pytest.mark.asyncio
async def test_public_write_repeat_selects_current_connection_and_fresh_notify_teardown():
    c = make_controller(7)
    old = c.client
    first, _ = duplicate_roles(c, False)
    renewed = make_controller(7)
    next_first, _ = duplicate_roles(renewed, True)
    await c.start_notify()

    async def initial(*_args, **_kwargs):
        c._coordinator.client = renewed.client

    old.write_gatt_char.side_effect = initial
    await c.write_command(b"\x00\x0b", repeat_count=2, repeat_delay_ms=0)
    assert old.write_gatt_char.call_args.args[0] is first[CBI]
    assert renewed.client.write_gatt_char.call_args.args[0] is next_first[CBI]
    await c.stop_notify()
    old.stop_notify.assert_awaited_once_with(first[RESPONSE])
    assert not renewed.client.stop_notify.called
    await c.start_notify()
    await c.stop_notify()
    renewed.client.start_notify.assert_awaited_once_with(next_first[RESPONSE], c._notification)
    renewed.client.stop_notify.assert_awaited_once_with(next_first[RESPONSE])


@pytest.mark.parametrize("runtime", [False, True])
@pytest.mark.parametrize(
    ("failure_index", "expected"),
    [(2, []), (3, [{"model": ""}]), (4, [{"model": ""}, {"firmware": "FW"}])],
)
@pytest.mark.asyncio
async def test_successful_info_fields_retained_before_later_failure(
    runtime, failure_index, expected
):
    c = make_controller(4)
    reads = [b"name", b"manufacturer", b" \x00 ", b" FW ", b"SW"]
    c.client.read_gatt_char.side_effect = reads[:failure_index] + [OSError("later read failed")]
    progress = []
    with pytest.raises(OSError):
        if runtime:
            await c.refresh_device_info()
        else:
            await async_prepare_vibradorm_app_pairing(
                c.client,
                "caresse",
                4,
                deadline=asyncio.get_running_loop().time() + 1,
                metadata_progress=progress.append,
            )
    if runtime:
        assert c.protocol_diagnostics["metadata"] == (
            dict(item for delta in expected for item in delta.items()) or None
        )
        assert [
            call.args for call in c._coordinator.handle_controller_state_update.call_args_list
        ] == [
            ("vibradorm_app_" + field, value)
            for delta in expected
            for field, value in delta.items()
        ]
    else:
        assert progress == expected


@pytest.mark.asyncio
async def test_partial_cached_info_reconstruction_preserves_missing_unknown_and_successful_empty():
    c = make_controller(4)
    c._coordinator.entry.data = {"vibradorm_app_metadata": {"model": "", "software": "previousSW"}}
    c = VibradormAppController(c._coordinator, app_profile="caresse", control_type=4, restored=True)
    assert c.protocol_diagnostics["metadata"] == {"model": "", "software": "previousSW"}
    assert [call.args for call in c._coordinator.handle_controller_state_update.call_args_list] == [
        ("vibradorm_app_model", ""),
        ("vibradorm_app_software", "previousSW"),
    ]
    c.client.read_gatt_char.side_effect = [
        b"name",
        b"manufacturer",
        b"newModel",
        b"",
        OSError("SW failed"),
    ]
    with pytest.raises(OSError):
        await c.refresh_device_info()
    assert c.protocol_diagnostics["metadata"] == {
        "model": "newModel",
        "firmware": "",
        "software": "previousSW",
    }


@pytest.mark.parametrize("runtime", [False, True])
@pytest.mark.parametrize("fail_after_reply", [False, True])
@pytest.mark.asyncio
async def test_article_progress_retained_before_later_write_failure(runtime, fail_after_reply):
    c = make_controller(7)
    callback = None
    progress = []
    attempts = 0

    async def subscribe(_char, listener):
        nonlocal callback
        callback = listener

    async def write(char, data, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            assert callback is not None
            callback(char, bytearray(b"\x21\xa0\xc8 first \x00"))
            if fail_after_reply:
                raise OSError("write failed after matching notification")
        else:
            raise OSError("next write failed")

    c.client.start_notify.side_effect = subscribe
    c.client.write_gatt_char.side_effect = write
    with pytest.raises(OSError):
        if runtime:
            await c.refresh_device_info()
        else:
            await async_prepare_vibradorm_app_pairing(
                c.client,
                "werkmeister",
                7,
                deadline=asyncio.get_running_loop().time() + 1,
                metadata_progress=progress.append,
            )
    if runtime:
        metadata = c.protocol_diagnostics["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["main_firmware_article"] == " first \x00"
        c._coordinator.handle_controller_state_update.assert_any_call(
            "vibradorm_app_main_firmware_article", " first \x00"
        )
    else:
        assert progress[-1] == {"main_firmware_article": " first \x00"}
    assert c._article_reply is None


@pytest.mark.parametrize("failure", ["software", "article", "cancel", "none"])
@pytest.mark.asyncio
async def test_runtime_refresh_terminal_metadata_batch_survives_actual_reconstruction(failure):
    c = make_controller(7)
    c._coordinator.entry.data = {
        "vibradorm_app_metadata": {"model": "oldModel", "software": "oldSW"}
    }
    c = VibradormAppController(c._coordinator, app_profile="caresse", control_type=7, restored=True)

    def remember(delta):
        stored = c._coordinator.entry.data["vibradorm_app_metadata"]
        c._coordinator.entry.data = {
            **c._coordinator.entry.data,
            "vibradorm_app_metadata": {**stored, **delta},
        }

    c._coordinator.remember_vibradorm_app_metadata.side_effect = remember
    reads: list[bytes | OSError] = [b"name", b"manufacturer", b"newModel", b"", b"newSW"]
    if failure == "software":
        reads[-1] = OSError("software read failed")
    c.client.read_gatt_char.side_effect = reads
    callback = None
    attempts = 0

    async def subscribe(_char, listener):
        nonlocal callback
        callback = listener

    async def write(char, _data, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts > 1 and failure == "article":
            raise OSError("later article request failed")
        assert callback is not None
        callback(char, bytearray(b"\x21\xa0\xc8article"))
        if failure == "cancel":
            c._coordinator.cancel_command.set()

    c.client.start_notify.side_effect = subscribe
    c.client.write_gatt_char.side_effect = write
    if failure in ("software", "article"):
        with pytest.raises(OSError):
            await c.refresh_device_info()
    elif failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await c.refresh_device_info()
    else:
        await c.refresh_device_info()
    expected = {"model": "newModel", "firmware": ""}
    if failure != "software":
        expected.update(software="newSW", main_firmware_article="article")
    c._coordinator.remember_vibradorm_app_metadata.assert_called_once_with(expected)
    c._coordinator.handle_controller_state_update.reset_mock()
    rebuilt = VibradormAppController(
        c._coordinator, app_profile="caresse", control_type=7, restored=True
    )
    assert rebuilt.protocol_diagnostics["metadata"] == {
        "software": "oldSW",
        **expected,
    }
    assert rebuilt._article_reply is None and rebuilt._metadata_progress_pending is None
    # Idle unsolicited article notifications are presenter data. They do not
    # reopen the information transaction or replace committed diagnostic info.
    rebuilt._notification(
        c.client.services[0].characteristics[3], bytearray(b"\x21\xa0\xc8unsolicited")
    )
    assert rebuilt.protocol_diagnostics["metadata"] == {"software": "oldSW", **expected}


@pytest.mark.asyncio
async def test_failed_refresh_before_any_matching_metadata_has_no_terminal_persist():
    c = make_controller(4)
    c.client.read_gatt_char.side_effect = OSError("name failed")
    with pytest.raises(OSError):
        await c.refresh_device_info()
    c._coordinator.remember_vibradorm_app_metadata.assert_not_called()
    assert c._metadata_progress_pending is None
