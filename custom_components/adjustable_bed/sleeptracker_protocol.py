"""Sleeptracker Smart Bed 3.6.2 direct BLE grammar (S02 accepted artifact).

This processor transport is independent of Adjustable Lite/Nordic UART.
Only local bed commands belong here, never provisioning, audio or cloud calls.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
type Axis = Literal["head", "foot", "lumbar"]
type FanSide = Literal["left", "right", "both"]

SERVICE_UUID = "f6380280-6d90-442c-8feb-3aec76948f06"
SERVICES = (SERVICE_UUID, "0000180a-0000-1000-8000-00805f9b34fb")
HELLO_UUID = "4bc4783d-64a3-45b0-9a4a-06cb7713e32b"
AUTH_UUID = "a5a25fb5-500f-436b-8d36-447bc5f30a29"
CONTROL_UUID = "3d91d13b-2310-43d1-b991-9e915b047653"
FIRMWARE_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
FOUNDATIONS = (
    "CalKing",
    "Full",
    "King",
    "NonTouchingTwins",
    "Queen",
    "SplitKing",
    "Twin",
    "Unspecified",
)
FREQUENCIES = (28, 40, 52, 68, 88)
PRESETS = ("all_flat", "zero_g", "anti_snore", "user_favorite", "tv_pc", "favorite_2")


@dataclass(frozen=True, slots=True)
class Model:
    """Persisted app layout, independently selected from hello aliases."""

    id: int
    label: str
    controller_model: str
    lumbar: bool = True
    extra_presets: bool = True
    zones: bool = True
    premium: bool = False
    breeze: bool = False


MODELS = {
    "ergo": Model(17, "Ergo", "GOOD", extra_presets=False, zones=False),
    "ergo_smart": Model(18, "Ergo Smart", "BETTER"),
    "ergo_prosmart": Model(19, "Ergo ProSmart / ProSmart Air", "BEST", premium=True),
    "activebreeze_large": Model(
        20, "ActiveBreeze large", "ACTIVE_BREEZE_BIG", premium=True, breeze=True
    ),
    "activebreeze_small": Model(
        21, "ActiveBreeze small", "ACTIVE_BREEZE_SMALL", premium=True, breeze=True
    ),
    "slim": Model(22, "Slim", "SLIM_GOOD", extra_presets=False, zones=False),
    "slim_smart": Model(23, "Slim Smart", "SLIM_BETTER"),
    "slim_prosmart": Model(24, "Slim ProSmart", "SLIM_BEST", premium=True),
    "unknown": Model(0, "Generic app layout (two axes)", "NONE", lumbar=False),
}
HELLO_MODELS = {
    "GOOD": 17,
    "SLIM_GOOD": 17,
    "BETTER": 18,
    "SLIM_BETTER": 18,
    "BEST": 19,
    "SLIM_BEST": 19,
    "ACTIVE_BREEZE_BIG": 20,
    "ACTIVE_BREEZE_SMALL": 21,
}


@dataclass(frozen=True, slots=True)
class Request:
    """Finite, typed public action. No arbitrary JSON or firmware commands."""

    kind: Literal[
        "preset", "climate", "wave", "wind_down", "local_animation", "identify", "massage"
    ]
    preset: str = "all_flat"
    save: bool = False
    fan_side: FanSide = "both"
    heating: bool = False
    level: int = 0
    constant: bool = True
    frequency: int = 52
    minutes: int = 30
    mode: int = 1
    massage_action: Literal["head", "foot", "pattern", "28Hz", "40Hz", "off"] = "off"


def validate_request(request: Request, model: Model) -> None:
    """Validate all fields before a service operates any paired receiver."""
    if request.kind == "preset":
        available = PRESETS if model.extra_presets else PRESETS[:4]
        if model.id == 0:
            available = PRESETS[:5]
        if request.preset not in available or (request.save and request.preset == "all_flat"):
            raise ValueError("Preset is unavailable for the selected Sleeptracker layout")
    elif request.kind == "climate":
        if not model.breeze or request.fan_side not in ("left", "right", "both"):
            raise ValueError("ActiveBreeze climate controls require an ActiveBreeze layout")
        if type(request.level) is not int or request.level not in range(4):
            raise ValueError("ActiveBreeze level must be 0 through 3")
    elif request.kind == "wave":
        if not model.premium:
            raise ValueError("Relaxation requires a ProSmart or ActiveBreeze layout")
        if (
            request.frequency not in FREQUENCIES
            or type(request.minutes) is not int
            or request.minutes not in range(5, 106, 5)
        ):
            raise ValueError("Wave uses 28/40/52/68/88 Hz and 5–105 minutes in steps of 5")
    elif request.kind == "massage":
        if request.massage_action not in ("head", "foot", "pattern", "28Hz", "40Hz", "off"):
            raise ValueError("Unknown Sleeptracker massage action")
        if request.massage_action in ("head", "foot") and not model.zones:
            raise ValueError("This layout exposes pattern massage only")
        if request.massage_action in ("28Hz", "40Hz") and not model.premium:
            raise ValueError("Direct frequency requires ProSmart or ActiveBreeze")
    elif request.kind in ("wind_down", "local_animation"):
        if not model.premium or (request.kind == "wind_down" and request.mode not in (1, 2)):
            raise ValueError("Select a supported ProSmart/ActiveBreeze relaxation mode")
    elif request.kind == "identify":
        if request.mode not in (1, 2):
            raise ValueError("Unknown light identification route")
    else:
        raise ValueError("Unknown Sleeptracker action")


def pretty(value: dict[str, Json], indent: str = "") -> str:
    """Match JsonDict's valid-object layout; safely escape untrusted strings."""
    lines = [indent + "{"]
    child_indent = indent + "    "
    for key, item in value.items():
        prefix = child_indent + json.dumps(key) + ": "
        encoded = (
            "\n" + pretty(item, child_indent)
            if isinstance(item, dict)
            else json.dumps(item, ensure_ascii=False, separators=(",", ": "))
        )
        lines.append(prefix + encoded + ",")
    if len(lines) > 1:
        lines[-1] = lines[-1][:-1]
    lines.append(indent + "}")
    return "\n".join(lines)


