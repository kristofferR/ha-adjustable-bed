# /// script
# dependencies = ["httpx"]
# ///
"""Fetch DewertOkin handset object+button maps by remote ID, cache to disk."""
import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "https://2df12gl0m0.execute-api.eu-central-1.amazonaws.com/prod"
TOK = "9FIqFcwHRgdlyPa2MgVizuwuLH0mxhkN"
HEADERS = {"authorizationToken": TOK}
CACHE = Path(sys.argv[1] if len(sys.argv) > 1 else "cache")
CACHE.mkdir(exist_ok=True)

sem = asyncio.Semaphore(6)


async def fetch_one(client: httpx.AsyncClient, kind: str, rid: str) -> None:
    out = CACHE / f"{rid}_{kind}.json"
    if out.exists():
        return
    async with sem:
        for attempt in range(3):
            try:
                r = await client.get(f"{BASE}/mobile-data/{kind}/{rid}", headers=HEADERS, timeout=25)
                out.write_text(json.dumps({"status": r.status_code, "body": r.text}))
                return
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    out.write_text(json.dumps({"status": -1, "body": f"ERR {e}"}))
                else:
                    await asyncio.sleep(1.5)


async def main() -> None:
    ids = [x.strip() for x in Path(sys.argv[2]).read_text().splitlines() if x.strip()]
    print(f"Fetching {len(ids)} IDs (object+button)...", flush=True)
    async with httpx.AsyncClient() as client:
        tasks = []
        for rid in ids:
            tasks.append(fetch_one(client, "object", rid))
            tasks.append(fetch_one(client, "button", rid))
        # progress in chunks
        for i in range(0, len(tasks), 40):
            await asyncio.gather(*tasks[i : i + 40])
            print(f"  {min(i + 40, len(tasks))}/{len(tasks)}", flush=True)
    print("done", flush=True)


asyncio.run(main())
