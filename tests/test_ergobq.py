"""Production session, gesture cleanup, native controls and complete action records."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.ergobq.controller import (
    MASSAGE_MODE,
    POSITIONS,
    ErgoBQController,
)
from custom_components.adjustable_bed.codec import ergobq as codec
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import ergobq as app
from custom_components.adjustable_bed.redaction import REDACTED, redact_bundle


async def bed(*, serial="", authorized=True):
    write = SimpleNamespace(
        uuid=codec.WRITE, properties=["write-without-response"], max_write_without_response_size=244
    )
    notify = SimpleNamespace(uuid=codec.NOTIFY, properties=["notify"])
    service = SimpleNamespace(characteristics=[write, notify])
    services = MagicMock()
    services.get_service.return_value = service
    services.__iter__.return_value = iter([service])
    client = SimpleNamespace(
        is_connected=True,
        mtu_size=247,
        services=services,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        disconnect=AsyncMock(),
    )
    state = ControllerState()
    co = SimpleNamespace(
        client=client,
        address="AA:BB:CC:DD:EE:FF",
        name="ErgoBQ",
        entry=SimpleNamespace(
            data={"product_type": "txbazdssmqcnndfc", app.SERIAL: serial, app.STAMP: "12"}
        ),
        cancel_command=asyncio.Event(),
        record_command_trace=MagicMock(),
        handle_controller_state_update=lambda key, value: state.update({key: value}),
        handle_controller_state_updates=lambda *updates: state.update(
            (u.key, u.value) for u in updates
        ),
    )
    c = ErgoBQController(co)
    c.profile = replace(c.profile, notify_settle=0, retry_delay=0)
    await c.start_notify()
    c._authorized = authorized
    receive = client.start_notify.call_args.args[1]
    return c, co, client, receive, state


def frames(client):
    return [call.args[1].hex() for call in client.write_gatt_char.call_args_list]


async def test_authentication_gate_and_no_invented_query_ack():
    c, co, client, receive, _ = await bed(authorized=False)
    with pytest.raises(ConnectionError):
        await c.preset_flat()

    async def send(_char, data, **_kwargs):
        packet = codec.parse_frame(data)
        if packet.command == 3:
            receive(None, bytearray(codec.frame(3, b"")))  # Empty payload cannot authorize.
            assert not c._authorized
            receive(None, bytearray(codec.frame(3, b"\x01")))

    client.write_gatt_char.side_effect = send
    session = SimpleNamespace(is_current=lambda: True)
    await c.async_after_connect(session)
    assert c._authorized
    assert [codec.parse_frame(bytes.fromhex(f)).command for f in frames(client)] == [3, 12, 0, 2]
    auth_trace = co.record_command_trace.call_args_list[0].kwargs["payload"]
    assert auth_trace["hex"] == REDACTED


async def test_auth_rejection_and_timeout_fail_closed():
    c, _, client, receive, _ = await bed(authorized=False)
    client.write_gatt_char.side_effect = lambda *_a, **_k: receive(
        None, bytearray(codec.frame(3, b"\x00"))
    )
    with pytest.raises(ConnectionError, match="rejected"):
        await c.async_after_connect(SimpleNamespace(is_current=lambda: True))
    c.profile = replace(c.profile, auth_timeout=0.01)
    client.write_gatt_char.side_effect = None
    with pytest.raises(TimeoutError):
        await c.async_after_connect(SimpleNamespace(is_current=lambda: True))
    assert not c._authorized


async def test_command_owned_startup_checks_its_caller_before_gatt():
    c, co, client, _, _ = await bed(authorized=False)
    co.cancel_command.set()
    with patch(
        "custom_components.adjustable_bed.beds.ergobq.controller.current_command_context",
        return_value=SimpleNamespace(cancel_event=co.cancel_command),
    ), pytest.raises(asyncio.CancelledError):
        await c.async_after_connect(SimpleNamespace(is_current=lambda: True))
    client.write_gatt_char.assert_not_awaited()


async def test_cancel_inflight_start_settles_before_original_session_release():
    c, co, client, _, _ = await bed()
    writing, finish = asyncio.Event(), asyncio.Event()

    async def send(_char, data, **_kwargs):
        if codec.parse_frame(data).payload[0] == 1:
            writing.set()
            await finish.wait()

    client.write_gatt_char.side_effect = send
    task = asyncio.create_task(c.hold_control("1_up", 60000))
    await writing.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert len(frames(client)) == 1
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client)[-1] == "55aa000400050501000101813c"
    assert len(frames(client)) == 2


async def test_stalled_start_is_bounded_and_releases_without_external_completion():
    c, co, client, _, _ = await bed()
    c.profile = replace(c.profile, write_timeout=0.01, retry_delay=0, attempts=2)
    stalled = asyncio.Event()
    cancelled_writes = 0

    async def send(_char, data, **_kwargs):
        nonlocal cancelled_writes
        if codec.parse_frame(data).payload[0] == 1:
            try:
                await stalled.wait()
            finally:
                cancelled_writes += 1

    client.write_gatt_char.side_effect = send
    task = asyncio.create_task(c.hold_control("1_up", 1000))
    try:
        done, _ = await asyncio.wait({task}, timeout=0.5)
        assert task in done
        with pytest.raises(TimeoutError):
            await task
    finally:
        if not task.done():
            co.cancel_command.set()
            task.cancel()
            stalled.set()
            await asyncio.gather(task, return_exceptions=True)
    assert not stalled.is_set()
    assert cancelled_writes == 2
    assert len(frames(client)) == 3
    assert frames(client)[-1] == "55aa000400050501000101813c"
    assert not c.ble_lock.locked()


async def test_lock_cancellation_and_replaced_link_never_send_or_replay():
    c, co, client, receive, state = await bed()
    await c.ble_lock.acquire()
    task = asyncio.create_task(c.target(1, 15))
    await asyncio.sleep(0)
    co.cancel_command.set()
    c.ble_lock.release()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client) == []
    co.cancel_command = asyncio.Event()
    await c.ble_lock.acquire()
    task = asyncio.create_task(c.hold_control("1_up", 1000))
    await asyncio.sleep(0)
    co.client = SimpleNamespace(is_connected=True)
    c.ble_lock.release()
    with pytest.raises(ConnectionError):
        await task
    assert frames(client) == []
    receive(None, bytearray(codec.frame(5, codec.number(1, 15).encode())))
    assert state.get(POSITIONS[1]) is None


async def test_submitted_motion_with_failed_callback_still_releases():
    from bleak.exc import BleakError

    c, _, client, _, _ = await bed()

    async def send(_char, data, **_kwargs):
        if codec.parse_frame(data).payload[0] == 1:
            raise BleakError("GATT callback failed after submission")

    client.write_gatt_char.side_effect = send
    with pytest.raises(BleakError):
        await c.hold_control("1_up", 60000)
    assert frames(client)[-1] == "55aa000400050501000101813c"
    assert len(frames(client)) == 4  # Three bounded start attempts and original-session STOP.


async def test_current_reports_drive_targets_light_and_massage_alignment():
    c, _, client, receive, state = await bed(serial="010203040405")
    assert len(c.motor_control_specs) == 4
    assert c.execution.declared == {"hold"}
    report = codec.boolean(18, True).encode() + codec.number(1, 15).encode()
    head = codec.Massage(True, 3, 0, 15)
    report += codec.raw(12, head.encode()).encode() + codec.raw(14, head.encode()).encode()
    receive(None, bytearray(codec.frame(5, report)))
    assert state[POSITIONS[1]] == 15 and state[MASSAGE_MODE["head"]] == "wave"
    await c.change_massage("head", "intensity", 4)
    assert list(codec.parse_dps(codec.parse_frame(bytes.fromhex(frames(client)[-1])).payload)) == [
        12,
        14,
    ]
    receive(
        None,
        bytearray(codec.frame(5, codec.raw(14, codec.Massage(True, 2, 0, 15).encode()).encode())),
    )
    await c.change_massage("head", "intensity", 5)
    assert list(codec.parse_dps(codec.parse_frame(bytes.fromhex(frames(client)[-1])).payload)) == [
        12
    ]
    await c.controller_number_specs[0].set_fn(c, 15)
    assert frames(client)[-1] == "55aa00040008010200040000000fc747"
    c.on_disconnect()
    assert state[POSITIONS[1]] is None
    with pytest.raises(ValueError):
        await c.change_massage("head", "intensity", 1)


async def test_metadata_and_unlink_use_their_own_nonempty_response():
    c, _, client, receive, _ = await bed()

    async def sent(_char, data, **_kwargs):
        request = codec.parse_frame(data)
        receive(None, bytearray(codec.frame(5, codec.number(1, 7).encode())))
        assert all(not waiter.done() for command, waiter in c._waiters if command is not None)
        receive(None, bytearray(codec.frame(request.command, b"\x01")))

    client.write_gatt_char.side_effect = sent
    await c.metadata()
    await c.unlink()
    assert not c._authorized


async def test_unlink_timeout_also_invalidates_and_releases_original_link():
    c, _, client, _, _ = await bed()
    c.profile = replace(c.profile, unlink_timeout=0.01)
    with pytest.raises(TimeoutError):
        await c.unlink(3)
    assert not c._authorized
    client.disconnect.assert_awaited_once()


async def test_named_fault_and_partner_reports_remain_typed():
    from custom_components.adjustable_bed.beds.ergobq.controller import (
        FAULT_FLAGS,
        IDENTITY,
        PARTNER_BROADCAST,
        PARTNER_CONNECTED,
    )

    c, _, _, receive, state = await bed()
    body = b"".join(
        dp.encode()
        for dp in (
            codec.raw(31, bytes.fromhex("00000081")),
            codec.enumeration(32, 9),
            codec.raw(33, bytes([255] * 6)),
        )
    )
    receive(None, bytearray(codec.frame(5, body)))
    assert state[FAULT_FLAGS["head_motor"]] is True
    assert state[FAULT_FLAGS["light"]] is True
    assert state[FAULT_FLAGS["foot_motor"]] is False
    assert state[IDENTITY] == "unset"
    assert state[PARTNER_CONNECTED] is True and state[PARTNER_BROADCAST] is True
    receive(
        None,
        bytearray(codec.frame(5, codec.raw(31, b"\xff").encode() + codec.raw(33, b"").encode())),
    )
    assert state[FAULT_FLAGS["head_motor"]] is False
    assert state[PARTNER_CONNECTED] is False
    assert c.position_number_specs == ()


async def test_partial_massage_edits_preserve_sent_fields_and_newer_reports():
    c, _, client, receive, _ = await bed()
    initial = codec.Massage(True, 3, 0, 15)
    c._status({12: initial.encode(), 14: initial.encode(), 18: False})
    await c.change_massage("head", "intensity", 4)
    await c.change_massage("head", "mode", 1)
    latest = codec.parse_frame(bytes.fromhex(frames(client)[-1]))
    assert codec.parse_dps(latest.payload)[12] == codec.Massage(True, 4, 1, 15).encode()

    async def report_during_write(*_args, **_kwargs):
        receive(None, bytearray(codec.frame(5, codec.raw(12, initial.encode()).encode())))

    client.write_gatt_char.side_effect = report_during_write
    await c.change_massage("head", "intensity", 5)
    assert c._massages["head"] == initial
    client.write_gatt_char.side_effect = None
    await c.set_massage_sync(True)
    await c.change_massage("legs", "intensity", 4)
    assert list(codec.parse_dps(codec.parse_frame(bytes.fromhex(frames(client)[-1])).payload)) == [
        12,
        14,
    ]


def test_identity_is_exact_and_private_inputs_are_redacted():
    assert app.product(b"txbazdssmqcnndfc") == "txbazdssmqcnndfc"
    assert app.product(b"txbazdssmqcnndfc", "MindLax") is None
    assert app.product(b"buhvwxxrdccgzvcz") is None
    assert app.motor_count("") == 2
    assert app.motor_count("010203040405") == 4
    with pytest.raises(ValueError):
        app.motor_count("01")
    assert redact_bundle({app.STAMP: "12", app.SERIAL: "010203040405"}) == {
        app.STAMP: REDACTED,
        app.SERIAL: REDACTED,
    }
