"""Accepted AMADA literals, bounded controls and connection ownership."""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.amada.controller import AmadaController
from custom_components.adjustable_bed.beds.amada.receive import bucket, parse
from custom_components.adjustable_bed.beds.amada.state import ALARM_ENABLED, ALARM_SENT, LIGHT
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.profiles import amada as p
from tests.hold_lease_wire import leased_hold, virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

ROOT = Path(__file__).parent / 'fixtures/amada'
VECTORS = json.loads((ROOT / 'vectors.json').read_text())
ACTIONS = dict(zip(
    ('headUp', 'headDown', 'footUp', 'footDown', 'hfUp', 'hfDown', 'headTiltUp', 'headTiltDown',
     'tv', 'zg', 'lounge', 'anti', 'flat', 'm1', 'resetMemoryPosition', 'massageAll', 'timerSwitch',
     'waveAdd', 'footStrengthAdd', 'footStrengthReduce', 'headStrengthAdd', 'headStrengthReduce',
     'toggleLight', 'stop'),
    ('head_up', 'head_down', 'foot_up', 'foot_down', 'combined_up', 'combined_down', 'tilt_up', 'tilt_down',
     'tv_pc', 'zero_g', 'lounge', 'anti_snore', 'flat', 'memory_1', 'reset_memory', 'massage_switch',
     'timer_step', 'wave_mode', 'foot_strength_up', 'foot_strength_down', 'strength_up', 'strength_down',
     'light_toggle', 'stop'), strict=True,
))


@pytest.mark.parametrize('v', VECTORS, ids=lambda v: v['id'])
def test_every_accepted_vector(v):
    args = v['inputs']
    if v['kind'] == 'command':
        actual = codec.frame40(p.AMADA.keys[ACTIONS[v['action']]], args['selector'])
    elif v['kind'] == 'alarm':
        actual = p.alarm_frame(**args)
    elif v['kind'] == 'clock':
        now = datetime(2000 + args['year_offset'], args['month'], args['day'], args['hour'], args['minute'], args['second'])
        actual = p.clock_frame(now)
        assert now.isoweekday() % 7 == args['weekday']
    elif v['kind'] == 'query':
        actual = codec.request(args['literal'][1])
    else:
        actual = parse(bytes.fromhex(v['expected_bytes']), args['selector'])
        assert asdict(actual) == v['expected_state']
        return
    assert actual == bytes.fromhex(v['expected_bytes'])


def test_independent_position_tuples():
    rows = json.loads((ROOT / 'position-literals.json').read_text())
    assert len(rows) == 15
    for row in rows:
        assert p.AMADA.keys[ACTIONS[row['action']]] == int.from_bytes(bytes(row['literal_tuple']), 'big')


@pytest.mark.parametrize(('raw', 'expected'), ((0, 0), (1, 1), (600, 1), (601, 2), (1200, 2), (1201, 3), (1800, 3), (1801, 0)))
def test_parser_boundaries(raw, expected):
    assert bucket(raw) == expected


def test_parser_fallback_and_swapped_markers_and_safe_truncation():
    a = bytes.fromhex('aa000002030600')
    b = bytes.fromhex('bb025803050801')
    frame = b'\xa5\x0b\x0e' + a + b
    assert parse(frame, 0).on and parse(frame, 0).light
    assert parse(b'\xa5\x0b\x0e' + b + a, 0) == parse(frame, 0)
    assert parse(b'\xa5\x0b\x0e' + b, 0xAA) == parse(b'\xa5\x0b\x0e' + b, 0xBB)
    for n in (*range(10), *range(11, 17)):
        assert parse(frame[:n], 0) is None
    assert parse(b'unknown response', 0) is None


def gatt():
    tx = MagicMock(uuid=p.WRITE_UUID, properties=['write-without-response'], descriptors=[], handle=1)
    rx = MagicMock(uuid=p.NOTIFY_UUID, properties=['notify'], descriptors=[], handle=2)
    return [SimpleNamespace(uuid=p.SERVICE_UUID, characteristics=[tx, rx])]


