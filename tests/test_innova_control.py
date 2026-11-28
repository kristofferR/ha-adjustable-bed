"""Innova Control 1.1.0 literals, catalog and captured-session behavior."""

import gzip
import json
import re
from pathlib import Path

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.innova_control import (
    InnovaControlController,
)
from custom_components.adjustable_bed.beds.richmat_classic.profiles import (
    load_catalog,
    resolve_layout,
)
from custom_components.adjustable_bed.beds.richmat_classic.resource_protocol import Request
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import innova_control
from tests.test_richmat_classic import controller as classic_controller
from tests.test_richmat_classic import instant as instant
from tests.test_richmat_classic import packets


def accepted():
    return json.loads(
        gzip.decompress(
            (Path(__file__).parent / "fixtures/innova_control/accepted.json.gz").read_bytes()
        )
    )


def test_every_frozen_literal_against_existing_codec():
    vectors = accepted()["vectors"]
    for row in vectors:
        expected = row["expected_bytes"].replace(" | ", "")
        if row["id"] == "V16":
            # Factory motor programming uses a different, excluded format.
            assert row["protocol"] == "P4"
            continue
        if row["id"] == "V14":
            result = codec.rgb(0x12, 0x34, 0x56)
        elif row["id"] == "V15":
            result = b"".join(codec.countdown(1440, 0x58))
        elif row["id"] == "V17":
            result = codec.local_group("1234")
        elif row["protocol"] == "P1":
            result = codec.encode("nordic", int(expected, 16))
        else:
            result = codec.frame(*bytes.fromhex(expected)[:-1])
        assert result.hex() == expected, row["id"]
    rows = accepted()["commands"]
    assert {key: len(value) for key, value in rows.items()} == {"P1": 250, "P2": 199}
    for protocol, commands in rows.items():
        for row in commands:
            value = row["bytes"]
            if protocol == "P1" and re.fullmatch("[0-9a-f]+", value):
                assert codec.encode("nordic", int(value, 16)).hex() == value
            elif protocol == "P2" and (match := re.search(r"mode=0 example ([0-9a-f]+)", value)):
                literal = match[1]
                assert codec.command(int(literal[6:8], 16)).hex() == literal


def controller(layout="6BRM", wire="FRAMED"):
    base, coord = classic_controller("innova2", layout, wire)
    ctrl = InnovaControlController(coord)
    ctrl._session = base._session
    return ctrl, coord


def test_full_catalog_preserves_every_binding_and_mode():
    catalog = load_catalog("innova2")
    assert len(catalog.models) == 559
    assert len(innova_control.LAYOUTS) == 558
    for v in accepted()["variants"]:
        model = catalog.models[v["id"].upper()]
        nodes = [n for n in v["nodes"] if n["element"].endswith(".RichButton")]
        assert len(model.controls) == len(nodes)
        for c, n in zip(model.controls, nodes, strict=True):
            d = n["resolved"]
            assert c.node == n["node"]
            assert (c.short, c.short_old, c.long, c.tag, c.extra, c.alarm_clock) == tuple(
                d.get(k)
                for k in (
                    "press_short",
                    "press_short_old",
                    "press_long",
                    "tag",
                    "extra",
                    "alarm_clock",
                )
            )
            assert c.status == int(d.get("press_status", 0))
            assert c.threshold_ms == int(d.get("press_long_time", 3000))
        modes = tuple(
            i
            for i in range(3)
            if any(n["resolved"].get("id") == "@+id/tvMode" + str(i + 1) for n in v["nodes"])
        ) or (0,)
        assert model.modes == modes


def test_all_command_classes_reconcile_with_actual_bound_operands():
    from custom_components.adjustable_bed.beds.richmat_classic.caller import (
        Selection,
        selected_operand,
    )

    catalog = load_catalog("innova2")
    checked = 0
    for protocol, rows in accepted()["commands"].items():
        wire = "RAW" if protocol == "P1" else "FRAMED"
        for row in rows:
            value = row["bytes"]
            if protocol == "P1" and re.fullmatch("[0-9a-f]+", value):
                literal = bytes.fromhex(value)
            elif protocol == "P2" and (match := re.search(r"mode=0 example ([0-9a-f]+)", value)):
                literal = bytes.fromhex(match[1])[3:4]
            else:
                assert row["dynamic_selection"]  # Axis selector, tested below.
                continue
            for evidence in row["evidence"]:
                match = re.search(r"/f([^/]+)\.xml XML node (\d+)", evidence)
                if match is None:
                    continue
                c = next(
                    c for c in catalog.models[match[1].upper()].controls if c.node == int(match[2])
                )
                arg = (
                    3
                    if row["timing"]["phase"] == "long"
                    else 2
                    if row["timing"]["mode"] == "3"
                    else int(row["timing"]["mode"])
                )
                possible = [
                    selected_operand(c, wire, arg, Selection(press_flag=flag, head=head))
                    for flag in ("53", "54", "55")
                    for head in (True, False)
                ]
                assert literal in possible, (row["action"], evidence, possible)
                checked += 1
    assert checked == 19112  # Four dynamic axis bindings are exercised separately.


