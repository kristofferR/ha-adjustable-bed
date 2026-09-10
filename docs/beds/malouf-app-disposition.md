# Malouf and Lucid app implementation disposition

This is the implementation ledger for Phase 4 row023, formal cluster-007,
against `release/4.0`. The explicit `malouf_app` configuration selects the app,
model, transport and side independently. Existing Malouf controllers and their
hardware-tested layout options remain separate. No discovery route is reassigned.
The new app route is supported by frozen artifact evidence; physical behavior is
not claimed as verified.

Implementation and independent final audit are in progress. The command rows below
record the required final dispositions and are checked against the complete unit
before its PR is opened.

## Accepted evidence reuse

Both accepted FULL member reports and the accepted cluster reconciliation were
reused without altering any analysis. The current #443 Batch 5 record accepts
Malouf independent audit003, Lucid FULL promotion and independent audit007, and
cluster audit005. There are exactly two members, no remaining DELTA route,
missing member or incomplete comparison area. All report manifests were checked:
8 Malouf entries, 33 Lucid entries and 14 reconciliation entries. Both package
reports have all 17 completion gates passing and no blockers.

| Member | Version | Artifact-set SHA-256 | analysis.json SHA-256 | REPORT.SHA256 SHA-256 |
|---|---|---|---|---|
| com.malouf.bedbase | 2.4.3 (54) | `d9b242a8dda6772f62c5b8f21fe13b462af2533b82a16d67ee7a4a841e6ff894` | `507fc665041de7b9b21d0662d598b0250591574f51236182c8674cc6e38eadbe` | `746d913ad256afd0deffe42e989a96c4e2f4c7aa941add5343a65f2236f9e5de` |
| com.lucid.bedbase | 1.3.3 (16) | `88162f4b6adc2cf0d0d5ee4252fe4de3e6564db1881e42ed0a34db3ba58ad148` | `7dc47677ea4ce1e0f8d0cdfcb22fd86dd14723c9bedf2ac52236ac0b65320d6d` | `8d21996769e6d209345dc38ac84bb178b9fe70293305f22a39227dfe9f3a880c` |

The local roots are `disassembly/output/phase4-early/<package>-<version>-2026-08-27/report`.
Cluster evidence is at `phase4b-odd-clusters-2026-08-27/cluster-007` beneath
`phase4-early`. Its reconciliation JSON hashes to
`c584d5aaab3d9e881816e97190554871f10aa70fb0a24ca53933c3bbdb9a1fef`,
manifest to `fd9492a0f0a17ba454247ad9532c5e5f309cbc1090c20a5c9519e8bc8c820239`,
and accepting audit005 to
`94c824326a6c8391065c15e48aa5e5c59401b6b89dec784c53bf84fd6e12769c`.
Raw artifacts, decompilation and reports remain machine-local.

## Whole-cluster reconciliation

All 11 frozen comparison areas are dispositioned. Five are SAME and six DIFFERENT;
all 68 normalized terminal command families overlap, with no side-only family.
The different number of structured report rows is not a different protocol count.
Malouf contains 69 command rows (30 opcode, 39 command32); Lucid contains 174
(112 command32, 62 opcode), including separately enumerated transport variants.
The neutral P1/P2 identifiers are reversed between reports and must not be joined
by identifier alone.

| Area | Frozen result | Integration disposition |
|---|---|---|
| Delivery/artifact set | DIFFERENT | EXCLUDED: packaging and French split introduce no controller operation. Preserve both identities. |
| Manifest and discovery | DIFFERENT | IMPLEMENTED: explicit five-profile configuration avoids Lucid's omitted new-service scan filter and ambiguous Nordic roles. |
| GATT roles | SAME | IMPLEMENTED: all 16 normalized role tuples retained through five explicit transport profiles. |
| BLE lifecycle | DIFFERENT | IMPLEMENTED: serialized HA connection/write/notify lifecycle; EXCLUDED Android scanner ownership and service-order hybrid races. |
| Packet construction | SAME | IMPLEMENTED: seven shared normal/dynamic builders with profile-specific framing. |
| Framing/authentication | SAME | IMPLEMENTED: no-response writes; no invented PIN, pairing handshake or checksum. |
| Commands/preset routing | DIFFERENT | IMPLEMENTED: exact nine-label map with six same and three differing labels, plus split route differences. |
| Notification parsing | SAME | IMPLEMENTED: three command32 parser families; opcode has no parser. |
| Resources/variant reachability | DIFFERENT | IMPLEMENTED: all 16 constructor models, app-specific fresh versus restored provenance. |
| Capability routing | DIFFERENT | IMPLEMENTED: model/action/transport intersection and exact dynamic/side routing. |
| Application stacks/native assets | SAME | EXCLUDED: shared third-party native and inference assets do not define another BLE transport. |

The accepted reconciliation also checks 20 exact source anchors, five identical
core files, three native libraries and two inference assets. Its 140 mutation
cases were already accepted and were not rerun. The accepted candidate inventories
(19 Malouf and 133 Lucid), 227 Lucid model-action traces and three dynamic routes
are cross-referenced below. A narrow source correction to an overbroad Lucid
massage-off trace is explicit and does not rewrite the accepted report or counts.

## Existing behavior retained

ALREADY_IMPLEMENTED: the existing Malouf legacy/new controllers encode the same
9-byte and 8-byte command32 frames, normal motor/preset command values, legacy
three-copy preset behavior, new preset release, and 85/55 memory-save counts,
including the lowercase `smartbed238` save-1 branch. Their tests and configuration
remain in place. These shared facts do not complete the app-specific model, middle
transport, opcode, state, alarm, routing or lifecycle findings; those are the new
`malouf_app` implementation.

## Runtime dispositions

- IMPLEMENTED: `opcode_legacy`, `opcode_framed`, `command32_legacy`,
  `command32_middle`, and `command32_new` are explicit transport choices. Models
  never select a transport. No ambiguous Nordic service is autodetected into this route.
- IMPLEMENTED: manual commands start immediately, refresh every 150 ms while
  requested, then use the transport's proven STOP 150 ms after release/cancel.
  Cleanup uses a fresh cancellation event. HA bounds held operations rather than
  leaving an Android touch listener active indefinitely.
- IMPLEMENTED: opcode legacy presets send once then immediate STOP; opcode framed
  sends once without normal STOP. Command32 legacy sends three copies without
  normal STOP; middle sends three then STOP; new sends one then STOP. Cancellation
  still performs proven protocol STOP cleanup for movement.
