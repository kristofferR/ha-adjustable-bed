# Row122: eShine E2000 / E3000 / E3100 / E5000

This is the source comparison for **com.okin.eshine 1.1.8 (version code 22)**,
standalone FULL. Static evidence is accepted; hardware operation remains
**unverified**. This profile is separate from the E6000 app
`com.richmat.eshinesleep` and its existing `eshine` controller. Shared branding,
Nordic UART or a Smartbed name cannot select a product.

## Evidence identity and acceptance

| Binding | SHA-256 |
|---------|---------|
| Six-file supplied artifact set | `fbf9cbc16b7f016c296821899e11e0d540f609af5ad9fb05bd3842a63acf9a5a` |
| Base APK | `aa46126cc2dacb0ac8ecbdfb7968624cce4efba419c66ef3d1aa8000c45af7cd` |
| Accepted REPORT.SHA256, 145 members | `73ee78edc2b83ff54ae8aebbce52fc0a4f4bfc617bb4bc9780fe0350f49f7594` |
| Accepted analysis.json | `65025d235307abf710245f1f93d0d020496ee174404523284fb7437af8214a69` |
| Accepted SOURCES.SHA256, 20,268 bindings | `621f814c810c7b9f53706fd67f22832e45a626565147d9c25fb2f47a77876281` |
| Independent AUDIT.SHA256, 228 members | `9fd47d286e5c00a6865b23fe2ea9307644fd8dda286144e06d6658a4724e52f4` |
| Parent ACCEPTANCE.json | `98f425ff6118991b64de6b6242815996762baf1c99734d6f39facf21ac70d4a7` |
| Parent chain verification | `76181bd469c6cec92fb11b6be4baa2624f80fd24d827dba121198a49efd46bb7` |

The accepted run is
`disassembly/output/phase4-early/com.okin.eshine-1.1.8-2026-11-03-bulk101-188-001/`;
its current report is `work/report-repair-sol-002/`, and the independent audit is
`audit/sol-round002/`. Acceptance records **17 PASS gates and zero open material
findings**. Before source comparison, the implementation pass independently
rehashed all **29,098 unique bound files** and verified **all 13 manifest views**,
including exact member bindings. Raw artifacts, reports, audits and extraction
outputs remain machine-local and unchanged.

The historical negative audit `bcc420fd860fb20328972585244cbd784c65639791c8baa788c0952787029c5b`
stays negative, with its historical OPEN finding. R122-SOL-001 is verified
addressed for the accepted repaired candidate only. The old audit mirror is a
lookup-only copy, never rewritten sealed text. Neither a predecessor nor an
autoresumed PARTIAL report is used as current acceptance.

## Complete disposition index

The [717-row CSV](row122-eshine.csv) is the normative discovery index:

| Inventory | Rows |
|-----------|-----:|
| Every accepted candidate ID, including 306 app methods, 242 native occurrences and 68 images | 629 |
| Every logical constructor, including clock, alarm and chord | 25 |
| Every native method-channel selector | 30 |
| Explicit semantic, lifecycle, consumer and exclusion reconciliation | 33 |
| **Total** | **717** |

| Disposition | Rows |
|-------------|-----:|
| IMPLEMENTED | 305 |
| ALREADY_IMPLEMENTED | 1 |
| EXCLUDED | 411 |
| **Undisposed** | **0** |

The 629 candidate rows themselves contain 260 IMPLEMENTED and 369 EXCLUDED
entries. Each row retains its accepted ID, exact evidence/source reference and
reason. App-method rows retain the accepted source-range SHA-256. Implemented
rows identify concrete source symbols and focused tests. The sole
ALREADY_IMPLEMENTED row credits config-entry identity/selection persistence,
with a source and test reference; it does not claim a related protocol is
already equivalent. Occurrence counts are not distinct feature counts.

The artifact has **25 logical constructors**, **22 fixed manager arrays plus two
raw chord implementations**, and two dynamic builders. There are **three
selectable profiles plus one dead sentinel**. E3000/E3100 is one selector, not two.
Every fixed constructor has an independent literal test, and dynamic builders
have calendar, clock and byte-encoding vectors. The accepted report's 120-vector
replay is static evidence, not a claim that the integration reproduces unsafe
app behavior byte-for-byte in every malformed or lifecycle case.

## Implemented bed behavior and HA consumers

| Domain | Implementation and exposure |
|--------|-----------------------------|
| Product selection | Explicit `eshine_e2000`, `eshine_e30003100`, `eshine_e5000`; app-search choices, required variant, side-owned profile, hidden irrelevant generic settings |
| Discovery | Case-sensitive `Smartbed` substring as a candidate only; exact address identity; existing confident receiver detection keeps priority |
| GATT/session | Exact UART service/write/notify roles; write-without-response required; notify or indicate; awaited subscription; connection-bound callbacks and writes |
| Movement | Head, Foot, E5000 Head Tilt; covers, movement buttons and generic held actions; 300 ms refresh and captured 200 ms STOP release |
| Presets | Flat, Zero Gravity, Anti Snore, Reading, Watch TV; Flat+Zero Gravity chord; bounded sustained recall through `hold_control` |
| Massage | On/off, head/foot strength increments, wave increment and timer increment; single action then query after 50 ms; wave requires reported enabled state |
| Light | Night Light held toggle and feedback, gated to E3000/E3100/E5000; no invented discrete on/off or brightness command |
| Clock/alarm | Civil-clock sync; enable/disable next-occurrence alarm; single weekday bit and exact action mapping; double set/query sequence; all-target preflight before writes |
| Massage state | Remaining seconds, timer index, enabled, wave, separate strengths, combined diagnostic and raw values; zeroed disabled UI projection, no clamps |
| Light state | Byte13 exactly one means on, independently of massage enabled; drives the enabled feedback light entity |
| Alarm state | Enabled normalization, action selection, local normalized datetime and raw day/type/time/enable attributes; no capability inference from reported action |
| Entities/card | Product-gated buttons/covers, massage and alarm state sensors, generic alarm/clock/held services; existing card sections and side routing |
| Pairing | No app authentication/bond or side/coupling frame. Single-address pairing disabled. Existing HA two-address pairing retains each physical side's explicit profile |
| Reconnect/error | No stale-session writes, listeners or buffer; connection loss invalidates state; subscription failure cleans up; cancellation always attempts original-session STOP |

