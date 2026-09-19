"""Sample the national point lattice out of the downloaded IMD .grd files.

Each .grd is one IMD rainfall day (24h ending 0830 IST, i.e. 0300-0300 UTC),
so the file's date label IS the IMD day D -- no time shifting is needed on
this side. The shifting happens on the forecast side, in fetch_openmeteo.py.
"""
from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import pandas as pd

from config import (IMD_BYTES, IMD_GRD, IMD_MISSING, IMD_NLAT, IMD_NLON,
                    INTERIM)

OUT = INTERIM / "imd_daily.parquet"


def date_from_name(p) -> dt.date | None:
    try:
        yy, mm, dd = p.stem.replace("rain_ind0.25_", "").split("_")
        return dt.date(2000 + int(yy), int(mm), int(dd))
    except Exception:
        return None


def main() -> int:
    pts = pd.read_csv(INTERIM / "points.csv")
    rows_i = pts.row.to_numpy()
    cols_i = pts.col.to_numpy()
    ids = pts.point_id.to_numpy()

    files = sorted(p for p in IMD_GRD.glob("*.grd")
                   if p.stat().st_size == IMD_BYTES)
    print(f"IMD grids on disk: {len(files)}")
    if not files:
        sys.exit("no grids yet")

    frames, bad = [], 0
    for p in files:
        d = date_from_name(p)
        if d is None:
            bad += 1
            continue
        g = np.fromfile(p, dtype="<f4").reshape(IMD_NLAT, IMD_NLON)
        vals = g[rows_i, cols_i].astype("float64")
        vals[vals <= IMD_MISSING + 1] = np.nan
        frames.append(pd.DataFrame({"point_id": ids,
                                    "date": pd.Timestamp(d),
                                    "imd_mm": vals}))
    df = pd.concat(frames, ignore_index=True)
    n_before = len(df)
    df = df.dropna(subset=["imd_mm"])
    df.to_parquet(OUT, index=False)

    print(f"unparseable filenames : {bad}")
    print(f"point-days            : {n_before} -> {len(df)} after dropping -999")
    print(f"date range            : {df.date.min().date()} .. {df.date.max().date()}")
    print(f"points                : {df.point_id.nunique()}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
