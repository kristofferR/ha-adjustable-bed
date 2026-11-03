# Bed guide format

Every bed guide in [`docs/beds/`](beds/) is a protocol reference that readers scan
for values. Use this layout for new guides and keep it when you update one.
[BedTech](beds/bedtech.md) is the canonical example.

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
Models, Apps and Features sections of every guide.
