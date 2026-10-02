"""Generate the Richmat MH app catalogs from the accepted row055 cluster inventories.

Usage::

    uv run --no-sync python tools/generate_richmat_mh_catalog.py [--check] [--phase4-dir DIR]

Reads the five frozen package inventories owned by the accepted cluster-020
reconciliation and the accepted Idealbed report's CmdKey/entity tables, then
writes the compact ``custom_components/adjustable_bed/richmat_mh_catalog.py``.
``--check`` verifies that the committed module matches the inputs. Every input
is pinned to the hash its accepted report or reconciliation records, so a
superseded extraction cannot be used.

The inputs are machine-local APK Protocol Audit reports (never committed). They
are read from ``DIR`` (``--phase4-dir``), else ``$ADJUSTABLE_BED_PHASE4_DIR``,
else ``disassembly/output/phase4-early`` in this checkout, else the same path in
the main checkout of a linked git worktree. Without them the script exits with
a message naming the directory it looked in.

Every per-model control comes from the package's own resolved command rows
(Revive: its per-model binding rows). Nothing is inferred across packages.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[1]
PHASE4_ENV = "ADJUSTABLE_BED_PHASE4_DIR"
PHASE4_RELATIVE = Path("disassembly/output/phase4-early")
RECONCILIATION_REPORT = Path(
    "cluster-020-reconciliation-2026-10-02-queue-e0bb6807-20261001-055-002/report"
)
# The accepted Idealbed report's CmdKey constant table (resolves setter expressions).
IDEALBED_REPORT = Path("com.richmat.idealbed-2.4.2-2026-10-02-queue-e0bb6807-20261001-055-003/report")
_phase4_override: list[Path] = []


class InputsMissing(SystemExit):
    """The machine-local frozen reports are not available."""


def _main_checkout() -> Path | None:
    """The main working tree of a linked worktree (reports live beside it)."""
    try:
        common = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return Path(common).parent if common else None


@cache
def phase4_dir() -> Path:
    """Directory holding the frozen APK Protocol Audit runs."""
    if _phase4_override:
        candidates = [_phase4_override[0]]
    elif env := os.environ.get(PHASE4_ENV):
        candidates = [Path(env)]
    else:
        candidates = [ROOT / PHASE4_RELATIVE]
        if (main := _main_checkout()) is not None and main != ROOT:
            candidates.append(main / PHASE4_RELATIVE)
    for candidate in candidates:
        if (candidate / RECONCILIATION_REPORT).is_dir():
            return candidate
    looked = ", ".join(str(c) for c in candidates)
    raise InputsMissing(
        f"The machine-local frozen reports are missing (looked in {looked}). The committed "
        f"catalog cannot be regenerated or checked here; pass --phase4-dir or set {PHASE4_ENV}."
    )


def reconciliation_dir() -> Path:
    return phase4_dir() / RECONCILIATION_REPORT


def idealbed_command_keys_path() -> Path:
    return phase4_dir() / IDEALBED_REPORT / "COMMAND_KEYS.json"


def idealbed_entity_controls_path() -> Path:
    return phase4_dir() / IDEALBED_REPORT / "ENTITY_CONTROLS.json"


# Pinned to the accepted Idealbed report's REPORT.SHA256.
REPORT_SHA256 = {
    "COMMAND_KEYS.json": "32976c563eaf919c076592a2060d1f3136be39e235b279011639bf850c89742e",
    "ENTITY_CONTROLS.json": "01300c8270f353b07c275906f9d6ad1b3e47d98ad1a27b1f83be3e22ca8b5f74",
}
# Intensity sliders by their entity opcode (MSG_HEAD/FOOT_INTENSITY_INC).
INTENSITY_ZONES = {"4C": "head", "4E": "foot"}
TARGET = ROOT / "custom_components/adjustable_bed/richmat_mh_catalog.py"
INVENTORY_SHA256 = {
    "representative": "4aa852c4cb31545748d5bbf8425327599f78c4e66f3d494f66966ef8ef7314e9",
    "sibling-1": "193e0c8515a42773926224e4ca3e80031a4dbe809983e001c62dd2029a82f2d5",
    "sibling-2": "fc414f663708575acce9032753b4f11ee99b73c0aa39c8f1c2231ce8ee420950",
    "sibling-3": "cb60a78c6756592e32f5d3edab0eac86b4d347da93456954fe0a4ac26ead4e9e",
    "sibling-4": "bb96926a3b1821922c3d9c7f151d32e55ec119c11a6011ec7fc37adde5290e6d",
}
PACKAGES = {
    "revive": "representative",
    "best_mattress": "sibling-1",
    "blvd_home": "sibling-2",
    "harmony": "sibling-3",
    "idealbed": "sibling-4",
}

MEM_AREAS = {88: "TV", 69: "ZG", 107: "ZG2", 70: "SNORE", 89: "LOUNGE", 46: "M1", 47: "M2", 48: "M3",
             178: "M4", 244: "M5", 49: "YOGA", 145: "LUMBAR", 108: "FLAT2", 112: "RELAX",
             98: "FACTORY_RESET", 35: "HEAD_UP_FOOT_UP", 33: "HEAD_UP_FOOT_DOWN", 34: "HEAD_DOWN_FOOT_UP",
             61: "HEAD_UP_ONLY", 62: "FOOT_UP_ONLY", 118: "MOTOR_KEEP_15", 134: "SLEEP_AID_MODE1",
             144: "MOTOR_KEEP_30", 242: "READ", 246: "FLAT_SLEEP"}
MOT_AREAS = {36: "HEAD", 38: "FOOT", 65: "LUMBAR", 63: "PILLOW", 113: "MOTOR5", 115: "MOTOR6",
             41: "HEAD_FOOT_BOTH", 67: "PILLOW_LUMBAR_BOTH", 91: "PILLOW_LUMBAR_BOTH_TILT", 60: "UBL1",
             117: "UBL2", 49: "FLAT", 132: "LOCK"}
MSG_AREAS = {76: "HEAD_INTENSITY_INC", 164: "HEAD_INTENSITY_INC2", 78: "FOOT_INTENSITY_INC",
             52: "HEAD_FOOT_BOTH_INTENSITY", 53: "HEAD_FOOT_BOTH_INTENSITY2", 54: "HEAD_FOOT_BOTH_SPEED",
             55: "HEAD_INC_FOOT_DEC_INTENSITY", 56: "HEAD_INTENSITY_INC3", 111: "HEAD_FOOT_ON_OFF",
             112: "HEAD_FOOT_ON_OFF2", 72: "MODE", 58: "MODE2", 59: "AROMA_ON_OFF", 73: "WAVE", 95: "MIN",
             93: "HEAD_FOOT_BOTH_ON", 94: "HEAD_FOOT_BOTH_OFF", 71: "MSG_OFF", 103: "INTENSITY",
             104: "MUSIC", 105: "MUSIC_VOLUME", 106: "MUSIC_VIBRATION_MODE", 107: "MUSIC_ON_OFF2",
             108: "MUSIC_PREVIOUS_NEXT", 109: "MUSIC_START_PAUSE", 217: "MUSIC_LOCK", 157: "HEAT_LEVEL",
             156: "HEAT_OFF", 161: "HEAT_MIN", 1: "MSG1_INTENSITY", 2: "MSG2_INTENSITY", 3: "MSG_MODE",
             4: "MSG_MODE3", 5: "MSG_TIME", 6: "MSG_SWITCH_BOTH"}
MOTOR_BUTTON_GROUPS = frozenset({"FLAT", "UBL1", "UBL2", "LOCK", "SYNC"})
_SCALAR = {"@+id/rvFlat": "FLAT", "@+id/rtUbl1": "UBL1", "@+id/rtUbl2": "UBL2", "@+id/rtUbl3": "UBL1",
           "@+id/rtLock": "LOCK", "@+id/rtSync": "SYNC"}
MOTOR_MODE_TYPES = {"01": "Mode1", "02": "Mode2", "03": "Mode3", "04": "Mode4", "11": "LEFT", "12": "RIGHT"}
MOTOR_BITS = {"Motor1": 0, "Motor2": 1, "Motor3": 2, "Motor4": 3}

# Fixed picker dialogs and setup-wizard identifiers. Labels are the ones the accepted
# reports record (Revive model_mappings.json, Best Mattress ANALYSIS.md P1 picker,
# HARMONY runtime-selector-inventory.json fixed_harmony_models); identifiers whose
# label the reports do not record are shown as the neutral model ID.
PICKERS: dict[str, tuple[tuple[str, str], ...]] = {
    "revive": (("vjrm", "2500"), ("farm", "3500"), ("gsrm", "3500SH"), ("fhrm", "4500"),
               ("garm", "5500"), ("iarm", "3.0"), ("vdrm", "4.0"), ("vorm", "5.0")),
    "best_mattress": (("bfrm", "BM2000"), ("utrm", "BM3000"), ("vsrm", "BM4000"), ("vorm", "BM5000")),
    "blvd_home": (("bfrm", "BFRM"), ("utrm", "UTRM"), ("eorm", "EORM"), ("garm", "GARM")),
    "harmony": (("utrm", "UTRM"), ("hvrm", "HVRM"), ("y7rm", "Y7RM"),
                ("a7rm", "BT2000"), ("t3rm", "BT2500"), ("ufrm", "BT3000 / BT3000FH"),
                ("vcrm", "BT4000"), ("vfrm", "BT6500"), ("u5rm", "BT7000")),
}
# Revive keeps its six short structured identifiers on its manual route.
MANUAL_SHORT_IDS: dict[str, tuple[str, ...]] = {"revive": ("3i", "4i", "4it", "5i", "6i", "7i")}
# Idealbed's SelectSurfaceDialogFrag.handleSurface accepts any typed or QR-scanned
# identifier whose lowercase surface class exists (I-003, SelectSurfaceDialogFrag:129-162).
MANUAL_ANY_MODEL: tuple[str, ...] = ("idealbed",)


class Raw(NamedTuple):
    route: str  # L legacy page | C VER1 entity page | B dedicated button-light page
    area: str  # motor | motor_btn | memory | massage | btn_led
    group: str
    role: str  # up | down | memory | recall | save | press
    label: str
    code: int
    keep_ms: int  # 0 when the control is ONCE


class Control(NamedTuple):
    route: str
    kind: str  # up | down | recall | save | press
    area: str
    group: str
    label: str
    code: int
    keep_ms: int


@cache
def inventory(pkg: str) -> dict[str, Any]:
    path = reconciliation_dir() / "inventories" / f"{pkg}.json"
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != INVENTORY_SHA256[pkg]:
        raise SystemExit(f"{path}: hash {digest} does not match the accepted reconciliation")
    return json.loads(data)


def _suffix_role(label: str, default: str = "?") -> str:
    low = label.lower().strip()
    if low.endswith(" up"):
        return "up"
    if low.endswith(" down"):
        return "down"
    return default


def _cb_name(label: str) -> str:
    for suffix in (" up", " down", " recall/action", " recall", " program",
                   " save/program separate button", " save/program (separate tap button)",
                   " main/recall button", " separate save button"):
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _enum_name(group: Any) -> str:
    text = group if isinstance(group, str) else group["enum"]
    m = re.search(r"E\w+Area\.(\w+)", text)
    return m.group(1) if m else text


# --------------------------------------------------------------------- adapters
# Each adapter yields (model, Raw, source pointer) for every control row it maps.


def _revive():
    d = inventory("representative")
    rows = d["supporting_inventories"]["binding_rows.json"]["content"]
    timing: dict[tuple[str, int, str], tuple[str, Any]] = {}
    for t in d["domains"]["commands"][0]["entries"]:
        if not re.fullmatch(r"P1-B\d+", t.get("id", "")):
            continue
        code = int(t["bytes"].split()[3], 16)
        for v in t["variants"]:
            timing[(v, code, t["action"].split(" [")[0])] = (
                t["timing"]["press_status"], t["timing"].get("repeat_ms"))
    for i, b in enumerate(rows):
        src = f"representative:/supporting_inventories/binding_rows.json/content/{i}"
        route, v = b["route"], b["variant"]
        if route.startswith("legacy"):
            if b.get("disposition") == "DEAD/UNUSED" or b.get("visibility_after_binder") is False:
                continue
            area_id, code = int(b["area"]), int(b["code"], 16)
            keep = int(b["ms"]) if b["press_type"] == "1" else 0
            label = b["action"]
            if route == "legacy:motorMap":
                group = b.get("tab_area") or MOT_AREAS[area_id]
                if group in MOTOR_BUTTON_GROUPS:
                    yield v, Raw("L", "motor_btn", group, "press", label, code, keep), src
                else:
                    role = "up" if label.upper().endswith(" UP") else "down"
                    yield v, Raw("L", "motor", group, role, b.get("tab_label") or group, code, keep), src
            elif route == "legacy:memoryMap":
                yield v, Raw("L", "memory", MEM_AREAS[area_id], "memory", label, code, keep), src
            else:
                yield v, Raw("L", "massage", MSG_AREAS[area_id], "press", label, code, keep), src
        elif route.startswith("dedicated"):
            yield v, Raw("B", "btn_led", "BTN_LED", "press", b["action"], int(b["code"], 16), 0), src
        else:
            kind = route.split(":")[1]
            ents = b["entity"] if isinstance(b["entity"], list) else [b["entity"]]
            for e in ents:
                name = e["name"]
                if kind == "motorMap" and e.get("up"):
                    for role in ("up", "down"):
                        if not e.get(role):
                            continue
                        code = int(e[role], 16)
                        press, ms = timing[(v, code, f"{name} {role}")]
                        assert press == "1", (v, name)
                        yield v, Raw("C", "motor", name, role, name, code, int(ms)), src
                elif kind == "motorMap":
                    code = int(e["code"], 16)
                    press, ms = timing[(v, code, name)]
                    yield v, Raw("C", "motor_btn", name, "press", name, code,
                                 int(ms) if press == "1" else 0), src
                elif kind == "memoryMap":
                    code = int(e["code"], 16)
                    assert timing[(v, code, f"{name} main/recall button")][0] == "2"
                    yield v, Raw("C", "memory", name, "recall", name, code, 0), src
                    if e.get("longCode"):
                        code2 = int(e["longCode"], 16)
                        assert timing[(v, code2, f"{name} separate save button")][0] == "2"
                        yield v, Raw("C", "memory", name, "save", name, code2, 0), src
                elif not e.get("msgRange"):
                    code = int(e["code"], 16)
                    assert timing[(v, code, name)][0] == "2"
                    yield v, Raw("C", "massage", name, "press", name, code, 0), src


def _best_mattress():
    rows = inventory("sibling-1")["domains"]["commands"][0]["entries"]
    for i, r in enumerate(rows):
        if "opcode" not in r:
            continue
        src = f"sibling-1:/domains/commands/0/entries/{i}"
        v = r["variant"][1:].lower()
        code, t = int(r["opcode"], 16), r["timing"]
        keep = int(t["repeat_interval_ms"]) if t["type"] == "KEEP" else 0
        sb, label = r.get("selector_branch") or "", r["action"]
        if sb.startswith("legacy"):
            area, group = r["ui_area"].lower(), r["group"]
            if area == "motor" and group in MOTOR_BUTTON_GROUPS:
                yield v, Raw("L", "motor_btn", group, "press", label, code, keep), src
            elif area == "motor":
                yield v, Raw("L", "motor", group, _suffix_role(label), group, code, keep), src
            elif area == "memory":
                yield v, Raw("L", "memory", group, "memory", label, code, keep), src
            else:
                yield v, Raw("L", "massage", group, "press", label, code, keep), src
        elif sb.startswith("Legacy HasBtnLed"):
            yield v, Raw("B", "btn_led", "BTN_LED", "press", label, code, 0), src
        elif sb.startswith("VER1 MotorMap"):
            yield v, Raw("C", "motor", _cb_name(label), _suffix_role(label), _cb_name(label), code, keep), src
        elif sb.startswith("VER1 RichView"):
            yield v, Raw("C", "motor_btn", "FLAT", "press", "FLAT", code, keep), src
        elif sb.startswith("VER1 MemoryMap"):
            role = "save" if "save/program" in label else "recall"
            yield v, Raw("C", "memory", _cb_name(label), role, _cb_name(label), code, keep), src
        else:
            raise AssertionError((v, label, sb))


_BLVD_AREA = re.compile(r"^(?P<model>\S+) (?P<label>.*) \[(?P<area>[A-Z_0-9]+):\d+\]$")


def _blvd_home():
    rows = inventory("sibling-2")["domains"]["commands"][0]["entries"]
    for i, r in enumerate(rows):
        m = _BLVD_AREA.match(r["action"])
        if not m or m["area"] in ("SPEECH", "MOTOR_ANGLE", "MASSAGE_CALL_INTENSITY"):
            continue
        src = f"sibling-2:/domains/commands/0/entries/{i}"
        v, area, st = m["model"], m["area"], r["source_trace"]
        assert st["visible"] is True, (v, r["action"])
        code = int(st["final_code"], 16)
        keep = int(st["ms"]) if st["pressType"] == "1" else 0
        label = st["final_label"]
        if area == "MOTOR":
            tab = st["selected_tab_tag"]
            shown = label.rsplit(" ", 1)[0] if st.get("display_resource") else tab
            yield v, Raw("L", "motor", tab, _suffix_role(label), shown, code, keep), src
        elif area == "MOTOR_SCALAR":
            yield v, Raw("L", "motor_btn", _SCALAR[st["group"]], "press", label, code, keep), src
        elif area == "MEMORY":
            yield v, Raw("L", "memory", st["group"], "memory", label, code, keep), src
        elif area == "MASSAGE":
            yield v, Raw("L", "massage", st["group"], "press", label, code, keep), src
        elif area == "MOTOR_CALL":
            yield v, Raw("C", "motor", _cb_name(label), _suffix_role(label), _cb_name(label), code, keep), src
        elif area == "MOTOR_CALL_SCALAR":
            yield v, Raw("C", "motor_btn", label, "press", label, code, keep), src
        elif area == "MEMORY_CALL":
            role = {"recall": "recall", "program": "save"}[st["role"]]
            yield v, Raw("C", "memory", _cb_name(label), role, _cb_name(label), code, keep), src
        elif area == "MASSAGE_CALL":
            yield v, Raw("C", "massage", label, "press", label, code, keep), src
        else:
            raise AssertionError(area)


def _harmony():
    d = inventory("sibling-3")
    si = d["supporting_inventories"]
    mats = {name: {v["id"]: v for v in si[name]["content"]["variants"]}
            for name in ("widget-action-matrix.json", "motor-action-matrix.json",
                         "entity-action-matrix.json", "remaining-action-matrix.json")}
    for i, r in enumerate(d["domains"]["commands"][0]["entries"]):
        ref = r.get("matrix_reference")
        if not ref or ref.startswith("speech-action-matrix.json"):
            continue
        name, v, idx = (p.strip() for p in ref.split("::"))
        a = mats[name][v]["actions"][int(idx.split()[1])]
        src = f"sibling-3:/domains/commands/0/entries/{i}"
        code = int(a.get("final_code") or a["code"], 16)
        keep = int(a["ms"]) if a["press_type"] == "1" else 0
        if name == "motor-action-matrix.json":
            yield v, Raw("L", "motor", a["area"], a["direction"].lower(), a["area"], code, keep), src
        elif name == "widget-action-matrix.json":
            assert a["visible"] is True
            area = "memory" if a["domain"] == "memoryMap" else "massage"
            yield v, Raw("L", area, _enum_name(a["group"]), "memory" if area == "memory" else "press",
                         a["label"], code, keep), src
        elif name == "remaining-action-matrix.json":
            dom = a["domain"]
            if dom == "motor-supplemental":
                yield v, Raw("L", "motor_btn", _SCALAR[a["widget"]], "press", a["label"], code, keep), src
            elif dom == "entity-motor-supplemental":
                grp = {"@+id/rvFlat": "FLAT", "@+id/rvUbl1": "UBL"}[a["widget"]]
                yield v, Raw("C", "motor_btn", grp, "press", a["label"], code, keep), src
            else:
                assert dom == "entity-massage", dom
                yield v, Raw("C", "massage", a["label"], "press", a["label"], code, keep), src
        else:
            key = a["key"]
            if a["domain"] == "entity-motor":
                yield v, Raw("C", "motor", a["label"], key.rsplit("/", 1)[1].lower(), a["label"],
                             code, keep), src
            else:
                role = {"rvSet": "recall", "rvBack": "save"}[key.rsplit("/", 1)[1]]
                yield v, Raw("C", "memory", a["label"], role, a["label"], code, keep), src


def _idealbed():
    for i, r in enumerate(inventory("sibling-4")["domains"]["commands"][0]["entries"]):
        src = f"sibling-4:/domains/commands/0/entries/{i}"
        vp = r.get("version_path") or ""
        if vp.startswith("VER0/generic"):
            ce, v = r["control_evidence"], r["variant"]
            code, t = int(r["opcode"], 16), r["timing"]
            keep = int(t["repeat_interval_ms"]) if t["press_type"] == "1" else 0
            label = r["action"]
            if ce.get("motor_group"):
                grp = ce["motor_group"][1]
                if grp in MOTOR_BUTTON_GROUPS:
                    yield v, Raw("L", "motor_btn", grp, "press", label, code, keep), src
                else:
                    role = "up" if ce["key"].endswith("_UP") else "down"
                    yield v, Raw("L", "motor", grp, role, grp, code, keep), src
            else:
                area = "memory" if "/widget/Mem" in ce["widget_source"] else "massage"
                yield v, Raw("L", area, ce["group"], "memory" if area == "memory" else "press",
                             label, code, keep), src
        elif r.get("entity_field"):
            v, code, t = r["variant"], int(r["opcode"], 16), r["timing"]
            keep = int(t["repeat_interval_ms"]) if t["press_type"] == "1" else 0
            label, ef = r["action"], r["entity_field"]
            if ef in ("up", "down"):
                yield v, Raw("C", "motor", _cb_name(label), ef, _cb_name(label), code, keep), src
            elif label.endswith(" tap"):
                yield v, Raw("C", "motor_btn", label[:-4], "press", label[:-4], code, keep), src
            elif label.endswith(" massage button"):
                nm = label[: -len(" massage button")]
                yield v, Raw("C", "massage", nm, "press", nm, code, keep), src
            else:
                role = "save" if ef == "longCode" else "recall"
                yield v, Raw("C", "memory", _cb_name(label), role, _cb_name(label), code, keep), src


ADAPTERS = {"revive": _revive, "best_mattress": _best_mattress, "blvd_home": _blvd_home,
            "harmony": _harmony, "idealbed": _idealbed}


def normalize(rows: list[Raw]) -> list[Control]:
    """Collapse one model's mapped rows into its effective, ordered control list."""
    out: list[Control] = []
    motors: dict[tuple[str, str, str], int] = {}
    mem_codes: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    mem_label: dict[tuple[str, str], str] = {}
    seen: set[tuple] = set()
    for c in rows:
        if c.area == "motor":
            key = (c.route, c.group, c.role)
            if key in motors:
                prev = out[motors[key]]
                assert (prev.code, prev.keep_ms) == (c.code, c.keep_ms), (prev, c)
                if prev.label == prev.group and c.label != c.group:
                    out[motors[key]] = prev._replace(label=c.label)
                continue
            motors[key] = len(out)
            out.append(Control(c.route, c.role, "motor", c.group, c.label, c.code, c.keep_ms))
        elif c.area == "memory" and c.role == "memory":
            codes = mem_codes[(c.route, c.group)]
            if c.code in codes:
                continue
            codes.append(c.code)
            assert len(codes) <= 2, (c, codes)
            if len(codes) == 1:
                mem_label[(c.route, c.group)] = c.label
            out.append(Control(c.route, "recall" if len(codes) == 1 else "save", "memory", c.group,
                               mem_label[(c.route, c.group)], c.code, c.keep_ms))
        else:
            kind = c.role if c.role in ("recall", "save") else "press"
            key = (c.route, kind, c.area, c.group, c.code)
            if key in seen:
                continue
            seen.add(key)
            out.append(Control(c.route, kind, c.area, c.group, c.label, c.code, c.keep_ms))
    # A one-direction entity (BLVD lprm "Back Foot Both" up) is an app button, not an axis.
    directions = collections.Counter((c.route, c.group) for c in out if c.area == "motor")
    return [
        c._replace(kind="press", area="motor_btn", label=f"{c.label} {c.kind}")
        if c.area == "motor" and directions[(c.route, c.group)] == 1
        else c
        for c in out
    ]


