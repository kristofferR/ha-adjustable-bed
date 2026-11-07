"""Direct BLE controllers for the five explicit RUF/Richmat app catalogs."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from ..row061_profiles import Field, fields, profiles
from ..row061_protocol import AlarmRequest
from .base import (
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .richmat_mh import (
    ANGLE_KEYS,
    INTENSITY_KEYS,
    LIGHT_TIMER_MINUTES_KEY,
    Axis,
    Control,
    Features,
    Model,
    RichmatMhController,
    SessionFlags,
    _invoke,
)
from .richmat_mh_protocol import (
    INIT_VER0,
    INIT_VER1,
    MOTOR_MODE_BITS,
    TX_DETECTION,
    TX_EXIT_ONE_MIN,
    TX_MOTOR_MODE,
    TX_QUERY_MASSAGE,
    TX_VERSION,
    Classifier,
    Event,
    angle_frame,
    control_frame,
    finalize,
    massage_intensity_frame,
    mattress_frame,
    motor_mode_frame,
    query_frame,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

VER2 = "0002"
MUSIC_QUERY = "6e15010185"
INIT_VER2 = (
    TX_MOTOR_MODE,
    "6e9a300139",
    TX_QUERY_MASSAGE,
    "6e08010178",
    "6e2008010300009a",
    "6e2008010500009c",
    "6e20080b020000a3",
    "6e20080201000099",
)


def _map(value: Field) -> dict[str, Field]:
    return value if isinstance(value, dict) else {}


def _ints(value: Field) -> tuple[int, ...]:
    return tuple(int(str(v), 16) for v in value) if isinstance(value, list) else ()


def _feature(app: str, model: str, key: str) -> Field:
    return fields(app, model.removesuffix("_mattress")).get(key)


def _entity_map(app: str, model: str, name: str, extended: bool = False) -> dict[str, Field]:
    return _map(_feature(app, model, name + ("2" if extended else "")))


def _alarm_entries(alarm_map: dict[str, Field]) -> tuple[tuple[str | None, int], ...]:
    return tuple(
        (str(e.get("name")) if e.get("name") else None, int(str(e["code"]), 16))
        for value in alarm_map.values()
        for item in (value if isinstance(value, list) else [value])
        if (e := _map(item)).get("code") and re.fullmatch("[0-9a-fA-F]{2}", str(e["code"]))
    )


def load_app_model(app: str, model_id: str) -> Model | None:
    """Read one app's own bindings; a normal mattress is an explicit setup choice."""
    base_id = model_id.removesuffix("_mattress")
    row = profiles(app).get(base_id)
    if row is None or (model_id != base_id and app not in ("wsilver2", "americanstar", "tx")):
        return None
    f = row["fields"]
    alarm_call = _alarm_entries(_map(f.get("alarmMap")))
    feature = Features(
        bool(f.get("hasLed")),
        bool(f.get("hasBtnLed")),
        bool(f.get("hasAroma")),
        bool(f.get("hasSnore")),
        bool(f.get("hasMusic")),
        bool(f.get("hasSleep")),
        str(f["sleepType"]) if f.get("sleepType") else None,
        bool(f.get("hasSpeech")),
        bool(f.get("hasSmartSetLock")),
        bool(f.get("hasSmartLightLock")),
        bool(f.get("isNewAlarm", f.get("newAlarm"))),
        _ints(f.get("alarmList")),
        _ints(f.get("snoreList")),
        alarm_call,
        (),
        (),
        (),
        bool(f.get("motorMap")),
    )
    return Model(app, model_id, tuple(Control(*c) for c in row["controls"]), feature)


