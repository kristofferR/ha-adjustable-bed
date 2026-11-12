"""The accepted signed/current-fragment validator, scoped to one HA session.

Android retains this accumulator across connections and dispatches ten bytes
unchecked. HA keeps the same within-session parsing, rejects stale callbacks,
and never promotes an uncorrelated alarm ACK to observed schedule state.
"""

from dataclasses import dataclass
from typing import Final

from .receive import ReceiveState

MAX_BUFFER_BYTES: Final = 64
"""HA receive budget, not a protocol frame length or inferred device limit."""


@dataclass(slots=True)
class ResourceReceiveState(ReceiveState):
    light_on_seen: bool = False
    light_off_seen: bool = False

    def feed(
        self,
        data: bytes,
        *,
        app: str,
        layout: str,
        desk_bound: bool = False,
        table_controls_bound: bool = False,
    ) -> None:
        self.value_event = None
        self.events = []
        if data.startswith(b"\x6e") and len(self.buffer) > 20:
            self.buffer = ""
        if len(self.buffer) + len(data) * 2 > MAX_BUFFER_BYTES * 2:
            self.buffer = ""
            return
        self.buffer += data.hex()
        size = len(self.buffer)
        if size == 10:
            if not data:
                return
            signed = ((sum(data[:-1]) + 128) & 255) - 128
            if signed != data[-1]:
                return
        elif size != 20:
            return
        packet, self.buffer = self.buffer, ""
        self.last_value = self.value_event = packet
        self.events.append({"value": packet})
        if packet == "6e09010078":
            self.alarm_capable = True
        elif packet == "6e0e00037f":
            self.light_capable = self.light_on_seen = True
        elif packet == "6e0e00017d":
            self.light_capable = self.light_off_seen = True
        # No usable accessory capability or bed-position parser is established.
        # Settings visibility is independent of layout alarm ownership.
        if self.alarm_capable and "alarm" not in self.menu:
            self.menu.add("alarm")
        elif self.light_capable and "light" not in self.menu:
            self.menu.add("light")
