"""Pydantic models for the generated config surface (decisions.yml, taxonomy.yml,
config/metrics/*.yml).

Every function that touches a financial concept names the corpus section it
implements, per CLAUDE.md section 8. This module implements corpus/00 (decisions),
corpus/06 section 3 (taxonomy) and corpus/05 + 05a (metric contracts) as typed
boundaries -- nothing here computes a metric value; that is the compiler's job
in a later sprint.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Decision(BaseModel):
    """One row of corpus/00's DECISION-REQUIRED or VERIFY register."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["decision", "verify"]
    status: Literal["resolved", "open"]
    resolution: str | None = None
    note: str | None = None
    label: str | None = None
    governs: list[str] = []


class TaxonomyClass(BaseModel):
    """One canonical class from corpus/06 section 3."""

    model_config = ConfigDict(extra="forbid")

    class_: str
    statement_section: Literal["pnl", "bs", "memo"]
    statement_line: str | None = None
    judgement_class: bool = False
    notes: str | None = None

    def __init__(self, **data):
        if "class" in data:
            data["class_"] = data.pop("class")
        super().__init__(**data)


class MetricRegistryEntry(BaseModel):
    """The corpus/05 registry row fields, present on every metric contract."""

    model_config = ConfigDict(extra="forbid")

    metric_id: str
    label: str
    category: Literal["STANDARD", "CONVENTION", "MANAGEMENT"]
    profile: Literal["both", "manufacturing", "consumer"]
    p0_ask: bool
    p0_statement: bool
    definition: str
    formula: str
    unit: str
    source_facts: list[str]
    dimensions: list[str]
    time_grain: str
    time_logic: str
    aggregation: str
    comparisons: list[str]
    allowed_filters: list[str]
    dependencies: list[str]
    alternative_definitions: str | None = None
    override_allowed: bool
    governed_by: list[str]
    unresolved_decisions: list[str]
    compiles: bool
    version: int
    owner: str


class MetricContractFile(BaseModel):
    """One config/metrics/<metric_id>.yml file as loaded from disk."""

    model_config = ConfigDict(extra="allow")  # `contract`, where present, is corpus/05a's own free shape

    source: str
    registry: MetricRegistryEntry
