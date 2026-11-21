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
    "ubl": "under-bed light",
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


# Resources whose words alone mislead: the remote's Set key arms programming and
# saves nothing itself; the later "massage off" keys repeat the first.
_RESOURCE_NAMES: Final[dict[str, str]] = {
    "com_set_old": "Program",
    "k_set_old": "Program",
    "com_msg_off2": "Massage off",
    "com_msg_off3": "Massage off",
}


def resource_label(name: str) -> str:
    """Name an app control from its Android string resource, e.g. ``com_m1_set``."""
    if name.startswith("Control "):
        return "Button " + name.removeprefix("Control ")
    if (named := _RESOURCE_NAMES.get(name)) is not None:
        return named
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
    label = re.sub(r"^Massage (\d+) min$", r"Massage timer \1 minutes", label)
    if save and not label.startswith(("M", "TV", "Zero Gravity", "Anti-snore")):
        label = label[:1].lower() + label[1:]
    return f"Save {label}" if save else label


# ---------------------------------------------------------------- MH family
#
# The Richmat MH-family apps (Revive, Nisco, MLILY Supreme, the RUF apps and
# Bed Tech's classic app) send one command code per control, and each code
# does one thing. Their labels say it in many ways ("Msg Head Intensity Inc",
# "Head Intensity+", "Head+"), so a control is named by its code. Nisco and
# MLILY Supreme name every code ("Massage Head Intensity Inc"); the Richmat app
# names the same codes by enum. A layout's own label still decides when it
# says more than the code, or something else.

# Each control code's name, with the feature it belongs to. Massage controls use
# the words the shared massage descriptions take.
MASSAGE: Final = "massage"
HEAT: Final = "heat"
MUSIC: Final = "music"
FAN: Final = "fan"
LIGHT: Final = "light"
OTHER: Final = "other"
MH_CODES: Final[dict[int, tuple[str, str]]] = {
    0x32: (MASSAGE, "Head massage on/off"),
    0x33: (MASSAGE, "Foot massage on/off"),
    0x34: (MASSAGE, "Massage intensity up"),
    0x35: (MASSAGE, "Massage intensity down"),
    0x36: (MASSAGE, "Massage speed up"),
    0x37: (MASSAGE, "Massage speed down"),
    0x38: (MASSAGE, "Pulse massage"),
    0x39: (MASSAGE, "Wave massage"),
    0x3A: (MASSAGE, "Constant massage"),
    0x47: (MASSAGE, "Massage off"),
    0x48: (MASSAGE, "Massage mode"),
    0x49: (MASSAGE, "Wave massage forward"),
    0x4A: (MASSAGE, "Wave massage reverse"),
    0x4B: (MASSAGE, "Wave massage 3"),
    0x4C: (MASSAGE, "Head massage intensity up"),
    0x4D: (MASSAGE, "Head massage intensity down"),
    0x4E: (MASSAGE, "Foot massage intensity up"),
    0x4F: (MASSAGE, "Foot massage intensity down"),
    0x5A: (MASSAGE, "Massage off and flat"),
    0x5D: (MASSAGE, "Head and foot massage on"),
    0x5E: (MASSAGE, "Head and foot massage off"),
    0x67: (MASSAGE, "Massage intensity 1"),
    0xAF: (MASSAGE, "Massage intensity 2"),
    0x68: (MASSAGE, "Massage intensity 3"),
    0x6F: (MASSAGE, "Head and foot massage on/off"),
    # The second head and foot steps never share a model with the first.
    0xA4: (MASSAGE, "Head massage intensity up"),
    0xA5: (MASSAGE, "Foot massage intensity up"),
    0xE0: (MASSAGE, "Lumbar massage intensity up"),
    0x9C: (HEAT, "Heat off"),
    0x9D: (HEAT, "Heat low"),
    0x9E: (HEAT, "Heat medium"),
    0x9F: (HEAT, "Heat high"),
    0xA0: (HEAT, "Heat on/off"),
    0xB7: (MUSIC, "Music volume"),
    0xB9: (MUSIC, "Music on/off"),
    0xC4: (MUSIC, "USB music on/off"),
    0xD2: (MUSIC, "Previous music track"),
    0xD3: (MUSIC, "Next music track"),
    0xD4: (MUSIC, "Music volume up"),
    0xD5: (MUSIC, "Music volume down"),
    0xD6: (MUSIC, "Music vibration mode"),
    0xD7: (MUSIC, "Music play/pause"),
    0xD8: (MUSIC, "Bluetooth music on/off"),
    0xE1: (FAN, "Fan 1 intensity up"),
    0xB8: (MUSIC, "Music switch"),
    0x50: (LIGHT, "Light"),
    0x75: (LIGHT, "Under-bed light off"),
    # The motor page's lock key: the smart set lock (its dedicated switch sends it too).
    0x84: (OTHER, "Smart set lock on/off"),
}
# Codes whose catalogs name them without saying what they do.
_MH_UNCLEAR: Final = frozenset({0xB8})
# Words a label may add to its code's name without saying anything else: the
# Nisco catalog's "Massage Head Foot Intensity Inc" is the code every other app
# calls "Intensity+".
_MH_SCOPE: Final[dict[int, frozenset[str]]] = {
    **dict.fromkeys((0x34, 0x35, 0x36, 0x37), frozenset({"head", "foot"})),
    0x5A: frozenset({"reset"}),
}
# The timer codes set the duration their label states: one code is 10 minutes
# on one model and 2 hours on another.
_MH_TIMERS: Final[dict[int, str]] = {
    0x5F: MASSAGE, 0x60: MASSAGE, 0x61: MASSAGE, 0x63: MASSAGE, 0xA1: HEAT, 0xA2: HEAT,
}
_FEATURE_WORDS: Final[dict[str, frozenset[str]]] = {
    MASSAGE: frozenset({"massage", "vibration"}),
    HEAT: frozenset({"heat", "heating", "warm"}),
    MUSIC: frozenset({"music", "bluetooth", "volume", "usb", "track", "song"}),
    FAN: frozenset({"fan", "fans"}),
    LIGHT: frozenset({"light", "lights", "lamp"}),
}
# Spellings a label uses for one word; the empty string drops the word.
_SAME: Final[dict[str, str]] = {
    "msg": "massage",
    "massager": "massage",
    "inc": "up",
    "dec": "down",
    "+": "up",
    "-": "down",
    "virbration": "vibration",
    "ubl": "under-bed light",
    "led": "light",
    "min": "minutes",
    "mins": "minutes",
    "minute": "minutes",
    "hour": "hours",
    "h": "hours",
    "all": "",
    "both": "",
    "level": "",
    "switch": "on/off",
    "toggle": "on/off",
}
_TOGGLES: Final = re.compile(r"\b(?:on[ /]?off|start[ /]?stop)\b")
_PLAY: Final = re.compile(r"\b(?:pause[ /]?start|start[ /]?pause|pause[ /]?play|play[ /]?pause|pause)\b")


