"""Independent vectors from the accepted S02 artifact, without local audit imports."""

from __future__ import annotations

import base64
import json

import pytest

from custom_components.adjustable_bed import sleeptracker_protocol as p


def test_movement_and_release_exact_pretty_wire() -> None:
    expected = """{
    "wsCommand": "motor-command",
    "authToken": "token",
    "request":
    {
        "movement":
        {
            "position":
            {
                "side": 1,
                "location": "head"
            },
            "action": "up",
            "ticks": 4,
            "waitForResponse": false
        }
    }
}"""
    expected = expected.replace('":\n', '": \n')
    assert p.movement("head", "up", 1, "token") == expected.encode()
    release = json.loads(p.movement("head", "stop", 1, "token"))
    assert release["request"]["movement"] == {
        "position": {"side": 1, "location": "head"},
        "action": "stop",
    }
    assert json.loads(p.stop(2, None))["request"] == {
        "stop": {"action": "all", "position": {"side": 2}}
    }
    assert json.loads(p.stop(2, None, all_features=False))["request"]["stop"]["action"] == "massage"


@pytest.mark.parametrize("preset", p.PRESETS)
def test_preset_recall_and_separate_save(preset: str) -> None:
    recall = json.loads(p.preset(preset, 2, "token"))
    assert recall == {
        "wsCommand": "motor-command",
        "authToken": "token",
        "request": {"preset": {"name": preset, "position": {"side": 2}}},
    }
    if preset != "all_flat":
        save = json.loads(p.preset(preset, 2, "token", save=True))
        assert save == {
            "wsCommand": "motor-control",
            "authToken": "token",
            "request": {"savePreset": {"position": {"side": 2}, "name": preset}},
        }


@pytest.mark.parametrize("direction", ["left", "right", "both"])
@pytest.mark.parametrize("heating,timer", [(False, 36000), (True, 3600)])
@pytest.mark.parametrize("level", range(4))
@pytest.mark.parametrize("constant", [False, True])
def test_breeze_complete_field_groups(direction, heating, timer, level, constant) -> None:
    wire = p.fan(
        p.Request("climate", fan_side=direction, heating=heating, level=level, constant=constant),
        "token",
    )
    decoded = json.loads(wire)
    assert b"\n" not in wire
    body = decoded["request"]["fanControl"]
    zones = ("left", "right") if direction == "both" else (direction,)
    expected = {"position": {"side": 0}}
    for zone in zones:
        expected.update(
            {
                zone + "IsConstant": constant,
                zone + "IsHeating": heating,
                zone + "Level": level,
                zone + "Timer": timer,
            }
        )
    assert body == expected
    assert list(body) == [
        "position",
        *[
            field
            for zone in zones
            for field in (zone + "IsConstant", zone + "IsHeating", zone + "Level")
        ],
        *[zone + "Timer" for zone in zones],
    ]


@pytest.mark.parametrize("hz,strength", [(28, 4), (40, 5), (52, 3), (68, 2), (88, 1)])
def test_relaxation_wave(hz, strength) -> None:
    wire = p.wave(p.Request("wave", frequency=hz, minutes=30), 1, None)
    statements = json.loads(wire)["request"]["statement"]["statements"]
    assert statements == [
        {
            "type": "command",
            "command": {
                "massage": {
                    "position": {"side": 1, "location": "ignore_this"},
                    "action": "pulse",
                    "value": strength,
                    "duration": 18000,
                }
            },
            "startDelayMs": 0,
        },
        {
            "type": "command",
            "startDelayMs": 500,
            "command": {"massage": {"position": {"side": 1}, "action": "frequency", "value": hz}},
        },
    ]
    assert "authToken" not in json.loads(wire)


def test_local_sequence_independent_audio_disposition() -> None:
    wire = p.local_animation(1, None)
    assert b"speaker" not in wire and b"audio" not in wire
    statements = json.loads(wire)["request"]["statement"]["statements"]
    assert len(statements) == 6
    assert all(item["type"] == "command" for item in statements)
    for index in (0, 5):
        assert statements[index]["command"] == {
            "preset": {"position": {"side": 1}, "name": "all_flat"}
        }
    for index in (2, 3):
        assert statements[index]["command"] == {
            "massage": {"position": {"side": 1}, "action": "toggle"}
        }
    assert [item["startDelayMs"] for item in statements] == [0, 11000, 0, 0, 7000, 34000]
    assert statements[1]["command"]["pulseCounts"]["pulseCountSettings"] == [
        {"location": "head", "pulseCount": 4000},
        {"location": "foot", "pulseCount": 5000},
    ]
    assert statements[4]["command"]["pulseCounts"]["pulseCountSettings"] == [
        {"location": "head", "pulseCount": 6000}
    ]


