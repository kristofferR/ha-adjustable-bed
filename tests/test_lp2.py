"""L&P commands, feature gates, cancellation and connection ownership."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic import lp2
from custom_components.adjustable_bed.beds.richmat_classic.protocol import Worker
from custom_components.adjustable_bed.beds.richmat_classic.rise import Schedule
from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport
from tests.test_lp2_vectors import vectors


def controller(layout="APRM", wire="FRAMED"):
    co = MagicMock()
    co.cancel_command = asyncio.Event()
    co.entry.data = {
        "product_type": layout,
        "protocol_variant": "lp2",
        "motor_pulse_count": 1,
        "ble_device_name": "6BRM",
    }
    co.client.is_connected = True
    co.client.write_gatt_char = AsyncMock()
    co.client.start_notify = AsyncMock()
    co.client.stop_notify = AsyncMock()
    ctrl = lp2.Lp2Controller(co)
    co.controller = ctrl
    write = SimpleNamespace(uuid="write", properties=["write"], handle=71)
    notify = SimpleNamespace(uuid="notify", properties=["notify"], handle=72)
    ctrl._session = Transport(co.client, write, notify, wire)
    ctrl._worker = Worker(tick_ms=150)
    return ctrl, co


def packets(co):
    return [call.args[1].hex() for call in co.client.write_gatt_char.call_args_list]


@pytest.fixture
def clock(monkeypatch):
    delays = []
    real_sleep = asyncio.sleep
    now = [0.0]
    monkeypatch.setattr(lp2, "monotonic", lambda: now[0])
    monkeypatch.setattr(lp2.dt_util, "now", lambda: datetime(2026, 11, 19, 12, tzinfo=UTC))

    async def sleep(seconds):
        delays.append(round(seconds * 1000))
        now[0] += seconds
        await real_sleep(0)

    async def wait(milliseconds, cancel):
        if cancel.is_set():
            return False
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(lp2.asyncio, "sleep", sleep)
    monkeypatch.setattr(lp2.Lp2Controller, "_wait", staticmethod(wait))
    return delays


@pytest.mark.parametrize(
    "wire,first,stop", [("RAW", "34", "6e"), ("FRAMED", "6e01002493", "6e01006edd")]
)
async def test_held_action_uses_exact_resource_and_release(clock, wire, first, stop):
    c, co = controller("6BRM", wire)
    await c.execute_action(1, hold_ms=150)
    assert packets(co)[0] == first
    assert packets(co)[-1] == stop
    assert clock[-1] == 50


async def test_cancel_during_refresh_cleans_up_only_its_link(clock):
    c, co = controller("6BRM")

    async def cancel(_char, _data, **_kwargs):
        co.cancel_command.set()

    co.client.write_gatt_char.side_effect = cancel
    await c.execute_action(1)
    assert packets(co) == ["6e01002493", "6e01006edd"]
    assert c._worker.payload is None


async def test_replacement_link_receives_neither_refresh_nor_old_cleanup(clock):
    c, co = controller("6BRM")
    original = co.client
    replacement = MagicMock()
    replacement.is_connected = True
    replacement.write_gatt_char = AsyncMock()

    async def replace_link(_char, _data, **_kwargs):
        co.client = replacement
        c._session = replace(c._session, client=replacement)

    original.write_gatt_char.side_effect = replace_link
    with pytest.raises(ConnectionError, match="changed"):
        await c.execute_action(1)
    assert original.write_gatt_char.await_count == 1
    replacement.write_gatt_char.assert_not_awaited()


async def test_direct_rgb_duration_aroma_and_fan_quirk(clock):
    c, co = controller()
    with pytest.raises(ValueError, match="lighting"):
        await c.settings(color=(12, 34, 56))
    c._receive.light_capable = c._receive.aroma_capable = True
    await c.settings(color=(12, 34, 56))
    await c.settings(seconds=300)
    await c.settings(aroma_times=(1, 2, 3))
    await c.settings(fan="head", duration=3, level=60)
    await c.settings(fan="foot", duration=6, level=60)
    assert packets(co) == [
        "6e0cff0c856e0d2238d5",
        "6e0b012ca6",
        "6e1b00018a",
        "6e1c00028c",
        "6e1d00038e",
        "6e01d30042",
        "6e01da0049",
        "6e0101da4a",
        "6e0101da4a",
    ]
    assert clock == [150, 150, 300, 300]


async def test_alarm_uses_shared_capability_and_two_frozen_parts(clock):
    c, co = controller("A9RM")
    capability = c.alarm_capability
    assert capability is not None
    action = capability.wake_actions[0]
    request = AlarmRequest(
        enabled=True,
        wake_action=action,
        hour=12,
        minute=0,
        reference_time=datetime(2026, 11, 19, 12, tzinfo=UTC),
    )
    await c.configure_alarm(request)
    code = next(v for v in c._alarm_actions().values() if lp2._ALARMS[v] == action)
    from custom_components.adjustable_bed.codec.richmat import countdown

    assert packets(co) == [p.hex() for p in countdown(1440, code)]
    assert clock == [300, 300]
    assert c._receive.alarm_enabled is None


async def test_motor_program_fragmentation_matches_default_literal(clock):
    c, co = controller("RMCS")
    rows = tuple((n, 0, 0) for n in (1, 2, 3, 4, 7, 8, 9, 10, 5, 6, 11, 12))
    schedule = Schedule(rows, 0, 0, "ble", "new", 1, (1, 2, 3, 4))
    await c.program_schedule(schedule)
    expected = next(
        expected.lower()
        for action, _, expected in vectors("direct")
        if action == "default UI configuration"
    )
    assert "".join(packets(co)) == expected
    assert all(len(bytes.fromhex(p)) <= 20 for p in packets(co))
    assert clock == [10] * (len(packets(co)) - 1)
    with pytest.raises(ValueError, match="65535"):
        await c.program_schedule(replace(schedule, rest=65536))


def test_no_screen_selectors_and_confirmation_never_offers_hold():
    c, _ = controller("E3RM")
    assert c.controller_select_specs == ()
    assert any("Save" in s.name for s in c.controller_button_specs)
    assert all(s.hold is None for s in c.controller_button_specs if s.requires_confirmation)


def test_fragmented_notification_literals_and_stale_callback():
    for action, expected, packet in vectors("direct"):
        if not action.startswith("parse"):
            continue
        c, co = controller("WFRM")
        data = bytes.fromhex(packet)
        session = c._session
        c._notification(session, session.notify, bytearray(data[:2]))
        c._notification(session, session.notify, bytearray(data[2:]))
        assert c._receive.height_cm == pytest.approx(expected["expected_cm"])
        assert c._receive.height_inches == pytest.approx(expected["expected_inch"])
        c._session = replace(session)
        previous = c._receive.height_cm
        c._notification(session, session.notify, bytearray.fromhex("6e08000177"))
        assert c._receive.height_cm == previous
        co.client.write_gatt_char.assert_not_awaited()


async def test_switch_only_shows_delivered_request_not_cleanup(clock):
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )
    from tests.state_helpers import state_writer

    c, co = controller("APRM")
    state = {lp2.MASSAGE_ON: False}
    co.handle_controller_state_updates.side_effect = state_writer(state)
    context = CommandContext(
        object(),
        co.cancel_command,
        0,
        "switch",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        switch = c.controller_switch_specs[0]
        co.cancel_command.set()
        await switch.set_fn(c, True)
        assert state[lp2.MASSAGE_ON] is False
        co.cancel_command.clear()
        await switch.set_fn(c, True)
        assert state[lp2.MASSAGE_ON] is True
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)


async def test_registered_service_validates_all_targets_before_first_write(hass):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import (
        async_register_lp2_services,
    )
    from custom_components.adjustable_bed.const import DOMAIN
    from tests.test_generic_services import target

    async_register_lp2_services(hass)
    a, first = target(
        family=lp2.Lp2Controller,
        layout="RMCS",
        program_schedule=AsyncMock(),
        schedule_frame=lambda _s: b"",
    )
    b, second = target(family=lp2.Lp2Controller, layout="APRM", program_schedule=AsyncMock())
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(a, "both"), (b, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="motor program"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "lp2",
            {
                "device_id": ["a", "b"],
                "operation": "motor_program",
                "confirm": True,
                "schedule": {
                    "records": [[i, 0, 0] for i in range(1, 13)],
                    "rest": 0,
                    "count": 0,
                    "radio": "ble",
                    "code": "new",
                    "identifier": 1,
                    "motors": [1, 2, 3, 4],
                },
            },
            blocking=True,
        )
    first.program_schedule.assert_not_awaited()
    second.program_schedule.assert_not_awaited()


def test_package_transport_falls_through_only_when_its_tuple_is_incomplete():
    from custom_components.adjustable_bed.codec.richmat import TRANSPORTS

    client = MagicMock()
    channels = {}
    services = {}
    for key in ("w0", "w1"):
        route = TRANSPORTS[key]
        write = SimpleNamespace(uuid=route.write_uuid, properties=["write"])
        notify = SimpleNamespace(uuid=route.notify_uuid, properties=["notify"])
        channels[key] = {route.write_uuid: write, route.notify_uuid: notify}
        service = MagicMock()
        service.get_characteristic.side_effect = channels[key].get
        services[route.service_uuid] = service
    client.services.get_service.side_effect = services.get
    assert lp2.select_transport(client).write is channels["w0"][TRANSPORTS["w0"].write_uuid]
    del channels["w0"][TRANSPORTS["w0"].notify_uuid]
    assert lp2.select_transport(client).write is channels["w1"][TRANSPORTS["w1"].write_uuid]
    del channels["w1"][TRANSPORTS["w1"].notify_uuid]
    with pytest.raises(ValueError, match="incomplete"):
        lp2.select_transport(client)


async def test_movement_test_cancellation_releases_before_any_next_phase(clock):
    c, co = controller("TEST")

    async def stop(_char, _data, **_kwargs):
        co.cancel_command.set()

    co.client.write_gatt_char.side_effect = stop
    await c.diagnostic_cycle()
    assert packets(co) == ["6e01002493", "6e01006edd"]


def test_service_number_values_are_normalized_before_packet_building():
    import voluptuous as vol

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import FIELDS

    request = vol.Schema(FIELDS)(
        {
            "device_id": "bed",
            "operation": "fan",
            "fan": "head",
            "duration": 3.0,
            "intensity": 60.0,
            "mode": 1.0,
            "motor": 3.0,
        }
    )
    assert all(type(request[key]) is int for key in ("duration", "intensity", "mode", "motor"))


async def test_alarm_preset_and_massage_composition_is_layout_owned(clock):
    c, co = controller("A9RM")
    alarm = AlarmRequest(
        enabled=True,
        wake_action="tv",
        massage=True,
        massage_zone="both",
        hour=12,
        minute=0,
        reference_time=datetime(2026, 11, 19, 12, tzinfo=UTC),
    )
    await c.configure_alarm(alarm)
    assert packets(co) == ["6e05a00013", "6e060577f0"]
    assert clock == [300, 300]
    # Owning a packet builder does not give a layout another preset.
    with pytest.raises(ValueError, match="offered"):
        c.validate_alarm(replace(alarm, wake_action="memory_3"))


def test_malformed_notification_retention_is_bounded_and_recovers():
    c, _ = controller()
    session = c._session
    c._notification(session, session.notify, bytearray(512))
    assert c._receive.buffer == ""
    c._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    assert c._receive.light_capable


async def test_raw_controls_name_the_effective_operand_and_reject_stale_buttons(clock):
    c, co = controller("BERM")
    framed = next(s for s in c.controller_button_specs if s.key == "richmat_classic_10_framed")
    assert framed.name == "Motor 3 down"
    c._session = replace(c._session, wire="RAW")
    save = next(s for s in c.controller_button_specs if s.key == "richmat_classic_10_raw")
    assert save.name == "Save M1"
    assert save.requires_confirmation and save.hold is None
    with pytest.raises(ValueError, match="held execution"):
        await c.execute_action(10, held=True)
    assert framed.key not in c.held_control_options
    with pytest.raises(ValueError, match="changed"):
        await framed.press_fn(c)
    with pytest.raises(ValueError, match="available held"):
        await c.hold_control(framed.key, 150)
    combined = next(s for s in c.controller_button_specs if s.key == "richmat_classic_15_raw")
    assert combined.name == "Motor 1+2 up"
    await combined.press_fn(c)
    assert packets(co) == ["36", "6e"]


@pytest.mark.parametrize("layout", ["ONRM", "BERM"])
async def test_raw_massage_off_never_advertises_or_publishes_ten_minutes(clock, layout):
    from tests.state_helpers import state_writer

    c, co = controller(layout)
    assert 10 in c.massage_timer_options
    c._session = replace(c._session, wire="RAW")
    # BERM has another genuine 10-minute control; ONRM has only the off operand.
    assert c._timer_controls.get(10) == (22 if layout == "BERM" else None)
    state = {}
    co.handle_controller_state_updates.side_effect = state_writer(state)
    if layout == "ONRM":
        with pytest.raises(ValueError, match="duration"):
            await c.set_massage_timer(10)
        assert lp2.MASSAGE_TIMER_MINUTES not in state
        co.client.write_gatt_char.assert_not_awaited()
    else:
        await c.set_massage_timer(10)
        assert packets(co) == ["5f", "6e"]
    assert any(
        "Massage" in s.name and "off" in s.name and c.controller_button_available(s.key)
        for s in c.controller_button_specs
    )


async def test_long_only_sync_pair_uses_switch_gestures(clock):
    c, co = controller("DXRM")
    switch = next(s for s in c.controller_switch_specs if s.key == "lp2_sync")
    assert all("Sync" not in s.name for s in c.controller_button_specs)
    await switch.set_fn(c, True)
    await switch.set_fn(c, False)
    assert packets(co) == ["6e0100bc2b", "6e01006edd", "6e0100bd2c", "6e01006edd"]
    assert clock.count(150) >= 2


@pytest.mark.parametrize("layout", ["E3RM", "BRRM"])
async def test_conflicting_long_and_held_flags_fail_before_worker(clock, layout):
    c, co = controller(layout)
    with pytest.raises(ValueError, match="either"):
        await c.execute_action(
            next(g.node for g in c._gestures("FRAMED") if g.long), long=True, held=True
        )
    co.client.write_gatt_char.assert_not_awaited()


def test_lp2_device_information_ownership_is_known_before_controller_build():
    from custom_components.adjustable_bed.bed_traits import bed_traits

    assert bed_traits("richmat_classic_apps", "lp2").owns_device_info_reads
    assert not bed_traits("richmat_classic_apps", "milemont").owns_device_info_reads


@pytest.mark.parametrize("operation", ["color", "aromatherapy"])
async def test_live_capabilities_of_entire_batch_precede_settings(hass, operation):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import (
        async_register_lp2_services,
    )
    from custom_components.adjustable_bed.const import DOMAIN
    from tests.test_generic_services import target

    async_register_lp2_services(hass)
    a, first = target(family=lp2.Lp2Controller, settings=AsyncMock())
    b, second = target(family=lp2.Lp2Controller, settings=AsyncMock())
    for child, c, supported in ((a, first, True), (b, second, False)):
        c._receive = SimpleNamespace(light_capable=supported, aroma_capable=supported)

        async def query(fn, *, current=c, **_kwargs):
            return await fn(current)

        child.async_execute_controller_query = AsyncMock(side_effect=query)
    values = {"rgb_color": [1, 2, 3]} if operation == "color" else {"aroma_times": [1, 2, 3]}
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(a, "both"), (b, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="support"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "lp2",
            {"device_id": ["a", "b"], "operation": operation, **values},
            blocking=True,
        )
    first.settings.assert_not_awaited()
    second.settings.assert_not_awaited()
    a.async_execute_controller_query.assert_awaited_once()
    b.async_execute_controller_query.assert_awaited_once()


@pytest.mark.parametrize("stop_during", ["preflight", "first_connection"])
async def test_stop_on_later_target_aborts_batch_before_first_write(hass, stop_during):
    from unittest.mock import patch

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import (
        async_register_lp2_services,
    )
    from custom_components.adjustable_bed.const import DOMAIN
    from tests.test_generic_services import target

    async_register_lp2_services(hass)
    a, first = target(family=lp2.Lp2Controller, settings=AsyncMock())
    b, second = target(family=lp2.Lp2Controller, settings=AsyncMock())
    if stop_during == "preflight":
        first._model = second._model = SimpleNamespace(modes=(0,))
        first.validate_action.return_value = (lp2.Gesture(1, "@string/k_motor1_up", 1),)

        def stop(*_args, **_kwargs):
            b.stop_epoch += 1
            return (lp2.Gesture(1, "@string/k_motor1_up", 1),)

        second.validate_action.side_effect = stop
        data = {"operation": "control", "control": 1}
    else:

        async def connect_then_run(fn, **_kwargs):
            b.stop_epoch += 1
            await fn(first)

        a.async_execute_controller_command.side_effect = connect_then_run
        data = {"operation": "fan", "fan": "head", "intensity": 20, "duration": 1}
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(a, "both"), (b, "both")], []),
    ):
        await hass.services.async_call(
            DOMAIN, "lp2", {"device_id": ["a", "b"], **data}, blocking=True
        )
    first.settings.assert_not_awaited()
    second.settings.assert_not_awaited()
    first.execute_action.assert_not_awaited()
    second.execute_action.assert_not_awaited()


@pytest.mark.parametrize(
    "layout,wire,extra,message",
    [
        ("BERM", "RAW", {"control": 10}, "Confirm"),
        ("E3RM", "FRAMED", {"control": 1, "long": True, "held": True, "confirm": True}, "either"),
    ],
)
async def test_service_rejects_unconfirmed_raw_save_and_conflicting_flags(
    hass, layout, wire, extra, message
):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import (
        async_register_lp2_services,
    )
    from custom_components.adjustable_bed.const import DOMAIN
    from tests.test_generic_services import target

    async_register_lp2_services(hass)
    actual, _ = controller(layout, wire)
    child, mock = target(family=lp2.Lp2Controller, execute_action=AsyncMock())
    mock._model = actual._model
    mock.validate_action = actual.validate_action
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(child, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match=message),
    ):
        await hass.services.async_call(
            DOMAIN, "lp2", {"device_id": "bed", "operation": "control", **extra}, blocking=True
        )
    mock.execute_action.assert_not_awaited()


@pytest.mark.parametrize("duration", [None, 450, 60000])
async def test_status_one_save_has_one_emission_regardless_of_movement_duration(clock, duration):
    c, co = controller("BERM", "RAW")
    await c.execute_action(10, hold_ms=duration)
    assert packets(co) == ["43", "6e"]
    assert clock == [50]


@pytest.mark.parametrize("side", ["left", "both"])
async def test_paired_movement_accepts_its_own_native_generation(hass, side):
    from unittest.mock import patch

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import (
        async_register_lp2_services,
    )
    from custom_components.adjustable_bed.const import DOMAIN, PAIR_CONNECTION_MODE_SEQUENTIAL
    from tests.test_paired_coordinator import _pair

    async_register_lp2_services(hass)
    parent, left, right = _pair([], mode=PAIR_CONNECTION_MODE_SEQUENTIAL)
    controllers = []
    for child in (left, right):
        c, _ = controller("6BRM")
        c.execute_action = AsyncMock()
        child.controller = child.capability_controller = c
        controllers.append(c)

        async def execute(fn, *, selected=c, **_kwargs):
            await fn(selected)

        child.async_execute_controller_command = AsyncMock(side_effect=execute)
    before = parent._pair_cancel_generation("left", frozenset({"movement"}))
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(parent, side)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "lp2",
            {"device_id": "pair", "side": side, "operation": "control", "control": 1},
            blocking=True,
        )
    assert parent._pair_cancel_generation("left", frozenset({"movement"})) != before
    assert parent.stop_count("left") == parent.stop_count("right") == 0
    controllers[0].execute_action.assert_awaited_once()
    assert controllers[1].execute_action.await_count == (1 if side == "both" else 0)
