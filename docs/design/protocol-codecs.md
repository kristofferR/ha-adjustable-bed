# Protocol codecs and app profiles

Ref #742, #744 and #745. Bed support is split into three layers so that a wire
format is encoded once, however many apps use it. The Jiecang family is the
reference implementation, described in detail below; the other families follow
it.

| Layer | Module | Owns |
| --- | --- | --- |
| Codec | `codec/<family>.py` | GATT transport roles, framing, checksums, command and response encoding, STOP and release frames |
| Profile | `profiles/<family>.py` | Typed data for one app or legacy route: layouts, payload shapes, timing, memory slots, setup schedules, name rules |
| Controller | `beds/<family>/` package, or `beds/<family>.py` when the family is one module | Glue that drives the codec from a profile, plus app behavior data cannot express |

Imports point one way: controllers use profiles and codecs, profiles use the
codec, and the codec imports neither.

The independently audited OkinComfortBed Ⅱ (Jalon) profile reproduces all of its
control, current-time and alarm literals through `codec/keeson.py`. Its model
byte stays zero and establishes no side addressing; its session and gesture
behavior lives in `beds/jalon_bed/`, separate from the other ORE apps.

## Codec families

Each codec module's docstring describes its frame; each profile module's
docstring names its routes and their evidence.

| Family (#745) | Codec | Profiles | Guide | Vectors |
| --- | --- | --- | --- | --- |
| J1 Jiecang F1 | `codec/jiecang.py` | `profiles/jiecang.py` | [Jiecang](../beds/jiecang.md) | `tests/jiecang_vectors.py` |
| J1 LOGICDATA app | `codec/jiecang.py` | `profiles/logicdata.py` | [Jiecang](../beds/jiecang.md#logicdata-app-family) | `tests/logicdata_vectors.py` |
| K1 Keeson E5/E6 | `codec/keeson.py` | `profiles/keeson.py` | [Keeson](../beds/keeson.md) | `tests/keeson_vectors.py` |
| O1 Okin N-frame | `codec/okin_nframe.py` | `profiles/okin_nframe.py` | [Okin N-frame](../beds/okin-nframe.md) | `tests/okin_nframe_vectors.py` |
| O2 Okin 5A | `codec/okin_5a.py` | `profiles/okin_5a.py` | [Okin 5A](../beds/okin-5a.md) | `tests/okin_5a_vectors.py` |
| R1 Richmat 6E | `codec/richmat.py` | `profiles/richmat.py`, `profiles/casper.py`, `profiles/hush.py` | [Richmat](../beds/richmat.md) | `tests/richmat_vectors.py`, `tests/casper_base_vectors.py`, `tests/hush_vectors.py` |
| S1 FFFF frame | `codec/ff_frame.py` | `profiles/ff_frame.py` | [FFFF frame](../beds/ff_frame.md) | `tests/ff_frame_vectors.py` |
| L1 Limoss DD | `codec/limoss.py` | `profiles/limoss.py` | [Limoss](../beds/limoss.md) | `tests/limoss_vectors.py` |
| Malouf (O2 Okin-like Malouf frames) | `codec/malouf.py` | `profiles/malouf.py` | [Malouf](../beds/malouf.md) | `tests/malouf_vectors.py` |
| HHC `$#` frames: MotoMotion (from `main`), MotoSleep and Power Bob | `codec/motomotion.py` | `profiles/motomotion.py`, `profiles/motosleep.py` | [HHC `$#` frames](../beds/motomotion.md) | `tests/motomotion_vectors.py` |
| BedJet PowerLayer `01` keys (from `main`) | `codec/bedjet_powerlayer.py` | `profiles/bedjet_powerlayer.py` | [BedJet PowerLayer](../beds/bedjet-powerlayer.md) | `tests/bedjet_powerlayer_vectors.py` |
| Kaidi mesh: Rize Seat, Floyd Home and ISleep | `codec/kaidi.py` | `profiles/kaidi.py` | [Kaidi](../beds/kaidi.md) | `tests/kaidi_vectors.py` |
| JMC400: Jensen Adjustable Sleep and Svane Remote | `codec/jmc.py` | `profiles/jmc.py` | [JMC400](../beds/jmc.md) | `tests/jmc_vectors.py` |
| Vibradorm VMAT: generic route, Caresse, Werkmeister, VMAT and V-MAT Basic | `codec/vibradorm.py` | `profiles/vibradorm.py`, `profiles/vmatbasic.py` | [Vibradorm](../beds/vibradorm.md) | `tests/vibradorm_vectors.py` |

Which bed types each family backs is in its registration module (see
[Registering a family](#registering-a-family)).

`codec/okin_ore.py` builds the Okin ORE `A5 5A` frame for the `okin_ore`
controller and the BOX1220 routes of Sleepy's Elite and AdjustableM5X4. No app
profile drives it, so it has no family registration; its vectors are in
`tests/test_okin_ore_vectors.py`. Standalone controllers that send frames from
several codecs (StarCode M1X12 and M5X5, Sleepy's Elite) build every frame a
codec covers through that codec.

`codec/sleep_envelope.py` builds the 14-byte sleep-sensor JSON envelope that the
Casper Base, Hush Base and GM Control sleep sensors and Good Vibe Sleep's sleep
routes send, and sizes the responses their receivers reassemble. Each app keeps
its own JSON, request numbering and limits. No app profile drives it, so it has
no family registration; its vectors are in `tests/test_sleep_envelope_vectors.py`.

The standalone `svane` bed type builds its JMC400 route and both of its routes'
lamp frames through `codec/jmc.py`, from the Svane Remote profile; its default
route writes LinonPI frames, so its controller is not a profile over the codec.

## Registering a family

A family registers itself in files it owns, so parallel family PRs do not touch
a shared registry.

- **Contract:** `tests/codec_families/<family>.py` declares
  `FAMILY = CodecFamily(...)`:
  - `profiles`: each profile class and its frozen vectors by profile key;
  - `bed_types`: the bed types whose controller is a profile over this codec;
  - `app_routes`: for bed types whose profile is an app choice, the config key
    and its choices;
  - `guide`: the guide path, how to find the frames it spells, the frozen frames
    they must belong to, and the protocol variant that reaches each profile.

  `tests/codec_families/_standalone.py` lists the bed types that stay
  standalone, with their reasons. `tests/test_codec_contract.py` discovers the
  modules and requires every supported bed type exactly once across
  `bed_types` and the standalone list. A `bed_types` entry must build a
  controller whose `profile` is one of the family's classes with vectors for
  its key; a standalone one must not.
- **Docs:** `scripts/codec_docs/<family>.py` exports `BLOCKS`, a list of
  `(guide, block name, renderer)`, and optionally `bed_types()`, the bed types
  per profile key that its profile summary lists. Shared helpers are in
  `scripts/codec_docs/_common.py`. `scripts/generate_codec_docs.py` discovers the
  modules. `tests/test_codec_docs.py` runs the generic checks for every family:
  stale blocks, one marked region per block, spelled frames are frozen vectors,
  and `bed_types()` matches the factory. Checks only one family needs go in
  `tests/test_codec_docs_<family>.py`.
- **Discovery:** `custom_components/adjustable_bed/discovery_hints/<family>.py`
  declares `HINTS`, from which the manifest's Bluetooth matchers are generated
  (see [discovery hints](discovery-hints.md)).

Profile keys are scoped to their profile class. Two families may use the same
key (Jiecang and Limoss both call their pre-v5 route `legacy`); every lookup,
including the contract's, goes through the class first.

## Jiecang codec

`codec/jiecang.py` encodes `F1 F1 opcode length payload checksum 7E`, where the
checksum is the low byte of the sum of opcode, length and payload. It holds:

- `TRANSPORTS`: the G1, G2 and G3 service, write, notify and name roles.
- `frame()` and the encoders built on it: motion, preset, memory, massage,
  light, RGB, alarm, clock, queries and G3 name wrapping.
- `SHORT_RELEASE` (`F1F14E004E7E`) and `LONG_RELEASE` (`F1F14E020000507E`).
- `parse_notification()` for `F2 F2` responses. It returns raw values where
  apps disagree, such as the automatic-light byte.

Two payload shapes address the controller: `STANDARD` (`01`) and `BILATERAL`
(`00 00`). Which one a command uses is a layout rule in the profile module.

## Profile schema

`JiecangProfile` has only the fields this family needs:

| Field | Meaning |
| --- | --- |
| `layouts` | Physical layouts and their axes, in the app's order. Empty for the motor-count layout of the legacy route |
| `transports` | Transports the profile drives, in the app's selection order |
| `hold` | Held movement: refresh interval, fixed or pulse-count repeats, final frame, release schedule |
| `recall` | Presets and memory recall: repeats, release delay and release frame |
| `memory_save`, `memory_slots`, `memory_payload` | Memory programming and capacity |
| `massage_levels` | Wire byte for each user-facing level |
| `fixed_rate` | Repeats keep absolute offsets instead of waiting after each write |
| `bootstrap` | Queries sent after notifications start |
| `name_rule` | Device names the app accepts |

| Profile | Evidence |
| --- | --- |
| `LEGACY` | Pre-v5 controller tests (bed types `jiecang` and `comfort_motion`) |
| `COMFORT_MOTION` | Comfort Motion 2.2.1 (row115) |
| `DREAMASK` | Dreamask (ERGOBALANCE) 1.0.8 |
| `DREAMOTION` | Dreamotion 1.0.5 |
| `DREAMHD` | Dream Motion HD 1.0.4 |

Bed types, transports, layouts, hold and release timing, recall and save timing,
memory slots and massage levels are generated from these definitions into the
[Jiecang guide](../beds/jiecang.md#choosing-a-profile).

Timing values come from each profile's own evidence and are never shared.

## App catalogs

A catalog is an app's own product, model or control table that a profile or
controller reads, such as `beds/hjbed/catalog.py` or `beds/richmat_mh/catalog.py`. Every
catalog follows one convention.

- **Typed Python literal by default.** One row per line, typed through a
  dataclass, `NamedTuple` or `type` alias, and wrapped in `# fmt: off` /
  `# fmt: on` so a formatter cannot spread a row over many lines.
- **A header that states provenance.** A generated catalog names its generator
  in `tools/` and the SHA-256 of each input; the generator writes that header
  and refuses other inputs where it pins them. A catalog without a checked-in
  generator says so and says where it came from, for example an accepted APK
  Protocol Audit report that stays outside the repository. It is then edited by
  hand.
- **Gzipped JSON only for large per-app data picked at runtime.** When one of
  several apps is chosen in setup and a Python literal of every app would run to
  megabytes, each app gets its own `<dir>/<app>.json.gz`. Today that is
  `beds/ruf_richmat/data/` and `beds/richmat_classic/data/`. They load through
  `catalog_json.load()` on an executor, and the owning module builds typed
  records from the returned `Node`: every value is checked against its declared
  type and a malformed row raises `CatalogError` naming its path.
- **No catalog import from `const.py`.** Values derived from a catalog, such as
  setup choices, live next to their users (`profiles/hush.py`,
  `beds/richmat_mh/models.py`, `pairing.py`), so importing `const` loads no catalog.

To review changes to `*.json.gz`, `.gitattributes` assigns the `gzip` diff
driver. Enable it once per clone:

```sh
git config diff.gzip.textconv "gzip -dc"
```

## Documentation

Docs follow the same split. A codec guide ([Jiecang](../beds/jiecang.md)) holds
the transports, framing, command tables, responses and release behavior once, then
one section per profile. Tables the profile data already knows sit between
`<!-- generated:<name> -->` markers and are rewritten by
`scripts/generate_codec_docs.py` from each family's `scripts/codec_docs/` module;
`tests/test_codec_docs.py` fails when one is stale. The layout is described in [Bed guide format](../BED_GUIDE_FORMAT.md#codec-guides).
Discovery ledgers stay separate documents linked from each profile section.

Byte-identical bed types kept for existing entries are listed under each codec
guide's **Aliases**; `tests/test_codec_docs.py` fails when two codec-backed bed
types build the same controller, profile and default timing without being
listed there. The default pulse timing table in
[Configuration](../CONFIGURATION.md#default-values-by-bed-type) is generated the
same way, from `scripts/codec_docs/_configuration.py`. `scripts/check_doc_links.py`
and `tests/test_doc_links.py` check every relative link and anchor in the README
and `docs/`.

## Controller glue

`JiecangProfileController` (`beds/jiecang/controller.py`) implements, from profile data
alone: the write loop and its pacing, held movement and cancellation-safe
release, explicit STOP, presets, memory recall and memory programming, and
layout-driven motor specs. The cleanup schedule always runs with a fresh
event, so a cancelled action still releases the motors.

Each controller keeps only behavior that frozen evidence proves and data cannot
express:

| Controller | Profile-specific code |
| --- | --- |
| `JiecangController` | G3-then-G1 transport with a generic fallback; head and feet driving the back and legs motors; 0-10 massage state |
| `ComfortMotionController` | Enumeration-order transports with every matching subscription; header-independent status replies; desired-state lights; wake routine |
| `JiecangAppController` | Transport choice and startup gating; capability-gated RGB lighting; Dream Motion HD light-control state; alarm and wake executor |

## Vector harness

`tests/jiecang_vectors.py` lists each profile's frozen single-frame literals.
App profiles take them from the test vectors of their accepted report; the
legacy route, which has none, takes the frames the pre-v5 controller sent.
`tests/test_jiecang_vectors.py` proves two things:

1. Every frozen literal round-trips through `codec.frame()` byte for byte.
2. Every fixed frame a profile can send is among its frozen literals. For the
   legacy route the two sets are equal.

To add a profile, add its literals to the vector file and its entry to the
census in the test. A profile whose literals the codec cannot reproduce gets
its own codec, with the reason recorded here.

## Route decisions

- **Comfort Motion keeps two routes.** The UUID-detected `comfort_motion` bed
  type uses the legacy profile, which covers G3 (FE60) controllers, three memory
  slots and 0-10 massage. The Comfort Motion app profile drives G1 and G2 only,
  with two slots, 0-3 massage and its own timing. Migrating legacy entries would
  drop entities and break G3 beds, so the setup label now names the UUID route
  "legacy controls".
- **`jiecang` and `comfort_motion` are aliases.** Both select the legacy
  profile; they differ only in detection signal, label and profile-review
  suggestions. They stay separate bed types until a guided migration (#676).

## Behavior notes

- Bytes on the wire are unchanged for every route. A differential capture of
  154 controller, layout, transport and profile combinations matched every
  write, its characteristic, write mode and relative timing, except for the
  legacy cancellation timing below.
- The legacy route now uses the shared, cancellation-aware write loop. A stop
  during a refresh releases immediately instead of after the rest of the
  50 or 100 ms interval. Frames and their order are unchanged.
- The legacy route no longer defines the unused `BOTH`, `HEAD_ALT`, `WAIST`,
  `TIMER` and right-side split constants. It never sent them.
