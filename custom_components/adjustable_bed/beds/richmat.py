"""Richmat bed controllers over the Richmat 6E codec.

Reverse engineering by getrav and Richard Hopton (smartbed-mqtt).

``RichmatProfileController`` drives the fixed-table routes from profile data:
held movement with a guaranteed STOP, one-shot presets and buttons, memory
recall and programming. ``RichmatController`` adds what a Richmat remote code
decides: which motors, presets and memory slots exist, the compatibility STOP,
the light packet family and the GGRM catalog actions. Frames come from
``codec/richmat.py``; codes and timing from ``profiles/richmat.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Mapping
from functools import partial
from typing import TYPE_CHECKING, cast

from bleak import BleakClient
from bleak.exc import BleakError

from ..card import CARD_MASSAGE, CARD_UTILITY
from ..codec import richmat as codec
from ..const import (
    CONF_RICHMAT_REMOTE,
    CONF_RMCONTROL_PRODUCT,
    CONF_RMCONTROL_SIDE,
    RICHMAT_NORDIC_CHAR_UUID,
    RICHMAT_PROTOCOL_PREFIX55,
    RICHMAT_PROTOCOL_PREFIXAA,
    RICHMAT_PROTOCOL_SINGLE,
    RICHMAT_PROTOCOL_WILINKE,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTE_GGRM,
    RICHMAT_REMOTE_LP_QRRM,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_PREFIX55,
    RICHMAT_VARIANT_PREFIXAA,
    RICHMAT_VARIANT_WILINKE,
    RICHMAT_WILINKE_STOP_COMPAT_REMOTE_CODES,
    RichmatFeatures,
    get_richmat_features,
    resolve_richmat_remote_code,
    richmat_remote_has_combined_head_feet,
)
from ..position_estimate import notify_release_failed
from ..profiles.richmat import GGRM_ACTIONS, RICHMAT, Button, RichmatProfile
from .base import BedController, ControllerButtonSpec, MotorControlSpec
from .builder import BuildContext

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB = "legacy_rgb"
RICHMAT_LIGHT_PROTOCOL_RGB_STRIP = "rgb_strip"

# GGRM's app layouts only send the 0x3C toggle; its handset has no colour control.
RICHMAT_TOGGLE_LIGHT_REMOTE_CODES = frozenset({"bt6500", "ggrm"})
RICHMAT_RGB_STRIP_LIGHT_REMOTE_CODES = frozenset({"qrrm"})
RICHMAT_RGB_STRIP_LIGHT_NAME_HINTS = ("casper",)
RICHMAT_LIGHT_TIMER_ALWAYS_ON = "Always On"

RICHMAT_RGB_STRIP_LIGHT_DEFAULT_COLOR = (1, 221, 255)
RICHMAT_RGB_STRIP_LIGHT_TIMER_MAX_MINUTES = 30
RICHMAT_RGB_STRIP_LIGHT_TIMER_OPTIONS = [
    RICHMAT_LIGHT_TIMER_ALWAYS_ON,
    *(f"{minute} min" for minute in range(1, RICHMAT_RGB_STRIP_LIGHT_TIMER_MAX_MINUTES + 1)),
]

RICHMAT_LEGACY_RGB_LIGHT_DEFAULT_COLOR = (0, 255, 0)
RICHMAT_LEGACY_RGB_LIGHT_TIMER_MAX_SECONDS = 300
RICHMAT_LEGACY_RGB_LIGHT_TIMER_OPTIONS = [
    RICHMAT_LIGHT_TIMER_ALWAYS_ON,
    *(f"{minute} min" for minute in range(1, 6)),
]

_FRAMINGS: dict[str, codec.Framing] = {
    RICHMAT_PROTOCOL_WILINKE: "wilinke",
    RICHMAT_PROTOCOL_PREFIX55: "prefix55",
    RICHMAT_PROTOCOL_PREFIXAA: "prefixaa",
}


async def _ggrm_button_action(controller: BedController, *, command: int) -> None:
    target = controller
    if not isinstance(target, RichmatController):
        raise TypeError("This action requires the GGRM remote profile")
    await target.tap_ggrm_action(command)


class RichmatProfileController(BedController):
    """Fixed-table Richmat route: every frame comes from the profile's codes."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: RichmatProfile,
        *,
        char_uuid: str,
        write_with_response: bool = True,
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._char_uuid = char_uuid
        self._write_with_response = write_with_response

    @property
    def control_characteristic_uuid(self) -> str:
        return self._char_uuid

    def _code(self, button: Button) -> int:
        code = (self.profile.codes or {}).get(button)
        if code is None:
            raise NotImplementedError(f"{button} is not supported on this bed")
        return code

    def _build_command(self, command_byte: int) -> bytes:
        return self.profile.frame(command_byte)

    def _build_stop_command(self) -> bytes:
        return self._build_command(self.profile.stop)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        try:
            await self._write_gatt_with_retry(
                self._char_uuid,
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
                cancel_event=cancel_event,
                response=self._write_with_response,
            )
        except BleakError as err:
            if "not found" in str(err).lower() or "invalid" in str(err).lower():
                _LOGGER.warning(
                    "Characteristic %s may not exist on this device. "
                    "Please report this to help add support for your device.",
                    self._char_uuid,
                )
                self.log_discovered_services(level=logging.INFO)
            raise

    async def _send(self, button: Button) -> None:
        await self.write_command(self._build_command(self._code(button)))

    async def _send_stop(self) -> None:
        await self.write_command(self._build_stop_command(), cancel_event=asyncio.Event())

    async def _release(self) -> None:
        """Cleanup STOP; quiet profiles keep the original error, if any."""
        if not self.profile.quiet_release:
            await self._send_stop()
            return
        try:
            await self._send_stop()
        except Exception:
            _LOGGER.debug("Failed to send STOP during cleanup")
            # The motor may still be moving: a running estimate cannot be trusted.
            notify_release_failed(self._coordinator)

    async def _move_with_stop(self, command_byte: int) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Pulse a movement code at the entry's pulse settings, then always STOP."""
        delay_ms = self._coordinator.motor_pulse_delay_ms
        try:
            await self.write_command(
                self._build_command(command_byte),
                # A leased hold (#483) refreshes until its lease ends.
                repeat_count=self.leased_hold_refreshes(delay_ms)
                or self._coordinator.motor_pulse_count,
                repeat_delay_ms=delay_ms,
            )
        finally:
            await self._release()

    async def _move(self, button: Button) -> None:
        await self._move_with_stop(self._code(button))

    async def _stop_axis(self, button: Button) -> None:
        self._code(button)
        await self._send_stop()

    async def _recall(self, code: int) -> None:
        recall = self.profile.recall
        command = self._build_command(code)
        if not recall.release:
            await self.write_command(
                command, repeat_count=recall.repeats, repeat_delay_ms=recall.repeat_ms
            )
            return
        try:
            await self.write_command(
                command, repeat_count=recall.repeats, repeat_delay_ms=recall.repeat_ms
            )
        finally:
            await self._release()

    # Capabilities follow the profile's codes.
    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in (self.profile.codes or {})

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in (self.profile.codes or {})

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in (self.profile.codes or {})

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in (self.profile.codes or {})

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.profile.memory)

    @property
    def memory_slot_count(self) -> int:
        return len(self.profile.memory)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self.profile.memory)

    @property
    def supports_lights(self) -> bool:
        return "light_toggle" in (self.profile.codes or {})

    @property
    def has_pillow_support(self) -> bool:
        return "pillow_up" in (self.profile.codes or {})

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar_up" in (self.profile.codes or {})

    # Motors. Back and legs are the head and feet motors.
    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move("feet_up")

    async def move_legs_down(self) -> None:
        await self._move("feet_down")

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move("feet_up")

    async def move_feet_down(self) -> None:
        await self._move("feet_down")

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_pillow_up(self) -> None:
        await self._move("pillow_up")

    async def move_pillow_down(self) -> None:
        await self._move("pillow_down")

    async def move_pillow_stop(self) -> None:
        await self._stop_axis("pillow_up")

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self._stop_axis("lumbar_up")

    async def stop_all(self) -> None:
        await self._send_stop()

    # Presets and memory
    async def preset_flat(self) -> None:
        await self._recall(self._code("flat"))

    async def preset_zero_g(self) -> None:
        await self._recall(self._code("zero_g"))

    async def preset_anti_snore(self) -> None:
        await self._recall(self._code("anti_snore"))

    async def preset_tv(self) -> None:
        await self._recall(self._code("tv"))

    async def preset_lounge(self) -> None:
        await self._recall(self._code("lounge"))

    async def preset_memory(self, memory_num: int) -> None:
        if 1 <= memory_num <= len(self.profile.memory):
            await self._recall(self.profile.memory[memory_num - 1][0])
        else:
            _LOGGER.warning(
                "Invalid memory number %d (valid: 1-%d)", memory_num, len(self.profile.memory)
            )

    async def program_memory(self, memory_num: int) -> None:
        if 1 <= memory_num <= len(self.profile.memory):
            await self.write_command(self._build_command(self.profile.memory[memory_num - 1][1]))
        else:
            _LOGGER.warning(
                "Invalid memory number %d (valid: 1-%d)", memory_num, len(self.profile.memory)
            )

    # Every fixed-table route has these buttons.
    async def lights_toggle(self) -> None:
        await self._send("light_toggle")

    async def massage_toggle(self) -> None:
        await self._send("massage_toggle")

    async def massage_head_toggle(self) -> None:
        await self._send("massage_head")

    async def massage_foot_toggle(self) -> None:
        await self._send("massage_foot")

    async def massage_mode_step(self) -> None:
        await self._send("massage_mode")


