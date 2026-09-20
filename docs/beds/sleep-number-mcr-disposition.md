# Sleep Number MCR / Sleep Expert discovery disposition

Evidence: SleepIQ 5.4.11 (version code 1787576046), APK SHA-256
`710b7dfd536007fc4812ad9a16402be3c1bf882cfc27fa9214ad72154bf36f5f`.
The accepted package report manifest is
`1c751b8ba76fd89d85eb0fb96f20d1f7fbc40171e3c3e3a7c59be3d36463475d`.
This comparison was performed after that report was frozen. Raw artifacts and
reports remain local. Hardware validation is pending real-user testing.

The implementation is `beds/sleep_number_mcr.py` and
`beds/sleep_number_mcr_protocol.py`. Semantic service documentation is in
[sleep-number-services.md](sleep-number-services.md). Basic controls use normal
covers, position numbers, firmness numbers, preset selects, massage buttons,
under-bed lights and warming climates. Additional commands and structured status
are available through the locked `sleep_number_command` service.

## Transport and model decisions

Binding sends a persisted nonzero random 64-bit identifier with zero header
addresses. The reply supplies the peer and client addresses; neither is derived
from the Bluetooth MAC. Requests use RIGHT=0 / LEFT=1. Matching checks the response
bit, negotiated addresses, node class and opcode; SE chunk transfers also check
the selector. Notification setup preserves the artifact's 128 ms service-discovery delay. Ordinary response timeout is 900 ms, long-transfer chunk timeout is
1800 ms, with three timeout retries. Writes split at ATT MTU minus three and retain the existing response-first
ESPHome compatibility path. If a local adapter rejects that write mode, the
chunk falls back to an advertised write-without-response operation. Invalid CRC, truncated responses, overlong SE values,
unknown commands, invalid parameters and unsupported feature requests are rejected.

Foundation capabilities come from its node and system status. Foundation
configuration controls articulation sides independently of pressure chambers.
Pressure requires the pump's DUAL selector, both present chambers and no KID
chamber before exposing two pressure sides. Warming follows pressure configuration:
dual has both sides; single routes to the artifact's LEFT warmer, with both physical warming writes on single-chamber 360 pumps. Massage sides follow available massage status independently of articulation. Manufacturer
advertisement classification determines 360 eligibility for Responsive Air; legacy
chamber types refine Adult/Genie/K1/K2. No bed model is assumed from its name.

Microadjust sends one absolute target and uses side-specific continued-adjustment
status requests during the hold. It releases every selected side after the
requested hold or cancellation. Each release uses a fresh cancellation token;
one side's release failure does not suppress the other. Cancelled firmness writes issue fresh-token pump ForceIdle and poll status every 500 ms until inactive. A separate 10-second HA safety deadline
bounds this cleanup, including the ForceIdle request, so an unresponsive or
continuously busy pump cannot hold the command lock indefinitely. Deadline expiry
raises an error asking the user to check the bed and Bluetooth connection; it does
not report that the pump stopped. This deadline is an integration safeguard, not
an APK-derived protocol timing value. Native absolute positions and presets are
monitored until stationary and stop on completion, cancellation or failure.
Motion values are percentages, not degrees.
A preset recall is distinct from saving or restoring its stored definition.

## Discovery ledger

Each row has one disposition. Test references below refer to
`tests/test_sleep_number_mcr.py`; exact packet fixtures are committed test literals,
not runtime imports from the local APK workspace.

