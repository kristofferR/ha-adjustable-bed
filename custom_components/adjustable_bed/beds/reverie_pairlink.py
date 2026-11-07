"""Reverie Pairlink controller and verified local-peer callback boundary.

The local BlueZ GATT server is a separate transport role owned by
``reverie_pairlink_transport``. Central writes still use HA's connected BLE
client. Local peer writes reach the entry-owned session reducer only after the
transport verifies the current BlueZ peer identity. The reducer learns session
keys and source state from the current transport callbacks; the accepted
zero-initialized virtual address remains valid until a source command replaces it.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

from bleak.exc import BleakError
from homeassistant.helpers.storage import Store

from ..card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_UTILITY
from ..const import CONF_SIDE
from ..controller_state import StateKey, StateUpdate
from ..state_keys import (
    LIGHT_LEVEL,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
    massage_zone_intensity,
    rgb_triple,
)
from .base import (
    POSITION_UNIT_PERCENT,
    BedController,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .builder import BuildContext
from .reverie_comfort import ReverieComfortRequest, validate_comfort_request
from .reverie_pairlink_profile import (
    PAIRLINK_BED_TYPES,
    PairlinkAdvertisement,
    build_pairlink_peripheral_profile,
    parse_pairlink_manufacturer_data,
    resolve_pairlink_model,
)
from .reverie_pairlink_protocol import (
    PAIRLINK_BROADCAST_ADDRESS,
    PAIRLINK_EXIT_COMMAND,
    PAIRLINK_LOW_POWER_NOTIFY_UUID,
    PAIRLINK_LOW_POWER_SERVICE_UUID,
    PAIRLINK_LOW_POWER_WRITE_UUID,
    PAIRLINK_NOTIFY_UUID,
    PAIRLINK_SERVICE_UUID,
    PAIRLINK_WRITE_UUID,
    GattWriter,
    a7_payload,
    build_user_frame,
    comfort_payloads,
    dashboard_payload,
    encrypt_user_frame,
    normalize_mac,
    parse_state_event,
    send_central_frame,
    state_query_payloads,
    status_sync_payloads,
)
from .reverie_pairlink_runtime import (
    PairlinkClockResponse,
    PairlinkComfortPlan,
    PairlinkEffect,
    PairlinkMeshEvent,
    PairlinkMeshStatusEvent,
    PairlinkPeerLifecycleEvent,
    PairlinkPeerLifecycleKind,
    PairlinkRole,
    PairlinkRuntime,
    PairlinkRuntimeNotReadyError,
    PairlinkSdkFrame,
    PairlinkSdkNative,
    PairlinkSendReply,
    PairlinkSendSnapshot,
    PairlinkWelcome,
    create_pairlink_runtime_for_entry,
)
from .reverie_pairlink_sdk import (
    PairlinkSdkMessage,
    calendar_payload,
    calendar_profile_frame,
    sdk_composition,
    sdk_low_power_device,
    sdk_mac,
    sdk_ping_device,
)
from .reverie_pairlink_sdk_dispatch import (
    PairlinkSdkCallbackEvent,
    PairlinkSdkReadError,
    decode_sdk_dispatch,
)
from .reverie_pairlink_sdk_metadata import (
    SdkCompositionQuery,
    SdkFingerprintQuery,
    SdkFingerprintStatus,
    SdkMetadataEffect,
    SdkMetadataStatus,
    SdkMetadataTimer,
)
from .reverie_pairlink_sdk_models import (
    PairlinkSdkDevice,
    replace_ping_device,
)
from .reverie_pairlink_sdk_storage import PairlinkSdkState
from .reverie_pairlink_transport import (
    PairlinkHostAdapterInventoryEntry,
    PairlinkPeerIdentity,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _field_key(name: str) -> StateKey[object]:
    """A decoded Pairlink event field."""
    return StateKey[object](name)


MASSAGE_TIMER: Final = StateKey[int | None]("reverie_massage_timer")
MASSAGE_MODE: Final = _field_key("reverie_massage_mode")
MASSAGE_MODE_OPTION: Final = StateKey[str | None]("reverie_massage_mode_option")
MASSAGE_RHYTHM_OPTION: Final = StateKey[str | None]("reverie_massage_rhythm_option")
LOW_BATTERY: Final = _field_key("pairlink_low_battery")


# Decoded fields that entities read, published under their typed keys.
_INTEGER_KEYS: Final[dict[str, StateKey[int | None]]] = {
    key: key
    for key in (
        LIGHT_LEVEL,
        MASSAGE_TIMER,
        massage_zone_intensity("head"),
        massage_zone_intensity("foot"),
    )
}
_OPTION_KEYS: Final[dict[str, StateKey[str | None]]] = {
    key: key for key in (MASSAGE_MODE_OPTION, MASSAGE_RHYTHM_OPTION)
}


def _state_update(name: str, value: object) -> StateUpdate:
    """Publish a decoded field; the ones entities read under their typed keys."""
    if name == UNDER_BED_LIGHTS_ON:
        return UNDER_BED_LIGHTS_ON(value if isinstance(value, bool) else None)
    if name == UNDER_BED_LIGHTS_RGB:
        return UNDER_BED_LIGHTS_RGB(rgb_triple(value))
    if (integer_key := _INTEGER_KEYS.get(name)) is not None:
        integer = value if isinstance(value, int) and not isinstance(value, bool) else None
        return integer_key(integer)
    if (option_key := _OPTION_KEYS.get(name)) is not None:
        return option_key(value if isinstance(value, str) else None)
    return _field_key(name)(value)


def _state_updates(values: Mapping[str, object]) -> list[StateUpdate]:
    return [_state_update(name, value) for name, value in values.items()]


PairlinkMeshEventCallback = Callable[[int, bytes | None, bool], None]


class _TracedCentralWriter:
    """Record each fragment ``send_central_frame`` writes, then write it."""

    def __init__(self, controller: BedController, client: GattWriter) -> None:
        self._controller = controller
        self._client = client

    async def write_gatt_char(
        self, char_specifier: str, data: bytes, response: bool | None = None
    ) -> None:
        self._controller._record_command_trace(
            char_specifier, data, response=bool(response), command_origin="pairlink"
        )
        await self._client.write_gatt_char(char_specifier, data, response=response)


class ReveriePairlinkController(BedController):
    """Controller for the app's R510L/Harmoniq Pairlink profiles."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        model: str | None = None,
        device_name: str | None = None,
        manufacturer_data: dict[int, bytes] | None = None,
        runtime: PairlinkRuntime | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.advertisement: PairlinkAdvertisement | None = parse_pairlink_manufacturer_data(
            manufacturer_data
        )
        self.model_id = resolve_pairlink_model(self.advertisement, device_name, model)
        if runtime is None:
            entry = coordinator.entry
            runtime = create_pairlink_runtime_for_entry(
                entry.data,
                entry.options,
                manufacturer_data=manufacturer_data,
            )
            coordinator._pairlink_runtime = runtime
        self._runtime = runtime
        runtime._central_status_callback = self._consume_central_library_status
        self._sdk_status_callback: Callable[
            [PairlinkSdkFrame | PairlinkMeshStatusEvent], None
        ] = self._consume_sdk_status8
        self._write_uuid = PAIRLINK_WRITE_UUID
        self._notify_uuid = PAIRLINK_NOTIFY_UUID
        self._active_notifications: list[str] = []
        self._event_callback: PairlinkMeshEventCallback | None = None
        self._sign_gate = runtime.sign_gate
        self._state: dict[str, object] = {}
        self._peer_states: dict[str, dict[str, object]] = {}
        self._peer_state_identities: dict[str, PairlinkPeerIdentity] = {}
        self._known_device_vaddrs: set[
            tuple[str, PairlinkPeerIdentity | None, bytes]
        ] = set()
        self._sdk_epoch = runtime.epoch
        if runtime._sdk_state is None:
            runtime._sdk_state = PairlinkSdkState(
                lambda: Store(
                    coordinator.hass, 1,
                    f"adjustable_bed.pairlink_sdk.{coordinator.entry.entry_id}"
                    + (
                        f".{normalize_mac(coordinator.address)}"
                        if coordinator.entry.data.get(CONF_SIDE) in ("left", "right")
                        else ""
                    ),
                ),
                self._async_sdk_metadata_effect,
            )
        self._sdk_entry_state = runtime._sdk_state
        self._sdk_devices = self._sdk_entry_state.devices
        self._sdk_owners = self._sdk_entry_state.owners
        self._sdk_views = self._sdk_entry_state.views
        self._sdk_views.on_clear = self._sdk_restore_clear
        self._sdk_views.on_restore = self._sdk_restore_device
        self._sdk_io = self._sdk_entry_state.io
        self._sdk_io._emit = self._async_sdk_metadata_effect
        self._sdk_metadata = self._sdk_entry_state.metadata
        self._sdk_receive_lock = self._sdk_entry_state.receive_lock
        self._sdk_context: PairlinkSdkFrame | PairlinkSdkNative | None = None
        self._sdk_lib_calc_status = True  # source MeshService.libCaclStatus
        self._sdk_timers: dict[str, asyncio.TimerHandle] = {}
        self._sdk_timer_generation: dict[str, int] = {}
        self._sdk_status_delegate: Callable[[int], None] | None = None
        self._sdk_low_power_callback: Callable[[PairlinkSdkDevice], None] = lambda _bean: None
        runtime._sdk_exit_callback = self._async_sdk_exit
        # MeshCallback's vendor method is inherited as a no-op by the app.
        self._sdk_vendor_callback: Callable[[PairlinkSdkMessage], None] = (
            self._ignore_sdk_vendor_data
        )
        self._sdk_aux_callback: Callable[[PairlinkSdkCallbackEvent], None] = (
            self._ignore_sdk_aux_callback
        )
        self._notify_callback: Callable[[str, float], None] | None = None
        self._routine_settings: list[ReverieComfortRequest] = []
        self._routine_times: list[int | None] = []
        self._routine_index = 0
        self._routine_timer: asyncio.TimerHandle | None = None
        self._routine_generation = 0
        self._routine_owner: tuple[int, PairlinkPeerIdentity] | None = None
        self._routine_connection_release: Callable[[], None] | None = None
        self._diagnostic_timer: asyncio.TimerHandle | None = None
        self._diagnostic_generation = 0
        self._diagnostic_snapshot: PairlinkSendSnapshot | None = None
        self._diagnostic_connection_release: Callable[[], None] | None = None
        self._status_sync_timer: asyncio.TimerHandle | None = None
        self._status_sync_generation = 0
        self._backup_check_timer: asyncio.TimerHandle | None = None
        self._backup_check_task: asyncio.Task[None] | None = None
        self._backup_check_generation = 0
        self._clock_sync_generation = 0
        self._clock_sync_timer: asyncio.TimerHandle | None = None
        self._clock_sync_active = False
        self._last_pairlink_clock_seconds: int | None = None
        self._active_control_session = False
        self._status_sync_error: Exception | None = None
        self._runtime.set_shutdown_callback(self._cancel_runtime_owned_activity)

    @property
    def _sdk_home_id(self) -> str | None:
        return self._sdk_entry_state.home_id

    @property
    def _sdk_expected_devices(self) -> int:
        return self._sdk_entry_state.expected_devices

    @_sdk_expected_devices.setter
    def _sdk_expected_devices(self, value: int) -> None:
        self._sdk_entry_state.expected_devices = value

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the accepted primary central write UUID."""
        return self._write_uuid

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object]:
        """Never trace Pairlink frames: they are keyed by the home ID and password."""
        return {"hex": "**REDACTED**", "length": len(command), "ascii_preview": None}

    def _central_writer(self, client: GattWriter) -> GattWriter:
        """Wrap ``client`` so each central fragment reaches the command trace."""
        return _TracedCentralWriter(self, client)

    @property
    def requires_disconnected_transport(self) -> bool:
        """Local-host join owns BlueZ notifications without a Bleak central link."""
        return self._runtime.role is PairlinkRole.PERIPHERAL

    @property
    def disconnected_transport_ready(self) -> bool:
        """Require a joined, authenticated, subscribed current local peer."""
        return self._runtime.disconnected_transport_ready

    @property
    def supports_single_address_pairing(self) -> bool:
        """No accepted Pairlink evidence maps HA left/right to app targets."""
        return False

    @property
    def _has_supported_model(self) -> bool:
        return self.model_id in PAIRLINK_BED_TYPES.values()

    @property
    def supports_motor_control(self) -> bool:
        return self._has_supported_model

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self._has_supported_model:
            return ()
        specs = (
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda controller: controller.move_back_up(),
                close_fn=lambda controller: controller.move_back_down(),
                stop_fn=lambda controller: controller.move_back_stop(),
                position_key="back",
                max_angle=100,
                hold=ControllerMotorHoldSpec("back_up", "back_down"),
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda controller: controller.move_legs_up(),
                close_fn=lambda controller: controller.move_legs_down(),
                stop_fn=lambda controller: controller.move_legs_stop(),
                position_key="legs",
                max_angle=100,
                hold=ControllerMotorHoldSpec("legs_up", "legs_down"),
            ),
        )
        if not self.has_lumbar_support:
            return specs
        return (
            *specs,
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda controller: controller.move_lumbar_up(),
                close_fn=lambda controller: controller.move_lumbar_down(),
                stop_fn=lambda controller: controller.move_lumbar_stop(),
                position_key=None,
                max_angle=100,
                hold=ControllerMotorHoldSpec("lumbar_up", "lumbar_down"),
            ),
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        if not self._has_supported_model:
            return ()
        controls = ("back_up", "back_down", "legs_up", "legs_down")
        if self.has_lumbar_support:
            return (*controls, "lumbar_up", "lumbar_down")
        return controls

    @property
    def supports_position_feedback(self) -> bool:
        return super().supports_position_feedback and self._has_supported_model

    @property
    def requires_notification_channel(self) -> bool:
        return self._has_supported_model

    @property
    def supports_direct_position_control(self) -> bool:
        return self._has_supported_model

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        if not self._has_supported_model:
            return ()
        return (
            build_position_number_spec("back", max_value=100, unit=POSITION_UNIT_PERCENT),
            build_position_number_spec("legs", max_value=100, unit=POSITION_UNIT_PERCENT),
        )

    @property
    def has_lumbar_support(self) -> bool:
        return self._has_supported_model and self.model_id == "R510L"

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._has_supported_model

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._has_supported_model

    @property
    def supports_preset_flat(self) -> bool:
        return self._has_supported_model

    @property
    def supports_memory_presets(self) -> bool:
        return self._has_supported_model

    @property
    def memory_slot_count(self) -> int:
        return 4 if self._has_supported_model else 0

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self._has_supported_model

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._has_supported_model

    @property
    def supports_light_state_feedback(self) -> bool:
        return self._has_supported_model

    @property
    def supports_light_level_control(self) -> bool:
        return self._has_supported_model

    @property
    def light_level_max(self) -> int:
        return 100

    @property
    def supports_light_color_control(self) -> bool:
        return self._has_supported_model

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self._has_supported_model else None

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        return (255, 255, 255) if self._has_supported_model else None

    @property
    def supports_massage(self) -> bool:
        return self._has_supported_model

    @property
    def supports_massage_off_control(self) -> bool:
        return self._has_supported_model

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self._has_supported_model

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["head", "foot"] if self._has_supported_model else []

    @property
    def massage_intensity_max(self) -> int:
        return 10

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self._has_supported_model:
            return ()
        return (
            ControllerStateSensorSpec(
                key="reverie_pairlink_massage_timer",
                translation_key="reverie_pairlink_massage_timer",
                state_key=MASSAGE_TIMER,
                icon="mdi:timer-outline",
                card=CARD_MASSAGE,
            ),
            ControllerStateSensorSpec(
                key="reverie_pairlink_massage_mode",
                translation_key="reverie_pairlink_massage_mode",
                state_key=MASSAGE_MODE,
                icon="mdi:waveform",
                card=CARD_MASSAGE,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(
        self,
    ) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self._has_supported_model:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="reverie_pairlink_low_battery",
                translation_key="reverie_pairlink_low_battery",
                state_key=LOW_BATTERY,
                icon="mdi:battery-low",
                card=CARD_UTILITY,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self._has_supported_model:
            return ()

        async def select_mode(_controller: BedController, option: str) -> None:
            if option not in ("0", "1", "2", "3", "4"):
                raise ValueError("Pairlink massage mode must be between 0 and 4")
            await self.set_massage_mode(int(option))

        async def select_rhythm(_controller: BedController, option: str) -> None:
            if option not in ("off", "on"):
                raise ValueError("Pairlink massage rhythm must be on or off")
            await self.set_massage_rhythm(option == "on")

        return (
            ControllerSelectSpec(
                key="reverie_pairlink_massage_mode",
                translation_key="reverie_pairlink_massage_mode",
                state_key=MASSAGE_MODE_OPTION,
                options=("0", "1", "2", "3", "4"),
                select_fn=select_mode,
                card=CARD_MASSAGE,
            ),
            ControllerSelectSpec(
                key="reverie_pairlink_massage_rhythm",
                translation_key="reverie_pairlink_massage_rhythm",
                state_key=MASSAGE_RHYTHM_OPTION,
                options=("off", "on"),
                select_fn=select_rhythm,
                card=CARD_MASSAGE,
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self._has_supported_model:
            return ()
        return (
            ControllerNumberSpec(
                key="reverie_pairlink_massage_timer",
                translation_key="reverie_pairlink_massage_timer",
                state_key=MASSAGE_TIMER,
                native_min_value=0,
                native_max_value=255,
                native_step=1,
                set_fn=lambda _controller, value: self.set_massage_timer_byte(int(value)),
                card=CARD_MASSAGE_TIMER,
            ),
        )

    async def async_discover_capabilities(self) -> None:
        """Resolve only the exact primary or low-power central GATT profile."""
        if not self._has_supported_model:
            return
        try:
            self._resolve_gatt_endpoints()
        except ConnectionError:
            self._runtime._on_central_library_status(
                3, source_mac=self._coordinator.address
            )
            raise

    def _resolve_gatt_endpoints(self) -> None:
        client = self.client
        services = getattr(client, "services", None) if client is not None else None
        if services is None:
            raise ConnectionError("Pairlink GATT services are not available")
        service_characteristics: dict[str, set[str]] = {}
        for service in services:
            service_uuid = str(getattr(service, "uuid", "")).lower()
            service_characteristics[service_uuid] = {
                str(getattr(characteristic, "uuid", "")).lower()
                for characteristic in getattr(service, "characteristics", ())
            }
        for service_uuid, write_uuid, notify_uuid in (
            (PAIRLINK_SERVICE_UUID, PAIRLINK_WRITE_UUID, PAIRLINK_NOTIFY_UUID),
            (
                PAIRLINK_LOW_POWER_SERVICE_UUID,
                PAIRLINK_LOW_POWER_WRITE_UUID,
                PAIRLINK_LOW_POWER_NOTIFY_UUID,
            ),
        ):
            characteristics = service_characteristics.get(service_uuid.lower(), set())
            if write_uuid.lower() in characteristics and notify_uuid.lower() in characteristics:
                self._write_uuid = write_uuid
                self._notify_uuid = notify_uuid
                return
        raise ConnectionError("Connected device does not expose a complete Pairlink GATT profile")

    def set_mesh_event_callback(self, callback: PairlinkMeshEventCallback | None) -> None:
        """Attach the typed Pairlink event boundary supplied by a session adapter."""
        self._event_callback = callback

    async def _async_handle_peripheral_peer_write(
        self,
        peer: PairlinkPeerIdentity,
        value: bytes,
    ) -> None:
        """Route a verified BlueZ peer write to its Pairlink session processor.

        The transport supplies identity only after matching the BlueZ WriteValue
        producer to a current Device1 object on the selected adapter. Keep that
        identity attached to this write so downstream auth/session state can be
        keyed by the actual peer and connection generation.
        """
        if not self.requires_disconnected_transport:
            raise PairlinkRuntimeNotReadyError("Pairlink local callback role is not selected")
        if not self._has_supported_model:
            raise PairlinkRuntimeNotReadyError("Pairlink model profile is not supported")
        if not isinstance(peer, PairlinkPeerIdentity) or type(value) is not bytes:
            raise PairlinkRuntimeNotReadyError("Pairlink peer write identity or payload is invalid")
        if self._runtime.is_closed:
            raise PairlinkRuntimeNotReadyError("Pairlink entry runtime is closed")
        if self._runtime.is_exiting:
            return
        await self._async_process_transport_packet(
            memoryview(value).tobytes(), source_mac=peer.address, peer=peer,
            expected_epoch=self._runtime.epoch,
        )
        self._sync_active_control_session()

    async def async_start_peripheral(
        self,
        *,
        host_adapter_source: str,
        adapter_inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
    ) -> None:
        """Start the entry-owned accepted profile on its explicitly selected host source."""
        if self._runtime.role is not PairlinkRole.PERIPHERAL:
            raise PairlinkRuntimeNotReadyError("Pairlink local role is not selected")
        profile = build_pairlink_peripheral_profile(
            home_id=int.from_bytes(self._runtime.credentials.home_id_le, "little"),
            local_join_bt_mac=self._runtime.local_join_bt_mac,
        )
        async with self._sdk_receive_lock:
            await self._async_initialize_sdk()
        await self._runtime.async_start_peripheral(
            host_adapter_source=host_adapter_source,
            adapter_inventory=adapter_inventory,
            profile=profile,
            on_peer_write=self._async_handle_peripheral_peer_write,
            on_peer_lifecycle=self._handle_peripheral_peer_lifecycle,
        )
        self._sdk_metadata.reset_join_state()

    async def _async_process_transport_packet(
        self, packet: bytes, *, source_mac: str,
        peer: PairlinkPeerIdentity | None, expected_epoch: int,
    ) -> None:
        """The existing receive lane owns native reduction AND awaited SDK IO."""
        async with self._sdk_receive_lock:
            if not self._runtime.effect_is_current(
                epoch=expected_epoch, source_mac=source_mac, peer=peer
            ):
                return
            await self._async_initialize_sdk()
            if not self._runtime.effect_is_current(
                epoch=expected_epoch, source_mac=source_mac, peer=peer
            ):
                return
            effects = self._runtime.process_transport_packet(
                packet, source_mac=source_mac, peer=peer, expected_epoch=expected_epoch
            )
            await self._async_apply_runtime_effects_unlocked(effects)

    async def _async_apply_runtime_effects(self, effects: tuple[PairlinkEffect, ...]) -> None:
        """Serialize source continuations across persistence/callback awaits."""
        async with self._sdk_receive_lock:
            await self._async_initialize_sdk()
            await self._async_apply_runtime_effects_unlocked(effects)

    async def _async_apply_runtime_effects_unlocked(self, effects: tuple[PairlinkEffect, ...]) -> None:
        for effect in effects:
            if isinstance(effect, PairlinkWelcome):
                if (
                    self._runtime.effect_is_current(
                        epoch=effect.epoch,
                        source_mac=effect.target_mac,
                        peer=effect.peer,
                    )
                    and self._runtime.peripheral_stop_adv_after_welcome
                ):
                    self._start_backup_check()
                continue
            if isinstance(effect, PairlinkSendReply):
                if not self._runtime.effect_is_current(
                    epoch=effect.epoch,
                    source_mac=effect.target_mac,
                    peer=effect.peer,
                ):
                    raise PairlinkRuntimeNotReadyError(
                        "Pairlink native reply belongs to an ended session"
                    )
                if effect.peer is not None:
                    await self._runtime.async_reply_to_peer(
                        effect.peer,
                        effect.payload,
                        epoch=effect.epoch,
                    )
                    self._select_local_primary_state()
                    continue
                client = self.client
                if (
                    client is None
                    or not client.is_connected
                    or self._runtime.role is not PairlinkRole.CENTRAL
                    or effect.target_mac != self._runtime.target_mac
                ):
                    raise PairlinkRuntimeNotReadyError(
                        "Pairlink native reply lost its selected central connection"
                    )
                self._resolve_gatt_endpoints()
                async with self._ble_lock:
                    await send_central_frame(
                        self._central_writer(client),
                        effect.payload,
                        characteristic=self._write_uuid,
                        att_mtu=client.mtu_size,
                    )
                if self._runtime.joined:
                    self._start_clock_sync()
                continue
            if isinstance(effect, PairlinkClockResponse):
                if not self._runtime.effect_is_current(
                    epoch=effect.epoch,
                    source_mac=effect.source_mac,
                    peer=effect.peer,
                ):
                    continue
                self._last_pairlink_clock_seconds = effect.timestamp_seconds
                if self._runtime.role is PairlinkRole.CENTRAL and self._runtime.joined:
                    self._schedule_clock_query(
                        self._clock_sync_generation,
                        delay_seconds=5,
                    )
                continue
            if isinstance(effect, PairlinkMeshEvent):
                if not self._runtime.effect_is_current(
                    epoch=effect.epoch,
                    source_mac=effect.source_mac,
                    peer=effect.peer,
                ):
                    continue
                self.handle_mesh_event(
                    effect.event_type,
                    effect.event_data,
                    effect.broadcast,
                    peer=effect.peer,
                )
                continue
            if isinstance(effect, PairlinkSdkFrame):
                if not self._runtime.effect_is_current(
                    epoch=effect.epoch,
                    source_mac=effect.source_mac,
                    peer=effect.peer,
                ):
                    continue
                self._sdk_context = effect
                self._sdk_metadata.callback_present = self._runtime._mesh_callback_present
                try:
                    await self._consume_sdk_frame(effect)
                finally:
                    self._sdk_context = None
                continue
            if isinstance(effect, PairlinkSdkNative):
                if not self._runtime.effect_is_current(
                    epoch=effect.epoch, source_mac=effect.source_mac, peer=effect.peer
                ):
                    continue
                self._sdk_context = effect
                self._sdk_metadata.callback_present = self._runtime._mesh_callback_present
                try:
                    await self._consume_sdk_native(effect)
                finally:
                    self._sdk_context = None
                continue
            raise TypeError("Pairlink runtime emitted an unsupported private effect")
        self._sync_active_control_session()

    async def _async_initialize_sdk(self) -> None:
        home_id = self._runtime.credentials.home_id_le.hex()
        self._sdk_metadata.callback_present = self._runtime._mesh_callback_present
        if not self._sdk_entry_state.initialized:
            await self._sdk_metadata.initialize(home_id)
            self._sdk_entry_state.initialized = True
            self._sdk_entry_state.home_id = home_id
        elif home_id != self._sdk_home_id:
            await self._sdk_metadata.initialize_fingerprint(home_id)
            self._sdk_entry_state.home_id = home_id

    async def _async_sdk_exit(self) -> None:
        """API_exit_mesh ordering, before native/backend/session teardown."""
        async with self._sdk_receive_lock:
            self._cancel_sdk_timers()
            if self._sdk_entry_state.initialized:
                await self._sdk_metadata.save_status()

    async def _consume_sdk_native(self, effect: PairlinkSdkNative) -> None:
        if effect.kind == "network_info":
            if self._runtime.role is not PairlinkRole.CENTRAL:
                return
            self._sdk_expected_devices = int.from_bytes(effect.packet[8:10], "little") or 1
            # CMD02 calls apiGetSyncTime before its fingerprint/status branch.
            # This uses the existing native send route and does not add a timer.
            await self._async_sdk_native_query(effect, b"\x01\x1a")
            if self._runtime._join_check_type != 0:
                return
            if not await self._sdk_metadata.begin_fingerprint():
                await self._async_sdk_ready_status(effect)
        elif effect.kind == "fingerprint":
            await self._sdk_metadata.receive_fingerprint(effect.packet)
        else:
            raise TypeError("unknown source SDK continuation")

    def _sdk_context_is_current(self, effect: PairlinkSdkFrame | PairlinkSdkNative) -> bool:
        return self._runtime.effect_is_current(
            epoch=effect.epoch, source_mac=effect.source_mac, peer=effect.peer
        )

    async def _async_sdk_metadata_effect(self, effect: SdkMetadataEffect) -> None:
        source = self._sdk_context
        if source is None or not self._sdk_context_is_current(source):
            raise PairlinkRuntimeNotReadyError("metadata continuation lost its receive owner")
        self._sdk_metadata.callback_present = self._runtime._mesh_callback_present
        if isinstance(effect, SdkMetadataStatus):
            if effect.status == 8:
                self._emit_sdk_status8(PairlinkMeshStatusEvent(
                    source.epoch, source.source_mac, source.peer, 8
                ))
            else:
                await self._async_sdk_ready_status(source)
        elif isinstance(effect, SdkFingerprintStatus):
            return  # Actual shipped onFingerPrintStatus body is empty.
        elif isinstance(effect, SdkFingerprintQuery):
            await self._async_sdk_native_query(source, b"\x01\x42")
        elif isinstance(effect, SdkCompositionQuery):
            await self._async_sdk_composition_query(source, effect.bt_address)
        elif isinstance(effect, SdkMetadataTimer):
            self._set_sdk_timer(source, effect)
        else:
            raise TypeError("unsupported metadata effect")

    async def _async_sdk_ready_status(
        self, source: PairlinkSdkFrame | PairlinkSdkNative
    ) -> None:
        """Consume app mesh status 7 with its existing BLE discovery request."""
        if not self._runtime._mesh_callback_present or not self._sdk_context_is_current(source):
            return
        if self._runtime.role is PairlinkRole.CENTRAL:
            try:
                snapshot = self._capture_current_send_snapshot()
            except (PairlinkRuntimeNotReadyError, ConnectionError):
                snapshot = None
            if snapshot is not None:
                self._sdk_devices.clear()
                self._sdk_restore_clear()
                frame = (
                    b"\x03" + PAIRLINK_BROADCAST_ADDRESS + b"\xfe"
                    + snapshot.own_virtual_address
                )
                await self._async_send_profile_frame(frame, snapshot)
                if self._runtime.snapshot_is_current(snapshot):
                    self._sdk_entry_state.started_ms = self._sdk_now_ms()
        if self._sdk_context_is_current(source) and self._sdk_status_delegate is not None:
            self._sdk_status_delegate(7)

    async def _async_sdk_native_query(
        self, source: PairlinkSdkFrame | PairlinkSdkNative, packet: bytes
    ) -> bool:
        if not self._sdk_context_is_current(source):
            return False
        # apiGetFingerPrint requires the existing physical connection; it does
        # not require a manufactured application-event key or a joined model.
        if source.peer is None:
            client = self.client
            if self._runtime.role is not PairlinkRole.CENTRAL or client is None or not client.is_connected:
                return False
        else:
            session = self._runtime.peer_sessions.get(source.source_mac)
            if session is None or not session.subscribed:
                return False
        await self._async_apply_runtime_effects_unlocked((
            PairlinkSendReply(source.epoch, source.source_mac, source.peer, packet),
        ))
        return True

    async def _async_sdk_composition_query(
        self, source: PairlinkSdkFrame | PairlinkSdkNative, bt_address: str
    ) -> None:
        if not self._sdk_context_is_current(source):
            return
        try:
            snapshot = self._capture_current_send_snapshot()
        except (PairlinkRuntimeNotReadyError, ConnectionError):
            return
        if snapshot.target_mac != source.source_mac or snapshot.peer != source.peer:
            return
        address = bytes.fromhex(bt_address.replace(":", ""))[::-1]
        if len(address) != 6:
            raise ValueError("source composition MAC width")
        # composGet(btMAC,0) -> SendPacket/GenUnitControlPacket(source kind2).
        inner = b"\x00\x00\x00\x00\x02" + self._runtime.local_join_bt_mac + b"\x00\x00"
        frame = b"\x03" + PAIRLINK_BROADCAST_ADDRESS + b"\x14" + address + b"\x20" + inner
        await self._async_send_profile_frame(frame, snapshot)

    def _set_sdk_timer(
        self, source: PairlinkSdkFrame | PairlinkSdkNative, effect: SdkMetadataTimer
    ) -> None:
        old = self._sdk_timers.pop(effect.timer, None)
        if old is not None:
            old.cancel()
        token = self._sdk_timer_generation.get(effect.timer, 0) + 1
        self._sdk_timer_generation[effect.timer] = token
        if effect.delay_ms is None:
            return
        self._sdk_timers[effect.timer] = self._coordinator.hass.loop.call_later(
            effect.delay_ms / 1000,
            self._schedule_sdk_timer, source, effect.timer, token,
        )

    def _schedule_sdk_timer(
        self, source: PairlinkSdkFrame | PairlinkSdkNative, timer: str, token: int
    ) -> None:
        if self._sdk_timer_generation.get(timer) != token or not self._sdk_context_is_current(source):
            return
        self._sdk_timers.pop(timer, None)
        self._coordinator.hass.async_create_task(
            self._async_sdk_timer(source, timer, token), "adjustable_bed.pairlink_sdk_timer"
        )

    async def _async_sdk_timer(
        self, source: PairlinkSdkFrame | PairlinkSdkNative, timer: str, token: int
    ) -> None:
        async with self._sdk_receive_lock:
            if self._sdk_timer_generation.get(timer) != token or not self._sdk_context_is_current(source):
                return
            self._sdk_context = source
            self._sdk_metadata.callback_present = self._runtime._mesh_callback_present
            try:
                if timer == "fingerprint":
                    await self._sdk_metadata.fingerprint_timeout()
                elif timer == "attributes":
                    await self._sdk_metadata.attributes_timeout()
                else:
                    raise TypeError("unknown source SDK timer")
            finally:
                self._sdk_context = None

    def _cancel_sdk_timers(self) -> None:
        for timer, handle in self._sdk_timers.items():
            handle.cancel()
            self._sdk_timer_generation[timer] = self._sdk_timer_generation.get(timer, 0) + 1
        self._sdk_timers.clear()

    async def _consume_sdk_frame(self, effect: PairlinkSdkFrame) -> None:
        """Consume only source-guarded SDK callbacks with a concrete HA effect."""
        if self._sdk_epoch != effect.epoch:
            self._clear_sdk_device_addresses()
        frame = effect.frame
        if len(frame) < 6 or frame[0] != 0x03:
            return
        if len(frame) == 6 and frame[5] != 0xFF:
            # Keep malformed subtype callbacks bounded, with no SDK state change.
            return
        channel = frame[5]
        subtype = frame[6] if len(frame) > 6 else None

        if channel == 0xFF:
            if self._runtime._join_check_type != 0:
                # The separate detector's pingReceived path does not emit 8.
                return
            self._consume_sdk_ping_response(effect)
            # GetPingResponse's return is intentionally not a status gate.
            self._emit_sdk_status8(effect)
            await self._sdk_metadata.ping_list_complete(self._sdk_expected_devices)
            return

        if channel in (0x14, 0x20, 0x21):
            await self._consume_sdk_message(effect)
            return

        if channel == 0x12:
            if subtype in (0x24, 0x28, 0x2A) and (
                len(frame) < 11
                or not self._sdk_virtual_address_is_current(
                    effect.source_mac, effect.peer, frame[7:11]
                )
            ):
                return
            if subtype == 0x30:
                # The SDK reads six address bytes and then the sign byte. Its
                # minimum safe frame is therefore 14 bytes. Lookup uses the
                # canonical logical MAC, independently of the physical route.
                if len(frame) < 14:
                    return
                reported_mac = sdk_mac(frame[7:13])
                self._sign_gate.process_type48(reported_mac, frame[13])
                self._runtime.mark_peer_state_changed(effect.peer)
                if (
                    any(bean.bt_addr == reported_mac for bean in self._sdk_current_devices(effect))
                ):
                    self._emit_sdk_status8(effect)
                return
            if self._pairlink_channel12_emits_status8(frame):
                devices = self._sdk_current_devices(effect)
                if subtype == 0x40:
                    first = self._sdk_devices[0] if self._sdk_devices else None
                    known = first is not None and any(bean is first for bean in devices)
                else:
                    known = bool(devices)
                if known:
                    self._emit_sdk_status8(effect)
            return

        if channel == 0x16 and subtype in (0x08, 0x0B) and len(frame) >= 14:
            if self._sdk_virtual_address_is_current(
                effect.source_mac, effect.peer, bytes(frame[7:11])
            ):
                self._emit_sdk_status8(effect)

    def _emit_sdk_status8(
        self, effect: PairlinkSdkFrame | PairlinkMeshStatusEvent
    ) -> None:
        if self._runtime._mesh_callback_present:
            self._sdk_status_callback(effect)
            if self._sdk_status_delegate is not None:
                self._sdk_status_delegate(8)

    def _consume_sdk_status8(
        self, effect: PairlinkSdkFrame | PairlinkMeshStatusEvent
    ) -> None:
        # Source requests reads before consulting the optional app delegate.
        # Existing send/readiness gates still decide whether anything is sent.
        if self._runtime.effect_is_current(
            epoch=effect.epoch, source_mac=effect.source_mac, peer=effect.peer
        ) and self._runtime.status_callback_target_is_current(
            source_mac=effect.source_mac, peer=effect.peer
        ):
            self._schedule_initial_dashboard_queries(effect)

    def _consume_central_library_status(self, effect: PairlinkMeshStatusEvent) -> None:
        if (
            effect.status != 8
            or self._runtime.role is not PairlinkRole.CENTRAL
            or effect.epoch != self._runtime.epoch
            or effect.source_mac != self._runtime.target_mac
        ):
            return
        self._emit_sdk_status8(effect)
        self.on_disconnect()

    def _sdk_restore_clear(self) -> None:
        self._sdk_owners.clear()
        self._known_device_vaddrs.clear()

    def _sdk_restore_device(self, device: PairlinkSdkDevice | None) -> None:
        source = self._sdk_context
        if source is None or not self._sdk_context_is_current(source):
            raise PairlinkRuntimeNotReadyError("fingerprint list restore lost its receive owner")
        if device is not None:
            self._sdk_bind(device, source)

    def _sdk_bind(self, device: PairlinkSdkDevice, effect: PairlinkSdkFrame | PairlinkSdkNative) -> None:
        self._sdk_owners[id(device)] = (effect.epoch, effect.source_mac, effect.peer)
        self._known_device_vaddrs = {
            (owner[1], owner[2], bean.vaddr)
            for bean in self._sdk_devices if bean is not None
            if (owner := self._sdk_owners.get(id(bean))) is not None
            and owner[0] == self._runtime.epoch
        }

    def _sdk_current_devices(self, effect: PairlinkSdkFrame | PairlinkSdkNative) -> list[PairlinkSdkDevice]:
        owner = (effect.epoch, effect.source_mac, effect.peer)
        return [bean for bean in self._sdk_devices if bean is not None and self._sdk_owners.get(id(bean)) == owner]

    def _consume_sdk_ping_response(self, effect: PairlinkSdkFrame) -> bool:
        frame = effect.frame
        if len(frame) < 20:
            return False
        bt_mac = sdk_mac(frame[6:12])
        # GetPingResponse updates only the first source MAC match.
        device = None
        for bean in self._sdk_devices:
            if bean is None:
                continue
            if bean.bt_addr is None:
                raise TypeError("null source SDK MAC during equals")
            if bean.bt_addr == bt_mac:
                device = bean
                break
        if device is None:
            device = PairlinkSdkDevice(
                bt_addr=bt_mac, vaddr=bytes(frame[12:16]),
                app_id=int.from_bytes(frame[16:18], "little", signed=True),
                version=f"{int.from_bytes(frame[16:18], 'little')} {self._sdk_signed8(frame[18])}.{self._sdk_signed8(frame[19])}",
            )
            self._sdk_devices.append(device)
        else:
            self._known_device_vaddrs.discard((effect.source_mac, effect.peer, device.vaddr))
            device.vaddr = bytes(frame[12:16])
        device.rtt = self._sdk_now_ms() - self._sdk_entry_state.started_ms
        self._sdk_bind(device, effect)
        # Java String.compareTo (MAC characters are ASCII); source null fails.
        self._sdk_devices.sort(key=self._sdk_sort_key)
        return True

    @staticmethod
    def _sdk_sort_key(device: PairlinkSdkDevice | None) -> bytes:
        if device is None or device.bt_addr is None:
            raise TypeError("null source SDK sort identity")
        return device.bt_addr.encode("utf-16-be", "surrogatepass")

    @staticmethod
    def _sdk_signed8(value: int) -> int:
        return value if value < 128 else value - 256

    @staticmethod
    def _sdk_now_ms() -> int:
        return int(datetime.now().timestamp() * 1000)

    @staticmethod
    def _ignore_sdk_vendor_data(_message: PairlinkSdkMessage) -> None:
        """Preserve the app's inherited MeshCallback no-op."""

    async def _consume_sdk_message(self, effect: PairlinkSdkFrame) -> None:
        devices = self._sdk_current_devices(effect)
        try:
            for message in decode_sdk_dispatch(
                effect.frame,
                local_mac=sdk_mac(self._runtime.local_join_bt_mac),
                known_macs={bean.bt_addr for bean in devices if bean.bt_addr is not None},
                callback_present=self._runtime._mesh_callback_present,
            ):
                if not self._runtime.effect_is_current(
                    epoch=effect.epoch, source_mac=effect.source_mac, peer=effect.peer
                ):
                    return
                if isinstance(message, PairlinkSdkCallbackEvent):
                    if self._runtime._mesh_callback_present:
                        self._sdk_aux_callback(message)
                    continue
                await self._consume_sdk_decoded_message(effect, message)
        except PairlinkSdkReadError:
            # Failed source reads end this receive branch. Never fabricate a
            # target or continue with a later record after a malformed prefix.
            return

    @staticmethod
    def _ignore_sdk_aux_callback(_event: PairlinkSdkCallbackEvent) -> None:
        """The actual app inherits channel/sensor/key callbacks as no-ops."""

    async def _consume_sdk_decoded_message(
        self, effect: PairlinkSdkFrame, message: PairlinkSdkMessage
    ) -> None:
        devices = self._sdk_current_devices(effect)
        device = None
        if message.address_type in (1, 3):
            device = next((bean for bean in devices if bean.vaddr == message.address[:4]), None)
        elif message.address_type in (2, 4):
            device = next((bean for bean in devices if bean.bt_addr == sdk_mac(message.address)), None)
        if message.short_ping:
            if message.opcode == 7:
                if device is not None:
                    device.online = True
                await self._async_sdk_ping_after()
                self._emit_sdk_status8(effect)
            return
        if (message.opcode & 0xFFFF) >= 0x8000:
            if self._runtime._mesh_callback_present:
                self._sdk_vendor_callback(replace(message, data=message.data or b""))
            return
        if message.groups is not None:
            self._consume_sdk_control_guards(message, devices)
            return
        if message.opcode in (3, 4):
            try:
                learned = sdk_ping_device(message, rtt=self._sdk_now_ms() - self._sdk_entry_state.started_ms)
                replace_ping_device(self._sdk_devices, learned)
            except (IndexError, TypeError, ValueError, AttributeError) as err:
                raise PairlinkSdkReadError("source ping parser/list failure") from err
            if learned is not None:
                self._sdk_bind(learned, effect)
                await self._async_sdk_ping_after()
            self._emit_sdk_status8(effect)
            return
        if message.opcode == 6:
            try:
                bean = sdk_low_power_device(message)
            except (IndexError, TypeError, ValueError, AttributeError) as err:
                raise PairlinkSdkReadError("source LP parser failure") from err
            if self._runtime._mesh_callback_present:
                self._sdk_low_power_callback(bean)
            return
        if message.opcode == 1:
            if device is not None:
                try:
                    sdk_composition(device, message.data)
                except (IndexError, TypeError, ValueError, AttributeError) as err:
                    raise PairlinkSdkReadError("source composition parser failure") from err
                await self._sdk_metadata.add(self._sdk_views.view(device))
            return
        if message.opcode == 0x049B and device is not None:
            self._schedule_sdk_calendar_response(effect, device)
        self._consume_sdk_control_guards(message, devices)

    async def _async_sdk_ping_after(self) -> None:
        """pingStatusAfterHandler uses online count, before FuncMsg callback8."""
        online = 0
        for index in range(len(self._sdk_devices)):
            try:
                bean = self._sdk_devices[index]
            except IndexError:
                continue
            if bean is None:
                raise PairlinkSdkReadError("null DeviceBean in source getOnlineNum")
            online += bean.online
        # AttributesManagement.start is static false; no worker is acquired.
        if online == self._sdk_expected_devices and self._sdk_metadata.fingerprint_state == 2:
            await self._sdk_metadata.save_fingerprint(self._sdk_metadata.pending_fingerprint)
            self._sdk_metadata.fingerprint_state = 3

    def _consume_sdk_control_guards(
        self, message: PairlinkSdkMessage, devices: list[PairlinkSdkDevice]
    ) -> None:
        """Retain catalog predicates; ROOT05..15 generic arithmetic is excluded."""
        temperature = message.opcode in (0x3BA, 0x3BB)
        hue = message.opcode in (0x3E7, 0x3E8)
        if not self._sdk_lib_calc_status or not (temperature or hue):
            return
        if message.data is None or len(message.data) < (2 if temperature else 6):
            return
        groups = message.groups
        # Source group loops keep duplicate group entries. Unicast/broadcast
        # select the source's explicit target MAC and mask, never physical MAC.
        selections = groups if groups is not None else (None,)
        for group in selections:
            for bean in devices:
                if groups is None and not message.broadcast and bean.bt_addr != message.target_mac:
                    continue
                for index, unit in enumerate(bean.units):
                    if group is not None and group not in unit.groups:
                        continue
                    if temperature and (groups is not None or message.broadcast) and not unit.onoff:
                        continue
                    if hue and not ((groups is not None and message.unit_mask == 0) or message.unit_mask & (1 << (index & 31))):
                        continue
                    if not self._sdk_metadata.supports(
                        bean.app_id, bean.company_id, bean.product_id, index, 5
                    ):
                        continue
                    # The following generic lighting prediction/callback body
                    # is ROOT05..15's explicit source exclusion.

    def _schedule_sdk_calendar_response(
        self, effect: PairlinkSdkFrame, device: PairlinkSdkDevice
    ) -> None:
        if not self._runtime.status_callback_target_is_current(
            source_mac=effect.source_mac, peer=effect.peer
        ):
            return
        try:
            snapshot = self._capture_current_send_snapshot()
        except (PairlinkRuntimeNotReadyError, ConnectionError, ValueError):
            return
        if snapshot.target_mac != effect.source_mac or snapshot.peer != effect.peer:
            return
        # Calendar.getInstance and Util.getTimeZone sample the clock separately.
        calendar = datetime.now().astimezone()
        offset = datetime.now().astimezone().utcoffset()
        if offset is None:
            return
        payload = calendar_payload(calendar, int(offset.total_seconds() * 1000))
        frame = calendar_profile_frame(
            target=device.vaddr,
            own_virtual_address=snapshot.own_virtual_address,
            payload=payload,
        )
        self._coordinator.hass.async_create_task(
            self._async_run_sdk_calendar_response(effect, snapshot, device, frame),
            "adjustable_bed.pairlink_calendar_response",
        )

    async def _async_run_sdk_calendar_response(
        self,
        effect: PairlinkSdkFrame,
        snapshot: PairlinkSendSnapshot,
        device: PairlinkSdkDevice,
        frame: bytes,
    ) -> None:
        async def send_calendar(controller: BedController) -> None:
            if controller is not self or not self._runtime.effect_is_current(
                epoch=effect.epoch, source_mac=effect.source_mac, peer=effect.peer
            ):
                return
            if (
                not any(bean is device for bean in self._sdk_current_devices(effect))
                or device.vaddr != frame[1:5]
            ):
                return
            await self._async_send_profile_frame(frame, snapshot)

        try:
            await self._coordinator.async_execute_controller_command(
                send_calendar,
                cancel_running=False,
                resource="reverie:pairlink:calendar-response",
                read_positions_after_operation=False,
            )
        except asyncio.CancelledError:
            raise
        except (PairlinkRuntimeNotReadyError, ConnectionError, PermissionError, BleakError):
            _LOGGER.warning("Pairlink calendar response lost its current send route")

    def _sdk_virtual_address_is_current(
        self,
        source_mac: str,
        peer: PairlinkPeerIdentity | None,
        virtual_address: bytes,
    ) -> bool:
        return (
            type(virtual_address) is bytes
            and len(virtual_address) == 4
            and any(
                bean is not None and bean.vaddr == virtual_address
                and self._sdk_owners.get(id(bean)) == (self._runtime.epoch, source_mac, peer)
                for bean in self._sdk_devices
            )
        )

    def _sdk_device_is_current(
        self, source_mac: str, peer: PairlinkPeerIdentity | None
    ) -> bool:
        return any(
            bean is not None
            and self._sdk_owners.get(id(bean)) == (self._runtime.epoch, source_mac, peer)
            for bean in self._sdk_devices
        )

    @staticmethod
    def _pairlink_channel12_emits_status8(frame: bytes) -> bool:
        """Apply only bounded source guards for channel-0x12 status callbacks."""
        subtype = frame[6]
        if subtype == 0x28:
            return len(frame) == 12
        if subtype == 0x24:
            # Source writes RTT before decoding UTF-8 at offset 11. Shorter
            # frames can throw before the callback; length 11 is a valid empty
            # string and still reaches status 8.
            return len(frame) >= 11
        if subtype == 0x2A:
            return len(frame) >= 21
        if subtype == 0x40 and len(frame) >= 8:
            row_count = frame[7]
            complete_rows = (len(frame) - 8) // 8
            if row_count == 0:
                return True
            first_rows_end = 8 + row_count * 4
            second_rows_end = 8 + (row_count + complete_rows) * 4
            return max(first_rows_end, second_rows_end) <= len(frame)
        return False

    def _schedule_initial_dashboard_queries(self, effect: PairlinkSdkFrame | PairlinkMeshStatusEvent) -> None:
        """Match the source status-8 callback's undeduplicated initial reads."""
        self._coordinator.hass.async_create_task(
            self._async_run_initial_dashboard_queries(effect),
            "adjustable_bed.pairlink_initial_dashboard_queries",
        )

    async def _async_run_initial_dashboard_queries(self, effect: PairlinkSdkFrame | PairlinkMeshStatusEvent) -> None:
        async def request_reads(controller: BedController) -> None:
            if controller is not self or not self._runtime.effect_is_current(
                epoch=effect.epoch, source_mac=effect.source_mac, peer=effect.peer
            ):
                return
            snapshot = self._capture_current_send_snapshot()
            if snapshot.target_mac != effect.source_mac or snapshot.peer != effect.peer:
                return
            for payload in state_query_payloads():
                try:
                    await self.async_send_payload(
                        payload, prepared_snapshot=snapshot, refresh_telemetry=True
                    )
                except PermissionError:
                    # The SDK loops over all selectors even when the shared
                    # sign gate refuses each send; no frame is emitted here.
                    continue

        try:
            await self._coordinator.async_execute_controller_command(
                request_reads,
                cancel_running=False,
                resource="reverie:pairlink:initial-dashboard-queries",
                read_positions_after_operation=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._status_sync_error = err
            _LOGGER.warning("Pairlink initial dashboard queries failed")
        else:
            self._status_sync_error = None

    def _handle_peripheral_peer_lifecycle(self, event: PairlinkPeerLifecycleEvent) -> None:
        """Apply an identity-bound lifecycle fact from the registered BlueZ backend."""
        if not self.requires_disconnected_transport or self._runtime.is_closed:
            return
        if self._runtime.is_exiting and event.kind in (
            PairlinkPeerLifecycleKind.CONNECTED,
            PairlinkPeerLifecycleKind.NOTIFY_SUBSCRIBED,
        ):
            return
        previous_session = self._runtime.peer_sessions.get(event.peer.address)
        current_identity = (
            previous_session is not None and previous_session.identity == event.peer
        )
        if event.kind is PairlinkPeerLifecycleKind.DISCONNECTED and not current_identity:
            return
        if event.kind is PairlinkPeerLifecycleKind.CONNECTED and current_identity:
            # Welcome removes the primary from the source backup list. Its
            # first later observation adds it back without reinitialization.
            assert previous_session is not None
            known_backup = previous_session.source_backup_member
            previous_session.source_backup_member = True
            if (
                known_backup
                and self._runtime._mesh_callback_present
                and self._sdk_status_delegate is not None
            ):
                self._sdk_status_delegate(3)
            return
        if event.kind is PairlinkPeerLifecycleKind.CONNECTED:
            current = self._peer_state_identities.get(event.peer.address)
            if current != event.peer:
                self._clear_peer_state(event.peer.address)
                self._clear_sdk_device_addresses(address=event.peer.address)
                self._peer_state_identities[event.peer.address] = event.peer
        was_primary = current_identity and self._runtime.primary_mac == event.peer.address
        if event.kind is PairlinkPeerLifecycleKind.DISCONNECTED and was_primary:
            backups = self._runtime.backup_peer_identities
            self._cancel_backup_check()
            if backups:
                self._coordinator.hass.async_create_task(
                    self._async_send_backup_exit(backups),
                    "adjustable_bed.pairlink_primary_disconnect_backup_exit",
                )
        self._runtime.apply_peer_lifecycle(event)
        if event.kind is PairlinkPeerLifecycleKind.CONNECTED:
            try:
                self._runtime.initialize_peer_provisioning(
                    event.peer,
                    extension=self._runtime.credentials.home_id_le,
                )
            except (PairlinkRuntimeNotReadyError, RuntimeError, ValueError):
                # A local peer can still use the ordinary authenticated route,
                # but provisioning must not continue with zero or stale key
                # material when P-256 initialization fails.
                _LOGGER.warning("Pairlink peer provisioning initialization failed")
        if event.kind is PairlinkPeerLifecycleKind.DISCONNECTED:
            self._peer_state_identities.pop(event.peer.address, None)
            self._clear_sdk_device_addresses(address=event.peer.address)
            self._clear_peer_state(
                event.peer.address,
                clear_positions=was_primary,
            )
        self._select_local_primary_state()
        self._sync_active_control_session()
        if self._runtime._mesh_callback_present and self._sdk_status_delegate is not None:
            if event.kind is PairlinkPeerLifecycleKind.DISCONNECTED and was_primary:
                self._sdk_status_delegate(5)

    def _start_backup_check(self) -> None:
        """Post the source welcome backup check after one second."""
        self._cancel_backup_check()
        if (
            self._runtime.role is not PairlinkRole.PERIPHERAL
            or self._runtime.is_closed
            or not self._runtime.peripheral_stop_adv_after_welcome
        ):
            return
        self._schedule_backup_check(
            self._backup_check_generation, self._runtime.epoch, delay_seconds=1
        )

    def _cancel_backup_check(self) -> None:
        self._backup_check_generation += 1
        if self._backup_check_timer is not None:
            self._backup_check_timer.cancel()
            self._backup_check_timer = None
        task = self._backup_check_task
        self._backup_check_task = None
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    def _schedule_backup_check(
        self, generation: int, epoch: int, *, delay_seconds: float
    ) -> None:
        if (
            generation != self._backup_check_generation
            or epoch != self._runtime.epoch
            or self._runtime.is_closed
            or not self._runtime.joined
            or not self._runtime.peripheral_stop_adv_after_welcome
        ):
            return
        self._backup_check_timer = self._coordinator.hass.loop.call_later(
            delay_seconds, self._enqueue_backup_check, generation, epoch
        )

    def _enqueue_backup_check(self, generation: int, epoch: int) -> None:
        if generation != self._backup_check_generation:
            return
        self._backup_check_timer = None
        if (
            epoch != self._runtime.epoch
            or self._runtime.is_closed
            or not self._runtime.joined
            or not self._runtime.peripheral_stop_adv_after_welcome
        ):
            return
        task = self._coordinator.hass.async_create_task(
            self._async_run_backup_check(generation, epoch),
            "adjustable_bed.pairlink_backup_check",
        )
        self._backup_check_task = task
        task.add_done_callback(self._backup_check_done)

    def _backup_check_done(self, task: asyncio.Task[None]) -> None:
        if self._backup_check_task is task:
            self._backup_check_task = None

    async def _async_run_backup_check(self, generation: int, epoch: int) -> None:
        if (
            generation != self._backup_check_generation
            or epoch != self._runtime.epoch
            or self._runtime.is_closed
            or not self._runtime.joined
            or not self._runtime.peripheral_stop_adv_after_welcome
        ):
            return
        backups = self._runtime.backup_peer_identities
        if not backups:
            return
        await self._async_send_backup_exit(
            backups, generation=generation, epoch=epoch
        )
        if (
            self._backup_check_is_current(generation, epoch)
            and self._runtime.backup_peer_identities
        ):
            self._schedule_backup_check(generation, epoch, delay_seconds=0.8)

    def _backup_check_is_current(self, generation: int, epoch: int) -> bool:
        return (
            generation == self._backup_check_generation
            and epoch == self._runtime.epoch
            and not self._runtime.is_closed
            and self._runtime.joined
            and self._runtime.peripheral_stop_adv_after_welcome
        )

    async def _async_send_backup_exit(
        self,
        peers: tuple[PairlinkPeerIdentity, ...],
        *,
        generation: int | None = None,
        epoch: int | None = None,
    ) -> None:
        backend = self._runtime.peripheral_backend
        if backend is None:
            return
        for peer in peers:
            if generation is not None and epoch is not None:
                if not self._backup_check_is_current(generation, epoch):
                    return
            try:
                await backend.async_notify_to_peer(peer, PAIRLINK_EXIT_COMMAND)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.warning("Pairlink backup exit send failed for a current peer")

    def _clear_peer_state(self, address: str, *, clear_positions: bool = False) -> None:
        state = self._peer_states.pop(address, {})
        if state and state is self._state:
            self.forward_controller_state_updates(*_state_updates(dict.fromkeys(state)))
        if clear_positions:
            self._coordinator.clear_position_feedback(("back", "legs"))

    def _clear_sdk_device_addresses(self, *, address: str | None = None) -> None:
        self._cancel_sdk_timers()
        if address is None:
            self._sdk_epoch = self._runtime.epoch
            self._known_device_vaddrs.clear()
            self._sdk_devices.clear()
            self._sdk_owners.clear()
            self._sdk_expected_devices = 0
            return
        removed = {
            key for key, owner in self._sdk_owners.items() if owner[1] == address
        }
        self._sdk_devices[:] = [bean for bean in self._sdk_devices if id(bean) not in removed]
        for key in removed:
            self._sdk_owners.pop(key, None)
        self._known_device_vaddrs = {
            binding for binding in self._known_device_vaddrs if binding[0] != address
        }

    def _sync_active_control_session(self) -> None:
        """Drive A8/A9 only while the selected physical route is actually ready."""
        if not self._routine_owner_is_current():
            self._cancel_routine()
        try:
            self._capture_current_send_snapshot()
        except (PairlinkRuntimeNotReadyError, ConnectionError, ValueError, PermissionError):
            active = False
        else:
            active = True
        if active != self._active_control_session:
            self._set_active_control_session(active)
        if active:
            self._start_clock_sync()

    def handle_mesh_event(
        self,
        event_type: int,
        event_data: bytes | None,
        broadcast_flag: bool = False,
        *,
        peer: PairlinkPeerIdentity | None = None,
    ) -> tuple[tuple[str, object], ...]:
        """Apply an already decoded app-level mesh event and forward it unchanged.

        The BLE characteristic notification is not itself the app-level mesh
        event envelope. The caller must supply the exact event type and bytes;
        this method does not guess an outer packet layout.
        """
        events = parse_state_event(event_type, event_data)
        if events:
            self._runtime.mark_peer_state_changed(peer)
            source_mac = (
                self._runtime.target_mac
                if self._runtime.role is PairlinkRole.CENTRAL
                else peer.address if peer is not None else None
            )
            if (
                event_type == 0x20
                and source_mac is not None
                and event_data is not None
                and len(event_data) >= 4
                and self._runtime.status_callback_target_is_current(
                    source_mac=source_mac,
                    peer=peer,
                )
            ):
                self._known_device_vaddrs.add(
                    (source_mac, peer, bytes(event_data[:4]))
                )
        is_active_peer = (
            self._runtime.role is PairlinkRole.CENTRAL
            or peer is None
            or self._runtime.primary_mac == peer.address
        )
        state = self._state
        if self._runtime.role is PairlinkRole.PERIPHERAL and peer is not None:
            state = self._peer_states.setdefault(peer.address, {})
            if is_active_peer:
                self._state = state
        updates = dict(events)
        for key, value in events:
            if key == "reverie_massage_mode":
                updates["reverie_massage_mode_option"] = str(value)
            elif key == "reverie_massage_rhythm":
                updates["reverie_massage_rhythm_option"] = "on" if value else "off"
        for key, value in updates.items():
            if key == "pairlink_selector_event":
                continue
            if key == "pairlink_changed_selectors":
                if isinstance(value, tuple) and all(
                    isinstance(selector, int) and not isinstance(selector, bool)
                    for selector in value
                ):
                    if is_active_peer:
                        self._schedule_state_queries(value)
                continue
            state[key] = value
            if not is_active_peer:
                continue
            self.forward_controller_state_updates(_state_update(key, value))
            if key == "back_position" and isinstance(value, int):
                self._notify_position("back", value)
            elif key == "legs_position" and isinstance(value, int):
                self._notify_position("legs", value)

        if any(key.startswith("reverie_pairlink_rgb_") for key, _ in events):
            rgb = tuple(state.get(f"reverie_pairlink_rgb_{index}") for index in (1, 2, 3))
            if all(type(channel) is int for channel in rgb):
                state["under_bed_lights_rgb"] = rgb
                if is_active_peer:
                    self.forward_controller_state_update(UNDER_BED_LIGHTS_RGB, rgb_triple(rgb))

        if self._event_callback is not None and is_active_peer:
            self._event_callback(event_type, event_data, broadcast_flag)
        return events

    def _select_local_primary_state(self) -> None:
        """Expose only the current verified primary peer through HA entities."""
        if self._runtime.role is not PairlinkRole.PERIPHERAL:
            return
        primary = self._runtime.primary_mac
        selected = self._peer_states.setdefault(primary, {}) if primary else {}
        previous = self._state
        if previous is selected:
            return
        self._state = selected
        if previous:
            self.forward_controller_state_updates(*_state_updates(dict.fromkeys(previous)))
        self._coordinator.clear_position_feedback(("back", "legs"))
        if selected:
            self.forward_controller_state_updates(*_state_updates(selected))
            for axis, key in (("back", "back_position"), ("legs", "legs_position")):
                value = selected.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    self._notify_position(axis, value)

    def process_network_info_event(self) -> None:
        """Reset the signing table when a session adapter reports network info."""
        self._sign_gate.process_network_info()
        self._runtime.state_generation += 1

    def _schedule_state_queries(self, selectors: tuple[int, ...]) -> None:
        """Run source A8/A9 query expansion through the existing command scheduler."""
        payloads = tuple(
            bytes((0x01, 0xA7, 0x20, selector))
            for selector in selectors
            if selector in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17)
        )
        if not payloads:
            return

        self._coordinator.hass.async_create_task(
            self._async_run_state_queries(payloads),
            "adjustable_bed.pairlink_state_queries",
        )

    async def _async_run_state_queries(self, payloads: tuple[bytes, ...]) -> None:
        async def send_queries(controller: BedController) -> None:
            if controller is not self:
                return
            for payload in payloads:
                await self.async_send_payload(payload)

        await self._coordinator.async_execute_controller_command(
            send_queries,
            cancel_running=False,
            resource="reverie:pairlink:state-queries",
            read_positions_after_operation=False,
        )

    async def async_request_state(self) -> None:
        """Request each accepted A7 state type in its source-defined order."""
        for payload in state_query_payloads():
            await self.async_send_payload(payload)

    def _set_active_control_session(self, active: bool) -> None:
        """Start or cancel the source's separate A8/A9 active-session loop."""
        if type(active) is not bool:
            raise TypeError("Pairlink control-session state must be boolean")
        self._status_sync_generation += 1
        generation = self._status_sync_generation
        self._active_control_session = active
        if self._status_sync_timer is not None:
            self._status_sync_timer.cancel()
            self._status_sync_timer = None
        if active:
            self._schedule_status_sync(generation, delay_seconds=0)

    def _schedule_status_sync(self, generation: int, *, delay_seconds: float) -> None:
        if generation != self._status_sync_generation or not self._active_control_session:
            return
        self._status_sync_timer = self._coordinator.hass.loop.call_later(
            delay_seconds,
            self._enqueue_status_sync,
            generation,
        )

    def _enqueue_status_sync(self, generation: int) -> None:
        self._status_sync_timer = None
        if generation != self._status_sync_generation or not self._active_control_session:
            return
        self._coordinator.hass.async_create_task(
            self._async_run_status_sync(generation),
            "adjustable_bed.pairlink_status_sync",
        )

    async def _async_run_status_sync(self, generation: int) -> None:
        if generation != self._status_sync_generation or not self._active_control_session:
            return

        async def send_requests(controller: BedController) -> None:
            if controller is not self or generation != self._status_sync_generation:
                return
            for payload in status_sync_payloads():
                await self.async_send_payload(payload)

        try:
            if self._runtime.role is PairlinkRole.CENTRAL:
                await self._coordinator.async_execute_controller_query(
                    send_requests,
                    cancel_running=False,
                    skip_disconnect=True,
                    run_if=lambda: (
                        generation == self._status_sync_generation
                        and self._active_control_session
                    ),
                    preserve_idle_deadline=True,
                )
            else:
                await self._coordinator.async_execute_controller_command(
                    send_requests,
                    cancel_running=False,
                    resource="reverie:pairlink:status-sync",
                    read_positions_after_operation=False,
                )
        except asyncio.CancelledError:
            caller = asyncio.current_task()
            if (
                self._runtime.role is not PairlinkRole.CENTRAL
                or caller is None
                or caller.cancelling()
            ):
                raise
            # Live queries report command preemption without cancelling this task.
            self._status_sync_error = None
        except Exception as err:
            self._status_sync_error = err
            _LOGGER.warning("Pairlink active status synchronization failed")
        else:
            self._status_sync_error = None

        if generation == self._status_sync_generation and self._active_control_session:
            self._schedule_status_sync(generation, delay_seconds=1)

    def _notify_position(self, axis: str, value: int) -> None:
        callback = self._notify_callback
        if callback is not None:
            callback(axis, float(value))

    def _start_clock_sync(self) -> None:
        """Start the source's one-shot query, rearmed only by a time response."""
        if (
            self._runtime.role is not PairlinkRole.CENTRAL
            or not self._runtime.joined
            or self._clock_sync_active
        ):
            return
        self._clock_sync_active = True
        self._clock_sync_generation += 1
        self._schedule_clock_query(self._clock_sync_generation, delay_seconds=5)

    def _schedule_clock_query(self, generation: int, *, delay_seconds: float) -> None:
        if (
            generation != self._clock_sync_generation
            or not self._clock_sync_active
            or not self._runtime.joined
        ):
            return
        if self._clock_sync_timer is not None:
            self._clock_sync_timer.cancel()
        self._clock_sync_timer = self._coordinator.hass.loop.call_later(
            delay_seconds,
            self._enqueue_clock_query,
            generation,
        )

    def _enqueue_clock_query(self, generation: int) -> None:
        self._clock_sync_timer = None
        if (
            generation != self._clock_sync_generation
            or not self._clock_sync_active
            or not self._runtime.joined
        ):
            return
        self._coordinator.hass.async_create_task(
            self._async_run_clock_query(generation),
            "adjustable_bed.pairlink_clock_query",
        )

    async def _async_run_clock_query(self, generation: int) -> None:
        client = self.client
        if (
            generation != self._clock_sync_generation
            or not self._clock_sync_active
            or not self._runtime.joined
            or client is None
            or not client.is_connected
        ):
            return

        async def request_time(controller: BedController) -> None:
            if (
                controller is not self
                or generation != self._clock_sync_generation
                or not self._runtime.joined
            ):
                return
            current_client = self.client
            if current_client is None or not current_client.is_connected:
                return
            async with self._ble_lock:
                if not self._runtime.joined or not current_client.is_connected:
                    return
                await send_central_frame(
                    self._central_writer(current_client),
                    b"\x01\x1a",
                    characteristic=self._write_uuid,
                    att_mtu=current_client.mtu_size,
                )

        try:
            await self._coordinator.async_execute_controller_query(
                request_time,
                cancel_running=False,
                skip_disconnect=True,
                run_if=lambda: (
                    generation == self._clock_sync_generation
                    and self._clock_sync_active
                    and self._runtime.joined
                ),
                preserve_idle_deadline=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.warning("Pairlink clock query failed")

    def _cancel_clock_sync(self) -> None:
        self._clock_sync_generation += 1
        self._clock_sync_active = False
        if self._clock_sync_timer is not None:
            self._clock_sync_timer.cancel()
            self._clock_sync_timer = None

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        async with self._sdk_receive_lock:
            await self._async_initialize_sdk()
        if not self._has_supported_model:
            return
        if self._runtime.role is PairlinkRole.PERIPHERAL:
            return
        client = self.client
        if client is None or not client.is_connected:
            return
        try:
            self._resolve_gatt_endpoints()
        except ConnectionError:
            self._runtime._on_central_library_status(
                3, source_mac=self._coordinator.address
            )
            raise
        address = normalize_mac(self._coordinator.address)
        previous_epoch = self._runtime.epoch
        entering_join = not self._runtime._central_link_connected
        self._runtime.central_connected(address)
        if self._runtime.epoch != previous_epoch or self._sdk_epoch != self._runtime.epoch:
            self._clear_sdk_device_addresses()
            state = self._state
            self._state = {}
            if state:
                self.forward_controller_state_updates(*_state_updates(dict.fromkeys(state)))
            self._coordinator.clear_position_feedback(("back", "legs"))
        connection_epoch = self._runtime.epoch
        try:

            def handler(_sender: Any, data: bytearray) -> None:
                if (
                    self.client is not client
                    or not client.is_connected
                    or not self._runtime.effect_is_current(
                        epoch=connection_epoch,
                        source_mac=address,
                        peer=None,
                    )
                ):
                    return
                payload = memoryview(data).tobytes()
                self._capture_raw_pairlink_notification(payload)
                self._coordinator.hass.async_create_task(
                    self._async_process_transport_packet(
                        payload, source_mac=address, peer=None,
                        expected_epoch=connection_epoch,
                    ),
                    "adjustable_bed.pairlink_rx_effects",
                )

            await client.start_notify(self._notify_uuid, handler)
            self._active_notifications.append(self._notify_uuid)
            if entering_join:
                self._sdk_metadata.reset_join_state()
            self._sync_active_control_session()
        except (BleakError, TimeoutError, OSError):
            self._runtime._on_central_library_status(
                4, source_mac=address
            )
            _LOGGER.warning("Could not start Pairlink notifications")
            self._notify_callback = None
            raise

    def _capture_raw_pairlink_notification(self, payload: bytes) -> None:
        """Keep opt-in support capture without writing protocol payloads to logs."""
        callback = self._raw_notify_callback
        if callback is None:
            return
        try:
            callback(self._notify_uuid, payload)
        except Exception:
            _LOGGER.debug("Pairlink raw notification capture callback failed")

    async def stop_notify(self) -> None:
        await self._async_sdk_exit()
        # This controller's periodic control requests depend on the same live
        # notification session that produces their replies. Stop both timer
        # paths even when HA already dropped the Bleak client during unload.
        self._set_active_control_session(False)
        self._cancel_clock_sync()
        self._cancel_backup_check()
        if self.client is None or not self.client.is_connected:
            self._active_notifications.clear()
            self._notify_callback = None
            return
        failures: list[Exception] = []
        for char_uuid in reversed(self._active_notifications):
            try:
                await self.client.stop_notify(char_uuid)
            except Exception as err:
                failures.append(err)
        self._active_notifications.clear()
        self._notify_callback = None
        if failures:
            raise ExceptionGroup("Pairlink notification cleanup failed", failures)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Positions arrive through the typed mesh event boundary, not GATT reads."""
        del motor_count

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Send one four-byte app payload; Pairlink has no repeated-write cadence."""
        del repeat_delay_ms
        if repeat_count != 1:
            raise ValueError("Pairlink accepts only one-shot command writes")
        await self.async_send_payload(command, cancel_event=cancel_event)

    async def async_send_payload(
        self,
        payload: bytes,
        *,
        destination: bytes = PAIRLINK_BROADCAST_ADDRESS,
        channel: int = 32,
        send_appearance: bool = False,
        cancel_event: asyncio.Event | None = None,
        prepared_snapshot: PairlinkSendSnapshot | None = None,
        refresh_telemetry: bool = False,
        refresh_release_telemetry: bool = False,
    ) -> None:
        """Send one source-framed action through the already selected Pairlink role."""
        if not self._has_supported_model:
            raise PairlinkRuntimeNotReadyError(
                f"Pairlink model {self.model_id} is not a supported profile"
            )
        if not isinstance(payload, bytes) or len(payload) != 4:
            raise ValueError("Pairlink dashboard payloads must be exactly four bytes")
        client = self.client
        if prepared_snapshot is not None:
            if not isinstance(prepared_snapshot, PairlinkSendSnapshot):
                raise TypeError("Prepared Pairlink snapshot has an invalid type")
            if prepared_snapshot.role is not self._runtime.role:
                raise PairlinkRuntimeNotReadyError("Prepared Pairlink role changed")
            snapshot = prepared_snapshot
            if snapshot.role is PairlinkRole.CENTRAL and (client is None or not client.is_connected):
                raise ConnectionError("Not connected to Pairlink bed")
        elif self._runtime.role is PairlinkRole.CENTRAL:
            snapshot = self._capture_current_send_snapshot()
        else:
            snapshot = self._capture_current_send_snapshot()
        frame = build_user_frame(
            payload,
            destination=destination,
            channel=channel,
            own_virtual_address=snapshot.own_virtual_address,
            send_appearance=send_appearance,
        )
        await self._async_send_profile_frame(
            frame,
            snapshot,
            cancel_event=cancel_event,
            refresh_telemetry=refresh_telemetry,
            refresh_release_telemetry=refresh_release_telemetry,
        )

    async def _async_send_profile_frame(
        self,
        frame: bytes,
        snapshot: PairlinkSendSnapshot,
        *,
        cancel_event: asyncio.Event | None = None,
        refresh_telemetry: bool = False,
        refresh_release_telemetry: bool = False,
    ) -> None:
        """Use the existing role/security/transport path for private profile consumers."""
        if refresh_telemetry or refresh_release_telemetry:
            snapshot = self._refresh_comfort_snapshot(
                snapshot, captured_release=refresh_release_telemetry
            )
        client = self.client
        if not self._runtime.allows_send(
            snapshot,
            destination=frame[1:5],
            channel=frame[5],
        ):
            raise PermissionError("Pairlink signing state rejected this mesh send")
        if snapshot.device_type == 1:
            if snapshot.device_key is None:
                raise PairlinkRuntimeNotReadyError(
                    "Pairlink encrypted route has no current target session key"
                )
            outbound = encrypt_user_frame(
                frame,
                event_key=snapshot.event_key,
                device_key=snapshot.device_key,
            )
        elif self._runtime.role is PairlinkRole.PERIPHERAL and snapshot.device_type == 0:
            outbound = frame
        else:
            raise PairlinkRuntimeNotReadyError(
                "Pairlink source device type has no supported action encoding"
            )
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        if cancel is not None and cancel.is_set():
            raise asyncio.CancelledError

        def validate_current() -> None:
            nonlocal snapshot
            if cancel is not None and cancel.is_set():
                raise asyncio.CancelledError
            if refresh_telemetry or refresh_release_telemetry:
                snapshot = self._refresh_comfort_snapshot(
                    snapshot, captured_release=refresh_release_telemetry
                )
            if not self._runtime.snapshot_is_current(snapshot):
                raise PairlinkRuntimeNotReadyError(
                    "Pairlink session changed before the action reached transport"
                )
            if not self._runtime.allows_send(
                snapshot, destination=frame[1:5], channel=frame[5]
            ):
                raise PermissionError("Pairlink signing state changed before transport")

        async def send_current() -> None:
            validate_current()
            try:
                if snapshot.role is PairlinkRole.CENTRAL:
                    if client is None or not client.is_connected:
                        raise ConnectionError("Pairlink central link ended before the write")
                    await send_central_frame(
                        self._central_writer(client),
                        outbound,
                        characteristic=self._write_uuid,
                        att_mtu=snapshot.mtu,
                    )
                else:
                    await self._runtime.async_notify_to_peer(
                        snapshot, outbound, validate_send=validate_current
                    )
            except BleakError:
                _LOGGER.warning("Pairlink central GATT write failed")
                raise

        if snapshot.role is PairlinkRole.CENTRAL:
            async with self._ble_lock:
                await send_current()
        else:
            # BlueZ's acquired peer socket has its own nonblocking writer lock.
            # Do not hold the controller's central GATT lock while notifying it.
            await send_current()
            if (
                len(outbound) > 5
                and outbound[5] == 0xFE
                and self._runtime.snapshot_is_current(snapshot)
            ):
                self._sdk_entry_state.started_ms = self._sdk_now_ms()

    def _capture_current_send_snapshot(self) -> PairlinkSendSnapshot:
        """Capture current authentication on the selected physical route."""
        if self._runtime.role is PairlinkRole.CENTRAL:
            client = self.client
            if client is None or not client.is_connected:
                raise ConnectionError("Not connected to Pairlink bed")
            self._resolve_gatt_endpoints()
            mtu = client.mtu_size
            if isinstance(mtu, bool) or not isinstance(mtu, int) or mtu < 4:
                raise ConnectionError("Pairlink BLE client reported an invalid ATT MTU")
            return self._runtime.prepare_send(mtu=mtu)
        return self._runtime.prepare_send()

    def _refresh_comfort_snapshot(
        self, captured: PairlinkSendSnapshot, *, captured_release: bool = False
    ) -> PairlinkSendSnapshot:
        """Accept telemetry changes while retaining captured transport and authentication."""
        if captured_release and captured.role is PairlinkRole.PERIPHERAL:
            current = self._runtime.prepare_release_snapshot(captured, mtu=captured.mtu)
        else:
            current = self._capture_current_send_snapshot()
        if replace(
            current,
            state_generation=captured.state_generation,
            peer_state_generation=captured.peer_state_generation,
        ) != captured:
            raise PairlinkRuntimeNotReadyError("Pairlink comfort transport or authentication changed")
        return current

    async def _async_release_to_captured_target(
        self,
        payload: bytes,
        captured: PairlinkSendSnapshot,
    ) -> None:
        """Refresh auth, then release only the captured physical session."""
        current = self._runtime.prepare_release_snapshot(
            captured,
            mtu=captured.mtu,
        )
        await self.async_send_payload(
            payload,
            cancel_event=asyncio.Event(),
            prepared_snapshot=current,
            refresh_release_telemetry=True,
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported Pairlink held control: {control}")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            raise ValueError("Pairlink hold duration must be an integer number of milliseconds")
        if not 100 <= duration_ms <= 60_000:
            raise ValueError("Pairlink hold duration must be between 100 and 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        captured = self._capture_current_send_snapshot()
        start_command, stop_command = {
            "back_up": (1, 3),
            "back_down": (2, 3),
            "legs_up": (4, 6),
            "legs_down": (5, 6),
            "lumbar_up": (7, 9),
            "lumbar_down": (8, 9),
        }[control]
        try:
            await self.async_send_payload(
                dashboard_payload(start_command, 0xFF),
                prepared_snapshot=captured,
            )
            await asyncio.sleep(duration_ms / 1000)
        except BaseException as operation_error:
            try:
                await self._async_release_to_captured_target(
                    dashboard_payload(stop_command, 0), captured
                )
            except BaseException as release_error:
                raise BaseExceptionGroup(
                    "Pairlink held command and release both failed",
                    [operation_error, release_error],
                ) from operation_error
            raise
        else:
            await self._async_release_to_captured_target(
                dashboard_payload(stop_command, 0), captured
            )

    async def _move(self, command: int, value: int = 0xFF) -> None:
        await self.async_send_payload(dashboard_payload(command, value))

    async def _stop_axis(self, command: int) -> None:
        await self.async_send_payload(dashboard_payload(command, 0), cancel_event=asyncio.Event())

    async def move_head_up(self) -> None:
        await self._move(1)

    async def move_head_down(self) -> None:
        await self._move(2)

    async def move_head_stop(self) -> None:
        await self._stop_axis(3)

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move(4)

    async def move_legs_down(self) -> None:
        await self._move(5)

    async def move_legs_stop(self) -> None:
        await self._stop_axis(6)

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    def _require_lumbar_support(self) -> None:
        if not self.has_lumbar_support:
            raise ValueError("Pairlink lumbar control is unavailable for the selected model")

    async def move_lumbar_up(self) -> None:
        self._require_lumbar_support()
        await self._move(7)

    async def move_lumbar_down(self) -> None:
        self._require_lumbar_support()
        await self._move(8)

    async def move_lumbar_stop(self) -> None:
        self._require_lumbar_support()
        await self._stop_axis(9)

    async def stop_all(self) -> None:
        self._cancel_routine()
        failures: list[Exception] = []
        commands = (3, 6, 9) if self.has_lumbar_support else (3, 6)
        for command in commands:
            try:
                await self._stop_axis(command)
            except Exception as err:
                failures.append(err)
        if failures:
            raise ExceptionGroup("Pairlink axis STOP writes failed", failures)

    @staticmethod
    def _position_value(position: int) -> int:
        if isinstance(position, bool) or not isinstance(position, int):
            raise ValueError("Pairlink position must be an integer")
        return min(100, max(0, position))

    async def set_motor_position(self, motor: str, position: int) -> None:
        if not self._has_supported_model:
            raise ValueError(f"Pairlink model {self.model_id} has no direct position controls")
        command = {"head": 1, "back": 1, "feet": 4, "foot": 4, "legs": 4, "lumbar": 7}.get(motor)
        if command is None:
            raise ValueError(f"Unsupported Pairlink position axis: {motor}")
        if motor == "lumbar" and not self.has_lumbar_support:
            raise ValueError("Pairlink lumbar position is unavailable for the selected model")
        value = self._position_value(position)
        if motor == "lumbar":
            value = 100 - value
        await self.async_send_payload(dashboard_payload(command, value))

    def angle_to_native_position(self, motor: str, angle: float) -> int:
        if isinstance(angle, bool) or not isinstance(angle, int | float):
            raise ValueError("Pairlink position must be numeric")
        normalized = "lumbar" if motor == "lumbar" else motor
        minimum = 0
        maximum = 100
        if normalized not in ("back", "head", "legs", "feet", "lumbar"):
            raise ValueError(f"Unsupported Pairlink position axis: {motor}")
        if normalized == "lumbar" and not self.has_lumbar_support:
            raise ValueError("Pairlink lumbar position is unavailable for the selected model")
        if not math.isfinite(angle) or not minimum <= angle <= maximum:
            raise ValueError("Pairlink position must be between 0 and 100")
        return int(round(angle))

    async def preset_flat(self) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink preset is unavailable for the selected model")
        await self._move(28, 0)

    async def preset_zero_g(self) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink preset is unavailable for the selected model")
        await self._move(98, 0)

    async def preset_anti_snore(self) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink preset is unavailable for the selected model")
        await self._move(101, 0)

    async def preset_memory(self, memory_num: int) -> None:
        if isinstance(memory_num, bool) or not isinstance(memory_num, int):
            raise ValueError("Pairlink memory slot must be an integer")
        if not 1 <= memory_num <= 4 or not self._has_supported_model:
            raise ValueError("Pairlink memory recall supports slots 1 through 4")
        await self._move(40 + memory_num, 0)

    async def program_memory(self, memory_num: int) -> None:
        del memory_num
        raise ValueError("Pairlink memory save is not a reachable app action")

    async def lights_on(self) -> None:
        await self._move(92, 0)

    async def lights_off(self) -> None:
        await self._move(93, 0)

    async def lights_toggle(self) -> None:
        current = self._state.get("under_bed_lights_on")
        if not isinstance(current, bool):
            raise ValueError("Pairlink light state is unknown; refresh state before toggling")
        await (self.lights_off() if current else self.lights_on())

    async def set_light_level(self, level: int) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink lighting is unavailable for the selected model")
        if isinstance(level, bool) or not isinstance(level, int):
            raise ValueError("Pairlink brightness must be an integer")
        value = min(100, max(0, level))
        await self.async_send_payload(a7_payload(16, value))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink lighting is unavailable for the selected model")
        if len(rgb_color) != 3:
            raise ValueError("Pairlink RGB color needs three channels")
        values = tuple(_validated_rgb_channel(channel) for channel in rgb_color)
        for selector, value in zip((17, 18, 19), values, strict=True):
            await self.async_send_payload(a7_payload(selector, value))

    def get_light_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        if isinstance(self._state.get("under_bed_lights_on"), bool):
            state["is_on"] = self._state["under_bed_lights_on"]
        if isinstance(self._state.get("light_level"), int):
            state["light_level"] = self._state["light_level"]
        rgb = tuple(self._state.get(f"reverie_pairlink_rgb_{index}") for index in (1, 2, 3))
        if all(isinstance(channel, int) for channel in rgb):
            state["rgb_color"] = rgb
        return state

    async def read_light_state(self) -> tuple[StateUpdate, ...]:
        """Return only current event-backed values; no undocumented query is sent."""
        on = self._state.get(UNDER_BED_LIGHTS_ON)
        level = self._state.get(LIGHT_LEVEL)
        return (
            *((UNDER_BED_LIGHTS_ON(on),) if isinstance(on, bool) else ()),
            *((LIGHT_LEVEL(level),) if isinstance(level, int) else ()),
        )

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink massage is unavailable for the selected model")
        if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 10:
            raise ValueError("Pairlink massage intensity must be between 0 and 10")
        command = {"head": 77, "foot": 79}.get(zone)
        if command is None:
            raise ValueError(f"Unsupported Pairlink massage zone: {zone}")
        value = 0 if level == 0 else 5 * level + 15
        await self._move(command, value)

    async def massage_off(self) -> None:
        await self._move(72, 0)

    async def massage_head_up(self) -> None:
        await self._step_massage("head", 1)

    async def massage_head_down(self) -> None:
        await self._step_massage("head", -1)

    async def massage_foot_up(self) -> None:
        await self._step_massage("foot", 1)

    async def massage_foot_down(self) -> None:
        await self._step_massage("foot", -1)

    async def _step_massage(self, zone: str, delta: int) -> None:
        key = f"massage_{zone}_intensity"
        current = self._state.get(key)
        if isinstance(current, bool) or not isinstance(current, int):
            raise ValueError(f"Pairlink {zone} massage intensity is unknown")
        await self.set_massage_intensity(zone, current + delta)

    async def set_massage_timer_byte(self, value: int) -> None:
        """Set the source timer byte without claiming a minute conversion."""
        if not self._has_supported_model:
            raise ValueError("Pairlink massage is unavailable for the selected model")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError("Pairlink massage timer byte must be between 0 and 255")
        await self.async_send_payload(a7_payload(22, value))

    async def set_massage_mode(self, mode: int) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink massage is unavailable for the selected model")
        if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 4:
            raise ValueError("Pairlink massage mode must be between 0 and 4")
        await self.async_send_payload(a7_payload(21, mode))

    async def set_massage_rhythm(self, enabled: bool) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink massage is unavailable for the selected model")
        if not isinstance(enabled, bool):
            raise ValueError("Pairlink massage rhythm must be a boolean")
        await self.async_send_payload(a7_payload(20, 1 if enabled else 0))

    async def massage_mode_step(self) -> None:
        current = self._state.get("reverie_massage_mode")
        if isinstance(current, bool) or not isinstance(current, int):
            raise ValueError("Pairlink massage mode is unknown")
        await self.set_massage_mode((current + 1) % 5)

    def get_massage_state(self) -> dict[str, Any]:
        return {
            "head_intensity": self._state.get("massage_head_intensity"),
            "foot_intensity": self._state.get("massage_foot_intensity"),
            "timer_mode": self._state.get("reverie_massage_timer"),
            "mode": self._state.get("reverie_massage_mode"),
        }

    @property
    def _comfort_field_names(self) -> tuple[str, ...]:
        lumbar = ("lumbar_position",) if self.has_lumbar_support else ()
        return (
            "head_position",
            "foot_position",
            *lumbar,
            "head_massage",
            "foot_massage",
            "timer_byte",
            "mode",
        )

    def validate_comfort_request(self, request: ReverieComfortRequest) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink comfort is unavailable for the selected model")
        validate_comfort_request(
            request,
            supported_fields=frozenset(self._comfort_field_names),
            value_ranges={
                "head_position": (0, 100),
                "foot_position": (0, 100),
                "lumbar_position": (0, 100),
                "head_massage": (0, 10),
                "foot_massage": (0, 10),
                "timer_byte": (0, 255),
                "mode": (0, 4),
            },
        )
        if request.force and any(
            value is None
            for value in (
                getattr(request, name) for name in self._comfort_field_names
            )
        ):
            raise ValueError("Forced Pairlink comfort requires every supported value")

    def comfort_runtime_identity(self) -> PairlinkRuntime:
        """Return the entry-owned runtime key for preflight plan routing."""
        return self._runtime

    def prepare_comfort(self, request: ReverieComfortRequest) -> PairlinkComfortPlan:
        """Resolve every request field against one authenticated live session."""
        self.validate_comfort_request(request)
        if self._runtime.role is PairlinkRole.CENTRAL:
            client = self.client
            if client is None or not client.is_connected:
                raise PairlinkRuntimeNotReadyError("Pairlink central link is not connected")
            mtu = client.mtu_size
        else:
            if not self._runtime.disconnected_transport_ready:
                raise PairlinkRuntimeNotReadyError("Pairlink local session is not ready")
            mtu = 23
        snapshot = self._runtime.prepare_send(mtu=mtu)
        if not self._runtime.allows_send(
            snapshot,
            destination=PAIRLINK_BROADCAST_ADDRESS,
            channel=32,
        ):
            raise PermissionError("Pairlink signing state rejected this comfort request")
        current = self._comfort_current_values()
        values: dict[str, int] = {}
        for name in self._comfort_field_names:
            requested = getattr(request, name)
            if requested is not None:
                values[name] = requested
                continue
            current_value = current.get(name)
            if current_value is None:
                raise ValueError(
                    f"Pairlink comfort cannot preserve {name}: current state is unknown"
                )
            values[name] = current_value
        payloads = comfort_payloads(
            values=values,
            current=current,
            force=request.force,
        )
        omitted_fields = tuple(
            name
            for name in self._comfort_field_names
            if getattr(request, name) is None
        )
        return PairlinkComfortPlan(
            owner=self._runtime,
            snapshot=snapshot,
            request_signature=_comfort_request_signature(request),
            payloads=payloads,
            omitted_fields=omitted_fields,
        )

    def comfort_plan_is_current(
        self,
        request: ReverieComfortRequest,
        plan: PairlinkComfortPlan,
    ) -> bool:
        """Revalidate one action plan immediately before scheduler commit."""
        return bool(
            isinstance(plan, PairlinkComfortPlan)
            and plan.owner is self._runtime
            and plan.request_signature == _comfort_request_signature(request)
            and self._runtime.snapshot_is_current(plan.snapshot)
            and self._runtime.allows_send(
                plan.snapshot,
                destination=PAIRLINK_BROADCAST_ADDRESS,
                channel=32,
            )
        )

    async def async_set_comfort(
        self,
        request: ReverieComfortRequest,
        *,
        prepared_plan: PairlinkComfortPlan | None = None,
    ) -> None:
        """Send only a plan bound to this runtime's current live generation."""
        self.validate_comfort_request(request)
        plan = prepared_plan if prepared_plan is not None else self.prepare_comfort(request)
        if (
            not isinstance(plan, PairlinkComfortPlan)
            or plan.owner is not self._runtime
            or plan.request_signature != _comfort_request_signature(request)
            or not self.comfort_plan_is_current(request, plan)
        ):
            raise PairlinkRuntimeNotReadyError(
                "Pairlink comfort preflight no longer matches the current session"
            )
        for index, payload in enumerate(plan.payloads):
            await self.async_send_payload(
                payload, prepared_snapshot=plan.snapshot, refresh_telemetry=index > 0
            )

    def _comfort_current_values(self) -> dict[str, int]:
        current: dict[str, int] = {}
        for name, state_key in (
            ("head_position", "back_position"),
            ("foot_position", "legs_position"),
            ("lumbar_position", "reverie_pairlink_head2_position"),
            ("head_massage", "massage_head_intensity"),
            ("foot_massage", "massage_foot_intensity"),
            ("timer_byte", "reverie_massage_timer"),
            ("mode", "reverie_massage_mode"),
        ):
            value = self._state.get(state_key)
            if isinstance(value, int) and not isinstance(value, bool):
                current[name] = value
        return current

    def validate_routine(
        self, steps: list[tuple[ReverieComfortRequest | None, int | None]]
    ) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink routines are unavailable for the selected model")
        for request, duration_minutes in steps:
            if duration_minutes is not None and (
                isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int)
            ):
                raise ValueError("Pairlink routine duration must be an integer number of minutes")
            if request is None:
                continue
            if request.force:
                raise ValueError("Pairlink routine steps use ordinary comfort dispatch")
            self.validate_comfort_request(request)

    async def async_start_routine(
        self, steps: list[tuple[ReverieComfortRequest | None, int | None]]
    ) -> None:
        """Replace settings and times independently, then run the first setting."""
        self.validate_routine(steps)
        self._cancel_routine()
        generation = self._routine_generation
        self._routine_settings = [request for request, _ in steps if request is not None]
        self._routine_times = [duration for _, duration in steps]
        self._routine_index = 0
        if self._routine_settings:
            self._hold_routine_connection()
            await self._run_routine_step(generation)

    def _hold_routine_connection(self) -> None:
        context = self._coordinator.hold_command_connection()
        context.__enter__()

        def release() -> None:
            context.__exit__(None, None, None)

        self._routine_connection_release = release

    def _release_routine_connection(self) -> None:
        release = self._routine_connection_release
        self._routine_connection_release = None
        if release is not None:
            release()

    def _routine_owner_is_current(self) -> bool:
        if self._routine_owner is None:
            return True
        epoch, peer = self._routine_owner
        return self._runtime.primary_mac == peer.address and self._runtime.effect_is_current(
            epoch=epoch, source_mac=peer.address, peer=peer
        )

    async def _run_routine_step(self, generation: int) -> None:
        if generation != self._routine_generation:
            return
        self._routine_timer = None
        if self._routine_index >= len(self._routine_settings):
            self._clear_routine()
            return
        index = self._routine_index
        request = self._routine_settings[index]
        self._routine_index += 1
        try:
            if self._runtime.role is PairlinkRole.PERIPHERAL and self._routine_owner is None:
                snapshot = self._capture_current_send_snapshot()
                if snapshot.peer is None:
                    raise PairlinkRuntimeNotReadyError(
                        "Pairlink routine peer identity is unavailable"
                    )
                self._routine_owner = (snapshot.epoch, snapshot.peer)
            if not self._routine_owner_is_current():
                self._cancel_routine()
                return
            await self.async_set_comfort(request)
        except BaseException:
            self._cancel_routine()
            raise
        if generation != self._routine_generation:
            return
        if self._routine_index >= len(self._routine_settings):
            self._clear_routine()
            return
        duration_minutes = self._routine_times[index] if index < len(self._routine_times) else None
        delay_seconds = max(1, duration_minutes or 1) * 60
        self._routine_timer = self._coordinator.hass.loop.call_later(
            delay_seconds, self._enqueue_routine_step, generation
        )

    def _enqueue_routine_step(self, generation: int) -> None:
        if generation != self._routine_generation:
            return
        self._routine_timer = None

        async def execute(controller: BedController) -> None:
            if controller is self and generation == self._routine_generation:
                await self._run_routine_step(generation)

        self._coordinator.hass.async_create_task(
            self._coordinator.async_execute_controller_command(
                execute,
                cancel_running=False,
                resource="reverie:pairlink:routine",
                read_positions_after_operation=False,
            ),
            "adjustable_bed.reverie_pairlink_routine_step",
        )

    def _cancel_routine(self) -> None:
        self._routine_generation += 1
        if self._routine_timer is not None:
            self._routine_timer.cancel()
            self._routine_timer = None
        self._clear_routine()

    def _clear_routine(self) -> None:
        self._routine_owner = None
        self._routine_settings.clear()
        self._routine_times.clear()
        self._routine_index = 0
        self._release_routine_connection()

    async def async_start_diagnostic(self) -> None:
        """Run the accepted two-second selected-mesh test and exact stop pair."""
        if not self._has_supported_model:
            raise ValueError("Pairlink diagnostic is unavailable for the selected model")
        captured = self._capture_current_send_snapshot()
        self._cancel_diagnostic()
        generation = self._diagnostic_generation
        self._diagnostic_snapshot = captured
        context = self._coordinator.hold_command_connection()
        context.__enter__()

        def release() -> None:
            context.__exit__(None, None, None)

        self._diagnostic_connection_release = release
        self._diagnostic_timer = self._coordinator.hass.loop.call_later(
            2, self._enqueue_diagnostic_stop, captured, generation
        )
        failures: list[Exception] = []
        for payload in (dashboard_payload(79, 20), dashboard_payload(92, 0)):
            try:
                await self.async_send_payload(
                    payload, prepared_snapshot=captured, refresh_telemetry=True
                )
            except Exception as err:
                failures.append(err)
        if failures:
            raise ExceptionGroup("Pairlink diagnostic start writes failed", failures)

    def _enqueue_diagnostic_stop(
        self, captured: PairlinkSendSnapshot, generation: int
    ) -> None:
        if generation != self._diagnostic_generation:
            return
        self._diagnostic_timer = None
        self._coordinator.hass.async_create_task(
            self._stop_diagnostic(captured, generation),
            "adjustable_bed.reverie_pairlink_diagnostic_stop",
        )

    async def _stop_diagnostic(
        self, captured: PairlinkSendSnapshot, generation: int
    ) -> None:
        failures: list[Exception] = []

        async def write_stops(controller: BedController) -> None:
            if (
                not isinstance(controller, ReveriePairlinkController)
                or controller._runtime is not self._runtime
                or generation != self._diagnostic_generation
            ):
                return
            for payload in (dashboard_payload(72, 0), dashboard_payload(93, 0)):
                try:
                    await controller._async_release_to_captured_target(payload, captured)
                except Exception as err:
                    failures.append(err)

        try:
            await self._coordinator.async_execute_controller_command(
                write_stops,
                cancel_running=False,
                resource="reverie:pairlink:diagnostic",
                read_positions_after_operation=False,
            )
        finally:
            if generation == self._diagnostic_generation:
                self._cancel_diagnostic()
        if failures:
            raise ExceptionGroup("Pairlink diagnostic stop writes failed", failures)

    def validate_diagnostic(self) -> None:
        if not self._has_supported_model:
            raise ValueError("Pairlink diagnostic is unavailable for the selected model")

    def _cancel_diagnostic(self) -> None:
        self._diagnostic_generation += 1
        self._diagnostic_snapshot = None
        if self._diagnostic_timer is not None:
            self._diagnostic_timer.cancel()
            self._diagnostic_timer = None
        release = self._diagnostic_connection_release
        self._diagnostic_connection_release = None
        if release is not None:
            release()

    def _cancel_runtime_owned_activity(self) -> None:
        """Invalidate controller timers when the entry-owned runtime closes."""
        self._set_active_control_session(False)
        self._cancel_clock_sync()
        self._cancel_backup_check()
        self._cancel_routine()
        self._cancel_diagnostic()

    def on_disconnect(self) -> None:
        self._cancel_runtime_owned_activity()
        self._active_notifications.clear()
        if self._runtime.role is PairlinkRole.CENTRAL and self._runtime.target_mac is not None:
            self._clear_sdk_device_addresses()
            state = self._state
            self._state = {}
            if state:
                self.forward_controller_state_updates(*_state_updates(dict.fromkeys(state)))
            self._coordinator.clear_position_feedback(("back", "legs"))
            self._runtime.central_disconnected(self._runtime.target_mac)
        else:
            self._clear_sdk_device_addresses()
            for address in tuple(self._peer_states):
                self._clear_peer_state(address, clear_positions=True)
            self._peer_state_identities.clear()
            self._state = {}
        super().on_disconnect()


def _comfort_request_signature(request: ReverieComfortRequest) -> tuple[object, ...]:
    return (
        request.head_position,
        request.foot_position,
        request.lumbar_position,
        request.head_massage,
        request.foot_massage,
        request.timer_byte,
        request.mode,
        request.force,
    )


def _validated_rgb_channel(channel: int) -> int:
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ValueError("Pairlink RGB channels must be integers")
    return min(255, max(0, channel))


async def build_controller(ctx: BuildContext) -> ReveriePairlinkController:
    """Build the controller around the entry's PairLink runtime, creating it once."""
    coordinator = ctx.coordinator
    runtime = coordinator._pairlink_runtime
    if runtime is None:
        runtime = create_pairlink_runtime_for_entry(
            ctx.data, coordinator.entry.options, manufacturer_data=ctx.manufacturer_data
        )
        coordinator._pairlink_runtime = runtime
    else:
        runtime.refresh_configured_inputs(
            ctx.data, coordinator.entry.options, manufacturer_data=ctx.manufacturer_data
        )
    return ReveriePairlinkController(
        coordinator,
        model=ctx.variant,
        device_name=ctx.device_name,
        manufacturer_data=ctx.manufacturer_data,
        runtime=runtime,
    )