# ------------------------------------------------------------------- model data


def _config(pkg: str, entry: dict[str, Any]) -> dict[str, Any]:
    if pkg in ("representative", "sibling-2"):
        raw = entry.get("evaluated_state") or {}
    elif pkg in ("sibling-1", "sibling-3"):
        raw = entry.get("configuration") or {}
    else:
        raw = {}
    return {k[0].lower() + k[1:]: v for k, v in raw.items()}


def _hex(value: Any) -> str:
    if isinstance(value, dict):
        return value["hex"].upper()
    return str(value).upper()


def _text(value: Any) -> str:
    return value["text"] if isinstance(value, dict) else str(value)


def _entries(mapping: Any):
    """Yield (key, value) from a plain dict or a Harmony map_key/value list."""
    if isinstance(mapping, dict):
        yield from mapping.items()
    elif isinstance(mapping, list):
        for item in mapping:
            yield item["map_key"], item["value"]


def _ideal_setters(entry: dict[str, Any]) -> dict[str, str]:
    return {s["setter"]: s["expression"] for s in entry.get("setters", [])}


def model_features(pkg: str, entry: dict[str, Any], ideal_keys: dict[str, str]) -> dict[str, Any]:
    """Constructor flags and VER1 entity ranges the page logic reads."""
    if pkg == "sibling-4":
        return _idealbed_features(entry, ideal_keys)
    cfg = _config(pkg, entry)

    def flag(name: str) -> bool:
        return bool(cfg.get(name))

    alarm = [_hex(x) for x in cfg.get("alarmList") or []]
    snore = [_hex(x) for x in cfg.get("snoreList") or []]
    angles = []
    for _key, ent in _entries(cfg.get("motorMap")):
        call, rng = ent.get("codeCall"), ent.get("angleRange")
        if call is None or rng is None:
            continue
        bits = MOTOR_BITS[call["enum"].split(".")[1]] if isinstance(call, dict) else int(call, 2)
        angles.append((bits, _text(ent["name"]), int(rng["min"]), int(rng["max"]), int(rng["offset"])))
    intensity = []
    for key, ents in _entries(cfg.get("massageMap")):
        for ent in ents:
            rng = ent.get("msgRange")
            if rng is not None:
                group = str(_enum_name(key) if isinstance(key, dict) else key)
                zone = INTENSITY_ZONES[_hex(ent["code"])]
                # The page reads MSG1_INTENSITY as head and MSG2_INTENSITY as foot.
                assert group in {"head": ("01", "MSG1_INTENSITY"), "foot": ("02", "MSG2_INTENSITY")}[zone]
                intensity.append((zone, _text(ent["name"]), int(rng["min"]), int(rng["max"])))
    alarm_call = []
    for _key, ents in _entries(cfg.get("alarmMap")):
        for ent in ents:
            alarm_call.append((_text(ent["name"]), _hex(ent["code"])))
    modes = []
    for key, vals in _entries(cfg.get("motorModeMap")):
        k = key["enum"] if isinstance(key, dict) else str(key)
        if k in ("2", "EGroupType.SINGLE"):
            modes = [v["enum"].split(".")[1] if isinstance(v, dict) else MOTOR_MODE_TYPES[v] for v in vals]
    sleep_type = cfg.get("sleepType")
    if isinstance(sleep_type, dict):
        sleep_type = {"SleepType.NEW": "02", "SleepType.OLD": "01"}[sleep_type["enum"]]
    return {
        "led": flag("hasLed"), "btn_led": flag("hasBtnLed"), "aroma": flag("hasAroma"),
        "snore": flag("hasSnore"), "music": flag("hasMusic"), "sleep": flag("hasSleep"),
        "sleep_type": sleep_type, "speech": bool(cfg.get("speechList")),
        "smart_set_lock": flag("hasSmartSetLock"), "smart_light_lock": flag("hasSmartLightLock"),
        "new_alarm": flag("isNewAlarm") or flag("newAlarm"),
        "alarm": alarm, "snore_list": snore, "alarm_call": alarm_call, "angles": angles,
        "intensity": intensity, "motor_modes": modes,
        "call": bool(cfg.get("motorMap") or cfg.get("memoryMap") or cfg.get("massageMap")),
    }


