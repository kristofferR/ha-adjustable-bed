#!/usr/bin/env python3
"""Merge local, Google Play, and APKPure evidence into the APK currency report."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

LATEST_FIELDS = [
    "package_id",
    "application_names",
    "local_version_name",
    "local_version_code",
    "local_architectures",
    "play_status",
    "play_version",
    "play_updated",
    "play_developer",
    "play_url",
    "play_availability",
    "apkpure_status",
    "apkpure_version_name",
    "apkpure_version_code",
    "apkpure_release_date",
    "apkpure_architectures",
    "apkpure_url",
    "latest_version_name",
    "latest_version_code",
    "latest_release_date",
    "latest_architectures",
    "latest_source",
    "cross_check",
    "classification",
    "blocker",
    "lookup_date",
]

DISCOVERY_FIELDS = [
    "package_id",
    "title",
    "developer",
    "developer_id",
    "play_url",
    "relevance",
    "reason",
    "play_status",
    "play_version",
    "play_updated",
    "apkpure_status",
    "apkpure_version_name",
    "apkpure_version_code",
    "apkpure_release_date",
    "apkpure_architectures",
    "apkpure_url",
    "latest_version_name",
    "latest_version_code",
    "cross_check",
    "blocker",
]

USER_CONFIRMED_BED_APPS = {
    "com.ly.homekobo",
    "com.okin.meisemobell",
    "com.okin.yamada",
    "com.sealy.flexirest",
    "com.sfd.slim",
    "com.sn.dianqi",
}

USER_CONFIRMED_NON_BED_APPS = {
    "at.logicdata.motionatwork",
    "com.keeson.ergopowercommand",
    "com.keeson.rondurewifi",
    "com.keeson.smartbed",
    "com.sbi.ada",
    "com.sbi.allswell",
    "com.sbi.markbase",
}


def classify(
    local_version_name: str,
    local_version_code: str,
    play: dict[str, Any],
    apkpure: dict[str, Any],
) -> tuple[str, str, str]:
    """Return classification, cross-check status, and any verification blocker."""
    play_status = play.get("status", "")
    play_version = play.get("version", "")
    apkpure_status = apkpure.get("status", "")
    apkpure_version = apkpure.get("version_name", "")
    apkpure_code = apkpure.get("version_code", "")

    if play_version and apkpure_version:
        cross_check = "matched" if play_version == apkpure_version else "version_mismatch"
    elif play_version:
        cross_check = "google_play_only"
    elif apkpure_version:
        cross_check = "apkpure_only"
    else:
        cross_check = "no_version_metadata"

    if cross_check == "version_mismatch":
        blocker = f"Google Play reports {play_version}; APKPure reports {apkpure_version}"
        return "unverifiable", cross_check, blocker

    if apkpure_status == "available" and apkpure_version:
        if local_version_code.isdigit() and str(apkpure_code).isdigit():
            local_code = int(local_version_code)
            latest_code = int(apkpure_code)
            if local_code == latest_code:
                return "current", cross_check, ""
            if local_code < latest_code:
                return "outdated", cross_check, ""
            return (
                "unverifiable",
                cross_check,
                f"local versionCode {local_code} is newer than APKPure {latest_code}",
            )
        if local_version_name == apkpure_version:
            return "current", cross_check, ""
        return (
            "unverifiable",
            cross_check,
            "version names differ and comparable versionCode metadata is unavailable",
        )

    if play_version:
        if local_version_name == play_version:
            return "current", cross_check, "APKPure has no current listing"
        return (
            "unverifiable",
            cross_check,
            "Google Play version differs, but Play does not expose versionCode",
        )

    if play_status in {"region_restricted", "not_in_region"}:
        return "region restricted", cross_check, "no version metadata available in probed regions"
    if play_status == "not_found" and apkpure_status in {"not_found", "removed"}:
        return "removed", cross_check, "not found on APKPure or in seven probed Play markets"
    if play_status == "not_found" and apkpure_status == "available":
        return "unavailable", cross_check, "Google Play listing not found in seven probed markets"
    errors = "; ".join(
        value
        for value in (play.get("error", ""), apkpure.get("error", ""))
        if value
    )
    return "unverifiable", cross_check, errors or "latest version metadata is unavailable"


def discovery_relevance(package_id: str, title: str) -> tuple[str, str]:
    """Conservatively bucket developer-catalog discoveries for human review."""
    if package_id in USER_CONFIRMED_BED_APPS:
        return "likely_bed_app", "user-confirmed bed app"
    if package_id in USER_CONFIRMED_NON_BED_APPS:
        if package_id.startswith("com.sbi."):
            return "not_bed_app", "user-confirmed Wi-Fi-only exclusion"
        return "not_bed_app", "user-confirmed non-bed app"

    value = f"{package_id} {title}".lower()
    exclusions = {
        "desk": "desk/workplace controller",
        "wheelchair": "wheelchair controller",
        "programmer": "service/programming utility",
        "catalog": "product catalog",
        "vetremote": "animal warmer controller",
        "pillow": "pillow controller",
        "recliner": "recliner controller",
        "sofa": "sofa controller",
        "myofficemate": "office app",
        "standuppls": "standing reminder",
        "motti": "non-bed TiMOTION app",
    }
    for token, reason in exclusions.items():
        if token in value:
            return "not_bed_app", reason

    indicators = (
        "adjustable",
        "base",
        "bed",
        "betten",
        "comfy",
        "dorsal",
        "ergobalance",
        "flexsteel",
        "komfy",
        "mattress",
        "motion",
        "relax",
        "saatva",
        "simmons",
        "sleep",
        "tempur",
        "zero-g",
        "zerog",
    )
    if any(token in value for token in indicators):
        return "likely_bed_app", "package or title contains a bed-control indicator"
    return "needs_review", "developer catalog match without a decisive title indicator"


def normalize_architectures(value: str) -> str:
    """Normalize comma/semicolon architecture lists from store metadata."""
    architectures = {
        architecture.strip()
        for group in value.split(";")
        for architecture in group.split(",")
        if architecture.strip()
    }
    return "; ".join(sorted(architectures))


def load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def keyed(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {record["package_id"]: record for record in records}


def merge_play(
    primary: list[dict[str, Any]],
    regional_paths: list[Path],
) -> dict[str, dict[str, Any]]:
    merged = keyed(primary)
    for path in regional_paths:
        for regional in load_json(path):
            current = merged[regional["package_id"]]
            for field in ("status", "availability", "error"):
                if regional.get(field):
                    current[field] = regional[field]
    return merged


def latest_rows(
    local_rows: list[dict[str, str]],
    play: dict[str, dict[str, Any]],
    apkpure: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for local in sorted(local_rows, key=lambda item: item["package_id"]):
        package_id = local["package_id"]
        play_record = play.get(package_id, {})
        apkpure_record = apkpure.get(package_id, {})
        classification, cross_check, blocker = classify(
            local["latest_local_version_name"],
            local["latest_local_version_code"],
            play_record,
            apkpure_record,
        )

        if cross_check == "version_mismatch" and play_record.get("version"):
            latest_version_name = str(play_record.get("version", ""))
            latest_version_code = ""
            latest_release_date = str(play_record.get("updated", ""))
            latest_architectures = ""
            latest_source = "Google Play (APKPure mismatch)"
        elif apkpure_record.get("status") == "available":
            latest_version_name = str(apkpure_record.get("version_name", ""))
            latest_version_code = str(apkpure_record.get("version_code", ""))
            latest_release_date = str(apkpure_record.get("release_date", ""))
            latest_architectures = normalize_architectures(
                str(apkpure_record.get("architectures", ""))
            )
            latest_source = "APKPure"
        else:
            latest_version_name = str(play_record.get("version", ""))
            latest_version_code = ""
            latest_release_date = str(play_record.get("updated", ""))
            latest_architectures = ""
            latest_source = "Google Play" if latest_version_name else ""

        rows.append(
            {
                "package_id": package_id,
                "application_names": local["application_names"],
                "local_version_name": local["latest_local_version_name"],
                "local_version_code": local["latest_local_version_code"],
                "local_architectures": local["architectures"],
                "play_status": str(play_record.get("status", "")),
                "play_version": str(play_record.get("version", "")),
                "play_updated": str(play_record.get("updated", "")),
                "play_developer": str(play_record.get("developer", "")),
                "play_url": str(play_record.get("url", "")),
                "play_availability": json.dumps(
                    play_record.get("availability", {}), sort_keys=True
                ),
                "apkpure_status": str(apkpure_record.get("status", "")),
                "apkpure_version_name": str(apkpure_record.get("version_name", "")),
                "apkpure_version_code": str(apkpure_record.get("version_code", "")),
                "apkpure_release_date": str(apkpure_record.get("release_date", "")),
                "apkpure_architectures": normalize_architectures(
                    str(apkpure_record.get("architectures", ""))
                ),
                "apkpure_url": str(apkpure_record.get("url", "")),
                "latest_version_name": latest_version_name,
                "latest_version_code": latest_version_code,
                "latest_release_date": latest_release_date,
                "latest_architectures": latest_architectures,
                "latest_source": latest_source,
                "cross_check": cross_check,
                "classification": classification,
                "blocker": blocker,
                "lookup_date": date.today().isoformat(),
            }
        )
    return rows


def discovered_rows(
    catalogs: list[dict[str, Any]],
    known_packages: set[str],
    play: dict[str, dict[str, Any]] | None = None,
    apkpure: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    play = play or {}
    apkpure = apkpure or {}
    rows: list[dict[str, str]] = []
    for catalog in catalogs:
        for app in catalog.get("apps", []):
            package_id = app.get("package_id", "")
            if not package_id or package_id in known_packages:
                continue
            relevance, reason = discovery_relevance(package_id, app.get("title", ""))
            play_record = play.get(package_id, {})
            apkpure_record = apkpure.get(package_id, {})
            play_version = str(play_record.get("version", ""))
            apkpure_version = str(apkpure_record.get("version_name", ""))
            if play_version and apkpure_version:
                cross_check = "matched" if play_version == apkpure_version else "version_mismatch"
            elif play_version:
                cross_check = "google_play_only"
            elif apkpure_version:
                cross_check = "apkpure_only"
            else:
                cross_check = "no_version_metadata"
            if cross_check == "version_mismatch":
                latest_version = play_version
                latest_code = ""
                blocker = f"Google Play reports {play_version}; APKPure reports {apkpure_version}"
            elif apkpure_version:
                latest_version = apkpure_version
                latest_code = str(apkpure_record.get("version_code", ""))
                blocker = ""
            else:
                latest_version = play_version
                latest_code = ""
                blocker = "" if latest_version else "no version metadata available"
            rows.append(
                {
                    "package_id": package_id,
                    "title": app.get("title", ""),
                    "developer": catalog.get("developer", ""),
                    "developer_id": catalog.get("developer_id", ""),
                    "play_url": app.get("url", ""),
                    "relevance": relevance,
                    "reason": reason,
                    "play_status": str(play_record.get("status", "")),
                    "play_version": play_version,
                    "play_updated": str(play_record.get("updated", "")),
                    "apkpure_status": str(apkpure_record.get("status", "")),
                    "apkpure_version_name": apkpure_version,
                    "apkpure_version_code": str(apkpure_record.get("version_code", "")),
                    "apkpure_release_date": str(apkpure_record.get("release_date", "")),
                    "apkpure_architectures": normalize_architectures(
                        str(apkpure_record.get("architectures", ""))
                    ),
                    "apkpure_url": str(apkpure_record.get("url", "")),
                    "latest_version_name": latest_version,
                    "latest_version_code": latest_code,
                    "cross_check": cross_check,
                    "blocker": blocker,
                }
            )
    return sorted(rows, key=lambda item: item["package_id"])


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_readme(path: Path, rows: list[dict[str, str]], discoveries: list[dict[str, str]]) -> None:
    classifications = Counter(row["classification"] for row in rows)
    play_statuses = Counter(row["play_status"] for row in rows)
    apkpure_statuses = Counter(row["apkpure_status"] for row in rows)
    relevance = Counter(row["relevance"] for row in discoveries)
    table = "\n".join(
        f"| {name} | {count} |" for name, count in sorted(classifications.items())
    )
    discovery_table = "\n".join(
        f"| {name} | {count} |" for name, count in sorted(relevance.items())
    )
    path.write_text(
        f"""# APK latest-version audit

