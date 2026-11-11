"""Product- and notification-gated configuration actions for Richmat 4.2.0."""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, cast

from homeassistant.util import dt as dt_util

from ...codec import richmat as codec
from . import protocol as p
from .catalog import ACTIONS, ENUM_CODES, FOUR_COLORS, PALETTE, descriptors
from .requests import OPERATIONS, Request

if TYPE_CHECKING:
    from .controller import RichmatAppController

LIGHT_OPERATIONS = {
    "light_timer",
    "light_rgb",
    "strip_rgb",
    "strip_timer",
    "strip_groove",
    "strip_color_mode",
    "strip_breathe",
    "strip_power",
    "therapy_light",
    "therapy_sound",
    "therapy_timer",
    "white_noise",
    "music_source",
}
ALARM_OPERATIONS = {"single_alarm", "cancel_alarm", "repeat_alarm", "delete_alarm", "toggle_alarm"}


def validate(c: RichmatAppController, r: Request) -> None:
    op = r.operation
    if op not in OPERATIONS or op.startswith("sleep_"):
        raise ValueError("Choose a main-bed Richmat app operation")
    if op.startswith("blanket_"):
        if not c.product["selectors"]["0xea47"]:
            raise ValueError("This product has no blanket controls")
        if op not in ("blanket_power", "blanket_settings", "blanket_sleep", "blanket_mite") and (
            not c.blanket.get("7") or c.blanket.get("23")
        ):
            raise ValueError("Blanket must be powered on and mite removal off")
        if op == "blanket_mite" and not c.blanket.get("7"):
            raise ValueError("Blanket must be powered on")
        if r.zone not in (1, 2, 3):
            raise ValueError("Choose blanket zone A, B or both")
        if op in ("blanket_mode", "blanket_temperature"):
            mode = r.mode if op == "blanket_mode" else (1 if c.blanket.get("b") == "cool" else 2)
            if mode not in (1, 2):
                raise ValueError("Blanket mode is cool (1) or warm (2)")
            low, high = (16, 25) if mode == 1 else (25, 55)
            if op == "blanket_temperature" and not low <= r.temperature <= high:
                raise ValueError(f"Choose a temperature from {low} to {high} °C")
        if op == "blanket_delay" and r.enabled and not 1 <= r.value <= 12:
            raise ValueError("Blanket delay must be 1 to 12, as shown in the app")
        if op == "blanket_settings" and r.flags is None:
            raise ValueError("Supply all six settings switches")
        if op == "blanket_sleep":
            s = r.sleep
            if s is None or r.zone not in (1, 2) or s.mode not in (1, 2):
                raise ValueError("Supply a sleep schedule for zone A or B")
            if (
                not 0 <= s.start_hour <= 23
                or not 0 <= s.end_hour <= 23
                or not 0 <= s.start_minute <= 59
                or not 0 <= s.end_minute <= 59
            ):
                raise ValueError("Invalid sleep schedule time")
            if not p.valid_sleep_duration(
                (s.start_hour, s.start_minute), (s.end_hour, s.end_minute)
            ):
                raise ValueError("Sleep schedule must be 5 to less than 16 hours")
            low, high = (16, 25) if s.mode == 1 else (25, 40)
            if (
                any(not low <= v <= high for v in s.temperatures)
                or s.after_mode not in (0, 1)
                or not 1 <= s.delay <= 60
                or any(day not in range(8) for day in s.days)
            ):
                raise ValueError("Invalid blanket sleep temperatures, repeat or after-mode delay")
    if op in ALARM_OPERATIONS:
        if not c.alarm_actions or "alarm" not in c.features:
            raise ValueError("This product requires its clock capability acknowledgement")
        repeat = bool(c.product["selectors"]["0x1001d"])
        if (op in ("repeat_alarm", "delete_alarm", "toggle_alarm")) != repeat:
            raise ValueError("Choose the alarm type this product exposes")
        if not 1 <= r.alarm_id <= 7 or any(day not in range(8) for day in r.weekdays):
            raise ValueError("Choose alarm 1 through 7 and Monday through Sunday or once")
        if op in ("single_alarm", "repeat_alarm"):
            if r.action not in c.alarm_actions or r.when is None:
                raise ValueError("Choose an action from this product alarm menu and a time")
            if op == "repeat_alarm" and not r.weekdays:
                raise ValueError("Choose weekdays or once")
    if op in LIGHT_OPERATIONS:
        feature = (
            "therapy"
            if op.startswith("therapy_") or op in ("white_noise", "music_source")
            else "groove"
            if op.startswith("strip_")
            else None
        )
        if (
            feature
            and feature not in c.features
            or feature is None
            and not c.features.intersection(("strip", "cold_warm"))
        ):
            raise ValueError(
                "This product requires its corresponding light capability acknowledgement"
            )
        if (
            op in ("therapy_sound", "white_noise", "music_source")
            and not c.product["therapy"]["sound_widget_product_gate"]
        ):
            raise ValueError("This product has no sound therapy controls")
        if op == "therapy_timer" and (
            not c.product["therapy"]["timer_widget_product_gate"] or r.value not in (30, 60, 480)
        ):
            raise ValueError("Choose an available therapy timer")
        if op in ("light_timer", "strip_timer") and not 0 <= r.value <= 900:
            raise ValueError("Light timer must be 0 through 900 seconds")
        if (
            any(type(v) is not int or not 0 <= v <= 255 for v in r.rgb)
            or not 10 <= r.opacity <= 100
        ):
            raise ValueError("Invalid RGB channels or opacity")
        if op in ("therapy_light", "therapy_sound", "white_noise") and r.mode not in (0, 1, 2, 3):
            raise ValueError("Choose an app therapy mode")
    if (
        op in ("snore", "get_off_bed", "snore_intervention")
        and "snore" not in c.features
        and not (c.product_key in ("A5RN", "GARM", "AFRN") and descriptors(c.product, "0xe5e9"))
    ):
        raise ValueError("This product has no admitted snore page")
    if op == "toggle_alarm" and not any(row["7"] == r.alarm_id for row in c.alarms):
        raise ValueError("Refresh and choose an observed alarm")
    if op == "detection" and "detection" not in c.features:
        raise ValueError("Detection requires its capability acknowledgement")
    if (
        op == "strip_groove"
        and r.mode not in (1, 2, 3, 4)
        or op == "strip_color_mode"
        and r.mode not in (2, 3, 5)
    ):
        raise ValueError("Choose an app groove/color mode")
    if (
        op == "light_rgb"
        and "cold_warm" not in c.features
        and r.rgb not in (FOUR_COLORS if c.product["palette"] else PALETTE)
    ):
        raise ValueError("Choose one of this product palette colors")
    if op == "snore_intervention" and not 0 <= r.value <= 255:
        raise ValueError("Intervention must fit its one-byte field")
    if op == "music_source" and (r.value, r.mode) != (3, 1):
        raise ValueError("The direct music source control selects local music (3,1)")
    if op == "query":
        if r.query not in p.QUERY and r.query not in ("blanket_sleep_a", "blanket_sleep_b"):
            raise ValueError("Unknown query")
        if (
            r.query == "alarms"
            and not c.alarm_actions
            or r.query.startswith("blanket")
            and not c.product["selectors"]["0xea47"]
            or r.query == "snore"
            and not descriptors(c.product, "0xe5e9")
            or r.query == "sleep_name"
            and c.product["selectors"]["0x10d37"] != "DeviceSleepMonitoringType@cdc971"
        ):
            raise ValueError("This product does not expose the queried feature")
    if op == "usb" and not any(
        ACTIONS[d]["enum"] == ACTIONS["caf651"]["enum"] for d in c.massage_actions
    ):
        raise ValueError("USB switch is not in this product massage menu")
    if op == "demo":
        if (
            r.cycle
            and r.steps
            and all(step.action == "deviceFunctionItemNone" and step.delay == 0 for step in r.steps)
        ):
            raise ValueError("A repeating demo needs a delay or a bed action")
        if not r.steps or any(
            step.action not in ENUM_CODES
            or "Desk" in step.action
            or not 0 <= step.seconds <= 60
            or not 0 <= step.delay <= 600
            for step in r.steps
        ):
            raise ValueError(
                "Demo needs known app actions, 0–60 second holds and 0–600 second delays"
            )


