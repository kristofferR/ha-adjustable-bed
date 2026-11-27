"""Accepted Dynasty DM9000 1.0.4: complete frozen catalog and safe HA lifecycle."""

from __future__ import annotations

import asyncio
import gzip
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import (
    Selection,
    selected_operand,
    transition,
)
from custom_components.adjustable_bed.beds.richmat_classic.dynasty import (
    ALARM_COMBINATIONS,
    DynastyController,
    lamp_timeout,
)
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.beds.richmat_classic.receive import ReceiveState
from custom_components.adjustable_bed.beds.richmat_classic.requests import Request
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.richmat import RICHMAT_CLASSIC
from tests.test_richmat_classic import controller as classic_controller
from tests.test_richmat_classic import packets
from tests.test_richmat_classic_setup import _layouts, _setup

FIXTURES = Path(__file__).parent / "fixtures/dynasty"


def controller(app="dynasty", layout="6BRM", wire="FRAMED"):
    template, coord = classic_controller(app, layout, wire)
    ctrl = DynastyController(coord, app=app)
    ctrl._session = template._session
    return ctrl, coord


@pytest.fixture
def instant(monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_classic.controller import (
        RichmatClassicController,
    )

    async def wait(_ms, cancel):
        return not cancel.is_set()

    monkeypatch.setattr(RichmatClassicController, "_wait", staticmethod(wait))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


def test_all_19440_frozen_catalog_mode_rows_match_existing_codec():
    rows = json.loads(gzip.decompress((FIXTURES / "wire.json.gz").read_bytes()))
    assert len(rows) == 19440
    for proto, _layout, action, _phase, operand, mode, expected in rows:
        assert (
            p.control(bytes.fromhex(operand), "RAW" if proto == "P1" else "FRAMED", mode).hex()
            == expected
        ), action


def test_all_8144_declarations_have_their_own_catalog_values():
    catalog = load_catalog("dynasty")
    rows = json.loads(gzip.decompress((FIXTURES / "controls.json.gz").read_bytes()))
    assert len(rows) == sum(len(m.controls) for m in catalog.models.values()) == 8144
    assert len(catalog.models) == 558
    for layout, node, attrs in rows:
        button = next(c for c in catalog.models[layout].controls if c.node == node)
        assert (
            button.short,
            button.short_old,
            button.long,
            button.tag,
            button.alarm_clock,
        ) == tuple(
            attrs.get(k)
            for k in ("press_short", "press_short_old", "press_long", "tag", "alarm_clock")
        )
        assert button.status == int(attrs.get("press_status", 1))
        assert button.threshold_ms == int(attrs.get("press_long_time", 3000))
        # The old-long XML is evidence, never a working getter or save command.
        if "press_long_old" in attrs:
            assert selected_operand(button, "RAW", 3, Selection()) == p.decode_resource(
                attrs.get("press_long")
            )


def test_39_frozen_vectors_have_35_codec_parser_matches_and_four_product_exclusions():
    vectors = json.loads((FIXTURES / "vectors.json").read_text())
    assert len(vectors) == 39
    excluded = []
    for vector in vectors:
        args = vector["inputs"]
        kind = args["kind"]
        if kind == "command":
            actual = p.control(
                bytes((args["opcode"],)),
                "RAW" if args.get("raw") else "FRAMED",
                args.get("mode", 0),
            ).hex()
        elif kind == "frame":
            actual = codec.frame(*args["prefix"]).hex()
        elif kind == "rgb":
            actual = p.rgb(*args["rgb"]).hex()
        elif kind == "timer":
            actual = lamp_timeout(args["seconds"]).hex()
        elif kind == "alarm":
            actual = " / ".join(frame.hex() for frame in p.alarm(args["minutes"], args["opcode"]))
        elif kind == "aroma":
            actual = p.aroma(args["op"], args["n"]).hex()
        elif kind == "parser":
            state = ReceiveState(buffer=args["data"])
            actual = state._pack(args["length"]) or "NO_MATCH"
        else:
            # No production encoder is added for excluded network administration
            # or mapping reprogramming. The original reproducer verifies these.
            assert vector["protocol"] in ("P3", "P4")
            excluded.append(vector["id"])
            continue
        assert actual == vector["expected_bytes"], vector["id"]
    assert excluded == ["GROUP", "REBIND", "PROGRAM-ZERO", "PROGRAM-HEX-WINDOW"]


def test_setup_keeps_the_exact_app_layout_and_refuses_non_bed_or_unsafe_screens():
    assert len(_layouts("dynasty")) == 560  # 554 bed layouts plus six distinct manual aliases.
    assert (
        _setup({"protocol_variant": "dynasty", "product_type": " B6RU "})["product_type"] == "B6RM"
    )
    assert resolve_layout("dynasty", "MPE_HJ002-123", from_name=True) == "TWRM"
    assert resolve_layout("dynasty", "OTRM", russian=True) == "O0RM"
    for code in ("TEST", "RMCS", "WFRM", "FWRM", "A0RN"):
        with pytest.raises(ValueError):
            _setup({"protocol_variant": "dynasty", "product_type": code})


def test_cadence_is_profile_and_actual_name_specific():
    assert "dynasty" in RICHMAT_CLASSIC
    assert p.worker_interval("6BRM-123", "RAW", rise=True) == 170
    assert p.worker_interval("6BRM-123", "FRAMED", rise=True) == 150
    assert p.worker_interval("6BRM-123", "RAW") == 150
    assert p.worker_interval("TWRM", "RAW", rise=True) == 110


async def test_native_labels_selectors_card_and_timeout_are_not_inferred_readbacks(instant):
    ctrl, coord = controller("dynasty", "U3RM")
    assert not ctrl.supports_single_address_pairing
    assert ctrl.motor_control_specs == ()
    assert ctrl.controller_button_available("dynasty_query")
    assert (
        next(s for s in ctrl.controller_button_specs if s.key == "dynasty_query").card.section
        == "utility"
    )
    assert next(s for s in ctrl.controller_button_specs if s.key == "dynasty_query").diagnostic
    assert ctrl.controller_number_specs == ()
    ctrl._receive.menu.add("light")
    (number,) = ctrl.controller_number_specs
    assert number.card.section == "lighting"
    assert (number.native_max_value, number.native_unit_of_measurement) == (300, "s")
    ctrl._receive.menu.clear()
    with pytest.raises(ServiceValidationError):
        await number.set_fn(ctrl, 0)
    assert packets(coord) == []
    ctrl._receive.menu.add("light")
    await number.set_fn(ctrl, 0)
    await number.set_fn(ctrl, 300)
    assert packets(coord) == ["6e0b000079", "6e0b012ca6"]
    assert ctrl._preferences["lamp_seconds"] == 300
    saved = dict(ctrl.persisted_app_state)
    ctrl.restore_persisted_app_state(saved)
    assert ctrl._preferences["lamp_seconds"] == 300
    with pytest.raises(ServiceValidationError):
        ctrl.validate_richmat_classic_request(Request("lamp_slider", minutes=5))


@pytest.mark.parametrize("outcome", ("cancel", "event", "replacement", "none"))
async def test_timeout_state_tracks_delivered_write(instant, outcome):
    from custom_components.adjustable_bed.beds.richmat_classic.controller import LAMP_SECONDS
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )
    from tests.state_helpers import state_writer

    ctrl, coord = controller("dynasty", "U3RM")
    ctrl._receive.menu.add("light")
    ctrl._lamp_seconds = 5
    ctrl._preferences["lamp_seconds"] = 5
    state = {}
    coord.handle_controller_state_updates.side_effect = state_writer(state)
    original = ctrl._session
    assert original is not None
    replacement, _ = controller("dynasty", "U3RM")
    entered, finish = asyncio.Event(), asyncio.Event()
    context = CommandContext(
        object(),
        coord.cancel_command,
        0,
        "timeout",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )

    async def write(*_args, **_kwargs):
        entered.set()
        await finish.wait()

    async def operation():
        token = _CURRENT_COMMAND_CONTEXT.set(context)
        try:
            await ctrl.async_execute_richmat_classic_request(Request("lamp_timeout", seconds=300))
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)

    original.client.write_gatt_char.side_effect = write
    if outcome == "none":
        coord.cancel_command.set()
        await operation()
        original.client.write_gatt_char.assert_not_awaited()
    else:
        task = asyncio.create_task(operation())
        await entered.wait()
        if outcome == "cancel":
            task.cancel()
        elif outcome == "replacement":
            ctrl._session = replacement._session
        coord.cancel_command.set()
        finish.set()
        if outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    if outcome in ("cancel", "event"):
        assert state[LAMP_SECONDS] == 300
        assert ctrl._preferences["lamp_seconds"] == 300
    else:
        assert LAMP_SECONDS not in state
        assert ctrl._preferences["lamp_seconds"] == 5


