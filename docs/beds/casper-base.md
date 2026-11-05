# Casper Base app

**Status:** ❓ Needs testing (accepted APK audit, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Casper Base **PRO** and **MAX**, selected explicitly through
  **Casper Base app (select product)**.
- 37 other command-bearing records accepted by this app's stored-product
  decoder, labelled **stored profile** in the product selector: NUP210, NUP300,
  NUP355B, NUP503B, NXC210, NXC300, NXC303, NXC310, NXC450, NXC455B, NXC513M,
  TTB01, NSF550, BAFD200, BAFD300, NLP200, NLP300, NEB300, NEF450, NXZ200,
  NJ200, AFD200, AFD300, NXC450G, Base Plus, CORE, ENHANCED, PREMIER, L400,
  L400SH, L500, L200, L300, L300SH, S175, S375, S575.
  - Their presence does not establish availability in a fresh Casper Base
    installation or support by another app.
  - The two empty placeholders expose no bed controls.
- Separate entries for the app's other devices: MM sleep sensors (names
  starting `RM-`), SXB sleep sensors (names starting `HJ-`) and the RCRM
  handset (see [Separate sleep sensors and remote finder](#separate-sleep-sensors-and-remote-finder)).

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Casper Base](https://play.google.com/store/apps/details?id=com.richmat.casperbase) 1.0.8 (version code 10800) | `com.richmat.casperbase` |

- This profile follows the independently accepted `com.richmat.casperbase`
  1.0.8 artifact.
- BLE behavior is statically verified. Physical motor effects, firmware
  compatibility, ATT behavior and sensor accuracy remain unverified. Real users
  can supply captures after a beta or release.

## Features

| Feature | PRO | MAX |
|---------|-----|-----|
| Motor Control | ✅ (back, legs, lumbar) | ✅ (back, legs, pillow, lumbar; different lumbar and pillow opcodes) |
| Flat | ✅ | ✅ |
| Presets | ✅ (TV, Lounge, Anti-snore, Zero-G; recall and save) | ✅ (same) |
| Memory Presets | ✅ (1 slot, recall and save) | ✅ (1 slot, recall and save) |
| Massage | ✅ (head/foot intensity, mode change, all off, 10/20/30-minute timers) | ✅ (same; different all-off opcode) |
| Lights | ✅ (Light Board button) | ✅ (Light Board and Bed Light buttons; ordinary light page once the capability reply confirms it) |
| RGB, music, alarms, sensor menu | ❌ | ❌ |
| Position Feedback | ❌ (raw motor-number diagnostics only, not calibrated angles) | ❌ (same) |
| Single-address Left/Right | ❌ (stored L400SH and L300SH only) | ❌ (same) |

- Stored profiles define their own motors, presets, memory slots, massage,
  light, RGB, music, alarm, fan/heating and sensor-menu sets in
  [`casper_base_catalog.py`](../../custom_components/adjustable_bed/casper_base_catalog.py).
- Fresh PRO/MAX do not gain music, sensor menus or repeating alarms from a reply.

### Controls

- The selected product defines its motor covers and named action buttons,
  including recall/save presets, massage zones, massage mode and timers, light
  icons, and any fan/heating controls.
- All named buttons appear in the card's utility section.
- PRO has back, legs and lumbar. MAX adds pillow control and uses different
  lumbar and pillow opcodes.
- Raw motor-number responses are available as diagnostics; they are not
  calibrated angle or position controls.
- Save buttons explicitly request programming; the app's three-second gesture
  does not require holding a Home Assistant button.
- Actions with no programming opcode have no save button, avoiding the app's
  unsafe zero-opcode long-press fallback.

## Protocol Details

**Service UUID:** one of six GATT layouts (below); the same UUID never identifies the app
**Write Characteristic:** the layout's write characteristic in the matching service
**Notify Characteristic:** the first notify-capable characteristic in the same service
**Format:** one-byte opcode on the first layout; otherwise five-byte sum-checksummed `6E 01 side opcode checksum`

| Layout | Service | Write characteristic | Command format |
|---|---|---|---|
| 0 | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | One byte |
| 1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | Five bytes |
| 2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | Five bytes |
| 3 | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | Five bytes |
| 4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | Five bytes |
| 5 | `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | Five bytes |

- HA pairs write/notify roles within one coherent service and uses the first
  discovered service whose write characteristic is writable.

### Packet Format

Builders in
[`casper_base_protocol.py`](../../custom_components/adjustable_bed/casper_base_protocol.py).
The checksum is the low byte of the sum of all preceding bytes.

| Packet | Template |
|---|---|
| Control (framed) | `6E 01 side opcode sum` (side `00` left/default, `01` right) |
| Control (one-byte layout) | `opcode` |
| Setup query (framed) | `6E type a b sum` |
| Setup query (one-byte layout) | last value only |
| Extended | `6E 20 length category subtype operation values… sum` (length counts every byte, including the checksum) |
| Light seconds | `6E 0B high low sum` |
| Light RGB | `6E 0C FF red sum` then `6E 0D green blue sum` |
| Single alarm | `6E 06 minutes_high mode sum` then `6E 05 minutes_low 00 sum` |

- Dedicated alarm and light builders retain their own framing even on the
  one-byte transport.
- Neither bed nor sensor paths require a PIN or application authentication.

### Write Mode

- The controller writes without response when the selected write
  characteristic advertises `write-without-response`, otherwise with response.
- Every write (first and queued) waits for a 100 ms tick first.

### Session Setup

On connect HA subscribes to the notify characteristic, then sends these setup
queries in order. Bed and sensor notification channels initialize even when
angle sensing is disabled.

| Query | Framed | One-byte layout |
|---|---|---|
| Exit limit | `6e 02 01 00 71` | `00` |
| Clock capability | `6e 08 01 01 78` | `01` |
| Light capability | `6e 0a 00 01 79` | `01` |
| Music capability | `6e 15 01 01 85` | `01` |
| Time sync (repeating-alarm products only) | Extended `08 03`, see [Configuration actions](#configuration-actions) | same |

## Detection / Setup

- Select **Casper Base app (select product)** during setup, then choose **PRO**
  or **MAX**.
- Select the actual product rather than inferring it from a shared service or
  the HLRM/JXRM strings.
- Existing generic Richmat entries are not migrated.
- Sleep sensors are classified by name; see
  [Separate sleep sensors and remote finder](#separate-sleep-sensors-and-remote-finder).

### Paired beds

- One-address Left/Right/Both controls are available only for the stored
  L400SH and L300SH layouts on a framed transport.
- Connect first so Home Assistant can verify the transport before enabling
  sides.
- Right sends side byte `01`; Both sends the left frame, then the right frame.
- Two-address pairs retain each side's own product selection.
- Music-page commands and the automatic anti-snore trigger use default left, as
  the app does, separately from selected-side catalog actions.

### Home Assistant setup

Choose the explicit **Casper Base app** profile and its PRO/MAX product. Other
stored-product choices are conditional records from this package, not inferred
app compatibility. The product owns the motor layout and accessory controls.
Configure two-address paired sides separately. Sleep sensors and the RCRM handset
use separate entries.

## Commands

Opcodes come from `ACTIONS` and `PRODUCTS` in
[`casper_base_catalog.py`](../../custom_components/adjustable_bed/casper_base_catalog.py);
frames are `control()` output for side `00`. On the one-byte layout only the
opcode is sent.

### Motor Control

| Command | App action | PRO | MAX |
|---|---|---|---|
| Back up / down | `HeadUp` / `HeadDown` | `0x24` / `0x25` (`6e 01 00 24 93` / `6e 01 00 25 94`) | same |
| Legs up / down | `FootUp` / `FootDown` | `0x26` / `0x27` (`6e 01 00 26 95` / `6e 01 00 27 96`) | same |
| Pillow (HA head) up / down | `PillowUp` / `PillowDown` | ❌ | `0x3F` / `0x40` (`6e 01 00 3f ae` / `6e 01 00 40 af`) |
| Lumbar up / down | `LumberUp` / `LumberDown` | `0x3F` / `0x40` (`6e 01 00 3f ae` / `6e 01 00 40 af`) | `0x41` / `0x42` (`6e 01 00 41 b0` / `6e 01 00 42 b1`) |
| STOP / release | `Stop` | `0x6E` (`6e 01 00 6e dd`) | same |

- Motor movement starts on a 100 ms tick and repeats at that interval for the
  configured pulse count, then sends the proven STOP.
- Every release uses a fresh cancellation event.

### Presets

| Command | App action | Recall | Save |
|---|---|---|---|
| Flat | `MotorReset` | `0x31` (`6e 01 00 31 a0`) | ❌ |
| TV | `TVPosition` | `0x58` (`6e 01 00 58 c7`) | `0x64` (`6e 01 00 64 d3`) |
| Lounge | `LoungePosition` | `0x59` (`6e 01 00 59 c8`) | `0x65` (`6e 01 00 65 d4`) |
| Anti-snore | `AntiSnoring` | `0x46` (`6e 01 00 46 b5`) | `0x69` (`6e 01 00 69 d8`) |
| Zero-G | `ZeroGravity` | `0x45` (`6e 01 00 45 b4`) | `0x66` (`6e 01 00 66 d5`) |

### Memory

| Command | App action | Recall | Save |
|---|---|---|---|
| Memory 1 | `MemoryPosition1` | `0x2E` (`6e 01 00 2e 9d`) | `0x2B` (`6e 01 00 2b 9a`) |

### Massage

| Command | App action | PRO | MAX |
|---|---|---|---|
| Head intensity | `MassageHeadInstensityStrengthen` | `0x4C` (`6e 01 00 4c bb`), then STOP | same |
| Foot intensity | `MassageFootInstensityStrengthen` | `0x4E` (`6e 01 00 4e bd`), then STOP | same |
| Mode change | `MassageModeChange` | `0x48` (`6e 01 00 48 b7`) | same |
| All off | `MassageModeAllOff` | `0x47` (`6e 01 00 47 b6`) | `0x5E` (`6e 01 00 5e cd`) |
| 10-minute timer | `Massage10MinuteTimer` | `0x5F` (`6e 01 00 5f ce`) | same |
| 20-minute timer | `Massage20MinuteTimer` | `0x63` (`6e 01 00 63 d2`) | same |
| 30-minute timer | `Massage30MinuteTimer` | `0x61` (`6e 01 00 61 d0`) | same |

- Massage/fan intensity taps send once followed by STOP.

### Lights

| Command | App action | PRO | MAX |
|---|---|---|---|
| Light Board | `LightBoard` | `0x3C` (`6e 01 00 3c ab`) | `0x50` (`6e 01 00 50 bf`) |
| Bed Light | `BedLight` | ❌ | `0x3C` (`6e 01 00 3c ab`) |

### Stored-profile actions

Further opcodes used only by stored profiles. A name with two opcodes depends on
the product's catalog entry.

| App action | Opcode |
|---|---|
| `MemoryPosition2` recall / save | `0x2F` / `0x2C` |
| `MemoryPosition3` recall / save | `0x30` / `0x2D` |
| `HeadAndFootUp` / `HeadAndFootDown` | `0x29` / `0x2A` |
| `Motor3Up` / `Motor3Down` | `0x71` / `0x72` |
| `PillowUp` / `PillowDown` | `0x3F` / `0x40` or `0x41` / `0x42` |
| `LumberUp` / `LumberDown` | `0x3F` / `0x40` or `0x41` / `0x42` |
| `LightBoard` | `0x3C` or `0x50` |
| `MassageModeAllOff` | `0x47` or `0x5E` |
| `HeatingOff` / `HeatingLowGear` / `HeatingHighGear` | `0x77` / `0x78` / `0x79` |
| `FanAllOff` | `0xA1` |
| `FanConstantMode` / `FanPulseMode` / `FanWaveMode` | `0xA3` / `0xA4` / `0xA5` |
| `Fan1InstensityStrengthen` / `Fan2InstensityStrengthen` (then STOP) | `0x8A` / `0x8B` |
| `CoaxingSleepMode` | `0x86` |

### Music page

Capability-gated on music products; always side `00`.

| App action | Opcode |
|---|---|
| `MusicPreviousSong` / `MusicNextSong` | `0xD2` / `0xD3` |
| `MusicVolumuUp` / `MusicVolumuDown` | `0xD4` / `0xD5` |
| `MusicShakeMode` | `0xD6` |
| `MusicPausePlay` | `0xD7` |
| `MusicBlueToothSwitch` | `0xD8` |
| `MusicSwitchSoundTrack` | `0xC4` |

- The music Bluetooth boolean follows the latest ordinary/extended reply or
  optimistic page switch, while raw events remain separate.
- USB soundtrack switching retains its two-second debounce and 900 ms delay:
  when Bluetooth is active it first sends `0xD8`.

## Configuration actions

Use `adjustable_bed.casper_base` with a `device_id` and `operation`.

- The service validates every selected physical target before any command.
- A feature must be present in the product and, where applicable, confirmed by
  the capability reply.
- Fresh PRO/MAX do not gain music, sensor menus or repeating alarms from a reply.

| Operation | Fields and behavior | Frame |
|---|---|---|
| `light_rgb` | `rgb_color: [red, green, blue]`, ordinary light page | `6E 0C FF red sum` + `6E 0D green blue sum` |
| `light_seconds` | `value` in seconds; zero is the app's always-on sentinel | `6E 0B high low sum`; zero sends `6e 0b ff ff 77` |
| `light_off` | Ordinary light page off | Control `0x75` (`6e 01 00 75 e4`) |
| `rgb_power`, `rgb_color` | Groove RGB page, `enabled` or `rgb_color` | `6E 20 09 04 04 01 00 enabled sum`; `6E 20 0B 04 01 01 00 red green blue sum` |
| `rgb_timer` | `value` in minutes: 5, 8, 10, 13, 15, 18, 21, 24, 27, 30, 120, 210, 300, 390, 480 | `6E 20 0A 04 02 01 00 minutes_high minutes_low sum` |
| `rgb_mode` | `value`: multicolor red 2, cycling 3, flowing 5 | `6E 20 0A 04 05 01 00 01 value sum` |
| `rgb_groove` | `value`: spectrum 1, energy 2, rhythm 3, scroll 4 | `6E 20 0A 04 05 01 00 02 value sum` |
| `rgb_breathe` | Groove RGB breathe effect | `6e 20 08 04 06 01 00 a1` |
| `alarm`, `alarm_cancel` | Single alarm, `hour`, `minute`, `mode`; next local occurrence at minute precision | Single-alarm pair with the mode's recall opcode; cancel `6e 06 00 00 74` + `6e 05 00 00 73` |
| `repeat_alarm` | `slot`, `hour`, `minute`, `mode`, `enabled`, `days` (Monday 0 through Sunday 6); empty days means once | `6E 20 0D 05 01 01 slot reserved hour minute mode mask sum` |
| `repeat_delete`, `repeat_query` | Delete `slot`, or clear the local list and request it again | `6E 20 08 05 02 01 slot sum`; query `6e 20 08 05 01 00 00 9c` |
| `time_sync` | Send Home Assistant's local calendar time for repeating alarms | `6E 20 0D 08 03 01 year-1970 month day hour minute second sum` |
| `sleep_name` | Request the separately connected sensor's advertised name on a sensor-capable stored product | `6e 20 08 06 03 00 00 9f` |

- Alarm modes are `tv`, `zero_g`, `anti_snore`, `lounge`, `memory_1`,
  `memory_2`, `memory_3`; only modes in the selected product's alarm list are
  accepted. PRO and MAX have no alarm list.
- Repeating-alarm `mask`: Monday is bit 7 through Sunday bit 1; bit 0 is
  `enabled`.
- The reserved byte of an existing repeating alarm is retained when editing it.
- RGB receive timers use `high * 60 + low`, while sends use a 16-bit minute
  value. This asymmetric behavior belongs to the app and is not silently
  normalized.

## Automatic anti-snore trigger

Microphone recording and phone audio processing are outside this integration.
For a detector supplied by another HA integration, call `snore_detector` with
`source: sensor.your_detector` and `enabled: true`.

| Detector status | Effect |
|---|---|
| 1 | Increments the counter |
| 0 or unavailable | Resets the counter |
| Other integer values | Counter unchanged |

- The sensor must report the app's detector status convention above.
- Every five qualifying samples attempt the ordinary anti-snore preset (control
  `0x46`, default left) and reset the counter.
- Polling begins after three seconds and repeats every three seconds.
- This is separate from manual anti-snore recall and save.
- Disable with the same operation and `enabled: false`.
- Disconnect/unload cancels the owned task, and replacing a session cannot
  revive an old timer.
- HA deliberately does not reproduce the app's leaked timers, late
  post-disposal sends or overlapping poll/write callbacks.
- No extra STOP packet is added to this preset trigger.

## Separate sleep sensors and remote finder

Add sensors as separate entries: **Casper Base sleep sensor (RM- / MM)** or
**Casper Base sleep sensor (HJ- / SXB)**.

- Discovery classification is case-sensitive `RM-` or `HJ-` at the start of
  the name. Scanning substrings and classification are separate rules.
- No bed product or cloud credential is inferred from the sensor.

### Sensor protocol

Builders in
[`casper_sleep_protocol.py`](../../custom_components/adjustable_bed/casper_sleep_protocol.py).

| Item | MM | SXB |
|---|---|---|
| Service | `0000e0ff-3c17-d293-8e48-14fe2e4da212` or `2320567c-05cf-6eb4-c341-772851827e1b` | same |
| Write | any write-without-response characteristic | `00000002-3c17-d293-8e48-14fe2e4da212` |
| Notify | any notify characteristic | `00000003-3c17-d293-8e48-14fe2e4da212` |
| Write mode | without response | with response |

- Sensor frames carry compact JSON in the accepted 14-byte envelope:
  `00 seq 01 00 (len+7) 00 00 11 03 43 55 44 len_low len_high` followed by
  `{"id":seq,"cmd":…,"val":…}`.
- Report payloads use gzip.
- Each entry has its own command, receive buffer and sequence state.
- Chunks follow the actual negotiated MTU.

| Sensor operation | Behavior | JSON `cmd` / `val` |
|---|---|---|
| `sensor_time` | Synchronize timestamp and timezone/UTC offset | `s_time`, MM `{"ts","tz"}`, SXB `{"ts","utc"}` |
| `sensor_info` | SXB: time request followed by the retained `s_init` information query | `s_time`, then `s_init` with `0` |
| `sensor_query_part` | MM sends `s_part` with null; SXB sends `q_part` | `val` null |
| `sensor_part` | `part`: MM 1 or 2; SXB left 11, right 12, both 13 | `s_part` with the part |
| `sensor_live` | `enabled`: start/stop two-second live polling | `q_realtime`, `{"type":0,"time":1}` |
| `sensor_report` | `part`, `report_type` (daily 1/monthly 2), `year`, `month`, `day` (use 1 for monthly) | `q_report` with `part`, `type`, `y`, `m`, `d`; then permission with `"allow":1` (MM adds it to the request, SXB sends `{"allow":1}`) |
| `sensor_stop` | Cancel local polling/request state; no BLE STOP exists | none |

### Sensor data

- Reports retain typed fields and a date/partition cache key in the
  diagnostic's `casper_sleep_report` attribute.
- Live entities expose separate left/right on-bed, heart, breath, movement and
  snoring display values.
- The app's unset token `--`, missing/null values, sequential updates and
  partial mutation before malformed-data errors are preserved.
- These are device/app values without a medical interpretation.
- SXB information `type` and `ver` are nullable strings. Non-null values merge
  into previous information even when `error` is nonzero; null values retain
  earlier strings.
- Information does not enable extra bed features.
- Firmware downloads and updates are excluded, while these direct BLE
  information responses are retained.

### Remote finder

- For the RCRM handset, add **Casper Base remote finder (RCRM handset)** and
  use `remote_find` (or Connect).
- This only establishes the connection, with no ExitLimit, setup query or
  invented locator packet.
- A physical indication remains unverified.

## Position Feedback / Notifications

The **Casper Base state** diagnostic exposes the product, all parsed events,
alarm records and malformed-packet errors.

| Notification | Event |
|---|---|
| `6e 09 01 00 78` | Clock page available |
| `6e 0e 00 03 7f` | Light page available |
| `6e 1a 00 01 89` | Aroma available |
| `6e 07 01 01 77` / `6e 07 01 02 78` | Alarm set / cancelled |
| `6e 16 01 01 86` | Music page available |
| `6e 90 c1 01 c0` | Detection available |
| `6e 21 00 00 8f` | Snore detection available |
| `6E 90 xx yy zz` (5 bytes) | High nibble of byte 2: `0` protocol version, `1` bed mode, `3` raw motor index/status/value, `A` massage mode and zones, `B` USB/play/music-follow/Bluetooth, `C` detection status/details, `D` music volume or shake gear |
| 7 bytes with `90` at byte 1, or 16 bytes | Raw desk height values |
| `6E 20 …` (extended) | Categories `01` motor, `02` massage, `03` white LED, `04` RGB, `05` alarm list/update, `06` snore/bed exit/sleep name, `09` music, `0A` check, `0B` press mode/same control, `0F` desk |

- Information from raw motor/desk events keeps its original index and values,
  without guessing a physical axis or unit.
- Alarm list responses suppress identical duplicates; updates replace the first
  matching ID.
- Capability, RGB, music and acknowledgement consumers retain separate state.
- Notifications retain all ordinary and extended parser branches. Extended
  frames must match their length and checksum.

### Receive framing

- HA keeps complete 5/7/16-byte ordinary notifications intact and accepts
  stream boundaries only at those supported lengths.
- Marker-valued payload and checksum bytes do not truncate a notification, and
  short five-byte fragments are retained.
- This corrects the app's marker-splitting bug without inventing a length
  header or adding an ordinary checksum requirement.
- Length alone cannot distinguish every fragmented or coalesced combination of
  the variable ordinary formats.

## Command Timing

| Timing | Value |
|---|---|
| Write tick | 100 ms before each bed write and before each sensor command |
| Motor hold | Configured pulse count, one opcode per tick, then STOP |
| Soundtrack switch | two-second debounce, 900 ms delay |
| Anti-snore detector poll | first after three seconds, then every three seconds |
| Sensor live poll | every two seconds |
| Sensor query response bound | five seconds (HA) |
| Report permission delay | one second |

- The five-second sensor query bound is HA's; the one-second report permission
  delay is proven. These bounds do not establish firmware acknowledgements or
  radio timing.

## Notes

### Protocol and safety boundaries

- HA uses its Bluetooth discovery, connection manager and command lock.
- It pairs write/notify roles within a coherent service, serializes
  operations, owns and cancels timers, limits malformed input and never
  disconnects unrelated devices.
- These documented safety choices replace app bugs rather than changing proven
  hardware commands.
- Excluded: phone microphone/DSP/recording/playback/sharing, app-local display
  names, privacy/permission/navigation/database/chart/export infrastructure,
  generic unused plugin APIs and datastore counters, cloud/firmware transfer
  including BLE OTA, SSID/password/network provisioning (not found), unsafe
  undefined long-press fallbacks and unsafe app lifecycle/race behavior.
- No in-scope command is deferred for lack of maintainer hardware.

### Analysis provenance

- Package `com.richmat.casperbase`, Casper Base 1.0.8 (version code 10800).
- Artifact set SHA-256:
  `2d21d42c17a7b5ae60c2403ff3654d80993e6d09f879cfe666c6d58270123f8b`
  (independent audit ACCEPT).
- The row101 audit records exact accepted seals, every discovery,
  implementation/test references and all exclusions. Its entries are the
  [ledger fixture](../../tests/fixtures/casper_base/ledger.json) that
  `tests/test_casper_base_ledger.py` checks.
- Raw APKs, extraction, reports and audits remain local and ignored.