def _words(label: str, *, fillers: bool = False) -> list[str]:
    """A label's words, lower case, in one spelling."""
    text = " ".join(label.replace("\\n", " ").replace("_", " ").split()).lower()
    text = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", text)
    text = re.sub(r"(?<=\w)([+-])$", r" \1", text)
    text = _PLAY.sub("play/pause", _TOGGLES.sub("on/off", text))
    words: list[str] = []
    for word in text.replace(":", " ").split():
        same = _SAME.get(word, word)
        words.extend((same or word).split() if fillers else same.split())
    return words


def _feature_of(words: list[str]) -> str | None:
    return next((f for f, known in _FEATURE_WORDS.items() if known & set(words)), None)


def _with_feature(feature: str, words: list[str]) -> str:
    text = " ".join(words)
    if feature in _FEATURE_WORDS and _feature_of(words) != feature:
        text = f"{feature} {text}"
    return text[:1].upper() + text[1:]


def richmat_mh_name(code: int, label: str, *, massage_page: bool = False) -> tuple[str, bool]:
    """Name a Richmat MH-family control, and say whether the catalogs establish it.

    A label that only says part of what its code does ("Head+") takes the
    code's name. A toggle label keeps its own button ("Start Stop" is "Massage
    on/off"). A label that names another feature or action keeps its words and
    is not established, nor is a code no catalog names.
    """
    words = _words(label)
    text = " ".join(words)
    if code in _MH_TIMERS and (
        duration := re.search(r"(\d+) (minutes|hours)|(minutes|hours) (\d+)", text)
    ):
        number, unit = duration[1] or duration[4], duration[2] or duration[3]
        return _with_feature(_MH_TIMERS[code], ["timer", number, unit]), True
    shown = _words(label, fillers=True)
    if code in _MH_UNCLEAR:
        return MH_CODES[code][1], False
    if code not in MH_CODES:
        return _with_feature(MASSAGE if massage_page else OTHER, shown), False
    feature, name = MH_CODES[code]
    known = _words(name)
    own = _FEATURE_WORDS.get(feature, frozenset())
    core = [w for w in words if w not in own]
    # An app's counter ("All Off2") repeats its control.
    if core and core[-1].isdigit() and not any(w.isdigit() for w in known):
        core.pop()
    # A bare symbol, or part of what the code does ("Head+"), names the code.
    if not re.search(r"[a-z]", text) or set(core) <= set(known) - own | _MH_SCOPE.get(code, set()):
        return name, True
    if _feature_of(words) not in (None, feature):
        return screen_label(" ".join(shown)), False
    # A toggle where the code turns the feature on or off: the label's own button.
    if core == ["on/off"] and {"on", "off", "on/off"} & set(known):
        return _with_feature(feature, core), True
    return _with_feature(feature, shown), False


