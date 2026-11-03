"""Generate runtime GM Control catalogs from the exact accepted row102 evidence.

Usage: uv run --no-sync python tools/generate_gmmotor_catalog.py REPORT_DIR
Raw artifacts and audit reports stay outside Git. This emits only the compact
runtime command/selection tables, never decompiled source or audit payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from pprint import pformat

ROOT = Path(__file__).resolve().parents[1]
REPORT_SEAL = "2251d01a96c95b4d5c15c369fe67202f2e8c7d513c91db88fc8b4ec31fb396d7"


def generate(report: Path) -> None:
    """Read frozen evidence; write only the caller checkout's runtime catalog."""
    assert hashlib.sha256((report / "REPORT.SHA256").read_bytes()).hexdigest() == REPORT_SEAL
    # Verify report members before using any source facts, with no mutation/replay.
    for line in (report / "REPORT.SHA256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((report / name).read_bytes()).hexdigest() == digest, name

    def read(name: str):
        return json.loads((report / name).read_text())

    materials = read("CONTROL_MATERIALS.json")
    analysis = read("analysis.json")
    inventory = analysis["variant_inventory"]
    cases = read("REACHABLE_UI_CASES_WORK.json")
    alarms = {r["id"]: r for r in read("CATALOG_ALARM_VECTORS.json")["records"]}
    command_materials = []
    material_indices = {}
    signatures = {}

    def material_row(m):
        e = m["enum"]
        return (
            e["name"],
            e["opcode"],
            e["long_opcode"],
            m["short_override"],
            m["long_override"],
            m["single_byte_short_override"],
            m["operate"]["index"],
        )

    def intern(m):
        row = material_row(m)
        if row not in signatures:
            signatures[row] = len(command_materials)
            command_materials.append(row)
        return signatures[row]

    for row in materials:
        material_indices[row["id"]] = intern(row["material"])

    case_map = defaultdict(list)
    for case in cases["cases"]:
        case_map[case["product"], case["material"]].append(case)

    def bits(state):
        return sum(int(flag) << i for i, flag in enumerate(state))

    def common_values(m, long):
        e = m["enum"]
        return (
            (m["long_override"] if m["long_override"] is not None else e["long_opcode"] or 0)
            if long
            else (m["short_override"] if m["short_override"] is not None else e["opcode"])
        )

    actions = []
    action_indices = {}
    product_controls = {}
    for product, entry in sorted(cases["products"].items()):
        product_controls[product] = {}
        for material in entry["controls"]:
            transitions = []
            for c in case_map[product, material]:
                packets = c["bytes_left_framed"]
                assert len(packets) <= 1
                phase = c["phase"]
                emit = bool(packets)
                long = phase == "long"
                target = c["captured_material"]
                target_index = intern(target)
                if emit and phase != "release":
                    opcode = packets[0][-2]
                    if common_values(target, long) & 255 != opcode:
                        long = not long
                    assert common_values(target, long) & 255 == opcode, c["id"]
                transitions.append(
                    (
                        bits(c["state_before"]),
                        phase,
                        bits(c["state_after"]),
                        emit,
                        long,
                        target_index,
                    )
                )
            row = (material_indices[material], tuple(sorted(set(transitions))))
            if row not in action_indices:
                action_indices[row] = len(actions)
                actions.append(row)
            product_controls[product][material] = action_indices[row]

    # Preserve exact occurrences within each default/selected primary catalog.
    membership = defaultdict(list)
    for row in materials:
        for use in row["usage"]:
            path = use["field_path"]
            if "0x83" not in path:
                continue
            pos = path.index("0x83")
            config = -1
            if "0x8f" in path[:pos]:
                config = path[path.index("0x8f") + 1]
            if pos == 1 or config != -1:
                membership[use["variant"], config].append((tuple(path[pos + 1 :]), row["id"]))

    profiles = {}
    side_values = {
        "Obj!DeviceSideOfBedType@a971f1": 0,
        "Obj!DeviceSideOfBedType@a97211": 1,
        "Obj!DeviceSideOfBedType@a97231": 2,
    }
    sleep_values = {
        "Obj!DeviceSleepMonitoringType@a96f71": "none",
        "Obj!DeviceSleepMonitoringType@a96f91": "ble",
        "Obj!DeviceSleepMonitoringType@a96fb1": "wifi",
    }
    routes = {}
    for variant in inventory:
        if not variant["support"]["supported"]:
            continue
        product = variant["id"]
        code = variant["selector"]["selector_text"]
        fields = variant["configuration"]["fields"]
        routes[code] = (
            variant["ui_route"],
            tuple(x for group in fields["remoteList"] for x in group),
        )
        if variant["ui_route"] != "primary":
            continue
        configurations = [(-1, fields)]
        for i, config in enumerate(fields["bedConfigList"]):
            for _, nested in config["map_entries"]:
                configurations.append((i, nested["fields"]))
        for index, f in configurations:
            controls = []
            for _, material in sorted(membership[product, index]):
                # An empty local-only material may have no command case.
                action = product_controls.get(product, {}).get(material)
                if action is not None:
                    controls.append(action)
            # Only fields with an active host consumer become runtime features.
            profiles[code if index == -1 else f"{code}:{index}"] = (
                tuple(controls),
                bits(cases["products"].get(product, {}).get("initial", [False] * 3)),
                f["isHaveLightStrip"],
                f["bedLightDisplayType"]["constant"] == "Obj!DeviceBedLightDisplayType@a96ff1",
                f["isSupportRepeatAlarm"],
                sleep_values[f["rmcSleepMonitoringType"]["constant"]],
                tuple(side_values[x["constant"]] for x in f["bedTypeList"]),
                tuple((x["enum"]["name"], x["wire_mode"]) for x in alarms[product]["choices"]),
                f["isHaveBottomMassageCountDown"],
            )
    rules = analysis["protocols"][0]["discovery_rules"]
    aliases = {}
    for vector in rules["literal_name_vectors"] + rules["name_vectors"]:
        if "selected_name" not in vector:
            continue  # Source range failure, handled safely by the HA name resolver.
        name = vector["input"].upper()
        key = name[:9] if name.startswith("MPE_") else name[:4]
        aliases[key, vector["russian"]] = vector["selected_name"]
    scan_names = tuple(
        sorted(
            set(rules["scan_keywords"])
            | {
                v["support"]["name"]
                for v in inventory
                if v["support"]["supported"] and v["support"]["name"]
            }
        )
    )
    remote_targets = defaultdict(list)
    for selection in read("PRODUCT_ROUTING_VECTORS.json")["selections"]:
        target = selection["selection"]["name"]
        if target not in remote_targets[selection["from"]]:
            remote_targets[selection["from"]].append(target)
    # Emit only consumed runtime data, with resolved source enum values.
    text = "\n".join(
        [
            '"""GM Control 4.6.6 compact runtime catalog. Generated; do not edit.',
            "",
            "See tools/generate_gmmotor_catalog.py. Raw audit reports stay local.",
            '"""',
            "from typing import Final",
            "",
            "from .gmmotor_catalog_types import ActionRow, MaterialRow, ProfileRow, RouteRow",
            "",
            "# fmt: off",
            "MATERIALS: Final[tuple[MaterialRow, ...]] = "
            + pformat(tuple(command_materials), width=110),
            "ACTIONS: Final[tuple[ActionRow, ...]] = " + pformat(tuple(actions), width=110),
            "PROFILES: Final[dict[str, ProfileRow]] = " + pformat(profiles, width=110),
            "ROUTES: Final[dict[str, RouteRow]] = " + pformat(routes, width=110),
            "NAME_ALIASES: Final[dict[tuple[str, bool], str]] = " + pformat(aliases, width=110),
            "SCAN_KEYWORDS: Final[tuple[str, ...]] = " + pformat(scan_names, width=110),
            "REMOTE_TARGETS: Final[dict[str, tuple[str, ...]]] = "
            + pformat({k: tuple(v) for k, v in remote_targets.items()}, width=110),
            "",
        ]
    )
    path = ROOT / "custom_components/adjustable_bed/gmmotor_catalog.py"
    path.write_text(text)
    manifest_path = ROOT / "custom_components/adjustable_bed/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    # HA requires a literal name prefix. Callback/manual selection still uses
    # the source substring rule when an advertisement reaches the integration.
    for keyword in (*scan_names, "RM-", "HJ-"):
        matcher = {"local_name": keyword + "*"}
        if matcher not in manifest["bluetooth"]:
            manifest["bluetooth"].append(matcher)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "materials": len(command_materials),
                "actions": len(actions),
                "profiles": len(profiles),
                "routes": len(routes),
                "bytes": len(text),
                "alarm_records_for_followup": len(alarms),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    generate(parser.parse_args().report.resolve())
