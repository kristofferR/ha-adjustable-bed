"""Ronco Motion only refines names admitted by existing Bluetooth matchers.

Shared Richmat names identify an app candidate, never an ECONOMY/PREMIUM layout.
The app's unfiltered scan is not an extra passive HA matcher.
"""
from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
