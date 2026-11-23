"""Galaxy 3.3.0 primary arm64 literal vectors, independent of other apps."""

from __future__ import annotations

import gzip
import json
import math
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from custom_components.adjustable_bed.beds.galaxy.catalog import ACTIONS, PRODUCTS, RUNTIMES
from custom_components.adjustable_bed.beds.goodvibe import protocol as p
from custom_components.adjustable_bed.beds.goodvibe.receive import common, extended
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.richmat_catalog import Action

FIXTURES = Path(__file__).parent / "fixtures/galaxy"


def fixture(name):
    return json.loads(gzip.decompress((FIXTURES / f"{name}.json.gz").read_bytes()))


def test_every_frozen_ordinary_builder_literal():
    vectors = fixture("ordinary")
    assert len(vectors) == 48642
    for identity, values, side, long, single, expected, _selector, _binding in vectors:
        assert (
            p.action_frame(Action(*values), side, single, long).hex()
            == bytes.fromhex(expected).hex()
        ), identity


def test_all_runtime_descriptor_operands_against_the_frozen_common_oracle():
    seen = set()
    for key, side, single, long, expected in fixture("surface"):
        assert p.action_frame(ACTIONS[key], side, single, long).hex() == expected, key
        seen.add(key)
    assert seen == {key for key, action in ACTIONS.items() if not action.local}


def test_every_product_configuration_and_reachable_control():
    from dataclasses import asdict

    expected = fixture("products")
    assert len(expected) == len(PRODUCTS) == 845
    for key, values, runtime in expected:
        product = PRODUCTS[key]
        assert list(json.loads(json.dumps(asdict(product))).values()) == values, key
        assert RUNTIMES[key].initial_release == runtime["initial_release"]
        assert RUNTIMES[key].query_order == tuple(runtime["advanced"]["query_order"])
        assert RUNTIMES[key].time_sync == runtime["advanced"]["time_zone_sync"]
        assert RUNTIMES[key].snore == runtime["advanced"]["snore_menu_after_name"]
        assert set(product.actions + product.alarms) <= ACTIONS.keys(), key
    assert "FWRM" not in PRODUCTS and "WFRM" not in PRODUCTS
    assert not any(key.startswith("sleep_") for key in PRODUCTS)


SPECIAL = dict(
    zip(
        (
            "exit_limit",
            "clock_query",
            "light_query",
            "music_query",
            "aroma_query",
            "mattress_query",
            "snore_query",
            "speech_query",
            "detection_query",
            "detection_start",
            "version_query",
            "mode_query",
            "motor1_query",
            "motor2_query",
            "motor3_query",
            "motor4_query",
            "massage_query",
            "light_state_query",
        ),
        codec.FUNCTION_PREFIXES,
        strict=True,
    )
)


def test_frozen_normal_advanced_builders():
    seen = 0
    for vector in fixture("common"):
        i, kind = vector["inputs"], vector["builder"]
        if kind in ("sleep", "envelope", "desk", "crc_frame"):
            continue  # Separate sensor/desk/OTA products are outside the bed boundary.
        if kind == "normal":
            single, long = i.get("service") == "one_byte", i.get("press") == "long"
            code = (
                i.get("long_value", 0)
                if long
                else i.get("alternate", i.get("short_value", 0))
                if single
                else i.get("short_value", 0)
            )
            actual = codec.function(
                code, i.get("side", 0), action=SPECIAL.get(i.get("special"), ""), single=single
            )
        elif kind in ("clock_low", "clock_high"):
            actual = p.clock(i["minutes"], i.get("mode", 0))[kind == "clock_high"]
        elif kind == "light_seconds":
            if i["seconds"] > 65535:
                # Android's private overflow builder is not reachable through the UI ranges.
                continue
            actual = p.light_duration(i["seconds"])
        elif kind == "color":
            actual = codec.rgb(*(math.floor(v * 255 + 0.5) for v in i["rgb"]))
        elif kind == "zone_epoch":
            now = datetime.fromtimestamp(i["epoch"], timezone(timedelta(hours=i["zone"])))
            actual = p.sync_time(now, build=codec.record)[0]
        elif kind == "zone_calendar":
            actual = codec.calendar(datetime(**i, tzinfo=UTC))
        elif kind == "snore_config":
            actual = p.snore_config(i["count"], i["value"], build=codec.record)
        elif kind == "snore_switch":
            actual = p.snore_switch(i["on"], build=codec.record)
        elif kind == "alarm_add":
            actual = p.repeat_alarm(
                i["slot"], i["hour"], i["minute"], i["mode"], i["repeat"], build=codec.record
            )
        elif kind == "alarm_delete":
            actual = p.delete_alarm(i["slot"], build=codec.record)
        else:
            actual = p.queries(codec.record)[
                {
                    "sleep_advert": "sleep_name",
                    "snore_config_query": "snore_config",
                    "snore_switch_query": "snore_switch",
                    "alarm_list": "alarms",
                }[kind]
            ]
        assert actual.hex() == vector["expected_bytes"], vector["id"]
        seen += 1
    assert seen == 46


