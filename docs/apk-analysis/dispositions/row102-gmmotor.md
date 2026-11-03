# Row102: GM Control 4.6.6 implementation ledger

This is the separate implementation/comparison ledger for
`com.desarketing.gmmotor`, version 4.6.6, code 46600. The user-facing protocol
reference is [GM Control](../../beds/gmmotor.md). Static source proves application
behavior; hardware delivery, ATT/firmware interpretation, physical effects and
physiological accuracy remain **UNVERIFIED**, for real users after beta/release.

## Evidence identity and scope

| Authority | SHA-256 / identity |
|-----------|--------------------|
| Artifact set | `0bdb27d045fb8d097cfc20e26e759ff238f8ac55eb317a3d3eccb814ccc8d11b` |
| Root acceptance | `4e26ae6a10988b9e59016ffaf2e8762c94ced1fe44e54dcb109d26e44049c180` |
| Accepted `REPORT.SHA256` | `2251d01a96c95b4d5c15c369fe67202f2e8c7d513c91db88fc8b4ec31fb396d7` (480 members) |
| `WORK_EVIDENCE.SHA256` | `142aa962f9b1ae1e2a2aa42b326646921e357a3a132f254dd35af643b9bc41c3` (26,998 members) |
| `SOURCE_EVIDENCE.SHA256` | `55d9d3cfb3a1d3bcf6e03bc0f823ca86526e7240454c20b50d5cbf0e98815708` (27,134 members) |
| Independent core `AUDIT.SHA256` | `91cad0127b79adfabaa7c5b6492a93a40b7c593fc6d1494427b003e25bfaca1b` (1,677 members) |

Machine-local run root, abbreviated **R** below:
`disassembly/output/phase4-early/com.desarketing.gmmotor-4.6.6-2026-11-03-bulk101-188-001`.
The accepted report is **R/work/report-repair-sol-001**. Source citations in the
CSV indexes are relative to R; report-sidecar names resolve in that accepted
report. Core citations resolve under **R/audit/sol-round002/core**.

Implementation independently rehashed all accepted manifests and their members,
including input and three scope manifests, before comparison. The 33,562 unique
paths include manifest files. Operational receipts remain machine-local under
`row102/implementation`; no APK, decompilation or raw audit report is committed.

Acceptance applies only to this replacement candidate: 17 gates PASS, 0 open,
1,182 IDs, 30 shards / 31 reports, 41,370 default field relationships and 140
additional nested relationships. Old negative/PARTIAL audits remain negative.
The retained runtime/heap decoding and bounded SDK primitives are evidence,
not a fresh full decompiler run. The earlier unsealed interval, later hash
reconciliation and pre-tool static-parse failure retain their original limits.
Neither acceptance nor this ledger supplies a blanket provenance waiver.

## Exhaustive indexes

Each row has exactly one disposition, `IMPLEMENTED` or `EXCLUDED`. No existing
protocol receives `ALREADY_IMPLEMENTED` credit by family resemblance. Implemented
rows cite concrete code and focused tests; excluded rows identify their source
and boundary/dead-code reason.

| Index | Coverage | IMPLEMENTED | EXCLUDED |
|-------|----------|-------------|----------|
| [Catalog](row102-gmmotor-catalog.csv) | All 1,182 constructors, hashes and 35 field cells each | 834 | 348 |
| [Nested configurations](row102-gmmotor-nested.csv) | Four nested records, 35 additional field cells each | 2 | 2 |
| [Candidates](row102-gmmotor-candidates.csv) | All 1,482 material, sender, native, selector, runtime and receive candidates | 1,128 | 354 |
| [Commands](row102-gmmotor-commands.csv) | 458 P1 rows and 14 host P2 builders | 472 | 0 |
| [Stream consumers](row102-gmmotor-streams.csv) | 78 bindings and 38 other uses | 52 | 64 |
| [Common dependencies](row102-gmmotor-dependencies.csv) | All 28 scoped common dependency references | 18 | 10 |
| [UUIDs](row102-gmmotor-uuids.csv) | All 22 UUID-like Dart literals | 21 | 1 |

