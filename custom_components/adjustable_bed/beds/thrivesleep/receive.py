"""Bounded current-product replies. Unclosed other-flavor parsers stay unsupported."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ...codec import richmat as codec
from ...profiles.thrivesleep import RESIDUAL_EXPIRY_S


def decode(b: bytes) -> dict[str, object]:
    if not codec.is_valid(b):
        return {}
    if b == bytes.fromhex("6e09010078"):
        return {"clock": True}
    if b == bytes.fromhex("6e0e00037f"):
        return {"light": True}
    if len(b) == 5 and b[:2] == b"\x6e\x90":
        high, low, value = b[2] >> 4, b[2] & 15, b[3]
        if high == 0:
            return {"protocolVersion": value, **({"bedMode": 1} if low == 1 else {})}
        if high == 3:
            return {"no": b[2] >> 2 & 3, "status": b[2] & 3, "angle": value}
        if high == 10:
            bits = low << 8 | value
            return dict(
                zip(
                    ("mode", "massage1", "massage2", "massage3"),
                    (bits >> shift & 7 for shift in (9, 6, 3, 0)),
                    strict=True,
                )
            )
    if len(b) < 8 or b[:2] != b"\x6e\x20" or b[2] != len(b) or b[5] not in (2, 3):
        return {}
    if b[3:5] == b"\x01\x02" and len(b) > 9:
        return {"firstTravel": int.from_bytes(b[7:9], "big") / 10}
    if b[3:5] == b"\x05\x01" and len(b) == 13:
        return dict(
            zip(("id", "reserved", "hour", "minute", "mode", "repeatCode"), b[6:12], strict=True)
        )
    if b[3:5] == b"\x06\x01" and len(b) > 8:
        return {"antiSnore": b[7] == 1}
    if b[3:5] == b"\x06\x03":
        return {"sleepAdvName": b[7:-1].decode("ascii", errors="replace")}
    if b[3:5] == b"\x0e\x01" and len(b) > 8:
        return {"fanGear": b[7]}
    return {}


@dataclass
class Receiver:
    pending: bytearray = field(default_factory=bytearray)
    expiry: asyncio.TimerHandle | None = None

    def close(self) -> None:
        if self.expiry is not None:
            self.expiry.cancel()
            self.expiry = None
        self.pending.clear()

    def feed(self, chunk: bytes) -> list[bytes]:
        if self.expiry is not None:
            if self.expiry.when() <= asyncio.get_running_loop().time():
                self.pending.clear()
            self.expiry.cancel()
        self.pending.extend(chunk)
        if len(self.pending) > 4096:
            self.close()
            return []
        result = []
        while self.pending:
            if self.pending[0] != 0x6E:
                del self.pending[0]
                continue
            if len(self.pending) < 3:
                break
            size = self.pending[2] if self.pending[1] == 0x20 else 5
            if size < 5:
                del self.pending[0]
                continue
            if len(self.pending) < size:
                break
            frame = bytes(self.pending[:size])
            del self.pending[:size]
            if codec.is_valid(frame):
                result.append(frame)
        self.expiry = asyncio.get_running_loop().call_later(RESIDUAL_EXPIRY_S, self.pending.clear)
        return result
