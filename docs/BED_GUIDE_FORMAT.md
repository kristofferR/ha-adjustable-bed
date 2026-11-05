# Bed guide format

Every bed guide in [`docs/beds/`](beds/) is a protocol reference that readers scan
for values. Use this layout for new guides and keep it when you update one.
[BedTech](beds/richmat.md#bedtech) is the canonical example.

A wire format shared by several apps or bed types gets one [codec guide](#codec-guides)
instead of one guide per app. [Jiecang](beds/jiecang.md) is the reference.

Discovery ledgers are a different document. Evidence, row-by-row dispositions,
reachability arguments and audit wording belong in the ledger, which is an
audit record: it stays machine-local with the APK Protocol Audit report and
never goes in `docs/`. The implementation PR states its totals and exclusions,
and the guide states the results in reference form.

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

- <package, version, artifact SHA-256, the PR that implemented it>
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
<!-- generated:<family>-profiles -->   <!-- summary, timing, layouts, startup -->
<!-- /generated -->
### Aliases          <!-- byte-identical bed types kept for existing entries -->

## Wire codec
### Transports         <!-- generated from the codec's transport table -->
### Framing and checksum
### Command encoders   <!-- one #### per command group, each table generated -->
### Responses          <!-- which parser each profile uses -->
### STOP and release behavior
### Vectors            <!-- where the frozen vectors and their tests live -->

## Profiles
### <Family name> family   <!-- only when several profiles share behavior -->
### <Profile name>         <!-- one per profile, see Profile sections -->

## Notes
### Analysis provenance
```

- **Codec part** holds everything every profile shares: transports, framing,
  checksum, the command tables built by the codec module, response parsing and
  release behavior. When profiles parse responses differently, say which parser
  each one uses.
- **Generated tables** sit between `<!-- generated:<name> -->` and
  `<!-- /generated -->` and are rewritten by `scripts/generate_codec_docs.py` from
  the codec and profile modules. Do not edit them by hand; edit the code and rerun
  the script. `tests/test_codec_docs.py` fails when a block is stale. To generate
  a block, add a renderer and a `BLOCKS` entry to the family's module in
  `scripts/codec_docs/` (see
  [Registering a family](design/protocol-codecs.md#registering-a-family)).
- **Generate every value the code knows**: transports, command tables (built by
  calling the codec's encoders, never as literals), bed types, layouts and
  payloads, timing and startup queries. Prose points to a generated table instead
  of repeating its numbers, so a changed profile cannot leave a stale copy.
- Every frame spelled out by hand must be one of the family's frozen vectors;
  the `guide` of its `tests/codec_families/` module tells the docs test how to
  find them.
- Keep hand-written prose for what code cannot express as data: setup flow,
  state machines, notification handling, services and safety behavior.

### Profile sections

Every profile section, and a family section shared by several profiles, uses
these headings in this order. Omit a heading that does not apply.

```markdown
### <Profile name>

**App:** [<App name>](<store link>) <version>, `<package>`   <!-- omit for a non-app route -->

**Status:** <✅ | ❓ | ⚠️> <short qualifier>

Behaves as the [<family>](#<family>-family), except as below.   <!-- family members only -->

#### Setup          <!-- setup questions, detection rules, transport choice, pairing -->
#### Controls       <!-- each control and the command table row it sends -->
#### Timing         <!-- link the generated tables; prose only for sequences the data lacks -->
#### Notifications  <!-- which responses the profile consumes and how -->
#### Services       <!-- actions beyond the standard entities -->
#### Evidence       <!-- link to the discovery ledger -->
```

- **Detection rules** go under the profile's Setup: the service UUIDs or name
  patterns that select it and the bed type each yields, or "Detection: none" for
  an explicit choice. "Choosing a profile" only says which route detection
  suggests.
- A family member lists only what differs from its family section.
- **Evidence** links the ledger and states the result in reference form, for
  example "Comfort Motion sends only its frozen frames". Dispositions, exclusions,
  counts and reachability arguments stay in the ledger.

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
