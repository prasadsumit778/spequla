"""CLI entrypoint for the synthetic reference dataset generator.

Implements corpus/12 sprint 0 item 3's exit criterion: "one command produces
a working environment with both synthetic companies loaded." This script
generates the deterministic dataset for one company and, with --land, lands
every generated file immutably into object storage under that tenant's
prefixed path (corpus/04 section 6) -- ready for sprint 1's ingestion to pick
up. It does not itself write canonical facts; that is sprint 1's ingestion
pipeline, not sprint 0's generator.

Usage:
    python3 synthetic/generate.py --company manufacturer --seed 42 [--tenant-id UUID] [--land]
    python3 synthetic/generate.py --company consumer --seed 42 [--tenant-id UUID] [--land]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--company", choices=["manufacturer", "consumer"], required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tenant-id", default=None, help="If set, lands files under this tenant's storage prefix")
    p.add_argument("--land", action="store_true", help="Upload generated files to object storage")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else DATA_ROOT / args.company

    if args.company == "manufacturer":
        from synthetic.manufacturer.engine import build_company
        from synthetic.manufacturer.write import write_all
        data = build_company(seed=args.seed)
        write_all(data, out_dir, schema_hash_defect_month=22)
        print(f"Manufacturer dataset written to {out_dir} "
              f"({len(data.coa)} ledgers, {len(data.months)} months, "
              f"{len(data.defect_log.entries)} defects logged)")
    else:
        from synthetic.consumer.engine import build_consumer_company
        from synthetic.consumer.write import write_all
        data = build_consumer_company(seed=args.seed)
        write_all(data, out_dir)
        print(f"Consumer dataset written to {out_dir} "
              f"({len(data.coa)} ledgers, {len(data.months)} months, "
              f"{len(data.defect_log.entries)} defects logged)")

    if args.land:
        if not args.tenant_id:
            print("error: --land requires --tenant-id", file=sys.stderr)
            return 1
        from src.ingest.landing import land_file
        files = sorted(out_dir.glob("*.csv")) + sorted(out_dir.glob("*.md"))
        for i, f in enumerate(files, start=1):
            land_file(args.tenant_id, load_run_id=0, file_name=f.name, data=f.read_bytes())
        print(f"Landed {len(files)} files to object storage under tenant {args.tenant_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
