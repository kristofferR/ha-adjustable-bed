# Jensen

**Status:** ✅ Tested on JMC400 (motion, position reports, massage); JMC400 lights,
fan and memory recall, and every LinOn control, are implemented from app
evidence and await user confirmation.

## Known Models
- Jensen JMC400 (JMC 400), including its LinON Entry box
- Jensen LinOn beds named "Adjustable Bed" or "Jensen Bed" (LinonPI services)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Adjustable Sleep 2.0.37 (106) | `air.no.jensen.adjustablesleep` |
| ✅ | Adjustable Sleep 2.0.29 (98) | `air.no.jensen.adjustablesleep` |

The `air.` prefix is historical: both versions are React Native apps. The app
drives three bed families:

- **JMC400** beds use the `jensen` bed type (this page).
- **LinOn** beds ("Adjustable Bed"/"Jensen Bed" names) use the Svane bed type's
  Jensen LinOn profile; see [LinOn](#linon) below. 2.0.29 never wrote a LinOn
  frame; 2.0.37 does.
- **Linak**-based Jensen beds use the [Linak](linak.md) bed type.

See the [discovery ledger](jensen-disposition.md).

## PIN Authentication

Jensen beds require a 4-digit PIN. The integration uses **3060** as the default
PIN, which works for most beds.

**If commands don't work or the bed disconnects immediately:**
1. Go to **Settings** → **Devices & Services** → **Adjustable Bed**
2. Click the **gear icon** on your Jensen device
3. Enter your bed's correct PIN in the **Jensen PIN** field
4. Save and reload the integration

The bed answers the PIN frame; a rejection is logged as a warning.

## Features

| Feature | Supported |
|---------|-----------|
| Motor control (head, foot, both together) | ✅ |
| Position feedback | ✅ (pushed by the bed while it moves) |
| Go-to-position | ✅ |
| Flat | ✅ |
| Memory | ✅ 1 device slot on box type 4, otherwise 4 slots stored by Home Assistant |
| Massage | ✅ head, foot and wave, levels 0-10 (from the config report) |
| Light | ✅ levels 0-10 (from the config report) |
| Fan | ✅ levels 0-10 (from the config report) |

Massage, light and fan appear only when the bed's config report lists them. The
bed does not report their state, so Home Assistant shows what it last sent.

### Memory

The app keeps its memories in one of two places, chosen by the box type in the
config report:

- **Box type 4** has one memory slot on the device. Save and recall use the
  device commands.
- **Every other box type** keeps up to four favourites in the app as measured
  head and foot positions, and recalls them with a go-to command. Home
  Assistant does the same: saving reads the current position and stores it
  (surviving restarts), and recall moves the bed back there. A slot must be
  saved before it can be recalled.

App favourites can also replay massage, light and fan settings. Home Assistant
recalls only the position; use a scene or script for the rest.

### Movement feedback

After a single flat, memory or go-to frame the bed moves on its own. Home
Assistant keeps the command running until the bed's position reports show the
move has ended: reports stop arriving, or an idle report repeats the last
position. It then reads the final position once. A Stop or another command
interrupts the move and sends STOP. If the bed still reports motion after 90
seconds, STOP is sent and the command ends. With angle sensing disabled, the
frame is sent without waiting.

The bed pushes reports roughly every half second while it moves, so no queries
are sent mid-move.

## Protocol Details

**Service UUID:** `00001234-0000-1000-8000-00805f9b34fb`
**Characteristic UUID:** `00001111-0000-1000-8000-00805f9b34fb` (write without
response, notify)
**Checksum:** none
**Pairing:** not required

### Detection

- Service UUID `00001234`
- Device name containing `JMC400` (the app's rule); the integration also accepts
  names starting with `jmc`

### Session start

1. Subscribe to notifications on `0x1111`.
2. PIN frame `1E d1 d2 d3 d4` (each digit as a byte; `1E 03 00 06 00` for 3060).
3. Config request `0A 00 00 00 00`.

The integration additionally sends `10 FF 00 00 00 00` and waits for its
position reply. The app does not send it, but the bed answers it, and some beds
ignore the first flat after reconnect until they see a `0x10` frame
([#217](https://github.com/kristofferR/ha-adjustable-bed/issues/217)). The iOS
app sends STOP at the same point for the same effect.

### Motion (`0x10`)

`[0x10, flags, 00, 00, 00, 00]`, where flags combine one head bit and one foot
bit:

| Flag | Meaning |
|------|---------|
| `0x01` | Head up |
| `0x02` | Head down |
| `0x10` | Foot up |
| `0x20` | Foot down |

So `10 11` raises both and `10 21` raises the head while lowering the foot. The
app repeats a held frame every 300 ms and sends STOP `10 00 00 00 00 00` once on
release. Combined movement is available through the
`adjustable_bed.linak_move_simultaneously` action (back and legs only).

| Command | Bytes |
|---------|-------|
| Flat | `10 81 00 00 00 00` (sent once by the app) |
| Save device memory (box type 4) | `10 40 00 00 00 00` |
| Recall device memory (box type 4) | `10 80 00 00 00 00` |
| Go to position | `10 04 hL hH fL fH` |

### Position reports

`[0x10, state, head u16 LE, foot u16 LE]`, pushed while the bed moves and in
reply to `0x10` frames. `state` is the active motion flags (`00` idle, `FF` for
the query reply). The app treats the four position bytes as opaque and echoes
them in go-to frames, so both use the same byte order.

The app shows no position scale. The integration's percentage mapping uses
anchors measured on one JMC400
([#631](https://github.com/kristofferR/ha-adjustable-bed/issues/631)):

| Axis | Flat | Fully raised |
|------|------|--------------|
| Head | 30000 | 30804 |
| Foot | 30000 | 29369 (the value falls as the foot rises) |

Other units may differ slightly; values beyond the anchors clamp to 0 or 100 %.

### Config report (`0x0A`)

The reply to `0A 00 00 00 00`, for example `0A 05 03 08 01 75`. The app reads
bytes 2 and 4 by treating their decimal digits as hexadecimal (a byte of 16
means `0x16`); the integration does the same.

| Byte 2 bit | Feature |
|------------|---------|
| `0x01` | Head massage |
| `0x02` | Foot massage |
| `0x04` | Light |
| `0x10` | Fan |
| `0x40` | Under-bed light |

Byte 4 is the box type. Box type 4 has device memory; box type 2 also offers the
app's scripted comfort mode (see the ledger).

### Massage, light and fan

| Command | Bytes |
|---------|-------|
| Massage | `12 head foot wave H M` (levels 0-10, 0 = off) |
| Light | `13 02 level 00 H M` (level 0-10; every light kind uses output `02`) |
| Light off | `13 02 00 00 00 32` (a fixed frame in 2.0.37) |
| Fan | `14 level 00 H M 50` (level 0-10) |

`H M` is a timer. The Android app encodes it incorrectly (hexadecimal digits
parsed as decimal) and the iOS app ends up sending `00 00`. The #631 iOS capture
shows massage running with `00 00`, so the integration always sends `00 00` and
offers no timers.

## LinOn

LinOn beds expose the LinonPI services that [Svane](svane.md) beds use, but the
Jensen app writes its own one-byte frames to them. They use the **Svane /
Jensen LinOn** bed type with protocol variant **`jensen_linon`**. Bluetooth
setup selects it for new beds whose name contains "Adjustable Bed" or "Jensen
Bed" (the app's rule); `auto` keeps the Svane app profile, so existing entries
change only when you select `jensen_linon` in the options. Beds named "Jensen
Bed" are discovered by name; "Adjustable Bed" is too generic, so those beds are
found by their head service UUID.

All writes are with response. Head uses service `0000abcb`, foot `0000c258`
and the light `0000d07b`:

| Command | Characteristic | Bytes |
|---------|----------------|-------|
| Up / down (held) | `000001ac` up, `0000bae9` down, in the head or foot service | `01`, resent every 800 ms |
| Head and foot together | head, then foot direction characteristic, alternating | `01` every 800 ms |
| STOP | `000001ac` in the head, then the foot, service | `FF` |
| Flat | `0000143d` in the head, then the foot, service | `00` |
| Under-bed light | `0000a8e0` | on `01 00 00`, off `00 00 00` |

The app sends STOP after every movement and for every stop control. It repeats
the STOP pair until a 20 s cap, which Home Assistant does not copy. Home
Assistant also sends STOP when a flat is interrupted, because the motors keep
moving on their own after its frames.

The app offers more than reaches the bed. Its light intensity slider crashes
the app instead of writing, its favourite recall stalls before its first write,
and it never subscribes to position reports. Home Assistant therefore offers
no light level, memory or position feedback for LinOn beds.

## Limitations

- The position anchors come from one JMC400.
- JMC400 lights, fan and device memory have no hardware confirmation yet.
- Massage wave only has an effect while head or foot massage runs.
- LinOn control comes from app evidence only; no LinOn bed has been tested.
