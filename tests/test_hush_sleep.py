"""Artifact-bound Hush sleep wire, complete schema and callback ownership."""

from __future__ import annotations

import asyncio
import gzip
import json
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.casper_base.protocol import Request
from custom_components.adjustable_bed.beds.hush_sleep.controller import HushSleepController
from custom_components.adjustable_bed.beds.hush_sleep.protocol import (
    HushReceive,
    build,
    new_day_layout,
    parse,
    report,
)
from custom_components.adjustable_bed.beds.hush_sleep.schema import SCHEMAS
from tests.test_hush_base import hush

VECTORS = json.loads((Path(__file__).parent / "fixtures/hush_sleep_commands.json").read_text())


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    real = asyncio.sleep

    async def tick(_):
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", tick)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["protocol"] + "-" + v["action"])
def test_accepted_command_examples(vector):
    kind = "mm" if vector["protocol"] == "P1" else "sxb"
    obj = json.loads(vector["example_json"])
    val = obj["val"]
    action = vector["action"]
    # s_init is independently preserved as an OTA exclusion, not exposed by HA.
    r = Request(
        "sensor_report",
        part=12 if kind == "sxb" else 2,
        report_type=1,
        year=2026,
        month=11,
        day=3,
        enabled=True,
    )
    if action == "s_antiSnore":
        r = Request("sensor_anti_snore", enabled=bool(val["L"][0]))
    if action == "s_part":
        r = Request("sensor_part", part=val)
    if action in ("q_report", "q_report_allow"):
        r = Request(
            "sensor_report",
            part=val.get("part", 12),
            report_type=val.get("type", 1),
            year=val.get("y", 2026),
            month=val.get("m", 11),
            day=val.get("d", 3),
        )
    ts = val.get("ts", 0) if isinstance(val, dict) else 0
    zone = val.get("tz", val.get("utc", 0)) if isinstance(val, dict) else 0
    packet = build(kind, action, obj["id"], r, ts=ts, zone=zone)
    assert packet.hex() == vector["example_hex"]


@pytest.mark.parametrize("schema", SCHEMAS)
def test_all_source_schema_fields_and_required_types(schema):
    # Each generated contract participates, including nested/multi report fields.
    fields = SCHEMAS[schema]
    value = {}
    for key, typ, nullable, _default, mode, _conversion, _nested, _element in fields:
        if nullable or mode == "lazy_num_list":
            continue
        value[key] = (
            {}
            if mode == "bean"
            else []
            if "list" in mode
            else ""
            if typ.startswith("String")
            else 0
        )
    # Required nested beans may carry their own required fields; those boundaries
    # are rejected rather than silently filled from an unrelated model.
    try:
        decoded = parse(schema, value)
    except ValueError:
        assert any(mode == "bean" and not nullable for _, _, nullable, _, mode, _, _, _ in fields)
    else:
        assert list(decoded) == [f[0] for f in fields]


@pytest.mark.parametrize("wrapper", [gzip.compress, zlib.compress])
def test_compressed_multi_report_and_typed_fields(wrapper):
    data = {
        "algorithmVersion": "0.0.3",
        "day": "2026-11-03",
        "sleep_data": [{"session_id": 7, "stage": [{"start": 1, "end": 2, "status": 3}]}],
        "calib_time_arr": [4],
        "situp_time_arr": [8],
    }
    rx = HushReceive("sxb")
    rx.reset("q_report_allow")
    payload = wrapper(json.dumps(data).encode())
    rx.report_size = len(payload)
    decoded = rx.feed(bytes(14) + payload)
    result = report(decoded, kind="sxb", monthly=False)
    assert isinstance(result, dict)
    sleep_data = result["sleep_data"]
    assert isinstance(sleep_data, list) and isinstance(sleep_data[0], dict)
    assert sleep_data[0]["session_id"] == 7
    assert result["calib_time_arr"] == [4]
    assert not new_day_layout("1.2.3")
    with pytest.raises(ValueError):
        report({"algorithmVersion": "bad"}, kind="sxb", monthly=False)
    with pytest.raises(ValueError):
        parse("0x7adb98", {"id": True, "cmd": "s_part"})
    assert parse("0x7b05bc", {"value": -3.8})["value"] == -3


async def test_sensor_settings_and_part_domains():
    ctrl, c = hush(kind="sxb")
    assert isinstance(ctrl, HushSleepController)
    ctrl._receive.reset("q_sens")
    ctrl._consume({"id": 1, "cmd": "q_sens", "val": {"L": [2.9], "R": [0]}})
    assert c.controller_state["hush_sleep_sensitivity"] == {"L": 1, "R": -1}
    ctrl._receive.reset("q_antiSnore")
    ctrl._consume({"val": {"L": [1, 8, 4], "R": [0, 8, 4]}})
    assert c.controller_state["hush_sleep_anti_snore"] == {"L": [1, 8, 4], "R": [0, 8, 4]}
    ctrl.validate_casper_base_request(Request("sensor_report", part=1))
    ctrl.validate_casper_base_request(Request("sensor_part", part=12))
    with pytest.raises(ValueError):
        ctrl.validate_casper_base_request(Request("sensor_report", part=12))
    with pytest.raises(ValueError):
        ctrl.validate_casper_base_request(Request("sensor_info"))


async def test_sleep_fragment_connection_loss_does_not_retarget():
    ctrl, c = hush(kind="sxb")
    assert isinstance(ctrl, HushSleepController)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def disconnected(*_args, **_kwargs):
        ctrl.on_disconnect()

    c.client.write_gatt_char.side_effect = disconnected
    with pytest.raises(ConnectionError):
        await ctrl._send("q_sens", Request("sensor_sensitivity"))
    assert c.client.write_gatt_char.await_count == 1


async def test_intent_survives_link_loss_but_explicit_release_clears():
    ctrl, c = hush(kind="mm")
    ctrl.restore_persisted_app_state({"live_requested": True})
    ctrl.on_disconnect()
    assert ctrl.requests_connection_recovery
    assert ctrl.persisted_app_state == {"live_requested": True}
    ctrl.on_connection_release("manual")
    assert not ctrl.requests_connection_recovery
    new, _ = hush(kind="mm")
    new.restore_persisted_app_state(ctrl.persisted_app_state)
    assert not new.requests_connection_recovery


async def test_delayed_handshake_uses_actual_admitted_controller():
    ctrl, c = hush(kind="sxb")
    assert isinstance(ctrl, HushSleepController)
    captured = []
    c.hass.async_create_background_task.side_effect = lambda coro, _: asyncio.create_task(coro)

    async def admit(command, **kwargs):
        captured.append(command)

    c.async_execute_controller_command = AsyncMock(side_effect=admit)
    ctrl._send = AsyncMock()
    ctrl._schedule("q_time")
    await asyncio.gather(*ctrl._followups)
    await captured[0](MagicMock())
    ctrl._send.assert_not_awaited()
    await captured[0](ctrl)
    ctrl._send.assert_awaited_once()
