"""Generate config/metrics/<metric_id>.yml from corpus/05 + corpus/05a.

Implements: corpus/12 sprint 0 item 1 ("Generate /config/metrics/ from /corpus/05
and /corpus/05a, one contract file per metric").

Eight metrics (net_revenue, gross_margin_pct, dso, operating_cost_cm1, cm1, cm2,
corporate_overhead, gmv) have a fully worked contract in corpus/05a -- those are
written out as-is, plus the registry-level fields from corpus/05 that 05a doesn't
carry (label, category, profile, p0_ask/p0_statement, dimensions, time_grain,
comparisons, allowed_filters). The remaining 53 metrics have no worked 05a
contract, so their config file is built directly from corpus/05's columns --
nothing is invented to fill the shape of a "full" contract that the corpus itself
does not provide for those metrics.
"""
import csv
import sys
from pathlib import Path

import yaml

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
OUT_DIR = Path(__file__).resolve().parent.parent / "config" / "metrics"


def load_registry():
    with (CORPUS / "05_SPEQULA_METRIC_REGISTRY.csv").open(newline="") as f:
        return list(csv.DictReader(f))


def load_contracts():
    data = yaml.safe_load((CORPUS / "05a_SPEQULA_METRIC_CONTRACTS.yml").read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def pipe_list(value: str):
    return [v for v in value.split("|") if v] if value else []


def main():
    registry = load_registry()
    contracts = load_contracts()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob("*.yml"):
        f.unlink()

    n_worked, n_registry_only = 0, 0
    compiles_no = []

    for row in registry:
        mid = row["metric_id"]
        compiles = row["compiles"].strip().lower() == "yes"
        if not compiles:
            compiles_no.append(mid)

        registry_fields = {
            "metric_id": mid,
            "label": row["label"],
            "category": row["category"],
            "profile": row["profile"],
            "p0_ask": row["p0_ask"].strip().lower() == "yes",
            "p0_statement": row["p0_statement"].strip().lower() == "yes",
            "definition": row["definition"],
            "formula": row["formula"],
            "unit": row["unit"],
            "source_facts": pipe_list(row["source_facts"]),
            "dimensions": pipe_list(row["dimensions"]),
            "time_grain": row["time_grain"],
            "time_logic": row["time_logic"],
            "aggregation": row["aggregation"],
            "comparisons": pipe_list(row["comparisons"]),
            "allowed_filters": pipe_list(row["allowed_filters"]),
            "dependencies": pipe_list(row["dependencies"]),
            "alternative_definitions": row["alternative_definitions"] or None,
            "override_allowed": row["override_allowed"].strip().lower() == "yes",
            "governed_by": pipe_list(row["decisions"]),
            "unresolved_decisions": pipe_list(row["unresolved_decisions"]),
            "compiles": compiles,
            "version": int(row["version"]),
            "owner": row["owner"],
        }

        if mid in contracts:
            n_worked += 1
            out = {
                "source": "corpus/05a_SPEQULA_METRIC_CONTRACTS.yml (worked contract)",
                "registry": registry_fields,
                "contract": contracts[mid],
            }
        else:
            n_registry_only += 1
            out = {
                "source": "corpus/05_SPEQULA_METRIC_REGISTRY.csv (registry row only; "
                          "no worked contract exists in corpus/05a for this metric)",
                "registry": registry_fields,
            }

        with (OUT_DIR / f"{mid}.yml").open("w") as f:
            f.write(f"# Generated from corpus/05 and corpus/05a for metric '{mid}'. Do not hand-edit.\n")
            yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=100)

    print(f"Wrote {len(registry)} metric contracts to {OUT_DIR}")
    print(f"  worked (05a) contracts: {n_worked}, registry-only: {n_registry_only}")
    print(f"  compiles=no ({len(compiles_no)}): {', '.join(sorted(compiles_no))}")
    print(f"  compiles=yes: {len(registry) - len(compiles_no)}")


if __name__ == "__main__":
    sys.exit(main())
