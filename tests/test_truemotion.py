"""trueMotion wire vectors and public runtime paths."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _build_paired_children, const
from custom_components.adjustable_bed.beds.truemotion import controller as bed
from custom_components.adjustable_bed.beds.truemotion.receive import Observations, Receiver
from custom_components.adjustable_bed.card import CARD_PRESET_SAVE
from custom_components.adjustable_bed.codec.suta import text
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow, CapabilityReport
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles import truemotion as app
from scripts.wire_snapshot import FakeClock, virtual_time
from tests.error_helpers import raises_key
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_detection import _make_service_info

VECTORS = (
    (app.PROFILES["B202"].axes[0].text("up"), b"AT+CTRL=BOTH BACK UP\r\n"),
    (app.STOP, b"AT+CTRL=BOTH STOP\r\n"),
    (app.preset("M1"), b"AT+MODE=BOTH M1\r\n"),
    (app.preset("M1", save=True), b"AT+SETMODE=BOTH M1\r\n"),
    (app.PROFILES["B603"].axes[-1].text("down"), b"AT+CTRL=BOTH T/L DOWN\r\n"),
    (app.massage("FOOT", "DT", "20"), b"AT+MASS=BOTH FOOT DT20\r\n"),
    (app.massage("HEAD", "LV", "10"), b"AT+MASS=BOTH HEAD LV10\r\n"),
    (app.light(False), b"AT+DISABLE=LIGHT\r\n"),
    (app.lock(True), b"AT+SETLOCK=ON\r\n"),
    (app.VERSION, b"AT+GETSYSTEM=VERSION\r\n"),
    (app.massage("FOOT", "DT", "00"), b"AT+MASS=BOTH FOOT DT00\r\n"),
    (app.massage("FOOT", "LV", "00"), b"AT+MASS=BOTH FOOT LV00\r\n"),
    (app.massage("HEAD", "LV", "00"), b"AT+MASS=BOTH HEAD LV00\r\n"),
)


@pytest.mark.parametrize(("command", "expected"), VECTORS)
def test_frozen_truemotion_vectors(command, expected):
    assert text(command) == expected


@pytest.mark.parametrize(
    ("name", "model", "primary"),
    [
        ("SUTA-B202D-1", "B202", "B202"),
        ("SUTA-B205B-1", "B206", "B206"),
        ("SUTA-B206C-1", "B206A", "B206A"),
        ("SUTA-B206B-1", "B206", "B206"),
        ("SUTA-B206F-1", "B206", None),
        ("SUTA-B604A-1", "B603", "B206A"),
        ("SUTA-B701-1", "B207", None),
        ("SUTA-mystery", "M510", None),
    ],
)
def test_app_layouts(name, model, primary):
    assert app.profile_for_name(name).model == model
    assert app.supports_pair_primary(name) is (primary is not None)
    if primary is not None:
        assert app.profile_for_name(name, split=True).model == primary


def test_discovery_shared_with_suta_and_never_recommends_switching_apps():
    info = _make_service_info(name="SUTA-B604A", service_uuids=[app.SERVICE_UUID])
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type == const.BED_TYPE_SUTA
    assert const.BED_TYPE_TRUEMOTION in (detected.ambiguous_types or ())
    assert "app_hint:truemotion" in detected.signals
    flow = AdjustableBedConfigFlow()
    assert flow._prepare_disambiguation(detected)
    assert flow._disambiguation_types == [const.BED_TYPE_SUTA, const.BED_TYPE_SUTA_KING_KOIL, const.BED_TYPE_TRUEMOTION]
    for bed_type in (const.BED_TYPE_SUTA, const.BED_TYPE_TRUEMOTION):
        assert recommend_profile({const.CONF_BED_TYPE: bed_type}, info, {}) is None

    for name in ("SUTA‑B604", "suta-B604", "Nearby accessory", "SUTA-DRAWER"):
        info = _make_service_info(name=name, service_uuids=[app.SERVICE_UUID])
        detected = detect_bed_type_detailed(info)
        assert const.BED_TYPE_TRUEMOTION not in (detected.ambiguous_types or ())
        assert detected.bed_type != const.BED_TYPE_TRUEMOTION


def test_notifications_distinguish_chunk_observations_and_completed_version():
    observations = Observations()
    receiver = Receiver(observations)
    assert receiver.feed(b"+OK:Ver") is None
    assert receiver.feed(b"sion=FW 1.2\r\n") == "FW 1.2"
    for packet in (
        b"+OK:GA=0108300100\r\n",
        b"+OK:GA=0208300100\r\n",
        b"+OK:GA=0208300100\r\n",
        b"+OK:GA=0308300102\r\n",
        b"+OK:GA=",
    ):
        assert receiver.feed(packet) is None
    assert observations.ga == {"08300100": {"1", "2"}}
    receiver.feed("+OK:GD=Ø😀xy".encode())
    assert observations.gd == "Ø😀"
    assert receiver.feed(b"\xff") is None
    assert observations.version == "FW 1.2"


def _entry_data(name, address):
    return {
        const.CONF_BED_TYPE: const.BED_TYPE_TRUEMOTION,
        const.CONF_BLE_DEVICE_NAME: name,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        CONF_ADDRESS: address,
    }


def _roles(client):
    tx = SimpleNamespace(
        uuid="last-write", handle=28, properties=["write", "notify"], descriptors=[]
    )
    rx = SimpleNamespace(uuid="last-notify", handle=29, properties=["notify"], descriptors=[])
    service = SimpleNamespace(
        uuid=app.SERVICE_UUID,
        characteristics=[
            SimpleNamespace(uuid="old-write", properties=["write-without-response"]),
            tx,
            rx,
            SimpleNamespace(uuid="later-indicate", properties=["indicate"]),
        ],
    )
    client.services.get_service.side_effect = lambda uuid: (
        service if uuid == app.SERVICE_UUID else None
    )
    client._backend = None
    return tx, rx


async def _setup_fake(name, *, split_primary=None):
    coordinator = _FactoryCoordinator()
    data = _entry_data(name, coordinator.address)
    coordinator.entry.data = data
    if split_primary is not None:
        primary = _entry_data(split_primary, "AA:BB:CC:DD:EE:02")
        parent = MockConfigEntry(
            data=build_pair_entry_data(primary, data, name="Dual"),
            domain=const.DOMAIN,
            title="Dual",
        )
        coordinator.entry = ChildEntryView(
            parent, effective_child_data(parent.data, "right"), lambda _: None
        )
    client = coordinator.client = MagicMock(is_connected=True)
    tx, rx = _roles(client)
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    coordinator.handle_controller_state_updates = MagicMock()
    coordinator.record_command_trace = MagicMock()
    controller = await create_controller(coordinator, const.BED_TYPE_TRUEMOTION, None, client)
    assert isinstance(controller, bed.TrueMotionController)
    coordinator.controller = controller
    await controller.start_notify()
    return coordinator, controller, tx, rx


@pytest.mark.parametrize(
    ("name", "active", "expected"),
    [
        (
            "SUTA-B202",
            (),
            [
                (100, "HEAD LV00"),
                (100, "FOOT DT00"),
                (200, "HEAD LV00"),
                (200, "FOOT DT00"),
                (300, "HEAD LV00"),
                (300, "FOOT DT00"),
            ],
        ),
        ("SUTA-B206A", ("FOOT",), [(150, "FOOT LV10")]),
        ("SUTA-B206A", ("HEAD", "FOOT"), [(0, "HEAD LV10"), (150, "FOOT LV10")]),
        ("SUTA-B603", ("FOOT",), [(100, "FOOT LV00"), (200, "FOOT LV00"), (300, "FOOT LV00")]),
        (
            "SUTA-B603",
            ("HEAD", "FOOT"),
            [
                (100, "HEAD LV00"),
                (150, "FOOT LV00"),
                (200, "HEAD LV00"),
                (250, "FOOT LV00"),
                (300, "HEAD LV00"),
                (350, "FOOT LV00"),
            ],
        ),
    ],
)
async def test_massage_schedules_follow_each_layout(name, active, expected):
    coordinator, controller, tx, rx = await _setup_fake(name)
    assert coordinator.client.start_notify.await_args.args[0] is rx
    clock = FakeClock()
    writes = []

    async def write(char, payload, *, response):
        assert char is tx
        assert response is False
        writes.append((round(clock.now * 1000), payload))

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_time(clock):
        for zone in active:
            await controller.massage_timer_next(zone)
        start = round(clock.now * 1000)
        writes.clear()
        await controller.massage_level_next()
    assert [(stamp - start, data) for stamp, data in writes] == [
        (stamp, b"AT+MASS=BOTH " + suffix.encode() + b"\r\n") for stamp, suffix in expected
    ]


async def test_split_uses_primary_editor_and_programs_two_frames_per_address():
    coordinator, controller, tx, _ = await _setup_fake(
        "SUTA-B202D-right", split_primary="SUTA-B604-left"
    )
    assert controller.profile.model == "B206A"
    assert controller.profile.split
    assert not controller.supports_preset_swing  # Swing uses the extra preset button.
    assert any(spec.key == "truemotion_swing" for spec in controller.controller_button_specs)
    with virtual_time(FakeClock()):
        await controller.program_memory(1)
    calls = coordinator.client.write_gatt_char.await_args_list
    assert [(call.args, call.kwargs) for call in calls] == [
        ((tx, b"AT+SETMODE=BOTH M1\r\n"), {"response": False}),
    ] * 2
    assert not controller.is_memory_slot_programmable(2)


async def test_link_loss_fences_old_notification_and_preserves_receive_only_maps():
    coordinator, controller, _, rx = await _setup_fake("SUTA-B207")
    client = coordinator.client
    callback = client.start_notify.await_args.args[1]
    callback(rx, bytearray(b"+OK:GA=0108300100\r\n"))
    callback(rx, bytearray(b"+OK:GD=123\r\n"))
    controller.on_disconnect()
    callback(rx, bytearray(b"+OK:GA=0208300100\r\n"))
    with raises_key("bed_not_connected"):
        await controller.move_back_up()
    client.write_gatt_char.assert_not_awaited()
    await controller.start_notify()
    assert controller._state.observations.ga == {"08300100": {"1"}}
    controller.on_connection_release("service")
    await controller.stop_notify()
    client.stop_notify.assert_awaited_once_with(rx)
    assert controller._state.observations.ga == {}
    assert controller._state.observations.gd == "123"


async def test_live_session_rejects_missing_notify_role():
    coordinator, controller, tx, _ = await _setup_fake("SUTA-B402")
    controller.on_disconnect()
    tx.properties = ["write"]
    coordinator.client.services.get_service.side_effect = None
    coordinator.client.services.get_service.return_value = SimpleNamespace(characteristics=[tx])
    with raises_key("truemotion_gatt", ServiceValidationError):
        await controller.start_notify()
    coordinator.client.write_gatt_char.assert_not_awaited()


async def test_cancellation_waiting_for_the_wire_lane_never_submits_motion():
    coordinator, controller, _, _ = await _setup_fake("SUTA-B202")
    async with controller._ble_lock:
        move = asyncio.create_task(controller.move_back_up())
        await asyncio.sleep(0)
        move.cancel()
        with pytest.raises(asyncio.CancelledError):
            await move
    coordinator.client.write_gatt_char.assert_not_awaited()


async def test_hold_cap_and_release_do_not_queue_stale_frames():
    coordinator, controller, _, _ = await _setup_fake("SUTA-B402")
    clock = FakeClock()
    with virtual_time(clock):
        await controller.hold_control("combined_up", 60000)
    payloads = [call.args[1] for call in coordinator.client.write_gatt_char.await_args_list]
    assert payloads == [b"AT+CTRL=BOTH TWO UP\r\n"] * 400 + [b"AT+CTRL=BOTH STOP\r\n"] * 3
    assert clock.now == pytest.approx(40.3)


async def test_scheduler_dedicated_stop_waits_for_release_and_owns_separate_timer_phases(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Display alias",
        data=_entry_data("SUTA-B202", "AA:BB:CC:DD:EE:28"),
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    _roles(mock_bleak_client)
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    started, finish = asyncio.Event(), asyncio.Event()
    frames = []

    async def write(_char, packet, *, response):
        assert response is False
        frames.append(packet)
        if packet == b"AT+CTRL=BOTH BACK UP\r\n":
            started.set()
            await finish.wait()

    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)
    try:
        assert await target.async_connect()
        with virtual_time(FakeClock()):
            move = asyncio.create_task(
                target.async_execute_controller_command(
                    lambda ctrl: ctrl.hold_control("back_up", 1000)
                )
            )
            await started.wait()
            stop = asyncio.create_task(target.async_stop_command())
            await asyncio.sleep(0)
            assert not stop.done()
            finish.set()
            await asyncio.gather(move, stop)
        assert frames == [
            b"AT+CTRL=BOTH BACK UP\r\n",
            *([b"AT+CTRL=BOTH STOP\r\n"] * 4),
            b"AT+MASS=BOTH HEAD DT00\r\n",
            b"AT+MASS=BOTH FOOT DT00\r\n",
            b"AT+MASS=BOTH HEAD DT00\r\n",
            b"AT+MASS=BOTH FOOT DT00\r\n",
        ]
    finally:
        await target.async_shutdown()


async def test_saved_presets_use_confirmed_buttons_not_held_recall():
    _, controller, _, _ = await _setup_fake("SUTA-B202")
    saves = [spec for spec in controller.controller_button_specs if spec.card == CARD_PRESET_SAVE]
    assert {spec.key for spec in saves} == {
        "truemotion_save_snore",
        "truemotion_save_tv",
        "truemotion_save_zerog",
    }
    assert all(spec.requires_confirmation and spec.hold is None for spec in saves)
    assert controller.standard_button_hold_spec("preset_tv") is None


async def test_setup_renders_the_missing_transport_message(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    report = CapabilityReport(
        device_found=True,
        connected=True,
        writable_count=1,
        truemotion_transport_valid=False,
    )
    assert "does not expose the trueMotion write and notification channels" in (
        await flow._format_capabilities(report)
    )


async def test_release_attempts_every_scheduled_stop_after_a_write_failure():
    coordinator, controller, _, _ = await _setup_fake("SUTA-B202")
    clock = FakeClock()
    writes = []

    async def write(_char, packet, *, response):
        assert response is False
        writes.append((round(clock.now * 1000), packet))
        if len(writes) == 2:
            raise BleakError("First STOP failed")

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_time(clock), pytest.raises(BleakError, match="First STOP failed"):
        await controller.move_back_up()
    assert writes == [
        (0, b"AT+CTRL=BOTH BACK UP\r\n"),
        *[(offset, b"AT+CTRL=BOTH STOP\r\n") for offset in (100, 200, 300)],
    ]


@pytest.mark.parametrize("left_lost", [False, True])
async def test_pair_failure_cleanup_stops_motors_without_cancelling_massage(hass, left_lost):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Dual trueMotion",
        data=build_pair_entry_data(
            _entry_data("SUTA-B202D-left", "AA:BB:CC:DD:EE:01"),
            _entry_data("SUTA-B202D-right", "AA:BB:CC:DD:EE:02"),
            name="Dual trueMotion",
        ),
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    frames = {"left": [], "right": []}
    for side, child in children.items():
        client = MagicMock(is_connected=True, disconnect=AsyncMock())
        _roles(client)
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()

        async def write(_char, packet, *, response, side=side, client=client):
            assert response is False
            frames[side].append(packet)
            if side == "left" and packet == b"AT+CTRL=BOTH BACK UP\r\n":
                if left_lost:
                    client.is_connected = False
                raise BleakError("Left motion failed")

        client.write_gatt_char = AsyncMock(side_effect=write)
        child._client = client
        child._controller = await create_controller(child, const.BED_TYPE_TRUEMOTION, None, client)
        await child._controller.start_notify()
        child._link_ready = True

    left = children["left"]
    ensure_connection = left.async_ensure_connected

    async def ensure_left(**kwargs):
        assert left.is_connected, "Paired cleanup must not reconnect the lost receiver"
        return await ensure_connection(**kwargs)

    left.async_ensure_connected = AsyncMock(side_effect=ensure_left)
    pair = PairedBedCoordinator(hass, entry, children)
    try:
        with virtual_time(FakeClock()):
            with pytest.raises(PairedSideError, match="Left motion failed"):
                await pair.async_execute_controller_command(
                    lambda ctrl: ctrl.move_back_up(),
                    resource="motor:back",
                )
            for side, writes in frames.items():
                assert (b"AT+CTRL=BOTH STOP\r\n" in writes) is (side == "right" or not left_lost)
                assert all(packet.startswith(b"AT+CTRL=") for packet in writes)
                writes.clear()

            await pair.async_stop_command(side=const.SIDE_RIGHT)
        assert frames["left"] == []
        assert frames["right"] == [
            b"AT+CTRL=BOTH STOP\r\n",
            b"AT+MASS=BOTH HEAD DT00\r\n",
            b"AT+MASS=BOTH FOOT DT00\r\n",
            b"AT+MASS=BOTH HEAD DT00\r\n",
            b"AT+MASS=BOTH FOOT DT00\r\n",
        ]
    finally:
        await pair.async_shutdown()
