"""Derive compact, immutable wire expectations from accepted row102 vectors.

Only test inputs/expected bytes and catalog membership are emitted. No APK,
decompiled instructions, audit report or mutable implementation output is copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAL = "2251d01a96c95b4d5c15c369fe67202f2e8c7d513c91db88fc8b4ec31fb396d7"


def generate(report: Path) -> None:
    assert hashlib.sha256((report / "REPORT.SHA256").read_bytes()).hexdigest() == SEAL
    for line in (report / "REPORT.SHA256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((report / name).read_bytes()).hexdigest() == digest, name

    def read(name):
        return json.loads((report / name).read_text())

    materials = read("CONTROL_MATERIALS.json")
    by_id = {row["id"]: row["material"] for row in materials}

    def signature(m):
        e = m["enum"]
        return [
            e["name"],
            e["opcode"],
            e["long_opcode"],
            m["short_override"],
            m["long_override"],
            m["single_byte_short_override"],
            m["operate"]["index"],
        ]

    builder_vectors = {}
    for row in read("CONTROL_BUILDER_VECTORS.json"):
        sig = signature(by_id[row["material"]])[:6]
        vectors = [[v["side"], v["single"], v["long"], v["bytes_hex"]] for v in row["vectors"]]
        key = json.dumps(sig)
        if key in builder_vectors:
            assert builder_vectors[key][1] == vectors
        builder_vectors[key] = [sig, vectors]

    def bits(state):
        return sum(int(value) << i for i, value in enumerate(state))

    grouped = defaultdict(list)
    raw_ui = read("REACHABLE_UI_CASES_WORK.json")
    for c in raw_ui["cases"]:
        grouped[c["product"], c["material"]].append(
            [
                bits(c["state_before"]),
                c["phase"],
                bits(c["state_after"]),
                bytes(c["bytes_left_framed"][0]).hex() if c["bytes_left_framed"] else "",
            ]
        )
    bundles, interned, contexts = [], {}, {}
    for context, vectors in grouped.items():
        bundle = [signature(by_id[context[1]]), sorted(vectors)]
        key = json.dumps(bundle)
        if key not in interned:
            interned[key] = len(bundles)
            bundles.append(bundle)
        contexts[context] = interned[key]
    membership = defaultdict(list)
    for row in materials:
        for use in row["usage"]:
            path = use["field_path"]
            if "0x83" not in path:
                continue
            pos = path.index("0x83")
            nested = path[path.index("0x8f") + 1] if "0x8f" in path[:pos] else -1
            context = (use["variant"], row["id"])
            if (pos == 1 or nested != -1) and context in contexts:
                membership[use["variant"], nested].append(
                    (tuple(path[pos + 1 :]), contexts[context])
                )
    profiles, profile_metadata = {}, {}
    alarm_records = {r["id"]: r for r in read("CATALOG_ALARM_VECTORS.json")["records"]}
    side_names = {
        "Obj!DeviceSideOfBedType@a971f1": 0,
        "Obj!DeviceSideOfBedType@a97211": 1,
        "Obj!DeviceSideOfBedType@a97231": 2,
    }
    sleep_names = {
        "Obj!DeviceSleepMonitoringType@a96f71": "none",
        "Obj!DeviceSleepMonitoringType@a96f91": "ble",
        "Obj!DeviceSleepMonitoringType@a96fb1": "wifi",
    }

    def metadata(f, product):
        return [
            f["isHaveLightStrip"],
            f["bedLightDisplayType"]["constant"] == "Obj!DeviceBedLightDisplayType@a96ff1",
            f["isSupportRepeatAlarm"],
            sleep_names[f["rmcSleepMonitoringType"]["constant"]],
            [side_names[x["constant"]] for x in f["bedTypeList"]],
            [[x["enum"]["name"], x["wire_mode"]] for x in alarm_records[product]["choices"]],
            f["isHaveBottomMassageCountDown"],
        ]

    for v in read("analysis.json")["variant_inventory"]:
        if not v["support"]["supported"] or v["ui_route"] != "primary":
            continue
        code, product = v["selector"]["selector_text"], v["id"]
        profiles[code] = [index for _, index in sorted(membership[product, -1])]
        f = v["configuration"]["fields"]
        profile_metadata[code] = metadata(f, product)
        for i, nested in enumerate(f["bedConfigList"]):
            profiles[f"{code}:{i}"] = [index for _, index in sorted(membership[product, i])]
            profile_metadata[f"{code}:{i}"] = metadata(
                nested["map_entries"][0][1]["fields"], product
            )
    data = {
        "report_seal": SEAL,
        "builder_vectors": list(builder_vectors.values()),
        "ui_vectors": bundles,
        "profiles": profiles,
        "profile_metadata": profile_metadata,
        "source_counts": {
            "members": 1182,
            "default_field_relationships": 41370,
            "nested_field_relationships": 140,
            "ui_cases": len(raw_ui["cases"]),
        },
    }
    path = ROOT / "tests/fixtures/gmmotor_vectors.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "builder_materials": len(builder_vectors),
                "ui_contexts": len(contexts),
                "unique_ui_bundles": len(bundles),
                "profiles": len(profiles),
                "bytes": path.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    generate(parser.parse_args().report.resolve())
