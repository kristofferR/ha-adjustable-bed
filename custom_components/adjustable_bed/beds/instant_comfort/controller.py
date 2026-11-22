"""Instant Comfort bases use the proven Malouf and Reverie frame carriers."""

from ...codec import personal_comfort as codec
from ...command_scheduler import Delivery, delivered
from ...errors import invalid
from ...profiles.instant_comfort import MODELS, PROFILES
from ...profiles.richmat import Button
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import BedController
from ..builder import BuildContext
from ..personal_comfort.controller import PersonalComfortBase
from .air import InstantComfortAir


class InstantComfortBase(PersonalComfortBase):
    async def massage_action(self, action: Button) -> None:
        # V2's plus and minus endpoints both start that zone at 50.
        if self.profile.key == "reverie_v2":
            if action == "massage_head_down":
                action = "massage_head"
            elif action == "massage_foot_down":
                action = "massage_foot"
        await super().massage_action(action)

    async def set_light(self, on: bool) -> None:
        self.validate_action("light")
        if self.profile.key != "reverie_v2":
            raise invalid("not_supported_by_bed", feature="discrete light control")
        characteristic, packet = codec.base6("light", light_on=on)

        def record(result: Delivery) -> None:
            if result == Delivery.SENT:
                self._light_on = on

        with delivered(record), self.sent_state(UNDER_BED_LIGHTS_ON(on)):
            await self.send(self.capture(), characteristic, packet)


async def build_controller(ctx: BuildContext) -> BedController:
    profile = PROFILES.get(ctx.variant or "")
    if profile is None:
        raise invalid("action_rejected", reason="Choose an Instant Comfort controller")
    if profile.key in ("anm3", "anm5", "ra"):
        layout = str(ctx.data.get("product_type", ""))
        if profile.key == "anm5" and layout not in ("two", "four"):
            raise invalid("action_rejected", reason="Choose the pressure channel layout")
        return InstantComfortAir(ctx.coordinator, profile, layout)
    model = str(ctx.data.get("product_type", ""))
    if model not in MODELS:
        raise invalid("action_rejected", reason="Choose an Instant Comfort base model")
    return InstantComfortBase(ctx.coordinator, profile, model)
