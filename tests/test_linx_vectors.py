"""Compare the accepted app literals with production, never the audit oracle."""

import json

import pytest

from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.codec import linx as codec
from tests.linx_vectors import VECTORS


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_all_39_accepted_literals_through_production(row):
    fields = row["inputs"]
    match row["protocol"]:
        case "P1":
            actual = codec.control(fields["N"], 1, km=fields["K"], held=True)
        case "P2":
            actual = codec.instruction(fields["key"])
        case "P3":
            actual = codec.startup_query(fields["prefix"][6:-4])
        case _:
            actual = (
                codec.SNORE_STATUS
                if not fields
                else codec.snore(
                    "unused",
                    uart=True,
                    keep=fields["keepTime"],
                    speed=fields["upSpeed"],
                    lift=fields["upTime"],
                )
            )
    assert actual.hex() == row["expected_bytes"]


def test_existing_json_codec_does_not_reproduce_linx_literal():
    row = next(row for row in VECTORS if row["protocol"] == "P1")
    assert (
        keeson.json_command(1, row["inputs"]["N"], ctrm=0, km=6, keykt=1).hex()
        != row["expected_bytes"]
    )


def test_static_alarm_serialization_is_separate_from_unavailable_catalog_semantics():
    assert (
        codec.alarm_slot("BED", 6)
        == b'{"dvid":"BED","code":15,"cmd":{"nm":6,"blmd":0,"blpt":0,"blat":0,"blsw":0}}'
    )
    # Numeric inputs test the frozen formula only, without naming any action.
    for position, mode in ((1, 16), (4, 16), (2, 128), (3, 0), (None, 0)):
        fields = json.loads(
            codec.alarm_slot(
                "BED", 1, position_id=position, weekdays=(0, 6, 6), seconds=3661, populated=True
            )
        )["cmd"]
        assert fields == {"nm": 1, "blmd": mode, "blpt": 65, "blat": 3661, "blsw": 1}
    for key, value in codec.ALARM_KEY_CONVERSION.items():
        assert codec.alarm_recall("BED", str(key), uart=True) == codec.instruction(value)
    assert json.loads(codec.alarm_recall("BED", "1000", uart=False))["cmd"] == {
        "ctrm": 1,
        "key": "00001000",
        "keykt": 0,
        "km": 1,
    }
    assert codec.alarm_recall("BED", "5", uart=True) == codec.instruction(0)
    for slot in (0, 7, True):
        with pytest.raises(ValueError):
            codec.alarm_slot("BED", slot)


def test_repaired_setup_reply_and_literal_bed_mode_guards():
    assert codec.setup_reply(bytes.fromhex("8e00000002123400")) == codec.SetupReply(
        "version_received", "12.3.4"
    )
    assert codec.setup_reply(bytes.fromhex("8e000000020a3400")) == codec.SetupReply(
        "invalid_version"
    )
    assert codec.setup_reply(bytes.fromhex("8e00000001000000")) == codec.SetupReply(
        "connection_failed"
    )
    for data in (
        b"",
        bytes(8),
        bytes.fromhex("8e00000003000000"),
        bytes.fromhex("8e000000021234"),
        bytes.fromhex("8e0000000212340000"),
    ):
        assert codec.setup_reply(data) is None
    assert codec.bed_mode(b'{"bedmd":20}', None) == 2
    assert codec.bed_mode(b'{"bedmd": 2}', 2) == 0
    assert codec.bed_mode(b'{"data":{}}', 2) == 2
    assert codec.status(b'{"data":') == {}
    assert codec.status(b"[]") == {}
    assert codec.diagnostic({"chkStatu": 1, "headPlus": 3, "footPlus": 4}).complete is False
    assert codec.diagnostic({"chkStatu": 0xC0, "headPlus": 3, "footPlus": 4}) == codec.Diagnostic(
        True, 0, 0, True, True, 3, 4
    )
    assert codec.diagnostic({"chkStatu": True, "headPlus": 3, "footPlus": 4}) is None
