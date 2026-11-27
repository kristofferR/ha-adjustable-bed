"""Dynasty native alarm admission and capability entity lifetime."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import yaml
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic import dynasty
from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.dynasty import DynastyController
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.requests import Request
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.entity_sweep import EntityLedger
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from tests.hold_lease_wire import virtual_clock
from tests.test_dynasty import controller
from tests.test_dynasty import instant as instant
from tests.test_richmat_classic import packets
from tests.test_richmat_classic_transport import Services, route

REFERENCE = datetime(2026, 11, 27, 9, 59, 59, tzinfo=ZoneInfo("Europe/Oslo"))


def _alarm(**changes):
    return AlarmRequest(
        **{"enabled": True, "hour": 10, "minute": 0, "wake_action": "zero_g", "reference_time": REFERENCE}
        | changes
    )


def _notify(ctrl, frame):
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex(frame))


@pytest.fixture
async def beds(hass, monkeypatch):
    runtimes = []
    writes = []
    await services.async_register_services(hass)

    async def make(*, proof=True, layout="A9RM"):
        _, stub = controller(layout=layout)
        entry = MockConfigEntry(domain=DOMAIN, data={
            "address": f"AA:BB:CC:DD:18:{len(runtimes):02X}",
            "bed_type": "richmat_classic_apps", "protocol_variant": "dynasty",
            "product_type": layout, "connection_mode": "idle",
        })
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        client = stub.client
        client.is_connected = False
        client.services = Services([route(0)])

        async def disconnect():
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        ctrl = DynastyController(coordinator)
        coordinator._client = client
        coordinator._offline_controller = ctrl

        async def connect(**_kwargs):
            if coordinator._controller is None:
                client.is_connected = True
                coordinator._client = client
                coordinator._controller = ctrl
                coordinator._position_connection_generation += 1
                coordinator._connection_creator_task = asyncio.current_task()
                await ctrl.start_notify()
            return True

        async def write(_char, data, **_kw):
            writes.append((coordinator.address, bytes(data)))
            if data == p.ALARM_QUERY and proof:
                _notify(ctrl, "6e09010078")

        client.write_gatt_char.side_effect = write
        monkeypatch.setattr(coordinator, "async_ensure_connected", AsyncMock(side_effect=connect))
        monkeypatch.setattr(coordinator, "async_connect", AsyncMock(side_effect=connect))
        monkeypatch.setattr(coordinator, "_async_refresh_controller_auth", AsyncMock())
        runtimes.append(coordinator)
        return coordinator, ctrl, client

    monkeypatch.setattr(
        services, "_resolve_sided_targets",
        lambda *_args: ([(runtime, "both") for runtime in runtimes], []),
    )
    yield make, writes
    for runtime in runtimes:
        if runtime._client is not None:
            runtime._client.is_connected = False
        await runtime.async_shutdown()


async def _call(hass):
    await hass.services.async_call(DOMAIN, "set_alarm", {
        "device_id": "bed", "enabled": True, "time": "10:00:00", "wake_action": "zero_g",
    }, blocking=True)


async def test_native_alarm_reconnects_and_queries_current_link_before_writing(hass, beds):
    make, writes = beds
    coordinator, ctrl, client = await make()
    # A saved menu is deliberately not admission on the next BLE connection.
    ctrl.restore_persisted_app_state({"menu": ["alarm"]})
    with virtual_clock():
        await _call(hass)
    assert coordinator.async_ensure_connected.await_count >= 1
    assert [packet[1] for _, packet in writes] == [2, 8, 5, 6]
    ctrl.on_disconnect()
    client.is_connected = False
    coordinator._controller = None
    writes.clear()
    with virtual_clock():
        await _call(hass)
    assert [packet[1] for _, packet in writes] == [2, 8, 5, 6]


@pytest.mark.parametrize("side", ["both", "left"])
async def test_sequential_native_alarm_readmits_each_write_link(hass, beds, monkeypatch, side):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    make, writes = beds
    left, _, _ = await make()
    right, _, _ = await make()
    entry = MockConfigEntry(domain=DOMAIN, version=5, data={"pair_id": "dynasty-alarm"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, entry, {"left": left, "right": right}, connection_mode="sequential")
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, side)], []))
    with virtual_clock():
        await _call(hass)
    selected = [left, right] if side == "both" else [left]
    assert [address for address, data in writes if data[1] in (5, 6)] == [
        bed.address for bed in selected for _ in range(2)
    ]
    for bed in selected:
        assert sum(address == bed.address and data == p.ALARM_QUERY for address, data in writes) == 2


@pytest.mark.parametrize("second_proof", (False, True))
async def test_every_target_is_checked_before_any_native_alarm_write(hass, beds, second_proof):
    make, writes = beds
    first, _, _ = await make()
    second, _, _ = await make(proof=second_proof)
    with virtual_clock():
        if second_proof:
            await _call(hass)
        else:
            with pytest.raises(ServiceValidationError):
                await _call(hass)
    queries = [address for address, data in writes if data == p.ALARM_QUERY]
    assert queries == [first.address, second.address]
    alarm_writes = [(address, data) for address, data in writes if data[1] in (5, 6)]
    if not second_proof:
        assert alarm_writes == []
    else:
        last_query = max(i for i, (_, data) in enumerate(writes) if data == p.ALARM_QUERY)
        assert all(i > last_query for i, (_, data) in enumerate(writes) if data[1] in (5, 6))
        assert [address for address, _ in alarm_writes] == [first.address] * 2 + [second.address] * 2


async def test_native_alarm_keeps_captured_occurrence_across_queued_minute(instant, monkeypatch):
    ctrl, coord = controller(layout="A9RM")
    _notify(ctrl, "6e09010078")
    executed = REFERENCE.replace(hour=10, minute=0, second=1)
    monkeypatch.setattr("homeassistant.util.dt.now", lambda: executed)
    alarm = _alarm()
    assert alarm.minutes_until(executed) == 1
    await ctrl.configure_alarm(alarm)
    assert packets(coord) == [packet.hex() for packet in p.alarm(1, 0x45)]


async def test_plain_advertised_massage_uses_proven_both_zone_code(instant):
    ctrl, coord = controller(layout="A9RM")
    _notify(ctrl, "6e09010078")
    assert "massage" in ctrl.alarm_capability.wake_actions
    await ctrl.configure_alarm(_alarm(wake_action="massage"))
    assert bytes.fromhex(packets(coord)[-1])[3] == 0x5D


async def test_screen_declared_alarm_needs_no_capability_query(instant):
    layout = next(
        name for name, model in load_catalog("dynasty").models.items()
        if name not in dynasty.EXCLUDED_LAYOUTS and any(c.status == 7 for c in model.controls)
        and any(c.alarm_clock == "45" for c in model.controls)
    )
    ctrl, coord = controller(layout=layout)
    assert not ctrl.alarm_capability.live_check
    await ctrl.check_alarm(_alarm())
    assert packets(coord) == []
    await ctrl.configure_alarm(_alarm(enabled=False))
    assert packets(coord) == [packet.hex() for packet in p.alarm(0, 0)]


async def test_separate_family_clock_alarm_keeps_its_app_semantics(instant, monkeypatch):
    from datetime import time

    ctrl, coord = controller(layout="A9RM")
    _notify(ctrl, "6e09010078")
    monkeypatch.setattr("homeassistant.util.dt.now", lambda: REFERENCE.replace(hour=10, minute=0))
    action = next(key for key, code in ctrl._alarm_actions().items() if code == 0x45)
    await ctrl.async_execute_richmat_classic_request(Request("alarm", action=action, when=time(10)))
    assert packets(coord) == [packet.hex() for packet in p.alarm(1440, 0x45)]


async def test_native_alarm_cancellation_settles_first_frame_and_skips_second(instant):
    ctrl, coord = controller(layout="A9RM")
    _notify(ctrl, "6e09010078")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        entered.set()
        await finish.wait()

    coord.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(ctrl.configure_alarm(_alarm()))
    await entered.wait()
    task.cancel()
    await asyncio.tasks.__sleep0()
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(packets(coord)) == 1
    assert bytes.fromhex(packets(coord)[0])[1] == 5


async def test_native_alarm_second_frame_never_borrows_replacement_link(monkeypatch):
    ctrl, coord = controller(layout="A9RM")
    _notify(ctrl, "6e09010078")
    replacement, other = controller(layout="A9RM")

    async def swap(_ms, _cancel):
        ctrl._session = replacement._session
        return True

    monkeypatch.setattr(ctrl, "_wait", swap)
    with pytest.raises(ConnectionError):
        await ctrl.configure_alarm(_alarm())
    assert len(packets(coord)) == 1
    assert packets(other) == []


async def test_timeout_registry_row_survives_disconnect_without_write_permission(hass, beds):
    make, _ = beds
    coordinator, ctrl, client = await make()
    with virtual_clock():
        assert await coordinator.async_ensure_connected()
    _notify(ctrl, "6e0e00037f")
    number = AdjustableBedControllerNumber(coordinator, ctrl.controller_number_specs[0])
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "number", DOMAIN, number.unique_id, config_entry=coordinator.entry,
    )
    row = registry.async_update_entity(
        row.entity_id, new_entity_id="number.my_timeout", name="My timeout",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    ledger = EntityLedger(hass, coordinator.entry, coordinator)
    ledger.platforms_forwarded(["number"])
    ledger.platform_finished("number")
    ledger.record("number", [("number", number.unique_id)])
    ledger.async_sweep()
    assert number.available
    ctrl.on_disconnect()
    assert not number.available
    ledger.record("number", [])
    ledger.async_sweep()
    assert registry.async_get(row.entity_id) == row
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await number._spec.set_fn(ctrl, 5)
    client.write_gatt_char.assert_not_awaited()
    with virtual_clock():
        await ctrl.start_notify()
    assert not number.available
    with pytest.raises(ServiceValidationError):
        ctrl.validate_richmat_classic_request(Request("lamp_timeout", seconds=5))
    _notify(ctrl, "6e0e00017d")
    assert number.available
    rebuilt = AdjustableBedControllerNumber(coordinator, ctrl.controller_number_specs[0])
    assert rebuilt.unique_id == row.unique_id
    ledger.record("number", [("number", rebuilt.unique_id)])
    ledger.async_sweep()
    assert registry.async_get(row.entity_id) == row


def test_public_timeout_operation_has_selector_and_source_english_labels():
    root = Path(dynasty.__file__).parents[2]
    schema = yaml.safe_load((root / "services.yaml").read_text())
    options = schema["richmat_classic"]["fields"]["operation"]["selector"]["select"]["options"]
    assert "lamp_timeout" in options
    for path in (root / "strings.json", root / "translations/en.json"):
        labels = json.loads(path.read_text())["selector"]["richmat_classic_operation"]["options"]
        assert labels["lamp_timeout"] == "Light timeout"
