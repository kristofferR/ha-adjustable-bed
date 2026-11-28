"""JunaSleep tables from its own profile and the proven shared encoders."""

from custom_components.adjustable_bed.profiles import junasleep as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _hex, _table


def render() -> str:
    rows = []
    transports = []
    for remote, profile in app.PROFILES.items():
        tx = app.codec.TRANSPORTS[profile.transport]
        rx = app.codec.TRANSPORTS[profile.notify]
        transports.append((app.CHOICES[remote], tx.service_uuid, tx.write_uuid, rx.notify_uuid))
        for axis, up, down in app.AXES[remote]:
            for direction, word in (("up", up), ("down", down)):
                rows.append(
                    (
                        remote.upper(),
                        f"{axis} {direction}",
                        _hex(encode(profile, word)),
                        f"held, {profile.refresh_ms} ms",
                    )
                )
        for action, word in {
            **profile.presets,
            **{f"Position {i}": w for i, w in profile.memory.items()},
            **app.actions(remote),
            "light": 0x20000,
        }.items():
            rows.append((remote.upper(), action, _hex(encode(profile, word)), "once"))
        rows.append(
            (
                remote.upper(),
                "status query",
                _hex(app.QUERY[remote]),
                f"every {app.QUERY_PERIOD_S:g} s",
            )
        )
    return "\n".join(
        [
            *_table(
                ("Remote", "Write service", "Write characteristic", "Normal notify characteristic"),
                transports,
            ),
            "",
            *_table(("Remote", "Control", "Frame", "Dispatch"), rows),
            "",
            *_table(
                ("Operation", "Schedule"),
                [
                    (
                        "A post-tap status",
                        f"3 queries, {app.POST_TAP_QUERY_S * 1000:g} ms initial and interval",
                    ),
                    ("Release / STOP", "End refresh, no packet"),
                ],
            ),
        ]
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-junasleep", render)]
