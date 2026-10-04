"""Literal shipped-native vectors and actual app-controller transactions."""

from __future__ import annotations

import asyncio
from itertools import product
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import (
    HELD_COMMANDS,
    LAYOUTS,
    LimossRemoteCapabilities,
    LimossRemoteParser,
    LimossRemoteSequence,
    format_command,
    version_string,
)
from custom_components.adjustable_bed.const import LIMOSS_CHAR_UUID, LIMOSS_SERVICE_UUID
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteMemoryStore,
    LimossRemoteSession,
)
from tests.limoss_remote_vectors import NATIVE_FRAMES, RENDERED_LAYOUTS


def make_controller(
    *,
    keys=8,
    system=0x12,
    memory=8,
    configuration=0,
    light=False,
    massage=False,
    reversal=(False, False, False, False),
    store=None,
    sequence=None,
):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.motor_count = 4
    coordinator.cancel_command = asyncio.Event()
    char = MagicMock(uuid=LIMOSS_CHAR_UUID, handle=7, properties=["write", "notify"])
    service = MagicMock(uuid=LIMOSS_SERVICE_UUID, characteristics=[char])
    coordinator.client = MagicMock(is_connected=True, services=[service])
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return LimossRemoteController(
        coordinator,
        product="bed",
        underbed_light=light,
        massage=massage,
        reverse_motors=reversal,
        cached_capabilities=LimossRemoteCapabilities(keys, system, 255, configuration, memory),
        session=LimossRemoteSession(memories=store if store is not None else LimossRemoteMemoryStore()),
        sequence=sequence if sequence is not None else LimossRemoteSequence(),
    )


def assert_nothing_persisted(c):
    assert not c.session.metadata
    c._coordinator.remember_limoss_remote_capabilities.assert_not_called()


def inner_packets(controller):
    return [
        LimossController._tea_decrypt(call.args[1][1:9])
        for call in controller.client.write_gatt_char.call_args_list
    ]


@pytest.mark.parametrize(("command", "counter", "native"), NATIVE_FRAMES)
def test_native_literal_frames(command, counter, native):
    packet = format_command(bytes.fromhex(command), counter)
    assert packet.hex() == native
    assert LimossRemoteParser().feed(bytes.fromhex(native)) == [bytes.fromhex(command)]


@pytest.mark.parametrize("layout", tuple(RENDERED_LAYOUTS))
def test_all29_rendered_tables_match_independent_frozen_fixture(layout):
    assert LAYOUTS[layout] == RENDERED_LAYOUTS[layout]


@pytest.mark.parametrize(
    ("system", "keys", "configuration", "light", "massage"),
    [
        (system, keys, configuration, light, massage)
        for system, counts in ((0x12, (2, 4, 6, 8, 10, 12)), (0x22, (2, 4, 6, 8)))
        for keys in counts
        for configuration in (0, 1)
        for light, massage in product((False, True), repeat=2)
    ],
)
def test_exact_layout_gates_reversal_and_capability_bytes(
    system, keys, configuration, light, massage
):
    c = make_controller(
        system=system, keys=keys, configuration=configuration, light=light, massage=massage
    )
    assert c.layout is not None
    visible = RENDERED_LAYOUTS[c.layout]
    assert c.held_control_options == tuple(
        action for action, opcode in HELD_COMMANDS.items() if opcode in visible
    )
    assert not c.supports_lights and not c.supports_massage
    assert not c.supports_preset_flat and not c.supports_position_feedback
    assert c.position_number_specs == ()
    assert all(spec.scheduler_resource == "*" for spec in c.motor_control_specs)
    assert "combined_up" not in make_controller(keys=4, light=True).held_control_options
    assert "shift_down" not in make_controller(keys=6, light=True).held_control_options
    assert "combined_up" not in make_controller(system=0x22, keys=4).held_control_options


@pytest.mark.parametrize("key_count", [0, 1, 3, 5, 7, 9, 11, 255])
@pytest.mark.parametrize("system", [0x10, 0x20])
def test_unsupported_key_counts_fall_back8_before_motor_count_fallback(key_count, system):
    c = make_controller(keys=key_count, system=system)
    assert c.capabilities is not None
    assert c.capabilities.supported_keys(c.product_selection) == 8
    assert c.capabilities.effective_motor_count(c.product_selection) == 4
    assert c.capabilities.key_count == key_count


