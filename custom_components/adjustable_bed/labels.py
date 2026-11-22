"""Display names for action labels a controller takes from an app or manual.

Catalogs keep each label as the artifact shows it, so they stay evidence. An
entity named after one gets this display form instead: no provenance notes, no
identifier underscores, no shouting or ``str.title()`` artifacts. Only display
text changes; keys and unique IDs never derive from it.
"""

from __future__ import annotations

import re
from typing import Final

_ACRONYMS: Final = frozenset({"TV", "USB", "RGB", "LED", "BLE", "AI", "MAC", "PIN", "ID"})
# Names that keep their capital in the middle of a label.
_PROPER: Final = frozenset({"Bluetooth", "Hz", "Pilates"})
# A capitalized word or word part: "Up", the "Off" of "On/Off".
_CAPITALIZED: Final = re.compile(r"(?<![A-Za-z])[A-Z][a-z]+(?![A-Za-z])")
# Notes about where a label came from, not what the control does.
_NOTES: Final = re.compile(
    r"\s*\((?:app gesture|unlabeled touch area)\)|\s+(?:preset icon|pictogram|preset)$"
    r"|-labeled remote action$|^bed\s+",
    re.IGNORECASE,
)
_PHRASES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\banti[ -]?snore\b", re.IGNORECASE), "anti-snore"),
    (re.compile(r"\bzero[ -]?g\b|\bzg\b", re.IGNORECASE), "zero G"),
    (re.compile(r"\bwhole-bed\b", re.IGNORECASE), "whole bed"),
    (re.compile(r"-and-"), " and "),
    (re.compile(r"\bhead foot both\b", re.IGNORECASE), "head and foot"),
    (re.compile(r"\bunder ?bed\b", re.IGNORECASE), "under-bed"),
    # The 4.x "Massage: Mode" style: one name style, "Massage mode".
    (re.compile(r"^(massage|fan): ", re.IGNORECASE), r"\1 "),
)
# Whole labels whose literal reading would mislead.
_NAMES: Final[dict[str, str]] = {"ANTI": "Anti-snore"}


def _word(word: str, *, first: bool) -> str:
    if word.upper() in _ACRONYMS:
        return word.upper()
    if word.isalpha() and word.isupper() and len(word) > 1 and not re.fullmatch(r"[IVX]+", word):
        return word.lower()
    # str.title() turns a roman numeral such as III into Iii.
    if re.fullmatch(r"I[ivx]+", word):
        return word.upper()
    # Sentence case: "Head Up" is "Head up", "On/Off" is "on/off".
    return _CAPITALIZED.sub(
        lambda match: (
            match[0] if match[0] in _PROPER or first and match.start() == 0 else match[0].lower()
        ),
        word,
    )


def display_label(label: str, *, mid_sentence: bool = False) -> str:
    """Return the entity name for an artifact action label.

    ``mid_sentence`` is for a label set inside a longer name ("Save {preset}"):
    its first word is lowercased like the rest.
    """
    label = _NAMES.get(label, label)
    text = _NOTES.sub("", label.replace("_", " ")).strip()
    # A number run into a word: "Mode1" is "Mode 1".
    text = re.sub(r"(?<=[a-z]{2})(?=\d)", " ", text)
    for pattern, replacement in _PHRASES:
        text = pattern.sub(replacement, text)
    # Some catalogs repeat a label as its own heading: "Music: Music".
    heading, _, rest = text.partition(": ")
    if rest == heading:
        text = heading
    words = text.split(" ")
    text = " ".join(
        _word(word, first=index == 0 and not mid_sentence) for index, word in enumerate(words)
    )
    return text if mid_sentence else text[:1].upper() + text[1:]
