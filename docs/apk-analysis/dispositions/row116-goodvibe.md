# Row116: Good Vibe Sleep implementation ledger

This is the post-freeze comparison of `com.richmat.goodvibesleep` 2.0.1 / code 20103. It covers the accepted standalone FULL unit, all 1,279 inventory IDs, 20 shards, 21 reports and 27 alias edges. The [bed guide](../../beds/goodvibe.md) is the user-facing protocol reference. These indexes retain evidence and dispositions separately from that guide.

This ledger records implemented behavior and explicit exclusions. The machine-local accepted reports remain immutable; this document does not replace or amend their acceptance.

## Identity and acceptance

| Item | SHA-256 / result |
|------|------------------|
| Artifact set | `d18aa9c204ed63a904e6c9c2836d47e80647cb78408a6f6535936a865535fc04` |
| ROOT acceptance receipt | `e6107397e505113af95fd07c95750c228deb3486829e5f51d0be1c2aa467389b` |
| Accepted `REPORT.SHA256` | `e9c7ae6768796a7d8c025823ea41ec77579acb1efe463c8423117fa23fffd6ba` |
| Accepted `analysis.json` | `e41b32beb33cfd8fe89ce8ef4544b9072bcded5be10a6bcfc8f57d9d7d39e995` |
| Accepted reproducer archive | `aa34e86f1c7f0d75aea8d94bcc41d6f52c6f57c5c065cf6f207fba6595f8050c` |
| Audit005 `AUDIT.SHA256` | `7cc32faf583a3e9cd0400c13c57edb98043e6696a9e1dbb2f87911058b7c19fe` |
| Source manifest | `6d83461445210bdf06fa7fbd92cc0a731392e968f3ff999dce7338d11a16a094` |
| Input manifest | `8c6be61c18aaba6c3a912277abdafba69b93ec1dd1cc73dffcc1d58367e9ec43` |
| Formal audit result | ACCEPT, 17 PASS, 0 FAIL, 0 UNKNOWN |

The artifact delivery contains five APKs and one DM sidecar. It is the configured account/device delivery recorded on 2026-11-03, without a claim of universal rollout/ABI completeness. Before comparison, the implementation pass independently checked the acceptance receipt, all direct seals, every 621 report / 20 audit / 33,630 source / 90 input manifest members, six artifact members, source-region dependencies and all 55 audit-declared transitive seals and their members (39,479 distinct files in that transitive check). Original paths and evidence bytes were not changed or replaced. The corrected SOURCE-relative-base retry is disclosed in the local verification receipt.

The accepted report is `work/report-repair-sol-003` under the package-local run `com.richmat.goodvibesleep-2.0.1-2026-11-03-bulk101-188-001`. Source paths/RVAs in the indexes are relative to that run. Root acceptance is authoritative even where the immutable author report's historical metadata still says it is awaiting acceptance.

## Exhaustive indexes

| Index | Scope |
|-------|-------|
| [Inventory](row116-goodvibe/inventory.csv) | Every exact accepted inventory ID, shard, source, field/getter-proof hash, disposition and implementation/test binding |
| [Common surfaces](row116-goodvibe/surfaces.csv) | All 1,543 accepted candidate rows, including native transport, UUIDs, builders, binary/JSON parsers, 35 common fields and lifecycle dependencies |
| [Commands](row116-goodvibe/commands.csv) | Every accepted command row plus the 23 explicitly labelled, derived current alarm-only descriptors and five constructed Y6RM menu descendants; exact values, ownership and dispositions |
| [JSON fields](row116-goodvibe/json-fields.csv) | All 259 fields across 62 typed constructors, with exact source line, raw-region hash, cast and nested-call binding |
| [Callers and consumers](row116-goodvibe/callers.csv) | All 65 individual normal builder/wrapper/caller edges, 54 sleep dispatcher callsites, 18 normal event registrations, 96 sleep subscriptions and 30 stream owners |
| [Field policies](row116-goodvibe/field-policies.csv) | The 35 shared field policies with exact runtime and test bindings |
| [Product fields](row116-goodvibe/product-fields.csv) | All 42,560 selector/field comparisons, exact value and getter-proof hashes, source pointer and policy binding |
| [Descriptor field policies](row116-goodvibe/descriptor-field-policies.csv) | Every one of the 22 descriptor constructor fields, separating packet/gesture/state fields from phone presentation |
| [Descriptor fields](row116-goodvibe/descriptor-fields.csv) | All 29,780 descriptor/field occurrences, including 177 catalog-only descriptors and local-menu primaries, with exact values hash-bound to source |
| [Constructed Y6RM controls](row116-goodvibe/derived-menu-controls.csv) | Five exact menu descendants with constructor hashes, object defaults, packet operands, gestures and public paths |
| [Constructed Y6RM fields](row116-goodvibe/derived-menu-fields.csv) | All 95 assigned inline constructor fields, including their phone-presentation exclusions |
| [Every exclusion](row116-goodvibe/exclusions.csv) | Complete exclusion list with index, exact ID, source and reason |
| [Counts and identity](row116-goodvibe/index.json) | Machine-readable counts per index, with overlap kept explicit |