def test_unknown_entry_requires_explicit_user_product_and_never_hardware_guess():
    caps = LimossRemoteCapabilities(8, 0xFF, 0, 0, 0)
    with pytest.raises(ValueError):
        caps.layout(None, False, False)
    assert caps.layout("chair", False, False) == "cKey8"


@pytest.mark.parametrize("reversal", tuple(product((False, True), repeat=4)))
@pytest.mark.asyncio
async def test_all16_reversal_parameters_and_format_time_sequence(reversal):
    c = make_controller(reversal=reversal)
    await c.write_command(bytes((0x12, *reversal)))
    inner = inner_packets(c)[0]
    assert inner[1:6] == bytes((0x12, *reversal)) and inner[6] == 0
    assert c.client.write_gatt_char.call_args.args[0] is c.client.services[0].characteristics[0]
    assert c.client.write_gatt_char.call_args.kwargs == {"response": True}


def test_parser_all_split_points_coalescing_and_unchecked_native_integrity():
    packets = [bytes.fromhex(native) for _, _, native in NATIVE_FRAMES[:3]]
    for split in range(1, 10):
        parser = LimossRemoteParser()
        assert parser.feed(packets[0][:split]) == []
        assert parser.feed(packets[0][split:] + packets[1]) == [
            bytes.fromhex(row[0]) for row in NATIVE_FRAMES[:2]
        ]
    parser = LimossRemoteParser()
    changed = bytearray(packets[0])
    changed[-1] ^= 255
    assert parser.feed(b"noise" + changed) == [bytes.fromhex(NATIVE_FRAMES[0][0])]
    # These synthetic plaintext boundary values prove the source's unchecked AA/sum path.
    inner = b"\0\x10\xff\xff\xff\xff\0\0"
    packet = b"\xdd" + LimossController._tea_encrypt(inner) + b"\0"
    assert parser.feed(packet) == [b"\x10\xff\xff\xff\xff"]


def test_parser_late_marker_noise_and_per_target_buffers_are_bounded():
    first, second = LimossRemoteParser(), LimossRemoteParser()
    native = bytes.fromhex(NATIVE_FRAMES[0][2])
    assert first.feed(b"x" * 10000 + native[:9]) == []
    assert len(first.buffer) == 9
    assert second.feed(native[-1:]) == []
    assert first.feed(native[-1:]) == [bytes.fromhex(NATIVE_FRAMES[0][0])]
    first.clear()
    assert first.buffer == b""


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ("01020304", "12.34"),
        ("ff8000ff", "-128.0"),
        ("ffffffff", "-1."),
        ("00000000", "00.00"),
    ],
)
def test_signed_version_strings(parameters, expected):
    assert version_string(bytes.fromhex(parameters)) == expected


@pytest.mark.asyncio
async def test_information_query_chain_literal_order_and_completed_batch():
    c = make_controller()

    def callback(char, packet, *, response):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        replies = {2: b"\x02\x0c\x14\xff\x18", 0: b"\0\xff\x80\0\xff", 1: b"\x01\x01\x02\x03\x04"}
        c._notification(char, bytearray(format_command(replies[opcode], 0)))

    c.client.write_gatt_char.side_effect = callback
    await c.start_notify()
    assert [inner[1:6].hex() for inner in inner_packets(c)] == [
        "0200000003",
        "0000000003",
        "0100000003",
    ]
    assert c.layout == "gKey12"
    assert c.session.metadata == {
        "hardware_version": "-128.0",
        "software_version": "12.34",
    }
    c._coordinator.remember_limoss_remote_capabilities.assert_called_once()
    char = c.client.start_notify.call_args.args[0]
    await c.stop_notify()
    assert c.client.stop_notify.call_args.args[0] is char


