"""King Koil's accumulated response and current-notification parser branches."""

from ..truemotion.receive import MAX_BUFFER, Observations
from ..truemotion.receive import Receiver as TextReceiver


class Receiver(TextReceiver):
    def __init__(self, observations: Observations) -> None:
        super().__init__(observations)
        self.raw: str | None = None
        self.alarms: dict[str, str] = {}
        self.collecting = False

    def feed(self, data: bytes) -> str | None:
        try:
            chunk = data.decode("utf-8")
        except UnicodeDecodeError:
            self.pending = ""
            return None
        self.pending += chunk
        version = None
        if len(self.pending) > MAX_BUFFER:
            self.pending = ""
        if self.pending.endswith("\r\n"):
            if self.pending.startswith("+OK:Version="):
                version = self.observations.version = self.pending[12:]
            else:
                self.raw = self.pending
            self.pending = ""
        if chunk.startswith("+OK:GD=") and len(chunk) >= 9:
            self.observations.gd = chunk[7:-2]
        elif chunk.startswith("+OK:GA=") and self.collecting and len(chunk) >= 9:
            body = chunk[7:-2]
            if len(body) == 10 and body[8:10] != "02":
                key, day = body[2:], body[1]
                old = self.alarms.get(key, "")
                if day not in old.split(",") and len(self.alarms) < MAX_BUFFER:
                    self.alarms[key] = old + day + ","
        return version