async def execute(c: RichmatAppController, r: Request) -> None:
    op = r.operation
    frames: tuple[bytes, ...]
    if op == "sync":
        frames = p.sync_time(dt_util.now(), dt_util.now())
    elif op == "detection":
        frames = (
            c._generic(
                "deviceFunctionItemSendStartDetection"
                if r.enabled
                else "deviceFunctionItemSendStopDetection"
            ),
        )
    elif op == "toggle_alarm":
        row = next(a for a in c.alarms if a["7"] == r.alarm_id)
        frames = (
            p.repeat_alarm(
                cast(int, row["7"]),
                cast(int, row["f"]),
                cast(int, row["17"]),
                cast(int, row["1f"]),
                cast(int, row["27"]),
                (cast(int, row["2f"]) & 254) | int(r.enabled),
            ),
        )
    elif op == "query":
        if r.query.startswith("blanket_sleep_"):
            frames = (codec.record_20_len(13, 7, 0, (1 if r.query.endswith("a") else 2,)),)
        else:
            frames = (p.QUERY[r.query],)
    elif op in ("single_alarm", "cancel_alarm"):
        if op == "cancel_alarm":
            frames = p.countdown(0, 0)
        else:
            assert r.when is not None
            now = dt_util.now().replace(second=0, microsecond=0)
            target = now.replace(hour=r.when.hour, minute=r.when.minute)
            seconds = int(target.timestamp()) - int(now.timestamp())
            minutes = int((seconds if seconds > 0 else seconds + 86400) / 60)
            c._pending_alarm = {
                "hour": target.hour,
                "minute": target.minute,
                "action": r.action,
                "timestamp": target.timestamp(),
            }
            frames = p.countdown(minutes, ACTIONS[r.action]["short"])
    elif op == "repeat_alarm":
        assert r.when is not None
        frames = (
            p.repeat_alarm(
                r.alarm_id,
                0,
                r.when.hour,
                r.when.minute,
                ACTIONS[r.action]["short"],
                p.repeat_mask(r.weekdays, r.enabled),
            ),
        )
    elif op == "delete_alarm":
        frames = (p.delete_alarm(r.alarm_id),)
    elif op == "light_timer":
        frames = (p.light_timer(r.value),)
        c.local["light_seconds"] = r.value
    elif op == "light_rgb":
        rgb = p.opacity(r.rgb, r.opacity)
        frames = (codec.rgb(*rgb),)
        c.local["light_color"] = list(rgb)
    elif op == "strip_rgb":
        frames = (p.extended(4, 1, *r.rgb),)
    elif op in ("strip_timer", "therapy_timer"):
        value = int(r.value / 60 + 0.5) if op == "strip_timer" else r.value
        frames = (p.extended(4, 2, value >> 8, value & 255),)
    elif op in ("strip_groove", "strip_color_mode"):
        frames = (p.extended(4, 5, 2 if op == "strip_groove" else 1, r.mode),)
    elif op == "strip_breathe":
        frames = (p.extended(4, 6),)
    elif op == "strip_power":
        frames = (p.extended(4, 4, int(r.enabled)),)
    elif op == "therapy_light":
        frames = (
            (p.extended(4, 4, 0),)
            if r.mode == 0
            else (
                p.extended(4, 1, *((255, 140, 20), (255, 220, 120), (255, 255, 255))[r.mode - 1]),
            )
        )
    elif op in ("therapy_sound", "white_noise"):
        if c.product_key in ("LURN", "LQRN"):
            frames = (p.music_source(0 if r.mode == 0 else 2, r.mode),)
        else:
            frames = (p.extended(9, 6, 0) if r.mode == 0 else p.extended(9, 6, 1, r.mode),)
        c.local["therapy_sound"] = r.mode
    elif op == "music_source":
        frames = (p.music_source(r.value, r.mode),)
    elif op in ("snore", "get_off_bed"):
        frames = (p.extended(6, 1 if op == "snore" else 2, int(r.enabled)),)
    elif op == "snore_intervention":
        frames = (codec.frame(110, 19, 0, r.value),)
    elif op == "blanket_power":
        c.blanket["7"] = r.enabled
        frames = (p.extended(13, 1, int(r.enabled)),)
    elif op in ("blanket_mode", "blanket_temperature"):
        if op == "blanket_mode":
            if c.blanket["b"] == ("cool" if r.mode == 1 else "warm"):
                return
            c.blanket.update({"b": "cool" if r.mode == 1 else "warm", "f": 25, "17": 25})
        else:
            for key in ("f", "17") if r.zone == 3 else ("f",) if r.zone == 1 else ("17",):
                c.blanket[key] = r.temperature
        frames = (
            p.extended(
                13,
                5,
                1 if c.blanket["b"] == "cool" else 2,
                cast(int, c.blanket["f"]),
                cast(int, c.blanket["17"]),
            ),
        )
    elif op == "blanket_delay":
        c.blanket.update({"2f": r.enabled, "33": r.value if r.enabled else 0})
        frames = (p.blanket_delay(r.enabled, r.value if r.enabled else 0),)
    elif op == "blanket_mite":
        c.blanket.update(
            {
                "23": r.enabled,
                "b": "warm",
                "f": 65 if r.enabled else 25,
                "17": 65 if r.enabled else 25,
            }
        )
        c._clamp_blanket()
        frames = (p.extended(13, 6, int(r.enabled)),)
    elif op == "blanket_settings":
        assert r.flags is not None
        c.blanket.update(zip(("3f", "3b", "4f", "43", "47", "4b"), r.flags, strict=True))
        frames = (p.extended(13, 8, sum(int(value) << n for n, value in enumerate(r.flags))),)
    elif op == "blanket_sleep":
        s = r.sleep
        assert s is not None
        changed = c.blanket["b"] != ("cool" if s.mode == 1 else "warm")
        frames = (s.frame(r.zone),)
        if changed:
            c.blanket.update({"b": "cool" if s.mode == 1 else "warm", "f": 25, "17": 25})
            frames += (p.extended(13, 5, s.mode, 25, 25),)
        c.local[f"blanket_sleep_{r.zone}"] = {
            "enabled": s.enabled,
            "mode": s.mode,
            "temperatures": s.temperatures,
        }
    elif op == "usb":
        if monotonic() - c._usb_at < 2:
            return
        c._usb_at = monotonic()
        link = c._current_link()
        if not c.local.get("ble"):
            if not await c._send(
                p.function(
                    ACTIONS["caf6d1"]["enum"], ACTIONS["caf6d1"]["short"], c._side(), link.single
                ),
                link,
                c._coordinator.cancel_command,
            ):
                return
            c.local["ble"] = True
            c._publish()
        if await c._wait(0.9, c._coordinator.cancel_command):
            if await c._send(
                p.function(
                    ACTIONS["caf651"]["enum"], ACTIONS["caf651"]["short"], c._side(), link.single
                ),
                link,
                c._coordinator.cancel_command,
            ):
                c.local["usb"] = not bool(c.local.get("usb"))
                c._publish()
        return
    elif op == "demo":
        c.local["demo"] = [
            {"action": s.action, "sustain": s.sustain, "seconds": s.seconds, "delay": s.delay}
            for s in r.steps
        ]
        c.local["demo_running"] = True
        c.local["demo_step"] = -1
        c.local["demo_cycle"] = r.cycle
        c._publish()
        link = c._current_link()
        side = c._side()
        cancel = c._coordinator.cancel_command
        try:
            if not await c._wait(0.5, cancel):
                return
            while True:
                for index, step in enumerate(r.steps):
                    c.local["demo_step"] = index
                    c._publish()
                    frame = p.function(step.action, ENUM_CODES[step.action], side, link.single)
                    if step.action != "deviceFunctionItemNone":
                        if step.sustain:
                            for _ in range(max(1, step.seconds * 10)):
                                if not await c._wait(0.1, cancel) or not await c._send(
                                    frame, link, cancel
                                ):
                                    return
                            await c._stop_side(link, side)
                        elif not await c._send(frame, link, cancel):
                            return
                    if not await c._wait(step.delay, cancel):
                        return
                if not r.cycle:
                    break
        finally:
            try:
                await c._stop_side(link, side)
            finally:
                c.local["demo_running"] = False
                c.local["demo_step"] = -1
                c._publish()
        return
    else:
        raise ValueError("Unsupported Richmat operation")
    for frame in frames:
        if not await c._send(frame, c._current_link(), c._coordinator.cancel_command):
            return
    if op == "delete_alarm":
        # The completed write invalidates this observation, without claiming an ACK.
        c.alarms[:] = [alarm for alarm in c.alarms if alarm["7"] != r.alarm_id]
    c._publish()
