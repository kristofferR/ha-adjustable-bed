"""Static traits of each bed type, known before any connection.

One record per bed type (refined per protocol variant where a trait depends on
it) answers what setup defaults, entity creation and the coordinator assume
before a controller exists. The controller factory stamps the same record on
every controller it builds, so controller properties default to it. A
controller may still refine a trait at runtime, for example after discovery.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Final

from .const import (
    BED_TYPE_ADJUSTABLE_BED,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_ADJUSTAMATTRESS,
    BED_TYPE_BEDJET_POWERLAYER,
    BED_TYPE_BEDSENSE,
    BED_TYPE_BF,
    BED_TYPE_CASPER_BASE,
    BED_TYPE_CASPER_SLEEP_MM,
    BED_TYPE_CASPER_SLEEP_SXB,
    BED_TYPE_CHERISH,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COMFORTBASE,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_ERGOMOTION_4,
    BED_TYPE_ESHINE,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GALAXY,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GMMOTOR_SLEEP_MM,
    BED_TYPE_GMMOTOR_SLEEP_SXB,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_HUSH_BASE,
    BED_TYPE_HUSH_SLEEP_MM,
    BED_TYPE_HUSH_SLEEP_SXB,
    BED_TYPE_ISLEEP,
    BED_TYPE_JALON,
    BED_TYPE_JALON_BED,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MLILY,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_RESIDENT,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT_APP,
    BED_TYPE_RICHMAT_APP_SLEEP,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_RIZE,
    BED_TYPE_RIZE_HOME,
    BED_TYPE_SBI,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPSTAR,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SUTA,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
    BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
    DEFAULT_DISCONNECT_AFTER_COMMAND,
    KEESON_LAYOUT_APP_BED_TYPES,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_SINO,
    ORE_COMFORT_BED_VARIANTS,
    REVERIE_BACK_MAX_ANGLE,
    RICHMAT_MH_BED_TYPES,
    SBI_FOOT_MAX_ANGLE,
    SBI_HEAD_MAX_ANGLE,
    SERTA_MP_REMOTE_BACK_MAX_ANGLE,
    SERTA_MP_REMOTE_LEGS_MAX_ANGLE,
    STARCODE_APP_CONNECTION_TIMEOUT_SECONDS,
    VARIANT_AUTO,
    resolve_explicit_bed_type,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BedTraits:
    """What a bed type declares about itself before connecting."""

    # Reports motor positions, so position sliders and seeking are offered.
    position_feedback: bool = False
    # Reported positions are 0-100 percentages rather than degrees.
    percentage_positions: bool = False
    # Exposes degree angle sensors for its axes.
    angle_sensors: bool = False
    # Reports no usable angles: stale angle sensors and position sliders from
    # earlier versions or profiles are removed (#322, #344, #501).
    no_angle_feedback: bool = False
    # The controller holds the BLE link for the entry's lifetime.
    persistent_connection: bool = False
    # Controls keep state in the connection-scoped controller, so a new entry
    # keeps the link between commands by default.
    connection_scoped_state: bool = False
    # Startup hooks own Device Information reads, including their timing.
    owns_device_info_reads: bool = False
    passive_position_reconciliation: bool = False
    # Overrides the connection profile's connect timeout, in seconds.
    connection_timeout: float | None = None
    # Travel limits in degrees, per axis, for frames whose hardware travels a
    # fixed range. They replace the configurable back and legs maximums.
    max_angles: Mapping[str, float] = field(default_factory=dict)

    @property
    def disconnect_after_command(self) -> bool:
        """Return the "disconnect after command" default for a new entry.

        These beds accept one BLE connection at a time, so holding the link
        locks out the physical remote and the vendor app until the idle timeout.
        Handing it straight back is the better default unless the bed needs it.
        """
        return not (self.persistent_connection or self.connection_scoped_state)


_NONE: Final = BedTraits()
_NO_ANGLES: Final = BedTraits(no_angle_feedback=True)
_SCOPED: Final = BedTraits(connection_scoped_state=True)
_NO_ANGLES_SCOPED: Final = BedTraits(no_angle_feedback=True, connection_scoped_state=True)
_NO_ANGLES_PERSISTENT: Final = BedTraits(no_angle_feedback=True, persistent_connection=True)
_PERCENT_FEEDBACK_SCOPED: Final = BedTraits(
    position_feedback=True, percentage_positions=True, connection_scoped_state=True
)
_ANGLE_FEEDBACK_SCOPED: Final = BedTraits(
    position_feedback=True, angle_sensors=True, connection_scoped_state=True
)
# Reverie frames stop the head/back axis short of the standard 68 degrees.
_REVERIE_MAX_ANGLES: Final = {"back": REVERIE_BACK_MAX_ANGLE, "head": REVERIE_BACK_MAX_ANGLE}

# Bed types absent here have no static traits (BedTraits()). The base record of
# a bed type with variants describes its automatic route; bed_traits() refines it.
_BED_TRAITS: Final[dict[str, BedTraits]] = {
    "paramount": BedTraits(position_feedback=True, connection_scoped_state=True, max_angles={"head": 75, "back": 75, "legs": 30, "feet": 30}),
    "smart_comfort_synargy": _NO_ANGLES_SCOPED,
    "smart_comfort_synergy": _NO_ANGLES_SCOPED,
    **dict.fromkeys(RICHMAT_MH_BED_TYPES, _NO_ANGLES),
    # Serta MP Remote is the one Keeson layout app with position feedback.
    **dict.fromkeys(KEESON_LAYOUT_APP_BED_TYPES - {BED_TYPE_SERTA_MP_REMOTE}, _NO_ANGLES),
    BED_TYPE_ADJUSTABLE_BED: _NO_ANGLES,
    BED_TYPE_ADJUSTABLE_LUMBAR: _NO_ANGLES,
    BED_TYPE_RIZE_HOME: _NO_ANGLES_SCOPED,
    BED_TYPE_RESIDENT: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_ADJUSTAMATTRESS: _NO_ANGLES,
    # Measured against the BedJet LCD remote's own degree readout.
    BED_TYPE_BEDJET_POWERLAYER: BedTraits(
        position_feedback=True,
        max_angles={
            "back": BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
            "head": BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
            "legs": BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
            "feet": BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
        },
    ),
    BED_TYPE_BEDSENSE: _NO_ANGLES,
    BED_TYPE_BF: _NO_ANGLES,
    BED_TYPE_JALON_BED: _NO_ANGLES_SCOPED,
    BED_TYPE_CASPER_BASE: _NO_ANGLES,
    "casper_remote": _NO_ANGLES,
    BED_TYPE_CASPER_SLEEP_MM: _NO_ANGLES,
    BED_TYPE_CASPER_SLEEP_SXB: _NO_ANGLES,
    BED_TYPE_CHERISH: _NO_ANGLES,
    BED_TYPE_RICHMAT_CLASSIC_APPS: _NO_ANGLES,
    # Preset repeat-tap and massage cycles depend on connection-local state.
    BED_TYPE_COMFORT_ENHANCEMENTS: _NO_ANGLES_SCOPED,
    BED_TYPE_COMFORTBASE: _NO_ANGLES_SCOPED,
    BED_TYPE_COMFORT_MOTION: _SCOPED,
    BED_TYPE_CUSTOMATIC_CLARITY: _NO_ANGLES,
    BED_TYPE_CUSTOMATIC_JEROMES: _NO_ANGLES,
    BED_TYPE_CUSTOMATIC_REMEDY: _NO_ANGLES,
    # Realtime sensor reports and report continuation use the live RX stream.
    BED_TYPE_DOUBLESLEEP: _NO_ANGLES_PERSISTENT,
    BED_TYPE_ERGOMOTION: _PERCENT_FEEDBACK_SCOPED,
    BED_TYPE_ERGOMOTION_4: _NO_ANGLES,
    BED_TYPE_ESHINE: _NO_ANGLES,
    BED_TYPE_ESHINE_OKIN: _NO_ANGLES,
    BED_TYPE_FSM_RELAX: _NO_ANGLES,
    BED_TYPE_FURNIMOVE: _NO_ANGLES,
    # Massage adjustments require the timer state received on this connection.
    BED_TYPE_JALON: _NO_ANGLES_SCOPED,
    BED_TYPE_GLIDEAWAY_MOTION: _NO_ANGLES,
    # The app exposes raw motor-index/desk reports, without a proven mapping to
    # the generic head/back/legs/feet angle entities.
    BED_TYPE_GMMOTOR: _NO_ANGLES_SCOPED,
    BED_TYPE_GMMOTOR_SLEEP_MM: _NO_ANGLES_PERSISTENT,
    BED_TYPE_GMMOTOR_SLEEP_SXB: _NO_ANGLES_PERSISTENT,
    BED_TYPE_GALAXY: _NO_ANGLES,
    BED_TYPE_GOODVIBE: _NO_ANGLES,
    BED_TYPE_MLILY: _NO_ANGLES,
    BED_TYPE_HJBED: _NO_ANGLES,
    BED_TYPE_RICHMAT_APP: _NO_ANGLES,
    BED_TYPE_RICHMAT_APP_SLEEP: _NO_ANGLES,
    BED_TYPE_HUSH_BASE: _NO_ANGLES,
    "luuna": _NO_ANGLES_SCOPED,
    "hush_remote": _NO_ANGLES,
    BED_TYPE_HUSH_SLEEP_MM: _NO_ANGLES,
    BED_TYPE_HUSH_SLEEP_SXB: _NO_ANGLES,
    BED_TYPE_ISLEEP: _NO_ANGLES_SCOPED,
    BED_TYPE_RIZE: _NO_ANGLES_SCOPED,
    BED_TYPE_JENSEN: _PERCENT_FEEDBACK_SCOPED,
    BED_TYPE_JIECANG: _SCOPED,
    BED_TYPE_JIECANG_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_KAIDI: _SCOPED,
    # Keeson, Serta and OKIN FFE share KeesonController, which reports
    # percentages. Only the Ergomotion variant reports positions.
    BED_TYPE_KEESON: BedTraits(percentage_positions=True, connection_scoped_state=True),
    # LP Comfort Connect is held open pending hardware confirmation of bonded
    # reconnects (#385).
    BED_TYPE_LEGGETT_GEN2: BedTraits(persistent_connection=True),
    BED_TYPE_LEGGETT_LP_LEGACY: _NO_ANGLES,
    # The automatic route usually resolves to Gen2, so assume it until connected.
    BED_TYPE_LEGGETT_PLATT: BedTraits(persistent_connection=True),
    BED_TYPE_LEGGETT_WILINKE: _SCOPED,
    BED_TYPE_LIMOSS: BedTraits(position_feedback=True, connection_scoped_state=True),
    BED_TYPE_LIMOSS_REMOTE: _NO_ANGLES,
    BED_TYPE_LINAK: BedTraits(
        position_feedback=True, angle_sensors=True, passive_position_reconciliation=True
    ),
    # Pressure is polled only on a held link, like the app's pump tab.
    BED_TYPE_LOGICDATA_AIR_PUMP: _NO_ANGLES_SCOPED,
    BED_TYPE_LOGICDATA_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_MALOUF_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_MOTION_BED: _NO_ANGLES_SCOPED,
    BED_TYPE_MOTOMOTION: _NO_ANGLES,
    BED_TYPE_OCTO: _SCOPED,
    BED_TYPE_OKIMAT: _ANGLE_FEEDBACK_SCOPED,
    BED_TYPE_OKIN_CB24: _SCOPED,
    BED_TYPE_OKIN_CST: _NO_ANGLES_SCOPED,
    BED_TYPE_OKIN_FFE: BedTraits(percentage_positions=True),
    BED_TYPE_OKIN_ORE: _SCOPED,
    # The stair receiver times out on idle reconnects (#344).
    BED_TYPE_OKIN_RF_ECO_BT: _NO_ANGLES_PERSISTENT,
    BED_TYPE_OKIN_UUID: _ANGLE_FEEDBACK_SCOPED,
    BED_TYPE_REVERIE: replace(_ANGLE_FEEDBACK_SCOPED, max_angles=_REVERIE_MAX_ANGLES),
    BED_TYPE_REVERIE_NIGHTSTAND: BedTraits(
        position_feedback=True,
        percentage_positions=True,
        angle_sensors=True,
        connection_scoped_state=True,
        max_angles=_REVERIE_MAX_ANGLES,
    ),
    BED_TYPE_REVERIE_PAIRLINK: BedTraits(
        position_feedback=True, percentage_positions=True, angle_sensors=True
    ),
    "richmat_sleep_receiver": _NO_ANGLES_PERSISTENT,
    # Head and foot angles come from the app's pulse lookup tables (#239).
    BED_TYPE_SBI: BedTraits(
        position_feedback=True,
        max_angles={"back": SBI_HEAD_MAX_ANGLE, "legs": SBI_FOOT_MAX_ANGLE},
    ),
    BED_TYPE_SERENITY: _NO_ANGLES,
    BED_TYPE_SERTA: BedTraits(percentage_positions=True),
    BED_TYPE_SERTA_MP_REMOTE: BedTraits(
        position_feedback=True,
        max_angles={
            "back": SERTA_MP_REMOTE_BACK_MAX_ANGLE,
            "legs": SERTA_MP_REMOTE_LEGS_MAX_ANGLE,
        },
    ),
    BED_TYPE_SIMMONS: _NO_ANGLES,
    BED_TYPE_SLEEP_NUMBER: _PERCENT_FEEDBACK_SCOPED,
    # MCR exposes positions only for actuators foundation discovery proves.
    BED_TYPE_SLEEP_NUMBER_MCR: BedTraits(
        position_feedback=True, percentage_positions=True, persistent_connection=True
    ),
    BED_TYPE_SLEEPSTAR: _PERCENT_FEEDBACK_SCOPED,
    BED_TYPE_SLEEPTRACKER: _NO_ANGLES,
    # The app reports three axes, but the accepted parser evidence does not map
    # them to this integration's named motor positions.
    BED_TYPE_SLEEPYS_ELITE_APP: _NONE,
    BED_TYPE_SLEEPYS_BOX25: _PERCENT_FEEDBACK_SCOPED,
    # The app gives up on a connect attempt after its own timeout.
    BED_TYPE_STARCODE_ABM5_4: BedTraits(
        no_angle_feedback=True,
        connection_scoped_state=True,
        connection_timeout=STARCODE_APP_CONNECTION_TIMEOUT_SECONDS,
    ),
    # M1X12 feedback reports opaque Part percentages, not named degree axes.
    BED_TYPE_STARCODE_M1X12: _NO_ANGLES,
    BED_TYPE_STARCODE_M5X5: BedTraits(position_feedback=True, percentage_positions=True),
    BED_TYPE_SUTA: _SCOPED,
    BED_TYPE_SVANE: _SCOPED,
    BED_TYPE_TRANQUIL: _NO_ANGLES,
    BED_TYPE_VIBRADORM: BedTraits(position_feedback=True, connection_scoped_state=True),
    BED_TYPE_VIBRADORM_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_VMATBASIC: _NO_ANGLES_SCOPED,
    BED_TYPE_ZSERIES: _NO_ANGLES,
}

_REVERIE_MODEL_BED_TYPES: Final = frozenset(
    {BED_TYPE_REVERIE, BED_TYPE_REVERIE_NIGHTSTAND, BED_TYPE_REVERIE_PAIRLINK}
)
# Keeson routes that may resolve to a connection-scoped controller before connecting.
_KEESON_SCOPED_VARIANTS: Final = frozenset(
    {None, "", VARIANT_AUTO, KEESON_VARIANT_ERGOMOTION, KEESON_VARIANT_SINO}
)
_GOODVIBE_SLEEP_SENSORS: Final = frozenset({"sleep_rm", "sleep_hj"})


def bed_traits(bed_type: str | None, protocol_variant: str | None = None) -> BedTraits:
    """Return the static traits of a bed type and protocol variant."""
    if not bed_type:
        return _NONE
    resolved = resolve_explicit_bed_type(bed_type, protocol_variant)
    traits = _BED_TRAITS.get(resolved, _NONE)
    if resolved == "bedtech" and protocol_variant not in (None, "", VARIANT_AUTO):
        return _NO_ANGLES
    if resolved in _REVERIE_MODEL_BED_TYPES:
        from .beds.reverie.profiles import resolve_reverie_model

        positions = resolve_reverie_model(protocol_variant).positions
        return replace(
            traits,
            position_feedback=positions,
            angle_sensors=positions,
            percentage_positions=traits.percentage_positions and positions,
        )
    if resolved == BED_TYPE_KEESON:
        return replace(
            traits,
            position_feedback=protocol_variant == KEESON_VARIANT_ERGOMOTION,
            percentage_positions=protocol_variant not in ORE_COMFORT_BED_VARIANTS,
            connection_scoped_state=protocol_variant in _KEESON_SCOPED_VARIANTS,
        )
    if resolved in (BED_TYPE_GOODVIBE, BED_TYPE_MLILY):
        return replace(traits, connection_scoped_state=protocol_variant in _GOODVIBE_SLEEP_SENSORS)
    return traits


def bed_type_has_position_feedback(bed_type: str | None, protocol_variant: str | None) -> bool:
    """Return True if this bed type/variant combination reports motor positions.

    Callers that decide whether to create position entities, accept
    set_position calls, or probe for position feedback must all agree.
    """
    return bed_traits(bed_type, protocol_variant).position_feedback


def disconnect_after_command_default_enabled(
    bed_type: str | None, protocol_variant: str | None = None
) -> bool:
    """Return whether a NEW entry should free the BLE link after each command.

    An existing entry already stores its own value, which is left alone.
    """
    if not bed_type:
        return DEFAULT_DISCONNECT_AFTER_COMMAND
    return bed_traits(bed_type, protocol_variant).disconnect_after_command


def supports_passive_position_reconciliation(bed_type: str | None) -> bool:
    """Return True if the bed type supports passive position reconciliation."""
    return bed_traits(bed_type).passive_position_reconciliation


def passive_position_reconciliation_default_enabled(bed_type: str | None) -> bool:
    """Return whether passive position reconciliation should default to enabled."""
    return supports_passive_position_reconciliation(bed_type)
