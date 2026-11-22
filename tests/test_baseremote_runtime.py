"""Saved Base Remote profiles through real setup, entities and scheduling."""

from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.baseremote.controller import BaseRemoteController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.hold_lease_wire import virtual_clock
from tests.test_richmat_family_flow import answer, fields, setup_flow


async def test_setup_and_reconfigure_keep_base_remote_and_its_searchable_layout(hass):
    flow = setup_flow(hass, "6BRM-bed")
    form, _ = await answer(flow, "baseremote")
    assert form["step_id"] == "profile_questions"
    assert fields(form)[const.CONF_PRODUCT_TYPE].default is vol.UNDEFINED
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: "O0RM"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == "baseremote"
    entry = MockConfigEntry(domain=const.DOMAIN, data=saved)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    assert isinstance(coordinator.capability_controller, BaseRemoteController)
    options = AdjustableBedOptionsFlow(entry)
    options.hass = hass
    options.handler = entry.entry_id
    form = await options.async_step_settings()
    assert const.CONF_PRODUCT_TYPE in {str(key) for key in form["data_schema"].schema}
    result = await options.async_step_settings({const.CONF_PRODUCT_TYPE: "B6RU"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == "baseremote"
    assert entry.data[const.CONF_PRODUCT_TYPE] == "B6RM"
    await coordinator.async_shutdown()


async def test_native_button_uses_real_command_lane_and_current_profile(hass):
    from tests.test_baseremote import controller, packets

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:66",
            const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            const.CONF_PROTOCOL_VARIANT: "baseremote",
            const.CONF_PRODUCT_TYPE: "6BRM",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    ctrl, double = controller()
    ctrl._coordinator = coordinator
    coordinator._controller = ctrl
    double.client.disconnect = AsyncMock()
    coordinator._client = double.client
    coordinator._cancel_command = double.cancel_command
    coordinator._is_connected = True

    async def connected(reset_timer=True):
        return True

    coordinator.async_ensure_connected = connected
    spec = next(s for s in ctrl.controller_button_specs if s.key == "baseremote_m0_n1_53")
    entity = ControllerActionButton(coordinator, spec)
    entity.hass = hass
    with virtual_clock():
        await entity.async_press()
    assert packets(double)[-1] == "6e01006edd"
    assert packets(double)[0] == "6e01002493"
    await coordinator.async_shutdown()


async def test_reconfigure_reaches_the_same_base_remote_layout_question(
    hass, enable_custom_integrations
):
    from custom_components.adjustable_bed.profile_migration import reconfigure_context

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bed",
        unique_id="AA:BB:CC:DD:EE:66",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:66",
            const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            const.CONF_PROTOCOL_VARIANT: "baseremote",
            const.CONF_PRODUCT_TYPE: "6BRM",
        },
    )
    entry.add_to_hass(hass)
    manager = hass.config_entries.flow
    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    assert result["step_id"] == "reconfigure_bed_type"
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: "richmat_classic_apps:baseremote"}
    )
    assert result["step_id"] == "profile_questions"
    assert const.CONF_PRODUCT_TYPE in {str(key) for key in result["data_schema"].schema}
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.fixture
async def radios(hass, mock_coordinator_connected, mock_establish_connection):
    """Real connection and scheduler paths with a separate radio per receiver."""
    from unittest.mock import MagicMock

    from bleak import BleakClient

    from custom_components.adjustable_bed import services
    from tests.test_richmat_classic_transport import Service, Services, channel, route

    receivers = {}
    coordinators = []
    events = []
    await services.async_register_services(hass)

    async def establish(_class, _device, name, **_kwargs):
        client = receivers[name]
        client.is_connected = True
        events.append((name, "connect"))
        return client

    mock_establish_connection.side_effect = establish

    async def make(layout="6BRM"):
        name = f"Receiver {len(coordinators)}"
        client = MagicMock(spec=BleakClient)
        client.is_connected = False
        client.mtu_size = 23
        group = Service(
            "0000ffe0-0000-1000-8000-00805f9b34fb",
            [
                channel("0000ffe2-0000-1000-8000-00805f9b34fb", "write"),
                channel("0000ffe1-0000-1000-8000-00805f9b34fb", "notify"),
            ],
        )
        client.services = Services([route(0), group])
        for service in client.services:
            service.handle = 1
            for i, characteristic in enumerate(service.characteristics):
                characteristic.handle = i + 1
                characteristic.descriptors = []
                characteristic.service_uuid = service.uuid
        callbacks = {}

        async def notify(characteristic, callback):
            callbacks[characteristic.uuid] = callback

        async def write(_characteristic, packet, **_kwargs):
            if packet == bytes.fromhex("6e0a000179"):
                callbacks[client.services[0].characteristics[1].uuid](
                    None, bytearray.fromhex("6e0e00037f")
                )
            if packet.startswith(b"AT+"):
                events.append((name, "group"))

        async def disconnect():
            events.append((name, "disconnect"))
            client.is_connected = False

        client.start_notify = AsyncMock(side_effect=notify)
        client.stop_notify = AsyncMock()
        client.write_gatt_char = AsyncMock(side_effect=write)
        client.disconnect = AsyncMock(side_effect=disconnect)
        receivers[name] = client
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            version=5,
            title=name,
            data={
                CONF_ADDRESS: f"AA:BB:CC:DD:EE:{len(coordinators) + 1:02X}",
                "name": name,
                "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
                "protocol_variant": "baseremote",
                "product_type": layout,
                "disable_angle_sensing": True,
                "ble_device_name": "6BRM",
                "idle_disconnect_seconds": 0,
                "disconnect_after_command": False,
            },
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._max_retries = 1
        await coordinator.async_prime_offline_controller()
        coordinators.append(coordinator)
        return coordinator, client

    yield make, events
    for coordinator in coordinators:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("operation", ["set_color", "set_group"])
