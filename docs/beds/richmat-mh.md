# Richmat app profiles (Revive Control, Best Mattress, Blvd Home, HARMONY, Idealbed)

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled by the five apps below. Each app's model catalog decides which
  motors, pages and buttons a model has.
- Models are named by the first four characters of the raw Bluetooth name
  (for example `7IRM…` selects `7irm`).

## Apps

| Analyzed | App | Package ID | Bed type |
|----------|-----|------------|----------|
| ✅ | [Revive Control](https://play.google.com/store/apps/details?id=com.richmat.revive3) 1.0.26 | `com.richmat.revive3` | `richmat_revive` |
| ✅ | [Best Mattress](https://play.google.com/store/apps/details?id=com.richmat.best_mattress) 1.1.1 | `com.richmat.best_mattress` | `richmat_best_mattress` |
| ✅ | [Blvd Home](https://play.google.com/store/apps/details?id=com.richmat.blvd_home) 1.0.1 | `com.richmat.blvd_home` | `richmat_blvd_home` |
| ✅ | [HARMONY](https://play.google.com/store/apps/details?id=com.richmat.harmony) 1.0.0 | `com.richmat.harmony` | `richmat_harmony` |
| ✅ | [Idealbed](https://play.google.com/store/apps/details?id=com.richmat.idealbed) 2.4.2 | `com.richmat.idealbed` | `richmat_idealbed` |

- The five apps share one BLE library. Their model catalogs, page gates and a
  few callbacks differ, so each app is its own explicit bed type.
- These profiles are opt-in: the shared Richmat services and names never select
  them automatically, and existing [Richmat](richmat.md) or
  [RMControl](rmcontrol.md) entries are not changed.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Two motors; the model decides which exist (KEEP then STOP) |
| Position Feedback | ⚠️ VER1 angle replies update the angle numbers; **Reached position** reports memory arrival |
| Presets / Memory | ✅ Standard presets and memory slots from the model's catalog |
| Massage | ✅ App-labelled buttons; VER1 head/foot intensity numbers |
| Lights | ✅ RGB light or colour action, light timeout, button-light page |
| Smart Set Lock | ✅ Toggle button and state |
| Snore Intervention | ✅ Off, anti-snore or zero gravity (the model's list) |
| Detection | ✅ Start/stop and per-device results |
| Alarms / Aroma / Waist Mattress | ✅ Actions and entities where the model's pages exist |

## Protocol Details

**Format:** bed frames `6e 01 M C SUM`; mattress frames `5e … SUM`

- `M` is the app's `txMode` byte: 0 in the app's single-device group, the only
  group a Home Assistant entry has.
- `SUM` is the low byte of the sum of the preceding bytes.
- Mattress frames use the `5e` header with the same additive checksum and no
  mode byte.
- Literal query frames are decoded and their sum recomputed before sending.

### GATT Selection

The controller follows the app's GATT selection (Nordic UART, then the fee9 and
ffe0/fff0 maps, then a fallback service) and keeps the characteristic's write
type. The fallback skips the generic access and attribute services
(`00001800`, `00001801`).

| Order | Service | Write | Notify |
|-------|---------|-------|--------|
| N1 | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| W1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` |
| W2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` |
| W3 | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` |
| W4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` |

### Connection Setup

After subscribing it waits 300 ms, sends the version query, waits 300 ms and
sends the version's initialization list with 300 ms between tasks.

| Step | VER0 | VER1 |
|------|------|------|
| Version query | `6e9a000008` | `6e9a000008` |
| Exit one-minute | `6e02010071` | `6e02010071` |
| Alarm | `6e08010178` | `6e08010178` |
| LED | `6e0a000179` | `6e0a000179` |
| Aroma | `6e1a000088` | `6e1a000088` |
| Mattress | `5e1a000190` (sent as `5e1a000179`) | same |
| Waist mattress | `5e1b00017a` | `5e1b00017a` |
| Snore | `6e2100008f` | `6e2100008f` |
| Speech | `6e22000090` | `6e22000090` |
| Detection | `6e9ac000c8` | none |
| Motor mode | none | `6e9a100018` |
| Motor angles | none | `6e9a300139`, `6e9a30023a`, `6e9a30033b`, `6e9a30043c` |
| Massage query | none | `6e9aa000a8` |
| Button-light lock query | none | `6e9ab000b8` |

When a VER1 reply mounts the alarm call page during setup, the phone clock is
sent once (as the app's alarm call page does on creation).

## Detection / Setup

1. Add the bed manually and choose the app your phone uses (for example
   **Revive Control app (Richmat)**). Motor count is fixed at two; the model
   decides which motors exist.
2. Leave the protocol variant on `auto` to apply the app's name rule: the first
   four characters of the raw Bluetooth name, lowercased, name the model
   (`7IRM…` selects `7irm`). The raw name is stored at setup.
3. Choose an explicit model variant (`model_<id>`) when the app would ask:
   names starting with `QRRM`, Idealbed names starting with `Cool Touch`, or a
   name with no live model. The variants list exactly the app's picker, setup
   wizard and manual model routes; Idealbed's manual dialog accepts any valid
   model identifier, so every Idealbed model is offered. Labels are the app's
   where the analysis recorded them, otherwise the model identifier.

- The setup and options forms report a name the app cannot resolve on the
  protocol variant field.
- Each side of a two-address pair keeps its own app and model; unpair before
  changing them.

## Connection and pages

- **VER0** (no `6e900001ff` reply) shows the legacy pages built from the model's
  function list, plus pages added by replies: alarm, LED or button-light,
  aroma, snore and detection.
- **VER1** shows the model's entity pages (motors with angle sliders, massage
  with intensity sliders, memories), the alarm call page and the LED page.
  VER1 keeps only the flags of the most recent reply, as the app does.
- The **waist mattress** page appears after a powered `5e1b` table reply.

The replies are stored as a capability snapshot; a change reloads the entities
after the link is released. Revive Control, Blvd Home and HARMONY switch to the
VER1 pages on the first initialization reply; Best Mattress and Idealbed switch
on the version reply.

## Controls

| Surface | Entities | Frames |
|---------|----------|--------|
| Motors | Covers (KEEP at the control's interval, then STOP 120 ms after release) | `6e 01 M C SUM`, STOP `6e 01 M 6e SUM` |
| Presets, memories, massage, motor-page buttons | Standard presets and memory slots, app-labelled buttons | Tap: one frame, STOP 120 ms later |
| LED page | Colour (RGB light when the motor page has the light toggle, else the colour action), light timeout 0–300 s (0 = always on) | `6e0c ff R s 6e0d G B s`, `6e 0b HH LL` |
| Button-light page | Colour as above, timeout (Blvd Home: 0–15 min); **Button light off** only in Revive Control and Best Mattress, the apps with an emitting OFF button | as above, OFF `75` |
| Smart set lock | **Toggle smart set lock** button, **Smart set lock** state | `6e 01 M 84` once |
| Snore intervention | Select: off, anti-snore, zero gravity (the model's list) | `6e 13 M code` |
| Detection | Start/stop buttons, **Detection** sensor with per-device results | `6e88c210c8`, `6e88c220d8` |
| VER1 angles | Back/foot/pillow angle numbers in the model's range | `6e 88 (30\|bits<<2) angle`, 100 ms after release |
| VER1 massage intensity | Head/foot intensity numbers (both zones sent) | `6e 88 a0 ((foot<<3)\|head)` |
| VER1 motor mode | Select (left/right or mode 1–3) | `6e 88 (10\|bits<<2) 00` |
| VER1 memory arrival | **Reached position** sensor | `6e904` reply |
| Waist mattress | Mode select, per-side heat, pressure and duration selects, per-side alarm sensors | `5e 03 cmd value SUM` |

- The light pages write only colour and timeout. The motor page's light toggle
  is the only on/off the apps send, so a model with it gets an RGB light (on/off
  is the toggle) and a model without it sets the colour with
  `richmat_mh_light_color` instead of a light that could not turn off.
- The light-page lock switch state is shown as **Smart light lock**; these apps
  never send its command.
- Alarm, aroma, waist alarms and light colour are actions (below).

## Commands

Motor, preset, memory, massage and page-button opcodes are per model: they come
from the generated catalog
[`richmat_mh_catalog.py`](../../custom_components/adjustable_bed/richmat_mh_catalog.py)
(app route, kind, page, app label, opcode, and KEEP interval or 0 for a single
tap). Each is sent as `6e 01 M C SUM`. The fixed frames below are shared.

### Fixed Opcodes

| Command | Opcode | Frame |
|---------|--------|-------|
| STOP | `6e` | `6e 01 M 6e SUM` |
| Button light off (Revive Control, Best Mattress) | `75` | `6e 01 M 75 SUM` |
| Smart set lock toggle | `84` | `6e 01 M 84 SUM`, once |

### VER1 Entity Frames

| Command | Frame | Values |
|---------|-------|--------|
| Motor angle target | `6e 88 (30\|bits<<2) angle SUM` | Absolute angle |
| Massage intensity | `6e 88 a0 ((foot&7)<<3 \| head&7) SUM` | Both zones at once |
| Motor mode | `6e 88 (10\|bits<<2) 00 SUM` | LEFT 1, RIGHT 2, Mode1 1, Mode2 2, Mode3 3 |

### Lights

| Command | Frame | Values |
|---------|-------|--------|
| Colour | `6e 0c ff R s1` + `6e 0d G B s2` | One 10-byte write, RGB 0-255 |
| Light timeout | `6e 0b HH LL SUM` | Seconds; zero or less sends `ff ff` (always on). The entity-page variant replaces `HH` with `txMode` |

### Snore and Detection

| Command | Frame |
|---------|-------|
| Snore intervention | `6e 13 M code SUM` (code 0 turns it off) |
| Start detection | `6e88c210c8` |
| Stop detection | `6e88c220d8` |

### Alarm

| Command | Frames |
|---------|--------|
| Countdown alarm | `6e 05 lo slot SUM`, then `6e 06 hi action SUM` (minutes, low and high byte) |
| Cancel alarm (single-slot models) | `6e05000073`, then `6e06000074` |
| Delete slot (three-slot models) | `6e 05 00 slot SUM`, then `6e 06 00 00 SUM` |
| Clock (three-slot models) | `6e 13 H M SUM`, then `6e 14 S ff SUM` |

The countdown is `(target − now) mod 1440` minutes; zero becomes 1440.
Three-slot alarms recall M1/M2/M3 with `2e`/`2f`/`30`.

| Alarm massage choice | Opcode |
|----------------------|--------|
| Head | `4c` |
| Foot | `4e` |
| Head and foot (two choices) | `5d` |
| Head and foot intensity increase | `34` |

| Position | Opcode | With head | With foot | With head and foot |
|----------|--------|-----------|-----------|--------------------|
| TV | `58` | `7a` | `7d` | `77` |
| Zero gravity | `45` | `7c` | `7f` | `79` |
| Anti-snore | `46` | `7b` | `7e` | `78` |
| Lounge | `59` | `ad` | `ae` | `ac` |
| M1 | `2e` | `82` | `83` | `81` |
| M2 | `2f` | `a7` | `a8` | `a6` |
| M3 | `30` | `aa` | `ab` | `a9` |

### Aroma

`6e fn (b0+b1) (b2+b3) SUM` over the value's little-endian 32-bit bytes, with
`fn` `1b` (mode 2 startup, minutes), `1c` (mode 3 startup, minutes) and `1d`
(mode 3 pause, hours).

### Waist Mattress

| Command | Frame |
|---------|-------|
| Control | `5e 03 cmd value SUM` |
| Mode | cmd `01`, value 0-9: off, left/right/both relax, wake, decompress |
| Alarm save | `5e 03 0b repeat side intensity H M nowH nowM SUM` |

| Side | Heat | Pressure | Duration | Alarm cancel | Side byte |
|------|------|----------|----------|--------------|-----------|
| Left | `02` | `05` | `08` | `10` | `01` |
| Right | `03` | `06` | `09` | `11` | `02` |
| Both | `04` | `07` | `0a` | `12` | `03` |

| Setting | Values |
|---------|--------|
| Heat | off 0, 2 hours 1, 4 hours 2, 8 hours 3 |
| Pressure | level 1-3 = 1-3 (no off) |
| Duration | 15 / 20 / 30 minutes = 1 / 2 / 3 (no off) |
| Alarm repeat | once `01`, daily `02` |

## Actions

- `adjustable_bed.richmat_mh_alarm`: `enabled`, `time` (local, minute
  precision), `position` and `massage` choices from the model's alarm page,
  `slot` (1–3) for three-slot models. The bed receives the minutes until the
  next occurrence. A position with a massage uses the app's combined opcode;
  two massages become head-and-foot; a pair the app cannot express is rejected.
  Three-slot models recall M1/M2/M3 per slot.
- `adjustable_bed.richmat_mh_aroma`: mode 2 startup (1–60 min), mode 3 startup
  (1–60 min) and mode 3 pause (1–12 h), sent as the app's three frames.
- `adjustable_bed.richmat_mh_waist_alarm`: `waist_side`, `enabled`, `time`,
  `repeat` (once/daily), `intensity` (1–3). Saving includes Home Assistant's
  current local time, as the app does.
- `adjustable_bed.richmat_mh_light_color`: `rgb_color`, written as the light
  page's 10-byte colour frame. Available when the LED or button-light page is
  shown.

Alarm countdowns and the waist alarm's current time are read per bed, right
before its frames are built. Connection setup (version query and initialization
list) finishes before any command runs or a sequential pair releases the link.

See [Actions](../SERVICES.md).

## Notifications

| Reply | Meaning |
|-------|---------|
| `6e900001ff` | VER1 |
| `6e09010078` / `6e09010179` | Alarm page / multi-slot alarm page |
| `6e0e00037f` | LED page |
| `6e1a000189` | Aroma page |
| `6e90c101c0` | Detection page |
| `6e90c210d0` / `6e90c220e0` | Detection started / stopped |
| `6e07010177` / `6e07010278` | Alarm set / deleted |
| `6e23a06e9f` | Stop music (classified by Revive Control, Blvd Home and HARMONY only) |
| Prefix `6e901` / `6e903` / `6e90a` | Motor mode / motor angle / massage (the button-light lock prefix is identical and shadowed) |
| Prefix `6e904` / `6e905` | Memory arrival / error |
| Prefix `6e90c` | Detection result |
| Prefix `6e21` | Snore |
| `6e 23 value function SUM` | Callback: function `84` is the smart set lock (`00` locked, `01` unlocked); `21` is snore |
| `5e1b…` (powered 31-byte table) | Waist mattress state |

- Detection results name the device type (`3` motor, `4` massager, `5` UBL, `6`
  USB) and status (`0` error, `1` pass, `2` control box error, `3`
  unplugged).
- VER1 motor-angle replies set the matching angle number, clamped to its
  slider range; massage replies set the head/foot intensity numbers.
- Replies are matched in a shared lowercase-hex buffer, reset when a new `6e` or
  `5e` frame starts and the buffer exceeds 100 characters.

## Command Timing

| Operation | Timing |
|-----------|--------|
| Version query and initialization tasks | 300 ms apart |
| STOP after release or a single tap | 120 ms |
| VER1 angle target | 100 ms after the slider release |
| Alarm frames | 300 ms apart (150 ms for three-slot save/delete) |
| Aroma frames | 150 ms apart |

## Regenerating the catalog

`tools/generate_richmat_mh_catalog.py` builds `richmat_mh_catalog.py` from the
machine-local frozen reports (hash-pinned). It reads them from `--phase4-dir`,
`$ADJUSTABLE_BED_PHASE4_DIR`, `disassembly/output/phase4-early` in the checkout,
or the main checkout of a linked worktree; `--check` verifies the committed file
and reports missing inputs instead of failing with a traceback.

## Notes

### Not implemented

- The auxiliary FA endpoint is a separate HJ_Bed Wi-Fi sleep sensor with cloud
  provisioning, firmware updates and JSON telemetry; it is out of scope.
- Speech/voice pages, the HARMONY video demo, phone music, multi-device grouping
  and the ordinary mattress page (no constructor enables it) are excluded. The
  ledger records the evidence for each.

### Hardware validation wanted

Real users should confirm model selection by name, KEEP/STOP behavior, alarm
countdown semantics, LED timeout units and the waist mattress controls after a
beta or release.

### Analysis provenance

APK Protocol Audit row055 (formal cluster-020): every package report and the
cluster reconciliation are accepted. The
[disposition ledger](../apk-analysis/dispositions/row055-richmat-cluster.md)
accounts for every inventory entry.
