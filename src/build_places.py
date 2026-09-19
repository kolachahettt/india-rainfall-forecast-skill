"""Build web/data/places.json — the decision tool's place lookup.

This is a UI convenience, NOT analysis data. Nothing on the page is derived
from it; it only turns a typed place name into a latitude and longitude so
the tool can snap to the nearest of the study's 139 grid cells.

Source: GeoNames India dump (CC BY 4.0). Selection is every administrative
seat — state and district headquarters — plus the most populous remaining
towns, deduplicated by name within 60 km, capped at 700 entries.
"""
from __future__ import annotations

import io
import json
import math
import sys
import zipfile

import requests

from config import WEB_DATA

DUMP = "https://download.geonames.org/export/dump/IN.zip"
ADMIN1 = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
SEATS = ("PPLC", "PPLA", "PPLA2", "PPLA3")
LIMIT = 700
DEDUPE_KM = 60
COLS = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon",
        "fclass", "fcode", "country", "cc2", "admin1", "admin2", "admin3",
        "admin4", "population", "elevation", "dem", "timezone", "moddate"]


def km(a_lat, a_lon, b_lat, b_lon):
    dla, dlo = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = (math.sin(dla / 2) ** 2 + math.cos(math.radians(a_lat))
         * math.cos(math.radians(b_lat)) * math.sin(dlo / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def main() -> int:
    print("fetching GeoNames ...", flush=True)
    states = {}
    for line in requests.get(ADMIN1, timeout=120).text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("IN."):
            states[parts[0].split(".")[1]] = parts[1]

    blob = requests.get(DUMP, timeout=600).content
    rows = []
    with zipfile.ZipFile(io.BytesIO(blob)).open("IN.txt") as fh:
        for line in io.TextIOWrapper(fh, encoding="utf-8"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 19:
                continue
            d = dict(zip(COLS, f))
            if d["fclass"] != "P":
                continue
            try:
                rows.append((d["asciiname"] or d["name"],
                             states.get(d["admin1"], ""),
                             float(d["lat"]), float(d["lon"]),
                             int(d["population"] or 0), d["fcode"]))
            except ValueError:
                continue
    print(f"  {len(rows):,} populated places")

    ordered = ([r for r in rows if r[5] in SEATS]
               + sorted((r for r in rows if r[5] not in SEATS),
                        key=lambda r: -r[4]))
    picked, seen = [], set()
    for r in ordered:
        k = (r[0].lower(), r[1])
        if k in seen:
            continue
        if any(q[0].lower() == r[0].lower()
               and km(r[2], r[3], q[2], q[3]) < DEDUPE_KM for q in picked):
            continue
        seen.add(k)
        picked.append(r)
        if len(picked) >= LIMIT:
            break

    out = {
        "note": ("Place lookup for the decision tool only. Not analysis data: "
                 "no number on this page is derived from it."),
        "source": "GeoNames (geonames.org), India dump, populated places",
        "licence": "CC BY 4.0",
        "selection": ("all administrative seats (state and district "
                      "headquarters) plus the most populous remaining towns, "
                      "deduplicated"),
        "fields": ["name", "state", "lat", "lon"],
        "places": [[r[0], r[1], round(r[2], 3), round(r[3], 3)]
                   for r in picked],
    }
    txt = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    (WEB_DATA / "places.json").write_text(txt, encoding="utf-8")
    seats = sum(1 for r in picked if r[5] in SEATS)
    print(f"  wrote {len(picked)} places ({seats} administrative seats, "
          f"{len({r[1] for r in picked})} states), {len(txt)/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
