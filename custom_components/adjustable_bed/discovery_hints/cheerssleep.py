"""CheersSleep's service filter, refined by the first manufacturer entry."""

from ..codec.cheerssleep import SERVICE
from ._hints import services

HINTS = services(SERVICE, bed_types={"cheerssleep"})
