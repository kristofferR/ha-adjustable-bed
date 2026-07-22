# /// script
# dependencies = []
# ///
"""Build the canonical per-remote-code dataset from backend maps + CSV flags.

Output: master.json  { code: record } and a coverage report on stderr.
Live codes -> authoritative backend keycodes.
Pruned codes (in CSV, not live) -> inherit keycodes from a live code with the
identical capability signature; else reconstruct from the universal keycode map.
"""
import csv
import glob
import json
import sys
import collections

CACHE = "cache"
CSV_PATH = "handsetlist.csv"

# Universal keycode map (fallback reconstruction), from backend modal values.
UNIV = {
    "tilt_up": "0x00000010", "tilt_down": "0x00000020",   # M1
    "back_up": "0x00000001", "back_down": "0x00000002",   # M2
    "legs_up": "0x00000004", "legs_down": "0x00000008",   # M3
    "feet_up": "0x00000040", "feet_down": "0x00000080",   # M4
    "memory_save": "0x00010000", "sync": "0x00000100",
    "child_lock": "0x08000000", "ubl": "0x00020000",
    "memory": {1: "0x00001000", 2: "0x00002000", 3: "0x00004000", 4: "0x00008000"},
    "flat": "0x100000aa",
}

# backend action -> our field
ACT = {
    "M1Out": "tilt_up", "M1In": "tilt_down",
    "M2Out": "back_up", "M2In": "back_down",
    "M3Out": "legs_up", "M3In": "legs_down",
    "M4Out": "feet_up", "M4In": "feet_down",
    "MemoSave": "memory_save", "Sync": "sync", "ChildLock": "child_lock",
    "UBL": "ubl", "Flat": "flat", "ZeroGravity": "zero_gravity",
    "QuietSleep": "quiet_sleep",
}
MASSAGE_ACTS = [
    "MassageAll", "Massager1", "Massager2", "Massager3", "MassagerWave",
    "MassagerHead", "MassagerHeadPlus", "MassagerHeadMinus",
    "MassagerFeet", "MassagerFeetPlus", "MassagerFeetMinus", "MassagerStop",
]


def load_live():
    live = {}
    for f in sorted(glob.glob(f"{CACHE}/*_button.json")):
        rid = f.split("/")[-1].split("_")[0]
        b = json.load(open(f))["body"]
        if not b.startswith("["):
            continue
        arr = json.loads(b)
        rec = {"code": rid, "source": "backend"}
        m = {}
        memory = {}
        massage = {}
        for x in arr:
            a = x["action"]
            kc = x["keycode"].lower()
            if a in ACT:
                m[ACT[a]] = kc
                # Preserve backend timing metadata. MemoSave uses it as a
                # hold-to-save duration. FurniMove's UBL touch path does not
                # consult these fields; it repeats only while touch is held.
                if a == "MemoSave" and x.get("duration") and x.get("frequency"):
                    rec["memory_save_duration_ms"] = x["duration"]
                    rec["memory_save_frequency_ms"] = x["frequency"]
                elif a == "UBL" and x.get("duration") and x.get("frequency"):
                    rec["ubl_duration_ms"] = x["duration"]
                    rec["ubl_frequency_ms"] = x["frequency"]
            elif a.startswith("Memo") and a[4:].isdigit():
                memory[int(a[4:])] = kc
            elif a in MASSAGE_ACTS:
                massage[a] = kc
        rec.update(m)
        if memory:
            rec["memory"] = {k: memory[k] for k in sorted(memory)}
        if massage:
            rec["massage"] = massage
        rec["desc"] = live_desc(rid)
        live[rid] = rec
    return live


def live_desc(rid):
    """Read a code's handset description from the cached object response."""
    try:
        od = json.load(open(f"{CACHE}/{rid}_object.json"))["body"]
        return json.loads(od)[0].get("description", "") if od.startswith("[") else ""
    except Exception:
        return ""


def signature(rec):
    """Capability signature (structure, not exact values) for matching."""
    motors = tuple(sorted(k for k in ("tilt_up", "back_up", "legs_up", "feet_up") if k in rec))
    memc = len(rec.get("memory", {}))
    return (
        motors, memc, "memory_save" in rec, "sync" in rec, "child_lock" in rec,
        bool(rec.get("massage")), "zero_gravity" in rec, "quiet_sleep" in rec,
    )


def csv_signature(row):
    def y(col):
        return row.get(col, "").strip().lower() == "y"
    motors = []
    if y("M1_up"):
        motors.append("tilt_up")
    if y("M2_up"):
        motors.append("back_up")
    if y("M3_up"):
        motors.append("legs_up")
    if y("M4_up"):
        motors.append("feet_up")
    memc = sum(1 for i in (1, 2, 3, 4) if y(f"Memory {i}"))
    has_massage = y("Massage_program1") or y("Massage_out")
    return (
        tuple(sorted(motors)), memc, y("Memoposition_save"), y("Synch"),
        y("Child_lock"), has_massage, y("Zero Gravity"), y("Quiet Sleep"),
    )