async def make_bed(selector='ab'):
    coord = _FactoryCoordinator()
    client = MagicMock(is_connected=True, services=gatt())
    client.write_gatt_char, client.start_notify, client.stop_notify = AsyncMock(), AsyncMock(), AsyncMock()
    coord.client = client
    coord.controller_state = ControllerState()
    coord.handle_controller_state_updates = lambda *values: coord.controller_state.update((u.key, u.value) for u in values)
    coord.record_command_trace = lambda **_kwargs: None
    c = AmadaController(coord, selector)
    c.static_traits = bed_traits('amada')
    coord.controller = c
    await c.async_discover_capabilities()
    await c.start_notify()
    return c, coord, client


def writes(client):
    return [bytes(c.args[1]) for c in client.write_gatt_char.await_args_list]


def notify(client, data):
    client.start_notify.call_args.args[1](client.services[0].characteristics[1], bytearray(data))


@pytest.mark.parametrize('selector', p.SELECTORS)
@pytest.mark.parametrize('key', p.UTILITY_TAILS)
async def test_utility_batches_and_exact_query_tails(selector, key):
    c, _, client = await make_bed(selector)
    with virtual_clock():
        await c.utility(key)
    assert writes(client) == [codec.frame40(p.AMADA.keys[key], p.SELECTORS[selector])] * 4 + [b'\x00\xb0'] * p.UTILITY_TAILS[key]
    assert all(call.kwargs['response'] is False for call in client.write_gatt_char.await_args_list)


async def test_save_reset_and_recall_timing():
    c, _, client = await make_bed('b')
    with virtual_clock() as clock:
        start = clock.now
        await c.program_memory(1)
        assert round((clock.now - start) * 1000) == 6000
        assert writes(client) == [codec.frame40(p.AMADA.keys['memory_1'], 0xBB)] * 60
        client.write_gatt_char.reset_mock()
        await c.reset_memory()
        assert writes(client) == [codec.frame40(p.AMADA.keys['reset_memory'], 0xBB)] * 60 + [codec.frame40(0, 0xBB)]
        client.write_gatt_char.reset_mock()
        await c.preset_tv()
        assert writes(client) == [codec.frame40(p.AMADA.keys['tv_pc'], 0xBB)] * 4 + [codec.frame40(0, 0xBB)]
    with pytest.raises(ValueError):
        await c.hold_control('memory_1', 6000)


@pytest.mark.parametrize('end', ('expire', 'stop'))
async def test_real_lease_and_actual_task_cancel(end):
    wire = await leased_hold('amada:a', lambda c: c.hold_control('head_up', 100), end_after_s=1.23, end=end)
    assert len(wire.held) >= 12
    assert all(w.data == codec.frame40(1, 0xAA) for w in wire.held)
    assert wire.after and all(w.data == codec.frame40(0, 0xAA) for w in wire.after)
    assert wire.ended_ms == 1230


async def test_cancelled_save_releases_and_settles_backend_write():
    c, coord, client = await make_bed()
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(*args, **kwargs):
        if bytes(args[1]) != codec.frame40(0):
            entered.set()
            await release.wait()

    client.write_gatt_char.side_effect = blocked
    task = asyncio.create_task(c.program_memory(1))
    await entered.wait()
    coord.cancel_command.set()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert writes(client)[-1] == codec.frame40(0)


async def test_old_callback_and_queued_stop_cannot_use_replacement_link():
    c, coord, client = await make_bed()
    old = client.start_notify.call_args.args[1]
    link = c._live()
    coord.client = MagicMock(is_connected=True)
    old(client.services[0].characteristics[1], bytearray.fromhex('a50b0eaa025802030601'))
    assert coord.controller_state[LIGHT] is None
    with pytest.raises(ConnectionError):
        await c._release(link)
    assert not writes(client) and not coord.client.write_gatt_char.called


