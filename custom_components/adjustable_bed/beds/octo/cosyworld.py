"""Cosyworld's current-session capabilities over the shared OCTO codec/runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...codec.octo import OctoCapabilityRecord, _encode_capability_value
from ...command_scheduler import note_frame_skipped
from ...const import CONF_OCTO_PIN
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...execution import ExecutionCapabilities
from ...profiles import cosyworld as app
from ...state_keys import (
    LIGHT_TIMER_OPTION,
    OCTO_LIGHT_DURATION,
    REMOTE_CONTROL_LOCK,
    SYNCHRO_MODE,
    UNDER_BED_LIGHTS_ON,
)
from ..builder import BuildContext
from ..entity_specs import ControllerButtonSpec, MotorControlSpec
from .controller import (
    OCTO_FEATURE_END,
    OCTO_FEATURE_LIGHT,
    OCTO_FEATURE_LIGHT_DURATION,
    OCTO_FEATURE_MEMCOUNT,
    OCTO_FEATURE_MEMINFO,
    OCTO_FEATURE_PIN,
    OCTO_FEATURE_REMOTE_CONTROL_LOCK,
    OCTO_FEATURE_SYNCHRO,
    OctoController,
)


class _HoldExpired(Exception):
    """The gesture ended while its next frame waited for the BLE lane."""


class CosyworldController(OctoController):
    """Reuse motor/PIN plumbing without admitting sibling features or fallbacks."""

    profile = app.PROFILE
    _write_characteristic: BleakGATTCharacteristic | None = None

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def normal_controls_available(self) -> bool:
        # Persisted surfaces may reconnect. Every writer still requires the
        # current link's complete discovery and PIN proof before transmission.
        if self.client is None:
            return self.controller_entity_discovery_complete
        return (
            self._session_ready
            and self._device_info is not None
            and self._device_info["cid"] != 0xFFFFFFFF
            and (
                self._pin_feature_active is not True
                or self._has_pin is True
                and self._pin_locked is False
            )
        )

    def _require_normal_controls(self) -> None:
        if self._pin_feature_active and self._has_pin is False:
            raise invalid("cosyworld_pin_unset")
        if not self.normal_controls_available:
            raise invalid("cosyworld_locked")

    @property
    def effective_motor_count(self) -> int | None:
        count = self._discovered_motor_count
        return count if count in (1, 2, 4) else None

    @property
    def uses_legacy_light_switch(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self.supports_discrete_light_control

    def _active_value(self, feature_id: int) -> bool:
        r = self._capability_records.get(feature_id)
        return bool(r and r.characteristic[:1] == b"\x01" and r.value)

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._active_value(OCTO_FEATURE_LIGHT)

    @property
    def supports_synchro(self) -> bool:
        return self._active_value(OCTO_FEATURE_SYNCHRO)

    @property
    def supports_remote_control_lock(self) -> bool:
        return self._active_value(OCTO_FEATURE_REMOTE_CONTROL_LOCK)

    @property
    def supports_automatic_light(self) -> bool:
        return False

    @property
    def supports_light_sensitivity(self) -> bool:
        return False

    @property
    def light_auto_off_seconds(self) -> int | None:
        minutes = self._light_duration_minutes
        return minutes * 60 if self.supports_lights and minutes else None

    def _apply_capability_records(
        self, records: Mapping[int, OctoCapabilityRecord], *, preserve_notification_pin_state=False
    ) -> None:
        super()._apply_capability_records(
            records, preserve_notification_pin_state=preserve_notification_pin_state
        )
        pin = records.get(OCTO_FEATURE_PIN)
        if not preserve_notification_pin_state and pin is not None and len(pin.value) >= 2:
            # The app reads V[0:2] even when C[0] says PIN is not used.
            self._has_pin = pin.value[0] == 1
            self._pin_locked = pin.value[1] != 1
        # These ids have no reachable Cosyworld color/automatic/sensitivity action.
        self._has_rgb = self._has_rgbwi = self._automatic_light_active = False
        self._light_sensitivity = None
        self._has_lights = self._active_value(OCTO_FEATURE_LIGHT)
        self._has_synchro = self._active_value(OCTO_FEATURE_SYNCHRO)
        sync = records.get(OCTO_FEATURE_SYNCHRO)
        self._synchro_active = sync.value[0] == 1 if sync and sync.value else None
        lock = records.get(OCTO_FEATURE_REMOTE_CONTROL_LOCK)
        self._remote_lock_active = bool(lock and lock.value and lock.value[0] == 1)
        # MEMCOUNT supplies the visible slot count. MEMINFO supplies classes and
        # descriptions only when its complete vector agrees with that slot list.
        count = records.get(OCTO_FEATURE_MEMCOUNT)
        self._memory_count = count.characteristic[0] if count and count.characteristic else 0
        info = records.get(OCTO_FEATURE_MEMINFO)
        if not (
            info
            and len(info.characteristic) == 3
            and info.characteristic[0] == self._memory_count
            and len(info.value) == self._memory_count
        ):
            self._memory_mem_count = self._memory_fix_count = self._memory_lock_count = 0
            self._memory_descriptions = ()
        duration = records.get(OCTO_FEATURE_LIGHT_DURATION)
        self._light_duration_minutes = (
            duration.value[0]
            if duration
            and duration.characteristic[:1] == b"\x01"
            and duration.value
            and duration.value[0] <= 60
            else None
        )

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        labels = {1: "Anti-snore", 2: "Zero gravity", 3: "Lumbar support"}
        return tuple(labels.get(v) for v in self._memory_descriptions)

    def _publish_capability_state(self) -> None:
        light = self._capability_records.get(OCTO_FEATURE_LIGHT)
        minutes = self._light_duration_minutes
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(light.value[0] == 1 if light and light.value else None),
            SYNCHRO_MODE(self._synchro_active),
            REMOTE_CONTROL_LOCK(self._remote_lock_active),
            OCTO_LIGHT_DURATION(minutes),
            LIGHT_TIMER_OPTION(app.LIGHT_TIMER_OPTIONS[minutes] if minutes is not None else None),
        )

    def _handle_feature_response(self, data: list[int]) -> None:
        r = self._extract_feature_value_pair(data)
        if self._capability_response_invalid or self.invalid_response_received:
            return
        if r is None or r.readonly not in (0, 1):
            self._capability_response_invalid = True
            return
        if r.feature_id == OCTO_FEATURE_END:
            self._capability_records = dict(self._pending_capability_records)
            self._apply_capability_records(
                self._capability_records, preserve_notification_pin_state=True
            )
            self._features_complete.set()
            self._capability_records_authoritative = True
            self._legacy_motor_layout_available = False
            self._feature_discovery_event.set()
            self._publish_capability_state()
            return
        old = self._pending_capability_records.get(r.feature_id)
        if old is not None:
            # The app retains the first readOnly/type on duplicate ids.
            r = replace(r, readonly=old.readonly, value_type=old.value_type)
        self._pending_capability_records[r.feature_id] = r
        if r.feature_id == OCTO_FEATURE_PIN:
            # PIN records and subsequent PIN notifications are an ordered live
            # stream. CAP_END must never replay an older unlock value.
            self._pin_feature_active = r.characteristic[:1] == b"\x01"
            self._has_pin = r.value[0] == 1 if len(r.value) >= 2 else None
            self._pin_locked = r.value[1] != 1 if len(r.value) >= 2 else None
            self._publish_pin_state()
        if self._session_ready:
            self._capability_records[r.feature_id] = r
            self._apply_capability_records(
                self._capability_records,
                preserve_notification_pin_state=True,
            )
            self._publish_capability_state()
        self._features_loaded.set()

    def on_light_auto_off(self) -> None:
        updated = False
        for records in (self._capability_records, self._pending_capability_records):
            r = records.get(OCTO_FEATURE_LIGHT)
            if r and r.characteristic[:1] == b"\x01" and r.value:
                records[OCTO_FEATURE_LIGHT] = r.with_value(b"\x00" + r.value[1:])
                updated = True
        if updated:
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(False))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client, generation = self.client, self._session_generation
        if client is None or not client.is_connected:
            raise BedNotConnectedError

        candidates = [
            char
            for service in client.services
            if service.uuid.lower() == app.SERVICE
            for char in service.characteristics
            if char.uuid.lower() == app.CHARACTERISTIC
        ]
        if (
            len(candidates) != 1
            or "write-without-response" not in candidates[0].properties
            or not {"notify", "indicate"}.intersection(candidates[0].properties)
        ):
            raise invalid("cosyworld_transport")
        characteristic = candidates[0]
        self._write_characteristic = characteristic

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self.client is not client or generation != self._session_generation:
                return
            # Handshake is the exact raw subscribedResult match, not any parsed ACK.
            if bytes(data) == app.HANDSHAKE_RESPONSE:
                self._ping_event.set()
            self._on_notification(sender, data)

        self._response_buffer.clear()
        async with self._ble_lock:
            await client.start_notify(characteristic, receive)
        self._notifications_started = True

    def _parse_response_packet(self, message: bytes) -> dict[str, list[int]] | None:
        packet = super()._parse_response_packet(message)
        if packet is not None and (
            packet["wire_command"][0] != packet["command"][0] or packet["command"][0] & 1 != 1
        ):
            return None
        return packet

    def _on_notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        # Shared parsing deliberately rejects malformed lengths, escaped-string
        # coercion, foreign directions and addressed variants this app never sends.
        # It does not implement the app's uncorrelated promise resolver.
        was_ping = self._ping_event.is_set()
        super()._on_notification(sender, data)
        # A fragmented, coalesced or nonempty ping is not the raw handshake reply.
        if not was_ping:
            self._ping_event.clear()

    async def stop_notify(self) -> None:
        self._session_ready = False
        self._session_generation += 1
        await super().stop_notify()

    async def discover_features(self) -> bool:
        self._session_ready = False
        self._session_generation += 1
        self._device_info = None
        self._device_info_invalid = False
        self._pending_capability_records = {}
        self._capability_response_invalid = False
        self.invalid_response_received = False
        self._ping_event.clear()
        self._device_info_event.clear()
        self._feature_discovery_event.clear()
        self._features_complete.clear()
        self._pin_sent = False
        self._pin_feature_active = self._has_pin = self._pin_locked = None
        self._pin_state_event.clear()
        self._pin_state_accepted = None
        # Rebind the callback after incrementing the session generation.
        if self._notifications_started:
            await super().stop_notify()
        await self.start_notify()
        client, generation = self.client, self._session_generation
        try:
            await self._write_octo_command([0x20, 0x7F], cancel_event=asyncio.Event())
            await asyncio.wait_for(self._ping_event.wait(), self.profile.handshake_timeout_s)
            await self._write_octo_command([0x20, 0x70], cancel_event=asyncio.Event())
            await asyncio.wait_for(self._device_info_event.wait(), self.profile.discovery_timeout_s)
            if self._device_info_invalid or self._device_info is None:
                return False
            await self._write_octo_command([0x20, 0x71], cancel_event=asyncio.Event())
            await asyncio.wait_for(
                self._feature_discovery_event.wait(), self.profile.discovery_timeout_s
            )
            if self._capability_response_invalid or self.invalid_response_received:
                return False
            self._session_ready = self._current(client, generation)
            if self._session_ready:
                self._publish_capability_state()
            return self._session_ready
        except TimeoutError:
            return False

    def _current(self, client: BleakClient | None, generation: int) -> bool:
        return (
            client is not None
            and client.is_connected
            and self.client is client
            and self._session_generation == generation
            and self._coordinator.controller is self
        )

    async def _write_octo_command(
        self,
        command: list[int],
        data: list[int] | None = None,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        client, generation = self.client, self._session_generation
        key = tuple(command)
        setup = {(0x20, 0x7F), (0x20, 0x70), (0x20, 0x71)}
        pin = {(0x20, 0x41), (0x20, 0x43)}
        stop = key == (0x02, 0x73)

        def check() -> None:
            if not self._current(client, generation):
                raise BedNotConnectedError("cosyworld_session")
            if not stop and key not in setup and not self._session_ready:
                raise BedNotConnectedError("cosyworld_session")
            if not stop and key not in setup | pin:
                self._require_normal_controls()

        def admit() -> None:
            check()
            if before_write is not None:
                before_write()

        check()
        await self._write_gatt_with_retry(
            app.CHARACTERISTIC,
            self._build_packet(command, data),
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
            expected_client=client,
            characteristic=self._write_characteristic,
            before_write=admit,
            settle_write=True,
            write_timeout=self.profile.write_timeout_s,
            wall_clock_pacing=True,
        )

    @property
    def restore_notifications_after_cancel(self) -> bool:
        # Resume owns both subscription and complete reinitialization.
        return False

    async def async_resume_session(self) -> None:
        if not self._session_ready and not await self.discover_features():
            raise BedNotConnectedError("cosyworld_session")
        await self.send_pin()

    async def async_refresh_auth(self) -> None:
        # Enrollment is still allowed when the feature requires a first PIN.
        # Normal commands independently enforce normal_controls_available.
        await self.async_resume_session()
        if self._pin_feature_active and self._has_pin:
            await self.async_wait_for_pin_acceptance(self._coordinator.cancel_command)

    async def start_keepalive(self) -> None:
        """Cosyworld has challenge-triggered PIN unlock, no proven periodic sender."""

    async def _write_setting(self, feature_id: int, value: bytes, *, toggle=False) -> None:
        client, generation = self.client, self._session_generation
        outgoing: OctoCapabilityRecord | None = None
        previous: OctoCapabilityRecord | None = None
        submitted = False

        def build() -> bytes:
            nonlocal outgoing, previous
            r = self._capability_records.get(feature_id)
            self._require_normal_controls()
            if r is None or r.characteristic[:1] != b"\x01" or toggle and not r.value:
                raise invalid("cosyworld_capability")
            previous = r
            outgoing = r.with_value(value + r.value[1:] if toggle else value)
            return self._build_packet(
                [0x20, 0x72], _encode_capability_value(outgoing, outgoing.value)
            )

        def show() -> None:
            nonlocal submitted
            submitted = (
                self._current(client, generation)
                and self._capability_records.get(feature_id) is previous
            )
            if submitted and outgoing is not None:
                self._capability_records[feature_id] = outgoing
                self._pending_capability_records[feature_id] = outgoing
                self._apply_capability_records(
                    self._capability_records, preserve_notification_pin_state=True
                )

        key: StateKey[bool | None] = {
            OCTO_FEATURE_LIGHT: UNDER_BED_LIGHTS_ON,
            OCTO_FEATURE_SYNCHRO: SYNCHRO_MODE,
            OCTO_FEATURE_REMOTE_CONTROL_LOCK: REMOTE_CONTROL_LOCK,
        }.get(feature_id, UNDER_BED_LIGHTS_ON)
        updates = (
            (key(value[0] == 1),)
            if toggle
            else (
                LIGHT_TIMER_OPTION(app.LIGHT_TIMER_OPTIONS[value[0]]),
                OCTO_LIGHT_DURATION(value[0]),
            )
        )
        if not self._current(client, generation) or not self._session_ready:
            raise BedNotConnectedError("cosyworld_session")
        with self.sent_state(
            *updates, is_current=lambda: submitted and self._current(client, generation)
        ):
            await self._write_gatt_with_retry(
                app.CHARACTERISTIC,
                b"",
                response=False,
                expected_client=client,
                characteristic=self._write_characteristic,
                before_write=lambda: self._check_current(client, generation),
                command_factory=build,
                on_write=show,
                settle_write=True,
                write_timeout=self.profile.write_timeout_s,
            )

    def _check_current(self, client: BleakClient | None, generation: int) -> None:
        if not self._current(client, generation) or not self._session_ready:
            raise BedNotConnectedError("cosyworld_session")

    async def lights_on(self) -> None:
        await self._write_setting(OCTO_FEATURE_LIGHT, b"\x01", toggle=True)

    async def lights_off(self) -> None:
        await self._write_setting(OCTO_FEATURE_LIGHT, b"\x00", toggle=True)

    async def lights_toggle(self) -> None:
        r = self._capability_records.get(OCTO_FEATURE_LIGHT)
        if not r or not r.value:
            raise invalid("cosyworld_capability")
        await (self.lights_off() if r.value[0] == 1 else self.lights_on())

    async def set_synchro(self, enabled: bool) -> None:
        await self._write_setting(OCTO_FEATURE_SYNCHRO, bytes((enabled,)), toggle=True)

    async def set_remote_control_lock(self, enabled: bool) -> None:
        await self._write_setting(OCTO_FEATURE_REMOTE_CONTROL_LOCK, bytes((enabled,)), toggle=True)

    @property
    def supports_light_timer(self) -> bool:
        return self.supports_light_duration

    @property
    def light_timer_options(self) -> list[str]:
        return list(app.LIGHT_TIMER_OPTIONS)

    @property
    def controller_number_specs(self):
        return ()

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option not in app.LIGHT_TIMER_OPTIONS:
            raise invalid("option_unavailable")
        await self.set_light_duration(app.LIGHT_TIMER_OPTIONS.index(timer_option))

    async def set_light_duration(self, minutes: int) -> None:
        if type(minutes) is not int or not 0 <= minutes <= 60:
            raise invalid("option_unavailable")
        if not self.supports_light_duration:
            raise invalid("cosyworld_capability")
        await self._write_setting(OCTO_FEATURE_LIGHT_DURATION, bytes((minutes,)))

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Four-motor pictograms do not establish individual physical axis labels.
        if self.effective_motor_count not in (1, 2):
            return ()
        return tuple(
            replace(
                s,
                translation_key="cosyworld_lift" if s.key == "tv_lift" else s.translation_key,
                hold=replace(
                    s.hold,
                    start_delay_ms=self.profile.start_delay_ms,
                    release_delay_ms=self.profile.motor_release_ms,
                ),
            )
            for s in super().motor_control_specs
            if s.hold is not None
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        controls = list(super().held_control_options)
        if self.effective_motor_count == 4:
            controls = [c for c in controls if c == "all_down" or c.startswith("memory_")]
        return tuple(controls)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            replace(
                s,
                hold=replace(
                    s.hold,
                    start_delay_ms=self.profile.start_delay_ms,
                    release_delay_ms=self.profile.memory_release_ms
                    if s.key.startswith("preset_memory_")
                    else self.profile.motor_release_ms,
                ),
            )
            if s.hold
            else s
            for s in super().controller_button_specs
        )

    @property
    def supports_preset_both_up(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

    async def _octo_move_with_stop(self, motor_bits: int, direction: str) -> None:
        client, generation = self.client, self._session_generation
        try:
            await self._write_octo_command(
                [2, 0x70 if direction == "up" else 0x71],
                [motor_bits],
                repeat_count=max(1, self._coordinator.motor_pulse_count),
                repeat_delay_ms=max(1, self._coordinator.motor_pulse_delay_ms),
            )
        finally:
            if self._current(client, generation):
                await self._stop_motors()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        client, generation = self.client, self._session_generation
        if control.startswith("memory_"):
            command, data = [2, 0x72], [int(control.removeprefix("memory_")) - 1]
        elif control == "all_down":
            command, data = [2, 0x71], [0x1E]
        else:
            mask, direction = self._held_motor_command(control)
            command, data = [2, 0x70 if direction == "up" else 0x71], [mask]
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        sent_at = loop.time()

        def admit() -> None:
            nonlocal sent_at
            self._check_current(client, generation)
            sent_at = loop.time()
            if sent_at >= deadline:
                note_frame_skipped()
                raise _HoldExpired

        try:
            while loop.time() < deadline and not cancel.is_set():
                await self._write_octo_command(
                    command, data, cancel_event=cancel, before_write=admit
                )
                remaining = min(deadline, sent_at + self.profile.refresh_ms / 1000) - loop.time()
                if remaining > 0 and not cancel.is_set():
                    try:
                        await asyncio.wait_for(cancel.wait(), remaining)
                    except TimeoutError:
                        pass
        except _HoldExpired:
            pass
        finally:
            if self._current(client, generation):
                await self._stop_motors()

    async def enroll_pin(self, pin: str) -> None:
        if len(pin) != 4 or not pin.isascii() or not pin.isdecimal():
            raise invalid("pin_invalid")
        client, generation = self.client, self._session_generation
        submitted = False

        def check() -> None:
            self._check_current(client, generation)
            if (
                self._device_info is None
                or self._device_info["cid"] == 0xFFFFFFFF
                or self._pin_feature_active is not True
                or self._has_pin is not False
                or self._pin_locked is not False
            ):
                raise invalid("cosyworld_locked")

        def remember() -> None:
            nonlocal submitted
            submitted = True
            self._pin = pin

        check()
        await self._write_gatt_with_retry(
            app.CHARACTERISTIC,
            self._build_packet([0x20, 0x41], [int(d) for d in pin]),
            response=False,
            expected_client=client,
            characteristic=self._write_characteristic,
            before_write=check,
            on_write=remember,
            settle_write=True,
            write_timeout=self.profile.write_timeout_s,
        )
        if not submitted:
            raise invalid("action_stopped")

    async def reset_defaults(self) -> None:
        client, generation = self.client, self._session_generation

        def check() -> None:
            self._check_current(client, generation)
            if (
                self._device_info is None
                or self._device_info["cid"] == 0xFFFFFFFF
                or self._pin_locked is not False
            ):
                raise invalid("cosyworld_locked")

        async def disconnect() -> None:
            await asyncio.sleep(self.profile.reset_disconnect_s)
            if self._current(client, generation):
                await self._coordinator.async_disconnect(
                    serialize_with_commands=True,
                    expected_session=lambda: self._current(client, generation),
                )

        def submitted() -> None:
            self._coordinator.entry.async_create_background_task(
                self._coordinator.hass,
                disconnect(),
                name="cosyworld_reset_disconnect",
            )

        check()
        await self._write_gatt_with_retry(
            app.CHARACTERISTIC,
            self._build_packet([0x20, 0xAE]),
            response=False,
            expected_client=client,
            characteristic=self._write_characteristic,
            before_write=check,
            on_write=submitted,
            settle_write=True,
            write_timeout=self.profile.write_timeout_s,
        )


async def build_controller(ctx: BuildContext) -> CosyworldController:
    return CosyworldController(
        ctx.coordinator,
        pin=ctx.data.get(CONF_OCTO_PIN, ""),
        capability_snapshot=ctx.stored_capabilities("cosyworld"),
    )
