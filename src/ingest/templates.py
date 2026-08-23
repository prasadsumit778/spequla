"""The column list of every template in corpus/01, transcribed verbatim.

corpus/01_SPEQULA_DATA_REQUEST_PACK.xlsx is what a customer is asked to fill
in. Each of its data sheets carries a one-line description in row 1, a
"delete the example" note in row 2, the header in row 3 and a synthetic
example in row 4. The header rows are reproduced here so the ingest path can
recognise a template without reading the workbook at runtime.

These names are NOT invented and must never be edited by hand to make a file
load. They are the customer-facing contract, and CLAUDE.md section 3.3
forbids supplying a source-system field name from anywhere but the corpus.
`tests/unit/test_templates.py` reads the real workbook and fails if this
module and corpus/01 ever disagree, so the corpus stays the authority.

Keys are the `template_type` values already written to `app.source_file`
by src/ingest/load_pipeline.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    template_type: str      # as stored in app.source_file.template_type
    sheet_name: str         # the sheet's name in corpus/01
    columns: tuple[str, ...]


COA = Template("COA", "COA", (
    "account_code", "account_name", "parent_group", "account_type",
    "opening_balance", "opening_dr_cr", "cost_centre", "is_active",
))

TB = Template("TB", "TB", (
    "period_end", "account_code", "account_name", "opening_balance",
    "debit_movement", "credit_movement", "closing_balance",
))

GL = Template("GL", "GL", (
    "voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
    "account_code", "account_name", "debit", "credit", "narration",
    "cost_centre", "party_name", "is_cancelled",
))

BANK = Template("Bank", "Bank", (
    "bank_account_ref", "txn_date", "value_date", "description", "reference",
    "debit", "credit", "running_balance",
))

CONSUMER_SALES = Template("ConsumerSales", "Consumer Sales", (
    "order_id", "order_date", "channel", "channel_sub", "customer_code",
    "item_code", "item_name", "quantity", "gross_amount", "discount_amount",
    "net_amount", "shipping_charged", "commission_amount", "shipping_cost",
    "payment_fee", "return_flag", "return_date", "return_reason", "settlement_date",
))

MFG_PRODUCTION = Template("MFGProduction", "MFG Production", (
    "period", "plant_or_line", "item_code", "item_name", "qty_produced",
    "qty_rejected", "uom", "input_qty", "input_uom", "available_hours",
    "running_hours", "power_units",
))

ALL_TEMPLATES: tuple[Template, ...] = (
    COA, TB, GL, BANK, CONSUMER_SALES, MFG_PRODUCTION,
)

BY_TYPE: dict[str, Template] = {t.template_type: t for t in ALL_TEMPLATES}
