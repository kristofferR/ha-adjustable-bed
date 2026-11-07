"""SleepIQ 5.4.11 MCR response decoders and bounded command values.

Derived from the frozen APK Protocol Audit MCR/SE evidence; no hardware validation claimed.
"""

from __future__ import annotations

from dataclasses import dataclass

PRESETS = {"Favorite": 1, "Read": 2, "Watch TV": 3, "Flat": 4, "Zero G": 5, "Snore": 6}


def require_payload(payload: bytes, minimum: int) -> None:
    """Reject truncated replies before exposing partially decoded state."""
    if len(payload) < minimum:
        raise ValueError(f"MCR response needs {minimum} bytes, received {len(payload)}")


@dataclass(frozen=True, slots=True)
class FoundationFeatures:
    """Capabilities read from the foundation, never inferred from brand."""

    configuration: int
    foot: bool
    massage: bool
    warming: bool
    light: bool
    generation: str
    model: str

    @property
    def sides(self) -> tuple[str, ...]:
        return ("right", "left") if self.configuration in (1, 2) else ("right",)

    @property
    def presets(self) -> tuple[str, ...]:
        names = ["Favorite", "Flat"]
        if self.model != "FF1":
            names += ["Zero G", "Snore"]
            if self.model == "FF3":
                names += ["Watch TV", "Read"]
        elif self.generation == "360":
            names += ["Snore"]
        return tuple(names)


def decode_system(payload: bytes) -> tuple[FoundationFeatures, dict[str, object]]:
    require_payload(payload, 7)
    flags = payload[3]
    foot, massage, warming, light = (bool(flags & bit) for bit in (4, 2, 8, 16))
    if foot and light:
        generation, model = "360", "FF3" if warming else "FF2"
    elif foot:
        generation, model = "legacy", "FF3" if massage else "FF2"
    else:
        generation, model = "360" if warming or light else "legacy", "FF1"
    features = FoundationFeatures(
        payload[0] if payload[0] < 4 else 0, foot, massage, warming, light, generation, model
    )
    return features, {
        "foundation_model": f"{generation} {model}",
        "foundation_configuration": features.configuration,
        "foundation_dual_board": bool(flags & 1),
        "foundation_board_revision": payload[4] & 15,
        "foundation_light_intensity_right": int.from_bytes(payload[1:2], signed=True),
        "foundation_light_intensity_left": int.from_bytes(payload[2:3], signed=True),
        "foundation_underperforming_left": bool(payload[6] & 4),
        "foundation_underperforming_right": bool(payload[6] & 8),
    }


def decode_foundation(payload: bytes) -> dict[str, object]:
    require_payload(payload, 15)
    state: dict[str, object] = {
        "foundation_moving": bool(payload[0] & 1),
        "foundation_needs_homing": bool(payload[0] & 32),
        "foundation_configured": bool(payload[0] & 64),
    }
    preset_names = {v: k for k, v in PRESETS.items()}
    for index, (side, axis) in enumerate(
        (("right", "head"), ("left", "head"), ("right", "foot"), ("left", "foot"))
    ):
        key = f"foundation_{axis}_{side}"
        flags = payload[9 + index]
        state[key] = payload[1 + index]
        state[f"{key}_moving"] = bool(flags & 1)
        state[f"{key}_limit"] = "missing" if flags & 2 else "unexpected" if flags & 4 else "normal"
        state[f"{key}_current"] = "under" if flags & 8 else "over" if flags & 16 else "normal"
        state[f"{key}_movement"] = (
            "none" if flags & 32 else "unexpected" if flags & 64 else "normal"
        )
    for index, side in enumerate(("right", "left")):
        shift = index * 4
        state[f"foundation_preset_{side}"] = preset_names.get((payload[14] >> shift) & 15, "None")
        state[f"foundation_timer_preset_{side}"] = preset_names.get(
            (payload[13] >> shift) & 15, "None"
        )
        state[f"foundation_timer_{side}"] = int.from_bytes(
            payload[5 + index * 2 : 7 + index * 2], "little"
        )
    return state


def decode_massage(payload: bytes, side: str) -> dict[str, object]:
    require_payload(payload, 11)
    if any(value > 3 for value in payload[1:4]):
        raise ValueError("Unknown MCR massage intensity or mode")
    return {
        f"massage_{name}_{side}": value
        for name, value in zip(
            ("head", "foot", "mode", "head_timer", "foot_timer", "mode_timer"),
            (*payload[1:4], *(int.from_bytes(payload[i : i + 2], "little") for i in (5, 7, 9))),
            strict=True,
        )
    }


def decode_pinch(payload: bytes) -> dict[str, object]:
    require_payload(payload, 5)
    state: dict[str, object] = {}
    for axis, disconnected, continuous, index in (
        ("head_right", 4, 64, 3),
        ("head_left", 8, 128, 4),
        ("foot_right", 1, 16, 1),
        ("foot_left", 2, 32, 2),
    ):
        state[f"pinch_{axis}_disconnected"] = bool(payload[0] & disconnected)
        state[f"pinch_{axis}_continuous"] = bool(payload[0] & continuous)
        state[f"pinch_{axis}_events"] = int.from_bytes(payload[index : index + 1], signed=True)
    return state


def classify_smartpump(data: bytes, address: str) -> dict[str, object]:
    """Decode manufacturer data including its two company bytes."""
    if len(data) < 3:
        return {"model": "unknown"}
    flags = data[2]
    right, left = bool(flags & 2), bool(flags & 16)
    sp1, sp2 = len(data) == 3, len(data) == 8
    marker360 = len(data) == 7 and data[3] == 6
    genie = len(data) == 7 and data[3] == 5
    adult = sp1 or ((sp1 or marker360 or genie) and right and not left)
    is360 = marker360 or (adult and address.upper().startswith("64"))
    model = (
        "360"
        if is360
        else "genie"
        if genie
        else "adult"
        if adult
        else "k1"
        if sp2 and right and not left
        else "k2"
        if sp2 and right and left
        else "unknown"
    )
    return {
        "model": model,
        "right": right,
        "left": left,
        "bind_open": bool(flags & 1),
        "valid": bool(flags & 128),
        "extra": data[3:6] if sp2 and data[6] == 2 and data[-1] == 0 else data[3:8] if sp2 else b"",
    }