Cutoff date: **{date.today().isoformat()}**. The local baseline is the 217-package inventory in
`../2026-07-14-apk-inventory/packages.csv`.

## Outcome

| Classification | Packages |
|---|---:|
{table}

Google Play status counts: `{dict(sorted(play_statuses.items()))}`.
APKPure status counts: `{dict(sorted(apkpure_statuses.items()))}`.

`latest_versions.csv` contains one row per local package, including local metadata, both source
records, the resolved latest version, architecture variants, source URLs, lookup date, and any
blocker. `google_play.json`, `google_play_regional*.json`, and `apkpure.json` preserve the raw
normalized evidence used to build it.

## Classification rules

- `current`: the local versionName or APKPure versionCode matches the latest verified metadata.
- `outdated`: APKPure exposes a higher numeric versionCode than the local archive.
- `removed`: neither APKPure nor any of the seven probed Play markets has a listing.
- `region restricted`: Play exposes a listing but no probed market supplied version metadata,
  and APKPure has no usable listing.
- `unavailable`: a store listing exists but a corresponding APK source is unavailable.
- `unverifiable`: sources conflict, metadata parsing failed, or version ordering cannot be proven.

Google Play does not publicly expose versionCode, so numeric currency comparisons use APKPure.
When Play and APKPure versionName values disagree, the row is deliberately `unverifiable`.

