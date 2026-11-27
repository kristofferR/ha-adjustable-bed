"""Restonic app tables, rendered from its profile and existing wire encoders."""

from custom_components.adjustable_bed.profiles import restonic as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/restonic.md"


def transports() -> str:
    return _block(
        _table(
            (
                "Branch",
                "Write service / characteristic",
                "Notify service / characteristic",
                "Response",
            ),
            (
                (
                    branch,
                    f"`{t.service}` / `{t.write}`",
                    f"`{t.notify_service}` / `{t.notify}`",
                    str(t.response),
                )
                for branch, t in app.TRANSPORTS.items()
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Action", "Layouts", *app.TRANSPORTS),
            (
                (
                    action,
                    ", ".join(
                        layout for layout, actions in app.ACTIONS.items() if action in actions
                    )
                    or "all (STOP)",
                    *(f"`{_hex(app.encode(branch, action))}`" for branch in app.TRANSPORTS),
                )
                for action in app.WORDS
            ),
        )
    )


def profiles() -> str:
    return _block(
        _table(
            ("Layout", "Axes", "Memory recall", "Presets", "Refresh", "Release"),
            (
                (
                    app.LAYOUT_CHOICES[layout],
                    ", ".join(app.AXES[layout]),
                    str(profile.memory_slots),
                    ", ".join(profile.presets),
                    f"{app.REFRESH_MS} ms",
                    f"{app.STOP_COUNT} STOP frames, {app.REFRESH_MS} ms apart",
                )
                for layout, profile in app.PROFILES.items()
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "restonic-transports", transports),
    (GUIDE, "restonic-commands", commands),
    (GUIDE, "restonic-profiles", profiles),
]
