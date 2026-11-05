"""Shared transaction for guided app and layout changes of an existing entry.

Configure and Repairs open the same reconfigure wizard for a family that has
one. The wizard works only on staged data:

1. snapshot the saved data and options (``MigrationSnapshot``);
2. ask the family's app and layout questions;
3. verify the family's exact requirements while the old runtime's transport is
   reserved, where the family has endpoint or bond requirements;
4. show the control changes computed from the two routes' entity sets
   (``async_control_changes``) with a note that a passed check does not prove
   the physical layout;
5. save only against an unchanged snapshot.

Keep, cancel, failure or a concurrent edit leave the saved entry as it was.
A label change that resolves to the saved route never migrates anything.

Families reuse this transaction, never another family's protocol checks.
"""

from __future__ import annotations

import copy
import hashlib
import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigEntryDisabler,
    ConfigFlowContext,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations

from .const import (
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COOLBASE,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_FURNIMOVE_REMOTE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_LEGGETT_APP_PROFILE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_MALOUF_APP_PROFILE,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONF_SLEEPYS_ELITE_SELECTOR,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_VMAT_REMOTE,
    CONF_VMATBASIC_PROFILE,
    DOMAIN,
    PAIR_SIDES,
    RICHMAT_REMOTE_LP_QRRM,
    grants_one_connection_per_pairing_window,
    requires_pairing,
)
from .pairing import effective_child_data, get_child, is_paired

if TYPE_CHECKING:
    from .entity_runtime import EntityRuntime

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ManagedFamily:
    """A family whose app or layout changes run through the guided wizard."""

    # Also the config-flow step that asks the family's app question.
    key: str
    bed_types: frozenset[str]
    # The app and layout settings Configure must not change on its own.
    route_keys: tuple[str, ...]
    # Whether a staged route has exact endpoint or bond requirements, so the
    # change must pass a connection check before it can be confirmed.
    requires_check: Callable[[Mapping[str, Any]], bool]
    # A route outside ``bed_types`` that the family question also chooses. It
    # has no guided change of its own, so Reconfigure asks this family's
    # question for it; Configure still changes its own settings.
    asks_for: Callable[[Mapping[str, Any]], bool] = lambda _data: False


VIBRADORM_FAMILY: Final = ManagedFamily(
    key="vibradorm",
    bed_types=frozenset({BED_TYPE_VIBRADORM, BED_TYPE_VIBRADORM_APP, BED_TYPE_VMATBASIC}),
    route_keys=(
        CONF_VIBRADORM_APP_PROFILE,
        CONF_VIBRADORM_CONTROL_TYPE,
        CONF_VIBRADORM_VMAT_REMOTE,
        CONF_VMATBASIC_PROFILE,
    ),
    requires_check=lambda _data: True,
)

# The app controllers need their app's exact GATT roles; the legacy Jiecang and
# Lierda routes fall back to a generic write role and have nothing to check.
JIECANG_FAMILY: Final = ManagedFamily(
    key="jiecang_family",
    bed_types=frozenset({BED_TYPE_JIECANG, BED_TYPE_COMFORT_MOTION, BED_TYPE_JIECANG_APP}),
    route_keys=(CONF_JIECANG_APP_PROFILE, CONF_JIECANG_APP_LAYOUT, CONF_JIECANG_APP_TRANSPORT),
    requires_check=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_JIECANG_APP,
)

_OKIN_ROUTES: Final = frozenset(
    {
        BED_TYPE_FURNIMOVE,
        BED_TYPE_OKIN_UUID,
        BED_TYPE_OKIMAT,
        BED_TYPE_OKIN_DOT,
        BED_TYPE_OKIN_RF_ECO_BT,
    }
)
# Every Okin route writes an exact command endpoint, and the Okin UUID and
# RF ECO BT routes also need a bond. The handset or remote code picks the layout.
# An app the review suggests switches as Configure switched it, unchecked.
OKIN_FAMILY: Final = ManagedFamily(
    key="okin_family",
    bed_types=_OKIN_ROUTES,
    route_keys=(CONF_FURNIMOVE_REMOTE, CONF_PROTOCOL_VARIANT),
    requires_check=lambda data: data.get(CONF_BED_TYPE) in _OKIN_ROUTES,
    # The question for an Okin CST bed lists its products first, then these
    # routes. Configure still picks a CST product.
    asks_for=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_OKIN_CST,
)