def test_authentication_fixed_salt_accepted_vector() -> None:
    wire = p.authentication("aa:bb:cc:01:02:03", "abc123", b"$2a$10$......................")
    password = json.loads(wire)["password"]
    assert (
        base64.b64decode(password)
        == b"$2a$10$......................YFssfzg1ZBGNiq6A1DjBD2UomFX09tK"
    )
    assert wire.startswith(b'{"type" : "authenticate", "password" : "')
    assert wire.endswith(b'", "clientId" : "sleeptracker-android-tsi"}')


@pytest.mark.parametrize(
    "action,location",
    [("step", "head"), ("step", "foot"), ("pattern", None), ("28Hz", None), ("40Hz", None)],
)
def test_massage_frequency_and_zone_wire(action, location) -> None:
    value = json.loads(p.massage(action, 2, "token", location=location))
    position = {"side": 2}
    if location is not None:
        position["location"] = location
    assert value == {
        "wsCommand": "motor-command",
        "authToken": "token",
        "request": {"massage": {"action": action, "value": 1, "position": position}},
    }


@pytest.mark.parametrize("all_features,action", [(True, "all"), (False, "massage")])
def test_selected_unit_stop_wire(all_features, action) -> None:
    assert json.loads(p.stop(2, None, all_features=all_features)) == {
        "wsCommand": "motor-command",
        "request": {"stop": {"action": action, "position": {"side": 2}}},
    }


@pytest.mark.parametrize("length", [1, 18, 19, 500, 501, 1200])
@pytest.mark.parametrize("capacity", [18, 100, 500])
def test_frames_reassemble_with_transport_capacity(length, capacity) -> None:
    payload = bytes(index % 251 for index in range(length))
    frames = p.frames(payload, capacity)
    assembler = p.Reassembler()
    outputs = [assembler.feed(frame) for frame in frames]
    assert outputs[:-1] == [None] * (len(frames) - 1)
    assert outputs[-1] == payload
    for index, frame in enumerate(frames):
        header = int.from_bytes(frame[:2], "little")
        assert header & 511 == len(frame) - 2 <= capacity
        assert header & 0x3E00 == 0
        assert bool(header & 0x8000) == (index == 0)
        assert bool(header & 0x4000) == (index == len(frames) - 1)
    assert p.frames(b"{}", 500) == (b"\x02\xc0{}",)


@pytest.mark.parametrize("frame", [b"", b"\x01", b"\x04\xc0{}", b"\x02\x40{}"])
def test_malformed_or_orphan_frames_are_rejected(frame) -> None:
    with pytest.raises(ValueError):
        p.Reassembler().feed(frame)


def test_remote_and_climate_parser_rules_stay_distinct() -> None:
    prior = {"left_heating": True, "left_level": 2, "right_level": 1}
    value = {
        "body": {
            "snapshots": [
                {
                    "massagePattern": 3,
                    "head": {"massage": {"strength": 4}},
                    "foot": {"massage": {"strength": 6}},
                    "safetyLightOn": "TRUE",
                    "fan": {"leftLevel": 9, "rightLevel": "3", "rightIsHeating": "false"},
                }
            ]
        }
    }
    state = p.status(value, 0, prior)
    assert state == {
        **prior,
        "massage_pattern": 3,
        "massage_head_strength": 4,
        "massage_foot_strength": 6,
        "light_on": True,
        "left_level": 3,
        "right_level": 0,
        "right_heating": False,
    }
    split = p.status(
        {
            "body": {
                "snapshots": [
                    {"side": 0, "massagePattern": 1, "safetyLightOn": True},
                    {"side": 1, "massagePattern": 2, "head": {"massage": {"strength": 8}}},
                ]
            }
        },
        1,
        state,
    )
    assert split["massage_pattern"] == 2
    assert split["massage_head_strength"] == split["massage_foot_strength"] == 0
    assert split["light_on"] is False
    assert split["left_level"] == 3
    reset = p.status({}, 0, split)
    assert reset["massage_pattern"] == 0 and reset["left_level"] == 3


@pytest.mark.parametrize("model", p.MODELS)
def test_exact_layout_gates(model) -> None:
    selected = p.MODELS[model]
    p.validate_request(p.Request("preset", preset="user_favorite"), selected)
    if selected.premium:
        p.validate_request(p.Request("wave"), selected)
    else:
        with pytest.raises(ValueError):
            p.validate_request(p.Request("wave"), selected)
    if not selected.breeze:
        with pytest.raises(ValueError):
            p.validate_request(p.Request("climate"), selected)


