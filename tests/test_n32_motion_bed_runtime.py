"""N32 through HA setup, factory, entities, services and the real scheduler."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.beds.n32_motion_bed.controller import N32MotionBedController
from custom_components.adjustable_bed.beds.n32_motion_bed.state import ALARM_KEYS, AlarmRow
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _motor_count_options,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_N32_MOTION_BED,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROFILE_ID,
    DOMAIN,
    NORDIC_UART_SERVICE_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import (
    detect_bed_type_detailed,
    get_bed_type_options,
)
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profile_id import entry_profile_id
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.services import async_register_services
from tests.form_helpers import NEW_BED_ROUTES, form_fields, start_new_bed
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_detection import _make_service_info
from tests.test_n32_motion_bed import frame, make_bed, writes

ADDRESS = "AA:BB:CC:DD:EE:42"


def entry(hass, address=ADDRESS, **data):
    item = MockConfigEntry(
        domain=DOMAIN,
        title="N32",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "N32",
            CONF_BED_TYPE: BED_TYPE_N32_MOTION_BED,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_MOTOR_COUNT: 3,
            CONF_MOTOR_PULSE_COUNT: 3,
            CONF_MOTOR_PULSE_DELAY_MS: 200,
            **data,
        },
    )
    item.add_to_hass(hass)
    return item


@pytest.mark.parametrize("route", NEW_BED_ROUTES)
async def test_actual_setup_routes_hide_only_owned_fields(hass, route):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = _make_service_info(name="N32 MotionBed123", service_uuids=[])
    flow._async_transport_note = AsyncMock(return_value="")
    form = await start_new_bed(flow, route, BED_TYPE_N32_MOTION_BED)
    assert form["step_id"] == "finish_settings"
    fields = {marker.schema for marker in form_fields(form["data_schema"])}
    assert CONF_MOTOR_PULSE_COUNT in fields
    assert not {CONF_MOTOR_COUNT, CONF_HAS_MASSAGE, CONF_MOTOR_PULSE_DELAY_MS} & fields
    assert _motor_count_options(BED_TYPE_N32_MOTION_BED) == [3]


async def test_offline_factory_restore_and_profile_migration(hass):
    item = entry(hass)
    await async_migrate_entry(hass, item)
    assert item.data[CONF_PROFILE_ID] == BED_TYPE_N32_MOTION_BED
    coord = _FactoryCoordinator()
    coord.entry = item
    c = await create_controller(coord, entry_profile_id(item.data), "auto", None)
    assert isinstance(c, N32MotionBedController)
    assert {s.key for s in c.motor_control_specs} == {"back", "legs", "head"}
    assert {s.key for s in c.controller_state_sensor_specs} == {f"n32_alarm_{s}" for s in (1, 2, 3)}
    options = [o for o in get_bed_type_options() if o["value"] == BED_TYPE_N32_MOTION_BED]
    assert len(options) == 1 and "N32 Motion Bed" in options[0]["label"]


async def test_factory_optional_identity_never_selects_a_route_or_control_address():
    coord = _FactoryCoordinator()
    c = await create_controller(
        coord,
        BED_TYPE_N32_MOTION_BED,
        "auto",
        None,
        manufacturer_data={89: bytes.fromhex("1011223344556677")},
    )
    assert c._manufacturer_identity == "665544332211"
    assert c._coordinator.address == coord.address
    assert c.profile.key == BED_TYPE_N32_MOTION_BED


@pytest.mark.parametrize("name", ["N32 MotionBed123", "n32 motionbed123", "SmArTbEd123"])
def test_name_candidates_require_explicit_app_without_a_service_filter(name):
    info = _make_service_info(name=name, service_uuids=[])
    result = detect_bed_type_detailed(info)
    assert BED_TYPE_N32_MOTION_BED in {result.bed_type, *(result.ambiguous_types or ())}
    assert result.confidence < 0.7


def test_confident_receiver_and_shared_uart_do_not_propose_unrelated_app():
    info = _make_service_info(name="Smartbed428000193", service_uuids=[NORDIC_UART_SERVICE_UUID])
    info.manufacturer_data = {89: bytes.fromhex("4142010204")}
    result = detect_bed_type_detailed(info)
    assert result.bed_type == "malouf_new_okin"
    assert BED_TYPE_N32_MOTION_BED not in (result.ambiguous_types or ())
    assert recommend_profile({CONF_BED_TYPE: "malouf_new_okin"}, info, {}) is None
    bare = _make_service_info(name="Unrelated UART", service_uuids=[NORDIC_UART_SERVICE_UUID])
    result = detect_bed_type_detailed(bare)
    assert BED_TYPE_N32_MOTION_BED not in {result.bed_type, *(result.ambiguous_types or ())}


@pytest.fixture
async def runtime(hass):
    coordinator = AdjustableBedCoordinator(hass, entry(hass))
    _, _, client = make_bed()
    coordinator._client = client
    controller = await create_controller(coordinator, BED_TYPE_N32_MOTION_BED, "auto", client)
    coordinator._controller = controller
    await controller.async_discover_capabilities()
    await controller.start_notify()
    hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    await async_register_services(hass)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        yield hass, coordinator, client
    await coordinator.async_shutdown()


async def test_native_cover_keeps_pulse_count_and_card_metadata(runtime):
    hass, coordinator, client = runtime
    c = coordinator.controller
    spec = next(s for s in c.motor_control_specs if s.key == "head")
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
    assert writes(client) == [frame("cervical_up")] * 3 + [frame("stop")]
    attrs = cover.extra_state_attributes
    assert attrs["held_control_up"] == "cervical_up"
    assert attrs["held_stop_scope"] == "side"
    assert attrs["hold_lease_mode"] == "stream"


async def test_real_card_lease_renews_one_stream_and_stale_generation_cannot_restart(runtime):
    hass, coord, client = runtime
    call = {
        "device_id": ["bed"],
        "motor": "back",
        "direction": "up",
        "duration_ms": 300,
        "hold_owner": "n32-card",
        "hold_generation": 7,
    }
    with virtual_clock():
        first = asyncio.create_task(
            hass.services.async_call(DOMAIN, "timed_move", call, blocking=True)
        )
        await asyncio.sleep(0.2)
        before = len(writes(client))
        await hass.services.async_call(DOMAIN, "timed_move", call, blocking=True)
        assert len(writes(client)) == before
        await asyncio.sleep(0.2)
        await coord.async_stop_command()
        await first
        count = len(writes(client))
        with pytest.raises(ServiceValidationError, match="has ended"):
            await hass.services.async_call(DOMAIN, "timed_move", call, blocking=True)
        assert len(writes(client)) == count
    motion = writes(client)
    assert motion[0] == frame("head_up")
    stop_index = motion.index(frame("stop"))
    assert all(f == frame("stop") for f in motion[stop_index:])


async def test_finite_timed_service_bounds_slow_writer_and_releases(runtime):
    hass, _, client = runtime
    held_at = []
    with virtual_clock() as clock:

        async def slow(_ch, data, **_kw):
            if data != frame("stop"):
                held_at.append(clock.elapsed)
            await asyncio.sleep(0.15)

        client.write_gatt_char.side_effect = slow
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                "device_id": ["bed"],
                "motor": "legs",
                "direction": "down",
                "duration_ms": 450,
            },
            blocking=True,
        )
    assert held_at and all(t < 0.45 for t in held_at)
    assert writes(client)[-1] == frame("stop")


async def test_alarm_service_uses_actual_row_fields_without_optimistic_sensor(runtime):
    hass, coord, client = runtime
    await hass.services.async_call(
        DOMAIN,
        "n32_motion_bed_alarm",
        {
            "device_id": ["bed"],
            "slot": 2,
            "operation": "set",
            "time": "06:30:00",
            "weekdays": ["monday"],
            "mode": "m1",
        },
        blocking=True,
    )
    assert writes(client) == [bytes.fromhex("07068205061e00010100"), bytes.fromhex("00d0")]
    assert ALARM_KEYS[2].time not in coord.controller_state
    assert coord.controller_state[ALARM_KEYS[2].record] == AlarmRow(6, 30, 130, 5, 1)
    replacement = N32MotionBedController(coord)
    assert replacement._rows[2] == AlarmRow(6, 30, 130, 5, 1) and not replacement._seen


@pytest.mark.parametrize(
    "fields",
    [
        {"operation": "set", "time": "06:30:00", "mode": "m1"},
        {"operation": "set", "time": "06:30:01", "mode": "m1", "weekdays": []},
        {"operation": "disable", "time": "06:30:00"},
        {"operation": "delete", "weekdays": []},
    ],
)
async def test_incomplete_or_wrong_operation_fields_write_nothing(runtime, fields):
    hass, _, client = runtime
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "n32_motion_bed_alarm",
            {
                "device_id": ["bed"],
                "slot": 1,
                **fields,
            },
            blocking=True,
        )
    assert not writes(client)


async def test_all_target_capabilities_checked_before_first_alarm_write(runtime):
    hass, coordinator, client = runtime
    invalid = MagicMock(spec=AdjustableBedCoordinator)
    invalid.name, invalid.capability_controller = "Other", MagicMock()
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both"), (invalid, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="does not support"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "n32_motion_bed_alarm",
            {
                "device_id": ["bed", "other"],
                "slot": 1,
                "operation": "delete",
            },
            blocking=True,
        )
    assert not writes(client)


async def test_two_address_pair_dispatches_only_the_selected_physical_side(runtime):
    hass, left, left_client = runtime
    right = AdjustableBedCoordinator(hass, entry(hass, address="AA:BB:CC:DD:EE:43"))
    _, _, right_client = make_bed()
    right._client = right_client
    right._controller = await create_controller(
        right, BED_TYPE_N32_MOTION_BED, "auto", right_client
    )
    await right.controller.async_discover_capabilities()
    await right.controller.start_notify()
    pair_entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "n32-two-address"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, pair_entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    try:
        with (
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "_async_refresh_controller_auth", AsyncMock()),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(pair, "right")], []),
            ),
            virtual_clock(),
        ):
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {
                    "device_id": ["pair"],
                    "control": "cervical_down",
                    "duration": 0.45,
                },
                blocking=True,
            )
            await hass.services.async_call(
                DOMAIN,
                "n32_motion_bed_alarm",
                {
                    "device_id": ["pair"],
                    "slot": 3,
                    "operation": "delete",
                },
                blocking=True,
            )
        assert writes(left_client) == []
        assert writes(right_client)[:4] == [frame("cervical_down")] * 3 + [frame("stop")]
        assert writes(right_client)[4:] == [
            bytes.fromhex("07070000000000000100"),
            bytes.fromhex("00e0"),
        ]
    finally:
        await right.async_shutdown()


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_real_connection_owns_notify_queries_clock_and_reconnect(
    hass, mock_bleak_client, monkeypatch
):
    from custom_components.adjustable_bed.beds.n32_motion_bed import controller as module

    monkeypatch.setattr(module, "CLOCK_DELAY_S", 0)
    _, _, roles = make_bed()
    service = MagicMock(uuid=NORDIC_UART_SERVICE_UUID, handle=0, description="N32 UART")
    service.characteristics = [
        MagicMock(uuid=ch.uuid, properties=ch.properties, handle=ch.handle, descriptors=[])
        for ch in roles.services[0].characteristics
    ]
    mock_bleak_client.services.__iter__ = lambda _: iter([service])
    mock_bleak_client.services.__len__ = lambda _: 1
    coord = AdjustableBedCoordinator(hass, entry(hass))
    assert await coord.async_connect()
    assert isinstance(coord.controller, N32MotionBedController)
    first = writes(mock_bleak_client)
    assert first[:3] == [bytes.fromhex(h) for h in ("00c0", "00d0", "00e0")]
    assert first[3].startswith(bytes.fromhex("0704"))
    assert mock_bleak_client.start_notify.await_count == 1
    await coord.async_disconnect()
    assert await coord.async_connect()
    assert writes(mock_bleak_client)[len(first) :][:3] == first[:3]
    await coord.async_shutdown()
