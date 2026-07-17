# Sleepy's Elite (MFRM)

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) and [SethCalkins](https://github.com/SethCalkins) (BOX25 Star, ported from [ha-dewertokin-bed](https://github.com/sethcalkins/ha-dewertokin-bed))

## Known Models

- MFRM Sleepy's Elite adjustable beds
- Mattress Firm adjustable beds using the Sleepy's Elite app
- DewertOkin BOX25 Star controller beds (BLE name: `Star*`)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy) | `com.okin.bedding.sleepy` |
| ✅ | Adjustable Comfort M1X12 | `com.starcode.adjustablem1x12` |
| ✅ | AdjustableM5X4 / AdjustableM5X5 | `com.starcode.abm5_4` / `com.starcode.abm5_5` |
| ✅ | MFRM Luxe / Ultra | `com.okin.bedding.luxe` / `com.okin.bedding.ultra` |

## Protocol Variants

The Sleepy's Elite app supports multiple control box types. This integration implements three BLE protocols:

`SLEEPSTAR` is not one of these variants. It is the SleepSpa S9000AI CB37
sleep-monitor protocol, which tunnels StarCode inside an additional envelope.
Use the separate [SleepSpa S9000AI protocol](sleepstar.md) for that device name.

| Variant | Packet Size | Checksum | Lumbar | Neck | Lights | Massage | Positions | Service UUID |
|---------|-------------|----------|--------|------|--------|---------|-----------|--------------|
| BOX15 | 9 bytes | Yes | ✅ | ❌ | ❌ | ❌ | ❌ | FFE5 |
| BOX24 | 7 bytes | No | ❌ | ❌ | ❌ | ❌ | ❌ | 62741523 (OKIN 64-bit) |
| BOX25 (StarCode or legacy) | 2-20 bytes | No | ✅ | ✅ | ✅ | ✅ | ✅ | 6e400001 (Nordic UART) |

**Protocol Selection:**

- If your device name starts with **"Star25"** and advertises Nordic UART, use BOX25. Auto mode reads Device Information `2A29`: text containing `star` selects StarCode; any other/missing value selects legacy CB25. A manual dialect override is available.
- If your bed has **lumbar control** (but no Star name), use the BOX15 variant
- If your bed has **OKIN 64-bit service UUID** (62741523-...), use BOX24
- Octo Star2 beds also use `Star2` names, but they advertise the Octo Star2 UUID and are detected as Octo first
- When in doubt, try BOX24 first (simplest protocol)

## Features

| Feature | BOX15 | BOX24 | BOX25 Star |
|---------|-------|-------|------------|
| Motor Control | ✅ | ✅ | ✅ |
| Lumbar Motor | ✅ | ❌ | ✅ |
| Neck Tilt Motor | ❌ | ❌ | ✅ |
| Position Feedback | ❌ | ❌ | ✅ (0-100%) |
| Direct Position Control | ❌ | ❌ | ✅ (protocol: head/feet/lumbar) |
| Memory Presets | ❌ | ❌ | ✅ (2 slots) |
| Memory Programming | ❌ | ❌ | ✅ |
| Flat Preset | ✅ | ✅ | ✅ |
| Zero-G Preset | ✅ | ✅ | ✅ |
| Anti-Snore Preset | ❌ | ❌ | ✅ |
| Lounge Preset | ❌ | ❌ | ✅ |
| Under-Bed Lights | ❌ | ❌ | ✅ (on/off and level 0-6) |
| Massage | ❌ | ❌ | ✅ (toggle/off, 3 wave modes, timer) |
| Massage Intensity | ❌ | ❌ | ✅ (head/foot steps and combined level 0-7) |

## Protocol Details

### BOX15 Protocol (9-byte packets with checksum)

**Service UUID:** `0000FFE5-0000-1000-8000-00805F9B34FB`

**Write Characteristic:** `0000FFE9-0000-1000-8000-00805F9B34FB`

**Packet Structure:**

```text
[0]    Header1: 0xE6
[1]    Header2: 0xFE
[2]    Prefix:  0x2C
[3]    Motor command
[4]    Preset data (byte 4)
[5]    Reserved: 0x00
[6]    Preset data (byte 6)
[7]    Reserved: 0x00
[8]    Checksum: (~sum(bytes[0:8])) & 0xFF
```

**Motor Commands (byte 3):**

| Command | Hex | Description |
|---------|-----|-------------|
| STOP | 0x00 | Stop all motors |
| HEAD UP | 0x02 | Raise head |
| HEAD DOWN | 0x01 | Lower head |
| FOOT UP | 0x08 | Raise foot |
| FOOT DOWN | 0x04 | Lower foot |
| LUMBAR UP | 0x20 | Raise lumbar |
| LUMBAR DOWN | 0x10 | Lower lumbar |

