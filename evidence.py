"""Step 2-3: clean the cases, classify how each closed case ended, and measure the evidence the requirements cite.

    ./venv/bin/python evidence.py     -> data/cases.duckdb, results/<name>.csv for every block in sql/02_evidence.sql

Every number in requirements.yaml points at one of these files.
"""
import re
from pathlib import Path

import duckdb

HERE = Path(__file__).parent
DB = HERE / "data" / "cases.duckdb"
RAW = HERE / "data" / "raw" / "cases.parquet"
SQL = HERE / "sql"


def blocks(path):
    text = path.read_text()
    return [(m.group(1).strip(), m.group(2).strip().rstrip(";")) for m in re.finditer(r"-- name: ([^\n]+)\n(.*?)(?=\n-- name:|\Z)", text, re.S)]


def build():
    if DB.exists():
        DB.unlink()
    con = duckdb.connect(str(DB))
    con.execute((SQL / "01_cases.sql").read_text().replace("{raw}", str(RAW)).replace("{rules}", str(HERE / "rules" / "outcomes.csv")))
    return con


def main():
    con = build()
    (HERE / "results").mkdir(exist_ok=True)
    for name, sql in blocks(SQL / "02_evidence.sql"):
        con.execute(f"COPY ({sql}) TO '{HERE / 'results' / (name + '.csv')}' (HEADER)")
        print(name, con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0], "rows")


if __name__ == "__main__":
    main()
