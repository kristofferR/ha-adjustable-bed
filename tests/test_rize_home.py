"""Accepted unit163 vectors on production callers, virtual time and real HA setup."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.rize_home import controller as rize
from custom_components.adjustable_bed.profiles import rize_home as p
from tests.hold_lease_wire import virtual_clock
from tests.rize_home_vectors import ACTIONS, FROZEN_FRAMES, ROOT, VECTORS

COMMANDS = json.loads((ROOT / "commands.json").read_text())
PARSERS = json.loads((ROOT / "parser_vectors.json").read_text())
REPAIRS = json.loads((ROOT / "repair_boundary_cases.json").read_text())


def char(uuid, properties):
    return SimpleNamespace(uuid=uuid, properties=properties, handle=17, descriptors=[])


def bed(product="remedy_iii"):
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_count = 4  # Generic settings must not alter either product.
    client = coordinator.client
    client.is_connected = True
    client.services = [
        SimpleNamespace(
            uuid=p.SERVICE_UUID.upper(),
            characteristics=[
                char(p.WRITE_UUID.upper(), ["write-without-response"]),
                char(p.NOTIFY_UUID, ["notify"]),
            ],
        )
    ]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    controller = rize.RizeHomeController(coordinator, product)
    controller.static_traits = bed_traits("rize_home")
    return controller, coordinator, client


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_every_original_literal_uses_existing_codec(row):
    key = ACTIONS[row["method"]]
    if key == "stop" and row["branch"] == 0:
        key = "voice_stop"
    for profile in p.PROFILES.values():
        assert profile.frames[key] == bytes.fromhex(row["expected_bytes"])


def test_exact_frozen_census_and_no_invented_fields():
    assert len(VECTORS) == 34
    for profile in p.PROFILES.values():
        assert {v.hex() for v in profile.frames.values()} == FROZEN_FRAMES[profile.key]
    assert len(COMMANDS) == 39
    assert len(p.VOICE_ACTIONS) == 28


@pytest.mark.parametrize("row", PARSERS, ids=lambda row: row["id"])
def test_original_parser_cases_project_only_persisted_state(row):
    profile = p.PROFILES["remedy_iii" if row["model"] == "MODEL-1" else "contempo_iv"]
    state = p.parse_massage(profile, bytes.fromhex(row["input_bytes"]))
    if row.get("expected_error") or row.get("expected") is None:
        assert state is None  # Safe HA difference: reject the Android RangeError.
    else:
        expected = row["expected"]
        assert state.timer_index == expected["timer_index"]
        assert state.active == expected["massage_active"]
        if profile.combined_massage:
            assert state.combined_intensity == expected["head_level"]
            assert state.head is state.foot is state.mode is None
        else:
            assert (state.head, state.foot, state.mode) == (
                expected["head_level"],
                expected["foot_level"],
                expected["mode"],
            )


@pytest.mark.parametrize("row", REPAIRS["projections"], ids=lambda row: row["id"])
def test_repaired_remedy_log_only_byte_and_independent_contempo_fields(row):
    profile = p.PROFILES["remedy_iii" if row["model"] == "MODEL-1" else "contempo_iv"]
    states = [p.parse_massage(profile, bytes.fromhex(data)) for data in row["input_bytes"]]
    if profile.combined_massage:
        assert states[0] == states[1]
        assert states[0].combined_intensity == 1
    else:
        assert [state.foot for state in states] == [1, 9]
        assert [(state.timer_index, state.head, state.mode) for state in states] == [(2, 3, 2)] * 2


@pytest.mark.parametrize("row", COMMANDS, ids=lambda row: row["id"])
async def test_all_39_semantic_rows_execute_production_routes(row):
    c, coord, client = bed("contempo_iv" if row["action"] == "massageMode" else "remedy_iii")
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(dest, data, **kwargs):
            assert dest is client.services[0].characteristics[0]
            assert kwargs == {"response": False}
            writes.append((round(clock.elapsed * 1000), bytes(data)))

        client.write_gatt_char.side_effect = write
        action = row["action"]
        if action.startswith("program "):
            preset = {"zeroGravity": "zero_g", "antiSnore": "anti_snore", "memory": "memory"}.get(
                action.split()[1], action.split()[1]
            )
            await c.program_preset(preset)
        elif action.startswith("stopCommand"):
            if "speak" in action:
                await c.select_source("speak")
            await c.stop_all()
        else:
            key = ACTIONS[action]
            if key not in c._button_actions():
                key = "voice_" + key
            await c.action(key)
    literal = bytes.fromhex(row["bytes"])
    assert writes and writes[0][1] == literal
    assert all(frame in p.FRAMES.values() for _, frame in writes)
    if row["timing"]["mode"] in (
        "held-6s",
        "button-source held recall frame for6s",
    ) or action.startswith("program "):
        assert [at for at, frame in writes if frame == literal] == list(range(0, 6000, 200))
    if action == "confirmationResponse" or action == "underbedLighting":
        assert [at for at, _ in writes] == [0, 200, 400]


@pytest.mark.parametrize(
    "product, expected",
    [
        ("remedy_iii", [1500, 1600, 1800, 2000]),
        ("contempo_iv", [1500, 1700, 1900]),
    ],
)
async def test_shared_once_timer_poll_replacement_and_release(product, expected):
    c, coord, client = bed(product)
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_dest, data, **kwargs):
            writes.append((round(clock.elapsed * 1000), data))

        client.write_gatt_char.side_effect = write
        key = "massage_up" if product == "remedy_iii" else "massage_head_up"
        await c.hold_control(key, 2200)
    assert [at for at, frame in writes if frame == p.FRAMES["query"]] == expected + [
        2700,
        2900,
        3100,
    ]
    assert [at for at, frame in writes if frame == p.FRAMES[key]] == list(range(0, 1500, 200))
    assert [at for at, frame in writes if frame == p.FRAMES["stop"]] == [2400, 2600]


@pytest.mark.parametrize("product", p.PROFILES)
async def test_product_layouts_and_rejected_controls_write_nothing(product):
    c, coord, client = bed(product)
    await c.async_discover_capabilities()
    motors = [spec.key for spec in c.motor_control_specs]
    assert motors == (
        ["back", "legs", "lumbar", "bed_height"]
        if product == "remedy_iii"
        else ["head", "back", "legs", "lumbar", "bed_height"]
    )
    assert all(spec.scheduler_resource == "*" for spec in c.motor_control_specs)
    bad = "head_tilt_up" if product == "remedy_iii" else "memory"
    for control in (bad, "sync", "light_on", "massage_set_5"):
        with pytest.raises(ValueError):
            await c.hold_control(control, 1000)
    with pytest.raises(ValueError):
        await c.program_memory(5)
    with pytest.raises(ValueError):
        await c.program_preset("flat")
    assert not client.write_gatt_char.called


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_cancelled_movement_releases_with_captured_source_and_fresh_event(task_cancel):
    c, coord, client = bed()
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.select_source("speak")
        task = asyncio.create_task(c.move_back_up())
        await asyncio.wait({task}, timeout=0.25)
        coord.cancel_command.set()
        # An unrelated source update cannot change this operation's cleanup.
        await c.select_source("button")
        if task_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    frames = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert frames == [p.FRAMES["head_up"]] * 2 + [p.FRAMES["voice_stop"]] * 3


async def test_speech_once_and_sensor_refresh_only_cleanup():
    c, coord, client = bed()
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.action("voice_reading")
        assert c._source == "speak"
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            p.FRAMES["reading"]
        ] * 3
        client.write_gatt_char.reset_mock()
        await c.action("voice_motion_on")
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        p.FRAMES["motion_on"]
    ] * 30


async def test_notification_subscription_retry_and_old_callback_cannot_publish():
    c, coord, client = bed()
    with virtual_clock():
        await c.async_discover_capabilities()
        client.start_notify.side_effect = [BleakError("CCCD busy"), None]
        await c.start_notify()
        callback = client.start_notify.call_args.args[1]
        notify = client.services[0].characteristics[1]
        callback(notify, bytearray.fromhex("a5 0b 0e 00 00 01 00 02 08"))
        assert coord.handle_controller_state_updates.call_args.args == (
            rize.TIMER(1),
            rize.ACTIVE(True),
            rize.COMBINED(1),
            rize.HEAD(None),
            rize.FOOT(None),
            rize.MODE(None),
        )
        await c.stop_notify()
        coord.handle_controller_state_updates.reset_mock()
        callback(notify, bytearray.fromhex("a5 0b 0e 00 00 01 00 08 08"))
        coord.handle_controller_state_updates.assert_not_called()
        await c.async_discover_capabilities()
        client.start_notify.side_effect = None
        await c.start_notify()
        coord.handle_controller_state_updates.reset_mock()
        callback(notify, bytearray.fromhex("a5 0b 0e 00 00 01 00 08 08"))
        coord.handle_controller_state_updates.assert_not_called()


@pytest.mark.parametrize("role", ["write", "notify", "service"])
async def test_exact_gatt_roles_required_and_failed_discovery_invalidates_old_link(role):
    c, coord, client = bed()
    await c.async_discover_capabilities()
    if role == "service":
        client.services[0].uuid = "wrong"
    else:
        index = 0 if role == "write" else 1
        client.services[0].characteristics[index].properties = []
    with pytest.raises(ValueError):
        await c.async_discover_capabilities()
    with pytest.raises(ConnectionError):
        await c.preset_flat()
    assert not client.write_gatt_char.called


@pytest.mark.parametrize("product", p.PROFILES)
@pytest.mark.parametrize("route", ["typed", "picked", "discovered"])
async def test_setup_saves_each_product_profile_and_configure_reloads(hass, product, route):
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
    )
    from custom_components.adjustable_bed.detection import get_bed_type_options
    from custom_components.adjustable_bed.profile_id import with_profile_ids
    from tests.form_helpers import finish_new_bed, start_new_bed

    assert {o["value"]: o["label"] for o in get_bed_type_options()}["rize_home"].startswith(
        "Rize Home app"
    )
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    from tests.test_detection import _make_service_info

    flow._discovery_info = _make_service_info(name="smartbed163", address="AA:BB:CC:DD:16:30")
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await start_new_bed(flow, route, "rize_home", "AA:BB:CC:DD:16:30")
    assert form["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
    await finish_new_bed(flow, result)
    data = with_profile_ids(flow._finish_with_verify.call_args.args[0])
    assert data[const.CONF_PROFILE_ID] == f"rize_home:{product}"
    assert data[const.CONF_PROTOCOL_VARIANT] == product
    assert data[const.CONF_HAS_MASSAGE] is True
    assert data[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert const.CONF_MOTOR_COUNT in hidden_generic_fields("rize_home", product)
    entry = MockConfigEntry(domain=const.DOMAIN, title="Rize Home", data=data)
    entry.add_to_hass(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.hass, options.handler = hass, entry.entry_id
    other = "contempo_iv" if product == "remedy_iii" else "remedy_iii"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await options._async_options_form({const.CONF_PROTOCOL_VARIANT: other}, step_id="settings")
        assert entry.data[const.CONF_PROTOCOL_VARIANT] == other
        assert with_profile_ids(entry.data)[const.CONF_PROFILE_ID] == f"rize_home:{other}"
        from custom_components.adjustable_bed import _async_sync_profile_ids
        from custom_components.adjustable_bed.controller_factory import create_controller
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        _async_sync_profile_ids(hass, entry)
        assert entry.data[const.CONF_PROFILE_ID] == f"rize_home:{other}"
        coordinator = AdjustableBedCoordinator(hass, entry)
        reloaded = await create_controller(coordinator, "rize_home", other, None)
        assert reloaded.profile is p.PROFILES[other]


@pytest.mark.usefixtures("mock_coordinator_connected")
@pytest.mark.parametrize("product", p.PROFILES)
@pytest.mark.parametrize("source_route", ["selector", "voice_entity"])
async def test_real_coordinator_startup_reconnect_entity_and_service_callers(
    hass, mock_bleak_client, product, source_route
):
    from unittest.mock import patch

    from homeassistant.const import CONF_ADDRESS
    from homeassistant.exceptions import ServiceValidationError
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.button import (
        AdjustableBedProductButton,
        ControllerActionButton,
        _button_entities_for,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
    from custom_components.adjustable_bed.services import async_register_services

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Rize Home",
        unique_id="AA:BB:CC:DD:16:30",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:16:30",
            const.CONF_BED_TYPE: "rize_home",
            const.CONF_PROTOCOL_VARIANT: product,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_MOTOR_PULSE_COUNT: 3,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    coord._max_retries = 1
    write = char(p.WRITE_UUID, ["write-without-response"])
    notify = char(p.NOTIFY_UUID, ["notify"])
    services = [SimpleNamespace(uuid=p.SERVICE_UUID, characteristics=[write, notify])]
    mock_bleak_client.services.__iter__ = lambda _: iter(services)
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coord
    await async_register_services(hass)
    # No real protocol waits. Full timing is tested separately on virtual time.
    with patch.object(rize, "_pause", AsyncMock(return_value=False)):
        assert await coord.async_connect()
        controller = coord.controller
        assert isinstance(controller, rize.RizeHomeController)
        assert controller.profile is p.PROFILES[product]
        assert [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list] == [
            p.FRAMES["query"]
        ] * 3
        source = AdjustableBedControllerSelect(coord, controller.controller_select_specs[0])
        source.hass = hass
        voices = [
            e
            for e in _button_entities_for(hass, coord)
            if isinstance(e, AdjustableBedProductButton)
        ]
        assert len(voices) == 28
        assert all(not e.entity_registry_enabled_default for e in voices)
        if source_route == "selector":
            await source.async_select_option("speak")
        else:
            voice = next(e for e in voices if e._spec.key == "rize_home_voice_reading")
            voice.hass = hass
            await voice.async_press()
        assert source.current_option == "speak"
        old_callback = mock_bleak_client.start_notify.call_args.args[1]
        await coord.async_disconnect()
        mock_bleak_client.write_gatt_char.reset_mock()
        # The real entity reconnects an idle link before invoking its controller.
        new_write = char(p.WRITE_UUID, ["write-without-response"])
        services[0].characteristics[0] = new_write
        spec = next(
            s for s in controller.controller_button_specs if s.key == "rize_home_save_zero_g"
        )
        entity = ControllerActionButton(coord, spec)
        entity.hass = hass
        await entity.async_press()
        assert coord.controller.profile is p.PROFILES[product]
        assert coord.controller is not controller
        assert coord.controller._source == "speak"
        assert source.current_option == "speak"
        writes = mock_bleak_client.write_gatt_char.await_args_list
        assert all(call.args[0] is new_write for call in writes)
        assert [call.args[1] for call in writes] == [p.FRAMES["query"]] * 3 + [
            p.FRAMES["zero_g"]
        ] * 3 + [p.FRAMES["voice_stop"]] * 3
        old_callback(notify, bytearray.fromhex("a5 0b 0e 00 00 01 00 02 08"))
        assert coord.controller_state.get(rize.ACTIVE) is None
        mock_bleak_client.write_gatt_char.reset_mock()
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coord, "both")], []),
        ):
            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {
                        "device_id": ["bed"],
                        "control": "light_on",
                        "duration": 0.1,
                    },
                    blocking=True,
                )
            mock_bleak_client.write_gatt_char.assert_not_awaited()
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {
                    "device_id": ["bed"],
                    "control": "head_up",
                    "duration": 0.6,
                },
                blocking=True,
            )
            assert [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list] == [
                p.FRAMES["head_up"]
            ] * 3 + [p.FRAMES["voice_stop"]] * 3
        await coord.async_shutdown()


@pytest.mark.parametrize("product", p.PROFILES)
@pytest.mark.parametrize("end", ["expire", "stop"])
async def test_actual_leased_motor_and_card_hold_release(product, end):
    from tests.hold_lease_wire import Write, leased_hold

    wire = await leased_hold(
        "rize_home:" + product,
        lambda c: c.move_back_up(),
        end_after_s=1.05,
        end=end,
    )
    assert wire.held == tuple(Write(ms, p.FRAMES["head_up"]) for ms in range(0, 1050, 200))
    releases = (1050, 1250, 1450) if end == "expire" else (1050, 1250, 1450, 1457, 1657, 1857)
    assert wire.after == tuple(Write(ms, p.FRAMES["stop"]) for ms in releases)


def test_shared_discovery_is_only_an_app_candidate():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    for name in ("smartbed163", "SmArTbEd163"):
        result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[]))
        assert "rize_home" in {result.bed_type, *(result.ambiguous_types or ())}
        assert result.confidence == 0.3
        assert "name:rize_home_app_candidate" in result.signals


@pytest.mark.parametrize("product", p.PROFILES)
async def test_nominal_query_and_release_times_absorb_write_latency(product):
    c, coord, client = bed(product)
    writes = []
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_dest, data, **_kwargs):
            writes.append((round(clock.elapsed * 1000), data))
            await asyncio.sleep(0.007)

        client.write_gatt_char.side_effect = write
        await c.hold_control("massage_up" if product == "remedy_iii" else "massage_head_up", 2200)
    query = [1500, 1600, 1800, 2000] if product == "remedy_iii" else [1500, 1700, 1900]
    assert [at for at, frame in writes if frame == p.FRAMES["query"]] == query + [2700, 2900, 3100]
    assert [at for at, frame in writes if frame == p.FRAMES["stop"]] == [2400, 2600]


async def test_short_light_gesture_replaces_its_once_timer_with_stop():
    c, coord, client = bed()
    with virtual_clock():
        await c.async_discover_capabilities()
        await c.hold_control("light", 100)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
        p.FRAMES["light"]
    ] + [p.FRAMES["stop"]] * 3


async def test_old_command_cleanup_cannot_send_or_cancel_a_new_session():
    c, coord, client = bed()
    with virtual_clock():
        await c.async_discover_capabilities()
        old = c._link
        task = asyncio.create_task(c.move_back_up())
        await asyncio.wait({task}, timeout=0.05)
        c.on_disconnect()
        new_write = char(p.WRITE_UUID, ["write-without-response"])
        client.services[0].characteristics[0] = new_write
        await c.async_discover_capabilities()
        generation = c._timer
        task.cancel()
        with pytest.raises(ConnectionError):
            await task
        assert c._timer == generation
        assert c._link is not old
        assert all(call.args[0] is not new_write for call in client.write_gatt_char.await_args_list)


@pytest.mark.parametrize("product", p.PROFILES)
def test_actual_standard_button_admission_and_card_metadata(product):
    from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS

    c, _, _ = bed(product)
    descriptions = {d.key: d for d in BUTTON_DESCRIPTIONS}
    for key in (
        "preset_zero_g",
        "preset_anti_snore",
        "preset_lounge",
        "toggle_light",
        "massage_all_toggle",
    ):
        supported = descriptions[key].is_supported
        assert supported is not None and supported(c)
        assert c.standard_button_hold_spec(key).control in c.held_control_options
    supported = descriptions["preset_reading"].is_supported
    assert supported is not None and supported(c) == (product == "remedy_iii")
    assert c.supports_memory_presets == (product == "remedy_iii")
    assert c.motor_pulse_settings()[1] == 200


@pytest.mark.parametrize("product", p.PROFILES)
@pytest.mark.parametrize("action", p.VOICE_ACTIONS)
async def test_all_shared_voice_action_entities_use_the_production_dispatcher(
    hass, product, action
):
    c, coord, client = bed(product)
    with virtual_clock():
        await c.async_discover_capabilities()
        from custom_components.adjustable_bed.button import (
            AdjustableBedProductButton,
            _button_entities_for,
        )

        coord.capability_controller = c
        coord.entity_side = None
        coord.entry.entry_id = "rize-home-" + product
        coord.entity_unique_id.side_effect = lambda key: key
        voices = {
            entity._spec.key: entity
            for entity in _button_entities_for(hass, coord)
            if isinstance(entity, AdjustableBedProductButton)
        }
        assert set(voices) == {"rize_home_voice_" + key for key in p.VOICE_ACTIONS}
        entity = voices["rize_home_voice_" + action]
        assert entity.entity_registry_enabled_default is False
        assert entity._spec.scheduler_resource == "*"
        placement = json.loads((ROOT.parent / "card_placements.json").read_text())[
            "button:product_action"
        ]
        assert entity._card.attributes == placement == {"card_section": "hidden"}
        entity.hass = hass

        async def execute(command, **_kwargs):
            await command(c)

        coord.async_execute_controller_command = AsyncMock(side_effect=execute)
        await entity.async_press()
        coord.async_execute_controller_command.assert_awaited_once()
    key = "voice_stop" if action == "stop" else action
    assert client.write_gatt_char.await_args_list[0].args[1] == p.FRAMES[key]
    assert c._source == "speak"


async def test_transport_failure_keeps_its_type_and_does_not_suppress_stop_burst():
    c, coord, client = bed()
    with virtual_clock():
        await c.async_discover_capabilities()
        client.write_gatt_char.side_effect = [BleakError("movement failed"), None, None, None]
        with pytest.raises(BleakError, match="movement failed"):
            await c.move_back_up()
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            p.FRAMES["head_up"]
        ] + [p.FRAMES["stop"]] * 3
        client.write_gatt_char.reset_mock()
        client.write_gatt_char.side_effect = [BleakError("first STOP failed"), None, None]
        with pytest.raises(BleakError, match="first STOP failed"):
            await c.stop_all()
        assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [
            p.FRAMES["stop"]
        ] * 3


@pytest.mark.parametrize(
    "product, expected",
    [
        ("remedy_iii", [1500, 1850, 1857, 2000]),
        ("contempo_iv", [1500, 1850, 1900]),
    ],
)
async def test_pending_plugin_write_does_not_restart_replacement_query_deadlines(product, expected):
    c, _, client = bed(product)
    writes = []
    first_query = True
    with virtual_clock() as clock:
        await c.async_discover_capabilities()

        async def write(_dest, data, **_kwargs):
            nonlocal first_query
            writes.append((round(clock.elapsed * 1000), data))
            delay = 0.35 if data == p.FRAMES["query"] and first_query else 0.007
            if data == p.FRAMES["query"]:
                first_query = False
            await asyncio.sleep(delay)

        client.write_gatt_char.side_effect = write
        await c.hold_control("massage_up" if product == "remedy_iii" else "massage_head_up", 2200)
    assert [at for at, frame in writes if frame == p.FRAMES["query"]] == expected + [
        2700,
        2900,
        3100,
    ]
