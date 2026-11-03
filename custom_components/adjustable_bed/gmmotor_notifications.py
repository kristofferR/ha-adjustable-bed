"""GM Control P1 semantic events, before controller/UI consumption.

Length predicates and empty DTOs follow the accepted 4.6.6 artifact. Required
field failures are caught at the BLE callback boundary, not silently defaulted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gmmotor_protocol import MalformedNotification

type Value = None | bool | int | float | str | list[Value] | dict[str, Value]


@dataclass(frozen=True, slots=True)
class Event:
    """One source event; values carry no inferred physical or medical meaning."""

    name: str
    value: Value = None


_ACKS = {
    bytes.fromhex("6e09010078"): "clock_capability",
    bytes.fromhex("6e0e00037f"): "light_capability",
    bytes.fromhex("6e1a000189"): "aroma_capability",
    bytes.fromhex("6e07010177"): "alarm_added",
    bytes.fromhex("6e07010278"): "alarm_cancelled",
    bytes.fromhex("6e16010186"): "music_capability",
    bytes.fromhex("6e90c101c0"): "detection_capability",
    # The pure branch exists; FrameBuffer rejects its non-progressing length.
    bytes.fromhex("6e2100008f"): "snore_capability",
    bytes.fromhex("6e23018416"): "box_locked",
    bytes.fromhex("6e23008415"): "box_unlocked",
    bytes.fromhex("6e23a06e9f"): "snore_stop_music",
}


def _desk() -> dict[str, Value]:
    return {
        "unit": "cm",
        "mode": "shortPress",
        "locked": False,
        "max_inches": 49.21,
        "min_inches": 23.6,
        "min_cm": 60.0,
        "max_cm": 125.0,
        "height": 23.6,
        "monitor_height": 60.0,
        "sedentary_setting": 10,
        "online": 0,
        "sedentary_countdown": 0,
        "memory_1": 0,
        "memory_2": 0,
    }


def _decimal(first: int, second: int) -> float:
    return (100 * first + second) / 10


def common(frame: bytes) -> tuple[Event, ...]:
    """Decode source common frames, including the checksum-free legacy branch."""
    size = len(frame)
    if size == 5:
        if name := _ACKS.get(frame):
            return (Event(name),)
        if frame[:2] != b"\x6e\x90":
            return ()
        selector, value = frame[2:4]
        group = selector >> 4
        if selector == 0:
            return (Event("protocol_version", value),)
        if group == 1:
            return (Event("bed_mode", selector & 15),)
        if group == 3:
            return (
                Event(
                    "motor_angle",
                    {"no": (selector >> 2) & 3, "status": selector & 3, "angle": value},
                ),
            )
        if group == 10:
            return (
                Event(
                    "massage_mode",
                    {
                        "mode": (selector >> 1) & 7,
                        "massage_1": value & 7,
                        "massage_2": (value >> 3) & 7,
                        "massage_3": ((selector & 1) << 2) | (value >> 6),
                    },
                ),
            )
        if group == 11:
            return (
                Event("music_usb", bool(selector & 1)),
                Event("music_play", bool(value & 128)),
                Event("music_shake", bool(value & 64)),
                Event("music_ble", bool(value & 32)),
            )
        if selector == 194:
            return (
                Event(
                    "detection_status",
                    {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start"),
                ),
            )
        if selector in (195, 196, 197, 198):
            # The source constructs an empty DTO, not decoded fault bits.
            return (Event("detection_message", {}),)
        if selector in (209, 210):
            return (Event("music_volume" if selector == 209 else "music_shake_gear", value),)
    if size == 7 and frame[1] == 144:
        desk = _desk()
        desk.update(
            unit="cm" if frame[3] == 0 else "inch",
            height=_decimal(frame[4], frame[5]),
            monitor_height=_decimal(frame[4], frame[5]),
        )
        return (Event("desk_height", desk),)
    if size == 16:
        desk = _desk()
        desk["unit"] = "cm" if frame[2] == 0 else "inch"
        for key, index in (
            ("min_inches", 3),
            ("max_inches", 5),
            ("min_cm", 7),
            ("max_cm", 9),
            ("height", 11),
            ("monitor_height", 13),
        ):
            desk[key] = _decimal(frame[index], frame[index + 1])
        return (Event("desk_data", desk),)
    return ()


def extra(frame: bytes) -> tuple[Event, ...]:
    """Decode category 20 with the artifact's exact branch/length predicates."""
    try:
        return _extra(frame)
    except IndexError as err:
        raise MalformedNotification("P1 notification lacks a required field") from err


