"""Build the national sample of verification points.

Takes every SAMPLE_STRIDE-th cell of the IMD 0.25 deg grid and keeps those
that are land (valid, not -999) in a reference IMD file. A regular lattice
rather than a hand-picked set of cities: it covers every climate region
without the selection bias of choosing "interesting" places, and anyone can
regenerate the identical point list from one .grd file.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from config import (IMD_BYTES, IMD_GRD, IMD_LAT0, IMD_LON0, IMD_MISSING,
                    IMD_NLAT, IMD_NLON, IMD_STEP, INTERIM, SAMPLE_STRIDE)

OUT = INTERIM / "points.csv"


def read_grd(path):
    a = np.fromfile(path, dtype="<f4")
    if a.size != IMD_NLAT * IMD_NLON:
        raise ValueError(f"{path}: unexpected size {a.size}")
    return a.reshape(IMD_NLAT, IMD_NLON)


def reference_grid():
    """A mid-monsoon file: land mask is identical across dates, but a wet day
    makes it obvious in QA that the values are real rainfall."""
    cands = sorted(p for p in IMD_GRD.glob("*.grd")
                   if p.stat().st_size == IMD_BYTES)
    if not cands:
        sys.exit("no IMD .grd files yet -- run fetch_imd.py first")
    for p in cands:
        if "_08_" in p.name:
            return p
    return cands[0]


def main() -> int:
    ref = reference_grid()
    g = read_grd(ref)
    land = g > IMD_MISSING + 1
    print(f"reference grid : {ref.name}")
    print(f"land cells     : {int(land.sum())} of {land.size}")

    rows = []
    for i in range(0, IMD_NLAT, SAMPLE_STRIDE):
        for j in range(0, IMD_NLON, SAMPLE_STRIDE):
            if not land[i, j]:
                continue
            rows.append({
                "point_id": f"p{len(rows):04d}",
                "row": i, "col": j,
                "lat": round(IMD_LAT0 + i * IMD_STEP, 4),
                "lon": round(IMD_LON0 + j * IMD_STEP, 4),
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"stride         : {SAMPLE_STRIDE} cells "
          f"({SAMPLE_STRIDE * IMD_STEP:.2f} deg)")
    print(f"sample points  : {len(df)}")
    print(f"lat range      : {df.lat.min()} .. {df.lat.max()}")
    print(f"lon range      : {df.lon.min()} .. {df.lon.max()}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