@pytest.mark.parametrize(
    "mode,running",
    [
        (0, False),
        (1, True),
        (2, True),
        (-3, True),
        (5, True),
        (0.9, False),
        (-0.9, False),
        (-2.9, True),
        (2147483647, True),
        (-2147483647, True),
        (2147483648, False),
        (-2147483648, False),
        (True, False),
        ("2", False),
        (None, False),
    ],
)
def test_wind_down_first_snapshot_numeric_rule(mode, running) -> None:
    assert p.wind_down_running({"body": {"snapshots": [{"windDownMode": mode}]}}) is running


@pytest.mark.parametrize("snapshots", [[], [None], None])
def test_wind_down_absent_snapshots_are_not_stop_proof(snapshots) -> None:
    assert p.wind_down_running({"body": {"snapshots": snapshots}}) is None
    assert p.wind_down_running({"body": {}}) is None
    assert p.wind_down_running({}) is None


def test_wind_down_uses_first_non_null_snapshot_without_side_filter() -> None:
    assert (
        p.wind_down_running(
            {
                "body": {
                    "snapshots": [
                        None,
                        {"side": 0, "windDownMode": 2},
                        {"side": 1, "windDownMode": 0},
                    ]
                }
            }
        )
        is True
    )
    assert p.wind_down_running({"body": {"snapshots": [{}, {"windDownMode": 2}]}}) is False
    assert p.wind_down_running({"body": {"snapshots": [{"windDownMode": 2}, "unused"]}}) is True


def test_reply_parser_skips_null_fields_including_duplicate_keys() -> None:
    details = p.child(
        p.json_object(
            b'{"details":{"body":{"snapshots":[{"windDownMode":2,"windDownMode":null}]}}}'
        ),
        "details",
    )
    assert p.wind_down_running(details) is True
    assert (
        p.wind_down_running(
            p.child(p.json_object(b'{"details":{"body":{"snapshots":null}}}'), "details")
        )
        is None
    )


@pytest.mark.parametrize(
    "value",
    [
        {"unused": [[]]},
        {"details": {"body": {"snapshots": [{"unused": [None, []]}, 7]}}},
        {"unused": [{"deeper": [[1]]}]},
    ],
)
def test_reply_parser_rejects_nonadvancing_nested_arrays(value) -> None:
    with pytest.raises(ValueError, match="nested array"):
        p.json_object(json.dumps(value).encode())


def test_reply_parser_accepts_arrays_of_objects_and_scalars() -> None:
    value = {"unused": [None, 7, True, "text", {"children": [{"value": 2}]}]}
    assert p.json_object(json.dumps(value).encode()) == value


@pytest.mark.parametrize(
    "raw",
    [
        b'{"unused":[[]],"unused":0}',
        b'{"unused":[[]],"unused":{}}',
        b'{"body":{"unused":[[]]},"body":{"snapshots":[]}}',
        b'{"details":{"unused":[[]]},"details":{"body":{}}}',
        b'{"unused":{"deep":[[]]},"unused":0}',
    ],
)
def test_reply_parser_validates_discarded_duplicate_values(raw) -> None:
    with pytest.raises(ValueError, match="nested array"):
        p.json_object(raw)


def test_reply_parser_keeps_valid_last_non_null_duplicate() -> None:
    assert p.json_object(b'{"unused":[1,null,{}],"unused":0,"unused":null}') == {"unused": 0}


@pytest.mark.parametrize("snapshots", ["bad", [1]])
def test_wind_down_malformed_shapes_fail_safely(snapshots) -> None:
    with pytest.raises(ValueError):
        p.wind_down_running({"body": {"snapshots": snapshots}})


def test_hello_aliases_are_independent_of_persisted_slim_ids() -> None:
    assert p.HELLO_MODELS["SLIM_BEST"] == 19
    assert p.MODELS["slim_prosmart"].id == 24


def test_untrusted_token_is_escaped_instead_of_copying_formatter_bug() -> None:
    token = 'a"b\\\n'
    assert json.loads(p.envelope(None, token, operation="motor-status"))["authToken"] == token


@pytest.mark.parametrize("company", [0xEF01, 0x01EF])
def test_manufacturer_fields_are_metadata_not_axis_decoders(company):
    metadata = p.manufacturer_metadata(
        {company: bytes.fromhex("0301020313010203")}, "AA:BB:CC:01:02:03"
    )
    assert metadata == {
        "advertised_flags": 3,
        "advertised_provisioned": True,
        "advertised_board_matches_target": True,
        "advertised_model_id": 19,
        "advertised_version_octets": [1, 2, 3],
    }
    assert not p.manufacturer_metadata({company: b"\x01\x02"}, "AA:BB:CC:01:02:03")
