# Malouf/Lucid

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Malouf
- Lucid
- Structures

These are retail brands, not protocol identifiers. **Lucid L600 is not one
protocol.** Confirmed L600 devices include:

| Advertising/GATT evidence | Integration protocol | Packet format |
|---------------------------|----------------------|---------------|
| `Smartbed237...`, Nordic UART, OKIN manufacturer ID 89 / `DOT` payload | OKIN CB24 | 7 bytes |
| `OKIN-BLE...`, `BTCB` payload, connected FFE5/FFE9 | Malouf Legacy OKIN | 9 bytes |

The integration uses those BLE signals and connected services. It does not map
the string `L600` to either protocol.

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
| Memory Presets | ✅ (1 or 2 slots, configurable) |
| Save Memory Position | ✅ |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Lumbar | Optional, layout-dependent |
| Head Tilt | Optional, layout-dependent |
| Hi-Lo / Bed Height | Optional, layout-dependent |

## Physical Layout

Protocol and physical actuators are separate settings. Choose the layout that
matches the buttons on the physical remote:

- Back + legs (the confirmed two-motor L600 app profile)
- Back + legs + head tilt
- Back + legs + lumbar
- Back + legs + head tilt + lumbar
- Hi-Lo

The memory-position setting is separate too. The Lucid Base 1.3.3 L600 model
defines one memory position, while other models in the same command family use
two. Auto selects one slot for the two-motor layout and two otherwise; both can
be overridden in integration options.

## Hi-Lo Layout

Some OKIN/Malouf-protocol beds use a Hi-Lo actuator layout. Only entries set to
the Hi-Lo layout expose:

- Back
- Legs
- Head End Tilt
- Foot End Tilt
- Bed Height

`Bed Height` raises or lowers the whole frame by moving both lift columns
together. `Head End Tilt` and `Foot End Tilt` control the two columns
independently for lengthwise tilt.

## Protocol Variants

The Malouf/Lucid controller family implemented here uses two distinct protocols.
The integration auto-detects framing from BLE evidence, not from retail model.

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

### Save Memory Commands

| Action | Value |
|--------|-------|
| Save Memory 1 | `0x10000` |
| Save Memory 1 (`Smartbed238...` exception) | `0x80010000` |
| Save Memory 2 | `0x80040000` |

## Command Timing

From app disassembly analysis (Malouf Base / Lucid Base):

| Operation | Legacy OKIN | New OKIN |
|-----------|-------------|----------|
| Held motor command | Every 150ms | Every 150ms in the app UI |
| Preset recall | 3 queued acknowledged writes, no STOP | 1 write followed by STOP |
| Save memory | 85 writes at 150ms | 55 writes at 100ms |

The APK schedules the first save-memory write after one interval. At the end it
calls the literal string `stopCommand`, but the dispatcher only recognizes
`stopDriver`; therefore the official app does **not** transmit a final STOP for
memory saving. The integration intentionally matches that observed behavior.

Lucid Base 1.3.3's shared SDK also recognizes Custom OKIN and Richmat hardware,
but those are separate integration protocols. Their presence in the same app
does not make them Malouf Legacy/New OKIN packet variants.
