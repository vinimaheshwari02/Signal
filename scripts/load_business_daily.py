"""Load business_daily.csv into the business_daily table. Safe to run again: rows are replaced.

usage: python scripts/load_business_daily.py path/to/business_daily.csv
           [--db postgresql://signal:signal@localhost:5432/signal]
"""
import argparse
import csv

import psycopg

COLUMNS = ["orders", "revenue_gbp", "payment_attempts", "payment_failures", "deliveries_due",
           "deliveries_late", "returns_requested", "search_sessions"]

UPSERT_SQL = """
INSERT INTO business_daily (tenant_id, market, day, orders, revenue_gbp, payment_attempts,
                            payment_failures, deliveries_due, deliveries_late, returns_requested,
                            search_sessions)
VALUES (%(tenant)s, %(market)s, %(date)s, %(orders)s, %(revenue_gbp)s, %(payment_attempts)s,
        %(payment_failures)s, %(deliveries_due)s, %(deliveries_late)s, %(returns_requested)s,
        %(search_sessions)s)
ON CONFLICT (tenant_id, market, day) DO UPDATE SET
  orders = EXCLUDED.orders, revenue_gbp = EXCLUDED.revenue_gbp,
  payment_attempts = EXCLUDED.payment_attempts, payment_failures = EXCLUDED.payment_failures,
  deliveries_due = EXCLUDED.deliveries_due, deliveries_late = EXCLUDED.deliveries_late,
  returns_requested = EXCLUDED.returns_requested, search_sessions = EXCLUDED.search_sessions
"""

parser = argparse.ArgumentParser()
parser.add_argument("csv_file")
parser.add_argument("--db", default="postgresql://signal:signal@localhost:5432/signal")
args = parser.parse_args()

rows = []
with open(args.csv_file, newline="", encoding="utf-8") as csv_file:
    for row in csv.DictReader(csv_file):
        for column in COLUMNS:
            if row[column].strip() == "":
                raise SystemExit(f"empty {column} on {row['date']} {row['tenant']} {row['market']}")
        rows.append(row)

with psycopg.connect(args.db) as conn:
    with conn.cursor() as cursor:
        cursor.executemany(UPSERT_SQL, rows)

days = set()
for row in rows:
    days.add(row["date"])
print(f"loaded {len(rows)} rows, {min(days)} to {max(days)}")
