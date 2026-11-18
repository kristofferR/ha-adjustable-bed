"""Lunio Smart+ production literals, stream fields and physical-session fences."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.luniosmart import controller as bed
from custom_components.adjustable_bed.beds.luniosmart.discovery import ALIASES, SCAN_CODES, matches
from custom_components.adjustable_bed.beds.luniosmart.receive import Receiver, decode
from custom_components.adjustable_bed.beds.richmat.transport import select_app_link
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.luniosmart import DIRECTIONS, PRESETS, PROFILE
from tests.luniosmart_vectors import FIXTURES, VECTORS
from tests.test_casper_base import char, frames
from tests.test_controller_contract import _FactoryCoordinator

GATT = json.loads((FIXTURES / "gatt-routes.json").read_text())
FOCUSED = json.loads((FIXTURES / "focused-cases.json").read_text())


def make(route=0, properties=("write", "write-without-response"), notify=True):
    c = _FactoryCoordinator()
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    row = GATT[route]
    chars = [char(row["write"].upper(), *properties)]
    if notify:
        chars += [char("first-notify", "notify"), char(row["declared_notify"], "notify")]
    c.client.services = [SimpleNamespace(uuid=row["service"].upper(), characteristics=chars)]
    ctrl = bed.LunioSmartController(c)
    c.controller = ctrl
    return ctrl, c


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real_sleep = asyncio.sleep

    async def pause(seconds, cancel):
        now[0] += seconds
        await real_sleep(0)
        return cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed, "_pause", pause)
    monkeypatch.setattr(bed.dt_util, "now", lambda: datetime(2026, 11, 17, 12, 34, 56))
    return now


def notify(c, packet):
    call = c.client.start_notify.call_args
    call.args[1](call.args[0], bytearray.fromhex(packet))


@pytest.mark.parametrize("route", range(6))
@pytest.mark.parametrize(
    "properties,response", [(("write",), True), (("write", "write-without-response"), False)]
)
async def test_six_routes_startup_and_every_proven_control(clock, route, properties, response):
    ctrl, c = make(route, properties)
    await ctrl.start_notify()
    assert c.client.start_notify.call_args.args[0].uuid == "first-notify"
    assert frames(c) == [
        GATT[route]["query"],
        codec.calendar(datetime(2026, 11, 17, 12, 34, 56), build=codec.record_20_len).hex(),
    ]
    for action in (*DIRECTIONS, *PRESETS):
        c.client.write_gatt_char.reset_mock()
        if action in DIRECTIONS:
            await ctrl.hold_control(action, 250)
            expected = [codec.command(DIRECTIONS[action]).hex()] * 3
        else:
            await ctrl.action(action)
            expected = [codec.command(PRESETS[action]).hex()]
        assert frames(c) == [*expected, "6e01006edd"]
        assert all(
            call.kwargs["response"] is response for call in c.client.write_gatt_char.call_args_list
        )


def test_catalog_inventory_and_case_sensitive_substrings():
    assert len(ALIASES) == 1134 and len(SCAN_CODES) == 1128
    assert {row["code"] for row in ALIASES if not row["eligible"]} == {
        "",
        "ZR90",
        "FMRN",
        "H3RN",
        "JSRN",
        "MTRN",
    }
    assert all(matches("prefix" + code + "suffix") for code in SCAN_CODES)
    assert matches("bed MlRM") and not matches("bed mlrm")
    assert not matches("not-a-bed")


@pytest.mark.parametrize(
    "row", [row for row in FOCUSED if row["entry"] == "fields"], ids=lambda row: row["id"]
)
def test_all_accepted_dynamic_bed_fields_on_production_parser(row):
    expected = [] if row["expected"] == "RangeError" else [tuple(e) for e in row["expected"]]
    assert decode(bytes.fromhex(row["hex"])) == expected


@pytest.mark.parametrize(
    "row",
    [r for r in VECTORS if r["inputs"]["builder"] == "literal_notification"],
    ids=lambda row: row["id"],
)
def test_exact_inner_constants_never_become_setters(row):
    value = decode(bytes.fromhex(row["expected_bytes"]))
    excluded = any(term in row["inputs"]["event"] for term in ("Aromatherapy", "Music"))
    assert value == ([] if excluded else [(row["inputs"]["event"], None)])


@pytest.mark.parametrize(
    "row",
    [row for row in FOCUSED if row["entry"] == "deframe" and isinstance(row["expected"], dict)],
    ids=lambda row: row["id"],
)
def test_shared_frame_boundaries_and_residuals(row):
    receiver = Receiver()
    actual = []
    for step in row["steps"]:
        if step == "expire":
            receiver.pending.clear()
        else:
            actual.extend(receiver.feed(bytes.fromhex(step)))
    expected = [bytes.fromhex(frame) for frame in row["expected"]["frames"]]
    expected = [
        frame
        for frame in expected
        if len(frame) < 2
        or frame[1] not in (0x21, 0x40)
        and (frame[1] != 0x20 or codec.is_valid(frame))
    ]
    assert actual == expected
    assert receiver.pending.hex() == row["expected"]["buffer"]


def test_malformed_deframer_cannot_spin_grow_or_publish_partial_state():
    receiver = Receiver()
    assert receiver.feed(bytes.fromhex("6e2100008f")) == [] and not receiver.pending
    assert receiver.feed(bytes.fromhex("6e4001")) == [] and receiver.pending.hex() == "6e4001"
    receiver.pending.clear()
    assert receiver.feed(b"x" * 4097) == [] and not receiver.pending
    assert receiver.feed(bytes.fromhex("6e40ffff")) == [] and not receiver.pending
    assert decode(bytes.fromhex("6e20050b60")) == []


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
@pytest.mark.parametrize("writerless", [False, True])
async def test_query_selector_independent_of_first_writer_and_notify(clock, order, writerless):
    ctrl, c = make(order[0], notify=False)
    second = GATT[order[1]]
    chars = [] if writerless else [char(second["write"], "write")]
    chars += [char("later-notify", "notify")]
    c.client.services.append(SimpleNamespace(uuid=second["service"], characteristics=chars))
    await ctrl.start_notify()
    assert ctrl._session.link.tx.uuid.lower() == GATT[order[0]]["write"].lower()
    assert ctrl._session.link.rx.uuid == "later-notify"
    assert frames(c)[0] == second["query"]


async def test_no_notify_still_queries_but_subscription_failure_skips_startup(clock):
    ctrl, c = make(notify=False)
    await ctrl.start_notify()
    c.client.start_notify.assert_not_awaited()
    assert len(frames(c)) == 2
    ctrl, c = make()
    c.client.start_notify.side_effect = RuntimeError("subscription failed")
    with pytest.raises(RuntimeError, match="subscription failed"):
        await ctrl.start_notify()
    assert frames(c) == []
    ctrl, c = make(properties=("write-without-response",))
    with pytest.raises(ValueError, match="writable"):
        select_app_link(c.client, PROFILE.transports)


async def test_state_is_read_only_and_old_subscription_cannot_cross_session(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    notify(c, "6e90000700")
    assert ctrl.observations["deviceControlBoxProtocolVersionEvent"] == 7
    assert (
        not ctrl.supports_massage
        and not ctrl.supports_lights
        and not ctrl.supports_position_feedback
    )
    assert ctrl.memory_slot_count == 1 and ctrl.position_number_specs == ()
    assert len(ctrl.motor_control_specs) == 2 and not ctrl.supports_single_address_pairing
    old = c.client.start_notify.call_args
    notify(c, "6e20ff")
    assert ctrl._expiry is not None
    ctrl.on_disconnect()
    assert ctrl._expiry is None and not ctrl._receiver.pending and not ctrl.observations
    await ctrl.start_notify()
    old.args[1](old.args[0], bytearray.fromhex("6e90006300"))
    assert not ctrl.observations


async def test_hold_deadline_slow_write_has_no_catchup(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def slow(*args, **kwargs):
        clock[0] += 1

    c.client.write_gatt_char.side_effect = slow
    await ctrl.hold_control("head_up", 250)
    assert frames(c) == ["6e01002493", "6e01006edd"]


async def test_stop_cancellation_settles_inflight_before_independent_release(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    started, finish = asyncio.Event(), asyncio.Event()

    async def pending(_char, packet, **kwargs):
        if packet.hex() == "6e01002493":
            started.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = pending
    task = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    await started.wait()
    c.cancel_command.set()
    task.cancel()
    await asyncio.sleep(0)
    assert frames(c) == ["6e01002493"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("change", ["client", "owner", "controller", "session"])
async def test_queued_execution_rechecks_all_physical_ownership(clock, change):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    captured = ctrl._session
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(ctrl.action("flat"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    if change == "client":
        c.client = MagicMock(is_connected=True)
    elif change == "owner":
        ctrl._coordinator = _FactoryCoordinator()
    elif change == "controller":
        c.controller = None
    elif change == "session":
        ctrl._session = None
    ctrl._ble_lock.release()
    with pytest.raises((ConnectionError, ValueError)):
        await task
    captured.link.client.write_gatt_char.assert_not_awaited()


async def test_single_address_side_selector_is_rejected(clock):
    ctrl, c = make()
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    with ctrl.side_scope("left"), pytest.raises(ValueError, match="side selector"):
        await ctrl.action("flat")
    assert not frames(c)


def test_startup_writes_have_no_buttons_and_status_is_opt_in():
    ctrl, _ = make()
    # Query and clock sync run on every connect.
    assert ctrl.controller_button_specs == ()
    (status,) = ctrl.controller_state_sensor_specs
    assert not status.entity_registry_enabled_default
