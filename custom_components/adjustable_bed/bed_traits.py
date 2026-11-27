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
    BED_TYPE_ALYA,
    BED_TYPE_AMBIENT,
    BED_TYPE_ATLAS_LIFT,
    BED_TYPE_BEDJET_POWERLAYER,
    BED_TYPE_BEDSENSE,
    BED_TYPE_BETTERLIVING2,
    BED_TYPE_BF,
    BED_TYPE_BOBPOWERBASE,
    BED_TYPE_CASPER_BASE,
    BED_TYPE_CASPER_SLEEP_MM,
    BED_TYPE_CASPER_SLEEP_SXB,
    BED_TYPE_CHERISH,
    BED_TYPE_COMFORT_BED,
    BED_TYPE_COMFORT_ENHANCEMENT3,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COMFORTBASE,
    BED_TYPE_COMFYDS,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_DEMO,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ENSO2,
    BED_TYPE_ERGOBED,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_ERGOMOTION_4,
    BED_TYPE_ESHINE,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FLEXISPOT,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GALAXY,
    BED_TYPE_GHOSTBED,
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
    BED_TYPE_JEROME_ADJUSTABLE_BASE,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_JOBS,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_KOMFYD,
    BED_TYPE_LANGJUE,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIKIMIO,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_LINX,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MLILY,
    BED_TYPE_MLILY0,
    BED_TYPE_MLILY_REMOTE,
    BED_TYPE_MOODBASE,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_MYSIDE,
    BED_TYPE_N32_MOTION_BED,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMATTMOTION,
    BED_TYPE_OKIMIKI,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_MOTIONBED,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_QPLUS_APP,
    BED_TYPE_RESIDENT,
    BED_TYPE_RESTFUL,
    BED_TYPE_RESTONIC,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT_APP,
    BED_TYPE_RICHMAT_APP_SLEEP,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_RIZE,
    BED_TYPE_RIZE_HOME,
    BED_TYPE_RIZE_REMEDY_II,
    BED_TYPE_RONCO_MOTION,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SHUDA,
    BED_TYPE_SILVERMOTION,
    BED_TYPE_SIMMONS,
    BED_TYPE_SIMMONS_BLUE,
    BED_TYPE_SLEEP_ASSIST_PRO,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPSTAR,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOMOS,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SUPERIOR_SLEEP,
    BED_TYPE_SUTA,
    BED_TYPE_SUTA_KING_KOIL,
    BED_TYPE_SVANE,
    BED_TYPE_SYMPHONY,
    BED_TYPE_SYMPHONY_SLEEP,
    BED_TYPE_TOPCARE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_TRUEMOTION,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VINDO,
    BED_TYPE_VMATBASIC,
    BED_TYPE_YAMADA,
    BED_TYPE_ZSERIES,
    BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
    BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_PROTOCOL_VARIANT,
    CONNECTION_MODE_ALWAYS,
    CONNECTION_MODE_IDLE,
    CONNECTION_MODE_RELEASE,
    KEESON_LAYOUT_APP_BED_TYPES,
    KEESON_VARIANT_COMFORTFURNITURE,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_SINO,
    ORE_COMFORT_BED_VARIANTS,
    ORE_GATT_ROUTED_VARIANTS,
    QPLUS_FOOT_MAX_ANGLE,
    QPLUS_HEAD_MAX_ANGLE,
    REVERIE_BACK_MAX_ANGLE,
    RICHMAT_MH_BED_TYPES,
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
    # STOP fences admitted refresh and runs controller cleanup on the current
    # link, without connecting or preparing a replacement link.
    cancellation_only_stop: bool = False
    # Controls keep state in the connection-scoped controller, so a new entry
    # keeps the link between commands by default.
    connection_scoped_state: bool = False
    # Reconnecting needs a bond the bed may refuse outside its pairing window,
    # so a new entry keeps the link between commands by default.
    costly_reconnect: bool = False
    # The bed pairs only for a few minutes after power-on and ignores connection
    # attempts from other adapters, so a failed connection to an advertising bed
    # is explained as a closed pairing window.
    pairing_window_at_power_on: bool = False
    # Startup hooks own Device Information reads, including their timing.
    owns_device_info_reads: bool = False
    # A single-address pair may need separate Left and Right operations.
    single_address_native_both: bool = True
    passive_position_reconciliation: bool = False
    # Overrides the connection profile's connect timeout, in seconds.
    connection_timeout: float | None = None
    # Travel limits in degrees, per axis, for frames whose hardware travels a
    # fixed range. They replace the configurable back and legs maximums.
    max_angles: Mapping[str, float] = field(default_factory=dict)

    @property
    def connection_mode(self) -> str:
        """Return a new entry's default connection mode.

        These beds accept one BLE connection at a time, so holding the link
        locks out the physical remote and the vendor app until the idle timeout.
        Handing it straight back is the better default unless the bed needs it.
        """
        if self.persistent_connection:
            return CONNECTION_MODE_ALWAYS
        if self.connection_scoped_state or self.costly_reconnect:
            return CONNECTION_MODE_IDLE
        return CONNECTION_MODE_RELEASE


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
    "agingplace": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "bedgear": BedTraits(no_angle_feedback=True, connection_scoped_state=True),
    "l2motion": BedTraits(no_angle_feedback=True, connection_scoped_state=True),
    BED_TYPE_ERGOBED: BedTraits(no_angle_feedback=True, connection_scoped_state=True, single_address_native_both=False, connection_timeout=5),
    BED_TYPE_MOODBASE: BedTraits(no_angle_feedback=True, connection_scoped_state=True, single_address_native_both=False, connection_timeout=5),
    "paramount": BedTraits(position_feedback=True, connection_scoped_state=True, max_angles={"head": 75, "back": 75, "legs": 30, "feet": 30}),
    "ormatek": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "dorsal": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5.0),
    "berun": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "nerum": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "relax_motion": _NO_ANGLES_SCOPED,
    "cheerssleep": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, single_address_native_both=False),
    "smart_sleep": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "sleep_assistant": _NO_ANGLES_SCOPED,
    BED_TYPE_SLEEP_ASSIST_PRO: _NO_ANGLES_SCOPED,
    "onlysnore": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    # Head, reclining and lumbar travel as the apps' Position screen scales it.
    "smart_comfort_synargy": _PERCENT_FEEDBACK_SCOPED,
    "smart_comfort_synergy": _PERCENT_FEEDBACK_SCOPED,
    **dict.fromkeys(RICHMAT_MH_BED_TYPES, _NO_ANGLES),
    # Q-Plus and Serta MP Remote are the Keeson layout apps with position feedback.
    **dict.fromkeys(
        KEESON_LAYOUT_APP_BED_TYPES - {BED_TYPE_QPLUS_APP, BED_TYPE_SERTA_MP_REMOTE}, _NO_ANGLES
    ),
    BED_TYPE_ADJUSTABLE_BED: _NO_ANGLES,
    BED_TYPE_ADJUSTABLE_LUMBAR: _NO_ANGLES,
    BED_TYPE_SUPERIOR_SLEEP: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    BED_TYPE_RIZE_HOME: _NO_ANGLES_SCOPED,
    BED_TYPE_OKIN_MOTIONBED: replace(_NO_ANGLES, owns_device_info_reads=True),
    BED_TYPE_OKIMATTMOTION: replace(_NO_ANGLES, owns_device_info_reads=True),
    BED_TYPE_COMFORT_ENHANCEMENT3: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_N32_MOTION_BED: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_SHUDA: replace(_NO_ANGLES, owns_device_info_reads=True, connection_timeout=5),
    BED_TYPE_RESIDENT: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "sleeptime": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "powersbedding": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "hestia_motion": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "ultramatic_smart_bed": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
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
    BED_TYPE_GHOSTBED: replace(_NO_ANGLES_SCOPED, connection_timeout=10.0, owns_device_info_reads=True),
    BED_TYPE_FLEXISPOT: replace(_NO_ANGLES_SCOPED, connection_timeout=10.0, owns_device_info_reads=True),
    BED_TYPE_JALON_BED: _NO_ANGLES_SCOPED,
    BED_TYPE_LANGJUE: _NO_ANGLES_SCOPED,
    BED_TYPE_MYSIDE: replace(_NO_ANGLES_SCOPED, connection_timeout=5.0, owns_device_info_reads=True),
    BED_TYPE_LINX: replace(_NO_ANGLES_SCOPED, connection_timeout=10.0, owns_device_info_reads=True),
    BED_TYPE_SYMPHONY_SLEEP: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_SYMPHONY: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, single_address_native_both=False, connection_timeout=8.0),
    "enso": _NO_ANGLES_SCOPED,
    BED_TYPE_ENSO2: replace(_NO_ANGLES_SCOPED, connection_timeout=10, owns_device_info_reads=True),
    "sealy_posturematic": BedTraits(no_angle_feedback=True, connection_scoped_state=True, connection_timeout=5.0),
    BED_TYPE_YAMADA: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_BETTERLIVING2: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_CASPER_BASE: _NO_ANGLES,
    BED_TYPE_RONCO_MOTION: _NO_ANGLES_SCOPED,
    "casper_remote": _NO_ANGLES,
    BED_TYPE_CASPER_SLEEP_MM: _NO_ANGLES,
    BED_TYPE_CASPER_SLEEP_SXB: _NO_ANGLES,
    BED_TYPE_CHERISH: _NO_ANGLES,
    BED_TYPE_RICHMAT_CLASSIC_APPS: _NO_ANGLES,
    # Preset repeat-tap and massage cycles depend on connection-local state.
    BED_TYPE_COMFORT_ENHANCEMENTS: _NO_ANGLES_SCOPED,
    "scott_living": replace(
        _NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=10,
        cancellation_only_stop=True,
    ),
    BED_TYPE_RESTONIC: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5, single_address_native_both=False),
    "kingkoil": replace(
        _NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5,
        cancellation_only_stop=True,
    ),
    BED_TYPE_SOMOS: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    BED_TYPE_COMFORTBASE: _NO_ANGLES_SCOPED,
    BED_TYPE_COMFORT_MOTION: _SCOPED,
    BED_TYPE_CUSTOMATIC_DEMO: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_CUSTOMATIC_CLARITY: _NO_ANGLES,
    BED_TYPE_CUSTOMATIC_JEROMES: _NO_ANGLES,
    BED_TYPE_CUSTOMATIC_REMEDY: _NO_ANGLES,
    # Realtime sensor reports and report continuation use the live RX stream.
    BED_TYPE_DOUBLESLEEP: _NO_ANGLES_PERSISTENT,
    BED_TYPE_ERGOMOTION: _PERCENT_FEEDBACK_SCOPED,
    BED_TYPE_ERGOMOTION_4: _NO_ANGLES,
    BED_TYPE_ESHINE: _NO_ANGLES,
    BED_TYPE_ALYA: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
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
    BED_TYPE_ATLAS_LIFT: _NO_ANGLES,
    BED_TYPE_TOPCARE: _NO_ANGLES,
    BED_TYPE_COMFORT_BED: replace(_NO_ANGLES_SCOPED, connection_timeout=5, owns_device_info_reads=True),
    BED_TYPE_GOODVIBE: _NO_ANGLES,
    BED_TYPE_MLILY: _NO_ANGLES,
    "majestichome": _NO_ANGLES,
    BED_TYPE_OKIMIKI: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    BED_TYPE_BOBPOWERBASE: replace(_NO_ANGLES, connection_scoped_state=True, single_address_native_both=False, connection_timeout=5),
    BED_TYPE_MLILY0: replace(_NO_ANGLES, connection_scoped_state=True),
    BED_TYPE_MLILY_REMOTE: replace(_NO_ANGLES, connection_scoped_state=True, single_address_native_both=False),
    BED_TYPE_HJBED: _NO_ANGLES,
    BED_TYPE_JEROME_ADJUSTABLE_BASE: _NO_ANGLES_SCOPED,
    BED_TYPE_RICHMAT_APP: _NO_ANGLES,
    BED_TYPE_RICHMAT_APP_SLEEP: _NO_ANGLES,
    BED_TYPE_HUSH_BASE: _NO_ANGLES,
    "silksnow": BedTraits(no_angle_feedback=True, connection_scoped_state=True, connection_timeout=5.0),
    "luuna": _NO_ANGLES_SCOPED,
    "instant_comfort": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, single_address_native_both=False),
    "personal_comfort": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, single_address_native_both=False),
    "ifit": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, single_address_native_both=False, connection_timeout=5),
    "leva": replace(_NO_ANGLES_SCOPED, connection_timeout=15.0, owns_device_info_reads=True),
    "mline": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "sinca_comfort": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=8),
    "luniosmart": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "sleep_evolution": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "wsilver_legacy": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_LIKIMIO: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "awmotion": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "dreamsense": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "muuegm": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "saatva": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "super_colchones": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "ergobq": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    "sonicsleep": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    "hush_remote": _NO_ANGLES,
    BED_TYPE_HUSH_SLEEP_MM: _NO_ANGLES,
    BED_TYPE_HUSH_SLEEP_SXB: _NO_ANGLES,
    BED_TYPE_ISLEEP: _NO_ANGLES_SCOPED,
    BED_TYPE_KOMFYD: _NO_ANGLES_SCOPED,
    BED_TYPE_COMFYDS: _NO_ANGLES_SCOPED,
    BED_TYPE_RIZE: _NO_ANGLES_SCOPED,
    BED_TYPE_JENSEN: _PERCENT_FEEDBACK_SCOPED,
    BED_TYPE_JIECANG: _SCOPED,
    BED_TYPE_JIECANG_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_KAIDI: _SCOPED,
    # Keeson and OKIN FFE share KeesonController, which reports
    # percentages. Only the Ergomotion variant reports positions.
    BED_TYPE_KEESON: BedTraits(percentage_positions=True, connection_scoped_state=True),
    # LP Comfort Connect needs its bond on every reconnect (#385, #709), so it
    # stays connected between commands and holds the link once a reconnect stalls.
    BED_TYPE_LEGGETT_GEN2: BedTraits(costly_reconnect=True),
    BED_TYPE_LEGGETT_LP_LEGACY: _NO_ANGLES,
    # The automatic route usually resolves to Gen2, so assume it until connected.
    BED_TYPE_LEGGETT_PLATT: BedTraits(costly_reconnect=True),
    BED_TYPE_LEGGETT_WILINKE: _SCOPED,
    BED_TYPE_LIMOSS: BedTraits(position_feedback=True, connection_scoped_state=True),
    BED_TYPE_LIMOSS_REMOTE: _NO_ANGLES,
    BED_TYPE_AMBIENT: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_VINDO: replace(_NO_ANGLES, owns_device_info_reads=True),
    BED_TYPE_LINAK: BedTraits(
        position_feedback=True,
        angle_sensors=True,
        passive_position_reconciliation=True,
        pairing_window_at_power_on=True,
    ),
    # Pressure is polled only on a held link, like the app's pump tab.
    BED_TYPE_LOGICDATA_AIR_PUMP: _NO_ANGLES_SCOPED,
    BED_TYPE_LOGICDATA_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_SILVERMOTION: _NO_ANGLES_SCOPED,
    BED_TYPE_MALOUF_APP: _NO_ANGLES_SCOPED,
    BED_TYPE_MOTION_BED: _NO_ANGLES_SCOPED,
    BED_TYPE_MOTOMOTION: _NO_ANGLES,
    BED_TYPE_OCTO: _SCOPED,
    # Saved as okin_cb24 until schema 5.7; earlier migration steps read its defaults.
    "okin_cb24": _SCOPED,
    "smartbed": replace(_SCOPED, no_angle_feedback=True),
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
    # Positions and the other feedback arrive only on a live mesh session.
    BED_TYPE_REVERIE_PAIRLINK: BedTraits(
        position_feedback=True,
        percentage_positions=True,
        angle_sensors=True,
        connection_scoped_state=True,
    ),
    "richmat_sleep_receiver": _NO_ANGLES_PERSISTENT,
    # Head and foot angles come from the app's pulse lookup tables (#239).
    BED_TYPE_QPLUS_APP: BedTraits(
        position_feedback=True,
        max_angles={"back": QPLUS_HEAD_MAX_ANGLE, "legs": QPLUS_FOOT_MAX_ANGLE},
    ),
    # Saved as sbi until schema 5.9; earlier migration steps read its defaults.
    "sbi": BedTraits(position_feedback=True),
    BED_TYPE_SERENITY: _NO_ANGLES,
    # Saved as serta until schema 5.10; earlier migration steps read its defaults.
    "serta": BedTraits(percentage_positions=True),
    BED_TYPE_SERTA_MP_REMOTE: BedTraits(
        position_feedback=True,
        max_angles={
            "back": SERTA_MP_REMOTE_BACK_MAX_ANGLE,
            "legs": SERTA_MP_REMOTE_LEGS_MAX_ANGLE,
        },
    ),
    "meisemobell": replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, connection_timeout=5),
    BED_TYPE_SIMMONS: _NO_ANGLES,
    BED_TYPE_SIMMONS_BLUE: replace(_NO_ANGLES, connection_timeout=5.0),
    BED_TYPE_SLEEP_NUMBER: _PERCENT_FEEDBACK_SCOPED,
    # MCR exposes positions only for actuators foundation discovery proves.
    BED_TYPE_SLEEP_NUMBER_MCR: BedTraits(
        position_feedback=True, percentage_positions=True, persistent_connection=True
    ),
    BED_TYPE_SLEEPSTAR: _PERCENT_FEEDBACK_SCOPED,
    BED_TYPE_SLEEPTRACKER: _NO_ANGLES,
    # Only the BOX25 control boxes report head, foot and lumbar; the controller
    # narrows the others.
    BED_TYPE_SLEEPYS_ELITE_APP: BedTraits(position_feedback=True, percentage_positions=True),
    BED_TYPE_SLEEPYS_BOX25: _PERCENT_FEEDBACK_SCOPED,
    # The app gives up on a connect attempt after its own timeout.
    BED_TYPE_STARCODE_ABM5_4: BedTraits(
        no_angle_feedback=True,
        connection_scoped_state=True,
        connection_timeout=STARCODE_APP_CONNECTION_TIMEOUT_SECONDS,
    ),
    # Head, foot and lumbar percentages, read only: the app has no way to set one.
    BED_TYPE_STARCODE_M1X12: BedTraits(position_feedback=True, percentage_positions=True),
    BED_TYPE_STARCODE_M5X5: BedTraits(position_feedback=True, percentage_positions=True),
    BED_TYPE_SUTA: _SCOPED,
    BED_TYPE_TRUEMOTION: replace(_NO_ANGLES_SCOPED, connection_timeout=8),
    BED_TYPE_SUTA_KING_KOIL: replace(_NO_ANGLES_SCOPED, connection_timeout=8),
    BED_TYPE_SVANE: _SCOPED,
    BED_TYPE_JOBS: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_TRANQUIL: _NO_ANGLES,
    BED_TYPE_RESTFUL: replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True),
    BED_TYPE_RIZE_REMEDY_II: _NO_ANGLES,
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
    {None, "", VARIANT_AUTO, KEESON_VARIANT_ERGOMOTION, KEESON_VARIANT_SINO, *ORE_GATT_ROUTED_VARIANTS}
)
_GOODVIBE_SLEEP_SENSORS: Final = frozenset({"sleep_rm", "sleep_hj"})