class RichmatController(RichmatProfileController):
    """Richmat bed whose remote code selects motors, presets and light packets."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        is_wilinke: bool = False,
        char_uuid: str | None = None,
        remote_code: str | None = None,
        command_protocol: str | None = None,
        write_with_response: bool = True,
        entry_title: str | None = None,
        configured_name: str | None = None,
        device_name: str | None = None,
    ) -> None:
        """Initialize the Richmat controller.

        Args:
            is_wilinke: WiLinke variant (5-byte frames) unless ``command_protocol`` is set
            char_uuid: The characteristic UUID to use for writing commands
            remote_code: The remote code for feature detection (e.g., "VIRM", "I7RM")
            command_protocol: Override the command protocol (single, wilinke, prefix55, prefixaa)
            entry_title, configured_name, device_name: model hints for the light family
        """
        if not command_protocol:
            command_protocol = RICHMAT_PROTOCOL_WILINKE if is_wilinke else RICHMAT_PROTOCOL_SINGLE
        self._command_protocol = command_protocol
        self._remote_code = remote_code or RICHMAT_REMOTE_AUTO
        profile = RICHMAT[_FRAMINGS.get(command_protocol, "nordic")]
        if (
            command_protocol == RICHMAT_PROTOCOL_WILINKE
            and self._remote_code.lower() in RICHMAT_WILINKE_STOP_COMPAT_REMOTE_CODES
        ):
            _LOGGER.info(
                "Using Richmat WiLinke compatibility stop byte 0x%02X for remote '%s'",
                codec.COMPAT_STOP,
                self._remote_code,
            )
            profile = dataclasses.replace(profile, stop=codec.COMPAT_STOP)
        super().__init__(
            coordinator,
            profile,
            char_uuid=char_uuid or RICHMAT_NORDIC_CHAR_UUID,
            write_with_response=write_with_response,
        )
        self._is_wilinke = is_wilinke
        # The 456-code generated mapping plus manual overrides.
        self._features = get_richmat_features(self._remote_code)
        self._light_protocol_family = self._resolve_light_protocol_family(
            entry_title=entry_title,
            configured_name=configured_name,
            device_name=device_name,
        )
        _LOGGER.debug(
            "RichmatController initialized (char: %s, protocol: %s, remote: %s, stop: 0x%02X, light_protocol: %s, response: %s)",
            self._char_uuid,
            self._command_protocol,
            self._remote_code,
            self.profile.stop,
            self._light_protocol_family,
            self._write_with_response,
        )

    def _resolve_light_protocol_family(
        self,
        *,
        entry_title: str | None,
        configured_name: str | None,
        device_name: str | None,
    ) -> str | None:
        """Resolve the Richmat light packet family for this controller."""
        if self._command_protocol != RICHMAT_PROTOCOL_WILINKE:
            return None

        remote_code = (self._remote_code or "").lower()
        if remote_code in {"", RICHMAT_REMOTE_AUTO}:
            return None

        haystack = " ".join(
            part.lower() for part in (entry_title, configured_name, device_name) if part
        )

        if remote_code in RICHMAT_RGB_STRIP_LIGHT_REMOTE_CODES:
            return RICHMAT_LIGHT_PROTOCOL_RGB_STRIP

        if remote_code in RICHMAT_TOGGLE_LIGHT_REMOTE_CODES:
            return None

        if remote_code == "i7rm" and "sleep function" in haystack:
            return RICHMAT_LIGHT_PROTOCOL_RGB_STRIP

        if remote_code == "i7rm" and any(
            hint in haystack for hint in RICHMAT_RGB_STRIP_LIGHT_NAME_HINTS
        ):
            return RICHMAT_LIGHT_PROTOCOL_RGB_STRIP

        if not bool(self._features & RichmatFeatures.UNDER_BED_LIGHTS):
            return None

        return RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"richmat_is_wilinke": self._is_wilinke}

    @property
    def features(self) -> RichmatFeatures:
        """Return the feature flags for this controller."""
        return self._features

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if (
            self._remote_code.upper() != RICHMAT_REMOTE_GGRM
            or self._command_protocol != RICHMAT_PROTOCOL_WILINKE
        ):
            return ()
        # Reuse the MH action identities, translations and card sections: these
        # are the same catalog commands, explicitly selected for a QRRM receiver.
        return tuple(
            ControllerButtonSpec(
                key=f"richmat_mh_{command:02x}",
                name=label,
                press_fn=partial(_ggrm_button_action, command=command),
                icon="mdi:content-save" if kind == "richmat_mh_save" else "mdi:timer-outline",
                translation_key=kind,
                translation_placeholders={"action": label},
                card=CARD_MASSAGE if kind == "richmat_mh_massage" else CARD_UTILITY,
            )
            for command, (label, kind) in GGRM_ACTIONS.items()
            if kind != "richmat_mh_massage" or self._coordinator.has_massage
        )

    async def tap_ggrm_action(self, command: int) -> None:
        """Send a catalog ONCE action, then its release after 120 ms."""
        if not any(
            spec.key == f"richmat_mh_{command:02x}" for spec in self.controller_button_specs
        ):
            raise ValueError("This action is not available for the selected Richmat remote")
        try:
            await self.write_command(self._build_command(command))
        finally:
            try:
                await asyncio.sleep(0.12)
            finally:
                await self.write_command(self._build_stop_command(), cancel_event=asyncio.Event())

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._remote_code.upper() != RICHMAT_REMOTE_GGRM

    @property
    def supports_massage_off_control(self) -> bool:
        return self._remote_code.upper() == RICHMAT_REMOTE_GGRM

    @property
    def supports_preset_zero_g(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_ZERO_G)

    @property
    def supports_preset_anti_snore(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_ANTI_SNORE)

    @property
    def supports_preset_tv(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_TV)

    @property
    def supports_preset_lounge(self) -> bool:
        return bool(self._features & RichmatFeatures.PRESET_LOUNGE)

    @property
    def has_lumbar_support(self) -> bool:
        return bool(self._features & RichmatFeatures.MOTOR_LUMBAR)

    @property
    def has_pillow_support(self) -> bool:
        return bool(self._features & RichmatFeatures.MOTOR_PILLOW)

    @property
    def _has_head_feet_support(self) -> bool:
        """Return True when this remote drives head and feet as one step.

        Two conditions: the profile has both motors, and the remote is one we
        have confirmed sends the combined command. The motor flags alone are
        not enough, since not every Richmat remote surface has this button.

        This stays a Richmat-local predicate rather than a `BedController`
        capability flag: no entity platform queries it, and the combined step
        is a protocol detail of this remote family, not a shared motor axis.
        """
        return bool(
            self._features & RichmatFeatures.MOTOR_HEAD
            and self._features & RichmatFeatures.MOTOR_FEET
            and richmat_remote_has_combined_head_feet(self._remote_code)
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose the native Richmat layout without back/legs alias duplicates."""
        specs = [
            MotorControlSpec(
                key="head",
                translation_key="head",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
            ),
            MotorControlSpec(
                key="feet",
                translation_key="feet",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                max_angle=45,
            ),
        ]

        if self._has_head_feet_support:
            # Richmat drives head and feet together as one hardware step, which
            # is what the combined button on the physical remote sends. This is
            # not the same as opening the head and feet covers one after another.
            specs.append(
                MotorControlSpec(
                    key="head_feet",
                    translation_key="head_feet",
                    open_fn=lambda ctrl: cast(RichmatController, ctrl).move_head_feet_up(),
                    close_fn=lambda ctrl: cast(RichmatController, ctrl).move_head_feet_down(),
                    stop_fn=lambda ctrl: cast(RichmatController, ctrl).move_head_feet_stop(),
                )
            )

        if self.has_pillow_support:
            specs.append(
                MotorControlSpec(
                    key="pillow",
                    translation_key="pillow",
                    open_fn=lambda ctrl: ctrl.move_pillow_up(),
                    close_fn=lambda ctrl: ctrl.move_pillow_down(),
                    stop_fn=lambda ctrl: ctrl.move_pillow_stop(),
                )
            )

        if self.has_lumbar_support:
            specs.append(
                MotorControlSpec(
                    key="lumbar",
                    translation_key="lumbar",
                    open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                    close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                    stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                    max_angle=30,
                )
            )

        return tuple(specs)

    @property
    def estimated_position_motor_groups(self) -> Mapping[str, tuple[str, ...]]:
        """Head and feet are directional pulse trains that always end with STOP.

        Pillow and lumbar are separate actuators, so moving them leaves the
        head and feet estimates intact.
        """
        groups: dict[str, tuple[str, ...]] = {
            "head": ("head",),
            "feet": ("feet",),
            "head_feet": ("head", "feet"),
            "pillow": (),
            "lumbar": (),
        }
        keys = {spec.key for spec in self.motor_control_specs}
        return {key: motors for key, motors in groups.items() if key in keys}

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove legacy generic motor aliases when Richmat layout changes.

        `head_feet` is listed too: correcting a bed to a single-axis remote
        profile drops the combined step, and without this the old cover lingers
        in the registry as an unavailable ghost.
        """
        return frozenset({"back", "legs", "pillow", "lumbar", "head_feet"})

    @property
    def supports_lights(self) -> bool:
        """Return True if this bed supports under-bed lights."""
        return bool(self._features & RichmatFeatures.UNDER_BED_LIGHTS) or (
            self._light_protocol_family is not None
        )

    @property
    def light_protocol_family(self) -> str | None:
        """Return the selected Richmat light packet family for this bed."""
        return self._light_protocol_family

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True when the selected light family has separate on/off packets."""
        return self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP

    @property
    def supports_explicit_light_on_control(self) -> bool:
        """Return True when the selected Richmat light family has an explicit ON packet."""
        return self._light_protocol_family in {
            RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB,
            RICHMAT_LIGHT_PROTOCOL_RGB_STRIP,
        }

    @property
    def supports_light_color_control(self) -> bool:
        """Return True for Richmat remotes with verified RGB light packets."""
        return self._light_protocol_family in {
            RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB,
            RICHMAT_LIGHT_PROTOCOL_RGB_STRIP,
        }

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        """Return the default Richmat RGB light color used by the OEM apps."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            return RICHMAT_RGB_STRIP_LIGHT_DEFAULT_COLOR
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            return RICHMAT_LEGACY_RGB_LIGHT_DEFAULT_COLOR
        return None

    @property
    def supports_light_timer(self) -> bool:
        """Return True for Richmat remotes with the dedicated under-bed light timer UI."""
        return self.supports_light_color_control

    @property
    def light_timer_options(self) -> list[str]:
        """Return supported Richmat under-bed light timer options."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            return list(RICHMAT_RGB_STRIP_LIGHT_TIMER_OPTIONS)
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            return list(RICHMAT_LEGACY_RGB_LIGHT_TIMER_OPTIONS)
        return []

    @property
    def _memory_slots(self) -> int:
        """Remote codes enable slots 1 to 3; recall and save still accept 1 to 5."""
        memory = (
            RichmatFeatures.PRESET_MEMORY_1,
            RichmatFeatures.PRESET_MEMORY_2,
            RichmatFeatures.PRESET_MEMORY_3,
        )
        return sum(1 for flag in memory if self._features & flag)

    @property
    def supports_memory_presets(self) -> bool:
        return self._memory_slots > 0

    @property
    def memory_slot_count(self) -> int:
        return self._memory_slots

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        """Return model-specific names for Richmat memory slots."""
        if self._remote_code.lower() == RICHMAT_REMOTE_LP_QRRM.lower():
            return ("Custom 1", "Custom 2")
        return ()

    @property
    def supports_memory_programming(self) -> bool:
        return bool(
            self._features
            & (
                RichmatFeatures.PROGRAM_MEMORY_1
                | RichmatFeatures.PROGRAM_MEMORY_2
                | RichmatFeatures.PROGRAM_MEMORY_3
            )
        )

    @property
    def supports_synchro(self) -> bool:
        """Return True - Richmat beds support split-king sync mode."""
        return True

    def _check_rgb(self, rgb_color: tuple[int, int, int]) -> None:
        if not all(0 <= value <= 255 for value in rgb_color):
            raise ValueError(f"RGB values must be between 0 and 255: {rgb_color}")

    def _build_legacy_light_power_on_command(self) -> bytes:
        """Build the legacy Richmat light power-on packet from the Java OEM apps."""
        if self._light_protocol_family != RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            raise NotImplementedError("Legacy Richmat light power command not supported")
        return codec.frame(codec.BED, 0x0A, 0x00, 0x01)

    def _build_light_color_command(self, rgb_color: tuple[int, int, int]) -> bytes:
        """Build the Richmat RGB color packet for the selected light family."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            self._check_rgb(rgb_color)
            return codec.rgb(*rgb_color)
        if self._light_protocol_family != RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            raise NotImplementedError("RGB light control not supported for this Richmat remote")
        self._check_rgb(rgb_color)
        return codec.strip(0x01, bytes(rgb_color))

    def _build_light_power_command(self, *, is_on: bool) -> bytes:
        """Build the Richmat QRRM-family RGB-strip power packet."""
        if self._light_protocol_family != RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            raise NotImplementedError("Discrete light power control not supported")
        return codec.strip(0x04, bytes((0x02 if is_on else 0x00,)))

    def _build_light_timer_command(self, value: int) -> bytes:
        """Build the timer packet: minutes for the RGB strip, seconds for legacy RGB."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            if value < 0:
                raise ValueError(f"Timer minutes must be >= 0: {value}")
            return codec.strip(0x02, bytes(((value >> 8) & 0xFF, value & 0xFF)))
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            if not 0 <= value <= RICHMAT_LEGACY_RGB_LIGHT_TIMER_MAX_SECONDS:
                raise ValueError(f"Legacy Richmat light timer must be 0-300 seconds: {value}")
            return codec.light_timer(value >> 8, value & 0xFF)
        raise NotImplementedError("Light timer not supported for this Richmat remote")

    async def move_head_feet_up(self) -> None:
        """Move head and feet up together.

        Richmat exposes this as a single combined command, which is what the
        physical remote sends. Driving the two motors one after the other is
        not equivalent: each motor command ends with its own STOP frame, so a
        second concurrent command would cut the first one short.
        """
        await self._move("head_feet_up")

    async def move_head_feet_down(self) -> None:
        """Move head and feet down together."""
        await self._move("head_feet_down")

    async def move_head_feet_stop(self) -> None:
        """Stop the combined head and feet movement."""
        await self._send_stop()

    async def move_pillow_stop(self) -> None:
        await self._send_stop()

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    async def program_lounge(self) -> None:
        """Program current position as lounge preset."""
        await self._send("save_lounge")

    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            await self.write_command(self._build_light_power_command(is_on=True))
            return
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            await self.write_command(self._build_legacy_light_power_on_command())
            return
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            await self.write_command(self._build_light_power_command(is_on=False))
            return
        await self.lights_toggle()

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        """Set the Richmat under-bed light RGB color."""
        await self.write_command(self._build_light_color_command(rgb_color))

    async def set_light_timer(self, timer_option: str) -> None:
        """Set the under-bed light auto-off timer, in minutes or seconds per family."""
        if self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_RGB_STRIP:
            scale, limit = 1, RICHMAT_RGB_STRIP_LIGHT_TIMER_MAX_MINUTES
        elif self._light_protocol_family == RICHMAT_LIGHT_PROTOCOL_LEGACY_RGB:
            scale, limit = 60, RICHMAT_LEGACY_RGB_LIGHT_TIMER_MAX_SECONDS
        else:
            raise NotImplementedError("Light timer not supported for this Richmat remote")
        if timer_option == RICHMAT_LIGHT_TIMER_ALWAYS_ON:
            value = 0
        elif timer_option.endswith(" min") and timer_option.split()[0].isdigit():
            value = int(timer_option.split()[0]) * scale
        else:
            value = -1
        if not 0 <= value <= limit:
            raise ValueError(f"Unsupported Richmat light timer option: {timer_option}")
        await self.write_command(self._build_light_timer_command(value))

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        if not self.supports_massage_toggle_control:
            raise NotImplementedError("Massage toggle not supported for this Richmat remote")
        await self._send("massage_toggle")

    async def massage_off(self) -> None:
        """Turn off all massage using the GGRM app catalogs' All Off command."""
        if not self.supports_massage_off_control:
            raise NotImplementedError("Massage off not supported for this Richmat remote")
        await self._send("massage_off")

    async def set_synchro(self, enabled: bool) -> None:
        """Enable or disable split-king sync mode (both sides move together)."""
        await self._send("sync_on" if enabled else "sync_off")