def test_setup_aliases_and_side_profile_are_app_local():
    from custom_components.adjustable_bed.setup_questions import (
        _classic_errors,
        _classic_layouts,
        _classic_normalize,
    )

    data = {"protocol_variant": "innova2"}
    assert innova_control.scan_matches("200IV2x")
    assert not innova_control.scan_matches(" L&P ADJBED")
    assert resolve_layout("innova2", "200IV2x", from_name=True) == "A8RM"
    assert resolve_layout("innova2", "OTRM", russian=True) == "O0RM"
    assert _classic_normalize(data, {"product_type": "ZRS3:APRM"})["product_type"] == "APRM"
    choices = _classic_layouts(data)
    assert "COOL" not in choices  # Alias for the excluded QRRM layout.
    for choice in choices:
        normalized = _classic_normalize(data, {"product_type": choice})
        assert not _classic_errors({**data, **normalized}), choice
    for layout in innova_control.EXCLUDED_LAYOUTS:
        assert layout not in _classic_layouts(data)
        assert _classic_errors({**data, "product_type": layout})


async def test_selected_modes_and_programming_use_only_own_catalog(instant):
    ctrl, coord = controller("BTRM")
    ctrl._select("mode", "2")
    await ctrl.execute_action(next(c.node for c in ctrl._controls if c.short == "24"))
    assert set(packets(coord)[:-1]) == {"6e01022495"}
    assert packets(coord)[-1] == "6e01026edf"
    ctrl, coord = controller("E3RM")
    ctrl._select("program", "armed")
    await ctrl.execute_action(1)
    assert packets(coord) == ["6e01002b9a", "6e01006edd"]
    assert not ctrl._selection.armed
    assert not ctrl.supports_single_address_pairing
    ctrl, coord = controller("U3RM")
    ctrl._selection = __import__("dataclasses").replace(ctrl._selection, press_flag="55")
    node = next(c.node for c in ctrl._controls if c.tag == "51")
    await ctrl.execute_action(node)
    assert set(packets(coord)[:-1]) == {"6e010071e0"}
    assert packets(coord)[-1] == "6e01006edd"


async def test_direct_settings_on_raw_link_and_exact_slider(instant):
    ctrl, coord = controller("D9RM", "RAW")
    ctrl._receive.light_capable = ctrl._receive.aroma_capable = True
    await ctrl.execute_request(Request("lamp_timeout", seconds=300))
    await ctrl.execute_request(Request("rgb", color=(0x12, 0x34, 0x56)))
    await ctrl.execute_request(Request("aroma", aroma_times=(1, 60, 12)))
    for i in range(6):
        await ctrl.execute_request(Request("massage_timer", progress=i))
    assert packets(coord) == [
        "6e0b012ca6",
        "6e0cff128b6e0d345605",
        "6e1b00018a",
        "6e1c003cc6",
        "6e1d000c97",
        *[codec.command(v).hex() for v in (0x8B, 1, 0x5F, 0x63, 4, 0x61)],
    ]
    assert not ctrl.supports_massage_timer
    assert any(s.key == "innova_control_timer_progress" for s in ctrl.controller_select_specs)


async def test_notify_parser_fragmentation_capabilities_and_stale_link(instant):
    from dataclasses import replace

    ctrl, _ = controller("YGRM")
    old = ctrl._session
    for value in ("6e0901", "0078", "6e0e00037f", "6e1a000189", "6e07010177"):
        ctrl._notification(old, None, bytearray.fromhex(value))
    assert ctrl._receive.alarm_capable and ctrl._receive.aroma_capable
    assert ctrl._receive.light_capable and ctrl._receive.light_on_seen
    assert ctrl._receive.height_cm is ctrl._receive.alarm_enabled is None
    ctrl._session = replace(old)
    ctrl.on_disconnect()
    ctrl._notification(old, None, bytearray.fromhex("6e0e00037f"))
    assert not ctrl._receive.light_capable


async def test_startup_queries_after_notify_and_framed_init(instant):
    from tests.test_richmat_classic_transport import Services, route

    for index, interval in ((0, 150), (1, 150), (2, 170), (3, 150)):
        ctrl, coord = controller()
        ctrl._device_name = "6BRM1234"
        coord.client.services = Services([route(index)])
        events = []

        async def notify(*args, events=events, **kwargs):
            events.append("notify")

        async def write(char, packet, events=events, **kwargs):
            events.append(packet.hex())

        coord.client.start_notify.side_effect = notify
        coord.client.write_gatt_char.side_effect = write
        await ctrl.start_notify()
        assert ctrl._worker.tick_ms == interval
        assert events == [
            "notify",
            *(["6e02010071"] if index != 2 else []),
            "6e0a000179",
            "6e1a000088",
        ]


async def test_cancellation_drains_write_then_releases_original_session():
    import asyncio

    from tests.hold_lease_wire import virtual_clock

    ctrl, coord = controller()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(char, packet, **kwargs):
        if packet != p.release("FRAMED"):
            entered.set()
            await finish.wait()

    coord.client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(ctrl.execute_action(1))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert len(packets(coord)) == 1
        finish.set()
        import pytest

        with pytest.raises(asyncio.CancelledError):
            await task
    assert packets(coord) == ["6e01002493", "6e01006edd"]