- IMPLEMENTED: opcode memory saves send once. Command32 legacy/middle save 85
  writes at 150 ms; new saves 55 at 100 ms, with the first write after one interval.
  The Android terminal literal `stopCommand` has no dispatcher branch and is not
  translated into an invented packet. Save is a programming lifecycle, not an
  indefinitely refreshed motor command.
- IMPLEMENTED: only six opcode-framed actions use the primary/secondary selector:
  head up/down, head massage, flat, zero-G and anti-snore. All other opcode actions
  force selector zero; command32 ignores it. Explicit partner routing preserves
  active-side and SplitHead DualBase fan-out rather than treating side as an
  invented command bit.
- IMPLEMENTED: legacy/middle clock and native alarms send three copies, new sends
  one. New-only status query `00 b0` follows the proven light/massage actions.
  Native alarms and clock synchronization are exposed through serialized services.
- IMPLEMENTED: notifications expose reported massage minutes and under-bed-light
  state only. Legacy accepts exactly 10/16/20 bytes; middle retains signed massage
  byte behavior and has no light support; new uses its exact selector and optional
  fields. No motor position, battery, intensity or target-position state is invented.
- EXCLUDED: Android service-order hybrids, OS permission/bonding races, redundant
  descriptor callbacks and queue timeout/drop behavior. HA owns BLE connection and
  serialization; the selected profile cannot mix a characteristic from one
  transport with another transport's frame or timing.
- EXCLUDED: dead command constants, unmatched UI aliases, Classic/DFU absence,
  unrelated native code, Android database/UI persistence mechanisms and classifier
  implementation. The selected-preset/flat actions used by shortcuts and snore
  detection remain available to HA automations; their BLE operations are included.

## Model and action inventory

Both reports contain the same 16 constructors. Malouf freshly selects 14 models;
L300 and Premium are restored-only. Lucid freshly selects L300, L600 and Premium;
the other 13 are restored-only. Every constructor can be selected explicitly in
HA, with capabilities constrained by its actual transformed command route.

| Model | Memory slots | Manual labels | Preset labels | Other labels |
|---|---:|---|---|---|
| Altitude | 0 | HEAD, FOOT, DUAL, TILT HEAD, FULL TILT | ZERO G, ANTI SNORE | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE OFF, LIGHT |
| E450 | 0 | HEAD, FOOT | ZERO G, ANTI SNORE |  |
| E455 | 0 | HEAD, FOOT | ZERO G, ANTI SNORE |  |
| Forte | 0 | HEAD, FOOT | ZERO G | MASSAGE, MASSAGE HEAD, MASSAGE TYPE, MASSAGE OFF |
| Good Life Base | 0 | Head, Foot, All | Oz Spine Relief, TV, Oz Anti Snore, Lounge |  |
| Good Life Premier Base | 0 | Head, Foot, All, Head Tilt, Lumbar | Oz Spine Relief, TV, Oz Anti Snore, Lounge | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE OFF, MASSAGE TIMER SET, LIGHT |
| Good Life Pro Base | 0 | Head, Foot, All | Oz Spine Relief, TV, Oz Anti Snore, Lounge | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE OFF, MASSAGE TIMER SET, LIGHT |
| L300 | 0 | HEAD, FOOT | ZERO G, ANTI SNORE |  |
| L600 | 1 | HEAD, FOOT | ZERO G, ANTI SNORE, LOUNGE, TV READ | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE TIMER, ALARM, LIGHT |
| M455 | 0 | HEAD, FOOT | ZERO G, ANTI SNORE | MASSAGE, MASSAGE HEAD, MASSAGE TYPE, MASSAGE OFF, MASSAGE TIMER SET |
| M550 | 1 | HEAD, FOOT | ZERO G, ANTI SNORE, LOUNGE, TV READ | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE TIMER, ALARM, LIGHT |
| M555 | 1 | HEAD, FOOT, DUAL | ZERO G, TV READ, ANTI SNORE, LOUNGE | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE OFF, MASSAGE TIMER SET, LIGHT |
| Premium | 2 | HEAD, FOOT, DUAL | ZERO G, ANTI SNORE, TV, READ | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE TIMER, ALARM, LIGHT |
| S655 | 2 | HEAD, FOOT, DUAL, HEAD TILT | ZERO G, TV READ, ANTI SNORE, LOUNGE | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE OFF, MASSAGE TIMER SET, LIGHT |
| S750 | 2 | HEAD, FOOT, HEAD TILT, LUMBAR | ZERO G, TV READ, ANTI SNORE, LOUNGE | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE TIMER, ALARM, LIGHT |
| S755 | 2 | HEAD, FOOT, DUAL, HEAD TILT, LUMBAR | ZERO G, TV READ, ANTI SNORE, LOUNGE | MASSAGE, MASSAGE HEAD, MASSAGE FOOT, MASSAGE TYPE, MASSAGE OFF, MASSAGE TIMER SET, LIGHT |

All constructor labels are IMPLEMENTED through supported transport intersections;
an unknown transformed command is EXCLUDED rather than assigned a guessed opcode.
In particular, Malouf maps Oz Spine Relief/Oz Anti Snore to zeroG/antiSnore;
Lucid retains the Oz literal, recognized by opcode and unmatched by command32.
Lucid Premium READ maps to `read` (command32 Lounge value; opcode no write).
Malouf Premium READ short release is unmatched for both families; its eight-tick
long hold reaches the real slot-2 save workflow. Memory-save access from fallback
preset labels is separate from ordinary numbered-memory capability. Lucid Good
Life Base, Good Life Pro Base and Good Life Premier Base each expose programming
slot 2 through the two Oz-label fallbacks, despite having zero numbered recall
slots. Slot 1 is not inferred. This applies to all five transports. The routed
action service exposes that save without creating unsupported recall entities.

## Concrete post-freeze source clarifications

These narrow lookups resolve implementation gaps in already accepted workspaces.
They are not new APK analysis and do not change frozen evidence acceptance.

1. Alarm weekdays are Sunday128, Monday2, Tuesday4, Wednesday8, Thursday16,
   Friday32, Saturday64. A nonempty recurring selection also sets bit0. No selected
   weekdays selects the next occurrence's weekday bit without bit0, advancing to
   tomorrow when the target hour/minute is not later than now. New framing moves
   Sunday to bit0 and drops the legacy repeat marker.
