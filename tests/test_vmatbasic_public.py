"""Factory, public controls and primary-only services exercise real delivery."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.vmatbasic_state import get_vmatbasic_session_intent
from tests.test_vmatbasic import make_controller, written


async def target(hass, profile="xtbox", address="AA:BB:CC:DD:EE:01"):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "App receiver",
            const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
            const.CONF_VMATBASIC_PROFILE: profile,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = make_controller(profile).client
    coordinator._controller = await create_controller(
        coordinator, const.BED_TYPE_VMATBASIC, "auto", coordinator.client
    )
    return coordinator


async def invoke(hass, targets, service, **data):
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        await hass.services.async_call(
            const.DOMAIN, service, {"device_id": "selected", **data}, blocking=True
        )


async def close(coordinator):
    coordinator._cancel_disconnect_timer()
    coordinator._cancel_diagnostic_polling()
    await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize("profile", ["basic", "cbi", "xtbox"])
async def test_registered_motor_hold_delivers_only_primary_literal_stream_and_release(
    hass, profile
):
    coordinator = await target(hass, profile)
    try:
        await invoke(
            hass,
            [(coordinator, const.SIDE_BOTH)],
            "hold_control",
            control="back_up",
            duration=0.1,
        )
        packets = written(coordinator.controller)
        assert 2 <= len(packets) <= 6
        assert all(
            packet == ("00001526" + "-9f03-0de5-96c5-b8f4f3081186", b"\x0b", True)
            for packet in packets[:-1]
        )
        assert packets[-1][1] == b"\xff"
    finally:
        await close(coordinator)


async def test_registered_xt_floor_hold_has_no_motor_stop(hass):
    coordinator = await target(hass)
    try:
        await invoke(
            hass,
            [(coordinator, const.SIDE_BOTH)],
            "hold_control",
            control="floor_hold",
            duration=0.1,
        )
        assert all(packet[1] == b"\x00\x11" for packet in written(coordinator.controller))
    finally:
        await close(coordinator)


@pytest.mark.parametrize(
    "name,packet", [("  New  ", b"New"), ("", b""), ("😀" * 5, "😀".encode() * 5)]
)
async def test_registered_rename_retains_only_successful_primary_name(hass, name, packet):
    coordinator = await target(hass)
    try:
        await invoke(hass, [(coordinator, const.SIDE_BOTH)], "rename", name=name)
        assert written(coordinator.controller)[0][1] == packet
        assert coordinator.entry.data[CONF_NAME] == packet.decode()
        assert coordinator.command_trace[-1]["payload"] == {
            "hex": "**REDACTED**",
            "length": len(packet),
        }
    finally:
        await close(coordinator)


async def test_failed_rename_does_not_change_retained_name(hass):
    coordinator = await target(hass)
    coordinator.client.write_gatt_char.side_effect = RuntimeError("failed")
    try:
        with pytest.raises(RuntimeError):
            await invoke(hass, [(coordinator, const.SIDE_BOTH)], "rename", name="New")
        assert coordinator.entry.data[CONF_NAME] == "App receiver"
    finally:
        await close(coordinator)


@pytest.mark.parametrize(
    "service,data",
    [
        ("hold_control", {"control": "floor_hold", "duration": 0.1}),
        ("rename", {"name": "New"}),
    ],
)
async def test_accessory_multi_target_rejection_precedes_any_write(hass, service, data):
    first = await target(hass)
    second = await target(hass, address="AA:BB:CC:DD:EE:02")
    try:
        with pytest.raises(ServiceValidationError):
            await invoke(
                hass, [(first, const.SIDE_BOTH), (second, const.SIDE_BOTH)], service, **data
            )
        assert written(first.controller) == written(second.controller) == []
    finally:
        await close(first)
        await close(second)


async def test_real_number_select_callbacks_and_reconstruction_preserve_color_dependency(hass):
    coordinator = await target(hass)
    try:
        selects = {
            entity._spec.key: entity
            for entity in _select_entities_for(hass, coordinator)
            if hasattr(entity, "_spec")
        }
        numbers = {
            entity._spec.key: entity
            for entity in _number_entities_for(hass, coordinator)
            if hasattr(entity, "_spec")
        }
        assert all(entity.current_option is None for entity in selects.values())
        assert all(entity.native_value is None for entity in numbers.values())
        await selects["vmatbasic_mood_palette"].async_select_option("col1")
        await numbers["vmatbasic_mood_brightness"].async_set_native_value(50)
        old_packet = written(coordinator.controller)[-1][1]
        coordinator._controller = await create_controller(
            coordinator, const.BED_TYPE_VMATBASIC, "auto", coordinator.client
        )
        await numbers["vmatbasic_mood_brightness"].async_set_native_value(50)
        assert written(coordinator.controller)[-1][1] == old_packet
        assert selects["vmatbasic_mood_palette"].current_option == "col1"
        await numbers["vmatbasic_floor_minutes"].async_set_native_value(255)
        assert written(coordinator.controller)[-1][1] == bytes.fromhex("001101ff")
        assert coordinator.entry.data[const.CONF_VMATBASIC_FLOOR_MINUTES] == 255
    finally:
        await close(coordinator)


async def test_mood_failed_delivery_preserves_constructed_color_but_not_published_state(hass):
    coordinator = await target(hass)
    try:
        coordinator.client.write_gatt_char.side_effect = RuntimeError("failed")
        with pytest.raises(RuntimeError):
            await coordinator.async_execute_controller_command(
                lambda ctrl: ctrl.set_mood_palette("col1")
            )
        assert "vmatbasic_mood_palette" not in coordinator.controller_state
        coordinator.client.write_gatt_char.side_effect = None
        coordinator._controller = await create_controller(
            coordinator, const.BED_TYPE_VMATBASIC, "auto", coordinator.client
        )
        await coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.set_mood_brightness(50)
        )
        assert written(coordinator.controller)[-1][1].hex() == "00770100526200"
    finally:
        await close(coordinator)


async def test_actual_shutdown_releases_admitted_motion_before_disconnect(hass):
    coordinator = await target(hass, "basic")
    entered = asyncio.Event()
    events = []
    client = coordinator.client

    async def write(char, packet, **kwargs):
        events.append(bytes(packet))
        if packet != b"\xff":
            entered.set()
            await asyncio.sleep(30)

    async def disconnect():
        events.append("disconnect")
        client.is_connected = False

    client.write_gatt_char.side_effect = write
    client.disconnect = AsyncMock(side_effect=disconnect)
    command = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.hold_control("back_up", 60000)
        )
    )
    try:
        await entered.wait()
        await coordinator.async_shutdown()
        await asyncio.gather(command, return_exceptions=True)
        assert events == [b"\x0b", b"\xff", "disconnect"]
        assert not coordinator._command_lock.locked()
    finally:
        if not command.done():
            command.cancel()
        await asyncio.gather(command, return_exceptions=True)
        await close(coordinator)


def test_process_intent_exact_address_profile_reset_and_independent_receivers(hass):
    first = get_vmatbasic_session_intent(hass, "aa:bb:cc:dd:ee:01", "xtbox")
    first.palette, first.brightness = "col1", 50
    assert get_vmatbasic_session_intent(hass, "AA:BB:CC:DD:EE:01", "xtbox") is first
    other = get_vmatbasic_session_intent(hass, "AA:BB:CC:DD:EE:02", "xtbox")
    assert (other.palette, other.brightness) == ("col20", 100)
    get_vmatbasic_session_intent(hass, "AA:BB:CC:DD:EE:01", "basic")
    reset = get_vmatbasic_session_intent(hass, "AA:BB:CC:DD:EE:01", "xtbox")
    assert reset is not first
    assert (reset.palette, reset.brightness) == ("col20", 100)


@pytest.mark.parametrize("profile", ["basic", "cbi", "xtbox"])
async def test_real_public_profile_entities_and_parser_state_have_no_extra_capabilities(
    hass, profile
):
    coordinator = await target(hass, profile)
    try:
        buttons = _button_entities_for(hass, coordinator)
        assert not any(
            "memory" in entity.unique_id or "preset_flat" in entity.unique_id for entity in buttons
        )
        covers = _cover_entities_for(hass, coordinator)
        assert {entity.entity_description.key for entity in covers} == {"back", "legs"}
        sensors = {
            entity._spec.key: entity
            for entity in _sensor_entities_for(hass, coordinator)
            if hasattr(entity, "_spec")
        }
        binaries = {
            entity._spec.key: entity
            for entity in _binary_sensor_entities_for(hass, coordinator)
            if hasattr(entity, "_spec")
        }
        assert all(entity.native_value is None for entity in sensors.values())
        assert binaries["vmatbasic_ed"].is_on is None
        await coordinator.async_execute_controller_query(
            lambda ctrl: ctrl.async_refresh_diagnostics()
        )
        assert sensors["vmatbasic_temperature"].native_value == 25.0
        assert sensors["vmatbasic_floor_minutes_observed"].native_value == 1439
        assert sensors["vmatbasic_model"].native_value == " model \0"
        assert binaries["vmatbasic_ed"].is_on is True
        coordinator.controller.invalidate_diagnostics()
        assert all(entity.native_value is None for entity in sensors.values())
        assert binaries["vmatbasic_ed"].is_on is None
    finally:
        await close(coordinator)


async def actual_descriptor_pair(hass):
    from custom_components.adjustable_bed import _build_paired_children
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    descriptors = [
        {
            CONF_ADDRESS: address,
            CONF_NAME: side,
            const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
            const.CONF_VMATBASIC_PROFILE: profile,
            const.CONF_VMATBASIC_FLOOR_LEVEL: level,
            const.CONF_VMATBASIC_FLOOR_MINUTES: minutes,
            const.CONF_SIDE: side,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        }
        for side, address, profile, level, minutes in [
            (const.SIDE_LEFT, "AA:BB:CC:DD:EE:01", "cbi", 201, 321),
            (const.SIDE_RIGHT, "AA:BB:CC:DD:EE:02", "xtbox", 6, 45),
        ]
    ]
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_PAIR_ID: "real-app-pair",
            CONF_NAME: "Both",
            const.CONF_PAIR_CHILDREN: descriptors,
        },
        options={
            const.CONF_VMATBASIC_PROFILE: "basic",
            const.CONF_VMATBASIC_FLOOR_LEVEL: 0,
            const.CONF_VMATBASIC_FLOOR_MINUTES: 0,
        },
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    parent = PairedBedCoordinator(hass, entry, children)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = parent
    for child in children.values():
        profile = child.entry.data[const.CONF_VMATBASIC_PROFILE]
        child._client = make_controller(profile).client
        child._controller = await create_controller(
            child, const.BED_TYPE_VMATBASIC, "auto", child.client
        )
    return parent, children[const.SIDE_LEFT], children[const.SIDE_RIGHT]


async def test_real_child_entry_preserves_physical_profile_settings_and_guarded_writes(hass):
    from custom_components.adjustable_bed.pairing import get_child

    parent, left, right = await actual_descriptor_pair(hass)
    before_right = dict(right.entry.data)
    try:
        assert left.entry.data[const.CONF_VMATBASIC_PROFILE] == "cbi"
        assert right.entry.data[const.CONF_VMATBASIC_PROFILE] == "xtbox"
        with patch.object(
            hass.config_entries, "async_update_entry", wraps=hass.config_entries.async_update_entry
        ) as update:
            await left.async_execute_controller_command(lambda ctrl: ctrl.set_floor_level(155))
            left.remember_vmatbasic_settings({"floor_level": 155})
        update.assert_called_once()
        saved = get_child(parent.entry.data, const.SIDE_LEFT)
        assert saved is not None
        assert saved[const.CONF_VMATBASIC_FLOOR_LEVEL] == 155
        assert saved[const.CONF_VMATBASIC_FLOOR_MINUTES] == 321
        assert dict(right.entry.data) == before_right
        assert written(right.controller) == []
        assert parent.consume_internal_entry_update(parent.entry)
        assert not parent.consume_internal_entry_update(parent.entry)
        assert not right.consume_internal_entry_update(parent.entry)
        await invoke(hass, [(parent, const.SIDE_LEFT)], "rename", name="Left named")
        assert get_child(parent.entry.data, const.SIDE_LEFT)[CONF_NAME] == "Left named"
        assert dict(right.entry.data) == before_right
    finally:
        await close(left)
        await close(right)


@pytest.mark.parametrize(
    "service,data",
    [
        ("hold_control", {"control": "floor_hold", "duration": 0.1}),
        ("rename", {"name": "Changed"}),
    ],
)
async def test_real_paired_accessory_both_rejects_before_either_write(hass, service, data):
    parent, left, right = await actual_descriptor_pair(hass)
    try:
        with pytest.raises(ServiceValidationError):
            await invoke(hass, [(parent, const.SIDE_BOTH)], service, **data)
        assert written(left.controller) == written(right.controller) == []
    finally:
        await close(left)
        await close(right)


@pytest.mark.parametrize(
    "service,data",
    [
        ("hold_control", {"control": "floor_hold", "duration": 0.1}),
        ("rename", {"name": "Changed"}),
    ],
)
async def test_failed_accessory_execution_releases_preflight_idle_ownership(hass, service, data):
    child = await target(hass)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._preflight_capability",
                new=AsyncMock(return_value=[(child, child)]),
            ),
            patch(
                "custom_components.adjustable_bed.services._execute_sided",
                new=AsyncMock(side_effect=RuntimeError("before admission")),
            ),
            patch.object(
                child, "async_ensure_connected", wraps=child.async_ensure_connected
            ) as ensure,
            pytest.raises(RuntimeError),
        ):
            await invoke(hass, [(child, const.SIDE_BOTH)], service, **data)
        assert ensure.call_args.kwargs["reset_timer"] is True
        assert child._disconnect_timer is not None
        assert written(child.controller) == []
    finally:
        await close(child)


@pytest.mark.parametrize("paired", [False, True])
async def test_real_diagnostics_download_preserves_each_profile_and_conditional_discovery(
    hass, paired
):
    from types import SimpleNamespace

    from custom_components.adjustable_bed.diagnostics import async_get_config_entry_diagnostics

    if paired:
        owner, left, right = await actual_descriptor_pair(hass)
        children = [left, right]
    else:
        owner = await target(hass, "xtbox")
        children = [owner]
        hass.data.setdefault(const.DOMAIN, {})[owner.entry.entry_id] = owner
    advertisement = SimpleNamespace(
        name="Unknown",
        manufacturer_data={0x03B0: bytes.fromhex("babe11110000")},
        service_uuids=[],
        rssi=-60,
        source="proxy",
        time=1.0,
    )
    try:
        with (
            patch(
                "custom_components.adjustable_bed.diagnostics.async_get_integration",
                new=AsyncMock(return_value=SimpleNamespace(version="4.0.2")),
            ),
            patch(
                "custom_components.adjustable_bed.diagnostics.find_service_info_by_address",
                return_value=(advertisement, True),
            ),
            patch(
                "custom_components.adjustable_bed.diagnostics.connection_reachability",
                return_value={},
            ),
        ):
            result = await async_get_config_entry_diagnostics(hass, owner.entry)
        records = (
            [side["advertisement"]["vmatbasic_discovery"] for side in result["sides"].values()]
            if paired
            else [result["advertisement"]["vmatbasic_discovery"]]
        )
        assert len(records) == len(children)
        for record in records:
            assert record["source_first_manufacturer_known"] is False
            assert record["source_filter_result"] is None
            assert record["profile_inference"] is False
            assert (
                record["conditional_records"][0]["matches_if_source_selected_this_record"] is True
            )
        if paired:
            assert result["sides"][const.SIDE_LEFT]["config"][const.CONF_VMATBASIC_PROFILE] == "cbi"
            assert (
                result["sides"][const.SIDE_RIGHT]["config"][const.CONF_VMATBASIC_PROFILE] == "xtbox"
            )
    finally:
        for child in children:
            await close(child)
