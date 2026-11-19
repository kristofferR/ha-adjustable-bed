"""SmartBed profile tables from the shipped app dispatch and existing codecs."""

from custom_components.adjustable_bed.profiles import smartbed as app

from ._common import Block, _block, _table

GUIDE = "docs/beds/smartbed.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(app.PROFILES, ("okin_cb24",))


def profiles() -> str:
    return _block(
        _table(
            (
                "Profile",
                "Builder",
                "Refresh",
                "Release",
                "Long save",
                "Preset choices",
                "Light",
                "Massage timer",
                "Wave maximum",
            ),
            (
                (
                    p.key,
                    "P3 / P4 with five motors" if p.key == "cb24" else f"P{p.base_protocol}",
                    f"{p.refresh_ms} ms",
                    f"{p.release_ms} ms",
                    f"{p.save_ms} ms",
                    ", ".join(p.preset_names),
                    "Yes" if p.has_light else "No",
                    "Yes" if p.has_massage and p.massage_timer else "No",
                    str(3 if p.base_protocol == 2 else p.wave_max) if p.has_massage else "None",
                )
                for p in app.PROFILES.values()
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Profiles", "Write service", "Write", "Notify service", "Notify"),
            (
                (
                    ", ".join(p.key for p in app.PROFILES.values() if p.transport == transport),
                    *(f"`{uuid}`" for uuid in transport),
                )
                for transport in dict.fromkeys(p.transport for p in app.PROFILES.values())
            ),
        )
    )


def commands() -> str:
    rows: list[tuple[str, str, str]] = []
    protocols: tuple[app.Protocol, ...] = (1, 2, 3, 4, 5)
    for protocol in protocols:

        def add(
            label: str,
            function: int,
            sub: int = 0,
            data: bytes | None = None,
            *,
            protocol: app.Protocol = protocol,
        ) -> None:
            frame = app.packet(protocol, function, sub, data)
            if frame:
                rows.append((f"P{protocol}", label, f"`{frame.hex()}`"))

        for function in (
            app.Function.HEAD,
            app.Function.FOOT,
            app.Function.BOTH,
            app.Function.TILT,
            app.Function.LUMBAR,
            app.Function.HIPS,
        ):
            for sub, direction in ((1, "up"), (2, "down")):
                add(f"{function.name.lower()} {direction}", function, sub)
        add("STOP", app.Function.STOP)
        for name, function in app.PRESETS.items():
            add(name, function, 6)
            if protocol == 5 and name != "flat":
                add(f"Save {name}", function, 7)
        for function in (
            app.Function.HEAD_MASSAGE,
            app.Function.FOOT_MASSAGE,
            app.Function.INTENSITY,
            app.Function.WAVE,
        ):
            for level in range(
                1, (4 if function is app.Function.WAVE and protocol != 2 else 3) + 1
            ):
                add(f"{function.name.lower()} {level}", function, level + 9)
        stepped = (
            (app.Function.INTENSITY, app.Function.WAVE)
            if protocol == 1
            else (app.Function.HEAD_MASSAGE, app.Function.FOOT_MASSAGE, app.Function.WAVE)
        )
        if protocol == 2:
            stepped += (app.Function.INTENSITY,)
        if protocol in (3, 4, 5):
            stepped += (app.Function.TIMER,)
        if protocol == 5:
            stepped = (app.Function.TIMER,)
            for function, (minimum, maximum) in app.ARROW_RANGES.items():
                for current in range(maximum + 1):
                    for increase in (False, True):
                        level = min(current + 1, maximum) if increase else max(current - 1, minimum)
                        add(
                            f"{function.name.lower()} {'increase' if increase else 'decrease'} from {current}",
                            function,
                            4 if level == 0 else level + 9,
                        )
        for function in stepped:
            for sub, direction in ((8, "increase"), (9, "decrease")):
                add(f"{function.name.lower()} {direction}", function, sub)
        if protocol in (2, 3, 4):
            add("Massage toggle", app.Function.MASSAGE, 3)
        for value in (10, 20, 30):
            add(f"Massage timer {value} minutes", app.Function.TIMER, value // 10 + 9)
        add("Massage query", app.Function.MASSAGE, 5)
        if protocol in (1, 5):
            add("Massage on", app.Function.MASSAGE, 3)
            add("Massage off", app.Function.MASSAGE, 4)
        add("Light on / toggle", app.Function.LIGHT, 3)
        if protocol == 5:
            add("Light off", app.Function.LIGHT, 4)
            add("Light query", app.Function.LIGHT, 5)
            for enabled in (0, 1):
                add(
                    f"RGB-flag light {'on' if enabled else 'off'}",
                    app.Function.LIGHT,
                    6,
                    bytes((2, enabled)),
                )
            for page in range(8):
                add(f"Configuration page {page}", app.Function.CONFIGURATION, data=bytes((page,)))
            for head, head_value in enumerate((0, 4, 6, 8)):
                for foot, foot_value in enumerate((0, 4, 6, 8)):
                    add(
                        f"Sonic intensity, head {head}, foot {foot}",
                        app.Function.SONIC_INTENSITY,
                        data=bytes((head_value, foot_value)),
                    )
            for mode in (0, 1):
                add(f"Sonic mode {mode}", app.Function.SONIC_MODE, 6, bytes((mode,)))
            for sub, label in ((3, "on"), (4, "off"), (5, "query")):
                add(f"Sonic {label}", app.Function.SONIC, sub)
            for minutes in (10, 20, 30):
                add(f"Sonic timer {minutes} minutes", app.Function.SONIC_TIMER, minutes // 10 + 9)
            for wave in range(7):
                add(f"Sonic wave {wave}", app.Function.SONIC_WAVE, data=bytes((wave,)))

        if protocol != 1:
            add("Alarm query", app.Function.ALARM, 5)
            add("Disable alarm", app.Function.ALARM, 4)
    return _block(_table(("Builder", "Control", "Frame (both sides)"), rows))


BLOCKS: list[Block] = [
    (GUIDE, "smartbed-profiles", profiles),
    (GUIDE, "smartbed-transports", transports),
    (GUIDE, "smartbed-commands", commands),
]
