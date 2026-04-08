"""Sleep Number BAM / MCR controller.

This controller targets older Sleep Number 360 / i8 FlexFit bases that expose the
MCR UART GATT service instead of the newer Fuzion BamKey service.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from ..const import (
    SLEEP_NUMBER_MCR_RX_CHAR_UUID,
    SLEEP_NUMBER_MCR_TX_CHAR_UUID,
)
from .base import BedController

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
_MCR_FUNC_CHAMBER_TYPES: Final = 97
_MCR_FUNC_FOUNDATION_OUTLET: Final = 19

_MCR_SIDE_LEFT: Final = 0
_MCR_SIDE_RIGHT: Final = 1
_MCR_SIDE_BOTH_CHAMBERS: Final = 2
_MCR_SIDE_ALL: Final = 0x0F
_MCR_OUTLET_UNDERBED_LIGHT: Final = 3

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

# Seconds to cache a bed-presence result from _async_read_chamber_types.
# The legacy + per-side binary sensors each poll on their own update cycle
# but ``_async_read_chamber_types`` already refreshes both sides at once,
# so rapid follow-up polls within this window return the cached state.
_BED_PRESENCE_POLL_TTL_SECONDS: Final = 5.0


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


def _bed_address_from_mac(address: str) -> int:
    """Derive the BAM/MCR node address from the BLE MAC address."""
    parts = address.upper().replace("-", ":").split(":")
    return (int(parts[-2], 16) << 8) | int(parts[-1], 16)


class SleepNumberMcrController(BedController):
    """Controller for older Sleep Number BAM / MCR beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the controller."""
        super().__init__(coordinator)
        self._bed_address = _bed_address_from_mac(coordinator.address)
        self._notify_started = False
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
        self._sleep_numbers: dict[str, int | None] = {"left": None, "right": None}
        self._foundation_presets: dict[str, str | None] = {"left": None, "right": None}
        self._under_bed_lights_on: bool | None = None
        self._bed_presence: dict[str, str | None] = {"left": None, "right": None}
        self._occupancy_supported = False
        # Lock + TTL for dedup across the legacy + per-side bed-presence
        # binary sensors: each polls on its own update cycle and
        # _async_read_chamber_types already refreshes both sides in one
        # BAM/MCR query.
        self._bed_presence_lock = asyncio.Lock()
        self._bed_presence_last_poll_monotonic: float = 0.0

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the MCR RX characteristic UUID."""
        return SLEEP_NUMBER_MCR_RX_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        """MCR is request/response over notifications."""
        return True

    @property
    def supports_motor_control(self) -> bool:
        """This initial implementation exposes presets, not live motor control."""
        return False

    @property
    def supports_stop_all(self) -> bool:
        """Do not expose a generic stop button until foundation stop is verified."""
        return False

    @property
    def supports_lights(self) -> bool:
        """The BAM/MCR bed exposes discrete under-bed light control."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """The BAM/MCR bed has separate under-bed light on/off writes."""
        return True

    @property
    def supports_under_bed_lights(self) -> bool:
        """The BAM/MCR bed exposes a dedicated under-bed light outlet."""
        return True

    @property
    def supports_bed_presence(self) -> bool:
        """Expose bed presence only when the firmware returns occupancy bytes."""
        return self._occupancy_supported

    @property
    def supports_sleep_number_setting(self) -> bool:
        """Suppress the single-side Sleep Number entity for this dual-side bed."""
        return False

    @property
    def sleep_number_setting_sides(self) -> tuple[str, ...]:
        """Return the sides that expose firmness controls."""
        return ("left", "right")

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
        """Return the sides that can trigger foundation presets."""
        return ("left", "right")

    @property
    def foundation_preset_options(self) -> list[str]:
        """Return the supported foundation preset names."""
        return list(_SLEEP_NUMBER_MCR_PRESETS)

    @property
    def bed_presence_sides(self) -> tuple[str, ...]:
        """Return supported occupancy sides when the BAM firmware reports them."""
        if self._occupancy_supported:
            return ("left", "right")
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
        _notify_callback: Callable[[str, float], None] | None = None,
    ) -> None:
        """Subscribe to the MCR response characteristic and run the init handshake."""
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        if not self._notify_started:
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

    async def query_config(self) -> None:
        """Read the current BAM/MCR state after connect.

        Hydration steps are independent: a transient malformed reply to
        the pump-status read must not abort the rest of init, otherwise
        the under-bed light and chamber queries never run and the
        corresponding entities stay silently disabled for the session.
        Transport failures still propagate (those are retried at the
        coordinator level).
        """
        await self._async_initialize_session()
        try:
            await self._async_read_pump_status()
        except ValueError:
            _LOGGER.debug(
                "Sleep Number MCR pump-status read returned an unexpected"
                " payload during query_config; firmness state left unknown",
                exc_info=True,
            )
        await self._async_read_underbed_light_state()
        await self._async_read_chamber_types()

    async def set_sleep_number_setting_for_side(self, side: str, value: int) -> None:
        """Set firmness for one side."""
        normalized = _normalize_sleep_number_setting(value)
        side_value = self._side_value(side)

        await self._async_initialize_session()
        await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_FORCE_IDLE,
            side=0,
            timeout=3.0,
        )
        await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_SET,
            side=side_value,
            payload=bytes([0x00, normalized]),
            timeout=5.0,
        )

        self._sleep_numbers[side] = normalized
        self.forward_controller_state_updates({f"sleep_number_{side}": normalized})

    async def set_foundation_preset_for_side(self, side: str, preset: str) -> None:
        """Trigger a foundation preset for one side."""
        preset_value = _SLEEP_NUMBER_MCR_PRESETS.get(preset)
        if preset_value is None:
            raise ValueError(f"Unsupported Sleep Number MCR preset: {preset}")

        await self._async_initialize_session()
        await self._async_send_frame(
            command_type=_MCR_CMD_FOUNDATION,
            status=_MCR_STATUS_FOUNDATION,
            function_code=_MCR_FUNC_PRESET,
            side=self._side_value(side),
            payload=bytes([preset_value, 0x00]),
            timeout=5.0,
        )

        self._foundation_presets[side] = preset
        self.forward_controller_state_updates({f"foundation_preset_{side}": preset})

    async def lights_on(self) -> None:
        """Turn on the under-bed light."""
        await self._async_set_underbed_light(True)

    async def lights_off(self) -> None:
        """Turn off the under-bed light."""
        await self._async_set_underbed_light(False)

    async def read_bed_presence(self) -> bool | None:
        """Return the left-side occupancy when chamber occupancy is available.

        Always issues a fresh BAM/MCR chamber-type read. Entity polling
        should prefer ``read_bed_presence_cached`` below, which wraps this
        with a TTL cache so the legacy + per-side binary sensors don't
        double-poll.
        """
        if not self._occupancy_supported:
            return None

        await self._async_initialize_session()
        await self._async_read_chamber_types()
        self._bed_presence_last_poll_monotonic = asyncio.get_running_loop().time()
        return self._left_presence_bool()

    async def read_bed_presence_cached(self) -> bool | None:
        """Read bed presence with a short TTL cache for entity polling.

        Home Assistant polls the legacy ``bed_presence`` sensor alongside
        the new per-side sensors on their own update cycles. One
        ``_async_read_chamber_types`` call already refreshes both sides,
        so rapid follow-up polls inside the TTL window return the cached
        state rather than re-issuing the BAM/MCR query. This mirrors the
        Fuzion controller's behaviour.
        """
        if not self._occupancy_supported:
            return None

        async with self._bed_presence_lock:
            now = asyncio.get_running_loop().time()
            if (
                self._bed_presence["left"] is not None
                and now - self._bed_presence_last_poll_monotonic
                < _BED_PRESENCE_POLL_TTL_SECONDS
            ):
                return self._left_presence_bool()
            return await self.read_bed_presence()

    def _left_presence_bool(self) -> bool | None:
        """Normalize the cached left-side presence state to a bool/None."""
        if self._bed_presence["left"] == "in":
            return True
        if self._bed_presence["left"] == "out":
            return False
        return None

    async def move_head_up(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_head_down(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_head_stop(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_back_up(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_back_down(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_back_stop(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_legs_up(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_legs_down(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_legs_stop(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_feet_up(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_feet_down(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def move_feet_stop(self) -> None:
        """Older BAM/MCR support is preset/firmness-only in this integration."""
        raise NotImplementedError("Direct motor control is not implemented for Sleep Number MCR")

    async def stop_all(self) -> None:
        """Generic stop is intentionally not exposed for this controller."""
        raise NotImplementedError("Stop all is not implemented for Sleep Number MCR")

    async def preset_flat(self) -> None:
        """Move the left side to flat when called directly."""
        await self.set_foundation_preset_for_side("left", "Flat")

    async def preset_memory(self, memory_num: int) -> None:
        """Older BAM/MCR favorite/read presets are exposed via side selects."""
        raise NotImplementedError(f"Memory preset {memory_num} not supported for Sleep Number MCR")

    async def program_memory(self, memory_num: int) -> None:
        """Older BAM/MCR memory programming is not implemented."""
        raise NotImplementedError(
            f"Memory programming {memory_num} not supported for Sleep Number MCR"
        )

    async def _async_initialize_session(self) -> None:
        """Run the required MCR init handshake once per connection."""
        if self._initialized:
            return

        frames = await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_INIT,
            side=0,
            payload=b"\x00" * 8,
            sub_address=0x0000,
            timeout=10.0,
        )
        if not any(frame.function_code == _MCR_FUNC_INIT for frame in frames):
            raise RuntimeError("Sleep Number MCR init handshake failed")
        self._initialized = True

    async def _async_read_pump_status(self) -> None:
        """Read both side firmness values and publish them."""
        frames = await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_READ,
            side=_MCR_SIDE_ALL,
            timeout=5.0,
        )

        for frame in frames:
            if frame.function_code != _MCR_FUNC_READ or len(frame.payload) < 5:
                continue
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
            timeout=5.0,
        )

        for frame in frames:
            if (
                frame.function_code == _MCR_FUNC_FOUNDATION_LIGHT_READ
                and len(frame.payload) >= 1
            ):
                self._under_bed_lights_on = bool(frame.payload[0])
                self.forward_controller_state_updates(
                    {"under_bed_lights_on": self._under_bed_lights_on}
                )
                return

        _LOGGER.debug("Sleep Number MCR under-bed light query returned no state")

    async def _async_read_chamber_types(self) -> None:
        """Read chamber/occupancy state when the BAM firmware exposes it."""
        frames = await self._async_send_frame(
            command_type=_MCR_CMD_PUMP,
            status=_MCR_STATUS_PUMP,
            function_code=_MCR_FUNC_CHAMBER_TYPES,
            side=_MCR_SIDE_BOTH_CHAMBERS,
            payload=b"\x00\x00",
            timeout=5.0,
        )

        for frame in frames:
            if frame.function_code != _MCR_FUNC_CHAMBER_TYPES:
                continue
            if len(frame.payload) < 8:
                _LOGGER.debug(
                    "Sleep Number MCR chamber query returned %d bytes; occupancy not available",
                    len(frame.payload),
                )
                return
            self._occupancy_supported = True
            self._bed_presence["right"] = "in" if frame.payload[4] else "out"
            self._bed_presence["left"] = "in" if frame.payload[6] else "out"
            # Also publish the generic ``bed_presence`` key so the legacy
            # compatibility sensor (kept for non-breaking upgrades) reflects
            # fresh data. MCR has no "configured side" concept — we mirror
            # the left side to match ``read_bed_presence()`` /
            # ``_left_presence_bool()``.
            self.forward_controller_state_updates(
                {
                    "bed_presence": self._bed_presence["left"],
                    "bed_presence_left": self._bed_presence["left"],
                    "bed_presence_right": self._bed_presence["right"],
                }
            )
            return

    async def _async_set_underbed_light(self, is_on: bool) -> None:
        """Write the under-bed light outlet state."""
        await self._async_initialize_session()
        await self._async_send_frame(
            command_type=_MCR_CMD_FOUNDATION,
            status=_MCR_STATUS_FOUNDATION,
            function_code=_MCR_FUNC_FOUNDATION_OUTLET,
            side=_MCR_OUTLET_UNDERBED_LIGHT,
            payload=bytes([1 if is_on else 0, 0, 0]),
            timeout=5.0,
        )

        self._under_bed_lights_on = is_on
        self.forward_controller_state_updates({"under_bed_lights_on": is_on})

    async def _async_send_frame(
        self,
        *,
        command_type: int,
        status: int,
        function_code: int,
        side: int,
        payload: bytes = b"",
        sub_address: int | None = None,
        timeout: float = 5.0,
        cancel_event: asyncio.Event | None = None,
    ) -> list[_McrFrame]:
        """Write an MCR frame and wait for the matching notification response.

        Replies are correlated to the outstanding request via
        ``(function_code, side)``. The notification handler ignores any
        unrelated parsed frames (late replies from prior commands, stray
        broadcasts) so the waiter only wakes once a frame that actually
        matches this request is reassembled and parsed.

        The response wait races ``_response_event`` against the caller's
        ``cancel_event`` and the coordinator's cancel signal so that a
        cancellation or disconnect exits the wait promptly instead of
        holding the serialized BLE path until ``timeout`` expires.
        """
        frame = self._build_frame(
            command_type=command_type,
            status=status,
            function_code=function_code,
            side=side,
            payload=payload,
            sub_address=self._bed_address if sub_address is None else sub_address,
        )
        # Set correlation BEFORE clearing state, so any in-flight notification
        # parsing on the event loop sees the new key.
        self._outstanding_request_key = (function_code & 0x7F, side & 0x0F)
        self._response_buffer.clear()
        self._response_frames.clear()
        self._response_event.clear()

        try:
            await self._async_write_frame(frame, cancel_event=cancel_event)

            coordinator_cancel = self._coordinator.cancel_command
            response_task = asyncio.create_task(self._response_event.wait())
            cancel_tasks: list[asyncio.Task[bool]] = [
                asyncio.create_task(coordinator_cancel.wait())
            ]
            if cancel_event is not None and cancel_event is not coordinator_cancel:
                cancel_tasks.append(asyncio.create_task(cancel_event.wait()))

            try:
                done, _pending = await asyncio.wait(
                    {response_task, *cancel_tasks},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for task in (response_task, *cancel_tasks):
                    if not task.done():
                        task.cancel()
                for task in (response_task, *cancel_tasks):
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task

            if not done:
                raise TimeoutError(
                    f"Timed out waiting for Sleep Number MCR response func={function_code}"
                )
            if response_task not in done:
                raise asyncio.CancelledError(
                    f"Sleep Number MCR response wait cancelled func={function_code}"
                )

            return list(self._response_frames)
        finally:
            self._outstanding_request_key = None

    async def _async_write_frame(
        self, frame: bytes, *, cancel_event: asyncio.Event | None = None
    ) -> None:
        """Write an MCR frame using fire-and-forget GATT writes.

        The BAM/MCR protocol already provides an application-level response
        over the notify characteristic, and some ESPHome proxy paths drop the
        BLE connection while waiting for a lower-level GATT write response.
        Rely on the protocol frame reply for acknowledgement instead of the
        transport-level write response.
        """
        await self._write_gatt_with_retry(
            SLEEP_NUMBER_MCR_RX_CHAR_UUID,
            frame,
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
        if not frame.is_response:
            return False
        expected_func, expected_side = self._outstanding_request_key
        if frame.function_code != expected_func:
            return False
        # The MCR firmware sometimes echoes a different side nibble for
        # bed-wide queries (e.g. ``_MCR_SIDE_ALL`` reads). Treat the request
        # as matching whenever the side either matches exactly or the
        # request was sent against ``_MCR_SIDE_ALL`` /
        # ``_MCR_SIDE_BOTH_CHAMBERS``.
        if expected_side in {_MCR_SIDE_ALL, _MCR_SIDE_BOTH_CHAMBERS}:
            return True
        return frame.side == expected_side

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
    ) -> bytes:
        """Build an MCR wire frame."""
        header = bytes(
            [
                command_type,
                0x00,
                0x00,
                (sub_address >> 8) & 0xFF,
                sub_address & 0xFF,
                status,
                0x00,
                0x00,
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
