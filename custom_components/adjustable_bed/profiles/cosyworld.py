"""Cosyworld Smart Control 1.0.09, verified static direct BLE contract, hardware unverified.

Aliases are display labels only. Capabilities and PIN state belong to the live
receiver, never to its name or a sibling app's default layout.
"""

from dataclasses import dataclass
from typing import Final

from ..codec.octo import OctoPacketCodec
from ..execution import ExecutionCapabilities

SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"
ALIASES: Final = (
    "RTV",
    "RC2",
    "MC2",
    "OCTOBrick",
    "MC1",
    "OCTOHDev",
    "L2M",
    "CLI",
    "OCTOIQ",
    "OCTOBrick2",
    "RC3",
    "BMB",
    "BMS",
    "BM3",
)
LIGHT_TIMER_OPTIONS: Final = ("Always on", *(f"{v} min" for v in range(1, 61)))
TOGGLES: Final = {"light": 0x000102, "synchro": 0x000101, "remote_lock": 0x000011}
# Every app movement case, retained for vectors/docs. Unknown 4M physical labels
# do not become entities or public held controls.
MOTOR_MASKS: Final = {"M1": 2, "M2": 4, "M3": 8, "M4": 16, "M12": 6, "M34": 24}


@dataclass(frozen=True, slots=True)
class CosyworldProfile:
    key: str = "cosyworld"
    execution: ExecutionCapabilities = ExecutionCapabilities(hold="stream")
    refresh_ms: int = 350
    start_delay_ms: int = 200
    motor_release_ms: int = 200
    memory_release_ms: int = 0
    handshake_timeout_s: float = 3
    # Host bounds, not device response timing or an app semantic ACK contract.
    discovery_timeout_s: float = 5
    write_timeout_s: float = 5
    reset_disconnect_s: float = 5
    max_hold_ms: int = 60_000


PROFILE: Final = CosyworldProfile()
_CODEC = OctoPacketCodec()
HANDSHAKE_RESPONSE: Final = _CODEC._build_packet([0x21, 0x7F])
STARTUP: Final = tuple(_CODEC._build_packet([0x20, command]) for command in (0x7F, 0x70, 0x71))


def scan_name(name: str) -> bool:
    """The Android bridge removes NULs before the app's nonempty/hidden gates."""
    name = name.replace("\x00", "")
    return bool(name) and name != "OCTOHDev"
