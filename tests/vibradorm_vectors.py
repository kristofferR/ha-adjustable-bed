"""Frozen Vibradorm VMAT frames, by profile key and characteristic role.

Each set holds every fixed frame a profile sends: commands whose bytes depend only
on the profile, its layout and the alternating toggle. Every literal is one the
pre-v5 controllers sent, in ``tests/fixtures/wire_snapshot.json`` or a
differential capture of every layout in both toggle phases. The V-MAT Basic sets
are also its artifact vectors (``tests/fixtures/vmatbasic-vectors.json``
T001-T007 and T081-T093). Light levels, timers, mood speeds, colors and massage
settings are values; ``VALUE_FRAMES`` holds the frames the artifact fixtures and
the wire snapshot froze for them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

MOTOR: Final = "motor"
"""``1526``: one command byte."""
LIGHT: Final = "light"
"""``1529``: level and 16-bit timer minutes."""
CBI: Final = "cbi"
"""``1550``: 16-bit command word and parameters."""

_FIXTURES = Path(__file__).parent / "fixtures"


def _frames(text: str) -> frozenset[str]:
    return frozenset(text.split())


FROZEN: Final[dict[str, dict[str, frozenset[str]]]] = {
    "legacy": {
        MOTOR: _frames("00 02 03 04 05 08 09 0a 0b 0c 0e 0f 1a 1b 1c ff"),
        LIGHT: _frames("000000 ff0000"),
        CBI: _frames(
            "000c 000d 000e 000f 001a 001b 001c 003400 003401 003d3f 800c 800d 800e 800f 801a "
            "801b 801c 803400 803401 803d3f"
        ),
    },
    "caresse": {
        MOTOR: _frames("00 02 03 08 09 0a 0b 0c 0e 0f 10 ff"),
        CBI: _frames(
            "0000 0002 0003 0004 0005 0008 0009 000a 000b 000c 000d 000e 000f 0010 001a 001b 001c "
            "003400 007701000050ef 00770100008a00 0077010000aba9 007701001aa1e2 00770100647687 "
            "007701006a00ff 007701006d8764 0077010076708a 00770100825a2c 00770100a20024 "
            "00770100aa00ff 00770100d80073 00770100e3c800 00770100e51300 00770100f0a309 "
            "00770100f472d0 00770100fa6800 00770100ffffff 00770801 00770802 00770803 00ff 01a0c8 "
            "103400 1077 107701000050ef 10770100008a00 1077010000aba9 107701001aa1e2 "
            "10770100647687 107701006a00ff 107701006d8764 1077010076708a 10770100825a2c "
            "10770100a20024 10770100aa00ff 10770100d80073 10770100e3c800 10770100e51300 "
            "10770100f0a309 10770100f472d0 10770100fa6800 10770100ffffff 10770801 10770802 "
            "10770803 8000 8002 8003 8004 8005 8008 8009 800a 800b 800c 800d 800e 800f 8010 801a "
            "801b 801c 803400 807701000050ef 80770100008a00 8077010000aba9 807701001aa1e2 "
            "80770100647687 807701006a00ff 807701006d8764 8077010076708a 80770100825a2c "
            "80770100a20024 80770100aa00ff 80770100d80073 80770100e3c800 80770100e51300 "
            "80770100f0a309 80770100f472d0 80770100fa6800 80770100ffffff 80770801 80770802 "
            "80770803 903400 9077 907701000050ef 90770100008a00 9077010000aba9 907701001aa1e2 "
            "90770100647687 907701006a00ff 907701006d8764 9077010076708a 90770100825a2c "
            "90770100a20024 90770100aa00ff 90770100d80073 90770100e3c800 90770100e51300 "
            "90770100f0a309 90770100f472d0 90770100fa6800 90770100ffffff 90770801 90770802 "
            "90770803"
        ),
    },
    "werkmeister": {
        CBI: _frames(
            "0000 0002 0003 0004 0005 0008 0009 000a 000b 000c 000d 000e 000f 0010 0018 0019 001a "
            "001b 001c 003d3f 00ff 01a0c8 8000 8002 8003 8004 8005 8008 8009 800a 800b 800c 800d "
            "800e 800f 8010 8018 8019 801a 801b 801c 803d3f"
        ),
    },
    "vmat": {
        MOTOR: _frames("00 08 09 0a 0b 10 ff"),
        CBI: _frames(
            "0000 0002 0003 0004 0005 0008 0009 000a 000b 000c 000d 000e 000f 0010 0018 0019 001a "
            "001b 001c 003400 003d3f 007701000050ee 00770100008a00 0077010000aaa8 007701001aa1e2 "
            "00770100647687 007701006a00ff 007701006d8764 0077010076708a 00770100825a2c "
            "00770100a20024 00770100aa00ff 00770100d80073 00770100e3c800 00770100e51300 "
            "00770100efa209 00770100f472d0 00770100fa6800 00770100ffffff 00770801 00770802 "
            "00770803 00ff 01a0c8 01a0c9 01a0ca 01a0ca00 01a0cc 01a7 01b34c01 01b3f401 103400 "
            "1077 107701000050ee 10770100008a00 1077010000aaa8 107701001aa1e2 10770100647687 "
            "107701006a00ff 107701006d8764 1077010076708a 10770100825a2c 10770100a20024 "
            "10770100aa00ff 10770100d80073 10770100e3c800 10770100e51300 10770100efa209 "
            "10770100f472d0 10770100fa6800 10770100ffffff 10770801 10770802 10770803 8000 8002 "
            "8003 8004 8005 8008 8009 800a 800b 800c 800d 800e 800f 8010 8018 8019 801a 801b 801c "
            "803400 803d3f 807701000050ee 80770100008a00 8077010000aaa8 807701001aa1e2 "
            "80770100647687 807701006a00ff 807701006d8764 8077010076708a 80770100825a2c "
            "80770100a20024 80770100aa00ff 80770100d80073 80770100e3c800 80770100e51300 "
            "80770100efa209 80770100f472d0 80770100fa6800 80770100ffffff 80770801 80770802 "
            "80770803 903400 9077 907701000050ee 90770100008a00 9077010000aaa8 907701001aa1e2 "
            "90770100647687 907701006a00ff 907701006d8764 9077010076708a 90770100825a2c "
            "90770100a20024 90770100aa00ff 90770100d80073 90770100e3c800 90770100e51300 "
            "90770100efa209 90770100f472d0 90770100fa6800 90770100ffffff 90770801 90770802 "
            "90770803"
        ),
    },
    "basic": {
        MOTOR: _frames("00 08 09 0a 0b 10 ff"),
    },
    "cbi": {
        MOTOR: _frames("00 08 09 0a 0b 10 ff"),
        LIGHT: _frames("000000"),
    },
    "xtbox": {
        MOTOR: _frames("00 08 09 0a 0b 10 ff"),
        CBI: _frames(
            "0011 0028 0029 002c 002d 0031 0034 0077 00770100000000 00770801 00770802 00770803"
        ),
    },
}


def _value_frames() -> dict[str, frozenset[str]]:
    vmat = json.loads((_FIXTURES / "vibradorm_vmat_vectors.json").read_text())
    vmatbasic = json.loads((_FIXTURES / "vmatbasic-vectors.json").read_text())["packets"]
    roles = {"motor": MOTOR, "floor": LIGHT, "literal": None, "rename": None}
    by_role: dict[str, set[str]] = {MOTOR: set(), LIGHT: set(), CBI: set()}
    for vector in vmat["vectors"]:
        by_role[CBI].add(vector["expected_bytes"].replace(" ", "").lower())
    for vector in vmatbasic:
        role = roles.get(vector["builder"], CBI)
        if role is not None:
            by_role[role].add(vector["expected"])
    # Caresse floor levels, mood speeds and massage settings in the wire snapshot.
    by_role[CBI] |= {
        *(f"9011{level:02x}00" for level in range(1, 7)),
        "10110600",
        "10770912",
        "90770902",
        "10300101030300000000",
        "10300001000000000000",
        "90300005000000000000",
    }
    return {role: frozenset(frames) for role, frames in by_role.items()}


VALUE_FRAMES: Final = _value_frames()
"""Value-carrying frames, by role, from the artifact fixtures and the wire snapshot."""
