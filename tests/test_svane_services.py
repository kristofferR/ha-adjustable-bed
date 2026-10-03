"""Real Svane public endpoints, mixed profiles and writer-owned partial release."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_PAIR_ID,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_paired_coordinator import RecordingChild
from tests.test_svane import make_controller, written


def target(profile="multi", bed_type=BED_TYPE_SVANE):
    controller = make_controller(profile)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Svane"
    coordinator.bed_type = bed_type
    coordinator.entry = SimpleNamespace(data={})
    coordinator.controller = coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_real_hold_endpoint_frames_and_cleanup(hass, profile):
    await async_register_services(hass)
    coordinator, controller = target(profile)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "head_up_feet_down", "duration": 0.13},
            blocking=True,
        )
    assert (
        [b for _, _, b in written(controller)]
        == (
            ["0100", "0100", "0000", "0000"]
            if profile == "multi"
            else ["102100000000", "102100000000", "100000000000"]
        )
        or profile == "multi"
        and {b for _, _, b in written(controller)} == {"0100", "0000"}
    )
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]


@pytest.mark.parametrize("failure", ["wrong_profile", "missing_role", "readonly_role"])
async def test_later_target_rejected_before_first_motion(hass, failure):
    await async_register_services(hass)
    first, one = target()
    second, two = target()
    if failure == "wrong_profile":
        second.bed_type = "jensen"
    elif failure == "missing_role":
        two.client.services[0].characteristics = []
    else:
        two.client.services[0].characteristics[0].properties = ["read"]
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": ["one", "two"], "control": "head_up", "duration": 0.1},
            blocking=True,
        )
    one.client.write_gatt_char.assert_not_awaited()
    two.client.write_gatt_char.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH])
async def test_mixed_profile_native_pair_routes_each_physical_target(hass, side):
    await async_register_services(hass)
    log = []

    class SvaneChild(RecordingChild):
        def __init__(self, child_side, profile):
            super().__init__(child_side, log)
            self.bed_type = BED_TYPE_SVANE
            self.entry = SimpleNamespace(data={})
            self.controller = make_controller(profile)
            self.capability_controller = self.controller

        async def async_execute_controller_command(
            self,
            command_fn,
            cancel_running=True,
            skip_disconnect=False,
            resource=None,
            resources=None,
        ):
            await command_fn(self.controller)

    children = {
        SIDE_LEFT: SvaneChild(SIDE_LEFT, "multi"),
        SIDE_RIGHT: SvaneChild(SIDE_RIGHT, "jmc"),
    }
    pair = PairedBedCoordinator(hass, SimpleNamespace(data={CONF_PAIR_ID: "svane-pair"}), children)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(pair, side)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "pair", "side": side, "control": "head_up", "duration": 0.1},
            blocking=True,
        )
    assert bool(written(children[SIDE_LEFT].controller)) is (side in (SIDE_LEFT, SIDE_BOTH))
    assert bool(written(children[SIDE_RIGHT].controller)) is (side in (SIDE_RIGHT, SIDE_BOTH))
    if side in (SIDE_LEFT, SIDE_BOTH):
        assert written(children[SIDE_LEFT].controller)[0][2] == "0100"
    if side in (SIDE_RIGHT, SIDE_BOTH):
        assert written(children[SIDE_RIGHT].controller)[0][2] == "100100000000"


async def test_axis_release_endpoint_signals_active_real_writer_no_independent_ble_lane(hass):
    await async_register_services(hass)
    coordinator, controller = target("jmc")
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        held = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": "bed", "control": "head_up_feet_down", "duration": 0.6},
                blocking=True,
            )
        )
        while not controller.client.write_gatt_char.await_count:
            await asyncio.sleep(0.001)
        await hass.services.async_call(
            DOMAIN, "svane_release_axis", {"device_id": "bed", "motor": "head"}, blocking=True
        )
        await asyncio.sleep(0.25)
        intermediate = [b for _, _, b in written(controller)]
        assert "102000000000" in intermediate and "100000000000" not in intermediate
        await hass.services.async_call(
            DOMAIN, "svane_release_axis", {"device_id": "bed", "motor": "feet"}, blocking=True
        )
        await held
    assert [b for _, _, b in written(controller)].count("100000000000") == 1
    assert coordinator.async_execute_controller_command.await_count == 1


async def test_release_selection_preflight_no_partial_intent_mutation(hass):
    await async_register_services(hass)
    first, controller = target()
    second, _ = target(bed_type="jensen")
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "svane_release_axis",
            {"device_id": ["one", "two"], "motor": "head"},
            blocking=True,
        )
    assert not controller._pending_release


@pytest.mark.parametrize("slot", [1, 2])
async def test_goto_preset_later_unsaved_multi_slot_prevents_earlier_jmc_write(hass, slot):
    await async_register_services(hass)
    first, jmc = target("jmc")
    second, multi = target("multi")
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="save this local slot"),
    ):
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": ["one", "two"], "preset": slot}, blocking=True
        )
    jmc.client.write_gatt_char.assert_not_awaited()
    multi.client.write_gatt_char.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


async def test_goto_preset_mixed_saved_memories_preserves_each_profile_packet(hass):
    await async_register_services(hass)
    first, jmc = target("jmc")
    second, multi = target("multi")
    jmc.session.jmc_slots = (bytes.fromhex("00112233"), bytes.fromhex("44556677"))
    multi.session.multi_slots[1] = (b"head", b"feet")
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        patch.object(jmc, "_wait", AsyncMock(return_value=True)),
        patch.object(multi, "_wait", AsyncMock(return_value=True)),
    ):
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": ["one", "two"], "preset": 1}, blocking=True
        )
    assert [packet for _, _, packet in written(jmc)] == ["100400112233"]
    assert [packet for _, _, packet in written(multi)] == [b"head".hex(), b"feet".hex()]


@pytest.mark.parametrize("saved", [(b"", b"feet"), (b"head", b"")])
async def test_goto_preset_later_empty_axis_rejects_every_target(hass, saved):
    await async_register_services(hass)
    first, jmc = target("jmc")
    second, multi = target("multi")
    multi.session.multi_slots[1] = saved
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="nonempty raw axes"),
    ):
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": ["one", "two"], "preset": 1}, blocking=True
        )
    jmc.client.write_gatt_char.assert_not_awaited()
    multi.client.write_gatt_char.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()
