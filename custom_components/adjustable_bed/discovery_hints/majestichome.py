"""Majestic Home scans unfiltered and manually selects its product (row151 E10).

Shared GATT services do not identify this app. Existing generic matchers cover
the transport; there is no app-specific advertisement matcher to generate.
"""

from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
