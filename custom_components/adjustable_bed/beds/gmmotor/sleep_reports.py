"""GM Control MM/SXB compressed day/month report branches and cache identities."""

from __future__ import annotations

import gzip
import io
import json
import zlib
from dataclasses import dataclass
from datetime import date

from .notifications import Value
from .protocol import MalformedNotification
from .sleep_dto import parse
from .sleep_protocol import new_day_layout

# HA resource policy, not an artifact-defined report-size limit.
MAX_REPORT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Report:
    """One source stream wrapper and its optional normal-mode cache key."""

    stream: str
    wrapper: Value
    cache_key: str | None
    cache_kind: str | None


def decode_report(
    payload: bytes, *, sxb: bool, kind: int, side: int, session_side: int, requested_date: date
) -> Report | None:
    """Decode gzip then Latin1 code points, preserving the source ordering.

    SXB always parses the old day DTO first. Its missing-day gate and version
    exception remain distinct from normal mode. All errors are reported to the
    controller to log/drop, matching the outer source handler's error boundary.
    """
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
            raw = compressed.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise MalformedNotification("Sleep report exceeds the HA decode budget")
        value: Value = json.loads(raw.decode("latin-1"))
        if kind not in (1, 2):
            return None
        if kind == 2:
            if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
                raise MalformedNotification("Month report must contain JSON objects")
            records = [
                parse("0x6e2ecc" if sxb else "0x6e887c", v) for v in value if isinstance(v, dict)
            ]
            wrapper: Value = {
                "class": "SxbSleepMonthReportRespWrapBean"
                if sxb
                else "RMSleepMonthReportRespWrapBean",
                "fields": {"0x7": session_side, "0xb": records},
            }
            return Report(
                "0x43" if sxb else "0x17",
                wrapper,
                None if sxb else f"{requested_date:%Y-%m}-{session_side}",
                None if sxb else "month",
            )
        if not isinstance(value, dict):
            raise MalformedNotification("Day report must be a JSON object")
        parsed = parse("0x6e1050" if sxb else "0x6e5c0c", value)
        name = "SxbSleepDayReportRespWrapBean" if sxb else "RMSleepDayReportRespWrapBean"
        stream = "0x47" if sxb else "0x1b"
        if sxb:
            version = value.get("algorithmVersion")
            if not isinstance(version, str):
                raise MalformedNotification("SXB day report lacks its algorithm version")
            if new_day_layout(version):
                parsed = parse("0x6ddc28", value)
                name = "SxbSleepDayReportRespWrapBean2"
                stream = "0x4b"
            if value.get("day") is None:
                return None
        wrapper = {"class": name, "fields": {"0x7": side, "0xb": parsed}}
        return Report(
            stream,
            wrapper,
            None if sxb else f"{requested_date:%Y-%m-%d}-{session_side}",
            None if sxb else "day",
        )
    except (OSError, EOFError, ValueError, TypeError, OverflowError, zlib.error) as err:
        raise MalformedNotification("Invalid compressed sleep report") from err