@pytest.mark.asyncio
async def test_failed_info_retains_completed_fields_without_false_success():
    c = make_controller()

    def callback(char, packet, *, response):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        if opcode == 1:
            raise OSError("software failed")
        raw = b"\x02\x08\x12\0\x08" if opcode == 2 else b"\0\x01\x02\x03\x04"
        c._notification(char, bytearray(format_command(raw, 0)))

    c.client.write_gatt_char.side_effect = callback
    with pytest.raises(OSError):
        await c.refresh_device_info()
    assert c.session.metadata == {"hardware_version": "12.34"}
    c._coordinator.remember_limoss_remote_capabilities.assert_called_once()
    assert c._request_reply is None


@pytest.mark.asyncio
async def test_save_queries_fresh_signed_values_atomically_and_reconstructs8slots():
    store = LimossRemoteMemoryStore()
    c = make_controller(system=0x14, store=store)
    values = (-2147483648, -1, 0, 2147483647)

    def callback(char, packet, *, response):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        motor = opcode // 16 - 1
        raw = bytes((opcode,)) + values[motor].to_bytes(4, "big", signed=True)
        c._notification(char, bytearray(format_command(raw, 0)))

    c.client.write_gatt_char.side_effect = callback
    for slot in range(1, 9):
        await c.program_memory(slot)
        await c.rename_memory(slot, "" if slot == 8 else f"Custom {slot}")
    assert len(store.slots) == 8
    assert store.slots[8].name == ""
    assert store.slots[8].positions == tuple(enumerate(values))
    assert c._coordinator.save_app_state.call_count == 16
    restored = LimossRemoteMemoryStore.restore(c.persisted_app_state["memories"])
    assert restored.serialize() == store.serialize()
    assert [inner[1] for inner in inner_packets(c)] == [0x10, 0x20, 0x30, 0x40] * 8
    assert not any(inner[1] in (0x11, 0xFF) for inner in inner_packets(c))


@pytest.mark.asyncio
async def test_failed_partial_save_preserves_previous_slot_and_unsolicited_is_diagnostic_only():
    c = make_controller()
    c.memories.save(1, ((0, 99), (1, 101)))

    def callback(char, packet, *, response):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        if opcode == 0x20:
            raise OSError("second position failed")
        c._notification(char, bytearray(format_command(bytes((opcode, 0, 0, 0, 7)), 0)))

    c.client.write_gatt_char.side_effect = callback
    with pytest.raises(OSError):
        await c.program_memory(1)
    assert c.memories.slots[1].positions == ((0, 99), (1, 101))
    before = c.client.write_gatt_char.call_count
    c._notification(
        c.client.services[0].characteristics[0], bytearray(format_command(b"\x10\0\0\0\x08", 0))
    )
    await asyncio.sleep(0)
    assert c.client.write_gatt_char.call_count == before
    assert c.memories.slots[1].positions == ((0, 99), (1, 101))


@pytest.mark.parametrize(
    ("system", "memory"), [(0x15, 8), (0x16, 8), (0x14, 9), (0x14, 15), (0x14, 0)]
)
@pytest.mark.asyncio
async def test_unsupported_save_domains_fail_before_any_command(system, memory):
    c = make_controller(system=system, memory=memory)
    with pytest.raises(ValueError):
        await c.program_memory(1)
    assert not c.client.write_gatt_char.called and c.sequence.value == 0


@pytest.mark.asyncio
async def test_held_deadline_and_midflight_cancel_always_five_fresh_native_releases():
    c = make_controller(reversal=(True, False, True, False))
    times = []

    def write(char, packet, *, response):
        times.append(asyncio.get_running_loop().time())
        if LimossController._tea_decrypt(packet[1:9])[1] == 0x12:
            c._coordinator.cancel_command.set()

    c.client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await c.hold_control("motor_1_up", 1000)
    inner = inner_packets(c)
    assert [row[1:6].hex() for row in inner] == ["1201000100"] + ["ff01000100"] * 5
    assert [row[6] for row in inner] == list(range(6))
    assert all(later - earlier >= 0.075 for earlier, later in zip(times, times[1:], strict=False))


@pytest.mark.asyncio
async def test_cleanup_attempts_all5_after_first_error_preserving_first_failure():
    c = make_controller()
    c.client.write_gatt_char.side_effect = [OSError("first release failed"), None, None, None, None]
    with pytest.raises(OSError, match="first release failed"):
        await c.stop_all()
    assert [row[1] for row in inner_packets(c)] == [0xFF] * 5
    assert [row[6] for row in inner_packets(c)] == list(range(5))


