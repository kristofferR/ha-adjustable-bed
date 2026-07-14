# Local APK inventory (2026-07-14)

This is the step 1 baseline for the clean-room APK re-analysis in issue #436.
It inventories the local corpus only; upstream latest-version discovery is step 2.

## Artifacts

- `archives.csv`: one row per local APK/XAPK archive, including embedded metadata, hashes, splits, architectures, duplicate annotations, warnings, and failures.
- `packages.csv`: one normalized row per resolved package ID, including every local version and source path.

## Method

- APK package/version/SDK/application metadata comes from `aapt dump badging`.
- XAPK container metadata comes from `manifest.json` and is cross-checked against the embedded base APK with `aapt`.
- CPU architectures come from APK native-code metadata and XAPK split identifiers.
  A blank architecture field means no native-code ABI or ABI split was declared.
- An SDK value of `not declared` means the archive does not declare that field.
- SHA-256 is calculated over each original archive.
- Filenames are retained only as source paths and are never treated as metadata.
- No archives were moved or deleted. All older versions remain preserved.

## Summary

| Metric | Count |
|---|---:|
| Local archives accounted for | 242 |
| APK archives | 105 |
| XAPK archives | 137 |
| Resolved package IDs | 217 |
| Distinct package/version records | 223 |
| Packages with multiple local versions | 4 |
| Exact duplicate SHA-256 groups | 15 |
| Repeated package/version groups | 18 |
| Complete metadata rows | 239 |
| Partial metadata rows | 2 |
| Extraction failures | 1 |

## Incomplete or failed extraction

| Status | Source path | Detail |
|---|---|---|
| partial | `disassembly/apk/analyzed/limossRemote_7.1.8_com.limoss.limossremote.xapk` | aapt failed: AndroidManifest.xml:51: error: ERROR getting 'android:icon' attribute: attribute value reference does not exist |
| partial | `disassembly/apk/analyzed/Relax Motion_1.5.0_com.motion.rmtrelax.xapk` | aapt failed: AndroidManifest.xml:123: error: ERROR getting 'android:icon' attribute: attribute value reference does not exist |
| error | `disassembly/apk/analyzed/richmat/com.richmat.xapk` | invalid ZIP container (missing or corrupt central directory) |

## Packages with multiple local versions

| Package | Versions |
|---|---|
| `com.desarketing.gmmotor` | 3.0.5 (8); 3.0.33 (36); 4.6.0 (46001) |
| `com.keeson.purpleBase` | 1.0.7 (20); 1.0.8 (23) |
| `com.leggett.android.universal` | 2.6.0 (39218); 2.9.0 (46164) |
| `de.octoactuators.octosmartcontrolapp` | 1.1.57 (10157); 1.03.00 (10300); 1.03.01 (10301) |

## Exact duplicate files

