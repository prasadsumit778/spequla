"""Tests for the mapping engine's pure logic, corpus/06 section 4."""
from decimal import Decimal

from src.mapping.engine import AccountToMap, evaluate_auto_accept, propose_mappings

JUDGEMENT_CLASSES = {
    "exceptional.one_off", "opex.owner_remuneration", "opex.related_party_charges",
    "cogs.absorption_variance", "liability.bill_discounting", "liability.debt_related_party",
}


def _account(name, value="1000000") -> AccountToMap:
    return AccountToMap(account_key=1, source_record_id="4001", source_account_name=name,
                          source_parent_group="Sales Accounts", period_value_inr=Decimal(value))


def test_propose_mappings_splits_matched_and_unmatched():
    accounts = [_account("Sales - Direct (North)"), _account("Misc 17")]
    proposed, unmatched = propose_mappings(accounts)
    assert len(proposed) == 1
    assert proposed[0].canonical_class == "revenue.product_sales"
    assert len(unmatched) == 1
    assert unmatched[0].source_account_name == "Misc 17"


def test_auto_accept_fires_for_a_clean_exact_rule_match():
    proposed, _ = propose_mappings([_account("Sales - Direct (North)")])
    accepted, reason = evaluate_auto_accept(proposed[0], JUDGEMENT_CLASSES, None, None)
    assert accepted is True


def test_auto_accept_never_fires_on_a_judgement_class():
    for name, expected_class in [
        ("Director Remuneration", "opex.owner_remuneration"),
        ("Rent Paid - Related Party", "opex.related_party_charges"),
        ("Absorption Variance", "cogs.absorption_variance"),
        ("Unsecured Loan - Director", "liability.debt_related_party"),
    ]:
        proposed, _ = propose_mappings([_account(name)])
        assert proposed[0].canonical_class == expected_class
        accepted, reason = evaluate_auto_accept(proposed[0], JUDGEMENT_CLASSES, None, None)
        assert accepted is False, f"{name} must never auto-accept"
        assert "judgement class" in reason


def test_auto_accept_refuses_a_conflicting_prior_mapping():
    proposed, _ = propose_mappings([_account("Sales - Direct (North)")])
    accepted, reason = evaluate_auto_accept(proposed[0], JUDGEMENT_CLASSES, "revenue.export_sales", None)
    assert accepted is False
    assert "conflicts" in reason


def test_auto_accept_respects_a_ceiling_when_one_is_declared():
    proposed, _ = propose_mappings([_account("Sales - Direct (North)", value="5000000")])
    accepted, _ = evaluate_auto_accept(proposed[0], JUDGEMENT_CLASSES, None, Decimal("1000000"))
    assert accepted is False  # value is above the (hypothetical, test-only) ceiling

    proposed, _ = propose_mappings([_account("Sales - Direct (North)", value="500")])
    accepted, _ = evaluate_auto_accept(proposed[0], JUDGEMENT_CLASSES, None, Decimal("1000000"))
    assert accepted is True


def test_auto_accept_never_fires_without_a_rule_match():
    unmatched_account = _account("Misc 17")
    fake_proposal_source = "human"  # simulating a non-rule proposal source
    from src.mapping.engine import Proposal
    fake = Proposal(account=unmatched_account, canonical_class="opex.other", derived_channel=None,
                      derived_geo=None, proposal_source=fake_proposal_source, proposal_reason="manual",
                      rule=None)
    accepted, reason = evaluate_auto_accept(fake, JUDGEMENT_CLASSES, None, None)
    assert accepted is False
    assert "not an exact-rule match" in reason
