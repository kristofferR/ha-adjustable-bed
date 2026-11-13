"""Normal Yamada alarm responses, with deliberate HA input safety.

The Android manager recognizes both prefix families before selecting the current
version's callback. Its P1 precheck can throw or commit partial state. R1 in the
frozen report/helper remains deferred; rejecting short/wrong-profile frames here
is integration safety, not a claim that Android has those guards.
"""

from ...profiles.yamada import Alarm


class AlarmParser:
    """One notification role's bounded, session-owned two-chunk buffer."""

    def __init__(self, p1: bool) -> None:
        self.p1 = p1
        self.pending = b""

    def feed(self, data: bytes, previous: dict[int, Alarm]) -> dict[int, Alarm]:
        if len(data) < 3:
            return {}
        assembled, self.pending = self.pending + data, b""
        if len(data) == 20 and data[1:3] == b"\xfe\x16":
            self.pending = data
            return {}
        if self.p1 and assembled[:3] == b"\xed\x80\x03" and len(assembled) >= 11:
            raw = {1: (*assembled[3:7], assembled[5]), 2: (*assembled[7:11], assembled[9])}
        elif (
            not self.p1
            and len(assembled) >= 10
            and assembled[:3] in (b"\xa5\x0c\x0e", b"\xa5\x0d\x0e")
        ):
            raw = {
                assembled[1] - 11: (
                    assembled[6],
                    assembled[7],
                    assembled[4],
                    assembled[5],
                    assembled[9],
                )
            }
        else:
            return {}  # E7 and A5 0E have no consumed hardware state.
        updates: dict[int, Alarm] = {}
        for slot, (hour, minute, week, position, marker) in raw.items():
            if hour > 23 or minute > 59:
                return {}  # Atomic safety rejection, rather than Android partial commits.
            enabled = marker not in (0, 128)
            old = previous.get(slot)
            updates[slot] = Alarm(
                hour,
                minute,
                week if enabled else old.weekday if old else None,
                position,
                enabled,
            )
        return updates
