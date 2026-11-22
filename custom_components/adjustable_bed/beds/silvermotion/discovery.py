"""SILVERmotion Android's manufacturer-only scan acceptance."""

from collections.abc import Mapping

from ...codec.silvermotion import MANUFACTURER


def scan_matches(data: Mapping[int, bytes], *, bonded: bool = False) -> bool:
    # Android SparseArray.keyAt(0) is the smallest company ID, not insertion order.
    if not data or min(data) != MANUFACTURER:
        return False
    payload = data[MANUFACTURER]
    if len(payload) == 7:
        return True
    return (
        len(payload) == 11
        and payload[7:9] in (b"LL", b"NS", b"FS")
        and (payload[9] == 0 or payload[9] == 1 and bonded)
    )
