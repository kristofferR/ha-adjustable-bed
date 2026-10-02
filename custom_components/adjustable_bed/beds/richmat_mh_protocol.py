"""Wire format and notification classifier of the Richmat MH apps.

Revive Control, Best Mattress, Blvd Home, HARMONY and Idealbed share one
Java/Kotlin BLE library (accepted APK audit row055, cluster-020). The packet
builders, framing and checksums are identical across the five apps; the
notification classifier differs in two places, recorded per app group.

Every bed frame is ``6e 01 M C SUM``: ``M`` is the app's ``txMode`` byte (0 in
the app's single-device group, the only group a Home Assistant entry has) and
``SUM`` is the low byte of the sum of the preceding bytes. Mattress frames use
the ``5e`` header with the same additive checksum and no mode byte.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Final, Literal

HEADER_BED: Final = 0x6E
HEADER_MATTRESS: Final = 0x5E
STOP_CODE: Final = 0x6E

# Ordered known services (N1, W1, W2, W3, W4) with their write and notify roles.
GATT_MAPS: Final = (
    ("6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
     "6e400003-b5a3-f393-e0a9-e50e24dcca9e"),
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600",
     "d44bc439-abfd-45a2-b575-925416129601"),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622",
     "d44bc439-abfd-45a2-b575-925416129611"),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe2-0000-1000-8000-00805f9b34fb",
     "0000ffe1-0000-1000-8000-00805f9b34fb"),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb",
     "0000fff1-0000-1000-8000-00805f9b34fb"),
)
# The fallback skips the generic access and attribute services.
FALLBACK_SKIPPED_PREFIXES: Final = ("00001800", "00001801")

# Connection setup: version query 300 ms after the link, init 300 ms later,
# each init task followed by a 300 ms sleep.
INIT_DELAY_S: Final = 0.3
INIT_TASK_SLEEP_S: Final = 0.3
STOP_DELAY_S: Final = 0.12  # STOP 120 ms after a release or a ONCE send.

TX_VERSION: Final = "6e9a000008"
TX_EXIT_ONE_MIN: Final = "6e02010071"
TX_ALARM: Final = "6e08010178"
TX_LED: Final = "6e0a000179"
TX_AROMA: Final = "6e1a000088"
TX_MATTRESS: Final = "5e1a000190"  # Literal; the sender recomputes the sum to 79.
TX_WAIST_MATTRESS: Final = "5e1b00017a"
TX_SNORE: Final = "6e2100008f"
TX_SPEECH: Final = "6e22000090"
TX_DETECTION: Final = "6e9ac000c8"
TX_MOTOR_MODE: Final = "6e9a100018"
TX_MOTOR_ANGLES: Final = ("6e9a300139", "6e9a30023a", "6e9a30033b", "6e9a30043c")
TX_QUERY_MASSAGE: Final = "6e9aa000a8"
TX_QUERY_UBL_LOCK: Final = "6e9ab000b8"
TX_ALARM_CANCEL: Final = ("6e05000073", "6e06000074")
TX_START_DETECTION: Final = "6e88c21000"
TX_STOP_DETECTION: Final = "6e88c22000"

INIT_VER0: Final = (TX_EXIT_ONE_MIN, TX_ALARM, TX_LED, TX_AROMA, TX_MATTRESS, TX_WAIST_MATTRESS,
                    TX_SNORE, TX_SPEECH, TX_DETECTION)
INIT_VER1: Final = (TX_EXIT_ONE_MIN, TX_ALARM, TX_LED, TX_AROMA, TX_MATTRESS, TX_WAIST_MATTRESS,
                    TX_SNORE, TX_SPEECH, TX_MOTOR_MODE, *TX_MOTOR_ANGLES, TX_QUERY_MASSAGE,
                    TX_QUERY_UBL_LOCK)

RX_VERSION1: Final = "6e900001ff"
RX_ALARM: Final = "6e09010078"
RX_ALARM_MULTI: Final = "6e09010179"
RX_LED: Final = "6e0e00037f"
RX_AROMA: Final = "6e1a000189"
RX_STOP_MUSIC: Final = "6e23a06e9f"
RX_DETECTION: Final = "6e90c101c0"
RX_START_DETECTION: Final = "6e90c210d0"
RX_STOP_DETECTION: Final = "6e90c220e0"
RX_HEAD_DETECTION: Final = "6e90c"
RX_HEAD_MOTOR_MODE: Final = "6e901"
RX_HEAD_MOTOR_ANGLE: Final = "6e903"
RX_HEAD_MASSAGE: Final = "6e90a"
RX_HEAD_UBL_LOCK: Final = "6e90a"  # Shadowed by the identical massage prefix.
RX_HEAD_MEMORY_ARRIVAL: Final = "6e904"
RX_HEAD_ERROR: Final = "6e905"
RX_SNORE_PREFIX: Final = "6e21"  # EPack.SNORE head + function
RX_CALLBACK_PREFIX: Final = "6e23"  # EPack.CALLBACK: 6e 23 value function SUM
RX_ALARM_SET_SUCCESS: Final = "6e07010177"
RX_ALARM_DEL_SUCCESS: Final = "6e07010278"
CALLBACK_LOCKED: Final = "00"  # ELock.LOCK
CALLBACK_UNLOCKED: Final = "01"  # ELock.UNLOCK
CALLBACK_FUNCTION_LOCK: Final = "84"  # CmdKey.LOCK, the smart set lock
CALLBACK_FUNCTION_SNORE: Final = "21"  # EPack.SNORE function
DATA_TABLE_LEN: Final = 32
BUFFER_RESET_LEN: Final = 100

# Fixed opcodes the app writes outside the per-model catalog.
BTN_LED_OFF_CODE: Final = 0x75  # Button-light page OFF (k_ubl_off, press_once)
SMART_SET_LOCK_CODE: Final = 0x84  # Motor-page smart set lock switch (CmdKey.LOCK)
# Button-light page colour wheel (SweepView sectors); Best Mattress and Idealbed lack white.
BTN_LED_PALETTE: Final = ((0xFF, 0x00, 0x00), (0xFE, 0x99, 0x02), (0xFF, 0xFF, 0x00), (0x00, 0xFF, 0x00),
                          (0x02, 0xD4, 0xFE), (0x0D, 0x00, 0xFF), (0xB2, 0x00, 0xB5))
BTN_LED_WHITE: Final = (0xFF, 0xFF, 0xFF)
AROMA_FUNCTIONS: Final = (0x1B, 0x1C, 0x1D)  # mode2 startup, mode3 startup, mode3 pause
AROMA_TASK_SLEEP_S: Final = 0.15
ALARM_TASK_SLEEP_S: Final = 0.3  # AlarmFrag/AlarmCallFrag task list spacing
MULTI_ALARM_SLEEP_S: Final = 0.15  # AlarmCallDialogFrag save/delete spacing
ANGLE_SEND_DELAY_S: Final = 0.1  # MotorCallFrag sleeps 100 ms after the slider release
# Multi-slot alarm rows (F7irm isNewAlarm): slot -> M1/M2/M3 recall opcode.
MULTI_ALARM_SLOTS: Final = {1: 0x2E, 2: 0x2F, 3: 0x30}
# Alarm massage choices (AlarmMsgFragAdapter filter) and their combined opcodes.
MSG_HEAD: Final = 0x4C
MSG_FOOT: Final = 0x4E
MSG_HEAD_FOOT_BOTH_ON: Final = 0x5D
MSG_HEAD_FOOT_INTENSITY_INC: Final = 0x34
ALARM_MASSAGE_CODES: Final = (MSG_HEAD, MSG_FOOT, MSG_HEAD_FOOT_BOTH_ON, MSG_HEAD_FOOT_INTENSITY_INC)
# combineCmd: (memory, massage) -> resource opcode (tv_head_on ... m3_all_on).
ALARM_COMBINATIONS: Final = {
    (0x58, MSG_HEAD): 0x7A, (0x58, MSG_FOOT): 0x7D, (0x58, MSG_HEAD_FOOT_BOTH_ON): 0x77,
    (0x45, MSG_HEAD): 0x7C, (0x45, MSG_FOOT): 0x7F, (0x45, MSG_HEAD_FOOT_BOTH_ON): 0x79,
    (0x46, MSG_HEAD): 0x7B, (0x46, MSG_FOOT): 0x7E, (0x46, MSG_HEAD_FOOT_BOTH_ON): 0x78,
    (0x59, MSG_HEAD): 0xAD, (0x59, MSG_FOOT): 0xAE, (0x59, MSG_HEAD_FOOT_BOTH_ON): 0xAC,
    (0x2E, MSG_HEAD): 0x82, (0x2E, MSG_FOOT): 0x83, (0x2E, MSG_HEAD_FOOT_BOTH_ON): 0x81,
    (0x2F, MSG_HEAD): 0xA7, (0x2F, MSG_FOOT): 0xA8, (0x2F, MSG_HEAD_FOOT_BOTH_ON): 0xA6,
    (0x30, MSG_HEAD): 0xAA, (0x30, MSG_FOOT): 0xAB, (0x30, MSG_HEAD_FOOT_BOTH_ON): 0xA9,
}
# Detection results: device type digit -> app label stem.
DETECTION_DEVICE_TYPES: Final = {"3": "motor", "4": "massager", "5": "ubl", "6": "usb"}
DETECTION_STATUS: Final = {"0": "error", "1": "pass", "2": "control_box_error", "3": "unplugged"}

# Waist mattress page (5e 03 cmd value SUM). Per side: (heat, pressure,
# duration, alarm-cancel, ESideMattress) codes; values are option indexes.
WAIST: Final = 0x03
WAIST_MODE: Final = 0x01
WAIST_ALARM: Final = 0x0B
WAIST_SIDES: Final = {
    "left": (0x02, 0x05, 0x08, 0x10, 0x01),
    "right": (0x03, 0x06, 0x09, 0x11, 0x02),
    "both": (0x04, 0x07, 0x0A, 0x12, 0x03),
}
WAIST_MODES: Final = (
    "off", "left_relax", "left_wake", "left_decompress", "right_relax", "right_wake",
    "right_decompress", "both_relax", "both_wake", "both_decompress",
)
# Dialog choices -> value. The pressure and duration dialogs offer no "off".
WAIST_HEAT: Final = {"off": 0, "2_hours": 1, "4_hours": 2, "8_hours": 3}
WAIST_PRESSURE: Final = {"level_1": 1, "level_2": 2, "level_3": 3}
WAIST_DURATION: Final = {"15_minutes": 1, "20_minutes": 2, "30_minutes": 3}
WAIST_ALARM_REPEAT: Final = {"once": 0x01, "daily": 0x02}

# Motor-mode buttons (VER1 page): selector bits written in 6e 88 (10|bits<<2).
MOTOR_MODE_BITS: Final = {"LEFT": 1, "RIGHT": 2, "Mode1": 1, "Mode2": 2, "Mode3": 3}

AppGroup = Literal["revive", "legacy"]  # notification-callback families


def checksum(data: Iterable[int]) -> int:
    """Low byte of the signed-byte sum, which equals the unsigned sum mod 256."""
    return sum(data) & 0xFF


def finalize(template: bytes | bytearray | list[int]) -> bytes:
    """``getFinalBytes``: zero the last byte, then store the sum of the frame."""
    out = bytearray(template)
    out[-1] = 0
    out[-1] = checksum(out)
    return bytes(out)


def control_frame(code: int, mode: int = 0) -> bytes:
    """``6e 01 M C SUM``, the frame every motor, preset and page button sends."""
    return finalize([HEADER_BED, 0x01, mode & 0xFF, code & 0xFF, 0])


def stop_frame(mode: int = 0) -> bytes:
    """``TX_END`` with the mode sampled when it is sent."""
    return control_frame(STOP_CODE, mode)


def query_frame(hex_text: str) -> bytes:
    """``sendHexData``: decode the literal, then recompute its sum (no mode)."""
    return finalize(bytes.fromhex(hex_text))


def angle_frame(motor_bits: int, angle: int) -> bytes:
    """Absolute motor target: ``6e 88 (30|bits<<2) |angle| SUM``."""
    return finalize([HEADER_BED, 0x88, 0x30 | ((motor_bits & 3) << 2), abs(int(angle)) & 0xFF, 0])


def massage_intensity_frame(head: int, foot: int) -> bytes:
    """Both zones at once: ``6e 88 a0 ((foot&7)<<3 | head&7) SUM``."""
    return finalize([HEADER_BED, 0x88, 0xA0, ((foot & 7) << 3) | (head & 7), 0])


def motor_mode_frame(bits: int) -> bytes:
    """VER1 motor-mode button: ``6e 88 (10|bits<<2) 00 SUM``."""
    return finalize([HEADER_BED, 0x88, 0x10 | ((bits & 3) << 2), 0x00, 0])


def rgb_frame(red: int, green: int, blue: int) -> bytes:
    """One 10-byte write: ``6e 0c ff R s1 6e 0d G B s2``."""
    for value in (red, green, blue):
        if not 0 <= value <= 255:
            raise ValueError("RGB values must be 0-255")
    return finalize([HEADER_BED, 0x0C, 0xFF, red, 0]) + finalize([HEADER_BED, 0x0D, green, blue, 0])


def light_timer_frame(seconds: int, mode_byte: int | None = None) -> bytes:
    """``6e 0b HH LL SUM``; zero or less means always on (``ff ff``).

    ``mode_byte`` reproduces the entity-page variant that routes the frame
    through the mode-rewriting sender, which replaces ``HH`` with ``txMode``.
    """
    hi, lo = (0xFF, 0xFF) if seconds <= 0 else ((seconds >> 8) & 0xFF, seconds & 0xFF)
    if mode_byte is not None:
        hi = mode_byte & 0xFF
    return finalize([HEADER_BED, 0x0B, hi, lo, 0])


def alarm_frames(minutes: int, action: int, slot: int = 0) -> tuple[bytes, bytes]:
    """Countdown alarm: ``6e 05 lo slot`` then ``6e 06 hi action``."""
    return (
        finalize([HEADER_BED, 0x05, minutes & 0xFF, slot & 0xFF, 0]),
        finalize([HEADER_BED, 0x06, (minutes >> 8) & 0xFF, action & 0xFF, 0]),
    )


def alarm_delete_frames(slot: int) -> tuple[bytes, bytes]:
    """Multi-slot alarm delete: ``6e 05 00 slot`` then ``6e 06 00 00``."""
    return (
        finalize([HEADER_BED, 0x05, 0x00, slot & 0xFF, 0]),
        finalize([HEADER_BED, 0x06, 0x00, 0x00, 0]),
    )


def clock_frames(hour: int, minute: int, second: int) -> tuple[bytes, bytes]:
    """Multi-slot alarm clock: ``6e 13 H M`` and ``6e 14 S ff``."""
    return (
        finalize([HEADER_BED, 0x13, hour & 0xFF, minute & 0xFF, 0]),
        finalize([HEADER_BED, 0x14, second & 0xFF, 0xFF, 0]),
    )


def snore_frame(code: int, mode: int = 0) -> bytes:
    """Snore intervention selection: ``6e 13 M code SUM`` (code 0 turns it off)."""
    return finalize([HEADER_BED, 0x13, mode & 0xFF, code & 0xFF, 0])


def aroma_frame(function: int, value: int) -> bytes:
    """Aroma timing: ``6e fn (b0+b1) (b2+b3) SUM`` over the int32 LE bytes."""
    b = int(value).to_bytes(4, "little", signed=True)
    return finalize([HEADER_BED, function & 0xFF, (b[0] + b[1]) & 0xFF, (b[2] + b[3]) & 0xFF, 0])


def mattress_frame(*body: int) -> bytes:
    """``5e ... SUM`` mattress/waist frame, no mode byte."""
    return finalize([HEADER_MATTRESS, *body, 0])


def waist_frame(command: int, value: int) -> bytes:
    """Waist page control: ``5e 03 cmd value SUM``."""
    return mattress_frame(WAIST, command & 0xFF, value & 0xFF)


def waist_alarm_frame(
    repeat: int, side: int, intensity: int, hour: int, minute: int, now_hour: int, now_minute: int
) -> bytes:
    """Waist alarm save: ``5e 03 0b repeat side intensity H M nowH nowM SUM``."""
    return mattress_frame(WAIST, WAIST_ALARM, repeat, side, intensity, hour, minute, now_hour, now_minute)


WaistAlarm = tuple[str, int, str] | None  # (HH:MM, repeat code, intensity) or no alarm


def _waist_alarm(data: str) -> tuple[str, WaistAlarm] | None:
    """``repeat side intensity HH MM`` hex (onInit/onAlarm); repeat 00 is no alarm."""
    if len(data) < 10:
        return None
    side = {code[4]: name for name, code in WAIST_SIDES.items()}.get(int(data[2:4], 16))
    if side is None:
        return None
    if data[0:2] == "00":
        return side, None
    return side, (f"{int(data[6:8], 16):02d}:{int(data[8:10], 16):02d}", int(data[0:2], 16), data[4:6])


def parse_waist_init(frame: str) -> dict[str, Any]:
    """``onInit``: the powered 31-byte table, read in 4-hex-digit fields."""
    body = frame[4:-2]
    state: dict[str, Any] = {"mode": int(body[6:8], 16)}
    for index, name in enumerate(WAIST_SIDES):
        state[f"{name}_heat"] = int(body[10 + 4 * index : 12 + 4 * index], 16)
        state[f"{name}_pressure"] = int(body[22 + 4 * index : 24 + 4 * index], 16)
        state[f"{name}_duration"] = int(body[34 + 4 * index : 36 + 4 * index], 16)
    alarm = _waist_alarm(body[46:])
    if alarm is not None:
        state[f"{alarm[0]}_alarm"] = alarm[1]
    return state


def parse_waist_piece(frame: str) -> dict[str, Any]:
    """``onResult`` (5-byte) and ``onAlarm`` (9-byte) waist frames."""
    command, data = int(frame[4:6], 16), frame[6:-2]
    if command == WAIST_ALARM:
        if len(frame) == 10:
            side = next((n for n, c in WAIST_SIDES.items() if c[3] == int(data, 16)), None)
            return {f"{side}_alarm": None} if side else {}
        alarm = _waist_alarm(data)
        return {f"{alarm[0]}_alarm": alarm[1]} if alarm else {}
    if len(frame) != 10:
        return {}
    value = int(data, 16)
    if command == WAIST_MODE:
        return {"mode": value}
    for name, (heat, pressure, duration, _cancel, _side) in WAIST_SIDES.items():
        for code, kind in ((heat, "heat"), (pressure, "pressure"), (duration, "duration")):
            if command == code:
                return {f"{name}_{kind}": value}
    return {}


def alarm_countdown_minutes(target_minute_of_day: int, now_minute_of_day: int) -> int:
    """``(target - now) mod 1440``; zero (and the -1 case) become 1440."""
    minutes = (target_minute_of_day - now_minute_of_day) % 1440
    return 1440 if minutes in (0, -1) else minutes


def alarm_action(memory: int | None, massage: tuple[int, ...]) -> int | None:
    """``setAlarmData``/``combineCmd``: the opcode for one memory and 0-2 massages.

    Two massage selections become ``MSG_HEAD_FOOT_BOTH_ON``; a memory with a
    massage uses the combined opcode, and a pair without one sends nothing.
    """
    msg = None
    if massage:
        msg = MSG_HEAD_FOOT_BOTH_ON if len(massage) == 2 else massage[0]
    if memory is None:
        return msg
    if msg is None:
        return memory
    return ALARM_COMBINATIONS.get((memory, msg))


def chk_sum(hex_text: str) -> bool:
    """``BleUtil.chkSum``: the last byte equals the low byte of the others' sum."""
    if len(hex_text) < 4 or len(hex_text) % 2:
        return False
    data = bytes.fromhex(hex_text)
    return checksum(data[:-1]) == data[-1]


