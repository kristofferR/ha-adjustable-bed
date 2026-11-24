"""Maxprime setup, connection roles and representative native actions."""

import asyncio
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic.controller import (
    RichmatClassicController,
)
from custom_components.adjustable_bed.beds.richmat_classic.maxprime import MaxprimeController
from custom_components.adjustable_bed.beds.richmat_classic.requests import Request
from custom_components.adjustable_bed.beds.richmat_classic.transport import ROUTES
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import maxprime
from tests.hold_lease_wire import virtual_clock
from tests.test_richmat_classic_transport import Service, Services, channel, route
from tests.test_richmat_family_flow import answer, fields, setup_flow

FRAMED_SERVICE = "0000fee9-0000-1000-8000-00805f9b34fb"


def controller(layout, *, wire="FRAMED", fallback=False):
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.entry.data = {
        const.CONF_PRODUCT_TYPE: layout,
        const.CONF_PROTOCOL_VARIANT: "maxprime",
        const.CONF_RICHMAT_CLASSIC_THIRD_SERVICE: fallback,
    }
    coordinator.client.is_connected = True
    coordinator.client.services = Services([route(0 if wire == "FRAMED" else 2)])
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    ctrl = MaxprimeController(coordinator, device_name=layout)
    coordinator.controller = ctrl
    return ctrl, coordinator


def packets(coordinator):
    return [call.args[1].hex() for call in coordinator.client.write_gatt_char.await_args_list]


def connected_coordinator(hass, layout: str, address: str, *, release: bool = False):
    return connected_profile(hass, layout, address, "maxprime", MaxprimeController, release=release)


def connected_legacy(hass, layout: str, address: str, *, release: bool = False):
    return connected_profile(
        hass, layout, address, "avocadoecobase", RichmatClassicController, release=release
    )


