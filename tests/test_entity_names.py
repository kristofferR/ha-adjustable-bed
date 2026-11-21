"""Entity names describe the control in plain words (AGENTS.md, "Adding a New Bed Type").

Home Assistant prefixes the device name, so an entity name never repeats a
brand, app or controller, notes where a value came from, uses protocol
vocabulary or shouts. The same rules apply to state labels and to the Motion
Bed button names its controller builds at runtime.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.motion_bed.actions import MOTION_BED_ACTIONS
from custom_components.adjustable_bed.beds.motion_bed.controller import (
    button_actions_for,
    motion_bed_button_name,
)
from custom_components.adjustable_bed.labels import display_label

STRINGS = Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json"

BRANDS = (
    "FurniMove", "FSM Relax", "Reverie", "Pairlink", "HJBed", "GM Control", "Good Vibe",
    "MotoMotion", "Casper", "Galaxy", "Richmat", "Luuna", "SonicSleep", "Rize", "Smart Comfort",
    "CheersSleep", "Lunio", "Power Bob", "Okimiki", "Majestic", "MLILY", "SUTA", "ELEVATE",
    "Sleeptracker", "Okin", "OKIN", "Keeson", "Linak", "Jiecang", "Somos", "Nerum", "Sophie",
    "Linx", "Ultramatic", "Symphony", "Yamada", "Bedgear", "Logicdata", "LOGICDATA", "Vibradorm",
    "StarCode", "Starcode", "Leggett", "Malouf", "Limoss", "Octo", "Solace", "Svane", "Jensen",
    "Ergomotion", "Tempur", "Eshine", "BedSense", "Hush", "Paramount", "Sleepy", "Comfy", "Apex",
)
# Where a value came from belongs in docs and code comments, not the name.
PROVENANCE = re.compile(
    r"\((?:app\b[^)]*|reported|raw|draft|observed|home assistant|[^)]*\bicon|fresh status|"
    r"memory page|\d+ seconds?|wire unit[^)]*|physical effect unknown|signed)\)"
    r"|^(?:app|observed|reported|raw|retained)\b|\bmetadata\b",
    re.IGNORECASE,
)
PROTOCOL = re.compile(
    r"0x[0-9a-f]+|\bfield\b|\bbits?\s*\d|\bflag\d|\bbytes?\b|\bmask\b|\bcodes?\b|\bselector\b|"
    r"\bparser\b|\btransport\b|\bwire\b|\buart\b|\bprojection\b|\bparameter \d|\baxis \d|"
    r"\bpart \d|\bmotor channel\b|memorytype|\bhall units\b|\baddress \d|\bunprovisioned\b|"
    r"\benroll\b|\bgatem\b|\bgateo\b|\bkk\b|\baa\b|\bsn\b",
    re.IGNORECASE,
)
ACRONYMS = {"TV", "USB", "RGB", "LED", "BLE", "AI", "MAC", "PIN", "ID", "HZ", "KHZ", "DSP", "PCB"}
TITLE_ARTIFACTS = re.compile(r"\b(?:Tv|Ai|Eq|Usb|Rgb|Led|Ble|Mac)\b|\bAnti Snore\b|\bmac\b")


def problems(name: str) -> list[str]:
    """Return every naming rule ``name`` breaks."""
    found = [f"brand {brand!r}" for brand in BRANDS if re.search(rf"\b{re.escape(brand)}", name)]
    if PROVENANCE.search(name):
        found.append("provenance note")
    if match := PROTOCOL.search(name):
        found.append(f"protocol word {match.group(0)!r}")
    found += [
        f"all-caps {word!r}"
        for word in re.findall(r"\b[A-Z]{2,}\b", name)
        # Remote labels such as M1 or V15 are one letter and digits, so the
        # all-caps pattern never sees them; II and III are preset numbers.
        if word.upper() not in ACRONYMS and not re.fullmatch(r"M\d|[IVX]+", word)
    ]
    if match := TITLE_ARTIFACTS.search(name):
        found.append(f"title() artifact {match.group(0)!r}")
    if re.match(r"hold\b", name, re.IGNORECASE):
        found.append("'Hold ...' phrasing")
    return found


def _translated_names() -> list[tuple[str, str]]:
    entities = json.loads(STRINGS.read_text())["entity"]
    return [
        (f"{platform}.{key}{f' state {state}' if state else ''}", label)
        for platform, keys in entities.items()
        for key, entry in keys.items()
        for state, label in [(None, entry.get("name") or ""), *(entry.get("state") or {}).items()]
    ]


@pytest.mark.parametrize(
    ("label", "issues"),
    [
        ("Reverie: Wave Level", ["brand 'Reverie'"]),
        ("App state field 0x0B", ["provenance note", "protocol word 'field'"]),
        ("Part 16 Down", ["protocol word 'Part 1'"]),
        ("BACK LEG", ["all-caps 'BACK'", "all-caps 'LEG'"]),
        ("Usb on", ["title() artifact 'Usb'"]),
        ("Hold to increase head massage", ["'Hold ...' phrasing"]),
        ("Save M1 position on TV", []),
        ("V15", []),
    ],
)
def test_rules_flag_known_bad_names(label: str, issues: list[str]) -> None:
    assert problems(label) == issues


def test_translated_entity_names_and_states_follow_the_rules() -> None:
    offenders = {ref: issues for ref, label in _translated_names() if (issues := problems(label))}
    assert offenders == {}


def test_motion_bed_runtime_button_names_follow_the_rules() -> None:
    owners = frozenset(action.owner for action in MOTION_BED_ACTIONS)
    names = {
        key: display_label(motion_bed_button_name(key, action))
        for key, action in button_actions_for(owners).items()
    }
    assert {key: problems(name) for key, name in names.items() if problems(name)} == {}


async def test_runtime_action_labels_follow_the_rules() -> None:
    """Entities named after an app or manual label show its display form."""
    from custom_components.adjustable_bed.beds.entity_specs import ProductButtonSpec
    from tests.entity_translation_reachability import factory_controllers

    labels = {
        value
        for controller in await factory_controllers()
        for spec in controller.controller_button_specs
        for value in (
            [spec.name]
            if isinstance(spec, ProductButtonSpec) or spec.translation_key is None
            else list((spec.translation_placeholders or {}).values())
        )
    }
    offenders = {label: issues for label in labels if (issues := problems(display_label(label)))}
    assert offenders == {}


@pytest.mark.parametrize(
    ("label", "shown"),
    [
        ("Anti Snore (app gesture)", "Anti-snore"),
        ("Massage TIMER / ALL OFF", "Massage timer / all off"),
        ("Tv Iii", "TV III"),
        ("ZERO-G preset", "Zero G"),
        ("bed head-and-foot up pictogram", "Head and foot up"),
        ("Lumbar down (unlabeled touch area)", "Lumbar down"),
    ],
)
def test_display_label_drops_artifact_notes_and_shouting(label: str, shown: str) -> None:
    assert display_label(label) == shown


@pytest.mark.parametrize(
    ("code", "label", "name", "clear"),
    [
        # Labels that say part of what the code does take the code's name.
        (0x4C, "Head+", "Head massage intensity up", True),
        (0x4C, "Msg Head Intensity Inc", "Head massage intensity up", True),
        (0x48, "Mode", "Massage mode", True),
        (0xD3, "Next", "Next music track", True),
        (0x9D, "Low", "Heat low", True),
        # A toggle keeps the product's own button; a timer its own duration.
        (0x5E, "Start\\nStop", "Massage on/off", True),
        (0x5F, "Hour2", "Massage timer 2 hours", True),
        (0x5F, "Massage 10Min", "Massage timer 10 minutes", True),
        # A label naming another feature or action is not the code's control.
        (0x4C, "Back Fan", "Back fan", False),
        (0x5D, "Both massage off", "Both massage off", False),
    ],
)
def test_richmat_mh_controls_are_named_by_their_code(code: int, label: str, name: str, clear: bool) -> None:
    from custom_components.adjustable_bed.beds.richmat.labels import richmat_mh_name

    assert richmat_mh_name(code, label) == (name, clear)


@pytest.mark.parametrize(
    ("label", "name"),
    [
        ("Zg Back", "Zero gravity"),
        ("Zg Set", "Zero gravity"),
        ("Snore Back", "Anti-snore"),
        ("M2 Back", "Memory 2"),
        ("Zero Gravity Mode primary", "Zero gravity"),
        ("Xiaofeiyan", "Yoga"),
        ("Erlieving Stress", "Relieving stress"),
        ("Lull", "Sleep aid"),
        ("Sleeping", "Sleeping"),
    ],
)
def test_richmat_preset_labels_name_the_preset(label: str, name: str) -> None:
    from custom_components.adjustable_bed.beds.richmat.labels import preset_name

    assert preset_name(label) == name


# Every entity of every offline controller variant, built once for the checks below.
@pytest.fixture(scope="module")
def devices():
    import asyncio

    from tests.entity_surface import devices as build

    return asyncio.run(build())




def test_every_shown_name_follows_the_rules(devices) -> None:
    offenders = {
        (device.bed, entity.name): issues
        for device in devices
        for entity in device.entities
        if entity.name and (issues := problems(entity.name))
    }
    assert offenders == {}


def test_catalog_names_are_words_with_their_feature(devices) -> None:
    """An app's abbreviations and bare button words never become an entity name."""
    abbreviation = re.compile(r"\b(?:msg|inc|dec|zg\d*|mem|pos|min|mins)\b", re.IGNORECASE)
    bare = re.compile(
        r"mode|next|previous|switch|on/off|on off|up|down|low|medium|middle|high|off|on|"
        r"intensity|[+/-]+|start stop|start/stop|pause/start|\d+ ?(?:min|h)",
        re.IGNORECASE,
    )
    assert {
        (device.bed, entity.name)
        for device in devices
        for entity in device.entities
        if entity.translation_key is not None
        and entity.translation_key.startswith("catalog_")
        and entity.name
        and (abbreviation.search(entity.name) or bare.fullmatch(entity.name))
    } == set()


