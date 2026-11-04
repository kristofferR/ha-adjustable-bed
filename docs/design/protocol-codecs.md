# Protocol codecs and app profiles

Ref #742 and #744. Bed support is split into three layers so that a wire
format is encoded once, however many apps use it. The Jiecang family is the
reference implementation; later families follow it (#745).

| Layer | Module | Owns |
| --- | --- | --- |
| Codec | `codec/<family>.py` | GATT transport roles, framing, checksums, command and response encoding, STOP and release frames |
| Profile | `profiles/<family>.py` | Typed data for one app or legacy route: layouts, payload shapes, timing, memory slots, setup schedules, name rules |
| Controller | `beds/<family>*.py` | Glue that drives the codec from a profile, plus app behavior data cannot express |

Imports point one way: controllers use profiles and codecs, profiles use the
codec, and the codec imports neither.

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

## Documentation

Docs follow the same split. A codec guide ([Jiecang](../beds/jiecang.md)) holds
the transports, framing, command tables, responses and release behavior once, then
one section per profile. Tables the profile data already knows sit between
`<!-- generated:<name> -->` markers and are rewritten by
`scripts/generate_codec_docs.py`; `tests/test_codec_docs.py` fails when one is
stale. The layout is described in [Bed guide format](../BED_GUIDE_FORMAT.md#codec-guides).
Discovery ledgers stay separate documents linked from each profile section.

## Controller glue

`JiecangProfileController` (`beds/jiecang.py`) implements, from profile data
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

## Follow-ups

- The LOGICDATA app profiles (`logicdata_app_protocol.py`) encode the same
  frame, transports, opcodes, alarm, clock and massage frames. They are the
  first #745 family to move onto this codec.
- The family write loop bypasses `_write_gatt_with_retry`, so Jiecang writes
  do not appear in support-bundle command traces. That was true before this
  change and needs its own fix.