def modal_extras(live):
    """Modal massage/zero-gravity keycodes across live handsets.

    The massage keycodes are identical on every live massage handset and
    zero-gravity is a single value, so pruned CSV codes flagged with those
    capabilities can be reconstructed from the modal maps.
    """
    massage = collections.defaultdict(collections.Counter)
    zerog = collections.Counter()
    for rec in live.values():
        for act, kc in (rec.get("massage") or {}).items():
            massage[act][kc] += 1
        if "zero_gravity" in rec:
            zerog[rec["zero_gravity"]] += 1
    modal_massage = {act: c.most_common(1)[0][0] for act, c in massage.items()}
    # Wave only exists on a minority of handsets; don't guess it for
    # reconstructed codes.
    modal_massage.pop("MassagerWave", None)
    return modal_massage, zerog.most_common(1)[0][0] if zerog else None


def reconstruct(sig, has_ubl, modal_massage, modal_zerog):
    motors, memc, msave, sync, clock, massage, zerog, quiet = sig
    rec = {}
    for mk in motors:
        base = mk[:-3]  # tilt/back/legs/feet
        rec[f"{base}_up"] = UNIV[f"{base}_up"]
        rec[f"{base}_down"] = UNIV[f"{base}_down"]
    if memc:
        rec["memory"] = {i: UNIV["memory"][i] for i in range(1, memc + 1)}
    if msave:
        rec["memory_save"] = UNIV["memory_save"]
    if sync:
        rec["sync"] = UNIV["sync"]
    if clock:
        rec["child_lock"] = UNIV["child_lock"]
    if massage and modal_massage:
        rec["massage"] = dict(modal_massage)
    if zerog and modal_zerog:
        rec["zero_gravity"] = modal_zerog
    # No live handset exposes QuietSleep, so `quiet` cannot be reconstructed.
    if has_ubl:
        rec["ubl"] = UNIV["ubl"]
    rec["flat"] = UNIV["flat"]
    return rec


def apply_csv_ubl(rec, row):
    """Honor the CSV UBL flag on CSV-sourced records.

    The capability signature doesn't include UBL, so an inherited sibling may
    disagree with the pruned code's own CSV row — the row is authoritative
    for which buttons the handset has.
    """
    has_ubl = row.get("UBL", "").strip().lower() == "y"
    if not has_ubl:
        for key in ("ubl", "ubl_duration_ms", "ubl_frequency_ms"):
            rec.pop(key, None)
    elif "ubl" not in rec:
        rec["ubl"] = UNIV["ubl"]
    return rec


# Codes that reuse the handset backend but are a DIFFERENT protocol
# ("DOT PROTOCOL" / RF1058 / RF34 / RF6707). These boxes speak the CB24-style
# 7-byte frame [0x05, 0x02, <keycode BE>, 0x00] over Nordic UART instead of
# the standard Okin 6-byte [0x04, 0x02, <keycode BE>] frame, and renumber the
# motor bits per handset (whichever channels exist start at 0x1/0x2) with
# Flat=0x08000000. They are emitted with protocol="dot" and kept out of the
# csv-inherit pool so standard codes never inherit DOT keycodes.
# Source: com.okin.okinsmartcomfort HexValueConverter.toByteArray(isDOTProtocol)
# + BluetoothLeService.setCharacteristics (CB24_WRITE_CHARACTERISTIC 6E400002).
DOT_CODES = {"90167", "93558", "97450", "97544", "98035", "91983"}

# FurniMove UI names for the motor channels (OkinMoveTypeConverters):
# M1=Head, M2=Back, M3=Legs, M4=Feet. Head maps to the tilt_* master fields
# (emitted as head_up/head_down config kwargs by the generators).
_M_FIELD = {"M1": "tilt", "M2": "back", "M3": "legs", "M4": "feet"}
_M_SECTION = {"M1": "Head", "M2": "Back", "M3": "Legs", "M4": "Feet"}


