# Casper Base app

Select **Casper Base app (select product)** during setup, then choose **PRO** or
**MAX**. Select the actual product rather than inferring it from a shared service
or the HLRM/JXRM strings. Existing generic Richmat entries are not migrated.

This profile follows the independently accepted `com.richmat.casperbase` 1.0.8
(version code 10800) artifact. Its BLE behavior is statically verified; physical
motor effects, firmware compatibility, ATT behavior and sensor accuracy remain
unverified. Real users can supply captures after a beta or release.

The product selector also offers the 37 other command-bearing records accepted by
this app's stored-product decoder. They are labelled **stored profile**. Their
presence does not establish availability in a fresh Casper Base installation or
support by another app. The two empty placeholders expose no bed controls.

## Controls

The selected product defines its motor covers and named action buttons, including
recall/save presets, massage zones, massage mode and timers, light icons, and any
fan/heating controls. All named buttons appear in the card's utility section.
PRO has back, legs and lumbar. MAX adds pillow control and uses different lumbar
and pillow opcodes. Raw motor-number responses are available as diagnostics;
they are not calibrated angle or position controls.

Motor movement starts on a 100 ms tick and repeats at that interval for the
configured pulse count, then sends the proven STOP. Massage/fan intensity taps
send once followed by STOP. Every release uses a fresh cancellation event. Save
buttons explicitly request programming; the app's three-second gesture does not
require holding a Home Assistant button. Actions with no programming opcode have
no save button, avoiding the app's unsafe zero-opcode long-press fallback.

One-address Left/Right/Both controls are available only for the stored L400SH and
L300SH layouts on a framed transport. Connect first so Home Assistant can verify
the transport before enabling sides. Two-address pairs retain each side's own
product selection. Music-page commands and the automatic anti-snore trigger use
default left, as the app does, separately from selected-side catalog actions.

## Configuration actions

Use `adjustable_bed.casper_base` with a `device_id` and `operation`. The service
validates every selected physical target before any command. A feature must be
present in the product and, where applicable, confirmed by the capability reply.
Fresh PRO/MAX do not gain music, sensor menus or repeating alarms from a reply.

| Operation | Fields and behavior |
|---|---|
| `light_rgb` | `rgb_color: [red, green, blue]`, ordinary light page |
| `light_seconds` | `value` in seconds; zero is the app's always-on sentinel |
| `light_off` | Ordinary light page off |
| `rgb_power`, `rgb_color` | Groove RGB page, `enabled` or `rgb_color` |
| `rgb_timer` | `value` in minutes: 5, 8, 10, 13, 15, 18, 21, 24, 27, 30, 120, 210, 300, 390, 480 |
| `rgb_mode` | `value`: multicolor red 2, cycling 3, flowing 5 |
| `rgb_groove` | `value`: spectrum 1, energy 2, rhythm 3, scroll 4 |
| `rgb_breathe` | Groove RGB breathe effect |
| `alarm`, `alarm_cancel` | Single alarm, `hour`, `minute`, `mode`; next local occurrence at minute precision |
| `repeat_alarm` | `slot`, `hour`, `minute`, `mode`, `enabled`, `days` (Monday 0 through Sunday 6); empty days means once |
| `repeat_delete`, `repeat_query` | Delete `slot`, or clear the local list and request it again |
| `time_sync` | Send Home Assistant's local calendar time for repeating alarms |
| `sleep_name` | Request the separately connected sensor's advertised name on a sensor-capable stored product |

Alarm modes are `tv`, `zero_g`, `anti_snore`, `lounge`, `memory_1`, `memory_2`,
`memory_3`; only modes in the selected product's alarm list are accepted.
The reserved byte of an existing repeating alarm is retained when editing it.
RGB receive timers use `high * 60 + low`, while sends use a 16-bit minute value.
This asymmetric behavior belongs to the app and is not silently normalized.

The **Casper Base state** diagnostic exposes the product, all parsed events,
alarm records and malformed-packet errors. Information from raw motor/desk events
keeps its original index and values, without guessing a physical axis or unit.
Alarm list responses suppress identical duplicates; updates replace the first
matching ID. Capability, RGB, music and acknowledgement consumers retain separate
state. The music Bluetooth boolean follows the latest ordinary/extended reply or
optimistic page switch, while raw events remain separate. USB soundtrack switching
retains its two-second debounce and 900 ms delay.

## Automatic anti-snore trigger

