"""Every execution-capability declaration needs reviewed evidence (#483, #516).

``EVIDENCE`` maps each bed type or family profile that declares a capability
to the keys proving it, per declared field. Keys are defined in the
"Evidence keys" section of ``docs/design/execution-capabilities.md``. A
declaration without a row fails here, so adding a capability needs a reviewed
evidence row, and a row whose declaration is gone fails too.

Profiles are identified as ``"<ProfileClass>:<key>"``; standalone controllers
by bed type. Runtime checks cover every bed type and app route; a source scan
also requires each place that declares a capability to be listed in
``DECLARATION_SITES``, so variants, layouts and runtime-built profiles cannot
declare one unreviewed.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES, VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.execution import (
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from custom_components.adjustable_bed.profiles import keeson as keeson_profiles
from tests.codec_families import families
from tests.test_controller_contract import (
    _create_controller_for_bed_type,
    _FactoryCoordinator,
    _make_connected_client,
)

FAMILIES = families()
APP_ROUTES = {
    bed_type: route for family in FAMILIES.values() for bed_type, route in family.app_routes.items()
}
DESIGN = Path(__file__).parents[1] / "docs" / "design" / "execution-capabilities.md"

# Declaration -> declared field -> evidence keys from the design document.
EVIDENCE: dict[str, Mapping[str, tuple[str, ...]]] = {
    # Rows sort by identity, so parallel declarations merge cleanly.
    # Jiecang F1: Comfort Motion (jcbed PARTIAL) and the legacy route stay blocked.
    "JiecangProfile:dreamask": {"hold": ("dreamask",)},
    "JiecangProfile:dreamhd": {"hold": ("dreamhd",)},
    "JiecangProfile:dreamotion": {"hold": ("dreamotion",)},
    # Limoss DD (L1). The legacy ``limoss`` route keeps finite pulses: its
    # cadence is the entry's pulse settings, not the app's.
    "LimossProfile:fsm_relax": {"hold": ("fsm",)},
    "LimossProfile:limoss_remote": {"hold": ("limoss",)},
    "LogicdataProfile:phone": {"hold": ("ld-phone",)},
    "LogicdataProfile:sleep_smart": {"hold": ("ld-mattress",)},
    "LogicdataProfile:tablet": {"hold": ("ld-pad",)},
    # Okin 5A (O2). Nectar and MF900 evidence reaches the Okin CST frame, not
    # the 5A keys those profiles send, so only ELEVATE declares.
    "Okin5AProfile:star_elevate": {"hold": ("abm5_5", "m1x12")},
    # Okin N-frame (#483): each app streams a held key until release. Nectar
    # Move is the Nectar app's CST route.
    "OkinNFrameProfile:adjustable_lumbar_okin": {"hold": ("lumbar",)},
    "OkinNFrameProfile:adjustable_lumbar_star": {"hold": ("lumbar",)},
    "OkinNFrameProfile:clarity": {"hold": ("clarity", "row028")},
    "OkinNFrameProfile:cst_aviada": {"hold": ("aviada",)},
    "OkinNFrameProfile:cst_bob": {"hold": ("bob",)},
    "OkinNFrameProfile:cst_carefree": {"hold": ("carefree",)},
    "OkinNFrameProfile:cst_clarity": {"hold": ("iiclarity",)},
    "OkinNFrameProfile:cst_contempo": {"hold": ("contempo",)},
    "OkinNFrameProfile:cst_mf900": {"hold": ("mf900",)},
    "OkinNFrameProfile:cst_nectar_move": {"hold": ("nectar", "row042")},
    "OkinNFrameProfile:cst_resident": {"hold": ("resident",)},
    "OkinNFrameProfile:cst_sanctuary": {"hold": ("sanctuary",)},
    "OkinNFrameProfile:cst_support": {"hold": ("support",)},
    "OkinNFrameProfile:jeromes": {"hold": ("jeromes", "row028")},
    "OkinNFrameProfile:prodigy2": {"hold": ("p2", "leggett-disp")},
    "OkinNFrameProfile:prodigy2l": {"hold": ("p2l", "leggett-disp")},
    "OkinNFrameProfile:prodigy4": {
        "hold": ("p4", "leggett-disp", "#483c"),
        # CU170 watchdog onset measured on hardware: 217-218 ms.
        "sustain_ms": ("#368", "#483c", "#516c"),
    },
    "OkinNFrameProfile:remedy": {"hold": ("remedy", "row028")},
    "OkinNFrameProfile:serenity": {"hold": ("serenity",)},
    "OkinNFrameProfile:simmons_okin": {"hold": ("simmons",)},
    "OkinNFrameProfile:simmons_smartbed": {"hold": ("simmons",)},
    "OkinNFrameProfile:starcode_abm5_4": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box1220": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box15": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box25": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box3633": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:tranquil": {"hold": ("tranquil",)},
    "OkinNFrameProfile:useries": {"hold": ("useries", "leggett-disp")},
    "OkinNFrameProfile:zseries_z230": {"hold": ("glory",)},
    "OkinNFrameProfile:zseries_z280": {"hold": ("glory",)},
    # Both Sleepy's BOX25 dialects, declared on the controller.
    "sleepys_box25": {"hold": ("sleepy",)},
}

_ABM = tuple(identity for identity in EVIDENCE if identity.startswith("OkinNFrameProfile:starcode"))
# Okin CST and the OKIN Bedding apps (Serenity, Tranquil, Z-Series) share ``_cst``.
_CST = tuple(
    identity
    for identity in EVIDENCE
    if identity.startswith("OkinNFrameProfile:cst_")
    or identity.removeprefix("OkinNFrameProfile:")
    in ("serenity", "tranquil", "zseries_z230", "zseries_z280")
)
_CUSTOMATIC = (
    "OkinNFrameProfile:clarity",
    "OkinNFrameProfile:jeromes",
    "OkinNFrameProfile:remedy",
)
_LEGGETT_STREAM = (
    "OkinNFrameProfile:prodigy2",
    "OkinNFrameProfile:prodigy2l",
    "OkinNFrameProfile:useries",
)
_LUMBAR = (
    "OkinNFrameProfile:adjustable_lumbar_okin",
    "OkinNFrameProfile:adjustable_lumbar_star",
)
_SIMMONS = ("OkinNFrameProfile:simmons_okin", "OkinNFrameProfile:simmons_smartbed")

# Source site -> the EVIDENCE identities it declares. A site is
# "<path under custom_components/adjustable_bed>:<enclosing name>". Runtime
# enumeration cannot reach every variant, layout or product, so every place
# that can declare a capability must be listed and reviewed here.
DECLARATION_SITES: dict[str, tuple[str, ...]] = {
    "beds/sleepys_box25.py:<module>.SleepysBox25Controller": ("sleepys_box25",),
    "profiles/jiecang.py:<module>.DREAMASK": ("JiecangProfile:dreamask",),
    "profiles/jiecang.py:<module>.DREAMHD": ("JiecangProfile:dreamhd",),
    "profiles/jiecang.py:<module>.DREAMOTION": ("JiecangProfile:dreamotion",),
    "profiles/limoss.py:<module>.FSM_RELAX": ("LimossProfile:fsm_relax",),
    "profiles/limoss.py:<module>.LIMOSS_REMOTE": ("LimossProfile:limoss_remote",),
    "profiles/logicdata.py:<module>.PHONE": ("LogicdataProfile:phone",),
    "profiles/logicdata.py:<module>.SLEEP_SMART": ("LogicdataProfile:sleep_smart",),
    "profiles/logicdata.py:<module>.TABLET": ("LogicdataProfile:tablet",),
    "profiles/okin_5a.py:<module>.ELEVATE": ("Okin5AProfile:star_elevate",),
    "profiles/okin_nframe.py:<module>.CU170_EXECUTION": ("OkinNFrameProfile:prodigy4",),
    "profiles/okin_nframe.py:<module>.CUSTOMATIC_EXECUTION": _CUSTOMATIC,
    "profiles/okin_nframe.py:<module>.LEGGETT_EXECUTION": _LEGGETT_STREAM,
    "profiles/okin_nframe.py:<module>._abm": _ABM,
    "profiles/okin_nframe.py:<module>._cst": _CST,
    "profiles/okin_nframe.py:<module>._customatic": _CUSTOMATIC,
    "profiles/okin_nframe.py:<module>._leggett": (*_LEGGETT_STREAM, "OkinNFrameProfile:prodigy4"),
    "profiles/okin_nframe.py:<module>._lumbar": _LUMBAR,
    "profiles/okin_nframe.py:<module>._simmons": _SIMMONS,
}

PACKAGE = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
CAPABILITY_FIELDS = frozenset({"hold", "sustain_ms", "concurrent"})
# Family profiles have their own ``hold`` timing field, so only these names
# identify a replace() of a declaration.
DISTINCT_FIELDS = frozenset({"execution", "sustain_ms", "concurrent"})


def _design_evidence_keys() -> frozenset[str]:
    """Keys of both tables in the design's "Evidence keys" section."""
    section = DESIGN.read_text().split("\n## Evidence keys\n", 1)[1]
    keys = {
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"\|\s*([^|\s]+)\s*\|", line))
    }
    return frozenset(keys - {"Key", "---"})