def _pinned(path: Path) -> bytes:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != REPORT_SHA256[path.name]:
        raise SystemExit(f"{path}: hash {digest} does not match the accepted report")
    return data


@cache
def _idealbed_command_keys() -> dict[str, str]:
    table = json.loads(_pinned(idealbed_command_keys_path()))
    return {k: v["value"].upper() for k, v in table.items()}


@cache
def _idealbed_entity_controls() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(_pinned(idealbed_entity_controls_path())))


def _idealbed_entities(variant: str) -> list[dict[str, Any]]:
    return [e for e in _idealbed_entity_controls() if e["variant"] == variant]


def _idealbed_features(entry: dict[str, Any], keys: dict[str, str]) -> dict[str, Any]:
    s = _ideal_setters(entry)

    def cmdkeys(expr: str) -> list[str]:
        return [keys[k] for k in re.findall(r"CmdKey\.INSTANCE\.get(\w+)\(\)", expr)]

    # Motor and massage maps refer to local arrays, so read the report's resolved entities.
    entities = _idealbed_entities(entry["id"])
    angles = [
        (int(f["codeCall"], 2), f["name"]["default_text"], f["angleRange"]["min"],
         f["angleRange"]["max"], f["angleRange"]["offset"])
        for e in entities
        if e["type"] == "MotorEntity" and (f := e["decoded_fields"]).get("angleRange")
    ]
    intensity = [
        (INTENSITY_ZONES[e["resolved_arguments"][3].upper()], None,
         e["decoded_fields"]["msgRange"]["min"], e["decoded_fields"]["msgRange"]["max"])
        for e in entities
        if e["type"] == "MassageEntity" and e["decoded_fields"].get("msgRange")
    ]
    modes = []
    mm = s.get("setMotorModeMap", "")
    # The list items are ``MotorModeType.X.getV()`` calls, so allow empty ``()`` inside.
    for part in re.findall(
        r"EGroupType\.(\w+)\.getK\(\)\), CollectionsKt\.arrayListOf\(((?:[^()]|\(\))*)\)", mm
    ):
        if part[0] == "SINGLE":
            modes = re.findall(r"MotorModeType\.(\w+)\.getV", part[1])

    def is_true(name: str) -> bool:
        return s.get(name, "").strip() == "true"

    sleep_type = None
    if "setSleepType" in s:
        match = re.search(r"SleepType\.(\w+)", s["setSleepType"])
        assert match, s["setSleepType"]
        sleep_type = {"NEW": "02", "OLD": "01"}[match.group(1)]
    return {
        "led": is_true("setHasLed"), "btn_led": is_true("setHasBtnLed"), "aroma": is_true("setHasAroma"),
        "snore": is_true("setHasSnore"), "music": is_true("setHasMusic"), "sleep": is_true("setHasSleep"),
        "sleep_type": sleep_type, "speech": "setSpeechList" in s,
        "smart_set_lock": is_true("setHasSmartSetLock"), "smart_light_lock": is_true("setHasSmartLightLock"),
        "new_alarm": is_true("setNewAlarm") or is_true("setIsNewAlarm"),
        "alarm": cmdkeys(s.get("setAlarmList", "")), "snore_list": cmdkeys(s.get("setSnoreList", "")),
        "alarm_call": [(None, c) for c in cmdkeys(s.get("setAlarmMap", ""))],
        "angles": angles, "intensity": intensity, "motor_modes": modes,
        "call": any(k in s for k in ("setMotorMap", "setMemoryMap", "setMassageMap")),
    }


