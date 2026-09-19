"""Build web/data/places.json — the decision tool's place lookup.

This is a UI convenience, NOT analysis data. Nothing on the page is derived
from it; it only turns a typed place name into a latitude and longitude so
the tool can snap to the nearest of the study's 139 grid cells.

Source: GeoNames (CC BY 4.0) — the India dump plus the admin1 and admin2
code tables.

WHY THIS WAS REBUILT. The first version selected "administrative seats" by
GeoNames feature code (PPLC / PPLA / PPLA2 / PPLA3) and then filled to 700 by
population. GeoNames does not tag Indian district seats reliably: Jaisalmer,
for instance, is a plain PPL with 67,604 people, so it was neither picked as a
seat nor large enough to survive the population cut. Nine of eighteen sampled
district headquarters were missing, while the page claimed every one was
present.

The fix is to enumerate districts first and find a representative for each,
rather than hoping the feature codes cover them. For each district in
GeoNames' admin2 table, a representative is chosen by, in order:

  1. a place inside that district tagged PPLA2 or PPLA3 — GeoNames' own
     "seat of an administrative division" marker, where it exists;
  2. a place inside that district whose name is the district's name — most
     Indian districts are named for their headquarters;
  3. the most populous place inside that district, if any of them carries a
     population at all;
  4. otherwise the MEDIAN position of the district's indexed places, labelled
     with the district's own name.

Route 4 exists because 17 districts — recently created ones in the Northeast
and the high Himalaya — have no population figures and no seat tag anywhere
inside them, so "most populous" degenerates to an arbitrary hamlet. Kinnaur
has 254 indexed places, every one at population zero; the old rule picked
Yangpa. A median position is at least defensibly inside the district.

Route 3 is NOT a headquarters claim (a district's largest town is often not
its seat: Jeypore is bigger than Koraput), and route 4 is not a place at all.
The counts per route go into the payload so the page can state what it
actually has rather than asserting completeness.

What matters here is weaker than "find the headquarters". The lookup only has
to land a point close enough to pick the nearest of 139 cells on a 1.5-degree
lattice, whose spacing is about 165 km. Most Indian districts are smaller than
that, so any point inside one usually selects the same cell. The district name
is carried on every entry and the typeahead searches it, so a district whose
seat has a different name — Sirmaur/Nahan, Kinnaur/Reckong Peo — is reachable
by either.

Population is carried so the typeahead can rank sensibly, and so that
ambiguous names (Bilaspur, Hamirpur, Aurangabad) sort usefully.
"""
from __future__ import annotations

import io
import json
import math
import sys
import zipfile
from collections import defaultdict

import requests

from config import WEB_DATA

DUMP = "https://download.geonames.org/export/dump/IN.zip"
ADMIN1 = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"
ADMIN2 = "https://download.geonames.org/export/dump/admin2Codes.txt"
CAPITALS = ("PPLC", "PPLA")            # national and state capitals
DISTRICT_SEATS = ("PPLA2", "PPLA3")    # district / sub-district seats
EXTRA_TOWNS = 400                      # largest remaining towns, after districts
DEDUPE_KM = 60
COLS = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon",
        "fclass", "fcode", "country", "cc2", "admin1", "admin2", "admin3",
        "admin4", "population", "elevation", "dem", "timezone", "moddate"]