@pytest.mark.parametrize("swap", (False, True))
async def test_bound_gesture_owns_original_link_mode_and_settles_write_before_release(
    instant, swap
):
    ctrl, coord = controller("dynasty", "6BRM")
    original = ctrl._session
    assert original is not None
    replacement, other = controller("dynasty", "6BRM", "RAW")
    entered, finish = asyncio.Event(), asyncio.Event()
    real_sleep = asyncio.tasks.__sleep0
    writes = []

    async def write(_char, packet, **_kw):
        writes.append(packet.hex())
        if len(writes) == 1:
            entered.set()
            await finish.wait()

    original.client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(ctrl.execute_action(1))
    await entered.wait()
    task.cancel()
    await real_sleep()
    assert not task.done() and writes == ["6e01002493"]
    if swap:
        ctrl._session = replacement._session
    ctrl._mode = 2
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert writes == (["6e01002493"] if swap else ["6e01002493", "6e01006edd"])
    assert packets(other) == []


async def test_query_and_settings_stay_on_admitted_link_and_use_typed_errors(instant):
    ctrl, coord = controller("dynasty", "A0RM")
    old = ctrl._session
    assert old is not None
    replacement, other = controller("dynasty", "A0RM")

    async def first(_char, packet, **_kw):
        ctrl._session = replacement._session

    old.client.write_gatt_char.side_effect = first
    with pytest.raises(ConnectionError):
        await ctrl.async_execute_richmat_classic_request(Request("query"))
    assert len(old.client.write_gatt_char.await_args_list) == 1
    assert packets(other) == []
    with pytest.raises(ServiceValidationError) as err:
        ctrl.validate_richmat_classic_request(Request("rgb", color=(1, 2, 3)))
    assert err.value.translation_key == "dynasty_request"


