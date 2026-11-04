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

from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES, VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.ergomotion4_profiles import PRODUCTS as ERGOMOTION_4_PRODUCTS
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

# Keeson E5/E6 (K1) profiles with stream evidence, by profile key. The base,
# OKIN, Sino, KSBT CR, OKIN FFE, Sleepy's Box15, Rondure and Scott Living routes
# are blocked and declare nothing.
KEESON_STREAM: dict[str, tuple[str, ...]] = {
    "ergomotion": ("sfdergo",),
    "serta": ("serta330",),
    "restonic_a": ("restonic",),
    "restonic_b": ("restonic",),
    "innova": ("sfm",),
    "bedsense_bases": ("sfmc2",),
    "avanti_bases": ("avanti",),
    "dynasty_bases": ("dynasty",),
    "maxcoil_una": ("maxcoil",),
    "americanstar": ("americanstar",),
    "simon_li": ("simon",),
    "heal_every_night": ("heal",),
    "okin_seating": ("minghua",),
    "adjustable_lite": ("adjlite",),
    "adjustable_lite_ksbt03c": ("adjlite",),
    "ksbt": ("hump",),
    "ksbt03c": ("mancini",),
    "sbi": ("costco",),
    "coolbase": ("coolbase",),
    "bf": ("bf",),
    "cherish": ("cherish",),
    "comfort_enhancements": ("enh",),
    "glideaway_motion": ("glide",),
    "adjustamattress": ("row067",),
    "adjustamattress_p2": ("row067",),
}
# Keeson cluster033 app layouts, and Ergomotion 4.0 per catalog product style.
KEESON_APP_STREAM: dict[str, tuple[str, ...]] = {
    "tempur_curve": ("tempur",),
    "qplus_app": ("costco",),
    "serta_mp_remote": ("serta330",),
    "omazz_adjusto_iii": ("omazz",),
    "ergomotion_app": ("sfdergo",),
    "row_control": ("row",),
    "ergo_slim": ("slim",),
    "tempur_au": ("tempur_au",),
}
ERGOMOTION_4_STYLES = frozenset(product.style for product in ERGOMOTION_4_PRODUCTS.values())

# Declaration -> declared field -> evidence keys from the design document.
EVIDENCE: dict[str, Mapping[str, tuple[str, ...]]] = {
    **{f"KeesonProfile:{key}": {"hold": keys} for key, keys in KEESON_STREAM.items()},
    **{
        f"AppProfile:{app}@{layout}": {"hold": KEESON_APP_STREAM[app]}
        for app, layouts in keeson_profiles.APP_LAYOUTS.items()
        for layout in layouts
    },
    **{
        f"AppProfile:ergomotion_4@{style}": {"hold": ("hump", "issue558")}
        for style in ERGOMOTION_4_STYLES
    },
}

# Source site -> the EVIDENCE identities it declares. A site is
# "<path under custom_components/adjustable_bed>:<enclosing name>". Runtime
# enumeration cannot reach every variant, layout or product, so every place
# that can declare a capability must be listed and reviewed here.
DECLARATION_SITES: dict[str, tuple[str, ...]] = {
    **{
        f"profiles/keeson.py:<module>.{key.upper()}": (f"KeesonProfile:{key}",)
        for key in KEESON_STREAM
    },
    "profiles/keeson.py:<module>.app_profile": tuple(
        f"AppProfile:{app}@{layout}"
        for app, layouts in keeson_profiles.APP_LAYOUTS.items()
        for layout in layouts
    ),
    "profiles/keeson.py:<module>.ergomotion_4_profile": tuple(
        f"AppProfile:ergomotion_4@{style}" for style in sorted(ERGOMOTION_4_STYLES)
    ),
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
    profiles.extend(keeson_profiles.ergomotion_4_profile(style) for style in ERGOMOTION_4_STYLES)
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