# The Keeson controllers fall back across their write roles and never refuse a
# link, so a Keeson route has no endpoint or bond to check; Configure switched
# these routes unchecked too. The variant picks the app or remote.
KEESON_FAMILY: Final = ManagedFamily(
    key="keeson_family",
    bed_types=frozenset(
        {
            BED_TYPE_KEESON,
            BED_TYPE_ERGOMOTION,
            BED_TYPE_SERTA,
            BED_TYPE_OKIN_FFE,
            BED_TYPE_COOLBASE,
        }
    ),
    route_keys=(CONF_PROTOCOL_VARIANT,),
    requires_check=lambda _data: False,
)

# Solace name routes and Woosa Sleep share the FFFF frame and controller, which
# never refuses a link, so a change has nothing to check; Configure switched
# them unchecked. Motion Bed and BedSense are separate bed types it can reach.
SOLACE_FAMILY: Final = ManagedFamily(
    key="solace_family",
    bed_types=frozenset({BED_TYPE_SOLACE}),
    route_keys=(CONF_PROTOCOL_VARIANT,),
    requires_check=lambda _data: False,
)

# The Okin receiver needs a bond, which the pairing step proves. LP Comfort
# Connect grants one connection per pairing window, so its first connection
# after the change bonds, as at setup. The MlRM receiver and the apps on other
# bed types switch unchecked, as Configure did.
LEGGETT_FAMILY: Final = ManagedFamily(
    key="leggett_family",
    bed_types=frozenset(
        {
            BED_TYPE_LEGGETT_PLATT,
            BED_TYPE_LEGGETT_GEN2,
            BED_TYPE_LEGGETT_OKIN,
            BED_TYPE_LEGGETT_WILINKE,
        }
    ),
    route_keys=(CONF_PROTOCOL_VARIANT, CONF_LEGGETT_APP_PROFILE),
    requires_check=lambda data: requires_pairing(
        data.get(CONF_BED_TYPE, ""), data.get(CONF_PROTOCOL_VARIANT)
    )
    and not grants_one_connection_per_pairing_window(
        data.get(CONF_BED_TYPE, ""), data.get(CONF_PROTOCOL_VARIANT)
    ),
    # The legacy L&P app and the L&P app on a QRRM remote are answers too.
    asks_for=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_LEGGETT_LP_LEGACY
    or (
        data.get(CONF_BED_TYPE) == BED_TYPE_RICHMAT
        and data.get(CONF_RICHMAT_REMOTE) == RICHMAT_REMOTE_LP_QRRM
    ),
)

_SLEEPYS_ROUTES: Final = frozenset(
    {
        BED_TYPE_SLEEPYS_ELITE_APP,
        BED_TYPE_SLEEPYS_BOX15,
        BED_TYPE_SLEEPYS_BOX24,
        BED_TYPE_SLEEPYS_BOX25,
    }
)
# The app's control box selector picks exact GATT routes, and each receiver
# route writes one exact command endpoint, so a change checks the link first.
# An app the review suggests switches unchecked, as Configure switched it.
SLEEPYS_FAMILY: Final = ManagedFamily(
    key="sleepys_family",
    bed_types=_SLEEPYS_ROUTES,
    route_keys=(CONF_SLEEPYS_ELITE_SELECTOR, CONF_PROTOCOL_VARIANT),
    requires_check=lambda data: data.get(CONF_BED_TYPE) in _SLEEPYS_ROUTES,
)

_CUSTOMATIC_ROUTES: Final = frozenset(
    {
        BED_TYPE_CUSTOMATIC_CLARITY,
        BED_TYPE_CUSTOMATIC_JEROMES,
        BED_TYPE_CUSTOMATIC_REMEDY,
        BED_TYPE_ZSERIES,
    }
)
# Each Customatic app writes its one exact command characteristic, and the
# Z-Series app the OKIN bedding apps' command characteristic, so a change checks
# the link first. The variant is the Z-Series model.
CUSTOMATIC_FAMILY: Final = ManagedFamily(
    key="customatic_family",
    bed_types=_CUSTOMATIC_ROUTES,
    route_keys=(CONF_PROTOCOL_VARIANT,),
    requires_check=lambda data: data.get(CONF_BED_TYPE) in _CUSTOMATIC_ROUTES,
)

_JORDANS_ROUTES: Final = frozenset({BED_TYPE_SERENITY, BED_TYPE_TRANQUIL})
# Both Jordan's apps write the OKIN bedding apps' command characteristic.
JORDANS_FAMILY: Final = ManagedFamily(
    key="jordans_family",
    bed_types=_JORDANS_ROUTES,
    route_keys=(),
    requires_check=lambda data: data.get(CONF_BED_TYPE) in _JORDANS_ROUTES,
)