Indexes overlap deliberately: a selected product has an inventory row and a candidate-surface row, for example. Their counts must not be added as a count of distinct products. Each row has exactly one of `IMPLEMENTED`, `ALREADY_IMPLEMENTED` or `EXCLUDED`. This change credits no blanket `ALREADY_IMPLEMENTED` behavior to another protocol family.

The 35 common fields divide at the shipped app's actual 12 getters. The active fields are app admission, name, sides, normal configuration choices, current details layout, remote aliases, alarm list, repeat-alarm support, BLE sleep type, light presence/display type and bottom massage countdown. Unconsumed catalog lists and richmat-flavor flags are excluded with their own source rows. Per-selector field and getter-proof hashes bind the complete values; the independently derived product fixture checks every selected profile's runtime values. No catalog-only field promotes an extra control.

## Implementation paths

- [`goodvibe_catalog.py`](../../../custom_components/adjustable_bed/goodvibe_catalog.py) contains the exact admitted products, four active normal configuration branches, all 27 remote/image aliases and current layout/alarm descriptors. Static choices remain distinct from GATT selection. The two sleep choices use separate physical-device entries.
- [`goodvibe_discovery.py`](../../../custom_components/adjustable_bed/goodvibe_discovery.py) preserves the source name predicate, aliases and prefix suggestions. `detection.py` adds app hints while keeping an existing receiver/app winner. Setup requires an explicit product choice; shared transport does not choose an app layout.
- [`goodvibe.py`](../../../custom_components/adjustable_bed/beds/goodvibe.py) owns selected-link identities, source gestures, release frames, process-local UI choices, notification callbacks, sleep live polling, report transactions and typed state publication. `controller_factory.py`, `config_flow.py`, `validators.py` and `app_profiles.py` wire those profiles through real HA setup and options.
- [`goodvibe_protocol.py`](../../../custom_components/adjustable_bed/goodvibe_protocol.py) owns this unit's dedicated settings, checksums and sleep envelope. No sibling's command values or timing were imported. Every current action's 12 framed/legacy/side/short/long alternatives are checked against independent accepted vectors.
- [`goodvibe_receive.py`](../../../custom_components/adjustable_bed/goodvibe_receive.py), [`goodvibe_schemas.py`](../../../custom_components/adjustable_bed/goodvibe_schemas.py) and [`goodvibe_sleep.py`](../../../custom_components/adjustable_bed/goodvibe_sleep.py) retain framing, parser bounds, casts, nested report schemas and retained UI state. They reject malformed or non-progressing input rather than inventing missing fields.
- [`goodvibe_services.py`](../../../custom_components/adjustable_bed/goodvibe_services.py) exposes exact app configuration through `adjustable_bed.goodvibe`, with per-product validation before any target writes. Dynamic buttons, selects, numbers and status/live sensors use the existing typed entity contracts. The card discovers their stable translation keys.

### Lifecycle and state

The source app's active futures, shared queue/buffer, per-write mutex and unretained transmitter timer are accounted for independently of packet construction. The integration owns a cancellable HA operation for each user action. It awaits each write, stops unsent chunks after cancellation, and uses a fresh cleanup path for the exact normal release frame. It does not claim that source STOP preempts already invoked writes or that clearing an app queue cancels an Android write.

`app_session` separates physical address and selected app profile. Normal selected side, release/hold/memory choices, selected massage countdown and sleep sequence state survive BLE controller replacement and quick handoff. Changing profile/address starts an isolated process-local view. Only the app's durable single-alarm and light preferences use the persisted app-state contract. Parsed state is never imported from another receiver or profile.

Early short-and-long release is admitted separately from a safety STOP or abort. The gesture retains its exact HA command context, cancellation event, task and side/link. A release can authorize its deferred short callback only while that admission is still active; it cannot revive a gesture after STOP or caller cancellation. `CommandContext.request_cancel` counts repeated cancellations of that exact resource admission while preserving the scheduler's existing event/reason behavior. The callback bypasses only its admitted release cancellation and checks that context's generation again inside the wire lock. Independent other-side admission does not change it; a newer relevant STOP or abort revokes it. Public tests in `test_goodvibe_review.py` cover other-side admission before, concurrent with and after release, including a blocked wire, plus STOP/abort in both orders. A hold still in connection preflight is invalidated without starting it later.