2. The fresh alarm spinner contains six positions mapping index+13 to zero-G13,
   lounge14, TV/read15, anti-snore16, memory1=17, memory2=18. Both apps remove the
   Memory1 label for fewer than two slots, then attempt the same removal again for
   zero slots, while retaining index+13 encoding. The remaining Memory2-labelled
   item therefore emits17. HA uses truthful operation names. The accepted
   `ALARM-POSITION-ROUTING` candidate also proves restored Alarm.position dispatch
   for all eight enum values, including massage20 and flat21, independent of this
   fresh UI pruning. No type19 is invented.
3. Lucid's synthesized command32 massageOff rows `CMD-P1-082` through `084`
   overstate reachability. The actual layout binds the off/timer button to
   `massageTimer`; the activity converts it to `massageOff` only for a connection
   whose `canSetMassageTimer` is true. The command32 constructor sets that flag
   false; opcode sets it true. Thus both apps' command32 OFF-labelled button emits
   timer `0x200`, not `0x02000000`. The latter is EXCLUDED. Lucid action traces
   ACTION017,039,068,085,118,149,185,225 receive this explicit correction. Frozen
   row text and all counts remain preserved.
4. In inactive SplitHead DualBase routing, both apps forward foot commands and
   transform dual to foot. Lucid additionally transforms all to foot; Malouf does
   not. Both forward STOP. Preset routing is separately applied to both bases.
   Programming collects only active bases. Existing HA pairing applies one
   callback to selected children and cannot express the changed inactive-side
   command by itself; the explicit routed-action service supplies the per-child
   plan through the existing paired scheduler. Ordinary entities retain literal
   per-device behavior, and the app route is selected explicitly.
5. Active means selected side All, selected side equals base side, or base side
   None. SplitHead + SplitBase sends normal actions to every base using primary
   `(left and not motor_swapped) or (right and motor_swapped)`; outside that
   configuration primary is true. Selecting All in this single-base app mode
   yields secondary, not two invented writes. Explicit wire-primary selection
   retains that operation; separate-address dual-base routing never reinterprets
   the primary selector as an address.
6. Lucid preset adapter's map omits both Oz labels. Its fallback is a memory
   action, slot 1 if the literal contains `1`, otherwise slot 2. At eight 250 ms
   ticks it opens the programming screen. This proves save slot 2 on the three
   zero-recall-slot Good Life models, independent of whether the short-release
   literal matches the chosen transport.

| Supplemental source | SHA-256 |
|---|---|
| M: `work/jadx/sources/com/malouf/bedbase/activities/AddEditAlarmActivity.java` | `edd3742646ef90b989be41e26c9279b0982cb183c0c1b9be8f655ff4f74eca33` |
| M: `work/jadx/sources/com/malouf/bedbase/activities/RemoteTabBarActivity.java` | `eb46a422c1555b87db089be025e2c933e35545958b967425a5f07341357911ab` |
| M: `work/jadx/sources/com/malouf/database/enums/AlarmPosition.java` | `e1d17caab897122a839c9929536af9eb1f1c991123d550bb3a3a6f128770e65f` |
| M: `work/jadx/sources/com/malouf/adjustablebasebluetooth/OkinConnection.java` | `ce5d1f60f22655041c5a5bd01d0f1b65c4c27bf207730df3b6405c5ca2da024f` |
| M: `work/jadx/sources/com/malouf/adjustablebasebluetooth/RichmatConnection.java` | `36089a5b22eed896219777a226b61fd10a9eab9619dc98d2480144b4cd6a8352` |
| L: `work/jadx/sources/com/lucid/bedbase/activities/AddEditAlarmActivity.java` | `439aa5e1dfda8ea2a7ebc857b38833fa525152c534f197eea1a3b896916bab3f` |
| L: `work/jadx/sources/com/lucid/bedbase/activities/RemoteTabBarActivity.java` | `484d22d9af170ae11f9b4481c1d04570fd671eeddcc29f9e1fbfc5ca5a1d5368` |
| L: `work/jadx/sources/com/malouf/database/enums/AlarmPosition.java` | `e1d17caab897122a839c9929536af9eb1f1c991123d550bb3a3a6f128770e65f` |
| L: `work/smali/base/res/values/arrays.xml` | `defcadf6d409c95041ec8292cae425b50782eda19149efca4409e4b2c9e26f80` |
| L: `work/smali/base/res/layout/fragment_massage.xml` | `3d676e52c4198f5927126b3aee456f1fefadb2d0b695426f70f23d357a8ff37c` |
| L: `work/jadx/sources/com/malouf/adjustablebasebluetooth/OkinConnection.java` | `ce5d1f60f22655041c5a5bd01d0f1b65c4c27bf207730df3b6405c5ca2da024f` |
| L: `work/jadx/sources/com/malouf/adjustablebasebluetooth/RichmatConnection.java` | `36089a5b22eed896219777a226b61fd10a9eab9619dc98d2480144b4cd6a8352` |

| M: `work/jadx/sources/com/malouf/bedbase/ActiveBed.java` | `79b95a52a5ea955c1cb947d2177c486abde36c6751dd2474cd05a22fc44b3363` |
| M: `work/jadx/sources/com/malouf/bedbase/recycler_view_adapters/PresetControlRecyclerViewAdapter.java` | `bc5320de0cd9417e9a505775e3dc7523ab615ef65ef703b3415ef4f5ecf6a73d` |
| M: `work/jadx/sources/com/malouf/bedbase/activities/SetMemoryPositionActivity.java` | `827dd96f563fbc7fb355a310d86c09af10cc05a2266b6d36571c8e0edb3a20a6` |
| L: `work/jadx/sources/com/lucid/bedbase/ActiveBed.java` | `1b090aa029e17ecfe3e8fc83c1a0f0e7d5ebc09a2f468e37d733f4b5fd742a63` |
| L: `work/jadx/sources/com/lucid/bedbase/recycler_view_adapters/PresetControlRecyclerViewAdapter.java` | `51971bf981d6a4679bf4c8eff4dcaed74aaeebe2354a25fef413e8e7f09ec34f` |
| L: `work/jadx/sources/com/lucid/bedbase/activities/SetMemoryPositionActivity.java` | `a1db8ea95e63f837df203570658cb2a51b2555cebd4e0485f2295744eb4ba7a3` |

