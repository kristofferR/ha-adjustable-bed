"""Restonic has no app-specific discovery signature; shared names stay manual.

Its scan accepts any nonempty name. Registering that as a Home Assistant
matcher would discover unrelated Bluetooth devices.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