## Developer-catalog refresh

The 28 Google Play developer catalogs associated with live baseline apps returned 136 apps.
`discovered_packages.csv` records {len(discoveries)} package IDs absent from the local inventory:

| Relevance | Packages |
|---|---:|
{discovery_table}

The relevance field includes explicit user-confirmed overrides and conservative title-based
fallbacks. It prevents unrelated desk, wheelchair, recliner, and catalog apps from being silently
treated as adjustable-bed APKs.

APKPure's developer and search pages returned Cloudflare 403 responses, and the signed-in browser
session was not permitted to automate those routes. Individual package lookups remained available
through APKPure's stable `/app/<package-id>` redirect, so every baseline package was checked there.
Google Play developer catalogs provide the reproducible discovery substitute; the blocked APKPure
catalog refresh is documented rather than treated as successful.

## Reproduction

```bash
(cd tools/google_play_inventory && go run . -input ../../docs/reanalysis/2026-07-14-apk-inventory/packages.csv -output ../../docs/reanalysis/2026-07-14-apk-latest-versions/google_play.json -fallback-countries "" -throttle 300ms)
(cd tools/google_play_inventory && go run . -input ../../docs/reanalysis/2026-07-14-apk-latest-versions/google_play.json -input-statuses not_found,not_in_region -output ../../docs/reanalysis/2026-07-14-apk-latest-versions/google_play_regional.json -fallback-countries no,gb,de,ca,au,jp -throttle 300ms)
(cd tools/google_play_inventory && go run . -discover-developers -input ../../docs/reanalysis/2026-07-14-apk-latest-versions/google_play.json -output ../../docs/reanalysis/2026-07-14-apk-latest-versions/google_play_developers.json -throttle 300ms)
python tools/apkpure_inventory.py --input docs/reanalysis/2026-07-14-apk-inventory/packages.csv --output docs/reanalysis/2026-07-14-apk-latest-versions/apkpure.json --throttle 0.1
python tools/apk_latest_report.py --play-regional docs/reanalysis/2026-07-14-apk-latest-versions/google_play_regional.json
```

