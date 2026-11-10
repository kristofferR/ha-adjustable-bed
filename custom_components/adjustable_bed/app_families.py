"""One declaration per app family: its row, its question and its guided change.

A family is a set of routes that one bed-type list row opens, because shared
names or services cannot tell which app or remote runs the bed. Its
declaration owns the row, the routes behind it, the answers of its question
and the settings an answer clears, and, for a family whose app can change in
place, its guided change (``profile_migration.py``). One config-flow step
drives every family from its declaration; a family that truly differs does so
through a small hook on it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum, auto
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from homeassistant.const import CONF_ADDRESS

from .beds.richmat_classic.profiles import APP_NAMES as RICHMAT_CLASSIC_APP_NAMES
from .const import (
    BED_TYPE_BEDSENSE,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COOLBASE,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_ERGOMOTION_4,
    BED_TYPE_ERGOMOTION_APP,
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
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MOTION_BED,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_FURNIMOVE_REMOTE,
    CONF_HAS_MASSAGE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    CONF_LEGGETT_APP_PROFILE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_READ_UUID,
    CONF_LP_LEGACY_WRITE_UUID,
    CONF_MALOUF_APP_MODEL,
    CONF_MALOUF_APP_PRIMARY,
    CONF_MALOUF_APP_PROFILE,
    CONF_MALOUF_APP_TRANSPORT,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_MOTOR_PULSE_USER_SET,
    CONF_PROTOCOL_VARIANT,
    CONF_REMACRO_MODEL,
    CONF_RICHMAT_REMOTE,
    CONF_RMCONTROL_PRODUCT,
    CONF_RMCONTROL_SIDE,
    CONF_SLEEPYS_ELITE_SELECTOR,
    CONF_STAIRCASE_LAYOUT_CONFIRMED,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_LIGHT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    CONF_VIBRADORM_RGB,
    CONF_VIBRADORM_VMAT_REMOTE,
    CONF_VMATBASIC_PROFILE,
    DEFAULT_MOTOR_COUNT,
    JIECANG_APP_PROFILES,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_JSON,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_PURPLE,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
    KEESON_VARIANT_SIMON_LI,
    KEESON_VARIANT_SLEEP_HARMONY,
    LEGGETT_APP_DEFAULT_PROFILE,
    LEGGETT_APP_MOTOR_COUNTS,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    OKIN_CST_VARIANTS,
    REMACRO_VARIANT_JEROMES,
    REMACRO_VARIANT_THE_BRICK,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_MH_APPS,
    RICHMAT_MH_BED_TYPES,
    RICHMAT_REMOTE_AUTO,
    RICHMAT_REMOTE_LP_QRRM,
    RICHMAT_REMOTES,
    SLEEP_NUMBER_MCR_SERVICE_UUID,
    SLEEP_NUMBER_SERVICE_UUID,
    SOLACE_VARIANT_WOOSA,
    SVANE_VARIANT_JENSEN_LINON,
    SVANE_VARIANT_JMC,
    VARIANT_AUTO,
    VIBRADORM_APP_CONFIG_KEYS,
    VMATBASIC_CONFIG_KEYS,
    ZSERIES_VARIANT_Z230,
    ZSERIES_VARIANT_Z280,
    get_motor_pulse_defaults,
    grants_one_connection_per_pairing_window,
    requires_pairing,
)
from .setup_questions import Question, SetupProfile

if TYPE_CHECKING:
    from bleak import BleakClient
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
    from homeassistant.core import HomeAssistant


class _Removed:
    """Marks a setting an answer drops."""


# An answer's setting with this value is dropped from the staged setup.
REMOVED: Final = _Removed()
_NOTHING: Final[Mapping[str, Any]] = MappingProxyType({})


class Then(Enum):
    """How setup continues once an answer has staged its route."""

    # Ask the route's declared questions, if it has any, then finish.
    CONTINUE = auto()
    # Finish without asking the route's questions: the answer settled them.
    FINISH = auto()
    # Open the route's own app question, when another family's step asks it.
    OWN_STEP = auto()


class Form(Enum):
    """How a family question lists its answers."""

    # Each answer's key, translated by the step's selector translations.
    KEYS = auto()
    # Each answer with an English label, still translated by key.
    LABELLED = auto()
    # A dropdown of English labels, with no translations.
    DROPDOWN = auto()


@dataclass(frozen=True, slots=True)
class Answer:
    """One answer of a family question: the route it stages and what it sets."""

    bed_type: str
    variant: str | None = None
    # Settings the answer stages, such as the app it names; REMOVED drops one.
    data: Mapping[str, Any] = _NOTHING
    label: str | None = None
    then: Then = Then.CONTINUE
    # Questions asked on the generic step before the route is final. An asked
    # variant reselects the route; the other answers and the profile's own
    # settled fields are staged.
    ask: SetupProfile | None = None
    # A step that confirms or narrows the answer before it is staged.
    step: str | None = None
    # The exact answers a narrowing step offers.
    group: tuple[Answer, ...] = ()
    # Stage only the bed type (and a given variant), keeping the settings the
    # form collected instead of the route's defaults.
    keeps_settings: bool = False
    # Keep the saved or detected route instead of choosing one.
    keep: bool = False
    # Whether the bed-type list counts this answer's route as a family member.
    # False for another brand's app the question only offers.
    member: bool = True


KEEP: Final = Answer(bed_type="", keep=True)


@dataclass(frozen=True, slots=True)
class Visit:
    """What a family question knows when it is drawn or answered."""

    hass: HomeAssistant
    family: AppFamily
    # The staged setup.
    data: Mapping[str, Any]
    # The route the question started from: its bed type and variant (or auto).
    incoming: tuple[str, str]
    # The question's first visit in this journey.
    first: bool
    # A guided change is running.
    guided: bool
    # This family runs that guided change.
    guiding: bool
    # The saved setup a guided change started from.
    saved: Mapping[str, Any] | None
    # The advertisement that started setup, if any.
    discovery: BluetoothServiceInfoBleak | None

    def advertisement(self) -> BluetoothServiceInfoBleak | None:
        """Return the discovery, else the bed's last advertisement."""
        if self.discovery is not None:
            return self.discovery
        from homeassistant.components import bluetooth

        return bluetooth.async_last_service_info(
            self.hass, self.data[CONF_ADDRESS], connectable=False
        )


# Checks a staged route's exact endpoints or GATT roles on the candidate link,
# raising when one is missing, and returns what it resolved for the confirm
# step's control list.
EndpointCheck = Callable[["HomeAssistant", "BleakClient", Mapping[str, Any]], Mapping[str, Any]]


def _never(_data: Mapping[str, Any]) -> bool:
    return False


def _nothing_preselected(_visit: Visit) -> str | None:
    return None


def _not_settled(_visit: Visit) -> bool:
    return False


# When Keep is offered.
def keep_when_guided(visit: Visit) -> bool:
    """Only a guided change keeps: setup has no saved route to keep."""
    return visit.guided


def keep_always(_visit: Visit) -> bool:
    return True


def keep_never(_visit: Visit) -> bool:
    return False


def keep_when_guiding(visit: Visit) -> bool:
    """Only this family's own guided change keeps; another's hands an app over."""
    return visit.guiding


