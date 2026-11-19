"""OnlySnore metadata joins its setup, declared entities and native card."""

import json
from pathlib import Path

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.onlysnore.controller import OnlySnoreController
from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES
from scripts.codec_docs.onlysnore import BLOCKS, GUIDE
from scripts.generate_codec_docs import _rendered
from tests.card_placements import controller_entities, placements
from tests.test_controller_contract import _FactoryCoordinator

ROOT = Path(__file__).parents[1]


def controllers():
    return [OnlySnoreController(_FactoryCoordinator(), alarm_count=count) for count in (1, 3)]


def test_app_declared_entity_names_exist_in_both_languages():
    for filename in ("strings.json", "translations/en.json"):
        entities = json.loads((ROOT / "custom_components/adjustable_bed" / filename).read_text())["entity"]
        for controller in controllers():
            for domain, specs in (
                ("button", controller.controller_button_specs),
                ("select", controller.controller_select_specs),
                ("switch", controller.controller_switch_specs),
                ("sensor", controller.controller_state_sensor_specs),
                ("binary_sensor", controller.controller_state_binary_sensor_specs),
            ):
                for spec in specs:
                    assert spec.translation_key in entities[domain], (filename, domain, spec.key)
                    assert entities[domain][spec.translation_key]["name"]


def test_app_setup_questions_have_labels_and_side_ownership():
    strings = json.loads((ROOT / "custom_components/adjustable_bed/strings.json").read_text())
    profile = SETUP_PROFILES["onlysnore"]
    side = per_side_profile("onlysnore", None)
    assert side is not None
    for question in profile.questions:
        assert question.key in side.keys
        assert question.key in strings["config"]["step"]["profile_questions"]["data"]
        assert question.key in strings["config"]["step"]["profile_questions"]["data_description"]
        assert question.key in strings["options"]["step"]["settings"]["data"]


def test_only_app_generated_blocks_are_current_and_unique():
    text = (ROOT / GUIDE).read_text()
    assert text == _rendered(GUIDE)
    for guide, name, _renderer in BLOCKS:
        assert guide == GUIDE
        assert text.count(f"<!-- generated:{name} -->") == 1


def test_actual_app_entities_match_appended_card_entries():
    fixture = json.loads((ROOT / "tests/fixtures/card_placements.json").read_text())
    actual = placements(controller_entities(controllers()))
    app = {key: value for key, value in actual.items() if ":onlysnore_" in key}
    # The three alarm-enabled binary sensors are attributes of the alarm times.
    assert len(app) == 21
    assert {key: value for key, value in fixture.items() if ":onlysnore_" in key} == app
    assert all(fixture[key] == value for key, value in actual.items())
