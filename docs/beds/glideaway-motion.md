# Glideaway Motion / Montion app

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

Choose **Glideaway Motion / Montion app** and the model selected in the Android
app. It is separate from the legacy **Okin ORE (A5 5A)** profile. Existing
legacy entries are not migrated automatically: the accepted app uses different
bytes and does not prove which hardware an existing entry controls.

## Known Models

- Glideaway MOTION 400 (GM-A4Z), MOTION 450 (GM-A450Z), MOTION 500 (GM-A5Z)
  and MOTION 600 (GM-A6Z) bases, selected manually as in the app

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Glideaway Motion](https://play.google.com/store/apps/details?id=com.ore.bedding.glideawaymontion) 1.0.3 (code 11) | `com.ore.bedding.glideawaymontion` |

This profile implements `com.ore.bedding.glideawaymontion` 1.0.3 (code 11),
whose archive label misspells Motion as “Montion”. Hardware remains unverified.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (per model: back/head, feet, head + feet, neck tilt, bed height) |
| Position Feedback | ❌ (no position feedback or angle slider) |
| Presets | ✅ Flat, Anti-snore, Zero gravity (every model) |
| Memory Presets | ✅ Memory A/B recall and save (every model) |
| Bed alarm | ✅ Alarm sensor, Refresh alarm button and alarm action (every model) |
| Lights | ⚠️ Toggle-only light button (500/600); no light-state feedback |
| Massage | ⚠️ 500/600: intensity up/down, wave frequency up/down, timer cycle, off; no direct level selection |
| Massage timer sensor | ✅ 500/600 (minutes, with the raw byte as an attribute) |
| Paired beds | ✅ Two physical addresses via native HA paired-bed routing; no app-proven single-address side protocol |

## Protocol Details

**Write Service / Characteristic:** `0000ffe5-0000-1000-8000-00805f9b34fb` / `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Service / Characteristic:** `0000ffe0-0000-1000-8000-00805f9b34fb` / `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** byte frames ending in a complement-of-sum checksum

| Role | Service | Characteristic |
| --- | --- | --- |
| Write | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` |
| Notify | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` |

### Write Mode

Bleak enables the notification CCCD. The app leaves Android's write type
unchanged, so the integration uses an actually advertised writable property,
with response for `write` only and without response when that property exists.
No undocumented handshake, fragmentation, authentication, side selector or
capability request is sent.

### Packet Format

All outbound frames append `(~sum(body)) & 255`, including header bytes.

| Frame | Layout |
| --- | --- |
| Normal | `E6 FE 16`, a four-byte little-endian mask, zero parameter, checksum |
| Alarm query | `E2 80 03 00 9A` |
| Alarm set | `ED 80 03 hour minute weekday wake`, eight zeros, checksum |
| RTC | `E7 80 01` plus the six encoded calendar fields and checksum |

## Detection / Setup

- The app scans without a name or service filter, remembers the selected MAC
  and requires manual model selection.
- Shared FFE services, names and GM descriptions do not identify a model. Add
  the integration manually and select the explicit app/model.
- No model discovery rule, pairing, PIN, status query or clock write is
  inferred from connecting.
- HA adapters and Bluetooth proxies use the normal integration connection
  settings. Two physical addresses may use native HA paired-bed routing; there
  is no app-proven single-address side protocol.

## Model selection and controls

| App model | Description | Covers | Extra controls |
| --- | --- | --- | --- |
| MOTION 400 | GM-A4Z | Back/head, feet, head + feet | None |
| MOTION 450 | GM-A450Z | Back/head, feet, bed height | None |
| MOTION 500 | GM-A5Z | Back/head, feet, head + feet, bed height | Light and massage |
| MOTION 600 | GM-A6Z | Back/head, feet, neck tilt, bed height | Light and massage |

- Every model has Flat, Anti-snore, Zero gravity, Memory A/B recall and save,
  a bed alarm sensor and a Refresh alarm button.
- Models 500/600 add a toggle-only light button, massage intensity up/down,
  wave frequency up/down, timer cycle, massage off, and a reported massage
  timer sensor (minutes with the raw byte as an attribute).
- There is no light-state feedback, direct massage level selection, position
  feedback, or angle slider.
- Model selection owns the layout and extras; generic motor count, massage,
  angle sensing and refresh-delay settings are hidden. The motor pulse count
  still controls the duration of a cover movement.

## Commands

Every normal frame is `E6 FE 16` + mask (little-endian) + `00` + checksum.

### Motor Control

| Normal control | Mask | Bytes (hex) |
| --- | --- | --- |
| Back/head up | `00000001` | `E6 FE 16 01 00 00 00 00 04` |
| Back/head down | `00000002` | `E6 FE 16 02 00 00 00 00 03` |
| Feet up | `00000004` | `E6 FE 16 04 00 00 00 00 01` |
| Feet down | `00000008` | `E6 FE 16 08 00 00 00 00 FD` |
| Combined up | `00000005` | `E6 FE 16 05 00 00 00 00 00` |
| Combined down | `0000000A` | `E6 FE 16 0A 00 00 00 00 FB` |
| Neck tilt up | `00000010` | `E6 FE 16 10 00 00 00 00 F5` |
| Neck tilt down | `00000020` | `E6 FE 16 20 00 00 00 00 E5` |
| Elevation up | `00000040` | `E6 FE 16 40 00 00 00 00 C5` |
| Elevation down | `00000080` | `E6 FE 16 80 00 00 00 00 85` |
| Release | `00000000` | `E6 FE 16 00 00 00 00 00 05` |

### Presets and Memory

| Normal control | Mask | Bytes (hex) |
| --- | --- | --- |
| Flat | `08000000` | `E6 FE 16 00 00 00 08 00 FD` |
| Anti-snore | `00008000` | `E6 FE 16 00 80 00 00 00 85` |
| Zero gravity | `00001000` | `E6 FE 16 00 10 00 00 00 F5` |
| Memory A recall and sustained save | `00002000` | `E6 FE 16 00 20 00 00 00 E5` |
| Memory B recall and sustained save | `00004000` | `E6 FE 16 00 40 00 00 00 C5` |

### Light and Massage (500/600)

| Normal control | Mask | Bytes (hex) |
| --- | --- | --- |
| Light toggle | `00020000` | `E6 FE 16 00 00 02 00 00 03` |
| Massage intensity increase | `00000C00` | `E6 FE 16 00 0C 00 00 00 F9` |
| Massage intensity decrease | `01800000` | `E6 FE 16 00 00 80 01 00 84` |
| Massage wave increase | `10000000` | `E6 FE 16 00 00 00 10 00 F5` |
| Massage wave decrease | `04000000` | `E6 FE 16 00 00 00 04 00 01` |
| Massage timer | `00000200` | `E6 FE 16 00 02 00 00 00 03` |
| Massage off | `00000100` | `E6 FE 16 00 01 00 00 00 04` |

## Notifications

- Notifications parse the massage timer from byte 8 of E7 FE (length ≥10),
  byte 14 of ED FE (length ≥16), byte 19 of F4 FE (length >20), or byte 19 of
  a fragmented F4-first packet.
- Raw FF means zero; otherwise multiply by ten **only when the previous
  displayed minutes differ from the raw byte**. For example, raw 1 then raw 10
  leaves the display at 10. This shipped comparison is the explicit accepted
  revision01 R01-F01 repair. HA also exposes the received raw value.
- ED 80 alarm replies use bytes 3–6; the day byte affects enabled detection
  but is not decoded as a schedule. Unknown wake values map to none.
- No incoming checksum contract was proven, so none is invented.
- HA rejects truncated/overflowing fragments, uses a per-controller buffer,
  clears it on recognized frames/disconnect and expires it after two seconds.
  This is a local stale-data guard, not a protocol timeout. It avoids the app's
  global buffer, unsafe copies and stale joins. A buffered response accepts a
  one-byte continuation. Complete F4 FE frames are not subject to the fragment
  buffer's 30-byte limit.
- No position, battery, firmware, capability, error or light-state parser
  exists in the accepted artifact.

## Command Timing

| Operation | Timing |
| --- | --- |
| Held packet refresh | Every **300 ms**, accounting for elapsed BLE write time |
| Cover movement | Configured pulse count × 300 ms, as a monotonic deadline |
| Release | Zero-mask release at **+300 and +600 ms** |
| Built-in preset, recall, light and massage buttons | Single 300 ms press |
| Memory save | **5.2 second** hold |
| Alarm set | RTC, 300 ms wait, alarm |
| Refresh alarm | Query twice, immediately and 200 ms later |

- No further held write starts after the movement deadline; an in-flight write
  finishes before cleanup.
- Cancellation uses the same release pair with fresh cancellation events and
  keeps the serialized command lane until cleanup finishes.
- Both release writes are attempted even if the first fails, then the error is
  reported.

## Hold actions

For longer preset/movement/feature holds, use `adjustable_bed.hold_control`:

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: bed_height_up
  duration: 2.4
```

- Controls are `back_up/down`, `feet_up/down`, model-dependent `both_up/down`,
  `bed_height_up/down`, `tilt_up/down`, plus `flat`, `anti_snore`, `zero_g`,
  `memory_1`, `memory_2`. Models 500/600 add `light`,
  `massage_intensity_up/down`, `massage_wave_up/down`, `massage_timer`,
  `massage_off`. Use the expanded names, for example `back_up`, not a literal
  slash.
- Holds accept 0.1–30 seconds; memory recalls must be shorter than five
  seconds.
- Use `save_preset` slot 1 or 2 (or the Save Memory buttons) for a **5.2
  second** memory hold. The frame is the same as recall; the app's saved toast
  is local, not a device acknowledgement. Firmware storage and its actual
  threshold remain unverified.

## Alarm and clock

`adjustable_bed.glideaway_set_alarm` accepts `device_id`, `enabled`, optional
`side`, `time` (minute precision, required when enabling), and `wake_mode`
(`none`, `memory_1`, `memory_2`, default `none`).

- Disabling needs no time. Every target must be this app profile.
- The serialized command first sends HA's local RTC, waits 300 ms, then sends
  the alarm. `adjustable_bed.sync_clock` sends just the RTC.
- Refresh alarm sends the query twice, immediately and 200 ms later;
  connection itself sends neither query nor RTC.

```yaml
action: adjustable_bed.glideaway_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "06:30:00"
  wake_mode: memory_1
```

The artifact has unusual calendar encoding, preserved literally rather than
replaced with an assumed next-occurrence algorithm:

- RTC uses year minus 1900, zero-based month, day minus one and hour minus one
  (midnight becomes FF), followed by minute/second.
- Public alarm time is the transmitted 0–23 hour. The app's 1–12 wheel sends
  its zero-based index plus AM/PM × 12, so its displayed hour is one higher.
- For Calendar weekday `d` (Sunday 1 to Saturday 7), selected time less than or
  equal to current hour/minute uses bit `d-1`; a later time uses bit `d%7`.
  No weekday selector exists. This counterintuitive direction is
  artifact-proven.
- Wake bytes are 00 (none), 11 (Memory A), 13 (Memory B). Disable writes zero
  alarm fields. The alarm sensor reports enabled/off, signed hour/minute and
  wake mode from the response; it does not invent a weekly schedule or ACK.

Alarm/RTC physical behavior, particularly midnight and weekday boundaries,
needs real-user confirmation after beta/release. Phone ringtones,
notifications and WorkManager jobs are outside the integration.

## Notes

### Safety exclusions

The app omits release handling for combined movement and light, and lets
streams survive lifecycle changes. HA deliberately bounds every hold and
releases those controls too, using the proven global zero-mask packet. It does
not reproduce stale reconnect writes or delayed STOP packets interleaving with
later commands. These are safety exclusions, not extra inferred hardware
commands.

### Analysis provenance

- Accepted source: row068 `com.ore.bedding.glideawaymontion` 1.0.3/code 11,
  complete 19-member XAPK set SHA256
  `7eb30a03349b9d9b9bffc43e2dafdb672c422fdd70e16b3e2c9ec2a55730c315`.
- Accepted `work/report-revision01/REPORT.SHA256` SHA256:
  `b3b4b2cc669d8050a68070aa3f9c1ad8021b0c7f9b244ab6703ae4d0caf3ec04`.
- The original candidate was rejected. The accepted revision has explicit
  coordinator mechanical R01-F01 repair provenance and two independent audit
  rounds, with all 17 gates PASS.
- This implementation is a separate post-freeze comparison, not a new
  clean-room report. Frozen evidence remains local and unchanged.
- See the [every-discovery ledger](../apk-analysis/dispositions/row068-glideaway-motion.md)
  and `tests/test_glideaway_motion.py` for the complete implementation mapping.
