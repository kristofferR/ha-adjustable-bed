# Row 018: RMControl findings-to-integration disposition

Target: `release/4.0`. Ref #443 and #436.

**Evidence reconciliation accepted; implementation validated.** The table below
describes actual code, not a claim that the cluster PR is complete or merged.
Product/reply gates for repeating alarms, RGB/timers and automatic snore
intervention are independently established. Physical verification is
deferred to users after beta/release.

## Evidence boundary

The accepted post-freeze composite covers `com.richmat.rmcontrol2` 21.3.7
(version code 213700), complete 20-APK XAPK SHA-256
`f4994bebb8ca20af8aea70c64faf17212692b2ffe1730e463a3b0cbeed7b0312`.
Composite report manifest SHA-256:
`3038c935d219550968b21a2a5c8f363d17aac4ef38f668fb5f58a3e4d9bc745d`.

Machine-local roots under `disassembly/output/phase4-early/`:

- H: `com.richmat.rmcontrol2-21.3.7-20260827`, preserved original evidence.
- C: `com.richmat.rmcontrol2-21.3.7-20260906-comparison-001`, accepted corrected
  runtime inventory and inherited full-report evidence.
- P: `com.richmat.rmcontrol2-21.3.7-20260908-packet-check-001`, separately frozen
  side-before-command correction and exceptional action prefixes.
- A: `com.richmat.rmcontrol2-21.3.7-20260908-packet-amendment-001`, pinned
  dependency overlay, manifest
  `e18e22419130959389076d23e907226e8acf36a5531217a9e4352912411ad1f5`.
- S: `com.richmat.rmcontrol2-21.3.7-20260908-scalar-check-001`, fresh scalar
  appendix, manifest
  `80522a5e45182f611985aa15d0a3fc22e430be6896b095de38b8b2c92d7552c4`.
- R: `com.richmat.rmcontrol2-21.3.7-20260908-scalar-review-001`, independent
  scalar and complete-composition acceptance, manifest
  `63b09f74e06b8591de3314c0bf4ee2dca020b86a6b73cee389a369c5904acb25`.

C's acceptance, validation and referenced-input manifests retain provenance.
Its amendment replaces 2,809 incorrect runtime mapping rows and 5,502 dependent
command objects; 9,326 static occurrences remain unchanged. The inventory has
1,167 concrete selectors, 234 empty selectors, 16,578 detail occurrences, 15,739
transport occurrences and 383 mapping families before A. A corrects 20,061
dependent fields, withdraws 20 local-only Clock/Voice command rows and four
local-only vectors, and records 15,729 BLE transport occurrences, 381 BLE mapping
families and 858 vectors. Historical counts are retained rather than silently
rewritten. These are inventory counts, not distinct bed features.

S recovers 1,168 factory cases including the default selector, with 16 typed
scalar properties each. Its 18,688 cells are independently checked against native
instructions and constructor/copyWith joins. Factory metadata and runtime menu
replies remain separate requirements; library-only flags do not enable features.
R accepts the composition with explicit precedence for the packet, specialized
and scalar corrections. The appendices retain scoped PARTIAL schemas because
they do not individually repeat the accepted full-app analysis. R records no
remaining artifact dependency gaps; implementation and hardware acceptance are
separate.

[Specialized evidence and interpretation corrections](row018-rmcontrol-specialized-evidence.md)
records exact source addresses for countdown versus clock sync, repeat-alarm
fields, anti-snore mode encoding, inbound/outbound layout, and semantic decoders.
This is a post-freeze comparison, not a replacement clean-room analysis.
No raw APK, decompiler output or original report is deleted or committed.

## Implemented route

The implementation is explicitly selected with `rmcontrol_product` and
`rmcontrol_side`; an empty product preserves the existing Richmat controller.
See [RMControl configuration and services](../beds/rmcontrol.md).

Code anchors are relative to `custom_components/adjustable_bed/`. Test anchors
are under `tests/`. “Implemented” describes local code plus focused coverage;
it does not assert hardware confirmation or a completed integration PR.

