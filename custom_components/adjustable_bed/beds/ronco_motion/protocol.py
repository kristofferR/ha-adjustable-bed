"""App-specific notification semantics over the shared Richmat codec."""

from datetime import time


def alarm_minutes(now: time, chosen: time) -> int:
    """Equal times mean tomorrow; seconds are ignored by the app."""
    return ((chosen.hour * 60 + chosen.minute - now.hour * 60 - now.minute) % 1440) or 1440


def parse_notification(data: bytes) -> list[dict[str, int | str]]:
    """One callback, with no checksum gate or cross-callback reassembly."""
    if data == bytes.fromhex("6e07010177"):
        return [{"alarm": "added"}]
    if data == bytes.fromhex("6e07010278"):
        return [{"alarm": "deleted"}]
    if len(data) < 3 or data[:2] != b"\x6e\x90" or data[2] >> 4 not in (0xB, 0xD):
        return []
    result: list[dict[str, int | str]] = []
    for offset in range(0, len(data) - 4, 5):
        chunk = data[offset : offset + 5]
        kind, field, value = chunk[2] >> 4, chunk[2] & 15, chunk[3]
        if kind == 0xB:
            result.append(
                {
                    "music_switch": field & 1,
                    "music_play_pause": value >> 7 & 1,
                    "music_mode_on_off": value >> 6 & 1,
                    "music_on_off": value >> 5 & 1,
                }
            )
        elif kind == 0xD and field in (1, 2):
            result.append(
                {
                    "music_volume" if field == 1 else "music_intensity": value
                    if value < 128
                    else value - 256
                }
            )
    return result