async def test_settings_connects_from_the_offline_profile(hass, radios, operation):
    from custom_components.adjustable_bed import services

    make, events = radios
    coordinator, client = await make()
    data = {"rgb_color": [18, 52, 86]} if operation == "set_color" else {"group": "1234"}
    with (
        patch.object(
            services, "_resolve_sided_targets", return_value=([(coordinator, "both")], [])
        ),
        virtual_clock(),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "baseremote_settings",
            {"device_id": "bed", "operation": operation, **data},
            blocking=True,
        )
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert ("Receiver 0", "connect") in events
    assert (
        bytes.fromhex("6e0cff128b6e0d345605") if operation == "set_color" else b"AT+GROUP1234\r\n"
    ) in packets
    if operation == "set_group":
        assert not client.is_connected


@pytest.mark.parametrize(
    "action,zone,code", [("tv", None, 0x58), ("head_massage", None, 0x4C), ("tv", "both", 0x77)]
)
async def test_shared_alarm_keeps_massage_optional(hass, radios, action, zone, code):
    from custom_components.adjustable_bed import services

    make, _ = radios
    coordinator, client = await make("A9RM")
    data = {"device_id": "bed", "enabled": True, "time": "07:30:00", "wake_action": action}
    if zone is not None:
        data["massage_zone"] = zone
    with (
        patch.object(
            services, "_resolve_sided_targets", return_value=([(coordinator, "both")], [])
        ),
        virtual_clock(),
    ):
        await hass.services.async_call(const.DOMAIN, "set_alarm", data, blocking=True)
    alarm = next(
        call.args[1] for call in client.write_gatt_char.await_args_list if call.args[1][1] == 6
    )
    assert alarm[3] == code


async def test_group_on_a_concurrent_pair_closes_each_receiver_before_the_next(hass, radios):
    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    make, events = radios
    left, left_client = await make()
    right, right_client = await make()
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data={"pair_id": "base-group"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(pair, "both")], [])),
        virtual_clock(),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "baseremote_settings",
            {"device_id": "bed", "operation": "set_group", "group": "1234"},
            blocking=True,
        )
    assert events == [
        ("Receiver 0", "connect"),
        ("Receiver 0", "group"),
        ("Receiver 0", "disconnect"),
        ("Receiver 1", "connect"),
        ("Receiver 1", "group"),
        ("Receiver 1", "disconnect"),
    ]
    assert not left_client.is_connected and not right_client.is_connected


