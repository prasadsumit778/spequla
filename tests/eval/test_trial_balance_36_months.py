"""Sprint 1 acceptance criterion: a trial balance generated from
fact_gl_entry matches the source trial balance exactly, to the rupee, for
all 36 months of the synthetic manufacturer.

Per corpus/12: "Acceptance: a trial balance generated from fact_gl_entry
matches the source trial balance exactly, to the rupee, for all 36 months of
the synthetic company." Per corpus/11 section 3.1 (financial accuracy,
GATING): "Exact, to the rupee. No tolerance."

This is an eval-tier test: it ingests the full synthetic dataset (400
ledgers, 36 months, ~4-5k GL lines) into a live tenant schema, so it is slow
by design and needs a live Postgres, same as the rest of tests/integration.
"""
from decimal import Decimal

import pytest

from src.ingest.calendar import month_end
from src.ingest.load_pipeline import load_coa_file, load_gl_file


def _write_csv(fieldnames, rows) -> bytes:
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


COA_FIELDS = ["account_code", "account_name", "parent_group", "account_type",
              "opening_balance", "opening_dr_cr", "cost_centre", "is_active"]
GL_FIELDS = ["voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
             "account_code", "account_name", "debit", "credit", "narration",
             "cost_centre", "party_name", "is_cancelled"]


@pytest.mark.eval
def test_trial_balance_ties_exactly_for_all_36_months(conn, tenant):
    from synthetic.manufacturer.engine import build_company
    tenant_id, schema = tenant
    data = build_company(seed=42)

    coa_rows = [{
        "account_code": l.account_code, "account_name": l.account_name,
        "parent_group": l.parent_group, "account_type": l.account_type,
        "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": l.cost_centre or "",
        "is_active": l.is_active,
    } for l in data.coa]
    coa_result = load_coa_file(conn, schema, tenant_id, 1, "COA.csv", _write_csv(COA_FIELDS, coa_rows), "pytest")
    conn.commit()
    assert coa_result.status == "succeeded"

    for i, d in enumerate(data.months):
        tag = f"{d.year:04d}-{d.month:02d}"
        raw = _write_csv(GL_FIELDS, data.gl_rows[i])
        r = load_gl_file(conn, schema, tenant_id, 1, f"GL_{tag}.csv", raw, "pytest")
        conn.commit()
        assert r.status == "succeeded", f"month {tag} failed to load: {r.blocked_reason}"

    mismatches = []
    for i, d in enumerate(data.months):
        tag = f"{d.year:04d}-{d.month:02d}"
        source_tb = {row["account_code"]: Decimal(row["closing_balance"]) for row in data.tb_rows[i]}

        with conn.cursor() as cur:
            cur.execute(
                f'SELECT da.source_account_code, SUM(fg.amount_base) '
                f'FROM "{schema}".fact_gl_entry fg JOIN "{schema}".dim_account da USING (account_key) '
                f'WHERE fg.tenant_id=%s AND fg.is_current AND fg.event_date <= %s '
                f'GROUP BY da.source_account_code',
                (tenant_id, month_end(d)),
            )
            computed_tb = {r[0]: r[1] for r in cur.fetchall() if r[1] != 0}

        all_codes = set(source_tb) | set(computed_tb)
        for code in all_codes:
            src = source_tb.get(code, Decimal("0"))
            got = computed_tb.get(code, Decimal("0"))
            if src != got:
                mismatches.append((tag, code, str(src), str(got)))

    assert not mismatches, f"trial balance mismatches (month, account_code, source, computed): {mismatches[:20]}"