class AppClassifier(Classifier):
    """The app-specific additions to the legacy classifier, with bounded input guards."""

    def __init__(self, app: str) -> None:
        super().__init__("revive")
        self.app = app
        self.music = False

    def feed(self, data: bytes) -> list[Event]:
        buf = self.buffer + data.hex()
        if self.app in ("ruf", "bailey2", "americanstar"):
            if buf.startswith("6e9000") and buf.endswith("ff") and len(buf) >= 10:
                version = {"01": "0001", "02": VER2}.get(buf[6:8])
                if version:
                    self.buffer = ""
                    return [Event("version", version)]
        if buf.startswith("6e90b") or (self.music and buf.startswith("6e90d")):
            self.music = True
            self.buffer = ""
            return [Event("music", buf[i : i + 10]) for i in range(0, len(buf) - 9, 10)]
        if buf.startswith("6e20"):
            # 6e20 uses the declared whole-frame length; never read a partial header.
            if len(buf) < 6:
                self.buffer = buf
                return []
            size = int(buf[4:6], 16)
            if len(buf) < size * 2:
                self.buffer = buf
                return []
            self.buffer = ""
            frame = bytes.fromhex(buf)
            if len(frame) != size or size < 8:
                return []
            return [Event("extended", buf)]
        return super().feed(data)


def waist_init(frame: str) -> dict[str, int]:
    """Warmth routes by its keys; pressure and duration retain their reported keys."""
    raw = bytes.fromhex(frame)
    values: dict[str, int] = {"mode": raw[5]}
    keys = {
        2: "left_heat",
        3: "right_heat",
        4: "both_heat",
        5: "left_pressure",
        6: "right_pressure",
        7: "both_pressure",
        8: "left_duration",
        9: "right_duration",
        10: "both_duration",
    }
    for offset in range(6, 24, 2):
        if key := keys.get(raw[offset]):
            values[key] = raw[offset + 1]
    return values


