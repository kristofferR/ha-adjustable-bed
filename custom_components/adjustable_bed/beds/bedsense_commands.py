"""BedSense 1.8 literal commands, accepted row108 report C001-C079.

Trailers are literal, including anomalies. No checksum or service UUID is inferred.
See docs/apk-analysis/dispositions/row108-bedsense.md for sealed provenance.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class BedSenseAction:
    row: str
    label: str
    frame: bytes
    variants: frozenset[int]


ACTIONS: Final[dict[str, BedSenseAction]] = {
    "back_up": BedSenseAction(
        "C001",
        "back up",
        bytes.fromhex("FF FF FF FF 05 00 00 00 03 97 01"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "back_down": BedSenseAction(
        "C002",
        "back down",
        bytes.fromhex("FF FF FF FF 05 00 00 00 04 D6 C3"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "head_up": BedSenseAction(
        "C003",
        "head up",
        bytes.fromhex("FF FF FF FF 05 00 00 00 01 16 C0"),
        frozenset((2, 3, 4, 5)),
    ),
    "head_down": BedSenseAction(
        "C004",
        "head down",
        bytes.fromhex("FF FF FF FF 05 00 00 00 02 56 C1"),
        frozenset((2, 3, 4, 5)),
    ),
    "lift_up": BedSenseAction(
        "C005", "lift up", bytes.fromhex("FF FF FF FF 05 00 00 00 01 16 C0"), frozenset((9,))
    ),
    "lift_down": BedSenseAction(
        "C006", "lift down", bytes.fromhex("FF FF FF FF 05 00 00 00 02 56 C1"), frozenset((9,))
    ),
    "waist_up": BedSenseAction(
        "C007",
        "waist up (TYPE 3 pressed label HIP)",
        bytes.fromhex("FF FF FF FF 05 00 00 00 0D 16 C5"),
        frozenset((1, 2, 3)),
    ),
    "waist_down": BedSenseAction(
        "C008",
        "waist down (TYPE 3 pressed label HIP)",
        bytes.fromhex("FF FF FF FF 05 00 00 00 0E 56 C4"),
        frozenset((1, 2, 3)),
    ),
    "hip_up": BedSenseAction(
        "C009", "hip up", bytes.fromhex("FF FF FF FF 05 00 00 00 0D 16 C5"), frozenset((4, 5, 9))
    ),
    "hip_down": BedSenseAction(
        "C010", "hip down", bytes.fromhex("FF FF FF FF 05 00 00 00 0E 56 C4"), frozenset((4, 5, 9))
    ),
    "legs_up": BedSenseAction(
        "C011",
        "leg up",
        bytes.fromhex("FF FF FF FF 05 00 00 00 06 57 02"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "legs_down": BedSenseAction(
        "C012",
        "leg down",
        bytes.fromhex("FF FF FF FF 05 00 00 00 07 96 C2"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "rise_and_fall_up": BedSenseAction(
        "C013",
        "rise and fall up",
        bytes.fromhex("FF FF FF FF 05 00 00 00 06 57 02"),
        frozenset((8,)),
    ),
    "rise_and_fall_down": BedSenseAction(
        "C014",
        "rise and fall down",
        bytes.fromhex("FF FF FF FF 05 00 00 00 07 96 C2"),
        frozenset((8,)),
    ),
    "back_and_leg_up": BedSenseAction(
        "C015",
        "back and leg up",
        bytes.fromhex("FF FF FF FF 05 00 00 00 2B 97 1F"),
        frozenset((1,)),
    ),
    "back_and_leg_down": BedSenseAction(
        "C016",
        "back and leg down",
        bytes.fromhex("FF FF FF FF 05 00 00 00 2C D6 DD"),
        frozenset((1,)),
    ),
    "release": BedSenseAction(
        "C017",
        "Release / quick-background or light-background tap",
        bytes.fromhex("FF FF FF FF 05 00 00 00 00 D7 00"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "background_tap": BedSenseAction(
        "C018",
        "Movement or massage background tap (physical meaning unverified)",
        bytes.fromhex("FF FF FF FF 05 00 00 00 00 D8 14"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "circulation_whole_body": BedSenseAction(
        "C019",
        "whole body circulation",
        bytes.fromhex("FF FF FF FF 05 00 05 00 E4 C7 4A"),
        frozenset((1, 2, 4, 5)),
    ),
    "circulation_default": BedSenseAction(
        "C020",
        "whole body circulation default",
        bytes.fromhex("FF FF FF FF 05 00 00 00 E7 97 4A"),
        frozenset((3,)),
    ),
    "circulation_back_and_leg": BedSenseAction(
        "C021",
        "back and leg circulation",
        bytes.fromhex("FF FF FF FF 05 00 05 00 E8 C7 4F"),
        frozenset((1,)),
    ),
    "circulation_head": BedSenseAction(
        "C022",
        "head circulation",
        bytes.fromhex("FF FF FF FF 05 00 05 00 E3 86 88"),
        frozenset((2, 3, 4, 5)),
    ),
    "circulation_waist": BedSenseAction(
        "C023",
        "waist circulation",
        bytes.fromhex("FF FF FF FF 05 00 05 00 E6 46 8B"),
        frozenset((1, 2, 3)),
    ),
    "circulation_hip": BedSenseAction(
        "C024",
        "hip circulation",
        bytes.fromhex("FF FF FF FF 05 00 05 00 E6 46 8B"),
        frozenset((4, 5)),
    ),
    "circulation_legs": BedSenseAction(
        "C025",
        "leg circulation",
        bytes.fromhex("FF FF FF FF 05 00 05 00 E5 06 8A"),
        frozenset((1, 2, 3, 4, 5)),
    ),
    "flat": BedSenseAction(
        "C026",
        "Flat Bed / recovery",
        bytes.fromhex("FF FF FF FF 05 00 00 00 08 D6 C6"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "lumbar": BedSenseAction(
        "C027",
        "Lumbar shortcut",
        bytes.fromhex("FF FF FF FF 05 00 00 00 2E 57 1C"),
        frozenset((6, 8)),
    ),
    "music": BedSenseAction(
        "C028",
        "Music shortcut",
        bytes.fromhex("FF FF FF FF 05 00 00 00 28 D7 1E"),
        frozenset((4, 5)),
    ),
    "leg_relax": BedSenseAction(
        "C029",
        "Leg Relax shortcut",
        bytes.fromhex("FF FF FF FF 05 00 00 00 29 16 DE"),
        frozenset((4, 5)),
    ),
    "rise": BedSenseAction(
        "C030", "RISE click", bytes.fromhex("FF FF FF FF 05 00 00 00 01 16 C0"), frozenset((9,))
    ),
    "decline": BedSenseAction(
        "C031", "DECLINE click", bytes.fromhex("FF FF FF FF 05 00 00 00 02 56 C1"), frozenset((9,))
    ),
    "save_m1": BedSenseAction(
        "C032",
        "M1 save",
        bytes.fromhex("FF FF FF FF 05 00 00 A0 0A 2F 07"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "clear_m1": BedSenseAction(
        "C033",
        "M1 clear",
        bytes.fromhex("FF FF FF FF 05 00 00 AF 0A 2A F7"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "recall_m1": BedSenseAction(
        "C034",
        "M1 recall",
        bytes.fromhex("FF FF FF FF 05 00 00 A1 0A 2E 97"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "save_m2": BedSenseAction(
        "C035",
        "M2 save",
        bytes.fromhex("FF FF FF FF 05 00 00 B0 0B E3 07"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "clear_m2": BedSenseAction(
        "C036",
        "M2 clear",
        bytes.fromhex("FF FF FF FF 05 00 00 BF 0B E6 F7"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "recall_m2": BedSenseAction(
        "C037",
        "M2 recall",
        bytes.fromhex("FF FF FF FF 05 00 00 B1 0B E2 97"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "save_tv": BedSenseAction(
        "C038",
        "TV save",
        bytes.fromhex("FF FF FF FF 05 00 00 50 05 2B 03"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "clear_tv": BedSenseAction(
        "C039",
        "TV clear",
        bytes.fromhex("FF FF FF FF 05 00 00 5F 05 2E F3"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "recall_tv": BedSenseAction(
        "C040",
        "TV recall",
        bytes.fromhex("FF FF FF FF 05 00 00 51 05 2A 93"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "builtin_tv": BedSenseAction(
        "C041",
        "TV built-in recall",
        bytes.fromhex("FF FF FF FF 05 00 00 00 05 17 03"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "save_zero_g": BedSenseAction(
        "C042",
        "Zero Gravity save",
        bytes.fromhex("FF FF FF FF 05 00 00 90 09 7B 06"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "clear_zero_g": BedSenseAction(
        "C043",
        "Zero Gravity clear",
        bytes.fromhex("FF FF FF FF 05 00 00 9F 09 7E F6"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "recall_zero_g": BedSenseAction(
        "C044",
        "Zero Gravity recall",
        bytes.fromhex("FF FF FF FF 05 00 00 91 09 7A 96"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "builtin_zero_g": BedSenseAction(
        "C045",
        "Zero Gravity built-in recall",
        bytes.fromhex("FF FF FF FF 05 00 00 00 09 17 06"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "save_anti_snore": BedSenseAction(
        "C046",
        "Anti Snore save",
        bytes.fromhex("FF FF FF FF 05 00 00 F0 0F D3 04"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "clear_anti_snore": BedSenseAction(
        "C047",
        "Anti Snore clear",
        bytes.fromhex("FF FF FF FF 05 00 00 FF 0F D6 F4"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "recall_anti_snore": BedSenseAction(
        "C048",
        "Anti Snore recall",
        bytes.fromhex("FF FF FF FF 05 00 00 F1 0F D2 94"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "builtin_anti_snore": BedSenseAction(
        "C049",
        "Anti Snore built-in recall",
        bytes.fromhex("FF FF FF FF 05 00 00 00 0F 97 04"),
        frozenset((1, 2, 3, 4, 5, 7, 9)),
    ),
    "save_flat": BedSenseAction(
        "C050",
        "Special Flat Bed save (slot 5)",
        bytes.fromhex("FF FF FF FF 05 00 00 F0 0F D3 04"),
        frozenset((6, 8)),
    ),
    "recall_flat": BedSenseAction(
        "C051",
        "Special Flat Bed recall (slot 5)",
        bytes.fromhex("FF FF FF FF 05 00 00 F1 0F D2 94"),
        frozenset((6, 8)),
    ),
    "massage_head_up": BedSenseAction(
        "C052",
        "Head massage increase",
        bytes.fromhex("FF FF FF FF 05 00 00 00 10 D6 CC"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_head_down": BedSenseAction(
        "C053",
        "Head massage decrease",
        bytes.fromhex("FF FF FF FF 05 00 00 00 11 17 0C"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_foot_up": BedSenseAction(
        "C054",
        "Foot massage increase",
        bytes.fromhex("FF FF FF FF 05 00 00 00 12 57 0D"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_foot_down": BedSenseAction(
        "C055",
        "Foot massage decrease",
        bytes.fromhex("FF FF FF FF 05 00 00 00 13 96 CD"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_wave_up": BedSenseAction(
        "C056",
        "Wave/frequency increase",
        bytes.fromhex("FF FF FF FF 05 00 00 00 14 D7 0F"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_wave_down": BedSenseAction(
        "C057",
        "Wave/frequency decrease",
        bytes.fromhex("FF FF FF FF 05 00 00 00 15 16 CF"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_timer_10": BedSenseAction(
        "C058",
        "Massage 10-minute selection",
        bytes.fromhex("FF FF FF FF 05 00 00 00 16 56 CE"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_timer_20": BedSenseAction(
        "C059",
        "Massage 20-minute selection",
        bytes.fromhex("FF FF FF FF 05 00 00 00 17 97 0E"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_timer_30": BedSenseAction(
        "C060",
        "Massage 30-minute selection",
        bytes.fromhex("FF FF FF FF 05 00 00 00 18 D7 0A"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "massage_timer_cancel": BedSenseAction(
        "C061",
        "Cancel selected massage timer",
        bytes.fromhex("FF FF FF FF 05 00 00 00 1C D6 C9"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "light_10_min": BedSenseAction(
        "C062",
        "Light duration 10 min",
        bytes.fromhex("FF FF FF FF 05 00 00 00 19 16 CA"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "light_8_h": BedSenseAction(
        "C063",
        "Light duration 8 h",
        bytes.fromhex("FF FF FF FF 05 00 00 00 1A 56 CB"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "light_10_h": BedSenseAction(
        "C064",
        "Light duration 10 h",
        bytes.fromhex("FF FF FF FF 05 00 00 00 1B 97 0B"),
        frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9)),
    ),
    "query_default_3": BedSenseAction(
        "C065",
        "Qdefault query 1 TV/M3",
        bytes.fromhex("FF FF FF FF 03 00 16 00 09 7E C2"),
        frozenset((1, 2, 3, 4, 5, 9)),
    ),
    "query_default_4": BedSenseAction(
        "C066",
        "Qdefault query 2 Zero Gravity/M4",
        bytes.fromhex("FF FF FF FF 03 00 1F 00 09 AE C0"),
        frozenset((1, 2, 3, 4, 5, 9)),
    ),
    "query_default_1": BedSenseAction(
        "C067",
        "Qdefault query 3 M1",
        bytes.fromhex("FF FF FF FF 03 00 28 00 09 1F 0E"),
        frozenset((1, 2, 3, 4, 5, 9)),
    ),
    "query_default_2": BedSenseAction(
        "C068",
        "Qdefault query 4 M2",
        bytes.fromhex("FF FF FF FF 03 00 31 00 09 CE C9"),
        frozenset((1, 2, 3, 4, 5, 9)),
    ),
    "query_default_5": BedSenseAction(
        "C069",
        "Qdefault query 5 Anti Snore/M5",
        bytes.fromhex("FF FF FF FF 03 00 3A 00 09 BF 0B"),
        frozenset((1, 2, 3, 4, 5, 9)),
    ),
    "query_68_3": BedSenseAction(
        "C070",
        "Q68 query 1 TV/M3",
        bytes.fromhex("FF FF FF FF 03 00 14 00 03 5F 05"),
        frozenset((6, 8)),
    ),
    "query_68_4": BedSenseAction(
        "C071",
        "Q68 query 2 Zero Gravity/M4",
        bytes.fromhex("FF FF FF FF 03 00 1C 00 03 DE C7"),
        frozenset((6, 8)),
    ),
    "query_68_1": BedSenseAction(
        "C072",
        "Q68 query 3 M1",
        bytes.fromhex("FF FF FF FF 03 00 24 00 03 5F 0A"),
        frozenset((6, 8)),
    ),
    "query_68_2": BedSenseAction(
        "C073",
        "Q68 query 4 M2",
        bytes.fromhex("FF FF FF FF 03 00 2C 00 03 DE C8"),
        frozenset((6, 8)),
    ),
    "query_68_5": BedSenseAction(
        "C074",
        "Q68 query 5 Anti Snore/M5",
        bytes.fromhex("FF FF FF FF 03 00 3A 00 09 BF 0B"),
        frozenset((6, 8)),
    ),
    "query_7_3": BedSenseAction(
        "C075",
        "Q7 query 1 TV/M3",
        bytes.fromhex("FF FF FF FF 03 00 18 00 03 9F 06"),
        frozenset((7,)),
    ),
    "query_7_4": BedSenseAction(
        "C076",
        "Q7 query 2 Zero Gravity/M4",
        bytes.fromhex("FF FF FF FF 03 00 20 00 03 1E CB"),
        frozenset((7,)),
    ),
    "query_7_1": BedSenseAction(
        "C077", "Q7 query 3 M1", bytes.fromhex("FF FF FF FF 03 00 28 00 03 9F 09"), frozenset((7,))
    ),
    "query_7_2": BedSenseAction(
        "C078", "Q7 query 4 M2", bytes.fromhex("FF FF FF FF 03 00 30 00 03 1F 0E"), frozenset((7,))
    ),
    "query_7_5": BedSenseAction(
        "C079",
        "Q7 query 5 Anti Snore/M5",
        bytes.fromhex("FF FF FF FF 03 00 38 00 03 9E CC"),
        frozenset((7,)),
    ),
}
