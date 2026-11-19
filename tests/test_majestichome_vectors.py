"""Accepted Majestic Home literals, frozen before choosing the production wire codec.

Majestic Home 1.0.4/code10400, frozen 2026-07-14. Static fixtures, not captures.
The two CRC utility cases are excluded OTA evidence, never BED commands.
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.goodvibe.receive import ACKS
from custom_components.adjustable_bed.codec import richmat as codec

FIXTURE = Path(__file__).parent / "fixtures/majestichome"
VECTORS = json.loads((FIXTURE / "protocol.json").read_text())


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_candidate_codec_literals(v):
    q = v["inputs"]
    expected = bytes.fromhex(v["expected_bytes"])
    if v["protocol"] in ("P1", "P2"):
        code = (q.get("save_code") or 0) if q["long_press"] else q["code"]
        actual = codec.function(
            code, action=v["action"].removesuffix(" save"), single=v["protocol"] == "P1"
        )
    elif v["protocol"] == "P_EXT":
        builder = q["builder"]
        if builder == "alarm_list":
            actual = codec.record(5, 1, 0, (0,))
        elif builder == "alarm_delete":
            actual = codec.record(5, 2, 1, (q["number"],))
        elif builder == "alarm_add":
            actual = codec.record(
                5,
                1,
                1,
                tuple(q[k] for k in ("number", "reserved", "hour", "minute", "preset", "repeat")),
            )
        elif builder == "sync_epoch":
            now = datetime.fromtimestamp(
                q["epoch_seconds"], timezone(timedelta(hours=q["offset_hours"]))
            )
            actual = codec.time_sync(now, build=codec.record, first_hex=True)[0]
        else:
            actual = codec.calendar(
                datetime(
                    *(q[k] for k in ("year", "month", "day", "hour", "minute", "second")),
                    tzinfo=UTC,
                ),
                build=codec.record,
            )
    elif v["protocol"] == "P_RX":
        # Reconstruct from the candidate's independently existing literal table.
        event = ACKS[tuple(expected)]
        actual = bytes(next(key for key, value in ACKS.items() if value == event))
    else:
        assert v["protocol"] == "ALGORITHM_ONLY"
        assert codec.is_valid_crc(bytes.fromhex(q["crc_input_hex"]) + expected)
        return
    assert actual == expected


def test_majestic_epoch_first_eight_hex_digits_and_legacy_default():
    now = datetime.fromtimestamp(0x100000000, UTC)
    assert codec.time_sync(now, first_hex=True)[0].hex() == "6e0c200802011000000000b5"
    with pytest.raises(OverflowError):
        codec.time_sync(now)
