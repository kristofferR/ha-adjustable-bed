# Row107: OKIN SleepEase 1.2.24

This is the separate source-comparison and implementation record for canonical
row107, package `com.okin.doublesleep`, version 1.2.24/code 109. Raw artifacts,
decompilation, accepted reports and independent audits remain machine-local.

## Accepted authority

| Identity | SHA-256 |
|---|---|
| Artifact set | `508acb365f68ddde1a289d51c8eb95eb089817ad35d0c773b578f787b0ff36c4` |
| Accepted replacement REPORT.SHA256 | `b83d0114c1f9bff1bf93483cd5f0cbe25853f08eb3c4ab418665ac37fc001d56` |
| EVIDENCE.SHA256 | `4fed47acf49c65201947cbc4b2df9e73ba176c1c621e184881842c37b17dee2f` |
| SUPERSESSION.json | `91ac91cd07f5ee3a457eeabe0a38b7a6998fc63d0e6359513281f63bd52c22a2` |
| Independent FULL17 AUDIT.SHA256 | `5cca091a82b3c36e310fbb03a07a2ecfd7d13fa95f4358554664f20b40f39203` |

Authority is the local row107 `ACCEPTANCE.json`, accepting
`work/report-repair-sol-002` and `audit/sol-round003`. All 17 gates passed;
R107-SOL-001 through 005 are CLOSED_VERIFIED, with zero open material findings.
Before source comparison, the implementation owner independently verified these
exact seals and 46 report, 3331 evidence, 218 audit and 89 input members.
The command and full receipt live in the durable row107 implementation handoff.
Earlier partial and negative reports remain immutable and are not authority.

## Coverage and reading the ledger

The adjacent [machine-readable ledger](row107-doublesleep.json) links the accepted 143 command rows,
273 action/driver cells, 10 model entries and 629 candidates to source, tests and
exactly one disposition. Command and action candidates are indexed by their
existing candidate IDs, rather than counted as new discoveries again. Additional
behavior rows cover notification branches, consumer fields, configuration,
state lifetime, lifecycle and explicit safety differences. Report-member coverage
is an evidence index, not an extra count of implemented features.

Every accepted discovery has a disposition. Independent local source review
approved the implementation after verifying its disconnect, consumer and legacy
download fixes. The durable handoff tracks subsequent PR review and CI status. This record does not
claim hardware verification or acceptance of an unreviewed source diff.

## Safety differences

- The app's global command caches, sequence, report side and singleton driver
  lifetime can cross physical devices. HA keeps caches and sequence per physical
  address/profile, parser buffers per connection and report requests serialized.
- P3's constructed MTU-byte writes exceed Android's MTU-minus3 admission limit;
  large packets also truncate the one-byte inner length. HA uses the same framing
  within negotiated ATT and representable length limits.
- The app launches all fragment futures without awaiting or aborting on error.
  HA awaits writes, stops a failed batch and does not claim a suppressed/cancelled
  write succeeded. Existing global command and BLE locks remain authoritative.
- P3's live-data consumer reuses the first map value for both named sides. HA
  consumes each named side's own values, preventing cross-side data attribution.
- The A61106 split can pass three fields into a five-field consumer. HA preserves
  that frame as raw data and a parser error; it does not fabricate missing fields.
- One-shot alarm Sunday computation can emit the repeat flag or overflow to 0.
  HA applies the artifact's proven Sunday-first day bits to the next occurrence.
- Malformed notifications cannot throw into HA's Bluetooth dispatcher. Accepted
  pre-error parser/cache mutations and source timer ordering are retained. Gzip
  and assembly have explicit 4 MiB bounds to prevent unbounded allocation.
- A cancelled or failed uncorrelated report exchange ends its connection before
  another request. Stale-client callbacks cannot publish into a new registration.
- Held commands have a finite HA duration and fresh STOP cleanup. App-background,
  process-death and disconnected global-timer behavior are not reproduced as an
  unsupervised motion scheduler.

Each difference retains the valid normal command/response path. The ledger binds
the excluded unsafe behavior to accepted source and its replacement tests.

## Product exclusions

Firmware/OTA, Wi-Fi or network provisioning, cloud/account/captcha/music bridges,
random mock data and companion SQL/chart/health-score calculations are outside
this BLE bed integration. Unreachable getter-only commands and unsupported enum
alternatives are excluded with their source reachability proof. Phone-specific
routes, dialogs, loading widgets, debug formatting and operating-system scan UI
are not copied into HA; their reachable bed commands and HA Bluetooth setup,
proxy selection and reconnect infrastructure remain supported.

The [protocol and usage guide](../../beds/doublesleep.md) describes controls,
services, returned state and deferred real-user checks after beta/release.

## Reconciled totals

| Inventory | IMPLEMENTED | ALREADY_IMPLEMENTED | EXCLUDED |
|---|---:|---:|---:|
| Canonical candidates | 534 | 21 | 74 |
| Driver commands | 120 | 0 | 23 |
| Action/driver cells | 219 | 0 | 54 |
| Models | 10 | 0 | 0 |
| Notification branches | 22 | 0 | 0 |
| Numeric cache fields | 16 | 0 | 0 |
| Report consumers | 2 | 0 | 10 |
| Consumer fields | 42 | 0 | 11 |

