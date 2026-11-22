"""Instant Comfort's channel parser over the Personal Comfort air wire format."""

from dataclasses import dataclass

from .personal_comfort import AirReply


def channel_target(channel: int, target: float) -> bytes:
    if channel not in range(4):
        raise ValueError("Pressure channel must be 0 through 3")
    pressure = int(66 * (min(50, max(5, target)) - 5) / 45)
    return f"C>SETP>{channel}>{pressure}\n".encode("ascii")


@dataclass(frozen=True)
class PressureReply:
    status: int
    channels: tuple[int, ...]

    @property
    def main(self) -> AirReply:
        return AirReply(
            self.status, self.channels[0], self.channels[2 if len(self.channels) == 4 else 1]
        )


def parse_pressure(packet: bytes) -> PressureReply | None:
    if not packet.startswith((b"RET>SP>", b"RBD>SP>")):
        return None
    count = 4 if packet.startswith(b"RBD>SP>") or len(packet) >= 29 else 2
    if len(packet) < 13 + 2 * count:
        return None
    try:
        status = int(packet[9:11], 16)
        channels = tuple(
            int(5 + 45 * min(66, max(0, int(packet[offset : offset + 2], 16))) / 66)
            for offset in range(13, 13 + 2 * count, 2)
        )
    except ValueError:
        return None
    return PressureReply(status, channels)
