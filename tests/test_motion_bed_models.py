"""Source-bound Motion Bed selection and action predicates.

Expected callsite guards below come from the frozen COMMANDS branch predicates,
not from the production action catalogue or its postfreeze generator.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import fields, replace
from pathlib import Path
from typing import cast

import pytest

from custom_components.adjustable_bed.motion_bed_actions import MOTION_BED_ACTIONS
from custom_components.adjustable_bed.motion_bed_models import (
    RAW_NAME_MARKERS,
    accepts_motion_bed_name,
    motion_bed_saved_title,
    select_motion_bed,
)
from custom_components.adjustable_bed.motion_bed_protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.motion_bed_state import MotionBedState

_ACTION_FOR_SOURCE = {
    packet.source_id: action for action in MOTION_BED_ACTIONS for packet in action.packets
}
_SOURCE_IDS = tuple(
    cast(
        dict[str, str],
        json.loads(
            Path(__file__)
            .with_name("fixtures")
            .joinpath("motion_bed_protocol_vectors.json")
            .read_text()
        )["literal_commands"],
    )
)

# ConnectActivity.defindeBlueNameList and HomeActivity.setFragments, ordered.
_HOME_ROUTES = (
    (
        (
            "QMS-IQ",
            *(f"QMS-I{i}6" for i in range(10)),
            *(f"QMS-L{i}4" for i in range(10)),
            "QMS-LQ",
        ),
        "K1",
        "W1",
    ),
    (("QMS-JQ-D", "QMS4", "S4-N"), "K2M", "W2"),
    (("QMS-NQ", "QMS3"), "K2M", "W3"),
    (("QMS-MQ", "QMS2", "SealyMF"), "K2M", "W4"),
    (("QMS-KQ-H", "QMS-H02"), "K3", "W6"),
    (("QMS-DFQ", "QMS-430", "QMS-444"), "K4", "W7"),
    (("QMS-DQ", "QMS-443"), "K5", "W8"),
    (("S3-2",), "K2M", "W10"),
    (("S3-3",), "K8", "W11"),
    (("S3-4",), "K9", "W11"),
    (("S4-Y",), "K11", "W12"),
    (("S5-Y",), "K11", "W13"),
    (("S6-Y",), "K11", "W14"),
    (("S4-4",), "K2M", "W18"),
)
_MODULE_ROUTES = (("TL-Q", "hub"), ("TL-A", "air"), ("TL-B", "motor"), ("TL-W", "thermal"))
_ALTERNATE_SOURCE = {
    **{f"KuaijieK2Fragment:{line}": True for line in (213, 215, 217, 219, 221)},
    **{f"KuaijieK2Fragment:{line}": False for line in (223, 225, 227, 229, 231)},
    **{f"KuaijieK2MFragment:{line}": True for line in (266, 268, 270, 272, 274)},
    **{f"KuaijieK2MFragment:{line}": False for line in (276, 278, 280, 282, 284)},
}

# FROZEN_GUARD_TABLE
_SOURCE_GUARDS: dict[str, tuple[str, bool | int]] = {
    "DianDongSetActivity:557": ("massage_timer", 10),
    "DianDongSetActivity:559": ("massage_timer", -10),
    "DianDongSetActivity:569": ("massage_timer", 20),
    "DianDongSetActivity:571": ("massage_timer", -20),
    "DianDongSetActivity:581": ("massage_timer", 30),
    "DianDongSetActivity:583": ("massage_timer", -30),
    "AnmoFragment:88": ("sync_enabled", True),
    "AnmoFragment:90": ("sync_enabled", False),
    "AnmoFragment:165": ("massage_timer", 10),
    "AnmoFragment:167": ("massage_timer", -10),
    "AnmoFragment:177": ("massage_timer", 20),
    "AnmoFragment:179": ("massage_timer", -20),
    "AnmoFragment:189": ("massage_timer", 30),
    "AnmoFragment:191": ("massage_timer", -30),
    "DengguangFragment:99": ("sync_enabled", True),
    "DengguangFragment:101": ("sync_enabled", False),
    "DiandongFragment:578": ("memory_1", True),
    "DiandongFragment:580": ("memory_1", False),
    "DiandongFragment:594": ("memory_2", True),
    "DiandongFragment:596": ("memory_2", False),
    "DiandongFragment:610": ("tv", True),
    "DiandongFragment:612": ("tv", False),
    "DiandongFragment:626": ("zero_gravity", True),
    "DiandongFragment:628": ("zero_gravity", False),
    "DiandongFragment:648": ("snore", True),
    "DiandongFragment:650": ("snore", False),
    "DiandongFragment:663": ("zero_gravity", True),
    "DiandongFragment:665": ("zero_gravity", False),
    "DiandongFragment:672": ("snore", True),
    "DiandongFragment:674": ("snore", False),
    "DiandongFragment:681": ("tv", True),
    "DiandongFragment:683": ("tv", False),
    "DiandongFragment:690": ("memory_2", True),
    "DiandongFragment:692": ("memory_2", False),
    "DiandongFragment:699": ("memory_1", True),
    "DiandongFragment:701": ("memory_1", False),
    "KuaijieK11Fragment:50": ("sync_enabled", True),
    "KuaijieK11Fragment:52": ("sync_enabled", False),
    "KuaijieK11Fragment:136": ("memory_2", True),
    "KuaijieK11Fragment:138": ("memory_2", False),
    "KuaijieK11Fragment:145": ("memory_1", True),
    "KuaijieK11Fragment:147": ("memory_1", False),
    "KuaijieK11Fragment:243": ("memory_1", True),
    "KuaijieK11Fragment:255": ("memory_2", True),
    "KuaijieK11Fragment:268": ("tv", True),
    "KuaijieK11Fragment:270": ("tv", False),
    "KuaijieK11Fragment:285": ("zero_gravity", True),
    "KuaijieK11Fragment:287": ("zero_gravity", False),
    "KuaijieK11Fragment:326": ("snore", True),
    "KuaijieK11Fragment:328": ("snore", False),
    "KuaijieK11Fragment:341": ("zero_gravity", True),
    "KuaijieK11Fragment:343": ("zero_gravity", False),
    "KuaijieK11Fragment:350": ("snore", True),
    "KuaijieK11Fragment:352": ("snore", False),
    "KuaijieK11Fragment:359": ("tv", True),
    "KuaijieK11Fragment:361": ("tv", False),
    "KuaijieK1Fragment:50": ("sync_enabled", True),
    "KuaijieK1Fragment:52": ("sync_enabled", False),
    "KuaijieK1Fragment:136": ("memory_2", True),
    "KuaijieK1Fragment:138": ("memory_2", False),
    "KuaijieK1Fragment:145": ("memory_1", True),
    "KuaijieK1Fragment:147": ("memory_1", False),
    "KuaijieK1Fragment:237": ("memory_1", True),
    "KuaijieK1Fragment:249": ("memory_2", True),
    "KuaijieK1Fragment:262": ("tv", True),
    "KuaijieK1Fragment:264": ("tv", False),
    "KuaijieK1Fragment:279": ("zero_gravity", True),
    "KuaijieK1Fragment:281": ("zero_gravity", False),
    "KuaijieK1Fragment:326": ("snore", True),
    "KuaijieK1Fragment:328": ("snore", False),
    "KuaijieK1Fragment:341": ("zero_gravity", True),
    "KuaijieK1Fragment:343": ("zero_gravity", False),
    "KuaijieK1Fragment:350": ("snore", True),
    "KuaijieK1Fragment:352": ("snore", False),
    "KuaijieK1Fragment:359": ("tv", True),
    "KuaijieK1Fragment:361": ("tv", False),
    "KuaijieK2Fragment:46": ("sync_enabled", True),
    "KuaijieK2Fragment:48": ("sync_enabled", False),
    "KuaijieK2Fragment:127": ("memory_2", True),
    "KuaijieK2Fragment:129": ("memory_2", False),
    "KuaijieK2Fragment:136": ("memory_1", True),
    "KuaijieK2Fragment:138": ("memory_1", False),
    "KuaijieK2Fragment:258": ("memory_1", True),
    "KuaijieK2Fragment:270": ("memory_2", True),
    "KuaijieK2Fragment:283": ("tv", True),
    "KuaijieK2Fragment:285": ("tv", False),
    "KuaijieK2Fragment:300": ("zero_gravity", True),
    "KuaijieK2Fragment:302": ("zero_gravity", False),
    "KuaijieK2Fragment:317": ("snore", True),
    "KuaijieK2Fragment:319": ("snore", False),
    "KuaijieK2Fragment:332": ("zero_gravity", True),
    "KuaijieK2Fragment:334": ("zero_gravity", False),
    "KuaijieK2Fragment:341": ("snore", True),
    "KuaijieK2Fragment:343": ("snore", False),
    "KuaijieK2Fragment:350": ("tv", True),
    "KuaijieK2Fragment:352": ("tv", False),
    "KuaijieK2MFragment:64": ("sync_enabled", True),
    "KuaijieK2MFragment:66": ("sync_enabled", False),
    "KuaijieK2MFragment:166": ("memory_2", True),
    "KuaijieK2MFragment:168": ("memory_2", False),
    "KuaijieK2MFragment:175": ("memory_1", True),
    "KuaijieK2MFragment:177": ("memory_1", False),
    "KuaijieK2MFragment:317": ("memory_1", True),
    "KuaijieK2MFragment:329": ("memory_2", True),
    "KuaijieK2MFragment:342": ("tv", True),
    "KuaijieK2MFragment:344": ("tv", False),
    "KuaijieK2MFragment:359": ("zero_gravity", True),
    "KuaijieK2MFragment:361": ("zero_gravity", False),
    "KuaijieK2MFragment:389": ("snore", True),
    "KuaijieK2MFragment:391": ("snore", False),
    "KuaijieK2MFragment:404": ("zero_gravity", True),
    "KuaijieK2MFragment:406": ("zero_gravity", False),
    "KuaijieK2MFragment:413": ("snore", True),
    "KuaijieK2MFragment:415": ("snore", False),
    "KuaijieK2MFragment:422": ("tv", True),
    "KuaijieK2MFragment:424": ("tv", False),
    "KuaijieK3Fragment:46": ("sync_enabled", True),
    "KuaijieK3Fragment:48": ("sync_enabled", False),
    "KuaijieK3Fragment:125": ("memory_2", True),
    "KuaijieK3Fragment:127": ("memory_2", False),
    "KuaijieK3Fragment:134": ("memory_1", True),
    "KuaijieK3Fragment:136": ("memory_1", False),
    "KuaijieK3Fragment:221": ("memory_1", True),
    "KuaijieK3Fragment:233": ("memory_2", True),
    "KuaijieK3Fragment:246": ("tv", True),
    "KuaijieK3Fragment:248": ("tv", False),
    "KuaijieK3Fragment:263": ("zero_gravity", True),
    "KuaijieK3Fragment:265": ("zero_gravity", False),
    "KuaijieK3Fragment:290": ("zero_gravity", True),
    "KuaijieK3Fragment:292": ("zero_gravity", False),
    "KuaijieK3Fragment:299": ("tv", True),
    "KuaijieK3Fragment:301": ("tv", False),
    "KuaijieK4Fragment:55": ("sync_enabled", True),
    "KuaijieK4Fragment:57": ("sync_enabled", False),
    "KuaijieK4Fragment:229": ("left_tv", True),
    "KuaijieK4Fragment:231": ("left_tv", False),
    "KuaijieK4Fragment:245": ("left_tv", True),
    "KuaijieK4Fragment:247": ("left_tv", False),
    "KuaijieK4Fragment:261": ("left_tv", True),
    "KuaijieK4Fragment:263": ("left_tv", False),
    "KuaijieK4Fragment:277": ("right_tv", True),
    "KuaijieK4Fragment:279": ("right_tv", False),
    "KuaijieK4Fragment:332": ("left_tv", True),
    "KuaijieK4Fragment:334": ("left_tv", False),
    "KuaijieK4Fragment:341": ("right_tv", True),
    "KuaijieK4Fragment:343": ("right_tv", False),
    "KuaijieK4Fragment:350": ("left_zero_gravity", True),
    "KuaijieK4Fragment:352": ("left_zero_gravity", False),
    "KuaijieK4Fragment:359": ("right_zero_gravity", True),
    "KuaijieK4Fragment:361": ("right_zero_gravity", False),
    "KuaijieK5Fragment:57": ("sync_enabled", True),
    "KuaijieK5Fragment:59": ("sync_enabled", False),
    "KuaijieK5Fragment:204": ("left_memory", True),
    "KuaijieK5Fragment:216": ("left_memory", True),
    "KuaijieK5Fragment:229": ("left_tv", True),
    "KuaijieK5Fragment:231": ("left_tv", False),
    "KuaijieK5Fragment:245": ("left_tv", True),
    "KuaijieK5Fragment:247": ("left_tv", False),
    "KuaijieK5Fragment:261": ("left_tv", True),
    "KuaijieK5Fragment:263": ("left_tv", False),
    "KuaijieK5Fragment:277": ("right_tv", True),
    "KuaijieK5Fragment:279": ("right_tv", False),
    "KuaijieK5Fragment:300": ("left_memory", True),
    "KuaijieK5Fragment:312": ("left_memory", True),
    "KuaijieK5Fragment:357": ("left_tv", True),
    "KuaijieK5Fragment:360": ("left_tv", False),
    "KuaijieK5Fragment:368": ("right_tv", True),
    "KuaijieK5Fragment:371": ("right_tv", False),
    "KuaijieK5Fragment:379": ("left_memory", True),
    "KuaijieK5Fragment:382": ("left_memory", False),
    "KuaijieK5Fragment:390": ("coupled_left_memory", True),
    "KuaijieK5Fragment:393": ("coupled_left_memory", False),
    "KuaijieK5Fragment:401": ("right_memory", True),
    "KuaijieK5Fragment:404": ("right_memory", False),
    "KuaijieK5Fragment:412": ("coupled_right_memory", True),
    "KuaijieK5Fragment:415": ("coupled_right_memory", False),
    "KuaijieK8Fragment:46": ("sync_enabled", True),
    "KuaijieK8Fragment:48": ("sync_enabled", False),
    "KuaijieK8Fragment:125": ("memory_2", True),
    "KuaijieK8Fragment:127": ("memory_2", False),
    "KuaijieK8Fragment:134": ("memory_1", True),
    "KuaijieK8Fragment:136": ("memory_1", False),
    "KuaijieK8Fragment:223": ("memory_1", True),
    "KuaijieK8Fragment:235": ("memory_2", True),
    "KuaijieK8Fragment:248": ("tv", True),
    "KuaijieK8Fragment:250": ("tv", False),
    "KuaijieK8Fragment:265": ("zero_gravity", True),
    "KuaijieK8Fragment:267": ("zero_gravity", False),
    "KuaijieK8Fragment:292": ("zero_gravity", True),
    "KuaijieK8Fragment:294": ("zero_gravity", False),
    "KuaijieK8Fragment:301": ("tv", True),
    "KuaijieK8Fragment:303": ("tv", False),
    "KuaijieK9Fragment:47": ("sync_enabled", True),
    "KuaijieK9Fragment:49": ("sync_enabled", False),
    "KuaijieK9Fragment:126": ("memory_2", True),
    "KuaijieK9Fragment:128": ("memory_2", False),
    "KuaijieK9Fragment:135": ("memory_1", True),
    "KuaijieK9Fragment:137": ("memory_1", False),
    "KuaijieK9Fragment:227": ("memory_1", True),
    "KuaijieK9Fragment:239": ("memory_2", True),
    "KuaijieK9Fragment:252": ("tv", True),
    "KuaijieK9Fragment:254": ("tv", False),
    "KuaijieK9Fragment:269": ("zero_gravity", True),
    "KuaijieK9Fragment:271": ("zero_gravity", False),
    "KuaijieK9Fragment:298": ("snore", True),
    "KuaijieK9Fragment:300": ("snore", False),
    "KuaijieK9Fragment:313": ("zero_gravity", True),
    "KuaijieK9Fragment:315": ("zero_gravity", False),
    "KuaijieK9Fragment:322": ("tv", True),
    "KuaijieK9Fragment:324": ("tv", False),
    "QinangFragment:184": ("air_full_custom", True),
    "QinangFragment:186": ("air_full_custom", False),
    "QinangFragment:193": ("air_back_custom", True),
    "QinangFragment:195": ("air_back_custom", False),
    "SmartSleepFragment:144": ("sleep_enabled", True),
    "SmartSleepFragment:147": ("sleep_enabled", False),
    "SmartSleepFragment:156": ("night_light_enabled", True),
    "SmartSleepFragment:159": ("night_light_enabled", False),
    "WeitiaoW10Fragment:50": ("sync_enabled", True),
    "WeitiaoW10Fragment:52": ("sync_enabled", False),
    "WeitiaoW11Fragment:50": ("sync_enabled", True),
    "WeitiaoW11Fragment:52": ("sync_enabled", False),
    "WeitiaoW12Fragment:49": ("sync_enabled", True),
    "WeitiaoW12Fragment:51": ("sync_enabled", False),
    "WeitiaoW13Fragment:80": ("sync_enabled", True),
    "WeitiaoW13Fragment:82": ("sync_enabled", False),
    "WeitiaoW14Fragment:80": ("sync_enabled", True),
    "WeitiaoW14Fragment:82": ("sync_enabled", False),
    "WeitiaoW18Fragment:78": ("sync_enabled", True),
    "WeitiaoW18Fragment:80": ("sync_enabled", False),
    "WeitiaoW1Fragment:78": ("sync_enabled", True),
    "WeitiaoW1Fragment:80": ("sync_enabled", False),
    "WeitiaoW2Fragment:78": ("sync_enabled", True),
    "WeitiaoW2Fragment:80": ("sync_enabled", False),
    "WeitiaoW3Fragment:78": ("sync_enabled", True),
    "WeitiaoW3Fragment:80": ("sync_enabled", False),
    "WeitiaoW4Fragment:47": ("sync_enabled", True),
    "WeitiaoW4Fragment:49": ("sync_enabled", False),
    "WeitiaoW6Fragment:47": ("sync_enabled", True),
    "WeitiaoW6Fragment:49": ("sync_enabled", False),
    "WeitiaoW7Fragment:76": ("sync_enabled", True),
    "WeitiaoW7Fragment:78": ("sync_enabled", False),
    "WeitiaoW8Fragment:75": ("sync_enabled", True),
    "WeitiaoW8Fragment:77": ("sync_enabled", False),
}
_ONE_SHOT_WEITIAO_IDS: tuple[str, ...] = (
    "WeitiaoW10Fragment:50",
    "WeitiaoW10Fragment:52",
    "WeitiaoW11Fragment:50",
    "WeitiaoW11Fragment:52",
    "WeitiaoW12Fragment:49",
    "WeitiaoW12Fragment:51",
    "WeitiaoW13Fragment:80",
    "WeitiaoW13Fragment:82",
    "WeitiaoW13Fragment:304",
    "WeitiaoW13Fragment:310",
    "WeitiaoW13Fragment:316",
    "WeitiaoW13Fragment:322",
    "WeitiaoW14Fragment:80",
    "WeitiaoW14Fragment:82",
    "WeitiaoW14Fragment:304",
    "WeitiaoW14Fragment:310",
    "WeitiaoW14Fragment:316",
    "WeitiaoW14Fragment:322",
    "WeitiaoW18Fragment:78",
    "WeitiaoW18Fragment:80",
    "WeitiaoW18Fragment:250",
    "WeitiaoW18Fragment:256",
    "WeitiaoW18Fragment:262",
    "WeitiaoW18Fragment:268",
    "WeitiaoW1Fragment:78",
    "WeitiaoW1Fragment:80",
    "WeitiaoW1Fragment:250",
    "WeitiaoW1Fragment:256",
    "WeitiaoW1Fragment:262",
    "WeitiaoW1Fragment:268",
    "WeitiaoW2Fragment:78",
    "WeitiaoW2Fragment:80",
    "WeitiaoW2Fragment:250",
    "WeitiaoW2Fragment:256",
    "WeitiaoW2Fragment:262",
    "WeitiaoW2Fragment:268",
    "WeitiaoW3Fragment:78",
    "WeitiaoW3Fragment:80",
    "WeitiaoW3Fragment:249",
    "WeitiaoW3Fragment:255",
    "WeitiaoW3Fragment:261",
    "WeitiaoW3Fragment:267",
    "WeitiaoW4Fragment:47",
    "WeitiaoW4Fragment:49",
    "WeitiaoW6Fragment:47",
    "WeitiaoW6Fragment:49",
    "WeitiaoW7Fragment:76",
    "WeitiaoW7Fragment:78",
    "WeitiaoW8Fragment:75",
    "WeitiaoW8Fragment:77",
)


def test_complete_source_bindings_without_duplication() -> None:
    counts = Counter(packet.source_id for action in MOTION_BED_ACTIONS for packet in action.packets)
    assert set(counts) == set(_SOURCE_IDS) == set(SOURCE_COMMANDS)
    assert len(counts) == 716
    assert all(count == 1 for count in counts.values())
    assert len({action.key for action in MOTION_BED_ACTIONS}) == len(MOTION_BED_ACTIONS)


@pytest.mark.parametrize("source_id", _SOURCE_IDS)
@pytest.mark.parametrize("alternate", (False, True))
@pytest.mark.parametrize("selected", (False, True))
def test_every_source_callsite_executes_its_artifact_guard(
    source_id: str, alternate: bool, selected: bool
) -> None:
    action = _ACTION_FOR_SOURCE[source_id]
    state = MotionBedState()
    expected = True
    if source_id in _SOURCE_GUARDS:
        field, value = _SOURCE_GUARDS[source_id]
        if type(value) is int:
            minute = abs(value) if selected else None
            state = replace(state, **{field: minute})
            expected = selected if value > 0 else not selected
        else:
            state = replace(state, **{field: selected})
            expected = selected == value
    if source_id in _ALTERNATE_SOURCE:
        expected = expected and alternate == _ALTERNATE_SOURCE[source_id]
    assert (source_id in action.select(state, alternate)) == expected
    assert action.owner == source_id.split(":")[0]


@pytest.mark.parametrize("source_id, guard", _SOURCE_GUARDS.items())
def test_selected_guard_does_not_read_unrelated_flags(
    source_id: str, guard: tuple[str, bool | int]
) -> None:
    key, expected = guard
    if type(expected) is int:
        return
    action = _ACTION_FOR_SOURCE[source_id]
    flags = {
        field.name: True
        for field in fields(MotionBedState)
        if field.type in ("bool", "bool | None")
    }
    flags[key] = expected
    state = replace(MotionBedState(), **flags)
    assert source_id in action.select(state, False)
    flags[key] = not expected
    state = replace(MotionBedState(), **flags)
    assert source_id not in action.select(state, False)


@pytest.mark.parametrize("source_id", _ONE_SHOT_WEITIAO_IDS)
def test_layout_sync_and_cycle_actions_have_no_motor_hold(source_id: str) -> None:
    assert _ACTION_FOR_SOURCE[source_id].kind == "press"


def test_whitelist_matches_all_forty_eight_case_sensitive_source_markers() -> None:
    expected = {marker for markers, _, _ in _HOME_ROUTES for marker in markers} | {
        marker for marker, _ in _MODULE_ROUTES
    }
    assert set(RAW_NAME_MARKERS) == expected
    assert len(RAW_NAME_MARKERS) == len(expected) == 48
    for marker in expected:
        assert accepts_motion_bed_name(marker)
        assert accepts_motion_bed_name(f"interior_{marker}_suffix")
        assert not accepts_motion_bed_name(marker.lower())
    for name in ("", "FFE1", "Unknown bed", "QMS-I07", "QMS-L05"):
        assert not accepts_motion_bed_name(name)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("<:;=>?", "CABDEF"),
        ("QMS3-N93-327:;<=>?", "QMS3-N93-327ABCDE F".replace(" ", "")),
        ("SealyMF", "SealyMF"),
    ],
)
def test_all_saved_title_character_transforms(raw: str, expected: str) -> None:
    assert motion_bed_saved_title(raw) == expected


@pytest.mark.parametrize("markers, preset, movement", _HOME_ROUTES)
def test_every_home_selector_and_interior_name(
    markers: tuple[str, ...], preset: str, movement: str
) -> None:
    for marker in markers:
        selection = select_motion_bed(f"prefix_{marker}_suffix")
        assert (selection.surface, selection.preset, selection.movement) == (
            "home",
            preset,
            movement,
        )
        assert {"home", "preset", "massage", "light", "smart_sleep"} <= selection.route.contexts


@pytest.mark.parametrize("marker, surface", _MODULE_ROUTES)
def test_module_navigation_precedes_home_selection(marker: str, surface: str) -> None:
    for home in ("QMS-IQ", "QMS4", "QMS3", "SealyMF", "S4-Y"):
        result = select_motion_bed(f"{home}_{marker}")
        assert (result.surface, result.preset, result.movement) == (surface, "modular", "modular")


def test_every_ordered_home_precedence_pair() -> None:
    for index, (markers, preset, movement) in enumerate(_HOME_ROUTES):
        for lower, _, _ in _HOME_ROUTES[index + 1 :]:
            result = select_motion_bed(f"{lower[0]}_{markers[0]}")
            assert (result.preset, result.movement) == (preset, movement)
    assert select_motion_bed("TL-W_TL-B_TL-A_TL-Q").surface == "hub"
    assert select_motion_bed("TL-W_TL-B_TL-A").surface == "air"
    assert select_motion_bed("TL-W_TL-B").surface == "motor"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("QMS-MQ", True),
        ("QMS2", True),
        ("S3-2", True),
        ("QMS3", True),
        ("QMS3-N93-327", True),
        ("QMS-NQ", False),
        ("QMS4", False),
        ("SealyMF", False),
    ],
)
def test_alternate_reply_identity_is_separate_from_preset_selection(
    name: str, expected: bool
) -> None:
    result = select_motion_bed(name)
    assert result.alternate_identity is expected
    assert result.route.alternate_identity is expected
    assert result.preset == ("K2" if name == "QMS3-N93-327" else "K2M")
    retained = select_motion_bed(name, preset_override="K2")
    assert retained.alternate_identity is expected


def test_explicit_same_target_retained_layouts_and_restored_fallback() -> None:
    assert select_motion_bed("", restored=True).preset == "K1"
    assert select_motion_bed("unrecognized restored title", restored=True).preset == "K2M"
    with pytest.raises(ValueError):
        select_motion_bed("unrecognized newly discovered title")
    result = select_motion_bed("QMS3", preset_override="K2", movement_override="W4")
    assert (result.surface, result.preset, result.movement) == ("home", "K2", "W4")
    for name, preset, movement in (
        ("TL-Q", "K2", None),
        ("TL-B", None, "W2"),
        ("QMS4", "modular", None),
        ("QMS4", None, "modular"),
    ):
        with pytest.raises(ValueError):
            select_motion_bed(name, preset_override=preset, movement_override=movement)


@pytest.mark.parametrize(
    "source_id", [key for key in _SOURCE_GUARDS if _ACTION_FOR_SOURCE[key].kind == "program"]
)
def test_program_branches_are_explicit_and_state_independent(source_id: str) -> None:
    action = _ACTION_FOR_SOURCE[source_id]
    assert action.kind == "program"
    state = MotionBedState()
    for branch in ("save", "clear"):
        source_ids = action.select(state, False, branch=branch)
        assert len(source_ids) == 1
        field, expected = _SOURCE_GUARDS[source_ids[0]]
        assert expected == (branch == "clear")
        assert source_ids == action.select(
            replace(state, **{field: not expected}), False, branch=branch
        )


@pytest.mark.parametrize(
    "source_id",
    (
        "KuaijieK4Fragment:245",
        "KuaijieK4Fragment:261",
        "KuaijieK4Fragment:277",
        "KuaijieK5Fragment:216",
        "KuaijieK5Fragment:300",
        "KuaijieK5Fragment:312",
    ),
)
def test_cross_field_short_recall_reads_exact_artifact_widget(source_id: str) -> None:
    action = _ACTION_FOR_SOURCE[source_id]
    assert action.kind == "press"
    key, expected = _SOURCE_GUARDS[source_id]
    assert expected is True
    assert source_id not in action.select(
        replace(
            MotionBedState(
                right_tv=True,
                left_zero_gravity=True,
                right_zero_gravity=True,
                right_memory=True,
                coupled_left_memory=True,
                coupled_right_memory=True,
            ),
            **{key: False},
        ),
        False,
    )
    assert source_id in action.select(replace(MotionBedState(), **{key: True}), False)
    with pytest.raises(ValueError):
        action.select(MotionBedState(), False, branch="save")


@pytest.mark.parametrize(
    "owner, first_true, first_false",
    [("KuaijieK2Fragment", 213, 223), ("KuaijieK2MFragment", 266, 276)],
)
def test_alternate_status_queries_preserve_source_order(
    owner: str, first_true: int, first_false: int
) -> None:
    action = _ACTION_FOR_SOURCE[f"{owner}:{first_true}"]
    assert action.kind == "query"
    for alternate, first in ((True, first_true), (False, first_false)):
        assert action.select(MotionBedState(), alternate) == tuple(
            f"{owner}:{first + 2 * offset}" for offset in range(5)
        )


def test_all_program_actions_have_both_source_branches() -> None:
    programs = [action for action in MOTION_BED_ACTIONS if action.kind == "program"]
    assert len(programs) == 49
    for action in programs:
        assert len(action.select(MotionBedState(), False, branch="save")) == 1
        assert len(action.select(MotionBedState(), False, branch="clear")) == 1


def test_audio_queries_and_previews_are_press_or_query_not_preset_programming() -> None:
    for action in MOTION_BED_ACTIONS:
        if "audio" in action.key:
            assert action.kind in ("press", "query")
            with pytest.raises(ValueError):
                action.select(MotionBedState(), False, branch="clear")


@pytest.mark.parametrize(
    "source_id",
    [
        source_id
        for source_id, (field, expected) in _SOURCE_GUARDS.items()
        if field in ("sync_enabled", "sleep_enabled", "night_light_enabled") and expected is False
    ],
)
def test_app_boolean_selection_defaults_false_without_claiming_reported_state(
    source_id: str,
) -> None:
    state = MotionBedState()
    action = _ACTION_FOR_SOURCE[source_id]
    field, _ = _SOURCE_GUARDS[source_id]
    assert getattr(state, field) is None
    assert source_id in action.select(state, False)
    assert getattr(state, field) is None
    assert source_id not in action.select(replace(state, **{field: True}), False)


def test_music_short_recall_and_long_audio_stop_are_distinct_closed_actions() -> None:
    # KuaijieK2MFragment.onTouch373/375: short UP (<2000ms) versus long UP.
    short = _ACTION_FOR_SOURCE["KuaijieK2MFragment:373"]
    long = _ACTION_FOR_SOURCE["KuaijieK2MFragment:375"]
    assert short.key != long.key
    assert short.kind == long.kind == "press"
    assert short.select(MotionBedState(), False) == ("KuaijieK2MFragment:373",)
    assert long.select(MotionBedState(), False) == ("KuaijieK2MFragment:375",)
    assert SOURCE_COMMANDS["KuaijieK2MFragment:373"] == bytes.fromhex("FFFFFFFF0100130BFF1A05")
    assert SOURCE_COMMANDS["KuaijieK2MFragment:375"] == bytes.fromhex("FFFFFFFF0100130B001B04")
    assert long.name == "Stop audio"
