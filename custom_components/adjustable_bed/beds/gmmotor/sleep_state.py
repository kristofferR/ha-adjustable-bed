"""GM Control sleep JSON dispatch and ordered stream/clock/follow-up effects."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .notifications import Value
from .protocol import MalformedNotification
from .sleep_dto import parse
from .sleep_protocol import SleepCommand, response_command


@dataclass(frozen=True, slots=True)
class Stream:
    """One source stream publication, identified by its artifact-local slot."""

    field: str
    value: Value


@dataclass(frozen=True, slots=True)
class ClockUpdate:
    fields: dict[str, Value]


@dataclass(frozen=True, slots=True)
class Followup:
    command: SleepCommand
    delayed: bool = False


@dataclass(frozen=True, slots=True)
class ReportSize:
    size: int


type Effect = Stream | ClockUpdate | Followup | ReportSize


def fields(value: Value) -> dict[str, Value]:
    """Read an already validated source DTO's named field storage."""
    if not isinstance(value, dict) or not isinstance(value.get("fields"), dict):
        raise MalformedNotification("Expected a parsed sleep DTO")
    result = value["fields"]
    assert isinstance(result, dict)
    return result


def dispatch(
    payload: bytes,
    *,
    sxb: bool,
    active: str | None,
    clock: dict[str, Value],
    session_side: int,
    report_type: int,
) -> tuple[Effect, ...]:
    """Decode byte code points, then the exact source selector precedence.

    OTA publications are outside the integration boundary. Their selectors keep
    their precedence so a shadowed supported branch is never falsely credited.
    Ordinary parse failures are safe HA callback errors; report parsing has its
    separate outer catch boundary in beds/gmmotor/sleep_reports.py.
    """
    try:
        text = payload.decode("latin-1")
        root: Value = json.loads(text)
    except (ValueError, TypeError) as err:
        raise MalformedNotification("Sleep response is not valid JSON") from err
    if not isinstance(root, dict):
        raise MalformedNotification("Sleep response must be a JSON object")
    command = response_command(text, sxb=sxb, active=active)
    if command is None or command.startswith(("q_ota", "s_ota")):
        return ()
    schemas = (
        {
            "s_time": ("0x6dcea0", "0x2f"),
            "q_time": ("0x6dc42c", "0x33"),
            "q_part": ("0x6dc28c", "0x37"),
            "s_part": ("0x6dc28c", "0x37"),
            "q_realtime": ("0x6dbc44", "0x3b"),
            "q_report": ("0x6db8d0", ""),
            "s_init": ("0x6db47c", "0x57"),
            "q_sens": ("0x6dabd4", "0x5f"),
            "s_sens": ("0x6dabd4", "0x5f"),
            "q_antiSnore": ("0x6da74c", "0x63"),
            "s_antiSnore": ("0x6da74c", "0x63"),
        }
        if sxb
        else {
            "s_time": ("0x6e4fa4", "0xb"),
            "q_part": ("0x6e4e0c", "0xf"),
            "s_part": ("0x6e4e0c", "0xf"),
            "q_realtime": ("0x6e4a54", "0x7"),
            "q_report": ("0x6e477c", ""),
            "s_init": ("0x6db47c", "0x57"),
        }
    )
    if command not in schemas:
        return ()
    address, stream = schemas[command]
    parsed = parse(address, root)
    storage = fields(parsed)
    if sxb and command == "s_time":
        effects: list[Effect] = [Stream(stream, parsed)]
        value = storage["0xf"]
        if value is not None:
            val = fields(value)
            effects.append(ClockUpdate({"0x7": val["0xf"], "0xb": val["0xb"]}))
        effects.append(Followup("q_time"))
        return tuple(effects)
    if sxb and command == "q_time":
        updated = dict(clock)
        value = storage["0xf"]
        updates: dict[str, Value] = {}
        if value is not None:
            val = fields(value)
            updates = {"0xf": val["0x7"], "0x13": val["0xb"]}
            updated.update(updates)
        return (
            ClockUpdate(updates),
            Stream(stream, {"class": "SxbQueryDeviceTimeVal", "fields": updated}),
            Followup("q_part"),
        )
    if sxb and command == "s_part":
        storage["0x17"] = True
    if command == "q_report":
        value = storage["0xf"]
        if value is None:
            return ()
        size = fields(value)["0x7"]
        if size is None:
            return ()
        if type(size) is not int:
            raise MalformedNotification("Sleep report size must be an integer")
        assert isinstance(size, int)
        effects = [ReportSize(size)]
        if size > 0:
            effects.append(Followup("q_report_allow", delayed=True))
        else:
            wrapper: Value = {
                "class": "SxbSleepReportSizeRespWrapBean"
                if sxb
                else "RMSleepReportSizeRespWrapBean",
                "fields": {"0x7": session_side, "0xf": report_type, "0x17": size},
            }
            effects.append(Stream("0x3f" if sxb else "0x13", wrapper))
        return tuple(effects)
    return (Stream(stream, parsed),)
