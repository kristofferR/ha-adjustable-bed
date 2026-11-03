# Glideaway Motion / Montion app

Choose **Glideaway Motion / Montion app** and the model selected in the Android
app. This profile implements `com.ore.bedding.glideawaymontion` 1.0.3 (code 11),
whose archive label misspells Motion as “Montion”. Hardware remains unverified.
It is separate from the legacy **Okin ORE (A5 5A)** profile. Existing legacy
entries are not migrated automatically: the accepted app uses different bytes
and does not prove which hardware an existing entry controls.

## Model selection and controls

| App model | Description | Covers | Extra controls |
| --- | --- | --- | --- |
| MOTION 400 | GM-A4Z | Back/head, feet, head + feet | None |
| MOTION 450 | GM-A450Z | Back/head, feet, bed height | None |
| MOTION 500 | GM-A5Z | Back/head, feet, head + feet, bed height | Light and massage |
| MOTION 600 | GM-A6Z | Back/head, feet, neck tilt, bed height | Light and massage |

Every model has Flat, Anti-snore, Zero gravity, Memory A/B recall and save,
a bed alarm sensor and a Refresh alarm button. Models 500/600 add a toggle-only
light button, massage intensity up/down, wave frequency up/down, timer cycle,
massage off, and a reported massage timer sensor (minutes with the raw byte as
an attribute). There is no light-state feedback, direct massage level selection,
position feedback, or angle slider. Model selection owns the layout and extras;
generic motor count, massage, angle sensing and refresh-delay settings are hidden.
The motor pulse count still controls the duration of a cover movement.

The app scans without a name or service filter, remembers the selected MAC and
requires manual model selection. Shared FFE services, names and GM descriptions
do not identify a model. Add the integration manually and select the explicit
app/model. No model discovery rule, pairing, PIN, status query or clock write is
inferred from connecting. HA adapters and Bluetooth proxies use the normal
integration connection settings. Two physical addresses may use native HA
paired-bed routing; there is no app-proven single-address side protocol.

## Timing and actions

Held packets refresh every **300 ms**, accounting for elapsed BLE write time.
Normal cover movements use the configured pulse count times 300 ms as a
monotonic deadline. No further held write starts after that deadline; an
in-flight write finishes before cleanup. The zero-mask release follows at
**+300 and +600 ms**.
Cancellation uses the same release pair with fresh cancellation events and
keeps the serialized command lane until cleanup finishes.
Both release writes are attempted even if the first fails, then the error is
reported. Built-in preset,
recall, light and massage buttons use a single 300 ms press. For longer
preset/movement/feature holds, use `adjustable_bed.hold_control`:

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: bed_height_up
  duration: 2.4
