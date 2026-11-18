"""MLILY Remote's five products over the shared Richmat product runtime."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...card import CARD_CLIMATE, CARD_LIGHTING, CARD_MASSAGE, CARD_PRESET_SAVE, CARD_PRESETS
from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped, note_frame_written
from ...controller_state import StateKey
from ...profiles.mlily_remote import ACTIONS, PROFILES, SAVE_MS, STARTUP, TICK_S
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..casper_base.controller import CasperBaseController
from ..casper_base.protocol import Request, alarm_countdown
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..goodvibe.controller import Link, select_link
from .receive import Receiver

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

MODEL: Final = StateKey[str]("mlily_remote_model")
EVENTS: Final = StateKey[dict[str, object]]("mlily_remote_events")
ALARM: Final = StateKey[dict[str, object]]("mlily_remote_alarm")
ERROR: Final = StateKey[str | None]("mlily_remote_error")

# Button names for the product's discrete actions, in the shared preset and Richmat MH
# massage names. Flat, memory recall/save and movement have their own entities.
LABELS: Final = {
    "BedLight": "Toggle Light",
    "ZeroGravity": "Zero Gravity",
    "AntiSnoring": "Anti-Snore",
    "TVPosition": "TV",
    "LoungePosition": "Lounge",
    "MassageHeadInstensityStrengthen": "Massage: Head Up",
    "MassageFootInstensityStrengthen": "Massage: Foot Up",
    "MassageLumbarInstensityStrengthen": "Massage: Lumbar Up",
    "MassageModeChange": "Massage mode",
    "MassageModeAllOff": "All Off",
    "Massage10MinuteTimer": "Massage: Timer 10 Minutes",
    "Massage20MinuteTimer": "Massage: Timer 20 Minutes",
    "Massage30MinuteTimer": "Massage: Timer 30 Minutes",
}
# PowerCool sends the same codes to its fans, with 2/3/5-hour timers.
COOLING_LABELS: Final = {
    **LABELS,
    "MassageHeadInstensityStrengthen": "Fan: Head Up",
    "MassageFootInstensityStrengthen": "Fan: Foot Up",
    "MassageModeChange": "Fan: Mode",
    "MassageModeAllOff": "Fan: Off",
    "Massage10MinuteTimer": "Fan: Timer 2 Hours",
    "Massage20MinuteTimer": "Fan: Timer 3 Hours",
    "Massage30MinuteTimer": "Fan: Timer 5 Hours",
}


async def invoke(controller: BedController, action: str, *, save: bool = False) -> None:
    await require_controller(controller, MlilyRemoteController).async_perform_casper_base_action(
        action, save=save
    )


class MlilyRemoteController(CasperBaseController):
    """Reuse product actions/memory mapping, with this app's lifecycle and gates."""

    profiles = PROFILES
    action_catalog = ACTIONS

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, product: str, layout: str = "single"
    ) -> None:
        super().__init__(coordinator, product=product)
        if layout not in ("single", "double"):
            raise ValueError("Choose single or double bed layout")
        self.layout = layout
        self._link: Link | None = None
        self._next_write = 0.0
        self._receiver = Receiver(self._event)
        self._alarm: dict[str, object] = {}
        self._pending_alarm: dict[str, object] | None = None
        self._error: str | None = None
        self._address = coordinator.address
        self._capabilities_changed = asyncio.Event()

    @property
    def supports_casper_base_controls(self) -> bool:
        return False

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        # The single-byte route cannot address either physical side.
        return self.layout == "double" and self._link is not None and not self._link.legacy

    @property
    def persisted_app_state_key(self) -> str:
        return "mlily_remote:" + self.model

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return deepcopy(self._alarm)

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        if state and (
            set(state) != {"hour", "minute", "mode"}
            or type(state["hour"]) is not int
            or not 0 <= state["hour"] < 24
            or type(state["minute"]) is not int
            or not 0 <= state["minute"] < 60
            or state["mode"] not in self.alarm_modes
        ):
            raise ValueError("Invalid saved MLILY Remote alarm")
        self._alarm = dict(state)

    @property
    def alarm_modes(self) -> tuple[str, ...]:
        return tuple(ACTIONS[i][0] for i in self.product[4])

    def _current(self) -> Link:
        link = self._link
        if (
            link is None
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address != self._address
        ):
            raise ConnectionError("MLILY Remote BLE session changed")
        return link

    def _side(self, link: Link) -> int:
        side = self.command_side
        if side in ("left", "right"):
            if link.legacy or self.layout != "double":
                raise ValueError("The Nordic route has no physical side selector")
            return int(side == "right")
        if side == "both":
            raise ValueError("MLILY Remote has no both-side opcode; target one child side")
        return 0

    async def _write(
        self,
        packet: bytes,
        link: Link,
        *,
        cleanup: bool = False,
        deadline: float | None = None,
        submitted: Callable[[], None] | None = None,
    ) -> bool:
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        async with self._ble_lock:
            await asyncio.sleep(max(0, self._next_write - loop.time()))
            if self._current() is not link:
                raise ConnectionError("MLILY Remote link was replaced while queued")
            if not cleanup and cancel.is_set():
                note_frame_skipped()
                return False
            if deadline is not None and loop.time() > deadline + 1e-9:
                return False
            self._next_write = loop.time() + TICK_S
            response = "write-without-response" not in link.tx.properties
            self._coordinator.record_command_trace(
                payload={"hex": packet.hex()},
                characteristic_uuid=link.tx.uuid,
                characteristic_handle=link.tx.handle,
                response=response,
                repeat_count=1,
                repeat_delay_ms=0,
                command_origin="mlily_remote",
                controller_class=type(self).__name__,
            )
            if submitted is not None:
                submitted()
            # A non-idempotent command is never replayed after a write failure.
            await link.client.write_gatt_char(link.tx, packet, response=response)
            note_frame_written()
        return True

    async def _send(self, packet: bytes, *, cleanup: bool = False) -> None:
        await self._write(packet, self._current(), cleanup=cleanup)

    async def _wait(self, delay: float) -> bool:
        try:
            await asyncio.wait_for(self._coordinator.cancel_command.wait(), max(0, delay))
        except TimeoutError:
            return True
        return False

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            "mlily_remote_" + name for name in self.actions if name.endswith(("Up", "Down"))
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or duration_ms < 100:
            raise ValueError("Choose an available MLILY Remote movement held for at least 100 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = control.removeprefix("mlily_remote_")
        link = self._current()
        side = self._side(link)
        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = start + self.leased_hold_ms(duration_ms) / 1000
        due = start + TICK_S
        attempted = False

        def submitted() -> None:
            nonlocal attempted
            attempted = True

        try:
            # First tick is delayed 100 ms. Drop missed ticks rather than backfilling.
            # A supported short hold gets its first tick even if scheduling was late;
            # once sent, its elapsed budget cannot be extended by slow writes.
            while due <= deadline + 1e-9 and await self._wait(due - loop.time()):
                if not await self._write(
                    codec.function(self.actions[action][0], side, single=link.legacy),
                    link,
                    deadline=deadline if attempted else deadline + TICK_S,
                    submitted=submitted,
                ):
                    break
                due = max(
                    due + TICK_S, start + (math.floor((loop.time() - start) / TICK_S) + 1) * TICK_S
                )
        finally:
            if (
                attempted
                and self._link is link
                and self.client is link.client
                and link.client.is_connected
            ):
                await self._write(
                    codec.function(codec.STOP, side, single=link.legacy), link, cleanup=True
                )

    async def async_perform_casper_base_action(
        self,
        action: str,
        *,
        save: bool = False,
        music_page: bool = False,
    ) -> None:
        item = self.actions.get(action)
        if music_page or item is None or save and item[1] is None:
            raise ValueError("Action unavailable for this MLILY Remote product")
        if action.endswith(("Up", "Down")):
            await self.hold_control("mlily_remote_" + action, 1000)
            return
        link = self._current()
        side = self._side(link)
        code = item[1] if save else item[0]
        assert code is not None
        if not save or await self._wait(SAVE_MS / 1000):
            await self._write(codec.function(code, side, single=link.legacy), link)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                hold=ControllerMotorHoldSpec(
                    "mlily_remote_" + name + "Up",
                    "mlily_remote_" + name + "Down",
                    stop_scope="side",
                    press_is_native=True,
                ),
            )
            for spec, name in (
                (
                    spec,
                    {
                        "back": "Head",
                        "legs": "Foot",
                        "head": "Pillow",
                        "lumbar": "Lumber",
                        "head_feet": "HeadAndFoot",
                    }[spec.key],
                )
                for spec in super().motor_control_specs
            )
        )

    def standard_button_requires_confirmation(self, key: str) -> bool:
        return key.startswith("program_memory_")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Flat and the memory slots are the shared preset_flat/preset_memory/
        # program_memory buttons; this adds only the product's other actions.
        cooling = PROFILES[self.model].cooling
        specs = []
        for name, (_, long) in self.actions.items():
            label = (COOLING_LABELS if cooling else LABELS).get(name)
            if label is None:
                continue
            card = (
                (CARD_CLIMATE if cooling else CARD_MASSAGE)
                if name.startswith("Massage")
                else CARD_LIGHTING
                if name == "BedLight"
                else CARD_PRESETS
            )
            for save in (False, True) if long is not None else (False,):
                title = ("Save " if save else "") + label
                prefix = "mlily_remote_"
                if cooling and name.startswith("Massage"):
                    prefix += "cooling_"
                key = prefix + name.lower() + ("_save" if save else "")
                specs.append(
                    ControllerButtonSpec(
                        key,
                        title,
                        partial(invoke, action=name, save=save),
                        translation_key=key,
                        translation_placeholders={"action": title},
                        requires_confirmation=save,
                        card=CARD_PRESET_SAVE if save else card,
                    )
                )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "mlily_remote",
                "mlily_remote",
                MODEL,
                "mdi:bed",
                # The product model, carrying received events, the saved alarm and the
                # last rejected reply as diagnostic attributes.
                attribute_keys=(EVENTS, ALARM, ERROR),
                entity_registry_enabled_default=False,
            ),
        )

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            MODEL(self.product[0]),
            EVENTS(deepcopy(self.events)),
            ALARM(deepcopy(self._alarm)),
            ERROR(self._error),
        )

    def _event(self, name: str, value: object) -> None:
        self.events[name] = value
        self._capabilities_changed.set()
        if name == "deviceAddAlarmSuccessEvent" and self._pending_alarm is not None:
            self._alarm, self._pending_alarm = self._pending_alarm, None
        elif name == "deviceCancelAlarmSuccessEvent":
            self._alarm.clear()
            self._pending_alarm = None
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("MLILY Remote is disconnected")
        if self._link is not None:
            await self.stop_notify()
        self.on_disconnect()
        # Bind encoding and notify to the write service, never the app's unsafe
        # last-route/first-write mixture on multi-service devices.
        from ...profiles.richmat import MLILY_REMOTE

        link = select_link(client, 1, MLILY_REMOTE, bind_framing=True, coherent_service=True)
        self._link = link
        self._write_char, self._notify_char, self._single = link.tx, link.rx, link.legacy
        self._next_write = asyncio.get_running_loop().time() + TICK_S
        try:
            await client.start_notify(link.rx, partial(self._notification, link))
            for action, code in STARTUP:
                if not await self._write(codec.function(code, action=action, single=link.legacy), link):
                    raise asyncio.CancelledError
            if not await self._write(codec.calendar(dt_util.now(), build=codec.record_20_len), link):
                raise asyncio.CancelledError
        except BaseException:
            await self.stop_notify()
            raise
        self._publish()

    def _notification(self, link: Link, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        self.forward_raw_notification(link.rx.uuid, bytes(data))
        self._receiver.feed(bytes(data))
        self._error = self._receiver.rejection
        self._publish()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.rx)

    def on_disconnect(self) -> None:
        self._link = None
        self._write_char = self._notify_char = None
        self._receiver.clear()
        self._capabilities_changed.set()
        self.events.clear()
        self._pending_alarm = None
        self._next_write = 0.0
        self._error = None
        self._publish()

    def validate_casper_base_request(self, request: Request) -> None:
        if request.operation not in ("alarm", "alarm_cancel", "time_sync", "anti_snore"):
            raise ValueError("Unsupported MLILY Remote operation")
        if request.operation == "anti_snore":
            if not PROFILES[self.model].phone_snore:
                raise ValueError("The default-left intervention belongs to MS300-SH")
            if self.command_side in ("right", "both"):
                raise ValueError("The default-left intervention requires the left owner")
        if request.operation in ("alarm", "alarm_cancel") and not self.alarm_modes:
            raise ValueError("This product has no alarm mode choices")
        if request.operation == "alarm" and (
            request.mode not in self.alarm_modes
            or not 0 <= request.hour < 24
            or not 0 <= request.minute < 60
        ):
            raise ValueError("Choose an alarm time and a mode offered by this product")

    async def async_prepare_request(self, request: Request) -> None:
        self.validate_casper_base_request(request)
        link = self._current()
        if request.operation in ("alarm", "alarm_cancel"):
            try:
                async with asyncio.timeout(3):  # HA readiness budget, not wire timing.
                    while "deviceCharacteristicsSubscriptionClockEvent" not in self.events:
                        self._capabilities_changed.clear()
                        await self._capabilities_changed.wait()
                        if self._current() is not link:
                            raise ConnectionError("MLILY Remote clock preflight lost its session")
            except TimeoutError:
                raise ValueError("This BLE session has not announced clock support") from None

    async def async_execute_casper_base_request(self, request: Request) -> None:
        await self.async_prepare_request(request)
        link = self._current()
        if request.operation in ("alarm", "alarm_cancel"):
            if "deviceCharacteristicsSubscriptionClockEvent" not in self.events:
                raise ValueError("This BLE session has not announced clock support")
            minutes = (
                alarm_countdown(request.hour, request.minute, dt_util.now())
                if request.operation == "alarm"
                else 0
            )
            code = self.actions[request.mode][0] if request.operation == "alarm" else 0
            self._pending_alarm = (
                {"hour": request.hour, "minute": request.minute, "mode": request.mode}
                if minutes
                else None
            )
            packets = codec.countdown(minutes, code)
        elif request.operation == "anti_snore":
            # The excluded phone detector's BED consequence uses default LEFT.
            packets = (codec.function(self.actions["AntiSnoring"][0], 0, single=link.legacy),)
        else:
            packets = (codec.calendar(dt_util.now(), build=codec.record_20_len),)
        try:
            for packet in packets:
                if not await self._write(packet, link):
                    self._pending_alarm = None
                    break
        except BaseException:
            self._pending_alarm = None
            raise

    async def stop_all(self) -> None:
        link = self._current()
        await self._write(
            codec.function(codec.STOP, self._side(link), single=link.legacy), link, cleanup=True
        )

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all


async def build_controller(ctx: BuildContext) -> MlilyRemoteController:
    return MlilyRemoteController(
        ctx.coordinator,
        product=ctx.variant or "",
        layout=str(ctx.data.get("product_type", "single")),
    )
