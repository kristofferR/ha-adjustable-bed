"""The accepted selected receive branches, with bounded stream storage."""

from ...codec import richmat as codec

type Value = str | int | float | bool | list[int]

LITERALS = {
    bytes.fromhex("6e09010078"): "alarm_capability",
    bytes.fromhex("6e0e00037f"): "light_capability",
    bytes.fromhex("6e07010177"): "alarm_add_success",
    bytes.fromhex("6e07010278"): "alarm_cancel_success",
}


def parse(packet: bytes) -> dict[str, Value] | None:
    if packet in LITERALS:
        return {"event": LITERALS[packet]}
    if (
        len(packet) < 7
        or packet[:2] != b"\x6e\x20"
        or packet[2] != len(packet)
        or not codec.is_valid(packet)
    ):
        return None
    # The checksum cannot supply a missing payload field.
    p = packet[:-1]
    category, sub, operation = p[3:6]
    if operation not in (2, 3):
        return None
    if category == 1 and sub == 2 and len(p) > 9:
        if len(p) == 12:
            return None  # A monitoring height requires both bytes.
        return {
            "height": (p[7] * 256 + p[8]) / 10,
            "type": p[9],
            "angle": p[10] if len(p) > 10 else -1,
            "monitorHeight": (p[11] * 256 + p[12]) / 10 if len(p) > 12 else 0,
        }
    if category == 2:
        if sub == 1 and len(p) > 6 and (len(p) - 6) % 2 == 0:
            return {
                "head" if p[i] == 1 else "foot": p[i + 1]
                for i in range(6, len(p), 2)
                if p[i] in (1, 2)
            }
        if sub in (2, 4, 5, 6) and len(p) > 7:
            return {
                {2: "mode", 4: "frequency", 5: "vibrationIntensity", 6: "switch"}[sub]: p[7] == 1
                if sub == 6
                else p[7]
            }
    if category == 3 and sub == 1 and len(p) > 7:
        return {"whiteLed": p[7] == 1}
    if category == 4:
        if sub == 1 and len(p) > 9:
            return {"rgb": list(p[7:10])}
        if sub == 2 and len(p) > 8:
            return {"seconds": p[7] * 60 + p[8]}
        if sub in (3, 4) and len(p) > 7:
            return {"sensing" if sub == 3 else "rgbSwitch": p[7] == 1}
    return None


class Stream:
    """Extra frames use their total length; common frames end at the next 6E.

    Common fragmentation deliberately retains the artifact's limited behavior.
    Invalid lengths are dropped for progress instead of copying its stalled loop.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self.buffer.extend(data)
        if len(self.buffer) > 4096:
            self.buffer.clear()
            return []
        frames = []
        while len(self.buffer) >= 3:
            start = self.buffer.find(0x6E)
            if start < 0:
                self.buffer.clear()
                break
            del self.buffer[:start]
            if len(self.buffer) < 3:
                break
            if self.buffer[1] == 0x20:
                length = self.buffer[2]
                if length < 7:
                    del self.buffer[0]
                    continue
                if len(self.buffer) < length:
                    break
            else:
                length = self.buffer.find(0x6E, 1)
                if length < 0:
                    length = len(self.buffer)
            frames.append(bytes(self.buffer[:length]))
            del self.buffer[:length]
        return frames
