# BedTech

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- BedTech adjustable bases
- Dreams Sleepmotion 200i

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [BedTech](https://play.google.com/store/apps/details?id=com.bedtech) | `com.bedtech` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot, Leg/Pillow |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ (5 modes, timer) |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore / TV / Lounge | ✅ |
| Dual Base Support | ✅ |

## Protocol Details

**Service UUID:** `0000fee9-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `d44bc439-abfd-45a2-b575-925416129600`

> [!NOTE]
> BedTech shares the FEE9 service UUID and characteristic with Richmat WiLinke.
> Both use a similar 5-byte command format with `0x6E` prefix.
> QRRM controllers that advertise manufacturer ID `0x4C57` are identified as
> BedTech; QRRM controllers without that field remain Richmat (including the
> confirmed Casper RGB-light controller). Manual selection may still be required
> if an advertisement omits the manufacturer field.

### Packet Format

**Single Motor Commands:** `[0x6E, 0x01, 0x00, charCode, (charCode + 0x6F) & 0xFF]`
**Dual Base Commands:** `[0x6E, 0x01, 0x01, charCode, (charCode + 0x70) & 0xFF]`

Commands use ASCII character codes. The last byte is a simple checksum.

### Write Mode

The official app (react-native-ble-manager) uses **write-with-response**
(`BleManager.write`) for every command; its `writeWithoutResponse` wrapper is
never called. An earlier claim that the app used write-without-response (and
that write-with-response made lights/lounge fail) traced back to issue #243,
whose device turned out to be a misclassified Richmat QRRM — it never applied
to real BedTech hardware. Verified against BedTech 7.1.3 Hermes bytecode
(2026-07-10, issue #410).

### Command Repeats

The app repeats only motor position commands (`repeat: 1` in its command
table), re-sending every `repeat_ms` while the button is held. Presets,
memory, massage, and light commands are sent once. The app sends no stop
command on button release (BT6500 field reports still show `^` acting as
stop, so the integration keeps sending it).

## Commands

### Motor Control

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Head Up | `$` | `0x24` | Raise head |
| Head Down | `%` | `0x25` | Lower head |
| Foot Up | `&` | `0x26` | Raise foot |
| Foot Down | `'` | `0x27` | Lower foot |
| Both Heads Up | `)` | `0x29` | Raise both heads (app group `bothHeads`) |
| Both Heads Down | `*` | `0x2A` | Lower both heads |
| Pillow Up | `?` | `0x3F` | Raise pillow (BT6500; app group `pillow`) |
| Pillow Down | `@` | `0x40` | Lower pillow |
| Lumbar Up | `A` | `0x41` | Raise lumbar (BT6500; app group `lumbar`) |
| Lumbar Down | `B` | `0x42` | Lower lumbar |

> [!WARNING]
> Earlier versions of this document labeled `)`/`*` as "leg/pillow" and
> `?`/`@`/`A`/`B` as "both heads"/"both feet". The BedTech 7.1.3 command
> table maps `)`/`*` to `bothHeads`, `?`/`@` to `pillow`, and `A`/`B` to
> `lumbar` (pillow/lumbar exist only on BT6500). The integration's entity
> mapping still follows the old labels and needs a separate verification
> pass before being changed.

### Presets

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Flat | `1` | `0x31` | Flat position |
| Flat (alt) | `l` | `0x6C` | Secondary flat command (app `flat2`) |
| Zero-G | `E` | `0x45` | Zero gravity |
| Anti-Snore | `F` | `0x46` | Anti-snore |
| TV | `X` | `0x58` | TV position |
| Lounge | `e` | `0x65` | Lounge position |

### Model Capabilities (per BedTech 7.1.3)

The app gates features per user-selected model; command bytes are shared.

| Model | Light | Massage | Pillow/Lumbar | Dual (head2) | Presets |
|-------|-------|---------|---------------|--------------|---------|
| BT2000 | ❌ | ❌ | ❌ | ❌ | flat, zero-g, anti-snore |
| BT2500 | ❌ | head only | ❌ | ❌ | flat, zero-g, anti-snore |
| BT3000 | ✅ | head+foot | ❌ | ❌ | + TV |
| BT3000FH | ✅ | head+foot | ❌ | ✅ | + TV |
| BT6500 | ✅ | head+foot | ✅ | ❌ | flat, zero-g, anti-snore |
| BTX4 | ❌ | ❌ | ❌ | ❌ | flat, zero-g |
| BTX4FH | ❌ | ❌ | ❌ | ✅ | flat, zero-g |
| BTX5 | ✅ | head+foot | ❌ | ❌ | flat, zero-g, anti-snore |
| BTX5FH | ✅ | head+foot | ❌ | ✅ | flat, zero-g, anti-snore |

BT2000/BT2500/BTX4/BTX4FH owners have no BLE light command at all — the
app hides the button. `light2` (`_u`/`_<`) is only offered on BT3000FH.

### Memory

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Memory 1 Go | `.` | `0x2E` | Go to memory position 1 |
| Memory 1 Save | `+` | `0x2B` | Save memory position 1 |
| Memory 2 Go | `/` | `0x2F` | Go to memory position 2 |
| Memory 2 Save | `,` | `0x2C` | Save memory position 2 |

### Massage

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Massage On | `]` | `0x5D` | Turn massage on |
| Massage Off | `^` | `0x5E` | Turn massage off |
| Massage Switch | `H` | `0x48` | Switch massage mode |
| Head Massage Up | `L` | `0x4C` | Increase head massage |
| Head Massage Down | `M` | `0x4D` | Decrease head massage |
| Foot Massage Up | `N` | `0x4E` | Increase foot massage |
| Foot Massage Down | `O` | `0x4F` | Decrease foot massage |

#### Massage Modes

| Mode | Char | Hex |
|------|------|-----|
| Constant | `:` | `0x3A` |
| Pulse | `8` | `0x38` |
| Wave 1 | `I` | `0x49` |
| Wave 2 | `J` | `0x4A` |
| Wave 3 | `K` | `0x4B` |

#### Massage Timer

| Timer | Char | Hex |
|-------|------|-----|
| 10 min | `_` | `0x5F` |
| 20 min | `c` | `0x63` |
| 30 min | `a` | `0x61` |

### Lights

| Command | Char | Hex | Description |
|---------|------|-----|-------------|
| Light Off | `u` | `0x75` | Turn light off |
| Light Toggle | `<` | `0x3C` | Toggle light |

The official app exposes the light as a toggle button. There is no discrete
light-on command; `.` and `+` belong to memory slot 1.

## Dual Base Commands

For dual-base (King/Split King) beds, secondary controls use `_` prefix:
- Head2 Up: `_$`
- Head2 Down: `_%`
- Preset2 Flat: `_1`
- Light2 Toggle: `_<`
- Memory2 Go: `_/`

These use the dual base packet format with `0x01` in byte 2 and `+0x70` checksum.
