"""Frozen literal operands from all four independently accepted row071 apps."""

import gzip
import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import protocol as frames
from custom_components.adjustable_bed.beds.richmat_classic import resource_protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, selected_operand
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.protocol import control
from custom_components.adjustable_bed.beds.richmat_classic.resource_receive import (
    ResourceReceiveState,
)
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.richmat_resource_apps import APPS

FIXTURES = Path(__file__).parent / "fixtures/richmat_cluster017"


def records(name):
    return json.loads(gzip.decompress((FIXTURES / f"{name}.json.gz").read_bytes()))


def test_all_member_wire_literals_reuse_the_richmat_codec():
    rows = records("wire")
    assert len(rows) == 24576
    members = set()
    for app, source_id, wire, operand, literal in rows:
        members.add(app)
        packet = control(bytes.fromhex(operand), "RAW" if wire == "raw" else "FRAMED")
        assert packet.hex() == literal.lower(), (app, source_id)
    assert members == {"lady_americana", "acaa", "sta2", "zerogravity"}


@pytest.mark.parametrize("app", APPS)
def test_complete_shared_binding_domain_uses_actual_getters(app):
    rows = records("bindings")
    assert len(rows) == 8294
    models = load_catalog(app).models
    checked = 0
    for row in rows:
        if "event" not in row or row.get("event") is None:
            continue  # Explicit navigation / non-command outcome.
        button = next(c for c in models[row["variant"]].controls if c.node == row["node"])
        condition = row.get("condition") or {}
        selection = Selection(
            press_flag=condition.get("flag", "53"), head=condition.get("head", True)
        )
        argument = 3 if row["event"] == "long" else 1 if button.status == 1 else 2
        value = selected_operand(
            button, "RAW" if row["transport"] == "raw" else "FRAMED", argument, selection
        )
        expected = bytes.fromhex(row["value"]) if row.get("value") else None
        assert value == expected, (app, row["id"])
        checked += 1
    assert checked == 8094 + 16  # Includes null GVRM branches, never invented alternates.


@pytest.mark.parametrize("app", APPS)
def test_accepted_direct_builder_and_parser_vectors(app):
    vectors = records(app + "_vectors")
    checked = 0
    for vector in vectors:
        args, identifier = vector["inputs"], vector["id"]
        expected = vector["expected_bytes"].replace("|", "").replace(";", "").lower()
        kind = vector.get("builder", args.get("kind"))
        result = None
        if kind == "ascii" or identifier.startswith("group-"):
            continue  # Excluded module membership administration.
        if kind in ("rx", "parser") or identifier.startswith("parser-"):
            state = ResourceReceiveState()
            chunks = args.get("chunks", args.get("notifications", [args.get("notification")]))
            emitted = []
            for chunk in chunks:
                state.feed(bytes.fromhex(chunk), app=app, layout="O0RM")
                if state.value_event:
                    emitted.append(state.value_event)
            if "expected_emitted" in vector:
                assert emitted == [v.lower() for v in vector["expected_emitted"]]
            elif "accepted" in args:
                assert bool(emitted) == args["accepted"]
            else:
                assert (emitted[-1] if emitted else "") == expected
            checked += 1
            continue
        if kind == "control":
            result = control(
                bytes.fromhex(args["value"]), "RAW" if args["kind"] == "raw" else "FRAMED"
            )
        elif kind == "layout":
            result = control(
                bytes.fromhex(args["opcode"]), "RAW" if vector["protocol"] == "P1" else "FRAMED"
            )
        elif kind == "frame":
            result = frames.direct(*args["fields"])
        elif kind == "payload":
            result = codec.frame(*args["payload"])
        elif kind == "packed_time":
            result = (
                frames.aroma(args["opcode"], args["value"])
                if args["opcode"] != 11
                else p.lamp_timeout(args["value"])
            )
        elif kind == "duration":
            result = p.lamp_timeout(args["value"])
        elif kind == "rgb":
            result = codec.rgb(*bytes.fromhex(args.get("value", args.get("rgb"))))
        elif kind == "alarm":
            code = args.get("action", args.get("opcode"))
            result = b"".join(
                frames.alarm(
                    args.get("delay", args.get("minutes")),
                    int(code, 16) if isinstance(code, str) else code,
                )
            )
        elif app == "sta2":
            action = vector["action"]
            if action == "movement":
                result = control(bytes((args["opcode"],)), "FRAMED" if args["wrapped"] else "RAW")
            elif action == "frame4":
                result = codec.frame(*(args[key] for key in "abcd"))
            elif action == "rgb_frames":
                result = codec.rgb(*bytes.fromhex(args["rgb"]))
            elif action == "collapsed_timer":
                result = p.lamp_timeout(args["n"])
            elif action == "alarm_frames":
                result = b"".join(frames.alarm(args["minutes"], args["opcode"]))
        elif app == "zerogravity":
            if identifier.startswith("framed-"):
                result = control(bytes.fromhex(args["command"]), "FRAMED")
            elif identifier == "raw-first-up":
                result = control(b"\x24", "RAW")
            elif identifier in ("startup", "alarm-query", "led-query", "aroma-query"):
                result = {
                    "startup": frames.INITIALIZE,
                    "alarm-query": frames.ALARM_QUERY,
                    "led-query": frames.LAMP_QUERY,
                    "aroma-query": frames.AROMA_QUERY,
                }[identifier]
            elif identifier.startswith("led-timeout"):
                result = p.lamp_timeout(args["seconds"])
            elif identifier.startswith("rgb-"):
                result = codec.rgb(*bytes.fromhex(args["rgb"]))
            elif identifier.startswith("alarm-compose-"):
                codes = [int(args["bed"], 16), *(int(c, 16) for c in args["massage"])]
                available = dict(zip(map(str, range(len(codes))), codes, strict=True))
                result = bytes((p.alarm_action(available, tuple(available)),))
            elif identifier.startswith("alarm"):
                result = b"".join(
                    frames.alarm(args.get("minutes", 0), int(args.get("action", "00"), 16))
                )
            elif identifier.startswith("d1-"):
                result = frames.massage_timer("D1RM", args["progress"])
            elif identifier.startswith("u3rm-"):
                button = next(
                    c
                    for c in load_catalog(app).models["U3RM"].controls
                    if c.tag == ("51" if args["direction"] == "up" else "52")
                )
                operand = selected_operand(
                    button, "FRAMED", 1, Selection(press_flag=args["pressFlag"])
                )
                assert isinstance(operand, bytes)
                result = control(operand, "FRAMED")
            elif identifier.startswith("worker-memory-"):
                worker = frames.Worker(mode=3, payload=b"\x2b")
                outputs = []
                for _ in range(args["held_polls"]):
                    outputs.extend(e.payload for e in worker.tick() if e.payload is not None)
                worker.mode, worker.payload = 4, b"\x2e"
                outputs.extend(e.payload for e in worker.tick() if e.payload is not None)
                result = b"".join(outputs)
        assert result is not None, (app, identifier)
        assert result.hex() == expected, (app, identifier)
        checked += 1
    assert checked >= len(vectors) - 3
