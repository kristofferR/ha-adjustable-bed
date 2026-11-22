"""Instant Comfort pressure channels and command-owned pending transitions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from ...card import CardPlacement, CardSection
from ...codec import instant_comfort as pressure
from ...codec import personal_comfort as codec
from ...command_scheduler import command_frames_not_counted, note_frame_skipped
from ...controller_state import StateKey
from ...errors import invalid
from ..base import BedController, require_controller
from ..cancellation import cancellable
from ..entity_specs import ControllerNumberSpec
from ..personal_comfort.air import ADJUSTMENT_TIMEOUT, HYDRATION_TIMEOUT, PersonalComfortAir
from ..personal_comfort.session import Owner

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ...profiles.instant_comfort import InstantComfortProfile

LEFT_LUMBAR: Final = StateKey[int | None]("instant_comfort_left_lumbar_firmness")
RIGHT_LUMBAR: Final = StateKey[int | None]("instant_comfort_right_lumbar_firmness")
LUMBAR_KEYS: Final[tuple[tuple[codec.Side, StateKey[int | None]], ...]] = (
    ("left", LEFT_LUMBAR),
    ("right", RIGHT_LUMBAR),
)


@dataclass
class _PressureAdjustment:
    channels: int
    saw_busy: bool = False
    complete: bool = False


class _TargetAlreadyReached(Exception):
    """The latest readback needs no target frame."""


async def _set_lumbar(controller: BedController, value: float, *, side: codec.Side) -> None:
    await require_controller(controller, InstantComfortAir).set_lumbar_firmness(side, value)


class InstantComfortAir(PersonalComfortAir):
    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: InstantComfortProfile, layout: str
    ) -> None:
        super().__init__(coordinator, profile)
        self.layout = layout
        self._anm3_events: asyncio.Queue[tuple[int, int]] | None = None
        self._pressure_adjustment: _PressureAdjustment | None = None
        self._pressure: pressure.PressureReply | None = None
        self._lumbar: dict[codec.Side, int | None] = {"left": None, "right": None}

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = super().controller_number_specs
        if self.profile.key != "anm5" or self.layout != "four":
            return specs
        return (
            *specs,
            *(
                ControllerNumberSpec(
                    str(key),
                    str(key),
                    key,
                    5,
                    50,
                    1,
                    partial(_set_lumbar, side=side),
                    card=CardPlacement(CardSection.FIRMNESS),
                )
                for side, key in LUMBAR_KEYS
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **super().protocol_diagnostics,
            "pressure_layout": self.layout,
            "pressure_channels": len(self._pressure.channels) if self._pressure else None,
        }

    def parse_reply(self, packet: bytes) -> codec.AirReply | None:
        if self.profile.key != "anm5":
            return super().parse_reply(packet)
        reply = pressure.parse_pressure(packet)
        if reply is None:
            return None
        self._pressure = reply
        if len(reply.channels) != (4 if self.layout == "four" else 2):
            # Keep the observed layout, without interpreting its other channel roles.
            return codec.AirReply(reply.status)
        if reply.status == 0:
            self._lumbar = {
                "left": reply.channels[1] if len(reply.channels) == 4 else None,
                "right": reply.channels[3] if len(reply.channels) == 4 else None,
            }
            self.forward_controller_state_updates(
                LEFT_LUMBAR(self._lumbar["left"]), RIGHT_LUMBAR(self._lumbar["right"])
            )
        return reply.main

    def receive(self, packet: bytes) -> None:
        version = self._reply_version
        super().receive(packet)
        if self._reply_version == version:
            return
        if self.profile.key == "anm3" and self.status is not None and self._anm3_events is not None:
            self._anm3_events.put_nowait((self._reply_version, self.status))
        adjustment = self._pressure_adjustment
        if self.profile.key == "anm5" and adjustment is not None and self._pressure is not None:
            if len(self._pressure.channels) != adjustment.channels:
                adjustment.saw_busy = adjustment.complete = False
            elif self._pressure.status != 0:
                adjustment.saw_busy = True
                adjustment.complete = False
            elif adjustment.saw_busy:
                adjustment.complete = True

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._pressure = None
        self._lumbar = {"left": None, "right": None}
        self.forward_controller_state_updates(LEFT_LUMBAR(None), RIGHT_LUMBAR(None))

    async def query(self, owner: Owner, side: codec.Side | None = None) -> None:
        # Hydration and polling do not imply the requested target went out.
        with command_frames_not_counted():
            await super().query(owner, side)

    async def _hydrate(self, owner: Owner, side: codec.Side) -> None:
        if self.profile.key != "anm5":
            await super()._hydrate(owner, side)
            return
        async with asyncio.timeout(HYDRATION_TIMEOUT):
            if self._pressure is not None and self._pressure.status != 0:
                # Cancellation ends polling; cached BUSY may outlive the adjustment.
                cutoff = self._reply_version

                def dispatch_query() -> bytes:
                    nonlocal cutoff
                    cutoff = self._reply_version
                    return codec.anm5("query")

                with command_frames_not_counted():
                    await self.send(owner, self.profile.write, b"", command_factory=dispatch_query)

                async def wait_for_reply() -> None:
                    while self._reply_version <= cutoff:
                        await self._wait_change(owner, 1)

                await cancellable(wait_for_reply(), owner.cancel)
            while True:
                self.check_owner(owner)
                if self._pressure is not None:
                    self._validate_layout(require_idle=True)
                if self.values[side] is not None:
                    return
                await self.query(owner)
                if self.values[side] is None:
                    await self._wait_change(owner, 1)

    def _validate_layout(self, *, require_idle: bool = False) -> None:
        expected = 4 if self.layout == "four" else 2
        if self._pressure is None or len(self._pressure.channels) != expected:
            raise invalid(
                "action_rejected",
                reason="The received pressure channels do not match the selected layout",
            )
        if require_idle and self._pressure.status != 0:
            raise invalid(
                "action_rejected",
                reason="The air unit is busy; wait for it to finish or stop it before changing firmness",
            )

    async def _adjust_firmness(self, owner: Owner, side: codec.Side, target: int) -> None:
        if self.profile.key != "anm5":
            await super()._adjust_firmness(owner, side, target)
            return
        self._validate_layout(require_idle=True)
        channel = (
            (0 if side == "left" else 2) if self.layout == "four" else (0 if side == "left" else 1)
        )
        if self.values[side] != target:
            await self._set_channel(owner, channel, target)

    def validate_pressure_targets(self, main: float | None, lumbar: float | None) -> None:
        if main is None and lumbar is None:
            raise invalid("action_rejected", reason="Choose at least one firmness target")
        for value in (main, lumbar):
            if value is not None and (not float(value).is_integer() or not 5 <= value <= 50):
                raise invalid("action_rejected", reason="Firmness must be an integer from 5 to 50")
        if lumbar is not None and (self.profile.key != "anm5" or self.layout != "four"):
            raise invalid("not_supported_by_bed", feature="lumbar firmness")

    async def set_pressures(
        self, side: codec.Side, main: float | None, lumbar: float | None
    ) -> None:
        self.validate_pressure_targets(main, lumbar)
        if self.profile.key != "anm5":
            assert main is not None
            await self.set_firmness(side, main)
            return
        owner = self.capture()
        async with asyncio.timeout(ADJUSTMENT_TIMEOUT):
            await self._hydrate(owner, side)
            self._validate_layout(require_idle=True)
            channel = (
                (0 if side == "left" else 2)
                if self.layout == "four"
                else (0 if side == "left" else 1)
            )
            targets = []
            if main is not None and self.values[side] != main:
                targets.append((channel, int(main)))
            if lumbar is not None and self._lumbar[side] != lumbar:
                targets.append((1 if side == "left" else 3, int(lumbar)))
            for index, (channel, target) in enumerate(targets):
                completed = await self._set_channel(owner, channel, target)
                if not completed and index + 1 < len(targets):
                    note_frame_skipped()
                    raise invalid(
                        "action_rejected",
                        reason="The first pressure adjustment did not finish; the next target was not sent",
                    )

    async def set_lumbar_firmness(self, side: codec.Side, value: float) -> None:
        if not float(value).is_integer():
            raise invalid("action_rejected", reason="Firmness must be an integer from 5 to 50")
        await self.set_pressures(side, None, int(value))

    async def _set_channel(self, owner: Owner, channel: int, target: int) -> bool:
        self._preparing = self._active = True
        self.status = None
        self._adjusting = False
        adjustment = _PressureAdjustment(4 if self.layout == "four" else 2)
        packet = pressure.channel_target(channel, target)

        def dispatch() -> bytes:
            self._validate_layout(require_idle=True)
            # No reply from before this locked dispatch can finish this target.
            adjustment.saw_busy = adjustment.complete = False
            self._pressure_adjustment = adjustment
            return packet

        self._validate_layout()
        try:
            await self.send(owner, self.profile.write, packet, command_factory=dispatch)
            deadline = asyncio.get_running_loop().time() + 3
            while True:
                await self.pause(owner, 0.5)
                # Polls use only R>SP; TPCH initialization is not repeated here.
                with command_frames_not_counted():
                    await self.send(owner, self.profile.write, codec.anm5("query"))
                self._validate_layout()
                if adjustment.saw_busy:
                    self._preparing = False
                if adjustment.complete or (
                    not adjustment.saw_busy and asyncio.get_running_loop().time() >= deadline
                ):
                    return adjustment.complete
        finally:
            if self._pressure_adjustment is adjustment:
                self._pressure_adjustment = None
            self._preparing = self._active = False

    async def _set_anm3(self, owner: Owner, side: codec.Side, target: int, current: int) -> None:
        args = (target if side == "left" else 0, target, 3 if side == "left" else 2)
        # Only this admitted command owns its pending name/operands. Replacement
        # cannot consume another side's stale app-global pending request.
        pending = False
        retries = 0
        target_sent = False
        events: asyncio.Queue[tuple[int, int]] = asyncio.Queue()
        prepare_reply_cutoff: int | None = None
        target_reply_cutoff: int | None = None
        preparing_deadline = asyncio.get_running_loop().time() + 5

        def dispatch_prepare() -> bytes:
            nonlocal prepare_reply_cutoff
            prepare_reply_cutoff = self._reply_version
            return codec.anm3(0x69, *args)

        def dispatch_target() -> bytes:
            nonlocal target_reply_cutoff
            observed = self.values[side]
            if observed == target:
                raise _TargetAlreadyReached
            if observed is None:
                raise invalid("action_rejected", reason="The current firmness is unknown")
            opcode = 1 if target > observed else 2
            self._adjusting = True
            self._acknowledged = False
            target_reply_cutoff = self._reply_version
            return codec.anm3(opcode, *args)

        async def reenter() -> bool:
            nonlocal pending, target_sent
            if pending:
                pending = False
                try:
                    await self.send(owner, self.profile.write, b"", command_factory=dispatch_target)
                except _TargetAlreadyReached:
                    return True
                target_sent = True
            else:
                pending = True
                with command_frames_not_counted():
                    await self.send(owner, self.profile.write, b"", command_factory=dispatch_prepare)
            return False

        self._anm3_events = events
        try:
            if await reenter():
                return
            while True:
                try:
                    async with asyncio.timeout(1):
                        received, status = await cancellable(events.get(), owner.cancel)
                except TimeoutError:
                    self.check_owner(owner)
                    if asyncio.get_running_loop().time() >= preparing_deadline:
                        self._preparing = False
                    continue
                self.check_owner(owner)
                if status in (0x69, 0x88) and pending and (
                    prepare_reply_cutoff is None or received <= prepare_reply_cutoff
                ):
                    continue
                if status == 0x69 and pending:
                    if await reenter():
                        return
                elif status == 0x88 and (
                    pending or (target_reply_cutoff is not None and received > target_reply_cutoff)
                ):
                    if retries >= 3:
                        if not target_sent:
                            note_frame_skipped()
                        self._adjusting = False
                        return
                    retries += 1
                    await self.pause(owner, 1)
                    if await reenter():
                        return
                elif status == 0x85:
                    if (
                        not target_sent
                        or target_reply_cutoff is None
                        or received <= target_reply_cutoff
                    ):
                        # A previous adjustment's ACK cannot deliver this target.
                        with command_frames_not_counted():
                            await self.send(owner, self.profile.write, codec.anm3(0x85))
                            await self.pause(owner, 0.2)
                            await self.query(owner)
                        continue
                    self._acknowledged = True
                    await self.send(owner, self.profile.write, codec.anm3(0x85))
                    await self.pause(owner, 0.2)
                    await self.query(owner)
                    return
        finally:
            if self._anm3_events is events:
                self._anm3_events = None