| M: `work/smali/com.malouf.bedbase/res/values/arrays.xml` | `0afbc79765f46d13c0d78c07e786ef5de799a4885aa647ca834e2537da5e311e` |
| M: `work/smali/com.malouf.bedbase/res/layout/fragment_massage.xml` | `a7b071d71674e48cbebbe0c7fff89b29e195deba020976d4d3579dd77728de4b` |

Source anchors: AddEditAlarmActivity106–153 and299–313 in both apps;
RemoteTabBarActivity Malouf911–950/Lucid900–939 (alarm),
Malouf789–809/Lucid778–800 (normal routing); AlarmPosition11–37;
arrays.xml positions array; fragment_massage.xml22;
OkinConnection constructor and RichmatConnection constructor feature flags;
ActiveBed37–50; Lucid preset adapter60–67,217–225,270–281;
RemoteTabBarActivity Lucid809–825/Malouf820–837 (programming targets);
SetMemoryPositionActivity saveMemoryPosition and sendCommand.
The task-local `row023-off-source-reproducer.py` independently asserts the two
layout bindings, click callbacks and opposite constructor capability flags; it
passes for both preserved workspaces. Focused integration tests cover the
resulting command32 timer versus opcode off behavior.

## Complete command-row ledger

`M1-NN` and `M2-NN` are stable one-based positions in Malouf's opcode and command32
command arrays. `L-CMD-*` preserves Lucid's frozen IDs. IMPLEMENTED means the
reachable route, bytes and lifecycle are covered, subject to model/transport
intersection; it does not expose every alias or definition-only branch.
EXCLUDED rows are retained visibly to prevent later reintroduction.

