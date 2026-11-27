"""Home Zone's public STOP/alarm lanes and capability-gated registry identity."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, time
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.const import Platform
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.homezone import HomeZoneController
from custom_components.adjustable_bed.beds.richmat_classic.resource_protocol import Request
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from tests.hold_lease_wire import virtual_clock
from tests.test_entity_sweep import async_setup_platforms_and_sweep
from tests.test_homezone import controller, packets


@pytest.fixture
async def runtime(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:66",
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": "homezone",
            "product_type": "BTRM",
            "ble_device_name": "BTRM-bed",
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    ctrl, double = controller("BTRM")
    ctrl._coordinator = coordinator
    coordinator._controller = ctrl
    coordinator._client = double.client
    coordinator._is_connected = True

    async def disconnected():
        double.client.is_connected = False

    double.client.disconnect = AsyncMock(side_effect=disconnected)

    async def connected(reset_timer=True):
        return True

    await services.async_register_services(hass)
    monkeypatch.setattr(coordinator, "async_ensure_connected", connected)
    monkeypatch.setattr(services, "_call_targets", lambda call: [(coordinator, "both")])
    monkeypatch.setattr(
        services, "_resolve_sided_targets", lambda *args, **kwargs: ([(coordinator, "both")], [])
    )
    yield coordinator, ctrl, double
    await coordinator.async_shutdown()


async def test_public_stop_preserves_selected_mode(hass, runtime):
    _, ctrl, double = runtime
    ctrl._select("mode", "2")
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN, "stop_all", {"device_id": ["bed"]}, blocking=True
        )
    assert packets(double) == ["6e01026edf"]


@pytest.mark.parametrize(
    "reference,execution,target,minutes",
    [
        (
            datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 8, 5, tzinfo=UTC),
            time(8, 10),
            5,
        ),
        (
            datetime(2026, 1, 2, 23, 59, tzinfo=UTC),
            datetime(2026, 1, 3, 0, 5, tzinfo=UTC),
            time(0, 10),
            5,
        ),
        (
            datetime(2026, 10, 25, 2, 50, tzinfo=ZoneInfo("Europe/Oslo"), fold=0),
            datetime(2026, 10, 25, 2, 55, tzinfo=ZoneInfo("Europe/Oslo"), fold=0),
            time(2, 10),
            15,
        ),
        (
            datetime(2026, 1, 2, 8, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 8, 11, tzinfo=UTC),
            time(8, 10),
            1,
        ),
    ],
)
async def test_public_alarm_counts_from_execution_to_selected_occurrence(
    hass, runtime, monkeypatch, reference, execution, target, minutes
):

    coordinator, _, double = runtime
    # YGRM owns a zero-gravity alarm; setup/capability admission stays native.
    data = {**coordinator.entry.data, "product_type": "YGRM"}
    hass.config_entries.async_update_entry(coordinator.entry, data=data)
    ctrl = HomeZoneController(coordinator)
    ctrl._session = runtime[1]._session
    coordinator._controller = ctrl
    clock = [reference]
    monkeypatch.setattr(services.dt_util, "now", lambda: clock[0])

    async def delayed_connection(reset_timer=True):
        clock[0] = execution
        return True

    monkeypatch.setattr(coordinator, "async_ensure_connected", delayed_connection)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {"device_id": ["bed"], "enabled": True, "time": target, "wake_action": "zero_g"},
            blocking=True,
        )
    assert packets(double) == [packet.hex() for packet in p.alarm(minutes, 0x45)]


async def test_light_timeout_registry_survives_disconnect_and_offline_reload(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
    created = await async_setup_platforms_and_sweep(
        hass, coordinator.entry, coordinator, (Platform.NUMBER,)
    )
    timer = next(entity for entity in created if isinstance(entity, AdjustableBedControllerNumber))
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "number", const.DOMAIN, timer.unique_id, config_entry=coordinator.entry
    )
    row = registry.async_update_entity(
        row.entity_id, new_entity_id="number.bedroom_timeout", name="Bedroom timeout"
    )
    with virtual_clock():
        await ctrl.execute_request(Request("lamp_timeout", seconds=60))
    assert timer.available
    original_session = ctrl._session
    ctrl.on_disconnect()
    assert timer.native_value is None
    await async_setup_platforms_and_sweep(hass, coordinator.entry, coordinator, (Platform.NUMBER,))
    assert registry.async_get(row.entity_id) == row
    assert not timer.available

    offline = HomeZoneController(coordinator)
    coordinator._controller = offline
    coordinator.cache_capability_controller()
    await async_setup_platforms_and_sweep(hass, coordinator.entry, coordinator, (Platform.NUMBER,))
    assert registry.async_get(row.entity_id) == row
    assert not timer.available
    with pytest.raises(ServiceValidationError):
        await offline.execute_request(Request("lamp_timeout", seconds=120))

    # A fresh connection alone does not authorize a retained number's writes.
    offline._session = original_session
    assert not timer.available
    with pytest.raises(ServiceValidationError):
        await offline.execute_request(Request("lamp_timeout", seconds=120))
    with pytest.raises(ServiceValidationError):
        await timer.async_set_native_value(120)
    assert packets(double) == ["6e0b003cb5"]

    offline._notification(
        offline._session, offline._session.notify, bytearray.fromhex("6e0e00037f")
    )
    restored = await async_setup_platforms_and_sweep(
        hass, coordinator.entry, coordinator, (Platform.NUMBER,)
    )
    replacement = next(
        entity for entity in restored if isinstance(entity, AdjustableBedControllerNumber)
    )
    assert replacement.unique_id == timer.unique_id
    assert replacement.available
    assert registry.async_get(row.entity_id) == row
    with virtual_clock():
        await replacement.async_set_native_value(120)
    assert packets(double) == ["6e0b003cb5", "6e0b0078f1"]


@pytest.mark.parametrize("reconnect", [False, True])
async def test_standalone_stop_captures_mode_and_originating_session(monkeypatch, reconnect):
    ctrl, double = controller("BTRM")
    ctrl._select("mode", "2")
    entered, finish = asyncio.Event(), asyncio.Event()
    original = ctrl._release

    async def delayed_release(delay_ms=0, *, mode=None):
        entered.set()
        await finish.wait()
        await original(0, mode=mode)

    monkeypatch.setattr(ctrl, "_release", delayed_release)
    task = asyncio.create_task(ctrl.stop_all())
    await entered.wait()
    ctrl._select("mode", "1")
    if reconnect:
        ctrl._session = replace(ctrl._session)
    finish.set()
    await task
    assert packets(double) == ([] if reconnect else ["6e01026edf"])


async def test_gesture_release_guard_avoids_duplicate_stop():
    from custom_components.adjustable_bed.beds.base import CONTROLLER_GESTURE_RELEASE

    ctrl, double = controller("BTRM")
    ctrl._select("mode", "2")
    token = CONTROLLER_GESTURE_RELEASE.set(True)
    try:
        await ctrl.stop_all()
    finally:
        CONTROLLER_GESTURE_RELEASE.reset(token)
    assert packets(double) == []
