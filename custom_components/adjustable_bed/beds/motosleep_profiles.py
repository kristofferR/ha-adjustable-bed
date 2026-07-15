"""Model routing recovered from the MotoSleep and Power Bob Android apps.

The two HHC apps share UUIDs but do not share one universal controller.  The
advertised local name selects both the wire protocol and the controls rendered
by the OEM app.  Keep that routing here instead of inferring capabilities from
another HHC model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType

Command = str | int
MotorPair = tuple[Command, Command]
StopAction = Command | tuple[int, int]


class MotoSleepTransport(StrEnum):
    """Command transports used by the two OEM applications."""

    POWER_BOB_ASCII = "power_bob_ascii"
    HHC_ASCII = "hhc_ascii"
    MOTO_BINARY = "moto_binary"


@dataclass(frozen=True, slots=True)
class MotoSleepProfile:
    """Resolved app controller profile for one advertised-name branch."""

    profile_id: str
    transport: MotoSleepTransport
    motors: Mapping[str, MotorPair]
    presets: Mapping[str, Command]
    memory_recall: tuple[Command, ...] = ()
    memory_save: tuple[Command, ...] = ()
    light_toggle: Command | None = None
    rgb_light: bool = False
    massage: Mapping[str, Command] = MappingProxyType({})
    stop: tuple[StopAction, int, int] | None = None
    write_with_response: bool = True
    raw_hhc: bool = False
    swing: Command | None = None
    synchro: tuple[str, str] | None = None
    auxiliary_action: Command | None = None


def _frozen(mapping: Mapping[str, Command | MotorPair] | None = None) -> Mapping:
    return MappingProxyType(dict(mapping or {}))


def _profile(
    profile_id: str,
    transport: MotoSleepTransport,
    *,
    motors: Mapping[str, MotorPair],
    commands: str = "",
    explicit_stop: bool = True,
    rgb_light: bool = False,
    raw_hhc: bool = False,
) -> MotoSleepProfile:
    """Build an ASCII profile from its APK-reachable literal inventory."""
    available = set(commands)
    presets = {
        key: command
        for key, command in {
            "flat": "O",
            "anti_snore": "R",
            "tv": "S",
            "zero_g": "T",
        }.items()
        if command in available
    }
    recall = tuple(command for command in ("U", "V") if command in available)
    save = tuple(command for command in ("Z", "a") if command in available)
    massage = {
        key: command
        for key, command in {
            "head_toggle": "C",
            "foot_toggle": "B",
            "off": "D",
            "head_up": "G",
            "head_down": "H",
            "foot_up": "E",
            "foot_down": "F",
            "head_off": "J",
            "foot_off": "I",
        }.items()
        if command in available
    }
    return MotoSleepProfile(
        profile_id=profile_id,
        transport=transport,
        motors=_frozen(motors),
        presets=_frozen(presets),
        memory_recall=recall,
        memory_save=save,
        light_toggle="A" if "A" in available else None,
        rgb_light=rgb_light,
        massage=_frozen(massage),
        stop=("b", 5, 30) if explicit_stop else None,
        write_with_response=transport is not MotoSleepTransport.POWER_BOB_ASCII,
        raw_hhc=raw_hhc,
        auxiliary_action="W" if "W" in available else None,
    )


# Power Bob 2.0.3 accepts only 14-character HHC names.  Auxiliary axes whose
# physical label is not statically unique intentionally keep neutral entity
# names.  This preserves the app-proven callsites without claiming hardware
# semantics that only real users can validate.
_POWER_BOB_COMMANDS = {
    "a15": "aAKLMNOPQRSTUVZ",
    "d345": "aABCDKLMNOPQUVZ",
    "four": "aABCDKLMNOpPqQRSTUVZ",
    "wr1140": "aABCDKLMNOpPqQRSTUVZ",
    "zero": "aAEFGHIJKLMNOPQpqUVZ",
    "one": "KLO",
    "two": "aABCDKLMNOpPqQUVZ",
    "three": "aAKLMNORSTUVZ",
    "five": "KL",
    "six": "KLMN",
    "seven": "aABCDKLMNOUVZ",
    "eight": "aAKLMNRSTUVZ",
    "nine": "KLMNO",
    "six_zg": "KLMN",
}


def _power_bob_profile(profile_id: str) -> MotoSleepProfile:
    motors: dict[str, MotorPair] = {"back": ("K", "L")}
    if profile_id not in {"one", "five"}:
        motors["legs"] = ("M", "N")
    if profile_id == "a15":
        # PanelA labels P/Q LUMBAR.  This is the issue #445 device branch.
        motors["lumbar"] = ("P", "Q")
    elif profile_id == "zero":
        motors.update({"lumbar": ("p", "q"), "tilt": ("P", "Q")})
    elif profile_id == "wr1140":
        motors.update({"lumbar": ("p", "q"), "auxiliary": ("P", "Q")})
    elif profile_id in {"four", "two"}:
        motors.update({"auxiliary_1": ("p", "q"), "auxiliary_2": ("P", "Q")})
    elif profile_id == "d345":
        motors["auxiliary"] = ("P", "Q")

    explicit_stop = profile_id in {"four", "wr1140", "one", "two", "three", "nine", "six_zg"}
    return _profile(
        f"power_bob_{profile_id}",
        MotoSleepTransport.POWER_BOB_ASCII,
        motors=motors,
        commands=_POWER_BOB_COMMANDS[profile_id],
        explicit_stop=explicit_stop,
        rgb_light=True,
    )


def _resolve_power_bob(name: str) -> MotoSleepProfile:
    c8, c9 = name[8], name[9]
    profile_id: str | None
    if (c8, c9) == ("1", "5") or c8 == "A":
        profile_id = "a15"
    elif (c8 in "348" and c9 == "5") or c8 == "C":
        profile_id = "d345"
    elif c8 == "4" or (c8 in "25" and c9 == "5") or c8 == "B":
        profile_id = "four"
    elif c8 == "9" and c9 in "5678":
        profile_id = "wr1140"
    else:
        profile_id = {
            "0": "zero",
            "1": "one",
            "2": "two",
            "3": "three",
            "5": "five",
            "6": "six",
            "7": "seven",
            "8": "eight",
            "9": "nine",
            "D": "six_zg",
        }.get(c8)
    if profile_id is None:
        return MotoSleepProfile(
            profile_id="power_bob_unknown",
            transport=MotoSleepTransport.POWER_BOB_ASCII,
            motors=_frozen(),
            presets=_frozen(),
            write_with_response=False,
        )
    return _power_bob_profile(profile_id)


_HHC_COMMANDS = {
    "f": "aABCDKLMNORSTUVZ",
    "g": "aABCDKLMNOpqRSTUVZ",
    "h": "aABCDKLMNOpqRSTUVZ",
    "a": "aAKLMNOPQRSTUVZ",
    "one": "KLO",
    "d": "aABCDKLMNOPQRSTUVZ",
    "four": "aABCDKLMNOpPqQRSTUVZ",
    "wr1140": "aABCDKLMNOpPqQRSTUVZ",
    "zero": "aAEFGHIJKLMNOPQpqUVZ",
    "two": "aABCDKLMNOpPqQUVZ",
    "three": "aAKLORSTUVZ",
    "five_new": "KLO",
    "five": "KLO",
    "six_new": "KLMNOT",
    "six": "KLMNO",
    "seven": "aABCDKLMNOUVZ",
    "eight_new": "aAKLMNORSTUVZ",
    "eight": "aAKLMNORSTUVZ",
    "nine": "KLMNO",
    "six_zg": "KLMNT",
    "e": "AKLOWR",
}


def _resolve_hhc(name: str) -> MotoSleepProfile:
    c16 = name[16] if len(name) > 16 else ""
    c18 = name[18] if len(name) > 18 else ""
    is_new = len(name) > 26 and name[26] == "I"

    if c16 in "FGH":
        profile_id = c16.lower()
    elif (c16, c18) == ("1", "5") or c16 == "A":
        profile_id = "a"
    elif (c16 == "1" and c18 != "5") or (c16, c18) == ("4", "6"):
        profile_id = "one"
    elif (c16, c18) in {("3", "5"), ("3", "6"), ("4", "5"), ("8", "5")} or c16 == "C":
        profile_id = "d"
    elif c16 == "4" or (c16, c18) in {("2", "5"), ("5", "5")} or c16 == "B":
        profile_id = "four"
    elif c16 == "9" and c18 in "5678":
        profile_id = "wr1140"
    elif c16 == "0":
        profile_id = "zero"
    elif c16 == "2":
        profile_id = "two"
    elif c16 == "3" or (c16, c18) in {("6", "5"), ("7", "5")}:
        profile_id = "three"
    elif c16 == "5":
        profile_id = "five_new" if is_new else "five"
    elif c16 == "6":
        profile_id = "six_new" if is_new else "six"
    elif c16 == "7":
        profile_id = "seven"
    elif c16 == "8":
        profile_id = "eight_new" if is_new else "eight"
    elif c16 == "9":
        profile_id = "nine"
    elif c16 == "D":
        profile_id = "six_zg"
    elif c16 == "E":
        profile_id = "e"
    else:
        profile_id = "one"

    motors: dict[str, MotorPair] = {"back": ("K", "L")}
    available = set(_HHC_COMMANDS[profile_id])
    if {"M", "N"} <= available:
        motors["legs"] = ("M", "N")
    if profile_id == "g":
        motors["lumbar"] = ("p", "q")
    elif profile_id == "h":
        motors["tilt"] = ("p", "q")
    elif profile_id == "zero":
        motors.update({"lumbar": ("p", "q"), "tilt": ("P", "Q")})
    elif profile_id == "wr1140":
        motors.update({"lumbar": ("p", "q"), "auxiliary": ("P", "Q")})
    elif profile_id in {"four", "two"}:
        motors.update({"auxiliary_1": ("p", "q"), "auxiliary_2": ("P", "Q")})
    elif profile_id == "a":
        # PanelA selects the rendered p/q versus P/Q axis from name[26].
        if len(name) > 26 and name[26] == "H":
            motors["lumbar"] = ("p", "q")
        else:
            motors["tilt"] = ("P", "Q")
    elif profile_id == "d":
        pair = ("p", "q") if len(name) > 26 and name[26] == "H" else ("P", "Q")
        if c16 == "3":
            motors["tilt" if c18 == "6" else "neck"] = pair
        elif c16 == "4":
            motors["lumbar"] = pair
        elif c16 == "8":
            motors["tilt"] = pair
        else:
            motors["auxiliary"] = pair

    rgb = profile_id in {"zero", "five_new", "six_new", "eight_new", "wr1140"}
    profile = _profile(
        f"motosleep_hhc_{profile_id}",
        MotoSleepTransport.HHC_ASCII,
        motors=motors,
        commands=_HHC_COMMANDS[profile_id],
        explicit_stop=True,
        rgb_light=rgb,
        raw_hhc=not (len(name) > 22 and name[22] == "M"),
    )
    if profile_id in {"f", "g", "h", "wr1140", "five_new", "six_new", "eight_new"}:
        # MainPanel sends 00012 when the current bind state is false and 00015
        # when it is true.  Store desired-state opcodes as (enable, disable).
        profile = replace(profile, synchro=("00012", "00015"))
    return profile


_MOTO_RE = re.compile(r"^MOTO(B|S)(\d{2})(\w)([0-9])([BCD])([A-Za-f])(\w)(\w)(\w)")


def _unknown_moto_profile() -> MotoSleepProfile:
    """Return a binary transport with no speculative bed controls."""
    return MotoSleepProfile(
        profile_id="motosleep_moto_unknown",
        transport=MotoSleepTransport.MOTO_BINARY,
        motors=_frozen(),
        presets=_frozen(),
    )


def _resolve_moto(name: str) -> MotoSleepProfile:
    match = _MOTO_RE.match(name)
    if match is None or len(name) != 28:
        return _unknown_moto_profile()

    page = name[7]
    motors_by_page: dict[str, dict[str, MotorPair]] = {
        # Commands and labels are taken from each page's BarButton instances.
        "0": {
            "back": (0x0002, 0x0001),
            "legs": (0x0200, 0x0100),
            "head": (0x0020, 0x0010),
            "lumbar": (0x0080, 0x0040),
            "feet": (0x0008, 0x0004),
        },
        "1": {
            "back": (0x0020, 0x0010),
            "legs": (0x0200, 0x0100),
            "head": (0x0002, 0x0001),
        },
        "2": {
            "back": (0x0002, 0x0001),
            "legs": (0x0200, 0x0100),
            "lumbar": (0x0080, 0x0040),
            "feet": (0x0008, 0x0004),
        },
        "3": {"back": (0x0002, 0x0001), "legs": (0x0200, 0x0100), "feet": (0x0008, 0x0004)},
        "4": {
            "back": (0x0002, 0x0001),
            "legs": (0x0200, 0x0100),
            "head": (0x0020, 0x0010),
            "lumbar": (0x0080, 0x0040),
            "feet": (0x0008, 0x0004),
        },
        "5": {"back": (0x0002, 0x0001), "legs": (0x0200, 0x0100), "feet": (0x0008, 0x0004)},
        "6": {
            "neck": (0x0020, 0x0010),
            "back": (0x0002, 0x0001),
            "lumbar": (0x0080, 0x0040),
            "legs": (0x0008, 0x0004),
        },
        "7": {"back": (0x0002, 0x0001), "legs": (0x0008, 0x0004), "lumbar": (0x0080, 0x0040)},
        "8": {
            "back": (0x0002, 0x0001),
            "legs": (0x0200, 0x0100),
            "head": (0x0020, 0x0010),
            "lumbar": (0x0080, 0x0040),
            "feet": (0x0008, 0x0004),
        },
        "9": {
            "back": (0x000A, 0x0005),
            "lumbar": (0x0200, 0x0100),
            "legs": (0x00A0, 0x0050),
        },
    }
    profile_names = {
        "0": "wrs23ms",
        "1": "wrs14dmm",
        "2": "wrs18ms",
        "3": "wrs14ms",
        "4": "wrs20ms",
        "5": "wrs16ms",
        "6": "wrc30mms",
        "7": "wrs27ms",
        "8": "wrs20ms_swing",
        "9": "wr219",
    }
    if page not in motors_by_page or page not in profile_names:
        return _unknown_moto_profile()

    presets: dict[str, Command]
    swing: Command | None = None
    if page == "9":
        presets = {"flat": 0x5555, "anti_snore": 0x8009, "zero_g": 0x800B}
        swing = 0x9089
    else:
        presets = {"flat": 0x800E, "anti_snore": 0x8009, "tv": 0x800A, "zero_g": 0x800B}
        if page == "8":
            swing = 0x8014

    memory_recall = () if page == "9" else (0x800C, 0x800D)
    memory_save = () if page == "9" else (0x811D, 0x811E)
    return MotoSleepProfile(
        profile_id=f"motosleep_moto_{profile_names[page]}",
        transport=MotoSleepTransport.MOTO_BINARY,
        motors=_frozen(motors_by_page[page]),
        presets=_frozen(presets),
        memory_recall=memory_recall,
        memory_save=memory_save,
        # The app's remaining model flags select runtime massage/audio tables.
        # Do not infer bed capabilities or friendly labels without those tables.
        stop=((0x9088, 1), 6, 100) if page == "9" else ((0x0000, 0), 5, 100),
        write_with_response=True,
        swing=swing,
    )


def resolve_motosleep_profile(device_name: str | None) -> MotoSleepProfile:
    """Resolve the exact OEM-app profile selected by an advertised local name."""
    name = device_name or ""
    upper_name = name.upper()
    if upper_name.startswith("MOTO"):
        return _resolve_moto(name)
    if "HHC" in upper_name and len(name) == 14:
        return _resolve_power_bob(name)
    if "HHC" in upper_name and len(name) >= 14:
        return _resolve_hhc(name)

    # Manual configurations created before model routing had no reliable local
    # name.  Keep their prior two-axis behavior, but do not expose speculative
    # auxiliary, massage, light, memory, or sync entities.
    return replace(
        _profile(
            "motosleep_unknown",
            MotoSleepTransport.HHC_ASCII,
            motors={"back": ("K", "L"), "legs": ("M", "N")},
            commands="KLMNO",
            explicit_stop=True,
        ),
        rgb_light=False,
    )
