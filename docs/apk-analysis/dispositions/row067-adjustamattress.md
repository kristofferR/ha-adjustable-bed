# Row067 AdjustaMattress implementation dispositions

Package `com.okin.adjustamattress` 1.6.0 (10), standalone FULL. This is the
post-freeze comparison and implementation record, not a clean-room report.
The accepted artifact/report/work/audit originals are preserved machine-locally.
Only derived implementation references, focused vectors, code and docs are committed.

| Accepted identity | SHA256 |
| --- | --- |
| Artifact set | `bff51c93b65b5236884608ceb941a6e0bb23ac36cb52f7e852c3d99d919822fb` |
| Report manifest, 45 entries | `69d851737cb7aa08716a98d594cdb8cf45bb20eb4a13d5a825835eb7486e7da4` |
| Work manifest, 126 entries | `6f3e687540f6790e5b572f1ec0b181169d0d55307f8915a9dc72822fe488aa91` |
| Independent FULL audit RESULT.json, 17 PASS / no findings | `c735a872b3c721c50f2320354ee305bac7c408a3df3f5d4de6563470f030c447` |
| Audit manifest, 153 entries | `cd5c6829df936b209919c4f8a6a6a50db226450d9594152812592c5cb45de5aa` |

Acceptance is the coordinator's receipt, not the older proposal-language status
inside the immutable report. The historical round02 temporary-cache ownership
deviation remains disclosed and was independently assessed. Nothing here
retroactively alters that adjudication or describes this comparison as clean-room.

## Complete discovery index

The [machine-readable ledger](row067-adjustamattress-ledger.json) gives every
accepted inventory item exactly one rule/disposition. A rule supplies the reason,
accepted evidence IDs, concrete source methods and focused tests. Repeated source,
method, phase and candidate references are separate inventory records, not new
features. File inventory IDs include the accepted row index because identical
source hashes can occur in multiple paths.

| Inventory | Records |
| --- | ---: |
| Command/vector rows | 180 |
| Exact method/model branches, including aliases and dormant branches | 180 |
| Four models × seven layouts | 28 |
| Source controls / source phases | 94 / 470 |
| Selected variant control-phase instances / conditional action records | 2235 / 2576 |
| Non-ImageButton handlers | 79 |
| Native Bluetooth sites / endpoints / reflection operations | 292 / 30 / 4 |
| Search candidates | 22019 |
| Source inventory / archive inventory | 11949 / 515 |
| Additional explicit safety/product-boundary dispositions | 7 |
| Total indexed records | 40658 |

The accepted closure also covers all 414 app functions, 6814 Dart functions,
234 BLE bridge functions, 117 literal plus 14 dynamic packet-array sites and
40 search families with 1705141 joined results. These are joined through the
candidate/source inventories, not sampled into new competing inventories.
There are **5741 IMPLEMENTED**, **34917 EXCLUDED**, and **0 ALREADY_IMPLEMENTED**
index records. All protocol behavior is implemented by the new explicit app
profile. Existing controllers with matching UUIDs are not claimed equivalent.
Support/index containers and Android/phone machinery are excluded as unrelated
infrastructure, with their actual bed-facing children separately accounted for.

## Reachable BLE behavior

| Discovery | Disposition and implementation evidence |
| --- | --- |
| Four model constructors, case-sensitive name versus scan admission, FFF0 mutation, seven independently selected layouts | IMPLEMENTED: `model_from_name`, `scan_admits`, `async_discover_capabilities`, `ADJUSTAMATTRESS_VARIANTS`; all 28 gate/role/entity tests and name/GATT tests |
| Every static/dynamic command, odd P4 wave and model-independent lift frames, checksum before Uint8List truncation, year/month/weekday differences | IMPLEMENTED: `adjustamattress_protocol.frame`; all 180 exact command vectors. Dormant callbacks remain builder-test evidence and never enable controls |
| Press/release/cancel/pressed-dispose/non-resumed behavior | IMPLEMENTED: finite `hold_control`, shielded `_release`, native cover/button hold metadata and existing card lifecycle handling. Tests cover held timing, cancellation, all four ordinary massage actions and model-specific cleanup |
| Four ordinary massage releases with P3/P4 guarded +400/+600 ms query edges | IMPLEMENTED: `_release(massage=True)`, tested for all four actions and all four models. P1/P2 have no release query |
| Dedicated P2 head/foot/wave selectors and timer commands, only L0/L1/L2/L3/L5 | IMPLEMENTED: model/layout-gated native selects/buttons. Tests call native HA entities through the coordinator and revalidate live capabilities |
| Alarm draft edits, enabled-edit guard, explicit enable/disable commit, P2 sentinel, +400 ms query builder/+600 ms submission | IMPLEMENTED: `set_number`, `local_setting`, `set_setting`, `_send_delayed`; exact vectors and native settings tests |
| Privacy local prerequisite/persistence, local strength index, enable/demo interaction | IMPLEMENTED: local select callbacks, persisted app state, `set_setting`, `_send_snore`; no privacy command or PIN is invented |
| P4 L0/L3 sleep prelude, retained demo, forced strength/threshold, sleeping feedback, +500 ms status query | IMPLEMENTED: `_refresh_sleep_state` requires a fresh P4 report before `_toggle_sleep`; a bounded HA readiness guard never guesses on timeout. Tests cover reconnect defaults, no-reply/cancellation and all 32 accepted boolean/strength state combinations. Non-P4 local-only method has no stable tab route and is EXCLUDED |
| All valid notification fields, byte order and model-specific level remapping | IMPLEMENTED: `parse` and native reported sensors. Focused vectors include malformed values, P1 fragmentation, on-only alarm state, P4 busy expiry/disconnect cleanup |
| Query/status/init hydration, notify prerequisite, with-response forwarding | IMPLEMENTED: explicit refresh buttons, startup subscription/hydration, exact GATT role checks. No-write branches and dormant native endpoints are EXCLUDED |
| One active physical destination; no wire side/A/B field | IMPLEMENTED: single-address pairing disabled; ordinary HA two-address pairs retain separate physical controllers and per-side variant configuration |

