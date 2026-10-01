"""SIMMONS app profile (com.okin.simmons 1.12.9), accepted as APK audit row049.

The app has two packet formats on one write gateway. Its Bluetooth name picks
the format (``okin`` prefix: checksummed frames written with response;
``smartbed`` prefix or an unmatched name: raw frames without response). The
discovered GATT services pick the destination independently. A per-device
bed-type choice (regular or inclined) swaps the zero-gravity/TV/anti-snore
presets for three inclined controls. Hardware is unverified.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_BLE_DEVICE_NAME,
    DOMAIN,
    SIMMONS_VARIANT_INCLINED,
    SIMMONS_VARIANT_INCLINED_OKIN,
    SIMMONS_VARIANT_INCLINED_SMARTBED,
    SIMMONS_VARIANT_OKIN,
    SIMMONS_VARIANT_SMARTBED,
)
from ..detection import is_mac_like_name
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)
from .simmons_protocol import (
    ALARM_MODES,
    FFE0_SERVICE,
    FFE4_NOTIFY,
    FFE5_SERVICE,
    FFE9_WRITE,
    INCLINED_ACTIONS,
    NUS_NOTIFY,
    NUS_SERVICE,
    NUS_WRITE,
    P1_ALARM_HEADER,
    AlarmMode,
    AlarmSlot,
    NotificationAssembler,
    Protocol,
    alarm_mode,
    alarm_type,
    apply_report,
    clock_frame,
    control_frame,
    gain_weekday,
    p1_alarm_frame,
    p2_alarm_frame,
    p2_disable_frame,
    parse_p1_alarm,
    parse_p2_alarm,
    query_frames,
    repeat_mask,
    resolve_protocol,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

REPEAT_MS: Final = 300  # Held controls repeat every 300 ms.
RELEASE_STOP_OFFSETS_S: Final = (0.1, 0.4)  # Two delayed STOPs after release.
QUERY_GAP_S: Final = 0.3  # Slot 2 query, and the query after an alarm write.
PAGE_QUERY_OFFSETS_S: Final = (0.0, 0.3, 0.6)  # Alarm page opening.
# The app's "Custom Mode has been set" toast fires after 5.5 s of continuous
# hold; its help text says to hold M for 5 s. No separate save opcode exists.
PROGRAM_HOLD_MS: Final = 5500
# Integration-side guard, not a protocol value: how long a write waits for the
# bed to report unknown alarm records before refusing to overwrite them.
ALARM_REPLY_TIMEOUT_S: Final = 2.0

_PROTOCOL_BY_VARIANT: Final[dict[str, Protocol]] = {
    SIMMONS_VARIANT_OKIN: "okin",
    SIMMONS_VARIANT_SMARTBED: "smartbed",
    SIMMONS_VARIANT_INCLINED_OKIN: "okin",
    SIMMONS_VARIANT_INCLINED_SMARTBED: "smartbed",
}
_INCLINED_VARIANTS: Final = frozenset(
    {SIMMONS_VARIANT_INCLINED, SIMMONS_VARIANT_INCLINED_OKIN, SIMMONS_VARIANT_INCLINED_SMARTBED}
)
_COMMON_CONTROLS: Final = (
    "head_up",
    "head_down",
    "legs_up",
    "legs_down",
    "flat",
    "memory",
    "light",
)
_REGULAR_CONTROLS: Final = ("zero_g", "tv", "anti_snore")
_INCLINED_LABELS: Final = {
    "inclined_left": "Inclined Left",
    "inclined_middle": "Inclined Middle",
    "inclined_right": "Inclined Right",
}
CUSTOM_MODE_WARNING: Final = (
    "Custom Mode alarms move the bed to the saved Custom Mode angles. Check the "
    "back/foot angles first: extreme custom angles can cause injury. Set "
    "confirm_custom_mode to proceed."
)
PEER_CONFLICT_ERROR: Final = (
    "Please do not set the same alarm timing for [Set 1] and [Set 2]: the other "
    "enabled alarm already uses this time or mode."
)


def _stored_ble_name(coordinator: object) -> object:
    """Return the raw Bluetooth name saved for this entry, never its display name."""
    data = getattr(getattr(coordinator, "entry", None), "data", None)
    return data.get(CONF_BLE_DEVICE_NAME) if isinstance(data, Mapping) else None


def _protocol_name(live: str | None, stored: object) -> str | None:
    """Pick the name for the app's prefix rule.

    The app reads Android's GAP name; HA sees the advertised name or BlueZ
    alias, which is the address when a bed sends no name. An address-like live
    name falls back to the name stored at setup, so the format stays stable
    across connections and proxies.
    """
    if not is_mac_like_name(live):
        return live
    return stored if isinstance(stored, str) and not is_mac_like_name(stored) else None


def _action(name: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        target = (
            controller._controller if isinstance(controller, SideBoundController) else controller
        )
        if not isinstance(target, SimmonsController):
            raise TypeError("This action requires the SIMMONS app profile")
        await target.execute_simmons_action(name)

    return invoke


class SimmonsController(BedController):
    """Faithful SIMMONS app controls, clock sync and two-slot alarms."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        protocol_variant: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        variant = protocol_variant or ""
        self._inclined = variant in _INCLINED_VARIANTS
        self._protocol: Protocol = _PROTOCOL_BY_VARIANT.get(variant) or resolve_protocol(
            _protocol_name(device_name, _stored_ble_name(coordinator))
        )
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._assembler = NotificationAssembler()
        self._pending_record: bytes | None = None
        self._awaiting = [False, False]
        # Which slots were reported on this connection (this controller is per connection).
        self._fresh = [False, False]
        self._reply = asyncio.Event()
        self._clock_synced = False  # Per connection: this controller is per session.
        # Alarm records live in coordinator state so they survive the
        # per-connection controller. They are per physical bed, not app-global.
        state = getattr(coordinator, "controller_state", {})
        self._slots: list[AlarmSlot | None] = [self._restore_slot(state, slot) for slot in (1, 2)]

    @staticmethod
    def _restore_slot(state: Mapping[str, object], slot: int) -> AlarmSlot | None:
        record = state.get(f"simmons_alarm_{slot}_record")
        if (
            isinstance(record, tuple)
            and len(record) == 5
            and all(type(value) is int for value in record[:4])
            and type(record[4]) is bool
        ):
            return AlarmSlot(*record)
        return None

    # ------------------------------------------------------------------ profile

    @property
    def protocol(self) -> Protocol:
        return self._protocol

    @property
    def inclined_layout(self) -> bool:
        return self._inclined

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_char.uuid if self._write_char is not None else NUS_WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "simmons_protocol": self._protocol,
            "simmons_layout": "inclined" if self._inclined else "regular",
            "simmons_write_characteristic": self._write_char.uuid if self._write_char else None,
            "simmons_notify_characteristic": self._notify_char.uuid if self._notify_char else None,
            "simmons_pending_record": self._pending_record.hex() if self._pending_record else None,
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Every release writes the all-zero STOP, so axes share one resource.
        return tuple(replace(spec, scheduler_resource="*") for spec in super().motor_control_specs)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, REPEAT_MS

    @property
    def supports_preset_zero_g(self) -> bool:
        return not self._inclined

    @property
    def supports_preset_tv(self) -> bool:
        return not self._inclined

    @property
    def supports_preset_anti_snore(self) -> bool:
        return not self._inclined

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Custom Mode",)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        extra = tuple(_INCLINED_LABELS) if self._inclined else _REGULAR_CONTROLS
        return (*_COMMON_CONTROLS, *extra)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_mode_options(self) -> tuple[AlarmMode, ...]:
        # Anti-snore is only offered on the regular bed layout.
        return ALARM_MODES if not self._inclined else ALARM_MODES[:2]

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        inclined = (
            tuple(
                ControllerButtonSpec(
                    f"simmons_{key}", label, _action(key), translation_key=f"simmons_{key}"
                )
                for key, label in _INCLINED_LABELS.items()
            )
            if self._inclined
            else ()
        )
        return (
            *inclined,
            ControllerButtonSpec(
                "simmons_sync_clock",
                "Sync Clock",
                _action("sync_clock"),
                translation_key="simmons_sync_clock",
                icon="mdi:clock-check",
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
            ControllerButtonSpec(
                "simmons_refresh_alarms",
                "Refresh Alarms",
                _action("refresh_alarms"),
                translation_key="simmons_refresh_alarms",
                icon="mdi:alarm",
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                key=f"simmons_alarm_{slot}",
                translation_key=f"simmons_alarm_{slot}",
                state_key=f"simmons_alarm_{slot}",
                icon="mdi:alarm",
                attribute_keys=tuple(
                    f"simmons_alarm_{slot}_{field}"
                    for field in ("enabled", "mode", "wire_type", "weekday_mask", "awaiting_reply")
                ),
            )
            for slot in (1, 2)
        )

    # --------------------------------------------------------------- transport

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None:
            raise ConnectionError("SIMMONS is not connected")
        write = notify = None
        # The app keeps iterating, so the last matching role of each kind wins.
        for service in client.services or ():
            service_uuid = service.uuid.lower()
            for char in service.characteristics:
                char_uuid = char.uuid.lower()
                if service_uuid == NUS_SERVICE and char_uuid == NUS_WRITE:
                    write = char
                elif service_uuid == NUS_SERVICE and char_uuid == NUS_NOTIFY:
                    notify = char
                elif service_uuid == FFE5_SERVICE and char_uuid == FFE9_WRITE:
                    write = char
                elif service_uuid == FFE0_SERVICE and char_uuid == FFE4_NOTIFY:
                    notify = char
        if write is None or notify is None:
            # The app disconnects unless both roles exist.
            raise ValueError("SIMMONS requires Nordic UART or FFE5/FFE9 plus FFE0/FFE4 roles")
        self._write_char, self._notify_char = write, notify

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._write_char is None:
            raise ConnectionError("SIMMONS write role is not resolved")
        await self._write_gatt_with_retry(
            self._write_char.uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            # OKIN-name frames use Android's default (acknowledged) write;
            # SmartBed and unmatched names write without response.
            response=self._protocol == "okin",
            wall_clock_pacing=True,
            characteristic=self._write_char,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client = self.client
        if client is None or self._notify_char is None:
            return
        async with self._ble_lock:
            await client.start_notify(self._notify_char, self._handle_notification)
        await self._initialize_session()

    async def _initialize_session(self) -> None:
        """Run the app's link-time traffic before the first command can start.

        The control page syncs the clock when a bed links and the alarm page
        queries at 0/300/600 ms. Doing both during connection setup means a
        quick-disconnect session still gets them. A failed write leaves the
        clock unsynced, so an alarm write syncs it first.
        """
        try:
            await self.sync_clock()
            await self.refresh_alarms()
        except (BleakError, ConnectionError, TimeoutError) as error:
            _LOGGER.debug("SIMMONS session initialization incomplete: %s", error)

    async def stop_notify(self) -> None:
        self._notify_callback = None
        client = self.client
        if client is None or not client.is_connected or self._notify_char is None:
            return
        async with self._ble_lock:
            await client.stop_notify(self._notify_char)

    # --------------------------------------------------------------- controls

    async def _release(self) -> None:
        """Send the release STOPs at +100/+400 ms, both attempted, uncancellable."""

        async def release() -> None:
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for offset in RELEASE_STOP_OFFSETS_S:
                await asyncio.sleep(max(0, started + offset - loop.time()))
                try:
                    await self.write_command(
                        control_frame(self._protocol, "stop"), cancel_event=asyncio.Event()
                    )
                except Exception as error:
                    failure = failure or error
            if failure is not None:
                raise failure

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001 - re-raised below unless cancelled
                break
        if cancelled:
            # The caller's cancellation wins; still retrieve a STOP failure.
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    async def _move(self, action: str) -> None:
        count, delay = self.motor_pulse_settings()
        try:
            await self.write_command(
                control_frame(self._protocol, action), repeat_count=count, repeat_delay_ms=delay
            )
        finally:
            await self._release()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Repeat a control every 300 ms for the hold, then release it."""
        if control not in self.held_control_options:
            raise ValueError(f"'{control}' is not a control of this SIMMONS bed layout")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Duration must be a positive integer, at most 60000 ms")
        deadline = asyncio.timeout(duration_ms / 1000)
        write_timeout = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            control_frame(self._protocol, control),
                            repeat_count=self.timed_move_repeat_count(duration_ms, REPEAT_MS),
                            repeat_delay_ms=REPEAT_MS,
                        )
                    except TimeoutError:
                        write_timeout = True
                        raise
            except TimeoutError:
                if write_timeout or not deadline.expired():
                    raise
        finally:
            await self._release()

    async def tap(self, control: str) -> None:
        """Press and release at once, as an app tap: the button-down write, no
        300 ms refresh (the pressed flag is already clear), then release STOPs."""
        if control not in self.held_control_options:
            raise ValueError(f"'{control}' is not a control of this SIMMONS bed layout")
        try:
            await self.write_command(control_frame(self._protocol, control))
        finally:
            await self._release()

    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_head_stop(self) -> None:
        await self._release()

    async def move_back_up(self) -> None:
        await self._move("head_up")

    async def move_back_down(self) -> None:
        await self._move("head_down")

    async def move_back_stop(self) -> None:
        await self._release()

    async def move_legs_up(self) -> None:
        await self._move("legs_up")

    async def move_legs_down(self) -> None:
        await self._move("legs_down")

    async def move_legs_stop(self) -> None:
        await self._release()

    async def move_feet_up(self) -> None:
        await self._move("legs_up")

    async def move_feet_down(self) -> None:
        await self._move("legs_down")

    async def move_feet_stop(self) -> None:
        await self._release()

    async def stop_all(self) -> None:
        await self._release()

    async def preset_flat(self) -> None:
        await self.tap("flat")

    async def preset_zero_g(self) -> None:
        await self.tap("zero_g")

    async def preset_tv(self) -> None:
        await self.tap("tv")

    async def preset_anti_snore(self) -> None:
        await self.tap("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1 or isinstance(memory_num, bool):
            raise ValueError("SIMMONS has one Custom Mode memory")
        await self.tap("memory")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num != 1 or isinstance(memory_num, bool):
            raise ValueError("SIMMONS has one Custom Mode memory")
        # Programming is the same recall frame held past the help's 5 s.
        await self.hold_control("memory", PROGRAM_HOLD_MS)

    async def lights_toggle(self) -> None:
        await self.tap("light")

    async def execute_simmons_action(self, action: str) -> None:
        if action == "sync_clock":
            await self.sync_clock()
        elif action == "refresh_alarms":
            await self.refresh_alarms()
        elif action in INCLINED_ACTIONS:
            await self.tap(action)
        else:
            raise ValueError(f"Unknown SIMMONS action '{action}'")

    # ------------------------------------------------------------ clock/alarm

    def invalidate_diagnostics(self) -> None:
        self._awaiting = [False, False]
        self._pending_record = None
        self._publish_slots()  # No reply can arrive once the session ends.

    async def sync_clock(self) -> None:
        """Write the local clock, as the control page does when a bed links."""
        await self._configure_write(clock_frame(self._protocol, dt_util.now()))
        self._clock_synced = True

    async def _query_once(self) -> None:
        frames = query_frames(self._protocol)
        await self._configure_write(frames[0])
        for frame in frames[1:]:
            await asyncio.sleep(QUERY_GAP_S)
            await self._configure_write(frame)

    async def _configure_write(self, frame: bytes) -> None:
        """Write a clock, query or alarm frame that a movement STOP must not skip."""
        await self.write_command(frame, cancel_event=asyncio.Event())

    async def refresh_alarms(self) -> None:
        """Repeat the alarm page's opening queries at 0, 300 and 600 ms."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        for offset in PAGE_QUERY_OFFSETS_S:
            await asyncio.sleep(max(0, started + offset - loop.time()))
            await self._query_once()

    def validate_simmons_alarm(
        self, *, slot: int, enabled: bool, mode: str | None, confirm_custom_mode: bool
    ) -> None:
        """Check the app's state-free alarm rules before anything is written."""
        if slot not in (1, 2) or isinstance(slot, bool):
            raise ValueError("SIMMONS has alarm slots 1 and 2")
        if not enabled:
            return
        if mode not in self.alarm_mode_options:
            raise ValueError(
                "Alarm mode must be custom_mode or flat"
                + ("" if self._inclined else ", or anti_snore")
            )
        if mode == "custom_mode" and not confirm_custom_mode:
            raise ValueError(CUSTOM_MODE_WARNING)

    async def _ensure_alarm_state(self) -> tuple[AlarmSlot, AlarmSlot]:
        """Return both records as reported in this connection, querying if needed.

        Restored records may be stale (the app can change an alarm while HA is
        away), so they are shown but never feed a conflict check or the peer
        record of a write.
        """
        if not all(self._fresh):
            self._reply.clear()
            await self._query_once()
            try:
                async with asyncio.timeout(ALARM_REPLY_TIMEOUT_S):
                    while not all(self._fresh):
                        await self._reply.wait()
                        self._reply.clear()
            except TimeoutError:
                pass
        first, second = self._slots
        if not all(self._fresh) or first is None or second is None:
            raise ServiceValidationError(
                "The bed did not report both alarm records in this connection; nothing was written",
                translation_domain=DOMAIN,
                translation_key="simmons_alarm_not_reported",
            )
        return first, second

    async def check_simmons_alarm(
        self,
        *,
        slot: int,
        enabled: bool,
        hour: int = 0,
        minute: int = 0,
        weekdays: Sequence[int] = (),
        mode: str | None = None,
        confirm_custom_mode: bool = False,
    ) -> None:
        """Validate an alarm against this bed's reported records without programming it.

        Multi-bed actions run this on every bed first, so a conflict or a bed
        that does not report its records changes no bed. Only the app's own
        alarm query is sent, and only when the records are not yet known.
        """
        await self._plan_alarm(slot, enabled, hour, minute, weekdays, mode, confirm_custom_mode)

    async def _plan_alarm(
        self,
        slot: int,
        enabled: bool,
        hour: int,
        minute: int,
        weekdays: Sequence[int],
        mode: str | None,
        confirm_custom_mode: bool,
    ) -> tuple[int, AlarmSlot, bytes]:
        """Return the slot index, its new local record and the frame to write."""
        self.validate_simmons_alarm(
            slot=slot, enabled=enabled, mode=mode, confirm_custom_mode=confirm_custom_mode
        )
        if enabled and not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid alarm time")
        if any(isinstance(day, bool) or not 0 <= day <= 6 for day in weekdays):
            raise ValueError("Alarm weekdays use Monday=0 through Sunday=6")
        slots = list(await self._ensure_alarm_state())
        index, peer = slot - 1, slots[2 - slot]
        local = slots[index]
        if not enabled:
            # Selected weekday and type are cleared; hours and minutes stay.
            selected = [local.hour, local.minute, 0, 0]
            frame = (
                p2_disable_frame(slot)
                if self._protocol == "smartbed"
                else self._p1_frame(index, selected, peer)
            )
            return index, replace(local, enabled=False), frame
        wire_type = alarm_type(self._protocol, mode or "")
        if peer.enabled and ((peer.hour, peer.minute) == (hour, minute) or peer.type == wire_type):
            raise ValueError(PEER_CONFLICT_ERROR)
        mask = repeat_mask(weekdays)
        weekday = gain_weekday(mask, hour, minute, dt_util.now())
        frame = (
            p2_alarm_frame(slot, weekday, wire_type, hour, minute)
            if self._protocol == "smartbed"
            else self._p1_frame(index, [hour, minute, weekday, wire_type], peer)
        )
        return index, AlarmSlot(hour, minute, mask, wire_type, True), frame

    async def configure_simmons_alarm(
        self,
        *,
        slot: int,
        enabled: bool,
        hour: int = 0,
        minute: int = 0,
        weekdays: Sequence[int] = (),
        mode: str | None = None,
        confirm_custom_mode: bool = False,
    ) -> None:
        """Program or disable one alarm exactly as the app's alarm page does."""
        self.validate_simmons_alarm(
            slot=slot, enabled=enabled, mode=mode, confirm_custom_mode=confirm_custom_mode
        )
        if not self._clock_synced:
            # Alarms fire on the bed's clock, so this session must have set it.
            await self.sync_clock()
        index, updated, frame = await self._plan_alarm(
            slot, enabled, hour, minute, weekdays, mode, confirm_custom_mode
        )
        await self._configure_write(frame)
        # Local state follows only a successful write, so a failed write cannot
        # change the overlays applied to later replies.
        if self._protocol == "okin":
            self._pending_record = frame[3:11]
            self._awaiting = [True, True]
        else:
            self._awaiting[index] = True
        self._slots[index] = updated
        self._publish_slots()
        await asyncio.sleep(QUERY_GAP_S)
        await self._query_once()

    @staticmethod
    def _p1_frame(index: int, selected: list[int], peer: AlarmSlot) -> bytes:
        records = [selected, peer.peer_record()] if index == 0 else [peer.peer_record(), selected]
        return p1_alarm_frame(*records)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        raw = bytes(data)
        if self._notify_char is not None:
            self.forward_raw_notification(self._notify_char.uuid, raw)
        message = self._assembler.feed(raw)
        if message is None:
            return
        if message[:3] == P1_ALARM_HEADER:
            if (
                self._pending_record is not None
                and len(message) >= 11
                and message[3:11] == self._pending_record
            ):
                self._pending_record = None
                self._awaiting = [False, False]
            reports = parse_p1_alarm(message)
            if reports is None:
                return  # Truncated replies are rejected whole.
            self._fresh = [True, True]
            for report in reports:
                self._slots[report.slot - 1] = apply_report(
                    report, self._slots[report.slot - 1], "okin"
                )
        else:
            report = parse_p2_alarm(message)
            if report is None:
                return
            self._slots[report.slot - 1] = apply_report(
                report, self._slots[report.slot - 1], "smartbed"
            )
            self._awaiting[report.slot - 1] = False
            self._fresh[report.slot - 1] = True
        self._publish_slots()
        self._reply.set()

    def _publish_slots(self) -> None:
        updates: dict[str, object] = {}
        for slot, record in enumerate(self._slots, start=1):
            if record is None:
                continue
            prefix = f"simmons_alarm_{slot}"
            updates.update(
                {
                    prefix: f"{record.hour:02d}:{record.minute:02d}",
                    f"{prefix}_enabled": record.enabled,
                    f"{prefix}_mode": alarm_mode(self._protocol, record.type),
                    f"{prefix}_wire_type": record.type,
                    f"{prefix}_weekday_mask": record.weekday,
                    f"{prefix}_awaiting_reply": self._awaiting[slot - 1],
                    f"{prefix}_record": (
                        record.hour,
                        record.minute,
                        record.weekday,
                        record.type,
                        record.enabled,
                    ),
                }
            )
        self.forward_controller_state_updates(updates)
