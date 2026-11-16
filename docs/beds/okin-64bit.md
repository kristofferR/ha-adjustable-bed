# Okin 64-Bit

**Status:** ❓ Needs testing
**Ref:** Reverse-engineered from the `com.okin.bedding.adjustbed` APK

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Controllers

- `NORA_CON` / `NORACON` Mattress Firm controllers
- Nectar Premier Adjustable Base / Resident Adjustable Base (`OKIN-` followed by
  digits, Device Information manufacturer `DewertOkin GmbH`): Custom OKIN variant,
  pairing required, see [Custom OKIN pairing and session](#custom-okin-pairing-and-session)
- Other newer Okin controllers using the 10-byte `0x08 0x02` command frame

Reported `NORA_CON` / `NORACON` controllers use the Nordic variant. Their connected
Device Information Service reports manufacturer `IDT` and model `NORACON`.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Adjustable bed | `com.okin.bedding.adjustbed` |
| ⬜ | Resident Adjustable Base (iOS) | Connection sequence from an iPhone Bluetooth capture, not app analysis |

## Detection

| Signal | Value |
|--------|-------|
| Nordic service UUID | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Nordic write characteristic | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Custom OKIN service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` |
| Custom OKIN write characteristic | `62741525-52f9-8864-b1ab-3b3a8d65950b` |
| Name hint | `NORA_CON` |
| Device Information hint | Manufacturer `IDT`, model `NORACON` |

The Nordic UART service is shared by several bed protocols. Generic Nordic UART
devices still need disambiguation; `NORA_CON` / `NORACON` is the known
high-confidence signal for this 64-bit profile.

## Protocol Variants

| Variant | Service UUID | Write Characteristic | Mode |
|---------|--------------|----------------------|------|
| Nordic (`25_42_02`) | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-...` | Fire-and-forget |
| Custom OKIN (`36_33_04a`) | `62741523-52f9-8864-b1ab-3b3a8d65950b` | `62741525-...` | Wait-for-response, bonded link, session on connect |

## Custom OKIN pairing and session

The Custom OKIN variant requires BLE pairing and opens a session on every
connection. The Nordic variant does neither.

**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`

### Pairing

- Bond once while the base is in pairing mode (press the pairing button on the
  control box), then use **Pair Now** during setup or the pairing repair.
- Later connections encrypt the link with the stored bond. On an ESPHome
  Bluetooth proxy that means requesting pairing on each connection, which the
  integration does once a cached bond proves unreliable.
- Without encryption, Device Information reads fail with Insufficient
  Authentication and motor writes fail with ATT Insufficient Authorization (`0x08`).

### Session sequence

Sent after encryption and before any command, all as Write Request (with
response) to `62741525`, 120 ms after the previous response:

| Step | Action | Bytes |
|------|--------|-------|
| 1 | Enable notifications | CCCD of `62741625` |
| 2 | Clock (twice) | `E7 80 01 YY MM DD hh mm ss` |
| 3 | Session open (twice) | `08 02 E1 80 01` |

The clock frame carries the current **UTC** time as C `struct tm` fields, with
no checksum:

| Byte | Field |
|------|-------|
| `YY` | Years since 1900 (2026 = `7E`) |
| `MM` | Month, zero-based (November = `0A`) |
| `DD` | Day of month |
| `hh` `mm` `ss` | Hour, minute, second |

Example: 2026-11-15 21:50:53 UTC is `E7 80 01 7E 0A 0F 15 32 35`.

Encryption alone is not enough: without the session the base still answers
motor writes with Insufficient Authorization. A session write that fails with a
GATT security error starts the integration's pairing recovery.

## Packet Format

```text
[0x08, 0x02, cmd[0], cmd[1], cmd[2], cmd[3], cmd[4], cmd[5], cmd[6], cmd[7]]
```

- Header: `0x08 0x02`
- Command: 8-byte 64-bit bitmask value
- Checksum: none

The `0x08 0x02` header distinguishes this from 32-bit Okin/Keeson-style frames
such as `0x04 0x02` and `0x05 0x02`. Do not reuse 6-byte Okimat or 7-byte
Mattress Firm Nordic packets with this protocol.

## Commands

| Command | Bytes | Description |
|---------|-------|-------------|
| Stop | `00 00 00 00 00 00 00 00` | Stop all motors |
| Head Up | `00 00 00 01 00 00 00 00` | Raise head |
| Head Down | `00 00 00 02 00 00 00 00` | Lower head |
| Foot Up | `00 00 00 04 00 00 00 00` | Raise foot |
| Foot Down | `00 00 00 08 00 00 00 00` | Lower foot |
| Lumbar Up | `00 00 00 10 00 00 00 00` | Raise lumbar |
| Lumbar Down | `00 00 00 20 00 00 00 00` | Lower lumbar |
| Flat | `08 00 00 00 00 00 00 00` | Flat preset |
| Zero-G | `00 00 10 00 00 00 00 00` | Zero gravity |
| Lounge | `00 00 20 00 00 00 00 00` | Lounge preset |
| TV/PC | `00 00 40 00 00 00 00 00` | TV position |
| Anti-Snore | `00 00 80 00 00 00 00 00` | Anti-snore |
| Memory 1 | `00 01 00 00 00 00 00 00` | Go to memory 1 |
| Memory 2 | `00 04 00 00 00 00 00 00` | Go to memory 2 |
| Light Toggle | `00 02 00 00 00 00 00 00` | Toggle lights |
| Light On | `00 00 00 00 00 00 00 40` | Turn light on |
| Light Off | `00 00 00 00 00 00 00 80` | Turn light off |
| Massage Switch | `00 00 01 00 00 00 00 00` | Switch massage mode |
| Massage Stop | `02 00 00 00 00 00 00 00` | Stop massage |

## Command Timing

Held motor commands repeat at the configured pulse interval, followed by STOP.
The Resident app repeats a held frame about every 300 ms and sends STOP twice on
release.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot, Lumbar |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ (timer, wave modes) |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| BLE Pairing | Custom OKIN: ✅ Required; Nordic: ❌ Not required |

## Related Protocols

- [Okimat/Okin](okimat.md) uses the same custom OKIN service UUID on some models,
  but sends 6-byte `0x04 0x02` frames.
- [Mattress Firm 900](mattressfirm.md) also uses Nordic UART, but sends 7-byte
  `5A 01 ... A5` frames.
- [Okin CB35](okin-cb35.md) uses Nordic UART with a related 7-byte Star protocol.
- The [Adjustable bed (Lumbar) app](adjustable-lumbar.md) sends `0x08 0x02` frames on
  both of these services with its own name rule, timing and release STOPs. Select
  that explicit profile for beds controlled with that app; this bed type is unchanged.
