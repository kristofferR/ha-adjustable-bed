"""Luuna's shared decoders, without promoting unconsumed events to capabilities."""

from ...codec import richmat as codec
from ..casper_base.protocol import Event, decode_main


def decode(packet: bytes) -> Event | None:
    """Keep Luuna's field meanings, unsigned offsets and weak motor length guards."""
    b = packet
    if len(b) < 5:
        return None
    if b[1] != 0x20:
        if len(b) == 16 and b[1] != 0x10:
            return None
        event = decode_main(b)
        if event and event.name == "detection_details":
            return Event("detection_details", {})  # Empty object in this artifact.
        return event
    if len(b) < 7 or len(b) != b[2] or not codec.is_valid(b):
        return None
    domain, sub, mode = b[3:6]
    if mode in (2, 3):
        if domain == 11 and sub in (1, 2, 4) and len(b) > 7:
            return Event(
                {1: "press_mode", 2: "same_control", 4: "same_split_control"}[sub],
                {"value": b[7] == 2 if sub == 2 else b[7]},
            )
        if domain == 13:
            guard = {1: 7, 2: 9, 5: 9, 6: 7, 7: 20, 8: 7, 9: 11}.get(sub)
            if guard is not None and len(b) > guard:
                return Event(f"blanket_{sub}", {})  # Empty payload classes, no app listeners.
    event = decode_main(b)
    if event and event.name == "motor_extra":
        event.values["monitor_height"] = int.from_bytes(b[11:13], "big") / 10 if len(b) > 13 else 0
    elif event and event.name == "desk_extra":
        event.values.update(long_press=bool(b[6] & 16), reset=bool(b[6] & 8))
        event.values.update(
            monitor_inch=(100 * b[22] + b[23]) / 10 if len(b) >= 27 else 0,
            monitor_cm=(100 * b[24] + b[25]) / 10 if len(b) >= 27 else 0,
        )
    return event
