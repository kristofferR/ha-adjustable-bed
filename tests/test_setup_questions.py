"""Profile-declared setup questions and owned generic fields (#779)."""

import json
import re
from dataclasses import replace
from pathlib import Path

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.config_flow import _configure_questions
from custom_components.adjustable_bed.setup_questions import (
    GENERIC_FIELDS,
    REQUIRED,
    SET_BY_PROFILE,
    SETUP_PROFILES,
    setup_profile,
    setup_profile_for,
)

_STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)


def test_owned_fields_are_generic_and_never_asked():
    for key, profile in SETUP_PROFILES.items():
        assert set(profile.owns) <= GENERIC_FIELDS, key
        assert not {question.key for question in profile.questions} & set(profile.owns), key


def test_the_most_specific_declaration_wins():
    # A variant entry replaces its bed type's entry.
    assert hidden_generic_fields(const.BED_TYPE_KEESON, const.VARIANT_AUTO) == frozenset()
    assert const.CONF_HAS_MASSAGE in hidden_generic_fields(
        const.BED_TYPE_KEESON, const.KEESON_VARIANT_INNOVA
    )
    assert (
        setup_profile(const.BED_TYPE_JIECANG_APP, None, "dreamask")
        is SETUP_PROFILES[const.BED_TYPE_JIECANG_APP]
    )
    assert setup_profile(None) is None


def test_every_declared_question_has_its_labels():
    """Labels come from strings.json, so a declared field cannot ship unlabelled.

    A question with choices or free text also explains itself in setup; a yes or
    no question may rely on its label.
    """
    step = _STRINGS["config"]["step"]["profile_questions"]
    settings = _STRINGS["options"]["step"]["settings"]["data"]
    for key, profile in SETUP_PROFILES.items():
        for question in profile.questions:
            strings = step["sections"]["advanced"] if question.advanced else step
            assert question.key in strings["data"], (key, question.key)
            if question.choices is not None or question.text:
                assert question.key in strings["data_description"], (key, question.key)
            assert question.key in settings, (key, question.key)


def test_every_generic_step_string_belongs_to_a_declared_question():
    """The generic step labels only declared questions, so none outlives its field."""
    step = _STRINGS["config"]["step"]["profile_questions"]
    advanced = step["sections"]["advanced"]
    questions = [question for profile in SETUP_PROFILES.values() for question in profile.questions]
    assert set(step["data"]) == {q.key for q in questions if not q.advanced}
    assert set(advanced["data"]) == {q.key for q in questions if q.advanced}
    settings = _STRINGS["options"]["step"]["settings"]
    for strings in (step, advanced, settings):
        assert set(strings["data_description"]) <= set(strings["data"])
    # Configure also labels settings no profile declares; tests/test_config_keys.py
    # checks each of its labels against the CONF_* audit.


def _documented_steps(design: str, section: str) -> list[str]:
    body = design.split(f"\n## {section}\n", 1)[1].split("\n## ", 1)[0]
    return [
        step
        for line in body.splitlines()
        if line.startswith("| ") and not line.startswith("| Step")
        for step in re.findall(r"`([a-z0-9_]+)`", line.split("|")[1])
    ]


def test_every_flow_step_is_recorded_with_its_reason():
    """A new per-app step needs its reason in the design note before it ships."""
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
    )

    design = (Path(__file__).parents[1] / "docs/design/setup-questions.md").read_text()
    documented = [
        *_documented_steps(design, "Dedicated steps"),
        *_documented_steps(design, "Shared steps"),
    ]
    steps = {
        name.removeprefix("async_step_")
        for flow in (AdjustableBedConfigFlow, AdjustableBedOptionsFlow)
        for klass in flow.__mro__
        if klass.__module__.startswith("custom_components.adjustable_bed")
        for name in vars(klass)
        if name.startswith("async_step_")
    }
    assert len(documented) == len(set(documented))
    assert set(documented) == steps


def test_jiecang_questions_follow_the_chosen_app():
    data = {
        const.CONF_BED_TYPE: const.BED_TYPE_JIECANG_APP,
        const.CONF_JIECANG_APP_PROFILE: "comfort_motion",
    }
    profile = setup_profile_for(data)
    assert profile is not None
    layout, light, transport = profile.questions
    from custom_components.adjustable_bed.profiles.jiecang import COMFORT_MOTION

    assert set(layout.options(data) or {}) == set(COMFORT_MOTION.layouts)
    assert layout.default_for(data) is REQUIRED
    assert light.options(data) is None and light.default_for(data) is True
    assert set(transport.options(data) or {}) == {"auto", *COMFORT_MOTION.transports}
    # A staged answer the app no longer offers falls back to the declared default.
    assert transport.default_for({**data, const.CONF_JIECANG_APP_TRANSPORT: "g3"}) == "auto"
    assert profile.owns[const.CONF_MOTOR_COUNT] is SET_BY_PROFILE
    assert profile.fixed_values() == {const.CONF_DISABLE_ANGLE_SENSING: True}