@pytest.mark.asyncio
async def test_calibration_confirmation_native05_and_five03_zero_reversal_tail():
    c = make_controller(reversal=(True, True, True, True))
    with pytest.raises(ValueError):
        await c.hold_calibration(110, confirmed=False)
    await c.hold_calibration(110, confirmed=True)
    inner = inner_packets(c)
    assert [row[1:6].hex() for row in inner] == ["0501010101"] * 2 + ["0300000000"] * 5


@pytest.mark.asyncio
async def test_optional_disable_constructs_ten_zero_packets_per_feature_without_stop():
    c = make_controller(light=True, massage=True)
    await c.set_optional_features(False, False)
    inner = inner_packets(c)
    assert [row[1:6].hex() for row in inner] == ["7100000000"] * 10 + ["6600000000"] * 10
    assert [row[6] for row in inner] == list(range(20))
    assert not c.underbed_light and not c.massage
    before = c.client.write_gatt_char.call_count
    await c.set_optional_features(True, True)
    assert c.client.write_gatt_char.call_count == before


@pytest.mark.asyncio
async def test_sequence_shared_across_targets_reconstruction_and_failed_delivery():
    sequence = LimossRemoteSequence(255)
    first = make_controller(sequence=sequence)
    first.client.write_gatt_char.side_effect = OSError("delivery failed")
    with pytest.raises(OSError):
        await first.write_command(b"\x12\0\0\0\0")
    second = make_controller(sequence=sequence)
    await second.write_command(b"\x13\0\0\0\0")
    assert inner_packets(first)[0][6] == 255
    assert inner_packets(second)[0][6] == 0
    assert sequence.value == 257
    wrap = LimossRemoteSequence(2147483647)
    assert wrap.take() == 255 and wrap.value == -2147483648


@pytest.mark.asyncio
async def test_exact_first_service_and_handle_no_fallback_invalid_roles():
    c = make_controller()
    first = c.client.services[0]
    duplicate = MagicMock(uuid=LIMOSS_CHAR_UUID, handle=99, properties=["write", "notify"])
    c.client.services = [
        MagicMock(uuid="unrelated", characteristics=[duplicate]),
        first,
        MagicMock(uuid=LIMOSS_SERVICE_UUID, characteristics=[duplicate]),
    ]
    await c.write_command(b"\x12\0\0\0\0")
    assert c.client.write_gatt_char.call_args.args[0] is first.characteristics[0]
    first.characteristics[0].properties = ["read"]
    with pytest.raises(ValueError):
        await c.write_command(b"\x12\0\0\0\0")


@pytest.mark.parametrize(
    "raw",
    [
        {"9": {}},
        {"1": {"name": "bad", "positions": {"4": 0}}},
        {"1": {"name": "bad", "positions": {"0": 2147483648}}},
        {"1": {"name": "bad", "positions": {"0": True}}},
    ],
)
def test_malformed_store_rejected_without_clamp_or_unit_conversion(raw):
    with pytest.raises(ValueError):
        LimossRemoteMemoryStore.restore(raw)


async def test_quick_tap_before_first80ms_poll_sends_no_frame_or_sequence():
    c = make_controller()
    await c.hold_control("motor_1_up", 40)
    c.client.write_gatt_char.assert_not_called()
    assert c.sequence.value == 0


async def test_held_deadline_and_att_latency_never_create_backlog():
    c = make_controller()
    started = asyncio.get_running_loop().time()
    times = []
    active = 0

    async def write(char, packet, **kwargs):
        nonlocal active
        active += 1
        assert active == 1
        times.append(
            (
                asyncio.get_running_loop().time() - started,
                LimossController._tea_decrypt(packet[1:9])[1],
            )
        )
        try:
            await asyncio.sleep(0.11)
        finally:
            active -= 1

    c.client.write_gatt_char.side_effect = write
    await c.hold_control("motor_1_up", 350)
    motion = [time for time, opcode in times if opcode == 0x12]
    release = [time for time, opcode in times if opcode == 0xFF]
    assert 2 <= len(motion) <= 3
    assert all(0.075 <= time < 0.35 for time in motion)
    assert all(later - earlier >= 0.105 for earlier, later in zip(motion, motion[1:], strict=False))
    assert len(release) == 5
    assert release[0] >= 0.345