# A preset's name in the shared words, by the labels the apps give it.
_PRESET_NAMES: Final[dict[str, tuple[str, ...]]] = {
    "Zero gravity": ("zg", "zero g", "zero gravity", "zg 3", "zg 4", "space"),
    "Zero gravity 2": ("zg 2", "zero g 2", "zero gravity 2"),
    "Anti-snore": (
        "snore", "anti snore", "anti-snore", "anti snore 3", "anti snoring", "anti-snoring",
        "snoring intervention", "snore intervention", "snoring intervention anti snore",
        "text snore intercept", "anti ronquidos",
    ),
    "TV": ("tv", "tv position"),
    "Lounge": ("lounge", "lounge position"),
    "Yoga": ("yoga", "yoga position", "xiaofeiyan"),
    "Reading": ("read", "reading", "reading position"),
    "Movie": ("movie", "movie watching", "movie viewing"),
    "Relieving stress": ("relieving stress", "erlieving stress"),
    "Flat 2": ("flat 2",),
    "Flat sleep": ("flat sleep", "flat sleeping"),
    "One-click head up": ("one-click head up", "head up only"),
    "One-click foot up": ("one-click foot up", "foot up only"),
    "Get-up assist": ("help get up", "assist", "assisted rise", "up", "get-up assist"),
    "Lumbar position": ("lumbar", "lumbar pos", "lumbar model"),
    "Pressure relief position": ("release press", "releasing press"),
    "Motion massage 15 minutes": ("v 15", "motor keep 15"),
    "Motion massage 30 minutes": ("v 30", "motor keep 30"),
    "Sleep aid": ("sleep aid", "sleep aid mode 1", "lull", "one-tap sleep aid"),
    "Sleep aid 2": ("one-tap sleep aid 2",),
    "Sleep aid 3": ("one-tap sleep aid 3",),
    "Sleeping": ("sleeping",),
    "Sleep": ("sleep",),
    "Timed flat": ("timing levelling",),
    "Factory reset": ("factory reset",),
    "Head up foot down": ("head up foot down",),
    "Head down foot up": ("head down foot up",),
    "Head up foot up": ("head up foot up",),
}
# The presets every app knows, which name one position only.
SHARED_PRESETS: Final = frozenset({"Zero gravity", "Zero gravity 2", "Anti-snore", "TV", "Lounge", "Yoga", "Reading"})
_PRESET_ALIASES: Final = {alias: name for name, aliases in _PRESET_NAMES.items() for alias in aliases}
# Words some catalogs append to a preset's label: its recall or save role, or
# an extraction note.
_PRESET_NOTES: Final = re.compile(
    r"(?:\s+(?:back|set|save|primary|recall/action|mode))+$", re.IGNORECASE
)
_MEMORY_LABEL: Final = re.compile(r"(?:m|mem|memory)\s*(?P<slot>[1-9])?(?: [a-e])?", re.IGNORECASE)


def preset_name(label: str, *, slot: int | None = None) -> str:
    """A recalled preset's name: the shared words, or the app's own name for it.

    ``slot`` is the memory slot a recall code stands for, which names a label
    that only says "M" or "Memory".
    """
    text = " ".join(label.replace("\\n", " ").split())
    text = _PRESET_NOTES.sub("", text).strip() or text
    if (memory := _MEMORY_LABEL.fullmatch(text)) and (memory["slot"] or slot):
        return f"Memory {memory['slot'] or slot}"
    if position := re.fullmatch(r"pos\s*(\d)", text, re.IGNORECASE):
        return f"Position {position[1]}"
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    if (name := _PRESET_ALIASES.get(text.lower())) is not None:
        return name
    return screen_label(text)