The candidate index includes 1,077 materials, 115 control-sender callsites, 242
native Bluetooth invocations, 21 compiled sleep builders, nine GATT enum entries,
six native execution stacks, eight explicit boundary findings, three receive
repair boundaries and one Wasm probe. Its native rows retain BLE effects, not
Android API spelling. Native READ/bond/PHY branches proved dead remain excluded.
Flutter/Android engine, camera, image, layout, licensing and audit infrastructure
are not HA bed features; their shared BLE callers remain separately included.

Paths separated by semicolons in a code/test cell share that cell's leading
`custom_components/adjustable_bed/` or `tests/` root. Symbols following `::` name
the implementation/test. CSV `source_sha256` identifies the exact constructor;
`configuration_sha256` covers all its default values. Each field cell is an
individual disposition under the following matrix and route overrides.

## Catalog field matrix

Evidence: accepted `CATALOG_FIELD_ACCESS_WORK.json`,
`repair-evidence/FIELD-RETURN-PROOF.json`, `repair-evidence/FOCUS-GETTER-PROFILES.json`,
`REACHABLE_UI_CASES_WORK.json`, `CATALOG_ALARM_VECTORS.json`, and the independent
scope getter/receiver proofs. A transfer/copy/default getter is not promoted into
a host feature merely because its body exists.

| Offset | Field | Primary-route disposition and concrete behavior |
|--------|-------|--------------------------------------------------|
| 07 | `name` | EXCLUDED: constructor/copy metadata; actual selector identities are implemented separately |
| 0B | `bedTypeList` | IMPLEMENTED: `Profile.sides`, setup admission and paired side routing |
| 0F | `appSupportList` | IMPLEMENTED: exact shipped-flavor support gate in `ROUTES` / profile selection |
| 13 | `richmatBedConfigList` | EXCLUDED: no host getter consumer; QLRN nested records also fail host support |
| 17 | `motorList` | EXCLUDED: copy/internal QLRN builder data; active controls use `detailsPageDisplayList` |
| 1B | `massageList` | EXCLUDED: copy data, no active host control-list consumer |
| 1F | `memoryList` | EXCLUDED: copy data; actual memory controls remain in the active details catalog |
| 23 | `richmatAlarmList` | EXCLUDED: copy data; active alarm choices use `alarmList` |
| 27 | `versionOneMotorList` | EXCLUDED: no active host consumer |
| 2B | `versionOneMassageList` | EXCLUDED: no active host consumer |
| 2F | `versionOneMemoryList` | EXCLUDED: no active host consumer |
| 33 | `versionOneRichmatAlarmList` | EXCLUDED: no active host consumer |
| 37 | `snoreList` | EXCLUDED: no active host list consumer; six-name settings gate implemented independently |
| 3B | `speechRecognitionList` | EXCLUDED: no active host consumer; reachable ordinary named controls are retained |
| 3F | `richmatSleepMonitoringType` | EXCLUDED: inactive field; active host uses `rmcSleepMonitoringType` |
| 43 | `isRichmatForcedDisplayBleSleep` | EXCLUDED: no active host consumer |
| 47 | `isRichmatForcedDisplayLightTherapy` | EXCLUDED: no active host consumer |
| 4B | `isRichmatSupportRepeatAlarm` | EXCLUDED: copy metadata; active gate is offset 77 |
| 4F | `isHaveSmartLock` | EXCLUDED: no active host consumer; independently reachable named/received lock behavior retained |
| 53 | `isRichmatHaveLightStrip` | EXCLUDED: inactive field; active host uses offset 6F |
| 57 | `isRichmatHaveGrooveLightStrip` | EXCLUDED: no active host consumer |
| 5B | `isRichmatSupportLightTherapy` | EXCLUDED: no active host consumer |
| 5F | `isRichmatSupportBlanket` | EXCLUDED: no active host consumer; unsolicited parser branches remain implemented |
| 63 | `isRichmatHaveWarmColdStrip` | EXCLUDED: no active host consumer |
| 67 | `avocadoAlarmList` | EXCLUDED: no active host consumer |
| 6B | `isAvocadoSupportRepeatAlarm` | EXCLUDED: no active host consumer |
| 6F | `isHaveLightStrip` | IMPLEMENTED: `Profile.has_light` plus live light capability reply, not a substituted legacy flag |
| 73 | `bedLightDisplayType` | IMPLEMENTED: selected eight-color/general RGB layout; nested V9RM value remains independent |
| 77 | `isSupportRepeatAlarm` | IMPLEMENTED: repeat versus countdown admission, independent of sleep monitoring |
| 7B | `rmcSleepMonitoringType` | IMPLEMENTED: active BLE sleep-name query/admission; no WiFi feature inferred |
| 7F | `alarmList` | IMPLEMENTED: exact first-match action/material override, including empty-list absence |
| 83 | `detailsPageDisplayList` | IMPLEMENTED: ordered exact controls, captured material and local flag transitions |
| 87 | `remoteList` | IMPLEMENTED: nine exact picker target sets; no first-target guess |
| 8B | `isHaveBottomMassageCountDown` | IMPLEMENTED: actual getter gate; only D1RM and D9RM evaluate true in admitted defaults |
| 8F | `bedConfigList` | IMPLEMENTED: V9RM default, standard and split-head membership/gates remain distinct |

