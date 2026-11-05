# BedJet PowerLayer

**Status:** ✅ Tested (confirmed working on a BedJet PowerLayer by @rluengen)

**Credit:** GATT layout and command values ported from the MIT-licensed
[`powerlayer` branch of natekspencer/ha-bedjet](https://github.com/natekspencer/ha-bedjet/tree/powerlayer).
Status-frame layout, movement timing and angle calibration derived from captures
contributed by [@Tim-GitHub](https://github.com/Tim-GitHub) in
[natekspencer/ha-bedjet#49](https://github.com/natekspencer/ha-bedjet/issues/49)
and the GATT dump in [#343](https://github.com/kristofferR/ha-adjustable-bed/issues/343).

## Known Models

- BedJet PowerLayer ultra-slim adjustable frame (1.75", ~900 lb lift)
- Advertises as `BEDJET_BF`; the GATT name characteristic reads `BEDFRM` from the
  factory and can be renamed from the remote
- Observed MAC prefixes: `40:22:D8`, `8C:4F:00`

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| n/a | BedJet (no PowerLayer control shipped) | `com.bedjet.app` |

BedJet's own app did not control the frame at the time of writing; BedJet
described app support as in development. There is therefore no APK to analyze
for this protocol, and all evidence comes from live BLE captures.

## Not the BedJet climate unit

The PowerLayer frame and the BedJet 3 climate blower are different products that
**advertise the same service UUID**, so an advertisement alone cannot tell them
apart. Only the frame exposes `00001001-…` once connected.

This integration controls **only the frame**. The blower is an air conditioner,
not a bed, and is out of scope; use a BedJet-specific integration for it.
Detection therefore keys on the advertised local name rather than the shared
service UUID, so setting up a climate unit is never offered. If the frame is
renamed to something that no longer starts with `BEDJET_BF` or `BEDFRM`,
auto-discovery stops matching and the bed type must be selected manually. After
connecting, the controller re-checks for the `1001` service and logs a clear
warning if the target turns out to be a climate unit.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head, foot) |
| Position Feedback | ✅ (degrees, see calibration below) |
| Memory Presets | ✅ recall only (M1–M3) |
| Memory Programming | ❌ no save command exists over BLE |
| Factory Presets | ✅ (Flat, Zero-G, TV, Anti-Snore) |
| Under-bed Lights | ❌ not present on this frame |
| Massage | ❌ module exists, but no command has been captured |
| Child Lock | ❌ remote-only, see below |

## Protocol Details

- **Advertised Service UUID:** `00001000-bed0-0080-aa55-4265644a6574` (shared with the climate unit)
- **Frame Service UUID:** `00001001-bed0-0080-aa55-4265644a6574` (frame only, visible after connecting)
- **Name Characteristic:** `00002001-bed0-0080-aa55-4265644a6574` (read/write, reads `BEDFRM`)
- **Status Characteristic:** `00002006-bed0-0080-aa55-4265644a6574` (read + notify, 20-byte frame)
- **Command Characteristic:** `00002007-bed0-0080-aa55-4265644a6574` (write)

### Command Format

Every command is two bytes:

```text
[0x01, <button>]
```

`0x01` is the only command opcode observed. The second byte is a remote key:

| Key | Value | Behaviour |
|-----|-------|-----------|
| Head up | `0x02` | watchdogged movement |
| Head down | `0x03` | watchdogged movement |
| Foot up | `0x04` | watchdogged movement |
| Foot down | `0x05` | watchdogged movement |
| Flat | `0x10` | latched preset |
| Anti-snore | `0x11` | latched preset |
| Zero-G | `0x12` | latched preset |
| TV | `0x13` | latched preset |
| Memory 1–3 | `0x20`–`0x22` | latched recall |

### Movement, stopping and timing

**The protocol defines no STOP command.** A movement key starts the motor and the
frame stops on its own shortly afterwards, so a release is simply the absence of
further writes. The controller declares `auto_stops_on_idle`, and the integration
never fabricates a stop write: writing anything else would start a new movement.

Measured from the captures, across writes separated by at least 2.8 s:

| Axis | Motion per single write | Travel per write |
|------|------------------------|------------------|
| Head | 1.18–1.41 s (median 1.34 s) | ~24 counts (~0.5°) |
| Foot | 1.18–1.41 s (median 1.28 s) | ~18 counts (~0.5°) |

The integration therefore repeats the key every 100 ms for the standard 10-pulse
press, which keeps the motor inside that watchdog window for the usual ~1 s hold.
Travel always ends about 1.3 s after the final write, so a dropped connection or
a cancelled command cannot leave a motor running.

Presets and memory recalls are **not** watchdogged: the frame drives all the way
to the stored position on a single write. They are sent exactly once; repeating
them would re-trigger the move partway through.

> **Unverified:** every capture spaced its writes further apart than the watchdog,
> so sub-watchdog streaming has never been observed on hardware. The watchdog
> model predicts it produces continuous travel, and it is bounded and safe either
> way, but please report real behaviour.

### Status Frame

The status characteristic reads and notifies a 20-byte frame:

| Offset | Meaning |
|--------|---------|
| 12–13 | Head position, big-endian raw actuator count |
| 14–15 | Foot position, big-endian raw actuator count |
| 4, 11, 16 | Observed changing during motion, meaning unknown |

Isolating each axis confirms the offsets: a head-only capture swept bytes 12–13
from 78 to 3362 while bytes 14–15 stayed at 0, and a foot-only capture swept
bytes 14–15 from 0 to 1704 while bytes 12–13 held at 104.

### Angle Calibration

Raw counts are not degrees and the relationship is not linear: the mechanical
linkage means the scale changes across the travel. The controller interpolates a
lookup table built by reading the BedJet LCD remote's own degree display against
the reported counts.

- Head: 0–73°
- Foot: 0–47°

Caveats:

- Expect roughly ±1° of unit-to-unit variation. The source frame rested at 1°
  rather than 0° when flat, and the table keeps that offset rather than hiding it.
- The frame recalibrates zero after a power loss. The remote shows `---` for both
  angles and asks for a flat cycle; pressing **Flat** restores a 0 reading after
  a few seconds.
- Because there is no "go to N degrees" command, `set_position` reaches a target
  with the integration's incremental seek loop rather than a direct write.

## Not Implemented

| Behaviour | Reason |
|-----------|--------|
| Wi-Fi provisioning (`00002002`, `00002003` carry SSID and password) | Out of scope: this integration is BLE-only and does not configure bed networking |
| Memory programming | The remote saves a slot by holding its key; no BLE save command has been observed |
| Child lock | Confirmed remote-only. With child lock on, BLE commands still move the frame, and toggling it produced no status change. There is no known opcode, and the frame's own firmware will need to extend the lock to BLE |
| Massage module | Optional kit; no capture exists yet. An owner with the kit has offered to help |
| Characteristics `00002005`, `00002008` | Present but never observed carrying traffic |
| Firmware version | Not located in any observed characteristic |

## Testing Status

| Capability | Status |
|------------|--------|
| Movement (head/foot, both directions) | Confirmed working over BLE on real hardware (upstream beta) |
| Presets and memory recall | Confirmed working over BLE on real hardware (upstream beta) |
| Position feedback offsets | Confirmed from isolated-axis captures |
| Angle calibration | Derived from one frame's remote readout; ±1° expected |
| This integration's controller | Confirmed working on a BedJet PowerLayer by @rluengen; individual feature coverage was not recorded |
