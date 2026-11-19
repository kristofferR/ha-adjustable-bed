"""Real HA setup, entity, service, STOP-admission and native paired-device calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, STATE_UNAVAILABLE, Platform
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.okimiki import controller as bed
from custom_components.adjustable_bed.beds.okimiki import services as app_services
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.entity_sweep import async_sweep_after_setup
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.services import _resolve_sided_targets as REAL_RESOLVE
from custom_components.adjustable_bed.services import async_register_services
from tests.test_okimiki import virtual as virtual
from tests.test_richmat_family_flow import setup_flow

CARD_METADATA = Path(__file__).parent / "fixtures/okimiki/card_metadata.json"


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Okimiki",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:69",
            CONF_NAME: "Okimiki",
            const.CONF_BED_TYPE: "okimiki",
            const.CONF_PROTOCOL_VARIANT: "KWRN",
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    route = bed.codec.TRANSPORTS["w1"]
    tx = SimpleNamespace(uuid=route.write_uuid, handle=169, properties=["write"], descriptors=[])
    rx = SimpleNamespace(uuid=route.notify_uuid, handle=170, properties=["notify"], descriptors=[])
    mock_bleak_client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])
    ]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, "both")], []),
    ) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


def notify(target, packet):
    ctrl = target.controller
    ctrl._notification(ctrl._link, ctrl._link.rx, bytearray.fromhex(packet))


async def invoke(hass, operation, **fields):
    await hass.services.async_call(
        const.DOMAIN,
        "okimiki",
        {"device_id": "bed", "operation": operation, **fields},
        blocking=True,
    )


async def test_registered_runtime_entities_alarm_light_and_timed_callers(hass, runtime, virtual):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.OkimikiController)
    assert not _light_entities_for(hass, target)
    notify(target, "6e0e00037f")
    assert _light_entities_for(hass, target)
    notify(target, "6e09010078")
    notify(target, "6e200d0501020100071e5989ab")
    client.write_gatt_char.reset_mock()
    await invoke(hass, "enable", alarm_id=1, enabled=False)
    assert written(client) == ["6e0d200501010100071e5988a9"]
    client.write_gatt_char.reset_mock()
    await invoke(hass, "light_color", rgb_color=[1, 2, 3])
    assert written(client) == ["6e0cff017a6e0d020380"]
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {"device_id": "bed", "motor": "both", "direction": "up", "duration_ms": 250},
        blocking=True,
    )
    assert written(client) == ["6e01002998", "6e01002998", "6e01006edd"]
    button = next(
        entity
        for entity in _button_entities_for(hass, target)
        if entity.unique_id.endswith("program_memory_1")
    )
    # The card offers a memory save only in Set mode; it needs no second prompt.
    assert "requires_confirmation" not in button.extra_state_attributes
    client.write_gatt_char.reset_mock()
    await button.async_press()
    assert written(client) == ["6e01002b9a"]
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    await cover.async_open_cover()
    assert written(client)[0] == "6e01002493" and written(client)[-1] == "6e01006edd"


@pytest.mark.parametrize(
    ("operation", "fields"),
    (("press", {"control": "head_up", "duration_ms": 250}), ("light_off", {})),
)
async def test_registered_stop_during_lazy_import_fences_first_write(
    hass, runtime, virtual, operation, fields
):
    target, client, _ = runtime
    assert await target.async_connect()
    original = app_services.async_import_modules

    async def importing(*args, **kwargs):
        await target.async_stop_command()
        await original(*args, **kwargs)

    client.write_gatt_char.reset_mock()
    with patch.object(app_services, "async_import_modules", importing):
        await invoke(hass, operation, **fields)
    assert written(client) == ["6e01006edd"]  # The explicit STOP itself is allowed.


@pytest.mark.parametrize("operation", ("light_off", "sync"))
async def test_all_target_preflight_rejects_before_first_settings_write(
    hass, runtime, virtual, operation
):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    assert await target.async_connect()
    notify(target, "6e0e00037f")
    if operation == "sync":
        await target.async_disconnect("idle_timeout")
    other, ctrl = fake_target(family=bed.OkimikiController)
    ctrl.product_key = "IPRM"
    ctrl._address = "AA:BB:CC:DD:EE:70"
    other.address = ctrl._address
    ctrl._coordinator = other
    ctrl._link = None
    ctrl._menus_changed = asyncio.Event()
    ctrl.validate_request = MagicMock()
    ctrl._alarms = []
    ctrl.menu_available = lambda _: False
    ctrl.model = bed.PRODUCTS["IPRM"]
    resolve.return_value = ([(target, "both"), (other, "both")], [])
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await invoke(hass, operation)
    assert not written(client)


@pytest.mark.parametrize("deferred_reply", (False, True))
@pytest.mark.parametrize(
    ("operation", "fields", "expected"),
    (
        ("light_off", {}, "6e010075e4"),
        ("light_color", {"rgb_color": [1, 2, 3]}, "6e0cff017a6e0d020380"),
        ("light_duration", {"seconds": 300}, "6e0b012ca6"),
        ("alarms", {}, "6e0820050100009c"),
        (
            "repeat",
            {"alarm_id": 1, "datetime": "2026-11-18T07:30:00+00:00", "mode": "lounge"},
            bed.p.Alarm(1, 0, 7, 30, 0x59, 1).frame().hex(),
        ),
        (
            "repeat",
            {"alarm_id": 1, "datetime": "2026-11-18T07:30:00+00:00", "mode": "lounge",
             "weekdays": ["monday", "sunday"]},
            bed.p.Alarm(1, 0, 7, 30, 0x59, bed.p.repeat_mask((0, 6), True)).frame().hex(),
        ),
    ),
)
async def test_settings_service_reconnects_before_session_validation(
    hass, runtime, virtual, operation, fields, expected, deferred_reply
):
    target, client, _ = runtime
    await hass.config.async_set_time_zone("UTC")
    assert await target.async_connect()
    notify(target, "6e0e00037f")
    notify(target, "6e09010078")
    await target.async_disconnect("idle_timeout")
    assert not target.capability_controller.menu_available("light")
    assert not target.capability_controller.menu_available("alarm")
    client.write_gatt_char.reset_mock()

    async def reply(*args, **kwargs):
        # Replies belong to the new subscription, never the retained controller.
        callback = client.start_notify.call_args.args[1]

        async def deliver():
            if deferred_reply:
                await asyncio.sleep(0.01)
            callback(None, bytearray.fromhex("6e0e00037f"))
            callback(None, bytearray.fromhex("6e09010078"))

        if deferred_reply:
            if args[1] == bed.codec.function(1, action="deviceFunctionItemCheckLight"):
                # The final startup write completes before either reply arrives.
                asyncio.create_task(deliver())
        else:
            await deliver()

    client.write_gatt_char.side_effect = reply
    await invoke(hass, operation, **fields)
    assert target.is_connected
    assert written(client)[-1] == expected


async def test_skipped_target_validation_prevents_all_settings_writes(hass, runtime, virtual):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    assert await target.async_connect()
    notify(target, "6e0e00037f")
    other, ctrl = fake_target(family=bed.OkimikiController)
    other.address = "AA:BB:CC:DD:EE:70"
    ctrl._alarms = []
    # A scheduler can return without calling the operation after STOP admission.
    other.async_execute_controller_command = AsyncMock()
    resolve.return_value = ([(target, "both"), (other, "both")], [])
    client.write_gatt_char.reset_mock()
    await invoke(hass, "light_off")
    assert not written(client)


async def test_renewable_hold_stop_release_and_reconnect_cleanup(hass, runtime, virtual):
    target, client, _ = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN,
        "hold_control",
        {
            "device_id": "bed",
            "control": "okimiki_head_up",
            "duration": 0.25,
            "hold_owner": "card",
            "hold_generation": 1,
        },
        blocking=True,
    )
    assert written(client)[0] == "6e01002493" and written(client)[-1] == "6e01006edd"
    notify(target, "6e0e00037f")
    await invoke(hass, "light_duration", seconds=300)
    assert target.controller.persisted_app_state["seconds"] == 300
    old = target.controller
    old_link = old._link
    await target.async_disconnect("idle_timeout")
    client.write_gatt_char.reset_mock()
    assert await target.async_connect()
    old._notification(old_link, old_link.rx, bytearray.fromhex("6e0e00037f"))
    assert not target.controller.supports_lights
    assert "6e0b012ca6" not in written(client)


async def test_card_metadata_matches_actual_native_entities(hass, runtime):
    """The frontend consumer fixture comes from real Python entity metadata."""
    target, _client, _resolve = runtime
    ctrl = target.capability_controller
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    release = next(
        entity for entity in _button_entities_for(hass, target)
        if entity.unique_id == target.entity_unique_id("okimiki_release")
    )
    rows = []
    for entity, entity_id in ((cover, "cover.okimiki_back"), (release, "button.okimiki_release")):
        attributes = (entity.capability_attributes or {}) | (entity.extra_state_attributes or {})
        rows.append({
            "entity_id": entity_id,
            "translation_key": entity.translation_key,
            "attributes": {
                key: value for key, value in attributes.items()
                if key.startswith(("card_", "hold_", "held_"))
            },
        })
    assert rows == json.loads(CARD_METADATA.read_text())
    assert all(
        spec.hold.release_button_key == release.translation_key
        for spec in ctrl.motor_control_specs
    )
    assert ctrl.execution.hold_for(None) is None


@pytest.mark.parametrize("disable_duration", (False, True))
async def test_discovered_light_registry_survives_idle_and_profile_changes(
    hass, runtime, enable_custom_integrations, disable_duration
):
    """Real platform discovery/sweep preserves customizations, never session permission."""
    from tests.test_wire_snapshot import _load_tool

    target, client, _resolve = runtime
    tool = _load_tool()
    clock = tool.FakeClock()

    async def ble(action):
        # Only protocol waits use virtual time. HA platform polling, registry
        # updates and teardown keep their real event-loop clock and handles.
        with tool.virtual_time(clock):
            return await action

    entry = target.entry
    entry.mock_state(hass, ConfigEntryState.LOADED)
    # The fixture already constructed the runtime and registered the domain's
    # services. Forward real platforms without bootstrapping the domain again
    # while this loaded entry's forward holds its setup lock.
    hass.config.components.add(const.DOMAIN)
    platforms = [Platform.LIGHT, Platform.NUMBER]
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    owned_platforms = list(entity_platform.async_get_platforms(hass, const.DOMAIN))
    async_sweep_after_setup(hass, entry, platforms)
    assert await ble(target.async_connect())
    notify(target, "6e0e00037f")
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    light_id = registry.async_get_entity_id(
        "light", const.DOMAIN, target.entity_unique_id("under_bed_lights")
    )
    number_id = registry.async_get_entity_id(
        "number", const.DOMAIN, target.entity_unique_id("controller_number_okimiki_light_seconds")
    )
    assert light_id and number_id
    light = registry.async_update_entity(
        light_id, new_entity_id="light.okimiki_custom", name="My reading light", icon="mdi:book"
    )
    number = registry.async_update_entity(
        number_id, name="My light duration",
        disabled_by=er.RegistryEntryDisabler.USER if disable_duration else None,
    )
    await hass.async_block_till_done()
    await ble(invoke(hass, "light_duration", seconds=300))
    old = target.controller
    old_link = old._link
    assert await ble(target.async_disconnect("idle_timeout"))
    await hass.async_block_till_done()

    def assert_retained_unknown():
        current_light = registry.async_get(light.entity_id)
        current_number = registry.async_get(number.entity_id)
        assert current_light is not None and current_number is not None
        assert (current_light.id, current_light.unique_id, current_light.name, current_light.icon) == (
            light.id, light.unique_id, "My reading light", "mdi:book"
        )
        assert (current_number.id, current_number.unique_id, current_number.name,
                current_number.disabled_by) == (
            number.id, number.unique_id, "My light duration", number.disabled_by
        )
        assert hass.states.get(light.entity_id).state == STATE_UNAVAILABLE
        if not disable_duration:
            assert hass.states.get(number.entity_id).state == STATE_UNAVAILABLE
        assert target.controller_state[bed.DURATION] is None
        assert not target.capability_controller.supports_lights

    assert_retained_unknown()
    client.write_gatt_char.reset_mock()
    assert await ble(target.async_connect())
    await hass.async_block_till_done()
    old._notification(old_link, old_link.rx, bytearray.fromhex("6e0e00037f"))
    assert_retained_unknown()
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await ble(invoke(hass, "light_off"))
    assert not written(client)
    notify(target, "6e0e00037f")
    await hass.async_block_till_done()
    assert registry.async_get(light.entity_id).id == light.id
    assert registry.async_get(number.entity_id).id == number.id
    assert hass.states.get(light.entity_id).state != STATE_UNAVAILABLE
    if not disable_duration:
        assert float(hass.states.get(number.entity_id).state) == 300

    # A different profile is a fresh discovery, not permission inherited from KWRN.
    assert await hass.config_entries.async_unload_platforms(entry, platforms)
    await target.async_shutdown()
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, const.CONF_PROTOCOL_VARIANT: "IPRM"}
    )
    replacement = AdjustableBedCoordinator(hass, entry)
    hass.data[const.DOMAIN][entry.entry_id] = replacement
    try:
        await replacement.async_prime_offline_controller()
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
        async_sweep_after_setup(hass, entry, platforms)
        await hass.async_block_till_done()
        assert not replacement.capability_controller.retained_entity_keys
        assert registry.async_get(light.entity_id) is None
        assert registry.async_get(number.entity_id) is None
    finally:
        await hass.config_entries.async_unload_platforms(entry, platforms)
        await replacement.async_shutdown()
        # HA's async_reset returns before stopping polling when disabling the
        # last entity left the old platform empty. Clean only our owned handles.
        for platform in owned_platforms:
            platform.async_unsub_polling()


@pytest.mark.parametrize(
    ("connection_mode", "operation", "target_side"),
    (
        ("concurrent", "press", "right"),
        ("sequential", "press", "right"),
        ("concurrent", "light_off", "right"),
        ("sequential", "light_off", "right"),
        ("sequential", "light_off", "both"),
        ("sequential", "enable", "right"),
    ),
)
async def test_native_paired_child_target_keeps_physical_bed_and_side_owned_product(
    hass, runtime, virtual, connection_mode, operation, target_side
):
    from custom_components.adjustable_bed import (
        _async_ensure_paired_device_registry,
        _build_paired_children,
    )
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import side_identifier
    from custom_components.adjustable_bed.profile_id import with_profile_ids
    from tests.test_paired_setup import _paired_entry_data

    target, client, resolve = runtime
    data = _paired_entry_data()
    data[const.CONF_BED_TYPE] = "okimiki"
    data[const.CONF_CONNECTION_MODE] = const.CONNECTION_MODE_IDLE
    for child, code in zip(data[const.CONF_PAIR_CHILDREN], ("IPRM", "KWRN"), strict=True):
        child.update(
            {
                const.CONF_BED_TYPE: "okimiki",
                const.CONF_PROTOCOL_VARIANT: code,
                const.CONF_HAS_MASSAGE: False,
            }
        )
        child.pop("capabilities", None)
    entry = MockConfigEntry(domain=const.DOMAIN, title="Okimiki pair", data=with_profile_ids(data))
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(
        hass, entry, _build_paired_children(hass, entry), connection_mode=connection_mode
    )
    hass.data[const.DOMAIN][entry.entry_id] = pair
    for child in pair.children.values():
        await child.async_prime_offline_controller()
        child._max_retries = 1
    _async_ensure_paired_device_registry(hass, entry, pair)
    registry = dr.async_get(hass)
    parent = registry.async_get_device_by_identifier(
        next(iter(pair.device_info["identifiers"])), entry.entry_id
    )
    right = registry.async_get_child_device_by_identifier(
        side_identifier(pair, "right"), entry.entry_id
    )
    assert isinstance(right, dr.ChildDeviceEntry) and right.parent_device_id == parent.id
    assert pair.children["left"].capability_controller.product_key == "IPRM"
    assert pair.children["right"].capability_controller.product_key == "KWRN"
    left = pair.children["left"]
    if target_side == "right":
        left.async_connect = AsyncMock(side_effect=AssertionError("Left must stay disconnected"))
    if operation != "press":
        async def reply(*args, **kwargs):
            callback = client.start_notify.call_args.args[1]
            callback(None, bytearray.fromhex("6e0e00037f"))
            callback(None, bytearray.fromhex("6e09010078"))
            if operation == "enable":
                callback(None, bytearray.fromhex("6e200d0501020100071e5989ab"))

        client.write_gatt_char.side_effect = reply
    # Use real registry targeting, rather than patching a child's side into a test call.
    resolve.side_effect = None
    resolve.side_effect = REAL_RESOLVE
    try:
        fields = (
            {"control": "head_up", "duration_ms": 250}
            if operation == "press"
            else {"alarm_id": 1, "enabled": False} if operation == "enable" else {}
        )
        await hass.services.async_call(
            const.DOMAIN,
            "okimiki",
            {"device_id": right.id if target_side == "right" else parent.id,
             "operation": operation, **fields},
            blocking=True,
        )
        if target_side == "right":
            left.async_connect.assert_not_awaited()
        if operation == "press":
            assert "6e01002493" in written(client)
            assert written(client)[-1] == "6e01006edd"
        elif operation == "light_off":
            assert written(client).count("6e010075e4") == (2 if target_side == "both" else 1)
        else:
            assert written(client)[-1] == "6e0d200501010100071e5988a9"
        assert all(packet[4:6] == "00" for packet in written(client) if packet.startswith("6e01"))
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "okimiki",
                {"device_id": right.id, "side": "left", "operation": "press", "control": "head_up"},
                blocking=True,
            )
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("code", bed.PRODUCTS)
async def test_new_install_and_configure_retain_exact_product(hass, code):
    from tests.form_helpers import finish_new_bed
    from tests.test_richmat_family_flow import configure, entry_for

    flow = setup_flow(hass)
    flow._discovery_info = None
    flow._manual_data[const.CONF_PROTOCOL_VARIANT] = code
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "okimiki"})
        if result.get("step_id") == "profile_questions":
            result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: code})
        result = await finish_new_bed(flow, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == code
    assert result["data"][const.CONF_MOTOR_COUNT] == 2
    entry = entry_for(
        hass,
        **{
            const.CONF_BED_TYPE: "okimiki",
            const.CONF_PROTOCOL_VARIANT: code,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_HAS_MASSAGE: True,
        },
    )
    result = await configure(hass, entry, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == code
    assert entry.data[const.CONF_MOTOR_COUNT] == 2
    assert entry.data[const.CONF_HAS_MASSAGE] is False
