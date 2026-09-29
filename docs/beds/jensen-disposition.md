# Jensen Adjustable Sleep implementation discovery ledger

This is the post-freeze comparison for `air.no.jensen.adjustablesleep` 2.0.37
(106), the newest accepted report. The protocol summary is in
[the Jensen guide](jensen.md). The accepted clean-room report contains 4
protocols, 84 unique command rows (88 listed per protocol), 39 candidate paths,
9 variants and 632 reproducible vectors:

- **P1** is the JMC400 protocol handled by the `jensen` bed type.
- **P2** ("LinOn": names "Adjustable Bed"/"Jensen Bed") drives LinonPI beds.
  It is reachable in 2.0.37 and handled by the `svane` bed type's Jensen LinOn
  profile.
- **P3** (Linak Exact/Exact 2) and **P4** (Linak Twin Drive/Generic Bed) are
  handled by the `linak` bed type.

The earlier 2.0.29 (98) report was compared first. Its JMC400 and Linak
behavior is unchanged in 2.0.37 except where a row below says otherwise; in
2.0.29 the LinOn setup threw before any frame was written.

Row IDs number each protocol's command rows in report order (`P1-16` is P1's
16th row); `Cnn` are the report's candidate IDs. Every row and candidate has
exactly one disposition. `IMPLEMENTED` means added or corrected in this change,
`ALREADY_IMPLEMENTED` means existing code verified against the report, and
`EXCLUDED` gives the evidence-based reason. Physical validation is deferred to
users after release; it is not an exclusion reason.

Implementation references are relative to `custom_components/adjustable_bed/`.
JMC400 tests are in `tests/test_jensen.py`, LinOn tests in
`tests/test_jensen_linon.py`.

## JMC400 (P1)

