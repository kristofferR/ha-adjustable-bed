"""Remacro (SynData) frames, counters and per-model layouts.

Every value here comes from the accepted cluster-002 / row 050 artifacts:
``com.cheers.slumber`` 1.0 (2), ``com.cheers.brick`` 1.0 (3) and
``com.cheers.jewmes`` 1.202112141512 (20). See
``docs/apk-analysis/dispositions/row050-remacro.md``. Hardware is unverified.

The apps select a model only by the lowest manufacturer-specific-data company
ID in the advertisement; names, payload bytes and RSSI are never consulted.
Which app a bed belongs to cannot be told from the air, so the app profile is
an explicit setting.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from ..const import CONF_REMACRO_LED_LEVEL, CONF_REMACRO_MODEL

APP_SLUMBERLAND: Final = "slumberland"
APP_THE_BRICK: Final = "the_brick"
APP_JEROMES: Final = "jeromes"
RemacroApp = Literal["slumberland", "the_brick", "jeromes"]

PID_CONTROL: Final = 0x01

FLAT: Final = 0x0111  # The home icon sends the combined-down code once.
MOTOR_STOP: Final = 0x0001
LIGHT_OFF: Final = 0x0500
LIGHT_RGBV: Final = 0x0501
LIGHT_RGBV_SAVE: Final = 0x050F
# Settings > LED light sends white with the slider value in the low byte.
LED_WHITE: Final = 0xFFFFFF00
LED_PREVIEW_DELAY_S: Final = 0.150
LED_SAVE_DELAY_S: Final = 0.500
LED_DEFAULT_BRIGHTNESS: Final = 255  # Preference default before any commit.

RELEASE_DELAY_S: Final = 0.120
STREAM_INTERVAL_S: Final = 0.100


def build_frame(serial: int, pid: int, code: int, parameter: int = 0) -> bytes:
    """Return ``[S, PID, LE16 code, LE32 parameter]`` with Java bit patterns."""
    return (
        bytes((serial & 0xFF, pid & 0xFF))
        + (code & 0xFFFF).to_bytes(2, "little")
        + (parameter & 0xFFFFFFFF).to_bytes(4, "little")
    )


class SynDataSerial:
    """The apps' shared ``CommandUtils.i`` counter (starts at 1, never reset).

    ``tap`` is ``sendCode``: capture then increment. ``hold`` is
    ``sendCodeLong``: Slumberland and The Brick always increment first, while
    Jerome's increments only when the code differs from the cached one.
    """

    def __init__(self, *, cache_hold_serial: bool) -> None:
        self._i = 1
        self._cache = 0
        self._cache_hold_serial = cache_hold_serial

    def tap(self, code: int, parameter: int = 0) -> bytes:
        frame = build_frame(self._i, PID_CONTROL, code, parameter)
        self._i += 1
        return frame

    def hold(self, code: int, parameter: int = 0) -> bytes:
        if not self._cache_hold_serial or self._cache != code:
            self._i += 1
        self._cache = code
        return build_frame(self._i, PID_CONTROL, code, parameter)


@dataclass(slots=True)
class RemacroSession:
    """App state for one bed for the life of its config entry runtime.

    ``serial`` matches the app: ``CommandUtils.i`` and its cache are static. The
    rest are screen fields in the app (side toggle, highlighted preset, massage
    and wave counters, LED slider), which reset when the screen reopens. Home
    Assistant has no screen lifecycle: it drops and rebuilds the controller after
    every command handoff or idle disconnect. Keeping them here is a deliberate
    deviation, so that a reconnect cannot restart the massage cycle, lose the
    preset re-press STOP, save a stale LED level or move the other side.
    """

    serial: SynDataSerial
    side: str = "left"
    active_preset: str | None = None
    head_level: int = 0
    foot_level: int = 0
    wave: int = 0
    # Seeded from the committed level when the session starts.
    led_brightness: int | None = None


def drop_sessions(cache: dict[tuple[str, str, int], RemacroSession], address: str) -> None:
    """Forget every session for a bed when its entry runtime ends."""
    for key in [key for key in cache if key[0] == address.upper()]:
        del cache[key]


def session_for(
    cache: dict[tuple[str, str, int], RemacroSession], address: str, app: str, model_id: int
) -> RemacroSession:
    """Return the session for one bed, app and model; a change starts fresh."""
    key = (address.upper(), app, model_id)
    session = cache.get(key)
    if session is None:
        session = RemacroSession(SynDataSerial(cache_hold_serial=app == APP_JEROMES))
        cache[key] = session
    return session


@dataclass(frozen=True, slots=True)
class Axis:
    """Press codes and the STOP sent on release."""

    up: int
    down: int
    stop: int


@dataclass(frozen=True, slots=True)
class MassageCodes:
    """One head/foot/wave button set; levels are indexed 1..3."""

    head: tuple[int, int, int]
    head_wave: tuple[int, int, int]
    head_off: int
    foot: tuple[int, int, int]
    foot_wave: tuple[int, int, int]
    foot_off: int
    wave: tuple[int, int]
    wave_off: int


@dataclass(frozen=True, slots=True)
class SideCodes:
    """Codes one screen sends for one side selection."""

    combined: Axis | None
    head: Axis | None
    lumbar: Axis | None
    foot: Axis | None
    memory_recall: tuple[int, ...] = ()
    memory_save: tuple[int, ...] = ()
    presets: Mapping[str, int] = field(default_factory=dict)
    massage: MassageCodes | None = None


@dataclass(frozen=True, slots=True)
class Screen:
    """One app control screen. ``right`` exists only on split screens."""

    name: str
    left: SideCodes
    right: SideCodes | None = None
    light_toggle: bool = False
    # OneActivity: individual releases send STOP three times 120 ms apart,
    # and (except in The Brick) the combined arrows stream while held.
    one_activity_timing: bool = False

    @property
    def split(self) -> bool:
        return self.right is not None

    @property
    def has_global_stop(self) -> bool:
        """Whether this screen ever sends ``MOTOR_STOP`` (0x0001)."""
        combined = self.left.combined
        return bool(self.left.presets) or (combined is not None and combined.stop == MOTOR_STOP)


COMBINED: Final = Axis(0x0110, 0x0111, MOTOR_STOP)
HEAD: Final = Axis(0x0101, 0x0102, 0x0100)
FOOT: Final = Axis(0x0105, 0x0106, 0x0104)
LUMBAR: Final = Axis(0x0109, 0x010A, 0x0108)

SPLIT_FOOT: Final = Axis(0x640D, 0x640E, 0x640C)
SPLIT_LEFT_COMBINED: Final = Axis(0x6444, 0x6445, 0x6443)
SPLIT_LEFT_HEAD: Final = Axis(0x6401, 0x6402, 0x6400)
SPLIT_LEFT_LUMBAR: Final = Axis(0x6407, 0x6408, 0x6406)
SPLIT_RIGHT_COMBINED: Final = Axis(0x6456, 0x6457, 0x6455)
SPLIT_RIGHT_HEAD: Final = Axis(0x6404, 0x6405, 0x6403)
SPLIT_RIGHT_LUMBAR: Final = Axis(0x640A, 0x640B, 0x6409)

MEMORY_RECALL: Final = (0x0311, 0x0313)
MEMORY_SAVE: Final = (0x0310, 0x0312)
PRESETS: Final = {"anti_snore": 0x0301, "tv": 0x0302, "zero_g": 0x0303}

MASSAGE: Final = MassageCodes(
    head=(0x0201, 0x0202, 0x0203),
    head_wave=(0x0220, 0x0221, 0x0222),
    head_off=0x0123,
    foot=(0x0204, 0x0205, 0x0206),
    foot_wave=(0x0228, 0x0229, 0x022A),
    foot_off=0x0124,
    wave=(0x0230, 0x0231),
    wave_off=0x0200,
)
# NineActivity left differs from the others only in its wave-off code.
NINE_LEFT_MASSAGE: Final = MassageCodes(
    head=MASSAGE.head,
    head_wave=MASSAGE.head_wave,
    head_off=MASSAGE.head_off,
    foot=MASSAGE.foot,
    foot_wave=MASSAGE.foot_wave,
    foot_off=MASSAGE.foot_off,
    wave=MASSAGE.wave,
    wave_off=0x0233,
)
# The right wave head level 2 really is 0x2401 in all three apps.
NINE_RIGHT_MASSAGE: Final = MassageCodes(
    head=(0x0207, 0x0208, 0x0209),
    head_wave=(0x0240, 0x2401, 0x0242),
    head_off=0x0133,
    foot=(0x020A, 0x020B, 0x020C),
    foot_wave=(0x0248, 0x0249, 0x024A),
    foot_off=0x0134,
    wave=(0x0250, 0x0251),
    wave_off=0x0253,
)

_TWO = SideCodes(COMBINED, HEAD, None, FOOT)
_THREE_MOTOR = SideCodes(COMBINED, HEAD, LUMBAR, FOOT)

SCREENS: Final[Mapping[str, Screen]] = {
    screen.name: screen
    for screen in (
        Screen("OneActivity", _THREE_MOTOR, one_activity_timing=True),
        Screen("TwoActivity", _TWO),
        Screen("TwoActivity1", _TWO),
        Screen(
            "ThreeActivity",
            SideCodes(COMBINED, HEAD, None, FOOT, MEMORY_RECALL, MEMORY_SAVE, massage=MASSAGE),
            light_toggle=True,
        ),
        Screen(
            "FourActivity",
            SideCodes(COMBINED, HEAD, LUMBAR, FOOT, MEMORY_RECALL, MEMORY_SAVE, massage=MASSAGE),
            light_toggle=True,
        ),
        Screen(
            "FiveActivity",
            SideCodes(COMBINED, HEAD, LUMBAR, FOOT, MEMORY_RECALL, MEMORY_SAVE, PRESETS),
            light_toggle=True,
        ),
        Screen(
            "SixActivity",
            SideCodes(COMBINED, HEAD, None, FOOT, MEMORY_RECALL, MEMORY_SAVE, PRESETS),
            light_toggle=True,
        ),
        Screen(
            "EightActivity",
            SideCodes(
                SPLIT_LEFT_COMBINED,
                SPLIT_LEFT_HEAD,
                SPLIT_LEFT_LUMBAR,
                SPLIT_FOOT,
                (0x6530, 0x6531),
                (0x6540, 0x6541),
                {"anti_snore": 0x6511, "tv": 0x6512, "zero_g": 0x6513},
            ),
            SideCodes(
                SPLIT_RIGHT_COMBINED,
                SPLIT_RIGHT_HEAD,
                SPLIT_RIGHT_LUMBAR,
                SPLIT_FOOT,
                (0x6538, 0x6539),
                (0x6548, 0x6549),
                {"anti_snore": 0x6521, "tv": 0x6522, "zero_g": 0x6523},
            ),
            light_toggle=True,
        ),
        Screen(
            "NineActivity",
            SideCodes(
                SPLIT_LEFT_COMBINED,
                SPLIT_LEFT_HEAD,
                SPLIT_LEFT_LUMBAR,
                SPLIT_FOOT,
                (0x6530, 0x6531),
                (0x6540, 0x6541),
                massage=NINE_LEFT_MASSAGE,
            ),
            SideCodes(
                SPLIT_RIGHT_COMBINED,
                SPLIT_RIGHT_HEAD,
                SPLIT_RIGHT_LUMBAR,
                SPLIT_FOOT,
                (0x6538, 0x6539),
                (0x6548, 0x6549),
                massage=NINE_RIGHT_MASSAGE,
            ),
            light_toggle=True,
        ),
        Screen("TenActivity", SideCodes(COMBINED, None, None, None)),
        Screen(
            "ElevenActivity",
            SideCodes(COMBINED, HEAD, None, FOOT, (0x0311,), (0x0310,), PRESETS, MASSAGE),
            light_toggle=True,
        ),
        Screen(
            "TwelveActivity",
            SideCodes(None, HEAD, LUMBAR, FOOT, (0x0311,), (0x0310,), PRESETS, MASSAGE),
            light_toggle=True,
        ),
    )
}


@dataclass(frozen=True, slots=True)
class Model:
    """One ``BDUtils`` entry: company ID, shipped label and selected screen."""

    model_id: int
    name: str
    screen: Screen


MODELS: Final[Mapping[int, Model]] = {
    model_id: Model(model_id, name, SCREENS[screen])
    for model_id, name, screen in (
        (14, "BS200C/BS200P", "TenActivity"),
        (16, "BS200C/BS200P", "TenActivity"),
        (45, "CS-B200", "TwoActivity"),
        (46, "CS-B200A", "SixActivity"),
        (47, "CS-B200M", "ThreeActivity"),
        (48, "CS-B300", "OneActivity"),
        (49, "CS-B300A", "FiveActivity"),
        (50, "CS-B300M", "FourActivity"),
        (51, "CS-B500YA", "EightActivity"),
        (52, "CS-B500YM", "NineActivity"),
        (53, "BA210", "TwoActivity1"),
        (54, "CS-B300M(ASI)", "TwelveActivity"),
        (55, "CS-B200M(ASI)", "ElevenActivity"),
    )
}

APP_MODEL_IDS: Final[Mapping[str, frozenset[int]]] = {
    APP_SLUMBERLAND: frozenset(MODELS),
    APP_THE_BRICK: frozenset(MODELS),
    APP_JEROMES: frozenset(range(45, 54)),
}
# Models whose Settings page shows the LED brightness entry. Jerome's hides it
# for every model, which also removes its only in-app route to that page.
APP_LED_SETTINGS_MODEL_IDS: Final[Mapping[str, frozenset[int]]] = {
    APP_SLUMBERLAND: frozenset({46, 49, 50, 51, 52, 53, 54, 55}),
    APP_THE_BRICK: frozenset({46, 49, 50, 51, 52, 53, 54, 55}),
    APP_JEROMES: frozenset(),
}

APP_LABELS: Final[Mapping[str, str]] = {
    APP_SLUMBERLAND: "Slumberland",
    APP_THE_BRICK: "The Brick",
    APP_JEROMES: "Jerome's",
}


def app_for_variant(protocol_variant: str | None) -> RemacroApp:
    """Map the stored protocol variant to an app; ``auto`` keeps Slumberland."""
    if protocol_variant == APP_THE_BRICK:
        return APP_THE_BRICK
    if protocol_variant == APP_JEROMES:
        return APP_JEROMES
    return APP_SLUMBERLAND


def advertised_model_id(manufacturer_data: Mapping[int, bytes] | None) -> int | None:
    """Return the app's selector: the lowest company ID, mapped or not."""
    return min(manufacturer_data) if manufacturer_data else None


