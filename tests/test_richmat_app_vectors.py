"""All2094 accepted Richmat 4.2.0 literal fixtures, including original2046.

Responses are synthetic parser inputs where the freeze says so, not traffic.
"""

import gzip
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.richmat_app import protocol as p
from custom_components.adjustable_bed.beds.richmat_app.catalog import ACTIONS
from custom_components.adjustable_bed.beds.richmat_app.receive import common, extended
from custom_components.adjustable_bed.beds.richmat_app.sleep import Receiver, packet, parse_response
from custom_components.adjustable_bed.codec import richmat as codec

FIXTURE = Path(__file__).parent / "fixtures/richmat_app"
VECTORS = json.loads(gzip.decompress((FIXTURE / "wire.json.gz").read_bytes()))
SEMANTICS = json.loads(gzip.decompress((FIXTURE / "semantic.json.gz").read_bytes()))


def build(kind, args):
    unary = {
        "anti_snore_switch": (6, 1),
        "getoff_power": (6, 2),
        "blanket_mite": (13, 6),
        "blanket_power": (13, 1),
        "strip_power": (4, 4),
    }
    if kind in unary:
        return p.extended(*unary[kind], int(args[0]))
    if kind == "snore_intervention":
        return codec.frame(110, 19, 0, args[0])
    if kind == "repeat_delete":
        return p.delete_alarm(*args)
    if kind in ("clock_high", "clock_low"):
        return p.countdown(args[0], args[1] if len(args) > 1 else 0)[kind == "clock_high"]
    if kind in ("strip_groove", "strip_color_mode"):
        return p.extended(4, 5, 2 if kind == "strip_groove" else 1, *args)
    if kind == "white_noise_mode":
        return p.extended(9, 6, 1, *args)
    if kind == "white_noise_off":
        return p.extended(9, 6, 0)
    if kind == "strip_timer":
        return p.extended(4, 2, args[0] // 256, args[0] & 255)
    if kind == "strip_breathe":
        return p.extended(4, 6)
    if kind == "music_source":
        return p.music_source(*args)
    if kind in ("blanket_power_query", "sleep_name_query", "blanket_setting_query"):
        return p.QUERY[
            {
                "blanket_power_query": "blanket_power",
                "sleep_name_query": "sleep_name",
                "blanket_setting_query": "blanket_settings",
            }[kind]
        ]
    if kind == "blanket_sleep_query":
        return codec.record_20_len(13, 7, 0, args)
    if kind == "blanket_settings":
        return p.extended(13, 8, sum(int(v) << i for i, v in enumerate(args)))
    if kind == "blanket_mode":
        return p.extended(13, 5, *args)
    if kind == "blanket_delay":
        return p.blanket_delay(*args)
    if kind == "strip_rgb":
        return p.extended(4, 1, *args)
    if kind == "light_rgb_octets":
        return codec.rgb(*args)
    if kind == "light_time":
        return p.light_timer(*args)
    if kind == "repeat_add_raw_fields":
        return p.repeat_alarm(*args)
    if kind == "blanket_sleep_raw_selected_fields":
        # The frozen raw-field boundary permits values outside UI admission.
        return codec.record_20_len(13, 7, 1, args)
    if kind == "alarm_epoch_zone":
        return p.sync_time(
            datetime.fromtimestamp(args[0], UTC), datetime.now(timezone(timedelta(hours=args[1])))
        )[0]
    if kind == "alarm_local_parts":
        return codec.calendar(datetime(*args), build=codec.record_20_len)
    raise AssertionError(kind)


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_frozen_literal(v):
    q = v["inputs"]
    expected = bytes.fromhex(v["expected_bytes"])
    if "descriptor" in q:
        a = ACTIONS[q["descriptor"].split("@")[1]]
        result = codec.function(a[q["press"]], q["side"], action=a["enum"], single=q["nordic"])
    elif "builder" in q:
        result = codec.function(110, single=q["nordic"])
    elif "wire_cmd" in q:
        result = packet(q["sequence"], q["wire_cmd"], q["value"])
        assert result[14:].decode() == v["expected_json"]
    elif "enabled" in q:
        enabled = q["enabled"]
        value = (
            {"L": [int(enabled), 8, 4], "R": [int(enabled), 8, 4]} if enabled is not None else None
        )
        result = packet(
            q["sequence"], "s_antiSnore" if enabled is not None else "q_antiSnore", value
        )
    elif "current_command" in q:
        rx = Receiver("hj", current=q["current_command"])
        offset = 0
        result = None
        for size in q["chunk_lengths"]:
            decoded = rx.feed(expected[offset : offset + size])
            offset += size
            if decoded:
                result = decoded[1]
        assert result is not None
        value = result.get("val")
        update = None
        if isinstance(value, dict):
            sides = [value.get(s) for s in ("L", "R")]
            update = all(isinstance(side, list) and side and int(side[0]) == 1 for side in sides)
        assert {**result, "switch_update": update} == v["expected_state"]
        return
    elif q.get("layer") or "scope" in q:
        if q.get("layer") == "extended":
            actual = (
                {"rejected": "sum"}
                if q.get("sum_gate") and not codec.is_valid(expected)
                else extended(expected)
            )
        else:
            actual = common(expected)
        assert actual == v["expected_state"]
        return
    elif q["kind"] in ("repeat_alarm_list", "anti_snore_status", "blanket_all_status"):
        result = p.QUERY[
            {
                "repeat_alarm_list": "alarms",
                "anti_snore_status": "snore",
                "blanket_all_status": "blanket",
            }[q["kind"]]
        ]
    elif q["kind"] == "motor_v1":
        result = codec.packed_motor(q["no"], q["angle"])
    elif q["kind"] == "massage_v1":
        result = codec.packed_massage(q["massage1"], q["massage2"])
    elif q["kind"] == "groove":
        timer = extended(expected)["timer"]
        assert {"received_timer": timer, "page_seconds": timer * 60} == v["expected_state"]
        return
    elif q["kind"].startswith(("mite_", "power_")):
        result = p.extended(
            13, 6 if q["kind"].startswith("mite") else 1, int(q["kind"].endswith("_on"))
        )
    else:
        result = build(q["kind"], q["args"])
    assert result == expected
    if "expected_writes" in v:
        stride = q["mtu"] - 3
        chunks = [result[i : i + stride] for i in range(0, len(result), stride)]
        wanted = [
            bytes(x) if isinstance(x, list) else bytes.fromhex(x) for x in v["expected_writes"]
        ]
        assert chunks == wanted


@pytest.mark.parametrize("v", SEMANTICS)
def test_semantic_contract(v):
    kind = v["kind"]
    if kind == "duration":
        actual = p.valid_sleep_duration(tuple(v["start"]), tuple(v["end"]))
    elif kind == "positive_delay_hydration":
        # Hydration is local, normal writes still enforce the picker range.
        actual = v["value"] if v["value"] > 0 else 5
    elif kind == "alarm_hour":
        actual = v["hour"] % 12 + (12 if v["period"] == "PM" else 0)
    elif kind == "opacity":
        actual = list(p.opacity(tuple(v["color"][:3]), v["value"])) + [v["color"][3]]
    else:
        if "expected_error" in v:
            with pytest.raises(ValueError):
                parse_response(v["value"], "s_time", v["variant"].removeprefix("new_"))
            return
        actual = parse_response(v["value"], "s_time", v["variant"].removeprefix("new_"))
    assert actual == v["expected"]
