# Ergomotion 4.0 3.7 dispositions (issue 558)

Separate post-freeze comparison of accepted `com.sfd.hump` 3.7 (65), not a new
clean-room analysis. Frozen evidence and its accepting audit were not modified.
The [machine ledger](issue558-ergomotion4.json) gives every item exactly one
disposition, exact package-local evidence and a concrete proof or boundary.
`proof_ref` and `reason_ref` resolve through the top-level lookup tables.

| Inventory | Count |
|-----------|------:|
| Candidate census | 423 |
| Eligible touch commands / shared actions | 373 / 12 |
| Controller routes / reachable routes | 27 / 25 |
| Catalog rows | 21 |
| Notification dispatch rows | 12 |
| Durable items (overlapping evidence coverage, not distinct commands) | 892 |
| IMPLEMENTED / ALREADY_IMPLEMENTED / EXCLUDED | 505 / 5 / 382 |

All 385 eligible command rows have an implemented disposition. Every one of the
21 acquired catalog rows has explicit selected-product gates, including
EZI MAID's M30 alias, 4194RGB's inverted format and ErgoBalance100's trailing
space. Conditional generic controls without a snapshot witness are available
only through explicit Other catalog product feature keys. Two permanently
hidden handlers remain excluded. The accepted source trace, not an inferred
family resemblance, determines each frame, release, timing and gate.

## Accepted identity

- Five-member Play artifact set: `cd637f0dec9831c9deb08f1449b2faf87c9dd70f511eaeb7210950c7a7eb69c0`.
- REPORT.SHA256: `221e356d9e6b88aaa68991d666a1bfa978ee5356be7c6da0447979b08ff09e7b`.
- analysis.json: `666fa3f03f9e8ec51c2323145fefd11653d2d16577148bd601e91172c3e37449`.
- Accepting AUDIT.SHA256: `9b317001ba212a9e58270b340c7ab1be45cbae7bb58f66b3b56bb6e522c8ae4d`; 17/17 PASS.
- Runtime catalog body: `2b9f12c5fb1857c2ca1268a7e6546b60f743caaa3d422c31d0bc0ae3e371af41` (21 rows).
- Acceptance record: `ACCEPTED-com.sfd.hump-3.7.json`, accepted 2026-11-04.
- Local run: `com.sfd.hump-3.7-2026-11-03-issue558-20261103-006`.

Report, audit and analysis digests match the supplied acceptance, and every
REPORT.SHA256/AUDIT.SHA256 member was reverified read-only before comparison.
Raw APKs, decompilation, frozen reports and this task's generator scripts remain
machine-local. Committed fixtures are minimal byte/timing test vectors, not
copies of the audit reports.

## Implementation decisions

- P1 Left=`02`, Right=`01`, Both=the eight-byte E5 frame, including every release.
  Use the existing opt-in native single-address child model and command-side
  ContextVar. Keeson Base and Ergomotion legacy entities retain their identities;
  incompatible P2/JSON/OEM profiles reject side addressing.
- Settings A/B -> selector00 is a proven app defect, explicitly excluded below.
  No physical A/B identity is inferred. Hardware mapping awaits real users.
- The complete app is separately selectable as Ergomotion 4.0, leaving earlier
  Keeson/Ergomotion, Ergomotion app B1/B2/C1/D1 and other closed fixes intact.
- Every app action uses a named button; held actions carry existing card/service
  metadata. No motor geometry or extra memory/program semantics are inferred.
- HA exposes decoded timer/light/RGB state even where the phone omits that
  layout from an icon-update overload. It never promotes discarded locals to
  measured motor positions. First-report RGB seeding is retained.
- HA owns scanning, pairing infrastructure, serialization, retries and lifecycle.
  Exact bed frames are retained while stale callbacks/cleanup cannot cross
  sessions. P2 queries are not replaced by invented STOP packets.
- Shared rename, clock and alarm frames remain callable on P2 layouts and have
  no side field. Their controls configure the physical receiver, not one half.
- Byte-exact 3.7 vectors cover 373 touch rows plus chords and P1 side variants,
  all parser dispatches, RGB/Java brightness and shared configuration. No older
  3.3 command is marked already implemented merely because its key matches.
  The narrow ALREADY_IMPLEMENTED transport rows identify unchanged HA connection
  ownership plus existing tests, not an assumed protocol implementation.

## Every exclusion