async def detect_richmat_variant(client: BleakClient) -> tuple[bool, str | None, bool]:
    """Detect which Richmat variant this device is.

    Returns:
        Tuple of (is_wilinke, characteristic_uuid, write_with_response)
    """
    nordic = codec.TRANSPORTS["n1"]
    # Guard against missing service discovery
    if client.services is None:
        _LOGGER.warning("BLE services not discovered, falling back to Nordic Richmat variant")
        return False, nordic.write_uuid, True

    service_uuids = [s.uuid.lower() for s in client.services]
    _LOGGER.debug("Richmat variant detection - discovered services: %s", service_uuids)

    wilinke = [codec.TRANSPORTS[key] for key in RICHMAT["wilinke"].transports if key != "n1"]
    for transport in wilinke:
        service_uuid, write_uuid = transport.service_uuid, transport.write_uuid
        try:
            service = client.services.get_service(service_uuid)
            if service:
                _LOGGER.debug(
                    "Found WiLinke service %s, looking for write char %s; characteristics: %s",
                    service_uuid,
                    write_uuid,
                    [c.uuid.lower() for c in service.characteristics],
                )
                if service.get_characteristic(write_uuid):
                    _LOGGER.info(
                        "Detected WiLinke Richmat variant (service: %s, write char: %s)",
                        service_uuid,
                        write_uuid,
                    )
                    return True, write_uuid, True

                # Some beds (like Germany Motions DHN-*) use a single characteristic
                # for both read/write/notify instead of separate write and notify chars
                notify_uuid = transport.notify_uuid
                if notify_uuid != write_uuid:
                    notify_char = service.get_characteristic(notify_uuid)
                    if notify_char:
                        # Exact property match avoids "write-without-response".
                        props = {prop.lower() for prop in notify_char.properties}
                        if "write" in props:
                            _LOGGER.info(
                                "Detected WiLinke Richmat variant using notify char for writing "
                                "(service: %s, write char: %s, response: False)",
                                service_uuid,
                                notify_uuid,
                            )
                            # Single-char variants may not ack writes.
                            return True, notify_uuid, False
                    _LOGGER.debug("Notify characteristic %s not writable or not found", notify_uuid)
        except Exception as err:
            _LOGGER.debug("WiLinke variant check failed for service %s: %s", service_uuid, err)

    # Devices with Nordic UART use single-byte commands, not 5-byte WiLinke packets.
    nordic_service = None
    try:
        nordic_service = client.services.get_service(nordic.service_uuid)
    except Exception:
        pass

    if nordic_service:
        _LOGGER.info(
            "Found Nordic UART service, using single-byte Richmat variant (char: %s)",
            nordic.write_uuid,
        )
        return False, nordic.write_uuid, True

    # Like the Germany Motions app, default to W1 (FEE9) rather than Nordic.
    w1_write_char = codec.TRANSPORTS["w1"].write_uuid
    _LOGGER.info(
        "No WiLinke service/characteristic found, falling back to W1 WiLinke variant "
        "(write char: %s)",
        w1_write_char,
    )
    return True, w1_write_char, True