**Preset Commands (byte 4 + byte 6):**

| Preset | Byte 4 | Byte 6 |
|--------|--------|--------|
| Flat | 0x00 | 0x10 |
| Zero-G | 0x20 | 0x00 |

**Example - Move Head Up:**

```text
E6 FE 2C 02 00 00 00 00 [checksum]
```

### BOX24 Protocol (7-byte packets)

**Service UUID:** `62741523-52F9-8864-B1AB-3B3A8D65950B` (OKIN 64-bit)

**Write Characteristic:** `62741625-52F9-8864-B1AB-3B3A8D65950B`

**Packet Structure:**

```text
[0]    Header1: 0xA5
[1]    Header2: 0x5A
[2]    Reserved: 0x00
[3]    Reserved: 0x00
[4]    Reserved: 0x00
[5]    Command type: 0x40
[6]    Motor/Preset command
```

**Motor Commands (byte 6):**

| Command | Hex | Description |
|---------|-----|-------------|
| STOP | 0x00 | Stop all motors |
| HEAD UP | 0x02 | Raise head |
| HEAD DOWN | 0x01 | Lower head |
| FOOT UP | 0x06 | Raise foot |
| FOOT DOWN | 0x05 | Lower foot |

**Preset Commands (byte 6):**

| Preset | Hex |
|--------|-----|
| Flat | 0xCC |
| Zero-G | 0xC0 |

**Example - Move Head Up:**

```text
A5 5A 00 00 00 40 02
```

### BOX25 Protocol (Nordic UART)

**Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` (Nordic UART)

**Write Characteristic (TX):** `6E400002-B5A3-F393-E0A9-E50E24DCCA9E`

**Notify Characteristic (RX):** `6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

**BLE Device Name:** Starts with `Star25` (e.g., `Star252201154718`)

**Integration motor surface:** `head`, `feet`, `lumbar`, `tilt`

**Integration direct-position surface:** `head` and `feet` sliders/services. The protocol also reports lumbar position and accepts direct lumbar position commands, but neck tilt does not currently have a protocol-backed position zone.

The Sleepy's app first classifies `Star25...` as BOX25, reads manufacturer name
characteristic `2A29`, then promotes it to `BOX25_STAR` only when the decoded
text starts with `star`. The M1X12/M5X5 implementations corroborate the same
runtime split using a case-insensitive `contains("star")` test. Fixed F23 and
kneading product identifiers (`STAR254203/4205/4255/4256/4257`,
`STAR255401/5402/5403`) are StarCode-only.

`BOX25_STAR` uses StarCode for every motor, preset, light, and massage action:

```text
5A 01 03 10 [category] [command] A5
```

Normal commands are written to Nordic UART without response. The integration
sends the proven `5A 0B 00 A5` wake frame once **with response**, before enabling
RX notifications, exactly matching the Sleepy's app session. There is no
application-level delay after wake. The legacy
`00 D0` / `00 B0` subsystem initializers and `05 02`, `08 02`, and `04 E0`
command families do not apply to `BOX25_STAR`.

#### Motor Commands (category `0x30`)

| Command | Action |
|---------|--------|
| `0x00` | Head up |
| `0x01` | Head down |
| `0x02` | Foot up |
| `0x03` | Foot down |
| `0x06` | Lumbar up |
| `0x07` | Lumbar down |
| `0x0A` | Neck tilt up |
| `0x0B` | Neck tilt down |
| `0x0F` | Stop |

#### Preset and Memory Recall Commands (StarCode, 7 bytes)

The Adjustable Comfort M1X12 app uses StarCode framing for presets:

```text
5A 01 03 10 30 [command] A5
```

| Preset | Command |
|--------|---------|
| Flat | 0x10 |
| Zero Gravity | 0x13 |
| Anti-Snore | 0x16 |
| Lounge/Reading | 0x17 |
| Memory 1 | 0x1A |
| Memory 2 | 0x1B |

