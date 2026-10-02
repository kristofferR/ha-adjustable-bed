"""Richmat MH app profiles: Revive Control, Best Mattress, Blvd Home, HARMONY, Idealbed.

Accepted as APK audit row055 (formal cluster-020). All five apps ship one BLE
library; their per-model catalogs, version-dependent pages and a few callbacks
differ. The app selects the model from the first four characters of the raw
Bluetooth name (``qrrm`` asks the user), or from its own model picker.

The app's version reply chooses the page set: ``VER0`` shows the legacy motor,
memory and massage pages built from the model's function list; ``VER1`` shows
the model's entity pages. Replies to the connection-time queries add the alarm,
light, aroma, snore and diagnostic pages. Home Assistant stores the result as a
capability snapshot and reloads when it changes. Hardware is unverified.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple

from homeassistant.util import dt as dt_util

from ..const import CONF_BLE_DEVICE_NAME, RICHMAT_MH_MODEL_CHOICES, VARIANT_AUTO
from ..detection import is_mac_like_name
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)
from .richmat_mh_protocol import (
    ALARM_MASSAGE_CODES,
    ALARM_TASK_SLEEP_S,
    ANGLE_SEND_DELAY_S,
    AROMA_FUNCTIONS,
    AROMA_TASK_SLEEP_S,
    BTN_LED_OFF_CODE,
    BTN_LED_PALETTE,
    BTN_LED_WHITE,
    CALLBACK_FUNCTION_LOCK,
    CALLBACK_FUNCTION_SNORE,
    CALLBACK_LOCKED,
    CALLBACK_UNLOCKED,
    DETECTION_DEVICE_TYPES,
    DETECTION_STATUS,
    FALLBACK_SKIPPED_PREFIXES,
    GATT_MAPS,
    INIT_DELAY_S,
    INIT_TASK_SLEEP_S,
    INIT_VER0,
    INIT_VER1,
    MOTOR_MODE_BITS,
    MULTI_ALARM_SLEEP_S,
    MULTI_ALARM_SLOTS,
    RX_ALARM,
    RX_ALARM_DEL_SUCCESS,
    RX_ALARM_MULTI,
    RX_ALARM_SET_SUCCESS,
    RX_AROMA,
    RX_CALLBACK_PREFIX,
    RX_LED,
    RX_SNORE_PREFIX,
    SMART_SET_LOCK_CODE,
    STOP_DELAY_S,
    TX_ALARM_CANCEL,
    TX_MATTRESS,
    TX_SPEECH,
    TX_START_DETECTION,
    TX_STOP_DETECTION,
    TX_VERSION,
    WAIST_ALARM,
    WAIST_ALARM_REPEAT,
    WAIST_DURATION,
    WAIST_HEAT,
    WAIST_MODE,
    WAIST_MODES,
    WAIST_PRESSURE,
    WAIST_SIDES,
    AppGroup,
    Classifier,
    Event,
    alarm_action,
    alarm_delete_frames,
    alarm_frames,
    angle_frame,
    aroma_frame,
    clock_frames,
    control_frame,
    light_timer_frame,
    massage_intensity_frame,
    motor_mode_frame,
    parse_waist_init,
    parse_waist_piece,
    query_frame,
    rgb_frame,
    snore_frame,
    stop_frame,
    waist_alarm_frame,
    waist_frame,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

App = Literal["revive", "best_mattress", "blvd_home", "harmony", "idealbed"]
APP_GROUPS: Final[dict[str, AppGroup]] = {
    "revive": "revive",
    "blvd_home": "revive",
    "harmony": "revive",
    "best_mattress": "legacy",
    "idealbed": "legacy",
}
MODEL_VARIANT_PREFIX: Final = "model_"
SNAPSHOT_NAMESPACE: Final = "richmat_mh"
VER0: Final = "0000"
VER1: Final = "0001"
COOL_TOUCH: Final = "cool touch"  # Idealbed's scan dialog asks for the model.

# Alarm page choices: app opcode -> stable service option.
ALARM_OPTIONS: Final = {
    0x58: "tv",
    0x45: "zero_g",
    0x46: "anti_snore",
    0x59: "lounge",
    0x2E: "memory_1",
    0x2F: "memory_2",
    0x30: "memory_3",
    0xB2: "memory_4",
    0xF4: "memory_5",
    0xF0: "yoga",
    0xB0: "alarm_mode_1",
    0xB1: "alarm_mode_2",
    0x4C: "head_massage",
    0x4E: "foot_massage",
    0x5D: "head_foot_massage",
    0x34: "head_foot_massage_intensity",
    0x4D: "head_massage_intensity_down",
    0x9D: "heat",
    0x86: "sleep_aid",
}
ALARM_OPTION_CODES: Final = {name: code for code, name in ALARM_OPTIONS.items()}
# Snore intervention positions (SnoreFragAdapter) and the clear option.
SNORE_OFF: Final = "off"
SNORE_OPTIONS: Final = {0x45: "zero_g", 0x46: "anti_snore"}
ANGLE_KEYS: Final = {"back": "richmat_mh_back_angle", "foot": "richmat_mh_foot_angle",
                     "pillow": "richmat_mh_pillow_angle"}
LIGHT_TIMER_KEY: Final = "richmat_mh_light_timer"
LIGHT_TIMER_MINUTES_KEY: Final = "richmat_mh_light_timer_minutes"
INTENSITY_KEYS: Final = {"head": "richmat_mh_head_massage_intensity",
                         "foot": "richmat_mh_foot_massage_intensity"}
SNORE_KEY: Final = "richmat_mh_snore"
MOTOR_MODE_KEY: Final = "richmat_mh_motor_mode"
DETECTION_KEY: Final = "richmat_mh_detection"
ALARM_STATUS_KEY: Final = "richmat_mh_alarm"
MEMORY_ARRIVAL_KEY: Final = "richmat_mh_memory_arrival"
SMART_SET_LOCK_KEY: Final = "richmat_mh_smart_set_lock"
SMART_LIGHT_LOCK_KEY: Final = "richmat_mh_smart_light_lock"
WAIST_MODE_KEY: Final = "richmat_mh_waist_mode"
# Waist page selects per side and field, with their option lists.
WAIST_FIELDS: Final = {"heat": WAIST_HEAT, "pressure": WAIST_PRESSURE, "duration": WAIST_DURATION}
WAIST_ALARM_KEYS: Final = {side: f"richmat_mh_waist_{side}_alarm" for side in WAIST_SIDES}
_SENSOR_KEYS: Final = frozenset(
    {DETECTION_KEY, ALARM_STATUS_KEY, MEMORY_ARRIVAL_KEY, *WAIST_ALARM_KEYS.values()}
)
_BINARY_SENSOR_KEYS: Final = frozenset({SMART_SET_LOCK_KEY, SMART_LIGHT_LOCK_KEY})
CALLBACK_FUNCTION_LED: Final = "0a"  # EPack.LED function: the light-page lock switch


class Control(NamedTuple):
    """One effective app control from the generated catalog."""

    route: str  # L legacy page, C VER1 entity page, B dedicated button-light page
    kind: str  # up | down | recall | save | press
    area: str  # motor | motor_btn | memory | massage | btn_led
    group: str
    label: str
    code: int
    keep_ms: int


class Features(NamedTuple):
    """The model constructor's flags and entity ranges (catalog FEATURES row)."""

    led: bool
    btn_led: bool
    aroma: bool
    snore: bool
    music: bool
    sleep: bool
    sleep_type: str | None
    speech: bool
    smart_set_lock: bool
    smart_light_lock: bool
    new_alarm: bool
    alarm: tuple[int, ...]
    snore_list: tuple[int, ...]
    alarm_call: tuple[tuple[str | None, int], ...]
    angles: tuple[tuple[int, str, int, int, int], ...]
    intensity: tuple[tuple[str, str | None, int, int], ...]
    motor_modes: tuple[str, ...]
    call: bool


