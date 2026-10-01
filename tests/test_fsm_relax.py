"""FSM Relax source vectors, exact app tables and safe session ownership."""

from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.fsm_relax import (
    FsmRelaxController,
    FsmRelaxProfile,
    build_packet,
    decode_packet,
    signed_version,
)
from custom_components.adjustable_bed.fsm_relax_state import FsmRelaxState


async def test_actual_coordinator_drop_immediately_invalidates_owned_session(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import BED_TYPE_FSM_RELAX, CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FSM_RELAX},
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    ctrl = make_controller()
    client = ctrl.client
    ctrl._coordinator = coordinator
    coordinator._controller = ctrl
    coordinator._client = client
    coordinator._auto_reconnect_enabled = MagicMock(return_value=False)
    ctrl._subscribed = True
    ctrl._buffer.extend(b"partial")
    pending = asyncio.get_running_loop().create_future()
    ctrl._pending[0] = pending
    optional = asyncio.create_task(asyncio.sleep(100))
    metadata = asyncio.create_task(asyncio.sleep(100))
    ctrl._optional_task = optional
    ctrl._metadata_tasks.add(metadata)
    generation = ctrl._generation
    client.is_connected = False
    coordinator._on_disconnect(client)
    assert coordinator.controller is None and coordinator.client is None
    assert ctrl._generation == generation + 1
    assert not ctrl._subscribed and not ctrl._live_capabilities
    assert not ctrl._buffer and not ctrl._pending and pending.cancelled()
    assert optional.cancelling() and metadata.cancelling()
    await asyncio.gather(optional, metadata, return_exceptions=True)


async def test_initializing_disconnect_cancels_query_and_rejects_same_client_old_callback(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import BED_TYPE_FSM_RELAX, CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_FSM_RELAX},
    )
    coordinator = AdjustableBedCoordinator(hass, entry)
    ctrl = make_controller()
    client = ctrl.client
    ctrl._coordinator = coordinator
    coordinator._client = client
    coordinator._controller = ctrl
    coordinator._connecting = True
    disconnect_callback = coordinator._on_disconnect
    await ctrl.start_notify()
    old_notify = client.start_notify.call_args.args[1]
    query = asyncio.create_task(ctrl._query(2))
    while not client.write_gatt_char.await_count:
        await asyncio.sleep(0)
    generation = ctrl._generation
    try:
        client.is_connected = False
        disconnect_callback(client)
        assert coordinator.client is client and coordinator.controller is ctrl
        assert ctrl._generation == generation + 1
        assert not ctrl._live_capabilities and not ctrl._subscribed
        with pytest.raises(asyncio.CancelledError):
            await query
        assert not ctrl._pending
        client.is_connected = True
        await ctrl.start_notify()
        packet = bytearray(build_packet(bytes.fromhex("0204000004"), 9))
        old_notify(None, packet)
        assert not ctrl._live_capabilities
        client.start_notify.call_args.args[1](None, packet)
        assert ctrl._live_capabilities and ctrl.key_count == 4 and ctrl.memory_slot_count == 4
        assert client.write_gatt_char.await_count == 1
    finally:
        query.cancel()
        await asyncio.gather(query, return_exceptions=True)
        await ctrl.stop_notify()


def make_controller(profile=None, *, cap=b"\x02\x08\x04\x00\x08"):
    c = MagicMock()
    c.address = "AA:BB:CC:DD:EE:FF"
    c.motor_pulse_count = 2
    c._cancel_command = asyncio.Event()
    c.cancel_command = c._cancel_command
    c._command_lock = asyncio.Lock()
    c.entry.async_create_background_task.side_effect = lambda _hass, coroutine, _name: (
        asyncio.create_task(coroutine)
    )
    c.client = MagicMock(
        is_connected=True,
        services=[
            SimpleNamespace(
                uuid="0000ffe0-0000-1000-8000-00805f9b34fb",
                characteristics=[
                    SimpleNamespace(
                        uuid="0000ffe1-0000-1000-8000-00805f9b34fb", properties=["write"], handle=1
                    )
                ],
            )
        ],
    )
    c.client.write_gatt_char = AsyncMock()
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    state = FsmRelaxState(c.hass, "entry", c.address)
    state._store = MagicMock(
        async_load=AsyncMock(return_value=None), async_save=AsyncMock(), async_remove=AsyncMock()
    )
    ctrl = FsmRelaxController(c, profile=profile, state=state)
    c.controller = ctrl
    if cap is not None:
        ctrl._accept_body(cap)
        ctrl._live_capabilities = True
    return ctrl