async def test_preexisting_cancel_or_invalid_command_does_not_consume_counter():
    c = make_controller()
    c._coordinator.cancel_command.set()
    await c.hold_control("motor_1_up", 100)
    with pytest.raises(asyncio.CancelledError):
        await c.write_command(b"\x12\0\0\0\0")
    assert c.sequence.value == 0
    c.client.write_gatt_char.assert_not_called()
    c._coordinator.cancel_command.clear()
    with pytest.raises(ValueError):
        await c.write_command(b"\x12")
    with pytest.raises(ValueError):
        await c.hold_control("dead", 100)
    assert c.sequence.value == 0


async def test_sparse_signed_memory_recall_literal_packets_and300ms_batches():
    from custom_components.adjustable_bed.limoss_remote_state import LimossRemoteMemory

    c = make_controller(system=0x14)
    c.memories.slots[8] = LimossRemoteMemory("Sparse", ((0, -2147483648), (2, -1)))
    times = []
    c.client.write_gatt_char.side_effect = lambda *args, **kwargs: times.append(
        asyncio.get_running_loop().time()
    )
    await c.hold_memory(8, 420)
    payloads = [row[1:6].hex() for row in inner_packets(c)]
    assert payloads == ["1180000000", "31ffffffff"] * 2 + ["ff00000000"] * 5
    assert times[2] - times[0] >= 0.295
    assert all(later - earlier >= 0.075 for earlier, later in zip(times, times[1:], strict=False))
    assert [row[6] for row in inner_packets(c)] == list(range(9))


async def test_capability_retry_one_second_then_hw_sw_without_extra_queries():
    c = make_controller()
    requested, times = [], []

    def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        requested.append(opcode)
        times.append(asyncio.get_running_loop().time())
        if opcode == 2 and requested.count(2) == 1:
            return
        c._notification(
            char,
            bytearray(
                format_command(
                    {2: b"\x02\x08\x12\0\x08", 0: b"\0\1\2\3\4", 1: b"\1\1\2\3\4"}[opcode], 0
                )
            ),
        )

    c.client.write_gatt_char.side_effect = write
    await c.refresh_device_info()
    assert requested == [2, 2, 0, 1]
    assert times[1] - times[0] >= 0.995
    assert c._request_reply is None


@pytest.mark.parametrize("opcode", [0x10, 0x20, 0x30, 0x40, 6])
@pytest.mark.parametrize("value", [-2147483648, -1, 0, 2147483647])
def test_every_signed_response_preserves_bits_without_idle_queries_or_memory_mutation(
    opcode, value
):
    c = make_controller()
    char = c.client.services[0].characteristics[0]
    c._notification(
        char, bytearray(format_command(bytes((opcode,)) + value.to_bytes(4, "big", signed=True), 0))
    )
    c.client.write_gatt_char.assert_not_called()
    assert c.memories.slots == {}
    field = (
        "limoss_remote_serial"
        if opcode == 6
        else f"limoss_remote_motor_{opcode // 16}_position_raw"
    )
    expected = str(value) if opcode == 6 else value
    assert c._coordinator.handle_controller_state_update.call_args.args == (field, expected)


async def test_startup_failure_unsubscribes_exact_role_and_preserves_read_error():
    c = make_controller()
    c.client.write_gatt_char.side_effect = ConnectionError("query failed")
    c.client.stop_notify.side_effect = ValueError("cleanup failed")
    with pytest.raises(ConnectionError, match="query failed"):
        await c.start_notify()
    c.client.stop_notify.assert_awaited_once_with(c.client.services[0].characteristics[0])
    assert c._notify_client is None and c._notify_char is None
    assert c._request_reply is None and c._parser.buffer == b""


async def test_repeated_task_cancellation_still_drains_five_fresh_releases():
    c = make_controller()
    entered = asyncio.Event()

    async def write(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        if opcode == 0xFF:
            entered.set()
            await asyncio.sleep(0.01)

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.hold_control("motor_1_up", 100))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [row[1] for row in inner_packets(c)] == [0x12] + [0xFF] * 5


