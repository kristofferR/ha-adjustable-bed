"""Real CheersSleep factory, HA callers, model gates and session ownership."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.cheerssleep import controller as bed
from custom_components.adjustable_bed.beds.cheerssleep import state_keys as keys
from custom_components.adjustable_bed.codec import cheerssleep as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.controller_state import ControllerState, sided
from custom_components.adjustable_bed.profiles import cheerssleep as app
from custom_components.adjustable_bed.state_keys import (
    LIGHT_LEVEL,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
)
from tests.cheerssleep_vectors import MODELS
from tests.error_helpers import raises_key
from tests.test_controller_contract import _FactoryCoordinator


def make(key=174, coord=None):
    c = coord or _FactoryCoordinator()
    c.entry.data[CONF_PRODUCT_TYPE] = str(key)
    c.controller_state = ControllerState()
    c.handle_controller_state_updates = lambda *updates: c.controller_state.update(
        (u.key, u.value) for u in updates
    )
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    write = MagicMock(uuid=codec.WRITE, handle=2, properties=["write"])
    notify = MagicMock(uuid=codec.NOTIFY, handle=3, properties=["notify"])
    service = MagicMock(uuid=codec.SERVICE)
    service.get_characteristic.side_effect = lambda uuid: {
        codec.WRITE: write,
        codec.NOTIFY: notify,
    }.get(uuid)
    c.client.services = [service]
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()

    async def disconnect():
        c.client.is_connected = False

    c.client.disconnect = AsyncMock(side_effect=disconnect)
    c.client.write_gatt_char = AsyncMock()
    ctrl = bed.CheersSleepController(c, app.MODELS[key])
    c.controller = ctrl
    return ctrl, c


def frames(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.call_args_list]


def entity_runtime(ctrl, c):
    """Run native public callers and registered callbacks against the real controller."""
    runtime = MagicMock(
        capability_controller=ctrl,
        controller=ctrl,
        controller_state=c.controller_state,
        device_info={},
        entity_side=None,
    )
    runtime.entity_unique_id.side_effect = lambda key: f"cheerssleep_{key}"
    callbacks = []

    def subscribe(callback):
        callbacks.append(callback)
        callback(c.controller_state)
        return lambda: callbacks.remove(callback)

    def publish(*updates):
        c.controller_state.update((u.key, u.value) for u in updates)
        for callback in callbacks:
            callback(c.controller_state)

    c.handle_controller_state_updates = publish
    runtime.register_controller_state_callback.side_effect = subscribe
    lock = asyncio.Lock()

    async def execute(command, **_kwargs):
        async with lock:
            await command(runtime.controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    return runtime


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    real_sleep = asyncio.sleep

    async def pause(seconds, cancel):
        now[0] += seconds
        await real_sleep(0)
        return not cancel.is_set()

    async def sleep(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed, "_pause", pause)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    return now


@pytest.mark.parametrize("row", MODELS, ids=lambda row: row["id"])
async def test_all_model_keys_factory_and_declared_entities(row):
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.pairing import supports_single_address_pairing

    _, c = make(row["model_key"])
    ctrl = await create_controller(c, "cheerssleep", "auto", c.client)
    assert isinstance(ctrl, bed.CheersSleepController)
    assert ctrl.model.key == row["model_key"]
    assert ctrl.profile.key == row["protocols"][0].lower()
    assert ctrl.memory_slot_count == row["capabilities"]["memory_slots"]
    assert ctrl.supports_single_address_pairing == bool(row["capabilities"].get("side_selection"))
    assert (
        supports_single_address_pairing("cheerssleep", product_type=str(ctrl.model.key))
        == ctrl.model.split
    )
    assert not ctrl.position_number_specs and not ctrl.execution.concurrent
    assert [s.key for s in ctrl.motor_control_specs] == list(ctrl.model.axes)
    assert all(s.hold for s in ctrl.motor_control_specs)
    assert ctrl.execution.hold == ("latched" if ctrl.model.format == "p1" else "stream")


def test_scan_signed_first_company_and_app_candidate_preserves_remacro():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    assert app.advertisement({89: bytes((0, 0, 45))}) == (app.MODELS[134], True)
    assert app.advertisement({89: bytes((0, 0, 212))}) == (app.MODELS[45], True)
    assert app.advertisement({134: b"", 45: b""}) == (app.MODELS[45], False)
    assert app.advertisement({89: b"1"}) is None
    assert app.advertisement({1: b"", 45: b""}) is None
    info = SimpleNamespace(
        name="Any name",
        address="AA:BB",
        service_uuids=[codec.SERVICE],
        manufacturer_data={89: bytes((0, 0, 45))},
        service_data={},
    )
    result = detect_bed_type_detailed(info)
    assert result.bed_type == "remacro" and "cheerssleep" in result.ambiguous_types


@pytest.mark.parametrize("key", [45, 134, 141, 172])
async def test_picker_new_install_and_per_side_fields(hass, key):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    form = await flow.async_step_select_app()
    picker = next(
        value for field, value in form["data_schema"].schema.items() if field == CONF_BED_TYPE
    )
    label = next(label for label, value in picker.rows().items() if value == "cheerssleep")
    assert "CheersSleep" in label
    await flow.async_step_select_app({CONF_BED_TYPE: label})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:98"})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({CONF_PRODUCT_TYPE: str(key)})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_PRODUCT_TYPE] == str(key)
    assert saved["motor_count"] == min(4, max(2, len(app.MODELS[key].axes)))
    assert CONF_PRODUCT_TYPE in per_side_profile("cheerssleep", "auto").keys


@pytest.mark.parametrize(
    "key,selected,expected",
    [
        (45, None, ["0201010100000000", "0301000100000000"]),
        (52, "right", ["0201046400000000", "0301036400000000"]),
        (172, "right", ["ee010500000001bbc0"] * 3 + ["ee01050000000000c0"]),
    ],
)
async def test_native_hold_exact_press_and_cancellation_independent_release(
    clock, key, selected, expected
):
    ctrl, c = make(key)
    await ctrl.start_notify()
    with ctrl.side_scope(selected):
        await ctrl.hold_control("back_up", 250)
    assert frames(c) == expected
    assert all(call.kwargs["response"] for call in c.client.write_gatt_char.call_args_list)
    assert c.client.start_notify.await_count == 1


async def test_burst_seven_writes_and_interrupted_counter(clock):
    ctrl, c = make(172)
    await ctrl.start_notify()
    with ctrl.side_scope("right"):
        await ctrl.program_memory(1)
    assert frames(c) == ["ee020506050000bbc0"] * 3 + ["ee0205aa000000bbc0"] * 4
    c.client.write_gatt_char.reset_mock()
    ctrl._burst.count = 2
    await ctrl.preset_flat()
    assert frames(c) == ["ee010508000000aac0"] + ["ee010500000000aac0"] * 4


@pytest.mark.parametrize(
    "key,selected,expected",
    [
        (46, None, "01010000000000"),
        (51, "right", "01010000000000"),
        (135, None, "ee01054000000000c0"),
        (140, None, "ee010540000000aac0"),
        (140, "left", "ee010540000000aac0"),
        (140, "right", "ee010540000000bbc0"),
    ],
)
@pytest.mark.parametrize("recall", ["preset", "memory"])
async def test_explicit_stop_cancels_automatic_movement(clock, key, selected, expected, recall):
    ctrl, c = make(key)
    await ctrl.start_notify()
    with ctrl.side_scope(selected):
        if recall == "preset":
            await ctrl.preset_zero_g()
        else:
            await ctrl.preset_memory(1)
        c.client.write_gatt_char.reset_mock()
        c.cancel_command.set()
        await ctrl.stop_all()
    sent = frames(c)
    assert len(sent) == 1
    # P1 serials depend on the preceding recall, but the STOP payload is fixed.
    assert (sent[0][2:] if ctrl.model.format == "p1" else sent[0]) == expected


@pytest.mark.parametrize("key", [46, 51, 135, 140])
@pytest.mark.parametrize("movement", ["flat", "memory", "manual", "stop"])
async def test_superseded_preset_is_recalled_on_first_press(clock, key, movement):
    ctrl, c = make(key)
    await ctrl.start_notify()
    with ctrl.side_scope("left"):
        await ctrl.preset_zero_g()
        first = frames(c)[0]
        if movement == "flat":
            await ctrl.preset_flat()
        elif movement == "memory":
            await ctrl.preset_memory(1)
        elif movement == "manual":
            await ctrl.move_axis("back", True, 10)
        else:
            await ctrl.stop_all()
        c.client.write_gatt_char.reset_mock()
        await ctrl.preset_zero_g()
    # P1 serials advance, while the command and parameters must match the recall.
    assert frames(c)[0][2:] == first[2:]


@pytest.mark.parametrize("key", [51, 140])
async def test_side_movement_preserves_other_sides_preset_toggle(clock, key):
    ctrl, c = make(key)
    await ctrl.start_notify()
    with ctrl.side_scope("right"):
        await ctrl.preset_zero_g()
    with ctrl.side_scope("left"):
        await ctrl.move_axis("back", True, 10)
    c.client.write_gatt_char.reset_mock()
    with ctrl.side_scope("right"):
        await ctrl.preset_zero_g()
    expected = codec.p1(0, 1, 1) if key == 51 else codec.normal(0x40000000, 2)
    assert frames(c)[0][2:] == expected.hex()[2:]


@pytest.mark.parametrize("movement", ["flat", "legs", "seven_motion", "ten_recall"])
async def test_shared_legacy_movement_clears_both_preset_selections(clock, movement):
    ctrl, c = make(51)
    await ctrl.start_notify()
    for side in ("left", "right"):
        with ctrl.side_scope(side):
            await ctrl.preset_zero_g()
    with ctrl.side_scope("left"):
        if movement == "flat":
            await ctrl.preset_flat()
        elif movement == "legs":
            await ctrl.move_axis("legs", True, 10)
        elif movement == "seven_motion":
            await ctrl.execute_request(bed.Request(movement, axis="legs", duration_ms=10))
        else:
            await ctrl.execute_request(bed.Request(movement, value=1))
    assert ctrl._presets == {}


async def test_legacy_irregular_massage_local_state_survives_reconnect(clock):
    ctrl, c = make(52)
    await ctrl.start_notify()
    with ctrl.side_scope("right"):
        await ctrl.massage_action("mode")
        await ctrl.massage_action("head")
    assert frames(c)[-1] == "0301012400000000"
    ctrl.on_disconnect()
    replacement = bed.CheersSleepController(c, app.MODELS[52])
    assert replacement._massage[2] == [2, 1, 1]
    assert replacement._counters is ctrl._counters
    assert replacement._burst is ctrl._burst


@pytest.mark.parametrize("key,query", [(171, True), (172, False), (179, True)])
async def test_sonic_mode_split_exception_skips_follow_up_query(clock, key, query):
    ctrl, c = make(key)
    await ctrl.start_notify()
    await ctrl.hold_control("sonic_switch", 50)
    assert frames(c)[:2] == [
        codec.normal(0xC0C, 1 if key == 172 else 0).hex(),
        codec.normal(0).hex(),
    ]
    assert (codec.query(True).hex() in frames(c)) == query


async def test_shared_settings_do_not_inherit_split_side(clock):
    ctrl, c = make(172)
    await ctrl.start_notify()
    with ctrl.side_scope("right"):
        await ctrl.set_light_color((17, 34, 51))
        await ctrl.set_light_level(100)
        await ctrl.set_sonic_level(60)
    assert (
        frames(c)
        == ["ee02050511223300c0"] * 3
        + ["ee0205aa00000000c0"] * 4
        + ["ee02050a64000000c0"] * 3
        + ["ee0205aa00000000c0"] * 4
        + ["ee02050b033c0000c0"] * 3
        + ["ee0205aa00000000c0"] * 4
    )


async def test_callback_link_ownership_live_state_and_teardown(clock):
    ctrl, c = make(141)
    await ctrl.start_notify()
    callback = c.client.start_notify.call_args.args[1]
    callback(None, bytearray.fromhex("eeb000aa000002020301"))
    assert c.controller_state[UNDER_BED_LIGHTS_ON] is True
    assert c.controller_state[sided(keys.MODE, "left")] == 1
    assert c.controller_state.get(sided(keys.MODE, "right")) is None
    ctrl.on_disconnect()
    callback(None, bytearray.fromhex("eeb000aa000002020301"))
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    old_link = ctrl._link
    ctrl.on_disconnect()
    await ctrl.start_notify()
    await ctrl._release(old_link, codec.normal(0))
    assert frames(c) == []


async def test_auxiliary_screens_actual_p1_sequences_no_dead_thirty_minutes(clock):
    ctrl, c = make(49)
    await ctrl.start_notify()
    await ctrl.execute_request(bed.Request("rgb_commit", 10, (17, 34, 51), 68))
    assert frames(c) == ["010301110a000000", "02010f0544332211"]
    await ctrl.execute_request(bed.Request("snore_setting", 1))
    assert frames(c)[-1] == "0203031101000000"
    await ctrl.execute_request(bed.Request("yb_massage", 2, duration_ms=900))
    assert frames(c)[-1] == "0301020284030000"
    with pytest.raises(ValueError, match="300 or 900"):
        ctrl.validate_request(bed.Request("yb_massage", 2, duration_ms=1800))
    await ctrl.execute_request(bed.Request("newten_motion", duration_ms=20, position=4))
    assert frames(c)[-2:] == ["0401090100000000", "0501080100000000"]


async def test_real_service_all_target_validation_and_capture_before_import(hass, clock):
    from custom_components.adjustable_bed.beds.cheerssleep.services import register_services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    register_services(hass)
    first, c1 = make(172)
    second, c2 = make(135)
    await first.start_notify()
    await second.start_notify()
    targets = []
    for ctrl in (first, second):
        target = MagicMock(spec=AdjustableBedCoordinator)
        target.name = "CheersSleep"
        target.controller_side = None
        target.bed_type = "cheerssleep"
        target.capability_controller = ctrl

        async def execute(command, ctrl=ctrl, **_kwargs):
            await command(ctrl)

        target.async_execute_controller_command = AsyncMock(side_effect=execute)
        targets.append((target, SIDE_BOTH))
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=(targets, []),
    ):
        with pytest.raises(Exception, match="sound level"):
            await hass.services.async_call(
                DOMAIN,
                "cheerssleep",
                {"device_id": ["one", "two"], "operation": "sonic_level", "value": 60},
                blocking=True,
            )
        assert not frames(c1) and not frames(c2)
        await hass.services.async_call(
            DOMAIN,
            "cheerssleep",
            {"device_id": ["one", "two"], "operation": "query"},
            blocking=True,
        )
        assert frames(c1) == ["eeb001aac0"] and frames(c2) == ["eeb00100c0"]


@pytest.mark.parametrize("key", [45, 134, 172])
async def test_configure_and_import_keep_model_profile(hass, key):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.setup_questions import setup_profile

    profile = setup_profile("cheerssleep")
    data = {CONF_BED_TYPE: "cheerssleep", CONF_PRODUCT_TYPE: str(key)}
    settled = profile.settled(data)
    assert {**data, **settled}[CONF_PRODUCT_TYPE] == str(key)
    assert settled["has_massage"] == (
        app.MODELS[key].massage or app.MODELS[key].sonic or app.MODELS[key].as_layout
    )
    entry = MockConfigEntry(domain=DOMAIN, data={**data, "address": "AA:BB:CC:DD:EE:98"})
    entry.add_to_hass(hass)
    # Configure uses the same declared questions/derivation, without scan seeding.
    assert profile.staged(entry.data, {CONF_PRODUCT_TYPE: "174"})[CONF_PRODUCT_TYPE] == "174"
    assert (
        profile.settled(profile.staged(entry.data, {CONF_PRODUCT_TYPE: "174"}))["motor_count"] == 4
    )
    choices = profile.questions[0].choices
    assert callable(choices)
    assert choices(entry.data)[str(key)].startswith(app.MODELS[key].label)


@pytest.mark.parametrize("key", [45, 134])
async def test_real_scheduler_lease_expiry_keeps_release(clock, key):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        CommandKind,
        DeviceCommandScheduler,
        HoldLease,
        command_resources,
    )
    from tests.hold_lease_wire import virtual_clock

    ctrl, c = make(key)
    await ctrl.start_notify()
    scheduler = DeviceCommandScheduler("cheerssleep-test")

    async def run(context):
        c.cancel_command = context.cancel_event
        await ctrl.hold_control("back_up", 100)

    with virtual_clock():
        await scheduler.execute(
            CommandIntent(
                run,
                resources=command_resources("motor:back"),
                kind=CommandKind.HOLD,
                lease=HoldLease(owner="test", generation=1, action="back_up", duration_s=0.35),
            )
        )
    assert frames(c)[-1] == ("0301000100000000" if key == 45 else "ee01050000000000c0")


async def test_as_rgb_light_uses_color_page_offset(clock):
    ctrl, c = make(153)
    await ctrl.start_notify()
    callback = c.client.start_notify.call_args.args[1]
    # The position page reads byte8 (set here); the RGB light follows byte16.
    callback(None, bytearray.fromhex("eed00000112233640100003c0100000000"))
    assert c.controller_state[UNDER_BED_LIGHTS_ON] is False
    assert c.controller_state.get(keys.SONIC_LEVEL) is None


@pytest.mark.parametrize("key", [171, 174])
def test_neck_pages_do_not_gain_unshipped_all_axis_controls(key):
    ctrl, _ = make(key)
    assert "all_up" not in ctrl.held_control_options
    assert not any(spec.key == "cheerssleep_all_up" for spec in ctrl.controller_button_specs)
    with pytest.raises(NotImplementedError, match="actuator"):
        ctrl._motion("all", True)


@pytest.mark.parametrize(
    "key,expected", [(134, []), (140, ["eeb001aac0"]), (172, ["eed00100c0", "eed00100c0"])]
)
async def test_actual_startup_queries_and_unscoped_navigation(clock, key, expected):
    ctrl, c = make(key)
    await ctrl.async_on_connect(MagicMock())
    assert frames(c) == expected


async def test_split_position_and_color_toggle_keep_both_caller_scopes(clock):
    ctrl, c = make(172)
    await ctrl.start_notify()
    with ctrl.side_scope("right"):
        await ctrl.execute_request(bed.Request("position_light_toggle"))
        await ctrl.execute_request(bed.Request("color_light_toggle"))
    assert (
        frames(c)
        == ["ee010500020000bbc0"] * 3
        + ["ee010500000000bbc0"] * 4
        + ["ee01050002000000c0"] * 3
        + ["ee01050000000000c0"] * 4
    )


@pytest.mark.parametrize(
    "operation", ["sonic_mode_1", "color_light_toggle", "position_light_toggle", "preset_zero_g"]
)
async def test_real_ha_native_child_target_keeps_right_side_and_rejects_conflict(
    hass, clock, operation
):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.const import CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.paired_devices import (
        async_register_children,
        side_identifier,
    )
    from custom_components.adjustable_bed.services import _resolve_sided_targets
    from tests.test_paired_setup import LEFT_ADDR, _paired_entry

    key = 51 if operation == "preset_zero_g" else 172
    entry = _paired_entry(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            "address": LEFT_ADDR,
            CONF_BED_TYPE: "cheerssleep",
            CONF_PRODUCT_TYPE: str(key),
        },
    )
    inner = AdjustableBedCoordinator(hass, entry)
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    _async_ensure_paired_device_registry(hass, entry, pair)
    async_register_children(hass, pair)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = pair
    registry = dr.async_get(hass)
    right = next(
        child
        for child in dr.async_child_entries_for_config_entry(registry, entry.entry_id)
        if side_identifier(pair, "right") in child.identifiers
    )
    entry.mock_state(hass, ConfigEntryState.LOADED)
    try:
        assert _resolve_sided_targets(hass, [right.id], None)[0] == [(pair, "right")]
        with raises_key("side_selection_conflict", ServiceValidationError):
            _resolve_sided_targets(hass, [right.id], "left")
        from custom_components.adjustable_bed.beds.cheerssleep.services import register_services

        template, transport = make(key)
        inner._client = transport.client
        live = bed.CheersSleepController(inner, app.MODELS[key])
        inner._controller = live
        await live.start_notify()

        async def execute(command, **_kwargs):
            await command(live)

        inner.async_execute_controller_command = AsyncMock(side_effect=execute)
        if operation == "preset_zero_g":
            from custom_components.adjustable_bed.button import (
                BUTTON_DESCRIPTIONS,
                PairedBedCombinedButton,
            )

            button = PairedBedCombinedButton(
                pair, next(d for d in BUTTON_DESCRIPTIONS if d.key == "preset_zero_g")
            )
            button.hass = hass
            await button.async_press()
            assert frames(transport) == ["0201136500000000", "0301236500000000"]
            await button.async_press()
            assert frames(transport)[2:] == ["0401010000000000", "0501010000000000"]
            return
        register_services(hass)
        parent = registry.async_get_device_by_identifier(
            next(iter(pair.device_info["identifiers"])), entry.entry_id
        )
        assert parent is not None
        target_id = right.id if operation == "sonic_mode_1" else parent.id
        data = {"device_id": [target_id], "operation": operation}
        if operation != "sonic_mode_1":
            data["side"] = "both"
        await hass.services.async_call(
            DOMAIN,
            "cheerssleep",
            data,
            blocking=True,
        )
        if operation == "sonic_mode_1":
            expected = ["ee0105000000ccbbc0"] * 3 + ["ee010500000000bbc0"] * 4
        elif operation == "position_light_toggle":
            expected = (
                ["ee010500020000aac0"] * 3
                + ["ee010500000000aac0"] * 4
                + ["ee010500020000bbc0"] * 3
                + ["ee010500000000bbc0"] * 4
            )
        else:
            expected = ["ee01050002000000c0"] * 3 + ["ee01050000000000c0"] * 4
        assert frames(transport) == expected
        if operation == "color_light_toggle":
            # A later action must still toggle, even before hardware feedback arrives.
            await hass.services.async_call(DOMAIN, "cheerssleep", data, blocking=True)
            assert frames(transport) == expected * 2
        assert live.commands_share_timer
        assert not pair._lanes.native_both
        assert [side for side, _ in pair.targets_for("both")] == ["left", "right"]
    finally:
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await pair.async_shutdown()


@pytest.mark.parametrize("key", [51, 52])
@pytest.mark.parametrize("motor", ["legs", "back", "lumbar"])
@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("side", ["left", "right", "both"])
@pytest.mark.parametrize("connection_state", ["connected", "offline", "disconnect_after_first"])
@pytest.mark.parametrize("service", ["timed_move", "hold_control"])
async def test_native_p1_movement_runs_shared_foot_once(
    hass, clock, key, motor, direction, side, connection_state, service
):
    await _exercise_native_p1_movement(
        hass, clock, key, motor, direction, side, connection_state, service
    )


@pytest.mark.parametrize("key", [51, 52])
@pytest.mark.parametrize(
    "operation,motor",
    [
        ("seven_motion", "legs"),
        ("seven_motion", "back"),
        ("seven_motion", "lumbar"),
        ("ten_motion", "all"),
        ("ten_motion", "back"),
        ("newten_motion", "legs"),
        ("newten_motion", "lumbar"),
    ],
)
async def test_native_auxiliary_actions_run_shared_movement_once(hass, clock, key, operation, motor):
    await _exercise_native_p1_movement(
        hass, clock, key, motor, "up", "both", "connected", operation
    )


async def _exercise_native_p1_movement(
    hass, clock, key, motor, direction, side, connection_state, service
):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.const import CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_paired_setup import LEFT_ADDR, _paired_entry

    entry = _paired_entry(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            "address": LEFT_ADDR,
            CONF_BED_TYPE: "cheerssleep",
            CONF_PRODUCT_TYPE: str(key),
        },
    )
    inner = AdjustableBedCoordinator(hass, entry)
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    _async_ensure_paired_device_registry(hass, entry, pair)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = pair
    parent = dr.async_get(hass).async_get_device_by_identifier(
        next(iter(pair.device_info["identifiers"])), entry.entry_id
    )
    assert parent is not None
    entry.mock_state(hass, ConfigEntryState.LOADED)
    try:
        _, transport = make(key)
        inner._client = transport.client
        live = bed.CheersSleepController(inner, app.MODELS[key])
        inner._controller = live
        await live.start_notify()
        if connection_state == "offline":
            inner._offline_controller = bed.CheersSleepController(inner, app.MODELS[key])
            inner._controller = None
            transport.client.is_connected = False

        command_count = 0

        async def connect(reset_timer=True):
            inner._controller = live
            transport.client.is_connected = True
            return True

        async def execute(command, **_kwargs):
            nonlocal command_count
            await connect()
            await command(live)
            command_count += 1
            if connection_state == "disconnect_after_first" and command_count == 1:
                inner._controller = None
                inner._offline_controller = None
                transport.client.is_connected = False

        inner.async_ensure_connected = AsyncMock(side_effect=connect)
        inner.async_execute_controller_command = AsyncMock(side_effect=execute)
        await async_register_services(hass)
        fields = (
            {"motor": motor, "direction": direction, "duration_ms": 1000}
            if service == "timed_move"
            else {"control": f"{motor}_{direction}", "duration": 1}
            if service == "hold_control"
            else {
                "operation": service,
                "axis": motor,
                "position": ("all", "back", "legs", "lumbar").index(motor) + 1,
                "up": direction == "up",
                "duration_ms": 1000,
            }
        )
        for _ in range(2):
            await hass.services.async_call(
                DOMAIN,
                service if service in ("timed_move", "hold_control") else "cheerssleep",
                {
                    "device_id": [parent.id],
                    **fields,
                    "side": side,
                },
                blocking=True,
            )
        # Independent numeric caller values from the frozen P1 vectors.
        ordinary = service in ("ten_motion", "newten_motion")
        codes = ({
            "all": {"left": 0x110, "right": 0x110},
            "back": {"left": 0x101, "right": 0x101},
            "legs": {"left": 0x105, "right": 0x105},
            "lumbar": {"left": 0x109, "right": 0x109},
        } if ordinary else {
            "legs": {"left": 0x640D, "right": 0x640D},
            "back": {"left": 0x6401, "right": 0x6404},
            "lumbar": {"left": 0x6407, "right": 0x640A},
        })[motor]
        sides = ["left", "right"] if side == "both" and motor != "legs" and not ordinary else [side]
        expected = []
        for selected in sides:
            up = codes["left" if selected == "both" else selected]
            expected.extend([up + (direction == "down"), 1 if ordinary and motor == "all" else up - 1])
        if service in ("timed_move", "hold_control"):
            assert command_count == len(sides) * 2
        assert [
            int.from_bytes(bytes.fromhex(frame)[2:4], "little") for frame in frames(transport)
        ] == expected * 2
        assert clock[0] == len(sides) * 2
    finally:
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await pair.async_shutdown()


async def test_conditional_seven_local_sleeper_and_child_conflict(clock):
    ctrl, c = make(45)
    await ctrl.start_notify()
    await ctrl.execute_request(
        bed.Request("seven_motion", duration_ms=10, axis="back", sleeper="right")
    )
    assert frames(c) == ["0201046400000000", "0301036400000000"]
    with ctrl.side_scope("left"), pytest.raises(ValueError, match="other side"):
        ctrl.validate_request(bed.Request("seven_motion", sleeper="right"))


def test_legacy_remacro_keyword_api_keeps_the_proven_encoder_contract():
    from custom_components.adjustable_bed.beds.remacro.protocol import build_frame

    assert build_frame(serial=2, pid=1, code=257, parameter=0).hex() == "0201010100000000"


@pytest.mark.parametrize("key", [171, 172])
async def test_sonic_cancel_preserves_release_then_only_proven_followup(clock, key):
    ctrl, c = make(key)
    await ctrl.start_notify()

    async def cancel_after_write(*_args, **_kwargs):
        c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel_after_write
    await ctrl.hold_control("sonic_switch", 500)
    assert frames(c)[1] == "ee01050000000000c0"
    assert frames(c)[2:] == (["eed00100c0"] if key == 171 else [])


async def test_replaced_controller_cannot_write_release_or_publish_on_same_client(clock):
    ctrl, c = make(141)
    await ctrl.start_notify()
    callback = c.client.start_notify.call_args.args[1]
    old = ctrl._link
    c.controller = bed.CheersSleepController(c, app.MODELS[141])
    await ctrl._release(old, codec.normal(0))
    callback(None, bytearray.fromhex("eeb000aa000002030201"))
    assert frames(c) == []
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    with pytest.raises(ConnectionError, match="session changed"):
        await ctrl.preset_flat()


@pytest.mark.parametrize("key", [45, 134])
async def test_finite_native_press_respects_ha_count_without_legacy_refresh(clock, key):
    ctrl, c = make(key)
    c.motor_pulse_count = 3
    await ctrl.start_notify()
    await ctrl.move_back_up()
    assert clock[0] == pytest.approx(0.3)
    assert len(frames(c)) == (2 if key == 45 else 4)


async def test_wave_mode_two_retains_levels_while_mode_one_initializes(clock):
    ctrl, c = make(52)
    await ctrl.start_notify()
    await ctrl.massage_action("mode")
    await ctrl.massage_action("head")
    await ctrl.massage_action("mode")
    assert ctrl._massage[1] == [2, 1, 2]
    assert frames(c)[-1] == "0401310200000000"


async def test_legacy_light_toggle_retains_local_intent_across_ha_handoff(clock):
    ctrl, c = make(46)
    await ctrl.start_notify()
    await ctrl.lights_toggle()
    await ctrl.stop_notify()
    replacement = bed.CheersSleepController(c, app.MODELS[46])
    c.controller = replacement
    await replacement.start_notify()
    await replacement.lights_toggle()
    assert frames(c) == ["0201010500000000", "0301000500000000"]


@pytest.mark.parametrize("row", MODELS, ids=lambda row: row["id"])
def test_every_exposed_axis_uses_its_own_accepted_caller_catalog(row):
    from tests.cheerssleep_vectors import NUMERIC

    ctrl, _ = make(row["model_key"])
    expected = {v["expected_bytes"] for v in NUMERIC if v["id"].split("-")[0] in row["command_ids"]}
    for axis in ctrl.model.axes:
        for up in (False, True):
            for frame in ctrl._motion(axis, up):
                compared = bytes((2,)) + frame[1:] if ctrl.model.format == "p1" else frame
                assert compared.hex() in expected, (row["id"], axis, compared.hex())


@pytest.mark.parametrize("key", [135, 141])
@pytest.mark.parametrize("desired", [False, True])
async def test_native_p2_light_desired_state_requires_current_feedback(hass, clock, key, desired):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.light import AdjustableBedOnOffLight, _light_entities_for

    ctrl, c = make(key)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    runtime = entity_runtime(ctrl, c)
    light = _light_entities_for(hass, runtime)[0]
    assert isinstance(light, AdjustableBedOnOffLight)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    await light.async_added_to_hass()
    callback = c.client.start_notify.call_args.args[1]

    def report(enabled, selected=1):
        data = bytearray.fromhex("eeb00000000002020300")
        data[3] = 0xBB if selected == 2 else 0xAA
        data[9] = int(enabled)
        callback(None, data)

    action = light.async_turn_on if desired else light.async_turn_off
    try:
        with raises_key("light_state_unknown", ServiceValidationError):
            await action()
        assert frames(c) == []
        if ctrl.model.split:
            report(not desired, selected=2)
            with raises_key("light_state_unknown", ServiceValidationError):
                await action()
            assert light.is_on is None
        report(desired)
        await action()
        assert frames(c) == [] and light.is_on is desired
        report(not desired)
        await action()
        selected = 1 if ctrl.model.split else 0
        expected = [codec.normal(0x20000, selected).hex()] * 3 + [
            codec.normal(0, selected).hex()
        ] * 4
        assert frames(c) == expected
        assert light.is_on is not desired  # No optimistic state after the write.
        with raises_key("light_state_unknown", ServiceValidationError):
            await action()
        report(not desired)  # A stale pre-toggle echo cannot admit a second toggle.
        with raises_key("light_state_unknown", ServiceValidationError):
            await action()
        assert frames(c) == expected
        report(desired)
        await action()
        assert frames(c) == expected and light.is_on is desired
        ctrl.on_disconnect()
        await ctrl.start_notify()
        report(not desired)  # Callback from the old physical session is ignored.
        with raises_key("light_state_unknown", ServiceValidationError):
            await action()
        assert frames(c) == expected
    finally:
        await light.async_will_remove_from_hass()


@pytest.mark.parametrize("key", [51, 52, 172])
async def test_standalone_split_movement_targets_left_side(clock, key):
    ctrl, c = make(key)
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    await ctrl.move_back_up()
    if key == 172:
        assert frames(c)[0] == "ee010500000001aac0"
    else:
        assert frames(c) == ["0201016400000000", "0301006400000000"]


@pytest.mark.parametrize("key", [153, 172])
async def test_d0_remote_feedback_reaches_native_rgb_light_and_invalidates(hass, clock, key):
    from custom_components.adjustable_bed.light import AdjustableBedLight, _light_entities_for

    ctrl, c = make(key)
    await ctrl.start_notify()
    runtime = entity_runtime(ctrl, c)
    light = _light_entities_for(hass, runtime)[0]
    assert isinstance(light, AdjustableBedLight)
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    light.async_get_last_state = AsyncMock(return_value=None)
    await light.async_added_to_hass()
    callback = c.client.start_notify.call_args.args[1]
    data = bytearray.fromhex("eed00000112233320100003c0100000001")
    try:
        callback(None, data)
        assert light.is_on is True
        assert light.rgb_color == (17, 34, 51)
        assert light.brightness == 127  # Accepted percent50 -> HA0..255, no raw scaling guess.
        assert c.controller_state[UNDER_BED_LIGHTS_RGB] == (17, 34, 51)
        assert c.controller_state[LIGHT_LEVEL] == 50
        data[4:8] = bytes((255, 0, 128, 201))
        callback(None, data)
        assert light.rgb_color == (255, 0, 128)
        assert c.controller_state[LIGHT_LEVEL] is None and light.brightness is None
        data[7] = 0
        callback(None, data)
        assert light.brightness == 0
        data[7] = 100
        callback(None, data)
        assert light.brightness == 255
        ctrl.on_disconnect()
        assert c.controller_state[UNDER_BED_LIGHTS_RGB] is None
        assert c.controller_state[LIGHT_LEVEL] is None
        assert light.rgb_color is None and light.brightness is None
        callback(None, data)
        assert light.rgb_color is None and light.brightness is None
    finally:
        await light.async_will_remove_from_hass()


@pytest.mark.parametrize("maximum", [6, 100])
async def test_shared_light_level_callback_handles_unknown_zero_and_positive(hass, maximum):
    from custom_components.adjustable_bed.light import _light_entities_for

    ctrl, c = make(153)
    light = _light_entities_for(hass, entity_runtime(ctrl, c))[0]
    light.async_write_ha_state = MagicMock()
    light._light_level_max = maximum
    for level, expected in ((1, 255 // maximum), (None, None), (0, 0), (maximum, 255)):
        light._handle_light_state(ControllerState({LIGHT_LEVEL: level}))
        assert light.brightness == expected
    # An update without a level observation must retain the last known brightness.
    light._handle_light_state(ControllerState({UNDER_BED_LIGHTS_RGB: (11, 22, 33)}))
    assert light.brightness == 255 and light.rgb_color == (11, 22, 33)


@pytest.mark.parametrize("key", [51, 52])
@pytest.mark.parametrize("operation", ["ten_motion", "newten_motion"])
@pytest.mark.parametrize("position", [1, 2, 3, 4])
@pytest.mark.parametrize("up", [False, True])
async def test_registered_ten_services_keep_ordinary_arrays_on_split_models(
    hass, clock, key, operation, position, up
):
    from custom_components.adjustable_bed.beds.cheerssleep.services import register_services
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl, c = make(key)
    await ctrl.start_notify()
    target = MagicMock(spec=AdjustableBedCoordinator)
    target.name = "CheersSleep"
    target.controller_side = None
    target.bed_type = "cheerssleep"
    target.capability_controller = ctrl

    async def execute(command, **_kwargs):
        await command(ctrl)

    target.async_execute_controller_command = AsyncMock(side_effect=execute)
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "cheerssleep",
            {
                "device_id": ["main"],
                "operation": operation,
                "position": position,
                "up": up,
                "duration_ms": 10,
            },
            blocking=True,
        )
    # C0321-C0324 and C0971-C0974: auxiliary screen owns these ordinary arrays.
    press = ((272, 257, 261, 265) if up else (273, 258, 262, 266))[position - 1]
    release = (1, 256, 260, 264)[position - 1]
    assert frames(c) == [codec.p1(2, 1, press).hex(), codec.p1(3, 1, release).hex()]
    c.client.write_gatt_char.reset_mock()
    await ctrl.execute_request(bed.Request("seven_motion", axis="back", duration_ms=10))
    assert frames(c) == [codec.p1(4, 1, 0x6401).hex(), codec.p1(5, 1, 0x6400).hex()]
    c.client.write_gatt_char.reset_mock()
    await ctrl.move_back_up()
    assert frames(c) == [codec.p1(6, 1, 0x6401).hex(), codec.p1(7, 1, 0x6400).hex()]


@pytest.mark.parametrize("key", [153, 172])
async def test_native_rgb_turn_on_uses_guarded_power_before_color(hass, clock, key):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.light import _light_entities_for

    ctrl, c = make(key)
    await ctrl.start_notify()
    light = _light_entities_for(hass, entity_runtime(ctrl, c))[0]
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    light.async_get_last_state = AsyncMock(return_value=None)
    await light.async_added_to_hass()
    try:
        with raises_key("light_state_unknown", ServiceValidationError):
            await light.async_turn_on(rgb_color=(9, 8, 7))
        assert not frames(c) and not light.is_on
        callback = c.client.start_notify.call_args.args[1]
        data = bytearray.fromhex("eed00000112233000100003c0100000000")
        callback(None, data)
        assert light.is_on is False
        await light.async_turn_on(rgb_color=(9, 8, 7))
        assert frames(c) == (
            ["ee01050002000000c0"] * 3
            + ["ee01050000000000c0"] * 4
            + ["ee02050509080700c0"] * 3
            + ["ee0205aa00000000c0"] * 4
        )
        with raises_key("light_state_unknown", ServiceValidationError):
            await light.async_turn_on(rgb_color=(9, 8, 7))
        assert len(frames(c)) == 14
        data[4:7] = bytes((9, 8, 7))
        data[16] = 1
        callback(None, data)
        assert light.is_on is True and light.rgb_color == (9, 8, 7)
        c.client.write_gatt_char.reset_mock()
        await light.async_turn_on(rgb_color=(9, 8, 7))
        assert frames(c) == ["ee02050509080700c0"] * 3 + ["ee0205aa00000000c0"] * 4
    finally:
        await light.async_will_remove_from_hass()


@pytest.mark.parametrize("key", [140, 141])
async def test_native_paired_lights_keep_independent_feedback_and_action_sides(hass, clock, key):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.const import CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.light import _light_entities_for
    from custom_components.adjustable_bed.paired_coordinator import (
        SingleAddressPairedCoordinator,
        entity_runtimes,
    )
    from custom_components.adjustable_bed.paired_devices import async_register_children
    from tests.test_paired_setup import LEFT_ADDR, _paired_entry

    entry = _paired_entry(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            "address": LEFT_ADDR,
            CONF_BED_TYPE: "cheerssleep",
            CONF_PRODUCT_TYPE: str(key),
        },
    )
    inner = AdjustableBedCoordinator(hass, entry)
    inner._schedule_controller_state_refresh = MagicMock()
    _, transport = make(key)
    inner._client = transport.client
    ctrl = bed.CheersSleepController(inner, app.MODELS[key])
    inner._controller = ctrl
    await ctrl.start_notify()
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    _async_ensure_paired_device_registry(hass, entry, pair)
    async_register_children(hass, pair)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    async def execute(command, **_kwargs):
        await command(ctrl)

    inner.async_execute_controller_command = AsyncMock(side_effect=execute)
    lights = {
        runtime.entity_side: _light_entities_for(hass, runtime)[0]
        for runtime in entity_runtimes(pair)
    }
    for light in lights.values():
        light.hass = hass
        light.async_write_ha_state = MagicMock()
        await light.async_added_to_hass()
    callback = transport.client.start_notify.call_args.args[1]

    def report(tag, enabled):
        data = bytearray.fromhex("eeb00000000002020300")
        data[3], data[9] = tag, int(enabled)
        callback(None, data)

    try:
        assert lights["left"].is_on is None and lights["right"].is_on is None
        report(0xAA, False)
        report(0xBB, True)
        assert lights["left"].is_on is False and lights["right"].is_on is True
        assert inner.controller_state[UNDER_BED_LIGHTS_ON] is False
        report(0, False)  # An unowned/wrong-side report cannot overwrite either child.
        assert lights["left"].is_on is False and lights["right"].is_on is True
        transport.client.write_gatt_char.reset_mock()
        await lights["left"].async_turn_on()
        await lights["right"].async_turn_off()
        assert frames(transport) == (
            ["ee010500020000aac0"] * 3
            + ["ee010500000000aac0"] * 4
            + ["ee010500020000bbc0"] * 3
            + ["ee010500000000bbc0"] * 4
        )
        report(0xAA, False)  # Stale left echo must not acknowledge the pending toggle.
        with raises_key("light_state_unknown", ServiceValidationError):
            await lights["left"].async_turn_on()
        assert lights["right"].is_on is True
        report(0xAA, True)
        report(0xBB, False)
        assert lights["left"].is_on is True and lights["right"].is_on is False
        assert inner.controller_state[UNDER_BED_LIGHTS_ON] is True  # Unsided mirrors left.
        ctrl.on_disconnect()
        assert lights["left"].is_on is None and lights["right"].is_on is None
        await ctrl.start_notify()
        report(0xBB, True)  # Old callback is tied to the previous physical link.
        assert lights["left"].is_on is None and lights["right"].is_on is None
        with raises_key("light_state_unknown", ServiceValidationError):
            await lights["right"].async_turn_on()
    finally:
        for light in lights.values():
            await light.async_will_remove_from_hass()
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await pair.async_shutdown()


async def test_native_paired_rgb_off_waits_for_shared_receiver_feedback(hass, clock):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.const import CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.light import _light_entities_for
    from custom_components.adjustable_bed.paired_coordinator import (
        SingleAddressPairedCoordinator,
        entity_runtimes,
    )
    from custom_components.adjustable_bed.paired_devices import async_register_children
    from tests.test_paired_setup import LEFT_ADDR, _paired_entry

    entry = _paired_entry(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
            "address": LEFT_ADDR,
            CONF_BED_TYPE: "cheerssleep",
            CONF_PRODUCT_TYPE: "172",
        },
    )
    inner = AdjustableBedCoordinator(hass, entry)
    inner._schedule_controller_state_refresh = MagicMock()
    _, transport = make(172)
    inner._client = transport.client
    ctrl = bed.CheersSleepController(inner, app.MODELS[172])
    inner._controller = ctrl
    await ctrl.start_notify()
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    _async_ensure_paired_device_registry(hass, entry, pair)
    async_register_children(hass, pair)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    command_lock = asyncio.Lock()

    async def execute(command, **_kwargs):
        async with command_lock:
            await command(ctrl)

    inner.async_execute_controller_command = AsyncMock(side_effect=execute)
    lights = {
        runtime.entity_side: _light_entities_for(hass, runtime)[0]
        for runtime in entity_runtimes(pair)
    }
    for light in lights.values():
        light.hass = hass
        light.async_write_ha_state = MagicMock()
        await light.async_added_to_hass()
    callback = transport.client.start_notify.call_args.args[1]
    data = bytearray.fromhex("eed00000112233000100003c0100000001")
    toggle = ["ee01050002000000c0"] * 3 + ["ee01050000000000c0"] * 4
    try:
        with raises_key("light_state_unknown", ServiceValidationError):
            await lights["left"].async_turn_off()
        assert not frames(transport)
        callback(None, data)
        assert all(light.is_on for light in lights.values())
        await lights["left"].async_turn_off()
        assert frames(transport) == toggle
        with raises_key("light_state_unknown", ServiceValidationError):
            await lights["right"].async_turn_off()
        callback(None, data)  # An old on report cannot acknowledge the pending off.
        with raises_key("light_state_unknown", ServiceValidationError):
            await lights["right"].async_turn_off()
        assert frames(transport) == toggle
        data[16] = 0
        callback(None, data)
        assert all(light.is_on is False for light in lights.values())
        for light in lights.values():
            await light.async_turn_off()
        assert frames(transport) == toggle
        ctrl.on_disconnect()
        await ctrl.start_notify()
        data[16] = 1
        callback(None, data)  # Previous-session feedback cannot re-enable either light.
        with raises_key("light_state_unknown", ServiceValidationError):
            await lights["right"].async_turn_off()
        assert frames(transport) == toggle
    finally:
        for light in lights.values():
            await light.async_will_remove_from_hass()
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await pair.async_shutdown()


async def test_p1_sleep_entities_follow_their_side(clock):
    ctrl, _ = make(51)

    def names() -> set[str]:
        return {spec.key for spec in ctrl.controller_state_sensor_specs}

    assert {"cheerssleep_left_heart", "cheerssleep_right_heart"} <= names()
    with ctrl.side_scope("right"):
        assert "cheerssleep_left_heart" not in names()
        assert {spec.key for spec in ctrl.controller_state_binary_sensor_specs} == {
            "cheerssleep_right_on_bed",
            "cheerssleep_right_asleep",
        }


async def test_reconfigure_asks_the_model_again(hass):
    from homeassistant.config_entries import SOURCE_RECONFIGURE
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=5,
        data={CONF_BED_TYPE: "cheerssleep", CONF_PRODUCT_TYPE: "45", "address": "AA:BB:CC:DD:EE:98"},
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    result = await flow.async_step_reconfigure()
    picker = next(v for k, v in result["data_schema"].schema.items() if k == CONF_BED_TYPE)
    label = next(label for label, value in picker.rows().items() if value == "cheerssleep")
    result = await flow.async_step_reconfigure_bed_type({CONF_BED_TYPE: label})
    assert result["type"] == "form"
    assert CONF_PRODUCT_TYPE in {str(field) for field in result["data_schema"].schema}


async def test_discovered_bed_starts_with_its_advertised_model(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import finish_new_bed, start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    info = MagicMock()
    info.name = "CheersSleep"
    info.address = "AA:BB:CC:DD:EE:98"
    info.service_uuids = [codec.SERVICE]
    info.manufacturer_data = {89: bytes((0, 0, 45))}  # Model 134.
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "picked", "cheerssleep")
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({})
    await finish_new_bed(flow, result)
    assert flow._finish_with_verify.await_args.args[0][CONF_PRODUCT_TYPE] == "134"


def test_identical_models_show_once_and_a_saved_twin_stays():
    """Entries that differ only in their key show once; other shared names keep theirs."""
    from custom_components.adjustable_bed.const import CONF_PRODUCT_TYPE
    from custom_components.adjustable_bed.setup_questions import (
        _cheerssleep_errors,
        _cheerssleep_models,
    )

    models = _cheerssleep_models({})
    assert models["14"] == "BS200C/BS200P" and "16" not in models
    # A shared name on another command format stays a choice of its own.
    assert {"45", "134"} <= set(models)
    saved = {CONF_PRODUCT_TYPE: "16"}
    assert _cheerssleep_models(saved)["16"] == "BS200C/BS200P"
    assert _cheerssleep_errors(saved) == {}