def envelope(
    request: dict[str, Json] | None,
    token: str | None,
    *,
    operation: str = "motor-command",
    compact: bool = False,
) -> bytes:
    value: dict[str, Json] = {"wsCommand": operation}
    if token is not None:
        value["authToken"] = token
    if request is not None:
        value["request"] = request
    text = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) if compact else pretty(value)
    )
    return text.encode("utf-8")


def movement(axis: Axis, action: str, side: int, token: str | None) -> bytes:
    value: dict[str, Json] = {"position": {"side": side, "location": axis}, "action": action}
    if action != "stop":
        value.update(ticks=4, waitForResponse=False)
    return envelope({"movement": value}, token)


def preset(name: str, side: int, token: str | None, *, save: bool = False) -> bytes:
    value: dict[str, Json] = (
        {"position": {"side": side}, "name": name}
        if save
        else {"name": name, "position": {"side": side}}
    )
    return envelope(
        {"savePreset" if save else "preset": value},
        token,
        operation="motor-control" if save else "motor-command",
    )


def massage(action: str, side: int, token: str | None, *, location: str | None = None) -> bytes:
    position: dict[str, Json] = {"side": side}
    if location is not None:
        position["location"] = location
    return envelope({"massage": {"action": action, "value": 1, "position": position}}, token)


def stop(side: int, token: str | None, *, all_features: bool = True) -> bytes:
    return envelope(
        {"stop": {"action": "all" if all_features else "massage", "position": {"side": side}}},
        token,
    )


def light(
    side: int, token: str | None, *, restricted: bool, off: bool = False, identify: bool = False
) -> bytes:
    if identify:
        return (
            '{"side" : 1, "command" : "light", "params" : {"operation":"'
            + ("off" if off else "toggle")
            + '"} }'
        ).encode()
    if restricted:
        return pretty(
            {"command": "light", "params": {"operation": "off" if off else "toggle"}}
        ).encode()
    return envelope({"safetyLight": {"action": "toggle", "position": {"side": side}}}, token)


def fan(request: Request, token: str | None) -> bytes:
    sides = ("left", "right") if request.fan_side == "both" else (request.fan_side,)
    value: dict[str, Json] = {"position": {"side": 0}}
    for side in sides:
        value.update(
            {
                side + "IsConstant": request.constant,
                side + "IsHeating": request.heating,
                side + "Level": request.level,
            }
        )
    for side in sides:
        value[side + "Timer"] = 3600 if request.heating else 36000
    return envelope({"fanControl": value}, token, compact=True)


