"""Sleep Number BAM / MCR controller.

This controller targets older Sleep Number 360 / i8 FlexFit bases that expose the
MCR UART GATT service instead of the newer Fuzion BamKey service.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import struct
import time
import zlib
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from ..const import (
    CONF_SLEEP_NUMBER_MCR_CLIENT_ID,
    SLEEP_NUMBER_MCR_RX_CHAR_UUID,
    SLEEP_NUMBER_MCR_TX_CHAR_UUID,
)
from .base import (
    POSITION_UNIT_PERCENT,
    BedController,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
)
from .sleep_number_mcr_protocol import (
    FoundationFeatures,
    classify_smartpump,
    decode_foundation,
    decode_massage,
    decode_pinch,
    decode_system,
    require_payload,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_MCR_SYNC: Final = b"\x16\x16"

_MCR_CMD_PUMP: Final = 0x02
_MCR_CMD_FOUNDATION: Final = 0x42

_MCR_STATUS_PUMP: Final = 0x02
_MCR_STATUS_FOUNDATION: Final = 0x42

_MCR_FUNC_INIT: Final = 0
_MCR_FUNC_FORCE_IDLE: Final = 2
_MCR_FUNC_SET: Final = 17
_MCR_FUNC_READ: Final = 18
_MCR_FUNC_PRESET: Final = 21
_MCR_FUNC_FOUNDATION_LIGHT_READ: Final = 20
_MCR_FUNC_FOUNDATION_OUTLET: Final = 19

_MCR_SIDE_LEFT: Final = 1
_MCR_SIDE_RIGHT: Final = 0
_MCR_SIDE_ALL: Final = 0x0F
_MCR_OUTLET_UNDERBED_LIGHT: Final = 3
_OPTIONAL_RESPONSE_GRACE_SECONDS: Final = 0.2
_INIT_HANDSHAKE_TIMEOUT_SECONDS: Final = 0.9
# HA safety bound: do not hold the serialized command path indefinitely.
_PUMP_CLEANUP_TIMEOUT_SECONDS: Final = 10.0
# SleepIQ's legacy FlexFit transition and continued-adjustment delays.
_FOUNDATION_POLL_SECONDS: Final = 0.333
_FOUNDATION_START_SECONDS: Final = 1.0
_FOUNDATION_SETTLE_SECONDS: Final = 0.5
# HA safety bound, not a firmware travel time or APK protocol constant.
_FOUNDATION_TIMEOUT_SECONDS: Final = 120.0
_FOUNDATION_CLEANUP_TIMEOUT_SECONDS: Final = 10.0

_SLEEP_NUMBER_MCR_PRESETS: Final[dict[str, int]] = {
    "Favorite": 1,
    "Read": 2,
    "Watch TV": 3,
    "Flat": 4,
    "Zero G": 5,
    "Snore": 6,
}

_SIDE_NAME_TO_VALUE: Final[dict[str, int]] = {
    "left": _MCR_SIDE_LEFT,
    "right": _MCR_SIDE_RIGHT,
}


# Semantic service schema: required fields, optional fields. No raw opcode interface.
_COMMAND_FIELDS: Final[dict[str, tuple[set[str], set[str]]]] = {
    "mcr_status": (set(), set()),
    "foundation_status": (set(), set()),
    "position": ({"side", "axis", "position"}, set()),
    "stop": ({"side"}, set()),
    "preset_save": ({"side", "preset"}, set()),
    "preset_reset": ({"side", "preset"}, set()),
    "preset_timer": ({"side", "preset", "timer"}, set()),
    "firmness_favorite": ({"side", "firmness"}, set()),
    "firmness_favorites": (set(), set()),
    "responsive_air": ({"side", "enabled"}, set()),
    "responsive_air_status": (set(), set()),
    "massage": ({"side"}, {"head", "foot", "mode", "timer"}),
    "massage_status": ({"side"}, set()),
    "foot_warming": ({"side", "level"}, {"duration"}),
    "foot_warming_status": ({"side"}, set()),
    "outlet": ({"outlet", "enabled"}, {"duration"}),
    "outlet_status": ({"outlet"}, set()),
    "light_intensity": ({"side", "intensity"}, set()),
    "underbed_auto": ({"enabled"}, set()),
    "underbed_auto_status": (set(), set()),
    "pinch_status": (set(), set()),
    "sense_and_do": ({"enabled"}, set()),
    "sense_and_do_status": (set(), set()),
    "kid_outlet": ({"device"}, {"outlet_on", "light_on"}),
    "kid_outlet_status": ({"device"}, set()),
    "head_tilt": ({"enabled"}, set()),
    "software_versions": (set(), set()),
}
_FOUNDATION_COMMANDS: Final = {
    "foundation_status",
    "position",
    "stop",
    "preset_save",
    "preset_reset",
    "preset_timer",
    "massage",
    "massage_status",
    "foot_warming",
    "foot_warming_status",
    "outlet",
    "outlet_status",
    "light_intensity",
    "underbed_auto",
    "underbed_auto_status",
    "pinch_status",
}


class _ResponseTimeout(TimeoutError):
    """A missing protocol response, retried separately from transport failures."""


@dataclass(slots=True)
class _McrFrame:
    """Parsed MCR frame."""

    command_type: int
    target: int
    sub_address: int
    status: int
    echo: int
    function_code: int
    side: int
    payload: bytes
    is_response: bool


def _mcr_crc(data: bytes) -> int:
    """Calculate the MCR Fletcher-style CRC."""
    s, r = 0, 0
    for value in data:
        s += value
        r += s
    return r & 0xFFFF


def _normalize_sleep_number_setting(value: int) -> int:
    """Clamp and snap Sleep Number firmness to the supported 5-point scale."""
    normalized = max(5, min(100, value))
    return int(round(normalized / 5) * 5)


def _motor_command(side: str, axis: str, direction: str) -> MotorCommandCallable:
    async def execute(controller: BedController) -> None:
        bound = controller.bind_side(side)
        if direction == "stop":
            await bound.stop_all()
        elif axis == "back":
            await (bound.move_back_up() if direction == "up" else bound.move_back_down())
        else:
            await (bound.move_legs_up() if direction == "up" else bound.move_legs_down())

    return execute


class SleepNumberMcrController(BedController):
    """Controller for older Sleep Number BAM / MCR beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        manufacturer_data: Mapping[int, bytes] | None = None,
    ) -> None:
        """Initialize the controller."""
        super().__init__(coordinator)
        self._bed_address = 0
        self._client_address = 0
        identifier = coordinator.entry.data.get(CONF_SLEEP_NUMBER_MCR_CLIENT_ID)
        self._client_identifier: int = (
            identifier
            if isinstance(identifier, int) and 0 < identifier < 1 << 64
            else (secrets.randbits(64) or 1)
        )
        self._foundation_features: FoundationFeatures | None = None
        self._nodes: set[int] = set()
        self._chambers: dict[str, int] = {}
        self._pressure_sides: tuple[str, ...] = ()
        self._massage_sides: tuple[str, ...] = ()
        self._chambers_present: tuple[bool, bool] = (False, False)
        self._pump_model = "unknown"
        for company, data in (manufacturer_data or {}).items():
            advertised = classify_smartpump(
                company.to_bytes(2, "little") + data, coordinator.address
            )
            if advertised["model"] != "unknown":
                self._pump_model = str(advertised["model"])
        self._state: dict[str, object] = {}
        self._notify_started = False
        self._notify_callback: Callable[[str, float], None] | None = None
        self._initialized = False
        self._response_buffer = bytearray()
        self._response_frames: list[_McrFrame] = []
        self._response_event = asyncio.Event()
        # Correlation key for the currently outstanding request, used to
        # ignore late notifications from the previous command and avoid
        # waking on unrelated frames. Each entry is a
        # ``(function_code, side)`` tuple matching the request that was
        # sent. ``None`` means no request is in flight.
        self._outstanding_request_key: tuple[int, int] | None = None
        self._outstanding_node: int | None = None
        # During the connection-priming init handshake, accept ANY notification
        # from the bed as confirmation, bypassing the strict per-frame
        # correlation below. Older BAM/MCR firmware echoes the init frame
        # without the response bit set (byte 8 & 0x80) or with a different side
        # nibble, which the strict matcher would otherwise discard — leaving the
        # handshake to time out and the connection stuck in a reconnect loop.
        # When an optional response times out, a delayed notification for the
        # same request key must not satisfy the next command. Keep the key
        # quarantined for a full timeout window after the miss so late replies
        # are drained before the key can be reused.
        self._quarantined_response_keys: dict[tuple[int, int], float] = {}
        self._sleep_numbers: dict[str, int | None] = {"left": None, "right": None}
        self._under_bed_lights_on: bool | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the MCR RX characteristic UUID."""
        return SLEEP_NUMBER_MCR_RX_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        """MCR is request/response over notifications."""
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        """MCR beds are kept connected for the entry's lifetime."""
        return True

    @property
    def supports_motor_control(self) -> bool:
        """Expose motor controls after foundation discovery."""
        return self._foundation_features is not None

    @property
    def supports_stop_all(self) -> bool:
        """The SE MFHR/MFHL commands stop foundation movement."""
        return self._foundation_features is not None

    @property
    def supports_lights(self) -> bool:
        """Only expose lighting reported by foundation system status."""
        return bool(self._foundation_features and self._foundation_features.light)

    @property
    def supports_discrete_light_control(self) -> bool:
        """The BAM/MCR bed has separate under-bed light on/off writes."""
        return self.supports_lights

    @property
    def supports_under_bed_lights(self) -> bool:
        """The BAM/MCR bed exposes a dedicated under-bed light outlet."""
        return self.supports_lights

    @property
    def supports_bed_presence(self) -> bool:
        """BAM/MCR occupancy probing is intentionally disabled."""
        return False

    @property
    def supports_sleep_number_setting(self) -> bool:
        """Suppress the single-side Sleep Number entity for this dual-side bed."""
        return False

    @property
    def sleep_number_setting_sides(self) -> tuple[str, ...]:
        """Return the sides that expose firmness controls."""
        return self._pressure_sides if self._pump_model != "genie" else ()

    @property
    def sleep_number_setting_min(self) -> int:
        """Return the minimum supported Sleep Number setting."""
        return 5

    @property
    def sleep_number_setting_max(self) -> int:
        """Return the maximum supported Sleep Number setting."""
        return 100

    @property
    def sleep_number_setting_step(self) -> int:
        """Return the supported Sleep Number increment."""
        return 5

    @property
    def foundation_preset_sides(self) -> tuple[str, ...]:
        """Expose only discovered foundation sides."""
        return self._foundation_features.sides if self._foundation_features else ()

    @property
    def foundation_preset_options(self) -> list[str]:
        """Return the supported foundation preset names."""
        return list(self._foundation_features.presets) if self._foundation_features else []

    @property
    def bed_presence_sides(self) -> tuple[str, ...]:
        """BAM/MCR occupancy sensors are not exposed."""
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        """Side-aware preset selects are used instead of generic buttons."""
        return False

    @property
    def supports_preset_zero_g(self) -> bool:
        """Side-aware preset selects are used instead of generic buttons."""
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        """Side-aware preset selects are used instead of generic buttons."""
        return False

    @property
    def supports_preset_tv(self) -> bool:
        """Side-aware preset selects are used instead of generic buttons."""
        return False

    async def start_notify(
        self,
        callback: Callable[[str, float], None] | None = None,
    ) -> None:
        """Subscribe to the MCR response characteristic and run the init handshake.

        Foundation reads publish position values through the supplied callback.
        """
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        if not self._notify_started:
            await asyncio.sleep(0.128)
            await client.start_notify(
                SLEEP_NUMBER_MCR_TX_CHAR_UUID,
                self._handle_mcr_notification,
            )
            self._notify_started = True

        self._initialized = False
        await self._async_initialize_session()

    async def stop_notify(self) -> None:
        """Unsubscribe from the MCR response characteristic."""
        client = self.client
        if client is not None and client.is_connected and self._notify_started:
            with contextlib.suppress(Exception):
                await client.stop_notify(SLEEP_NUMBER_MCR_TX_CHAR_UUID)
        self._notify_started = False
        self._initialized = False
        self._response_buffer.clear()
        self._response_frames.clear()
        self._response_event.clear()
        self._quarantined_response_keys.clear()

    async def query_config(self) -> None:
        """Discover nodes and hydrate only supported feature families."""
        await self._async_initialize_session()
        nodes = await self._mcr_request(0x72, 0x12)
        self._nodes = set(nodes)
        chambers = await self._mcr_request(0x02, 0x61, 2, b"\x00\x00")
        require_payload(chambers, 4)
        self._chambers = {"right": chambers[1], "left": chambers[3]}
        self._chambers_present = (bool(chambers[0]), bool(chambers[2]))
        if self._pump_model != "360":
            self._pump_model = (
                "genie"
                if 3 in self._chambers.values()
                else "k2"
                if 2 in self._chambers.values()
                else "k1"
                if 1 in self._chambers.values()
                else "adult"
            )
        self._publish(
            {
                "chamber_present_right": bool(chambers[0]),
                "chamber_present_left": bool(chambers[2]),
                "chamber_type_right": chambers[1],
                "chamber_type_left": chambers[3],
                "mcr_nodes": sorted(self._nodes),
                "pump_model": self._pump_model,
                "chamber_diagnostics_right": list(chambers[4:6]) if len(chambers) >= 8 else [0, 0],
                "chamber_diagnostics_left": list(chambers[6:8]) if len(chambers) >= 8 else [0, 0],
            }
        )
        await self._async_read_pump_status()
        with contextlib.suppress(ValueError):
            await self._read_favorites()
        if 0x41 in self._nodes:
            self._foundation_features, state = decode_system(await self._mcr_request(0x42, 0x25))
            self._publish(state)
            await self._read_foundation()
            if self.supports_lights:
                with contextlib.suppress(ValueError):
                    await self._async_read_underbed_light_state()
            if self.supports_massage:
                for side in ("left", "right"):
                    with contextlib.suppress(ValueError):
                        await self._read_massage(side)
            for side in self.footwarming_climate_sides:
                with contextlib.suppress(ValueError):
                    await self._read_warming(side)

    async def set_sleep_number_setting_for_side(self, side: str, value: int) -> None:
        if side not in self.sleep_number_setting_sides:
            raise ValueError("Pressure side is not present")
        await self._set_sleep_number_for_chamber(side, value)

    async def _set_sleep_number_for_chamber(self, side: str, value: int) -> None:
        """Set firmness for one side."""
        normalized = _normalize_sleep_number_setting(value)
        side_value = self._side_value(side)

        await self._async_initialize_session()
        await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_FORCE_IDLE,
            side=0,
            timeout=0.9,
            require_response=True,
        )
        try:
            await self._async_send_frame(
                command_type=_MCR_CMD_PUMP,
                status=_MCR_STATUS_PUMP,
                function_code=_MCR_FUNC_SET,
                side=side_value,
                payload=bytes([0x00, normalized]),
                timeout=0.9,
                require_response=True,
            )
        except BaseException:
            await self._idle_pump_after_cancel()
            raise

        self._sleep_numbers[side] = normalized
        self.forward_controller_state_updates({f"sleep_number_{side}": normalized})

    async def set_foundation_preset_for_side(self, side: str, preset: str) -> None:
        """Trigger a foundation preset for one side."""
        preset_value = _SLEEP_NUMBER_MCR_PRESETS.get(preset)
        if preset_value is None:
            raise ValueError(f"Unsupported Sleep Number MCR preset: {preset}")

        self._require_foundation(side)
        if preset not in self.foundation_preset_options:
            raise ValueError("Preset is not supported by the foundation")
        await self._async_initialize_session()
        recovery = preset == "Flat"
        pinch = await self._prepare_foundation_motion((side,), allow_homing=recovery)
        async with self._foundation_motion((side,)):
            async with asyncio.timeout(_FOUNDATION_TIMEOUT_SECONDS):
                await self._mcr_request(
                    0x42, 0x15, self._side_value(side), bytes([preset_value, 0])
                )
                targets = (
                    {f"foundation_{axis}_{side}": 0 for axis in self._foundation_axes}
                    if recovery
                    else {}
                )
                await self._wait_for_foundation(
                    (side,),
                    targets,
                    allow_homing=recovery,
                    expected_preset=None if recovery else preset,
                )
                await self._check_pinch((side,), previous=pinch)

    async def lights_on(self) -> None:
        """Turn on the under-bed light."""
        await self._async_set_underbed_light(True)

    async def lights_off(self) -> None:
        """Turn off the under-bed light."""
        await self._async_set_underbed_light(False)

    async def read_bed_presence(self) -> bool | None:
        """BAM/MCR occupancy sensors are not exposed in this integration."""
        return None

    async def read_bed_presence_cached(self) -> bool | None:
        """BAM/MCR occupancy sensors are not exposed in this integration."""
        return None

    async def move_head_up(self) -> None:
        await self._move_axis("head", 100)

    async def move_head_down(self) -> None:
        await self._move_axis("head", 0)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._move_axis("head", 100)

    async def move_back_down(self) -> None:
        await self._move_axis("head", 0)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_axis("foot", 100)

    async def move_legs_down(self) -> None:
        await self._move_axis("foot", 0)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._move_axis("foot", 100)

    async def move_feet_down(self) -> None:
        await self._move_axis("foot", 0)

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        """Always release both available sides with a fresh cancellation token."""
        sides = (self.command_side,) if self.command_side else self.foundation_preset_sides
        try:
            await self._stop_sides(sides)
        finally:
            await self._mcr_request(0x02, 0x02, cancel_event=asyncio.Event())

    async def preset_flat(self) -> None:
        """Move each available foundation side to flat."""
        for side in self.foundation_preset_sides:
            await self.set_foundation_preset_for_side(side, "Flat")

    async def preset_memory(self, memory_num: int) -> None:
        """Older BAM/MCR favorite/read presets are exposed via side selects."""
        raise NotImplementedError(f"Memory preset {memory_num} not supported for Sleep Number MCR")

    async def program_memory(self, memory_num: int) -> None:
        """Older BAM/MCR memory programming is not implemented."""
        raise NotImplementedError(
            f"Memory programming {memory_num} not supported for Sleep Number MCR"
        )

    async def _async_initialize_session(self) -> None:
        """Negotiate peer/client addresses using the persisted random identifier."""
        if self._initialized:
            return
        self._bed_address = self._client_address = 0
        frames = await self._async_send_frame(
            command_type=2,
            status=2,
            function_code=0,
            side=0,
            payload=self._client_identifier.to_bytes(8, "big"),
            sub_address=0,
            timeout=_INIT_HANDSHAKE_TIMEOUT_SECONDS,
        )
        for frame in frames:
            if len(frame.payload) >= 10:
                self._client_address = int.from_bytes(frame.payload[8:10], "big")
                self._bed_address = frame.target
                self._initialized = True
                return
        raise ValueError("MCR bind response omitted assigned addresses")

    async def _idle_pump_after_cancel(self) -> None:
        token = asyncio.Event()
        deadline = asyncio.timeout(_PUMP_CLEANUP_TIMEOUT_SECONDS)
        try:
            async with deadline:
                await self._mcr_request(2, 2, cancel_event=token)
                while True:
                    await asyncio.sleep(0.5)
                    await self._async_read_pump_status(cancel_event=token)
                    if not self._state.get("pump_adjusting", False):
                        return
        except TimeoutError as exc:
            if not deadline.expired():
                raise
            raise TimeoutError(
                "Could not confirm that the Sleep Number pump stopped before the cleanup "
                "deadline; check the bed and its Bluetooth connection"
            ) from exc

    async def _async_read_pump_status(self, *, cancel_event: asyncio.Event | None = None) -> None:
        """Read both side firmness values and publish them."""
        frames = await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_READ,
            side=0,
            timeout=0.9,
            require_response=True,
            cancel_event=cancel_event,
        )

        for frame in frames:
            if frame.function_code != _MCR_FUNC_READ or len(frame.payload) < 3:
                continue
            if frame.side not in (0, 1):
                raise ValueError("Invalid pump chamber configuration")
            self._pressure_sides = (
                ("right", "left")
                if frame.side == 1
                and all(self._chambers_present)
                and 1 not in self._chambers.values()
                else ("right",)
            )
            self._publish(
                {"pump_adjusting": frame.payload[0] != 0, "pump_dual_chamber": frame.side == 1}
            )
            self._sleep_numbers["left"] = frame.payload[1]
            self._sleep_numbers["right"] = frame.payload[2]
            self.forward_controller_state_updates(
                {
                    "sleep_number_left": frame.payload[1],
                    "sleep_number_right": frame.payload[2],
                }
            )
            return

        raise ValueError("Sleep Number MCR pump status query returned no usable payload")

    async def _async_read_underbed_light_state(self) -> None:
        """Read and publish the under-bed light state."""
        frames = await self._async_send_frame(
            command_type=_MCR_CMD_FOUNDATION,
            status=_MCR_STATUS_FOUNDATION,
            function_code=_MCR_FUNC_FOUNDATION_LIGHT_READ,
            side=_MCR_OUTLET_UNDERBED_LIGHT,
            timeout=0.9,
            require_response=True,
        )

        for frame in frames:
            if frame.function_code == _MCR_FUNC_FOUNDATION_LIGHT_READ and len(frame.payload) >= 1:
                self._under_bed_lights_on = bool(frame.payload[0])
                self.forward_controller_state_updates(
                    {"under_bed_lights_on": self._under_bed_lights_on}
                )
                return

        _LOGGER.debug("Sleep Number MCR under-bed light query returned no state")

    async def _async_set_underbed_light(self, is_on: bool) -> None:
        """Write the under-bed light outlet state."""
        await self._async_initialize_session()
        await self._async_send_frame(
            command_type=_MCR_CMD_FOUNDATION,
            status=_MCR_STATUS_FOUNDATION,
            function_code=_MCR_FUNC_FOUNDATION_OUTLET,
            side=_MCR_OUTLET_UNDERBED_LIGHT,
            payload=bytes([1 if is_on else 0, 0, 0]),
            timeout=0.9,
            require_response=True,
        )

        self._under_bed_lights_on = is_on
        self.forward_controller_state_updates({"under_bed_lights_on": is_on})

    @property
    def supports_position_feedback(self) -> bool:
        return self._foundation_features is not None

    @property
    def reports_percentage_position(self) -> bool:
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        return self._foundation_features is not None

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = (
            ("back", "legs")
            if self._foundation_features and self._foundation_features.foot
            else ("back",)
        )
        return tuple(
            MotorControlSpec(
                key=f"{axis}_{side}",
                translation_key=f"{axis}_{side}",
                position_key=f"{side}_{axis}",
                max_angle=100,
                open_fn=_motor_command(side, axis, "up"),
                close_fn=_motor_command(side, axis, "down"),
                stop_fn=_motor_command(side, axis, "stop"),
            )
            for side in self.foundation_preset_sides
            for axis in axes
        )

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return tuple(
            PositionNumberSpec(
                key=spec.key.replace("_", "_position_", 1),
                translation_key=spec.key.replace("_", "_position_", 1),
                position_key=spec.position_key or spec.key,
                icon="mdi:bed",
                native_max_value=100,
                native_unit_of_measurement=POSITION_UNIT_PERCENT,
                open_fn=spec.open_fn,
                close_fn=spec.close_fn,
                stop_fn=spec.stop_fn,
            )
            for spec in self.motor_control_specs
        )

    async def read_positions(self, motor_count: int = 2) -> None:
        await self._read_foundation()

    async def set_motor_position(self, motor: str, position: int) -> None:
        if motor.startswith(("left_", "right_")):
            side, motor = motor.split("_", 1)
        else:
            side = self.command_side or "right"
        if motor not in ("head", "back", "legs", "feet"):
            raise ValueError("Unknown motor")
        if not 0 <= position <= 100:
            raise ValueError("Position must be 0..100")
        await self._set_position(side, "head" if motor in ("head", "back") else "foot", position)

    def angle_to_native_position(self, motor: str, angle: float) -> int:
        return max(0, min(100, round(angle)))

    @property
    def supports_footwarming_climate(self) -> bool:
        return bool(self.footwarming_climate_sides)

    async def turn_footwarming_on_for_side(self, side: str) -> None:
        await self.set_footwarming_preset_for_side(side, "low")

    async def turn_footwarming_off_for_side(self, side: str) -> None:
        await self.set_footwarming_preset_for_side(side, "off")

    async def set_footwarming_preset_for_side(self, side: str, preset: str) -> None:
        levels = {"off": 0, "low": 1, "medium": 2, "high": 3}
        if preset not in levels:
            raise ValueError("Unknown foot warming preset")
        timer = self._state.get(f"foot_warming_timer_{side}", 120)
        duration = timer if isinstance(timer, int) and timer > 0 else 120
        await self.set_footwarming_for_side(side, levels[preset], duration if levels[preset] else 0)

    @property
    def supports_massage(self) -> bool:
        return bool(self._foundation_features and self._foundation_features.massage)

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def footwarming_climate_sides(self) -> tuple[str, ...]:
        return (
            (("right", "left") if len(self._pressure_sides) == 2 else ("left",))
            if self._foundation_features and self._foundation_features.warming
            else ()
        )

    def _publish(self, updates: dict[str, object]) -> None:
        for side in set(self.foundation_preset_sides) | set(self.footwarming_climate_sides):
            for axis, key in (("head", "back"), ("foot", "legs")):
                value = updates.get(f"foundation_{axis}_{side}")
                if isinstance(value, (int, float)) and self._notify_callback is not None:
                    self._notify_callback(f"{side}_{key}", float(value))
            level = updates.get(f"foot_warming_temperature_{side}")
            if isinstance(level, int):
                updates[f"footwarming_hvac_mode_{side}"] = "heat" if level else "off"
                updates[f"footwarming_preset_{side}"] = ("off", "low", "medium", "high")[level]
                updates[f"footwarming_level_{side}"] = level
                duration = updates.get(f"foot_warming_timer_{side}")
                if isinstance(duration, int):
                    updates[f"footwarming_remaining_time_minutes_{side}"] = duration
        self._state.update(updates)
        self.forward_controller_state_updates(updates)

    async def _mcr_request(
        self,
        node: int,
        opcode: int,
        sub: int = 0,
        payload: bytes = b"",
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> bytes:
        frames = await self._async_send_frame(
            command_type=node,
            status=node,
            function_code=opcode,
            side=sub,
            payload=payload,
            timeout=1.8 if opcode == 0x1D and sub in (9, 10, 11, 12, 13, 14) else 0.9,
            cancel_event=cancel_event,
        )
        if not frames:
            raise ValueError("MCR response is empty")
        frame = frames[0]
        if node == 0x52 and (
            frame.side == 15 or opcode == 0x1D and sub in (1, 2) and frame.side == 14
        ):
            raise ValueError("Sleep Expert rejected the request")
        return frame.payload

    async def _se_read(self, key: str) -> bytes:
        key_bytes = key.encode("ascii")
        if key not in ("SREL", "SRFS"):
            frames = await self._async_send_frame(
                command_type=0x52, status=0x52, function_code=0x1C, side=0, payload=key_bytes
            )
            if not frames:
                raise ValueError("Sleep Expert read returned no reply")
            if frames[0].side == 15:
                raise ValueError("Sleep Expert read rejected")
            if frames[0].side != 14:
                return frames[0].payload
        header = await self._mcr_request(0x52, 0x1D, 2, key_bytes)
        if len(header) != 8:
            raise ValueError("Invalid Sleep Expert long read header")
        crc, length = struct.unpack(">II", header)
        if length > 1024 * 1024:
            raise ValueError("Sleep Expert response exceeds safe allocation bound")
        data = bytearray()
        empty = 0
        index = 0
        while len(data) < length:
            chunk = await self._mcr_request(0x52, 0x1D, 12 + index % 3)
            empty = empty + 1 if not chunk else 0
            if empty >= 3 or len(data) + len(chunk) > length:
                raise ValueError("Invalid Sleep Expert long read chunk")
            data.extend(chunk)
            index += 1
        if zlib.crc32(data) != crc:
            raise ValueError("Sleep Expert CRC32 mismatch")
        return bytes(data)

    async def _se_write(
        self, key: str, value: bytes, *, cancel_event: asyncio.Event | None = None
    ) -> None:
        """All exposed control values fit the artifact's safe short-write boundary."""
        if len(key) != 4 or len(value) > 11:
            raise ValueError("Sleep Expert short value must fit eleven bytes")
        await self._mcr_request(
            0x52, 0x1B, payload=key.encode("ascii") + value, cancel_event=cancel_event
        )

    async def _read_foundation(
        self, *, keep_adjusting: str | None = None, cancel_event: asyncio.Event | None = None
    ) -> dict[str, object]:
        selector = 0 if keep_adjusting is None else self._side_value(keep_adjusting) + 2
        state = decode_foundation(
            await self._mcr_request(0x42, 0x12, selector, cancel_event=cancel_event)
        )
        self._publish(state)
        return state

    async def _read_favorites(self) -> dict[str, object]:
        payload = await self._mcr_request(2, 0x14)
        require_payload(payload, 2)
        state: dict[str, object] = {
            "sleep_number_favorite_right": payload[0],
            "sleep_number_favorite_left": payload[1],
        }
        self._publish(state)
        return state

    async def _read_massage(self, side: str) -> dict[str, object]:
        state = decode_massage(await self._mcr_request(0x42, 0x1A, self._side_value(side)), side)
        self._publish(state)
        if side not in self._massage_sides:
            self._massage_sides = (*self._massage_sides, side)
        return state

    async def _read_warming(self, side: str) -> dict[str, object]:
        payload = await self._mcr_request(0x42, 0x2A, self._side_value(side))
        require_payload(payload, 3)
        level = {31: 1, 57: 2, 72: 3}.get(payload[0], 0)
        state: dict[str, object] = {
            f"foot_warming_temperature_{side}": level,
            f"foot_warming_timer_{side}": int.from_bytes(payload[1:3], "little", signed=True),
        }
        self._publish(state)
        return state

    async def _stop_side(self, side: str) -> None:
        await self._se_write(
            "MFHL" if side == "left" else "MFHR", b"110", cancel_event=asyncio.Event()
        )

    async def _stop_sides(self, sides: tuple[str, ...]) -> None:
        failure: BaseException | None = None
        for side in sides:
            try:
                async with asyncio.timeout(_FOUNDATION_CLEANUP_TIMEOUT_SECONDS):
                    await self._stop_side(side)
            except BaseException as exc:
                if failure is None:
                    failure = exc
        if failure is not None:
            raise failure

    async def _set_position(self, side: str, axis: str, position: int) -> None:
        self._require_foundation(side, axis)
        pinch = await self._prepare_foundation_motion((side,))
        key = ("MFU" if axis == "head" else "MFF") + ("L" if side == "left" else "R")
        async with self._foundation_motion((side,)):
            async with asyncio.timeout(_FOUNDATION_TIMEOUT_SECONDS):
                await self._se_write(key, f"{position}_0".encode("ascii"))
                await self._wait_for_foundation((side,), {f"foundation_{axis}_{side}": position})
                await self._check_pinch((side,), previous=pinch)

    async def _move_axis(self, axis: str, target: int) -> None:
        """Maintain microadjust with side-specific status requests, then release."""
        sides = (self.command_side,) if self.command_side else self.foundation_preset_sides
        for side in sides:
            self._require_foundation(side, axis)
        pinch = await self._prepare_foundation_motion(sides)
        async with self._foundation_motion(sides):
            async with asyncio.timeout(_FOUNDATION_TIMEOUT_SECONDS):
                for side in sides:
                    payload = bytearray(b"\xff" * 12)
                    offset = 0 if axis == "head" else 2
                    payload[offset : offset + 2] = bytes((target, 0))
                    await self._mcr_request(0x42, 0x11, self._side_value(side), bytes(payload))
            count, delay = self.motor_pulse_settings()
            # The configured hold bounds BLE waits too, not just sleeps.
            hold = asyncio.timeout(min(count * delay / 1000, _FOUNDATION_TIMEOUT_SECONDS))
            try:
                async with hold:
                    moving = True
                    while moving:
                        await self._foundation_delay(_FOUNDATION_POLL_SECONDS)
                        for side in sides:
                            state = await self._read_foundation(keep_adjusting=side)
                            self._check_foundation(state, sides)
                            moving = self._foundation_is_moving(state)
                            if not moving:
                                break
            except TimeoutError:
                if not hold.expired():
                    raise
        await self._check_pinch(sides, previous=pinch)

    @property
    def _foundation_axes(self) -> tuple[str, ...]:
        return (
            ("head", "foot")
            if self._foundation_features and self._foundation_features.foot
            else ("head",)
        )

    def _check_foundation(
        self, state: Mapping[str, object], sides: tuple[str, ...], *, allow_homing: bool = False
    ) -> None:
        if not state["foundation_configured"]:
            raise ValueError("Foundation is not configured")
        for side in sides:
            for axis in self._foundation_axes:
                for diagnostic in ("limit", "current", "movement"):
                    value = state[f"foundation_{axis}_{side}_{diagnostic}"]
                    if value != "normal":
                        raise ValueError(f"Foundation {side} {axis}: {diagnostic} is {value}")
        if state["foundation_needs_homing"] and not allow_homing:
            raise ValueError("Foundation needs homing; use the Flat preset to recover")

    async def _check_pinch(
        self, sides: tuple[str, ...], *, previous: Mapping[str, object] | None = None
    ) -> dict[str, object]:
        # The artifact queries obstruction sensors only for 360 foundations.
        if not self._foundation_features or self._foundation_features.generation != "360":
            return {}
        state = decode_pinch(await self._mcr_request(0x42, 0x28))
        self._publish(state)
        for side in sides:
            for axis in self._foundation_axes:
                key = f"pinch_{axis}_{side}"
                if state[f"{key}_disconnected"] or state[f"{key}_continuous"]:
                    raise ValueError(f"Foundation {side} {axis}: obstruction sensor fault")
        # A non-split foundation compares obstruction events on both sides.
        event_sides = (
            sides if self._foundation_features.configuration in (1, 2) else ("right", "left")
        )
        for side in event_sides:
            for axis in self._foundation_axes:
                key = f"pinch_{axis}_{side}"
                events = state[f"{key}_events"]
                before = previous.get(f"{key}_events") if previous else None
                # Conservatively reject any counter change, including signed wrap/reset.
                if isinstance(events, int) and isinstance(before, int) and events != before:
                    raise ValueError(
                        f"Foundation {side} {axis}: obstruction counter changed during movement"
                    )
        return state

    async def _prepare_foundation_motion(
        self, sides: tuple[str, ...], *, allow_homing: bool = False
    ) -> dict[str, object]:
        self._check_foundation(await self._read_foundation(), sides, allow_homing=allow_homing)
        return await self._check_pinch(sides)

    async def _foundation_delay(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._coordinator.cancel_command.wait(), seconds)
        except TimeoutError:
            return
        raise asyncio.CancelledError("Foundation movement cancelled")

    @staticmethod
    def _foundation_is_moving(state: Mapping[str, object]) -> bool:
        return any(
            state[f"foundation_{axis}_{side}_moving"]
            for side in ("right", "left")
            for axis in ("head", "foot")
        )

    async def _wait_for_foundation(
        self,
        sides: tuple[str, ...],
        targets: Mapping[str, int],
        *,
        allow_homing: bool = False,
        expected_preset: str | None = None,
    ) -> None:
        await self._foundation_delay(_FOUNDATION_START_SECONDS)
        stationary = 0
        while True:
            state = await self._read_foundation()
            self._check_foundation(state, sides, allow_homing=allow_homing)
            moving = self._foundation_is_moving(state)
            stationary = 0 if moving else stationary + 1
            # Confirm an initial stationary reply with two more samples.
            if stationary == 3:
                self._check_foundation(state, sides)
                if expected_preset is not None:
                    for side in sides:
                        if state[f"foundation_preset_{side}"] != expected_preset:
                            raise ValueError(
                                f"Foundation stopped without confirming {side} preset {expected_preset}"
                            )
                for key, target in targets.items():
                    actual = state[key]
                    if not isinstance(actual, int) or abs(actual - target) >= 3:
                        raise ValueError(
                            f"Foundation stopped before reaching {key} target {target}: {actual}"
                        )
                return
            await self._foundation_delay(
                _FOUNDATION_POLL_SECONDS if moving else _FOUNDATION_SETTLE_SECONDS
            )

    @contextlib.asynccontextmanager
    async def _foundation_motion(self, sides: tuple[str, ...]) -> AsyncIterator[None]:
        try:
            yield
        except BaseException:
            try:
                await self._finish_foundation_motion(sides)
            except Exception:
                _LOGGER.warning("Foundation cleanup failed after movement error", exc_info=True)
            raise
        else:
            await self._finish_foundation_motion(sides)

    async def _finish_foundation_motion(self, sides: tuple[str, ...]) -> None:
        released = False
        try:
            await self._stop_sides(sides)
            released = True
        finally:
            # Release and final readback must survive the movement's cancel signal.
            try:
                async with asyncio.timeout(_FOUNDATION_CLEANUP_TIMEOUT_SECONDS):
                    state = await self._read_foundation(cancel_event=asyncio.Event())
                self._check_foundation(state, sides)
            except Exception:
                if released:
                    raise
                _LOGGER.warning(
                    "Could not refresh foundation positions after release", exc_info=True
                )

    def _require_foundation(self, side: str, axis: str | None = None) -> None:
        if not self._foundation_features or side not in self._foundation_features.sides:
            raise ValueError("Foundation side is not present")
        if axis == "foot" and not self._foundation_features.foot:
            raise ValueError("Foundation has no foot actuator")

    async def _change_massage(
        self, field: str, *, step: int | None = None, toggle: bool = False
    ) -> None:
        if not self.supports_massage:
            raise ValueError("Massage unavailable")
        sides = (self.command_side,) if self.command_side else self._massage_sides
        for side in sides:
            status = await self._read_massage(side)
            current = status[f"massage_{field}_{side}"]
            if not isinstance(current, int):
                raise ValueError("Invalid massage state")
            level = (0 if current else 1) if toggle else max(0, min(3, current + (step or 0)))
            await self.async_execute_sleep_number_command("massage", {"side": side, field: level})
            await self._read_massage(side)

    async def massage_toggle(self) -> None:
        await self._change_massage("head", toggle=True)
        await self._change_massage("foot", toggle=True)

    async def massage_head_toggle(self) -> None:
        await self._change_massage("head", toggle=True)

    async def massage_foot_toggle(self) -> None:
        await self._change_massage("foot", toggle=True)

    async def massage_head_up(self) -> None:
        await self._change_massage("head", step=1)

    async def massage_head_down(self) -> None:
        await self._change_massage("head", step=-1)

    async def massage_foot_up(self) -> None:
        await self._change_massage("foot", step=1)

    async def massage_foot_down(self) -> None:
        await self._change_massage("foot", step=-1)

    async def massage_intensity_up(self) -> None:
        await self.massage_head_up()
        await self.massage_foot_up()

    async def massage_intensity_down(self) -> None:
        await self.massage_head_down()
        await self.massage_foot_down()

    async def massage_mode_step(self) -> None:
        if not self.supports_massage:
            raise ValueError("Massage unavailable")
        for side in (self.command_side,) if self.command_side else self._massage_sides:
            status = await self._read_massage(side)
            mode = status[f"massage_mode_{side}"]
            if not isinstance(mode, int):
                raise ValueError("Invalid massage mode")
            await self.async_execute_sleep_number_command(
                "massage", {"side": side, "mode": (mode + 1) % 4}
            )

    async def massage_off(self) -> None:
        for side in (self.command_side,) if self.command_side else self._massage_sides:
            await self.async_execute_sleep_number_command(
                "massage", {"side": side, "head": 0, "foot": 0, "mode": 0}
            )

    async def set_footwarming_for_side(self, side: str, level: int, timer: int = 120) -> None:
        await self.async_execute_sleep_number_command(
            "foot_warming", {"side": side, "level": level, "duration": timer}
        )

    @property
    def sleep_number_command_names(self) -> tuple[str, ...]:
        return tuple(_COMMAND_FIELDS)

    def validate_sleep_number_command(self, command: str, parameters: Mapping[str, object]) -> None:
        fields = _COMMAND_FIELDS.get(command)
        if fields is None:
            raise ValueError(f"Unsupported Sleep Number MCR command: {command}")
        required, optional = fields
        if parameters.keys() - (required | optional) or required - parameters.keys():
            raise ValueError(
                f"Invalid parameters for {command}; required: {sorted(required)}, optional: {sorted(optional)}"
            )
        for name, value in parameters.items():
            if name == "side":
                if value not in ("left", "right"):
                    raise ValueError("side must be left or right")
            elif name == "axis":
                if value not in ("head", "foot"):
                    raise ValueError("axis must be head or foot")
            elif name == "preset":
                if not isinstance(value, str) or value not in _SLEEP_NUMBER_MCR_PRESETS:
                    raise ValueError("Unknown foundation preset")
            elif name in ("enabled", "outlet_on", "light_on"):
                if not isinstance(value, bool):
                    raise ValueError(f"{name} must be boolean")
            elif name == "level":
                if type(value) is not int or not 0 <= value <= 3:
                    raise ValueError("level must be 0..3")
            elif name in ("head", "foot", "mode"):
                if type(value) is not int or not 0 <= value <= 3:
                    raise ValueError(f"{name} must be 0..3")
            elif name in ("position", "firmness"):
                if type(value) is not int or not 0 <= value <= 100:
                    raise ValueError(f"{name} must be 0..100")
                if name == "firmness" and (value < 5 or value % 5):
                    raise ValueError("firmness must be 5..100 in increments of 5")
            elif name in ("duration", "timer"):
                if type(value) is not int or not 0 <= value <= 32767:
                    raise ValueError(f"{name} must be 0..32767")
            elif name in ("outlet", "device"):
                if type(value) is not int or not (1 if name == "outlet" else 0) <= value <= (
                    4 if name == "outlet" else 15
                ):
                    raise ValueError(f"Invalid {name} selector")
            elif name == "intensity":
                if type(value) is not int or value not in (1, 30, 45, 75, 100):
                    raise ValueError("Unsupported light intensity")
        side = str(parameters.get("side", "right"))
        if self.command_side is not None and "side" in parameters and side != self.command_side:
            raise ValueError("Command side cannot override the selected bed side")
        if (
            command in ("firmness_favorite", "responsive_air")
            and side not in self.sleep_number_setting_sides
        ):
            raise ValueError("Pressure side is not present")
        if command in _FOUNDATION_COMMANDS and command not in (
            "foot_warming",
            "foot_warming_status",
            "massage",
            "massage_status",
            "light_intensity",
        ):
            self._require_foundation(
                side, str(parameters["axis"]) if "axis" in parameters else None
            )
        if command in ("massage", "massage_status") and (
            not self.supports_massage or side not in self._massage_sides
        ):
            raise ValueError("Foundation does not support massage")
        if (
            command in ("foot_warming", "foot_warming_status")
            and side not in self.footwarming_climate_sides
        ):
            raise ValueError("Foundation does not support foot warming")
        if (
            command in ("kid_outlet", "kid_outlet_status", "head_tilt")
            and 2 not in self._chambers.values()
        ):
            raise ValueError("Bed does not have a head-tilt/K2 chamber")
        if command in ("responsive_air", "responsive_air_status") and self._pump_model != "360":
            raise ValueError("Responsive Air requires a discovered 360 pump")
        if (
            command
            in (
                "responsive_air",
                "responsive_air_status",
                "software_versions",
                "underbed_auto",
                "underbed_auto_status",
            )
            and 0x51 not in self._nodes
        ):
            raise ValueError("Sleep Expert node is absent")
        if command in ("outlet", "outlet_status", "light_intensity"):
            if not self._foundation_features:
                raise ValueError("Foundation unavailable")
            if command == "light_intensity":
                allowed = ({1, 30, 100} if self._foundation_features.light else set()) | (
                    {45, 75, 100} if self._foundation_features.massage else set()
                )
                if (
                    not (self._foundation_features.light or self._foundation_features.massage)
                    or parameters["intensity"] not in allowed
                ):
                    raise ValueError("Light intensity is not supported by this foundation")
            elif parameters["outlet"] == 3 and self._foundation_features.light:
                pass
            elif not self._foundation_features.massage:
                raise ValueError("Legacy lighting/outlets are not supported")
        if command in ("underbed_auto", "underbed_auto_status") and not self.supports_lights:
            raise ValueError("Under-bed lighting unavailable")
        if command == "massage" and not (parameters.keys() & {"head", "foot", "mode", "timer"}):
            raise ValueError("massage requires at least one setting")
        if command == "kid_outlet" and not (parameters.keys() & {"outlet_on", "light_on"}):
            raise ValueError("kid_outlet requires an outlet or light setting")
        if (
            command in ("preset_save", "preset_reset", "preset_timer")
            and parameters["preset"] not in self.foundation_preset_options
        ):
            raise ValueError("Preset is not supported by the foundation")
        if command == "sense_and_do" or command == "sense_and_do_status":
            if 0x31 not in self._nodes:
                raise ValueError("Sense-and-do node is absent")

    async def async_execute_sleep_number_command(
        self, command: str, parameters: Mapping[str, object]
    ) -> dict[str, object]:
        """Execute an allowlisted semantic operation inside coordinator locking."""
        self.validate_sleep_number_command(command, parameters)
        side = str(parameters.get("side", "right"))
        sub = self._side_value(side)

        # Schema validation above ensures these scalar conversions are safe.
        def number(name: str, default: int = 0) -> int:
            value = parameters.get(name, default)
            if not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            return value

        if command == "mcr_status":
            await self.query_config()
            return dict(self._state)
        if command == "foundation_status":
            return await self._read_foundation()
        if command == "position":
            await self._set_position(side, str(parameters["axis"]), number("position"))
        elif command == "stop":
            await self._stop_side(side)
        elif command == "preset_save":
            await self._mcr_request(
                0x42, 0x16, sub, bytes((_SLEEP_NUMBER_MCR_PRESETS[str(parameters["preset"])],))
            )
        elif command == "preset_reset":
            await self._se_write(
                "MFRL" if side == "left" else "MFRR",
                str(_SLEEP_NUMBER_MCR_PRESETS[str(parameters["preset"])]).encode(),
            )
        elif command == "preset_timer":
            payload = bytearray(b"\xff" * 12)
            payload[7:9] = number("timer").to_bytes(2, "little")
            payload[9] = _SLEEP_NUMBER_MCR_PRESETS[str(parameters["preset"])]
            await self._mcr_request(0x42, 0x11, sub, bytes(payload))
        elif command == "firmness_favorite":
            await self._mcr_request(2, 0x13, sub, bytes((number("firmness"),)))
        elif command == "firmness_favorites":
            return await self._read_favorites()
        elif command == "responsive_air":
            await self._se_write(
                "LRLE" if side == "left" else "LRRE",
                int(bool(parameters["enabled"])).to_bytes(4, "big"),
            )
        elif command == "responsive_air_status":
            reply = await self._se_read("LRSG")
            require_payload(reply, 1)
            result: dict[str, object] = {
                "responsive_air_right": bool(reply[0] & 1),
                "responsive_air_left": bool(reply[0] & 2),
            }
            self._publish(result)
            return result
        elif command == "massage":
            payload = bytearray(b"\xff" * 12)
            for name, offset in (("head", 4), ("foot", 5), ("mode", 6)):
                if name in parameters:
                    payload[offset] = number(name)
            if "mode" not in parameters and parameters.keys() & {"head", "foot"}:
                payload[6] = 0
            if "timer" in parameters and number("timer") != 255:
                payload[10:12] = number("timer").to_bytes(2, "little")
            await self._mcr_request(0x42, 0x11, sub, bytes(payload))
        elif command == "massage_status":
            return await self._read_massage(side)
        elif command == "foot_warming":
            duration = number("duration", 120 if number("level") else 0)
            warming_sides = (
                (side, "right" if side == "left" else "left")
                if self._pump_model == "360" and len(self._pressure_sides) == 1
                else (side,)
            )
            for warming_side in warming_sides:
                await self._mcr_request(
                    0x42,
                    0x29,
                    self._side_value(warming_side),
                    bytes(((0, 31, 57, 72)[number("level")],)) + duration.to_bytes(2, "little"),
                )
                self._publish(
                    {
                        f"foot_warming_temperature_{warming_side}": number("level"),
                        f"foot_warming_timer_{warming_side}": duration,
                    }
                )
        elif command == "foot_warming_status":
            return await self._read_warming(side)
        elif command == "outlet":
            await self._mcr_request(
                0x42,
                0x13,
                number("outlet"),
                bytes((int(bool(parameters["enabled"])),))
                + number("duration").to_bytes(2, "little"),
            )
        elif command == "outlet_status":
            reply = await self._mcr_request(0x42, 0x14, number("outlet"))
            require_payload(reply, 3)
            return {
                "enabled": bool(reply[0]),
                "duration": int.from_bytes(reply[1:3], "little", signed=True),
            }
        elif command == "light_intensity":
            payload = bytearray(b"\xff\xff\xff")
            payload[1 if side == "right" else 2] = number("intensity")
            await self._mcr_request(0x42, 0x24, payload=bytes(payload))
        elif command == "underbed_auto":
            await self._se_write("MUAS", bytes((int(bool(parameters["enabled"])),)))
        elif command == "underbed_auto_status":
            reply = await self._se_read("MUAG")
            value = 0
            for byte in reply[:4]:
                value = (value << 8) + (byte if byte < 128 else byte - 256)
            return {"enabled": value == 1}
        elif command == "pinch_status":
            return decode_pinch(await self._mcr_request(0x42, 0x28))
        elif command == "sense_and_do":
            await self._mcr_request(
                0x32, 0x14, payload=bytes((1, 0 if parameters["enabled"] else 1))
            )
        elif command == "sense_and_do_status":
            reply = await self._mcr_request(0x32, 0x12)
            require_payload(reply, 2)
            return {"enabled": reply[1] == 0}
        elif command == "kid_outlet":
            await self._mcr_request(
                0x92,
                0x13,
                number("device"),
                bytes(
                    (
                        int(bool(parameters["outlet_on"])) if "outlet_on" in parameters else 255,
                        int(bool(parameters["light_on"])) if "light_on" in parameters else 255,
                        0,
                    )
                ),
            )
        elif command == "kid_outlet_status":
            reply = await self._mcr_request(0x92, 0x12)
            require_payload(reply, number("device") + 1)
            value = reply[number("device")]
            return {
                "light_on": bool(value & 2),
                "outlet_on": bool(value & 1),
                "status_update_requested": bool(value & 4),
                "in_use": not bool(value & 16),
            }
        elif command == "head_tilt":
            tilt_side = "left" if self._chambers.get("left") == 2 else "right"
            await self._set_sleep_number_for_chamber(tilt_side, 100 if parameters["enabled"] else 5)
        elif command == "software_versions":
            bammit = (await self._se_read("SREL")).decode("utf-8", errors="replace")
            rfs = (await self._se_read("SRFS")).decode("utf-8", errors="replace")
            return {"bammit": bammit, "rfs": rfs, "software": bammit.split("_")[0].replace("Z", "")}
        return {}

    async def _async_send_frame(
        self,
        *,
        command_type: int,
        status: int,
        function_code: int,
        side: int,
        payload: bytes = b"",
        sub_address: int | None = None,
        timeout: float = 0.9,
        cancel_event: asyncio.Event | None = None,
        require_response: bool = True,
    ) -> list[_McrFrame]:
        """Retry a missing response three times, as the MCR BlobCall does."""
        for attempt in range(4):
            try:
                return await self._async_send_frame_once(
                    command_type=command_type,
                    status=status,
                    function_code=function_code,
                    side=side,
                    payload=payload,
                    sub_address=sub_address,
                    timeout=timeout,
                    cancel_event=cancel_event,
                    require_response=require_response,
                )
            except _ResponseTimeout:
                if attempt == 3:
                    raise
        raise AssertionError("Unreachable MCR retry state")

    async def _async_send_frame_once(
        self,
        *,
        command_type: int,
        status: int,
        function_code: int,
        side: int,
        payload: bytes = b"",
        sub_address: int | None = None,
        timeout: float = 0.9,
        cancel_event: asyncio.Event | None = None,
        require_response: bool = True,
    ) -> list[_McrFrame]:
        """Write an MCR frame and wait for the matching notification response.

        Replies are correlated to the outstanding request via
        ``(function_code, side)``. When an optional response times out,
        the same request key is quarantined for a full timeout window so
        a delayed reply cannot satisfy the next command that reuses that
        key.

        The response wait races ``_response_event`` against the caller's
        ``cancel_event`` and the coordinator's cancel signal so that a
        cancellation or disconnect exits the wait promptly instead of
        holding the serialized BLE path until ``timeout`` expires.

        Optional responses only wait a short grace window. This keeps
        BAM/MCR write-only operations from holding the coordinator's
        serialized BLE path for the full 3-5 second timeout when the
        firmware simply never echoes an acknowledgement.
        """
        frame = self._build_frame(
            command_type=command_type,
            status=status,
            function_code=function_code,
            side=side,
            payload=payload,
            sub_address=self._bed_address if sub_address is None else sub_address,
            client_address=self._client_address,
        )
        request_key = self._request_key(function_code, side)
        await self._async_wait_for_response_quarantine(
            request_key, function_code=function_code, side=side, cancel_event=cancel_event
        )
        # Set correlation BEFORE clearing state, so any in-flight notification
        # parsing on the event loop sees the new key.
        self._outstanding_request_key = request_key
        self._outstanding_node = command_type
        self._response_buffer.clear()
        self._response_frames.clear()
        self._response_event.clear()

        try:
            await self._async_write_frame(frame, cancel_event=cancel_event)

            coordinator_cancel = (
                cancel_event if cancel_event is not None else self._coordinator.cancel_command
            )
            response_task = asyncio.create_task(self._response_event.wait())
            cancel_tasks: list[asyncio.Task[bool]] = [
                asyncio.create_task(coordinator_cancel.wait())
            ]
            if cancel_event is not None and cancel_event is not coordinator_cancel:
                cancel_tasks.append(asyncio.create_task(cancel_event.wait()))

            response_timeout = (
                timeout if require_response else min(timeout, _OPTIONAL_RESPONSE_GRACE_SECONDS)
            )

            try:
                done, _pending = await asyncio.wait(
                    {response_task, *cancel_tasks},
                    timeout=response_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for task in (response_task, *cancel_tasks):
                    if not task.done():
                        task.cancel()
                # Collect child cancellation without swallowing cancellation of
                # this request (including the pump-cleanup deadline).
                await asyncio.gather(response_task, *cancel_tasks, return_exceptions=True)

            if not done:
                if not require_response:
                    self._quarantine_response_key(
                        request_key,
                        deadline=time.monotonic() + timeout,
                    )
                    _LOGGER.debug(
                        "Sleep Number MCR frame timed out without a matching response "
                        "during the optional %.3fs grace window (func=%s side=%s); "
                        "continuing without retry",
                        response_timeout,
                        function_code,
                        side,
                    )
                    return list(self._response_frames)
                raise _ResponseTimeout(
                    f"Timed out waiting for Sleep Number MCR response func={function_code}"
                )
            if response_task not in done:
                raise asyncio.CancelledError(
                    f"Sleep Number MCR response wait cancelled func={function_code}"
                )

            return list(self._response_frames)
        finally:
            self._outstanding_request_key = None
            self._outstanding_node = None

    async def _async_write_frame(
        self, frame: bytes, *, cancel_event: asyncio.Event | None = None
    ) -> None:
        """Preserve proxy-compatible writes and fragment at the negotiated ATT MTU."""
        client = self.client
        if client is None:
            raise ConnectionError("Not connected to bed")
        characteristic = client.services.get_characteristic(SLEEP_NUMBER_MCR_RX_CHAR_UUID)
        properties = characteristic.properties if characteristic is not None else ()
        if "write" not in properties and "write-without-response" not in properties:
            raise ValueError("MCR characteristic has no writable property")
        mtu = client.mtu_size
        size = max(1, mtu - 3) if isinstance(mtu, int) else 20
        for offset in range(0, len(frame), size):
            chunk = frame[offset : offset + size]
            # ESPHome can drop unacknowledged writes despite the advertised
            # properties. Local adapters may enforce those properties instead.
            try:
                await self._write_gatt_with_retry(
                    SLEEP_NUMBER_MCR_RX_CHAR_UUID,
                    chunk,
                    cancel_event=cancel_event,
                    response=True,
                )
            except (BleakError, TimeoutError, OSError):
                if "write-without-response" not in properties:
                    raise
                await self._write_gatt_with_retry(
                    SLEEP_NUMBER_MCR_RX_CHAR_UUID,
                    chunk,
                    cancel_event=cancel_event,
                    response=False,
                )

    def _handle_mcr_notification(self, _sender: object, data: bytearray) -> None:
        """Handle an MCR notification frame."""
        raw = bytes(data)
        self.forward_raw_notification(SLEEP_NUMBER_MCR_TX_CHAR_UUID, raw)
        self._response_buffer.extend(raw)
        parsed_frame = False
        for frame in self._extract_response_frames():
            parsed_frame = True
            if (quarantined_key := self._matching_quarantined_request_key(frame)) is not None:
                _LOGGER.debug(
                    "Ignoring late Sleep Number MCR notification for quarantined request "
                    "(func=%s side=%s quarantined=%s)",
                    frame.function_code,
                    frame.side,
                    quarantined_key,
                )
                continue
            if not self._frame_matches_outstanding_request(frame):
                _LOGGER.debug(
                    "Ignoring Sleep Number MCR notification that does not match"
                    " the outstanding request (func=%s side=%s outstanding=%s)",
                    frame.function_code,
                    frame.side,
                    self._outstanding_request_key,
                )
                continue
            self._response_frames.append(frame)
            self._response_event.set()
        if not parsed_frame:
            _LOGGER.debug(
                "Sleep Number MCR notification buffered awaiting more data: %s",
                raw.hex(),
            )

    def _frame_matches_outstanding_request(self, frame: _McrFrame) -> bool:
        """Return True when ``frame`` is the response to the in-flight request."""
        if self._outstanding_request_key is None:
            return False
        return self._frame_matches_request_key(frame, self._outstanding_request_key)

    def _frame_matches_request_key(
        self,
        frame: _McrFrame,
        request_key: tuple[int, int],
    ) -> bool:
        """Match negotiated addresses and opcode, plus SE chunk selectors."""
        expected_func, expected_side = request_key
        if self._outstanding_node is not None and (frame.command_type & 0xF0) != (
            self._outstanding_node & 0xF0
        ):
            return False
        if not frame.is_response or frame.sub_address != self._client_address:
            return False
        if frame.sub_address == 0:
            return frame.function_code == expected_func
        if frame.echo != self._bed_address or frame.function_code != expected_func:
            return False
        if expected_func == 0x1D and expected_side in (9, 10, 11, 12, 13, 14):
            return frame.side == expected_side or frame.side == 15
        return True

    @staticmethod
    def _request_key(function_code: int, side: int) -> tuple[int, int]:
        """Normalize the request correlation tuple."""
        return (function_code & 0x7F, side & 0x0F)

    def _prune_response_quarantine(self) -> None:
        """Drop expired quarantined request keys."""
        now = time.monotonic()
        expired_keys = [
            request_key
            for request_key, deadline in self._quarantined_response_keys.items()
            if deadline <= now
        ]
        for request_key in expired_keys:
            self._quarantined_response_keys.pop(request_key, None)

    def _quarantine_response_key(self, request_key: tuple[int, int], *, deadline: float) -> None:
        """Ignore late replies for ``request_key`` until ``deadline``."""
        current_deadline = self._quarantined_response_keys.get(request_key)
        if current_deadline is None or deadline > current_deadline:
            self._quarantined_response_keys[request_key] = deadline

    def _matching_quarantined_request_key(self, frame: _McrFrame) -> tuple[int, int] | None:
        """Return the quarantined request key that ``frame`` matches, if any."""
        self._prune_response_quarantine()
        for request_key in self._quarantined_response_keys:
            if self._frame_matches_request_key(frame, request_key):
                return request_key
        return None

    async def _async_wait_for_response_quarantine(
        self,
        request_key: tuple[int, int],
        *,
        function_code: int,
        side: int,
        cancel_event: asyncio.Event | None,
    ) -> None:
        """Wait until a timed-out optional request key is safe to reuse."""
        while True:
            self._prune_response_quarantine()
            deadline = self._quarantined_response_keys.get(request_key)
            if deadline is None:
                return

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._quarantined_response_keys.pop(request_key, None)
                return

            _LOGGER.debug(
                "Waiting %.3fs before reusing Sleep Number MCR request key "
                "(func=%s side=%s) after an optional timeout",
                remaining,
                function_code,
                side,
            )

            coordinator_cancel = (
                cancel_event if cancel_event is not None else self._coordinator.cancel_command
            )
            wait_task = asyncio.create_task(asyncio.sleep(remaining))
            cancel_tasks: list[asyncio.Task[bool]] = [
                asyncio.create_task(coordinator_cancel.wait())
            ]
            if cancel_event is not None and cancel_event is not coordinator_cancel:
                cancel_tasks.append(asyncio.create_task(cancel_event.wait()))

            try:
                done, _pending = await asyncio.wait(
                    {wait_task, *cancel_tasks},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for task in (wait_task, *cancel_tasks):
                    if not task.done():
                        task.cancel()
                for task in (wait_task, *cancel_tasks):
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

            if wait_task in done:
                self._quarantined_response_keys.pop(request_key, None)
                return

            raise asyncio.CancelledError(
                f"Sleep Number MCR request reuse cancelled func={function_code}"
            )

    def _extract_response_frames(self) -> list[_McrFrame]:
        """Parse as many complete MCR frames as possible from the notification buffer."""
        frames: list[_McrFrame] = []

        while True:
            if len(self._response_buffer) < 2:
                break

            sync_index = self._response_buffer.find(_MCR_SYNC)
            if sync_index < 0:
                self._response_buffer.clear()
                break
            if sync_index > 0:
                del self._response_buffer[:sync_index]

            if len(self._response_buffer) < 12:
                break

            payload_length = self._response_buffer[11] & 0x0F
            frame_length = 14 + payload_length
            if len(self._response_buffer) < frame_length:
                break

            raw_frame = bytes(self._response_buffer[:frame_length])
            del self._response_buffer[:frame_length]

            frame = self._parse_frame(raw_frame)
            if frame is None:
                _LOGGER.debug(
                    "Ignoring unparseable Sleep Number MCR notification: %s",
                    raw_frame.hex(),
                )
                continue
            frames.append(frame)

        return frames

    @staticmethod
    def _build_frame(
        *,
        command_type: int,
        status: int,
        function_code: int,
        side: int,
        payload: bytes,
        sub_address: int,
        client_address: int = 0,
    ) -> bytes:
        """Build an MCR wire frame."""
        if len(payload) > 15:
            raise ValueError("MCR payload exceeds 15 bytes")
        header = bytes(
            [
                command_type,
                (client_address >> 8) & 0xFF,
                client_address & 0xFF,
                (sub_address >> 8) & 0xFF,
                sub_address & 0xFF,
                status,
                (client_address >> 8) & 0xFF,
                client_address & 0xFF,
                function_code,
                ((side & 0x0F) << 4) | (len(payload) & 0x0F),
            ]
        )
        body = header + payload
        return _MCR_SYNC + body + struct.pack(">H", _mcr_crc(body))

    @staticmethod
    def _parse_frame(data: bytes) -> _McrFrame | None:
        """Parse an MCR frame from a notification payload."""
        if len(data) < 14 or not data.startswith(_MCR_SYNC):
            return None

        body = data[2:-2]
        expected_crc = struct.unpack(">H", data[-2:])[0]
        if _mcr_crc(body) != expected_crc:
            return None

        if len(body) < 10:
            return None

        payload_length = body[9] & 0x0F
        payload = body[10 : 10 + payload_length]
        if len(payload) != payload_length:
            return None

        raw_function = body[8]
        return _McrFrame(
            command_type=body[0],
            target=(body[1] << 8) | body[2],
            sub_address=(body[3] << 8) | body[4],
            status=body[5],
            echo=(body[6] << 8) | body[7],
            function_code=raw_function & 0x7F,
            side=(body[9] >> 4) & 0x0F,
            payload=payload,
            is_response=bool(raw_function & 0x80),
        )

    @staticmethod
    def _side_value(side: str) -> int:
        """Convert a human-readable side name to the MCR selector nibble."""
        try:
            return _SIDE_NAME_TO_VALUE[side]
        except KeyError as err:
            raise ValueError(f"Unsupported Sleep Number MCR side: {side}") from err