| SHA-256 | Source paths |
|---|---|
| `8042f82558322f849bca5cfe7188b3d715abc939abecbf53d736311281e2a4fd` | `disassembly/apk/analyzed/Adjustable bed_1.1_com.okin.bedding.adjustbed.xapk`<br>`disassembly/apk/analyzed/dewertokin/com.okin.bedding.adjustbed.xapk` |
| `a04d3f972fcc031b607143f4a2034e54955ca4a4c4e806b003c27fbcbd5e30b7` | `disassembly/apk/analyzed/BetterLiving-1_1.2.5_APKPure.xapk`<br>`disassembly/apk/analyzed/dewertokin/com.ore.betterliving2.xapk` |
| `2d21d42c17a7b5ae60c2403ff3654d80993e6d09f879cfe666c6d58270123f8b` | `disassembly/apk/analyzed/Casper Base_1.0.8_APKPure.xapk`<br>`disassembly/apk/analyzed/richmat/com.richmat.casperbase.xapk` |
| `26a33ef79aa50f0b899d934c01aad8641b97da58bd9b78134122ac56d33eeaa9` | `disassembly/apk/analyzed/dewertokin/com.okin.bedding.rizeResident.apk`<br>`disassembly/apk/analyzed/Resident Adjustable Bed_1.0.1_com.okin.bedding.rizeResident.apk` |
| `a4f5ae67b2b9b870e6413d08597364041ac6947c7ba5445eb1979498895ff46f` | `disassembly/apk/analyzed/dewertokin/com.okin.bedding.rizemf900.xapk`<br>`disassembly/apk/analyzed/Mattress Firm 900 - O_1.1.2_com.okin.bedding.rizemf900.xapk` |
| `3f0c9d6bccbde12dd86293c8834e8925cfae6b8360b0e3bc8671577527baea53` | `disassembly/apk/analyzed/dewertokin/com.okin.bedding.sleepy.xapk`<br>`disassembly/apk/analyzed/MFRM Sleepy's Elite_1.1.4_com.okin.bedding.sleepy.xapk` |
| `9258b9011be191008d0fd4c5d667e82bf214db4d118918dbbb0c51f185f7ff07` | `disassembly/apk/analyzed/dewertokin/com.okin.bedding.smartbedwifi.xapk`<br>`disassembly/apk/analyzed/OKIN Smart Bed_2.2.0_com.okin.bedding.smartbedwifi.xapk` |
| `583dd003df0478419935bb1c6649a8e8b0228988e0b38b12c6919efa275e85f7` | `disassembly/apk/analyzed/dewertokin/com.okin.resident.release.apk`<br>`disassembly/apk/analyzed/Resident Adjustable Base_1.0.0_com.okin.resident.release.apk` |
| `95964d51b74d4431344cca94054f024a807be10d78b2fad3eeec48c797122c8b` | `disassembly/apk/analyzed/dewertokin/com.ore.jalon.neworebeding.xapk`<br>`disassembly/apk/analyzed/OKIN ComfortBed II-N_2.0.2_com.ore.jalon.neworebeding.xapk` |
| `57993119d540fbf7361a67eaa60e01337c7d98a92f6666b2620ae393b179354e` | `disassembly/apk/analyzed/dewertokin/com.ore.okincomfortbed.xapk`<br>`disassembly/apk/analyzed/OKIN Comfort Bed_1.1.4_com.ore.okincomfortbed.xapk` |
| `d46d4bef4be6e62655fc527698e355c938832e72d5a9bfe2ff33904a240ac202` | `disassembly/apk/analyzed/dewertokin/com.ore.sfm.apk`<br>`disassembly/apk/analyzed/INNOVA_2.0_com.ore.sfm.apk` |
| `8ce8d5dc933d5ab2223f66e7dde1199e42f29e544c8a02d9bba54393a3d571a5` | `disassembly/apk/analyzed/dewertokin/com.synergy.okin.xapk`<br>`disassembly/apk/analyzed/Smart Comfort by Synergy_2.2.0_com.synergy.okin.xapk` |
| `74790fb44942e64e9056f79ceb128000e2189f11e2f00d9dfe1c1b03973843f6` | `disassembly/apk/analyzed/richmat/com.richmat.rmcontrol2.xapk`<br>`disassembly/apk/analyzed/RMControl_21.3.2_com.richmat.rmcontrol2.xapk` |
| `7aea9162d751def93eea7631c9d2f713a38cdcb953301279217b2e4075ed68ae` | `disassembly/apk/analyzed/richmat/com.richmat.sleepfunction.apk`<br>`disassembly/apk/analyzed/SleepFunction Bed Control_1.3.0_com.richmat.sleepfunction.apk` |
| `e05889c388e1c8b9aca6668e0688a8e5f85bebcba12044d1750fd5a4d2190dbb` | `disassembly/apk/analyzed/richmat/com.richmat.svenson.apk`<br>`disassembly/apk/analyzed/SVEN & SON_2.0.1_com.richmat.svenson.apk` |

## Repeated package/version metadata

| Package/version | Archives | Distinct files |
|---|---:|---:|
| `com.okin.bedding.adjustbed` 1.1 (27) | 2 | 1 |
| `com.okin.bedding.rizeResident` 1.0.1 (2) | 2 | 1 |
| `com.okin.bedding.rizemf900` 1.1.2 (4) | 2 | 1 |
| `com.okin.bedding.sleepy` 1.1.4 (13) | 2 | 1 |
| `com.okin.bedding.smartbedwifi` 2.2.0 (22) | 2 | 1 |
| `com.okin.resident.release` 1.0.0 (1) | 2 | 1 |
| `com.ore.betterliving2` 1.2.5 (12) | 2 | 1 |
| `com.ore.jalon.neworebeding` 2.0.2 (9) | 2 | 1 |
| `com.ore.okincomfortbed` 1.1.4 (6) | 2 | 1 |
| `com.ore.sfm` 2.0 (3) | 2 | 1 |
| `com.richmat.casperbase` 1.0.8 (10800) | 2 | 1 |
| `com.richmat.mlily0` 3.1.1 (31100) | 2 | 2 |
| `com.richmat.rmcontrol2` 21.3.2 (213203) | 2 | 1 |
| `com.richmat.sleepfunction` 1.3.0 (23) | 2 | 1 |
| `com.richmat.svenson` 2.0.1 (32) | 2 | 1 |
| `com.synergy.okin` 2.2.0 (16) | 2 | 1 |
| `de.octoactuators.octosmartcontrolapp` 1.03.00 (10300) | 2 | 2 |
| `de.vibradorm.vmat` 1.11 (49) | 2 | 2 |

## Reproduce

Run from the repository root in WSL with `aapt` installed:

```bash
python3 tools/apk_inventory.py disassembly/apk docs/reanalysis/2026-07-14-apk-inventory \
  --inventory-date 2026-07-14
```