@dataclass(frozen=True, slots=True)
class AppFamily:
    """A family's row, question and guided change."""

    # The config-flow step that asks the family's question.
    step: str
    # The row in the bed-type list: its route, family name and apps.
    row: str
    name: str
    apps: str
    answers: Mapping[str, Answer]
    # Routes reached only through the row; the list does not show them.
    routes: frozenset[str] = frozenset()
    # Other bed types whose app question this is.
    also: frozenset[str] = frozenset()
    # Routes behind the row that open their own questions, not this one.
    direct: frozenset[str] = frozenset()
    # Whether the question only picks a route. False when its answers are apps
    # whose own settings follow (Vibradorm, LOGICDATA, StarCode).
    picks_route: bool = True
    # Whether a list drawn for a route behind the row shows the row; False
    # shows the route by its own label.
    routes_show_row: bool = True
    form: Form = Form.KEYS
    keep_label: str = "keep"
    offers_keep: Callable[[Visit], bool] = keep_when_guided
    # How setup continues after Keep.
    keep_then: Then = Then.CONTINUE
    # The answers this visit offers, when they depend on the bed or the setup.
    offer: Callable[[Visit], Mapping[str, Answer]] | None = None
    # An answer the question takes without asking, such as an advertised route.
    preselect: Callable[[Visit], str | None] = _nothing_preselected
    # Whether the staged route already answers the question.
    settled: Callable[[Visit], bool] = _not_settled
    # The answer the form suggests.
    suggest: Callable[[Visit], str] | None = None
    placeholders: Callable[[Visit], dict[str, str]] | None = None
    # The setting that names an app within one bed type; a new app changes it.
    profile_key: str | None = None
    # Settings a changed route drops before the new one is staged.
    clears: tuple[str, ...] = ()
    # A changed route drops every setting another bed type's profiles own.
    clears_other_profiles: bool = False
    # Answers staged under a saved compatibility ID, by that ID: the answer's
    # route and the (ID, variant) that runs it. The saved ID is never rewritten.
    aliases: Mapping[str, Mapping[str, tuple[str, str | None]]] = _NOTHING
    # Whether the app or layout can change in place through the guided change.
    guided: bool = False
    # Routes of a guided family that never change in place.
    unguided: frozenset[str] = frozenset()
    # The app and layout settings Configure must not change on its own.
    route_keys: tuple[str, ...] = ()
    # Whether a staged route has exact endpoint or bond requirements, so the
    # change must pass a connection check before it can be confirmed.
    requires_check: Callable[[Mapping[str, Any]], bool] = _never
    # A route outside the guided routes that this question also chooses. It
    # has no guided change of its own, so Reconfigure asks this question for
    # it; Configure still changes its own settings.
    asks_for: Callable[[Mapping[str, Any]], bool] = _never
    # The check a route that ``requires_check`` passes before it can be confirmed.
    endpoint_check: EndpointCheck | None = None
    # The modules ``endpoint_check`` imports, which the flow loads off the event loop.
    check_imports: tuple[str, ...] = ()

    @property
    def asks(self) -> frozenset[str]:
        """Return the bed types whose app question this is."""
        return (frozenset({self.row}) | self.routes | self.also) - self.direct

    @property
    def managed(self) -> frozenset[str]:
        """Return the routes whose app or layout the guided change manages."""
        return self.asks - self.unguided if self.guided else frozenset()

    def offered(self, visit: Visit) -> dict[str, Answer]:
        """Return this visit's answers, with Keep last when it is offered."""
        answers = dict(self.offer(visit) if self.offer is not None else self.answers)
        if self.offers_keep(visit) and "keep" not in answers:
            answers["keep"] = KEEP
        return answers

    def saved_id(self, incoming: str, answer: Answer) -> Answer:
        """Return the answer under the saved compatibility ID that runs its route."""
        alias = self.aliases.get(incoming, {}).get(answer.bed_type)
        if alias is None:
            return answer
        return replace(answer, bed_type=alias[0], variant=alias[1])

    def changes_route(self, data: Mapping[str, Any], answer: Answer) -> bool:
        """Return True when the answer stages another route or app than the staged one."""
        if answer.bed_type != data.get(CONF_BED_TYPE):
            return True
        key = self.profile_key
        return key is not None and data.get(key) != answer.data.get(key)


def _current(visit: Visit) -> dict[str, str]:
    """Name the route the question started from."""
    from .detection import bed_type_label

    return {"current": bed_type_label(visit.incoming[0])}


def keep_unless_row(visit: Visit) -> bool:
    """Keep saves the route detection or the saved setup chose; the row alone chose none."""
    return visit.guided or visit.incoming[0] != visit.family.row


def _app_row(visit: Visit) -> bool:
    """Return True when the route started as one app's own bed-type list row."""
    from .detection import APP_VARIANT_CHOICES

    return visit.incoming in APP_VARIANT_CHOICES


# --- Endpoint checks -------------------------------------------------------