def _instances(value: object, cls: type, depth: int = 0) -> Iterator[object]:
    if isinstance(value, cls):
        yield value
    elif depth < 2 and isinstance(value, Mapping):
        for item in value.values():
            yield from _instances(item, cls, depth + 1)
    elif depth < 2 and isinstance(value, (tuple, list, frozenset, set)):
        for item in value:
            yield from _instances(item, cls, depth + 1)


async def _family_profiles() -> dict[str, ExecutionCapabilities]:
    """Every reachable family profile's declaration, by identity.

    Static profiles are found in their modules; profiles built at runtime are
    reached through each bed type's and app route's controller.
    """
    registered = {cls for family in FAMILIES.values() for cls in family.profiles}
    profiles = [
        profile
        for cls in registered
        for value in vars(sys.modules[cls.__module__]).values()
        for profile in _instances(value, cls)
    ]
    for bed_type in SUPPORTED_BED_TYPES:
        profiles.append(getattr(await _create_controller_for_bed_type(bed_type), "profile", None))
    # Layouts are built at runtime and never stored; reach every one.
    profiles.extend(
        keeson_profiles.app_profile(app, layout)
        for app, layouts in keeson_profiles.APP_LAYOUTS.items()
        for layout in layouts
    )
    for bed_type, (config_key, choices) in APP_ROUTES.items():
        for choice in choices:
            coordinator = _FactoryCoordinator()
            coordinator.entry.data[config_key] = choice
            controller = await create_controller(
                coordinator, bed_type, VARIANT_AUTO, _make_connected_client()
            )
            profiles.append(getattr(controller, "profile", None))

    declared: dict[str, ExecutionCapabilities] = {}
    for profile in profiles:
        if type(profile) not in registered:
            continue
        execution = getattr(profile, "execution", None)
        assert isinstance(execution, ExecutionCapabilities), profile
        identity = _identity(profile)
        # One identity must not carry two different declarations.
        assert declared.setdefault(identity, execution) == execution, identity
    # Vectors are frozen per profile key, so the scan must reach every
    # profile that has them. Otherwise a declaration could hide.
    for name, family in FAMILIES.items():
        reached = {
            identity.split(":", 1)[1].split("@", 1)[0]
            for identity in declared
            if identity.split(":", 1)[0] in {cls.__name__ for cls in family.profiles}
        }
        frozen = {key for vectors in family.profiles.values() for key in vectors}
        assert frozen <= reached, (name, frozen - reached)
    return declared


