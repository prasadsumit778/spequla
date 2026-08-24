"""Generate config/taxonomy.yml from corpus/06a_SPEQULA_COA_MAPPING_TEMPLATE.xlsx's
Canonical Classes tab.

Implements: corpus/12 sprint 0 item 1 ("Generate /config/taxonomy.yml from
/corpus/06 section 3"). The taxonomy is PROVISIONAL VERSION 0 per corpus/06
section 3's own heading -- this generator transcribes it as-is and does not
correct, merge or add classes.

Sourced from 06a rather than 06's own markdown table (the first version of
this script did the latter): 06 section 3 states statement_line per-class
only for revenue/contra-revenue (3.1), and only in prose, sometimes with an
unresolved "X or Y" ("gross_revenue or cogs credit"), for 3.2-3.6 -- and
never assigns one at all for balance sheet classes (3.5), on the grounds that
guessing one would violate CLAUDE.md 3.1. 06a's Canonical Classes tab is
06's own named companion file and gives a single, disambiguated
statement_line for all 82 classes including every balance sheet class (e.g.
asset.cash_bank -> 'cash', liability.trade_payable -> 'accounts_payable') --
that disambiguation is what src/mapping/review.py's _write_map_account needs,
since map_account.statement_line is NOT NULL per corpus/04 section 3.7 and a
null value there was a live bug waiting to fire the first time a balance
sheet account got mapped.
"""
import sys
from pathlib import Path

import openpyxl
import yaml

XLSX = Path(__file__).resolve().parent.parent / "corpus" / "06a_SPEQULA_COA_MAPPING_TEMPLATE.xlsx"
OUT = Path(__file__).resolve().parent.parent / "config" / "taxonomy.yml"

JUDGEMENT_CLASSES = {
    "exceptional.one_off",
    "opex.owner_remuneration",
    "opex.related_party_charges",
    "cogs.absorption_variance",
    "liability.bill_discounting",
    "liability.debt_related_party",
}

STMT_SECTION_MAP = {"P&L": "pnl", "BS": "bs", "MEMO": "memo"}


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["Canonical Classes"]
    rows = list(ws.iter_rows(values_only=True))

    out = []
    for row in rows:
        cls = row[0]
        stmt = row[1]
        if not cls or not isinstance(cls, str) or stmt not in STMT_SECTION_MAP:
            continue  # title, subtitle, header row, blank separator, or the footer count line
        statement_line, profile, decision, notes = row[2], row[3], row[4], row[5]
        note_parts = [p for p in (notes, f"Decision: {decision}" if decision else None,
                                    f"Profile: {profile}" if profile and profile != "Both" else None) if p]
        out.append({
            "class": cls,
            "statement_section": STMT_SECTION_MAP[stmt],
            "statement_line": statement_line,
            "judgement_class": cls in JUDGEMENT_CLASSES,
            "notes": "; ".join(note_parts) if note_parts else None,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        f.write("# Generated from corpus/06a_SPEQULA_COA_MAPPING_TEMPLATE.xlsx's Canonical Classes\n")
        f.write("# tab (corpus/06's own named companion file). Do not hand-edit.\n")
        f.write("# PROVISIONAL, version 0 -- per corpus/06 section 3's own heading. Revise against a\n")
        f.write("# real chart of accounts before freezing for company two.\n")
        yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True, width=100)

    n_judgement = sum(1 for r in out if r["judgement_class"])
    n_null_line = sum(1 for r in out if not r["statement_line"])
    print(f"Wrote {len(out)} canonical classes to {OUT} ({n_judgement} judgement classes, "
          f"{n_null_line} with no statement_line)")
    if len(out) != 86:
        print(f"WARNING: expected 86 classes per 06a's own footer count, got {len(out)}", file=sys.stderr)
        return 1
    if n_null_line:
        print(f"WARNING: {n_null_line} classes still have no statement_line", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
