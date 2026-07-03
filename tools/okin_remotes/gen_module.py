# /// script
# dependencies = []
# ///
"""Emit the full beds/okin_uuid_remotes.py leaf module."""
import json
import re

master = json.load(open("master.json"))


def h(v):
    return int(v, 16)


MASSAGE_MAP = {
    "MassagerHeadPlus": "head_up", "MassagerHeadMinus": "head_down",
    "MassagerFeetPlus": "foot_up", "MassagerFeetMinus": "foot_down",
    "MassagerStop": "stop", "MassagerWave": "wave", "MassageAll": "all",
    "Massager1": "mode1", "Massager2": "mode2", "Massager3": "mode3",
    "MassagerHead": "head_toggle", "MassagerFeet": "foot_toggle",
}


def model_of(desc):
    if not desc:
        return "Okin RF"
    d = desc.strip().strip('"').strip()
    m = re.match(r"([A-Za-z0-9/\-]+)", d)
    return m.group(1) if m else d[:20]


def features_of(r):
    motors = []
    if "tilt_up" in r:
        motors.append("Head")
    motors.append("Back")
    if "legs_up" in r:
        motors.append("Legs")
    if "feet_up" in r:
        motors.append("Feet")
    parts = ["/".join(motors)]
    nmem = len(r.get("memory", {}))
    if nmem:
        parts.append(f"{nmem} Mem")
    if r.get("massage"):
        parts.append("Massage")
    return ", ".join(parts)


FIELD_ORDER = [
    ("flat", "flat"),
    ("back_up", "back_up"), ("back_down", "back_down"),
    ("legs_up", "legs_up"), ("legs_down", "legs_down"),
    ("head_up", "tilt_up"), ("head_down", "tilt_down"),
    ("feet_up", "feet_up"), ("feet_down", "feet_down"),
    ("sync", "sync"), ("child_lock", "child_lock"),
    ("zero_gravity", "zero_gravity"), ("quiet_sleep", "quiet_sleep"),
    ("memory_save", "memory_save"),
]
codes = sorted(master, key=int)

hdr = '''"""Generated Okin UUID remote-code table (DO NOT EDIT BY HAND).

Source of truth: the DewertOkin FurniMove handset backend
(``GET /mobile-data/button/{remote_id}``), supplemented by the bundled
``handsetlist.csv`` capability flags for remote codes the backend no longer
serves. Regenerate with the project's ``tools/gen_okin_remotes.py`` script.

Each entry is keyword arguments for ``OkinUuidRemoteConfig`` (see
``okin_uuid.py``). Keycodes are the 32-bit Okin command values; the controller
wraps them as ``[0x04, 0x02, <4-byte big-endian>]``.

``source`` comment legend:
  backend         -> authoritative keycodes from the live handset backend
  csv-inherit:<n> -> pruned code; keycodes inherited from live sibling <n>
                     with the identical capability signature
  csv-reconstruct -> pruned code with no live sibling; keycodes rebuilt from
                     the universal Okin keycode map (Flat may be approximate)
"""

from __future__ import annotations

# Default remote when variant is auto/unknown (most common basic RF-TOPLINE).
DEFAULT_OKIN_UUID_REMOTE = "82417"

# code -> dropdown label
OKIN_UUID_VARIANT_LABELS: dict[str, str] = {
'''
lines = [hdr]
for c in codes:
    lab = f"{c} - {model_of(master[c].get('desc',''))} ({features_of(master[c])})".replace('"', "'")
    lines.append(f'    "{c}": "{lab}",')
lines.append("}\n")
lines.append("# code -> OkinUuidRemoteConfig kwargs")
lines.append("OKIN_UUID_REMOTE_DATA: dict[str, dict] = {")
for c in codes:
    r = master[c]
    kv = [f'"name": "{model_of(r.get("desc",""))}"']
    for fld, src in FIELD_ORDER:
        if src in r and r[src]:
            kv.append(f'"{fld}": {hex(h(r[src]))}')
    mem = r.get("memory", {})
    for i in (1, 2, 3, 4):
        val = mem.get(str(i), mem.get(i))
        if val:
            kv.append(f'"memory_{i}": {hex(h(val))}')
    if "ubl" in r:
        kv.append(f'"toggle_lights": {hex(h(r["ubl"]))}')
    if r.get("massage"):
        mm = {MASSAGE_MAP[k]: hex(h(v)) for k, v in r["massage"].items() if k in MASSAGE_MAP}
        inner = ", ".join(f'"{k}": {v}' for k, v in sorted(mm.items()))
        kv.append(f"\"massage\": {{{inner}}}")
    lines.append(f'    "{c}": {{{", ".join(kv)}}},  # {r.get("source","")}')
lines.append("}")

open("okin_uuid_remotes.py", "w").write("\n".join(lines) + "\n")
print("wrote okin_uuid_remotes.py:", len(codes), "codes")