def test_configure_leaves_the_route_to_the_guided_change():
    profile = _configure_questions(
        {
            const.CONF_BED_TYPE: const.BED_TYPE_JIECANG_APP,
            const.CONF_JIECANG_APP_PROFILE: "dreamask",
        }
    )
    assert profile is not None
    assert [question.key for question in profile.questions] == [const.CONF_HAS_LIGHT]


def test_a_handset_table_derives_the_motors_and_massage():
    profile = SETUP_PROFILES[const.BED_TYPE_FURNIMOVE]
    settled = profile.settled({const.CONF_FURNIMOVE_REMOTE: "82417"})
    assert settled[const.CONF_MOTOR_COUNT] == 2
    assert settled[const.CONF_HAS_MASSAGE] is False
    assert settled[const.CONF_DISABLE_ANGLE_SENSING] is True


def test_a_generic_field_the_profile_asks_is_hidden_from_generic_forms():
    # The remote code and motor count are the Okin UUID profile's own questions.
    assert {const.CONF_PROTOCOL_VARIANT, const.CONF_MOTOR_COUNT} <= hidden_generic_fields(
        const.BED_TYPE_OKIN_UUID, const.VARIANT_AUTO
    )


def test_a_saved_route_new_setups_do_not_offer_stays_selectable():
    code, _motors = SETUP_PROFILES[const.BED_TYPE_OKIN_DOT].questions
    saved = {const.CONF_BED_TYPE: const.BED_TYPE_OKIN_DOT, const.CONF_PROTOCOL_VARIANT: "90167"}
    assert "90167" in (code.options(saved) or {})
    assert "90167" not in (code.options({const.CONF_BED_TYPE: const.BED_TYPE_OKIN_DOT}) or {})


async def test_whole_number_answers_are_coerced_from_select_text(hass):
    from unittest.mock import AsyncMock, patch

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
        const.CONF_PROTOCOL_VARIANT: const.KEESON_VARIANT_INNOVA,
    }
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_MOTOR_COUNT: "3"})
    assert finish.call_args.args[0][const.CONF_MOTOR_COUNT] == 3


def test_every_profile_with_questions_has_a_setup_step_that_asks_them():
    """A declared question hides its generic field, so some step must ask it."""
    from custom_components.adjustable_bed.config_flow import _APP_SETUP_STEPS
    from custom_components.adjustable_bed.profile_id import profile_route

    for key, profile in SETUP_PROFILES.items():
        if profile.questions:
            assert profile_route(key).bed_type in _APP_SETUP_STEPS, key


def test_a_condition_renders_as_a_native_conditional_field():
    from custom_components.adjustable_bed.config_flow import _profile_question_schema

    data = {
        const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "caresse",
    }
    profile = setup_profile_for(data)
    assert profile is not None
    markers = {marker.schema: marker for marker in _profile_question_schema(profile, data)}
    assert markers[const.CONF_VIBRADORM_RESTORED].visible is None
    assert markers[const.CONF_VIBRADORM_RGB].visible == {
        "field": const.CONF_VIBRADORM_RESTORED,
        "value": True,
    }


def test_a_condition_on_an_answer_the_form_omits_is_settled_by_the_saved_setup():
    from custom_components.adjustable_bed.config_flow import _profile_question_schema

    profile = SETUP_PROFILES[const.BED_TYPE_VMATBASIC]
    # Configure leaves the product to the guided change, so its fields are settled here.
    without_product = replace(profile, questions=profile.questions[1:])
    cbi = {const.CONF_VMATBASIC_PROFILE: "cbi"}
    basic = {const.CONF_VMATBASIC_PROFILE: "basic"}
    shown = {m.schema: m for m in _profile_question_schema(without_product, cbi)}
    assert const.CONF_VMATBASIC_FLOOR_LEVEL in shown
    assert shown[const.CONF_VMATBASIC_FLOOR_LEVEL].visible is None
    assert not _profile_question_schema(without_product, basic)


def test_a_profile_cleans_its_answers_before_checking_them():
    legacy = SETUP_PROFILES[const.BED_TYPE_LEGGETT_LP_LEGACY]
    staged = legacy.staged(
        {},
        {
            const.CONF_LP_LEGACY_MODEL: " a2rm ",
            const.CONF_LP_LEGACY_MODE: "framed",
            const.CONF_LP_LEGACY_WRITE_UUID: "11111111222233334444555555555555",
            const.CONF_LP_LEGACY_READ_UUID: "",
        },
    )
    assert staged[const.CONF_LP_LEGACY_MODEL] == "A2RM"
    assert staged[const.CONF_LP_LEGACY_WRITE_UUID] == "11111111-2222-3333-4444-555555555555"
    assert legacy.validate is not None and legacy.validate(staged) == {}


def test_an_unanswered_required_question_stays_required():
    legacy = SETUP_PROFILES[const.BED_TYPE_LEGGETT_LP_LEGACY]
    write = legacy.questions[2]
    assert write.default_for(legacy.staged({}, {})) is REQUIRED