def km(a_lat, a_lon, b_lat, b_lon):
    dla, dlo = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = (math.sin(dla / 2) ** 2 + math.cos(math.radians(a_lat))
         * math.cos(math.radians(b_lat)) * math.sin(dlo / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def codes(url: str, prefix: str, col: int = 1) -> dict[str, str]:
    """col 1 is the name, col 2 the ASCII name. Use ASCII for admin2: 110 of
    India's 763 entries carry diacritics there while every place name in the
    dump is already transliterated, and mixing the two makes the suggestion
    list look broken ("Bilaspur, Bilaspur district")."""
    out = {}
    for line in requests.get(url, timeout=180).text.splitlines():
        p = line.split("\t")
        if len(p) > col and p[0].startswith(prefix):
            out[p[0]] = p[col] or p[1]
    return out


def main() -> int:
    print("fetching GeoNames code tables ...", flush=True)
    a1 = {k.split(".")[1]: v for k, v in codes(ADMIN1, "IN.").items()}
    a2 = codes(ADMIN2, "IN.", col=2)
    # GeoNames' admin2 slot for India is mostly districts, but Maharashtra
    # occupies five of them with revenue DIVISIONS. They are real
    # administrative units and give a usable point, but they are not
    # districts and the count must not pretend otherwise.
    n_div = sum(1 for v in a2.values() if v.split()[-1] in ("Division", "Region"))
    print(f"  {len(a1)} states/UTs, {len(a2)} second-order units "
          f"({len(a2) - n_div} districts, {n_div} divisions)")

    print("fetching the India dump ...", flush=True)
    blob = requests.get(DUMP, timeout=900).content
    places = []
    with zipfile.ZipFile(io.BytesIO(blob)).open("IN.txt") as fh:
        for line in io.TextIOWrapper(fh, encoding="utf-8"):
            f = line.rstrip("\n").split("\t")
            if len(f) < 19 or f[6] != "P":
                continue
            d = dict(zip(COLS, f))
            try:
                lat, lon = float(d["lat"]), float(d["lon"])
            except ValueError:
                continue
            places.append({
                "name": d["asciiname"] or d["name"],
                "state": a1.get(d["admin1"], ""),
                "dkey": f"IN.{d['admin1']}.{d['admin2']}"
                        if d["admin1"] and d["admin2"] else "",
                "lat": lat, "lon": lon,
                "pop": int(d["population"] or 0), "fcode": d["fcode"]})
    print(f"  {len(places):,} populated places")

    by_district = defaultdict(list)
    for p in places:
        if p["dkey"] in a2:
            by_district[p["dkey"]].append(p)

    # ---- one representative per district, by the four-step rule ----------
    picked, routes = [], defaultdict(int)
    for dkey, dname in sorted(a2.items()):
        cand = by_district.get(dkey, [])
        if not cand:
            # a district GeoNames indexes but places nothing inside (the two
            # Puducherry enclaves). Fall back to a nationwide name match.
            cand = [p for p in places if p["name"].lower() == dname.lower()]
            if not cand:
                routes["none"] += 1
                continue
            rep, route = max(cand, key=lambda p: p["pop"]), "name_nationwide"
        else:
            seats = [p for p in cand if p["fcode"] in DISTRICT_SEATS]
            exact = [p for p in cand if p["name"].lower() == dname.lower()]
            if seats:
                rep, route = max(seats, key=lambda p: p["pop"]), "seat_fcode"
            elif exact:
                rep, route = max(exact, key=lambda p: p["pop"]), "district_name"
            elif any(p["pop"] > 0 for p in cand):
                rep, route = max(cand, key=lambda p: p["pop"]), "largest_town"
            else:
                # no seat, no name match, no population anywhere: the
                # district's median position, named for the district
                lats = sorted(p["lat"] for p in cand)
                lons = sorted(p["lon"] for p in cand)
                mid = len(cand) // 2
                rep = {"name": dname, "state": cand[0]["state"],
                       "lat": lats[mid], "lon": lons[mid], "pop": 0,
                       "fcode": "", "dkey": dkey}
                route = "district_median"
        routes[route] += 1
        picked.append(dict(rep, district=dname, route=route))
    n_districts = len(picked)
    print(f"  districts represented: {n_districts} of {len(a2)}  "
          + "  ".join(f"{k}={v}" for k, v in sorted(routes.items())))

    # ---- state and UT capitals, if the district pass missed them ----------
    have = {(p["name"].lower(), p["state"]) for p in picked}
    n_caps = 0
    for p in sorted((p for p in places if p["fcode"] in CAPITALS),
                    key=lambda p: -p["pop"]):
        k = (p["name"].lower(), p["state"])
        if k in have:
            continue
        have.add(k)
        picked.append(dict(p, district=a2.get(p["dkey"], ""), route="capital"))
        n_caps += 1
    print(f"  capitals added: {n_caps}")

    # ---- largest remaining towns, deduplicated ---------------------------
    n_extra = 0
    for p in sorted(places, key=lambda p: -p["pop"]):
        if n_extra >= EXTRA_TOWNS:
            break
        k = (p["name"].lower(), p["state"])
        if k in have or p["pop"] < 1000:
            continue
        if any(q["name"].lower() == p["name"].lower()
               and km(p["lat"], p["lon"], q["lat"], q["lon"]) < DEDUPE_KM
               for q in picked):
            continue
        have.add(k)
        picked.append(dict(p, district=a2.get(p["dkey"], ""), route="town"))
        n_extra += 1
    print(f"  extra towns added: {n_extra}")

    # district is only carried when it adds something the name does not
    rows = [[p["name"], p["state"],
             "" if p["district"].lower() == p["name"].lower()
             else p["district"],
             round(p["lat"], 3), round(p["lon"], 3), p["pop"]]
            for p in sorted(picked, key=lambda p: -p["pop"])]

    out = {
        "note": ("Place lookup for the decision tool only. Not analysis data: "
                 "no number on this page is derived from it."),
        "source": "GeoNames (geonames.org): India dump, admin1 and admin2 "
                  "code tables",
        "licence": "CC BY 4.0",
        "fields": ["name", "state", "district", "lat", "lon", "pop"],
        "district_field_note": ("Empty when the district name is the same as "
                                "the place name, which is the usual case for "
                                "a headquarters."),
        "coverage": {
            "total": len(rows),
            "admin2_units_in_geonames": len(a2),
            "districts_in_geonames": len(a2) - n_div,
            "divisions_not_districts": n_div,
            "districts_represented": n_districts,
            "states_and_uts": len({p["state"] for p in picked if p["state"]}),
            "by_route": dict(sorted(routes.items())),
            "capitals_added": n_caps, "extra_towns": n_extra,
            "route_note": (
                "seat_fcode: GeoNames tags a district- or sub-district seat "
                "inside the district. district_name: no seat tag, but a place "
                "carries the district's own name, which in India is normally "
                "the headquarters. largest_town: neither, so the district's "
                "most populous place stands in -- these are NOT claimed to be "
                "headquarters. district_median: no seat, no name match and no "
                "population figures anywhere in the district, so the entry is "
                "the median position of its indexed places, labelled with the "
                "district's name. name_nationwide: the district contains no "
                "indexed place at all, so a nationwide name match was used."),
        },
        "selection": (
            "One representative for every district in GeoNames' admin2 index "
            "for India, plus state and union-territory capitals, plus the "
            "largest remaining towns. Districts are never deduplicated away; "
            f"only the extra towns are, by name within {DEDUPE_KM} km."),
        "places": rows,
    }
    txt = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
    (WEB_DATA / "places.json").write_text(txt, encoding="utf-8")
    print(f"  wrote {len(rows)} places, {len(txt)/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
