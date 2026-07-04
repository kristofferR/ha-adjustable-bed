# /// script
# dependencies = []
# ///
"""Generate okin_uuid remote table + const OKIMAT_VARIANTS from master.json."""
import json
import re

master = json.load(open("master.json"))


def h(v):
    """int literal from hex string."""
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
    # first token up to first space is usually the model family
    m = re.match(r"([A-Za-z0-9/\-]+)", d)
    return m.group(1) if m else d[:20]


def features_of(r):
    parts = []
    motors = []
    if "tilt_up" in r:
        motors.append("Head")
    if "back_up" in r:
        motors.append("Back")
    if "legs_up" in r:
        motors.append("Legs")
    if "feet_up" in r:
        motors.append("Feet")
    parts.append("/".join(motors))
    nmem = len(r.get("memory", {}))
    if nmem:
        parts.append(f"{nmem} Mem")
    if r.get("massage"):
        parts.append("Massage")
    return ", ".join(parts)


def label(code, r):
    return f"{code} - {model_of(r.get('desc',''))} ({features_of(r)})"


# ---- const OKIMAT_VARIANTS body ----
codes = sorted(master, key=int)
lines = ['OKIMAT_VARIANTS: Final = {', '    VARIANT_AUTO: "Auto-detect (try 82417 first)",']
for c in codes:
    lab = label(c, master[c]).replace('"', "'")
    lines.append(f'    "{c}": "{lab}",')
lines.append("}")
open("gen_okimat_variants.py", "w").write("\n".join(lines) + "\n")

# ---- okin_uuid remote data ----
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
out = ["_REMOTE_DATA: dict[str, dict] = {"]
for c in codes:
    r = master[c]
    kv = []
    kv.append(f'"name": "{model_of(r.get("desc",""))}"')
    for fld, src in FIELD_ORDER:
        if src in r and r[src]:
            kv.append(f'"{fld}": {hex(h(r[src]))}')
    mem = r.get("memory", {})
    for i in (1, 2, 3, 4):
        if str(i) in mem or i in mem:
            val = mem.get(str(i), mem.get(i))
            kv.append(f'"memory_{i}": {hex(h(val))}')
    if "ubl" in r:
        kv.append(f'"toggle_lights": {hex(h(r["ubl"]))}')
    if r.get("massage"):
        mm = {MASSAGE_MAP[k]: hex(h(v)) for k, v in r["massage"].items() if k in MASSAGE_MAP}
        inner = ", ".join(f'"{k}": {v}' for k, v in sorted(mm.items()))
        kv.append(f"\"massage\": {{{inner}}}")
    src = r.get("source", "")
    out.append(f'    "{c}": {{{", ".join(kv)}}},  # {src}')
out.append("}")
open("gen_remote_data.py", "w").write("\n".join(out) + "\n")

print("wrote gen_okimat_variants.py and gen_remote_data.py")
print("codes:", len(codes))
# sample
print("\nsample labels:")
for c in ["82417", "93332", "82795", "90658", "83126"]:
    if c in master:
        print(" ", label(c, master[c]))