def bed_traits(bed_type: str | None, protocol_variant: str | None = None) -> BedTraits:
    """Return the static traits of a bed type and protocol variant."""
    if not bed_type:
        return _NONE
    resolved = resolve_explicit_bed_type(bed_type, protocol_variant)
    traits = _BED_TRAITS.get(resolved, _NONE)
    if resolved == BED_TYPE_LINAK and protocol_variant == "carpe_diem":
        return replace(_NO_ANGLES_SCOPED, owns_device_info_reads=True, cancellation_only_stop=True)
    if resolved == "richmat_classic_apps" and protocol_variant == "lp2":
        return replace(traits, owns_device_info_reads=True)
    if resolved == "richmat_classic_apps" and protocol_variant == "jerome2":
        return replace(traits, single_address_native_both=False)
    if resolved == "richmat_classic_apps" and protocol_variant == "dreamlab2":
        return replace(traits, single_address_native_both=False, owns_device_info_reads=True)
    if resolved == "solace" and protocol_variant in ("sophie", "flexirest"):
        return replace(traits, no_angle_feedback=True, connection_scoped_state=True, owns_device_info_reads=True)
    if resolved in ("richmat_nisco", "richmat_mlily_supreme", "bedtech_classic") and protocol_variant == "sleep":
        return replace(traits, persistent_connection=True)
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
            connection_scoped_state=protocol_variant in _KEESON_SCOPED_VARIANTS or protocol_variant == KEESON_VARIANT_COMFORTFURNITURE,
            no_angle_feedback=traits.no_angle_feedback or protocol_variant == KEESON_VARIANT_COMFORTFURNITURE,
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


