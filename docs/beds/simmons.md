# SIMMONS app profile

Select **SIMMONS app** manually when the bed uses the Android app `com.okin.simmons` (shown as SIMMONS). The profile follows the accepted APK Protocol Audit of version 1.12.9 (code 99), a 20-APK XAPK with artifact-set SHA-256 `b5ef1222e24ad9bdf5b2d513fbc7a9aece2b63269c0e8d9632e2596837ffc70f`. Behavior is static-verified only: **hardware unverified**. The comparison ledger is [row049](../apk-analysis/dispositions/row049-simmons.md).

OKIN and SmartBed Bluetooth names and the Nordic UART or FFE5 services are shared with other apps, so they never select this profile. Existing entries keep their bed type until you change it.

## Configuration

The protocol variant carries two independent choices from the app:

| Variant | Bed type | Packet format |
|---|---|---|
| `auto` (default) | Regular | From the Bluetooth name |
| `simmons_okin` / `simmons_smartbed` | Regular | Fixed |
| `simmons_inclined` | Inclined | From the Bluetooth name |
| `simmons_inclined_okin` / `simmons_inclined_smartbed` | Inclined | Fixed |

The name rule is the app's, which reads Android's device (GAP) name; HA sees the advertised name or BlueZ alias instead. HA keeps the raw Bluetooth name from setup and from later real (non-address) observations, never the entry's display name. An address-like live name (BlueZ uses the address when a bed sends no name) falls back to that stored raw name. The lowercased name is checked for a `smartbed` prefix, then an `okin` prefix, with no trimming. Any other name, including a missing one, uses the SmartBed format, as the app does for a reconnect to a saved bed whose name matches neither prefix. Use a fixed variant if Home Assistant sees a different name than the phone. In a two-address pair the variant belongs to each physical bed, so the combined options form refuses variant changes: unpair, set each bed, then combine them again.

The app offers the inclined bed type only in its Japanese language setting; the profile offers it regardless of language. Motor count is fixed at two (back, legs). Position feedback, massage and pairing do not exist in the app.

## Transport

| Role | Service | Characteristic |
|---|---|---|
| Write | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| Write | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` |
| Notify | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` |

