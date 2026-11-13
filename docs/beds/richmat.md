# Richmat

**Status:** ✅ Tested (Richmat and legacy BedTech routes); ❓ explicit BedTech 7.1.3 models; ❓ the RMControl, Richmat MH, HJBed, Eshine, classic app, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, L&P legacy app, Casper Base, Hush Base, SonicSleep and Luuna + profiles are APK-verified with hardware unverified

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), getrav, [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [Josh Pearce](https://github.com/joshpearce) (L&P MlRM)

One wire codec (`6E` frames ending in an additive `sum8`, over seven GATT
transports) serves the Richmat remote routes, BedTech, Leggett & Platt MlRM
beds, five families of catalog apps, the Eshine app, the legacy L&P app and the
Casper Base and Hush Base apps. This guide covers the codec first, then one
section per profile. See
[Protocol codecs and app profiles](../design/protocol-codecs.md) for the architecture.

## Known Models

Brands using Richmat actuators:

- L&P Adjustable Base (Leggett & Platt), including MlRM bases and the legacy
  app's [122 remote layouts](#lp-legacy-app)
- SVEN & SON
- [Casper Base](#casper-base) (PRO, MAX and stored products)
- [Galaxy Bed Control](#galaxy-bed-control), including Galaxy 26W-N
- MLILY
- Luuna / Luuna Rise
- BedTech adjustable bases, Dreams Sleepmotion 200i
- Jerome's
- Revive
- Idealbed
- Maxprime
- Milemont
- [Hush Base](#hush-base) (L200 to L500, S175 to S575 and SH split-head models)
- FLEXX MOTION
- Likimio
- Lunio Smart+
- [Good Vibe Sleep](#good-vibe-sleep) (dedicated app profiles and independent sleep sensors)
- Best Mattress Power Base
- Easy Rest
- Coaster Sleep
- Avocado Eco Base
- ENSO Sleep
- Dynasty DM9000
- Thomas Cole Sleep
- Forty Winks ActivFlex
- Superior
- Richmat HJA5 series
- Saatva
- Lucid L300
- Classic Brands
- Eshine (E6000)

The catalog apps name their layouts themselves: an RMControl product code, a
Richmat MH model (the first four characters of the Bluetooth name), an HJBed
or Good Vibe Sleep product or a classic app's four-character layout. Shared services and Bluetooth names do not identify a layout, so each
is an explicit choice (see [Choosing a profile](#choosing-a-profile)).

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [Richmat](https://play.google.com/store/apps/details?id=com.richmat.richmat) 4.2.0 (42006) | `com.richmat.richmat` | [Richmat 4.2.0](#richmat-420) |
| ✅ | [RMControl](https://play.google.com/store/apps/details?id=com.richmat.rmcontrol2) 21.3.7 | `com.richmat.rmcontrol2` | [RMControl](#rmcontrol); the [Richmat remotes](#richmat-remotes) cover the same beds |
| ✅ | [BedTech](https://play.google.com/store/apps/details?id=com.bedtech) 7.1.3 (14) | `com.bedtech` | [BedTech](#bedtech) |
| ✅ | [SleepFunction Bed Control](https://play.google.com/store/apps/details?id=com.richmat.sleepfunction) | `com.richmat.sleepfunction` | [Richmat remotes](#richmat-remotes) |
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) 2.3.25 | `com.richmat.lp2` | [L&P MlRM](#lp-mlrm), [Richmat remotes](#richmat-remotes) (QRRM) |
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp) 2.2.1 (13), legacy | `com.richmat.lp` | [L&P legacy app](#lp-legacy-app) |
| ✅ | [LP Control](https://play.google.com/store/apps/details?id=com.leggett.android.universal) 2.9.0 | `com.leggett.android.universal` | [Leggett & Platt](leggett-platt.md) |
| ✅ | [SVEN & SON](https://play.google.com/store/apps/details?id=com.richmat.svenson) | `com.richmat.svenson` | [Richmat remotes](#richmat-remotes) |
| ✅ | [Revive Control](https://play.google.com/store/apps/details?id=com.richmat.revive3) 1.0.26 | `com.richmat.revive3` | [Richmat MH](#richmat-mh-apps), bed type `richmat_revive` |
| ✅ | [Best Mattress](https://play.google.com/store/apps/details?id=com.richmat.best_mattress) 1.1.1 | `com.richmat.best_mattress` | [Richmat MH](#richmat-mh-apps), bed type `richmat_best_mattress` |
| ✅ | [Blvd Home](https://play.google.com/store/apps/details?id=com.richmat.blvd_home) 1.0.1 | `com.richmat.blvd_home` | [Richmat MH](#richmat-mh-apps), bed type `richmat_blvd_home` |
| ✅ | [HARMONY](https://play.google.com/store/apps/details?id=com.richmat.harmony) 1.0.0 | `com.richmat.harmony` | [Richmat MH](#richmat-mh-apps), bed type `richmat_harmony` |
| ✅ | [Idealbed](https://play.google.com/store/apps/details?id=com.richmat.idealbed) 2.4.2 | `com.richmat.idealbed` | [Richmat MH](#richmat-mh-apps), bed type `richmat_idealbed` |
| ✅ | [RUF \| Betten Motor 2](https://play.google.com/store/apps/details?id=com.desarketing.ruf_betten_motor2) 1.1.8 | `com.desarketing.ruf_betten_motor2` | Own guide, [RUF and Richmat app profiles](ruf-richmat-apps.md): Richmat MH frames, bed type `ruf_betten` |
| ✅ | [W.Silver Products](https://play.google.com/store/apps/details?id=com.richmat.wsilver2) 1.1.19 | `com.richmat.wsilver2` | Own guide, [RUF and Richmat app profiles](ruf-richmat-apps.md): Richmat MH frames, bed type `wsilver_products` |
| ✅ | [AMERICANSTAR](https://play.google.com/store/apps/details?id=com.richmat.americanstar) 1.0.0 | `com.richmat.americanstar` | Own guide, [RUF and Richmat app profiles](ruf-richmat-apps.md): Richmat MH frames, bed type `richmat_americanstar` |
| ✅ | [Bailey's Bed Control](https://play.google.com/store/apps/details?id=com.richmat.bailey2) 2.1.21 | `com.richmat.bailey2` | Own guide, [RUF and Richmat app profiles](ruf-richmat-apps.md): Richmat MH frames, bed type `bailey_bed_control` |
| ✅ | [TX](https://play.google.com/store/apps/details?id=com.richmat.tx) 1.0.0 | `com.richmat.tx` | Own guide, [RUF and Richmat app profiles](ruf-richmat-apps.md): Richmat MH frames, bed type `richmat_tx` |
| ✅ | [HJBed](https://play.google.com/store/apps/details?id=com.richmat.hjbed) 2.1.2 (code 21200) | `com.richmat.hjbed` | [HJBed](#hjbed) |
| ✅ | [Eshine](https://play.google.com/store/apps/details?id=com.richmat.eshinesleep) 1.0.1 (code 10100) | `com.richmat.eshinesleep` | [Eshine](#eshine) |
| ✅ | [Avocado Eco Base](https://play.google.com/store/apps/details?id=com.richmat.avocadoecobase) 1.0.4 (5) | `com.richmat.avocadoecobase` | [Classic apps](#classic-richmat-apps) |
| ✅ | [CoasterSleep](https://play.google.com/store/apps/details?id=com.richmat.coastersleep) 1.0.10 (10) | `com.richmat.coastersleep` | [Classic apps](#classic-richmat-apps) |
| ✅ | [Forty Winks](https://play.google.com/store/apps/details?id=com.richmat.fortywinks) 1.0.1 | `com.richmat.fortywinks` | [Classic apps](#classic-richmat-apps) |
| ✅ | [Milemont](https://play.google.com/store/apps/details?id=com.richmat.milemont) 1.0.4 | `com.richmat.milemont` | [Classic apps](#classic-richmat-apps) |
| ✅ | [Superior](https://play.google.com/store/apps/details?id=com.richmat.superior) 1.0.9 | `com.richmat.superior` | [Classic apps](#classic-richmat-apps) |
| ✅ | [Galaxy Bed Control](https://play.google.com/store/apps/details?id=nl.starinternational.galaxy) 3.3.0 (330002) | `nl.starinternational.galaxy` | [Galaxy Bed Control](#galaxy-bed-control) |
| ✅ | [Luuna Rise](https://play.google.com/store/apps/details?id=com.richmat.luunarise2) 1.0.13 | `com.richmat.luunarise2` | [Luuna Rise / Power Cool](#luuna-rise--power-cool) |
| ✅ | [Power Cool Sleep System](https://play.google.com/store/apps/details?id=com.richmat.powercool) 1.0.8 | `com.richmat.powercool` | [Luuna Rise / Power Cool](#luuna-rise--power-cool) |
| ✅ | [Lady Americana](https://play.google.com/store/apps/details?id=com.richmat.lady_americana) 1.0.2 (3) | `com.richmat.lady_americana` | [Lady Americana](#lady-americana) |
| ✅ | [ACAA](https://play.google.com/store/apps/details?id=com.richmat.acaa) 1.0.4 (5) | `com.richmat.acaa` | [ACAA](#acaa) |
| ✅ | [STA Homecare](https://play.google.com/store/apps/details?id=com.richmat.sta2) 1.0.5 (6) | `com.richmat.sta2` | [STA Homecare](#sta-homecare) |
| ✅ | [Zero Gravity](https://play.google.com/store/apps/details?id=com.richmat.zerogravity) 1.0.3 (4) | `com.richmat.zerogravity` | [Zero Gravity](#zero-gravity) |
| ✅ | [Good Vibe Sleep](https://play.google.com/store/apps/details?id=com.richmat.goodvibesleep) 2.0.1 (20103) | `com.richmat.goodvibesleep` | [Good Vibe Sleep](#good-vibe-sleep) |
| ✅ | [MLILY Control](https://play.google.com/store/apps/details?id=com.richmat.mlily2) 5.0.2 (50200) | `com.richmat.mlily2` | [MLILY Control](#mlily-control) |
| ✅ | [Casper Base](https://play.google.com/store/apps/details?id=com.richmat.casperbase) 1.0.8 (10800) | `com.richmat.casperbase` | [Casper Base](#casper-base); setup, sleep sensors and remote finder in its [own guide](casper-base.md) |
| ✅ | [SonicSleep](https://play.google.com/store/apps/details?id=com.richmat.sonicsleep) 1.0.4 (10400) | `com.richmat.sonicsleep` | [SonicSleep](#sonicsleep) |
| ✅ | [Luuna +](https://play.google.com/store/apps/details?id=com.richmat.luuna) 2.0.1 (20102) | `com.richmat.luuna` | [Luuna +](#luuna-) |
| ✅ | [Hush Base](https://play.google.com/store/apps/details?id=com.richmat.hushbase) 1.0.5 (10501) | `com.richmat.hushbase` | [Hush Base](#hush-base); setup, sleep sensors and remote finder in its [own guide](hush-base.md) |

## Features

| Feature | Richmat remotes | BedTech | L&P MlRM | RMControl | Richmat MH | HJBed | Classic apps | Eshine | Good Vibe Sleep | L&P legacy app | Casper Base | Hush Base |
|---------|-----------------|---------|----------|-----------|------------|-------|------------|--------|-----------------|----------------|-------------|-----------|
| Motor Control | ✅ (up to 7 motors) | ✅ Back/legs; BT6500 pillow/lumbar; FH head banks | ✅ Head, Feet | ✅ Catalog movement with cancellable repeats and release cleanup | ✅ Two motors; the model decides which exist (KEEP then STOP) | ✅ Selected head, foot, combined, pillow, lumbar, tilt, foot-box and sofa routes, depending on product | ✅ Exact app-labelled controls per selected layout | ✅ Head, feet, lumbar and pillow; global STOP | ✅ Exact app-labelled actions, with each product's gesture and operand | ⚠️ Layout-specific app buttons; no generic head, foot or lumbar axes | ✅ Product-specific; PRO back, legs and lumbar, MAX adds pillow | ✅ Product-specific back, legs, pillow, lumbar, combined and third motor |
| Hold Until Release | ✅ ([renewable hold](../SERVICES.md#renewable-holds)) | ✅ Explicit 7.1.3 models, no release frame; legacy keeps finite pulses | ✅ | ✅ Products whose motor controls are sustain presses; short-press products keep finite moves | ✅ (KEEP until the lease ends, then STOP 120 ms later) | ✅ (sustained actions) | ✅ Keep buttons, including the Hold presets ([renewable hold](../SERVICES.md#renewable-holds), release 50 ms after it ends); short, long and armed presses keep their gestures | ✅ ([renewable hold](../SERVICES.md#renewable-holds) and `hold_control`, then STOP) | ✅ Sustained-press controls only ([renewable hold](../SERVICES.md#renewable-holds)); short, long and short-and-long presses, and memory-mode controls while memory mode is on, keep their own gestures | ❌ Button gestures only | ❌ Finite pulses, then STOP | ❌ Finite pulses, then STOP |
| [Estimated Positions](../ESTIMATED_POSITIONS.md) | ✅ Opt-in head and feet | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Position Feedback | ❌ | ❌ | ❌ | ❌ (numbered motor reports are not relabeled as physical axes) | ⚠️ VER1 angle replies update the angle numbers; **Reached position** reports memory arrival | Raw observed travel, angle and height data; no inferred position seeking or units | ❌ No inferred angle or general command acknowledgement; desk height, range, unit and error callbacks | ❌ (motor reports never populate position feedback or sliders) | ❌ No calibrated position controls; raw typed events remain visible | ❌ | ❌ Raw motor-number diagnostics only, not calibrated angles | ❌ Raw index, angle and height events only |
| Memory Presets | ✅ (1-5 slots, varies by model) | ✅ (2 slots) | ✅ (2 slots, held recall) | ✅ Where the selected catalog supports them | ✅ Memory slots from the model's catalog | ✅ Product-specific named recall/save buttons, including memory 1–4 where selected | ✅ Per-node short and long gestures, memory-arm and Hold/Release gates | ❌ (named preset saves instead) | ✅ Product-specific short/long gestures and local memory mode | ⚠️ Only as the selected layout's named app buttons | ✅ The product's slots, recall and save (PRO and MAX: one) | ✅ Product-specific recall and explicit save |
| Presets | ✅ Zero-G / Anti-Snore / TV / Lounge; Yoga / Read on some models | ✅ Model-specific presets; Lounge only on legacy | ✅ Zero-G / Anti-Snore / TV / Lounge | ✅ Where the catalog has them | ✅ Standard presets from the model's catalog | ✅ Product-specific | ✅ Where the layout has them | ✅ Flat / Zero-G / Anti-Snore; saves Zero-G and Anti-Snore | ✅ Zero gravity, anti-snoring, TV and lounge actions where the product has them | ⚠️ Only as the selected layout's named app buttons | ✅ TV, Lounge, Anti-snore and Zero-G, recall and save | ✅ Product-specific, recall and save |
| Massage | ✅ | ✅ Model-specific zone, mode, off or 20-minute timer actions | ✅ Discrete head/foot up and down, timers | ✅ Including head/foot intensity up/down where both directions exist | ✅ App-labelled buttons; VER1 head/foot intensity numbers | ✅ Product-specific mode, intensity and timer buttons | ✅ Bound levels, patterns, timers and popup choices | ✅ Head and foot strength, mode, off, 10/20/30-minute buttons | ✅ Exact controls in the selected app layout; bottom massage countdown | ⚠️ Only as the selected layout's named app buttons | ✅ Head and foot intensity, mode, all off, 10/20/30-minute timers | ✅ The product's zones, modes and timers |
| Under-bed Lights | ✅ (toggle; RGB color picker + timer on select models) | ✅ Model-specific toggle; legacy also off | ✅ (toggle) | ⚠️ RGB, **Always On** or **1 through 15 minutes** timer; gated on the light acknowledgment and strip flag | ✅ RGB light or colour action, light timeout, button-light page | ✅ Selected lamp buttons; advanced timeout/RGB require product flag and acknowledgement | ✅ Bound controls, capability-gated RGB and timer settings | ✅ (toggle) | ✅ Product-gated actions, RGB settings and duration choices | ⚠️ Only as the selected layout's named app buttons; no RGB | ✅ Light buttons; ordinary light or RGB page where the product and its reply allow | ✅ RGB strip for lighting-flag products, colour and timer otherwise |
| Split-King Sync | ✅ (controller-level on/off; assumed state) | ❌ | ❌ | ✅ Where the catalog has it | ❌ | ✅ Sync buttons where selected | ✅ Where the layout has it | ❌ | ✅ Sync on/off actions where the product has them | ❌ | ❌ (one-address Left/Right on stored L400SH and L300SH) | ❌ (one-address Left/Right on side-flag products) |
| Alarms | ❌ | ❌ | ❌ | ⚠️ `adjustable_bed.rmcontrol_alarm`, product-gated | ✅ Actions and entities where the model's pages exist | ✅ Single or repeat alarms where the product flag and clock acknowledgement permit | ✅ One selected layout action at the next requested wall-clock time | ❌ | ✅ Product-gated single and repeat alarms, slots 1–7 | ❌ | ⚠️ Single and repeating alarms on stored products with alarm lists; none on PRO and MAX | ✅ Single; repeating only on restored products with that capability |
| Other | | | | ✅ Disabled-by-default catalog buttons; ⚠️ `adjustable_bed.rmcontrol_anti_snore` on six products | ✅ Smart set lock, snore intervention, detection, aroma, waist mattress | ✅ Music, clock synchronization, local layout, single-address paired sides | ✅ Aroma (no reliable setting acknowledgements); desk target, unit, three recall buttons and fourth/reset button | ⚠️ Eleven read-only diagnostic sensors | ✅ Snore settings where the normal product's settings menu admits them; independent type 1/type 2 sleep sensors with live values and direct BLE reports; only the product's listed sides. ❌ Firmware, Wi-Fi and cloud are outside the direct BLE bed boundary | ⚠️ Disabled-by-default app-response diagnostic; Stop cancels and releases the active action only (no emergency-stop command) | ✅ Music page, external snore trigger, sensor-name query; separate [sleep sensors and remote finder](casper-base.md#separate-sleep-sensors-and-remote-finder) | ✅ Fan, heating and music on products that list them; separate [sleep modules](hush-base.md#sleep-transport) |

## Choosing a profile

Detection suggests the [Richmat remotes](#richmat-remotes) route for Richmat
services and names, and [BedTech](#bedtech) or [L&P MlRM](#lp-mlrm) where their
signals are present. The catalog apps are opt-in: choose RMControl with its
product code, a Richmat MH app with its model, HJBed, Good Vibe Sleep or MLILY Control with
its product, a classic app with its layout, the Eshine app, or the
[L&P legacy app](#lp-legacy-app) with its remote code and packet mode.
[Casper Base](#casper-base) and [Hush Base](#hush-base) are bed types of their
own: choose the app's row in the bed-type list, then its product.

### Home Assistant setup

The bed-type list has one **Richmat** row naming RMControl, the five MH apps, the
five classic apps, MLILY Control, SleepFunction, SVEN & SON and the Richmat remotes. Searching
for any of those names finds it. A detected Richmat bed opens the same question.
Setup then asks which app you use; the bed's name and services never decide it.

1. **RMControl app:** choose the exact product code RMControl shows, then the
   side the app commands (see [RMControl](#rmcontrol)).
2. **Revive Control, Best Mattress, Blvd Home, HARMONY or Idealbed app:** choose
   the model, or keep Auto to read it from the Bluetooth name (see
   [Richmat MH apps](#richmat-mh-apps)).
3. **Avocado Eco Base, CoasterSleep, Forty Winks, Milemont or Superior app:**
   choose the app's four-character layout (see
   [Classic Richmat apps](#classic-richmat-apps)).
4. **SleepFunction or SVEN & SON app, or a Richmat remote:** choose the remote
   code. A code the Bluetooth name carries is preselected (see
   [Richmat remotes](#richmat-remotes)).

RMControl and the remote controls also offer the packet dialect under
**Advanced**. An app picked from the **Richmat app profiles** brand list skips
the question. Existing entries keep their bed type, settings and entity IDs.
**Configure** changes the same answers and lists each app by its own name, so an
existing entry can switch to an MH or classic app there. A remote entry opts in
to RMControl by choosing a product, and an RMControl entry returns to the remote
controls by choosing None. Each receiver of a two-address pair answers for itself.

<!-- generated:richmat-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Fixed-table routes

Movement repeats the code at the entry's pulse count and delay, whose defaults are
listed, then always sends STOP with a fresh cancel event. Every other button is
one write. Under a [renewable hold](../SERVICES.md#renewable-holds), movement
repeats at the same delay until the lease ends or STOP arrives, up to 30 s, then
sends STOP.

| Profile | Bed type | Framing | STOP | Default pulses | Presets and recall | Memory | Hold until release |
|---|---|---|---|---|---|---|---|
| Richmat WiLinke | `richmat` | wilinke | `6E 01 00 6E DD` | 7 × 150 ms | once | 5 slots | renewable lease |
| Richmat Nordic | `richmat` | nordic | `6E` | 7 × 150 ms | once | 5 slots | renewable lease |
| Richmat Prefix55 | `richmat` | prefix55 | `55 01 00 6E C4` | 7 × 150 ms | once | 5 slots | renewable lease |
| Richmat PrefixAA | `richmat` | prefixaa | `AA 01 00 6E 19` | 7 × 150 ms | once | 5 slots | renewable lease |
| BedTech legacy | `bedtech` | wilinke | `6E 01 00 5E CD` | 10 × 100 ms | once | 2 slots | no |
| BedTech app BT2000 | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BT2500 | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BT3000 | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BT3000FH | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BT6500 | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BTX4 | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BTX4FH | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BTX5 | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| BedTech app BTX5FH | `bedtech` | wilinke | End refresh (no frame) | 10 × 100 ms | once | 2 slots | renewable lease |
| L&P MlRM | `leggett_wilinke` | wilinke | `6E 01 00 6E DD` | 10 × 110 ms | 100 × 300 ms, then STOP | 2 slots | renewable lease |

### Catalog apps

| Profile | Bed type | Transport order | Commands | Hold until release |
|---|---|---|---|---|
| SonicSleep | `sonicsleep` | platform GATT order | fixed IQRM product | renewable lease; no release packet |
| HJBed | `hjbed` | W1, N1, W5, W4, W3, W2 | per-product catalog | renewable lease |
| Richmat 4.2.0 | `richmat_app` | N1, W1, W2, W3, W4, W5 | per-model catalog | renewable lease |
| Eshine | `eshine` | N1, W1, W2, W3, W4, W5 | [fixed E6000 table](#eshine-commands) | renewable lease |
| Richmat MH Revive Control | `richmat_revive` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH Best Mattress | `richmat_best_mattress` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH Blvd Home | `richmat_blvd_home` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH HARMONY | `richmat_harmony` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH Idealbed | `richmat_idealbed` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH RUF Betten | `ruf_betten` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH W.Silver | `wsilver_products` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH AMERICANSTAR | `richmat_americanstar` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH Bailey | `bailey_bed_control` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Richmat MH TX | `richmat_tx` | N1, W1, W2, W3, W4 | per-model catalog | renewable lease |
| Classic Avocado Eco Base | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic CoasterSleep | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Forty Winks | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Milemont | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Superior | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Luuna Rise | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Power Cool Sleep System | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Lady Americana | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic ACAA | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic STA Homecare | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Classic Zero Gravity | `richmat_classic_apps` | W1, W2, N1, W4 | per-layout catalog | renewable lease on keep buttons |
| Galaxy Bed Control | `galaxy` | W1, N1, W5, W4, W3, W2 | per-product catalog | no |
| Good Vibe Sleep | `goodvibe` | W1, N1, W5, W4, W3, W2 | per-product catalog | renewable lease on sustained controls |
| MLILY Control | `mlily` | W1, N1, W5, W4, W3, W2 | per-product catalog | renewable lease on sustained controls |
| L&P legacy app | `leggett_lp_legacy` | configured characteristics | per-layout catalog | no |
| Casper Base | `casper_base` | N1, W1, W2, W3, W4, W5 | per-product catalog | no |
| Hush Base | `hush_base` | N1, W1, W2, W3, W4, W5 | per-product catalog | no |
| Luuna + | `luuna` | N1, W1, W2, W3, W4, W5 | per-product catalog | renewable lease |
<!-- /generated -->

### Catalog app timing

<!-- generated:richmat-catalog-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile | Operation | Timing |
|---|---|---|
| RMControl | Write queue, including release | at least 100 ms apart |
| RMControl | Sustain press | entry pulse count at 100 ms, then STOP |
| RMControl | Short and long press | one write |
| Richmat MH | Version query after subscribing | 300 ms |
| Richmat MH | Initialization tasks | 300 ms apart, the first 300 ms after the version query |
| Richmat MH | STOP after a release or a single tap | 120 ms |
| Richmat MH | VER1 angle target | 100 ms after the slider release |
| Richmat MH | Alarm frames | 300 ms apart (150 ms for three-slot save/delete) |
| Richmat MH | Aroma frames | 150 ms apart |
| HJBed | Sustained refresh | every 100 ms from the first tick |
| HJBed | Write spacing | at least 100 ms between attempts |
| HJBed | Menu probes at connect | 300 ms apart |
| HJBed | BJRN preset save | waits 3 s |
| Eshine | Held refresh | every 100 ms for the entry pulse count, then STOP |
| Eshine | Other buttons and STOP | one write |
| Classic apps | Worker tick | 150 ms; 110 ms for TWRM and MLRM names |
| Classic apps | Release after a held control | 50 ms |
| Classic apps | Once or short press | payload, then release 150 ms later |
| Classic apps | Long press | 3000 ms, or the node's own threshold |
| Classic apps | FRAMED startup frame | 300 ms after notifications start |
| Classic apps | Alarm frames | 300 ms apart |
| Classic apps | Settings queries | 500 ms apart |
| Classic apps | Aroma frames, RGB busy interval | 150 ms |
| Classic apps | Desk button refresh | every 200 ms, with no release frame |
| Good Vibe Sleep | Sustained press | first write after 100 ms, then every 100 ms; STOP once a write was attempted |
| Good Vibe Sleep | Long and short-and-long press | long action after 3000 ms |
| Good Vibe Sleep | Menu checks at connect | 300 ms apart |
| Good Vibe Sleep | Incomplete notification bytes | dropped after 500 ms |
| Good Vibe Sleep | Live sleep data | polled every 2 s |
| L&P legacy app | Held press | every 100 ms for the entry pulse count, then its release |
| L&P legacy app | Long press | one write after 3100 ms |
| L&P legacy app | One-shot press | one write, then one 100 ms tick |
| Casper Base | Every write | waits one 100 ms tick first |
| Casper Base | Movement | entry pulse count, one code per 100 ms tick, then STOP |
| Casper Base | Soundtrack switch | dropped within 2 s of the last; 900 ms after its Bluetooth switch |
| Casper Base | External snore detector | sampled every 3 s |
| Hush Base | Every write | waits one 100 ms tick first |
| Hush Base | Movement | entry pulse count, one code per 100 ms tick, then STOP |
| Hush Base | Soundtrack switch | dropped within 2 s of the last; 900 ms after its Bluetooth switch |
| Hush Base | External snore detector | sampled every 3 s |
<!-- /generated -->

### Aliases

No two Richmat bed types send identical bytes. The
[protocol inventory](../design/protocol-inventory.md) found one model identical in two apps:
`model_bfrm` in Best Mattress and in Blvd Home. Each app keeps its own catalog,
so the model stays a choice in both [Richmat MH apps](#richmat-mh-apps).

The two routes also keep separate [profile ids](../design/profile-id.md#aliases).

## Wire codec

`codec/richmat.py` holds the transports, framing, checksum and every command
encoder below. Profiles in `profiles/richmat.py` hold the codes, transport order
and timing.

### Transports

<!-- generated:richmat-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Key | Service | Write | Notify | Commands | Profiles |
|---|---|---|---|---|---|
| N1 | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | bare code | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat 4.2.0, Eshine, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed, Richmat MH RUF Betten, Richmat MH W.Silver, Richmat MH AMERICANSTAR, Richmat MH Bailey, Richmat MH TX, Classic Avocado Eco Base, Classic CoasterSleep, Classic Forty Winks, Classic Milemont, Classic Superior, Classic Luuna Rise, Classic Power Cool Sleep System, Classic Lady Americana, Classic ACAA, Classic STA Homecare, Classic Zero Gravity, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, Casper Base, Hush Base, Luuna +, SonicSleep |
| W0 | `8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA |
| W1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, BedTech legacy, BedTech app BT2000, BedTech app BT2500, BedTech app BT3000, BedTech app BT3000FH, BedTech app BT6500, BedTech app BTX4, BedTech app BTX4FH, BedTech app BTX5, BedTech app BTX5FH, L&P MlRM, HJBed, Richmat 4.2.0, Eshine, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed, Richmat MH RUF Betten, Richmat MH W.Silver, Richmat MH AMERICANSTAR, Richmat MH Bailey, Richmat MH TX, Classic Avocado Eco Base, Classic CoasterSleep, Classic Forty Winks, Classic Milemont, Classic Superior, Classic Luuna Rise, Classic Power Cool Sleep System, Classic Lady Americana, Classic ACAA, Classic STA Homecare, Classic Zero Gravity, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, Casper Base, Hush Base, Luuna +, SonicSleep |
| W2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat 4.2.0, Eshine, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed, Richmat MH RUF Betten, Richmat MH W.Silver, Richmat MH AMERICANSTAR, Richmat MH Bailey, Richmat MH TX, Classic Avocado Eco Base, Classic CoasterSleep, Classic Forty Winks, Classic Milemont, Classic Superior, Classic Luuna Rise, Classic Power Cool Sleep System, Classic Lady Americana, Classic ACAA, Classic STA Homecare, Classic Zero Gravity, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, Casper Base, Hush Base, Luuna +, SonicSleep |
| W3 | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat 4.2.0, Eshine, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed, Richmat MH RUF Betten, Richmat MH W.Silver, Richmat MH AMERICANSTAR, Richmat MH Bailey, Richmat MH TX, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, Casper Base, Hush Base, Luuna +, SonicSleep |
| W4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat 4.2.0, Eshine, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed, Richmat MH RUF Betten, Richmat MH W.Silver, Richmat MH AMERICANSTAR, Richmat MH Bailey, Richmat MH TX, Classic Avocado Eco Base, Classic CoasterSleep, Classic Forty Winks, Classic Milemont, Classic Superior, Classic Luuna Rise, Classic Power Cool Sleep System, Classic Lady Americana, Classic ACAA, Classic STA Homecare, Classic Zero Gravity, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, Casper Base, Hush Base, Luuna +, SonicSleep |
| W5 | `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | `00000003-3c17-d293-8e48-14fe2e4da212` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat 4.2.0, Eshine, Galaxy Bed Control, Good Vibe Sleep, MLILY Control, Casper Base, Hush Base, Luuna +, SonicSleep |

W0 is the legacy custom service, W4 and W5 are name-guarded (see the Richmat
profile's Setup). The Richmat routes try W0 to W5, then N1, then fall back to W1.
<!-- /generated -->

### Framing and checksum

- `sum8` is the low byte of the sum of every byte before it. Values are masked to
  eight bits, as the apps do.
- A **command** is `6E 01 side code sum8`. `side` is `00` for a single bed;
  RMControl uses `01` for right and `02` for both; HJBed sends both sides as
  separate `00` and `01` frames; the Richmat MH apps put their `txMode` byte
  there (`00` in the single-device group).
- Nordic UART transports take the bare code. The legacy Richmat routes also frame
  the code behind a `55` or `AA` header:

<!-- generated:richmat-framing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Framing | Layout | Flat |
|---|---|---|
| wilinke | `6E 01 00 code sum8` | `6E 01 00 31 A0` |
| nordic | bare code | `31` |
| prefix55 | `55 01 00 code sum8` | `55 01 00 31 87` |
| prefixaa | `AA 01 00 code sum8` | `AA 01 00 31 DC` |
<!-- /generated -->

- **Extended records** are `6E len 20 domain command operation data sum8`, where
  `len` counts the whole frame. Notifications, Good Vibe Sleep's settings records
  and every Casper Base and Hush Base record place the length after `20`:
  `6E 20 len domain command operation data sum8`.
- `6E 40` notifications carry a two-byte length and end in a big-endian
  CRC-16/XMODEM instead of `sum8`.
- Richmat MH **mattress** frames use the `5E` header with the same checksum and
  no side byte.

### Command encoders

#### Fixed-table buttons

Codes are the profile's; frames are built by the codec with WiLinke framing.

<!-- generated:richmat-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Richmat (WiLinke) | BedTech | L&P MlRM |
|---|---|---|---|
| Head up | `6E 01 00 24 93` | `6E 01 00 24 93` | `6E 01 00 24 93` |
| Head down | `6E 01 00 25 94` | `6E 01 00 25 94` | `6E 01 00 25 94` |
| Feet up | `6E 01 00 26 95` | `6E 01 00 26 95` | `6E 01 00 26 95` |
| Feet down | `6E 01 00 27 96` | `6E 01 00 27 96` | `6E 01 00 27 96` |
| Head and feet up | `6E 01 00 29 98` | n/a | n/a |
| Head and feet down | `6E 01 00 2A 99` | n/a | n/a |
| Pillow up | `6E 01 00 3F AE` | `6E 01 00 29 98` | n/a |
| Pillow down | `6E 01 00 40 AF` | `6E 01 00 2A 99` | n/a |
| Lumbar up | `6E 01 00 41 B0` | n/a | n/a |
| Lumbar down | `6E 01 00 42 B1` | n/a | n/a |
| Flat | `6E 01 00 31 A0` | `6E 01 00 31 A0` | `6E 01 00 31 A0` |
| Zero-G | `6E 01 00 45 B4` | `6E 01 00 45 B4` | `6E 01 00 45 B4` |
| Anti-Snore | `6E 01 00 46 B5` | `6E 01 00 46 B5` | `6E 01 00 46 B5` |
| TV | `6E 01 00 58 C7` | `6E 01 00 58 C7` | `6E 01 00 58 C7` |
| Lounge | `6E 01 00 59 C8` | `6E 01 00 65 D4` | `6E 01 00 59 C8` |
| Save lounge | `6E 01 00 65 D4` | n/a | n/a |
| Light toggle | `6E 01 00 3C AB` | `6E 01 00 3C AB` | `6E 01 00 3C AB` |
| Light off | n/a | `6E 01 00 75 E4` | n/a |
| Massage toggle | `6E 01 00 5D CC` | `6E 01 00 5D CC` | `6E 01 00 32 A1` |
| Massage off | `6E 01 00 5E CD` | n/a | `6E 01 00 47 B6` |
| Head massage step | `6E 01 00 4C BB` | `6E 01 00 4C BB` | `6E 01 00 32 A1` |
| Foot massage step | `6E 01 00 4E BD` | `6E 01 00 4E BD` | `6E 01 00 33 A2` |
| Massage mode step | `6E 01 00 48 B7` | `6E 01 00 48 B7` | `6E 01 00 38 A7` |
| Head massage up | n/a | n/a | `6E 01 00 4C BB` |
| Head massage down | n/a | n/a | `6E 01 00 4D BC` |
| Foot massage up | n/a | n/a | `6E 01 00 4E BD` |
| Foot massage down | n/a | n/a | `6E 01 00 4F BE` |
| Massage intensity up | n/a | n/a | `6E 01 00 34 A3` |
| Massage intensity down | n/a | n/a | `6E 01 00 35 A4` |
| Wave massage | n/a | n/a | `6E 01 00 39 A8` |
| Massage timer 10 min | n/a | n/a | `6E 01 00 5F CE` |
| Massage timer 20 min | n/a | n/a | `6E 01 00 63 D2` |
| Massage timer 30 min | n/a | n/a | `6E 01 00 61 D0` |
| Controller sync on | `6E 01 00 BC 2B` | n/a | n/a |
| Controller sync off | `6E 01 00 BD 2C` | n/a | n/a |
| STOP | `6E 01 00 6E DD` | `6E 01 00 5E CD` | `6E 01 00 6E DD` |
| Compatibility STOP (QRRM, BT6500 remotes) | `6E 01 00 5E CD` | n/a | n/a |
<!-- /generated -->

#### Memory

<!-- generated:richmat-memory -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Richmat (WiLinke) | BedTech | L&P MlRM |
|---|---|---|---|
| Memory 1 recall | `6E 01 00 2E 9D` | `6E 01 00 2E 9D` | `6E 01 00 2E 9D` |
| Memory 2 recall | `6E 01 00 2F 9E` | `6E 01 00 2F 9E` | `6E 01 00 2F 9E` |
| Memory 3 recall | `6E 01 00 30 9F` | n/a | n/a |
| Memory 4 recall | `6E 01 00 B2 21` | n/a | n/a |
| Memory 5 recall | `6E 01 00 F4 63` | n/a | n/a |
| Memory 1 save | `6E 01 00 2B 9A` | `6E 01 00 2B 9A` | `6E 01 00 2B 9A` |
| Memory 2 save | `6E 01 00 2C 9B` | `6E 01 00 2C 9B` | `6E 01 00 2C 9B` |
| Memory 3 save | `6E 01 00 2D 9C` | n/a | n/a |
| Memory 4 save | `6E 01 00 B3 22` | n/a | n/a |
| Memory 5 save | `6E 01 00 F5 64` | n/a | n/a |

The Richmat remote code decides how many slots appear (up to three); recall and
save accept every listed slot.
<!-- /generated -->

#### Lights

<!-- generated:richmat-lights -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | RGB strip (QRRM family) | Legacy RGB |
|---|---|---|
| On | `04 09 04 01 00 02 00 00 14` | `6E 0A 00 01 79` |
| Off | `04 09 04 01 00 00 00 00 12` | light toggle |
| Colour | `04 0B 01 01 00 R G B 00 00 sum8` | `6E 0C FF R sum8 6E 0D G B sum8` (one write) |
| Timer | minutes, for example 5 min `04 0A 02 01 00 00 05 00 00 16` | seconds, for example 5 min `6E 0B 01 2C A6` |
| Always On | `04 0A 02 01 00 00 00 00 00 11` | `6E 0B 00 00 79` |
<!-- /generated -->

#### Function selectors

The catalog apps send a few actions behind their own prefix instead of
`6E 01 side`:

<!-- generated:richmat-functions -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Catalog action | Prefix |
|---|---|
| `ItemExitLimit` | `6E 02 01` |
| `ItemCheckClock` | `6E 08 01` |
| `ItemCheckLight` | `6E 0A 00` |
| `ItemCheckMusic` | `6E 15 01` |
| `ItemCheckAroma` | `6E 1A 00` |
| `ItemCheckMattress` | `5E 1A 00` |
| `ItemCheckSnore` | `6E 21 00` |
| `ItemCheckSpeech` | `6E 22 00` |
| `ItemCheckDetection` | `6E 9A C0` |
| `ItemSendStartDetection` | `6E 88 C2` |
| `ItemQueryVersion` | `6E 9A 00` |
| `VersionOneBedCurrentMode` | `6E 9A 10` |
| `VersionOneMotor1CurrentAngle` | `6E 9A 30` |
| `VersionOneMotor2CurrentAngle` | `6E 9A 30` |
| `VersionOneMotor3CurrentAngle` | `6E 9A 30` |
| `VersionOneMotor4CurrentAngle` | `6E 9A 30` |
| `VersionOneCurrentMassageMode` | `6E 9A A0` |
| `VersionOneCurrentBedLightStatus` | `6E 9A B0` |

Every other catalog action uses `6E 01 side`. HJBed, Casper Base and Hush Base
send only the first four, Good Vibe Sleep the first three.
<!-- /generated -->

#### Variable frames

| Frame | Layout |
|-------|--------|
| Light timer | `6E 0B high low sum8`; each app chooses its always-on value |
| Light colour | `6E 0C FF R sum8` + `6E 0D G B sum8`, one write |
| Countdown alarm | `6E 05 low slot sum8`, then `6E 06 high action sum8`; zero minutes and action cancel |
| Repeating alarm | Extended `05 01 01` (create), `05 02 01` (delete), `05 01 00` (query) |
| Time sync | Extended `08 02 01`: Unix time (4 bytes, big-endian) + whole-hour offset; `08 03 01`: `year−1970 month day hour minute second` |
| Snore intervention | Extended `06 01 01` (switch), `06 05 01` (configure), `06 03 00` (sleep-advertisement query) |
| Control mode (HJBed) | Extended `0B 02 00` (query) and `0B 02 01` (set) |
| RGB strip (QRRM family) | `04 len command 01 00 payload 00 00 sum8` |

Good Vibe Sleep sends its repeating-alarm, snore and time-sync records with the
length after `20` (see [its settings](#alarms-and-snore-settings)); Casper Base and
Hush Base send every record that way and their own countdown order (see the
[Casper and Hush family](#casper-and-hush-family)).

### Responses

The fixed-table routes read no responses. Each catalog app keeps its own
parser: RMControl's `NotificationBuffer`, the Richmat MH `Classifier` (two app
groups), HJBed's stream splitter and Good Vibe Sleep's `Notifications` buffer.
The first three check the additive checksum; Good Vibe Sleep checks it on `6E 20`
records and matches acknowledgements exactly. Eshine's `NotificationStream`
checks it on extended frames only. The L&P legacy app matches three exact frames.
Casper Base's `MainReceive` checks it on `6E 20` records; Hush Base's
`HushMainReceive` also on `6E 21`, and checks `6E 40` frames with the codec's
CRC-16. See each profile's Notifications.

### STOP and release behavior

- STOP is the command with code `6E`. QRRM and BT6500 Richmat remotes, and the legacy
  BedTech route, stop with `5E` instead.
- Fixed-table movement with a declared release always ends with STOP, sent with a fresh cancel event, so a cancelled
  hold still releases the motors. The BedTech route reports a failed STOP; the
  others log it and keep the original error.
- The catalog apps release per catalog entry: some actions are followed by STOP,
  others are not (see each profile's Controls). The L&P legacy app has no global
  STOP; each control sends its own release.
- A [renewable hold](../SERVICES.md#renewable-holds) keeps the held code
  refreshing at the profile's own interval (the entry's pulse delay on the
  fixed-table routes, the app's KEEP or sustain cadence on the catalog apps)
  until the lease ends or a STOP arrives, up to 30 s, then sends the same STOP.
  Legacy BedTech keeps finite pulses; its explicit 7.1.3 models end refresh
  without a release packet.

### Vectors

`tests/richmat_vectors.py` freezes each profile's frames: the accepted reports'
literals for the catalog apps (Good Vibe Sleep's from its accepted vectors in
`tests/fixtures/goodvibe`, the L&P legacy app's in both modes from its catalog),
and the pre-v5 controllers' frames for the fixed-table routes.
`tests/test_richmat_vectors.py` checks that every literal round-trips through the
codec and that each profile sends only frozen frames. For the fixed-table routes
and the L&P legacy app the two sets are equal.

`tests/casper_base_vectors.py` and `tests/hush_vectors.py` freeze the Casper Base
and Hush Base reports' sent frames, per app product and shared.
`tests/test_casper_base_vectors.py` and `tests/test_hush_vectors.py` rebuild each
one through the builder the apps use (`tests/casper_frames.py`) and check that
every product's catalog codes are frozen.

## Profiles

### Richmat remotes

**Status:** ✅ Tested

The `richmat` bed type. Its protocol variant picks the framing (one
[profile](#choosing-a-profile) each); its Richmat remote code picks the motors,
presets, memory slots, light packets and STOP.

#### Setup

- **Variant:** `auto` detects the transport. It tries the WiLinke services W0 to
  W5, using the write characteristic or, on single-characteristic beds such as
  Germany Motions `DHN-*`, a writable notify characteristic (without response).
  Then Nordic UART selects the Nordic variant, and otherwise W1 is used.
  `wilinke`, `prefix55` and `prefixaa` still detect the characteristic.
- **Remote code:** `richmat_remote` names the physical remote; `auto` keeps a
  generic layout. Features come from the 456-code generated mapping plus manual
  overrides.

FEE9/QRRM advertisements are shared with BedTech. A confirmed BedTech-specific
manufacturer field (`0x4C57`) selects the BedTech protocol; QRRM devices without
that field retain Richmat behavior, including the confirmed Casper RGB-light model.

QRRM is a generic controller name, not a single physical remote layout. For the
L&P surface reported in issue #504, with Flat, Zero G, Custom 1, and Custom 2,
choose **L&P QRRM** under the integration options. It remains an explicit profile
because the BLE name and GATT layout do not distinguish it from other QRRM
surfaces.
The current L&P and Richmat apps make the same explicit product-profile choice;
their generic QRRM profiles contain no controls. On the hardware from
issue #504, Flat is confirmed. The other command frames are statically verified
across the apps but have not yet been validated on that physical bed.

The QRRM receiver in issue #695 (Sven & Son, `WLT825X_H35_S`) is paired with an
HJH89 remote whose label prints, and QR-encodes, `GGRM`. Choose **GGRM / HJH89**
for that handset: head, feet, pillow (head tilt) and lumbar motors, Flat, Zero G,
Anti-snore, one memory, massage and a white light toggle. The Revive Control,
Blvd Home and HARMONY catalogs define the same GGRM controls and release with
`0x6E`, so this profile does not use the `0x5E` compatibility stop, which those
catalogs send as massage All Off. Hardware validation is pending.
With massage enabled, GGRM exposes All Off (`0x5E`), head/foot intensity steps
and mode stepping. It does not expose the generic all-massage toggle (`0x5D`),
which is absent from those GGRM catalogs.
The WiLinke GGRM profile also exposes Save Zero G and Save Anti-snore, plus
10, 20 and 30 minute massage buttons when massage is enabled. These are
one-shot catalog actions followed by the standard release after 120 ms.
Timer buttons do not claim to report the bed's current timer setting.
The commands are proven by the accepted row055 Revive Control, Blvd Home and
HARMONY GGRM tables; physical behavior on the issue #695 bed remains unverified.

The app tries BLE services in this order:

1. **WiLinke 1**: `0000FEE9-0000-1000-8000-00805F9B34FB`
2. **WiLinke 2**: `0000FEE9-0000-1000-8000-00805F9B34BB`
3. **Nordic UART**: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
4. **FFF0**: `0000FFF0-0000-1000-8000-00805F9B34FB`
5. **FFE0**: `0000FFE0-0000-1000-8000-00805F9B34FB`

> **W5 (`0000E0FF-3C17-D293-8E48-14FE2E4DA212`) caveat:** the Germany Motions app
> also lists a sixth "W5" service on a Telink-style custom 128-bit base (`0xE0FF`
> is just the little-endian form of the generic `0xFFE0`). That base is shared by
> non-bed Telink-chip devices, so a "Nokia-*" headset was misdetected as a Richmat
> bed (issue #382). W5 is therefore **not** used for passive discovery and only
> detects as a bed when the device name also matches a Richmat pattern.

> **W4 (`0000FFF0-...`) caveat:** FFF0 is a fully generic short UUID that many
> non-bed devices advertise — a "NO_DVR-*" camera system was misdetected as a
> Richmat bed (issue #418). All known W4 beds are Germany Motions units named
> `DHN-*` (the GM Bed Control app scans unfiltered and identifies beds by
> name/remote code, never by bare FFF0), so W4 likewise only detects as a bed
> when the device name also matches a Richmat pattern. FFF0 stays in
> `manifest.json` for passive discovery because SUTA and the Keeson Sino
> fallback also rely on it (both name-guarded as well).

Device name hints:

| Device Name Prefix | Features |
|-------------------|----------|
| `WFRM`, `FWRM` | Table/Lift with height control |
| `6BRM` | Nordic variant (170ms timing) |
| `TWRM`, `MLRM` | Fast timing (110ms) |
| `YGRM`, `BRRM` | Extended presets |

#### Controls

- Motors follow the remote code: head and feet always, pillow and lumbar when
  the remote has them. Back and legs are aliases of head and feet.
- `0x29`/`0x2A` are exposed as the `head_feet` cover, but only for remotes listed
  in `RICHMAT_COMBINED_HEAD_FEET_REMOTE_CODES`. Confirmed on hardware (#552): on
  two `twrm` beds (`WLT` / `WLT825X_H35_S`) the command raises head and feet at
  the same time, which two sequential cover commands cannot do because each
  Richmat motor command ends with its own STOP frame. Not every Richmat remote
  surface has this button, and the head and feet motor flags do not say which
  ones do, so the entity stays opt-in per remote code. Add a code to the set when
  a bed on that profile is confirmed. `auto` is excluded on purpose: it is the
  fallback whenever detection cannot name the remote.

> [!NOTE]
> The BedTech app calls the same byte pair `bothHeads`, which would mean two head
> sections rather than head plus feet. The naming across apps is not settled here;
> the per-remote allow list is what keeps the control off unconfirmed beds.

- Massage toggle (`5D`) is offered except on GGRM, which gets All Off (`5E`).
- **Lights:** most Richmat beds have a simple white under-bed light controlled
  via toggle. Some models (Casper, certain QRRM/I7RM remotes) have RGB light
  strips with full color control. BT6500 uses the plain white toggle light
  command. RGB is available on WiLinke-variant beds when a specific remote code
  is configured (not "Auto").
  - **RGB strip** (Casper, QRRM, I7RM with Casper/SleepFunction in the name):
    explicit on/off, color and timer. Timer range: 1-30 minutes or "Always On".
  - **Legacy RGB** (other WiLinke remotes with the lights feature flag): power-on,
    color and timer. Timer range: 1-5 minutes or "Always On". Off is the toggle.
  - RGB-capable beds expose a **Light** entity with a color wheel instead of a
    simple on/off switch. See [Lights](#lights) for the frames.
- **Controller Sync** sends `BC` (on) or `BD` (off).

**Controller Sync** (previously **Synchro Mode**) sends the selected controller's
sync command. It does not mirror commands between two Home Assistant entries.
The displayed switch state records requested changes, not confirmed movement or
sync status from the bed. In the HJC9 report, enabling it on both frames did not
make them move together.

For independently controllable frames, use the **Combine two beds into one
(Dual Bed)** flow, or keep standalone entries and control both with a script.
See [Controller Sync and two-frame setup](../CONFIGURATION.md#split-king--controller-sync)
for the distinction, setup guidance, and a script example.

**GGRM catalog actions** (WiLinke only; the massage timers need massage enabled):

<!-- generated:richmat-ggrm -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| GGRM action | WiLinke frame |
|---|---|
| Save Zero G | `6E 01 00 66 D5` |
| Save Anti-snore | `6E 01 00 69 D8` |
| Massage 10 min | `6E 01 00 5F CE` |
| Massage 20 min | `6E 01 00 63 D2` |
| Massage 30 min | `6E 01 00 61 D0` |
<!-- /generated -->

Codes listed by the apps that this route does not send:

| Group | Codes |
|-------|-------|
| Motors 5-7 (select table/lift actuators) | `71`/`72`, `73`/`74`, `D0`/`D1` |
| Combined movements | All `56`/`57`, Lumbar+Pillow `43`/`44`, Lumbar+Pillow Tilt `5B`/`5C`, Feet+Lumbar `96`/`97`, Head up + Feet down `21`, Head down + Feet up `22` |
| Presets | Yoga `F0`, Read `F2`, Side Sleeper `BA`, Sleep `8E`, Wakeup `93`, Flat Sleep `F6` |
| Save presets | Zero-G `66`, Anti-Snore `69`, TV `64`, Yoga `F1`, Side Sleeper `BB`, Sleep `8F`, Wakeup `94`, Flat Sleep `F7` (GGRM sends `66` and `69` as catalog actions) |
| Preset resets | Motor `BE`, TV `CA`, Snore `CB`, Zero-G `CC` |
| Discrete massage | Head off/1/2/3 `98`-`9B`, Foot off/1/2/3 `9C`-`9F`, Third motor increment `E0` |

#### Timing

Pulse defaults are in [Fixed-table routes](#fixed-table-routes). From app
disassembly analysis (SleepFunction):

| Device Name Prefix | Interval | Notes |
|-------------------|----------|-------|
| `6BRM` (Nordic) | 170ms | Nordic vendor |
| `TWRM`, `MLRM` | 110ms | Faster repeat |
| Default | **150ms** | Most devices |

Motor commands are sent continuously while the button is held. STOP is sent on
release.

#### Evidence

The Richmat remotes send only their frozen frames. The GGRM catalog actions are
proven by the accepted row055 reports (Revive Control, Blvd Home and HARMONY GGRM tables, with the `main_6e` release and
its 120 ms delay); the other frames are the pre-v5 controller's.

### BedTech

**App:** [BedTech](https://play.google.com/store/apps/details?id=com.bedtech) 7.1.3 (14), `com.bedtech`

**Status:** ❓ Needs testing (explicit app models); ✅ existing legacy controls

#### Setup

Choose **BedTech app**, then the exact model. Detection cannot select a model.
Existing entries keep **Legacy BedTech controls**, including their field-reported
`^` release and old pillow mapping. Select an explicit model to use the app's
controls and release behavior. No automatic migration changes a working bed.

All models write with response on W1 (FEE9). The app accepts any nonempty
Bluetooth name with that service, without a model-name or manufacturer filter.
Home Assistant normalizes UUIDs and accepts the service at any advertisement
index. Shared FEE9/QRRM alone remains ambiguous with Richmat, so confirm the app.
The existing hardware-specific identification remains: manufacturer ID `0x4C57`
and connected model `WLT825X_H35` identify confirmed BedTech receivers;
`WLT825X_H35_S` identifies the Casper/Richmat HJC27. A proxy may omit the
manufacturer field. Unknown models stay unchanged rather than being guessed.

For BT3000FH, BTX4FH and BTX5FH, enable **Left/Right controls** on the one
receiver to select the two head banks. Other models can combine two receiver
entries. Configure each physical receiver's model separately.
The app's bed-size choices do not negotiate a protocol or change the bytes.

#### Controls

<!-- generated:bedtech-models -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Model | Motors | Presets | Massage | Light | Single-address sides |
|---|---|---|---|---|---|
| BT2000 | back, legs | none | none | none | no |
| BT2500 | back, legs | Flat, Zero-G, Anti-Snore | Massage toggle, Massage off | none | no |
| BT3000 | back, legs | Flat, Zero-G, Anti-Snore | Head massage step, Foot massage step, Massage mode step, Massage timer 20 min | toggle | no |
| BT3000FH | back, legs | Flat, Zero-G, TV | Head massage step, Foot massage step, Massage mode step, Massage off | toggle | yes, shared foot |
| BT6500 | back, legs, pillow, lumbar | Flat, Zero-G, Anti-Snore | Head massage step, Foot massage step, Massage mode step, Massage off | toggle | no |
| BTX4 | back, legs | Flat, Zero-G | none | none | no |
| BTX4FH | back, legs | Flat, Zero-G | none | none | yes, shared foot |
| BTX5 | back, legs | Flat, Zero-G, Anti-Snore | Head massage step, Foot massage step, Massage mode step, Massage timer 20 min | toggle | no |
| BTX5FH | back, legs | Flat, Zero-G, Anti-Snore | Head massage step, Foot massage step, Massage mode step, Massage timer 20 min | toggle | yes, shared foot |
<!-- /generated -->

Every model has two memory slots, recalled and saved with one write.
The declared three-second save duration is unused by the shipped sender.
BT2000's screen has no preset buttons. BT3000 has no ordinary TV button;
BT3000FH has TV instead of anti-snore. BT2500's displayed light button throws
before writing, so no light entity is created for that model.

<!-- generated:bedtech-app-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Action | Code | Frame (bank 0) | Timing |
|---|---|---|---|
| Head up | `24` | `6E 01 00 24 93` | 100 ms until release |
| Head down | `25` | `6E 01 00 25 94` | 100 ms until release |
| Feet up | `26` | `6E 01 00 26 95` | 100 ms until release |
| Feet down | `27` | `6E 01 00 27 96` | 100 ms until release |
| Flat | `31` | `6E 01 00 31 A0` | once |
| Zero-G | `45` | `6E 01 00 45 B4` | once |
| Anti-Snore | `46` | `6E 01 00 46 B5` | once |
| Massage toggle | `5D` | `6E 01 00 5D CC` | once |
| Massage off | `5E` | `6E 01 00 5E CD` | once |
| Head massage step | `4C` | `6E 01 00 4C BB` | once |
| Foot massage step | `4E` | `6E 01 00 4E BD` | once |
| Massage mode step | `48` | `6E 01 00 48 B7` | once |
| Light toggle | `3C` | `6E 01 00 3C AB` | once |
| Massage timer 20 min | `63` | `6E 01 00 63 D2` | once |
| TV | `58` | `6E 01 00 58 C7` | once |
| Pillow up | `3F` | `6E 01 00 3F AE` | 100 ms until release |
| Pillow down | `40` | `6E 01 00 40 AF` | 100 ms until release |
| Lumbar up | `41` | `6E 01 00 41 B0` | 100 ms until release |
| Lumbar down | `42` | `6E 01 00 42 B1` | 100 ms until release |
| Memory 1 recall | `2E` | `6E 01 00 2E 9D` | once |
| Memory 1 save | `2B` | `6E 01 00 2B 9A` | once |
| Memory 2 recall | `2F` | `6E 01 00 2F 9E` | once |
| Memory 2 save | `2C` | `6E 01 00 2C 9B` | once |
<!-- /generated -->

FH head controls use bank 0 for Left and bank 1 for Right. Both heads use the
app's fixed combined commands. Only BT3000FH provides synchronized head-down;
BTX4FH and BTX5FH reject it without a write, so lower each head individually.
Only BT3000FH provides secondary Flat, Zero-G, TV and light toggle. The other
FH models reject those secondary actions. FH memory and massage remain in
bank 0, even when Right is selected. They never use the unused `memory2` table.
Foot movement remains shared. Every FH command replaces the single physical
refresh timer, and STOP from either head ends activity on both banks. These
are model gates, not inferred hardware features.

The legacy route still offers its old Lounge, light off and pillow controls.
Their codes were previously exposed in response to hardware reports. Explicit
7.1.3 models do not expose those unused catalog actions. In particular `)`/`*`
mean **both heads** in this app, and BT6500 pillow uses `?`/`@`, lumbar `A`/`B`.
The old integration labels stay confined to Legacy. Unused head/foot massage-down,
direct mode/wave commands and 10/30-minute timers do not acquire entities.

#### Timing

Explicit app models refresh movement every **100 ms**, with no release packet.
Every new app-model command replaces the previous stream on that physical
receiver, including a light or massage action. A normal HA press uses the
configured finite pulse count. A renewable hold
continues at the same cadence until release or its 30-second ceiling. STOP,
cancellation, disconnect and unload end the refresh through the HA scheduler.
The `^` packet is massage off on models whose UI offers it, not movement STOP.
No retry replays a rejected app command. Writes are serialized and await GATT
completion; a slow link does not build the Android app's pending-write backlog.

Legacy keeps its finite pulses and `^` compatibility STOP from BT6500 reports.
The one-shot preset, memory, massage and light actions do not repeat.
The app's setup test raises the head for two seconds, stops refresh, and schedules
disconnect 500 ms later. HA setup only checks the connection. Explicit
`bedtech_app_command` with `action: connectionTest` raises the first head for
two seconds and uses HA's configured connection handoff, so a delayed Android
disconnect callback cannot interrupt a newer operation.

#### Notifications

No app initialization frame, notification subscription, position parser, read
query, pairing/PIN handshake, MTU negotiation or bed acknowledgement is present.
GATT write completion is not bed state. The 20-minute massage button sends one command and offers no invented Off
option or state feedback.
There are no inferred position sensors or sliders.

#### Services

`bedtech_app_command` exposes the app's sleeper selector. Target the paired parent
for a two-receiver bed. Selectors 1/2 select one receiver, 3 both, 4/5 select one
head while sending foot actions and STOP to both receivers. This includes foot
massage. FH selectors 4/5 select the first/second head on one link; 3 selects both
heads. Other FH actions retain their documented bank and model guards.
A conflicting child target and sleeper selector is rejected before any write.
Movement remains a finite pulse operation; standard `timed_move` provides holds.
See [the action reference](../SERVICES.md#bedtech-app).

#### Evidence

Accepted unit095 APK Protocol Audit and independent audit001: `com.bedtech`
7.1.3 (14), nine model routes and 148 frozen literal vectors. The Richmat codec
reproduces every literal byte for byte, including bank 1. All 585 app
model/action/side routes are retained as focused test vectors. Hardware remains
unverified for the explicit profiles, including cessation of movement after
refresh ends, bank mapping, memory saves and the timer20 button.

Artifact SHA-256: `0d529e90a1d134c9f2e1ff5d3966616ec8f4c01ec63d7e9e79974d8f7e2137a2`.
Report manifest SHA-256: `d196849c2c9463ac6bbd929eea3070d0e8f234aa511362284508a9c9cdc945fd`.
The earlier BedTech 7.1.3 Hermes checks (2026-07-10, issue #410) established
write-with-response; the contrary light/Lounge experiment in issue #243 did
not describe the official app's write mode. The legacy field-report behavior
remains available independently of the explicit app profiles.

### L&P MlRM

**App:** [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) 2.3.25, `com.richmat.lp2`

**Status:** ✅ Tested

Behaves as the Richmat remotes route with WiLinke framing on W1, except as below.

#### Setup

The `leggett_wilinke` bed type, and the `mlrm` app profile of `leggett_platt`.
Detection: name prefix `MlRM` with a WiLinke service. Writes use the W1 write
characteristic `d44bc439-abfd-45a2-b575-925416129600` with response. See
[Leggett & Platt](leggett-platt.md) for the other Leggett variants.

#### Controls

- Discrete massage: head and foot up/down, overall intensity up/down, wave and
  pattern step, head/foot toggles and Stop Massage, instead of the Richmat step
  commands. See [Fixed-table buttons](#fixed-table-buttons).
- Massage timer select: 10, 20 or 30 minutes; 0 sends Stop Massage. The timer
  state is optimistic: the bed reports nothing, so the physical remote can make
  it stale.
- Lights are toggle-only.
- Motor buttons instead of covers (`has_discrete_motor_control`).
- The app also has save codes for Zero-G `66`, Anti-Snore `69`, TV `64` and
  Lounge `65`; the integration does not send them.

#### Timing

Presets and memory recall are held, then released with STOP; the repeat count and
interval are in [Fixed-table routes](#fixed-table-routes).

#### Evidence

L&P MlRM sends only its frozen frames, the pre-v5 controller's.

### RMControl

**App:** [RMControl](https://play.google.com/store/apps/details?id=com.richmat.rmcontrol2) 21.3.7, `com.richmat.rmcontrol2`

**Status:** ❓ Needs testing (source-verified against RMControl 21.3.7, hardware unverified)

These opt-in profiles preserve the app's exact product choices and individual
button commands. Movement, preset, memory, massage, light and extra-action
opcodes are per product: they come from the RMControl catalog in
[`beds/rmcontrol/profiles.py`](../../custom_components/adjustable_bed/beds/rmcontrol/profiles.py),
with separate short, long-press and Nordic short opcodes. An action absent from,
or ambiguous in, the selected catalog is rejected.

#### Setup

- Beds whose RMControl product code is in the app's catalog. An app product
  code identifies a remote layout, not a guarantee that every bed using the same
  Bluetooth service supports the same controls.
- BLE sleep products: the ten source-listed products get the sleep-discovery
  query; HNRN, HQRN, HSRN, HURN, M7RN and MJRN support automatic snore
  intervention.
- Standing-desk-only products (FWRM, WFRM) use a separate desk protocol and are
  rejected.

In Home Assistant, answer the Richmat question with **RMControl app** (see
[Home Assistant setup](#home-assistant-setup)), or opt an existing Richmat entry
in under **Configure**:

- **RMControl product** (`rmcontrol_product`) **None** keeps the existing
  Richmat remote behavior. Existing entries are not automatically migrated.
- To opt in, choose the exact product code used in RMControl. Do not select a
  similar-looking product to unlock unsupported controls. Empty catalogs remain
  empty, and standing-desk-only products are not offered. The product needs the
  Auto, Nordic or WiLinke dialect; setup and Configure refuse Prefix55 and
  PrefixAA.
- Set **RMControl side** (`rmcontrol_side`) to `left`, `right` or `both`. The
  default is `left`. This selects the app's command side, not a new Bluetooth
  address. A paired-bed service's optional `side` selects which paired controller
  receives the operation; it does not add a side byte to specialized packets.

- The controller discovers the selected transport's actual service, writable
  characteristic and notification role. Exactly one known writable transport
  must be present (W1, W2, W3, W4, W5, then N1, which is unframed).
- Writes use response unless the characteristic offers write without response.
- It does not broaden automatic discovery to every device advertising a shared
  Bluetooth service.

Connection setup subscribes to the notification role, then sends:

<!-- generated:rmcontrol-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | Sent when | Frames |
|---|---|---|
| Exit limit | always | `6E 02 01 00 71` (Nordic `00`) |
| Time sync | the product has an alarm catalog | extended `08 02 01` then `08 03 01` |
| Sleep-advertisement query | a BLE sleep product | extended `06 03 00`: `00` |
| Check clock | always | `6E 08 01 01 78` (Nordic `01`) |
| Check light | always | `6E 0A 00 01 79` (Nordic `01`) |
<!-- /generated -->

It then waits up to 5 seconds (an integration readiness budget, not an on-wire
interval) for the light, alarm and sleep-advertisement replies the product
expects. Some beds omit optional
replies; basic controls stay usable and late replies are accepted.

#### Controls

Standard movement, presets, memory programming, massage and lighting appear
where the selected catalog supports them. Additional catalog actions are exposed
as **disabled-by-default buttons**. Enable the relevant entities in the device's
entity list.

- Button names retain the app getter/context and occurrence number where needed
  to distinguish variants. Long-press actions have separate buttons; held
  movement uses cancellable repeats and protocol-specific release cleanup.
- This includes supported combined/extra motor commands and less common heating,
  fan, airbag, anti-pinch, aroma, music and sleep actions. It does not invent
  parameterized controls merely because the shared library can parse a report.
- Phone flashlight, menus, headings, desk-only and sofa-specific controls are
  excluded.
- Head and foot massage strength actions appear as intensity up/down controls
  when the selected product provides both directions. A product with only a
  strength-increase action retains its named product button; it does not expose
  that action as a zone on/off toggle.

Sensors and binary sensors are added when their corresponding state is first
reported, rather than creating permanently unknown entities for every catalog.
Diagnostics retain the selected product, transport, capability replies, decoded
state, supported alarm action names and all received alarm records. Reported
numeric values without proven units are deliberately unitless. A numbered motor
is not silently relabeled as a particular physical axis.

##### Lighting

- RGB starts unknown until a color report arrives.
- Where supported, the light timer offers **Always On** and **1 through 15
  minutes**. Always On uses the app's `ff ff` timeout representation.
- A generic light capability alone is not a promise of RGB support. Color and
  timer controls require the app's light acknowledgment and selected strip flag.
- PARN accepts only its eight source-defined colors, listed as exact RGB tuples
  in diagnostics; other colors are rejected.

| Command | Frame | Description |
|---------|-------|-------------|
| Action (framed) | `6e 01 side cmd SUM` | Short or long-press opcode |
| Action (Nordic) | `cmd` | Nordic short opcode, or the long-press opcode |
| STOP / release | `6e 01 side 6e SUM` (Nordic: `6e`) | Sent after every sustain press with a fresh cancel event |

Light timer: seconds, 0 sends `ff ff` (Always On). See
[Variable frames](#variable-frames) for alarms, time sync and snore intervention;
`repeat_mask` uses bit 7 for Monday through bit 1 for Sunday.

#### Timing

See [Catalog app timing](#catalog-app-timing).

#### Notifications

Frames must start with `6e` and carry a valid additive checksum; unknown or
malformed frames have no effect.

| Frame | Meaning |
|-------|---------|
| `6e09010078`, `6e0e00037f`, `6e1a000189`, `6e16010186`, `6e90c101c0`, `6e2100008f` | Alarm, light, aroma, music, detection and anti-snore capability |
| `6e07010177` / `6e07010278` | Single alarm added / cancelled |
| `6e23018416` / `6e23008415` | Locked / unlocked |
| `6e23a06e9f` | Anti-snore stop music |
| `6e 90 selector value SUM` | Protocol version, bed mode, motor (number, status, angle), massage mode/strengths, music, detection status, component diagnostics |
| `6e 20 len …` | Extended reports: diagnostics, sleep advertisement, RGB, light timer, white light, lock, press mode, fan, aroma, heating, massage, motor travel, motor angle, alarm records |

The receive buffer assembles fragmented or coalesced notifications and discards
a partial frame after 500 ms without new data, as the app's timer does.

#### Services

##### Alarm service

Use `adjustable_bed.rmcontrol_alarm`, selecting the device and operation. It
requires an explicitly selected RMControl profile and the appropriate supported
alarm capability. Action names must come from that device's diagnostics
`alarm_actions` list, not raw bytes or another product's catalog. Ambiguous or
absent actions are rejected before writing.

| Operation | Additional fields | Effect |
| --- | --- | --- |
| `single` | `minutes` (1..65535), `action` | Run the selected action after a countdown measured in minutes. |
| `cancel_single` | None | Cancel the countdown alarm. |
| `repeat` | `alarm_id` (1..7), `time`, `weekdays`, `action` | Create or replace the selected repeating-alarm slot at local time, with minute precision. |
| `delete` | `alarm_id` (1..7) | Delete that repeating-alarm slot. |
| `query` | None | Request repeating-alarm records; received records appear in state/diagnostics. |
| `sync` | None | Send current Home Assistant time, timezone and local calendar values to the supported alarm subsystem. |

- `weekdays` uses `monday` through `sunday`; it is not a raw bit mask.
- An optional `side` accepts `left`, `right` or `both` for paired-bed targeting.
- Replacing a slot changes the alarm stored on the bed, not merely a Home
  Assistant automation.
- A **single alarm is a countdown**, not a wall-clock alarm or time-sync
  operation.
- The separate synchronization protocol encodes timezone offsets in whole hours,
  truncated toward zero. Half-hour and quarter-hour offsets cannot be represented
  fully; this is a source-proven limitation, not an automatic adjustment by HA.
- New alarm creation resolves the current selected product's effective command,
  including its override. It does not reproduce the app's separate restoration
  path that can discard an override.

The app's single and repeating alarm pages are distinct. An alarm acknowledgment
and nonempty selected `alarmList` normally enable the menu; PNRN has the app's
explicit initial-menu exception. The exact product flag then chooses single or
repeating operations. An empty action list never permits arbitrary alarm actions.
Time synchronization has its own condition, a nonempty `alarmList`, and is also
performed during connection setup independently of the repeating-alarm flag.

##### Automatic snore intervention

Use `adjustable_bed.rmcontrol_anti_snore`. This is separate from moving to the
anti-snore preset position.

| Operation | Additional fields | Effect |
| --- | --- | --- |
| `switch` | `enabled` (boolean) | Enable or disable supported automatic snore detection/intervention. |
| `configure` | `mode` (`count` or `time`), `value` (0..255) | Set the app's intervention count or time value. |
| `query` | None | Request the enable state and intervention configuration. |

- The service also accepts the paired-bed `side` field.
- The time mode deliberately does not claim seconds or minutes where the
  artifact does not establish that unit.
- Configuring count/time is not equivalent to enabling the feature.

This service requires the app's BLE sleep-monitoring metadata, a received sleep
advertisement event and one of its six supported selectors: HNRN, HQRN, HSRN,
HURN, M7RN or MJRN. The connection setup queries sleep discovery only for the
ten source-listed BLE sleep products. A generic snore state report is not enough
to activate automatic intervention.

#### Evidence

RMControl sends the frames of the selected product's catalog, source-verified
against RMControl 21.3.7 and hardware unverified. The service list is not a
promise that every product supports those features; a rejected operation must not
be worked around by choosing an unrelated product. Evidence: APK Protocol Audit
row018.

### Richmat MH apps

**App:** Revive Control 1.0.26, Best Mattress 1.1.1, Blvd Home 1.0.1, HARMONY 1.0.0 and Idealbed 2.4.2 (see [Apps](#apps))

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

#### Setup

RUF \| Betten Motor 2, W.Silver Products, AMERICANSTAR, Bailey's Bed Control and
TX use the same library with their own catalogs, release rules and extra pages;
see [their guide](ruf-richmat-apps.md).

Revive Control, Best Mattress, Blvd Home, HARMONY and Idealbed share one BLE
library. Their model catalogs, page gates and a few callbacks differ, so each
app is its own explicit bed type and profile. Motor, preset, memory, massage and
page-button opcodes are per model: they come from the generated catalog
[`beds/richmat_mh/catalog.py`](../../custom_components/adjustable_bed/beds/richmat_mh/catalog.py)
(app route, kind, page, app label, opcode, and KEEP interval or 0 for a single
tap). Each is sent as `6e 01 M C SUM`.

These profiles are opt-in: the shared Richmat services and names never select
them automatically, and existing Richmat remote or RMControl entries are not
changed.

1. Answer the Richmat question with the app your phone uses (for example
   **Revive Control app**). Motor count is fixed at two; the model decides
   which motors exist.
2. Keep the model on Auto to apply the app's name rule: the first
   four characters of the raw Bluetooth name, lowercased, name the model
   (`7IRM…` selects `7irm`). The raw name is stored at setup.
3. Choose an explicit model (`model_<id>`) when the app would ask:
   names starting with `QRRM`, Idealbed names starting with `Cool Touch`, or a
   name with no live model. The variants list exactly the app's picker, setup
   wizard and manual model routes; Idealbed's manual dialog accepts any valid
   model identifier, so every Idealbed model is offered. Labels are the app's
   where the analysis recorded them, otherwise the model identifier.

- Setup and Configure report a name the app cannot resolve on the model question.
- Each side of a two-address pair keeps its own app and model. Change a side's
  model under its receiver settings; unpair to change its app.

The controller follows the app's GATT selection (Nordic UART, then the fee9 and
ffe0/fff0 maps, then a fallback service; see [Transports](#transports)) and keeps
the characteristic's write type. The fallback skips the generic access and
attribute services (`00001800`, `00001801`).

After subscribing it sends the version query, then the version's initialization
list (timing in [Catalog app timing](#catalog-app-timing)):

<!-- generated:richmat-mh-setup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | VER0 | VER1 |
|---|---|---|
| Version query | `6E 9A 00 00 08` | `6E 9A 00 00 08` |
| Exit one-minute | `6E 02 01 00 71` | `6E 02 01 00 71` |
| Alarm | `6E 08 01 01 78` | `6E 08 01 01 78` |
| LED | `6E 0A 00 01 79` | `6E 0A 00 01 79` |
| Aroma | `6E 1A 00 00 88` | `6E 1A 00 00 88` |
| Mattress | `5E 1A 00 01 79` | `5E 1A 00 01 79` |
| Waist mattress | `5E 1B 00 01 7A` | `5E 1B 00 01 7A` |
| Snore | `6E 21 00 00 8F` | `6E 21 00 00 8F` |
| Speech | `6E 22 00 00 90` | `6E 22 00 00 90` |
| Detection | `6E 9A C0 00 C8` | none |
| Motor mode | none | `6E 9A 10 00 18` |
| Motor 1 angle | none | `6E 9A 30 01 39` |
| Motor 2 angle | none | `6E 9A 30 02 3A` |
| Motor 3 angle | none | `6E 9A 30 03 3B` |
| Motor 4 angle | none | `6E 9A 30 04 3C` |
| Massage query | none | `6E 9A A0 00 A8` |
| Button-light lock query | none | `6E 9A B0 00 B8` |

The app's mattress literal ends in checksum `90`; the sender recomputes its
checksum, so the bed receives the frame above.
<!-- /generated -->

When a VER1 reply mounts the alarm call page during setup, the phone clock is
sent once (as the app's alarm call page does on creation).

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

##### Home Assistant setup

Answer the Richmat question with the app your phone uses, for example **Revive Control app**. Shared Richmat names and services never select these profiles. `auto` applies the app's name rule: the first four characters of the raw Bluetooth name, lowercased, select the model. Names starting with `QRRM` (and Idealbed names starting with `Cool Touch`) make the app ask, so choose the model variant (`model_<id>`, labelled as in the app's picker, wizard or manual list). The form reports a name the app cannot resolve. Motor count is fixed; the model's catalog decides the motors, and each control keeps the app's KEEP interval. The model belongs to each physical bed: change it under that receiver's settings in a two-address pair.

#### Controls

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

<!-- generated:richmat-mh-fixed -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Frame (single-device group) |
|---|---|
| STOP | `6E 01 00 6E DD` |
| Button light off (Revive Control, Best Mattress) | `6E 01 00 75 E4` |
| Smart set lock toggle, once | `6E 01 00 84 F3` |
| Start detection | `6E 88 C2 10 C8` |
| Stop detection | `6E 88 C2 20 D8` |
| Cancel alarm (single-slot models) | `6E 05 00 00 73` then `6E 06 00 00 74` |
<!-- /generated -->

| Command | Frame | Values |
|---------|-------|--------|
| Motor angle target | `6e 88 (30\|bits<<2) angle SUM` | Absolute angle |
| Massage intensity | `6e 88 a0 ((foot&7)<<3 \| head&7) SUM` | Both zones at once |
| Motor mode | `6e 88 (10\|bits<<2) 00 SUM` | LEFT 1, RIGHT 2, Mode1 1, Mode2 2, Mode3 3 |

| Command | Frame | Values |
|---------|-------|--------|
| Colour | `6e 0c ff R s1` + `6e 0d G B s2` | One 10-byte write, RGB 0-255 |
| Light timeout | `6e 0b HH LL SUM` | Seconds; zero or less sends `ff ff` (always on). The entity-page variant replaces `HH` with `txMode` |

| Command | Frame |
|---------|-------|
| Snore intervention | `6e 13 M code SUM` (code 0 turns it off) |
| Start detection | `6e88c210c8` |
| Stop detection | `6e88c220d8` |

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

`6e fn (b0+b1) (b2+b3) SUM` over the value's little-endian 32-bit bytes, with
`fn` `1b` (mode 2 startup, minutes), `1c` (mode 3 startup, minutes) and `1d`
(mode 3 pause, hours).

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

#### Timing

See [Catalog app timing](#catalog-app-timing). KEEP intervals are per control, in
the catalog.

#### Notifications

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

#### Services

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

#### Evidence

The Richmat MH apps send only frames frozen from their accepted row055 reports,
which record the evidence and every exclusion. Real users should confirm model selection by
name, KEEP/STOP behavior, alarm countdown semantics, LED timeout units and the
waist mattress controls after a beta or release.

`tools/generate_richmat_mh_catalog.py` builds `beds/richmat_mh/catalog.py` from the
machine-local frozen reports (hash-pinned). It reads them from `--phase4-dir`,
`$ADJUSTABLE_BED_PHASE4_DIR`, `disassembly/output/phase4-early` in the checkout,
or the main checkout of a linked worktree; `--check` verifies the committed file
and reports missing inputs instead of failing with a traceback.

### HJBed

**App:** [HJBed](https://play.google.com/store/apps/details?id=com.richmat.hjbed) 2.1.2 (code 21200), `com.richmat.hjbed`

**Status:** ❓ Needs testing (static app evidence; physical behavior, ATT and firmware acceptance unverified)

#### Setup

Choose the **HJBed app** row, then search its product question for the exact
product shown in HJBed. It lists all 19 current products and 24 conditionally
restored products, and nothing is preselected. Shared services and
Bluetooth names do not identify the layout.

| HA product profile | App label | Remote code | App selector |
| --- | --- | --- | --- |
| `aw_motionhc800` | HC800 | `LTRM` | Conditional |
| `aw_motionsn300` | SN300 | `B3RN` | Conditional |
| `aw_motionsn500` | SN500 | `LTRM` | Conditional |
| `dream_blue` | blue | `LTRM` | Conditional |
| `dream_green` | green | `HARM` | Conditional |
| `dream_orange` | orange | `JMRM` | Conditional |
| `dream_yellow` | yellow | `HBRM` | Conditional |
| `flexxafeg300` | AFEG300 | `L5RN` | Conditional |
| `flexxafeg300sh` | AFEG300-SH | `LPRN` | Conditional |
| `flexx_linkrfrn` | FlexxLink | `RFRN` | Conditional |
| `flexxpb250` | PB250 | `VJRM` | Conditional |
| `flexxpb300` | PB300 | `FARM` | Conditional |
| `flexxpb325` | PB325 | `FARM` | Conditional |
| `flexxpb450` | PB450 | `MPRM` | Conditional |
| `flexxpb450sh` | PB450-SH | `LVRN` | Conditional |
| `hj_bedbjrn` | BJRN | `BJRN` | Current |
| `hj_bedbyrn` | BYRN | `BYRN` | Current |
| `hj_bedd4rn` | D4RN | `D4RN` | Current |
| `hj_bedd5rn` | D5RN | `D5RN` | Current |
| `hj_bedd6rn` | D6RN | `D6RN` | Current |
| `hj_bedd7rn` | D7RN | `D7RN` | Current |
| `hj_bede3rm` | E3RM | `E3RM` | Current |
| `hj_bedfarm` | FARM | `FARM` | Current |
| `hj_bedhzrm` | HZRM | `HZRM` | Current |
| `hj_bedjgrm` | JGRM | `JGRM` | Current |
| `hj_bedjhrm` | JHRM | `JHRM` | Current |
| `hj_bedjjrm` | JJRM | `JJRM` | Current |
| `hj_bedkzrm` | KZRM | `KZRM` | Current |
| `hj_bedl2rm` | L2RM | `L2RM` | Current |
| `hj_bedrern` | RERN | `RERN` | Current |
| `hj_bedtyrn` | TYRN | `TYRN` | Current |
| `hj_bedtzrn` | TZRN | `TZRN` | Current |
| `hj_beduurn` | UURN | `UURN` | Current |
| `hj_bedvjrm` | VJRM | `VJRM` | Current |
| `likomioabm10` | ABM10 | `UTRM` | Conditional |
| `motionnxca200` | Series 1 | `GURN` | Conditional |
| `motionnxca300` | Series 2 | `GVRN` | Conditional |
| `motion_opus` | Series 3 | `GWRN` | Conditional |
| `muuegmabf03` | ABF03 | `BNRN` | Conditional |
| `muuegmabf07` | ABF07 | `DNRN` | Conditional |
| `muuegmnupg400` | NUPG400 | `BVRN` | Conditional |
| `velocityvip3` | VIP 3.0 | `` | Conditional |
| `velocityvip3sh` | VIP 3.0-SH | `` | Conditional |

- Choose the explicit app and product profile; configure two-address sides separately.
- Bluetooth scan candidates contain case-sensitive `QRRM`, `COOL`, `MPE_`, `209A` or `ZRA1`.
- HA's indexed name hints match those prefixes. Service/manual detection still accepts the keywords anywhere in a name.
- Names with an earlier prefix and no eligible advertised service use manual device selection. HA rejects leading-wildcard manifest matchers.
- E0FF uses name hints or manual selection because non-bed devices share it; all six listed transports work after explicit selection.
- HA provides discovery and an explicit device/product picker. Names are scan hints, not capability evidence.
- Phone text/QR input searches the current 19 remote codes; persisted display keys use exact case-sensitive first-match selection.
- HA stores an explicit profile per physical device, so ambiguous remote codes cannot change its layout.
- The two later FlexxLink objects are shadowed by the first RFRN display-key match and are not independent selectable profiles. `None` is unused as a control profile.
- No layout or feature is inferred from a generic Richmat remote table.

Write selection requires `write`. A selected `write-without-response` property
uses writes without response; otherwise writes use response. Selection retains
the first eligible write and first notify, while the last matched service decides
the generic packet mode. HA/Bleak handles MTU negotiation without an arbitrary override.

##### Home Assistant setup

Choose HJBed and the exact app product. Its profile owns layout, massage, timing and angle-sensor settings. The local Normal/Motion layout choice and acknowledged single-alarm preferences are persisted per physical receiver/profile. This profile section lists all current and conditional profiles.

#### Controls

Covers represent actual selected up/down pairs. A lone combined-up action remains
a button, without inventing combined-down. Named buttons retain each product's
preset, save, massage, light, sync and sofa controls. All eight independent
MusicPage actions are available, including next/previous, even when the
profile has no music tab. Music packets always use left 0, as configured.

The pulse count bounds a normal HA action. The card uses a bounded held action;
its release button cancels refresh and runs that action's own cleanup. Motors,
normal reset, bed light and massage send their configured STOP where applicable.
Presets and sofa reset end refresh without an extra STOP. Sofa lamp and music
send once without STOP. BJRN preset programming waits three seconds; other
programming sends its long code once. Explicit Stop remains available separately.
Native cover Stop uses the selected side's shared Stop action, so card ownership
is cleared across that side's motor controls. Cross-axis firmware effects remain
unverified.
The **HJBed layout** local select chooses Normal or the conditionally named Motion
layout; Motion reset is a short action and its mode query has a narrower gate.

Short controls with a release callback send once on down, wait for release, then
perform cleanup; holding them does not turn them into repeated commands. Native
single-address paired side controls are offered only by the four coupled profiles.

The `hold_control` action accepts a listed `hjbed_*` control and a finite duration
up to 60 seconds. Sub-100 ms sustained actions send nothing. Save and recall are
separate actions, so holding recall never overwrites a memory.
Finite pulse actions share a deadline allowing one 100 ms pacing slot per
selected side after the final nominal tick. Explicit held durations keep their
requested end. Card release works for standalone,
single-address side controls and two-address pairs.

Values below come from the shipped `beds/hjbed/controller.py` controller and its imported
catalog/packet builders. Detail IDs distinguish product-specific variants. Each
product exposes only its selected controls. The full profile bindings are in the
[HJBed catalog](../../custom_components/adjustable_bed/beds/hjbed/catalog.py). Exit limit
and the clock, light and music menu probes use [function selectors](#function-selectors);
in single-code mode they send `00` and `01`.

<!-- generated:hjbed-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

##### Motor Control

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Foot Box Down (`975861`) | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | Refresh 100 ms; STOP |
| Foot Box Up (`9758e1`) | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | Refresh 100 ms; STOP |
| Foot Down (`9740e1`) | `27` | `6E 01 00 27 96` | `6E 01 01 27 97` | Refresh 100 ms; STOP |
| Foot Up (`974161`) | `26` | `6E 01 00 26 95` | `6E 01 01 26 96` | Refresh 100 ms; STOP |
| Head And Foot Down (`9743e1`) | `2A` | `6E 01 00 2A 99` | `6E 01 01 2A 9A` | Refresh 100 ms; STOP |
| Head And Foot Up (`974461`) | `29` | `6E 01 00 29 98` | `6E 01 01 29 99` | Refresh 100 ms; STOP |
| Head Down (`9741e1`) | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | Refresh 100 ms; STOP |
| Head Up (`974261`) | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | Refresh 100 ms; STOP |
| Lumbar Down (`973fe1`) | `40` | `6E 01 00 40 AF` | `6E 01 01 40 B0` | Refresh 100 ms; STOP |
| Lumbar Down (`974be1`) | `42` | `6E 01 00 42 B1` | `6E 01 01 42 B2` | Refresh 100 ms; STOP |
| Lumbar Up (`974061`) | `3F` | `6E 01 00 3F AE` | `6E 01 01 3F AF` | Refresh 100 ms; STOP |
| Lumbar Up (`974c61`) | `41` | `6E 01 00 41 B0` | `6E 01 01 41 B1` | Refresh 100 ms; STOP |
| Pillow Down (`973ee1`) | `42` | `6E 01 00 42 B1` | `6E 01 01 42 B2` | Refresh 100 ms; STOP |
| Pillow Down (`974a61`) | `40` | `6E 01 00 40 AF` | `6E 01 01 40 B0` | Refresh 100 ms; STOP |
| Pillow Up (`973f61`) | `41` | `6E 01 00 41 B0` | `6E 01 01 41 B1` | Refresh 100 ms; STOP |
| Pillow Up (`974ae1`) | `3F` | `6E 01 00 3F AE` | `6E 01 01 3F AF` | Refresh 100 ms; STOP |
| Tilt Down (`974fe1`) | `5C` | `6E 01 00 5C CB` | `6E 01 01 5C CC` | Refresh 100 ms; STOP |
| Tilt Up (`975061`) | `5B` | `6E 01 00 5B CA` | `6E 01 01 5B CB` | Refresh 100 ms; STOP |
| Backward (`975461`) | `5C` | `6E 01 00 5C CB` | `6E 01 01 5C CC` | Refresh 100 ms; STOP |
| Forword (`9754e1`) | `5B` | `6E 01 00 5B CA` | `6E 01 01 5B CB` | Refresh 100 ms; STOP |
| Head Down (`975561`) | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | Refresh 100 ms; STOP |
| Head Up (`9755e1`) | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | Refresh 100 ms; STOP |
| Lumbar Down (`975661`) | `40` | `6E 01 00 40 AF` | `6E 01 01 40 B0` | Refresh 100 ms; STOP |
| Lumbar Up (`9756e1`) | `3F` | `6E 01 00 3F AE` | `6E 01 01 3F AF` | Refresh 100 ms; STOP |
| Pillow Down (`975761`) | `42` | `6E 01 00 42 B1` | `6E 01 01 42 B2` | Refresh 100 ms; STOP |
| Pillow Up (`9757e1`) | `41` | `6E 01 00 41 B0` | `6E 01 01 41 B1` | Refresh 100 ms; STOP |

##### Presets

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Anti Snoring (`9738e1`) | `46` | `6E 01 00 46 B5` | `6E 01 01 46 B6` | Once; no extra STOP |
| Anti Snoring (`975961`) | `46` | `6E 01 00 46 B5` | `6E 01 01 46 B6` | Refresh 100 ms; no extra STOP |
| Coaxing Sleep Mode (`9744e1`) | `86` | `6E 01 00 86 F5` | `6E 01 01 86 F6` | Once; no extra STOP |
| Lounge Position (`973961`) | `59` | `6E 01 00 59 C8` | `6E 01 01 59 C9` | Once; no extra STOP |
| Memory Position1 (`973861`) | `2E` | `6E 01 00 2E 9D` | `6E 01 01 2E 9E` | Once; no extra STOP |
| Memory Position1 (`974e61`) | `2E` | `6E 01 00 2E 9D` | `6E 01 01 2E 9E` | Refresh 100 ms; no extra STOP |
| Memory Position2 (`9737e1`) | `2F` | `6E 01 00 2F 9E` | `6E 01 01 2F 9F` | Once; no extra STOP |
| Memory Position2 (`974de1`) | `2F` | `6E 01 00 2F 9E` | `6E 01 01 2F 9F` | Refresh 100 ms; no extra STOP |
| Memory Position3 (`9751e1`) | `30` | `6E 01 00 30 9F` | `6E 01 01 30 A0` | Refresh 100 ms; no extra STOP |
| Memory Position4 (`975261`) | `B2` | `6E 01 00 B2 21` | `6E 01 01 B2 22` | Refresh 100 ms; no extra STOP |
| T V Position (`973a61`) | `58` | `6E 01 00 58 C7` | `6E 01 01 58 C8` | Once; no extra STOP |
| T V Position (`974d61`) | `58` | `6E 01 00 58 C7` | `6E 01 01 58 C8` | Refresh 100 ms; no extra STOP |
| T V Position (`975161`) | `58` | `6E 01 00 58 C7` | `6E 01 01 58 C8` | Refresh 100 ms; no extra STOP |
| Zero Gravity (`9739e1`) | `45` | `6E 01 00 45 B4` | `6E 01 01 45 B5` | Once; no extra STOP |
| Zero Gravity (`974ce1`) | `45` | `6E 01 00 45 B4` | `6E 01 01 45 B5` | Refresh 100 ms; no extra STOP |
| Zero Gravity (`9750e1`) | `45` | `6E 01 00 45 B4` | `6E 01 01 45 B5` | Refresh 100 ms; no extra STOP |

##### Massage

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Massage10 Minute Timer (`973be1`) | `5F` | `6E 01 00 5F CE` | `6E 01 01 5F CF` | Once; STOP |
| Massage20 Minute Timer (`973b61`) | `63` | `6E 01 00 63 D2` | `6E 01 01 63 D3` | Once; STOP |
| Massage30 Minute Timer (`973ae1`) | `61` | `6E 01 00 61 D0` | `6E 01 01 61 D1` | Once; STOP |
| Massage Foot Instensity Strengthen (`973d61`) | `4E` | `6E 01 00 4E BD` | `6E 01 01 4E BE` | Once; STOP |
| Massage Head Instensity Strengthen (`973de1`) | `4C` | `6E 01 00 4C BB` | `6E 01 01 4C BC` | Once; STOP |
| Massage Instensity Strengthen (`974361`) | `34` | `6E 01 00 34 A3` | `6E 01 01 34 A4` | Once; STOP |
| Massage Mode All Off (`973c61`) | `5E` | `6E 01 00 5E CD` | `6E 01 01 5E CE` | Once; STOP |
| Massage Mode Change (`973ce1`) | `48` | `6E 01 00 48 B7` | `6E 01 01 48 B8` | Once; STOP |
| Massage Switch (`9742e1`) | `6F` | `6E 01 00 6F DE` | `6E 01 01 6F DF` | Once; STOP |

##### Lights

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Bed Light (`974961`) | `3C` | `6E 01 00 3C AB` | `6E 01 01 3C AC` | Once; STOP |
| Bed Light Close (`9759e1`) | `75` | `6E 01 00 75 E4` | `6E 01 01 75 E5` | Once; no extra STOP |
| Light Board (`9749e1`) | `50` | `6E 01 00 50 BF` | `6E 01 01 50 C0` | Once; STOP |
| Light (`975361`) | `3C` | `6E 01 00 3C AB` | `6E 01 01 3C AC` | Once; no extra STOP |

##### Music

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Music Blue Tooth Switch (`9748e1`) | `D8` | `6E 01 00 D8 47` | `6E 01 00 D8 47` | Once; no extra STOP |
| Music Next Song (`974661`) | `D3` | `6E 01 00 D3 42` | `6E 01 00 D3 42` | Once; no extra STOP |
| Music Pause Play (`9745e1`) | `D7` | `6E 01 00 D7 46` | `6E 01 00 D7 46` | Once; no extra STOP |
| Music Previous Song (`9746e1`) | `D2` | `6E 01 00 D2 41` | `6E 01 00 D2 41` | Once; no extra STOP |
| Music Shake Mode (`974861`) | `D6` | `6E 01 00 D6 45` | `6E 01 00 D6 45` | Once; no extra STOP |
| Music Switch Sound Track (`975ae1`) | `C4` | `6E 01 00 C4 33` | `6E 01 00 C4 33` | Once; no extra STOP |
| Music Volumu Down (`974761`) | `D5` | `6E 01 00 D5 44` | `6E 01 00 D5 44` | Once; no extra STOP |
| Music Volumu Up (`9747e1`) | `D4` | `6E 01 00 D4 43` | `6E 01 00 D4 43` | Once; no extra STOP |

##### Reset, stop and sync

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Exit Limit (`973761`) | `00` | `6E 02 01 00 71` | `6E 02 01 00 71` | Once; no extra STOP |
| Motor Reset (`973e61`) | `31` | `6E 01 00 31 A0` | `6E 01 01 31 A1` | Once; STOP; Motion once |
| Motor Reset (`974f61`) | `31` | `6E 01 00 31 A0` | `6E 01 01 31 A1` | Refresh 100 ms; STOP; Motion once |
| Stop (`975a61`) | `6E` | `6E 01 00 6E DD` | `6E 01 01 6E DE` | Once; no extra STOP |
| Sync Off (`9752e1`) | `BD` | `6E 01 00 BD 2C` | `6E 01 01 BD 2D` | Once; no extra STOP |
| Sync On (`974b61`) | `BC` | `6E 01 00 BC 2B` | `6E 01 01 BC 2C` | Once; no extra STOP |
| Sit Position (`9753e1`) | `E5` | `6E 01 00 E5 54` | `6E 01 01 E5 55` | Refresh 100 ms; no extra STOP |

##### Memory

Save is available only for selected preset details with a long code. BJRN waits
three seconds; other product saves send once immediately. Recall and save remain
separate actions.

| Save command (detail) | Single code | Framed left | Framed right |
|---|---|---|---|
| Anti Snoring (`9738e1`) | `69` | `6E 01 00 69 D8` | `6E 01 01 69 D9` |
| Anti Snoring (`975961`) | `69` | `6E 01 00 69 D8` | `6E 01 01 69 D9` |
| Coaxing Sleep Mode (`9744e1`) | `89` | `6E 01 00 89 F8` | `6E 01 01 89 F9` |
| Lounge Position (`973961`) | `65` | `6E 01 00 65 D4` | `6E 01 01 65 D5` |
| Memory Position1 (`973861`) | `2B` | `6E 01 00 2B 9A` | `6E 01 01 2B 9B` |
| Memory Position1 (`974e61`) | `2B` | `6E 01 00 2B 9A` | `6E 01 01 2B 9B` |
| Memory Position2 (`9737e1`) | `2C` | `6E 01 00 2C 9B` | `6E 01 01 2C 9C` |
| Memory Position2 (`974de1`) | `2C` | `6E 01 00 2C 9B` | `6E 01 01 2C 9C` |
| Memory Position3 (`9751e1`) | `2D` | `6E 01 00 2D 9C` | `6E 01 01 2D 9D` |
| Memory Position4 (`975261`) | `B3` | `6E 01 00 B3 22` | `6E 01 01 B3 23` |
| T V Position (`973a61`) | `64` | `6E 01 00 64 D3` | `6E 01 01 64 D4` |
| T V Position (`974d61`) | `64` | `6E 01 00 64 D3` | `6E 01 01 64 D4` |
| T V Position (`975161`) | `64` | `6E 01 00 64 D3` | `6E 01 01 64 D4` |
| Zero Gravity (`9739e1`) | `66` | `6E 01 00 66 D5` | `6E 01 01 66 D6` |
| Zero Gravity (`974ce1`) | `66` | `6E 01 00 66 D5` | `6E 01 01 66 D6` |
| Zero Gravity (`9750e1`) | `66` | `6E 01 00 66 D5` | `6E 01 01 66 D6` |
<!-- /generated -->

#### Timing

See [Catalog app timing](#catalog-app-timing).

- Sustained controls start at the first refresh tick and use monotonic tick deadlines.
- Writes are serialized with the minimum spacing; write latency does not accumulate in the refresh interval.
- Both-side frames share one bounded hold window. Stale refreshes are dropped; an in-flight write and required cleanup may finish after the window.
- Every attempted side retains its own release, including when another side's release fails.
- Startup follows [HJBed startup](#hjbed-startup).

##### HJBed startup

<!-- generated:hjbed-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | When | Framed | Single-code |
|---|---|---|---|
| Exit limit | first | `6E 02 01 00 71` | `00` |
| Time sync | next, two frames | extended `08 02 01` then `08 03 01` | same |
| Control mode query | blue, green and orange; green and orange only in the Motion layout | `6E 08 20 0B 02 00 00 A3` | same |
| Clock menu probe | +300 ms | `6E 08 01 01 78` | `01` |
| Light menu probe | +600 ms | `6E 0A 00 01 79` | `01` |
| Music menu probe | +900 ms | `6E 15 01 01 85` | `01` |

Probe offsets count from the start of the menu request, after the exit frame.
<!-- /generated -->

#### Notifications

**HJBed status** exposes the last event, structured `hjbed_events`, complete
`hjbed_alarms`, `hjbed_saved_alarm`, host-only `hjbed_available_alarm_slots` and
parser rejection information. Bed
observations include motor travel/angles/height, version/control modes, massage,
white/RGB lighting, music, snore/off-bed/name/locks, coaxing, aroma, heating, fan,
blanket and detection data. These passive readings do not enable an outbound
command. Raw values are retained where physical units or motor mappings are not
proven. Position seeking is not inferred from those observations.

The six service/write pairs are in `beds/hjbed/controller.py:GATT`. The first
eligible write and first notify characteristic are retained in returned order;
the last matched service decides single-code versus framed generic commands.
Write selection requires `write`, notification selection requires `notify`.
The response policy follows that characteristic's write-without-response flag.
HA/Bleak owns connection setup, adapters, proxies and MTU negotiation. There is
no app-owned PIN, challenge, authentication or bonding exchange to reproduce.

Generic packets are one command byte on the selected Nordic mode, otherwise
`6e 01 side code sum8`. Exit and three menu probes have exact separate prefixes.
Variable outbound frames are `6e length 20 ... sum8`; inbound extended frames
place length after `20` or `21`. Every final integer is masked to eight bits.
Clock synchronization uses timestamp/calendar from one snapshot and timezone
from a second snapshot, with whole-hour offset truncation.

Complete inbound frames are destructively split before dispatch. Earlier emitted
state survives a later parser/callback failure; failing and later local frames
are not replayed. Retained incomplete bytes receive a 500 ms timer only after
successful dispatch. Common frames retain their individual checksum and
chunk behavior. Zero-length nonprogress input is rejected safely.

#### Services

Variable builders below always retain their full frames, including in single-code mode.
These are exact examples from the shipped builders; fields vary with the requested values.

| Operation and example input | Exact GATT write(s) |
| --- | --- |
| Single alarm: 1440 minutes, code `45` | `6e05a00013`; `6e060545be` |
| Cancel single alarm | `6e05000073`; `6e06000074` |
| Light timeout: 600 seconds | `6e0b0258d3` |
| Light always on: 0 seconds | `6e0bffff77` |
| RGB: 11, 22, 33; one combined write | `6e0cff0b846e0d1621b2` |
| Repeat alarm: slot1, kind0, 07:30, code45, Monday enabled | `6e0d200501010100071e45818e` |
| Delete repeat slot1 | `6e0820050201019f` |
| Query repeat list | `6e0820050100009c` |
| Clock sync: 2026-11-03 12:00:00 +01:00 | `6e0c200802016ae9beb00167`; `6e0d20080301380b030c0000f9` |
| Query control mode | `6e08200b020000a3` |
| Split-head mode0 | `6e09200b02010000a5` |
| Standard mode2 | `6e09200b02010002a7` |


Use `adjustable_bed.hjbed` with `device_id` and `operation`. All selected physical
targets are validated before any configuration write. Generic `side` routing
remains supported; direct variable builders configure the current physical
receiver, while generic motion frames select left 0 or right 1. Music stays left.

| Operation | Fields | Eligibility |
| --- | --- | --- |
| `single` | `time`, `action` | Single-alarm product flag and clock acknowledgement |
| `cancel_single` | none | Same single-alarm gate |
| `repeat` | `time`, `action`, `alarm_id` unless a slot is known free, `weekdays`, `enabled` | Repeat-alarm flag and clock acknowledgement |
| `query`, `delete` | `alarm_id` for delete | Repeat-alarm gate |
| `toggle` | observed `alarm_id`, `enabled` | Repeat-alarm gate |
| `sync` | none | Clock synchronization used by the app's product menu |
| `light_timeout` | `seconds` | Light-page flag and light acknowledgement |
| `light_color` | `rgb_color` | Same light-page gate |
| `mode` | `mode: split_head` or `standard` | Normal layout, blue/green/orange only |

Alarm time uses minute precision. Empty weekdays means once; Monday is bit 7,
Sunday bit 1, enabled bit 0. Use an explicit `alarm_id` from 1 through 7 when
occupancy is unknown. Automatic allocation chooses the smallest slot freed by a
delete in the current connection, provided no later reply reports it occupied.
Availability is rechecked after pacing; a late occupied-slot reply rejects the
automatic create. The slot is reserved before writing, including when write success is uncertain.
Query, reconnect and disconnect clear this knowledge. A full table is rejected rather than sending
an invalid slot. Imported custom alarm data is retained when toggling a record.
Single-alarm preferences are persisted only after the bed's success reply and
removed on cancellation success. The saved selected date/time, function identity,
label and nullable repeat metadata remain available after restart. An unsolicited
add-success event cannot replace that metadata with a guessed selection. Repeat-list observations preserve full bean
equality; an escalation replaces only the first matching number. Query clears the
observed list before replies; deletion removes the first selected full bean.
Single-alarm countdowns subtract epoch seconds across DST changes and retain the
86400-second fallback when the target is not later.

Light timeout is 0 to 900 seconds (0 means always on), except blue, which offers
1800 to 28800 seconds. Color sends one 10-byte GATT write containing both
checksummed RGB pieces. No brightness or extra lighting command is invented.

The current 19 profiles have all advanced music/alarm/repeat/light-page flags
false. A feature reply cannot override that static gate. Simple lamp buttons,
selected massage lists, and independently named music routes remain independent.
The full per-product action and flag inventory is in the
[HJBed catalog](../../custom_components/adjustable_bed/beds/hjbed/catalog.py).
Alarm action keys are snake-case names such as `zero_gravity`, `anti_snoring`,
`memory_position1`, `tv_position`, or `lounge_position`, and must belong to the
selected product's alarm list.

#### Evidence

HJBed sends only frames frozen from its accepted row121 evidence (artifact set
`bd3a5e96393fb32be9059fbb9a0eae5639deb7f0d761b4a27b3b382433c4d291`). Physical
effects, ATT behavior and firmware acceptance are for real users to validate after
a beta or release. Evidence: APK Protocol Audit row121.

### Eshine

**App:** [Eshine](https://play.google.com/store/apps/details?id=com.richmat.eshinesleep) 1.0.1 (code 10100), `com.richmat.eshinesleep`

**Status:** ❓ Needs testing (static verified, hardware unverified)

The `eshine` bed type drives the E6000 (metadata H3RN), the only product the
app offers, from one fixed table: head, feet, lumbar and pillow motors, presets,
named preset saves, massage and a light toggle.

#### Setup

- Detection: none. Choose **Eshine app (E6000)** manually. Shared Bluetooth
  names and services do not identify this app, and existing Richmat entries keep
  their own behavior.
- The profile owns the generic motor count, massage, angle and protocol fields,
  so setup hides them. Only the pulse count remains configurable; the refresh is
  fixed (see [Catalog app timing](#catalog-app-timing)).
- A two-address pair keeps this profile per physical bed; single-address side
  control is unsupported.
- **Transport:** the bed must expose exactly one complete endpoint among N1 and
  W1 to W5 (see [Transports](#transports)). N1 takes the bare code; the others
  take `6E 01 00 code sum8`. Several complete endpoints are rejected rather than
  combining the first write role with the last service's framing, as the app can.
- Within that service the controller selects the matching write characteristic
  and the first notify characteristic, even when its UUID differs from the
  declared notify UUID.
- Write is required; write without response alone is insufficient. When both
  write properties exist, writes use no response; otherwise they use response.
- After subscribing, setup sends ExitLimit once (see
  [Eshine commands](#eshine-commands)). The app has no challenge, PIN, cipher,
  heartbeat, state sync or outbound capability query.
- Notifications stay enabled with angle sensing disabled. Reconnect clears
  partial receive data and observed state before repeating setup.
- HA owns Bluetooth adapters and proxies, timeouts and reconnect policy; it does
  not reproduce the phone's five-second scan, MTU request, dialog or local
  SQLite storage.

#### Controls

Head, feet, lumbar and pillow covers share one global STOP and one scheduling
resource. Flat, Zero-G and Anti-Snore recall are each sent once.
**Save Zero Gravity** and **Save Anti-Snore** are separate buttons for named
presets, not numbered memory slots. The phone app's three-second gesture chooses
save, but the bed does not receive a three-second stream: each save button
sends its save code once. Strength and mode labels do not establish physical
cycle levels, persistence or discrete on/off values.

The generic `hold_control` action accepts `head_up`, `head_down`, `feet_up`,
`feet_down`, `lumbar_up`, `lumbar_down`, `pillow_up` and `pillow_down` for 1 to
60000 ms. The dashboard card shows motors, presets, lighting, massage and save
buttons in its existing sections.

##### Eshine commands

<!-- generated:eshine-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Bare (N1) | Framed | Sends |
|---|---|---|---|
| Head up | `24` | `6E 01 00 24 93` | refresh 100 ms; STOP |
| Head down | `25` | `6E 01 00 25 94` | refresh 100 ms; STOP |
| Feet up | `26` | `6E 01 00 26 95` | refresh 100 ms; STOP |
| Feet down | `27` | `6E 01 00 27 96` | refresh 100 ms; STOP |
| Lumbar up | `3F` | `6E 01 00 3F AE` | refresh 100 ms; STOP |
| Lumbar down | `40` | `6E 01 00 40 AF` | refresh 100 ms; STOP |
| Pillow up | `41` | `6E 01 00 41 B0` | refresh 100 ms; STOP |
| Pillow down | `42` | `6E 01 00 42 B1` | refresh 100 ms; STOP |
| Flat | `31` | `6E 01 00 31 A0` | once |
| Zero-G | `45` | `6E 01 00 45 B4` | once |
| Anti-Snore | `46` | `6E 01 00 46 B5` | once |
| Save Zero Gravity | `66` | `6E 01 00 66 D5` | once |
| Save Anti-Snore | `69` | `6E 01 00 69 D8` | once |
| Light toggle | `3C` | `6E 01 00 3C AB` | once |
| Head massage strength | `4C` | `6E 01 00 4C BB` | once |
| Foot massage strength | `4E` | `6E 01 00 4E BD` | once |
| Massage mode step | `48` | `6E 01 00 48 B7` | once |
| Massage off | `5E` | `6E 01 00 5E CD` | once |
| Massage 10 minutes | `5F` | `6E 01 00 5F CE` | once |
| Massage 20 minutes | `63` | `6E 01 00 63 D2` | once |
| Massage 30 minutes | `61` | `6E 01 00 61 D0` | once |
| STOP | `6E` | `6E 01 00 6E DD` | once |
| ExitLimit (setup) | `00` | `6E 02 01 00 71` | once after subscribing |
<!-- /generated -->

#### Timing

See [Catalog app timing](#catalog-app-timing).

- Movement sends a global STOP on completion, cancellation or failure, with a
  fresh cancel event.
- The pulse count bounds an HA movement and is not a hardware limit. A
  [renewable hold](../SERVICES.md#renewable-holds) refreshes until the lease
  ends, then sends STOP.
- HA actions start on invocation. Flutter pointer recognition, arena arbitration
  and the first eligible refresh callback are phone UI behavior, not a
  requirement for HA to wait for a physical touch.
- HA serializes commands, avoiding the app's queued stale movements and FIFO
  STOP backlog. No physical STOP delivery or latency guarantee is inferred.

#### Notifications

Eleven diagnostic sensors expose the most recent event name and a dictionary of
observed values: capabilities, motors, massage, light, RGB, alarm, anti-snore,
lock, music, mode and component checks.

- Attributes keep independent numbered motors and component check frames.
- They stay unknown until notifications arrive and are cleared on a new
  connection.
- Event-only acknowledgements are recorded as `true`, meaning observed, not a
  new writable capability.
- No parsed reply enables new commands: the app's E6000 layout is fixed and its
  own UI has no subscribers for these parsed states.
- Motor reports keep the artifact's numeric motor/type, status, angle, height
  and monitor-height fields. Their mapping to physical head, feet, lumbar and
  pillow axes is unproven, so they never populate position feedback or sliders.
- Alarm reports contain six ordered opaque integers. Sleep advertisement names
  stay byte lists.
- Received side modes never enable single-address pairing or send a side
  selector.
- RGB, alarm, anti-snore configuration, lock and music state is read-only; no
  outbound builder is inferred from a receive branch.

`beds/eshine/protocol.py` parses the stream:

- Type `20` frames accumulate across notifications and need an exact length and
  the additive checksum.
- Common frames keep the app's delimiter and notification-boundary behavior,
  including loss of partial common frames and splitting at an embedded `6e`;
  they have no generic checksum rule.
- Malformed lengths and short fields are rejected safely. The accepted audit
  corrections show that `6e2007060302a0`, `6e2007060303a1`, `6e200806050200a3`
  and `6e200806050300a4` cannot emit parsed anti-snore state; HA drops them
  rather than reproducing Dart range errors.
- The receive buffer has a 65535-byte safety bound; that is not a bed
  packet-size claim.

#### Evidence

Eshine sends only frames frozen from its accepted row106 evidence, framed and
bare. Desk data, firmware maintenance and OTA, empty pruned blanket and
diagnostic models, unused enums and unrelated phone infrastructure are excluded;
no bed Wi-Fi, provisioning, cloud or account path was found. Firmware
acceptance, physical axis semantics, massage and light cycles and STOP behavior
are for real users to validate after a beta or release, with full GATT and
notification captures. Evidence: APK Protocol Audit row106.

### Classic Richmat apps

**App:** Avocado Eco Base 1.0.4 (5), CoasterSleep 1.0.10 (10), Forty Winks 1.0.1, Milemont 1.0.4 and Superior 1.0.9 (see [Apps](#apps))

**Status:** ❓ Needs testing (accepted static APK evidence; hardware unverified)

These older resource-driven apps have an independent profile per app. Existing
Richmat and RMControl entries retain their own behavior, and no capability is
inherited from the Richmat remote routes.

#### Setup

Each app selects one of its own four-character remote layouts from a
package-local catalog. A compiled layout is not hardware confirmation.

| App | Layouts |
|---|---:|
| Avocado Eco Base | 704 |
| CoasterSleep | 715 |
| Forty Winks | 725 |
| Milemont | 700 |
| Superior | 725 |

1. Answer the Richmat question with the exact app (for example **Forty Winks
   app**). The app is the protocol variant, so its profile id is
   `richmat_classic_apps:<app>`.
2. Choose the four-character layout the app shows. The list is the chosen app's
   own; choose the layout explicitly even when the Bluetooth name looks like one.
   Four-character app aliases resolve to their package-local layouts, and the
   diagnostic TEST and RMCS layouts are excluded.
3. Forty Winks and Superior `ZRS6` is a layout picker: choose `ZRS6:CORN` or
   `ZRS6:CPRN` to use the `CORN` or `CPRN` controls. The picker itself sends no
   bed command.
4. Under **Advanced**, allow the app's third-service fallback only when the bed
   uses that app path.

- `FWRM` and `WFRM` select the separate desk controls.
- Motor count, massage and angle sensing are fixed by the profile, and the app
  sets its own refresh. The pulse count bounds a native held control.
- Configure asks the same layout and fallback, and checks the layout against
  the chosen app.
- Detection: none. Advertisement aliases and four-character names are
  package-local, so a matching name only adds the five apps as candidates beside
  the detected Richmat route. A shared service UUID does not identify the app,
  its axes or a physical side.
- One-address Left/Right pairing is unavailable: the app's mode labels do not
  establish physical side roles.

The first present fixed service wins, in the order W1, W2, N1, W4 (see
[Transports](#transports)). N1 sends the decoded resource bytes unchanged (RAW);
the others are framed. An incomplete first match fails; it does not silently
choose a lower-priority service. The app also has an index-2 service fallback,
which Home Assistant uses only with the explicit option: it selects the last
writable and receive-capable characteristics in that service and sends RAW
bytes. A final read-only receive role still permits RAW controls, with no
invented reads, notification subscription or startup frame. Home Assistant
always uses current-session objects, and Bleak manages notification
subscription and descriptors. The app never explicitly sets Android writeType;
Home Assistant uses write-with-response when supported, otherwise
write-without-response. That ATT choice is not a claim about the app's
effective platform write type.

`U3RM` remembers its third, fourth or fifth selector. The hardware meaning of a
motor slot or Mode 1/2/3 is not inferred from a layout name.

#### Controls

Native buttons carry each node's app label. A node's tag, selector,
visibility, current mode and short or long gesture decide what it sends. Local
mode, head/foot, memory-arm and Hold/Release selectors appear where the layout
has them.

A keep button, including a recall preset or Flat under Hold, accepts a
[renewable hold](../SERVICES.md#renewable-holds): it repeats its payload every
worker tick until the lease ends, then releases 50 ms later. Short, long and
armed presses, and a head/foot selection that leaves a control with nothing to
send, keep their own gestures and refuse a lease, including when the selector
changed after the hold was admitted. See the
[per-control scope](../design/execution-capabilities.md#per-control-hold-scope).

| Path | Frame |
|---|---|
| RAW (N1, fallback) | The selected decoded resource bytes, unchanged |
| FRAMED | `6E 01 M C sum8` (`codec.command`), `M` the current app mode |
| Settings | `6E OP A B sum8` (`codec.frame`), independent of the ordinary encoding |
| RGB | Two settings frames in one 10-byte write (`codec.rgb`) |
| Ordinary release | RAW `6E`; FRAMED `6E 01 M 6E sum8` |

`M` is an actually available app mode; RAW ignores it. The ordinary FRAMED
sender uses only the first selected operand byte. Legacy short operands can
differ from current ones. All five shipped constructors leave the legacy long
getter null, and the integration does not use that ignored XML attribute.
`GVRM` foot selection reaches that null getter, so it cannot invent a movement
packet. Raw SelectView armed-save DOWN has no handler; it does not become a
working save by copying another profile's bytes.

##### Resource-selected controls

This indexes the operands stored in the five shipped catalogs. Values are sets
across the exact layouts that bind each resource, not universal capabilities.
FRAMED values are wrapped as above. The complete node tables ship in
`beds/richmat_classic/data/`.

| Bound resource | RAW short operand(s) | Current short operand(s) | Long operand(s) |
|---|---|---|---|
| `adjust_volume` | `b7` | `b7` | None |
| `com_first_up_once` | `3d` | `3d` | None |
| `com_lumbar_back_pos` | `91` | `91` | `92` |
| `com_lumbar_set_pos` | `91` | `91` | `92` |
| `com_motor1_2_down` | `2a`, `39` | `2a` | None |
| `com_motor1_2_up` | `29`, `36`, `38` | `29` | None |
| `com_motor2_down` | `27`, `41` | `27` | None |
| `com_motor_keep_30` | `90` | `90` | None |
| `com_msg1_intensity_dec` | `49`, `4a`, `4d` | `4d` | None |
| `com_msg1_intensity_inc` | `42`, `46`, `49`, `4c` | `4c` | None |
| `com_msg2_intensity_dec` | `4b`, `4f` | `4f` | None |
| `com_msg2_intensity_inc` | `44`, `48`, `4e` | `4e` | None |
| `com_msg_10min` | `39`, `47`, `49`, `4c`, `50`, `5f` | `5f` | None |
| `com_msg_10min_new` | `a1` | `a1` | None |
| `com_msg_20min` | `63` | `63` | None |
| `com_msg_20min_new` | `a2` | `a2` | None |
| `com_msg_30min` | `61` | `61` | None |
| `com_msg_30min_new` | `a3` | `a3` | None |
| `com_msg_aroma` | `3b` | `3b` | None |
| `com_msg_constant` | `3a`, `47` | `3a` | None |
| `com_msg_foot_intensity2` | `a5` | `a5` | None |
| `com_msg_head_intensity2` | `a4` | `a4` | None |
| `com_msg_intensity_dec` | `35`, `4b` | `35` | None |
| `com_msg_off` | `39`, `47`, `48`, `5d` | `39`, `47`, `48`, `5d` | `47` |
| `com_msg_off2` | `5a` | `5a` | None |
| `com_msg_off3` | `48`, `5e` | `48`, `5e` | `5e` |
| `com_msg_on` | `5d` | `5d` | `47` |
| `com_msg_speed_dec` | `37`, `49` | `37` | None |
| `com_msg_speed_inc` | `36`, `48` | `36` | None |
| `com_msg_wave1` | `49` | `49` | None |
| `com_msg_wave2` | `4a` | `4a` | None |
| `com_msg_wave3` | `4b` | `4b` | None |
| `com_relax_set` | `70` | `70` | `95` |
| `com_second_up_once` | `3e` | `3e` | None |
| `com_table_down` | `02` | `02` | None |
| `com_table_up` | `01` | `01` | None |
| `com_unwind_back` | `8c` | `8c` | `8d` |
| `com_unwind_set` | `8c` | `8c` | `8d` |
| `com_wakeup_back` | `93` | `93` | `94` |
| `com_wakeup_set` | `93` | `93` | `94` |
| `k_first_second_once_up` | `23` | `23` | None |
| `k_first_up_once` | `3d` | `3d` | None |
| `k_first_up_second_down` | `21` | `21` | None |
| `k_flat` | `31`, `32`, `38` | `31` | `84` |
| `k_flat2` | `6c` | `6c` | None |
| `k_flat_old` | `38` | `31` | None |
| `k_flat_old2` | `31` | None | None |
| `k_flat_sleep_back` | `f6`, `f7` | `f6`, `f7` | `f6`, `f7` |
| `k_flat_sleep_save` | `f6`, `f7` | `f6`, `f7` | `f6`, `f7` |
| `k_lock` | `31`, `84`, `d9` | `31`, `84`, `d9` | `84` |
| `k_lounge_back` | `32`, `59` | `59` | `65` |
| `k_lounge_back_old2` | `32` | `31`, `59` | None |
| `k_lounge_save` | `59` | `59` | `65` |
| `k_m1_back` | `2e`, `42` | `2e` | `2b` |
| `k_m1_back_old2` | `42` | `2e`, `3f` | `2b` |
| `k_m1_save` | `2b`, `2e`, `42`, `43` | `2b`, `2e` | `2b` |
| `k_m1_set_old2` | `42`, `43` | `2b`, `2e`, `40` | `2b` |
| `k_m2_back` | `2f`, `44` | `2f` | `2c` |
| `k_m2_back_old2` | `44` | `2f`, `44` | `2c` |
| `k_m2_save` | `2c`, `2f`, `44`, `45` | `2c`, `2f` | `2c` |
| `k_m2_set_old2` | `44`, `45` | `2c`, `2f`, `42` | `2c` |
| `k_m3_back` | `30` | `30` | `2d` |
| `k_m3_save` | `2d`, `30` | `2d`, `30` | `2d` |
| `k_m4_back` | `b2` | `b2` | `b3` |
| `k_m4_save` | `b2` | `b2` | `b3` |
| `k_m5_back` | `f4` | `f4` | `f5` |
| `k_m5_save` | `f4` | `f4` | `f5` |
| `k_motor1_2_down` | `2a`, `39` | `2a` | None |
| `k_motor1_2_down_old` | `39` | `2a` | None |
| `k_motor1_2_down_old2` | `37`, `39` | `2a` | None |
| `k_motor1_2_up` | `29`, `36`, `38` | `29` | None |
| `k_motor1_2_up_old` | `38` | `29` | None |
| `k_motor1_2_up_old2` | `36` | `29`, `3c` | None |
| `k_motor1_down` | `25`, `37`, `38` | `25` | None |
| `k_motor1_down_old` | `37` | `25` | None |
| `k_motor1_down_old2` | `38` | `25` | None |
| `k_motor1_up` | `24`, `34`, `35` | `24` | None |
| `k_motor1_up_old` | `34` | `24` | None |
| `k_motor1_up_old2` | `35` | `24` | None |
| `k_motor2_3_down` | `97` | `97` | None |
| `k_motor2_3_up` | `96` | `96` | None |
| `k_motor2_down` | `27`, `41` | `27` | None |
| `k_motor2_down_old` | `38`, `41` | `27` | None |
| `k_motor2_down_old2` | `41` | `27` | None |
| `k_motor2_up` | `26`, `36`, `37` | `26` | None |
| `k_motor2_up_old` | `35`, `36` | `26` | None |
| `k_motor2_up_old2` | `37` | `26` | None |
| `k_motor3_4_down` | `44` | `44` | None |
| `k_motor3_4_tilt_down` | `5c` | `5c` | None |
| `k_motor3_4_tilt_up` | `5b` | `5b` | None |
| `k_motor3_4_up` | `43` | `43` | None |
| `k_motor3_down` | `40`, `43` | `40` | None |
| `k_motor3_up` | `3f`, `42` | `3f` | None |
| `k_motor4_down` | `42`, `45` | `42` | None |
| `k_motor4_up` | `41` | `41` | None |
| `k_motor5_down` | `72` | `72` | None |
| `k_motor5_up` | `71` | `71` | None |
| `k_motor6_down` | `74` | `74` | None |
| `k_motor6_up` | `73` | `73` | None |
| `k_motor7_down` | `d1` | `d1` | None |
| `k_motor7_up` | `d0` | `d0` | None |
| `k_motor_keep_15` | `76` | `76` | None |
| `k_motor_reset` | `be` | `be` | None |
| `k_msg1_intensity_dec_old2` | `49` | `4d`, `5f` | None |
| `k_msg1_intensity_inc_old2` | `46` | `3c`, `4c` | None |
| `k_msg1_off_old2` | `47` | `47`, `5f` | None |
| `k_msg1_on_off_old` | `42` | `4c` | None |
| `k_msg2_intensity_dec_old2` | `4b` | `35`, `4f` | None |
| `k_msg2_intensity_inc_old2` | `48` | `34`, `4e` | None |
| `k_msg2_on_off_old` | `44` | `4e` | None |
| `k_msg_constant_old` | `47` | `3a` | None |
| `k_msg_first_on_off` | `32` | `32` | None |
| `k_msg_intensity1_old` | `4c` | `67` | None |
| `k_msg_intensity2_old` | `4d` | `4d` | None |
| `k_msg_intensity3_old` | `4e` | `68` | None |
| `k_msg_intensity_dec_old` | `4b` | `35`, `4f` | None |
| `k_msg_intensity_first` | `4c`, `67` | `67` | None |
| `k_msg_intensity_inc` | `34`, `48`, `4a` | `34` | None |
| `k_msg_intensity_inc_old` | `4a` | `34`, `4d` | None |
| `k_msg_intensity_third` | `4e`, `68` | `68` | None |
| `k_msg_mode` | `48`, `4a` | `48` | `47`, `5e` |
| `k_msg_mode_old2` | `4a` | `48` | None |
| `k_msg_off_old` | `39` | `5f` | None |
| `k_msg_off_old2` | `50` | `5f` | None |
| `k_msg_on_off` | `6f` | `6f` | None |
| `k_msg_on_old2` | `4c` | `5f` | None |
| `k_msg_pulse` | `38`, `46` | `38` | None |
| `k_msg_pulse_old` | `46` | `38`, `3c` | None |
| `k_msg_second_on_off` | `33` | `33` | None |
| `k_msg_speed_dec_old` | `49` | `37`, `4c` | None |
| `k_msg_speed_inc_old` | `48` | `36`, `4e` | None |
| `k_msg_wave` | `39`, `45` | `39` | `47` |
| `k_msg_wave_old` | `45` | `39` | None |
| `k_music_lock` | `d9` | `d9` | `84` |
| `k_next` | `d3` | `d3` | None |
| `k_on_off` | `d8` | `d8` | None |
| `k_previous` | `d2` | `d2` | None |
| `k_read_back` | `f2`, `f3` | `f2`, `f3` | `f2`, `f3` |
| `k_read_set` | `f2`, `f3` | `f2`, `f3` | `f2`, `f3` |
| `k_relax_back` | `70` | `70` | `95` |
| `k_reset` | `62` | `62` | None |
| `k_second_up_first_down` | `22` | `22` | None |
| `k_set_old` | `35` | `45` | None |
| `k_side_sleeper_back` | `ba` | `ba` | `bb` |
| `k_side_sleeper_set` | `ba` | `ba` | `bb` |
| `k_sleep_back` | `8e` | `8e` | `8f` |
| `k_sleep_set` | `8e` | `8e` | `8f` |
| `k_snore_back` | `46` | `46` | `69` |
| `k_snore_reset` | `cb` | `cb` | None |
| `k_snore_save` | `46`, `69` | `46`, `69` | `69` |
| `k_start_pause` | `d7` | `d7` | None |
| `k_sync_off` | `bd` | `bd` | `bd` |
| `k_sync_on` | `bc` | `bc` | `bc` |
| `k_tv_back` | `33`, `58` | `58` | `64` |
| `k_tv_back_old2` | `31`, `33` | `58` | None |
| `k_tv_save` | `58`, `64` | `58`, `64` | `64` |
| `k_ubl_off` | `3c`, `75` | `3c`, `75` | `75` |
| `k_ubl_on_off` | `36`, `3c`, `43`, `46` | `3c` | `75` |
| `k_ubl_on_off_old` | `43` | `3c` | None |
| `k_vibration` | `d6` | `d6` | None |
| `k_volume_down` | `d5` | `d5` | None |
| `k_volume_up` | `d4` | `d4` | `d4` |
| `k_wakeup_mode` | `85` | `85` | None |
| `k_yoga_back` | `f0` | `f0` | `f1` |
| `k_yoga_save` | `f0` | `f0` | `f1` |
| `k_zg2_back` | `6b` | `6b` | `6a` |
| `k_zg2_return` | `6b` | `6b` | `6a` |
| `k_zg2_save` | `6b` | `6b` | `6a` |
| `k_zg2_set` | `6b` | `6b` | `6a` |
| `k_zg_back` | `34`, `35`, `45` | `45` | `66` |
| `k_zg_back_old` | `32`, `34` | `45` | `66` |
| `k_zg_save` | `34`, `45`, `66` | `45`, `66` | `66` |
| `sleep1` | `86` | `86` | None |
| `swtch_music` | `b8` | `b8` | None |
| `turn_off_music` | `b9` | `b9` | None |

##### Auxiliary settings

`A(op,a,b)` is the settings frame `6E op a b sum8`.

| Operation | Exact bytes or formula |
|---|---|
| Framed initialization | `6e02010071`, after the startup delay |
| Desk layout initialization or query | `6e94000002` immediately; the FRAMED notification startup repeats it after the startup delay |
| Alarm query | `6e08010178`, only if the current alarm metadata list is nonempty |
| Lamp query | `6e0a000179` |
| Aroma query | `6e1a000088` |
| Alarm schedule | `A(05,delay low,00)`, then `A(06,delay high,action)` |
| Alarm cancel | `6e05000073`, then `6e06000074` |
| RGB | `A(0c,ff,R) \|\| A(0d,G,B)` |
| Lamp slider | `A(0b,(minutes*60) high,(minutes*60) low)`; zero is `6e0bffff77` |
| Lamp Save | `A(0b,minutes high,minutes low)`; zero minutes saves zero |
| Aroma | `A(1b,00,mode2 minutes)`, `A(1c,00,mode3 minutes)`, `A(1d,00,pause hours)` |
| Massage popup | 15/30/45/toggle: `6e01005fce` / `6e010063d2` / `6e010061d0` / `6e01005ecd` |
| D1RM slider | 0/2/3/5 map to `5e`/`5f`/`63`/`61`; 1/4 pass through, using `A(01,00,value)` |
| D9RM slider | Same, except zero maps to `8b` |
| Desk units | `6e910000ff` cm / `6e91000100` inches |
| Desk target | `A(88,int(float32(display*10))/100,int(float32(display*10))%100)` with Java truncation |
| Desk buttons 1/2/3 | `6e96000408` / `6e9600080c` / `6e96001014` |
| Desk fourth button, newly reported error confirmation | `6e95000003` |

Alarms select one actual layout checkbox action. The delay is the minutes until
the next chosen local time; an equal or unset time means 1440 minutes. There are
no weekday, date or combined preset-plus-massage packets. The lamp slider and
Save keep their different source units. Aroma ranges are 1-60 minutes, 1-60
minutes and 1-12 hours; the source's uppercase consumer and two-byte getInt
defect prevent reliable aroma-save feedback.

#### Timing

See [Catalog app timing](#catalog-app-timing). Mode 0 resets the long-press
counter but keeps the long-fired latch; mode 4 releases and resets both. A new
DOWN resets neither. Home Assistant cancellation ends pending commands, always
performs the protocol cleanup and does not resume a held movement after a
disconnect or a lost UI owner. The app's unsafe queued or pending continuations
and stale cached-characteristic reuse are not reproduced. A bounded desk button
hold ends its refresh, with no invented release frame.

#### Notifications

| Prefix | Consumer |
|---|---|
| `6e08` | Legacy desk height, base 128; oldPack duplicate suppression |
| `6e90` | Modern desk height, base 100, unit-dependent float32 arithmetic |
| `6e94` / `6e92` | Desk unit, range and initial values; only `94` reveals the modern controls |
| `6e97` | Desk error callback |
| `6e09010078` | Alarm capability |
| `6e0e00017d` / `6e0e00037f` | Lamp capability and state flags |
| `6e1a000189` | Aroma capability |
| `6e07010177` / `6e07010278` | Alarm set / cancel state |

The checksum, ordered prefix search and the source's 5, 7 and 16-byte length
branches apply. The app can discard coalesced packets or throw on an empty
short-buffer match; Home Assistant reports malformed input without crashing the
Bluetooth callback. Numeric rounding preserves binary32 operations and
promoted-float BigDecimal HALF_EVEN. The Avocado URRM settings observer can
starve the lamp and aroma rows after its suppressed alarm row; that
package-specific gate is not applied to the other apps.

No bed angle, general command acknowledgement, general massage state, firmware,
memory count or authentication API is inferred from dormant constants.

#### Services

`adjustable_bed.richmat_classic` sends the app's typed settings: `operation:
query` requests the settings capabilities, then alarm and alarm cancel, RGB,
lamp slider and Save timers, aroma, massage popup and slider, and the desk
target, unit, recall buttons and reset. The layout's available alarm action IDs
and the received state are in diagnostics. Wi-Fi, cloud and account,
group and network administration, and the diagnostic endurance and
motor-mapping configuration stay outside the supported surface. See
[Actions](../SERVICES.md#classic-richmat-app-settings).

#### Evidence

The classic apps send only frames frozen from their five accepted row066
reports. APK Protocol Audit row066 records the accepted versions, all five
artifact and report hashes, the accepted authority, exact member differences,
exclusions, safety divergences, implementation status and deferred hardware
validation.
Coaster's indivisible accepted aggregate and its historical six-cache-file FAIL
remain explicit there. Static acceptance is not hardware confirmation.

### Good Vibe Sleep

**App:** [Good Vibe Sleep](https://play.google.com/store/apps/details?id=com.richmat.goodvibesleep) 2.0.1 (20103), `com.richmat.goodvibesleep`

**Status:** ❓ Needs testing (static app evidence only)

A per-product catalog app over this codec, plus independent sleep sensors that
speak their own JSON envelope. Its product catalog stays controller data; the
[Good Vibe Sleep catalog](../../custom_components/adjustable_bed/beds/goodvibe/catalog.py)
lists every product, alias and action.

#### Setup

- Choose the exact product or remote shown in Good Vibe Sleep. Shared Bluetooth
  services do not identify a model. Detection: the app's own name filter
  ([`beds/goodvibe/discovery.py`](../../custom_components/adjustable_bed/beds/goodvibe/discovery.py))
  offers Good Vibe Sleep and suggests a product (step 1); it never chooses one.
- The catalog supplies 848 admitted normal-product/configuration choices and 27
  remote/image aliases. The row116 audit retains every accepted selector,
  including excluded selectors.
- Independent sleep sensors use case-sensitive `RM-` (type 1) or `HJ-` (type 2)
  name prefixes. Add the sensor's own Bluetooth address with the corresponding
  sleep profile.
- FWRM and WFRM are desk products and are excluded.

1. Choose the **Good Vibe Sleep app** row, then search its product question for
   the exact app product/configuration or remote alias. A product the app's own
   name rule reads from the Bluetooth name is suggested, never chosen for you.
   Name matches offer app hints and do not replace another identified receiver.
2. Choose the Home Assistant Bluetooth adapter or proxy that reaches that
   physical address.
3. Add each independent sleep device separately, selecting type 1 or type 2. A
   normal product's `sleep_advertisement_name` status attribute can identify the
   app's requested sensor name.

Single-address pairs expose only the selected product's admitted sides. A
combined command uses native side 2 when the product offers it; products
offering only sides 0 and 1 receive left then right commands on the same BLE link.

The source app has no app-owned PIN, challenge, encryption or bond request. This
does not establish that firmware never requires OS bonding. Home Assistant
retains its normal adapter, proxy and setup infrastructure.

##### Normal-product GATT

A normal product accepts the W1, N1, W5, W4, W3 and W2 services of the
[transport table](#transports); N1 takes single-byte commands, the others framed
ones. The first exact TX with the `write` property is retained. RX is the first
`notify` characteristic in an accepted service, without nominal RX equality. The
last accepted service sets framed/single-byte mode even when TX/RX came from an
earlier service. Missing usable TX/RX fails setup. Writes prefer
without-response when TX supports it.

##### Sleep GATT

Both sleep types accept `0000e0ff-3c17-d293-8e48-14fe2e4da212` and `2320567c-05cf-6eb4-c341-772851827e1b`.

| Profile | TX selection | RX selection | Writes |
|---------|--------------|--------------|--------|
| Type 1 / `RM-` | First write-without-response property | First notify property | Without response |
| Type 2 / `HJ-` | `00000002-3c17-d293-8e48-14fe2e4da212` with write | `00000003-3c17-d293-8e48-14fe2e4da212` with notify | With response |

The additional service is live BLE support. Its enum name does not turn it into
excluded network provisioning. Nominal `26f66991-68ee-c2be-444d-b95c3f2dc38a`
characteristic fields are not used for selection.

#### Controls

Normal generic frames are [commands](#framing-and-checksum), `6e 01 side operand sum8`,
except the startup [function selectors](#function-selectors). The legacy service
emits only the operand. Short, long and legacy-short operands are distinct per
descriptor; each is listed in the catalog.

The row116 audit's command table contains every accepted command ID, exact
framed/legacy alternatives, source owner and implementation disposition. The
catalog contains 1,393 current layout/alarm action definitions and five
controls constructed inside the Y6RM menu. Controls retain their app labels
without assigning a physical motor to a name alone.

| Command | Bytes | Description |
|---------|-------|-------------|
| Generic short action | `6e 01 S C sum8` or `C` | `C` is the exact selected descriptor's short/legacy-short operand |
| Generic long action | `6e 01 S L sum8` or `L` | `L` is the exact descriptor's reachable long operand |
| Release / STOP | `6e 01 S 6e sum8` or `6e` | Sent by gestures that define release; no inferred firmware guarantee |

The five-model memory predicate applies only to E3RM, GXRM, JDRM, JFRM and JGRM,
with the GXRM/TV exception. The app's memory control sends its ordinary operand
before changing local mode. Forced-long details and local release/hold choices
remain separate from physical state.

The fixed commands below, including the Y6RM menu controls, use the common
frame on each side, or the single code on the legacy service:

<!-- generated:goodvibe-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Single code | Side 0 | Side 1 | Side 2 |
|---|---|---|---|---|
| Release (STOP) | `6E` | `6E 01 00 6E DD` | `6E 01 01 6E DE` | `6E 01 02 6E DF` |
| Close bed light | `75` | `6E 01 00 75 E4` | `6E 01 01 75 E5` | `6E 01 02 75 E6` |
| Massage countdown off | `5E` | `6E 01 00 5E CD` | `6E 01 01 5E CE` | `6E 01 02 5E CF` |
| Massage countdown 10 min | `5F` | `6E 01 00 5F CE` | `6E 01 01 5F CF` | `6E 01 02 5F D0` |
| Massage countdown 20 min | `63` | `6E 01 00 63 D2` | `6E 01 01 63 D3` | `6E 01 02 63 D4` |
| Massage countdown 30 min | `61` | `6E 01 00 61 D0` | `6E 01 01 61 D1` | `6E 01 02 61 D2` |
| Y6RM Head Up, sustain press | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | `6E 01 02 24 95` |
| Y6RM Foot Up, sustain press | `26` | `6E 01 00 26 95` | `6E 01 01 26 96` | `6E 01 02 26 97` |
| Y6RM Head Down, sustain press | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | `6E 01 02 25 96` |
| Y6RM Foot Down, sustain press | `27` | `6E 01 00 27 96` | `6E 01 01 27 97` | `6E 01 02 27 98` |
| Y6RM Motor Reset, short press | `31` | `6E 01 00 31 A0` | `6E 01 01 31 A1` | `6E 01 02 31 A2` |
<!-- /generated -->

The Y6RM sustained controls refresh like any sustained press; a released control
sends STOP through the same common builder. These labels do not establish
physical axes for an untested bed.

##### Lights

| Command | Bytes | Description |
|---------|-------|-------------|
| Duration | `6e 0b HH LL sum8` | Seconds, big-endian; zero maps to `ff ff` |
| Color | `6e 0c ff R sum8 6e 0d G B sum8` | Both records in one write buffer |

Close bed light (above) is a dedicated close action, with no extra release.
Each product offers these durations and colours:

<!-- generated:goodvibe-lights -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Products | Durations (seconds) |
|---|---|
| Full colour | 0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720, 780, 840, 900 |
| Eight colours | 0, 300, 600, 900 |
| RNRN, eight colours | 0, 1800, 3600, 14400, 28800 |

The eight colours are `(255, 255, 0)`, `(0, 255, 0)`, `(0, 127, 255)`,
`(0, 0, 255)`, `(139, 0, 255)`, `(255, 255, 255)`, `(255, 0, 0)`, `(255, 165, 0)`.
<!-- /generated -->

##### Massage countdown

Products with the bottom massage countdown offer off, 10, 20 and 30 minutes (see
the table above). The dedicated slider callback sends once without a release frame.

#### Timing

See [Catalog app timing](#catalog-app-timing).

- Short actions send once and release on completion/cancellation. Long and
  short-and-long gestures do not acquire an invented release frame. Releasing a
  short-and-long card control before the long threshold sends its short action;
  explicit STOP and aborted operations do not.
- A renewable hold (`hold_control` with `hold_owner` and `hold_generation`,
  which the card uses for press-and-hold) is offered only on controls whose
  effective gesture is a sustained press. It keeps the sustained refresh while
  renewals arrive, up to 30 seconds in total, and sends the release once when
  the lease ends. Other controls refuse a lease, as beds without renewable holds
  do, and keep their finite gesture. While memory mode is on, its eligible
  controls refuse a lease too.
- Source normal queue timing is a 100 ms backlog scheduler, not a universal
  minimum write gap. Home Assistant serializes commands and owns finite
  cancellation and release cleanup.
- Sleep writes await each chunk. Monitoring retains its user intent through an
  unexpected disconnect. Manual disconnect, unload and explicit stop end that
  intent and cancel owned resources.
- The app's unretained 100 ms timer and active split futures are not firmware
  guarantees. Home Assistant stops unsent chunks on cancellation and does not
  recreate the app's timer or callback ownership leaks.

##### Good Vibe Sleep startup

<!-- generated:goodvibe-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | When | Framed | Single-code |
|---|---|---|---|
| Exit limit | first | `6E 02 01 00 71` | `00` |
| Check clock | 300 ms after the previous step | `6E 08 01 01 78` | `01` |
| Check light | 300 ms after the previous step | `6E 0A 00 01 79` | `01` |
| Time sync | next, when the product has an alarm menu | settings records `08 02 01` then `08 03 01` | same |
| Sleep name query | next, when the product has sleep monitoring | `6E 20 08 06 03 00 00 9F` | same |
<!-- /generated -->

#### Notifications

- Normal frames retain the shipped checksum/framing and event order: `6E 20`
  records must carry a valid `sum8`, acknowledgements match their exact frames,
  and `6E 21` and `6E 40` records are framed but have no bed-state consumer.
  Incomplete normal data expires (see [Catalog app timing](#catalog-app-timing)).
  Malformed bounds and zero-length records are rejected without fabricating state.
- Sleep ordinary assembly uses byte 12 and strips one 14-byte header. Type 1
  routes by the retained request; type 2 uses the artifact's ordered
  text-contains routing. Incoming bytewise text is separate from outbound UTF-8.
- Report continuation preserves the type-specific whole-chunk versus
  per-chunk-header rule, then bounded GZip decoding and typed day/month schemas.
  Type 2 day schema selection retains the algorithm-version comparison and
  first-component-1 exception.
- Live values preserve separate L/R occupancy, heart, respiration, movement and
  snore fields. Type 2 invalid markers retain earlier values; malformed new
  updates do not partially replace one side.
- Full typed event and report records remain in status attributes. The
  integration does not claim medical or physical validation of these values.

#### Services

Use `adjustable_bed.goodvibe` for these settings and queries. The action
validates every target before writing. The dashboard card includes app
controls, local side selection, light durations, snore numbers and sleep state.

##### Alarms and snore settings

Settings records put the length after `20`:
`6e 20 len domain command operation data sum8`, where `len` counts the whole
frame (`codec.record_20_len`). The domains and commands match the
[variable frames](#variable-frames).

| Command | Bytes | Description |
|---------|-------|-------------|
| Single alarm low | `6e 05 minuteLow 00 sum8` | First write |
| Single alarm high | `6e 06 minuteHigh action sum8` | Second write |
| Repeat alarm | `6e 20 0d 05 01 01 slot 00 hour minute action mask sum8` | Monday bit 7 through Sunday bit 1; enabled bit 0 |
| Delete repeat alarm | `6e 20 08 05 02 01 slot sum8` | Slots 1–7 |
| Snore switch | `6e 20 09 06 01 01 00 enabled sum8` | Normal settings menu |
| Snore configuration | `6e 20 0a 06 05 01 selector 00 value sum8` | Selector 1: count 1–30; selector 2: time 5–30 in steps of five |
| Time sync | `6e 20 0c 08 02 01 epochBE32 offsetHours sum8`, then `6e 20 0d 08 03 01 yearMinus1970 month day hour minute second sum8` | Startup and the `sync` operation |

The repeat-alarm query retains returned records, the sleep-name query reads the
normal product's independent sensor name, and the snore queries read the count,
time and switch. These are exact examples from the shipped builders; fields vary
with the requested values:

<!-- generated:goodvibe-settings -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Operation and example input | Exact GATT write(s) |
|---|---|
| Single alarm: 4660 minutes, action `05` | `6e053400a7`; `6e0612058b` |
| Cancel single alarm | `6e05000073`; `6e06000074` |
| Light duration: 300 seconds | `6e0b012ca6` |
| Light always on: 0 seconds | `6e0bffff77` |
| Colour: 255, 128, 0; one combined write | `6e0cffff786e0d8000fb` |
| Repeat alarm: slot 1, 07:30, action `05`, mask `F9` | `6e200d0501010100071e05f9c6` |
| Delete repeat alarm: slot 1 | `6e2008050201019f` |
| Query repeat alarms | `6e2008050100009c` |
| Query sleep name | `6e2008060300009f` |
| Snore switch: on | `6e20090601010001a0` |
| Snore count: 7 | `6e200a060501010007ac` |
| Snore time: 30 | `6e200a06050102001ec4` |
| Query snore configuration, then switch | `6e20090605000000a2`; `6e2008060100009d` |
| Time sync: 2026-11-03 13:00:00+01:00 | `6e200c0802016ae9ccc00185`; `6e200d080301380b030d0000fa` |
<!-- /generated -->

Single-alarm date and current time are truncated to minutes. A nonpositive
difference adds one day once. A single-alarm preference is saved only on its
ACK. Repeat alarms use an explicit slot or the smallest unoccupied slot in the
observed list. Automatic slots are checked and retained for all targets before
any target writes. The normal snore menu excludes HNRN, HQRN, HSRN, HURN, M7RN
and MJRN.

##### Sleep controls and reports

Sleep JSON uses insertion-ordered `id`, `cmd`, `val` and UTF-8 encoding. It is
not a Richmat frame but the sleep-sensor envelope of
[`codec/sleep_envelope.py`](../../custom_components/adjustable_bed/codec/sleep_envelope.py):

```text
00 seq 01 00 ((n+7)&ff) 00 00 11 03 43 55 44 lenLo lenHi JSON
```

`n` is the JSON byte length. Ordinary IDs cycle 1–254. There is no ordinary
sleep checksum or CRC. Each packet is chunked using the current link's MTU
minus three, bounded by 512 bytes.

| Action | Type 1 JSON command/value | Type 2 JSON command/value |
|--------|---------------------------|---------------------------|
| Set time | `s_time:{ts,tz}` | `s_time:{ts,utc}` |
| Query time | No packet | `q_time:null` |
| Query part | `s_part:null` with retained query selector | `q_part:null` |
| Set part | `s_part:part` | `s_part:part` |
| Live query | `q_realtime:{type:0,time:1}` | Same |
| Report metadata | `q_report:{part,type,y,m,d}` | Same |
| Report continuation | `q_report:{part,type,y,m,d,allow:1}` | `q_report:{allow:1}` |
| Query sensitivity | No setter/query packet admitted | `q_sens:null`; removed setter has no packet |
| Query anti-snore | No packet | `q_antiSnore:null` |
| Set anti-snore | No packet | `s_antiSnore:{L:[enabled,8,4],R:[enabled,8,4]}` |

A report action automatically requests metadata and continuation, then waits
for the typed result. Day is type 1 and month is type 2; report parts are 1 or
2. Setting a type 1 sleep part accepts 1 or 2; type 2 accepts 11, 12 or 13.
Type 2 startup selects the shipped default 12. Report operations replace live
monitoring to protect the shared response selector.

#### Evidence

Good Vibe Sleep sends only frames frozen from its accepted row116 vectors
(`tests/fixtures/goodvibe`). Hardware, ATT delivery, firmware acceptance and
physiological interpretation remain unverified. Real users may validate them
after beta/release; maintainer hardware acquisition is not required.
APK Protocol Audit row116 records the source bindings, hashes, exclusions and
audit limits.

### L&P legacy app

**App:** [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp) 2.2.1 (13), `com.richmat.lp`

**Status:** ❓ Needs testing (static verified, hardware unverified)

The `leggett_lp_legacy` bed type follows the legacy app's 122 remote layouts,
each selected by the four-character code used in that app's manual or QR setup
(for example `A2RM`, `B1RM`, `ZR00`); the full list is `LP_LEGACY_PROFILE_CODES`
in `beds/leggett/lp_legacy_profiles.py`. I0RM has no proven bed commands in this app and
therefore exposes no remote action buttons. It does not change existing Richmat
or L&P QRRM configurations.

#### Setup

- Detection: none. Choose the **L&P Adjustable Base (legacy app)** row, or
  answer **L&P Adjustable Base legacy app (2.2.1)** in the
  [L&P question](leggett-platt.md#home-assistant-setup), then select the exact
  remote code and packet mode. An existing legacy entry reaches the other L&P
  routes through the same question in **Reconfigure**; **Configure** still
  changes its own settings.
- **Transport:** none of the codec's [transports](#transports). The app selects
  its characteristics at runtime, and its accepted report contains no fixed
  service or characteristic UUID that can safely be applied to every layout.
  Configure the bed's write characteristic UUID and, when known, its response
  characteristic UUID. These must come from the device's GATT information or a
  capture of the working app.
- The configured characteristic must be writable. Writes use write-with-response
  when it has the `write` property, otherwise write-without-response.
- BLE pairing is not required.
- Neither a name prefix nor a remote code proves the packet mode.
- Choosing a different layout changes the available controls.
- For paired beds with separate addresses, each side's stored profile provides
  its remote buttons even when that side is unavailable during startup.
- Profile, packet mode and GATT UUIDs stay specific to each side and are not
  shown in the pair's shared settings. To change them, unpair the beds, update
  the individual entries, then pair them again.
- Changing the layout or packet mode creates distinct action entities. Update
  automations to use those new entities; old actions remain unavailable instead
  of being silently reassigned to different commands.

#### Controls

Home Assistant exposes the selected layout's actions as named buttons, including
separate long-press actions where the app defines them. They also appear in the
adjustable bed card's utility section. Automations can call the ordinary
`button.press` action on these entities.

The app's labels describe the available actions. Some are pictograms with
uncertain physical meaning, so the integration keeps those descriptions instead
of assigning guessed head, foot or lumbar axes. Memory, massage and lights exist
only as the selected layout's named buttons; there is no RGB control.

##### Packet modes

Every control event has a command token: one character, optionally followed by
four hex digits (for example `n006E`). The catalog stores the tokens; the codec
builds the packet for the entry's mode.

| Mode | Packet |
|---|---|
| **Legacy** | The first character of the token as one byte, as Nordic framing sends a bare code |
| **Framed** | `6E 01 hi lo sum8`: the token's four hex digits as two bytes, the codec's command with `hi` in the side byte |

- Only controls with a proven encoding for the selected mode are exposed.
  Single-character tokens have no framed encoding.
- The two modes can send different bytes for the same token, as 6BRM's `40024`
  below shows.

<!-- generated:lp-legacy-tokens -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Token | Legacy | Framed | Notes |
|---|---|---|---|
| `n006E` | `6E` | `6E 01 00 6E DD` | Release of 1,372 of the 1,715 catalogued controls |
| `$0024` | `24` | `6E 01 00 24 93` |  |
| `40024` | `34` | `6E 01 00 24 93` | 6BRM; the two modes differ |
| `2` | `32` | Undefined | Single character, Legacy only |
| (empty) | Nothing | `6E 01 00 00 6F` | Empty token; Legacy writes nothing |
<!-- /generated -->

The complete per-layout catalog is `beds/leggett/lp_legacy_catalog.py`.

##### Event states

Each app button has a press event and a release (completion) event. Their
state decides how the integration sends them:

| State | Event | Integration behavior |
|---|---|---|
| 1 | Held press | Writes immediately, then repeats for the configured motor pulse count |
| 2 | Release | Always written after the press, even when the action is cancelled |
| 3 | Long press | **(long press)** button: waits the long-press time, then writes once |
| 4 | Short-press completion | Written after a completed press of 3 s or less that was not cancelled; on long-press controls it is the plain button |
| 5 | One-shot press | Writes once, then waits one tick |

#### Timing

See [Catalog app timing](#catalog-app-timing).

- Held controls repeat at the app's proven cadence. The configured motor pulse
  count determines how long a button invocation holds the control. The wait
  between writes accounts for time spent awaiting the Bluetooth write.
- The integration preserves each control's own release behavior and sends its
  release even when a running action is cancelled.
- One-shot controls do not inherit a movement repeat loop.
- The Stop button cancels the active action and performs its release cleanup.
  It cannot stop movement started outside this integration: the artifact
  defines no separate global emergency-stop command.

#### Notifications

The optional app-response diagnostic reports only the three exact patterns the
app recognizes. Their physical meaning is not established. They are not motor
positions, battery readings, a capability query or proof that an alarm is set.

<!-- generated:lp-legacy-notifications -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Frame | Reported effect |
|---|---|
| `6E 09 01 00 78` | `app_status_5` |
| `6E 07 01 01 77` | `alarm_routine_1` |
| `6E 07 01 02 78` | `alarm_routine_2` |
<!-- /generated -->

- The response characteristic is subscribed when it notifies or indicates, or
  read once when it is only readable.
- The diagnostic sensor is disabled by default.
- There is no invented position feedback, pairing requirement or RGB capability.

#### Evidence

The L&P legacy app sends only the packets of its accepted row019 catalog, in
both modes. APK Protocol Audit row019 records the catalog coverage, excluded
application-only behavior and the frozen evidence identity. Raw APKs and
analysis remain machine-local. Physical confirmation is deferred to users with
the corresponding bed after a beta or release; it is separate from static
protocol verification.

### Casper and Hush family

**Status:** ❓ Needs testing (accepted APK audits, hardware unverified)

The Casper Base and Hush Base apps ship one Richmat library: its transports,
connect queries, fixed codes, receive parser and settings records are the same
in both. Each app keeps its own product catalog, in
[`beds/casper_base/catalog.py`](../../custom_components/adjustable_bed/beds/casper_base/catalog.py)
and [`beds/hush_base/catalog.py`](../../custom_components/adjustable_bed/beds/hush_base/catalog.py);
the library's data is in
[`profiles/casper.py`](../../custom_components/adjustable_bed/profiles/casper.py).
Setup, the separate sleep sensors and the remote finder are in the
[Casper Base app](casper-base.md) and [Hush Base](hush-base.md) guides.

#### Setup

- Detection: none. Choose the app, then the exact product. Shared services, and
  the HLRM/JXRM strings, never identify an app or a product.
- The library looks up N1, then W1 to W5 of the [transport table](#transports).
  Home Assistant pairs the write and notify roles within one coherent service:
  the first service the bed exposes whose write characteristic is writable wins,
  and its first notify characteristic receives.
- N1 takes the bare code; the other services take the framed command
  `6E 01 side code sum8`. The light timer and colour, countdown and record
  frames keep their own framing on N1 too.
- Writes go without response when the write characteristic offers
  `write-without-response`, otherwise with response.
- Neither the bed nor the sensor path requires a PIN or app authentication.
- **One-address sides:** only products with the side flag, on a framed
  transport. Enabling sides connects to the bed first so Home Assistant can
  verify the transport. Right sends side `01`; Both sends the left frame, then
  the right one. The music page and the automatic anti-snore trigger always use
  side `00`, as the apps do.
- **Session setup:** after subscribing, the bed is queried in this order. The
  bed's notification channel starts even when angle sensing is disabled.

<!-- generated:casper-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | Framed | N1 |
|---|---|---|
| Exit limit | `6E 02 01 00 71` | `00` |
| Check clock | `6E 08 01 01 78` | `01` |
| Check light | `6E 0A 00 01 79` | `01` |
| Check music | `6E 15 01 01 85` | `01` |
| Time sync, on products with repeating alarms | calendar record `08 03 01`, length after `20` | same |
<!-- /generated -->

#### Controls

- The selected product's catalog row decides its motor covers and named action
  buttons; the same name can carry a different code in another product. Frames
  are [commands](#framing-and-checksum) at side `00`.
- Movement repeats its code once per tick for the entry's pulse count, then
  sends STOP `6E` on the same side with a fresh cancel event. Massage and fan
  intensity taps send once, then STOP. Every other action is one write.
- Save buttons send the action's program code; the apps' three-second gesture
  does not require holding a Home Assistant button. An action without a program
  code has no save button, avoiding the apps' unsafe zero-code long-press
  fallback.
- **Music page:** capability-gated on music products, always side `00`. The
  music Bluetooth flag follows the latest ordinary or extended reply or the
  optimistic page switch, while raw events stay separate. The soundtrack switch
  keeps its debounce and delay (see [Catalog app timing](#catalog-app-timing)).

<!-- generated:casper-music -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App action | Casper Base | Hush Base |
|---|---|---|
| `MusicBlueToothSwitch` | `D8` | `D8` |
| `MusicSwitchSoundTrack` | `C4` | `C4` |
| `MusicShakeMode` | `D6` | `D6` |
| `MusicVolumuDown` | `D5` | `D5` |
| `MusicVolumuUp` | `D4` | `D4` |
| `MusicNextSong` | `D3` | `D3` |
| `MusicPausePlay` | `D7` | `D7` |
| `MusicPreviousSong` | `D2` | `D2` |
<!-- /generated -->

#### Timing

See [Catalog app timing](#catalog-app-timing). The HA command lock serializes
operations and owns their timers; the apps' leaked timers, late sends after
disposal and overlapping poll and write callbacks are not reproduced.

#### Notifications

The bed state diagnostic exposes the product, every parsed event, the alarm
records and malformed-packet errors.

| Notification | Event |
|---|---|
| `6e 09 01 00 78` | Clock page available |
| `6e 0e 00 03 7f` | Light page available |
| `6e 1a 00 01 89` | Aroma available |
| `6e 07 01 01 77` / `6e 07 01 02 78` | Alarm set / cancelled |
| `6e 16 01 01 86` | Music page available |
| `6e 90 c1 01 c0` | Detection available |
| `6e 21 00 00 8f` | Snore detection available |
| `6E 90 xx yy zz` (5 bytes) | High nibble of byte 2: `0` protocol version, `1` bed mode, `3` raw motor index/status/value, `A` massage mode and zones, `B` USB/play/music-follow/Bluetooth, `C` detection status/details, `D` music volume or shake gear |
| 7 bytes with `90` at byte 1, or 16 bytes | Raw desk height values |
| `6E 20 …` (extended) | Categories `01` motor, `02` massage, `03` white LED, `04` RGB, `05` alarm list/update, `06` snore/bed exit/sleep name, `09` music, `0A` check, `0B` press mode/same control, `0F` desk |

- Raw motor and desk events keep their original index and values, without
  guessing a physical axis or unit.
- Alarm list responses suppress identical duplicates; updates replace the first
  matching ID.
- Capability, RGB, music and acknowledgement consumers keep separate state.
- Every ordinary and extended parser branch is retained. Extended frames must
  match their length and the codec's `sum8`.
- **Receive framing:** complete 5, 7 and 16-byte ordinary notifications stay
  intact; stream boundaries are accepted only at those lengths. Marker-valued
  payload and checksum bytes do not truncate a notification, and short five-byte
  fragments are kept. This corrects the apps' marker-splitting bug without
  inventing a length header or adding an ordinary checksum requirement. Length
  alone cannot separate every fragmented or coalesced combination of the
  variable ordinary formats.

#### Services

`adjustable_bed.casper_base` and `adjustable_bed.hush_base` send these frames;
the [Casper Base](casper-base.md#configuration-actions) and
[Hush Base](hush-base.md#configuration-actions) guides list the fields, gates
and choices. Records are extended frames with the length after `20`:
`6E 20 len category subtype operation values sum8`, where `len` counts every
byte. Operation `01` writes and `00` queries; replies use `02` and `03`.

| Operation | Frame |
|---|---|
| `light_rgb` | `6E 0C FF red sum8` + `6E 0D green blue sum8`, one write |
| `light_seconds` | `6E 0B high low sum8`, seconds; zero is the always-on `6e 0b ff ff 77` |
| `light_off` | Command `75` at side `00` (`6e 01 00 75 e4`, bare on N1) |
| `rgb_power` | Record `04 04 01`: `00 enabled` |
| `rgb_color` | Record `04 01 01`: `00 red green blue` |
| `rgb_timer` | Record `04 02 01`: `00 minutes_high minutes_low` |
| `rgb_mode`, `rgb_groove` | Record `04 05 01`: `00 01 mode` or `00 02 mode` |
| `rgb_breathe` | Record `04 06 01`: `00` (`6e 20 08 04 06 01 00 a1`) |
| `alarm`, `alarm_cancel` | Countdown pair `6E 06 minutes_high mode sum8` and `6E 05 minutes_low 00 sum8`, the mode being the position's recall code; cancel sends zero minutes and mode. The order is each app's (see its Services) |
| `repeat_alarm` | Record `05 01 01`: `slot reserved hour minute mode mask` |
| `repeat_delete` | Record `05 02 01`: `slot` |
| `repeat_query` | Record `05 01 00`: `00` (`6e 20 08 05 01 00 00 9c`) |
| `time_sync` | Record `08 03 01`: `year-1970 month day hour minute second`, local time |
| `sleep_name` | Record `06 03 00`: `00` (`6e 20 08 06 03 00 00 9f`) |
| `snore_detector` | Every fifth positive sample sends the anti-snore command `46` at side `00` |

- Repeating-alarm `mask`: Monday is bit 7 through Sunday bit 1; bit 0 is
  `enabled`. The reserved byte of an existing alarm is kept when editing it.
- RGB timers are sent as a 16-bit minute value but received as
  `high * 60 + low`. This asymmetry is the apps' and is not normalized.

#### Evidence

Both apps send only frames frozen from their accepted reports
(`tests/casper_base_vectors.py`, `tests/hush_vectors.py`);
`tests/test_casper_base_vectors.py` and `tests/test_hush_vectors.py` rebuild
each one through this codec. Physical motor effects, firmware compatibility,
ATT behavior and sensor accuracy remain unverified. Real users can supply
captures after a beta or release; maintainer hardware is not required.

### Casper Base

**App:** [Casper Base](https://play.google.com/store/apps/details?id=com.richmat.casperbase) 1.0.8 (version code 10800), `com.richmat.casperbase`

**Status:** ❓ Needs testing (accepted APK audit, hardware unverified)

Behaves as the [Casper and Hush family](#casper-and-hush-family), except as below.

#### Setup

- The `casper_base` bed type. Choose **Casper Base app (select product)**, then
  **PRO** or **MAX**, the app's own products. Its protocol variant is the product.
- The 37 other choices, labelled **stored profile**, are products the app's
  stored-product decoder accepts. They are explicit choices, never inferred.
- One-address sides: the stored L400SH and L300SH layouts.

#### Controls

PRO and MAX send these frames. On N1 only the code is sent.

<!-- generated:casper-base-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App action | PRO | MAX |
|---|---|---|
| `HeadUp` | `6E 01 00 24 93` | `6E 01 00 24 93` |
| `HeadDown` | `6E 01 00 25 94` | `6E 01 00 25 94` |
| `FootUp` | `6E 01 00 26 95` | `6E 01 00 26 95` |
| `FootDown` | `6E 01 00 27 96` | `6E 01 00 27 96` |
| `LumberUp` | `6E 01 00 3F AE` | `6E 01 00 41 B0` |
| `LumberDown` | `6E 01 00 40 AF` | `6E 01 00 42 B1` |
| `LightBoard` | `6E 01 00 3C AB` | `6E 01 00 50 BF` |
| `MotorReset` | `6E 01 00 31 A0` | `6E 01 00 31 A0` |
| `MassageHeadInstensityStrengthen` | `6E 01 00 4C BB` | `6E 01 00 4C BB` |
| `MassageFootInstensityStrengthen` | `6E 01 00 4E BD` | `6E 01 00 4E BD` |
| `MassageModeChange` | `6E 01 00 48 B7` | `6E 01 00 48 B7` |
| `MassageModeAllOff` | `6E 01 00 47 B6` | `6E 01 00 5E CD` |
| `Massage10MinuteTimer` | `6E 01 00 5F CE` | `6E 01 00 5F CE` |
| `Massage20MinuteTimer` | `6E 01 00 63 D2` | `6E 01 00 63 D2` |
| `Massage30MinuteTimer` | `6E 01 00 61 D0` | `6E 01 00 61 D0` |
| `TVPosition` | `6E 01 00 58 C7`, save `6E 01 00 64 D3` | `6E 01 00 58 C7`, save `6E 01 00 64 D3` |
| `LoungePosition` | `6E 01 00 59 C8`, save `6E 01 00 65 D4` | `6E 01 00 59 C8`, save `6E 01 00 65 D4` |
| `AntiSnoring` | `6E 01 00 46 B5`, save `6E 01 00 69 D8` | `6E 01 00 46 B5`, save `6E 01 00 69 D8` |
| `ZeroGravity` | `6E 01 00 45 B4`, save `6E 01 00 66 D5` | `6E 01 00 45 B4`, save `6E 01 00 66 D5` |
| `MemoryPosition1` | `6E 01 00 2E 9D`, save `6E 01 00 2B 9A` | `6E 01 00 2E 9D`, save `6E 01 00 2B 9A` |
| `PillowUp` | n/a | `6E 01 00 3F AE` |
| `PillowDown` | n/a | `6E 01 00 40 AF` |
| `BedLight` | n/a | `6E 01 00 3C AB` |
| STOP | `6E 01 00 6E DD` | `6E 01 00 6E DD` |
<!-- /generated -->

Only stored products use these further actions:

<!-- generated:casper-base-stored -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App action | Code | Program code |
|---|---|---|
| `MemoryPosition3` | `30` | `2D` |
| `MemoryPosition2` | `2F` | `2C` |
| `HeadAndFootDown` | `2A` | none |
| `HeadAndFootUp` | `29` | none |
| `Motor3Down` | `72` | none |
| `Motor3Up` | `71` | none |
| `PillowDown` | `42` | none |
| `PillowUp` | `41` | none |
| `HeatingOff` | `77` | none |
| `HeatingHighGear` | `79` | none |
| `HeatingLowGear` | `78` | none |
| `FanWaveMode` | `A5` | none |
| `FanPulseMode` | `A4` | none |
| `FanConstantMode` | `A3` | none |
| `FanAllOff` | `A1` | none |
| `Fan2InstensityStrengthen` | `8B` | none |
| `Fan1InstensityStrengthen` | `8A` | none |
| `MusicBlueToothSwitch` | `D8` | none |
| `CoaxingSleepMode` | `86` | none |
<!-- /generated -->

- When the music Bluetooth flag is set, the soundtrack switch first sends the
  Bluetooth switch `D8`.
- Fresh PRO and MAX gain no music page, sensor menu or repeating alarms from a
  reply.

#### Services

- Every light operation needs the product's light flag and the light capability
  reply; the RGB flag selects the `rgb_*` operations, otherwise the ordinary
  ones.
- The countdown alarm sends `6E 06 minutes_high mode sum8` first, then
  `6E 05 minutes_low 00 sum8`; cancel sends `6e 06 00 00 74`, then
  `6e 05 00 00 73`.

#### Evidence

Casper Base sends only the frames frozen from its accepted row101 report:
its builder vectors (`tests/fixtures/casper_base/builders.json`) and command
ledger. APK Protocol Audit row101 records the accepted seals, every discovery,
implementation and test references and all exclusions.

### Hush Base

**App:** [Hush Base](https://play.google.com/store/apps/details?id=com.richmat.hushbase) 1.0.5 (10501), `com.richmat.hushbase`

**Status:** ❓ Needs testing (artifact verified; hardware unverified)

Behaves as the [Casper and Hush family](#casper-and-hush-family), except as below.

#### Setup

- The `hush_base` bed type. Choose **Hush Base app (select product)**, then the
  exact model; the app's own twelve products, catalog indices 46 to 57, come
  first. Its protocol variant is the product.
- The other catalog indices are products a phone restored under the shared
  catalog, labelled **restored profile**. They keep the Hush app's own rows and
  are explicit choices, never inferred.
- One-address sides: the products with the side flag. Nordic has no side byte,
  so one-address pairing is rejected there. Two-address pairs keep independent
  profile and connection ownership.
- Every operation keeps its admitted connection: a write that would land on a
  newer connection fails instead.

#### Controls

The catalog's codes, gated by the selected product; entries with the same name
can carry different codes.

<!-- generated:hush-base-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App action | Code | Program code |
|---|---|---|
| `HeadUp` | `24` | none |
| `HeadDown` | `25` | none |
| `FootUp` | `26` | none |
| `FootDown` | `27` | none |
| `LumberUp` | `3F` | none |
| `LumberDown` | `40` | none |
| `LightBoard` | `3C` | none |
| `MotorReset` | `31` | none |
| `MassageHeadInstensityStrengthen` | `4C` | none |
| `MassageFootInstensityStrengthen` | `4E` | none |
| `MassageModeChange` | `48` | none |
| `MassageModeAllOff` | `47` | none |
| `Massage10MinuteTimer` | `5F` | none |
| `Massage20MinuteTimer` | `63` | none |
| `Massage30MinuteTimer` | `61` | none |
| `TVPosition` | `58` | `64` |
| `LoungePosition` | `59` | `65` |
| `AntiSnoring` | `46` | `69` |
| `ZeroGravity` | `45` | `66` |
| `MemoryPosition1` | `2E` | `2B` |
| `PillowUp` | `3F` | none |
| `PillowDown` | `40` | none |
| `LumberUp` | `41` | none |
| `LumberDown` | `42` | none |
| `LightBoard` | `50` | none |
| `BedLight` | `3C` | none |
| `MassageModeAllOff` | `5E` | none |
| `HeadAndFootUp` | `29` | none |
| `HeadAndFootDown` | `2A` | none |
| `PillowUp` | `41` | none |
| `PillowDown` | `42` | none |
| `MusicBlueToothSwitch` | `D8` | none |
| `MemoryPosition2` | `2F` | `2C` |
| `Motor3Up` | `71` | none |
| `Motor3Down` | `72` | none |
| `MemoryPosition3` | `30` | `2D` |
| `CoaxingSleepMode` | `86` | `89` |
| `Fan1InstensityStrengthen` | `8A` | none |
| `Fan2InstensityStrengthen` | `8B` | none |
| `FanAllOff` | `A1` | none |
| `FanConstantMode` | `A3` | none |
| `FanPulseMode` | `A4` | none |
| `FanWaveMode` | `A5` | none |
| `HeatingLowGear` | `78` | none |
| `HeatingHighGear` | `79` | none |
| `HeatingOff` | `77` | none |
| `FanChangeMode` | `A2` | none |
| `FanForwardAndBackwardChange` | `8C` | none |
| `FanTimer2Hour` | `A6` | none |
| `FanTimer3Hour` | `A7` | none |
| `FanTimer5Hour` | `A8` | none |
| `MassageModeAllOff` | `DC` | none |
| `ReleasePressurPosition` | `C5` | none |
| `MassageModeConstant` | `3A` | none |
| `MassageModePulse` | `38` | none |
| `MassageModeWave` | `39` | none |
| `CoaxingSleepMode` | `76` | `89` |
<!-- /generated -->

- `PhoneLight` is never exposed. Text actions with no program code are not
  offered as saves, instead of sending the ambiguous zero.
- Every fan action, including modes and timers, sends once, then STOP.
- The soundtrack switch first sends the Bluetooth switch `D8` when the music
  Bluetooth flag is clear, then `C4`.

#### Timing

Partial bed frames expire 500 ms after the last chunk.

#### Notifications

Hush adds to the family's parser:

- `6E 20` and `6E 21` records carry a one-byte length and end in `sum8`;
  `6E 40` frames carry a two-byte length and end in a CRC-16/XMODEM, checked by
  the codec's `is_valid_crc`. Firmware installation over `6E 40` is excluded;
  the validated transport observation is kept.
- `6e 23 01 84 16` / `6e 23 00 84 15` report the remote locked or unlocked, and
  `6e 23 a0 6e 9f` that configuration is available.
- Extended categories add motor angle, snore count and time, remote lock, music
  volume, shake and USB, press mode, blanket, fan, atomization and heating
  values; desk records add the unit and monitor heights.
- Malformed packets are bounded and marker-valued ordinary data is preserved.
  No raw axis is assigned a physical motor or calibrated unit.

#### Services

- Every light operation needs the light capability reply; the product's
  lighting flag selects the RGB operations or the ordinary ones.
- The countdown alarm sends `6E 05 minutes_low 00 sum8` first, then
  `6E 06 minutes_high mode sum8`.
- The last light duration and colour persist for the entry.

#### Evidence

Hush Base sends only the frames frozen from its accepted row126 report, whose
products, shared builders and auxiliary shards are listed in
`tests/hush_vectors.py`. APK Protocol Audit row126 records the accepted source
references, dispositions and exclusions.

### SonicSleep

**App:** [SonicSleep / 소닉슬립](https://play.google.com/store/apps/details?id=com.richmat.sonicsleep) 1.0.4 (10400), `com.richmat.sonicsleep`

**Status:** ❓ APK-verified; hardware unverified.

#### Setup

Search for **SonicSleep** in manual setup or Configure, under Richmat. Setup
stores the fixed `one` / IQRM product and two physical motors. Head, foot and
combined controls are selections of those motors. Names and shared services
never select another product, remote code or downloaded catalog. Each physical
receiver keeps its own app settings in a two-address pair. There are no
single-address side bytes, authentication challenge or mandatory bond.
Home Assistant owns Bluetooth adapters, proxies, retries and connection handoff.

The app's scan matches the case-sensitive substrings in the table. GATT discovery
iterates recognized services in platform order: first eligible write and notify
roles are retained independently, while each later recognized service overwrites
the raw/framed route selector. The writer requires the exact write UUID and
`write`; a write-without-response-only characteristic is rejected. The first
`notify` characteristic wins, regardless of the expected UUID. Its writer's
properties select the write response mode. Multi-service firmware can expose
mixed roles under this source rule; physical compatibility remains unverified.

#### Controls

Two individual covers and one combined control expose the six held directions.
Flat and six preset recalls send once. Every preset has an explicit save
control. The native card asks for confirmation before saving, then sends the
save opcode once. Automations can call the save entity or `save_preset`
explicitly. The builder's long enum is a choice of opcode, not a physical hold
requirement. The observed-only massage, light, position and split information
never creates extra control entities or calibrated position sliders.

<!-- generated:sonicsleep -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Product | Stored product | Physical motors | Refresh | Scan name substrings (case sensitive) |
|---|---|---|---|---|
| IQRM | one | 2 (head and foot) | 100 ms | QRRM, COOL, MPE_, 209A, BED- |

| Route | Service | Write | Expected notify constant | Function format |
|---|---|---|---|---|
| Nordic | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | raw |
| W1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed |
| W2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | framed |
| W3 | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` | framed |
| W4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | framed |
| W5 | `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | `00000003-3c17-d293-8e48-14fe2e4da212` | framed |

| Control | Nordic | W1–W5 |
|---|---|---|
| head_up | `24` | `6E 01 00 24 93` |
| head_down | `25` | `6E 01 00 25 94` |
| foot_up | `26` | `6E 01 00 26 95` |
| foot_down | `27` | `6E 01 00 27 96` |
| both_up | `29` | `6E 01 00 29 98` |
| both_down | `2A` | `6E 01 00 2A 99` |
| flat | `31` | `6E 01 00 31 A0` |
| zero_gravity | `45` | `6E 01 00 45 B4` |
| save_zero_gravity | `66` | `6E 01 00 66 D5` |
| lounge | `59` | `6E 01 00 59 C8` |
| save_lounge | `65` | `6E 01 00 65 D4` |
| tv | `58` | `6E 01 00 58 C7` |
| save_tv | `64` | `6E 01 00 64 D3` |
| anti_snore | `46` | `6E 01 00 46 B5` |
| save_anti_snore | `69` | `6E 01 00 69 D8` |
| memory_1 | `2E` | `6E 01 00 2E 9D` |
| save_memory_1 | `2B` | `6E 01 00 2B 9A` |
| memory_2 | `2F` | `6E 01 00 2F 9E` |
| save_memory_2 | `2C` | `6E 01 00 2C 9B` |

| Startup | Nordic | W1–W5 |
|---|---|---|
| deviceFunctionItemExitLimit | `00` | `6E 02 01 00 71` |
| deviceFunctionItemCheckClock | `01` | `6E 08 01 01 78` |

| Extended operation (all routes) | Frame |
|---|---|
| List alarms | `6E 08 20 05 01 00 00 9C` |
| Query bed link name | `6E 08 20 06 03 00 00 9F` |
| Delete received ID 7 | `6E 08 20 05 02 01 07 A5` |
| New/edit ID 3, 06:30, zero gravity, Monday/Sunday, enabled | `6E 0D 20 05 01 01 03 00 06 1E 45 83 91` |
| Cached ID 3, opaque 07, 06:30, mode 45, Monday/Sunday, disabled | `6E 0D 20 05 01 01 03 07 06 1E 45 82 97` |
| Epoch, +05:30 truncated to 05 | `6E 0C 20 08 02 01 6A F5 01 80 05 8A` |
| Calendar, 2026-11-12 05:30:00 | `6E 0D 20 08 03 01 38 0B 0C 05 1E 00 19` |
<!-- /generated -->

#### Timing

Notifications are registered before enabling the channel. Startup sends
exit-limit, clock query, bed link-name query, epoch sync and calendar sync in
that order, at the profile's write cadence. Exit-limit is startup only.
Extended records retain their framing on the Nordic raw route.

The first held refresh waits one tick before the requested movement window
starts, so a 100 ms movement can send one refresh. HA awaits each radio write
before the next tick, cancels unsent refreshes, drains an in-flight write, and never catches
up missed ticks. Timed movement and renewable card holds use the real command
scheduler, captured physical owner and a bounded deadline. Release and STOP end
refresh without sending an extra packet. Firmware watchdog and physical stopping
behavior remain unverified. Sequential two-link pairs reject renewable Both
holds before motion; finite operations and individual-side controls remain usable.

#### Notifications

Common five-byte messages have no generic checksum gate. The source stream can
consume a three-byte common fragment before its tail arrives; extended frames
wait for their declared length and validate the additive checksum. HA preserves
valid-frame behavior, bounds pending input and rejects malformed field access.
The app's weaker bounds are not a claim about HA validation in the app.

The state sensor publishes only observations from the current physical session:
clock/light/snore/diagnostic capabilities, protocol version, bed mode, raw motor
and travel values, massage/follow-shake, white/RGB light, anti-snore/off-bed,
press/split status, BED diagnostic frames, alarm records and bed link name.
No percentage/degree calibration or battery value is inferred. Reconnect and
controller replacement invalidate the cache and old notification callbacks.

Alarm list replies insert at the front if the record is absent. Escalations
replace an existing matching ID only. ACKs remain observations, never retry
instructions. Cached enable/disable preserves received ID, opaque byte, hour,
minute, raw mode and weekday bits, replacing enabled bit zero only. Form edits
use selected time/preset values and zero the opaque field. Selected edit/delete
reuse received IDs, including IDs outside the new-ID allocator. New allocation
searches 1 through 7 and hides add after seven list entries; this is app policy,
not hardware capacity.

The link name uses direct byte-to-character conversion. NULs are retained and
UTF-8 is not decoded. In the app this name is stored and adds a separate sleep
peripheral tab; its global scan and disconnect-all operations can affect that
peripheral. HA retains the bed query/reply but manages only the selected bed's
owned connection. The separate MM/SXB sleep sensing, reports, OTA and network
paths remain outside BED support, even when their UUID overlaps W5.

#### Services

`adjustable_bed.sonicsleep` exposes `list`, `new`, `edit`, `toggle`, `delete`,
`link_name` and `sync_clock`, with device and paired-side targeting. Alarm actions
require a clock-capability reply. Read/modify/write actions require current
connection-owned alarm records; missing replies reject before alarm writes.
After a mutation, that ID requires fresh received fields before another mutation;
an ACK alone cannot validate the previous record. Prepared fields are checked
again under the BLE lock immediately before dispatch.
A new alarm refreshes and collects observed list records before allocating an
ID. Because no empty-list or list-completion reply is proven, silence rejects
creation too. A changed cache or released/replaced connection invalidates a
prepared all-target settings operation. Choose an individual side if a
sequential pair cannot retain both live alarm caches.

For forms, `hour`, `minute`, `mode`, `weekdays` (Monday 0 through Sunday 6) and
`enabled` supply explicit values; `alarm_id` identifies a received record for
edit, toggle or delete. Toggle ignores form defaults and preserves raw fields.
Clock synchronization preserves whole-hour timezone truncation and year minus
1970 encoding. No phone telemetry or sleep analytics reader is included.

#### Evidence

APK Protocol Audit row179, SonicSleep 1.0.4 (10400), artifact SHA-256
`173f81b5e902650733fdd44968f31cf9ceee2b5c376d361acf043b985612b5e4`.
All accepted command literals use the existing Richmat codec; receive and stream
contracts are covered by the committed SonicSleep fixtures. Opaque alarm fields
and caller-specific domains include the accepted R179-A001 repair. Hardware
validation belongs to external beta/release users with existing beds.

### Luuna +

**App:** [Luuna +](https://play.google.com/store/apps/details?id=com.richmat.luuna) 2.0.1 (20102), `com.richmat.luuna`

**Status:** ❓ Needs testing. Static BLE evidence is verified; hardware remains unverified.

#### Setup

Select **Luuna + app**, then Rise, Rise Pro or Rise Pro Light. The product is
explicit: a shared Richmat service or a catalog code in the Bluetooth name does
not choose it. Setup derives the motor count, massage and disabled angle sensing.
The profile id is `luuna:<product>`. Two-address pairs keep each receiver's choice.
There is no one-address Left/Right selector, PIN, bond command or authentication
handshake in this app. Home Assistant manages the BLE connection and proxy path.

The app scans for case-sensitive name fragments shown below. Prefix discovery
hints and common Richmat service hints admit matching beds; generic detection
continues to suggest the Richmat family, where users choose their app.
The writer and first notify-capable characteristic must be in the same supported
service. Nordic sends bare opcodes; configuration builders retain their own
framing on every transport. Write-without-response is used when the selected
writer supports it, otherwise writes use a response.

#### Controls

<!-- generated:luuna -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Product | Stored key | Catalog code | Motors | Massage | Memory slots | Sleep name | Light flag |
|---|---|---|---|---|---|---|---|
| Rise | `rise` | V1RM | 2 | no | 1 | yes | no |
| Rise Pro | `risepro` | JVRM | 4 | yes | 2 | no | no |
| Rise Pro Light | `riseprolight` | FDRN | 4 | yes | 1 | yes | yes |

| Action | Normal opcode | Program opcode | Framed write | Products |
|---|---|---|---|---|
| HeadUp | `24` | none | `6E 01 00 24 93` | Rise, Rise Pro, Rise Pro Light |
| HeadDown | `25` | none | `6E 01 00 25 94` | Rise, Rise Pro, Rise Pro Light |
| FootUp | `26` | none | `6E 01 00 26 95` | Rise, Rise Pro, Rise Pro Light |
| FootDown | `27` | none | `6E 01 00 27 96` | Rise, Rise Pro, Rise Pro Light |
| PillowUp | `41` | none | `6E 01 00 41 B0` | Rise Pro, Rise Pro Light |
| PillowDown | `42` | none | `6E 01 00 42 B1` | Rise Pro, Rise Pro Light |
| LumberUp | `3F` | none | `6E 01 00 3F AE` | Rise Pro, Rise Pro Light |
| LumberDown | `40` | none | `6E 01 00 40 AF` | Rise Pro, Rise Pro Light |
| MotorReset | `31` | none | `6E 01 00 31 A0` | Rise, Rise Pro, Rise Pro Light |
| MassageHeadInstensityStrengthen | `4C` | none | `6E 01 00 4C BB` | Rise Pro, Rise Pro Light |
| MassageFootInstensityStrengthen | `4E` | none | `6E 01 00 4E BD` | Rise Pro, Rise Pro Light |
| MassageModeChange | `48` | none | `6E 01 00 48 B7` | Rise Pro, Rise Pro Light |
| MassageModeAllOff | `5E` | none | `6E 01 00 5E CD` | Rise Pro, Rise Pro Light |
| Massage10MinuteTimer | `5F` | none | `6E 01 00 5F CE` | Rise Pro, Rise Pro Light |
| Massage20MinuteTimer | `63` | none | `6E 01 00 63 D2` | Rise Pro, Rise Pro Light |
| Massage30MinuteTimer | `61` | none | `6E 01 00 61 D0` | Rise Pro, Rise Pro Light |
| AntiSnoring | `46` | `69` | `6E 01 00 46 B5` | Rise, Rise Pro, Rise Pro Light |
| ZeroGravity | `45` | `66` | `6E 01 00 45 B4` | Rise, Rise Pro, Rise Pro Light |
| TVPosition | `58` | `64` | `6E 01 00 58 C7` | Rise Pro, Rise Pro Light |
| MemoryPosition1 | `2E` | `2B` | `6E 01 00 2E 9D` | Rise, Rise Pro, Rise Pro Light |
| MemoryPosition2 | `2F` | `2C` | `6E 01 00 2F 9E` | Rise Pro |

| Startup/query | Framed write | Nordic write |
|---|---|---|
| ExitLimit | `6E 02 01 00 71` | `00` |
| CheckClock | `6E 08 01 01 78` | `01` |
| CheckLight | `6E 0A 00 01 79` | `01` |

| Setting | Value |
|---|---|
| Transports | n1, w5, w4, w3, w2, w1 |
| Scan keywords (case-sensitive contains) | QRRM, COOL, MPE_, 209A, BED- |
| Write/held refresh tick | 100 ms |
| Clock/light query dispatch interval | 300 ms |
| HA service capability wait budget | 3 s |
| Light duration choices (seconds) | 0, 300, 600, 900 |
| Warm / cold RGB | (255, 140, 20) / (255, 255, 255) |
<!-- /generated -->

Every product has Flat, Anti-Snore, Zero-G and Memory 1. Preset save buttons send
their separate program opcode once. Rise Pro adds Memory 2; Rise Pro Light does
not. Massage controls are one-shot actions, including intensity steps, mode,
off and the three timer buttons. The ordinary strip page requires both the
Rise Pro Light flag and its exact light capability announcement.

#### Timing

The generated table gives the app's refresh cadence. A finite movement uses the
entry's pulse count; a renewable hold refreshes until release or its safety
ceiling. Release cancels refresh without transmitting a STOP opcode. This is the
app's complete cleanup behavior, not a measured firmware stopping guarantee.
Commands await serialized GATT writes; the Android timer's duplicated-head race
and pending movement queue are not reproduced. Cancellation prevents queued
refreshes from reaching a replacement connection.

After subscribing, startup sends ExitLimit, the local binary calendar for every
product, and the sleep-advertisement-name query for Rise and Rise Pro Light.
Clock and light queries follow on the product-query schedule. It sends no
version, music or other unused shared-library query. Disconnect clears receive
fragments and capability observations; old callbacks cannot re-enable them.

#### Notifications

Only the exact clock and light announcements enable their corresponding controls.
Service preflight reconnects each selected receiver through its query lane and
waits within the generated HA admission budget for the current connection's reply.
It rejects a missing reply instead of reusing a disconnected capability. Sequential
pairs validate one receiver at a time and revalidate a replacement connection.
Alarm add/cancel acknowledgements update status. The bed-provided sleep name is
retained as diagnostic state; it does not open an accessory connection.
Other decoded shared-library messages remain structured diagnostic observations.
Their presence does not enable extra products, position sliders, music, blanket,
desk, repeating-alarm or side-control commands. Motor height/type use the audited
unsigned offsets, with optional angle and monitor height; they have no calibrated
axis mapping. Empty payload classes remain empty.

Home Assistant preserves incomplete common frames and bounds invalid extended
lengths instead of copying the app's premature fragment consumption or zero-length
loop. Extended records require their declared length and checksum. Malformed short
alarm/press records are rejected instead of indexing beyond their payload.

#### Services

`adjustable_bed.luuna` offers `alarm`, `alarm_cancel`, `light_rgb`, `light_seconds`,
`light_warm`, `light_cold`, `light_off`, `sleep_name` and `time_sync`. Generic
memory and movement actions use the same profile and command serialization.

Alarms use one selected preset from that product's alarm list and a local hour
and minute. The countdown ignores seconds; the current minute wraps to tomorrow.
Both save and cancel write the low frame first, then the high/action frame.
There is no weekday or repeating schedule on this live alarm path.
Light RGB is one combined write. Warm/cold accept `value` as brightness percent;
light duration accepts the generated choices, with zero meaning always on.
Off is its own opcode, independent of duration. Capability and product checks
run before any target writes.

#### Evidence

Accepted APK Protocol Audit unit146, including scoped repair001 and independent
audit002. All normal/program, dynamic-builder and parser literal cases are kept
in `tests/fixtures/luuna/` and exercised by `tests/test_luuna.py`. The existing
Richmat codec reproduces the app's literal command frames without a new codec.
Physical movement, stop latency, supported firmware, calibration and negotiated
MTU remain for real beta/release users to validate.

### MLILY Control

**App:** [MLILY Control](https://play.google.com/store/apps/details?id=com.richmat.mlily2) 5.0.2 (50200), `com.richmat.mlily2`

**Status:** ❓ Needs testing. Static APK behavior verified; hardware remains unverified.

#### Setup

Choose **MLILY Control**, then the exact product or its explicit remote-choice
route. Search by the product code shown in the app. The name helper suggests
an admitted product from the Bluetooth name, but shared services cannot identify
the app. A remote-choice route records both the chooser and its selected remote.
Single-address Left/Right controls are offered only when that product lists both;
Both is sent as a native side only when the product lists it.

The app uses the six transports in the generated profile table. Nordic sends a
bare byte only for selected-detail commands. Explicit RGB, timer, clock, repeat
alarm, name and synchronization helpers retain their framed packets on Nordic.
There is no app-owned encryption or PIN handshake in these routes.

Independent **RM- (MM)** and **HJ- (SXB)** sleep devices need separate entries.
Their advertised name selects the route, independently of the bed product.

#### Controls

The generated tables retain every product's ordered control and alarm IDs.
A hidden or disabled descriptor is retained as data and creates no button.
Phone-light, Clock and Voice callbacks are local navigation; use the alarm action
for scheduling. The MLILY menu expands to its four directional controls and reset.
A normal None, title or logo descriptor can send zero and is not assumed to be a
hardware no-op. Labels identify the app's controls without assigning unproven
physical axes to motor numbers.

BRRM, APRM, YFRM and YGRM start in release mode. BRRM, YFRM and YGRM replace
force-long controls with None while release mode is set; APRM does not. Flagged
head/foot controls change the local release/hold latch. The Memory button sends
its command before changing its latch. E3RM, GXRM, JDRM, JFRM and JGRM use that
latch for their declared save actions; GXRM TV stays outside this rule.

The light menu requires the exact light capability reply and the current
product's light getter. It offers RGB, a 0 to 900 second duration in 60 second
steps, and close. Zero duration means always on. D1RM and D9RM alone expose the
bottom massage countdown; D9RM has its own off operand.

<!-- generated:mlily-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| ID | App control | Gesture | Framed short / long (Left) | Nordic short / long | Flags |
|---|---|---|---|---|---|
| 9f4f2493dee8 | Head Up | sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `34` / `00` |  |
| 75ae7f8d618f | Head Down | sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `37` / `00` |  |
| ec0a15aea952 | Foot Up | sustainPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `36` / `00` |  |
| 334e68909524 | Foot Down | sustainPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `41` / `00` |  |
| 4fbb0fc77db8 | Head And Foot Up | sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `38` / `00` |  |
| 9ea62e37e453 | Head And Foot Down | sustainPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `39` / `00` |  |
| 40c92af58e6b | Motor Reset | shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |  |
| 5673678c0373 | Anti Snoring | shortAndLongPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |  |
| 28496fb1f4c5 | Zero Gravity | shortAndLongPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |  |
| 117f6978b348 | Bed Light | shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `3C` / `00` |  |
| c9c6dc2a9231 | Head Up | sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |  |
| 2169603a2ccb | Pillow Up | sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |  |
| 117fd7eb4622 | Foot Up | sustainPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `26` / `00` |  |
| 4d7ee9a33ecb | Head Down | sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |  |
| 3261d5acee66 | Pillow Down | sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |  |
| 9f41c906558f | Foot Down | sustainPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `27` / `00` |  |
| 6c281b509549 | T V Position | shortAndLongPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |  |
| 066921cd681d | Massage Head Instensity Strengthen | shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `4C` / `00` |  |
| 8f4abf075ee0 | Memory Position1 | shortAndLongPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |  |
| fed5208309e0 | Massage Foot Instensity Strengthen | shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `4E` / `00` |  |
| 19c13c4d0fda | Massage Mode Change | shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `48` / `00` |  |
| 4bae16e7f959 | Memory Position2 | shortAndLongPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |  |
| eecf3193581a | Massage Mode All Off | shortPress | `6E 01 00 5E CD` / `6E 01 00 00 6F` | `5E` / `00` |  |
| a682aa466866 | Memory Position3 | shortAndLongPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |  |
| 7b913c93bb17 | Lounge Position | shortAndLongPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |  |
| 3ab5f8fe96f4 | Lumber Up | sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |  |
| b2fcb856104f | Lumber Down | sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |  |
| a12633f5f7e7 | Title Massage | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| e0e957b09025 | Phone Light | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` | local |
| d0daaadb8852 | Massage10 Minute Timer | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` |  |
| cc52e6494256 | Massage20 Minute Timer | shortPress | `6E 01 00 63 D2` / `6E 01 00 00 6F` | `63` / `00` |  |
| 00467dc3027e | Massage30 Minute Timer | shortPress | `6E 01 00 61 D0` / `6E 01 00 00 6F` | `61` / `00` |  |
| cd12add2435e | Lumber Up | sustainPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |  |
| 41ca19922c41 | Lumber Down | sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |  |
| baeaf2a9d637 | Head And Foot Up | sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `29` / `00` |  |
| 015704594ec9 | Head And Foot Down | sustainPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `2A` / `00` |  |
| 2e64e05f3433 | Massage Instensity Strengthen | shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `34` / `00` |  |
| 7936d8f22c8b | Massage Speed Strengthen | shortPress | `6E 01 00 36 A5` / `6E 01 00 00 6F` | `36` / `00` |  |
| f361a88972f6 | Massage Instensity Weaken | shortPress | `6E 01 00 35 A4` / `6E 01 00 00 6F` | `35` / `00` |  |
| ca0bd126e0a1 | Massage Speed Weaken | shortPress | `6E 01 00 37 A6` / `6E 01 00 00 6F` | `37` / `00` |  |
| fb4a820461aa | Massage Mode Pulse | shortPress | `6E 01 00 38 A7` / `6E 01 00 00 6F` | `38` / `00` |  |
| 8a49ddf1e409 | Massage Mode Wave | shortPress | `6E 01 00 39 A8` / `6E 01 00 00 6F` | `39` / `00` |  |
| 2cd34a3a66a4 | Massage Mode Constant | shortPress | `6E 01 00 3A A9` / `6E 01 00 00 6F` | `3A` / `00` |  |
| 834d0298c2a6 | Pillow Up | sustainPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |  |
| 0f61cb2ddc7d | Pillow Down | sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |  |
| 2f6d8987dec5 | Lounge Position | shortPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `32` / `65` |  |
| 6b7f5b7e4164 | T V Position | shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `33` / `64` |  |
| b1db771e6321 | Zero Gravity | shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `34` / `66` |  |
| db703b2419a6 | Head Up | sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `35` / `00` |  |
| 8813cb017a49 | Head And Foot Up | sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `36` / `00` |  |
| b8e3489845f5 | Foot Up | sustainPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `37` / `00` |  |
| 38d7adaf1e75 | Head Down | sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `38` / `00` |  |
| 82f8199bd9d2 | Memory Position1 | shortAndLongPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `42` / `2B` |  |
| 8b3a862df042 | Memory Position2 | shortAndLongPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `44` / `2C` |  |
| 8aa2cd105798 | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `4C` / `00` |  |
| ab1f300c0bec | Bed Light | shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `46` / `00` |  |
| e0f268656b0e | Massage Instensity Strengthen | shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `48` / `00` |  |
| 45e9ce37fd2b | Massage Mode Change | shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `4A` / `00` |  |
| ec80d8038d75 | Massage Instensity Weaken | shortPress | `6E 01 00 35 A4` / `6E 01 00 00 6F` | `4B` / `00` |  |
| 8a9f00d9b56b | Motor3 Up | sustainPress | `6E 01 00 71 E0` / `6E 01 00 00 6F` | `71` / `00` |  |
| 1c485e495380 | Music Volumu Up | shortPress | `6E 01 00 D4 43` / `6E 01 00 00 6F` | `D4` / `00` |  |
| 598c167cdd86 | Motor3 Down | sustainPress | `6E 01 00 72 E1` / `6E 01 00 00 6F` | `72` / `00` |  |
| 3af051d36602 | Music Volumu Down | shortPress | `6E 01 00 D5 44` / `6E 01 00 00 6F` | `D5` / `00` |  |
| e9ada0a12c3f | Music Blue Tooth Switch | shortPress | `6E 01 00 D8 47` / `6E 01 00 00 6F` | `D8` / `00` |  |
| 9b1697fdff0d | Music Shake Mode | shortPress | `6E 01 00 D6 45` / `6E 01 00 00 6F` | `D6` / `00` |  |
| 4deb18342f34 | Motor Reset | shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `38` / `00` |  |
| 67bd828daaae | Zero Gravity | shortAndLongPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `34` / `66` |  |
| c51a841b2c8c | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` |  |
| c5f845fc1b8c | None | shortAndLongPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| bd888e1de887 | Motor Reset | shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` | hidden |
| 142bbf0bf7fb | Motor And Massage All Off | shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |  |
| 69224cc45667 | Tile Up | sustainPress | `6E 01 00 43 B2` / `6E 01 00 00 6F` | `43` / `00` |  |
| 6993e9e0837a | Tile Down | sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |  |
| 35667705e3aa | Relieve Zero Gravity Setting | shortPress | `6E 01 00 62 D1` / `6E 01 00 00 6F` | `62` / `00` |  |
| 1d9d650e8a43 | Massage Head Instensity Weaken | shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `4D` / `00` |  |
| 25c8ea6b1577 | Massage Foot Instensity Weaken | shortPress | `6E 01 00 4F BE` / `6E 01 00 00 6F` | `4F` / `00` |  |
| 2be41ffbb790 | Head And Foot All Up | shortPress | `6E 01 00 23 92` / `6E 01 00 00 6F` | `23` / `00` |  |
| 907892216e64 | Lumber Memory Position | shortAndLongPress | `6E 01 00 91 00` / `6E 01 00 92 01` | `91` / `92` |  |
| ef00e521377c | Reading Position | shortAndLongPress | `6E 01 00 F2 61` / `6E 01 00 F3 62` | `F2` / `F3` |  |
| 6ae8f5f37ad8 | Control Box Lock | shortAndLongPress | `6E 01 00 84 F3` / `6E 01 00 84 F3` | `84` / `84` |  |
| a69312fb7952 | Head Up And Foot Down | shortPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` | toggle latch |
| b0198fb326ef | Foot Up And Head Down | shortPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` | toggle latch |
| 61a7fe7954d9 | Zero Gravity | shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |  |
| acbeb1054bf8 | Zero Gravity (long action) | shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` | force long |
| 85a65e824cea | Anti Snoring | shortPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |  |
| f4e9bbed8b0f | Anti Snoring (long action) | shortPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` | force long |
| 2cf18159af62 | Memory Position1 | shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |  |
| dcef78bc22f0 | T V Position | shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |  |
| 1aa50b6d640d | Memory Position2 | shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |  |
| c2ca32745d26 | Memory Position1 (long action) | shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` | force long |
| 83257209aa9b | T V Position (long action) | shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` | force long |
| 712ce9b7b11a | Memory Position2 (long action) | shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` | force long |
| b88f492e2cf8 | Massage Mode All Off | shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |  |
| aa28f346c0b2 | Massage Mode Wave | shortAndLongPress | `6E 01 00 48 B7` / `6E 01 00 47 B6` | `48` / `47` |  |
| 2814e11c8aa7 | Foot Up And Head Down | sustainPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |  |
| a34755c5373f | Head Up And Foot Down | sustainPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |  |
| 27175a0eb1db | Head Up And Foot Down | shortPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |  |
| 401fefccde6c | Foot Up And Head Down | shortPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |  |
| 8a1d6deba766 | Motor Reset | sustainPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |  |
| 1420f18c4e7c | Phone Light | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` | local, hidden |
| 0d7a31c38a0f | Massage15 Minute Up And Down | shortPress | `6E 01 00 76 E5` / `6E 01 00 00 6F` | `76` / `00` |  |
| 24c6281aef68 | Massage30 Minute Up And Down | shortPress | `6E 01 00 90 FF` / `6E 01 00 00 6F` | `90` / `00` |  |
| 0f18e5df2881 | Memory Position1 | shortAndLongPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` | hidden |
| ec59821b3288 | Massage1 Open Or Close | shortPress | `6E 01 00 32 A1` / `6E 01 00 00 6F` | `32` / `00` |  |
| 6851aa6370a7 | Massage Mode Off And Motor Reset | shortPress | `6E 01 00 5A C9` / `6E 01 00 00 6F` | `5A` / `00` |  |
| 0b38648cbc7d | Massage2 Open Or Close | shortPress | `6E 01 00 33 A2` / `6E 01 00 00 6F` | `33` / `00` |  |
| ead8b334e722 | Massage Instensity Third Gear | shortPress | `6E 01 00 68 D7` / `6E 01 00 00 6F` | `68` / `00` |  |
| 2da9275ccfd2 | Massage Instensity First Gear | shortPress | `6E 01 00 67 D6` / `6E 01 00 00 6F` | `67` / `00` |  |
| 77c86cd0c17a | All Motor Up | sustainPress | `6E 01 00 43 B2` / `6E 01 00 00 6F` | `43` / `00` |  |
| 6aa92787433c | All Motor Down | sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |  |
| 30dd0d403916 | Massage Mode Wave Third Mode | shortPress | `6E 01 00 4B BA` / `6E 01 00 00 6F` | `4B` / `00` |  |
| a4c14d2529e4 | Massage Mode All On | shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |  |
| 0ff117b1a0e4 | Clock | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` | local |
| 06285d76f7d6 | Lumber Up | sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `42` / `00` |  |
| 835533d816a5 | Lounge Position | shortAndLongPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `32` / `65` |  |
| df4710a090bc | Pillow Up | sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |  |
| 69f676b601cc | Lumber Down | sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `43` / `00` |  |
| 5cce9d518876 | Pillow Down | sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `45` / `00` |  |
| a9df34716acf | Bed Light | shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `36` / `00` |  |
| 5edcf65572e0 | Massage Head Instensity Strengthen | shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `46` / `00` |  |
| f11b9f7d9d63 | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `47` / `00` |  |
| 8d5cd2611afe | Massage Foot Instensity Strengthen | shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `48` / `00` |  |
| 9bb165a7dcda | Massage Head Instensity Weaken | shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `49` / `00` |  |
| 33c66736687c | Massage Foot Instensity Weaken | shortPress | `6E 01 00 4F BE` / `6E 01 00 00 6F` | `4B` / `00` |  |
| 4678fa165b43 | Massage1 Instensity | shortPress | `6E 01 00 A4 13` / `6E 01 00 00 6F` | `A4` / `00` |  |
| 262d2a25c564 | Massage2 Instensity | shortPress | `6E 01 00 A5 14` / `6E 01 00 00 6F` | `A5` / `00` |  |
| 3dc2f2b7bb6a | None | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| 4d2b999586da | Massage10 Minute Timer | shortPress | `6E 01 00 A1 10` / `6E 01 00 00 6F` | `A1` / `00` |  |
| 0417c61e3983 | Massage20 Minute Timer | shortPress | `6E 01 00 A2 11` / `6E 01 00 00 6F` | `A2` / `00` |  |
| c9b91d8958e4 | Massage30 Minute Timer | shortPress | `6E 01 00 A3 12` / `6E 01 00 00 6F` | `A3` / `00` |  |
| bcd458bf83d9 | Memory Position4 | shortAndLongPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |  |
| bc3a73aad676 | Logo | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| 2445a0dfc2f6 | Tile Up | sustainPress | `6E 01 00 5B CA` / `6E 01 00 00 6F` | `5B` / `00` |  |
| bf729f1b5ed0 | Tile Down | sustainPress | `6E 01 00 5C CB` / `6E 01 00 00 6F` | `5C` / `00` |  |
| 8b9b6f611374 | Relax Position | shortAndLongPress | `6E 01 00 70 DF` / `6E 01 00 95 04` | `70` / `95` |  |
| d326af07ba43 | Motor Reset2 | shortPress | `6E 01 00 6C DB` / `6E 01 00 00 6F` | `6C` / `00` |  |
| 6fa232d21245 | Zero Gravity2 | shortAndLongPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |  |
| ccecea3d3e29 | Massage Mode All Off | shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `48` / `00` |  |
| 765d0a06908d | Yoga Position | shortAndLongPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |  |
| 3641af85cedc | Help Get Up | shortPress | `6E 01 00 3D AC` / `6E 01 00 00 6F` | `3D` / `00` |  |
| b867d983cdde | Head And Foot Up | sustainPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` |  |
| 362b90931207 | Head And Foot Down | sustainPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` |  |
| 747268a767c1 | Sync On | shortPress | `6E 01 00 BC 2B` / `6E 01 00 BC 2B` | `BC` / `BC` |  |
| aae5ac3a0d37 | Sync Off | shortPress | `6E 01 00 BD 2C` / `6E 01 00 BD 2C` | `BD` / `BD` |  |
| 9d89827e6527 | Massage Mode All Off | shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |  |
| 0430aa1692b3 | Adjust Volume | shortPress | `6E 01 00 B7 26` / `6E 01 00 00 6F` | `B7` / `00` |  |
| 32f839e744fc | Music Cut | shortPress | `6E 01 00 B8 27` / `6E 01 00 00 6F` | `B8` / `00` |  |
| 01681d7f89d6 | Music Close | shortPress | `6E 01 00 B9 28` / `6E 01 00 00 6F` | `B9` / `00` |  |
| 6242308520dd | Title Fan | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| b47a34f44021 | Title Timer | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| cac4b66cd7a7 | Massage Mode Change | shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |  |
| ea2823e1712c | Head Up And Foot Stop | shortPress | `6E 01 00 3D AC` / `6E 01 00 00 6F` | `3D` / `00` |  |
| 99105a76fa86 | Side Sleep Position | shortAndLongPress | `6E 01 00 BA 29` / `6E 01 00 BB 2A` | `BA` / `BB` |  |
| bc6785c7a5e2 | Yoga Position | shortAndLongPress | `6E 01 00 F0 5F` / `6E 01 00 F1 60` | `F0` / `F1` |  |
| 83ab13a2cb63 | Control Box Lock | shortPress | `6E 01 00 84 F3` / `6E 01 00 84 F3` | `84` / `84` |  |
| ee9d85e8f679 | Sync On | shortAndLongPress | `6E 01 00 BC 2B` / `6E 01 00 BC 2B` | `BC` / `BC` |  |
| 8c5b0f15c431 | Sync Off | shortAndLongPress | `6E 01 00 BD 2C` / `6E 01 00 BD 2C` | `BD` / `BD` |  |
| 7db56e9a5841 | Memory Position1 | sustainPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |  |
| 5cd238832057 | Memory Position2 | sustainPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |  |
| 8f030943aeb4 | Memory Position3 | sustainPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |  |
| a08b869dac7f | Memory Position4 | sustainPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |  |
| 7630ce144577 | Memory | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` | toggle latch |
| 1a3d61c98ecd | Massage15 Minute Spine Guard | shortPress | `6E 01 00 76 E5` / `6E 01 00 00 6F` | `76` / `00` |  |
| 0ed419290436 | Motor4 Up | sustainPress | `6E 01 00 73 E2` / `6E 01 00 00 6F` | `73` / `00` |  |
| 7d7711b87a5b | Motor4 Down | sustainPress | `6E 01 00 74 E3` / `6E 01 00 00 6F` | `74` / `00` |  |
| 96c416888e37 | Head And Foot Down | shortPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `2A` / `00` |  |
| e6916fcf70cf | Relieve Snore Setting | shortPress | `6E 01 00 CB 3A` / `6E 01 00 00 6F` | `CB` / `00` |  |
| df262cafa7c3 | Motor5 Up | sustainPress | `6E 01 00 D0 3F` / `6E 01 00 00 6F` | `D0` / `00` |  |
| bbd8006f52ed | Motor5 Down | sustainPress | `6E 01 00 D1 40` / `6E 01 00 00 6F` | `D1` / `00` |  |
| f74a6c435973 | Music Previous Song | shortPress | `6E 01 00 D2 41` / `6E 01 00 00 6F` | `D2` / `00` |  |
| 93cf8e749e1a | Music Next Song | shortPress | `6E 01 00 D3 42` / `6E 01 00 00 6F` | `D3` / `00` |  |
| 6b7e45adcd7e | Music Pause Play | shortPress | `6E 01 00 D7 46` / `6E 01 00 00 6F` | `D7` / `00` |  |
| 358f52a6aa0d | Massage Mode All Off | shortPress | `6E 01 00 61 D0` / `6E 01 00 00 6F` | `61` / `00` |  |
| e8fe7d3e6212 | Deep Sleep Position | shortAndLongPress | `6E 01 00 F6 65` / `6E 01 00 F7 66` | `F6` / `F7` |  |
| 48c2bc0ceadb | Control Box Lock | shortAndLongPress | `6E 01 00 D9 48` / `6E 01 00 84 F3` | `D9` / `84` |  |
| e68e9e2f64d9 | Reading Position | shortAndLongPress | `6E 01 00 F3 62` / `6E 01 00 F2 61` | `F3` / `F2` |  |
| 1d5e03f74fc5 | Deep Sleep Position | shortAndLongPress | `6E 01 00 F7 66` / `6E 01 00 F6 65` | `F7` / `F6` |  |
| 88f0e2ac71b6 | Massage Mode All Off | shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `34` / `00` |  |
| c6bace77098c | Music Switch Sound Track | shortPress | `6E 01 00 C4 33` / `6E 01 00 00 6F` | `C4` / `00` |  |
| 650eafce0eaa | Memory Position5 | shortAndLongPress | `6E 01 00 F4 63` / `6E 01 00 F5 64` | `F4` / `F5` |  |
| 3df9197ac546 | Massage Mode Change | shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `48` / `00` | hidden |
| 4674d65a3f82 | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` | hidden |
| 60490ae8efdc | Bed Light | shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `3C` / `00` | hidden |
| cf3cb69d4b7f | Relieve Zero Gravity Setting | sustainPress | `6E 01 00 BE 2D` / `6E 01 00 00 6F` | `BE` / `00` |  |
| 93cf506de9b3 | Massage Switch | shortPress | `6E 01 00 6F DE` / `6E 01 00 00 6F` | `6F` / `00` |  |
| deb504870d56 | Memory Position1 | shortPress | `6E 01 00 2B 9A` / `6E 01 00 2B 9A` | `2B` / `2B` |  |
| 02ba78481b03 | Lumber Down | shortPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |  |
| ba1f116c4be9 | Bed Light Close | shortPress | `6E 01 00 75 E4` / `6E 01 00 00 6F` | `75` / `00` |  |
| 096137e27d72 | Help Sleep Mode1 | shortAndLongPress | `6E 01 00 86 F5` / `6E 01 00 00 6F` | `86` / `00` |  |
| 9ac4ed2f3878 | Massage Mode All Off | shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` | hidden |
| cb68d0c1f3d0 | Massage Switch | shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |  |
| 943b0a6f4768 | Massage30 Minute Timer | shortPress | `6E 01 00 90 FF` / `6E 01 00 00 6F` | `90` / `00` |  |
| e2c34d5c7ade | Massage Mode Wave First Mode | shortPress | `6E 01 00 49 B8` / `6E 01 00 00 6F` | `49` / `00` |  |
| 880df9c72093 | Massage Mode Wave Second Mode | shortPress | `6E 01 00 4A B9` / `6E 01 00 00 6F` | `4A` / `00` |  |
| 5f94b5202960 | Memory Position3 | shortPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |  |
| c152a974ea6c | Memory Position4 | shortPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |  |
| 269880b9371b | T V Position | sustainPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |  |
| 0cbc9c0946d9 | Zero Gravity | sustainPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |  |
| 7f3a7ce922ef | Anti Snoring | sustainPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |  |
| cea3e21b77bb | Motor Reset | sustainPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` | hidden |
| c281d87c6bc6 | Head Up | sustainPress | `6E 01 00 23 92` / `6E 01 00 00 6F` | `23` / `00` |  |
| cca2946b7656 | Head Down | shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |  |
| 40ada9347fc6 | Wake Up | shortAndLongPress | `6E 01 00 85 F4` / `6E 01 00 00 6F` | `85` / `00` |  |
| dcbbe7e29dbc | Head Up And Foot Stop | shortPress | `6E 01 00 30 9F` / `6E 01 00 00 6F` | `30` / `00` |  |
| 714e57c2a018 | Memory Position1 | shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `42` / `2B` |  |
| ef3a6fa0cab9 | Memory Position1 | shortPress | `6E 01 00 2B 9A` / `6E 01 00 2B 9A` | `43` / `2B` |  |
| 2201ae4481dc | Memory Position2 | shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `44` / `2C` |  |
| 64a00c529c7e | Memory Position2 | shortPress | `6E 01 00 2C 9B` / `6E 01 00 2C 9B` | `45` / `2C` |  |
| 89900b928a9a | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `49` / `00` |  |
| 855711f7ad92 | Title Massage Russian | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| d213cf6b3d93 | Memory Position1 | shortPress | `6E 01 00 45 B4` / `6E 01 00 2B 9A` | `35` / `2B` |  |
| ded03dbb3f14 | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `39` / `00` |  |
| 1f5c6a24ed34 | Massage Head Instensity Strengthen | shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `42` / `00` |  |
| ebdbb493dcf8 | Bed Light | shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `43` / `00` |  |
| 27fbe32d1207 | Massage Foot Instensity Strengthen | shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `44` / `00` |  |
| d9b3d5dfffab | Massage Mode Wave | shortPress | `6E 01 00 39 A8` / `6E 01 00 00 6F` | `45` / `00` |  |
| 14755149209f | Massage Mode Pulse | shortPress | `6E 01 00 38 A7` / `6E 01 00 00 6F` | `46` / `00` |  |
| de25830c8d4b | Massage Mode Constant | shortPress | `6E 01 00 3A A9` / `6E 01 00 00 6F` | `47` / `00` |  |
| c0dda09c7c32 | Massage Speed Strengthen | shortPress | `6E 01 00 36 A5` / `6E 01 00 00 6F` | `48` / `00` |  |
| 33c20fd70f57 | Massage Speed Weaken | shortPress | `6E 01 00 37 A6` / `6E 01 00 00 6F` | `49` / `00` |  |
| 3a435638569b | Massage Instensity Strengthen | shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `4A` / `00` |  |
| 976dbfd3d1e0 | Voice | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` | local |
| a3494ef11b0f | Head Down | shortAndLongPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |  |
| d3480f51746b | Head Up | shortAndLongPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |  |
| 40c1cd7355f7 | Head Up | shortPress | `6E 01 00 3D AC` / `6E 01 00 00 6F` | `3D` / `00` |  |
| 7b8ececd7224 | Head Down | shortPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |  |
| 63144be9c453 | Foot Up | shortPress | `6E 01 00 3E AD` / `6E 01 00 00 6F` | `3E` / `00` |  |
| fd7cabcb5995 | Foot Down | shortPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |  |
| 0e6d9419b849 | Lounge Position | sustainPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |  |
| 2f1420c5a271 | None | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` |  |
| be9bf9076ad2 | Massage Head Instensity Strengthen | shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `49` / `00` |  |
| f8e672eec1db | Massage Head Instensity Weaken | shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `4A` / `00` |  |
| 5530d0fca78d | Massage Mode All Off | shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `50` / `00` |  |
| aaa2bcc5127b | Massage Instensity First Gear | shortPress | `6E 01 00 67 D6` / `6E 01 00 00 6F` | `4C` / `00` |  |
| b993d8df46b2 | Massage Instensity Second Gear | shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `4D` / `00` |  |
| 9cbb678a9d22 | Massage Instensity Third Gear | shortPress | `6E 01 00 68 D7` / `6E 01 00 00 6F` | `4E` / `00` |  |
| bc0701329d6d | Foot Up | shortPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `26` / `00` |  |
| 5f8ce0c4c2dd | Motor Reset | shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `32` / `00` |  |
| 3a6416ee9d41 | Aromatherapy | shortAndLongPress | `6E 01 00 3B AA` / `6E 01 00 00 6F` | `3B` / `00` |  |
| c60949e83877 | Memory Position2 | shortPress | `6E 01 00 2C 9B` / `6E 01 00 2C 9B` | `2C` / `2C` |  |
| 60e96affa5ae | Memory Position3 | shortPress | `6E 01 00 2D 9C` / `6E 01 00 2D 9C` | `2D` / `2D` |  |
| 416a4029b7a8 | Motor Reset | shortPress | `6E 01 00 30 9F` / `6E 01 00 00 6F` | `30` / `00` |  |
| 798be2af9a94 | Massage Switch | shortAndLongPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `4C` / `00` |  |
| 2ae78fe2056f | Title Massage Japan | shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| 6f8f9641288c | Mlily Menu | sustainPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` | local |
| d7ec05d2d681 | Head And Foot Up | sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `29` / `00` | hidden |
| b73241ec2198 | Un Wind Position | shortAndLongPress | `6E 01 00 8C FB` / `6E 01 00 8D FC` | `8C` / `8D` |  |
| bf7378a0d6b3 | Wake Up Position | shortAndLongPress | `6E 01 00 93 02` / `6E 01 00 94 03` | `93` / `94` |  |
| a69ac0b746b0 | Sleep Position | shortAndLongPress | `6E 01 00 8E FD` / `6E 01 00 8F FE` | `8E` / `8F` |  |
| 3f4b74a17f67 | Massage Mode Change | shortPress | `6E 01 00 39 A8` / `6E 01 00 00 6F` | `39` / `00` |  |
| ae1f78b6afb3 | Head And Foot Up | sustainPress | `6E 01 00 96 05` / `6E 01 00 00 6F` | `96` / `00` |  |
| 40f883b6ac2b | Head And Foot Down | sustainPress | `6E 01 00 97 06` / `6E 01 00 00 6F` | `97` / `00` |  |
| a966d07dc322 | Massage Mode All Off | sustainPress | `6E 01 00 5E CD` / `6E 01 00 00 6F` | `5E` / `00` |  |
| f7b6f0f21335 | Massage Mode All Off | shortPress | `6E 01 00 5E CD` / `6E 01 00 00 6F` | `5E` / `00` | hidden |
| 9883c4c11c1b | Massage Lumbar Instensity Strengthen | shortPress | `6E 01 00 E0 4F` / `6E 01 00 00 6F` | `E0` / `00` |  |
| adbc6ec7023d | Coaxing Sleep Mode | shortPress | `6E 01 00 86 F5` / `6E 01 00 89 F8` | `86` / `89` |  |
| 290d9910a4d6 | Head Up | shortPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |  |
| 1719150dc50c | Head Down | shortPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |  |
| 8220cfc68b4c | Foot Down | shortPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `27` / `00` |  |
| c4aa46ccfc61 | Pillow Up | shortPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |  |
| fcdb3da2d700 | Pillow Down | shortPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |  |
| 002aebdb0a22 | All Motor Up | shortPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` |  |
| a38b6b922f03 | All Motor Down | shortPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` |  |
| c08507546144 | Coaxing Sleep Mode2 | shortPress | `6E 01 00 87 F6` / `6E 01 00 00 6F` | `87` / `00` |  |
| c2b08d0842de | Coaxing Sleep Mode3 | shortPress | `6E 01 00 88 F7` / `6E 01 00 00 6F` | `88` / `00` |  |
| 216754480545 | Help Get Up Position | shortAndLongPress | `6E 01 00 3D AC` / `6E 01 00 F8 67` | `3D` / `F8` |  |
| 90483ec7049a | Yoga Position | shortPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |  |
| 1791ad47505a | Forword | sustainPress | `6E 01 00 5B CA` / `6E 01 00 00 6F` | `5B` / `00` |  |
| 26dec4df5a23 | Backward | sustainPress | `6E 01 00 5C CB` / `6E 01 00 00 6F` | `5C` / `00` |  |
| 8f924ee61014 | Swing Help Sleep | sustainPress | `6E 01 00 76 E5` / `6E 01 00 00 6F` | `76` / `00` |  |
| fa348b746fa6 | Head Down | sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |  |
| 9ed1afa85901 | Head Up | sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |  |
| fc6b2ae62c27 | Zero Gravity Motor Down | sustainPress | `6E 01 00 72 E1` / `6E 01 00 00 6F` | `72` / `00` |  |
| f58be5dcd1fe | Zero Gravity Motor Up | sustainPress | `6E 01 00 71 E0` / `6E 01 00 00 6F` | `71` / `00` |  |
| 0e0ea393ef1e | Pillow Down | sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |  |
| 10511feca46c | Pillow Up | sustainPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |  |
| e73cc3cccaca | Lumbar Down | sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |  |
| 1e7a055c5cb4 | Lumbar Up | sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |  |
| b3d7c4c9f76b | Sit Position | sustainPress | `6E 01 00 E5 54` / `6E 01 00 00 6F` | `E5` / `00` |  |
| 5d879bb26b68 | All Motor Up | sustainPress | `6E 01 00 5B CA` / `6E 01 00 00 6F` | `5B` / `00` |  |
| b7f6aa4c400e | None | sustainPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |  |
| 42bfa59734d3 | All Motor Down | sustainPress | `6E 01 00 5C CB` / `6E 01 00 00 6F` | `5C` / `00` |  |
| e77a18d88f25 | Head And Foot Up | shortPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `29` / `00` |  |
| 18368dd0106a | Motor Reset | shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |  |
| 2baeb8064f93 | Sync On | longPress | `6E 01 00 BC 2B` / `6E 01 00 BC 2B` | `BC` / `BC` |  |
| 4acd433d5358 | Sync Off | longPress | `6E 01 00 BD 2C` / `6E 01 00 BD 2C` | `BD` / `BD` |  |
| d83949b70674 | All Motor Up | sustainPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` | hidden |
| d9be9bdbf73f | All Motor Down | sustainPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` | hidden |
| 96fa600efc5a | Lounge Position | shortPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |  |
| d1b4075edc9c | Reading Position | shortPress | `6E 01 00 F2 61` / `6E 01 00 F3 62` | `F2` / `F3` |  |
| 002dd35e5d0a | Zero Gravity2 | shortPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |  |
| dbad80951ce1 | Deep Sleep Position | shortPress | `6E 01 00 F6 65` / `6E 01 00 F7 66` | `F6` / `F7` |  |
| 54c13a02b356 | T V Position | shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |  |
| 905d025dc026 | Zero Gravity | shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |  |
| e9c2c0671d97 | Zero Gravity2 | shortPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |  |
| 06098b3bf431 | Anti Snoring | shortPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |  |
| 327d71fae3ff | Lounge Position | shortPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |  |
| 4f5e1c0d1218 | Memory Position1 | shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |  |
| 3228164a54b8 | Memory Position2 | shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |  |
| 2210609e88f8 | Wake Up | shortPress | `6E 01 00 85 F4` / `6E 01 00 00 6F` | `85` / `00` |  |
| cc8810821e84 | Memory Position3 | shortPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |  |
| 1693947c0792 | Memory Position5 | shortPress | `6E 01 00 F4 63` / `6E 01 00 F5 64` | `F4` / `F5` |  |
| d29e676e4bc9 | Massage Head Instensity Strengthen | shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `4C` / `00` |  |
| 2b03e7d24309 | Massage Foot Instensity Strengthen | shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `4E` / `00` |  |
| 2256dbe95090 | Massage Mode All On | shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |  |
| 825d5590da69 | Alarm Mode1 | shortPress | `6E 01 00 B0 1F` / `6E 01 00 00 6F` | `B0` / `00` |  |
| 559de78abf9b | Alarm Mode2 | shortPress | `6E 01 00 B1 20` / `6E 01 00 00 6F` | `B1` / `00` |  |
| b49407ca4efb | Reading Position | shortPress | `6E 01 00 F2 61` / `6E 01 00 F3 62` | `F2` / `F3` |  |
| 176c6f31715f | Alarm Mode1 | shortPress | `6E 01 00 F5 64` / `6E 01 00 00 6F` | `F5` / `00` |  |
| c47e1167bb98 | All Motor Up | shortPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` |  |
| 12629335d2cb | All Motor Down | shortPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` |  |
| 6cf2073c55b5 | Memory Position4 | shortPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |  |
<!-- /generated -->

<details>
<summary>Complete product, remote, menu and schedule table</summary>

<!-- generated:mlily-catalog -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Product / explicit remote route | Control IDs in app order | Alarm mode IDs | Sides | Light menu getter | Repeat | BLE sleep | Massage timer |
|---|---|---|---|---|---|---|---|
| 6brm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4fbb0fc77db8, 9ea62e37e453 |  | 0 | True | False | False | False |
| 6crm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4fbb0fc77db8, 40c92af58e6b |  | 0 | True | False | False | False |
| 6drm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4fbb0fc77db8, 40c92af58e6b, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| 6erm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 117f6978b348, 40c92af58e6b, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| 6frm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 117f6978b348, 40c92af58e6b |  | 0 | True | False | False | False |
| a0rm | c9c6dc2a9231, 2169603a2ccb, 117fd7eb4622, 4d7ee9a33ecb, 3261d5acee66, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, 4bae16e7f959, eecf3193581a, a682aa466866 |  | 0 | True | False | False | False |
| a0rn | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| a1rm | c9c6dc2a9231, 2169603a2ccb, 117fd7eb4622, 4d7ee9a33ecb, 3261d5acee66, 9f41c906558f, 28496fb1f4c5, 8f4abf075ee0, cd12add2435e, 4bae16e7f959, 066921cd681d, 41ca19922c41, fed5208309e0, 19c13c4d0fda, 40c92af58e6b, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| a2rm | 8f4abf075ee0, 4bae16e7f959, a682aa466866, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, a12633f5f7e7, 2e64e05f3433, 066921cd681d, 7936d8f22c8b, f361a88972f6, fed5208309e0, ca0bd126e0a1, fb4a820461aa, 8a49ddf1e409, 2cd34a3a66a4 |  | 0 | True | False | False | False |
| a2rn | 5673678c0373, 28496fb1f4c5, 117f6978b348, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| a3rm | 2f6d8987dec5, 6b7f5b7e4164, b1db771e6321, db703b2419a6, 8813cb017a49, b8e3489845f5, 38d7adaf1e75, 9ea62e37e453, 334e68909524, 82f8199bd9d2, 8b3a862df042, 40c92af58e6b, a12633f5f7e7, 8aa2cd105798, ab1f300c0bec, e0f268656b0e, 45e9ce37fd2b, e0e957b09025, ec80d8038d75, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| a3rn | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f |  | 0 | True | False | False | False |
| a4rn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 6c281b509549, e0e957b09025, 28496fb1f4c5, 4bae16e7f959, 5673678c0373, 117f6978b348 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 1aa50b6d640d | 0 | True | False | False | False |
| a5rn | 3ab5f8fe96f4, 8a9f00d9b56b, 1c485e495380, b2fcb856104f, 598c167cdd86, 3af051d36602, 117f6978b348, e9ada0a12c3f, 9b1697fdff0d, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, e0e957b09025, 40c92af58e6b, 8f4abf075ee0, 5673678c0373, eecf3193581a, 28496fb1f4c5, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| a6rm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4deb18342f34, 67bd828daaae |  | 0 | True | False | False | False |
| a6rn | 5673678c0373, 28496fb1f4c5, 117f6978b348, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| a7rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, e0e957b09025 |  | 0 | True | False | False | False |
| a8rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 117f6978b348, 9f41c906558f, 28496fb1f4c5, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| a9rm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, c51a841b2c8c, 4bae16e7f959, 19c13c4d0fda, 117f6978b348 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| a9rn | 6c281b509549, 7b913c93bb17, 8f4abf075ee0, c5f845fc1b8c, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, 142bbf0bf7fb, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| aarm | c9c6dc2a9231, 69224cc45667, 117fd7eb4622, 4d7ee9a33ecb, 6993e9e0837a, 9f41c906558f, 40c92af58e6b, 3ab5f8fe96f4, 834d0298c2a6, b2fcb856104f, 066921cd681d, 0f61cb2ddc7d, 19c13c4d0fda, fed5208309e0, 117f6978b348, eecf3193581a |  | 0 | True | False | False | False |
| aarn | c9c6dc2a9231, 4d7ee9a33ecb, 40c92af58e6b, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| abrm | 28496fb1f4c5, 8f4abf075ee0, 2169603a2ccb, 3261d5acee66, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 117f6978b348, 35667705e3aa | 2cf18159af62 | 0 | True | False | False | False |
| abrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 3ab5f8fe96f4, 19c13c4d0fda, eecf3193581a, b2fcb856104f, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| acrm | 28496fb1f4c5, 2169603a2ccb, 5673678c0373, 6c281b509549, 3261d5acee66, 7b913c93bb17, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 35667705e3aa, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, 1d9d650e8a43, 117f6978b348, 25c8ea6b1577 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| acrn | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4deb18342f34, 67bd828daaae |  | 0, 1 | True | False | False | False |
| adrm | 28496fb1f4c5, 2169603a2ccb, 5673678c0373, 6c281b509549, 3261d5acee66, 7b913c93bb17, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 35667705e3aa, 9f41c906558f, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, 1d9d650e8a43, 117f6978b348, 25c8ea6b1577, 8f4abf075ee0, 4bae16e7f959, a682aa466866 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| aerm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 2be41ffbb790, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 2169603a2ccb, 907892216e64, 3261d5acee66, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea | 0 | True | False | False | False |
| afrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 2be41ffbb790, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| agrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 2be41ffbb790, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 2169603a2ccb, eecf3193581a, 3261d5acee66 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| ahrm | c9c6dc2a9231, 6c281b509549, 3ab5f8fe96f4, 4d7ee9a33ecb, 5673678c0373, b2fcb856104f, 28496fb1f4c5, 066921cd681d, 19c13c4d0fda, fed5208309e0, 117fd7eb4622, eecf3193581a, 834d0298c2a6, 9f41c906558f, 40c92af58e6b, 0f61cb2ddc7d, 117f6978b348 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| airm | 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 5673678c0373, 2169603a2ccb, 8f4abf075ee0, 117f6978b348, 3261d5acee66, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, fed5208309e0 | 066921cd681d | 0 | True | False | False | False |
| airn | 28496fb1f4c5, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 40c92af58e6b, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, 117f6978b348, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ajrm | 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, fed5208309e0 | 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| ajrn | 7b913c93bb17, ef00e521377c, c9c6dc2a9231, 4d7ee9a33ecb, baeaf2a9d637, 6c281b509549, 015704594ec9, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 5673678c0373, 40c92af58e6b | dcef78bc22f0, d1b4075edc9c, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a | 0 | True | False | False | False |
| akrm | 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 5673678c0373 |  | 0 | True | False | False | False |
| alrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 2be41ffbb790, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 2169603a2ccb, 907892216e64, 3261d5acee66, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea | 0 | True | False | False | False |
| amrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 2be41ffbb790, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| anrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 2be41ffbb790, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 2169603a2ccb, eecf3193581a, 3261d5acee66 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| aorm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 7b913c93bb17, 40c92af58e6b, 6ae8f5f37ad8 |  | 0 | True | False | False | False |
| aprm | a69312fb7952, 2be41ffbb790, b0198fb326ef, 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 61a7fe7954d9, acbeb1054bf8, 117fd7eb4622, 4d7ee9a33ecb, 85a65e824cea, f4e9bbed8b0f, 9f41c906558f, 2cf18159af62, dcef78bc22f0, 1aa50b6d640d, c2ca32745d26, 83257209aa9b, 712ce9b7b11a, 066921cd681d, b88f492e2cf8, aa28f346c0b2, fed5208309e0, 1d9d650e8a43, d0daaadb8852, cc52e6494256, 25c8ea6b1577 |  | 0 | True | False | False | False |
| aprn | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 2814e11c8aa7, e0e957b09025, a34755c5373f |  | 0 | True | False | False | False |
| aqrm | 2be41ffbb790, 27175a0eb1db, 401fefccde6c, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 2cf18159af62, 1aa50b6d640d, c2ca32745d26, 712ce9b7b11a, e0e957b09025, 8a1d6deba766, 117f6978b348 |  | 0 | True | False | False | False |
| aqrn | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 1420f18c4e7c, baeaf2a9d637, 015704594ec9, 40c92af58e6b, 5673678c0373, 8f4abf075ee0, 35667705e3aa, 4bae16e7f959 |  | 0 | True | False | False | False |
| arrm | e0e957b09025, 117f6978b348, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| asrm | c9c6dc2a9231, 4d7ee9a33ecb |  | 0 | True | False | False | False |
| asrn | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, 5673678c0373, 4d7ee9a33ecb, 40c92af58e6b, 117fd7eb4622, e0e957b09025, 9f41c906558f |  | 0 | True | False | False | False |
| atrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| aurm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, a12633f5f7e7, 066921cd681d, 0d7a31c38a0f, fed5208309e0, c51a841b2c8c, 24c6281aef68, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| aurn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 28496fb1f4c5, 7b913c93bb17, 6c281b509549, 5673678c0373 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62 | 0 | True | False | False | False |
| avrm | c9c6dc2a9231, 4d7ee9a33ecb, 0f18e5df2881, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, e0e957b09025, 015704594ec9 |  | 0 | True | False | False | False |
| awrm | d0daaadb8852, cc52e6494256, 00467dc3027e, eecf3193581a, 117f6978b348, 19c13c4d0fda, 066921cd681d, 8f4abf075ee0, fed5208309e0, c9c6dc2a9231, 40c92af58e6b, 4d7ee9a33ecb, baeaf2a9d637, 4bae16e7f959, 015704594ec9, 117fd7eb4622, e0e957b09025, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| axrm | d0daaadb8852, cc52e6494256, 00467dc3027e, eecf3193581a, 117f6978b348, 19c13c4d0fda, 066921cd681d, 8f4abf075ee0, fed5208309e0, c9c6dc2a9231, 40c92af58e6b, 4d7ee9a33ecb, 2169603a2ccb, 4bae16e7f959, 3261d5acee66, 117fd7eb4622, e0e957b09025, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| axrn | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 3ab5f8fe96f4, 40c92af58e6b, b2fcb856104f |  | 0 | True | False | False | False |
| ayrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| ayrn | 117fd7eb4622, 6c281b509549, 9f41c906558f, c9c6dc2a9231, 8f4abf075ee0, 3ab5f8fe96f4, 4d7ee9a33ecb, 4bae16e7f959, b2fcb856104f, 40c92af58e6b, 117f6978b348, e0e957b09025 | dcef78bc22f0 | 0 | True | False | False | False |
| azrm | e0e957b09025, 8f4abf075ee0, c9c6dc2a9231, 4d7ee9a33ecb, 40c92af58e6b, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| azrn | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f |  | 0 | True | False | False | False |
| b0rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, e0e957b09025 |  | 0 | True | False | False | False |
| b1rm | ec59821b3288, 6851aa6370a7, 0b38648cbc7d, c9c6dc2a9231, ead8b334e722, 117fd7eb4622, 4d7ee9a33ecb, 2da9275ccfd2, 9f41c906558f, 40c92af58e6b, 117f6978b348, e0e957b09025 |  | 0 | True | False | False | False |
| b2rm | c9c6dc2a9231, 4d7ee9a33ecb |  | 0 | True | False | False | False |
| b2rn | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| b3rm | c9c6dc2a9231, 4d7ee9a33ecb |  | 0 | True | False | False | False |
| b4rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 77c86cd0c17a, 117fd7eb4622, 4d7ee9a33ecb, 6aa92787433c, 9f41c906558f, 7b913c93bb17, 8f4abf075ee0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62 | 0 | True | False | False | False |
| b5rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 6c281b509549, 28496fb1f4c5, e0e957b09025, 40c92af58e6b | dcef78bc22f0, 61a7fe7954d9 | 0 | True | False | False | False |
| b5rn | 5673678c0373, 28496fb1f4c5, 117f6978b348, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 85a65e824cea, 61a7fe7954d9, dcef78bc22f0, 2cf18159af62 | 0 | True | False | False | False |
| b6rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| b7rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 40c92af58e6b |  | 0 | True | False | False | False |
| b7rn | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 6c281b509549, baeaf2a9d637, 015704594ec9, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| b8rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, 19c13c4d0fda, 30dd0d403916 |  | 0 | True | False | False | False |
| b8rn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| b8tt | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, fed5208309e0, 25c8ea6b1577 |  | 0 | True | False | False | False |
| b9rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 77c86cd0c17a, 6aa92787433c, 28496fb1f4c5, 40c92af58e6b | 61a7fe7954d9 | 0 | True | False | False | False |
| b9tt | 40c92af58e6b, e0e957b09025, 35667705e3aa, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, fed5208309e0, a4c14d2529e4, 25c8ea6b1577 |  | 0 | True | False | False | False |
| barm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| bbrm | 4d7ee9a33ecb, c9c6dc2a9231, 9f41c906558f, 117fd7eb4622, e0e957b09025 |  | 0 | True | False | False | False |
| bbrn | 5673678c0373, 28496fb1f4c5, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 117f6978b348, 4bae16e7f959, a682aa466866, e0e957b09025, c5f845fc1b8c |  | 0 | True | False | False | False |
| bcrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, 40c92af58e6b, 0ff117b1a0e4 | 61a7fe7954d9 | 0 | True | False | False | False |
| bdrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 7b913c93bb17, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, 40c92af58e6b, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a | 0 | True | False | False | False |
| berm | db703b2419a6, 40c92af58e6b, b8e3489845f5, 38d7adaf1e75, 6b7f5b7e4164, 334e68909524, 06285d76f7d6, 835533d816a5, df4710a090bc, 69f676b601cc, b1db771e6321, 5cce9d518876, e0e957b09025, a12633f5f7e7, a9df34716acf, 5edcf65572e0, f11b9f7d9d63, 8d5cd2611afe, 9bb165a7dcda, 45e9ce37fd2b, 33c66736687c, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| bfrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| bgrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 40c92af58e6b, 015704594ec9, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 4678fa165b43, eecf3193581a, 262d2a25c564, 19c13c4d0fda, e0e957b09025, 3dc2f2b7bb6a, 4d2b999586da, 0417c61e3983, c9b91d8958e4 |  | 0 | True | False | False | False |
| bhrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, 142bbf0bf7fb, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| birm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, 142bbf0bf7fb, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| bjrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 117f6978b348, 8f4abf075ee0, 4bae16e7f959, 6c281b509549, 28496fb1f4c5, 7b913c93bb17, 40c92af58e6b | 61a7fe7954d9 | 0 | True | False | False | False |
| bkrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 6c281b509549, 9f41c906558f, baeaf2a9d637, 7b913c93bb17, 40c92af58e6b |  | 0 | True | False | False | False |
| blrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| bmrm | 8f4abf075ee0, 4bae16e7f959, a682aa466866, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| bnrm | 6c281b509549, a682aa466866, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| borm | a34755c5373f, 2814e11c8aa7, c9c6dc2a9231, 77c86cd0c17a, 117fd7eb4622, 4d7ee9a33ecb, 6aa92787433c, 9f41c906558f, 28496fb1f4c5, 40c92af58e6b, 5673678c0373, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| bprm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| bqrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, e0e957b09025, 015704594ec9 |  | 0 | True | False | False | False |
| brrm | a69312fb7952, 2be41ffbb790, b0198fb326ef, 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 61a7fe7954d9, acbeb1054bf8, 117fd7eb4622, 4d7ee9a33ecb, 85a65e824cea, f4e9bbed8b0f, 9f41c906558f, 2cf18159af62, dcef78bc22f0, 1aa50b6d640d, c2ca32745d26, 83257209aa9b, 712ce9b7b11a | 61a7fe7954d9 | 0 | True | False | False | False |
| bsrm | c9c6dc2a9231, 4d7ee9a33ecb, 4bae16e7f959, 8f4abf075ee0, a682aa466866, bcd458bf83d9, bc3a73aad676 |  | 0 | True | False | False | False |
| btrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b |  | 0, 1, 2 | True | False | False | False |
| burm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0, 1, 2 | True | False | False | False |
| bvrm | 28496fb1f4c5, 5673678c0373, 6c281b509549, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, 40c92af58e6b, e0e957b09025, a4c14d2529e4 |  | 0, 1, 2 | True | False | False | False |
| bwrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 40c92af58e6b | 2cf18159af62 | 0, 1, 2 | True | False | False | False |
| bwrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 2445a0dfc2f6, 77c86cd0c17a, bf729f1b5ed0, 6aa92787433c, 117f6978b348, 28496fb1f4c5 | 61a7fe7954d9 | 0 | True | False | False | False |
| bxrm | c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 117f6978b348, 4bae16e7f959 |  | 0 | True | False | False | False |
| bxrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 2445a0dfc2f6, 77c86cd0c17a, bf729f1b5ed0, 6aa92787433c, e0e957b09025, 28496fb1f4c5 | 61a7fe7954d9 | 0 | True | False | False | False |
| byrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 77c86cd0c17a, 6aa92787433c, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| bzrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 8b9b6f611374, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, c51a841b2c8c, 117f6978b348, 2e64e05f3433, 19c13c4d0fda, e0e957b09025, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| c0rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, e0e957b09025, 40c92af58e6b, 117f6978b348, 35667705e3aa | 2cf18159af62 | 0 | True | False | False | False |
| c1rm | 28496fb1f4c5, 8f4abf075ee0, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| c1rn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 6c281b509549, 117f6978b348, 5673678c0373, 28496fb1f4c5 | dcef78bc22f0, 85a65e824cea, 61a7fe7954d9, 2cf18159af62 | 0 | True | False | False | False |
| c2rm | 117f6978b348, 27175a0eb1db, 2be41ffbb790, 401fefccde6c, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 834d0298c2a6, 8a9f00d9b56b, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 0f61cb2ddc7d, 598c167cdd86, 2cf18159af62, 1aa50b6d640d, dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, c2ca32745d26, 712ce9b7b11a, 83257209aa9b, acbeb1054bf8, f4e9bbed8b0f, 066921cd681d, b88f492e2cf8, 3dc2f2b7bb6a, 19c13c4d0fda, fed5208309e0, 1d9d650e8a43, d0daaadb8852, e0e957b09025, cc52e6494256, 25c8ea6b1577 |  | 0 | True | False | False | False |
| c2rn | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 5673678c0373, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| c3rm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 117f6978b348 |  | 0 | True | False | False | False |
| c4rm | 5673678c0373, 28496fb1f4c5, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| c5rm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| c6rm | c9c6dc2a9231, 3ab5f8fe96f4, 4d7ee9a33ecb, b2fcb856104f, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, bcd458bf83d9, 40c92af58e6b, d326af07ba43 |  | 0 | True | False | False | False |
| c7rm | 28496fb1f4c5, 6fa232d21245, 8f4abf075ee0, bcd458bf83d9, 40c92af58e6b, d326af07ba43, c9c6dc2a9231, 3ab5f8fe96f4, 4d7ee9a33ecb, b2fcb856104f, 117fd7eb4622, 9f41c906558f, 066921cd681d, fed5208309e0, ccecea3d3e29, 117f6978b348 |  | 0 | True | False | False | False |
| c8rm | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| c9rm | 27175a0eb1db, 2be41ffbb790, 401fefccde6c, 117f6978b348, e0e957b09025, 8a1d6deba766, c9c6dc2a9231, 61a7fe7954d9, acbeb1054bf8, 117fd7eb4622, 4d7ee9a33ecb, 85a65e824cea, f4e9bbed8b0f, 9f41c906558f, 2cf18159af62, dcef78bc22f0, 1aa50b6d640d, c2ca32745d26, 83257209aa9b, 712ce9b7b11a, 066921cd681d, fed5208309e0, 1d9d650e8a43, aa28f346c0b2, 25c8ea6b1577 |  | 0 | True | False | False | False |
| c9rn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 85a65e824cea, 61a7fe7954d9, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| carm | 2169603a2ccb, 3261d5acee66, cd12add2435e, 41ca19922c41, 8a9f00d9b56b, 598c167cdd86, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| carn | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 96fa600efc5a, 61a7fe7954d9, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| cbrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, 015704594ec9, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| cbrn | 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 96fa600efc5a, 85a65e824cea, 61a7fe7954d9, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| ccrm | 28496fb1f4c5, 6c281b509549, c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 117f6978b348, 8f4abf075ee0 |  | 0 | True | False | False | False |
| ccrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 6c281b509549, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| cdrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| cdrn | 765d0a06908d, 5673678c0373, 3641af85cedc, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 28496fb1f4c5, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| cerm | 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 4d7ee9a33ecb, baeaf2a9d637, 6c281b509549, 015704594ec9, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 5673678c0373, 40c92af58e6b | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| cfrn | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 77c86cd0c17a, 6aa92787433c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| cgrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 117fd7eb4622, 9f41c906558f, c9c6dc2a9231, 2169603a2ccb, bd888e1de887, 4d7ee9a33ecb, 3261d5acee66, fed5208309e0, 117f6978b348, 3dc2f2b7bb6a, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| chrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5 |  | 0 | True | False | False | False |
| chrn | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, 117f6978b348, 40c92af58e6b |  | 0 | True | False | False | False |
| cirm | 6c281b509549, 8f4abf075ee0, 28496fb1f4c5, a682aa466866, 7b913c93bb17, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| cjrm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 77c86cd0c17a, 834d0298c2a6, 6aa92787433c, 066921cd681d, 0f61cb2ddc7d, fed5208309e0, 19c13c4d0fda, 117f6978b348, eecf3193581a, 5673678c0373, 40c92af58e6b |  | 0 | True | False | False | False |
| ckrm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 3ab5f8fe96f4, 77c86cd0c17a, 834d0298c2a6, b2fcb856104f, 6aa92787433c, 0f61cb2ddc7d, 117f6978b348, 6c281b509549, 40c92af58e6b, 7b913c93bb17, 28496fb1f4c5 |  | 0 | True | False | False | False |
| clrm | cd12add2435e, 5673678c0373, 41ca19922c41, 2169603a2ccb, 28496fb1f4c5, 3261d5acee66, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| clrn | 765d0a06908d, 3641af85cedc, 5673678c0373, 28496fb1f4c5, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| cmrm | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, 4bae16e7f959, a682aa466866, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 5f94b5202960 | 0 | True | False | False | False |
| cmrn | baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| cnrm | e0e957b09025, 8f4abf075ee0, 77c86cd0c17a, 6aa92787433c, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| corm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, 4bae16e7f959, b88f492e2cf8, a682aa466866 |  | 0 | True | False | False | False |
| corn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| cprm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 28496fb1f4c5, 8f4abf075ee0, 834d0298c2a6, 4bae16e7f959, 066921cd681d, 0f61cb2ddc7d, fed5208309e0, 19c13c4d0fda, 40c92af58e6b, 9d89827e6527, 117f6978b348 |  | 0 | True | False | False | False |
| cprn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37 |  | 0 | True | False | False | False |
| cqrm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, 4bae16e7f959, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| crrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 28496fb1f4c5 |  | 0 | True | False | False | False |
| csrm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 066921cd681d, e0e957b09025, a682aa466866, fed5208309e0, 8f4abf075ee0, 19c13c4d0fda, eecf3193581a, 4bae16e7f959, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ctrm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 066921cd681d, e0e957b09025, b2fcb856104f, fed5208309e0, 8f4abf075ee0, 19c13c4d0fda, eecf3193581a, 4bae16e7f959, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| curm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 3ab5f8fe96f4, 19c13c4d0fda, eecf3193581a, b2fcb856104f, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| cvrm | 117f6978b348, 28496fb1f4c5, 8f4abf075ee0, c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 066921cd681d, fed5208309e0, ccecea3d3e29 |  | 0 | True | False | False | False |
| cwrm | 5673678c0373, 0430aa1692b3, 28496fb1f4c5, 3ab5f8fe96f4, 32f839e744fc, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, 01681d7f89d6, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| cxrm | 28496fb1f4c5, 5673678c0373, 6c281b509549, 4bae16e7f959, 8f4abf075ee0, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| cyrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| czrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| d0rm | c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, 3dc2f2b7bb6a, 117f6978b348, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| d1rm | c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 066921cd681d, eecf3193581a, fed5208309e0, 117f6978b348 |  | 0 | True | False | False | True |
| d2rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, 28496fb1f4c5, 6c281b509549, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda |  | 0 | True | False | False | False |
| d3rm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, 28496fb1f4c5, 5673678c0373, 117f6978b348, 40c92af58e6b, 6242308520dd, 066921cd681d, eecf3193581a, fed5208309e0, b47a34f44021, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| d4rm | 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, 28496fb1f4c5, 6c281b509549, 5673678c0373, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda |  | 0 | True | False | False | False |
| d5rm | baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| d6rm | 3ab5f8fe96f4, b2fcb856104f |  | 0 | True | False | False | False |
| d7rm | 117f6978b348, 35667705e3aa, e0e957b09025, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, fed5208309e0, 1d9d650e8a43, cac4b66cd7a7, 25c8ea6b1577 | 2cf18159af62 | 0 | True | False | False | False |
| d8rm | c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 117f6978b348, 9f41c906558f |  | 0 | True | False | False | False |
| d9rm | c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 066921cd681d, eecf3193581a, fed5208309e0, 117f6978b348 |  | 0 | True | False | False | True |
| darm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, c51a841b2c8c, 4bae16e7f959, 19c13c4d0fda, 117f6978b348 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| dbrm | 117f6978b348, 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, 4bae16e7f959, 6c281b509549, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| dcrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, eecf3193581a, 117f6978b348, 066921cd681d, 19c13c4d0fda, e0e957b09025, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ddrm | 28496fb1f4c5, 7b913c93bb17, 5673678c0373, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, 4bae16e7f959, 6c281b509549, a682aa466866 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 5f94b5202960 | 0 | True | False | False | False |
| derm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, a682aa466866, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, e0e957b09025, c51a841b2c8c, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dfrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, a682aa466866, 8f4abf075ee0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| dgrm | e0e957b09025, 5673678c0373, a682aa466866, 28496fb1f4c5, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f | 61a7fe7954d9, 85a65e824cea | 0 | True | False | False | False |
| dhrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 3dc2f2b7bb6a, a12633f5f7e7, 35667705e3aa, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| dirm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 3dc2f2b7bb6a, a12633f5f7e7, 35667705e3aa, 066921cd681d, 117f6978b348, 1d9d650e8a43, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| djrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dkrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 3ab5f8fe96f4, b2fcb856104f, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dlrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 7b913c93bb17, 6c281b509549, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dmrm | 99105a76fa86, 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| dnrm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 6c281b509549, 28496fb1f4c5, bd888e1de887, bc6785c7a5e2, 5673678c0373, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f |  | 0 | True | False | False | False |
| dprm | 99105a76fa86, 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| dqrm | 28496fb1f4c5, 5673678c0373, 6c281b509549, 4bae16e7f959, 8f4abf075ee0, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0, 1 | True | False | False | False |
| drrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 28496fb1f4c5, e0e957b09025, 40c92af58e6b |  | 0, 1, 2 | True | False | False | False |
| dsrm | 117f6978b348, 28496fb1f4c5, e0e957b09025, 8f4abf075ee0, c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 066921cd681d, 83ab13a2cb63, fed5208309e0, ccecea3d3e29 |  | 0 | True | False | False | False |
| dtrm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| durm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 6c281b509549, baeaf2a9d637, 015704594ec9, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| dvrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 7b913c93bb17, 015704594ec9, 5673678c0373, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 117f6978b348, 9f41c906558f |  | 0 | True | False | False | False |
| dwrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, 117f6978b348, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| dxrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, ee9d85e8f679, 40c92af58e6b, 8c5b0f15c431 |  | 0 | True | False | False | False |
| dyrm | a34755c5373f, 2814e11c8aa7 |  | 0 | True | False | False | False |
| dzrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| e0rm | baeaf2a9d637, 015704594ec9, e0e957b09025 |  | 0 | True | False | False | False |
| e1rm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 3ab5f8fe96f4, 40c92af58e6b, b2fcb856104f, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| e2rm | c9c6dc2a9231, 4d7ee9a33ecb, bc3a73aad676 |  | 0 | True | False | False | False |
| e3rm | 7db56e9a5841, 5cd238832057, 8f030943aeb4, a08b869dac7f, 2445a0dfc2f6, bf729f1b5ed0, c9c6dc2a9231, 7630ce144577, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, 117f6978b348, 015704594ec9, 747268a767c1, e0e957b09025, aae5ac3a0d37 |  | 0 | True | False | False | False |
| e4rm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 2445a0dfc2f6, 77c86cd0c17a, bf729f1b5ed0, 6aa92787433c, e0e957b09025, 28496fb1f4c5 |  | 0 | True | False | False | False |
| e5rm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, 1a3d61c98ecd, 015704594ec9, 4bae16e7f959, 066921cd681d, eecf3193581a, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| e6rm | 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, 8a9f00d9b56b, 598c167cdd86, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 0ed419290436, 5673678c0373, 7d7711b87a5b, 8f4abf075ee0, 28496fb1f4c5, 4bae16e7f959 |  | 0 | True | False | False | False |
| e7rm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 834d0298c2a6, b2fcb856104f, 0f61cb2ddc7d, 117f6978b348, 28496fb1f4c5 |  | 0 | True | False | False | False |
| e8rm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 4bae16e7f959, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| e9rm | 6c281b509549, 6ae8f5f37ad8, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, 9d89827e6527, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ecrm | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, e0e957b09025, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0, 1 | True | False | False | False |
| edrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, cd12add2435e, 40c92af58e6b, 41ca19922c41, c9c6dc2a9231, 2169603a2ccb, 117fd7eb4622, 4d7ee9a33ecb, 3261d5acee66, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| efrm | 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, 28496fb1f4c5, 6c281b509549, 5673678c0373, 066921cd681d, eecf3193581a, 19c13c4d0fda, 117f6978b348, fed5208309e0 |  | 0 | True | False | False | False |
| egrm | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, e0e957b09025, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| eirm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, 5673678c0373, 4bae16e7f959, a682aa466866, 28496fb1f4c5, 6c281b509549 |  | 0 | True | False | False | False |
| ejrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 4bae16e7f959 |  | 0 | True | False | False | False |
| ekrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 40c92af58e6b, 9f41c906558f |  | 0, 1, 2 | True | False | False | False |
| emrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| enrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, e0e957b09025, 96c416888e37, 8f4abf075ee0, 4bae16e7f959, a682aa466866 |  | 0 | True | False | False | False |
| eorm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| eprm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025 |  | 0, 1 | True | False | False | False |
| eqrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 1420f18c4e7c, baeaf2a9d637, 015704594ec9, 40c92af58e6b, 5673678c0373, 8f4abf075ee0, e6916fcf70cf, 4bae16e7f959 |  | 0 | True | False | False | False |
| errm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, e0e957b09025, 40c92af58e6b | 2cf18159af62 | 0 | True | False | False | False |
| esrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| etrm | 28496fb1f4c5, 6c281b509549, 5673678c0373, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| eurm | 117f6978b348, e0e957b09025, 3dc2f2b7bb6a, c9c6dc2a9231, 117fd7eb4622, df262cafa7c3, 4d7ee9a33ecb, 9f41c906558f, bbd8006f52ed, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| evrm | 5673678c0373, 3ab5f8fe96f4, 28496fb1f4c5, 6fa232d21245, b2fcb856104f, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ewrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, fed5208309e0, 7b913c93bb17, 6c281b509549, 19c13c4d0fda, eecf3193581a, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| exrm | 5673678c0373, 28496fb1f4c5, 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| eyrm | c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f |  | 0 | True | False | False | False |
| ezrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, ef00e521377c, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| f0rm | 28496fb1f4c5, 6c281b509549, 5673678c0373, 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 |  | 0 | True | False | False | False |
| f1rm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, cd12add2435e, 41ca19922c41, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| f2rm | c9c6dc2a9231, 4d7ee9a33ecb, bc3a73aad676 |  | 0 | True | False | False | False |
| f3rm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| f4rm | f74a6c435973, 93cf8e749e1a, 1c485e495380, 3af051d36602, 9b1697fdff0d, e9ada0a12c3f, 6b7e45adcd7e, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, eecf3193581a, 40c92af58e6b, 8f4abf075ee0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| f5rm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| f6rm | c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 28496fb1f4c5, 4bae16e7f959, 5673678c0373 |  | 0 | True | False | False | False |
| f7rm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, cd12add2435e, 41ca19922c41, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| f8rm | 6c281b509549, 5673678c0373, 4bae16e7f959, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f, a682aa466866, 7b913c93bb17, 28496fb1f4c5 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 1aa50b6d640d, 5f94b5202960 | 0 | True | False | False | False |
| f9rm | 117f6978b348, 8f4abf075ee0, e0e957b09025, 5673678c0373, 28496fb1f4c5, 7b913c93bb17, c9c6dc2a9231, 6c281b509549, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 3ab5f8fe96f4, 4d7ee9a33ecb, b2fcb856104f, 066921cd681d, eecf3193581a, fed5208309e0, 1d9d650e8a43, 19c13c4d0fda, 25c8ea6b1577, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| farm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| fbrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| fcrm | 28496fb1f4c5, 5673678c0373, 6c281b509549, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 117f6978b348, 9f41c906558f, 40c92af58e6b, e0e957b09025, a4c14d2529e4, 358f52a6aa0d |  | 0 | True | False | False | False |
| fdrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, fed5208309e0, 7b913c93bb17, 6c281b509549, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 002dd35e5d0a, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| ferm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, cd12add2435e, 4bae16e7f959, 41ca19922c41, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, eecf3193581a, e8fe7d3e6212, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, dbad80951ce1, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| ffrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, cd12add2435e, 7b913c93bb17, 6c281b509549, 41ca19922c41, e8fe7d3e6212, e0e957b09025 | dcef78bc22f0, 61a7fe7954d9, 002dd35e5d0a, 85a65e824cea, 96fa600efc5a, dbad80951ce1, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| fgrm | 48c2bc0ceadb, 117f6978b348, e9ada0a12c3f, 1c485e495380, 3af051d36602, 9b1697fdff0d, 6b7e45adcd7e, f74a6c435973, 93cf8e749e1a, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 28496fb1f4c5, 40c92af58e6b, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| fhrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, 2169603a2ccb, 3261d5acee66, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62 | 0 | True | False | False | False |
| firm | e68e9e2f64d9, 28496fb1f4c5, 1d5e03f74fc5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| fjrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 88f0e2ac71b6, 117f6978b348, 40c92af58e6b, 28496fb1f4c5 |  | 0 | True | False | False | False |
| fkrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| flrm | 2445a0dfc2f6, bf729f1b5ed0, 77c86cd0c17a, 6aa92787433c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| fmrm | 48c2bc0ceadb, 117f6978b348, e9ada0a12c3f, 1c485e495380, 3af051d36602, 9b1697fdff0d, 6b7e45adcd7e, f74a6c435973, 93cf8e749e1a, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 28496fb1f4c5, 5673678c0373, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| fnrm | 48c2bc0ceadb, 117f6978b348, e9ada0a12c3f, 1c485e495380, 3af051d36602, 9b1697fdff0d, 6b7e45adcd7e, f74a6c435973, 93cf8e749e1a, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 28496fb1f4c5, 5673678c0373, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, c6bace77098c | 61a7fe7954d9, 85a65e824cea, 2cf18159af62 | 0, 1 | True | False | False | False |
| fprm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| fqrm | 5673678c0373, 28496fb1f4c5, 2169603a2ccb, 3261d5acee66, cd12add2435e, 41ca19922c41, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, c51a841b2c8c, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| frrm | e68e9e2f64d9, 28496fb1f4c5, 1d5e03f74fc5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 6ae8f5f37ad8, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| fsrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 6c281b509549, 117f6978b348, 5673678c0373, 28496fb1f4c5 | dcef78bc22f0, 85a65e824cea, 61a7fe7954d9, 2cf18159af62 | 0 | True | False | False | False |
| ftrm | 5673678c0373, 28496fb1f4c5, cd12add2435e, 41ca19922c41, 2169603a2ccb, 3261d5acee66, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| furm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 5673678c0373, 40c92af58e6b, 28496fb1f4c5, 117fd7eb4622, e0e957b09025, 9f41c906558f | 61a7fe7954d9, 85a65e824cea, 2cf18159af62 | 0 | True | False | False | False |
| fvrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 8f4abf075ee0 | 2cf18159af62 | 0 | True | False | False | False |
| fxrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 5673678c0373, e0e957b09025, 28496fb1f4c5, 6c281b509549 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea | 0 | True | False | False | False |
| fyrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 6c281b509549, 5673678c0373, 28496fb1f4c5 | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea | 0 | True | False | False | False |
| fzrm | 117f6978b348, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 8f4abf075ee0, e0e957b09025, b2fcb856104f, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| g2rm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 117f6978b348, 5673678c0373, 28496fb1f4c5 | 61a7fe7954d9, 85a65e824cea | 0 | True | False | False | False |
| g3rm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| g4rm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 |  | 0, 1 | True | False | False | False |
| g5rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, bc6785c7a5e2, fed5208309e0, 19c13c4d0fda, 650eafce0eaa, eecf3193581a, 5673678c0373 |  | 0 | True | False | False | False |
| g6rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 6c281b509549, 40c92af58e6b, 7b913c93bb17, 28496fb1f4c5, bc6785c7a5e2, 5673678c0373, 650eafce0eaa |  | 0 | True | False | False | False |
| g7rm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, e9ada0a12c3f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| g8rm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f |  | 0 | True | False | False | False |
| g9rm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62 | 0 | True | False | False | False |
| garm | 3ab5f8fe96f4, 8a9f00d9b56b, 1c485e495380, b2fcb856104f, 598c167cdd86, 3af051d36602, 117f6978b348, e9ada0a12c3f, 9b1697fdff0d, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 834d0298c2a6, 0f61cb2ddc7d, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| gbrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 77c86cd0c17a, e0e957b09025, 6aa92787433c, 117f6978b348, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| gcrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| gdrm | 48c2bc0ceadb, e0e957b09025, e9ada0a12c3f, 1c485e495380, 3af051d36602, 9b1697fdff0d, 6b7e45adcd7e, f74a6c435973, 93cf8e749e1a, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 28496fb1f4c5, 5673678c0373, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| germ | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 5673678c0373, 015704594ec9, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 4674d65a3f82, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| gfrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, 3ab5f8fe96f4, 28496fb1f4c5, 5673678c0373, b2fcb856104f, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 4674d65a3f82, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ggrm | 28496fb1f4c5, e0e957b09025, 5673678c0373, 2169603a2ccb, cd12add2435e, 8f4abf075ee0, 3261d5acee66, 41ca19922c41, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 4674d65a3f82, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ghrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0, 1 | True | False | False | False |
| gjrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| gkrm | cd12add2435e, 2169603a2ccb, 1c485e495380, 41ca19922c41, 3261d5acee66, 3af051d36602, 117f6978b348, e9ada0a12c3f, 9b1697fdff0d, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 28496fb1f4c5, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| gmrm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4fbb0fc77db8, 9ea62e37e453 |  | 0 | True | False | False | False |
| gnrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 117f6978b348, 40c92af58e6b, 066921cd681d, fed5208309e0, 19c13c4d0fda, eecf3193581a |  | 0 | True | False | False | False |
| gorm | 77c86cd0c17a, 6aa92787433c, 8f4abf075ee0, e0e957b09025, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, eecf3193581a, fed5208309e0, 1d9d650e8a43, 19c13c4d0fda, 25c8ea6b1577, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1, 2 | True | False | False | False |
| gprm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 6c281b509549, 9f41c906558f, 3ab5f8fe96f4, 40c92af58e6b, b2fcb856104f, 5673678c0373, e0e957b09025, 28496fb1f4c5 |  | 0 | True | False | False | False |
| grrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, e0e957b09025, baeaf2a9d637 |  | 0 | True | False | False | False |
| gsrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62 | 0, 1 | True | False | False | False |
| gtrm | 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, 142bbf0bf7fb, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| gurm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 5673678c0373, 40c92af58e6b, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| gwrm | 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 60490ae8efdc, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b |  | 0 | True | False | False | False |
| gxrm | e0e957b09025, cf3cb69d4b7f, 7630ce144577, 7db56e9a5841, 5cd238832057, 8f030943aeb4, c9c6dc2a9231, 117fd7eb4622, dcef78bc22f0, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| gyrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| gzrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, e0e957b09025, b2fcb856104f, 117f6978b348, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| h2rm | 6c281b509549, 5673678c0373, 650eafce0eaa, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| h3rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 3ab5f8fe96f4, 40c92af58e6b, b2fcb856104f |  | 0 | True | False | False | False |
| h5rm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| h6rm | 7db56e9a5841, 5cd238832057, c2ca32745d26, 712ce9b7b11a, c9c6dc2a9231, 8a1d6deba766, 4d7ee9a33ecb, 117fd7eb4622, e0e957b09025, 9f41c906558f |  | 0 | True | False | False | False |
| h7rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, cd12add2435e, 117fd7eb4622, 4d7ee9a33ecb, 41ca19922c41, 9f41c906558f, 8f4abf075ee0, 5673678c0373, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| h8rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 7b913c93bb17, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| h9rm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 6c281b509549, 28496fb1f4c5, 5673678c0373, 35667705e3aa, 4bae16e7f959 |  | 0 | True | False | False | False |
| harm | 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 5673678c0373, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 93cf506de9b3, 2e64e05f3433, 19c13c4d0fda, d0daaadb8852, 117f6978b348, 3dc2f2b7bb6a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hbrm | 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, 117f6978b348, 93cf506de9b3, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hcrm | 27175a0eb1db, 2be41ffbb790, 401fefccde6c, c9c6dc2a9231, deb504870d56, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 2e64e05f3433, 2cf18159af62, 7936d8f22c8b, f361a88972f6, ca0bd126e0a1, ec59821b3288, 0b38648cbc7d, fb4a820461aa, 8a49ddf1e409, 2cd34a3a66a4, e0e957b09025, 117f6978b348 |  | 0 | True | False | False | False |
| hdrm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 3ab5f8fe96f4, 117f6978b348, 02ba78481b03, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| herm | c9c6dc2a9231, e0e957b09025, 4d7ee9a33ecb, 117fd7eb4622, 8f4abf075ee0, 9f41c906558f, baeaf2a9d637, 4bae16e7f959, 015704594ec9, 77c86cd0c17a, 28496fb1f4c5, 6aa92787433c, 2445a0dfc2f6, 5673678c0373, bf729f1b5ed0, 117f6978b348, ba1f116c4be9 |  | 0 | True | False | False | False |
| hkrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f |  | 0, 1 | True | False | False | False |
| hlrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, e0e957b09025, 9d89827e6527, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hmrm | 8f4abf075ee0, 4bae16e7f959, a682aa466866, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 5673678c0373, 015704594ec9, e0e957b09025, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 4674d65a3f82, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hnrm | 28496fb1f4c5, bc6785c7a5e2, 5673678c0373, 6c281b509549, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 650eafce0eaa, 096137e27d72, 015704594ec9, 19c13c4d0fda, 066921cd681d, 3dc2f2b7bb6a, c51a841b2c8c, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hprm | 117f6978b348, 8f4abf075ee0, 5673678c0373, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 066921cd681d, e0e957b09025, b2fcb856104f, fed5208309e0, 834d0298c2a6, 19c13c4d0fda, eecf3193581a, 0f61cb2ddc7d, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hqrm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, 1d9d650e8a43, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hrrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62 | 0 | True | False | False | False |
| htrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 7b913c93bb17, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| hurm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 40c92af58e6b, 8f4abf075ee0, 117f6978b348 |  | 0 | True | False | False | False |
| hvrm | 2169603a2ccb, 5673678c0373, 3261d5acee66, cd12add2435e, 28496fb1f4c5, 41ca19922c41, baeaf2a9d637, 6c281b509549, 015704594ec9, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hwrm | e9ada0a12c3f, 1c485e495380, 9b1697fdff0d, 3af051d36602, cd12add2435e, 40c92af58e6b, 41ca19922c41, c9c6dc2a9231, 2169603a2ccb, 117fd7eb4622, 4d7ee9a33ecb, 3261d5acee66, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hxrm | 5673678c0373, 1c485e495380, 6b7e45adcd7e, 3af051d36602, e9ada0a12c3f, 40c92af58e6b, 9b1697fdff0d, c9c6dc2a9231, cd12add2435e, 117fd7eb4622, 4d7ee9a33ecb, 41ca19922c41, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hyrm | 28496fb1f4c5, 1c485e495380, 5673678c0373, e9ada0a12c3f, 3af051d36602, 9b1697fdff0d, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, cd12add2435e, 40c92af58e6b, 2169603a2ccb, 41ca19922c41, 117f6978b348, 3261d5acee66, 066921cd681d, fed5208309e0, 93cf506de9b3, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| hzrm | 117f6978b348, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f | 61a7fe7954d9, 85a65e824cea, 96fa600efc5a | 0 | True | False | False | False |
| i0rm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| i1rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, e0e957b09025, 117f6978b348, eecf3193581a | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| i2rm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 5673678c0373, 015704594ec9, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 9ac4ed2f3878 |  | 0 | True | False | False | False |
| i3rm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 7b913c93bb17, 015704594ec9, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| i4rm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| i5rm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 3ab5f8fe96f4, 8f4abf075ee0, 834d0298c2a6, b2fcb856104f, 4bae16e7f959, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| i6rm | 3ab5f8fe96f4, b2fcb856104f, 8f4abf075ee0, e0e957b09025, 4bae16e7f959 |  | 0 | True | False | False | False |
| i7rm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, a12633f5f7e7, 066921cd681d, b88f492e2cf8, fed5208309e0, 19c13c4d0fda, 117f6978b348 |  | 0 | True | False | False | False |
| i8rm | 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 5673678c0373, a12633f5f7e7, 066921cd681d, b88f492e2cf8, fed5208309e0, 19c13c4d0fda, 117f6978b348, e0e957b09025 |  | 0 | True | False | False | False |
| i9rm | 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, ec59821b3288, e0e957b09025 |  | 0 | True | False | False | False |
| iarm | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, a12633f5f7e7, 066921cd681d, c51a841b2c8c, 19c13c4d0fda, 117f6978b348, fed5208309e0 |  | 0 | True | False | False | False |
| ibrm | c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, 6c281b509549, 28496fb1f4c5, 5673678c0373, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, e0e957b09025, 117f6978b348, eecf3193581a | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62 | 0 | True | False | False | False |
| icrm | 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, 5673678c0373, a12633f5f7e7, 066921cd681d, b88f492e2cf8, fed5208309e0, 19c13c4d0fda, 117f6978b348, 8f4abf075ee0 |  | 0 | True | False | False | False |
| idrm | 6c281b509549, 117f6978b348, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| ierm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, a12633f5f7e7, 066921cd681d, b88f492e2cf8, fed5208309e0, 19c13c4d0fda, 117f6978b348, eecf3193581a |  | 0 | True | False | False | False |
| ifrm | 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, cb68d0c1f3d0, e0e957b09025 |  | 0 | True | False | False | False |
| igrm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 7b913c93bb17, 5673678c0373, 6c281b509549, a12633f5f7e7, 066921cd681d, 28496fb1f4c5, 19c13c4d0fda, fed5208309e0, 117f6978b348, eecf3193581a |  | 0 | True | False | False | False |
| ihrm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, a12633f5f7e7, 066921cd681d, b88f492e2cf8, fed5208309e0, 19c13c4d0fda, 117f6978b348, 3dc2f2b7bb6a |  | 0 | True | False | False | False |
| iirm | 40c92af58e6b, e0e957b09025, 8f4abf075ee0, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, a12633f5f7e7, 066921cd681d, b88f492e2cf8, fed5208309e0 |  | 0 | True | False | False | False |
| ijrm | c9c6dc2a9231, 4d7ee9a33ecb, e0e957b09025 |  | 0 | True | False | False | False |
| ikrm | c9c6dc2a9231, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| ilrm | c9c6dc2a9231, 4d7ee9a33ecb, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 943b0a6f4768 |  | 0 | True | False | False | False |
| imrm | c9c6dc2a9231, 4d7ee9a33ecb, 117f6978b348, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| inrm | c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, ec59821b3288, e0e957b09025, 8f4abf075ee0 |  | 0 | True | False | False | False |
| iorm | 6c281b509549, e0e957b09025, 28496fb1f4c5, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, 066921cd681d, c51a841b2c8c, fed5208309e0 |  | 0 | True | False | False | False |
| iprm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f |  | 0 | True | False | False | False |
| iqrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, 7b913c93bb17, 28496fb1f4c5 | 96fa600efc5a | 0 | True | False | False | False |
| irrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 7b913c93bb17, 015704594ec9, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 9ac4ed2f3878 |  | 0 | True | False | False | False |
| isrm | c9c6dc2a9231, 4d7ee9a33ecb, e0e957b09025, 8a1d6deba766 |  | 0 | True | False | False | False |
| j2rm | 28496fb1f4c5, 5673678c0373, 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, e2c34d5c7ade, 880df9c72093, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| j3rm | 5673678c0373, 8f4abf075ee0, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, e2c34d5c7ade, 880df9c72093, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| j4rm | c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f, 5673678c0373, e0e957b09025, 28496fb1f4c5 |  | 0 | True | False | False | False |
| j5rm | c9c6dc2a9231, 117fd7eb4622, 8f4abf075ee0, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 117f6978b348, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| j6rm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37 |  | 0 | True | False | False | False |
| j7rm | 28496fb1f4c5, 5673678c0373, 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, e2c34d5c7ade, 880df9c72093, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| j9rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jbrm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jdrm | e0e957b09025, 7630ce144577, 85a65e824cea, 61a7fe7954d9, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 2cf18159af62, 117f6978b348, b2fcb856104f, 1aa50b6d640d, 5f94b5202960, 747268a767c1, aae5ac3a0d37, c152a974ea6c |  | 0 | True | False | False | False |
| jerm | 8f4abf075ee0, 4bae16e7f959, a682aa466866, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 5673678c0373, 117f6978b348, 28496fb1f4c5, 747268a767c1, e0e957b09025, aae5ac3a0d37 |  | 0 | True | False | False | False |
| jfrm | e0e957b09025, 7630ce144577, 85a65e824cea, 61a7fe7954d9, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 2cf18159af62, 117f6978b348, b2fcb856104f, 1aa50b6d640d, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| jgrm | 269880b9371b, 0cbc9c0946d9, 7f3a7ce922ef, 7630ce144577, 7db56e9a5841, 5cd238832057, c9c6dc2a9231, 4d7ee9a33ecb, cea3e21b77bb, 117fd7eb4622, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jhrm | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, 5673678c0373, 4d7ee9a33ecb, 8a1d6deba766, 117fd7eb4622, e0e957b09025, 9f41c906558f |  | 0 | True | False | False | False |
| jjrm | c9c6dc2a9231, 4d7ee9a33ecb, 6c281b509549, e0e957b09025, 8a1d6deba766 |  | 0 | True | False | False | False |
| jkrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, e0e957b09025, fed5208309e0, 19c13c4d0fda, a682aa466866, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jlrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jmrm | 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 5673678c0373, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 93cf506de9b3, 2e64e05f3433, 19c13c4d0fda, d0daaadb8852, 117f6978b348, 3dc2f2b7bb6a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| jnrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jprm | d0daaadb8852, cc52e6494256, 00467dc3027e, eecf3193581a, 117f6978b348, 19c13c4d0fda, 066921cd681d, 8f4abf075ee0, fed5208309e0, c9c6dc2a9231, 40c92af58e6b, 4d7ee9a33ecb, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, 117fd7eb4622, e0e957b09025, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| jqrm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025 | 61a7fe7954d9, 85a65e824cea, 2cf18159af62 | 0, 1 | True | False | False | False |
| jrrm | 7b913c93bb17, 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 6c281b509549, eecf3193581a, 015704594ec9, 19c13c4d0fda, 066921cd681d, e0e957b09025, 4bae16e7f959, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| jsrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 7b913c93bb17, 6c281b509549, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jwrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 2169603a2ccb, 4d7ee9a33ecb, 9f41c906558f, 3261d5acee66, 8f4abf075ee0, 1a3d61c98ecd, 40c92af58e6b, 066921cd681d, 19c13c4d0fda, fed5208309e0, 3dc2f2b7bb6a, 117f6978b348, c51a841b2c8c, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| jzrm | e0e957b09025, 6c281b509549, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| k2rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 28496fb1f4c5, 40c92af58e6b |  | 0 | True | False | False | False |
| k5rm | 48c2bc0ceadb, 117f6978b348, 9b1697fdff0d, f74a6c435973, 6b7e45adcd7e, 93cf8e749e1a, 1c485e495380, e9ada0a12c3f, 3af051d36602, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, e0e957b09025, 40c92af58e6b, 8f4abf075ee0, 5673678c0373, eecf3193581a, 28496fb1f4c5, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| k6rm | 5673678c0373, 28496fb1f4c5, 117f6978b348, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| k7rm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 35667705e3aa |  | 0 | True | False | False | False |
| k8rm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 117f6978b348, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 |  | 0 | True | False | False | False |
| k9rm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025 |  | 0 | True | False | False | False |
| karm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 117f6978b348 |  | 0, 1 | True | False | False | False |
| kbrm | 48c2bc0ceadb, 117f6978b348, e9ada0a12c3f, 1c485e495380, 3af051d36602, 9b1697fdff0d, 6b7e45adcd7e, f74a6c435973, 93cf8e749e1a, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 28496fb1f4c5, 5673678c0373, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| kcrm | 48c2bc0ceadb, e0e957b09025, e9ada0a12c3f, 1c485e495380, 3af051d36602, 9b1697fdff0d, 6b7e45adcd7e, f74a6c435973, 93cf8e749e1a, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 28496fb1f4c5, 5673678c0373, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| kerm | 6c281b509549, 8f4abf075ee0, 28496fb1f4c5, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 2cf18159af62, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| kfrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, eecf3193581a, 117f6978b348, 066921cd681d, 19c13c4d0fda, e0e957b09025, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | dcef78bc22f0, 61a7fe7954d9, 96fa600efc5a, 2cf18159af62, 1aa50b6d640d, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| kgrm | 5673678c0373, 1c485e495380, 6b7e45adcd7e, 3af051d36602, e9ada0a12c3f, 40c92af58e6b, 9b1697fdff0d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| khrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117f6978b348, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f |  | 0 | True | False | False | False |
| kjrm | 6c281b509549, 117f6978b348, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| kkrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, 5673678c0373, 8f4abf075ee0 | 85a65e824cea, 2cf18159af62, 066921cd681d, fed5208309e0 | 0 | True | False | False | False |
| kmrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| knrm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| kprm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 61a7fe7954d9, 85a65e824cea, 2cf18159af62, 1aa50b6d640d | 0 | True | False | False | False |
| kqrm | 8f4abf075ee0, 6c281b509549, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, e0e957b09025, 117f6978b348, 40c92af58e6b | dcef78bc22f0 | 0 | True | False | False | False |
| krrm | 5673678c0373, 28496fb1f4c5, 117f6978b348, 40c92af58e6b, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 85a65e824cea, 61a7fe7954d9 | 0 | True | False | False | False |
| kurm | 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117f6978b348, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f |  | 0, 1 | True | False | False | False |
| kvrm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 066921cd681d, 8f4abf075ee0, e0e957b09025, 1d9d650e8a43, 4bae16e7f959, fed5208309e0, 19c13c4d0fda, eecf3193581a, 25c8ea6b1577, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| kxrm | e0e957b09025, 8f4abf075ee0, 4bae16e7f959, a682aa466866, c9c6dc2a9231, 117fd7eb4622, 6c281b509549, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| kyrm | 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 117f6978b348, 9f41c906558f, baeaf2a9d637, 015704594ec9, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| l3rm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, fed5208309e0, 7b913c93bb17, 6c281b509549, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, e9c2c0671d97, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| l4rm | 28496fb1f4c5, 5673678c0373, 117f6978b348, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 |  | 0 | True | False | False | False |
| l5rm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, 117f6978b348, 8f4abf075ee0, 19c13c4d0fda, 066921cd681d, fed5208309e0 |  | 0, 1, 2 | True | False | False | False |
| l8rm | c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, 5673678c0373, 096137e27d72, 8f4abf075ee0, 4bae16e7f959, a682aa466866 |  | 0 | True | False | False | False |
| l9rm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| lcrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6fa232d21245, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, fed5208309e0, 7b913c93bb17, 6c281b509549, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, e9c2c0671d97, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| ldrm | 5673678c0373, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| lfrm | 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, 28496fb1f4c5, 6c281b509549, 5673678c0373, 066921cd681d, c51a841b2c8c, 19c13c4d0fda, 117f6978b348, fed5208309e0 | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| lgrm | 5673678c0373, 8f4abf075ee0, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| ljrm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 40c92af58e6b, 117fd7eb4622, e0e957b09025, 9f41c906558f | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| llrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| lmrm | c281d87c6bc6, 142bbf0bf7fb, cca2946b7656 |  | 0 | True | False | False | False |
| lnrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 4bae16e7f959 |  | 0 | True | False | False | False |
| lqrm | 117f6978b348, 40ada9347fc6, 650eafce0eaa, 5673678c0373, dcbbe7e29dbc, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 6c281b509549, 28496fb1f4c5, e0e957b09025, 7b913c93bb17, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 2210609e88f8, 3228164a54b8, cc8810821e84, 1693947c0792, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| lrrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 6c281b509549, e0e957b09025, 28496fb1f4c5, 4bae16e7f959, 5673678c0373, 117f6978b348, 7b913c93bb17 | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 3228164a54b8 | 0 | True | False | False | False |
| lsrm | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 6c281b509549, e0e957b09025, 7b913c93bb17, 8f4abf075ee0, 5673678c0373, 117f6978b348 | 54c13a02b356, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218 | 0 | True | False | False | False |
| lurm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 117f6978b348 |  | 0 | True | False | False | False |
| lvrm | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 3ab5f8fe96f4, 19c13c4d0fda, eecf3193581a, b2fcb856104f, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| lwrm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 |  | 0 | True | False | False | False |
| lxrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| lyrm | 3ab5f8fe96f4, 28496fb1f4c5, b2fcb856104f, c9c6dc2a9231, 77c86cd0c17a, 117fd7eb4622, 4d7ee9a33ecb, 6aa92787433c, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| lzrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| m2rm | 5673678c0373, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 40c92af58e6b, e0e957b09025, b2fcb856104f, 117f6978b348, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| m3rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| m4rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, e0e957b09025, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f |  | 0 | True | False | False | False |
| m5rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 8a9f00d9b56b, 117f6978b348, 0ed419290436, 598c167cdd86, e0e957b09025, 7d7711b87a5b |  | 0 | True | False | False | False |
| m6rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 4bae16e7f959, 066921cd681d, 2e64e05f3433, fed5208309e0, 19c13c4d0fda, f361a88972f6, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| m7rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 117f6978b348, 066921cd681d, fed5208309e0, 19c13c4d0fda, eecf3193581a |  | 0 | True | False | False | False |
| m8rm | 5673678c0373, 28496fb1f4c5, 117f6978b348, 6c281b509549, 40c92af58e6b, 8f4abf075ee0, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| m9rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 6fa232d21245, 8f4abf075ee0, 35667705e3aa, 40c92af58e6b, e0e957b09025 |  | 0 | True | False | False | False |
| marm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, 015704594ec9, 117f6978b348, 066921cd681d, fed5208309e0, 19c13c4d0fda, eecf3193581a |  | 0 | True | False | False | False |
| mcrm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, e0e957b09025, b2fcb856104f, 8f4abf075ee0, 747268a767c1, aae5ac3a0d37 |  | 0 | True | False | False | False |
| mdrm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 3ab5f8fe96f4, 8a1d6deba766, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| merm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 3ab5f8fe96f4, 8a1d6deba766, b2fcb856104f |  | 0 | True | False | False | False |
| mfrm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 834d0298c2a6, b2fcb856104f, 0f61cb2ddc7d, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| mgrm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, 4bae16e7f959 |  | 0 | True | False | False | False |
| mlrm | 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 35667705e3aa, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 1d9d650e8a43, e0e957b09025, 25c8ea6b1577, d0daaadb8852, 8a49ddf1e409, 00467dc3027e |  | 0 | True | False | False | False |
| mmrm | 40c92af58e6b, 2f6d8987dec5, 6b7f5b7e4164, b1db771e6321, db703b2419a6, 8813cb017a49, b8e3489845f5, 38d7adaf1e75, 9ea62e37e453, 334e68909524, 714e57c2a018, ef3a6fa0cab9, 2201ae4481dc, 64a00c529c7e, a12633f5f7e7, 89900b928a9a, a9df34716acf, e0f268656b0e, 45e9ce37fd2b, e0e957b09025, ec80d8038d75, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| mrrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| o0rm | 117f6978b348, e0e957b09025, 35667705e3aa, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 0ff117b1a0e4, 8f4abf075ee0, 40c92af58e6b, 855711f7ad92, 066921cd681d, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577, d0daaadb8852, 00467dc3027e | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| o1rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| o2rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, c51a841b2c8c, 117f6978b348, 2e64e05f3433, 19c13c4d0fda, e0e957b09025, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| o3rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| o4rm | 8f4abf075ee0, c5f845fc1b8c, 4bae16e7f959, c9c6dc2a9231, 117f6978b348, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, 9d89827e6527, fed5208309e0, 1d9d650e8a43, 19c13c4d0fda, 25c8ea6b1577, ca0bd126e0a1, 3dc2f2b7bb6a, 7936d8f22c8b |  | 0 | True | False | False | False |
| o5rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 8f4abf075ee0, 0f61cb2ddc7d, a12633f5f7e7, cb68d0c1f3d0, 117f6978b348, 40c92af58e6b, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| o6rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 2e64e05f3433, 8f4abf075ee0, 7936d8f22c8b, f361a88972f6, ca0bd126e0a1, ec59821b3288, 0b38648cbc7d, fb4a820461aa, 8a49ddf1e409, 2cd34a3a66a4, e0e957b09025, 3dc2f2b7bb6a, 3dc2f2b7bb6a |  | 0 | True | False | False | False |
| o7rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| o8rm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| o9rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| oarm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 6c281b509549, 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| omrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, deb504870d56, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 2e64e05f3433, 2cf18159af62, 7936d8f22c8b, f361a88972f6, ca0bd126e0a1, ec59821b3288, 0b38648cbc7d, fb4a820461aa, 8a49ddf1e409, 2cd34a3a66a4, e0e957b09025, 3dc2f2b7bb6a, 117f6978b348 |  | 0 | True | False | False | False |
| onrm | 40c92af58e6b, 2f6d8987dec5, 6b7f5b7e4164, d213cf6b3d93, 9f4f2493dee8, 4deb18342f34, ec0a15aea952, 75ae7f8d618f, ded03dbb3f14, 334e68909524, a12633f5f7e7, 1f5c6a24ed34, ebdbb493dcf8, 27fbe32d1207, d9b3d5dfffab, 14755149209f, de25830c8d4b, c0dda09c7c32, 33c20fd70f57, 3a435638569b, ec80d8038d75 |  | 0 | True | False | False | False |
| oorm | 27175a0eb1db, 2be41ffbb790, 401fefccde6c, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, 2e64e05f3433, 7936d8f22c8b, f361a88972f6, ca0bd126e0a1, ec59821b3288, 0b38648cbc7d, fb4a820461aa, 8a49ddf1e409, 2cd34a3a66a4, e0e957b09025, 3dc2f2b7bb6a, 117f6978b348 |  | 0 | True | False | False | False |
| oprm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| oqrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| orrm | 3ab5f8fe96f4, 6c281b509549, b2fcb856104f, c9c6dc2a9231, 77c86cd0c17a, 117fd7eb4622, 4d7ee9a33ecb, 6aa92787433c, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| osrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 976dbfd3d1e0, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| otrm | 117f6978b348, e0e957b09025, 35667705e3aa, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 0ff117b1a0e4, 8f4abf075ee0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577, d0daaadb8852, 00467dc3027e | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| ourm | 27175a0eb1db, 401fefccde6c, 142bbf0bf7fb, e0e957b09025 |  | 0 | True | False | False | False |
| ovrm | a3494ef11b0f, d3480f51746b |  | 0 | True | False | False | False |
| owrm | 40c1cd7355f7, 7b8ececd7224, 63144be9c453, 40c92af58e6b, fd7cabcb5995, 142bbf0bf7fb |  | 0 | True | False | False | False |
| oxrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| oyrm | 117f6978b348, e0e957b09025, 3dc2f2b7bb6a, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 3dc2f2b7bb6a, 8f4abf075ee0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577, d0daaadb8852, cc52e6494256 | 905d025dc026, 06098b3bf431, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| ozrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| p0rm | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| p1rm | 6c281b509549, 28496fb1f4c5, 117f6978b348, c9c6dc2a9231, 0e6d9419b849, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, 0ff117b1a0e4, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026 | 0 | True | False | False | False |
| p2rm | c9c6dc2a9231, e0e957b09025, 4d7ee9a33ecb, 117fd7eb4622, 8f4abf075ee0, 9f41c906558f, baeaf2a9d637, 4bae16e7f959, 015704594ec9, 77c86cd0c17a, 28496fb1f4c5, 6aa92787433c, 2445a0dfc2f6, 5673678c0373, bf729f1b5ed0, 117f6978b348, ba1f116c4be9 |  | 0 | True | False | False | False |
| p3rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 40c92af58e6b, 3dc2f2b7bb6a |  | 0 | True | False | False | False |
| p4rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| p5rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, a12633f5f7e7, 066921cd681d, 142bbf0bf7fb, fed5208309e0, 2f1420c5a271, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| p6rm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 77c86cd0c17a, 834d0298c2a6, 6aa92787433c, 066921cd681d, 0f61cb2ddc7d, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 5673678c0373, 40c92af58e6b |  | 0 | True | False | False | False |
| p9rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| qrrm |  |  | 0 | True | False | False | False |
| r2rm | 40c92af58e6b, 2f6d8987dec5, 6b7f5b7e4164, b1db771e6321, db703b2419a6, 8813cb017a49, b8e3489845f5, 38d7adaf1e75, 9ea62e37e453, 334e68909524, 714e57c2a018, ef3a6fa0cab9, 2201ae4481dc, 64a00c529c7e, a12633f5f7e7, be9bf9076ad2, ab1f300c0bec, 8d5cd2611afe, f8e672eec1db, 5530d0fca78d, 33c66736687c, aaa2bcc5127b, b993d8df46b2, 9cbb678a9d22 |  | 0 | True | False | False | False |
| r5rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| r6rm | 8f4abf075ee0, 4bae16e7f959, a682aa466866, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, c5f845fc1b8c, 40c92af58e6b, c5f845fc1b8c, 2e64e05f3433, a12633f5f7e7, 7936d8f22c8b, f361a88972f6, e0e957b09025, ca0bd126e0a1, ec59821b3288, 0b38648cbc7d, fb4a820461aa, 8a49ddf1e409, 2cd34a3a66a4 |  | 0 | True | False | False | False |
| s9rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, 5673678c0373, 35667705e3aa, 40c92af58e6b, e0e957b09025 |  | 0 | True | False | False | False |
| sarm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 28496fb1f4c5, 5673678c0373, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| t0rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| t1rm | 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, bc3a73aad676, 4d7ee9a33ecb, 117fd7eb4622, bc3a73aad676, 9f41c906558f, 3ab5f8fe96f4, bc3a73aad676, b2fcb856104f, 834d0298c2a6, bc3a73aad676, 0f61cb2ddc7d, e0e957b09025, 117f6978b348 |  | 0 | True | False | False | False |
| t2rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| t3rm | 28496fb1f4c5, 5673678c0373, 6c281b509549, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, 40c92af58e6b, e0e957b09025, cb68d0c1f3d0 |  | 0 | True | False | False | False |
| t4rm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4fbb0fc77db8, 9ea62e37e453, e0e957b09025, 0cbc9c0946d9 |  | 0 | True | False | False | False |
| t5rm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, c9c6dc2a9231, 6c281b509549, 117fd7eb4622, 4d7ee9a33ecb, 28496fb1f4c5, 9f41c906558f, 40c92af58e6b, 5673678c0373, 117f6978b348, 066921cd681d, c51a841b2c8c, fed5208309e0, 19c13c4d0fda, 3dc2f2b7bb6a, 3dc2f2b7bb6a | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| t6rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 3dc2f2b7bb6a |  | 0 | True | False | False | False |
| t7rm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| t8rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| t9rm | 28496fb1f4c5, 5673678c0373, c5f845fc1b8c, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, c5f845fc1b8c, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, 1d9d650e8a43, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 2256dbe95090 | 0 | True | False | False | False |
| tarm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| tbrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, c9c6dc2a9231, 6c281b509549, 117fd7eb4622, 4d7ee9a33ecb, 7b913c93bb17, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, 117f6978b348, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 2f1420c5a271, 2f1420c5a271 | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| tcrm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| tdrm | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, 8f4abf075ee0, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| term | 3ab5f8fe96f4, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, b2fcb856104f, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, e0e957b09025, eecf3193581a |  | 0 | True | False | False | False |
| test | c9c6dc2a9231, bc0701329d6d |  | 0 | True | False | False | False |
| thrm | 40c92af58e6b, 2f6d8987dec5, 6b7f5b7e4164, d213cf6b3d93, 9f4f2493dee8, 4fbb0fc77db8, ec0a15aea952, 75ae7f8d618f, 9ea62e37e453, 334e68909524, a12633f5f7e7, 1f5c6a24ed34, ebdbb493dcf8, 27fbe32d1207, d9b3d5dfffab, 14755149209f, de25830c8d4b, c0dda09c7c32, 33c20fd70f57, 3a435638569b, ec80d8038d75 |  | 0 | True | False | False | False |
| tlrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, e0e957b09025, 117f6978b348 |  | 0 | True | False | False | False |
| twrm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 4fbb0fc77db8, 9ea62e37e453, e0e957b09025, 5f8ce0c4c2dd |  | 0 | True | False | False | False |
| tzrm | 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 06285d76f7d6, 69f676b601cc, e0e957b09025, 5f8ce0c4c2dd |  | 0 | True | False | False | False |
| u0rm | 28496fb1f4c5, 7b913c93bb17, 40c92af58e6b, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 35667705e3aa |  | 0 | True | False | False | False |
| u1rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, c51a841b2c8c, 117f6978b348, 2e64e05f3433, 19c13c4d0fda, e0e957b09025, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| u2rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, c51a841b2c8c, 117f6978b348, 2e64e05f3433, 19c13c4d0fda, e0e957b09025, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| u3rm | 28496fb1f4c5, 6c281b509549, 7b913c93bb17, c9c6dc2a9231, 8a9f00d9b56b, 117fd7eb4622, 4d7ee9a33ecb, 598c167cdd86, 9f41c906558f, 8f4abf075ee0, 6fa232d21245, 117f6978b348, a12633f5f7e7, e0e957b09025, 066921cd681d, c51a841b2c8c, 40c92af58e6b, fed5208309e0, 19c13c4d0fda, 5673678c0373, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| u4rm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, baeaf2a9d637, a12633f5f7e7, 015704594ec9, 066921cd681d, fed5208309e0, eecf3193581a, 117f6978b348, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| u5rm | 3ab5f8fe96f4, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, b2fcb856104f, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, e0e957b09025, 117f6978b348, eecf3193581a |  | 0 | True | False | False | False |
| u6rm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| u7rm | 117f6978b348, e0e957b09025, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 35667705e3aa, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| u8rm | 117f6978b348, e0e957b09025, 35667705e3aa, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0 |  | 0 | True | False | False | False |
| u9rm | 35667705e3aa, e0e957b09025, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| uarm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 35667705e3aa, 28496fb1f4c5, 5673678c0373, a12633f5f7e7, 066921cd681d, d0daaadb8852, fed5208309e0, 1d9d650e8a43, cc52e6494256, 25c8ea6b1577, 8a49ddf1e409 |  | 0 | True | False | False | False |
| ubrm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 35667705e3aa, 28496fb1f4c5, 5673678c0373, a12633f5f7e7, 066921cd681d, d0daaadb8852, fed5208309e0, 1d9d650e8a43, cc52e6494256, 25c8ea6b1577, 8a49ddf1e409 |  | 0 | True | False | False | False |
| ucrm | baeaf2a9d637, e0e957b09025, 015704594ec9, c9c6dc2a9231, 7b913c93bb17, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| udrm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| uerm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 40c92af58e6b, 066921cd681d, a12633f5f7e7, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ufrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| ugrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| uhrm | 8f4abf075ee0, 4bae16e7f959, a682aa466866, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| uirm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 6c281b509549, 28496fb1f4c5, bd888e1de887, 7b913c93bb17, 5673678c0373, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f |  | 0 | True | False | False | False |
| ujrm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 35667705e3aa, 28496fb1f4c5, 5673678c0373, a12633f5f7e7, 066921cd681d, d0daaadb8852, fed5208309e0, 1d9d650e8a43, cc52e6494256, 25c8ea6b1577, 8a49ddf1e409 |  | 0 | True | False | False | False |
| ukrm | 40c92af58e6b, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, c51a841b2c8c, 117f6978b348, 2e64e05f3433, 19c13c4d0fda, e0e957b09025, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ulrm | 40c92af58e6b, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda |  | 0 | True | False | False | False |
| umrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| unrm | 28496fb1f4c5, 5673678c0373, 6c281b509549, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 117f6978b348, 4bae16e7f959, 3dc2f2b7bb6a, a12633f5f7e7, 35667705e3aa, 066921cd681d, c51a841b2c8c, 40c92af58e6b, fed5208309e0, 19c13c4d0fda, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| uorm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| uprm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| uqrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| urrm | 5673678c0373, 8f4abf075ee0, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| utrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| uurm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 40c92af58e6b, 117fd7eb4622, e0e957b09025, 9f41c906558f |  | 0 | True | False | False | False |
| uvrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| uwrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| uxrm | 5673678c0373, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b |  | 0 | True | False | False | False |
| uyrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 3a6416ee9d41, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| uzrm | 28496fb1f4c5, 7b913c93bb17, 40c92af58e6b, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, c51a841b2c8c, 6c281b509549, 2e64e05f3433, 19c13c4d0fda, 35667705e3aa, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| v0rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, 3dc2f2b7bb6a, a12633f5f7e7, 35667705e3aa, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| v1rm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| v2rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| v3rm | 4fbb0fc77db8, 9ea62e37e453, 9f4f2493dee8, 75ae7f8d618f, ec0a15aea952, 334e68909524, 8f4abf075ee0, 117f6978b348 |  | 0 | True | False | False | False |
| v4rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| v5rm | 117f6978b348, e0e957b09025, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f |  | 0 | True | False | False | False |
| v6rm | 117f6978b348, e0e957b09025, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 35667705e3aa, 28496fb1f4c5, 066921cd681d, 142bbf0bf7fb, fed5208309e0 |  | 0 | True | False | False | False |
| v7rm | 117f6978b348, e0e957b09025, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 40c92af58e6b, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 066921cd681d, 35667705e3aa, fed5208309e0, a12633f5f7e7, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| v8rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| v9rm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, 3ab5f8fe96f4, 28496fb1f4c5, 5673678c0373, b2fcb856104f, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 9ac4ed2f3878 |  | 0 | True | False | False | False |
| varm | 117f6978b348, e0e957b09025, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 35667705e3aa, 28496fb1f4c5 |  | 0 | True | False | False | False |
| vbrm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 6c281b509549, 28496fb1f4c5, bd888e1de887, 7b913c93bb17, 5673678c0373, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a |  | 0 | True | False | False | False |
| vcrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| vdrm | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, a12633f5f7e7, 066921cd681d, c51a841b2c8c, 19c13c4d0fda, 117f6978b348, fed5208309e0 |  | 0 | True | False | False | False |
| verm | 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, 28496fb1f4c5, 6c281b509549, 5673678c0373, 066921cd681d, c51a841b2c8c, 19c13c4d0fda, 117f6978b348, fed5208309e0 |  | 0 | True | False | False | False |
| vfrm | 6c281b509549, 8f4abf075ee0, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 0f61cb2ddc7d, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| vgrm | 28496fb1f4c5, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, ec59821b3288, e0e957b09025 |  | 0 | True | False | False | False |
| vhrm | 6c281b509549, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 5673678c0373 |  | 0 | True | False | False | False |
| virm | 28496fb1f4c5, e0e957b09025, 5673678c0373, 3ab5f8fe96f4, 834d0298c2a6, 8f4abf075ee0, b2fcb856104f, 0f61cb2ddc7d, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 9ac4ed2f3878 |  | 0 | True | False | False | False |
| vjrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 40c92af58e6b | 4f5e1c0d1218 | 0 | True | False | False | False |
| vkrm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 6c281b509549, 28496fb1f4c5, bd888e1de887, 35667705e3aa, 5673678c0373, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a |  | 0 | True | False | False | False |
| vlrm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 3ab5f8fe96f4, b2fcb856104f, bd888e1de887, 28496fb1f4c5, 5673678c0373, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, eecf3193581a |  | 0 | True | False | False | False |
| vmrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, 3ab5f8fe96f4, 28496fb1f4c5, 5673678c0373, b2fcb856104f, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| vnrm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, 117f6978b348, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, b88f492e2cf8 |  | 0 | True | False | False | False |
| vorm | 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, 28496fb1f4c5, 6c281b509549, 5673678c0373, 066921cd681d, c51a841b2c8c, 19c13c4d0fda, 117f6978b348, fed5208309e0 | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| vprm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 3ab5f8fe96f4, b2fcb856104f, bd888e1de887, 834d0298c2a6, 0f61cb2ddc7d, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, eecf3193581a |  | 0 | True | False | False | False |
| vqrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 8f4abf075ee0, 28496fb1f4c5, 066921cd681d, fed5208309e0, 1d9d650e8a43, 25c8ea6b1577 |  | 0 | True | False | False | False |
| vrrm | 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, 77c86cd0c17a, 4d7ee9a33ecb, 117fd7eb4622, 6aa92787433c, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, e0e957b09025, a12633f5f7e7, 3dc2f2b7bb6a, 066921cd681d, d326af07ba43, fed5208309e0, c51a841b2c8c, 117f6978b348, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| vsrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| vtrm | 6c281b509549, 28496fb1f4c5, 117f6978b348, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 0f61cb2ddc7d, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, 2f1420c5a271, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| vurm | 3ab5f8fe96f4, b2fcb856104f, 117f6978b348, c9c6dc2a9231, 6c281b509549, 4d7ee9a33ecb, 117fd7eb4622, 28496fb1f4c5, 9f41c906558f, 834d0298c2a6, 0f61cb2ddc7d, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, 2f1420c5a271, e0e957b09025, eecf3193581a |  | 0 | True | False | False | False |
| vvrm | c9c6dc2a9231, 3ab5f8fe96f4, 4d7ee9a33ecb, 117fd7eb4622, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| vwrm | c9c6dc2a9231, 7b913c93bb17, 4d7ee9a33ecb, 117fd7eb4622, 5673678c0373, 9f41c906558f, 40c92af58e6b, 6c281b509549, 8f4abf075ee0, 28496fb1f4c5, 066921cd681d, 4bae16e7f959, fed5208309e0, 19c13c4d0fda, a682aa466866, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| vxrm | baeaf2a9d637, e0e957b09025, 015704594ec9, c9c6dc2a9231, deb504870d56, 117fd7eb4622, 4d7ee9a33ecb, 2cf18159af62, 9f41c906558f, 066921cd681d, c60949e83877, 117f6978b348, 19c13c4d0fda, 1aa50b6d640d, fed5208309e0, 3dc2f2b7bb6a, 60e96affa5ae, eecf3193581a, 5f94b5202960 |  | 0 | True | False | False | False |
| vyrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 9ea62e37e453, 9f41c906558f, 8f4abf075ee0, 3a6416ee9d41, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| vzrm | c9c6dc2a9231, 6c281b509549, 117fd7eb4622, 4d7ee9a33ecb, 3ab5f8fe96f4, 9f41c906558f, 77c86cd0c17a, b2fcb856104f, 6aa92787433c, 066921cd681d, 834d0298c2a6, fed5208309e0, 19c13c4d0fda, 0f61cb2ddc7d, eecf3193581a, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| w0rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 9ea62e37e453, 9f41c906558f, 8f4abf075ee0, 976dbfd3d1e0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| w1rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| w2rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 9ea62e37e453, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| w3rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 3dc2f2b7bb6a, a12633f5f7e7, 976dbfd3d1e0, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| w4rm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, e0e957b09025, 9f41c906558f, 40c92af58e6b |  | 0 | True | False | False | False |
| w5rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 8f4abf075ee0, 117f6978b348, 4bae16e7f959, 066921cd681d, a682aa466866, fed5208309e0, 1d9d650e8a43, 28496fb1f4c5, 25c8ea6b1577, 19c13c4d0fda |  | 0 | True | False | False | False |
| w6rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, 4bae16e7f959, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| w7rm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 066921cd681d, 2e64e05f3433, fed5208309e0, 19c13c4d0fda, f361a88972f6, eecf3193581a, 117f6978b348 |  | 0 | True | False | False | False |
| w8rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| w9rm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 976dbfd3d1e0, 40c92af58e6b, 8f4abf075ee0, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, e0e957b09025, 117f6978b348, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| warm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 976dbfd3d1e0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| wbrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| wcrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| wdrm | 5673678c0373, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, ec59821b3288, 117f6978b348, 19c13c4d0fda, c51a841b2c8c, e0e957b09025, 2e64e05f3433, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| werm | 5673678c0373, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, ec59821b3288, 117f6978b348, 19c13c4d0fda, c51a841b2c8c, e0e957b09025, 2e64e05f3433, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| wgrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| whrm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 3ab5f8fe96f4, 9f41c906558f, 77c86cd0c17a, b2fcb856104f, 6aa92787433c, 066921cd681d, 834d0298c2a6, fed5208309e0, 19c13c4d0fda, 0f61cb2ddc7d, eecf3193581a, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| wirm | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, 3ab5f8fe96f4, 28496fb1f4c5, 5673678c0373, b2fcb856104f, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 9ac4ed2f3878 |  | 0 | True | False | False | False |
| wjrm | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| wkrm | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| wlrm | 28496fb1f4c5, 7b913c93bb17, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 4bae16e7f959, 6c281b509549, a682aa466866 | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 3228164a54b8, cc8810821e84 | 0 | True | False | False | False |
| wmrm | c9c6dc2a9231, 4d7ee9a33ecb | 327d71fae3ff | 0 | True | False | False | False |
| wnrm | 3ab5f8fe96f4, c9c6dc2a9231, 117fd7eb4622, b2fcb856104f, 4d7ee9a33ecb, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, e0e957b09025, 117f6978b348, eecf3193581a | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| worm | 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 60490ae8efdc, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b |  | 0 | True | False | False | False |
| wprm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 6c281b509549 |  | 0 | True | False | False | False |
| wqrm | c9c6dc2a9231, 4d7ee9a33ecb, 7b913c93bb17, 28496fb1f4c5, 8f4abf075ee0 |  | 0 | True | False | False | False |
| wrrm | baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025 | 4f5e1c0d1218 | 0 | True | False | False | False |
| wsrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 3ab5f8fe96f4, 40c92af58e6b, b2fcb856104f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| wtrm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 3ab5f8fe96f4, 77c86cd0c17a, 834d0298c2a6, b2fcb856104f, 6aa92787433c, 0f61cb2ddc7d, 8f4abf075ee0, 6c281b509549, 40c92af58e6b, 7b913c93bb17, 28496fb1f4c5 |  | 0 | True | False | False | False |
| wurm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, 4bae16e7f959, eecf3193581a, 117f6978b348 | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| wvrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| wwrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b | 06098b3bf431 | 0 | True | False | False | False |
| wxrm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 3dc2f2b7bb6a, 117f6978b348, eecf3193581a | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| wyrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 27175a0eb1db, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 117f6978b348 |  | 0 | True | False | False | False |
| wzrm | c9c6dc2a9231, e0e957b09025, 4d7ee9a33ecb, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| x0rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 416a4029b7a8, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| x1rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, 5673678c0373 | 905d025dc026, 06098b3bf431 | 0 | True | False | False | False |
| x2rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, 798be2af9a94 | 905d025dc026 | 0 | True | False | False | False |
| x4rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, 015704594ec9, 3ab5f8fe96f4, b2fcb856104f, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| x5rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, 015704594ec9, 6c281b509549, 7b913c93bb17, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| x6rm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, 6c281b509549 |  | 0 | True | False | False | False |
| x7rm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, 015704594ec9, 066921cd681d, fed5208309e0, eecf3193581a, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| x8rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 40c92af58e6b, 4bae16e7f959, baeaf2a9d637, 015704594ec9, 117f6978b348, 28496fb1f4c5 |  | 0 | True | False | False | False |
| x9rm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 3ab5f8fe96f4, 40c92af58e6b, 834d0298c2a6, b2fcb856104f, 117f6978b348, 0f61cb2ddc7d, 066921cd681d, fed5208309e0, b88f492e2cf8, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| xarm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, e0e957b09025, 40c92af58e6b, 3dc2f2b7bb6a, 35667705e3aa | 4f5e1c0d1218 | 0 | True | False | False | False |
| xbrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 066921cd681d, fed5208309e0, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| xcrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | 905d025dc026, 06098b3bf431, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xdrm | c9c6dc2a9231, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 4bae16e7f959 |  | 0 | True | False | False | False |
| xerm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 117f6978b348 | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xfrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, ea2823e1712c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | 54c13a02b356, 905d025dc026, 06098b3bf431, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xgrm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, ea2823e1712c | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| xhrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, 015704594ec9, 066921cd681d, fed5208309e0, eecf3193581a, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 3228164a54b8 | 0 | True | False | False | False |
| xirm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, 40c92af58e6b, 015704594ec9, 066921cd681d, fed5208309e0, eecf3193581a, 117f6978b348, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| xjrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xkrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xlrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 3ab5f8fe96f4, ea2823e1712c, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 | 905d025dc026, 06098b3bf431, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xmrm | 3ab5f8fe96f4, c9c6dc2a9231, 834d0298c2a6, 117fd7eb4622, b2fcb856104f, 4d7ee9a33ecb, 0f61cb2ddc7d, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, 2ae78fe2056f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, e0e957b09025, 117f6978b348, eecf3193581a |  | 0 | True | False | False | False |
| xnrm | baeaf2a9d637, 015704594ec9, 8f4abf075ee0, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| xorm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 3ab5f8fe96f4, b2fcb856104f |  | 0 | True | False | False | False |
| xprm | 8f4abf075ee0, 5673678c0373, 4bae16e7f959, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 3228164a54b8 | 0 | True | False | False | False |
| xqrm | 28496fb1f4c5, 8f4abf075ee0, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 19c13c4d0fda, eecf3193581a, 066921cd681d, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| xrrm | 28496fb1f4c5, 8f4abf075ee0, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| xsrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| xtrm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| xurm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, e0e957b09025, 40c92af58e6b, 5673678c0373 |  | 0 | True | False | False | False |
| xvrm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 3ab5f8fe96f4, 40c92af58e6b, b2fcb856104f, 066921cd681d, fed5208309e0, b88f492e2cf8, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| xwrm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 066921cd681d, 19c13c4d0fda, fed5208309e0, 3ab5f8fe96f4, eecf3193581a, 834d0298c2a6, b2fcb856104f, e0e957b09025, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| xxrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, 40c92af58e6b, e0e957b09025 |  | 0 | True | False | False | False |
| xyrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| xzrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| y0rm | e0e957b09025, 8f4abf075ee0, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| y1rm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 2be41ffbb790 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| y2rm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 93cf506de9b3, 117f6978b348, 40c92af58e6b, 28496fb1f4c5 |  | 0 | True | False | False | False |
| y3rm | 6c281b509549, 28496fb1f4c5, 40c92af58e6b, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, e0e957b09025, a12633f5f7e7, 066921cd681d, c51a841b2c8c, fed5208309e0, 1d9d650e8a43, 117f6978b348, 25c8ea6b1577 |  | 0 | True | False | False | False |
| y4rm | 28496fb1f4c5, 7b913c93bb17, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, bc6785c7a5e2, 6c281b509549, ef00e521377c |  | 0 | True | False | False | False |
| y5rm | c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f |  | 0 | True | False | False | False |
| y6rm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, 6f8f9641288c, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e, bc3a73aad676 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| y7rm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| y8rm | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, e0e957b09025, eecf3193581a | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| y9rm | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| yarm | 3ab5f8fe96f4, 5673678c0373, 834d0298c2a6, b2fcb856104f, 28496fb1f4c5, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ybrm | 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| ycrm | c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 28496fb1f4c5, 9f41c906558f |  | 0 | True | False | False | False |
| ydrm | c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, e0e957b09025, 9f41c906558f, 5673678c0373, 28496fb1f4c5 |  | 0 | True | False | False | False |
| yerm | 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, 142bbf0bf7fb, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 54c13a02b356, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| yfrm | 2be41ffbb790, a69312fb7952, b0198fb326ef, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 2cf18159af62, 1aa50b6d640d, c2ca32745d26, 712ce9b7b11a, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| ygrm | a69312fb7952, 2be41ffbb790, b0198fb326ef, 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 61a7fe7954d9, acbeb1054bf8, 117fd7eb4622, 4d7ee9a33ecb, 85a65e824cea, f4e9bbed8b0f, 9f41c906558f, 2cf18159af62, dcef78bc22f0, 1aa50b6d640d, c2ca32745d26, 83257209aa9b, 712ce9b7b11a, 066921cd681d, b88f492e2cf8, 19c13c4d0fda, fed5208309e0, 1d9d650e8a43, d0daaadb8852, cc52e6494256, 25c8ea6b1577 | 905d025dc026 | 0 | True | False | False | False |
| yhrm | 28496fb1f4c5, 5673678c0373, 6c281b509549, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 117f6978b348, 4bae16e7f959, 3dc2f2b7bb6a, a12633f5f7e7, 35667705e3aa, 066921cd681d, c51a841b2c8c, 40c92af58e6b, fed5208309e0, 19c13c4d0fda, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| yirm | 6c281b509549, 28496fb1f4c5, 5673678c0373, 834d0298c2a6, 7b913c93bb17, 0f61cb2ddc7d, 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, ea2823e1712c, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 825d5590da69, 559de78abf9b | 0 | True | False | False | False |
| yjrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 9ea62e37e453, 9f41c906558f, 8f4abf075ee0, 976dbfd3d1e0, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ykrm | 28496fb1f4c5, 8f4abf075ee0, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| ymrm | ea2823e1712c, 8f4abf075ee0, 28496fb1f4c5, 3ab5f8fe96f4, 7b913c93bb17, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, 6c281b509549, 4bae16e7f959, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356 | 0 | True | False | False | False |
| ynrm | ea2823e1712c, 8f4abf075ee0, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, e0e957b09025 |  | 0 | True | False | False | False |
| yorm | 6c281b509549, 28496fb1f4c5, 5673678c0373, 834d0298c2a6, 7b913c93bb17, 0f61cb2ddc7d, 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, ea2823e1712c, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 825d5590da69, 559de78abf9b | 0 | True | False | False | False |
| yprm | ea2823e1712c, 3ab5f8fe96f4, 28496fb1f4c5, 834d0298c2a6, b2fcb856104f, 0f61cb2ddc7d, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 6c281b509549, 9f41c906558f, 066921cd681d, fed5208309e0, 19c13c4d0fda, 7b913c93bb17, 4bae16e7f959, 117f6978b348, 5673678c0373, 8f4abf075ee0, a682aa466866, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, cc8810821e84, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| yqrm | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 2be41ffbb790 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| yrrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 7b913c93bb17, 6c281b509549, 8f4abf075ee0, 40c92af58e6b | 54c13a02b356, 327d71fae3ff, 4f5e1c0d1218 | 0 | True | False | False | False |
| ysrm | 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, 4bae16e7f959, 117fd7eb4622, 4d7ee9a33ecb, a682aa466866, 9f41c906558f, 834d0298c2a6, bcd458bf83d9, 0f61cb2ddc7d | 3228164a54b8 | 0 | True | False | False | False |
| ytrm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, 117fd7eb4622, a682aa466866, 9f41c906558f, 834d0298c2a6, bcd458bf83d9, 0f61cb2ddc7d, 40c92af58e6b, e0e957b09025 | 3228164a54b8 | 0 | True | False | False | False |
| yurm | 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, 4bae16e7f959, 117fd7eb4622, 4d7ee9a33ecb, a682aa466866, 9f41c906558f, 40c92af58e6b, bcd458bf83d9, e0e957b09025 | 3228164a54b8 | 0 | True | False | False | False |
| yvrm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 3ab5f8fe96f4, 4bae16e7f959, b2fcb856104f, 117fd7eb4622, a682aa466866, 9f41c906558f, 40c92af58e6b, bcd458bf83d9, 3dc2f2b7bb6a | 3228164a54b8 | 0 | True | False | False | False |
| ywrm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, c51a841b2c8c, 117f6978b348, 2e64e05f3433, 19c13c4d0fda, e0e957b09025, f361a88972f6, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| yxrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 7b913c93bb17, 40c92af58e6b, 3dc2f2b7bb6a | 54c13a02b356, 905d025dc026 | 0 | True | False | False | False |
| yyrm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 066921cd681d, 6c281b509549, fed5208309e0, 19c13c4d0fda, 28496fb1f4c5, eecf3193581a, 5673678c0373 | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| yzrm | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, 8f4abf075ee0, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 1d9d650e8a43, 35667705e3aa, 25c8ea6b1577, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| z0rm | e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 117fd7eb4622, d7ec05d2d681, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| z1rm | c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, e0e957b09025, 015704594ec9 |  | 0 | True | False | False | False |
| z2rm | 28496fb1f4c5, 7b913c93bb17, 40c92af58e6b, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 6c281b509549, a12633f5f7e7, 066921cd681d, 5673678c0373, fed5208309e0, eecf3193581a, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| z3rm | 834d0298c2a6, 5673678c0373, 0f61cb2ddc7d, 3ab5f8fe96f4, 28496fb1f4c5, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, c51a841b2c8c, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| z4rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| z5rm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| z6rm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, eecf3193581a, 4bae16e7f959, 19c13c4d0fda, 117f6978b348 | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| z7rm | c9c6dc2a9231, e0e957b09025, 4d7ee9a33ecb, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| z8rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 7b913c93bb17, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| z9rm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| zarm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 117f6978b348 | 327d71fae3ff | 0 | True | False | False | False |
| zbrm | 6c281b509549, 117f6978b348, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 4bae16e7f959 |  | 0 | True | False | False | False |
| zcrm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| zdrm | 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 4d7ee9a33ecb, baeaf2a9d637, 6c281b509549, 015704594ec9, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 5673678c0373 | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| zerm | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| zfrm | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, c51a841b2c8c, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| zgrm | c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 6c281b509549, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 3dc2f2b7bb6a, 117f6978b348, eecf3193581a | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| zhrm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 5673678c0373, 117fd7eb4622, 4d7ee9a33ecb, b73241ec2198, 9f41c906558f, bf7378a0d6b3, a69ac0b746b0, 8b9b6f611374, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 3f4b74a17f67, 25c8ea6b1577 | 2b03e7d24309 | 0 | True | False | False | False |
| zirm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 5673678c0373, 117fd7eb4622, 4d7ee9a33ecb, b73241ec2198, 9f41c906558f, a69ac0b746b0, 3ab5f8fe96f4, bf7378a0d6b3, b2fcb856104f, 8b9b6f611374, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 3f4b74a17f67, 25c8ea6b1577 | d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| zjrm | 117f6978b348, e0e957b09025, 35667705e3aa, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0 |  | 0 | True | False | False | False |
| zkrm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 3f4b74a17f67, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zlrm | 35667705e3aa, e0e957b09025, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 1d9d650e8a43, 3f4b74a17f67, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zmrm | 28496fb1f4c5, 6c281b509549, 5673678c0373, 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 |  | 0 | True | False | False | False |
| znrm | 28496fb1f4c5, 6fa232d21245, 8f4abf075ee0, bcd458bf83d9, 40c92af58e6b, d326af07ba43, c9c6dc2a9231, 3ab5f8fe96f4, 4d7ee9a33ecb, b2fcb856104f, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| zorm | 28496fb1f4c5, ae1f78b6afb3, 5673678c0373, 3ab5f8fe96f4, 40f883b6ac2b, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 |  | 0 | True | False | False | False |
| zprm | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 8f4abf075ee0, e0e957b09025, 40c92af58e6b |  | 0 | True | False | False | False |
| zqrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| zr00 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, e0e957b09025 |  | 0 | True | False | False | False |
| zr01 | c9c6dc2a9231, 4d7ee9a33ecb, e0e957b09025 |  | 0 | True | False | False | False |
| zr10 | 6c281b509549, 117f6978b348, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | True | False | False | False |
| zr11 | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, e0e957b09025, 117f6978b348, 40c92af58e6b |  | 0 | True | False | False | False |
| zr12 | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 8f4abf075ee0, 117fd7eb4622, 4d7ee9a33ecb, 4bae16e7f959, 9f41c906558f, e0e957b09025, 40c92af58e6b, 117f6978b348 |  | 0 | True | False | False | False |
| zr20 | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, baeaf2a9d637, 015704594ec9, e0e957b09025 |  | 0 | True | False | False | False |
| zr21 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 35667705e3aa, e0e957b09025, 28496fb1f4c5, 40c92af58e6b |  | 0 | True | False | False | False |
| zr30 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| zr40 | c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 40c92af58e6b, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f |  | 0 | True | False | False | False |
| zr50 | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 117f6978b348, 9f41c906558f, 3ab5f8fe96f4, 066921cd681d, 834d0298c2a6, b2fcb856104f, fed5208309e0, 0f61cb2ddc7d, eecf3193581a, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| zr51 | 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 40c92af58e6b, 117fd7eb4622, 4d7ee9a33ecb, 117f6978b348, 9f41c906558f, baeaf2a9d637, d0daaadb8852, 3ab5f8fe96f4, 015704594ec9, cc52e6494256, b2fcb856104f, 066921cd681d, 00467dc3027e, fed5208309e0, eecf3193581a, 19c13c4d0fda |  | 0 | True | False | False | False |
| zr60 | 28496fb1f4c5, 8f4abf075ee0, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 117f6978b348, e0e957b09025 |  | 0 | True | False | False | False |
| zr70 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 77c86cd0c17a, 6aa92787433c, 2445a0dfc2f6, bf729f1b5ed0 |  | 0 | True | False | False | False |
| zr80 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 77c86cd0c17a, 6aa92787433c, 2445a0dfc2f6, bf729f1b5ed0, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| zra0 | c9c6dc2a9231, e0e957b09025, 117fd7eb4622, 4d7ee9a33ecb, 6c281b509549, 9f41c906558f, baeaf2a9d637, 7b913c93bb17, 015704594ec9, 3ab5f8fe96f4, 28496fb1f4c5, b2fcb856104f, 834d0298c2a6, 5673678c0373, 0f61cb2ddc7d, 117f6978b348, ba1f116c4be9 |  | 0 | True | False | False | False |
| zra1 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| zra2 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, baeaf2a9d637, 015704594ec9, 40c92af58e6b, 8f4abf075ee0, 5673678c0373, 4bae16e7f959, 28496fb1f4c5, a682aa466866 |  | 0 | True | False | False | False |
| zri0 | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 3f4b74a17f67, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrrm | 28496fb1f4c5, 6fa232d21245, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, d326af07ba43, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f |  | 0 | True | False | False | False |
| zrs0 |  |  | 0 | True | False | False | False |
| zrs1 |  |  | 0 | True | False | False | False |
| zrs2 |  |  | 0 | True | False | False | False |
| zrs3 |  |  | 0 | True | False | False | False |
| zrs4 |  |  | 0 | True | False | False | False |
| zrs5 |  |  | 0 | True | False | False | False |
| zrs6 |  |  | 0 | True | False | False | False |
| zsrm | c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 117f6978b348 | 327d71fae3ff | 0 | True | False | False | False |
| ztrm | c9c6dc2a9231, 6c281b509549, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 28496fb1f4c5, 066921cd681d, 19c13c4d0fda, fed5208309e0, 3ab5f8fe96f4, eecf3193581a, 834d0298c2a6, b2fcb856104f, 40c92af58e6b, 0f61cb2ddc7d, 117f6978b348 | 327d71fae3ff | 0 | True | False | False | False |
| zurm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 7b913c93bb17, 28496fb1f4c5, 066921cd681d, 5673678c0373, fed5208309e0, 19c13c4d0fda, 8f4abf075ee0, eecf3193581a, 117f6978b348 | 327d71fae3ff | 0 | True | False | False | False |
| zvrm | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, 8a1d6deba766, a966d07dc322 |  | 0 | True | False | False | False |
| zwrm | 28496fb1f4c5, 6c281b509549, 5673678c0373, 8f4abf075ee0, 4bae16e7f959, a682aa466866, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e, 117f6978b348, eecf3193581a, e0e957b09025 |  | 0 | True | False | False | False |
| zxrm | e0e957b09025, 117f6978b348, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| zyrm | e0e957b09025, 28496fb1f4c5, 40c92af58e6b, 5673678c0373, 117f6978b348, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| zzrm | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f |  | 0 | True | False | False | False |
| cvrn | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 40c92af58e6b | 06098b3bf431, 905d025dc026, 4f5e1c0d1218 | 0 | True | False | False | False |
| d8rn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| dcrn | 117f6978b348, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| dfrn | 28496fb1f4c5, ef00e521377c, 5673678c0373, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dgrn | e0e957b09025, 8f4abf075ee0, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| dhrn | e0e957b09025, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f |  | 0 | True | False | False | False |
| dmrn | 8f4abf075ee0, e0e957b09025, 4bae16e7f959, 6c281b509549, baeaf2a9d637, 28496fb1f4c5, 5673678c0373, 015704594ec9, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, f7b6f0f21335, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dsrn | 5673678c0373, 28496fb1f4c5, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dwrn | 834d0298c2a6, 0f61cb2ddc7d, 834d0298c2a6, 0f61cb2ddc7d, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| dbrn | 5673678c0373, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| cxrn | c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 40c92af58e6b, 6c281b509549, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, 19c13c4d0fda, 4bae16e7f959, eecf3193581a, a682aa466866 |  | 0 | True | False | False | False |
| cyrn | 5673678c0373, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| anrn | 5673678c0373, 6c281b509549, 28496fb1f4c5, 8f4abf075ee0, 4bae16e7f959, a682aa466866, 834d0298c2a6, 40c92af58e6b, 0f61cb2ddc7d, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, a12633f5f7e7, e0e957b09025, 117f6978b348, 9883c4c11c1b, eecf3193581a, 066921cd681d, 19c13c4d0fda, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| ekrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, ef00e521377c, e0e957b09025, 6c281b509549, 28496fb1f4c5, 7b913c93bb17, adbc6ec7023d | 905d025dc026, b49407ca4efb, 54c13a02b356, 327d71fae3ff | 0 | True | False | False | False |
| eorn | 7db56e9a5841, 5cd238832057, c2ca32745d26, 712ce9b7b11a, 747268a767c1, 117f6978b348, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, 1420f18c4e7c, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| c7rn | 3ab5f8fe96f4, 5673678c0373, b2fcb856104f, 834d0298c2a6, 28496fb1f4c5, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| c8rn | 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, 6c281b509549, 4bae16e7f959, 7b913c93bb17, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, fed5208309e0, 117f6978b348, 19c13c4d0fda, eecf3193581a, e0e957b09025, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| esrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, ef00e521377c, e0e957b09025, 6c281b509549, 28496fb1f4c5, 7b913c93bb17, adbc6ec7023d | 176c6f31715f | 0 | True | False | False | False |
| etrn | 1c485e495380, e0e957b09025, 8f4abf075ee0, 3af051d36602, e9ada0a12c3f, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, 117f6978b348, 0f61cb2ddc7d, 19c13c4d0fda, 3ab5f8fe96f4, 9b1697fdff0d, fed5208309e0, b2fcb856104f, 747268a767c1 |  | 0 | True | False | True | False |
| eurn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218, 3228164a54b8 | 0, 1 | True | False | False | False |
| evrn | 3ab5f8fe96f4, b2fcb856104f, 8a9f00d9b56b, 598c167cdd86, 77c86cd0c17a, 6aa92787433c, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| exrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 54c13a02b356, 905d025dc026, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| eyrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 8f4abf075ee0, e0e957b09025, 0f61cb2ddc7d, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 54c13a02b356, 905d025dc026, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | False | False |
| f3rn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, 1d9d650e8a43, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| f4rn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 3ab5f8fe96f4, e0e957b09025, 015704594ec9, b2fcb856104f, 066921cd681d, 19c13c4d0fda, eecf3193581a, 1d9d650e8a43, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| fcrn | 117f6978b348, 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 3ab5f8fe96f4, 19c13c4d0fda, eecf3193581a, b2fcb856104f, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | False | False | False | False |
| ffrn | c9c6dc2a9231, 117fd7eb4622, e0e957b09025, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 015704594ec9 |  | 0 | True | False | False | False |
| fprn | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 54c13a02b356, 327d71fae3ff, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| ftrn | 290d9910a4d6, 1719150dc50c, bc0701329d6d, 8220cfc68b4c, c4aa46ccfc61, fcdb3da2d700, 002aebdb0a22, a38b6b922f03 | c47e1167bb98, 12629335d2cb | 0 | True | True | False | False |
| furn | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218 | 0 | True | False | False | False |
| g1rn | 40c92af58e6b, 6c281b509549, ef00e521377c, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, adbc6ec7023d, 9f41c906558f, 4d7ee9a33ecb, c08507546144, c2b08d0842de, 5673678c0373, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, b49407ca4efb, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8, d29e676e4bc9, 2b03e7d24309 | 0 | True | False | True | False |
| g2rn | adbc6ec7023d, 6c281b509549, ef00e521377c, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 216754480545, 90483ec7049a, e0e957b09025, 5673678c0373, 8f4abf075ee0, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 6cf2073c55b5 | 0 | True | True | True | False |
| g5rn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, a682aa466866, a12633f5f7e7, 066921cd681d, 40c92af58e6b, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| g6rn | 5673678c0373, 28496fb1f4c5, 6c281b509549, 8f4abf075ee0, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 905d025dc026, 54c13a02b356, 4f5e1c0d1218 | 0 | False | False | False | False |
| g7rn | 5673678c0373, 28496fb1f4c5, 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 905d025dc026 | 0 | False | False | False | False |
| g9rn | 77c86cd0c17a, 8f4abf075ee0, 6aa92787433c, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 066921cd681d, 117f6978b348, b2fcb856104f, 19c13c4d0fda, 2445a0dfc2f6, eecf3193581a, fed5208309e0, bf729f1b5ed0, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 905d025dc026, 54c13a02b356, 4f5e1c0d1218 | 0 | False | False | False | False |
| garn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 8f4abf075ee0, e0e957b09025, 40c92af58e6b | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218 | 0 | False | False | False | False |
| gbrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, e0e957b09025, 8f4abf075ee0 |  | 0 | False | False | False | False |
| gcrn | baeaf2a9d637, 015704594ec9, e0e957b09025 |  | 0 | False | False | False | False |
| gern | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, 8f4abf075ee0, c5f845fc1b8c, 4bae16e7f959 | 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | False | False | False | False |
| gfrn | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, 6c281b509549, 5673678c0373, 28496fb1f4c5, adbc6ec7023d, 90483ec7049a, 40c92af58e6b, 117f6978b348 | 06098b3bf431, 905d025dc026, 54c13a02b356 | 0 | False | False | False | False |
| glrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 6c281b509549, 117f6978b348, 5673678c0373, 28496fb1f4c5 | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218 | 0 | True | False | False | False |
| gnrn | 5673678c0373, 117f6978b348, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | False | False | False | False |
| grrn | 6c281b509549, 117f6978b348, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b |  | 0 | False | False | False | False |
| gxrn | 1791ad47505a, 26dec4df5a23 |  | 0 | False | False | False | False |
| gzrn | c9c6dc2a9231, 4d7ee9a33ecb, 40c92af58e6b, e0e957b09025 |  | 0 | False | False | False | False |
| hcrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, 015704594ec9, 4bae16e7f959, 7b913c93bb17, 28496fb1f4c5 |  | 0 | True | False | False | False |
| hnrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37 | 905d025dc026, 06098b3bf431 | 0 | True | True | True | False |
| hqrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37, 066921cd681d, fed5208309e0, 19c13c4d0fda | 905d025dc026, 06098b3bf431 | 0 | True | True | True | False |
| hsrn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | True | False |
| hurn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d, 066921cd681d, fed5208309e0, 19c13c4d0fda | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | True | False |
| j2rn | a08b869dac7f, 8f924ee61014, fa348b746fa6, 9ed1afa85901, 1791ad47505a, 26dec4df5a23, 269880b9371b, 0e6d9419b849, fc6b2ae62c27, f58be5dcd1fe, 0e0ea393ef1e, 10511feca46c, e73cc3cccaca, 1e7a055c5cb4, 0cbc9c0946d9, b3d7c4c9f76b |  | 0 | False | False | False | False |
| j5rn | 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jbrn | 117f6978b348, 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 4bae16e7f959, 19c13c4d0fda, eecf3193581a, a682aa466866, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| jcrn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 5d879bb26b68, b7f6aa4c400e, 42bfa59734d3, 8f4abf075ee0, 117f6978b348, 40c92af58e6b | 54c13a02b356, 06098b3bf431, 905d025dc026, 4f5e1c0d1218 | 0 | True | False | False | False |
| jdrn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 3ab5f8fe96f4, 4d7ee9a33ecb, 9f41c906558f, b2fcb856104f, 5d879bb26b68, b7f6aa4c400e, 42bfa59734d3, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 06098b3bf431, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| jprn | 5673678c0373, 8f4abf075ee0, 3ab5f8fe96f4, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0, 1 | True | False | False | False |
| jtrn | 5673678c0373, 28496fb1f4c5, 7b913c93bb17, e0e957b09025, 8f4abf075ee0, 4bae16e7f959, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f |  | 0 | True | False | False | False |
| jurn | 28496fb1f4c5, 5673678c0373, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, 066921cd681d, 19c13c4d0fda, fed5208309e0, eecf3193581a, e0e957b09025, 117f6978b348, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| k6rn | e77a18d88f25, 96c416888e37, 18368dd0106a, e0e957b09025 |  | 0 | True | False | False | False |
| kbrn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 2445a0dfc2f6, 117fd7eb4622, 4d7ee9a33ecb, bf729f1b5ed0, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0, 1 | True | True | False | False |
| kcrn | 6c281b509549, 7b913c93bb17, 8f4abf075ee0, 4bae16e7f959, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, 19c13c4d0fda, e0e957b09025, eecf3193581a, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| kgrn | 6c281b509549, 7b913c93bb17, 28496fb1f4c5, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 327d71fae3ff, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| klrn | 290d9910a4d6, 1719150dc50c, e0e957b09025 |  | 0 | True | False | False | False |
| kmrn | 290d9910a4d6, 1719150dc50c |  | 0 | True | False | False | False |
| kprn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 6c281b509549, 5673678c0373, 28496fb1f4c5 | 905d025dc026, 06098b3bf431, 54c13a02b356 | 0 | True | True | False | False |
| kqrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 117f6978b348, 5673678c0373, 28496fb1f4c5 | 905d025dc026, 06098b3bf431 | 0 | True | True | False | False |
| krrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 06098b3bf431, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| ksrn | 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 117f6978b348, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 905d025dc026, 4f5e1c0d1218 | 0 | True | True | False | False |
| kwrn | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 8f4abf075ee0, 4bae16e7f959, baeaf2a9d637, 015704594ec9, 7b913c93bb17, 28496fb1f4c5 | 327d71fae3ff, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| l2rn | 28496fb1f4c5, e0e957b09025, 5673678c0373, 2169603a2ccb, cd12add2435e, 8f4abf075ee0, 3261d5acee66, 41ca19922c41, 117f6978b348, c9c6dc2a9231, 117fd7eb4622, bd888e1de887, 4d7ee9a33ecb, 9f41c906558f, a12633f5f7e7, 3df9197ac546, 066921cd681d, fed5208309e0, 4674d65a3f82, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | True | False | False | False |
| l7rn | 3dc2f2b7bb6a, 117f6978b348, 747268a767c1, 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 3ab5f8fe96f4, 19c13c4d0fda, eecf3193581a, b2fcb856104f, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | False | False | False | False |
| l9rn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218, 3228164a54b8 | 0, 1 | True | True | False | False |
| larn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, e0e957b09025, 015704594ec9, 6c281b509549, 5673678c0373, 28496fb1f4c5 | 905d025dc026, 06098b3bf431, 54c13a02b356 | 0 | True | True | False | False |
| lbrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 6c281b509549, 117f6978b348, 5673678c0373, 28496fb1f4c5 | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218 | 0 | True | True | False | False |
| lcrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 06098b3bf431, 54c13a02b356, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| ldrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 834d0298c2a6, 066921cd681d, e0e957b09025, 0f61cb2ddc7d, fed5208309e0, 3ab5f8fe96f4, 19c13c4d0fda, eecf3193581a, b2fcb856104f, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431 | 0 | True | True | False | False |
| lern | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, e0e957b09025, 8f4abf075ee0, 40c92af58e6b | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0, 1 | True | True | False | False |
| lkrn | 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 015704594ec9, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 40c92af58e6b, a12633f5f7e7, 066921cd681d, 117f6978b348, fed5208309e0, eecf3193581a, e0e957b09025, 19c13c4d0fda, d0daaadb8852, cc52e6494256, 00467dc3027e | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218, 3228164a54b8 | 0, 1 | True | True | False | False |
| llrn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 06098b3bf431, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| m4rn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 5673678c0373, e0e957b09025, 28496fb1f4c5, 8f4abf075ee0 | 905d025dc026, 06098b3bf431, 4f5e1c0d1218 | 0 | True | False | False | False |
| m5rn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, baeaf2a9d637, 8f4abf075ee0, e0e957b09025, 015704594ec9, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 06098b3bf431, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| m6rn | 117f6978b348, 6c281b509549, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 2169603a2ccb, 8f4abf075ee0, e0e957b09025, 3261d5acee66, 4bae16e7f959, 066921cd681d, 19c13c4d0fda, eecf3193581a, fed5208309e0, d0daaadb8852, cc52e6494256, 00467dc3027e | 54c13a02b356, 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | False | False | False |
| m7rn | 2baeb8064f93, 4acd433d5358, b867d983cdde, 362b90931207, e0e957b09025, 117f6978b348, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 6c281b509549 | 54c13a02b356, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
| m9rn | 117f6978b348, 8f4abf075ee0, 5673678c0373, 28496fb1f4c5, c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 2169603a2ccb, 066921cd681d, e0e957b09025, 3261d5acee66, fed5208309e0, cd12add2435e, 19c13c4d0fda, eecf3193581a, 41ca19922c41, d0daaadb8852, cc52e6494256, 00467dc3027e |  | 0 | False | False | False | False |
| marn | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 5673678c0373, 28496fb1f4c5, 066921cd681d, 8f4abf075ee0, fed5208309e0, eecf3193581a, 4bae16e7f959, 19c13c4d0fda, 117f6978b348 | 06098b3bf431, 905d025dc026, 4f5e1c0d1218, 3228164a54b8 | 0, 1 | True | True | False | False |
| mbrn | c9c6dc2a9231, 117fd7eb4622, 40c92af58e6b, 9f41c906558f, 4d7ee9a33ecb, 8f4abf075ee0, e0e957b09025, 6c281b509549, 117f6978b348, 5673678c0373, 28496fb1f4c5 | 905d025dc026, 06098b3bf431, 54c13a02b356, 4f5e1c0d1218 | 0 | True | False | False | False |
| mdrn | c9c6dc2a9231, 4d7ee9a33ecb, d83949b70674, 117fd7eb4622, 9f41c906558f, 3ab5f8fe96f4, b2fcb856104f, d9be9bdbf73f, 834d0298c2a6, 0f61cb2ddc7d | c47e1167bb98, 12629335d2cb | 0 | True | True | False | False |
| mhrn |  |  | 0 | True | False | False | False |
| zrs0/b8tt | c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 40c92af58e6b, 28496fb1f4c5, fed5208309e0, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrs0/b9tt | 40c92af58e6b, e0e957b09025, 35667705e3aa, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 8f4abf075ee0, 9f41c906558f, fed5208309e0, a4c14d2529e4, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrs1/zri0 | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 3f4b74a17f67, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrs1/i4rm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 3ab5f8fe96f4, 117fd7eb4622, 4d7ee9a33ecb, b2fcb856104f, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrs1/i5rm | 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 28496fb1f4c5, 117fd7eb4622, 4d7ee9a33ecb, 5673678c0373, 9f41c906558f, 3ab5f8fe96f4, 8f4abf075ee0, 834d0298c2a6, b2fcb856104f, 4bae16e7f959, 0f61cb2ddc7d, a12633f5f7e7, 066921cd681d, 35667705e3aa, fed5208309e0, 1d9d650e8a43, 8a49ddf1e409, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrs1/d7rm | 117f6978b348, 35667705e3aa, e0e957b09025, c9c6dc2a9231, baeaf2a9d637, 117fd7eb4622, 4d7ee9a33ecb, 40c92af58e6b, 9f41c906558f, 5673678c0373, 8f4abf075ee0, 28496fb1f4c5, a12633f5f7e7, 066921cd681d, fed5208309e0, 1d9d650e8a43, cac4b66cd7a7, 25c8ea6b1577 | 2cf18159af62 | 0 | True | False | False | False |
| zrs2/zr00 | c9c6dc2a9231, 4d7ee9a33ecb, 117fd7eb4622, 9f41c906558f, e0e957b09025 |  | 0 | True | False | False | False |
| zrs2/zr01 | c9c6dc2a9231, 4d7ee9a33ecb, e0e957b09025 |  | 0 | True | False | False | False |
| zrs3/aprm | a69312fb7952, 2be41ffbb790, b0198fb326ef, 117f6978b348, e0e957b09025, 40c92af58e6b, c9c6dc2a9231, 61a7fe7954d9, acbeb1054bf8, 117fd7eb4622, 4d7ee9a33ecb, 85a65e824cea, f4e9bbed8b0f, 9f41c906558f, 2cf18159af62, dcef78bc22f0, 1aa50b6d640d, c2ca32745d26, 83257209aa9b, 712ce9b7b11a, 066921cd681d, b88f492e2cf8, aa28f346c0b2, fed5208309e0, 1d9d650e8a43, d0daaadb8852, cc52e6494256, 25c8ea6b1577 |  | 0 | True | False | False | False |
| zrs3/aqrm | 2be41ffbb790, 27175a0eb1db, 401fefccde6c, c9c6dc2a9231, 117fd7eb4622, 4d7ee9a33ecb, 9f41c906558f, 2cf18159af62, 1aa50b6d640d, c2ca32745d26, 712ce9b7b11a, e0e957b09025, 8a1d6deba766, 117f6978b348 |  | 0 | True | False | False | False |
| zrs4/mdrm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 3ab5f8fe96f4, 8a1d6deba766, b2fcb856104f, 834d0298c2a6, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| zrs4/merm | c9c6dc2a9231, 8f4abf075ee0, 4d7ee9a33ecb, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 3ab5f8fe96f4, 8a1d6deba766, b2fcb856104f |  | 0 | True | False | False | False |
| zrs4/mfrm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 834d0298c2a6, b2fcb856104f, 0f61cb2ddc7d, 8f4abf075ee0, 4bae16e7f959 |  | 0 | True | False | False | False |
| zrs4/mgrm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, 8f4abf075ee0, b2fcb856104f, 4bae16e7f959 |  | 0 | True | False | False | False |
| zrs5/j6rm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37 |  | 0 | True | False | False | False |
| zrs5/mcrm | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, e0e957b09025, b2fcb856104f, 8f4abf075ee0, 747268a767c1, aae5ac3a0d37 |  | 0 | True | False | False | False |
| zrs5/corn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| zrs6/cprn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37 |  | 0 | True | False | False | False |
| zrs6/corn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d |  | 0 | True | False | False | False |
| mhrn/hnrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37 | 905d025dc026, 06098b3bf431 | 0 | True | True | True | False |
| mhrn/hqrn | c9c6dc2a9231, 117fd7eb4622, 8a1d6deba766, 9f41c906558f, 4d7ee9a33ecb, 28496fb1f4c5, e0e957b09025, 5673678c0373, 117f6978b348, 747268a767c1, aae5ac3a0d37, 066921cd681d, fed5208309e0, 19c13c4d0fda | 905d025dc026, 06098b3bf431 | 0 | True | True | True | False |
| mhrn/hsrn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | True | False |
| mhrn/hurn | e0e957b09025, 28496fb1f4c5, 8f4abf075ee0, 5673678c0373, c9c6dc2a9231, 117fd7eb4622, 4bae16e7f959, 9f41c906558f, 4d7ee9a33ecb, 3ab5f8fe96f4, b867d983cdde, 117f6978b348, b2fcb856104f, 362b90931207, 834d0298c2a6, 747268a767c1, aae5ac3a0d37, 0f61cb2ddc7d, 066921cd681d, fed5208309e0, 19c13c4d0fda | 905d025dc026, 06098b3bf431, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | True | False |
| mhrn/m7rn | 2baeb8064f93, 4acd433d5358, b867d983cdde, 362b90931207, e0e957b09025, 117f6978b348, c9c6dc2a9231, 4d7ee9a33ecb, bd888e1de887, 117fd7eb4622, 9f41c906558f, 8f4abf075ee0, 4bae16e7f959, 6c281b509549 | 54c13a02b356, 4f5e1c0d1218, 3228164a54b8 | 0 | True | True | False | False |
<!-- /generated -->

</details>

#### Timing

Sustained controls first send after 100 ms and refresh every 100 ms. A short
press sends on down and releases on up. Long gestures have a 3 second threshold;
a short-and-long press emits its short command on an early release and its long
command after the threshold, with no invented release frame for either callback.
Only sustained controls support renewable holds. Cancellation releases an
attempted short or sustained command with a fresh cleanup event.

Writes are serialized with at least the app's 100 ms queue cadence. This prevents
the Android asynchronous queue's overlapping writes. Connection setup subscribes
before ExitLimit and settings queries. Products with alarm choices synchronize
time before the clock/light query schedule, whose probes are 300 ms apart.
A stale callback cannot write to a replacement connection.

#### Notifications

The status sensor exposes declared typed event state and protocol rejections.
Common replies cover capabilities, lock, version, numeric motor feedback,
massage, music/vibration and diagnostics. Extended replies cover motor travel,
massage, white/RGB light, alarm records, anti-snore, lock, checks and press mode.
Feedback without a registered app consumer never rewrites local side or gesture
selection. Blanket replies retain their empty source objects rather than invented
populated settings.

Framed records assemble by length and checksum. Legacy packets retain their
source header splitting behavior. Malformed lengths and truncated payloads are
rejected safely. Partial records expire rather than leaking into another session.

MM and SXB keep separate ordinary receive state and report accumulation. Ordinary
responses decode UTF-8; gzip reports use the source byte-to-character mapping.
Ordinary response length uses the low length byte, while SXB report fragments
strip each header and MM report fragments retain their complete payload. Invalid
or oversized compressed data is rejected. Live values and day/month reports are
exposed without assigning clinical meaning.

#### Services

`adjustable_bed.mlily` exposes `single`, `cancel_single`, `repeat`, `toggle`,
`delete`, `alarms`, `sync`, `light_color`, `light_duration`, `light_off`,
`massage_timer` and the independent sleep operations. The status sensor's event
attributes include exact alarm IDs and six-byte records. Select an alarm action
ID from this product's alarm column, never an opcode from a different product.

The clock reply and a nonempty alarm getter admit scheduling. Repeat products
use the repeat page; other products use a single countdown. A single save writes
low minutes then high minutes/action. Only its acknowledgement changes the saved
active alarm. Repeating saves encode enabled in bit 0 and Monday through Sunday
in bits 7 through 1; no weekdays means once. Repeat saves require an explicit
`alarm_id` from 1 through 7, or an observed `alarm_record` for an edit. The app
chooses its first missing ID from its local list; HA requires the intended ID
because individual replies have no count or completion marker. A cold, partial
or stale cache cannot prove that a slot is unused. An explicit ID writes that
slot and may replace its existing alarm. Editing an observed `alarm_record`
retains its ID and schedule; choosing an action overrides its recovered mode.
Unknown recovered modes need an explicit choice. List replies deduplicate all
six fields; escalation replaces only the first matching ID. Save/delete refresh
the list after 200 ms; toggle preserves all record fields except enabled.

Sleep operations are `sync`, `part`, `time`, `realtime`, `report`, `anti_snore`,
`sensitivity` and `init`. MM supports sync, part, realtime and reports; SXB also
supports time, anti-snore, sensitivity query and initialization. Part and report
arguments remain explicit caller inputs. Use `left` and `right` for the SXB
anti-snore operands. Reports serialize metadata and continuation before receipt;
live polling stops for the transfer. Stop cancels local sleep work without a
motor STOP packet. Live monitoring polls every 2 seconds and reconnects while
requested. Native session identity prevents cross-device report and command races.

#### Evidence

APK Protocol Audit row159, MLILY Control 5.0.2, artifact set
`3f69a06f281b6c1e79c3db4aca9639cbf504b668ccb2765dfa0a39850b4f4c51`.
The accepted reconciliation002 and independent audit001 establish the exact
catalog, corrected framing and alarm closure. Literal vectors are in
`tests/fixtures/mlily/`; all normal bed frames use the Richmat codec and sleep
JSON uses the shared sleep-envelope codec. Static evidence does not establish
physical effects, over-air delivery, alarm accuracy or persistence.


### Richmat 4.2.0

**App:** [Richmat](https://play.google.com/store/apps/details?id=com.richmat.richmat) 4.2.0 (42006), `com.richmat.richmat`

**Status:** ❓ Needs testing. Complete static protocol support; hardware remains unverified.

#### Setup

Choose **Richmat 4.2.0 app** and the exact product code. The searchable product
question lists the app's manual products first and labels the additional restored
products explicitly. QR text is a product code, not a Bluetooth address. Product
identity, protocol version and selected physical side remain independent.
The case-sensitive scan uses advertised-name substrings; shared services never
select an app or product. Home Assistant connects through its normal adapter or
Bluetooth proxy selection. No PIN or bonding handshake is defined by this app.

The bed's sleep-name reply appears in the status sensor's `events.sleep_device`.
Add that physical device separately as **Richmat 4.2.0 sleep device**, choosing its
RM-/MM or HJ-/public session. The restored demo options retain the old library's
service selection. Each entry owns its own link, sequence and cancellation; a
sleep-device reply never changes the main bed's product. Use the exact advertised
name to identify it. This replaces the Android global scanner and singleton
connection owners with independent HA entries.

#### Controls

The product and observed protocol version choose movement pairs, presets and
save buttons, massage controls and the angle/intensity sliders. Preset saving
uses its separate button with the catalog's long opcode, without a save hold.
Motor reset, light, synchronization and box-lock controls keep their own product
gates. Catalog declarations without a live control binding do not create bed entities.

<!-- generated:richmat-app-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Descriptor | Control | Short (left) | Save / long (left) |
|---|---|---|---|
| `caf351` | None | `6E 01 00 00 6F` | `6E 01 00 00 6F` |
| `caf3d1` | Stop | `6E 01 00 6E DD` | `6E 01 00 00 6F` |
| `caf451` | Bed Light Close | `6E 01 00 75 E4` | `6E 01 00 00 6F` |
| `caf4d1` | Exit Limit | `6E 02 01 00 71` | `6E 02 01 00 71` |
| `caf551` | Send Stop Detection | `6E 01 00 00 6F` | `6E 01 00 00 6F` |
| `caf5d1` | Send Start Detection | `6E 88 C2 10 C8` | `6E 88 C2 00 B8` |
| `caf651` | Music Switch Sound Track | `6E 01 00 C4 33` | `6E 01 00 00 6F` |
| `caf6d1` | Music Blue Tooth Switch | `6E 01 00 D8 47` | `6E 01 00 00 6F` |
| `caf751` | Control Box Lock | `6E 01 00 84 F3` | `6E 01 00 84 F3` |
| `caf7d1` | Relieve Zero Gravity Setting | `6E 01 00 62 D1` | `6E 01 00 00 6F` |
| `caf851` | Memory Position3 | `6E 01 00 30 9F` | `6E 01 00 2D 9C` |
| `caf8d1` | Memory Position2 | `6E 01 00 2F 9E` | `6E 01 00 2C 9B` |
| `caf951` | Memory Position1 | `6E 01 00 2E 9D` | `6E 01 00 2B 9A` |
| `caf9d1` | T V Position | `6E 01 00 58 C7` | `6E 01 00 64 D3` |
| `cafa51` | Zero Gravity | `6E 01 00 45 B4` | `6E 01 00 66 D5` |
| `cafad1` | Lounge Position | `6E 01 00 59 C8` | `6E 01 00 65 D4` |
| `cafb51` | Anti Snoring | `6E 01 00 46 B5` | `6E 01 00 69 D8` |
| `cafbd1` | Reading Position | `6E 01 00 F2 61` | `6E 01 00 F3 62` |
| `cafc51` | Lumbar Memory Position | `6E 01 00 91 00` | `6E 01 00 92 01` |
| `cafcd1` | Relieve Zero Gravity Setting | `6E 01 00 62 D1` | `6E 01 00 00 6F` |
| `cafd51` | Massage30 Minute Up And Down | `6E 01 00 90 FF` | `6E 01 00 00 6F` |
| `cafdd1` | Massage15 Minute Up And Down | `6E 01 00 76 E5` | `6E 01 00 00 6F` |
| `cafe51` | Release Pressur Position | `6E 01 00 C5 34` | `6E 01 00 00 6F` |
| `cafed1` | Help Get Up Position | `6E 01 00 3D AC` | `6E 01 00 F8 67` |
| `caff51` | Yoga Position | `6E 01 00 F0 5F` | `6E 01 00 F1 60` |
| `caffd1` | Relax Position | `6E 01 00 70 DF` | `6E 01 00 95 04` |
| `cb0051` | Memory Position4 | `6E 01 00 B2 21` | `6E 01 00 B3 22` |
| `cb00d1` | Help Get Up | `6E 01 00 3D AC` | `6E 01 00 00 6F` |
| `cb0151` | Yoga Position | `6E 01 00 6B DA` | `6E 01 00 6A D9` |
| `cb01d1` | Sleep Position | `6E 01 00 8E FD` | `6E 01 00 8F FE` |
| `cb0251` | Yoga Position | `6E 01 00 30 9F` | `6E 01 00 2D 9C` |
| `cb02d1` | Timing Flat Position | `6E 01 00 FE 6D` | `6E 01 00 00 6F` |
| `cb0351` | Zero Gravity2 | `6E 01 00 6B DA` | `6E 01 00 6A D9` |
| `cb03d1` | Side Sleep Position | `6E 01 00 BA 29` | `6E 01 00 BB 2A` |
| `cb0451` | Coaxing Sleep Mode | `6E 01 00 86 F5` | `6E 01 00 89 F8` |
| `cb04d1` | Lounge Position | `6E 01 00 59 C8` | `6E 01 00 65 D4` |
| `cb0551` | T V Position | `6E 01 00 58 C7` | `6E 01 00 64 D3` |
| `cb05d1` | Zero Gravity | `6E 01 00 45 B4` | `6E 01 00 66 D5` |
| `cb0651` | Help Get Up Position | `6E 01 00 3D AC` | `6E 01 00 F8 67` |
| `cb06d1` | Relieve Snore Setting | `6E 01 00 CB 3A` | `6E 01 00 00 6F` |
| `cb0751` | Deep Sleep Position | `6E 01 00 F6 65` | `6E 01 00 F7 66` |
| `cb07d1` | Massage15 Minute Spine Guard | `6E 01 00 76 E5` | `6E 01 00 00 6F` |
| `cb0851` | Memory Position5 | `6E 01 00 F4 63` | `6E 01 00 F5 64` |
| `cb08d1` | Yoga Position | `6E 01 00 6B DA` | `6E 01 00 6A D9` |
| `cb0951` | Coaxing Sleep Mode3 | `6E 01 00 88 F7` | `6E 01 00 00 6F` |
| `cb09d1` | Coaxing Sleep Mode2 | `6E 01 00 87 F6` | `6E 01 00 00 6F` |
| `cb0a51` | Help Sleep Mode1 | `6E 01 00 86 F5` | `6E 01 00 00 6F` |
| `cb0ad1` | Massage30 Minute Timer | `6E 01 00 61 D0` | `6E 01 00 00 6F` |
| `cb0b51` | Massage20 Minute Timer | `6E 01 00 63 D2` | `6E 01 00 00 6F` |
| `cb0bd1` | Massage10 Minute Timer | `6E 01 00 5F CE` | `6E 01 00 00 6F` |
| `cb0c51` | Memory Position1 | `6E 01 00 76 E5` | `6E 01 00 2B 9A` |
| `cb0cd1` | Help Sleep Mode1 | `6E 01 00 86 F5` | `6E 01 00 00 6F` |
| `cb0d51` | Coaxing Sleep Mode | `6E 01 00 76 E5` | `6E 01 00 89 F8` |
| `cb0dd1` | Coaxing Sleep Mode | `6E 01 00 C5 34` | `6E 01 00 89 F8` |
| `cb0e51` | Wake Up | `6E 01 00 85 F4` | `6E 01 00 00 6F` |
| `cb0ed1` | Coaxing Sleep Mode | `6E 01 00 86 F5` | `6E 01 00 89 F8` |
| `cb0f51` | Head And Foot All Up | `6E 01 00 23 92` | `6E 01 00 00 6F` |
| `cb0fd1` | Foot Up And Head Down | `6E 01 00 22 91` | `6E 01 00 00 6F` |
| `cb1051` | Head Up And Foot Down | `6E 01 00 21 90` | `6E 01 00 00 6F` |
| `cb10d1` | Motor Reset2 | `6E 01 00 6C DB` | `6E 01 00 00 6F` |
| `cb1151` | Head Up And Foot Stop | `6E 01 00 3D AC` | `6E 01 00 00 6F` |
| `cb11d1` | Wake Up Position | `6E 01 00 93 02` | `6E 01 00 94 03` |
| `cb1251` | Relax Position | `6E 01 00 70 DF` | `6E 01 00 95 04` |
| `cb12d1` | Un Wind Position | `6E 01 00 8C FB` | `6E 01 00 8D FC` |
| `cb1351` | Tile Down | `6E 01 00 44 B3` | `6E 01 00 00 6F` |
| `cb13d1` | Tile Up | `6E 01 00 43 B2` | `6E 01 00 00 6F` |
| `cb1451` | Bed Light | `6E 01 00 3C AB` | `6E 01 00 00 6F` |
| `cb14d1` | Motor Reset | `6E 01 00 31 A0` | `6E 01 00 00 6F` |
| `cb1551` | Pillow Down | `6E 01 00 40 AF` | `6E 01 00 00 6F` |
| `cb15d1` | Pillow Up | `6E 01 00 3F AE` | `6E 01 00 00 6F` |
| `cb1651` | Lumbar Down | `6E 01 00 42 B1` | `6E 01 00 00 6F` |
| `cb16d1` | Lumbar Up | `6E 01 00 41 B0` | `6E 01 00 00 6F` |
| `cb1751` | Foot Down | `6E 01 00 27 96` | `6E 01 00 00 6F` |
| `cb17d1` | Foot Up | `6E 01 00 26 95` | `6E 01 00 00 6F` |
| `cb1851` | Head Down | `6E 01 00 25 94` | `6E 01 00 00 6F` |
| `cb18d1` | Head Up | `6E 01 00 24 93` | `6E 01 00 00 6F` |
| `cb1951` | Light Board | `6E 01 00 50 BF` | `6E 01 00 00 6F` |
| `cb19d1` | Pillow Down | `6E 01 00 42 B1` | `6E 01 00 00 6F` |
| `cb1a51` | Pillow Up | `6E 01 00 41 B0` | `6E 01 00 00 6F` |
| `cb1ad1` | Lumbar Down | `6E 01 00 40 AF` | `6E 01 00 00 6F` |
| `cb1b51` | Lumbar Up | `6E 01 00 3F AE` | `6E 01 00 00 6F` |
| `cb1bd1` | Phone Light | `6E 01 00 00 6F` | `6E 01 00 00 6F` |
| `cb1c51` | Motor3 Down | `6E 01 00 72 E1` | `6E 01 00 00 6F` |
| `cb1cd1` | Motor3 Up | `6E 01 00 71 E0` | `6E 01 00 00 6F` |
| `cb1d51` | Head And Foot Up | `6E 01 00 29 98` | `6E 01 00 00 6F` |
| `cb1dd1` | Foot Up And Head Down | `6E 01 00 22 91` | `6E 01 00 00 6F` |
| `cb1e51` | Head And Foot All Up | `6E 01 00 23 92` | `6E 01 00 00 6F` |
| `cb1ed1` | Head Up And Foot Down | `6E 01 00 21 90` | `6E 01 00 00 6F` |
| `cb1f51` | Head And Foot Down | `6E 01 00 2A 99` | `6E 01 00 00 6F` |
| `cb1fd1` | All Motor Down | `6E 01 00 44 B3` | `6E 01 00 00 6F` |
| `cb2051` | All Motor Up | `6E 01 00 43 B2` | `6E 01 00 00 6F` |
| `cb20d1` | Lumbar Up | `6E 01 00 44 B3` | `6E 01 00 00 6F` |
| `cb2151` | Tile Down | `6E 01 00 5C CB` | `6E 01 00 00 6F` |
| `cb21d1` | Tile Up | `6E 01 00 5B CA` | `6E 01 00 00 6F` |
| `cb2251` | All Motor Down | `6E 01 00 57 C6` | `6E 01 00 00 6F` |
| `cb22d1` | All Motor Up | `6E 01 00 56 C5` | `6E 01 00 00 6F` |
| `cb2351` | Motor Reset2 | `6E 01 00 6C DB` | `6E 01 00 00 6F` |
| `cb23d1` | Head Up And Foot Stop | `6E 01 00 3D AC` | `6E 01 00 00 6F` |
| `cb2451` | Sync Off | `6E 01 00 BD 2C` | `6E 01 00 BD 2C` |
| `cb24d1` | Sync On | `6E 01 00 BC 2B` | `6E 01 00 BC 2B` |
| `cb2551` | Motor4 Down | `6E 01 00 74 E3` | `6E 01 00 00 6F` |
| `cb25d1` | Motor4 Up | `6E 01 00 73 E2` | `6E 01 00 00 6F` |
| `cb2651` | Motor5 Down | `6E 01 00 D1 40` | `6E 01 00 00 6F` |
| `cb26d1` | Motor5 Up | `6E 01 00 D0 3F` | `6E 01 00 00 6F` |
| `cb2751` | Motor3 Up | `6E 01 00 5B CA` | `6E 01 00 00 6F` |
| `cb27d1` | Motor4 Up | `6E 01 00 5C CB` | `6E 01 00 00 6F` |
| `cb2851` | Light Board | `6E 01 00 50 BF` | `6E 01 00 00 6F` |
| `cb28d1` | Head And Foot Down | `6E 01 00 57 C6` | `6E 01 00 00 6F` |
| `cb2951` | Head And Foot Up | `6E 01 00 56 C5` | `6E 01 00 00 6F` |
| `cb29d1` | Sofa Backward | `6E 01 00 5C CB` | `6E 01 00 00 6F` |
| `cb2a51` | Sofa Forword | `6E 01 00 5B CA` | `6E 01 00 00 6F` |
| `cb2ad1` | Motor4 Down | `6E 01 00 74 E3` | `6E 01 00 00 6F` |
| `cb2b51` | Tile Down | `6E 01 00 73 E2` | `6E 01 00 00 6F` |
| `cb2bd1` | Tile Up | `6E 01 00 5B CA` | `6E 01 00 00 6F` |
| `cb2c51` | All Motor Down | `6E 01 00 5C CB` | `6E 01 00 00 6F` |
| `cb2cd1` | All Motor Up | `6E 01 00 5B CA` | `6E 01 00 00 6F` |
| `cb2d51` | Motor Reset | `6E 01 00 47 B6` | `6E 01 00 00 6F` |
| `cb2dd1` | Motor4 Down | `6E 01 00 2A 99` | `6E 01 00 00 6F` |
| `cb2e51` | Motor4 Up | `6E 01 00 29 98` | `6E 01 00 00 6F` |
| `cb2ed1` | Motor4 Down | `6E 01 00 7B EA` | `6E 01 00 00 6F` |
| `cb2f51` | Motor4 Up | `6E 01 00 7A E9` | `6E 01 00 00 6F` |
| `cb2fd1` | Motor3 Down | `6E 01 00 72 E1` | `6E 01 00 00 6F` |
| `cb3051` | Motor3 Up | `6E 01 00 71 E0` | `6E 01 00 00 6F` |
| `cb30d1` | Head And Foot Down | `6E 01 00 44 B3` | `6E 01 00 00 6F` |
| `cb3151` | Head And Foot Up | `6E 01 00 43 B2` | `6E 01 00 00 6F` |
| `cb31d1` | Foot Down | `6E 01 00 40 AF` | `6E 01 00 00 6F` |
| `cb3251` | Foot Up | `6E 01 00 3F AE` | `6E 01 00 00 6F` |
| `cb32d1` | Head Down | `6E 01 00 42 B1` | `6E 01 00 00 6F` |
| `cb3351` | Head Up | `6E 01 00 41 B0` | `6E 01 00 00 6F` |
| `cb33d1` | Head And Foot Down | `6E 01 00 31 A0` | `6E 01 00 00 6F` |
| `cb3451` | Head And Foot Up | `6E 01 00 23 92` | `6E 01 00 00 6F` |
| `cb34d1` | Head And Foot Down | `6E 01 00 97 06` | `6E 01 00 00 6F` |
| `cb3551` | Head And Foot Up | `6E 01 00 96 05` | `6E 01 00 00 6F` |
| `cb35d1` | Massage30 Minute Timer | `6E 01 00 61 D0` | `6E 01 00 00 6F` |
| `cb3651` | Massage20 Minute Timer | `6E 01 00 63 D2` | `6E 01 00 00 6F` |
| `cb36d1` | Massage10 Minute Timer | `6E 01 00 5F CE` | `6E 01 00 00 6F` |
| `cb3751` | Massage Mode Change | `6E 01 00 48 B7` | `6E 01 00 00 6F` |
| `cb37d1` | Massage Mode All Off | `6E 01 00 5E CD` | `6E 01 00 00 6F` |
| `cb3851` | Massage Foot Instensity Strengthen | `6E 01 00 4E BD` | `6E 01 00 00 6F` |
| `cb38d1` | Massage Head Instensity Strengthen | `6E 01 00 4C BB` | `6E 01 00 00 6F` |
| `cb3951` | Massage Instensity Strengthen | `6E 01 00 34 A3` | `6E 01 00 00 6F` |
| `cb39d1` | Massage Foot Instensity Weaken | `6E 01 00 4F BE` | `6E 01 00 00 6F` |
| `cb3a51` | Massage Head Instensity Weaken | `6E 01 00 4D BC` | `6E 01 00 00 6F` |
| `cb3ad1` | Massage Foot Instensity Strengthen | `6E 01 00 4E BD` | `6E 01 00 00 6F` |
| `cb3b51` | Massage Head Instensity Strengthen | `6E 01 00 4C BB` | `6E 01 00 00 6F` |
| `cb3bd1` | Heating Switch | `6E 01 00 A0 0F` | `6E 01 00 00 6F` |
| `cb3c51` | Massage Fan Instensity Strengthen | `6E 01 00 E1 50` | `6E 01 00 00 6F` |
| `cb3cd1` | Music Volumu Down | `6E 01 00 D5 44` | `6E 01 00 00 6F` |
| `cb3d51` | Music Volumu Up | `6E 01 00 D4 43` | `6E 01 00 00 6F` |
| `cb3dd1` | Music Pause Play | `6E 01 00 D7 46` | `6E 01 00 00 6F` |
| `cb3e51` | Music Shake Mode | `6E 01 00 D6 45` | `6E 01 00 00 6F` |
| `cb3ed1` | Massage Mode Wave | `6E 01 00 39 A8` | `6E 01 00 00 6F` |
| `cb3f51` | Massage Mode All Off | `6E 01 00 5A C9` | `6E 01 00 00 6F` |
| `cb3fd1` | Massage Instensity First Gear | `6E 01 00 67 D6` | `6E 01 00 00 6F` |
| `cb4051` | Massage Instensity Third Gear | `6E 01 00 68 D7` | `6E 01 00 00 6F` |
| `cb40d1` | Massage2 Open Or Close | `6E 01 00 33 A2` | `6E 01 00 00 6F` |
| `cb4151` | Massage1 Open Or Close | `6E 01 00 32 A1` | `6E 01 00 00 6F` |
| `cb41d1` | Massage Mode Wave Third Mode | `6E 01 00 4B BA` | `6E 01 00 00 6F` |
| `cb4251` | Massage Mode All On | `6E 01 00 5D CC` | `6E 01 00 00 6F` |
| `cb42d1` | Massage2 Instensity | `6E 01 00 A5 14` | `6E 01 00 00 6F` |
| `cb4351` | Massage1 Instensity | `6E 01 00 A4 13` | `6E 01 00 00 6F` |
| `cb43d1` | Massage Mode All Off | `6E 01 00 47 B6` | `6E 01 00 00 6F` |
| `cb4451` | Massage Switch | `6E 01 00 5D CC` | `6E 01 00 00 6F` |
| `cb44d1` | Massage Mode All Off | `6E 01 00 5D CC` | `6E 01 00 00 6F` |
| `cb4551` | Motor And Massage All Off | `6E 01 00 47 B6` | `6E 01 00 00 6F` |
| `cb45d1` | Music Cut | `6E 01 00 B8 27` | `6E 01 00 00 6F` |
| `cb4651` | Adjust Volume | `6E 01 00 B7 26` | `6E 01 00 00 6F` |
| `cb46d1` | Music Close | `6E 01 00 B9 28` | `6E 01 00 00 6F` |
| `cb4751` | Massage15 Minute Timer | `6E 01 00 60 CF` | `6E 01 00 00 6F` |
| `cb47d1` | Massage Lumbar Instensity Strengthen | `6E 01 00 E0 4F` | `6E 01 00 00 6F` |
| `cb4851` | Massage Mode All Off | `6E 01 00 5F CE` | `6E 01 00 00 6F` |
| `cb48d1` | Swing Mode Switch | `6E 01 00 D6 45` | `6E 01 00 00 6F` |
| `cb4951` | Swing On And Off | `6E 01 00 D8 47` | `6E 01 00 00 6F` |
| `cb49d1` | Swing Help Sleep | `6E 01 00 76 E5` | `6E 01 00 00 6F` |
| `cb4a51` | Music Next Song | `6E 01 00 D3 42` | `6E 01 00 00 6F` |
| `cb4ad1` | Music Previous Song | `6E 01 00 D2 41` | `6E 01 00 00 6F` |
| `cb4b51` | Music Lock | `6E 01 00 D9 48` | `6E 01 00 00 6F` |
| `cb4bd1` | Massage Mode All Off | `6E 01 00 61 D0` | `6E 01 00 00 6F` |
| `cb4c51` | Massage Mode All Off | `6E 01 00 34 A3` | `6E 01 00 00 6F` |
| `cb4cd1` | Fan Timer5 Hour | `6E 01 00 A8 17` | `6E 01 00 00 6F` |
| `cb4d51` | Fan Timer3 Hour | `6E 01 00 A7 16` | `6E 01 00 00 6F` |
| `cb4dd1` | Fan Timer2 Hour | `6E 01 00 A6 15` | `6E 01 00 00 6F` |
| `cb4e51` | Fan Change Mode | `6E 01 00 A2 11` | `6E 01 00 00 6F` |
| `cb4ed1` | Fan All Off | `6E 01 00 A1 10` | `6E 01 00 00 6F` |
| `cb4f51` | Fan2 Instensity Strengthen | `6E 01 00 8B FA` | `6E 01 00 00 6F` |
| `cb4fd1` | Fan1 Instensity Strengthen | `6E 01 00 8A F9` | `6E 01 00 00 6F` |
| `cb5051` | Anti Pinch Sensitivity Mode Change | `6E 01 00 BE 2D` | `6E 01 00 00 6F` |
| `cb50d1` | Massage Mode Constant | `6E 01 00 3A A9` | `6E 01 00 00 6F` |
| `cb5151` | Massage Mode Pulse | `6E 01 00 38 A7` | `6E 01 00 00 6F` |
| `cb51d1` | Massage Switch | `6E 01 00 6F DE` | `6E 01 00 00 6F` |
| `cb5251` | Massage Speed Weaken | `6E 01 00 37 A6` | `6E 01 00 00 6F` |
| `cb52d1` | Massage Speed Strengthen | `6E 01 00 36 A5` | `6E 01 00 00 6F` |
| `cb5351` | Massage Instensity Weaken | `6E 01 00 35 A4` | `6E 01 00 00 6F` |
| `cb53d1` | Massage Foot Instens Third Mode | `6E 01 00 9F 0E` | `6E 01 00 00 6F` |
| `cb5451` | Massage Foot Instens Second Mode | `6E 01 00 9E 0D` | `6E 01 00 00 6F` |
| `cb54d1` | Massage Foot Instens First Mode | `6E 01 00 9D 0C` | `6E 01 00 00 6F` |
| `cb5551` | Massage Foot Off | `6E 01 00 9C 0B` | `6E 01 00 00 6F` |
| `cb55d1` | Massage Head Instens Third Mode | `6E 01 00 9B 0A` | `6E 01 00 00 6F` |
| `cb5651` | Massage Head Instens Second Mode | `6E 01 00 9A 09` | `6E 01 00 00 6F` |
| `cb56d1` | Massage Head Instens First Mode | `6E 01 00 99 08` | `6E 01 00 00 6F` |
| `cb5751` | Massage Head Off | `6E 01 00 98 07` | `6E 01 00 00 6F` |
| `cb57d1` | Heating Off | `6E 01 00 9C 0B` | `6E 01 00 00 6F` |
| `cb5851` | Heating High Gear | `6E 01 00 9F 0E` | `6E 01 00 00 6F` |
| `cb58d1` | Heating Middle Gear | `6E 01 00 9E 0D` | `6E 01 00 00 6F` |
| `cb5951` | Heating Low Gear | `6E 01 00 9D 0C` | `6E 01 00 00 6F` |
| `cb59d1` | Heating60 Min | `6E 01 00 A2 11` | `6E 01 00 00 6F` |
| `cb5a51` | Heating30 Min | `6E 01 00 A1 10` | `6E 01 00 00 6F` |
| `cb5ad1` | Motor And Massage All Off | `6E 01 00 5F CE` | `6E 01 00 00 6F` |
| `cb5b51` | Massage30 Minute Up And Down | `6E 01 00 90 FF` | `6E 01 00 00 6F` |
| `cb5bd1` | Massage15 Minute Spine Guard | `6E 01 00 76 E5` | `6E 01 00 00 6F` |
| `cb5c51` | Massage Mode Wave Second Mode | `6E 01 00 4A B9` | `6E 01 00 00 6F` |
| `cb5cd1` | Massage Mode Wave First Mode | `6E 01 00 49 B8` | `6E 01 00 00 6F` |
| `cb5d51` | Fan Forward And Backward Change | `6E 01 00 8C FB` | `6E 01 00 00 6F` |
| `cb5dd1` | Massage Foot Instensity Strengthen | `6E 01 00 33 A2` | `6E 01 00 00 6F` |
| `cb5e51` | Massage Instensity Strengthen | `6E 01 00 4E BD` | `6E 01 00 00 6F` |
| `cb5ed1` | Massage Instensity Second Gear | `6E 01 00 4D BC` | `6E 01 00 00 6F` |
| `cb5f51` | Massage Mode Wave | `6E 01 00 48 B7` | `6E 01 00 00 6F` |
| `cb5fd1` | Massage Switch | `6E 01 00 4C BB` | `6E 01 00 00 6F` |
| `cb6051` | Bed Light On | `6E 01 00 BF 2E` | `6E 01 00 00 6F` |
| `cb60d1` | Yoga Position | `6E 01 00 F0 5F` | `6E 01 00 6A D9` |
| `cb6151` | Alarm Mode1 | `6E 01 00 F5 64` | `6E 01 00 00 6F` |
| `cb61d1` | Reading Position | `6E 01 00 F2 61` | `6E 01 00 F3 62` |
| `cb6251` | Alarm Wake | `6E 01 00 2E 9D` | `6E 01 00 00 6F` |
| `cb62d1` | Alarm Mode2 | `6E 01 00 B1 20` | `6E 01 00 00 6F` |
| `cb6351` | Alarm Mode1 | `6E 01 00 B0 1F` | `6E 01 00 00 6F` |
| `cb63d1` | Pillow Down | `6E 01 00 40 AF` | `6E 01 00 00 6F` |
| `cb6451` | Pillow Up | `6E 01 00 3F AE` | `6E 01 00 00 6F` |
| `cb64d1` | Foot Down | `6E 01 00 27 96` | `6E 01 00 00 6F` |
| `cb6551` | Foot Up | `6E 01 00 26 95` | `6E 01 00 00 6F` |
| `cb65d1` | Head Down | `6E 01 00 25 94` | `6E 01 00 00 6F` |
| `cb6651` | Head Up | `6E 01 00 24 93` | `6E 01 00 00 6F` |
| `cb66d1` | Pillow Down | `6E 01 00 42 B1` | `6E 01 00 00 6F` |
| `cb6751` | Pillow Up | `6E 01 00 41 B0` | `6E 01 00 00 6F` |
| `cb67d1` | Foot Down | `6E 01 00 27 96` | `6E 01 00 00 6F` |
| `cb6851` | Foot Up | `6E 01 00 26 95` | `6E 01 00 00 6F` |
| `cb68d1` | Head Down | `6E 01 00 25 94` | `6E 01 00 00 6F` |
| `cb6951` | Head Up | `6E 01 00 24 93` | `6E 01 00 00 6F` |
| `cb69d1` | Foot Down | `6E 01 00 27 96` | `6E 01 00 00 6F` |
| `cb6a51` | Foot Up | `6E 01 00 26 95` | `6E 01 00 00 6F` |
| `cb6ad1` | Head Down | `6E 01 00 25 94` | `6E 01 00 00 6F` |
| `cb6b51` | Head Up | `6E 01 00 24 93` | `6E 01 00 00 6F` |
| `cb6bd1` | Foot Down | `6E 01 00 27 96` | `6E 01 00 00 6F` |
| `cb6c51` | Foot Up | `6E 01 00 26 95` | `6E 01 00 00 6F` |
| `cb6cd1` | Head Down | `6E 01 00 25 94` | `6E 01 00 00 6F` |
| `cb6d51` | Head Up | `6E 01 00 24 93` | `6E 01 00 00 6F` |

| Query | Frame |
|---|---|
| alarms | `6E 20 08 05 01 00 00 9C` |
| snore | `6E 20 08 06 00 00 00 9C` |
| blanket | `6E 20 07 0D 00 00 A2` |
| blanket_power | `6E 20 09 0D 01 00 00 00 A5` |
| blanket_settings | `6E 20 09 0D 08 00 00 00 AC` |
| sleep_name | `6E 20 08 06 03 00 00 9F` |

| Startup phase | Function | Frame |
|---|---|---|
| Product | deviceFunctionItemCheckClock | `6E 08 01 01 78` |
| Product | deviceFunctionItemCheckLight | `6E 0A 00 01 79` |
| Product | deviceFunctionItemCheckAroma | `6E 1A 00 00 88` |
| Product | deviceFunctionItemCheckMattress | `5E 1A 00 01 79` |
| Product | deviceFunctionItemCheckLumbarMattress | `6E 01 00 01 70` |
| Product | deviceFunctionItemCheckSnore | `6E 21 00 00 8F` |
| Product | deviceFunctionItemCheckSpeech | `6E 22 00 00 90` |
| Product | deviceFunctionItemCheckDetection | `6E 9A C0 00 C8` |
| Product | deviceFunctionItemQueryVersion | `6E 9A 00 00 08` |
| Protocol version 1 | deviceFunctionVersionOneBedCurrentMode | `6E 9A 10 00 18` |
| Protocol version 1 | deviceFunctionVersionOneMotor1CurrentAngle | `6E 9A 30 01 39` |
| Protocol version 1 | deviceFunctionVersionOneMotor2CurrentAngle | `6E 9A 30 02 3A` |
| Protocol version 1 | deviceFunctionVersionOneMotor3CurrentAngle | `6E 9A 30 03 3B` |
| Protocol version 1 | deviceFunctionVersionOneMotor4CurrentAngle | `6E 9A 30 04 3C` |
| Protocol version 1 | deviceFunctionVersionOneCurrentMassageMode | `6E 9A A0 00 A8` |
| Protocol version 1 | deviceFunctionVersionOneCurrentBedLightStatus | `6E 9A B0 00 B8` |

Named operations: `sync`, `detection`, `toggle_alarm`, `sleep_sync`, `query`,
`single_alarm`, `cancel_alarm`, `repeat_alarm`, `delete_alarm`, `light_timer`,
`light_rgb`, `strip_rgb`, `strip_timer`, `strip_groove`, `strip_color_mode`,
`strip_breathe`, `strip_power`, `therapy_light`, `therapy_sound`, `therapy_timer`,
`music_source`, `white_noise`, `snore`, `get_off_bed`, `snore_intervention`,
`blanket_power`, `blanket_mode`, `blanket_temperature`, `blanket_delay`,
`blanket_mite`, `blanket_settings`, `blanket_sleep`, `usb`, `demo`, `sleep_time`,
`sleep_part`, `sleep_realtime`, `sleep_report`, `sleep_snore`,
`sleep_sensitivity`, `sleep_init`, `sleep_cancel`, `sleep_poll`.
<!-- /generated -->

Product identities and their two menu branches remain separate even when their
scalar getters match. These are catalog entries, not a claim that every product
is a bed or has every feature. The following reference lists only the controls
and gates selected by the shipped catalog.

<!-- generated:richmat-app-products -->
<details>
<summary>Product catalog and protocol branches</summary>

| Product | Selection | Motor menus (ordinary / V1) | Presets (ordinary / V1) | Blanket | RGB / therapy / strip / cold-warm | Sleep / BLE menu |
|---|---|---|---|---|---|---|
| 6BRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| 6CRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| 6DRM | manual | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| 6ERM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| 6FRM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| 6HRM | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| 7IRM | manual | 4 / 4 | 7 / 9 | False | False / False / False / False | DeviceSleepMonitoringType@cdc991 / False |
| A0RM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A0RN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A1RM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A2RM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A2RN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| A3RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A3RN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| A4RN | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A5RN | manual | 5 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| A6RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A6RN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| A7RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A7RN | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A8RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A8RN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A9RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| A9RN | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AARM | manual | 5 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AARN | restored | 1 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ABRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ABRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ACRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ACRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ADRM | manual | 3 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ADRN | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| AERM | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AERN | manual | 3 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| AFRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AFRN | manual | 5 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| AGRM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AHRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AIRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AIRN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| AJRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AJRN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AKRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AKRN | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ALRM | restored | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ALRN | manual | 4 / 0 | 6 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc971 / False |
| AMRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AMRN | manual | 4 / 4 | 6 / 9 | False | False / False / True / False | DeviceSleepMonitoringType@cdc991 / False |
| ANRM | restored | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ANRN | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AORM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| APRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| APRN | restored | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AQRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AQRN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ARRM | restored | 1 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ARRN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ASRM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ASRN | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ATRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ATRN | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AURM | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AURN | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AVRM | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AWRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AWRN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AXRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AXRN | restored | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AYRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AYRN | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AZRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| AZRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B0RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B1RM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B1RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B2RM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B2RN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B3RM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B3RN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| B4RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B4RN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| B5RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B5RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B6RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B6RU | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B7RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B7RN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B8RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B8RN | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B8TT | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B9RM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B9RN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| B9TT | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BARM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BARN | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BBRM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BBRN | restored | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BCRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BCRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BDRM | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BDRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BERM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BERN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BFRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BFRN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| BGRM | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BGRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BHRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BHRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BIRM | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BIRN | manual | 5 / 0 | 7 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| BJRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BKRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BKRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BLRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BLRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BMRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BMRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BNRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BNRN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| BORM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BORN | manual | 3 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| BPRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BPRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BQRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BRRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BRRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BSRM | restored | 1 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BSRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BTRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BTRN | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BURM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BURN | manual | 2 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| BVRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BVRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BWRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BWRN | restored | 4 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BXRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BXRN | restored | 4 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BYRM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BZRM | manual | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| BZRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C0RM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C1RM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C1RN | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C2RM | restored | 5 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C2RN | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C3RM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C3RN | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C4RM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C4RN | manual | 4 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C5RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C5RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C6RM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C6RN | manual | 4 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C7RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C7RN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C8RM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C8RN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C9RM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| C9RN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CARM | restored | 5 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CARN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CBRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CBRN | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CCRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CCRN | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CDRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CDRN | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CERM | manual | 3 / 3 | 5 / 5 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CERN | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| CFRM | manual | 5 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CFRN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CGRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CGRN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| CHRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CHRN | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CIRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CIRN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CJRM | restored | 5 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CJRN | manual | 3 / 0 | 6 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| CKRM | restored | 6 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CLRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CLRN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CMRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CMRN | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CNRM | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CNRN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CORM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CORN | restored | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CPRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CPRN | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CQRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CRRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CRRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| CSRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CSRN | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| CTRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CTRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CURM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CURN | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CVRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CVRN | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CWRM | manual | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CWRN | manual | 3 / 0 | 9 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CXRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CXRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CYRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CYRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CZRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| CZRN | manual | 3 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| D0RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D1RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D1RN | manual | 4 / 0 | 6 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| D2RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D2RN | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D3RM | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D3RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D4RM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D5RM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D6RM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D7RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D8RM | restored | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D8RN | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D9RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| D9RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DARM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DARN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DBRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DBRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DCRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DCRN | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DDRM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DDRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| DERM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DERN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DFRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DFRN | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DGRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DGRN | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DHRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DHRN | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DIRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DIRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DJRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DJRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DKRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DKRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DLRM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DLRN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DMRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DMRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DNRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DNRN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| DORN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DPRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DPRN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DQRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DQRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DRRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DRRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DSRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DSRN | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DTRM | manual | 2 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| DTRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DURM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DURN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DVRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DVRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DWRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DWRN | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DXRM | restored | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DXRN | manual | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DYRM | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DYRN | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DZRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| DZRN | manual | 3 / 0 | 7 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| E0RM | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E1RM | manual | 4 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| E1RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E2RM | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E2RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E3RM | restored | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E3RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E4RM | restored | 4 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E4RN | manual | 2 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| E5RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E6RM | manual | 6 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E7RM | restored | 4 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E8RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| E9RM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EARM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc991 / False |
| EBRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ECRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EDRM | restored | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EERM | manual | 5 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| EFRM | manual | 4 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| EFRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EGRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EGRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| EHRM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EHRN | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| EIRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EIRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EJRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EJRN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EKRM | restored | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EKRN | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ELRM | manual | 3 / 3 | 5 / 5 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ELRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EMRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EMRN | manual | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ENRM | restored | 4 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ENRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EORM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EORN | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EPRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EPRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EQRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ERRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ESRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ESRN | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ETRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ETRN | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EURM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EURN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EVRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EVRN | manual | 5 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EWRM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EWRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EXRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EXRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EYRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EYRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EZRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| EZRN | manual | 5 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| F0RM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| F1RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F1RN | manual | 2 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| F2RM | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F2RN | manual | 6 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| F3RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F3RN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F4RM | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F4RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F5RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F5RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F6RM | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F7RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F7RN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F8RM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F8RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F9RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| F9RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FARM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FARN | manual | 3 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FBRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FBRN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FCRM | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FCRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FDRM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FDRN | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FERM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FERN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FFRM | restored | 3 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FFRN | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FGRM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FGRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FHRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FHRN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FIRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FJRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FJRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FKRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FKRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FLRM | restored | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FLRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FMRM | manual | 2 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FMRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FNRM | manual | 2 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FNRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FPRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FPRN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| FQRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FQRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FRRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FRRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| FSRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc991 / False |
| FSRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FTRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FTRN | restored | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FURM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FURN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FVRM | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FVRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / True |
| FWRM | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FWRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / True |
| FXRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FXRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / True |
| FYRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FYRN | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FZRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| FZRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G1RN | manual | 3 / 0 | 9 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / True |
| G2RM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G2RN | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / True |
| G3RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G3RN | manual | 3 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G4RM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G4RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G5RM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G5RN | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G6RM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G6RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G7RM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G7RN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G8RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G8RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| G9RM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| G9RN | manual | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GARM | manual | 5 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| GARN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GBRM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GBRN | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GCRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GCRN | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GDRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GDRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GERM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GERN | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GFRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GFRN | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GGRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GGRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GHRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GHRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| GJRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GJRN | manual | 3 / 0 | 9 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| GKRM | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| GKRN | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| GLRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| GLRN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GMRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GMRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| GNRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GNRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GORM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GPRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GQRM | manual | 4 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| GQRN | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GRRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GRRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GSRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| GSRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GTRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GTRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GURM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GURN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GVRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GWRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GWRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| GXRM | restored | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GXRN | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GYRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GYRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GZRM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| GZRN | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H2RM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H2RN | manual | 6 / 0 | 8 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| H3RM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H3RN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H4RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H4RN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H5RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H6RM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H7RM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H7RN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H8RM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H8RN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| H9RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| H9RN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / True |
| HARM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| HARN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HBRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| HCRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HCRN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HDRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HDRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HERM | restored | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HERN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HFRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HGRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HHRN | manual | 5 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc971 / False |
| HJRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HKRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HKRN | manual | 2 / 0 | 6 / 0 | False | False / True / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HLRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HMRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HMRN | manual | 4 / 0 | 4 / 0 | True | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| HNRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HNRN | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HPRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HQRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc991 / False |
| HQRN | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HRRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| HSRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HSRN | restored | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HTRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HURM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HURN | restored | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HVRM | manual | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HWRM | manual | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HWRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HXRM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HYRM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| HYRN | manual | 4 / 0 | 3 / 0 | False | False / True / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HZRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| HZRN | manual | 4 / 0 | 6 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| I0RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I1RM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I2RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I3RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I4RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I5RM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I6RM | manual | 1 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I7RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I8RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| I9RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IARM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IBRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ICRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IDRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IERM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IFRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IGRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IHRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IIRM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IJRM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IKRM | manual | 1 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ILRM | manual | 1 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IMRM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| INRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IORM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IPRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IQRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| IRRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ISRM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J2RM | manual | 2 / 0 | 6 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| J2RN | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J3RM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| J3RN | manual | 6 / 0 | 4 / 0 | False | True / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| J4RM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J4RN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J5RM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J5RN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J6RM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J6RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J7RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J7RN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J8RM | manual | 4 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| J8RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J9RM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| J9RN | manual | 2 / 0 | 7 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc971 / False |
| JARN | manual | 2 / 0 | 9 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| JBRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JBRN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JCRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JCRN | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JDRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JDRN | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JERM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JERN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JFRM | restored | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JGRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JHRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JJRM | restored | 1 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JKRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JLRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JLRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JMRM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| JMRN | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JNRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JNRN | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JPRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JPRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JQRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JQRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JRRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JRRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JSRM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JSRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JTRM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| JTRN | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JURM | manual | 3 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| JURN | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JVRM | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JWRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JWRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JXRM | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| JXRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JYRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JYRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JZRM | restored | 1 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| JZRN | manual | 3 / 0 | 8 / 0 | False | False / False / False / True | DeviceSleepMonitoringType@cdc951 / False |
| K2RM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K2RN | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K3RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K3RN | manual | 5 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| K4RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K4RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| K5RM | manual | 3 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| K5RN | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K6RM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| K6RN | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K7RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K7RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K8RM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K8RN | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| K9RM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| K9RN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KARM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KARN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KBRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KBRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KCRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KCRN | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KDRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KDRN | manual | 3 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KERM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KERN | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KFRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KFRN | manual | 4 / 0 | 4 / 0 | False | False / True / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KGRM | manual | 3 / 0 | 1 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KGRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KHRM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KHRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KJRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KJRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KKRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KKRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KLRM | manual | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KLRN | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KMRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KMRN | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KNRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KNRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KPRM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KPRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KQRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KQRN | manual | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KRRM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KRRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KSRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KSRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KTRM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KTRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KURM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| KVRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KVRN | manual | 5 / 0 | 2 / 0 | False | True / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| KWRM | manual | 3 / 3 | 5 / 5 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KWRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KXRM | restored | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KXRN | manual | 6 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc971 / False |
| KYRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KYRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| KZRN | manual | 4 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L2RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L3RM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L3RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L4RM | manual | 2 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| L4RN | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L5RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L5RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L6RM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| L6RN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L7RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L7RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L8RM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L8RN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| L9RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| L9RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LARM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LARN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LBRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc991 / False |
| LBRN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LCRM | restored | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LCRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LDRM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| LDRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LERM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| LERN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LFRM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LFRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc971 / False |
| LGRM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LGRN | manual | 2 / 0 | 4 / 0 | False | False / True / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LHRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LHRN | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LJRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LJRN | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LKRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LKRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LLRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LLRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LMRM | restored | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LNRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LNRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LPRM | manual | 3 / 3 | 5 / 5 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LPRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LQRM | restored | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LQRN | manual | 4 / 0 | 8 / 0 | False | False / True / True / False | DeviceSleepMonitoringType@cdc951 / False |
| LRRM | restored | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LRRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LSRM | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LSRN | manual | 7 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc971 / False |
| LTRM | manual | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LTRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LURM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LURN | manual | 4 / 0 | 8 / 0 | False | False / True / True / False | DeviceSleepMonitoringType@cdc951 / False |
| LVRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LVRN | manual | 3 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| LWRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LWRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LXRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LXRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LYRM | restored | 5 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LYRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LZRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| LZRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M2RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M2RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M3RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M4RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M4RN | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M5RM | manual | 5 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M5RN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M6RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M6RN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M7RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M7RN | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M8RM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| M8RN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| M9RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| M9RN | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MARM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MARN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MBRM | manual | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MBRN | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MCRM | restored | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MCRN | manual | 5 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| MDRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MDRN | restored | 5 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MERM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MERN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MFRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MFRN | manual | 3 / 0 | 8 / 0 | False | False / False / False / True | DeviceSleepMonitoringType@cdc951 / False |
| MGRM | restored | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MGRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| MHRN | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MJRN | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MKRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MLRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MLRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MMRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MMRN | manual | 4 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MNRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MPRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MPRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MQRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MQRN | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MRRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MRRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MSRM | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MSRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MTRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MTRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MURM | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MURN | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MVRM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| MVRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MWRM | manual | 2 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| MWRN | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MXRM | manual | 2 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| MXRN | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MYRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MYRN | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| MZRN | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N2RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N2RN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N3RM | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N3RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N4RM | manual | 4 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| N4RN | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N5RM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N5RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N6RN | manual | 4 / 0 | 4 / 0 | False | False / False / False / True | DeviceSleepMonitoringType@cdc951 / False |
| N7RN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N8RN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| N9RN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NARN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NBRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NCRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NDRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NERN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NFRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NGRN | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| NHRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NJRN | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NLRN | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NMRN | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NNRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NPRN | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NQRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NRRN | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NTRN | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NURN | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NXRN | manual | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| NYRN | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| None | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O0RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O1RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O2RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O3RM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O4RM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O5RM | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O6RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O7RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O8RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| O9RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OARM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OMRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ONRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OORM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OPRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OQRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ORRM | manual | 5 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OSRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OTRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OURM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OVRM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OWRM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OXRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OYRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| OZRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P0RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P1RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P2RM | manual | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P3RM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P3RN | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P4RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P4RN | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P5RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P6RM | manual | 5 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| P9RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| QRRM | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| R2RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| R5RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| R6RM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| S9RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| SARM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T0RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T1RM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T2RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T3RM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T4RM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T5RM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T6RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T7RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T8RM | manual | 3 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| T9RM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TARM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TBRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TCRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TDRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TERM | restored | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TEST | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| THRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TLRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TWRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| TZRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U0RM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U1RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U2RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U3RM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U4RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U5RM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U6RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U7RM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U8RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| U9RM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UARM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UBRM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UCRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UDRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UERM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UFRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UGRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UHRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UIRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UJRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UKRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ULRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UMRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UNRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UORM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UPRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UQRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| URRM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UTRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UURM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UVRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UWRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UXRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UYRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| UZRM | manual | 3 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V0RM | manual | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V1RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V2RM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V3RM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V4RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V5RM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V6RM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V7RM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V8RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| V9RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VARM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VBRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VCRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VDRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VERM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VFRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VGRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VHRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VIRM | manual | 4 / 0 | 3 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| VJRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VKRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VLRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VMRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VNRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VORM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VPRM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VQRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VRRM | manual | 5 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VSRM | manual | 3 / 0 | 4 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| VTRM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VURM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VVRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VWRM | manual | 2 / 0 | 7 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VXRM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VYRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| VZRM | manual | 5 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W0RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W1RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W2RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W3RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W4RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W5RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W6RM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W7RM | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W8RM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| W9RM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WARM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WBRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WCRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WDRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WERM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WFRM | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WGRM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WHRM | manual | 5 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WIRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WJRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WKRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WLRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WMRM | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WNRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WORM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WPRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WQRM | manual | 1 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WRRM | manual | 3 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WSRM | manual | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WTRM | manual | 6 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WURM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WVRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WWRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WXRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WYRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| WZRM | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X0RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X1RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X2RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X4RM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X5RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X6RM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X7RM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X8RM | restored | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| X9RM | restored | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XARM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XBRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XCRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XDRM | restored | 1 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XERM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XFRM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XGRM | manual | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XHRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XIRM | manual | 3 / 0 | 5 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| XJRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XKRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XLRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XMRM | restored | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XNRM | restored | 1 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XORM | restored | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XPRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XQRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XRRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XSRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XTRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XURM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XVRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XWRM | restored | 5 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XXRM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XYRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| XZRM | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y0RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y1RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y2RM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y3RM | manual | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y4RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y5RM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y6RM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y7RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y8RM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Y9RM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YARM | manual | 4 / 0 | 2 / 0 | False | False / False / True / False | DeviceSleepMonitoringType@cdc951 / False |
| YBRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YCRM | manual | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YDRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YERM | manual | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YFRM | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YGRM | manual | 2 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YHRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YIRM | manual | 4 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YJRM | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YKRM | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YMRM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YNRM | manual | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YORM | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YPRM | manual | 4 / 0 | 8 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YQRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YRRM | restored | 2 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YSRM | restored | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YTRM | restored | 4 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YURM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YVRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YWRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YXRM | restored | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YYRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| YZRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z0RM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z1RM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z2RM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z3RM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z4RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z5RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z6RM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z7RM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z8RM | manual | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| Z9RM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZARM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZBRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZCRM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZDRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZERM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZFRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZGRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZHRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZIRM | restored | 3 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZJRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZKRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZLRM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZMRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZNRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZORM | restored | 4 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZPRM | restored | 2 / 0 | 1 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZQRM | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR00 | manual | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR01 | manual | 1 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR10 | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR11 | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR12 | manual | 2 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR20 | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR21 | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR30 | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR40 | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR50 | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR51 | manual | 4 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR60 | manual | 2 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR70 | manual | 5 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR80 | manual | 5 / 0 | 2 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZR90 | manual | 3 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRA0 | manual | 5 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRA1 | manual | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRA2 | manual | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRI0 | manual | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRRM | restored | 3 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS0 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS1 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS2 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS3 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS4 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS5 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZRS6 | restored | 0 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZSRM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZTRM | restored | 4 / 0 | 3 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZURM | restored | 3 / 0 | 5 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZVRM | restored | 4 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZWRM | restored | 2 / 0 | 6 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZXRM | restored | 2 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZYRM | restored | 2 / 0 | 4 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |
| ZZRM | restored | 3 / 0 | 0 / 0 | False | False / False / False / False | DeviceSleepMonitoringType@cdc951 / False |

</details>
<!-- /generated -->

#### Timing

Movement starts after the first 100 ms tick. Releasing or cancelling before that
tick sends nothing. After a movement tick, cleanup sends its side-scoped STOP
with a fresh cancellation event. Explicit STOP remains available independently.
Presets, save buttons, massage taps and settings send once. Main writes are
serialized and spaced by at least 100 ms, avoiding the Android periodic-queue
race. Startup subscribes before Exit Limit, then schedules the nine product
queries at 50 ms producer intervals through that queue. Protocol version exactly
one schedules its seven additional information queries. No extra disconnect
packet is invented. USB switching retains its two-second throttle and delayed
second command; cancellation prevents a stale delayed write.

Blanket general temperature limits differ from its sleep-stage limits. Mite
removal changes local warm temperatures through the general clamp and sends
only the mite command. Sleep settings send before a changed main-mode frame.
The main delay retains the artifact's raw multiply-by-sixty formula even though
its Android label says hours. Groove timers convert UI seconds to rounded
minutes before encoding; received timers retain the separate base-sixty decode
and subscriber multiplication. These values are not calibrated hardware units.

#### Notifications

The status sensor exposes capability pages, alarm records, direct-bed notification
fields, the local blanket model, saved choices and rejection details. Local
optimistic changes are not hardware acknowledgements. Alarm list replies append;
escalation replies replace the first record with the same number. General blanket
responses merge only the fields their subscribers consume. Unsupported RGB
colors retain palette index -1.

Common motor replies use `no`; extended replies use `position`. The latter stay
in diagnostics and do not silently overwrite the former. Malformed lengths,
truncated fields and stale notifications are rejected without reproducing Android
exceptions or nonprogressing loops. Unrelated desk/OTA payloads do not become bed
features. A product-menu reload can remove transient capability pages.

Sleep links use compact UTF-8 JSON over the shared sleep envelope. Sequence wraps
from 254 to 1; each write is split at the link's negotiated MTU minus three. MM
writes without response and HJ with response. Required and nullable response
fields remain distinct. Time replies update sleep type/version metadata. Report
metadata retains fsize-driven followups and polling cancellation; physiological
report interpretation is excluded. Local sleep cancellation clears the session,
without sending the main bed's movement STOP.
An active report keeps its BLE link through the metadata handshake and compressed
transfer, even with quick handoff or a short idle timeout. Completion, cancellation,
disconnect, or a 60-second integration watchdog ends that hold. The watchdog is an
integration limit, not a protocol response interval.

#### Services

`adjustable_bed.richmat_app` exposes named configuration operations, validated
against the selected product and its current capabilities. Use normal device and
side targeting. The generated command reference and action form list operations;
no action accepts arbitrary packet bytes.

- Lighting: timer, palette/RGB and opacity, groove/color/breathe modes, power,
  therapy timer/color/sound and the local-music source.
- Alarms: single countdown, cancellation, explicit repeat slot, toggle, deletion,
  list refresh and time synchronization. Weekdays are Monday 0 through Sunday 6;
  7 means once. Full tables require an explicit slot and never emit Android's -1.
- Blanket: power, mode, selected-zone temperature, main delay, mite removal, all
  six settings flags and each zone's sleep schedule. Flags are child lock,
  protection, anti-freezing, tone, light and screen-off, in that order. A sleep
  schedule supplies its enabled flag, mode, start/end, repeat days, after-mode,
  delay and four stage temperatures. Schedule duration is validated together.
- Detection start/stop, anti-snore/off-bed settings, USB and cancellable automatic
  demos. Demo steps use known app enum names, sustain seconds and delay seconds.
- Separate sleep entry: `sleep_sync`, time/part/realtime queries, polling,
  sensitivity query, automatic anti-snore query/setting, report session, init and
  local cancellation. `sleep_snore` uses value 0 for query and 1 for setting.
  There is no valid sensitivity setter in this artifact.

#### Evidence

Row173's accepted Richmat 4.2.0 artifact provides every catalog, frame and lifecycle
value. `tests/test_richmat_app_vectors.py` preserves all 2,094 literal fixtures and
24 semantic cases. `tests/test_richmat_app.py` checks integration behavior.
Physical validation is for real beta/release users and is not implied here.
Artifact set SHA-256: `ca4b6ab4750585672889a6dd2e53b16a0e693804408eaa343ed6c6af4df2f0b7`.


## Notes

### Analysis provenance

- RMControl: APK Protocol Audit row018.
- Richmat MH: row055.
- HJBed: row121.
- Eshine: row106.
- Classic apps: row066.
- Good Vibe Sleep: row116.
- MLILY Control: row159.
- L&P legacy app: row019.
- Casper Base: row101, artifact set
  `2d21d42c17a7b5ae60c2403ff3654d80993e6d09f879cfe666c6d58270123f8b`.
- Hush Base: row126, artifact set
  `d24ad2c95ea839969a5406fa8219f62048386598152608554641586041293cd7`.
- The Richmat remotes, BedTech and L&P MlRM routes have no accepted report of
  their own; their frames are the pre-v5 controllers'.

### Galaxy Bed Control

**App:** [Galaxy Bed Control](https://play.google.com/store/apps/details?id=nl.starinternational.galaxy) 3.3.0 (330002), `nl.starinternational.galaxy`

**Status:** ❓ Needs testing. Primary arm64 app behavior is verified; hardware and firmware behavior remain unverified.

#### Setup

Choose **Galaxy Bed Control app** and the exact product code. Setup suggests the
app's advertisement mapping, then requires the selected product's own remote
when it opens a remote picker. MHRN offers H158B's HNRN/HQRN and H109's
M7RN/MJRN outcomes. V9RM and RNRN keep separate base, standard and splitHead
configurations. A constructor, Bluetooth UUID or similar name never substitutes
one product for another. Unsupported codes and the two standalone desk products
are refused. Each physical side keeps its own product and remote settings.

Discovery follows Galaxy's case-sensitive substring scan, with the platform's
prefix matchers as discovery hints. Manual setup remains available when a name
occurs only inside the advertisement. Advertisement prefix extraction uppercases
four characters; the MPE branch uses nine. Its explicit mappings are suggestions,
not protocol aliases. The Russian OTRM mapping is O0RM. Short names and unknown
products do not select a fallback layout. No app-owned PIN or authentication
handshake is required. A usable write and notification channel is required before
any command is admitted. Framing stays bound to the selected write characteristic; a later accepted service cannot change that characteristic’s dialect.

<!-- generated:galaxy-products -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Product / configuration | Controls / alarms | Sides | Light / repeat / snore | Remote picker |
|---|---|---|---|---|
| `6BRM` | 6 / 0 | 0 | yes / no / no | none |
| `6CRM` | 6 / 0 | 0 | yes / no / no | none |
| `6DRM` | 8 / 0 | 0 | yes / no / no | none |
| `6ERM` | 8 / 0 | 0 | yes / no / no | none |
| `6FRM` | 6 / 0 | 0 | yes / no / no | none |
| `A0RM` | 17 / 0 | 0 | yes / no / no | none |
| `A0RN` | 22 / 7 | 0 | yes / no / no | none |
| `A1RM` | 17 / 0 | 0 | yes / no / no | none |
| `A2RM` | 19 / 0 | 0 | yes / no / no | none |
| `A2RN` | 19 / 0 | 0 | yes / no / no | none |
| `A3RM` | 22 / 0 | 0 | yes / no / no | none |
| `A3RN` | 12 / 0 | 0 | yes / no / no | none |
| `A4RN` | 11 / 4 | 0 | yes / no / no | none |
| `A5RN` | 27 / 0 | 0 | yes / no / no | none |
| `A6RM` | 6 / 0 | 0 | yes / no / no | none |
| `A6RN` | 19 / 0 | 0 | yes / no / no | none |
| `A7RM` | 7 / 0 | 0 | yes / no / no | none |
| `A8RM` | 8 / 0 | 0 | yes / no / no | none |
| `A9RM` | 17 / 7 | 0 | yes / no / no | none |
| `A9RN` | 20 / 0 | 0 | yes / no / no | none |
| `AARM` | 16 / 0 | 0 | yes / no / no | none |
| `AARN` | 5 / 0 | 0 | yes / no / no | none |
| `ABRM` | 11 / 1 | 0 | yes / no / no | none |
| `ABRN` | 21 / 5 | 0 | yes / no / no | none |
| `ACRM` | 18 / 6 | 0 | yes / no / no | none |
| `ACRN` | 6 / 0 | 0, 1 | yes / no / no | none |
| `ADRM` | 22 / 6 | 0 | yes / no / no | none |
| `AERM` | 20 / 3 | 0 | yes / no / no | none |
| `AFRM` | 20 / 5 | 0 | yes / no / no | none |
| `AGRM` | 20 / 5 | 0 | yes / no / no | none |
| `AHRM` | 17 / 5 | 0 | yes / no / no | none |
| `AIRM` | 15 / 1 | 0 | yes / no / no | none |
| `AIRN` | 20 / 0 | 0 | yes / no / no | none |
| `AJRM` | 12 / 2 | 0 | yes / no / no | none |
| `AJRN` | 12 / 5 | 0 | yes / no / no | none |
| `AKRM` | 7 / 0 | 0 | yes / no / no | none |
| `ALRM` | 20 / 3 | 0 | yes / no / no | none |
| `AMRM` | 20 / 5 | 0 | yes / no / no | none |
| `ANRM` | 20 / 5 | 0 | yes / no / no | none |
| `ANRN` | 26 / 0 | 0 | yes / no / no | none |
| `AORM` | 8 / 0 | 0 | yes / no / no | none |
| `APRM` | 28 / 0 | 0 | yes / no / no | none |
| `APRN` | 7 / 0 | 0 | yes / no / no | none |
| `AQRM` | 14 / 0 | 0 | yes / no / no | none |
| `AQRN` | 12 / 0 | 0 | yes / no / no | none |
| `ARRM` | 7 / 0 | 0 | yes / no / no | none |
| `ASRM` | 2 / 0 | 0 | yes / no / no | none |
| `ASRN` | 9 / 0 | 0 | yes / no / no | none |
| `ATRM` | 12 / 0 | 0 | yes / no / no | none |
| `AURM` | 22 / 7 | 0 | yes / no / no | none |
| `AURN` | 11 / 5 | 0 | yes / no / no | none |
| `AVRM` | 8 / 0 | 0 | yes / no / no | none |
| `AWRM` | 21 / 0 | 0 | yes / no / no | none |
| `AXRM` | 21 / 0 | 0 | yes / no / no | none |
| `AXRN` | 9 / 0 | 0 | yes / no / no | none |
| `AYRM` | 22 / 2 | 0 | yes / no / no | none |
| `AYRN` | 12 / 1 | 0 | yes / no / no | none |
| `AZRM` | 7 / 0 | 0 | yes / no / no | none |
| `AZRN` | 12 / 0 | 0 | yes / no / no | none |
| `B0RM` | 7 / 0 | 0 | yes / no / no | none |
| `B1RM` | 12 / 0 | 0 | yes / no / no | none |
| `B2RM` | 2 / 0 | 0 | yes / no / no | none |
| `B2RN` | 22 / 0 | 0 | yes / no / no | none |
| `B3RM` | 2 / 0 | 0 | yes / no / no | none |
| `B4RM` | 22 / 5 | 0 | yes / no / no | none |
| `B5RM` | 8 / 2 | 0 | yes / no / no | none |
| `B5RN` | 19 / 4 | 0 | yes / no / no | none |
| `B6RM` | 6 / 0 | 0 | yes / no / no | none |
| `B7RM` | 7 / 0 | 0 | yes / no / no | none |
| `B7RN` | 11 / 0 | 0 | yes / no / no | none |
| `B8RM` | 8 / 0 | 0 | yes / no / no | none |
| `B8RN` | 22 / 0 | 0 | yes / no / no | none |
| `B8TT` | 8 / 0 | 0 | yes / no / no | none |
| `B9RM` | 8 / 1 | 0 | yes / no / no | none |
| `B9TT` | 12 / 0 | 0 | yes / no / no | none |
| `BARM` | 4 / 0 | 0 | yes / no / no | none |
| `BBRM` | 5 / 0 | 0 | yes / no / no | none |
| `BBRN` | 17 / 0 | 0 | yes / no / no | none |
| `BCRM` | 7 / 1 | 0 | yes / no / no | none |
| `BDRM` | 22 / 4 | 0 | yes / no / no | none |
| `BERM` | 24 / 0 | 0 | yes / no / no | none |
| `BFRM` | 11 / 0 | 0 | yes / no / no | none |
| `BGRM` | 22 / 0 | 0 | yes / no / no | none |
| `BHRM` | 20 / 0 | 0 | yes / no / no | none |
| `BIRM` | 22 / 0 | 0 | yes / no / no | none |
| `BJRM` | 11 / 1 | 0 | yes / no / no | none |
| `BKRM` | 12 / 0 | 0 | yes / no / no | none |
| `BLRM` | 22 / 0 | 0 | yes / no / no | none |
| `BMRM` | 12 / 0 | 0 | yes / no / no | none |
| `BNRM` | 22 / 0 | 0 | yes / no / no | none |
| `BORM` | 21 / 0 | 0 | yes / no / no | none |
| `BPRM` | 8 / 0 | 0 | yes / no / no | none |
| `BQRM` | 7 / 0 | 0 | yes / no / no | none |
| `BRRM` | 20 / 1 | 0 | yes / no / no | none |
| `BSRM` | 7 / 0 | 0 | yes / no / no | none |
| `BTRM` | 6 / 0 | 0, 1, 2 | yes / no / no | none |
| `BURM` | 22 / 7 | 0, 1, 2 | yes / no / no | none |
| `BVRM` | 12 / 0 | 0, 1, 2 | yes / no / no | none |
| `BWRM` | 7 / 1 | 0, 1, 2 | yes / no / no | none |
| `BWRN` | 11 / 1 | 0 | yes / no / no | none |
| `BXRM` | 8 / 0 | 0 | yes / no / no | none |
| `BXRN` | 11 / 1 | 0 | yes / no / no | none |
| `BYRM` | 8 / 0 | 0 | yes / no / no | none |
| `BZRM` | 22 / 0 | 0 | yes / no / no | none |
| `C0RM` | 10 / 1 | 0 | yes / no / no | none |
| `C1RM` | 7 / 0 | 0 | yes / no / no | none |
| `C1RN` | 11 / 4 | 0 | yes / no / no | none |
| `C2RM` | 35 / 0 | 0 | yes / no / no | none |
| `C2RN` | 22 / 0 | 0 | yes / no / no | none |
| `C3RM` | 9 / 0 | 0 | yes / no / no | none |
| `C4RM` | 20 / 0 | 0 | yes / no / no | none |
| `C5RM` | 20 / 0 | 0 | yes / no / no | none |
| `C6RM` | 10 / 0 | 0 | yes / no / no | none |
| `C7RM` | 16 / 0 | 0 | yes / no / no | none |
| `C7RN` | 20 / 0 | 0 | yes / no / no | none |
| `C8RM` | 9 / 0 | 0 | yes / no / no | none |
| `C8RN` | 20 / 0 | 0 | yes / no / no | none |
| `C9RM` | 25 / 0 | 0 | yes / no / no | none |
| `C9RN` | 22 / 5 | 0 | yes / no / no | none |
| `CARM` | 20 / 0 | 0 | yes / no / no | none |
| `CARN` | 22 / 5 | 0 | yes / no / no | none |
| `CBRM` | 22 / 5 | 0 | yes / no / no | none |
| `CBRN` | 20 / 6 | 0 | yes / no / no | none |
| `CCRM` | 9 / 0 | 0 | yes / no / no | none |
| `CCRN` | 11 / 0 | 0 | yes / no / no | none |
| `CDRM` | 12 / 0 | 0 | yes / no / no | none |
| `CDRN` | 22 / 0 | 0 | yes / no / no | none |
| `CERM` | 12 / 5 | 0 | yes / no / no | none |
| `CFRN` | 20 / 0 | 0 | yes / no / no | none |
| `CGRM` | 20 / 0 | 0 | yes / no / no | none |
| `CHRM` | 6 / 0 | 0 | yes / no / no | none |
| `CHRN` | 7 / 0 | 0 | yes / no / no | none |
| `CIRM` | 19 / 0 | 0 | yes / no / no | none |
| `CJRM` | 17 / 0 | 0 | yes / no / no | none |
| `CKRM` | 17 / 0 | 0 | yes / no / no | none |
| `CLRM` | 20 / 0 | 0 | yes / no / no | none |
| `CLRN` | 20 / 0 | 0 | yes / no / no | none |
| `CMRM` | 21 / 1 | 0 | yes / no / no | none |
| `CMRN` | 2 / 0 | 0 | yes / no / no | none |
| `CNRM` | 9 / 0 | 0 | yes / no / no | none |
| `CORM` | 17 / 0 | 0 | yes / no / no | none |
| `CORN` | 18 / 0 | 0 | yes / no / no | none |
| `CPRM` | 17 / 0 | 0 | yes / no / no | none |
| `CPRN` | 11 / 0 | 0 | yes / no / no | none |
| `CQRM` | 17 / 0 | 0 | yes / no / no | none |
| `CRRM` | 9 / 0 | 0 | yes / no / no | none |
| `CSRM` | 21 / 0 | 0 | yes / no / no | none |
| `CTRM` | 21 / 0 | 0 | yes / no / no | none |
| `CURM` | 21 / 0 | 0 | yes / no / no | none |
| `CVRM` | 11 / 0 | 0 | yes / no / no | none |
| `CVRN` | 8 / 3 | 0 | yes / no / no | none |
| `CWRM` | 20 / 4 | 0 | yes / no / no | none |
| `CXRM` | 11 / 0 | 0 | yes / no / no | none |
| `CXRN` | 17 / 0 | 0 | yes / no / no | none |
| `CYRM` | 22 / 0 | 0 | yes / no / no | none |
| `CYRN` | 20 / 0 | 0 | yes / no / no | none |
| `CZRM` | 22 / 0 | 0 | yes / no / no | none |
| `D0RM` | 19 / 0 | 0 | yes / no / no | none |
| `D1RM` | 13 / 0 | 0 | yes / no / no | none |
| `D2RM` | 18 / 0 | 0 | yes / no / no | none |
| `D3RM` | 18 / 4 | 0 | yes / no / no | none |
| `D4RM` | 21 / 0 | 0 | yes / no / no | none |
| `D5RM` | 2 / 0 | 0 | yes / no / no | none |
| `D6RM` | 2 / 0 | 0 | yes / no / no | none |
| `D7RM` | 18 / 1 | 0 | yes / no / no | none |
| `D8RM` | 6 / 0 | 0 | yes / no / no | none |
| `D8RN` | 22 / 0 | 0, 1 | yes / no / no | none |
| `D9RM` | 13 / 0 | 0 | yes / no / no | none |
| `DARM` | 17 / 7 | 0 | yes / no / no | none |
| `DBRM` | 11 / 5 | 0 | yes / no / no | none |
| `DBRN` | 20 / 0 | 0 | yes / no / no | none |
| `DCRM` | 22 / 0 | 0 | yes / no / no | none |
| `DCRN` | 9 / 0 | 0 | yes / no / no | none |
| `DDRM` | 12 / 7 | 0 | yes / no / no | none |
| `DERM` | 19 / 0 | 0 | yes / no / no | none |
| `DFRM` | 22 / 6 | 0 | yes / no / no | none |
| `DFRN` | 21 / 0 | 0 | yes / no / no | none |
| `DGRM` | 9 / 2 | 0 | yes / no / no | none |
| `DGRN` | 9 / 0 | 0 | yes / no / no | none |
| `DHRM` | 24 / 0 | 0, 1 | yes / no / no | none |
| `DHRN` | 9 / 0 | 0 | yes / no / no | none |
| `DIRM` | 24 / 0 | 0, 1 | yes / no / no | none |
| `DJRM` | 20 / 0 | 0 | yes / no / no | none |
| `DKRM` | 20 / 0 | 0 | yes / no / no | none |
| `DLRM` | 20 / 0 | 0 | yes / no / no | none |
| `DMRM` | 12 / 0 | 0 | yes / no / no | none |
| `DMRN` | 22 / 0 | 0 | yes / no / no | none |
| `DNRM` | 11 / 0 | 0 | yes / no / no | none |
| `DPRM` | 22 / 5 | 0 | yes / no / no | none |
| `DQRM` | 11 / 0 | 0, 1 | yes / no / no | none |
| `DRRM` | 8 / 0 | 0, 1, 2 | yes / no / no | none |
| `DSRM` | 13 / 0 | 0 | yes / no / no | none |
| `DSRN` | 20 / 0 | 0 | yes / no / no | none |
| `DTRM` | 9 / 0 | 0 | yes / no / no | none |
| `DURM` | 11 / 0 | 0 | yes / no / no | none |
| `DVRM` | 15 / 0 | 0 | yes / no / no | none |
| `DWRM` | 20 / 0 | 0, 1 | yes / no / no | none |
| `DWRN` | 18 / 0 | 0 | yes / no / no | none |
| `DXRM` | 7 / 0 | 0 | yes / no / no | none |
| `DYRM` | 2 / 0 | 0 | yes / no / no | none |
| `DZRM` | 20 / 6 | 0 | yes / no / no | none |
| `E0RM` | 3 / 0 | 0 | yes / no / no | none |
| `E1RM` | 22 / 0 | 0 | yes / no / no | none |
| `E2RM` | 3 / 0 | 0 | yes / no / no | none |
| `E3RM` | 17 / 0 | 0 | yes / no / no | none |
| `E4RM` | 11 / 0 | 0 | yes / no / no | none |
| `E5RM` | 21 / 7 | 0 | yes / no / no | none |
| `E6RM` | 17 / 0 | 0 | yes / no / no | none |
| `E7RM` | 11 / 0 | 0 | yes / no / no | none |
| `E8RM` | 11 / 0 | 0 | yes / no / no | none |
| `E9RM` | 20 / 0 | 0 | yes / no / no | none |
| `ECRM` | 11 / 0 | 0, 1 | yes / no / no | none |
| `EDRM` | 22 / 0 | 0 | yes / no / no | none |
| `EFRM` | 19 / 0 | 0 | yes / no / no | none |
| `EGRM` | 11 / 0 | 0 | yes / no / no | none |
| `EIRM` | 11 / 0 | 0 | yes / no / no | none |
| `EJRM` | 7 / 0 | 0 | yes / no / no | none |
| `EKRM` | 5 / 0 | 0, 1, 2 | yes / no / no | none |
| `EKRN` | 11 / 4 | 0 | yes / no / no | none |
| `EMRM` | 22 / 0 | 0 | yes / no / no | none |
| `ENRM` | 17 / 0 | 0 | yes / no / no | none |
| `EORM` | 20 / 0 | 0 | yes / no / no | none |
| `EORN` | 13 / 0 | 0 | yes / no / no | none |
| `EPRM` | 9 / 0 | 0, 1 | yes / no / no | none |
| `EQRM` | 12 / 0 | 0 | yes / no / no | none |
| `ERRM` | 8 / 1 | 0 | yes / no / no | none |
| `ESRM` | 22 / 0 | 0 | yes / no / no | none |
| `ESRN` | 11 / 1 | 0 | yes / no / no | none |
| `ETRM` | 21 / 8 | 0 | yes / no / no | none |
| `ETRN` | 21 / 0 | 0 | yes / no / no | none |
| `EURM` | 19 / 0 | 0 | yes / no / no | none |
| `EURN` | 22 / 5 | 0, 1 | yes / no / no | none |
| `EVRM` | 20 / 0 | 0 | yes / no / no | none |
| `EVRN` | 21 / 0 | 0 | yes / no / no | none |
| `EWRM` | 20 / 0 | 0 | yes / no / no | none |
| `EXRM` | 20 / 0 | 0 | yes / no / no | none |
| `EXRN` | 21 / 7 | 0 | yes / no / no | none |
| `EYRM` | 7 / 0 | 0 | yes / no / no | none |
| `EYRN` | 21 / 7 | 0 | yes / no / no | none |
| `EZRM` | 8 / 0 | 0 | yes / no / no | none |
| `F0RM` | 20 / 0 | 0 | yes / no / no | none |
| `F1RM` | 20 / 0 | 0 | yes / no / no | none |
| `F2RM` | 3 / 0 | 0 | yes / no / no | none |
| `F3RM` | 20 / 0 | 0 | yes / no / no | none |
| `F3RN` | 21 / 0 | 0 | yes / no / no | none |
| `F4RM` | 22 / 0 | 0 | yes / no / no | none |
| `F4RN` | 21 / 4 | 0 | yes / no / no | none |
| `F5RM` | 20 / 0 | 0, 1 | yes / no / no | none |
| `F6RM` | 9 / 0 | 0 | yes / no / no | none |
| `F7RM` | 20 / 0 | 0 | yes / no / no | none |
| `F8RM` | 11 / 6 | 0 | yes / no / no | none |
| `F9RM` | 23 / 0 | 0 | yes / no / no | none |
| `FARM` | 20 / 6 | 0 | yes / no / no | none |
| `FBRM` | 11 / 0 | 0 | yes / no / no | none |
| `FCRM` | 13 / 0 | 0 | yes / no / no | none |
| `FCRN` | 21 / 0 | 0 | no / no / no | none |
| `FDRM` | 20 / 7 | 0 | yes / no / no | none |
| `FERM` | 20 / 5 | 0 | yes / no / no | none |
| `FFRM` | 17 / 8 | 0 | yes / no / no | none |
| `FFRN` | 7 / 0 | 0 | yes / no / no | none |
| `FGRM` | 24 / 0 | 0 | yes / no / no | none |
| `FHRM` | 21 / 5 | 0 | yes / no / no | none |
| `FIRM` | 22 / 0 | 0 | yes / no / no | none |
| `FJRM` | 8 / 0 | 0 | yes / no / no | none |
| `FKRM` | 20 / 0 | 0 | yes / no / no | none |
| `FLRM` | 9 / 0 | 0 | yes / no / no | none |
| `FMRM` | 24 / 0 | 0 | yes / no / no | none |
| `FNRM` | 25 / 3 | 0, 1 | yes / no / no | none |
| `FPRM` | 20 / 0 | 0 | yes / no / no | none |
| `FPRN` | 22 / 6 | 0 | yes / no / no | none |
| `FQRM` | 20 / 0 | 0 | yes / no / no | none |
| `FRRM` | 22 / 0 | 0 | yes / no / no | none |
| `FSRM` | 11 / 4 | 0 | yes / no / no | none |
| `FTRM` | 20 / 0 | 0 | yes / no / no | none |
| `FTRN` | 8 / 2 | 0 | yes / yes / no | none |
| `FURM` | 9 / 3 | 0 | yes / no / no | none |
| `FURN` | 20 / 4 | 0 | yes / no / no | none |
| `FVRM` | 9 / 1 | 0 | yes / no / no | none |
| `FXRM` | 9 / 3 | 0 | yes / no / no | none |
| `FYRM` | 11 / 3 | 0 | yes / no / no | none |
| `FZRM` | 21 / 5 | 0 | yes / no / no | none |
| `G1RN` | 24 / 8 | 0 | yes / no / no | none |
| `G2RM` | 11 / 2 | 0 | yes / no / no | none |
| `G2RN` | 21 / 1 | 0 | yes / yes / no | none |
| `G3RM` | 21 / 5 | 0 | yes / no / no | none |
| `G4RM` | 9 / 0 | 0, 1 | yes / no / no | none |
| `G5RM` | 17 / 0 | 0 | yes / no / no | none |
| `G5RN` | 22 / 6 | 0 | yes / no / no | none |
| `G6RM` | 11 / 0 | 0 | yes / no / no | none |
| `G6RN` | 20 / 4 | 0 | no / no / no | none |
| `G7RM` | 20 / 0 | 0 | yes / no / no | none |
| `G7RN` | 20 / 2 | 0 | no / no / no | none |
| `G8RM` | 12 / 0 | 0 | yes / no / no | none |
| `G9RM` | 21 / 5 | 0 | yes / no / no | none |
| `G9RN` | 23 / 4 | 0 | no / no / no | none |
| `GARM` | 24 / 0 | 0 | yes / no / no | none |
| `GARN` | 12 / 4 | 0 | no / no / no | none |
| `GBRM` | 11 / 0 | 0 | yes / no / no | none |
| `GBRN` | 7 / 0 | 0 | no / no / no | none |
| `GCRM` | 22 / 0 | 0 | yes / no / no | none |
| `GCRN` | 3 / 0 | 0 | no / no / no | none |
| `GDRM` | 24 / 0 | 0 | yes / no / no | none |
| `GERM` | 22 / 0 | 0 | yes / no / no | none |
| `GERN` | 9 / 3 | 0 | no / no / no | none |
| `GFRM` | 22 / 0 | 0 | yes / no / no | none |
| `GFRN` | 11 / 3 | 0 | no / no / no | none |
| `GGRM` | 22 / 0 | 0 | yes / no / no | none |
| `GHRM` | 20 / 4 | 0, 1 | yes / no / no | none |
| `GJRM` | 20 / 6 | 0 | yes / no / no | none |
| `GKRM` | 24 / 0 | 0 | yes / no / no | none |
| `GLRN` | 11 / 4 | 0 | yes / no / no | none |
| `GMRM` | 6 / 0 | 0 | yes / no / no | none |
| `GNRM` | 11 / 0 | 0 | yes / no / no | none |
| `GNRN` | 12 / 0 | 0 | no / no / no | none |
| `GORM` | 20 / 0 | 0, 1, 2 | yes / no / no | none |
| `GPRM` | 11 / 0 | 0 | yes / no / no | none |
| `GRRM` | 7 / 0 | 0 | yes / no / no | none |
| `GRRN` | 12 / 0 | 0 | no / no / no | none |
| `GSRM` | 21 / 5 | 0, 1 | yes / no / no | none |
| `GTRM` | 20 / 6 | 0 | yes / no / no | none |
| `GURM` | 11 / 0 | 0 | yes / no / no | none |
| `GWRM` | 7 / 0 | 0 | yes / no / no | none |
| `GXRM` | 20 / 0 | 0 | yes / no / no | none |
| `GXRN` | 2 / 0 | 0 | no / no / no | none |
| `GYRM` | 19 / 0 | 0 | yes / no / no | none |
| `GZRM` | 11 / 0 | 0 | yes / no / no | none |
| `GZRN` | 4 / 0 | 0 | no / no / no | none |
| `H2RM` | 22 / 0 | 0 | yes / no / no | none |
| `H3RM` | 12 / 0 | 0 | yes / no / no | none |
| `H5RM` | 19 / 4 | 0 | yes / no / no | none |
| `H6RM` | 10 / 0 | 0 | yes / no / no | none |
| `H7RM` | 22 / 0 | 0 | yes / no / no | none |
| `H8RM` | 22 / 8 | 0 | yes / no / no | none |
| `H9RM` | 12 / 0 | 0 | yes / no / no | none |
| `HARM` | 19 / 0 | 0 | yes / no / no | none |
| `HBRM` | 20 / 0 | 0 | yes / no / no | none |
| `HCRM` | 21 / 0 | 0 | yes / no / no | none |
| `HCRN` | 11 / 0 | 0 | yes / no / no | none |
| `HDRM` | 11 / 0 | 0 | yes / no / no | none |
| `HERM` | 17 / 0 | 0 | yes / no / no | none |
| `HKRM` | 12 / 0 | 0, 1 | yes / no / no | none |
| `HLRM` | 20 / 0 | 0 | yes / no / no | none |
| `HMRM` | 22 / 0 | 0 | yes / no / no | none |
| `HNRM` | 21 / 0 | 0 | yes / no / no | none |
| `HNRN` | 11 / 2 | 0 | yes / yes / yes | none |
| `HPRM` | 21 / 0 | 0 | yes / no / no | none |
| `HQRM` | 21 / 0 | 0 | yes / no / no | none |
| `HQRN` | 14 / 2 | 0 | yes / yes / yes | none |
| `HRRM` | 21 / 5 | 0 | yes / no / no | none |
| `HSRN` | 18 / 4 | 0 | yes / yes / yes | none |
| `HTRM` | 22 / 8 | 0 | yes / no / no | none |
| `HURM` | 8 / 0 | 0 | yes / no / no | none |
| `HURN` | 21 / 4 | 0 | yes / yes / yes | none |
| `HVRM` | 24 / 0 | 0 | yes / no / no | none |
| `HWRM` | 22 / 0 | 0 | yes / no / no | none |
| `HXRM` | 22 / 0 | 0 | yes / no / no | none |
| `HYRM` | 23 / 0 | 0 | yes / no / no | none |
| `HZRM` | 11 / 3 | 0 | yes / no / no | none |
| `I0RM` | 19 / 0 | 0 | yes / no / no | none |
| `I1RM` | 20 / 5 | 0 | yes / no / no | none |
| `I2RM` | 19 / 0 | 0 | yes / no / no | none |
| `I3RM` | 14 / 0 | 0 | yes / no / no | none |
| `I4RM` | 19 / 0 | 0 | yes / no / no | none |
| `I5RM` | 22 / 0 | 0 | yes / no / no | none |
| `I6RM` | 5 / 0 | 0 | yes / no / no | none |
| `I7RM` | 15 / 0 | 0 | yes / no / no | none |
| `I8RM` | 16 / 0 | 0 | yes / no / no | none |
| `I9RM` | 9 / 0 | 0 | yes / no / no | none |
| `IARM` | 17 / 0 | 0 | yes / no / no | none |
| `IBRM` | 19 / 4 | 0 | yes / no / no | none |
| `ICRM` | 16 / 0 | 0 | yes / no / no | none |
| `IDRM` | 12 / 0 | 0 | yes / no / no | none |
| `IERM` | 16 / 0 | 0 | yes / no / no | none |
| `IFRM` | 9 / 0 | 0 | yes / no / no | none |
| `IGRM` | 17 / 0 | 0 | yes / no / no | none |
| `IHRM` | 16 / 0 | 0 | yes / no / no | none |
| `IIRM` | 13 / 0 | 0 | yes / no / no | none |
| `IJRM` | 3 / 0 | 0 | yes / no / no | none |
| `IKRM` | 5 / 0 | 0 | yes / no / no | none |
| `ILRM` | 6 / 0 | 0 | yes / no / no | none |
| `IMRM` | 5 / 0 | 0 | yes / no / no | none |
| `INRM` | 8 / 0 | 0 | yes / no / no | none |
| `IORM` | 12 / 0 | 0 | yes / no / no | none |
| `IPRM` | 7 / 0 | 0 | yes / no / no | none |
| `IQRM` | 11 / 1 | 0 | yes / no / no | none |
| `IRRM` | 19 / 0 | 0 | yes / no / no | none |
| `ISRM` | 4 / 0 | 0 | yes / no / no | none |
| `J2RM` | 22 / 0 | 0 | yes / no / no | none |
| `J2RN` | 16 / 0 | 0 | no / no / no | none |
| `J3RM` | 22 / 0 | 0 | yes / no / no | none |
| `J4RM` | 8 / 0 | 0 | yes / no / no | none |
| `J5RM` | 11 / 0 | 0 | yes / no / no | none |
| `J5RN` | 20 / 0 | 0 | yes / no / no | none |
| `J6RM` | 11 / 0 | 0 | yes / no / no | none |
| `J7RM` | 22 / 0 | 0, 1 | yes / no / no | none |
| `J9RM` | 22 / 0 | 0 | yes / no / no | none |
| `JBRM` | 20 / 0 | 0 | yes / no / no | none |
| `JBRN` | 21 / 0 | 0 | yes / no / no | none |
| `JCRN` | 15 / 4 | 0 | yes / no / no | none |
| `JDRM` | 18 / 0 | 0 | yes / no / no | none |
| `JDRN` | 25 / 5 | 0 | yes / no / no | none |
| `JERM` | 16 / 0 | 0 | yes / no / no | none |
| `JFRM` | 18 / 0 | 0 | yes / no / no | none |
| `JGRM` | 20 / 0 | 0 | yes / no / no | none |
| `JHRM` | 9 / 0 | 0 | yes / no / no | none |
| `JJRM` | 5 / 0 | 0 | yes / no / no | none |
| `JKRM` | 20 / 0 | 0 | yes / no / no | none |
| `JLRM` | 20 / 0 | 0 | yes / no / no | none |
| `JMRM` | 19 / 0 | 0, 1 | yes / no / no | none |
| `JNRM` | 20 / 0 | 0 | yes / no / no | none |
| `JPRM` | 21 / 0 | 0 | yes / no / no | none |
| `JPRN` | 20 / 0 | 0, 1 | yes / no / no | none |
| `JQRM` | 9 / 3 | 0, 1 | yes / no / no | none |
| `JRRM` | 21 / 8 | 0 | yes / no / no | none |
| `JSRM` | 20 / 0 | 0 | yes / no / no | none |
| `JTRN` | 11 / 0 | 0 | yes / no / no | none |
| `JURN` | 20 / 0 | 0 | yes / no / no | none |
| `JWRM` | 21 / 6 | 0 | yes / no / no | none |
| `JZRM` | 7 / 0 | 0 | yes / no / no | none |
| `K2RM` | 8 / 0 | 0 | yes / no / no | none |
| `K5RM` | 27 / 0 | 0 | yes / no / no | none |
| `K6RM` | 19 / 5 | 0 | yes / no / no | none |
| `K6RN` | 4 / 0 | 0 | yes / no / no | none |
| `K7RM` | 12 / 0 | 0 | yes / no / no | none |
| `K8RM` | 12 / 0 | 0 | yes / no / no | none |
| `K9RM` | 9 / 0 | 0 | yes / no / no | none |
| `KARM` | 10 / 0 | 0, 1 | yes / no / no | none |
| `KBRM` | 24 / 0 | 0 | yes / no / no | none |
| `KBRN` | 22 / 5 | 0, 1 | yes / yes / no | none |
| `KCRM` | 24 / 0 | 0 | yes / no / no | none |
| `KCRN` | 21 / 6 | 0 | yes / yes / no | none |
| `KERM` | 22 / 5 | 0 | yes / no / no | none |
| `KFRM` | 22 / 7 | 0 | yes / no / no | none |
| `KGRM` | 22 / 0 | 0 | yes / no / no | none |
| `KGRN` | 22 / 5 | 0 | yes / yes / no | none |
| `KHRM` | 12 / 0 | 0 | yes / no / no | none |
| `KJRM` | 11 / 0 | 0 | yes / no / no | none |
| `KKRM` | 11 / 4 | 0 | yes / no / no | none |
| `KLRN` | 3 / 0 | 0 | yes / no / no | none |
| `KMRM` | 22 / 0 | 0 | yes / no / no | none |
| `KMRN` | 2 / 0 | 0 | yes / no / no | none |
| `KNRM` | 11 / 0 | 0 | yes / no / no | none |
| `KPRM` | 20 / 4 | 0 | yes / no / no | none |
| `KPRN` | 11 / 3 | 0 | yes / yes / no | none |
| `KQRM` | 12 / 1 | 0 | yes / no / no | none |
| `KQRN` | 11 / 2 | 0 | yes / yes / no | none |
| `KRRM` | 19 / 2 | 0 | yes / no / no | none |
| `KRRN` | 21 / 5 | 0 | yes / yes / no | none |
| `KSRN` | 19 / 3 | 0 | yes / yes / no | none |
| `KURM` | 12 / 0 | 0, 1 | yes / no / no | none |
| `KVRM` | 21 / 0 | 0 | yes / no / no | none |
| `KWRN` | 11 / 4 | 0 | yes / yes / no | none |
| `KXRM` | 18 / 0 | 0 | yes / no / no | none |
| `KYRM` | 11 / 0 | 0 | yes / no / no | none |
| `L2RN` | 22 / 0 | 0 | yes / no / no | none |
| `L3RM` | 20 / 7 | 0 | yes / no / no | none |
| `L4RM` | 9 / 0 | 0 | yes / no / no | none |
| `L5RM` | 11 / 0 | 0, 1, 2 | yes / no / no | none |
| `L7RN` | 23 / 0 | 0 | no / no / no | none |
| `L8RM` | 11 / 0 | 0 | yes / no / no | none |
| `L9RM` | 20 / 0 | 0 | yes / no / no | none |
| `L9RN` | 22 / 5 | 0, 1 | yes / yes / no | none |
| `LARN` | 11 / 3 | 0 | yes / yes / no | none |
| `LBRN` | 11 / 4 | 0 | yes / yes / no | none |
| `LCRM` | 20 / 7 | 0 | yes / no / no | none |
| `LCRN` | 21 / 5 | 0 | yes / yes / no | none |
| `LDRM` | 20 / 0 | 0 | yes / no / no | none |
| `LDRN` | 21 / 3 | 0 | yes / yes / no | none |
| `LERN` | 12 / 4 | 0, 1 | yes / yes / no | none |
| `LFRM` | 19 / 5 | 0 | yes / no / no | none |
| `LGRM` | 20 / 2 | 0 | yes / no / no | none |
| `LJRM` | 9 / 3 | 0 | yes / no / no | none |
| `LKRN` | 22 / 5 | 0, 1 | yes / yes / no | none |
| `LLRM` | 7 / 0 | 0 | yes / no / no | none |
| `LLRN` | 21 / 5 | 0 | yes / yes / no | none |
| `LMRM` | 3 / 0 | 0 | yes / no / no | none |
| `LNRM` | 7 / 0 | 0 | yes / no / no | none |
| `LQRM` | 22 / 10 | 0 | yes / no / no | none |
| `LRRM` | 12 / 5 | 0 | yes / no / no | none |
| `LSRM` | 11 / 4 | 0 | yes / no / no | none |
| `LURM` | 10 / 0 | 0 | yes / no / no | none |
| `LVRM` | 21 / 5 | 0 | yes / no / no | none |
| `LWRM` | 9 / 0 | 0 | yes / no / no | none |
| `LXRM` | 7 / 0 | 0 | yes / no / no | none |
| `LYRM` | 22 / 3 | 0 | yes / no / no | none |
| `LZRM` | 22 / 0 | 0 | yes / no / no | none |
| `M2RM` | 20 / 0 | 0 | yes / no / no | none |
| `M3RM` | 22 / 0 | 0 | yes / no / no | none |
| `M4RM` | 7 / 0 | 0 | yes / no / no | none |
| `M4RN` | 9 / 3 | 0 | yes / no / no | none |
| `M5RM` | 19 / 0 | 0 | yes / no / no | none |
| `M5RN` | 21 / 5 | 0 | yes / no / no | none |
| `M6RM` | 17 / 0 | 0 | yes / no / no | none |
| `M6RN` | 21 / 5 | 0 | yes / no / no | none |
| `M7RM` | 11 / 0 | 0 | yes / no / no | none |
| `M7RN` | 14 / 3 | 0 | yes / yes / yes | none |
| `M8RM` | 19 / 5 | 0 | yes / no / no | none |
| `M9RM` | 9 / 0 | 0 | yes / no / no | none |
| `M9RN` | 21 / 0 | 0 | no / no / no | none |
| `MARM` | 11 / 0 | 0 | yes / no / no | none |
| `MBRN` | 11 / 4 | 0 | yes / no / no | none |
| `MCRM` | 11 / 0 | 0 | yes / no / no | none |
| `MDRM` | 11 / 0 | 0 | yes / no / no | none |
| `MDRN` | 10 / 2 | 0 | yes / yes / no | none |
| `MERM` | 9 / 0 | 0 | yes / no / no | none |
| `MFRM` | 11 / 0 | 0 | yes / no / no | none |
| `MGRM` | 9 / 0 | 0 | yes / no / no | none |
| `MHRN` | 0 / 0 | 0 | yes / no / no | HNRN, HQRN, M7RN, MJRN |
| `MJRN` | 17 / 3 | 0 | yes / yes / yes | none |
| `MLRM` | 19 / 0 | 0 | yes / no / no | none |
| `MMRM` | 24 / 0 | 0 | yes / no / no | none |
| `MRRM` | 22 / 0 | 0 | yes / no / no | none |
| `MVRN` | 20 / 5 | 0 | yes / yes / no | none |
| `MXRN` | 20 / 9 | 0 | yes / yes / no | none |
| `MZRN` | 0 / 0 | 0 | yes / no / no | PGRN, PHRN |
| `N4RN` | 6 / 2 | 0 | yes / yes / no | none |
| `N6RN` | 22 / 4 | 0 | yes / yes / no | none |
| `N7RN` | 23 / 5 | 0, 1 | yes / yes / no | none |
| `NTRN` | 0 / 0 | 0 | yes / no / no | FFRN, NURN |
| `NURN` | 6 / 0 | 0 | yes / no / no | none |
| `O0RM` | 20 / 5 | 0 | yes / no / no | none |
| `O1RM` | 22 / 0 | 0 | yes / no / no | none |
| `O2RM` | 22 / 0 | 0 | yes / no / no | none |
| `O3RM` | 22 / 0 | 0 | yes / no / no | none |
| `O4RM` | 22 / 0 | 0 | yes / no / no | none |
| `O5RM` | 22 / 0 | 0 | yes / no / no | none |
| `O6RM` | 20 / 0 | 0 | yes / no / no | none |
| `O7RM` | 22 / 7 | 0 | yes / no / no | none |
| `O8RM` | 20 / 0 | 0 | yes / no / no | none |
| `O9RM` | 22 / 5 | 0 | yes / no / no | none |
| `OARM` | 22 / 6 | 0 | yes / no / no | none |
| `OMRM` | 22 / 0 | 0 | yes / no / no | none |
| `ONRM` | 21 / 0 | 0 | yes / no / no | none |
| `OORM` | 21 / 0 | 0 | yes / no / no | none |
| `OPRM` | 22 / 0 | 0 | yes / no / no | none |
| `OQRM` | 22 / 0 | 0 | yes / no / no | none |
| `ORRM` | 22 / 0 | 0 | yes / no / no | none |
| `OSRM` | 22 / 0 | 0 | yes / no / no | none |
| `OTRM` | 20 / 5 | 0 | yes / no / no | none |
| `OURM` | 4 / 0 | 0 | yes / no / no | none |
| `OVRM` | 2 / 0 | 0 | yes / no / no | none |
| `OWRM` | 6 / 0 | 0 | yes / no / no | none |
| `OXRM` | 22 / 0 | 0 | yes / no / no | none |
| `OYRM` | 19 / 4 | 0 | yes / no / no | none |
| `OZRM` | 21 / 0 | 0 | yes / no / no | none |
| `P0RM` | 21 / 0 | 0 | yes / no / no | none |
| `P1RM` | 22 / 2 | 0 | yes / no / no | none |
| `P2RM` | 17 / 0 | 0 | yes / no / no | none |
| `P3RM` | 12 / 0 | 0 | yes / no / no | none |
| `P3RN` | 8 / 0 | 0 | yes / no / no | none |
| `P4RM` | 21 / 7 | 0 | yes / no / no | none |
| `P5RM` | 22 / 0 | 0 | yes / no / no | none |
| `P6RM` | 17 / 0 | 0 | yes / no / no | none |
| `P9RM` | 8 / 0 | 0 | yes / no / no | none |
| `P9RN` | 15 / 6 | 0, 1 | yes / yes / no | none |
| `PARN` | 20 / 0 | 0, 1 | yes / no / no | none |
| `PGRN` | 8 / 0 | 0 | yes / no / no | none |
| `PHRN` | 8 / 0 | 0 | yes / no / no | none |
| `PLRN` | 20 / 4 | 0 | yes / no / no | none |
| `PNRN` | 20 / 6 | 0 | yes / no / no | none |
| `PYRN` | 6 / 0 | 0 | yes / no / no | none |
| `QARN` | 8 / 2 | 0 | yes / no / no | none |
| `QGRN` | 9 / 3 | 0 | yes / no / no | none |
| `QHRN` | 22 / 5 | 0 | yes / yes / no | none |
| `QRRM` | 0 / 0 | 0 | yes / no / no | none |
| `QVRN` | 3 / 0 | 0 | yes / no / no | none |
| `R2RM` | 24 / 0 | 0 | yes / no / no | none |
| `R5RM` | 22 / 0 | 0 | yes / no / no | none |
| `R5RN` | 18 / 0 | 0 | yes / no / no | none |
| `R6RM` | 22 / 0 | 0 | yes / no / no | none |
| `R7RN` | 22 / 5 | 0 | yes / yes / no | none |
| `RARN` | 22 / 7 | 0 | yes / no / no | none |
| `RHRN` | 21 / 5 | 0 | yes / yes / no | none |
| `RLRN` | 21 / 5 | 0 | yes / yes / no | none |
| `RMRN` | 21 / 5 | 0 | yes / yes / no | none |
| `RNRN` | 34 / 0 | 0 | yes / no / no | none |
| `RNRN/splitHead` | 35 / 0 | 0, 1 | yes / no / no | none |
| `RNRN/standard` | 34 / 0 | 0 | yes / no / no | none |
| `RRRN` | 22 / 5 | 0 | yes / no / no | none |
| `RSRN` | 11 / 4 | 0 | yes / yes / no | none |
| `RURN` | 11 / 1 | 0 | yes / yes / no | none |
| `RXRN` | 21 / 5 | 0 | yes / yes / no | none |
| `S6RN` | 6 / 0 | 0 | yes / no / no | none |
| `S7RN` | 8 / 0 | 0 | yes / no / no | none |
| `S9RM` | 9 / 0 | 0 | yes / no / no | none |
| `SARM` | 8 / 0 | 0 | yes / no / no | none |
| `T0RM` | 8 / 0 | 0 | yes / no / no | none |
| `T1RM` | 13 / 0 | 0 | yes / no / no | none |
| `T2RM` | 8 / 0 | 0 | yes / no / no | none |
| `T3RM` | 12 / 0 | 0 | yes / no / no | none |
| `T4RM` | 8 / 0 | 0 | yes / no / no | none |
| `T5RM` | 17 / 5 | 0 | yes / no / no | none |
| `T6RM` | 8 / 0 | 0 | yes / no / no | none |
| `T7RM` | 20 / 6 | 0 | yes / no / no | none |
| `T8RM` | 8 / 0 | 0 | yes / no / no | none |
| `T9RM` | 21 / 3 | 0 | yes / no / no | none |
| `TARM` | 22 / 0 | 0 | yes / no / no | none |
| `TBRM` | 17 / 6 | 0 | yes / no / no | none |
| `TCRM` | 17 / 0 | 0 | yes / no / no | none |
| `TDRM` | 20 / 0 | 0 | yes / no / no | none |
| `TERM` | 23 / 0 | 0 | yes / no / no | none |
| `TEST` | 2 / 0 | 0 | yes / no / no | none |
| `THRM` | 21 / 0 | 0 | yes / no / no | none |
| `TLRM` | 8 / 0 | 0 | yes / no / no | none |
| `TWRM` | 8 / 0 | 0 | yes / no / no | none |
| `TZRM` | 8 / 0 | 0 | yes / no / no | none |
| `U0RM` | 13 / 0 | 0 | yes / no / no | none |
| `U1RM` | 22 / 0 | 0 | yes / no / no | none |
| `U2RM` | 22 / 0 | 0 | yes / no / no | none |
| `U3RM` | 23 / 0 | 0 | yes / no / no | none |
| `U4RM` | 21 / 0 | 0 | yes / no / no | none |
| `U5RM` | 24 / 0 | 0 | yes / no / no | none |
| `U6RM` | 9 / 3 | 0 | yes / no / no | none |
| `U7RM` | 11 / 0 | 0 | yes / no / no | none |
| `U8RM` | 12 / 0 | 0 | yes / no / no | none |
| `U9RM` | 19 / 0 | 0 | yes / no / no | none |
| `UARM` | 20 / 0 | 0 | yes / no / no | none |
| `UBRM` | 20 / 0 | 0 | yes / no / no | none |
| `UCRM` | 12 / 0 | 0 | yes / no / no | none |
| `UDRM` | 7 / 0 | 0 | yes / no / no | none |
| `UERM` | 22 / 0 | 0 | yes / no / no | none |
| `UFRM` | 22 / 7 | 0 | yes / no / no | none |
| `UGRM` | 22 / 0 | 0 | yes / no / no | none |
| `UHRM` | 22 / 0 | 0 | yes / no / no | none |
| `UIRM` | 11 / 0 | 0 | yes / no / no | none |
| `UJRM` | 20 / 0 | 0 | yes / no / no | none |
| `UKRM` | 22 / 0 | 0 | yes / no / no | none |
| `ULRM` | 19 / 0 | 0 | yes / no / no | none |
| `UMRM` | 12 / 0 | 0 | yes / no / no | none |
| `UNRM` | 24 / 0 | 0 | yes / no / no | none |
| `UORM` | 12 / 0 | 0 | yes / no / no | none |
| `UPRM` | 12 / 0 | 0 | yes / no / no | none |
| `UQRM` | 12 / 0 | 0 | yes / no / no | none |
| `URRM` | 20 / 2 | 0 | yes / no / no | none |
| `UTRM` | 20 / 0 | 0 | yes / no / no | none |
| `UURM` | 9 / 0 | 0 | yes / no / no | none |
| `UVRM` | 22 / 0 | 0 | yes / no / no | none |
| `UWRM` | 12 / 0 | 0 | yes / no / no | none |
| `UXRM` | 12 / 0 | 0 | yes / no / no | none |
| `UYRM` | 20 / 0 | 0 | yes / no / no | none |
| `UZRM` | 22 / 0 | 0 | yes / no / no | none |
| `V0RM` | 24 / 0 | 0 | yes / no / no | none |
| `V1RM` | 9 / 3 | 0 | yes / no / no | none |
| `V2RM` | 22 / 0 | 0 | yes / no / no | none |
| `V3RM` | 8 / 0 | 0 | yes / no / no | none |
| `V4RM` | 22 / 7 | 0 | yes / no / no | none |
| `V5RM` | 8 / 0 | 0 | yes / no / no | none |
| `V6RM` | 14 / 0 | 0 | yes / no / no | none |
| `V7RM` | 21 / 0 | 0 | yes / no / no | none |
| `V8RM` | 22 / 0 | 0 | yes / no / no | none |
| `V9RM` | 19 / 0 | 0 | yes / no / no | none |
| `V9RM/splitHead` | 20 / 0 | 0, 1 | yes / no / no | none |
| `V9RM/standard` | 19 / 0 | 0 | yes / no / no | none |
| `VARM` | 11 / 0 | 0 | yes / no / no | none |
| `VBRM` | 18 / 0 | 0 | yes / no / no | none |
| `VCRM` | 22 / 0 | 0 | yes / no / no | none |
| `VDRM` | 17 / 0 | 0 | yes / no / no | none |
| `VERM` | 19 / 0 | 0 | yes / no / no | none |
| `VFRM` | 22 / 0 | 0 | yes / no / no | none |
| `VGRM` | 9 / 0 | 0 | yes / no / no | none |
| `VHRM` | 9 / 0 | 0 | yes / no / no | none |
| `VIRM` | 19 / 0 | 0 | yes / no / no | none |
| `VJRM` | 7 / 1 | 0 | yes / no / no | none |
| `VKRM` | 18 / 0 | 0 | yes / no / no | none |
| `VLRM` | 17 / 0 | 0 | yes / no / no | none |
| `VMRM` | 14 / 0 | 0 | yes / no / no | none |
| `VNRM` | 17 / 0 | 0 | yes / no / no | none |
| `VORM` | 19 / 7 | 0 | yes / no / no | none |
| `VPRM` | 17 / 0 | 0 | yes / no / no | none |
| `VQRM` | 11 / 0 | 0 | yes / no / no | none |
| `VRRM` | 24 / 0 | 0 | yes / no / no | none |
| `VSRM` | 20 / 0 | 0 | yes / no / no | none |
| `VTRM` | 22 / 0 | 0 | yes / no / no | none |
| `VURM` | 19 / 0 | 0 | yes / no / no | none |
| `VVRM` | 17 / 0 | 0 | yes / no / no | none |
| `VWRM` | 17 / 0 | 0 | yes / no / no | none |
| `VXRM` | 19 / 0 | 0 | yes / no / no | none |
| `VYRM` | 22 / 0 | 0 | yes / no / no | none |
| `VZRM` | 17 / 0 | 0 | yes / no / no | none |
| `W0RM` | 22 / 0 | 0 | yes / no / no | none |
| `W1RM` | 7 / 0 | 0 | yes / no / no | none |
| `W2RM` | 22 / 0 | 0 | yes / no / no | none |
| `W3RM` | 24 / 0 | 0 | yes / no / no | none |
| `W4RM` | 7 / 0 | 0 | yes / no / no | none |
| `W5RM` | 17 / 0 | 0 | yes / no / no | none |
| `W6RM` | 17 / 0 | 0 | yes / no / no | none |
| `W7RM` | 17 / 0 | 0 | yes / no / no | none |
| `W8RM` | 4 / 0 | 0 | yes / no / no | none |
| `W9RM` | 19 / 0 | 0 | yes / no / no | none |
| `WARM` | 22 / 0 | 0 | yes / no / no | none |
| `WBRM` | 22 / 0 | 0 | yes / no / no | none |
| `WCRM` | 22 / 0 | 0 | yes / no / no | none |
| `WDRM` | 22 / 0 | 0 | yes / no / no | none |
| `WERM` | 22 / 0 | 0 | yes / no / no | none |
| `WGRM` | 4 / 0 | 0 | yes / no / no | none |
| `WHRM` | 17 / 0 | 0 | yes / no / no | none |
| `WIRM` | 19 / 0 | 0 | yes / no / no | none |
| `WJRM` | 20 / 4 | 0 | yes / no / no | none |
| `WKRM` | 20 / 4 | 0 | yes / no / no | none |
| `WLRM` | 11 / 6 | 0 | yes / no / no | none |
| `WMRM` | 2 / 1 | 0 | yes / no / no | none |
| `WNRM` | 22 / 7 | 0 | yes / no / no | none |
| `WORM` | 7 / 0 | 0 | yes / no / no | none |
| `WPRM` | 7 / 0 | 0 | yes / no / no | none |
| `WQRM` | 5 / 0 | 0 | yes / no / no | none |
| `WRRM` | 9 / 1 | 0 | yes / no / no | none |
| `WSRM` | 22 / 0 | 0 | yes / no / no | none |
| `WTRM` | 17 / 0 | 0 | yes / no / no | none |
| `WURM` | 17 / 7 | 0 | yes / no / no | none |
| `WVRM` | 13 / 0 | 0 | yes / no / no | none |
| `WWRM` | 12 / 1 | 0 | yes / no / no | none |
| `WXRM` | 22 / 7 | 0 | yes / no / no | none |
| `WYRM` | 12 / 0 | 0 | yes / no / no | none |
| `WZRM` | 8 / 0 | 0 | yes / no / no | none |
| `X0RM` | 22 / 0 | 0 | yes / no / no | none |
| `X1RM` | 7 / 2 | 0 | yes / no / no | none |
| `X2RM` | 7 / 1 | 0 | yes / no / no | none |
| `X4RM` | 11 / 0 | 0 | yes / no / no | none |
| `X5RM` | 11 / 0 | 0 | yes / no / no | none |
| `X6RM` | 7 / 0 | 0 | yes / no / no | none |
| `X7RM` | 20 / 2 | 0 | yes / no / no | none |
| `X8RM` | 11 / 0 | 0 | yes / no / no | none |
| `X9RM` | 23 / 0 | 0 | yes / no / no | none |
| `XARM` | 10 / 1 | 0 | yes / no / no | none |
| `XBRM` | 8 / 0 | 0 | yes / no / no | none |
| `XCRM` | 20 / 4 | 0 | yes / no / no | none |
| `XDRM` | 5 / 0 | 0 | yes / no / no | none |
| `XERM` | 17 / 7 | 0 | yes / no / no | none |
| `XFRM` | 20 / 5 | 0 | yes / no / no | none |
| `XGRM` | 9 / 3 | 0 | yes / no / no | none |
| `XHRM` | 20 / 1 | 0 | yes / no / no | none |
| `XIRM` | 20 / 0 | 0 | yes / no / no | none |
| `XJRM` | 22 / 7 | 0 | yes / no / no | none |
| `XKRM` | 22 / 7 | 0 | yes / no / no | none |
| `XLRM` | 20 / 4 | 0 | yes / no / no | none |
| `XMRM` | 24 / 0 | 0 | yes / no / no | none |
| `XNRM` | 5 / 0 | 0 | yes / no / no | none |
| `XORM` | 8 / 0 | 0 | yes / no / no | none |
| `XPRM` | 21 / 1 | 0 | yes / no / no | none |
| `XQRM` | 14 / 0 | 0 | yes / no / no | none |
| `XRRM` | 7 / 0 | 0 | yes / no / no | none |
| `XSRM` | 20 / 0 | 0 | yes / no / no | none |
| `XTRM` | 20 / 0 | 0 | yes / no / no | none |
| `XURM` | 12 / 0 | 0 | yes / no / no | none |
| `XVRM` | 20 / 2 | 0 | yes / no / no | none |
| `XWRM` | 16 / 0 | 0 | yes / no / no | none |
| `XXRM` | 8 / 0 | 0 | yes / no / no | none |
| `XYRM` | 22 / 7 | 0 | yes / no / no | none |
| `XZRM` | 22 / 7 | 0 | yes / no / no | none |
| `Y0RM` | 7 / 0 | 0 | yes / no / no | none |
| `Y1RM` | 9 / 3 | 0 | yes / no / no | none |
| `Y2RM` | 8 / 0 | 0 | yes / no / no | none |
| `Y3RM` | 19 / 0 | 0 | yes / no / no | none |
| `Y4RM` | 11 / 0 | 0 | yes / no / no | none |
| `Y5RM` | 7 / 0 | 0 | yes / no / no | none |
| `Y6RM` | 17 / 4 | 0 | yes / no / no | none |
| `Y7RM` | 9 / 3 | 0 | yes / no / no | none |
| `Y8RM` | 20 / 6 | 0 | yes / no / no | none |
| `Y9RM` | 9 / 3 | 0 | yes / no / no | none |
| `YARM` | 20 / 0 | 0 | yes / no / no | none |
| `YBRM` | 7 / 0 | 0 | yes / no / no | none |
| `YCRM` | 6 / 0 | 0 | yes / no / no | none |
| `YDRM` | 8 / 0 | 0 | yes / no / no | none |
| `YERM` | 20 / 8 | 0 | yes / no / no | none |
| `YFRM` | 14 / 0 | 0 | yes / no / no | none |
| `YGRM` | 28 / 1 | 0 | yes / no / no | none |
| `YHRM` | 24 / 0 | 0 | yes / no / no | none |
| `YIRM` | 24 / 2 | 0 | yes / no / no | none |
| `YJRM` | 22 / 0 | 0 | yes / no / no | none |
| `YKRM` | 7 / 0 | 0 | yes / no / no | none |
| `YMRM` | 20 / 1 | 0 | yes / no / no | none |
| `YNRM` | 9 / 0 | 0 | yes / no / no | none |
| `YORM` | 24 / 2 | 0 | yes / no / no | none |
| `YPRM` | 24 / 9 | 0 | yes / no / no | none |
| `YQRM` | 9 / 3 | 0 | yes / no / no | none |
| `YRRM` | 8 / 3 | 0 | yes / no / no | none |
| `YSRM` | 12 / 1 | 0 | yes / no / no | none |
| `YTRM` | 14 / 1 | 0 | yes / no / no | none |
| `YURM` | 12 / 1 | 0 | yes / no / no | none |
| `YVRM` | 12 / 1 | 0 | yes / no / no | none |
| `YWRM` | 22 / 0 | 0 | yes / no / no | none |
| `YXRM` | 8 / 2 | 0 | yes / no / no | none |
| `YYRM` | 17 / 7 | 0 | yes / no / no | none |
| `YZRM` | 23 / 0 | 0 | yes / no / no | none |
| `Z0RM` | 7 / 0 | 0 | yes / no / no | none |
| `Z1RM` | 8 / 0 | 0 | yes / no / no | none |
| `Z2RM` | 21 / 2 | 0 | yes / no / no | none |
| `Z3RM` | 20 / 0 | 0 | yes / no / no | none |
| `Z4RM` | 22 / 7 | 0 | yes / no / no | none |
| `Z5RM` | 22 / 7 | 0 | yes / no / no | none |
| `Z6RM` | 17 / 7 | 0 | yes / no / no | none |
| `Z7RM` | 8 / 0 | 0 | yes / no / no | none |
| `Z8RM` | 22 / 8 | 0 | yes / no / no | none |
| `Z9RM` | 12 / 4 | 0 | yes / no / no | none |
| `ZARM` | 17 / 1 | 0 | yes / no / no | none |
| `ZBRM` | 12 / 0 | 0 | yes / no / no | none |
| `ZCRM` | 7 / 0 | 0 | yes / no / no | none |
| `ZDRM` | 11 / 5 | 0 | yes / no / no | none |
| `ZERM` | 22 / 0 | 0 | yes / no / no | none |
| `ZFRM` | 22 / 7 | 0 | yes / no / no | none |
| `ZGRM` | 22 / 7 | 0 | yes / no / no | none |
| `ZHRM` | 19 / 1 | 0 | yes / no / no | none |
| `ZIRM` | 20 / 2 | 0 | yes / no / no | none |
| `ZJRM` | 12 / 0 | 0 | yes / no / no | none |
| `ZKRM` | 19 / 0 | 0 | yes / no / no | none |
| `ZLRM` | 19 / 0 | 0 | yes / no / no | none |
| `ZMRM` | 20 / 0 | 0 | yes / no / no | none |
| `ZNRM` | 12 / 0 | 0 | yes / no / no | none |
| `ZORM` | 20 / 0 | 0 | yes / no / no | none |
| `ZPRM` | 7 / 0 | 0 | yes / no / no | none |
| `ZQRM` | 4 / 0 | 0 | yes / no / no | none |
| `ZR00` | 5 / 0 | 0 | yes / no / no | none |
| `ZR01` | 3 / 0 | 0 | yes / no / no | none |
| `ZR10` | 12 / 0 | 0 | yes / no / no | none |
| `ZR11` | 12 / 0 | 0 | yes / no / no | none |
| `ZR12` | 12 / 0 | 0 | yes / no / no | none |
| `ZR20` | 7 / 0 | 0 | yes / no / no | none |
| `ZR21` | 8 / 0 | 0 | yes / no / no | none |
| `ZR30` | 6 / 0 | 0 | yes / no / no | none |
| `ZR40` | 7 / 0 | 0 | yes / no / no | none |
| `ZR50` | 23 / 0 | 0 | yes / no / no | none |
| `ZR51` | 23 / 0 | 0 | yes / no / no | none |
| `ZR60` | 9 / 0 | 0 | yes / no / no | none |
| `ZR70` | 10 / 0 | 0 | yes / no / no | none |
| `ZR80` | 12 / 0 | 0 | yes / no / no | none |
| `ZRA0` | 17 / 0 | 0 | yes / no / no | none |
| `ZRA1` | 6 / 0 | 0 | yes / no / no | none |
| `ZRA2` | 12 / 0 | 0 | yes / no / no | none |
| `ZRI0` | 19 / 0 | 0 | yes / no / no | none |
| `ZRRM` | 12 / 0 | 0 | yes / no / no | none |
| `ZRS0` | 0 / 0 | 0 | yes / no / no | B8TT, B9TT |
| `ZRS1` | 0 / 0 | 0 | yes / no / no | ZRI0, I4RM, I5RM, D7RM |
| `ZRS2` | 0 / 0 | 0 | yes / no / no | ZR00, ZR01 |
| `ZRS3` | 0 / 0 | 0 | yes / no / no | APRM, AQRM |
| `ZRS4` | 0 / 0 | 0 | yes / no / no | MDRM, MERM, MFRM, MGRM |
| `ZRS5` | 0 / 0 | 0 | yes / no / no | J6RM, MCRM, CORN |
| `ZRS6` | 0 / 0 | 0 | yes / no / no | CPRN, CORN |
| `ZSRM` | 17 / 1 | 0 | yes / no / no | none |
| `ZTRM` | 17 / 1 | 0 | yes / no / no | none |
| `ZURM` | 17 / 1 | 0 | yes / no / no | none |
| `ZVRM` | 10 / 0 | 0 | yes / no / no | none |
| `ZWRM` | 20 / 0 | 0 | yes / no / no | none |
| `ZXRM` | 7 / 0 | 0 | yes / no / no | none |
| `ZYRM` | 11 / 0 | 0 | yes / no / no | none |
| `ZZRM` | 6 / 0 | 0 | yes / no / no | none |
<!-- /generated -->

#### Controls

Every bed-command button retains its selected descriptor's short operand, long
operand, Nordic override and gesture. Distinct codes and configurations remain
independent even when their commands happen to match. Action IDs below identify
both normal buttons and the exact alarm actions a product admits. The product
catalog determines which IDs are offered; getter-only lists do not add controls.

The side selector offers only that product's declared sides. Commands, explicit
service sides and single-address paired children all pass the same side check.
Home Assistant captures the side and BLE connection for an entire gesture, so a
side change cannot redirect its release. E3RM, GXRM, JDRM, JFRM and JGRM retain
the memory-save latch for the seven named memory/preset actions, with GXRM TV's
exception. APRM, BRRM, YFRM and YGRM start in release mode. BRRM/YFRM/YGRM's
flagged replacement sends the None operand rather than silently ignoring it.
Local visual flags do not grant or revoke BLE capabilities.

D1RM/D9RM expose Off, 10, 20 and 30 minute massage countdown choices. A committed
choice sends once without an added release. Other app-labelled bed effects,
including hardware fan, heating, aroma, lock, synchronization and music-related
bed commands, retain their own catalog bytes. Phone torch, speech and navigation
widgets are local app actions and do not create BLE buttons.

<!-- generated:galaxy-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Action ID | App label / gesture | Framed short / long (Left) | Nordic short / long |
|---|---|---|---|
| 00768ad5c89c | deviceFunctionItemMusicPreviousSong / shortPress | `6E 01 00 D2 41` / `6E 01 00 00 6F` | `D2` / `00` |
| 03948f09ef03 | deviceFunctionItemZeroGravity2 / shortAndLongPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |
| 0633e7cf2d22 | deviceFunctionSofaBackward / sustainPress | `6E 01 00 5C CB` / `6E 01 00 00 6F` | `5C` / `00` |
| 06ab47fde8fd | deviceFunctionItemTileDown / sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |
| 06ceedc7765d | deviceFunctionItemRelieveZeroGravitySetting / shortPress | `6E 01 00 62 D1` / `6E 01 00 00 6F` | `62` / `00` |
| 0781eac7d139 | deviceFunctionItemMusicShakeClose / shortPress | `6E 01 00 DC 4B` / `6E 01 00 00 6F` | `DC` / `00` |
| 0838ca2e9af9 | deviceFunctionItemMusicSwitchSoundTrack / shortPress | `6E 01 00 C4 33` / `6E 01 00 00 6F` | `C4` / `00` |
| 08f67be62ad8 | deviceFunctionItemMemoryPosition1 / shortAndLongPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `42` / `2B` |
| 0accc27a6ff2 | deviceFunctionItemFootUpAndHeadDown / shortPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |
| 0ae43b2ba3ef | deviceFunctionItemSwingHelpSleep / sustainPress | `6E 01 00 76 E5` / `6E 01 00 00 6F` | `76` / `00` |
| 0b0b9685e1c1 | deviceFunctionItemMassage15MinuteUpAndDown / shortPress | `6E 01 00 76 E5` / `6E 01 00 00 6F` | `76` / `00` |
| 0b282e025218 | deviceFunctionItemFootUp / sustainPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `36` / `00` |
| 0b963e38699f | deviceFunctionItemTileUp / sustainPress | `6E 01 00 5B CA` / `6E 01 00 00 6F` | `5B` / `00` |
| 0cb97f6dea8a | deviceFunctionSofaLumbarDown / shortAndLongPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |
| 0cccbba6ad56 | deviceFunctionItemMemoryPosition1 / shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |
| 0d663ad100dd | deviceFunctionItemTitleTimer / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| 0e6510b9d9f8 | deviceFunctionItemNone / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` |
| 0e689e6ccad3 | deviceFunctionItemMemoryPosition3 / shortAndLongPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |
| 0f5030e77dcb | deviceFunctionSofaForword / sustainPress | `6E 01 00 5B CA` / `6E 01 00 00 6F` | `5B` / `00` |
| 0f7ade54e07f | deviceFunctionItemFootDown / shortAndLongPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `27` / `00` |
| 107670e3a0b3 | deviceFunctionItemLumberDown / shortPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |
| 113cb2a072be | deviceFunctionItemMlilyMenu / sustainPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| 11560c46d458 | deviceFunctionItemMassageModePulse / shortPress | `6E 01 00 38 A7` / `6E 01 00 00 6F` | `46` / `00` |
| 1201c925fb63 | deviceFunctionItemMassage2Instensity / shortPress | `6E 01 00 A5 14` / `6E 01 00 00 6F` | `A5` / `00` |
| 138a26790c48 | deviceFunctionItemMemoryPosition2 / shortAndLongPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |
| 13aa59bcdb87 | deviceFunctionItemLumberMemoryPosition / shortAndLongPress | `6E 01 00 91 00` / `6E 01 00 92 01` | `91` / `92` |
| 151ed6e5c962 | deviceFunctionItemMusicShakeFirstGear / shortPress | `6E 01 00 DD 4C` / `6E 01 00 00 6F` | `DD` / `00` |
| 153387b194f4 | deviceFunctionItemMotor5Down / sustainPress | `6E 01 00 D1 40` / `6E 01 00 00 6F` | `D1` / `00` |
| 15ab88d3324f | deviceFunctionItemHeadDown / sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `38` / `00` |
| 17837aeaf1c2 | deviceFunctionItemHeadUp / sustainPress | `6E 01 00 23 92` / `6E 01 00 00 6F` | `23` / `00` |
| 185f017838c5 | deviceFunctionItemMassageFootInstensityWeaken / shortPress | `6E 01 00 4F BE` / `6E 01 00 00 6F` | `4B` / `00` |
| 18af21d5070b | deviceFunctionItemMotorReset / sustainPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |
| 190811c7ee7a | deviceFunctionItemMassageInstensityStrengthen / shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `34` / `00` |
| 1ab43b1645a6 | deviceFunctionItemMotor3Up / shortAndLongPress | `6E 01 00 71 E0` / `6E 01 00 00 6F` | `71` / `00` |
| 1c2ed3d5f48f | deviceFunctionItemHeadUp / sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `35` / `00` |
| 1dfe8744e8a5 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 BE 2D` / `6E 01 00 00 6F` | `BE` / `00` |
| 1fa0bf876809 | deviceFunctionItemMassageSpeedStrengthen / shortPress | `6E 01 00 36 A5` / `6E 01 00 00 6F` | `36` / `00` |
| 1fd044951f81 | deviceFunctionItemVoice / shortPress (local) | no BLE | no BLE |
| 20a47df7a9fe | deviceFunctionItemDeepSleepPosition / shortAndLongPress | `6E 01 00 F7 66` / `6E 01 00 F6 65` | `F7` / `F6` |
| 20da93b5e0d8 | deviceFunctionItemControlBoxLock / shortAndLongPress | `6E 01 00 D9 48` / `6E 01 00 84 F3` | `D9` / `84` |
| 20fbf4502a1c | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `39` / `00` |
| 2244dc2953c1 | deviceFunctionItemMassage30MinuteTimer / shortPress | `6E 01 00 90 FF` / `6E 01 00 00 6F` | `90` / `00` |
| 22cd0b23a7a4 | deviceFunctionItemYogaPosition / shortAndLongPress | `6E 01 00 E0 4F` / `6E 01 00 E2 51` | `E0` / `E2` |
| 23a6bfbf3393 | deviceFunctionItemMassageModePulse / shortPress | `6E 01 00 38 A7` / `6E 01 00 00 6F` | `38` / `00` |
| 2456fd1de9c0 | deviceFunctionItemUnWindPosition / shortAndLongPress | `6E 01 00 8C FB` / `6E 01 00 8D FC` | `8C` / `8D` |
| 25356be8c511 | deviceFunctionItemWakeUpPosition / shortAndLongPress | `6E 01 00 93 02` / `6E 01 00 94 03` | `93` / `94` |
| 268a2e2cc269 | deviceFunctionItemMassageFootInstensityWeaken / shortPress | `6E 01 00 4F BE` / `6E 01 00 00 6F` | `4F` / `00` |
| 285b51f4f9e5 | deviceFunctionItemLoungePosition / shortAndLongPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |
| 29b45867df0e | deviceFunctionItemMassageModeChange / shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `48` / `00` |
| 2ab1281f472c | deviceFunctionItemMotorReset / shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `38` / `00` |
| 2b688d4c1261 | deviceFunctionItemWakeUp / shortAndLongPress | `6E 01 00 85 F4` / `6E 01 00 00 6F` | `85` / `00` |
| 309a885f5da0 | deviceFunctionItemMemoryPosition4 / shortAndLongPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |
| 30edc5e57ed3 | deviceFunctionItemHeadAndFootDown / sustainPress | `6E 01 00 97 06` / `6E 01 00 00 6F` | `97` / `00` |
| 31430a40e557 | deviceFunctionItemMassageModeChange / shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |
| 321b806f1bec | deviceFunctionItemMemoryPosition1 / shortAndLongPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |
| 3350a7dbe704 | deviceFunctionItemAntiSnoring / shortAndLongPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |
| 33937c0eabb4 | deviceFunctionItemBedLight / shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `3C` / `00` |
| 3437d7efe461 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `34` / `00` |
| 3443d35e240e | deviceFunctionAirbagLumbarSwitch / shortPress | `6E 01 00 CE 3D` / `6E 01 00 00 6F` | `CE` / `00` |
| 3481196aea0e | deviceFunctionItemMusicShakeThirdGear / shortPress | `6E 01 00 DF 4E` / `6E 01 00 00 6F` | `DF` / `00` |
| 35eda430fce9 | deviceFunctionItemPillowDown / shortPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |
| 3624e7135dda | deviceFunctionItemMusicNextSong / shortPress | `6E 01 00 D3 42` / `6E 01 00 00 6F` | `D3` / `00` |
| 3657bc6b57f3 | deviceFunctionItemMusicVolumuUp / shortPress | `6E 01 00 D4 43` / `6E 01 00 00 6F` | `D4` / `00` |
| 365e0528fabc | deviceFunctionItemZeroGravity / shortAndLongPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |
| 3660b44a8d2c | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` |
| 368c961c7d0f | deviceFunctionItemMassageInstensityFirstGear / shortPress | `6E 01 00 67 D6` / `6E 01 00 00 6F` | `4C` / `00` |
| 3a1da8a7936c | deviceFunctionItemRelieveZeroGravitySetting / sustainPress | `6E 01 00 BE 2D` / `6E 01 00 00 6F` | `BE` / `00` |
| 3a66ceaa8b98 | deviceFunctionItemZeroGravity / shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |
| 3ac30c11abbc | deviceFunctionItemAllMotorUp / sustainPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` |
| 3b0ca50c1a99 | deviceFunctionItemHeadUp / shortAndLongPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |
| 3b7426c168bb | deviceFunctionItemMemoryPosition3 / sustainPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |
| 3c563a6ed95a | deviceFunctionItemLogo / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| 3d07e495ecba | deviceFunctionItemHeadAndFootAllUp / shortPress | `6E 01 00 23 92` / `6E 01 00 00 6F` | `23` / `00` |
| 3d3a5c281ba8 | deviceFunctionItemMassage30MinuteUpAndDown / shortPress | `6E 01 00 90 FF` / `6E 01 00 00 6F` | `90` / `00` |
| 3de07899c72c | deviceFunctionItemBedLightClose / shortPress | `6E 01 00 75 E4` / `6E 01 00 00 6F` | `75` / `00` |
| 3eaf170d6395 | deviceFunctionItemMassageHeadInstensSecondMode / shortPress | `6E 01 00 9A 09` / `6E 01 00 00 6F` | `9A` / `00` |
| 3ec2d2e3f45d | deviceFunctionItemMassage10MinuteTimer / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `5F` / `00` |
| 3ef450736fe8 | deviceFunctionItemAlarmMode2 / shortPress | `6E 01 00 B1 20` / `6E 01 00 00 6F` | `B1` / `00` |
| 413b56feb6cc | deviceFunctionItemAntiSnoring / shortPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |
| 416528417b6c | deviceFunctionItemLumberDown / sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |
| 436b2c9f27a5 | deviceFunctionItemFootUp / shortAndLongPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `26` / `00` |
| 439f3159f6e0 | deviceFunctionItemMotorAndMassageAllOff / shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |
| 43d4f66d0c82 | deviceFunctionItemFootDown / shortPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |
| 443dc0604e41 | deviceFunctionItemMemoryPosition1 / sustainPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |
| 4491ae0fe371 | deviceFunctionItemZeroGravity2 / shortPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |
| 44b0c38bdf3c | deviceFunctionItemBedLight / shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `43` / `00` |
| 4500d9c24b53 | deviceFunctionSofaHeadUp / sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |
| 4501725f3ef5 | deviceFunctionItemControlBoxLock / shortAndLongPress | `6E 01 00 84 F3` / `6E 01 00 84 F3` | `84` / `84` |
| 4509df8a29bc | deviceFunctionItemFanTimer3Hour / shortPress | `6E 01 00 A7 16` / `6E 01 00 00 6F` | `A7` / `00` |
| 460eaa0c9c06 | deviceFunctionItemTVPosition / shortAndLongPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |
| 4744e2125604 | deviceFunctionItemMassage30MinuteTimer / shortPress | `6E 01 00 61 D0` / `6E 01 00 00 6F` | `61` / `00` |
| 4819f56ca2b9 | deviceFunctionItemAllMotorUp / shortPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` |
| 48b8677df3f3 | deviceFunctionItemMassageModeChange / shortPress | `6E 01 00 72 E1` / `6E 01 00 00 6F` | `72` / `00` |
| 490439c2e818 | deviceFunctionItemLoungePosition / sustainPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |
| 494aeb2a2642 | deviceFunctionItemAllMotorUp / sustainPress | `6E 01 00 B6 25` / `6E 01 00 00 6F` | `B6` / `00` |
| 496bd06c72a3 | deviceFunctionItemMusicClose / shortPress | `6E 01 00 B9 28` / `6E 01 00 00 6F` | `B9` / `00` |
| 4a1fd16956e2 | deviceFunctionItemMassageLumbarInstensityStrengthen / shortPress | `6E 01 00 E0 4F` / `6E 01 00 00 6F` | `E0` / `00` |
| 4a3a0b986abd | deviceFunctionItemMassageSwitch / shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |
| 4c393e6d904f | deviceFunctionItemHeadAndFootUp / shortPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `29` / `00` |
| 4d9f48795df3 | deviceFunctionItemHeadAndFootUp / sustainPress | `6E 01 00 56 C5` / `6E 01 00 00 6F` | `56` / `00` |
| 4e26611eed4a | deviceFunctionItemMassageHeadInstensThirdMode / shortPress | `6E 01 00 9B 0A` / `6E 01 00 00 6F` | `9B` / `00` |
| 4e267fb43482 | deviceFunctionItemMassage1OpenOrClose / shortPress | `6E 01 00 32 A1` / `6E 01 00 00 6F` | `32` / `00` |
| 4e6a210e7921 | deviceFunctionItemMassageHeadInstensityWeaken / shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `4A` / `00` |
| 50246afd1950 | deviceFunctionItemMotorReset / shortPress | `6E 01 00 30 9F` / `6E 01 00 00 6F` | `30` / `00` |
| 51e59167de7f | deviceFunctionItemZeroGravity / shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |
| 52adbe7a3b28 | deviceFunctionItemMassageFootInstensityStrengthen / shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `4E` / `00` |
| 52db8cbeaaac | deviceFunctionItemMusicBlueToothSwitch / shortPress | `6E 01 00 D8 47` / `6E 01 00 00 6F` | `D8` / `00` |
| 5389041d2923 | deviceFunctionItemMassageHeadInstensityStrengthen / shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `46` / `00` |
| 5441ec9f3ae0 | deviceFunctionItemSyncOff / longPress | `6E 01 00 BD 2C` / `6E 01 00 BD 2C` | `BD` / `BD` |
| 558c0081b122 | deviceFunctionItemHeadUp / sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `34` / `00` |
| 5653ca1468dd | deviceFunctionItemCoaxingSleepMode2 / shortPress | `6E 01 00 87 F6` / `6E 01 00 00 6F` | `87` / `00` |
| 56e4fc173edc | deviceFunctionItemHeadUpAndFootDown / shortPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |
| 572700e782ee | deviceFunctionItemMemoryPosition2 / shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |
| 57dde465fc30 | deviceFunctionItemFootUp / shortPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `26` / `00` |
| 5964d0ea61c6 | deviceFunctionItemPillowUp / shortPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |
| 59cf0540575c | deviceFunctionItemFootUp / shortPress | `6E 01 00 3E AD` / `6E 01 00 00 6F` | `3E` / `00` |
| 5acf1c0314fe | deviceFunctionItemMemoryPosition5 / shortPress | `6E 01 00 F4 63` / `6E 01 00 F5 64` | `F4` / `F5` |
| 5ae3ab06338c | deviceFunctionItemNone / sustainPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| 5dc6c04ba291 | deviceFunctionSofaLumbarUp / sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |
| 5ddc7f0c8188 | deviceFunctionItemPillowUp / sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |
| 5ed2bfd209c8 | deviceFunctionItemPillowUp / sustainPress | `6E 01 00 7E ED` / `6E 01 00 00 6F` | `7E` / `00` |
| 5f6dc4efbe19 | deviceFunctionItemMassageSpeedWeaken / shortPress | `6E 01 00 37 A6` / `6E 01 00 00 6F` | `37` / `00` |
| 6087a67a0ea8 | deviceFunctionItemAllMotorDown / sustainPress | `6E 01 00 B8 27` / `6E 01 00 00 6F` | `B8` / `00` |
| 60b2ef6a572f | deviceFunctionItemFootUpAndHeadDown / sustainPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |
| 60cc184338e1 | deviceFunctionItemControlBoxLock / shortPress | `6E 01 00 84 F3` / `6E 01 00 84 F3` | `84` / `84` |
| 620bd72350b8 | deviceFunctionItemAllMotorDown / shortPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` |
| 630602a08285 | deviceFunctionItemAllMotorDown / sustainPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` |
| 64dcdd7ca52d | deviceFunctionItemMassageModeConstant / shortPress | `6E 01 00 3A A9` / `6E 01 00 00 6F` | `3A` / `00` |
| 6502adff1ac1 | deviceFunctionItemMemoryPosition1 / shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `42` / `2B` |
| 657730c34383 | deviceFunctionItemSleepPosition / shortAndLongPress | `6E 01 00 8E FD` / `6E 01 00 8F FE` | `8E` / `8F` |
| 658d5232baf8 | deviceFunctionItemMassageInstensityFirstGear / shortPress | `6E 01 00 67 D6` / `6E 01 00 00 6F` | `67` / `00` |
| 67113d8caad1 | deviceFunctionItemMemoryPosition3 / shortPress | `6E 01 00 30 9F` / `6E 01 00 2D 9C` | `30` / `2D` |
| 673557f50269 | deviceFunctionItemHeadDown / sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |
| 6893182c3e1f | deviceFunctionItemMassageModeOffAndMotorReset / shortPress | `6E 01 00 5A C9` / `6E 01 00 00 6F` | `5A` / `00` |
| 6abf54114f31 | deviceFunctionItemMassageInstensityStrengthen / shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `4A` / `00` |
| 6b2ef03f286d | deviceFunctionItemHeadAndFootDown / sustainPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `39` / `00` |
| 6bcd01cdd5b5 | deviceFunctionItemMemoryPosition1 / shortPress | `6E 01 00 45 B4` / `6E 01 00 2B 9A` | `35` / `2B` |
| 6c1dc1af2c34 | deviceFunctionItemMemoryPosition2 / sustainPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |
| 6c2a1bedb707 | deviceFunctionItemMemoryPosition2 / longPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |
| 721a2ee6260c | deviceFunctionItemMotor5Up / sustainPress | `6E 01 00 D0 3F` / `6E 01 00 00 6F` | `D0` / `00` |
| 73d49efb68c5 | deviceFunctionItemHeadDown / shortPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |
| 73f5478bcfb9 | deviceFunctionItemHeadDown / shortAndLongPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |
| 75c061f1dd65 | deviceFunctionItemFootDown / shortPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `27` / `00` |
| 76eed6abcd76 | deviceFunctionItemMassageFootInstensFirstMode / shortPress | `6E 01 00 9D 0C` / `6E 01 00 00 6F` | `9D` / `00` |
| 7758e56b711b | deviceFunctionItemMassageModeAllOff / sustainPress | `6E 01 00 5E CD` / `6E 01 00 00 6F` | `5E` / `00` |
| 7795d60ad72e | deviceFunctionItemReadingPosition / shortPress | `6E 01 00 F2 61` / `6E 01 00 F3 62` | `F2` / `F3` |
| 77df14c54e8e | deviceFunctionSofaPillowUp / shortAndLongPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |
| 77e0e35cf814 | deviceFunctionItemMemory / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| 77f130d8f765 | deviceFunctionItemReadingPosition / shortAndLongPress | `6E 01 00 F2 61` / `6E 01 00 F3 62` | `F2` / `F3` |
| 78107fe6925a | deviceFunctionItemMemoryPosition1 / shortPress | `6E 01 00 2B 9A` / `6E 01 00 2B 9A` | `2B` / `2B` |
| 78323408b9f4 | deviceFunctionItemMassageSpeedStrengthen / shortPress | `6E 01 00 36 A5` / `6E 01 00 00 6F` | `48` / `00` |
| 787098f3de8a | deviceFunctionItemMotor4Down / sustainPress | `6E 01 00 74 E3` / `6E 01 00 00 6F` | `74` / `00` |
| 787429a0e059 | deviceFunctionItemHeadAndFootUp / sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `38` / `00` |
| 7a1587791f2e | deviceFunctionItemMotor4Down / shortAndLongPress | `6E 01 00 74 E3` / `6E 01 00 00 6F` | `74` / `00` |
| 7a2bc77f4aa2 | deviceFunctionItemMassageInstensityWeaken / shortPress | `6E 01 00 35 A4` / `6E 01 00 00 6F` | `35` / `00` |
| 7b24886b91f6 | deviceFunctionItemSideSleepPosition / shortAndLongPress | `6E 01 00 BA 29` / `6E 01 00 BB 2A` | `BA` / `BB` |
| 7ba02deab1c3 | deviceFunctionAirbagAllSwitch / shortPress | `6E 01 00 CB 3A` / `6E 01 00 00 6F` | `CB` / `00` |
| 7bb6a14f7e98 | deviceFunctionSofaLumbarUp / shortAndLongPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |
| 7cc5950ed801 | deviceFunctionItemMemoryPosition1 / longPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |
| 7f8362981224 | deviceFunctionItemMotor3Up / sustainPress | `6E 01 00 71 E0` / `6E 01 00 00 6F` | `71` / `00` |
| 7f9eda012f64 | deviceFunctionItemMassageFootInstensThirdMode / shortPress | `6E 01 00 9F 0E` / `6E 01 00 00 6F` | `9F` / `00` |
| 820106f2d6dd | deviceFunctionItemMassageHeadInstensityStrengthen / shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `4C` / `00` |
| 8207ce775431 | deviceFunctionItemWakeUp / shortPress | `6E 01 00 85 F4` / `6E 01 00 00 6F` | `85` / `00` |
| 83090bdc8e09 | deviceFunctionItemHeadAndFootDown / sustainPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `2A` / `00` |
| 835856209472 | deviceFunctionItemHeadUpAndFootStop / shortPress | `6E 01 00 30 9F` / `6E 01 00 00 6F` | `30` / `00` |
| 838f321d8555 | deviceFunctionItemMassageInstensityThirdGear / shortPress | `6E 01 00 68 D7` / `6E 01 00 00 6F` | `68` / `00` |
| 8406592d4686 | deviceFunctionItemZeroGravity / shortAndLongPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `34` / `66` |
| 850f5aeb0b3e | deviceFunctionItemMemoryPosition2 / shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `2F` / `2C` |
| 85384b23cdc1 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5E CD` / `6E 01 00 00 6F` | `5E` / `00` |
| 8597264510db | deviceFunctionItemMemoryPosition1 / shortPress | `6E 01 00 2E 9D` / `6E 01 00 2B 9A` | `2E` / `2B` |
| 85d834a83487 | deviceFunctionItemSyncOff / shortAndLongPress | `6E 01 00 BD 2C` / `6E 01 00 BD 2C` | `BD` / `BD` |
| 8661e62701cf | deviceFunctionItemLumberDown / sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `43` / `00` |
| 88a4f08c9252 | deviceFunctionItemSyncOn / shortAndLongPress | `6E 01 00 BC 2B` / `6E 01 00 BC 2B` | `BC` / `BC` |
| 88aa084c0f06 | deviceFunctionItemHeadDown / sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `37` / `00` |
| 896242ba2b4b | deviceFunctionItemHelpGetUp / shortPress | `6E 01 00 3D AC` / `6E 01 00 00 6F` | `3D` / `00` |
| 89d0d81ea7cd | deviceFunctionItemHelpGetUpPosition / shortPress | `6E 01 00 3D AC` / `6E 01 00 F8 67` | `3D` / `F8` |
| 8b10d37d7978 | deviceFunctionItemBedLight / shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `46` / `00` |
| 8df5b61e297f | deviceFunctionItemPillowUp / sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |
| 8e73893aad10 | deviceFunctionItemMassage10MinuteTimer / shortPress | `6E 01 00 A1 10` / `6E 01 00 00 6F` | `A1` / `00` |
| 8fbd6aa186ef | deviceFunctionItemMassageSpeedWeaken / shortPress | `6E 01 00 37 A6` / `6E 01 00 00 6F` | `49` / `00` |
| 9082899ebbf3 | deviceFunctionItemClock / shortPress (local) | no BLE | no BLE |
| 90b530b342a8 | deviceFunctionSofaPillowDown / shortAndLongPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |
| 91906568b6d2 | deviceFunctionItemMemoryPosition4 / sustainPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |
| 91a3c6b8411b | deviceFunctionItemHeadUp / shortPress | `6E 01 00 3D AC` / `6E 01 00 00 6F` | `3D` / `00` |
| 941d70bafe1e | deviceFunctionItemHeadUpAndFootDown / shortPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |
| 944b1a60f697 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |
| 96a28bdf766b | deviceFunctionItemTVPosition / shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |
| 97889821ebe9 | deviceFunctionItemMassageModeAllOn / shortPress | `6E 01 00 5D CC` / `6E 01 00 00 6F` | `5D` / `00` |
| 97d395b86b74 | deviceFunctionItemHeadUpAndFootStop / shortPress | `6E 01 00 3D AC` / `6E 01 00 00 6F` | `3D` / `00` |
| 98c1e3ac8fca | deviceFunctionItemMassageFootInstensSecondMode / shortPress | `6E 01 00 9E 0D` / `6E 01 00 00 6F` | `9E` / `00` |
| 9908b3accea1 | deviceFunctionItemPillow2Up / shortAndLongPress | `6E 01 00 7A E9` / `6E 01 00 00 6F` | `7A` / `00` |
| 9a34fb9046c0 | deviceFunctionItemLumberDown / sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |
| 9ad1e023bf24 | deviceFunctionItemFan2InstensityStrengthen / shortPress | `6E 01 00 8B FA` / `6E 01 00 00 6F` | `8B` / `00` |
| 9ad2cd3ffa5a | deviceFunctionItemPillowDown / sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |
| 9ae059e86a44 | deviceFunctionItemTileDown / sustainPress | `6E 01 00 5C CB` / `6E 01 00 00 6F` | `5C` / `00` |
| 9b3505985df2 | deviceFunctionItemTileUp / sustainPress | `6E 01 00 43 B2` / `6E 01 00 00 6F` | `43` / `00` |
| 9bc116cba3e6 | deviceFunctionItemMassageFootOff / shortPress | `6E 01 00 9C 0B` / `6E 01 00 00 6F` | `9C` / `00` |
| 9bf26831d86a | deviceFunctionItemAntiSnoring / shortPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |
| 9c0c291dde85 | deviceFunctionItemMassage20MinuteTimer / shortPress | `6E 01 00 63 D2` / `6E 01 00 00 6F` | `63` / `00` |
| 9cc13d12dfaf | deviceFunctionItemSyncOn / longPress | `6E 01 00 BC 2B` / `6E 01 00 BC 2B` | `BC` / `BC` |
| 9d39a2d4f2db | deviceFunctionAirbagBackSwitch / shortPress | `6E 01 00 CC 3B` / `6E 01 00 00 6F` | `CC` / `00` |
| 9d561e6e9c0b | deviceFunctionItemHeadAndFootDown / sustainPress | `6E 01 00 57 C6` / `6E 01 00 00 6F` | `57` / `00` |
| 9d825ec713c7 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `50` / `00` |
| 9f2152edb06d | deviceFunctionItemHeadDown / shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |
| 9f51b232b380 | deviceFunctionItemMassageHeadOff / shortPress | `6E 01 00 98 07` / `6E 01 00 00 6F` | `98` / `00` |
| a01900db2834 | deviceFunctionItemMassage15MinuteSpineGuard / shortPress | `6E 01 00 76 E5` / `6E 01 00 00 6F` | `76` / `00` |
| a186fa8a102b | deviceFunctionItemPillowDown / sustainPress | `6E 01 00 80 EF` / `6E 01 00 00 6F` | `80` / `00` |
| a1da564a9027 | deviceFunctionItemTVPosition / shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `33` / `64` |
| a3873cba2a70 | deviceFunctionSofaSitPosition / sustainPress | `6E 01 00 E5 54` / `6E 01 00 00 6F` | `E5` / `00` |
| a3b39b7b566f | deviceFunctionItemMotorReset / shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |
| a60c7745771b | deviceFunctionItemBedLight / shortPress | `6E 01 00 3C AB` / `6E 01 00 00 6F` | `36` / `00` |
| a63e4733c91c | deviceFunctionItemMassage30MinuteTimer / shortPress | `6E 01 00 A3 12` / `6E 01 00 00 6F` | `A3` / `00` |
| a72bd4817ca1 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |
| a74fd401b687 | deviceFunctionItemFootUp / sustainPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `37` / `00` |
| a8018fb49c3e | deviceFunctionItemTitleMassage / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| a89fad642679 | deviceFunctionItemMassageHeadInstensityWeaken / shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `49` / `00` |
| a90aac0dab9b | deviceFunctionItemDeepSleepPosition / shortAndLongPress | `6E 01 00 F6 65` / `6E 01 00 F7 66` | `F6` / `F7` |
| a932d7d08150 | deviceFunctionItemMassage20MinuteTimer / shortPress | `6E 01 00 A2 11` / `6E 01 00 00 6F` | `A2` / `00` |
| aa1e731452e0 | deviceFunctionItemHeadUp / shortPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |
| aa91f303c38d | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 BA 29` / `6E 01 00 00 6F` | `BA` / `00` |
| ab5952b9edf7 | deviceFunctionSofaPillowDown / sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |
| ab65d2e4193c | deviceFunctionItemYogaPosition / shortPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |
| ac2104a8d1f6 | deviceFunctionItemRelaxPosition / shortAndLongPress | `6E 01 00 70 DF` / `6E 01 00 95 04` | `70` / `95` |
| ade69bf0acfc | deviceFunctionItemMotor4Up / shortAndLongPress | `6E 01 00 73 E2` / `6E 01 00 00 6F` | `73` / `00` |
| ae200466d8a6 | deviceFunctionAirbagPillowSwitch / shortPress | `6E 01 00 CF 3E` / `6E 01 00 00 6F` | `CF` / `00` |
| ae5bc6ff0245 | deviceFunctionItemHeadAndFootUp / sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `29` / `00` |
| b1a788a4bb5b | deviceFunctionItemFan1InstensityStrengthen / shortPress | `6E 01 00 8A F9` / `6E 01 00 00 6F` | `8A` / `00` |
| b1e63ceb9e68 | deviceFunctionItemCoaxingSleepMode3 / shortPress | `6E 01 00 88 F7` / `6E 01 00 00 6F` | `88` / `00` |
| b1fd54d08341 | deviceFunctionItemHeadDown / shortPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |
| b2198a58197b | deviceFunctionItemMotorReset / shortPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `32` / `00` |
| b2b08b2b55b7 | deviceFunctionItemMotorReset2 / shortPress | `6E 01 00 6C DB` / `6E 01 00 00 6F` | `6C` / `00` |
| b2cc8582c5ea | deviceFunctionItemPillowDown / sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `45` / `00` |
| b4b8d12b8d58 | deviceFunctionItemHelpGetUpPosition / shortAndLongPress | `6E 01 00 3D AC` / `6E 01 00 F8 67` | `3D` / `F8` |
| b4bc7b0ab4f2 | deviceFunctionItemFanTimer5Hour / shortPress | `6E 01 00 A8 17` / `6E 01 00 00 6F` | `A8` / `00` |
| b50f84eeaf59 | deviceFunctionItemAlarmMode1 / shortPress | `6E 01 00 B0 1F` / `6E 01 00 00 6F` | `B0` / `00` |
| b59d0afa1b56 | deviceFunctionItemAromatherapy / shortAndLongPress | `6E 01 00 3B AA` / `6E 01 00 00 6F` | `3B` / `00` |
| b82f35ef9c9c | deviceFunctionItemFootUp / sustainPress | `6E 01 00 26 95` / `6E 01 00 00 6F` | `26` / `00` |
| b89dc016ba5e | deviceFunctionItemLoungePosition / shortPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `59` / `65` |
| b8ae596bdcff | deviceFunctionItemMassageModeChange / shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `4A` / `00` |
| b96eba48cb6a | deviceFunctionItemMemoryPosition2 / shortPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `44` / `2C` |
| b9d7fc9cd4d2 | deviceFunctionSofaPillowUp / sustainPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |
| b9fd99466308 | deviceFunctionItemMassageModeWave / shortPress | `6E 01 00 39 A8` / `6E 01 00 00 6F` | `39` / `00` |
| bb01554b17a8 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 61 D0` / `6E 01 00 00 6F` | `61` / `00` |
| bd4b6927a35c | deviceFunctionItemYogaPosition / shortAndLongPress | `6E 01 00 6B DA` / `6E 01 00 6A D9` | `6B` / `6A` |
| be741e4841de | deviceFunctionItemAllMotorDown / sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |
| beea25299ceb | deviceFunctionItemTitleMassageRussian / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| bf0dc6e541c4 | deviceFunctionItemTitleFan / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| bfde3a3a34b4 | deviceFunctionItemMemoryPosition3 / shortPress | `6E 01 00 2D 9C` / `6E 01 00 2D 9C` | `2D` / `2D` |
| c03b8e2a8fbb | deviceFunctionItemTVPosition / sustainPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |
| c0c739d85916 | deviceFunctionItemHeadUpAndFootDown / sustainPress | `6E 01 00 21 90` / `6E 01 00 00 6F` | `21` / `00` |
| c1ee3907b355 | deviceFunctionItemAllMotorDown / sustainPress | `6E 01 00 88 F7` / `6E 01 00 00 6F` | `88` / `00` |
| c2112226b40f | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `49` / `00` |
| c2fb85dff51a | deviceFunctionItemFootDown / sustainPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `41` / `00` |
| c3b474f99c00 | deviceFunctionItemSyncOff / shortPress | `6E 01 00 BD 2C` / `6E 01 00 BD 2C` | `BD` / `BD` |
| c3cc6b473b6c | deviceFunctionItemMassageHeadInstensityStrengthen / shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `42` / `00` |
| c5b0f8225ba7 | deviceFunctionItemLumberUp / sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `3F` / `00` |
| c5cfd88a0063 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `47` / `00` |
| c6e7a2285522 | deviceFunctionItemSyncOn / shortPress | `6E 01 00 BC 2B` / `6E 01 00 BC 2B` | `BC` / `BC` |
| c73a9fadc0cd | deviceFunctionItemMusicShakeMode / shortPress | `6E 01 00 D6 45` / `6E 01 00 00 6F` | `D6` / `00` |
| c7b35ccf498d | deviceFunctionItemMemoryPosition5 / shortAndLongPress | `6E 01 00 F4 63` / `6E 01 00 F5 64` | `F4` / `F5` |
| c93ed25f45e4 | deviceFunctionItemPillowUp / sustainPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |
| c998a5ea1890 | deviceFunctionItemHeadAndFootUp / sustainPress | `6E 01 00 29 98` / `6E 01 00 00 6F` | `36` / `00` |
| cb84d65549c2 | deviceFunctionItemMassageSwitch / shortAndLongPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `4C` / `00` |
| cbaf3b6f4035 | deviceFunctionItemLoungePosition / shortAndLongPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `32` / `65` |
| cbb374ca38ea | deviceFunctionItemHeadAndFootDown / shortPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `2A` / `00` |
| cc068f3311b4 | deviceFunctionItemLumberAndPillowDown / sustainPress | `6E 01 00 44 B3` / `6E 01 00 00 6F` | `44` / `00` |
| ccbaa9322b74 | deviceFunctionItemLumberUp / sustainPress | `6E 01 00 82 F1` / `6E 01 00 00 6F` | `82` / `00` |
| ccc2a945e831 | deviceFunctionItemAdjustVolume / shortPress | `6E 01 00 B7 26` / `6E 01 00 00 6F` | `B7` / `00` |
| cdfa48e8574e | deviceFunctionSofaZeroGravityMotorUp / sustainPress | `6E 01 00 71 E0` / `6E 01 00 00 6F` | `71` / `00` |
| ce185a33a177 | deviceFunctionItemMemoryPosition2 / shortAndLongPress | `6E 01 00 2F 9E` / `6E 01 00 2C 9B` | `44` / `2C` |
| cedc2c60bea8 | deviceFunctionItemRelieveSnoreSetting / shortPress | `6E 01 00 CB 3A` / `6E 01 00 00 6F` | `CB` / `00` |
| cf339c0f5687 | deviceFunctionItemHelpSleepMode1 / shortAndLongPress | `6E 01 00 86 F5` / `6E 01 00 00 6F` | `86` / `00` |
| cf751a703c94 | deviceFunctionItemMassageModeWaveThirdMode / shortPress | `6E 01 00 4B BA` / `6E 01 00 00 6F` | `4B` / `00` |
| d19a07b24108 | deviceFunctionItemMemoryPosition2 / shortPress | `6E 01 00 2C 9B` / `6E 01 00 2C 9B` | `2C` / `2C` |
| d221a0c433b7 | deviceFunctionAirbagFootSwitch / shortPress | `6E 01 00 CD 3C` / `6E 01 00 00 6F` | `CD` / `00` |
| d4192859a471 | deviceFunctionItemLumberUp / sustainPress | `6E 01 00 3F AE` / `6E 01 00 00 6F` | `42` / `00` |
| d4d9d796e2f6 | deviceFunctionItemMotorReset / shortPress | `6E 01 00 47 B6` / `6E 01 00 00 6F` | `47` / `00` |
| d5845b8f6cd4 | deviceFunctionItemAlarmMode1 / shortPress | `6E 01 00 F5 64` / `6E 01 00 00 6F` | `F5` / `00` |
| d6190dbad27a | deviceFunctionItemFanTimer2Hour / shortPress | `6E 01 00 A6 15` / `6E 01 00 00 6F` | `A6` / `00` |
| d634e893754f | deviceFunctionItemFootDown / sustainPress | `6E 01 00 27 96` / `6E 01 00 00 6F` | `27` / `00` |
| d70b447d20a4 | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 48 B7` / `6E 01 00 00 6F` | `48` / `00` |
| d71812168b1b | deviceFunctionItemMassageModeAllOff / shortPress | `6E 01 00 5F CE` / `6E 01 00 00 6F` | `4C` / `00` |
| d752369adf34 | deviceFunctionItemMassageModeWave / shortAndLongPress | `6E 01 00 48 B7` / `6E 01 00 47 B6` | `48` / `47` |
| d86d11220ae9 | deviceFunctionItemMemoryPosition2 / shortPress | `6E 01 00 2C 9B` / `6E 01 00 2C 9B` | `45` / `2C` |
| d959e04c5afb | deviceFunctionItemMotor4Up / sustainPress | `6E 01 00 73 E2` / `6E 01 00 00 6F` | `73` / `00` |
| da7d355f20b0 | deviceFunctionItemMusicPausePlay / shortPress | `6E 01 00 D7 46` / `6E 01 00 00 6F` | `D7` / `00` |
| db50fc8b2ab6 | deviceFunctionItemMassageSwitch / shortPress | `6E 01 00 6F DE` / `6E 01 00 00 6F` | `6F` / `00` |
| db5ea9c30d9c | deviceFunctionItemMusicShakeSecondGear / shortPress | `6E 01 00 DE 4D` / `6E 01 00 00 6F` | `DE` / `00` |
| dc97e2bd52e7 | deviceFunctionItemLumberAndPillowUp / sustainPress | `6E 01 00 43 B2` / `6E 01 00 00 6F` | `43` / `00` |
| dd397c2b9ee9 | deviceFunctionItemMusicVolumuDown / shortPress | `6E 01 00 D5 44` / `6E 01 00 00 6F` | `D5` / `00` |
| dd64ad4208ed | deviceFunctionItemLumberUp / sustainPress | `6E 01 00 41 B0` / `6E 01 00 00 6F` | `41` / `00` |
| de11c48d4569 | deviceFunctionItemAllMotorUp / sustainPress | `6E 01 00 43 B2` / `6E 01 00 00 6F` | `43` / `00` |
| de16c1ec2bc9 | deviceFunctionItemMassageFootInstensityStrengthen / shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `48` / `00` |
| de3277b9f758 | deviceFunctionItemHeadAndFootDown / sustainPress | `6E 01 00 2A 99` / `6E 01 00 00 6F` | `72` / `00` |
| de82af361206 | deviceFunctionItemMassageHeadInstensityWeaken / shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `4D` / `00` |
| deb93f913eee | deviceFunctionItemMassageInstensitySecondGear / shortPress | `6E 01 00 4D BC` / `6E 01 00 00 6F` | `4D` / `00` |
| e16e0cd9d82a | deviceFunctionItemCoaxingSleepMode / shortPress | `6E 01 00 86 F5` / `6E 01 00 89 F8` | `86` / `89` |
| e1edeb9dcc6e | deviceFunctionItemFanAllOff / shortPress | `6E 01 00 A1 10` / `6E 01 00 00 6F` | `A1` / `00` |
| e2a8e5e02a7e | deviceFunctionItemPillow2Down / shortAndLongPress | `6E 01 00 7B EA` / `6E 01 00 00 6F` | `7B` / `00` |
| e2e430d20566 | deviceFunctionItemMassageModeWave / shortPress | `6E 01 00 39 A8` / `6E 01 00 00 6F` | `45` / `00` |
| e33a14c3a7fb | deviceFunctionItemMassageFootInstensityStrengthen / shortPress | `6E 01 00 4E BD` / `6E 01 00 00 6F` | `44` / `00` |
| e367c085fcec | deviceFunctionItemLumberDown / sustainPress | `6E 01 00 84 F3` / `6E 01 00 00 6F` | `84` / `00` |
| e45fa296fec6 | deviceFunctionItemAllMotorUp / sustainPress | `6E 01 00 86 F5` / `6E 01 00 00 6F` | `86` / `00` |
| e4c73fd5e987 | deviceFunctionSofaHeadDown / sustainPress | `6E 01 00 25 94` / `6E 01 00 00 6F` | `25` / `00` |
| e50dd75b517b | deviceFunctionItemMotorReset / shortAndLongPress | `6E 01 00 31 A0` / `6E 01 00 00 6F` | `31` / `00` |
| e527904360a5 | deviceFunctionItemMemoryPosition4 / shortPress | `6E 01 00 B2 21` / `6E 01 00 B3 22` | `B2` / `B3` |
| e682c266d31b | deviceFunctionItemMusicCut / shortPress | `6E 01 00 B8 27` / `6E 01 00 00 6F` | `B8` / `00` |
| e6cc77b9883b | deviceFunctionItemMassageInstensityStrengthen / shortPress | `6E 01 00 34 A3` / `6E 01 00 00 6F` | `48` / `00` |
| e7145fceece1 | deviceFunctionSofaLumbarDown / sustainPress | `6E 01 00 40 AF` / `6E 01 00 00 6F` | `40` / `00` |
| e71e0fe63b0f | deviceFunctionItemPhoneLight / shortAndLongPress (local) | no BLE | no BLE |
| e8b56157ff71 | deviceFunctionItemNone / shortAndLongPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| e90839281af1 | deviceFunctionItemMassageModeWaveSecondMode / shortPress | `6E 01 00 4A B9` / `6E 01 00 00 6F` | `4A` / `00` |
| ea01c54f5727 | deviceFunctionItemMassageHeadInstensFirstMode / shortPress | `6E 01 00 99 08` / `6E 01 00 00 6F` | `99` / `00` |
| eb67babb26cf | deviceFunctionItemMassageModeWaveFirstMode / shortPress | `6E 01 00 49 B8` / `6E 01 00 00 6F` | `49` / `00` |
| eb7965cc2b32 | deviceFunctionItemMotor3Down / sustainPress | `6E 01 00 72 E1` / `6E 01 00 00 6F` | `72` / `00` |
| ed0fcf6f5099 | deviceFunctionItemPhoneLight / shortPress (local) | no BLE | no BLE |
| edf64c411999 | deviceFunctionItemZeroGravity / shortPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `34` / `66` |
| edf7eabe88e0 | deviceFunctionItemMassage1Instensity / shortPress | `6E 01 00 A4 13` / `6E 01 00 00 6F` | `A4` / `00` |
| f06d71f5757a | deviceFunctionSofaZeroGravityMotorDown / sustainPress | `6E 01 00 72 E1` / `6E 01 00 00 6F` | `72` / `00` |
| f17c7ae2d266 | deviceFunctionItemLoungePosition / shortPress | `6E 01 00 59 C8` / `6E 01 00 65 D4` | `32` / `65` |
| f253c5c3b44b | deviceFunctionItemDeepSleepPosition / shortPress | `6E 01 00 F6 65` / `6E 01 00 F7 66` | `F6` / `F7` |
| f2b8b295e814 | deviceFunctionItemHeadUp / sustainPress | `6E 01 00 24 93` / `6E 01 00 00 6F` | `24` / `00` |
| f354ae292d2d | deviceFunctionItemTVPosition / shortPress | `6E 01 00 58 C7` / `6E 01 00 64 D3` | `58` / `64` |
| f47f29344bc8 | deviceFunctionItemNone / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| f4b3b8be75d2 | deviceFunctionItemAntiSnoring / sustainPress | `6E 01 00 46 B5` / `6E 01 00 69 D8` | `46` / `69` |
| f5107d4d7128 | deviceFunctionItemMassageInstensityThirdGear / shortPress | `6E 01 00 68 D7` / `6E 01 00 00 6F` | `4E` / `00` |
| f524675f0711 | deviceFunctionItemMassageModeConstant / shortPress | `6E 01 00 3A A9` / `6E 01 00 00 6F` | `47` / `00` |
| f60a3278f7ee | deviceFunctionItemHeadAndFootUp / sustainPress | `6E 01 00 96 05` / `6E 01 00 00 6F` | `96` / `00` |
| f6310d43b778 | deviceFunctionItemMemoryPosition1 / shortPress | `6E 01 00 2B 9A` / `6E 01 00 2B 9A` | `43` / `2B` |
| f765539996b9 | deviceFunctionItemMassageInstensityWeaken / shortPress | `6E 01 00 35 A4` / `6E 01 00 00 6F` | `4B` / `00` |
| f989986de6b8 | deviceFunctionItemYogaPosition / shortAndLongPress | `6E 01 00 F0 5F` / `6E 01 00 F1 60` | `F0` / `F1` |
| f9b05d5ab4bb | deviceFunctionItemReadingPosition / shortAndLongPress | `6E 01 00 F3 62` / `6E 01 00 F2 61` | `F3` / `F2` |
| fa506142451f | deviceFunctionItemMotor3Down / shortAndLongPress | `6E 01 00 72 E1` / `6E 01 00 00 6F` | `72` / `00` |
| faadbc92ccae | deviceFunctionItemMassage2OpenOrClose / shortPress | `6E 01 00 33 A2` / `6E 01 00 00 6F` | `33` / `00` |
| fbf8e6b81d09 | deviceFunctionItemTitleMassageJapan / shortPress | `6E 01 00 00 6F` / `6E 01 00 00 6F` | `00` / `00` |
| fd7e4ffdbcc4 | deviceFunctionItemFootUpAndHeadDown / shortPress | `6E 01 00 22 91` / `6E 01 00 00 6F` | `22` / `00` |
| fdc61ea14bbd | deviceFunctionItemPillowDown / sustainPress | `6E 01 00 42 B1` / `6E 01 00 00 6F` | `42` / `00` |
| fe4854c04187 | deviceFunctionItemFanChangeMode / shortPress | `6E 01 00 A2 11` / `6E 01 00 00 6F` | `A2` / `00` |
| fe81a90583c6 | deviceFunctionItemMassageHeadInstensityStrengthen / shortPress | `6E 01 00 4C BB` / `6E 01 00 00 6F` | `49` / `00` |
| ffb1a70dc13d | deviceFunctionItemZeroGravity / sustainPress | `6E 01 00 45 B4` / `6E 01 00 66 D5` | `45` / `66` |
<!-- /generated -->

#### Timing

A sustained control first sends after 100 ms, then refreshes while held. Only
those controls advertise renewable holds; a local memory latch can change a
sustained action to one long operand. Short presses send on activation. Long and
short-and-long gestures use the app's 3-second threshold. Release after an active
short or sustained gesture sends the ordinary side-scoped STOP, using a fresh
cleanup path that cancellation cannot suppress. Short-and-long and long gestures
retain the app's absence of that automatic release. Explicit Stop always sends
STOP. A command in flight cannot be retracted.

Writes are serialized and paced at least 100 ms after completion. Home Assistant
invalidates pending movement on cancellation rather than replaying the Android
FIFO's stale movement. It checks the current connection again after pacing and
ignores notifications from replaced links. There is no app-level automatic write
retry, normal-message fragmentation or invented startup command. Notification
remainders expire after 500 ms; malformed packets are discarded without blocking
subsequent commands or publishing invented values.

<!-- generated:galaxy-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

Subscribe before initialization. Queue the applicable local time and sleep-name
records, then check clock and light on the 300 ms menu schedule. Sync the two
local time records only for a product with an alarm list; query the sleep
advertisement name only for the nine BLE-enabled bed products. The catalog keeps
each copied configuration’s own gates.

| Step | Framed / Nordic |
|---|---|
| Check clock | `6E 08 01 01 78` / `01` |
| Check light | `6E 0A 00 01 79` / `01` |
<!-- /generated -->

#### Notifications

The Galaxy bed status sensor exposes decoded events as attributes, including
motor/angle records, massage, lights, lock, fan, heating, atomization, alarm
acknowledgements and records, diagnostics and bed sleep-advertisement metadata.
Raw values retain their reported numbering and units; they do not create assumed
percentage sliders. Atomization retains both timer bytes. Empty blanket models
remain empty rather than reporting computations the app never stored. Diagnostic
and audio-related replies remain observable without starting phone audio or
creating separate accessory integrations.

Clock replies enable the alarm menu only when the current product has an alarm
list; PNRN also has its initial menu exception. Light replies require the current
product's light flag. The first admitted ASCII sleep-name reply is cached until
the link is reset. Only the nine BLE-enabled bed products admit it; the six
HNRN/HQRN/HSRN/HURN/M7RN/MJRN products also admit the bed's anti-snore settings.
Parser press-mode events do not change the local release, hold or memory flags.

Separate sleep monitors, network setup, cloud accounts, firmware updates, desk
screens and standalone accessories are not part of this bed profile. Their
shared framing cannot stall the bed notification stream.

#### Services

`adjustable_bed.galaxy` provides product-gated alarm scheduling/cancellation,
repeat slots, time synchronization, RGB, light timeout/off, massage countdown and
bed anti-snore settings. Use `single`, `cancel_single`, `repeat`, `delete`,
`alarms`, `enable_alarm`, `sync`, `light_color`, `light_duration`, `light_off`, `massage_timer`,
`snore_switch`, `snore_count`, `snore_time` or `snore_query`. Alarm writes take an
exact action ID from the selected product's alarm list. Repeat alarms use slots
1 through 7, Monday 0 through Sunday 6, and an explicit enable flag. `enable_alarm` changes an observed slot’s enabled bit while preserving all six received fields, including the reserved field and weekday mask. Query `alarms` first. Validating
all targets precedes execution; connection-time capability replies are checked
again before a feature write. A freshly connected bed must report the relevant
capability before that setting is used.

The advanced settings use the Galaxy length-before-domain record form, distinct
from the length-after-domain records other apps use. RGB remains two checksummed
subframes in one write. No raw-command or separate-sensor service is exposed.

<!-- generated:galaxy-settings -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Setting / query | Write |
|---|---|
| alarms | `6E 08 20 05 01 00 00 9C` |
| sleep_name | `6E 08 20 06 03 00 00 9F` |
| snore_switch | `6E 08 20 06 01 00 00 9D` |
| snore_config | `6E 09 20 06 05 00 00 00 A2` |
| snore on | `6E 09 20 06 01 01 00 01 A0` |
| snore count 3 | `6E 0A 20 06 05 01 01 00 03 A8` |
| snore time 15 | `6E 0A 20 06 05 01 02 00 0F B5` |
| repeat slot 1, 07:30, mode 2, Mon/Sun enabled | `6E 0D 20 05 01 01 01 00 07 1E 02 83 4D` |
| delete slot 3 | `6E 08 20 05 02 01 03 A1` |
| light 300 seconds | `6E 0B 01 2C A6` |
| red | `6E 0C FF FF 78 6E 0D 00 00 7B` |
| D1RM massage countdown 0 min | `6E 01 00 5E CD` |
| D1RM massage countdown 10 min | `6E 01 00 5F CE` |
| D1RM massage countdown 20 min | `6E 01 00 63 D2` |
| D1RM massage countdown 30 min | `6E 01 00 61 D0` |
| D9RM massage countdown 0 min | `6E 01 00 8B FA` |
| D9RM massage countdown 10 min | `6E 01 00 5F CE` |
| D9RM massage countdown 20 min | `6E 01 00 63 D2` |
| D9RM massage countdown 30 min | `6E 01 00 61 D0` |
<!-- /generated -->

#### Evidence

Row A09's accepted whole-artifact reconciliation binds every selector to its
current getters, installed copied configuration, screen route and session state.
The 48,642 ordinary frozen literals are carried by `tests/fixtures/galaxy` and
encoded by `codec/richmat.py`; focused tests also cover normal advanced builders,
parsers, countdown commits and reconciled runtime transitions. This is static
app evidence, not a claim of hardware validation. Real beta/release users can
validate firmware, physical sides and release behavior with timestamped captures.

Analysis provenance: `nl.starinternational.galaxy` 3.3.0 (330002), primary arm64
artifact SHA-256 `9a0b0cca3d62c85a749a17cfacd772740f5b07be85687c491cf269ac85646bdb`;
accepted reconciliation manifest
`bb26a0b2a2d97af9e91b40dc83aaf2b7cd46c4753710aa1a2e797ffc64199b59`.
Supplemental v7a delivery is not interchangeable evidence.

## Luuna Rise / Power Cool

**Status:** ❓ Needs testing. Static protocol support is implemented; physical
targets, selected product compatibility and firmware effects are unverified.

### Known Models

Select the app first, then its exact four-character layout. Luuna Rise has its
own 604-layout catalog and Power Cool its own 586-layout catalog. An app name,
shared Bluetooth service or matching opcode does not establish a product match.
Luuna's H-series layouts include HKRM with its own Left/Right selector. AHRM's
one-shot action differs between apps; Luuna also has an H9RM reset-labelled
action that is absent in Power Cool. That label does not prove a factory reset.

### Features

Layout-bound movement, combined movement, recall/save, massage, USB, fan, lock
and light-labelled controls retain the selected app's gesture and visibility
gates. Lock and vibration targets remain unknown. No motor position, battery,
model identity or general command acknowledgment is reported by these apps.
Settings provide alarm countdowns and combinations, RGB, lamp timers and the
D1RM/D9RM/Y6RM timer utilities. A lamp capability reply reveals a timer number
entity without a reload. Its value is a local requested setting, not readback.

Power Cool's explicit TEST layout offers a finite 14-step motor diagnostic
cycle. Its RMCS layout programs a 12-record motor schedule. Select these layouts
deliberately and use `adjustable_bed.richmat_rise`. RMCS has no proven readback,
abort, commit or acknowledgment command. Radio selection is a field in the
program; the phone still sends it over BLE.

### Detection / Setup

Search for **Luuna Rise** or **Power Cool Sleep System** in the Richmat app
question. Choose the layout that matches your app, including manual selection
for QRRM / Cool Touch / 209A05 devices. Layout and fallback settings belong to
one physical address. Stored choices and local preferences do not identify the
firmware. A shared name or service never selects either app automatically.
The third-service fallback remains an explicit advanced opt-in, with runtime
characteristics rather than guessed UUIDs. Standalone desk layouts are omitted.

### Protocol Details

Both profiles use the [Richmat transports](#transports), in W1, W2, Nordic UART,
W4 order. The first present service wins; incomplete roles do not fall through.
Raw Nordic/fallback controls send the selected resource bytes. Wrapped controls
send `6E 01 mode command sum8`. A raw mode choice adds no side bytes. Direct
structured settings bypass that wrapper on either route. No PIN, authentication
handshake, MTU negotiation or firmware query is added.

Successful local subscription on a wrapped route precedes initialization by
300 ms. Notification failure suppresses initialization and capability proof,
while ordinary bed controls remain usable. Settings query alarm capability
only when the layout has alarm choices, then lamp capability, 500 ms apart.
Replies are checked on the current connection; cached Android flags and handles
cannot authorize a new session.

### Commands

Status 1 refreshes while held, status 2 is a one-shot with 150 ms release,
and status 3 offers short recall or thresholded long action. E3RM's local MEM
selector overrides status 3: normal recall refreshes while held; armed save
sends on the next poll; both end with the 50 ms release. Hold/Release overlays
are limited to BRRM/YFRM/YGRM. GVRM's uninitialized old-long field emits no foot
command. U3RM's selected tag changes its additional actuator bytes.

The table preserves exact layout eligibility. Hidden controls remain hidden
unless a proven overlay reveals them. Resource names are app labels, not proof
of motor anatomy. Short music actions are unavailable while independently
proven long lock-labelled gestures remain available.

<!-- generated:richmat-rise-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Utility | Bytes | Availability |
|---|---|---|
| Alarm query | `6E 08 01 01 78` | Selected layout has alarm actions |
| Lamp query | `6E 0A 00 01 79` | Every selected bed layout |
| Cancel alarm | `6E 05 00 00 73` / `6E 06 00 00 74` | Live alarm capability |
| Lamp zero, slider | `6E 0B FF FF 77` | Live lamp capability |
| Lamp zero, Save | `6E 0B 00 00 79` | Live lamp capability |
| Lamp 300 seconds | `6E 0B 01 2C A6` | Live lamp capability |
| RGB 1,221,255 | `6E 0C FF 01 7A 6E 0D DD FF 57` | Live lamp capability; one concatenated write |
| D1RM/D9RM slider 0 | `6E 01 00 5E CD` / `6E 01 00 8B FA` | Exact selected layout only |
| D1RM/D9RM slider 1 | `6E 01 00 01 70` / `6E 01 00 01 70` | Exact selected layout only |
| D1RM/D9RM slider 2 | `6E 01 00 5F CE` / `6E 01 00 5F CE` | Exact selected layout only |
| D1RM/D9RM slider 3 | `6E 01 00 63 D2` / `6E 01 00 63 D2` | Exact selected layout only |
| D1RM/D9RM slider 4 | `6E 01 00 04 73` / `6E 01 00 04 73` | Exact selected layout only |
| D1RM/D9RM slider 5 | `6E 01 00 61 D0` / `6E 01 00 61 D0` | Exact selected layout only |
| Y6RM popup 15 | `6E 01 00 5F CE` | Layout offers tag 65 |
| Y6RM popup 30 | `6E 01 00 63 D2` | Layout offers tag 65 |
| Y6RM popup 45 | `6E 01 00 61 D0` | Layout offers tag 65 |
| Y6RM popup toggle | `6E 01 00 5E CD` | Layout offers tag 65 |

| Alarm preset byte | With all massage | With head massage | With foot massage |
|---|---|---|---|
| `58` | `77` | `7A` | `7D` |
| `46` | `78` | `7B` | `7E` |
| `45` | `79` | `7C` | `7F` |
| `59` | `AC` | `AD` | `AE` |
| `2E` | `81` | `82` | `83` |
| `2F` | `A6` | `A7` | `A8` |
| `30` | `A9` | `AA` | `AB` |

### Luuna Rise resource commands

<details><summary>Selected-layout command and gesture gates</summary>


| Layouts | Short | Raw old-short | Long | Status | Tag | Threshold ms | Initial visibility |
|---|---|---|---|---|---|---|---|
| BORM | 21 | none | none | 1 | none | 3000 | visible |
| APRM, AQRM, BRRM, C2RM, C9RM, DYRM, HCRM, OORM, OURM, OWRM, WYRM, YFRM, YGRM | 21 | none | none | 2 | none | 3000 | visible |
| BORM | 22 | none | none | 1 | none | 3000 | visible |
| APRM, AQRM, BRRM, C2RM, C9RM, DYRM, HCRM, OORM, OURM, OWRM, YFRM, YGRM | 22 | none | none | 2 | none | 3000 | visible |
| AERM, AFRM, AGRM, ALRM, AMRM, ANRM, APRM, AQRM, BRRM, C2RM, C9RM, HCRM, OORM, Y1RM, YFRM, YGRM, YQRM | 23 | none | none | 2 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A6RM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM | 24 | 34 | none | 1 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 24 | 35 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ARRM, ASRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B2RM, B3RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BSRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E2RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F2RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, HARM, HBRM, HCRM, HDRM, HERM, HKRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IJRM, IKRM, ILRM, IMRM, INRM, IORM, IPRM, IQRM, IRRM, ISRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OVRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WMRM, WNRM, WORM, WPRM, WQRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XDRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR01, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 24 | none | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A6RM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM | 25 | 37 | none | 1 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 25 | 38 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ARRM, ASRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B2RM, B3RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BSRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E2RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F2RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, HARM, HBRM, HCRM, HDRM, HERM, HKRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IJRM, IKRM, ILRM, IMRM, INRM, IORM, IPRM, IQRM, IRRM, ISRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OVRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WMRM, WNRM, WORM, WPRM, WQRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XDRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR01, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 25 | none | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A6RM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM | 26 | 36 | none | 1 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 26 | 37 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, HARM, HBRM, HCRM, HDRM, HERM, HKRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, INRM, IORM, IPRM, IQRM, IRRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WPRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 26 | none | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A3RM, A6RM, BERM, GMRM, MMRM, ONRM, R2RM, T4RM, THRM, TWRM, TZRM, V3RM | 27 | 41 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, HARM, HBRM, HCRM, HDRM, HERM, HKRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, INRM, IORM, IPRM, IQRM, IRRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WPRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 27 | none | none | 1 | none | 3000 | visible |
| A3RM, MMRM, R2RM | 29 | 36 | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, GMRM, T4RM, THRM, TWRM, V3RM | 29 | 38 | none | 1 | none | 3000 | visible |
| A2RM, ATRM, AURM, AVRM, AWRM, AYRM, B0RM, B6RM, B7RM, BFRM, BGRM, BHRM, BKRM, BNRM, BQRM, BURM, C5RM, CBRM, CERM, CKRM, CMRM, CORM, CSRM, CYRM, D2RM, D5RM, D7RM, DFRM, DHRM, DIRM, DMRM, DURM, DVRM, E0RM, E3RM, E5RM, EFRM, ENRM, EQRM, ESRM, ETRM, F3RM, F5RM, FARM, FBRM, FIRM, FRRM, FVRM, FYRM, G2RM, G3RM, G5RM, G8RM, G9RM, GCRM, GERM, GHRM, GORM, GRRM, GSRM, GXRM, GYRM, H5RM, H8RM, HARM, HERM, HKRM, HMRM, HNRM, HQRM, HTRM, HVRM, I2RM, I3RM, IARM, IDRM, IIRM, IPRM, IQRM, IRRM, M4RM, M6RM, MARM, O2RM, O3RM, O9RM, OARM, OPRM, OQRM, OXRM, P0RM, P2RM, P3RM, P4RM, P5RM, R5RM, R6RM, T8RM, TARM, TCRM, TDRM, TLRM, U0RM, U1RM, U4RM, U8RM, UCRM, UFRM, UJRM, UKRM, ULRM, UPRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V4RM, V5RM, V6RM, VARM, VXRM, VYRM, W0RM, W2RM, W5RM, W6RM, W7RM, WERM, WKRM, WRRM, WSRM, WTRM, WURM, WVRM, WZRM, X4RM, X5RM, X7RM, X8RM, XERM, XHRM, XIRM, XJRM, XKRM, XNRM, XORM, XWRM, Y3RM, YHRM, YJRM, YWRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z4RM, Z5RM, Z7RM, Z8RM, ZBRM, ZCRM, ZDRM, ZERM, ZJRM, ZR10, ZR20, ZR30, ZR51, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZURM, ZZRM | 29 | none | none | 1 | none | 3000 | visible |
| 6BRM, A3RM, GMRM, MMRM, R2RM, T4RM, THRM, TWRM, V3RM, VYRM, W0RM, W2RM, YJRM | 2A | 39 | none | 1 | none | 3000 | visible |
| A2RM, ATRM, AURM, AVRM, AWRM, AYRM, B6RM, B7RM, BFRM, BGRM, BHRM, BNRM, BQRM, BURM, C5RM, CBRM, CERM, CKRM, CORM, CYRM, D2RM, D5RM, DFRM, DHRM, DIRM, DMRM, DURM, DVRM, E0RM, E3RM, E5RM, EFRM, ENRM, EQRM, ESRM, ETRM, F3RM, F5RM, FARM, FBRM, FIRM, FRRM, FVRM, FYRM, G2RM, G3RM, G5RM, G8RM, G9RM, GCRM, GERM, GHRM, GORM, GSRM, GXRM, GYRM, H5RM, H8RM, HARM, HERM, HKRM, HMRM, HNRM, HQRM, HTRM, HVRM, I2RM, I3RM, IARM, IDRM, IIRM, IPRM, IQRM, IRRM, M4RM, MARM, O2RM, O3RM, O9RM, OARM, OPRM, OQRM, OXRM, P0RM, P2RM, P3RM, P4RM, P5RM, R5RM, R6RM, T8RM, TARM, TCRM, TDRM, TLRM, U0RM, U1RM, U4RM, UCRM, UFRM, UJRM, UKRM, ULRM, UPRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V4RM, VXRM, W5RM, W6RM, W7RM, WERM, WKRM, WRRM, WSRM, WTRM, WURM, WVRM, WZRM, X4RM, X5RM, X7RM, X8RM, XERM, XHRM, XIRM, XJRM, XKRM, XNRM, XORM, XWRM, Y3RM, YHRM, YWRM, YYRM, YZRM, Z1RM, Z2RM, Z4RM, Z5RM, Z7RM, Z8RM, ZBRM, ZDRM, ZERM, ZR10, ZR20, ZR30, ZR51, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZURM, ZZRM | 2A | none | none | 1 | none | 3000 | visible |
| MMRM, R2RM | 2B | 43 | none | 2 | none | 3000 | visible |
| BRRM, YFRM, YGRM | 2B | none | none | 2 | none | 3000 | hidden |
| APRM, AQRM, C2RM, C9RM, HCRM, OMRM, VXRM | 2B | none | none | 2 | none | 3000 | visible |
| MMRM, R2RM | 2C | 45 | none | 2 | none | 3000 | visible |
| BRRM, YFRM, YGRM | 2C | none | none | 2 | none | 3000 | hidden |
| APRM, AQRM, C2RM, C9RM, VXRM | 2C | none | none | 2 | none | 3000 | visible |
| VXRM | 2D | none | none | 2 | none | 3000 | visible |
| A3RM | 2E | 42 | 2B | 3 | none | 3000 | visible |
| MMRM, R2RM | 2E | 42 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A9RM, ABRM, ADRM, AERM, AFRM, AGRM, AIRM, AJRM, ALRM, AMRM, ANRM, ARRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B4RM, B9TT, BJRM, BKRM, BLRM, BMRM, BNRM, BPRM, BRRM, BSRM, BTRM, BURM, BVRM, BWRM, BXRM, BZRM, C0RM, C1RM, C3RM, C5RM, C6RM, C7RM, C8RM, CARM, CCRM, CDRM, CERM, CGRM, CIRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CVRM, CXRM, CYRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D9RM, DARM, DBRM, DCRM, DDRM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DZRM, E1RM, E3RM, E5RM, E6RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EWRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FRRM, FSRM, FTRM, FURM, FVRM, FZRM, G3RM, G4RM, G7RM, G8RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GURM, GXRM, GYRM, GZRM, H5RM, H7RM, H8RM, H9RM, HARM, HBRM, HCRM, HDRM, HERM, HKRM, HLRM, HMRM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I6RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IHRM, IIRM, IKRM, ILRM, INRM, IORM, IQRM, IRRM, M3RM, M5RM, M6RM, M7RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, T1RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, UERM, UFRM, UGRM, UHRM, UIRM, UKRM, ULRM, UMRM, UNRM, UORM, UQRM, URRM, UTRM, UURM, UVRM, UXRM, UYRM, UZRM, V1RM, V3RM, V4RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VVRM, VWRM, VYRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W9RM, WARM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WNRM, WPRM, WQRM, WRRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XDRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XNRM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XYRM, XZRM, Y0RM, Y1RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YBRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YYRM, YZRM, Z2RM, Z4RM, Z5RM, Z6RM, Z8RM, Z9RM, ZARM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZJRM, ZKRM, ZMRM, ZNRM, ZPRM, ZR10, ZR12, ZR50, ZR51, ZR60, ZR80, ZRA2, ZRI0, ZRRM, ZSRM, ZURM, ZWRM, ZYRM | 2E | none | 2B | 3 | none | 3000 | visible |
| CMRM | 2E | none | 2B | 3 | none | 5000 | visible |
| APRM, AQRM, C2RM, C9RM, H6RM, VXRM | 2E | none | none | 1 | none | 3000 | visible |
| A3RM | 2F | 44 | 2C | 3 | none | 3000 | visible |
| MMRM, R2RM | 2F | 44 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A9RM, ADRM, AERM, AFRM, AGRM, AIRM, AJRM, ALRM, AMRM, ANRM, ARRM, AURM, AWRM, AXRM, AYRM, BJRM, BKRM, BLRM, BMRM, BPRM, BRRM, BSRM, BURM, BVRM, BXRM, BZRM, C0RM, C8RM, CERM, CGRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CXRM, CYRM, D0RM, D1RM, D2RM, D3RM, D4RM, D9RM, DARM, DBRM, DCRM, DERM, DHRM, DIRM, DJRM, DKRM, DLRM, DNRM, DPRM, DQRM, DTRM, DVRM, DWRM, DZRM, E3RM, E5RM, E6RM, E8RM, E9RM, ECRM, EFRM, EGRM, EIRM, EJRM, EMRM, ENRM, EORM, EQRM, ERRM, ESRM, ETRM, EWRM, F1RM, F5RM, F6RM, F7RM, FARM, FBRM, FDRM, FERM, FFRM, FIRM, FKRM, FPRM, FZRM, G3RM, G7RM, GCRM, GERM, GFRM, GHRM, GJRM, GTRM, GURM, GXRM, GZRM, H5RM, H8RM, H9RM, HBRM, HERM, HMRM, HPRM, HQRM, HTRM, I1RM, I2RM, I3RM, I5RM, I6RM, IARM, ILRM, IQRM, IRRM, M3RM, M5RM, M6RM, MRRM, O1RM, O2RM, O3RM, O4RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, OSRM, OXRM, OZRM, P0RM, P1RM, P2RM, P4RM, P5RM, P9RM, R5RM, R6RM, T1RM, T3RM, T5RM, T6RM, T7RM, T8RM, TARM, TBRM, TERM, U0RM, U1RM, U2RM, U5RM, UERM, UFRM, UGRM, UHRM, UIRM, UKRM, ULRM, UMRM, UNRM, UORM, UQRM, UTRM, UVRM, UXRM, UZRM, V4RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VWRM, W2RM, W3RM, W5RM, W6RM, W7RM, WDRM, WERM, WIRM, WKRM, WNRM, WPRM, WURM, WXRM, X0RM, X7RM, X8RM, X9RM, XARM, XCRM, XDRM, XFRM, XHRM, XJRM, XKRM, XMRM, XPRM, XSRM, XTRM, XURM, XVRM, XYRM, XZRM, Y5RM, Y6RM, Y8RM, YBRM, YERM, YFRM, YGRM, YHRM, YMRM, YPRM, YSRM, YTRM, YURM, YVRM, YWRM, YYRM, Z2RM, Z4RM, Z5RM, Z6RM, Z8RM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZR12, ZR50, ZR51, ZR80, ZRA2, ZRRM, ZWRM, ZYRM | 2F | none | 2C | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 2F | none | 2C | 3 | none | 5000 | visible |
| APRM, AQRM, C2RM, C9RM, H6RM, VXRM | 2F | none | none | 1 | none | 3000 | visible |
| BNRM | 2F | none | none | 2 | none | 3000 | visible |
| A0RM, A2RM, ADRM, BMRM, BNRM, BSRM, BZRM, CIRM, CORM, CSRM, DERM, DFRM, DGRM, E3RM, EIRM, ENRM, GXRM, HMRM, ILRM, M5RM, O3RM, OQRM, OSRM, OXRM, R6RM, U0RM, UERM, UHRM, UKRM, ULRM, UZRM, V7RM, VWRM, W5RM, W7RM, X0RM, YPRM, YSRM, YTRM, YURM, YVRM, YWRM, YYRM, ZRA2, ZWRM | 30 | none | 2D | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 30 | none | 2D | 3 | none | 5000 | visible |
| VXRM | 30 | none | none | 1 | none | 3000 | visible |
| TWRM, TZRM | 31 | 32 | none | 2 | none | 3000 | visible |
| A6RM, ONRM | 31 | 38 | none | 2 | none | 3000 | visible |
| AQRM, CCRM, CVRM, DSRM, H6RM, ZVRM | 31 | none | none | 1 | none | 3000 | visible |
| 6CRM, 6DRM, 6ERM, 6FRM, A0RM, A1RM, A3RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, ARRM, ATRM, AURM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B4RM, B5RM, B7RM, B8RM, B8TT, B9RM, B9TT, BCRM, BDRM, BERM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BORM, BPRM, BRRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H7RM, H8RM, H9RM, HARM, HBRM, HCRM, HDRM, HKRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IKRM, IMRM, INRM, IORM, IPRM, IQRM, IRRM, ISRM, M3RM, M6RM, M7RM, M9RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, ONRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OWRM, OXRM, OYRM, OZRM, P0RM, P1RM, P3RM, P4RM, P5RM, P6RM, P9RM, R2RM, R5RM, R6RM, S9RM, SARM, T0RM, T2RM, T3RM, T5RM, T6RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, THRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XNRM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YTRM, YURM, YVRM, YXRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZCRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZR10, ZR11, ZR12, ZR21, ZR40, ZR50, ZR51, ZR60, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZWRM, ZXRM, ZYRM | 31 | none | none | 2 | none | 3000 | visible |
| Y6RM | 31 | none | none | 2 | y6rm | 3000 | visible |
| B1RM, HCRM, I9RM, INRM, O6RM, OMRM, OORM, R6RM, VGRM, WDRM, WERM | 32 | none | none | 2 | none | 3000 | visible |
| B1RM, HCRM, O6RM, OMRM, OORM, R6RM | 33 | none | none | 2 | none | 3000 | visible |
| A3RM, MMRM | 34 | 48 | none | 2 | none | 3000 | visible |
| ONRM, THRM | 34 | 4A | none | 2 | none | 3000 | visible |
| A2RM, BZRM, FJRM, HARM, HCRM, M6RM, O2RM, O6RM, OMRM, OORM, R6RM, U1RM, U2RM, UKRM, UZRM, W7RM, WDRM, WERM, YWRM | 34 | none | none | 2 | none | 3000 | visible |
| A3RM, MMRM, ONRM, THRM | 35 | 4B | none | 2 | none | 3000 | visible |
| A2RM, BZRM, HCRM, M6RM, O2RM, O6RM, OMRM, OORM, R6RM, U1RM, U2RM, UKRM, UZRM, W7RM, YWRM | 35 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 36 | 48 | none | 2 | none | 3000 | visible |
| A2RM, HCRM, O4RM, O6RM, OMRM, OORM, R6RM | 36 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 37 | 49 | none | 2 | none | 3000 | visible |
| A2RM, HCRM, O4RM, O6RM, OMRM, OORM, R6RM | 37 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 38 | 46 | none | 2 | none | 3000 | visible |
| A2RM, HCRM, O6RM, OMRM, OORM, R6RM | 38 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 39 | 45 | none | 2 | none | 3000 | visible |
| D7RM, EURM, I0RM, I4RM, I5RM, MLRM, O0RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, ZHRM, ZIRM, ZKRM, ZLRM, ZRI0 | 39 | none | 47 | 3 | none | 3000 | visible |
| A2RM, HCRM, O6RM, OMRM, OORM, R6RM | 39 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 3A | 47 | none | 2 | none | 3000 | visible |
| A2RM, HCRM, O6RM, OMRM, OORM, R6RM | 3A | none | none | 2 | none | 3000 | visible |
| BERM, MMRM | 3C | 36 | none | 2 | none | 3000 | visible |
| ONRM, THRM | 3C | 43 | none | 2 | none | 3000 | visible |
| A3RM, R2RM | 3C | 46 | none | 2 | none | 3000 | visible |
| CZRM, FGRM, W3RM, W9RM, WARM, WDRM, WERM | 3C | none | 75 | 3 | none | 3000 | visible |
| FMRM, FNRM, GARM | 3C | none | 75 | 3 | none | 5000 | visible |
| 6ERM, 6FRM, A1RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AHRM, AIRM, ALRM, AMRM, APRM, AQRM, ARRM, AWRM, AXRM, AYRM, B1RM, B4RM, BDRM, BHRM, BIRM, BJRM, BLRM, BMRM, BNRM, BORM, BRRM, BURM, BXRM, BZRM, C0RM, C2RM, C3RM, C4RM, C5RM, C7RM, C9RM, CBRM, CCRM, CGRM, CIRM, CJRM, CKRM, CLRM, CMRM, CPRM, CQRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DFRM, DHRM, DIRM, DJRM, DPRM, DQRM, DSRM, DWRM, DZRM, E1RM, E3RM, E5RM, E7RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, EURM, EVRM, EWRM, EXRM, F0RM, F1RM, F5RM, F7RM, F9RM, FARM, FCRM, FHRM, FIRM, FJRM, FKRM, FPRM, FQRM, FRRM, FSRM, FTRM, FZRM, G2RM, G3RM, G7RM, G9RM, GBRM, GCRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GSRM, GTRM, GWRM, GXRM, GZRM, H2RM, H7RM, HARM, HBRM, HCRM, HDRM, HERM, HPRM, HQRM, HRRM, HTRM, HURM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IDRM, IERM, IGRM, IHRM, IMRM, M3RM, M5RM, M6RM, M7RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O4RM, O5RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, ORRM, OSRM, OTRM, OYRM, OZRM, P0RM, P1RM, P2RM, R5RM, T1RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TLRM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UFRM, UGRM, UHRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UYRM, V0RM, V2RM, V3RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W5RM, W6RM, W7RM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WORM, WSRM, WURM, WVRM, WXRM, WYRM, X0RM, X8RM, X9RM, XCRM, XERM, XFRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XSRM, XTRM, XYRM, XZRM, Y2RM, Y3RM, Y6RM, Y8RM, YARM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YORM, YPRM, YWRM, YZRM, Z3RM, Z4RM, Z5RM, Z6RM, ZARM, ZBRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZORM, ZR10, ZR11, ZR12, ZR50, ZR51, ZR60, ZRA0, ZRI0, ZSRM, ZTRM, ZURM, ZWRM, ZXRM, ZYRM | 3C | none | none | 2 | none | 3000 | visible |
| DJRM, DKRM, DLRM, EVRM, EWRM, FDRM, FFRM, OWRM, XFRM, XGRM, XLRM, YIRM, YMRM, YNRM, YORM, YPRM | 3D | none | none | 2 | none | 3000 | visible |
| OWRM | 3E | none | none | 2 | none | 3000 | visible |
| BERM, TZRM | 3F | 42 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AGRM, AHRM, AIRM, ALRM, ANRM, AXRM, BDRM, BGRM, BIRM, BLRM, BMRM, C2RM, C4RM, C6RM, C7RM, CARM, CBRM, CDRM, CGRM, CJRM, CKRM, CLRM, CPRM, CQRM, CTRM, CURM, CWRM, CZRM, D4RM, D6RM, DARM, DCRM, DKRM, DPRM, E1RM, E6RM, E7RM, E8RM, EDRM, EFRM, EMRM, ENRM, EORM, EVRM, EXRM, F0RM, F4RM, F9RM, FGRM, FHRM, FKRM, FPRM, FQRM, FTRM, FZRM, GARM, GFRM, GGRM, GKRM, GPRM, GXRM, GZRM, H2RM, H3RM, HBRM, HDRM, HLRM, HPRM, HRRM, HVRM, HWRM, HYRM, I0RM, I4RM, I5RM, I6RM, I8RM, ICRM, IGRM, M3RM, M5RM, MRRM, O1RM, O5RM, O7RM, O8RM, ORRM, P6RM, T0RM, T1RM, T2RM, T9RM, TERM, U2RM, U5RM, U9RM, UARM, UBRM, UERM, UGRM, UHRM, UNRM, URRM, V0RM, V2RM, V7RM, V8RM, V9RM, VCRM, VDRM, VERM, VFRM, VIRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VZRM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WHRM, WIRM, WJRM, WNRM, WSRM, WTRM, WWRM, WXRM, X0RM, X4RM, X9RM, XCRM, XLRM, XMRM, XORM, XPRM, XTRM, XVRM, XWRM, XXRM, XYRM, XZRM, Y3RM, Y6RM, YARM, YIRM, YMRM, YORM, YPRM, YSRM, YTRM, YURM, YVRM, Z3RM, Z6RM, Z9RM, ZARM, ZFRM, ZGRM, ZIRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZR11, ZR50, ZR51, ZRA0, ZRI0, ZRRM, ZSRM, ZTRM, ZVRM | 3F | none | none | 1 | none | 3000 | visible |
| BERM, TZRM | 40 | 43 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AGRM, AHRM, AIRM, ALRM, ANRM, AXRM, BDRM, BGRM, BIRM, BLRM, BMRM, C2RM, C4RM, C6RM, C7RM, CARM, CBRM, CDRM, CGRM, CJRM, CKRM, CLRM, CPRM, CQRM, CTRM, CURM, CWRM, CZRM, D4RM, D6RM, DARM, DCRM, DKRM, DPRM, E1RM, E6RM, E7RM, E8RM, EDRM, EFRM, EMRM, ENRM, EORM, EVRM, EXRM, F0RM, F4RM, F9RM, FGRM, FHRM, FKRM, FPRM, FQRM, FTRM, FZRM, GARM, GFRM, GGRM, GKRM, GPRM, GXRM, GZRM, H2RM, H3RM, HBRM, HDRM, HLRM, HPRM, HRRM, HVRM, HWRM, HYRM, I0RM, I4RM, I5RM, I6RM, I8RM, ICRM, IGRM, M3RM, M5RM, MRRM, O1RM, O5RM, O7RM, O8RM, ORRM, P6RM, T0RM, T1RM, T2RM, T9RM, TERM, U2RM, U5RM, U9RM, UARM, UBRM, UERM, UGRM, UHRM, UNRM, URRM, V0RM, V2RM, V7RM, V8RM, V9RM, VCRM, VDRM, VERM, VFRM, VIRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VZRM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WHRM, WIRM, WJRM, WNRM, WSRM, WTRM, WWRM, WXRM, X0RM, X4RM, X9RM, XCRM, XLRM, XMRM, XORM, XPRM, XTRM, XVRM, XWRM, XXRM, XYRM, XZRM, Y3RM, Y6RM, YARM, YIRM, YMRM, YORM, YPRM, YSRM, YTRM, YURM, YVRM, Z3RM, Z6RM, Z9RM, ZARM, ZFRM, ZGRM, ZIRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZR11, ZR50, ZR51, ZRA0, ZRI0, ZRRM, ZSRM, ZTRM, ZVRM | 40 | none | none | 1 | none | 3000 | visible |
| A1RM, AARM, AHRM, BDRM, BIRM, C2RM, C4RM, CARM, CJRM, CKRM, CLRM, CPRM, CURM, CZRM, D4RM, E1RM, E6RM, E7RM, EDRM, EXRM, F1RM, F7RM, FERM, FFRM, FQRM, FTRM, GARM, GGRM, GKRM, GXRM, H2RM, H3RM, H7RM, HPRM, HVRM, HWRM, HXRM, HYRM, I5RM, O5RM, ORRM, P6RM, T1RM, TERM, U5RM, U9RM, UHRM, URRM, V0RM, V2RM, VERM, VFRM, VIRM, VORM, VPRM, VRRM, VTRM, VURM, VZRM, WBRM, WCRM, WHRM, WTRM, X9RM, XMRM, XPRM, XWRM, YARM, YIRM, YORM, YPRM, YSRM, YTRM, Z3RM, ZLRM, ZR50, ZRA0, ZTRM, ZVRM | 41 | none | none | 1 | none | 3000 | visible |
| BERM | 42 | 45 | none | 1 | none | 3000 | visible |
| A1RM, AARM, AHRM, BDRM, BIRM, C2RM, C4RM, CARM, CJRM, CKRM, CLRM, CPRM, CURM, CZRM, D4RM, E1RM, E6RM, E7RM, EDRM, EXRM, F1RM, F7RM, FERM, FFRM, FQRM, FTRM, GARM, GGRM, GKRM, GXRM, H2RM, H3RM, H7RM, HPRM, HVRM, HWRM, HXRM, HYRM, I5RM, O5RM, ORRM, P6RM, T1RM, TERM, U5RM, U9RM, UHRM, URRM, V0RM, V2RM, VERM, VFRM, VIRM, VORM, VPRM, VRRM, VTRM, VURM, VZRM, WBRM, WCRM, WHRM, WTRM, X9RM, XMRM, XPRM, XWRM, YARM, YIRM, YORM, YPRM, YSRM, YTRM, Z3RM, ZLRM, ZR50, ZRA0, ZTRM, ZVRM | 42 | none | none | 1 | none | 3000 | visible |
| AARM, B4RM, B9RM, BORM, BYRM, CJRM, CKRM, CNRM, E4RM, FLRM, GBRM, GORM, HERM, ORRM, P2RM, P6RM, VRRM, VZRM, WHRM, WTRM, ZR70, ZR80 | 43 | none | none | 1 | none | 3000 | visible |
| AARM, B4RM, B9RM, BERM, BORM, BYRM, CJRM, CKRM, CNRM, E4RM, FLRM, GBRM, GORM, HERM, ORRM, P2RM, P6RM, VRRM, VZRM, WHRM, WTRM, ZR70, ZR80 | 44 | none | none | 1 | none | 3000 | visible |
| A6RM | 45 | 34 | 66 | 3 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 45 | 34 | none | 2 | none | 3000 | visible |
| ONRM, THRM | 45 | 35 | none | 2 | none | 3000 | visible |
| IDRM, IERM, IHRM, UORM, UPRM | 45 | none | 66 | 2 | none | 3000 | visible |
| U3RM | 45 | none | 66 | 3 | 54 | 3000 | visible |
| 6DRM, 6ERM, A0RM, A1RM, A8RM, A9RM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, ATRM, AURM, AWRM, AXRM, AYRM, B4RM, B5RM, B8RM, B8TT, B9RM, B9TT, BDRM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BNRM, BORM, BRRM, BURM, BVRM, BZRM, C1RM, C3RM, C4RM, C5RM, C7RM, C8RM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CKRM, CLRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D3RM, D4RM, D7RM, D9RM, DARM, DBRM, DCRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DZRM, E1RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EMRM, ENRM, EORM, EPRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F5RM, F6RM, F7RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GPRM, GSRM, GTRM, GURM, GWRM, GYRM, H3RM, H5RM, H7RM, H8RM, H9RM, HARM, HBRM, HDRM, HERM, HKRM, HLRM, HMRM, HNRM, HQRM, HRRM, HTRM, HURM, HVRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, IARM, IBRM, ICRM, IGRM, IORM, IQRM, IRRM, M3RM, M5RM, M6RM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OPRM, OQRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, R5RM, S9RM, SARM, T3RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U1RM, U2RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UIRM, UJRM, ULRM, UMRM, UNRM, UQRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, V0RM, V1RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VQRM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, W0RM, W2RM, W3RM, W5RM, W6RM, WARM, WBRM, WCRM, WDRM, WERM, WIRM, WJRM, WKRM, WNRM, WQRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XYRM, XZRM, Y1RM, Y2RM, Y3RM, Y4RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YCRM, YDRM, YERM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YWRM, YXRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, Z9RM, ZARM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZR10, ZR11, ZR12, ZR21, ZR40, ZR50, ZR51, ZR60, ZRA0, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZWRM, ZYRM | 45 | none | 66 | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 45 | none | 66 | 3 | none | 5000 | visible |
| APRM, C2RM, C9RM, T4RM | 45 | none | none | 1 | none | 3000 | visible |
| BCRM, BJRM, D2RM, O2RM, O5RM, U0RM, UKRM, UZRM, WORM | 45 | none | none | 2 | none | 3000 | visible |
| U3RM | 46 | none | 69 | 3 | 54 | 3000 | visible |
| 6DRM, 6ERM, A0RM, A9RM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BFRM, BGRM, BHRM, BIRM, BNRM, BORM, BRRM, BVRM, C3RM, C4RM, C5RM, CBRM, CERM, CGRM, CIRM, CJRM, CLRM, CORM, CSRM, CTRM, CURM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D3RM, D4RM, D7RM, D9RM, DARM, DBRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DTRM, DURM, DVRM, DWRM, DZRM, E1RM, E5RM, E6RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EMRM, ENRM, EORM, EPRM, EQRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, F0RM, F1RM, F3RM, F5RM, F6RM, F7RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FHRM, FKRM, FMRM, FNRM, FPRM, FQRM, FSRM, FTRM, FURM, FXRM, FYRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GPRM, GSRM, GTRM, GURM, GYRM, H2RM, H5RM, H7RM, H8RM, H9RM, HARM, HBRM, HDRM, HERM, HKRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HVRM, HXRM, HYRM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IBRM, ICRM, IERM, IFRM, IGRM, IHRM, IRRM, M6RM, MLRM, O0RM, O1RM, O4RM, O7RM, O8RM, OARM, OPRM, OQRM, OTRM, OYRM, OZRM, P2RM, P3RM, P4RM, P5RM, P6RM, S9RM, SARM, T3RM, T5RM, T7RM, T9RM, TBRM, TCRM, TDRM, TERM, U4RM, U5RM, U6RM, U7RM, U8RM, UARM, UBRM, UCRM, UDRM, UGRM, UIRM, UJRM, ULRM, UNRM, UORM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, V1RM, V4RM, V6RM, V7RM, V9RM, VARM, VBRM, VERM, VGRM, VHRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VSRM, VVRM, VWRM, WDRM, WERM, WIRM, WJRM, WKRM, WNRM, WURM, WVRM, WWRM, WXRM, WYRM, X1RM, X4RM, X5RM, X7RM, X9RM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XLRM, XMRM, XPRM, XSRM, XTRM, XURM, XVRM, XYRM, Y1RM, Y4RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YDRM, YERM, YGRM, YHRM, YIRM, YJRM, YORM, YPRM, YQRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z6RM, Z8RM, Z9RM, ZARM, ZDRM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZMRM, ZORM, ZR40, ZR50, ZR51, ZRA0, ZRA2, ZRI0, ZSRM, ZTRM, ZURM, ZWRM, ZYRM | 46 | none | 69 | 3 | none | 3000 | visible |
| DDRM, F8RM, WLRM | 46 | none | 69 | 3 | none | 5000 | visible |
| APRM, C2RM, C9RM | 46 | none | none | 1 | none | 3000 | visible |
| P1RM, UKRM | 46 | none | none | 2 | none | 3000 | visible |
| BHRM, BIRM, CPRM, E9RM, GTRM, HLRM, O4RM, OURM, OWRM, P5RM, V6RM, YERM | 47 | none | none | 2 | none | 3000 | visible |
| A3RM, BERM, MMRM | 48 | 4A | none | 2 | none | 3000 | visible |
| APRM, C2RM, C9RM, YGRM | 48 | none | 47 | 3 | none | 3000 | visible |
| C7RM, CVRM, DSRM, YMRM, YPRM | 48 | none | 5E | 3 | none | 3000 | visible |
| A0RM, A1RM, A9RM, AARM, ACRM, ADRM, AFRM, AGRM, AHRM, AIRM, AJRM, AMRM, ANRM, AURM, AWRM, AXRM, AYRM, B4RM, B8RM, BDRM, BGRM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CJRM, CLRM, CMRM, CORM, CPRM, CQRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D2RM, D4RM, DARM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, HARM, HBRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HVRM, HWRM, HXRM, HYRM, I1RM, I2RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IRRM, M3RM, M6RM, M7RM, MARM, MRRM, O1RM, O2RM, O3RM, O4RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, P4RM, P5RM, P6RM, R5RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UERM, UFRM, UGRM, UHRM, UKRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X7RM, X9RM, XCRM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XWRM, XYRM, XZRM, Y6RM, Y8RM, YARM, YERM, YHRM, YIRM, YJRM, YORM, YWRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, ZARM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZSRM, ZTRM, ZURM, ZWRM | 48 | none | none | 2 | none | 3000 | visible |
| B8RM | 4B | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 4C | 42 | none | 2 | none | 3000 | visible |
| BERM | 4C | 46 | none | 2 | none | 3000 | visible |
| R2RM | 4C | 49 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A9RM, AARM, ACRM, ADRM, AFRM, AGRM, AHRM, AIRM, AJRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, C2RM, C4RM, C5RM, C7RM, C9RM, CARM, CBRM, CJRM, CLRM, CMRM, CORM, CPRM, CQRM, CSRM, CTRM, CURM, CVRM, CWRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D9RM, DARM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DSRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, ETRM, EURM, EVRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, HBRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IIRM, IORM, IRRM, M3RM, M6RM, M7RM, MARM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, P6RM, R5RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U3RM, U4RM, U5RM, U9RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, V0RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X2RM, X7RM, X9RM, XBRM, XCRM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XWRM, XYRM, XZRM, Y3RM, Y6RM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, ZARM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZKRM, ZLRM, ZMRM, ZORM, ZR50, ZR51, ZRI0, ZSRM, ZTRM, ZURM, ZWRM | 4C | none | none | 2 | none | 3000 | visible |
| BERM | 4D | 49 | none | 2 | none | 3000 | visible |
| R2RM | 4D | 4A | none | 2 | none | 3000 | visible |
| R2RM | 4D | 4D | none | 2 | none | 3000 | visible |
| ACRM, ADRM, APRM, C2RM, C9RM, D7RM, DIRM, EURM, F9RM, GORM, HQRM, I0RM, I4RM, I5RM, MLRM, O0RM, O4RM, OTRM, OYRM, T9RM, U9RM, UARM, UBRM, UJRM, V7RM, VQRM, W5RM, Y3RM, YGRM, YZRM, ZHRM, ZIRM, ZKRM, ZLRM, ZRI0 | 4D | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 4E | 44 | none | 2 | none | 3000 | visible |
| BERM, R2RM | 4E | 48 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A9RM, AARM, ACRM, ADRM, AFRM, AGRM, AHRM, AIRM, AJRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, B8TT, B9TT, BDRM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, C2RM, C4RM, C5RM, C7RM, C9RM, CARM, CBRM, CGRM, CIRM, CJRM, CLRM, CMRM, CORM, CPRM, CQRM, CSRM, CTRM, CURM, CVRM, CWRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D9RM, DARM, DCRM, DERM, DFRM, DHRM, DJRM, DPRM, DSRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, HBRM, HLRM, HMRM, HNRM, HPRM, HRRM, HTRM, HVRM, HWRM, HXRM, HYRM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IIRM, IORM, IRRM, M3RM, M6RM, M7RM, MARM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, P6RM, R5RM, T5RM, T7RM, TARM, TBRM, TCRM, TDRM, TERM, U3RM, U4RM, U5RM, U9RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, V0RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X7RM, X9RM, XBRM, XCRM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XWRM, XYRM, XZRM, Y3RM, Y6RM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, ZARM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZKRM, ZLRM, ZMRM, ZORM, ZR50, ZR51, ZRI0, ZSRM, ZTRM, ZURM, ZWRM | 4E | none | none | 2 | none | 3000 | visible |
| BERM, R2RM | 4F | 4B | none | 2 | none | 3000 | visible |
| ACRM, ADRM, APRM, B8TT, B9TT, C2RM, C9RM, D7RM, EURM, F9RM, GORM, I0RM, I4RM, I5RM, MLRM, O0RM, O4RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, VQRM, W5RM, Y3RM, YGRM, YZRM, ZHRM, ZIRM, ZKRM, ZLRM, ZRI0 | 4F | none | none | 2 | none | 3000 | visible |
| A3RM, BERM, MMRM, ONRM, R2RM, THRM | 58 | 33 | none | 2 | none | 3000 | visible |
| U3RM | 58 | none | 64 | 3 | 54 | 3000 | visible |
| A0RM, A9RM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, ALRM, AMRM, ANRM, ATRM, AURM, AWRM, AXRM, AYRM, B4RM, B5RM, BDRM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BNRM, BRRM, BURM, BVRM, BZRM, C5RM, CBRM, CCRM, CDRM, CERM, CIRM, CKRM, CORM, CQRM, CSRM, CTRM, CURM, CXRM, CYRM, CZRM, D4RM, DARM, DBRM, DCRM, DERM, DFRM, DHRM, DIRM, DLRM, DNRM, DQRM, DURM, DVRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EIRM, EMRM, ENRM, ESRM, ETRM, EWRM, F0RM, F3RM, F9RM, FCRM, FDRM, FFRM, FHRM, FSRM, FXRM, FYRM, FZRM, G3RM, G5RM, G6RM, G8RM, G9RM, GCRM, GERM, GFRM, GJRM, GPRM, GSRM, GTRM, GURM, GYRM, H2RM, H3RM, H7RM, H8RM, H9RM, HARM, HBRM, HKRM, HLRM, HMRM, HNRM, HQRM, HRRM, HTRM, HVRM, I1RM, I2RM, I3RM, IARM, IBRM, IDRM, IGRM, IORM, IRRM, M3RM, M5RM, MRRM, O1RM, O3RM, O4RM, O6RM, O7RM, O9RM, OARM, OMRM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, P3RM, P4RM, P5RM, R5RM, T3RM, T5RM, T7RM, TARM, TBRM, TCRM, TERM, U1RM, U2RM, U4RM, U5RM, UCRM, UERM, UFRM, UGRM, UIRM, UMRM, UNRM, UORM, UPRM, UQRM, UVRM, UWRM, V0RM, V2RM, V4RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VHRM, VKRM, VMRM, VORM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, VZRM, W0RM, W2RM, W3RM, W6RM, WARM, WBRM, WCRM, WIRM, WJRM, WNRM, WPRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X5RM, X6RM, X7RM, X9RM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XMRM, XSRM, XURM, XVRM, XYRM, XZRM, Y3RM, Y4RM, Y8RM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YYRM, Z2RM, Z4RM, Z5RM, Z6RM, Z8RM, Z9RM, ZARM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZMRM, ZR10, ZR11, ZR12, ZR50, ZR51, ZRA0, ZSRM, ZTRM, ZURM, ZWRM | 58 | none | 64 | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 58 | none | 64 | 3 | none | 5000 | visible |
| APRM, C2RM, C9RM | 58 | none | none | 1 | none | 3000 | visible |
| BJRM, D2RM, O2RM, O5RM, UZRM | 58 | none | none | 2 | none | 3000 | visible |
| YRRM | 58 | none | none | 3 | none | 3000 | visible |
| A3RM, BERM, MMRM, ONRM, R2RM, THRM | 59 | 32 | none | 2 | none | 3000 | visible |
| U3RM | 59 | none | 65 | 3 | 55 | 3000 | visible |
| ACRM, ADRM, AORM, ATRM, B4RM, BDRM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BURM, BZRM, CDRM, CIRM, CKRM, CQRM, DCRM, DERM, DLRM, DVRM, DWRM, DZRM, ECRM, EGRM, EMRM, ENRM, ESRM, ETRM, EWRM, F3RM, F9RM, FDRM, FFRM, FHRM, FZRM, G5RM, G6RM, G8RM, G9RM, GJRM, GSRM, GTRM, GURM, H3RM, H7RM, H8RM, HKRM, HLRM, HRRM, HTRM, I3RM, IGRM, IQRM, IRRM, M3RM, M5RM, MRRM, O3RM, O6RM, O9RM, OMRM, OSRM, OXRM, OZRM, P1RM, R5RM, T7RM, TARM, TBRM, TCRM, TDRM, U0RM, U1RM, U2RM, U4RM, UCRM, UERM, UFRM, UIRM, UMRM, UPRM, UQRM, UXRM, V0RM, V2RM, V8RM, VBRM, VCRM, VVRM, VWRM, VYRM, W0RM, W2RM, W3RM, W6RM, WARM, WBRM, WCRM, WDRM, WERM, WQRM, WSRM, WTRM, X0RM, X5RM, X7RM, X9RM, XERM, XHRM, XIRM, XJRM, XKRM, XSRM, XURM, XVRM, XZRM, Y4RM, Y8RM, YERM, YIRM, YMRM, YPRM, YWRM, YXRM, YZRM, Z2RM, Z5RM, Z8RM, ZARM, ZERM, ZR11, ZR12, ZR50, ZR51, ZRA0, ZSRM, ZURM | 59 | none | 65 | 3 | none | 3000 | visible |
| DDRM, F8RM, WLRM | 59 | none | 65 | 3 | none | 5000 | visible |
| BJRM, O2RM, O5RM, UZRM | 59 | none | none | 2 | none | 3000 | visible |
| YORM, YRRM | 59 | none | none | 3 | none | 3000 | visible |
| B1RM | 5A | none | none | 2 | none | 3000 | visible |
| E3RM, E4RM, FLRM, HERM, P2RM, ZR70, ZR80 | 5B | none | none | 1 | none | 3000 | visible |
| E3RM, E4RM, FLRM, HERM, P2RM, ZR70, ZR80 | 5C | none | none | 1 | none | 3000 | visible |
| B9TT | 5D | none | 47 | 3 | none | 3000 | visible |
| APRM, BVRM, C2RM, CORM, FCRM, I2RM, I7RM, I8RM, ICRM, IERM, IFRM, IHRM, IIRM, IRRM, O5RM, T3RM, V9RM, VIRM, VNRM, WIRM, X9RM, XVRM, YGRM | 5D | none | none | 2 | none | 3000 | visible |
| ZVRM | 5E | none | none | 1 | none | 3000 | visible |
| A0RM, A1RM, AARM, AERM, AFRM, AGRM, AHRM, ALRM, AMRM, ANRM, AWRM, AXRM, BGRM, BNRM, BORM, C4RM, C5RM, CARM, CGRM, CIRM, CJRM, CLRM, CMRM, CQRM, CSRM, CTRM, CURM, CWRM, CZRM, D0RM, D1RM, D3RM, D9RM, DCRM, DERM, DFRM, DHRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, EDRM, EFRM, EMRM, EORM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GDRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GYRM, H5RM, H7RM, HPRM, HQRM, HRRM, HVRM, HWRM, HXRM, HYRM, I1RM, IBRM, IERM, IGRM, M6RM, M7RM, MARM, O8RM, P1RM, P6RM, T7RM, TCRM, TDRM, TERM, U4RM, U5RM, URRM, UTRM, UYRM, VBRM, VKRM, VLRM, VPRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VZRM, W6RM, W7RM, W9RM, WHRM, WJRM, WKRM, WNRM, WURM, WXRM, X7RM, XCRM, XERM, XFRM, XHRM, XIRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XWRM, XYRM, XZRM, Y8RM, YARM, YIRM, YORM, YYRM, YZRM, Z2RM, Z4RM, Z5RM, Z6RM, ZARM, ZERM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZSRM, ZTRM, ZURM, ZWRM | 5E | none | none | 2 | none | 3000 | visible |
| ONRM | 5F | 39 | none | 2 | none | 3000 | visible |
| BERM | 5F | 47 | none | 2 | none | 3000 | visible |
| MMRM | 5F | 49 | none | 2 | none | 3000 | visible |
| A3RM | 5F | 4C | none | 2 | none | 3000 | visible |
| R2RM | 5F | 50 | none | 2 | none | 3000 | visible |
| A3RM, A9RM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BERM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C2RM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CLRM, CMRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D2RM, D3RM, D4RM, DARM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, HARM, HBRM, HLRM, HMRM, HNRM, HPRM, HQRM, HRRM, HTRM, HVRM, HWRM, HXRM, HYRM, I1RM, IARM, IBRM, IORM, M3RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, R5RM, T5RM, T7RM, T9RM, TARM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, UKRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VDRM, VERM, VFRM, VORM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, X7RM, X9RM, XCRM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XYRM, XZRM, Y3RM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z8RM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZWRM | 5F | none | none | 2 | none | 3000 | visible |
| A3RM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BERM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CLRM, CMRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D3RM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FCRM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, HARM, HBRM, HLRM, HNRM, HPRM, HQRM, HRRM, HTRM, HVRM, HWRM, HXRM, HYRM, I1RM, IBRM, M3RM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OZRM, P0RM, P1RM, P4RM, P5RM, R5RM, T7RM, T9RM, TARM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UERM, UFRM, UGRM, UHRM, UKRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VFRM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, X7RM, X9RM, XCRM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XYRM, XZRM, Y8RM, YARM, YERM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z8RM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZWRM | 61 | none | none | 2 | none | 3000 | visible |
| ABRM, ACRM, ADRM, B9TT, C0RM, D7RM, DHRM, DIRM, H9RM, I0RM, I4RM, I5RM, M9RM, MLRM, O0RM, OTRM, S9RM, U0RM, U7RM, U8RM, U9RM, UARM, UBRM, UJRM, UNRM, UZRM, V0RM, V6RM, V7RM, VARM, VKRM, XARM, YHRM, YZRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZR21, ZRI0 | 62 | none | none | 2 | none | 3000 | visible |
| A3RM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BERM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C2RM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CLRM, CMRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D3RM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, HARM, HBRM, HLRM, HNRM, HPRM, HQRM, HRRM, HTRM, HVRM, HWRM, HXRM, HYRM, I1RM, IBRM, M3RM, MLRM, MMRM, MRRM, O1RM, O2RM, O3RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, R5RM, T7RM, T9RM, TARM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, UKRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VFRM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, X7RM, X9RM, XCRM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XYRM, XZRM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z8RM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZWRM | 63 | none | none | 2 | none | 3000 | visible |
| BRRM, YGRM | 64 | none | none | 2 | none | 3000 | hidden |
| APRM, C2RM, C9RM | 64 | none | none | 2 | none | 3000 | visible |
| BRRM, YGRM | 66 | none | none | 2 | none | 3000 | hidden |
| APRM, C2RM, C9RM | 66 | none | none | 2 | none | 3000 | visible |
| R2RM | 67 | 4C | none | 2 | none | 3000 | visible |
| B1RM | 67 | none | none | 2 | none | 3000 | visible |
| R2RM | 68 | 4E | none | 2 | none | 3000 | visible |
| B1RM | 68 | none | none | 2 | none | 3000 | visible |
| BRRM, YGRM | 69 | none | none | 2 | none | 3000 | hidden |
| APRM, C2RM, C9RM | 69 | none | none | 2 | none | 3000 | visible |
| U3RM | 6B | none | 6A | 3 | 53 | 3000 | visible |
| C7RM, DJRM, DKRM, DLRM, EVRM, EWRM, FDRM, FFRM, G7RM, M9RM, ZNRM, ZRRM | 6B | none | 6A | 3 | none | 3000 | visible |
| C6RM, C7RM, VRRM, ZNRM, ZRRM | 6C | none | none | 2 | none | 3000 | visible |
| HARM, HBRM, Y2RM | 6F | none | none | 2 | none | 3000 | visible |
| ZHRM, ZIRM | 70 | none | 95 | 3 | none | 3000 | visible |
| BZRM | 70 | none | none | 2 | none | 3000 | visible |
| C2RM, CARM, E6RM, GARM, M5RM | 71 | none | none | 1 | none | 3000 | visible |
| C2RM, E6RM, GARM, M5RM | 72 | none | none | 1 | none | 3000 | visible |
| E6RM, M5RM | 73 | none | none | 1 | none | 3000 | visible |
| E6RM, M5RM | 74 | none | none | 1 | none | 3000 | visible |
| HERM, P2RM, ZRA0 | 75 | none | none | 2 | none | 3000 | visible |
| AURM, E5RM | 76 | none | none | 2 | none | 3000 | visible |
| DTRM, F6RM | 84 | none | none | 2 | none | 3000 | hidden |
| DSRM, HLRM | 84 | none | none | 2 | none | 3000 | visible |
| ZHRM, ZIRM | 8C | none | 8D | 3 | none | 3000 | visible |
| ZHRM, ZIRM | 8E | none | 8F | 3 | none | 3000 | visible |
| AURM, ILRM | 90 | none | none | 2 | none | 3000 | visible |
| AERM, ALRM | 91 | none | 92 | 3 | none | 3000 | visible |
| ZHRM, ZIRM | 93 | none | 94 | 3 | none | 3000 | visible |
| ZORM | 96 | none | none | 1 | none | 3000 | visible |
| ZORM | 97 | none | none | 1 | none | 3000 | visible |
| BGRM | A1 | none | none | 2 | none | 3000 | visible |
| BGRM | A2 | none | none | 2 | none | 3000 | visible |
| BGRM | A3 | none | none | 2 | none | 3000 | visible |
| BGRM | A4 | none | none | 2 | none | 3000 | visible |
| BGRM | A5 | none | none | 2 | none | 3000 | visible |
| BSRM, C6RM, C7RM, E3RM, YSRM, YTRM, YURM, YVRM, ZNRM | B2 | none | B3 | 3 | none | 3000 | visible |
| DMRM, DPRM | BA | none | BB | 3 | none | 3000 | visible |
| E3RM, GXRM | BC | none | none | 2 | none | 3000 | visible |
| E3RM, GXRM | BD | none | none | 2 | none | 3000 | visible |
| EURM | D0 | none | none | 1 | none | 3000 | visible |
| EURM | D1 | none | none | 1 | none | 3000 | visible |
| F4RM, FGRM, FMRM, FNRM, GARM, GDRM, GKRM, HWRM, HXRM, HYRM | D6 | none | none | 2 | none | 3000 | visible |
| F4RM, FGRM, FMRM, FNRM, G7RM, GARM, GDRM, GKRM, HWRM, HXRM, HYRM | D8 | none | none | 2 | none | 3000 | visible |
| DNRM, HNRM, Y4RM | F0 | none | F1 | 3 | none | 3000 | visible |
| G5RM, G6RM | F0 | none | none | 2 | none | 3000 | visible |
| EZRM, Y4RM | F2 | none | F3 | 3 | none | 3000 | visible |
| FIRM, FRRM | F3 | none | F2 | 3 | none | 3000 | visible |
| G5RM, G6RM, H2RM, HNRM | F4 | none | F5 | 3 | none | 3000 | visible |
| FERM, FFRM | F6 | none | F7 | 3 | none | 3000 | visible |
| FIRM, FRRM | F7 | none | F6 | 3 | none | 3000 | visible |
| GVRM | none | 31 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 32 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 35 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 37 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 38 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 42 | none | 1 | none | 3000 | visible |
| GVRM | none | 43 | none | 1 | none | 3000 | visible |
| GVRM | none | 44 | none | 1 | none | 3000 | visible |
| GVRM | none | 45 | none | 1 | none | 3000 | visible |
| GVRM | none | 46 | none | 1 | none | 3000 | visible |
| GVRM | none | 47 | none | 1 | none | 3000 | visible |
| H6RM | none | none | 2B | 3 | none | 3000 | visible |
| H6RM | none | none | 2C | 3 | none | 3000 | visible |
| FRRM | none | none | 84 | 2 | none | 5000 | visible |
| AORM, E9RM, FGRM, FMRM, FNRM, GDRM | none | none | 84 | 3 | none | 5000 | visible |
| DXRM | none | none | BC | 3 | none | 3000 | visible |
| DXRM | none | none | BD | 3 | none | 3000 | visible |
| U3RM | none | none | none | 1 | 51 | 3000 | visible |
| U3RM | none | none | none | 1 | 52 | 3000 | visible |
| ZRS3 | none | none | none | 2 | aprm | 3000 | visible |
| ZRS3 | none | none | none | 2 | aqrm | 3000 | visible |
| ZRS0 | none | none | none | 2 | b8tt | 3000 | visible |
| ZRS0 | none | none | none | 2 | b9tt | 3000 | visible |
| ZRS1 | none | none | none | 2 | d7rm | 3000 | visible |
| ZRS1 | none | none | none | 2 | i4rm | 3000 | visible |
| ZRS1 | none | none | none | 2 | i5rm | 3000 | visible |
| ZRS2 | none | none | none | 2 | zr00 | 3000 | visible |
| ZRS2 | none | none | none | 2 | zr01 | 3000 | visible |
| ZRS1 | none | none | none | 2 | zri0 | 3000 | visible |

 </details>

### Power Cool Sleep System resource commands

<details><summary>Selected-layout command and gesture gates</summary>


| Layouts | Short | Raw old-short | Long | Status | Tag | Threshold ms | Initial visibility |
|---|---|---|---|---|---|---|---|
| BORM | 21 | none | none | 1 | none | 3000 | visible |
| APRM, AQRM, BRRM, C2RM, C9RM, DYRM, OORM, OURM, OWRM, WYRM, YFRM, YGRM | 21 | none | none | 2 | none | 3000 | visible |
| BORM | 22 | none | none | 1 | none | 3000 | visible |
| APRM, AQRM, BRRM, C2RM, C9RM, DYRM, OORM, OURM, OWRM, YFRM, YGRM | 22 | none | none | 2 | none | 3000 | visible |
| AERM, AFRM, AGRM, ALRM, AMRM, ANRM, APRM, AQRM, BRRM, C2RM, C9RM, OORM, Y1RM, YFRM, YGRM, YQRM | 23 | none | none | 2 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A6RM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM | 24 | 34 | none | 1 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 24 | 35 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ARRM, ASRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B2RM, B3RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BSRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E2RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F2RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IJRM, IKRM, ILRM, IMRM, INRM, IORM, IPRM, IQRM, IRRM, ISRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OVRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WMRM, WNRM, WORM, WPRM, WQRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XDRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR01, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 24 | none | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A6RM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM | 25 | 37 | none | 1 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 25 | 38 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ARRM, ASRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B2RM, B3RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BSRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E2RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F2RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IJRM, IKRM, ILRM, IMRM, INRM, IORM, IPRM, IQRM, IRRM, ISRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OVRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WMRM, WNRM, WORM, WPRM, WQRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XDRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR01, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 25 | none | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A6RM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM | 26 | 36 | none | 1 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 26 | 37 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, INRM, IORM, IPRM, IQRM, IRRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WPRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 26 | none | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, 6ERM, 6FRM, A3RM, A6RM, BERM, GMRM, MMRM, ONRM, R2RM, T4RM, THRM, TWRM, TZRM, V3RM | 27 | 41 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, AQRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B4RM, B5RM, B6RM, B7RM, B8RM, B8TT, B9RM, B9TT, BARM, BBRM, BCRM, BDRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BORM, BPRM, BQRM, BRRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E3RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H6RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, INRM, IORM, IPRM, IQRM, IRRM, M3RM, M4RM, M5RM, M6RM, M7RM, M9RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WPRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XORM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YXRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZBRM, ZCRM, ZDRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZQRM, ZR00, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZVRM, ZWRM, ZXRM, ZYRM, ZZRM | 27 | none | none | 1 | none | 3000 | visible |
| A3RM, MMRM, R2RM | 29 | 36 | none | 1 | none | 3000 | visible |
| 6BRM, 6CRM, 6DRM, GMRM, T4RM, THRM, TWRM, V3RM | 29 | 38 | none | 1 | none | 3000 | visible |
| A2RM, ATRM, AURM, AVRM, AWRM, AYRM, B0RM, B6RM, B7RM, BFRM, BGRM, BHRM, BKRM, BNRM, BQRM, BURM, C5RM, CBRM, CERM, CKRM, CMRM, CORM, CSRM, CYRM, D2RM, D5RM, D7RM, DFRM, DHRM, DIRM, DMRM, DURM, DVRM, E0RM, E3RM, E5RM, EFRM, ENRM, EQRM, ESRM, ETRM, F3RM, F5RM, FARM, FBRM, FIRM, FRRM, FVRM, FYRM, G2RM, G3RM, G5RM, G8RM, G9RM, GCRM, GERM, GHRM, GORM, GRRM, GSRM, GXRM, GYRM, H5RM, H8RM, I2RM, I3RM, IARM, IDRM, IIRM, IPRM, IQRM, IRRM, M4RM, M6RM, MARM, O2RM, O3RM, O9RM, OARM, OPRM, OQRM, OXRM, P0RM, P2RM, P3RM, P4RM, P5RM, R5RM, R6RM, T8RM, TARM, TCRM, TDRM, TLRM, U0RM, U1RM, U4RM, U8RM, UCRM, UFRM, UJRM, UKRM, ULRM, UPRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V4RM, V5RM, V6RM, VARM, VXRM, VYRM, W0RM, W2RM, W5RM, W6RM, W7RM, WERM, WKRM, WRRM, WSRM, WTRM, WURM, WVRM, WZRM, X4RM, X5RM, X7RM, X8RM, XERM, XHRM, XIRM, XJRM, XKRM, XNRM, XORM, XWRM, Y3RM, YHRM, YJRM, YWRM, YYRM, YZRM, Z0RM, Z1RM, Z2RM, Z4RM, Z5RM, Z7RM, Z8RM, ZBRM, ZCRM, ZDRM, ZERM, ZJRM, ZR10, ZR20, ZR30, ZR51, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZURM, ZZRM | 29 | none | none | 1 | none | 3000 | visible |
| 6BRM, A3RM, GMRM, MMRM, R2RM, T4RM, THRM, TWRM, V3RM, VYRM, W0RM, W2RM, YJRM | 2A | 39 | none | 1 | none | 3000 | visible |
| A2RM, ATRM, AURM, AVRM, AWRM, AYRM, B6RM, B7RM, BFRM, BGRM, BHRM, BNRM, BQRM, BURM, C5RM, CBRM, CERM, CKRM, CORM, CYRM, D2RM, D5RM, DFRM, DHRM, DIRM, DMRM, DURM, DVRM, E0RM, E3RM, E5RM, EFRM, ENRM, EQRM, ESRM, ETRM, F3RM, F5RM, FARM, FBRM, FIRM, FRRM, FVRM, FYRM, G2RM, G3RM, G5RM, G8RM, G9RM, GCRM, GERM, GHRM, GORM, GSRM, GXRM, GYRM, H5RM, H8RM, I2RM, I3RM, IARM, IDRM, IIRM, IPRM, IQRM, IRRM, M4RM, MARM, O2RM, O3RM, O9RM, OARM, OPRM, OQRM, OXRM, P0RM, P2RM, P3RM, P4RM, P5RM, R5RM, R6RM, T8RM, TARM, TCRM, TDRM, TLRM, U0RM, U1RM, U4RM, UCRM, UFRM, UJRM, UKRM, ULRM, UPRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V4RM, VXRM, W5RM, W6RM, W7RM, WERM, WKRM, WRRM, WSRM, WTRM, WURM, WVRM, WZRM, X4RM, X5RM, X7RM, X8RM, XERM, XHRM, XIRM, XJRM, XKRM, XNRM, XORM, XWRM, Y3RM, YHRM, YWRM, YYRM, YZRM, Z1RM, Z2RM, Z4RM, Z5RM, Z7RM, Z8RM, ZBRM, ZDRM, ZERM, ZR10, ZR20, ZR30, ZR51, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZURM, ZZRM | 2A | none | none | 1 | none | 3000 | visible |
| MMRM, R2RM | 2B | 43 | none | 2 | none | 3000 | visible |
| BRRM, YFRM, YGRM | 2B | none | none | 2 | none | 3000 | hidden |
| APRM, AQRM, C2RM, C9RM, OMRM, VXRM | 2B | none | none | 2 | none | 3000 | visible |
| MMRM, R2RM | 2C | 45 | none | 2 | none | 3000 | visible |
| BRRM, YFRM, YGRM | 2C | none | none | 2 | none | 3000 | hidden |
| APRM, AQRM, C2RM, C9RM, VXRM | 2C | none | none | 2 | none | 3000 | visible |
| VXRM | 2D | none | none | 2 | none | 3000 | visible |
| A3RM | 2E | 42 | 2B | 3 | none | 3000 | visible |
| MMRM, R2RM | 2E | 42 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A7RM, A9RM, ABRM, ADRM, AERM, AFRM, AGRM, AIRM, AJRM, ALRM, AMRM, ANRM, ARRM, ATRM, AURM, AVRM, AWRM, AXRM, AYRM, AZRM, B4RM, B9TT, BJRM, BKRM, BLRM, BMRM, BNRM, BPRM, BRRM, BSRM, BTRM, BURM, BVRM, BWRM, BXRM, BZRM, C0RM, C1RM, C3RM, C5RM, C6RM, C7RM, C8RM, CARM, CCRM, CDRM, CERM, CGRM, CIRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CVRM, CXRM, CYRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D9RM, DARM, DBRM, DCRM, DDRM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DZRM, E1RM, E3RM, E5RM, E6RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EJRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EWRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FRRM, FSRM, FTRM, FURM, FVRM, FZRM, G3RM, G4RM, G7RM, G8RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GURM, GXRM, GYRM, GZRM, H5RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I6RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IHRM, IIRM, IKRM, ILRM, INRM, IORM, IQRM, IRRM, M3RM, M5RM, M6RM, M7RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, OQRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P4RM, P5RM, P6RM, P9RM, R5RM, R6RM, T1RM, T3RM, T5RM, T6RM, T7RM, T8RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, UERM, UFRM, UGRM, UHRM, UIRM, UKRM, ULRM, UMRM, UNRM, UORM, UQRM, URRM, UTRM, UURM, UVRM, UXRM, UYRM, UZRM, V1RM, V3RM, V4RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VVRM, VWRM, VYRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W9RM, WARM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WNRM, WPRM, WQRM, WRRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XDRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XNRM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XYRM, XZRM, Y0RM, Y1RM, Y5RM, Y6RM, Y7RM, Y8RM, Y9RM, YBRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YSRM, YTRM, YURM, YVRM, YWRM, YYRM, YZRM, Z2RM, Z4RM, Z5RM, Z6RM, Z8RM, Z9RM, ZARM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZJRM, ZKRM, ZMRM, ZNRM, ZPRM, ZR10, ZR12, ZR50, ZR51, ZR60, ZR80, ZRA2, ZRI0, ZRRM, ZSRM, ZURM, ZWRM, ZYRM | 2E | none | 2B | 3 | none | 3000 | visible |
| CMRM | 2E | none | 2B | 3 | none | 5000 | visible |
| APRM, AQRM, C2RM, C9RM, H6RM, VXRM | 2E | none | none | 1 | none | 3000 | visible |
| A3RM | 2F | 44 | 2C | 3 | none | 3000 | visible |
| MMRM, R2RM | 2F | 44 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A9RM, ADRM, AERM, AFRM, AGRM, AIRM, AJRM, ALRM, AMRM, ANRM, ARRM, AURM, AWRM, AXRM, AYRM, BJRM, BKRM, BLRM, BMRM, BPRM, BRRM, BSRM, BURM, BVRM, BXRM, BZRM, C0RM, C8RM, CERM, CGRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CXRM, CYRM, D0RM, D1RM, D2RM, D3RM, D4RM, D9RM, DARM, DBRM, DCRM, DERM, DHRM, DIRM, DJRM, DKRM, DLRM, DNRM, DPRM, DQRM, DTRM, DVRM, DWRM, DZRM, E3RM, E5RM, E6RM, E8RM, E9RM, ECRM, EFRM, EGRM, EIRM, EJRM, EMRM, ENRM, EORM, EQRM, ERRM, ESRM, ETRM, EWRM, F1RM, F5RM, F6RM, F7RM, FARM, FBRM, FDRM, FERM, FFRM, FIRM, FKRM, FPRM, FZRM, G3RM, G7RM, GCRM, GERM, GFRM, GHRM, GJRM, GTRM, GURM, GXRM, GZRM, H5RM, H8RM, H9RM, I1RM, I2RM, I3RM, I5RM, I6RM, IARM, ILRM, IQRM, IRRM, M3RM, M5RM, M6RM, MRRM, O1RM, O2RM, O3RM, O4RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, OSRM, OXRM, OZRM, P0RM, P1RM, P2RM, P4RM, P5RM, P9RM, R5RM, R6RM, T1RM, T3RM, T5RM, T6RM, T7RM, T8RM, TARM, TBRM, TERM, U0RM, U1RM, U2RM, U5RM, UERM, UFRM, UGRM, UHRM, UIRM, UKRM, ULRM, UMRM, UNRM, UORM, UQRM, UTRM, UVRM, UXRM, UZRM, V4RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VWRM, W2RM, W3RM, W5RM, W6RM, W7RM, WDRM, WERM, WIRM, WKRM, WNRM, WPRM, WURM, WXRM, X0RM, X7RM, X8RM, X9RM, XARM, XCRM, XDRM, XFRM, XHRM, XJRM, XKRM, XMRM, XPRM, XSRM, XTRM, XURM, XVRM, XYRM, XZRM, Y5RM, Y6RM, Y8RM, YBRM, YERM, YFRM, YGRM, YHRM, YMRM, YPRM, YSRM, YTRM, YURM, YVRM, YWRM, YYRM, Z2RM, Z4RM, Z5RM, Z6RM, Z8RM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZR12, ZR50, ZR51, ZR80, ZRA2, ZRRM, ZWRM, ZYRM | 2F | none | 2C | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 2F | none | 2C | 3 | none | 5000 | visible |
| APRM, AQRM, C2RM, C9RM, H6RM, VXRM | 2F | none | none | 1 | none | 3000 | visible |
| BNRM | 2F | none | none | 2 | none | 3000 | visible |
| A0RM, A2RM, ADRM, BMRM, BNRM, BSRM, BZRM, CIRM, CORM, CSRM, DERM, DFRM, DGRM, E3RM, EIRM, ENRM, GXRM, ILRM, M5RM, O3RM, OQRM, OSRM, OXRM, R6RM, U0RM, UERM, UHRM, UKRM, ULRM, UZRM, V7RM, VWRM, W5RM, W7RM, X0RM, YPRM, YSRM, YTRM, YURM, YVRM, YWRM, YYRM, ZRA2, ZWRM | 30 | none | 2D | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 30 | none | 2D | 3 | none | 5000 | visible |
| VXRM | 30 | none | none | 1 | none | 3000 | visible |
| TWRM, TZRM | 31 | 32 | none | 2 | none | 3000 | visible |
| A6RM, ONRM | 31 | 38 | none | 2 | none | 3000 | visible |
| AQRM, CCRM, CVRM, DSRM, H6RM, ZVRM | 31 | none | none | 1 | none | 3000 | visible |
| 6CRM, 6DRM, 6ERM, 6FRM, A0RM, A1RM, A3RM, A7RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, APRM, ARRM, ATRM, AURM, AWRM, AXRM, AYRM, AZRM, B0RM, B1RM, B4RM, B5RM, B7RM, B8RM, B8TT, B9RM, B9TT, BCRM, BDRM, BERM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BORM, BPRM, BRRM, BTRM, BURM, BVRM, BWRM, BXRM, BYRM, BZRM, C0RM, C1RM, C2RM, C3RM, C4RM, C5RM, C6RM, C7RM, C8RM, C9RM, CARM, CBRM, CDRM, CERM, CGRM, CHRM, CIRM, CJRM, CKRM, CLRM, CMRM, CNRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DDRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DTRM, DURM, DVRM, DWRM, DXRM, DZRM, E1RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EKRM, EMRM, ENRM, EORM, EPRM, EQRM, ERRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F4RM, F5RM, F6RM, F7RM, F8RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FLRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FVRM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GARM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GPRM, GRRM, GSRM, GTRM, GURM, GWRM, GXRM, GYRM, GZRM, H2RM, H3RM, H5RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IKRM, IMRM, INRM, IORM, IPRM, IQRM, IRRM, ISRM, M3RM, M6RM, M7RM, M9RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, ONRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OWRM, OXRM, OYRM, OZRM, P0RM, P1RM, P3RM, P4RM, P5RM, P6RM, P9RM, R2RM, R5RM, R6RM, S9RM, SARM, T0RM, T2RM, T3RM, T5RM, T6RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, THRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XARM, XBRM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XNRM, XPRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XWRM, XXRM, XYRM, XZRM, Y0RM, Y1RM, Y2RM, Y3RM, Y4RM, Y5RM, Y7RM, Y8RM, Y9RM, YARM, YBRM, YCRM, YDRM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YRRM, YTRM, YURM, YVRM, YXRM, YZRM, Z0RM, Z1RM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z7RM, Z8RM, Z9RM, ZARM, ZCRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZPRM, ZR10, ZR11, ZR12, ZR21, ZR40, ZR50, ZR51, ZR60, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZWRM, ZXRM, ZYRM | 31 | none | none | 2 | none | 3000 | visible |
| Y6RM | 31 | none | none | 2 | y6rm | 3000 | visible |
| B1RM, I9RM, INRM, O6RM, OMRM, OORM, R6RM, VGRM, WDRM, WERM | 32 | none | none | 2 | none | 3000 | visible |
| B1RM, O6RM, OMRM, OORM, R6RM | 33 | none | none | 2 | none | 3000 | visible |
| A3RM, MMRM | 34 | 48 | none | 2 | none | 3000 | visible |
| ONRM, THRM | 34 | 4A | none | 2 | none | 3000 | visible |
| A2RM, BZRM, FJRM, M6RM, O2RM, O6RM, OMRM, OORM, R6RM, U1RM, U2RM, UKRM, UZRM, W7RM, WDRM, WERM, YWRM | 34 | none | none | 2 | none | 3000 | visible |
| A3RM, MMRM, ONRM, THRM | 35 | 4B | none | 2 | none | 3000 | visible |
| A2RM, BZRM, M6RM, O2RM, O6RM, OMRM, OORM, R6RM, U1RM, U2RM, UKRM, UZRM, W7RM, YWRM | 35 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 36 | 48 | none | 2 | none | 3000 | visible |
| A2RM, O4RM, O6RM, OMRM, OORM, R6RM | 36 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 37 | 49 | none | 2 | none | 3000 | visible |
| A2RM, O4RM, O6RM, OMRM, OORM, R6RM | 37 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 38 | 46 | none | 2 | none | 3000 | visible |
| A2RM, O6RM, OMRM, OORM, R6RM | 38 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 39 | 45 | none | 2 | none | 3000 | visible |
| D7RM, EURM, I0RM, I4RM, I5RM, MLRM, O0RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, ZHRM, ZIRM, ZKRM, ZLRM, ZRI0 | 39 | none | 47 | 3 | none | 3000 | visible |
| A2RM, O6RM, OMRM, OORM, R6RM | 39 | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 3A | 47 | none | 2 | none | 3000 | visible |
| A2RM, O6RM, OMRM, OORM, R6RM | 3A | none | none | 2 | none | 3000 | visible |
| BERM, MMRM | 3C | 36 | none | 2 | none | 3000 | visible |
| ONRM, THRM | 3C | 43 | none | 2 | none | 3000 | visible |
| A3RM, R2RM | 3C | 46 | none | 2 | none | 3000 | visible |
| CZRM, FGRM, W3RM, W9RM, WARM, WDRM, WERM | 3C | none | 75 | 3 | none | 3000 | visible |
| FMRM, FNRM, GARM | 3C | none | 75 | 3 | none | 5000 | visible |
| 6ERM, 6FRM, A1RM, A8RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AFRM, AHRM, AIRM, ALRM, AMRM, APRM, AQRM, ARRM, AWRM, AXRM, AYRM, B1RM, B4RM, BDRM, BHRM, BIRM, BJRM, BLRM, BMRM, BNRM, BORM, BRRM, BURM, BXRM, BZRM, C0RM, C2RM, C3RM, C4RM, C5RM, C7RM, C9RM, CBRM, CCRM, CGRM, CIRM, CJRM, CKRM, CLRM, CMRM, CPRM, CQRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D8RM, D9RM, DARM, DBRM, DCRM, DFRM, DHRM, DIRM, DJRM, DPRM, DQRM, DSRM, DWRM, DZRM, E1RM, E3RM, E5RM, E7RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, EURM, EVRM, EWRM, EXRM, F0RM, F1RM, F5RM, F7RM, F9RM, FARM, FCRM, FHRM, FIRM, FJRM, FKRM, FPRM, FQRM, FRRM, FSRM, FTRM, FZRM, G2RM, G3RM, G7RM, G9RM, GBRM, GCRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GSRM, GTRM, GWRM, GXRM, GZRM, H2RM, H7RM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IDRM, IERM, IGRM, IHRM, IMRM, M3RM, M5RM, M6RM, M7RM, MARM, MLRM, MRRM, O0RM, O1RM, O2RM, O4RM, O5RM, O7RM, O8RM, O9RM, OARM, OMRM, OORM, OPRM, ORRM, OSRM, OTRM, OYRM, OZRM, P0RM, P1RM, P2RM, R5RM, T1RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TLRM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UFRM, UGRM, UHRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UYRM, V0RM, V2RM, V3RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W5RM, W6RM, W7RM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WORM, WSRM, WURM, WVRM, WXRM, WYRM, X0RM, X8RM, X9RM, XCRM, XERM, XFRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XSRM, XTRM, XYRM, XZRM, Y2RM, Y3RM, Y6RM, Y8RM, YARM, YERM, YFRM, YGRM, YHRM, YIRM, YJRM, YORM, YPRM, YWRM, YZRM, Z3RM, Z4RM, Z5RM, Z6RM, ZARM, ZBRM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZMRM, ZORM, ZR10, ZR11, ZR12, ZR50, ZR51, ZR60, ZRA0, ZRI0, ZSRM, ZTRM, ZURM, ZWRM, ZXRM, ZYRM | 3C | none | none | 2 | none | 3000 | visible |
| DJRM, DKRM, DLRM, EVRM, EWRM, FDRM, FFRM, OWRM, XFRM, XGRM, XLRM, YIRM, YMRM, YNRM, YORM, YPRM | 3D | none | none | 2 | none | 3000 | visible |
| OWRM | 3E | none | none | 2 | none | 3000 | visible |
| BERM, TZRM | 3F | 42 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AGRM, AHRM, AIRM, ALRM, ANRM, AXRM, BDRM, BGRM, BIRM, BLRM, BMRM, C2RM, C4RM, C6RM, C7RM, CARM, CBRM, CDRM, CGRM, CJRM, CKRM, CLRM, CPRM, CQRM, CTRM, CURM, CWRM, CZRM, D4RM, D6RM, DARM, DCRM, DKRM, DPRM, E1RM, E6RM, E7RM, E8RM, EDRM, EFRM, EMRM, ENRM, EORM, EVRM, EXRM, F0RM, F4RM, F9RM, FGRM, FHRM, FKRM, FPRM, FQRM, FTRM, FZRM, GARM, GFRM, GGRM, GKRM, GPRM, GXRM, GZRM, H2RM, H3RM, I0RM, I4RM, I5RM, I6RM, I8RM, ICRM, IGRM, M3RM, M5RM, MRRM, O1RM, O5RM, O7RM, O8RM, ORRM, P6RM, T0RM, T1RM, T2RM, T9RM, TERM, U2RM, U5RM, U9RM, UARM, UBRM, UERM, UGRM, UHRM, UNRM, URRM, V0RM, V2RM, V7RM, V8RM, V9RM, VCRM, VDRM, VERM, VFRM, VIRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VZRM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WHRM, WIRM, WJRM, WNRM, WSRM, WTRM, WWRM, WXRM, X0RM, X4RM, X9RM, XCRM, XLRM, XMRM, XORM, XPRM, XTRM, XVRM, XWRM, XXRM, XYRM, XZRM, Y3RM, Y6RM, YARM, YIRM, YMRM, YORM, YPRM, YSRM, YTRM, YURM, YVRM, Z3RM, Z6RM, Z9RM, ZARM, ZFRM, ZGRM, ZIRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZR11, ZR50, ZR51, ZRA0, ZRI0, ZRRM, ZSRM, ZTRM, ZVRM | 3F | none | none | 1 | none | 3000 | visible |
| BERM, TZRM | 40 | 43 | none | 1 | none | 3000 | visible |
| A0RM, A1RM, A9RM, AARM, ABRM, ACRM, ADRM, AERM, AGRM, AHRM, AIRM, ALRM, ANRM, AXRM, BDRM, BGRM, BIRM, BLRM, BMRM, C2RM, C4RM, C6RM, C7RM, CARM, CBRM, CDRM, CGRM, CJRM, CKRM, CLRM, CPRM, CQRM, CTRM, CURM, CWRM, CZRM, D4RM, D6RM, DARM, DCRM, DKRM, DPRM, E1RM, E6RM, E7RM, E8RM, EDRM, EFRM, EMRM, ENRM, EORM, EVRM, EXRM, F0RM, F4RM, F9RM, FGRM, FHRM, FKRM, FPRM, FQRM, FTRM, FZRM, GARM, GFRM, GGRM, GKRM, GPRM, GXRM, GZRM, H2RM, H3RM, I0RM, I4RM, I5RM, I6RM, I8RM, ICRM, IGRM, M3RM, M5RM, MRRM, O1RM, O5RM, O7RM, O8RM, ORRM, P6RM, T0RM, T1RM, T2RM, T9RM, TERM, U2RM, U5RM, U9RM, UARM, UBRM, UERM, UGRM, UHRM, UNRM, URRM, V0RM, V2RM, V7RM, V8RM, V9RM, VCRM, VDRM, VERM, VFRM, VIRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VZRM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WHRM, WIRM, WJRM, WNRM, WSRM, WTRM, WWRM, WXRM, X0RM, X4RM, X9RM, XCRM, XLRM, XMRM, XORM, XPRM, XTRM, XVRM, XWRM, XXRM, XYRM, XZRM, Y3RM, Y6RM, YARM, YIRM, YMRM, YORM, YPRM, YSRM, YTRM, YURM, YVRM, Z3RM, Z6RM, Z9RM, ZARM, ZFRM, ZGRM, ZIRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZR11, ZR50, ZR51, ZRA0, ZRI0, ZRRM, ZSRM, ZTRM, ZVRM | 40 | none | none | 1 | none | 3000 | visible |
| A1RM, AARM, AHRM, BDRM, BIRM, C2RM, C4RM, CARM, CJRM, CKRM, CLRM, CPRM, CURM, CZRM, D4RM, E1RM, E6RM, E7RM, EDRM, EXRM, F1RM, F7RM, FERM, FFRM, FQRM, FTRM, GARM, GGRM, GKRM, GXRM, H2RM, H3RM, H7RM, I5RM, O5RM, ORRM, P6RM, T1RM, TERM, U5RM, U9RM, UHRM, URRM, V0RM, V2RM, VERM, VFRM, VIRM, VORM, VPRM, VRRM, VTRM, VURM, VZRM, WBRM, WCRM, WHRM, WTRM, X9RM, XMRM, XPRM, XWRM, YARM, YIRM, YORM, YPRM, YSRM, YTRM, Z3RM, ZLRM, ZR50, ZRA0, ZTRM, ZVRM | 41 | none | none | 1 | none | 3000 | visible |
| BERM | 42 | 45 | none | 1 | none | 3000 | visible |
| A1RM, AARM, AHRM, BDRM, BIRM, C2RM, C4RM, CARM, CJRM, CKRM, CLRM, CPRM, CURM, CZRM, D4RM, E1RM, E6RM, E7RM, EDRM, EXRM, F1RM, F7RM, FERM, FFRM, FQRM, FTRM, GARM, GGRM, GKRM, GXRM, H2RM, H3RM, H7RM, I5RM, O5RM, ORRM, P6RM, T1RM, TERM, U5RM, U9RM, UHRM, URRM, V0RM, V2RM, VERM, VFRM, VIRM, VORM, VPRM, VRRM, VTRM, VURM, VZRM, WBRM, WCRM, WHRM, WTRM, X9RM, XMRM, XPRM, XWRM, YARM, YIRM, YORM, YPRM, YSRM, YTRM, Z3RM, ZLRM, ZR50, ZRA0, ZTRM, ZVRM | 42 | none | none | 1 | none | 3000 | visible |
| AARM, B4RM, B9RM, BORM, BYRM, CJRM, CKRM, CNRM, E4RM, FLRM, GBRM, GORM, ORRM, P2RM, P6RM, VRRM, VZRM, WHRM, WTRM, ZR70, ZR80 | 43 | none | none | 1 | none | 3000 | visible |
| AARM, B4RM, B9RM, BERM, BORM, BYRM, CJRM, CKRM, CNRM, E4RM, FLRM, GBRM, GORM, ORRM, P2RM, P6RM, VRRM, VZRM, WHRM, WTRM, ZR70, ZR80 | 44 | none | none | 1 | none | 3000 | visible |
| A6RM | 45 | 34 | 66 | 3 | none | 3000 | visible |
| A3RM, BERM, MMRM, R2RM | 45 | 34 | none | 2 | none | 3000 | visible |
| ONRM, THRM | 45 | 35 | none | 2 | none | 3000 | visible |
| IDRM, IERM, IHRM, UORM, UPRM | 45 | none | 66 | 2 | none | 3000 | visible |
| U3RM | 45 | none | 66 | 3 | 54 | 3000 | visible |
| 6DRM, 6ERM, A0RM, A1RM, A8RM, A9RM, ABRM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AORM, ATRM, AURM, AWRM, AXRM, AYRM, B4RM, B5RM, B8RM, B8TT, B9RM, B9TT, BDRM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BNRM, BORM, BRRM, BURM, BVRM, BZRM, C1RM, C3RM, C4RM, C5RM, C7RM, C8RM, CBRM, CCRM, CDRM, CERM, CGRM, CHRM, CIRM, CKRM, CLRM, CORM, CPRM, CQRM, CRRM, CSRM, CTRM, CURM, CVRM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D3RM, D4RM, D7RM, D9RM, DARM, DBRM, DCRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DRRM, DSRM, DTRM, DURM, DVRM, DWRM, DZRM, E1RM, E4RM, E5RM, E6RM, E7RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EMRM, ENRM, EORM, EPRM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, EZRM, F0RM, F1RM, F3RM, F5RM, F6RM, F7RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FGRM, FHRM, FIRM, FJRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FSRM, FTRM, FURM, FXRM, FYRM, FZRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GPRM, GSRM, GTRM, GURM, GWRM, GYRM, H3RM, H5RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, IARM, IBRM, ICRM, IGRM, IORM, IQRM, IRRM, M3RM, M5RM, M6RM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O6RM, O7RM, O8RM, O9RM, OARM, OMRM, OPRM, OQRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P3RM, P4RM, P5RM, R5RM, S9RM, SARM, T3RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U1RM, U2RM, U4RM, U5RM, U6RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UDRM, UERM, UFRM, UGRM, UIRM, UJRM, ULRM, UMRM, UNRM, UQRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, V0RM, V1RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VQRM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, W0RM, W2RM, W3RM, W5RM, W6RM, WARM, WBRM, WCRM, WDRM, WERM, WIRM, WJRM, WKRM, WNRM, WQRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X1RM, X2RM, X4RM, X5RM, X6RM, X7RM, X8RM, X9RM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XQRM, XRRM, XSRM, XTRM, XURM, XVRM, XYRM, XZRM, Y1RM, Y2RM, Y3RM, Y4RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YCRM, YDRM, YERM, YGRM, YHRM, YIRM, YJRM, YKRM, YMRM, YNRM, YORM, YPRM, YQRM, YWRM, YXRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, Z9RM, ZARM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZJRM, ZKRM, ZLRM, ZMRM, ZNRM, ZORM, ZR10, ZR11, ZR12, ZR21, ZR40, ZR50, ZR51, ZR60, ZRA0, ZRA2, ZRI0, ZRRM, ZSRM, ZTRM, ZURM, ZWRM, ZYRM | 45 | none | 66 | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 45 | none | 66 | 3 | none | 5000 | visible |
| APRM, C2RM, C9RM, T4RM | 45 | none | none | 1 | none | 3000 | visible |
| BCRM, BJRM, D2RM, O2RM, O5RM, U0RM, UKRM, UZRM, WORM | 45 | none | none | 2 | none | 3000 | visible |
| U3RM | 46 | none | 69 | 3 | 54 | 3000 | visible |
| 6DRM, 6ERM, A0RM, A9RM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, AIRM, AJRM, AKRM, ALRM, AMRM, ANRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BFRM, BGRM, BHRM, BIRM, BNRM, BORM, BRRM, BVRM, C3RM, C4RM, C5RM, CBRM, CERM, CGRM, CIRM, CJRM, CLRM, CORM, CSRM, CTRM, CURM, CWRM, CXRM, CYRM, CZRM, D0RM, D1RM, D3RM, D4RM, D7RM, D9RM, DARM, DBRM, DERM, DFRM, DGRM, DHRM, DIRM, DJRM, DKRM, DLRM, DMRM, DNRM, DPRM, DQRM, DTRM, DURM, DVRM, DWRM, DZRM, E1RM, E5RM, E6RM, E8RM, E9RM, ECRM, EDRM, EFRM, EGRM, EIRM, EMRM, ENRM, EORM, EPRM, EQRM, ETRM, EURM, EVRM, EWRM, EXRM, EYRM, F0RM, F1RM, F3RM, F5RM, F6RM, F7RM, F9RM, FARM, FBRM, FCRM, FDRM, FERM, FFRM, FHRM, FKRM, FMRM, FNRM, FPRM, FQRM, FSRM, FTRM, FURM, FXRM, FYRM, G2RM, G3RM, G4RM, G5RM, G6RM, G7RM, G8RM, G9RM, GBRM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GPRM, GSRM, GTRM, GURM, GYRM, H2RM, H5RM, H7RM, H8RM, H9RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IBRM, ICRM, IERM, IFRM, IGRM, IHRM, IRRM, M6RM, MLRM, O0RM, O1RM, O4RM, O7RM, O8RM, OARM, OPRM, OQRM, OTRM, OYRM, OZRM, P2RM, P3RM, P4RM, P5RM, P6RM, S9RM, SARM, T3RM, T5RM, T7RM, T9RM, TBRM, TCRM, TDRM, TERM, U4RM, U5RM, U6RM, U7RM, U8RM, UARM, UBRM, UCRM, UDRM, UGRM, UIRM, UJRM, ULRM, UNRM, UORM, URRM, UTRM, UURM, UVRM, UWRM, UXRM, UYRM, V1RM, V4RM, V6RM, V7RM, V9RM, VARM, VBRM, VERM, VGRM, VHRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VSRM, VVRM, VWRM, WDRM, WERM, WIRM, WJRM, WKRM, WNRM, WURM, WVRM, WWRM, WXRM, WYRM, X1RM, X4RM, X5RM, X7RM, X9RM, XCRM, XERM, XFRM, XGRM, XHRM, XIRM, XLRM, XMRM, XPRM, XSRM, XTRM, XURM, XVRM, XYRM, Y1RM, Y4RM, Y6RM, Y7RM, Y8RM, Y9RM, YARM, YDRM, YERM, YGRM, YHRM, YIRM, YJRM, YORM, YPRM, YQRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z6RM, Z8RM, Z9RM, ZARM, ZDRM, ZFRM, ZGRM, ZHRM, ZIRM, ZJRM, ZKRM, ZMRM, ZORM, ZR40, ZR50, ZR51, ZRA0, ZRA2, ZRI0, ZSRM, ZTRM, ZURM, ZWRM, ZYRM | 46 | none | 69 | 3 | none | 3000 | visible |
| DDRM, F8RM, WLRM | 46 | none | 69 | 3 | none | 5000 | visible |
| APRM, C2RM, C9RM | 46 | none | none | 1 | none | 3000 | visible |
| P1RM, UKRM | 46 | none | none | 2 | none | 3000 | visible |
| BHRM, BIRM, CPRM, E9RM, GTRM, O4RM, OURM, OWRM, P5RM, V6RM, YERM | 47 | none | none | 2 | none | 3000 | visible |
| A3RM, BERM, MMRM | 48 | 4A | none | 2 | none | 3000 | visible |
| APRM, C2RM, C9RM, YGRM | 48 | none | 47 | 3 | none | 3000 | visible |
| C7RM, CVRM, DSRM, YMRM, YPRM | 48 | none | 5E | 3 | none | 3000 | visible |
| A0RM, A1RM, A9RM, AARM, ACRM, ADRM, AFRM, AGRM, AHRM, AIRM, AJRM, AMRM, ANRM, AURM, AWRM, AXRM, AYRM, B4RM, B8RM, BDRM, BGRM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CJRM, CLRM, CMRM, CORM, CPRM, CQRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D2RM, D4RM, DARM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, I1RM, I2RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IRRM, M3RM, M6RM, M7RM, MARM, MRRM, O1RM, O2RM, O3RM, O4RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, P4RM, P5RM, P6RM, R5RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UERM, UFRM, UGRM, UHRM, UKRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X7RM, X9RM, XCRM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XWRM, XYRM, XZRM, Y6RM, Y8RM, YARM, YERM, YHRM, YIRM, YJRM, YORM, YWRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, ZARM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZSRM, ZTRM, ZURM, ZWRM | 48 | none | none | 2 | none | 3000 | visible |
| B8RM | 4B | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 4C | 42 | none | 2 | none | 3000 | visible |
| BERM | 4C | 46 | none | 2 | none | 3000 | visible |
| R2RM | 4C | 49 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A9RM, AARM, ACRM, ADRM, AFRM, AGRM, AHRM, AIRM, AJRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, C2RM, C4RM, C5RM, C7RM, C9RM, CARM, CBRM, CJRM, CLRM, CMRM, CORM, CPRM, CQRM, CSRM, CTRM, CURM, CVRM, CWRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D9RM, DARM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DSRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, ETRM, EURM, EVRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IIRM, IORM, IRRM, M3RM, M6RM, M7RM, MARM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, P6RM, R5RM, T5RM, T7RM, T9RM, TARM, TBRM, TCRM, TDRM, TERM, U3RM, U4RM, U5RM, U9RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, V0RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X2RM, X7RM, X9RM, XBRM, XCRM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XWRM, XYRM, XZRM, Y3RM, Y6RM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, ZARM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZKRM, ZLRM, ZMRM, ZORM, ZR50, ZR51, ZRI0, ZSRM, ZTRM, ZURM, ZWRM | 4C | none | none | 2 | none | 3000 | visible |
| BERM | 4D | 49 | none | 2 | none | 3000 | visible |
| R2RM | 4D | 4A | none | 2 | none | 3000 | visible |
| R2RM | 4D | 4D | none | 2 | none | 3000 | visible |
| ACRM, ADRM, APRM, C2RM, C9RM, D7RM, DIRM, EURM, F9RM, GORM, I0RM, I4RM, I5RM, MLRM, O0RM, O4RM, OTRM, OYRM, T9RM, U9RM, UARM, UBRM, UJRM, V7RM, VQRM, W5RM, Y3RM, YGRM, YZRM, ZHRM, ZIRM, ZKRM, ZLRM, ZRI0 | 4D | none | none | 2 | none | 3000 | visible |
| ONRM, THRM | 4E | 44 | none | 2 | none | 3000 | visible |
| BERM, R2RM | 4E | 48 | none | 2 | none | 3000 | visible |
| A0RM, A1RM, A2RM, A9RM, AARM, ACRM, ADRM, AFRM, AGRM, AHRM, AIRM, AJRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, B8TT, B9TT, BDRM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, C2RM, C4RM, C5RM, C7RM, C9RM, CARM, CBRM, CGRM, CIRM, CJRM, CLRM, CMRM, CORM, CPRM, CQRM, CSRM, CTRM, CURM, CVRM, CWRM, CYRM, CZRM, D0RM, D1RM, D2RM, D3RM, D4RM, D7RM, D9RM, DARM, DCRM, DERM, DFRM, DHRM, DJRM, DPRM, DSRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EMRM, EORM, ESRM, ETRM, EURM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IIRM, IORM, IRRM, M3RM, M6RM, M7RM, MARM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, P6RM, R5RM, T5RM, T7RM, TARM, TBRM, TCRM, TDRM, TERM, U3RM, U4RM, U5RM, U9RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, V0RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X7RM, X9RM, XBRM, XCRM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XWRM, XYRM, XZRM, Y3RM, Y6RM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YYRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z6RM, Z8RM, ZARM, ZERM, ZFRM, ZGRM, ZHRM, ZIRM, ZKRM, ZLRM, ZMRM, ZORM, ZR50, ZR51, ZRI0, ZSRM, ZTRM, ZURM, ZWRM | 4E | none | none | 2 | none | 3000 | visible |
| BERM, R2RM | 4F | 4B | none | 2 | none | 3000 | visible |
| ACRM, ADRM, APRM, B8TT, B9TT, C2RM, C9RM, D7RM, EURM, F9RM, GORM, I0RM, I4RM, I5RM, MLRM, O0RM, O4RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, VQRM, W5RM, Y3RM, YGRM, YZRM, ZHRM, ZIRM, ZKRM, ZLRM, ZRI0 | 4F | none | none | 2 | none | 3000 | visible |
| A3RM, BERM, MMRM, ONRM, R2RM, THRM | 58 | 33 | none | 2 | none | 3000 | visible |
| U3RM | 58 | none | 64 | 3 | 54 | 3000 | visible |
| A0RM, A9RM, ACRM, ADRM, AERM, AFRM, AGRM, AHRM, ALRM, AMRM, ANRM, ATRM, AURM, AWRM, AXRM, AYRM, B4RM, B5RM, BDRM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BNRM, BRRM, BURM, BVRM, BZRM, C5RM, CBRM, CCRM, CDRM, CERM, CIRM, CKRM, CORM, CQRM, CSRM, CTRM, CURM, CXRM, CYRM, CZRM, D4RM, DARM, DBRM, DCRM, DERM, DFRM, DHRM, DIRM, DLRM, DNRM, DQRM, DURM, DVRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EFRM, EIRM, EMRM, ENRM, ESRM, ETRM, EWRM, F0RM, F3RM, F9RM, FCRM, FDRM, FFRM, FHRM, FSRM, FXRM, FYRM, FZRM, G3RM, G5RM, G6RM, G8RM, G9RM, GCRM, GERM, GFRM, GJRM, GPRM, GSRM, GTRM, GURM, GYRM, H2RM, H3RM, H7RM, H8RM, H9RM, I1RM, I2RM, I3RM, IARM, IBRM, IDRM, IGRM, IORM, IRRM, M3RM, M5RM, MRRM, O1RM, O3RM, O4RM, O6RM, O7RM, O9RM, OARM, OMRM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, P3RM, P4RM, P5RM, R5RM, T3RM, T5RM, T7RM, TARM, TBRM, TCRM, TERM, U1RM, U2RM, U4RM, U5RM, UCRM, UERM, UFRM, UGRM, UIRM, UMRM, UNRM, UORM, UPRM, UQRM, UVRM, UWRM, V0RM, V2RM, V4RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VHRM, VKRM, VMRM, VORM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, VZRM, W0RM, W2RM, W3RM, W6RM, WARM, WBRM, WCRM, WIRM, WJRM, WNRM, WPRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X5RM, X6RM, X7RM, X9RM, XERM, XFRM, XHRM, XIRM, XJRM, XKRM, XMRM, XSRM, XURM, XVRM, XYRM, XZRM, Y3RM, Y4RM, Y8RM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YYRM, Z2RM, Z4RM, Z5RM, Z6RM, Z8RM, Z9RM, ZARM, ZBRM, ZDRM, ZERM, ZFRM, ZGRM, ZMRM, ZR10, ZR11, ZR12, ZR50, ZR51, ZRA0, ZSRM, ZTRM, ZURM, ZWRM | 58 | none | 64 | 3 | none | 3000 | visible |
| CMRM, DDRM, F8RM, WLRM | 58 | none | 64 | 3 | none | 5000 | visible |
| APRM, C2RM, C9RM | 58 | none | none | 1 | none | 3000 | visible |
| BJRM, D2RM, O2RM, O5RM, UZRM | 58 | none | none | 2 | none | 3000 | visible |
| YRRM | 58 | none | none | 3 | none | 3000 | visible |
| A3RM, BERM, MMRM, ONRM, R2RM, THRM | 59 | 32 | none | 2 | none | 3000 | visible |
| U3RM | 59 | none | 65 | 3 | 55 | 3000 | visible |
| ACRM, ADRM, AORM, ATRM, B4RM, BDRM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BURM, BZRM, CDRM, CIRM, CKRM, CQRM, DCRM, DERM, DLRM, DVRM, DWRM, DZRM, ECRM, EGRM, EMRM, ENRM, ESRM, ETRM, EWRM, F3RM, F9RM, FDRM, FFRM, FHRM, FZRM, G5RM, G6RM, G8RM, G9RM, GJRM, GSRM, GTRM, GURM, H3RM, H7RM, H8RM, I3RM, IGRM, IQRM, IRRM, M3RM, M5RM, MRRM, O3RM, O6RM, O9RM, OMRM, OSRM, OXRM, OZRM, P1RM, R5RM, T7RM, TARM, TBRM, TCRM, TDRM, U0RM, U1RM, U2RM, U4RM, UCRM, UERM, UFRM, UIRM, UMRM, UPRM, UQRM, UXRM, V0RM, V2RM, V8RM, VBRM, VCRM, VVRM, VWRM, VYRM, W0RM, W2RM, W3RM, W6RM, WARM, WBRM, WCRM, WDRM, WERM, WQRM, WSRM, WTRM, X0RM, X5RM, X7RM, X9RM, XERM, XHRM, XIRM, XJRM, XKRM, XSRM, XURM, XVRM, XZRM, Y4RM, Y8RM, YERM, YIRM, YMRM, YPRM, YWRM, YXRM, YZRM, Z2RM, Z5RM, Z8RM, ZARM, ZERM, ZR11, ZR12, ZR50, ZR51, ZRA0, ZSRM, ZURM | 59 | none | 65 | 3 | none | 3000 | visible |
| DDRM, F8RM, WLRM | 59 | none | 65 | 3 | none | 5000 | visible |
| BJRM, O2RM, O5RM, UZRM | 59 | none | none | 2 | none | 3000 | visible |
| YORM, YRRM | 59 | none | none | 3 | none | 3000 | visible |
| B1RM | 5A | none | none | 2 | none | 3000 | visible |
| E3RM, E4RM, FLRM, P2RM, ZR70, ZR80 | 5B | none | none | 1 | none | 3000 | visible |
| E3RM, E4RM, FLRM, P2RM, ZR70, ZR80 | 5C | none | none | 1 | none | 3000 | visible |
| B9TT | 5D | none | 47 | 3 | none | 3000 | visible |
| AHRM, APRM, BVRM, C2RM, CORM, FCRM, I2RM, I7RM, I8RM, ICRM, IERM, IFRM, IHRM, IIRM, IRRM, O5RM, T3RM, V9RM, VIRM, VNRM, WIRM, X9RM, XVRM, YGRM | 5D | none | none | 2 | none | 3000 | visible |
| ZVRM | 5E | none | none | 1 | none | 3000 | visible |
| A0RM, A1RM, AARM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, AWRM, AXRM, BGRM, BNRM, BORM, C4RM, C5RM, CARM, CGRM, CIRM, CJRM, CLRM, CMRM, CQRM, CSRM, CTRM, CURM, CWRM, CZRM, D0RM, D1RM, D3RM, D9RM, DCRM, DERM, DFRM, DHRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, EDRM, EFRM, EMRM, EORM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FRRM, FTRM, FZRM, G3RM, G5RM, G7RM, G9RM, GARM, GDRM, GHRM, GJRM, GKRM, GNRM, GORM, GSRM, GYRM, H5RM, H7RM, I1RM, IBRM, IERM, IGRM, M6RM, M7RM, MARM, O8RM, P1RM, P6RM, T7RM, TCRM, TDRM, TERM, U4RM, U5RM, URRM, UTRM, UYRM, VBRM, VKRM, VLRM, VPRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VZRM, W6RM, W7RM, W9RM, WHRM, WJRM, WKRM, WNRM, WURM, WXRM, X7RM, XCRM, XERM, XFRM, XHRM, XIRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XWRM, XYRM, XZRM, Y8RM, YARM, YIRM, YORM, YYRM, YZRM, Z2RM, Z4RM, Z5RM, Z6RM, ZARM, ZERM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZSRM, ZTRM, ZURM, ZWRM | 5E | none | none | 2 | none | 3000 | visible |
| ONRM | 5F | 39 | none | 2 | none | 3000 | visible |
| BERM | 5F | 47 | none | 2 | none | 3000 | visible |
| MMRM | 5F | 49 | none | 2 | none | 3000 | visible |
| A3RM | 5F | 4C | none | 2 | none | 3000 | visible |
| R2RM | 5F | 50 | none | 2 | none | 3000 | visible |
| A3RM, A9RM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BERM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C2RM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CLRM, CMRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D2RM, D3RM, D4RM, DARM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, I1RM, IARM, IBRM, IORM, M3RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, R5RM, T5RM, T7RM, T9RM, TARM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, UKRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VDRM, VERM, VFRM, VORM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, X7RM, X9RM, XCRM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XYRM, XZRM, Y3RM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z8RM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZWRM | 5F | none | none | 2 | none | 3000 | visible |
| A3RM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BERM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CLRM, CMRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D3RM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FCRM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, I1RM, IBRM, M3RM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OZRM, P0RM, P1RM, P4RM, P5RM, R5RM, T7RM, T9RM, TARM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UERM, UFRM, UGRM, UHRM, UKRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VFRM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, X7RM, X9RM, XCRM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XYRM, XZRM, Y8RM, YARM, YERM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z8RM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZWRM | 61 | none | none | 2 | none | 3000 | visible |
| ABRM, ACRM, ADRM, B9TT, C0RM, D7RM, DHRM, DIRM, I0RM, I4RM, I5RM, M9RM, MLRM, O0RM, OTRM, S9RM, U0RM, U7RM, U8RM, U9RM, UARM, UBRM, UJRM, UNRM, UZRM, V0RM, V6RM, V7RM, VARM, VKRM, XARM, YHRM, YZRM, ZHRM, ZIRM, ZJRM, ZKRM, ZLRM, ZR21, ZRI0 | 62 | none | none | 2 | none | 3000 | visible |
| A3RM, AERM, AFRM, AGRM, ALRM, AMRM, ANRM, APRM, AURM, AWRM, AXRM, AYRM, B4RM, BDRM, BERM, BHRM, BIRM, BLRM, BNRM, BORM, BURM, BZRM, C2RM, C4RM, C5RM, CARM, CBRM, CGRM, CIRM, CLRM, CMRM, CSRM, CTRM, CURM, CWRM, CYRM, CZRM, D0RM, D3RM, DCRM, DERM, DFRM, DHRM, DIRM, DJRM, DKRM, DLRM, DPRM, DWRM, DZRM, E1RM, E5RM, E9RM, EDRM, EMRM, EORM, ESRM, ETRM, EVRM, EWRM, EXRM, F0RM, F1RM, F3RM, F4RM, F5RM, F7RM, F9RM, FARM, FDRM, FERM, FGRM, FHRM, FIRM, FKRM, FMRM, FNRM, FPRM, FQRM, FRRM, FTRM, FZRM, G3RM, G7RM, G9RM, GARM, GCRM, GDRM, GERM, GFRM, GGRM, GHRM, GJRM, GKRM, GORM, GSRM, GTRM, GYRM, H2RM, H5RM, H7RM, H8RM, I1RM, IBRM, M3RM, MLRM, MMRM, MRRM, O1RM, O2RM, O3RM, O5RM, O7RM, O8RM, O9RM, OARM, OPRM, OQRM, ORRM, OSRM, OXRM, OYRM, OZRM, P0RM, P1RM, P4RM, P5RM, R5RM, T7RM, T9RM, TARM, TDRM, TERM, U1RM, U2RM, U3RM, U4RM, U5RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, UKRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VFRM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, X7RM, X9RM, XCRM, XFRM, XHRM, XIRM, XJRM, XKRM, XLRM, XMRM, XPRM, XQRM, XSRM, XTRM, XVRM, XYRM, XZRM, Y8RM, YARM, YERM, YGRM, YHRM, YIRM, YJRM, YMRM, YORM, YPRM, YWRM, YZRM, Z2RM, Z3RM, Z4RM, Z5RM, Z8RM, ZERM, ZFRM, ZGRM, ZMRM, ZORM, ZR50, ZR51, ZWRM | 63 | none | none | 2 | none | 3000 | visible |
| BRRM, YGRM | 64 | none | none | 2 | none | 3000 | hidden |
| APRM, C2RM, C9RM | 64 | none | none | 2 | none | 3000 | visible |
| BRRM, YGRM | 66 | none | none | 2 | none | 3000 | hidden |
| APRM, C2RM, C9RM | 66 | none | none | 2 | none | 3000 | visible |
| R2RM | 67 | 4C | none | 2 | none | 3000 | visible |
| B1RM | 67 | none | none | 2 | none | 3000 | visible |
| R2RM | 68 | 4E | none | 2 | none | 3000 | visible |
| B1RM | 68 | none | none | 2 | none | 3000 | visible |
| BRRM, YGRM | 69 | none | none | 2 | none | 3000 | hidden |
| APRM, C2RM, C9RM | 69 | none | none | 2 | none | 3000 | visible |
| U3RM | 6B | none | 6A | 3 | 53 | 3000 | visible |
| C7RM, DJRM, DKRM, DLRM, EVRM, EWRM, FDRM, FFRM, G7RM, M9RM, ZNRM, ZRRM | 6B | none | 6A | 3 | none | 3000 | visible |
| C6RM, C7RM, VRRM, ZNRM, ZRRM | 6C | none | none | 2 | none | 3000 | visible |
| Y2RM | 6F | none | none | 2 | none | 3000 | visible |
| ZHRM, ZIRM | 70 | none | 95 | 3 | none | 3000 | visible |
| BZRM | 70 | none | none | 2 | none | 3000 | visible |
| C2RM, CARM, E6RM, GARM, M5RM | 71 | none | none | 1 | none | 3000 | visible |
| C2RM, E6RM, GARM, M5RM | 72 | none | none | 1 | none | 3000 | visible |
| E6RM, M5RM | 73 | none | none | 1 | none | 3000 | visible |
| E6RM, M5RM | 74 | none | none | 1 | none | 3000 | visible |
| P2RM, ZRA0 | 75 | none | none | 2 | none | 3000 | visible |
| AURM, E5RM | 76 | none | none | 2 | none | 3000 | visible |
| DTRM, F6RM | 84 | none | none | 2 | none | 3000 | hidden |
| DSRM | 84 | none | none | 2 | none | 3000 | visible |
| ZHRM, ZIRM | 8C | none | 8D | 3 | none | 3000 | visible |
| ZHRM, ZIRM | 8E | none | 8F | 3 | none | 3000 | visible |
| AURM, ILRM | 90 | none | none | 2 | none | 3000 | visible |
| AERM, ALRM | 91 | none | 92 | 3 | none | 3000 | visible |
| ZHRM, ZIRM | 93 | none | 94 | 3 | none | 3000 | visible |
| ZORM | 96 | none | none | 1 | none | 3000 | visible |
| ZORM | 97 | none | none | 1 | none | 3000 | visible |
| BGRM | A1 | none | none | 2 | none | 3000 | visible |
| BGRM | A2 | none | none | 2 | none | 3000 | visible |
| BGRM | A3 | none | none | 2 | none | 3000 | visible |
| BGRM | A4 | none | none | 2 | none | 3000 | visible |
| BGRM | A5 | none | none | 2 | none | 3000 | visible |
| BSRM, C6RM, C7RM, E3RM, YSRM, YTRM, YURM, YVRM, ZNRM | B2 | none | B3 | 3 | none | 3000 | visible |
| DMRM, DPRM | BA | none | BB | 3 | none | 3000 | visible |
| E3RM, GXRM | BC | none | none | 2 | none | 3000 | visible |
| E3RM, GXRM | BD | none | none | 2 | none | 3000 | visible |
| EURM | D0 | none | none | 1 | none | 3000 | visible |
| EURM | D1 | none | none | 1 | none | 3000 | visible |
| F4RM, FGRM, FMRM, FNRM, GARM, GDRM, GKRM | D6 | none | none | 2 | none | 3000 | visible |
| F4RM, FGRM, FMRM, FNRM, G7RM, GARM, GDRM, GKRM | D8 | none | none | 2 | none | 3000 | visible |
| DNRM, Y4RM | F0 | none | F1 | 3 | none | 3000 | visible |
| G5RM, G6RM | F0 | none | none | 2 | none | 3000 | visible |
| EZRM, Y4RM | F2 | none | F3 | 3 | none | 3000 | visible |
| FIRM, FRRM | F3 | none | F2 | 3 | none | 3000 | visible |
| G5RM, G6RM, H2RM | F4 | none | F5 | 3 | none | 3000 | visible |
| FERM, FFRM | F6 | none | F7 | 3 | none | 3000 | visible |
| FIRM, FRRM | F7 | none | F6 | 3 | none | 3000 | visible |
| GVRM | none | 31 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 32 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 35 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 37 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 38 | none | 1 | 63 | 3000 | visible |
| GVRM | none | 42 | none | 1 | none | 3000 | visible |
| GVRM | none | 43 | none | 1 | none | 3000 | visible |
| GVRM | none | 44 | none | 1 | none | 3000 | visible |
| GVRM | none | 45 | none | 1 | none | 3000 | visible |
| GVRM | none | 46 | none | 1 | none | 3000 | visible |
| GVRM | none | 47 | none | 1 | none | 3000 | visible |
| H6RM | none | none | 2B | 3 | none | 3000 | visible |
| H6RM | none | none | 2C | 3 | none | 3000 | visible |
| FRRM | none | none | 84 | 2 | none | 5000 | visible |
| AORM, E9RM, FGRM, FMRM, FNRM, GDRM | none | none | 84 | 3 | none | 5000 | visible |
| DXRM | none | none | BC | 3 | none | 3000 | visible |
| DXRM | none | none | BD | 3 | none | 3000 | visible |
| U3RM | none | none | none | 1 | 51 | 3000 | visible |
| U3RM | none | none | none | 1 | 52 | 3000 | visible |
| ZRS3 | none | none | none | 2 | aprm | 3000 | visible |
| ZRS3 | none | none | none | 2 | aqrm | 3000 | visible |
| ZRS0 | none | none | none | 2 | b8tt | 3000 | visible |
| ZRS0 | none | none | none | 2 | b9tt | 3000 | visible |
| ZRS1 | none | none | none | 2 | d7rm | 3000 | visible |
| ZRS1 | none | none | none | 2 | i4rm | 3000 | visible |
| ZRS1 | none | none | none | 2 | i5rm | 3000 | visible |
| ZRS2 | none | none | none | 2 | zr00 | 3000 | visible |
| ZRS2 | none | none | none | 2 | zr01 | 3000 | visible |
| ZRS1 | none | none | none | 2 | zri0 | 3000 | visible |

 </details>

| Power Cool TEST opcode | Refresh seconds | Rest seconds |
|---|---|---|
| `24` | 10 | 5 |
| `3F` | 10 | 5 |
| `40` | 12 | 5 |
| `25` | 12 | 5 |
| `26` | 10 | 5 |
| `41` | 10 | 5 |
| `42` | 12 | 5 |
| `27` | 12 | 5 |
| `29` | 10 | 5 |
| `3F` | 10 | 5 |
| `40` | 12 | 5 |
| `41` | 10 | 5 |
| `42` | 12 | 5 |
| `2A` | 12 | 5 |
<!-- /generated -->

### Position Feedback / Notifications

The source recognizer's checksum, prefix order and partial/coalesced-message
behavior are preserved. Malformed input reports a bounded diagnostic rejection.
Exact alarm-capability, lamp-capability and alarm set/cancel replies update
current-session state. An alarm confirmation preserves the local selection;
it is not a schedule readback or general movement acknowledgment. Desk telemetry
and accessory messages do not create bed position or accessory entities.

### Command Timing

Ordinary refresh is 150 ms, or 110 ms for actual advertised TWRM/MLRM names.
Raw advertised 6BRM uses 170 ms. Manual layout selection does not change cadence.
Long thresholds are 3000 ms or the selected node's 5000 ms override, counted by
worker polls. Held release waits 50 ms. Alarm writes are 300 ms apart. RGB sends
one 10-byte write with a 150 ms busy interval. Lamp time is 0 to 300 seconds;
zero has distinct slider (`FFFF`) and Save (`0000`) encodings with unverified
physical meaning. Y6RM's app timer labels differ from its resource names, so
they are retained as app choices rather than asserted firmware durations.

Power Cool RMCS sends its 89-byte selected program in 20-byte chunks, 10 ms
apart, without adding a STOP. TEST uses the generated run/rest sequence and
the admitted route's release. Diagnostic movement participates in HA's movement
scheduler and cancellation. Ordinary holds use renewable leases where the
selected gesture actually refreshes until release.

### Notes

HA cancels pending saves and clears stale gesture latches instead of allowing
Android's in-bounds CANCEL/pause behavior to resume movement. Release targets
the mode admitted with the gesture, so changing a live selector cannot redirect
STOP. Cleanup uses a fresh cancellation event; raw long-only paths with no
defined release end their pending refresh without inventing a STOP.

Wi-Fi, mesh administration, cloud/accounts, OTA, standalone desks, phone/media
controls and separate aroma/audio accessories are outside this bed integration.
Luuna's manufacturing layouts remain excluded; Power Cool's separately accepted
direct bed diagnostics are available only through their explicit layouts.

### Analysis provenance

- Luuna Rise `com.richmat.luunarise2` 1.0.13 (21), artifact SHA-256
  04c89b0e7bb18bf8c11522c27af89cbbcf665d753452b168756f013a8153d549.
- Power Cool Sleep System `com.richmat.powercool` 1.0.8 (9), artifact set SHA-256
  `71123fc12a3d063a3acc278f3bc2b2bf5ad507fe1a5322694f509cbb272143db`.

### Lady Americana / ACAA / STA Homecare / Zero Gravity family

**Status:** ❓ APK-verified, hardware unverified. External beta/release qualification only.

#### Setup

Choose **Richmat**, then the exact app and its four-character layout. All four
app names are searchable in setup and Configure. A shared Bluetooth name or
service suggests the family, and does not choose an app or physical layout.
Each receiver in a two-address pair keeps its own app, layout and saved choices.
There is no single-address Left/Right selector for these apps.

The fixed route priority is W1, W2, Nordic UART, then W4. The first present
service wins even if its characteristics are incomplete. An explicit advanced
option enables the source's third-service property fallback. HA resolves both
characteristics from the current session and rejects an incomplete route.
Android leaves write type unchanged; HA uses the selected characteristic's
advertised write properties. No authentication or position-feedback contract
is established.

#### Controls

The generated tables below retain every layout's ordinary, raw legacy and
loaded long operands. Status 1 refreshes a held command. Status 2 sends once.
Status 3 distinguishes short recall from a long command. A numbered memory
resource is available only on layouts that actually bind it; controls retain
their source resource names where icons and resource numbering disagree.

The GVRM Head/Foot choice is local: Head reads the legacy short getter on both
transports, while Foot has a null getter. It is not a bed-side address. U3RM's
local axis selection starts at third; tagged preset releases select third,
fourth or fifth for later adjustments. Legacy-long attributes ignored by the
Android constructor are not alternate commands.

The separate generic BED requests correspond to the app's recognized-command
callbacks. They remain usable through `richmat_resource_bed` and optional
app-request buttons, independently of XML buttons and alarm choices. A
`memory_three` request does not certify a third physical slot. Use the normal
Stop action for movement release. `voice_stop_request` sends the app's separate
request and then the protocol release; its label is not emergency STOP evidence.
Speech recognition and microphone machinery are not part of the integration.

<!-- generated:richmat-resource-apps -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App | Stored key | Catalog layouts | Outside bed setup | Shared 3B BED action |
|---|---|---|---|---|
| Lady Americana | lady_americana | 243 | WFRM | False |
| ACAA | acaa | 243 | WFRM | True |
| STA Homecare | sta2 | 243 | WFRM | False |
| Zero Gravity | zerogravity | 243 | BBRM, OVRM, W8RM, WFRM | True |

| Input alias | Layout |
|---|---|
| B6RU | B6RM |
| ZR90 | S9RM |
| 200IV2 | A8RM |
| FC200 | A8RM |
| 400I | A0RM |
| 800I | A1RM |
| MPE_HJ001 | ZRA2 |
| MPE_HJ002 | TWRM |
| MPE_HJ003 | WPRM |
| MPE_HJ005 | WPRM |
| MPE_HJ006 | BNRM |
| MPE_HJ008 | BLRM |

| App | Ordinary refresh | Raw advertised 6BRM refresh | Held release | Tap release | Long counter numerator |
|---|---|---|---|---|---|
| Lady Americana | 150 | 170 | 50 | 150 | 3000 |
| ACAA | 150 | 170 | 50 | 150 | 3000 |
| STA Homecare | 150 | 170 | 50 | 150 | 3000 |
| Zero Gravity | 150 | 170 | 50 | 150 | 3000 |

| Direct action | Write | Gate / sequence |
|---|---|---|
| Framed startup | `6E 02 01 00 71` | Before notification registration; none on raw |
| Alarm query | `6E 08 01 01 78` | Nonempty layout alarm list; then wait 500 ms |
| LED query | `6E 0A 00 01 79` | Then wait 500 ms |
| Shared accessory query | `6E 1A 00 00 88` | Then wait 500 ms; no accessory controls |
| Cancel alarm | `6E 05 00 00 73` / `6E 06 00 00 74` | 300 ms after each write |
| RGB example | `6E 0C FF 01 7A 6E 0D DD FF 57` | Observed LED capability; one concatenated write |
| Light timeout 0 s | `6E 0B 00 00 79` | Observed LED capability; byte-pair fold |
| Light timeout 1 s | `6E 0B 00 01 7A` | Observed LED capability; byte-pair fold |
| Light timeout 255 s | `6E 0B 00 FF 78` | Observed LED capability; byte-pair fold |
| Light timeout 256 s | `6E 0B 00 01 7A` | Observed LED capability; byte-pair fold |
| Light timeout 300 s | `6E 0B 00 2D A6` | Observed LED capability; byte-pair fold |
| D1RM timer index 0 | `6E 01 00 5E CD` | D1RM only; direct, no release |
| D1RM timer index 1 | `6E 01 00 01 70` | D1RM only; direct, no release |
| D1RM timer index 2 | `6E 01 00 5F CE` | D1RM only; direct, no release |
| D1RM timer index 3 | `6E 01 00 63 D2` | D1RM only; direct, no release |
| D1RM timer index 4 | `6E 01 00 04 73` | D1RM only; direct, no release |
| D1RM timer index 5 | `6E 01 00 61 D0` | D1RM only; direct, no release |

| Layout | Alarm tags, in traversal order |
|---|---|
| A9RM | 46, 5D |
| BCRM | 45 |
| BJRM | 45 |
| O0RM | 45, 46, 2E, 4C, 4E |
| OTRM | 45, 46, 2E, 4C, 4E |
| OYRM | 45, 46, 4C, 4E |
| P1RM | 58, 45 |
| V1RM | 45, 46, 2E |
| V4RM | 58, 46, 45, 5D |
| WJRM | 46, 45, 58, 2E |
| WKRM | 46, 45, 2E, 2F |
| WMRM | 59 |
| WRRM | 2E |
| WURM | 46 |
| WVRM | 46 |
| WWRM | 46 |
| WYRM | 46 |
| X1RM | 45, 46 |
| X2RM | 45 |

| Generic BED callback request | Raw | Framed | Execution |
|---|---|---|---|
| head_up | 24 | `6E 01 00 24 93` | bounded held refresh, then release |
| head_down | 25 | `6E 01 00 25 94` | bounded held refresh, then release |
| foot_up | 26 | `6E 01 00 26 95` | bounded held refresh, then release |
| foot_down | 27 | `6E 01 00 27 96` | bounded held refresh, then release |
| tv | 58 | `6E 01 00 58 C7` | once, then release |
| lounge | 59 | `6E 01 00 59 C8` | once, then release |
| zero_gravity | 45 | `6E 01 00 45 B4` | once, then release |
| anti_snore | 46 | `6E 01 00 46 B5` | once, then release |
| memory_one | 2E | `6E 01 00 2E 9D` | once, then release |
| memory_two | 2F | `6E 01 00 2F 9E` | once, then release |
| memory_three | 30 | `6E 01 00 30 9F` | once, then release |
| flat | 31 | `6E 01 00 31 A0` | once, then release |
| voice_stop_request | 47 | `6E 01 00 47 B6` | once, then release |

<details><summary>Common layout control bindings</summary>

| Control | Raw | Framed short | Framed long | Status | Local tag | Layouts |
|---|---|---|---|---|---|---|
| Control 1 | none | none | none | 2 | b8tt | ZRS0 |
| Control 1 | none | none | none | 2 | zr00 | ZRS2 |
| Control 1 | none | none | none | 2 | zri0 | ZRS1 |
| Control 10 | 45 | none | none | 1 | none | GVRM |
| Control 10 | none | none | none | 7 | none | O0RM, OTRM |
| Control 10 | none | none | none | 9 | none | BMRM, IDRM, UMRM, UORM, UPRM, UQRM, UWRM, WVRM, WWRM, WYRM, ZR10, ZR11, ZR12 |
| Control 11 | none | none | none | 8 | 64 | W0RM, WARM |
| Control 11 | none | none | none | 9 | none | I7RM, I9RM, IERM, IFRM, IHRM, V1RM, VGRM, WRRM, ZR60 |
| Control 12 | none | none | none | 9 | none | B1RM, GVRM, Y3RM |
| Control 13 | 46 | none | none | 1 | none | GVRM |
| Control 13 | none | none | none | 9 | none | BERM, VRRM |
| Control 14 | none | none | none | 9 | none | W9RM |
| Control 15 | none | none | none | 8 | 64 | W3RM |
| Control 15 | none | none | none | 9 | none | MLRM, R6RM, U3RM |
| Control 16 | 47 | none | none | 1 | none | GVRM |
| Control 16 | none | none | none | 9 | none | T1RM |
| Control 17 | none | none | none | 7 | none | P1RM |
| Control 17 | none | none | none | 9 | none | IBRM, VBRM, VKRM |
| Control 18 | none | none | none | 9 | none | A3RM, BLRM, BNRM, BZRM, D2RM, I8RM, M3RM, M5RM, MRRM, O1RM, O2RM, O3RM, O5RM, O7RM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, R5RM, U1RM, U2RM, UERM, UFRM, UGRM, UHRM, UKRM, ULRM, UVRM, V2RM, V4RM, V8RM, VCRM, VFRM, VTRM, VURM, VYRM, W0RM, W2RM, WARM, WBRM, WCRM, WDRM, WERM, WSRM, X0RM |
| Control 19 | none | none | none | 9 | none | BHRM, T7RM, URRM, UTRM, UYRM, VSRM, WJRM, WKRM |
| Control 2 | 37 | none | none | 1 | 63 | GVRM |
| Control 2 | none | none | none | 2 | b9tt | ZRS0 |
| Control 2 | none | none | none | 2 | i4rm | ZRS1 |
| Control 2 | none | none | none | 2 | zr01 | ZRS2 |
| Control 2 | none | none | none | 9 | none | B9TT, BKRM, I0RM, I2RM, I3RM, I4RM, I5RM, IIRM, O0RM, OTRM, OYRM, P2RM, T5RM, U8RM, U9RM, UARM, UBRM, UCRM, UJRM, V9RM, VIRM, VMRM, VNRM, VXRM, WIRM, WZRM, ZRA0, ZRI0 |
| Control 20 | none | none | none | 9 | none | BGRM, BIRM, I1RM, MMRM, V0RM, W3RM, WNRM |
| Control 21 | none | none | none | 9 | none | D4RM, UNRM |
| Control 22 | none | none | none | 9 | none | O6RM, OMRM, OORM, U5RM |
| Control 3 | 42 | none | none | 1 | none | GVRM |
| Control 3 | none | none | none | 2 | i5rm | ZRS1 |
| Control 3 | none | none | none | 9 | none | IJRM, U7RM, V5RM, V6RM, V7RM, VARM, ZR01 |
| Control 4 | 31 | none | none | 1 | 63 | GVRM |
| Control 4 | none | none | none | 9 | none | I6RM, IKRM, IMRM, OURM |
| Control 5 | 35 | none | none | 1 | 63 | GVRM |
| Control 5 | none | none | none | 1 | 51 | U3RM |
| Control 5 | none | none | none | 8 | 64 | OSRM |
| Control 5 | none | none | none | 9 | none | BBRM, W4RM, ZR00 |
| Control 6 | 43 | none | none | 1 | none | GVRM |
| Control 6 | none | none | none | 9 | none | ZR21 |
| Control 7 | 44 | none | none | 1 | none | GVRM |
| Control 7 | none | none | none | 7 | none | BCRM |
| Control 7 | none | none | none | 8 | 64 | W9RM |
| Control 7 | none | none | none | 9 | none | A7RM, B0RM, P9RM, SARM, T0RM, T2RM, T4RM, TLRM, TWRM, TZRM, ZR20 |
| Control 8 | 32 | none | none | 1 | 63 | GVRM |
| Control 8 | none | none | none | 1 | 52 | U3RM |
| Control 8 | none | none | none | 9 | none | A8RM, VJRM, W1RM |
| Control 9 | 38 | none | none | 1 | 63 | GVRM |
| Control 9 | none | none | none | 9 | none | M9RM, S9RM |
| btn_foot | none | none | none | 0 | 62 | GVRM |
| btn_head | none | none | none | 0 | 61 | GVRM |
| com  first second up | 23 | `6E 01 00 23 92` | none | 2 | none | OORM |
| com fifth down | 72 | `6E 01 00 72 E1` | none | 1 | none | M5RM |
| com fifth up | 71 | `6E 01 00 71 E0` | none | 1 | none | M5RM |
| com first down | 25 | `6E 01 00 25 94` | none | 1 | none | A0RM, A1RM, A2RM, A6RM, A7RM, A8RM, A9RM, AARM, B0RM, B1RM, B2RM, B3RM, B6RM, B7RM, B8RM, B8TT, B9TT, BARM, BBRM, BCRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IJRM, IKRM, ILRM, IMRM, M3RM, M5RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OVRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T5RM, T6RM, T7RM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WMRM, WNRM, WORM, WPRM, WQRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, Y2RM, Y3RM, ZR00, ZR01, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0 |
| com first down | 37 | `6E 01 00 25 94` | none | 1 | none | 6BRM, 6CRM, 6DRM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM |
| com first down | 38 | `6E 01 00 25 94` | none | 1 | none | A3RM, BERM, MMRM, R2RM |
| com first second down | 2A | `6E 01 00 2A 99` | none | 1 | none | A2RM, AARM, B6RM, B7RM, BFRM, BGRM, BHRM, BNRM, D2RM, I2RM, I3RM, IARM, IDRM, IIRM, O2RM, O3RM, OPRM, OQRM, OXRM, P0RM, P2RM, R5RM, R6RM, TLRM, U0RM, U1RM, U4RM, UCRM, UFRM, UJRM, UKRM, ULRM, UPRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V4RM, VXRM, W5RM, W6RM, W7RM, WERM, WKRM, WRRM, WSRM, WTRM, WURM, WVRM, WZRM, Y3RM, ZR10, ZR20, ZR30, ZR51, ZR70, ZR80, ZRA0, ZRA1, ZRA2 |
| com first second down | 39 | `6E 01 00 2A 99` | none | 1 | none | 6BRM, A3RM, GMRM, MMRM, R2RM, T4RM, THRM, TWRM, V3RM, VYRM, W0RM, W2RM |
| com first second up | 29 | `6E 01 00 29 98` | none | 1 | none | A2RM, AARM, B0RM, B6RM, B7RM, BFRM, BGRM, BHRM, BKRM, BNRM, D2RM, I2RM, I3RM, IARM, IDRM, IIRM, O2RM, O3RM, OPRM, OQRM, OXRM, P0RM, P2RM, R5RM, R6RM, TLRM, U0RM, U1RM, U4RM, U8RM, UCRM, UFRM, UJRM, UKRM, ULRM, UPRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V4RM, V5RM, V6RM, VARM, VXRM, VYRM, W0RM, W2RM, W5RM, W6RM, W7RM, WERM, WKRM, WRRM, WSRM, WTRM, WURM, WVRM, WZRM, Y3RM, ZR10, ZR20, ZR30, ZR51, ZR70, ZR80, ZRA0, ZRA1, ZRA2 |
| com first second up | 36 | `6E 01 00 29 98` | none | 1 | none | A3RM, MMRM, R2RM |
| com first second up | 38 | `6E 01 00 29 98` | none | 1 | none | 6BRM, 6CRM, 6DRM, GMRM, T4RM, THRM, TWRM, V3RM |
| com first up | 24 | `6E 01 00 24 93` | none | 1 | none | A0RM, A1RM, A2RM, A6RM, A7RM, A8RM, A9RM, AARM, B0RM, B1RM, B2RM, B3RM, B6RM, B7RM, B8RM, B8TT, B9TT, BARM, BBRM, BCRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IJRM, IKRM, ILRM, IMRM, M3RM, M5RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OVRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T5RM, T6RM, T7RM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WMRM, WNRM, WORM, WPRM, WQRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, Y2RM, Y3RM, ZR00, ZR01, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0 |
| com first up | 34 | `6E 01 00 24 93` | none | 1 | none | 6BRM, 6CRM, 6DRM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM |
| com first up | 35 | `6E 01 00 24 93` | none | 1 | none | A3RM, BERM, MMRM, R2RM |
| com first up down | 90 | `6E 01 00 90 FF` | none | 2 | none | ILRM |
| com first up once | 3D | `6E 01 00 3D AC` | none | 2 | none | OWRM |
| com first up second down | 21 | `6E 01 00 21 90` | none | 2 | none | OORM, OURM, OWRM, WYRM |
| com flat | 31 | `6E 01 00 31 A0` | none | 2 | none | 6CRM, 6DRM, A0RM, A1RM, A3RM, A6RM, A7RM, A8RM, A9RM, AARM, B0RM, B1RM, B7RM, B8RM, B8TT, B9TT, BCRM, BERM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, IKRM, IMRM, M3RM, M9RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, OMRM, ONRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OWRM, OXRM, OYRM, OZRM, P0RM, P1RM, P9RM, R2RM, R5RM, R6RM, S9RM, SARM, T0RM, T2RM, T5RM, T6RM, T7RM, THRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X1RM, X2RM, Y2RM, Y3RM, ZR10, ZR11, ZR12, ZR21, ZR40, ZR50, ZR51, ZR60, ZRA2, ZRI0 |
| com flat | 32 | `6E 01 00 31 A0` | none | 2 | none | TWRM, TZRM |
| com flat | 38 | `6E 01 00 31 A0` | none | 2 | none | ONRM |
| com flat2 | 6C | `6E 01 00 6C DB` | none | 2 | none | VRRM |
| com fourth down | 42 | `6E 01 00 42 B1` | none | 1 | none | A1RM, AARM, BIRM, D4RM, I5RM, O5RM, ORRM, T1RM, U5RM, U9RM, UHRM, URRM, V0RM, V2RM, VERM, VFRM, VIRM, VORM, VPRM, VRRM, VTRM, VURM, VZRM, WBRM, WCRM, WHRM, WTRM, ZR50, ZRA0 |
| com fourth down | 45 | `6E 01 00 42 B1` | none | 1 | none | BERM |
| com fourth up | 41 | `6E 01 00 41 B0` | none | 1 | none | A1RM, AARM, BIRM, D4RM, I5RM, O5RM, ORRM, T1RM, U5RM, U9RM, UHRM, URRM, V0RM, V2RM, VERM, VFRM, VIRM, VORM, VPRM, VRRM, VTRM, VURM, VZRM, WBRM, WCRM, WHRM, WTRM, ZR50, ZRA0 |
| com lounge return | 32 | `6E 01 00 59 C8` | none | 2 | none | A3RM, BERM, MMRM, ONRM, R2RM, THRM |
| com lounge return | 59 | `6E 01 00 59 C8` | `6E 01 00 65 D4` | 3 | 55 | U3RM |
| com lounge return | 59 | `6E 01 00 59 C8` | `6E 01 00 65 D4` | 3 | none | BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BZRM, I3RM, IGRM, M3RM, M5RM, MRRM, O3RM, O6RM, OMRM, OSRM, OXRM, OZRM, P1RM, R5RM, T7RM, U0RM, U1RM, U2RM, U4RM, UCRM, UERM, UFRM, UIRM, UMRM, UPRM, UQRM, UXRM, V0RM, V2RM, V8RM, VBRM, VCRM, VVRM, VWRM, VYRM, W0RM, W2RM, W3RM, W6RM, WARM, WBRM, WCRM, WDRM, WERM, WLRM, WQRM, WSRM, WTRM, X0RM, ZR11, ZR12, ZR50, ZR51, ZRA0 |
| com lounge return | 59 | `6E 01 00 59 C8` | none | 2 | none | BJRM, O2RM, O5RM, UZRM |
| com m1 return | 2E | `6E 01 00 2E 9D` | `6E 01 00 2B 9A` | 3 | none | A0RM, A1RM, A2RM, A7RM, A9RM, B9TT, BJRM, BKRM, BLRM, BMRM, BNRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I6RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IHRM, IIRM, IKRM, ILRM, M3RM, M5RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, OMRM, OORM, OPRM, OQRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P9RM, R5RM, R6RM, T1RM, T5RM, T6RM, T7RM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, UERM, UFRM, UGRM, UHRM, UIRM, UKRM, ULRM, UMRM, UNRM, UORM, UQRM, URRM, UTRM, UVRM, UXRM, UYRM, UZRM, V1RM, V3RM, V4RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VVRM, VWRM, VYRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W9RM, WARM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WNRM, WPRM, WQRM, WRRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, ZR10, ZR12, ZR50, ZR51, ZR60, ZR80, ZRA2, ZRI0 |
| com m1 return | 2E | `6E 01 00 2E 9D` | none | 1 | none | VXRM |
| com m1 return | 42 | `6E 01 00 2E 9D` | `6E 01 00 2B 9A` | 3 | none | A3RM |
| com m1 return | 42 | `6E 01 00 2E 9D` | none | 2 | none | MMRM, R2RM |
| com m1 set | 2B | `6E 01 00 2B 9A` | none | 2 | none | OMRM, VXRM |
| com m1 set | 43 | `6E 01 00 2B 9A` | none | 2 | none | MMRM, R2RM |
| com m2 return | 2F | `6E 01 00 2F 9E` | `6E 01 00 2C 9B` | 3 | none | A0RM, A1RM, A2RM, A9RM, BJRM, BKRM, BLRM, BMRM, BZRM, D0RM, D1RM, D2RM, D4RM, I1RM, I2RM, I3RM, I5RM, I6RM, IARM, ILRM, M3RM, M5RM, MRRM, O1RM, O2RM, O3RM, O4RM, O7RM, OPRM, OQRM, OSRM, OXRM, OZRM, P0RM, P1RM, P2RM, P9RM, R5RM, R6RM, T1RM, T5RM, T6RM, T7RM, U0RM, U1RM, U2RM, U5RM, UERM, UFRM, UGRM, UHRM, UIRM, UKRM, ULRM, UMRM, UNRM, UORM, UQRM, UTRM, UVRM, UXRM, UZRM, V4RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VWRM, W2RM, W3RM, W5RM, W6RM, W7RM, WDRM, WERM, WIRM, WKRM, WLRM, WNRM, WPRM, WURM, WXRM, X0RM, ZR12, ZR50, ZR51, ZR80, ZRA2 |
| com m2 return | 2F | `6E 01 00 2F 9E` | none | 1 | none | VXRM |
| com m2 return | 2F | `6E 01 00 2F 9E` | none | 2 | none | BNRM |
| com m2 return | 44 | `6E 01 00 2F 9E` | `6E 01 00 2C 9B` | 3 | none | A3RM |
| com m2 return | 44 | `6E 01 00 2F 9E` | none | 2 | none | MMRM, R2RM |
| com m2 return old2 | 44 | `6E 01 00 44 B3` | none | 1 | none | BERM |
| com m2 set | 2C | `6E 01 00 2C 9B` | none | 2 | none | VXRM |
| com m2 set | 45 | `6E 01 00 2C 9B` | none | 2 | none | MMRM, R2RM |
| com m3 return | 30 | `6E 01 00 30 9F` | `6E 01 00 2D 9C` | 3 | none | A0RM, A2RM, BMRM, BNRM, BZRM, ILRM, M5RM, O3RM, OQRM, OSRM, OXRM, R6RM, U0RM, UERM, UHRM, UKRM, ULRM, UZRM, V7RM, VWRM, W5RM, W7RM, WLRM, X0RM, ZRA2 |
| com m3 return | 30 | `6E 01 00 30 9F` | none | 1 | none | VXRM |
| com m3 set | 2D | `6E 01 00 2D 9C` | none | 2 | none | VXRM |
| com msg 10min | 39 | `6E 01 00 5F CE` | none | 2 | none | ONRM |
| com msg 10min | 47 | `6E 01 00 5F CE` | none | 2 | none | BERM |
| com msg 10min | 49 | `6E 01 00 5F CE` | none | 2 | none | MMRM |
| com msg 10min | 4C | `6E 01 00 5F CE` | none | 2 | none | A3RM |
| com msg 10min | 50 | `6E 01 00 5F CE` | none | 2 | none | R2RM |
| com msg 10min | 5F | `6E 01 00 5F CE` | none | 2 | none | A3RM, A9RM, BERM, BHRM, BIRM, BLRM, BNRM, BZRM, D0RM, D2RM, D4RM, I1RM, IARM, IBRM, M3RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O5RM, O7RM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, R5RM, T5RM, T7RM, U1RM, U2RM, U3RM, U4RM, U5RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, UKRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VDRM, VERM, VFRM, VORM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, Y3RM, ZR50, ZR51 |
| com msg 10min new | A1 | `6E 01 00 A1 10` | none | 2 | none | BGRM |
| com msg 20min | 63 | `6E 01 00 63 D2` | none | 2 | none | A3RM, BERM, BHRM, BIRM, BLRM, BNRM, BZRM, D0RM, I1RM, IBRM, M3RM, MMRM, MRRM, O1RM, O2RM, O3RM, O5RM, O7RM, OPRM, OQRM, ORRM, OSRM, OXRM, OYRM, OZRM, P0RM, P1RM, R5RM, T7RM, U1RM, U2RM, U3RM, U4RM, U5RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, UKRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VFRM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, ZR50, ZR51 |
| com msg 20min new | A2 | `6E 01 00 A2 11` | none | 2 | none | BGRM |
| com msg 30min | 61 | `6E 01 00 61 D0` | none | 2 | none | A3RM, BERM, BHRM, BIRM, BLRM, BNRM, BZRM, D0RM, I1RM, IBRM, M3RM, MLRM, MMRM, MRRM, O0RM, O1RM, O2RM, O3RM, O5RM, O7RM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OZRM, P0RM, P1RM, R5RM, T7RM, U1RM, U2RM, U3RM, U4RM, U5RM, UERM, UFRM, UGRM, UHRM, UKRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, VCRM, VFRM, VRRM, VSRM, VTRM, VYRM, W0RM, W2RM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WJRM, WKRM, WNRM, WSRM, WXRM, X0RM, ZR50, ZR51 |
| com msg 30min new | A3 | `6E 01 00 A3 12` | none | 2 | none | BGRM |
| com msg aroma | 3B | `6E 01 00 3B AA` | none | 2 | none | UYRM, VYRM |
| com msg constant | 3A | `6E 01 00 3A A9` | none | 2 | none | A2RM, O6RM, OMRM, OORM, R6RM |
| com msg constant | 47 | `6E 01 00 3A A9` | none | 2 | none | ONRM, THRM |
| com msg fir intensity new | A4 | `6E 01 00 A4 13` | none | 2 | none | BGRM |
| com msg first intensity dec | 49 | `6E 01 00 4D BC` | none | 2 | none | BERM |
| com msg first intensity dec | 4A | `6E 01 00 4D BC` | none | 2 | none | R2RM |
| com msg first intensity dec | 4D | `6E 01 00 4D BC` | none | 2 | none | I0RM, I4RM, I5RM, MLRM, O0RM, O4RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, VQRM, W5RM, Y3RM, ZRI0 |
| com msg first intensity inc | 42 | `6E 01 00 4C BB` | none | 2 | none | ONRM, THRM |
| com msg first intensity inc | 46 | `6E 01 00 4C BB` | none | 2 | none | BERM |
| com msg first intensity inc | 49 | `6E 01 00 4C BB` | none | 2 | none | R2RM |
| com msg first intensity inc | 4C | `6E 01 00 4C BB` | none | 2 | none | A0RM, A1RM, A2RM, A9RM, AARM, BHRM, BIRM, BLRM, BNRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IIRM, M3RM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O7RM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, R5RM, T5RM, T7RM, U3RM, U4RM, U5RM, U9RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, V0RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, X2RM, Y3RM, ZR50, ZR51, ZRI0 |
| com msg first off old2 | 47 | `6E 01 00 47 B6` | none | 2 | none | OURM, OWRM |
| com msg first on off | 32 | `6E 01 00 32 A1` | none | 2 | none | B1RM, I9RM, O6RM, OMRM, OORM, R6RM, VGRM, WDRM, WERM |
| com msg intensity dec | 35 | `6E 01 00 35 A4` | none | 2 | none | A2RM, BZRM, O2RM, O6RM, OMRM, OORM, R6RM, U1RM, U2RM, UKRM, UZRM, W7RM |
| com msg intensity dec | 4B | `6E 01 00 35 A4` | none | 2 | none | A3RM, MMRM, ONRM, THRM |
| com msg intensity first | 4C | `6E 01 00 67 D6` | none | 2 | none | R2RM |
| com msg intensity first | 67 | `6E 01 00 67 D6` | none | 2 | none | B1RM |
| com msg intensity inc | 34 | `6E 01 00 34 A3` | none | 2 | none | A2RM, BZRM, O2RM, O6RM, OMRM, OORM, R6RM, U1RM, U2RM, UKRM, UZRM, W7RM, WDRM, WERM |
| com msg intensity inc | 48 | `6E 01 00 34 A3` | none | 2 | none | A3RM, MMRM |
| com msg intensity inc | 4A | `6E 01 00 34 A3` | none | 2 | none | ONRM, THRM |
| com msg intensity second old | 4D | `6E 01 00 4D BC` | none | 2 | none | R2RM |
| com msg intensity third | 4E | `6E 01 00 68 D7` | none | 2 | none | R2RM |
| com msg intensity third | 68 | `6E 01 00 68 D7` | none | 2 | none | B1RM |
| com msg mode | 48 | `6E 01 00 48 B7` | none | 2 | none | A0RM, A1RM, A9RM, AARM, B8RM, BGRM, BHRM, BIRM, BLRM, BNRM, BZRM, D0RM, D2RM, D4RM, I1RM, I2RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, M3RM, MRRM, O1RM, O2RM, O3RM, O4RM, O5RM, O7RM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, R5RM, T5RM, T7RM, U1RM, U2RM, U3RM, U4RM, U5RM, UERM, UFRM, UGRM, UHRM, UKRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, UZRM, V0RM, V2RM, V4RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, ZR50, ZR51 |
| com msg mode | 4A | `6E 01 00 48 B7` | none | 2 | none | A3RM, BERM, MMRM |
| com msg off | 47 | `6E 01 00 47 B6` | none | 2 | none | BHRM, BIRM, O4RM, V6RM |
| com msg off2 | 5A | `6E 01 00 5A C9` | none | 2 | none | B1RM |
| com msg off3 | 5E | `6E 01 00 5E CD` | none | 2 | none | A0RM, A1RM, AARM, BGRM, D0RM, D1RM, I1RM, IBRM, IERM, IGRM, P1RM, T7RM, U4RM, U5RM, URRM, UTRM, UYRM, VBRM, VKRM, VLRM, VPRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VZRM, W6RM, W7RM, W9RM, WHRM, WJRM, WKRM, WNRM, WURM, WXRM, ZR50, ZR51 |
| com msg on | 5D | `6E 01 00 5D CC` | `6E 01 00 47 B6` | 3 | none | B9TT |
| com msg on | 5D | `6E 01 00 5D CC` | none | 2 | none | I2RM, I7RM, I8RM, ICRM, IERM, IFRM, IHRM, IIRM, O5RM, V9RM, VIRM, VNRM, WIRM |
| com msg on off | 6F | `6E 01 00 6F DE` | none | 2 | none | Y2RM |
| com msg pulse | 38 | `6E 01 00 38 A7` | none | 2 | none | A2RM, O6RM, OMRM, OORM, R6RM |
| com msg pulse | 46 | `6E 01 00 38 A7` | none | 2 | none | ONRM, THRM |
| com msg sec intensity new | A5 | `6E 01 00 A5 14` | none | 2 | none | BGRM |
| com msg second intensity dec | 4B | `6E 01 00 4F BE` | none | 2 | none | BERM, R2RM |
| com msg second intensity dec | 4F | `6E 01 00 4F BE` | none | 2 | none | B8TT, B9TT, I0RM, I4RM, I5RM, MLRM, O0RM, O4RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, VQRM, W5RM, Y3RM, ZRI0 |
| com msg second intensity inc | 44 | `6E 01 00 4E BD` | none | 2 | none | ONRM, THRM |
| com msg second intensity inc | 48 | `6E 01 00 4E BD` | none | 2 | none | BERM, R2RM |
| com msg second intensity inc | 4E | `6E 01 00 4E BD` | none | 2 | none | A0RM, A1RM, A2RM, A9RM, AARM, B8TT, B9TT, BHRM, BIRM, BLRM, BNRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IERM, IGRM, IHRM, IIRM, M3RM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O7RM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, R5RM, T5RM, T7RM, U3RM, U4RM, U5RM, U9RM, UARM, UBRM, UERM, UFRM, UGRM, UHRM, UJRM, ULRM, UNRM, URRM, UTRM, UVRM, UYRM, V0RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W3RM, W5RM, W6RM, W7RM, W9RM, WARM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WSRM, WURM, WXRM, X0RM, Y3RM, ZR50, ZR51, ZRI0 |
| com msg second on off | 33 | `6E 01 00 33 A2` | none | 2 | none | B1RM, O6RM, OMRM, OORM, R6RM |
| com msg speed dec | 37 | `6E 01 00 37 A6` | none | 2 | none | A2RM, O4RM, O6RM, OMRM, OORM, R6RM |
| com msg speed dec | 49 | `6E 01 00 37 A6` | none | 2 | none | ONRM, THRM |
| com msg speed inc | 36 | `6E 01 00 36 A5` | none | 2 | none | A2RM, O4RM, O6RM, OMRM, OORM, R6RM |
| com msg speed inc | 48 | `6E 01 00 36 A5` | none | 2 | none | ONRM, THRM |
| com msg wave | 39 | `6E 01 00 39 A8` | `6E 01 00 47 B6` | 3 | none | I0RM, I4RM, I5RM, MLRM, O0RM, OTRM, OYRM, U9RM, UARM, UBRM, UJRM, V7RM, ZRI0 |
| com msg wave | 39 | `6E 01 00 39 A8` | none | 2 | none | A2RM, O6RM, OMRM, OORM, R6RM |
| com msg wave | 45 | `6E 01 00 39 A8` | none | 2 | none | ONRM, THRM |
| com msg wave third | 4B | `6E 01 00 4B BA` | none | 2 | none | B8RM |
| com relax | 70 | `6E 01 00 70 DF` | none | 2 | none | BZRM |
| com reset | 62 | `6E 01 00 62 D1` | none | 2 | none | B9TT, I0RM, I4RM, I5RM, M9RM, MLRM, O0RM, OTRM, S9RM, U0RM, U7RM, U8RM, U9RM, UARM, UBRM, UJRM, UNRM, UZRM, V0RM, V6RM, V7RM, VARM, VKRM, ZR21, ZRI0 |
| com second down | 27 | `6E 01 00 27 96` | none | 1 | none | A0RM, A1RM, A2RM, A6RM, A7RM, A8RM, A9RM, AARM, B0RM, B1RM, B6RM, B7RM, B8RM, B8TT, B9TT, BARM, BBRM, BCRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, M3RM, M5RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T5RM, T6RM, T7RM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WPRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, Y2RM, Y3RM, ZR00, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0 |
| com second down | 41 | `6E 01 00 27 96` | none | 1 | none | 6BRM, 6CRM, 6DRM, A3RM, BERM, GMRM, MMRM, ONRM, R2RM, T4RM, THRM, TWRM, TZRM, V3RM |
| com second up | 26 | `6E 01 00 26 95` | none | 1 | none | A0RM, A1RM, A2RM, A6RM, A7RM, A8RM, A9RM, AARM, B0RM, B1RM, B6RM, B7RM, B8RM, B8TT, B9TT, BARM, BBRM, BCRM, BFRM, BGRM, BHRM, BIRM, BJRM, BKRM, BLRM, BMRM, BNRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IARM, IBRM, ICRM, IDRM, IERM, IFRM, IGRM, IHRM, IIRM, M3RM, M5RM, M9RM, MLRM, MRRM, O0RM, O1RM, O2RM, O3RM, O4RM, O5RM, O6RM, O7RM, OMRM, OORM, OPRM, OQRM, ORRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, P9RM, R5RM, R6RM, S9RM, SARM, T0RM, T1RM, T2RM, T5RM, T6RM, T7RM, TLRM, U0RM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UERM, UFRM, UGRM, UHRM, UIRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UXRM, UYRM, UZRM, V0RM, V1RM, V2RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VJRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VQRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W1RM, W2RM, W3RM, W4RM, W5RM, W6RM, W7RM, W8RM, W9RM, WARM, WBRM, WCRM, WDRM, WERM, WGRM, WHRM, WIRM, WJRM, WKRM, WLRM, WNRM, WORM, WPRM, WRRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, WZRM, X0RM, X1RM, X2RM, Y2RM, Y3RM, ZR00, ZR10, ZR11, ZR12, ZR20, ZR21, ZR30, ZR40, ZR50, ZR51, ZR60, ZR70, ZR80, ZRA0, ZRA1, ZRA2, ZRI0 |
| com second up | 36 | `6E 01 00 26 95` | none | 1 | none | 6BRM, 6CRM, 6DRM, GMRM, ONRM, T4RM, THRM, TWRM, TZRM, V3RM |
| com second up | 37 | `6E 01 00 26 95` | none | 1 | none | A3RM, BERM, MMRM, R2RM |
| com second up first down | 22 | `6E 01 00 22 91` | none | 2 | none | OORM, OURM, OWRM |
| com second up once | 3E | `6E 01 00 3E AD` | none | 2 | none | OWRM |
| com sixth down | 74 | `6E 01 00 74 E3` | none | 1 | none | M5RM |
| com sixth up | 73 | `6E 01 00 73 E2` | none | 1 | none | M5RM |
| com snore return | 46 | `6E 01 00 46 B5` | `6E 01 00 69 D8` | 3 | 54 | U3RM |
| com snore return | 46 | `6E 01 00 46 B5` | `6E 01 00 69 D8` | 3 | none | 6DRM, A0RM, A9RM, BFRM, BGRM, BHRM, BIRM, BNRM, D0RM, D1RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, I8RM, I9RM, IBRM, ICRM, IERM, IFRM, IGRM, IHRM, MLRM, O0RM, O1RM, O4RM, O7RM, OPRM, OQRM, OTRM, OYRM, OZRM, S9RM, SARM, T5RM, T7RM, U4RM, U5RM, U7RM, U8RM, UARM, UBRM, UCRM, UGRM, UIRM, UJRM, ULRM, UNRM, UORM, URRM, UTRM, UVRM, UWRM, UXRM, UYRM, V1RM, V4RM, V6RM, V7RM, V9RM, VARM, VBRM, VERM, VGRM, VHRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VSRM, VVRM, VWRM, WDRM, WERM, WIRM, WJRM, WKRM, WLRM, WNRM, WURM, WVRM, WWRM, WXRM, WYRM, X1RM, ZR40, ZR50, ZR51, ZRA0, ZRA2, ZRI0 |
| com snore return | 46 | `6E 01 00 46 B5` | none | 2 | none | P1RM, P2RM, UKRM |
| com third down | 40 | `6E 01 00 40 AF` | none | 1 | none | A0RM, A1RM, A9RM, AARM, BGRM, BIRM, BLRM, BMRM, D4RM, I0RM, I4RM, I5RM, I6RM, I8RM, ICRM, IGRM, M3RM, M5RM, MRRM, O1RM, O5RM, O7RM, ORRM, T0RM, T1RM, T2RM, U2RM, U5RM, U9RM, UARM, UBRM, UERM, UGRM, UHRM, UNRM, URRM, V0RM, V2RM, V7RM, V8RM, V9RM, VCRM, VDRM, VERM, VFRM, VIRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VZRM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WHRM, WIRM, WJRM, WNRM, WSRM, WTRM, WWRM, WXRM, X0RM, Y3RM, ZR11, ZR50, ZR51, ZRA0, ZRI0 |
| com third down | 43 | `6E 01 00 40 AF` | none | 1 | none | BERM, TZRM |
| com third fourth down | 44 | `6E 01 00 44 B3` | none | 1 | none | ORRM, P2RM, VRRM, VZRM, WHRM, WTRM, ZR70, ZR80 |
| com third fourth lean down | 5C | `6E 01 00 5C CB` | none | 1 | none | P2RM, ZR70, ZR80 |
| com third fourth lean up | 5B | `6E 01 00 5B CA` | none | 1 | none | P2RM, ZR70, ZR80 |
| com third fourth up | 43 | `6E 01 00 43 B2` | none | 1 | none | ORRM, P2RM, VRRM, VZRM, WHRM, WTRM, ZR70, ZR80 |
| com third up | 3F | `6E 01 00 3F AE` | none | 1 | none | A0RM, A1RM, A9RM, AARM, BGRM, BIRM, BLRM, BMRM, D4RM, I0RM, I4RM, I5RM, I6RM, I8RM, ICRM, IGRM, M3RM, M5RM, MRRM, O1RM, O5RM, O7RM, ORRM, T0RM, T1RM, T2RM, U2RM, U5RM, U9RM, UARM, UBRM, UERM, UGRM, UHRM, UNRM, URRM, V0RM, V2RM, V7RM, V8RM, V9RM, VCRM, VDRM, VERM, VFRM, VIRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VZRM, W3RM, W9RM, WARM, WBRM, WCRM, WDRM, WHRM, WIRM, WJRM, WNRM, WSRM, WTRM, WWRM, WXRM, X0RM, Y3RM, ZR11, ZR50, ZR51, ZRA0, ZRI0 |
| com third up | 42 | `6E 01 00 3F AE` | none | 1 | none | BERM, TZRM |
| com tv return | 33 | `6E 01 00 58 C7` | none | 2 | none | A3RM, BERM, MMRM, ONRM, R2RM, THRM |
| com tv return | 58 | `6E 01 00 58 C7` | `6E 01 00 64 D3` | 3 | 54 | U3RM |
| com tv return | 58 | `6E 01 00 58 C7` | `6E 01 00 64 D3` | 3 | none | A0RM, A9RM, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BNRM, BZRM, D4RM, I1RM, I2RM, I3RM, IARM, IBRM, IDRM, IGRM, M3RM, M5RM, MRRM, O1RM, O3RM, O4RM, O6RM, O7RM, OMRM, OPRM, OQRM, ORRM, OSRM, OXRM, OZRM, P0RM, P1RM, R5RM, T5RM, T7RM, U1RM, U2RM, U4RM, U5RM, UCRM, UERM, UFRM, UGRM, UIRM, UMRM, UNRM, UORM, UPRM, UQRM, UVRM, UWRM, V0RM, V2RM, V4RM, V8RM, V9RM, VBRM, VCRM, VDRM, VERM, VFRM, VHRM, VKRM, VMRM, VORM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, VZRM, W0RM, W2RM, W3RM, W6RM, WARM, WBRM, WCRM, WIRM, WJRM, WLRM, WNRM, WPRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, Y3RM, ZR10, ZR11, ZR12, ZR50, ZR51, ZRA0 |
| com tv return | 58 | `6E 01 00 58 C7` | none | 2 | none | BJRM, D2RM, O2RM, O5RM, UZRM |
| com ubl off | 75 | `6E 01 00 75 E4` | none | 2 | none | P2RM, ZRA0 |
| com ubl on off | 36 | `6E 01 00 3C AB` | none | 2 | none | BERM, MMRM |
| com ubl on off | 3C | `6E 01 00 3C AB` | `6E 01 00 75 E4` | 3 | none | W3RM, W9RM, WARM, WDRM, WERM |
| com ubl on off | 3C | `6E 01 00 3C AB` | none | 2 | none | A1RM, A9RM, AARM, B1RM, BHRM, BIRM, BJRM, BLRM, BMRM, BNRM, BZRM, D0RM, D1RM, D2RM, D4RM, I0RM, I1RM, I2RM, I4RM, I5RM, I7RM, I8RM, IARM, IBRM, ICRM, IDRM, IERM, IGRM, IHRM, IMRM, M3RM, M5RM, MLRM, MRRM, O0RM, O1RM, O2RM, O4RM, O5RM, O7RM, OMRM, OORM, OPRM, ORRM, OSRM, OTRM, OYRM, OZRM, P0RM, P1RM, P2RM, R5RM, T1RM, T5RM, T7RM, TLRM, U1RM, U2RM, U3RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UFRM, UGRM, UHRM, UJRM, UKRM, ULRM, UMRM, UNRM, UORM, UPRM, UQRM, URRM, UTRM, UVRM, UWRM, UYRM, V0RM, V2RM, V3RM, V4RM, V5RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VPRM, VRRM, VSRM, VTRM, VURM, VVRM, VWRM, VXRM, VYRM, VZRM, W0RM, W2RM, W5RM, W6RM, W7RM, WBRM, WCRM, WHRM, WIRM, WJRM, WKRM, WNRM, WORM, WSRM, WURM, WXRM, WYRM, X0RM, Y2RM, Y3RM, ZR10, ZR11, ZR12, ZR50, ZR51, ZR60, ZRA0, ZRI0 |
| com ubl on off | 43 | `6E 01 00 3C AB` | none | 2 | none | ONRM, THRM |
| com ubl on off | 46 | `6E 01 00 3C AB` | none | 2 | none | A3RM, R2RM |
| com zg return | 34 | `6E 01 00 45 B4` | none | 2 | none | A3RM, BERM, MMRM, R2RM |
| com zg return | 35 | `6E 01 00 45 B4` | none | 2 | none | ONRM, THRM |
| com zg return | 45 | `6E 01 00 45 B4` | `6E 01 00 66 D5` | 2 | none | IARM, IDRM, IERM, IHRM, UORM, UPRM |
| com zg return | 45 | `6E 01 00 45 B4` | `6E 01 00 66 D5` | 3 | 54 | U3RM |
| com zg return | 45 | `6E 01 00 45 B4` | `6E 01 00 66 D5` | 3 | none | 6DRM, A0RM, A1RM, A6RM, A8RM, A9RM, B8RM, B8TT, B9TT, BFRM, BGRM, BHRM, BIRM, BKRM, BLRM, BNRM, BZRM, D0RM, D1RM, D4RM, I0RM, I1RM, I2RM, I3RM, I4RM, I5RM, I7RM, IBRM, ICRM, IGRM, M3RM, M5RM, MLRM, MRRM, O0RM, O1RM, O3RM, O4RM, O6RM, O7RM, OMRM, OPRM, OQRM, OSRM, OTRM, OXRM, OYRM, OZRM, P0RM, P1RM, P2RM, R5RM, S9RM, SARM, T5RM, T7RM, U1RM, U2RM, U4RM, U5RM, U7RM, U8RM, U9RM, UARM, UBRM, UCRM, UERM, UFRM, UGRM, UIRM, UJRM, ULRM, UMRM, UNRM, UQRM, UTRM, UVRM, UWRM, UXRM, UYRM, V0RM, V1RM, V2RM, V4RM, V6RM, V7RM, V8RM, V9RM, VARM, VBRM, VCRM, VDRM, VERM, VFRM, VGRM, VHRM, VIRM, VKRM, VLRM, VMRM, VNRM, VORM, VQRM, VSRM, VTRM, VURM, VVRM, VWRM, VYRM, W0RM, W2RM, W3RM, W5RM, W6RM, WARM, WBRM, WCRM, WDRM, WERM, WIRM, WJRM, WKRM, WLRM, WNRM, WQRM, WSRM, WTRM, WURM, WVRM, WWRM, WXRM, WYRM, X0RM, X1RM, X2RM, Y2RM, Y3RM, ZR10, ZR11, ZR12, ZR21, ZR40, ZR50, ZR51, ZR60, ZRA0, ZRA2, ZRI0 |
| com zg return | 45 | `6E 01 00 45 B4` | none | 1 | none | T4RM |
| com zg return | 45 | `6E 01 00 45 B4` | none | 2 | none | BCRM, BJRM, D2RM, O2RM, O5RM, U0RM, UKRM, UZRM, WORM |
| com zg2 return | 6B | `6E 01 00 6B DA` | `6E 01 00 6A D9` | 3 | 53 | U3RM |
| com zg2 return | 6B | `6E 01 00 6B DA` | `6E 01 00 6A D9` | 3 | none | M9RM |

 </details>
<!-- /generated -->

#### Timing

The generated timing values are milliseconds. Only an actual raw-route
advertised name with trimmed prefix `6BRM` selects the longer refresh. Choosing
that layout manually does not change timing. The Android long counter uses
integer division of its threshold by the refresh, followed by its sending tick;
it is not an exact hardware wall-clock deadline.

HA serializes commands, bounds finite holds by elapsed time, settles in-flight
writes, and sends required release cleanup on cancellation. A late write cannot
cause a backlog of refreshes after the deadline. A sequential two-link pair
cannot sustain a Both hold; single-side actions remain available. No hardware
simultaneous fan-out or automatic stop on disconnect is claimed.

Startup is a direct framed write before notification registration, without an
ACK/authentication gate. Raw connections have no startup write. The query action
sends the optional alarm query only for nonempty layout metadata, then LED and
shared accessory queries in order. The latter retains shared-channel effects
without exposing accessory configuration. Direct settings, queries, RGB and
alarms bypass movement framing and do not append movement release packets.

#### Notifications

The Android five-byte validator checks the current fragment, with a signed sum
compared to an unsigned final byte. Rejected data remains buffered. Exactly ten
accumulated bytes dispatch unchecked. An oversized retained buffer is cleared
when a new fragment starts with the header. HA preserves those within-session
compatibility rules, with a bounded receive budget and callbacks tied to the
current controller/session. Android's retained cross-connection accumulator,
stale-global close and drop/resume worker behavior are not safe HA ownership
rules.

Alarm metadata, the received capability flag and direct alarm navigation are
separate gates. LED support requires an actual current-session reply; saved
menus and default RGB values do not establish device feedback. RGB is one
concatenated write. The phone wheel drops updates while its sender is busy;
HA serializes explicit action requests. Timeout retains the source's byte-pair
folding rather than silently substituting a conventional 16-bit value.

The phone's alarm set ACK reads CURRENT UI choices and the CURRENT global
address, merges tags without removing stale keys, and stores no scheduled time.
Hydration follows layout order with exclusive bed choices and independent
massage choices. Cancel click clears the entire phone preference file before
BLE; cancel ACK removes only the current address's ICON key. These phone-cache
behaviors are not observed hardware schedules. HA keeps request state per bed,
records received events without attributing them to a pending request, and
rejects stale-session effects. It reports no invented angle, battery, firmware
or alarm-time feedback.

#### Services

`adjustable_bed.richmat_resource_bed` exposes `query`, `alarm`, `cancel_alarm`,
`rgb`, `lamp_timeout`, `massage_timer` and `bed_command`. The status entity lists
available alarm action names in layout order. Choose one bed preset and optional
massage actions. The action validates every target before execution, and STOP
fences later writes on every target even while another target is awaiting BLE.

An alarm time selects its next local occurrence, with unset/equal time meaning
the next day. Only the layout-owned combinations are accepted. Light timeout
requests are 0–300 seconds, with zero labelled keep on. The D1RM massage slider
uses its actual 0–5 callback mapping. Requested values are labelled as requests,
not device readback. Other layout actions use their named buttons and the
standard `hold_control` action; held buttons publish current card metadata.

#### Evidence

All four independently accepted row071 app reports establish the shared binding
domain, both movement formats and direct settings builders. The Richmat codec
reproduces their frozen literal vectors; the controllers use each member's
explicit product scope and preserve its source-qualified limits. Hardware
motion, physical axes, memory effects and optional features remain unverified.

### Lady Americana

**App:** [Lady Americana](https://play.google.com/store/apps/details?id=com.richmat.lady_americana) 1.0.2 (3), `com.richmat.lady_americana`

**Status:** ❓ Needs testing.

Behaves as the [resource app family](#lady-americana--acaa--sta-homecare--zero-gravity-family).

#### Setup

Choose Lady Americana and an explicit layout.

#### Controls

Uses the common catalog. The UYRM/VYRM aroma-labelled button is outside its bed scope.

#### Evidence

Accepted row071 Lady Americana 1.0.2 (3), artifact SHA-256 `5feff848f129c77f06faaae3031add398588bc372965f7b9ae51219826eae228`.

### ACAA

**App:** [ACAA](https://play.google.com/store/apps/details?id=com.richmat.acaa) 1.0.4 (5), `com.richmat.acaa`

**Status:** ❓ Needs testing.

Behaves as the [resource app family](#lady-americana--acaa--sta-homecare--zero-gravity-family).

#### Setup

Choose ACAA and an explicit layout.

#### Controls

Retains its accepted UYRM/VYRM shared BED action. This does not expose accessory configuration.

#### Evidence

Accepted row071 ACAA 1.0.4 (5), artifact SHA-256 `3d2760f83ea1f97d4552641b2a3ff2ee4051888888250d01c306be2827af04fe`.

### STA Homecare

**App:** [STA Homecare](https://play.google.com/store/apps/details?id=com.richmat.sta2) 1.0.5 (6), `com.richmat.sta2`

**Status:** ❓ Needs testing.

Behaves as the [resource app family](#lady-americana--acaa--sta-homecare--zero-gravity-family).

#### Setup

Choose STA Homecare and an explicit layout.

#### Controls

The UYRM/VYRM aroma-labelled button is outside its bed scope. The D1RM slider remains a bed action.

#### Evidence

Accepted row071 STA Homecare 1.0.5 (6), artifact SHA-256 `3385bd3b50f777d41ef632c74c4ed5cac00decba4a7ae8d357182c5c0fe65d6c`.

### Zero Gravity

**App:** [Zero Gravity](https://play.google.com/store/apps/details?id=com.richmat.zerogravity) 1.0.3 (4), `com.richmat.zerogravity`

**Status:** ❓ Needs testing.

Behaves as the [resource app family](#lady-americana--acaa--sta-homecare--zero-gravity-family).

#### Setup

Choose Zero Gravity and an explicit layout. Its separate BBRM, OVRM and W8RM
seating layouts are not bed setup choices. This scope does not extend to other
apps or to WLRM from a name alone.

#### Controls

Retains its accepted UYRM/VYRM shared BED action without accessory settings.

#### Evidence

Accepted row071 Zero Gravity 1.0.3 (4), artifact SHA-256 `82ad82b84bfe881af3e74f72accd136b783e5fb0bf62077fc85fcc37ef901678`.