def test_one_device_never_shows_one_name_twice(devices) -> None:
    offenders = set()
    for device in devices:
        names = Counter(entity.name.casefold() for entity in device.entities if entity.name)
        offenders |= {(device.bed, name) for name, count in names.items() if count > 1}
    assert offenders == set()


def test_unique_ids_are_unique_on_every_device(devices) -> None:
    """Four MLILY remotes once listed the same control twice (one unique ID, two entities)."""
    offenders = set()
    for device in devices:
        ids = Counter((entity.domain, entity.unique_id) for entity in device.entities)
        offenders |= {(device.bed, key) for key, count in ids.items() if count > 1}
    assert offenders == set()


def test_no_entity_comes_from_an_empty_catalog_slot(devices) -> None:
    placeholder = re.compile(r"(?:no action|menu|.* menu|logo)(?: \d+)?", re.IGNORECASE)
    assert {
        (device.bed, entity.name)
        for device in devices
        for entity in device.entities
        if entity.name and placeholder.fullmatch(entity.name)
    } == set()


def test_catalog_controls_sit_with_what_they_are(devices) -> None:
    """A catalog's motor moves, presets and massage never fall back to the utility row."""
    shaped = re.compile(
        r"\b(?:up|down)$|\b(?:flat|zero g(?:ravity)?|tv|lounge|anti-snore|memory \d|m\d)\b"
        r"|\bmassage\b",
        re.IGNORECASE,
    )
    assert {
        (device.bed, entity.name)
        for device in devices
        for entity in device.entities
        if entity.domain == "button"
        and entity.translation_key in ("catalog_action", "remote_action")
        and entity.section == "utility"
        and entity.enabled
        and entity.name
        and shaped.search(entity.name)
    } == set()