# ------------------------------------------------------------------ classifier


@dataclass(frozen=True, slots=True)
class Event:
    """One classified notification outcome."""

    kind: str
    data: str = ""
    extra: tuple[str, ...] = ()


RxType = Literal["NONE", "INIT", "MOTOR_MODE", "MOTOR_ANGLE", "MASSAGE", "UBL_LOCK",
                 "MEMORY_ARRIVAL", "ERROR", "ALARM", "SNORE"]


@dataclass(slots=True)
class Classifier:
    """The app's shared lowercase-hex notification buffer and classification.

    ``group`` selects the callback family: Revive Control, Blvd Home and
    HARMONY classify the stop-music prefix; Best Mattress and Idealbed do not.
    The version reply's page callback is handled by the controller.
    """

    group: AppGroup
    rx_type: RxType = "NONE"
    buffer: str = ""
    events: list[Event] = field(default_factory=list)

    def feed(self, data: bytes) -> list[Event]:
        self.events = []
        hex_text = data.hex()
        if hex_text.startswith(("6e", "5e")) and len(self.buffer) > BUFFER_RESET_LEN:
            self.buffer = ""
        self.buffer += hex_text
        buf = self.buffer
        if buf == RX_VERSION1:
            self.buffer = ""
            self.events.append(Event("version", "0001"))
            return self.events
        for prefix, rx in ((RX_HEAD_MOTOR_MODE, "MOTOR_MODE"), (RX_HEAD_MOTOR_ANGLE, "MOTOR_ANGLE"),
                           (RX_HEAD_MASSAGE, "MASSAGE"), (RX_HEAD_UBL_LOCK, "UBL_LOCK"),
                           (RX_HEAD_MEMORY_ARRIVAL, "MEMORY_ARRIVAL"), (RX_HEAD_ERROR, "ERROR")):
            if buf.startswith(prefix):
                self.rx_type = rx  # type: ignore[assignment]
                break
        else:
            if self.group == "revive" and buf.startswith(RX_STOP_MUSIC):
                self.events.append(Event("init", buf))
                self.buffer = ""
                return self.events
        head = buf[:2]
        if head == "6e":
            self._bed(buf)
        elif head == "5e":
            self._mattress(buf)
        else:
            self.buffer = ""
        return self.events

    def _done(self, *, reset_type: bool = True) -> None:
        self.buffer = ""
        if reset_type:
            self.rx_type = "NONE"

    def _bed(self, buf: str) -> None:
        if len(buf) < 10:
            return
        rx = self.rx_type
        if rx == "INIT":
            if len(buf) >= DATA_TABLE_LEN:
                return
            if not chk_sum(buf):
                self.buffer = ""
                return
            if buf == RX_DETECTION:
                self.events.append(Event("detection_available"))
            elif buf == RX_START_DETECTION:
                self.events.append(Event("detection_started"))
            elif buf == RX_STOP_DETECTION:
                self.events.append(Event("detection_stopped"))
            elif buf.startswith(RX_HEAD_DETECTION):
                self.events.append(Event("detection_result", buf, (buf[5:6], buf[6:7], buf[7:8])))
            else:
                self.events.append(Event("init", buf))
            self.buffer = ""
        elif rx == "MOTOR_MODE":
            bits = format(int(buf[5:6], 16), "04b")[:2]
            self.events.append(Event("motor_mode", bits))
            self._done()
        elif rx == "MOTOR_ANGLE":
            motor = format(int(buf[4:6], 16), "08b")
            raw = int(buf[6:8], 16)
            value = str(raw - 256 if raw > 127 else raw)
            if motor[6:8] == "01":  # Sign.NEGATIVE: the app prefixes a minus sign.
                value = "-" + value
            self.events.append(Event("motor_angle", motor[4:6], (value,)))
            self._done()
        elif rx == "MASSAGE":
            bits = format(int(buf, 16), f"0{len(buf) * 4}b")[20:32]
            self.events.append(Event("massage", bits))
            self._done()
        elif rx in ("UBL_LOCK", "ERROR"):
            self._done()
        elif rx == "MEMORY_ARRIVAL":
            self.events.append(Event("memory_arrival", buf[6:8]))
            self._done()
        elif rx == "ALARM":
            if chk_sum(buf):
                self.events.append(Event("alarm", buf))
            self._done()
        elif rx == "SNORE":
            if len(buf) >= DATA_TABLE_LEN:
                return
            valid = chk_sum(buf)
            if valid:
                self.events.append(Event("snore", buf))
                self.rx_type = "NONE"
            # Best Mattress and Idealbed keep a frame with a bad sum buffered.
            if valid or self.group == "revive":
                self.buffer = ""

    def _mattress(self, buf: str) -> None:
        sub = buf[2:4]
        if sub == "1a":  # ordinary mattress initialization, 28 bytes
            if len(buf) > 56:
                self.buffer = ""
            elif len(buf) == 56:
                if chk_sum(buf) and buf[6:8] == "01":
                    self.events.append(Event("init", TX_MATTRESS))
                    self.events.append(Event("mattress_init", buf))
                self.buffer = ""
        elif sub in ("01", "02"):
            if len(buf) in (10, 16):
                if chk_sum(buf):
                    self.events.append(Event("mattress", buf))
                self.buffer = ""
            else:
                self._resync(buf, "mattress")
        elif sub == "1b":  # waist mattress initialization, 31 bytes
            if len(buf) > 62:
                self.buffer = ""
            elif len(buf) == 62:
                if chk_sum(buf) and buf[6:8] == "01":
                    self.events.append(Event("waist_init", buf))
                self.buffer = ""
        elif sub == "03":
            pieces = {10: (10,), 18: (18,), 28: (10, 18), 36: (18, 18), 38: (10, 10, 18)}.get(len(buf))
            if pieces is None:
                self._resync(buf, "waist")
                return
            offset = 0
            for size in pieces:
                piece = buf[offset : offset + size]
                offset += size
                if chk_sum(piece):
                    self.events.append(Event("waist", piece))
            self.buffer = ""

    def _resync(self, buf: str, kind: str) -> None:
        """``handleMattressData``/``handleWaistData`` for unexpected lengths.

        Up to 80 hex digits the app scans for ``5e`` headers and takes
        ``substring(index, 10)`` (an absolute end, so only a header at the
        scan position yields a whole frame); a valid piece clears the buffer.
        """
        if len(buf) > 80:
            self.buffer = ""
            return
        found = False
        position = 0
        while position < len(buf):
            rest = buf[position:]
            index = rest.find("5e")
            if index == -1 or index + 10 > len(rest):
                break
            piece = rest[index:10]
            if chk_sum(piece):
                self.events.append(Event(kind, piece))
                found = True
            position += index + 10
        if found:
            self.buffer = ""
