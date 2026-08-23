"""Integration test: the deterministic compiler against a fully ingested and
mapped synthetic manufacturer. Needs live Postgres (see tests/conftest.py) --
skips cleanly otherwise.

Covers corpus/12 sprint 3's compiler test line ("a metric with an unresolved
decision does not serve a default") and the sprint's acceptance criterion
("every metric on the overview screen carries a citation that resolves to
source rows") for the two of the nine headline tiles that actually compile
for this company today (cash, net_debt -- see src/semantic/compiler.py's
docstring and tests/unit/test_semantic_compiler.py for why the other seven
are correctly gated, not a bug).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.config.loader import load_registry
from src.semantic.citation import NotCitable, build_citation
from src.semantic.compiler import compile_metric
from tests.helpers import ingest_manufacturer, run_and_freeze_mapping


def test_cash_and_net_debt_compile_with_full_citations(conn, tenant):
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    version_id, summary, freeze = run_and_freeze_mapping(conn, schema, tenant_id, entity_id,
                                                             effective_from=date(2022, 4, 1))
    assert freeze.passed, freeze.reason

    config = load_registry()
    last_period = "2025-03"  # 36 months from 2022-04

    cash = compile_metric(conn, schema, tenant_id, entity_id, "cash", last_period, config)
    assert cash.status == "ok", cash.reason
    assert cash.value is not None
    assert cash.row_count > 0

    net_debt = compile_metric(conn, schema, tenant_id, entity_id, "net_debt", last_period, config)
    assert net_debt.status == "ok", net_debt.reason

    citation = build_citation(conn, schema, tenant_id, entity_id, version_id, cash, "reconciled")
    assert citation.value == cash.value
    assert citation.metric == "cash"
    assert citation.row_count == cash.row_count
    assert "fact_gl_entry" in citation.source_facts
    assert len(citation.source_files) > 0  # GL exports actually contributed rows
    assert citation.mapping_version == 1
    assert citation.query_hash and len(citation.query_hash) == 6
    assert citation.drill_url == f"/query/{citation.query_hash}/rows"


def test_gated_metrics_do_not_serve_a_default(conn, tenant):
    """corpus/12 sprint 3: 'a metric with an unresolved decision does not
    serve a default.' Every one of these has dependencies that route back to
    an open per-company decision -- none should ever produce a numeric
    value against this synthetic company, and each must name the actual
    blocking decision, not a generic failure."""
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    run_and_freeze_mapping(conn, schema, tenant_id, entity_id, effective_from=date(2022, 4, 1))

    config = load_registry()
    period = "2025-03"

    expectations = {
        "net_revenue": {"D-006"},
        "gross_margin_pct": {"D-006", "D-012", "D-015", "D-016", "D-017", "D-018", "D-001", "D-002"},
        "ebitda": {"D-006", "D-012", "D-015", "D-016", "D-017", "D-018", "D-001", "D-002"},
        "working_capital": {"D-018"},
        "dso": {"D-006", "D-001", "D-002"},
        "dio": {"D-018", "D-012", "D-015", "D-016", "D-017"},
        "dpo": {"D-012", "D-015", "D-016", "D-017", "D-018"},
    }
    for metric_id, expected_decisions in expectations.items():
        result = compile_metric(conn, schema, tenant_id, entity_id, metric_id, period, config)
        assert result.status == "blocked", f"{metric_id} unexpectedly resolved: {result.value}"
        assert result.value is None
        assert set(result.blocking_decisions) == expected_decisions, \
            f"{metric_id}: expected {expected_decisions}, got {set(result.blocking_decisions)}"

        try:
            build_citation(conn, schema, tenant_id, entity_id, 1, result, "reconciled")
            assert False, f"{metric_id}: a blocked metric must never be citable"
        except NotCitable:
            pass


def test_no_approved_mapping_blocks_every_metric_before_the_decision_gate_matters(conn, tenant):
    """corpus/06 section 6 rule 1: 'Metrics do not unlock until version 1 is
    approved.' Even cash (no unresolved decision at all) must not resolve
    to a number before a mapping is frozen."""
    tenant_id, schema = tenant
    entity_id = 1
    ingest_manufacturer(conn, schema, tenant_id, entity_id)
    # deliberately: no run_and_freeze_mapping call

    config = load_registry()
    result = compile_metric(conn, schema, tenant_id, entity_id, "cash", "2025-03", config)
    assert result.status == "blocked"
    assert result.value is None
    assert "approved" in result.reason.lower()