def bodies(ctrl):
    return [decode_packet(call.args[1]) for call in ctrl.client.write_gatt_char.call_args_list]


def feed(ctrl, body):
    ctrl._receive(build_packet(body, 99))


SOURCE_VECTORS = [
    ("V001", "0000000003", 0, "dd9afc185029d7131907"),
    ("V002", "0100000003", 1, "dd8fe3b94f8267bd9895"),
    ("V003", "0200000003", 2, "ddb4b0bf6c3e4f750270"),
    ("V004", "0300000000", 3, "ddf3b6e1dd55b83ffe8e"),
    ("V005", "0500000000", 4, "dd054d35081d1f1310cb"),
    ("V006", "1000000000", 5, "dd9acfa5bb77b9189785"),
    ("V007", "1100000000", 6, "dd7d1ea96bfe1e275322"),
    ("V008", "1200000000", 7, "dd5f7afa96da2202c70b"),
    ("V009", "1300000000", 8, "dd08e317af00410807de"),
    ("V010", "2000000000", 9, "ddfe65e204f46c83c7d0"),
    ("V011", "2100000000", 10, "dd46f4b0d2d2da5a38d7"),
    ("V012", "2200000000", 11, "ddc268d63c94d8fc4dce"),
    ("V013", "2300000000", 12, "ddbcd100113a44dd6036"),
    ("V014", "3000000000", 13, "dd9052aec9efa366acda"),
    ("V015", "3100000000", 14, "dd8a21c1d716c6fe4c46"),
    ("V016", "3200000000", 15, "dd6ab825caf0704954eb"),
    ("V017", "3300000000", 16, "ddbad370866fe3af1677"),
    ("V018", "4000000000", 17, "ddc28e105a42f4a9d046"),
    ("V019", "4100000000", 18, "dd56ec8d5ee6a02526db"),
    ("V020", "5000000000", 19, "ddd602866c85bcfad8ba"),
    ("V021", "5100000000", 20, "dd49b34d0bae1237577f"),
    ("V022", "5200000000", 21, "dd4955d98402d886ade5"),
    ("V023", "5300000000", 22, "dd46becf690d06f084a0"),
    ("V024", "5400000000", 23, "dd17acab69e22d75f72f"),
    ("V025", "5500000000", 24, "ddfa3949a4df6a07f03d"),
    ("V026", "6000000000", 25, "dd557e9121960dbaf8b7"),
    ("V027", "6100000000", 26, "dda0f3141997af550a42"),
    ("V028", "6200000000", 27, "dd114762ef8766a3e5fb"),
    ("V029", "6300000000", 28, "dd4b472be983c164204b"),
    ("V030", "6400000000", 29, "dd6c354ba8c8f7d21a1c"),
    ("V031", "6500000000", 30, "dd96ba2b023fc6e980c8"),
    ("V032", "7000000000", 31, "dd3ccf3c621311c30d7a"),
    ("V033", "ff00000000", 32, "dd1ccd6b601a4af101e7"),
    ("V034", "1112345678", 255, "dd5f581ba20c1bd0367e"),
    ("V035", "1180000000", 255, "ddbaef6db9f57d839839"),
    ("V036", "2112345678", 255, "ddf71f768d0f40ab0afa"),
    ("V037", "2180000000", 255, "ddf34c8a695ea2f0faf9"),
    ("V038", "3112345678", 255, "dda612d7666869cf9709"),
    ("V039", "3180000000", 255, "ddec4d7b42d73b039179"),
    ("V040", "4112345678", 255, "dda582e2dc33e6ef9963"),
    ("V041", "4180000000", 255, "dd5121fe549d282c30c2"),
    ("V042", "1201010000", 256, "dd4ee817eaf4b3fe742d"),
    ("V043", "0000000000", 105, "ddd38905b3757e79d431"),
]

