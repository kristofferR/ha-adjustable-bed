# Jensen Adjustable Sleep implementation discovery ledger

This is the post-freeze comparison for `air.no.jensen.adjustablesleep` 2.0.29
(98). The protocol summary is in [the Jensen guide](jensen.md). The accepted
clean-room report contains 3 protocols, 123 command rows, 49 candidate paths,
6 variants and 318 reproducible vectors:

- **P1** ("Linon": names "Adjustable Bed"/"Jensen Bed") never writes a frame in
  this version.
- **P2** is the JMC400 protocol handled by the `jensen` bed type.
- **P3** drives Linak-based Jensen beds, handled by the `linak` bed type.

Row IDs below number each protocol's command rows in report order (`P2-13` is
P2's 13th row); `Cnn` are the report's candidate IDs. Every row and candidate
has exactly one disposition. `IMPLEMENTED` means added or corrected in this
change, `ALREADY_IMPLEMENTED` means existing code verified against the report,
and `EXCLUDED` gives the evidence-based reason. Physical validation is deferred
to users after release; it is not an exclusion reason.

Implementation references are relative to `custom_components/adjustable_bed/`.
Jensen tests are in `tests/test_jensen.py`.

## Discovery decisions

| ID | Discovery | Sources | Disposition | Implementation or exact exclusion reason |
|---|---|---|---|---|
| J01 | Name rule `/JMC400/i` anywhere in the name, no scan filter | C01, C02, C03, C25 | IMPLEMENTED | `detection.py` also accepts `JENSEN_NAME_FRAGMENT`; `tests/test_detection.py::test_detect_jensen_by_app_name_fragment`. Service-UUID and `jmc` prefix detection remain. |
| J02 | Connect, service discovery, notification subscription and CCCD | C04, C05, C06, C07, C10 | ALREADY_IMPLEMENTED | `coordinator.py` connection; `beds/jensen.py:start_notify`; `TestJensenNotificationStartup`. |
| J03 | Write without response on `0x1111` | C12 | IMPLEMENTED | `start_notify` selects no-response unless the characteristic only supports writes; `TestJensenWriteMode`. |
| J04 | 5-byte PIN frame at session start | C13, P2-25 | IMPLEMENTED | `JensenCommands.pin_unlock`; `TestJensenFrames`, `TestJensenController`. The coordinator's per-command PIN refresh is kept (`TestJensenCoordinatorAuthRefresh`). |
| J05 | 5-byte config request and config parser (decimal digits read as hex, box type) | C14, C32, P2-27 | IMPLEMENTED | `query_config`, `_decode_config_field`; `TestJensenConfig`, including the #631 report `0A 05 03 08 01 75`. |
| J06 | PIN status reply; re-entry when locked | C15 (`unLock`), C32 | IMPLEMENTED | `_handle_notification` warns that the configured PIN was rejected; the PIN is corrected in the entry options. `test_rejected_pin_is_logged`. |
| J07 | Set a new bed PIN | C15 (`storePinCode`), P2-26 | EXCLUDED | Unreachable: the PIN-change screen is gated by `config.hasPinCode`, which module 1300 always sets false. |
| J08 | Software-revision reply | C32 | EXCLUDED | Dead: the app never requests it and discards the comparison. |
| J09 | Position reports (`0x10`) | C32 | IMPLEMENTED | u16 little-endian decode with #631 hardware anchors (the app treats the bytes as opaque); `TestJensenPositionParsing`. |
| J10 | Single-section motion and STOP, repeated every 300 ms while held, STOP once on release | P2-01…P2-04, P2-09 | IMPLEMENTED | `_move_with_stop`; default pulse 4 × 300 ms in `const.py`; `TestJensenHeldMovement`. |
| J11 | Combined back/legs motion | P2-05…P2-08 | IMPLEMENTED | `move_simultaneously` behind the existing `linak_move_simultaneously` action (text made protocol-neutral); `test_simultaneous_movement`. |
| J12 | Flat, sent once, then the bed moves autonomously | P2-10 | IMPLEMENTED | `preset_flat` follows reports to completion (`_monitor_movement`); `TestJensenMovementMonitoring`. Keeps the integration's short burst and `10 FF` warm-up for the #217 reconnect behavior. |
| J13 | Device memory save/recall on box type 4 | P2-11, P2-12 | IMPLEMENTED | `uses_device_memory`, `program_memory`, `preset_memory`; `test_device_memory_slot`. Other boxes no longer send these frames. |
| J14 | App-stored favourites on other boxes: capture the reported position, recall with go-to | P2-13 (position frame), C28 | IMPLEMENTED | Four slots persisted in an HA `Store`, recalled with the echoed `10 04` bytes and monitored; `TestJensenMemory`, `TestJensenDirectPosition`. |
| J15 | Favourite recall also replaying differing massage, fan and light frames | P2-13 (accessory frames) | EXCLUDED | App-side scene composition. Each frame is available on its own (J16, J17, J20); HA scenes compose them. The replayed fan frame also lacks its `0x50` trailer, a builder defect not worth copying. |
| J16 | Massage head, foot and wave levels | P2-15 | IMPLEMENTED | `set_massage_intensity` resends all three levels; wave slider added; `TestJensenMassage`. The #631 capture confirms `12 06 00 06 00 00`. |
| J17 | Light level and off on output `02` | P2-16, P2-17 | IMPLEMENTED | `set_light_level`, light level slider; `test_light_levels`. Replaces the old `13 00 FF…` frames, which the app never sends. |
| J18 | Light brighter/dimmer | P2-18 | EXCLUDED | Sends nothing in the app. |
| J19 | Pairing-screen identify blink | P2-19 | EXCLUDED | Pairing/naming-screen affordance looped until that screen closes; HA has no equivalent step. Its frames are light frames (J17). |
| J20 | Fan level and off | P2-20, P2-21 | IMPLEMENTED | `set_fan_level`, new `fan_level` number entity; `test_fan_levels`, `TestJensenEntities`. |
| J21 | Timer bytes (`H M`) in massage, light and fan frames | C31, P2-15…P2-17, P2-20…P2-22 | EXCLUDED | No coherent encoding: Android parses hexadecimal digits as decimal (30 min becomes `00 01`, some values NaN) and iOS sends `00 00`. The integration sends `00 00`, which the #631 capture shows running massage; no timer is offered. |
| J22 | Fan timer resume sending a NaN intensity | P2-22 | EXCLUDED | App defect with no defined device meaning. |
| J23 | Voice control on JMC400 | C38, C44, P2-23, P2-28, P2-31 | EXCLUDED | Unreachable: `hasVoiceControl` is false for JMC400; fan phrases are also missing from the command map. |
| J24 | Gyro (tilt) control, including the fan cross-wiring and misspelled massage steps | C37, C42, C43, P2-24, P2-29, P2-30 | EXCLUDED | Phone-accelerometer input method. It emits only frames covered above, and its cross-wired or misspelled branches are app defects. |
| J25 | Comfort-mode favourite (box type 2) | P2-14 | EXCLUDED | A ~5-minute app-scripted choreography of frames already implemented (J12, J14, J16, J17). HA scripts can reproduce it. Its constant go-to targets are unverified for box type 2, so HA does not ship them. |
| J26 | Idle and lifecycle disconnects, user disconnect | C16, C17, C18 | ALREADY_IMPLEMENTED | HA's idle disconnect and disconnect-after-command settings in `coordinator.py`. The app's lifecycle disconnect without STOP (C17) is not copied: HA always sends STOP when a movement is interrupted (`test_cancel_sends_stop_and_propagates`, `test_task_cancellation_sends_stop`). |
| J27 | Uncancelled repeat chains, STOP revival window, 20 s cap without STOP, error-retry accumulation, identify/motion interaction, shared multi-bed flags | C46, C48, C49 | EXCLUDED | Safety: app scheduling defects. HA serializes commands, never overlaps repeats, and ends every movement with STOP. |
| J28 | Commands fanned out to every controlled bed with the same type and box | App multi-bed control | ALREADY_IMPLEMENTED | Paired entries (`paired_coordinator.py`); `tests/test_paired_setup.py::test_paired_entry_loads_with_both_sides`. |
| J29 | Type selection, variant inventory and command-service factories | C23, C24, C26 | ALREADY_IMPLEMENTED | V2 maps to `jensen`; V3–V6 advertise the Linak control or position service and map to `linak` (`detection.py`, Linak UUID detection tests). The V4/V5 choice after naming is the Linak model/layout selection. |
| J30 | P1 "Linon" protocol | C09, C27, C34, P1-01…P1-07 | EXCLUDED | Dead: setup throws on an undeclared global, so no P1 frame is ever written. |
| J31 | P3 motion, combined motion, STOP, flatten and memory save/recall | C11, C29, P3-01…P3-36 | ALREADY_IMPLEMENTED | `beds/linak.py` `LinakCommands` (all-up/down, per-section, `34`–`37`, `FF 00`, memory `0E`/`0F`/`0C`/`44`, store `39`/`3A`/`45`); `tests/test_linak.py` `TestLinakMovement`, `TestLinakPresets`, `tests/test_linak_protocol.py::test_configuration_and_all_40_two_section_commands`. The app's slot numbering (its M1 is Linak memory 2) and its use of memory 1 as flat are UI labels over the same frames. |
| J32 | P3 light on/off | P3-37, P3-38, P3-42, P3-43, P3-47, P3-48 | ALREADY_IMPLEMENTED | `LinakCommands.LIGHTS_ON`/`LIGHTS_OFF`; `TestLinakLights.test_discrete_lights_match_hardware_verified_sequence`. |
| J33 | P3 DC output dim up/down (`9E 00`/`9F 00`) | P3-39, P3-40, P3-44, P3-45, P3-49, P3-50 | EXCLUDED | Linak product boundary: Linak protocol changes belong to the Linak work unit in the #436 queue, which must reconcile them against the Linak apps. Recorded there as a candidate. |
| J34 | P3 identify blink | P3-41, P3-46, P3-51 | EXCLUDED | Pairing-screen affordance, as J19. |
| J35 | P3 voice (including cross-wired Exact phrases) and gyro | C45, P3-52…P3-85 | EXCLUDED | Voice and phone-tilt input methods emitting only frames covered by J31/J32/J33; the cross-wired branches are app defects. |
| J36 | P3 position subscription and reports (u16 LE on outputs 7/8) | C08, C33 | ALREADY_IMPLEMENTED | Linak position characteristics in `const.py`; `TestLinakPositionData`. |
| J37 | P3 twin-drive position mirroring | C30 | ALREADY_IMPLEMENTED | Two beds are driven through paired entries (J28); HA does not mirror one bed's measured positions onto another. |
| J38 | P3 STOP lost behind a pending with-response write | C47 | EXCLUDED | Safety: app defect. HA's Linak STOP is written in its own serialized operation (`test_linak_uses_explicit_stop_release`). |
| J39 | P3 generic `/Bed/i` name rule that requires advertised services | C02 | EXCLUDED | Too broad for automatic discovery; real Linak controllers are detected by their service UUIDs. |
| J40 | Permissions, unused bridge calls, legacy scanner, Bluetooth Classic, DFU, unused constants, native libraries, network | C19, C20, C21, C22, C35, C36, C39, C40, C41 | EXCLUDED | Unrelated to bed control, dead or third-party code (C39's reachable siblings are J20/J22). |
| J41 | Position monitoring after autonomous moves (#628) | Integration requirement | IMPLEMENTED | `_monitor_movement` follows pushed reports: no mid-move queries, a bounded wait, a final measured read, and STOP on cancel. `TestJensenMovementMonitoring`. |

## Totals

40 behaviors are dispositioned: 14 IMPLEMENTED, 8 ALREADY_IMPLEMENTED and 18
EXCLUDED. J41 is an integration requirement from #628, not an artifact
discovery, and is not counted.

## Evidence identity

Frozen corpus artifact (Google Play split set, basename manifest):

```text
004688d4afca009a79b64b2d036fdc99d3e514156f450e69b37d3d05fb836eb9
```

Accepted `REPORT.SHA256` file digest:

```text
4fdcca2d26176c40b32f6487f94127a49be0f465a98d3f68758ada8503cb274b
```

The independent audit passed all 17 completion gates after five rounds (eight
findings, all resolved). Raw APKs, decompilation and reports remain
machine-local. Google Play listed 2.0.37 on 2026-09-29; it is newer than the
corpus cutoff and was not analyzed.

Useful user captures after release: lights, fan and box-type-4 device memory;
position reports during flat and memory moves; position anchors from a second
JMC400.
