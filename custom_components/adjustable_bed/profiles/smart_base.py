"""Smart Base 1.3.1, selected 200IV2 / A8RM P1 route only.

Accepted frozen report: com.richmat.smartbase-1.3.1-2026-11-27-queueA139-inputs01.
Motor numbers do not establish physical geometry or a side selector.
"""

from typing import Final

from ..codec import richmat as codec
from ..execution import STREAM_HOLD
from .richmat import RichmatProfile

PRODUCT: Final = "200iv2_a8rm"
NAME: Final = "200IV2"
SERVICE: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
TX: Final = "d44bc439-abfd-45a2-b575-925416129600"
RX: Final = "d44bc439-abfd-45a2-b575-925416129601"
TICK_MS: Final = 150
HELD_RELEASE_MS: Final = 50
TAP_RELEASE_MS: Final = 150
SAVE_MS: Final = 3000
STARTUP_MS: Final = 300
QUERY_MS: Final = 500
ALARM_MS: Final = 300
PROFILE: Final = RichmatProfile(
    key="smart_base",
    execution=STREAM_HOLD,
    transports=("w1",),
    codes={"flat": 0x31, "zero_g": 0x45, "save_zero_g": 0x66, "light_toggle": 0x3C},
    stop=0x6E,
    motor_repeat_ms=TICK_MS,
)
MOTORS: Final = ((0x24, 0x25), (0x26, 0x27))
INITIALIZE: Final = codec.frame(0x6E, 2, 1, 0)
QUERIES: Final = (codec.frame(0x6E, 0x0A, 0, 1), codec.frame(0x6E, 0x1A, 0, 0))
# Only whole, exact five-byte notifications have accepted parser evidence.
FLAGS: Final = {
    codec.frame(0x6E, 9, 1, 0): "alarm",
    codec.frame(0x6E, 0x0E, 0, 3): "led_on",
    codec.frame(0x6E, 0x0E, 0, 1): "led_off",
    codec.frame(0x6E, 0x1A, 0, 1): "aroma",
}