SOURCE_TABLES = [
    ("chair", 2, 0, (80, 81)),
    ("chair", 4, 0, (34, 35, 18, 19, 80, 81)),
    ("chair", 6, 0, (34, 35, 18, 19, 80, 81)),
    ("chair", 8, 0, (34, 35, 18, 19, 80, 81)),
    ("bed", 2, 0, (18, 19)),
    ("bed", 2, 1, (18, 19, 112)),
    ("bed", 2, 2, (18, 19, 96, 97, 98, 99)),
    ("bed", 2, 3, (18, 19, 100, 101, 112)),
    ("bed", 4, 0, (18, 19, 34, 35, 80, 81)),
    ("bed", 4, 1, (18, 19, 34, 35, 112, 81)),
    ("bed", 4, 2, (18, 19, 34, 35, 96, 97, 98, 99)),
    ("bed", 4, 3, (18, 19, 34, 35, 112, 81, 100, 101)),
    ("bed", 6, 0, (18, 19, 34, 35, 50, 51, 84, 85)),
    ("bed", 6, 1, (18, 19, 34, 35, 50, 51, 112, 84)),
    ("bed", 6, 2, (18, 19, 96, 34, 35, 97, 50, 51, 98, 84, 85, 99)),
    ("bed", 6, 3, (18, 19, 100, 34, 35, 101, 50, 51, 112, 84, 85)),
    ("bed", 8, 0, (18, 19, 34, 35, 80, 81, 82, 83)),
    ("bed", 8, 1, (18, 19, 112, 34, 35, 80, 81, 82, 83)),
    ("bed", 8, 2, (18, 19, 96, 34, 35, 97, 80, 81, 98, 82, 83, 99)),
    ("bed", 8, 3, (18, 19, 100, 34, 35, 101, 80, 81, 112, 82, 83)),
]


@pytest.mark.parametrize("identity,body,counter,expected", SOURCE_VECTORS)
def test_source_codec_vectors(identity, body, counter, expected):
    from custom_components.adjustable_bed.beds.limoss import LimossController

    packet = bytes.fromhex(expected)
    logical = bytes.fromhex(body)
    assert build_packet(logical, counter) == packet, identity
    assert decode_packet(packet) == logical
    legacy = object.__new__(LimossController)
    legacy._counter = counter & 255
    assert legacy._build_packet(*logical) == packet
    assert legacy._decode_packet(packet) == (logical[0], logical[1:])


@pytest.mark.parametrize("layout,key,flags,expected", SOURCE_TABLES)
def test_exact_source_tables(layout, key, flags, expected):
    ctrl = make_controller(
        FsmRelaxProfile(layout, bool(flags & 1), bool(flags & 2)), cap=bytes((2, key, 255, 0, 8))
    )
    assert ctrl.action_opcodes == expected
    assert len(ctrl.controller_button_specs) == len(expected)
    assert ctrl.motor_control_specs == ()
    assert not ctrl.supports_massage and not ctrl.supports_lights


@pytest.mark.parametrize("key", range(256))
def test_capability_byte_all_values(key):
    ctrl = make_controller(cap=bytes((2, key, 231, 0xFF, 0xFF)))
    assert ctrl.key_count == (key if key in (2, 4, 6, 8) else 8)
    assert ctrl.memory_slot_count == 8
    assert ctrl._state["fsm_relax_reported_memory_count"] == 65535
    assert ctrl._state["fsm_relax_vibration_count"] == 231


@pytest.mark.parametrize("count,usable", [(count, min(count, 8)) for count in (*range(10), 65535)])
def test_memory_count_boundaries(count, usable):
    ctrl = make_controller(cap=b"\x02\x04\xff" + count.to_bytes(2, "big"))
    assert ctrl.memory_slot_count == usable


@pytest.mark.parametrize("slot", range(1, 9))
@pytest.mark.parametrize("count", (*range(10), 65535))
def test_every_local_slot_is_gated_by_reported_count(slot, count):
    ctrl = make_controller(cap=b"\x02\x04\xff" + count.to_bytes(2, "big"))
    ctrl._subscribed = True
    if slot <= min(count, 8):
        ctrl._validate_memory(slot)
    else:
        with pytest.raises(ValueError):
            ctrl._validate_memory(slot)


@pytest.mark.parametrize("opcode", (0x10, 0x20, 0x30, 0x40))
@pytest.mark.parametrize("raw", (-(2**31), -1, 0, 2**31 - 1))
def test_signed_opaque_positions(opcode, raw):
    ctrl = make_controller()
    feed(ctrl, bytes((opcode,)) + raw.to_bytes(4, "big", signed=True))
    assert ctrl._state[f"fsm_relax_motor_{opcode // 16}_raw"] == raw
    assert ctrl.position_number_specs == ()
    assert not ctrl.supports_position_feedback


