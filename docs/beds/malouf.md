# Malouf

**Status:** ❓ Untested

**Credit:** Reverse-engineered from Malouf Base app v2.4.3

## Known Models

- Malouf
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
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Lumbar | ✅ |
| Head Tilt | ✅ |

## Protocol Variants

Malouf beds use two distinct protocols. The integration auto-detects which one your bed uses.

### NEW_OKIN (Nordic UART)

**Advertised Service UUID:** `01000001-0000-1000-8000-00805f9b34fb`
**Command Service:** Nordic UART (`6e400001-b5a3-f393-e0a9-e50e24dcca9e`)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 8 bytes `[0x05, 0x02, (cmd>>24)&0xFF, (cmd>>16)&0xFF, (cmd>>8)&0xFF, cmd&0xFF, 0x00, 0x00]`

### LEGACY_OKIN (FFE5)

**Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Format:** 9 bytes `[0xE6, 0xFE, 0x16, cmd&0xFF, (cmd>>8)&0xFF, (cmd>>16)&0xFF, (cmd>>24)&0xFF, 0x00, checksum]`
**Checksum:** `(~sum(bytes[0:8])) & 0xFF`

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
