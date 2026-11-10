"""Unit087: independent frozen frames, live selection, gestures and exposure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.beds.adjustable_lumbar import AdjustableBedAppController
from custom_components.adjustable_bed.beds.entity_specs import MotorCommandCallable
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.profiles.adjustable_bed import (
    PROFILES,
    VOICE_FINITE,
    VOICE_MOTORS,
)
from tests.adjustable_bed_vectors import ROWS
from tests.test_adjustable_lumbar import make_controller, nus_services, okin_services, written


def controller(name="OKIN-1", **kwargs):
    source = make_controller(name, **kwargs)
    return AdjustableBedAppController(source._coordinator, device_name=name)


@pytest.mark.parametrize(
    ("action", "moves"),
    [
        ("voice_head_up", True),
        ("voice_head_down", True),
        ("voice_feet_up", True),
        ("voice_feet_down", True),
        ("voice_lumbar_up", True),
        ("voice_lumbar_down", True),
        ("voice_flat", True),
        ("voice_zero_g", True),
        ("voice_anti_snore", True),
        ("voice_lounge", True),
        ("voice_incline", True),
        ("voice_stop", False),
        ("voice_light", False),
        ("voice_wave_1", False),
        ("voice_wave_2", False),
        ("voice_wave_3", False),
        ("voice_massage_on", False),
        ("voice_massage_stop", False),
    ],
)
async def test_speech_buttons_invalidate_estimates_before_moving(
    hass: HomeAssistant, action: str, moves: bool
) -> None:
    bed = controller()
    coordinator = bed._coordinator
    coordinator.hass = hass
    coordinator.entry.entry_id = "speech_estimates"
    manager = await pe.async_setup_position_estimates(
        hass, coordinator.entry.entry_id, ((coordinator.address, None),)
    )
    estimate = manager.beds[coordinator.address]
    estimate.configure({"back": (20.0, 10.0), "legs": (10.0, 8.0)})
    estimate.set_reference()

    async def admitted(command: MotorCommandCallable, **_kwargs: object) -> None:
        await command(bed)

    async def check_before_command(_action: str) -> None:
        assert estimate.tracking(["back", "legs"]) is not moves

    coordinator.async_execute_controller_command = AsyncMock(side_effect=admitted)
    spec = next(
        spec for spec in bed.controller_button_specs if spec.key == f"adjustable_bed_{action}"
    )
    button = ControllerActionButton(coordinator, spec)
    button.hass = hass
    with patch.object(bed, "execute_app_action", new=AsyncMock(side_effect=check_before_command)):
        await button.async_press()
    await manager.async_unload()


@pytest.mark.parametrize("row", ROWS, ids=lambda row: f"{row['table']}/{row['action']}")
def test_frozen_rows_match_existing_codecs(row):
    assert PROFILES[row["table"]].frames[row["action"]] == bytes.fromhex(row["bytes"])


@pytest.mark.parametrize(
    ("name", "reply", "table", "response"),
    [
        ("OKIN-1", b"STAR", "36_33_04a", True),
        ("Star25", b"STAR", "35_22_01", False),
        ("Star25", b"STAR\0", "25_42_02", False),
        ("Star25", b"", "25_42_02", False),
    ],
)
async def test_profile_is_resolved_before_control(name, reply, table, response):
    bed = controller(name, manufacturer=reply)
    await bed.async_discover_capabilities()
    assert bed.table == table
    await bed.start_notify()
    await bed.check_massage()
    assert bed.client.write_gatt_char.call_args.kwargs["response"] is response
    assert bed.execution.hold == ("latched" if table == "35_22_01" else "stream")
    bed.forward_raw_notification = MagicMock()
    bed.forward_controller_state_updates = MagicMock()
    bed._handle_notification(None, bytearray.fromhex("A5 0B 00 00 02 58 03 43"))
    bed.forward_raw_notification.assert_called_once()
    bed.forward_controller_state_updates.assert_not_called()


@pytest.mark.parametrize(
    ("name", "services", "error"),
    [
        ("Star25", nus_services(info=False), "Device Information"),
        ("OKIN-1", okin_services()[:1], "Device Information"),
        ("OKIN-1", okin_services(manufacturer=False), "manufacturer characteristic"),
        ("other", nus_services(), "no command table"),
    ],
)
async def test_missing_gatt_branches_do_not_fall_into_another_table(name, services, error):
    with pytest.raises(ValueError, match=error):
        await controller(name, services=services).async_discover_capabilities()


async def test_star_missing_characteristic_keeps_p1():
    bed = controller("Star25", services=nus_services(manufacturer=False))
    await bed.async_discover_capabilities()
    assert bed.table == "25_42_02"


@pytest.mark.parametrize("action", VOICE_MOTORS)
async def test_p2_voice_start_is_single_and_has_bounded_cleanup(action):
    bed = controller("Star25", manufacturer=b"STAR")
    await bed.async_discover_capabilities()
    # End the bounded movement through the coordinator's cancel event.
    bed._coordinator.cancel_command.wait = AsyncMock(return_value=True)
    with patch("asyncio.sleep", new=AsyncMock()):
        await bed.execute_app_action(action)
    frames = PROFILES["35_22_01"].frames
    assert written(bed) == [
        frames[key].hex(" ").upper() for key in ("voice_stop", action, "voice_stop", "stop", "stop")
    ]


@pytest.mark.parametrize("action", VOICE_FINITE)
async def test_speech_nonmotor_actions_use_two_writes_without_post_stop(action):
    bed = controller("Star25", manufacturer=b"STAR")
    await bed.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()):
        await bed.execute_app_action(f"voice_{action}")
    assert written(bed) == [
        PROFILES[bed.table].frames[key].hex(" ").upper() for key in ("voice_stop", action, action)
    ]


async def test_cancellation_cannot_suppress_voice_or_ordinary_stop():
    bed = controller("Star25", manufacturer=b"STAR")
    await bed.async_discover_capabilities()
    bed._coordinator.cancel_command.set()
    with patch("asyncio.sleep", new=AsyncMock()):
        await bed.move_lumbar_up()
    assert written(bed) == [
        PROFILES[bed.table].frames[key].hex(" ").upper() for key in ("voice_stop", "stop", "stop")
    ]


async def test_every_verified_feature_has_an_action_and_no_numbered_memory():
    bed = controller("Star25", manufacturer=b"STAR")
    await bed.async_discover_capabilities()
    actions = {s.key for s in bed.controller_button_specs}
    assert {
        f"adjustable_bed_{key}"
        for key in (
            *VOICE_MOTORS,
            "voice_stop",
            "save_zero_g",
            "save_lounge",
            "save_incline",
            "save_anti_snore",
            "check_massage",
        )
    } <= actions
    assert not bed.supports_memory_presets
    assert not bed.supports_discrete_light_control
    assert not bed.supports_position_feedback
    assert {s.scheduler_resource for s in bed.motor_control_specs} == {"*"}


@pytest.mark.parametrize(
    ("variant", "table"),
    [
        ("adjustable_bed_okin", "36_33_04a"),
        ("adjustable_bed_star", "25_42_02"),
        ("adjustable_bed_star_5a", "35_22_01"),
    ],
)
async def test_factory_and_stable_profile_identity(variant, table):
    from custom_components.adjustable_bed.const import BED_TYPE_ADJUSTABLE_BED
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.test_controller_contract import _FactoryCoordinator

    coordinator = _FactoryCoordinator()
    bed = await create_controller(coordinator, BED_TYPE_ADJUSTABLE_BED, variant, None)
    assert isinstance(bed, AdjustableBedAppController)
    assert bed.table == table
    assert (
        resolve_profile_id({"bed_type": BED_TYPE_ADJUSTABLE_BED, "protocol_variant": variant})
        == f"adjustable_bed:{variant}"
    )


async def test_setup_and_entity_exposure(hass):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.config_flow import (
        _motor_count_options,
        _name_rule_setup_name,
    )
    from custom_components.adjustable_bed.const import (
        BED_TYPE_ADJUSTABLE_BED,
        CONF_BLE_DEVICE_NAME,
    )
    from custom_components.adjustable_bed.detection import get_bed_type_options
    from tests.test_malouf_app_entities import configure_entity_runtime

    assert _motor_count_options(BED_TYPE_ADJUSTABLE_BED) == [3]
    assert _name_rule_setup_name(BED_TYPE_ADJUSTABLE_BED, "Star25") == {
        CONF_BLE_DEVICE_NAME: "Star25"
    }
    assert any(option["value"] == BED_TYPE_ADJUSTABLE_BED for option in get_bed_type_options())
    assert per_side_profile(BED_TYPE_ADJUSTABLE_BED, None).variant_owned
    bed = controller()
    runtime = configure_entity_runtime(hass, bed, BED_TYPE_ADJUSTABLE_BED)
    keys = {entity.unique_id for entity in _button_entities_for(hass, runtime)}
    assert any("adjustable_bed_voice_head_up" in key for key in keys)
    assert any("adjustable_bed_save_zero_g" in key for key in keys)


async def test_failed_voice_cleanup_still_attempts_both_ordinary_stops():
    bed = controller("Star25", manufacturer=b"STAR")
    await bed.async_discover_capabilities()
    bed._coordinator.cancel_command.set()
    original = bed.write_command

    async def fail_voice_stop(command, *args, **kwargs):
        if command == PROFILES[bed.table].frames["voice_stop"]:
            raise OSError("voice STOP failed")
        await original(command, *args, **kwargs)

    with (
        patch.object(bed, "write_command", side_effect=fail_voice_stop),
        patch("asyncio.sleep", new=AsyncMock()),
        pytest.raises(OSError, match="voice STOP failed"),
    ):
        await bed.execute_app_action("voice_lumbar_up")
    assert written(bed) == [PROFILES[bed.table].frames["stop"].hex(" ").upper()] * 2


@pytest.mark.parametrize(
    "scenario",
    [
        "adjustable_bed",
        "adjustable_bed:adjustable_bed_star",
        "adjustable_bed:adjustable_bed_star_5a",
    ],
)
@pytest.mark.parametrize("end", ["expire", "stop"])
async def test_renewable_hold_outlives_finite_pulses_and_releases(scenario, end):
    from tests.hold_lease_wire import leased_hold

    async def move(bed):
        await bed.move_lumbar_up()

    wire = await leased_hold(scenario, move, end_after_s=3, end=end)
    p2 = scenario.endswith("star_5a")
    if p2:
        # One pre-STOP plus one voice start remains active until the lease ends.
        assert [write.data.hex() for write in wire.held] == ["5a010310301fa5", "5a0103104006a5"]
        assert [write.data.hex() for write in wire.after[:3]] == [
            "5a010310301fa5",
            "5a010310300fa5",
            "5a010310300fa5",
        ]
    else:
        assert len(wire.held) > wire.pulse_count
        assert {write.data.hex() for write in wire.after} == {"08020000000000000000"}
    assert wire.after[-1].at_ms >= wire.ended_ms + 300


@pytest.mark.parametrize("axis", ["head", "lumbar"])
async def test_p2_renewal_cannot_extend_motion_beyond_latched_ceiling(axis):
    from custom_components.adjustable_bed.execution import LATCHED_HOLD_CEILING_MS
    from tests.hold_lease_wire import leased_hold

    async def move(bed):
        assert bed.execution.hold_ceiling_ms == LATCHED_HOLD_CEILING_MS
        await getattr(bed, f"move_{axis}_up")()

    # Keep the lease alive longer than its ceiling, as a continuously renewed
    # client would. The controller must complete its own release first.
    wire = await leased_hold(
        "adjustable_bed:adjustable_bed_star_5a", move, end_after_s=15, end="expire"
    )
    start = "5a0103104006a5" if axis == "lumbar" else "5a0103103000a5"
    stop = "5a010310301fa5" if axis == "lumbar" else "5a010310300fa5"
    assert any(write.data.hex() == start for write in wire.held)
    started = next(write for write in wire.held if write.data.hex() == start)
    first_stop = next(
        write for write in wire.held if write.data.hex() == stop and write.at_ms > started.at_ms
    )
    assert LATCHED_HOLD_CEILING_MS <= first_stop.at_ms <= LATCHED_HOLD_CEILING_MS + 20
    assert not wire.after
    if axis == "head":
        assert len([write for write in wire.held if write.data.hex() == start]) > wire.pulse_count
