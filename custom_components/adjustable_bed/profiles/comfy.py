"""KomfyD 1.0.9 and ComfyDS 1.0.0, accepted row084 / cluster-016.

Hand-kept from each accepted report and the accepted reconciliation command
rows C01–C32. Every literal is independently checked in test_comfy_vectors.
Column order is first/left, second/right, both. No physical axis, H/F intensity
or timer coupling is inferred from the app's labels.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import ClassVar, Final

from ..beds.kaidi.protocol import KaidiAdvertisement, parse_kaidi_manufacturer_payload
from ..const import (
    BED_TYPE_COMFYDS,
    CONF_BED_TYPE,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_PRODUCT_TYPE,
)
from ..execution import ExecutionCapabilities
from .kaidi import IsleepProfile

# fmt: off
KOMFYD_COMMANDS: Final[Mapping[str, tuple[int, int, int]]] = {
    "head_up": (1, 10, 19), "head_down": (2, 11, 20), "head_stop": (3, 12, 21),
    "legs_up": (4, 13, 22), "legs_down": (5, 14, 23), "legs_stop": (6, 15, 24),
    "lumbar_up": (7, 16, 25), "lumbar_down": (8, 17, 26), "lumbar_stop": (9, 18, 27),
    "preset_stop": (28, 29, 30), "zero": (31, 32, 33), "flat": (34, 35, 36),
    "save_1": (37, 37, 37), "save_2": (38, 38, 38),
    "save_3": (39, 39, 39), "save_4": (40, 40, 40),
    "memory_1": (41, 41, 41), "memory_2": (42, 42, 42),
    "memory_3": (43, 43, 43), "memory_4": (44, 44, 44),
    "lock": (61, 62, 63), "unlock": (64, 65, 66), "query": (70, 70, 70),
    "h_increase": (71, 74, 83), "h_decrease": (72, 75, 84),
    "f_increase": (77, 80, 86), "f_decrease": (78, 81, 87),
    "timer_10": (89, 96, 103), "timer_20": (90, 97, 104),
    "timer_30": (91, 98, 105), "timer_40": (92, 99, 106), "timer_50": (93, 100, 107),
    "timer_start": (94, 101, 108), "timer_stop": (95, 102, 109),
    "light_on": (110, 112, 114), "light_off": (111, 113, 115),
}
# Independent ComfyDS table, not a sibling-app alias. The full literal census
# proves these values, including memory bank1 on every posBed selection.
COMFYDS_COMMANDS: Final[Mapping[str, tuple[int, int, int]]] = {
    "head_up": (1, 10, 19), "head_down": (2, 11, 20), "head_stop": (3, 12, 21),
    "legs_up": (4, 13, 22), "legs_down": (5, 14, 23), "legs_stop": (6, 15, 24),
    "lumbar_up": (7, 16, 25), "lumbar_down": (8, 17, 26), "lumbar_stop": (9, 18, 27),
    "preset_stop": (28, 29, 30), "zero": (31, 32, 33), "flat": (34, 35, 36),
    "save_1": (37, 37, 37), "save_2": (38, 38, 38),
    "save_3": (39, 39, 39), "save_4": (40, 40, 40),
    "memory_1": (41, 41, 41), "memory_2": (42, 42, 42),
    "memory_3": (43, 43, 43), "memory_4": (44, 44, 44),
    "lock": (61, 62, 63), "unlock": (64, 65, 66), "query": (70, 70, 70),
    "h_increase": (71, 74, 83), "h_decrease": (72, 75, 84),
    "f_increase": (77, 80, 86), "f_decrease": (78, 81, 87),
    "timer_10": (89, 96, 103), "timer_20": (90, 97, 104),
    "timer_30": (91, 98, 105), "timer_40": (92, 99, 106), "timer_50": (93, 100, 107),
    "timer_start": (94, 101, 108), "timer_stop": (95, 102, 109),
    "light_on": (110, 112, 114), "light_off": (111, 113, 115),
}
# fmt: on
COMFY_PRODUCTS: Final = {
    129: "129 (first bank)",
    131: "131 (alias of 129)",
    130: "130 (left/both/right)",
}
COMFY_ACTIONS: Final = (
    "zero",
    "h_increase",
    "h_decrease",
    "f_increase",
    "f_decrease",
    "timer_start",
    "timer_stop",
    "lock",
    "unlock",
    "query",
)


def signed32(value: int) -> int:
    """Decode the Java int domain without treating -2 as unsigned 4294967294."""
    return (value + 2**31) % 2**32 - 2**31


def wire_target(target: int) -> int:
    """Only the helper's -2 sentinel is serialized as zero (B02/B05)."""
    if not -(2**31) <= target < 2**31 or target == 0:
        raise ValueError("A nonzero signed Kaidi destination is required")
    return 0 if target == -2 else target