| Evidence row | Action | Disposition |
|---|---|---|
| M1-01 | headUp | IMPLEMENTED |
| M1-02 | headDown | IMPLEMENTED |
| M1-03 | footUp | IMPLEMENTED |
| M1-04 | footDown | IMPLEMENTED |
| M1-05 | dualUp/allUp | IMPLEMENTED |
| M1-06 | dualDown/allDown | IMPLEMENTED |
| M1-07 | setMemory1 | IMPLEMENTED |
| M1-08 | setMemory2 | IMPLEMENTED |
| M1-09 | setMemory3 | EXCLUDED |
| M1-10 | memory1/Memory 1 | IMPLEMENTED |
| M1-11 | memory2/Memory 2 | IMPLEMENTED |
| M1-12 | memory3 | EXCLUDED |
| M1-13 | allFlat | IMPLEMENTED |
| M1-14 | lightSwitch | IMPLEMENTED |
| M1-15 | fullTiltUp/headTiltUp | IMPLEMENTED |
| M1-16 | fullTiltDown/headTiltDown | IMPLEMENTED |
| M1-17 | tiltHeadUp/lumbarUp | IMPLEMENTED |
| M1-18 | tiltHeadDown/lumbarDown | IMPLEMENTED |
| M1-19 | zeroG/Zero G/Oz Spine Relief | IMPLEMENTED |
| M1-20 | antiSnore/Anti Snore/Oz Anti Snore | IMPLEMENTED |
| M1-21 | massageOff | IMPLEMENTED |
| M1-22 | massageWave | IMPLEMENTED |
| M1-23 | massageHead | IMPLEMENTED |
| M1-24 | massageFoot | IMPLEMENTED |
| M1-25 | tvRead/TV Read/TV | IMPLEMENTED |
| M1-26 | lounge/Lounge | IMPLEMENTED |
| M1-27 | massage10 | IMPLEMENTED |
| M1-28 | massage30 | IMPLEMENTED |
| M1-29 | massage20 | IMPLEMENTED |
| M1-30 | stopDriver | IMPLEMENTED |
| M2-01 | stopDriver | IMPLEMENTED |
| M2-02 | headUp | IMPLEMENTED |
| M2-03 | headDown | IMPLEMENTED |
| M2-04 | footUp | IMPLEMENTED |
| M2-05 | dualUp | IMPLEMENTED |
| M2-06 | footDown | IMPLEMENTED |
| M2-07 | dualDown | IMPLEMENTED |
| M2-08 | headTiltUp/headTiltDown | IMPLEMENTED |
| M2-09 | lumbarUp/lumbarDown | IMPLEMENTED |
| M2-10 | massageAll | EXCLUDED |
| M2-11 | massageTimer | IMPLEMENTED |
| M2-12 | massageFoot | IMPLEMENTED |
| M2-13 | massageHead | IMPLEMENTED |
| M2-14 | zeroG | IMPLEMENTED |
| M2-15 | lounge/Lounge | IMPLEMENTED |
| M2-16 | read/Read | EXCLUDED |
| M2-17 | tvRead | IMPLEMENTED |
| M2-18 | TV Read/tv/TV | EXCLUDED |
| M2-19 | antiSnore | IMPLEMENTED |
| M2-20 | memory1/Memory 1 | IMPLEMENTED |
| M2-21 | lightSwitch | IMPLEMENTED |
| M2-22 | memory2/Memory 2 | IMPLEMENTED |
| M2-23 | intensityOne | EXCLUDED |
| M2-24 | intensityTwo | EXCLUDED |
| M2-25 | intensityThree | EXCLUDED |
| M2-26 | massageWaist | EXCLUDED |
| M2-27 | massageHeadMinus | EXCLUDED |
| M2-28 | massageFootMinus | EXCLUDED |
| M2-29 | massageStopAll | EXCLUDED |
| M2-30 | massageOff | EXCLUDED |
| M2-31 | massageAllOnOff | EXCLUDED |
| M2-32 | allFlat | IMPLEMENTED |
| M2-33 | massageWaistMinus | EXCLUDED |
| M2-34 | massageWave | IMPLEMENTED |
| M2-35 | setMemory1 | IMPLEMENTED |
| M2-36 | setMemory2 | IMPLEMENTED |
| M2-37 | setCurrentTime | IMPLEMENTED |
| M2-38 | setAlarm/clearAlarm | IMPLEMENTED |
| M2-39 | query light/massage status | IMPLEMENTED |
| L-CMD-P1-001 | headUp | IMPLEMENTED |
| L-CMD-P1-002 | headUp | IMPLEMENTED |
| L-CMD-P1-003 | headUp | IMPLEMENTED |
| L-CMD-P1-004 | headDown | IMPLEMENTED |
| L-CMD-P1-005 | headDown | IMPLEMENTED |
| L-CMD-P1-006 | headDown | IMPLEMENTED |
| L-CMD-P1-007 | footUp | IMPLEMENTED |
| L-CMD-P1-008 | footUp | IMPLEMENTED |
| L-CMD-P1-009 | footUp | IMPLEMENTED |
| L-CMD-P1-010 | footDown | IMPLEMENTED |
| L-CMD-P1-011 | footDown | IMPLEMENTED |
| L-CMD-P1-012 | footDown | IMPLEMENTED |
| L-CMD-P1-013 | dualUp | IMPLEMENTED |
| L-CMD-P1-014 | dualUp | IMPLEMENTED |
| L-CMD-P1-015 | dualUp | IMPLEMENTED |
| L-CMD-P1-016 | dualDown | IMPLEMENTED |
| L-CMD-P1-017 | dualDown | IMPLEMENTED |
| L-CMD-P1-018 | dualDown | IMPLEMENTED |
| L-CMD-P1-019 | headTiltUp | IMPLEMENTED |
| L-CMD-P1-020 | headTiltUp | IMPLEMENTED |
| L-CMD-P1-021 | headTiltUp | IMPLEMENTED |
| L-CMD-P1-022 | headTiltDown | IMPLEMENTED |
| L-CMD-P1-023 | headTiltDown | IMPLEMENTED |
| L-CMD-P1-024 | headTiltDown | IMPLEMENTED |
| L-CMD-P1-025 | lumbarUp | IMPLEMENTED |
| L-CMD-P1-026 | lumbarUp | IMPLEMENTED |
| L-CMD-P1-027 | lumbarUp | IMPLEMENTED |
| L-CMD-P1-028 | lumbarDown | IMPLEMENTED |
| L-CMD-P1-029 | lumbarDown | IMPLEMENTED |
| L-CMD-P1-030 | lumbarDown | IMPLEMENTED |
| L-CMD-P1-031 | massageAll | EXCLUDED |
| L-CMD-P1-032 | massageAll | EXCLUDED |
| L-CMD-P1-033 | massageAll | EXCLUDED |
| L-CMD-P1-034 | massageTimer | IMPLEMENTED |
| L-CMD-P1-035 | massageTimer | IMPLEMENTED |
| L-CMD-P1-036 | massageTimer | IMPLEMENTED |
| L-CMD-P1-037 | massageFoot | IMPLEMENTED |
| L-CMD-P1-038 | massageFoot | IMPLEMENTED |
| L-CMD-P1-039 | massageFoot | IMPLEMENTED |
| L-CMD-P1-040 | massageHead | IMPLEMENTED |
| L-CMD-P1-041 | massageHead | IMPLEMENTED |
| L-CMD-P1-042 | massageHead | IMPLEMENTED |
| L-CMD-P1-043 | zeroG / Zero G | IMPLEMENTED |
| L-CMD-P1-044 | zeroG / Zero G | IMPLEMENTED |
| L-CMD-P1-045 | zeroG / Zero G | IMPLEMENTED |
| L-CMD-P1-046 | lounge / Lounge / read / Read | IMPLEMENTED |
| L-CMD-P1-047 | lounge / Lounge / read / Read | IMPLEMENTED |
| L-CMD-P1-048 | lounge / Lounge / read / Read | IMPLEMENTED |
| L-CMD-P1-049 | tv / TV / tvRead / TV Read | IMPLEMENTED |
| L-CMD-P1-050 | tv / TV / tvRead / TV Read | IMPLEMENTED |
| L-CMD-P1-051 | tv / TV / tvRead / TV Read | IMPLEMENTED |
| L-CMD-P1-052 | antiSnore / Anti Snore | IMPLEMENTED |
| L-CMD-P1-053 | antiSnore / Anti Snore | IMPLEMENTED |
| L-CMD-P1-054 | antiSnore / Anti Snore | IMPLEMENTED |
| L-CMD-P1-055 | memory1 / Memory 1 | IMPLEMENTED |
| L-CMD-P1-056 | memory1 / Memory 1 | IMPLEMENTED |
| L-CMD-P1-057 | memory1 / Memory 1 | IMPLEMENTED |
| L-CMD-P1-058 | lightSwitch | IMPLEMENTED |
| L-CMD-P1-059 | lightSwitch | IMPLEMENTED |
| L-CMD-P1-060 | lightSwitch | IMPLEMENTED |
| L-CMD-P1-061 | memory2 / Memory 2 | IMPLEMENTED |
| L-CMD-P1-062 | memory2 / Memory 2 | IMPLEMENTED |
| L-CMD-P1-063 | memory2 / Memory 2 | IMPLEMENTED |
| L-CMD-P1-064 | intensityOne | EXCLUDED |
| L-CMD-P1-065 | intensityOne | EXCLUDED |
| L-CMD-P1-066 | intensityOne | EXCLUDED |
| L-CMD-P1-067 | intensityTwo | EXCLUDED |
| L-CMD-P1-068 | intensityTwo | EXCLUDED |
| L-CMD-P1-069 | intensityTwo | EXCLUDED |
| L-CMD-P1-070 | intensityThree | EXCLUDED |
| L-CMD-P1-071 | intensityThree | EXCLUDED |
| L-CMD-P1-072 | intensityThree | EXCLUDED |
| L-CMD-P1-073 | massageWaist | EXCLUDED |
| L-CMD-P1-074 | massageWaist | EXCLUDED |
| L-CMD-P1-075 | massageWaist | EXCLUDED |
| L-CMD-P1-076 | massageHeadMinus | EXCLUDED |
| L-CMD-P1-077 | massageHeadMinus | EXCLUDED |
| L-CMD-P1-078 | massageHeadMinus | EXCLUDED |
| L-CMD-P1-079 | massageFootMinus | EXCLUDED |
| L-CMD-P1-080 | massageFootMinus | EXCLUDED |
| L-CMD-P1-081 | massageFootMinus | EXCLUDED |
| L-CMD-P1-082 | massageStopAll / massageOff | EXCLUDED (source correction above) |
| L-CMD-P1-083 | massageStopAll / massageOff | EXCLUDED (source correction above) |
| L-CMD-P1-084 | massageStopAll / massageOff | EXCLUDED (source correction above) |
| L-CMD-P1-085 | massageAllOnOff | EXCLUDED |
| L-CMD-P1-086 | massageAllOnOff | EXCLUDED |
| L-CMD-P1-087 | massageAllOnOff | EXCLUDED |
| L-CMD-P1-088 | allFlat | IMPLEMENTED |
| L-CMD-P1-089 | allFlat | IMPLEMENTED |
| L-CMD-P1-090 | allFlat | IMPLEMENTED |
| L-CMD-P1-091 | massageWave / massageWaistMinus | IMPLEMENTED |
| L-CMD-P1-092 | massageWave / massageWaistMinus | IMPLEMENTED |
| L-CMD-P1-093 | massageWave / massageWaistMinus | IMPLEMENTED |
| L-CMD-P1-094 | stopDriver | IMPLEMENTED |
| L-CMD-P1-095 | stopDriver | IMPLEMENTED |
| L-CMD-P1-096 | stopDriver | IMPLEMENTED |
| L-CMD-P1-097 | setMemory1 | IMPLEMENTED |
| L-CMD-P1-098 | setMemory1 | IMPLEMENTED |
| L-CMD-P1-099 | setMemory1 | IMPLEMENTED |
| L-CMD-P1-100 | setMemory2 | IMPLEMENTED |
| L-CMD-P1-101 | setMemory2 | IMPLEMENTED |
| L-CMD-P1-102 | setMemory2 | IMPLEMENTED |
| L-CMD-P1-103 | setCurrentTime | IMPLEMENTED |
| L-CMD-P1-104 | setCurrentTime | IMPLEMENTED |
| L-CMD-P1-105 | setCurrentTime | IMPLEMENTED |
| L-CMD-P1-106 | setAlarm | IMPLEMENTED |
| L-CMD-P1-107 | setAlarm | IMPLEMENTED |
| L-CMD-P1-108 | setAlarm | IMPLEMENTED |
| L-CMD-P1-109 | clearAlarm | IMPLEMENTED |
| L-CMD-P1-110 | clearAlarm | IMPLEMENTED |
| L-CMD-P1-111 | clearAlarm | IMPLEMENTED |
| L-CMD-P1-112 | queryLightAndMassageStatus | IMPLEMENTED |
| L-CMD-P2-001 | headUp | IMPLEMENTED |
| L-CMD-P2-002 | headUp | IMPLEMENTED |
| L-CMD-P2-003 | headDown | IMPLEMENTED |
| L-CMD-P2-004 | headDown | IMPLEMENTED |
| L-CMD-P2-005 | footUp | IMPLEMENTED |
| L-CMD-P2-006 | footUp | IMPLEMENTED |
| L-CMD-P2-007 | footDown | IMPLEMENTED |
| L-CMD-P2-008 | footDown | IMPLEMENTED |
| L-CMD-P2-009 | dualUp / allUp | IMPLEMENTED |
| L-CMD-P2-010 | dualUp / allUp | IMPLEMENTED |
| L-CMD-P2-011 | dualDown / allDown | IMPLEMENTED |
| L-CMD-P2-012 | dualDown / allDown | IMPLEMENTED |
| L-CMD-P2-013 | setMemory1 | IMPLEMENTED |
| L-CMD-P2-014 | setMemory1 | IMPLEMENTED |
| L-CMD-P2-015 | setMemory2 | IMPLEMENTED |
| L-CMD-P2-016 | setMemory2 | IMPLEMENTED |
| L-CMD-P2-017 | setMemory3 | EXCLUDED |
| L-CMD-P2-018 | setMemory3 | EXCLUDED |
| L-CMD-P2-019 | memory1 / Memory 1 | IMPLEMENTED |
| L-CMD-P2-020 | memory1 / Memory 1 | IMPLEMENTED |
| L-CMD-P2-021 | memory2 / Memory 2 | IMPLEMENTED |
| L-CMD-P2-022 | memory2 / Memory 2 | IMPLEMENTED |
| L-CMD-P2-023 | memory3 | EXCLUDED |
| L-CMD-P2-024 | memory3 | EXCLUDED |
| L-CMD-P2-025 | allFlat | IMPLEMENTED |
| L-CMD-P2-026 | allFlat | IMPLEMENTED |
| L-CMD-P2-027 | lightSwitch | IMPLEMENTED |
| L-CMD-P2-028 | lightSwitch | IMPLEMENTED |
| L-CMD-P2-029 | headTiltUp / fullTiltUp | IMPLEMENTED |
| L-CMD-P2-030 | headTiltUp / fullTiltUp | IMPLEMENTED |
| L-CMD-P2-031 | headTiltDown / fullTiltDown | IMPLEMENTED |
| L-CMD-P2-032 | headTiltDown / fullTiltDown | IMPLEMENTED |
| L-CMD-P2-033 | lumbarUp / tiltHeadUp | IMPLEMENTED |
| L-CMD-P2-034 | lumbarUp / tiltHeadUp | IMPLEMENTED |
| L-CMD-P2-035 | lumbarDown / tiltHeadDown | IMPLEMENTED |
| L-CMD-P2-036 | lumbarDown / tiltHeadDown | IMPLEMENTED |
| L-CMD-P2-037 | zeroG / Zero G / Oz Spine Relief | IMPLEMENTED |
| L-CMD-P2-038 | zeroG / Zero G / Oz Spine Relief | IMPLEMENTED |
| L-CMD-P2-039 | antiSnore / Anti Snore / Oz Anti Snore | IMPLEMENTED |
| L-CMD-P2-040 | antiSnore / Anti Snore / Oz Anti Snore | IMPLEMENTED |
| L-CMD-P2-041 | massageOff | IMPLEMENTED |
| L-CMD-P2-042 | massageOff | IMPLEMENTED |
| L-CMD-P2-043 | massageWave | IMPLEMENTED |
| L-CMD-P2-044 | massageWave | IMPLEMENTED |
| L-CMD-P2-045 | massageHead | IMPLEMENTED |
| L-CMD-P2-046 | massageHead | IMPLEMENTED |
| L-CMD-P2-047 | massageFoot | IMPLEMENTED |
| L-CMD-P2-048 | massageFoot | IMPLEMENTED |
| L-CMD-P2-049 | tvRead / TV Read / TV | IMPLEMENTED |
| L-CMD-P2-050 | tvRead / TV Read / TV | IMPLEMENTED |
| L-CMD-P2-051 | lounge / Lounge | IMPLEMENTED |
| L-CMD-P2-052 | lounge / Lounge | IMPLEMENTED |
| L-CMD-P2-053 | massage10 | IMPLEMENTED |
| L-CMD-P2-054 | massage10 | IMPLEMENTED |
| L-CMD-P2-055 | massage30 | IMPLEMENTED |
| L-CMD-P2-056 | massage30 | IMPLEMENTED |
| L-CMD-P2-057 | massage20 | IMPLEMENTED |
| L-CMD-P2-058 | massage20 | IMPLEMENTED |
| L-CMD-P2-059 | stopDriver | IMPLEMENTED |
| L-CMD-P2-060 | stopDriver | IMPLEMENTED |
| L-CMD-P2-061 | read [Premium preset attempted action] | EXCLUDED |
| L-CMD-P2-062 | read [Premium preset attempted action] | EXCLUDED |

