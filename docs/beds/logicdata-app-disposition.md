# MOTIONrelax phone and tablet implementation disposition

This records the complete Phase 4 row021, formal cluster-006, implementation
against `release/4.0`. The accepted phone and tablet apps use explicit MOTIONrelax
profiles. Their packet family, configured actuator layout and GATT transport are
separate choices. Existing legacy controllers remain separate; a brand name or
shared service UUID does not establish the appropriate profile.

**Hardware status:** artifact-proven, physical operation unverified. All accepted
analysis is preserved. Hardware checks are deferred to users after beta/release.

## Accepted whole-cluster evidence

The cluster contains exactly these two packages, both independently audited and
accepted on 2026-08-27 in [#443](https://github.com/kristofferR/ha-adjustable-bed/issues/443).

| Package | Version | Accepted route | Canonical artifact-set SHA-256 | Report manifest SHA-256 |
|---|---|---|---|---|
| `com.logicdata.app.android.bed` | 1.0.6 (7), five APK members | FULL representative | `7f44dce68bd051bab9fa43714fb9559fc518a9479796987f5a65f9652984a8eb` | `db627eee378d91f45008482b3f794949ed00276021072b586fbae05c6178252c` |
| `com.logicdata.app.android.pad.bed` | 1.0.4 (5), five APK members | DELTA route promoted to FULL | `0efdbe3f8bb24155bba546ad6d6fd66271f81a446d03024fd66043075fef4f5e` | `7611bf1f29378d51e5600b8f638845d90b2c7a4fe0757186a38c551bcbcc5da1` |

The accepted `analysis.json` hashes are
`edbc95e53e32248c266eaaf4524cd7d7ff058368ba25fabdd634f090ad0c17e9` (phone) and
`b760502e10a02e81d9e8b3cebd36a0368808a75dd1ea98db2223d257b5ec9eff` (tablet).
All four file hashes were checked against the current acceptance registry before
implementation. Both reports pass all 17 completion gates and have zero analysis
blockers. The tablet independently sealed Stage 1 with manifest
`626eebc1da95e9a3cb369808f59cac0ea179101bda15fca398e9003336ef6adc`, then admitted
the verified representative under Stage 2 manifest
`93d3727fdaec3f1a3516e1a15cae7a652f62c970e3efb0271d6417eefcbd1b07`.
Its FULL promotion and all eleven comparison areas are frozen in
`STAGE2_CHECKLIST.json` and confirmed by `QA.txt`.

The phone report has 34 grouped command rows: 24 P1, eight P2 and two rename
rows. Its reproducer reconciles 71 named fixed frames, 12 builders, 22 report
vectors, dynamic/parser models, six GATT counterfactuals, 648 rejected byte
mutations and ten source mutations. The tablet has 89 command rows: 75 fixed
symbol rows, 12 MiddleMotor builders and two renames, with 100 executed vectors
and 87 rejected checksum mutations. Of the 75 fixed symbols, 30 are reachable
and 45 are dead declarations. A dead symbol can contain the same bytes as a
reachable literal callsite, so declaration counts do not measure supported
actions.

Evidence stays machine-local under
`disassembly/output/phase4-early/<package>-<version>-20260827/report/`.
Use the final `ANALYSIS.md`, `analysis.json` and reproducer for each package.
For the tablet, `CORRECTED_COMMAND_LEDGER.tsv` explicitly supersedes the interim
Stage 1 classifications for both P1 memory saves, both P2 memory saves and the
P2 hardware-query builder. No prior evidence is removed or rewritten, and no
APK or frozen report is distributed with the integration.

## Configuration and routing

Both apps expose the same independent configuration axes:

| Axis | Proven choices |
|---|---|
| App profile | Phone 1.0.6 or tablet 1.0.4 |
| Packet family | P1 standard/Vienna, P2 middle-motor, P1 Toronto |
| Standard topology | Two motors; three with neck, lumbar, height or split-upper adjunct; four with head/back/lumbar/legs |
| Series | Standard or split |
| Optional capabilities | Massage and under-bed light, independently selected |
| Transport | T1, T2 or T3, independently of packet family |

The 24 standard configuration tuples are six topologies times four light/massage
combinations. The reports additionally account for three product/family selector
buttons and the split selector. Vienna aliases standard two-motor with light and
massage; Toronto aliases standard two-motor with light and no massage. These are
28 selector entries, not 28 distinct hardware products. P2 middle is a fixed
layout with two memory slots, back/legs, flat and light; it has no exposed massage
or alarm UI. Split and middle bring the distinct configurations to 26.

The app stores packet-family `bedType` globally while per-device history stores
the remaining layout/capability fields. The integration makes the selected
configuration explicit. A notification beginning `F2 F2 11` supplies the runtime
middle-family flag; it does not identify a physical model or supply actuator
positions.

The implementation profile names are `phone` and `tablet`, and families are `p1`
and `p2`. Layouts are `standard_2`, `standard_3_neck`, `standard_3_lumbar`,
`standard_3_hi_low`, `standard_3_split_upper`, `standard_4`, `split_series` and
`middle`. Only `middle` uses P2. A narrow post-freeze source comparison on
2026-09-08 checked the potentially stale split-plus-P2 state: split selection
retains `bedType`, but `showSpecificBed` subsequently calls
`showMiddleMotorLayout` whenever that value is 1, overriding the split layout.
The middle renderer shows two motors and hides the split, three/four-motor,
massage and alarm layouts. Rejecting P2 with a non-middle layout therefore
preserves the final app routing rather than discarding a mixed profile.

The precise supplemental anchors are each accepted workspace's
`work/jadx/sources/com/dreamotion/app/android/dreamotion/MainActivity.java`:

- Phone `showSpecificBed` lines 1361-1366 and `showMiddleMotorLayout` at 1140;
  source SHA-256 `3976efc3b6bb0dcc2c345b2d887704f2ca18ff945a53b3332b6183bd47769bb0`.
- Tablet `showSpecificBed` lines 1266-1271 and `showMiddleMotorLayout` lines
  785-816; source SHA-256 `b6bf51478ff7bd990600ab15cc88096c133d73469761ca88e6724287d4528150`.

These bounded comparisons preserve the frozen reports unchanged.

Split-series massage exposes left/back and right/back only. The apparent split
leg widget is invisible by default and is never made visible. This was checked
at phone `showMassageOfSplitBed` lines 2760-2768 and tablet lines 2588-2596, plus
their respective `work/jadx/resources/res/layout/activity_main.xml` lines
1385-1387 and 1342-1344. Ordinary standard layouts, including three-motor
split-upper, use back and leg massage. Hidden split-leg listeners are not a
basis for exposing another zone.

## Transport, framing and initialization

| Transport | Service | Write / notification / rename characteristics |
|---|---|---|
| T1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `ff01` / `ff02` / `ff06`, using the same Bluetooth base UUID |
| T2 | `88121427-11e2-52a2-4615-ff00dec16800` | Shared `88121427-11e2-52a2-4615-ff00dec16801`; no rename |
| T3 | `0000fe60-0000-1000-8000-00805f9b34fb` | `fe61` / `fe62` / `fe63`, using the same Bluetooth base UUID |

Both apps scan T1 for two seconds, pause for one second, then scan T3 for two
seconds. Neither supplies a device-name/manufacturer matcher or fresh T2 scan.
T2 can carry commands through an already known exact address; standalone T2
does not emit the ready event that starts initialization queries. T1/T3 require
write, notification and rename roles for that event. Home Assistant owns scanning
and serialized GATT operations. Coherent service selection avoids the Android
global-characteristic overwrite and raw-T1-rename-to-T3 defect.

P1 frames are `F1 F1 | opcode | length | payload | checksum | 7E`; the checksum is
the low byte of the sum from opcode through payload. P2 ordinary controls use
payload `00 00` with length `02`. P2 hardware query is the exception: its payload
is `40 00`, producing `F1F100024000427E`. Transport does not choose P1 or P2.

The ready-relative query schedules are:

| Offset | Phone | Tablet |
|---|---|---|
| +1000/+1100 ms | Actuator query `F1F1000150517E` | Actuator query `F1F1000101027E` |
| +1200/+1300 ms | P1 `F1F1000140417E` or P2 `F1F100024000427E` | Same selector-dependent choice |
| +1400/+1500 ms | Vibration query `F1F1000108097E` | Same |
| +3000/+3100 ms | Dynamic current-time writes | Absent |
| +3000 ms, T3 | Rename-channel notification subscription | Same subscription, without clock writes |

Neither app defines authentication, PIN, encryption, MTU negotiation or an
application acknowledgement/retry protocol. ATT write mode follows actual
characteristic properties; it is not inferred from a missing `setWriteType` call.
The tablet's T3 subscription was verified by a narrow comparison of the accepted
`MainActivity.java` ready-event handler, lines 521-541: it enables notifications
and writes the name characteristic's CCCD after 3000 ms. This event is independent
of the clock writer that exists only in the phone app.

## Complete command-row disposition

`P1:n` and `P2:n` refer to one-based command rows within the phone report's
respective protocol. `R:n` refers to its rename protocol. `T:n` is the one-based
tablet command row in `analysis.json`. The mappings below cover all 34 phone and
89 tablet rows. Alias rows remain identifiable without adding nonexistent
controls for unused declarations.

| Accepted rows | Disposition | Behavior |
|---|---|---|
| P1:1-7; T:2-5,11-12,18-19,31-32,44-47,73-74 | Implemented; unused named movement aliases are not separate actions | All standard, auxiliary and split movement bytes, including literal callsites |
| P1:8-10; T:1,34,75 | Implemented | P1 zero gravity, flat and anti-snore |
| P1:11-12; T:41-42,65-66 | Implemented | P1 save/recall A/B; save is three copies at 0/30/60 ms |
| P1:13; T:64 | Implemented | P1 light toggle and mixed-family release sequence |
| P1:14; T:71 | Implemented | P1 massage stop |
| P1:15; T:6,8-10,20,23-25 | Implemented literal actions; unused named aliases excluded as separate controls | Back/left intensity at wire values 0/2/3/4 |
| P1:16; T:13,15-17 | Implemented | Right-back intensity at wire values 0/2/3/4 |
| P1:17; T:48-49,53-58 | Implemented literal actions; unused named aliases excluded as separate controls | Leg intensity at wire values 0/2/3/4 |
| P1:18; T:68 | Implemented by app profile | Phone mode includes releases; tablet mode is command-only |
| P1:19; T:33 | Implemented | P1 short release, including P2 movement/recall cleanup |
| P1:20-22; T:35,37,40 | Implemented by app profile and family | Initial actuator, hardware and vibration queries |
| P1:23-24 | Implemented for phone | Current clock and clock-request response use P1 frames for either selected family; native alarm configuration is P1-only |
| P2:1-2; T:76-79 | Implemented | P2 back/leg movement |
| P2:3-4; T:80-81,83-84 | Implemented | P2 save, single recall and bounded held recall A/B; corrected saves remain reachable |
| P2:5; T:82 | Implemented | P2 single and bounded held flat with action-specific cleanup |
| P2:6-8; T:85-87 | Implemented | P2 light, long release and corrected hardware-query builder |
| R:1-2; T:88-89 | Implemented by app profile and transport | Phone rename once; tablet rename twice at 0/+500 ms |
| T:7,14,21-22,26-30,50-52,59-63 | Excluded unreachable declarations | Intensity value 1 and values 5-10; no reachable UI control |
| T:36,38-39,43,67,69-70,72 | Excluded unreachable declarations | Combined status/timer queries, memory C, reset/start and timer |

Both profiles expose two memory slots and UI massage levels Off/1/2/3, mapped to
wire values 0/2/3/4. Packet-family P2 does not acquire P1 zero gravity, anti-snore,
massage or alarm controls simply because those bytes occur elsewhere in the app.

## Action-specific lifecycle

Ordinary movement repeats every 100 ms, with one terminal movement frame on
normal touch release and a P1 short release at +100 ms. P2 movement uses the same
P1 cleanup. Home Assistant cancellation never adds a terminal movement and
always performs the proven cleanup, including when a write fails.

The tablet report's general 200 ms repeat field describes the memory gesture,
not ordinary movement. The same narrow accepted-source comparison verifies
`MainActivity.java:385` sets `intervalOfRepeatButton=100`; lines 4054-4059 and
4076-4081 pass it to the movement listeners. The separate
`views/GestureButtonView.java:85` schedules memory long-press repeats at 200 ms.

P1 presets and confirmed memory recalls send P1 release at +100 ms. P1/P2 saves
send three copies at 0/30/60 ms without an appended release. P2 memory long-hold
recall has its own 200 ms cadence. The P2-only service
`adjustable_bed.logicdata_hold_preset` exposes `flat`, `memory_1` and `memory_2`
for a bounded duration: flat repeats every 100 ms, memory every 200 ms. Normal
flat hold ends with its terminal flat frame; memory hold has no terminal recall.
Both remain cancellable and always end with P1 release at +100 ms. Cancellation
does not add a terminal action. Android's pre-confirmation gesture release and later confirmed-tap
release are separate widget events; an explicit HA single recall uses the
confirmed action and cleanup. The app's P2 flat tap omits cleanup,
while its held-flat path sends the same flat command and P1 release at +100 ms.
HA deliberately uses this proven same-action held-release sequence after every
P2 flat command, including failure/cancellation. This is a safety adaptation to
the integration's movement-cleanup contract, not a claim that the app's tap path
sends a release. No command byte or release interval is invented, and no P2
long-release assumption is introduced.

Light sends its family-specific toggle at 0, P1 and P2 release at +80 ms, then
another P1 release at +100 ms. Phone massage mode sends the long release at
+1000 ms followed by short release at +1100 ms. Tablet massage mode sends one
command; its +1000 ms handler only updates animation and adds no release.
Massage intensity and stop are command-only.

Native phone alarm configuration remains useful independently of app scheduling.
The phone's `WorkerWaketime` has zero app-owned construction/enqueue producers,
`initialOthers()` has no caller, and `setWaketimeAlarm` only stores a date.
Consequently the local wake executor and its dense packet sequences are dead
code, not features to expose. Tablet has neither live clock/alarm writers nor
their notification parsers. Android alarm screens and storage do not justify
adding these absent tablet protocol operations.

## Eleven-area FULL reconciliation

| Accepted area | Accepted comparison | Integration disposition |
|---|---|---|
| Delivery | Same five-split/DEX/GIF stack shape; different identities and display-density split | Both exact accepted packages retained |
| Manifest/discovery | Same service-filtered scans and no name/manufacturer matcher | Shared discovery constraints |
| GATT roles | Same three transports and dead login fields | Shared coherent role selection; no login command |
| BLE callsites | Phone has four write boundaries; tablet has two | Clock/alarm methods restricted to phone |
| Packet construction | Different actuator query; selector-dependent hardware query; no tablet time/alarm | Explicit profile/family builders and corrected tablet query |
| Framing/authentication | Same checksum envelope; no live authentication | Shared framing only where both reports prove it |
| Notification parsing | Tablet lacks phone clock/alarm parsing | Profile-specific bounded parsers |
| Commands/STOP/timing | Tablet mode has no release; rename is twice with defective encoding | Distinct mode/rename schedules; malformed name encoding excluded |
| Resources/variants | All 28 selector entries reconcile | Explicit family/layout/capability selection |
| Native stack | Only unrelated GIF JNI beyond DEX | No speculative native protocol |
| Capability routing | Shared selectors and dead local alarm producer; tablet clock/alarm absent | No promotion of dead scaffolding to live controls |

These are six agreement areas, four material-difference areas, and one agreement
with a package-specific absence. The accepted FULL promotion resolves all eleven;
no further cluster member or analysis pass is outstanding.

## Parsing, exclusions and deferred validation

Both apps use complete callback values with no reassembly or response checksum
validation. Implemented state includes family validation, hardware acknowledgement,
massage intensity and the legacy light bit. Phone additionally handles current-time
requests and native alarm fields. Generic opcode-05/06 status does not require an
`F2 F2` header. Defensive length/range checks prevent Android parser exceptions
without inventing a checksum requirement. Neither app reports positions, RGB,
brightness, firmware/model identifiers or calibration status.

| Finding | Exclusion or adaptation |
|---|---|
| Missing movement key/cancel cleanup | Android defect excluded; HA always sends proven release cleanup |
| P2 flat tap omits release | Omission excluded; HA uses the same app's proven P2 held-flat P1 release at +100 ms |
| Duplicate readiness events, characteristic overwrites and unchecked write returns | Android scheduling/routing defects excluded; coherent roles and serialized writes |
| P2 pre-confirmation duplicate gesture callbacks and app preference history | Android interaction mechanisms excluded; explicit single/held recall actions and configuration retain reachable packet behavior |
| Tablet T3 UTF-16 length, unpadded hex and null write | Malformed encoding excluded; valid bounded names retain the proven T3 frame and double-write schedule |
| Local wake workers/timers and externally stimulated alarm receivers | Dead producer graph excluded; phone native alarm configuration is still implemented |
| Named memory C, unused intensity levels, timer/reset/start/status paths | Unreachable declarations excluded, including byte-identical aliases as separate controls |
| Login fields and unused generic read helpers | Dead code excluded; no authentication or extra reads invented |
| GIF JNI and Lottie asset | Unrelated third-party/UI artifacts excluded |
| Classic/cloud transport, pairing/PIN, firmware/OTA, EEPROM/calibration, RGB/brightness/light timer, position feedback | Absent domains excluded |

Later hardware checks should confirm actuator mapping, selected family/layout,
characteristic properties, T2 provisioning, mixed-family release behavior and
notification boundaries. Shared brand names and app labels do not establish
hardware confirmation. None of these deferred checks invalidates the accepted
artifact analysis.

Ref [#436](https://github.com/kristofferR/ha-adjustable-bed/issues/436),
[#443](https://github.com/kristofferR/ha-adjustable-bed/issues/443) and
[#447](https://github.com/kristofferR/ha-adjustable-bed/issues/447).
