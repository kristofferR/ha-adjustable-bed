# Bluetooth discovery hints

Home Assistant starts a discovery flow only for advertisements that match the
manifest's `bluetooth` list. Detection then decides which bed it is. Both steps
read the same declared hints ([#780](https://github.com/kristofferR/ha-adjustable-bed/issues/780)).

## Declaring hints

Each family owns `custom_components/adjustable_bed/discovery_hints/<family>.py`
and declares `HINTS`, built with the helpers in `_hints.py`:

- `services(uuid, ..., bed_types=...)`: advertised service UUIDs.
- `manufacturer(company_id, data_start=..., bed_types=...)`: a manufacturer
  record, optionally with a payload prefix.
- `names(pattern, ..., bed_types=..., case=...)`: local names. A pattern is a
  glob without its trailing `*`, with a literal first three characters as Home
  Assistant requires. The gate is case-sensitive, so `case` lists the
  spellings it needs: `EXACT`, `FOLD` (as declared and lowercase) or `ANY`
  (every letter case). `anywhere=True` records that detection also accepts the
  pattern after the start of the name, which the gate cannot express.

`bed_types` names the bed types a hint can lead to. Take hints from the app's
scan filter or a catalog where one exists. The GM Control hints read
`gmmotor_catalog.SCAN_KEYWORDS`, which `tools/generate_gmmotor_catalog.py`
writes, so a regenerated catalog leaves no stale matcher.

`_excluded.py` holds the name fragments of non-bed devices that share generic
bed service UUIDs. Detection rejects them only when nothing but those UUIDs is
advertised.

## The manifest

`scripts/generate_bluetooth_matchers.py` writes the manifest's `bluetooth` list
from the hints: service UUIDs, then manufacturer records, then names, sorted.
Families may declare the same signal, but must agree on `connectable`. CI runs
the script with `--check`, and `tests/test_bluetooth_matchers.py` checks that:

- the manifest holds exactly the hints' matchers;
- every matcher maps to a declared hint;
- Home Assistant's own matcher admits every hint's signal, and detection's
  first pass sees it;
- every hint names known bed types, and name spellings only vary case.

Never edit the list by hand. Change a hint and regenerate.

## Detection's first pass

`first_pass(service_info)` returns the hints an advertisement matched, with
Home Assistant's matching rules. Detection reads it for the app candidate
passes (GM Control, its sleep sessions, HJBed, the AdjustableM5X4 Star scan,
the FurniMove gateway and the Casper Base sleep sensors). Refinement from
names, GATT, model or device info stays in `detection.py`, because it is
ordered and often needs more than one signal.

Several detection name rules are wider than the gate: they ignore case, accept
a pattern inside the name, or have no matcher at all. Such a bed is discovered
only when it also advertises a matched service UUID or manufacturer record.
The Good Vibe Sleep scan filter and the eShine `Smartbed` name rule are such
rules: as hints they would add matchers the manifest has never had.
Changing what is discovered needs evidence and its own change.
