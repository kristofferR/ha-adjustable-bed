"""Personal Comfort bases over their proven, independently selected routes."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, cast

from ...codec import personal_comfort as codec
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateUpdate
from ...profiles.personal_comfort import MODELS, PROFILES, PersonalComfortProfile
from ...profiles.richmat import Button
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import settled as _settled
from ..catalog_buttons import massage_button
from ..entity_specs import ControllerButtonSpec, ControllerMotorHoldSpec, MotorControlSpec
from ..richmat.controller import RichmatProfileController
from .air import PersonalComfortAir
from .session import Owner, PersonalComfortSession

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


async def _massage(controller: BedController, *, action: Button) -> None:
    await require_controller(controller, PersonalComfortBase).massage_action(action)


# Richmat's legacy _move_with_stop(int) has a different signature from the
# base helper. This class uses _move/held_axis instead of either helper.
class PersonalComfortBase(RichmatProfileController, PersonalComfortSession):  # pyright: ignore[reportIncompatibleMethodOverride]
    profile: PersonalComfortProfile

    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: PersonalComfortProfile, model: str
    ) -> None:
        if model not in MODELS:
            raise ValueError("Choose a Personal Comfort base model")
        super().__init__(coordinator, profile, char_uuid=profile.write, write_with_response=True)
        self.model = model
        self._wave: int | None = None
        self._light_on: bool | None = None

    @property
    def commands_share_timer(self) -> bool:
        return self.profile.key == "malouf"

    @property
    def auto_stops_on_idle(self) -> bool:
        return self.profile.key == "malouf"

    @property
    def supports_motor_control(self) -> bool:
        return self.model != "none"

    @property
    def supports_stop_all(self) -> bool:
        return self.supports_motor_control

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        # Reservation preempts the legacy event before installing its ticket.
        # The paired scheduler owns STOP/replacement admission at this point.
        self.check_owner(self.capture(), cleanup=True)

    @property
    def supports_preset_flat(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.supports_motor_control

    @property
    def has_pillow_support(self) -> bool:
        return self.profile.key != "reverie_v1" and self.model in ("pf4", "pf42")

    @property
    def memory_slot_count(self) -> int:
        return 2 if self.supports_motor_control and self.profile.key != "reverie_v1" else 0

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    @property
    def has_lumbar_support(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_motor_control and self.profile.key != "reverie_v2"

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_motor_control and self.profile.key == "reverie_v2"

    @property
    def light_state_is_assumed(self) -> bool:
        return self.profile.key == "reverie_v2"

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_discrete_light_control

    @property
    def reads_light_state_on_connect(self) -> bool:
        return self.profile.key == "reverie_v2"

    @property
    def supports_massage(self) -> bool:
        return self.model in ("pf3", "pf4", "other")

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    # The app has cycle/increment commands, never a measured absolute level.
    # Custom specs below name each operation precisely and avoid carrier buttons.
    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return False

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if not self.supports_massage:
            return ()
        verb = (
            "Increase"
            if self.profile.key == "malouf"
            else "Cycle"
            if self.profile.key == "reverie_v1"
            else "Start"
        )
        actions: list[tuple[Button, str]] = [
            ("massage_head", f"{verb} head massage"),
            ("massage_foot", f"{verb} foot massage"),
            ("massage_mode", "Cycle massage pattern"),
        ]
        if self.profile.key == "malouf":
            actions.append(("massage_head_down", "Decrease head massage"))
            actions.append(("massage_foot_down", "Decrease foot massage"))
        return tuple(
            massage_button(f"personal_comfort_{action}", label, partial(_massage, action=action))
            for action, label in actions
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self.supports_motor_control:
            return ()
        specs = [
            MotorControlSpec(
                "back",
                "back",
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.move_back_stop(),
                hold=self._motor_hold("head"),
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda c: c.move_legs_up(),
                lambda c: c.move_legs_down(),
                lambda c: c.move_legs_stop(),
                hold=self._motor_hold("feet"),
            ),
        ]
        if self.has_pillow_support:
            specs.append(
                MotorControlSpec(
                    "pillow",
                    "pillow",
                    lambda c: c.move_pillow_up(),
                    lambda c: c.move_pillow_down(),
                    lambda c: c.move_pillow_stop(),
                    hold=self._motor_hold("pillow"),
                )
            )
        return tuple(specs)

    def _motor_hold(self, axis: str) -> ControllerMotorHoldSpec:
        return ControllerMotorHoldSpec(
            f"{axis}_up",
            f"{axis}_down",
            press_is_native=True,
            stop_scope="side" if self.profile.key == "reverie_v1" else "motor",
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            control
            for spec in self.motor_control_specs
            if spec.hold is not None
            for control in (spec.hold.up_control, spec.hold.down_control)
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60_000:
            raise ValueError("Choose an available motor and a hold up to 60 seconds")
        self.validate_action(control)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        await self.held_axis(
            self.capture(), axis, direction == "up", self.leased_hold_ms(duration_ms)
        )

    def validate_action(self, action: str) -> None:
        if not self.supports_motor_control:
            raise ValueError("No base is configured")
        if action.startswith("pillow") and not self.has_pillow_support:
            raise ValueError("This model has no pillow control")
        if action.startswith("massage") and not self.supports_massage:
            raise ValueError("This model has no massage control")
        if action.startswith(("memory_", "save_")):
            if (
                action not in ("memory_1", "memory_2", "save_1", "save_2")
                or not self.supports_memory_presets
            ):
                raise ValueError("This base does not support the requested memory")

    async def action(self, owner: Owner, action: str) -> None:
        self.validate_action(action)
        if self.profile.key == "malouf":
            if action.startswith(("memory_", "save_")):
                code = self.profile.memory[int(action[-1]) - 1][int(action.startswith("save_"))]
            else:
                code = (self.profile.codes or {}).get(cast(Button, action))
                if code is None:
                    raise ValueError("Unsupported base action")
            await self.send(owner, self.profile.write, self.profile.frame(code))
        elif self.profile.key == "reverie_v1":
            await self.send(
                owner, self.profile.write, codec.base5(action, wave=codec.next_wave(self._wave))
            )
        else:
            characteristic, packet = codec.base6(action, wave=codec.next_wave(self._wave))
            await self.send(owner, characteristic, packet)
        if action == "massage_mode":
            self._wave = codec.next_wave(self._wave)

    async def _send(self, button: Button) -> None:
        await self.action(self.capture(), button)

    async def _move(self, button: Button) -> None:
        await self.hold_control(button, 1000)

    async def held_axis(self, owner: Owner, axis: str, up: bool, duration_ms: int) -> None:
        action = f"{axis}_{'up' if up else 'down'}"
        self.validate_action(action)
        try:
            if self.profile.key == "malouf":
                code = (self.profile.codes or {}).get(cast(Button, action))
                if code is None:
                    raise ValueError("Unsupported motor")
                loop = asyncio.get_running_loop()
                deadline = loop.time() + duration_ms / 1000
                try:
                    async with asyncio.timeout_at(deadline):
                        await self.send(
                            owner,
                            self.profile.write,
                            self.profile.frame(code),
                            repeat_count=max(1, (duration_ms + 199) // 200),
                            repeat_ms=200,
                            wall_clock_pacing=True,
                            deadline=deadline,
                        )
                        await self.pause(owner, max(0, deadline - loop.time()))
                except TimeoutError:
                    if loop.time() < deadline:
                        raise
            else:
                deadline = asyncio.get_running_loop().time() + duration_ms / 1000
                ceiling = asyncio.timeout_at(deadline)
                try:
                    async with ceiling:
                        await self.action(owner, action)
                        await self.pause(
                            owner, max(0, deadline - asyncio.get_running_loop().time())
                        )
                except TimeoutError:
                    if not ceiling.expired():
                        raise
        finally:
            await _settled(self.release_axis(owner, axis))

    async def release_axis(self, owner: Owner, axis: str) -> None:
        if self.profile.key == "reverie_v1":
            await self.send(owner, self.profile.write, codec.base5("stop"), cleanup=True)
        elif self.profile.key == "reverie_v2":
            characteristic, packet = codec.release_axis(axis)
            await self.send(owner, characteristic, packet, cleanup=True)

    async def _send_stop(self) -> None:
        if not self.supports_stop_all:
            return
        owner = self.capture()

        async def release() -> None:
            errors: list[Exception] = []
            axes = (
                ("head", "feet", *(("pillow",) if self.has_pillow_support else ()))
                if self.profile.key == "reverie_v2"
                else ("head",)
            )
            for axis in axes:
                try:
                    await self.release_axis(owner, axis)
                except Exception as error:
                    errors.append(error)
            if errors:
                raise ExceptionGroup("Base release failed", errors)

        await _settled(release())

    async def _stop_axis(self, button: Button) -> None:
        await self.release_axis(self.capture(), button.rsplit("_", 1)[0])

    async def move_head_stop(self) -> None:
        await self.release_axis(self.capture(), "head")

    async def move_legs_stop(self) -> None:
        await self.release_axis(self.capture(), "feet")

    move_feet_stop = move_legs_stop

    async def preset_flat(self) -> None:
        await self.action(self.capture(), "flat")

    async def preset_zero_g(self) -> None:
        await self.action(self.capture(), "zero_g")

    async def preset_anti_snore(self) -> None:
        await self.action(self.capture(), "anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        await self.action(self.capture(), f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self.action(self.capture(), f"save_{memory_num}")

    async def massage_action(self, action: Button) -> None:
        await self.action(self.capture(), action)

    async def massage_off(self) -> None:
        await self.action(self.capture(), "massage_off")

    async def lights_toggle(self) -> None:
        if self.profile.key == "reverie_v2":
            if self._light_on is None:
                raise ValueError("Light state is unknown")
            await self.set_light(not self._light_on)
        else:
            await self.action(self.capture(), "light_toggle")

    async def set_light(self, on: bool) -> None:
        self.validate_action("light")
        if self.profile.key != "reverie_v2":
            raise NotImplementedError("This base has a toggle-only light")
        characteristic, packet = codec.base6("light", light_on=on)
        await self.send(self.capture(), characteristic, packet)
        self._light_on = on
        self.forward_controller_state_update(UNDER_BED_LIGHTS_ON, on)

    async def lights_on(self) -> None:
        await self.set_light(True)

    async def lights_off(self) -> None:
        await self.set_light(False)

    async def read_light_state(self) -> tuple[StateUpdate, ...]:
        if self.profile.key != "reverie_v2":
            raise NotImplementedError
        owner = self.capture()
        self._light_on = None
        try:
            value = await owner.client.read_gatt_char(codec.reverie_uuid("db8010a0"))
        except Exception:
            self.check_owner(owner, cleanup=True)
            return (UNDER_BED_LIGHTS_ON(None),)
        self.check_owner(owner, cleanup=True)
        self._light_on = bytes(value) == b"d"
        return (UNDER_BED_LIGHTS_ON(self._light_on),)

    async def start_notify(self, callback=None) -> None:
        del callback
        roles = [(self.profile.service, self.profile.write, "write")]
        if self.profile.key == "reverie_v2":
            prefixes = ["db801021", "db801022", "db8010a0", "db8010d0"]
            if self.has_pillow_support:
                prefixes.append("db801020")
            if self.supports_massage:
                prefixes += ["db801061", "db801060", "db801080"]
            roles += [
                (self.profile.service, codec.reverie_uuid(prefix), "write") for prefix in prefixes
            ]
            roles.append((self.profile.service, codec.reverie_uuid("db8010a0"), "read"))
        self.require_gatt(roles)
        if self.profile.key == "reverie_v2":
            self.forward_controller_state_updates(*await self.read_light_state())

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._wave = None
        self._light_on = None
        self.forward_controller_state_update(UNDER_BED_LIGHTS_ON, None)


async def build_controller(ctx: BuildContext) -> BedController:
    # Setup requires an explicit route; no shared UUID silently selects a base.
    key = ctx.variant or ""
    profile = PROFILES.get(key)
    if profile is None:
        raise ValueError("Choose a Personal Comfort controller")
    if key in ("anm3", "anm5", "ra"):
        return PersonalComfortAir(ctx.coordinator, profile)
    model = str(ctx.data.get(CONF_PRODUCT_TYPE, ""))
    return PersonalComfortBase(ctx.coordinator, profile, model)