def _identity(profile: object) -> str:
    """Profile class and key, plus the layout when one key has several."""
    identity = f"{type(profile).__name__}:{getattr(profile, 'key', None)}"
    layout = getattr(profile, "layout", None)
    return f"{identity}@{layout}" if isinstance(layout, str) else identity


async def _declarations() -> dict[str, frozenset[str]]:
    return {
        identity: execution.declared
        for identity, execution in (await _family_profiles()).items()
        if execution.declared
    }


def test_evidence_keys_exist_in_design() -> None:
    known = _design_evidence_keys()
    assert {"p4", "useries", "clarity", "svane"} <= known
    for identity, fields in EVIDENCE.items():
        for name, keys in fields.items():
            assert keys, f"{identity}.{name} needs at least one evidence key"
            assert not set(keys) - known, (identity, name, set(keys) - known)


async def test_every_profile_declaration_has_evidence() -> None:
    for identity, declared in (await _declarations()).items():
        assert identity in EVIDENCE, f"{identity} declares {sorted(declared)} without evidence"
        assert set(EVIDENCE[identity]) == declared, (identity, sorted(declared))


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_every_controller_declaration_has_evidence(bed_type: str) -> None:
    """A controller declares through its family profile, or has its own row."""
    controller = await _create_controller_for_bed_type(bed_type)
    execution = controller.execution
    assert isinstance(execution, ExecutionCapabilities)
    if not execution.declared:
        return
    profile = getattr(controller, "profile", None)
    registered = {cls for family in FAMILIES.values() for cls in family.profiles}
    if type(profile) in registered and getattr(profile, "execution", None) is execution:
        identity = _identity(profile)
    else:
        identity = bed_type
    assert identity in EVIDENCE, f"{identity} declares {sorted(execution.declared)}"
    assert set(EVIDENCE[identity]) == execution.declared, identity


