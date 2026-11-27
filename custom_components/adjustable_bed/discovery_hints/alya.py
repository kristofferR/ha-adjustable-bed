"""Alya requires explicit setup: raw scan offsets are not HA manufacturer data.

The app accepts every named device as its CB fallback, so no safe automatic
advertisement matcher exists. Shared ORE/Sino/UART UUIDs remain other apps' hints.
"""
from ._hints import Hint

HINTS: tuple[Hint, ...] = ()