The 348 rejected constructors have every field EXCLUDED by the exact shipped
support predicate. Dedicated FWRM/WFRM, QRRM and MHRN routes bypass primary field
consumers: their dormant fields are EXCLUDED, while support, concrete route,
desk commands, barcode/product selection and special remote targets are
IMPLEMENTED. Nine ordinary remote pickers retain their actual `remoteList`.
The two QLRN nested records are EXCLUDED by its rejected host route; V9RM's two
nested records are IMPLEMENTED with their own values. Field cells never union
the standard and split-head control lists.

Concrete implementation: `gmmotor_catalog.py`, `gmmotor_profiles.py`,
`gmmotor_discovery.py`, `config_flow.py` and `beds/gmmotor*.py`.
Tests: `test_gmmotor_source_catalog.py`, `test_gmmotor_profiles.py`,
`test_gmmotor_discovery.py`, `test_gmmotor_integration.py`.

## Selection, setup and persistence

IMPLEMENTED: all 833 supported nonempty scan labels and 16 extra literals,
case-sensitive substring filtering, first-four/first-nine uppercase aliases,
locale-dependent alias choices, explicit remote targets, QR concrete products,
manual fallback and saved HA product/side identity. Shared advertisement names
and services offer app candidates without replacing current upstream profiles.
HA's explicit product dropdown also allows the user to choose the locale-specific
or remote result directly. Camera acquisition of the QR code is EXCLUDED as a
phone-only input mechanism; its product interpretation remains included.

HA requires a literal prefix for background `local_name` matchers. The manifest
therefore uses prefix patterns, with the source substring check in detection and
manual discovery. Short malformed names safely return the empty selector;
the source can throw a range error. Empty/unsupported stored selectors use the
source empty base; new setup rejects an unadmitted final product. QRRM must
resolve a concrete product and cannot silently become an empty controller.

MM/SXB entries own one physical address and one session each. HA device/address
selection replaces the app's batch-global last-input mode, connected-bean
shortcut, RSSI-first substring scan and app preference storage. The source
batch-global choice is not propagated between independent HA devices. This is
an explicit HA ownership adaptation, not an extra wire protocol or an exclusion
of either mode. Querying the selected bed's advertised sleep name remains
available, including source character-code conversion for its byte list.

IMPLEMENTED: app-lifetime product gesture flags survive HA's connection-scoped
controller replacement. The existing `app_session` registry holds the flags by
physical address, exact product and app side (`gmmotor_sessions.py`), including
opt-in quick handoff. A changed product starts a new view; these transient flags
are not written to disk. New product entries default quick handoff off. This HA
lifetime adaptation retains the accepted widget's stateful callback selection;
it does not preserve connection-owned ACKs or invent a hardware state.