| Finding domain | Current disposition | Working implementation and validation |
| --- | --- | --- |
| Artifact identity and runtime aliases | Accepted evidence, no runtime analysis | `richmat_profiles.py` preserves concrete selectors, getter/occurrence context, effective overrides and gesture signatures. `test_richmat_profiles.py` checks inventory and empty selectors. |
| GATT roles and write properties | Implemented for explicit RMControl route | `beds/rmcontrol.py:detect_rmcontrol_transport`, `start_notify` select source-known service/write/notify roles and actual characteristic properties. `controller_factory.py` leaves legacy discovery and profiles intact. `test_rmcontrol.py` covers service-role/property rejection and Nordic write mode. |
| Notification session | Implemented | `start_notify` subscribes, resets session state and sends the recovered ExitLimit/CheckClock/CheckLight probes, with alarm time sync and sleep discovery under their source-specific product gates. `stop_notify` removes the subscription and clears partial bytes. State changes use coordinator callbacks. |
| Normal/Nordic packets, side and exceptions | Implemented with corrected evidence | `rmcontrol_protocol.py:build_action` uses P's `6e 01 side command sum`, one-byte Nordic output and 18 exceptional prefixes. `test_action_side_precedes_command` checks nonzero sides; controller tests check product overrides and release. |
| Serialization, gestures and release | Implemented | `beds/rmcontrol.py:async_execute_product_action` resolves an exact occurrence, distinguishes short/long/sustain, repeats held commands at source 100 ms cadence and releases with a fresh cancellation event. Existing coordinator locking is reused. `test_motion_uses_corrected_product_bytes_side_and_fresh_release`, `test_task_cancellation_still_releases`, `test_motion_failure_still_releases_without_masking_error`, `test_release_failure_is_not_reported_as_success`. |
| Product selection and empty catalogs | Implemented, opt-in | `config_flow.py:_rmcontrol_schema_fields`, `controller_factory.py:create_controller`, exact `get_product_profile` lookup. Empty products borrow no controls. `test_rmcontrol_wiring.py` validates options; `test_empty_profile_does_not_inherit_remote_capabilities`. |
| Core/combined motion and extra motors | Implemented from selected actions | `motor_control_specs` exposes supported standard axes; `controller_button_specs` preserves additional/combined/numbered actions without inventing physical axis names. Exact getter/occurrence selection handles conflicting duplicates. |
| Presets and programming | Implemented from selected actions | Controller preset/capability methods resolve the product catalog; additional reading/yoga/sleep/wake/side/help-get-up actions and long-press programming are reachable through occurrence-specific buttons. Unsupported features fail instead of using default opcodes. |
| Massage and advanced discrete controls | Implemented from selected actions | Typed massage methods plus `controller_button_specs` expose fixed gears, intensity/channel/mode/timer actions and supported fan, heating, airbags, anti-pinch, aroma, music, sleep/swing controls. Extra buttons are disabled by default, not omitted. No speculative parameterized setters are generated from notification-only domains. |
| Common notifications | Implemented | `rmcontrol_protocol.py:decode_notification` decodes exact capabilities/events, protocol/mode, motor/massage/music and source diagnostic enums. `NotificationBuffer` validates checksum/length, fragmentation, coalescing and source 500 ms expiry. Literal vectors and malformed-frame tests in `test_rmcontrol_protocol.py`. |
| Extended bed notifications | Implemented for source-bearing bed state | Motor, massage, white light, RGB, alarm, snore, lock, music, diagnostic channel, press/split mode, fan, aroma and heating decoders feed `_accept_notification`. Selected meaningful fields become dynamic sensors/binary sensors; all decoded fields remain in `protocol_diagnostics`. Physical units/axis mappings are not invented. `test_named_domain_updates`; `test_reported_state_precedes_entity_discovery_callback_and_retains_alarm_records`. |
| Light power | Implemented from selected actions | `lights_on`/`lights_off` retain catalog-specific power/toggle behavior. No universal light command is borrowed by an empty product. |
| RGB and light timer | Implemented | Common light ACK and exact `isHaveLightStrip` enable timer controls; the RGB light additionally requires a selected discrete or toggle power-off route. PARN accepts only its eight source colors; other selected display types use the panchromatic route. Zero timeout uses `ff ff`; choices are no timeout and 1..15 minutes. Initial RGB stays unknown until reported. Dynamic light/select wiring and focused palette/gate tests cover reachability. |
| Countdown single alarm | Implemented | The reachable alarm menu plus false `isSupportRepeatAlarm` enables single/cancel. Menu reachability requires Clock ACK and nonempty `alarmList`, except the exact PNRN initial-menu case. Actions still require an unambiguous `alarmList` entry. `richmatAlarmList` is not substituted. Countdown minutes are not wall-clock time. |
| Repeating alarm and clock/zone sync | Implemented | Repeat/delete/query require the reachable menu and true `isSupportRepeatAlarm`. Slot/time/weekdays/actions are validated and effective overrides retained. Time sync separately requires nonempty `alarmList`, independent of the repeat flag; startup uses that same source condition. Literal builders and controller/service tests cover these distinct gates. |
| Automatic anti-snore intervention | Implemented | BLE sleep metadata, the sleep-advertisement event and the six exact app-listed selectors enable the service. The ten BLE-sleep selectors receive the gated discovery query. Enable, count/time configuration and queries remain separate. Generic anti-snore state alone does not activate the feature, and no unproven time unit is asserted. |
| Five alternate-menu controls | Reconciled, no duplicate synthetic features | The source's fixed head/foot/stop enum controls use the same exact action resolution and release primitives. They do not justify borrowing unavailable controls for an empty selector. |
| Conditional None substitution | Excluded local UI behavior | C's BRRM/YFRM/YGRM branch can replace an action with None; None is not exposed as a bed command. Underlying supported movement remains reachable. |
| Phone flashlight, labels, headings and navigation | Excluded local UI behavior | `_is_transport_action` excludes identified presentation/navigation items, not arbitrary uncommon BLE features. Raw catalog evidence is retained. |
| Desk-only and sofa-specific actions | Excluded non-bed scope | FWRM/WFRM desk products and explicit `deviceFunctionSofa*` controls are not exposed. Generic bed motor actions are retained. Desk/OTA parsers do not create bed entities. |
| Blanket shared-library handler | Excluded unsupported semantics, evidence preserved | Source emits fieldless `RMDeviceBlacketDetailsModel` instances (size 0x8) after reads. It does not establish usable blanket fields/setters in this APK. See specialized evidence addresses; no invented blanket climate/schedule API. |
| OTA, cloud and Android application stack | Excluded | Firmware transfer, permissions, analytics, cloud credentials, app persistence and presentation are not bed BLE controls. Relevant local commands and version readout remain covered. |
| Physical meaning and real-device behavior | Deferred external validation | APK conformance is not a hardware test. Unknown units, numbered axes and advertised capability combinations stay conservative until real users supply beta/release feedback. |

## Validation and handoff

- Full assembled suite before the final capability-table amendment: 4,387 passed.
- Final assembled validation after the amendment: 832 passed, covering RMControl
  packets/controller/catalog/services, legacy Richmat, configuration, entities,
  controller contracts and manifest checks. The 117 socket warnings are existing
  test-environment warnings, not failures.
- CI-pinned Ruff 0.15.16 and Pyright 1.1.411: clean.
- Frozen three-input catalog regeneration, scalar native checks and independent
  composition verifier: pass.

The final cluster deliverable is one non-draft implementation PR against
`release/4.0`. Its live review/merge status is tracked in the canonical queue in
#436, the #443 progress summary, #447 and the published queue. Validation does
not imply hardware confirmation, merge or deployment. No untouched bulk work
is authorized by this handoff.
