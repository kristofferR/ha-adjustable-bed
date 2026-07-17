# SleepSpa S9000AI (SLEEPSTAR)

**Status:** 🧪 Statically verified from the OEM app; physical hardware testing is pending

This controller is for the SleepSpa S9000AI device class advertised as
`SLEEPSTAR`. It is a CB37 sleep-monitor session over Nordic UART. Bed actions
use StarCode, but every StarCode packet is tunneled through the CB37 transparent
control-box route. It must not be configured as Sleepy's BOX25 or Okin CB35.

## Evidence

The implementation comes from a clean-room Phase 4 analysis of:

- App: SleepSpa 1.3.7 (build 37)
- Package: `com.dot.bedding.sleepspa.sleep_spa`
- Complete split APK set: base, `arm64_v8a`, `en`, `nb`, and `xxhdpi`
- Artifact-set SHA-256: `d114ec34fcd6645c30d356019ad756d3117d09f0eed8c41eb8e377b885557fdf`
- Report status: COMPLETE, with 29/29 independent packet/parser vectors passing

The report proves application behavior. Real-bed validation remains deferred
until a user can test a beta or release and provide a support bundle if needed.

## Discovery and variants

| Signal | Meaning |
|--------|---------|
| BLE name starts with `SLEEPSTAR` | S9000AI demo sleep-monitor device |
| Company ID `0x00B2`, payload byte 6 = `0x88` | Single-side variant |
| Company ID `0x00B2`, payload byte 6 = `0x86` | Dual-side variant |
| Missing or any other subtype byte | Dual fallback, matching the app |

The app also bundles real `SLEEPBT` single/dual library classes, but its own
application filter rejects them. The integration therefore explicitly rejects
`SLEEPBT` instead of misclassifying the shared Nordic UART service as another
bed protocol.

## BLE transport

| Purpose | UUID |
|---------|------|
| Nordic UART service | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| TX, write without response | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` |
| RX, notify | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` |

There is no application PIN, authentication exchange, encryption wrapper,
nonce, or outer checksum. The environment-sensor payload alone uses an inner
CRC-16/MODBUS value.

## Session sequence

The integration enables RX notifications before writing anything, then sends:

1. CB37 configuration page 1
2. Raw CB37 local date/time calibration
3. Wrapped StarCode local date/time calibration
4. Sleep-sensor firmware-version query
5. Motor, light, sleep configuration, environment duration, and environment
   address state queries

Writes use the app's 100 ms sender cadence. A single 12-second recovery timer
clears and requests configuration page 1 again. Page 1 contains a bitmap for
pages 2 through 8; only advertised missing pages are requested. Disconnect
cleanup cancels all session timers and sends no logout packet.

## Packet families

### Transparent control-box route

```text
AA 00 00 09 02 LL [StarCode payload]
```

`LL` is the one-byte StarCode payload length. Example STOP:

```text
AA 00 00 09 02 07 5A 01 03 10 30 0F A5
```

Normal StarCode actions use:

```text
5A 01 [32-bit key, big endian] A5
```

Extended values use:

```text
5A E0 04 key value value2 value3 A5
```

Direct motor positions use:

```text
5A F0 03 zone position 00 A5
```

Position is clamped to 0 through 100 and zones 0 through 4 address the five
controllable actuator parts.

### Sleep and environment routes

Sleep queries use:

```text
2A 00 00 family command length [payload]
```

Environment MODBUS messages use:

```text
AA 00 00 09 03 LL [MODBUS payload] crcLo crcHi
```

## Home Assistant features

| Feature | Proven behavior |
|---------|-----------------|
| Actuators | Head, feet, lumbar, Auxiliary 1, Auxiliary 2; shared STOP |
| Position feedback | 0-100% for five addressable parts; sixth feedback-only part retained in diagnostics |
| Direct position | Zones 0-4, one packet |
| Presets | Flat, TV, Zero-G, Anti-Snore, Lounge, both-up |
| Memory | Two app-visible slots; recall 3 writes then STOP, save 55 writes |
| Lighting | Discrete on/off/toggle, brightness 0-6; protocol API also retains color indices 0-7 |
| Sonic massage | Head, foot, and combined intensity 0-6; five modes; 10/20/30-minute timer |
| Sleep monitor | Query/config builders for anti-snore, sleep zone, daily/monthly reports |
| Environment | Duration, address, and seven-register query builders |
| Audio | Media, USB, noise, sonic type, volume, cutoff, reset, preset, and EQ protocol methods |

The APK names the last three position channels only by part number. The
integration exposes the two controllable channels as Auxiliary 1 and Auxiliary
2 rather than guessing their physical purpose. The sixth channel is
feedback-only and appears in controller diagnostics as
`sleepstar_part6_position`.

## Notifications

Both forms below are accepted:

- Direct inner status beginning with `A5`
- `AA ... 02` wrapper whose declared inner payload begins at byte 6

Motor status type `0x0D` maps bytes `4, 6, 8, 10, 5, 7` to head, foot,
lumbar, part 4, part 5, and feedback-only part 6. Values are clamped to 100.
Sonic (`0x0B`), alarm (`0x0C`), and EQ (`0x0E`) notifications are routed to
diagnostic controller state. Identical notifications inside 200 ms are
ignored, matching the app.

Sleep/environment/config/report responses are retained in controller state as
hex so support bundles preserve unmodified protocol evidence. The integration
does not guess the physical meaning of values that the analyzed app leaves
model-dependent.

## Deferred physical validation

After beta or release, useful validation includes:

1. Confirm Company ID `0x00B2`, subtype byte, and single/dual selection from an
   actual `SLEEPSTAR` advertisement.
2. Exercise every actuator and verify the two Auxiliary labels.
3. Verify preset, memory-save, brightness, sonic intensity/mode/timer, and STOP
   behavior.
4. Capture representative motor, sonic, alarm, environment, daily, and monthly
   notifications with a generated support bundle.