IMPLEMENTED: MM/SXB live intent survives an unexpected BLE drop independently
of the discarded controller. The coordinator's tracked reconnect task restores
the link and one polling timer on the replacement. Intentional teardown clears
the intent even if the client was already lost; explicit stop, unload and
canceled startup cannot silently restart monitoring. Old callbacks retain their
generation and controller ownership checks. These HA recovery/lifetime choices
do not claim new source wire behavior. Native SDK waits, packet builders and
receive/dispatch ordering remain as documented below.
Recoverable subscription or initialization-write failures release only the failed
connection's resources; the monitoring request survives for the next attempt.

Code: `gmmotor_sessions.py`, `beds/gmmotor.py`, `beds/gmmotor_sleep.py`,
`coordinator.py` and `const.py`. Tests: `test_gmmotor_reconnect.py` exercises real
connect, factory replacement, one-second/ordinary idle teardown, programming
selection, address/product/side isolation, both sleep modes, duplicate recovery,
late callbacks, explicit stop/disconnect, offline unload and startup cancellation.

## Builders, native writes and command lifecycle

IMPLEMENTED: all effective ordinary/special P1 prefixes, short/long/single-byte
overrides, side bytes, native integer masking, SUM8 and desk decimal-pair
construction. `Action.apply` retains actual captured materials: BRRM's visible
preset can send opcode zero; E3RM's memory arm can send zero before using the
long memory opcode. Neither visible names nor protocol-family similarity choose
a packet. Physical axes are not inferred from labels; named controls are exposed
through the shared controller button/hold contract.
Continuous card holds are declared only for sustain gestures. Finite actions
use ordinary buttons, with a separate long button where the source admits it;
desk memory recall remains a short action rather than a continuous hold.

P1 selects the last accepted service, first exact WRITE, first global NOTIFY,
and response mode from the selected characteristic. P2 preserves carried
candidates, WRITE-before-NOTIFY branch ordering and all subscription occurrences.
Declared notify UUIDs do not replace the P1 property selector. The WiFi-named
2320567c service remains in scope because it carries the direct BLE sleep path.

All three source SDK write paths and 242 Android invocations are assigned in the
candidate index. The retained behavior includes disconnected/role/property
admission, native byte limits, negotiated MTU, per-frame/chunk order, 15-second
completion timeout, shared mutex release on error, no write retry and first-error
abort. Android adapter/engine/permission callback APIs are replaced by HA's
Bluetooth stack. Actual ATT results are UNVERIFIED, not claimed from mocks.

P1 ordinary writes have 100 ms cadence. Sustain starts at 100 ms; long callbacks
fire at three seconds. Short/sustain cleanup uses the exact side STOP with a
fresh event. Long and short/long gestures have no invented release. Source
long-sustain's later periodic callback sends nothing. The desk's long-memory
callback is also a no-op; compiled long opcodes are not promoted to programming.
HA guarantees cancellation/error cleanup where the source lacks a dispose STOP
guarantee. This safety behavior is explicit.

P2 emits the exact 14-byte header, compact UTF-8 JSON, 1–254 ID wrap and 100 ms
queue step. MM's `q_part` emits `s_part:null`; MM's `q_time` consumes an ID but
sends nothing. SXB and MM time/report/allow/part builders remain distinct.
MTU-sized chunks are sequential with no added per-chunk cadence. HA serializes
multi-packet service calls under the production coordinator command lock and
uses a shared SDK mutex across independent GM sessions.

Tests: `test_gmmotor_source_catalog.py`, `test_gmmotor_protocol.py`,
`test_gmmotor_transport.py`, `test_gmmotor.py`, `test_gmmotor_desk.py`,
`test_gmmotor_sleep_protocol.py`, `test_gmmotor_sleep.py`,
`test_gmmotor_integration.py::test_real_scheduler_keeps_two_countdown_frames_atomic`.

## Receive ordering and safety differences