def model_ids(app: str) -> dict[str, dict[str, Any]]:
    """Every catalog entry of the package with its id, reachability and features."""
    pkg = PACKAGES[app]
    d = inventory(pkg)
    out: dict[str, dict[str, Any]] = {}
    for i, m in enumerate(d["models"]):
        e = m["entry"]
        mid = e["id"]
        if pkg == "sibling-1":
            mid = mid[1:].lower()
        if ":" in mid:
            continue  # BLVD other-flavor branch edges, dead in this package
        dead = (e.get("disposition") or e.get("reachability")) == "DEAD/UNUSED"
        out[mid] = {"index": i, "dead": dead, "entry": e, "model": m}
    return out


# ------------------------------------------------- effective constructors (RA-001)
# The reconciliation's executed-setter records override every flattened annotation
# (semantic_override_policy); unassigned fields keep the BaseSurface defaults.
_FLAG_SETTERS = {"led": "setHasLed", "btn_led": "setHasBtnLed", "aroma": "setHasAroma",
                 "snore": "setHasSnore", "music": "setHasMusic", "sleep": "setHasSleep",
                 "smart_set_lock": "setHasSmartSetLock", "smart_light_lock": "setHasSmartLightLock"}
# Fields whose effective record names only the setter (enum registers, local maps):
# the flattened value is kept when, and only when, one of these setters executed.
_VALUE_SETTERS = {"sleep_type": ("setSleepType",), "speech": ("setSpeechList",),
                  "new_alarm": ("setNewAlarm", "setIsNewAlarm"), "snore_list": ("setSnoreList",),
                  "alarm_call": ("setAlarmMap",), "angles": ("setMotorMap",),
                  "intensity": ("setMassageMap",), "motor_modes": ("setMotorModeMap",),
                  "call": ("setMotorMap", "setMemoryMap", "setMassageMap")}
