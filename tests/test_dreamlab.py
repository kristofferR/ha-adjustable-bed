"""Dreamlab Control connects, stages a gesture, and cleans up its owned session."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from habluetooth import BluetoothManager
from homeassistant.components import bluetooth
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic import dreamlab as bed
from custom_components.adjustable_bed.beds.richmat_classic.discovery import matching_apps
from custom_components.adjustable_bed.beds.richmat_classic.requests import Request
from custom_components.adjustable_bed.beds.richmat_classic.transport import ROUTES, Transport
from custom_components.adjustable_bed.const import CONF_RICHMAT_CLASSIC_THIRD_SERVICE, SIDE_RIGHT
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.dreamlab import layout_from_name, scan_matches
from custom_components.adjustable_bed.setup_questions import setup_profile
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.conftest import TEST_ADDRESS
from tests.state_helpers import state_writer


def controller(layout="6BRM", wire="FRAMED"):
    coord = MagicMock()
    coord.cancel_command = asyncio.Event()
    coord.entry.data = {
        "protocol_variant": "dreamlab2",
        "product_type": layout,
        "motor_pulse_count": 2,
        "ble_device_name": layout + "-bed",
    }
    coord.client.is_connected = True
    coord.client.write_gatt_char = AsyncMock()
    coord.client.start_notify = AsyncMock()
    coord.client.stop_notify = AsyncMock()
    ctrl = bed.DreamlabController(coord, app="dreamlab2")
    coord.controller = ctrl
    ctrl._session = Transport(
        coord.client,
        SimpleNamespace(uuid="write", properties=["write"], handle=1),
        SimpleNamespace(uuid="notify", properties=["notify"], handle=2),
        wire,
    )
    ctrl._wire = wire
    return ctrl, coord


def packets(coord):
    return [call.args[1].hex() for call in coord.client.write_gatt_char.await_args_list]


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    now = [0.0]
    original = asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await original(0)

    async def wait(milliseconds, cancel):
        if cancel.is_set():
            return False
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    monkeypatch.setattr(bed.DreamlabController, "_wait", staticmethod(wait))
    return now


def test_discovery_requires_receiver_but_keeps_existing_candidates():
    assert "dreamlab2" not in matching_apps("MPE_HJ012")
    assert "dreamlab2" not in matching_apps("6BRM", ("00001800-0000-1000-8000-00805f9b34fb",))
    matches = matching_apps("MPE_HJ012", (ROUTES[0][0],))
    assert "dreamlab2" in matches and "jerome2" in matches
    assert layout_from_name("200IV2abcd") == "A8RM"
    assert layout_from_name("MPE_HJ006-1") == "BNRM"
    assert layout_from_name("COOL TOUCH") is None
    assert layout_from_name("209A05") is None
    assert not scan_matches("B6RU") and not scan_matches("ZR90")


@pytest.mark.parametrize("index", range(4))
async def test_named_route_and_startup(index):
    ctrl, coord = controller("FDRM")
    uuid, tx, rx, wire = ROUTES[index]
    send = SimpleNamespace(uuid=tx, properties=["write-without-response"], handle=1)
    notify = SimpleNamespace(uuid=rx, properties=["indicate"], handle=2)
    service = SimpleNamespace(get_characteristic={tx: send, rx: notify}.get)
    coord.client.services.get_service.side_effect = {uuid: service}.get
    await ctrl.start_notify()
    assert ctrl._session.wire == wire
    assert coord.client.start_notify.await_args.args[0] is notify
    assert packets(coord) == (["6e02010071"] if wire == "FRAMED" else []) + [
        "6e08010178",
        "6e0a000179",
        "6e1a000088",
    ]
    assert all(
        call.kwargs["response"] is False for call in coord.client.write_gatt_char.await_args_list
    )


async def test_third_service_requires_fresh_write_and_read():
    ctrl, coord = controller()
    coord.entry.data[CONF_RICHMAT_CLASSIC_THIRD_SERVICE] = True
    tx = SimpleNamespace(uuid="third-write", properties=["write"], handle=3)
    rx = SimpleNamespace(uuid="third-notify", properties=["notify"], handle=4)
    coord.client.services.get_service.return_value = None
    coord.client.services.__iter__.return_value = [
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(characteristics=[tx, rx]),
    ]
    await ctrl.start_notify()
    assert ctrl._session.write is tx and ctrl._session.notify is rx
    assert ctrl._session.wire == "RAW"
    coord.client.services.__iter__.return_value = [
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(characteristics=[rx]),
    ]
    with pytest.raises(ConnectionError, match="No complete"):
        await ctrl.start_notify()


@pytest.mark.parametrize(
    ("wire", "expected"),
    [("FRAMED", ["6e01002493"] * 2 + ["6e01006edd"]), ("RAW", ["34", "34", "6e"])],
)
async def test_held_head_and_explicit_cleanup(wire, expected, clock):
    ctrl, coord = controller(wire=wire)
    await ctrl.execute_action(1)
    assert packets(coord) == expected
    assert clock[0] == pytest.approx(0.35)
    assert ctrl.execution.hold_for("dreamlab_1") == "stream"


async def test_target_is_captured_through_release_and_fallback_rejects_sides():
    ctrl, coord = controller("F5RM")
    with ctrl.side_scope(SIDE_RIGHT):
        head_up = next(c.node for c in ctrl._controls if c.short == "24")
        await ctrl.execute_action(head_up, hold_ms=1)
    assert packets(coord) == ["6e01012494", "6e01016ede"]
    ctrl._session = replace(ctrl._session, wire="RAW")
    with ctrl.side_scope(SIDE_RIGHT), pytest.raises(ServiceValidationError):
        await ctrl.execute_action(head_up)
    assert len(packets(coord)) == 2


async def test_long_only_uses_its_route_release_and_save_is_not_held():
    ctrl, coord = controller("AORM", "RAW")
    lock = next(spec for spec in ctrl.controller_button_specs if spec.key == "dreamlab_8_long")
    await lock.press_fn(ctrl)
    assert packets(coord) == ["84"]
    assert lock.requires_confirmation and lock.hold is None
    ctrl, coord = controller("A3RM", "RAW")
    await ctrl.execute_action(10, long=True)
    assert packets(coord) == ["2b", "6e"]


async def test_cancel_at_threshold_sends_end_without_late_save(monkeypatch):
    ctrl, coord = controller("AORM")

    async def cancel_before_send(milliseconds, cancel):
        cancel.set()
        return False

    monkeypatch.setattr(ctrl, "_wait", cancel_before_send)
    await ctrl.execute_action(8, long=True)
    assert packets(coord) == ["6e01006edd"]


async def test_held_write_failure_still_attempts_end():
    ctrl, coord = controller()
    coord.client.write_gatt_char.side_effect = [OSError("failed write"), None]
    with pytest.raises(OSError, match="failed write"):
        await ctrl.execute_action(1)
    assert packets(coord) == ["6e01002493", "6e01006edd"]


async def test_selector_writes_and_gating():
    ctrl, coord = controller("YFRM")
    select = next(
        spec for spec in ctrl.controller_select_specs if spec.key == "dreamlab_press_mode"
    )
    assert not ctrl.controller_button_available("dreamlab_8")
    await select.select_fn(ctrl, "release")
    assert packets(coord) == ["6e01002190", "6e01006edd"]
    assert ctrl.controller_button_available("dreamlab_8_long")
    assert not ctrl.controller_button_available("dreamlab_10")
    await select.select_fn(ctrl, "hold")
    assert packets(coord)[-2:] == ["6e01002291", "6e01006edd"]
    assert not ctrl.controller_button_available("dreamlab_8_long")
    assert ctrl.controller_button_available("dreamlab_10")
    assert "dreamlab_8" in ctrl.held_control_options
    assert "dreamlab_10" not in ctrl.held_control_options


async def test_raw_layout_selectors_and_programming():
    ctrl, coord = controller("U3RM", "RAW")
    await ctrl.execute_action(3)
    await ctrl.execute_action(5, hold_ms=1)
    assert packets(coord) == ["59", "6e", "71", "6e"]
    ctrl, coord = controller("GVRM")
    select = next(spec for spec in ctrl.controller_select_specs if spec.key == "dreamlab_head_foot")
    await ctrl.execute_action(2, hold_ms=1)
    assert select.local_select_fn is not None
    select.local_select_fn("foot")
    assert not ctrl.controller_button_available("dreamlab_2")
    assert packets(coord) == ["6e010037a6", "6e01006edd"]
    ctrl, coord = controller("E3RM")
    await ctrl.execute_action(1, long=True)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]


async def test_direct_settings_and_fragmented_capability_recovery():
    ctrl, coord = controller("D1RM", "RAW")

    def receive(hex_data):
        ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex(hex_data))

    receive("6e09010077")  # Invalid checksum.
    assert not ctrl._receive.alarm_capable
    receive("6e09")
    receive("010078")
    assert ctrl._receive.alarm_capable
    receive("6e0701")
    receive("0177")
    assert ctrl._receive.alarm_enabled
    receive("6e0e00037f")
    receive("6e1a00028a")  # ACK, not a capability.
    with pytest.raises(ServiceValidationError):
        await ctrl.async_execute_richmat_classic_request(
            Request("aroma", aroma_values=(10, 60, 12))
        )
    receive("6e1a000189")
    light_seconds = next(
        spec for spec in ctrl.controller_number_specs if spec.key == "dreamlab_light_seconds"
    )
    await light_seconds.set_fn(ctrl, 300)
    await ctrl.set_light_color((255, 128, 1))
    await ctrl.async_execute_richmat_classic_request(Request("aroma", aroma_values=(10, 60, 12)))
    await ctrl.configure_alarm(AlarmRequest(enabled=False, reference_time=datetime.now(UTC)))
    assert packets(coord) == [
        "6e0b012ca6",
        "6e0cffff786e0d8001fc",
        "6e1b000a93",
        "6e1c003cc6",
        "6e1d000c97",
        "6e05000073",
        "6e06000074",
    ]


async def test_y6rm_uses_direct_timer_on_raw_route():
    ctrl, coord = controller("Y6RM", "RAW")
    assert ctrl.massage_timer_options == [10, 20, 30]
    assert not ctrl.massage_timer_can_turn_off
    await ctrl.set_massage_timer(20)
    assert packets(coord) == ["6e010063d2"]


async def test_cleanup_cannot_write_to_replacement_session():
    ctrl, coord = controller()
    initial_client = coord.client
    replacement_client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())

    async def change_link(_char, _packet, **_kwargs):
        coord.client = replacement_client
        ctrl._session = replace(ctrl._session, client=replacement_client)
        coord.cancel_command.set()

    initial_client.write_gatt_char.side_effect = change_link
    await ctrl.execute_action(1)
    initial_client.write_gatt_char.assert_awaited_once()
    replacement_client.write_gatt_char.assert_not_awaited()


async def test_direct_alarm_layout_does_not_depend_on_settings_reply():
    ctrl, coord = controller("BCRM")
    want = AlarmRequest(
        enabled=True,
        hour=8,
        minute=30,
        wake_action="zero_g",
        reference_time=datetime.now(UTC),
    )
    assert ctrl.alarm_capability is not None
    assert not ctrl.alarm_capability.live_check
    await ctrl.configure_alarm(want)
    assert packets(coord)[1][6:8] == "45"

    ctrl, _ = controller("FDRM")
    assert ctrl.alarm_capability is not None and ctrl.alarm_capability.live_check
    with pytest.raises(ServiceValidationError):
        await ctrl.check_alarm(want)


@pytest.mark.parametrize(
    ("layout", "key", "choice", "node", "expected"),
    [
        ("F5RM", "dreamlab_mode", "right", 7, ["6e01012494", "6e01016ede"]),
        ("U3RM", "dreamlab_axis", "5", 5, ["6e010071e0", "6e01006edd"]),
        ("GVRM", "dreamlab_head_foot", "foot", 2, []),
    ],
)
async def test_recreated_controller_keeps_local_selector(layout, key, choice, node, expected):
    original, _ = controller(layout)
    select = next(spec for spec in original.controller_select_specs if spec.key == key)
    assert select.local_select_fn is not None
    select.local_select_fn(choice)
    original.on_disconnect()
    restored, coord = controller(layout)
    restored.restore_persisted_app_state(original.persisted_app_state)
    if expected:
        await restored.execute_action(node, hold_ms=1)
    else:
        with pytest.raises(ServiceValidationError):
            await restored.execute_action(node, hold_ms=1)
    assert packets(coord) == expected


async def test_disconnect_keeps_reported_light_power_but_requires_fresh_feedback():
    ctrl, coord = controller("D1RM")
    state = {}
    coord.handle_controller_state_updates.side_effect = state_writer(state)
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
    ctrl.on_disconnect()
    assert state[UNDER_BED_LIGHTS_ON] is True
    with pytest.raises(ServiceValidationError):
        await ctrl.lights_off()
    assert packets(coord) == []


@pytest.mark.parametrize(
    ("local_name", "packet_name", "name_used", "expected"),
    [
        ("MLRM-bed", None, "MLRM-bed", 110),
        (None, None, "6BRM-bed", 170),
        (None, "TWRM-bed", "TWRM-bed", 110),
    ],
)
@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_refresh_uses_advertised_then_saved_name_ignoring_alias(
    hass,
    monkeypatch,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    local_name,
    packet_name,
    name_used,
    expected,
):
    entry = MockConfigEntry(
        domain="adjustable_bed",
        data={
            "address": TEST_ADDRESS,
            "name": "Bedroom",
            "bed_type": "richmat_classic_apps",
            "protocol_variant": "dreamlab2",
            "product_type": "6BRM",
            "ble_device_name": "6BRM-bed",
        },
    )
    entry.add_to_hass(hass)
    service_uuid, tx, rx, _ = ROUTES[2]
    send = SimpleNamespace(uuid=tx, properties=["write"], handle=1)
    notify = SimpleNamespace(uuid=rx, properties=["notify"], handle=2)
    service = SimpleNamespace(get_characteristic={tx: send, rx: notify}.get)
    mock_bleak_client.services.get_service.side_effect = {service_uuid: service}.get
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()

    device = BLEDevice(TEST_ADDRESS, "MLRM display alias", {"source": "local"})
    mock_async_ble_device_from_address.return_value = device
    manager = BluetoothManager()
    if local_name is None:
        # The manager caches the device name from an earlier BlueZ scan.
        previous = AdvertisementData(None, {}, {}, [service_uuid], 0, -41, ("scanner",))
        manager.scanner_adv_received(
            bluetooth.BluetoothServiceInfoBleak.from_scan("local", device, previous, 0, True)
        )

    advertisement = AdvertisementData(local_name, {}, {}, [service_uuid], 0, -40, ("scanner",))
    scanner_device = BLEDevice(TEST_ADDRESS, None, {"source": "local"})
    info = bluetooth.BluetoothServiceInfoBleak.from_scan(
        "local", scanner_device, advertisement, 1, True
    )
    if packet_name is not None:
        name_bytes = packet_name.encode()
        info.raw = bytes((len(name_bytes) + 1, 0x09)) + name_bytes
    manager.scanner_adv_received(info)
    cached = manager.async_last_service_info(TEST_ADDRESS, True)
    assert cached is info
    if local_name is None:
        assert cached.advertisement.local_name == "MLRM display alias"
        assert not cached.advertisement.platform_data

    profile = setup_profile("richmat_classic_apps")
    assert profile is not None and profile.seed is not None
    seeded = profile.seed(hass, entry.data, cached)
    assert seeded["ble_device_name"] == name_used
    monkeypatch.setattr(
        bluetooth,
        "async_last_service_info",
        lambda _hass, address, *, connectable: (
            manager.async_last_service_info(address, connectable)
            if connectable or local_name is None
            else None
        ),
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    try:
        assert await coordinator.async_connect()
        ctrl = coordinator.controller
        assert isinstance(ctrl, bed.DreamlabController)
        assert ctrl._worker.tick_ms == expected
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(("layout", "off"), [("D1RM", "6e01005ecd"), ("D9RM", "6e01008bfa")])
async def test_massage_slider_is_the_shared_timer_with_the_apps_four_stops(layout, off):
    """The slider snaps to four stops the app labels 0, 2H, 3H and 5H."""
    ctrl, coord = controller(layout)
    assert ctrl.supports_massage_timer and ctrl.auto_enable_massage
    assert ctrl.massage_timer_options == [120, 180, 300] and ctrl.massage_timer_can_turn_off
    assert not any("massage" in spec.key for spec in ctrl.controller_number_specs)
    for minutes in (0, 120, 180, 300):
        await ctrl.set_massage_timer(minutes)
    assert packets(coord) == [off, "6e01005fce", "6e010063d2", "6e010061d0"]
