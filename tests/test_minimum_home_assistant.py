"""An older Home Assistant stops on import with one message naming the minimum."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.minimum_home_assistant import MINIMUM, require


def test_an_older_home_assistant_is_told_the_minimum() -> None:
    with pytest.raises(ImportError, match=r"needs Home Assistant 2026\.11\.0 or newer.*2026\.10\.4"):
        require("2026.10.4")
    require(MINIMUM)