Each group below lists every excluded ledger ID. Its exact source/line and any
more specific accepting-audit reason are also retained on that item in JSON.
There are no exclusions for convenience, rare models, missing hardware or lack
of an entity. Wi-Fi provisioning was not found; network/cloud/OTA remain outside
the product boundary, not implementation debt.

### E_CLASSIC (48 items)

Classic RFCOMM is outside the BLE-only product boundary; the normal MainActivity forces BLE mode. No Classic pairing/retry/command path is shipped.

`candidate:T013`, `candidate:T014`, `candidate:T015`, `candidate:T016`, `candidate:T017`, `candidate:T018`, `candidate:T019`, `candidate:T020`, `candidate:T021`, `candidate:T022`, `candidate:T023`, `candidate:T024`, `candidate:T025`, `candidate:T026`, `candidate:T027`, `candidate:T028`, `candidate:T029`, `candidate:T030`, `candidate:T031`, `candidate:T032`, `candidate:T033`, `candidate:T034`, `candidate:T035`, `candidate:T036`, `candidate:T037`, `candidate:T038`, `candidate:T039`, `candidate:T040`, `candidate:T041`, `candidate:T042`, `candidate:T060`, `candidate:T061`, `candidate:T062`, `candidate:T063`, `candidate:T064`, `candidate:T065`, `candidate:T066`, `candidate:T067`, `candidate:T068`, `candidate:T069`, `candidate:T070`, `candidate:T071`, `candidate:T072`, `candidate:T073`, `candidate:T074`, `candidate:T075`, `candidate:T076`, `candidate:CLASSIC`.

### E_DFU (151 items)

Vendor firmware transfer, bootloader, updater and OTA/DFU are outside direct bed control. Normal BLE name gates and meditation command availability are implemented separately.

`candidate:T099`, `candidate:T100`, `candidate:T101`, `candidate:T102`, `candidate:T103`, `candidate:T104`, `candidate:T105`, `candidate:T106`, `candidate:T107`, `candidate:T108`, `candidate:T109`, `candidate:T110`, `candidate:T111`, `candidate:T112`, `candidate:T113`, `candidate:T114`, `candidate:T115`, `candidate:T116`, `candidate:T117`, `candidate:T118`, `candidate:T119`, `candidate:T120`, `candidate:T121`, `candidate:T122`, `candidate:T123`, `candidate:T124`, `candidate:T125`, `candidate:T126`, `candidate:T127`, `candidate:T128`, `candidate:T129`, `candidate:T130`, `candidate:T131`, `candidate:T132`, `candidate:T133`, `candidate:T134`, `candidate:T135`, `candidate:T136`, `candidate:T137`, `candidate:T138`, `candidate:T139`, `candidate:T140`, `candidate:T141`, `candidate:T142`, `candidate:T143`, `candidate:T144`, `candidate:T145`, `candidate:T146`, `candidate:T147`, `candidate:T148`, `candidate:T149`, `candidate:T150`, `candidate:T151`, `candidate:T152`, `candidate:T153`, `candidate:T154`, `candidate:T155`, `candidate:T156`, `candidate:T157`, `candidate:T158`, `candidate:T159`, `candidate:T160`, `candidate:T161`, `candidate:T162`, `candidate:T163`, `candidate:T164`, `candidate:T165`, `candidate:T166`, `candidate:T167`, `candidate:T168`, `candidate:T169`, `candidate:T170`, `candidate:T171`, `candidate:T172`, `candidate:T173`, `candidate:T174`, `candidate:T175`, `candidate:T176`, `candidate:T177`, `candidate:T178`, `candidate:T179`, `candidate:T180`, `candidate:T181`, `candidate:T182`, `candidate:T183`, `candidate:T184`, `candidate:T185`, `candidate:T186`, `candidate:T187`, `candidate:T188`, `candidate:T189`, `candidate:T190`, `candidate:T191`, `candidate:T192`, `candidate:T193`, `candidate:T194`, `candidate:T195`, `candidate:T196`, `candidate:T197`, `candidate:T198`, `candidate:T199`, `candidate:T200`, `candidate:T201`, `candidate:T202`, `candidate:T203`, `candidate:T204`, `candidate:T205`, `candidate:T206`, `candidate:T207`, `candidate:T208`, `candidate:T209`, `candidate:T210`, `candidate:T211`, `candidate:T212`, `candidate:T213`, `candidate:T214`, `candidate:T215`, `candidate:T216`, `candidate:T217`, `candidate:T218`, `candidate:T219`, `candidate:T220`, `candidate:T221`, `candidate:T222`, `candidate:T223`, `candidate:T224`, `candidate:T225`, `candidate:T226`, `candidate:T227`, `candidate:T228`, `candidate:T229`, `candidate:T230`, `candidate:T231`, `candidate:T232`, `candidate:T233`, `candidate:T234`, `candidate:T235`, `candidate:T236`, `candidate:T237`, `candidate:T238`, `candidate:T239`, `candidate:T240`, `candidate:T241`, `candidate:T242`, `candidate:T243`, `candidate:T244`, `candidate:T245`, `candidate:T246`, `candidate:T247`, `candidate:T248`, `candidate:DFU`.

