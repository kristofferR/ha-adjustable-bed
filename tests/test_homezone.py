"""Home Zone 1.0.3 frozen frames/catalog and physical-session behavior."""

import asyncio
import gzip
import json
from dataclasses import replace
from datetime import UTC
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic import rise
from custom_components.adjustable_bed.beds.richmat_classic.homezone import (
    HomeZoneController,
    HomeZoneReceive,
)
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.beds.richmat_classic.resource_protocol import Request
from custom_components.adjustable_bed.profiles import homezone
from tests.test_richmat_classic import controller as classic_controller
from tests.test_richmat_classic import instant as instant
from tests.test_richmat_classic import packets


def accepted():
    return json.loads(
        gzip.decompress((Path(__file__).parent / "fixtures/homezone/accepted.json.gz").read_bytes())
    )


def controller(layout="6BRM", wire="FRAMED"):
    base, coord = classic_controller("homezone", layout, wire)
    ctrl = HomeZoneController(coord)
    ctrl._session = base._session
    return ctrl, coord


def test_every_frozen_builder_matches_existing_codec():
    vectors = accepted()["vectors"]
    assert len(vectors) == 18
    for row in vectors:
        a = row["inputs"]
        kind = a["kind"]
        if kind == "frame":
            result = p.direct(*a["fields"])
        elif kind == "control":
            result = p.control(bytes((a["code"],)), "RAW" if a["raw"] else "FRAMED", a["mode"])
        elif kind == "rgb":
            result = p.rgb(*a["rgb"])
        elif kind == "aroma":
            result = p.aroma(a["op"], a["value"])
        elif kind == "alarm":
            result = b"".join(p.alarm(a["delay"], a["code"]))
        else:
            assert kind == "rmcs"  # EXCLUDED factory motor/radio mapping.
            continue
        assert result.hex() == row["expected_bytes"], row["id"]


def test_full_catalog_preserves_every_frozen_binding_and_modes():
    variants = accepted()["variants"]
    catalog = load_catalog("homezone")
    assert len(variants) == len(catalog.models) == 559
    assert sum(len(v["elements"]) for v in variants) == 8148
    for v in variants:
        model = catalog.models[v["id"]]
        assert model.modes == tuple(v["mode_values"])
        assert len(model.controls) == len(v["elements"])
        for c, e in zip(model.controls, v["elements"], strict=True):
            a = e["resolved"]
            assert c.node == e["index"]
            assert (c.short, c.short_old, c.long, c.tag, c.extra, c.alarm_clock) == tuple(
                a.get(k)
                for k in (
                    "press_short",
                    "press_short_old",
                    "press_long",
                    "tag",
                    "extra",
                    "alarm_clock",
                )
            )
            assert c.status == int(a.get("press_status", 0))
            assert c.threshold_ms == int(a.get("press_long_time", 3000))
            for wire, operand in [("RAW", c.short_old or c.short), ("FRAMED", c.short)]:
                if operand:
                    b = bytes.fromhex(operand)
                    for mode in model.modes:
                        result = p.control(b, wire, mode)
                        assert result == (
                            b
                            if wire == "RAW"
                            else bytes((110, 1, mode, b[0], (111 + mode + b[0]) & 255))
                        )


def test_frozen_alarm_combinations_are_exact():
    for row in accepted()["alarms"]["combined"]:
        if "action_code" in row:
            assert (
                rise.alarm_action(
                    {"bed": int(row["preset_byte"], 16), "massage": 0x4C}, ("bed", "massage")
                )
                == 0x80
            )
        else:
            for tag, code in [
                ("massage_all", 0x5D),
                ("massage_head", 0x4C),
                ("massage_foot", 0x4E),
            ]:
                assert rise.alarm_action(
                    {"bed": int(row["preset_byte"], 16), "massage": code}, ("bed", "massage")
                ) == int(row[tag]["action_code"], 16)


