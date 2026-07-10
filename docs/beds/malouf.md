# Malouf/Lucid

**Status:** ✅ Tested

> Protocol re-verified 2026-07-10 against a fresh jadx decompile of Lucid Base
> v1.3.3 (`com.lucid.bedbase`): frame formats, checksum, command values,
> preset repeat behaviour, and timing all match the shipped controllers.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Malouf
- Lucid
- Structures

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Malouf Base](https://play.google.com/store/apps/details?id=com.malouf.bedbase) | `com.malouf.bedbase` |
| ✅ | [Lucid Base](https://play.google.com/store/apps/details?id=com.lucid.bedbase) | `com.lucid.bedbase` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots, save + recall) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Lumbar | ✅ |
| Head Tilt | ✅ |

## Hi-Lo Layout

Some OKIN/Malouf-protocol beds use a Hi-Lo actuator layout instead of the usual
`back/legs/head/feet` ladder. For those beds, the integration exposes:

- Back
- Legs
- Head End Tilt
- Foot End Tilt
- Bed Height

`Bed Height` raises or lowers the whole frame by moving both lift columns
together. `Head End Tilt` and `Foot End Tilt` control the two columns
independently for lengthwise tilt.

## Protocol Variants

Malouf beds use two distinct protocols. The integration auto-detects which one your bed uses.

### NEW_OKIN (Nordic UART)

**Advertised Service UUID:** `01000001-0000-1000-8000-00805f9b34fb`
**Command Service:** Nordic UART (`6e400001-b5a3-f393-e0a9-e50e24dcca9e`)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 8 bytes `[0x05, 0x02, (cmd>>24)&0xFF, (cmd>>16)&0xFF, (cmd>>8)&0xFF, cmd&0xFF, 0x00, 0x00]`

Some newer Malouf S755 / DewertOkin `CB.24.42.28` bases advertise only the
Nordic UART service with a `Smartbed428...` name and OKIN manufacturer payload
starting `AB 01 02`. Those are still the NEW_OKIN/Malouf 8-byte protocol, not
the CB24 7-byte protocol.

### LEGACY_OKIN (FFE5)

**Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Format:** 9 bytes `[0xE6, 0xFE, 0x16, cmd&0xFF, (cmd>>8)&0xFF, (cmd>>16)&0xFF, (cmd>>24)&0xFF, 0x00, checksum]`
**Checksum:** `(~sum(bytes[0:8])) & 0xFF`

Some Lucid L600 / DewertOKIN `OKIN-BLE` controllers advertise the Malouf/Lucid
family UUID (`01000001-...`) but expose only the FFE5/FFE9 command service after
connection. Their advertising manufacturer payload commonly contains `BTCB`.
Those devices are treated as the LEGACY_OKIN/FFE5 protocol.

## Commands

Both protocols use the same command values (32-bit integers):

### Motor Commands

| Command | Value | Description |
|---------|-------|-------------|
| Head Up | `0x1` | Raise head |
| Head Down | `0x2` | Lower head |
| Foot Up | `0x4` | Raise foot |
| Foot Down | `0x8` | Lower foot |
| Head Tilt Up | `0x10` | Raise head tilt |
| Head Tilt Down | `0x20` | Lower head tilt |
| Lumbar Up | `0x40` | Raise lumbar |
| Lumbar Down | `0x80` | Lower lumbar |
| Dual Up | `0x5` | Raise head + foot |
| Dual Down | `0xA` | Lower head + foot |
| Stop | `0x0` | Stop all |

### Preset Commands

| Command | Value |
|---------|-------|
| Flat | `0x8000000` |
| Zero-G | `0x1000` |
| Lounge | `0x2000` |
| TV/Read | `0x4000` |
| Anti-Snore | `0x8000` |
| Memory 1 | `0x10000` |
| Memory 2 | `0x40000` |

### Memory Programming (hold-to-save)

The app saves the current position by emulating a held memory button: it
streams the save command at the protocol's repeat interval for the full
repeat window (85×150ms legacy, 55×100ms new OKIN), then sends STOP.

| Command | Value |
|---------|-------|
| Save Memory 1 | `0x10000` (same as recall; the sustained stream signals "save") |
| Save Memory 1 (`Smartbed238` names) | `0x80010000` |
| Save Memory 2 | `0x80040000` |

### Other Commands

| Command | Value |
|---------|-------|
| Light Toggle | `0x20000` |
| Massage Head + | `0x800` |
| Massage Foot + | `0x400` |
| Massage Head - | `0x800000` |
| Massage Foot - | `0x1000000` |
| Massage Timer | `0x200` |
| Massage Off | `0x2000000` |

### Observed But Not Implemented

Additional commands found in the app (fresh Lucid Base 1.3.3 decompile,
2026-07-10) that the integration does not currently expose:

| App command | Value | Notes |
|-------------|-------|-------|
| `massageAllOnOff` | `0x4000000` | Toggle all massage on/off |
| `massageAll` (+) | `0x100` | Step all-massage intensity |
| `massageWave` | `0x10000000` | Massage wave/type (also sent for `massageWaistMinus`) |
| `massageWaist` | `0x400000` | Waist massage + |
| `intensityOne/Two/Three` | `0x80000` / `0x100000` / `0x200000` | Direct intensity levels |
| Set alarm | 16-byte frame `ED 80 03 hh mm repeats type … ~sum` (legacy/custom) | Sent 3× on legacy |
| Set current time | 10-byte frame `E7 80 01 yy mm dd hh mm ss ~sum` (legacy/custom) | Sent 3× on legacy |
| Status query | `[0x00, 0xB0]` | New OKIN only; light/massage status |

Legacy beds also push status notifications on FFE4 (frame lengths 10/16/20)
carrying massage time remaining and under-bed light state — unparsed by the
integration today.

### L600 Model Notes

The app's L600 model definition: manual controls HEAD/FOOT only, presets
Zero-G / Anti-Snore / Lounge / TV-Read, **1 memory position**, massage
(head/foot/type/timer), light, alarm. No tilt, lumbar, or Hi-Lo hardware.

## Command Timing

From app disassembly analysis (Malouf Base / Lucid Base):

| Protocol | Repeat Interval | Max Repeats |
|----------|----------------|-------------|
| Legacy OKIN (FFE5) | 150ms | 85 |
| New OKIN (Nordic) | 100ms | 55 |

The app supports multiple protocols with automatic detection:
1. **Legacy OKIN (FFE5/FFE9)** - 9-byte packets
2. **Custom OKIN (62741523)** - 10-byte packets
3. **New OKIN (Nordic UART)** - 8-byte packets
4. **Richmat WiLinke (FEE9)** - 5-byte packets