def test_alarm_combinations_and_u3rm_are_gated_by_declared_controls():
    from custom_components.adjustable_bed.beds.richmat_classic.dynasty import alarm_choices

    assert alarm_choices({"tv": 0x58}) == {"tv": 0x58}
    frozen = json.loads((FIXTURES / "alarm-functions.json").read_text())
    for branch in ("tv", "snore", "zg", "lounge", "m1", "m2", "m3"):
        row = frozen[branch]
        assert ALARM_COMBINATIONS[int(row["none"], 16)] == tuple(
            int(row[s], 16) for s in ("head_and_foot", "head", "foot")
        )
    for preset, encoded in ALARM_COMBINATIONS.items():
        choices = alarm_choices({"preset": preset, "h": 0x4C, "f": 0x4E})
        assert tuple(choices[f"preset_{s}"] for s in ("head_and_foot", "head", "foot")) == encoded
    ctrl, _ = controller("dynasty", "U3RM")
    up = next(c for c in ctrl._controls if c.tag == "51")
    assert [
        transition(
            up, "U3RM", "FRAMED", replace(Selection(), press_flag=flag), "DOWN", app="dynasty"
        ).payload
        for flag in ("53", "54", "55")
    ] == [b"\x3f", b"\x41", b"\x71"]


async def test_startup_writes_before_its_300ms_wait_and_raw_uses_actual_name(monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_classic import dynasty as module

    ctrl, coord = controller("dynasty", "6BRM")
    events = []

    async def write(_char, data, **_kw):
        events.append(data.hex())

    async def sleep(seconds):
        events.append(seconds)

    coord.client.write_gatt_char.side_effect = write
    monkeypatch.setattr(module, "select", lambda *_args, **_kw: ctrl._session)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    ctrl._device_name = "6BRM-real-name"
    await ctrl.start_notify()
    assert events == ["6e02010071", 0.3]
    assert ctrl._worker.tick_ms == 150
    assert ctrl._session is not None
    ctrl._session = replace(ctrl._session, wire="RAW")
    events.clear()
    await ctrl.start_notify()
    assert events == []
    assert ctrl._worker.tick_ms == 170


async def test_shared_native_alarm_uses_only_declared_preset_and_massage(instant):
    from homeassistant.util import dt as dt_util

    from custom_components.adjustable_bed.alarm import AlarmRequest

    layout = next(
        code
        for code, model in load_catalog("dynasty").models.items()
        if {"58", "4C", "4E"} <= {c.alarm_clock for c in model.controls}
    )
    ctrl, coord = controller("dynasty", layout)
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e09010078"))
    capability = ctrl.alarm_capability
    assert capability is not None and "tv" in capability.wake_actions
    await ctrl.configure_alarm(
        AlarmRequest(
            enabled=True,
            hour=10,
            minute=0,
            wake_action="tv",
            massage=True,
            massage_zone="both",
            reference_time=dt_util.now(),
        )
    )
    writes = [bytes.fromhex(packet) for packet in packets(coord)]
    assert len(writes) == 2 and writes[0][1] == 5
    assert writes[1][1] == 6 and writes[1][3] == 0x77
    assert all(codec.is_valid(packet) for packet in writes)


def test_seconds_timeout_is_refused_by_other_apps_during_preflight():
    ctrl, coord = classic_controller("avocadoecobase", "6BRM")
    with pytest.raises(ServiceValidationError):
        ctrl.validate_richmat_classic_request(Request("lamp_timeout", seconds=5))
    assert packets(coord) == []


def test_notifications_require_current_link_and_verified_checksum():
    ctrl, coord = controller("dynasty", "6BRM")
    session = ctrl._session
    assert session is not None
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e000300"))
    assert ctrl._receive.menu == set() and ctrl._light_on is None
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    assert "light" in ctrl._receive.menu and ctrl._light_on is True
    replacement, _ = controller("dynasty", "6BRM")
    ctrl._session = replacement._session
    ctrl._receive.menu.clear()
    ctrl._light_on = None
    ctrl._notification(session, session.notify, bytearray.fromhex("6e0e00037f"))
    assert ctrl._receive.menu == set() and ctrl._light_on is None
    assert packets(coord) == []


async def test_alarm_dialog_buzzer_has_its_frozen_direct_operand(instant):
    ctrl, coord = controller("dynasty", "6BRM")
    ctrl._receive.menu.add("alarm")
    await ctrl.async_execute_richmat_classic_request(Request("alarm", action="buzzer"))
    assert bytes.fromhex(packets(coord)[-1])[3] == 0x80
