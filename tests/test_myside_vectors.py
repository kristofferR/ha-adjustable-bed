"""All 96 accepted My Side 1.0.6 literals against the existing Richmat codec.

Builder-only candidates remain fixtures, never capabilities. These are static
APK derivations, not hardware traffic. Transport order is tested with handles.
"""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.beds.myside.protocol import parse
from custom_components.adjustable_bed.beds.richmat.transport import select_app_link
from custom_components.adjustable_bed.codec import richmat as codec

VECTORS = json.loads((Path(__file__).parent / "fixtures/myside/vectors.json").read_text())
ROUTES = ("n1", "w1", "w2", "w3", "w4", "w5")


def mask(days, enabled):
    names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    return int(enabled) | (
        0 if "once" in days else sum(1 << (7 - i) for i, d in enumerate(names) if d in days)
    )


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_existing_codec(v):
    q = v["inputs"]
    kind = q["builder"]
    expected = bytes.fromhex(v["expected_bytes"])
    if kind == "ordinary":
        actual = codec.function(q["opcode"], q["side"], single=q["nordic"])
    elif kind == "extended":
        actual = codec.extended(*q["payload"])
    elif kind == "prefix":
        actual = codec.frame(*q["prefix"])
    elif kind in ("clock_low", "clock_high"):
        actual = codec.countdown(q["minutes"], q.get("parameter", 0))[kind == "clock_high"]
    elif kind == "calendar":
        actual = codec.calendar(datetime(*q["parts"]))
    elif kind == "literal_capability":
        from custom_components.adjustable_bed.beds.richmat_app.receive import EXACT

        assert (
            EXACT[expected.hex()]
            == {"alarm": "clock_available", "light": "light_available", "aroma": "aroma_available"}[
                q["event"]
            ]
        )
        return
    elif kind == "parse_extended":
        reply = parse(expected)
        assert reply is not None
        wanted = v["expected_parsed"]
        if wanted["event"] == "sleep_name":
            assert reply.name == wanted["name"]
        else:
            assert [
                reply.alarm.number,
                reply.alarm.unknown,
                reply.alarm.hour,
                reply.alarm.minute,
                reply.alarm.opcode,
                reply.alarm.repeat,
            ] == [wanted[k] for k in ("number", "unknown", "hour", "minute", "opcode", "repeat")]
            assert reply.event == wanted["event"]
        assert codec.is_valid(expected) and expected[2] == len(expected)
        return
    elif kind in ("alarm", "alarm_edit_projection", "alarm_enable_projection"):
        if kind == "alarm":
            fields = [q[k] for k in ("number", "unknown", "hour", "minute", "opcode")]
            repeat = mask(q["days"], q["enabled"])
        else:
            old = q["existing"]
            bean = (
                {
                    **old,
                    "unknown": 0,
                    **{k: q[k] for k in ("hour", "minute", "opcode")},
                    "repeat": mask(q["days"], q["enabled"]),
                }
                if kind == "alarm_edit_projection"
                else {**old, "repeat": old["repeat"] & 254 | int(q["enabled"])}
            )
            assert bean == v["expected_projection"]
            fields = [bean[k] for k in ("number", "unknown", "hour", "minute", "opcode")]
            repeat = bean["repeat"]
        actual = codec.record(5, 1, 1, (*fields, repeat))
    elif kind == "gatt_order_projection":
        services = []
        for service in q["services"]:
            key = "n1" if service["accepted_enum"] == "N" else service["accepted_enum"].lower()
            write, notify = service["write"], service["notify"]
            services.append(
                SimpleNamespace(
                    uuid=codec.TRANSPORTS[key].service_uuid,
                    characteristics=[
                        SimpleNamespace(
                            uuid=write["uuid"],
                            properties=[
                                "write",
                                *(["write-without-response"] if write["without_response"] else []),
                            ],
                        ),
                        SimpleNamespace(uuid=notify["uuid"], properties=["notify"]),
                    ],
                )
            )
        selected = select_app_link(SimpleNamespace(services=services), ROUTES)
        wanted = v["expected_selection"]
        assert selected.tx.uuid == wanted["write_uuid"]
        assert selected.rx.uuid == wanted["notify_uuid"]
        assert ("write-without-response" in selected.tx.properties) == wanted["without_response"]
        actual = codec.function(q["opcode"], q["side"], single=selected.query_single)
    else:
        raise AssertionError(kind)
    assert actual == expected