_VALUE_DEFAULTS = {"sleep_type": None, "speech": False, "new_alarm": False, "snore_list": [],
                   "alarm_call": [], "angles": [], "intensity": [], "motor_modes": [], "call": False}
_HANDLED_SETTERS = {"setFunList", "setRenameMap", "setAlarmList", *_FLAG_SETTERS.values(),
                    *(s for names in _VALUE_SETTERS.values() for s in names)}
_GET_KEY = re.compile(r"CmdKey\.INSTANCE\.get(\w+)\(\)")


def _flattened_fun_keys(pkg: str, e: dict[str, Any]) -> list[str]:
    """The CmdKey names of the package's flattened (annotated) FunList."""
    if pkg == "representative":
        return [f["action"] for f in e["features"]]
    if pkg == "sibling-1":
        (stmt,) = (d["statement"] for d in e["declaration_evidence"] if d["field"] == "FunList")
        return _GET_KEY.findall(stmt)
    if pkg == "sibling-3":
        return list(e["function_keys"])
    return list(e["fun_keys"])


def _flattened_fun_codes(pkg: str, e: dict[str, Any]) -> list[str]:
    if pkg == "representative":
        return [f["value"].upper() for f in e["features"]]
    if pkg == "sibling-1":
        return [c.upper() for c in e["configuration"]["FunList"]]
    if pkg == "sibling-3":
        return [f["hex"].upper() for f in e["configuration"]["FunList"]]
    return [f["value"].upper() for f in e["fun_values"]]


