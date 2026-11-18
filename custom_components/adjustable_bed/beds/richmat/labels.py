"""Readable entity labels for app-catalogued Richmat-family actions.

Several apps (HJBed, Casper/Hush Base, Good Vibe, Richmat app) name their
actions after one shared enum vocabulary such as
``deviceFunctionItemMassageHeadInstensityStrengthen``, and others ship screen
labels with line breaks and shouting capitals. These helpers turn both into
sentence-case names a person recognises. They only change display text: entity
keys and unique IDs are derived elsewhere and stay stable.
"""

from __future__ import annotations

import re
from typing import Final

_PREFIXES: Final = ("deviceFunctionItem", "deviceFunctionSofa", "deviceFunction")

# Whole names whose literal reading would mislead.
_NAMES: Final[dict[str, str]] = {
    "None": "No action",
    "Mlily Menu": "Menu",
    "Title Fan": "Fan menu",
    "Title Massage": "Massage menu",
    "Title Massage Japan": "Japanese massage menu",
    "Title Massage Russian": "Russian massage menu",
    "Title Timer": "Timer menu",
    "Send Start Detection": "Start detection",
    "Send Stop Detection": "Stop detection",
    "Forward": "Sofa forward",
    "Backward": "Sofa backward",
}

# Misspellings and literal translations in the shared vocabulary.
_PHRASES: Final[tuple[tuple[str, str], ...]] = (
    ("Lumber", "Lumbar"),
    ("Anti Snoring", "Anti-snore"),
    ("Instensity", "Intensity"),
    ("Instens", "Intensity"),
    ("Volumu", "Volume"),
    ("Pressur ", "Pressure "),
    ("Forword", "Forward"),
    ("Tile ", "Tilt "),
    ("Blue Tooth", "Bluetooth"),
    ("T V", "TV"),
    ("Un Wind", "Unwind"),
    ("Release Pressure Position", "Pressure relief position"),
    ("Intensity Strengthen", "Intensity up"),
    ("Intensity Weaken", "Intensity down"),
    ("Speed Strengthen", "Speed up"),
    ("Speed Weaken", "Speed down"),
    ("Coaxing Sleep Mode", "Sleep aid"),
    ("Help Sleep Mode", "Sleep aid"),
    ("Swing Help Sleep", "Swing sleep aid"),
    ("Help Get Up", "Get-up assist"),
    ("Music Shake Close", "Music vibration off"),
    ("Music Shake", "Music vibration"),
    ("First Gear", "Level 1"),
    ("Second Gear", "Level 2"),
    ("Third Gear", "Level 3"),
    ("High Gear", "High"),
    ("Middle Gear", "Medium"),
    ("Low Gear", "Low"),
    ("First Mode", "Mode 1"),
    ("Second Mode", "Mode 2"),
    ("Third Mode", "Mode 3"),
    ("Open Or Close", "On/off"),
    ("Light Close", "Light off"),
    ("Music Close", "Music off"),
    ("Vibration Close", "Vibration off"),
    ("Switch Sound Track", "Switch soundtrack"),
)

_KEEP_UPPER: Final = frozenset({"TV", "USB", "UBL", "LED", "RGB", "AI", "PIN", "ID"})
_PROPER: Final = frozenset({"Bluetooth"})
_SLOT: Final = re.compile(r"^[A-Z]\d+$")


def _sentence(words: list[str]) -> str:
    out = []
    for index, word in enumerate(words):
        if word.upper() in _KEEP_UPPER and word.isupper() or _SLOT.match(word) or word in _PROPER:
            out.append(word)
        elif index == 0:
            out.append(word[:1].upper() + word[1:].lower())
        else:
            out.append(word.lower())
    return " ".join(out)


def function_label(enum: str) -> str:
    """Name a ``deviceFunction*`` action the way a person would."""
    for prefix in _PREFIXES:
        if enum.startswith(prefix):
            enum = enum.removeprefix(prefix)
            break
    text = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])", " ", enum)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text).strip()
    if text in _NAMES:
        return _NAMES[text]
    text += " "
    for old, new in _PHRASES:
        text = text.replace(old, new)
    text = text.strip()
    if text in _NAMES:
        return _NAMES[text]
    words = text.split()
    # "Bed Light Switch" toggles: say so.
    if words and words[-1] == "Switch":
        words[-1] = "on/off"
    return _sentence(words)


_SCREEN: Final[dict[str, str]] = {
    "ZG": "Zero G",
    "POS1": "Position 1",
    "POS2": "Position 2",
    "POS3": "Position 3",
}


def screen_label(text: str) -> str:
    """Tidy a vendor screen label: one line, no shouting, known typos fixed."""
    words = " ".join(text.split())
    words = _SCREEN.get(words, words)
    for old, new in (("Massger", "Massager"), ("Virbration", "Vibration")):
        words = words.replace(old, new)
    result = []
    for word in words.split(" "):
        if word.isupper() and len(word) > 1 and word not in _KEEP_UPPER and not _SLOT.match(word):
            # Keep slash-joined acronyms such as TV/READ readable.
            word = "/".join(
                part if part in _KEEP_UPPER else part.capitalize() for part in word.split("/")
            )
        result.append(word)
    label = " ".join(result)
    return label[:1].upper() + label[1:]


