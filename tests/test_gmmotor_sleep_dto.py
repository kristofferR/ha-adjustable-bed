"""GM Control sleep DTO casts, null branches and compressed report boundaries."""

import gzip
import json
from datetime import date

import pytest

from custom_components.adjustable_bed.gmmotor_protocol import MalformedNotification
from custom_components.adjustable_bed.gmmotor_sleep_dto import parse
from custom_components.adjustable_bed.gmmotor_sleep_reports import decode_report


def test_part_dto_uses_int_id_and_numeric_value() -> None:
    assert parse("0x6e4e0c", {"id": 7.9, "cmd": "q_part", "val": 3.25}) == {
        "class": "RMSleepPartRespBean",
        "fields": {"0x7": 7, "0xb": None, "0xf": "q_part", "0x13": 3.25},
    }
    assert parse("0x6e4e0c", {"id": 1, "cmd": None, "val": None}) == {
        "class": "RMSleepPartRespBean",
        "fields": {"0x7": 1, "0xb": None, "0xf": None, "0x13": None},
    }


def test_realtime_modes_do_not_interchange_strings_and_numeric_lists() -> None:
    normal = parse("0x6e4a54", {"id": 7, "cmd": "q_realtime", "val": {"L": "1-2", "R": "3-4"}})
    assert isinstance(normal, dict)
    with pytest.raises(MalformedNotification, match="string"):
        parse("0x6e4a54", {"id": 7, "cmd": "q_realtime", "val": {"L": [1, 2], "R": [3, 4]}})
    assert parse("0x6dc0a8", {"L": [1, 2.25], "R": [3, 4]}) == {
        "class": "SxbSleepRealtimeRespValBean",
        "fields": {"0x7": [1, 2.25], "0xb": [3, 4]},
    }


def test_required_map_and_invalid_numeric_rejected_safely() -> None:
    with pytest.raises(MalformedNotification, match="non-null map"):
        parse("0x6e477c", {"id": 7, "cmd": "q_report", "val": None})
    with pytest.raises(MalformedNotification, match="number"):
        parse("0x6e4e0c", {"id": True, "cmd": "q_part", "val": 1})
    with pytest.raises(MalformedNotification, match="number"):
        parse("0x6e4e0c", {"id": 7, "cmd": "q_part", "val": "1"})


def report(value, *, sxb: bool, kind: int, side: int = 2):
    return decode_report(
        gzip.compress(json.dumps(value, separators=(",", ":")).encode()),
        sxb=sxb,
        kind=kind,
        side=side,
        session_side=1,
        requested_date=date(2026, 11, 3),
    )


def test_month_wrapper_and_cache_use_session_side() -> None:
    normal = report([], sxb=False, kind=2)
    assert normal is not None
    assert normal.wrapper == {
        "class": "RMSleepMonthReportRespWrapBean",
        "fields": {"0x7": 1, "0xb": []},
    }
    assert normal.cache_key == "2026-11-1"
    sxb = report([], sxb=True, kind=2)
    assert sxb is not None
    assert sxb.wrapper == {
        "class": "SxbSleepMonthReportRespWrapBean",
        "fields": {"0x7": 1, "0xb": []},
    }
    assert sxb.cache_key is None


def test_source_day_gate_differs_between_modes() -> None:
    assert report({"algorithmVersion": "1.0", "day": None}, sxb=True, kind=1) is None
    normal = report({"day": None}, sxb=False, kind=1)
    assert normal is not None
    assert normal.cache_key == "2026-11-03-1"
    assert isinstance(normal.wrapper, dict)
    fields = normal.wrapper["fields"]
    assert isinstance(fields, dict)
    assert fields["0x7"] == 2
    assert report({}, sxb=True, kind=3) is None


def test_malformed_gzip_does_not_escape_the_report_boundary() -> None:
    with pytest.raises(MalformedNotification, match="compressed"):
        decode_report(
            b"not gzip", sxb=True, kind=1, side=2, session_side=1, requested_date=date(2026, 11, 3)
        )
