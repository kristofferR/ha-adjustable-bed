"""Shared scan names offer AW MOTION as a choice, without guessing a model."""

from ..profiles.awmotion import SCAN_WORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(*SCAN_WORDS, bed_types={"awmotion"}, anywhere=True),)
