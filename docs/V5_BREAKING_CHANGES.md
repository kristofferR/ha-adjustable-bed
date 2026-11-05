# v5 Breaking Changes

Version 5 rebuilds how the integration encodes bed protocols: every protocol
family now runs on a shared wire codec with one typed profile per app or route.
It also changes some runtime behavior that offline tests cannot prove on real
beds. This page lists what changes for an existing 4.x installation. Each
`v5.0.0bN` beta's release notes link here, and the page is kept in step with
what each beta ships.

> [!CAUTION]
> **Take a Home Assistant backup before you install a v5 beta.** v5 migrates
> every Adjustable Bed config entry to schema 5, and 4.x refuses to load
> schema 5 entries. Restoring a Home Assistant backup taken before the upgrade
> is the only way back to 4.x. There is no downgrade path. See
> [Going back to 4.x](TROUBLESHOOTING.md#going-back-to-4x).

## Contents

- [Before You Upgrade](#before-you-upgrade)
- [Config Entry Migration (Schema 5.1)](#config-entry-migration-schema-51)
- [Removed or Renamed Options, Bed Types and Entities](#removed-or-renamed-options-bed-types-and-entities)
- [New Entities, Attributes and Actions](#new-entities-attributes-and-actions)
- [Behavior Changes](#behavior-changes)
- [Moved Documentation](#moved-documentation)
- [Still Landing Before 5.0.0](#still-landing-before-500)
- [Rollback](#rollback)

## Before You Upgrade

**v5 requires Home Assistant 2026.11.0 or newer**, where 4.x needs 2026.9.0. v5
uses that release's native conditional setup fields, repairs that follow their
entry, migration retry without a restart, and faster Bluetooth wake-up.

1. Update Home Assistant to 2026.11.0 or newer and check that it runs. From
   2026.11, custom integrations install through the built-in
   **Marketplace** under **Settings > Marketplace**.
2. Create a full backup under **Settings > System > Backups**. Keep it until
   you have decided to stay on v5.
3. Note the integration version you run now, so you can report it if you go
   back.
4. Under **Settings > Marketplace**, open **Adjustable Bed**. In its three-dots
   menu, choose **Include pre-releases** and confirm with **Include**. The beta
   then shows as an update under **Settings > Updates**. To pick one beta
   instead, choose **Install another version** in the same menu, select the
   `v5.0.0bN` version (marked **Pre-release**) and select **Update**.
5. Restart Home Assistant and reload the dashboard page.

To stop receiving betas, choose **Exclude pre-releases** in the same menu. An
installed beta stays until a newer stable version is out.

## Config Entry Migration (Schema 5.1)

On the first start, every config entry at schema 4 or older migrates to schema
5, minor version 1. Earlier 4.x steps still run first for entries that missed
them. The schema 5 step stores the profile id each entry runs, which is the one
name for the route its bed type, protocol variant and app key used to select
together. The [profile id design note](design/profile-id.md) describes the
format.

| Field | What the migration does |
|-------|-------------------------|
| `bed_type` | Unchanged |
| `protocol_variant` | Unchanged |
| App keys (`jiecang_app_profile`, `leggett_app_profile`, `logicdata_app_profile`, `malouf_app_profile`, `vibradorm_app_profile`) | Unchanged |
| Every other saved field and option | Unchanged |
| Paired side descriptors (`pair_children`) | Unchanged, except that each side gains its own `profile_id` |
| `profile_id` | **Added.** Derived from the saved fields above, for example `keeson:sino` or `jiecang_app@dreamask`. A paired side's id comes from that side's own settings and never from the parent |
| `profile_migration` | **Added.** A record of the migration: `from_version`, `from_minor_version`, `resolver_version`, the new `profile_id`, the saved `fields` it was derived from and, for a paired entry, the same for each side under `sides` |
| Schema version | Becomes 5.1 |

The migration changes no entry, device or entity identity, so dashboards,
automations and actions keep their targets. Entries created on v5 have a
`profile_id` but no `profile_migration`. Every later setup re-derives the stored
ids from the saved fields, so **Configure**, **Reconfigure**, Repairs and
pairing changes keep them current.

The migration record appears in two places:

- **Diagnostics:** `profile` for a standalone entry; `profile_migration` and
  each side's `profile_id` for a paired entry.
- **Support bundle:** the `profile` section, with the schema version, the
  stored `profile_id`, the migration record and, for a paired entry, each
  side's `profile_id` and whether this bundle targeted it.

## Removed or Renamed Options, Bed Types and Entities

**None.** No bed type, saved config key, option, action, action field, entity
or unique ID is removed or renamed in v5. The comparison covered `const.py`,
`config_flow.py`, `strings.json`, `translations/en.json`, `services.yaml` and
every entity platform between `main` and `v5`. Byte-identical aliases such as
`okimat` and `okin_uuid` keep their own bed type and their own profile id; the
[profile id design note](design/profile-id.md#aliases) records why each pair
stays separate.

The forms that write those keys did change. Several families' rows now sit
behind one app question, fresh setup no longer shows a separate protocol
variant field, and the Leggett app profile step is part of the Leggett & Platt
question. **Setup and Configure** under [Behavior Changes](#behavior-changes)
describes each change. Every saved ID still loads unchanged.

v5 includes every bed type in 4.3.0. Good Vibe Sleep and the eShine E2000,
E3000/E3100 and E5000 app arrived through
[#816](https://github.com/kristofferR/ha-adjustable-bed/pull/816), and every
scripted command on them sends the same bytes as on `main`. The classic Richmat
apps (Avocado Eco Base, CoasterSleep, Forty Winks, Milemont and Superior,
[#825](https://github.com/kristofferR/ha-adjustable-bed/pull/825)) arrived on
`main` after 4.3.0 and are included too, with their layout asked on the profile
setup step.

## New Entities, Attributes and Actions

These are additions. Existing entities keep their names, states and attributes.

| Addition | Where | When it appears |
|----------|-------|-----------------|
| `hold_lease_mode` attribute (`stream` or `latched`) | Covers, held buttons and combined paired controls | Only on beds that declare a renewable hold, listed under [Behavior Changes](#behavior-changes). A combined paired control carries it only when both sides declare the same mode |
| `hold_lease_motor` attribute | Same entities, with the `timed_move` motor they hold | Together with `hold_lease_mode`, where the control maps to a `timed_move` motor |
| `hold_owner` and `hold_generation` fields | `timed_move` and `hold_control` | Always listed. Beds that declare no renewable hold reject them before anything moves; calls without them behave as before. See [Renewable holds](SERVICES.md#renewable-holds) |
| **Estimated positions** menu | **Configure**, one entry per side on a paired bed | Only on beds whose protocol supports [estimated positions](ESTIMATED_POSITIONS.md) |
| Estimated position, set-reference, "I used the remote", saved-position and "Saved positions" entities | `number`, `button` and `sensor` | Only after you enable estimated positions for a motor |
| Saved-position actions (`save_position`, `recall_position`, `set_position_reference`, `lower_to_flat` and five more) | `adjustable_bed.*` | Always listed, and useful only once estimated positions are enabled. [Actions](ESTIMATED_POSITIONS.md#actions) gives each action's requirements |
| **Tap to start and stop movement** card option (`tap_to_move`) | Dashboard card editor, **Motors** | Off by default. With it on, a tap on a motor arrow starts the motor and the next tap stops it ([#609](https://github.com/kristofferR/ha-adjustable-bed/issues/609)). See [Tap to move](../README.md#tap-to-move) |
| **Change app or layout** menu item | **Configure** | On Vibradorm, Jiecang, Okin, Keeson, Solace and Leggett & Platt entries. It replaces Vibradorm's **Choose Vibradorm app and remote** item and points to **Reconfigure** |
| Profile id and migration record | Diagnostics and support bundles | Diagnostics: `profile` for a standalone entry, `profile_migration` and each side's `profile_id` for a paired entry. Support bundles of a configured bed: `profile` (empty for a raw-address capture). The support bundle's `report_version` is now 2.6 |

## Behavior Changes

**Renewable hold leases ([#483](https://github.com/kristofferR/ha-adjustable-bed/issues/483)).**
`timed_move` and `hold_control` can carry a lease that keeps a held motor
moving while calls renew it, and that ends with the bed's usual release or STOP
when renewals stop. Without `hold_owner` and `hold_generation` both calls stay
finite, as in 4.x, though **Concurrent motors** below still applies to
`timed_move`. A bed declares a hold only where its app is proven to hold a
key until release, either by streaming it (`stream`) or by one start frame and
a STOP (`latched`). One stream hold ends after 30 s in total and one latched
hold after 10 s, however often it is renewed. See
[Renewable holds](SERVICES.md#renewable-holds), the
[command lifecycle](COMMAND_LIFECYCLE.md#renewable-hold-leases) and the
[evidence matrix](design/execution-capabilities.md#evidence-matrix) for each
row's evidence.

| Hold | Beds |
|------|------|
| `stream` | Okin N-frame: Leggett Okin (Prodigy 2L, Prodigy 2, Prodigy CE, U Series), Customatic (Clarity, Jerome's, Remedy, Z-230, Z-280), the Okin CST apps including Nectar Move, Jordan's Serenity and Tranquil, SIMMONS, AdjustableM5X4, Adjustable bed (Lumbar) and Sleepy's BOX25 ([#800](https://github.com/kristofferR/ha-adjustable-bed/pull/800), [#820](https://github.com/kristofferR/ha-adjustable-bed/pull/820)) |
| `stream` | Jiecang: ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD and the three LOGICDATA apps ([#799](https://github.com/kristofferR/ha-adjustable-bed/pull/799)) |
| `stream` | Keeson: the K1 profiles with stream evidence, such as Ergomotion, Serta, Restonic, INNOVA, the ORE apps, SBI, Cool Base, Glideaway Motion and AdjustaMattress P1/P2, plus every cluster033 app layout and every Ergomotion 4.0 style ([#819](https://github.com/kristofferR/ha-adjustable-bed/pull/819)) |
| `stream` | Richmat: every `richmat` remote-code route, the Richmat MH apps, L&P MlRM, HJBed, and RMControl products whose motor controls all sustain ([#822](https://github.com/kristofferR/ha-adjustable-bed/pull/822)) |
| `stream` | Malouf and Lucid apps and the Malouf new and legacy Okin routes ([#823](https://github.com/kristofferR/ha-adjustable-bed/pull/823)); Limoss Remote and FSM Relax ([#802](https://github.com/kristofferR/ha-adjustable-bed/pull/802)); Okin 5A ELEVATE ([#813](https://github.com/kristofferR/ha-adjustable-bed/pull/813)) |
| `stream` | Linak, OCTO Standard, eShine, the eShine E2000/E3000/E3100/E5000 app, TiMOTION AHF, the Vibradorm app profiles, V-MAT Basic, StarCode M1X12 and M5X5, L&P Gen2, Jensen JMC400, FurniMove, the Sleepy's Elite app and Good Vibe Sleep's sustained-press controls ([#815](https://github.com/kristofferR/ha-adjustable-bed/pull/815), [#831](https://github.com/kristofferR/ha-adjustable-bed/pull/831)); Svane Remote on both its routes ([#827](https://github.com/kristofferR/ha-adjustable-bed/pull/827)); Jensen LinOn, the Svane `jensen_linon` route ([#843](https://github.com/kristofferR/ha-adjustable-bed/pull/843)) |
| `latched` | Solace name routes (HomeKobo, Sealy MotionFlex and Sweet Night, not legacy S4-Y or unidentified names) and Woosa Sleep, BedSense, Reverie, Kaidi (except Floyd and dual-seat beds), iSleep and Remacro ([#821](https://github.com/kristofferR/ha-adjustable-bed/pull/821)) |
| None | Every other bed and route keeps the finite pulses it used in 4.x. These include routes the evidence does not cover (Comfort Motion and legacy Jiecang, BedTech, AdjustaMattress P3/P4, legacy Limoss, generic Vibradorm, Nectar and Mattress Firm on Okin 5A, `okimat`), routes with nothing a lease could renew (L&P legacy, Motion Bed, dual-seat Kaidi), routes without a complete report (Kaidi Floyd, Solace S4-Y, OCTO Star2), and Good Vibe Sleep's short, long and short-and-long presses |

**Dashboard card renewal.** The card renews a lease every 250 ms with a 750 ms
lease, but only for entities that carry `hold_lease_mode`. Every other control
keeps the finite pulses it used in 4.x. Releasing the control, hiding the page
or removing the card stops renewing and sends STOP.

**Concurrent motors ([#516](https://github.com/kristofferR/ha-adjustable-bed/issues/516)).**
On a standalone bed whose app is proven to hold independent motors together,
`timed_move` calls on different motors now run on one merged stream, so two
controls held at once move both motors. In 4.x the second motor's command
replaced the first. This covers Leggett Okin Prodigy CE (head, feet, pillow and
lumbar) and U Series (head, feet and pillow)
([#814](https://github.com/kristofferR/ha-adjustable-bed/pull/814)), and Svane
Remote head and feet on both its routes
([#827](https://github.com/kristofferR/ha-adjustable-bed/pull/827)). Every
`timed_move` on these motors joins the stream, even a single move. A motor's own
Stop ends only that motor. Paired beds, `hold_control` and every other bed stay
serialized, including Leggett Okin Prodigy 2 and 2L
([#835](https://github.com/kristofferR/ha-adjustable-bed/pull/835)) and
Customatic. See the
[merged stream](COMMAND_LIFECYCLE.md#merged-stream-for-concurrent-motors).

**Calibrated position estimates ([#601](https://github.com/kristofferR/ha-adjustable-bed/issues/601)).**
Opt-in, per motor, for OCTO Standard and the Richmat remote-code profiles. Beds
where you do not enable it are unaffected. **Configure > Estimated positions**
calibrates each motor's travel times. With it enabled, the integration times
the moves it sends and never sends a frame of its own. Presets and memory
recalls make the estimate unknown. The integration cannot see the physical
remote, so press **I used the remote** after using it. The dashboard card shows
estimates as "≈ 42%", adds a **Saved positions** section and a **Set
reference** dialog, and shows an alert when estimates need calibrating or a
position is unknown or unconfirmed after a restart. See
[Estimated positions](ESTIMATED_POSITIONS.md) and
[In the card](ESTIMATED_POSITIONS.md#in-the-card).

**Setup and Configure ([#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676)).**
For five families, a bed's name and Bluetooth services cannot tell its apps
apart, so setup and **Reconfigure** now ask one question: which app or remote
controls this bed. **Keep** saves the route detection chose, or leaves an
existing entry unchanged. Rows that left the top-level list are reached through
the question, and a saved entry shows its own route's label.

| Family | What setup shows now |
|--------|----------------------|
| Jiecang ([#830](https://github.com/kristofferR/ha-adjustable-bed/pull/830)) | One Jiecang row instead of three. The question offers ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD, Comfort Motion, or a remote without an app, which then asks its motor count. The apps no longer show angle sensing, which they always keep off, and **Configure** no longer shows their layout and transport ([#838](https://github.com/kristofferR/ha-adjustable-bed/pull/838)) |
| Okin ([#832](https://github.com/kristofferR/ha-adjustable-bed/pull/832)) | The FurniMove row becomes the Okin row; Okin UUID, Okin DOT and RF ECO BT leave the top-level list. The question offers the FurniMove / OKIN Smart Remote app, an Okimat or OKIN handset code, a DOT remote, the RF ECO BT stair lift, and the apps the app review suggests for an Okimat route. You don't need an RF remote to answer |
| Keeson ([#833](https://github.com/kristofferR/ha-adjustable-bed/pull/833)) | The Keeson, Ergomotion, Serta Motion Perfect, Okin FFE and Cool Base rows ask one question covering the Keeson apps and remote routes. Restonic remote A and B become one Restonic BT row that asks the remote style. The ORE apps and INNOVA ask for the app's 2M, 3M or 4M screen instead of a motor count |
| Solace ([#836](https://github.com/kristofferR/ha-adjustable-bed/pull/836)) | QMS and similar names ask: HomeKobo, Sealy MotionFlex or Sweet Night; Woosa Sleep; Motion Bed; or BedSense. Woosa Sleep shows a note on its own controls before you choose it |
| Leggett & Platt ([#837](https://github.com/kristofferR/ha-adjustable-bed/pull/837)) | The Leggett Okin row becomes the L&P row; the Gen2 and WiLinke rows leave the top-level list. The question offers Prodigy CE, Prodigy 2, Prodigy 2L or U Series; LP Control with an LP BED receiver or an LP Comfort Connect base; the L&P Adjustable Base app with an MlRM base or a QRRM remote; and the L&P legacy app. It replaces the separate Leggett app profile step |

Across all bed types ([#826](https://github.com/kristofferR/ha-adjustable-bed/pull/826)):

- Fresh setup no longer shows a separate protocol variant field. An app entry
  always sets its own route. A bed type with several receiver routes lists them
  in a collapsed **Advanced: receiver route** section, or in a short **Receiver
  route** step when you choose another bed type.
- The bed type list is searchable by label, including app names such as
  MotoSleep / Power Bob. Compatibility IDs such as `okimat` and `dewertokin`
  show friendly labels, and **Configure** adds "(saved as `<id>`)".
- Motor count and pulse delay are no longer asked for the Jiecang, Malouf and
  LOGICDATA apps, whose layout or model sets them.

For existing beds ([#792](https://github.com/kristofferR/ha-adjustable-bed/pull/792)
and the family PRs above):

- **Configure** on a Vibradorm, Jiecang, Okin, Keeson, Solace or Leggett & Platt
  entry keeps routine settings but refuses an app, layout, handset or route
  change and points to **Reconfigure**. In 4.x, Configure saved these changes
  directly for every family except Vibradorm.
- **Reconfigure** asks the family question, checks the chosen setup on a
  released link where the family has endpoint or pairing requirements, and
  lists the controls that are added and removed, with the automations and
  scripts that use a removed control, before **Apply this change** saves it.
  [Changing the app or layout](CONFIGURATION.md#changing-the-app-or-layout-of-an-existing-bed)
  describes the steps.
- App profile repairs stay open when they hand you to **Configure** or the
  guided change, until you save a change or keep the current setup. **Keep**
  is remembered with the apps it showed, so the repair returns only when a
  later release offers an app you were not shown. For the families above, the
  repair opens the guided change.
- Splitting a combined bed keeps the Bluetooth adapter or proxy, idle
  disconnect and disconnect-after-command settings used while combined, instead
  of restoring the ones from before. Bed type, app profile and side settings
  are restored as before.

**Paired-bed routing ([#524](https://github.com/kristofferR/ha-adjustable-bed/issues/524)).**
Paired commands now run through one topology strategy per pair type. A trace
recorded before the change, covering every GATT write, link change and caller
outcome, is reproduced exactly, so no routing behavior is intended to change.
See [topology strategies](design/paired-runtime-and-registry.md#topology-strategies).

**Coordinator and services modules ([#782](https://github.com/kristofferR/ha-adjustable-bed/issues/782)).**
The coordinator's bond, connection and position code and the family actions
moved into their own modules. Every action registers with the same name,
handler and schema as before, and the coordinator keeps its methods and its log
name (`custom_components.adjustable_bed.coordinator`), so no behavior is
intended to change.

**Wire behavior.** The wire snapshot records the bytes, order and timing every
bed type sends for every scripted command. Since it was added, two recorded
timings changed, and the other updates only added scenarios:

- `jiecang`, `comfort_motion`: a STOP during a move sends its release at once
  instead of at the next refresh slot. Frames and their order are unchanged
  ([#750](https://github.com/kristofferR/ha-adjustable-bed/pull/750)).
- `svane` (Jensen LinOn route): a STOP during a held move reaches the bed at
  once instead of after the rest of its 800 ms refresh interval. Bytes and
  characteristics are unchanged
  ([#843](https://github.com/kristofferR/ha-adjustable-bed/pull/843)).
- `leggett_okin`, `leggett_platt` (default and `okin` routes): a new
  `release_stream` scenario, which sends the existing four-zero release
  ([#814](https://github.com/kristofferR/ha-adjustable-bed/pull/814)).
- `svane` (both Svane Remote routes): a new `release_stream` scenario, which
  writes nothing
  ([#827](https://github.com/kristofferR/ha-adjustable-bed/pull/827)).
- `ergomotion_4`, `goodvibe`, `eshine_okin`: new scenarios for bed types that
  arrived from `main`, byte-identical to `main`
  ([#767](https://github.com/kristofferR/ha-adjustable-bed/pull/767),
  [#816](https://github.com/kristofferR/ha-adjustable-bed/pull/816)).

These deliberate changes are outside the scripted commands:

- Leggett Okin Prodigy CE and U Series: a `timed_move` sends the four-zero
  release once on the merged stream, where 4.x sent it twice
  ([#814](https://github.com/kristofferR/ha-adjustable-bed/pull/814)).
- Keeson Restonic A and B: the touch-up release frame now goes out even when
  the move is cancelled more than once
  ([#785](https://github.com/kristofferR/ha-adjustable-bed/pull/785)).
- Renewable holds send their own sequences only when a lease is requested.
  The merged stream carries every `timed_move` on a declared motor, and
  composes new frames only when two of those motors move together, as
  described above.

**Support bundle command trace ([#786](https://github.com/kristofferR/ha-adjustable-bed/pull/786), [#794](https://github.com/kristofferR/ha-adjustable-bed/pull/794)).**
Controllers with their own write loops now record those writes in the
bundle's `command_trace`: the Jiecang family, L&P MlRM, FSM Relax, Jensen
LinOn, the Okin 5A, DOT and N-frame controllers, Reverie, Reverie
Nightstand, Reverie Pairlink, Rondure, Sleep Number and Svane. Bundles from
these beds are larger and show the commands they sent. Reverie Pairlink frames
are recorded as `**REDACTED**` with their length only, because they carry
credentials.

**Bluetooth discovery ([#780](https://github.com/kristofferR/ha-adjustable-bed/issues/780)).**
The manifest's Bluetooth matchers are now generated from per-family hints. The
generated list holds exactly the 963 matchers that 4.3.0 ships, in a different
order, so the same advertisements start discovery. See
[discovery hints](design/discovery-hints.md).

## Moved Documentation

Per-bed guides that share a wire codec were folded into that codec's guide,
with one section per profile. Old links to these files on the `v5` branch
return 404.

| Old guide | New section |
|-----------|-------------|
| `beds/adjustable-lumbar.md` | [Okin N-frame: Adjustable bed (Lumbar)](beds/okin-nframe.md#adjustable-bed-lumbar) |
| `beds/adjustamattress.md` | [Keeson: AdjustaMattress](beds/keeson.md#adjustamattress) |
| `beds/bedsense.md` | [FFFF frame: BedSense](beds/ff_frame.md#bedsense) |
| `beds/bedtech.md` | [Richmat: BedTech](beds/richmat.md#bedtech) |
| `beds/bf-cherish.md` | [Keeson: BF and Cherish](beds/keeson.md#bf-and-cherish) |
| `beds/comfort-enhancements.md` | [Keeson: Comfort Enhancements](beds/keeson.md#comfort-enhancements) |
| `beds/comfort-motion.md` | [Jiecang: Comfort Motion app](beds/jiecang.md#comfort-motion-app) |
| `beds/coolbase.md` | [Keeson: Cool Base](beds/keeson.md#cool-base) |
| `beds/customatic.md` | [Okin N-frame: Customatic family](beds/okin-nframe.md#customatic-family) |
| `beds/customatic-z-series.md` | [Okin N-frame: Customatic Z-Series](beds/okin-nframe.md#customatic-z-series) |
| `beds/dewertokin.md` | [Okin N-frame: DewertOkin](beds/okin-nframe.md#dewertokin) |
| `beds/doublesleep.md` | [Okin N-frame: OKIN SleepEase](beds/okin-nframe.md#okin-sleepease) |
| `beds/ergo-slim.md` | [Keeson: Ergo Slim](beds/keeson.md#ergo-slim) |
| `beds/ergomotion.md` | [Keeson: Ergomotion app](beds/keeson.md#ergomotion-app) |
| `beds/ergomotion-4.md` | [Keeson: Ergomotion 4.0](beds/keeson.md#ergomotion-40) |
| `beds/fsm_relax.md` | [Limoss: FSM Relax](beds/limoss.md#fsm-relax) |
| `beds/glideaway-motion.md` | [Keeson: Glideaway Motion](beds/keeson.md#glideaway-motion) |
| `beds/hjbed.md` | [Richmat: HJBed](beds/richmat.md#hjbed) |
| `beds/jiecang-app.md` | [Jiecang: Dream app family](beds/jiecang.md#dream-app-family) |
| `beds/leggett-okin.md` | [Okin N-frame: Leggett Okin family](beds/okin-nframe.md#leggett-okin-family) |
| `beds/limoss-remote.md` | [Limoss: Limoss Remote](beds/limoss.md#limoss-remote) |
| `beds/logicdata-app.md` | [Jiecang: LOGICDATA app family](beds/jiecang.md#logicdata-app-family) |
| `beds/malouf-app.md` | [Malouf: Malouf Base / Lucid Base family](beds/malouf.md#malouf-base--lucid-base-family) |
| `beds/mattressfirm.md` | [Okin 5A: Mattress Firm 900 / iFlex](beds/okin-5a.md#mattress-firm-900--iflex) |
| `beds/motion_bed.md` | [FFFF frame: Motion Bed](beds/ff_frame.md#motion-bed) |
| `beds/nectar.md` | [Okin 5A: Nectar](beds/okin-5a.md#nectar) |
| `beds/okimat.md` | [Okin N-frame: Okimat](beds/okin-nframe.md#okimat) |
| `beds/okin-64bit.md` | [Okin N-frame: Okin 64-Bit](beds/okin-nframe.md#okin-64-bit) |
| `beds/okin-cb35.md` | [Okin 5A: Sealy Posturematic (CB35)](beds/okin-5a.md#sealy-posturematic-cb35) |
| `beds/okin-cst.md` | [Okin N-frame: Okin CST](beds/okin-nframe.md#okin-cst) |
| `beds/okin-dot.md` | [Okin N-frame: Okin DOT](beds/okin-nframe.md#okin-dot) |
| `beds/okin-rf-eco-bt.md` | [Okin N-frame: RF ECO BT stair lift](beds/okin-nframe.md#rf-eco-bt-stair-lift) |
| `beds/omazz-adjusto-iii.md` | [Keeson: Omazz Adjusto III](beds/keeson.md#omazz-adjusto-iii) |
| `beds/ore-comfort-bed.md` | [Keeson: ORE comfort-bed profiles](beds/keeson.md#ore-comfort-bed-profiles) |
| `beds/q-plus-adjustable-remote.md` | [Keeson: Q-Plus Adjustable Remote](beds/keeson.md#q-plus-adjustable-remote) |
| `beds/richmat-classic-apps.md` | [Richmat: Classic Richmat apps](beds/richmat.md#classic-richmat-apps) |
| `beds/richmat-mh.md` | [Richmat: Richmat MH apps](beds/richmat.md#richmat-mh-apps) |
| `beds/rmcontrol.md` | [Richmat: RMControl](beds/richmat.md#rmcontrol) |
| `beds/rondure.md` | [Keeson: Rondure](beds/keeson.md#rondure) |
| `beds/row-control.md` | [Keeson: ROW Control](beds/keeson.md#row-control) |
| `beds/sbi.md` | [Keeson: SBI / Q-Plus (Costco)](beds/keeson.md#sbi--q-plus-costco) |
| `beds/scott-living.md` | [Keeson: Scott Living](beds/keeson.md#scott-living) |
| `beds/serenity.md` | [Okin N-frame: Jordan's Serenity](beds/okin-nframe.md#jordans-serenity) |
| `beds/serta.md` | [Keeson: Serta](beds/keeson.md#serta) |
| `beds/serta-mp-remote.md` | [Keeson: Serta MP Remote](beds/keeson.md#serta-mp-remote) |
| `beds/simmons.md` | [Okin N-frame: SIMMONS](beds/okin-nframe.md#simmons) |
| `beds/solace.md` | [FFFF frame: Solace name routes](beds/ff_frame.md#solace-name-routes) |
| `beds/star-elevate.md` | [Okin 5A: DewertOkin ELEVATE](beds/okin-5a.md#dewertokin-elevate) |
| `beds/starcode-abm5-4.md` | [Okin N-frame: AdjustableM5X4](beds/okin-nframe.md#adjustablem5x4) |
| `beds/tempur-au.md` | [Keeson: TEMPUR AU](beds/keeson.md#tempur-au) |
| `beds/tempur-curve.md` | [Keeson: Tempur Curve](beds/keeson.md#tempur-curve) |
| `beds/tranquil.md` | [Okin N-frame: Jordan's Tranquil](beds/okin-nframe.md#jordans-tranquil) |
| `beds/woosa.md` | [FFFF frame: Woosa Sleep](beds/ff_frame.md#woosa-sleep) |

## Still Landing Before 5.0.0

These are planned for v5 but are not in every beta yet. This list shrinks as
they land.

- Guided setup for the remaining families of
  [#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676): Malouf,
  Jensen and Svane, Limoss, LOGICDATA, Richmat and RMControl, Sleepy's,
  Customatic and Star, Remacro, Reverie and Sleep Number.
- Setup questions and owned options declared by profiles for the families
  beyond Jiecang, and a review of which saved config keys are still needed
  ([#779](https://github.com/kristofferR/ha-adjustable-bed/issues/779)).

## Rollback

> [!WARNING]
> **A Home Assistant backup taken before upgrading is the only way back to
> 4.x.** Installing 4.x over v5 leaves every Adjustable Bed entry failing to
> load, because 4.x rejects config entries above schema 4. See
> [Going back to 4.x](TROUBLESHOOTING.md#going-back-to-4x) for what happens
> and how to restore.

Report beta problems in the pinned v5 beta feedback issue, or open a bug report
and choose **v5 beta** as the release. Include diagnostics or a
[support bundle](GETTING_HELP.md#generating-a-support-bundle) and the beta
number.