async def test_alarm_submitted_is_distinct_from_report_and_session_state_clears():
    c, coord, client = await make_bed('a')
    await c.configure_alarm(AlarmRequest(reference_time=datetime(2026,11,27,12), enabled=True, hour=7, minute=30, weekdays=(0, 6), wake_action='light'))
    assert writes(client) == [bytes.fromhex('07058307071e0001aa')]
    assert coord.controller_state[ALARM_SENT] == writes(client)[0].hex()
    assert coord.controller_state[ALARM_ENABLED] is None
    raw = bytes.fromhex('a50c0eaa8307071e0001')
    notify(client, raw)
    assert coord.controller_state[ALARM_ENABLED] is True
    revision = c._alarm_revision
    notify(client, raw)
    assert c._alarm_revision == revision
    c.on_disconnect()
    assert coord.controller_state[ALARM_SENT] is None
    assert coord.controller_state[ALARM_ENABLED] is None


async def test_no_delivery_publishes_no_sent_state_and_stale_link_does_not_publish():
    c, coord, client = await make_bed()
    coord.cancel_command.set()
    await c.configure_alarm(AlarmRequest(reference_time=datetime(2026,11,27,12), enabled=True, hour=7))
    assert not writes(client) and coord.controller_state[ALARM_SENT] is None
    coord.cancel_command.clear()

    async def replace(*args, **kwargs):
        coord.client = MagicMock(is_connected=True)

    client.write_gatt_char.side_effect = replace
    with pytest.raises(ConnectionError):
        await c.configure_alarm(AlarmRequest(reference_time=datetime(2026,11,27,12), enabled=True, hour=7))
    assert coord.controller_state[ALARM_SENT] is None


async def test_bootstrap_and_notify_retry(monkeypatch):
    c, _, client = await make_bed()
    client.start_notify.side_effect = [BleakError('retry'), None]
    monkeypatch.setattr('custom_components.adjustable_bed.beds.amada.controller.dt_util.now', lambda: datetime(2026, 11, 27, 12, 34, 56))
    with virtual_clock():
        await c.start_notify()
        await c.async_on_connect(SimpleNamespace(is_current=lambda: True, async_start_notify=AsyncMock()))
    clock = bytes.fromhex('07040b1a1b050c2238')
    assert writes(client) == [clock] * 4 + [b'\x00\xb0'] * 2 + [b'\x00\xc0'] * 2


@pytest.mark.parametrize(('now', 'mask'), ((datetime(2026, 11, 29, 7, 29), 1), (datetime(2026, 11, 29, 7, 30), 2)))
def test_alarm_once_strictly_future_sunday_and_equality(now, mask):
    assert p.alarm_week((), 7, 30, now) == mask
    assert p.alarm_week((0, 6), 7, 30, now) == 0x83


async def test_write_latency_does_not_extend_refresh_cadence():
    c, _, client = await make_bed()
    times = []
    with virtual_clock() as clock:
        async def latency(*args, **kwargs):
            times.append(clock.now)
            await asyncio.sleep(0.007)
        client.write_gatt_char.side_effect = latency
        await c.hold_control('head_up', 300)
        assert [round(t * 1000) for t in times] == [0, 100, 200, 300]


async def test_alarm_disable_needs_a_real_marker_and_preserves_reported_fields():
    c, _, client = await make_bed('b')
    raw = bytes.fromhex('a50c0ebb8305071e0001')

    async def reply(*args, **kwargs):
        if bytes(args[1]) == b'\x00\xc0':
            notify(client, raw)

    client.write_gatt_char.side_effect = reply
    request = AlarmRequest(reference_time=datetime(2026, 11, 27, 12), enabled=False)
    with virtual_clock():
        await c.check_alarm(request)
        await c.configure_alarm(request)
    assert writes(client) == [b'\x00\xc0'] * 4 + [bytes.fromhex('07058305071e0000bb')]
    client.write_gatt_char.reset_mock()
    raw = bytes.fromhex('a50c0e00000000000000')
    with virtual_clock(), pytest.raises(ValueError, match='unsupported alarm'):
        await c.check_alarm(request)
    assert writes(client) == [b'\x00\xc0'] * 4