async def test_subscription_callback_ignores_old_client_after_reconnect_and_stop():
    c = make_controller()
    c.refresh_device_info = AsyncMock()
    first = c.client
    first_char = first.services[0].characteristics[0]
    duplicate = MagicMock(uuid=LIMOSS_CHAR_UUID, handle=99, properties=["write", "notify"])
    first.services[0].characteristics.append(duplicate)
    await c.start_notify()
    first_callback = first.start_notify.await_args.args[1]
    first.start_notify.assert_awaited_once()
    assert first.start_notify.await_args.args[0] is first_char
    await c.stop_notify()
    first.stop_notify.assert_awaited_once_with(first_char)
    first_callback(first_char, bytearray(format_command(b"\6\xff\xff\xff\xff", 0)))
    assert_nothing_persisted(c)
    second = make_controller().client
    second_char = second.services[0].characteristics[0]
    second_char.handle = 44
    c._coordinator.client = second
    await c.start_notify()
    second_callback = second.start_notify.await_args.args[1]
    first_callback(first_char, bytearray(format_command(b"\6\0\0\0\1", 0)))
    assert_nothing_persisted(c)
    second_callback(second_char, bytearray(format_command(b"\6\xff\xff\xff\xff", 0)))
    assert c.session.metadata == {"serial": "-1"}
    await c.stop_all()
    assert all(call.args[0] is second_char for call in second.write_gatt_char.call_args_list)
    assert [row[1] for row in inner_packets(c)] == [0xFF] * 5


@pytest.mark.parametrize(
    ("action", "opcode", "keys", "system", "light", "massage"),
    [
        ("motor_1_up", 0x12, 8, 0x14, False, False),
        ("motor_1_down", 0x13, 8, 0x14, False, False),
        ("motor_2_up", 0x22, 8, 0x14, False, False),
        ("motor_2_down", 0x23, 8, 0x14, False, False),
        ("motor_3_up", 0x32, 12, 0x14, False, False),
        ("motor_3_down", 0x33, 12, 0x14, False, False),
        ("motor_4_up", 0x42, 8, 0x24, False, False),
        ("motor_4_down", 0x43, 8, 0x24, False, False),
        ("combined_up", 0x50, 10, 0x14, False, False),
        ("combined_down", 0x51, 10, 0x14, False, False),
        ("lift_up", 0x52, 10, 0x14, False, False),
        ("lift_down", 0x53, 10, 0x14, False, False),
        ("shift_up", 0x54, 10, 0x14, False, False),
        ("shift_down", 0x55, 10, 0x14, False, False),
        ("massage_back_plus", 0x60, 8, 0x14, False, True),
        ("massage_back_minus", 0x61, 8, 0x14, False, True),
        ("massage_foot_plus", 0x62, 8, 0x14, False, True),
        ("massage_foot_minus", 0x63, 8, 0x14, False, True),
        ("massage_both_plus", 0x64, 2, 0x12, True, True),
        ("massage_both_minus", 0x65, 2, 0x12, True, True),
        ("light", 0x70, 2, 0x12, True, False),
    ],
)
async def test_every_reachable_held_opcode_and_native_stop_through_live_caller(
    action, opcode, keys, system, light, massage
):
    c = make_controller(
        keys=keys, system=system, light=light, massage=massage, reversal=(True, False, True, False)
    )
    await c.hold_control(action, 110)
    assert [row[1:6] for row in inner_packets(c)] == [bytes((opcode, 1, 0, 1, 0))] + [
        bytes.fromhex("ff01000100")
    ] * 5


@pytest.mark.parametrize("slot", range(1, 9))
async def test_all_eight_local_slots_have_real_recall_and_release(slot):
    from custom_components.adjustable_bed.limoss_remote_state import LimossRemoteMemory

    c = make_controller(system=0x11)
    c.memories.slots[slot] = LimossRemoteMemory(f"Slot {slot}", ((0, -slot),))
    await c.hold_memory(slot, 110)
    assert [row[1:6] for row in inner_packets(c)] == [
        bytes((0x11,)) + (-slot).to_bytes(4, "big", signed=True)
    ] + [bytes.fromhex("ff00000000")] * 5