| ID | Frozen discovery | Disposition | Implementation, verification, or exact exclusion |
|---|---|---|---|
| M01 | C4624a chamber types | IMPLEMENTED | `query_config`; presence, type and optional diagnostics; `test_connect_negotiates_addresses` |
| M02 | C4625b foundation short bind, node 72/opcode 11/subcommand 2/payload 41 | EXCLUDED | Installer reassociation changes the foundation's binding, outside normal control and unsafe to offer as an unguarded control command. Existing association is preserved. |
| M03 | C4626c session bind | IMPLEMENTED | `_async_initialize_session`; assigned addresses, persisted random identifier; `test_binding_requires_valid_reply`, frozen bind vector |
| M04 | C4627d foot warming change | IMPLEMENTED | `foot_warming`, warming climate hooks; frozen payload 48/LE duration and command vectors |
| M05 | C4628e warming status | IMPLEMENTED | `_read_warming`, levels and signed duration; `foot_warming_status` |
| M06 | C4629f pump idle | IMPLEMENTED | Firmness preamble and `stop_all`; frozen idle vector |
| M07 | C4630g preset recall | IMPLEMENTED | `set_foundation_preset_for_side`; model-gated names, artifact vectors |
| M08 | C4631h microadjust absolute targets | IMPLEMENTED | `_move_axis`; 12-byte unchanged-field mask and cleanup; frozen vectors and cancellation test |
| M09 | i foundation status | IMPLEMENTED | `decode_foundation`; all actuator flags, positions, timers, presets; parser vector test and `foundation_status` |
| M10 | j outlet control | IMPLEMENTED | `outlet`, `lights_on/off`; nightstand 1/2, nightlight 3/4, UBL 3; payload vectors |
| M11 | k outlet status | IMPLEMENTED | `outlet_status`, `_async_read_underbed_light_state`; state and signed LE timer |
| M12 | l pinch status | IMPLEMENTED | `decode_pinch`, `pinch_status`; all four sensors, signed event counters; parser vector |
| M13 | m preset store | IMPLEMENTED | `preset_save`; one-byte preset vector |
| M14 | n foundation lighting intensity | IMPLEMENTED | `light_intensity`; right/left offset and unchanged-field mask; payload vector |
| M15 | o foundation system status | IMPLEMENTED | `decode_system`, runtime entity/capability gates; model and diagnostic parser tests |
| M16 | p massage change | IMPLEMENTED | `massage`, existing massage buttons; all fields, modes, timer and 255 sentinel; payload and sentinel tests |
| M17 | q massage status | IMPLEMENTED | `decode_massage`, `_read_massage`; three LE timers, enum rejection; parser vector |
| M18 | s firmness favorite store | IMPLEMENTED | `firmness_favorite`; pressure-side gate and payload vector |
| M19 | t firmness favorites read | IMPLEMENTED | `_read_favorites`, `firmness_favorites`; right/left values, no movement |
| M20 | u preset timer | IMPLEMENTED | `preset_timer`; exact 12-byte masked payload and timer vector |
| M21 | v node list | IMPLEMENTED | `query_config` node discovery; `mcr_status` exposes list and full discovered state |
| M22 | w pump status | IMPLEMENTED | `_async_read_pump_status`; active state and SINGLE/DUAL selector; `test_pump_single_chamber_does_not_expose_second_side` |
| M23 | D Sense-and-do configuration | IMPLEMENTED | `sense_and_do`; node-gated inverse enable byte; payload vector |
| M24 | E Sense-and-do status | IMPLEMENTED | `sense_and_do_status`; enabled iff byte 1 zero |
| M25 | F firmness target | IMPLEMENTED | `_set_sleep_number_for_chamber`; explicit pressure/head-tilt routes, RIGHT 0/LEFT 1, frozen vectors |
| M26 | G kids outlet/light change | IMPLEMENTED | `kid_outlet`; separate nullable settings encoded FF/00/01, trailing 00; payload vector |
| M27 | H kids outlet status | IMPLEMENTED | `kid_outlet_status`; indexed light/outlet/update/in-use flags |
| M28 | A SE long-write select | EXCLUDED | Reachable long values are WiFi credentials SWSS and cloud-supplied setup configuration SWCF. Provisioning the bed's WiFi/cloud account is outside this local BLE control integration. No raw long-write escape hatch is exposed. |
| M29 | B SE short read | IMPLEMENTED | `_se_read`; safe catalog keys, E fallback and F rejection |
| M30 | C SE short write | IMPLEMENTED | `_se_write`; every in-scope control fits a 4-byte key plus a value of at most 11 bytes. App's 12..15-byte malformed short-write boundary is rejected, not reproduced on hardware. |
| M31 | x SE long-read chunks | IMPLEMENTED | `_se_read`; C/D/E cycle, empty limit, length/CRC validation; long-read tests |
| M32 | y SE long-read select | IMPLEMENTED | `_se_read`; versions force long route; E/F reject and 8-byte metadata validation |
| M33 | z SE long-write chunks | EXCLUDED | Same provisioning-only callers and product boundary as M28. Unsafe malformed or raw configuration writes are not offered. |
| S01 | A SRFS version | IMPLEMENTED | `software_versions`, verified long read and raw RFS output |
| S02 | B SYST network status | EXCLUDED | WiFi/internet/cloud-server status belongs to bed network provisioning, not local BLE bed control. |
| S03 | C SWSC WiFi scan list | EXCLUDED | WiFi setup/discovery product boundary; no WiFi credentials/configuration flow exists in this integration. |
| S04 | C2983g MUAG automatic light state | IMPLEMENTED | `underbed_auto_status`; signed-byte accumulator and AUTO boolean |
| S05 | C2999x LRSG Responsive Air state | IMPLEMENTED | `responsive_air_status`; right bit 0, left bit 1 and 360 gate |
| S06 | C3001z SREL raw Bammit version | IMPLEMENTED | `software_versions.bammit`, forced long read |
| S07 | D SWST current WiFi | EXCLUDED | WiFi provisioning/status product boundary, as S02/S03. |
| S08 | GetSoftwareInfoCall normalized SREL | IMPLEMENTED | `software_versions.software`; first underscore token and uppercase Z removal |
| S09 | H SWSI WiFi setup-version | EXCLUDED | Gates cloud configuration selection only; outside the local-control product boundary. |
| S10 | L MFRL/MFRR reset preset | IMPLEMENTED | `preset_reset`; distinct from recall/save, SE payload vectors |
| S11 | SetWifiCredentialsCall SWSS | EXCLUDED | WiFi credential provisioning outside this integration; avoids handling/logging WiFi credentials. |
| S12 | W MFUL/MFUR/MFFL/MFFR position | IMPLEMENTED | `_set_position`; percent_0 ASCII, side/axis capability gates and cancellation cleanup; SE vectors |
| S13 | i0 LRRE/LRLE Responsive Air | IMPLEMENTED | `responsive_air`; exact BE32 boolean; 360/SE/pressure gates, SE vector |
| S14 | k0 SWCF setup configuration | EXCLUDED | Cloud-provided account/bed installation document and WiFi setup are outside local control; runtime cloud schema is not reconstructed. |
| S15 | n0 MUAS auto-light write | IMPLEMENTED | `underbed_auto`; exact one-byte bool, SE vector |
| S16 | q0 MFHL/MFHR movement stop | IMPLEMENTED | `_stop_side`, `_stop_sides`; ASCII 110, fresh cancel token, all-side cleanup tests |
| S17 | s0 SWSF WiFi fallback | EXCLUDED | WiFi installation fallback only, same provisioning boundary as S11/S14. |
| X01 | SmartPump advertisement classification | IMPLEMENTED | `classify_smartpump`, factory passes manufacturer bytes; classification vectors |
| X02 | Foundation generation/model and actuator/preset gates | IMPLEMENTED | `FoundationFeatures`, `decode_system`, runtime cover/number/select/climate capabilities |
| X03 | UART weighted checksum | ALREADY_IMPLEMENTED | `_mcr_crc` unchanged; `test_all_frozen_transport_vectors` checks 16 independently frozen exact frames |
| X04 | Fragmentation, reply matching and response retries | IMPLEMENTED | `_async_write_frame`, `_frame_matches_request_key`, `_async_send_frame`; MTU/property and retry tests |
| X05 | K2 head tilt | IMPLEMENTED | `head_tilt`; selects HEADTILT chamber preferring left, pressure 5/100; no foundation required |
| X07 | Genie obsolete pressure setters | EXCLUDED | `capability/sleepnumber/a.java` throws unconditionally from both firmness and favorite setters. Read-only status remains available, but these unreachable obsolete mutations are suppressed. |
| X06 | UI lifecycle and transport ownership | EXCLUDED | Android foreground/background/passive timer and cloud CDC failover are app lifecycle behavior. HA owns reconnection, scheduling, Bluetooth access and command serialization; Android activity lifecycle is not copied. |