These inventories overlap by explicit references; they are not summed. The 511
archive members and 46 report members each have a provenance disposition/index.

## Complete exclusion index

- **X-GLOBAL**: Global numeric caches, sequence and report side crossing devices are unsafe for per-bed state and commands. Retain values per address/profile and correlate report side within one owned exchange. Evidence: `state-cache.json; REPAIR-STATE-LIFETIME; P3 search883d18`.
- **X-ATT**: Original P3 packets exceed native ATT admission and truncate one-byte lengths. Preserve the envelope within negotiated MTU-minus3 and representable body length. Evidence: `transport-contract.json; P3 packet builders884a1c/884d00`.
- **X-ASYNC**: Unawaited fragment futures can continue after rejected earlier writes and have no complete result. Await/fail-fast batches, retain locks and 15s write deadline, and never publish a suppressed write as success. Evidence: `transport-contract.json; SEND3c1a18; native367f88`.
- **X-SIDE**: Reusing the first map value across L/R misattributes sensor data. Consume each explicitly named side independently. Evidence: `notification-catalog.json/P3 realtime; handleReadData3c2500`.
- **X-A61106**: Three-value split fails a five-field consumer. Preserve raw bytes and parser error without fabricating fields or publishing an incomplete coherent sample. Evidence: `notification-catalog.json/P1/P2 raw broadcast; overview86dd38/86e438`.
- **X-SUNDAY**: One-shot Sunday computation can wrap to0 or collide with repeat flag. Use the proven Sunday-first bit layout and next occurrence, retain valid weekday/repeat behavior. Evidence: `ANALYSIS.md alarm row49; DateTime weekday proof; alarm64f35c`.
- **X-BOUNDS**: Unbounded gzip/buffer allocation and exceptions escaping Bluetooth callbacks are unsafe in HA. Bound 4 MiB, preserve accepted mutations/timer order, report malformed input without success. Evidence: `notification-catalog.json; BinaryHistory/JsonReader retained buffers; HISTORY-DISPATCH.json`.
- **X-LATE**: Late uncorrelated responses and old-client callbacks must not reach a new physical/side exchange. Serialize requests, bound silence rather than total progressing-transfer duration, and close a cancelled/failed report session. Evidence: `HISTORY-DISPATCH.json; P3 cached1108; disconnect cleanup3b69e4`.
- **X-UNHELD**: Do not recreate a phone-global motion timer that can outlive its owner or fail to release on task cancellation. Bound HA holds and send fresh STOP in finally. Evidence: `sendCommand3c156c; HOLD; tapUp/tapCancel stop1`.
- **X-IDENTITY**: The source can deduplicate two physical devices by the same original name when no hyphen exists. Preserve the claimed identity for diagnostics, but keep HA physical-address ownership and never merge/suppress beds by a potentially colliding app name. Evidence: `gainRealMac3c4f60; SCAN3c4ad0`.
- **X-YEAR**: Out-of-range calendar years wrap to a different binary year. Reject binary report years outside 2000..2255; retain the full supported calendar for P3 JSON and all legacy records. Evidence: `P2 queryReport882f98; year%2000 -> Uint8List`.
- **X-CALLBACK**: Do not propagate a diagnostic/UI observer exception into HA Bluetooth or let one independent raw observer suppress another complete observation. Preserve parser mutation/timer order and current physical ownership; guarded HA callbacks isolate observer failures. Evidence: `HISTORY-DISPATCH.json; observer Map.forEach; MFP local catch3bc6b0`.
- **X-PHONE**: Mobile route-selected report refresh, account/SQL fallback, dialogs, global device maps and OS scan/permission policies are companion infrastructure. Exact bed commands are exposed explicitly; HA adapter/proxy/reconnect support remains. Evidence: `Home86d868 and report refresh5e8a68; AutoConnect395f68/ReConnect661834`.
- **X-OTA**: Firmware acquisition/update and related transport lifecycle are outside direct BLE bed controls. Version display is retained. Evidence: `candidate OTA; P2 commands74/75/76; P3 q_ota; FirmwareManager598c98/5b0ff4/5b57d8`.
- **X-CLOUD**: Account/cloud/captcha/WebView/music infrastructure has no normal direct bed-write feature. Evidence: `WEB5e8000; AES55aeb0/55af04/55b3b4/595120; reverse-callsite ledger`.
- **X-WIFI**: Bed Wi-Fi/network/provisioning is outside product scope; no app-owned reachable provisioning command was found. Evidence: `accepted semantic/structural/callsite searches; omission-reconciliation.json`.
- **X-ANALYTICS**: Local SQL, month/day chart grouping and derived health/stress/recovery scores are companion analytics. All incoming BLE records, fields and direct derived sensor state are retained. Evidence: `REPORT-DATA.md; BlueReader68713c/688960; month aggregation5e9c8c/5ec110`.
- **X-MOCK**: Random debug observer injection emits no physical BLE write. Evidence: `DEBUG-SIM68c330/68c234`.