@dataclass(frozen=True, slots=True)
class Model:
    """A resolved app model: its full layout and constructor features."""

    app: str
    model_id: str
    controls: tuple[Control, ...]
    features: Features


def _catalog() -> Any:
    from .. import richmat_mh_catalog

    return richmat_mh_catalog


def load_model(app: str, model_id: str) -> Model | None:
    """Return a catalog model, or None when the app has no such live model."""
    catalog = _catalog()
    row = catalog.MODELS.get(app, {}).get(model_id)
    if row is None:
        return None
    layout, feature = row
    return Model(
        app,
        model_id,
        tuple(Control(*catalog.CONTROLS[i]) for i in catalog.LAYOUTS[layout]),
        Features(*catalog.FEATURES[feature]),
    )


def selectable_models(app: str) -> tuple[str, ...]:
    """Model identifiers the app's picker, setup wizard or manual route offers."""
    return tuple(model for model, _label in RICHMAT_MH_MODEL_CHOICES[app])


ModelProblem = Literal["no_name", "choose_model", "unknown_model"]


def resolve_model(
    app: str, protocol_variant: str | None, name: str | None
) -> tuple[str | None, ModelProblem | None]:
    """Apply the app's selection: an explicit picker model, else the name rule.

    The scanner accepts a name of at least four characters; its first four,
    lowercased, name the model class. ``qrrm`` is the app's "ask the user"
    sentinel (Idealbed also asks for names starting with ``Cool Touch``), and a
    prefix without a live model is reported as invalid.
    """
    if protocol_variant and protocol_variant.startswith(MODEL_VARIANT_PREFIX):
        model = protocol_variant[len(MODEL_VARIANT_PREFIX) :]
        if model in selectable_models(app) and load_model(app, model) is not None:
            return model, None
        return None, "unknown_model"
    if not name or len(name) < 4:
        return None, "no_name"
    if app == "idealbed" and len(name) >= 10 and name[:10].lower() == COOL_TOUCH:
        return None, "choose_model"
    prefix = name[:4].lower()
    if prefix == "qrrm":
        return None, "choose_model"
    if load_model(app, prefix) is None:
        return None, "unknown_model"
    return prefix, None


# Canonical app labels that map a recall code onto a standard capability.
_MEMORY_SLOTS: Final = {0x2E: 1, 0x2F: 2, 0x30: 3, 0xB2: 4, 0xF4: 5}
_GENERIC_MEMORY_LABELS: Final = {
    1: {"memory1", "m1", "memory"},
    2: {"memory2", "m2"},
    3: {"memory3", "m3"},
    4: {"memory4", "m4"},
    5: {"memory5", "m5"},
}
_PRESETS: Final[dict[int, tuple[str, frozenset[str]]]] = {
    0x45: ("zero_g", frozenset({"zero gravity", "zero gravity mode", "zg"})),
    0x46: ("anti_snore", frozenset({"anti-snore", "anti snore", "snore"})),
    0x58: ("tv", frozenset({"tv"})),
    0x59: ("lounge", frozenset({"lounge"})),
    0xF0: ("yoga", frozenset({"yoga", "yoga mode"})),
}
FLAT_CODE: Final = 0x31
LIGHT_TOGGLE_CODE: Final = 0x3C
# Motor-page icons carry no text; name them after their app command keys.
_BUTTON_GROUP_NAMES: Final = {
    "FLAT": "Flat",
    "UBL1": "Light",
    "UBL2": "Light off",
    "LOCK": "Lock",
    "SYNC": "Sync",
    "UBL": "Light",
}
# Motor groups: stable entity key, translation by group.
_AXES: Final = {
    "HEAD": ("head", "head"),
    "Back": ("head", "back"),
    "FOOT": ("feet", "feet"),
    "Foot": ("feet", "feet"),
    "PILLOW": ("pillow", "pillow"),
    "Pillow": ("pillow", "pillow"),
    "LUMBAR": ("lumbar", "lumbar"),
    "Lumbar": ("lumbar", "lumbar"),
    "HEAD_FOOT_BOTH": ("head_feet", "head_feet"),
    "Back Foot Both": ("head_feet", "head_feet"),
    "MOTOR5": ("motor_5", "richmat_mh_motor_5"),
    "MOTOR6": ("motor_6", "richmat_mh_motor_6"),
    "PILLOW_LUMBAR_BOTH": ("pillow_lumbar", "richmat_mh_pillow_lumbar"),
    "PILLOW_LUMBAR_BOTH_TILT": ("tilt", "tilt"),
}
# Shown labels that rename an axis (e.g. a pillow tab titled "Lumbar").
_AXIS_LABELS: Final = {
    "back": "back",
    "head": "head",
    "foot": "feet",
    "pillow": "pillow",
    "lumbar": "lumbar",
    "lumbar2": "richmat_mh_lumbar_2",
    "back foot both": "head_feet",
}


def _clean_label(label: str) -> str:
    return " ".join(label.replace("\\n", " ").replace("\n", " ").split())


@dataclass(frozen=True, slots=True)
class Axis:
    key: str
    translation_key: str
    up: Control
    down: Control


@dataclass(frozen=True, slots=True)
class Tap:
    """A button: one app control sent as a tap (frame, then STOP 120 ms later)."""

    key: str
    name: str
    code: int
    translation_key: str


LightPage = Literal["led", "btn_led"]


