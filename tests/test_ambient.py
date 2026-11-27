"""M3 Ambient setup, entities and actions against a simulated GATT receiver."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, EntityCategory
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_sync_profile_ids,
    button,
    const,
    light,
    number,
    sensor,
    services,
)
from custom_components.adjustable_bed.codec import ambient as p1
from custom_components.adjustable_bed.codec import ambient_climate as p2
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type, detect_new_bed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profile_migration import reconfigure_context
from custom_components.adjustable_bed.profiles import ambient as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from tests.error_helpers import raises_key
from tests.form_helpers import form_fields, options_of
from tests.test_config_flow import _advance_progress, _patch_gate

ADDRESS = "AA:BB:CC:DD:EE:A6"
_LEFT_STATE = bytes.fromhex("26259f79aa29100709151700536a0000410a")
_RIGHT_STATE = bytes.fromhex("26259f79bb1718000000000000000000410a")
_ONE_PIECE_ECHO = bytes.fromhex("242380090011000b000700080000410a13")


@pytest.fixture(autouse=True)
def short_waits(monkeypatch):
    monkeypatch.setattr(app, "WRITE_PACING", 0)
    monkeypatch.setattr(app, "SAMPLE_TIMEOUT", 0.04)
    monkeypatch.setattr(app, "HEAT_PROBE_INTERVAL", 0.01)
    monkeypatch.setattr(app, "HEAT_TIMEOUT", 0.07)
    monkeypatch.setattr(app, "HEAT_TIMER_DELAY", 0.015)


def test_control_box_is_an_app_hint_and_never_a_receiver_identity():
    info = SimpleNamespace(
        name="prefix cOnTrOl_BoX 123",
        address=ADDRESS,
        service_uuids=[],
        manufacturer_data={},
        service_data={},
    )
    assert detect_bed_type(info) is None
    result = detect_new_bed(info)
    assert result.bed_type == const.BED_TYPE_AMBIENT and result.confidence == 0.3
    info.name, info.service_uuids = "Generic receiver", [app.SERVICE]
    assert detect_bed_type(info) != const.BED_TYPE_AMBIENT


@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_setup_requires_an_explicit_layout(hass, layout):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._selected_bed_type = const.BED_TYPE_AMBIENT
    result = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
    assert result["step_id"] == "profile_questions"
    variant_field = form_fields(result["data_schema"])[const.CONF_PROTOCOL_VARIANT]
    assert options_of(variant_field) == list(app.LAYOUTS)
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: layout})
        assert result["step_id"] == "finish_settings"
        assert const.CONF_PROTOCOL_VARIANT not in form_fields(result["data_schema"])
        result = await flow.async_step_finish_settings(
            {CONF_NAME: "Ambient bed", const.CONF_CONNECTION_MODE: "idle"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == layout
    entry = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    entry.add_to_hass(hass)
    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == f"ambient:{layout}"


def _receiver(*, write=True, notify=True):
    # The selected characteristic object and handle must survive through the write.
    writer = SimpleNamespace(
        uuid=app.WRITE, properties=["write"] if write else ["write-without-response"], handle=3
    )
    notifier = SimpleNamespace(
        uuid=app.NOTIFY, properties=["notify"] if notify else ["read"], handle=5
    )
    service = SimpleNamespace(uuid=app.SERVICE, characteristics=[writer, notifier])
    client = SimpleNamespace(
        address=ADDRESS,
        is_connected=True,
        services=[service],
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client, writer, notifier


@pytest.mark.parametrize("notify", [True, False])
async def test_setup_probe_checks_roles_without_subscribing_or_writing(hass, notify):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    client, _, _ = _receiver(notify=notify)

    with (
        _patch_gate("hci0", -55),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
        patch("custom_components.adjustable_bed.config_flow.discover_services", AsyncMock()),
    ):
        report = await flow._probe_capabilities(ADDRESS, "auto", const.BED_TYPE_AMBIENT, app.SPLIT)

    assert report.ambient_transport_valid is notify
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.disconnect.assert_awaited_once()


async def test_reconfigure_rejects_an_unproven_receiver(hass, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Existing bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Existing bed",
            const.CONF_BED_TYPE: const.BED_TYPE_LINAK,
        },
        unique_id=ADDRESS,
    )
    entry.add_to_hass(hass)
    previous = dict(entry.data)
    manager = hass.config_entries.flow
    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_AMBIENT}
    )
    assert result["step_id"] == "profile_questions"

    client, _, _ = _receiver(notify=False)

    with (
        _patch_gate("hci0", -55),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
        patch("custom_components.adjustable_bed.config_flow.discover_services", AsyncMock()),
    ):
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_PROTOCOL_VARIANT: app.SPLIT}
        )
        result = await _advance_progress(hass, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "ambient_receiver_mismatch"
    assert dict(entry.data) == previous
    client.write_gatt_char.assert_not_awaited()


async def _runtime(hass, layout=app.SPLIT, **roles):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Ambient bed",
            const.CONF_BED_TYPE: const.BED_TYPE_AMBIENT,
            const.CONF_PROTOCOL_VARIANT: layout,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client, writer, notifier = _receiver(**roles)
    coordinator._client = client
    controller = await create_controller(coordinator, const.BED_TYPE_AMBIENT, layout, client)
    coordinator._controller = controller
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(const.DOMAIN, ADDRESS)}
    )

    def receive(data):
        _, callback = client.start_notify.await_args.args
        callback(notifier, bytearray(data))

    async def action(name, **fields):
        await hass.services.async_call(
            const.DOMAIN,
            f"ambient_{name}",
            {"device_id": device.id, **fields},
            blocking=True,
        )

    await services.async_register_services(hass)
    return SimpleNamespace(
        client=client,
        writer=writer,
        notifier=notifier,
        coordinator=coordinator,
        controller=controller,
        receive=receive,
        action=action,
        device_id=device.id,
        frames=lambda: [call.args[1] for call in client.write_gatt_char.await_args_list],
    )


async def _entities(runtime, platform):
    coordinator = runtime.coordinator
    entities = []
    await platform.async_setup_entry(coordinator.hass, coordinator.entry, entities.extend)
    return {entity._attr_translation_key: entity for entity in entities}


async def test_startup_queries_only_after_notification_setup(hass):
    runtime = await _runtime(hass)
    controller = runtime.controller
    session = SimpleNamespace(
        is_current=lambda: True,
        async_start_notify=runtime.coordinator.async_start_notify,
    )
    await controller.async_on_connect(session)
    runtime.client.start_notify.assert_awaited_once()
    await controller.async_after_connect(session)
    assert runtime.frames() == [
        bytes.fromhex(frame)
        for frame in (
            "24239c420000de410d",
            "519f030103f7",
            "519f030104f8",
            "519f030108fc",
            "519f030109fd",
            "519f03012216",
        )
    ]
    assert all(
        call.args[0] is runtime.writer and call.kwargs == {"response": True}
        for call in runtime.client.write_gatt_char.await_args_list
    )

    runtime.receive(bytes.fromhex("519f0203040101fb"))
    runtime.receive(bytes.fromhex("519f060102030400"))
    state = runtime.coordinator.controller_state
    assert state["ambient_power_supply"] == "DC"
    assert state["ambient_firmware"] == "1020304"
    buttons = await _entities(runtime, button)
    sensors = await _entities(runtime, sensor)
    for entity in (
        buttons["ambient_refresh"],
        sensors["ambient_power_supply"],
        sensors["ambient_firmware"],
    ):
        assert entity.entity_category is EntityCategory.DIAGNOSTIC
        assert entity.entity_registry_enabled_default is False


@pytest.mark.parametrize("roles", [{"write": False}, {"notify": False}])
async def test_bad_gatt_never_admits_control(hass, roles):
    runtime = await _runtime(hass, **roles)
    with pytest.raises(BleakError):
        await runtime.controller.start_notify()
    with pytest.raises(BedNotConnectedError):
        await runtime.controller.lights_on()
    runtime.client.start_notify.assert_not_awaited()
    assert runtime.frames() == []


async def test_split_position_actions_and_native_numbers_keep_their_selector(hass):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    numbers = await _entities(runtime, number)
    buttons = await _entities(runtime, button)
    assert "ambient_home_flat" not in buttons and "stop" not in buttons
    assert runtime.controller.motor_control_specs == ()
    await buttons["ambient_left_tv"].async_press()
    await runtime.action("set_position", position_side="right", head=23, feet=24, neck=0)
    assert [frame.hex() for frame in runtime.frames()] == [
        "26258009aa00290010000000000000410a13",
        "26258009bb00170018000000000000410a13",
    ]
    assert numbers["ambient_left_head"].native_value is None
    with raises_key("ambient_position_side"):
        await runtime.action("set_position", head=10, feet=8, neck=3)
    assert len(runtime.frames()) == 2

    runtime.receive(_LEFT_STATE)
    assert numbers["ambient_left_head"].native_value == 41
    assert numbers["ambient_right_head"].native_value is None
    before = len(runtime.frames())
    runtime.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: runtime.receive(
        _LEFT_STATE
    )
    with raises_key("ambient_position_unknown"):
        await numbers["ambient_right_head"].async_set_native_value(9)
    assert runtime.frames()[before:] == [p1.BED_STATE_QUERY]
    runtime.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: runtime.receive(
        _RIGHT_STATE
    )
    await numbers["ambient_right_head"].async_set_native_value(9)
    assert runtime.frames()[-1] == p1.position(p1.Coordinates(9, 24, 0), p1.Side.RIGHT)


async def test_one_piece_presets_preserve_template_and_home_flat_is_distinct(hass):
    runtime = await _runtime(hass, app.ONE_PIECE)
    await runtime.controller.start_notify()
    runtime.receive(_ONE_PIECE_ECHO)
    buttons = await _entities(runtime, button)
    await buttons["ambient_tv"].async_press()
    await buttons["ambient_anti_snore"].async_press()
    await buttons["ambient_home_flat"].async_press()
    runtime.controller.on_disconnect()
    await runtime.controller.start_notify()
    await buttons["ambient_anti_snore"].async_press()
    assert [frame.hex() for frame in runtime.frames()] == [
        "2423800900290010000000080000410a13",
        "2423800900090000000000080000410a13",
        "24235555000000410d",
        "2423800900090000000000000000410a13",
    ]
    with raises_key("ambient_position_side"):
        await runtime.action("set_position", position_side="left", head=9, feet=0, neck=0)


@pytest.mark.parametrize("unlock_first", [False, True])
async def test_cancelled_native_preset_never_reaches_ble(hass, unlock_first):
    runtime = await _runtime(hass, app.ONE_PIECE)
    await runtime.controller.start_notify()
    buttons = await _entities(runtime, button)
    queued = asyncio.Event()

    class ObservedLock(asyncio.Lock):
        async def acquire(self):
            if self.locked():
                queued.set()
            return await super().acquire()

    lock = runtime.controller._ble_lock = ObservedLock()
    await lock.acquire()
    press = asyncio.create_task(buttons["ambient_anti_snore"].async_press())
    try:
        await asyncio.wait_for(queued.wait(), 1)
        assert runtime.frames() == []
        if unlock_first:
            lock.release()
        press.cancel()
        done, _ = await asyncio.wait((press,), timeout=1)
        assert press in done
        with pytest.raises(asyncio.CancelledError):
            await press
        if not unlock_first:
            assert lock.locked()
        assert runtime.frames() == []
    finally:
        if not unlock_first and lock.locked():
            lock.release()
        await asyncio.gather(press, return_exceptions=True)


async def test_cancelled_native_preset_settles_an_already_submitted_write(hass):
    runtime = await _runtime(hass, app.ONE_PIECE)
    await runtime.controller.start_notify()
    buttons = await _entities(runtime, button)
    submitted = asyncio.Event()
    acknowledge = asyncio.Event()

    async def write(*_args, **_kwargs):
        submitted.set()
        await acknowledge.wait()

    runtime.client.write_gatt_char.side_effect = write
    press = asyncio.create_task(buttons["ambient_anti_snore"].async_press())
    try:
        await asyncio.wait_for(submitted.wait(), 1)
        press.cancel()
        await asyncio.sleep(0)
        assert runtime.controller._ble_lock.locked()
    finally:
        acknowledge.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(press, 1)
    assert not runtime.controller._ble_lock.locked()
    assert len(runtime.frames()) == 1


@pytest.mark.parametrize(
    ("action", "fields"),
    [
        ("set_position", {"head": 9, "feet": 0, "neck": 0}),
        ("set_heat", {"heat_side": "left", "shoulder": 0, "torso": 0, "legs": 0}),
        ("set_rgb", {"red": 1, "green": 2, "blue": 3}),
    ],
)
async def test_stop_invalidates_ambient_actions_waiting_on_import(hass, monkeypatch, action, fields):
    from custom_components.adjustable_bed.beds.ambient import services as ambient_services

    runtime = await _runtime(hass, app.ONE_PIECE)
    await runtime.controller.start_notify()
    waiting = asyncio.Event()
    resume = asyncio.Event()

    async def delayed_import(*_args):
        waiting.set()
        await resume.wait()

    monkeypatch.setattr(ambient_services, "async_import_modules", delayed_import)
    queued = asyncio.create_task(runtime.action(action, **fields))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        with raises_key("ambient_stop_unavailable"):
            await hass.services.async_call(
                const.DOMAIN, "stop_all", {"device_id": runtime.device_id}, blocking=True
            )
    finally:
        resume.set()
    await asyncio.wait_for(queued, 1)
    assert runtime.frames() == []


async def test_stop_on_disconnected_ambient_fences_local_work_without_connecting(hass):
    runtime = await _runtime(hass)
    coordinator = runtime.coordinator
    coordinator._controller = None
    coordinator._client = None
    stop_epoch = coordinator.stop_epoch
    with (
        patch.object(coordinator, "async_ensure_connected", new=AsyncMock()) as connect,
        raises_key("ambient_stop_unavailable"),
    ):
        await hass.services.async_call(
            const.DOMAIN, "stop_all", {"device_id": runtime.device_id}, blocking=True
        )
    assert coordinator.stop_epoch == stop_epoch + 1
    connect.assert_not_awaited()
    runtime.client.start_notify.assert_not_awaited()
    assert runtime.frames() == []


async def test_native_light_and_raw_rgb_action_use_separate_color_scales(hass):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    lights = await _entities(runtime, light)
    entity = lights["under_bed_lights"]
    entity.async_write_ha_state = Mock()
    await entity.async_turn_on(rgb_color=(255, 128, 1))
    assert [frame.hex() for frame in runtime.frames()] == [
        "242380f1000071410d",
        "242380e8007810410d",
        "242380e9003c55410d",
        "242380ea00006a410d",
        "24239c420000de410d",
    ]
    state = runtime.coordinator.controller_state
    assert state.get(UNDER_BED_LIGHTS_ON) is None
    runtime.receive(p1.LIGHT_ON)
    runtime.receive(_LEFT_STATE)
    assert runtime.coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True
    assert runtime.coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (0, 176, 225)

    await runtime.action("set_rgb", red=255, green=128, blue=1)
    assert runtime.frames()[-4:] == [
        p1.rgb("red", 255),
        p1.rgb("green", 128),
        p1.rgb("blue", 1),
        p1.BED_STATE_QUERY,
    ]


async def test_massage_and_fan_publish_only_reported_state(hass):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    entities = await _entities(runtime, number)
    massage = entities["ambient_shoulder_massage"]
    fan = entities["ambient_left_fan"]
    await massage.async_set_native_value(1)
    assert massage.native_value is None
    runtime.receive(bytes.fromhex("242382790015ee410a"))
    assert massage.native_value is None
    runtime.receive(bytes.fromhex("242382790015ee410d"))
    assert massage.native_value == 1
    assert entities["ambient_feet_massage"].native_value is None

    await fan.async_set_native_value(5)
    assert runtime.frames()[-2:] == [
        bytes.fromhex("519f010308011916"),
        bytes.fromhex("519f030108fc"),
    ]
    assert fan.native_value is None
    runtime.receive(bytes.fromhex("519f020308011917"))
    assert fan.native_value == 5
    assert entities["ambient_right_fan"].native_value is None


def _heat_reply(zones):
    body = bytes((0x51, 0x9F, 2, 8, 3, 6, *zones))
    return body + bytes((sum(body) & 255,))


@pytest.mark.parametrize("zones", [(6, 12, 18), (0, 0, 0)])
async def test_heat_action_preserves_peer_and_only_exact_confirmation_allows_timer(hass, zones):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    prior = (7, 8, 9, 1, 2, 3)
    shoulder, torso, legs = zones
    expected = (7, 8, 9, shoulder, torso, legs)
    query_count = 0

    async def respond(_char, frame, **_kwargs):
        nonlocal query_count
        if frame != p2.query(p2.Query.HEAT_ZONES):
            return
        query_count += 1
        if query_count == 1:
            runtime.receive(_heat_reply(prior))
        elif query_count == 2:
            runtime.receive(_heat_reply(expected)[:-1] + b"\x00")
            runtime.receive(_heat_reply((7, 8, 9, 6, 12, 17)))
        else:
            runtime.receive(_heat_reply(expected))

    runtime.client.write_gatt_char.side_effect = respond
    await runtime.action(
        "set_heat", heat_side="left", shoulder=shoulder, torso=torso, legs=legs, timer_hours="2"
    )
    assert runtime.frames() == [
        p2.query(p2.Query.HEAT_ZONES),
        p2.heat(expected),
        p2.query(p2.Query.HEAT_ZONES),
        p2.query(p2.Query.HEAT_ZONES),
        p2.heat_timer(2),
    ]
    assert runtime.coordinator.controller_state["ambient_right_legs_heat"] == 9
    assert runtime.coordinator.controller_state["ambient_left_legs_heat"] == legs


async def test_heat_action_never_writes_from_old_or_incomplete_state(hass):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    valid = _heat_reply((7, 8, 9, 1, 2, 3))
    runtime.receive(valid)
    runtime.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: runtime.receive(
        valid[:-2]
    )
    with raises_key("ambient_heat_unknown"):
        await runtime.action("set_heat", heat_side="right", shoulder=6, torso=12, legs=18)
    assert runtime.frames() == [p2.query(p2.Query.HEAT_ZONES)]


async def test_heat_confirmation_during_pending_target_write_allows_timer(hass):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    query = p2.query(p2.Query.HEAT_ZONES)
    expected = (7, 8, 9, 6, 12, 18)
    target = p2.heat(expected)
    submitted = asyncio.Event()
    acknowledge = asyncio.Event()
    query_count = 0

    async def respond(_char, frame, **_kwargs):
        nonlocal query_count
        if frame == query:
            query_count += 1
            if query_count == 1:
                runtime.receive(_heat_reply((7, 8, 9, 1, 2, 3)))
        elif frame == target:
            runtime.receive(_heat_reply(expected))
            submitted.set()
            await acknowledge.wait()

    runtime.client.write_gatt_char.side_effect = respond
    command = asyncio.create_task(
        runtime.action("set_heat", heat_side="left", shoulder=6, torso=12, legs=18, timer_hours=2)
    )
    try:
        await asyncio.wait_for(submitted.wait(), 1)
        assert runtime.frames() == [query, target]
    finally:
        acknowledge.set()
    await asyncio.wait_for(command, 1)
    assert runtime.frames() == [query, target, query, p2.heat_timer(2)]


@pytest.mark.parametrize("replace_link", [False, True])
async def test_timer_requires_the_confirmed_zones_and_link_until_dispatch(
    hass, monkeypatch, replace_link
):
    from custom_components.adjustable_bed.beds.ambient import controller as module

    runtime = await _runtime(hass)
    bed = runtime.controller
    await bed.start_notify()
    waiting_for_timer = asyncio.Event()
    original_cancellable = module.cancellable
    query_count = 0

    async def cancellable(operation, cancel):
        if operation.__qualname__ == "sleep":
            waiting_for_timer.set()
        return await original_cancellable(operation, cancel)

    monkeypatch.setattr(module, "cancellable", cancellable)

    async def respond(_char, frame, **_kwargs):
        nonlocal query_count
        if frame != p2.query(p2.Query.HEAT_ZONES):
            return
        query_count += 1
        runtime.receive(
            _heat_reply((7, 8, 9, 1, 2, 3) if query_count == 1 else (7, 8, 9, 6, 12, 18))
        )

    runtime.client.write_gatt_char.side_effect = respond
    command = asyncio.create_task(
        runtime.action("set_heat", heat_side="left", shoulder=6, torso=12, legs=18, timer_hours=2)
    )
    async with asyncio.timeout(2):
        await waiting_for_timer.wait()

    if replace_link:
        _, old_callback = runtime.client.start_notify.await_args.args
        bed.on_disconnect()
        new_client, _, _ = _receiver()
        runtime.coordinator._client = new_client
        await bed.start_notify()
        old_callback(runtime.notifier, bytearray(_heat_reply((7, 8, 9, 6, 12, 18))))
        with pytest.raises(BedNotConnectedError):
            await command
        new_client.write_gatt_char.assert_not_awaited()
    else:
        runtime.receive(_heat_reply((7, 8, 0, 6, 12, 18)))
        with raises_key("ambient_heat_unconfirmed"):
            await command

    assert p2.heat_timer(2) not in runtime.frames()


async def test_heat_times_out_after_four_probes_without_matching_feedback(hass):
    runtime = await _runtime(hass)
    await runtime.controller.start_notify()
    query = p2.query(p2.Query.HEAT_ZONES)

    def respond(_char, frame, **_kwargs):
        if frame == query:
            # A valid six-zone response that never matches the requested values.
            runtime.receive(_heat_reply((7, 8, 9, 1, 2, 3)))

    runtime.client.write_gatt_char.side_effect = respond
    with raises_key("ambient_heat_unconfirmed"):
        await runtime.action(
            "set_heat", heat_side="left", shoulder=6, torso=12, legs=18, timer_hours=2
        )
    assert runtime.frames() == [query, p2.heat((7, 8, 9, 6, 12, 18)), query, query, query, query]