Totals: **57 rows: 44 IMPLEMENTED, 1 ALREADY_IMPLEMENTED, 12 EXCLUDED**.
Exclusions are individually enumerated in M02, M28, M33, S02, S03, S07, S09,
S11, S14, S17, X06 and X07. No in-scope control is deferred for lack of maintainer
hardware. Physical semantics and device-specific compatibility remain unverified.

## Motion follow-up from the BedRemote comparison (2026-09-20)

This follow-up reuses the accepted artifact and report identified above. It is a
post-freeze comparison against BedRemote commit
`360dd040eb02bfefb13b089a04bde601026259a5` and integration v4 commit
`9bd5ee81b9e319773a9ec83f1eeb177bb543ecf8`, not a new clean-room analysis.
The original 57-row catalog and corpus completion counts remain unchanged.

Artifact-local references (Java package `com.selectcomfort.sleepiq` appears as
`com.selectcomfort.p066sleepiq` in jadx):

- `device/call/C2988l.java:46` and `capability/flexfit/q0.java:46`: continued
  adjustment uses selector `side + 2`, no payload. Authoritative
  `capability/flexfit/a0.smali`, methods `n` and `B`, establish the 333 ms delay.
- `device/call/W.java:79-88`: native target keys and decimal `_0` values.
  `a0.smali` methods `t` and `x`: 1000 ms initial delay, 333 ms moving checks,
  two further stationary samples separated by 500 ms; `Nd/d.java:62` ORs all
  four actuator moving flags. `C3948a0.h` supplies the target tolerance, less than 3.
