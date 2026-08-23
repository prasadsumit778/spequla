"""Writers for the synthetic consumer dataset, matching corpus/01's Field
Specifications tab column-for-column, one file per template per month."""
from __future__ import annotations

from pathlib import Path

from synthetic.common import write_csv
from synthetic.consumer.engine import ConsumerCompanyData

COA_FIELDS = ["account_code", "account_name", "parent_group", "account_type",
              "opening_balance", "opening_dr_cr", "cost_centre", "is_active"]
TB_FIELDS = ["period_end", "account_code", "account_name", "opening_balance",
             "debit_movement", "credit_movement", "closing_balance"]
GL_FIELDS = ["voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
             "account_code", "account_name", "debit", "credit", "narration",
             "cost_centre", "party_name", "is_cancelled"]
CONSUMER_SALES_FIELDS = ["order_id", "order_date", "channel", "channel_sub", "customer_code",
                            "item_code", "item_name", "quantity", "gross_amount", "discount_amount",
                            "net_amount", "shipping_charged", "commission_amount", "shipping_cost",
                            "payment_fee", "return_flag", "return_date", "return_reason", "settlement_date",
                            "revenue_model", "order_type", "commission_earned", "advertising_earned",
                            "platform_fee_earned"]


def write_all(data: ConsumerCompanyData, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    coa_rows = [{
        "account_code": l.account_code, "account_name": l.account_name,
        "parent_group": l.parent_group, "account_type": l.account_type,
        "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": "", "is_active": "Yes",
    } for l in data.coa]
    write_csv(out_dir / "COA.csv", COA_FIELDS, coa_rows)

    for i, d in enumerate(data.months):
        tag = f"{d.year:04d}-{d.month:02d}"
        write_csv(out_dir / f"GL_{tag}.csv", GL_FIELDS, data.gl_rows[i])
        write_csv(out_dir / f"TB_{tag}.csv", TB_FIELDS, data.tb_rows[i])
        write_csv(out_dir / f"ConsumerSales_{tag}.csv", CONSUMER_SALES_FIELDS, data.order_rows[i])

    (out_dir / "SYNTHETIC_DEFECT_LOG.md").write_text(_render_defect_log(data))


def _render_defect_log(data: ConsumerCompanyData) -> str:
    lines = ["# Synthetic consumer brand -- seeded defect log", "",
             "Per corpus/11 section 2.3: twelve months, multi-channel, both revenue models, "
             "marketplace commission, returns arriving in a later period than the sale, and an "
             "order file that does not tie exactly to the books (the residual is intentional and "
             "is reported, never resolved, per corpus/02 section 3).", ""]
    for e in data.defect_log.entries:
        lines.append(f"- Defect {e['defect_id']}: {e}")
    return "\n".join(lines)
