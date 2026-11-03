# Row101: Casper Base 1.0.8 disposition ledger

This is the separate source-comparison and implementation record for standalone row101.
Only the independently accepted replacement report is artifact authority. Integration code,
historical documentation and other apps were comparison material, never artifact facts.
The report, extraction, raw APKs and both audit rounds remain immutable and machine-local.

## Authority and verification

- `artifact_set_sha256`: `2d21d42c17a7b5ae60c2403ff3654d80993e6d09f879cfe666c6d58270123f8b`
- `report_manifest_sha256`: `1cc13b9e51aa6e74e7f6a507c7418b1420f72a734d5eb7027b60db11ccf6daef`
- `analysis_json_sha256`: `6fefbf3117f3ab8cbd67444cd5e78fe1332be87b0cee51346f60f3639d37d551`
- `supersession_sha256`: `db85bf1dab6f2ac7fea3dee4c4f1d2bdfae183db784c754aff21878b945cfd31`
- `audit_manifest_sha256`: `bfc0cea59e3685b8970fbb6d5d5728973238dd8789235b09f6600396c98dbbc0`
- `audit_md_sha256`: `9edaff4734760946a69b11bcd112c1293ca028d3ebfa0710c78496fa5d001af1`
- `findings_sha256`: `eb3e05f40a14e77fd7561fd4af327c221e1b1e5ccbd89231aeae65597827ef44`

All 33 report, 676 evidence, 71 audit and 133 input manifest members were rehashed
read-only before comparison. The accepted audit is ACCEPT, 17/17 gates, zero open
material findings; SOL101-001/002/003 remain closed. No superseded wording is reused.

## Coverage

The [machine-readable ledger](row101-casper-base.json) has **568 individually identified entries**:
**535 IMPLEMENTED, 0 ALREADY_IMPLEMENTED, 33 EXCLUDED**. Repeated protocol rows are
separate provenance entries, not claims of 535 distinct user features. Every row resolves
through concrete implementation and validation groups. There are no pending dispositions.

| Domain | Entries |
|---|---:|
| command | 181 |
| notification | 69 |
| discovery_rules | 4 |
| gatt | 4 |
| session_sequence | 4 |
| packet_format | 4 |
| capabilities | 4 |
| timing | 4 |
| release_behavior | 4 |
| product | 41 |
| command_item | 60 |
| decoder | 56 |
| receive_consumer | 113 |
| behavior | 7 |
| exclusion | 13 |

The 181 outgoing rows include automatic anti-snore sends separately from manual recall
and programming. All 41 product objects, 60 command items, 69 receive rows, 56 decoder/
helper entries and 113 event producer/consumer sites are accounted for. Conditional
stored products remain explicit choices; their names establish no other app compatibility.

## Implementation contracts

- P1/P2 use the package-local catalog and all six GATT layouts. Product layout, capability
  replies and explicit side selection remain separate. The same UUID never identifies an app.
- All setup queries, STOP/release, motors, presets/save, massage/fan/heating, music source
  callbacks, single/repeating alarms and both ordinary/groove light builders are covered.
  Album/play/volume/USB state, alarm acknowledgements, exact-list equality and ID updates,
  RGB state and raw uncalibrated motor/desk/diagnostic events remain exposed.
- MM/SXB use separate physical-entry state. Their JSON/envelope, write types, MTU chunks,
  time/partition/live/report requests, gzip/typed report data and information queries are retained.
  No sensor reading selects a motor capability or automatically drives the bed.
- All 43 retained response constructors, seven forwarding closures and four numeric helpers
  are represented by the response schemas/decoder and typed list conversions. Two firmware
  transfer constructors are explicitly excluded. Nullable information strings merge in order;
  a nonzero error does not suppress their retained direct BLE state.
- Live state checks both typed sides before consumer entry, mutates complete left then right,
  retains short-packet prior fields, resets validity at entry and preserves earlier assignments
  when a later token/index fails. Frozen sequential/negative vectors cover this distinction.
- The external detector adapter samples every 3 seconds. Manual, automatic default-left and
  selected-side catalog send uses remain distinct. Phone DSP/acquisition stays excluded.
- The RCRM finder only connects, without setup queries, ExitLimit or an invented locator frame.
- HA preflights all physical targets and owns locking, cleanup, typed services and per-side
  product settings. Scoped tests exercise the real coordinator lock, services and task teardown.

## Every exclusion