Command-row total: 243 = 195 IMPLEMENTED + 48 EXCLUDED. Shared already-implemented facts are identified separately above.

## Candidate and model trace closure

The 19 Malouf and 133 Lucid candidate IDs retain their frozen meaning. Reachable
transport, packet, notification, model and action candidates are IMPLEMENTED by
the corresponding runtime rows above; OS/UI ownership is EXCLUDED with the
replacement boundary stated, and dead/unrelated paths remain EXCLUDED. Lucid's
52 `SEARCH-METHOD-*` candidates are authoritative method-owner cross-checks of
those same operations, not 52 extra command families. All are covered by this
mapping, including the corrected off/timer caller route.

| Member | Candidate IDs | Disposition |
|---|---|---|
| M | C01 | IMPLEMENTED: discovery |
| M | C02 | IMPLEMENTED: factory |
| M | C03 | IMPLEMENTED: factory |
| M | C04 | IMPLEMENTED: transport |
| M | C05 | IMPLEMENTED: transport |
| M | C06 | IMPLEMENTED: transport |
| M | C07 | IMPLEMENTED: transport |
| M | C08 | IMPLEMENTED: transport |
| M | C09 | IMPLEMENTED: device information |
| M | C10 | IMPLEMENTED: notifications |
| M | C11 | EXCLUDED: controller constants |
| M | C12 | IMPLEMENTED: model profiles |
| M | C13 | IMPLEMENTED: model profiles |
| M | C14 | IMPLEMENTED: automatic control trigger |
| M | C15 | EXCLUDED: native |
| M | C16 | EXCLUDED: native |
| M | C17 | EXCLUDED: Bluetooth Classic |
| M | C18 | EXCLUDED: firmware/DFU |
| M | C19 | EXCLUDED: controller constants |
| L | SCAN-START | IMPLEMENTED: scan |
| L | SCAN-STOP | IMPLEMENTED: scan |
| L | SCAN-CALLBACK | IMPLEMENTED: scan callback |
| L | PAIR-SELECT | IMPLEMENTED: setup UI |
| L | PAIR-TEST-HOLD | IMPLEMENTED: setup UI action |
| L | PAIR-TEST-BINDINGS | IMPLEMENTED: setup UI action |
| L | SERVICE-BIND | IMPLEMENTED: service lifecycle |
| L | BLUETOOTH-ACTIVITY-BIND | IMPLEMENTED: service lifecycle |
| L | SERVICE-FACTORY | IMPLEMENTED: factory |
| L | PROTOCOL-FACTORY | IMPLEMENTED: factory/model routing |
| L | CONNECT-GATT | IMPLEMENTED: connect |
| L | CONNECTION-CALLBACK | IMPLEMENTED: connect callback |
| L | DISCOVER-SERVICES | IMPLEMENTED: service discovery |
| L | DISCOVERY-DISPATCH | IMPLEMENTED: service discovery callback |
| L | CALLBACK-CHAR-WRITE | IMPLEMENTED: write callback |
| L | CALLBACK-DESC-WRITE | IMPLEMENTED: descriptor callback |
| L | CALLBACK-CHAR-READ-33 | IMPLEMENTED: read callback |
| L | CALLBACK-CHAR-READ-LEGACY | IMPLEMENTED: read callback |
| L | CALLBACK-DESC-READ-LEGACY | IMPLEMENTED: descriptor callback |
| L | CALLBACK-DESC-READ-33 | IMPLEMENTED: descriptor callback |
| L | DISCONNECT-GATT | IMPLEMENTED: disconnect |
| L | CLOSE-GATT | IMPLEMENTED: close |
| L | NOTIFY-LOCAL | IMPLEMENTED: notification setup |
| L | QUEUE-ADD-DESC-WRITE | IMPLEMENTED: queue |
| L | QUEUE-ADD-CHAR-WRITE | IMPLEMENTED: queue |
| L | QUEUE-ADD-CHAR-READ | IMPLEMENTED: queue |
| L | QUEUE-ADD-DESC-READ | IMPLEMENTED: queue |
| L | QUEUE-SERIALIZE | IMPLEMENTED: queue |
| L | REQUEST-TYPE-QUEUE | IMPLEMENTED: queue |
| L | BOUNDARY-READ-CHAR | IMPLEMENTED: transport boundary |
| L | BOUNDARY-READ-DESC | IMPLEMENTED: transport boundary |
| L | BOUNDARY-WRITE-CHAR | IMPLEMENTED: transport boundary |
| L | BOUNDARY-WRITE-DESC | IMPLEMENTED: transport boundary |
| L | SDK-SEND | IMPLEMENTED: command wrapper |
| L | SDK-SET-MEMORY | IMPLEMENTED: command wrapper |
| L | SDK-ALARM-NOTIFY | IMPLEMENTED: command wrapper |
| L | P1-SERVICE-SELECT | IMPLEMENTED: GATT selector |
| L | P1-PARSER-BODY-JAVA | IMPLEMENTED: massage/light notification parser |
| L | P1-PARSER-33 | IMPLEMENTED: notification parser |
| L | P1-PARSER-LEGACY | IMPLEMENTED: notification parser |
| L | P1-MASSAGE-HELPER-JAVA | IMPLEMENTED: massage notification parser |
| L | P1-LIGHT-HELPER-JAVA | IMPLEMENTED: under-bed-light notification parser |
| L | P1-PARSER-BODY-SMALI | IMPLEMENTED: massage/light notification parser |
| L | P1-MASSAGE-HELPER-SMALI | IMPLEMENTED: massage notification parser |
| L | P1-LIGHT-HELPER-SMALI | IMPLEMENTED: under-bed-light notification parser |
| L | P1-BUILDER | IMPLEMENTED: packet builder |
| L | P1-COMMAND-SWITCH | IMPLEMENTED: command branch |
| L | P1-MEMORY | IMPLEMENTED: memory programming |
| L | P1-NOTIFY-CCCD | IMPLEMENTED: notification/CCCD |
| L | P1-ALARM-QUERY | IMPLEMENTED: dynamic builders |
| L | P2-SERVICE-SELECT | IMPLEMENTED: GATT selector |
| L | P2-NO-NOTIFY | EXCLUDED: negative notification |
| L | P2-COMMAND-SWITCH | IMPLEMENTED: command branch |
| L | P2-MEMORY | IMPLEMENTED: memory programming |
| L | UI-MANUAL | IMPLEMENTED: UI action |
| L | UI-PRESET | IMPLEMENTED: UI action |
| L | UI-MASSAGE | IMPLEMENTED: UI action |
| L | UI-REMOTE-ROUTING | IMPLEMENTED: UI/config routing |
| L | UI-MEMORY-SAVE | IMPLEMENTED: UI action |
| L | BACKGROUND-SNORE | IMPLEMENTED: background action |
| L | BACKGROUND-SHORTCUT | IMPLEMENTED: background action |
| L | UI-ALARM-EDIT-CLEAR | IMPLEMENTED: dynamic alarm UI |
| L | UI-ALARM-ENABLE-CLEAR | IMPLEMENTED: dynamic alarm UI |
| L | UI-ALARM-PROGRAM | IMPLEMENTED: dynamic alarm/time route |
| L | ALARM-POSITION-ROUTING | IMPLEMENTED: dynamic alarm/time route |
| L | MODEL-RESTORE | IMPLEMENTED: model routing |
| L | MODEL-SELECTOR | IMPLEMENTED: model routing |
| L | CONFIG-SIDE | IMPLEMENTED: configuration routing |
| L | SERVICE-DISCONNECT-ALL | IMPLEMENTED: service cleanup |
| L | SERVICE-DISCONNECT-RECEIVER | IMPLEMENTED: service cleanup |
| L | SERVICE-DISCONNECT-REMOVE | IMPLEMENTED: service cleanup |
| L | DEAD-P1-intensityOne | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-intensityTwo | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-intensityThree | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-massageWaist | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-massageHeadMinus | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-massageFootMinus | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-massageAllOnOff | EXCLUDED: implementation-only command branch |
| L | DEAD-P1-massageAll | EXCLUDED: implementation-only command branch |
| L | DEAD-P2-setMemory3 | EXCLUDED: implementation-only command branch |
| L | DEAD-P2-memory3 | EXCLUDED: implementation-only command branch |

