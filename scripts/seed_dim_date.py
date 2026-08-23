"""Populate dim_date for a tenant schema.

Usage: python3 scripts/seed_dim_date.py --schema tenant_xxx --start 2023-04-01 --end 2027-03-31
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import psycopg

from src.ingest.calendar import generate_dim_date_rows

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")

COLUMNS = ["date_key", "day_of_month", "month_num", "month_name", "calendar_year",
           "calendar_quarter", "fiscal_year", "fiscal_year_label", "fiscal_quarter",
           "fiscal_month_num", "period_key", "is_month_end", "is_quarter_end",
           "is_fiscal_year_end", "days_in_month"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schema", required=True)
    p.add_argument("--start", type=date.fromisoformat, default=date(2020, 4, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date(2030, 3, 31))
    args = p.parse_args()

    rows = generate_dim_date_rows(args.start, args.end)
    placeholders = ", ".join(["%s"] * len(COLUMNS))
    col_list = ", ".join(COLUMNS)
    sql = (f'INSERT INTO "{args.schema}".dim_date ({col_list}) VALUES ({placeholders}) '
           f'ON CONFLICT (date_key) DO NOTHING')

    # autocommit=True previously meant one implicit commit per row -- 2557
    # individual round trips to the database. Against a local Postgres
    # (sub-millisecond latency) that's invisible; against a real remote
    # connection it was taking close to a minute on its own. A single
    # transaction, sent as one pipelined batch, does the same insert in one
    # round trip's worth of latency instead of 2557.
    with psycopg.connect(DB_URL, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            with conn.pipeline():
                cur.executemany(sql, [[r[c] for c in COLUMNS] for r in rows])
        conn.commit()
    print(f"Seeded {len(rows)} dim_date rows into {args.schema} ({args.start} to {args.end})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
