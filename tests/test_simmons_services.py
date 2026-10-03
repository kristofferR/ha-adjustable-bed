"""SIMMONS hold and alarm actions: profile preflight before any write."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import BED_TYPE_SIMMONS, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_simmons import make_controller


def target(profile=BED_TYPE_SIMMONS, variant=None):
    controller = make_controller(variant)
    controller.hold_control = AsyncMock()
    controller.configure_simmons_alarm = AsyncMock()
    controller.check_simmons_alarm = AsyncMock()
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "SIMMONS"
    coordinator.bed_type = profile
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


def _targets(coordinator):
    return patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    )


@pytest.mark.parametrize(
    ("profile", "variant", "control", "error"),
    [
        (BED_TYPE_SIMMONS, None, "memory", None),
        (BED_TYPE_SIMMONS, None, "inclined_left", "does not support held control"),
        (BED_TYPE_SIMMONS, "simmons_inclined", "zero_g", "does not support held control"),
    ],
)
async def test_hold_control_preflights_profile_and_layout(hass, profile, variant, control, error):
    await async_register_services(hass)
    coordinator, controller = target(profile, variant)
    call = {"device_id": "bed", "control": control, "duration": 5.5}
    with _targets(coordinator):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(DOMAIN, "hold_control", call, blocking=True)
            coordinator.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(DOMAIN, "hold_control", call, blocking=True)
            controller.hold_control.assert_awaited_once_with("memory", 5500)


async def test_set_alarm_passes_the_app_fields(hass):
    await async_register_services(hass)
    coordinator, controller = target()
    with _targets(coordinator):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {
                "device_id": "bed",
                "slot": "2",
                "enabled": True,
                "time": "07:30:00",
                "weekdays": ["monday", "sunday"],
                "mode": "custom_mode",
                "confirm_custom_mode": True,
            },
            blocking=True,
        )
    fields = {
        "slot": 2,
        "enabled": True,
        "mode": "custom_mode",
        "confirm_custom_mode": True,
        "hour": 7,
        "minute": 30,
        "weekdays": (0, 6),
    }
    controller.check_simmons_alarm.assert_awaited_once_with(**fields)
    controller.configure_simmons_alarm.assert_awaited_once_with(**fields)
    assert coordinator.async_execute_controller_command.await_args.kwargs["resource"] == (
        "configuration"
    )


@pytest.mark.parametrize(
    ("variant", "fields", "error"),
    [
        (None, {"mode": "custom_mode"}, "Custom Mode"),
        ("simmons_inclined", {"mode": "anti_snore"}, "Alarm mode"),
        (None, {}, "Alarm mode"),
    ],
)
async def test_set_alarm_rejects_unconfirmed_or_unavailable_modes(hass, variant, fields, error):
    await async_register_services(hass)
    coordinator, controller = target(variant=variant)
    with _targets(coordinator), pytest.raises(ServiceValidationError, match=error):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {"device_id": "bed", "slot": 1, "enabled": True, "time": "07:30:00", **fields},
            blocking=True,
        )
    controller.configure_simmons_alarm.assert_not_awaited()


async def test_set_alarm_requires_a_simmons_target(hass):
    await async_register_services(hass)
    coordinator, controller = target("okin_cb24")
    with _targets(coordinator), pytest.raises(ServiceValidationError, match="not a SIMMONS"):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {"device_id": "bed", "slot": 1, "enabled": False},
            blocking=True,
        )
    controller.configure_simmons_alarm.assert_not_awaited()


def test_entity_translations_cover_every_layout():
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    for filename in ("strings.json", "translations/en.json"):
        metadata = json.loads((root / filename).read_text())
        assert {"simmons_alarm_1", "simmons_alarm_2"} <= set(metadata["entity"]["sensor"])
        buttons = {
            spec.translation_key
            for variant in (None, "simmons_inclined")
            for spec in make_controller(variant).controller_button_specs
        }
        assert buttons <= set(metadata["entity"]["button"])


def _real_target(name: str, records):
    from custom_components.adjustable_bed.beds.simmons_protocol import AlarmSlot

    controller = make_controller(name="OKIN-1")
    controller._write_char = controller.client.services[0].characteristics[0]
    controller._clock_synced = True
    if records is not None:
        controller._slots = [AlarmSlot(*record) for record in records]
        controller._reported = list(controller._slots)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = name
    coordinator.bed_type = BED_TYPE_SIMMONS
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


FREE = [(6, 0, 0, 0, False), (9, 0, 132, 16, False)]


@pytest.mark.parametrize(
    ("second_records", "error"),
    [
        # The other enabled alarm already uses 07:30.
        ([(6, 0, 0, 0, False), (7, 30, 132, 16, True)], "same alarm timing"),
        # The bed never reports its records.
        (None, "did not report"),
    ],
)
async def test_multi_bed_alarm_validates_every_bed_before_any_write(hass, second_records, error):
    await async_register_services(hass)
    first, first_controller = _real_target("A", FREE)
    second, second_controller = _real_target("B", second_records)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        patch("custom_components.adjustable_bed.beds.simmons.ALARM_REPLY_TIMEOUT_S", 0),
        pytest.raises(ServiceValidationError, match=error),
    ):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {
                "device_id": ["a", "b"],
                "slot": 1,
                "enabled": True,
                "time": "07:30:00",
                "mode": "flat",
            },
            blocking=True,
        )
    assert first_controller.client.write_gatt_char.await_count == 0  # Bed A unchanged.
    sent = [call.args[1] for call in second_controller.client.write_gatt_char.call_args_list]
    assert sent == ([] if second_records else [bytes.fromhex("E1 80 03 9B")])  # Query only.


async def test_multi_bed_alarm_programs_every_bed_after_all_pass(hass):
    await async_register_services(hass)
    first, first_controller = _real_target("A", FREE)
    second, second_controller = _real_target("B", FREE)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {"device_id": ["a", "b"], "slot": 1, "enabled": False},
            blocking=True,
        )
    for controller in (first_controller, second_controller):
        assert controller.client.write_gatt_char.call_args_list[0].args[1][:3] == bytes.fromhex(
            "ED 80 03"
        )


async def test_cancelled_alarm_call_releases_every_preflighted_bed(hass):
    import asyncio

    await async_register_services(hass)
    coordinator, _controller = target()
    coordinator.async_execute_controller_command = AsyncMock(side_effect=asyncio.CancelledError)
    preflighted = [(coordinator, coordinator), (MagicMock(), MagicMock())]
    with (
        _targets(coordinator),
        patch(
            "custom_components.adjustable_bed.services._preflight_capability",
            new=AsyncMock(return_value=preflighted),
        ),
        patch(
            "custom_components.adjustable_bed.services._release_preflighted", new=AsyncMock()
        ) as release,
        pytest.raises(asyncio.CancelledError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {"device_id": "bed", "slot": 1, "enabled": False},
            blocking=True,
        )
    release.assert_awaited_once_with(preflighted)
