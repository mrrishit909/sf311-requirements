"""Step 4: the duplicate-warning spike, run for a few radius/window settings so the requirement's threshold is chosen on evidence.

    ./venv/bin/python spike.py      -> results/duplicate_spike.csv, results/duplicate_spike_by_service.csv (50 m, 3 days)
"""
from pathlib import Path

import duckdb
import pandas as pd

import evidence as E

SETTINGS = [(25, 1), (50, 3), (50, 7), (100, 7), (200, 7)]     # (radius in metres, look-back in days)


def main():
    con = duckdb.connect(str(E.DB), read_only=True)
    sql = (E.SQL / "03_duplicate_spike.sql").read_text()
    rows = [con.execute(sql.replace("{radius_m}", str(r)).replace("{days}", str(d))).df() for r, d in SETTINGS]
    out = pd.concat(rows, ignore_index=True)
    out[out["service"] == "All services"].to_csv(E.HERE / "results" / "duplicate_spike.csv", index=False)
    out[(out["radius_m"] == 50) & (out["days"] == 3)].to_csv(E.HERE / "results" / "duplicate_spike_by_service.csv", index=False)
    print(out[out["service"] == "All services"].to_string(index=False))
    print(out[(out["radius_m"] == 50) & (out["days"] == 3)].to_string(index=False))


if __name__ == "__main__":
    main()
