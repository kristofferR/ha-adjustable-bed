"""App profiles over the JMC400 codec (``codec/jmc.py``).

``JENSEN`` is the Jensen Adjustable Sleep app's JMC400 route, the ``jensen`` bed
type, from the audits of ``air.no.jensen.adjustablesleep`` 2.0.29 (98) and
2.0.37 (106) and the #631 JMC400 capture. ``SVANE_REMOTE`` is the Svane Remote
1.8 app (``com.svane.svaneremote``, row130): its JMC400 route, the ``svane`` bed
type's ``svane_remote_jmc`` variant, sends every frame below, and its
multi-service route sends the same light frames to its own lamp roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Final

from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities


@dataclass(frozen=True, slots=True, kw_only=True)
class JmcProfile:
    """What one app sends after a light or fan level."""

    key: str
    light_on: bytes
    """The three bytes after a light level."""
    light_off: bytes
    """The three bytes after level 0 in the app's light-off frame."""
    fan: bytes | None = None
    """The four bytes after a fan level; ``None`` when the app sends no fan frame."""
    execution: ClassVar[ExecutionCapabilities] = NO_EXECUTION_CAPABILITIES
    """Each controller declares its own (#483, #516)."""


JENSEN: Final = JmcProfile(
    key="jensen",
    light_on=bytes(3),
    # A fixed frame in 2.0.37 (TV078), unlike the level frame's layout.
    light_off=bytes((0x00, 0x00, 0x32)),
    fan=bytes((0x00, 0x00, 0x00, 0x50)),
)
SVANE_REMOTE: Final = JmcProfile(
    key="svane_remote",
    light_on=bytes((0x01, 0x00, 0x64)),
    light_off=bytes(3),
)
PROFILES: Final[dict[str, JmcProfile]] = {
    profile.key: profile for profile in (JENSEN, SVANE_REMOTE)
}
