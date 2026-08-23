"""Unit tests for the refusing config loader.

Implements: corpus/12 sprint 0 item 1 acceptance ("53 of 61 metrics should
compile; 8 should not"), and the loader's refusal contract.
"""
import pytest

from src.config.loader import MetricNotConfigured, load_registry

EXPECTED_BLOCKED = {
    "gross_revenue": {"D-001", "D-002"},
    "net_revenue": {"D-006"},
    "cogs": {"D-012", "D-015", "D-016", "D-017", "D-018"},
    "inventory": {"D-018"},
    "volume_sold": {"D-041"},
    "volume_produced": {"D-041"},
    "realisation_per_unit": {"D-041"},
    "capacity_utilisation_pct": {"D-042"},
}


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def test_total_metric_count(registry):
    assert len(registry.metrics) == 61


def test_53_compile_8_blocked(registry):
    assert len(registry.blocked_metrics) == 8
    assert set(registry.blocked_metrics) == set(EXPECTED_BLOCKED)


def test_blocking_decisions_match_corpus(registry):
    for metric_id, expected in EXPECTED_BLOCKED.items():
        assert set(registry.blocked_metrics[metric_id]) == expected


def test_blocked_metric_raises_not_configured_never_a_default(registry):
    with pytest.raises(MetricNotConfigured) as exc_info:
        registry.resolve_metric("net_revenue")
    assert "D-006" in exc_info.value.blocking
    assert "not yet configured" in str(exc_info.value)


def test_unblocked_metric_resolves(registry):
    contract = registry.resolve_metric("gross_margin_pct")
    assert contract.registry.metric_id == "gross_margin_pct"


def test_unknown_metric_raises_keyerror(registry):
    with pytest.raises(KeyError):
        registry.resolve_metric("does_not_exist")


def test_all_open_decisions_are_the_twelve_per_company_ones(registry):
    open_decisions = {d.id for d in registry.decisions.values()
                       if d.status == "open" and d.type == "decision"}
    assert open_decisions == {
        "D-001", "D-002", "D-006", "D-012", "D-015", "D-016",
        "D-017", "D-018", "D-041", "D-042", "D-050", "D-052",
    }