def test_setup_scope_and_aliases_are_explicit():
    from custom_components.adjustable_bed.setup_questions import (
        _classic_errors,
        _classic_layouts,
        _classic_normalize,
    )

    data = {"protocol_variant": "homezone"}
    assert "homezone" in __import__(
        "custom_components.adjustable_bed.beds.richmat_classic.discovery",
        fromlist=["matching_apps"],
    ).matching_apps("6BRM1234")
    for code in homezone.EXCLUDED_LAYOUTS:
        assert code not in _classic_layouts(data)
        assert _classic_errors({**data, "product_type": code})
        with pytest.raises(ValueError):
            controller(code)
    assert _classic_normalize(data, {"product_type": "ZRS3:APRM"})["product_type"] == "APRM"
    assert resolve_layout("homezone", "200IV2ABCD", from_name=True) == "A8RM"
    assert resolve_layout("homezone", "OTRM", russian=True) == "O0RM"
    assert not homezone.scan_matches("  A")


@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_bound_motor_and_combination_save_cleanup(wire, instant):
    ctrl, coord = controller(wire=wire)
    await ctrl.execute_action(1)
    assert packets(coord)[-1] == p.release(wire).hex()
    assert set(packets(coord)[:-1]) == {p.control(b"4" if wire == "RAW" else b"$", wire).hex()}
    ctrl, coord = controller("E3RM", wire)
    ctrl._select("program", "armed")
    await ctrl.execute_action(1)
    assert packets(coord) == [p.control(b"+", wire).hex(), p.release(wire).hex()]
    assert not ctrl._selection.armed
    assert ctrl.execution.concurrent == frozenset()


async def test_utilities_remain_framed_on_raw_link(instant):
    ctrl, coord = controller("D9RM", "RAW")
    ctrl._receive.light_capable = ctrl._receive.aroma_capable = True
    for seconds in (0, 255, 256, 300):
        await ctrl.execute_request(Request("lamp_timeout", seconds=seconds))
    await ctrl.execute_request(Request("rgb", color=(1, 221, 255)))
    await ctrl.execute_request(Request("aroma", aroma_times=(60, 60, 12)))
    await ctrl.execute_request(Request("massage_timer", progress=0))
    assert packets(coord) == [
        "6e0b000079",
        "6e0b00ff78",
        "6e0b01007a",
        "6e0b012ca6",
        "6e0cff017a6e0dddff57",
        "6e1b003cc5",
        "6e1c003cc6",
        "6e1d000c97",
        "6e01008bfa",
    ]
    with pytest.raises(ValueError):
        await ctrl.execute_request(Request("aroma", aroma_times=(61, 1, 1)))
    with pytest.raises(ValueError):
        await ctrl.execute_request(Request("bed_command", command="head_up"))


def test_parser_capabilities_are_link_local_no_positions_or_schedule():
    receive = HomeZoneReceive()
    receive.feed(bytes.fromhex("6e0901"), app="homezone", layout="6BRM")
    receive.feed(bytes.fromhex("0078"), app="homezone", layout="6BRM")
    assert receive.alarm_capable
    for value in ["6e0e00037f", "6e1a000189", "6e07010177"]:
        receive.feed(bytes.fromhex(value), app="homezone", layout="6BRM")
    assert receive.light_capable and receive.aroma_capable
    assert receive.alarm_enabled is receive.height_cm is None
    receive.feed(bytes.fromhex("0000000000"), app="homezone", layout="6BRM")
    assert receive.buffer == ""
    ctrl, coord = controller()
    ctrl._receive = receive
    ctrl.on_disconnect()
    assert not ctrl._receive.alarm_capable and not ctrl._receive.light_capable
    assert ctrl.persisted_app_state == {}


async def test_inflight_write_settles_before_release_on_cancellation(instant):
    ctrl, coord = controller()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(char, packet, **kwargs):
        if packet != p.release("FRAMED"):
            entered.set()
            await finish.wait()

    coord.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(ctrl.execute_action(1))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert len(packets(coord)) == 1
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert packets(coord) == ["6e01002493", "6e01006edd"]


async def test_replacement_link_never_receives_prior_command_or_release(instant):
    ctrl, coord = controller()
    old = ctrl._session

    async def write(char, packet, **kwargs):
        if packet != p.release("FRAMED"):
            ctrl._session = replace(old)
            coord.cancel_command.set()

    coord.client.write_gatt_char.side_effect = write
    await ctrl.execute_action(1)
    assert packets(coord) == ["6e01002493"]


