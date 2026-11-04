# Sealy MotionFlex implementation discovery ledger

This is the post-freeze comparison for the MotionFlex route of the
[Solace name routes](ff_frame.md#solace-name-routes). Evidence identity is in
[the codec guide](ff_frame.md#analysis-provenance).

## Discovery decisions

Every behavior reachable in the frozen MotionFlex report has one disposition
below. Grouped rows cover commands or notifications that share one reachable
surface and implementation path.

| Reachable discovery | Disposition | Integration reference |
|---|---|---|
| Accepted local-name prefix discovery, including `My QMS2`, and conservative profile routing | IMPLEMENTED | `manifest.json`, `detection.py`, and `resolve_solace_profile()` |
| FFE1 connection, notification/CCCD setup, writes, clean disconnect, and the absence of authentication or bonding | ALREADY_IMPLEMENTED | Coordinator BLE lifecycle plus `SolaceController` transport tests |
| Fixed CRC frames and additive-checksum variable frames | IMPLEMENTED | `codec/ff_frame.py`, `SolaceCommands` and `tests/test_ff_frame_vectors.py` |
| Back/legs movement with STOP cleanup | ALREADY_IMPLEMENTED | Solace movement methods and cancellation tests |
| Flat, relaxing-bedtime, memory, TV, zero-G, and anti-snore actions | IMPLEMENTED | Preset buttons/methods and Solace command tests |
| Five startup preset queries and selected-state notification parsing | ALREADY_IMPLEMENTED | `_async_query_preset_states()` and notification tests |
| Music start/stop, track selection, previews, volume query/set, and volume reply | IMPLEMENTED | Music buttons, `solace_audio`, audio-volume sensor, and service-to-entity test |
| Startup local-time clock synchronization | IMPLEMENTED | `build_solace_clock_command()` and startup-query tests |
| Alarm programming and alarm/audio-availability replies | IMPLEMENTED | `solace_set_alarm`, `build_solace_alarm_command()`, and parser tests |
| Brightness writes 0-10, brightness query/reply, and three timer toggles | IMPLEMENTED | Solace light, number, and select entities plus command, parser, and entity-state tests |
| Model-setting identifiers whose predicate has no visible effect | EXCLUDED | Reachable app settings are behaviorally inert, so there is no state or command to reproduce |
| Sync notifications with empty EventBus consumers | EXCLUDED | The app records a switch, but no reachable behavior consumes or changes it |
| Arbitrarily prefixed or broad case-sensitive `QMS` substring discovery | EXCLUDED | Home Assistant rejects leading-wildcard discovery hints as too broad; accepted prefixes remain reachable, while auto-configuring unknown FFE1 families would be unsafe |
| Initial FFE1 write without an initialized application value | EXCLUDED | The artifact does not assign command bytes before this write, so reproducing an unknown cached characteristic value would be nondeterministic and unsafe |
| Reads of every GATT descriptor and their passive callbacks | EXCLUDED | The app has no consumer for the returned values; Home Assistant's Bluetooth stack owns the CCCD operation needed for notifications |

Ledger totals: **IMPLEMENTED 7, ALREADY_IMPLEMENTED 3, EXCLUDED 5**.

Dead or unreachable artifact code is outside the reachable ledger: the hidden
massage and fault surfaces, characteristic reads, RSSI reads, reliable writes,
and the unused advertisement parser are not exposed by the MotionFlex
application.

## Withheld from the name-selected routes

- Yoga selector `4E` (historical frame `FF FF FF FF 05 00 00 00 4E 57 34`): it
  belongs to an app whose audit is still pending.
- Legacy all-flat selector `2A` outside the exact S4-Y compatibility route.
- Five generic numbered memory slots: the historical "memory 3-5" frames are the
  TV, Zero-G and Anti-Snore program branches.
- Broad S3/S4/S5/S6 and leading-wildcard `QMS` detection.
- Woosa's absolute massage selectors `4F`-`56`, light-off selector `4B` and its
  STOP plus 200 ms preset preamble: Woosa Sleep only.