@cache
def cmdkey_codes(pkg: str) -> dict[str, str]:
    """CmdKey name -> opcode, from the package's own constructor tables."""
    if pkg == "sibling-4":
        return _idealbed_command_keys()
    table: dict[str, str] = {}
    for m in inventory(pkg)["models"]:
        e = m["entry"]
        if (e.get("disposition") or e.get("reachability")) == "DEAD/UNUSED" or ":" in e["id"]:
            continue
        keys, codes = _flattened_fun_keys(pkg, e), _flattened_fun_codes(pkg, e)
        assert len(keys) == len(codes), (pkg, e["id"])
        for key, code in zip(keys, codes, strict=True):
            assert table.setdefault(key, code) == code, (pkg, e["id"], key, code, table[key])
    return table


def effective_constructor(info: dict[str, Any]) -> dict[str, Any] | None:
    rec = info["model"].get("reconciliation_effective_constructor")
    if rec is None:
        return None
    assert rec["result"] == "PASS", rec
    return rec["effective_setter_values"]


def apply_effective_features(pkg: str, values: dict[str, Any], feats: dict[str, Any]) -> dict[str, Any]:
    unknown = set(values) - _HANDLED_SETTERS
    assert not unknown, (pkg, unknown)
    out = dict(feats)
    for name, setter in _FLAG_SETTERS.items():
        out[name] = setter in values and values[setter] in (1, True)
    for name, setters in _VALUE_SETTERS.items():
        if any(s in values for s in setters):
            # The record holds only the register; the flattened value must carry it.
            assert out[name] not in (None, False, []), (pkg, name)
        else:
            out[name] = _VALUE_DEFAULTS[name]
    keys = cmdkey_codes(pkg)
    out["alarm"] = [keys[k["cmdkey"]] for k in values.get("setAlarmList") or []]
    return out


