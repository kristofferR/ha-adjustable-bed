"""Sleep Assist Pro saved-ID routes and explicitly configured remote controls."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..codec import keeson
from ..codec.sleep_assist_pro import Route
from ..const import CONF_BLE_DEVICE_NAME, CONF_HAS_LIGHT, CONF_PRODUCT_TYPE
from ..execution import STREAM_HOLD, ExecutionCapabilities

CONF_CONTROLS: Final = "sleep_assist_pro_controls"
MOTION_INTERVAL_MS: Final = 200
GATT_OPERATION_TIMEOUT_SECONDS: Final = 5

NORDIC_0001: Final = keeson.TRANSPORTS["ksbt"]
NORDIC_0020: Final = keeson.Transport(
    "6e400020-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400021-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400022-b5a3-f393-e0a9-e50e24dcca9e",
)
FFE5: Final = keeson.Transport(
    "0000ffe5-0000-1000-8000-00805f9b34fb",
    "0000ffe9-0000-1000-8000-00805f9b34fb",
    "0000ffe4-0000-1000-8000-00805f9b34fb",
)
A00A: Final = keeson.TRANSPORTS["json"]
EE00: Final = keeson.Transport(
    "000000ee-0000-1000-8000-00805f9b34fb",
    "0000ff04-0000-1000-8000-00805f9b34fb",
    "0000ff02-0000-1000-8000-00805f9b34fb",
)

TRANSPORTS: Final[dict[Route, tuple[keeson.Transport, ...]]] = {
    "p1": (NORDIC_0001, NORDIC_0020, FFE5),
    "p2": (NORDIC_0001, NORDIC_0020, FFE5),
    "p3": (NORDIC_0001,),
    "p4": (A00A,),
    "p5": (EE00,),
}

WORDS: Final = {
    "head_up": 0x01,
    "head_down": 0x02,
    "feet_up": 0x04,
    "feet_down": 0x08,
    "tilt_up": 0x10,
    "tilt_down": 0x20,
    "lumbar_up": 0x40,
    "lumbar_down": 0x80,
    "bed_up": 0x50,
    "bed_down": 0xA0,
    "flat": 0x08000000,
    "zero_g": 0x1000,
    "anti_snore": 0x8000,
    "music": 0x10000,
    "relax": 0x2000,
    "tv": 0x4000,
    "demonstration": 0x80000000,
    "bed_in": 0x40000000,
    "bed_out": 0x80000000,
    "massage_all": 0x100,
    "massage_timer": 0x200,
    "massage_feet_up": 0x400,
    "massage_head_up": 0x800,
    "massage_head_down": 0x800000,
    "massage_feet_down": 0x1000000,
    "light_toggle": 0x20000,
}

PRESETS: Final = {
    "anti_snore": "Anti-snore",
    "music": "Music",
    "relax": "Relax / Read",
    "tv": "TV",
}
MASSAGE: Final = {
    "massage_all": "All-zone massage",
    "massage_timer": "Massage timer",
    "massage_head_up": "Head massage up or cycle",
    "massage_feet_up": "Foot massage up or cycle",
    "massage_head_down": "Head massage down",
    "massage_feet_down": "Foot massage down",
}
CONTROL_CHOICES: Final = {
    "head": "Head movement",
    "feet": "Foot movement",
    "tilt": "Head tilt",
    "side_b": "Side B head movement (double-head layout)",
    "lumbar": "Lumbar",
    "flat": "Flat",
    "zero_g": "Zero gravity",
    **PRESETS,
    "demonstration": "Demonstration",
    **MASSAGE,
    "dawnhouse": "DawnHouse bed up / down and in / out controls",
    "rgb": "RGB under-bed light",
    "dimmer": "ErgoSportive light dimmer",
}


def route_for_id(device_id: object) -> Route | None:
    """Use the saved ID, with the length Java String.length() reports."""
    if not isinstance(device_id, str):
        return None
    name = device_id.lower()
    size = len(device_id.encode("utf-16-le", errors="surrogatepass")) // 2
    if name.startswith(("base-i4", "base-i5")):
        return "p1"
    if name.startswith("ksbt"):
        if size == 13:
            return "p3"
        if size == 16:
            return "p2"
    if name.startswith("kswf") and size == 16:
        return "p4"
    if name.startswith(("kspsbed", "ksslbed")):
        return "p5"
    return None


@dataclass(frozen=True, slots=True)
class Profile:
    route: Route
    device_id: str
    controls: frozenset[str]
    light: bool

    @property
    def execution(self) -> ExecutionCapabilities:
        return STREAM_HOLD

    @property
    def indication(self) -> bool:
        return self.route in ("p4", "p5")


def selected(data: Mapping[str, object]) -> Profile:
    device_id = data.get(CONF_BLE_DEVICE_NAME)
    if not isinstance(device_id, str) or (route := route_for_id(device_id)) is None:
        raise ValueError(CONF_BLE_DEVICE_NAME)
    # The frozen JSON vectors establish the ordinary ASCII identity form.
    if route in ("p4", "p5") and re.fullmatch(r"[A-Za-z0-9_.-]+", device_id) is None:
        raise ValueError(CONF_BLE_DEVICE_NAME)
    values = data.get(CONF_CONTROLS, ())
    if not isinstance(values, (list, tuple)) or any(
        not isinstance(value, str) or value not in CONTROL_CHOICES for value in values
    ):
        raise ValueError(CONF_CONTROLS)
    controls: frozenset[str] = frozenset(values)
    light = data.get(CONF_HAS_LIGHT) is True
    name = str(data.get(CONF_PRODUCT_TYPE, "")).lower()
    if (
        (not controls and not light)
        or {"tilt", "side_b"} <= controls
        or "dawnhouse" in controls
        and (
            route not in ("p4", "p5")
            or not any(token in name for token in ("dawnhouse", "dawn house"))
        )
        or "rgb" in controls
        and (not light or route in ("p4", "p5"))
        or "dimmer" in controls
        and (not light or route != "p3" or "ergosportive" not in name)
    ):
        raise ValueError(CONF_CONTROLS)
    return Profile(route, device_id, controls, light)