def default_connection_mode(bed_type: str | None, protocol_variant: str | None = None) -> str:
    """Return the connection mode an entry runs when it stores none."""
    if not bed_type:
        return CONNECTION_MODE_IDLE
    return bed_traits(bed_type, protocol_variant).connection_mode


def connection_mode_is_fixed(bed_type: str | None, protocol_variant: str | None = None) -> bool:
    """Return True when the bed holds its link whatever the connection mode says."""
    return bed_traits(bed_type, protocol_variant).persistent_connection


def reads_positions(data: Mapping[str, object]) -> bool:
    """Return whether an entry (or paired side) reads the bed's position.

    The saved choice wins; without one, a bed reads its position exactly when
    its route reports one. Flows store the choice only when it differs.
    """
    stored = data.get(CONF_DISABLE_ANGLE_SENSING)
    if isinstance(stored, bool):
        return not stored
    bed_type = data.get(CONF_BED_TYPE)
    variant = data.get(CONF_PROTOCOL_VARIANT)
    return bed_type_has_position_feedback(
        bed_type if isinstance(bed_type, str) else None,
        variant if isinstance(variant, str) else None,
    )


def store_read_positions(data: dict[str, object], read: bool | None = None) -> None:
    """Save ``read`` (or keep the saved choice) only where it differs from the route.

    Changes ``data`` in place, so a bed whose route reports no position, or
    one reading as its route does, stores nothing.
    """
    if read is None:
        read = reads_positions(data)
    data.pop(CONF_DISABLE_ANGLE_SENSING, None)
    if read != reads_positions(data):
        data[CONF_DISABLE_ANGLE_SENSING] = not read


