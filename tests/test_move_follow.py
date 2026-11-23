"""Following a move the bed finishes on its own (#628)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.bedjet_powerlayer import BedJetPowerLayerController
from custom_components.adjustable_bed.beds.limoss.controller import LimossController
from custom_components.adjustable_bed.beds.serta_mp_remote import SertaMPRemoteController
from custom_components.adjustable_bed.beds.sleepstar import SleepStarController
from custom_components.adjustable_bed.beds.sleepys.box25 import (
    Box25Commands,
    SleepysBox25Controller,
)
from custom_components.adjustable_bed.codec import limoss as limoss_codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SLEEPYS_BOX25_VARIANT_STAR,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_keeson_layout_app import ready
from tests.test_starcode_m5x5 import make_controller as m5x5_controller

BASE = "custom_components.adjustable_bed.beds.base"
QUIET = 0.2
REPLY = 0.05


@pytest.fixture(autouse=True)
def _fast_follow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{BASE}._FOLLOW_STEP_SECONDS", 0.01)
    monkeypatch.setattr(f"{BASE}._FOLLOW_QUIET_SECONDS", QUIET)
    monkeypatch.setattr(f"{BASE}._FOLLOW_REPLY_SECONDS", REPLY)
    monkeypatch.setattr(f"{BASE}._FOLLOW_BOUND_SECONDS", 5.0)


def _status(head: int, foot: int = 0) -> bytearray:
    """A BOX25 status report: head at byte 4, foot at byte 6."""
    frame = bytearray(20)
    frame[0:2] = b"\xa5\x0d"
    frame[4] = head
    frame[6] = foot
    return frame


async def _box25(
    hass: HomeAssistant, *, angle_sensing: bool = True, connection_mode: str = "idle"
) -> tuple[AdjustableBedCoordinator, SleepysBox25Controller, Callable[[int], None]]:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:25",
            CONF_NAME: "Bed",
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: not angle_sensing,
            CONF_PROTOCOL_VARIANT: SLEEPYS_BOX25_VARIANT_STAR,
            CONF_CONNECTION_MODE: connection_mode,
        },
        unique_id="AA:BB:CC:DD:EE:25",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, SleepysBox25Controller)
    controller._notify_callback = coordinator._handle_position_update

    def report(head: int) -> None:
        controller._on_notification(MagicMock(uuid="rx"), _status(head))

    report(0)
    return coordinator, controller, report


def _queries(client: MagicMock) -> int:
    return sum(
        call.args[1] == Box25Commands.QUERY_STATUS for call in client.write_gatt_char.call_args_list
    )


@pytest.mark.usefixtures("mock_coordinator_connected")
class TestFollow:
    async def test_listens_until_reports_stop_then_asks_once(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        """Reports keep it listening past the first quiet window; only a quiet bed is asked."""
        coordinator, controller, report = await _box25(hass)
        head = 0

        async def write(_char: object, data: bytes, **_kwargs: object) -> None:
            if data == Box25Commands.QUERY_STATUS:
                report(head)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)
        loop = asyncio.get_running_loop()
        started = loop.time()

        follow = asyncio.create_task(controller.follow_autonomous_move())
        while loop.time() < started + 2 * QUIET:
            head += 1
            report(head)
            await asyncio.sleep(QUIET / 10)
            assert not follow.done()
            assert _queries(mock_bleak_client) == 0
        await follow

        assert coordinator.position_data["head"] == float(head)
        assert _queries(mock_bleak_client) == 1

    async def test_a_reply_that_moved_keeps_following(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        """A bed that reports only when asked is asked until two answers agree."""
        coordinator, controller, report = await _box25(hass)
        answers = iter((30, 55, 55))

        async def write(_char: object, data: bytes, **_kwargs: object) -> None:
            if data == Box25Commands.QUERY_STATUS:
                report(next(answers))

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)

        await controller.follow_autonomous_move()

        assert coordinator.position_data["head"] == 55.0
        assert _queries(mock_bleak_client) == 3

    async def test_a_lost_reply_is_asked_for_again(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        """One dropped reply must not end the move while the bed still travels."""
        coordinator, controller, report = await _box25(hass)
        answers = iter((None, 40, 40))

        async def write(_char: object, data: bytes, **_kwargs: object) -> None:
            if data == Box25Commands.QUERY_STATUS and (head := next(answers)) is not None:
                report(head)

        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)

        await controller.follow_autonomous_move()

        assert coordinator.position_data["head"] == 40.0
        assert _queries(mock_bleak_client) == 3

    async def test_a_bed_that_never_answers_is_asked_twice(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        _coordinator, controller, _report = await _box25(hass)
        mock_bleak_client.write_gatt_char.reset_mock()

        async with asyncio.timeout(2):
            await controller.follow_autonomous_move()

        assert _queries(mock_bleak_client) == 2

    async def test_the_link_is_handed_back_only_after_the_move(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Release mode hands the link back after a command; a followed move is still one."""
        monkeypatch.setattr(
            "custom_components.adjustable_bed.coordinator_connection._COMMAND_BURST_GRACE_SECONDS",
            QUIET / 10,
        )
        coordinator, _controller, report = await _box25(hass, connection_mode="release")
        mock_bleak_client.disconnect.reset_mock()
        command = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda bed: bed.follow_autonomous_move()
            )
        )
        for head in range(1, 15):
            await asyncio.sleep(QUIET / 10)
            report(head)
            mock_bleak_client.disconnect.assert_not_called()
            assert not command.done()

        async with asyncio.timeout(5):
            await command
            while not mock_bleak_client.disconnect.called:
                await asyncio.sleep(QUIET / 10)

        assert coordinator.position_data["head"] == 14.0

    async def test_stop_is_not_held_back_by_a_stalled_read(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        _coordinator, controller, _report = await _box25(hass)
        stalled = asyncio.Event()

        async def never_returns(_motor_count: int = 2) -> None:
            stalled.set()
            await asyncio.Event().wait()

        with patch.object(controller, "read_positions", never_returns):
            follow = asyncio.create_task(controller.follow_autonomous_move())
            await stalled.wait()
            controller._coordinator.cancel_command.set()
            async with asyncio.timeout(2):
                await follow

    async def test_a_queued_command_is_not_held_back_by_a_stalled_read(
        self, hass: HomeAssistant
    ) -> None:
        coordinator, controller, _report = await _box25(hass)
        stalled = asyncio.Event()

        async def never_returns(_motor_count: int = 2) -> None:
            stalled.set()
            await asyncio.Event().wait()

        with patch.object(controller, "read_positions", never_returns):
            follow = asyncio.create_task(controller.follow_autonomous_move())
            await stalled.wait()
            with patch.object(
                type(coordinator.command_scheduler), "has_pending", property(lambda _self: True)
            ):
                async with asyncio.timeout(2):
                    await follow

    async def test_stop_ends_it_and_sends_stop(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        coordinator, _controller, report = await _box25(hass)
        mock_bleak_client.write_gatt_char.reset_mock()
        command = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda bed: bed.follow_autonomous_move()
            )
        )
        await asyncio.sleep(QUIET / 10)
        report(20)

        async with asyncio.timeout(2):
            await coordinator.async_stop_command()
            await command

        written = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
        assert Box25Commands.MOTOR_STOP in written
        assert (
            Box25Commands.QUERY_STATUS
            not in written[: written.index(Box25Commands.MOTOR_STOP)]
        )

    async def test_a_queued_command_ends_it(self, hass: HomeAssistant) -> None:
        coordinator, controller, _report = await _box25(hass)

        with (
            patch.object(
                type(coordinator.command_scheduler), "has_pending", property(lambda _self: True)
            ),
            patch.object(controller, "read_positions", AsyncMock()) as read,
        ):
            async with asyncio.timeout(2):
                await controller.follow_autonomous_move()

        read.assert_not_awaited()

    async def test_a_lost_link_ends_it(self, hass: HomeAssistant) -> None:
        _coordinator, controller, _report = await _box25(hass)

        with (
            patch.object(AdjustableBedCoordinator, "is_connected", property(lambda _self: False)),
            patch.object(controller, "read_positions", AsyncMock()) as read,
        ):
            async with asyncio.timeout(2):
                await controller.follow_autonomous_move()

        read.assert_not_awaited()

    async def test_a_bed_that_never_settles_is_left_at_the_bound(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The bound only ends the reading; no frame is invented to stop the bed."""
        _coordinator, controller, report = await _box25(hass)
        monkeypatch.setattr(f"{BASE}._FOLLOW_BOUND_SECONDS", 0.2)
        mock_bleak_client.write_gatt_char.reset_mock()

        async def keep_moving() -> None:
            for head in range(1, 100):
                report(head)
                await asyncio.sleep(0.01)

        mover = asyncio.create_task(keep_moving())
        async with asyncio.timeout(2):
            await controller.follow_autonomous_move()
        mover.cancel()

        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_reading_switched_off_skips_it(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        _coordinator, controller, _report = await _box25(hass, angle_sensing=False)
        mock_bleak_client.write_gatt_char.reset_mock()

        async with asyncio.timeout(QUIET / 2):
            await controller.follow_autonomous_move()

        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_box25_preset_and_target_follow_after_their_frames(
        self, hass: HomeAssistant, mock_bleak_client: MagicMock
    ) -> None:
        _coordinator, controller, _report = await _box25(hass)
        order: list[str] = []
        mock_bleak_client.write_gatt_char = AsyncMock(
            side_effect=lambda *_a, **_k: order.append("frame")
        )
        with (
            patch.object(
                controller,
                "follow_autonomous_move",
                AsyncMock(side_effect=lambda: order.append("follow")),
            ),
            patch("custom_components.adjustable_bed.beds.sleepys.box25.asyncio.sleep", AsyncMock()),
            patch("custom_components.adjustable_bed.beds.gatt_write.asyncio.sleep", AsyncMock()),
        ):
            await controller.preset_zero_g()
            assert order[-2:] == ["frame", "follow"] and order.count("follow") == 1
            await controller.set_motor_position("head", 40)
            assert order[-2:] == ["frame", "follow"] and order.count("follow") == 2
            await controller.move_head_up()
            assert order.count("follow") == 2


def _mock_controller[T: BedController](cls: Callable[[Any], T]) -> tuple[T, AsyncMock]:
    coordinator = MagicMock()
    coordinator.client.is_connected = True
    coordinator.cancel_command = asyncio.Event()
    controller = cls(coordinator)
    follow = AsyncMock()
    controller.follow_autonomous_move = follow  # type: ignore[method-assign]
    return controller, follow


async def test_sleepstar_recall_and_target_follow() -> None:
    controller, follow = _mock_controller(SleepStarController)
    with (
        patch.object(controller, "write_command", AsyncMock()),
        patch("custom_components.adjustable_bed.beds.sleepstar._SENDER_CADENCE_SECONDS", 0),
    ):
        await controller.preset_flat()
        await controller.preset_memory(1)
        await controller.set_motor_position("head", 40)
        assert follow.await_count == 3
        await controller.move_head_up()
        await controller.program_memory(1)

    assert follow.await_count == 3


async def test_limoss_recall_follows_and_a_held_move_does_not() -> None:
    controller, follow = _mock_controller(LimossController)
    controller._memory_positions = {1: {"back": 1200}}
    controller._memory_slot_count = 1
    with (
        patch.object(controller, "write_command", AsyncMock()) as write,
        patch.object(controller, "validate_memory_recall"),
        patch("custom_components.adjustable_bed.beds.limoss.controller.asyncio.sleep", AsyncMock()),
    ):
        await controller.preset_memory(1)
        assert write.await_args_list[-1].args == (
            limoss_codec.set_position(1, 1200, signed=False),
        )
        assert follow.await_count == 1
        await controller.preset_flat()

    assert follow.await_count == 1


def test_limoss_compares_raw_positions() -> None:
    """A raw value past the largest seen so far keeps the same estimated angle."""
    controller, _follow = _mock_controller(LimossController)
    controller._last_positions_raw = {"back": 1200}
    before = controller._move_feedback()

    controller._last_positions_raw["back"] = 1300

    assert controller._move_feedback() != before


async def test_bedjet_latched_keys_follow() -> None:
    controller, follow = _mock_controller(BedJetPowerLayerController)
    with patch.object(controller, "write_command", AsyncMock()):
        await controller.preset_zero_g()
        await controller.preset_memory(1)
        assert follow.await_count == 2
        await controller.move_back_up()

    assert follow.await_count == 2


async def test_serta_mp_remote_target_and_recall_follow() -> None:
    controller, follow = _mock_controller(SertaMPRemoteController)
    with patch.object(controller, "write_command", AsyncMock()):
        await controller.set_motor_position("back", 10)
        await controller.preset_memory(1)
    for handle in controller._setters:
        handle.cancel()

    assert follow.await_count == 2


async def test_starcode_m5x5_recalls_follow(hass: HomeAssistant) -> None:
    controller = m5x5_controller(hass)
    follow = AsyncMock()
    controller.follow_autonomous_move = follow  # type: ignore[method-assign]
    with (
        patch.object(controller, "write_command", AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.starcode.accessory_group."
            "interrupt_conflicting_group",
            AsyncMock(),
        ),
    ):
        await controller.app_action("flat")
        await controller.app_action("memory_1")
        assert follow.await_count == 2
        await controller.app_action("head_up")

    assert follow.await_count == 2


@pytest.mark.parametrize(
    ("key", "follows"),
    [("flat", True), ("zero_g", True), ("light", False), ("level", False), ("head_up", False)],
)
async def test_qplus_follows_only_one_frame_presets(key: str, follows: bool) -> None:
    """Massage and light keys are sent once too, but move nothing."""
    controller, _coordinator = await ready("qplus_app", "H")
    controller.follow_autonomous_move = AsyncMock()  # type: ignore[method-assign]
    controller.hold_control = AsyncMock()  # type: ignore[method-assign]

    await controller._run_action(key)

    assert controller.follow_autonomous_move.await_count == int(follows)