@pytest.mark.parametrize("route_index,expected_interval", [(0, 150), (1, 150), (2, 170), (3, 150)])
async def test_startup_subscribes_before_delayed_framed_initialization(
    route_index, expected_interval, instant
):
    from tests.test_richmat_classic_transport import Services, route

    ctrl, coord = controller()
    ctrl._device_name = "6BRM1234"
    coord.client.services = Services([route(route_index)])
    events = []

    async def notify(*args, **kwargs):
        events.append("notify")

    async def write(char, packet, **kwargs):
        events.append(packet.hex())

    coord.client.start_notify.side_effect = notify
    coord.client.write_gatt_char.side_effect = write
    await ctrl.start_notify()
    assert ctrl._worker.tick_ms == expected_interval
    assert events == (["notify"] if route_index == 2 else ["notify", "6e02010071"])
    old = ctrl._session
    ctrl.on_disconnect()
    ctrl._notification(old, None, bytearray.fromhex("6e1a000189"))
    assert not ctrl._receive.aroma_capable


def test_every_normalized_ordinary_command_row_reconciles_with_catalog():
    import re

    from custom_components.adjustable_bed.beds.richmat_classic.caller import (
        Selection,
        selected_operand,
    )

    catalog = load_catalog("homezone")
    counts = {}
    for protocol, rows in accepted()["commands"].items():
        counts[protocol] = len(rows)
        for row in rows:
            if not re.fullmatch(protocol + r"-C\d+", row["id"]):
                continue  # Dedicated utilities/hold/memory rows have separate tests.
            if protocol == "P1":
                literal = bytes.fromhex(row["bytes"])
            else:
                match = re.match(r"6e 01 mode ([0-9a-f]{2}) ", row["bytes"])
                if match is None:
                    continue  # Direct settings builder, covered by frozen vectors.
                literal = bytes.fromhex(match[1])
            wire = "RAW" if protocol == "P1" else "FRAMED"
            for binding in row.get("bindings", []):
                layout, node = binding.split(":")
                c = next(c for c in catalog.models[layout].controls if c.node == int(node))
                # Frozen rows include companion bindings too. Reconciliation
                # checks their bytes without enabling their excluded gestures.
                possible = [
                    selected_operand(c, wire, arg, Selection(press_flag=flag, head=head))
                    for arg in (1, 2, 3, 10)
                    for flag in ("53", "54", "55")
                    for head in (True, False)
                ]
                assert literal in possible, (row["id"], binding)
    assert counts == {"P1": 252, "P2": 217, "P3": 1}


async def test_shared_alarm_uses_layout_choices_and_countdown(instant, monkeypatch):
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest
    from custom_components.adjustable_bed.beds.richmat_classic import homezone as bed

    ctrl, coord = controller("YGRM")
    monkeypatch.setattr(bed.dt_util, "now", lambda: datetime(2026, 1, 2, 8, 0, tzinfo=UTC))
    request = AlarmRequest(
        enabled=True,
        hour=6,
        minute=0,
        wake_action="zero_g",
        reference_time=datetime(2026, 1, 2, 6, 0, tzinfo=UTC),
    )
    ctrl.validate_alarm(request)
    await ctrl.check_alarm(request)
    await ctrl.configure_alarm(request)
    assert packets(coord) == [packet.hex() for packet in p.alarm(1320, 0x45)]
    coord.client.write_gatt_char.reset_mock()
    await ctrl.configure_alarm(
        AlarmRequest(enabled=False, reference_time=datetime(2026, 1, 2, 6, 0, tzinfo=UTC))
    )
    assert packets(coord) == [packet.hex() for packet in p.alarm(0, 0)]
    assert ctrl._receive.alarm_enabled is None


def test_dead_once_long_binding_and_click_selectors_are_not_commands():
    ctrl, _ = controller("FRRM")
    assert "richmat_classic_11" not in {s.key for s in ctrl.controller_button_specs}
    ctrl, _ = controller("BRRM")
    keys = {s.key for s in ctrl.controller_button_specs}
    assert all(
        f"richmat_classic_{c.node}" not in keys
        for c in ctrl._controls
        if c.view_id in ("btnRelease", "btnHold")
    )
    assert any(s.key == "richmat_classic_hold" for s in ctrl.controller_select_specs)
