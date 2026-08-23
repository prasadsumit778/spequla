"""Books-to-bank reconciliation, corpus/09 section 3.2.

"Three sources, one honest answer." Books (accrual, net of credit notes) vs
bank receipts (cash in, including advances), with the gap between them
itemised into named modelled differences rather than swept into one number.

D-052 (books-to-bank residual tolerance) is deliberately unset -- corpus/00:
"a threshold that can only honestly be set from observation... none blocks
the build." Two consequences follow, both load-bearing:

  1. The list of modelled differences per company is itself an accounting-
     policy-interview output (corpus/09 section 9: "comes from the
     accounting policy conversation, one company at a time"), not something
     derivable from data alone. Nothing has been configured for the
     synthetic company yet, so `modelled_differences` is legitimately empty
     here -- the entire books-vs-bank gap surfaces as residual, which is
     the honest state, not a shortfall in this module.
  2. Without a tolerance, "residual within/above tolerance" cannot be
     evaluated as true or false -- this module therefore never classifies a
     residual as reconciled or breached. It computes and itemises; the
     period state machine (src/quality/period_state.py) is where a human
     reviews the visible residual and marks the period reconciled, per that
     module's own docstring on why the MAPPED -> RECONCILED transition is a
     human action here rather than an automatic tolerance gate.

Split into DB-fetching wrappers (fetch_*, run_books_to_bank) and a pure
function (compute_reconciliation) over already-fetched totals, continuing
the pattern from src/quality/trial_balance.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

from src.reports.query import class_movements
from src.semantic.compiler import period_bounds
from src.semantic.formula import natural_positive

# corpus/09 section 3.2's seven named categories, verbatim -- the only valid
# values for ModelledDifference.category. An unlisted category is a
# programming error, not a new kind of difference this module invents.
MODELLED_DIFFERENCE_CATEGORIES = (
    "credit_period",
    "advances_received",
    "tds_deducted",
    "gateway_marketplace_lag",
    "unpresented_instruments",
    "inter_account_transfer",
    "unbooked_bank_charges",
)


@dataclass
class ModelledDifference:
    category: str
    amount_inr: Decimal
    note: str

    def __post_init__(self):
        if self.category not in MODELLED_DIFFERENCE_CATEGORIES:
            raise ValueError(f"{self.category!r} is not one of corpus/09 section 3.2's named categories")


@dataclass
class ReconciliationResult:
    period_key: str
    books_total: Decimal
    bank_total: Decimal
    modelled_differences: list[ModelledDifference] = field(default_factory=list)
    residual: Decimal = Decimal("0")

    @property
    def modelled_total(self) -> Decimal:
        return sum((d.amount_inr for d in self.modelled_differences), Decimal("0"))


def compute_reconciliation(period_key: str, books_total: Decimal, bank_total: Decimal,
                             modelled_differences: list[ModelledDifference] | None = None) -> ReconciliationResult:
    """Pure. residual = books - bank - modelled, always computed and always
    reported regardless of whether any modelled difference is configured --
    'it never picks one and moves on.'"""
    differences = modelled_differences or []
    modelled_total = sum((d.amount_inr for d in differences), Decimal("0"))
    residual = books_total - bank_total - modelled_total
    return ReconciliationResult(period_key=period_key, books_total=books_total, bank_total=bank_total,
                                   modelled_differences=differences, residual=residual)


def fetch_books_total(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                         period_start, period_end) -> Decimal:
    """'Books (accrual, net of credit notes)': revenue recognised in the GL
    this period (every revenue.* class), net of sales returns specifically
    -- corpus/09 section 3.2 names credit notes by name, not discounts or
    rate differences, and D-047 books a return in the period it occurs, so
    'net of credit notes' is exactly contra_revenue.sales_returns for this
    period, not the full contra-revenue group."""
    movements = class_movements(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    total = Decimal("0")
    for cls, raw in movements.items():
        if cls.startswith("revenue."):
            total += natural_positive(cls, raw)
    returns_raw = movements.get("contra_revenue.sales_returns", Decimal("0"))
    total -= natural_positive("contra_revenue.sales_returns", returns_raw)
    return total


def fetch_bank_total(conn, schema: str, tenant_id: str, entity_id: int, period_start, period_end) -> Decimal:
    """'Bank receipts (cash in, including advances)': every fact_bank_txn
    line with amount_base > 0 for the period. fact_bank_txn's own sign
    convention (src/ingest/staging.py's stage_bank docstring: credit minus
    debit, money in positive) already is 'cash in positive' -- no
    reclassification needed, unlike the GL side."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(amount_base), 0) FROM "{schema}".fact_bank_txn '
            f'WHERE tenant_id = %s AND entity_id = %s AND is_current '
            f'AND event_date BETWEEN %s AND %s AND amount_base > 0',
            (tenant_id, entity_id, period_start, period_end),
        )
        return cur.fetchone()[0]


def run_books_to_bank(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                         period_key: str,
                         modelled_differences: list[ModelledDifference] | None = None) -> ReconciliationResult:
    period_start, period_end = period_bounds(period_key)
    books_total = fetch_books_total(conn, schema, tenant_id, entity_id, mapping_version_id, period_start, period_end)
    bank_total = fetch_bank_total(conn, schema, tenant_id, entity_id, period_start, period_end)
    return compute_reconciliation(period_key, books_total, bank_total, modelled_differences)


def write_reconciliation_run(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                                check_type: str, result: ReconciliationResult, run_by: str,
                                tolerance_pct: Decimal | None = None) -> int:
    """check_type: 'books_to_bank' here, or 'trial_balance' for
    src/quality/trial_balance.py's result (same table, corpus/04's own
    table inventory: 'Result of each reconciliation check per period').
    status is deliberately never 'reconciled' when tolerance_pct is None --
    see this module's docstring point 2. It is 'unreconciled' until a human
    reviews the visible residual and the period state machine records a
    reconciled period_lock row, or 'reconciled' only when a real
    company-specific tolerance_pct is supplied and the residual is within
    it."""
    if tolerance_pct is not None and abs(result.residual) <= tolerance_pct * result.books_total:
        status = "reconciled"
    else:
        status = "unreconciled"
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".reconciliation_run '
            f'(tenant_id, entity_id, period_key, check_type, status, books_amount_inr, bank_amount_inr, '
            f' modelled_differences, residual_inr, tolerance_pct, run_by, mapping_version_id) '
            f'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING reconciliation_run_id',
            (tenant_id, entity_id, result.period_key, check_type, status, result.books_total, result.bank_total,
             json.dumps([{"category": d.category, "amount_inr": str(d.amount_inr), "note": d.note}
                          for d in result.modelled_differences]),
             result.residual, str(tolerance_pct) if tolerance_pct is not None else None, run_by,
             mapping_version_id),
        )
        return cur.fetchone()[0]