def _extra(b: bytes) -> tuple[Event, ...]:
    size = len(b)
    if b[2] != size:
        return ()
    category, sub, status = b[3], b[4], b[5]
    events: list[Event] = []
    if category == 10:
        return (Event("check", [sub, list(b)]),) if sub in range(1, 7) else ()
    if category == 5 and sub == 1:
        record: dict[str, Value] = {
            key: b[i]
            for key, i in zip(
                ("id", "repeat", "hour", "minute", "mode", "status"), range(6, 12), strict=True
            )
        }
        return (
            (Event("alarm_list" if status == 2 else "alarm_escalation", record),)
            if status in (2, 3)
            else ()
        )
    if status not in (2, 3):
        return ()
    if category == 1:
        if sub == 2 and size > 9:
            events.append(
                Event(
                    "motor_height",
                    {
                        "height": (256 * b[7] + b[8]) / 10,
                        "type": b[9],
                        "angle": b[10] if size > 11 else -1,
                        "monitor_height": (256 * b[11] + b[12]) / 10 if size > 13 else 0.0,
                    },
                )
            )
        if sub == 3 and size > 8:
            events.append(Event("motor_angle", {"position": b[6], "angle": b[8]}))
    elif category == 2:
        if sub == 1 and (size - 7) % 2 == 0:
            for i in range(6, size - 1, 2):
                if b[i] in (1, 2):
                    events.append(
                        Event(
                            "massage_head_strength" if b[i] == 1 else "massage_foot_strength",
                            b[i + 1],
                        )
                    )
        if size > 7 and sub in (2, 4, 5, 6):
            events.append(
                Event(
                    {
                        2: "massage_mode",
                        4: "massage_frequency",
                        5: "music_shake",
                        6: "massage_power",
                    }[sub],
                    b[7] == 1 if sub == 6 else b[7],
                )
            )
    elif category == 3 and sub == 1 and size > 7:
        events.append(Event("white_light", b[7] == 1))
    elif category == 4:
        if sub == 1 and size > 9:
            events.append(Event("rgb_color", [b[7] / 255, b[8] / 255, b[9] / 255]))
        if sub == 2 and size > 8:
            events.append(Event("rgb_timer", 60 * b[7] + b[8]))
        if sub in (3, 4) and size > 7:
            events.append(Event("rgb_motion" if sub == 3 else "rgb_power", b[7] == 1))
    elif category == 6:
        if sub in (1, 2) and size > 7:
            events.append(Event("anti_snore" if sub == 1 else "get_off_bed", b[7] == 1))
        if sub == 3:
            if size < 8:
                raise MalformedNotification("Invalid sleep-name sublist range")
            events.append(Event("sleep_name", list(b[7:-1])))
        if sub == 4 and size > 8 and b[7] == b[8] == 1:
            events.append(Event("snore_stop_music"))
        if sub == 5 and size > 7:
            value = b[8]
            if b[7] in (1, 2):
                events.append(Event("snore_count" if b[7] == 1 else "snore_time", value))
    elif category == 7 and sub == 2 and size > 7:
        events.append(Event("box_locked" if b[7] == 1 else "box_unlocked"))
    elif category == 9 and size > 7:
        if sub in (1, 3, 4):
            events.append(Event({1: "music_play", 3: "music_ble", 4: "music_usb"}[sub], b[7] == 1))
        if sub == 2 and b[6] in (2, 3):
            events.append(Event("music_volume" if b[6] == 2 else "music_volume_silent", b[7]))
    elif category == 11 and sub in (1, 2, 4):
        events.append(
            Event(
                {1: "press_mode", 2: "standard_split_control", 4: "same_split_control"}[sub],
                b[7] == 2 if sub == 2 else b[7],
            )
        )
    elif category == 13:
        specs = {
            1: ("blanket_power", 7),
            2: ("blanket_delay", 9),
            5: ("blanket_mode", 9),
            6: ("blanket_mite_removal", 7),
            7: ("blanket_sleep", 20),
            8: ("blanket_setting", 7),
            9: ("blanket_live", 11),
        }
        if sub in specs and size > specs[sub][1]:
            events.append(Event(specs[sub][0], {}))
    elif category == 14 and sub == 1 and size > 7:
        events.append(Event("fan_gear", b[7]))
    elif category == 15 and size >= 20:
        desk = _desk()
        bits = b[6]
        desk.update(
            unit="inch" if bits & 1 else "cm",
            mode="longPress" if bits & 8 else "shortPress",
            locked=bool(bits & 16),
        )
        for key, index in (
            ("min_inches", 7),
            ("max_inches", 9),
            ("min_cm", 11),
            ("max_cm", 13),
            ("height", 15),
            ("monitor_height", 17),
        ):
            desk[key] = _decimal(b[index], b[index + 1])
        if size >= 23:
            desk.update(online=b[19], sedentary_setting=b[20], sedentary_countdown=b[21])
        if size >= 27:
            desk.update(memory_1=_decimal(b[22], b[23]), memory_2=_decimal(b[24], b[25]))
        events.append(Event("desk_data", desk))
    elif category == 16:
        if sub == 1 and size > 7:
            events.append(Event("atomization_open", b[7]))
        if sub == 2 and size > 8:
            events.append(Event("atomization_time", b[8]))
    elif category == 17:
        if sub == 2 and size > 8:
            value = 256 * b[7] + b[8]
            kind = 0 if value == 0 else 1 if value == 65535 else 2
            events.append(
                Event(
                    "heating_time",
                    {"position": b[6], "type": kind, "time_sum": value if kind == 2 else 0},
                )
            )
        if sub == 3 and size > 8:
            events.append(Event("heating_temperature", {"position": b[6], "temperature": b[8]}))
        if sub == 5 and size > 6:
            events.append(Event("heating_model", b[6]))
    return tuple(events)


def desk21(b: bytes) -> tuple[Event, ...]:
    """The distinct 21/15 desk receive wrapper, with end-relative fields."""
    try:
        if b[2] != len(b) or b[3] != 15 or b[5] not in (2, 3):
            return ()
        value: dict[str, Value]
        if b[4] == 1 and len(b) > 9:
            value = {"height": (256 * b[6] + b[7]) / 10, "type": 2}
            name = "motor_height"
        elif b[4] == 6 and len(b) >= 12:
            value = {
                "online": b[-12] == 1,
                "height": (256 * b[-11] + b[-10]) / 10,
                "sedentary_setting": 256 * b[-9] + b[-8],
                "sedentary_countdown": 256 * b[-7] + b[-6],
            }
            name = "desk_pair"
        else:
            return ()
        if len(b) >= 10:
            value["desk_code"] = int.from_bytes(b[-5:-1], "big")
        return (Event(name, value),)
    except IndexError as err:
        raise MalformedNotification("P1 desk notification lacks a required field") from err