Each preset frame is sent three times at 100 ms intervals, followed 100 ms
later by the StarCode commit frame `5A 01 03 10 30 0F A5`. Without that final
frame the bed remains armed until STOP or BLE disconnect (issue #372).

Saving Memory 1/2 uses command `0x94`/`0x95`, respectively. The app models this
as a long press: it repeats the save frame 110 times at 100 ms intervals and
does not append the preset commit frame.

#### Position Commands

```text
5A F0 03 [zone] [position 0-100] 00 A5
```

Zones are `0x00` for head, `0x01` for foot, and `0x02` for lumbar. The status
query is `5A B0 00 A5`.

#### Lighting Commands (category `0x30`)

| Command | Action |
|---------|--------|
| `0x71` | Toggle under-bed light |
| `0x73` | Turn under-bed light on |
| `0x74` | Turn under-bed light off |

Direct brightness uses `5A E0 04 00 [level 0-6] 00 00 A5`.

#### Massage Commands

| Category | Command | Action |
|----------|---------|--------|
| `0x30` | `0x52` / `0x53` / `0x54` | Massage modes 1-3 |
| `0x30` | `0x5A` | Toggle massage on/off |
| `0x30` | `0x6F` | Massage off |
| `0x30` | `0x60` / `0x61` | Head strength up/down |
| `0x30` | `0x62` / `0x63` | Foot strength up/down |
| `0x40` | `0x60` / `0x61` | Overall strength up/down |

The direct combined-intensity slider is normalized as 0-7 in the app. Zero is
encoded as zero; positive levels are encoded as 2-8:

```text
5A E0 04 06 [encoded] [encoded] 00 A5
```

The 10/20/30 minute timer maps to values 1/2/3:

```text
5A E0 04 07 [1-3] 00 00 A5
```

#### Legacy CB25 Runtime Dialect

When `2A29` is missing, unreadable, empty, or does not contain `star`, Auto mode
uses the legacy packet builders recovered from the same reachable BOX25 class:

```text
normal:   05 02 [32-bit key, big-endian] 00
extended: 04 E0 [subcommand] [value] [value2] 00
position: 03 F0 [zone] [position] 00
query:    00 B0 (massage/light), 00 D0 (motor position)
```

Movement keys are `1/2` head, `4/8` foot, `10/20` lumbar, `40/80` neck,
and zero for STOP. Preset keys are `08000000` flat, `00004000` TV,
`00001000` zero-G, `00008000` anti-snore, `00002000` lounge,
`00010000` memory 1, and `00040000` memory 2. The integration preserves the
same three-repeat plus STOP recall sequence and the proven long-press memory
programming behavior.

Legacy light on/off uses `04 E0 01 01/00 00 00`; toggle and wave modes use the
10-byte `08 02` family. Direct brightness, combined massage intensity, and the
timer use the same subcommands as StarCode without the `5A ... A5` wrapper.
Feedback uses the shared BOX25 parser below.

#### Notification Parsing

Both legacy `BOX25` and `BOX25_STAR` route Nordic UART RX notifications through
the same parser. A legacy `00 D0` position query and the StarCode
`5A B0 00 A5` query therefore produce the same 20-byte position packet family:

```text
A5 0D ... [head at byte 4] ... [foot at byte 6] ... [lumbar at byte 8] ...
```

Each motor position is clamped to the app's 0-100 range. Issue #372's captured
notification `A5 0D 11 01 16 00 00 ...` therefore reports head position 22.
Parsing is selected by this notification header, not by a pending-query token
or the runtime dialect.

`A5 0B` is the massage/status branch. Remaining duration is the big-endian
value `(byte[4] << 8) | byte[5]`; 1-600, 601-1200, and 1201-1800 seconds map to
the 10, 20, and 30 minute timer choices. The OEM parser consumes each BLE value
event directly and does not reassemble fragments.

## Checksum Calculation (BOX15 only)

The BOX15 protocol uses an inverted 8-bit sum (one's complement):

```python
checksum = (~sum(bytes[0:8])) & 0xFF
```

## Command Timing

From app disassembly:

- **Repeat Interval:** Continuous while button held
- **Pattern:** Send command repeatedly with ~100ms delay
- **Stop Required:** Yes, explicit stop after motor release
- **BOX25 Star normal write mode:** write without response
- **BOX25 Star wake:** one write with response before notifications, no app delay

## Detection

Sleepy's Elite beds are auto-detected by name plus BLE services:

- Device names starting with `star25` (case-insensitive) plus Nordic UART → BOX25, then `2A29` selects StarCode or legacy packets at connection time
- `ELEVATE*` plus Nordic UART → the separate [ELEVATE controller](star-elevate.md),
  never BOX25
- Device names starting with "star" without Nordic UART are treated as a low-confidence BOX25 match because Octo Star2 uses similar names
- Device names containing "sleepy" or "mfrm" (case-insensitive):
  - OKIN 64-bit service (62741523-...) → BOX24
  - FFE5 service (0000FFE5-...) → BOX15

**If auto-detection fails:**

1. Use nRF Connect app to scan your bed
2. If device name starts with "Star" → manually select BOX25 Star
3. If you see service `62741523-...` → manually select BOX24
4. If you only see service `0000FFE5-...` → manually select BOX15
5. If BOX24 doesn't work and your bed has lumbar → try BOX15

## Related Protocols

- **[DewertOkin](dewertokin.md)** - Different command format, uses handle writes
- **[Okin 64-bit](okin-64bit.md)** - Similar service UUID but different packet format
- **[Keeson](keeson.md)** - Same FFE5 service but different command encoding
