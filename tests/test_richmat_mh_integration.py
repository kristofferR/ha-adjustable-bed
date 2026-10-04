"""Richmat MH app profiles: registration, opt-in detection and entity wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.actuator_groups import get_actuator_group_for_bed_type
from custom_components.adjustable_bed.beds import richmat_mh_protocol as protocol
from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import (
    _motor_count_options,
    _name_rule_setup_name,
    _richmat_mh_variant_error,
)
from custom_components.adjustable_bed.const import (
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BLE_DEVICE_NAME,
    RICHMAT_MH_APPS,
    RICHMAT_MH_BED_TYPES,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_richmat_mh import make, vers0, vers1


@pytest.mark.parametrize("bed_type", sorted(RICHMAT_MH_BED_TYPES))
def test_profile_registration(bed_type: str) -> None:
    assert bed_type in SUPPORTED_BED_TYPES and bed_type in BEDS_WITHOUT_ANGLE_FEEDBACK
    assert get_motor_pulse_defaults(bed_type) == (10, 100)
    assert not requires_pairing(bed_type)  # the app has no pairing, PIN or encryption
    assert _motor_count_options(bed_type) == [2]
    assert get_actuator_group_for_bed_type(bed_type)[0] == "richmat_apps"
    assert any(option["value"] == bed_type for option in get_bed_type_options())
    assert is_valid_variant_for_bed_type(bed_type, VARIANT_AUTO)
    assert _name_rule_setup_name(bed_type, "7IRM0001") == {CONF_BLE_DEVICE_NAME: "7IRM0001"}
    assert _name_rule_setup_name(bed_type, "AA:BB:CC:DD:EE:FF") == {}


@pytest.mark.parametrize("name", ["QRRM0001", "7IRM0001", "Cool Touch 9", "VORM1234"])
@pytest.mark.parametrize("service", [gatt[0] for gatt in protocol.GATT_MAPS])
def test_shared_names_and_services_never_select_an_app_profile(name, service) -> None:
    info = MagicMock()
    info.name = name
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = [service]
    info.manufacturer_data = {}
    assert detect_bed_type(info) not in RICHMAT_MH_BED_TYPES


@pytest.mark.parametrize("bed_type", sorted(RICHMAT_MH_BED_TYPES))
async def test_offline_factory_reads_only_the_stored_raw_name(bed_type: str) -> None:
    coordinator = _FactoryCoordinator()
    coordinator.entry.data[CONF_BLE_DEVICE_NAME] = "CERM0001"
    controller = await create_controller(
        coordinator, bed_type, VARIANT_AUTO, None, device_name="QRRM display"
    )
    assert controller.protocol_diagnostics["richmat_mh_app"] == RICHMAT_MH_APPS[bed_type]
    assert controller.protocol_diagnostics["richmat_mh_model"] == "cerm"


async def test_legacy_page_entities(hass) -> None:
    controller = make("revive", "CFRM0001", snapshot={**vers0("cfrm", alarm=True), "detection": True})
    runtime = configure_entity_runtime(hass, controller, "richmat_revive")
    buttons = {e.unique_id.removeprefix("bed_").removesuffix("_left") for e in _button_entities_for(hass, runtime)}
    assert {"richmat_mh_toggle_smart_set_lock", "richmat_mh_start_detection",
            "richmat_mh_stop_detection", "preset_flat"} <= buttons
    assert "toggle_light" not in buttons  # the colour light owns the light icon
    taps = [e for e in _button_entities_for(hass, runtime)
            if str(getattr(e, "_attr_translation_key", "")).startswith("richmat_mh_")
            and getattr(e, "_attr_translation_placeholders", None)]
    assert taps and all(e._attr_translation_placeholders == {"action": e._spec.name} for e in taps)
    assert len(_light_entities_for(hass, runtime)) == 1
    numbers = {e.unique_id for e in _number_entities_for(hass, runtime)}
    assert "bed_controller_number_richmat_mh_light_timer_left" in numbers
    selects = {e.unique_id for e in _select_entities_for(hass, runtime)}
    assert any("richmat_mh_snore" in key for key in selects)
    sensors = {e.unique_id for e in _sensor_entities_for(hass, runtime)}
    assert {"bed_richmat_mh_detection_left", "bed_richmat_mh_alarm_left"} <= sensors
    binary = {e.unique_id for e in _binary_sensor_entities_for(hass, runtime)}
    assert "bed_richmat_mh_smart_set_lock_left" in binary


@pytest.mark.parametrize(("app", "model", "snapshot"), [
    ("revive", "dtrm", vers0("dtrm", led=True)),
    ("idealbed", "cerm", vers1("cerm", led=True)),
])
async def test_light_page_without_an_on_off_path_is_not_a_light(hass, app, model, snapshot) -> None:
    """The light pages write only colour and timeout; without the motor-page toggle
    there is no proven on/off, so colour is an action instead of a broken light."""
    controller = make(app, f"{model.upper()}0001", snapshot=snapshot)
    runtime = configure_entity_runtime(hass, controller, f"richmat_{app}")
    assert _light_entities_for(hass, runtime) == []
    assert controller.supports_richmat_mh_light_color
    assert not (controller.supports_light_color_control or controller.supports_light_toggle_control)
    numbers = {e.unique_id for e in _number_entities_for(hass, runtime)}
    assert "bed_controller_number_richmat_mh_light_timer_left" in numbers
    await controller.async_discover_capabilities()
    await controller.set_light_color((1, 2, 3))
    assert bytes(controller.client.write_gatt_char.call_args.args[1]).hex() == (
        protocol.rgb_frame(1, 2, 3).hex()
    )


async def test_ver1_page_entities(hass) -> None:
    controller = make(snapshot=vers1("7irm", alarm=True))
    runtime = configure_entity_runtime(hass, controller, "richmat_revive")
    numbers = {e.unique_id.removeprefix("bed_controller_number_").removesuffix("_left")
               for e in _number_entities_for(hass, runtime)}
    assert {"richmat_mh_back_angle", "richmat_mh_foot_angle", "richmat_mh_pillow_angle",
            "richmat_mh_head_massage_intensity", "richmat_mh_foot_massage_intensity"} <= numbers
    selects = {e.unique_id for e in _select_entities_for(hass, runtime)}
    assert any("richmat_mh_motor_mode" in key for key in selects)
    sensors = {e.unique_id for e in _sensor_entities_for(hass, runtime)}
    assert "bed_richmat_mh_memory_arrival_left" in sensors
    assert _light_entities_for(hass, runtime) == []  # no LED reply in this snapshot


@pytest.mark.parametrize(
    ("bed_type", "variant", "name", "error"),
    [
        ("richmat_revive", VARIANT_AUTO, "7IRM0001", None),
        ("richmat_revive", VARIANT_AUTO, "QRRM0001", "richmat_mh_choose_model"),
        ("richmat_idealbed", VARIANT_AUTO, "Cool Touch 1", "richmat_mh_choose_model"),
        ("richmat_revive", VARIANT_AUTO, "AA:BB:CC:DD:EE:FF", "richmat_mh_no_name"),
        ("richmat_harmony", VARIANT_AUTO, "ZZZZ0001", "richmat_mh_unknown_model"),
        ("richmat_harmony", "model_utrm", None, None),
        ("richmat", VARIANT_AUTO, "QRRM0001", None),
    ],
)
def test_setup_forms_report_what_the_app_could_not_resolve(bed_type, variant, name, error) -> None:
    assert _richmat_mh_variant_error(bed_type, variant, name) == error


def test_every_entity_translation_and_select_state_exists() -> None:
    import json
    from pathlib import Path

    from custom_components.adjustable_bed import richmat_mh_catalog as catalog

    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    strings = json.loads((root / "strings.json").read_text())["entity"]
    assert strings == json.loads((root / "translations/en.json").read_text())["entity"]
    dev = {"alarm": True, "led": True, "aroma": True, "snore": True}
    seen: dict[str, set[str]] = {p: set() for p in ("button", "select", "number", "sensor", "binary_sensor", "cover")}
    for app in catalog.MODELS:
        for model in catalog.MODELS[app]:
            for base in (vers0(model, **dev), vers1(model, **dev)):
                controller = make(app, f"{model}0000" if len(model) == 4 else None,
                                  variant=None if len(model) == 4 else f"model_{model}",
                                  snapshot={**base, "waist": True, "detection": True})
                if controller.model is None:
                    continue
                seen["button"] |= {s.translation_key for s in controller.controller_button_specs}
                seen["cover"] |= {s.translation_key for s in controller.motor_control_specs}
                seen["number"] |= {s.translation_key for s in controller.controller_number_specs}
                seen["sensor"] |= {s.translation_key for s in controller.controller_state_sensor_specs}
                seen["binary_sensor"] |= {
                    s.translation_key for s in controller.controller_state_binary_sensor_specs
                }
                for spec in controller.controller_select_specs:
                    seen["select"].add(spec.translation_key)
                    assert set(spec.options) <= set(strings["select"][spec.translation_key]["state"])
    for platform, keys in seen.items():
        missing = {k for k in keys if k and k not in strings[platform]}
        assert not missing, (platform, missing)


def test_coordinator_persists_a_changed_snapshot_and_schedules_a_reload() -> None:
    from types import SimpleNamespace

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    coordinator = object.__new__(AdjustableBedCoordinator)
    coordinator._bed_type = "richmat_revive"
    coordinator.entry = SimpleNamespace(data={"capabilities": {"other": 1}})
    coordinator._ble_bond_established = False
    coordinator._pending_internal_bond_marker = False
    coordinator._pending_capability_reload = False
    coordinator._controller = object()
    persisted: list[dict] = []
    coordinator._begin_internal_entry_update = lambda bonded: None
    coordinator._async_persist_config = lambda data, **kwargs: persisted.append(data)
    coordinator._schedule_pending_capability_reload = MagicMock()
    snapshot = {"model": "7irm", "version": "0001"}
    coordinator.remember_richmat_mh_snapshot(snapshot)
    assert persisted == [{"capabilities": {"other": 1, "richmat_mh": snapshot}}]
    assert coordinator._pending_capability_reload is True
    assert coordinator._offline_controller is coordinator._controller
    coordinator._schedule_pending_capability_reload.assert_called_once()
    coordinator.entry = SimpleNamespace(data={"capabilities": {"richmat_mh": snapshot}})
    coordinator.remember_richmat_mh_snapshot(snapshot)  # unchanged: no write
    assert len(persisted) == 1
    coordinator._bed_type = "richmat"
    with pytest.raises(ValueError):
        coordinator.remember_richmat_mh_snapshot(snapshot)


async def test_two_address_pair_refuses_a_combined_model_change(hass) -> None:
    """Each side is its own physical bed and app model; unpair before changing it."""
    from unittest.mock import patch

    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.data_entry_flow import FlowResultType
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed import _build_paired_children
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_COUNT,
        CONF_PAIR_CHILDREN,
        CONF_PAIR_ID,
        CONF_PAIR_MEMBER_ADDRESSES,
        CONF_PAIR_MODE,
        CONF_PAIR_SCHEMA_VERSION,
        CONF_PREFERRED_ADAPTER,
        CONF_PROTOCOL_VARIANT,
        CONF_SIDE,
        DOMAIN,
        PAIR_MODE_SEPARATE_ADDRESS,
    )

    left, right = "AA:BB:CC:DD:EE:81", "AA:BB:CC:DD:EE:82"

    def child(side: str, address: str) -> dict:
        return {
            CONF_SIDE: side,
            CONF_ADDRESS: address,
            CONF_NAME: side.capitalize(),
            CONF_BED_TYPE: "richmat_revive",
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_PROTOCOL_VARIANT: "model_vorm",
            CONF_BLE_DEVICE_NAME: "VORM0001",
        }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Revive Pair",
        data={
            CONF_PAIR_ID: "pair_revive",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_SCHEMA_VERSION: 1,
            CONF_BED_TYPE: "richmat_revive",
            CONF_NAME: "Revive Pair",
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_PROTOCOL_VARIANT: "model_vorm",
            CONF_PAIR_MEMBER_ADDRESSES: [left, right],
            CONF_PAIR_CHILDREN: [child("left", left), child("right", right)],
        },
        unique_id="pair_revive",
        version=4,
    )
    entry.add_to_hass(hass)
    _build_paired_children(hass, entry)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    with patch("homeassistant.components.bluetooth.async_last_service_info", return_value=None):
        result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: "model_farm"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "app_profile_unpair_first"}
    stored = [c[CONF_PROTOCOL_VARIANT] for c in entry.data[CONF_PAIR_CHILDREN]]
    assert stored == ["model_vorm", "model_vorm"]


@pytest.mark.parametrize(
    ("snapshot", "minted"),
    [
        (vers1("7irm", alarm=True, led=True), True),
        (None, False),  # never connected: the pages are unknown
        (vers1("cfrm", led=True), False),  # another model's replies
    ],
)
async def test_offline_side_mints_from_the_stored_snapshot(hass, snapshot, minted) -> None:
    """A paired side unreachable at reload keeps its catalog and page-gated entities."""
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_COUNT,
        CONF_PREFERRED_ADAPTER,
        CONF_PROTOCOL_VARIANT,
        DOMAIN,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:91", CONF_NAME: "Revive", CONF_BED_TYPE: "richmat_revive",
        CONF_MOTOR_COUNT: 2, CONF_DISABLE_ANGLE_SENSING: True, CONF_PREFERRED_ADAPTER: "auto",
        CONF_PROTOCOL_VARIANT: VARIANT_AUTO, CONF_BLE_DEVICE_NAME: "7IRM0001",
    }
    if snapshot is not None:
        data["capabilities"] = {"richmat_mh": snapshot}
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="AA:BB:CC:DD:EE:91")
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    controller = coordinator.capability_controller
    if not minted:
        assert controller is None
        return
    assert controller is not None and controller.supports_richmat_mh_alarm
    keys = {spec.key for spec in controller.controller_number_specs}
    assert {"richmat_mh_back_angle", "richmat_mh_light_timer"} <= keys