Implementation:
[`eshine_okin.py`](../../../custom_components/adjustable_bed/beds/eshine_okin.py),
[`eshine_okin_protocol.py`](../../../custom_components/adjustable_bed/beds/eshine_okin_protocol.py),
[`tests/test_eshine_okin.py`](../../../tests/test_eshine_okin.py).
The [bed guide](../../beds/eshine-okin.md) is the user-facing protocol reference.

## Deliberate safety and framing corrections

Every correction has a separate EXCLUDED semantic row alongside its implemented
safe counterpart. None establishes a new packet, hardware behavior or STOP
scope:

- **S-unsafe-mutable-stop:** the app's delayed callback rereads shared field63,
  so another command can replace STOP. HA captures the proven literal and the
  original live session, and releases in `finally` with a fresh cancellation
  event. Shielded cleanup drains before task cancellation propagates. The 200 ms delay remains explicit.
- **S-unsafe-delayed-work / S-subscription-bugs:** the app's unretained futures,
  duplicate listeners and route/device-switch races are unsafe. HA awaits its
  operations, cancels delayed work, subscribes once, fences late callbacks and
  clears state on disconnect. It never sends an old request to a new target.
- **S-unsafe-buffer:** the exact marker is raw length20, raw byte1 `fe`, byte2
  `16`, with byte0 unchecked. App concatenation retains that unrecognized header
  and suppresses one later valid message, even across sessions. HA traces and
  ignores the unknown frame, then accepts the next complete recognized delivery.
  There is no invented reassembly format or guessed hardware fragment contract.
- **S-unsafe-truncation:** the app can update massage before throwing at missing
  byte13. HA requires complete accessed fields and publishes an atomic update;
  malformed/truncated messages cannot throw from a BLE callback or partly
  replace reported state.
- **S-alarm-parameter-race:** the app's second alarm write rereads mutable UI time.
  HA snapshots every validated request argument for both writes.
- **S-duplicate-name-ui:** HA preserves distinct physical addresses with equal
  names, avoiding the app's duplicate-name list defect.

HA consumers are continuously mounted rather than tab-dependent. Connection
initialization queries state and alarm without setting the clock; clock sync is
explicit and runs before enabling an alarm. Received values remain observations,
not optimistic success or physical position. The local reference date/seconds
for alarm display comes from HA's current local time, without recreating an
unrelated stale Flutter picker object. Raw fields remain available.

## All exclusion classes

The CSV provides every individual EXCLUDED row and exact evidence. These are the
complete classes, not implementation debt:

1. **Product boundary:** WiFi, provisioning, SSID/password and network
   administration; cloud/accounts/login/HTTP/MQTT; OTA/DFU/bootloader and firmware
   management; Bluetooth Classic/advertising and unrelated infrastructure.
   Accepted E-NEGATIVE/E-SEARCH/E-NATIVE found no selected app-owned paths.
2. **Dead or unselected behavior:** the `unKnown` sentinel, unused SDK read/bond/
   PHY/priority/RSSI/descriptor/adapter-toggle APIs, dead assets, and absent
   position/battery/device-info, numeric-memory, capability-query, calibration,
   advanced-light or partner/coupling commands. No shared transport or method
   name establishes these as features.
3. **Android/Flutter infrastructure:** permission prompts, engine hot restart,
   singleton/global plugin mutex, object marshalling, OS bond broadcasts,
   optional service-change subscription, MTU512 request and app scan timers.
   HA's existing Bluetooth adapters/proxies, connection manager and Bleak own
   host setup. These Android implementation details are not bed commands.
4. **Companion UI:** packaged graphics, launcher/framework images, layout,
   clipping, route rendering, dialogs, logging, Flutter preferences and the
   5.5-second success toast. Action, product-gate and state semantics have their
   own implemented rows. All 68 images were visually inspected in the two
   accepted contact sheets; no hidden controls were inferred.
5. **Unsafe app behavior:** the six correction classes above. Physical STOP
   scope, preset persistence and real radio outcomes are never assumed.

## Validation and limits

Focused tests cover literal packets, profile/setup/factory contracts, subscription
and GATT failures, cancellation/error release, changed-session rejection, delayed
query cancellation, reconnect and stale callbacks, consumer arithmetic including
unusual values, malformed notifications, public-service validation, all-target
preflight, HA entities and card buckets. Existing shared controller, profile,
service, pairing, discovery and lifecycle tests validate the reused paths.

Hardware remains **Needs testing**. Physical effects, ATT outcomes and preset
persistence can be validated by real users after beta/release; no maintainer
hardware acquisition or immediate test is required. No static implementation
scope is deferred to those checks. Global audit queue/tracker publication remains
the parent coordinator's responsibility.