def test_each_dead_or_unrendered_cell_cannot_be_a_public_action():
    c = make_controller(system=0x22, keys=4)
    assert set(c.held_control_options) == {
        "motor_1_up",
        "motor_1_down",
        "motor_2_up",
        "motor_2_down",
    }
    assert not any(
        action in HELD_COMMANDS
        for action in ("query_serial", "volume_up", "volume_down", "test", "flat")
    )
    assert c.supports_sync is False
    assert c.supports_light_toggle_control is False
    assert c.supports_massage_off_control is False
    assert c.memory_slot_count == 8


async def test_rename_preserves_valid_local_capacity_even_when_capture_motor_domain_is_unsupported():
    c = make_controller(system=0x15)
    await c.rename_memory(8, "Name only")
    assert c.memories.slots[8].name == "Name only"
    with pytest.raises(ValueError):
        await c.program_memory(8)
    with pytest.raises(ValueError):
        await c.hold_memory(8, 100)
    c.client.write_gatt_char.assert_not_called()


async def test_changed_motor_layout_rejects_stale_memory_before_any_write():
    from custom_components.adjustable_bed.limoss_remote_state import LimossRemoteMemory

    c = make_controller(system=0x12)
    c.memories.slots[8] = LimossRemoteMemory("Old four-motor layout", ((0, -1), (3, 1)))
    with pytest.raises(ValueError, match="different reported motor layout"):
        await c.hold_memory(8, 100)
    c.client.write_gatt_char.assert_not_called()
    assert c.sequence.value == 0


@pytest.mark.parametrize(
    ("properties", "response"),
    [
        (["write", "notify"], True),
        (["write-without-response", "notify"], False),
        (["write", "write-without-response", "notify"], True),
    ],
)
async def test_property_based_write_policy_binds_actual_selected_characteristic(
    properties, response
):
    c = make_controller()
    char = c.client.services[0].characteristics[0]
    char.properties = properties
    await c.write_command(b"\x12\0\0\0\0")
    c.client.write_gatt_char.assert_awaited_once()
    assert c.client.write_gatt_char.await_args.args[0] is char
    assert c.client.write_gatt_char.await_args.kwargs == {"response": response}
    trace = c._coordinator.record_command_trace.call_args.kwargs
    assert trace["characteristic_handle"] == char.handle
    assert trace["response"] is response
    assert trace["payload"]["hex"] == c.client.write_gatt_char.await_args.args[1].hex()


async def test_actual_att_timeout_is_not_mistaken_for_hold_deadline_and_still_releases():
    c = make_controller()

    async def write(char, packet, **kwargs):
        if LimossController._tea_decrypt(packet[1:9])[1] == 0x12:
            await asyncio.Event().wait()

    c.client.write_gatt_char.side_effect = write
    with pytest.raises(TimeoutError):
        await c.hold_control("motor_1_up", 3000)
    assert [row[1] for row in inner_packets(c)] == [0x12] + [0xFF] * 5


def test_unused04_unknown_opcodes_do_not_mutate_capabilities_memories_or_issue_queries():
    c = make_controller()
    before = c.protocol_diagnostics
    char = c.client.services[0].characteristics[0]
    for opcode in (4, 0x91, 0x92, 0x99, 0xFF):
        c._notification(
            char, bytearray(format_command(bytes((opcode,)) + bytes.fromhex("80000000"), 0))
        )
    assert c.protocol_diagnostics == before
    c._coordinator.handle_controller_state_update.assert_not_called()
    assert_nothing_persisted(c)
    c.client.write_gatt_char.assert_not_called()


async def test_notification_teardown_fails_active_request_without_claiming_user_cancel():
    c = make_controller()
    entered = asyncio.Event()
    c.client.write_gatt_char.side_effect = lambda *args, **kwargs: entered.set()
    task = asyncio.create_task(c.refresh_device_info())
    await entered.wait()
    await c.stop_notify()
    with pytest.raises(ConnectionError, match="notification channel stopped"):
        await task
    assert c._request_reply is None
    assert not c._coordinator.cancel_command.is_set()
    assert [row[1] for row in inner_packets(c)] == [2]
    assert_nothing_persisted(c)


