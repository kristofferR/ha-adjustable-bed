"""Restonic's raw offset fields, without invented units or state semantics."""


class Parser:
    """Keep BOX15's retained fragment within one connection, rejecting short fields.

    The app retains a prefix after concatenation. This does too, but caps both
    prefix and assembled data and resets on disconnect. No checksum is inferred.
    """

    def __init__(self, branch: str) -> None:
        self.branch = branch
        self.pending = b""

    def feed(self, data: bytes) -> dict[str, int]:
        if not data:
            return {}
        if self.branch == "box15":
            if len(data) <= 20:
                if len(data) > 3 and data[:3] == b"\xf4\xfe\x16":
                    self.pending = data
                    return {}
                if len(data) not in (10, 16):
                    data = self.pending + data
            if len(data) > 40:
                return {}
            if len(data) > 3 and data[:2] == b"\xed\x80":
                if len(data) < 7:
                    return {}
                return {"2b": data[3], "43": data[5], "33": data[4], "3b": data[6]}
            normalize = {0: 0, 1: 1, 3: 2, 6: 3}
            if len(data) == 23:
                b, v23, a, z = data[19] & 15, data[21], data[11] & 7, data[12]
            elif len(data) == 16:
                b, v23, a, z = data[14] & 15, data[14] >> 4, data[7], data[8]
            elif len(data) == 10:
                b, v23, a, z = data[8] & 15, 1, 0, 0
            else:
                b, v23, a, z = 0, 1, 0, 0
            return {"b": b, "23": v23, "13": normalize.get(a, a), "1b": normalize.get(z, z)}
        if self.branch == "box24":
            if data[:2] == b"\xa5\x0c" and len(data) >= 8:
                return {
                    "2b": data[6],
                    "43": data[4],
                    "33": data[7],
                    "3b": 17 if data[5] == 5 else 19 if data[5] == 6 else 9,
                }
            if data[:3] == b"\xa5\x0b\x0e" and len(data) >= 9:

                def strength(value: int) -> int:
                    return value % 3 + value // 3 + (1 if value > 1 else 0)

                return {
                    "b": (data[4] & 15) // 2,
                    "23": data[6] - 1,
                    "13": strength(data[7] & 15),
                    "1b": strength(data[8]),
                }
        return {}