- `C3948a0.b`, `w`, and `a0.smali` methods `e`, `t`: diagnostic gates, 360
  obstruction status, non-split two-side event comparison, selected-side Flat
  recovery. Flat recovery here retains fault gates as an explicit safety boundary.
- `device/call/q0.java:49-57`: selected-side `MFHL`/`MFHR`, ASCII `110` STOP.
  `device/call/X.java:45` and `app/v4/ui/bed/flexfit/screen/S.java:76-84` preserve
  the selected side for ordinary presets; Partner Snore is the explicit exception.

The controller owns the polling inside the coordinator's command lock. Held
movement refreshes selected sides even when optional angle sensing is disabled.
Every status reply publishes decoded positions. Targets must finish within the
artifact's tolerance; Flat also requires the homing flag to clear. Status bytes
`0x62` and `0x63` both mean homing is still required.

The integration bounds target/preset monitoring and held target dispatch at 120 seconds, each side's STOP
at 10 seconds, and final status readback at 10 seconds, including GATT writes.
These are HA safeguards, not APK timing values. Held motion releases immediately
when its configured duration expires, before post-movement obstruction checks.
STOP and final read use fresh cancellation events. Failed cleanup is reported;
an existing movement error is preserved. A readback failure is not reported as
successful completion, and the final read is checked for newly reported faults.
Non-Flat presets require the reported current preset to match the requested one;
stationary feedback alone does not prove an acknowledged request executed.
For obstruction event counters, HA conservatively rejects any change, including a
signed-byte wrap or reset, rather than copying the app's numeric-increase check.
It reports a changed counter without guessing whether the cause was a rollover
or reset. These completion guards add no protocol commands. No physical
validation is claimed.

| ID | Finding | Disposition | Implementation, verification, or exclusion |
|---|---|---|---|
| H01 | Held-motion continuation | IMPLEMENTED | `_move_axis`, `_read_foundation`; `test_held_motion_keeps_selected_side_moving`, `test_hold_keeps_refreshing_while_opposite_actuator_moves` |
| H02 | Native target/preset completion | IMPLEMENTED | `_wait_for_foundation`; `test_absolute_target_waits_for_stable_feedback`, `test_absolute_target_reports_early_stop`, `test_target_waits_for_opposite_actuator_to_stop` |
| H03 | Movement diagnostic handling | IMPLEMENTED | `_check_foundation`, `_check_pinch`; actuator/homing/obstruction rejection tests and shared/split obstruction-event tests |
| H04 | Bounded release and final readback | IMPLEMENTED | `_foundation_motion`, `_finish_foundation_motion`, `_stop_sides`; cancellation, timeout, release-order and original-error preservation tests |
| H05 | Explicit monitored Flat recovery | IMPLEMENTED | `set_foundation_preset_for_side`; `test_preset_keeps_selected_side_and_monitors_recovery`, `test_flat_does_not_mistake_homing_flag_for_recovery` |
| H06 | Selected-side preset packets | ALREADY_IMPLEMENTED | Retained selected-side opcode `0x15` and preset IDs; both-side preset tests |
| H07 | Position/actuator flag decoder | ALREADY_IMPLEMENTED | `decode_foundation`; existing parser fixtures retained, published positions exercised by motion tests |
| H08 | Native 0..100 position values | ALREADY_IMPLEMENTED | Native SE target path retained; no universal head-83 rescaling supported by this artifact |
| H09 | MotorStart, direct foundation ForceIdle and alternate absolute packets | EXCLUDED | Hardware/version-specific leads not established by the accepted APK's reachable motion path; do not replace confirmed commands |
| H10 | Blanket global-preset restrictions | EXCLUDED | APK preserves selected-side routing; mechanically shared sections require layout/firmware-specific real-user validation after beta/release |
| H11 | New occupancy capability | EXCLUDED | Comparison produced no dependable occupancy method |
| H12 | Unrestricted reset-to-flat bypass | EXCLUDED | The app's reset path can bypass ordinary diagnostic gates. HA permits homing recovery but conservatively refuses configuration, actuator and obstruction faults; no force-reset control is exposed |

Follow-up totals: **12 rows: 5 IMPLEMENTED, 3 ALREADY_IMPLEMENTED, 4 EXCLUDED**.
Exclusions are H09–H12. Together with the original catalog: **69 rows:
49 IMPLEMENTED, 4 ALREADY_IMPLEMENTED, 16 EXCLUDED**. These are discovery
dispositions, not additional package completions or changes to the frozen corpus.
