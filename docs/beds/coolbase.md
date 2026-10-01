# Cool Base

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Cool Base adjustable bed bases (Keeson BaseI5 with cooling fan)
- DewertOKIN `OKIN-BLE` / `BTCB` controllers that use the same 8-byte packet
  format without fan controls

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Cool Base 1.0.0 (3) | `com.keeson.coolbase` |

The Cool Base profile follows the independently accepted clean-room audit of
this app; see the [row047 dispositions](../apk-analysis/dispositions/row047-coolbase.md).
Hardware behavior is unverified.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2 motors: head, foot) |
| Position Feedback | ❌ |
| Memory Presets | Cool Base: ❌ (the app's star button has no proven memory meaning; exposed as **Star button**). DewertOKIN OKIN-BLE: 2 slots |
| Factory Presets | ✅ (Flat, Zero-G, TV, Anti-Snore; Lounge only on DewertOKIN OKIN-BLE) |
| Massage | ✅ (Head massage, Foot massage, Massage mode buttons; mode sensor) |
| Light Control | ✅ (on/off from reported state; toggle) |
| Fan Control | ✅ (Left fan, Right fan, Fan sync buttons; level sensors 0-3) |

## Protocol Details

**Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** 8-byte packets with XOR checksum

## Detection

Cool Base bed-type detection matches device names containing `base-i5`, the
app's own scan filter. For configured
Cool Base entries, the DewertOKIN profile is selected when the connected BLE name
matches `okin-ble*` / `btcb*` or the BLE manufacturer value is `DewertOKIN`.
`OKIN-BLE` / `DewertOKIN` devices may need manual Cool Base selection only when
they advertise overlapping OKIN UUIDs.

Note: Cool Base shares the same service UUID (FFE5) as Keeson and other beds, but is distinguished by the device name pattern.

## Packet Format

All commands are 8 bytes:

```text
[0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
```

Where:
- Bytes 0-2 = Header `[0xE5, 0xFE, 0x16]`
- Bytes 3-6 = Command bytes (32-bit value in little-endian)
- Byte 7 = Trailer: `(sum(bytes 0-6) ^ 0xFF) & 0xFF`. The app writes literal
  trailers; this formula reproduces every one it ships.

## Commands

### Motor Control

| Action | Value | cmd0 | Notes |
|--------|-------|------|-------|
| Head Up | 0x01 | 0x01 | Hold to move |
| Head Down | 0x02 | 0x02 | Hold to move |
| Foot Up | 0x04 | 0x04 | Hold to move |
| Foot Down | 0x08 | 0x08 | Hold to move |
| Status query | 0x00 | 0x00 | All zeros; see below |

The app sends no distinct STOP: releasing a button ends the 100 ms refresh. The
integration then sends the all-zero frame, which is the app's own status query.

### Factory Presets

| Action | Value | cmd bytes |
|--------|-------|-----------|
| Flat | 0x08000000 | cmd3=0x08 |
| Zero-G | 0x00001000 | cmd1=0x10 |
| TV | 0x00004000 | cmd1=0x40 |
| Anti-Snore | 0x00008000 | cmd1=0x80 |
| Star button / Memory 1 | 0x00010000 | cmd2=0x01; Memory 1 only on DewertOKIN OKIN-BLE |
| Memory 2 | 0x00040000 | cmd2=0x04, DewertOKIN OKIN-BLE profile only |

### Light & Massage

| Action | Value | cmd bytes |
|--------|-------|-----------|
| Light Toggle | 0x00020000 | cmd2=0x02 |
| Massage Head | 0x00000800 | cmd1=0x08 |
| Massage Foot | 0x00000400 | cmd1=0x04 |
| Massage Level | 0x04000000 | cmd3=0x04 |

### Fan Control (Unique to Cool Base)

| Action | Value | cmd bytes | Notes |
|--------|-------|-----------|-------|
| Left Fan | 0x00400000 | cmd2=0x40 | Device-side level change |
| Right Fan | 0x40000000 | cmd3=0x40 | Device-side level change |
| Fan Sync | 0x00040000 | cmd2=0x04 | Fan-labelled; not bed sync |

## Notification Format

Only exact 28-byte replies to the status query are used. Any value outside the
listed range leaves that field unchanged:
- Byte 13: `(b & 0xF0) >> 6` is the light flag (0 off, 1 on)
- Byte 19: Massage mode (0-3)
- Byte 20: Left fan level (0-3)
- Byte 21: Right fan level (0-3)

The status query follows every tapped control three times, 200 ms apart, and
repeats every 3 s while connected. Polling never extends the idle disconnect.
Reported state clears when the connection ends. With the default
disconnect-after-command setting the light is usually unknown, so an on/off
request first sends a status query and waits up to 1 s for the reply.

The head massage, foot massage and massage mode buttons appear without the
massage option because the app always shows them.

## Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets, fans, massage, light | 1 | - | Then three status queries, 200 ms apart |
| Status query | 1 | - | Sent after movement and every 3 s while connected |

## Notes

1. Cool Base is a Keeson BaseI5 variant with additional fan/wind control features for cooling.

2. Fan, massage and light buttons send fixed frames. The app never computes the next level; how the device cycles levels is unverified.

3. Fan levels are reported in status replies and exposed as diagnostic sensors.

4. Fan sync is the app's fan-labelled button; its exact synchronization policy is unverified.

5. On DewertOKIN `OKIN-BLE` / `BTCB` devices, `0x00040000` is Memory 2 instead
   of sync fan. The integration exposes Memory 2 and suppresses fan controls for
   that profile to avoid showing both meanings for the same packet.
