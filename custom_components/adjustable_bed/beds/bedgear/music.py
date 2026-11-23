"""Mutable, session-local accessory intent for Leon's L2Motion."""

from dataclasses import dataclass, field
from math import isfinite

from ...codec.motomotion import music_command, short_transport
from ...controller_state import StateKey

VOLUME = StateKey[int | None]("l2motion_volume")
TREBLE = StateKey[int | None]("l2motion_treble")
BASS = StateKey[int | None]("l2motion_bass")
VIBRATION = StateKey[int | None]("l2motion_vibration")
MODE = StateKey[str | None]("l2motion_sound_mode")
MODES = ("custom", "vocal", "cinema", "entertainment")
CHANNELS = (VOLUME, TREBLE, BASS, VIBRATION)


@dataclass
class Music:
    volume: int = 11
    mode: str = "custom"
    maps: dict[str, list[int]] = field(
        default_factory=lambda: {
            "custom": [11, 11, 11],
            "vocal": [10, 5, 5],
            "cinema": [18, 16, 15],
            "entertainment": [15, 19, 17],
        }
    )

    def scalar(self, index: int, value: float) -> bytes:
        if not isfinite(value) or not 0 <= value <= 22 or index not in range(4):
            raise ValueError("Choose a sound level from 0 to 22")
        if self.mode != "custom" and index in (1, 2):
            raise ValueError("Treble and bass are adjustable in Custom sound mode")
        return music_command("MTBV"[index], value)

    def aggregate(self, mode: str) -> bytes:
        if mode not in MODES:
            raise ValueError("Choose an available sound mode")
        frame = b"".join(
            music_command(k, v)
            for k, v in zip("MTBV", (self.volume, *self.maps[mode]), strict=True)
        )
        result = short_transport(frame.decode("ascii"), wrapped=True)
        assert result is not None
        return result

    def commit_scalar(self, index: int, value: float) -> None:
        if index == 0:
            self.volume = int(value)
        else:
            self.maps[self.mode][index - 1] = int(value)
