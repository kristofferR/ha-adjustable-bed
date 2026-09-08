"""Controller behavior at the artifact/HA boundary for the explicit app profiles."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import jiecang_app_protocol as protocol
from custom_components.adjustable_bed.beds.jiecang_app import _TRANSPORTS, JiecangAppController


@pytest.fixture
def make_controller(monkeypatch):
    """Build actual GATT role maps; skip wall time without skipping packet writes."""

    async def pause(_milliseconds, cancel):
        return cancel.is_set()

    monkeypatch.setattr(JiecangAppController, "_pause", staticmethod(pause))

    def make(profile="dreamask", layout="standard_2", transports=("g1",), **options):
        characteristics = {}
        services = {}
        for transport in transports:
            service_uuid, write, notify, name = _TRANSPORTS[transport]
            members = {
                uuid: SimpleNamespace(uuid=uuid, properties=["write", "notify"])
                for uuid in (write, notify, name)
                if uuid
            }
            characteristics.update(members)
            services[service_uuid] = SimpleNamespace(get_characteristic=members.get)
        client = SimpleNamespace(
            is_connected=True,
            services=SimpleNamespace(
                get_service=services.get, get_characteristic=characteristics.get
            ),
            write_gatt_char=AsyncMock(),
            start_notify=AsyncMock(),
            stop_notify=AsyncMock(),
        )
        coordinator = SimpleNamespace(
            address="AA:BB:CC:DD:EE:FF",
            client=client,
            cancel_command=asyncio.Event(),
            motor_pulse_count=3,
            has_massage=True,
            handle_controller_state_updates=MagicMock(),
            async_execute_controller_command=AsyncMock(),
            hass=SimpleNamespace(async_create_task=asyncio.create_task),
        )
        controller = JiecangAppController(coordinator, profile=profile, layout=layout, **options)
        return controller, coordinator, client

    return make


def packets(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("profile,final", [("dreamask", 0), ("dreamotion", 1)])
async def test_held_movement_profile_release_and_final_command(make_controller, profile, final):
    controller, _, client = make_controller(profile=profile)
    await controller.move_back_up()
    assert packets(client) == [bytes.fromhex("f1f1010101037e")] * (3 + final) + [
        command for _, command in protocol.movement_releases(profile)
    ]


@pytest.mark.parametrize("profile", protocol.APP_PROFILES)
async def test_cancelled_movement_sends_only_fresh_release(make_controller, profile):
    controller, coordinator, client = make_controller(profile=profile)
    coordinator.cancel_command.set()
    await controller.move_back_up()
    assert packets(client) == [command for _, command in protocol.movement_releases(profile)]


async def test_failed_movement_still_releases(make_controller):
    controller, _, client = make_controller(profile="dreamotion")
    client.write_gatt_char.side_effect = [RuntimeError("failed"), None, None]
    with pytest.raises(RuntimeError, match="failed"):
        await controller.move_back_up()
    assert packets(client)[1:] == [protocol.SHORT_RELEASE, protocol.LONG_RELEASE]


async def test_presets_memory_and_programming_match_reachable_frames(make_controller):
    controller, _, client = make_controller(layout="standard_4_bilateral")
    await controller.preset_flat()
    await controller.preset_memory(2)
    await controller.program_memory(1)
    assert packets(client) == [
        bytes.fromhex("f1f1080200000a7e"),
        protocol.LONG_RELEASE,
        bytes.fromhex("f1f10d0200000f7e"),
        protocol.LONG_RELEASE,
        *([bytes.fromhex("f1f10a0200000c7e")] * 3),
    ]
    assert controller.memory_slot_count == 2
    with pytest.raises(ValueError):
        await controller.preset_memory(3)


@pytest.mark.parametrize("layout", protocol.LAYOUTS)
async def test_every_layout_exposes_routable_motor_specs(make_controller, layout):
    controller, coordinator, client = make_controller(layout=layout)
    coordinator.motor_pulse_count = 1
    assert tuple(spec.key for spec in controller.motor_control_specs) == protocol.layout_axes(
        layout
    )
    for spec in controller.motor_control_specs:
        client.write_gatt_char.reset_mock()
        await spec.open_fn(controller)
        assert packets(client)[0] == protocol.motion_command(layout, spec.key, True)
        client.write_gatt_char.reset_mock()
        await spec.close_fn(controller)
        assert packets(client)[0] == protocol.motion_command(layout, spec.key, False)


async def test_bilateral_massage_zones_and_alarm_stop_remain_distinct(make_controller):
    controller, _, client = make_controller(layout="standard_4_bilateral")
    assert controller.massage_intensity_zones == ["head", "right"]
    assert not controller.supports_foot_massage_intensity_step_control
    await controller.set_massage_intensity("right", 3)
    await controller.massage_off()
    await controller.stop_wake_routine()
    assert packets(client) == [
        bytes.fromhex("f1f122020004287e"),
        protocol.LONG_RELEASE,
        bytes.fromhex("f1f111020000137e"),
        bytes.fromhex("f1f11101081a7e"),
    ]
    assert controller.get_massage_state() == {"head_intensity": 0, "right_intensity": 0}


async def test_alarm_and_split_wake_use_shared_back_right_intensity(make_controller):
    controller, _, client = make_controller(layout="split_after_bilateral")
    await controller.configure_clock_alarm(
        enabled=True,
        weekdays=[0, 2, 4],
        hour=6,
        minute=30,
        preset="memory_1",
        head_level=2,
        foot_level=3,
    )
    assert packets(client) == [bytes.fromhex("f1f1510801012a061e030203b17e")]
    client.write_gatt_char.reset_mock()
    await controller.execute_wake_routine(preset="memory_1", head_level=2, foot_level=3)
    assert packets(client) == [
        command for _, command in protocol.wake_schedule("split_after_bilateral", "memory_1", 2, 3)
    ]
    assert bytes.fromhex("f1f1220208032f7e") in packets(client)
    with pytest.raises(ValueError, match="Yoga"):
        await controller.execute_wake_routine(preset="yoga")


async def test_failed_wake_always_releases(make_controller):
    controller, _, client = make_controller()
    client.write_gatt_char.side_effect = [RuntimeError("write failure"), None]
    with pytest.raises(RuntimeError, match="write failure"):
        await controller.execute_wake_routine(preset="flat", head_level=1)
    assert packets(client)[-1] == protocol.LONG_RELEASE


async def test_absolute_schedule_accounts_for_ble_latency(make_controller):
    controller, _, _ = make_controller()
    now = [10.0]
    writes = []

    async def pause(milliseconds, _cancel):
        now[0] += max(0, milliseconds) / 1000
        return False

    async def write(command, **_kwargs):
        writes.append((round((now[0] - 10) * 1000), command))
        now[0] += 0.01

    controller._pause = pause
    controller.write_command = write
    with patch(
        "custom_components.adjustable_bed.beds.jiecang_app.asyncio.get_running_loop",
        return_value=SimpleNamespace(time=lambda: now[0]),
    ):
        await controller._schedule(((0, b"a"), (30, b"b"), (60, b"c")))
    assert writes == [(0, b"a"), (30, b"b"), (60, b"c")]


async def test_gatt_bootstrap_idempotence_and_state_capabilities(make_controller):
    controller, _, client = make_controller()

    async def notify(uuid, callback):
        callback(SimpleNamespace(uuid=uuid), bytearray.fromhex("f2f20e00070000"))
        callback(SimpleNamespace(uuid=uuid), bytearray.fromhex("f2f2520733221164012c01517e"))

    client.start_notify.side_effect = notify
    await controller.async_discover_capabilities()
    await controller.start_notify()
    assert packets(client) == [command for _, command in protocol.BOOTSTRAP_SCHEDULE]
    assert client.start_notify.await_count == 1
    assert controller.supports_preset_yoga
    assert controller.supports_light_color_control
    assert controller.default_light_rgb_color == (17, 34, 51)
    await controller.stop_notify()
    client.stop_notify.assert_awaited_once_with(_TRANSPORTS["g1"][2])


async def test_cancelled_bootstrap_does_not_mark_controller_ready(make_controller):
    controller, coordinator, client = make_controller()
    coordinator.cancel_command.set()
    with pytest.raises(ConnectionError, match="cancelled"):
        await controller.start_notify()
    assert not controller._started
    assert not controller._subscriptions
    assert not packets(client)
    client.stop_notify.assert_awaited_once()


async def test_g2_standalone_is_dreamotion_only_and_has_no_bootstrap(make_controller):
    controller, _, client = make_controller(profile="dreamotion", transports=("g2",))
    await controller.start_notify()
    assert controller.control_characteristic_uuid == _TRANSPORTS["g2"][1]
    assert not packets(client)
    assert not controller.supports_device_rename
    other, _, _ = make_controller(profile="dreamask", transports=("g2",))
    with pytest.raises(ConnectionError, match="GATT"):
        await other.start_notify()


async def test_g2_copresent_still_bootstraps(make_controller):
    controller, _, client = make_controller(transports=("g1", "g2"), transport="g2")
    controller._capabilities_received.set()
    await controller.start_notify()
    assert packets(client) == [command for _, command in protocol.BOOTSTRAP_SCHEDULE]


@pytest.mark.parametrize("transport", ["g1", "g2"])
async def test_missing_g1_name_role_does_not_bootstrap(make_controller, transport):
    controller, _, client = make_controller(transports=("g1", "g2"), transport=transport)
    service = client.services.get_service(_TRANSPORTS["g1"][0])
    original = service.get_characteristic
    service.get_characteristic = lambda uuid: (
        None if uuid == _TRANSPORTS["g1"][3] else original(uuid)
    )
    await controller.start_notify()
    assert not packets(client)
    assert controller._started


async def test_retained_motor_spec_uses_reconnected_controller(make_controller):
    old, _, old_client = make_controller()
    current, _, current_client = make_controller()
    await old.motor_control_specs[0].open_fn(current)
    assert not packets(old_client)
    assert packets(current_client)


@pytest.mark.parametrize(
    "transport,expected", [("g1", b"Bed1"), ("g3", bytes.fromhex("01fc070442656431"))]
)
async def test_rename_uses_coherent_selected_transport(make_controller, transport, expected):
    controller, _, client = make_controller(transports=("g1", "g3"), transport=transport)
    controller._select_transport()
    await controller.rename_device("Bed1")
    assert packets(client) == [expected, expected]
    assert all(
        call.args[0] == _TRANSPORTS[transport][3] for call in client.write_gatt_char.await_args_list
    )
    with pytest.raises(ValueError, match="ASCII"):
        await controller.rename_device("Bed 1")


async def test_light_toggle_and_partial_changes_preserve_reported_fields(make_controller):
    controller, _, client = make_controller()
    sender = SimpleNamespace(uuid=_TRANSPORTS["g1"][2])
    controller._handle_notification(sender, bytearray.fromhex("f2f20e00070000"))
    controller._handle_notification(sender, bytearray.fromhex("f2f2520733221164012c01517e"))
    await controller.lights_toggle()
    assert packets(client) == [
        protocol.rgb_command(17, 34, 51, 100, 300, False),
        protocol.LIGHT_TOGGLE,
        protocol.SHORT_RELEASE,
        protocol.LONG_RELEASE,
    ]
    client.write_gatt_char.reset_mock()
    await controller.set_light_color((1, 2, 3))
    await controller.set_light_level(42)
    await controller.set_light_timer("600")
    assert packets(client) == [
        protocol.rgb_command(1, 2, 3, 100, 300, False),
        protocol.rgb_command(1, 2, 3, 42, 300, False),
        protocol.rgb_command(1, 2, 3, 42, 600, False),
    ]


async def test_missing_light_state_does_not_invent_settings(make_controller):
    controller, _, client = make_controller()
    with patch(
        "custom_components.adjustable_bed.beds.jiecang_app.asyncio.wait_for",
        side_effect=TimeoutError,
    ):
        # Avoid creating an unawaited Event.wait coroutine in the deliberately failing mock.
        controller._rgb_received.wait = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="No light state"):
            await controller.lights_toggle()
    assert packets(client) == [protocol.QUERY_LIGHT, protocol.QUERY_LIGHT]


@pytest.mark.parametrize("opcode", [5, 6])
async def test_legacy_light_status_wins_over_cached_rgb_for_later_writes(make_controller, opcode):
    controller, _, client = make_controller()
    sender = SimpleNamespace(uuid=_TRANSPORTS["g1"][2])
    controller._handle_notification(sender, bytearray.fromhex("f2f20e00070000"))
    controller._handle_notification(sender, bytearray.fromhex("f2f2520733221164012c01517e"))
    # A physical remote can turn off the light without sending another RGB reply.
    controller._handle_notification(sender, bytearray((0, 0, opcode, 0, 0, 0, 0, 0, 0)))
    await controller.set_light_color((1, 2, 3))
    assert packets(client) == [protocol.rgb_command(1, 2, 3, 100, 300, False)]
    client.write_gatt_char.reset_mock()
    await controller.lights_toggle()
    assert packets(client) == [
        protocol.rgb_command(1, 2, 3, 100, 300, True),
        protocol.LIGHT_TOGGLE,
        protocol.SHORT_RELEASE,
        protocol.LONG_RELEASE,
    ]


async def test_auto_light_is_state_guarded_and_idempotent(make_controller):
    controller, coordinator, client = make_controller()
    sender = SimpleNamespace(uuid=_TRANSPORTS["g1"][2])
    controller._handle_notification(sender, bytearray.fromhex("f2f20e00070000"))
    with pytest.raises(ValueError, match="Read automatic"):
        await controller.set_automatic_light(True)
    controller._handle_notification(sender, bytearray.fromhex("f2f25300000000"))
    await controller.set_automatic_light(True)
    assert not packets(client)
    await controller.set_automatic_light(False)
    assert packets(client) == [protocol.AUTOMATIC_LIGHT_TOGGLE]
    assert coordinator.handle_controller_state_updates.call_args.args[0]["automatic_light"] is False


async def test_clock_reply_uses_coordinator_serialization(make_controller):
    controller, coordinator, client = make_controller()

    async def execute(callback, **_kwargs):
        await callback(controller)

    coordinator.async_execute_controller_command.side_effect = execute
    controller._handle_notification(
        SimpleNamespace(uuid=_TRANSPORTS["g1"][2]), bytearray.fromhex("f2f250000000")
    )
    await controller._clock_task
    assert packets(client)[0][:4] == bytes.fromhex("f1f15007")
    assert coordinator.async_execute_controller_command.call_args.kwargs == {
        "cancel_running": False
    }
