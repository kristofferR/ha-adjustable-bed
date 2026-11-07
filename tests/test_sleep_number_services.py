"""Sleep Number service routing and all-side validation."""

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import sleep_number_services as services


def controller(side=None):
    result = SimpleNamespace(
        sleep_number_command_names=("query",),
        validate_sleep_number_command=MagicMock(),
        async_execute_sleep_number_command=AsyncMock(return_value={"level": 42}),
        command_side=side,
        _coordinator=SimpleNamespace(address="AA:BB"),
    )
    result.side_scope = MagicMock(return_value=contextlib.nullcontext())
    return result


def call(hass, **data):
    return ServiceCall(
        hass,
        "adjustable_bed",
        "sleep_number_command",
        {"device_id": "bed", "command": "query", **data},
    )


async def test_execution_uses_scheduler_and_returns_bound_sides(hass):
    left, right = controller("left"), controller("right")
    target = SimpleNamespace(name="Bed")
    parent = SimpleNamespace()

    async def execute(coordinator, side, callback, **kwargs):
        assert coordinator is parent
        assert side == "both"
        assert kwargs["resource"] == "*"
        assert not kwargs["cancel_running"]
        await callback(left)
        await callback(right)

    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(parent, "both")], [])),
        patch.object(services, "_command_targets", return_value=[target, target]),
        patch.object(services, "_validation_controller", side_effect=[left, right]),
        patch.object(services, "_execute_sided", side_effect=execute) as scheduler,
    ):
        result = await services.handle_sleep_number_command(call(hass))
    assert result == {
        "command": "query",
        "results": {"left": {"level": 42}, "right": {"level": 42}},
    }
    scheduler.assert_awaited_once()
    left.async_execute_sleep_number_command.assert_awaited_once_with("query", {})


async def test_invalid_second_side_prevents_all_writes(hass):
    left, right = controller("left"), controller("right")
    right.validate_sleep_number_command.side_effect = ValueError("invalid side")
    target = SimpleNamespace(name="Bed")
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])),
        patch.object(services, "_command_targets", return_value=[target, target]),
        patch.object(services, "_validation_controller", side_effect=[left, right]),
        patch.object(services, "_execute_sided") as scheduler,
        patch.object(services, "_release_preflighted") as release,
        pytest.raises(ServiceValidationError, match="invalid side"),
    ):
        await services.handle_sleep_number_command(call(hass))
    scheduler.assert_not_awaited()
    left.async_execute_sleep_number_command.assert_not_awaited()
    release.assert_awaited_once()


async def test_unsupported_bed_is_rejected_before_execution(hass):
    unsupported = controller()
    unsupported.sleep_number_command_names = ()
    target = SimpleNamespace(name="Other bed")
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])),
        patch.object(services, "_command_targets", return_value=[target]),
        patch.object(services, "_validation_controller", return_value=unsupported),
        patch.object(services, "_execute_sided") as scheduler,
        pytest.raises(ServiceValidationError, match="not supported"),
    ):
        await services.handle_sleep_number_command(call(hass))
    scheduler.assert_not_awaited()


@pytest.mark.parametrize(
    "data",
    [
        {"device_id": ["a", "b"], "command": "query"},
        {"device_id": "a", "command": ""},
        {"device_id": "a", "command": "query", "parameters": [1]},
        {"device_id": "a", "command": "query", "side": "invalid"},
    ],
)
def test_schema_rejects_invalid_calls(data):
    with pytest.raises(vol.Invalid):
        services.SLEEP_NUMBER_COMMAND_SCHEMA(data)


async def test_registration_accepts_optional_response(hass):
    services.async_register_sleep_number_services(hass)
    assert (
        hass.services.supports_response("adjustable_bed", "sleep_number_command")
        == SupportsResponse.OPTIONAL
    )


async def test_motion_preempts_and_single_result_is_named(hass):
    live = controller()
    live.sleep_number_command_names = ("position",)
    target = SimpleNamespace(name="Bed", capability_controller=live)

    async def execute(callback, **kwargs):
        assert kwargs["cancel_running"] is True
        await callback(live)

    target.async_execute_controller_command = AsyncMock(side_effect=execute)
    with patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])):
        result = await services.handle_sleep_number_command(call(hass, command="position"))
    assert result["results"] == {"single": {"level": 42}}
    target.async_execute_controller_command.assert_awaited_once()


async def test_cancellation_releases_preflight_connections(hass):
    import asyncio

    live = controller()
    target = SimpleNamespace(name="Bed", capability_controller=live)
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])),
        patch.object(services, "_execute_sided", side_effect=asyncio.CancelledError),
        patch.object(services, "_release_preflighted") as release,
        pytest.raises(asyncio.CancelledError),
    ):
        await services.handle_sleep_number_command(call(hass))
    release.assert_awaited_once()


def test_json_response_preserves_nested_programs():
    value = {"programs": [{"enabled": True, "segments": [1, 2], "missing": None}]}
    assert services._json_value(value) == value


@pytest.mark.parametrize("value", [b"raw", float("nan"), {1: "invalid key"}])
def test_json_response_rejects_non_serializable_values(value):
    with pytest.raises(ValueError):
        services._json_value(value)


@pytest.mark.parametrize("selected_side", ["right", "both"])
async def test_two_address_pair_rejects_cross_side_parameters_before_writes(hass, selected_side):
    from custom_components.adjustable_bed.beds.sleep_number import SleepNumberController
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    children = {side: MagicMock(address=address, name=side) for side, address in (
        ("left", "AA:01"), ("right", "AA:02")
    )}
    controllers = {side: SleepNumberController(child) for side, child in children.items()}
    parent = MagicMock(spec=PairedBedCoordinator)
    parent.children = children
    parent.child_for_side.side_effect = children.get
    selected = ("left", "right") if selected_side == "both" else ("right",)
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(parent, selected_side)], [])),
        patch.object(services, "_validation_controller", side_effect=[controllers[s] for s in selected]),
        patch.object(services, "_execute_sided") as scheduler,
        pytest.raises(ServiceValidationError, match="physical bed side"),
    ):
        await services.handle_sleep_number_command(call(
            hass, command="get_sleep_number_controls", parameters={"side": "left"}
        ))
    scheduler.assert_not_awaited()


async def test_two_address_execution_revalidates_the_physical_side(hass):
    from custom_components.adjustable_bed.beds.sleep_number import SleepNumberController
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    child = MagicMock(address="AA:02", name="right")
    live = SleepNumberController(child)
    live.async_execute_sleep_number_command = AsyncMock(return_value={"level": 42})
    parent = MagicMock(spec=PairedBedCoordinator)
    parent.children = {"right": child}
    parent.child_for_side.return_value = child
    observed = []

    async def execute(coordinator, side, callback, **kwargs):
        await callback(live)

    async def record(command, parameters):
        observed.append(live.command_side)
        return {"level": 42}

    live.async_execute_sleep_number_command.side_effect = record
    with (
        patch.object(services, "_resolve_sided_targets", return_value=([(parent, "right")], [])),
        patch.object(services, "_validation_controller", return_value=live),
        patch.object(services, "_execute_sided", side_effect=execute),
    ):
        result = await services.handle_sleep_number_command(call(
            hass, command="get_sleep_number_controls", parameters={"side": "right"}
        ))
    assert observed == ["right"]
    assert result["results"] == {"right": {"level": 42}}
