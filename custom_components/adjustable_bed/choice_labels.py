"""Tidy catalog text before it is shown as a setup choice."""

from __future__ import annotations

import re

_TRUNCATION = re.compile(r"\s*(?:\.\.\.|…)$")


def clean_choice_label(text: str) -> str:
    """Return catalog text as one tidy line.

    Vendor catalogs carry line breaks (some escaped as a literal ``\\n``),
    surrounding quotes, a trailing ``...`` where a name was cut, and trailing
    slashes. None of that helps someone pick their remote.
    """
    text = " ".join(text.replace("\\n", " ").split())
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = text[1:-1].strip()
    return _TRUNCATION.sub("", text).rstrip(" /")
