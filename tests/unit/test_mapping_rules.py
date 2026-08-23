"""Tests for the rule library, corpus/06 section 4 step 2 and section 2."""
from src.mapping.rules import extract_channel_geo, match_exact_rule


def test_exact_match_case_insensitive():
    r1 = match_exact_rule("Sales - Direct (North)")
    r2 = match_exact_rule("SALES - DIRECT (NORTH)")
    assert r1 is not None
    assert r1.canonical_class == r2.canonical_class == "revenue.product_sales"


def test_odd_casing_and_spacing_variants_from_the_synthetic_generator():
    assert match_exact_rule("SALES - DIRECT (SOUTH)").canonical_class == "revenue.product_sales"
    assert match_exact_rule("Sales-Direct(East)").canonical_class == "revenue.product_sales"
    assert match_exact_rule("sales - distributor (west)").canonical_class == "revenue.product_sales"


def test_judgement_classes_are_reachable_by_rule():
    assert match_exact_rule("Director Remuneration").canonical_class == "opex.owner_remuneration"
    assert match_exact_rule("Rent Paid - Related Party").canonical_class == "opex.related_party_charges"
    assert match_exact_rule("Absorption Variance").canonical_class == "cogs.absorption_variance"
    assert match_exact_rule("Unsecured Loan - Director").canonical_class == "liability.debt_related_party"


def test_unknown_ledger_name_has_no_rule():
    assert match_exact_rule("Misc 17") is None
    assert match_exact_rule("Suspense A/c") is None
    assert match_exact_rule("Some Ledger Nobody Wrote A Rule For") is None


def test_consumer_ledgers_covered():
    assert match_exact_rule("Sales - Marketplace Amazon").canonical_class == "revenue.product_sales"
    assert match_exact_rule("Marketplace Commission Borne").canonical_class == "contra_revenue.commission_marketplace"
    assert match_exact_rule("Fulfilment Cost").canonical_class == "cogs.fulfilment"


def test_extract_channel_geo_worked_example():
    # The exact example from corpus/06 section 2.
    channel, geo = extract_channel_geo("Sales - Retail (Delhi)")
    assert channel == "retail"
    assert geo == "Delhi"


def test_extract_channel_geo_no_space_variant():
    channel, geo = extract_channel_geo("Sales-Direct(East)")
    assert channel == "direct"
    assert geo == "East"


def test_extract_channel_geo_absent_for_non_revenue_ledger():
    channel, geo = extract_channel_geo("Sundry Creditors")
    assert channel is None
    assert geo is None