STREAM_HOOKS = ("stream_tick_s", "write_stream_tick", "end_stream_member", "release_stream")


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_concurrent_declaration_implements_the_stream_hooks(bed_type: str) -> None:
    """A controller that merges motors must compose its own frames (#516)."""
    controller = await _create_controller_for_bed_type(bed_type)
    if not controller.execution.concurrent:
        return
    for hook in STREAM_HOOKS:
        assert getattr(type(controller), hook) is not getattr(BedController, hook), (
            bed_type,
            hook,
        )


async def test_evidence_rows_match_live_declarations() -> None:
    """A row whose declaration was removed must go too."""
    assert {identity for identity in EVIDENCE if ":" in identity} <= set(await _declarations())
    assert {identity for identity in EVIDENCE if ":" not in identity} <= set(
        SUPPORTED_BED_TYPES
    )


def _declaration_sites(root: Path = PACKAGE) -> dict[str, set[str]]:
    """Every source site that constructs, passes, assigns or overrides a declaration.

    Maps each site to the capability fields its ``ExecutionCapabilities`` calls
    name, so a conditional or layout-specific field cannot hide behind a
    reviewed site. ``"**"`` marks a call whose fields cannot be read.
    """
    sites: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "execution.py":
            continue
        tree = ast.parse(path.read_text(), filename=relative)
        for scope, node in _walk_scoped(tree, "<module>"):
            if _names_field_by_string(node):
                # A field named by string (a ``**{...}`` key, setattr) is unreadable.
                sites.setdefault(f"{relative}:{scope}", set()).add("**")
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                    node.func.id if isinstance(node.func, ast.Name) else ""
                )
                site = f"{relative}:{scope}"
                if name == "ExecutionCapabilities" and (node.args or node.keywords):
                    fields = sites.setdefault(site, set())
                    fields.update(keyword.arg or "**" for keyword in node.keywords)
                    if node.args:
                        fields.add("**")
                if any(keyword.arg == "execution" for keyword in node.keywords):
                    sites.setdefault(site, set())
                source = ast.unparse(node)
                if name in ("replace", "__replace__") and (
                    "execution" in source.lower()
                    or any(keyword.arg in DISTINCT_FIELDS for keyword in node.keywords)
                ):
                    # replace() can add a field to a reviewed declaration.
                    fields = sites.setdefault(site, set())
                    fields.update(
                        keyword.arg if keyword.arg is not None else "**"
                        for keyword in node.keywords
                        if keyword.arg is None or keyword.arg in CAPABILITY_FIELDS
                    )
            elif (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "execution"
                and relative != "beds/base.py"
            ):
                sites.setdefault(f"{relative}:{scope}", set())
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and relative != "beds/base.py":
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                empty_default = (
                    isinstance(node.value, ast.Name) and node.value.id == "NO_EXECUTION_CAPABILITIES"
                )
                if not empty_default and any(
                    (isinstance(t, ast.Name) and t.id == "execution")
                    or (isinstance(t, ast.Attribute) and t.attr in ("execution", "_execution"))
                    for t in targets
                ):
                    sites.setdefault(f"{relative}:{scope}", set())
    return sites


