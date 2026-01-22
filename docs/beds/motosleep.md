# MotoSleep

**Status:** 🔄 Works, improvements in progress

**Credit:** Reverse engineering by waynebowie99 and [Richard Hopton/smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Beds with HHC (Hangzhou Huaci) controllers
- Power Bob
- Device names start with "HHC" (e.g., `HHC3611243CDEF`)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MotoSleep](https://play.google.com/store/apps/details?id=com.HHC.MotoSleep) | `com.HHC.MotoSleep` |
| ✅ | [Power Bob for Adjustable Bed](https://play.google.com/store/apps/details?id=com.HHC.PowerBob) | `com.HHC.PowerBob` |

## Features
| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ✅ (2 slots) |
| Massage | ✅ |
| Under-bed Lights | ✅ |
| Zero-G / Anti-Snore | ✅ |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Format:** 2 bytes `[0x24, ASCII_char]` (0x24 = '$')

### Motor Commands

| Command | Bytes | ASCII | Description |
|---------|-------|-------|-------------|
| Head Up | `24 4B` | `$K` | Raise head |
| Head Down | `24 4C` | `$L` | Lower head |
| Feet Up | `24 4D` | `$M` | Raise feet |
| Feet Down | `24 4E` | `$N` | Lower feet |
| Neck Up | `24 50` | `$P` | Raise neck |
| Neck Down | `24 51` | `$Q` | Lower neck |
| Lumbar Up | `24 70` | `$p` | Raise lumbar |
| Lumbar Down | `24 71` | `$q` | Lower lumbar |

### Preset Commands

| Command | Bytes | ASCII |
|---------|-------|-------|
| Home/Flat | `24 4F` | `$O` |
| Zero-G | `24 54` | `$T` |
| Anti-Snore | `24 52` | `$R` |
| TV | `24 53` | `$S` |
| Memory 1 | `24 55` | `$U` |
| Memory 2 | `24 56` | `$V` |
| Save Memory 1 | `24 5A` | `$Z` |
| Save Memory 2 | `24 61` | `$a` |
| Save Zero-G | `24 59` | `$Y` |
| Save Anti-Snore | `24 57` | `$W` |
| Save TV | `24 58` | `$X` |

### Other Commands

| Command | Bytes | ASCII |
|---------|-------|-------|
| Lights Toggle | `24 41` | `$A` |
| Massage Head | `24 43` | `$C` |
| Massage Foot | `24 42` | `$B` |
| Massage Stop | `24 44` | `$D` |
| Massage Head Up | `24 47` | `$G` |
| Massage Head Down | `24 48` | `$H` |
| Massage Foot Up | `24 45` | `$E` |
| Massage Foot Down | `24 46` | `$F` |
| Massage Head Off | `24 4A` | `$J` |
| Massage Foot Off | `24 49` | `$I` |
| Sync | `24 7A` | `$z` |

## Command Timing

From app disassembly analysis:

- **Motor commands:** Single command per button press (no repeat interval)
- **Pattern:** Send command on press, motors stop when no command received
- **Stop command:** Not required (controller handles stop)

## Supported Bed Model Variants

From app analysis, dedicated support for:
- WR1140
- WRS14 series (WRS14Dmm, WRS14ms)
- WRS16ms, WRS18ms, WRS20ms, WRS23ms
