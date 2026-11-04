"""Patch a shared ``services`` helper everywhere a family action also looks it up."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch


@contextmanager
def patch_with_family(family: str, target: str, *args: Any, **kwargs: Any) -> Iterator[Any]:
    """Patch ``target`` in ``services`` and the same name in ``family`` with one mock.

    Generic actions resolve shared helpers in ``services``; a family module that
    imported the helper resolves its own binding, so both must see the same mock.
    """
    module, name = target.rsplit(".", 1)
    assert module == "custom_components.adjustable_bed.services", target
    with patch(target, *args, **kwargs) as mock, patch(
        f"custom_components.adjustable_bed.{family}.{name}", mock
    ):
        yield mock