Microphone recording and phone audio processing are outside this integration.
For a detector supplied by another HA integration, call `snore_detector` with
`source: sensor.your_detector` and `enabled: true`. The sensor must report the
app's detector status convention: 1 increments the counter; 0 or unavailable
resets it; other integer values leave it unchanged. Every five qualifying samples
attempt the ordinary anti-snore preset and reset the counter. Polling begins after
three seconds and repeats every three seconds. This is separate from manual
anti-snore recall and save.

Disable with the same operation and `enabled: false`. Disconnect/unload cancels
the owned task, and replacing a session cannot revive an old timer. HA deliberately
does not reproduce the app's leaked timers, late post-disposal sends or overlapping
poll/write callbacks. No extra STOP packet is added to this preset trigger.

## Separate sleep sensors and remote finder

Add sensors as separate entries: **Casper Base sleep sensor (RM- / MM)** or
**Casper Base sleep sensor (HJ- / SXB)**. Discovery classification is case-sensitive
`RM-` or `HJ-` at the start of the name. Scanning substrings and classification are
separate rules. No bed product or cloud credential is inferred from the sensor.

| Sensor operation | Behavior |
|---|---|
| `sensor_time` | Synchronize timestamp and timezone/UTC offset |
| `sensor_info` | SXB: time request followed by the retained `s_init` information query |
| `sensor_query_part` | MM sends `s_part` with null; SXB sends `q_part` |
| `sensor_part` | `part`: MM 1 or 2; SXB left 11, right 12, both 13 |
| `sensor_live` | `enabled`: start/stop two-second live polling |
| `sensor_report` | `part`, `report_type` (daily 1/monthly 2), `year`, `month`, `day` (use 1 for monthly) |
| `sensor_stop` | Cancel local polling/request state; no BLE STOP exists |

Each entry has its own command, receive buffer and sequence state. MM writes
without response, SXB with response; chunks follow the actual negotiated MTU.
Reports retain typed fields and a date/partition cache key in the diagnostic's
`casper_sleep_report` attribute. Live entities expose separate left/right on-bed,
heart, breath, movement and snoring display values. The app's unset token `--`,
missing/null values, sequential updates and partial mutation before malformed-data
errors are preserved. These are device/app values without a medical interpretation.

SXB information `type` and `ver` are nullable strings. Non-null values merge into
previous information even when `error` is nonzero; null values retain earlier
strings. Information does not enable extra bed features. Firmware downloads and
updates are excluded, while these direct BLE information responses are retained.

For the RCRM handset, add **Casper Base remote finder (RCRM handset)** and use
`remote_find` (or Connect). This only establishes the connection, with no ExitLimit,
setup query or invented locator packet. A physical indication remains unverified.

## Protocol and safety boundaries

Bed GATT layouts select a one-byte or five-byte sum-checksummed format. Dedicated
alarm and light builders retain their own framing even on the one-byte transport.
Notifications retain all ordinary and extended parser branches. Sensor frames
carry compact JSON in the accepted 14-byte envelope; report payloads use gzip.
HA keeps complete 5/7/16-byte ordinary notifications intact and accepts stream
boundaries only at those supported lengths. Marker-valued payload and checksum
bytes do not truncate a notification, and short five-byte fragments are retained.
This corrects the app's marker-splitting bug without inventing a length header or
adding an ordinary checksum requirement. Length alone cannot distinguish every
fragmented or coalesced combination of the variable ordinary formats.
Neither bed nor sensor paths require a PIN or application authentication. Bed and
sensor notification channels initialize even when angle sensing is disabled.

HA uses its Bluetooth discovery, connection manager and command lock. It pairs
write/notify roles within a coherent service, serializes operations, owns and
cancels timers, limits malformed input and never disconnects unrelated devices.
These documented safety choices replace app bugs rather than changing proven
hardware commands. An HA sensor query has a five-second response bound; report
permission follows the proven one-second delay. These bounds do not establish
firmware acknowledgements or radio timing.

Excluded: phone microphone/DSP/recording/playback/sharing, app-local display names,
privacy/permission/navigation/database/chart/export infrastructure, generic unused
plugin APIs and datastore counters, cloud/firmware transfer including BLE OTA,
SSID/password/network provisioning (not found), unsafe undefined long-press
fallbacks and unsafe app lifecycle/race behavior. No in-scope command is deferred
for lack of maintainer hardware.

The [row101 disposition ledger](../apk-analysis/dispositions/row101-casper-base.md)
records exact accepted seals, every discovery, implementation/test references and
all exclusions. Raw APKs, extraction, reports and audits remain local and ignored.