### E_PHONE (22 items)

Android permissions, phone adapter enable/disable, scan-screen timing, broadcast/callback plumbing, UI/lifecycle and phone-only metadata are host-platform machinery. HA retains its existing Bluetooth adapters/proxies and manual setup; no phone-system administration feature is ported.

`candidate:T001`, `candidate:T002`, `candidate:T003`, `candidate:T004`, `candidate:T005`, `candidate:T006`, `candidate:T007`, `candidate:T008`, `candidate:T009`, `candidate:T010`, `candidate:T011`, `candidate:T012`, `candidate:T052`, `candidate:T053`, `candidate:T054`, `candidate:T055`, `candidate:T056`, `candidate:T057`, `candidate:T058`, `candidate:T059`, `candidate:T077`, `candidate:T095`.

### E_DEAD (145 items)

The accepting audit proves no live constructor, selector, handler binding or visible ancestor path. Dead/unbound code grants no control or capability.

`candidate:V05`, `candidate:V06`, `candidate:T078`, `candidate:T080`, `candidate:T093`, `candidate:T096`, `candidate:T097`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btnLevel`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btnM`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btnMusic`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btnReset`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btn_anti_snore`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btn_read`, `candidate:UI-DEAD-RemoteDefaultFragmentSec-btn_tv`, `candidate:TAG-DEAD-RemoteM14Fragment-btnAntiSnore`, `candidate:TAG-DEAD-RemoteM14Fragment-btnLumbarDown`, `candidate:TAG-DEAD-RemoteM14Fragment-btnLumbarUp`, `candidate:TAG-DEAD-RemoteM14Fragment-btnMeditation`, `candidate:TAG-DEAD-RemoteM14Fragment-btnMusic`, `candidate:UI-DEAD-RemoteM15Fragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM15Fragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM15Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM15Fragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM15Fragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM15Fragment-btn_light`, `candidate:UI-DEAD-RemoteM15Fragment-btn_read`, `candidate:TAG-DEAD-RemoteM16Fragment-btnAllMassage`, `candidate:TAG-DEAD-RemoteM16Fragment-btnAntiSnore`, `candidate:TAG-DEAD-RemoteM16Fragment-btnLumbarDown`, `candidate:TAG-DEAD-RemoteM16Fragment-btnLumbarUp`, `candidate:TAG-DEAD-RemoteM16Fragment-btnMeditation`, `candidate:TAG-DEAD-RemoteM16Fragment-btnMusic`, `candidate:TAG-DEAD-RemoteM16Fragment-btnZg`, `candidate:TAG-DEAD-RemoteM17Fragment-btnAllMassage`, `candidate:TAG-DEAD-RemoteM17Fragment-btnMusic`, `candidate:UI-DEAD-RemoteM18Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM18Fragment-btnM`, `candidate:UI-DEAD-RemoteM18Fragment-btnReset`, `candidate:UI-DEAD-RemoteM18Fragment-btn_anti_snore`, `candidate:UI-DEAD-RemoteM18Fragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM18Fragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM18Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM18Fragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM18Fragment-btn_head_tilt_down`, `candidate:UI-DEAD-RemoteM18Fragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM18Fragment-btn_massage_head`, `candidate:UI-DEAD-RemoteM18Fragment-btn_massage_timer`, `candidate:UI-DEAD-RemoteM19Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM19Fragment-btnM`, `candidate:UI-DEAD-RemoteM19Fragment-btnReset`, `candidate:UI-DEAD-RemoteM19Fragment-btn_anti_snore`, `candidate:UI-DEAD-RemoteM19Fragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM19Fragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM19Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM19Fragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM19Fragment-btn_head_tilt_down`, `candidate:UI-DEAD-RemoteM19Fragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM19Fragment-btn_massage_foot`, `candidate:UI-DEAD-RemoteM19Fragment-btn_massage_head`, `candidate:UI-DEAD-RemoteM19Fragment-btn_massage_timer`, `candidate:UI-DEAD-RemoteM20Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM20Fragment-btnM`, `candidate:UI-DEAD-RemoteM20Fragment-btnMusic`, `candidate:UI-DEAD-RemoteM20Fragment-btnReset`, `candidate:UI-DEAD-RemoteM20Fragment-btn_anti_snore`, `candidate:UI-DEAD-RemoteM20Fragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM20Fragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM20Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM20Fragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM20Fragment-btn_head_tilt_down`, `candidate:UI-DEAD-RemoteM20Fragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM20Fragment-btn_light`, `candidate:UI-DEAD-RemoteM20Fragment-btn_massage_foot`, `candidate:UI-DEAD-RemoteM20Fragment-btn_massage_head`, `candidate:UI-DEAD-RemoteM20Fragment-btn_massage_timer`, `candidate:UI-DEAD-RemoteM20Fragment-btn_read`, `candidate:UI-DEAD-RemoteM20Fragment-btn_tv`, `candidate:UI-DEAD-RemoteM21Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM21Fragment-btnM`, `candidate:UI-DEAD-RemoteM21Fragment-btnReset`, `candidate:UI-DEAD-RemoteM21Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM21Fragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM21Fragment-btn_head_tilt_down`, `candidate:UI-DEAD-RemoteM21Fragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM21Fragment-btn_massage_head`, `candidate:UI-DEAD-RemoteM21Fragment-btn_massage_timer`, `candidate:UI-DEAD-RemoteM22DemoFragment-btnLevel`, `candidate:UI-DEAD-RemoteM22DemoFragment-btnM`, `candidate:UI-DEAD-RemoteM22DemoFragment-btnMusic`, `candidate:UI-DEAD-RemoteM22DemoFragment-btnReset`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_anti_snore`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_foot_down`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_foot_up`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_head_down`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_head_tilt_down`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_head_up`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_light`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_massage_timer`, `candidate:UI-DEAD-RemoteM22DemoFragment-btn_tv`, `candidate:UI-DEAD-RemoteM30Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM30Fragment-btnM`, `candidate:UI-DEAD-RemoteM30Fragment-btnMusic`, `candidate:UI-DEAD-RemoteM30Fragment-btnReset`, `candidate:UI-DEAD-RemoteM30Fragment-btn_anti_snore`, `candidate:UI-DEAD-RemoteM30Fragment-btn_flat`, `candidate:UI-DEAD-RemoteM30Fragment-btn_foot_down`, `candidate:UI-DEAD-RemoteM30Fragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM30Fragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM30Fragment-btn_foot_up`, `candidate:UI-DEAD-RemoteM30Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM30Fragment-btn_head_foot_up`, `candidate:UI-DEAD-RemoteM30Fragment-btn_head_tilt_down`, `candidate:UI-DEAD-RemoteM30Fragment-btn_head_tilt_up`, `candidate:UI-DEAD-RemoteM30Fragment-btn_light`, `candidate:UI-DEAD-RemoteM30Fragment-btn_massage_foot`, `candidate:UI-DEAD-RemoteM30Fragment-btn_massage_head`, `candidate:UI-DEAD-RemoteM30Fragment-btn_massage_timer`, `candidate:UI-DEAD-RemoteM30Fragment-btn_read`, `candidate:UI-DEAD-RemoteM30Fragment-btn_tv`, `candidate:UI-DEAD-RemoteM30Fragment-btn_zerog`, `candidate:UI-DEAD-RemoteM6Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM6Fragment-btnM`, `candidate:UI-DEAD-RemoteM6Fragment-btnMusic`, `candidate:UI-DEAD-RemoteM6Fragment-btnReset`, `candidate:TAG-DEAD-RemoteM7Fragment-btnLumbarDown`, `candidate:TAG-DEAD-RemoteM7Fragment-btnLumbarUp`, `candidate:UI-DEAD-RemoteM8Fragment-btnLevel`, `candidate:UI-DEAD-RemoteM8Fragment-btnM`, `candidate:UI-DEAD-RemoteM8Fragment-btnMusic`, `candidate:UI-DEAD-RemoteM8Fragment-btnReset`, `candidate:UI-DEAD-RemoteM8Fragment-btn_foot_tilt_down`, `candidate:UI-DEAD-RemoteM8Fragment-btn_foot_tilt_up`, `candidate:UI-DEAD-RemoteM8Fragment-btn_head_foot_down`, `candidate:UI-DEAD-RemoteM8Fragment-btn_head_foot_up`, `candidate:TAG-DEAD-RemoteM9Fragment-btnLumbarDown`, `candidate:TAG-DEAD-RemoteM9Fragment-btnLumbarUp`, `candidate:TAG-DEAD-RemoteM9Fragment-btnMusic`, `candidate:M14-LEGACY-DFU`, `route:V05`, `route:V06`.

