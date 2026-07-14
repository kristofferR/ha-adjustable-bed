# APK acquisition and verification (2026-07-14)

This is the phase 3 analysis-corpus manifest for issue #436. It selects one latest
artifact for every baseline package and every newly discovered likely BLE bed app.
Wi-Fi-only and unrelated discoveries remain excluded by the phase 2 classification.

## Artifacts

- `acquisition.csv`: one selected artifact or exact blocker per package.
- `files.csv`: one row per APK or embedded split, with hashes, signatures, resource
  counts, native-library counts, ABIs, and Flutter `libapp.so` ABIs.
- Selected raw downloads remain byte-for-byte untouched under the gitignored
  acquisition directory; redundant non-arm64 acquisition attempts are not retained.

## Acquisition tool

Downloads use [`apkeep` 1.0.0](https://github.com/EFForg/apkeep/releases/tag/1.0.0), pinned to the
x86_64 Linux asset SHA-256 `a23579a3ba366d25a6d69848189b983d65662f4ecf4b9e11e16510811659de4e`. Its release signature was
verified against PGP fingerprint `1073E74EB38BD6D19476CBF8EA9DBF9FB761A677` before use.
APKPure requests pin the expected version and prefer arm64-v8a when advertised.
When APKPure exposes an exact architecture variant, its recorded artifact URL is
downloaded directly with retry/resume support because apkeep 1.0.0 can return the
armv7 artifact for an arm64 request. The resulting archive receives the same checks.
Google Play requests ask for all split APKs and use a local credential file; no
credential or token is written to these reports.

## Verification

- Package ID, `versionName`, and APKPure `versionCode` are read from the APK itself.
- Google Play does not expose `versionCode` in its web metadata, so Play downloads
  verify the expected `versionName` and record the embedded `versionCode` afterward.
- SHA-256 is recorded for the original APK/XAPK and every embedded split. Google Play
  split sets use a deterministic set hash over sorted member paths and member hashes.
- Every APK signature is checked with `apksigner`; signer certificate SHA-256 digests
  are recorded without modifying the files.
- Every XAPK or Play split is opened and counted for resources and native libraries.
- Flutter is detected only from `lib/<abi>/libapp.so`. A latest Flutter artifact without
  arm64-v8a is blocked explicitly, with any older local arm64 fallback recorded separately.

## Summary

| Metric | Count |
|---|---:|
| In-scope packages | 252 |
| Baseline packages | 217 |
| Newly discovered likely BLE apps | 35 |
| Reused current local artifacts | 158 |
| Downloaded and verified artifacts | 91 |
| Validation errors | 0 |
| Flutter arm64 blockers | 0 |
| Source/delivery blockers | 3 |
| APKPure downloads selected | 41 |
| Google Play primary selections | 50 |
| Flutter arm64 Play fallbacks selected | 3 |
| Flutter artifacts detected | 66 |
| APK/split file rows | 1845 |

## Remaining blockers

| Package | Status | Detail |
|---|---|---|
| `com.keeson.junasleep` | blocked | Google Play reports 1.0.3; APKPure reports 1.0.1; Google Play returned no APK/XAPK for the requested latest build and emitted no diagnostic |
| `com.saatva` | blocked | Google Play returned no APK/XAPK for the requested latest build and emitted no diagnostic |
| `com.selectcomfort.SleepIQ` | blocked | Google Play version differs, but Play does not expose versionCode; Google Play returned no APK/XAPK for the requested latest build and emitted no diagnostic |

## Reproduce

Run from the repository root after installing `aapt`, `apksigner`, and the pinned
`apkeep` release. Google Play is optional until a local `apkeep.ini` is configured:

```bash
python3 tools/apk_acquisition.py \
  --google-play-ini ~/.config/apkeep/apkeep.ini
```

Raw download directory: `disassembly/apk/not-analyzed/acquired-2026-07-14`.