def test_common_parser_literals_keep_raw_units_and_empty_models():
    vectors = {v["id"]: v for v in fixture("parsers")}
    events = {}
    for key, vector in vectors.items():
        if vector["kind"] != "normal":
            continue
        data = list(bytes.fromhex(vector["bytes"]))
        if key in ("R004", "R046", "R047", "R048"):
            continue  # Standalone desk state; shared stream framing is tested separately.
        events[key] = dict(extended(data, timer_pair=True) if data[1] == 0x20 else common(data))
    assert events["R001"]["deviceControlBoxProtocolVersionEvent"] == 7
    assert events["R002"]["deviceVersionOneMotorAngleEvent"] == vectors["R002"]["expected"]
    assert events["R005"]["deviceVersionOneMotorAngleEvent"] == vectors["R005"]["expected"]
    for key in ("R020", "R021"):
        assert events[key]["deviceMotorCurrentHeightStatusEvent"] == vectors[key]["expected"]
    assert events["R006"]["deviceRGBStripTimerStatusEvent"] == 90
    assert events["R007"]["deviceRepeatAlarmListEscalationStatusEvent"]["alarm_fields"] == [
        1,
        0,
        7,
        30,
        2,
        131,
    ]
    assert events["R008"]["deviceAntiSnoreConfigTimeEvent"] == 3
    for key in ("R009", "R010"):
        value = events[key]["deviceHeatingTimeChangeStatusEvent"]
        expected = vectors[key]["expected"]
        assert value == {
            "position": expected["position"],
            "type": expected["type"],
            "timeSum": expected["time"],
        }
    assert events["R022"] == {
        "deviceMassageHeadStrengthStatusEvent": 3,
        "deviceMassageFootStrengthStatusEvent": 5,
    }
    assert events["R028"]["deviceRGBStripColorStatusEvent"]["rgba_bytes"] == [255, 0, 255, 255]
    assert events["R033"]["deviceSleepAdvNameEvent"] == list(b"HJ-TEST")
    assert events["R040"]["deviceAtomizationTimeStatusEvent"] == [1, 30]
    assert events["R044"]["deviceCheckEvent"] == [3, list(bytes.fromhex(vectors["R044"]["bytes"]))]
    assert events["R045"]["deviceBlacketDelayStatusEvent"]["fields"] == {}

    scalars = {
        "R023": ("deviceMassageModeStatusEvent", "mode"),
        "R024": ("deviceMassageFrequencStatusEvent", "frequency"),
        "R025": ("deviceMusicShakeStatusEvent", "music_follow_intensity"),
        "R026": ("deviceMassagePowerStatusEvent", "on"),
        "R027": ("deviceWhiteLedStatusEvent", "on"),
        "R029": ("deviceRGBStripMotionStatusEvent", "auto_sense"),
        "R030": ("deviceRGBStripStatusEvent", "on"),
        "R031": ("deviceAntiSnoreEvent", "on"),
        "R032": ("deviceGetOffBedStatusEvent", "out_of_bed"),
        "R037": ("deviceMusicBleStatusEvent", "bluetooth"),
        "R038": ("deviceFanGearStatusEvent", "fan"),
        "R039": ("deviceAtomizationOpenStatusEvent", "level"),
        "R042": ("deviceHeatingPadModelStatusEvent", "state"),
        "R043": ("deviceStrandardAndSplitControlEvent", "same_control"),
    }
    for key, (event, field) in scalars.items():
        assert events[key][event] == vectors[key]["expected"][field], key
    assert events["R003"] == {
        "deviceMusicUsbStatusEvent": True,
        "deviceMusicPlayStatusEvent": True,
        "deviceMusicShakeStatusEvent": True,
        "deviceMusicBleStatusEvent": True,
    }
    assert events["R034"] == {"deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent": None}
    assert events["R035"] == {"deviceCharacteristicsSubscriptionBoxLockEvent": None}
    assert events["R036"] == {"deviceMusicVolumeStatusEvent": 80}
    assert (
        events["R041"]["deviceHeatingTemperatureChangeStatusEvent"] == vectors["R041"]["expected"]
    )
    assert len(events) == 35


def test_every_shared_framing_vector_preserves_bed_stream_progress():
    from custom_components.adjustable_bed.beds.goodvibe.receive import Notifications

    for vector in fixture("parsers"):
        if vector["kind"] != "framing":
            continue
        emitted = []
        receiver = Notifications(lambda name, value, emitted=emitted: emitted.append((name, value)), timer_pair=True)
        for fragment in vector["fragments"]:
            receiver.feed(bytes.fromhex(fragment))
        if vector.get("timeout"):
            receiver.clear()
        assert receiver.buffer.hex() == vector["expected"]["remaining"], vector["id"]
        for frame in vector["expected"]["frames"] + vector["expected"]["rejected"]:
            data = bytes.fromhex(frame)
            if data[1] == 0x40:
                assert codec.is_valid_crc(data) == (frame in vector["expected"]["frames"])
        # Ignored desk/firmware and rejected checksum records cannot consume the next bed reply.
        if not receiver.buffer:
            receiver.feed(bytes.fromhex("6e09010078"))
            assert emitted[-1] == ("deviceCharacteristicsSubscriptionClockEvent", None), vector[
                "id"
            ]
