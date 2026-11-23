"""Native Instant Comfort routes, entities, services and cancellation."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.instant_comfort.air import (
    LEFT_LUMBAR,
    RIGHT_LUMBAR,
    InstantComfortAir,
)
from custom_components.adjustable_bed.beds.instant_comfort.controller import InstantComfortBase
from custom_components.adjustable_bed.codec import personal_comfort as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.profiles.instant_comfort import MODELS, PROFILES
from tests.test_personal_comfort import make as pc_make
from tests.test_personal_comfort import writes
from tests.test_wire_snapshot import _load_tool


@pytest.fixture
async def clock():
    tool = _load_tool()
    virtual = tool.FakeClock()
    with tool.virtual_time(virtual):
        yield virtual


def make(route="malouf", model="pf4", layout="two"):
    _old, c = pc_make(route, model)
    ctrl = (
        InstantComfortAir(c, PROFILES[route], layout)
        if route in ("anm3", "anm5", "ra")
        else InstantComfortBase(c, PROFILES[route], model)
    )
    c.controller = c.capability_controller = ctrl
    c.entry.data = {
        "bed_type": "instant_comfort",
        "protocol_variant": route,
        "product_type": layout if route == "anm5" else model,
    }
    return ctrl, c


@pytest.mark.parametrize("route", PROFILES)
async def test_factory_keeps_concrete_profile(hass, route):
    _ctrl, c = make(route)
    c.hass = hass
    ctrl = await create_controller(c, "instant_comfort", route, c.client)
    assert ctrl.profile is PROFILES[route]
    assert isinstance(
        ctrl, InstantComfortAir if route in ("anm3", "anm5", "ra") else InstantComfortBase
    )


@pytest.mark.parametrize("route", ["malouf", "reverie_v1", "reverie_v2"])
@pytest.mark.parametrize("model", MODELS)
def test_base_model_capabilities(route, model):
    ctrl, _c = make(route, model)
    assert ctrl.has_pillow_support == (route != "reverie_v1" and model in ("pf4", "pf42"))
    assert ctrl.supports_massage == (model in ("pf3", "pf4", "other"))
    assert ctrl.memory_slot_count == (0 if route == "reverie_v1" else 2)
    assert not ctrl.has_lumbar_support
    assert not ctrl.supports_single_address_pairing


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("malouf", ["6e01002493"] * 5),
        ("reverie_v1", ["550154", "55ffaa"]),
        ("reverie_v2", ["01", "00"]),
    ],
)
async def test_native_hold_release(clock, route, expected):
    ctrl, c = make(route)
    await ctrl.hold_control("head_up", 1000)
    assert [frame for _char, frame, _response in writes(c)] == expected


@pytest.mark.parametrize("route", ["reverie_v1", "reverie_v2"])
async def test_cancel_and_release(clock, route):
    ctrl, c = make(route)
    c.client.write_gatt_char.side_effect = lambda *_a, **_kw: c.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_head_up()
    assert writes(c)[-1][1] == ("55ffaa" if route == "reverie_v1" else "00")


async def test_v2_plus_and_minus_reach_same_zones():
    ctrl, c = make("reverie_v2")
    for zone, prefix in (("head", "db801061"), ("foot", "db801060")):
        await ctrl.massage_action(f"massage_{zone}_down")
        assert writes(c)[-1] == (codec.reverie_uuid(prefix), "32", True)


async def test_v2_light_state_is_published_after_delivery():
    ctrl, c = make("reverie_v2")
    await ctrl.set_light(True)
    assert ctrl._light_on is True
    c.client.write_gatt_char.side_effect = ConnectionError("write failed")
    with pytest.raises(ConnectionError):
        await ctrl.set_light(False)
    assert ctrl._light_on is True


@pytest.mark.parametrize("busy", [False, True])
async def test_anm3_ready_and_busy_pending_paths(clock, busy):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}

    async def respond(_char, packet, **_kwargs):
        op = packet[2]
        if op == 0x69:
            ctrl.receive(bytes((0, 0, 0x88 if busy else 0x69)))
        elif op == 1:
            ctrl.receive(bytes((0, 0, 0x85)))

    c.client.write_gatt_char.side_effect = respond
    await ctrl.set_firmness("left", 25)
    assert [bytes.fromhex(frame)[2] for _char, frame, _response in writes(c)] == [
        0x69,
        1,
        0x85,
        0x83,
    ]
    assert ctrl._adjusting is False
    if busy:
        assert clock.now >= 1


async def test_anm3_busy_after_pending_clear_prepares_again(clock):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}
    sent = 0

    async def respond(_char, packet, **_kwargs):
        nonlocal sent
        op = packet[2]
        if op == 0x69:
            ctrl.receive(bytes((0, 0, 0x88)))
        elif op == 1:
            sent += 1
            ctrl.receive(bytes((0, 0, 0x88 if sent == 1 else 0x85)))

    c.client.write_gatt_char.side_effect = respond
    await ctrl.set_firmness("left", 25)
    assert [bytes.fromhex(frame)[2] for _char, frame, _response in writes(c)] == [
        0x69,
        1,
        0x69,
        1,
        0x85,
        0x83,
    ]


async def test_anm3_cancel_drops_pending_instead_of_cross_side_reentry(clock):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}
    c.client.write_gatt_char.side_effect = lambda *_a, **_kw: c.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await ctrl.set_firmness("left", 25)
    c.cancel_command = asyncio.Event()
    c.client.write_gatt_char.side_effect = lambda *_a, **_kw: c.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await ctrl.set_firmness("right", 30)
    assert [bytes.fromhex(frame)[2] for _char, frame, _response in writes(c)] == [0x69, 0x69]
    assert bytes.fromhex(writes(c)[-1][1])[7] == 2


async def test_native_lumbar_number_and_channel_routing(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    assert ctrl.values == {"left": 5, "right": 27}
    assert c.controller_state[LEFT_LUMBAR] == 15
    assert c.controller_state[RIGHT_LUMBAR] == 50
    number = AdjustableBedControllerNumber(c, ctrl.controller_number_specs[-1])
    assert number.native_value == 50

    async def execute(fn, **_kw):
        await fn(ctrl)

    c.async_execute_controller_command = AsyncMock(side_effect=execute)
    await number.async_set_native_value(30)
    c.async_execute_controller_command.assert_awaited_once()
    assert bytes.fromhex(writes(c)[0][1]) == b"C>SETP>3>36\n"
    assert all(bytes.fromhex(frame) == b"R>SP\n" for _ch, frame, _r in writes(c)[1:])
    ctrl.on_disconnect()
    assert number.native_value is None


async def test_layout_mismatch_rejects_before_target(clock):
    ctrl, c = make("anm5", layout="two")
    ctrl.receive(b"RBD>SP>00000000102142")
    with pytest.raises(ServiceValidationError, match="layout"):
        await ctrl.set_firmness("right", 30)
    assert not writes(c)


async def test_busy_pressure_reply_does_not_replace_values():
    ctrl, _c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    ctrl.receive(b"RBD>SP>00010042424242")
    assert ctrl.values == {"left": 5, "right": 27}
    assert ctrl._lumbar == {"left": 15, "right": 50}


@pytest.mark.parametrize(
    ("route", "product"), [("anm5", "four"), ("malouf", "pf4"), ("reverie_v2", "pf3")]
)
async def test_native_setup_persists_route_and_layout(hass, route, product):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {"bed_type": "instant_comfort"}
    first = await flow.async_step_profile_questions()
    route_schema = first["data_schema"]
    assert route_schema is not None
    route_answer = route_schema({"protocol_variant": route})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        layout = await flow.async_step_profile_questions(route_answer)
        finish.assert_not_awaited()
        product_schema = layout["data_schema"]
        assert product_schema is not None
        product_answer = product_schema({"product_type": product})
        await flow.async_step_profile_questions(product_answer)
    saved = finish.call_args.args[0]
    assert saved["protocol_variant"] == route
    assert saved["product_type"] == product
    assert saved["disable_angle_sensing"] is True


async def test_native_combined_sequence(hass, clock):
    from pytest_homeassistant.common import MockConfigEntry

    from tests.test_personal_comfort_services import call, close, pair

    parent, old = pair()
    controllers = []
    for child, previous in zip(parent.children.values(), old, strict=True):
        ctrl = InstantComfortBase(child, PROFILES[previous.profile.key], previous.model)
        child.controller = child.capability_controller = ctrl
        child.bed_type = "instant_comfort"
        child.entry = MockConfigEntry(
            domain="adjustable_bed", data={**child.entry.data, "bed_type": "instant_comfort"}
        )
        controllers.append(ctrl)
    try:
        await call(hass, parent, "full_body_massage")
        assert [
            call.args[1].hex() for call in controllers[0].client.write_gatt_char.call_args_list
        ] == ["6e01004cbb", "6e01004ebd"]
        assert [
            call.args[1].hex() for call in controllers[1].client.write_gatt_char.call_args_list
        ] == ["32", "32"]
    finally:
        await close(parent)


async def test_anm5_native_startup_and_disconnect(clock):
    ctrl, c = make("anm5", layout="four")
    await ctrl.start_notify()
    assert [bytes.fromhex(frame) for _char, frame, _response in writes(c)] == [
        b"C>TPCH>0\n",
        b"C>TPCH>0\n",
        b"R>SP\n",
    ]
    notify = c.client.start_notify.call_args.args[1]
    notify(None, bytearray(b"RBD>SP>00000000102142"))
    assert c.controller_state[RIGHT_LUMBAR] == 50
    await ctrl.stop_notify()
    notify(None, bytearray(b"RBD>SP>00000042424242"))
    assert c.controller_state[RIGHT_LUMBAR] is None
    assert ctrl._initial is None
    assert not ctrl._followups


@pytest.mark.parametrize(
    ("route", "recall", "save"),
    [("malouf", "6e01002f9e", "6e01002c9b"), ("reverie_v2", "05", "85")],
)
async def test_live_memory_on_selected_base(route, recall, save):
    ctrl, c = make(route)
    await ctrl.preset_memory(2)
    await ctrl.program_memory(2)
    assert [frame for _char, frame, _response in writes(c)] == [recall, save]


@pytest.mark.parametrize(
    ("name", "services"),
    [
        ("ANM-air", [codec.bluetooth_uuid("ffe5")]),
        ("2618B-unit", [codec.bluetooth_uuid("ffe0")]),
        ("RA", [codec.RA_SERVICE]),
        ("Base", [codec.V1_SERVICE]),
    ],
)
def test_discovery_preserves_explicit_app_choice(name, services):
    from custom_components.adjustable_bed.detection import (
        detect_bed_type_detailed,
        get_bed_type_options,
    )
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=services))
    assert "instant_comfort" in {result.bed_type, *(result.ambiguous_types or ())}
    assert any(
        "Instant Comfort" in option["label"]
        for option in get_bed_type_options()
        if option["value"] == "instant_comfort"
    )


def test_pair_persists_independent_base_profiles():
    from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data

    left = {
        "address": "AA:BB:CC:DD:EE:01",
        "bed_type": "instant_comfort",
        "protocol_variant": "malouf",
        "product_type": "pf4",
    }
    right = {
        "address": "AA:BB:CC:DD:EE:02",
        "bed_type": "instant_comfort",
        "protocol_variant": "reverie_v2",
        "product_type": "pf3",
    }
    pair = build_pair_entry_data(left, right, name="Bed")
    assert effective_child_data(pair, "left")["protocol_variant"] == "malouf"
    assert effective_child_data(pair, "right")["product_type"] == "pf3"
    with pytest.raises(ValueError, match="bases"):
        build_pair_entry_data(
            left, {**right, "protocol_variant": "anm5", "product_type": "four"}, name="Bed"
        )


@pytest.mark.parametrize("complete", [True, False])
async def test_combined_targets_wait_for_idle_transition(clock, complete):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    targets = []

    async def respond(_char, packet, **_kw):
        if packet.startswith(b"C>SETP>"):
            targets.append(bytes(packet))
            if complete:
                ctrl.receive(b"RBD>SP>00010000102142")
                ctrl.receive(b"RBD>SP>00000000102142")

    c.client.write_gatt_char.side_effect = respond
    if complete:
        await ctrl.set_pressures("right", 30, 25)
        assert targets == [b"C>SETP>2>36\n", b"C>SETP>3>29\n"]
    else:
        with pytest.raises(ServiceValidationError, match="did not finish"):
            await ctrl.set_pressures("right", 30, 25)
        assert targets == [b"C>SETP>2>36\n"]


async def test_native_firmness_service(hass, clock):
    from custom_components.adjustable_bed.beds.instant_comfort.services import register_services
    from custom_components.adjustable_bed.const import DOMAIN

    ctrl, c = make("anm5", layout="four")
    c.hass = hass
    ctrl.receive(b"RBD>SP>00000000102142")

    async def execute(fn, **_kwargs):
        await fn(ctrl)

    async def respond(_char, packet, **_kwargs):
        if packet.startswith(b"C>SETP>"):
            ctrl.receive(b"RBD>SP>00010000102142")
            ctrl.receive(b"RBD>SP>00000000102142")

    c.async_execute_controller_command = AsyncMock(side_effect=execute)
    c.client.write_gatt_char.side_effect = respond
    register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(c, "both")], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "instant_comfort_firmness",
            {"device_id": ["air"], "sleeper": "right", "firmness": 30, "lumbar_firmness": 25},
            blocking=True,
        )
    assert [
        bytes.fromhex(frame)
        for _char, frame, _response in writes(c)
        if bytes.fromhex(frame).startswith(b"C>SETP>")
    ] == [b"C>SETP>2>36\n", b"C>SETP>3>29\n"]


async def test_cancellation_discards_queued_lumbar(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    c.client.write_gatt_char.side_effect = lambda *_a, **_kw: c.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await ctrl.set_pressures("right", 30, 25)
    assert [bytes.fromhex(frame) for _char, frame, _response in writes(c)] == [b"C>SETP>2>36\n"]


@pytest.mark.parametrize("complete", [False, True])
async def test_late_ack_cannot_deliver_unsent_replacement(clock, complete):
    from custom_components.adjustable_bed import command_scheduler as scheduler

    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}
    context = scheduler.CommandContext(
        object(), c.cancel_command, 0, "replacement", "command", None, frozenset({"*"})
    )
    deliveries = []
    target_seen = False

    async def respond(_char, packet, **_kwargs):
        nonlocal target_seen
        if packet[2] == 0x69:
            ctrl.receive(bytes((0, 0, 0x85)))
            if complete:
                ctrl.receive(bytes((0, 0, 0x69)))
        elif packet[2] == 1:
            target_seen = True
            ctrl.receive(bytes((0, 0, 0x85)))
        elif packet[2] == 0x85 and not complete:
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = respond
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(context)
    try:
        with scheduler.delivered(deliveries.append):
            if complete:
                await ctrl.set_firmness("left", 25)
            else:
                with pytest.raises(asyncio.CancelledError):
                    await ctrl.set_firmness("left", 25)
                # Pass cancellation through the shared delivery finalizer.
                raise asyncio.CancelledError
    except asyncio.CancelledError:
        assert not complete
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
    assert target_seen is complete
    assert deliveries == [scheduler.Delivery.SENT if complete else scheduler.Delivery.NONE]


async def test_wrong_layout_idle_cannot_release_lumbar(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")

    async def respond(_char, packet, **_kwargs):
        if packet.startswith(b"C>SETP>"):
            ctrl.receive(b"RBD>SP>00010000102142")
            ctrl.receive(b"RET>SP>0000000042")

    c.client.write_gatt_char.side_effect = respond
    with pytest.raises(ServiceValidationError, match="layout"):
        await ctrl.set_pressures("right", 30, 25)
    targets = [
        bytes.fromhex(frame)
        for _char, frame, _response in writes(c)
        if bytes.fromhex(frame).startswith(b"C>SETP>")
    ]
    assert targets == [b"C>SETP>2>36\n"]


async def test_layout_is_checked_under_write_lock(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    await ctrl._ble_lock.acquire()
    pending = asyncio.create_task(ctrl.set_pressures("right", 30, None))
    await asyncio.sleep(0)
    ctrl.receive(b"RET>SP>0000000042")
    ctrl._ble_lock.release()
    with pytest.raises(ServiceValidationError, match="layout"):
        await pending
    assert not writes(c)


def test_app_hint_preserves_confident_receiver_and_accessory_exclusion():
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    receiver = detect_bed_type_detailed(
        _make_service_info(name="Reverie", service_uuids=[codec.V1_SERVICE])
    )
    assert "instant_comfort" in receiver.ambiguous_types
    assert _confident_auto_detect(receiver) == receiver.bed_type == "reverie"
    accessory = detect_bed_type_detailed(
        _make_service_info(name="SUTA-DRAWER", service_uuids=[codec.V1_SERVICE])
    )
    assert accessory.bed_type is None
    assert "instant_comfort" not in (accessory.ambiguous_types or ())


async def test_native_combine_keeps_optional_axis_and_offline_entities(
    hass, enable_custom_integrations, mock_coordinator_connected
):
    from homeassistant import config_entries
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.pairing import effective_child_data
    from custom_components.adjustable_bed.pairing_candidates import encode_pair_selection

    entries = []
    registry = er.async_get(hass)
    for address, route, model in (
        ("AA:BB:CC:DD:EE:01", "malouf", "pf4"),
        ("AA:BB:CC:DD:EE:02", "reverie_v2", "pf3"),
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=route,
            unique_id=address,
            data={
                "address": address,
                "bed_type": "instant_comfort",
                "protocol_variant": route,
                "product_type": model,
                "motor_count": 2,
                "disable_angle_sensing": True,
                "preferred_adapter": "auto",
            },
            version=5,
            state=ConfigEntryState.LOADED,
        )
        entry.add_to_hass(hass)
        entries.append(entry)
    row = registry.async_get_or_create(
        "button",
        DOMAIN,
        "AA:BB:CC:DD:EE:02_personal_comfort_massage_head",
        config_entry=entries[1],
    )
    _old, fake = make("malouf")
    fake.client.disconnect = AsyncMock(
        side_effect=lambda: setattr(fake.client, "is_connected", False)
    )

    async def connect(coordinator):
        if coordinator.address == "AA:BB:CC:DD:EE:02":
            return False
        coordinator._client = fake.client
        coordinator._controller = await create_controller(
            coordinator, "instant_comfort", "malouf", fake.client
        )
        return True

    with patch.object(AdjustableBedCoordinator, "async_connect", connect):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": "pair_beds"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"pair_selection": encode_pair_selection(*(entry.entry_id for entry in entries))},
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    paired = result["result"]
    assert paired.state is ConfigEntryState.LOADED
    assert registry.async_get(row.entity_id).config_entry_id == paired.entry_id
    parent = hass.data[DOMAIN][paired.entry_id]
    assert parent.children["left"].capability_controller.has_pillow_support
    assert not parent.children["right"].is_connected
    assert parent.children["right"].capability_controller.supports_massage
    assert effective_child_data(paired.data, "right")["protocol_variant"] == "reverie_v2"


@pytest.mark.parametrize("fresh_ack", [False, True])
async def test_queued_ack_before_dispatch_cannot_complete_target(clock, fresh_ack):
    from custom_components.adjustable_bed import command_scheduler as scheduler

    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}
    context = scheduler.CommandContext(
        object(), c.cancel_command, 0, "replacement", "command", None, frozenset({"*"})
    )

    async def respond(_char, packet, **_kwargs):
        if packet[2] == 0x69:
            ctrl.receive(bytes((0, 0, 0x69)))
            ctrl.receive(bytes((0, 0, 0x85)))
        elif packet[2] == 1 and fresh_ack:
            ctrl.receive(bytes((0, 0, 0x85)))
        elif packet[2] == 0x85 and not fresh_ack:
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = respond
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(context)
    try:
        if fresh_ack:
            await ctrl.set_firmness("left", 25)
        else:
            with pytest.raises(asyncio.CancelledError):
                await ctrl.set_firmness("left", 25)
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
    # Target plus its fresh ACK, or target alone. Old ACK maintenance is uncounted.
    assert context.frames_written == (2 if fresh_ack else 1)
    assert ctrl._anm3_events is None


@pytest.mark.parametrize("latest", [35, 25])
async def test_anm3_direction_uses_refreshed_readback_at_dispatch(clock, latest):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}

    async def respond(_char, packet, **_kwargs):
        if packet[2] == 0x69:
            ctrl.receive(bytes((0, 0, 0x85)))
            ctrl.receive(bytes((0, 0, 0x69)))
        elif packet[2] == 0x83:
            ctrl.receive(bytes((0x55, 4, 0x83, 0, 20, latest, 0, 0, 0, 0xAA)))
        elif packet[2] in (1, 2):
            ctrl.receive(bytes((0, 0, 0x85)))

    c.client.write_gatt_char.side_effect = respond
    await ctrl.set_firmness("left", 25)
    targets = [
        bytes.fromhex(frame)[2]
        for _char, frame, _response in writes(c)
        if bytes.fromhex(frame)[2] in (1, 2)
    ]
    assert targets == ([2] if latest == 35 else [])


async def test_wrong_layout_busy_cannot_pair_with_matching_idle(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")

    async def respond(_char, packet, **_kwargs):
        if packet.startswith(b"C>SETP>"):
            ctrl.receive(b"RET>SP>0001000042")
            ctrl.receive(b"RBD>SP>00000000102142")

    c.client.write_gatt_char.side_effect = respond
    with pytest.raises(ServiceValidationError, match="did not finish"):
        await ctrl.set_pressures("right", 30, 25)
    targets = [
        bytes.fromhex(frame)
        for _char, frame, _response in writes(c)
        if bytes.fromhex(frame).startswith(b"C>SETP>")
    ]
    assert targets == [b"C>SETP>2>36\n"]
    assert ctrl._pressure_adjustment is None


async def test_pressure_edges_before_locked_dispatch_do_not_finish_target(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    await ctrl._ble_lock.acquire()
    pending = asyncio.create_task(ctrl.set_pressures("right", 30, 25))
    await asyncio.sleep(0)
    ctrl.receive(b"RBD>SP>00010000102142")
    ctrl.receive(b"RBD>SP>00000000102142")
    ctrl._ble_lock.release()
    with pytest.raises(ServiceValidationError, match="did not finish"):
        await pending
    targets = [
        bytes.fromhex(frame)
        for _char, frame, _response in writes(c)
        if bytes.fromhex(frame).startswith(b"C>SETP>")
    ]
    assert targets == [b"C>SETP>2>36\n"]
    assert ctrl._pressure_adjustment is None


async def test_busy_unit_cannot_arm_adjustment_at_locked_dispatch(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    await ctrl._ble_lock.acquire()
    pending = asyncio.create_task(ctrl.set_pressures("right", 30, 25))
    await asyncio.sleep(0)
    ctrl.receive(b"RBD>SP>00010000102142")
    ctrl._ble_lock.release()
    with pytest.raises(ServiceValidationError, match="busy"):
        await pending
    assert not writes(c)
    assert ctrl._pressure_adjustment is None


async def test_wrong_layout_idle_preserves_matching_firmness_and_cannot_create_noop(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")
    ctrl.receive(b"RET>SP>0000000042")
    assert ctrl.values == {"left": 5, "right": 27}
    assert ctrl._lumbar == {"left": 15, "right": 50}
    assert ctrl.protocol_diagnostics["pressure_channels"] == 2
    ctrl.receive(b"RBD>SP>00010000102142")

    async def still_busy(_char, packet, **_kwargs):
        if packet == b"R>SP\n":
            ctrl.receive(b"RBD>SP>00010000102142")

    c.client.write_gatt_char.side_effect = still_busy
    with pytest.raises(ServiceValidationError, match="busy"):
        await ctrl.set_firmness("right", 50)
    assert [bytes.fromhex(frame) for _char, frame, _response in writes(c)] == [b"R>SP\n"]
    c.client.write_gatt_char.reset_mock()

    ctrl.receive(b"RBD>SP>00000000102142")

    async def respond(_char, packet, **_kwargs):
        if packet.startswith(b"C>SETP>"):
            ctrl.receive(b"RBD>SP>00010000102142")
            ctrl.receive(b"RBD>SP>00000000104242")

    c.client.write_gatt_char.side_effect = respond
    await ctrl.set_firmness("right", 50)
    assert bytes.fromhex(writes(c)[0][1]) == b"C>SETP>2>66\n"
    assert ctrl.values["right"] == 50


async def test_cancelled_pressure_adjustment_refreshes_cached_busy_before_replacement(clock):
    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00000000102142")

    async def cancel_first(_char, packet, **_kwargs):
        if packet.startswith(b"C>SETP>"):
            ctrl.receive(b"RBD>SP>00010000102142")
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = cancel_first
    with pytest.raises(asyncio.CancelledError):
        await ctrl.set_pressures("right", 30, 25)
    c.cancel_command = asyncio.Event()
    c.client.write_gatt_char.reset_mock()

    async def idle_then_adjust(_char, packet, **_kwargs):
        if packet == b"R>SP\n":
            ctrl.receive(b"RBD>SP>00000000102142")
        elif packet.startswith(b"C>SETP>"):
            ctrl.receive(b"RBD>SP>00010000102142")
            ctrl.receive(b"RBD>SP>00000000102142")

    c.client.write_gatt_char.side_effect = idle_then_adjust
    await ctrl.set_pressures("right", 30, 25)
    packets = [bytes.fromhex(frame) for _char, frame, _response in writes(c)]
    assert packets[0] == b"R>SP\n"
    assert [packet for packet in packets if packet.startswith(b"C>SETP>")] == [
        b"C>SETP>2>36\n", b"C>SETP>3>29\n"
    ]


async def test_cached_busy_refresh_keeps_reply_received_before_wait_task_runs(clock):
    from custom_components.adjustable_bed.beds.cancellation import cancellable

    ctrl, c = make("anm5", layout="four")
    ctrl.receive(b"RBD>SP>00010000102142")

    async def reply_before_task_starts(operation, event):
        ctrl.receive(b"RBD>SP>00000000102142")
        return await cancellable(operation, event)

    with (
        patch(
            "custom_components.adjustable_bed.beds.instant_comfort.air.cancellable",
            side_effect=reply_before_task_starts,
        ),
        patch("custom_components.adjustable_bed.beds.instant_comfort.air.HYDRATION_TIMEOUT", 0.1),
    ):
        await ctrl.set_firmness("right", 27)
    assert [bytes.fromhex(frame) for _char, frame, _response in writes(c)] == [b"R>SP\n"]
    assert ctrl.values["right"] == 27


@pytest.mark.parametrize("status", [0x69, 0x88])
@pytest.mark.parametrize("fresh_reply", [False, True])
async def test_anm3_prepare_ignores_replies_received_before_locked_dispatch(clock, status, fresh_reply):
    ctrl, c = make("anm3")
    ctrl.values = {"left": 10, "right": 20}
    prepared = asyncio.Event()

    async def respond(_char, packet, **_kwargs):
        if packet[2] == 0x69:
            prepared.set()
            if fresh_reply:
                ctrl.receive(bytes((0, 0, status)))
        elif packet[2] == 1:
            ctrl.receive(bytes((0, 0, 0x85)))

    c.client.write_gatt_char.side_effect = respond
    await ctrl._ble_lock.acquire()
    pending = asyncio.create_task(ctrl.set_firmness("left", 25))
    await asyncio.sleep(0)
    ctrl.receive(bytes((0, 0, status)))
    ctrl._ble_lock.release()
    await prepared.wait()
    if fresh_reply:
        await pending
        assert [bytes.fromhex(frame)[2] for _char, frame, _response in writes(c)] == [
            0x69, 1, 0x85, 0x83
        ]
    else:
        for _ in range(5):
            await asyncio.sleep(0)
        assert not pending.done()
        assert [bytes.fromhex(frame)[2] for _char, frame, _response in writes(c)] == [0x69]
        c.cancel_command.set()
        with pytest.raises(asyncio.CancelledError):
            await pending


@pytest.mark.parametrize("route", ["anm5", "anm3", "ra"])
async def test_reconfigure_controller_picker_precedes_selected_layout(hass, route):
    from homeassistant.config_entries import SOURCE_RECONFIGURE
    from pytest_homeassistant.common import MockConfigEntry

    entry = MockConfigEntry(
        domain="adjustable_bed",
        title="Bed",
        unique_id="AA:BB:CC:DD:EE:01",
        data={
            "address": "AA:BB:CC:DD:EE:01",
            "bed_type": "instant_comfort",
            "protocol_variant": "malouf",
            "product_type": "pf4",
            "preferred_adapter": "auto",
        },
        version=5,
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    app = await flow.async_step_reconfigure()
    assert app["step_id"] == "reconfigure_bed_type"
    app_schema = app["data_schema"]
    assert app_schema is not None
    routes = await flow.async_step_reconfigure_bed_type(
        app_schema({"bed_type": "instant_comfort"})
    )
    assert routes["step_id"] == "reconfigure_route"
    route_schema = routes["data_schema"]
    assert route_schema is not None
    defaults = {marker.schema: marker.default() for marker in route_schema.schema}
    assert defaults["protocol_variant"] == "malouf"
    with patch.object(flow, "_finish_with_verify", return_value={"type": "abort"}) as finish:
        layout = await flow.async_step_reconfigure_route(
            route_schema({"protocol_variant": route})
        )
    if route == "anm5":
        assert layout["step_id"] == "profile_questions"
        product_schema = layout["data_schema"]
        assert product_schema is not None
        assert product_schema({"product_type": "four"}) == {"product_type": "four"}
        finish.assert_not_called()
    else:
        assert layout == {"type": "abort"}
        finish.assert_awaited_once()
        assert finish.call_args.args[0]["protocol_variant"] == route
        assert finish.call_args.args[0]["has_massage"] is False
    # Reconfigure has staged the change, leaving the saved entry intact.
    assert entry.data["protocol_variant"] == "malouf"


async def test_pressure_target_hydrates_matching_layout_before_dispatch(clock):
    ctrl, c = make("anm5", layout="four")
    sent = False

    async def respond(_char, packet, **_kwargs):
        nonlocal sent
        if packet.startswith(b"C>SETP>"):
            sent = True
            ctrl.receive(b"RBD>SP>00010000102142")
            ctrl.receive(b"RBD>SP>00000000104242")
        elif packet == b"R>SP\n":
            ctrl.receive(b"RBD>SP>00000000104242" if sent else b"RBD>SP>00000000102142")

    c.client.write_gatt_char.side_effect = respond
    await ctrl.set_firmness("right", 50)
    packets = [bytes.fromhex(frame) for _char, frame, _response in writes(c)]
    assert packets[:3] == [b"C>TPCH>0\n", b"C>TPCH>0\n", b"R>SP\n"]
    assert [packet for packet in packets if packet.startswith(b"C>SETP>")] == [b"C>SETP>2>66\n"]
    assert ctrl.values["right"] == 50
