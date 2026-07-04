# /// script
# dependencies = []
# ///
"""Emit the generated remote-code artifacts from master.json.

Outputs (single source for both so labels always agree):
- okin_uuid_remotes.py    -> copy to custom_components/adjustable_bed/beds/
- gen_okimat_variants.py  -> OKIMAT_VARIANTS body to sync into const.py
"""
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
    if "back_up" in r:
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


def label_of(c):
    r = master[c]
    return f"{c} - {model_of(r.get('desc', ''))} ({features_of(r)})".replace('"', "'")


def timed(r, key, dur_key, freq_key):
    """Emit an int keycode, or a (keycode, count, delay_ms) hold tuple."""
    kc = hex(h(r[key]))
    dur, freq = r.get(dur_key), r.get(freq_key)
    if dur and freq:
        if dur % freq:
            raise ValueError(f"{r['code']}: {key} duration {dur} not a multiple of {freq}")
        return f"({kc}, {dur // freq}, {freq})"
    return kc


FIELD_ORDER = [
    ("flat", "flat"),
    ("back_up", "back_up"), ("back_down", "back_down"),
    ("legs_up", "legs_up"), ("legs_down", "legs_down"),
    ("head_up", "tilt_up"), ("head_down", "tilt_down"),
    ("feet_up", "feet_up"), ("feet_down", "feet_down"),
    ("sync", "sync"), ("child_lock", "child_lock"),
    ("zero_gravity", "zero_gravity"), ("quiet_sleep", "quiet_sleep"),
]


def kwargs_of(c):
    r = master[c]
    kv = [f'"name": "{model_of(r.get("desc", ""))}"']
    for fld, src in FIELD_ORDER:
        if src in r and r[src]:
            kv.append(f'"{fld}": {hex(h(r[src]))}')
    if r.get("memory_save"):
        kv.append(
            f'"memory_save": '
            f'{timed(r, "memory_save", "memory_save_duration_ms", "memory_save_frequency_ms")}'
        )
    mem = r.get("memory", {})
    for i in (1, 2, 3, 4):
        val = mem.get(str(i), mem.get(i))
        if val:
            kv.append(f'"memory_{i}": {hex(h(val))}')
    if "ubl" in r:
        kv.append(f'"toggle_lights": {timed(r, "ubl", "ubl_duration_ms", "ubl_frequency_ms")}')
    if r.get("massage"):
        mm = {MASSAGE_MAP[k]: hex(h(v)) for k, v in r["massage"].items() if k in MASSAGE_MAP}
        inner = ", ".join(f'"{k}": {v}' for k, v in sorted(mm.items()))
        kv.append(f"\"massage\": {{{inner}}}")
    return ", ".join(kv)


codes = sorted(master, key=int)

hdr = '''"""Generated Okin UUID remote-code table (DO NOT EDIT BY HAND).

Source of truth: the DewertOkin FurniMove handset backend
(``GET /mobile-data/button/{remote_id}``), supplemented by the bundled
``handsetlist.csv`` capability flags for remote codes the backend no longer
serves. Regenerate with ``tools/okin_remotes/gen_module.py`` (see the README
there for the full pipeline).

Each entry is keyword arguments for ``OkinUuidRemoteConfig`` (see
``okin_uuid.py``). Keycodes are the 32-bit Okin command values; the controller
wraps them as ``[0x04, 0x02, <4-byte big-endian>]``. ``memory_save`` and
``toggle_lights`` may be ``(keycode, count, delay_ms)`` hold tuples when the
backend specifies hold timing for that handset.

``source`` comment legend:
  backend         -> authoritative keycodes from the live handset backend
  csv-inherit:<n> -> pruned code; keycodes inherited from live sibling <n>
                     with the identical capability signature
  csv-reconstruct -> pruned code with no live sibling; keycodes rebuilt from
                     the universal/modal Okin keycode maps (Flat may be
                     approximate)
"""

from __future__ import annotations

# Default remote when variant is auto/unknown (most common basic RF-TOPLINE).
DEFAULT_OKIN_UUID_REMOTE = "82417"

# code -> dropdown label
OKIN_UUID_VARIANT_LABELS: dict[str, str] = {
'''

lines = [hdr.rstrip("\n")]
for c in codes:
    lines.append(f'    "{c}": "{label_of(c)}",')
lines.append("}\n")
lines.append("# code -> OkinUuidRemoteConfig kwargs")
lines.append("OKIN_UUID_REMOTE_DATA: dict[str, dict] = {")
for c in codes:
    lines.append(f'    "{c}": {{{kwargs_of(c)}}},  # {master[c].get("source", "")}')
lines.append("}")
open("okin_uuid_remotes.py", "w").write("\n".join(lines) + "\n")

# ---- const.py OKIMAT_VARIANTS body ----
out = ["OKIMAT_VARIANTS: Final = {", '    VARIANT_AUTO: "Auto-detect (try 82417 first)",']
for c in codes:
    out.append(f'    "{c}": "{label_of(c)}",')
out.append("}")
open("gen_okimat_variants.py", "w").write("\n".join(out) + "\n")

print("wrote okin_uuid_remotes.py + gen_okimat_variants.py:", len(codes), "codes")
