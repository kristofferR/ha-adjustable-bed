"""Typed comfort values shared by the Reverie protocol controllers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReverieComfortRequest:
    """One explicit bed comfort setting; omitted fields remain unspecified."""

    head_position: int | None = None
    foot_position: int | None = None
    lumbar_position: int | None = None
    head_massage: int | None = None
    foot_massage: int | None = None
    timer_byte: int | None = None
    mode: int | None = None
    force: bool = False


def validate_comfort_request(
    request: ReverieComfortRequest,
    *,
    supported_fields: frozenset[str],
    value_ranges: Mapping[str, tuple[int, int]] | None = None,
) -> None:
    """Check request shape without applying another profile's value domains."""
    fields = {
        "head_position": request.head_position,
        "foot_position": request.foot_position,
        "lumbar_position": request.lumbar_position,
        "head_massage": request.head_massage,
        "foot_massage": request.foot_massage,
        "timer_byte": request.timer_byte,
        "mode": request.mode,
    }
    if not any(value is not None for value in fields.values()):
        raise ValueError("At least one Reverie comfort value is required")
    domains = value_ranges or {}
    for name, value in fields.items():
        if value is None:
            continue
        if name not in supported_fields:
            raise ValueError(f"This Reverie profile does not support {name}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if not -(2**31) <= value <= 2**31 - 1:
            raise ValueError(f"{name} must fit the source Java integer input")
        if name in domains:
            minimum, maximum = domains[name]
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
    if not isinstance(request.force, bool):
        raise ValueError("force must be a boolean")


def build_p1_composer_payload(request: ReverieComfortRequest, *, body_tilt: bool) -> bytes | None:
    """Build the accepted V1 Composer payload without value clamping."""
    required = (
        request.head_position,
        request.foot_position,
        request.lumbar_position,
        request.head_massage,
        request.foot_massage,
    )
    if any(value is None for value in required):
        raise ValueError("Protocol 110 comfort requires all five Composer values")

    head, foot, lumbar, head_massage, foot_massage = required
    assert head is not None and foot is not None and lumbar is not None
    assert head_massage is not None and foot_massage is not None
    if lumbar < 0:
        if not body_tilt:
            return None
        mapped_lumbar = int((lumbar + 100) * 36 / 100)
    elif body_tilt:
        mapped_lumbar = int(lumbar * 64 / 100 + 36)
    else:
        mapped_lumbar = lumbar

    fields = (head, foot, mapped_lumbar, head_massage * 4, foot_massage * 4)
    encoded = "00" + "".join(_java_hex(value) for value in fields) + "00000000"
    encoded = encoded[: len(encoded) - len(encoded) % 2]
    return bytes.fromhex(encoded)


def build_stk_composer_payload(
    request: ReverieComfortRequest,
    *,
    side: int,
    current_head: int | None,
    current_head2: int | None,
) -> bytes:
    """Build the STK V1 routine frame, requiring exact preserved-axis state."""
    if side not in (1, 2, 3):
        raise ValueError("STK routine side must be 1, 2, or 3")
    required = (
        request.head_position,
        request.foot_position,
        request.lumbar_position,
        request.head_massage,
        request.foot_massage,
    )
    if any(value is None for value in required):
        raise ValueError("STK Composer routine requires all five values")
    for value in (current_head, current_head2):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255
        ):
            raise ValueError("Preserved STK head feedback must be an unsigned byte")

    head, foot, lumbar, head_massage, foot_massage = required
    assert head is not None and foot is not None and lumbar is not None
    assert head_massage is not None and foot_massage is not None

    if side == 1:
        if current_head2 is None:
            raise ValueError("STK side 1 routine requires current head2 feedback")
        head_side, lumbar_side = head, current_head2
    elif side == 2:
        if current_head is None:
            raise ValueError("STK side 2 routine requires current head feedback")
        head_side, lumbar_side = current_head, lumbar
    else:
        head_side, lumbar_side = head, lumbar

    fields = (
        head_side,
        foot,
        lumbar_side,
        foot_massage * 4,
        head_massage * 4,
        head_massage * 4,
    )
    encoded = "00" + "".join(_java_hex(value) for value in fields) + "00000000"
    encoded = encoded[: len(encoded) - len(encoded) % 2]
    return bytes.fromhex(encoded)


def _java_hex(value: int) -> str:
    """Match Integer.toHexString(int), including its signed 32-bit form."""
    encoded = format(value & 0xFFFFFFFF, "x")
    return encoded if len(encoded) != 1 else f"0{encoded}"