Lucid synthesized method-owner IDs (all mapped to the implemented operation or excluded platform boundary above):

`SEARCH-METHOD-02425875008A`, `SEARCH-METHOD-0A6EA26561CF`, `SEARCH-METHOD-0BEE5C2744E8`, `SEARCH-METHOD-0DFB114E0CC2`, `SEARCH-METHOD-156851EFCE12`, `SEARCH-METHOD-159FE2F68144`, `SEARCH-METHOD-1709651A0ACA`, `SEARCH-METHOD-1F514DA611F1`, `SEARCH-METHOD-1F9624753F8F`, `SEARCH-METHOD-26B2F479B414`, `SEARCH-METHOD-28CACCADFBE1`, `SEARCH-METHOD-2C6B031B8899`, `SEARCH-METHOD-30034EA332A6`, `SEARCH-METHOD-39C8B84CD69E`, `SEARCH-METHOD-3B0718AB2791`, `SEARCH-METHOD-3E0BFBD4FFD2`, `SEARCH-METHOD-3E322B81C107`, `SEARCH-METHOD-44CA45616894`, `SEARCH-METHOD-4AA46920F0BC`, `SEARCH-METHOD-51ACF76AA37F`, `SEARCH-METHOD-55F58210B441`, `SEARCH-METHOD-5DE9E9E2FEF6`, `SEARCH-METHOD-631C7BAA0D2E`, `SEARCH-METHOD-6EBD28037096`, `SEARCH-METHOD-6F8493B77A4D`, `SEARCH-METHOD-7219730D958C`, `SEARCH-METHOD-7647D211C8FB`, `SEARCH-METHOD-770CFAFFCAE0`, `SEARCH-METHOD-891E40CC8577`, `SEARCH-METHOD-89D197A7A0AF`, `SEARCH-METHOD-8BE301E5F594`, `SEARCH-METHOD-8C56E44E1C70`, `SEARCH-METHOD-8D215EFBF5FC`, `SEARCH-METHOD-9B817EE12B34`, `SEARCH-METHOD-9F782CA3F9D0`, `SEARCH-METHOD-A0B8D7F241F8`, `SEARCH-METHOD-A3A68710552D`, `SEARCH-METHOD-A6D488D8EBF7`, `SEARCH-METHOD-AE400548D1E5`, `SEARCH-METHOD-B009F9FE866C`, `SEARCH-METHOD-B687FA1161DF`, `SEARCH-METHOD-BE2560CCE9D2`, `SEARCH-METHOD-C155EB393A5C`, `SEARCH-METHOD-C575B67503D0`, `SEARCH-METHOD-D69766DA1492`, `SEARCH-METHOD-D8DE2221D0D3`, `SEARCH-METHOD-D96D858C0FF4`, `SEARCH-METHOD-DB62FE9AF1E9`, `SEARCH-METHOD-DF20CE740D5E`, `SEARCH-METHOD-E506A1D86A7A`, `SEARCH-METHOD-E80E5ACC315B`, `SEARCH-METHOD-F2E0E355499C`.

Lucid ACTION001–ACTION227 are exhausted by the 16-model table and exact command
intersection. MATCH routes are implemented; UNKNOWN/NO WRITE routes are excluded;
the eight off-labelled traces are corrected above. Malouf's 51 constructor preset
entries resolve through all nine exact preset literals, including its one MA01
unmatched Premium READ short-release disposition and live long-hold save alternative.
The three dynamic routes setCurrentTime, setAlarm and clearAlarm are implemented
with their separate add/edit, enable and active-delete preconditions. Physical
semantics remain deferred external validation after release, not an implementation
or evidence gate.
