"""Linx 1.0.7 (com.keeson.connectedbed): Quest and Orbes models over independent BLE routes.

Model and BLE route are independent. No offline alarm catalog was supplied.
These static controls and defaults come from this app alone.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import linx as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class LinxProfile:
    key: str
    label: str
    massage: bool
    individual_binary_release: bool
    unknown_mode_km: int
    consumes_mode: bool
    refresh_ms: int = 3
    execution: ExecutionCapabilities = STREAM_HOLD


PROFILES: Final = {
    "quest": LinxProfile("quest", "Linx 2.5 Q (model 9)", True, False, 6, True),
    "orbes": LinxProfile(
        "orbes", "Orbes BR 40+ Slim Q VAVE Linx (model 10)", False, True, 10, False
    ),
}


@dataclass(frozen=True, slots=True)
class Route:
    event_transport: str
    snore_uart: bool
    label: str


# FastBleService.isHasWifi routes generic buffers. SnoreService independently
# reads the stored bean to choose JSON or a direct UART write (E07/E16).
ROUTES: Final = {
    "a00a": Route("a00a", False, "A00A / B002 BLE; JSON intervention (current app default)"),
    "uart": Route("uart", True, "Nordic UART BLE; binary UART intervention (restored)"),
    "uart_json": Route(
        "uart", False, "Nordic UART BLE; unchanged JSON intervention (mixed restored state)"
    ),
    "a00a_uart": Route(
        "a00a", True, "A00A / B002 BLE; direct binary UART intervention (mixed restored state)"
    ),
}
TRANSPORT_CHOICES: Final = {key: route.label for key, route in ROUTES.items()}
AXES: Final = {"head": (1, 2), "feet": (4, 8), "both": (5, 10)}
PRESETS: Final = {"flat": 0x08000000, "zero_g": 0x1000}
MEMORY: Final = {1: 0x8000, 2: 0x10000, 3: 0x2000, 4: 0x4000}
LIGHT: Final = 0x20000
MASSAGE: Final = {"head": 0x800, "foot": 0x400, "timer": 0x200, "mode": 0x04000000}
SNORE_DEFAULT: Final = 10
WRITE_CHUNK_SIZE: Final = 243
CONNECT_SETTLE_MS: Final = 300
DIAGNOSTIC_TIMEOUT: Final = 60


def release(profile: LinxProfile, device: str, axis: str = "both") -> bytes:
    return (
        codec.instruction(0)
        if profile.individual_binary_release and axis != "both"
        else codec.control(device, 0)
    )
