"""Writers: serialise a built CompanyData to files matching corpus/01's
Field Specifications tab exactly, column for column, one file per template
per month (per corpus/01's own "Frequency: Monthly" checklist entries).

Defect #6 (schema hash change between two months) is applied here, not in
the engine: the GL export for one specific month is written with a renamed
column so its header -- and therefore its schema hash -- differs from every
other month's file.
"""
from __future__ import annotations

from pathlib import Path

from synthetic.common import write_csv
from synthetic.manufacturer.engine import CompanyData

COA_FIELDS = ["account_code", "account_name", "parent_group", "account_type",
              "opening_balance", "opening_dr_cr", "cost_centre", "is_active"]
TB_FIELDS = ["period_end", "account_code", "account_name", "opening_balance",
             "debit_movement", "credit_movement", "closing_balance"]
GL_FIELDS = ["voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
             "account_code", "account_name", "debit", "credit", "narration",
             "cost_centre", "party_name", "is_cancelled"]
GL_FIELDS_DEFECT6 = ["voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
                      "account_code", "account_name", "debit", "credit", "remarks",
                      "cost_centre", "party_name", "is_cancelled"]  # 'narration' renamed 'remarks'
BANK_FIELDS = ["bank_account_ref", "txn_date", "value_date", "description", "reference",
               "debit", "credit", "running_balance"]
SALES_FIELDS = ["invoice_no", "invoice_date", "customer_code", "customer_name", "item_code",
                 "item_name", "quantity", "uom", "rate", "gross_amount", "discount_amount",
                 "taxable_value", "tax_amount", "invoice_total", "channel", "dispatch_date",
                 "is_credit_note"]
PURCHASE_FIELDS = ["bill_no", "bill_date", "vendor_code", "vendor_name", "item_code", "item_name",
                     "expense_account", "quantity", "uom", "rate", "taxable_value", "tax_amount",
                     "bill_total", "is_msme_vendor"]
AR_AGEING_FIELDS = ["as_at_date", "customer_code", "customer_name", "invoice_no", "invoice_date",
                      "due_date", "outstanding_amount", "credit_days"]
AP_AGEING_FIELDS = ["as_at_date", "vendor_code", "vendor_name", "bill_no", "bill_date",
                      "due_date", "outstanding_amount"]
INVENTORY_FIELDS = ["as_at_date", "item_code", "item_name", "item_category", "stock_type",
                      "location", "closing_qty", "uom", "closing_value", "valuation_method"]
MFG_FIELDS = ["period", "plant_or_line", "item_code", "item_name", "qty_produced", "qty_rejected",
               "uom", "input_qty", "input_uom", "available_hours", "running_hours", "power_units"]


def write_all(data: CompanyData, out_dir: Path, schema_hash_defect_month: int):
    out_dir.mkdir(parents=True, exist_ok=True)

    coa_rows = [{
        "account_code": l.account_code, "account_name": l.account_name,
        "parent_group": l.parent_group, "account_type": l.account_type,
        "opening_balance": "0", "opening_dr_cr": "Dr", "cost_centre": l.cost_centre or "",
        "is_active": l.is_active,
    } for l in data.coa]
    write_csv(out_dir / "COA.csv", COA_FIELDS, coa_rows)

    for i, d in enumerate(data.months):
        tag = f"{d.year:04d}-{d.month:02d}"

        fields = GL_FIELDS_DEFECT6 if i == schema_hash_defect_month else GL_FIELDS
        gl_out_rows = data.gl_rows[i]
        if i == schema_hash_defect_month:
            gl_out_rows = [{**{k: v for k, v in r.items() if k != "narration"}, "remarks": r["narration"]}
                            for r in gl_out_rows]
        write_csv(out_dir / f"GL_{tag}.csv", fields, gl_out_rows)

        write_csv(out_dir / f"TB_{tag}.csv", TB_FIELDS, data.tb_rows[i])
        # Defect #3 (corpus/11 section 2.2): "One month where the bank file
        # is missing entirely" -- the file itself is omitted, not uploaded
        # empty, so corpus/09 section 2.1's "a required stream has not been
        # supplied at all" check has something real to detect.
        if data.bank_rows[i]:
            write_csv(out_dir / f"Bank_{tag}.csv", BANK_FIELDS, data.bank_rows[i])
        write_csv(out_dir / f"SalesRegister_{tag}.csv", SALES_FIELDS, data.sales_rows[i])
        write_csv(out_dir / f"PurchaseRegister_{tag}.csv", PURCHASE_FIELDS, data.purchase_rows[i])
        write_csv(out_dir / f"ARAgeing_{tag}.csv", AR_AGEING_FIELDS, data.ar_ageing_rows[i])
        write_csv(out_dir / f"APAgeing_{tag}.csv", AP_AGEING_FIELDS, data.ap_ageing_rows[i])
        write_csv(out_dir / f"Inventory_{tag}.csv", INVENTORY_FIELDS, data.inventory_rows[i])
        write_csv(out_dir / f"MFGProduction_{tag}.csv", MFG_FIELDS, data.mfg_rows[i])

    defect_log_path = out_dir / "SYNTHETIC_DEFECT_LOG.md"
    defect_log_path.write_text(_render_defect_log(data))


def _render_defect_log(data: CompanyData) -> str:
    from synthetic.defects import DEFECTS
    lines = ["# Synthetic manufacturer -- seeded defect log",
             "",
             "Generated by synthetic/manufacturer/write.py. Documents exactly where each of the",
             "thirteen defects from corpus/11 section 2.2 landed in this run, for tests to locate.",
             ""]
    by_id = {}
    for e in data.defect_log.entries:
        by_id.setdefault(e["defect_id"], []).append(e)
    for defect in DEFECTS:
        lines.append(f"## Defect {defect.id}: {defect.description}")
        lines.append(f"Targets: {defect.check}")
        lines.append(f"Lands in: {defect.lands_in}")
        for e in by_id.get(defect.id, []):
            detail = {k: v for k, v in e.items() if k not in ("defect_id",)}
            lines.append(f"- {detail}")
        lines.append("")
    return "\n".join(lines)