def test_every_save_is_a_guarded_save(devices) -> None:
    """One rule: a save sits in a save role; the card confirms a preset save first.

    A memory slot's save needs no dialog: the card only offers it in Set mode.
    """
    offenders = set()
    for device in devices:
        for entity in device.entities:
            if entity.domain != "button" or entity.role != "save":
                continue
            confirms = entity.section == "presets"
            if entity.requires_confirmation is not confirms or entity.category != "config":
                offenders.add((device.bed, entity.name))
    assert offenders == set()


def test_catalog_extras_start_disabled(devices) -> None:
    """Music, fans, resets and the like are there to enable, not on every dashboard."""
    extra = re.compile(r"\b(?:music|fan|fans|bluetooth|volume|aromatherapy|reset)\b", re.IGNORECASE)
    assert {
        (device.bed, entity.name)
        for device in devices
        for entity in device.entities
        if entity.domain == "button"
        and entity.translation_key is not None
        and entity.translation_key.startswith("catalog_")
        and entity.enabled
        and entity.name
        and extra.search(entity.name)
        and not re.search(r"\bmassage\b|^save\b", entity.name, re.IGNORECASE)
    } == set()


def test_a_button_that_asks_first_offers_no_held_gesture(devices) -> None:
    """The card's hold path sends without its dialog, so a confirmed button never holds."""
    assert {
        (device.bed, entity.name)
        for device in devices
        for entity in device.entities
        if entity.requires_confirmation and entity.held
    } == set()
