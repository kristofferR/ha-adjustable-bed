"""Hush shared notification extensions from accepted s01 receive contracts."""

from __future__ import annotations

import time

from .casper_base_protocol import Event, MainReceive, decode_main
from .codec.richmat import is_valid, is_valid_crc


class HushMainReceive(MainReceive):
    """Support both extended lengths; bound malformed input and stale tails."""

    def __init__(self) -> None:
        super().__init__()
        self._last = 0.0

    def feed(self, chunk: bytes) -> list[bytes]:
        now = time.monotonic()
        if now - self._last >= 0.5:
            self.pending.clear()
        self._last = now
        self.pending.extend(chunk)
        out: list[bytes] = []
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            kind = self.pending[1]
            if kind in (0x20, 0x21, 0x40):
                if kind == 0x40 and len(self.pending) < 4:
                    break
                size = (self.pending[2] << 8) | self.pending[3] if kind == 0x40 else self.pending[2]
                if size < (9 if kind == 0x40 else 7):
                    self.pending.clear()
                    raise ValueError("Invalid extended notification length")
                if len(self.pending) < size:
                    break
                packet = bytes(self.pending[:size])
                del self.pending[:size]
                if (is_valid_crc if kind == 0x40 else is_valid)(packet):
                    out.append(packet)
            else:
                # Retain complete ordinary frames, including marker-valued data.
                size = len(self.pending)
                if size not in (5, 7, 16):
                    size = next(
                        (
                            n
                            for n in (5, 7, 16)
                            if len(self.pending) > n and self.pending[n] == 0x6E
                        ),
                        0,
                    )
                    if not size:
                        if len(self.pending) < 16:
                            break
                        self.pending.clear()
                        raise ValueError("Unsupported ordinary frame boundary")
                packet = bytes(self.pending[:size])
                del self.pending[:size]
                # Leave subsequent frames to this loop's Hush length handling.
                out.append(packet)
        return out


def decode(b: bytes) -> Event | None:
    """Preserve bed state for every direct parser branch, with raw axes."""
    if len(b) < 5:
        return None
    if b.hex() == "6e2100008f":
        # Direct-handler literal only; the stream rejects its zero length.
        return Event("snore_available", {})
    if b[1] == 0x21:
        if len(b) > 9 and b[3:6] in (b"\x0f\x01\x02", b"\x0f\x01\x03"):
            return Event("motor_extra", {"height": int.from_bytes(b[6:8], "big") / 10, "type": 2})
        return None
    if b[1] == 0x40:
        # OTA is excluded, but keep the common validated transport observation.
        return Event("firmware_transport", {"raw": b.hex()})
    exact = {
        "6e23018416": "remote_locked",
        "6e23008415": "remote_unlocked",
        "6e23a06e9f": "configuration_available",
    }
    if name := exact.get(b.hex()):
        return Event(name, {})
    event = decode_main(b)
    if b[1] != 0x20 or len(b) < 7:
        return event
    category, sub, op = b[3:6]
    if event and event.name == "motor_extra" and len(b) > 13:
        event.values["monitor_height"] = int.from_bytes(b[11:13], "big") / 10
    if op not in (2, 3):
        return event
    if category == 1 and sub == 3 and len(b) > 8:
        return Event("motor_angle", {"position": b[6], "angle": b[8]})
    if category == 6:
        if sub == 4 and len(b) > 8 and b[7] == b[8] == 1:
            return Event("configuration_available", {})
        if sub == 5 and len(b) > 8 and b[7] in (1, 2):
            return Event("snore_count" if b[7] == 1 else "snore_time", {"value": b[8]})
    if category == 7 and sub == 2 and len(b) > 7:
        return Event("remote_locked" if b[7] == 1 else "remote_unlocked", {})
    if category == 9 and len(b) > 7:
        if sub == 2 and b[6] in (2, 3):
            return Event("music_volume" if b[6] == 2 else "music_shake", {"value": b[7]})
        if sub == 4:
            return Event("music_usb", {"value": b[7] == 1})
    if category == 11 and sub == 4 and len(b) > 7:
        return Event("press_mode_extra", {"value": b[7]})
    if category == 13:
        guard = {1: 7, 2: 9, 5: 9, 6: 7, 7: 20, 8: 7, 9: 11}.get(sub)
        if guard is not None and len(b) > guard:
            return Event("blanket_" + str(sub), {})
    if category == 14 and sub == 1 and len(b) > 7:
        return Event("fan", {"value": b[7]})
    if category == 15 and event is not None:
        event.values["unit"] = "inch" if b[6] & 1 else "cm"
        if len(b) >= 27:
            event.values["monitor_inch"] = (100 * b[22] + b[23]) / 10
            event.values["monitor_cm"] = (100 * b[24] + b[25]) / 10
    if category == 16:
        if sub == 1 and len(b) > 7:
            return Event("atomization", {"value": b[7]})
        if sub == 2 and len(b) > 8:
            return Event("atomization_extra", {"value": b[8]})
    if category == 17:
        if sub == 2 and len(b) > 8:
            duration = int.from_bytes(b[7:9], "big")
            return Event(
                "heating_time",
                {
                    "position": b[6],
                    "type": 1 if duration == 65535 else 2,
                    "time": 0 if duration == 65535 else duration,
                },
            )
        if sub == 3 and len(b) > 8:
            return Event("heating_temperature", {"position": b[6], "value": b[8]})
        if sub == 5:
            return Event("heating_mode", {"value": b[6]})
    return event
