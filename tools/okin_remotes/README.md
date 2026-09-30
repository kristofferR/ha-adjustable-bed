# Okin UUID remote-code table regeneration

This directory regenerates `custom_components/adjustable_bed/beds/okin_uuid_remotes.py`
(the per-remote-code keycode table) and the `OKIMAT_VARIANTS` /
`OKIN_DOT_VARIANTS` dropdowns in `const.py`.

## Source of truth

DewertOkin's **FurniMove / OkinSmartComfort** app resolves each handset code
against a live AWS backend at pairing time (the bundled `handsetlist.csv` is
only a stale seed). The backend returns authoritative 32-bit keycodes and
timing metadata per remote code:

- Base (production): `https://2df12gl0m0.execute-api.eu-central-1.amazonaws.com/prod`
- `GET /mobile-data/button/{code}` — keycodes (the table we want)
- `GET /mobile-data/object/{code}` — model description
- Header: `authorizationToken: 9FIqFcwHRgdlyPa2MgVizuwuLH0mxhkN`

These values were extracted from the FurniMove 2.0.1 APK
(`disassembly/output/com.dewertokin.okinsmartcomfort/`). The API/token may
change; re-extract from a newer APK's `resources.arsc` if fetches start failing.

## Pipeline

The captured data is committed as `master.json` so the table can be regenerated
**without** re-hitting the backend:

```bash
cd tools/okin_remotes
uv run gen_module.py   # -> okin_uuid_remotes.py (copy into beds/)
                       #    + gen_okimat_variants.py (OKIMAT_VARIANTS body for const.py)
```

To refresh `master.json` from the network (rarely needed), provide a text file
with one remote ID per line. Include the `RemoteID` values from
`handsetlist.csv` and the already-shipped codes in `master.json`. The example
path below is your supplied file, not a file included in this repository.

```bash
# Fetch object and button responses for the supplied IDs
uv run fetch_handsets.py "cache" "/path/to/remote-ids.txt"
# Rebuild the normalized dataset from the cached responses
uv run build_master.py        # -> master.json
```

The fetcher preserves existing cache files. Use a fresh cache when refreshing
previously fetched IDs. No ID-sweep script is shipped here; add independently
verified new IDs to your input file before fetching.

## Notes

- **Flat is per-code.** Two codes in the same model family can use different
  Flat values, so the table stores each code's exact values (no family lumping).
- **UBL timing is not a repeat count.** FurniMove repeats the light key only
  while the user keeps touching it; the UBL path does not consult the backend's
  `duration` or `frequency` fields. Generated light commands are therefore
  single keycodes. Memory-save timing remains an explicit hold duration.
- **Pruned codes.** ~87 codes the backend no longer serves inherit keycodes from
  a live code with the identical capability signature (`csv-inherit:<code>`), or
  are rebuilt from the universal keycode map (`csv-reconstruct`) when no sibling
  exists. The `source` field on each entry records which.
- **DOT codes.** `build_master.DOT_CODES` marks the "DOT PROTOCOL" / RF1058 /
  RF34 / RF6707 codes (90167, 91983, 93558, 97450, 97544, 98035). They reuse
  the handset backend but their boxes speak CB24-style 7-byte frames over
  Nordic UART with a positionally re-numbered motor layout and
  Flat=0x08000000. They are emitted with `protocol: "dot"` (driving the
  `okin_dot` bed type and `OKIN_DOT_VARIANTS`) and are kept out of the
  csv-inherit pool so standard codes never inherit DOT keycodes. See
  `docs/beds/okin-dot.md`.