class Row061Controller(RichmatMhController):
    """One physical receiver, explicit app/model, and response-gated extra controls."""

    _app_groups = dict.fromkeys(("ruf", "wsilver2", "americanstar", "bailey2", "tx"), "revive")

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str,
        protocol_variant: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(
            coordinator, app=app, protocol_variant=protocol_variant, device_name=device_name
        )
        self._classifier = AppClassifier(app)
        self._normal_selected = bool(protocol_variant and protocol_variant.endswith("_mattress"))
        if self._stored_snapshot.get("app") != app:
            self._stored_snapshot = {}
            self._version, self._call_page = "0000", False
            self._dev, self._waist, self._detection = {}, False, False
        self._normal_ready = (
            bool(self._stored_snapshot.get("normal_ready")) and self._normal_selected
        )
        self._normal_values: dict[tuple[int, int], int] = {}
        self._ranges: dict[int, tuple[int, int]] = {}
        self._calendar_alarms: dict[int, dict[str, int]] = {}

    def capability_snapshot(self):
        snapshot = super().capability_snapshot()
        if snapshot is not None:
            snapshot.update(app=self._app, normal_ready=self._normal_ready)
        return snapshot

    @property
    def route(self) -> str:
        if self._app == "ruf":
            return "L"
        if self._version == VER2 and self._call_page:
            return (
                "D"
                if self.model
                and self.model.model_id.removesuffix("_mattress") in ("2i", "3i", "4i")
                else "C"
            )
        return "C" if self._version == "0001" and self._call_page else "L"

    def _controls(self) -> tuple[Control, ...]:
        return tuple(c for c in self.model.controls if c.route == self.route) if self.model else ()

    def _axes(self) -> tuple[Axis, ...]:
        pairs: dict[str, dict[str, Control]] = {}
        for c in self._controls():
            if c.area == "motor":
                pairs.setdefault(c.group, {})[c.kind] = c
        axes = []
        for group, pair in pairs.items():
            if "up" not in pair or "down" not in pair:
                continue
            key = re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_")
            key = {
                "back": "head",
                "foot": "feet",
                "back_foot_both": "head_feet",
                "head_foot_both": "head_feet",
            }.get(key, key)
            translation = {
                "head": "back",
                "feet": "feet",
                "pillow": "pillow",
                "lumbar": "lumbar",
                "head_feet": "head_feet",
            }.get(key, "richmat_mh_action")
            axes.append(Axis(key, translation, pair["up"], pair["down"]))
        return tuple(axes)

    @property
    def _features(self) -> Features | None:
        result = super()._features
        if result and self.route == "D":
            return result._replace(alarm_call=_alarm_entries(self._map("alarmMap")))
        return result

    def _map(self, name: str) -> dict[str, Field]:
        return (
            _entity_map(self._app, self.model.model_id, name, self.route == "D")
            if self.model
            else {}
        )

    @property
    def motor_mode_options(self) -> tuple[str, ...]:
        if self.route == "L" or not self.model:
            return ()
        modes = _map(_feature(self._app, self.model.model_id, "motorModeMap"))
        values = modes.get("20")
        names = {"01": "mode1", "02": "mode2", "03": "mode3", "11": "left", "12": "right"}
        return (
            tuple(names[str(v)] for v in values if str(v) in names)
            if isinstance(values, list)
            else ()
        )

    def _angles(self) -> tuple[tuple[int, str, int, int, int], ...]:
        if self.route == "L":
            return ()
        rows = []
        for value in self._map("motorMap").values():
            e = _map(value)
            r = _map(e.get("angleRange"))
            code = e.get("codeCall")
            if not r or not isinstance(code, str):
                continue
            # Legacy binToHex weights each decimal digit; the extended format uses its raw byte.
            bits = (
                int(code, 16)
                if self.route == "D"
                else sum(int(c) << i for i, c in enumerate(reversed(code)))
            )
            name = str(e.get("name", ""))
            if name.lower() not in ANGLE_KEYS:
                continue
            low, high = self._ranges.get(
                bits, (int(str(r.get("min", 0))), int(str(r.get("max", 0))))
            )
            rows.append((bits, name, low, high, int(str(r.get("offset", 0)))))
        return tuple(rows)

    def _intensities(self) -> tuple[tuple[str, str | None, int, int], ...]:
        if self.route == "L":
            return ()
        rows = []
        for value in self._map("massageMap").values():
            for item in value if isinstance(value, list) else [value]:
                e = _map(item)
                r = _map(e.get("msgRange"))
                if not r:
                    continue
                zone = {"4c": "head", "4e": "foot"}.get(str(e.get("code", "")).lower())
                if zone:
                    rows.append(
                        (
                            zone,
                            str(e.get("name", zone)),
                            int(str(r.get("min", 0))),
                            int(str(r.get("max", 0))),
                        )
                    )
        return tuple(rows)

    def _light_page(self):
        if self._app == "ruf":
            return None
        if self.route != "L":
            return "led" if self._dev.get("led") else None
        f = self._features
        if not f:
            return None
        # Each constructor's page requires the corresponding device reply.
        if f.led and self._dev.get("led"):
            return "led"
        return "btn_led" if f.btn_led and self._dev.get("led") else None

    def _snore_options(self) -> tuple[str, ...]:
        from .richmat_mh import SNORE_OPTIONS

        f = self._features
        if self.route != "L" or not f or not f.snore or not self.model:
            return ()
        if not self._dev.get("snore") and self.model.model_id.removesuffix("_mattress") not in (
            "a5rn",
            "garm",
            "afrn",
        ):
            return ()
        options = tuple(SNORE_OPTIONS[c] for c in f.snore_list if c in SNORE_OPTIONS)
        return ("off", *options) if options else ()

    def _smart_light_lock(self) -> bool:
        return False  # The declared flag has no reachable sending listener in these five apps.

    def _detection_page(self) -> bool:
        return self._detection and (self.route == "L" or self._app == "ruf")

    def _smart_set_lock(self) -> bool:
        return self._app != "ruf" and super()._smart_set_lock()

    def _alarm_page(self) -> bool:
        return self._app != "ruf" and super()._alarm_page()

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = super().controller_number_specs
        if self._light_page() != "btn_led":
            return specs
        return tuple(s for s in specs if s.key != "richmat_mh_light_timer") + (
            ControllerNumberSpec(
                LIGHT_TIMER_MINUTES_KEY,
                LIGHT_TIMER_MINUTES_KEY,
                LIGHT_TIMER_MINUTES_KEY,
                0,
                15,
                1,
                lambda ctrl, v: _invoke(ctrl, "write_light_timer", int(v) * 60, int(v)),
                native_unit_of_measurement="min",
            ),
        )

    async def tap(self, code: int) -> None:
        control = next((c for c in self._controls() if c.code == code), None)
        if control is None:
            raise ValueError("This command is not on the selected app/model page")
        try:
            await self.write_command(
                control_frame(code),
                repeat_count=self._coordinator.motor_pulse_count if control.keep_ms else 1,
                repeat_delay_ms=control.keep_ms or 100,
            )
        finally:
            if self._app == "bailey2" and not control.keep_ms:
                await self._release_after_once()
            else:
                await self._release()

    async def _release_after_once(self) -> None:
        # Bailey's natural ONCE completion uses 100ms, distinct from KEEP's 120ms.
        try:
            await asyncio.sleep(0.1)
        finally:
            from .richmat_mh_protocol import stop_frame

            await self.write_command(stop_frame(), cancel_event=asyncio.Event())

    async def _release(self) -> None:
        if self._app == "ruf":
            from .richmat_mh_protocol import stop_frame

            await self.write_command(stop_frame(), cancel_event=asyncio.Event())
        else:
            await super()._release()

    async def _run_session_setup(self) -> None:
        pending = self._pending = SessionFlags()
        self._normal_ready = False
        self._normal_values.clear()
        try:
            await asyncio.sleep(0.1 if self._app in ("ruf", "bailey2", "americanstar") else 0.3)
            await self._write_query(TX_VERSION)
            await asyncio.sleep(0.3)
            if pending.version != VER2:
                self._classifier.rx_type = "INIT"
            if pending.version == VER2 and self._app in ("ruf", "bailey2", "americanstar"):
                tasks, delay = INIT_VER2, 0.3
            elif pending.version == "0001":
                tasks = INIT_VER1 + (() if self._app == "tx" else (MUSIC_QUERY,))
                delay = 0.4
            elif self._app == "wsilver2":
                tasks, delay = (TX_EXIT_ONE_MIN, TX_DETECTION), 0.3
            else:
                tasks, delay = INIT_VER0 + (() if self._app == "tx" else (MUSIC_QUERY,)), 0.3
            for literal in tasks:
                await self._write_query(literal)
                await asyncio.sleep(delay)
        finally:
            if self._pending is pending:
                self._pending = None
        self._version, self._call_page = pending.version, pending.call_page
        self._dev, self._waist, self._detection = pending.dev, pending.waist, pending.detection
        self._persist_snapshot()

    def _apply(self, event: Event) -> None:
        if self._pending is None and event.kind in (
            "version",
            "init",
            "waist_init",
            "detection_available",
        ):
            pending = self._pending = SessionFlags(
                self._version, self._call_page, dict(self._dev), self._detection, self._waist
            )
            try:
                self._apply(event)
            finally:
                self._pending = None
            self._version, self._call_page = pending.version, pending.call_page
            self._dev, self._detection, self._waist = pending.dev, pending.detection, pending.waist
            self._persist_snapshot()
            return
        if event.kind == "version":
            if self._pending:
                self._pending.version = event.data
            return
        if event.kind == "waist_init":
            if self._pending:
                self._pending.waist = True
            self._apply_waist(waist_init(event.data))
            # Alarm begins at byte24: command, repeat, side, intensity, hour, minute.
            from .richmat_mh_protocol import parse_waist_piece

            alarm = finalize(bytes.fromhex("5e03" + event.data[48:60] + "00"))
            self._apply_waist(parse_waist_piece(alarm.hex()))
            return
        if event.kind == "mattress_init":
            self._normal_init(bytes.fromhex(event.data))
            self._persist_snapshot()
            return
        if event.kind == "mattress":
            self._normal_reply(bytes.fromhex(event.data))
            return
        if event.kind == "music":
            raw = bytes.fromhex(event.data)
            values: dict[str, object] = {}
            if raw[2] >> 4 == 0x0B:
                bits = f"{((raw[2] & 15) << 8) | raw[3]:012b}"
                values = {
                    name: bits[index] == "1"
                    for index, name in enumerate(("switch", "play", "mode", "on"), 3)
                }
            elif raw[2] in (0xD1, 0xD2):
                values["volume" if raw[2] == 0xD1 else "intensity"] = (
                    raw[3] - 256 if raw[3] > 127 else raw[3]
                )
            self.forward_controller_state_updates(
                {"row061_music_status": "reported", "row061_music_values": values}
            )
            return
        if event.kind == "extended":
            self._extended(bytes.fromhex(event.data))
            return
        super()._apply(event)

    def _apply_init(self, rx: str) -> None:
        # RUF uses the shared parser/cache but never mounts generic control pages.
        super()._apply_init(rx)
        if self._pending and self._pending.version == VER2:
            self._pending.call_page = True

    def _extended(self, frame: bytes) -> None:
        device, prop = frame[3:5]
        if self._pending and self._pending.version == VER2:
            self._pending.call_page = True
        if device == 1 and prop == 3:
            for offset in (6, 9) if len(frame) == 13 else (6,):
                if offset + 2 < len(frame) - 1:
                    angle = frame[offset + 2]
                    if self._app == "ruf":
                        angle = frame[offset + 1]
                    self._apply_angle(frame[offset], str(angle))
        elif device == 1 and prop == 5 and len(frame) == 17:
            for offset in (6, 11):
                self._ranges[frame[offset]] = (0, frame[offset + 4])
        elif device == 1 and prop == 4:
            self._apply_motor_mode(format(frame[6] + 1, "02b"))
        elif device == 0x0B and prop == 2:
            self._apply_motor_mode(format(frame[7] + 1, "02b"))
        elif device == 5 and prop == 1 and len(frame) >= 13 and frame[5] in (2, 3):
            try:
                slot, bed = int(f"{frame[6]:02x}"), int(f"{frame[7]:02x}")
            except ValueError:
                return
            self._calendar_alarms[slot] = {
                "bed": bed,
                "hour": frame[8],
                "minute": frame[9],
                "mode": frame[10],
                "week": frame[11],
            }
            self.forward_controller_state_updates(
                {
                    "row061_calendar_alarms": dict(self._calendar_alarms),
                    "row061_calendar_alarm_count": len(self._calendar_alarms),
                }
            )
        elif device == 2 and prop == 1 and len(frame) in (9, 11):
            values = dict(self._intensity)
            for offset in (6, 8) if len(frame) == 11 else (6,):
                zone = {1: "head", 2: "foot"}.get(frame[offset])
                if zone:
                    values[zone] = frame[offset + 1] if frame[offset + 1] <= 7 else 1
            self._apply_intensity(values)

    async def set_angle(self, bits: int, angle: int) -> None:
        spec = next((x for x in self._angles() if x[0] == bits), None)
        if spec is None or not spec[2] <= angle <= spec[3]:
            raise ValueError("Angle is outside the selected model's reported range")
        await asyncio.sleep(0.1)
        frame = (
            finalize([0x6E, 0x20, 0x0A, 1, 3, 1, bits, 0, abs(angle), 0])
            if self.route == "D"
            else angle_frame(bits, angle)
        )
        await self.write_command(frame)

    async def set_motor_mode(self, option: str) -> None:
        if option not in self.motor_mode_options:
            raise ValueError("Mode is not offered by this model")
        name = {"left": "LEFT", "right": "RIGHT"}.get(option, option.capitalize())
        bits = MOTOR_MODE_BITS[name]
        frame = (
            finalize([0x6E, 0x20, 9, 0x0B, 2, 1, 0, bits - 1, 0])
            if self.route == "D"
            else motor_mode_frame(bits)
        )
        await self.write_command(frame)
        self._motor_mode = option
        self.forward_controller_state_update("richmat_mh_motor_mode", option)

    async def write_massage_intensity(self, zone: str, value: int) -> None:
        spec = next((x for x in self._intensities() if x[0] == zone), None)
        if spec is None or not spec[2] <= value <= spec[3]:
            raise ValueError("Intensity is outside the selected model's range")
        values = {**self._intensity, zone: value}
        frame = (
            finalize([0x6E, 0x20, 9, 2, 1, 1, 1 if zone == "head" else 2, value, 0])
            if self.route == "D"
            else massage_intensity_frame(values["head"], values["foot"])
        )
        await self.write_command(frame)
        self._intensity = values
        self.forward_controller_state_update(INTENSITY_KEYS[zone], value)

    # The normal mattress's saved Boolean is represented by an explicit HA variant.
    # A fresh model or a waist reply alone never grants these controls.
    def _normal_init(self, raw: bytes) -> None:
        version = self._pending.version if self._pending else self._version
        if not self._normal_selected or version in ("0001", VER2) or len(raw) != 28 or raw[3] != 1:
            return
        body = raw[2:-1]
        side = body[17]
        if side not in (1, 2):
            return
        self._normal_ready = True
        for offset in range(0, 20, 2):
            self._normal_values[side, body[offset]] = body[offset + 1]
        if body[20] == 0x0B:
            self._normal_reply(finalize([0x5E, side, *body[20:25], 0]))
        self._publish_normal()

    def _normal_reply(self, raw: bytes) -> None:
        if not self._normal_ready or len(raw) not in (5, 8) or raw[1] not in (1, 2):
            return
        self._normal_values[raw[1], raw[2]] = raw[3]
        if raw[2] == 0x0B:
            key = f"row061_mattress_{'left' if raw[1] == 1 else 'right'}_alarm"
            self.forward_controller_state_update(
                key, f"{raw[5]:02d}:{raw[6]:02d}" if len(raw) == 8 and raw[3] else "off"
            )
        self._publish_normal()

    def _publish_normal(self) -> None:
        from ..row061_protocol import NORMAL_SETTINGS

        values: dict[str, object] = {}
        for side, side_no in (("left", 1), ("right", 2)):
            for setting, (code, options) in NORMAL_SETTINGS.items():
                raw = self._normal_values.get((side_no, code))
                values[f"row061_mattress_{side}_{setting}"] = next(
                    (name for name, value in options.items() if value == raw), None
                )
        self.forward_controller_state_updates(values)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = list(super().controller_state_sensor_specs)
        if self._app != "ruf":
            specs.append(
                ControllerStateSensorSpec(
                    "row061_music_status",
                    "row061_music_status",
                    "row061_music_status",
                    "mdi:music",
                    attribute_keys=("row061_music_values",),
                )
            )
        if self._calendar_page():
            specs.append(
                ControllerStateSensorSpec(
                    "row061_calendar_alarms",
                    "row061_calendar_alarms",
                    "row061_calendar_alarm_count",
                    "mdi:alarm",
                    attribute_keys=("row061_calendar_alarms",),
                )
            )
        if self._normal_ready:
            for side in ("left", "right"):
                key = f"row061_mattress_{side}_alarm"
                specs.append(ControllerStateSensorSpec(key, key, key, "mdi:alarm"))
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        from ..row061_protocol import NORMAL_SETTINGS

        specs = list(super().controller_select_specs)
        if self._normal_ready:
            for side in ("left", "right"):
                for setting, (_code, options) in NORMAL_SETTINGS.items():
                    key = f"row061_mattress_{side}_{setting}"
                    specs.append(
                        ControllerSelectSpec(
                            key,
                            key,
                            key,
                            tuple(options),
                            lambda ctrl, option, s=side, f=setting: _invoke(
                                ctrl, "normal_setting", s, f, option
                            ),
                        )
                    )
        return tuple(specs)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = super().motor_control_specs
        if not self._normal_ready:
            return specs
        return specs + tuple(
            MotorControlSpec(
                key=f"row061_mattress_{side}_pillow",
                translation_key=f"row061_mattress_{side}_pillow",
                open_fn=lambda ctrl, s=side: _invoke(ctrl, "normal_pillow", s, 1),
                close_fn=lambda ctrl, s=side: _invoke(ctrl, "normal_pillow", s, 2),
                stop_fn=lambda ctrl, s=side: _invoke(ctrl, "normal_pillow_stop", s),
                scheduler_resource="*",
            )
            for side in ("left", "right")
        )

    async def normal_setting(self, side: str, setting: str, option: str) -> None:
        from ..row061_protocol import NORMAL_SETTINGS

        spec = NORMAL_SETTINGS.get(setting)
        if (
            not self._normal_ready
            or side not in ("left", "right")
            or spec is None
            or option not in spec[1]
        ):
            raise ValueError("The selected mattress has not reported this setting")
        await self.write_command(
            mattress_frame(1 if side == "left" else 2, spec[0], spec[1][option])
        )

    async def normal_pillow_stop(self, side: str) -> None:
        if not self._normal_ready or side not in ("left", "right"):
            raise ValueError("The selected mattress has no initialized pillow")
        await self.write_command(
            mattress_frame(1 if side == "left" else 2, 6, 0), cancel_event=asyncio.Event()
        )

    async def normal_pillow(self, side: str, direction: int) -> None:
        if not self._normal_ready or side not in ("left", "right") or direction not in (1, 2):
            raise ValueError("The selected mattress has no initialized pillow")
        try:
            await self.write_command(mattress_frame(1 if side == "left" else 2, 6, direction))
            # One DOWN packet, no refresh. HA bounds the user's hold by its configured pulse window.
            count, delay = self.motor_pulse_settings()
            try:
                await asyncio.wait_for(
                    self._coordinator.cancel_command.wait(), count * delay / 1000
                )
            except TimeoutError:
                pass
        finally:
            await self.normal_pillow_stop(side)

    @property
    def supports_row061_alarms(self) -> bool:
        return self._normal_ready or self._calendar_page()

    def _calendar_page(self) -> bool:
        return bool(
            self.model
            and self._app in ("wsilver2", "americanstar", "bailey2", "tx")
            and _feature(self._app, self.model.model_id, "hasNewAlarm")
            and _feature(self._app, self.model.model_id, "alarmList")
        )

    def validate_row061_alarm(self, request: AlarmRequest) -> None:
        request.validate()
        if request.family == "calendar" and not request.delete and self.model:
            if request.mode not in _ints(_feature(self._app, self.model.model_id, "alarmList")):
                raise ValueError("Choose an alarm position from this model's alarm list")
        if request.family == "mattress" and not self._normal_ready:
            raise ValueError(
                "Select the normal mattress variant and obtain its powered initialization first"
            )
        if request.family == "calendar" and not self._calendar_page():
            raise ValueError("This model has not reported its calendar alarm capability")

    async def row061_alarm(self, request: AlarmRequest) -> None:
        from homeassistant.util import dt as dt_util

        from ..row061_protocol import alarm_frame, calendar_clock

        self.validate_row061_alarm(request)
        now = dt_util.now()
        if request.family == "calendar":
            await self.write_command(query_frame("6e2008050100009c"))
            for frame in calendar_clock(now):
                await asyncio.sleep(0.2)
                await self.write_command(frame)
        if request.family == "calendar":
            from dataclasses import replace

            request = replace(
                request, bed=self._calendar_alarms.get(request.slot, {}).get("bed", 0)
            )
        await self.write_command(alarm_frame(request, now))
        if request.family == "calendar":
            await asyncio.sleep(0.3)
            await self.write_command(query_frame("6e2008050100009c"))

    async def write_light_timer(self, seconds: int, shown: int) -> None:
        await super().write_light_timer(seconds, shown)
        if self._light_page() == "btn_led":
            self.forward_controller_state_update(LIGHT_TIMER_MINUTES_KEY, shown)

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._normal_ready = False
        self._normal_values.clear()
        self._ranges.clear()
