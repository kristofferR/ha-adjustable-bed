# Profile ids and the schema 5 migration

Issue [#778](https://github.com/kristofferR/ha-adjustable-bed/issues/778). Code:
[`profile_id.py`](../../custom_components/adjustable_bed/profile_id.py).
Tests: `tests/test_profile_id.py`, `tests/test_profile_id_aliases.py`.

## Why

A config entry identified its bed through several interacting fields:
`bed_type`, `protocol_variant` and five app keys (`jiecang_app_profile`,
`leggett_app_profile`, `logicdata_app_profile`, `malouf_app_profile`,
`vibradorm_app_profile`). Each consumer resolved that combination on its own.
Schema 5 stores the result once, as a **profile id**, and the runtime builds from it.

## The profile id

A profile id names the route an entry runs:

```text
<bed_type>[:<protocol_variant>][@<app_profile>]
```

- The variant appears when one is stored and it is not `auto`. A missing variant
  and `auto` are the same route, because the coordinator has always passed `auto`
  for both.
- The app profile appears for bed types that pick one with an app key, read
  from that key. `leggett_platt` with the `okin` variant reads
  `leggett_app_profile`, like `leggett_okin`.
- `%`, `:` and `@` inside a saved value are escaped as `%25`, `%3A` and `%40`, so
  every id round-trips. Other characters, including spaces, stay as saved.

Examples: `linak`, `keeson:sino`, `reverie:Skye 500`, `jiecang_app@dreamask`,
`leggett_platt:okin@prodigy`.

The id space is every codec family profile route plus every standalone
controller: each bed type, each listed variant and each app key choice, with
families and standalone bed types as registered in `tests/codec_families/`.
A route can still auto-detect inside its family at connect (for example
`keeson` resolves its variant from the advertisement); the id names the
configured route, not the result of that detection.

### API

The surface for later work, such as setup questions per profile
([#779](https://github.com/kristofferR/ha-adjustable-bed/issues/779)):

| Name | Purpose |
|------|---------|
| `resolve_profile_id(data)` | Saved fields to profile id |
| `profile_route(profile_id)` | Profile id to `ProfileRoute(bed_type, variant, app_profile)` |
| `entry_profile_id(data)` | The stored id, or the derived one for data without it |
| `with_profile_ids(data, options)` | Entry data with the entry's and each paired side's id derived |
| `APP_PROFILE_KEYS` | The app key each bed type reads |
| `PROFILE_RESOLVER_VERSION` | Bumped whenever the resolver maps any fields to a different id |

## Saved fields stay

The maintainer's rule for v5: the original `bed_type`, `protocol_variant` and app
keys stay in the entry unchanged, and users see them only in Configure Advanced
and in diagnostics. No saved ID is rewritten. The profile id is stored beside
them.

## Storage

| Where | Key |
|-------|-----|
| Every entry | `profile_id` |
| Each paired side descriptor | `profile_id`, derived from the side's effective config |
| The migrated entry | `profile_migration` |

A side never inherits the parent's id: both keys are excluded from child
inheritance in `pairing.py`. A side's effective config includes parent options,
so an option that changes the side's variant changes its id.

## Migration (4.x to 5.1)

`async_migrate_entry` runs the earlier steps unchanged, then stamps version 5,
minor version 1. The step derives the ids and writes the record:

```json
{
  "from_version": 4,
  "from_minor_version": 3,
  "resolver_version": 1,
  "profile_id": "keeson:sino",
  "fields": {"bed_type": "keeson", "protocol_variant": "sino"},
  "sides": {"left": {"profile_id": "...", "fields": {}}}
}
```

`fields` holds the saved values the ids were derived from; `sides` is present for
paired entries. The migration changes no other data, no options and no entry,
device or entity identity, so actions and automations keep their targets. The
v4 minor steps now run only for version 4 entries.

Schema 5 entries do not load on 4.x, because 4.x rejects versions above 4.
Restoring a Home Assistant backup is the only rollback; there is no downgrade path.

An unpaired side is recreated at the current schema (5.1), so it no longer
re-runs the 4.x minor steps: its saved fields were already migrated with the
pair, and the one-time app profile review is not raised for it again.

### Physical validation

Deferred for the v5 beta ([#783](https://github.com/kristofferR/ha-adjustable-bed/issues/783)).
Proven offline: `tests/test_profile_id.py` migrates every former route (each
bed type, listed variant and app key choice) as a standalone entry, and
examples of both pair modes. It checks that saved fields stay, that entry, device and entity identities
stay, and that every wire snapshot scenario builds the same controller from its
profile id. Needs real reports: upgrades of real 4.x installations, especially
entries from early releases, entries with options saved over several versions
and paired beds, that come up with the same controls and entity IDs. The
`profile_migration` record in diagnostics and support bundles shows what each
upgrade derived.

## Runtime

- **Setup** re-derives the stored ids before any coordinator is created, for
  standalone and paired entries. Configure, repairs, pairing and unpairing edit
  saved fields and then reload, so the stored ids never go stale.
- **Runtime corrections** (a connect-time protocol correction) store the
  corrected id together with the corrected bed type.
- **The coordinator** reads `entry_profile_id(entry.data)` and takes its bed type
  and variant from the id's route. Every bed-type branch and the controller
  factory receive those, so the factory builds from the profile id.
  `_SIMPLE_CONTROLLERS` stays reachable: each of its bed types is its own id.
- **Diagnostics** show the running id and the migration record (`profile` for a
  standalone entry, `profile_migration` and each side's `profile_id` for a pair).
- **Support bundles** carry a `profile` section: the schema version, the stored
  id, the migration record and, for a pair, each side's stored id with whether
  the bundle's address reaches that side (both, for a single-address pair).

`tests/test_profile_id.py` builds every wire snapshot scenario from its profile
id and checks that the factory receives the same arguments and returns the same
controller class.

## Aliases

Two routes may share one profile id only when they are proven equivalent beyond
the wire: setup fields, capabilities, entities and Repairs, each with its own
test. The wire snapshot proves bytes only, and shared names, UUIDs or grouping
prove nothing ([#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676)).

No byte-identical group in the [protocol inventory](protocol-inventory.md) passes
yet, so every route keeps its own id. `tests/test_profile_id_aliases.py` pins one
non-wire difference per group:

| Group | Kept separate because |
|-------|-----------------------|
| `comfort_motion`, `jiecang` | Repairs: the app profile review lists the LOGICDATA app for `comfort_motion` only. Device manufacturer: "Comfort Motion" against "Jiecang". |
| `okimat`, `okin_uuid` | Setup offers only `okin_uuid`. Device manufacturer: "Okimat" against "Okin". |
| `dewertokin`, `okin_handle` | Repairs: the review lists apps for `dewertokin` only. Setup offers only `okin_handle`. Device manufacturer differs. |
| `nectar`, `okin_7byte` | Setup offers only `okin_7byte`. Device manufacturer: "Nectar" against "Okin". |
| `mattressfirm`, `okin_nordic` | Setup offers only `okin_nordic`. Device manufacturer: "MattressFirm" against "Okin". |
| `ergomotion`, `keeson:ergomotion`; `serta`, `keeson:serta` | Capabilities: only the bed types mint their controller and entities before the first connection. Device manufacturer: "Ergomotion" and "Serta" against "Keeson". |
| `leggett_okin`, `leggett_platt`, `leggett_platt:okin` | Setup offers only `leggett_okin`. `leggett_platt` without a variant chooses its controller from GATT at connect. |
| `leggett_gen2`, `leggett_platt:gen2` | Setup offers only `leggett_gen2`. |
| `keeson:americanstar`, `avanti_bases`, `bedsense_bases`, `dynasty_bases`, `maxcoil_una` | Setup fields: Avanti Bases hides more generic fields; AMERICANSTAR and Avanti keep the motor count per side. Each app has its own setup label. |
| `richmat_best_mattress:model_bfrm`, `richmat_blvd_home:model_bfrm` | Two bed types built for different apps, with their own setup labels. |
| `fsm_relax`, `fsm_relax:massage_light` | Already one id, `fsm_relax`: the light and massage flags are settings, not routes. |

Merging a group later means: remove each difference or prove it immaterial with a
test, map the alias to the canonical id in `resolve_profile_id`, bump
`PROFILE_RESOLVER_VERSION`, and list the merge on the v5 breaking changes page
([#783](https://github.com/kristofferR/ha-adjustable-bed/issues/783)). Setup then
re-derives the stored id; the saved fields still stay.
