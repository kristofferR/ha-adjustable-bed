"""Fixed ASCII app tables rendered only from the shipped profiles and codec."""

from collections.abc import Iterable

from custom_components.adjustable_bed.beds.richmat_legacy.protocol import packet
from custom_components.adjustable_bed.codec.richmat import TRANSPORTS
from custom_components.adjustable_bed.profiles.richmat_legacy import APP_NAMES, Action, profiles
from scripts.codec_docs._common import Block, _block, _table


def _writes(values: Iterable[str]) -> str:
    return " / ".join("`" + packet(value).hex().upper() + "`" for value in values) or "none"


def _local_effects(action: Action) -> str:
    effects = []
    if action.select in ("axis", "mode"):
        effects.append(
            "; ".join(
                f"{action.select} {index}: state {state}"
                for index, state in enumerate(action.states)
            )
        )
    if action.selected_value is not None:
        effects.append(f"set local mode {action.selected_value}")
    if action.axis_value is not None:
        effects.append(f"select local axis {action.axis_value}")
    if action.select == "led":
        effects.append("alternate local LED request flag")
    if action.key == "cancel_refresh":
        effects.append("cancel screen refresh; no wire write")
    if action.reset_counter:
        effects.append("reset screen counter on release")
    return "; ".join(effects) or "none"


def render() -> str:
    catalog = profiles()
    parts: list[str] = []
    route = TRANSPORTS["n1"]
    parts += _table(
        ("Service", "Write", "Local notify target (no subscription handshake)"),
        [(f"`{route.service_uuid}`", f"`{route.write_uuid}`", f"`{route.notify_uuid}`")],
    )
    parts += ["", "##### App and prefix catalog", ""]
    parts += _table(
        ("App", "Profile key", "Exact name prefixes", "Screen: initial / period (ms)"),
        (
            (
                APP_NAMES[profile.app],
                f"`{profile.key}`",
                ", ".join(f"`{prefix}*`" for prefix in profile.routes),
                "; ".join(
                    f"{screen}: {initial} / {period}"
                    for screen, initial, period in profile.schedules
                ),
            )
            for profile in catalog.values()
        ),
    )
    for app, name in APP_NAMES.items():
        parts.extend(["", f"##### {name}", ""])
        for profile in catalog.values():
            if profile.app != app:
                continue
            parts += [
                f"###### {profile.code}",
                "",
                "Exact name gates: "
                + ", ".join(f"`{p}*`" for p in profile.routes)
                + ". "
                + "Schedules (screen, initial/period ms): "
                + "; ".join(f"{s}: {initial}/{period}" for s, initial, period in profile.schedules)
                + ".",
                "",
            ]
            rows = []
            for action in profile.actions:
                branch = (
                    "; ".join(
                        f"{arm}: {_writes(b.writes)}"
                        + (
                            f" from event {b.threshold + 1} (threshold {b.threshold})"
                            if b.threshold is not None
                            else ""
                        )
                        for arm, b in action.branches
                    )
                    or "none"
                )
                down = (
                    "; ".join(
                        f"flag {i}: {_writes(v)}" for i, v in enumerate(action.down_by_selection)
                    )
                    if action.down_by_selection
                    else _writes(action.down)
                )
                short = (
                    _writes(action.short) + f" if counter <{action.short_guard}"
                    if action.short_guard is not None
                    else "none"
                )
                rows.append(
                    (
                        f"`{action.key}`",
                        action.label.replace("|", "/"),
                        action.screen,
                        down,
                        branch,
                        short,
                        _writes(action.release),
                        _local_effects(action),
                    )
                )
            parts += _table(
                (
                    "Control key",
                    "App label / artwork",
                    "Screen",
                    "DOWN attempts",
                    "Periodic state: attempts",
                    "Short release",
                    "Unconditional release",
                    "Local effects",
                ),
                rows,
            )
            parts.append("")
    return _block(parts)


BLOCKS: list[Block] = [("docs/beds/richmat.md", "richmat-legacy-ascii", render)]
