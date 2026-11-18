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
)
# Whole labels whose literal reading would mislead.
_NAMES: Final[dict[str, str]] = {"ANTI": "Anti-snore"}


def _word(word: str) -> str:
    if word.upper() in _ACRONYMS:
        return word.upper()
    if word.isalpha() and word.isupper() and len(word) > 1 and not re.fullmatch(r"[IVX]+", word):
        return word.lower()
    # str.title() turns a roman numeral such as III into Iii.
    if re.fullmatch(r"I[ivx]+", word):
        return word.upper()
    return word


def display_label(label: str) -> str:
    """Return the entity name for an artifact action label."""
    if named := _NAMES.get(label):
        return named
    text = _NOTES.sub("", label.replace("_", " ")).strip()
    for pattern, replacement in _PHRASES:
        text = pattern.sub(replacement, text)
    # Some catalogs repeat a label as its own heading: "Music: Music".
    heading, _, rest = text.partition(": ")
    if rest == heading:
        text = heading
    text = " ".join(_word(word) for word in text.split(" "))
    return text[:1].upper() + text[1:]