The first report pass creates `discovered_packages.csv`. Run the two inventory helpers against
that CSV to refresh `discovered_google_play.json` and `discovered_apkpure.json`, then run the report
command once more to merge their latest-version metadata.

The Go helper pins `github.com/kryuchenko/google-play-scraper` and adds a tested raw-page fallback
for version/update fields currently missed by the upstream parser.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local",
        type=Path,
        default=Path("docs/reanalysis/2026-07-14-apk-inventory/packages.csv"),
    )
    parser.add_argument(
        "--play",
        type=Path,
        default=Path("docs/reanalysis/2026-07-14-apk-latest-versions/google_play.json"),
    )
    parser.add_argument(
        "--play-regional",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument(
        "--apkpure",
        type=Path,
        default=Path("docs/reanalysis/2026-07-14-apk-latest-versions/apkpure.json"),
    )
    parser.add_argument(
        "--developers",
        type=Path,
        default=Path("docs/reanalysis/2026-07-14-apk-latest-versions/google_play_developers.json"),
    )
    parser.add_argument(
        "--discovered-play",
        type=Path,
        default=Path(
            "docs/reanalysis/2026-07-14-apk-latest-versions/discovered_google_play.json"
        ),
    )
    parser.add_argument(
        "--discovered-apkpure",
        type=Path,
        default=Path("docs/reanalysis/2026-07-14-apk-latest-versions/discovered_apkpure.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/reanalysis/2026-07-14-apk-latest-versions"),
    )
    args = parser.parse_args()

    with args.local.open(newline="", encoding="utf-8") as file:
        local_rows = list(csv.DictReader(file))
    play = merge_play(load_json(args.play), args.play_regional)
    apkpure = keyed(load_json(args.apkpure))
    discoveries = discovered_rows(
        load_json(args.developers),
        {row["package_id"] for row in local_rows},
        keyed(load_json(args.discovered_play)) if args.discovered_play.exists() else {},
        keyed(load_json(args.discovered_apkpure)) if args.discovered_apkpure.exists() else {},
    )
    rows = latest_rows(local_rows, play, apkpure)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "latest_versions.csv", LATEST_FIELDS, rows)
    write_csv(args.output_dir / "discovered_packages.csv", DISCOVERY_FIELDS, discoveries)
    write_readme(args.output_dir / "README.md", rows, discoveries)


if __name__ == "__main__":
    main()
