"""Personal Comfort route, owner, lifecycle and entity behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.personal_comfort.air import PersonalComfortAir
from custom_components.adjustable_bed.beds.personal_comfort.controller import PersonalComfortBase
from custom_components.adjustable_bed.codec import personal_comfort as codec
from custom_components.adjustable_bed.profiles.personal_comfort import MODELS, PROFILES, air_route
from tests.state_helpers import state_writer
from tests.test_wire_snapshot import _load_tool


def make(route="malouf", model="pf4"):
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.stop_epoch = 0
    coordinator.motor_count = 2
    coordinator.motor_pulse_count = 5
    coordinator.motor_pulse_delay_ms = 200
    coordinator.controller_state = {}
    coordinator.handle_controller_state_updates.side_effect = state_writer(
        coordinator.controller_state
    )
    coordinator.handle_controller_state_update.side_effect = lambda k, v: (
        coordinator.controller_state.update({k: v})
    )
    coordinator.hass.async_create_task.side_effect = asyncio.create_task
    client = coordinator.client
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=bytearray(b"d"))
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    services = {}
    for profile in PROFILES.values():
        for service, char, properties in (
            (profile.service, profile.write, ["write"]),
            (profile.notify_service, profile.notify, ["notify"]),
        ):
            if service and char:
                services.setdefault(service, {})[char] = SimpleNamespace(
                    uuid=char, properties=properties
                )
    for char in (*codec.RA_WRITE.values(), *codec.RA_READ.values()):
        services[codec.RA_SERVICE][char] = SimpleNamespace(uuid=char, properties=["write", "read"])
    services[codec.bluetooth_uuid("180a")] = {
        codec.bluetooth_uuid("2a26"): SimpleNamespace(properties=["read"])
    }
    for prefix in (
        *codec.AXES.values(),
        "db8010a0",
        "db8010d0",
        "db801061",
        "db801060",
        "db801080",
    ):
        uuid = codec.reverie_uuid(prefix)
        services[codec.reverie_uuid("db801000")][uuid] = SimpleNamespace(
            uuid=uuid, properties=["write", "read"]
        )
    client.services.get_service.side_effect = lambda service: (
        SimpleNamespace(get_characteristic=services[service].get) if service in services else None
    )
    client.services.__iter__.side_effect = lambda: iter(())
    profile = PROFILES[route]
    controller = (
        PersonalComfortAir(coordinator, profile)
        if route in ("anm3", "anm5", "ra")
        else PersonalComfortBase(coordinator, profile, model)
    )
    coordinator.controller = controller
    return controller, coordinator


def writes(coordinator):
    return [
        (call.args[0], bytes(call.args[1]).hex(), call.kwargs["response"])
        for call in coordinator.client.write_gatt_char.call_args_list
    ]


@pytest.fixture
async def clock():
    tool = _load_tool()
    virtual = tool.FakeClock()
    with tool.virtual_time(virtual):
        yield virtual


@pytest.mark.parametrize("route", ["malouf", "reverie_v1", "reverie_v2"])
@pytest.mark.parametrize("model", MODELS)
def test_model_gates(route, model):
    ctrl, _ = make(route, model)
    assert ctrl.has_pillow_support == (route != "reverie_v1" and model in ("pf4", "pf42"))
    assert ctrl.supports_massage == (model in ("pf3", "pf4", "other"))
    assert ctrl.memory_slot_count == (2 if model != "none" and route != "reverie_v1" else 0)
    assert not ctrl.has_lumbar_support
    assert not ctrl.supports_single_address_pairing
    assert ctrl.alarm_capability is None
    labels = [spec.name for spec in ctrl.controller_button_specs]
    assert len(labels) == len(set(labels))
    assert all("Decrease" not in label for label in labels) if route != "malouf" else True


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("malouf", ["6e01002493"] * 5),
        ("reverie_v1", ["550154", "55ffaa"]),
        ("reverie_v2", ["01", "00"]),
    ],
)
async def test_movement_and_exact_release(clock, route, expected):
    ctrl, c = make(route)
    await ctrl.move_head_up()
    assert [v[1] for v in writes(c)] == expected
    assert all(v[2] for v in writes(c))
    if route == "reverie_v2":
        assert {v[0] for v in writes(c)} == {"db801021-f324-29c3-38d1-85c0c2e86885"}


@pytest.mark.parametrize("route", ["reverie_v1", "reverie_v2"])
async def test_cancel_releases_with_fresh_event(clock, route):
    ctrl, c = make(route)

    async def cancel(*_args, **_kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_head_up()
    assert [v[1] for v in writes(c)] == (
        ["550154", "55ffaa"] if route == "reverie_v1" else ["01", "00"]
    )


async def test_release_failure_propagates(clock):
    ctrl, c = make("reverie_v1")
    c.client.write_gatt_char.side_effect = [None, ConnectionError("release failed")]
    with pytest.raises(ConnectionError, match="release failed"):
        await ctrl.move_head_up()


async def test_replacement_never_releases_to_new_client(clock):
    ctrl, c = make("reverie_v2")
    original = c.client

    async def replace(*_args, **_kwargs):
        ctrl.on_disconnect()
        c.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

    original.write_gatt_char.side_effect = replace
    with pytest.raises(ConnectionError, match="physical session"):
        await ctrl.move_head_up()
    c.client.write_gatt_char.assert_not_called()
    assert original.write_gatt_char.call_count == 1


async def test_release_all_axes_drains_failures():
    ctrl, c = make("reverie_v2")
    c.client.write_gatt_char.side_effect = [ConnectionError("head"), None, None]
    with pytest.raises(ExceptionGroup):
        await ctrl.stop_all()
    assert [v[0] for v in writes(c)] == [
        codec.reverie_uuid(p) for p in ("db801021", "db801022", "db801020")
    ]


@pytest.mark.parametrize(
    ("route", "recall", "save"),
    [
        ("malouf", "6e01002f9e", "6e01002c9b"),
        ("reverie_v2", "05", "85"),
    ],
)
async def test_memory_uses_requested_receiving_base(route, recall, save):
    ctrl, c = make(route)
    await ctrl.preset_memory(2)
    await ctrl.program_memory(2)
    assert [v[1] for v in writes(c)] == [recall, save]


async def test_reverie_v1_memory_rejected_without_write():
    ctrl, c = make("reverie_v1")
    with pytest.raises(ValueError, match="memory"):
        await ctrl.preset_memory(2)
    assert not writes(c)


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("malouf", "6e01003cab"),
        ("reverie_v1", "555b"),
    ],
)
async def test_toggle_is_not_desired_state_light(route, expected):
    ctrl, c = make(route)
    await ctrl.lights_toggle()
    assert [v[1] for v in writes(c)] == [expected]
    assert not ctrl.supports_discrete_light_control
    assert not ctrl.supports_light_state_feedback


@pytest.mark.parametrize("route", ["malouf", "reverie_v1"])
def test_toggle_routes_expose_no_assumed_light_entity(hass, route):
    from custom_components.adjustable_bed.light import _light_entities_for

    ctrl, c = make(route)
    c.capability_controller = ctrl
    assert ctrl.supports_light_toggle_control
    assert _light_entities_for(hass, c) == []


@pytest.mark.parametrize("route", ["malouf", "reverie_v1", "reverie_v2"])
def test_no_base_model_exposes_no_light_or_movement(hass, route):
    from custom_components.adjustable_bed.light import _light_entities_for

    ctrl, c = make(route, "none")
    c.capability_controller = ctrl
    assert not ctrl.supports_light_toggle_control
    assert not ctrl.supports_stop_all
    assert not ctrl.motor_control_specs
    assert _light_entities_for(hass, c) == []


@pytest.mark.parametrize(
    ("reply", "on"), [(b"d", True), (b"\x64", True), (b"\x00", False), (b"D", False)]
)
async def test_light_read_and_desired_state(reply, on):
    ctrl, c = make("reverie_v2")
    c.client.read_gatt_char.return_value = bytearray(reply)
    await ctrl.start_notify()
    assert ctrl._light_on is on
    await ctrl.lights_on()
    await ctrl.lights_off()
    assert [v[1] for v in writes(c)] == ["64", "00"]
    ctrl.on_disconnect()
    assert ctrl._light_on is None


async def test_air_entities_are_native_numbers_only():
    ctrl, _ = make("anm3")
    assert [s.native_min_value for s in ctrl.controller_number_specs] == [5, 5]
    assert [s.native_max_value for s in ctrl.controller_number_specs] == [50, 50]
    assert not ctrl.motor_control_specs
    assert len(ctrl.controller_state_sensor_specs) == 1
    assert not ctrl.supports_stop_all
    assert not ctrl.supports_memory_presets


async def test_anm3_ready_captures_target_and_ack(clock):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 20, "right": 30}

    async def reply(_char, packet, **_kwargs):
        if packet[2] == 0x69:
            ctrl.receive(bytes.fromhex("550469"))
        elif packet[2] == 1:
            ctrl.receive(bytes.fromhex("550485"))

    c.client.write_gatt_char.side_effect = reply
    await ctrl.set_firmness("right", 35)
    assert [v[1] for v in writes(c)] == [
        "5504690023000002e7aa",
        "55040100230000027faa",
        "5504850000000000deaa",
        "5504830000000003dfaa",
    ]


async def test_anm5_query_order_and_success_dependency(clock):
    ctrl, c = make("anm5")
    await ctrl.query(ctrl.capture())
    assert [bytes.fromhex(v[1]) for v in writes(c)] == [b"C>TPCH>0\n", b"C>TPCH>0\n", b"R>SP\n"]
    c.client.write_gatt_char.reset_mock()
    c.client.write_gatt_char.side_effect = ConnectionError("select failed")
    with pytest.raises(ConnectionError):
        await ctrl.query(ctrl.capture())
    assert len(writes(c)) == 1


@pytest.mark.parametrize("route", ["anm3", "anm5", "ra"])
async def test_air_no_equal_target_write_and_input_admission(route):
    ctrl, c = make(route)
    ctrl.values = {"left": 30, "right": 40}
    await ctrl.set_firmness("right", 40)
    assert not writes(c)
    for value in (4, 51, 10.5):
        with pytest.raises(ValueError):
            await ctrl.set_firmness("left", value)
    assert not writes(c)


def test_air_discovery_precedence_and_case():
    assert air_route("2618X", {codec.RA_SERVICE, codec.bluetooth_uuid("ffe0")}) == "ra"
    assert air_route("2618X", {codec.bluetooth_uuid("ffe0")}) == "anm5"
    assert air_route("2816", {"ffe0"}) == "anm5"
    assert air_route("ANM-X", {codec.bluetooth_uuid("ffe5")}) == "anm3"
    assert air_route("anm-X", {codec.bluetooth_uuid("ffe5")}) is None
    assert air_route("2618X", {codec.bluetooth_uuid("180a")}) is None


async def test_gatt_admission_before_any_write():
    ctrl, c = make("reverie_v2")
    c.client.services.get_service.return_value = None
    c.client.services.get_service.side_effect = None
    with pytest.raises(ValueError, match="Bluetooth services"):
        await ctrl.start_notify()
    assert not writes(c)


async def test_busy_retries_captured_adjustment_not_ready(clock):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 20, "right": 30}
    attempts = 0

    async def reply(_char, packet, **_kwargs):
        nonlocal attempts
        if packet[2] == 0x69:
            ctrl.receive(bytes.fromhex("550469"))
        elif packet[2] == 1:
            attempts += 1
            ctrl.receive(bytes.fromhex("550488" if attempts == 1 else "550485"))

    c.client.write_gatt_char.side_effect = reply
    await ctrl.set_firmness("right", 35)
    assert [v[1] for v in writes(c)][:3] == [
        "5504690023000002e7aa",
        "55040100230000027faa",
        "55040100230000027faa",
    ]


async def test_busy_exhaustion_has_no_fabricated_stop(clock):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 20, "right": 30}
    c.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: ctrl.receive(
        bytes.fromhex("550488")
    )
    await ctrl.set_firmness("left", 35)
    assert len(writes(c)) == 4
    assert all(bytes.fromhex(v[1])[2] == 0x69 for v in writes(c))
    assert not ctrl._adjusting


async def test_ra_firmware_retry_and_exact_scaling(clock):
    ctrl, c = make("ra")
    c.client.read_gatt_char.side_effect = [
        ConnectionError("firmware"),
        bytearray(b"71RU2265.03"),
        bytearray(b"\x32"),
        bytearray(b"\x33"),
    ]
    await ctrl._initialize(ctrl.capture())
    assert ctrl.values == {"left": 50, "right": 51}
    assert [call.args[0] for call in c.client.read_gatt_char.call_args_list] == [
        codec.bluetooth_uuid("2a26")
    ] * 2 + list(codec.RA_READ.values())
    ctrl.on_disconnect()
    assert ctrl.firmware is None
    assert ctrl.values == {"left": None, "right": None}


async def test_stale_notification_is_ignored_and_shutdown_drains(clock):
    ctrl, c = make("anm3")
    await ctrl.start_notify()
    callback = c.client.start_notify.call_args.args[1]
    ctrl.on_disconnect()
    callback(None, bytearray.fromhex("550483002832000000aa"))
    assert ctrl.values == {"left": None, "right": None}
    await ctrl.stop_notify()
    assert not ctrl._followups


def test_route_and_model_stay_with_each_paired_side():
    from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data

    left = {
        "address": "AA:BB:CC:DD:EE:01",
        "bed_type": "personal_comfort",
        "protocol_variant": "malouf",
        "product_type": "pf4",
    }
    right = {
        "address": "AA:BB:CC:DD:EE:02",
        "bed_type": "personal_comfort",
        "protocol_variant": "reverie_v2",
        "product_type": "pf3",
    }
    paired = build_pair_entry_data(left, right, name="Bed")
    assert (
        effective_child_data(
            paired, "left", {"protocol_variant": "reverie_v1", "product_type": "other"}
        )["protocol_variant"]
        == "malouf"
    )
    assert effective_child_data(paired, "right")["product_type"] == "pf3"
    with pytest.raises(ValueError, match="bases"):
        build_pair_entry_data(left, {**right, "protocol_variant": "ra"}, name="Bed")


def test_setup_derives_only_app_model_permissions():
    from custom_components.adjustable_bed.setup_questions import _personal_comfort_settings

    for model in MODELS:
        assert _personal_comfort_settings({"protocol_variant": "malouf", "product_type": model})[
            "has_massage"
        ] == (model in ("pf3", "pf4", "other"))
    assert not _personal_comfort_settings({"protocol_variant": "ra", "product_type": "pf4"})[
        "has_massage"
    ]


async def test_repeated_cancellation_waits_for_captured_release():
    ctrl, c = make("reverie_v2")
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, packet, **_kwargs):
        if packet == b"\x01":
            c.cancel_command.set()
        else:
            started.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(ctrl.move_head_up())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [v[1] for v in writes(c)] == ["01", "00"]


async def test_notification_ack_owns_new_epoch_not_completed_command(clock):
    ctrl, c = make("anm3")
    c.cancel_command.set()

    async def query(operation, **_kwargs):
        c.cancel_command = asyncio.Event()
        await operation(ctrl)

    c.async_execute_controller_query = AsyncMock(side_effect=query)
    ctrl.receive(bytes.fromhex("550401"))
    ctrl.receive(bytes.fromhex("550485"))
    await asyncio.gather(*ctrl._followups)
    assert [v[1] for v in writes(c)] == ["5504850000000000deaa", "5504830000000003dfaa"]
    assert c.async_execute_controller_query.call_args.kwargs["preserve_idle_deadline"]


async def test_initial_query_is_sent_before_startup_returns(clock):
    ctrl, c = make("anm3")

    async def reply(_char, packet, **_kwargs):
        assert packet.hex() == "5504830000000003dfaa"
        callback = c.client.start_notify.call_args.args[1]
        callback(None, bytearray.fromhex("550483002832000000aa"))

    c.client.write_gatt_char.side_effect = reply
    await ctrl.start_notify()
    assert ctrl.values == {"left": 50, "right": 40}
    assert [v[1] for v in writes(c)] == ["5504830000000003dfaa"]
    await ctrl.stop_notify()


def test_setup_requires_an_explicit_route():
    from custom_components.adjustable_bed.config_flow import _labelled_routes
    from custom_components.adjustable_bed.setup_questions import REQUIRED, SETUP_PROFILES
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    assert set(_labelled_routes("personal_comfort")) == set(PROFILES)
    assert not is_valid_variant_for_bed_type("personal_comfort", "auto")
    question = SETUP_PROFILES["personal_comfort"].questions[0]
    assert question.default is REQUIRED


@pytest.mark.parametrize("route", ["malouf", "reverie_v1", "reverie_v2"])
async def test_timed_move_uses_requested_duration_and_one_release(clock, monkeypatch, route):
    from contextlib import asynccontextmanager

    from custom_components.adjustable_bed import services

    ctrl, c = make(route)
    c.hass = None

    @asynccontextmanager
    async def validation(*_args):
        yield ctrl

    monkeypatch.setattr(services, "_side_validation", validation)
    command, *_rest = await services._timed_move_plan(c, c, [], "back", "up", 2500)
    await command(ctrl)
    assert clock.now == pytest.approx(2.5)
    frames = [v[1] for v in writes(c)]
    assert frames == (
        ["6e01002493"] * 13
        if route == "malouf"
        else ["550154", "55ffaa"]
        if route == "reverie_v1"
        else ["01", "00"]
    )


@pytest.mark.parametrize("latency", [0.07, 0.4])
async def test_malouf_refresh_is_start_paced_and_finitely_bounded(clock, latency):
    ctrl, c = make("malouf")
    starts = []

    async def acknowledged(*_args, **_kwargs):
        starts.append(clock.now)
        await asyncio.sleep(latency)

    c.client.write_gatt_char.side_effect = acknowledged
    await ctrl.hold_control("feet_down", 1000)
    assert starts == pytest.approx([0, 0.2, 0.4, 0.6, 0.8] if latency < 0.2 else [0, 0.4, 0.8])
    assert clock.now == pytest.approx(1)
    assert all(v[1] == "6e01002796" for v in writes(c))


async def test_anm_reconnect_waits_for_delayed_measured_firmness(clock):
    ctrl, c = make("anm3")
    ctrl.on_disconnect()
    tasks = []

    async def measured():
        await asyncio.sleep(0.2)
        ctrl.receive(bytes.fromhex("550483002832000000aa"))

    async def reply(_char, packet, **_kwargs):
        if packet[2] == 0x83:
            tasks.append(asyncio.create_task(measured()))
        elif packet[2] == 0x69:
            ctrl.receive(bytes.fromhex("550469"))
        elif packet[2] == 2:
            ctrl.receive(bytes.fromhex("550485"))

    c.client.write_gatt_char.side_effect = reply
    await ctrl.set_firmness("left", 25)
    await asyncio.gather(*tasks)
    assert clock.now >= 0.4
    assert "550402191900000390aa" in [v[1] for v in writes(c)]


async def test_ra_reconnect_hydrates_firmware_and_actual_side(clock):
    ctrl, c = make("ra")
    ctrl.on_disconnect()

    async def read(char):
        await asyncio.sleep(0.2)
        return b"71RU2265.00" if char == codec.bluetooth_uuid("2a26") else b"\x14"

    c.client.read_gatt_char.side_effect = read
    await ctrl.set_firmness("right", 25)
    assert writes(c) == [(codec.RA_WRITE["right"], "320f0f", True)]
    assert ctrl.values == {"left": None, "right": 20}


@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("read_error", [False, True])
async def test_startup_light_read_owns_session_not_preempted_legacy_event(replace, read_error):
    ctrl, c = make("reverie_v2")
    c.cancel_command.set()

    async def read(_char):
        if replace:
            ctrl.on_disconnect()
        if read_error:
            raise ConnectionError("Light read failed")
        return b"d"

    c.client.read_gatt_char.side_effect = read
    if replace:
        with pytest.raises(ConnectionError, match="physical session"):
            await ctrl.start_notify()
    else:
        await ctrl.start_notify()
        assert ctrl._light_on is (None if read_error else True)
    assert not writes(c)


@pytest.mark.parametrize("side", ["left", "right"])
async def test_ra_setter_needs_only_requested_pressure_characteristic(clock, side):
    ctrl, c = make("ra")
    ctrl.firmware = "71RU2265.00"

    async def read(char):
        if char != codec.RA_READ[side]:
            raise ConnectionError("The other pressure characteristic is unavailable")
        return b"\x14"

    c.client.read_gatt_char.side_effect = read
    await ctrl.set_firmness(side, 25)
    assert writes(c) == [(codec.RA_WRITE[side], "320f0f", True)]
    assert ctrl.values[side] == 20
    assert ctrl.values["right" if side == "left" else "left"] is None
    assert {call.args[0] for call in c.client.read_gatt_char.call_args_list} == {
        codec.RA_READ[side]
    }
    assert clock.now == pytest.approx(5)


@pytest.mark.parametrize("available", ["left", "right"])
async def test_ra_background_publishes_available_side_while_other_read_retries(clock, available):
    ctrl, c = make("ra")
    ctrl.firmware = "71RU2265.00"

    async def read(char):
        if char == codec.RA_READ[available]:
            return b"\x14"
        raise ConnectionError("The other pressure is unavailable")

    c.client.read_gatt_char.side_effect = read
    task = asyncio.create_task(ctrl.query(ctrl.capture()))
    try:
        await asyncio.sleep(0.6)
        missing = "right" if available == "left" else "left"
        assert c.controller_state[f"personal_comfort_{available}_firmness"] == 20
        assert c.controller_state[f"personal_comfort_{missing}_firmness"] is None
        calls = [call.args[0] for call in c.client.read_gatt_char.call_args_list]
        assert calls.count(codec.RA_READ[available]) == 1
        assert calls.count(codec.RA_READ[missing]) >= 2
        assert not writes(c)
    finally:
        c.cancel_command.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("route", ["reverie_v1", "reverie_v2"])
@pytest.mark.parametrize(("duration", "latency"), [(100, 0.4), (1000, 0.007), (2500, 0.4)])
async def test_latched_hold_timer_includes_movement_acknowledgment(clock, route, duration, latency):
    ctrl, c = make(route)
    starts = []

    async def write(_char, packet, **_kwargs):
        starts.append((bytes(packet).hex(), clock.now))
        await asyncio.sleep(latency)

    c.client.write_gatt_char.side_effect = write
    await ctrl.hold_control("head_up", duration)
    assert [packet for packet, _when in starts] == [
        "550154" if route == "reverie_v1" else "01",
        "55ffaa" if route == "reverie_v1" else "00",
    ]
    assert [when for _packet, when in starts] == pytest.approx([0, duration / 1000])
    assert clock.now == pytest.approx(duration / 1000 + latency)


@pytest.mark.parametrize("route", ["anm3", "anm5", "ra"])
async def test_missing_initial_air_value_times_out_on_captured_session(clock, route):
    ctrl, c = make(route)
    c.client.read_gatt_char.side_effect = ConnectionError("No firmware reply")
    with pytest.raises(TimeoutError):
        await ctrl.set_firmness("left", 25)
    assert clock.now == pytest.approx(10)
    assert all(v[1] not in {"433e53544f504e0a", "55ffaa", "00"} for v in writes(c))


@pytest.mark.parametrize("route", ["anm3", "anm5", "ra"])
async def test_lost_air_completion_has_a_foreground_ceiling(clock, route):
    ctrl, c = make(route)
    ctrl.values = {"left": 20, "right": 30}
    ctrl.firmware = "71RU2265.00"
    if route == "anm5":
        c.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: ctrl.receive(
            b"RET>SP>00014216201008"
        )
    c.client.read_gatt_char.side_effect = ConnectionError("No pressure reply")
    with pytest.raises(TimeoutError):
        await ctrl.set_firmness("left", 25)
    assert clock.now == pytest.approx(120)
    assert not ctrl._active and not ctrl._preparing
    assert all(v[1] not in {"433e53544f504e0a", "55ffaa", "00"} for v in writes(c))