```

Controls are `back_up/down`, `feet_up/down`, model-dependent `both_up/down`,
`bed_height_up/down`, `tilt_up/down`, plus `flat`, `anti_snore`, `zero_g`,
`memory_1`, `memory_2`. Models 500/600 add `light`, `massage_intensity_up/down`,
`massage_wave_up/down`, `massage_timer`, `massage_off`. Use the expanded names,
for example `back_up`, not a literal slash. Holds accept 0.1–30 seconds;
memory recalls must be shorter than five seconds. Use `save_preset` slot 1 or 2
(or the Save Memory buttons) for a **5.2 second** memory hold. The frame is the
same as recall; the app's saved toast is local, not a device acknowledgement.
Firmware storage and its actual threshold remain unverified.

The app omits release handling for combined movement and light, and lets streams
survive lifecycle changes. HA deliberately bounds every hold and releases those
controls too, using the proven global zero-mask packet. It does not reproduce
stale reconnect writes or delayed STOP packets interleaving with later commands.
These are safety exclusions, not extra inferred hardware commands.

## Alarm and clock

`adjustable_bed.glideaway_set_alarm` accepts `device_id`, `enabled`, optional
`side`, `time` (minute precision, required when enabling), and `wake_mode`
(`none`, `memory_1`, `memory_2`, default `none`). Disabling needs no time. Every
target must be this app profile. The serialized command first sends HA's local
RTC, waits 300 ms, then sends the alarm. `adjustable_bed.sync_clock` sends just
the RTC. Refresh alarm sends the query twice, immediately and 200 ms later;
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
- Public alarm time is the transmitted 0–23 hour. The app's 1–12 wheel sends its
  zero-based index plus AM/PM × 12, so its displayed hour is one higher.
- For Calendar weekday `d` (Sunday 1 to Saturday 7), selected time less than or
  equal to current hour/minute uses bit `d-1`; a later time uses bit `d%7`.
  No weekday selector exists. This counterintuitive direction is artifact-proven.
- Wake bytes are 00 (none), 11 (Memory A), 13 (Memory B). Disable writes zero
  alarm fields. The alarm sensor reports enabled/off, signed hour/minute and
  wake mode from the response; it does not invent a weekly schedule or ACK.

Alarm/RTC physical behavior, particularly midnight and weekday boundaries,
needs real-user confirmation after beta/release. Phone ringtones, notifications
and WorkManager jobs are outside the integration.

## Wire format and notifications

| Role | Service | Characteristic |
| --- | --- | --- |
| Write | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` |
| Notify | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` |

Bleak enables the notification CCCD. The app leaves Android's write type
unchanged, so the integration uses an actually advertised writable property,
with response for `write` only and without response when that property exists.
No undocumented handshake, fragmentation, authentication, side selector or
capability request is sent.

All outbound frames append `(~sum(body)) & 255`, including header bytes.
Normal frames are `E6 FE 16`, a four-byte little-endian mask, zero parameter,
checksum. Alarm query is `E2 80 03 00 9A`; alarm set is `ED 80 03 hour minute
weekday wake`, eight zeros, checksum. RTC is `E7 80 01` plus the six encoded
calendar fields and checksum.

| Normal control | Mask |
| --- | --- |
| Back/head up/down | 00000001 / 00000002 |
| Feet up/down | 00000004 / 00000008 |
| Combined up/down | 00000005 / 0000000A |
| Neck tilt up/down | 00000010 / 00000020 |
| Elevation up/down | 00000040 / 00000080 |
| Release | 00000000 |
| Flat / Anti-snore / Zero gravity | 08000000 / 00008000 / 00001000 |
| Memory A/B recall and sustained save | 00002000 / 00004000 |
| Light toggle | 00020000 |
| Massage intensity increase/decrease | 00000C00 / 01800000 |
| Massage wave increase/decrease | 10000000 / 04000000 |
| Massage timer / off | 00000200 / 00000100 |

Notifications parse timer byte 8 from E7 FE (length ≥10), byte 14 from ED FE
(length ≥16), byte 19 from F4 FE (length >20), or byte 19 from a fragmented
F4-first packet. Raw FF means zero; otherwise multiply by ten **only when the
previous displayed minutes differ from the raw byte**. For example, raw 1
then raw 10 leaves the display at 10. This shipped comparison is the explicit
accepted revision01 R01-F01 repair. HA also exposes the received raw value.
ED 80 alarm replies use bytes 3–6; the day byte affects enabled detection but is
not decoded as a schedule. Unknown wake values map to none. No incoming checksum
contract was proven, so none is invented.

HA rejects truncated/overflowing fragments, uses a per-controller buffer, clears
it on recognized frames/disconnect and expires it after two seconds. This is a
local stale-data guard, not a protocol timeout. It avoids the app's global
buffer, unsafe copies and stale joins. A buffered response accepts a one-byte
continuation. Complete F4 FE frames are not subject to
the fragment buffer's 30-byte limit. No position, battery, firmware, capability,
error or light-state parser exists in the accepted artifact.

## Provenance and coverage

Accepted source: row068 `com.ore.bedding.glideawaymontion` 1.0.3/code 11,
complete 19-member XAPK set SHA256
`7eb30a03349b9d9b9bffc43e2dafdb672c422fdd70e16b3e2c9ec2a55730c315`.
Accepted `work/report-revision01/REPORT.SHA256` SHA256:
`b3b4b2cc669d8050a68070aa3f9c1ad8021b0c7f9b244ab6703ae4d0caf3ec04`.
The original candidate was rejected. The accepted revision has explicit
coordinator mechanical R01-F01 repair provenance and two independent audit
rounds, with all 17 gates PASS. This implementation is a separate post-freeze
comparison, not a new clean-room report. Frozen evidence remains local and
unchanged. See the [every-discovery ledger](../apk-analysis/dispositions/row068-glideaway-motion.md)
and `tests/test_glideaway_motion.py` for the complete implementation mapping.