class RichmatMhController(BedController):
    """Faithful Richmat MH app controls for one selected model."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str,
        protocol_variant: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        if app not in APP_GROUPS:
            raise ValueError(f"Unknown Richmat MH app: {app}")
        self._app = app
        data = getattr(getattr(coordinator, "entry", None), "data", None)
        data = data if isinstance(data, Mapping) else {}
        stored_name = data.get(CONF_BLE_DEVICE_NAME)
        name = device_name if not is_mac_like_name(device_name) else None
        if name is None and isinstance(stored_name, str) and not is_mac_like_name(stored_name):
            name = stored_name
        model_id, problem = resolve_model(app, protocol_variant or VARIANT_AUTO, name)
        self._model_problem: ModelProblem | None = problem
        self._model = load_model(app, model_id) if model_id else None
        snapshot = (data.get("capabilities") or {}).get(SNAPSHOT_NAMESPACE)
        snapshot = snapshot if isinstance(snapshot, Mapping) and snapshot.get("model") == model_id else {}
        self._stored_snapshot: dict[str, Any] = dict(snapshot)
        self._version: str = str(snapshot.get("version", VER0))
        self._dev: dict[str, bool] = {k: bool(v) for k, v in (snapshot.get("dev") or {}).items()}
        self._call_page: bool = bool(snapshot.get("call_page", False))
        self._detection: bool = bool(snapshot.get("detection", False))
        self._waist: bool = bool(snapshot.get("waist", False))
        self._classifier = Classifier(APP_GROUPS[app])
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_chars: list[BleakGATTCharacteristic] = []
        self._init_task: asyncio.Task[None] | None = None
        self._init_complete = asyncio.Event()
        self._motor_mode: str | None = None
        # Slider progress the app keeps between writes; RangeEntity starts at 0.
        self._intensity: dict[str, int] = {"head": 0, "foot": 0}
        self._detection_results: dict[str, str] = {}

    # ------------------------------------------------------------------ profile

    @property
    def app(self) -> str:
        return self._app

    @property
    def model(self) -> Model | None:
        return self._model

    @property
    def version(self) -> str:
        return self._version

    @property
    def route(self) -> str:
        """``C`` when the app shows the VER1 entity pages, else ``L``."""
        if self._version != VER1:
            return "L"
        # Best Mattress and Idealbed rebuild pages from the version reply itself;
        # the other apps do it on the first initialization reply.
        return "C" if APP_GROUPS[self._app] == "legacy" or self._call_page else "L"

    def _controls(self) -> tuple[Control, ...]:
        if self._model is None:
            return ()
        route = self.route
        return tuple(c for c in self._model.controls if c.route == route)

    @property
    def control_characteristic_uuid(self) -> str:
        if self._write_char is not None:
            return self._write_char.uuid
        return GATT_MAPS[1][1]

    @property
    def requires_notification_channel(self) -> bool:
        # Connection setup, the version reply and every page gate need replies.
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        # The app's mode byte selects its own device groups, not bed sides.
        return False

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "richmat_mh_app": self._app,
            "richmat_mh_model": self._model.model_id if self._model else None,
            "richmat_mh_model_problem": self._model_problem,
            "richmat_mh_version": self._version,
            "richmat_mh_route": self.route,
            "richmat_mh_device_flags": dict(self._dev),
            "richmat_mh_detection": self._detection,
            "richmat_mh_waist": self._waist,
            "richmat_mh_write_uuid": self._write_char.uuid if self._write_char else None,
        }

    def capability_snapshot(self) -> dict[str, Any] | None:
        if self._model is None:
            return None
        return {
            "model": self._model.model_id,
            "version": self._version,
            "call_page": self._call_page,
            "dev": dict(sorted(self._dev.items())),
            "detection": self._detection,
            "waist": self._waist,
        }

    # -------------------------------------------------------------------- pages

    @property
    def _features(self) -> Features | None:
        return self._model.features if self._model is not None else None

    def _alarm_page(self) -> bool:
        """``ALARM`` (legacy) or ``ALARM_CALL`` (VER1), both gated on the alarm reply."""
        f = self._features
        if f is None or not self._dev.get("alarm", False):
            return False
        return bool(f.alarm) if self.route == "L" else bool(f.alarm_call)

    def _multi_alarm(self) -> bool:
        """The VER1 alarm page shows three fixed slots for ``isNewAlarm`` models."""
        f = self._features
        return self.route == "C" and f is not None and f.new_alarm and self._alarm_page()

    def _light_page(self) -> LightPage | None:
        f = self._features
        if f is None:
            return None
        if self.route == "C":
            # VER1 shows the LED page for any model whose bed answered the query.
            return "led" if self._dev.get("led", False) else None
        if self._app == "harmony" and not self._dev.get("led", False):
            # Only Revive/Blvd Home's flavor branch and the Best Mattress and
            # Idealbed handler add the page from the constructor flag alone.
            return None
        if f.led:
            return "led"
        return "btn_led" if f.btn_led else None

    def _aroma_page(self) -> bool:
        f = self._features
        return self.route == "L" and f is not None and f.aroma and self._dev.get("aroma", False)

    def _snore_options(self) -> tuple[str, ...]:
        f = self._features
        if self.route != "L" or f is None or not f.snore:
            return ()
        if self._app not in ("revive", "blvd_home") and not self._dev.get("snore", False):
            return ()
        options = tuple(SNORE_OPTIONS[c] for c in f.snore_list if c in SNORE_OPTIONS)
        return (SNORE_OFF, *options) if options else ()

    def _detection_page(self) -> bool:
        return self.route == "L" and self._detection

    def _smart_set_lock(self) -> bool:
        f = self._features
        return self.route == "L" and f is not None and f.smart_set_lock

    def _angles(self) -> tuple[tuple[int, str, int, int, int], ...]:
        f = self._features
        return f.angles if f is not None and self.route == "C" else ()

    def _intensities(self) -> tuple[tuple[str, str | None, int, int], ...]:
        f = self._features
        return f.intensity if f is not None and self.route == "C" else ()

    # ---------------------------------------------------------------- catalog

    def _axes(self) -> tuple[Axis, ...]:
        pairs: dict[str, dict[str, Control]] = {}
        for c in self._controls():
            if c.area == "motor":
                pairs.setdefault(c.group, {})[c.kind] = c
        axes = []
        for group, roles in pairs.items():
            key, translation = _AXES[group]
            translation = _AXIS_LABELS.get(roles["up"].label.lower(), translation)
            axes.append(Axis(key, translation, roles["up"], roles["down"]))
        return tuple(axes)

    def _memory_groups(self) -> list[list[Control]]:
        groups: dict[str, list[Control]] = {}
        for c in self._controls():
            if c.area == "memory":
                groups.setdefault(c.group, []).append(c)
        return list(groups.values())

    def _memory_slots(self) -> dict[int, tuple[Control, Control | None]]:
        """Contiguous memory slots from recall codes, with their save buttons."""
        recall: dict[int, Control] = {}
        saves: dict[int, Control] = {}
        for members in self._memory_groups():
            first = members[0]
            slot = _MEMORY_SLOTS.get(first.code)
            if first.kind != "recall" or slot is None or slot in recall:
                continue
            recall[slot] = first
            for member in members[1:]:
                if member.kind == "save":
                    saves[slot] = member
        slots: dict[int, tuple[Control, Control | None]] = {}
        for slot in range(1, 6):
            if slot not in recall:
                break
            slots[slot] = (recall[slot], saves.get(slot))
        return slots

    def _presets(self) -> dict[str, tuple[Control, Control | None]]:
        """Standard preset buttons where the app shows the canonical label."""
        presets: dict[str, tuple[Control, Control | None]] = {}
        for members in self._memory_groups():
            first = members[0]
            spec = _PRESETS.get(first.code)
            if first.kind != "recall" or spec is None:
                continue
            name, labels = spec
            if _clean_label(first.label).lower() not in labels or name in presets:
                continue
            save = next((m for m in members[1:] if m.kind == "save"), None)
            presets[name] = (first, save)
        return presets

    def _flat(self) -> Control | None:
        return next(
            (c for c in self._controls() if c.area == "motor_btn" and c.code == FLAT_CODE), None
        )

    def _light_toggle(self) -> Control | None:
        return next(
            (c for c in self._controls() if c.area == "motor_btn" and c.code == LIGHT_TOGGLE_CODE),
            None,
        )

    def _taps(self) -> tuple[Tap, ...]:
        """Every remaining app control, one button per opcode."""
        used: set[int] = set()
        for recall, save in self._memory_slots().values():
            used.add(recall.code)
            if save is not None:
                used.add(save.code)
        for recall, save in self._presets().values():
            used.add(recall.code)
            if save is not None:
                used.add(save.code)
        if (flat := self._flat()) is not None:
            used.add(flat.code)
        if (light := self._light_toggle()) is not None:
            used.add(light.code)
        controls = self._controls()
        taps: list[Tap] = []
        group_labels: dict[str, str] = {}
        for c in controls:
            if c.area == "memory" and c.kind == "recall":
                group_labels[c.group] = _clean_label(c.label)
        for c in controls:
            if c.area == "motor" or c.code in used:
                continue
            used.add(c.code)
            key = f"richmat_mh_{c.code:02x}"
            if c.area == "memory":
                base = group_labels.get(c.group, _clean_label(c.label))
                if c.kind == "save":
                    taps.append(Tap(key, f"Save {base}", c.code, "richmat_mh_save"))
                elif c.group in ("FACTORY_RESET", "Factory Reset"):
                    taps.append(Tap(key, base, c.code, "richmat_mh_action"))
                else:
                    taps.append(Tap(key, base, c.code, "richmat_mh_preset"))
            elif c.area == "massage":
                taps.append(Tap(key, _clean_label(c.label), c.code, "richmat_mh_massage"))
            else:
                name = _BUTTON_GROUP_NAMES.get(c.group) or _clean_label(c.label)
                taps.append(Tap(key, name, c.code, "richmat_mh_action"))
        if self._light_page() == "btn_led" and BTN_LED_OFF_CODE not in used:
            # The button-light page's OFF button is identical in every app layout.
            taps.append(
                Tap(f"richmat_mh_{BTN_LED_OFF_CODE:02x}", "Button light off", BTN_LED_OFF_CODE,
                    "richmat_mh_action")
            )
        return tuple(taps)

    # ------------------------------------------------------------ capabilities

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Every release writes the same global STOP, so the axes share a resource.
        return tuple(
            MotorControlSpec(
                key=axis.key,
                translation_key=axis.translation_key,
                open_fn=lambda ctrl, k=axis.key: _invoke(ctrl, "move_axis", k, "up"),
                close_fn=lambda ctrl, k=axis.key: _invoke(ctrl, "move_axis", k, "down"),
                stop_fn=lambda ctrl: _invoke(ctrl, "stop_all"),
                scheduler_resource="*",
            )
            for axis in self._axes()
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset(key for key, _ in _AXES.values())

    def motor_pulse_settings(self) -> tuple[int, int]:
        """The pulse count bounds a hold; the app's own interval is per control."""
        return self._coordinator.motor_pulse_count, 100

    @property
    def supports_preset_flat(self) -> bool:
        return self._flat() is not None

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self._presets()

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self._presets()

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self._presets()

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in self._presets()

    @property
    def supports_preset_yoga(self) -> bool:
        return "yoga" in self._presets()

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self._memory_slots())

    @property
    def memory_slot_count(self) -> int:
        return len(self._memory_slots())

    @property
    def supports_memory_programming(self) -> bool:
        return any(save is not None for _, save in self._memory_slots().values())

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        slot = self._memory_slots().get(memory_num)
        return slot is not None and slot[1] is not None

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        names: list[str | None] = []
        for slot, (recall, _save) in sorted(self._memory_slots().items()):
            label = _clean_label(recall.label)
            names.append(None if label.lower() in _GENERIC_MEMORY_LABELS[slot] else label)
        return tuple(names)

    @property
    def supports_lights(self) -> bool:
        return self._light_toggle() is not None or self._light_page() is not None

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._light_toggle() is not None

    @property
    def supports_light_color_control(self) -> bool:
        # The LED and button-light pages both write the 10-byte colour frame.
        return self._light_page() is not None

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self._light_page() is not None else None

    @property
    def supports_stop_all(self) -> bool:
        return bool(self._axes())

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec] = []
        for _name, (recall, save) in self._presets().items():
            if save is not None:
                label = f"Save {_clean_label(recall.label)}"
                specs.append(
                    ControllerButtonSpec(
                        f"richmat_mh_{save.code:02x}",
                        label,
                        _tap_action(save.code),
                        icon="mdi:content-save",
                        translation_key="richmat_mh_save",
                        translation_placeholders={"action": label},
                    )
                )
        for tap in self._taps():
            specs.append(
                ControllerButtonSpec(
                    tap.key,
                    tap.name,
                    _tap_action(tap.code),
                    icon="mdi:content-save" if tap.translation_key == "richmat_mh_save" else "mdi:gesture-tap",
                    translation_key=tap.translation_key,
                    translation_placeholders={"action": tap.name},
                )
            )
        if self._smart_set_lock():
            specs.append(
                ControllerButtonSpec(
                    "richmat_mh_toggle_smart_set_lock",
                    "Toggle smart set lock",
                    lambda ctrl: _invoke(ctrl, "toggle_smart_set_lock"),
                    icon="mdi:lock-outline",
                    translation_key="richmat_mh_toggle_smart_set_lock",
                    cancel_movement=False,
                )
            )
        if self._detection_page():
            for key, method, icon in (
                ("richmat_mh_start_detection", "start_detection", "mdi:stethoscope"),
                ("richmat_mh_stop_detection", "stop_detection", "mdi:stop-circle-outline"),
            ):
                specs.append(
                    ControllerButtonSpec(
                        key,
                        key.removeprefix("richmat_mh_").replace("_", " ").capitalize(),
                        lambda ctrl, m=method: _invoke(ctrl, m),
                        icon=icon,
                        translation_key=key,
                        cancel_movement=False,
                    )
                )
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs: list[ControllerSelectSpec] = []
        if options := self.motor_mode_options:
            specs.append(
                ControllerSelectSpec(
                    key=MOTOR_MODE_KEY,
                    translation_key=MOTOR_MODE_KEY,
                    state_key=MOTOR_MODE_KEY,
                    options=options,
                    select_fn=lambda ctrl, option: _invoke(ctrl, "set_motor_mode", option),
                )
            )
        if options := self._snore_options():
            specs.append(
                ControllerSelectSpec(
                    key=SNORE_KEY,
                    translation_key=SNORE_KEY,
                    state_key=SNORE_KEY,
                    options=options,
                    select_fn=lambda ctrl, option: _invoke(ctrl, "set_snore", option),
                )
            )
        if self._waist:
            specs.append(
                ControllerSelectSpec(
                    key=WAIST_MODE_KEY,
                    translation_key=WAIST_MODE_KEY,
                    state_key=WAIST_MODE_KEY,
                    options=WAIST_MODES,
                    select_fn=lambda ctrl, option: _invoke(ctrl, "set_waist_mode", option),
                )
            )
            for side in WAIST_SIDES:
                for field, options in WAIST_FIELDS.items():
                    key = f"richmat_mh_waist_{side}_{field}"
                    specs.append(
                        ControllerSelectSpec(
                            key=key,
                            translation_key=key,
                            state_key=key,
                            options=tuple(options),
                            select_fn=lambda ctrl, option, s=side, f=field: _invoke(
                                ctrl, "set_waist_setting", s, f, option
                            ),
                        )
                    )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        page = self._light_page()
        if page == "btn_led" and self._app == "blvd_home":
            # Blvd Home's button-light slider counts minutes (0-15) and sends seconds.
            specs.append(
                ControllerNumberSpec(
                    LIGHT_TIMER_MINUTES_KEY, LIGHT_TIMER_MINUTES_KEY, LIGHT_TIMER_MINUTES_KEY,
                    0, 15, 1, lambda ctrl, v: _invoke(ctrl, "write_light_timer", int(v) * 60, int(v)),
                    native_unit_of_measurement="min",
                )
            )
        elif page is not None:
            specs.append(
                ControllerNumberSpec(
                    LIGHT_TIMER_KEY, LIGHT_TIMER_KEY, LIGHT_TIMER_KEY,
                    0, 300, 1, lambda ctrl, v: _invoke(ctrl, "write_light_timer", int(v), int(v)),
                    native_unit_of_measurement="s",
                )
            )
        for bits, name, low, high, _offset in self._angles():
            key = ANGLE_KEYS[name.lower()]
            specs.append(
                ControllerNumberSpec(
                    key, key, key, low, high, 1,
                    lambda ctrl, v, b=bits: _invoke(ctrl, "set_angle", b, int(v)),
                    native_unit_of_measurement="°",
                )
            )
        for zone, _name, low, high in self._intensities():
            key = INTENSITY_KEYS[zone]
            specs.append(
                ControllerNumberSpec(
                    key, key, key, low, high, 1,
                    lambda ctrl, v, z=zone: _invoke(ctrl, "write_massage_intensity", z, int(v)),
                )
            )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs: list[ControllerStateSensorSpec] = []
        if self._detection_page():
            specs.append(
                ControllerStateSensorSpec(
                    DETECTION_KEY, DETECTION_KEY, DETECTION_KEY, "mdi:stethoscope",
                    attribute_keys=(f"{DETECTION_KEY}_results",),
                )
            )
        if self._alarm_page():
            specs.append(
                ControllerStateSensorSpec(ALARM_STATUS_KEY, ALARM_STATUS_KEY, ALARM_STATUS_KEY, "mdi:alarm")
            )
        if self.route == "C" and self._memory_groups():
            specs.append(
                ControllerStateSensorSpec(
                    MEMORY_ARRIVAL_KEY, MEMORY_ARRIVAL_KEY, MEMORY_ARRIVAL_KEY, "mdi:map-marker-check"
                )
            )
        if self._waist:
            for key in WAIST_ALARM_KEYS.values():
                specs.append(
                    ControllerStateSensorSpec(
                        key, key, key, "mdi:alarm",
                        attribute_keys=(f"{key}_repeat", f"{key}_intensity"),
                    )
                )
        return tuple(specs)

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        return _SENSOR_KEYS - {spec.key for spec in self.controller_state_sensor_specs}

    def _smart_light_lock(self) -> bool:
        """The light page shows its lock switch; no listener sends from it in these apps."""
        f = self._features
        return f is not None and f.smart_light_lock and self._light_page() is not None

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        specs: list[ControllerStateBinarySensorSpec] = []
        for visible, key in ((self._smart_set_lock(), SMART_SET_LOCK_KEY),
                             (self._smart_light_lock(), SMART_LIGHT_LOCK_KEY)):
            if visible:
                specs.append(ControllerStateBinarySensorSpec(key, key, key, "mdi:lock"))
        return tuple(specs)

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        return _BINARY_SENSOR_KEYS - {s.key for s in self.controller_state_binary_sensor_specs}

    @property
    def motor_mode_options(self) -> tuple[str, ...]:
        """VER1 motor-mode buttons the model shows in the single-device group."""
        f = self._features
        if f is None or self.route != "C" or not f.motor_modes:
            return ()
        return tuple(m.lower() for m in f.motor_modes)

    # ------------------------------------------------------------ alarm/aroma

    @property
    def supports_richmat_mh_alarm(self) -> bool:
        return self._alarm_page()

    @property
    def richmat_mh_alarm_positions(self) -> tuple[str, ...]:
        """Options of the alarm page's single-choice list, in app order."""
        f = self._features
        if f is None or not self._alarm_page() or self._multi_alarm():
            return ()
        codes = f.alarm if self.route == "L" else tuple(code for _label, code in f.alarm_call)
        return tuple(dict.fromkeys(ALARM_OPTIONS[c] for c in codes if c in ALARM_OPTIONS))

    @property
    def richmat_mh_alarm_massages(self) -> tuple[str, ...]:
        """Options of the legacy alarm page's massage list (``AlarmMsgFragAdapter``)."""
        f = self._features
        if f is None or self.route != "L" or not self._alarm_page():
            return ()
        return tuple(ALARM_OPTIONS[c] for c in f.alarm if c in ALARM_MASSAGE_CODES)

    def validate_richmat_mh_alarm(
        self,
        *,
        enabled: bool,
        position: str | None,
        massage: Sequence[str],
        slot: int | None,
    ) -> None:
        self._alarm_request(enabled=enabled, position=position, massage=massage, slot=slot)

    def _alarm_request(
        self, *, enabled: bool, position: str | None, massage: Sequence[str], slot: int | None
    ) -> int | None:
        """Return the action opcode for a set request (None when cancelling)."""
        if not self._alarm_page():
            raise ValueError("The bed has not reported an alarm page for this model")
        if self._multi_alarm():
            if slot not in MULTI_ALARM_SLOTS:
                raise ValueError("This model's alarm page has slots 1, 2 and 3; choose a slot")
            if position is not None or massage:
                raise ValueError("Each alarm slot recalls its own memory; omit position and massage")
            return MULTI_ALARM_SLOTS[slot] if enabled else None
        if slot is not None:
            raise ValueError("This model has a single alarm; omit the slot")
        if not enabled:
            if position is not None or massage:
                raise ValueError("Cancelling the alarm takes no position or massage")
            return None
        positions, massages = self.richmat_mh_alarm_positions, self.richmat_mh_alarm_massages
        if position is not None and position not in positions:
            raise ValueError(f"Position '{position}' is not on this model's alarm page")
        unknown = [m for m in massage if m not in massages]
        if unknown or len(set(massage)) != len(massage):
            raise ValueError("Massage choices must be distinct options from this model's alarm page")
        if position is None and not massage:
            raise ValueError("Choose a position or a massage, as the app requires")
        # The app reads the selected massage rows in their page order.
        ordered = tuple(ALARM_OPTION_CODES[m] for m in massages if m in massage)
        action = alarm_action(ALARM_OPTION_CODES[position] if position else None, ordered)
        if action is None:
            raise ValueError("The app sends nothing for this position and massage combination")
        return action

    async def richmat_mh_alarm(
        self,
        *,
        enabled: bool,
        minutes: int,
        position: str | None,
        massage: Sequence[str],
        slot: int | None,
    ) -> None:
        action = self._alarm_request(enabled=enabled, position=position, massage=massage, slot=slot)
        self._classifier.rx_type = "ALARM"
        if self._multi_alarm():
            assert slot is not None
            frames = (
                alarm_frames(minutes, action, slot) if action is not None else alarm_delete_frames(slot)
            )
            await self._write_sequence(frames, MULTI_ALARM_SLEEP_S)
        elif action is None:
            await self._write_sequence(tuple(query_frame(t) for t in TX_ALARM_CANCEL), ALARM_TASK_SLEEP_S)
        else:
            await self._write_sequence(alarm_frames(minutes, action), ALARM_TASK_SLEEP_S)

    @property
    def supports_richmat_mh_aroma(self) -> bool:
        return self._aroma_page()

    async def richmat_mh_aroma(
        self, mode2_startup_minutes: int, mode3_startup_minutes: int, mode3_pause_hours: int
    ) -> None:
        if not self._aroma_page():
            raise ValueError("The bed has not reported an aroma page for this model")
        values = (mode2_startup_minutes, mode3_startup_minutes, mode3_pause_hours)
        for value, high in zip(values, (60, 60, 12), strict=True):
            if not 1 <= value <= high:
                raise ValueError("Aroma startup times are 1-60 minutes and the pause 1-12 hours")
        frames = tuple(aroma_frame(fn, value) for fn, value in zip(AROMA_FUNCTIONS, values, strict=True))
        await self._write_sequence(frames, AROMA_TASK_SLEEP_S)

    @property
    def supports_richmat_mh_waist_alarm(self) -> bool:
        return self._waist

    async def richmat_mh_waist_alarm(
        self,
        *,
        enabled: bool,
        waist_side: str,
        hour: int,
        minute: int,
        now_hour: int,
        now_minute: int,
        repeat: str,
        intensity: int,
    ) -> None:
        """WaistMattressAlarmDialog: save (time, repeat, intensity) or cancel one side."""
        if not self._waist:
            raise ValueError("The bed has not reported a waist mattress page")
        codes = WAIST_SIDES.get(waist_side)
        if codes is None or repeat not in WAIST_ALARM_REPEAT or not 1 <= intensity <= 3:
            raise ValueError("Choose a waist side, once or daily, and intensity 1-3")
        if enabled:
            frame = waist_alarm_frame(
                WAIST_ALARM_REPEAT[repeat], codes[4], intensity, hour, minute, now_hour, now_minute
            )
        else:
            frame = waist_frame(WAIST_ALARM, codes[3])
        await self.write_command(frame, cancel_event=asyncio.Event())

    async def _write_sequence(self, frames: Sequence[bytes], sleep_s: float) -> None:
        """The app's task list: each frame, then its fixed sleep before the next."""
        for index, frame in enumerate(frames):
            if index:
                await asyncio.sleep(sleep_s)
            await self.write_command(frame, cancel_event=asyncio.Event())

    # --------------------------------------------------------------- transport

    async def async_discover_capabilities(self) -> None:
        """Resolve the app's GATT roles; reject a name the app cannot resolve."""
        client = self.client
        if client is None:
            raise ConnectionError("Richmat MH bed is not connected")
        if self._model is None:
            raise ValueError(_problem_message(self._model_problem))
        services = list(client.services or ())
        by_uuid = {s.uuid.lower(): s for s in services}
        write = notify = None
        notifies: list[BleakGATTCharacteristic] = []
        for service_uuid, write_uuid, notify_uuid in GATT_MAPS:
            service = by_uuid.get(service_uuid)
            if service is None:
                continue
            chars = {c.uuid.lower(): c for c in service.characteristics}
            w, n = chars.get(write_uuid), chars.get(notify_uuid)
            if w is not None and {"write", "write-without-response"} & set(w.properties):
                write = w
            if n is not None and {"notify", "indicate"} & set(n.properties):
                notify = n
                notifies.append(n)
            break  # The app stops at the first known service, complete or not.
        if write is None or notify is None:
            # Fallback: the first service other than generic access/attribute;
            # the last writable characteristic wins, every notifier is subscribed.
            for service in services:
                if service.uuid.lower()[:8] in FALLBACK_SKIPPED_PREFIXES:
                    continue
                notifies = []
                write = notify = None
                for c in service.characteristics:
                    props = set(c.properties)
                    if {"write", "write-without-response"} & props:
                        write = c
                    elif {"notify", "indicate"} & props:
                        notify = c
                        notifies.append(c)
                break
        if write is None or notify is None:
            raise ValueError("The Richmat MH app needs a writable and a notifying characteristic")
        self._write_char = write
        self._notify_chars = notifies

    @property
    def _write_with_response(self) -> bool:
        # The app keeps the characteristic's own write type (Android defaults
        # to write-without-response only when that is the advertised property).
        props = set(self._write_char.properties) if self._write_char is not None else set()
        return "write-without-response" not in props

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._write_char is None:
            raise ConnectionError("Richmat MH write role is not resolved")
        await self._write_gatt_with_retry(
            self._write_char.uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
            wall_clock_pacing=True,
            characteristic=self._write_char,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client = self.client
        if client is None:
            return
        for char in self._notify_chars:
            async with self._ble_lock:
                await client.start_notify(char, self._handle_notification)
        self._start_session()

    async def stop_notify(self) -> None:
        self._notify_callback = None
        self._cancel_session()
        client = self.client
        if client is None or not client.is_connected:
            return
        for char in self._notify_chars:
            async with self._ble_lock:
                await client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._cancel_session()

    def _start_session(self) -> None:
        self._cancel_session()
        self._init_complete = asyncio.Event()
        self._init_task = asyncio.get_running_loop().create_task(self._run_session_setup())

    def _cancel_session(self) -> None:
        task, self._init_task = self._init_task, None
        if task is not None and not task.done():
            task.cancel()

    async def _run_session_setup(self) -> None:
        """``handleProtocol``: version query, then the version's init list.

        Flags are rebuilt for this session, so a reply that stops arriving
        removes its page again.
        """
        try:
            self._version = VER0
            self._call_page = False
            self._dev = {}
            self._detection = False
            self._waist = False
            await asyncio.sleep(INIT_DELAY_S)
            await self._write_query(TX_VERSION)
            await asyncio.sleep(INIT_DELAY_S)
            tasks = INIT_VER1 if self._version == VER1 else INIT_VER0
            self._classifier.rx_type = "INIT"
            clock_sent = False
            for hex_text in tasks:
                await self._write_query(hex_text)
                await asyncio.sleep(INIT_TASK_SLEEP_S)
                if not clock_sent and self.route == "C" and self._alarm_page():
                    # AlarmCallFrag sends the phone clock when its page is created,
                    # even if a later reply removes the page again.
                    clock_sent = True
                    await self._send_clock()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a failed query leaves the stored snapshot
            _LOGGER.debug("Richmat MH connection setup failed", exc_info=True)
            return
        self._init_complete.set()
        self._persist_snapshot()

    async def _send_clock(self) -> None:
        now = dt_util.now()
        for frame in clock_frames(now.hour, now.minute, now.second):
            await self.write_command(frame, cancel_event=asyncio.Event())

    async def _write_query(self, hex_text: str) -> None:
        await self.write_command(query_frame(hex_text), cancel_event=asyncio.Event())

    def _persist_snapshot(self) -> None:
        snapshot = self.capability_snapshot()
        if snapshot is None or snapshot == self._stored_snapshot:
            return
        self._stored_snapshot = dict(snapshot)
        remember = getattr(self._coordinator, "remember_richmat_mh_snapshot", None)
        if callable(remember):
            remember(snapshot)

    # ------------------------------------------------------------ notifications

    def _handle_notification(self, sender: Any, data: bytearray) -> None:
        uuid = getattr(sender, "uuid", None) or (self._notify_chars[0].uuid if self._notify_chars else "")
        self.forward_raw_notification(str(uuid), bytes(data))
        for event in self._classifier.feed(bytes(data)):
            self._apply(event)

    def _apply(self, event: Event) -> None:
        kind = event.kind
        if kind == "version":
            self._version = VER1
        elif kind == "init":
            self._apply_init(event.data)
            if event.data.startswith(RX_CALLBACK_PREFIX):
                self._apply_lock(event.data[6:8], event.data[4:6])
        elif kind == "detection_available":
            self._detection = True
        elif kind == "detection_started":
            self._detection_results = {}
            self.forward_controller_state_updates(
                {DETECTION_KEY: "running", f"{DETECTION_KEY}_results": {}}
            )
        elif kind == "detection_stopped":
            self.forward_controller_state_update(DETECTION_KEY, "stopped")
        elif kind == "detection_result":
            device_type, number, code = event.extra
            stem = DETECTION_DEVICE_TYPES.get(device_type)
            if stem is not None:
                self._detection_results[f"{stem}_{number}"] = DETECTION_STATUS.get(code, code)
                self.forward_controller_state_update(
                    f"{DETECTION_KEY}_results", dict(self._detection_results)
                )
        elif kind == "waist_init":
            self._waist = True
            self._apply_waist(parse_waist_init(event.data))
        elif kind == "waist":
            self._apply_waist(parse_waist_piece(event.data))
        elif kind == "motor_mode":
            self._apply_motor_mode(event.data)
        elif kind == "motor_angle":
            self._apply_angle(int(event.data, 2), event.extra[0])
        elif kind == "massage":
            # onChangeMassage: bits 6-8 are the foot slider, 9-11 the head slider.
            self._apply_intensity({"foot": int(event.data[6:9], 2), "head": int(event.data[9:12], 2)})
        elif kind == "memory_arrival":
            self._apply_memory_arrival(event.data)
        elif kind == "alarm":
            if event.data == RX_ALARM_SET_SUCCESS:
                self.forward_controller_state_update(ALARM_STATUS_KEY, "set")
            elif event.data == RX_ALARM_DEL_SUCCESS:
                self.forward_controller_state_update(ALARM_STATUS_KEY, "cancelled")
        elif kind == "snore":
            self._apply_snore(event.data)

    def _apply_init(self, rx: str) -> None:
        """``ControlFrag.onReceiverEvent`` capability flags."""
        multi = APP_GROUPS[self._app] == "revive"
        if self._version == VER1:
            # VER1 resets these five flags before every reply (snore is kept).
            for key in ("alarm", "led", "aroma", "mattress", "speech"):
                self._dev[key] = False
            self._call_page = True
        if rx == RX_ALARM or (multi and rx == RX_ALARM_MULTI):
            self._dev["alarm"] = True
        elif rx == RX_LED:
            self._dev["led"] = True
        elif rx == RX_AROMA:
            self._dev["aroma"] = True
        elif rx == TX_MATTRESS:
            self._dev["mattress"] = True
        elif rx == TX_SPEECH:
            self._dev["speech"] = True
        elif self._version != VER1 and rx.startswith(RX_SNORE_PREFIX):
            self._dev["snore"] = True

    def _apply_lock(self, function: str, value: str) -> None:
        """Lock switches follow ``6e 23 v 84`` (motor page) and ``6e 23 v 0a`` (light page)."""
        if function == CALLBACK_FUNCTION_LOCK and self._smart_set_lock():
            key = SMART_SET_LOCK_KEY
        elif function == CALLBACK_FUNCTION_LED and self._smart_light_lock():
            key = SMART_LIGHT_LOCK_KEY
        else:
            return
        if value == CALLBACK_LOCKED:
            self.forward_controller_state_update(key, True)
        elif value == CALLBACK_UNLOCKED:
            self.forward_controller_state_update(key, False)

    def _apply_snore(self, rx: str) -> None:
        """SnoreFrag: cancel confirmation and the ``6e 23 code 21`` callback."""
        if not self._snore_options():
            return
        if rx == RX_ALARM_DEL_SUCCESS:
            self.forward_controller_state_update(SNORE_KEY, SNORE_OFF)
        elif rx.startswith(RX_CALLBACK_PREFIX) and rx[6:8] == CALLBACK_FUNCTION_SNORE:
            code = int(rx[4:6], 16)
            if code == 0:
                self.forward_controller_state_update(SNORE_KEY, SNORE_OFF)
            elif SNORE_OPTIONS.get(code) in self._snore_options():
                self.forward_controller_state_update(SNORE_KEY, SNORE_OPTIONS[code])

    def _apply_motor_mode(self, bits: str) -> None:
        options = self.motor_mode_options
        if not options:
            return
        value = int(bits, 2)
        # onChangeMode: a LEFT/RIGHT list maps 01/10; Mode1..3 map 01/10/11.
        names = ("left", "right") if options[0] in ("left", "right") else ("mode1", "mode2", "mode3")
        index = value - 1
        if 0 <= index < len(names) and names[index] in options:
            self._motor_mode = names[index]
            self.forward_controller_state_update(MOTOR_MODE_KEY, self._motor_mode)

    def _apply_angle(self, bits: int, value: str) -> None:
        """``onChangeAngle``: clamp the reported angle into the slider's range."""
        for motor, name, low, high, _offset in self._angles():
            if motor == bits:
                try:
                    angle = int(value)
                except ValueError:
                    return
                self.forward_controller_state_update(ANGLE_KEYS[name.lower()], min(max(angle, low), high))
                return

    def _apply_intensity(self, values: Mapping[str, int]) -> None:
        updates: dict[str, Any] = {}
        for zone, _name, low, high in self._intensities():
            value = min(max(values[zone], low), high)
            self._intensity[zone] = value
            updates[INTENSITY_KEYS[zone]] = value
        if updates:
            self.forward_controller_state_updates(updates)

    def _apply_waist(self, values: Mapping[str, Any]) -> None:
        """The waist page's bean: mode, per-side settings and alarms."""
        updates: dict[str, Any] = {}
        for field, value in values.items():
            if field == "mode":
                if 0 <= value < len(WAIST_MODES):
                    updates[WAIST_MODE_KEY] = WAIST_MODES[value]
            elif field.endswith("_alarm"):
                key = WAIST_ALARM_KEYS[field.removesuffix("_alarm")]
                updates[key] = value[0] if value else "off"
                repeat = next((n for n, c in WAIST_ALARM_REPEAT.items() if value and c == value[1]), None)
                updates[f"{key}_repeat"] = repeat
                updates[f"{key}_intensity"] = int(value[2], 16) if value else None
            else:
                side, name = field.split("_", 1)
                # A value the dialog cannot select (e.g. pressure off) is unknown.
                option = next((o for o, v in WAIST_FIELDS[name].items() if v == value), None)
                updates[f"richmat_mh_waist_{side}_{name}"] = option
        if updates:
            self.forward_controller_state_updates(updates)

    def _apply_memory_arrival(self, code: str) -> None:
        """MemoryCallFrag announces "has reached the <name> position"."""
        if self.route != "C":
            return
        for members in self._memory_groups():
            recall = members[0]
            if recall.kind == "recall" and f"{recall.code:02x}" == code.lower():
                self.forward_controller_state_update(MEMORY_ARRIVAL_KEY, _clean_label(recall.label))
                return

    # --------------------------------------------------------------- controls

    async def _release(self) -> None:
        """STOP 120 ms after the release, attempted even when cancelled."""

        async def release() -> None:
            try:
                await asyncio.sleep(STOP_DELAY_S)
            finally:
                await self.write_command(stop_frame(), cancel_event=asyncio.Event())

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
                task.cancel()  # Skip the remaining delay; STOP is still sent.
            except Exception:  # noqa: BLE001 - re-raised below unless cancelled
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    async def tap(self, code: int) -> None:
        """An app tap: one frame, then STOP 120 ms later (ONCE and short KEEP)."""
        try:
            await self.write_command(control_frame(code))
        finally:
            await self._release()

    async def move_axis(self, key: str, direction: Literal["up", "down"]) -> None:
        """Hold an axis: KEEP repeats at the control's interval, then releases."""
        axis = next((a for a in self._axes() if a.key == key), None)
        if axis is None:
            raise NotImplementedError(f"The selected model has no '{key}' motor")
        control = axis.up if direction == "up" else axis.down
        count, _ = self.motor_pulse_settings()
        try:
            await self.write_command(
                control_frame(control.code), repeat_count=count, repeat_delay_ms=control.keep_ms
            )
        finally:
            await self._release()

    async def set_motor_mode(self, option: str) -> None:
        if option not in self.motor_mode_options:
            raise ValueError(f"Unsupported motor mode: {option}")
        name = {"left": "LEFT", "right": "RIGHT"}.get(option, option.capitalize())
        await self.write_command(motor_mode_frame(MOTOR_MODE_BITS[name]), cancel_event=asyncio.Event())
        self._motor_mode = option
        self.forward_controller_state_update(MOTOR_MODE_KEY, option)

    async def set_snore(self, option: str) -> None:
        """SnoreFragAdapter: the selected position's opcode, or 00 to clear."""
        if option not in self._snore_options():
            raise ValueError(f"Unsupported snore intervention option: {option}")
        code = 0 if option == SNORE_OFF else next(c for c, n in SNORE_OPTIONS.items() if n == option)
        self._classifier.rx_type = "SNORE"
        await self.write_command(snore_frame(code), cancel_event=asyncio.Event())
        self.forward_controller_state_update(SNORE_KEY, option)

    async def write_light_timer(self, seconds: int, shown: int) -> None:
        """LED/button-light timeout slider: one frame, no STOP."""
        if self._light_page() is None:
            raise ValueError("The bed has not reported a light page for this model")
        await self.write_command(light_timer_frame(seconds), cancel_event=asyncio.Event())
        key = LIGHT_TIMER_MINUTES_KEY if self._app == "blvd_home" and self._light_page() == "btn_led" else LIGHT_TIMER_KEY
        self.forward_controller_state_update(key, shown)

    @property
    def button_light_palette(self) -> tuple[tuple[int, int, int], ...]:
        """The button-light page's colour sectors (the LED page's hue bar is continuous)."""
        if APP_GROUPS[self._app] == "legacy":
            return BTN_LED_PALETTE
        return (*BTN_LED_PALETTE, BTN_LED_WHITE)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        page = self._light_page()
        if page is None:
            raise NotImplementedError("The bed has not reported a light page for this model")
        rgb = tuple(int(v) for v in rgb_color)
        if page == "btn_led" and rgb not in self.button_light_palette:
            colours = ", ".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in self.button_light_palette)
            raise ValueError(f"The button-light page offers only its colours: {colours}")
        await self.write_command(rgb_frame(*rgb), cancel_event=asyncio.Event())

    async def set_angle(self, bits: int, angle: int) -> None:
        """MotorCallFrag: 100 ms after the slider release, one absolute target."""
        spec = next((a for a in self._angles() if a[0] == bits), None)
        if spec is None or not spec[2] <= angle <= spec[3]:
            raise ValueError("Angle is outside the selected motor's range")
        await asyncio.sleep(ANGLE_SEND_DELAY_S)
        await self.write_command(angle_frame(bits, angle), cancel_event=asyncio.Event())
        self.forward_controller_state_update(ANGLE_KEYS[spec[1].lower()], angle)

    async def write_massage_intensity(self, zone: str, value: int) -> None:
        """MassageCallFrag sends both sliders' progress in one frame."""
        spec = next((i for i in self._intensities() if i[0] == zone), None)
        if spec is None or not spec[2] <= value <= spec[3]:
            raise ValueError("Massage intensity is outside the selected zone's range")
        values = {**self._intensity, zone: value}
        await self.write_command(
            massage_intensity_frame(values["head"], values["foot"]), cancel_event=asyncio.Event()
        )
        self._intensity = values
        self.forward_controller_state_update(INTENSITY_KEYS[zone], value)

    async def set_waist_mode(self, option: str) -> None:
        """WaistMattressModeActivity start (the side's mode) or stop (00)."""
        if not self._waist or option not in WAIST_MODES:
            raise ValueError(f"Unsupported waist mattress mode: {option}")
        await self.write_command(waist_frame(WAIST_MODE, WAIST_MODES.index(option)), cancel_event=asyncio.Event())
        self.forward_controller_state_update(WAIST_MODE_KEY, option)

    async def set_waist_setting(self, side: str, field: str, option: str) -> None:
        """Waist heat, pressure and duration dialogs for the selected side."""
        options = WAIST_FIELDS.get(field)
        if not self._waist or side not in WAIST_SIDES or options is None or option not in options:
            raise ValueError(f"Unsupported waist mattress {field}: {option}")
        command = WAIST_SIDES[side][("heat", "pressure", "duration").index(field)]
        await self.write_command(waist_frame(command, options[option]), cancel_event=asyncio.Event())
        self.forward_controller_state_update(f"richmat_mh_waist_{side}_{field}", option)

    async def toggle_smart_set_lock(self) -> None:
        """MotorFrag's smart-set-lock switch: ``6e 01 M 84`` once, no STOP."""
        if not self._smart_set_lock():
            raise NotImplementedError("The selected model has no smart set lock")
        await self.write_command(control_frame(SMART_SET_LOCK_CODE), cancel_event=asyncio.Event())

    async def start_detection(self) -> None:
        await self._detection_command(TX_START_DETECTION)

    async def stop_detection(self) -> None:
        await self._detection_command(TX_STOP_DETECTION)

    async def _detection_command(self, hex_text: str) -> None:
        if not self._detection_page():
            raise NotImplementedError("The bed has not reported a detection page")
        await self._write_query(hex_text)

    async def _move_group(self, keys: tuple[str, ...], direction: Literal["up", "down"]) -> None:
        key = next((k for k in keys if any(a.key == k for a in self._axes())), keys[0])
        await self.move_axis(key, direction)

    async def move_head_up(self) -> None:
        await self._move_group(("head",), "up")

    async def move_head_down(self) -> None:
        await self._move_group(("head",), "down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._move_group(("head",), "up")

    async def move_back_down(self) -> None:
        await self._move_group(("head",), "down")

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_group(("feet",), "up")

    async def move_legs_down(self) -> None:
        await self._move_group(("feet",), "down")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._move_group(("feet",), "up")

    async def move_feet_down(self) -> None:
        await self._move_group(("feet",), "down")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        await self.write_command(stop_frame(), cancel_event=asyncio.Event())

    async def preset_flat(self) -> None:
        flat = self._flat()
        if flat is None:
            raise NotImplementedError("The selected model has no Flat button")
        await self.tap(flat.code)

    async def _preset(self, name: str) -> None:
        preset = self._presets().get(name)
        if preset is None:
            raise NotImplementedError(f"The selected model has no {name} preset")
        await self.tap(preset[0].code)

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_lounge(self) -> None:
        await self._preset("lounge")

    async def preset_yoga(self) -> None:
        await self._preset("yoga")

    async def preset_memory(self, memory_num: int) -> None:
        slot = self._memory_slots().get(memory_num)
        if slot is None:
            raise NotImplementedError(f"The selected model has no memory {memory_num}")
        await self.tap(slot[0].code)

    async def program_memory(self, memory_num: int) -> None:
        slot = self._memory_slots().get(memory_num)
        if slot is None or slot[1] is None:
            raise NotImplementedError(f"The selected model cannot save memory {memory_num}")
        await self.tap(slot[1].code)

    async def lights_toggle(self) -> None:
        light = self._light_toggle()
        if light is None:
            raise NotImplementedError("The selected model has no light button")
        await self.tap(light.code)


def _problem_message(problem: ModelProblem | None) -> str:
    if problem == "choose_model":
        return (
            "The app resolves this Bluetooth name by asking for the model; choose the "
            "model in the protocol variant"
        )
    if problem == "no_name":
        return "The app selects the model from the Bluetooth name; choose the model explicitly"
    return "The app has no model for this Bluetooth name; choose the model explicitly"


def richmat_mh_target(controller: BedController | SideBoundController) -> RichmatMhController:
    """The Richmat MH controller behind an entity or service target."""
    target = controller._controller if isinstance(controller, SideBoundController) else controller
    if not isinstance(target, RichmatMhController):
        raise TypeError("This action requires a Richmat MH app profile")
    return target


def _invoke(controller: BedController | SideBoundController, method: str, *args: Any) -> Any:
    return getattr(richmat_mh_target(controller), method)(*args)


def _tap_action(code: int) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        await richmat_mh_target(controller).tap(code)

    return invoke
