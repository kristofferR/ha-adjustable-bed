"""Estimated-position entities and actions on a set-up OCTO bed (#601)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed.beds.octo import OctoController
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OCTO_VARIANT_STANDARD,
)

ADDRESS = "AA:BB:CC:DD:EE:61"
ENTRY_ID = "octo_estimate_entry"


@pytest.fixture
async def octo_bed(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_octo_ready_transport: None,
    enable_custom_integrations: None,
    request: pytest.FixtureRequest,
) -> MockConfigEntry:
    """An OCTO bed with calibrated back and legs and a stored 40% back estimate."""
    hass_storage[pe.storage_key(ENTRY_ID)] = {
        "version": pe.STORAGE_VERSION,
        "key": pe.storage_key(ENTRY_ID),
        "data": {
            "beds": {
                ADDRESS: {
                    "back": {"up_s": 20.0, "down_s": 10.0, "percent": 40.0},
                    "legs": {"up_s": 10.0, "down_s": 8.0, "percent": 0.0},
                    "head": {"up_s": None, "down_s": None},
                }
            },
            "positions": [],
        },
    }
    motor_count = getattr(request, "param", 2)
    if motor_count == 1:
        hass_storage[pe.storage_key(ENTRY_ID)]["data"]["beds"][ADDRESS] = {
            "tv_lift": {"up_s": 20.0, "down_s": 10.0, "percent": 40.0}
        }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom bed",
        data={
            "address": ADDRESS,
            "name": "Bedroom bed",
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_MOTOR_COUNT: motor_count,
            CONF_OCTO_MOTOR_COUNT_OVERRIDE: str(motor_count),
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
        },
        unique_id=ADDRESS,
        entry_id=ENTRY_ID,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity_id(hass: HomeAssistant, domain: str, key: str) -> str:
    found = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}")
    assert found is not None, key
    return found


def device_id(hass: HomeAssistant) -> str:
    row = er.async_get(hass).async_get(entity_id(hass, "button", "estimate_remote_used"))
    assert row is not None and row.device_id is not None
    return row.device_id


async def call(hass: HomeAssistant, service: str, **data: Any) -> Any:
    return await hass.services.async_call(
        DOMAIN,
        service,
        {"device_id": device_id(hass), **data},
        blocking=True,
        return_response=service == "save_position",
    )


async def test_restored_estimate_is_unconfirmed_until_the_user_confirms(
    hass: HomeAssistant, octo_bed: MockConfigEntry
) -> None:
    back = entity_id(hass, "number", "back_position_estimated")
    state = hass.states.get(back)
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["estimate_state"] == "unconfirmed"
    assert state.attributes["last_estimate"] == 40.0
    assert state.attributes["full_travel_up_s"] == 20.0
    assert state.name == "Bedroom bed Back position (estimated)"
    # Enabled but not calibrated: unavailable.
    head = hass.states.get(entity_id(hass, "number", "head_position_estimated"))
    assert head is not None and head.state == STATE_UNAVAILABLE

    with pytest.raises(ServiceValidationError):
        await call(hass, "save_position", name="Reading")

    await call(hass, "confirm_position_unchanged")
    state = hass.states.get(back)
    assert state is not None and state.state == "40"
    assert hass.states.get(entity_id(hass, "sensor", "saved_positions")) is not None


async def test_cover_moves_are_timed_and_remote_use_invalidates(
    hass: HomeAssistant, octo_bed: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [0.0]
    monkeypatch.setattr(pe, "_clock", lambda: clock[0])

    async def move(_self: OctoController) -> None:
        # Time the configured native movement, not a fixed one-second hold.
        clock[0] += 1.2

    await call(hass, "set_position_reference", motors=["back"])
    with patch.object(OctoController, "move_back_up", move):
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": entity_id(hass, "cover", "back")}, blocking=True
        )
    back = entity_id(hass, "number", "back_position_estimated")
    assert hass.states.get(back).state == "6"

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "estimate_remote_used")},
        blocking=True,
    )
    state = hass.states.get(back)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["estimate_reason"] == "remote"

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "set_back_reference")},
        blocking=True,
    )
    assert hass.states.get(back).state == "0"


@pytest.mark.parametrize("octo_bed", [1], indirect=True)
async def test_tv_lift_estimate_slider_saved_position_and_reference(
    hass: HomeAssistant, octo_bed: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A standalone lift can calibrate, move to a percentage and recall a saved height."""
    clock = [0.0]
    monkeypatch.setattr(pe, "_clock", lambda: clock[0])
    moves: list[tuple[str, int]] = []

    async def hold(_self: OctoController, control: str, duration_ms: int) -> None:
        moves.append((control, duration_ms))
        clock[0] += duration_ms / 1000

    async def delay(_seconds: float) -> None:
        return

    lift_id = entity_id(hass, "number", "tv_lift_position_estimated")
    state = hass.states.get(lift_id)
    assert state is not None and state.state == STATE_UNKNOWN
    assert state.name == "Bedroom bed TV lift position (estimated)"
    assert state.attributes["icon"] == "mdi:television-classic"
    assert "max_angle" not in state.attributes
    cover_state = hass.states.get(entity_id(hass, "cover", "tv_lift"))
    assert cover_state is not None
    assert cover_state.attributes["hold_lease_mode"] == "stream"
    assert cover_state.attributes["hold_lease_motor"] == "tv_lift"
    await call(hass, "set_position_reference", motors=["tv_lift"])

    with (
        patch.object(OctoController, "hold_control", hold),
        patch("custom_components.adjustable_bed.services.asyncio.sleep", delay),
    ):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": lift_id, "value": 50}, blocking=True
        )
        assert hass.states.get(lift_id).state == "50"
        await call(hass, "save_position", name="TV open")
        await hass.services.async_call(
            "number", "set_value", {"entity_id": lift_id, "value": 0}, blocking=True
        )
        await call(hass, "recall_position", position="TV open")

    assert moves == [("tv_lift_up", 10000), ("tv_lift_down", 5000), ("tv_lift_up", 10000)]
    assert hass.states.get(lift_id).state == "50"
    await call(hass, "mark_position_unknown")
    assert hass.states.get(lift_id).state == STATE_UNKNOWN
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id(hass, "button", "set_tv_lift_reference")},
        blocking=True,
    )
    assert hass.states.get(lift_id).state == "0"