@pytest.mark.parametrize(
    "transition",
    ["disconnected", "cleared", "replaced", "wrong_handle", "wrong_uuid", "replaced_role"],
)
async def test_registered_callback_rejects_stale_client_and_wrong_exact_role(transition):
    c = make_controller()
    c.refresh_device_info = AsyncMock()
    client = c.client
    role = client.services[0].characteristics[0]
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    raw_callback = MagicMock()
    c.set_raw_notify_callback(raw_callback)
    reply = asyncio.get_running_loop().create_future()
    c._request_reply = (6, reply)
    if transition == "disconnected":
        client.is_connected = False
    elif transition == "cleared":
        c._coordinator.client = None
    elif transition == "replaced":
        c._coordinator.client = make_controller().client
    elif transition == "wrong_handle":
        role = MagicMock(uuid=LIMOSS_CHAR_UUID, handle=99)
    elif transition == "wrong_uuid":
        role = MagicMock(uuid=LIMOSS_SERVICE_UUID, handle=role.handle)
    elif transition == "replaced_role":
        client.services[0].characteristics = [
            MagicMock(uuid=LIMOSS_CHAR_UUID, handle=role.handle, properties=["write", "notify"])
        ]
    callback(role, bytearray(format_command(bytes.fromhex("06ffffffff"), 0)))
    assert_nothing_persisted(c)
    c._coordinator.handle_controller_state_update.assert_not_called()
    raw_callback.assert_not_called()
    assert c._parser.buffer == b"" and not reply.done()
    reply.cancel()
    c._request_reply = None
    await c.stop_notify()


async def test_disconnect_generation_fences_reused_client_and_fails_active_query():
    c = make_controller()
    c.refresh_device_info = AsyncMock()
    client = c.client
    role = client.services[0].characteristics[0]
    await c.start_notify()
    old_callback = client.start_notify.await_args.args[1]
    reply = asyncio.get_running_loop().create_future()
    c._request_reply = (6, reply)
    c._parser.buffer.extend(b"\xaa")
    c.on_disconnect()
    assert c._notify_client is None and c._notify_char is None and c._parser.buffer == b""
    with pytest.raises(ConnectionError, match="notification channel stopped"):
        reply.result()
    c._request_reply = None
    # The same native client/characteristic objects may be reused by a transport.
    await c.start_notify()
    current_callback = client.start_notify.await_args.args[1]
    pending = asyncio.get_running_loop().create_future()
    c._request_reply = (6, pending)
    old_callback(role, bytearray(format_command(bytes.fromhex("0600000001"), 0)))
    assert_nothing_persisted(c)
    assert not pending.done()
    current_callback(role, bytearray(format_command(bytes.fromhex("06ffffffff"), 0)))
    assert pending.result() == bytes.fromhex("ffffffff")
    assert c.session.metadata == {"serial": "-1"}
    c._request_reply = None
    await c.stop_notify()


async def test_unsubscribe_invalidates_registered_callback_before_native_await():
    c = make_controller()
    c.refresh_device_info = AsyncMock()
    client = c.client
    role = client.services[0].characteristics[0]
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]

    async def unsubscribe(char):
        assert char is role
        callback(role, bytearray(format_command(bytes.fromhex("06ffffffff"), 0)))
        assert_nothing_persisted(c)

    client.stop_notify.side_effect = unsubscribe
    await c.stop_notify()


async def test_disconnect_hook_fails_actual_information_request_and_drops_late_reply():
    c = make_controller()
    refresh = c.refresh_device_info
    c.refresh_device_info = AsyncMock()
    client = c.client
    role = client.services[0].characteristics[0]
    await c.start_notify()
    callback = client.start_notify.await_args.args[1]
    entered = asyncio.Event()

    async def write(char, packet, **kwargs):
        entered.set()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(refresh())
    await entered.wait()
    c.on_disconnect()
    with pytest.raises(ConnectionError, match="notification channel stopped"):
        await task
    callback(role, bytearray(format_command(bytes.fromhex("0208140028"), 0)))
    assert c._request_reply is None and c._progress is None
    assert_nothing_persisted(c)
    assert client.write_gatt_char.await_count == 1