async def test_exact_signed_versions_ack_serial_and_unknown():
    assert signed_version(bytes.fromhex("018002ff")) == "1-128.2"
    assert signed_version(bytes.fromhex("ffffffff")) == "-1."
    ctrl = make_controller()
    for opcode in (0, 1):
        feed(ctrl, bytes((opcode,)) + bytes.fromhex("018002ff"))
    assert ctrl._state["fsm_relax_hardware_version"] == "1-128.2"
    for opcode in (4, 4, 5, 5, 6, 0x99):
        feed(ctrl, bytes((opcode,)) + bytes.fromhex("ffffffff"))
    assert ctrl._state["fsm_relax_serial"] == -1
    assert ctrl._state["fsm_relax_calibration_observed"] is True
    assert "not correlated" in ctrl._state["fsm_relax_acknowledgement"]
    assert ctrl.local.slots == {}
    await asyncio.gather(*ctrl._metadata_tasks)
    assert ctrl.local.serial == -1


def test_fragment_coalesced_noise_and_checksum_validation():
    ctrl = make_controller()
    a = build_packet(bytes.fromhex("10ffffffff"), 1)
    b = build_packet(bytes.fromhex("2000000002"), 2)
    ctrl._receive(b"noise" + a[:3])
    assert "fsm_relax_motor_1_raw" not in ctrl._state
    ctrl._receive(a[3:] + b)
    assert ctrl._state["fsm_relax_motor_1_raw"] == -1
    assert ctrl._state["fsm_relax_motor_2_raw"] == 2
    before = ctrl._state.copy()
    for index in range(10):
        corrupted = bytearray(a)
        corrupted[index] ^= 1
        ctrl._receive(bytes(corrupted))
    assert ctrl._state == before
    ctrl._receive(b"\xdd" * 2000)
    assert len(ctrl._buffer) < 10


@pytest.mark.parametrize("bad", (None, "chairish", 1))
def test_profile_validation(bad):
    with pytest.raises(ValueError):
        FsmRelaxProfile(bad)
    with pytest.raises(ValueError):
        FsmRelaxProfile(reversals=(False, False, False, 0))


@pytest.mark.parametrize("reversals", list(itertools.product((False, True), repeat=4)))
async def test_no_response_fresh_counter_and_reversal_frames(reversals):
    ctrl = make_controller(FsmRelaxProfile("bed", reversals=reversals))
    ctrl._counter = 255
    await ctrl.write_command(bytes((0x12,)) + bytes(reversals), repeat_count=2, repeat_delay_ms=0)
    calls = ctrl.client.write_gatt_char.call_args_list
    assert all(call.kwargs == {"response": False} for call in calls)
    assert calls[0].args[1] == build_packet(bytes((0x12,)) + bytes(reversals), 255)
    assert calls[1].args[1] == build_packet(bytes((0x12,)) + bytes(reversals), 0)


@pytest.mark.parametrize("mutation", ("missing_service", "wrong_char", "duplicate"))
async def test_exact_role_negative_cases(mutation):
    ctrl = make_controller()
    services = ctrl.client.services
    if mutation == "missing_service":
        services[0].uuid = "wrong"
    elif mutation == "wrong_char":
        services[0].characteristics[0].uuid = "wrong"
    else:
        services[0].characteristics *= 2
    with pytest.raises(ValueError):
        await ctrl.start_notify()
    ctrl.client.write_gatt_char.assert_not_called()


async def test_property_absence_and_actual_transport_error():
    ctrl = make_controller()
    ctrl.client.services[0].characteristics[0].properties = []
    await ctrl.start_notify()
    ctrl.client.write_gatt_char.side_effect = BleakError("actual transport failure")
    with pytest.raises(BleakError, match="actual"):
        await ctrl.write_command(bytes.fromhex("0200000003"))
    assert ctrl.client.write_gatt_char.await_count == 1
    assert ctrl.client.write_gatt_char.call_args.kwargs["response"] is False


