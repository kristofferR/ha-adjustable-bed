"""Softide 1.2.4: explicit local models and independent primary/care routes."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..codec import sleep_assistant as codec
from ..const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT
from ..execution import STREAM_HOLD, ExecutionCapabilities

SERVICE: Final = "0000a00a-0000-1000-8000-00805f9b34fb"
WRITE: Final = "0000b002-0000-1000-8000-00805f9b34fb"
NOTIFY: Final = "0000b003-0000-1000-8000-00805f9b34fb"
NAME: Final = "KSWF16S"
REFRESH_MS: Final = 300
PRIMARY_TIMEOUT_MS: Final = 50000
MOON_SAMPLE_LIMIT: Final = 96
MOON_DISPLAY_SECONDS: Final = 482
MOON_GATE_MS: Final = 1500
QUERY_DELAY_MS: Final = 700
FREQUENCY_DELAY_MS: Final = 300
REQUEST_DELAY_MS: Final = 10
PROGRAM_OFFSETS_MS: Final = (0, 200, 800, 1400)
CONF_SENSORS: Final = "softide_sensors"
CONF_PREPARE: Final = "softide_prepare_massage"
ROUTES: Final = {
    "primary": "Ordinary remote (STOP on release)",
    "care": "Care remote (end refresh on release)",
}
SENSORS: Final = {
    "single": "One sleeper",
    "right": "Right sensor",
    "left": "Left sensor",
    "combined": "Both sensors",
}
MODELS: Final = {
    "1": "IQ1 exhibition (1)",
    "2": "Teenagers exhibition (2)",
    "3": "IQ3 Plus exhibition (3)",
    "4": "IQ3Y Plus (4)",
    "5": "S Nova (5)",
    "6": "S100 brushless (6)",
    "7": "Teenagers brushless (7)",
    "8": "S300 Plus brushless (8)",
    "9": "S300Y Plus brushless (9)",
    "other": "Other model (IQ1 remote)",
    "-1": "No selected model (-1)",
}
SPARSE_KEYS: Final = frozenset(
    {
        0,
        1,
        2,
        4,
        5,
        8,
        9,
        10,
        16,
        32,
        37,
        64,
        128,
        256,
        512,
        1024,
        2048,
        3072,
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        262144,
        524288,
        1048576,
        2097152,
        4194304,
        8388608,
        16777216,
        33554432,
        134217728,
        1073741824,
    }
)
WORDS: Final = {
    "back_up": 1,
    "back_down": 2,
    "legs_up": 4,
    "legs_down": 8,
    "section_a_up": 1,
    "section_a_down": 2,
    "section_b_up": 4,
    "section_b_down": 8,
    "combined_up": 5,
    "combined_down": 10,
    "foot_up": 16,
    "foot_down": 32,
    "flat": 134217728,
    "zero_g": 4096,
    "tv": 16384,
    "reading": 8192,
    "massage_head": 2048,
    "massage_foot": 1024,
    "massage_timer": 512,
    "massage_off": 33554432,
    "stop": 0,
}
MASSAGE: Final = {
    "massage_head": "Cycle head massage",
    "massage_foot": "Cycle foot massage",
    "massage_timer": "Cycle massage timer",
    "massage_off": "Massage off",
}
MODES: Final = {
    "relaxation": "Relaxation",
    "lumbar_relaxation": "Lumbar relaxation",
    "sleep_relaxation": "Relaxation for better sleep",
}
PROGRAMS: Final = {
    "one_button_sleep": ("One button sleep", 1073741824),
    "smart_relaxation": ("Smart relaxation program", 2147483648),
    "after_drinking": ("After-drinking program", 32768),
    "reverse_arrow": ("Reverse arrow pose", 1073750016),
    "supine_bound_angle": ("Supine bound angle pose", 1073750016),
    "locust": ("Locust pose", 4096),
    "bow": ("Bow pose", 4096),
    "rest": ("Rest pose", 134217728),
}


def instruction(key: int) -> bytes:
    return codec.aa_key(key if key in SPARSE_KEYS else 0)


def frame(action: str) -> bytes:
    return instruction(WORDS[action]) if action in WORDS else codec.SOFTIDE_LITERALS[action]


def program(action: str) -> tuple[tuple[int, bytes], ...]:
    return (
        (0, frame("prepare_program")),
        (200, frame("massage_off")),
        (200, frame("stop")),
        (800, frame("massage_off")),
        (800, frame("stop")),
        (1400, codec.aa_key(PROGRAMS[action][1])),
        (1400, frame("stop")),
    )


@dataclass(frozen=True, slots=True)
class SoftideProfile:
    model: str
    route: str = "primary"
    sensors: str = "single"
    identity: str = ""
    prepare_massage: bool = False
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def key(self) -> str:
        return f"softide:{self.model}:{self.route}"

    @property
    def layout(self) -> str | None:
        if self.model == "-1" and self.route == "primary":
            return None
        return "IQ3" if self.model in ("3", "8") else "IQ3Y" if self.model in ("4", "9") else "IQ1"

    @property
    def axes(self) -> tuple[str, ...]:
        if self.layout is None:
            return ()
        return (
            ("section_a", "section_b", "combined", "foot")
            if self.layout == "IQ3Y"
            else ("back", "legs")
        )

    @property
    def controls(self) -> tuple[str, ...]:
        if self.layout is None:
            return ()
        return (
            "flat",
            "zero_g",
            "tv",
            "reading",
            *MASSAGE,
            *(MODES if self.layout != "IQ1" else ()),
        )

    @property
    def programs(self) -> tuple[str, ...]:
        if self.route == "care":
            return ()
        # Simple models have audio-only Likes; Moon and SmartRelax remain
        # separate primary pages. The unmatched branch also has JHMS/YJM.
        return (
            "one_button_sleep",
            "smart_relaxation",
            "rest",
            *(
                key
                for key in PROGRAMS
                if key not in ("one_button_sleep", "smart_relaxation", "rest")
                and self.model not in ("1", "2", "5", "6", "7")
            ),
        )


def selected(data: Mapping[str, object]) -> SoftideProfile:
    model, route = data.get(CONF_PROTOCOL_VARIANT, "other"), data.get(CONF_PRODUCT_TYPE, "primary")
    sensors = data.get(CONF_SENSORS, "single")
    identity = data.get(CONF_BLE_DEVICE_NAME, "")
    prepare = data.get(CONF_PREPARE, False)
    for key, value, choices in (
        (CONF_PROTOCOL_VARIANT, model, MODELS),
        (CONF_PRODUCT_TYPE, route, ROUTES),
        (CONF_SENSORS, sensors, SENSORS),
    ):
        if not isinstance(value, str) or value not in choices:
            raise ValueError(key)
    if not isinstance(identity, str) or type(prepare) is not bool:
        raise ValueError(CONF_BLE_DEVICE_NAME)
    assert isinstance(model, str) and isinstance(route, str) and isinstance(sensors, str)
    return SoftideProfile(model, route, sensors, identity, prepare)
