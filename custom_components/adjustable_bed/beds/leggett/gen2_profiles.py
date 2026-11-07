"""Per-model capability profiles for Leggett & Platt Gen2 (LP Comfort Connect) beds.

Gen2 beds do NOT report their capabilities over BLE at runtime. Instead the LP
Control app (``com.leggett.android.universal``) ships a bundled JSON profile per
product (``assets/ID_<productId>.json``) and selects it by a ``productId`` that
it derives from the BLE advertisement's manufacturer-specific data. The profile
declares which under-bed light (none / toggle / single-colour / RGB), actuators
(pillow, lumbar, head, foot), massage, and memory slots the model has.

This module ports that mechanism:

* :func:`compute_product_id` reproduces the app's ``productId(ScanResult)``
  algorithm (``Gen2BedControlBoxInterface.java:572-598``) from the manufacturer
  data we already detect on.
* :data:`GEN2_PROFILES` is the distilled capability table extracted from the 33
  bundled ``ID_*.json`` profiles (furnitureType AB = bed, CHR = chair).
* :func:`capabilities_for_product` looks up a product, falling back to a generous
  default (the app's default ``ID_7`` set) for unknown ids so unrecognised beds
  keep a full entity set rather than losing controls.

Source: reverse engineering of LP Control v2.9.0; see docs/beds/leggett-platt.md.
Values are unverified on hardware (tracked under issue #385).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from ..const import MANUFACTURER_ID_LEGGETT_GEN2

# Under-bed light style declared by the profile's ``lightConfig.colorPallet`` +
# ``ublEnabled``: no light, a plain on/off toggle, a single (non-RGB) colour, or
# full RGB colour control.
LightStyle = Literal["none", "toggle", "single", "rgb"]

# Manufacturer payload prefixes that mark an LP Comfort Connect advertisement.
_GEN2_PREFIXES: Final = (b"XP", b"CP")


@dataclass(frozen=True, slots=True)
class Gen2Capabilities:
    """Distilled capability set for one Gen2 product."""

    light: LightStyle
    light_brightness: bool
    has_pillow: bool
    has_lumbar: bool
    has_head: bool
    has_foot: bool
    has_massage: bool
    has_massage_wave: bool
    memory_slots: int
    is_chair: bool = False


def _c(  # noqa: PLR0913 - mirrors the profile JSON fields one-to-one
    light: LightStyle,
    brightness: bool,
    pillow: bool,
    lumbar: bool,
    head: bool,
    foot: bool,
    massage: bool,
    wave: bool,
    memory: int,
    chair: bool,
) -> Gen2Capabilities:
    return Gen2Capabilities(
        light=light,
        light_brightness=brightness,
        has_pillow=pillow,
        has_lumbar=lumbar,
        has_head=head,
        has_foot=foot,
        has_massage=massage,
        has_massage_wave=wave,
        memory_slots=memory,
        is_chair=chair,
    )


# productId -> capabilities, distilled from assets/ID_<productId>.json.
# Columns: light, brightness, pillow, lumbar, head, foot, massage, wave, memory, chair
GEN2_PROFILES: Final[dict[int, Gen2Capabilities]] = {
    5: _c("rgb", True, True, True, True, True, True, True, 3, False),
    7: _c("rgb", True, True, True, True, True, True, True, 3, False),
    8: _c("toggle", True, False, False, True, True, True, True, 3, False),
    9: _c("toggle", True, True, False, True, True, True, True, 3, False),
    10: _c("rgb", True, False, False, True, True, True, True, 3, False),
    11: _c("rgb", True, True, False, True, True, True, True, 3, False),
    12: _c("rgb", True, False, False, True, True, True, True, 3, False),
    13: _c("rgb", True, True, False, True, True, True, True, 3, False),
    14: _c("rgb", True, False, False, True, True, True, True, 3, False),
    15: _c("rgb", True, False, False, True, True, True, True, 3, False),
    16: _c("rgb", True, True, False, True, True, True, True, 3, False),
    10000: _c("rgb", True, False, False, True, True, True, True, 3, False),
    10002: _c("rgb", True, True, False, True, True, True, True, 3, False),
    10010: _c("rgb", True, True, True, True, True, True, True, 3, False),
    10011: _c("none", False, False, False, True, False, False, False, 3, False),
    10012: _c("single", False, False, False, True, True, True, False, 3, False),
    10013: _c("none", False, True, False, True, True, False, False, 3, False),
    10014: _c("rgb", True, False, False, False, False, True, True, 3, False),
    10015: _c("single", True, True, True, False, False, True, False, 3, False),
    10016: _c("single", True, False, True, False, False, True, False, 3, False),
    10017: _c("none", False, False, True, True, True, True, True, 3, False),
    10018: _c("none", False, True, True, True, True, False, False, 3, False),
    10019: _c("single", True, False, False, True, False, False, False, 3, False),
    10022: _c("rgb", True, True, True, True, True, True, True, 3, False),
    10027: _c("rgb", True, False, False, True, True, True, True, 3, False),
    10029: _c("rgb", True, False, False, True, True, True, True, 3, False),
    10030: _c("none", False, False, True, True, True, False, False, 0, True),
    10031: _c("none", False, False, True, True, True, False, False, 0, True),
    10032: _c("none", False, False, False, True, True, False, False, 0, True),
    10034: _c("toggle", True, False, False, True, True, True, True, 3, False),
    10036: _c("rgb", True, True, True, True, True, True, True, 3, False),
    10038: _c("none", False, False, False, True, True, False, False, 0, True),
    10039: _c("none", False, False, False, True, True, False, False, 0, True),
}

# Fallback for unknown product ids: the app's default GEN2_BED profile (ID_7) —
# a fully-featured bed. Keeping unknown beds fully-featured avoids hiding controls
# a bed may actually have; known ids get accurate gating.
GEN2_FALLBACK: Final[Gen2Capabilities] = GEN2_PROFILES[7]


def compute_product_id(manufacturer_data: Mapping[int, bytes] | None) -> int | None:
    """Derive the Gen2 productId from advertisement manufacturer data.

    Reproduces ``Gen2BedControlBoxInterface.productId(ScanResult)``: take the
    manufacturer payload that begins with ASCII ``XP``/``CP``, hex-encode each
    byte, reverse the list of hex bytes, join the first four, and parse as a
    base-16 integer. e.g. ``58 50 05 00 00 00`` -> ``["00","00","00","05",…]`` ->
    ``0x00000005`` -> ``5``.
    """
    if not manufacturer_data:
        return None
    payload = manufacturer_data.get(MANUFACTURER_ID_LEGGETT_GEN2)
    if payload is None or len(payload) < 6 or payload[:2] not in _GEN2_PREFIXES:
        return None
    # Reverse the hex of the four bytes after the prefix and parse base-16 — this
    # is exactly the four payload bytes [2:6] read little-endian.
    return int.from_bytes(payload[2:6], "little")


def capabilities_for_product(product_id: int | None) -> Gen2Capabilities:
    """Return the capability profile for a product id (generous fallback)."""
    if product_id is None:
        return GEN2_FALLBACK
    return GEN2_PROFILES.get(product_id, GEN2_FALLBACK)
