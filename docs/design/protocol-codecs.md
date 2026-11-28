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

A family is proven by encoding: its framing rule holds byte for byte for the
command writes of every route in it, never because apps share a name, UUID or
vendor. Bed types that send identical bytes stay separate bed types so existing
entries keep their identities; the wire snapshot (`tests/test_wire_snapshot.py`)
captures every route's writes and shows the equality.

The independently audited OkinComfortBed Ⅱ (Jalon) profile reproduces all of its
control, current-time and alarm literals through `codec/keeson.py`. Its model
byte stays zero and establishes no side addressing; its session and gesture
behavior lives in `beds/jalon_bed/`, separate from the other ORE apps.

OkimattMotion's 31 control literals reproduce through Keeson's big-endian
E5 encoder. Its 10 alarm literals use the shared checksum with the EA clock
field encoder and OkimattMotion's own option bytes. The Cherish clock differs
in those fields, and the OkimattMotion profile has its own control sequences.

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

Each family's guide lists the bed types it backs.

`codec/okin_ore.py` builds the Okin ORE `A5 5A` frame for the `okin_ore`
controller and the BOX1220 routes of Sleepy's Elite and AdjustableM5X4. No app
profile drives it; its vectors are in
`tests/test_okin_ore_vectors.py`. Standalone controllers that send frames from
several codecs (StarCode M1X12 and M5X5, Sleepy's Elite) build every frame a
codec covers through that codec.

`codec/sleep_envelope.py` builds the 14-byte sleep-sensor JSON envelope that the
Casper Base, Hush Base and GM Control sleep sensors and Good Vibe Sleep's sleep
routes send, and sizes the responses their receivers reassemble. Each app keeps
its own JSON, request numbering and limits. No app profile drives it; its
vectors are in `tests/test_sleep_envelope_vectors.py`.

The standalone `svane` bed type builds its JMC400 route and both of its routes'
lamp frames through `codec/jmc.py`, from the Svane Remote profile; its default
route writes LinonPI frames, so its controller is not a profile over the codec.

## Snore Monitor BED records

Snore Monitor 2.3.8's literals require `codec/onlysnore.py`.
Its control declares five while carrying six payload bytes, including a distinct
save/release flag; triple alarms likewise keep a declared length that differs
from their payload size. Neither the existing N-frame carrier nor Smart Sleep
codec reproduces its complete control, intervention, alarm and receive formats.
The minimal codec reuses N-frame's parameter-record encoder without introducing
a new carrier or changing existing scenarios. `profiles/onlysnore.py` owns this
app's command catalog and timing, while its controller owns the BED session and
distinct single/triple alarm behavior. The frozen proof and actual-path tests
are app-specific; separate sleep sensing, network and audio remain excluded.
See the [Snore Monitor BED guide](../beds/onlysnore.md).

## Flexispot

Flexispot 1.1 (2) needs `codec/flexispot.py`: none of the existing carriers
encodes its 20-byte `9B`/`9D` records, CRC16 body at offsets 2–16, unprotected
alarm-slot byte, two-slot schedule or signed notification fields. All 77 frozen
literals reproduce through its encoder. `profiles/flexispot.py` keeps the four
explicit layouts and this app's timing; its controller keeps session-bound
motor release and notification-backed read/modify/write behavior. No existing
wire scenario changes. See the [Flexispot guide](../beds/flexispot.md).

GhostBed 1.3 (4) reproduces all 27 frozen frames through the same encoder, including its literal alarm-3/4 bank/key stores and the unprotected selector. `profiles/ghostbed.py` keeps its fixed current layout and independently recovered timing. `beds/flexispot/ghostbed.py` extends the shared controller for four banked alarms and current left-only anti-snore semantics. It does not inherit Flexispot product selection or infer a split layout.

## Smart Comfort seat codec

The Smart Comfort SYNARGY and SYNERGY literals are reproduced by
`codec/smart_comfort.py`, with independent profiles in `profiles/smart_comfort.py`.
Keeson's checked E5 carrier can reproduce the outer motor envelope, but its key
word semantics do not cover seat-scoped accessory groups, BGR/mask color fields,
A0/B1 queries or the three replies. Okin N-frame does not encode this payload.
No existing codec reproduces every relevant command and response format, so this
family owns its encoders and parser. `tests/test_smart_comfort.py` verifies both
members' frozen literals, rather than selecting a family by UUID or brand.
See the [Smart Comfort guide](../beds/smart-comfort.md).

## Sleeptime

Sleeptime 1.0.1 reproduces the frozen writes through Okin N-frame's
`frame40`, `request`, `clock` and `alarm` encoders. Its motion suffix is
`01`. Ultramatic's side selector, BCD fields and paired seven-byte status
records have different meanings. Sleeptime adds one single-record dispatcher
for massage and alarm updates. The app profile owns the three layouts,
weekday mapping and cadence. The controller binds the delayed release and
settings writes to their starting UART session. See the
[Sleeptime guide](../beds/okin-nframe.md#sleeptime) and
`tests/test_sleeptime.py`.

## Ultramatic Smart Bed

Ultramatic Smart Bed 1.1.2 reproduces every app send through
Okin N-frame's `frame40`, `request`, `clock` and `alarm` encoders, including
unequal alarm type/side cases. `SideRecordParser` adds bounded extraction of
the app's two seven-byte replies. Its typed app profile owns BCD, side selection
and normalization; the family controller extension owns the session and gestures.
It uses one Nordic UART route and is independent of the legacy Ultramatic ORE
controller. Hardware remains unverified.

## Sealy FlexiRest

Sealy FlexiRest 1.0.4 (4) matches all 73 accepted transmit vectors through
the existing FFFF control, query, sum, clock and alarm encoders. Its explicit
`flexirest` Solace profile owns name gates and startup timing; the shared
Solace/Sophie controller supplies the equivalent preset and massage behavior.
The extension adds session-settled writes, the distinct light-off command,
fault readback and native onboard alarm semantics. Android panel events remain
UI behavior and do not establish receiver capabilities or sync changes.
See [Sealy FlexiRest](../beds/ff_frame.md#sealy-flexirest).

## M Line composite codec

The M Line 1.2.2 codec delegates its 44 frozen control literals to the proven
N-frame and Keeson carriers. Neither existing codec implements its complete
auxiliary and receive formats, so `codec/mline.py` owns those, with typed
selectors/layouts in `profiles/mline.py`. All 96 accepted packet cases run
through production encoders. See the [M Line guide](../beds/mline.md).

## Relax Motion

`codec/relax_motion.py` reuses CheersSleep's byte-identical serial/PID encoder
for P1. Its P2 normal and extra fields are unaddressed and its release is five
zero bytes, so it owns those thin encoders instead of adopting CheersSleep's
side and release semantics. `profiles/relax_motion.py` holds the model, app-page
and locale gates. Both carriers are checked by literal vectors and real native
controller/entity/service paths. See [Relax Motion](../beds/relax-motion.md).

## SmartBed

The SmartBed app's ten receiver profiles reuse the Okin ORE, Keeson E6, Okin
N-frame and SoundWave record encoders. The profile in `profiles/smartbed.py`,
not the transport, selects each builder. Its controller owns the notification
handlers of one connection, the capability pages and the release and query
timing. It is a bed type of its own beside the Okin receiver route, whose
frames are unchanged. See [SmartBed](../beds/smartbed.md).

## Linak two-byte control words

Vindö 1.0.18 shares the Linak opcode-plus-zero framing and the four
back/legs combination encodings. `codec/linak.py` holds those shared builders
and adds the Vindö unsigned, variable-length position parser. The existing
Linak Bed Control parser expects exact four-byte status and speed reports.
The existing controllers also differ in notification setup, movement timing,
release or massage sequencing, so Vindö has its own app profile and session.
See [Vindö](../beds/vindo.md) and `tests/test_vindo_vectors.py`.

## Registering a family

A family keeps its files to itself, so parallel family PRs do not touch a
shared registry.

- **Docs:** `scripts/codec_docs/<family>.py` exports `BLOCKS`, a list of
  `(guide, block name, renderer)`, and optionally `bed_types()`, the bed types
  per profile key that its profile summary lists. Shared helpers are in
  `scripts/codec_docs/_common.py`. `scripts/generate_codec_docs.py` discovers the
  modules.
- **Discovery:** `custom_components/adjustable_bed/discovery_hints/<family>.py`
  declares `HINTS`, from which the manifest's Bluetooth matchers are generated
  (see [discovery hints](discovery-hints.md)).

Profile keys are scoped to their profile class. Two families may use the same
key (Jiecang and Limoss both call their pre-v5 route `legacy`); every lookup
goes through the class first.

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
| `COMFORT_MOTION` | Comfort Motion 2.2.1 |
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
`scripts/generate_codec_docs.py` from each family's `scripts/codec_docs/` module.
The layout is described in [Bed guide format](../BED_GUIDE_FORMAT.md#codec-guides).

Byte-identical bed types kept for existing entries are listed under each codec
guide's **Aliases**. The default pulse timing table in
[Configuration](../CONFIGURATION.md#default-values-by-bed-type) is generated the
same way, from `scripts/codec_docs/_configuration.py`.

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

BetterLiving2 1.3.0 (16) fits the existing Keeson word carriers and
checked calendar/alarm builders plus Okin N-frame records: every frame it sends
comes from the existing encoders. Its six control box and motor profiles extend
the shared Keeson controller; their operation ownership and P1 stateful alarm
consumer remain app-specific.

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

## Execution capabilities

Held motion and concurrent motors are declared in `execution.py`'s
`ExecutionCapabilities`: a family profile's `execution` field,
or an `execution` override on a standalone controller. The codec states what
the wire can express; the profile states what its own app is proven to do.
Nothing is declared by analogy with another app, family or shared codec. The
Okin N-frame codec can OR any motor words, but only the profiles whose apps
compose two axes and release one without stopping the other declare
`concurrent`. Prodigy 2 composes keys but its release clears them all, so it
stays serialized.

- **Hold** is `stream` (the app refreshes a held frame until release) or
  `latched` (one start frame and an explicit stop). `hold_controls` scopes it to
  the held controls whose gesture is a sustained press, for controllers whose
  buttons also carry other gestures (Good Vibe Sleep and the classic Richmat
  apps, recomputed from their mode selectors on every read). Leases, renewal and
  STOP pre-emption are in the [command lifecycle](../COMMAND_LIFECYCLE.md#renewable-hold-leases).
- **Concurrent motors** run as one streamer per device that writes the composed
  frame each tick, so there is never extra BLE concurrency. A combined control
  of a pair uses the intersection of both sides' capabilities.
- **Motor speed** has no field: no app is proven to offer a selectable speed.

Linak keeps its conservative reversal: a seek refreshes the held movement
without an intermediate release and sends STOP on cleanup, and no extra
reversal packet or settle delay is added between seeks. A replacement waits
for the previous STOP; the physical pause users once reported is unverified on
current firmware.

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

ComfortBaseForBluetooth 1.1.2 (6) reuses Keeson K1 only after all
43 frozen builders reproduce literally through `frame`, `clock_fields` and
`alarm_table`. Its product catalog is UI data over one `comfortbase` profile.
The Keeson controller supplies hold/release and recall; its ComfortBase extension
adds the bounded save gesture, product gates, fixed GATT roles and timer parser.

## OKIN Smart Sleep

OKIN Smart Sleep 2.4.9's P1 motor/preset literals reproduce through Keeson's `p2_side` carrier,
which `codec/smart_sleep.py` reuses. No existing codec reproduces P1's complete
settings and reply shapes plus P2's AA/2A commands and notifications, including
its distinct motor-neutral and global STOP. `profiles/smart_sleep.py` declares
both formats and their catalogs; one family controller owns their session.
The vector harness compares every accepted in-scope literal before reuse.
See [Smart Sleep](../beds/smart-sleep.md).

N32 Motion Bed 1.1.14 (38) reproduces its four-mask held frames,
clock and slot queries through Okin N-frame. Its alarm uses the same seven
counted fields plus an uncounted reserved byte and a third proven slot.
`alarm(..., reserved=0)` expresses that trailer without changing existing
profiles' records. Its typed fixed profile uses the shared Okin family
controller; its own session and alarm callback live in `beds/n32_motion_bed/`.

アシステック / Yamada 1.0.1 (6) adds explicit P1/P2 profiles only after
all 35 packet literals match existing Keeson and Okin N-frame encoders. Its
shared-family controller extension owns alarm parsing, session fences, raw clock
fields and captured release scheduling. No new codec or product alias is needed.

Bedgear 2.0.1 (row A12) independently matches the HHC codec's short plain/M
frames and decimal-digit XOR format. `decimal_fields` preserves the exact string
widths of all three source builders, including the alarm's six-plus-four fields.
The unchanged 75 nonempty vectors plus suppressed-query, parser and selector
cases live in `tests/fixtures/bedgear/`; `tests/test_bedgear_vectors.py` proves
the byte matches. The separate `BedgearProfile` owns its 15 layouts, independent
name gates, timing and control release policies. No sibling app's parameters
select its capabilities.

Leon's L2Motion 2.0.2 matches the existing HHC carrier in all independent
transmit literals in `tests/l2motion_vectors.py`. Its `L2MotionProfile` declares
its own name gates, axes and controls. The shared letter runtime preserves
Bedgear's timing while L2Motion delays the first periodic write until its first
timer tick. Neither synchronization commands nor accessory replies establish
concurrent motors, position feedback or native side routing.

ErgoBed Control 1.0.3 matches MotoMotion's plain letters and decimal R records
in 40 frozen vectors. The remaining vector uses the same digit XOR and
variable-width decimal fields with an A terminator. The codec exposes that
terminator for the local clock. The ErgoBed profile sets its own panel and
feature gates, record field order, and held behavior. Its shared letter
controller extension handles the exact 75-token status records and fences
settings writes to the current BLE connection.

## Linx

Linx 1.0.7 (27) adds `codec/linx.py` and typed Quest/Orbes
profiles. The existing Keeson JSON encoder does not reproduce the frozen Gson
field order, and no existing carrier reproduces its complete AA, ASCII startup
and AB intervention literals. The production harness compares all 39 accepted
literals byte for byte. The independent transport selection and connection-owned
release, cache and callback behavior belong to `beds/linx/`, without changing
any legacy JSON wire scenario. See [Linx](../beds/linx.md).

Somos 1.0.0/code1 reuses Keeson's K1 E6, P2 and P2-side carriers
only after all 60 accepted literal rows match. The final zero in its P1
carrier and P3 trailer establishes no side selection. Its five explicit
`profiles/somos.py` products use the shared family controller, extended only
for source-specific polling, notification parsing and neutral UI axes.

### SUTA P1/P2 (SUTA 3.20.0)

SUTA's exact-name application panels now use `codec/suta.py`,
`profiles/suta.py` and the shared `beds/suta/` controller. P1 adds only UTF-8
CRLF framing; P2 uses its own 53 59 / payload / additive-sum / 54 43 format.
No existing family represents both accepted formats and every frozen literal,
so the new codec is deliberately limited to these two builders. The production
harness covers all 203 accepted final frames and 56 constructor literals.
Names, timing and capability gates stay in profile/catalog data. The historical
standalone SUTA inventory does not describe this expanded route.

Okimiki 1.0.1 (10101) freezes the original 42
and focused 29 literal rows in `tests/fixtures/okimiki/`. All 71 passed the
production Richmat codec before selecting it. `profiles/okimiki.py` retains
four concrete factory/CID/body identities, including IPRM and IQRM's distinct
alarm getter despite sharing KWRN's menu body. Its shared catalog-controller
extension owns the app's whole-buffer common parser, captured-session writes,
strict elapsed deadlines, flat release, three-second save threshold and local
alarm records. No existing wire builder or profile changes.

CheersSleep 2.7.0 adds `codec/cheerssleep.py`: the serial/PID P1
encoder is extracted from Remacro's existing `build_frame`, retaining that import
API and all app-specific counters. The accepted P1 literals prove identical
framing; CheersSleep's distinct counters and timing remain in its own profile.
P2's EE normal/setting/query frames require a new encoder, since no existing
codec reproduces them. Neither UI labels nor shared service identity establish
byte equivalence. `tests/test_cheerssleep_vectors.py` covers both formats.

ORE Ultramatic 1.0.5 selects the existing Keeson codec only after
all 81 frozen transmit literals reproduce through its production encoders.
Both the big-endian P1 and reserved-byte little-endian P2 builders are proven;
shared names or GATT roles do not establish that match. The app profile owns
GATT-dependent selection, alarm choices and calendar transformations. A shared
ORE controller extension owns route capabilities and session-fenced callbacks,
with corrected fragment early returns in the Keeson parser. The full 91-vector
harness and 12 parser observations remain fixtures, with
explicit bounds-safe/session-lifetime differences for Home Assistant.

Restonic 1.0.1 (okin.bedding.restonic) reproduces every frozen builder through
Keeson E6, Okin ORE and Keeson P2-side. Its profile keeps the three BLE branches
independent from the three UI layouts. The shared Keeson controller extension
owns captured-session refresh/release and raw offset diagnostics without adding
a wire codec or changing existing routes. See [Restonic](../beds/restonic.md).

### Alya Smart Furnishing

The accepted row090 app layouts in `profiles/alya.py` drive ORE (P1), Keeson E6 (P2) and Okin N-frame (P3/P4). All 260 frozen reachable command literals reproduce through these existing codecs. ORE already carries parameter payloads; the N-frame encoder adds the five-byte massage setting record. The app's own 300 ms hold/release cadence and twelve-layout capability gates remain its profile data. Commands and transports are generated in the [Alya app guide](../beds/alya.md).

## ErgoBQ BED

ErgoBQ 1.8.1 adds `codec/ergobq.py` for the versioned `55 AA` command,
big-endian payload length, DP TLVs and big-endian reflected CRC16 envelope.
The existing FF-frame, Richmat and Keeson carriers do not reproduce this
format's complete literal set. The typed `profiles/ergobq.py` selects the two
byte-identical BED products and serial-dependent axes. It has no mattress
profile. `beds/ergobq/` uses the shared settled GATT writer with an expected
client, while owning its authentication, notification stream and release.
See [ErgoBQ BED](../beds/ergobq.md) and `tests/test_ergobq_vectors.py`.

## iFit

iFit 1.1 (3) reuses `codec/okin_5a.py` only after all 35 reachable command
literals and its separate startup literal reproduce byte for byte. Its
`profiles/ifit.py` declares independent timing and command data. The shared
Okin 5A controller extension in `beds/ifit/` owns exact-session startup,
held refresh without a trailing release frame, and the combined Flat/preset
save gesture. No existing app route, discovery matcher or wire scenario changes.
See [iFit](../beds/okin-5a.md#ifit).

## Comfort Bed

Comfort Bed 1.0.2's current ComfortCareBed profile reproduces all 108 frozen
TX literals through `codec/richmat.py:function`, including both sides, startup
queries and the absent-long-code zero output. It adds profile data and extends
the existing family motion/session controller. Its ordinary RX dispatcher
differs from Casper's complete-length receiver, so it has a scoped dispatcher
with only its two verified announcements. See the
[Comfort Bed section](../beds/richmat.md#comfort-bed) and `tests/test_comfort_bed.py`.

Amada Smart 1.0.0 (1) selects the unchanged Okin N-frame codec after all 78
frozen transmit literals match `frame40`, `request`, `clock` and `alarm`.
`profiles/amada.py` owns the explicit A/AB/B selector and its own schedules.
The shared Okin controller extension owns AMADA's captured BLE session, selected
record parsing, six-second save/reset and generic HA alarm routing. A/B are not
physical Left/Right evidence. The accepted source remains bounded PARTIAL
(B1 SDK warnings and B2 exception/cancellation ordering), hardware unverified.

### Active Sleep

`codec/active_sleep.py` and its typed profile are separate from Bed Operation's
`codec/paramount.py`: the latter adds a `40` header and uses different GATT
UUIDs, so it does not reproduce the Active Sleep literals. All 32 frozen
Active Sleep frames have an independent literal vector test, including excluded
commands tested only through the codec, never exposed as runtime actions.

## Thrive Sleep

Thrive Sleep 1.1.2 uses the existing Richmat function, calendar, RGB, light-timer,
countdown and extended-record encoders. All 115 frozen literals reproduce through
those encoders. Its three current profiles own the product menus and alarm modes;
its session controller rejects mixed recognized services rather than applying
the app's independent handle-selection and encoding order to unknown hardware.
See [Thrive Sleep](../beds/richmat.md#thrive-sleep).