_RESOURCE_WORDS: Final[dict[str, str]] = {
    "msg": "massage",
    "msg1": "massage 1",
    "msg2": "massage 2",
    "ubl": "underbed light",
    "zg": "Zero Gravity",
    "zg2": "Zero Gravity 2",
    "tv": "TV",
    "snore": "Anti-snore",
    "inc": "up",
    "dec": "down",
    "fir": "1",
    "sec": "2",
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "lean": "tilt",
    "flat2": "Flat 2",
    "swtch": "switch",
    "btn": "",
    "com": "",
    "k": "",
    "pos": "",
    "new": "",
    "old": "",
    "old2": "",
    "return": "",
    "back": "",
}


def resource_label(name: str) -> str:
    """Name an app control from its Android string resource, e.g. ``com_m1_set``."""
    if name.startswith("Control "):
        return "Button " + name.removeprefix("Control ")
    words = name.replace("_", " ").split()
    save = any(w in ("set", "save") for w in words)
    out: list[str] = []
    for word in words:
        if word in ("set", "save"):
            continue
        if word not in _RESOURCE_WORDS and not re.fullmatch(r"m\d", word):
            word = re.sub(r"^([a-z]+)(\d+)$", r"\1 \2", word)
        word = re.sub(r"^(\d+)min$", r"\1 min", word)
        for part in word.split():
            mapped = _RESOURCE_WORDS.get(part, part)
            if mapped:
                out.extend(mapped.split())
    # "1 2 up" names motors; join their numbers.
    if out and out[0].isdigit():
        out.insert(0, "motor")
    joined: list[str] = []
    for word in out:
        if word.isdigit() and joined and joined[-1][-1].isdigit() and joined[-2:-1] != ["intensity"]:
            joined[-1] += "+" + word
        else:
            joined.append(word)
    text = " ".join(joined).replace("on off", "on/off")
    label = _sentence(text.split()) if text else "Button"
    for proper in ("Zero gravity", "Anti-snore"):
        label = label.replace(proper.lower(), proper)
    label = label.replace("Zero gravity", "Zero Gravity").replace("zero gravity", "Zero Gravity")
    if save and not label.startswith(("M", "TV", "Zero Gravity", "Anti-snore")):
        label = label[:1].lower() + label[1:]
    return f"Save {label}" if save else label


# Command-name catalog labels (Nisco, MLILY Supreme) for controls the Richmat MH
# apps also show, in the MH buttons' wording.
_COMMAND_NAMES: Final[dict[str, str]] = {
    "Massage Head On Off": "Head On/Off",
    "Massage Foot On Off": "Foot On/Off",
    "Massage Off": "All Off",
    "All massage off": "All Off",
    "Massage Head Foot Both Off": "All Off",
    "Massage Head Foot Both On": "All On",
    "Massage Pulse": "Pulse",
    "Massage Wave": "Wave",
    "Massage Wave3": "Wave 3",
    "Massage Constant": "Constant",
    "Massage Mode": "Massage mode",
    "Massage Intensity1": "Intensity 1",
    "Massage Intensity2": "Intensity 2",
    "Massage Intensity3": "Intensity 3",
    "Massage Off Reset": "Massage off and flat",
    "Massage Head Foot Intensity Inc": "Massage: Intensity Up",
    "Massage Head Foot Intensity Dec": "Massage: Intensity Down",
    "Massage Head Foot Speed Inc": "Massage: Speed Up",
    "Massage Head Foot Speed Dec": "Massage: Speed Down",
    "Music Vibration Mode": "Vibration mode",
    "Head Up Only": "One-click Head Up",
    "Foot Up Only": "One-click Foot Up",
    "Head Foot Both": "Head and foot up",
    "Head Foot On Off": "Head and foot on/off",
    "Pillow": "Pillow up",
    "Pillow Lumbar Both Tilt Up": "Pillow and lumbar tilt up",
    "Pillow Lumbar Both Tilt Down": "Pillow and lumbar tilt down",
    "Ubl Off": "Underbed light off",
    "Ubl On Off": "Underbed light on/off",
    "Flat2": "Flat 2",
    "Zg2 Back": "Zero Gravity 2",
    "Memory1": "Memory 1",
    "Anti Snore3": "Anti-snore 3",
}
# The second head/foot step buttons never share a model with the first.
_COMMAND_ZONE: Final = re.compile(r"Massage (Head|Foot|Lumbar) Intensity (Inc|Dec)\d?")
_COMMAND_MINUTES: Final = re.compile(r"Massage (\d+)Min")


def command_label(label: str, *, save: bool = False) -> str:
    """Name a command-name catalog label (``Massage Head Intensity Inc``)."""
    if label == "Zg2 Set":
        return "Save Zero Gravity 2"
    if zone := _COMMAND_ZONE.fullmatch(label):
        name = f"Massage: {zone[1]} {'Up' if zone[2] == 'Inc' else 'Down'}"
    elif minutes := _COMMAND_MINUTES.fullmatch(label):
        name = f"Massage: Timer {minutes[1]} Minutes"
    else:
        name = _COMMAND_NAMES.get(label, label)
    return f"Save {name}" if save else name