## Precise exclusions and adaptations

| Evidence | EXCLUDED behavior and reason |
| --- | --- |
| `E_R2_LIGHTING`, `0x2ce14c/0x2ce158/0x2ce180`, all five normal P2 lighting variants | **Safety:** the action submits the retained arbitrary command, potentially movement, and starts 200 ms refresh. No light opcode exists. P2 lighting is absent and cannot be invoked through hold/action validation; no substitute bytes are invented |
| Dedicated P2 timer release/cancel/dispose/lifecycle callbacks; `E_PERIOD` | **Safety:** unbounded orphaned refresh is excluded. The evidenced timer bytes remain available as a finite action with the exact model STOP; no other-model dormant timer is promoted |
| `E_PERIOD`, `E_R2_RELEASE`, session disconnect sequence | **Safety:** shared mutable cross-operation buffers, delayed STOP replacement and refresh surviving disconnect are excluded. The complete operation owns the command lock and immutable bytes through cancellation-safe cleanup |
| `NONIMAGE/0x3f77d4`, `NONIMAGE/0x34aafc`, `E_PERIOD` | **Unrelated companion UI scheduling and safety:** phone page/tab/HomeBloc timers are not HA pages. They can replace the active shared movement frame and pending STOP. Native explicit alarm/massage/status queries retain the bed-facing function; they cannot replace another operation's frame |
| `E_PARSE`, parser boundary fixtures | **Safety/correctness:** indexed-read crashes, zeroing state on unknown fragments and suppressed valid on-only callbacks are app defects. Complete valid fields are parsed; incomplete frames cause no partial mutation; no physical status meaning is inferred |
| 49 stable model/method exclusions, false per-variant guards, 18 dormant native endpoints, four reflection sites | **Dead/unused path:** stale callback construction and generic native endpoint presence do not establish a normal app capability. Byte vectors retain evidence; the selected layout/model remains authoritative |
| `FEATURE-DOMAINS.md`, exact complete app writer/UUID/native closure | **Product boundary:** bed Wi-Fi provisioning, SSID/password, network administration, cloud/account/credentials and unrelated companion services remain excluded, even over BLE. No app-owned BLE command for these exists in this artifact; generic SDK/engine networking is unrelated evidence |
| Native endpoint/site inventories, Android launcher and SDK inventories | **Unrelated platform infrastructure:** Android permissions, location prompts, MTU/PHY/scan filters, MethodChannel implementation, native cache/bond/storage/plugin operations and rendering resources are not HA bed commands. HA/Bleak owns scanning, connection/proxy/adapter policy and CCCD details; the app's local BLE role/notify/write prerequisites are implemented |
| No reachable writer/parser/UI action in accepted closure | No invented memory save/M2-M4, firmware/OTA/reset, measured angle/percent/height/current, occupancy meaning for auxiliary bit, brightness/RGB or protocol authentication. This is a scoped negative boundary, not implementation debt |

No exclusion uses missing hardware, presumed model prevalence, convenience or
lack of an existing entity as its reason. Physical behavior remains unverified
and is deferred to real users after beta/release. No bed was physically operated.

## Validation

`tests/test_adjustamattress.py` covers the complete concrete command/vector table,
all 28 layout/model gates, constructor/scan/GATT differences, role rejection,
with-response writes, bounded notification retry, startup hydration, cancellation
cleanup, all ordinary massage releases, native entity dispatch/profile changes,
alarm/drafts/privacy, all 32 sleep states, parser fields and lifecycle cleanup.
Shared controller/entity/action/service/profile tests exercise the integration
contracts. Frontend discovery tests group every new native entity class, and the
committed bundle is rebuilt with typecheck/build and the frontend test suite.
No physical validation or full-suite claim is implied by these focused checks.