def _remote_code(ctx: BuildContext) -> str:
    """Resolve the remote code from the entry, its names and a live BLE name.

    An Auto remote is inferred from the BLE name at connect time, which keeps
    entries created before the code was stored working.
    """
    from ..detection import detect_richmat_remote_from_name

    coordinator = ctx.coordinator
    remote = resolve_richmat_remote_code(
        ctx.data.get(CONF_RICHMAT_REMOTE, RICHMAT_REMOTE_AUTO),
        entry_title=coordinator.entry.title,
        configured_name=coordinator.name,
    )
    if ctx.client is None:
        return remote
    if remote == RICHMAT_REMOTE_AUTO and (detected := detect_richmat_remote_from_name(ctx.device_name)):
        _LOGGER.info(
            "Auto-detected Richmat remote code '%s' from BLE name '%s'", detected, ctx.device_name
        )
        remote = detected
    return resolve_richmat_remote_code(
        remote,
        entry_title=coordinator.entry.title,
        configured_name=coordinator.name,
        device_name=ctx.device_name,
    )


_OFFLINE_ERRORS: dict[str | None, str] = {
    RICHMAT_VARIANT_WILINKE: "Cannot use WiLinke variant: client not connected",
    RICHMAT_VARIANT_PREFIX55: "Cannot use Prefix55 variant: client not connected",
    RICHMAT_VARIANT_PREFIXAA: "Cannot use PrefixAA variant: client not connected",
}
_CONFIGURED_PROTOCOLS: dict[str | None, str] = {
    RICHMAT_VARIANT_PREFIX55: RICHMAT_PROTOCOL_PREFIX55,
    RICHMAT_VARIANT_PREFIXAA: RICHMAT_PROTOCOL_PREFIXAA,
}