IMPLEMENTED: raw observer notification before handler work; old remainder timer
cancellation before extraction; extraction of the entire batch before dispatch;
20/21 length/SUM8, 40 BE16/CRC16-XMODEM and legacy next-6E boundaries; ten
pipeline-reachable ACKs; source required-index guards, empty DTOs and precise
event ordering. The pure `6E2100008F` ACK branch stays dominated by the outer
zero-length extractor. It is not promoted into a live capability reply.

The source zero-length path does not progress and grows pending state without
dispatch or a new timer. HA drops that batch with an invalid-notification count.
Source required-field exceptions retain earlier dispatched effects and suppress
later events/timer work; HA retains earlier effects, drops the malformed remainder
and guarantees callback cleanup. A short extended header is retained safely
instead of invoking a source range exception. The 500 ms remainder expiry is
implemented without pretending these safer paths are artifact behavior.

The source app appends bytes before its raw observer and unawaited handler.
HA raw capture runs before buffer extraction and uses the existing base-class
exception isolation, so a failed diagnostic observer cannot suppress semantic
parsing. The independent synthetic observer-fault witness (not a default
app-owned fault) leaves the source's old timer active with appended bytes and
does not enter its handler. HA does not claim equivalent failure behavior for
that injected case; `test_ha_raw_capture_fault_is_isolated_before_semantic_dispatch`
records the explicit HA policy.

P2 ordinary assembly retains the low-byte length threshold and overshoot,
MM-start clearing versus SXB-start retention, per-SXB-report-chunk 14-byte strip,
whole-text selector precedence, native IDs and distinct handler boundaries.
All 61 DTO layouts and 245 null branches are decoded; invalid JSON/type/index
paths are safe HA rejections. Unsupported dynamic-index harness observations are
not counted as artifact exception evidence. Gzip then Latin1 report decoding,
old-before-new SXB day parsing, missing-day/version gates and normal cache
identities remain distinct. OTA selectors retain precedence even when their
firmware publication is EXCLUDED.

HA adds an 8 MiB assembly/decompression budget and cancels stale follow-ups on
stop/disconnect. It does not cancel an in-flight SDK write for local sleep stop.
One finite report transfer, including a terminal nonpositive-size reply, can
resume a prior HA live-poll intent afterward;
the source leaves its page's active command in place. These ownership/resource
differences do not add any wire STOP or inferred hardware command.

Tests: `test_gmmotor_protocol.py`, `test_gmmotor.py`,
`test_gmmotor_sleep_protocol.py`, `test_gmmotor_sleep_dto.py`,
`test_gmmotor_sleep.py`. Exhaustive operational comparisons cover all common,
extra, desk, pipeline, DTO/null, version, live, compressed-report and dispatch
vectors against this accepted seal.

## Calendar, alarms and secondary domains

IMPLEMENTED: source local calendar/Unix epoch/timezone frames, whole-hour
truncation, year-minus-1970 representation, two countdown frames, repeat six-field
records, delete/list, exact first-match alarm overrides, full-record dedup and
existing-ID escalation replacement. `alarm_at` strips seconds, compares epoch
minutes and adds exactly 86,400 seconds to a nonpositive difference, rather than
inventing a next-calendar-day wire command. HA supplies its configured timezone.

Actual session/menu gates remain separate from static metadata: clock ACK plus
nonempty alarm choices; repeat flag chooses the repeat page; light ACK plus
offset-6F flag; eight-color versus general RGB; six exact anti-snore product
names independent of its status listener. Count/time slider ranges and 0–900
second light timeout are admitted explicitly. Bottom massage countdown follows
the actual offset-8B getter and D9RM's separate zero-choice opcode.

Every reachable ordinary named control, including massage, memory, position,
light, music and other catalog functions, uses its own captured material and
gesture. All reachable unsolicited notification domains are retained as raw
state, including motor indexes, detection, music, massage, RGB/white light,
anti-snore/get-off-bed, sleep name, box lock, blanket, fan, atomization, heating,
desk and side/mode reports. A dormant capability flag cannot suppress a proven
incoming parser branch or create an unproved outgoing setter.