def _vibradorm_roles(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    """The staged app's or V-MAT Basic product's GATT roles; pairing proves the legacy bond."""
    bed_type = data[CONF_BED_TYPE]
    if bed_type == BED_TYPE_VMATBASIC:
        from .beds.vmatbasic.controller import validate_profile_roles

        validate_profile_roles(client, data[CONF_VMATBASIC_PROFILE])
    elif bed_type == BED_TYPE_VIBRADORM_APP:
        from .beds.vibradorm.app import validate_profile_roles as validate_app_roles
        from .profiles.vibradorm import validate_vibradorm_app_profile

        control = data[CONF_VIBRADORM_CONTROL_TYPE]
        validate_app_roles(
            client,
            validate_vibradorm_app_profile(
                data[CONF_VIBRADORM_APP_PROFILE],
                "other" if control == "other" else int(control),
                restored=data[CONF_VIBRADORM_RESTORED],
                floor_light=data[CONF_VIBRADORM_FLOOR_LIGHT],
                rgb=data[CONF_VIBRADORM_RGB],
                massage=data[CONF_HAS_MASSAGE],
                light_extension=data[CONF_VIBRADORM_LIGHT_EXTENSION],
                remote=data.get(CONF_VIBRADORM_VMAT_REMOTE),
            ),
        )
    return {}


def _jiecang_transport(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    from .beds.jiecang.app import require_app_transport

    require_app_transport(client, data)
    return {}


def _okin_endpoint(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    if data[CONF_BED_TYPE] in OKIN_FAMILY.managed:
        from .controller_factory import require_okin_route_endpoint

        require_okin_route_endpoint(client, data[CONF_BED_TYPE])
    return {}


def _sleepys_route(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    if data[CONF_BED_TYPE] in SLEEPYS_FAMILY.managed:
        from .controller_factory import require_sleepys_route

        require_sleepys_route(client, data)
    return {}


def _app_roles(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    """The staged Customatic or Jordan's app's own command endpoint or roles."""
    bed_type = data[CONF_BED_TYPE]
    if bed_type in (BED_TYPE_ZSERIES, *JORDANS_FAMILY.managed):
        from .beds.serenity.controller import require_app_roles

        require_app_roles(
            client,
            f"zseries_{data[CONF_PROTOCOL_VARIANT]}" if bed_type == BED_TYPE_ZSERIES else bed_type,
        )
    elif bed_type in CUSTOMATIC_FAMILY.managed:
        from .beds.customatic.controller import require_command_endpoint

        require_command_endpoint(client, bed_type.removeprefix("customatic_"))
    return {}


def _malouf_transport(
    hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    """The app's transport, read from the advertised name as the runtime reads it."""
    if data[CONF_BED_TYPE] != BED_TYPE_MALOUF_APP:
        return {}
    from homeassistant.components import bluetooth

    from .beds.malouf.app import require_app_transport

    advertised = bluetooth.async_last_service_info(hass, data[CONF_ADDRESS], connectable=False)
    # The entry keeps the user's choice, which may stay automatic.
    return {
        CONF_MALOUF_APP_TRANSPORT: require_app_transport(
            client, data, advertised.device.name if advertised else None
        )
    }


def _logicdata_route(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    from .controller_factory import require_logicdata_route

    require_logicdata_route(client, data)
    return {}


def _limoss_remote_route(
    _hass: HomeAssistant, client: BleakClient, data: Mapping[str, Any]
) -> Mapping[str, Any]:
    if data[CONF_BED_TYPE] == BED_TYPE_LIMOSS_REMOTE:
        from .beds.limoss.remote import require_app_route

        require_app_route(client)
    return {}


def _in(routes: Callable[[], frozenset[str]]) -> Callable[[Mapping[str, Any]], bool]:
    """Require a check for a staged route among a family's managed routes."""
    return lambda data: data.get(CONF_BED_TYPE) in routes()


# --- Follow-up questions ---------------------------------------------------


def _route_motor_counts(data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .config_flow import _motor_count_options

    return {count: str(count) for count in _motor_count_options(data[CONF_BED_TYPE])}


def _first_motor_count(data: Mapping[str, Any]) -> int:
    from .config_flow import _motor_count_options

    return _motor_count_options(data[CONF_BED_TYPE])[0]


def _keeson_routes(_data: Mapping[str, Any]) -> Mapping[Any, str]:
    from .config_flow import _labelled_routes

    return _labelled_routes(BED_TYPE_KEESON)


def _legacy_cadence(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """A legacy remote route's own command cadence."""
    pulse_count, pulse_delay = get_motor_pulse_defaults(data[CONF_BED_TYPE], VARIANT_AUTO)
    return {
        CONF_MOTOR_PULSE_COUNT: pulse_count,
        CONF_MOTOR_PULSE_DELAY_MS: pulse_delay,
        CONF_MOTOR_PULSE_USER_SET: False,
    }


# A legacy remote route chosen in place of a Jiecang app: the app had fixed the
# motors and cadence, so the route asks its own motors and takes its cadence.
_LEGACY_MOTORS: Final = SetupProfile(
    questions=(Question(CONF_MOTOR_COUNT, _route_motor_counts, DEFAULT_MOTOR_COUNT),),
    derive=_legacy_cadence,
)
# The remote style chosen in the Restonic BT app's settings; A is its default.
_RESTONIC_STYLE: Final = SetupProfile(
    questions=(
        Question(
            CONF_PROTOCOL_VARIANT,
            {
                KEESON_VARIANT_RESTONIC_A: "Remote A (6 buttons)",
                KEESON_VARIANT_RESTONIC_B: "Remote B (10 buttons)",
            },
            KEESON_VARIANT_RESTONIC_A,
        ),
    ),
    title=lambda _data: "Restonic BT",
)
# An older Keeson remote's route and the bed's motor count.
_KEESON_REMOTE_ROUTE: Final = SetupProfile(
    questions=(
        Question(
            CONF_PROTOCOL_VARIANT,
            _keeson_routes,
            lambda data: next(iter(_keeson_routes(data))),
        ),
        Question(CONF_MOTOR_COUNT, _route_motor_counts, _first_motor_count),
    ),
    title=lambda _data: "Keeson remote",
)


# --- Vibradorm --------------------------------------------------------------


def _on_legacy_vibradorm(visit: Visit) -> bool:
    """On a legacy entry the legacy setup is the saved route, so it keeps it."""
    return visit.saved is not None and visit.saved.get(CONF_BED_TYPE) == BED_TYPE_VIBRADORM


def _vibradorm_answers(visit: Visit) -> Mapping[str, Answer]:
    if not _on_legacy_vibradorm(visit):
        return VIBRADORM_FAMILY.answers
    return {
        **VIBRADORM_FAMILY.answers,
        "legacy": replace(KEEP, label="Keep current setup"),
    }


def _vibradorm_app(profile: str, label: str) -> Answer:
    return Answer(
        BED_TYPE_VIBRADORM_APP,
        data={CONF_VIBRADORM_APP_PROFILE: profile},
        label=label,
        keeps_settings=True,
    )


VIBRADORM_FAMILY: Final = AppFamily(
    step="vibradorm",
    row=BED_TYPE_VIBRADORM,
    name="Vibradorm",
    apps="VMAT, Caresse Diamant, Werkmeister, V-MAT Basic",
    answers={
        "vmat": _vibradorm_app("vmat", "VMAT"),
        "caresse": _vibradorm_app("caresse", "Caresse Diamant"),
        "werkmeister": _vibradorm_app("werkmeister", "Werkmeister"),
        "vmatbasic": Answer(BED_TYPE_VMATBASIC, label="V-MAT Basic", keeps_settings=True),
        # A form drawn for a detected app or V-MAT Basic, or an app entry, set
        # none of the legacy settings, so they are asked.
        "legacy": Answer(BED_TYPE_VIBRADORM, label="Legacy setup"),
    },
    routes=frozenset({BED_TYPE_VIBRADORM_APP, BED_TYPE_VMATBASIC}),
    picks_route=False,
    form=Form.DROPDOWN,
    keep_label="Keep current setup",
    offers_keep=lambda visit: visit.guided and not _on_legacy_vibradorm(visit),
    offer=_vibradorm_answers,
    profile_key=CONF_VIBRADORM_APP_PROFILE,
    clears=(*VIBRADORM_APP_CONFIG_KEYS, *VMATBASIC_CONFIG_KEYS, CONF_VIBRADORM_APP_METADATA),
    guided=True,
    route_keys=(
        CONF_VIBRADORM_APP_PROFILE,
        CONF_VIBRADORM_CONTROL_TYPE,
        CONF_VIBRADORM_VMAT_REMOTE,
        CONF_VMATBASIC_PROFILE,
    ),
    requires_check=lambda _data: True,
    endpoint_check=_vibradorm_roles,
    check_imports=("beds.vmatbasic.controller", "beds.vibradorm.vmat_setup"),
)


# --- LOGICDATA --------------------------------------------------------------


def _logicdata_app(app: str) -> Answer:
    return Answer(BED_TYPE_LOGICDATA_APP, data={CONF_LOGICDATA_APP_PROFILE: app})


def _logicdata_answers(visit: Visit) -> Mapping[str, Answer]:
    """The pump is its own physical device, never a route a bed entry changes to."""
    return {
        key: answer
        for key, answer in LOGICDATA_FAMILY.answers.items()
        if not (visit.guided and answer.bed_type == BED_TYPE_LOGICDATA_AIR_PUMP)
    }


_LOGICDATA_ROUTE_KEYS: Final = (
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_TRANSPORT,
)
# The apps share Bluetooth services, so nothing about the bed chooses one.
# SimplicityFrame writes its one encrypted characteristic after the bond the
# pairing step proves, and each LOGICDATA app needs its selected transport, so a
# change checks the link first. The Sleep Smart air pump is a separate physical
# device with its own entry, never a route of a bed entry.
LOGICDATA_FAMILY: Final = AppFamily(
    step="logicdata_family",
    row=BED_TYPE_LOGICDATA_APP,
    name="LOGICDATA",
    apps=(
        "SILVERmotion (SimplicityFrame), MOTIONrelax phone and tablet, and Sleep Smart Air "
        "Mattress apps"
    ),
    answers={
        "silvermotion": Answer(BED_TYPE_LOGICDATA),
        "phone": _logicdata_app("phone"),
        "tablet": _logicdata_app("tablet"),
        "sleep_smart": _logicdata_app("sleep_smart"),
        "sleep_smart_pump": Answer(BED_TYPE_LOGICDATA_AIR_PUMP),
    },
    routes=frozenset({BED_TYPE_LOGICDATA, BED_TYPE_LOGICDATA_AIR_PUMP}),
    picks_route=False,
    offers_keep=keep_unless_row,
    offer=_logicdata_answers,
    placeholders=_current,
    profile_key=CONF_LOGICDATA_APP_PROFILE,
    # Another app's command family, layout and transport mean nothing here.
    clears=_LOGICDATA_ROUTE_KEYS,
    guided=True,
    unguided=frozenset({BED_TYPE_LOGICDATA_AIR_PUMP}),
    route_keys=_LOGICDATA_ROUTE_KEYS,
    requires_check=_in(lambda: LOGICDATA_FAMILY.managed),
    endpoint_check=_logicdata_route,
    check_imports=("beds.logicdata.app",),
)


# --- Jiecang ----------------------------------------------------------------


def _jiecang_answers(visit: Visit) -> Mapping[str, Answer]:
    """The apps and legacy remotes, then another family's apps the review suggests.

    A legacy remote chosen in place of an app asks its own motor count, since
    the app set the layout and cadence itself. A suggested app, such as the
    LOGICDATA app for a Comfort Motion bed, continues in its own question.
    """
    from .detection import resolve_bed_type_choice
    from .profile_review import suggested_apps

    answers = dict(JIECANG_FAMILY.answers)
    if visit.incoming[0] == BED_TYPE_JIECANG_APP:
        for key in ("legacy_jiecang", "legacy_lierda"):
            answers[key] = replace(
                answers[key], ask=_LEGACY_MOTORS, data={CONF_MOTOR_COUNT: REMOVED}
            )
    for app in suggested_apps(visit.hass, visit.data):
        bed_type, variant = resolve_bed_type_choice(app)
        if bed_type not in JIECANG_FAMILY.asks:
            answers[app] = Answer(bed_type, variant, then=Then.OWN_STEP)
    return answers


_JIECANG_ROUTE_KEYS: Final = (
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_TRANSPORT,
)
# Never inferred from the bed's name. The app controllers need their app's
# exact GATT roles; the legacy Jiecang and Lierda routes fall back to a generic
# write role and have nothing to check.
JIECANG_FAMILY: Final = AppFamily(
    step="jiecang_family",
    row=BED_TYPE_JIECANG_APP,
    name="Jiecang",
    apps=(
        "ERGOBALANCE, Dream Motion, Dream Motion HD and Comfort Motion apps, Glide and Lierda"
        " remotes"
    ),
    answers={
        **{
            profile: Answer(
                BED_TYPE_JIECANG_APP,
                data={CONF_JIECANG_APP_PROFILE: profile},
                keeps_settings=True,
            )
            for profile in JIECANG_APP_PROFILES
        },
        "legacy_jiecang": Answer(BED_TYPE_JIECANG, keeps_settings=True),
        "legacy_lierda": Answer(BED_TYPE_COMFORT_MOTION, keeps_settings=True),
    },
    routes=frozenset({BED_TYPE_JIECANG, BED_TYPE_COMFORT_MOTION}),
    offers_keep=keep_unless_row,
    offer=_jiecang_answers,
    placeholders=_current,
    profile_key=CONF_JIECANG_APP_PROFILE,
    clears=_JIECANG_ROUTE_KEYS,
    guided=True,
    route_keys=_JIECANG_ROUTE_KEYS,
    requires_check=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_JIECANG_APP,
    endpoint_check=_jiecang_transport,
    check_imports=("beds.jiecang.app", "beds.comfort_motion"),
)


# --- Okin -------------------------------------------------------------------


def _okin_cst_apps() -> dict[str, Answer]:
    """The Okin CST products, each the route of the app its accepted report names."""
    return {
        f"{BED_TYPE_OKIN_CST}:{variant}": Answer(BED_TYPE_OKIN_CST, variant, label=label)
        for variant, label in OKIN_CST_VARIANTS.items()
        if variant != VARIANT_AUTO
    }


def _okin_answers(visit: Visit) -> Mapping[str, Answer]:
    """The detected family's apps first, then the other Okin answers.

    The apps the review suggests for this route stay one answer away; a
    detected or chosen Okin CST bed is offered its own apps first.
    """
    from .detection import resolve_bed_type_choice
    from .profile_review import choice_label, related_app_choices

    incoming, variant = visit.incoming
    apps = {
        app: Answer(*resolve_bed_type_choice(app), label=choice_label(app))
        for app in related_app_choices(incoming, variant)
    }
    if incoming == BED_TYPE_OKIN_CST:
        return {**_okin_cst_apps(), **apps, **OKIN_FAMILY.answers}
    return {**OKIN_FAMILY.answers, **apps}


def _okin_settled(visit: Visit) -> bool:
    """An app row, such as Nectar Move, or an explicit CST product answered the question."""
    incoming, variant = visit.incoming
    return (
        visit.first
        and not visit.guided
        and (
            _app_row(visit)
            or incoming == BED_TYPE_OKIN_CST
            and f"{BED_TYPE_OKIN_CST}:{variant}" in _okin_cst_apps()
        )
    )


# Every Okin route writes an exact command endpoint, and the Okin UUID and RF
# ECO BT routes also need a bond. The handset or remote code picks the layout.
# An app the review suggests switches as Configure switched it, unchecked.
OKIN_FAMILY: Final = AppFamily(
    step="okin_family",
    row=BED_TYPE_FURNIMOVE,
    name="Okin",
    apps="FurniMove / OKIN Smart Remote app, Okimat, Lucid, DOT and RF ECO BT remotes",
    answers={
        "furnimove": Answer(BED_TYPE_FURNIMOVE, label="FurniMove / OKIN Smart Remote app"),
        "okin_uuid": Answer(
            BED_TYPE_OKIN_UUID, label="No app: Okimat or OKIN handset code (requires pairing)"
        ),
        "okin_dot": Answer(BED_TYPE_OKIN_DOT, label="No app: DOT remote (RF34 or RF6707)"),
        # Choosing the staircase is the explicit confirmation its repair asks for.
        "okin_rf_eco_bt": Answer(
            BED_TYPE_OKIN_RF_ECO_BT,
            data={CONF_STAIRCASE_LAYOUT_CONFIRMED: True, CONF_MOTOR_COUNT: 1},
            label="No app: single-actuator staircase, RF ECO BT (requires pairing)",
        ),
    },
    routes=frozenset({BED_TYPE_OKIN_UUID, BED_TYPE_OKIN_DOT, BED_TYPE_OKIN_RF_ECO_BT}),
    # A new Okin CST bed answers with its apps first; CST is not a guided
    # route, so an existing entry keeps Configure.
    also=frozenset({BED_TYPE_OKIMAT, BED_TYPE_OKIN_CST}),
    form=Form.LABELLED,
    keep_label="I don't know: keep the detected controls",
    # A FurniMove row or gateway chose no handset, so there is nothing to keep.
    offers_keep=keep_unless_row,
    offer=_okin_answers,
    settled=_okin_settled,
    placeholders=_current,
    clears=(CONF_FURNIMOVE_REMOTE, CONF_PROTOCOL_VARIANT, CONF_STAIRCASE_LAYOUT_CONFIRMED),
    aliases={BED_TYPE_OKIMAT: {BED_TYPE_OKIN_UUID: (BED_TYPE_OKIMAT, None)}},
    guided=True,
    unguided=frozenset({BED_TYPE_OKIN_CST}),
    route_keys=(CONF_FURNIMOVE_REMOTE, CONF_PROTOCOL_VARIANT),
    requires_check=_in(lambda: OKIN_FAMILY.managed),
    # The question for an Okin CST bed lists its products first, then these
    # routes. Configure still picks a CST product.
    asks_for=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_OKIN_CST,
    endpoint_check=_okin_endpoint,
)


# --- Keeson -----------------------------------------------------------------


def _keeson_restonic_row(visit: Visit) -> str | None:
    """The Restonic BT row already answered the app; its style is still asked."""
    if (
        visit.first
        and not visit.guided
        and _app_row(visit)
        and visit.incoming[1] in (KEESON_VARIANT_RESTONIC_A, KEESON_VARIANT_RESTONIC_B)
    ):
        return "restonic"
    return None


def _keeson_settled(visit: Visit) -> bool:
    """An app row already answered the question."""
    return visit.first and not visit.guided and _app_row(visit) and not _keeson_restonic_row(visit)


def _keeson_group(*routes: tuple[str, str | None]) -> tuple[Answer, ...]:
    return tuple(Answer(bed_type, variant, member=False) for bed_type, variant in routes)


# Shared names cannot tell the app. The Keeson controllers fall back across
# their write roles and never refuse a link, so a Keeson route has no endpoint
# or bond to check; Configure switched these routes unchecked too. The variant
# picks the app or remote.
KEESON_FAMILY: Final = AppFamily(
    step="keeson_family",
    row=BED_TYPE_KEESON,
    name="Keeson",
    apps=(
        "Member's Mark, Purple, Sleep Harmony and Linx / Juna Sleep apps, some Ergomotion Sync beds"
    ),
    answers={
        "sleep_harmony": Answer(BED_TYPE_KEESON, KEESON_VARIANT_SLEEP_HARMONY),
        "restonic": Answer(BED_TYPE_KEESON, ask=_RESTONIC_STYLE),
        # Grouped answers expand into one exact app or route each.
        "ergomotion_apps": Answer(
            BED_TYPE_KEESON,
            step="keeson_app",
            group=_keeson_group(
                (BED_TYPE_ERGOMOTION_APP, None),
                (BED_TYPE_ERGOMOTION_4, None),
                (BED_TYPE_SERTA_MP_REMOTE, None),
            ),
        ),
        "ore_apps": Answer(
            BED_TYPE_KEESON,
            step="keeson_app",
            group=_keeson_group(
                (BED_TYPE_KEESON, KEESON_VARIANT_AVANTI_BASES),
                (BED_TYPE_KEESON, KEESON_VARIANT_AMERICANSTAR),
                (BED_TYPE_KEESON, KEESON_VARIANT_BEDSENSE_BASES),
                (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA),
                (BED_TYPE_KEESON, KEESON_VARIANT_MAXCOIL_UNA),
                (BED_TYPE_KEESON, KEESON_VARIANT_DYNASTY_BASES),
            ),
        ),
        "okin_seating_apps": Answer(
            BED_TYPE_KEESON,
            step="keeson_app",
            group=_keeson_group(
                (BED_TYPE_KEESON, KEESON_VARIANT_ADJUSTABLE_LITE),
                (BED_TYPE_KEESON, KEESON_VARIANT_SIMON_LI),
                (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT),
                (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_SEATING),
            ),
        ),
        "purple_base_json": Answer(
            BED_TYPE_KEESON,
            step="keeson_app",
            group=_keeson_group(
                (BED_TYPE_KEESON, KEESON_VARIANT_PURPLE),
                (BED_TYPE_KEESON, KEESON_VARIANT_BASE),
                (BED_TYPE_KEESON, KEESON_VARIANT_JSON),
            ),
        ),
        "coolbase": Answer(BED_TYPE_COOLBASE),
        "other_route": Answer(BED_TYPE_KEESON, ask=_KEESON_REMOTE_ROUTE),
    },
    also=frozenset({BED_TYPE_ERGOMOTION, BED_TYPE_SERTA, BED_TYPE_OKIN_FFE, BED_TYPE_COOLBASE}),
    offers_keep=keep_always,
    keep_then=Then.FINISH,
    preselect=_keeson_restonic_row,
    settled=_keeson_settled,
    placeholders=_current,
    guided=True,
    route_keys=(CONF_PROTOCOL_VARIANT,),
)


# --- Solace -----------------------------------------------------------------


def _woosa_row(visit: Visit) -> str | None:
    """The Woosa Sleep row already answered the question."""
    if visit.first and not visit.guided and visit.incoming[1] == SOLACE_VARIANT_WOOSA:
        return "woosa"
    return None


# Several apps share QMS names. Solace name routes and Woosa Sleep share the
# FFFF frame and controller, which never refuses a link, so a change has nothing
# to check; Configure switched them unchecked. Motion Bed and BedSense are
# separate bed types it can reach.
SOLACE_FAMILY: Final = AppFamily(
    step="solace_family",
    row=BED_TYPE_SOLACE,
    name="Solace",
    apps="HomeKobo, Sealy MotionFlex and Sweet Night apps",
    answers={
        "name_route": Answer(BED_TYPE_SOLACE, VARIANT_AUTO),
        # Say what Woosa Sleep controls differ before choosing it.
        "woosa": Answer(BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA, step="solace_woosa"),
        "motion_bed": Answer(BED_TYPE_MOTION_BED, member=False),
        "bedsense": Answer(BED_TYPE_BEDSENSE, member=False),
    },
    offers_keep=keep_always,
    preselect=_woosa_row,
    placeholders=_current,
    guided=True,
    route_keys=(CONF_PROTOCOL_VARIANT,),
)


# --- Leggett & Platt --------------------------------------------------------


def _leggett_app(profile: str) -> Answer:
    """An app's own route and layout, by its report."""
    return Answer(
        BED_TYPE_LEGGETT_OKIN,
        data={
            CONF_LEGGETT_APP_PROFILE: profile,
            CONF_MOTOR_COUNT: LEGGETT_APP_MOTOR_COUNTS[profile],
        },
    )


# A route without an app profile drops it.
_NO_LEGGETT_APP: Final[Mapping[str, Any]] = MappingProxyType({CONF_LEGGETT_APP_PROFILE: REMOVED})

# Each app has its own layout. The Okin receiver needs a bond, which the
# pairing step proves. LP Comfort Connect grants one connection per pairing
# window, so its first connection after the change bonds, as at setup. The MlRM
# receiver and the apps on other bed types switch unchecked, as Configure did.
LEGGETT_FAMILY: Final = AppFamily(
    step="leggett_family",
    row=BED_TYPE_LEGGETT_OKIN,
    name="Leggett & Platt",
    apps="Prodigy CE, Prodigy 2, Prodigy 2L, U Series, LP Control and L&P Adjustable Base apps",
    answers={
        "prodigy_ce": _leggett_app("prodigy4"),
        "prodigy2": _leggett_app("prodigy2"),
        "prodigy2l": _leggett_app("prodigy2l"),
        "useries": _leggett_app("useries"),
        # LP Control drives an LP BED receiver with its Okin profile; the route
        # keeps its default layout, which no LP Control product is proven to change.
        "lp_control_okin": _leggett_app(LEGGETT_APP_DEFAULT_PROFILE),
        "lp_control_gen2": Answer(BED_TYPE_LEGGETT_GEN2, data=_NO_LEGGETT_APP),
        "lp_app_mlrm": Answer(BED_TYPE_LEGGETT_WILINKE, data=_NO_LEGGETT_APP),
        "lp_app_qrrm": Answer(
            BED_TYPE_RICHMAT,
            data={**_NO_LEGGETT_APP, CONF_RICHMAT_REMOTE: RICHMAT_REMOTE_LP_QRRM},
            then=Then.FINISH,
            member=False,
        ),
        "lp_legacy": Answer(BED_TYPE_LEGGETT_LP_LEGACY, data=_NO_LEGGETT_APP, member=False),
    },
    routes=frozenset({BED_TYPE_LEGGETT_GEN2, BED_TYPE_LEGGETT_WILINKE}),
    also=frozenset({BED_TYPE_LEGGETT_PLATT}),
    offers_keep=keep_always,
    placeholders=_current,
    # The legacy app's and the QRRM remote's own settings mean nothing on another route.
    clears=(
        CONF_LP_LEGACY_MODEL,
        CONF_LP_LEGACY_MODE,
        CONF_LP_LEGACY_WRITE_UUID,
        CONF_LP_LEGACY_READ_UUID,
        CONF_RICHMAT_REMOTE,
    ),
    aliases={
        BED_TYPE_LEGGETT_PLATT: {
            BED_TYPE_LEGGETT_GEN2: (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_GEN2),
            BED_TYPE_LEGGETT_OKIN: (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN),
            BED_TYPE_LEGGETT_WILINKE: (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_MLRM),
        }
    },
    guided=True,
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


# --- Jensen / Svane ---------------------------------------------------------


def _jensen_suggestion(bed_type: str, variant: str, name: str | None) -> str:
    """Return the answer the apps' own name rules pick for this bed.

    The Svane Remote app picks its JMC400 profile for a name with ``JMC``, and
    the Jensen app its LinOn profile for "Adjustable Bed" or "Jensen Bed".
    Every setup route suggests the same answer; the user confirms it.
    """
    from .beds.svane.state import svane_profile_for_selected_name
    from .detection import is_jensen_linon_name

    for answer, route in JENSEN_FAMILY.answers.items():
        if (route.bed_type, route.variant) == (bed_type, variant) and variant != VARIANT_AUTO:
            return answer
    if bed_type == BED_TYPE_JENSEN:
        return "jensen_jmc400"
    if name != "Svane Bed" and is_jensen_linon_name(name):
        return "jensen_linon"
    if svane_profile_for_selected_name(name) == "jmc":
        return "svane_jmc400"
    return "svane_bed"


def _jensen_suggest(visit: Visit) -> str:
    """Suggest from the bed's name; an unnamed advertisement reports its address instead."""
    from .detection import is_mac_like_name

    advertised = visit.advertisement()
    name = next(
        (
            candidate
            for candidate in (
                advertised.name if advertised is not None else None,
                visit.data.get(CONF_BLE_DEVICE_NAME),
            )
            if isinstance(candidate, str) and candidate and not is_mac_like_name(candidate)
        ),
        None,
    )
    return _jensen_suggestion(*visit.incoming, name)


# The JMC400 name and the LinonPI services each occur with both apps, so they
# never decide the profile; the apps' own name rules only suggest it. The
# Jensen and Svane controllers resolve their GATT roles only when they write, so
# a link never refuses them on connect and a change has nothing to check;
# Configure switched these routes unchecked too. The variant picks the Svane
# Remote profile or the Jensen app's LinOn profile.
JENSEN_FAMILY: Final = AppFamily(
    step="jensen_family",
    row=BED_TYPE_SVANE,
    name="Jensen / Svane",
    apps="Jensen Adjustable Sleep app (JMC400 and LinOn beds) and Svane Remote app",
    answers={
        "jensen_jmc400": Answer(BED_TYPE_JENSEN),
        "jensen_linon": Answer(BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON),
        "svane_bed": Answer(BED_TYPE_SVANE, VARIANT_AUTO),
        "svane_jmc400": Answer(BED_TYPE_SVANE, SVANE_VARIANT_JMC),
    },
    routes=frozenset({BED_TYPE_JENSEN}),
    suggest=_jensen_suggest,
    guided=True,
    route_keys=(CONF_PROTOCOL_VARIANT,),
)


# --- Sleepy's Elite ---------------------------------------------------------


def _with_suggested_apps(visit: Visit) -> Mapping[str, Answer]:
    """Offer the apps the review suggests for this route one answer away."""
    from .detection import resolve_bed_type_choice
    from .profile_review import choice_label, suggested_apps

    answers = dict(visit.family.answers)
    for app in suggested_apps(visit.hass, visit.data):
        bed_type, variant = resolve_bed_type_choice(app)
        if bed_type not in visit.family.asks:
            answers[app] = Answer(bed_type, variant, label=choice_label(app), then=Then.OWN_STEP)
    return answers


# Never inferred from the bed. The app's control box selector picks exact GATT
# routes, and each receiver route writes one exact command endpoint, so a
# change checks the link first. An app the review suggests switches unchecked,
# as Configure switched it.
SLEEPYS_FAMILY: Final = AppFamily(
    step="sleepys_family",
    row=BED_TYPE_SLEEPYS_ELITE_APP,
    name="Sleepy's Elite",
    apps="MFRM Sleepy's Elite app, BOX15, BOX24 and BOX25 receivers",
    answers={
        "app": Answer(BED_TYPE_SLEEPYS_ELITE_APP),
        "box25": Answer(BED_TYPE_SLEEPYS_BOX25),
        "box24": Answer(BED_TYPE_SLEEPYS_BOX24),
        "box15": Answer(BED_TYPE_SLEEPYS_BOX15),
    },
    routes=frozenset({BED_TYPE_SLEEPYS_BOX15, BED_TYPE_SLEEPYS_BOX24, BED_TYPE_SLEEPYS_BOX25}),
    form=Form.LABELLED,
    offers_keep=keep_unless_row,
    offer=_with_suggested_apps,
    placeholders=_current,
    # A new route starts from its own defaults, never another route's control
    # box or dialect.
    clears=(CONF_SLEEPYS_ELITE_SELECTOR,),
    guided=True,
    route_keys=(CONF_SLEEPYS_ELITE_SELECTOR, CONF_PROTOCOL_VARIANT),
    requires_check=_in(lambda: SLEEPYS_FAMILY.managed),
    endpoint_check=_sleepys_route,
    check_imports=("beds.sleepys.app",),
)


# --- App families: one question each, answered once ------------------------


def _answered_elsewhere(visit: Visit) -> bool:
    """An app's own row, or a route arriving from another family, already answered."""
    return visit.first and not visit.guiding and visit.incoming[0] != visit.family.row


# Each Customatic app writes its one exact command characteristic, and the
# Z-Series app the OKIN bedding apps' command characteristic, so a change checks
# the link first. The variant is the Z-Series model.
CUSTOMATIC_FAMILY: Final = AppFamily(
    step="customatic_family",
    row=BED_TYPE_CUSTOMATIC_CLARITY,
    name="Customatic",
    apps="Clarity (Rize Clarity), Jerome's C, Remedy (Rize Remedy) and Z-Series apps",
    answers={
        "clarity": Answer(BED_TYPE_CUSTOMATIC_CLARITY),
        "jeromes": Answer(BED_TYPE_CUSTOMATIC_JEROMES),
        "remedy": Answer(BED_TYPE_CUSTOMATIC_REMEDY),
        "zseries_z230": Answer(BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z230),
        "zseries_z280": Answer(BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280),
    },
    routes=frozenset({BED_TYPE_CUSTOMATIC_JEROMES, BED_TYPE_CUSTOMATIC_REMEDY}),
    also=frozenset({BED_TYPE_ZSERIES}),
    offers_keep=keep_when_guiding,
    settled=_answered_elsewhere,
    clears_other_profiles=True,
    guided=True,
    route_keys=(CONF_PROTOCOL_VARIANT,),
    requires_check=_in(lambda: CUSTOMATIC_FAMILY.managed),
    endpoint_check=_app_roles,
    check_imports=("beds.customatic.controller", "beds.serenity.controller"),
)

# Both Jordan's apps write the OKIN bedding apps' command characteristic.
JORDANS_FAMILY: Final = AppFamily(
    step="jordans_family",
    row=BED_TYPE_SERENITY,
    name="Jordan's",
    apps="Serenity and Tranquil apps",
    answers={"serenity": Answer(BED_TYPE_SERENITY), "tranquil": Answer(BED_TYPE_TRANQUIL)},
    routes=frozenset({BED_TYPE_TRANQUIL}),
    offers_keep=keep_when_guiding,
    settled=_answered_elsewhere,
    clears_other_profiles=True,
    guided=True,
    requires_check=_in(lambda: JORDANS_FAMILY.managed),
    endpoint_check=_app_roles,
    check_imports=("beds.serenity.controller",),
)

# Each StarCode app asks its own settings after the question; AdjustableM5X5
# and M1X12 open their own questions directly.
STARCODE_FAMILY: Final = AppFamily(
    step="starcode_family",
    row=BED_TYPE_STARCODE_ABM5_4,
    name="StarCode",
    apps="AdjustableM5X4, AdjustableM5X5 and Adjustable Comfort M1X12 apps",
    answers={
        "m5x4": Answer(BED_TYPE_STARCODE_ABM5_4),
        "m5x5": Answer(BED_TYPE_STARCODE_M5X5),
        "m1x12": Answer(BED_TYPE_STARCODE_M1X12),
    },
    routes=frozenset({BED_TYPE_STARCODE_M5X5, BED_TYPE_STARCODE_M1X12}),
    direct=frozenset({BED_TYPE_STARCODE_M5X5, BED_TYPE_STARCODE_M1X12}),
    picks_route=False,
    offers_keep=keep_when_guiding,
    settled=_answered_elsewhere,
    clears_other_profiles=True,
)

# The two apps, then the generic controls the family row and detection choose.
# The Limoss Remote app needs its exact service and notifying command
# characteristic, so a change to it checks the link first. The generic Limoss
# route and FSM Relax write the shared command characteristic and switch
# unchecked, as Configure switched them. Leaving enabled Limoss Remote
# accessories sends the app's OFF commands before saving (config_flow).
LIMOSS_FAMILY: Final = AppFamily(
    step="limoss_family",
    row=BED_TYPE_LIMOSS,
    name="Limoss / Stawett",
    apps="Limoss Remote and FSM Relax apps, Stawett and older Limoss controls",
    answers={
        "limoss_remote": Answer(BED_TYPE_LIMOSS_REMOTE),
        "fsm_relax": Answer(BED_TYPE_FSM_RELAX),
        "generic": Answer(BED_TYPE_LIMOSS),
    },
    routes=frozenset({BED_TYPE_LIMOSS_REMOTE, BED_TYPE_FSM_RELAX}),
    offers_keep=keep_when_guiding,
    settled=_answered_elsewhere,
    clears_other_profiles=True,
    guided=True,
    requires_check=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_LIMOSS_REMOTE,
    endpoint_check=_limoss_remote_route,
    check_imports=("beds.limoss.remote",),
)


# --- Receiver families: the advertised service decides ----------------------


def _advertised(services: Mapping[str, str]) -> Callable[[Visit], str | None]:
    """Take the one answer whose service the bed advertises; ask when none or several are."""

    def preselect(visit: Visit) -> str | None:
        info = visit.advertisement()
        advertised = {uuid.lower() for uuid in (info.service_uuids if info else ())}
        confirmed = [key for key, service in services.items() if service in advertised]
        return confirmed[0] if len(confirmed) == 1 else None

    return preselect


REVERIE_FAMILY: Final = AppFamily(
    step="reverie_family",
    row=BED_TYPE_REVERIE_NIGHTSTAND,
    name="Reverie",
    apps="Nightstand app, Protocol 110 and Protocol 108 receivers",
    answers={
        "protocol_110": Answer(BED_TYPE_REVERIE_NIGHTSTAND),
        "protocol_108": Answer(BED_TYPE_REVERIE),
    },
    routes=frozenset({BED_TYPE_REVERIE}),
    offers_keep=keep_unless_row,
    preselect=_advertised(
        {"protocol_110": REVERIE_NIGHTSTAND_SERVICE_UUID, "protocol_108": REVERIE_SERVICE_UUID}
    ),
)

SLEEP_NUMBER_FAMILY: Final = AppFamily(
    step="sleep_number_family",
    row=BED_TYPE_SLEEP_NUMBER,
    name="Sleep Number",
    apps="SleepIQ app, Fuzion (Climate 360, FlexFit) and BAM/MCR (i8, 360 FlexFit 2) bases",
    answers={
        "fuzion": Answer(BED_TYPE_SLEEP_NUMBER),
        "mcr": Answer(BED_TYPE_SLEEP_NUMBER_MCR),
    },
    routes=frozenset({BED_TYPE_SLEEP_NUMBER_MCR}),
    offers_keep=keep_unless_row,
    preselect=_advertised(
        {"fuzion": SLEEP_NUMBER_SERVICE_UUID, "mcr": SLEEP_NUMBER_MCR_SERVICE_UUID}
    ),
)


# --- Richmat ----------------------------------------------------------------

# Another route's RMControl settings mean nothing to a classic or MH app.
_NO_RMCONTROL: Final[Mapping[str, Any]] = MappingProxyType(
    dict.fromkeys((CONF_RMCONTROL_PRODUCT, CONF_RMCONTROL_SIDE, CONF_RICHMAT_REMOTE), REMOVED)
)


def _richmat_answers(visit: Visit) -> Mapping[str, Answer]:
    """Each answer with what its route reads from the bed's advertised name.

    An MH app's name rule reads the raw name. A listed remote code the name
    carries is the Richmat route's default; an unlisted one is kept as detected.
    """
    from .config_flow import _name_rule_setup_name
    from .detection import detect_richmat_remote_from_name

    info = visit.advertisement()
    name = info.name if info is not None else None
    answers: dict[str, Answer] = {}
    for key, answer in RICHMAT_FAMILY.answers.items():
        if answer.bed_type in RICHMAT_MH_APPS:
            answer = replace(
                answer, data={**answer.data, **_name_rule_setup_name(answer.bed_type, name)}
            )
        elif answer.bed_type == BED_TYPE_RICHMAT and CONF_RICHMAT_REMOTE not in visit.data:
            code = detect_richmat_remote_from_name(name)
            remote = (
                code.upper()
                if code and code.upper() in RICHMAT_REMOTES
                else code or RICHMAT_REMOTE_AUTO
            )
            answer = replace(answer, data={**answer.data, CONF_RICHMAT_REMOTE: remote})
        answers[key] = answer
    return answers


def _richmat_app_row(visit: Visit) -> str | None:
    """An app chosen elsewhere, such as from a brand's list, already answered."""
    if not visit.first or visit.incoming[0] == BED_TYPE_RICHMAT:
        return None
    return next(
        (
            key
            for key, answer in RICHMAT_FAMILY.answers.items()
            if answer.bed_type == visit.incoming[0]
        ),
        None,
    )


# Shared names and services cannot tell the app. RMControl and the remote
# controls share the Richmat route; the RMControl product tells them apart, and
# the remote controls have none.
RICHMAT_FAMILY: Final = AppFamily(
    step="richmat_family",
    row=BED_TYPE_RICHMAT,
    name="Richmat",
    apps=(
        "RMControl, Revive Control, Best Mattress, Blvd Home, HARMONY, Idealbed, "
        "RUF | Betten (Motor 2), W.Silver Products, AMERICANSTAR, Bailey's Bed Control, TX, "
        "Avocado Eco Base, CoasterSleep, Forty Winks, Milemont, Superior, SleepFunction and "
        "SVEN & SON apps, and Richmat remotes"
    ),
    answers={
        "richmat_420": Answer("richmat_app"),
        "rmcontrol": Answer(BED_TYPE_RICHMAT, data={CONF_RMCONTROL_PRODUCT: None}),
        **{app: Answer(bed_type, data=_NO_RMCONTROL) for bed_type, app in RICHMAT_MH_APPS.items()},
        # The classic apps keep their own declared questions.
        **{
            app: Answer(BED_TYPE_RICHMAT_CLASSIC_APPS, app, data=_NO_RMCONTROL)
            for app in RICHMAT_CLASSIC_APP_NAMES
        },
        "remote": Answer(BED_TYPE_RICHMAT, data={CONF_RMCONTROL_PRODUCT: ""}),
    },
    routes=RICHMAT_MH_BED_TYPES,
    routes_show_row=False,
    offers_keep=keep_never,
    offer=_richmat_answers,
    preselect=_richmat_app_row,
)


# --- Remacro ----------------------------------------------------------------

# The variant that selects each store app. Auto is the Slumberland app, as in v4.0.2.
_REMACRO_APPS: Final = {
    "slumberland": VARIANT_AUTO,
    "the_brick": REMACRO_VARIANT_THE_BRICK,
    "jeromes": REMACRO_VARIANT_JEROMES,
}


def _remacro_model(visit: Visit) -> int | None:
    from .beds.remacro.discovery import remacro_manufacturer_data
    from .beds.remacro.protocol import advertised_model_id

    return advertised_model_id(
        remacro_manufacturer_data(
            visit.hass,
            visit.data[CONF_ADDRESS],
            visit.discovery.manufacturer_data if visit.discovery is not None else None,
        )
    )


def _remacro_answers(visit: Visit) -> Mapping[str, Answer]:
    """The apps that list the advertised model; a model no app lists, or none seen, runs on any.

    The bed type stays; only the app changes, so the form's settings stay. The
    advertised model is remembered.
    """
    from .beds.remacro.protocol import app_for_variant, apps_listing

    model_id = _remacro_model(visit)
    listing = apps_listing(model_id)
    model = {} if model_id is None else {CONF_REMACRO_MODEL: model_id}
    return {
        key: Answer(BED_TYPE_REMACRO, variant, data=model, keeps_settings=True)
        for key, variant in _REMACRO_APPS.items()
        if not listing or app_for_variant(variant) in listing
    }


def _remacro_placeholders(visit: Visit) -> dict[str, str]:
    from .beds.remacro.protocol import MODELS

    model_id = _remacro_model(visit)
    return {
        "model": (
            "none seen yet"
            if model_id is None
            else MODELS[model_id].name
            if model_id in MODELS
            else f"company ID {model_id}"
        )
    }


# The advertisement picks the model, never the app.
REMACRO_FAMILY: Final = AppFamily(
    step="remacro_family",
    row=BED_TYPE_REMACRO,
    name="Remacro",
    apps="Slumberland, The Brick and Jerome's apps",
    answers={
        key: Answer(BED_TYPE_REMACRO, variant, keeps_settings=True)
        for key, variant in _REMACRO_APPS.items()
    },
    offers_keep=keep_never,
    offer=_remacro_answers,
    placeholders=_remacro_placeholders,
)


# --- Malouf / Lucid ---------------------------------------------------------

# Shared services and retail names identify neither the app nor the hardware.
# The apps pick one GATT transport from the Bluetooth name and services and
# refuse an ambiguous or missing one, so a change to an app checks the link.
# The receiver routes correct each other from the services when they connect.
MALOUF_FAMILY: Final = AppFamily(
    step="malouf_family",
    row=BED_TYPE_MALOUF_APP,
    name="Malouf / Lucid",
    apps="Malouf Base and Lucid Base apps, Nordic UART and FFE5 receivers",
    answers={
        "malouf": Answer(BED_TYPE_MALOUF_APP, data={CONF_MALOUF_APP_PROFILE: "malouf"}),
        "lucid": Answer(BED_TYPE_MALOUF_APP, data={CONF_MALOUF_APP_PROFILE: "lucid"}),
        "nordic_uart": Answer(BED_TYPE_MALOUF_NEW_OKIN),
        "ffe5": Answer(BED_TYPE_MALOUF_LEGACY_OKIN),
    },
    routes=frozenset({BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN}),
    offers_keep=keep_unless_row,
    placeholders=_current,
    profile_key=CONF_MALOUF_APP_PROFILE,
    # Another app or receiver starts from its own defaults, never another
    # app's model, role or transport.
    clears=(
        CONF_MALOUF_APP_PROFILE,
        CONF_MALOUF_APP_MODEL,
        CONF_MALOUF_APP_TRANSPORT,
        CONF_MALOUF_APP_PRIMARY,
    ),
    guided=True,
    route_keys=(CONF_MALOUF_APP_PROFILE,),
    requires_check=lambda data: data.get(CONF_BED_TYPE) == BED_TYPE_MALOUF_APP,
    endpoint_check=_malouf_transport,
    check_imports=("beds.malouf.app",),
)


APP_FAMILIES: Final[tuple[AppFamily, ...]] = (
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
    STARCODE_FAMILY,
    REVERIE_FAMILY,
    SLEEP_NUMBER_FAMILY,
    RICHMAT_FAMILY,
    REMACRO_FAMILY,
)
# Families whose app or layout changes through the guided change.
GUIDED_FAMILIES: Final = tuple(family for family in APP_FAMILIES if family.guided)
_BY_BED_TYPE: Final = {bed_type: family for family in APP_FAMILIES for bed_type in family.asks}
# Routes reached through their family's one row and question.
FAMILY_STEP_ROUTES: Final = frozenset(
    bed_type for family in APP_FAMILIES for bed_type in family.routes
)
_BY_ROW: Final = {family.row: family for family in APP_FAMILIES}
FAMILY_ROW_SEPARATOR: Final = " · "


def question_family(bed_type: str | None) -> AppFamily | None:
    """Return the family whose question a new bed on this route is asked."""
    return _BY_BED_TYPE.get(bed_type) if bed_type is not None else None


def answer_family(bed_type: str, variant: str | None) -> AppFamily | None:
    """Return the family whose question offers this route as one of its members."""
    return next(
        (
            family
            for family in APP_FAMILIES
            for answer in family.answers.values()
            if answer.member and (answer.bed_type, answer.variant) == (bed_type, variant)
        ),
        None,
    )


def row_family(bed_type: str) -> AppFamily | None:
    """Return the family whose row this bed type is."""
    return _BY_ROW.get(bed_type)


def family_row_label(bed_type: str) -> str | None:
    """Return a family row's list label, "<apps> · <family>", or None."""
    if (family := row_family(bed_type)) is None:
        return None
    return f"{family.apps}{FAMILY_ROW_SEPARATOR}{family.name}"


def shown_row(route: str, *, configure: bool) -> str | None:
    """Return the family row a list drawn for this route shows in its place.

    Configure lists a route by its own label, except Vibradorm's, whose apps
    change only through the guided change.
    """
    for family in APP_FAMILIES:
        if not family.routes_show_row or (configure and family is not VIBRADORM_FAMILY):
            continue
        if route in family.routes or route in family.aliases:
            return family.row
    return None
