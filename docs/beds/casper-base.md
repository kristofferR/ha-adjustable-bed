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
  [`casper_base_catalog.py`](../../custom_components/adjustable_bed/casper_base_catalog.py);
  each product is a profile in
  [`profiles/casper.py`](../../custom_components/adjustable_bed/profiles/casper.py)
  over the [Richmat codec](richmat.md#casper-base).
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

Casper Base beds speak the [Richmat 6E](richmat.md) wire format. The
[Casper and Hush family](richmat.md#casper-and-hush-family) and its
[Casper Base profile](richmat.md#casper-base) give the transports, the session
setup, every frame this route sends, the notifications and the timing.

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
- Enabling sides connects to the bed first so Home Assistant can verify the
  transport.
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

## Configuration actions

Use `adjustable_bed.casper_base` with a `device_id` and `operation`.

- The service validates every selected physical target before any command.
- A feature must be present in the product and, where applicable, confirmed by
  the capability reply.
- Fresh PRO/MAX do not gain music, sensor menus or repeating alarms from a reply.
- The [Richmat guide](richmat.md#casper-and-hush-family) lists the frame each
  operation sends.

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

- Alarm modes are `tv`, `zero_g`, `anti_snore`, `lounge`, `memory_1`,
  `memory_2`, `memory_3`; only modes in the selected product's alarm list are
  accepted. PRO and MAX have no alarm list.
- The reserved byte of an existing repeating alarm is retained when editing it.

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

- Sensor frames carry compact JSON in the sleep-sensor envelope built by
  [`codec/sleep_envelope.py`](../../custom_components/adjustable_bed/codec/sleep_envelope.py):
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
alarm records and malformed-packet errors. Raw motor and desk events are not
calibrated angles or positions. The
[Casper and Hush family](richmat.md#casper-and-hush-family) lists every
notification and how the stream is split.

## Command Timing

The bed's write tick, motor hold, soundtrack switch and detector poll are in the
Richmat guide's [catalog app timing](richmat.md#catalog-app-timing).

| Timing | Value |
|---|---|
| Write tick | 100 ms before each sensor command |
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
