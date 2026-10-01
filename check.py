"""The project's check: run after download.py, evidence.py, spike.py and spec.py.

    ./venv/bin/python check.py

The requirements are checked against the results files by spec.py; this checks the results files themselves, by
recomputing them a second way, in pandas, straight from the frozen raw pull:
1. exclusions, the closure-outcome rules (re-applied in Python), the outcome counts and the taxonomy's coverage
2. the parking response curve, closed-before-opened cases and the busiest minute
3. the duplicate spike's grid join, against a brute-force distance check on 400 random cases
"""
import json
import re

import duckdb
import numpy as np
import pandas as pd
import yaml

import evidence as E
import spec as S

R = E.HERE / "results"


def main():
    raw = pd.read_parquet(E.RAW)
    assert len(raw) == json.loads((R / "pull.json").read_text())["rows"]
    ex = pd.read_csv(R / "exclusions.csv").set_index("dropped")["cases"]
    assert ex["test cases"] == (raw["source"] == "Test").sum() and ex["no channel recorded"] == raw["source"].isna().sum()
    c = raw[raw["source"].notna() & (raw["source"] != "Test")].copy()
    assert ex["kept"] == len(c)

    # 1. outcome rules, applied with Python's re instead of DuckDB's regexp engine
    rules = pd.read_csv(E.HERE / "rules" / "outcomes.csv").sort_values("order")
    pats = [(re.compile(p), o) for p, o in zip(rules["pattern"], rules["outcome"])]
    closed = c[c["status_description"] == "Closed"].copy()

    def classify(note):
        if not isinstance(note, str) or not note.strip():
            return "unclassified"
        n = note.strip().lower().replace("_", " ")
        return next((o for p, o in pats if p.search(n)), "unclassified")

    closed["outcome"] = closed["status_notes"].map(classify)
    moved = closed["outcome"].eq("cannot_locate") & closed["service_name"].isin(["Parking Enforcement", "Encampment"])
    closed.loc[moved, "outcome"] = "not_found_on_arrival"
    mine = closed["outcome"].value_counts()
    theirs = pd.read_csv(R / "outcomes.csv").set_index("outcome")["cases"]
    assert mine.sort_index().equals(theirs.sort_index()), pd.concat([mine, theirs], axis=1)
    tq = pd.read_csv(R / "taxonomy_quality.csv").iloc[0]
    assert tq["coverage_pct"] >= 99 and tq["closed_cases"] == len(closed)

    # 2. parking response curve, data-quality count, busiest minute
    req = pd.to_datetime(closed["requested_datetime"])
    hrs = (pd.to_datetime(closed["closed_date"]) - req).dt.total_seconds() / 3600
    assert tq["closed_before_requested"] == (hrs < 0).sum()
    pk = closed[(closed["service_name"] == "Parking Enforcement") & (hrs >= 0)]
    h = hrs[pk.index]
    bucket = pd.cut(h, [0, 1, 2, 4, 8, np.inf], right=False, labels=["1: under 1 h", "2: 1-2 h", "3: 2-4 h", "4: 4-8 h", "5: 8 h or more"])
    curve = pk.groupby(bucket, observed=True)["outcome"].apply(lambda s: round(100 * (s == "not_found_on_arrival").mean(), 1))
    assert curve.to_dict() == pd.read_csv(R / "parking_response.csv").set_index("time_to_close")["not_found_pct"].to_dict()
    peak = pd.to_datetime(c["requested_datetime"]).dt.floor("min").value_counts().max()
    assert peak == pd.read_csv(R / "load_profile.csv")["peak_per_minute"][0]

    # 3. the spike's grid join finds exactly the cases a brute-force distance check finds (50 m, 3 days)
    con = duckdb.connect(str(E.DB), read_only=True)
    sql = (E.SQL / "03_duplicate_spike.sql").read_text().replace("{radius_m}", "50").replace("{days}", "3")
    flagged = set(con.execute(sql[:sql.index("\nSELECT 50 AS radius_m")] + "\nSELECT id FROM flagged").df()["id"])
    cases = con.execute("SELECT id, service, subtype, requested, closed, lat, lon FROM cases WHERE lat IS NOT NULL AND subtype IS NOT NULL").df()
    sample = cases[cases["id"].isin(set(con.execute("SELECT id FROM closed").df()["id"]))].sample(400, random_state=1)
    groups = dict(tuple(cases.groupby(["service", "subtype"])))
    for _, n in sample.iterrows():
        e = groups[(n["service"], n["subtype"])]
        e = e[(e["requested"] < n["requested"]) & (e["requested"] >= n["requested"] - pd.Timedelta(days=3))
              & (e["closed"].isna() | (e["closed"] > n["requested"]))]
        d = 2 * 6371000 * np.arcsin(np.sqrt(np.sin(np.radians(e["lat"] - n["lat"]) / 2) ** 2
                                            + np.cos(np.radians(n["lat"])) * np.cos(np.radians(e["lat"])) * np.sin(np.radians(e["lon"] - n["lon"]) / 2) ** 2))
        assert bool((d <= 50).any()) == (n["id"] in flagged), n["id"]

    S.validate(yaml.safe_load((E.HERE / "requirements.yaml").read_text()))
    print(f"OK: exclusions, the 14 outcome rules re-applied in Python ({tq['coverage_pct']}% of closed cases classified), "
          f"parking curve, data-quality count and busiest minute recompute from the raw pull; the spike's grid join matches "
          f"a brute-force check on 400 cases ({int(sample['id'].isin(flagged).sum())} flagged); every requirement's evidence matches")


if __name__ == "__main__":
    main()
