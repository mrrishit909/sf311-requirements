"""Step 1: freeze one snapshot of San Francisco 311 cases (12 months requested Sep 2025 - Aug 2026).

    ./venv/bin/python download.py     -> data/raw/cases.parquet (not committed: rows carry addresses), results/pull.json

Source: DataSF "311 Cases" (dataset vw6y-z8j6), SODA API. The dataset updates nightly and open cases change status,
so everything downstream runs on this one frozen file; results/pull.json records when DataSF built it.
"""
import io
import json
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import pandas as pd

HERE = Path(__file__).parent
RAW = HERE / "data" / "raw"
API = "https://data.sf.gov/resource/vw6y-z8j6.csv"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
COLS = ["service_request_id", "requested_datetime", "closed_date", "updated_datetime", "status_description", "status_notes",
        "agency_responsible", "service_name", "service_subtype", "service_details", "source", "lat", "long", "media_url",
        "supervisor_district", "analysis_neighborhood", "data_as_of"]
MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 9), (2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 9)]]
LIMIT = 200_000                                                    # above any month's volume; asserted below


def get(params):
    ctx = ssl.create_default_context(cafile=certifi.where())     # /etc/ssl/cert.pem lacks GlobalSign Root R46
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    for attempt in range(5):                                      # the API drops long transfers now and then
        try:
            return urllib.request.urlopen(req, context=ctx, timeout=600).read()
        except (OSError, urllib.error.URLError) as e:
            print("retry", attempt + 1, e)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("API kept failing")


def month(m):
    """One request per month: deep $offset paging over the whole year made the API stall for many minutes."""
    y, mo = map(int, m.split("-"))
    nxt = f"{y + mo // 12}-{mo % 12 + 1:02d}"
    where = f"requested_datetime >= '{m}-01T00:00:00' AND requested_datetime < '{nxt}-01T00:00:00'"
    n = int(pd.read_csv(io.BytesIO(get({"$select": "count(*) AS n", "$where": where})))["n"][0])
    df = pd.read_csv(io.BytesIO(get({"$select": ",".join(COLS), "$where": where, "$limit": LIMIT})), dtype=str)
    assert len(df) == n < LIMIT, (m, len(df), n)
    print(m, n, flush=True)
    return df


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        df = pd.concat(pool.map(month, MONTHS), ignore_index=True)
    assert df["service_request_id"].is_unique
    df.to_parquet(RAW / "cases.parquet", index=False)
    (HERE / "results").mkdir(exist_ok=True)
    pull = {"dataset": "DataSF 311 Cases (vw6y-z8j6)", "requested_from": "2025-09-01", "requested_to": "2026-08-31",
            "rows": len(df), "data_as_of": df["data_as_of"].max()}
    (HERE / "results" / "pull.json").write_text(json.dumps(pull, indent=2) + "\n")
    print(pull)


if __name__ == "__main__":
    main()
