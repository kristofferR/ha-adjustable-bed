"""Flexx's case-sensitive advertisement-name words offer an explicit app choice."""

from ..profiles.flexx_motion import SCAN_WORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(*SCAN_WORDS, bed_types={'flexx_motion'}, anywhere=True, packet_name_only=True),
)
