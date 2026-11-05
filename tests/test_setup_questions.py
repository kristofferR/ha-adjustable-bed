"""Profile-declared setup questions and owned generic fields (#779)."""

import json
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
    """Labels come from strings.json, so a declared field cannot ship unlabelled."""
    step = _STRINGS["config"]["step"]["profile_questions"]
    settings = _STRINGS["options"]["step"]["settings"]["data"]
    for key, profile in SETUP_PROFILES.items():
        for question in profile.questions:
            labels = step["sections"]["advanced"]["data"] if question.advanced else step["data"]
            assert question.key in labels, (key, question.key)
            assert question.key in settings, (key, question.key)


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