async def build_controller(ctx: BuildContext) -> BedController:
    """Build the Richmat or RMControl controller for the configured or detected transport."""
    coordinator = ctx.coordinator
    variant = ctx.variant
    client = ctx.client
    remote = _remote_code(ctx)
    names = {
        "entry_title": coordinator.entry.title,
        "configured_name": coordinator.name,
        "device_name": ctx.device_name,
    }

    rmcontrol_product = ctx.data.get(CONF_RMCONTROL_PRODUCT, "")
    if rmcontrol_product:
        await ctx.preload("rmcontrol")
        from .rmcontrol import RmcontrolController, detect_rmcontrol_transport

        if variant in {RICHMAT_VARIANT_PREFIX55, RICHMAT_VARIANT_PREFIXAA}:
            raise ValueError("RMControl app profiles require Nordic or WiLinke transport")
        if client is None or not client.is_connected:
            raise ConnectionError("Cannot select RMControl transport: client not connected")
        framed, char_uuid, write_with_response = await detect_rmcontrol_transport(client)
        if (variant == RICHMAT_VARIANT_NORDIC and framed) or (
            variant == RICHMAT_VARIANT_WILINKE and not framed
        ):
            raise ValueError("Configured RMControl transport disagrees with the GATT service")
        return RmcontrolController(
            coordinator,
            rmcontrol_product=rmcontrol_product,
            rmcontrol_side=ctx.data.get(CONF_RMCONTROL_SIDE, "left"),
            is_wilinke=framed,
            char_uuid=char_uuid,
            remote_code=remote,
            write_with_response=write_with_response,
            **names,
        )

    if variant == RICHMAT_VARIANT_NORDIC:
        _LOGGER.debug("Using Nordic Richmat variant (configured)")
        return RichmatController(coordinator, is_wilinke=False, remote_code=remote, **names)
    if client is None or not client.is_connected:
        raise ConnectionError(_OFFLINE_ERRORS.get(variant, "Cannot detect variant: client not connected"))
    # Even a configured WiLinke variant detects its characteristic: different
    # WiLinke devices use different UUIDs.
    is_wilinke, char_uuid, write_with_response = await detect_richmat_variant(client)
    if variant in _CONFIGURED_PROTOCOLS:
        _LOGGER.debug("Using %s Richmat variant (configured)", variant)
        return RichmatController(
            coordinator,
            is_wilinke=True,
            remote_code=remote,
            command_protocol=_CONFIGURED_PROTOCOLS[variant],
            char_uuid=char_uuid,
            write_with_response=write_with_response,
            **names,
        )
    if variant == RICHMAT_VARIANT_WILINKE:
        _LOGGER.debug("Using WiLinke Richmat variant (configured)")
        is_wilinke = True
    else:
        _LOGGER.debug("Auto-detected Richmat variant (wilinke=%s)", is_wilinke)
    return RichmatController(
        coordinator,
        is_wilinke=is_wilinke,
        char_uuid=char_uuid,
        remote_code=remote,
        write_with_response=write_with_response,
        **names,
    )