async def test_controls_ready_before_optional_info_and_query_bodies():
    ctrl = make_controller(cap=None)

    def respond(_role, packet, **_kwargs):
        body = decode_packet(packet)
        if body[0] == 2:
            feed(ctrl, bytes.fromhex("0202040008"))

    ctrl.client.write_gatt_char.side_effect = respond
    await ctrl.async_discover_capabilities()
    assert ctrl.action_opcodes == (0x50, 0x51)
    assert bodies(ctrl)[0] == bytes.fromhex("0200000003")
    assert ctrl._optional_task is not None and not ctrl._optional_task.done()
    await ctrl.stop_notify()


@pytest.mark.parametrize("failure", (TimeoutError(), BleakError("optional BLE failure")))
async def test_optional_wait_outside_command_lock_timeout_preserves_caps(failure):
    ctrl = make_controller()
    await ctrl.start_notify()
    with patch.object(ctrl, "_query", AsyncMock(side_effect=failure)):
        await ctrl._optional_information()
    assert ctrl.memory_slot_count == 8
    assert "remain usable" in ctrl._state["fsm_relax_optional_information"]
    task = asyncio.create_task(ctrl._query(0, optional=True))
    await asyncio.sleep(0.01)
    assert not ctrl._coordinator._command_lock.locked()
    assert bodies(ctrl)[0] == bytes.fromhex("0000000003")
    feed(ctrl, bytes.fromhex("00018002ff"))
    await task
    await ctrl.stop_notify()


async def test_old_generation_and_disconnected_callbacks_ignored():
    ctrl = make_controller()
    await ctrl.start_notify()
    callback = ctrl.client.start_notify.call_args.args[1]
    await ctrl.stop_notify()
    await ctrl.start_notify()
    callback(None, bytearray(build_packet(bytes.fromhex("10ffffffff"), 1)))
    assert "fsm_relax_motor_1_raw" not in ctrl._state
    callback = ctrl.client.start_notify.call_args.args[1]
    ctrl.client.is_connected = False
    callback(None, bytearray(build_packet(bytes.fromhex("10ffffffff"), 1)))
    assert "fsm_relax_motor_1_raw" not in ctrl._state


async def test_hold_timing_and_five_release_attempts_despite_failure():
    ctrl = make_controller(FsmRelaxProfile("bed"))
    loop = asyncio.get_running_loop()
    started = loop.time()
    times = []

    def write(_role, packet, **_kwargs):
        times.append((loop.time() - started, decode_packet(packet)[0]))
        if len(times) == 3:
            raise BleakError("first cleanup failure")

    ctrl.client.write_gatt_char.side_effect = write
    with pytest.raises(BleakError):
        await ctrl.hold_control("command_12", 120)
    assert [op for _, op in times] == [0x12, 0x12] + [0xFF] * 5
    assert times[0][0] >= 0.055
    assert 0.05 <= times[1][0] - times[0][0] <= 0.085


async def test_cancel_before_first_write_repeated_cancellation_cleanup():
    ctrl = make_controller(FsmRelaxProfile("bed"))
    ctrl._coordinator._cancel_command.set()
    task = asyncio.create_task(ctrl.hold_control("command_12", 120))
    await asyncio.sleep(0.075)
    task.cancel()
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bodies(ctrl) == [bytes.fromhex("ff00000000")] * 5


async def test_cleanup_deadlines_with_slow_first_write():
    ctrl = make_controller()
    loop = asyncio.get_running_loop()
    start = loop.time()
    times = []

    async def write(*_args, **_kwargs):
        times.append(loop.time() - start)
        if len(times) == 1:
            await asyncio.sleep(0.04)

    ctrl.client.write_gatt_char.side_effect = write
    await ctrl.stop_all()
    assert 0.055 <= times[0] <= 0.09
    assert 0.105 <= times[1] <= 0.155
    assert 0.285 <= times[-1] <= 0.345