The table below lists every excluded ledger row. Overlapping entries identify the exact
source occurrence as well as its shared exclusion policy. Their valid reasons are product
boundary, unreachable/dead code, unrelated phone infrastructure or an explicit safety choice.

| Ledger ID | Reason |
|---|---|
| `P1.command.069` | Safety: absent long opcode falls back to zero; HA exposes save only when the artifact defines a programming opcode. No fallback packet is sent. |
| `P2.command.069` | Safety: absent long opcode falls back to zero; HA exposes save only when the artifact defines a programming opcode. No fallback packet is sent. |
| `product.00` | Dead/empty placeholder: no command-bearing lists or model-selection control surface, as dispositioned in accepted E-CATALOG. The two distinct class layouts are not treated as interchangeable capability records. |
| `product.40` | Dead/empty placeholder: no command-bearing lists or model-selection control surface, as dispositioned in accepted E-CATALOG. The two distinct class layouts are not treated as interchangeable capability records. |
| `item.8d54d1` | Dead constant, no product-list or write-callgraph reference. It is not a hardware command. |
| `decoder.0x534784` | Firmware transfer rdy/cont/suc state has only an OTA continuation/readiness/success consumer. Information error/ver/type decoding is separately retained. |
| `decoder.0x53456c` | Firmware transfer rdy/cont/suc state has only an OTA continuation/readiness/success consumer. Information error/ver/type decoding is separately retained. |
| `consumer.000` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.001` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.002` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.003` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.004` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.022` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.029` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.033` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.034` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.043` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.044` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.045` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `consumer.112` | App-local privacy, permission, navigation, display-name/database refresh event. No bed BLE transformation or additional bed-control consequence; HA setup/state infrastructure and direct connection events are separately covered. |
| `excluded.phone_audio` | Unrelated companion-phone audio infrastructure. |
| `excluded.ota_cloud` | Firmware/cloud/OTA product boundary, regardless of BLE transport. |
| `excluded.network_provisioning` | Network/Wi-Fi provisioning outside the BLE bed product boundary; no command invented. |
| `excluded.datastore` | Unrelated generic storage infrastructure, no bed transformation. |
| `excluded.phone_ui_storage` | Unrelated companion-app storage/presentation; direct BLE state remains exposed. |
| `excluded.unused_plugin` | Dead plugin cases are not reachable app features. |
| `excluded.unsafe_zero_long` | Safety: omit undefined programming gestures; retain proven short actions. |
| `excluded.unsafe_app_lifecycle` | Safety: owned cancellable HA tasks, bounded requests and deterministic cleanup replace harmful app bugs. |
| `excluded.unsafe_cross_service` | Safety: first coherent service/write/notify selection; never mix roles across services. |
| `excluded.unsafe_shared_sensor_state` | Safety: independent physical-entry state, serialized transactions and MTU-aware writes. Proven per-protocol commands remain available. |
| `excluded.unsafe_malformed_receive` | Safety: preserve complete ordinary notifications and marker-valued data at supported 5/7/16-byte boundaries, reject malformed lengths, catch typed/bounds failures, cap report decompression; retain partial live state and diagnostics. No length header or ordinary checksum gate is invented. |
| `excluded.unrelated_disconnects` | Safety: HA only owns and disconnects the selected physical target. |
| `excluded.p3_empty_init_builder` | Dead outbound builder: do not extrapolate a P4 packet to P3. |

Unsafe app lifecycle behavior is documented, not silently copied or called missing evidence.
HA serializes writes, cancels owned timers and delayed work, selects coherent GATT roles,
avoids unrelated-device disconnects, rejects undefined long programming commands and
bounds malformed frames/report decompression. The accepted ordinary marker-splitting bug is corrected at supported notification lengths, preserving checksum-valued markers and current music-source state. Ambiguous variable-length fragment combinations have no inferred header. Proven hardware commands are unchanged.

## Validation and external status

Focused fixed-byte vectors, all product/control declarations, receive branches, sequential
typed consumers, service preflight, cancellation and the real coordinator serialization path
are in `tests/test_casper_base*.py` and `tests/fixtures/casper_base/`. The focused runs and
whole-tree Ruff/Pyright, frontend check/test and independent Sol review are recorded in the
row101 implementation handoff. Publication remains blocked until those checks/review pass.

Hardware, ATT/radio effects and sensor accuracy remain **DEFERRED_REAL_USERS_AFTER_BETA_OR_RELEASE**.
There is no deferred static implementation work. No maintainer bed acquisition or immediate
hardware test is required. The PR remains unmerged; release/deployment are separate decisions.
