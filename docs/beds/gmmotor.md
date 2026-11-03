# GM Control

**Status:** ❓ Needs testing (static app evidence; physical bed and firmware behavior unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Exact GM Control product codes, selected in setup. The [catalog ledger](../apk-analysis/dispositions/row102-gmmotor-catalog.csv) records every admitted and unsupported constructor.
- `V9RM`, `V9RM (standard)` and `V9RM (split head)` retain distinct catalogs. Select the configuration actually used by the app.
- `FWRM` and `WFRM` use the dedicated desk controller.
- MM and SXB sleep modules are separate Bluetooth devices and separate integration entries.
- Shared Bluetooth names or UUIDs do not establish that another app uses this catalog.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [GM Control](https://play.google.com/store/apps/details?id=com.desarketing.gmmotor) 4.6.6 (46600) | `com.desarketing.gmmotor` |

## Features

| Feature | Product controller | FWRM / WFRM desk | MM / SXB module |
|---------|--------------------|------------------|-----------------|
| Motor Control | Exact named app controls and holds | Up, down, reset | None |
| Position Feedback | Raw indexed reports; no inferred axis mapping | Raw height, unit, bounds and state | None |
| Memory Presets | Exact product controls, including state-dependent recall/program gestures | Three short recalls; long memory callback sends nothing | None |
| Massage | Exact product controls; bottom countdown where admitted | None | None |
| Lights | Product controls; RGB/timeout menu requires its capability reply | None | None |
| Alarms | Countdown or repeat table according to product; requires clock reply | None | None |
| Anti-snore Settings | HNRN, HQRN, HSRN, HURN, M7RN, MJRN | None | Incoming raw state only |
| Sleep Monitoring | BLE module name query where admitted | None | Live polling, part settings, day/month reports, clock, raw sensitivity query on SXB |
| Paired Beds | Separate addresses retain their own product and app side; one address requires that product's side choices | Separate physical devices | Separate physical devices |
| Firmware / Cloud / Bed Network | Outside integration boundary | Outside integration boundary | Outside integration boundary |

## Protocol Details

### Product and desk GATT roles

| Service UUID | Selected write UUID |
|--------------|---------------------|
| `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` |
| `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` |
| `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` |

The last accepted service in discovery order selects the mode. Selection then
uses the first matching characteristic with WRITE and the first global NOTIFY
characteristic. A declared notification UUID does not replace this property
selection. WRITE_NO_RESPONSE alone does not satisfy WRITE admission.

### Packet Format

Most framed product controls are `6E 01 SIDE OPCODE SUM8`. `SIDE` is 0 for Left,
1 for Right and 2 for Both, subject to the selected product's choices. `SUM8` is
the sum of preceding bytes modulo 256. Special controls have their own three-byte
prefix. Short overrides, long overrides and Nordic single-byte overrides remain
separate values in the shipped catalog.

The Nordic service sends the selected one-byte opcode. Other modes send their
framed packet. This does not make product catalogs interchangeable.

### Write Mode

The selected product characteristic uses without-response writes when it also
has WRITE_NO_RESPONSE; otherwise it uses with-response writes. A frame must fit
the negotiated ATT payload (`MTU - 3`, at most 512 bytes). Failed writes abort
without retry. Product and sleep sessions share one native-write mutex within HA.

## Detection / Setup

1. Choose **GM Control**, then the exact product code and its app side. A matching
   raw Bluetooth name supplies a suggestion; it cannot resolve a remote picker.
2. For an app remote picker or QR code, select its resulting concrete product.
   `QRRM` itself is not a final controller profile.
3. Choose **GM Control MM sleep module** or **GM Control SXB sleep module** for an
   independent module. Never select a sensor mode from the bed's transport UUID.

The app's name filter is a case-sensitive substring test, with uppercase product
selection and explicit aliases afterward. HA background matchers require a
literal prefix, so background advertisements use the corresponding prefix
patterns. Manual discovery and the callback retain the substring rule. Existing
receiver matches keep priority and offer the app as an additional explicit choice.

For a single Bluetooth address, **Pair sides** appears only for exact products
that admit Right. If the product has Left and Right without Both, HA serializes
the two admitted sides. Separate physical receivers retain independent products,
side settings and session state.

New product entries disable Disconnect After Command by default. Product UI
flags remain local to the physical address, exact product and app side when HA
replaces a BLE controller, including when quick handoff is explicitly enabled.
Changing product or restarting HA starts a fresh app view. Live capability
replies are still obtained separately for each connection.

## Commands

The named buttons come from the selected catalog. The card displays them as
utility controls, with continuous holds for sustain actions and separate buttons
for finite short/long callbacks. The `hold_control` action
accepts the button's `held_control` identifier and a bounded duration.

### Example: 6BRM product, framed Left

| App command | Exact bytes | Gesture |
|-------------|-------------|---------|
| Head Up | `6E 01 00 24 93` | Sustain |
| Head Down | `6E 01 00 25 94` | Sustain |
| Foot Up | `6E 01 00 26 95` | Sustain |
| Foot Down | `6E 01 00 27 96` | Sustain |
| Head and Foot Up | `6E 01 00 29 98` | Sustain |
| Head and Foot Down | `6E 01 00 2A 99` | Sustain |
| Release / Stop | `6E 01 00 6E DD` | Fresh, uncancelled cleanup |

These values describe 6BRM only. Other exact products can override opcodes,
gestures, visibility or the material captured by a callback. Raw button labels
do not prove physical motor axes. Long-only, short/long and state-dependent
memory actions remain distinct.

### Desk commands

| Command | Exact body before SUM8 | Behavior |
|---------|------------------------|----------|
| Up / Down | `6E 01 00 01` / `6E 01 00 02` | Sustain, then `6E 01 00 6E DD` |
| Reset | `6E 95 00 00` | Sustain, then release |
| Memory 1 / 2 / 3 | `6E 01 00 04` / `6E 01 00 08` / `6E 01 00 10` | Short recall, no release; long callback sends nothing |
| Height | `6E 88 HIGH LOW` | Height in cm × 10, split by decimal 100; inch input first × 2.54 |
| Unit | `6E 91 00 UNIT` | 0 cm, 1 inch |
| Query | `6E 94 00 00` | Single request |

Desk height is checked against reported bounds, or the source defaults
60–125 cm / 23.6–49.21 inches. The decimal height bytes are not a binary uint16.

### Specialized actions

Use `adjustable_bed.gmmotor`. Service preflight validates every selected product
and the operation fields. Before sending a light or alarm action, the executing
connection waits up to five seconds for its required capability reply, including
after an idle reconnect. A missing reply rejects the action without sending its
commands.

| Operation | Exact construction / field meaning |
|-----------|------------------------------------|
| `clock_sync` | `6E 0C 20 08 02 01 UNIX_BE32 ZONE_HOURS SUM8`, then `6E 0D 20 08 03 01 YEAR_MINUS_1970 MONTH DAY HOUR MINUTE SECOND SUM8` |
| `alarm` | `6E 05 MINUTES_LOW 00 SUM8`, then `6E 06 MINUTES_HIGH MODE SUM8` |
| `alarm_at` | Same countdown frames; HA local hour/minute, seconds removed, nonpositive difference plus exactly 86400 seconds |
| `alarm_cancel` | The two countdown frames with minutes/mode zero |
| `repeat_alarm` | `6E 0D 20 05 01 01 ID REPEAT HOUR MINUTE MODE STATUS SUM8` |
| `repeat_delete` | `6E 08 20 05 02 01 ID SUM8` |
| `repeat_query` | `6E 08 20 05 01 00 00 SUM8` |
| `light_color` | `6E 0C FF RED SUM8`, then `6E 0D GREEN BLUE SUM8`, concatenated in one write |
| `light_timeout` | `6E 0B SECONDS_HIGH SECONDS_LOW SUM8`; 0–900 seconds, zero encodes the unlimited `FFFF` sentinel |
| `light_off` | Product material opcode `75` hex, using the current app side / single-byte mode |
| `snore_enabled` | `6E 09 20 06 01 01 00 ENABLED SUM8` |
| `snore_query` | `6E 08 20 06 01 00 00 SUM8`, then `6E 09 20 06 05 00 00 00 SUM8` |
| `snore_count` / `snore_time` | `6E 0A 20 06 05 01 SELECTOR 00 VALUE SUM8`; selector 1 count (1–30), 2 time (5–30) |
| `massage_timer` | Source choices 0–3; D9RM opcodes `8B,5F,63,61`, D1RM `5E,5F,63,61` |
| `sleep_name` | `6E 08 20 06 03 00 00 SUM8`; only when the selected profile admits BLE sleep monitoring |
| `refresh` | CheckClock `6E 08 01 01 78`, then CheckLight `6E 0A 00 01 79` (framed modes); single-byte mode sends `01` for each |

`mode` is the exact action name listed in that product's alarm catalog. Alarm
mode overrides are independent of the same visible control's ordinary opcode.
Repeat-capable products open the repeat page; other alarm products use countdowns.
Both menus require the live clock capability reply. Light settings additionally
require the selected product's light flag and the live light capability reply.

The eight-color layout admits RGB values `(255,255,0)`, `(0,255,0)`, `(0,127,255)`,
`(0,0,255)`, `(139,0,255)`, `(255,255,255)`, `(255,0,0)`, `(255,165,0)`.

## Sleep Modules

Both modules accept service `2320567c-05cf-6eb4-c341-772851827e1b` or
`0000e0ff-3c17-d293-8e48-14fe2e4da212`. MM chooses WRITE_NO_RESPONSE and NOTIFY by
properties. SXB requires WRITE UUID `00000002-3c17-d293-8e48-14fe2e4da212` and
NOTIFY UUID `00000003-3c17-d293-8e48-14fe2e4da212`. WRITE wins a dual-property
characteristic, and candidate roles can carry across accepted services.

The 14-byte header is `00 ID TOTAL SEQUENCE (PAYLOAD_LEN+7) 00 00 11 03 43 55 44
LEN_LOW LEN_HIGH`, with native byte masking, followed by compact UTF-8 JSON.
There is no packet checksum. IDs run 1–254. Each queued frame waits 100 ms and
is written in sequential `MTU - 3` chunks without a delay between chunks.

| Action | MM JSON command | SXB JSON command |
|--------|-----------------|------------------|
| `sensor_time` | `s_time`, `{ts,tz}` | `s_time`, `{ts,utc}` (whole hours) |
| `sensor_query_part` | `s_part` with null value, the source query-name quirk | `q_part` with null value |
| `sensor_part` | `s_part`, value 1 or 2 | `s_part`, value 11, 12 or 13; skips a choice already reported |
| `sensor_live` | `q_realtime`, `{type:0,time:1}` every 2 seconds | Same command and cadence |
| `sensor_report` | `q_report`, `{part,type,y,m,d}` | Same initial request |
| Transfer follow-up | `q_report` retains report parameters and adds `allow:1` | `q_report`, `{allow:1}` |
| `sensor_sensitivity` | Unavailable | `q_sens`, null value; no inferred setter |
| `sensor_stop` | Local polling / receive cancellation, no wire STOP | Same |

`value` supplies the device part setting. `part` supplies report side 1/2;
`report_type` is 1 for day and 2 for month. `report_date` defaults to HA's local
date. `sensor_live` uses `enabled` to start or stop polling. Clock synchronization
uses HA's configured timezone. SXB time replies publish in source order and
follow up with `q_time`, then `q_part`. MM's compiled `q_time` selector consumes
an ID and sends no bytes.

An unexpected BLE drop schedules coordinator recovery. Active live monitoring
resumes once on the replacement controller. `sensor_stop`, intentional
disconnect, unload and canceled startup clear that intent, so a later explicit
connection does not restart polling. Timers, receive buffers and queued callbacks
belong to their original connection and are invalidated when it ends.
Cleanup after a recoverable startup failure keeps the monitoring request for
the coordinator's next connection attempt.

## Position Feedback / Notifications

- The GM Control state sensor exposes parsed event values, raw indexed motor and
  desk reports, alarm records and the selected catalog's local UI state.
- The sleep-module state sensor exposes raw stream DTOs, clock state, separate
  live-side values and decoded day/month reports. These have no validated
  physiological accuracy or medical interpretation.
- P1 `20`/`21` outer frames use their length byte and SUM8. `40` framing retains
  its BE16 length and CRC16/XMODEM even though firmware payloads are excluded.
- Legacy frames split at the next `6E` or the end of the current notification;
  no extra legacy checksum or invented fixed length is imposed.
- Sleep ordinary replies use the source low length byte; SXB report transfer
  strips 14 bytes from each notification. SXB dispatch retains whole-text
  substring precedence. Compressed reports use gzip and Latin1 code points,
  including the distinct old/new SXB day layouts and normal-mode cache keys.
- SXB live display uses five-second windows. A valid side reply marks its window
  as seen; an empty window clears that side's displayed values and online flag.
  MM does not inherit this display timer.

## Command Timing

- Product write cadence: at least 100 ms between writes.
- Sustain: first command at 100 ms, then 100 ms ticks; release uses a fresh cancel
  event. A release before the first tick sends nothing.
- Long gestures: 3 seconds; the selected callback determines whether any release
  exists. Ending a long action does not invent an extra release frame.
- Initial menu queries: 300 ms steps; partial P1 remainder expires after 500 ms.
- SDK write timeout: 15 seconds. Failed writes are not retried.

## Notes

HA safely drops malformed notifications that make the app's extractor loop
without progress. It also guarantees callback cleanup after required-field
failures, limits sleep report memory/decompression to 8 MiB and cancels stale
session follow-ups on stop/disconnect. These are explicit HA safety behaviors;
raw diagnostic observer faults are isolated so parsing can continue. The
[discovery ledger](../apk-analysis/dispositions/row102-gmmotor.md) records
their differences from the artifact.

### Analysis provenance

- GM Control 4.6.6 / code 46600, artifact-set SHA-256
  `0bdb27d045fb8d097cfc20e26e759ff238f8ac55eb317a3d3eccb814ccc8d11b`.
- [Complete row102 implementation/disposition ledger](../apk-analysis/dispositions/row102-gmmotor.md).
- Hardware, ATT delivery, firmware interpretation and physical effects remain
  unverified. Real-user reports after a beta or release can supply that evidence.