@pytest.mark.parametrize("key", (2, 4, 6, 8))
async def test_sequential_new_query_atomic_signed_save(key):
    ctrl = make_controller(cap=bytes((2, key, 0, 0, 8)))
    await ctrl.start_notify()
    ctrl._live_capabilities = True

    def respond(_role, packet, **_kwargs):
        opcode = decode_packet(packet)[0]
        feed(ctrl, bytes((opcode,)) + (-opcode).to_bytes(4, "big", signed=True))

    ctrl.client.write_gatt_char.side_effect = respond
    await ctrl.program_memory(8)
    assert bodies(ctrl) == [bytes(((i + 1) * 16, 0, 0, 0, 0)) for i in range(key // 2)]
    assert ctrl.local.slots[8] == {i: -(i + 1) * 16 for i in range(key // 2)}
    assert ctrl.local._store.async_save.await_count == 1


async def test_timeout_cancel_quarantine_and_same_opcode_ambiguity():
    ctrl = make_controller(cap=bytes.fromhex("0202000008"))
    await ctrl.start_notify()
    ctrl._live_capabilities = True
    ctrl.local.slots[1] = {0: 123}
    with (
        patch.object(ctrl, "_query", AsyncMock(side_effect=TimeoutError)),
        pytest.raises(TimeoutError),
    ):
        await ctrl.program_memory(1)
    assert ctrl.local.slots[1] == {0: 123}
    with pytest.raises(RuntimeError, match="quarantined"):
        await ctrl.program_memory(1)
    await ctrl.stop_notify()
    await ctrl.start_notify()
    ctrl._live_capabilities = True
    with pytest.raises(RuntimeError, match="quarantined"):
        await ctrl.program_memory(2)
    await ctrl.stop_notify()
    # A fresh client/subscription is required, merely resubscribing is insufficient.
    old_client = ctrl._coordinator.client
    ctrl._coordinator.client = MagicMock(is_connected=True, services=old_client.services)
    ctrl.client.start_notify = AsyncMock()
    ctrl.client.write_gatt_char = AsyncMock()
    await ctrl.start_notify()
    ctrl._live_capabilities = True

    # A delayed device-retained reply after reconnect is indistinguishable.
    def delayed(_role, _packet, **_kwargs):
        feed(ctrl, bytes.fromhex("100000007b"))

    ctrl.client.write_gatt_char.side_effect = delayed
    await ctrl.program_memory(2)
    assert ctrl.local.slots[2] == {0: 123}
    assert "indistinguishable" in ctrl.protocol_diagnostics["reply_freshness"]
    ctrl.client.write_gatt_char.side_effect = None
    task = asyncio.create_task(ctrl.program_memory(3))
    await asyncio.sleep(0.01)
    ctrl._coordinator._cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert 3 not in ctrl.local.slots and ctrl._quarantined


async def test_unsolicited_wrong_order_and_transport_failure_no_slot_mutation():
    ctrl = make_controller()
    await ctrl.start_notify()
    ctrl._live_capabilities = True
    feed(ctrl, bytes.fromhex("10ffffffff"))
    assert ctrl.local.slots == {}

    def wrong(_role, packet, **_kwargs):
        feed(ctrl, bytes.fromhex("20ffffffff"))
        raise BleakError("uncertain write")

    ctrl.client.write_gatt_char.side_effect = wrong
    with pytest.raises(BleakError):
        await ctrl.program_memory(1)
    assert ctrl.local.slots == {} and ctrl._quarantined


async def test_sparse_recall_normal_queue_and_cancel_preempts_targets():
    ctrl = make_controller()
    await ctrl.start_notify()
    ctrl._live_capabilities = True
    ctrl.local.slots[8] = {0: -1, 2: -(2**31)}
    await ctrl.recall_memory(8, hold_ms=1)
    assert (
        bodies(ctrl)
        == [bytes.fromhex("11ffffffff"), bytes.fromhex("3180000000")]
        + [bytes.fromhex("0300000000")] * 5
    )
    ctrl.client.write_gatt_char.reset_mock()

    def cancel(_role, _packet, **_kwargs):
        ctrl._coordinator._cancel_command.set()

    ctrl.client.write_gatt_char.side_effect = cancel
    await ctrl.recall_memory(8, hold_ms=1000)
    assert bodies(ctrl) == [bytes.fromhex("11ffffffff")] + [bytes.fromhex("0300000000")] * 5
    assert ctrl._quarantined


@pytest.mark.parametrize("slot", (0, 9, True, -1))
async def test_memory_invalid_slots_and_missing_motor_zero(slot):
    ctrl = make_controller()
    await ctrl.start_notify()
    ctrl._live_capabilities = True
    with pytest.raises(ValueError):
        await ctrl.recall_memory(slot, hold_ms=120)
    ctrl.local.slots[1] = {1: 4}
    with pytest.raises(ValueError, match="motor-zero"):
        await ctrl.recall_memory(1, hold_ms=120)
    ctrl.client.write_gatt_char.assert_not_called()


async def test_calibration_confirmation_single_attempt_and_current_callback():
    ctrl = make_controller(FsmRelaxProfile("bed", reversals=(True, False, True, False)))
    ctrl._live_capabilities = True
    with pytest.raises(ValueError):
        await ctrl.calibrate(confirmed=False)
    ctrl.client.write_gatt_char.assert_not_called()
    ctrl.client.write_gatt_char.side_effect = BleakError("uncertain")
    with pytest.raises(BleakError):
        await ctrl.calibrate(confirmed=True)
    assert bodies(ctrl) == [bytes.fromhex("0501000100")]
    spec = ctrl.controller_button_specs[0]
    other = make_controller(FsmRelaxProfile("bed"))
    other.hold_control = AsyncMock()
    await spec.press_fn(other)
    other.hold_control.assert_awaited_once_with("command_12", 120)


def test_negative_capabilities_no_unproven_routes():
    ctrl = make_controller(FsmRelaxProfile("bed", True, True))
    for key in (
        "supports_preset_flat",
        "supports_position_feedback",
        "supports_lights",
        "supports_massage",
        "supports_clock_alarm",
        "supports_clock_sync",
        "supports_child_lock",
        "supports_factory_reset",
        "supports_device_rename",
        "supports_simultaneous_movement",
        "supports_direct_position_control",
    ):
        assert getattr(ctrl, key) is False, key
    assert 0x42 not in ctrl.action_opcodes and 0x43 not in ctrl.action_opcodes
    assert ctrl._counter == 0


async def test_scoped_cancel_event_overrides_legacy_global_event():
    ctrl = make_controller()
    ctrl._coordinator._cancel_command.set()
    ctrl._coordinator.cancel_command = asyncio.Event()
    await ctrl.write_command(bytes.fromhex("0200000003"))
    assert len(bodies(ctrl)) == 1
    ctrl._coordinator.cancel_command.set()
    await ctrl.write_command(bytes.fromhex("0200000003"))
    assert len(bodies(ctrl)) == 1


@pytest.mark.parametrize(
    "opcode",
    (
        0x12,
        0x13,
        0x22,
        0x23,
        0x32,
        0x33,
        0x50,
        0x51,
        0x52,
        0x53,
        0x54,
        0x55,
        0x60,
        0x61,
        0x62,
        0x63,
        0x64,
        0x65,
        0x70,
    ),
)
async def test_every_reachable_held_opcode_execution_and_release(opcode):
    layout, key, flags, _expected = next(row for row in SOURCE_TABLES if opcode in row[3])
    ctrl = make_controller(
        FsmRelaxProfile(layout, bool(flags & 1), bool(flags & 2), (True, False, True, False)),
        cap=bytes((2, key, 0, 0, 8)),
    )
    await ctrl.hold_control(f"command_{opcode:02x}", 60)
    assert bodies(ctrl) == [bytes((opcode, 1, 0, 1, 0))] + [bytes.fromhex("ff01000100")] * 5
    assert len({call.args[1] for call in ctrl.client.write_gatt_char.call_args_list}) == 6


async def test_complete_optional_hardware_software_stage_order():
    ctrl = make_controller()
    await ctrl.start_notify()

    def reply(_role, packet, **_kwargs):
        opcode = decode_packet(packet)[0]
        feed(ctrl, bytes((opcode, 1, 2, 3, 4)))

    ctrl.client.write_gatt_char.side_effect = reply
    await ctrl._optional_information()
    assert bodies(ctrl) == [bytes.fromhex("0000000003"), bytes.fromhex("0100000003")]
    assert ctrl._state["fsm_relax_optional_information"] == "Observed"
    await ctrl.stop_notify()


async def test_discovery_capability_change_requests_entity_reconciliation():
    ctrl = make_controller(cap=bytes.fromhex("0202000004"))
    ctrl.local.capability_body = bytes.fromhex("0202000004")

    def reply(_role, packet, **_kwargs):
        if decode_packet(packet)[0] == 2:
            feed(ctrl, bytes.fromhex("0208000008"))

    ctrl.client.write_gatt_char.side_effect = reply
    await ctrl.async_discover_capabilities()
    assert ctrl._coordinator._pending_capability_reload is True
    assert ctrl.memory_slot_count == 8
    await ctrl.stop_notify()