### E_HIDDEN (2 items)

Bound handler is permanently hidden by its effective parent/view visibility (C109 or C347); synthetic direct invocation is not a reachable user control.

`candidate:HIDDEN-C109`, `candidate:HIDDEN-C347`.

### E_CRC (1 items)

CRC16 belongs to the dead P3 controller; no reachable normal BLE frame uses it.

`candidate:CRC`.

### E_INFO (1 items)

Unused Device Information UUIDs/read helpers have no reachable normal-control read or parser; do not invent serial, battery or firmware sensors.

`candidate:DIS`.

### E_DISCARDED (2 items)

Values are loaded only into discarded locals or an empty updateDeviceStatus helper. No reachable bed-position/state effect exists.

`candidate:T086`, `candidate:STATUS-NOOP`.

### E_CLOUD (1 items)

HTTP catalog acquisition is frozen evidence only. Online catalog refresh, cloud/account/auth/weather and network administration are outside the direct BLE integration. All 21 acquired local capability rows are implemented.

`candidate:CLOUD`.

### E_LOCATION (2 items)

JNI/location/Android location-library behavior is unrelated to bed BLE control.

`candidate:NATIVE-LOC`, `candidate:NATIVE-INDOOR`.

### E_PERSISTENCE (1 items)

JNI Realm persistence is phone application infrastructure. Explicit HA per-address/profile configuration replaces it without a bed command.

