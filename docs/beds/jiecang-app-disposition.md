# ERGOBALANCE and Dream Motion app protocol

This is the implementation disposition for Phase 4 row020, formal cluster-004,
against `release/4.0`. The bed type `jiecang_app` provides the app-derived protocol
through explicit app-profile and actuator-layout selections. The existing
`jiecang` controller remains separate: shared service UUIDs alone do not identify
an app profile or establish that a legacy configuration should be migrated.

**Hardware status:** artifact-proven, physical operation unverified. The reports
are COMPLETE; hardware validation is deferred to users after beta or release.

## Accepted evidence and cluster gate

The entire cluster contains these two packages. Both reports were accepted and
independently audited on 2026-08-27 in [#443](https://github.com/kristofferR/ha-adjustable-bed/issues/443).
They are reused without modification or another APK analysis.

| Package | Version | Accepted route | Artifact-set SHA-256 | Report manifest SHA-256 |
|---|---|---|---|---|
| `com.jiecang.dreamask.app.android.bed` (ERGOBALANCE) | 1.0.8 (8), five APK members | FULL representative | `d5ec3d4de0eafdffc6400f730c7f11285469a7b626a4aea50be66514d730114a` | `6b1e45e85fed47bc73e29a159a24a27ec2340de0b3f3186ed65ce8c5e172646f` |
| `com.jiecang.dreamotion.app.android.bed` (Dream Motion) | 1.0.5 (11), four APK members | DELTA route promoted to FULL | `bbc25698c039d1b0c7451ef78e97133c34c0403856c470987d7f41beccd73ebf` | `b2e6b34638d893b4f366dacd22835b6b804f3661299c31cd50d319e7c05d6cf6` |

The accepted `analysis.json` hashes are respectively
`bdb5bb81cb29d2fa1b8b1f4880e350d512925ccba7473f85a09ddedc1b3345a9` and
`21d49393849988197880538247feeaa1205fd8a97c9dc0795683f494fcf9dd31`.
The Dream Motion Stage 1 seal is
`865c601dc0f9f0d9614d3253901a52374c59379fea359852289e93991b02812e`.
Its frozen chronology verifies independent Stage 1, local verification of the
accepted representative, FULL reconciliation, then the final freeze.

Both reports pass all 17 completion gates with no artifact-analysis blockers.
ERGOBALANCE accounts for 42 layout-qualified command rows and 196 vectors; Dream
Motion accounts for 58 command rows and 202 vectors. Different row counts reflect
different grouping granularity, not 16 commands unique to Dream Motion.

The source evidence remains machine-local under
`disassembly/output/phase4-early/<package>-<version>-20260827/report/`.
The durable references are `ANALYSIS.md`, `analysis.json`,
`ledgers/command-ledger.tsv`, `ledgers/selector-wire-matrix.tsv`,
`ledgers/notification-ledger.tsv`, and, for Dream Motion,
`ledgers/representative-delta.tsv`. Raw artifacts and frozen reports are not
distributed with the integration.

## Profile, layout and transport selection

Select profile `dreamask` for ERGOBALANCE or `dreamotion` for Dream Motion. Profile
controls the proven release lifecycle; layout controls packet routing. They are
independent of the discovered GATT service layout.

| Layout | App-level control intent |
|---|---|
| `standard_2` | Back, legs and their combined movement |
| `standard_3_neck` | Back, legs and neck |
| `standard_3_lumbar` | Back, legs and lumbar |
| `standard_3_hi_low` | Back, legs and height |
| `standard_3_split_upper` | Left/right upper sections, combined upper sections and legs |
| `standard_4_legacy` | Back, legs, head and lumbar |
| `standard_4_bilateral` | Independent left/right head and foot sections, plus paired head/foot controls |
| `split_series` | Split upper sections using standard movement and global commands |
| `split_after_bilateral` | Split-series movement with the persisted bilateral global-command route |

The first eight are the app's stable layouts. The ninth explicitly represents a
reachable app state: selecting split-series writes only `BedSeries=2` and retains
the previous four-motor/bilateral fields. Its movement stays standard while
presets and massage use bilateral commands. The integration exposes this state
deliberately rather than depending on the history of an Android preferences file.
Optional light and massage settings remain independent capability choices.

| Transport | Service | Write / notify / name roles | Reachability |
|---|---|---|---|
| G1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `ff01` / `ff02` / `ff06`, using the same Bluetooth base UUID | Discoverable in both apps |
| G3 | `0000fe60-0000-1000-8000-00805f9b34fb` | `fe61` / `fe62` / `fe63`, using the same Bluetooth base UUID | Discoverable in both apps |
| G2 | `88121427-11e2-52a2-4615-ff00dec16800` | Bidirectional `88121427-11e2-52a2-4615-ff00dec16801`; no name role | Co-present route in both apps; standalone exact-MAC connection only in Dream Motion |

The apps discover G1 for two seconds, pause for one second and discover G3 for two
seconds. Neither has an app-derived name/manufacturer matcher or standalone G2
scan. Home Assistant supplies scanning and connection management. A shared UUID
does not justify silently changing an existing bed to `jiecang_app`.

## Whole-cluster command disposition

All reachable packet and control families are implemented for `jiecang_app`.
The table covers every command row in both accepted ledgers. `E` and `D` refer to
ERGOBALANCE and Dream Motion, respectively; row numbers are one-based data rows,
excluding the TSV header. Paired up/down actions can occupy one E row and two D
rows. The feature names describe integration behavior rather than Android widget
names.

| Accepted command rows | Disposition | Integration behavior |
|---|---|---|
| E1-6; D49-54 | Implemented | Software, light, actuator, hardware, vibration and alarm queries; G1/G3 initialization follows the recorded query schedule after subscription |
| E7-9; D1-6 | Implemented | Standard back, legs and combined movement with 100 ms held-command cadence |
| E10-15; D32-37 | Implemented | All six bilateral movement pairs with two-byte `00 00` payloads |
| E30-31; D7-10 | Implemented | Layout-selected neck/height and lumbar auxiliary movement |
| E32-33; D11-14 | Implemented | Right and combined split-upper movement |
| E16-17; D15-17, D38-40 | Implemented | Flat, zero gravity and anti-snore with standard or bilateral payloads and discrete-action release |
| E18; D19, D21 | Implemented | Save memory A/B with two-byte zero payload and three writes at 0/30/60 ms |
| E19; D20, D22, D42 | Implemented | Recall memory A/B with two-byte zero payload and long release at +800 ms |
| E20; D23, D43 | Implemented | Light toggle following dynamic state at +150 ms, with both release forms at +230 ms total |
| E21-22; D30, D47 | Implemented | Standard/alarm and bilateral massage stop payloads remain distinct |
| E23-25; D26-28 | Implemented | Back/left, foot and right-back standard intensity; UI levels 0/1/2/3 map to wire values 0/2/3/4 |
| E26-27; D44-45 | Implemented | Bilateral left/right intensity uses the two-byte zero-prefixed route and long release at +800 ms |
| E28-29; D29, D46 | Implemented | Standard and bilateral massage mode frames with long release at +1000 ms |
| E34; D18, D41 | Implemented | Yoga preset; software capability controls availability |
| E35; D25 | Implemented | Automatic/human-sensing light toggle and reported state, gated by capability and layout |
| E36-37; D31, D48 | Implemented | Both artifact-defined release frames with action/profile-specific timing and cancellation cleanup |
| E38; D55 | Implemented | Current-clock frame in response to the clock-request notification |
| E39; D56 | Implemented | Native alarm configuration, including weekday mask, wake choice and massage levels; wake execution is separately callable for HA scheduling |
| E40; D24 | Implemented | Dynamic B/G/R, brightness, timeout and on/off state |
| E41; D57 | Implemented | Raw ASCII G1 rename, written twice at 0/+500 ms |
| E42; D58 | Implemented | Framed G3 rename, written twice at 0/+500 ms |

Requests use `F1 F1 | opcode | payload length | payload | checksum | 7E`, where
the checksum is the low byte of the sum from opcode through payload. Standard
movement typically uses payload `01`; bilateral movement uses `00 00`. Memory,
Yoga and light commands retain their own proven payloads regardless of layout.
The short release is `F1 F1 4E 00 4E 7E`; the long release is
`F1 F1 4E 02 00 00 50 7E`.

The light toggle's dynamic frame contains the **desired inverse** of the latest
reported on/off state, followed by the separate toggle packet. A narrow
post-freeze comparison on 2026-09-08 resolved this assignment from the already
accepted ERGOBALANCE source, without changing the frozen report:
`work/jadx-base/sources/com/dreamask/app/android/dreamask/MainActivity.java`,
SHA-256 `fc5b0d7c14851a3c91d7fe9f18b7a67d117f645c6ac5567d977dfebd9aef2e2e`,
`initialViewControl`, lines 5183-5204. Line 5187 maps saved `00` to `01` and every
other saved state to `00`; line 5188 uses that value in the dynamic payload and
checksum; lines 5189-5202 define the subsequent toggle/release schedule. The
integration therefore uses the latest unified light status, including legacy
opcode-05/06 updates, while preserving the separately reported RGB and timer.
The same narrow comparison confirmed the identical assignment and schedule in
the accepted Dream Motion source:
`work/stage1/jadx-authoritative/sources/com/dreamotion/app/android/dreamotion/MainActivity.java`,
SHA-256 `481c4becfcafb013f0f8c5968b2d5db74e91c8df42033ecf902eb4d0ee704014`,
`initialViewControl`, lines 5092-5113. Line 5096 computes the desired inverse,
line 5097 uses it in the frame, and lines 5098-5111 schedule the remaining writes.

Alarm wake execution preserves the recorded five wake-command copies at
+800/+830/+860/+890/+920 ms and long releases at +1690/+1720 ms. Standard-series
memory B also releases at +1600 ms. Massage alarm operations retain the three
commands and three short releases at 30 ms intervals. A HA automation can invoke
the wake operation. Split-series alarm execution couples right-side intensity to
the back intensity, as the right sequence belongs to the same accepted branch;
it does not provide an independent right-side alarm setting. The Android
application's local timer and broadcast scheduler
are not required. Yoga can be stored in the native alarm packet as wake code
`06`, but neither accepted app dispatches a Yoga wake action. The integration
does not invent that missing executor.

## Eleven-row representative reconciliation

The accepted reconciliation has one analysis-route row, six material behavior
differences and four explicitly shared domains. It is not eleven distinct
protocol differences.

| Domain | Accepted evidence | Implementation disposition |
|---|---|---|
| Analysis route | Dream Motion required FULL promotion | Already complete and independently accepted before implementation |
| Final repeat sentinel | ERGOBALANCE suppresses `-1`; Dream Motion sends a final movement/flat command | App-specific lifecycle is explicit; cancellation never adds another movement command |
| Touch-release dispatch | ERGOBALANCE uses `onRelease`; Dream Motion owns cleanup in movement touch listeners | Profile-specific movement cleanup is implemented without an Android widget dependency |
| Key-release cleanup | ERGOBALANCE cleans up; Dream Motion sends its final command without cleanup | Missing cleanup is excluded as an Android input-path defect; HA movement always runs release cleanup |
| Movement cleanup timing | ERGOBALANCE long releases +50/+150 ms; Dream Motion short +100 ms and long +800 ms | Both schedules are implemented by profile |
| Flat hold release | ERGOBALANCE suppresses final repeat; Dream Motion sends it; neither hold path releases | Discrete flat preserves the proven click/+800 ms release path; unsafe hold cleanup omission is excluded |
| Standalone G2 | Dream Motion can connect a persisted exact MAC without a ready bootstrap; ERGOBALANCE requires co-presence | Profile-specific reachability and bootstrap behavior are preserved |
| Packet builders | Standard envelope, bilateral payloads, dynamic light, clock, alarm and rename agree | Shared typed builders implement both members |
| Split persistence | Both retain stale motor/type fields | Explicit `split_after_bilateral` represents the reachable packet route |
| G1/G3 co-presence | Ready flags accumulate; last characteristic wins; rename encoding tests G1 first | Each selected service keeps its matching write/notify/name roles and name encoding; cross-service overwrite, duplicate readiness bursts and descriptor races are excluded |
| Parsers | Both accept family-specific minimum lengths and partial alarm messages | Shared bounded parsing preserves meaningful state; malformed fields cannot crash the notification callback |

## Notifications and capability disposition

Implemented notification handling covers clock requests, software capability,
hardware/layout responses, alarm visibility/configuration, dynamic light,
automatic-light state and legacy massage/light state. There is no position,
angle or height feedback in either accepted artifact, so this route must not
create position feedback or target-position entities.

The app's parser operates on complete notification callbacks. In particular,
opcode `05`/`06` legacy status accepts an arbitrary two-byte header when at least
nine bytes are available. The light family needs 13 bytes. Alarm messages of
7-13 bytes expose alarm availability without full fields; full parsing needs 14.
The integration guards field bounds and unsupported values, while avoiding an
invented checksum/trailer requirement that would reject accepted app traffic.

Yoga uses the reported software capability; automatic/color lighting also obeys
the layout gate, including the bilateral and mixed split route. Reported massage
values do not justify exposing unreachable intensity controls.

## Exclusions and deferred validation

| Finding | Disposition and reason |
|---|---|
| Android `ACTION_CANCEL` and Dream Motion key-up omit cleanup | Excluded defect; HA cancellation sends the proven release with a fresh cancellation token |
| Repeated ready broadcasts and writing before CCCD completion | Excluded Android service-loop/race behavior; HA subscribes before a serialized initialization sequence |
| G1-first raw rename sent to a last-selected G3 name characteristic | Excluded cross-service routing defect; selecting G1 or G3 retains that service's matching name characteristic and encoding |
| Android color-picker drag callbacks, configuration-screen refreshes and local alarm broadcasts | Excluded UI scheduling mechanisms; direct light configuration, queries, alarm configuration and wake execution provide the useful operations |
| Stale Android preference history | Persistence mechanism excluded; its concrete mixed packet route is implemented explicitly |
| Invalid notification parsing exceptions or stale unknown alarm choice | Excluded defects; bounded parsing rejects unusable fields without crashing or inventing state |
| Definition-only memory C, extra intensity constants, timer/reset/start paths | Excluded unreachable code; two callable memory slots and the reachable UI intensity range are exposed |
| Connected-login UUID comparison/retained field and unused read wrapper | Excluded dead paths; no authentication or read transaction is invented |
| GIF native library | Excluded unrelated third-party decoder |
| Classic Bluetooth, cloud/Wi-Fi control, PIN/bonding/authentication, OTA/DFU, firmware/EEPROM, position control | Excluded absent domains after accepted artifact searches |

Physical validation should confirm actuator mapping for each layout, especially
the bilateral right-foot UI whose internal builder is named right-back; runtime
GATT characteristic properties and service order; and movement release, mixed
split routing, alarms and lighting. These are deferred hardware checks, not a
reason to repeat the accepted analysis or claim that hardware has been tested.

Ref [#436](https://github.com/kristofferR/ha-adjustable-bed/issues/436),
[#443](https://github.com/kristofferR/ha-adjustable-bed/issues/443) and
[#447](https://github.com/kristofferR/ha-adjustable-bed/issues/447).