| ID | Discovery | Sources | Disposition | Implementation or exact exclusion reason |
|---|---|---|---|---|
| J01 | Name rule `/JMC400/i` anywhere in the name, unfiltered scan, type precedence | C01, C02, C03 | IMPLEMENTED | `detection.py` also accepts `JENSEN_NAME_FRAGMENT`; `tests/test_detection.py::test_detect_jensen_by_app_name_fragment`. Service-UUID and `jmc` prefix detection remain. |
| J02 | Connect, service discovery, notification subscription and CCCD | C07, C11 | ALREADY_IMPLEMENTED | `coordinator.py` connection; `beds/jensen.py:start_notify`; `TestJensenNotificationStartup`. |
| J03 | Write without response on `0x1111` | C10 | IMPLEMENTED | `start_notify` selects no-response unless the characteristic only supports writes; `TestJensenWriteMode`. |
| J04 | 5-byte PIN frame at session start | P1-22 | IMPLEMENTED | `JensenCommands.pin_unlock`; `TestJensenFrames`, `TestJensenController`. The coordinator's per-command PIN refresh is kept (`TestJensenCoordinatorAuthRefresh`). |
| J05 | 5-byte config request and `0x0A` parser (decimal digits read as hex, box type) | P1-23, C20 | IMPLEMENTED | `query_config`, `_decode_config_field`; `TestJensenConfig`, including the #631 report `0A 05 03 08 01 75`. The last report is stored in the entry (`capability_snapshot`) and reused when a later request goes unanswered; a changed report reloads the entry so its entities follow it. |
| J06 | `0x1E` PIN status reply; re-entry when locked | P1-22 | IMPLEMENTED | `_handle_notification` warns that the configured PIN was rejected; the PIN is corrected in the entry options. `test_rejected_pin_is_logged`. |
| J07 | Set a new bed PIN (`1F`) and its `0x1F` echo | P1-24, C30 | EXCLUDED | Unreachable: the PIN-change screen is gated by `hasPinCode`, which the JMC400 config service always sets false. |
| J08 | Software-revision reply (`0x04`) and DFU | C22 | EXCLUDED | Dead: the revision is never requested, no DFU store is created and no DFU library ships. |
| J09 | Position reports (`0x10`) | P1-13 (dynamic fields) | IMPLEMENTED | u16 little-endian decode with #631 hardware anchors (the app treats the bytes as opaque); `TestJensenPositionParsing`. |
| J10 | Single-section motion and STOP, repeated every 300 ms while held, STOP once on release | P1-01…P1-04, P1-09, C14 | IMPLEMENTED | `_move_with_stop`; default pulse 4 × 300 ms in `const.py`; `TestJensenHeldMovement`. |
| J11 | Combined head/foot motion | P1-05…P1-08 | IMPLEMENTED | `move_simultaneously` behind the `linak_move_simultaneously` action; `test_simultaneous_movement`. |
| J12 | Flat, sent once, then the bed moves autonomously | P1-10 | IMPLEMENTED | `preset_flat` follows reports to completion (`_monitor_movement`); `TestJensenMovementMonitoring`. Keeps the short burst and `10 FF` warm-up for the #217 reconnect behavior. |
| J13 | Device memory save/recall on box type 4 | P1-11, P1-12 | IMPLEMENTED | `uses_device_memory`, `program_memory`, `preset_memory`; `test_device_memory_slot`. Other boxes no longer send these frames. |
| J14 | App-stored favourites on other boxes: capture the reported position, recall with go-to | P1-13 (position frame) | IMPLEMENTED | Four slots persisted in an HA `Store`, recalled with the echoed `10 04` bytes and monitored; `TestJensenMemory`, `TestJensenDirectPosition`. |
| J15 | Favourite recall also replaying differing massage, fan and light frames | P1-13 (accessory frames) | EXCLUDED | App-side scene composition; each frame is available on its own (J16, J17, J19) and HA scenes compose them. The replayed fan frame lacks its `0x50` trailer and the light frame shifts its layout, builder defects not worth copying. |
| J16 | Massage head, foot and wave levels, and off | P1-18, P1-19 | IMPLEMENTED | `set_massage_intensity` resends all three levels; wave slider; `TestJensenMassage`. The #631 capture confirms `12 06 00 06 00 00`. |
| J17 | Light level and off on output `02` | P1-15, P1-16 | IMPLEMENTED | `set_light_level`, light level slider; `test_light_levels`. Off is the fixed 2.0.37 frame `13 02 00 00 00 32` (vector TV078; 2.0.29 sent `13 02 00 00 12 03`). |
| J18 | Pairing-screen identify blink, on JMC400 and Linak | P1-17, P3-25, P4-20 | EXCLUDED | Pairing/naming-screen affordance looped until that screen closes; HA has no equivalent step. Its frames are light frames (J17, K05). |
| J19 | Fan level and off | P1-20, P1-21 | IMPLEMENTED | `set_fan_level`, `fan_level` number entity; `test_fan_levels`, `TestJensenEntities`. |
| J20 | Timer bytes (`H M`) in massage, light and fan frames | P1-15, P1-18, P1-20, C32 | EXCLUDED | No coherent encoding: Android parses hexadecimal digits as decimal (no timer becomes `12 03`, 10 minutes `00 00`), and the iOS branch is dead in this artifact. The integration sends `00 00`, which the #631 iOS capture shows running massage; no timer is offered. |
| J21 | Voice and gyro (tilt) control | C29 | EXCLUDED | Alternative triggers of the same store actions with no new bytes; JMC400 has no voice control. |
| J22 | Comfort-mode favourite (box type 2) | P1-14 | EXCLUDED | A 48-step app-scripted choreography of frames already implemented (J12, J14, J16, J17). HA scripts can reproduce it. Its constant go-to targets are unverified for box type 2, so HA does not ship them. |
| J23 | Box type names (TWINDRIVE, DYNAMIQUE, FIRMNESS, LINONENTRY, LINONPI) | P1 model mappings | EXCLUDED | UI labels. The behavior they select (device memory on box 4, comfort mode on box 2) is J13 and J22. |
| J24 | Idle, sequence-end and background disconnects | C08, C35, P1-26, P2-12, P3-27, P4-23 | ALREADY_IMPLEMENTED | HA's idle disconnect and disconnect-after-command settings in `coordinator.py`. The app's background disconnect without STOP, with timers left running and resent after reconnect, is not copied: HA always sends STOP when a movement is interrupted (`test_cancel_sends_stop_and_propagates`, `test_task_cancellation_sends_stop`). |
| J25 | Motion pressed during a flat: no STOP (P4: `FF 00`), movement 300 ms later, nothing on an early release; 20 s repeat cap; error-retry accumulation | C38, P1-25, P2-11, P3-26, P4-22 | EXCLUDED | Safety: app scheduling. HA serializes commands, ends every interrupted or finished movement with STOP before the next command runs, and never overlaps repeats. |
| J26 | Commands fanned out to every controlled bed of the same type and box | C28 | ALREADY_IMPLEMENTED | Paired entries (`paired_coordinator.py`); `tests/test_paired_setup.py::test_paired_entry_loads_with_both_sides`. |
| J27 | Type selection, variant inventory and command-service factories | C05, C06, C21 | ALREADY_IMPLEMENTED | V01–V03 map to `jensen`, V05–V08 advertise the Linak control or position service and map to `linak` (`detection.py`, Linak UUID detection tests). V04 is L01. |
| J28 | Unused JMC400 opcodes, `N/A` type, UI gating and store wiring | C18, C31, C36, C37 | EXCLUDED | Dead or UI-only: defined but never sent, or no BLE I/O. |
| J29 | Position monitoring after autonomous moves (#628) | Integration requirement | IMPLEMENTED | `_monitor_movement` follows pushed reports: no mid-move queries, a final measured read, and STOP on cancel or when motion is still reported after 90 s. `TestJensenMovementMonitoring`. |

## LinOn (P2)

| ID | Discovery | Sources | Disposition | Implementation or exact exclusion reason |
|---|---|---|---|---|
| L01 | LinOn selection: name `/Adjustable Bed\|Jensen Bed/i` wins over every other rule | C02, C03 | IMPLEMENTED | Bluetooth setup stores the `jensen_linon` variant of `svane` for new entries with those names (`detection.is_jensen_linon_name`); `auto` stays the Svane app profile so existing entries are unchanged, and the options flow can select either. "Jensen Bed" names are discovered as `svane`; a bare "Adjustable Bed" is too generic and relies on the head service UUID. `test_bluetooth_setup_stores_the_app_profile`, `test_factory_uses_the_stored_profile`, `test_detect_jensen_linon_by_name`. |
| L02 | One characteristic per function under the head, foot and light services, write with response | C09, C15 | IMPLEMENTED | `beds/jensen_linon.py` reuses the LinonPI per-service writes (`_write_to_service_char`, with response). |
| L03 | Held single-motor motion: `01` to the up or down characteristic every 800 ms | P2-01…P2-04 | IMPLEMENTED | `_move_motor`/`_hold_sequence`, one write per 800 ms of the configured hold duration, each held for a full interval before STOP; `test_single_motor_hold_then_stop`. |
| L04 | Combined motion: head then foot `01`, alternating every 800 ms | P2-05 | IMPLEMENTED | `move_simultaneously`; `test_combined_motion_alternates_head_and_foot`. |
| L05 | STOP: `FF` to the head, then the foot, up characteristic | P2-06 | IMPLEMENTED | `_send_stop` after every movement and for every stop control, with a fresh cancel event; `test_stop_all`, `test_cancel_still_sends_stop`. The two writes follow each other directly rather than 800 ms apart, so the foot stops sooner. |
| L06 | STOP sequence repeating until the 20 s cap | P2-06 (repeat) | EXCLUDED | App defect: the release payload is a sequence, so it never matches the single stop command and keeps cycling. HA sends it once. |
| L07 | Flat: `00` to the head, then the foot, position characteristic | P2-07 | IMPLEMENTED | `preset_flat`; `test_flat`. Sent back to back; the app's 800 ms step and the disconnect after the sequence are app scheduling. The motors then move on their own, so an interrupted flat sends STOP (`test_interrupted_flat_sends_stop`). |
| L08 | Under-bed light on/off `[on, seconds, 00]` | P2-08 | IMPLEMENTED | `lights_on`, `lights_off`, `lights_toggle` send `01 00 00`/`00 00 00`; state tracked as last sent; `test_light_frames_and_state`. |
| L09 | Light timer seconds byte | P2-08 (dynamic field) | EXCLUDED | The byte is the timer in seconds truncated to 8 bits by the bridge, so most timers wrap; the countdown itself runs in the app. No timer is offered (as J20). |
| L10 | Light intensity slider | P2-09, C39 | EXCLUDED | No bytes reach the bed: a non-zero value crashes the app in the bridge, and zero routes to off (L08). `supports_light_level_control` is false. |
| L11 | Favourite recall | P2-10 | EXCLUDED | Writes nothing: the first step's data is never populated, so the sequence stalls before any write. Memory controls are not offered. |
| L12 | LinOn notifications and their base64 position parser | C13 | EXCLUDED | Dead: the subscription targets an undefined service and is rejected, so no position feedback exists in this profile. |
| L13 | Night-stand light, foot memory, device information, battery and other LinOn characteristics | C23 | EXCLUDED | Defined but never used by a reachable path. |

## Linak (P3, P4)

| ID | Discovery | Sources | Disposition | Implementation or exact exclusion reason |
|---|---|---|---|---|
| K01 | Exact/Exact 2: all up/down, STOP, zero position and memory 1–3 recall/store | P3-01…P3-20, C16 | ALREADY_IMPLEMENTED | `beds/linak.py` `LinakCommands` (all-up/down, `FF 00`, memory `0E`/`0F`/`0C`/`44`, store `39`/`3A`/`45`); `tests/test_linak.py` `TestLinakMovement`, `TestLinakPresets`. The app's slot numbering (its M1 is Linak memory 2, its zero position memory 1) is a UI label over the same frames. |
| K02 | Twin Drive/Generic: per-section and combined motion, STOP and memory 1–3 | P4-01…P4-09, P4-11…P4-16 | ALREADY_IMPLEMENTED | `LinakCommands` sections `08`–`0B`, `34`–`37`, `FF 00`, memory frames; `tests/test_linak_protocol.py::test_configuration_and_all_40_two_section_commands`, `TestLinakPresets`. |
| K03 | Twin Drive/Generic flat: `00 00` held, or latched by a tap and auto-stopped with `FF 00` after 15 s; recall held up to 20 s | P4-10 | EXCLUDED | Linak product boundary: `preset_flat` already holds `00 00` and releases it, with a bound set from the Linak apps. Aligning durations belongs to the Linak work unit in the #436 queue; recorded there as a candidate. |
| K04 | Linak position subscription and reports | C12 | ALREADY_IMPLEMENTED | Linak position characteristics in `const.py`; `TestLinakPositionData`. |
| K05 | Light on/off (`92 00`/`93 00`) | P3-21, P3-22, P4-17, P4-18 (`93 00`) | ALREADY_IMPLEMENTED | `LinakCommands.LIGHTS_ON`/`LIGHTS_OFF`; `TestLinakLights.test_discrete_lights_match_hardware_verified_sequence`. |
| K06 | Generic Bed and `/Bed/i` names turn the light off with the DC_1 toggle `94 00` | P4-18 (`94 00`) | EXCLUDED | Linak product boundary, as K03: `LIGHTS_TOGGLE` exists, and when to prefer it is for the Linak work unit to reconcile against the Linak apps. |
| K07 | DC output dim up/down (`9E 00`/`9F 00`) | P3-23, P3-24, P4-19 | EXCLUDED | Linak product boundary, as K03. |
| K08 | Twin Drive synced drive: each bed's frame rewritten from the position difference to the other bed | P4-21, C17 | EXCLUDED | Linak product boundary, as K03: two Linak beds run as a paired entry (J26); synchronizing their positions is a paired-Linak feature for the Linak work unit. |
| K09 | Exact 2 / Twin Drive chosen by the user for Generic Bed devices | C04 | ALREADY_IMPLEMENTED | Linak variants in `LINAK_VARIANTS` and the controller's layout detection. |
| K10 | Generic `/Bed/i` name rule that requires advertised services | C02 | EXCLUDED | Too broad for automatic discovery; real Linak controllers are detected by their service UUIDs. |
| K11 | Unused Linak command tables and UUIDs | C19, C24 | EXCLUDED | Defined but never referenced by a builder or read. |

## Out of scope

| ID | Discovery | Sources | Disposition | Reason |
|---|---|---|---|---|
| X01 | Native BLE bridge, unused bridge calls, native libraries, network, Bluetooth Classic | C25, C26, C27, C33, C34 | EXCLUDED | Third-party transport or unrelated to bed control. |

## Totals

54 behaviors are dispositioned: 22 IMPLEMENTED, 9 ALREADY_IMPLEMENTED and
23 EXCLUDED. J29 is an integration requirement from #628, not an artifact
discovery, and is counted with the IMPLEMENTED entries.

## Evidence identity

2.0.37 (106), Google Play split set acquired 2026-09-29, after the frozen
corpus cutoff (basename manifest):

```text
a1c07e6a38459217f8723b90fe849edaacadcd5fe6514f140e18ef70261e7f72
```

Accepted `REPORT.SHA256` file digest:

```text
56b03a29ff5f5822b455506ee328a14346a49c65fdfc0a9cd87ba588b5052712
```

The independent audit passed all 17 completion gates in its second round
(four findings, all resolved).

2.0.29 (98), frozen corpus artifact:

```text
004688d4afca009a79b64b2d036fdc99d3e514156f450e69b37d3d05fb836eb9
```

Accepted `REPORT.SHA256` file digest:

```text
4fdcca2d26176c40b32f6487f94127a49be0f465a98d3f68758ada8503cb274b
```

Raw APKs, decompilation and reports remain machine-local.

Useful user captures after release: JMC400 lights, fan and box-type-4 device
memory; position reports during flat and memory moves; position anchors from a
second JMC400; and any LinOn bed ("Jensen Bed" or "Adjustable Bed") with its
movement, flat and light.
