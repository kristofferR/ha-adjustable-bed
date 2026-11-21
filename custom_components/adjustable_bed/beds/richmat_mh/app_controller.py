"""App-specific policies extending the shared Richmat MH family runtime."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from ...codec import richmat as codec
from ...command_scheduler import current_command_context
from ...const import RICHMAT_MH_APP_CATALOGS
from ...controller_state import StateKey
from ...execution import HOLD_CEILING_MS
from ...profiles.richmat_mh_apps import APPS
from ..base import BedController
from ..builder import BuildContext
from ..catalog_buttons import unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..richmat.labels import preset_name
from ..ruf_richmat.controller import RufRichmatController, waist_init
from . import protocol
from .app_catalog import catalog, details
from .controller import (
    DETECTION_KEY,
    LIGHT_TIMER_KEY,
    SNORE_KEY,
    SNORE_OPTIONS,
    Control,
    Features,
    RichmatMhController,
    SessionFlags,
    _invoke,
)

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

DIAGNOSTIC_ROWS: Final = StateKey[list[dict[str, str]]]("richmat_mh_diagnostic_rows")
DIAGNOSTIC_PROGRESS: Final = StateKey[int]("richmat_mh_diagnostic_progress")
MATTRESS_FRAME: Final = StateKey[str]("richmat_mh_mattress_frame")
MATTRESS_AVAILABLE: Final = StateKey[bool]("richmat_mh_mattress_available")
WAIST_AVAILABLE: Final = StateKey[bool]("richmat_mh_waist_available")
LAST_REPLY: Final = StateKey[str]("richmat_mh_last_reply")
_COMPONENTS: Final = {
    ("3", "1"): "motor1", ("3", "2"): "motor2", ("3", "3"): "motor3",
    ("3", "4"): "motor4", ("3", "5"): "motor5",
    ("4", "1"): "massager1", ("4", "2"): "massager2",
    ("5", "1"): "under_bed_light1", ("6", "1"): "usb1",
}
_COMPONENT_LABELS: Final = {
    "motor1": ("f_motor1", "Back motor"), "motor2": ("f_motor2", "Foot motor"),
    "motor3": ("f_motor3", "Pillow motor"), "motor4": ("f_motor4", "Lumbar motor"),
    "motor5": ("f_motor5", "Lumbar2 motor"),
    "massager1": ("f_massager1", "Back Massager"),
    "massager2": ("f_massager2", "Foot Massager"),
    "under_bed_light1": ("f_ubl1", "UBL"), "usb1": ("f_usb1", "USB"),
}
_RESULT_LABELS: Final = {
    "0": "Error", "1": "Pass", "2": "Control box error", "3": "Device is not plugged in",
}
_NORMAL_SETTINGS: Final = {
    "pressure": (1, {"off": 0, "low": 1, "medium": 2, "high": 3}),
    "heat_level": (2, {"off": 0, "low": 1, "medium": 2, "high": 3}),
    "heat_duration": (3, {"off": 0, "2_hours": 1, "4_hours": 2, "6_hours": 3, "8_hours": 4}),
    "heat_area": (4, {"off": 0, "back": 1, "legs": 2, "both": 3}),
    "mode": (5, {"off": 0, "sleep": 1, "wake": 2, "decompress": 3, "leg": 4}),
    "pillow_duration": (7, {"off": 0, "20_minutes": 1, "40_minutes": 2, "60_minutes": 3}),
    "sleep_duration": (9, {"15_minutes": 1, "20_minutes": 2, "30_minutes": 3}),
}



# Button names as Home Assistant shows them, read once when the module loads.
_BUTTON_NAMES: Final[dict[str, dict[str, str]]] = json.loads(
    (Path(__file__).parents[2] / "translations" / "en.json").read_text(encoding="utf-8")
)["entity"]["button"]


def _shown_name(spec: ControllerButtonSpec) -> str:
    """The name a button shows: its translated name, or the name it was given."""
    template = _BUTTON_NAMES.get(spec.translation_key or "", {}).get("name")
    if template is None:
        return spec.name
    return template.format(**(spec.translation_placeholders or {}))

class RichmatMHAppClassifier(protocol.Classifier):
    """Keep the accepted app's coalescing and diagnostic boundaries separate."""

    def __init__(self, app: str) -> None:
        super().__init__("revive")
        self.app = app

    def _bed(self, buf: str) -> None:
        super()._bed(buf)
        if not APPS[self.app].diagnostic_results:
            self.events = [
                protocol.Event("init", event.data) if event.kind == "detection_result" else event
                for event in self.events
            ]

    def _mattress(self, buf: str) -> None:
        if self.app == "nisco" and buf.startswith("5e03") and len(buf) == 30:
            for offset in (0, 10, 20):
                piece = buf[offset:offset + 10]
                if protocol.chk_sum(piece):
                    self.events.append(protocol.Event("waist", piece))
            self.buffer = ""
            return
        if buf.startswith("5e03") and len(buf) // 2 in (15, 18) and len(buf) // 2 not in APPS[self.app].waist_combined_lengths:
            self.buffer = ""  # HA fence for a combined form this app does not establish.
            return
        super()._mattress(buf)