async def test_capability_entities_keep_registry_identity_but_need_fresh_replies(hass, radios):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.entity_sweep import EntityLedger
    from custom_components.adjustable_bed.light import _light_entities_for
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from tests.error_helpers import raises_key

    make, _ = radios
    coordinator, client = await make("D1RM")
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    assert isinstance(ctrl, BaseRemoteController)
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e1a000189"))
    number = AdjustableBedControllerNumber(coordinator, ctrl.controller_number_specs[0])
    registry = er.async_get(hass)
    rows = [
        registry.async_get_or_create(
            domain, const.DOMAIN, coordinator.entity_unique_id(key), config_entry=coordinator.entry
        )
        for domain, key in ctrl.retained_entity_keys
    ]
    ctrl.on_disconnect()
    assert not number.available
    assert not ctrl.supports_light_color_control
    assert ctrl.light_color_control_pending
    assert _light_entities_for(hass, coordinator) == []
    with raises_key("baseremote_control"):
        await ctrl.set_light_color((18, 52, 86))
    ledger = EntityLedger(hass, coordinator.entry, coordinator)
    ledger.platforms_forwarded(["light", "number"])
    ledger.platform_finished("light")
    ledger.platform_finished("number")
    ledger.async_sweep()
    assert all(registry.async_get(row.entity_id) is not None for row in rows)
    with virtual_clock():
        await ctrl.start_notify()
    assert number.available


async def test_stop_on_other_side_during_group_subscription_prevents_every_group_write(
    hass, radios
):
    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    make, _ = radios
    left, left_client = await make()
    right, right_client = await make()
    with virtual_clock():
        assert await right.async_ensure_connected()
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data={"pair_id": "group-stop"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    original = left_client.start_notify.side_effect

    async def subscribe(characteristic, callback):
        if characteristic.uuid.startswith("0000ffe1"):
            await right.async_stop_command()
        return await original(characteristic, callback)

    left_client.start_notify.side_effect = subscribe
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(pair, "both")], [])),
        virtual_clock(),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "baseremote_settings",
            {"device_id": "bed", "operation": "set_group", "group": "1234"},
            blocking=True,
        )
    assert not left.cancel_command.is_set()
    assert not any(
        call.args[1].startswith(b"AT+")
        for client in (left_client, right_client)
        for call in client.write_gatt_char.await_args_list
    )


async def test_failed_group_close_clears_live_caps_and_retry_reinitializes(hass, radios):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from tests.error_helpers import raises_key

    make, _ = radios
    coordinator, client = await make("D1RM")
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    number = AdjustableBedControllerNumber(coordinator, ctrl.controller_number_specs[0])
    client.disconnect.side_effect = BleakError("still connected")
    with (
        patch.object(
            services, "_resolve_sided_targets", return_value=([(coordinator, "both")], [])
        ),
        virtual_clock(),
    ):
        with raises_key("baseremote_group_disconnect"):
            await hass.services.async_call(
                const.DOMAIN,
                "baseremote_settings",
                {"device_id": "bed", "operation": "set_group", "group": "1234"},
                blocking=True,
            )
        assert client.is_connected
        assert ctrl._session is None
        assert not number.available
        assert not ctrl.supports_light_color_control
        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "baseremote_settings",
            {"device_id": "bed", "operation": "set_color", "rgb_color": [18, 52, 86]},
            blocking=True,
        )
    packets = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert packets[0] == bytes.fromhex("6e02010071")
    assert packets[-1] == bytes.fromhex("6e0cff128b6e0d345605")
    assert number.available

    # Let fixture shutdown release the retained link.
    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect


async def test_group_cleanup_does_not_close_a_replacement_that_won_the_connection_lane(
    hass, radios, mock_establish_connection
):
    import asyncio
    from contextlib import asynccontextmanager

    from custom_components.adjustable_bed import services

    make, _ = radios
    coordinator, original_client = await make()
    _, replacement = await make()
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    write_started, finish_write, cleanup_waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_write = original_client.write_gatt_char.side_effect

    async def write(characteristic, packet, **kwargs):
        await original_write(characteristic, packet, **kwargs)
        if packet.startswith(b"AT+"):
            write_started.set()
            await finish_write.wait()

    original_client.write_gatt_char.side_effect = write
    connection_guard = coordinator.async_connection_operation_guard

    @asynccontextmanager
    async def observed_guard():
        cleanup_waiting.set()
        async with connection_guard() as disconnect:
            yield disconnect

    coordinator.async_connection_operation_guard = observed_guard

    async def establish(*_args, **_kwargs):
        replacement.is_connected = True
        return replacement

    mock_establish_connection.side_effect = establish
    with (
        patch.object(
            services, "_resolve_sided_targets", return_value=([(coordinator, "both")], [])
        ),
        virtual_clock(),
    ):
        group = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "baseremote_settings",
                {"device_id": "bed", "operation": "set_group", "group": "1234"},
                blocking=True,
            )
        )
        await write_started.wait()
        async with connection_guard():
            original_client.is_connected = False
            reconnect = asyncio.create_task(coordinator.async_connect())
            await asyncio.sleep(0)
            finish_write.set()
            await cleanup_waiting.wait()
        assert await reconnect
        with pytest.raises(ConnectionError, match="changed before group cleanup"):
            await group
    assert coordinator.client is replacement and replacement.is_connected
    replacement.disconnect.assert_not_awaited()


async def test_failed_reinitialization_rolls_back_partial_capabilities_and_subscription(
    hass, radios
):
    from bleak.exc import BleakError

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from tests.error_helpers import raises_key

    make, _ = radios
    coordinator, client = await make("D1RM")
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    number = AdjustableBedControllerNumber(coordinator, ctrl.controller_number_specs[0])
    client.disconnect.side_effect = BleakError("link retained")
    with (
        patch.object(
            services, "_resolve_sided_targets", return_value=([(coordinator, "both")], [])
        ),
        virtual_clock(),
    ):
        with raises_key("baseremote_group_disconnect"):
            await hass.services.async_call(
                const.DOMAIN,
                "baseremote_settings",
                {"device_id": "bed", "operation": "set_group", "group": "1234"},
                blocking=True,
            )
        previous_stops = client.stop_notify.await_count
        original_write = client.write_gatt_char.side_effect

        async def write(characteristic, packet, **kwargs):
            if packet == bytes.fromhex("6e1a000088"):
                raise BleakError("aroma probe failed")
            await original_write(characteristic, packet, **kwargs)

        client.write_gatt_char.side_effect = write
        with pytest.raises(BleakError, match="aroma probe failed"):
            await hass.services.async_call(
                const.DOMAIN,
                "baseremote_settings",
                {"device_id": "bed", "operation": "set_color", "rgb_color": [18, 52, 86]},
                blocking=True,
            )
        assert client.is_connected and ctrl._session is None
        assert not ctrl._notifications_started
        assert not ctrl.supports_light_color_control and not number.available
        assert ctrl.light_color_control_pending
        assert client.stop_notify.await_count == previous_stops + 1
        assert client.stop_notify.await_args.args[0] is client.services[0].characteristics[1]
        assert not any(
            call.args[1] == bytes.fromhex("6e0cff128b6e0d345605")
            for call in client.write_gatt_char.await_args_list
        )
        client.write_gatt_char.side_effect = original_write
        await hass.services.async_call(
            const.DOMAIN,
            "baseremote_settings",
            {"device_id": "bed", "operation": "set_color", "rgb_color": [18, 52, 86]},
            blocking=True,
        )
        assert number.available and ctrl.supports_light_color_control

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect


@pytest.mark.parametrize("phase", ["recovery", "group"])
@pytest.mark.parametrize("reply_error", [False, True])
@pytest.mark.parametrize("cleanup_error", [False, True])
async def test_start_notify_drains_bluez_registration_before_rollback(
    hass, radios, phase, reply_error, cleanup_error
):
    import asyncio
    from unittest.mock import MagicMock

    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
    from bleak.exc import BleakDBusError, BleakError
    from dbus_fast import Message, MessageType

    make, _ = radios
    coordinator, client = await make("D1RM")
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    if phase == "recovery":
        await ctrl.stop_notify()
    original_subscribe = client.start_notify.side_effect
    original_stop = client.stop_notify.side_effect
    original_disconnect = client.disconnect.side_effect
    backend = BleakClientBlueZDBus(coordinator.address, bluez={}, timeout=10)
    started, reply_ready = asyncio.Event(), asyncio.Event()
    calls = []

    async def bus_call(message):
        calls.append(message.member)
        if message.member == "StartNotify":
            started.set()
            await reply_ready.wait()
            if reply_error:
                return Message(
                    message_type=MessageType.ERROR,
                    reply_serial=1,
                    error_name="org.bluez.Error.Failed",
                    signature="s",
                    body=["notify failed"],
                )
        elif message.member == "StopNotify" and cleanup_error:
            return Message(
                message_type=MessageType.ERROR,
                reply_serial=1,
                error_name="org.bluez.Error.Failed",
                signature="s",
                body=["No notify session started"],
            )
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)

    backend._bus = MagicMock()
    backend._bus.call = AsyncMock(side_effect=bus_call)
    backend._is_connected = True
    client._backend = backend
    characteristic = client.services[0 if phase == "recovery" else 1].characteristics[1]
    path = "/org/bluez/hci0/dev_test/service0001/char0002"
    characteristic.obj = (path, {})

    async def subscribe(characteristic, callback):
        await backend.start_notify(characteristic, callback, bluez={"use_start_notify": True})

    async def unsubscribe(channel):
        if channel is characteristic:
            await backend.stop_notify(channel)

    client.start_notify.side_effect = subscribe
    client.stop_notify.side_effect = unsubscribe
    if cleanup_error:
        client.disconnect.side_effect = BleakError("disconnect failed")
    client.write_gatt_char.reset_mock()
    recovery = asyncio.create_task(
        ctrl.async_refresh_auth() if phase == "recovery" else ctrl.async_group("1234")
    )
    await started.wait()
    assert path in backend._notification_callbacks
    if not reply_error:
        recovery.cancel()
    await asyncio.sleep(0)
    assert not recovery.done()
    reply_ready.set()
    with pytest.raises(BleakDBusError if reply_error else asyncio.CancelledError) as caught:
        await recovery
    if reply_error:
        assert "notify failed" in str(caught.value)
    assert calls == ["StartNotify", "StopNotify"]
    assert not backend._notification_callbacks
    assert client.is_connected == (phase == "recovery" or cleanup_error)
    assert ctrl._session is None
    assert not ctrl._notifications_started and not ctrl.supports_light_color_control
    assert not client.write_gatt_char.await_args_list
    client.start_notify.side_effect = original_subscribe
    client.stop_notify.side_effect = original_stop
    client.disconnect.side_effect = original_disconnect
    with virtual_clock():
        await coordinator.async_execute_controller_command(
            lambda controller: controller.set_light_color((18, 52, 86))
        )
    assert client.write_gatt_char.await_args.args[1] == bytes.fromhex("6e0cff128b6e0d345605")


async def test_pairing_deadline_leaves_a_clean_session_for_the_next_command(hass, radios):
    import asyncio
    from contextlib import suppress
    from unittest.mock import MagicMock

    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
    from dbus_fast import Message, MessageType

    make, _ = radios
    coordinator, client = await make("D1RM")
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    session = ctrl._session
    primary = session.notify
    path = "/org/bluez/hci0/dev_test/service0000/char0002"
    primary.obj = (path, {})
    backend = BleakClientBlueZDBus(coordinator.address, bluez={}, timeout=10)
    backend._is_connected = True

    def old_callback(_data):
        pass

    backend._notification_callbacks[path] = old_callback
    began, reply_ready = asyncio.Event(), asyncio.Event()
    cancelled = False
    cleared_before_recovery = False

    async def bus_call(message):
        nonlocal cancelled
        if message.member == "StopNotify":
            began.set()
            try:
                await reply_ready.wait()
            except asyncio.CancelledError:
                cancelled = True
                raise
        if message.member == "StartNotify":
            await reply_ready.wait()
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)

    backend._bus = MagicMock()
    backend._bus.call = AsyncMock(side_effect=bus_call)
    client._backend = backend
    original_subscribe = client.start_notify.side_effect
    original_stop = client.stop_notify.side_effect

    async def subscribe(characteristic, callback):
        nonlocal cleared_before_recovery
        cleared_before_recovery = path not in backend._notification_callbacks
        await original_subscribe(characteristic, callback)
        await backend.start_notify(characteristic, callback, bluez={"use_start_notify": True})

    client.start_notify.side_effect = subscribe
    client.stop_notify.side_effect = backend.stop_notify
    client.start_notify.reset_mock()

    async def transfer():
        async with asyncio.timeout(0.02):
            await coordinator.async_release_for_pairing_transfer()

    with virtual_clock():
        release = asyncio.create_task(transfer())
        try:
            await began.wait()
            done, _ = await asyncio.wait((release,), timeout=7)
            assert done, "Pairing deadline must release the connection lane before the stop reply"
            with pytest.raises(TimeoutError):
                await release
            assert cancelled
            assert coordinator.is_connected and not coordinator._pairing_transfer_active
            assert ctrl._session is None and not ctrl._notifications_started
            assert not backend._notification_callbacks and not ctrl.supports_light_color_control
            client.start_notify.assert_not_awaited()
            async with coordinator.async_connection_operation_guard():
                pass
            # A command owns fresh initialization and its required drained ATT.
            reply_ready.set()
            await coordinator.async_execute_controller_command(
                lambda controller: controller.set_light_color((18, 52, 86))
            )
            assert cleared_before_recovery
            assert ctrl._session is not session and ctrl._notifications_started
            assert backend._notification_callbacks[path] is not old_callback
            assert client.write_gatt_char.await_args.args[1] == bytes.fromhex(
                "6e0cff128b6e0d345605"
            )
        finally:
            reply_ready.set()
            with suppress(TimeoutError):
                await release
            client.start_notify.side_effect = original_subscribe
            client.stop_notify.side_effect = original_stop