def animation(statements: list[Json], token: str | None) -> bytes:
    return envelope(
        {"statement": {"type": "sequence", "statements": statements}},
        token,
        operation="motor-animation",
        compact=True,
    )


def wave(request: Request, side: int, token: str | None) -> bytes:
    strength = {28: 4, 40: 5, 52: 3, 68: 2, 88: 1}[request.frequency]
    return animation(
        [
            {
                "type": "command",
                "command": {
                    "massage": {
                        "position": {"side": side, "location": "ignore_this"},
                        "action": "pulse",
                        "value": strength,
                        "duration": request.minutes * 600,
                    }
                },
                "startDelayMs": 0,
            },
            {
                "type": "command",
                "startDelayMs": 500,
                "command": {
                    "massage": {
                        "position": {"side": side},
                        "action": "frequency",
                        "value": request.frequency,
                    }
                },
            },
        ],
        token,
    )


def local_animation(side: int, token: str | None) -> bytes:
    """Shipped local bed statements, independently usable without media/audio."""
    position: dict[str, Json] = {"side": side}

    def statement(command: dict[str, Json], delay: int) -> Json:
        return {"type": "command", "command": command, "startDelayMs": delay}

    def counts(values: tuple[tuple[str, int], ...], delay: int) -> Json:
        return statement(
            {
                "pulseCounts": {
                    "position": position,
                    "pulseCountSettings": [
                        {"location": axis, "pulseCount": count} for axis, count in values
                    ],
                }
            },
            delay,
        )

    return animation(
        [
            statement({"preset": {"position": position, "name": "all_flat"}}, 0),
            counts((("head", 4000), ("foot", 5000)), 11000),
            statement({"massage": {"position": position, "action": "toggle"}}, 0),
            statement({"massage": {"position": position, "action": "toggle"}}, 0),
            counts((("head", 6000),), 7000),
            statement({"preset": {"position": position, "name": "all_flat"}}, 34000),
        ],
        token,
    )


def authentication(mac: str, challenge: str, salt: bytes | None = None) -> bytes:
    """Run in an executor: bcrypt is CPU work, and the result is secret."""
    import bcrypt

    # Shipped bcrypt consumes the first 72 bytes (including its implicit NUL).
    hashed = bcrypt.hashpw(
        (mac.upper() + challenge).encode()[:72], salt or bcrypt.gensalt(rounds=10, prefix=b"2a")
    )
    password = base64.b64encode(hashed).decode("ascii")
    return (
        '{"type" : "authenticate", "password" : "'
        + password
        + '", "clientId" : "sleeptracker-android-tsi"}'
    ).encode()


def frames(payload: bytes, limit: int) -> tuple[bytes, ...]:
    if not 1 <= limit <= 500:
        raise ValueError("BLE payload capacity must be 1–500 bytes")
    return tuple(
        (
            len(chunk)
            | (0x8000 if offset == 0 else 0)
            | (0x4000 if offset + len(chunk) == len(payload) else 0)
        ).to_bytes(2, "little")
        + chunk
        for offset in range(0, len(payload), limit)
        if (chunk := payload[offset : offset + limit])
    )


class Reassembler:
    """Per-channel bounded replies; ignore unused sequence bits as the app does."""

    def __init__(self) -> None:
        self.buffer: bytearray | None = None

    def feed(self, frame: bytes) -> bytes | None:
        if len(frame) < 2:
            raise ValueError("Short Sleeptracker frame")
        header = int.from_bytes(frame[:2], "little")
        length = header & 0x1FF
        if len(frame) != length + 2:
            self.buffer = None
            raise ValueError("Invalid Sleeptracker frame length")
        if header & 0x8000:
            self.buffer = bytearray()
        if self.buffer is None or len(self.buffer) + length > 65536:
            self.buffer = None
            raise ValueError("Orphan or oversized Sleeptracker reply")
        self.buffer.extend(frame[2:])
        if header & 0x4000:
            result = bytes(self.buffer)
            self.buffer = None
            return result
        return None


