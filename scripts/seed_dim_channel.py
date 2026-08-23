"""Seed dim_channel.

Per corpus/04 table inventory: "Consumer pilots. Single default row for
manufacturing." D-046 (resolved, corpus/00): the seven canonical consumer
channels are "own website; marketplace (per marketplace); quick commerce
(per platform); owned retail (per store); franchise retail; distributor;
exports." Manufacturing gets its own single default row, not one of the
seven -- corpus/04 does not say manufacturing's channel is any specific one
of D-046's consumer taxonomy, only that a single default row exists so
fact tables referencing channel_key never need a nullable path.

Usage: python3 scripts/seed_dim_channel.py --schema tenant_xxx --tenant-id UUID --profile consumer|manufacturing
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://spequla:spequla@localhost:5432/spequla")

# D-046, corpus/00 resolved decisions.
CONSUMER_CHANNELS = [
    ("own_website", "Own website"),
    ("marketplace", "Marketplace"),
    ("quick_commerce", "Quick commerce"),
    ("owned_retail", "Owned retail"),
    ("franchise_retail", "Franchise retail"),
    ("distributor", "Distributor"),
    ("exports", "Exports"),
]
MANUFACTURING_CHANNELS = [("direct", "Direct sales")]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schema", required=True)
    p.add_argument("--tenant-id", required=True)
    p.add_argument("--profile", required=True, choices=["consumer", "manufacturing"])
    p.add_argument("--entity-id", type=int, default=1)
    args = p.parse_args()

    channels = CONSUMER_CHANNELS if args.profile == "consumer" else MANUFACTURING_CHANNELS

    with psycopg.connect(DB_URL, autocommit=True, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            for channel_type, channel_name in channels:
                cur.execute(
                    f'SELECT 1 FROM "{args.schema}".dim_channel WHERE tenant_id=%s AND entity_id=%s '
                    f'AND source_record_id=%s AND is_current',
                    (args.tenant_id, args.entity_id, channel_type),
                )
                if cur.fetchone():
                    continue
                cur.execute(
                    f'INSERT INTO "{args.schema}".dim_channel '
                    f'(tenant_id, entity_id, channel_type, channel_name, load_run_id, source_record_id) '
                    f'VALUES (%s, %s, %s, %s, 0, %s)',
                    (args.tenant_id, args.entity_id, channel_type, channel_name, channel_type),
                )
    print(f"Seeded {len(channels)} dim_channel row(s) ({args.profile}) into {args.schema}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
