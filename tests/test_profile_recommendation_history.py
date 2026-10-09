"""Replay closed-issue identities; evidence and limits are in the audit document."""

from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PROTOCOL_VARIANT,
    NORDIC_UART_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
)
from custom_components.adjustable_bed.profile_recommendations import (
    _recommendation_label,
    recommend_profile,
)


def observed(name, services=(), manufacturer=None):
    return SimpleNamespace(
        address="AA:BB:CC:DD:EE:30",
        name=name,
        service_uuids=list(services),
        manufacturer_data=manufacturer or {},
        service_data={},
    )


@pytest.mark.parametrize("selected", ["solace", "richmat"], ids=["issue73", "issue171"])
def test_rc2_wrong_profile_suggests_octo(selected):
    result = recommend_profile({CONF_BED_TYPE: selected}, observed("RC2"), {})
    assert result is not None and result.suggested == "octo"
    assert recommend_profile({CONF_BED_TYPE: "octo"}, observed("RC2"), {}) is None


@pytest.mark.parametrize(
    ("selected", "variant", "advertisement", "candidate"),
    [
        pytest.param(
            "okin_nordic",
            "auto",
            observed("Smartbed209008942", manufacturer={89: b""}),
            "okin_cb24",
            id="issue185",
        ),
        pytest.param(
            "bedtech",
            "auto",
            observed("QRRM141291", ["0000fee9-0000-1000-8000-00805f9b34fb"]),
            "richmat",
            id="issue194",
        ),
        pytest.param(
            "keeson",
            "sino",
            observed(
                "ORE-ac2170000d",
                [
                    "0000fff0-0000-1000-8000-00805f9b34fb",
                    "0000ffb0-0000-1000-8000-00805f9b34fb",
                ],
            ),
            "keeson:dynasty_bases",
            id="issue180",
        ),
        pytest.param(
            "okin_cb24",
            "auto",
            observed(
                "Smartbed428000193", [NORDIC_UART_SERVICE_UUID], {89: bytes.fromhex("4142010204")}
            ),
            "malouf_new_okin",
            id="issues47_393",
        ),
        pytest.param(
            "okin_cb35",
            "auto",
            observed("Star250000000001", [NORDIC_UART_SERVICE_UUID]),
            "sleepys_box25",
            id="issues372_413",
        ),
    ],
)
def test_ambiguous_history_contains_confirmed_route_without_choosing_winner(
    selected, variant, advertisement, candidate
):
    result = recommend_profile(
        {CONF_BED_TYPE: selected, CONF_PROTOCOL_VARIANT: variant}, advertisement, {}
    )
    assert result is not None and result.suggested is None
    assert candidate in result.choices


@pytest.mark.parametrize("variant", ["standard", "auto", "star2"])
def test_issue73_explicit_standard_reviews_star2_but_auto_and_star2_are_quiet(variant):
    result = recommend_profile(
        {CONF_BED_TYPE: "octo", CONF_PROTOCOL_VARIANT: variant},
        observed(
            "DA1458x\x00\x00\x00", [OCTO_STAR2_SERVICE_UUID], {24576: bytes.fromhex("52572d424c45")}
        ),
        {},
    )
    if variant == "standard":
        assert result is not None and result.suggested is None
        assert result.current == "octo:standard"
        assert result.choices == ("octo:auto", "octo:star2")
        assert "Standard Octo" in _recommendation_label(result.current)
        assert "Octo Remote Star2" in _recommendation_label(result.choices[1])
    else:
        assert result is None


@pytest.mark.parametrize("name", ["smart_dfu", "KSBT04C000001"])
def test_issue311_explicit_ksbt_review_includes_existing_ksbt04c_transport(name):
    result = recommend_profile(
        {CONF_BED_TYPE: "keeson", CONF_PROTOCOL_VARIANT: "ksbt"},
        observed(name, ["0000ffe5-0000-1000-8000-00805f9b34fb"]),
        {},
    )
    assert result is not None and result.suggested is None
    assert result.current == "keeson:ksbt"
    assert "keeson:ksbt04c" in result.choices
    assert "KSBT04C" in _recommendation_label("keeson:ksbt04c")


def test_standard_octo_without_star2_signature_is_not_questioned():
    assert (
        recommend_profile(
            {CONF_BED_TYPE: "octo", CONF_PROTOCOL_VARIANT: "standard"}, observed("RC2"), {}
        )
        is None
    )


def test_issue116_does_not_offer_identical_alias_as_a_remote_profile_improvement():
    result = recommend_profile(
        {CONF_BED_TYPE: "okin_uuid", CONF_PROTOCOL_VARIANT: "92471"},
        observed("OKIN Luis", [OKIMAT_SERVICE_UUID]),
        {},
    )
    assert result is not None and result.suggested is None
    assert "okimat" not in result.choices


@pytest.mark.parametrize("remote", ["auto", "qrrm", "LP-QRRM", "lp-qrrm", "BT6500"])
def test_issues194_504_560_review_unresolved_qrrm_layout_without_overriding_explicit_remote(remote):
    result = recommend_profile(
        {CONF_BED_TYPE: "richmat", CONF_PROTOCOL_VARIANT: "auto", "richmat_remote": remote},
        observed("QRRM106475"),
        {},
    )
    assert result is not None and result.suggested is None
    remote_choices = {choice for choice in result.choices if choice.startswith("richmat_remote:")}
    if remote in {"auto", "qrrm"}:
        assert remote_choices == {"richmat_remote:LP-QRRM", "richmat_remote:BT6500"}
        assert "Custom 1/2" in _recommendation_label("richmat_remote:LP-QRRM")
    else:
        assert not remote_choices


def test_qrrm_bedtech_signature_does_not_question_the_richmat_remote_layout():
    result = recommend_profile(
        {CONF_BED_TYPE: "richmat", "richmat_remote": "auto"},
        observed(
            "QRRM157738",
            ["0000fee9-0000-1000-8000-00805f9b34fb"],
            {19543: bytes.fromhex("54307651")},
        ),
        {},
    )
    assert result is not None and result.suggested == "bedtech"
    assert not any(choice.startswith("richmat_remote:") for choice in result.choices)


@pytest.mark.parametrize(
    ("selected", "advertisement"),
    [
        pytest.param("okimat", observed("OKIN-338977"), id="issue501_missing_passive_identity"),
        pytest.param("richmat", observed("Galaxy"), id="issue130_no_identity"),
        pytest.param(
            "motosleep",
            observed("Wyze Scale", ["0000fff0-0000-1000-8000-00805f9b34fb"]),
            id="issue187_scale",
        ),
        pytest.param(
            "motosleep",
            observed("Smart Watch", ["0000fff0-0000-1000-8000-00805f9b34fb"]),
            id="issue187_watch",
        ),
        pytest.param("bedtech", observed("DA14531"), id="issue296_not_a_bed"),
        pytest.param(
            "dewertokin",
            observed(
                "TT214H BlueFrog",
                ["00001523-0000-1000-8000-00805f9b34fb", "00001623-0000-1000-8000-00805f9b34fb"],
            ),
            id="issue450_coffee_machine",
        ),
        pytest.param(
            "okin_ore",
            observed(
                "Bedroom TV (1019)",
                ["00000000-deca-fade-deca-deafdecacafe", "00001000-0000-1000-8000-00805f9b34fb"],
                {76: bytes.fromhex("10050114fd180f")},
            ),
            id="issue577_apple_tv",
        ),
    ],
)
def test_missing_identity_and_non_beds_do_not_get_replacement_suggestions(selected, advertisement):
    assert recommend_profile({CONF_BED_TYPE: selected}, advertisement, {}) is None
