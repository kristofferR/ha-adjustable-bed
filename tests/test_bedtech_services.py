"""Public BedTech app routing, all-target validation and physical STOP ownership."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.bedtech.services import register_services
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH, SIDE_LEFT, SIDE_RIGHT
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from tests.test_bedtech_app import controller


def target(model):
    bed = controller(model)
    bed.write_command = AsyncMock()
    child = MagicMock(spec=AdjustableBedCoordinator)
    child.name = model
    child.bed_type = "bedtech"
    child.entry = SimpleNamespace(data={})
    child.controller_side = None
    child.capability_controller = bed
    child.stop_epoch = 0
    child.pairlink_peripheral = False

    async def execute(command, **kwargs):
        if kwargs.get("expected_stop_epoch", child.stop_epoch) == child.stop_epoch:
            await command(bed)

    child.async_execute_controller_command = AsyncMock(side_effect=execute)
    return child, bed


def pair(left, right):
    parent = MagicMock(spec=PairedBedCoordinator)
    children = {SIDE_LEFT: left, SIDE_RIGHT: right}
    parent.children = children
    parent.child_for_side.side_effect = children.get
    parent._targets_for.side_effect = lambda side: (
        list(children.items()) if side == SIDE_BOTH else [(side, children[side])]
    )
    parent._pair_cancel_generation.return_value = (0,)

    async def execute(command, *, side, **kwargs):
        for selected in children if side == SIDE_BOTH else [side]:
            await children[selected].async_execute_controller_command(command)

    parent.async_execute_controller_command = AsyncMock(side_effect=execute)
    return parent


async def call(hass, targets, action, sleeper=3):
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "bedtech_app_command",
            {"device_id": ["bed"], "action": action, "sleeper": sleeper},
            blocking=True,
        )


@pytest.mark.parametrize(
    "action,sleeper,expected",
    [
        ("headUp", 4, [0]),
        ("headUp", 5, [1]),
        ("footUp", 4, [0, 1]),
        ("footMassageUp", 5, [0, 1]),
        ("presetFlat", 3, [0, 1]),
    ],
)
async def test_two_receivers_apply_the_app_shared_foot_routing(hass, action, sleeper, expected):
    left, lbed = target("bt3000")
    right, rbed = target("bt3000")
    parent = pair(left, right)
    await call(hass, [(parent, SIDE_BOTH)], action, sleeper)
    assert [i for i, bed in enumerate((lbed, rbed)) if bed.write_command.await_count] == expected


async def test_shared_foot_stop_cancels_both_receivers(hass):
    left, _ = target("bt3000")
    right, _ = target("bt3000")
    parent = pair(left, right)
    await call(hass, [(parent, SIDE_BOTH)], "stop", 5)
    parent.async_stop_command.assert_awaited_once_with(side=SIDE_BOTH)
    parent.async_execute_controller_command.assert_not_awaited()


async def test_child_target_cannot_expand_to_other_receiver(hass):
    left, lbed = target("bt3000")
    right, rbed = target("bt3000")
    parent = pair(left, right)
    with pytest.raises(ServiceValidationError, match="conflicts"):
        await call(hass, [(parent, SIDE_LEFT)], "footUp", 4)
    lbed.write_command.assert_not_awaited()
    rbed.write_command.assert_not_awaited()


@pytest.mark.parametrize(
    "action,model", [("lightToggle", "bt2500"), ("presetTV", "bt3000"), ("headDown", "btx4fh")]
)
async def test_no_target_writes_if_any_model_or_routed_action_is_unsupported(hass, action, model):
    first, bed1 = target("bt3000fh")
    second, bed2 = target(model)
    with pytest.raises(ServiceValidationError):
        await call(hass, [(first, SIDE_BOTH), (second, SIDE_BOTH)], action)
    bed1.write_command.assert_not_awaited()
    bed2.write_command.assert_not_awaited()


async def test_standalone_fh_right_memory_keeps_bank_zero(hass):
    child, bed = target("bt3000fh")
    await call(hass, [(child, SIDE_BOTH)], "memory1Save", 5)
    assert bed.write_command.await_args.args[0].hex() == "6e01002b9a"


async def test_standalone_fh_right_head_and_light_use_bank_one(hass):
    child, bed = target("bt3000fh")
    await call(hass, [(child, SIDE_BOTH)], "headUp", 5)
    await call(hass, [(child, SIDE_BOTH)], "lightToggle", 5)
    assert [args.args[0].hex() for args in bed.write_command.await_args_list] == [
        "6e01012494",
        "6e01013cac",
    ]


async def test_later_target_stop_during_preflight_prevents_its_dispatch(hass):
    first, _ = target("bt3000")
    second, bed = target("bt3000")

    async def stop_later(command, **kwargs):
        second.stop_epoch += 1

    first.async_execute_controller_command.side_effect = stop_later
    await call(hass, [(first, SIDE_BOTH), (second, SIDE_BOTH)], "headUp", 1)
    bed.write_command.assert_not_awaited()


async def test_connection_test_cannot_move_first_head_from_a_right_request(hass):
    child, bed = target("bt3000fh")
    with pytest.raises(ServiceValidationError, match="first head"):
        await call(hass, [(child, SIDE_BOTH)], "connectionTest", 5)
    bed.write_command.assert_not_awaited()
