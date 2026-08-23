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