# The Richmat app names its actions by enum. These read as the MH family's names
# for the same controls; every other enum reads well as ``function_label`` gives it.
_APP_NAMES: Final[dict[str, str]] = {
    "RelieveZeroGravitySetting": "Factory reset",
    "MassageModeChange": "Massage mode",
    "MassageModeAllOff": "Massage off",
    "MassageModeAllOn": "Massage on",
    "MassageModePulse": "Pulse massage",
    "MassageModeWave": "Wave massage",
    "MassageModeConstant": "Constant massage",
    "MassageModeWaveFirstMode": "Wave massage 1",
    "MassageModeWaveSecondMode": "Wave massage 2",
    "MassageModeWaveThirdMode": "Wave massage 3",
    "Massage1OpenOrClose": "Head massage on/off",
    "Massage2OpenOrClose": "Foot massage on/off",
    "MassageHeadOff": "Head massage off",
    "MassageFootOff": "Foot massage off",
    "MassageHeadInstensFirstMode": "Head massage level 1",
    "MassageHeadInstensSecondMode": "Head massage level 2",
    "MassageHeadInstensThirdMode": "Head massage level 3",
    "MassageFootInstensFirstMode": "Foot massage level 1",
    "MassageFootInstensSecondMode": "Foot massage level 2",
    "MassageFootInstensThirdMode": "Foot massage level 3",
    "MassageInstensityFirstGear": "Massage intensity 1",
    "MassageInstensitySecondGear": "Massage intensity 2",
    "MassageInstensityThirdGear": "Massage intensity 3",
    "MassageLumbarInstensityStrengthen": "Lumbar massage intensity up",
    "Massage15MinuteUpAndDown": "Motion massage 15 minutes",
    "Massage30MinuteUpAndDown": "Motion massage 30 minutes",
    "Massage15MinuteSpineGuard": "Spine guard massage 15 minutes",
    "MotorAndMassageAllOff": "Motor and massage off",
    "MotorReset2": "Flat 2",
    "BedLight": "Light",
    "BedLightClose": "Light off",
    "MusicBlueToothSwitch": "Bluetooth music on/off",
    "MusicPausePlay": "Music play/pause",
    "MusicNextSong": "Next music track",
    "MusicPreviousSong": "Previous music track",
    "AdjustVolume": "Music volume",
    "MusicCut": "Music switch",
    "MusicSwitchSoundTrack": "USB music mode",
    "MassageFanInstensityStrengthen": "Fan 1 intensity up",
    "Fan1InstensityStrengthen": "Head fan intensity up",
    "Fan2InstensityStrengthen": "Foot fan intensity up",
    "FanAllOff": "Fan off",
    "FanChangeMode": "Fan mode",
    "FanForwardAndBackwardChange": "Fan forward/reverse",
    "FanTimer2Hour": "Fan timer 2 hours",
    "FanTimer3Hour": "Fan timer 3 hours",
    "FanTimer5Hour": "Fan timer 5 hours",
    "HeatingSwitch": "Heat on/off",
    "HeatingOff": "Heat off",
    "HeatingLowGear": "Heat low",
    "HeatingMiddleGear": "Heat medium",
    "HeatingHighGear": "Heat high",
    "Heating30Min": "Heat timer 30 minutes",
    "Heating60Min": "Heat timer 60 minutes",
    "SwingModeSwitch": "Swing mode",
    "SwingOnAndOff": "Swing on/off",
    "AntiPinchSensitivityModeChange": "Anti-pinch sensitivity",
}
# Enums the catalog names without saying what they do.
_APP_UNCLEAR: Final = frozenset({"MusicCut", "RelieveSnoreSetting"})


def richmat_app_name(enum: str, label: str) -> tuple[str, bool]:
    """Name a Richmat app action, and say whether the catalog establishes it.

    The enum says what the action is; a fixed timer takes the duration the
    product's own label shows ("2h" on a 10-minute enum). A label naming another
    feature than the enum keeps its own words and is not established.
    """
    short = enum
    for prefix in _PREFIXES:
        short = short.removeprefix(prefix)
    if (minutes := re.fullmatch(r"Massage(\d+)MinuteTimer", short)) is not None:
        words = _words(label)
        duration = re.search(r"(\d+) (minutes|hours)", " ".join(words))
        return f"Massage timer {duration[0] if duration else f'{minutes[1]} minutes'}", True
    name = _APP_NAMES.get(short) or function_label(enum)
    words = _words(label)
    own = _feature_of(_words(name))
    if (shown := _feature_of(words)) is not None and shown != own and own is not None:
        return screen_label(" ".join(_words(label, fillers=True))), False
    # A toggle label on an on or off action: the product's own button.
    toggle = [w for w in words if w not in _FEATURE_WORDS.get(own or "", ())] == ["on/off"]
    if toggle and re.search(r"(?<!/)\b(?:on|off)$", name):
        return re.sub(r"(?<!/)\b(?:on|off)$", "on/off", name), True
    return name, short not in _APP_UNCLEAR
