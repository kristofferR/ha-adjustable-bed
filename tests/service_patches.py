"""Patch a shared ``services`` helper everywhere a family action also looks it up."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from importlib import import_module
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
    family_module = f"custom_components.adjustable_bed.{family}"
    with ExitStack() as stack:
        mock = stack.enter_context(patch(target, *args, **kwargs))
        if hasattr(import_module(family_module), name):
            stack.enter_context(patch(f"{family_module}.{name}", mock))
        yield mock