Native paired child release preserves that intent through the shared scheduler's queued STOP operation. A later ordinary STOP keeps its ordinary cleanup. The product's exact sides getter controls combined routing: 30 admitted profiles offer only 0/1 and execute left then right, while eight offer native side 2. The remaining 837 normal choices offer only side 0. `paired_coordinator.py:SingleAddressPairedCoordinator` and `tests/test_goodvibe_review.py:test_combined_pair_uses_only_sides_admitted_by_the_product` bind this gate to the actual HA pair path.

Old notification callbacks and expiry/poll tasks cannot own a replacement link. Explicit stop, manual disconnect and unload end sleep monitoring intent and cancel resources. Unexpected disconnect preserves admitted monitoring intent, and the coordinator retries failed recovery while that intent remains. This is HA recovery policy, not a claim that the Android connection callback automatically retries.

Normal alarms retain ACK-based local single-alarm updates and observed repeat records. Repeat-alarm allocation is a pure per-physical-profile preflight plan: every full-slot error occurs before target execution, and observed cache changes do not cause a later target to allocate again. A refresh event clears and requeries that observed list. The five inline countdown callsites (including the D9RM off alternative) and light-close callsite have dedicated public select/button paths. Default light durations (FMRM 900, RNRN 14400, other light products 300 seconds), light palette and duration constraints, snore-menu exclusions and slider ranges come from this package's actual callers. Source button labels are preserved without assigning physical motor meanings.

A sleep report operation performs metadata, continuation and typed report receipt under the HA operation's connection ownership. Day type is 1 and month type is 2. Monthly payloads are lists of typed records. Type 1 part settings admit 1/2; type 2 admits 11/12/13, with shipped startup default 12. Report part operands are 1/2. Type 2 time ACKs query time, then part through current-link-owned serialized follow-ups. The report page replaces live polling; active report assembly keeps the link, and cancellation clears its request resources. Completed direct-BLE report records remain in a process-local cache keyed by part/type/date within the physical/profile session.

### Intentional safety boundaries

- Missing selected GATT TX/RX fails setup instead of reporting the app's success-without-channels state.
- Zero-length framing, invalid lengths/casts, partial invalid realtime sides and oversized/incomplete compressed input do not fabricate or partially replace visible state. Report decompression is bounded to 1 MiB.
- HA request ownership and cancellation are stronger than the app's unretained timer and packet-interleaving behavior. Native individual-write serialization is not presented as proof of whole-app lifecycle behavior.
- Hardware delivery/freshness cannot be proven from a characteristic callback or a repeated sequence value. No firmware watchdog, position calibration, pairing requirement or physiological interpretation is inferred.

## Exclusions

The [complete row list](row116-goodvibe/exclusions.csv) is exhaustive. Its reasons are restricted to exact source reachability, product/transport boundaries, safety or unrelated app behavior:

- Factory selectors rejected by the shipped `good` flavor, unused getters/catalog fields and inactive compiled flavors/display pages. The registered public sleep-settings route is reachable and is implemented; it is not excluded with the unused full display page.
- FWRM/WFRM and dedicated desk height/unit/reset parsers/builders, with no artifact bed linkage.
- Firmware lookup/download and OTA initialization/CRC/data paths, including the corresponding native responses and typed firmware network schema.
- Wi-Fi QR SSID/password metadata and cloud/account/network/report infrastructure unrelated to direct BLE bed control. The live additional sleep BLE service and direct BLE reports remain supported.
- Phone flashlight, voice/local navigation presentation, icon/name/crop/language/chart plumbing and unrelated native camera/barcode/image assets. Relevant model/alias/configuration effects are retained separately. The Y6RM menu dispatch at 0x7ffe48 constructs five direct BLE widgets at 0x800f2c; its primary navigation is excluded while all five descendants and their 95 constructor fields are accounted explicitly. They are derived comparison rows within this accepted unit, not new canonical inventory/queue IDs.
- Generic Android library APIs without a retained Dart invocation, including unused arbitrary reads/descriptors, bond administration, RSSI/PHY/priority and cache controls. HA Bluetooth adapter/proxy/setup support remains intact.
- Unreachable descriptor/enum alternatives do not become public actions solely because a builder can encode their operands. The independently tested builder alternatives remain distinct from reachable gestures.

## Audit and validation limits

Audit005 freshly checked 21 schemas, 89 independent negative controls, active/archive generator agreement and metadata/dependency consistency. The 23 producer suites / 30,792 fixtures were fresh in audit004. The 54 temporal schedules and unchanged source proofs were exact carries, not freshly rerun by audit005. Historical repair001 false freshness claims, failed setup attempts and internal 531-member self-reference issues remain disclosed; later acceptance does not retroactively clear them.

Implementation tests are separately run against production packet, parser, controller, setup, entity/service and coordinator paths. They do not turn static artifact execution into hardware evidence. Hardware, ATT delivery, firmware acceptance and physiology remain unverified and are deferred to real users after beta/release, without a maintainer hardware demand.
