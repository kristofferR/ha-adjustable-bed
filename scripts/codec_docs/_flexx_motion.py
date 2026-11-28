"""Usable Flexx Motion model, control and setting tables from owned profiles."""

from collections import defaultdict
from datetime import UTC, datetime

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import flexx_motion as p
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    groups: dict[tuple[str, int, int | None, bool, bool, int], list[str]] = defaultdict(list)
    for profile in p.PROFILES.values():
        for action in profile.controls:
            groups[
                (
                    action.label,
                    action.code,
                    action.save,
                    action.held,
                    action.release,
                    action.save_delay_ms,
                )
            ].append(profile.label)
    return _block(
        _table(
            (
                "Model",
                "Selection",
                "Movement",
                "Memory slots",
                "Massage",
                "Alarm",
                "Color light",
                "Bed side",
            ),
            (
                (
                    profile.label,
                    "Current picker" if profile.normal else "Restored product",
                    ", ".join(
                        a.label.removesuffix(" up")
                        for a in profile.controls
                        if a.action in ("HeadUp", "FootUp", "LumberUp", "PillowUp", "FootBoxUp")
                    ),
                    str(sum(a.action.startswith("MemoryPosition") for a in profile.controls)),
                    "yes"
                    if any(a.action.startswith("Massage") for a in profile.controls)
                    else "no",
                    ("7 repeating slots" if profile.repeat else "One-shot")
                    if profile.clock
                    else "no",
                    "after light reply" if profile.light else "no",
                    "Left / Right" if profile.side else "no selector",
                )
                for profile in sorted(
                    p.PROFILES.values(), key=lambda profile: (not profile.normal, profile.label)
                )
            ),
        ),
        _table(
            ("Control", "Nordic", "Framed, left", "Save", "Gesture / release", "Models"),
            (
                (
                    label,
                    _hex(codec.function(code, single=True)),
                    _hex(codec.function(code)),
                    _hex(codec.function(save)) + (" after 3 s" if delay else "")
                    if save is not None
                    else "none",
                    ("100 ms held refresh" if held else "one press")
                    + ("; STOP" if release else "; no release frame"),
                    ", ".join(models),
                )
                for (label, code, save, held, release, delay), models in groups.items()
            ),
        ),
        _table(
            ("Transport", "Service", "Required write UUID", "Nominal notify UUID"),
            (
                (
                    key,
                    f"`{codec.TRANSPORTS[key].service_uuid}`",
                    f"`{codec.TRANSPORTS[key].write_uuid}`",
                    f"`{codec.TRANSPORTS[key].notify_uuid}`",
                )
                for key in p.CATALOG_TRANSPORTS
            ),
        ),
        _table(
            ("Timing", "Value"),
            (
                ("Held first tick / refresh", f"{p.HOLD_MS} ms"),
                (
                    "Transport completion timeout (not a bed acknowledgement)",
                    f"{p.IO_TIMEOUT_S:g} s",
                ),
                (
                    "Clock / light startup query",
                    f"{p.QUERY_MS} / {2 * p.QUERY_MS} ms after menu startup",
                ),
                ("Pending receive expiry", f"{p.RECEIVE_EXPIRY_S:g} s"),
                ("Light timer send delay", f"{p.LIGHT_DELAY_MS} ms"),
                (
                    "Blue light timer choices",
                    ", ".join(f"{n // 60} min" for n in p.PROFILES["blue"].light_seconds),
                ),
                (
                    "Other color-light timer choices",
                    "Always on, "
                    + ", ".join(f"{n // 60} min" for n in p.PROFILES["PB450"].light_seconds if n),
                ),
            ),
        ),
        _table(
            ("Setting / example", "Frame or ordered frames"),
            (
                (
                    "Exit limit, framed",
                    _hex(codec.function(0, action="deviceFunctionItemExitLimit")),
                ),
                (
                    "Clock capability query, framed",
                    _hex(codec.function(1, action="deviceFunctionItemCheckClock")),
                ),
                (
                    "Light capability query, framed",
                    _hex(codec.function(1, action="deviceFunctionItemCheckLight")),
                ),
                (
                    "STOP, Nordic / framed left / right",
                    " / ".join(
                        _hex(codec.function(codec.STOP, side, single=raw))
                        for raw, side in ((True, 0), (False, 0), (False, 1))
                    ),
                ),
                ("Color light off, left regardless of selected side", _hex(codec.function(p.LIGHT_CLOSE_OPCODE))),
                (
                    "One-shot alarm, 300 min, zero gravity",
                    " / ".join(map(_hex, codec.countdown(300, 0x45))),
                ),
                ("Cancel one-shot alarm", " / ".join(map(_hex, codec.countdown(0, 0)))),
                ("Read repeating alarms", _hex(codec.record_20_len(5, 1, 0, (0,)))),
                (
                    "Alarm 1, 06:30, zero gravity, Monday and Wednesday",
                    _hex(codec.record_20_len(5, 1, 1, (1, 0, 6, 30, 0x45, 0xA1))),
                ),
                (
                    "Disable that alarm",
                    _hex(codec.record_20_len(5, 1, 1, (1, 0, 6, 30, 0x45, 0xA0))),
                ),
                ("Delete alarm 1", _hex(codec.record_20_len(5, 2, 1, (1,)))),
                (
                    "Query box mode, Blue / Green / Orange",
                    _hex(codec.record_20_len(11, 2, 0, (0,))),
                ),
                (
                    "Box mode: standard / split",
                    " / ".join(_hex(codec.record_20_len(11, 2, 1, (0, mode))) for mode in (p.BOX_STANDARD, p.BOX_SPLIT)),
                ),
                (
                    "Light timer: always on / 60 s",
                    " / ".join(map(_hex, (codec.light_timer(255, 255), codec.light_timer(0, 60)))),
                ),
                (
                    "Clock, 2026-11-28 06:30 UTC",
                    " / ".join(
                        map(
                            _hex,
                            codec.time_sync(
                                datetime(2026, 11, 28, 6, 30, tzinfo=UTC),
                                build=codec.record_20_len,
                                first_hex=True,
                            ),
                        )
                    ),
                ),
            ),
        ),
        _table(
            ("Light color", "One GATT write"),
            (
                (name.replace("_", " ").capitalize(), _hex(codec.rgb(*rgb)))
                for name, rgb in p.PALETTE.items()
            ),
        ),
    )