def _names_field_by_string(node: ast.AST) -> bool:
    if isinstance(node, ast.Dict):
        return any(
            isinstance(key, ast.Constant) and key.value in DISTINCT_FIELDS for key in node.keys
        )
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setattr"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in DISTINCT_FIELDS
    )


def _walk_scoped(node: ast.AST, scope: str) -> Iterator[tuple[str, ast.AST]]:
    for child in ast.iter_child_nodes(node):
        yield scope, child
        name = (
            child.name
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            else None
        )
        if name is None and isinstance(child, (ast.Assign, ast.AnnAssign)) and scope == "<module>":
            target = child.targets[0] if isinstance(child, ast.Assign) else child.target
            name = target.id if isinstance(target, ast.Name) else None
        yield from _walk_scoped(child, f"{scope}.{name}" if name else scope)


def test_every_declaration_site_is_reviewed() -> None:
    """No variant, layout or runtime profile can declare a capability unlisted."""
    sites = _declaration_sites()
    assert set(sites) == set(DECLARATION_SITES), (
        "list each new execution declaration site in DECLARATION_SITES with its evidence"
    )
    for site, identities in DECLARATION_SITES.items():
        assert identities, site
        assert set(identities) <= set(EVIDENCE), (site, set(identities) - set(EVIDENCE))
        # Every field a site can declare, on any branch, needs evidence on
        # every identity the site produces.
        for identity in identities:
            assert sites[site] <= set(EVIDENCE[identity]), (site, identity, sites[site])


def test_site_guard_finds_declarations(tmp_path: Path) -> None:
    """The guard recognizes each way of declaring, so it cannot pass vacuously."""
    samples = {
        "built.py": "def make():\n    return ExecutionCapabilities(hold='stream')\n",
        "passed.py": "PROFILE = Profile(key='x', execution=STREAM)\n",
        "replaced.py": "MX = replace(BASE, execution=STREAM)\n",
        "override.py": (
            "class C:\n    @property\n    def execution(self):\n        return STREAM\n"
        ),
        "assigned.py": "class P:\n    execution: ExecutionCapabilities = STREAM\n",
        "empty.py": "class P:\n    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES\n",
    }
    samples["conditional.py"] = (
        "def make(mx):\n"
        "    return ExecutionCapabilities(hold='stream', concurrent=AXES if mx else frozenset())\n"
    )
    samples["spread.py"] = "X = ExecutionCapabilities(**FIELDS)\n"
    samples["variant.py"] = (
        "class V:\n    @property\n    def execution(self):\n"
        "        return replace(ExecutionCapabilities(hold='stream'),"
        " concurrent=AXES if self.v else frozenset())\n"
    )
    samples["copied.py"] = "X = replace(BASE_EXECUTION, **CHANGES)\n"
    samples["keyed.py"] = "CHANGES = {'concurrent': AXES}\n"
    samples["setattr.py"] = "def f(p):\n    setattr(p, 'execution', STREAM)\n"
    for name, source in samples.items():
        (tmp_path / name).write_text(source)
    sites = _declaration_sites(tmp_path)
    assert {site.split(":", 1)[0] for site in sites} == set(samples) - {"empty.py"}
    assert sites["conditional.py:<module>.make"] == {"hold", "concurrent"}
    assert sites["spread.py:<module>.X"] == {"**"}
    assert sites["variant.py:<module>.V.execution"] == {"hold", "concurrent"}
    assert sites["copied.py:<module>.X"] == {"**"}
    assert sites["keyed.py:<module>.CHANGES"] == {"**"}
    assert sites["setattr.py:<module>.f"] == {"**"}


def test_default_declares_nothing() -> None:
    assert NO_EXECUTION_CAPABILITIES.declared == frozenset()
    assert ExecutionCapabilities(
        hold="stream", sustain_ms=217, concurrent=frozenset({"motor:back", "motor:legs"})
    ).declared == {"hold", "sustain_ms", "concurrent"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hold": "pulsed"},
        {"sustain_ms": 200},
        {"hold": "stream", "sustain_ms": 0},
        {"concurrent": frozenset({"motor:back"})},
        {"concurrent": frozenset({"motor:back", ""})},
    ],
)
def test_invalid_declarations_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ExecutionCapabilities(**kwargs)  # type: ignore[arg-type]
