"""Tests for the trial balance zero-tolerance check, corpus/09 2.4/3.1, D-051."""
from decimal import Decimal

from src.quality.trial_balance import evaluate_balances


def test_balanced_period_passes():
    result = evaluate_balances("2026-04", {
        ("4001", "Sales"): Decimal("-100000"),
        ("1200", "Sundry Debtors"): Decimal("100000"),
    })
    assert result.balanced is True
    assert result.blocking is False
    assert result.total == 0


def test_imbalanced_period_blocks_and_names_contributors():
    result = evaluate_balances("2026-04", {
        ("4001", "Sales"): Decimal("-100000"),
        ("1200", "Sundry Debtors"): Decimal("99999"),  # off by 1 rupee
    })
    assert result.balanced is False
    assert result.blocking is True
    assert result.total == Decimal("-1")
    assert len(result.largest_contributors) == 2


def test_zero_tolerance_even_one_paisa_off():
    result = evaluate_balances("2026-04", {
        ("4001", "Sales"): Decimal("-100000.00"),
        ("1200", "Sundry Debtors"): Decimal("100000.01"),
    })
    assert result.balanced is False


def test_synthetic_manufacturer_defect_4_month_blocks(seed=42):
    from synthetic.manufacturer.engine import build_company
    from synthetic.common import period_key as pkey
    data = build_company(seed=seed)
    entry = next(e for e in data.defect_log.entries if e["defect_id"] == 4)
    defect_month_str = entry["month"]
    month_idx = next(i for i, d in enumerate(data.months) if pkey(d) == defect_month_str)

    balances: dict = {}
    for row in data.gl_rows[month_idx]:
        key = (row["account_code"], row["account_name"])
        amt = Decimal(row["debit"] or "0") - Decimal(row["credit"] or "0")
        balances[key] = balances.get(key, Decimal("0")) + amt

    result = evaluate_balances(defect_month_str, balances)
    assert result.balanced is False
    assert result.blocking is True


def test_synthetic_manufacturer_normal_month_passes(seed=42):
    from synthetic.manufacturer.engine import build_company
    data = build_company(seed=seed)
    defect_months = {e["month"] for e in data.defect_log.entries if e["defect_id"] == 4}

    for month_idx, d in enumerate(data.months):
        from synthetic.common import period_key as pkey
        pk = pkey(d)
        if pk in defect_months:
            continue
        balances: dict = {}
        for row in data.gl_rows[month_idx]:
            key = (row["account_code"], row["account_name"])
            amt = Decimal(row["debit"] or "0") - Decimal(row["credit"] or "0")
            balances[key] = balances.get(key, Decimal("0")) + amt
        result = evaluate_balances(pk, balances)
        assert result.balanced is True, f"{pk} should balance"
