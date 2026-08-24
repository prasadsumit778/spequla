"""row_hash: content hash of a staged row's business columns.

Implements corpus/04 section 1.2 ("row_hash bytea. Content hash of the
business columns. Drives deduplication and change detection") and corpus/09
section 2.3 (duplicate voucher number and line within a period -> BLOCKING,
deduplicated on row_hash) and section 3 guarantee #2 (idempotent: the same
file loaded twice produces no duplicate facts, because row_hash catches it).

The hash is computed from the STAGED row's business fields only -- never
tenant_id, load_run_id, valid_from/valid_to/is_current, or row_hash itself,
since those are lineage/knowledge-time metadata, not business content. Two
staged rows with identical business content hash identically regardless of
which load_run produced them, which is exactly what makes re-uploading a
file idempotent.
"""
from __future__ import annotations

import hashlib

# The business columns of a staged GL row, in a fixed order, per corpus/01's
# GL template plus corpus/04's fact_gl_entry business columns. Deliberately
# excludes lineage columns (load_run_id, source_record_id, valid_from/to).
GL_ROW_HASH_FIELDS = [
    "voucher_no", "voucher_type", "voucher_date", "entry_date", "line_no",
    "account_code", "debit", "credit", "narration", "cost_centre",
    "party_name", "is_cancelled",
]

# corpus/01's Bank template columns, business content only.
BANK_ROW_HASH_FIELDS = [
    "bank_account_ref", "txn_date", "value_date", "description", "reference",
    "debit", "credit", "running_balance",
]

# Consumer Sales / channel order line, corpus/04 section 3.5's business columns.
CHANNEL_ORDER_ROW_HASH_FIELDS = [
    "order_id", "order_date", "channel", "channel_sub", "customer_code", "item_code",
    "quantity", "gross_amount", "discount_amount", "net_amount", "shipping_charged",
    "commission_amount", "shipping_cost", "payment_fee", "return_flag", "return_date",
    "return_reason", "revenue_model", "order_type", "commission_earned",
    "advertising_earned", "platform_fee_earned",
]

# MFG Production, corpus/04 section 3.6's business columns.
PRODUCTION_OUTPUT_ROW_HASH_FIELDS = [
    "period", "plant_or_line", "item_code", "qty_produced", "qty_rejected", "uom",
    "input_qty", "input_uom", "available_hours", "running_hours", "power_units",
]

# Store Master, corpus/04 section 3.10 / corpus/01's Store Master template.
STORE_MASTER_ROW_HASH_FIELDS = [
    "store_code", "store_name", "store_format", "city", "state", "site_type",
    "area_sqft", "opening_date", "closure_date", "status",
]


def compute_row_hash(row: dict, fields: list[str] = GL_ROW_HASH_FIELDS) -> bytes:
    """Deterministic content hash over `fields`, missing fields treated as
    empty string so a field that is merely absent doesn't change the hash
    unpredictably across slightly-different-shaped exports."""
    parts = [str(row.get(f, "") or "") for f in fields]
    return hashlib.sha256("\x1f".join(parts).encode()).digest()