def fun_list_delta(pkg: str, info: dict[str, Any], values: dict[str, Any]) -> list[str]:
    """Effective FunList keys absent from the flattened list the command rows used."""
    effective = [k["cmdkey"] for k in values["setFunList"]]
    flattened = _flattened_fun_keys(pkg, info["entry"])
    removed = [k for k in flattened if k not in effective]
    assert not removed, (pkg, info["entry"]["id"], removed)
    return [k for k in effective if k not in flattened]


def _blvd_widget_template(code: str) -> Raw:
    """The single legacy widget every Blvd Home surface renders for one FunList code.

    MenuUtil.setFunctionList maps a CmdKey to its layout independently of the
    surface, so a code present on other surfaces has one widget template. The
    frame is the common builder S([6e, 01, txMode, code]).
    """
    shapes = set()
    for r in inventory("sibling-2")["domains"]["commands"][0]["entries"]:
        st = r.get("source_trace") or {}
        if st.get("groupcodes") == [code] and st.get("area") in ("MEMORY", "MASSAGE"):
            shapes.add((st["area"], st["group"], st["widget"], st["final_code"], st["pressType"],
                        int(st["ms"]), st["final_label"], st["visible"], st["formula"]))
    assert len(shapes) == 1, (code, shapes)
    ((area, group, _widget, final, press, ms, label, visible, formula),) = shapes
    assert visible is True and formula == "S([6e,01,txMode,hexStr2Bytes(final_code)[0]])"
    if area == "MEMORY":
        return Raw("L", "memory", group, "memory", label, int(final, 16), ms if press == "1" else 0)
    return Raw("L", "massage", group, "press", label, int(final, 16), ms if press == "1" else 0)


