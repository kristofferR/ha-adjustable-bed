"""Bedgear app candidate; exact length and selector validation is separate."""

from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names('HHC', bed_types={'bedgear', 'l2motion'}, anywhere=True),)