def _non_null_fields(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    fields: dict[str, Json] = {}
    for key, value in pairs:
        # Validate each wire value before a duplicate key can discard it.
        _validate_arrays(value)
        if value is not None:
            fields[key] = value
    return fields


def _validate_arrays(value: Json) -> None:
    """Reject nested arrays that stall the app's parser, including unused fields."""
    if isinstance(value, dict):
        for item in value.values():
            _validate_arrays(item)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, list):
                raise ValueError("Sleeptracker reply contains a nested array")
            _validate_arrays(item)


def json_object(payload: bytes) -> dict[str, Json]:
    value = json.loads(payload, object_pairs_hook=_non_null_fields)
    if not isinstance(value, dict) or not value:
        raise ValueError("Sleeptracker reply must be a nonempty object")
    return cast(dict[str, Json], value)


def child(value: dict[str, Json], key: str) -> dict[str, Json]:
    item = value.get(key)
    if item is None:
        return {}
    if not isinstance(item, dict):
        raise ValueError("Sleeptracker field must be an object")
    return item


def integer(value: Json, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    number = int(value)
    return number if abs(number) <= 2147483647 else default


def boolean(value: Json) -> bool:
    return str(value).lower() == "true"


def wind_down_running(details: dict[str, Json]) -> bool | None:
    """The Wind Down screen consumes the first parsed snapshot, without side matching."""
    snapshots = child(details, "body").get("snapshots")
    if snapshots is None:
        return None
    if not isinstance(snapshots, list):
        raise ValueError("Sleeptracker snapshots must be a list")
    first = next((item for item in snapshots if item is not None), None)
    if first is None:
        return None
    if not isinstance(first, dict):
        raise ValueError("Sleeptracker snapshot must be an object")
    return integer(first.get("windDownMode")) != 0


class RemoteSnapshotError(ValueError):
    """Ordinary scalar snapshots cannot be consumed by the remote screen."""


def status(
    value: dict[str, Json], selected_snapshot: int, previous: dict[str, Json]
) -> dict[str, Json]:
    """Remote reset rules and fan partial-update rules are deliberately distinct."""
    snapshots = child(value, "body").get("snapshots", [])
    if not isinstance(snapshots, list):
        raise ValueError("Sleeptracker snapshots must be a list")
    snapshots = [item for item in snapshots if item is not None]
    if any(not isinstance(item, dict) for item in snapshots):
        if all(isinstance(item, (dict, str, int, float, bool)) for item in snapshots):
            raise RemoteSnapshotError("Sleeptracker snapshot must be an object")
        raise ValueError("Sleeptracker snapshot must be an object")
    updates: dict[str, Json] = {
        "massage_pattern": 0,
        "massage_head_strength": 0,
        "massage_foot_strength": 0,
        "light_on": False,
    }
    if len(snapshots) == 1 and isinstance(snapshot := snapshots[0], dict):
        updates["massage_pattern"] = integer(snapshot.get("massagePattern"))
        updates["light_on"] = boolean(snapshot.get("safetyLightOn"))
        for axis in ("head", "foot"):
            updates["massage_" + axis + "_strength"] = integer(
                child(child(snapshot, axis), "massage").get("strength")
            )
        fan_value = child(snapshot, "fan")
        for side in ("left", "right"):
            if (key := side + "IsHeating") in fan_value:
                updates[side + "_heating"] = boolean(fan_value[key])
            if (key := side + "Level") in fan_value:
                updates[side + "_level"] = max(0, min(3, integer(fan_value[key])))
    elif len(snapshots) == 2:
        for snapshot in snapshots:
            if (
                isinstance(snapshot, dict)
                and integer(snapshot.get("side"), -1) == selected_snapshot
                and "massagePattern" in snapshot
            ):
                updates["massage_pattern"] = integer(snapshot["massagePattern"])
    return {**previous, **updates}


def manufacturer_metadata(data: Mapping[int, bytes], address: str) -> dict[str, Json]:
    """HA already separates the company bytes from its manufacturer payload."""
    for company in (0xEF01, 0x01EF):
        if (payload := data.get(company)) is None or len(payload) < 8:
            continue
        target = address.replace(":", "").replace("-", "")[-6:].lower()
        return {
            "advertised_flags": payload[0],
            "advertised_provisioned": bool(payload[0] & 1),
            "advertised_board_matches_target": payload[1:4].hex() == target,
            "advertised_model_id": payload[4],
            "advertised_version_octets": list(payload[5:8]),
        }
    return {}