def connected_profile[T: RichmatClassicController](
    hass, layout: str, address: str, variant: str, cls: type[T], *, release: bool
) -> tuple[T, AdjustableBedCoordinator]:
    _, double = controller(layout)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        state=ConfigEntryState.LOADED,
        data={
            **double.entry.data,
            CONF_ADDRESS: address,
            const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            const.CONF_PROTOCOL_VARIANT: variant,
            const.CONF_CONNECTION_MODE: (
                const.CONNECTION_MODE_RELEASE if release else const.CONNECTION_MODE_IDLE
            ),
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    ctrl = cls(co, device_name=layout)
    co.async_ensure_connected = AsyncMock(return_value=True)
    co._controller = ctrl
    co._client = double.client
    co._client.disconnect = AsyncMock()
    co._is_connected = True
    return ctrl, co


def test_selector_distinguishes_name_only_aliases_manual_and_code_entry():
    assert maxprime.advertised_layout("MPE_HJ002-bed") == "TWRM"
    assert maxprime.advertised_layout("MPE_HJ006-1") == "BNRM"
    assert maxprime.interval_ms("MPE_HJ002-bed", raw=True) == 150
    assert maxprime.interval_ms("TWRM-bed", raw=True) == 110
    assert maxprime.interval_ms("6BRM-bed", raw=True) == 170
    assert maxprime.manual_layout("B6RU") == "B6RM"
    assert not maxprime.scan_matches("B6RU")
    assert maxprime.advertised_layout("209A05-bed") is None
    assert maxprime.advertised_layout("COOL TOUCH") is None
    assert maxprime.manual_layout("QRRM") == "QRRM"
    assert maxprime.manual_layout("MPE_HJ002") is None
    assert maxprime.manual_layout(" A0RM ") is None
    assert maxprime.manual_layout("OTRM") == "OTRM"
    assert maxprime.manual_layout("OTRM", russian=True) == "O0RM"


@pytest.mark.parametrize("services,default", [([], vol.UNDEFINED), ([FRAMED_SERVICE], "TWRM")])
async def test_app_choice_preserves_exact_receiver_corroboration(hass, services, default):
    flow = setup_flow(hass, "MPE_HJ002-bed")
    flow._discovery_info.service_uuids = services
    result, _ = await answer(flow, "maxprime")
    selected = fields(result)[const.CONF_PRODUCT_TYPE].default
    assert (selected() if callable(selected) else selected) == default
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: "ZRS3:AQRM"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == "maxprime"
    assert saved[const.CONF_PRODUCT_TYPE] == "AQRM"
    assert saved[const.CONF_BLE_DEVICE_NAME] == "MPE_HJ002-bed"
    entry = MockConfigEntry(domain=const.DOMAIN, data=saved)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    assert isinstance(coordinator.capability_controller, MaxprimeController)
    await coordinator.async_shutdown()


async def test_startup_priority_partial_route_and_property_fallback():
    ctrl, coordinator = controller("6BRM", fallback=True)
    client = coordinator.client
    client.services = Services([route(2), route(1), route(0)])
    with virtual_clock():
        await ctrl.start_notify()
        assert packets(coordinator) == ["6e02010071"]
        await ctrl.async_after_connect(SimpleNamespace(is_current=lambda: True))
    assert client.start_notify.await_args.args[0].uuid == ROUTES[0][2]
    assert packets(coordinator) == ["6e02010071", "6e0a000179", "6e1a000088"]
    await ctrl.stop_notify()
    client.write_gatt_char.reset_mock()
    client.services = Services([route(2), Service(FRAMED_SERVICE, [])])
    with pytest.raises(ConnectionError):
        await ctrl.start_notify()
    assert not packets(coordinator)
    client.services = Services(
        [
            Service("other", []),
            Service("another", []),
            Service(
                "vendor",
                [
                    channel("first", "write"),
                    channel("notify", "notify"),
                    channel("last", "write-without-response"),
                    channel("read", "read"),
                ],
            ),
        ]
    )
    client.start_notify.reset_mock()
    with virtual_clock():
        await ctrl.start_notify()
        await ctrl.async_after_connect(SimpleNamespace(is_current=lambda: True))
        assert not packets(coordinator)
        await ctrl.hold_control(ctrl.held_control_options[0], 100)
    assert packets(coordinator) == ["34", "6e"]
    assert all(
        call.args[0].uuid == "last" and call.kwargs["response"] is False
        for call in client.write_gatt_char.await_args_list
    )
    client.start_notify.assert_not_awaited()


async def test_optional_probe_failure_keeps_bed_command_session():
    ctrl, coordinator = controller("6BRM")
    client = coordinator.client

    async def reject_lamp(_char, packet, **_kwargs):
        if packet.hex() == "6e0a000179":
            raise BleakError("lamp probe unavailable")

    client.write_gatt_char.side_effect = reject_lamp
    with virtual_clock():
        await ctrl.start_notify()
        await ctrl.async_after_connect(SimpleNamespace(is_current=lambda: True))
        assert ctrl.protocol_diagnostics["rejection"] == "Settings probe failed"
        await ctrl.stop_all()
    assert packets(coordinator) == ["6e02010071", "6e0a000179", "6e1a000088", "6e01006edd"]


async def test_execution_defaults_for_unconnected_and_one_shot_layouts():
    ctrl, _ = controller("6BRM")
    assert ctrl.execution.hold != "stream"
    ctrl, _ = controller("DYRM")
    with virtual_clock():
        await ctrl.start_notify()
    assert not ctrl.held_control_options
    assert ctrl.execution.hold != "stream"


async def test_layout_change_cannot_reuse_a_motor_or_preset_button_id():
    a, _ = controller("A0RM")
    b, _ = controller("U3RM")
    with virtual_clock():
        await a.start_notify()
        await b.start_notify()
    first = {spec.key for spec in a.controller_button_specs if spec.hold}
    second = {spec.key for spec in b.controller_button_specs if not spec.release_only}
    assert first and second and first.isdisjoint(second)


@pytest.mark.parametrize("release_fails", [False, True])
async def test_wrapped_mode_hold_cleanup_uses_admitted_mode_through_public_stop(
    hass,
    release_fails,
):
    ctrl, coordinator = connected_coordinator(hass, "DHRM", "AA:BB:CC:DD:EE:44")
    client = coordinator.client
    with virtual_clock():
        await ctrl.start_notify()
        client.write_gatt_char.reset_mock()
        choose = ctrl.controller_select_specs[0].local_select_fn
        assert choose is not None
        choose("1")
        control = ctrl.held_control_options[0]
        sent, finish = asyncio.Event(), asyncio.Event()

        async def blocked_write(_char, packet, **_kwargs):
            nonlocal release_fails
            if not sent.is_set():
                sent.set()
                await finish.wait()
            elif release_fails and packet.hex() == "6e01016ede":
                release_fails = False
                raise BleakError("release did not reach the bed")

        retry = release_fails
        client.write_gatt_char.side_effect = blocked_write

        async def hold(current):
            await current.hold_control(control, 1000)

        move = asyncio.create_task(
            coordinator.async_execute_controller_command(hold, resource="movement")
        )
        await sent.wait()
        choose("0")
        stop = asyncio.create_task(coordinator.async_stop_command())
        await asyncio.sleep(0)
        finish.set()
        await stop
        with suppress(asyncio.CancelledError, BleakError):
            await move
        assert packets(coordinator) == ["6e01012494", *(["6e01016ede"] * (2 if retry else 1))]
        await coordinator.async_stop_command()
        assert packets(coordinator)[-1] == "6e01006edd"
    await coordinator.async_shutdown()


async def test_settings_batch_checks_the_second_receiver_before_changing_the_first(hass):
    first, left = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:41")
    second, right = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:42")
    await services.async_register_services(hass)
    targets = [(left, "both"), (right, "both")]
    with (
        virtual_clock(),
        patch.object(services, "_resolve_sided_targets", return_value=(targets, [])),
    ):
        await first.start_notify()
        await second.start_notify()
        for co in (left, right):
            co.client.write_gatt_char.reset_mock()
        rx = SimpleNamespace(uuid=ROUTES[0][2])
        left.client.start_notify.await_args.args[1](rx, bytearray.fromhex("6e0e00037f"))
        data = {
            "device_id": ["left-bed", "right-bed"],
            "operation": "rgb",
            "rgb_color": [18, 52, 86],
        }
        with pytest.raises(ServiceValidationError) as rejected:
            await hass.services.async_call(const.DOMAIN, "richmat_classic", data, blocking=True)
        assert rejected.value.translation_key == "maxprime_settings"
        assert not packets(left) and not packets(right)

        right.client.start_notify.await_args.args[1](rx, bytearray.fromhex("6e0e00037f"))
        await hass.services.async_call(const.DOMAIN, "richmat_classic", data, blocking=True)
        assert packets(left) == packets(right) == ["6e0cff128b6e0d345605"]
    await left.async_shutdown()
    await right.async_shutdown()


async def test_settings_batch_uses_loaded_profile_during_entry_reload(hass):
    first, left = connected_legacy(hass, "YFRM", "AA:BB:CC:DD:EE:54")
    second, right = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:55")
    registry = dr.async_get(hass)
    device_ids = []
    for co in (left, right):
        hass.data.setdefault(const.DOMAIN, {})[co.entry.entry_id] = co
        device_ids.append(
            registry.async_get_or_create(
                config_entry_id=co.entry.entry_id, **co.device_info
            ).id
        )
    await services.async_register_services(hass)
    with virtual_clock():
        await first.start_notify()
        await second.start_notify()
        for co in (left, right):
            co.client.write_gatt_char.reset_mock()
        rx = SimpleNamespace(uuid=ROUTES[0][2])
        left.client.start_notify.await_args.args[1](rx, bytearray.fromhex("6e0e00037f"))

        # The save has landed while the previous coordinator still owns the device.
        new_data = {**right.entry.data, const.CONF_PROTOCOL_VARIANT: "avocadoecobase"}
        new_data[const.CONF_PROFILE_ID] = resolve_profile_id(new_data)
        hass.config_entries.async_update_entry(right.entry, data=new_data)
        assert right.profile_id != new_data[const.CONF_PROFILE_ID]
        with pytest.raises(ServiceValidationError) as rejected:
            await hass.services.async_call(
                const.DOMAIN,
                "richmat_classic",
                {"device_id": device_ids, "operation": "rgb", "rgb_color": [18, 52, 86]},
                blocking=True,
            )
        assert rejected.value.translation_key == "maxprime_settings"
        assert not packets(left) and not packets(right)
    await left.async_shutdown()
    await right.async_shutdown()


@pytest.mark.parametrize("wire,end", [("RAW", []), ("FRAMED", ["6e01006edd"])])
async def test_long_only_lock_and_short_only_recall_have_distinct_release(wire, end):
    ctrl, coordinator = controller("AORM", wire=wire)
    with virtual_clock():
        await ctrl.start_notify()
        coordinator.client.write_gatt_char.reset_mock()
        lock = next(b for b in ctrl.controller_button_specs if b.name == "Lock")
        assert lock.hold is None and lock.key.endswith("_long")
        start = asyncio.get_running_loop().time()
        await lock.press_fn(ctrl)
        assert asyncio.get_running_loop().time() - start == pytest.approx(
            4.95 + (0.05 if end else 0)
        )
    assert packets(coordinator) == (["84"] if wire == "RAW" else ["6e010084f3"]) + end
    ctrl, coordinator = controller("YRRM", wire=wire)
    with virtual_clock():
        await ctrl.start_notify()
        coordinator.client.write_gatt_char.reset_mock()
        tv = next(b for b in ctrl.controller_button_specs if b.name == "TV")
        await tv.press_fn(ctrl)
    assert packets(coordinator) == (["58", "6e"] if wire == "RAW" else ["6e010058c7", "6e01006edd"])


async def test_alternate_save_never_holds_and_reply_gates_settings():
    ctrl, coordinator = controller("YFRM")
    with virtual_clock():
        await ctrl.start_notify()
        client = coordinator.client
        client.write_gatt_char.reset_mock()
        choose = ctrl.controller_select_specs[0].local_select_fn
        assert choose is not None
        choose("hold")
        save = next(
            b
            for b in ctrl.controller_button_specs
            if b.name == "Save M1" and ctrl.controller_button_available(b.key)
        )
        assert save.requires_confirmation and save.hold is None
        await save.press_fn(ctrl)
        assert packets(coordinator) == ["6e01002b9a", "6e01006edd"]
        with pytest.raises(ServiceValidationError):
            await ctrl.set_light_color((18, 52, 86))
        callback = client.start_notify.await_args.args[1]
        rx = SimpleNamespace(uuid=ROUTES[0][2])
        callback(rx, bytearray.fromhex("6e0e00037f00fe"))
        assert not ctrl.supports_light_color_control
        callback(rx, bytearray.fromhex("6e0e00037f"))
        callback(rx, bytearray.fromhex("6e1a000189"))
        assert ctrl.supports_light_color_control
        await ctrl.set_light_color((18, 52, 86))
        await ctrl.async_execute_richmat_classic_request(Request("aroma", aroma_values=(60, 2, 12)))
        assert packets(coordinator)[-4:] == [
            "6e0cff128b6e0d345605",
            "6e1b003cc5",
            "6e1c00028c",
            "6e1d000c97",
        ]
        await ctrl.stop_notify()
    callback(rx, bytearray.fromhex("6e0e00037f"))
    assert not ctrl.supports_light_color_control


@pytest.mark.parametrize("legacy_first", [False, True])
async def test_settings_batch_holds_checked_links_across_release_timeout(hass, legacy_first):
    make_first = connected_legacy if legacy_first else connected_coordinator
    first, left = make_first(hass, "YFRM", "AA:BB:CC:DD:EE:46", release=True)
    second, right = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:47", release=True)
    await services.async_register_services(hass)

    async def slow_connection(**_kwargs):
        # A connection to the next receiver takes longer than the Release grace.
        await asyncio.sleep(2)
        return True

    right.async_ensure_connected = AsyncMock(side_effect=slow_connection)
    radios = (left.client, right.client)
    targets = [(left, "both"), (right, "both")]
    with (
        virtual_clock(),
        patch.object(services, "_resolve_sided_targets", return_value=(targets, [])),
    ):
        for ctrl, radio in zip((first, second), radios, strict=True):
            await ctrl.start_notify()
            radio.write_gatt_char.reset_mock()
            callback = radio.start_notify.await_args.args[1]
            callback(SimpleNamespace(uuid=ROUTES[0][2]), bytearray.fromhex("6e1a000189"))
        await hass.services.async_call(
            const.DOMAIN,
            "richmat_classic",
            {
                "device_id": ["left-bed", "right-bed"],
                "operation": "aroma",
                "aroma_times": [60, 2, 12],
            },
            blocking=True,
        )
        expected = ["6e1b003cc5", "6e1c00028c", "6e1d000c97"]
        assert packets(left) == packets(right) == expected
        for radio in radios:
            radio.disconnect.assert_not_awaited()
    await left.async_shutdown()
    await right.async_shutdown()


async def test_settings_rejects_lost_validated_session_before_the_first_write(hass):
    first, left = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:48")
    second, right = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:49")
    await services.async_register_services(hass)
    targets = [(left, "both"), (right, "both")]
    with (
        virtual_clock(),
        patch.object(services, "_resolve_sided_targets", return_value=(targets, [])),
    ):
        for ctrl, co in ((first, left), (second, right)):
            await ctrl.start_notify()
            co.client.write_gatt_char.reset_mock()
            callback = co.client.start_notify.await_args.args[1]
            callback(SimpleNamespace(uuid=ROUTES[0][2]), bytearray.fromhex("6e0e00037f"))
        original = second.settings_session

        def swap_after_check(request):
            proven = original(request)
            # Same BleakClient can have a fresh subscription during link recovery.
            second._session = replace(proven)
            return proven

        with (
            patch.object(second, "settings_session", side_effect=swap_after_check),
            pytest.raises(ServiceValidationError) as rejected,
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "richmat_classic",
                {
                    "device_id": ["left-bed", "right-bed"],
                    "operation": "rgb",
                    "rgb_color": [18, 52, 86],
                },
                blocking=True,
            )
        assert rejected.value.translation_key == "bed_changed"
        assert not packets(left) and not packets(right)
    await left.async_shutdown()
    await right.async_shutdown()


@pytest.mark.parametrize("invalidate", ["session", "stop"])
@pytest.mark.parametrize("legacy_side", [None, "left", "right"])
async def test_settings_rechecks_peer_after_waiting_for_the_gatt_lock(
    hass, invalidate, legacy_side
):
    make_first = connected_legacy if legacy_side == "left" else connected_coordinator
    make_second = connected_legacy if legacy_side == "right" else connected_coordinator
    first, left = make_first(hass, "YFRM", "AA:BB:CC:DD:EE:52")
    second, right = make_second(hass, "YFRM", "AA:BB:CC:DD:EE:53")
    await services.async_register_services(hass)
    targets = [(left, "both"), (right, "both")]
    with (
        virtual_clock(),
        patch.object(services, "_resolve_sided_targets", return_value=(targets, [])),
    ):
        for ctrl, co in ((first, left), (second, right)):
            await ctrl.start_notify()
            co.client.write_gatt_char.reset_mock()
            callback = co.client.start_notify.await_args.args[1]
            callback(SimpleNamespace(uuid=ROUTES[0][2]), bytearray.fromhex("6e0e00037f"))

        waiting = asyncio.Event()
        original = first._send

        async def send(packet, cancel=None):
            waiting.set()
            await original(packet, cancel)

        with patch.object(first, "_send", side_effect=send):
            async with first._ble_lock:
                call = asyncio.create_task(
                    hass.services.async_call(
                        const.DOMAIN,
                        "richmat_classic",
                        {
                            "device_id": ["left-bed", "right-bed"],
                            "operation": "rgb",
                            "rgb_color": [18, 52, 86],
                        },
                        blocking=True,
                    )
                )
                await waiting.wait()
                if invalidate == "session":
                    assert second._session is not None
                    second._session = replace(second._session)
                else:
                    await right.async_stop_command()

            if invalidate == "session":
                with pytest.raises(ServiceValidationError) as rejected:
                    await call
                assert rejected.value.translation_key == "bed_changed"
            else:
                await call
        assert not packets(left)
        assert packets(right) == (["6e01006edd"] if invalidate == "stop" else [])
    await left.async_shutdown()
    await right.async_shutdown()


async def test_sequential_pair_settings_validate_and_write_one_side_per_call(hass):
    first, left = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:50")
    _, right = connected_coordinator(hass, "YFRM", "AA:BB:CC:DD:EE:51")
    await services.async_register_services(hass)
    pair_entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "maxprime-settings"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass,
        pair_entry,
        {"left": left, "right": right},
        connection_mode=const.PAIR_CONNECTION_MODE_SEQUENTIAL,
    )
    left.async_connect = AsyncMock(return_value=True)
    radios = (left.client, right.client)

    async def drop(co: AdjustableBedCoordinator, _reason: str = "") -> bool:
        co.client.is_connected = False
        co._is_connected = False
        return True

    left.async_disconnect = AsyncMock(side_effect=partial(drop, left))
    right.async_disconnect = AsyncMock(side_effect=partial(drop, right))
    with (
        virtual_clock(),
        patch.object(
            services,
            "_resolve_sided_targets",
            side_effect=lambda _hass, _ids, side: ([(pair, side or "both")], []),
        ),
    ):
        await first.start_notify()
        for radio in radios:
            radio.write_gatt_char.reset_mock()
        callback = left.client.start_notify.await_args.args[1]
        callback(SimpleNamespace(uuid=ROUTES[0][2]), bytearray.fromhex("6e0e00037f"))
        data = {"device_id": "pair", "operation": "rgb", "rgb_color": [18, 52, 86]}
        with pytest.raises(ServiceValidationError) as rejected:
            await hass.services.async_call(const.DOMAIN, "richmat_classic", data, blocking=True)
        assert rejected.value.translation_key == "maxprime_settings_sequential"
        assert not packets(left) and not packets(right)

        await hass.services.async_call(
            const.DOMAIN,
            "richmat_classic",
            {**data, "side": "left"},
            blocking=True,
        )
        assert packets(left) == ["6e0cff128b6e0d345605"]
        assert not packets(right)
    await left.async_shutdown()
    await right.async_shutdown()


async def test_alarm_requires_current_reply_and_uses_next_target_minute():
    ctrl, coordinator = controller("A9RM")
    assert ctrl.alarm_capability is not None
    time = datetime(2026, 7, 17, 7, 30, tzinfo=UTC)
    alarm = AlarmRequest(enabled=True, reference_time=time, hour=7, minute=30, wake_action="zero_g")
    with virtual_clock():
        await ctrl.start_notify()
        client = coordinator.client
        client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await ctrl.configure_alarm(alarm)
        callback = client.start_notify.await_args.args[1]
        callback(SimpleNamespace(uuid=ROUTES[0][2]), bytearray.fromhex("6e09010078"))
        with patch(
            "custom_components.adjustable_bed.beds.richmat_classic.maxprime.dt_util.now",
            return_value=time,
        ):
            await ctrl.configure_alarm(alarm)
    assert packets(coordinator) == ["6e05a00013", "6e060545be"]
