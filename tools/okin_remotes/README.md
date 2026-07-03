# Okin UUID remote-code table regeneration

This directory regenerates `custom_components/adjustable_bed/beds/okin_uuid_remotes.py`
(the per-remote-code keycode table) and the `OKIMAT_VARIANTS` dropdown in
`const.py`.

## Source of truth

DewertOkin's **FurniMove / OkinSmartComfort** app resolves each handset code
against a live AWS backend at pairing time (the bundled `handsetlist.csv` is
only a stale seed). The backend returns authoritative 32-bit keycodes and hold
timing per remote code:

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
uv run gen_module.py          # -> okin_uuid_remotes.py (copy into beds/)
uv run codegen.py             # -> gen_okimat_variants.py (OKIMAT_VARIANTS body)
```

To refresh `master.json` from the network (rarely needed):

```bash
# 1. Fetch known codes (handsetlist.csv IDs + already-shipped codes)
uv run fetch_handsets.py cache all_known_ids.txt
# 2. Sweep for codes newer than the CSV (object endpoint is cheap)
uv run sweep_objects.py sweep_ids.txt sweep_live.txt   # then fetch their buttons
# 3. Rebuild the normalized dataset
uv run build_master.py        # -> master.json
```

## Notes

- **Flat is per-code.** Two codes in the same model family can use different
  Flat values, so the table stores each code's exact values (no family lumping).
- **Pruned codes.** ~87 codes the backend no longer serves inherit keycodes from
  a live code with the identical capability signature (`csv-inherit:<code>`), or
  are rebuilt from the universal keycode map (`csv-reconstruct`) when no sibling
  exists. The `source` field on each entry records which.
- **Excluded codes.** `build_master.EXCLUDE` drops "DOT PROTOCOL" / RF1058 /
  RF34 / RF6707 codes (Flat=0x08000000, re-numbered layout) — they reuse the
  handset backend but are a different, incompatible command protocol.