async def test_saved_position_gets_an_optional_button(
    hass: HomeAssistant, octo_bed: MockConfigEntry
) -> None:
    await call(hass, "set_position_reference")
    response = await call(hass, "save_position", name="Reading")
    position_id = response["position_id"]
    sensor = hass.states.get(entity_id(hass, "sensor", "saved_positions"))
    assert sensor.state == "1"
    assert sensor.attributes["positions"] == [
        {
            "id": position_id,
            "name": "Reading",
            "button": True,
            "beds": {"bed": {"back": 0.0, "legs": 0.0}},
        }
    ]
    button = entity_id(hass, "button", f"saved_position_{position_id}")
    assert hass.states.get(button).name == "Bedroom bed Reading"

    await call(hass, "rename_position", position="Reading", name="Read", create_button=False)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get(button) is None

    await call(hass, "rename_position", position="Read", name="Read", create_button=True)
    await hass.async_block_till_done()
    assert entity_id(hass, "button", f"saved_position_{position_id}")

    await call(hass, "delete_position", position=position_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "sensor", "saved_positions")).state == "0"
    assert (
        er.async_get(hass).async_get_entity_id(
            "button", DOMAIN, f"{ADDRESS}_saved_position_{position_id}"
        )
        is None
    )


async def test_paired_sides_save_and_block_independently(hass: HomeAssistant) -> None:
    """A Both save covers both sides, a side save only that side (#601)."""
    from homeassistant.config_entries import ConfigEntryState

    from custom_components.adjustable_bed import (
        _async_ensure_paired_device_registry,
        _build_paired_children,
        async_register_services,
    )
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_CHILDREN,
        CONF_PAIR_ID,
        CONF_PAIR_MEMBER_ADDRESSES,
        CONF_PAIR_MODE,
        CONF_SIDE,
        PAIR_MODE_SEPARATE_ADDRESS,
    )
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_registry import (
        _device_for_entry_and_identifier,
    )

    left, right = "AA:BB:CC:DD:EE:71", "AA:BB:CC:DD:EE:72"
    snapshot = {"octo": {"memory_count": 0, "discovered_motor_count": 2, "has_pin": False}}

    def child(side: str, address: str) -> dict[str, Any]:
        return {
            CONF_SIDE: side,
            "address": address,
            "name": side.capitalize(),
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            "capabilities": snapshot,
        }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PAIR_ID: "pair_estimates",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_BED_TYPE: BED_TYPE_OCTO,
            "name": "Master Bed",
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_PAIR_MEMBER_ADDRESSES: [left, right],
            CONF_PAIR_CHILDREN: [child("left", left), child("right", right)],
        },
        unique_id="pair_estimates",
        entry_id="pair_estimates",
        version=4,
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    children = _build_paired_children(hass, entry)
    coordinator = PairedBedCoordinator(hass, entry, children)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_ensure_paired_device_registry(hass, entry, coordinator)
    await async_register_services(hass)
    manager = await pe.async_setup_position_estimates(
        hass, entry.entry_id, [(c.address, side) for side, c in coordinator.children.items()]
    )
    for bed in manager.beds.values():
        bed.configure({"back": (20.0, 10.0)})
    parent = _device_for_entry_and_identifier(
        dr.async_get(hass), entry.entry_id, (DOMAIN, "pair_estimates")
    )
    assert parent is not None

    async def call_pair(service: str, **data: Any) -> Any:
        return await hass.services.async_call(
            DOMAIN,
            service,
            {"device_id": parent.id, **data},
            blocking=True,
            return_response=service == "save_position",
        )

    await call_pair("set_position_reference", side="left")
    assert manager.beds[left].tracking(["back"])
    assert not manager.beds[right].tracking(["back"])
    with pytest.raises(ServiceValidationError):
        await call_pair("save_position", name="Reading")

    await call_pair("save_position", side="left", name="Snore")
    await call_pair("set_position_reference", side="right")
    await call_pair("save_position", name="Reading", create_button=False)
    assert {p.name: set(p.targets) for p in manager.positions} == {
        "Snore": {"left"},
        "Reading": {"left", "right"},
    }

    # A side selection cannot move or change a position that covers both sides.
    with pytest.raises(ServiceValidationError) as err:
        await call_pair("delete_position", side="left", position="Reading")
    assert err.value.translation_key == "saved_position_other_side"

    # With one side no longer estimated, the whole bed still manages its positions.
    manager.beds[right].configure({})
    await call_pair("rename_position", position="Reading", name="Read")
    manager.beds[right].configure({"back": (20.0, 10.0)})
    manager.beds[right].set_reference()

    # A recall never silently skips a saved side that is no longer estimated.
    manager.beds[right].configure({})
    with pytest.raises(ServiceValidationError) as err:
        await call_pair("recall_position", position="Read")
    assert err.value.translation_key == "saved_position_unavailable"
    manager.beds[right].configure({"back": (20.0, 10.0)})
    manager.beds[right].set_reference()

    await call_pair("mark_position_unknown", side="right")
    assert manager.beds[left].tracking(["back"])
    with pytest.raises(ServiceValidationError):
        await call_pair("recall_position", position="Read")
    await pe.async_unload_position_estimates(hass, entry.entry_id)


