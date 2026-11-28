"""Dreamotion Smart requires explicit app selection.

Android's raw advertisement substring and network-state setup filter cannot
be represented by HA's structured advertisement fields. Do not promote its
JESP_ name or FE60 service alone to an app identity.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
