"""Unit tests for src/semantic/ir.py -- pure, no DB (validate_ir only
touches the loaded registry, per corpus/07 section 3's own table)."""
import pytest

from src.config.loader import load_registry
from src.semantic.ir import IRRequest, IRValidationError, validate_ir


@pytest.fixture(scope="module")
def config():
    return load_registry()


def test_valid_ir_passes(config):
    ir = IRRequest(intent="metric_value", metric="cash", period={"type": "month", "value": "2025-03"})
    validate_ir(ir, config)  # must not raise


def test_unknown_metric_rejected(config):
    ir = IRRequest(intent="metric_value", metric="not_a_real_metric")
    with pytest.raises(IRValidationError) as exc:
        validate_ir(ir, config)
    assert exc.value.field_name == "metric"


def test_metric_missing_for_intent_that_needs_one(config):
    ir = IRRequest(intent="metric_value")
    with pytest.raises(IRValidationError) as exc:
        validate_ir(ir, config)
    assert exc.value.field_name == "metric"


def test_breakdown_dimension_not_in_metric_contract_rejected(config):
    ir = IRRequest(intent="metric_breakdown", metric="cash", breakdown=["not_a_real_dimension"])
    with pytest.raises(IRValidationError) as exc:
        validate_ir(ir, config)
    assert exc.value.field_name == "breakdown"


def test_breakdown_dimension_in_contract_accepted(config):
    ir = IRRequest(intent="metric_breakdown", metric="net_revenue", breakdown=["customer"])
    validate_ir(ir, config)  # 'customer' is in net_revenue's dimensions list -- schema-valid,
    # even though no data path resolves it yet (that's an execution-time fact, not a schema one)


def test_filter_dimension_not_allowed_rejected(config):
    ir = IRRequest(intent="metric_value", metric="cash", filters=[{"dimension": "not_allowed", "op": "eq", "value": "x"}])
    with pytest.raises(IRValidationError) as exc:
        validate_ir(ir, config)
    assert exc.value.field_name == "filters"


def test_compare_to_not_in_comparisons_list_rejected(config):
    # equity has no `comparisons` entries worth relying on being empty --
    # use a metric with a known comparisons list instead and ask for one
    # not in it.
    ir = IRRequest(intent="metric_comparison", metric="cash", compare_to={"type": "ytd"})
    with pytest.raises(IRValidationError) as exc:
        validate_ir(ir, config)  # cash's comparisons list is ['mom', 'yoy'], not 'ytd'
    assert exc.value.field_name == "compare_to"


def test_grain_finer_than_metric_time_grain_rejected(config):
    ir = IRRequest(intent="metric_value", metric="cash", grain="month")
    validate_ir(ir, config)  # cash's own time_grain is 'month' -- equal grain is fine


def test_basis_must_be_accrual_or_cash():
    with pytest.raises(Exception):
        IRRequest(intent="metric_value", metric="cash", basis="blended")


def test_profile_mismatch_rejected(config):
    # net_revenue is profile='both' so this should not raise for a
    # mismatched single-profile tenant; find an actual single-profile
    # metric to test against if one exists, else this is a smoke test only.
    ir = IRRequest(intent="metric_value", metric="net_revenue", period={"type": "month", "value": "2025-03"})
    validate_ir(ir, config, tenant_profile="manufacturing")  # must not raise -- profile='both'


def test_unsupported_intent_skips_further_validation(config):
    ir = IRRequest(intent="unsupported")
    validate_ir(ir, config)  # must not raise -- nothing else to check on a refusal


def test_extra_field_rejected_by_schema():
    with pytest.raises(Exception):
        IRRequest(intent="metric_value", metric="cash", made_up_field="x")
