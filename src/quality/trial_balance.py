"""The trial balance zero-tolerance check.

Implements corpus/09 sections 2.4 and 3.1: "Sum of amount_base across all
current rows for a complete period equals exactly zero... Tolerance is zero,
per D-051. A period that fails does not proceed to statement assembly, and
the failure names the accounts contributing the largest imbalance."

This is the one quality check wired in sprint 1 (the rest of the catalogue in
corpus/09 is sprint 3 scope) -- it is what the sprint 1 acceptance criterion
depends on: a trial balance generated from fact_gl_entry must match the
source trial balance exactly, to the rupee, for all 36 months.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from src.quality.books_to_bank import ReconciliationResult
from src.quality.checks import ExceptionCandidate

# D-051, and settled rather than open -- corpus/09 section 3.1: "Tolerance is
# zero. There is no defensible non-zero tolerance for a trial balance, and
# D-051 records this as settled." This is NOT D-052's deliberately blank
# books-to-bank tolerance: it is a stated value, so it is written onto the
# reconciliation_run row rather than left null.
TRIAL_BALANCE_TOLERANCE_PCT = Decimal("0")


@dataclass
class AccountContribution:
    account_code: str
    account_name: str
    net_amount: Decimal


@dataclass
class TrialBalanceCheckResult:
    period_key: str
    total: Decimal
    balanced: bool
    blocking: bool
    largest_contributors: list[AccountContribution] = field(default_factory=list)


def evaluate_balances(period_key: str, account_balances: dict[tuple[str, str], Decimal]) -> TrialBalanceCheckResult:
    """Pure evaluation over {(account_code, account_name): net_amount_base}
    for one period -- unit-testable without a DB. account_balances is exactly
    what you'd get from `SELECT account_code, account_name, SUM(amount_base)
    ... GROUP BY account_code, account_name` for the period's current rows."""
    total = sum(account_balances.values(), Decimal("0"))
    balanced = total == 0
    contributors = []
    if not balanced:
        contributors = [
            AccountContribution(code, name, amt)
            for (code, name), amt in sorted(account_balances.items(), key=lambda kv: -abs(kv[1]))
            if amt != 0
        ][:5]
    return TrialBalanceCheckResult(
        period_key=period_key, total=total, balanced=balanced,
        blocking=not balanced,  # zero tolerance, D-051 -- any non-zero total blocks
        largest_contributors=contributors,
    )


def check_trial_balance(conn, schema: str, tenant_id: str, period_key: str) -> TrialBalanceCheckResult:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT da.source_account_code, da.source_account_name, SUM(fg.amount_base) '
            f'FROM "{schema}".fact_gl_entry fg JOIN "{schema}".dim_account da USING (account_key) '
            f'WHERE fg.tenant_id=%s AND fg.period_key=%s AND fg.is_current '
            f'GROUP BY da.source_account_code, da.source_account_name',
            (tenant_id, period_key),
        )
        balances = {(r[0], r[1]): r[2] for r in cur.fetchall()}
    return evaluate_balances(period_key, balances)


def _rupees(amount: Decimal) -> str:
    """Two decimals, always. The rest of the exception queue renders money as
    `Rs {v:,.0f}`, which at a zero tolerance would print a blocking Rs 0.01
    imbalance as "Rs 0" -- a number that looks right and is wrong."""
    return f"Rs {amount:,.2f}"


def imbalance_exception(result: TrialBalanceCheckResult) -> ExceptionCandidate:
    """corpus/09 section 2.4's catalogue row -- "Trial balance does not
    balance ... BLOCKING" -- as the thing the catalogue blocks THROUGH: an
    exception row (corpus/09 section 4). Class 'consistency', which is the
    section of the catalogue the row sits in.

    corpus/09 section 3.1 requires that "the failure names the accounts
    contributing the largest imbalance", so the contributors go in the
    description rather than a structured column: an exception carries one
    object_ref, and the object this one concerns is the period.

    **What `largest_contributors` actually ranks.** evaluate_balances sorts
    by absolute net balance. In a trial balance every account carries a
    balance, so that ranking surfaces the period's biggest accounts, which
    need not include the one-sided voucher that caused the imbalance. The
    description therefore reports what those figures are and does not assert
    a cause the check has not established.

    Pure: a computed result in, a candidate out. The write is
    src/quality/checks.write_exceptions, called from
    src/ingest/load_pipeline.load_gl_file."""
    if not result.blocking:
        raise ValueError(f"{result.period_key} balances -- there is no exception to raise. "
                         f"corpus/09 section 2.4's row fires on a non-zero total only.")
    contributors = "; ".join(
        f"{c.account_code} {c.account_name} {_rupees(c.net_amount)}" for c in result.largest_contributors
    )
    return ExceptionCandidate(
        exception_class="consistency",
        severity="blocking",
        description=(
            f"Trial balance for {result.period_key} does not balance: the period's current GL rows net to "
            f"{_rupees(result.total)}, not zero. Tolerance is zero (D-051), so statement assembly for this "
            f"period is blocked. Accounts carrying the largest balances in the period "
            f"(corpus/09 section 3.1): {contributors}."
        ),
        period_key=result.period_key,
        object_type="period",
        object_ref=result.period_key,
        value_inr=abs(result.total),
        suggested_action=(
            "Fix at source and reload (corpus/09 section 4): a non-zero total means the lines exported for "
            "this period do not form a complete set of balanced double entries."
        ),
    )


def as_reconciliation_result(result: TrialBalanceCheckResult) -> ReconciliationResult:
    """The trial balance tie as a reconciliation_run payload. corpus/09
    section 2.5 lists it as one of P0's two reconciliation checks, and
    corpus/04's table inventory grains reconciliation_run as "result of each
    reconciliation check per period" -- so the tie is recorded every period,
    whether or not it failed, exactly like books-to-bank.

    A trial balance has one source, not two. books_amount_inr is the period's
    net; bank_amount_inr is null (db/migrations/tenant/0011's own comment);
    and the residual IS that net, because the figure it is measured against
    is exactly zero. No modelled differences: corpus/09 section 3.2's seven
    categories belong to books-to-bank, and nothing about a trial balance
    imbalance is an expected difference to be modelled away."""
    return ReconciliationResult(
        period_key=result.period_key,
        books_total=result.total,
        bank_total=None,
        modelled_differences=[],
        residual=result.total,
    )