_MALOUF_ROUTES: Final = frozenset(
    {BED_TYPE_MALOUF_APP, BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN}
)
# The apps pick one GATT transport from the Bluetooth name and services and
# refuse an ambiguous or missing one, so a change to an app checks the link.
# The receiver routes correct each other from the services when they connect.
MALOUF_FAMILY: Final = ManagedFamily(
    key="malouf_family",
    bed_types=_MALOUF_ROUTES,
    route_keys=(CONF_MALOUF_APP_PROFILE,),
    requires_check=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_MALOUF_APP,
)

_LOGICDATA_ROUTES: Final = frozenset({BED_TYPE_LOGICDATA, BED_TYPE_LOGICDATA_APP})
# SimplicityFrame writes its one encrypted characteristic after the bond the
# pairing step proves, and each LOGICDATA app needs its selected transport, so a
# change checks the link first. The Sleep Smart air pump is a separate physical
# device with its own entry, never a route of a bed entry.
LOGICDATA_FAMILY: Final = ManagedFamily(
    key="logicdata_family",
    bed_types=_LOGICDATA_ROUTES,
    route_keys=(
        CONF_LOGICDATA_APP_PROFILE,
        CONF_LOGICDATA_APP_FAMILY,
        CONF_LOGICDATA_APP_LAYOUT,
        CONF_LOGICDATA_APP_TRANSPORT,
    ),
    requires_check=lambda data: data.get(CONF_BED_TYPE) in _LOGICDATA_ROUTES,
)

# The Jensen and Svane controllers resolve their GATT roles only when they
# write, so a link never refuses them on connect and a change has nothing to
# check; Configure switched these routes unchecked too. The variant picks the
# Svane Remote profile or the Jensen app's LinOn profile.
JENSEN_FAMILY: Final = ManagedFamily(
    key="jensen_family",
    bed_types=frozenset({BED_TYPE_JENSEN, BED_TYPE_SVANE}),
    route_keys=(CONF_PROTOCOL_VARIANT,),
    requires_check=lambda _data: False,
)

# The Limoss Remote app needs its exact service and notifying command
# characteristic, so a change to it checks the link first. The generic Limoss
# route and FSM Relax write the shared command characteristic and switch
# unchecked, as Configure switched them. Leaving enabled Limoss Remote
# accessories sends the app's OFF commands before saving (config_flow).
LIMOSS_FAMILY: Final = ManagedFamily(
    key="limoss_family",
    bed_types=frozenset({BED_TYPE_LIMOSS, BED_TYPE_LIMOSS_REMOTE, BED_TYPE_FSM_RELAX}),
    route_keys=(),
    requires_check=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_LIMOSS_REMOTE,
)

MANAGED_FAMILIES: Final[tuple[ManagedFamily, ...]] = (
    VIBRADORM_FAMILY,
    JIECANG_FAMILY,
    OKIN_FAMILY,
    KEESON_FAMILY,
    SOLACE_FAMILY,
    LEGGETT_FAMILY,
    SLEEPYS_FAMILY,
    CUSTOMATIC_FAMILY,
    JORDANS_FAMILY,
    MALOUF_FAMILY,
    LOGICDATA_FAMILY,
    JENSEN_FAMILY,
    LIMOSS_FAMILY,
)


