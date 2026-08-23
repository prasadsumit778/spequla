"""The semantic intermediate representation, corpus/07 section 3.

"The model does not write SQL. The model writes a semantic intermediate
representation and a deterministic compiler writes the SQL." (section 1)

IRRequest is the Pydantic model for the ten-field schema. validate_ir()
checks it against the metric registry, exactly as corpus/07's own field
table requires -- rejection is a first-class outcome, never repaired by
guessing (section 3's own words). An IR that fails validation raises
IRValidationError naming the field and the reason; nothing downstream ever
sees a half-valid IR.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.config.loader import ConfigRegistry
from src.semantic.compiler import period_bounds

INTENTS = (
    "metric_value", "metric_trend", "metric_comparison", "metric_breakdown",
    "metric_ranking", "variance_explain", "statement_view", "concentration",
    "ageing", "definition_lookup", "data_health", "unsupported",
)

FILTER_OPS = ("eq", "in", "gt", "gte", "lt", "lte", "ne")

_GRAIN_ORDER = {"month": 0, "quarter": 1, "year": 2}


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["month", "fiscal_quarter", "fiscal_year", "custom_range"]
    value: str
    resolved_from: str | None = None
    resolved_range: tuple[str, str] | None = None


class CompareTo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["prior_period", "yoy", "mom", "ytd"]
    value: str | None = None


class Filter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    op: Literal["eq", "in", "gt", "gte", "lt", "lte", "ne"]
    value: object


class Sort(BaseModel):
    model_config = ConfigDict(extra="forbid")
    by: Literal["metric", "dimension"]
    direction: Literal["asc", "desc"] = "desc"


class IRRequest(BaseModel):
    """corpus/07 section 3's ten fields, verbatim. metric is optional only
    for intents that do not name one (data_health, statement_view without a
    single metric, unsupported)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="spequla.ir.v1", alias="$schema")
    intent: Literal[INTENTS]
    metric: str | None = None
    metric_version: int | None = None
    grain: Literal["month", "quarter", "year"] | None = None
    period: Period | None = None
    compare_to: CompareTo | None = None
    breakdown: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    sort: Sort | None = None
    limit: int | None = None
    basis: Literal["accrual", "cash"] = "accrual"
    as_of: str = "current"


class IRValidationError(Exception):
    """Names the offending field and the reason -- corpus/07 section 3:
    'An IR that fails validation produces a message naming the field and
    the reason. It is never repaired by guessing.'"""

    def __init__(self, field_name: str, reason: str):
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"{field_name}: {reason}")


def _require_metric(config: ConfigRegistry, metric_id: str):
    if metric_id not in config.metrics:
        raise IRValidationError("metric", f"{metric_id!r} is not a metric this system knows")
    contract = config.metrics[metric_id]
    if not contract.registry.p0_ask:
        raise IRValidationError("metric", f"{metric_id!r} is not exposed on the Ask surface (p0_ask=false)")
    return contract


def validate_ir(ir: IRRequest, config: ConfigRegistry, tenant_profile: str | None = None) -> None:
    """Raises IRValidationError on the first failing field. Does not touch
    the database -- pure validation against the loaded registry, per
    corpus/07 section 3's table. Metric-approval-for-this-company and
    decision-resolution are the same transitive gate
    src/semantic/compiler.transitive_blocking_decisions implements; this
    function does not duplicate that logic, it defers to it at compile
    time (stage 6), consistent with 'is approved for this company' being
    a per-tenant runtime fact, not a static schema property.
    """
    if ir.intent not in INTENTS:
        raise IRValidationError("intent", f"{ir.intent!r} is not one of the twelve intents in corpus/07 section 4")

    if ir.intent == "unsupported":
        return  # nothing else to validate -- refusal path, see src/semantic/refusal.py

    needs_metric = ir.intent not in ("data_health", "statement_view", "definition_lookup")
    if needs_metric or ir.metric:
        if not ir.metric:
            raise IRValidationError("metric", f"intent {ir.intent!r} requires a metric")
        contract = _require_metric(config, ir.metric)
        reg = contract.registry

        if tenant_profile and reg.profile != "both" and reg.profile != tenant_profile:
            raise IRValidationError("metric", f"{ir.metric!r} is a {reg.profile}-profile metric, "
                                                f"this company is {tenant_profile}")

        if ir.grain is not None:
            metric_grain = reg.time_grain
            if metric_grain in _GRAIN_ORDER and ir.grain in _GRAIN_ORDER:
                if _GRAIN_ORDER[ir.grain] < _GRAIN_ORDER[metric_grain]:
                    raise IRValidationError("grain", f"{ir.grain!r} is finer than {ir.metric!r}'s own "
                                                        f"time_grain {metric_grain!r} -- not permitted")

        if ir.compare_to is not None:
            allowed = set(reg.comparisons)
            requested = {"prior_period": "mom", "yoy": "yoy", "mom": "mom", "ytd": "ytd"}.get(ir.compare_to.type)
            if requested not in allowed:
                raise IRValidationError("compare_to", f"{ir.compare_to.type!r} is not in {ir.metric!r}'s "
                                                          f"comparisons list {reg.comparisons}")

        allowed_dims = set(reg.dimensions)
        for dim in ir.breakdown:
            if dim not in allowed_dims:
                raise IRValidationError("breakdown", f"dimension {dim!r} is not in {ir.metric!r}'s "
                                                        f"dimensions list {sorted(allowed_dims)}")

        allowed_filter_dims = set(reg.allowed_filters)
        for f in ir.filters:
            if f.dimension not in allowed_filter_dims:
                raise IRValidationError("filters", f"dimension {f.dimension!r} is not in {ir.metric!r}'s "
                                                       f"allowed_filters {sorted(allowed_filter_dims)}")
            if f.op not in FILTER_OPS:
                raise IRValidationError("filters", f"operator {f.op!r} is not in the allowlist {FILTER_OPS}")

    if ir.period is not None:
        if ir.period.type == "month":
            try:
                y, m = ir.period.value.split("-")
                period_bounds(f"{int(y):04d}-{int(m):02d}")
            except Exception as e:
                raise IRValidationError("period", f"{ir.period.value!r} does not resolve to a month: {e}")

    if ir.basis not in ("accrual", "cash"):
        raise IRValidationError("basis", f"{ir.basis!r} must be 'accrual' or 'cash', never blended")

    if ir.as_of != "current":
        try:
            datetime.fromisoformat(ir.as_of)
        except ValueError:
            raise IRValidationError("as_of", f"{ir.as_of!r} is not 'current' or a valid ISO timestamp")
