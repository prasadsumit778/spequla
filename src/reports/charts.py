"""Chart specs, corpus/08 section 8. "A model never selects a chart in P0.
Anything the rules cannot handle falls back to a table, which is always a
correct answer." Every constructor here returns a plain JSON-serialisable
dict -- "store the specification, not the picture," so the same spec
renders identically in the app, a PDF and an email, and can be re-rendered
at a prior snapshot.
"""
from __future__ import annotations

from decimal import Decimal


def _num(v):
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else v


def line_chart(title: str, series_label: str, points: list[tuple[str, Decimal | None]], unit: str = "INR") -> dict:
    """corpus/08 section 8: 'One metric over time' -> Line."""
    return {
        "chart_type": "line", "title": title, "unit": unit,
        "series": [{"label": series_label, "points": [{"period": p, "value": _num(v)} for p, v in points]}],
    }


def kpi_tile_chart(title: str, value: Decimal | None, delta_vs_prior_month: Decimal | None,
                       delta_vs_prior_year: Decimal | None, unit: str) -> dict:
    """corpus/08 section 8: 'Single value against a target or comparative' -> KPI tile with delta."""
    return {
        "chart_type": "kpi_tile", "title": title, "unit": unit, "value": _num(value),
        "delta_vs_prior_month": _num(delta_vs_prior_month), "delta_vs_prior_year": _num(delta_vs_prior_year),
    }


def waterfall_chart(title: str, total_delta: Decimal, components: list[tuple[str, Decimal, bool]]) -> dict:
    """corpus/08 section 8: 'Change between two periods, additive' -> Waterfall bridge.
    components: (label, value, is_residual)."""
    return {
        "chart_type": "waterfall", "title": title, "total_delta": _num(total_delta),
        "components": [{"label": label, "value": _num(v), "is_residual": r} for label, v, r in components],
    }


def table_chart(title: str, columns: list[str], rows: list[list]) -> dict:
    """corpus/08 section 8: 'Anything else' -> Table, always a correct answer."""
    return {"chart_type": "table", "title": title, "columns": columns,
              "rows": [[_num(c) for c in row] for row in rows]}