class RichmatMHAppController(RufRichmatController):
    """Reuse family controls and mattress entities with two independent catalogs."""

    _app_groups: Mapping[str, protocol.AppGroup] = dict[str, protocol.AppGroup].fromkeys(APPS, "revive")
    _wire_profiles = {app: profile.wire for app, profile in APPS.items()}
    normal_requires_legacy_version = False

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, app: str,
        protocol_variant: str | None = None, device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator, app=app, protocol_variant=protocol_variant, device_name=device_name)
        self._classifier = RichmatMHAppClassifier(app)
        stored_mode = self._stored_snapshot.get("transmit_mode")
        self._transmit_mode = stored_mode if type(stored_mode) is int and stored_mode in (0, 1, 2) else 0
        self._session_generation = 0
        self._owner_client: BleakClient | None = None
        self._delayed_consumers: set[asyncio.Task[None]] = set()
        self._diagnostic_rows: list[dict[str, str]] = []
        surface = details(app, self.model.model_id) if self.model else None
        self._mode_groups = surface.mode_groups if surface else {}
        self._remote_long_codes = surface.remote_long if surface else ()
        self._speech = dict(surface.speech) if surface else {}
        stored_group = str(self._stored_snapshot.get("group_type") or "SINGLE")
        self._group_type = stored_group if stored_group in self._mode_groups else None
        if not APPS[app].normal_mattress:
            self._waist = self._normal_ready = False

    @property
    def route(self) -> str:
        return "C" if self._version == "0001" and self._call_page else "L"

    @property
    def _features(self) -> Features | None:
        return self.model.features if self.model else None

    @property
    def normal_settings(self) -> dict[str, tuple[int, dict[str, int]]]:
        return _NORMAL_SETTINGS

    @property
    def waist_fields(self) -> Mapping[str, Mapping[str, int]]:
        return {
            "heat": protocol.WAIST_HEAT,
            "pressure": {"off": 0, **protocol.WAIST_PRESSURE},
            "duration": {"off": 0, **protocol.WAIST_DURATION},
        }

    def _angles(self) -> tuple[tuple[int, str, int, int, int], ...]:
        return RichmatMhController._angles(self)

    def _intensities(self) -> tuple[tuple[str, str | None, int, int], ...]:
        return RichmatMhController._intensities(self)

    @property
    def motor_mode_options(self) -> tuple[str, ...]:
        if self.route != "C" or self._group_type is None:
            return ()
        return tuple(name.lower() for name in self._mode_groups.get(self._group_type, ()))

    def capability_snapshot(self) -> dict[str, object] | None:
        snapshot = super().capability_snapshot()
        if snapshot is not None:
            snapshot["transmit_mode"] = self._transmit_mode
            snapshot["group_type"] = self._group_type
        return snapshot

    def _light_page(self) -> Literal["led", "btn_led"] | None:
        if self.route == "C":
            return "led" if self._dev.get("led") else None
        f = self._features
        if f is None or not self._dev.get("led"):
            return None
        return "led" if f.led else "btn_led" if f.btn_led else None

    def _snore_options(self) -> tuple[str, ...]:
        f = self._features
        if self.route != "L" or f is None or not f.snore:
            return ()
        if not self._dev.get("snore") and not (self.app == "nisco" and self.model and self.model.model_id == "garm"):
            return ()
        return ("off", *(SNORE_OPTIONS[code] for code in f.snore_list if code in SNORE_OPTIONS))

    def _smart_light_lock(self) -> bool:
        return self.app == "mlily_supreme" and bool(self.model and self.model.model_id.removesuffix("_mattress") == "cfrm") and self._light_page() is not None

    def _detection_page(self) -> bool:
        return self._detection

    def _calendar_page(self) -> bool:
        return False

    @property
    def _write_with_response(self) -> bool:
        return True  # Both accepted Android callers retain WRITE_TYPE_DEFAULT.

    async def async_discover_capabilities(self) -> None:
        await super().async_discover_capabilities()
        # T05's fallback selects the last receive role. Rejecting missing preferred
        # characteristics above is an HA fence, not guaranteed Android recovery.
        self._notify_chars = self._notify_chars[-1:]
        self._session_generation += 1
        self._owner_client = self.client

    def _require_owner(self) -> None:
        if self._owner_client is None or self.client is not self._owner_client:
            raise ConnectionError("This command belongs to a previous BLE session")

    async def _dispatch(
        self, frame: bytes, *, cancel_event: asyncio.Event | None = None,
        factory: Callable[[], bytes] | None = None, deadline: float | None = None,
        cleanup: bool = False,
    ) -> None:
        self._require_owner()
        if self._write_char is None:
            raise ConnectionError("The write characteristic is unresolved")
        generation = self._session_generation

        def validate() -> None:
            self._require_owner()
            if generation != self._session_generation:
                raise ConnectionError("The BLE session changed before dispatch")
            context = current_command_context()
            if not cleanup and context and context.cancel_event.is_set():
                raise asyncio.CancelledError
            limit = context.hold_deadline if not cleanup and context and context.lease else deadline
            if limit is not None and asyncio.get_running_loop().time() >= limit:
                raise _HoldElapsed

        task = asyncio.create_task(self._write_gatt_with_retry(
            self._write_char.uuid, frame, cancel_event=cancel_event,
            response=True, characteristic=self._write_char,
            expected_client=self._owner_client, before_write=validate, command_factory=factory,
        ))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
                if cancel_event is None:
                    self._coordinator.cancel_command.set()
        task.result()
        self._require_owner()
        if generation != self._session_generation:
            raise ConnectionError("The completed write belongs to a previous BLE session")
        if cancelled:
            raise asyncio.CancelledError

    async def write_command(
        self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                return
            started = asyncio.get_running_loop().time()
            factory = (
                (lambda: codec.command(command[3], self._transmit_mode))
                if len(command) == 5 and command[:2] == bytes((codec.BED, 1)) else None
            )
            cleanup = (
                len(command) == 5 and (
                    command[:2] == bytes((codec.BED, 1)) and command[3] == codec.STOP
                    or command[0] == codec.MATTRESS and command[2:4] == bytes((6, 0))
                )
            )
            await self._dispatch(command, cancel_event=cancel_event, factory=factory, cleanup=cleanup)
            if index + 1 < repeat_count:
                await self._wait_cancel(max(0, repeat_delay_ms / 1000 - (asyncio.get_running_loop().time() - started)), cancel)

    @staticmethod
    async def _wait_cancel(seconds: float, cancel: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
        except TimeoutError:
            pass

    async def _release(self, delay: float = 0.12) -> None:
        owner, generation = self._owner_client, self._session_generation

        async def release() -> None:
            await asyncio.sleep(delay)
            if owner is not None and owner.is_connected and self.client is owner and generation == self._session_generation:
                await self._dispatch(protocol.stop_frame(self._transmit_mode), cancel_event=asyncio.Event(), factory=lambda: protocol.stop_frame(self._transmit_mode), cleanup=True)
                if context := current_command_context():
                    context.cleanup_stop_sent = True

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _held(self, control: Control, duration_ms: int | None = None) -> None:
        cancel = self._coordinator.cancel_command
        count, _delay = self.motor_pulse_settings()
        interval = control.keep_ms / 1000
        duration = duration_ms / 1000 if duration_ms is not None else count * interval
        deadline = asyncio.get_running_loop().time() + duration
        try:
            while not cancel.is_set():
                context = current_command_context()
                limit = context.hold_deadline if context and context.lease else deadline
                if limit is None or asyncio.get_running_loop().time() >= limit:
                    break
                started = asyncio.get_running_loop().time()
                try:
                    await self._dispatch(codec.command(control.code), factory=lambda: codec.command(control.code, self._transmit_mode), deadline=limit)
                except _HoldElapsed:
                    break
                await self._wait_cancel(max(0, min(interval - (asyncio.get_running_loop().time() - started), limit - asyncio.get_running_loop().time())), cancel)
        finally:
            await self._release(0 if self._fixed_remote else 0.12)

    @property
    def _fixed_remote(self) -> bool:
        return bool(self.model and self.model.model_id.removesuffix("_mattress") in {"6brm", "aerm", "afrm", "agrm", "bqrm", "y1rm"})

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f"mh_{control.code:02x}" for control in self._controls() if control.keep_ms))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= HOLD_CEILING_MS:
            raise ValueError("Choose a control this bed offers and a duration of up to 30 seconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        code = int(control.removeprefix("mh_"), 16)
        item = next(item for item in self._controls() if item.code == code and item.keep_ms)
        await self._held(item, duration_ms)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = {axis.key: axis for axis in self._axes()}
        return tuple(
            replace(spec, hold=ControllerMotorHoldSpec(
                f"mh_{axes[spec.key].up.code:02x}",
                f"mh_{axes[spec.key].down.code:02x}",
            )) if spec.key in axes else spec
            for spec in super().motor_control_specs
        )

    async def move_axis(self, key: str, direction: Literal["up", "down"]) -> None:
        axis = next((axis for axis in self._axes() if axis.key == key), None)
        if axis is None:
            raise ValueError("This app/model has no such motor")
        await self._held(axis.up if direction == "up" else axis.down)

    async def tap(self, code: int) -> None:
        control = next((control for control in self._controls() if control.code == code), None)
        if control is None:
            raise ValueError("This control is not on the selected app/model page")
        if self._fixed_remote and code in self._remote_long_codes:
            await self.remote_long(code)
            return
        if control.keep_ms:
            await self._held(control)
        else:
            try:
                await self.write_command(codec.command(code))
            finally:
                await self._release(0.15 if self._fixed_remote else 0.12)

    async def stop_all(self) -> None:
        await self._release(0)

    async def set_snore(self, option: str) -> None:
        if option not in self._snore_options():
            raise ValueError("This snore preset is not available on the selected page")
        code = 0 if option == "off" else next(code for code, name in SNORE_OPTIONS.items() if name == option)
        self._classifier.rx_type = "SNORE"
        # NISCO-A001: read mode only after the BLE lock is acquired, including retries.
        await self._dispatch(protocol.snore_frame(code), factory=lambda: protocol.snore_frame(code, self._transmit_mode))
        self.forward_controller_state_update(SNORE_KEY, option)

    async def write_light_timer(self, seconds: int, shown: int) -> None:
        if self._light_page() is None or not 0 <= seconds <= 300:
            raise ValueError("Choose a light timer from 0 to 300 seconds")
        # 0..300 is an explicit HA UI bound for Nisco; M proves that UI range.
        factory = (lambda: protocol.light_timer_frame(seconds, self._transmit_mode)) if APPS[self.app].rewrite_light_timer_mode else None
        await self._dispatch(protocol.light_timer_frame(seconds), factory=factory)
        self.forward_controller_state_update(LIGHT_TIMER_KEY, shown)

    async def write_massage_intensity(self, zone: str, value: int) -> None:
        # Both accepted slider callers wait 100 ms after release.
        await asyncio.sleep(0.1)
        await super().write_massage_intensity(zone, value)

    # Transmit mode and motor group are the app's local pickers: no bed write of
    # their own, so they are set through the richmat_mh_control action, not entities.
    def set_transmit_mode(self, option: str) -> None:
        if option not in ("0", "1", "2"):
            raise ValueError("Choose transmit mode 0, 1 or 2")
        self._transmit_mode = int(option)
        self._persist_snapshot()

    @property
    def motor_groups(self) -> tuple[str, ...]:
        return tuple(self._mode_groups)

    def set_group_type(self, option: str) -> None:
        if option not in self._mode_groups:
            raise ValueError("Choose a group this bed model offers")
        self._group_type = option
        self._persist_snapshot()

    async def toggle_smart_light_lock(self) -> None:
        if not self._smart_light_lock():
            raise ValueError("This app/model has no smart light lock control")
        # Dedicated cfrm caller uses mask2, preserving fixed mode00, no STOP.
        await self._dispatch(codec.command(0xC0, 0))

    def control_named(self, name: str) -> int:
        """Return the code of the one control on this app/model page named ``name``.

        The name its button shows is accepted, and so is the app's own wording.
        """
        wanted = " ".join(name.split()).casefold()
        names: dict[int, set[str]] = {}
        for control in self._controls():
            # A motor's two directions share its label: "Back up", "Back down".
            label = " ".join(control.label.split())
            wording = {label, preset_name(label)} if control.area == "memory" else {label}
            if control.kind == "save":
                wording = {f"Save {w}" for w in wording}
            elif control.kind in ("up", "down"):
                wording = {f"{label} {control.kind}"}
            names.setdefault(control.code, set()).update(wording)
        for spec in self.controller_button_specs:
            code = next((c for c in names if spec.key.endswith(f"_{c:02x}")), None)
            if code is not None:
                names[code].add(_shown_name(spec))
        codes = {code for code, labels in names.items() if wanted in {n.casefold() for n in labels}}
        if len(codes) != 1:
            raise ValueError("Choose a control by the name of its button")
        return codes.pop()

    def validate_control(self, code: int, *, remote_long: bool = False) -> Control:
        control = next((control for control in self._controls() if control.code == code), None)
        if control is None:
            raise ValueError("Choose a control this bed model offers")
        if remote_long and (
            self.route != "L" or control.kind != "save" or not self.model
            or code not in self._remote_long_codes
        ):
            raise ValueError("This bed model cannot save positions this way")
        return control

    def validate_voice(self, source: int) -> Control:
        target = self._speech.get(source)
        if target == codec.STOP:
            return Control("L", "press", "motor_btn", "END", "Stop", codec.STOP, 0)
        control = next((item for item in self.model.controls if item.code == target), None) if self.model else None
        if control is None:
            raise ValueError("Choose a voice command this bed model offers")
        return control

    async def voice_queue(self, source: int) -> None:
        control = self.validate_voice(source)
        if control.code == codec.STOP:
            await self._release()
        elif control.keep_ms:
            await self._held(control._replace(keep_ms=120))
        else:
            try:
                await self.write_command(codec.command(control.code))
            finally:
                await self._release()

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        # Only N establishes the 6e23 lock-state consumer. M still has its
        # source-proven command buttons, without fabricated state feedback.
        return super().controller_state_binary_sensor_specs if self.app == "nisco" else ()

    async def remote_long(self, code: int) -> None:
        self.validate_control(code, remote_long=True)
        generation = self._session_generation
        try:
            await self._wait_cancel(3, self._coordinator.cancel_command)
            if self._coordinator.cancel_command.is_set() or generation != self._session_generation:
                return
            await self.write_command(codec.command(code))
            await self._wait_cancel(0.15, self._coordinator.cancel_command)
        finally:
            await self._release(0)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        for spec in super().controller_button_specs:
            control = next((c for c in self._controls() if spec.key.endswith(f"_{c.code:02x}")), None)
            if control and control.keep_ms:
                spec = replace(spec, hold=ControllerHoldSpec(f"mh_{control.code:02x}"))
            specs.append(spec)
        if self._smart_light_lock():
            specs.append(ControllerButtonSpec(
                "richmat_mh_toggle_smart_light_lock", "Toggle smart light lock",
                lambda ctrl: _invoke(ctrl, "toggle_smart_light_lock"),
                translation_key="richmat_mh_toggle_smart_light_lock", cancel_movement=False,
            ))
        return unique_buttons(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [spec for spec in super().controller_state_sensor_specs if spec.key != "ruf_richmat_music_status"]
        if APPS[self.app].diagnostic_results and self._detection_page():
            specs = [replace(spec, attribute_keys=(*spec.attribute_keys, DIAGNOSTIC_ROWS, DIAGNOSTIC_PROGRESS)) if spec.key == DETECTION_KEY else spec for spec in specs]
        return tuple(specs) + (
            ControllerStateSensorSpec(
                LAST_REPLY, str(LAST_REPLY), LAST_REPLY, "mdi:bluetooth",
                attribute_keys=(MATTRESS_FRAME, MATTRESS_AVAILABLE, WAIST_AVAILABLE),
                entity_registry_enabled_default=False,
            ),
        )

    async def _run_session_setup(self) -> None:
        pending = self._pending = SessionFlags()
        generation = self._session_generation
        self._normal_ready = False
        self._normal_values.clear()
        try:
            await asyncio.sleep(0.3)
            await self._write_query(protocol.TX_VERSION)
            await asyncio.sleep(0.3)
            self._classifier.rx_type = "INIT"
            tasks = protocol.INIT_VER1 if pending.version == "0001" else protocol.INIT_VER0
            for frame in tasks:
                # AROMA and SPEECH are permanent excluded probes. Keep their
                # schedule slots without transmitting accessory/infrastructure queries.
                if frame not in (protocol.TX_AROMA, protocol.TX_SPEECH):
                    await self._write_query(frame)
                await asyncio.sleep(0.3)
            if self._pending is not pending or generation != self._session_generation:
                return
            self._version, self._call_page = pending.version, pending.call_page
            self._dev, self._detection = pending.dev, pending.detection
            self._waist = pending.waist and APPS[self.app].normal_mattress
            self._persist_snapshot()
        finally:
            if self._pending is pending:
                self._pending = None

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        self._require_owner()
        self._session_generation += 1
        owner, generation = self._owner_client, self._session_generation

        def receive(sender: object, data: bytearray) -> None:
            if self.client is owner and generation == self._session_generation:
                self._handle_notification(sender, data)

        assert owner is not None
        for char in self._notify_chars:
            async with self._ble_lock:
                if self.client is not owner or generation != self._session_generation:
                    raise ConnectionError("Notification setup lost its physical receiver")
                await owner.start_notify(char, receive)
        task = self._start_session()
        try:
            await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current and current.cancelling():
                raise

    async def stop_notify(self) -> None:
        self._notify_callback = None
        self._session_generation += 1
        self._cancel_session()
        for task in self._delayed_consumers:
            task.cancel()
        owner = self._owner_client
        if owner is None:
            return
        for char in self._notify_chars:
            async with self._ble_lock:
                if self.client is owner and owner.is_connected:
                    await owner.stop_notify(char)

    def _apply(self, event: protocol.Event) -> None:
        if event.data.startswith(("6e", "5e")):
            self.forward_controller_state_update(LAST_REPLY, event.data)
        if self.app == "mlily_supreme":
            if event.kind in ("alarm", "snore"):
                # The accepted sibling forwards these raw; N's exact ACK/lock
                # consumer mapping is not an established sibling counterpart.
                # Undecoded, so it never sets the alarm sensor: the raw reply is
                # only in the diagnostic last-reply sensor.
                self.forward_controller_state_update(LAST_REPLY, event.data)
                return
            if event.kind == "init" and event.data.startswith(protocol.RX_CALLBACK_PREFIX):
                self._apply_init(event.data)
                self.forward_controller_state_update(LAST_REPLY, event.data)
                return
        if event.kind in ("mattress_init", "mattress", "waist_init", "waist"):
            self.forward_controller_state_update(MATTRESS_FRAME, event.data)
            if event.kind in ("mattress_init", "waist_init"):
                key = MATTRESS_AVAILABLE if event.kind == "mattress_init" else WAIST_AVAILABLE
                self.forward_controller_state_update(key, True)
            if self.app != "mlily_supreme":
                return
            if event.kind == "mattress":
                self._normal_reply(bytes.fromhex(event.data))
                return
            if event.kind in ("mattress_init", "waist_init"):
                if event.kind == "waist_init":
                    if self._pending:
                        self._pending.waist = True
                    else:
                        self._waist = True
                        self._persist_snapshot()
                generation = self._session_generation

                async def consume() -> None:
                    await asyncio.sleep(0.3)
                    if generation != self._session_generation:
                        return
                    if event.kind == "mattress_init":
                        self._normal_init(bytes.fromhex(event.data))
                    else:
                        self._apply_waist({
                            **protocol.parse_waist_init(event.data),
                            **waist_init(event.data),
                        })
                    self._persist_snapshot()

                task = asyncio.create_task(consume())
                self._delayed_consumers.add(task)
                task.add_done_callback(self._delayed_consumers.discard)
                return
        if event.kind.startswith("detection_") and APPS[self.app].diagnostic_results:
            if event.kind == "detection_available":
                if self._pending:
                    self._pending.detection = True
                else:
                    self._detection = True
                    self._persist_snapshot()
                return
            if not self._detection_page() and not (self._pending and self._pending.detection):
                return  # HA's callback consumer exists only for an admitted page.
            if event.kind == "detection_started":
                self._diagnostic_rows.clear()
                self.forward_controller_state_update(DETECTION_KEY, "running")
                self.forward_controller_state_update(DIAGNOSTIC_PROGRESS, 0)
            elif event.kind == "detection_stopped":
                self.forward_controller_state_update(DETECTION_KEY, "stopped")
                self.forward_controller_state_update(DIAGNOSTIC_PROGRESS, 0)
            elif event.kind == "detection_result":
                kind, number, result = event.extra
                component = _COMPONENTS.get((kind, number))
                if component is None:
                    return
                resource, label = _COMPONENT_LABELS[component]
                self._diagnostic_rows.append({
                    "component": component, "label_resource": resource, "label": label,
                    "raw_result": result, "result": protocol.DETECTION_STATUS.get(result, result),
                    "result_label": _RESULT_LABELS.get(result, result),
                    "icon": "ic_check" if result == "1" else "ic_cross",
                })
            self.forward_controller_state_update(DIAGNOSTIC_ROWS, [dict(row) for row in self._diagnostic_rows])
            return
        RichmatMhController._apply(self, event)

    def on_disconnect(self) -> None:
        self._session_generation += 1
        self._owner_client = None
        for task in self._delayed_consumers:
            task.cancel()
        super().on_disconnect()


class _HoldElapsed(Exception):
    """A local HA hold deadline elapsed while waiting for the BLE lane."""


async def build_controller(ctx: BuildContext) -> BedController:
    app = RICHMAT_MH_APP_CATALOGS[ctx.bed_type]
    if app == "bedtech_classic":
        await ctx.preload("bedtech.classic")
        from ..bedtech.classic import build_classic_controller

        return await build_classic_controller(ctx)
    if ctx.variant == "sleep":
        await ctx.preload("richmat_mh.app_sleep")
        from .app_sleep import RichmatMHAppSleepController

        return RichmatMHAppSleepController(ctx.coordinator, app=app)
    await ctx.coordinator.hass.async_add_executor_job(catalog, app)
    return RichmatMHAppController(ctx.coordinator, app=app, protocol_variant=ctx.variant, device_name=ctx.live_device_name)
