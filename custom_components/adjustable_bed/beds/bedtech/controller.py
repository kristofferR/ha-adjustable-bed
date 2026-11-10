"""BedTech legacy and explicit 7.1.3 models over the Richmat 6E codec."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...card import CARD_MASSAGE
from ...codec import richmat as codec
from ...const import BEDTECH_WRITE_CHAR_UUID, CONF_PROTOCOL_VARIANT, SIDE_LEFT, SIDE_RIGHT
from ...profiles.richmat import BEDTECH, BEDTECH_APP_PROFILES, Button
from ..builder import BuildContext
from ..entity_specs import ControllerButtonSpec, MotorControlSpec
from ..richmat.controller import RichmatProfileController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


class BedTechController(RichmatProfileController):
    """Retain the hardware-backed legacy route; explicit models use app evidence."""

    def __init__(self, coordinator: AdjustableBedCoordinator, model: str | None = None) -> None:
        self.model = model or str(coordinator.entry.data.get(CONF_PROTOCOL_VARIANT, "auto"))
        if self.model != "auto" and self.model not in BEDTECH_APP_PROFILES:
            raise ValueError(f"Unknown BedTech model: {self.model}")
        super().__init__(
            coordinator,
            BEDTECH_APP_PROFILES.get(self.model, BEDTECH),
            char_uuid=BEDTECH_WRITE_CHAR_UUID,
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        count, delay = super().motor_pulse_settings()
        return count, self.profile.motor_repeat_ms or delay

    @property
    def app_model(self) -> bool:
        return self.model in BEDTECH_APP_PROFILES

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.app_model and self.model.endswith("fh")

    @property
    def commands_share_timer(self) -> bool:
        return self.app_model

    @property
    def auto_stops_on_idle(self) -> bool:
        # The app ends the refresh, with no release frame. Hardware is unverified.
        return self.profile.stop is None

    def _build_command(self, command_byte: int) -> bytes:
        if not self.supports_single_address_pairing:
            return super()._build_command(command_byte)
        side = self.command_side
        if command_byte in (0x24, 0x25):
            if side == SIDE_RIGHT:
                return codec.command(command_byte, 1)
            if side != SIDE_LEFT:
                if command_byte == 0x25 and self.model != "bt3000fh":
                    raise NotImplementedError("This app model has no synchronized head-down action")
                return codec.command(0x29 if command_byte == 0x24 else 0x2A)
        if side == SIDE_RIGHT and command_byte in (0x31, 0x45, 0x46, 0x58, 0x3C):
            if self.model != "bt3000fh":
                raise NotImplementedError("This app model has no secondary preset or light action")
            return codec.command(command_byte, 1)
        # Foot, memory and massage stay in bank 0, even for the second sleeper.
        return super()._build_command(command_byte)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self.app_model:
            return super().motor_control_specs
        motors = (
            MotorControlSpec(
                "back",
                "back",
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.move_back_stop(),
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda c: c.move_legs_up(),
                lambda c: c.move_legs_down(),
                lambda c: c.move_legs_stop(),
            ),
        )
        if self.model == "bt6500":
            return (
                *motors,
                MotorControlSpec(
                    "head",
                    "pillow",
                    lambda c: c.move_pillow_up(),
                    lambda c: c.move_pillow_down(),
                    lambda c: c.move_pillow_stop(),
                ),
                MotorControlSpec(
                    "lumbar",
                    "lumbar",
                    lambda c: c.move_lumbar_up(),
                    lambda c: c.move_lumbar_down(),
                    lambda c: c.move_lumbar_stop(),
                ),
            )
        return motors

    def _supports_button(self, name: Button) -> bool:
        if name not in (self.profile.codes or {}):
            return False
        try:
            self._build_command(self._code(name))
        except NotImplementedError:
            return False
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return self._supports_button("flat")

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._supports_button("zero_g")

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._supports_button("anti_snore")

    @property
    def supports_preset_tv(self) -> bool:
        return self._supports_button("tv")

    @property
    def supports_lights(self) -> bool:
        return self._supports_button("light_toggle")

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._supports_button("light_toggle")

    @property
    def supports_massage(self) -> bool:
        return self.app_model and any(
            key.startswith("massage_") for key in self.profile.codes or {}
        )

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return "massage_off" in (self.profile.codes or {})

    @property
    def supports_massage_toggle_control(self) -> bool:
        return "massage_toggle" in (self.profile.codes or {})

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return "massage_head" in (self.profile.codes or {})

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return "massage_foot" in (self.profile.codes or {})

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return "massage_mode" in (self.profile.codes or {})

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if not self._supports_button("massage_timer_20"):
            return ()
        return (
            ControllerButtonSpec(
                "bedtech_massage_timer_20",
                "Massage 20 minutes",
                lambda controller: controller.set_massage_timer(20),
                icon="mdi:timer-outline",
                translation_key="bedtech_massage_timer_20",
                card=CARD_MASSAGE,
            ),
        )

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes != 20 or not self._supports_button("massage_timer_20"):
            raise ValueError("This BedTech model only exposes the 20-minute timer")
        await self._send("massage_timer_20")

    async def massage_off(self) -> None:
        await self._send("massage_off")

    async def lights_on(self) -> None:
        """The OEM app offers a toggle, without a discrete ON."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        await self._send("light_off")

    def validate_app_action(self, action: str) -> None:
        """Reject missing UI actions and routed model dead ends before any write."""
        if not self.app_model:
            raise ValueError("Choose an explicit BedTech app model first")
        if action == "connectionTest" and self.supports_single_address_pairing and self.command_side == SIDE_RIGHT:
            raise ValueError("The connection test raises the first head; target Left or the parent")
        if action in {"stop", "connectionTest", "memory1", "memory1Save", "memory2", "memory2Save"}:
            return
        if action not in APP_ACTIONS:
            raise ValueError(f"Unknown BedTech action: {action}")
        self._build_command(self._code(APP_ACTIONS[action]))

    async def app_action(self, action: str) -> None:
        """One ordinary app action, bounded by HA's normal movement pulse count."""
        self.validate_app_action(action)
        if action == "connectionTest":
            # The app's explicit setup test holds the first head for two seconds.
            # HA owns connection handoff and cancellation, rather than a JS timer.
            with self.side_scope(SIDE_LEFT):
                deadline = asyncio.timeout(2)
                try:
                    async with deadline:
                        await self.write_command(
                            self._build_command(self._code("head_up")),
                            repeat_count=21,
                            repeat_delay_ms=100,
                        )
                except TimeoutError:
                    if not deadline.expired():
                        raise
                finally:
                    await self._release()
            return
        if action == "massageTimer20":
            await self.set_massage_timer(20)
            return
        if action == "stop":
            await self.stop_all()
            return
        if action.startswith("memory"):
            slot = int(action[6])
            if action.endswith("Save"):
                await self.program_memory(slot)
            else:
                await self.preset_memory(slot)
            return
        button = APP_ACTIONS[action]
        code = self._code(button)
        if button.endswith(("_up", "_down")):
            await self._move_with_stop(code)
        else:
            await self._send(button)


APP_ACTIONS: dict[str, Button] = {
    "headUp": "head_up",
    "headDown": "head_down",
    "footUp": "feet_up",
    "footDown": "feet_down",
    "pillowUp": "pillow_up",
    "pillowDown": "pillow_down",
    "lumbarUp": "lumbar_up",
    "lumbarDown": "lumbar_down",
    "presetFlat": "flat",
    "presetZeroG": "zero_g",
    "presetAntiSnore": "anti_snore",
    "presetTV": "tv",
    "lightToggle": "light_toggle",
    "massageOn": "massage_toggle",
    "massageOff": "massage_off",
    "headMassageUp": "massage_head",
    "footMassageUp": "massage_foot",
    "massageMode": "massage_mode",
    "massageTimer20": "massage_timer_20",
}
APP_ACTION_CHOICES = (
    *APP_ACTIONS,
    "memory1",
    "memory1Save",
    "memory2",
    "memory2Save",
    "stop",
    "connectionTest",
)


async def build_controller(ctx: BuildContext) -> BedTechController:
    return BedTechController(ctx.coordinator, ctx.variant or "auto")
