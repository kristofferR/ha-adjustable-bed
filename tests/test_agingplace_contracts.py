"""App-scoped metadata contracts, independent of the row069 runtime receipts."""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.components.bluetooth.match import IntegrationMatcher

from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.discovery_hints.agingplace import HINTS
from custom_components.adjustable_bed.profiles import agingplace as app
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from scripts import generate_codec_docs as docs
from scripts.codec_docs._agingplace import BLOCKS
from tests.codec_families import families
from tests.entity_translation_reachability import TRANSLATION_FILES, _spec_keys
from tests.test_controller_contract import _FactoryCoordinator


async def test_app_entities_and_service_fields_have_translations():
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = {"bed_type": "agingplace", "ble_device_name": "KSWF07S123456789"}
    controller = await create_controller(coordinator, "agingplace", "auto", None)
    keys = _spec_keys([controller])
    for platform, required in keys.items():
        assert all(re.fullmatch(r"[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?", key) for key in required), (
            platform,
            required,
        )
    sensor_ids = {spec.key for spec in controller.controller_state_sensor_specs}
    assert sensor_ids == {
        f"agingplace_{name}"
        for name in (
            "heart_rate",
            "breathing_rate",
            "circulation_remaining",
            "sleep_remaining",
            "relax_cycle_remaining",
            "diagnostic_status",
            "version",
        )
    }
    for path in TRANSLATION_FILES:
        strings = json.loads(path.read_text())
        for platform, required in keys.items():
            assert required <= strings["entity"][platform].keys(), (platform, required)
        assert strings["services"]["agingplace_action"]["fields"].keys() >= {
            "device_id",
            "action",
            "side",
        }
        assert strings["services"]["agingplace_set_setting"]["fields"].keys() >= {
            "device_id",
            "setting",
            "value",
            "side",
        }


def test_questions_own_every_side_setting_and_have_explanations():
    data = {"bed_type": "agingplace"}
    profile = setup_profile_for(data)
    assert profile is not None
    assert {question.key for question in profile.questions} == app.CONFIG_KEYS | {"ble_device_name"}
    for path in TRANSLATION_FILES:
        strings = json.loads(path.read_text())
        labels = strings["config"]["step"]["profile_questions"]
        configured = strings["options"]["step"]["settings"]["data"]
        for question in profile.questions:
            assert question.key in labels["data"]
            assert question.key in labels["data_description"]
            assert question.key in configured


def test_app_single_profile_defaults_to_a_saveable_auto_route():
    from custom_components.adjustable_bed.config_flow import _default_setup_route
    from custom_components.adjustable_bed.const import VARIANT_REQUIRED_BED_TYPES
    from custom_components.adjustable_bed.validators import (
        get_variants_for_bed_type,
        is_valid_variant_for_bed_type,
    )

    route = _default_setup_route("agingplace")
    assert route == "auto"
    assert "agingplace" not in VARIANT_REQUIRED_BED_TYPES
    assert get_variants_for_bed_type("agingplace") is None
    assert is_valid_variant_for_bed_type("agingplace", route)
    profile = setup_profile_for({"bed_type": "agingplace"})
    assert profile is not None
    assert profile.settled({"bed_type": "agingplace"})["protocol_variant"] == route


@pytest.mark.parametrize("name", ("KSWF07S123456789", "prefixKSWF19Ssuffix"))
def test_source_case_sensitive_substrings_reach_the_app(name):
    info = MagicMock()
    info.name = name
    info.device.name = name
    info.address = "AA:69:00:00:00:01"
    info.connectable = True
    info.service_uuids = []
    info.service_data = {}
    info.manufacturer_data = {}
    result = detect_bed_type_detailed(info)
    assert "agingplace" in {result.bed_type, *(result.ambiguous_types or ())}
    if name.startswith("KSWF"):
        gate = IntegrationMatcher(
            [
                {"domain": "adjustable_bed", **matcher}
                for hint in HINTS
                for matcher in hint.matchers()
            ]
        )
        gate.async_setup()
        assert "adjustable_bed" in gate.match_domains(info)


def test_only_registered_row069_guide_blocks_are_current():
    for guide, name, renderer in BLOCKS:
        text = (Path(__file__).parents[1] / guide).read_text()
        assert text.count(f"<!-- generated:{name} -->") == 1
        assert docs.render(text, name, renderer()) == text
    assert docs.family_modules().keys() <= families().keys()
