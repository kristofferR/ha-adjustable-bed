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

1. Create a full backup under **Settings > System > Backups**. Keep it until
   you have decided to stay on v5.
2. Note the integration version you run now, so you can report it if you go
   back.
3. In HACS, open **Adjustable Bed**, choose **Redownload** and select the
   `v5.0.0bN` version. Turn on beta versions for the repository if the beta is
   not listed. Restart Home Assistant and reload the dashboard page.

The minimum Home Assistant version is unchanged: **2026.9.0**.

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
ids from the saved fields, so **Configure**, Repairs and pairing changes keep
them current.

The migration record appears in two places:

- **Diagnostics:** `profile` for a standalone entry; `profile_migration` and
  each side's `profile_id` for a paired entry.
- **Support bundle:** the `profile` section, with the schema version, the
  stored `profile_id`, the migration record and, for a paired entry, each
  side's `profile_id` and whether this bundle targeted it.

## Removed or Renamed Options, Bed Types and Entities

**None.** No bed type, config key, option, action, action field, entity or
unique ID is removed or renamed in v5. The comparison covered `const.py`,
`config_flow.py`, `strings.json`, `translations/en.json`, `services.yaml` and
every entity platform between `main` and `v5`. Byte-identical aliases such as
`okimat` and `okin_uuid` keep their own bed type and their own profile id; the
[profile id design note](design/profile-id.md#aliases) records why each pair
stays separate.

Bed types added to 4.x after v5 branched, such as Good Vibe Sleep, arrive in v5
when `main` is merged into `v5` before each beta.

## New Entities, Attributes and Actions

These are additions. Existing entities keep their names, states and attributes.

| Addition | Where | When it appears |
|----------|-------|-----------------|
| `hold_lease_mode` attribute (`stream` or `latched`) | Covers, held buttons and combined paired controls | Only on beds that declare a renewable hold. No bed declares one in the current beta; the per-family opt-ins are still landing |
| `hold_lease_motor` attribute | Same entities, with the `timed_move` motor they hold | Together with `hold_lease_mode`, where the control maps to a `timed_move` motor |
| `hold_owner` and `hold_generation` fields | `timed_move` and `hold_control` | Always listed. Beds that declare no renewable hold reject them before anything moves; calls without them behave as before. See [Renewable holds](SERVICES.md#renewable-holds) |
| **Estimated positions** menu | **Configure**, one entry per side on a paired bed | Only on beds whose protocol supports [estimated positions](ESTIMATED_POSITIONS.md) |
| Estimated position, set-reference, "I used the remote", saved-position and "Saved positions" entities | `number`, `button` and `sensor` | Only after you enable estimated positions for a motor |
| Saved-position actions (`save_position`, `recall_position`, `set_position_reference`, `lower_to_flat` and five more) | `adjustable_bed.*` | Always listed. They fail with "not enabled" until a motor is calibrated. See [Actions](ESTIMATED_POSITIONS.md#actions) |
| `profile` section | Diagnostics and support bundles | Always. The support bundle's `report_version` is now 2.6 |

## Behavior Changes

**Renewable hold leases ([#483](https://github.com/kristofferR/ha-adjustable-bed/issues/483)).**
`timed_move` and `hold_control` can carry a lease that keeps a held motor
moving while calls renew it, and that ends with the bed's usual release or STOP
when renewals stop. Without `hold_owner` and `hold_generation` both actions run
exactly as before. The scheduler support has landed, but no controller declares
a renewable hold yet, so in this beta no bed changes behavior. See
[Renewable holds](SERVICES.md#renewable-holds) and the
[command lifecycle](COMMAND_LIFECYCLE.md#renewable-hold-leases).

**Dashboard card renewal.** The card renews a lease every 250 ms with a 750 ms
lease, but only for entities that carry `hold_lease_mode`. Every other control
keeps the finite pulses it used in 4.x. Releasing the control, hiding the page
or removing the card stops renewing and sends STOP.

**Calibrated position estimates ([#601](https://github.com/kristofferR/ha-adjustable-bed/issues/601)).**
Opt-in, per motor, for OCTO Standard and the Richmat remote-code profiles. Beds
where you do not enable it are unaffected. With it enabled, the integration
times the moves it sends and never sends a frame of its own; presets, memory
recalls and the physical remote make the estimate unknown. See
[Estimated positions](ESTIMATED_POSITIONS.md).

**Paired-bed routing ([#524](https://github.com/kristofferR/ha-adjustable-bed/issues/524)).**
Paired commands now run through one topology strategy per pair type. A trace
recorded before the change, covering every GATT write, link change and caller
outcome, is reproduced exactly, so no routing behavior is intended to change.
See [topology strategies](design/paired-runtime-and-registry.md#topology-strategies).

**Wire behavior.** The wire snapshot records the bytes, order and timing every
bed type sends for every scripted command. Across the codec migration, one
timing changed: on the legacy `jiecang` and `comfort_motion` bed types, a STOP
during a move now sends its release at once instead of waiting for the next
refresh slot. Frames and their order are unchanged. Every other recorded write
is identical.

**Support bundle command trace ([#794](https://github.com/kristofferR/ha-adjustable-bed/pull/794)).**
Controllers with their own write loops now record those writes in the
bundle's `command_trace`: FSM Relax, Jensen LinOn, the Okin 7-byte, DOT and
N-frame controllers, Reverie, Reverie Nightstand, Reverie Pairlink, Rondure,
Sleep Number and Svane. Bundles from these beds are larger and show the
commands they sent.

**Bluetooth discovery ([#780](https://github.com/kristofferR/ha-adjustable-bed/issues/780)).**
The manifest's Bluetooth matchers are now generated from per-family hints. The
generated list holds exactly the 963 matchers `main` had when v5 branched, in a
different order, so the same advertisements start discovery. See
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

- Guided setup changes: a shared guided-change transaction, split retention and
  pending Repairs ([#792](https://github.com/kristofferR/ha-adjustable-bed/pull/792)),
  then the later setup phases of
  [#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676).
- Merged motor streams for protocols proven to run two motors at once
  ([#795](https://github.com/kristofferR/ha-adjustable-bed/pull/795), for
  [#516](https://github.com/kristofferR/ha-adjustable-bed/issues/516)).
- Per-family renewable hold opt-ins
  ([#483](https://github.com/kristofferR/ha-adjustable-bed/issues/483)).
- The remaining estimated position work: saved positions in the dashboard card
  ([#601](https://github.com/kristofferR/ha-adjustable-bed/issues/601)).
- Setup questions and owned options declared by profiles
  ([#779](https://github.com/kristofferR/ha-adjustable-bed/issues/779)).
- Internal work with no intended user-visible change: test pruning
  ([#781](https://github.com/kristofferR/ha-adjustable-bed/issues/781)) and
  splitting the coordinator and services modules
  ([#782](https://github.com/kristofferR/ha-adjustable-bed/issues/782)).

## Rollback

> [!WARNING]
> **A Home Assistant backup taken before upgrading is the only way back to
> 4.x.** Installing 4.x over v5 leaves every Adjustable Bed entry failing to
> load, because 4.x rejects config entries above schema 4. See
> [Going back to 4.x](TROUBLESHOOTING.md#going-back-to-4x) for what happens
> and how to restore.

Report beta problems in the pinned v5 beta feedback issue, or open a bug report
and choose **v5 beta** as the version. Include diagnostics or a
[support bundle](GETTING_HELP.md#generating-a-support-bundle) and the beta
number.
