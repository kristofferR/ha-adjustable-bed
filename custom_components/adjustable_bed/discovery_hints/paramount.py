"""Paramount advertises session-state services, without name matching."""

from ..codec.paramount import CONNECT_WAIT_UUID, REGISTRATION_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = (
    *services(CONNECT_WAIT_UUID, REGISTRATION_UUID, bed_types={"paramount"}),
)
