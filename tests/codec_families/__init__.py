"""Codec families, one module each, discovered by the codec contract (#745).

Each public module in this package declares ``FAMILY = CodecFamily(...)`` for
the bed types it owns, so parallel family PRs edit only their own module.
Bed types that keep their own wire format are listed in ``_standalone.py``.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

# Bed type -> (config key, profile choices) for the app routes of a family.
AppRoutes = Mapping[str, tuple[str, tuple[str, ...]]]


def _no_variant(_key: str, _bed_type: str) -> str | None:
    return None


def spelled_frames(pattern: str, flags: int = 0) -> Callable[[str], set[str]]:
    """Find frames spelled in backticks as hex, spaced or compact."""
    regex = re.compile(pattern, flags)
    return lambda text: {match.replace(" ", "").lower() for match in regex.findall(text)}


@dataclass(frozen=True, kw_only=True)
class CodecGuide:
    """What ``tests/test_codec_docs.py`` checks in a family's codec guide.

    - ``spelled``: the guide's complete frames, as compact lowercase hex. Each
      must be in ``frozen``.
    - ``variant``: the protocol variant that reaches a profile key on a bed type,
      for checking the guide's bed types against the factory.
    """

    path: str
    spelled: Callable[[str], set[str]]
    frozen: frozenset[str]
    variant: Callable[[str, str], str | None] = _no_variant


@dataclass(frozen=True, kw_only=True)
class CodecFamily:
    """One codec family's registration.

    - ``profiles``: profile class -> frozen vectors by profile key.
    - ``bed_types``: bed types whose controller is a profile over this codec.
    - ``app_routes``: codec-backed bed types whose app profile is a choice.
    - ``pending``: bed types planned for this family, each with its #745 item.
      Migrating one moves it from ``pending`` to ``bed_types``.
    - ``guide``: what the docs tests check in the family's codec guide.
    """

    profiles: Mapping[type, Mapping[str, frozenset[str]]]
    bed_types: frozenset[str]
    app_routes: AppRoutes = field(default_factory=dict)
    pending: Mapping[str, str] = field(default_factory=dict)
    guide: CodecGuide | None = None


def families() -> dict[str, CodecFamily]:
    """Every family module's ``FAMILY``, by module name."""
    return {
        info.name: importlib.import_module(f"{__name__}.{info.name}").FAMILY
        for info in pkgutil.iter_modules(__path__)
        if not info.name.startswith("_")
    }