`candidate:NATIVE-REALM`.

### E_SELECTOR_BUG (1 items)

Settings A/B strings yield side byte 00 because the builder only recognizes Left/Right. HA exposes the proven Left=02/Right=01 selectors and native Both; reproducing the mismatched strings would select an unintended side.

`boundary:E_SELECTOR_BUG`.

### E_NAME_OVERFLOW (1 items)

More than 16 UTF-16 units overrun the source 18-byte name array. Reject before any write; retain the source 16-unit checksum overwrite and non-ASCII byte truncation for valid-size input.

`boundary:E_NAME_OVERFLOW`.

### E_ALARM_INVALID (1 items)

Past/same-time or ambiguous/nonexistent local one-time alarm targets have unsafe Android date/countdown behavior. Require future same-day unambiguous targets and validate both three-slot tables before any write; valid artifact vectors remain byte-exact.

`boundary:E_ALARM_INVALID`.

### E_QUEUE_BUG (1 items)

The app queues repeated references to one mutable characteristic and disconnects after queue overflow, allowing later setValue calls to change pending movement. HA serializes immutable frames and binds cleanup to the original session, preventing stale motion after cancellation/reconnect.

`boundary:E_QUEUE_BUG`.

### E_PICKER (1 items)

The phone bitmap picker, image density, out-of-bounds getPixel crash, Android fromUser/listener restoration and haptic/audio/countdown presentation are phone UI. HA RGB inputs and brightness preserve all reachable BLE color writes; HA automation can repeat the proven meditation start frame.

`boundary:E_PICKER`.

### E_O5 (1 items)

The generic o5 preset tag is assigned/visible but has no command branch. No BLE action is invented for it.

`boundary:E_O5`.

## Validation and deferred hardware checks

Focused conformance lives in `tests/test_ergomotion4.py` and
`tests/fixtures/ergomotion4/`. Existing Keeson, paired registry/runtime, setup,
controller contracts, service validation and documentation checks cover the
surrounding integration. This ledger is checked for total/source coverage.

Only physical/ATT/firmware acceptance remains deferred: receiver identity,
Left/Right orientation, actual motor and preset effects, release semantics,
notifications, RGB, rename and alarm behavior. Those are real-user checks after
a beta/release, never a maintainer acquisition or immediate hardware-test task.

User guide: [Ergomotion 4.0](../../beds/ergomotion-4.md).
Ref [#558](https://github.com/kristofferR/ha-adjustable-bed/issues/558).
