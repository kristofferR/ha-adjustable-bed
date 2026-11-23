"""Match a raised error by its translation key rather than by its English text."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from homeassistant.exceptions import HomeAssistantError


@contextmanager
def raises_key(
    key: str | set[str], error: type[HomeAssistantError] = HomeAssistantError
) -> Iterator[pytest.ExceptionInfo[HomeAssistantError]]:
    """Expect ``error`` with translation ``key``, or one of a set of keys."""
    with pytest.raises(error) as raised:
        yield raised
    keys = {key} if isinstance(key, str) else key
    assert raised.value.translation_key in keys, raised.value
