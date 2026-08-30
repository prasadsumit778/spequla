"""Fixture IR for corpus/10's golden questions, keyed by exact question
text, for use with src.semantic.model_client.StubModelClient.

This is test data standing in for what real intent classification and IR
generation would produce -- it proves the deterministic pipeline (stages
2, 5-10 of corpus/07 section 2) against real data, not natural-language
understanding, which remains untested until a real ModelClient is wired up.

LAST_MONTH is 2025-03, which despite the name is NOT the last month of GL
data: synthetic/manufacturer/profile.py gives FISCAL_START 2023-04 and
N_MONTHS 36, so the synthetic manufacturer (seed=42) runs 2023-04 through
2026-03 and 2025-03 is month 24 of 36. Whether the golden set should instead
resolve "last month" to the dataset's actual boundary is OQ-017; the
fixtures are not moved here, because every expected value below is tied to
the month it names. Questions are grouped exactly
as corpus/10 groups them: the 37 gating questions (5 of them profile
'consumer', correctly left unresolvable until Sprint 6's
fact_channel_order_line exists -- see their own comments), then the 14
refusals.
"""
from __future__ import annotations

LAST_MONTH = "2025-03"
PRIOR_MONTH = "2025-02"

GATING_FIXTURES: dict[str, tuple[str, dict]] = {
    "What was our revenue last month?": (
        "metric_value",
        {"intent": "metric_value", "metric": "net_revenue", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "Show me the P&L for last quarter.": (
        # Simplification, disclosed: statement_view is implemented for a
        # single month in this sprint, not a literal fiscal-quarter roll-up
        # -- the intent and mechanism (statement assembly, not the metric
        # registry) are what this fixture exercises.
        "statement_view",
        {"intent": "statement_view", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "What is our EBITDA this year to date?": (
        # Simplification, disclosed: YTD aggregation is not implemented --
        # this exercises metric_value for the last closed month instead,
        # which correctly reports the same D-006/D-012 chain block a true
        # YTD sum would also hit.
        "metric_value",
        {"intent": "metric_value", "metric": "ebitda", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "Show revenue for the last twelve months.": (
        "metric_trend",
        {"intent": "metric_trend", "metric": "net_revenue",
          "period": {"type": "custom_range", "value": "last_12_months",
                       "resolved_range": ["2024-04-01", "2025-03-31"]}},
    ),
    "Why did EBITDA decline?": (
        "variance_explain",
        {"intent": "variance_explain", "metric": "ebitda", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "What is our revenue by customer this quarter?": (
        "metric_breakdown",
        {"intent": "metric_breakdown", "metric": "net_revenue", "breakdown": ["customer"],
          "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "Who are our top ten customers by revenue?": (
        "metric_ranking",
        {"intent": "metric_ranking", "metric": "net_revenue", "breakdown": ["customer"],
          "sort": {"by": "metric", "direction": "desc"}, "limit": 10,
          "period": {"type": "month", "value": LAST_MONTH}},
    ),
    # GQ-028, profile=consumer, required_facts includes fact_channel_order_line
    # (Sprint 6). No fixture -- StubModelClient's default (question not
    # found -> unsupported) is the honest outcome until that table exists;
    # asserting THAT specific behaviour is what tests/eval/test_golden_
    # questions.py does for all five consumer-profile gating questions.
    "What is our gross margin by product?": (
        "metric_breakdown",
        {"intent": "metric_breakdown", "metric": "gross_margin_pct", "breakdown": ["product"],
          "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "Which products have the highest margins?": (
        "metric_ranking",
        {"intent": "metric_ranking", "metric": "gross_margin_pct", "breakdown": ["product"],
          "sort": {"by": "metric", "direction": "desc"}, "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "What is our current DSO?": (
        "metric_value",
        {"intent": "metric_value", "metric": "dso", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "How has our cash conversion cycle changed?": (
        "metric_trend",
        {"intent": "metric_trend", "metric": "ccc",
          "period": {"type": "custom_range", "value": "last_12_months",
                       "resolved_range": ["2024-04-01", "2025-03-31"]}},
    ),
    "How much receivable is over ninety days?": (
        "ageing",
        {"intent": "ageing", "metric": "accounts_receivable", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "How much cash do we have?": (
        "metric_value",
        {"intent": "metric_value", "metric": "cash", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "What is our net debt?": (
        "metric_value",
        {"intent": "metric_value", "metric": "net_debt", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    "Where did the cash go last month?": (
        "variance_explain",
        {"intent": "variance_explain", "metric": "closing_cash", "period": {"type": "month", "value": LAST_MONTH}},
    ),
    # GQ-071, GQ-072, GQ-073, GQ-074: profile=consumer, required_facts
    # fact_channel_order_line (Sprint 6). No fixture, same as GQ-028.
    "Is June reconciled?": (
        "data_health",
        {"intent": "data_health", "period": {"type": "month", "value": "2024-06"}},
    ),
    "How much of our data is unmapped?": (
        "data_health",
        {"intent": "data_health"},
    ),
    "How do you calculate DSO for us?": (
        "definition_lookup",
        {"intent": "definition_lookup", "metric": "dso"},
    ),
}

REFUSAL_FIXTURES: dict[str, tuple[str, str]] = {
    "What will our revenue be next quarter?":
        ("unsupported", "Forecasting is not available in this release."),
    "What happens to cash if we grow twenty percent?":
        ("unsupported", "Scenario modelling is not available in this release."),
    "What does our supply agreement say about price escalation?":
        ("unsupported", "Document analysis is not available."),
    "What is our customer acquisition cost?":
        ("unsupported", "CAC requires customer identity across channels, which is not held."),
    "Which of our competitors is growing fastest?":
        ("unsupported", "The system only sees this company's data."),
    "Is our GST filing correct?":
        ("unsupported", "GST data is not connected in this release."),
    "What is the market size for our product category?":
        ("unsupported", "External market data is not available."),
    "Should we raise prices?":
        ("unsupported", "This is a management decision, not a query."),
    "What is our valuation?":
        ("unsupported", "Valuation is out of scope."),
    "Show me consolidated group revenue.":
        ("unsupported", "Multi-entity consolidation is not available in this release."),
    "What is our EBITDA for a month that has not closed?":
        ("unsupported", "The period is not reportable: unreconciled and unmapped value above threshold."),
    "Which employee costs the most?":
        ("unsupported", "Employee-level data is excluded from analysis by design."),
    "What is our contribution margin?":
        ("unsupported", "The variable cost declaration has not been made for this company."),
    "How much did we lose to fraud last year?":
        ("unsupported", "No fraud classification exists in the data."),
}

ALL_FIXTURES: dict[str, tuple[str, dict | str]] = {**GATING_FIXTURES, **REFUSAL_FIXTURES}

# The 5 consumer-profile gating questions, deliberately unfixtured -- kept
# as a named list so the eval test can assert on them explicitly rather
# than by omission.
CONSUMER_PROFILE_DEFERRED_QUESTIONS = [
    "What is revenue by channel this month?",
    "Which channel makes money after everything?",
    "Do our unit economics work before marketing?",
    "What is our GMV this month and how much of it is our revenue?",
    "Why did returns rise last month?",
]
