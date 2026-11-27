"""JunaSleep native HA callers, setup, cancellation and physical ownership."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson import junasleep as bed
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import junasleep as app
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_junasleep_vectors import VECTORS


class Char:
    def __init__(self, uuid, properties, handle):
        self.uuid, self.properties, self.handle = uuid, properties, handle
        self.descriptors = []


ADDRESS = "AA:BB:CC:DD:18:10"


def gatt():
    def service(uuid, chars):
        return SimpleNamespace(
            uuid=uuid,
            characteristics=chars,
            get_characteristic=lambda key: next((c for c in chars if c.uuid == key), None),
        )

    a, b = bed.codec.TRANSPORTS["ksbt"], bed.codec.TRANSPORTS["base"]
    return [
        service(
            a.service_uuid,
            [Char(a.write_uuid, ["write-without-response"], 1), Char(a.notify_uuid, ["notify"], 2)],
        ),
        service(b.service_uuid, [Char(b.write_uuid, ["write"], 3)]),
        service(bed.KEESON_BASE_NOTIFY_SERVICE_UUID, [Char(b.notify_uuid, ["notify"], 4)]),
    ]


def entry(hass, remote, address=ADDRESS):
    from custom_components.adjustable_bed.setup_questions import _junasleep_settings

    data = {
        CONF_ADDRESS: address,
        CONF_NAME: "JunaSleep",
        const.CONF_BED_TYPE: "junasleep",
        const.CONF_PROTOCOL_VARIANT: remote,
        const.CONF_BLE_DEVICE_NAME: "KSBT02C000000000" if remote == "a" else "base000000000000",
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        **_junasleep_settings({const.CONF_PROTOCOL_VARIANT: remote}),
    }
    e = MockConfigEntry(domain=const.DOMAIN, title="JunaSleep", unique_id=address, data=data)
    e.add_to_hass(hass)
    return e


def written(client):
    return [bytes(call.args[1]).hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("remote", "ab")
@pytest.mark.parametrize("on", (True, False))
@pytest.mark.parametrize("report", (True, False))
async def test_native_desired_light_hydrates_before_periodic_poll(
    hass, mock_coordinator_connected, mock_bleak_client,
    mock_async_ble_device_from_address, enable_custom_integrations, remote, on, report,
):
    client = mock_bleak_client
    client.services = gatt()
    e = entry(hass, remote)
    mock_async_ble_device_from_address.return_value.name = e.data[const.CONF_BLE_DEVICE_NAME]
    assert await hass.config_entries.async_setup(e.entry_id)
    target = hass.data[const.DOMAIN][e.entry_id]
    ctrl = target.controller
    target._cancel_diagnostic_polling()
    char, receive = client.start_notify.call_args.args
    raw = bytearray(16 if remote == "a" else 20)
    raw[12 if remote == "a" else 14] = (0 if on else 1) << (0 if remote == "a" else 6)
    toggle = "040200020000" if remote == "a" else "e5fe160000020004"

    async def answer(_char, payload, **_kwargs):
        if bytes(payload).hex() == toggle:
            raw[12 if remote == "a" else 14] = int(on) << (0 if remote == "a" else 6)
        if report and bytes(payload) == app.QUERY[remote]:
            receive(char, raw)

    client.write_gatt_char.side_effect = answer
    client.write_gatt_char.reset_mock()
    entity = er.async_get(hass).async_get_entity_id(
        "light", const.DOMAIN, f"{ADDRESS}_under_bed_lights"
    )
    assert entity is not None
    started = asyncio.get_running_loop().time()
    deadline = ctrl._next_query
    assert 0 < deadline - started <= app.QUERY_PERIOD_S
    try:
        with virtual_clock() as clock:
            clock.now = started
            call = hass.services.async_call(
                "light", "turn_on" if on else "turn_off", {"entity_id": entity}, blocking=True
            )
            if report:
                await call
            else:
                with raises_key("light_state_unknown"):
                    await call
        query = app.QUERY[remote].hex()
        expected = [query]
        if report:
            expected += [toggle] + ([query] * 3 if remote == "a" else [])
        assert written(client) == expected
        assert ctrl._next_query == deadline
    finally:
        await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("remote", "ab")
async def test_native_entities_every_outgoing_vector(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
    remote,
):
    client = mock_bleak_client
    client.services = gatt()
    e = entry(hass, remote)
    # Exercise the maintenance action after a user has enabled its diagnostic entity.
    er.async_get(hass).async_get_or_create(
        "button", const.DOMAIN, f"{ADDRESS}_junasleep_query", config_entry=e
    )
    mock_async_ble_device_from_address.return_value.name = e.data[const.CONF_BLE_DEVICE_NAME]
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    target = hass.data[const.DOMAIN][e.entry_id]
    c = target.controller
    assert isinstance(c, bed.JunaSleepController)
    registry = er.async_get(hass)
    device = next(
        v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
    )
    assert not c.supports_memory_programming
    assert not c.supports_single_address_pairing
    assert c.execution.declared == {"hold"}
    assert c.profile.release.steps == ()
    assert len(c.motor_control_specs) == (2 if remote == "a" else 4)
    with virtual_clock():
        for row in (
            r for r in VECTORS["commands"] if r["protocol"] == ("P1" if remote == "a" else "P2")
        ):
            client.write_gatt_char.reset_mock()
            action = row["action"]
            if row["kind"] == "held":
                control = {
                    "foot_up": "feet_up",
                    "foot_down": "feet_down",
                    "neck_in": "tilt_up",
                    "neck_out": "tilt_down",
                    "lumbar_in": "lumbar_up",
                    "lumbar_out": "lumbar_down",
                }.get(action, action)
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": device, "control": control, "duration": 0.1},
                    blocking=True,
                )
            else:
                if action == "light_button":
                    entity = registry.async_get_entity_id(
                        "light", const.DOMAIN, f"{ADDRESS}_under_bed_lights"
                    )
                    assert entity is not None
                    await hass.services.async_call(
                        "light", "toggle", {"entity_id": entity}, blocking=True
                    )
                    assert written(client), row["id"]
                    assert written(client)[0] == bytes.fromhex(row["expected_bytes"]).hex()
                    continue
                key = {
                    "flat": "preset_flat",
                    "zero_g": "preset_zero_g",
                    "position_I": "preset_memory_1",
                    "position_II": "preset_memory_2",
                    "light_button": "toggle_light",
                    "status_query": "junasleep_query",
                }.get(action, f"junasleep_{action}")
                entity = registry.async_get_entity_id("button", const.DOMAIN, f"{ADDRESS}_{key}")
                assert entity is not None, (action, key)
                await hass.services.async_call(
                    "button", "press", {"entity_id": entity}, blocking=True
                )
            assert written(client), row["id"]
            assert written(client)[0] == bytes.fromhex(row["expected_bytes"]).hex(), row["id"]
            allowed = {bytes.fromhex(row["expected_bytes"]).hex(), app.QUERY[remote].hex()}
            assert set(written(client)) <= allowed
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("remote", "ab")
async def test_manual_setup_and_side_ownership(hass, remote):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.pairing import effective_child_data
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["junasleep"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: remote})
    result = await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == len(app.AXES[remote])
    assert saved[const.CONF_HAS_MASSAGE]
    assert resolve_profile_id(saved) == f"junasleep:{remote}"
    assert per_side_profile("junasleep", remote).variant_owned
    pair = {
        const.CONF_BED_TYPE: "junasleep",
        const.CONF_PAIR_CHILDREN: [
            {**entry(hass, "a").data, const.CONF_SIDE: "left"},
            {**entry(hass, "b", ADDRESS[:-1] + "1").data, const.CONF_SIDE: "right"},
        ],
    }
    assert (
        effective_child_data(pair, "left", {const.CONF_PROTOCOL_VARIANT: "b"})[
            const.CONF_PROTOCOL_VARIANT
        ]
        == "a"
    )


async def test_session_notification_quirks_stale_cancel_and_replacement(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    client.services = gatt()
    target = AdjustableBedCoordinator(hass, entry(hass, "a"))
    assert await target.async_connect()
    c = target.controller
    char, notify = client.start_notify.call_args.args
    raw = bytearray(16)
    raw[3] = 1
    raw[4] = 2
    raw[12] = 1
    notify(char, raw)
    assert target.controller_state[bed.SECONDS] == 0x12
    assert target.controller_state[bed.INDICATOR] == 10
    raw[12] = 3
    raw[3] = 255
    raw[4] = 255
    notify(char, raw)
    assert target.controller_state[bed.INDICATOR] == 10
    assert target.controller_state[bed.UNDER_BED_LIGHTS_ON] is True
    with virtual_clock():
        client.write_gatt_char.reset_mock()

        async def cancel(*args, **kwargs):
            target.cancel_command.set()

        client.write_gatt_char.side_effect = cancel
        await target.async_execute_controller_command(
            lambda ctrl: ctrl.hold_control("head_up", 1000)
        )
        assert written(client) == ["040200000001"]
        client.write_gatt_char.side_effect = None
        c.on_disconnect()
        notify(char, raw)
        assert target.controller_state[bed.INDICATOR] is None
        await c.async_discover_capabilities()
        target.cancel_command.clear()
        client.write_gatt_char.reset_mock()

        async def replace(*args, **kwargs):
            target._address = "AA:BB:CC:DD:18:11"

        client.write_gatt_char.side_effect = replace
        with pytest.raises(ConnectionError):
            await c.hold_control("head_up", 1000)
        assert len(written(client)) == 1
        notify(char, raw)
        assert target.controller_state[bed.INDICATOR] is None
    await target.async_shutdown()


@pytest.mark.parametrize("remote", "ab")
async def test_renewable_card_hold_outlives_pulse_batch_and_stops_without_frame(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, remote
):
    client = mock_bleak_client
    client.services = gatt()
    e = entry(hass, remote)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = hass.data[const.DOMAIN][e.entry_id]
    target._motor_pulse_count = 1
    registry = er.async_get(hass)
    device = next(
        v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
    )

    async def renew():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": device,
                "motor": "head",
                "direction": "up",
                "duration_ms": 200,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )

    client.write_gatt_char.reset_mock()
    with virtual_clock():
        active = asyncio.create_task(renew())
        for _ in range(8):
            await asyncio.sleep(0.1)
            await renew()
            assert not active.done()
        await target.async_stop_command()
        await active
        count = len(written(client))
        await asyncio.sleep(0.5)
        assert len(written(client)) == count
    assert len(written(client)) >= 2
    assert set(written(client)) == {"040200000001" if remote == "a" else "e5fe160100000005"}
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_name_routed_notifications_and_non_gating_failure(
    hass, mock_coordinator_connected, mock_bleak_client
):
    from bleak.exc import BleakError

    client = mock_bleak_client
    client.services = gatt()
    target = AdjustableBedCoordinator(hass, entry(hass, "b"))
    assert await target.async_connect()
    c = target.controller
    # Name and remote are independent, including a deliberate mismatched name.
    target._ble_device_name = "base000000000000"
    await c.async_discover_capabilities()
    client.start_notify.side_effect = BleakError("CCCD refused")
    await c.start_notify()
    client.write_gatt_char.reset_mock()
    await c.preset_flat()
    assert written(client) == ["e5fe1600000008fe"]
    client.start_notify.side_effect = None
    await c.start_notify()
    char, notify = client.start_notify.call_args.args
    assert char.uuid == bed.codec.TRANSPORTS["base"].notify_uuid
    raw = bytearray(20)
    raw[9:13] = bytes.fromhex("ffffffff")
    raw[14] = 0x40
    notify(char, raw)
    assert target.controller_state[bed.UNDER_BED_LIGHTS_ON] is True
    assert target.controller_state[bed.INDICATOR] is None
    target._ble_device_name = "KSBT02C000000000"
    await c.stop_notify()
    await c.async_discover_capabilities()
    await c.start_notify()
    assert client.start_notify.call_args.args[0].uuid == bed.codec.TRANSPORTS["ksbt"].notify_uuid
    # An old controller cannot clear its replacement's report.
    target._controller = MagicMock()
    target.handle_controller_state_updates(bed.INDICATOR(20))
    c.on_disconnect()
    assert target.controller_state[bed.INDICATOR] == 20
    target._controller = c
    await target.async_shutdown()


@pytest.mark.parametrize("side", [const.SIDE_RIGHT, const.SIDE_BOTH])
async def test_paired_hold_preflights_both_remotes_before_writing(hass, monkeypatch, side):
    from functools import partial

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import services
    from tests.test_controller_contract import _FactoryCoordinator
    from tests.test_paired_coordinator import _pair

    pair, left, right = _pair([])
    controls = []
    for child, remote in ((left, "a"), (right, "b")):
        c = bed.JunaSleepController(_FactoryCoordinator(), remote=remote)
        controls.append(c)
        c.hold_control = AsyncMock()
        monkeypatch.setattr(child, "capability_controller", c, raising=False)

        async def execute(controller, command, **kwargs):
            await command(controller)

        monkeypatch.setattr(child, "async_execute_controller_command", partial(execute, c))
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, side)], []))
    await services.async_register_services(hass)
    request = {"device_id": "pair", "control": "tilt_up", "duration": 0.1}
    if side == const.SIDE_BOTH:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(const.DOMAIN, "hold_control", request, blocking=True)
        assert all(not c.hold_control.called for c in controls)
    else:
        await hass.services.async_call(const.DOMAIN, "hold_control", request, blocking=True)
        controls[1].hold_control.assert_awaited_once()
        controls[0].hold_control.assert_not_awaited()


@pytest.mark.parametrize("name", ["KSBT02C123", "prefixKSBT02C123", "base123", "BASE123"])
def test_shared_name_discovery_offers_junasleep_without_choosing_a_remote(name):
    from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed

    info = MagicMock()
    info.name = info.device.name = info.advertisement.local_name = name
    info.manufacturer_data = {}
    info.service_uuids = []
    info.advertisement.service_uuids = []
    result = detect_bed_type_detailed(info)
    assert "junasleep" in {result.bed_type, *(result.ambiguous_types or ())}
    if result.bed_type == "junasleep":
        assert detect_bed_type(info) is None


async def test_missing_notification_role_does_not_gate_control(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    client.services = gatt()[:2]
    target = AdjustableBedCoordinator(hass, entry(hass, "b"))
    assert await target.async_connect()
    target._ble_device_name = "base000000000000"
    c = target.controller
    await c.async_discover_capabilities()
    await c.start_notify()
    assert c._link.notify is None
    client.write_gatt_char.reset_mock()
    await c.preset_flat()
    assert written(client) == ["e5fe1600000008fe"]
    await target.async_shutdown()