@dataclass(frozen=True)
class ComfyProfile(IsleepProfile):
    """Shared proven selector domain, with a separate command table per app."""

    key: ClassVar[str] = "komfyd"
    commands: ClassVar[Mapping[str, tuple[int, int, int]]] = KOMFYD_COMMANDS
    execution: ClassVar[ExecutionCapabilities] = ExecutionCapabilities(hold="latched")
    retain_source_on_reconnect: ClassVar[bool] = False
    write_spacing_s: ClassVar[float] = 0.05
    first_write_s: ClassVar[float] = 0.01
    memory_repeat_s: ClassVar[float] = 1
    join_timeout_s: ClassVar[float] = 8
    raw_type: int = 129

    @property
    def split(self) -> bool:
        return self.product == 130

    @property
    def axes(self) -> tuple[str, ...]:
        # Three rendered app controls, independent of all capability nibbles.
        return ("back", "legs", "lumbar")

    @property
    def can_store(self) -> bool:
        return bool(self.actuators & 0xF000)


@dataclass(frozen=True)
class ComfyDSProfile(ComfyProfile):
    key: ClassVar[str] = "comfyds"
    commands: ClassVar[Mapping[str, tuple[int, int, int]]] = COMFYDS_COMMANDS
    retain_source_on_reconnect: ClassVar[bool] = True


def validate_comfy_profile(data: Mapping[str, object]) -> ComfyProfile:
    raw = data.get(CONF_PRODUCT_TYPE)
    room = data.get(CONF_KAIDI_ROOM_ID)
    acu = data.get(CONF_KAIDI_SOFA_ACU_NO, 0)
    if type(raw) is not int or raw not in COMFY_PRODUCTS:
        raise ValueError("Select raw bed type 129, 130 or 131")
    if type(room) is not int or not -(2**31) <= room < 2**31:
        raise ValueError("Enter the existing signed 32-bit room ID")
    if type(acu) is not int or not 0 <= acu <= 0xFFFF:
        raise ValueError("Invalid capability word")
    cls = ComfyDSProfile if data.get(CONF_BED_TYPE) == BED_TYPE_COMFYDS else ComfyProfile
    return cls(129 if raw == 131 else raw, room, acu, raw)


def comfy_advertisement(manufacturer_data: Mapping[int, bytes]) -> KaidiAdvertisement | None:
    """S01–S05: safe bounds, signed state and the complete bed-only raw domain.

    HA owns scan cycles/RSSI/connectability. A valid shared advertisement cannot
    identify either app, so this seeds explicit setup and never selects an app.
    """
    payload = manufacturer_data.get(0xFFFF)
    ad = parse_kaidi_manufacturer_payload(payload) if payload is not None else None
    if ad is None or ad.adv_type not in (1, 2, 9) or ad.sofa_type not in COMFY_PRODUCTS:
        return None
    if ad.adv_type == 9 and ad.company_id != 0x4B44:
        return None
    acu = ad.sofa_acu_no
    if acu is None or (acu >> 8 & 7) > 5 or (acu & 15) > 5 or (acu >> 4 & 15) > 5:
        return None
    return replace(
        ad,
        product_id=129 if ad.sofa_type == 131 else ad.sofa_type,
        room_id=signed32(ad.room_id) if ad.room_id is not None else None,
        vaddr=signed32(ad.vaddr) if ad.vaddr is not None else None,
    )


def add_comfy_metadata(
    data: Mapping[str, object], manufacturer_data: Mapping[int, bytes]
) -> dict[str, object]:
    result = dict(data)
    if (ad := comfy_advertisement(manufacturer_data)) is not None:
        result.setdefault(CONF_PRODUCT_TYPE, ad.sofa_type)
        result.setdefault(CONF_KAIDI_SOFA_ACU_NO, ad.sofa_acu_no)
        if ad.room_id is not None:
            result.setdefault(CONF_KAIDI_ROOM_ID, ad.room_id)
    return result