Services are matched in discovery order and the last match of each role wins, independent of the packet format. A connection without both a write and a notify role fails, as the app disconnects. OKIN-format frames are written with response (Android's default write type); SmartBed-format frames without response. Notifications stay subscribed with angle sensing off.

## Frames

The 32-bit control mask is shared by both formats.

- OKIN: `E6 FE 16` + mask little-endian + `00` + checksum, where checksum = (255 − sum of the preceding bytes) & 255.
- SmartBed: `05 02` + mask big-endian + `00`, no checksum.

| Control | Mask | OKIN frame | SmartBed frame |
|---|---|---|---|
| Back up | `0x1` | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| Back down | `0x2` | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| Legs up | `0x4` | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| Legs down | `0x8` | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| Flat | `0x08000000` | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| Zero gravity (regular) | `0x1000` | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| TV/PC (regular) | `0x4000` | `E6 FE 16 00 40 00 00 00 C5` | `05 02 00 00 40 00 00` |
| Anti-snore (regular) | `0x8000` | `E6 FE 16 00 80 00 00 00 85` | `05 02 00 00 80 00 00` |
| Custom Mode memory | `0x10000` | `E6 FE 16 00 00 01 00 00 04` | `05 02 00 01 00 00 00` |
| Under-bed light | `0x20000` | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |
| STOP | `0` | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |
| Inclined left / middle / right | `0x10` / `0x1000` / `0x20` | SmartBed frame, written with response | `05 02 00 00 00 10 00` / `05 02 00 00 10 00 00` / `05 02 00 00 00 20 00` |

The inclined controls always send the SmartBed frame, even with the OKIN format selected; the profile reproduces this. Their physical roles are unknown, so they are exposed as **Inclined Left/Middle/Right** buttons. The middle mask equals zero gravity.

## Timing and release

Every control repeats every 300 ms while held. On release the app schedules two STOP frames, at +100 ms and +400 ms. HA sends both from one release origin with fresh cancellation events, even if the movement was cancelled or a write failed. Every release is global, so all axes share one command resource.

Covers move for the configured pulse count at the fixed 300 ms interval. Preset, Custom Mode recall, light and inclined buttons are app taps: the button-down frame once, with no 300 ms refresh because the press is already released, then the two release STOPs at +100 and +400 ms. The app enforces no minimum preset hold. **Save Custom Mode** holds the recall frame for 5.5 s: the app's help says to hold M for 5 seconds and its "Custom Mode has been set" notice appears at 5.5 s. There is no separate save frame, and whether the bed stores the position is unverified. Use `simmons_hold_control` for a longer hold. Whether a tap completes a preset on the bed, or the bed needs a hold, is unverified.

The app's own races (a new press replacing a pending STOP, repeat revival, no STOP on page dispose or disconnect) are not reproduced: HA serializes commands and always finishes the release.

## Alarms and clock

During connection setup, after notifications start and before any command runs, HA writes the local clock and repeats the alarm page's queries at 0, 300 and 600 ms, so even a quick-disconnect session gets them. If that clock write fails, `simmons_set_alarm` writes the clock first, because the alarm fires on the bed's clock. **Sync Clock** and **Refresh Alarms** buttons repeat these.

| | OKIN | SmartBed |
|---|---|---|
| Clock | `E7 80 01`, year−1900, month−1, day, hour, minute, second, checksum | `07 04`, year−1900, month−1, day, hour, minute, second, ISO weekday (Mon 1…Sun 7) |
| Query | `E1 80 03 9B` (both alarms) | `00 C0`, then `00 D0` 300 ms later |
| Program | `ED 80 03` + slot 1 and slot 2 records (hour, minute, weekday, type) + `00 00 00 00` + checksum | `07 05` (slot 1) or `07 06` (slot 2), weekday, type, hour, minute, `00 01 01` |
| Disable | Same frame; selected weekday and type 0, hours/minutes kept | `07 05` or `07 06` + seven zero bytes |
| Reply | `ED 80 03`: records at offsets 3 and 7; enabled unless weekday is 0 or 128 | `A5 0C 0E` / `A5 0D 0E`: weekday 4, type 5, hour 6, minute 7, open 9 |

These writes are not press/hold commands: a movement STOP never cancels them, and local records change only after the write is sent. Each integer is masked to one byte. Alarm modes map to wire types Custom Mode/Flat/Anti-snore = 17/28/16 (OKIN) or 5/9/4 (SmartBed). Anti-snore is offered only on a regular bed.

The weekday is a bitmask with Sunday as bit 0 and bit 7 marking a repeat. A repeat mask passes through. A one-off alarm (mask 128) is sent as the bit of the next occurrence: today if the time, truncated to whole milliseconds, is not yet past, otherwise after an absolute 24 hours, so a DST change can shift the day.

OKIN programming rewrites both slots, so the other slot's stored record is re-sent unchanged (its weekday is sent as 0 when that alarm is disabled). The app stores the weekday mask from its editor and encodes only the slot being written, so an enabled one-off alarm in the other slot is re-sent as mask 128, which the app's own reply parser reads as disabled. The profile reproduces this; whether the bed then keeps or drops that one-off alarm is unverified. The written record is remembered as pending until an exactly matching reply arrives. After a write, HA queries again 300 ms later.

`simmons_set_alarm` follows the app's rules: Custom Mode needs `confirm_custom_mode` (the app warns that extreme custom angles can cause injury), and an enabled alarm cannot share its time or mode with the other enabled alarm. If this HA run has no alarm records yet, the bed is queried first and the write is refused if it does not answer within 2 s (an integration-side guard, not an app value).

Reply overlays match the app: an enabled OKIN record keeps the locally known weekday, and a disabled SmartBed record keeps the local hour, minute and weekday; a SmartBed record with open=1 and all fields zero counts as disabled. A 20-byte notification whose bytes 1–2 are `FE 16` is joined with the next one. Records too short for their header are ignored whole.

Differences from the app: alarm records belong to each physical bed rather than one global phone setting; they live in memory, so after an HA restart the first reply is taken as reported. Local records change only after a successful write. HA never enables an alarm with wire type 0, which the app can do by re-enabling a disabled slot.

**Alarm 1** and **Alarm 2** sensors show the time, with attributes for enabled, mode, wire type, weekday mask and whether a reply is awaited.

## Validation requests

For real users after a beta or release: whether each name prefix matches the bed's actual protocol, which GATT roles the bed exposes, whether a preset tap completes the motion or needs a hold, what the inclined controls move, whether the bed accepts SmartBed inclined frames in OKIN mode, how the light responds to a hold, how alarm replies report one-off alarms, and whether an enabled one-off alarm survives programming the other slot on an OKIN bed (it is re-sent as mask 128).