Sleep consumers retain raw DTOs, separate live-side gates, device-part settings,
report-part/date/type inputs, day/month values and exact normal-mode cache keys.
SXB's time-stream publication precedes clock mutation; follow-ups preserve order.
New-day stream 4B remains exposed even though the host's day widget listens only
to old-day stream 47. No widget listener is falsely claimed for it. Source
calendar/side selection is represented by HA date/part inputs and published report
state; charts/localized Flutter layout are not new BLE semantics.

Two-second live polling and SXB five-second display windows are implemented
separately. A valid side reply marks its window; an empty window clears only that
side's displayed state. MM does not inherit the SXB timer. Physical/medical
meaning remains UNVERIFIED. The sensitivity query and unsolicited response
parsers remain included; no removed `s_sens` or inactive anti-snore setter is
invented from a neighboring branch.

Tests: `test_gmmotor_profiles.py`, `test_gmmotor.py`, `test_gmmotor_desk.py`,
`test_gmmotor_protocol.py`, `test_gmmotor_sleep_dto.py`,
`test_gmmotor_sleep.py`, `test_gmmotor_integration.py`.

## HA exposure and paired lifecycle

IMPLEMENTED: lazy controller factory, supported-type metadata, explicit app
selection, profile validation, options persistence, per-physical-receiver product
and app side, all-target service preflight, coordinator serialization, named
buttons/holds, diagnostic state, card discovery and compiled frontend bundle.
The `gmmotor` service is finite and typed; it exposes no arbitrary raw-write API.

Single-address pairing requires the exact product's Right choice. A product
without native Both uses two admitted side commands on one serialized connection.
Cleanup retains each side. Separate-address pairs retain different product/side
settings and independent sessions; a logical Right child does not relabel the
physical receiver's configured wire side. Desk controls keep their source side
zero. MM/SXB modules offer no invented motor or single-address pairing surface.

Production tests exercise real coordinator locking, entity button execution,
sensor state, all-target rejection and native paired routing. Existing profiles
and contracts remain covered by controller, detection and pairing tests.

## Explicit exclusions

| Discovery | Disposition / exact basis |
|-----------|---------------------------|
| Firmware transfer / OTA UI and outgoing `q_ota*`, `s_ota*`, `s_init` workflow | EXCLUDED: `sleep_ota_page.dart` at 74160C, 7D0F20, 7D1260, 7D4CC8; firmware is outside product boundary. Shared services, framing, CRC, selector order and independent clock paths retained |
| Firmware HTTP catalog/download | EXCLUDED: `wifi_sleep_api.dart` 7D5928/7FC9C4 and `http_util.dart` 7D5EEC/7FBC88/7FCA3C; remote firmware infrastructure |
| P1 firmware notification payload | EXCLUDED: `bluetooth_util.dart` 8101EC/810490; 40 framing and CRC still implemented |
| Alternative mlily/new/public sleep UI | EXCLUDED: `sleep.dart` 7401C4 with host 8092C0 / config 809438 fixed base display; independently shared base receivers remain included |
| Removed sensitivity-set sender | EXCLUDED: `sleep_util.dart` 6CFE6C/6CFFC0 reaches removed-code/null-cast branch; query and incoming parser retained |
| Dormant constructors/fields/materials | EXCLUDED individually in CSV: exact support gate, receiver-aware no-consumer proof or dead callback; no model-prevalence/hardware exclusion |
| Phone torch / camera / image / framework UI | EXCLUDED: handset-only behavior or rendering, with no direct bed BLE effect; QR product interpretation retained |
| WiFi provisioning, bed network, cloud/account services | EXCLUDED product boundary. Complete source searches found no app-owned SSID/password/provisioning/account sender; the WiFi-named BLE service and shared BLE effects remain included |

No finding is excluded for convenience, rarity, lack of an entity, or missing
maintainer hardware. Physical checks are deferred external validation after a
beta/release and do not block source implementation.
