"""Render the Sleep Assist Pro selector, BLE roles and wire tables."""

from custom_components.adjustable_bed.codec import sleep_assist_pro as codec
from custom_components.adjustable_bed.profiles import sleep_assist_pro as app

from ._common import _block, _hex, _table

GUIDE = "docs/beds/sleep-assist-pro.md"
IDS: dict[codec.Route, str] = {
    "p1": "BASE-I4.demo",
    "p2": "KSBT012345678901",
    "p3": "KSBT012345678",
    "p4": "KSWF012345678901",
    "p5": "KSPSBED_TEST",
}


def transports() -> str:
    return _block(
        _table(
            ("Route", "Service", "Write", "Receive", "Subscription"),
            (
                (
                    route.upper(),
                    gatt.service_uuid,
                    gatt.write_uuid,
                    gatt.notify_uuid,
                    "Indicate" if route in ("p4", "p5") else "Notify",
                )
                for route, transports in app.TRANSPORTS.items()
                for gatt in transports
            ),
        )
    )


def controls() -> str:
    return _block(
        _table(
            ("Action", "Key", "Routes"),
            (
                (
                    action.replace("_", " "),
                    f"`{word:08x}`",
                    "P4"
                    if action in ("bed_up", "bed_down")
                    else "P4, P5"
                    if action in ("bed_in", "bed_out")
                    else "P1–P5",
                )
                for action, word in app.WORDS.items()
            ),
        )
    )


def frames() -> str:
    return _block(
        _table(
            ("Route", "Head up", "Held movement follow-up"),
            (
                (
                    route.upper(),
                    _hex(codec.key(route, app.WORDS["head_up"], device, epoch_seconds=1700000000)),
                    _hex(release) if (release := codec.release(route, device)) else "End refresh",
                )
                for route, device in IDS.items()
            ),
        )
    )


BLOCKS = [
    (GUIDE, "sleep-assist-pro-transports", transports),
    (GUIDE, "sleep-assist-pro-controls", controls),
    (GUIDE, "sleep-assist-pro-frames", frames),
]
