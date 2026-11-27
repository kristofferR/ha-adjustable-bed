"""MLILY 3.1.1 literal compatibility, catalog gates and owned-link operations."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.mlily0.controller import MlilyController
from custom_components.adjustable_bed.beds.mlily0.receive import Receiver
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.mlily0 import ACTIONS, PROFILES
from tests.hold_lease_wire import virtual_clock
from tests.test_casper_base import frames
from tests.test_casper_base import make as casper_make

ROOT = Path(__file__).parent / "fixtures/mlily0"


@pytest.fixture(autouse=True)
async def protocol_clock():
    with virtual_clock():
        yield


def make(product="bedc", transport=1):
    _, coordinator = casper_make(transport=transport)
    return MlilyController(coordinator, product=product), coordinator


@pytest.mark.parametrize("row", json.loads((ROOT / "products.json").read_text()), ids=lambda r: r["key"])
def test_exact_product_actions_and_save_gates(row):
    p = PROFILES[row["key"]]
    for group, expected in zip(p.row[1:6], row["groups"], strict=True):
        assert [dict(zip(("name", "short", "save"), ACTIONS[i], strict=True)) for i in group] == expected
    assert p.row[10] == row["repeat"]
    controller, _ = make(row["key"])
    for name, (_, save) in controller.actions.items():
        assert save is None or any(r["name"] == name and r["save"] == save for g in row["groups"] for r in g)
    assert controller.supports_single_address_pairing is False


@pytest.mark.parametrize("route", ("P1", "P2"))
def test_every_frozen_control_literal_reuses_existing_codec(route):
    vectors = [r for r in json.loads((ROOT / "controls.json").read_text()) if r["route"] == route]
    actions = [(name, code) for name, short, save in ACTIONS for code in ((short,) if save is None else (short, save))]
    assert len(vectors) == len(actions) == 75
    for row, (name, code) in zip(vectors, actions, strict=True):
        assert row["action"].startswith("deviceFunctionItem" + name + " /")
        assert codec.function(code, action="deviceFunctionItem" + name, single=route == "P1").hex() == row["expected"]


@pytest.mark.parametrize("row", json.loads((ROOT / "replay.json").read_text()), ids=lambda r: r["id"])
def test_frozen_builder_and_readback_subset(row):
    p, kind = row["inputs"], row["kind"]
    if kind == "control":
        actual = codec.function(p["code"], single=p["nordic"], action="deviceFunctionItemExitLimit" if p.get("exit_limit") else "").hex()
    elif kind in ("alarm_low", "alarm_high"):
        actual = codec.countdown(p["minutes"], p.get("mode", 0))[kind == "alarm_high"].hex()
    elif kind == "alarm_repeat":
        actual = codec.frame(0x6E, 0x14, int(p["daily"]), 0xFE).hex()
    elif kind == "sync_time":
        actual = [codec.frame(0x6E, 0x13, p["hour"], p["minute"]).hex(), codec.frame(0x6E, 0x14, p["second"], 0xFF).hex()]
    else:
        events = []
        Receiver(lambda name, value: events.append((name, value))).feed(bytes.fromhex(p["bytes"]))
        actual = (events[0][0] if events[0][1] is True else events[0][1]) if events else None
        if events and events[0][0] == "white_led":
            actual = {"white_led": events[0][1]}
    assert actual == row["expected"]


@pytest.mark.parametrize("transport", range(6))
async def test_gatt_response_and_no_invented_startup(transport):
    controller, c = make(transport=transport)
    await controller.start_notify()
    assert frames(c) == []
    await controller.exit_limit()
    assert frames(c) == (["00"] if transport == 0 else ["6e02010071"])
    assert not controller.supports_single_address_pairing
    await controller.stop_notify()


async def test_native_controls_use_product_overrides():
    controller, c = make("bedM6")
    await controller.start_notify()
    await controller.preset_memory(2)
    await controller.program_memory(2)
    assert frames(c) == ["6e0100f05f", "6e0100f160"]
    assert controller.alarm_capability
    with controller.side_scope("right"), pytest.raises(ValueError, match="no side selector"):
        await controller.preset_memory(1)
    await controller.stop_notify()


async def test_native_alarm_and_clock_are_framed_on_nordic():
    controller, c = make(transport=0)
    await controller.start_notify()
    now = datetime(2026, 11, 27, 7, 0, 15, tzinfo=UTC)
    with patch("custom_components.adjustable_bed.beds.mlily0.controller.dt_util.now", return_value=now):
        await controller.configure_alarm(AlarmRequest(enabled=True, hour=12, minute=0,
            wake_action="memory_1", weekdays=tuple(range(7)), reference_time=now))
    assert frames(c) == ["6e052c009f", "6e06012ea3", "6e1401fe81"]

    c.client.write_gatt_char.reset_mock()
    with patch("custom_components.adjustable_bed.beds.mlily0.controller.dt_util.now", return_value=now):
        await controller.sync_clock()
    assert frames(c) == ["6e13070088", "6e140fff90"]
    c.client.write_gatt_char.reset_mock()
    await controller.configure_alarm(AlarmRequest(enabled=False, reference_time=now))
    assert frames(c) == ["6e05000073", "6e06000074"]
    with pytest.raises(ValueError, match="only once or every day"):
        controller.validate_alarm(AlarmRequest(enabled=True, wake_action="memory_1", weekdays=(1,), reference_time=now))
    await controller.stop_notify()


async def test_alarm_countdown_accounts_for_connection_delay():
    controller, c = make(transport=0)
    await controller.start_notify()
    alarm = AlarmRequest(enabled=True, hour=12, minute=0, wake_action="memory_1",
        reference_time=datetime(2026, 11, 27, 7, 0, 59, tzinfo=UTC))
    with patch("custom_components.adjustable_bed.beds.mlily0.controller.dt_util.now",
        return_value=datetime(2026, 11, 27, 7, 1, tzinfo=UTC)):
        await controller.configure_alarm(alarm)
    assert frames(c) == ["6e052b009e", "6e06012ea3", "6e1400fe80"]


@pytest.mark.parametrize("revocation", ["session", "caller"])
async def test_submission_has_no_extra_scheduling_gap(monkeypatch, revocation):
    controller, c = make()
    await controller.start_notify()
    observed = []

    def revoke():
        observed.append("revoked")
        if revocation == "session":
            controller.on_disconnect()
        else:
            c.cancel_command.set()
            task.cancel()

    def trace(*_args, **_kwargs):
        asyncio.get_running_loop().call_soon(revoke)

    async def write(*_args, **_kwargs):
        observed.append("submitted")
        finished = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(finished.set_result, None)
        await finished

    monkeypatch.setattr(c, "record_command_trace", trace)
    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.preset_memory(1))
    if revocation == "caller":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    assert observed[:2] == ["submitted", "revoked"]


async def test_release_before_first_tick_sends_nothing():
    controller, c = make()
    await controller.start_notify()
    c.cancel_command.set()
    await controller.hold_control("mlily0_HeadUp", 500)
    assert frames(c) == []
    await controller.stop_notify()


async def test_motor_refresh_ends_in_original_protocol_stop():
    controller, c = make()
    await controller.start_notify()
    await controller.hold_control("mlily0_HeadUp", 300)
    assert frames(c) == ["6e01002493"] * 3 + ["6e01006edd"]
    await controller.stop_notify()


async def test_write_cancellation_settles_before_stop():
    controller, c = make()
    await controller.start_notify()
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []

    async def write(char, packet, **kwargs):
        writes.append(bytes(packet).hex())
        if len(writes) == 1:
            entered.set()
            await release.wait()

    c.client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(controller.hold_control("mlily0_HeadUp", 500))
    await entered.wait()
    task.cancel()
    c.cancel_command.set()
    await asyncio.sleep(0)
    assert writes == ["6e01002493"]
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert writes == ["6e01002493", "6e01006edd"]
    await controller.stop_notify()


async def test_reconnect_does_not_receive_old_alarm_tail():
    controller, c = make()
    await controller.start_notify()
    original = c.client

    async def replace_link(*args, **kwargs):
        controller.on_disconnect()
        c.client = AsyncMock(is_connected=True)

    original.write_gatt_char.side_effect = replace_link
    with pytest.raises(ConnectionError):
        await controller.configure_alarm(AlarmRequest(enabled=True, hour=12, minute=0,
            wake_action="memory_1", reference_time=datetime(2026, 11, 27, 7, tzinfo=UTC)))
    assert original.write_gatt_char.await_count == 1
    c.client.write_gatt_char.assert_not_awaited()


async def test_failed_movement_is_not_retried_and_still_releases():
    controller, c = make()
    await controller.start_notify()
    c.client.write_gatt_char.side_effect = [TimeoutError("write failed"), None]
    with pytest.raises(TimeoutError):
        await controller.hold_control("mlily0_HeadUp", 300)
    assert frames(c) == ["6e01002493", "6e01006edd"]
    await controller.stop_notify()


async def test_native_alarm_action_exposes_product_modes(hass):
    from tests.alarm_helpers import call_set_alarm

    controller, c = make("bedM6", transport=0)
    await controller.start_notify()
    await call_set_alarm(hass, controller, {
        "enabled": True, "time": "12:00:00", "wake_action": "memory_2",
    }, bed_type="mlily0")
    # The high countdown frame carries this product's F0 override on Nordic too.
    assert bytes(c.client.write_gatt_char.call_args_list[1].args[1])[3] == 0xF0
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="only once or every day"):
        await call_set_alarm(hass, controller, {
            "enabled": True, "time": "12:00:00", "wake_action": "memory_2",
            "weekdays": ["monday"],
        }, bed_type="mlily0")
    assert frames(c) == []
    await controller.stop_notify()


@pytest.mark.parametrize("row", json.loads((ROOT / "gatt.json").read_text()), ids=lambda r: r["name"])
def test_frozen_gatt_routes(row):
    key = "n1" if row["name"].endswith("Nordic") else row["name"][-2:].lower()
    route = codec.TRANSPORTS[key]
    assert (route.service_uuid, route.write_uuid, route.notify_uuid) == tuple(
        row[k].lower() for k in ("service", "write", "declared_notify")
    )


async def test_get_up_is_a_preset_not_a_sustained_motor():
    controller, c = make("bedc")
    await controller.start_notify()
    assert "mlily0_HelpGetUp" not in controller.held_control_options
    spec = next(s for s in controller.controller_button_specs if s.name == "Get Up")
    await spec.press_fn(controller)
    assert frames(c) == ["6e01003dac"]
    await controller.stop_notify()


async def test_motion_release_keeps_original_connected_client_after_replacement():
    controller, c = make()
    await controller.start_notify()
    old = c.client

    async def replace_link(*args, **kwargs):
        if old.write_gatt_char.await_count == 1:
            controller.on_disconnect()
            c.client = AsyncMock(is_connected=True)
            c.cancel_command.set()

    old.write_gatt_char.side_effect = replace_link
    await controller.hold_control("mlily0_HeadUp", 300)
    assert [bytes(call.args[1]).hex() for call in old.write_gatt_char.call_args_list] == [
        "6e01002493", "6e01006edd",
    ]
    c.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(("packet", "expected"), [
    ("6e200b02010201040206b5", [("deviceMassageHeadStrengthStatusEvent", 4), ("deviceMassageFootStrengthStatusEvent", 6)]),
    ("6e2009020202000370", [("deviceMassageModeStatusEvent", 3)]),
    ("6e200b0401020012345636", [("deviceRGBStripColorStatusEvent", {"rgba_bytes": [18, 52, 86, 255]})]),
])
def test_accepted_massage_and_rgb_fields_are_diagnostics(packet, expected):
    # Synthetic frames built from the accepted field offsets, not hardware captures.
    b = bytearray.fromhex(packet)
    b[-1] = sum(b[:-1]) & 0xFF
    events = []
    receiver = Receiver(lambda name, value: events.append((name, value)))
    receiver.feed(bytes(b))
    assert events == expected
    events.clear()
    b[-1] ^= 1
    receiver.feed(bytes(b))
    assert events == [] and receiver.rejection == "Invalid notification checksum"
