"""Generated Linx profile, GATT, timing and static-control reference."""

from custom_components.adjustable_bed.codec import linx as codec
from custom_components.adjustable_bed.profiles import linx as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/linx.md"
DEVICE = "KSWF07D00000000"


def bed_types() -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(app.PROFILES, ("linx",))


def profiles() -> str:
    return _block(
        _table(
            (
                "Profile",
                "App model",
                "Refresh",
                "Unknown mode km",
                "Cache",
                "Startup / chunk limit",
            ),
            (
                (
                    key,
                    profile.label,
                    f"{profile.refresh_ms} ms",
                    str(profile.unknown_mode_km),
                    "Consume on touch" if profile.consumes_mode else "Retain per connection",
                    f"{app.CONNECT_SETTLE_MS} ms, subscribe, route query, bed-mode query; {app.WRITE_CHUNK_SIZE} bytes",
                )
                for key, profile in app.PROFILES.items()
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Route", "Service", "Write", "Incoming", "Subscription", "Intervention"),
            (
                (
                    key,
                    codec.TRANSPORTS[route.event_transport].service,
                    codec.TRANSPORTS[route.event_transport].write,
                    codec.TRANSPORTS[route.event_transport].notify,
                    codec.TRANSPORTS[route.event_transport].subscription,
                    "Binary, direct UART" if route.snore_uart else "JSON, same generic route",
                )
                for key, route in app.ROUTES.items()
            ),
        )
    )


def commands() -> str:
    rows: list[tuple[str, str, str]] = []
    for key, profile in app.PROFILES.items():
        for axis, words in app.AXES.items():
            for direction, word in zip(("up", "down"), words, strict=True):
                for km in (6, 10):
                    rows.append(
                        (
                            key,
                            f"{axis} {direction}, km {km}",
                            codec.control(DEVICE, word, km=km, held=True).decode(),
                        )
                    )
            release = app.release(profile, DEVICE, axis)
            rows.append(
                (
                    key,
                    f"{axis} release",
                    release.decode() if release.startswith(b"{") else _hex(release),
                )
            )
        actions = {**app.PRESETS, "light": app.LIGHT}
        if profile.massage:
            actions.update({f"memory_{slot}": word for slot, word in app.MEMORY.items()})
            actions.update({f"massage_{name}": word for name, word in app.MASSAGE.items()})
        else:
            actions["sleep / anti-snore"] = app.MEMORY[1]
        rows.extend(
            (key, action, codec.control(DEVICE, word).decode()) for action, word in actions.items()
        )
    rows.extend(
        ("either", f"clear alarm {slot}", codec.alarm_slot(DEVICE, slot).decode())
        for slot in range(1, 7)
    )
    rows.extend(
        ("either", name, codec.request(DEVICE, code, fields).decode())
        for name, code, fields in (
            ("status", 4, {"sw": 1}),
            ("bed mode", 7, {"bedmd": 100}),
            ("self-check", 6, {"key": "80000000", "km": 2}),
        )
    )
    rows.append(("UART", "startup query", codec.startup_query(DEVICE).decode()))
    for route, settings in app.ROUTES.items():
        frame = codec.snore(
            DEVICE,
            uart=settings.snore_uart,
            keep=app.SNORE_DEFAULT,
            speed=app.SNORE_DEFAULT,
            lift=app.SNORE_DEFAULT,
        )
        rows.append(
            (
                route,
                f"snore defaults {app.SNORE_DEFAULT}",
                frame.decode() if frame.startswith(b"{") else _hex(frame),
            )
        )
    rows.append(("A00A", "snore status", _hex(codec.SNORE_STATUS)))
    return _block(_table(("Profile / route", "Action", "Payload"), rows))


BLOCKS: list[Block] = [
    (GUIDE, f"linx-{name}", renderer)
    for name, renderer in (
        ("profiles", profiles),
        ("transports", transports),
        ("commands", commands),
    )
]
