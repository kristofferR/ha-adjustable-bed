# Richmat app profiles (Revive Control, Best Mattress, Blvd Home, HARMONY, Idealbed)

**Status:** 🧪 Artifact-verified, hardware unverified. APK Protocol Audit row055
(formal cluster-020): every package report and the cluster reconciliation are
accepted. The [disposition ledger](../apk-analysis/dispositions/row055-richmat-cluster.md)
accounts for every inventory entry.

| App | Package | Version | Bed type |
|-----|---------|---------|----------|
| Revive Control | `com.richmat.revive3` | 1.0.26 | `richmat_revive` |
| Best Mattress | `com.richmat.best_mattress` | 1.1.1 | `richmat_best_mattress` |
| Blvd Home | `com.richmat.blvd_home` | 1.0.1 | `richmat_blvd_home` |
| HARMONY | `com.richmat.harmony` | 1.0.0 | `richmat_harmony` |
| Idealbed | `com.richmat.idealbed` | 2.4.2 | `richmat_idealbed` |

The five apps share one BLE library. Their model catalogs, page gates and a few
callbacks differ, so each app is its own explicit bed type. These profiles are
opt-in: the shared Richmat services and names never select them automatically,
and existing [Richmat](richmat.md) or [RMControl](rmcontrol.md) entries are not
changed.

## Setup

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

The setup and options forms report a name the app cannot resolve on the
protocol variant field. Each side of a two-address pair keeps its own app and
model; unpair before changing them.

## Connection and pages

The controller follows the app's GATT selection (Nordic UART, then the fee9 and
ffe0/fff0 maps, then a fallback service) and keeps the characteristic's write
type. After subscribing it waits 300 ms, sends the version query, waits 300 ms
and sends the version's initialization list with 300 ms between tasks.

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

The light pages write only colour and timeout. The motor page's light toggle is
the only on/off the apps send, so a model with it gets an RGB light (on/off is
the toggle) and a model without it sets the colour with
`richmat_mh_light_color` instead of a light that could not turn off. The
light-page lock switch state is shown as **Smart light lock**; these apps never
send its command. Alarm, aroma, waist alarms and light colour are actions (below).

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

## Regenerating the catalog

`tools/generate_richmat_mh_catalog.py` builds `richmat_mh_catalog.py` from the
machine-local frozen reports (hash-pinned). It reads them from `--phase4-dir`,
`$ADJUSTABLE_BED_PHASE4_DIR`, `disassembly/output/phase4-early` in the checkout,
or the main checkout of a linked worktree; `--check` verifies the committed file
and reports missing inputs instead of failing with a traceback.

## Not implemented

- The auxiliary FA endpoint is a separate HJ_Bed Wi-Fi sleep sensor with cloud
  provisioning, firmware updates and JSON telemetry; it is out of scope.
- Speech/voice pages, the HARMONY video demo, phone music, multi-device grouping
  and the ordinary mattress page (no constructor enables it) are excluded. The
  ledger records the evidence for each.

## Hardware validation wanted

Real users should confirm model selection by name, KEEP/STOP behavior, alarm
countdown semantics, LED timeout units and the waist mattress controls after a
beta or release.