ModelProblem = Literal["unknown", "unmapped", "not_in_app"]


def model_problem(
    app: RemacroApp,
    manufacturer_data: Mapping[int, bytes] | None,
    stored_model_id: object,
) -> tuple[ModelProblem | None, int | None]:
    """Classify the selector like the app, falling back to the stored value.

    ``unknown``: nothing seen yet. ``unmapped``: no app lists this company ID.
    ``not_in_app``: another of the apps lists it, but not the selected one.
    """
    model_id = advertised_model_id(manufacturer_data)
    if (
        model_id is None
        and isinstance(stored_model_id, int)
        and not isinstance(stored_model_id, bool)
    ):
        model_id = stored_model_id
    if model_id is None:
        return "unknown", None
    if model_id not in MODELS:
        return "unmapped", model_id
    if model_id not in APP_MODEL_IDS[app]:
        return "not_in_app", model_id
    return None, model_id


def resolve_model(
    app: RemacroApp,
    manufacturer_data: Mapping[int, bytes] | None,
    stored_model_id: object,
) -> Model:
    """Select the model like the app, falling back to the stored selector."""
    problem, model_id = model_problem(app, manufacturer_data, stored_model_id)
    if problem == "unknown" or model_id is None:
        raise ValueError(
            "Remacro model is unknown: no manufacturer data has been seen for this bed yet"
        )
    if problem is not None:
        raise ValueError(
            f"The {APP_LABELS[app]} app does not list a bed advertising company ID {model_id}"
        )
    return MODELS[model_id]


def add_remacro_model(
    entry_data: Mapping[str, Any], manufacturer_data: Mapping[int, bytes] | None
) -> dict[str, Any]:
    """Return entry data remembering an advertised, app-listed model selector."""
    updated = dict(entry_data)
    model_id = advertised_model_id(manufacturer_data)
    if model_id in MODELS:
        updated[CONF_REMACRO_MODEL] = model_id
    return updated


def remacro_led_level(entry_data: Mapping[str, Any], model_id: int) -> int | None:
    """Return the level committed for this model, like the app's per-model "LV"."""
    levels = entry_data.get(CONF_REMACRO_LED_LEVEL)
    level = levels.get(str(model_id)) if isinstance(levels, Mapping) else None
    return level if isinstance(level, int) and not isinstance(level, bool) else None
