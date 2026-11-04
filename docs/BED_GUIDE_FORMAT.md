# Bed guide format

Every bed guide in [`docs/beds/`](beds/) is a protocol reference that readers scan
for values. Use this layout for new guides and keep it when you update one.
[BedTech](beds/bedtech.md) is the canonical example.

A wire format shared by several apps or bed types gets one [codec guide](#codec-guides)
instead of one guide per app. [Jiecang](beds/jiecang.md) is the reference.

Discovery ledgers are a different document. Evidence, row-by-row dispositions,
reachability arguments and audit wording belong in the ledger
(`docs/apk-analysis/dispositions/` or `docs/beds/*-disposition.md`). The guide
links to the ledger and states the results in reference form.

## Skeleton

```markdown
# <Bed, actuator or app name>

**Status:** <✅ Tested | ❓ Needs testing | ⚠️ Partially tested> (<optional short qualifier>)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)<, other contributors>

## Known Models

- <brands, models, remotes, Bluetooth name patterns>

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [<App name>](https://play.google.com/store/apps/details?id=<package>) <version> | `<package>` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (<axes>) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (<n> slots) |
| Massage | ... |
| Lights | ... |

## Protocol Details

**Service UUID:** `<uuid>`
**Write Characteristic:** `<uuid>`
**Notify Characteristic:** `<uuid>`
**Format:** <one-line packet summary>

### Packet Format
### Write Mode

## Detection / Setup

## Commands

### Motor Control

| Command | Bytes | Description |
|---------|-------|-------------|

### Presets
### Memory
### Massage
### Lights

## Position Feedback / Notifications

## Command Timing

## Notes

### Analysis provenance

- <package, version, artifact SHA-256, link to the discovery ledger>
```

## Codec guides

A codec guide describes one wire format and every profile built on it. It keeps the
same opening as a single-protocol guide (Status, Credit, Known Models, Apps,
Features) so the reference check applies, then splits into codec and profile parts.

```markdown
# <Family>

**Status:** ...   **Credit:** ...

## Known Models
## Apps            <!-- one row per app, with a Profile column linking its section -->
## Features        <!-- one column per profile -->
## Choosing a profile
<!-- generated:<family>-profiles -->
<!-- /generated -->

## Wire codec
### Transports
### Framing and checksum
### Command encoders   <!-- one #### table per command group -->
### Responses
### STOP and release behavior
### Vectors            <!-- where the frozen vectors and their tests live -->

## Profiles
### <Profile name>     <!-- one per profile -->

## Notes
### Analysis provenance
```

- **Codec part** holds everything every profile shares: transports, framing,
  checksum, the command tables built by the codec module, response parsing and
  release behavior.
- **A profile section** covers the app or product, its setup questions, available
  controls, timing beyond the generated tables, and verification status. It links
  its discovery ledger rather than folding it in. Behavior shared by several
  profiles gets a family section before them; each profile then lists only what
  differs.
- **Generated tables** sit between `<!-- generated:<name> -->` and
  `<!-- /generated -->` and are rewritten by `scripts/generate_codec_docs.py` from
  the profile module. Do not edit them by hand; edit the profile and rerun the
  script. `tests/test_codec_docs.py` fails when a block is stale. To generate a block
  for a new family, add a renderer and a `BLOCKS` entry to the script.
- Keep hand-written prose for what profile data cannot express: setup flow,
  state machines, notification handling, services, safety adaptations.
- Tables of frames come from the codec module and controllers, as with any guide.

## Rules

- **Status** is one short line starting with ✅, ❓ or ⚠️. Static (APK) evidence
  without hardware confirmation is ❓ Needs testing. Put longer caveats in the body.
- **Apps** and **Features** are tables. A guide that covers several variants may
  use one column per variant (`| Feature | <variant A> | <variant B> |`).
- **Commands** are tables with the exact values the controller sends, taken from
  the code in `custom_components/adjustable_bed/beds/`. Never copy values from
  another bed type.
- Prefer headings, short bullets and tables over paragraphs. Add sections such as
  Alarms, Actions or Paired beds where the protocol needs them.
- Use `> [!NOTE]` and `> [!WARNING]` callouts sparingly, for corrections and
  safety caveats.
- Keep headings that other docs link to. Renaming one breaks its `#anchor`.
- When rewriting a guide, keep every fact, caveat, version, hash, link and issue
  reference. Restructure the wording, not the content.

`tests/test_bed_guide_format.py` checks the Status and Credit lines and the Known
Models, Apps and Features sections of every guide, codec guides included.