def dot_record(rid, arr, desc):
    """Build a DOT-protocol master record from a backend button array.

    DOT motor bits are renumbered per handset (the keycodes always start at
    0x1/0x2 for whichever channels exist), but each channel keeps its section
    meaning — map M-numbers to the standard section fields so the exposed HA
    controls carry the right names (RF1058 = Head+Feet, RF6707 = Head+Back).
    """
    rec = {"code": rid, "source": "backend", "protocol": "dot", "desc": desc}
    sections = []
    memory = {}
    massage = {}
    for x in sorted(arr, key=lambda x: x["action"]):
        a, kc = x["action"], x["keycode"].lower()
        if a[:2] in _M_FIELD and a[2:] in ("Out", "In"):
            field = _M_FIELD[a[:2]]
            rec[f"{field}_{'up' if a[2:] == 'Out' else 'down'}"] = kc
            if _M_SECTION[a[:2]] not in sections:
                sections.append(_M_SECTION[a[:2]])
        elif a.startswith("Memo") and a[4:].isdigit():
            memory[int(a[4:])] = kc
        elif a == "MemoSave":
            rec["memory_save"] = kc
            if x.get("duration") and x.get("frequency"):
                rec["memory_save_duration_ms"] = x["duration"]
                rec["memory_save_frequency_ms"] = x["frequency"]
        elif a in MASSAGE_ACTS:
            massage[a] = kc
        elif a == "Flat":
            rec["flat"] = kc
        elif a == "UBL":
            rec["ubl"] = kc
            if x.get("duration") and x.get("frequency"):
                rec["ubl_duration_ms"] = x["duration"]
                rec["ubl_frequency_ms"] = x["frequency"]
        elif a == "ZeroGravity":
            rec["zero_gravity"] = kc
        elif a == "QuietSleep":
            rec["quiet_sleep"] = kc
        elif a == "Snore":
            rec["anti_snore"] = kc
    rec["sections"] = "/".join(sections)
    if memory:
        rec["memory"] = {k: memory[k] for k in sorted(memory)}
    if massage:
        rec["massage"] = massage
    return rec


def main():
    live = load_live()
    dot = {}
    for c in DOT_CODES:
        if live.pop(c, None) is None:
            continue
        raw = json.load(open(f"{CACHE}/{c}_button.json"))["body"]
        dot[c] = dot_record(c, json.loads(raw), live_desc(c))
    # index live by signature (DOT codes removed: never an inherit source)
    by_sig = collections.defaultdict(list)
    for rid, rec in live.items():
        by_sig[signature(rec)].append(rid)

    rows = {}
    with open(CSV_PATH, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            rid = row["RemoteID"].strip()
            if rid.isdigit():
                rows[rid] = row

    master = {}
    stats = collections.Counter()
    for rid, rec in live.items():
        master[rid] = rec
        stats["backend"] += 1
    for rid, rec in dot.items():
        master[rid] = rec
        stats["backend-dot"] += 1

    modal_massage, modal_zerog = modal_extras(live)

    for rid, row in rows.items():
        if rid in master:
            continue
        sig = csv_signature(row)
        desc = row.get("Description", "")
        siblings = by_sig.get(sig, [])
        if siblings:
            # inherit from the sibling; pick modal Flat among siblings
            flats = collections.Counter(live[s].get("flat", UNIV["flat"]) for s in siblings)
            src = siblings[0]
            rec = dict(live[src])
            rec["flat"] = flats.most_common(1)[0][0]
            rec["code"] = rid
            rec["desc"] = desc
            rec["source"] = f"csv-inherit:{src}"
            master[rid] = apply_csv_ubl(rec, row)
            stats["csv-inherit"] += 1
        else:
            has_ubl = row.get("UBL", "").strip().lower() == "y"
            rec = reconstruct(sig, has_ubl, modal_massage, modal_zerog)
            rec["code"] = rid
            rec["desc"] = desc
            rec["source"] = "csv-reconstruct"
            master[rid] = rec
            stats["csv-reconstruct"] += 1

    json.dump(master, open("master.json", "w"), indent=1)
    print("=== master build ===", file=sys.stderr)
    print("total codes:", len(master), file=sys.stderr)
    for k, v in stats.most_common():
        print(f"  {k}: {v}", file=sys.stderr)
    # distinct flat values
    flats = collections.Counter(r.get("flat") for r in master.values())
    print("flat distribution:", dict(flats), file=sys.stderr)
    # capability spread
    caps = collections.Counter()
    for r in master.values():
        if "tilt_up" in r:
            caps["tilt_motor"] += 1
        if "feet_up" in r:
            caps["feet_motor"] += 1
        if r.get("memory"):
            caps[f"memory_x{len(r['memory'])}"] += 1
        if "memory_save" in r:
            caps["memory_save"] += 1
        if "sync" in r:
            caps["sync"] += 1
        if "child_lock" in r:
            caps["child_lock"] += 1
        if "zero_gravity" in r:
            caps["zero_gravity"] += 1
        if "quiet_sleep" in r:
            caps["quiet_sleep"] += 1
        if r.get("massage"):
            caps["massage"] += 1
    print("capability spread:", file=sys.stderr)
    for k, v in caps.most_common():
        print(f"  {k}: {v}", file=sys.stderr)


main()