@pytest.mark.parametrize("group_only", [False, True])
async def test_group_failure_removes_primary_bluez_callback_on_retained_link(
    hass, radios, group_only
):
    from unittest.mock import MagicMock

    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
    from bleak.exc import BleakError
    from dbus_fast import Message, MessageType

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.errors import BedCommandFailedError
    from tests.error_helpers import raises_key
    from tests.test_richmat_classic_transport import Services

    make, _ = radios
    coordinator, client = await make("D1RM")
    if group_only:
        client.services = Services([client.services[1]])
    primary = client.services[0].characteristics[1]
    backend = BleakClientBlueZDBus(coordinator.address, bluez={}, timeout=10)
    calls = []

    async def bus_call(message):
        calls.append((message.member, message.path))
        if message.member == "StopNotify" or (
            message.member == "StartNotify" and message.path != primary.obj[0]
        ):
            return Message(
                message_type=MessageType.ERROR,
                reply_serial=1,
                error_name="org.bluez.Error.Failed",
                signature="s",
                body=[
                    "No notify session started"
                    if message.member == "StopNotify"
                    else "notify failed"
                ],
            )
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)

    backend._bus = MagicMock()
    backend._bus.call = AsyncMock(side_effect=bus_call)
    backend._is_connected = True
    client._backend = backend
    for index, service in enumerate(client.services):
        service.characteristics[1].obj = (
            f"/org/bluez/hci0/dev_test/service{index:04d}/char0002",
            {},
        )
    original_subscribe = client.start_notify.side_effect
    original_stop = client.stop_notify.side_effect
    original_disconnect = client.disconnect.side_effect

    async def subscribe(characteristic, callback):
        await original_subscribe(characteristic, callback)
        await backend.start_notify(characteristic, callback, bluez={"use_start_notify": True})

    client.start_notify.side_effect = subscribe
    client.stop_notify.side_effect = backend.stop_notify
    client.disconnect.side_effect = BleakError("disconnect failed")
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    ctrl = coordinator.controller
    assert primary.obj[0] in backend._notification_callbacks
    assert ctrl._notifications_started
    client.write_gatt_char.reset_mock()
    with (
        patch.object(
            services, "_resolve_sided_targets", return_value=([(coordinator, "both")], [])
        ),
        virtual_clock(),
        raises_key("baseremote_group_disconnect")
        if group_only
        else pytest.raises(BedCommandFailedError, match="notify failed"),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "baseremote_settings",
            {"device_id": "bed", "operation": "set_group", "group": "1234"},
            blocking=True,
        )
    assert client.is_connected and ctrl._session is None
    assert not backend._notification_callbacks
    assert not ctrl._notifications_started and not ctrl.supports_light_color_control
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == (
        [b"AT+GROUP1234\r\n"] if group_only else []
    )
    assert ("StopNotify", primary.obj[0]) in calls
    client.start_notify.side_effect = original_subscribe
    client.stop_notify.side_effect = original_stop
    client.disconnect.side_effect = original_disconnect
