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
  spellings it needs: `EXACT` or `FOLD` (as declared and lowercase).
  `anywhere=True` records that detection also accepts the
  pattern after the start of the name, which the gate cannot express.

`bed_types` names the bed types a hint can lead to. Take hints from the app's
scan filter or a catalog where one exists. The GM Control hints read
`SCAN_KEYWORDS` in `beds/gmmotor/catalog.py`, which `tools/generate_gmmotor_catalog.py`
writes, so a regenerated catalog leaves no stale matcher.

`_hints.TOO_BROAD` lists app scan prefixes that common non-bed devices also
advertise (`TEST`, `SLEEP`, `1320`, `1520`). They stay in the hints, so
detection still reads them, but get no matcher: they never start discovery on
their own, and their apps stay selectable by hand.

`_excluded.py` holds the shared service UUIDs and the name fragments of
non-bed devices that advertise them. Detection rejects such a name only when
nothing but those UUIDs and standard Bluetooth services (Battery, Device
Information, Heart Rate, HID and the other assigned `0x18xx` services) is
advertised.

## The manifest

`scripts/generate_bluetooth_matchers.py` writes the manifest's `bluetooth` list
from the hints: service UUIDs, then manufacturer records, then names, sorted.
Families may declare the same signal, but must agree on `connectable`. A name a
shorter declared prefix already admits gets no matcher of its own. CI runs
the script with `--check`, and `tests/test_bluetooth_matchers.py` checks that:

- the manifest holds exactly the hints' matchers, less the covered prefixes;
- every matcher maps to a declared hint;
- Home Assistant's own matcher admits every hint's signal, and detection's
  first pass sees it;
- every hint names known bed types, and name spellings only vary case.

Never edit the list by hand. Change a hint and regenerate.

## Detection's first pass

`first_pass(service_info)` returns the hints an advertisement matched, with
Home Assistant's matching rules. Detection reads it for the app candidate
passes (GM Control, its sleep sessions, HJBed, the AdjustableM5X4 Star scan,
the FurniMove gateway and the Casper Base sleep sensors). The Casper names run
after a bed's own service and the non-bed exclusions, and where another sleep
module shares the name they are one candidate among several. Refinement from
names, GATT, model or device info stays in `detection.py`, because it is
ordered and often needs more than one signal.

Several detection name rules are wider than the gate: they ignore case, accept
a pattern inside the name, or have no matcher at all. Such a bed is discovered
only when it also advertises a matched service UUID or manufacturer record.
The Good Vibe Sleep scan filter and the eShine `Smartbed` name rule are such
rules: as hints they would add matchers the manifest has never had.
Changing what is discovered needs evidence and its own change.

## A new bed

Discovery and the device list use `detect_new_bed()`. When nothing but shared
services (and standard Bluetooth services) led to a bed type, with no matched
name or manufacturer record, a device without a name is not offered, and one
with a name is offered as uncertain: the flow then says it may not be a bed.
Reviews of a configured bed's route use `detect_bed_type_detailed()`, without
that rule. A new bed is saved under the current route, never a compatibility
ID such as `dewertokin`; entries that already have one keep it.
