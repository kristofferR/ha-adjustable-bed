"""Frozen app vectors with explicit source-corrected member caller cases."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from custom_components.adjustable_bed.cluster018_caller import Retain, Selection, transition
from custom_components.adjustable_bed.cluster018_profiles import Control
from custom_components.adjustable_bed.cluster018_protocol import (
    Worker,
    alarm,
    control,
    decode_resource,
    desk_target,
    direct,
    lamp_timer,
    rgb,
    worker_interval,
)
from custom_components.adjustable_bed.cluster018_receive import MalformedFrame, ReceiveState

FIXTURES = Path(__file__).parent / "fixtures" / "cluster018"


def test_worker_startup_preserves_actual_name_guard_and_cadence():
    import pytest

    for wire in ("RAW", "FRAMED"):
        assert worker_interval(" 6brm-bed ", wire) == 150
        assert worker_interval("TWRM-1", wire) == 110
        assert worker_interval("MLRM", wire) == 110
        assert worker_interval("OTHER", wire) == 150
        with pytest.raises(ValueError, match="four"):
            worker_interval("abc", wire)
    assert worker_interval(None, "FRAMED") == 110
    with pytest.raises(ValueError, match="name"):
        worker_interval(None, "RAW")


def test_accepted_selected_material_contracts() -> None:
    """All branch cases; ZRS6 navigation uses the separately recorded source correction."""
    with gzip.open(FIXTURES / "callers.json.gz", "rt") as source:
        cases = json.load(source)
    assert len(cases) == 47876
    for case in cases:
        row = case["button"]
        row["modes"] = tuple(row["modes"])
        row["ancestor_visibility"] = tuple(row["ancestor_visibility"])
        result = transition(Control(**row), case["layout"], case["wire"], Selection(**case["selection"]), case["event"], app=case.get("app"))
        actual = {}
        for key in case["expected"]:
            value = getattr(result, key)
            actual[key] = "RETAIN" if isinstance(value, Retain) else value.hex() if isinstance(value, bytes) else value
        assert actual == case["expected"], case


def test_every_member_navigation_predicate_matches_its_actual_source_method():
    from dataclasses import replace

    from custom_components.adjustable_bed.cluster018_profiles import controls

    members = json.loads((FIXTURES / "navigation_predicates.json").read_text())
    tags = {tag for member in members for tag in member["tags"]} | {"unmatched"}
    for member in members:
        template = controls(member["app"], "6BRM")[0]
        for tag in tags:
            for value in (tag, tag.upper()):
                # Declared caller-library tag input, not another live UI control.
                button = replace(template, status=2, tag=value)
                result = transition(button, "6BRM", "FRAMED", Selection(), "DOWN", app=member["app"])
                expected = "navigate:" + tag if tag in member["tags"] else None
                assert result.local == expected, (member["app"], value)


def test_accepted_builders_and_parser_vectors() -> None:
    cases = json.loads((FIXTURES / "vectors.json").read_text())
    for case in cases:
        kind, args = case["input"]
        if kind == "CONTROL":
            wire, payload, mode = args
            actual = control(bytes.fromhex(payload), wire, mode).hex()
        elif kind == "DIRECT":
            actual = direct(*args).hex()
        elif kind == "ALARM":
            actual = b"".join(alarm(*args)).hex()
        elif kind == "RGB":
            actual = rgb(*args).hex()
        elif kind in ("LED_SECONDS", "LED_SAVE"):
            actual = lamp_timer(*args, save=kind == "LED_SAVE").hex()
        elif kind == "DESK_TARGET":
            actual = desk_target(*args).hex()
        elif kind == "DECODE":
            decoded = decode_resource(*args)
            actual = decoded.hex() if decoded is not None else None
        elif kind == "PARSER_SINGLE":
            state = ReceiveState()
            try:
                state.feed(bytes.fromhex(args[0]), app="avocadoecobase", layout="FWRM")
            except MalformedFrame:
                assert case["expected"]["error"] is not None, case
                continue
            expected = case["expected"]
            if expected["first_dispatch"] and expected["first_dispatch"]["event"] == "height":
                assert [state.height_cm, state.height_inches] == expected["first_dispatch"]["values"], case
            assert state.buffer == expected["buffer"], case
            continue
        else:
            raise AssertionError(kind)
        assert actual == case["expected"], case


def test_all_byte_pairs_match_frozen_independent_jvm_height_results() -> None:
    import struct

    from custom_components.adjustable_bed.cluster018_protocol import new_height, old_height

    with gzip.open(FIXTURES / "height_vectors.bin.gz", "rb") as source:
        expected = source.read()
    assert len(expected) == 65536 * 24
    for first in range(256):
        for second in range(256):
            actual = struct.pack("!6f", *old_height(first, second), *new_height(0, first, second), *new_height(1, first, second))
            offset = (first * 256 + second) * 24
            assert actual == expected[offset:offset + 24], (first, second)


def test_worker_retains_partial_long_count_and_latch_until_release_paths() -> None:
    worker = Worker(mode=3, payload=b"\x2b", count=2)
    assert worker.tick() == ()
    worker.mode = 0
    assert worker.tick()[0].delay_ms == 50
    assert worker.counter == 0
    worker.mode = 3
    worker.count = 0
    assert worker.tick()[0].payload == b"\x2b"
    assert worker.fired
    worker.mode = 0
    worker.tick()
    assert worker.fired
    worker.mode = 4
    assert [x.payload for x in worker.tick()] == [b"\x6e"]
    assert not worker.fired


def test_complete_retained_worker_contexts_match_accepted_source_iterations() -> None:
    with gzip.open(FIXTURES / "worker_cases.json.gz", "rt") as source:
        cases = json.load(source)
    for case in cases:
        expected = case["expected"]
        worker = Worker(mode=case["mode"], payload=bytes.fromhex(case["payload"]) if case["payload"] else None,
                        count=case["count"], counter=case["counter"], fired=case["fired"],
                        tick_ms=case["tick_ms"], total_ms=case["total_ms"])
        emissions = worker.tick() if case["running"] else ()
        assert [e.payload.hex() if e.payload is not None else None for e in emissions] == [v[1] for v in expected["sendData_invocations"]], case
        assert [e.delay_ms for e in emissions if e.delay_ms] + ([worker.tick_ms] if case["running"] else []) == expected["source_delay_arguments_ms"], case
        assert (worker.mode, worker.counter, worker.fired) == (expected["mode_after"], expected["i_after"], expected["z_after"]), case


def test_raw_null_assignment_and_outside_cancel_are_not_fresh_idle_state() -> None:
    worker = Worker(mode=3, payload=None, count=2, counter=1, fired=True)
    worker.outside_cancel()
    assert worker.mode == 3
    assert worker.tick() == ()
    assert worker.tick()[0].payload is None
    worker.mode = 1
    worker.outside_cancel()
    assert worker.mode == 0


def test_count_setter_preserves_other_worker_state_and_uses_the_current_tick() -> None:
    """Accepted five-member three-instruction setter: divide, write count, return."""
    from dataclasses import asdict

    import pytest

    for tick in (100, 110, 150):
        for milliseconds in (0, 150, 3000, 5000):
            worker = Worker(mode=3, payload=b"\x2b", counter=7, fired=True, tick_ms=tick)
            before = asdict(worker)
            worker.set_count(milliseconds)
            after = asdict(worker)
            assert after.pop("count") == milliseconds // tick
            before.pop("count")
            assert after == before
            worker.set_interval(110)
            assert worker.count == 27  # mTotalSec remains 3000, not milliseconds.
    worker = Worker(tick_ms=0, count=17)
    with pytest.raises(ZeroDivisionError):
        worker.set_count(3000)
    assert worker.count == 17


def test_accepted_quick_release_and_memory_sequences() -> None:
    from dataclasses import replace

    from custom_components.adjustable_bed.cluster018_profiles import controls

    for case in json.loads((FIXTURES / "sequences.json").read_text()):
        inputs = case["input"]
        app = case["member"].split(".")[-1]
        button = next(c for c in controls(app, inputs["layout"]) if c.node == inputs["node"])
        selection = Selection(armed=inputs["armed"])
        worker = Worker(tick_ms=110)
        writes = []
        for event in inputs["events"]:
            if event == "POLL":
                for emission in worker.tick():
                    assert emission.payload is not None
                    writes.append({"frame": control(emission.payload, inputs["wire"], inputs["curMode"]).hex(), "sleep_before_ms": emission.delay_ms})
                continue
            step = transition(button, inputs["layout"], inputs["wire"], selection, event)
            if not (step.idle_up_guard and worker.mode == -1):
                if not isinstance(step.count_ms, Retain):
                    worker.set_count(step.count_ms)
                if not isinstance(step.payload, Retain):
                    worker.payload = step.payload
                if not isinstance(step.mode, Retain):
                    worker.mode = step.mode
            if step.consume_arm:
                selection = replace(selection, armed=False)
        assert writes == case["writes"], case
        assert {"mode": worker.mode, "i": worker.counter, "z": worker.fired, "arm": "ARMED" if selection.armed else "UNARMED_LITERAL0"} == case["final"], case


def test_accepted_parser_binding_reset_and_visibility_sequences() -> None:
    for case in json.loads((FIXTURES / "parser_sequences.json").read_text()):
        state = ReceiveState()
        bound = True
        for event, expected in zip(case["events"], case["expected"], strict=True):
            state.events = []
            if event == "UNBIND":
                bound = False
            elif event == "BIND":
                bound = True
            elif event == "RESET":
                state.old_pack = ""
            else:
                state.feed(bytes.fromhex(event), app=case["member"].split(".")[-1], layout="FWRM", table_controls_bound=bound)
            assert (state.old_pack or "null") == expected["oldPack"]
            assert state.modern_controls == expected["visible"], case
            assert state.modern_controls == expected["scrollable"], case
            from custom_components.adjustable_bed.cluster018_protocol import float32
            def numeric(value):
                if isinstance(value, dict):
                    return {k:numeric(v) for k,v in value.items()}
                if isinstance(value, list):
                    return [numeric(v) for v in value]
                return float32(value) if isinstance(value,float) else value
            assert state.events == numeric(expected["events"]), (case["id"], event, state.events, expected["events"])


def test_all_member_caller_vectors_preserve_declared_library_modes() -> None:
    from custom_components.adjustable_bed.cluster018_profiles import controls
    from custom_components.adjustable_bed.cluster018_protocol import float32, rounded

    for case in json.loads((FIXTURES / 'caller_vectors.json').read_text()):
        inputs = case['input']
        for peer in case['results']:
            expected = peer['expected']
            if isinstance(inputs, list):
                raw = bytes.fromhex(inputs[1][0])
                values = [rounded(float32((raw[i]*100+raw[i+1])/10)) for i in (3,5,7,9,11,13)]
                assert {'unit':raw[2], 'discarded':values[:2], 'min':values[2], 'max':values[3], 'initial_primary':values[5], 'initial_secondary':values[4]} == expected
                continue
            app = peer['member'].split('.')[-1]
            button = next(c for c in controls(app, inputs['layout']) if c.node == inputs['node'])
            result = transition(button, inputs['layout'], inputs['wire'], Selection(armed=inputs['armed']), inputs['event'])
            assert isinstance(result.payload, bytes)
            assert control(result.payload, inputs['wire'], inputs['curMode']).hex() == expected['selected_frame']
            assert result.mode == expected['mode']
            assert result.count_ms == expected['count_ms']
            assert result.consume_arm