def derived_rows(app: str, missing: list[str]) -> list[Raw]:
    """Rows for effective FunList keys the package's command extraction skipped."""
    if not missing:
        return []
    assert app == "blvd_home", (app, missing)
    keys = cmdkey_codes(PACKAGES[app])
    return [_blvd_widget_template(keys[k]) for k in missing]


def build() -> dict[str, Any]:
    apps: dict[str, Any] = {}
    for app, adapter in ADAPTERS.items():
        pkg = PACKAGES[app]
        raw: dict[str, list[Raw]] = collections.defaultdict(list)
        for v, row, _src in adapter():
            raw[v].append(row)
        ids = model_ids(app)
        ideal_keys = _idealbed_command_keys() if pkg == "sibling-4" else {}
        models = {}
        for mid, info in sorted(ids.items()):
            if info["dead"] or mid == "qrrm":
                continue
            rows = raw.get(mid, [])
            feats = model_features(pkg, info["entry"], ideal_keys)
            values = effective_constructor(info)
            if values is not None:
                feats = apply_effective_features(pkg, values, feats)
                added = derived_rows(app, fun_list_delta(pkg, info, values))
                if added:
                    last_l = max(i for i, r in enumerate(rows) if r.route == "L")
                    rows = [*rows[: last_l + 1], *added, *rows[last_l + 1 :]]
            controls = normalize(rows)
            models[mid] = {"controls": controls, "features": feats}
        unknown = set(raw) - set(models)
        assert not unknown, (app, sorted(unknown))
        apps[app] = models
    return apps


# ------------------------------------------------------------------- emission


def render(apps: dict[str, Any]) -> str:
    control_index: dict[Control, int] = {}
    layouts: dict[tuple[int, ...], int] = {}
    feature_index: dict[str, int] = {}
    features: list[str] = []
    rows: dict[str, list[str]] = {}
    for app, models in apps.items():
        out = []
        for mid, data in models.items():
            ids = tuple(control_index.setdefault(c, len(control_index)) for c in data["controls"])
            layout = layouts.setdefault(ids, len(layouts))
            feat = repr(_features_tuple(data["features"]))
            fid = feature_index.setdefault(feat, len(features))
            if fid == len(features):
                features.append(feat)
            out.append(f"        {mid!r}: ({layout}, {fid}),")
        rows[app] = out
    lines = [
        '"""Richmat MH app catalogs (Revive Control, Best Mattress, Blvd Home, HARMONY, Idealbed).',
        "",
        "Generated by tools/generate_richmat_mh_catalog.py from the accepted row055",
        "cluster-020 inventories; do not edit by hand. Each model maps to an ordered",
        "control layout (app route, kind, page area, app group, app label, opcode,",
        "KEEP repeat interval or 0 for ONCE) and its constructor feature record.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final",
        "",
        "# fmt: off",
        "CONTROLS: Final = (",
    ]
    lines += [f"    {tuple(c)!r}," for c in control_index]
    lines += [")", "", "LAYOUTS: Final = ("]
    lines += [f"    {ids!r}," for ids in layouts]
    lines += [")", "", "# (led, btn_led, aroma, snore, music, sleep, sleep_type, speech, smart_set_lock,",
              "#  smart_light_lock, new_alarm, alarm, snore_list, alarm_call, angles, intensity,",
              "#  motor_modes, call)", "FEATURES: Final = ("]
    lines += [f"    {f}," for f in features]
    lines += [")", "", "# app -> model -> (layout index, feature index)", "MODELS: Final = {"]
    for app, out in rows.items():
        lines.append(f"    {app!r}: {{")
        lines += out
        lines.append("    },")
    lines += ["}", "", "# App picker dialogs and setup-wizard identifiers with their labels.",
              "PICKERS: Final = {"]
    for app, choices in PICKERS.items():
        lines.append(f"    {app!r}: {choices!r},")
    lines += ["}", "", "MANUAL_SHORT_IDS: Final = {"]
    for app, ids in MANUAL_SHORT_IDS.items():
        lines.append(f"    {app!r}: {ids!r},")
    lines += ["}", "", "# Apps whose manual dialog accepts any catalog model identifier.",
              f"MANUAL_ANY_MODEL: Final = {MANUAL_ANY_MODEL!r}", "# fmt: on", ""]
    return "\n".join(lines)


def _features_tuple(f: dict[str, Any]) -> tuple:
    return (
        f["led"], f["btn_led"], f["aroma"], f["snore"], f["music"], f["sleep"], f["sleep_type"],
        f["speech"], f["smart_set_lock"], f["smart_light_lock"], f["new_alarm"],
        tuple(int(c, 16) for c in f["alarm"]), tuple(int(c, 16) for c in f["snore_list"]),
        tuple((n, int(c, 16)) for n, c in f["alarm_call"]), tuple(tuple(a) for a in f["angles"]),
        tuple(tuple(x) for x in f["intensity"]), tuple(f["motor_modes"]), f["call"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Richmat MH app catalogs.")
    parser.add_argument("--check", action="store_true", help="verify the committed catalog")
    parser.add_argument("--phase4-dir", type=Path, help="directory of the frozen report runs")
    args = parser.parse_args()
    if args.phase4_dir is not None:
        _phase4_override.append(args.phase4_dir)
    try:
        text = render(build())
    except InputsMissing as err:
        print(err, file=sys.stderr)
        return 2
    if args.check:
        if TARGET.read_text() != text:
            print(f"{TARGET} is stale; regenerate it", file=sys.stderr)
            return 1
        print("catalog matches the accepted inventories")
        return 0
    TARGET.write_text(text)
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
