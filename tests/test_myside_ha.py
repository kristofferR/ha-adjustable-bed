"""My Side's real setup, coordinator, entity and registered service paths."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.bed_traits import reads_positions
from custom_components.adjustable_bed.beds.myside import controller as bed
from custom_components.adjustable_bed.beds.myside import services
from custom_components.adjustable_bed.beds.myside.protocol import Alarm
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import myside as app
from tests.form_helpers import complete, form_fields
from tests.hold_lease_wire import virtual_clock
from tests.test_setup_routes import _typed


@pytest.mark.parametrize("product", app.PROFILES)
async def test_real_setup_explicit_product_and_side_ownership(
    hass, enable_custom_integrations, product
):
    result = await _typed(hass, "myside")
    assert result["step_id"] == "profile_questions"
    assert CONF_PROTOCOL_VARIANT in {str(m.schema) for m in form_fields(result["data_schema"])}
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.AdjustableBedConfigFlow._verification_possible",
            return_value=False,
        ),
        patch("custom_components.adjustable_bed.async_setup_entry", return_value=True),
    ):
        result = await complete(
            hass,
            result,
            {
                "profile_questions": {CONF_PROTOCOL_VARIANT: product},
                "finish_settings": {CONF_NAME: "My Side"},
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["has_massage"] is app.PROFILES[product].coaxing
    assert data["motor_count"] == 2 and data["motor_pulse_delay_ms"] == 100
    assert not reads_positions(data)
    assert resolve_profile_id(data) == f"myside:{product}"
    assert per_side_profile("myside", product).variant_owned


@pytest.fixture(autouse=True)
async def cleanup(hass):
    yield
    for target in hass.data.get("myside_test_targets", []):
        await target.async_shutdown()


async def target(hass, product="79"):
    targets = hass.data.setdefault("myside_test_targets", [])
    address = f"AA:BB:CC:67:00:{len(targets) + 1:02X}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="My Side",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "My Side",
            CONF_BED_TYPE: "myside",
            CONF_PROTOCOL_VARIANT: product,
            "motor_count": 2,
            "has_massage": app.PROFILES[product].coaxing,
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    route = codec.TRANSPORTS["w1"]
    tx = SimpleNamespace(uuid=route.write_uuid, properties=["write"], handle=1, descriptors=[])
    rx = SimpleNamespace(uuid=route.notify_uuid, properties=["notify"], handle=2, descriptors=[])
    client = SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])],
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    coord._client = client
    ctrl = await create_controller(coord, "myside", product, client)
    coord._controller = coord._offline_controller = ctrl
    ctrl.profile = replace(ctrl.profile, startup_ms=0)
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        await ctrl.start_notify()
    coord._ready = True
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coord
    targets.append(coord)
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coord.device_info
    )
    client.write_gatt_char.reset_mock()
    return coord, ctrl, client, device


def frames(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


def receive_alarm(controller, alarm, direction=2):
    link = controller._link
    controller._notification(
        link,
        link.rx,
        bytearray(
            codec.record_20_len(
                5,
                1,
                direction,
                (alarm.number, alarm.unknown, alarm.hour, alarm.minute, alarm.opcode, alarm.repeat),
            )
        ),
    )


async def invoke(hass, devices, operation, **fields):
    await hass.services.async_call(
        DOMAIN, "myside", {"device_id": devices, "operation": operation, **fields}, blocking=True
    )


async def test_registered_alarm_actions_and_native_save_entity(hass):
    coord, ctrl, client, device = await target(hass)
    services.register_services(hass)
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        await invoke(hass, [device.id], "query")
        receive_alarm(ctrl, Alarm(1, 55, 6, 30, 69, 169))
        client.write_gatt_char.reset_mock()
        await invoke(hass, [device.id], "enable", alarm_id=1, enabled=False)
        receive_alarm(ctrl, Alarm(1, 55, 6, 30, 69, 169))
        await invoke(
            hass, [device.id], "edit", alarm_id=1, hour=6, minute=30, weekdays=["0", "2", "4"]
        )
        save = next(s for s in ctrl.controller_button_specs if s.key == "myside_save_zero_gravity")
        entity = ControllerActionButton(coord, save)
        entity.async_write_ha_state = MagicMock()
        await entity.async_press()
    assert frames(client) == [
        "6e0d200501010137061e45a8eb",
        "6e0d200501010100061e45a9b5",
        "6e010066d5",
    ]


async def test_all_targets_preflight_before_any_write(hass):
    first = await target(hass)
    second = await target(hass, "76")
    services.register_services(hass)
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        await invoke(hass, [first[3].id], "query")
        receive_alarm(first[1], Alarm(1, 55, 6, 30, 69, 169))
        receive_alarm(first[1], Alarm(2, 0, 7, 0, 46, 1))
        await invoke(hass, [first[3].id], "delete", alarm_id=2)
        first[2].write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await invoke(hass, [first[3].id, second[3].id], "add")
    assert not frames(first[2]) and not frames(second[2])


async def test_stop_during_lazy_import_cancels_pending_action(hass, monkeypatch):
    coord, ctrl, client, device = await target(hass)
    services.register_services(hass)
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        await invoke(hass, [device.id], "query")
        receive_alarm(ctrl, Alarm(1, 55, 6, 30, 69, 169))
        receive_alarm(ctrl, Alarm(2, 0, 7, 0, 46, 1))
        await invoke(hass, [device.id], "delete", alarm_id=2)
    imported, proceed = asyncio.Event(), asyncio.Event()
    original = services.async_import_modules

    async def delayed(*args):
        imported.set()
        await proceed.wait()
        await original(*args)

    monkeypatch.setattr(services, "async_import_modules", delayed)
    task = asyncio.create_task(invoke(hass, [device.id], "add"))
    await imported.wait()
    await coord.async_stop_command()
    client.write_gatt_char.reset_mock()
    proceed.set()
    await task
    assert not frames(client)


async def test_real_cover_stop_owns_cleanup(hass):
    coord, ctrl, client, _ = await target(hass)
    cover = AdjustableBedCover(coord, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    started = asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == codec.command(0x24):
            started.set()

    client.write_gatt_char.side_effect = write
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        moving = asyncio.create_task(cover.async_open_cover())
        await started.wait()
        await cover.async_stop_cover()
        await asyncio.gather(moving, return_exceptions=True)
    assert frames(client)[0] == "6e01002493" and frames(client)[-1] == "6e01006edd"
    assert not coord._command_lock.locked()


async def test_paired_child_routes_and_preserves_product_gates(hass):
    left = await target(hass, "76")
    right = await target(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "myside-test"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, entry, {"left": left[0], "right": right[0]})
    hass.data[DOMAIN][entry.entry_id] = pair
    registry = dr.async_get(hass)
    registry.async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=pair.device_info
    )
    child = registry.async_get_or_create_child_from_info(
        config_entry_id=entry.entry_id, device_info=child_device_info(pair, "right")
    )
    services.register_services(hass)
    with virtual_clock() as clock, patch.object(bed, "monotonic", lambda: clock.now):
        await invoke(hass, [child.id], "query")
    assert frames(left[2]) == []
    assert frames(right[2]) == ["6e0820050100009c"]
    assert not left[1].supports_massage and right[1].supports_massage