async def test_timed_move_times_only_the_hold(
    hass: HomeAssistant, octo_bed: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [0.0]
    monkeypatch.setattr(pe, "_clock", lambda: clock[0])

    async def hold(_self: OctoController, control: str, duration_ms: int) -> None:
        assert (control, duration_ms) == ("back_up", 2000)
        clock[0] += 2.0

    async def delay(seconds: float) -> None:
        clock[0] += seconds

    await call(hass, "set_position_reference", motors=["back"])
    with (
        patch.object(OctoController, "hold_control", hold),
        patch("custom_components.adjustable_bed.services.asyncio.sleep", delay),
    ):
        await call(hass, "timed_move", motor="back", direction="up", duration_ms=2000)
    assert hass.states.get(entity_id(hass, "number", "back_position_estimated")).state == "10"


async def test_configured_max_angle_reaches_the_card(
    hass: HomeAssistant, octo_bed: MockConfigEntry
) -> None:
    """Only an axis with a configured maximum angle gets the dashed graphic."""
    from custom_components.adjustable_bed.const import CONF_BACK_MAX_ANGLE

    back = entity_id(hass, "number", "back_position_estimated")
    assert "max_angle" not in hass.states.get(back).attributes
    hass.config_entries.async_update_entry(octo_bed, options={CONF_BACK_MAX_ANGLE: 60.0})
    await hass.async_block_till_done()
    assert hass.states.get(back).attributes["max_angle"] == 60.0
    legs = hass.states.get(entity_id(hass, "number", "legs_position_estimated"))
    assert "max_angle" not in legs.attributes
