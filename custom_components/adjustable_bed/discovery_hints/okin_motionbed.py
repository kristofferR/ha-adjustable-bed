"""OKIN Motion Bed scans all devices. No app-specific advertisement signature.

Select this app explicitly by name and the bed by MAC. FFE5/FFE0 are not
identity evidence and must never automatically select this profile.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