def _receivers(entry_data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the entry's receiver, or each side of a pair as well."""
    receivers = [entry_data]
    if is_paired(entry_data):
        receivers.extend(
            effective_child_data(entry_data, side)
            for side in PAIR_SIDES
            if get_child(entry_data, side) is not None
        )
    return receivers


def managed_family(entry_data: Mapping[str, Any]) -> ManagedFamily | None:
    """Return the guided family of the entry's receiver, or of either paired side."""
    bed_types = {receiver.get(CONF_BED_TYPE) for receiver in _receivers(entry_data)}
    return next(
        (family for family in MANAGED_FAMILIES if family.bed_types & bed_types),
        None,
    )


def reconfigure_family(entry_data: Mapping[str, Any]) -> ManagedFamily | None:
    """Return the family whose question Reconfigure asks for the entry.

    That is the guided family, or a family whose question also chooses the
    entry's route (``asks_for``). Repairs and Configure's refusals follow only
    the guided family, since that question may not offer what they suggest.
    """
    return managed_family(entry_data) or next(
        (
            family
            for family in MANAGED_FAMILIES
            for receiver in _receivers(entry_data)
            if family.asks_for(receiver)
        ),
        None,
    )


@dataclass(frozen=True, slots=True)
class MigrationSnapshot:
    """The saved setup a guided change starts from and must still match."""

    data: Mapping[str, Any]
    options: Mapping[str, Any]

    @classmethod
    def of(cls, entry: ConfigEntry) -> MigrationSnapshot:
        return cls(
            MappingProxyType(copy.deepcopy(dict(entry.data))),
            MappingProxyType(copy.deepcopy(dict(entry.options))),
        )

    def matches(self, entry: ConfigEntry) -> bool:
        """Return True while nobody else has saved the entry."""
        return dict(self.data) == dict(entry.data) and dict(self.options) == dict(entry.options)

    def is_unchanged_by(self, staged: Mapping[str, Any]) -> bool:
        """Return True when a staged answer resolves to the saved setup."""
        saved = {**self.data, **self.options}
        return {
            key: value for key, value in staged.items() if key in saved or key != CONF_NAME
        } == saved

    def staged(self, title: str) -> dict[str, Any]:
        """Return a mutable working copy that the wizard may change."""
        staged = copy.deepcopy({**self.data, **self.options})
        staged.setdefault(CONF_NAME, title)
        return staged


def reconfigure_context(entry: ConfigEntry) -> ConfigFlowContext:
    """Return the flow context that opens the guided change for an entry."""
    return ConfigFlowContext(source=SOURCE_RECONFIGURE, entry_id=entry.entry_id)


@dataclass(frozen=True, slots=True)
class ControlChanges:
    """What a staged change does to the entry's Home Assistant controls."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unchanged: int = 0
    # Automations and scripts that reference a removed entity.
    references: tuple[str, ...] = ()
    # False when the staged route's controls are only known after connecting.
    known: bool = True


_PLATFORMS: Final = (
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "light",
    "number",
    "select",
    "sensor",
    "switch",
)


@contextmanager
def _read_only_entity_registry(hass: HomeAssistant) -> Iterator[None]:
    """Ignore entity registry writes while entities are only being listed.

    Entity builders tidy up stale registry rows as they build. A preview of a
    route that is not saved must never remove or rewrite an existing row.
    ``er.async_get`` is cached per instance, so the instance's write methods are
    shadowed, and only around synchronous code, so nothing else runs meanwhile.
    """
    registry = er.async_get(hass)

    def ignore_remove(entity_id: str) -> None:
        """Keep the row."""

    def ignore_update(entity_id: str, **_changes: Any) -> er.RegistryEntry | None:
        return registry.async_get(entity_id)

    shadowed = {"async_remove": ignore_remove, "async_update_entity": ignore_update}
    for name, method in shadowed.items():
        setattr(registry, name, method)
    try:
        yield
    finally:
        for name in shadowed:
            delattr(registry, name)


async def _async_entity_labels(
    hass: HomeAssistant, runtime: EntityRuntime
) -> dict[str, tuple[str, str]]:
    """Return ``unique_id -> (platform, label)`` for the entities a runtime exposes."""
    language = hass.config.language
    names = await async_get_translations(hass, language, "entity", {DOMAIN})
    built: list[tuple[str, Any]] = []
    with _read_only_entity_registry(hass):
        # Builders are synchronous, so nothing else runs while writes are hidden.
        for platform in _PLATFORMS:
            module = import_module(f".{platform}", __package__)
            builder = getattr(module, f"_{platform}_entities_for")
            built.extend((platform, entity) for entity in builder(hass, runtime))
    entities: dict[str, tuple[str, str]] = {}
    for platform, entity in built:
        unique_id = entity.unique_id
        if unique_id is None:
            continue
        key = entity.translation_key
        label = names.get(f"component.{DOMAIN}.entity.{platform}.{key}.name") if key else None
        if label and (placeholders := entity.translation_placeholders):
            try:
                label = label.format(**placeholders)
            except KeyError, IndexError, ValueError:
                pass
        if not label:
            name = entity.name
            label = name if isinstance(name, str) and name else key or unique_id
        entities[unique_id] = (platform, label)
    return entities


async def _async_preview_labels(
    hass: HomeAssistant, entry: ConfigEntry, data: Mapping[str, Any]
) -> dict[str, tuple[str, str]] | None:
    """Mint the staged configuration offline and list its controls, if possible.

    The preview runs under its own address. App sessions, selection intent and
    stored app state are kept per address, and minting a controller for another
    profile would otherwise replace the live bed's session. Unique IDs are
    mapped back to the real address afterwards.
    """
    from .app_session import drop_app_sessions
    from .app_state_store import discard_app_state_store
    from .coordinator import AdjustableBedCoordinator

    address = str(data.get(CONF_ADDRESS, "")).upper()
    # Controllers validate a Bluetooth address shape. A locally administered
    # address derived from the entry keeps the preview's sessions separate.
    digest = hashlib.sha256(f"preview:{entry.entry_id}".encode()).digest()
    preview_address = ":".join(f"{byte:02X}" for byte in (0x02, *digest[:5]))
    from .profile_id import with_profile_ids

    preview = ConfigEntry(
        # The runtime builds from the stored profile id, which staged data
        # still carries for the saved route.
        data=with_profile_ids({**data, CONF_ADDRESS: preview_address}),
        disabled_by=ConfigEntryDisabler.USER,
        discovery_keys=MappingProxyType({}),
        domain=DOMAIN,
        entry_id=entry.entry_id,
        minor_version=entry.minor_version,
        options={},
        source=entry.source,
        subentries_data=(),
        title=entry.title,
        unique_id=entry.unique_id,
        version=entry.version,
    )
    try:
        runtime = AdjustableBedCoordinator(hass, preview)
        await runtime.async_prime_offline_controller(preview=True)
        if runtime.capability_controller is None:
            return None
        labels = await _async_entity_labels(hass, runtime)
    except Exception:  # noqa: BLE001 - a preview never blocks the change
        _LOGGER.debug("Could not list the staged controls for %s", entry.title, exc_info=True)
        return None
    finally:
        drop_app_sessions(hass, preview_address)
        discard_app_state_store(hass, preview_address)
    return {
        address + unique_id[len(preview_address) :]
        if unique_id.startswith(preview_address)
        else unique_id: label
        for unique_id, label in labels.items()
    }


async def _async_current_labels(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, tuple[str, str]]:
    """List the entry's controls: the running runtime, else the saved setup, else the registry."""
    from .coordinator import AdjustableBedCoordinator

    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(runtime, AdjustableBedCoordinator) and runtime.capability_controller is not None:
        try:
            return await _async_entity_labels(hass, runtime)
        except Exception:  # noqa: BLE001 - fall back to the saved setup
            _LOGGER.debug("Could not list the running controls of %s", entry.title, exc_info=True)
    labels = await _async_preview_labels(hass, entry, {**entry.data, **entry.options})
    if labels is not None:
        return labels
    registry = er.async_get(hass)
    return {
        row.unique_id: (row.domain, row.name or row.original_name or row.entity_id)
        for row in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


def _references(hass: HomeAssistant, entity_ids: list[str]) -> tuple[str, ...]:
    """Name the automations and scripts that use any of the given entities."""
    found: dict[str, str] = {}
    for component, finder_name in (
        ("automation", "automations_with_entity"),
        ("script", "scripts_with_entity"),
    ):
        if component not in hass.config.components:
            continue
        finder = getattr(import_module(f"homeassistant.components.{component}"), finder_name)
        for entity_id in entity_ids:
            for referrer in finder(hass, entity_id):
                state = hass.states.get(referrer)
                found[referrer] = state.name if state is not None else referrer
    return tuple(sorted(found.values(), key=str.lower))


async def async_control_changes(
    hass: HomeAssistant, entry: ConfigEntry, staged: Mapping[str, Any]
) -> ControlChanges:
    """Compare the entry's controls with those of the staged configuration.

    Unique IDs are address-based, so a control the staged route keeps keeps its
    entity, history and automations. Only the staged route's declared controls
    are known before it connects; controls a bed reports later can differ.
    """
    staged_data = {key: value for key, value in staged.items() if key != CONF_NAME}
    staged_data[CONF_ADDRESS] = entry.data.get(CONF_ADDRESS, staged.get(CONF_ADDRESS))
    target = await _async_preview_labels(hass, entry, staged_data)
    if target is None:
        return ControlChanges(known=False)
    current = await _async_current_labels(hass, entry)
    removed_ids = sorted(current.keys() - target.keys())
    registry = er.async_get(hass)
    removed_entities = [
        entity_id
        for unique_id in removed_ids
        if (entity_id := registry.async_get_entity_id(current[unique_id][0], DOMAIN, unique_id))
    ]
    return ControlChanges(
        added=tuple(
            sorted((target[uid][1] for uid in target.keys() - current.keys()), key=str.lower)
        ),
        removed=tuple(sorted((current[uid][1] for uid in removed_ids), key=str.lower)),
        unchanged=len(current.keys() & target.keys()),
        references=_references(hass, removed_entities),
    )
