# APK latest-version audit

Cutoff date: **2026-07-14**. The local baseline is the 217-package inventory in
`../2026-07-14-apk-inventory/packages.csv`.

## Outcome

| Classification | Packages |
|---|---:|
| current | 159 |
| outdated | 30 |
| unverifiable | 28 |

Google Play status counts: `{'available': 187, 'not_found': 24, 'not_in_region': 1, 'region_restricted': 5}`.
APKPure status counts: `{'available': 201, 'removed': 15, 'unavailable': 1}`.

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
`discovered_packages.csv` records 56 package IDs absent from the local inventory:

| Relevance | Packages |
|---|---:|
| likely_bed_app | 35 |
| not_bed_app | 21 |

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