# Bed types that never read "Has massage": their controllers have no massage
# commands, or turn massage on themselves. tests/test_controller_contract.py
# keeps this in step with the controllers.
MASSAGE_SETTING_UNUSED_BED_TYPES: Final = frozenset(
    {
     BED_TYPE_AMBIENT, BED_TYPE_ATLAS_LIFT, BED_TYPE_TOPCARE, BED_TYPE_COMFORT_BED,
     "adjustable_bed", "adjustable_lumbar", "adjustamattress", "bailey_bed_control",
     BED_TYPE_ERGOBED, BED_TYPE_MOODBASE, "l2motion", "bedgear", "bedjet_powerlayer", "bedsense", "bf", "casper_base", "casper_remote",
     "casper_sleep_mm", "casper_sleep_sxb", "cherish", "comfort_enhancement3",
     "comfortbase", "coolbase", "customatic_clarity", "customatic_jeromes", BED_TYPE_CUSTOMATIC_DEMO,
     "customatic_remedy", "customatic_zseries", "diagnostic", "doublesleep", "ergo_slim",
     "enso2", "ergomotion_4", "ergomotion_app", "eshine", "fsm_relax", "galaxy",
     "glideaway_motion", "gmmotor", "gmmotor_sleep_mm", "gmmotor_sleep_sxb", "goodvibe",
     "hjbed", "hush_base", "hush_remote", "hush_sleep_mm", "hush_sleep_sxb", "jalon",
     "leggett_lp_legacy", "logicdata_air_pump", "luuna", "malouf_app", "mlily",
     "motion_bed", "motomotion", "motosleep", "octo", "okin_motionbed", "okin_rf_eco_bt",
     "sinca_comfort", "omazz_adjusto_iii", "personal_comfort", "instant_comfort", "paramount", "qplus_app", "remacro", "resident", "reverie",
     "reverie_nightstand", "richmat_americanstar", "myside", "richmat_app", "richmat_app_sleep",
     "richmat_best_mattress", "richmat_blvd_home", "richmat_classic_apps",
     "richmat_harmony", "richmat_idealbed", "richmat_revive", "richmat_sleep_receiver",
     "richmat_tx", "rize_home", "rize_remedy_ii", "row_control", "ruf_betten",
     "restful", "serenity", "serta_mp_remote", "simmons", "sleep_number", "sleepstar",
     "sleeptracker", "sleepys_box15", "sleepys_box24", "smart_comfort_synargy",
     "awmotion", "dreamsense", "smart_comfort_synergy", "solace", "saatva", "sonicsleep", "star_elevate", "starcode_abm5_4",
     "starcode_m1x12", "starcode_m5x5", "svane", "symphony", "symphony_sleep",
     "tempur_au", "tempur_curve", "timotion_ahf", "tranquil", "vmatbasic",
     "wsilver_products", "yamada", "ormatek", "powersbedding",
    }
)


def asks_massage(bed_type: str | None) -> bool:
    """Return True when the "Has massage" setting changes this bed's controls."""
    return bed_type not in MASSAGE_SETTING_UNUSED_BED_TYPES


def supports_passive_position_reconciliation(bed_type: str | None) -> bool:
    """Return True if the bed type supports passive position reconciliation."""
    return bed_traits(bed_type).passive_position_reconciliation


def passive_position_reconciliation_default_enabled(bed_type: str | None) -> bool:
    """Return whether passive position reconciliation should default to enabled."""
    return supports_passive_position_reconciliation(bed_type)
